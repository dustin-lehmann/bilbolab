from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

import numpy as np

from core.utils.control_lib.lib_control.learning.lifted import vector_to_lifted_matrix
from core.utils.control_lib.lib_control.learning.iml.iml import (
    iml_get_norm_optimal_matrices,
    iml_get_learning_gain,
    iml_update,
)
from research.iitl.iitl_utils import TrajectoryPair


# ======================================================================================================================
def iitl_get_scalar_learning_matrix(P_target: np.ndarray,
                                    u_source: np.ndarray,
                                    s: float) -> np.ndarray:
    r"""Scalar-weight IITL learning matrix.

    Implements Def.~design_L with the scalar-weight parameterisation
    :math:`\mathbf{W}_e = \mathbf{I}_N`, :math:`\mathbf{W}_{\Delta t} = s\,\mathbf{I}_N`:

    .. math::
        \mathbf{L}_j = (\mathbf{P}_j^\top \mathbf{P}_j + s\mathbf{I})^{-1}
                       \mathbf{P}_j^\top,
        \qquad \mathbf{P}_j = \mathbf{F}^{(\beta)}\,\mathcal{M}(\mathbf{u}_j^{(\alpha)}).

    Parameters
    ----------
    P_target   : (N, N) transition matrix of the target system, :math:`\mathbf{F}^{(\beta)}`.
    u_source   : (N,) source input :math:`\mathbf{u}_j^{(\alpha)}`.
    s          : trial-change weight, :math:`s > 0`.

    Returns
    -------
    L_j : (N, N) learning matrix.
    """
    P_j = P_target @ vector_to_lifted_matrix(u_source)
    N = P_j.shape[0]
    I_N = np.eye(N)
    A = (P_j.T @ P_j) + s * I_N
    B = P_j.T
    return np.linalg.solve(A, B)


# ======================================================================================================================
def iitl_update(t_j: np.ndarray,
                L_j: np.ndarray,
                e_j: np.ndarray,
                Q: np.ndarray | None = None) -> np.ndarray:
    r"""Transfer-vector update.

    Unfiltered update (Eq.~learning_update):

    .. math:: \hat{\mathbf{t}}_{j+1} = \hat{\mathbf{t}}_{j} + \mathbf{L}_j\,\mathbf{e}_j.

    Filtered update (Eq.~filtered_learning_update) when ``Q`` is provided:

    .. math:: \hat{\mathbf{t}}_{j+1} = \mathbf{Q}\,(\hat{\mathbf{t}}_{j} + \mathbf{L}_j\,\mathbf{e}_j).
    """
    t_next = t_j + L_j @ e_j
    if Q is not None:
        t_next = Q @ t_next
    return t_next


# ======================================================================================================================
def iitl_update_rls_gramian(G_prev: np.ndarray,
                            P_j: np.ndarray) -> np.ndarray:
    r"""Incremental update of the cumulative regressor Gramian.

    Implements Eq.~rls_gramian:

    .. math:: \mathbf{G}_j = \mathbf{G}_{j-1} + \mathbf{P}_j^\top \mathbf{P}_j.

    The caller owns ``G_prev`` (initialise with ``np.zeros((N, N))`` for
    ``j = 0``) and must pass the returned matrix back in on the next trial.

    Parameters
    ----------
    G_prev : (N, N) cumulative Gramian through trial :math:`j-1`.
    P_j    : (N, N) current-trial regressor
             :math:`\mathbf{P}_j = \mathbf{F}^{(\beta)}\mathcal{M}(\mathbf{u}_j^{(\alpha)})`.

    Returns
    -------
    G_j : (N, N) cumulative Gramian through trial :math:`j`.
    """
    return G_prev + P_j.T @ P_j


# ======================================================================================================================
def iitl_get_rls_learning_matrix(G_j: np.ndarray,
                                 P_j: np.ndarray,
                                 s: float) -> np.ndarray:
    r"""Accumulated-information ("RLS") learning matrix.

    Implements Def.~rls_update_design / Eq.~rls_L with the scalar-weight
    parameterisation :math:`\mathbf{W}_e = \mathbf{I}_N`,
    :math:`\mathbf{W}_{\Delta t} = s\,\mathbf{I}_N` augmented by the
    cumulative regressor Gramian :math:`\mathbf{G}_j`:

    .. math::
        \mathbf{L}_j^{\mathrm{RLS}} = (\mathbf{G}_j + s\mathbf{I}_N)^{-1}\mathbf{P}_j^\top.

    Unrolling Eq.~learning_update under this learning matrix produces the
    ridge-regularised batch least-squares estimator Eq.~rls_batch. ``G_j``
    must already include :math:`\mathbf{P}_j^\top \mathbf{P}_j` on entry;
    use :func:`iitl_update_rls_gramian` to update it before calling this
    function.

    Parameters
    ----------
    G_j : (N, N) cumulative regressor Gramian through trial :math:`j`.
    P_j : (N, N) current-trial regressor.
    s   : regularisation weight, :math:`s > 0`.

    Returns
    -------
    L_j : (N, N) learning matrix.
    """
    N = P_j.shape[0]
    return np.linalg.solve(G_j + s * np.eye(N), P_j.T)


