import numpy as np
import matplotlib.pyplot as plt
import scipy.signal as sig
from scipy.linalg import circulant

from core.utils.control_lib.lib_control.learning.lifted import vector_to_lifted_matrix


# ======================================================================================================================
def _butterworth_ir(N: int, cutoff: tuple, order: int, btype: str
                    ) -> np.ndarray:
    """Length-N causal impulse response of a digital Butterworth filter
    with the given band type and cutoff(s). Internal helper.
    """
    b, a = sig.butter(order, cutoff, btype=btype, output="ba")  # type: ignore
    delta = np.zeros(N)
    delta[0] = 1.0
    return sig.lfilter(b, a, delta)


def causal_lowpass(N: int, cutoff_cps: float,
                   order: int = 4) -> np.ndarray:
    """N x N lower-triangular Toeplitz Q implementing a causal Butterworth
    low-pass in the trial domain: Q @ u performs strict linear convolution
    of u with the Butterworth impulse response, with no future-sample
    access.

    Use when convergence proofs require Q F = F Q with F also lower-
    triangular Toeplitz (the standard IITL / ILC commutativity assumption),
    which the zero-phase circulant variants lose.

    Parameters
    ----------
    N : int
        Horizon length.
    cutoff_cps : float
        -3 dB cut-off in cycles per sample, 0 < cutoff_cps < 0.5.
    order : int, default 4
        Butterworth order. Each order adds 20 dB/decade of stop-band
        roll-off.

    Returns
    -------
    numpy.ndarray
        Lower-triangular Toeplitz matrix of shape (N, N).
    """
    if not (0.0 < cutoff_cps < 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5); got {cutoff_cps}")
    h = _butterworth_ir(N, 2.0 * cutoff_cps, order, "low") # type: ignore
    return vector_to_lifted_matrix(h)


# ======================================================================================================================
def causal_highpass(N: int, cutoff_cps: float,
                    order: int = 4) -> np.ndarray:
    """N x N lower-triangular Toeplitz Q implementing a causal Butterworth
    high-pass in the trial domain.

    Parameters
    ----------
    N : int
        Horizon length.
    cutoff_cps : float
        -3 dB cut-off in cycles per sample, 0 < cutoff_cps < 0.5.
    order : int, default 4
        Butterworth order.

    Returns
    -------
    numpy.ndarray
        Lower-triangular Toeplitz matrix of shape (N, N).
    """
    if not (0.0 < cutoff_cps < 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5); got {cutoff_cps}")
    h = _butterworth_ir(N, 2.0 * cutoff_cps, order, "high") # type: ignore
    return vector_to_lifted_matrix(h)


# ======================================================================================================================
def causal_bandpass(N: int, low_cps: float, high_cps: float,
                    order: int = 4) -> np.ndarray:
    """N x N lower-triangular Toeplitz Q implementing a causal Butterworth
    band-pass in the trial domain.

    Parameters
    ----------
    N : int
        Horizon length.
    low_cps : float
        Lower -3 dB edge in cycles per sample, 0 < low_cps < high_cps.
    high_cps : float
        Upper -3 dB edge in cycles per sample, low_cps < high_cps < 0.5.
    order : int, default 4
        Butterworth order applied to each edge of the band.

    Returns
    -------
    numpy.ndarray
        Lower-triangular Toeplitz matrix of shape (N, N).
    """
    if not (0.0 < low_cps < high_cps < 0.5):
        raise ValueError(
            f"require 0 < low_cps < high_cps < 0.5; "
            f"got low_cps={low_cps}, high_cps={high_cps}")
    h = _butterworth_ir(N, (2.0 * low_cps, 2.0 * high_cps), order, "bandpass")
    return vector_to_lifted_matrix(h)


# ======================================================================================================================
def _brickwall_from_mask(N: int, mask: np.ndarray, amplitude: float,
                         delay: float) -> np.ndarray:
    """Internal helper: build a length-N real impulse response whose DFT is
    amplitude on the bins selected by mask and zero elsewhere, with a linear-
    phase delay shifting the time-domain peak to sample index delay.
    """
    M = N // 2 + 1
    k = np.arange(M)
    phase = np.exp(-1j * 2.0 * np.pi * k * delay / N)
    H = np.where(mask, amplitude * phase, 0.0 + 0.0j)
    H[0] = H[0].real
    if N % 2 == 0:
        H[-1] = H[-1].real
    return np.fft.irfft(H, n=N)


