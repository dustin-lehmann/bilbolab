import numpy as np
import warnings
import scipy.linalg as la


def calc_transition_matrix(sys, N):
    if sys.dt is None:
        raise Exception("System has to be discrete time!")

    m = relative_degree(sys)
    P = np.zeros((N, N))

    diag, P2 = np.linalg.eig(sys.A)
    P3 = np.linalg.inv(P2)

    for i in range(0, N):
        for j in range(0, N):
            markov_m = m + i - j
            if markov_m < m:
                P[i, j] = 0
            else:
                P[i, j] = sys.C@np.linalg.matrix_power(sys.A, (markov_m-1))@sys.B
                # DN = np.diag(diag ** (markov_m - 1))
                # P[i, j] = np.real(sys.C @ P2 @ DN @ P3 @ sys.B)
    return P


def ilc_update(Q, L, u, e, *args, **kwargs):
    u = Q @ u.T + L @ e.T
    return u


def ilc_is_stable():
    return 0


def ilc_is_mc():
    return 0


def relative_degree(sys):
    # warnings.warn("Relative degree not implemented yet!")
    return 1


def qlearning(P: np.ndarray, Qw, Rw, Sw):
    if isinstance(Qw, (int, float)):
        Qw = Qw * np.eye(P.shape[0])
    if isinstance(Rw, (int, float)):
        Rw = Rw * np.eye(P.shape[0])
    if isinstance(Sw, (int, float)):
        Sw = Sw * np.eye(P.shape[0])

    Q = np.linalg.inv(P.T @ Qw @ P + Rw + Sw) @ (P.T @ Qw @ P + Sw)
    L = np.linalg.inv(P.T @ Qw @ P + Sw) @ P.T @ Qw
    return Q, L


def pdlearning(kp, kd, N):
    L = np.zeros((N, N))
    L[0][0] = kp

    idx = 0
    for j in range(1, N):
        L[j][idx] = -kd
        L[j][idx + 1] = kp + kd
        idx = idx + 1
    return L


def qfilter():
    return 0