# ======================================================================================================================
def iitl_get_exploration_biased_weight(G_j: np.ndarray,
                                       s: float,
                                       eps: float | None = None,
                                       delta: float = 1e-4) -> np.ndarray:
    r"""Eigenvalue-shaped trial-change weight built from the cumulative Gramian.

    Implements Eq.~appendix_W_dt_def of the appendix on alternative learning
    matrix designs:

    .. math::
        \mathbf{W}_{\Delta\mathbf{t},j} = s\,\mathbf{V}_j\,\mathrm{diag}\!\left(\frac{\sigma_{i,j}}{\sigma_{i,j} + \varepsilon}\right)\!\mathbf{V}_j^\top + \delta\mathbf{I}_N\,,

    where :math:`\mathbf{G}_j = \mathbf{V}_j\,\mathrm{diag}(\sigma_{i,j})\,\mathbf{V}_j^\top`.
    Along well-resolved eigendirections of :math:`\mathbf{G}_j`
    (:math:`\sigma_{i,j} \gg \varepsilon`) the weight saturates at :math:`s`;
    along poorly-resolved directions (:math:`\sigma_{i,j} \ll \varepsilon`) it
    falls to the floor :math:`\delta`.

    Parameters
    ----------
    G_j : (N, N) cumulative regressor Gramian through trial :math:`j`.
    s   : nominal regularisation weight, :math:`s > 0`.
    eps : knee parameter. Defaults to ``s`` if not provided.
    delta : floor on the weight to keep the inverse well-conditioned along
            unexcited directions. Defaults to ``1e-4``.

    Returns
    -------
    W_dt : (N, N) symmetric positive-definite weight matrix.
    """
    if eps is None:
        eps = s
    N = G_j.shape[0]
    sigmas, V = np.linalg.eigh(G_j)
    sigmas = np.clip(sigmas, 0.0, None)
    W_dt = s * (V * (sigmas / (sigmas + eps))) @ V.T + delta * np.eye(N)
    # Symmetrise to suppress eigh-induced floating-point asymmetry.
    return 0.5 * (W_dt + W_dt.T)


# ======================================================================================================================
def iitl_get_exploration_biased_learning_matrix(P_j: np.ndarray,
                                                G_j: np.ndarray,
                                                s: float,
                                                eps: float | None = None,
                                                delta: float = 1e-4) -> np.ndarray:
    r"""Exploration-biased learning matrix.

    Implements Def.~exploration_biased_design (Eq.~appendix_exploration_L):

    .. math::
        \mathbf{L}_j^{\mathrm{expl}} = \bigl(\mathbf{P}_j^\top\mathbf{P}_j + \mathbf{W}_{\Delta\mathbf{t},j}\bigr)^{-1}\mathbf{P}_j^\top\,,

    with :math:`\mathbf{W}_{\Delta\mathbf{t},j}` built from the eigendecomposition
    of :math:`\mathbf{G}_j` via :func:`iitl_get_exploration_biased_weight`.
    Pairs the *current-trial* data block with a spectrum-aware regulariser; the
    iterate consequently exhibits per-trajectory cycling on multi-trajectory
    learning sets (the cumulative information is used to shape the regulariser
    only, not as the data block in the inverse). See
    :func:`iitl_get_hybrid_rls_exploration_learning_matrix` for the variant that
    eliminates the cycling.

    ``G_j`` must already include :math:`\mathbf{P}_j^\top \mathbf{P}_j` on entry.
    """
    W_dt = iitl_get_exploration_biased_weight(G_j, s, eps, delta)
    return np.linalg.solve(P_j.T @ P_j + W_dt, P_j.T)