# ======================================================================================================================
def brickwall_lowpass(N: int, cutoff_cps: float,
                      amplitude: float = 1.0) -> np.ndarray:
    """N x N circulant matrix Q implementing an ideal brick-wall low-pass
    filter in the trial domain: Q @ u performs circular convolution of u
    with the brick-wall sinc, exactly reproducing the DFT-domain operation
    where bins with |f| <= cutoff_cps are kept (multiplied by amplitude)
    and the rest are zeroed.

    Use this when the full trial vector is known and causality is not
    required (typical IITL / trial-domain Q-filter setting). For a causal
    lower-triangular form, use lowpass_vector (Butterworth) and build an
    LTTM via vector_to_lifted_matrix.

    Parameters
    ----------
    N : int
        Horizon length.
    cutoff_cps : float
        Pass-band edge in cycles per sample, 0 < cutoff_cps <= 0.5. The
        effective cutoff is rounded down to the nearest DFT bin k/N.
    amplitude : float, default 1.0
        Pass-band magnitude (unity passband for amplitude = 1.0).

    Returns
    -------
    numpy.ndarray
        Circulant matrix of shape (N, N).
    """
    if not (0.0 < cutoff_cps <= 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5]; got {cutoff_cps}")
    rfreqs = np.fft.rfftfreq(N, d=1.0)
    mask = rfreqs <= cutoff_cps
    h = _brickwall_from_mask(N, mask, amplitude, delay=0.0) # type: ignore
    return circulant(h)


# ======================================================================================================================
def brickwall_highpass(N: int, cutoff_cps: float,
                       amplitude: float = 1.0) -> np.ndarray:
    """N x N circulant matrix Q implementing an ideal brick-wall high-pass
    filter in the trial domain: bins with |f| > cutoff_cps pass through
    (multiplied by amplitude), the rest are zeroed.

    Parameters
    ----------
    N : int
        Horizon length.
    cutoff_cps : float
        Stop-band edge in cycles per sample, 0 <= cutoff_cps < 0.5.
    amplitude : float, default 1.0
        Pass-band magnitude.

    Returns
    -------
    numpy.ndarray
        Circulant matrix of shape (N, N).
    """
    if not (0.0 <= cutoff_cps < 0.5):
        raise ValueError(f"cutoff_cps must be in [0, 0.5); got {cutoff_cps}")
    rfreqs = np.fft.rfftfreq(N, d=1.0)
    mask = rfreqs > cutoff_cps
    h = _brickwall_from_mask(N, mask, amplitude, delay=0.0) # type: ignore
    return circulant(h)


# ======================================================================================================================
def brickwall_bandpass(N: int, low_cps: float, high_cps: float,
                       amplitude: float = 1.0) -> np.ndarray:
    """N x N circulant matrix Q implementing an ideal brick-wall band-pass
    filter in the trial domain: bins with low_cps < |f| <= high_cps pass
    through (multiplied by amplitude), the rest are zeroed.

    Parameters
    ----------
    N : int
        Horizon length.
    low_cps : float
        Lower band edge in cycles per sample, 0 <= low_cps < high_cps.
    high_cps : float
        Upper band edge in cycles per sample, low_cps < high_cps <= 0.5.
    amplitude : float, default 1.0
        Pass-band magnitude.

    Returns
    -------
    numpy.ndarray
        Circulant matrix of shape (N, N).
    """
    if not (0.0 <= low_cps < high_cps <= 0.5):
        raise ValueError(
            f"require 0 <= low_cps < high_cps <= 0.5; "
            f"got low_cps={low_cps}, high_cps={high_cps}")
    rfreqs = np.fft.rfftfreq(N, d=1.0)
    mask = (rfreqs > low_cps) & (rfreqs <= high_cps)
    h = _brickwall_from_mask(N, mask, amplitude, delay=0.0)
    return circulant(h)


