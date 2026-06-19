import dataclasses
from typing import Callable

import numpy as np

from core.utils.deprecation import deprecated
from core.utils.control_lib.lib_control.learning.lifted import vector_to_lifted_matrix
from core.utils.control_lib.lib_control.learning.iml.iml import (
    iml_get_norm_optimal_matrices,
    iml_get_learning_gain,
    iml_update,
)


@dataclasses.dataclass
class ILC_TrialData:
    u: np.ndarray
    y: np.ndarray
    e: np.ndarray
    e_norm: float
    L: np.ndarray
    Q: np.ndarray


@dataclasses.dataclass
class ModelFreeILC_TrialData:
    """Per-trial record of model-free (Dual-)ILC.

    Carries the outer ILC trial (``u, y, e, ...``) together with the inner
    iterative-model-learning (IML) state so the model estimate can be inspected
    alongside the input convergence.
    """
    u: np.ndarray                       # input used this trial (carried in)
    y: np.ndarray                       # measured output
    e: np.ndarray                       # tracking error, reference - y
    e_norm: float
    L: np.ndarray                       # outer ILC learning matrix L_j(F_hat_j)
    Q: np.ndarray                       # outer ILC q-filter used this trial
    model_vector: np.ndarray            # f_hat_{j-1} carried into the trial
    model_vector_update: np.ndarray     # f_hat_j after the inner IML step
    model_prediction: np.ndarray        # U_j f_hat_{j-1}
    model_output_error: np.ndarray      # e_{f,j} = y_j - U_j f_hat_{j-1}
    model_output_error_norm: float
    model_learning_matrix: np.ndarray   # inner IML gain L_f (K_j)
    model_q_filter: np.ndarray | None   # inner IML q-filter Q_m, if any
    s: float                            # outer (input) regularisation used
    s_m: float                          # inner (model) regularisation used
    model_estimation_error_norm: float  # ||f_target - f_hat_j||, nan if unknown


# ======================================================================================================================
def ilc_update(u: np.ndarray, e: np.ndarray, L: np.ndarray, Q: np.ndarray | None = None, *args, **kwargs):
    if Q is None:
        Q: np.ndarray = np.eye(len(u))

    Q = np.asarray(Q)
    L = np.asarray(L)
    u = np.asarray(u)
    e = np.asarray(e)

    N = len(u)

    assert Q.shape == (N, N), f"Q must be {N}x{N}, got {Q.shape}"  # type: ignore
    assert L.shape == (N, N), f"L must be {N}x{N}, got {L.shape}"
    assert len(e) == N, f"e must have length {N}, got {len(e)}"

    u = Q @ (u + L @ e)  # type: ignore
    return u


# ======================================================================================================================


# ======================================================================================================================
def ilc_get_norm_optimal_matrices(P: np.ndarray, s: float, r: float = 0.0):
    Qw = np.eye(P.shape[0])
    Rw = r * np.eye(P.shape[0])
    Sw = s * np.eye(P.shape[0])

    Q = np.linalg.inv(P.T @ Qw @ P + Rw + Sw) @ (P.T @ Qw @ P + Sw)
    L = np.linalg.inv(P.T @ Qw @ P + Sw) @ P.T @ Qw

    return L, Q


# ======================================================================================================================
def ilc_pd_learning_matrix(kp: float, kd: float, N: int):
    L = np.zeros((N, N))
    L[0][0] = kp

    idx = 0
    for j in range(1, N):
        L[j][idx] = -kd
        L[j][idx + 1] = kp + kd
        idx = idx + 1
    return L


# ======================================================================================================================
def run_ilc(
        dynamics: Callable,
        reference: np.ndarray,
        P: np.ndarray,
        J: int,
        s: float = 1.0,
        r: float = 0.0,
        u0: np.ndarray | None = None,
):
    N = P.shape[0]

    if u0 is None:
        u0 = np.zeros(N)

    trials = []

    u = u0
    L, Q = ilc_get_norm_optimal_matrices(P, s, r)

    for j in range(J):
        y = dynamics(u)
        e = reference - y
        u_next = ilc_update(u, e, L, Q)
        trial = ILC_TrialData(
            u=u,
            y=y,
            e=e,
            L=L,
            Q=Q,
            e_norm=np.linalg.norm(e, ord=2)  # type: ignore
        )
        trials.append(trial)
        u = u_next

    return trials