# ======================================================================================================================
def iitl_get_hybrid_rls_exploration_learning_matrix(P_j: np.ndarray,
                                                    G_j: np.ndarray,
                                                    s: float,
                                                    eps: float | None = None,
                                                    delta: float = 1e-4) -> np.ndarray:
    r"""Hybrid RLS-plus-exploration learning matrix.

    Implements Def.~hybrid_rls_exploration_design (Eq.~appendix_hybrid_L):

    .. math::
        \mathbf{L}_j^{\mathrm{hybrid}} = \bigl(\mathbf{G}_j + \mathbf{W}_{\Delta\mathbf{t},j}\bigr)^{-1}\mathbf{P}_j^\top\,.

    Pairs the *cumulative* Gramian data block (as in
    :func:`iitl_get_rls_learning_matrix`) with the eigenvalue-shaped weight of
    :func:`iitl_get_exploration_biased_weight`. The cumulative-Gramian-in-the-inverse
    delivers the accumulated-information design's anti-cycling property and
    :math:`\mathcal{O}(1/j)` gain decay on the resolved subspace, while
    :math:`\mathbf{W}_{\Delta\mathbf{t},j}` supplies the spectrum-adaptive floor
    on the unresolved one. Empirically the strongest noise-free design of the
    four implemented in this module on the chapter's introductory pair.

    ``G_j`` must already include :math:`\mathbf{P}_j^\top \mathbf{P}_j` on entry.
    """
    W_dt = iitl_get_exploration_biased_weight(G_j, s, eps, delta)
    return np.linalg.solve(G_j + W_dt, P_j.T)


# ======================================================================================================================
def iitl_get_learning_gain(f_target: np.ndarray, u: np.ndarray, kappa: float = 100.0) -> float:
    # Check if f_target is a vector or a matrix
    if f_target.ndim == 1:
        f_target = vector_to_lifted_matrix(f_target)

    Fu = f_target @ u
    sigma_max = np.linalg.norm(Fu, 2)
    s = (sigma_max / kappa) ** 2
    return float(s)


# ======================================================================================================================
@dataclass
class IITL_Trial_Data:
    u_source: np.ndarray
    y_source: np.ndarray
    u_target: np.ndarray
    y_target: np.ndarray
    learning_error: np.ndarray
    learning_error_norm: float
    s: float
    learning_matrix: np.ndarray
    q_filter: np.ndarray | None
    transfer_vector: np.ndarray
    transfer_vector_update: np.ndarray


@dataclass
class IITL_Results:
    trials: list[IITL_Trial_Data]


# ======================================================================================================================
@dataclass
class ModelFreeIITL_Trial_Data:
    """Per-trial record of the model-free IITL scheme (Alg.~model-free-iitl).

    Extends the fields of :class:`IITL_Trial_Data` (the outer transfer loop)
    with the state of the inner model-learning loop, which estimates the
    target Markov-parameter vector :math:`\\mathbf{f}^{(\\beta)}` instead of
    relying on a known target model.

    Outer-loop fields match :class:`IITL_Trial_Data`; ``learning_matrix`` here
    is the *model-based* matrix :math:`\\hat{\\mathbf{L}}_j`
    (Eq.~model_free_transfer_learning_matrix), built from the current model
    estimate rather than the true target dynamics.
    """
    # --- outer (transfer) loop -- mirrors IITL_Trial_Data ---------------------
    u_source: np.ndarray
    y_source: np.ndarray
    u_target: np.ndarray
    y_target: np.ndarray
    learning_error: np.ndarray
    learning_error_norm: float
    s: float
    learning_matrix: np.ndarray              # L_hat_j (model-based)
    q_filter: np.ndarray | None
    transfer_vector: np.ndarray              # t_j  (carried into trial j)
    transfer_vector_update: np.ndarray       # t_{j+1}
    # --- inner (model-learning) loop -----------------------------------------
    model_vector: np.ndarray                 # f_hat_{j-1} (carried into trial j)
    model_vector_update: np.ndarray          # f_hat_j (after the inner update)
    model_prediction: np.ndarray             # y_hat_j^(beta), Eq.~model_free_prediction
    model_output_error: np.ndarray           # e_{f,j}, Eq.~model_output_error
    model_output_error_norm: float
    model_learning_matrix: np.ndarray        # K_j, Eq.~model_learning_matrix
    model_q_filter: np.ndarray | None        # inner q-filter on the model update
    model_estimation_error_norm: float       # ||f^(beta) - f_hat_j||, if f known
    s_m: float


@dataclass
class ModelFreeIITL_Results:
    trials: list[ModelFreeIITL_Trial_Data]