# ======================================================================================================================
def _butterworth_freq_response(N: int, cutoff_cps: float,
                               order: int) -> np.ndarray:
    """One-sided (rfft-shaped) magnitude response of a digital Butterworth
    low-pass with cutoff cutoff_cps and given order, evaluated on the DFT
    grid of length N. Real, non-negative, length N // 2 + 1.
    """
    rfreqs = np.fft.rfftfreq(N, d=1.0)
    return 1.0 / np.sqrt(1.0 + (rfreqs / cutoff_cps) ** (2 * order))


def _circulant_from_rfft_mag(N: int, mag: np.ndarray) -> np.ndarray:
    """Build a real circulant matrix whose DFT magnitudes equal mag and
    whose phases are zero (zero-phase filter). The first column is the
    inverse rfft of mag.
    """
    h = np.fft.irfft(mag.astype(complex), n=N)
    return circulant(h)


# ======================================================================================================================
def zero_phase_lowpass(N: int, cutoff_cps: float,
                       order: int = 4) -> np.ndarray:
    """N x N circulant zero-phase smooth low-pass: combines the Butterworth
    roll-off shape (no Gibbs ringing) with the trial-domain matrix interface
    (no causality, no delay). Equivalent to applying a Butterworth twice
    (forward + backward, scipy.signal.filtfilt) so the magnitude response is
    |H_butter(omega)|^2.

    Use as a smoother alternative to brickwall_lowpass when the sharp cutoff
    is undesirable, or as a non-causal alternative to the LTTM-Butterworth
    when you want zero phase distortion.

    Parameters
    ----------
    N : int
        Horizon length.
    cutoff_cps : float
        -3 dB cutoff of the underlying Butterworth in cycles per sample,
        0 < cutoff_cps < 0.5. (After squaring, the resulting -6 dB point of
        the zero-phase filter is at cutoff_cps; the -3 dB point is slightly
        below.)
    order : int, default 4
        Order of the underlying Butterworth. Each order adds 40 dB/decade
        of stop-band roll-off in the squared response.

    Returns
    -------
    numpy.ndarray
        Circulant matrix of shape (N, N).
    """
    if not (0.0 < cutoff_cps < 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5); got {cutoff_cps}")
    H = _butterworth_freq_response(N, cutoff_cps, order)
    return _circulant_from_rfft_mag(N, H ** 2)


# ======================================================================================================================
def zero_phase_highpass(N: int, cutoff_cps: float,
                        order: int = 4) -> np.ndarray:
    """N x N circulant zero-phase smooth high-pass. Magnitude response is
    1 - |H_butter_lowpass(omega)|^2, i.e. the complement of a smooth
    lowpass. See zero_phase_lowpass for the convention.
    """
    if not (0.0 < cutoff_cps < 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5); got {cutoff_cps}")
    H = _butterworth_freq_response(N, cutoff_cps, order)
    return _circulant_from_rfft_mag(N, 1.0 - H ** 2)


# ======================================================================================================================
def zero_phase_bandpass(N: int, low_cps: float, high_cps: float,
                        order: int = 4) -> np.ndarray:
    """N x N circulant zero-phase smooth band-pass: product of a smooth
    high-pass at low_cps and a smooth low-pass at high_cps, each
    Butterworth-shaped of the given order.
    """
    if not (0.0 < low_cps < high_cps < 0.5):
        raise ValueError(
            f"require 0 < low_cps < high_cps < 0.5; "
            f"got low_cps={low_cps}, high_cps={high_cps}")
    H_lo = _butterworth_freq_response(N, high_cps, order) ** 2
    H_hi = 1.0 - _butterworth_freq_response(N, low_cps, order) ** 2
    return _circulant_from_rfft_mag(N, H_lo * H_hi)


