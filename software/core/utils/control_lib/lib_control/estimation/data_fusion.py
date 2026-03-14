import numpy as np


def covariance_intersection(mean1: np.ndarray,
                            covariance1: np.ndarray,
                            mean2: np.ndarray,
                            covariance2: np.ndarray,
                            omega: float| None = None,
                            cost: str = 'trace') -> tuple[np.ndarray, np.ndarray]:

    if cost != 'trace':
        raise ValueError('Only trace cost is supported.')

    covariance1 = 0.5 * (covariance1 + covariance1.T)
    covariance2 = 0.5 * (covariance2 + covariance2.T)

    lambda1 = np.linalg.inv(covariance1)
    lambda2 = np.linalg.inv(covariance2)
    eta1 = lambda1 @ mean1
    eta2 = lambda2 @ mean2

    if omega is None:
        best_w, best_tr = 0.0, np.inf
        for w in np.linspace(0.0, 1.0, 51):
            lam = w * lambda1 + (1.0 - w) * lambda2
            try:
                P = np.linalg.inv(lam)
            except np.linalg.LinAlgError:
                continue
            tr = np.trace(P)
            if tr < best_tr:
                best_tr, best_w = tr, w
        omega = best_w

    Lambda = omega * lambda1 + (1.0 - omega) * lambda2
    covariance = np.linalg.inv(Lambda)
    eta = omega * eta1 + (1.0 - omega) * eta2
    mean = covariance @ eta
    return mean, covariance


def ekf_update():
    ...