def run_iitl(
        target_dynamics: Callable,
        learning_set: list[TrajectoryPair],
        f_target: np.ndarray,
        J: int,
        N: int | None = None,
        t_1: np.ndarray | None = None,
        s: float | None = None,
        adaptive_s: bool = False,
        kappa: float = 100.0,
        adaptive_q: bool = False,
        Q: np.ndarray | None = None,
) -> IITL_Results:
    """Run the base Iterative Input Transfer Learning (IITL) scheme.

    Implements Alg.~iitl: at each trial a source trajectory is drawn from
    ``learning_set`` (cyclic selection), transferred to the target via
    :math:`\\mathcal{M}(\\hat{\\mathbf{t}}_j)\\mathbf{u}_j^{(\\alpha)}`, applied
    to ``target_dynamics``, and the resulting learning error is used to update
    the transfer-vector estimate via the scalar-weight learning matrix.

    Notes
    -----
    If ``t_1`` is not provided, the initial estimate defaults to
    :math:`[1, 0, \\dots, 0]^\\top`, which corresponds to the **unity transfer**
    :math:`\\mathcal{M}(\\hat{\\mathbf{t}}_1) = \\mathbf{I}` — i.e. the first
    trial applies the source input to the target unchanged. This is a sensible
    warm start whenever source and target share the same relative degree.
    Pass ``t_1=np.zeros((N, 1))`` to start from the zero estimate instead.
    """
    L = len(learning_set)
    trials = []
    if N is None:
        N = len(learning_set[0].input)

    if t_1 is None:
        t_1 = np.zeros((N,))
        t_1[0] = 1

    transfer_vector = t_1

    for j in range(0, J):
        # Draw the learning input
        learning_pair = learning_set[j % L]
        u_source = learning_pair.input
        y_source = learning_pair.output

        # Transfer the learning input to the target system
        u_target = vector_to_lifted_matrix(transfer_vector) @ u_source

        # Apply the transferred input to the target system
        y_target = target_dynamics(u_target)

        # Calculate the error
        learning_error = y_source - y_target

        # Optional: calculate the adaptive s
        if adaptive_s:
            s = iitl_get_learning_gain(f_target, u_source, kappa)

        if s is None:
            raise ValueError("Learning gain cannot be None")

        # Calculate the learning matrix
        L_j = iitl_get_scalar_learning_matrix(f_target, u_source, s)

        if adaptive_q:
            raise NotImplementedError("Not yet implemented")

        # Update the transfer vector
        transfer_vector_update = iitl_update(transfer_vector,
                                             L_j,
                                             learning_error,
                                             Q)

        trial_data = IITL_Trial_Data(
            u_source=u_source,
            y_source=y_source,
            u_target=u_target,
            y_target=y_target,
            learning_error=learning_error,
            learning_error_norm=np.linalg.norm(learning_error, ord=2),  # type: ignore
            s=s,
            learning_matrix=L_j,
            q_filter=Q,
            transfer_vector=transfer_vector,
            transfer_vector_update=transfer_vector_update,
        )
        trials.append(trial_data)
        transfer_vector = transfer_vector_update

    results = IITL_Results(
        trials=trials
    )
    return results


# ======================================================================================================================
class RLSDesign(StrEnum):
    """Learning-matrix designs that maintain the cumulative regressor Gramian.

    Members are plain strings, so callers can pass either the enum member or
    the string literal interchangeably.

    Members
    -------
    PLAIN              : Def.~rls_update_design (accumulated-information).
    EXPLORATION_BIASED : Def.~exploration_biased_design.
    HYBRID             : Def.~hybrid_rls_exploration_design (RLS + exploration).
    """
    PLAIN = "rls"
    EXPLORATION_BIASED = "exploration_biased"
    HYBRID = "hybrid_rls_exploration"


