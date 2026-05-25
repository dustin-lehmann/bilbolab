import numpy as np
import scipy.signal as sig


# ======================================================================================================================
def second_order_ss(wn: float, zeta: float, dt: float) -> sig.StateSpace:
    r"""Discrete-time state-space model of a unit-gain 2nd-order low-pass
    plant,

    .. math::
        G(s) = \frac{\omega_n^2}{s^2 + 2\zeta\omega_n s + \omega_n^2},

    zero-order-hold sampled with period ``dt``.

    Parameters
    ----------
    wn : float
        Undamped natural frequency in rad/s.
    zeta : float
        Damping ratio. Underdamped for 0 < zeta < 1, critically damped at
        zeta = 1, overdamped for zeta > 1.
    dt : float
        Sample period in seconds.

    Returns
    -------
    scipy.signal.StateSpace
        Discrete-time state-space realisation with ``dt`` set.
    """
    num = [wn ** 2]
    den = [1.0, 2.0 * zeta * wn, wn ** 2]
    sys_c = sig.TransferFunction(num, den).to_ss()
    Ad, Bd, Cd, Dd, _ = sig.cont2discrete(
        (sys_c.A, sys_c.B, sys_c.C, sys_c.D), dt=dt, method="zoh"
    )
    return sig.StateSpace(Ad, Bd, Cd, Dd, dt=dt)


# ======================================================================================================================
def simulate_lti(ss: sig.StateSpace, u: np.ndarray, m: int = 1) -> np.ndarray:
    r"""Zero-state simulation of ``ss`` on input ``u`` under the
    relative-degree-absorbed lifting convention. Returns the shifted output

    .. math::
        \mathbf{y} = [y_m,\, y_{m+1},\, \ldots,\, y_{N+m-1}]^\top
                   \in \mathbb{R}^N,
        \quad y_k = C x_k + D u_k, \quad x_0 = 0,

    so that ``y == P @ u`` for the lifted transition matrix ``P``
    associated with ``ss`` at relative degree ``m``. For ``m = 1`` (strictly
    proper with :math:`CB \neq 0`) this reduces to ``y_k = C x_{k+1}``,
    matching the BILBO record-after-step convention.

    Parameters
    ----------
    ss : scipy.signal.StateSpace
        Discrete-time state-space system.
    u : numpy.ndarray
        Length-N real input sequence.
    m : int, default 1
        Relative degree absorbed into the lifted matrix. The simulation
        runs N + m steps and returns samples ``[m, N + m)``; choose ``m``
        so that the leading m samples of the natural output (which are
        zero / feed-through artefacts) are discarded.

    Returns
    -------
    numpy.ndarray
        Length-N output trajectory.
    """
    A, B, C, D = ss.A, ss.B, ss.C, ss.D
    D_scalar = float(np.asarray(D).reshape(-1)[0]) if np.asarray(D).size else 0.0
    N = len(u)
    nx = A.shape[0]
    x = np.zeros((nx, 1))
    y_full = np.empty(N + m)
    u_ext = np.concatenate([u, np.zeros(m)])
    for k in range(N + m):
        y_full[k] = (C @ x)[0, 0] + D_scalar * u_ext[k]
        x = A @ x + B * u_ext[k]
    return y_full[m:m + N]