# ======================================================================================================================
def fir_lowpass(N: int, cutoff_cps: float,
                order: int = 16,
                window: str = "hann") -> np.ndarray:
    """N x N symmetric positive-semidefinite Q implementing a zero-phase
    FIR low-pass via Q = H^T H, where H is the lower-triangular Toeplitz
    convolution matrix of a windowed-sinc FIR kernel.

    Spectral gain |H(omega)|^2 in the pass-band, rolling off to zero in
    the stop-band. Unlike zero_phase_lowpass (circulant, no boundary
    effects) this Q is a banded symmetric Toeplitz whose first and last
    order rows lose taps near the boundaries — that's the cost of
    Toeplitz structure (no wrap-around) and is what keeps Q close to
    commuting with LTTM F in the IITL convergence proofs.

    Parameters
    ----------
    N : int
        Horizon length.
    cutoff_cps : float
        FIR cutoff in cycles per sample, 0 < cutoff_cps < 0.5.
    order : int, default 16
        FIR order. The kernel has order + 1 symmetric taps, so the
        effective bandwidth of Q is 2 * order samples around the
        diagonal. Larger order gives sharper transition at the price of
        a wider boundary layer.
    window : str, default "hann"
        Window passed to scipy.signal.firwin.

    Returns
    -------
    numpy.ndarray
        Symmetric positive-semidefinite matrix of shape (N, N).
    """
    if not (0.0 < cutoff_cps < 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5); got {cutoff_cps}")
    h = sig.firwin(order + 1, 2.0 * cutoff_cps, window=window)
    if len(h) > N:
        raise ValueError(
            f"FIR length {len(h)} exceeds horizon N={N}; lower the order")
    col = np.zeros(N)
    col[: len(h)] = h
    H = vector_to_lifted_matrix(col)
    return H.T @ H


# ======================================================================================================================
def fir_lowpass_zero_padded(N: int, cutoff_cps: float,
                            order: int = 16,
                            window: str = "hann") -> np.ndarray:
    """N x N symmetric banded Toeplitz Q implementing a zero-phase FIR
    low-pass via centered linear convolution with zero-padding at the
    boundaries.

    Spectral gain |H(omega)| in the pass-band — contrast fir_lowpass which
    builds Q = H^T H and therefore applies |H(omega)|^2. Use this variant
    when you need the unsquared response and accept boundary truncation
    rather than the circulant wrap of zero_phase_lowpass.

    Parameters
    ----------
    N : int
        Horizon length.
    cutoff_cps : float
        FIR cutoff in cycles per sample, 0 < cutoff_cps < 0.5.
    order : int, default 16
        FIR order. The kernel has order + 1 symmetric taps and order must
        be even so that the centered placement on diagonals
        -order/2 .. order/2 yields a linear-phase symmetric Toeplitz.
    window : str, default "hann"
        Window passed to scipy.signal.firwin.

    Returns
    -------
    numpy.ndarray
        Symmetric banded Toeplitz matrix of shape (N, N).
    """
    if not (0.0 < cutoff_cps < 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5); got {cutoff_cps}")
    if order % 2 != 0:
        raise ValueError(
            f"order must be even (so order+1 is odd); got {order}")
    L = order + 1
    if L > N:
        raise ValueError(
            f"FIR length {L} exceeds horizon N={N}; lower the order")
    h = sig.firwin(L, 2.0 * cutoff_cps, window=window)
    M = order // 2
    Q = np.zeros((N, N), dtype=float)
    for r in range(-M, M + 1):
        diag_len = N - abs(r)
        if diag_len <= 0:
            continue
        Q += np.diag(np.full(diag_len, h[M + r]), k=r)
    return 0.5 * (Q + Q.T)


