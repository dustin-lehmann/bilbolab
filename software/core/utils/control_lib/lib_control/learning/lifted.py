import numpy as np


# ======================================================================================================================
def vector_to_lifted_matrix(vec: np.ndarray) -> np.ndarray:
    n = len(vec)
    M = np.zeros((n, n), dtype=vec.dtype)
    for i in range(n):
        M[i:, i] = vec[:n - i]  # shift vec into column i
    return M


# ======================================================================================================================
def lifted_matrix_to_vector(matrix: np.ndarray, rtol: float = 1e-5, atol: float = 1e-8) -> np.ndarray:
    assert (is_lttm(matrix, rtol=rtol, atol=atol))
    return matrix[:, 0]


# ======================================================================================================================
def is_lttm(matrix: np.ndarray, rtol: float = 1e-5, atol: float = 1e-8) -> bool:
    """
    Check if M is approximately a lower-triangular Toeplitz matrix (LTTM).
    """
    M = np.asarray(matrix)
    if M.ndim != 2 or M.shape[0] != M.shape[1]:
        return False
    n = M.shape[0]
    c = M[:, 0]
    # Build the expected LTTM from the first column
    expected = np.zeros_like(M)
    for i in range(n):
        expected[i:, i] = c[:n - i]
    return np.allclose(M, expected, rtol=rtol, atol=atol)


# ======================================================================================================================
def _scalar_D(sys) -> float:
    """Extract the scalar direct-feedthrough term of a SISO system.

    Returns 0.0 if ``sys`` has no ``D`` attribute or ``D`` is None. Raises
    ``ValueError`` for non-scalar (MIMO) ``D``.
    """
    D = getattr(sys, "D", None)
    if D is None:
        return 0.0
    D_arr = np.asarray(D).reshape(-1)
    if D_arr.size == 0:
        return 0.0
    if D_arr.size == 1:
        return float(D_arr[0])
    raise ValueError(
        f"Non-scalar D not supported (got shape {np.asarray(D).shape}; expected SISO)."
    )


# ======================================================================================================================
def relative_degree(sys) -> int:
    r"""Relative degree of a discrete-time SISO state-space system.

    Defined as the smallest non-negative integer :math:`m` such that the
    Markov parameter :math:`h_m \neq 0`, where

    .. math:: h_0 = D, \qquad h_k = C\,A^{k-1}\,B \quad (k \ge 1).

    Returns ``0`` for biproper systems (``D != 0``) and ``k`` for strictly
    proper systems whose first non-zero Markov parameter is :math:`C A^{k-1} B`.

    Raises ``ValueError`` if no non-zero Markov parameter is found within
    ``A.shape[0] + 1`` lags (system has no reachable output).
    """
    D = _scalar_D(sys)
    if D != 0.0:
        return 0
    A = np.asarray(sys.A)
    B = np.asarray(sys.B)
    C = np.asarray(sys.C)
    n = A.shape[0]
    AkB = B
    for m in range(1, n + 2):
        val = float(np.asarray(C @ AkB).reshape(-1)[0])
        if val != 0.0:
            return m
        AkB = A @ AkB
    raise ValueError(
        f"relative_degree: no non-zero Markov parameter within {n + 1} lags."
    )


# ======================================================================================================================
def get_transition_matrix_from_system(sys, N):
    r"""Lifted transition matrix :math:`\mathbf{P}` and relative degree
    :math:`m` of a discrete-time SISO state-space system, under the
    *relative-degree-absorbed* output-shift convention.

    The output trajectory is indexed from :math:`m`, so that

    .. math::
        \mathbf{y} = [y_m,\, y_{m+1},\, \ldots,\, y_{N+m-1}]^\top,
        \qquad \mathbf{u} = [u_0,\, u_1,\, \ldots,\, u_{N-1}]^\top,

    and the lifted matrix is the lower-triangular Toeplitz matrix

    .. math::
        \mathbf{P}[i, j] = \begin{cases}
            h_{m + i - j}  & j \le i, \\
            0              & j > i,
        \end{cases}

    with Markov parameters :math:`h_0 = D`,
    :math:`h_k = C\,A^{k-1}\,B` for :math:`k \ge 1`. By construction of the
    relative degree, :math:`\mathbf{P}[i, i] = h_m \neq 0`, so
    :math:`\mathbf{P}` is invertible.

    For strictly proper systems with :math:`CB \neq 0` (``m = 1``, e.g.\ all
    BILBO dynamics), this reduces to :math:`\mathbf{P}[i, j] = C A^{i-j} B`
    on and below the diagonal, matching the previous convention.

    Parameters
    ----------
    sys : discrete-time state-space system with attributes ``A, B, C, D, dt``.
    N   : horizon length.

    Returns
    -------
    (P, m) : tuple of (ndarray of shape (N, N), int)
        The lifted transition matrix and the relative degree used for the
        index shift.
    """
    if sys.dt is None:
        raise Exception("System has to be discrete time!")

    m = relative_degree(sys)
    A = np.asarray(sys.A)
    B = np.asarray(sys.B)
    C = np.asarray(sys.C)

    # Markov parameters h_0, ..., h_{N+m-1}, with h_0 = D and
    # h_k = C A^{k-1} B for k >= 1. Built incrementally to avoid
    # recomputing matrix powers.
    h = np.zeros(N + m)
    h[0] = _scalar_D(sys)
    AkB = B
    for k in range(1, N + m):
        h[k] = float(np.asarray(C @ AkB).reshape(-1)[0])
        AkB = A @ AkB

    P = np.zeros((N, N))
    for i in range(N):
        for j in range(i + 1):
            P[i, j] = h[m + i - j]

    return P, m
