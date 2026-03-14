import numpy as np
import scipy


def vec2liftedMatrix(vec: np.ndarray) -> np.ndarray:
    n = len(vec)
    M = np.zeros((n, n), dtype=vec.dtype)
    for i in range(n):
        M[i:, i] = vec[:n - i]  # shift vec into column i
    return M


def is_lttm(M: np.ndarray, rtol: float = 1e-5, atol: float = 1e-8) -> bool:
    """
    Check if M is approximately a lower-triangular Toeplitz matrix (LTTM).
    """
    M = np.asarray(M)
    if M.ndim != 2 or M.shape[0] != M.shape[1]:
        return False
    n = M.shape[0]
    c = M[:, 0]
    # Build the expected LTTM from the first column
    expected = np.zeros_like(M)
    for i in range(n):
        expected[i:, i] = c[:n - i]
    return np.allclose(M, expected, rtol=rtol, atol=atol)


def liftedMatrix2Vec(M: np.ndarray, rtol: float = 1e-5, atol: float = 1e-8) -> np.ndarray:
    """
    If M is approximately a lower-triangular Toeplitz matrix, return its first column.
    Otherwise raise a ValueError.
    """
    M = np.asarray(M)
    if M.ndim != 2 or M.shape[0] != M.shape[1]:
        raise ValueError("Input must be a square matrix.")
    n = M.shape[0]
    c = M[:, 0]
    # Build the expected LTTM from the first column and compare
    expected = np.zeros_like(M)
    for i in range(n):
        expected[i:, i] = c[:n - i]
    if not np.allclose(M, expected, rtol=rtol, atol=atol):
        max_abs = float(np.max(np.abs(M - expected)))
        raise ValueError(
            f"Not approximately a lower-triangular Toeplitz matrix: "
            f"max abs deviation {max_abs:.3e} exceeds tolerances "
            f"(rtol={rtol}, atol={atol})."
        )
    return c


if __name__ == '__main__':
    vec = np.array([1, 2, 3, 4, 5, 6])
    M = vec2liftedMatrix(vec)
    print(M)
    vec2 = liftedMatrix2Vec(M)
    print(vec2)