# ======================================================================================================================
def signal_matched_q(signal: np.ndarray,
                     modulation: np.ndarray | None = None,
                     shape: str = "brickwall",
                     threshold: float = 0.01,
                     alpha: float = 0.01) -> np.ndarray:
    """Symmetric circulant Q-filter whose pass-band is shaped by the
    spectrum of a reference signal (data-driven, no fixed cutoff).

    The pass-band is anchored at the frequencies where the effective
    spectrum |modulation(omega) * signal(omega)| is significant. Bins where
    that product is small are zeroed (or strongly attenuated), since the
    downstream cost is insensitive to the filtered iterate at those bins.

    In the IITL deployment-error analysis the relevant density is
    |F_beta(omega)|^2 |U_d(omega)|^2 |e_t(omega)|^2, so passing
    signal = u_deploy, modulation = first column of F_beta reproduces the
    deployment-matched Q-filter rule of Sec. iitl_q_filter_design.

    Equivalent shortcut: pass the already pre-multiplied signal
    F_beta @ u_deploy as signal and leave modulation = None. The two are
    exactly equal when F_beta is circulant, since |rfft(F_beta @ u)| equals
    |rfft(F_beta[:, 0]) * rfft(u)|. For an LTTM F_beta they differ only at
    the trial boundaries (linear convolution truncation versus circular
    wrap), and for Q-filter design — which only cares about which bins to
    keep, not their exact magnitudes — the resulting mask is usually
    indistinguishable. Use the (signal, modulation) form when you want the
    two factors to remain separately inspectable; use the pre-multiplied
    form when F_beta is non-Toeplitz / non-LTI and only its actual response
    on this particular u is meaningful.

    Parameters
    ----------
    signal : numpy.ndarray
        Length-N reference signal whose spectrum drives the pass-band shape
        (e.g. the deployment input u_deploy).
    modulation : numpy.ndarray, optional
        Length-N additional weighting (e.g. the impulse response of the
        target plant F_beta). The effective spectrum is
        |fft(modulation) * fft(signal)|. If None, only |fft(signal)| is used.
    shape : {"brickwall", "wiener"}, default "brickwall"
        Pass-band shaping rule.

        - "brickwall": hard indicator, mask[k] = 1 if effective magnitude
          at bin k exceeds threshold * peak, else 0.
        - "wiener": soft Wiener-style shaping
          |P|^2 / (|P|^2 + alpha * peak^2).
    threshold : float, default 0.01
        Brick-wall threshold as a fraction of the peak effective magnitude
        (used when shape = "brickwall").
    alpha : float, default 0.01
        Wiener regularisation (used when shape = "wiener").

    Returns
    -------
    numpy.ndarray
        Symmetric circulant Q-filter of shape (N, N).
    """
    signal = np.asarray(signal).ravel()
    N = len(signal)
    Sx = np.abs(np.fft.rfft(signal))
    if modulation is not None:
        modulation = np.asarray(modulation).ravel()
        if len(modulation) != N:
            raise ValueError(
                f"modulation must have length N={N}, got {len(modulation)}") # type: ignore
        Sm = np.abs(np.fft.rfft(modulation))
        spec = Sm * Sx
    else:
        spec = Sx

    peak = float(spec.max())
    if peak <= 0.0:
        raise ValueError("reference spectrum is zero everywhere")

    if shape == "brickwall":
        mask = (spec > threshold * peak).astype(float)
    elif shape == "wiener":
        p2 = spec ** 2
        mask = p2 / (p2 + alpha * peak ** 2)
    else:
        raise ValueError(
            f"shape must be 'brickwall' or 'wiener'; got {shape!r}")

    q_col = np.fft.irfft(mask.astype(complex), n=N)
    return circulant(q_col)


# ======================================================================================================================

