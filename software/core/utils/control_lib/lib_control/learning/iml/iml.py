import numpy as np

from core.utils.control_lib.lib_control.learning.lifted import vector_to_lifted_matrix


# ======================================================================================================================
def iml_update(m: np.ndarray, error: np.ndarray, L: np.ndarray, Q: np.ndarray | None = None ) -> np.ndarray:

    if Q is None:
        Q = np.eye(len(m))

    Q = np.asarray(Q)
    L = np.asarray(L)
    m = np.asarray(m)
    error = np.asarray(error)

    N = len(m)

    assert Q.shape == (N, N), f"Q must be {N}x{N}, got {Q.shape}"  # type: ignore
    assert L.shape == (N, N), f"L must be {N}x{N}, got {L.shape}"
    assert len(error) == N, f"e must have length {N}, got {len(error)}"

    u = Q @ (m + L @ error)  # type: ignore
    return u


# ======================================================================================================================
def iml_get_learning_gain(u: np.ndarray, kappa: float = 100.0) -> float:
    """
    Tikhonov regularization parameter ``s`` for the inner model-learning
    least-squares solve

        L = (U^T U + s I)^{-1} U^T,

    chosen so that the per-direction gain sigma_i / (sigma_i^2 + s) faithfully
    inverts singular directions with sigma_i >> sigma_max / kappa and damps the
    rest. The threshold sits at sqrt(s) = sigma_max / kappa, so kappa is the
    effective condition-number cap of the regularized inverse.

    Effect of kappa:
      - Large kappa (e.g. 1000): cutoff sqrt(s) is small, more singular
        directions are inverted faithfully. Faster nominal convergence but
        stronger amplification of noise and model mismatch in weakly excited
        directions.
      - Small kappa (e.g. 10): cutoff sqrt(s) is large, only the dominant
        directions are inverted; the rest are heavily damped. Slower but more
        robust learning, with smaller updates in poorly excited directions.
      - kappa -> inf reproduces the unregularized pseudo-inverse;
        kappa -> 0 disables learning entirely.

    The choice s = (sigma_max / kappa)^2 is scale-invariant: rescaling u by a
    constant leaves the resulting learning matrix unchanged up to the expected
    inverse factor.
    """
    U = vector_to_lifted_matrix(u)
    sigma_max = np.linalg.norm(U, 2)
    s = (sigma_max / kappa) ** 2
    return float(s)


# ======================================================================================================================
def iml_get_norm_optimal_matrices(u: np.ndarray, s: float | None = None, r: float = 0.0, kappa: float = 100.0):
    if s is None:
        s: float = iml_get_learning_gain(u, kappa)

    U = vector_to_lifted_matrix(u)
    Qw = np.eye(U.shape[0])
    Rw = r * np.eye(U.shape[0])
    Sw = s * np.eye(U.shape[0])

    Q = np.linalg.inv(U.T @ Qw @ U + Rw + Sw) @ (U.T @ Qw @ U + Sw)
    L = np.linalg.inv(U.T @ Qw @ U + Sw) @ U.T @ Qw

    return L, Q
