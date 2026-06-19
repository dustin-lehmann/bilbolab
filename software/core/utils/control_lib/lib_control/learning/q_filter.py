import dataclasses

import numpy as np
from typing import Tuple

__all__ = [
    "design_zero_phase_fir",
    "apply_zero_phase_to_params",
    "build_Qf_zero_padded",
    "build_Qf_circulant",
    "fir_toeplitz_causal",
    "build_Qf_TtT",
    "freq_response",
    "FIR_Design_Params",
]


# ================================================================
# FIR Q-FILTER DESIGN: Intuitive Tutorial
#
# We want a Q-filter that smooths the parameter vector m across its
# coefficients. The function
#
#     h = design_zero_phase_fir(fc=0.2, L=61, window="hann")
#
# returns a symmetric, linear-phase FIR low-pass filter that we can
# apply to m (zero-phase, so no shift of features).
#
# -------------------------------
# 1) The cutoff frequency (fc)
# -------------------------------
# - "fc" is the cutoff frequency, expressed in *cycles per coefficient*.
# - Nyquist (the fastest oscillation representable) is 0.5 cycles/coeff.
#   -> a sine wave alternating +1, -1, +1, ...
# - Smaller fc = stronger low-pass (more smoothing).
#   Example: fc = 0.05 keeps only very slow trends (~20 coeffs per cycle).
# - Larger fc = weaker low-pass (less smoothing).
#   Example: fc = 0.4 almost passes everything, just gentle smoothing.
#
# In practice, fc ~ 0.1–0.3 is a reasonable range for parameter smoothing.
#
# -------------------------------
# 2) The filter length (L)
# -------------------------------
# - L (odd number) sets the number of taps of the FIR filter.
# - Longer L => sharper transition from passband to stopband
#   (more selective cutoff), but also more computation and longer
#   "edge effects" near the start/end of the vector.
# - Shorter L => blurrier transition, less selective, but simpler.
#
# Rough rule: transition width ≈ 4 / L   (in cycles per coeff).
# Example: L=61 → transition ~0.065. So if fc=0.2, then cutoff rolls
# off between 0.2 and 0.265 cycles/coeff.
#
# -------------------------------
# 3) The window
# -------------------------------
# - Because we truncate the ideal sinc filter, we need a window to
#   control ripples and sidelobes.
# - "hann": good general-purpose choice (side lobes ~ -31 dB).
# - "hamming": similar, a bit less ripple (~ -41 dB).
# - "blackman": strongest suppression (~ -57 dB), but wider transition.
#
# In short:
#   - Use "hann" for balanced smoothing (default).
#   - Use "blackman" if you want to kill high-frequency noise as much
#     as possible, even if transition is broader.
#
# -------------------------------
# 4) Application
# -------------------------------
# After designing h, you can:
#
#   # Direct zero-phase convolution
#   m_next = apply_zero_phase_to_params(m_tilde, h)
#
#   # Matrix form (equivalent to above, |H| frequency response)
#   Qf = build_Qf_zero_padded(h, N)
#   m_next = Qf @ m_tilde
#
#   # SPD variant (|H|^2 response, guaranteed positive definite)
#   Qf = build_Qf_TtT(h, N)
#   m_next = Qf @ m_tilde
#
# Direct convolution and Qf-zero-padded are *intuitively* exactly the
# same. The SPD variant is slightly "stronger" smoothing, but ensures
# nice mathematical properties (useful in learning control proofs).
#
# ================================================================


# -------------------------------
# FIR design and application
# -------------------------------
@dataclasses.dataclass(frozen=True)
class FIR_Design_Params:
    fc: float
    L: int
    window: str = "hann"  # can be "hann", "hamming", "blackman"


