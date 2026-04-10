import numpy as np

from core.utils.control_lib.lib_control.lifted_systems import vec2liftedMatrix


def imlUpdateOptimal(uj: np.ndarray, yj: np.ndarray, mj: np.ndarray) -> np.ndarray:
    ej = yj - vec2liftedMatrix(mj) @ uj
    Lj = getOptimalLearningMatrix(uj)

    mj_1 = mj + Lj @ ej

    return mj_1


def getOptimalLearningMatrixFromMatrix(U: np.ndarray):
    N = U.shape[0]
    Q = np.eye(N)
    sigma_max = np.linalg.norm(U, 2)
    # S = (sigma_max ** 2) * np.eye(N)
    S = (sigma_max / 100) * np.eye(N)
    A = U.T @ (Q @ U) + S
    B = U.T @ Q
    L = np.linalg.solve(A, B)
    return L


def getOptimalLearningMatrix(u: np.ndarray):
    u = np.asarray(u)

    U = vec2liftedMatrix(u)
    return getOptimalLearningMatrixFromMatrix(U)