def run_rls_iitl(
        target_dynamics: Callable,
        learning_set: list[TrajectoryPair],
        f_target: np.ndarray,
        J: int,
        s: float,
        N: int = None,
        t_1: np.ndarray | None = None,
        Q: np.ndarray | None = None,
        design: RLSDesign | str = RLSDesign.PLAIN,
        eps: float | None = None,
        delta: float = 1e-4,
) -> IITL_Results:
    """Run an IITL variant that maintains the cumulative regressor Gramian.

    Sister of :func:`run_iitl` for the three learning-matrix designs that use
    :math:`\\mathbf{G}_j = \\sum_{k\\le j}\\mathbf{P}_k^\\top\\mathbf{P}_k`:
    plain RLS, exploration-biased, and hybrid RLS-plus-exploration. See
    :class:`RLSDesign` for the available members.

    Parameters
    ----------
    s : regularisation weight, :math:`s > 0`. Mandatory (no adaptive-:math:`s`
        is provided here -- the spectrum-aware designs already adapt their
        regulariser per direction).
    design : :class:`RLSDesign` member, or its string value. Defaults to plain RLS.
    eps : knee parameter for the exploration-shaped designs. Defaults to ``s``.
        Ignored for plain RLS.
    delta : floor parameter for the exploration-shaped designs. Defaults to
        ``1e-4``. Ignored for plain RLS.
    Q : optional Q-filter to apply to the post-update iterate.

    See :func:`run_iitl` for the semantics of ``t_1`` and the trial loop.
    """
    try:
        design = RLSDesign(design)
    except ValueError as exc:
        raise ValueError(
            f"Unknown RLS design {design!r}; valid options: "
            f"{[d.value for d in RLSDesign]}") from exc
    if s is None:
        raise ValueError("Regularisation s is required for run_rls_iitl")

    L = len(learning_set)
    trials = []
    if N is None:
        N = len(learning_set[0].input)

    if t_1 is None:
        t_1 = np.zeros((N,))
        t_1[0] = 1

    transfer_vector = t_1
    G = np.zeros((N, N))

    if f_target.ndim == 1:
        F_target_mat = vector_to_lifted_matrix(f_target)
    else:
        F_target_mat = f_target

    for j in range(0, J):
        learning_pair = learning_set[j % L]
        u_source = learning_pair.input
        y_source = learning_pair.output

        u_target = vector_to_lifted_matrix(transfer_vector) @ u_source
        y_target = target_dynamics(u_target)
        learning_error = y_source - y_target

        # Per-trial regressor and cumulative Gramian update.
        P_j = F_target_mat @ vector_to_lifted_matrix(u_source)
        G = iitl_update_rls_gramian(G, P_j)

        if design is RLSDesign.PLAIN:
            L_j = iitl_get_rls_learning_matrix(G, P_j, s)
        elif design is RLSDesign.EXPLORATION_BIASED:
            L_j = iitl_get_exploration_biased_learning_matrix(
                P_j, G, s, eps=eps, delta=delta)
        else:  # RLSDesign.HYBRID
            L_j = iitl_get_hybrid_rls_exploration_learning_matrix(
                P_j, G, s, eps=eps, delta=delta)

        transfer_vector_update = iitl_update(transfer_vector,
                                             L_j,
                                             learning_error,
                                             Q)

        trials.append(IITL_Trial_Data(
            u_source=u_source,
            y_source=y_source,
            u_target=u_target,
            y_target=y_target,
            learning_error=learning_error,
            learning_error_norm=np.linalg.norm(learning_error, ord=2),  # type: ignore
            s=s,
            learning_matrix=L_j,
            q_filter=Q,
            transfer_vector=transfer_vector,
            transfer_vector_update=transfer_vector_update,
        ))
        transfer_vector = transfer_vector_update

    return IITL_Results(trials=trials)