# ======================================================================================================================
def run_model_free_dilc(
        dynamics: Callable,
        reference: np.ndarray,
        J: int,
        N: int | None = None,
        u0: np.ndarray | None = None,
        f_0: np.ndarray | None = None,
        s: float = 1.0,
        r: float = 0.0,
        s_m: float | None = None,
        adaptive_s_m: bool = True,
        kappa: float = 100.0,
        Q: np.ndarray | None = None,
        Q_m: np.ndarray | None = None,
        f_target: np.ndarray | None = None,
) -> list[ModelFreeILC_TrialData]:
    r"""Model-free norm-optimal ILC -- the single-agent Dual-ILC of
    ``sec:mf-dualilc``.

    Standard norm-optimal ILC needs the plant Markov matrix
    :math:`\mathbf{F}` to synthesise its operators :math:`(\mathbf{L}, \mathbf{Q})`.
    Dual-ILC removes that prerequisite by running an inner iterative
    model-learning (IML) loop that identifies the plant impulse response on the
    fly from the same trials, and synthesising the outer ILC gains from the
    running estimate :math:`\hat{\mathbf{F}}_j = \mathcal{M}(\hat{\mathbf{f}}_j)`.
    The true plant is used only to roll out :math:`\mathbf{y}_j` and enters
    neither update. This is the ILC analogue of :func:`run_model_free_iitl`.

    Each trial, in order:

    1. roll out the current input, :math:`\mathbf{y}_j = \mathcal{F}(\mathbf{u}_j)`;
    2. **model loop (IML)** -- predict :math:`\mathbf{U}_j\hat{\mathbf{f}}_{j-1}`,
       form the residual :math:`\mathbf{e}_{\mathrm{f},j} = \mathbf{y}_j -
       \mathbf{U}_j\hat{\mathbf{f}}_{j-1}`, and update the impulse-response
       estimate by the norm-optimal IML step (Eq.~mf-iml-loop);
    3. **input loop (ILC)** -- synthesise :math:`(\mathbf{L}_j, \mathbf{Q}_j)`
       at :math:`\hat{\mathbf{F}}_j = \mathcal{M}(\hat{\mathbf{f}}_j)`
       (Eq.~mf-gain-synthesis) and update the input from the tracking error
       (Eq.~mf-ilc-loop).

    Parameters
    ----------
    dynamics : Callable
        Plant roll-out: maps an input trajectory to an output trajectory.
    reference : ndarray
        Tracking reference :math:`\mathbf{y}^\star` (length ``N``).
    J : int
        Number of trials.
    N : int, optional
        Trajectory length; defaults to ``len(reference)``.
    u0 : ndarray, optional
        Initial input. Defaults to zeros. NOTE: with ``u0 = 0`` *and*
        ``f_0 = 0`` the scheme is degenerate -- a zero input excites nothing,
        the model stays zero, and the synthesised gain is zero (frozen).
        Supply either a non-zero initial input (e.g. a transfer prior) or a
        coarse model prior ``f_0``.
    f_0 : ndarray, optional
        Initial impulse-response estimate :math:`\hat{\mathbf{f}}_0`. Defaults
        to zeros; a nominal-plant prior warms up the inner loop.
    s : float, optional
        Outer ILC input-change weight (``sec:fundamentals-no-ilc``). Larger =
        gentler input updates.
    r : float, optional
        Outer ILC input-magnitude weight.
    s_m : float, optional
        Inner IML regularisation. Ignored (and may be ``None``) when
        ``adaptive_s_m`` is set.
    adaptive_s_m : bool, optional
        Recompute the inner regularisation per trial from the current input
        regressor (condition-number heuristic, cap ``kappa``). Default ``True``.
    kappa : float, optional
        Condition-number cap for the adaptive inner regulariser.
    Q : ndarray, optional
        Optional override for the outer ILC q-filter. ``None`` uses the
        norm-optimal :math:`\mathbf{Q}_j` synthesised from the model estimate.
    Q_m : ndarray, optional
        Optional inner IML q-filter. ``None`` leaves the norm-optimal IML
        filter (identity at ``r = 0``); a low-pass ``Q_m`` suppresses
        high-frequency noise in the model estimate.
    f_target : ndarray, optional
        True plant Markov vector, used **only** to log the model-estimation
        error per trial; never enters the update.

    Returns
    -------
    list[ModelFreeILC_TrialData]
        Per-trial records (outer ILC + inner IML state).
    """
    reference = np.asarray(reference, dtype=float)
    if N is None:
        N = len(reference)
    if u0 is None:
        u0 = np.zeros(N)
    if f_0 is None:
        f_0 = np.zeros(N)

    u = np.asarray(u0, dtype=float)
    model_vector = np.asarray(f_0, dtype=float)
    trials: list[ModelFreeILC_TrialData] = []

    for j in range(J):
        # --- roll out the current input on the true (unknown) plant ----------
        y = np.asarray(dynamics(u), dtype=float)

        # --- inner loop: iterative model learning (IML), Eq.~mf-iml-loop -----
        model_prediction = vector_to_lifted_matrix(u) @ model_vector
        model_output_error = y - model_prediction

        if adaptive_s_m:
            s_m_j = iml_get_learning_gain(u, kappa)
        elif s_m is None:
            raise ValueError("s_m must be set when adaptive_s_m is False")
        else:
            s_m_j = float(s_m)

        if s_m_j > 0.0:
            K_j, Q_iml = iml_get_norm_optimal_matrices(u, s=s_m_j, r=0.0)
            Q_inner = Q_iml if Q_m is None else Q_m
            model_vector_update = iml_update(model_vector, model_output_error,
                                             K_j, Q_inner)
        else:
            # No excitation this trial (e.g. a zero initial input with the
            # adaptive rule -> s_m = 0): the IML regressor is singular and the
            # model loop has no information, so carry the estimate over
            # unchanged. The outer ILC still updates from the prior model f_0.
            K_j = np.zeros((N, N))
            model_vector_update = np.array(model_vector, dtype=float)

        # --- outer loop: norm-optimal ILC at the current model estimate ------
        # Gains synthesised from F_hat_j = M(f_hat_j), Eq.~mf-gain-synthesis.
        P_hat = vector_to_lifted_matrix(model_vector_update)
        L_j, Q_no = ilc_get_norm_optimal_matrices(P_hat, s, r)
        Q_outer = Q_no if Q is None else Q
        e = reference - y
        u_next = ilc_update(u, e, L_j, Q_outer)

        if f_target is not None:
            model_estimation_error_norm = float(
                np.linalg.norm(np.asarray(f_target) - model_vector_update))
        else:
            model_estimation_error_norm = float("nan")

        trials.append(ModelFreeILC_TrialData(
            u=u,
            y=y,
            e=e,
            e_norm=float(np.linalg.norm(e, ord=2)),
            L=L_j,
            Q=Q_outer,
            model_vector=model_vector,
            model_vector_update=model_vector_update,
            model_prediction=model_prediction,
            model_output_error=model_output_error,
            model_output_error_norm=float(
                np.linalg.norm(model_output_error, ord=2)),
            model_learning_matrix=K_j,
            model_q_filter=Q_m,
            s=float(s),
            s_m=s_m_j,
            model_estimation_error_norm=model_estimation_error_norm,
        ))

        u = u_next
        model_vector = model_vector_update

    return trials


