import dataclasses
from typing import Callable

import numpy as np

from core.utils.deprecation import deprecated


@dataclasses.dataclass
class ILC_TrialData:
    u: np.ndarray
    y: np.ndarray
    e: np.ndarray
    e_norm: float
    L: np.ndarray
    Q: np.ndarray


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