# ======================================================================================================================
def run_model_free_iitl(
        target_dynamics: Callable,
        learning_set: list[TrajectoryPair],
        J: int,
        N: int | None = None,
        t_1: np.ndarray | None = None,
        f_0: np.ndarray | None = None,
        s: float | None = None,
        s_m: float | None = None,
        adaptive_s: bool = False,
        adaptive_s_m: bool = False,
        kappa: float = 100.0,
        Q: np.ndarray | None = None,
        Q_m: np.ndarray | None = None,
        f_target: np.ndarray | None = None,
) -> ModelFreeIITL_Results:
    """Run the model-free Iterative Input Transfer Learning (IITL) scheme.

    Implements Alg.~model-free-iitl: the standard IITL outer loop
    (Sec.~iitl_estimation) wrapped around an inner model-learning (IML) loop
    that estimates the target Markov-parameter vector
    :math:`\\mathbf{f}^{(\\beta)}` on the fly. The true target dynamics
    :math:`\\mathbf{F}^{(\\beta)}` are never accessed -- only the measured
    target output enters the algorithm -- which removes the dependence of the
    learning-matrix design on a known target model.

    Each trial performs, in order:

    1. select a source pair from ``learning_set`` (cyclic selection);
    2. transfer the input, :math:`\\mathbf{u}_j^{(\\beta)} =
       \\mathcal{M}(\\hat{\\mathbf{t}}_j)\\,\\mathbf{u}_j^{(\\alpha)}`, and
       apply it to ``target_dynamics``;
    3. **inner loop** -- predict the target output from the previous model
       estimate (Eq.~model_free_prediction), form the model output error
       (Eq.~model_output_error), and update the model estimate via the
       norm-optimal IML step (Eq.~model_update) using the model learning
       matrix :math:`\\mathbf{K}_j` (Eq.~model_learning_matrix);
    4. **outer loop** -- form the learning error (Eq.~learning_error), build
       the *model-based* transfer learning matrix :math:`\\hat{\\mathbf{L}}_j`
       (Eq.~model_free_transfer_learning_matrix) from the updated model
       estimate, and update the transfer vector (Eq.~model_free_transfer_update).

    Parameters
    ----------
    target_dynamics : Callable
        Target agent: maps a target input to a target output trajectory.
    learning_set : list[TrajectoryPair]
        Source input/output pairs :math:`\\mathfrak{L}`.
    J : int
        Number of trials. Each trial is one experiment on the target.
    N : int, optional
        Trajectory length; defaults to ``len(learning_set[0].input)``.
    t_1 : ndarray, optional
        Initial transfer-vector estimate. Defaults to the unity transfer
        :math:`[1, 0, \\dots, 0]^\\top`, so the first trial applies the source
        input to the target unchanged.
    f_0 : ndarray, optional
        Initial target-model estimate :math:`\\hat{\\mathbf{f}}_0^{(\\beta)}`.
        Defaults to the zero vector. A coarse plant-class prior (Markov
        parameters of a nominal plant) is recommended: it warms up the inner
        loop and avoids the degenerate ``t_1 = 0, f_0 = 0`` freeze.
    s : float, optional
        Outer (transfer) regularisation, :math:`s > 0`. Ignored when
        ``adaptive_s`` is set.
    s_m : float, optional
        Inner (model) regularisation, :math:`s_{\\mathrm{m}} > 0`. Ignored
        when ``adaptive_s_m`` is set.
    adaptive_s, adaptive_s_m : bool, optional
        Recompute the corresponding regularisation per trial from the current
        regressor (condition-number heuristic with cap ``kappa``).
    kappa : float, optional
        Condition-number cap for the adaptive regularisers.
    Q : ndarray, optional
        Optional outer q-filter applied to the transfer-vector update.
    Q_m : ndarray, optional
        Optional inner q-filter applied to the model-vector update (the IML
        loop). ``None`` leaves the norm-optimal IML filter in place, which at
        ``r = 0`` is the identity -- i.e. an unfiltered model update. A
        low-pass ``Q_m`` suppresses high-frequency noise accumulating in the
        model estimate.
    f_target : ndarray, optional
        True target Markov vector. Used **only** for logging the model
        estimation error per trial; never enters the update. ``None`` leaves
        ``model_estimation_error_norm`` as ``nan``.

    Returns
    -------
    ModelFreeIITL_Results
        Per-trial records, including the inner-loop model estimates.
    """
    L = len(learning_set)
    if N is None:
        N = len(learning_set[0].input)

    if t_1 is None:
        t_1 = np.zeros((N,))
        t_1[0] = 1.0
    if f_0 is None:
        f_0 = np.zeros((N,))

    transfer_vector = np.asarray(t_1, dtype=float)
    model_vector = np.asarray(f_0, dtype=float)

    trials: list[ModelFreeIITL_Trial_Data] = []

    for j in range(0, J):
        # --- select the source pair and transfer the input ------------------
        learning_pair = learning_set[j % L]
        u_source = np.asarray(learning_pair.input, dtype=float)
        y_source = np.asarray(learning_pair.output, dtype=float)

        u_target = vector_to_lifted_matrix(transfer_vector) @ u_source
        y_target = np.asarray(target_dynamics(u_target), dtype=float)

        # --- inner loop: refine the target-model estimate (IML step) --------
        # Prediction under the previous estimate, Eq.~model_free_prediction.
        model_prediction = vector_to_lifted_matrix(u_target) @ model_vector
        # Model output error, Eq.~model_output_error.
        model_output_error = y_target - model_prediction

        if adaptive_s_m:
            s_m = iml_get_learning_gain(u_target, kappa)
        if s_m is None:
            raise ValueError("Inner regularisation s_m cannot be None")

        # Model learning matrix K_j and IML update,
        # Eq.~model_learning_matrix / Eq.~model_update. With r = 0 the
        # norm-optimal IML filter Q_iml is the identity, so without a custom
        # Q_m the update is the plain f_j = f_{j-1} + K_j e_{f,j}; a supplied
        # Q_m filters the model estimate instead.
        K_j, Q_iml = iml_get_norm_optimal_matrices(u_target, s=s_m, r=0.0)
        Q_inner = Q_iml if Q_m is None else Q_m
        model_vector_update = iml_update(model_vector, model_output_error,
                                         K_j, Q_inner)

        # --- outer loop: update the transfer vector -------------------------
        learning_error = y_source - y_target

        if adaptive_s:
            s = iitl_get_learning_gain(model_vector_update, u_source, kappa)
        if s is None:
            raise ValueError("Outer regularisation s cannot be None")

        # Model-based transfer learning matrix L_hat_j, built from the updated
        # model estimate in place of the unknown target dynamics,
        # Eq.~model_free_transfer_learning_matrix.
        L_hat_j = iitl_get_scalar_learning_matrix(
            vector_to_lifted_matrix(model_vector_update), u_source, s)
        transfer_vector_update = iitl_update(transfer_vector, L_hat_j,
                                             learning_error, Q)

        if f_target is not None:
            model_estimation_error_norm = float(
                np.linalg.norm(np.asarray(f_target) - model_vector_update))
        else:
            model_estimation_error_norm = float("nan")

        trials.append(ModelFreeIITL_Trial_Data(
            u_source=u_source,
            y_source=y_source,
            u_target=u_target,
            y_target=y_target,
            learning_error=learning_error,
            learning_error_norm=float(np.linalg.norm(learning_error, ord=2)),
            s=s,
            learning_matrix=L_hat_j,
            q_filter=Q,
            transfer_vector=transfer_vector,
            transfer_vector_update=transfer_vector_update,
            model_vector=model_vector,
            model_vector_update=model_vector_update,
            model_prediction=model_prediction,
            model_output_error=model_output_error,
            model_output_error_norm=float(
                np.linalg.norm(model_output_error, ord=2)),
            model_learning_matrix=K_j,
            model_q_filter=Q_m,
            model_estimation_error_norm=model_estimation_error_norm,
            s_m=s_m,
        ))

        transfer_vector = transfer_vector_update
        model_vector = model_vector_update

    return ModelFreeIITL_Results(trials=trials)