# ======================================================================================================================
def debug_plots_ilc(trials):
    import matplotlib.pyplot as plt

    if not trials:
        raise ValueError("trials is empty, nothing to plot")

    J = len(trials)
    # Recover the reference from the first trial: e = reference - y  ->  reference = y + e
    reference = trials[0].y + trials[0].e

    fig, (ax_err, ax_y, ax_u) = plt.subplots(1, 3, figsize=(15, 4))

    # --- Left panel: error-norm progression ---------------------------------
    e_norms = [t.e_norm for t in trials]
    ax_err.plot(range(J), e_norms, marker="o", color="C0")
    ax_err.set_xlabel("Trial $j$")
    ax_err.set_ylabel(r"$\|e_j\|_2$")
    ax_err.set_title("Error-norm progression")
    ax_err.set_yscale("log")
    ax_err.grid(True, which="both", alpha=0.3)

    # Opacity ramp: early trials faint, latest trial fully opaque.
    alphas = np.linspace(0.15, 1.0, J)

    # --- Middle panel: reference output and all outputs ---------------------
    for j, (t, a) in enumerate(zip(trials, alphas)):
        ax_y.plot(t.y, color="C1", alpha=a)
    # Reference drawn last (on top) with a dotted line.
    ax_y.plot(reference, color="k", linewidth=2.0, linestyle=":", label="reference")
    ax_y.set_xlabel("Time step $k$")
    ax_y.set_ylabel("Output $y$")
    ax_y.set_title("Output trajectories")
    ax_y.legend()
    ax_y.grid(True, alpha=0.3)

    # --- Right panel: all inputs --------------------------------------------
    for j, (t, a) in enumerate(zip(trials, alphas)):
        ax_u.plot(t.u, color="C2", alpha=a)
    ax_u.set_xlabel("Time step $k$")
    ax_u.set_ylabel("Input $u$")
    ax_u.set_title("Input trajectories")
    ax_u.grid(True, alpha=0.3)

    fig.tight_layout()
    plt.show()
    return fig


# ======================================================================================================================
# Compatibility Stubs
@deprecated
def qlearning(P: np.ndarray, Qw, Rw, Sw):
    L, Q = ilc_get_norm_optimal_matrices(P, Sw, Rw)
    return Q, L


@deprecated
def pdlearning(kp, kd, N):
    return ilc_pd_learning_matrix(kp, kd, N)