def design_zero_phase_fir(fc: float, L: int, window: str = "hann") -> np.ndarray:
    """
    Design a symmetric, linear-phase low-pass FIR by windowed-sinc.
    fc: cutoff in cycles/coefficient (0 < fc < 0.5). Nyquist = 0.5
    L : odd number of taps (e.g., 31, 41, 61)
    window: "hann", "hamming", "blackman"
    Returns h with DC gain = 1 (sum(h) == 1).
    """
    if not (0 < fc < 0.5):
        raise ValueError("fc must be in (0, 0.5).")
    if L % 2 != 1:
        raise ValueError("Use an odd number of taps L for symmetric linear-phase.")

    M = (L - 1) // 2
    n = np.arange(-M, M + 1, dtype=float)

    # Ideal low-pass in cycles/sample domain
    h_ideal = np.zeros_like(n, dtype=float)
    nz = n != 0
    h_ideal[nz] = np.sin(2 * np.pi * fc * n[nz]) / (np.pi * n[nz])
    h_ideal[~nz] = 2 * fc

    # Window
    if window == "hann":
        w = 0.5 - 0.5 * np.cos(2 * np.pi * (np.arange(L)) / (L - 1))
    elif window == "hamming":
        w = 0.54 - 0.46 * np.cos(2 * np.pi * (np.arange(L)) / (L - 1))
    elif window == "blackman":
        w = 0.42 - 0.5 * np.cos(2 * np.pi * (np.arange(L)) / (L - 1)) + 0.08 * np.cos(
            4 * np.pi * (np.arange(L)) / (L - 1))
    else:
        raise ValueError("Unsupported window: choose 'hann', 'hamming', or 'blackman'.")

    h = h_ideal * w
    h /= h.sum()  # normalize DC gain
    # ensure perfect symmetry
    h = 0.5 * (h + h[::-1])
    return h


def apply_zero_phase_to_params(m: np.ndarray, h: np.ndarray, pad_mode: str = "edge") -> np.ndarray:
    """
    Centered convolution (mode='same') with symmetric h -> zero-phase smoothing of m.
    pad_mode: how to pad at boundaries for the centered convolution ("edge", "reflect", etc.).
    """
    m = np.asarray(m).ravel()
    h = np.asarray(h).ravel()
    if len(h) % 2 != 1:
        raise ValueError("h must be symmetric with odd length.")
    pad = (len(h) - 1) // 2
    m_pad = np.pad(m, pad, mode=pad_mode)
    y = np.convolve(m_pad, h, mode="same")[pad:-pad]
    return y


# -------------------------------
# Matrix forms of the Q-filter
# -------------------------------

def build_Qf_zero_padded(h: np.ndarray, N: int) -> np.ndarray:
    """
    Zero-phase, centered *linear* convolution as a matrix (zero padding outside 0..N-1).
    Result: symmetric banded Toeplitz (truncated near edges).
    """
    h = np.asarray(h, dtype=float).ravel()
    if len(h) % 2 != 1:
        raise ValueError("h must be symmetric with odd length.")
    L = len(h)
    M = (L - 1) // 2
    Q = np.zeros((N, N), dtype=float)
    # offsets r = j - i
    for r in range(-M, M + 1):
        diag_len = N - abs(r)
        if diag_len <= 0:
            continue
        Q += np.diag(np.full(diag_len, h[M + r]), k=r)
    # enforce symmetry numerically
    Q = 0.5 * (Q + Q.T)
    return Q


def build_Qf_circulant(h: np.ndarray, N: int) -> np.ndarray:
    """
    Zero-phase, centered *circular* convolution as a matrix (wrap-around).
    Result: symmetric circulant banded matrix.
    """
    h = np.asarray(h, dtype=float).ravel()
    if len(h) % 2 != 1:
        raise ValueError("h must be symmetric with odd length.")
    L = len(h)
    M = (L - 1) // 2
    Q = np.zeros((N, N), dtype=float)
    E = np.eye(N)
    for r in range(-M, M + 1):
        Q += h[M + r] * np.roll(E, shift=r, axis=1)
    Q = 0.5 * (Q + Q.T)  # ensure symmetry
    return Q