# ======================================================================================================================
def run_model_free_rls_iitl(
        target_dynamics: Callable,
        learning_set: list[TrajectoryPair],
        J: int,
        s: float,
        N: int | None = None,
        t_1: np.ndarray | None = None,
        f_0: np.ndarray | None = None,
        s_m: float | None = None,
        adaptive_s_m: bool = False,
        kappa: float = 100.0,
        design: RLSDesign | str = RLSDesign.PLAIN,
        eps: float | None = None,
        delta: float = 1e-4,
        Q: np.ndarray | None = None,
        Q_m: np.ndarray | None = None,
        f_target: np.ndarray | None = None,
) -> ModelFreeIITL_Results:
    """Model-free IITL with an accumulated-information (RLS) outer loop.

    Combines the inner model-learning loop of :func:`run_model_free_iitl`
    (the target Markov vector is estimated on the fly) with the outer
    regressor-Gramian designs of :func:`run_rls_iitl` (plain RLS,
    exploration-biased, or hybrid). The outer transfer update therefore pools
    information across trials, which makes it markedly more noise-robust than
    the per-trial scalar-weight design of :func:`run_model_free_iitl`.

    The outer regressor is built from the *current model estimate*,
    :math:`\\mathbf{P}_j = \\mathcal{M}(\\hat{\\mathbf{f}}_j^{(\\beta)})\\,
    \\mathcal{M}(\\mathbf{u}_j^{(\\alpha)})`, so the cumulative Gramian
    :math:`\\mathbf{G}_j` accumulates regressors that improve as the inner
    loop converges. Early-trial contributions are based on a coarse model and
    are diluted as later, more accurate regressors are added.

    Parameters
    ----------
    target_dynamics : Callable
        Target agent: maps a target input to a target output trajectory.
    learning_set : list[TrajectoryPair]
        Source input/output pairs.
    J : int
        Number of trials.
    s : float
        Outer RLS regularisation, :math:`s > 0`. Mandatory -- the
        spectrum-aware designs adapt their per-direction gain themselves, so
        no adaptive-:math:`s` is provided (cf. :func:`run_rls_iitl`).
    N : int, optional
        Trajectory length; defaults to ``len(learning_set[0].input)``.
    t_1 : ndarray, optional
        Initial transfer-vector estimate; defaults to the unity transfer.
    f_0 : ndarray, optional
        Initial target-model estimate; defaults to the zero vector. A coarse
        plant-class prior is recommended (see :func:`run_model_free_iitl`).
    s_m : float, optional
        Inner (model) regularisation. Ignored when ``adaptive_s_m`` is set.
    adaptive_s_m : bool, optional
        Recompute the inner regularisation per trial from the current
        regressor (condition-number heuristic with cap ``kappa``).
    kappa : float, optional
        Condition-number cap for the adaptive inner regularisation.
    design : RLSDesign or str, optional
        Outer learning-matrix design; see :class:`RLSDesign`. Defaults to
        plain RLS.
    eps, delta : float, optional
        Knee and floor parameters of the exploration-shaped designs; ignored
        for plain RLS.
    Q : ndarray, optional
        Optional outer q-filter on the transfer-vector update.
    Q_m : ndarray, optional
        Optional inner q-filter on the model-vector update. ``None`` leaves
        the norm-optimal IML filter (the identity at ``r = 0``) in place.
    f_target : ndarray, optional
        True target Markov vector, used only for logging the model estimation
        error per trial; never enters the update.

    Returns
    -------
    ModelFreeIITL_Results
        Per-trial records; ``learning_matrix`` holds the RLS matrix
        :math:`\\hat{\\mathbf{L}}_j`.
    """
    try:
        design = RLSDesign(design)
    except ValueError as exc:
        raise ValueError(
            f"Unknown RLS design {design!r}; valid options: "
            f"{[d.value for d in RLSDesign]}") from exc
    if s is None:
        raise ValueError("Regularisation s is required for run_model_free_rls_iitl")

    L = len(learning_set)
    if N is None:
        N = len(learning_set[0].input)

    if t_1 is None:
        t_1 = np.zeros((N,))
        t_1[0] = 1.0
    if f_0 is None:
        f_0 = np.zeros((N,))

    transfer_vector = np.asarray(t_1, dtype=float)
    model_vector = np.asarray(f_0, dtype=float)
    G = np.zeros((N, N))

    trials: list[ModelFreeIITL_Trial_Data] = []

    for j in range(0, J):
        # --- select the source pair and transfer the input ------------------
        learning_pair = learning_set[j % L]
        u_source = np.asarray(learning_pair.input, dtype=float)
        y_source = np.asarray(learning_pair.output, dtype=float)

        u_target = vector_to_lifted_matrix(transfer_vector) @ u_source
        y_target = np.asarray(target_dynamics(u_target), dtype=float)

        # --- inner loop: refine the target-model estimate (IML step) --------
        model_prediction = vector_to_lifted_matrix(u_target) @ model_vector
        model_output_error = y_target - model_prediction

        if adaptive_s_m:
            s_m = iml_get_learning_gain(u_target, kappa)
        if s_m is None:
            raise ValueError("Inner regularisation s_m cannot be None")

        K_j, Q_iml = iml_get_norm_optimal_matrices(u_target, s=s_m, r=0.0)
        Q_inner = Q_iml if Q_m is None else Q_m
        model_vector_update = iml_update(model_vector, model_output_error,
                                         K_j, Q_inner)

        # --- outer loop: RLS transfer-vector update -------------------------
        learning_error = y_source - y_target

        # Model-based regressor from the updated estimate, and cumulative
        # Gramian update.
        P_j = (vector_to_lifted_matrix(model_vector_update)
               @ vector_to_lifted_matrix(u_source))
        G = iitl_update_rls_gramian(G, P_j)

        if design is RLSDesign.PLAIN:
            L_hat_j = iitl_get_rls_learning_matrix(G, P_j, s)
        elif design is RLSDesign.EXPLORATION_BIASED:
            L_hat_j = iitl_get_exploration_biased_learning_matrix(
                P_j, G, s, eps=eps, delta=delta)
        else:  # RLSDesign.HYBRID
            L_hat_j = iitl_get_hybrid_rls_exploration_learning_matrix(
                P_j, G, s, eps=eps, delta=delta)

        transfer_vector_update = iitl_update(transfer_vector, L_hat_j,
                                             learning_error, Q)

        if f_target is not None:
            model_estimation_error_norm = float(
                np.linalg.norm(np.asarray(f_target) - model_vector_update))
        else:
            model_estimation_error_norm = float("nan")

        trials.append(ModelFreeIITL_Trial_Data(
            u_source=u_source,
            y_source=y_source,
            u_target=u_target,
            y_target=y_target,
            learning_error=learning_error,
            learning_error_norm=float(np.linalg.norm(learning_error, ord=2)),
            s=s,
            learning_matrix=L_hat_j,
            q_filter=Q,
            transfer_vector=transfer_vector,
            transfer_vector_update=transfer_vector_update,
            model_vector=model_vector,
            model_vector_update=model_vector_update,
            model_prediction=model_prediction,
            model_output_error=model_output_error,
            model_output_error_norm=float(
                np.linalg.norm(model_output_error, ord=2)),
            model_learning_matrix=K_j,
            model_q_filter=Q_m,
            model_estimation_error_norm=model_estimation_error_norm,
            s_m=s_m,
        ))

        transfer_vector = transfer_vector_update
        model_vector = model_vector_update

    return ModelFreeIITL_Results(trials=trials)