if __name__ == '__main__':
    from core.utils.control_lib.lib_control.learning.dynamics_helpers import (
        hz_to_normalized,
        plot_impulse_spectrum,
    )
    from core.utils.control_lib.lib_control.learning.vector_generation import (
        multisine_vector,
    )

    N, dt = 200, 0.01
    cutoff_hz = 10
    cutoff = hz_to_normalized(cutoff_hz, dt=dt)

    # ------------------------------------------------------------------
    # Example 1: Impulse responses and spectra of the four Q variants.
    # IR is taken as the first column Q[:, 0] (= Q @ e_0).
    # ------------------------------------------------------------------
    Q_causal = causal_lowpass(N=N, cutoff_cps=cutoff, order=4)
    Q_brick = brickwall_lowpass(N=N, cutoff_cps=cutoff)
    Q_zp = zero_phase_lowpass(N=N, cutoff_cps=cutoff, order=4)
    Q_fir = fir_lowpass(N=N, cutoff_cps=cutoff, order=8)

    h_causal = Q_causal[:, 0]
    h_brick = Q_brick[:, 0]
    h_zp = Q_zp[:, 0]
    h_fir = Q_fir[:, 0]

    fig, (ax_t, ax_f) = plt.subplots(2, 1, figsize=(8, 6))
    t = np.arange(N) * dt
    ax_t.plot(t, h_causal, label="causal_lowpass (LTTM Butterworth)")
    ax_t.plot(t, h_brick, label="brickwall_lowpass (circulant ideal)",
              alpha=0.7)
    ax_t.plot(t, h_zp, label="zero_phase_lowpass (circulant Butterworth^2)",
              linestyle="--")
    ax_t.plot(t, h_fir, label="fir_lowpass (Q = H^T H)", linestyle=":")
    ax_t.set_xlabel("Time (s)")
    ax_t.set_ylabel("Amplitude")
    ax_t.set_title("Filter impulse responses (Q[:, 0])")
    ax_t.legend()
    ax_t.grid(True, alpha=0.3)

    plot_impulse_spectrum(h_causal, dt=dt, db=True, floor_db=-80,
                          label="causal_lowpass", ax=ax_f)
    plot_impulse_spectrum(h_brick, dt=dt, db=True, floor_db=-80,
                          label="brickwall_lowpass", ax=ax_f)
    plot_impulse_spectrum(h_zp, dt=dt, db=True, floor_db=-80,
                          label="zero_phase_lowpass", ax=ax_f,
                          linestyle="--")
    plot_impulse_spectrum(h_fir, dt=dt, db=True, floor_db=-80,
                          label="fir_lowpass", ax=ax_f, linestyle=":")
    ax_f.axvline(cutoff_hz, color="k", lw=0.8, ls="--",
                 label=f"cutoff = {cutoff_hz} Hz")
    ax_f.legend()
    plt.tight_layout()

    # ------------------------------------------------------------------
    # Example 2: Same input filtered four ways at the same cutoff.
    # ------------------------------------------------------------------
    rng = np.random.default_rng(seed=0)
    u = multisine_vector(N=N, rng=rng, amplitude=1.0, phase="random")

    y_causal = Q_causal @ u
    y_brick = Q_brick @ u
    y_zp = Q_zp @ u
    y_fir = Q_fir @ u

    fig2, (ax_t2, ax_f2) = plt.subplots(2, 1, figsize=(8, 6))
    ax_t2.plot(t, u, label="broadband multisine (input)", alpha=0.4)
    ax_t2.plot(t, y_causal, label="causal_lowpass")
    ax_t2.plot(t, y_brick, label="brickwall_lowpass", linestyle="--")
    ax_t2.plot(t, y_zp, label="zero_phase_lowpass", linestyle="-.")
    ax_t2.plot(t, y_fir, label="fir_lowpass", linestyle=":")
    ax_t2.set_xlabel("Time (s)")
    ax_t2.set_ylabel("Amplitude")
    ax_t2.set_title(f"Same input filtered four ways at {cutoff_hz} Hz")
    ax_t2.legend()
    ax_t2.grid(True, alpha=0.3)

    plot_impulse_spectrum(u, dt=dt, db=True, floor_db=-80,
                          label="input", ax=ax_f2)
    plot_impulse_spectrum(y_causal, dt=dt, db=True, floor_db=-80,
                          label="causal_lowpass", ax=ax_f2)
    plot_impulse_spectrum(y_brick, dt=dt, db=True, floor_db=-80,
                          label="brickwall_lowpass", ax=ax_f2,
                          linestyle="--")
    plot_impulse_spectrum(y_zp, dt=dt, db=True, floor_db=-80,
                          label="zero_phase_lowpass", ax=ax_f2,
                          linestyle="-.")
    plot_impulse_spectrum(y_fir, dt=dt, db=True, floor_db=-80,
                          label="fir_lowpass", ax=ax_f2,
                          linestyle=":")
    ax_f2.axvline(cutoff_hz, color="k", lw=0.8, ls="--",
                  label=f"cutoff = {cutoff_hz} Hz")
    ax_f2.legend()
    plt.tight_layout()

    plt.show()