def fir_toeplitz_causal(h: np.ndarray, N: int) -> np.ndarray:
    """
    Build causal Toeplitz T(h), N x N, for FIR h with h[0] at k=0.
    """
    h = np.asarray(h).ravel()
    L = len(h)
    T = np.zeros((N, N), dtype=float)
    for i in range(N):
        kmax = min(i + 1, L)
        T[i, i - kmax + 1:i + 1] = h[:kmax][::-1]
    return T


def build_Qf_TtT(h: np.ndarray, N: int, normalize_dc: bool = True) -> np.ndarray:
    """
    SPD 'Q_f' via Q_f = T(h)^T T(h). This applies |H|^2 in frequency.
    If normalize_dc is True, DC gain is normalized to 1 (divides by (sum h)^2).
    """
    Tq = fir_toeplitz_causal(h, N)
    Qf = Tq.T @ Tq
    if normalize_dc:
        s = np.sum(h)
        if s != 0:
            Qf = Qf / (s * s)
    # ensure symmetry numerically
    Qf = 0.5 * (Qf + Qf.T)
    return Qf


# -------------------------------
# Frequency response utility
# -------------------------------

def freq_response(h: np.ndarray, worN: int = 1024) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns (freq, |H(e^{j2πf})|) with f in [0, 0.5] cycles/sample.
    """
    h = np.asarray(h, dtype=float).ravel()
    f = np.linspace(0, 0.5, worN)
    n = np.arange(len(h))
    expo = np.exp(-1j * 2 * np.pi * f[:, None] * n[None, :])
    H = expo @ h
    mag = np.abs(H)
    return f, mag


# -------------------------------
# Examples (run when executed directly)
# -------------------------------

if __name__ == "__main__":
    import matplotlib.pyplot as plt

    # Example 1: smooth a noisy parameter vector
    N = 300
    i = np.arange(N)
    m_true = 0.6 * np.sin(2 * np.pi * 0.05 * i) + 0.3 * np.sin(2 * np.pi * 0.18 * i)
    np.random.seed(0)
    m_noisy = m_true + 0.15 * np.random.randn(N)

    # Design FIR low-pass
    h = design_zero_phase_fir(fc=0.2, L=61, window="hann")

    # Apply directly (centered convolution)
    m_smooth = apply_zero_phase_to_params(m_noisy, h)
    #
    # plt.figure()
    # plt.title("Zero-phase smoothing of parameter vector")
    # plt.plot(m_noisy, label="noisy m")
    # plt.plot(m_smooth, label="smoothed (fc=0.20, L=61)")
    # plt.legend()
    # plt.xlabel("coefficient index")
    # plt.ylabel("amplitude")
    # plt.show()
    #
    # # Example 2: compare matrix Q_f variants
    # Q_zero = build_Qf_zero_padded(h, N)
    # Q_circ = build_Qf_circulant(h, N)
    # Q_ttt = build_Qf_TtT(h, N)
    #
    # mB = Q_zero @ m_noisy
    # mC = Q_circ @ m_noisy
    # mD = Q_ttt @ m_noisy
    #
    # plt.figure()
    # plt.title("Matrix Q_f variants vs direct FIR")
    # plt.plot(m_smooth, label="direct FIR (ref)")
    # plt.plot(mB, label="Qf zero-padded @ m")
    # plt.plot(mC, label="Qf circulant @ m")
    # plt.plot(mD, label="Qf = T^T T @ m (|H|^2)")
    # plt.legend()
    # plt.xlabel("coefficient index")
    # plt.ylabel("amplitude")
    # plt.show()

    # Frequency response of FIR taps
    f, mag = freq_response(h)
    plt.figure()
    plt.title("Magnitude response of h and |H|^2")
    plt.plot(f, mag, label="|H|")
    plt.plot(f, mag ** 2, label="|H|^2")
    plt.xlabel("frequency [cycles / coefficient]")
    plt.ylabel("magnitude")
    plt.legend()
    plt.show()
