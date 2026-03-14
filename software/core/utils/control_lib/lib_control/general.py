import numpy as np
from control import *
import scipy


def sign(x):
    return x and (1, -1)[x < 0]


class PID_ctrl:
    def __init__(self, Ts, P=0, I=0, D=0, max_rate=None, max=None):
        self.Kp = P
        self.Ki = I
        self.Kd = D
        self.Ts = Ts

        self.last_error = 0
        self.integral = 0

        self.max_rate = max_rate
        self.max = max

    def reset(self):
        self.integral = 0
        self.last_error = 0

    def update(self, e):
        if self.Kp == 0 and self.Ki == 0 and self.Kd == 0:
            return 0

        if self.max_rate is not None:
            if abs(e) > self.max_rate * self.Ts:
                e = self.max_rate * self.Ts * sign(e)

        out = self.Kp * e + self.Ki * self.integral + self.Kd * 1 / self.Ts * (e - self.last_error)

        if abs(self.Ki) > 0:
            self.integral += self.Ts * e
        if abs(self.Kd) > 0:
            self.last_error = e
        return out


class PID2_ctrl:
    def __init__(self, Ts, P=0, I=0, D=0, b=0, c=0, max_rate=None, max=None):
        self.Kp = P
        self.Ki = I
        self.Kd = D
        self.b = b
        self.c = c
        self.Ts = Ts

        self.last_error = 0
        self.integral = 0

        self.max_rate = max_rate
        self.max = max

    def reset(self):
        self.integral = 0
        self.last_error = 0

    def update(self, r, y):
        if self.Kp == 0 and self.Ki == 0 and self.Kd == 0:
            return 0

        # if self.max_rate is not None:
        #     if abs(e) > self.max_rate * self.Ts:
        #         e = self.max_rate * self.Ts * sign(e)

        out = self.Kp * (self.b * r - y) + self.Ki * self.integral + self.Kd * 1 / self.Ts * (
                    self.c * r - y - self.last_error)

        if abs(self.Ki) > 0:
            self.integral += self.Ts * (r - y)
        if abs(self.Kd) > 0:
            self.last_error = (self.c * r - y)

        if self.max is not None:
            if abs(out) > self.max:
                out = sign(out) * self.max
        return out


def eigenstructure_assignment(A, B, poles, eigenvectors):
    N = A.shape[0]
    M = B.shape[1]

    reduced_ev = [None] * N
    D = [None] * N

    for i in range(0, N):
        reduced_ev[i] = eigenvectors[~np.isnan(eigenvectors[:, i]), i]
        reduced_ev[i] = np.atleast_2d(reduced_ev[i]).T
        D_i = np.zeros((M, N))
        V_temp = ~np.isnan(eigenvectors[:, i])
        indexes = np.argwhere(V_temp == 1)

        for j in range(0, M):
            D_i[j, indexes[j]] = 1
        D[i] = D_i

    b = [None] * N
    x = [None] * N
    r = [None] * N

    for i in range(0, N):
        mat_temp = np.vstack((np.hstack((A - poles[i] * np.eye(N), B)), np.hstack((D[i], np.zeros((M, M))))))
        vec_temp = np.vstack((np.zeros((N, 1)), reduced_ev[i]))
        b[i] = np.linalg.inv(mat_temp) @ vec_temp
        x[i] = b[i][0:N]
        r[i] = -b[i][N:N + M]

    X = np.zeros((N, N), dtype=complex)
    R = np.zeros((M, N), dtype=complex)
    for i in range(0, N):
        X[:, i] = x[i][:, 0]
        R[:, i] = r[i][:, 0]

    K = np.real(R @ np.linalg.inv(X))
    if np.isnan(np.sum(K)):
        raise Exception("Eigenstructure assignment not possible!")
    return K


def dlqr(A, B, Q, R):
    # first, try to solve the ricatti equation
    X = np.matrix(scipy.linalg.solve_discrete_are(A, B, Q, R))

    # compute the LQR gain
    K = np.matrix(scipy.linalg.inv(B.T * X * B + R) * (B.T * X * A))

    eigVals, eigVecs = scipy.linalg.eig(A - B * K)

    K = np.asarray(K)
    return K, X, eigVals


def random_experiment(p):
    random_number = np.random.random_sample()
    if random_number <= p:
        return True
    else:
        return False


def tf2lifted(sys, N, m):
    dt = sys.dt
    t = np.arange(start=0, stop=(N + m) * dt, step=dt)
    _, imp_response = impulse_response(sys, T=t)
    tm = scipy.linalg.toeplitz(imp_response[m:])
    lfm = scipy.linalg.tril(tm)

    return lfm
