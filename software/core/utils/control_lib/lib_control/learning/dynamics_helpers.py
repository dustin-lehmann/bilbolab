from typing import overload

import numpy as np
import matplotlib.pyplot as plt


# ======================================================================================================================
@overload
def hz_to_normalized(f_hz: float, dt: float, unit: str = "cycles") -> float: ...


@overload
def hz_to_normalized(f_hz: np.ndarray, dt: float, unit: str = "cycles") -> np.ndarray: ...


def hz_to_normalized(f_hz, dt: float, unit: str = "cycles"):
    """Convert a frequency (or array of frequencies) in Hz to a normalized
    discrete-time frequency at the sample period "dt".

    Parameters
    ----------
    f_hz : float or array_like
        Frequency in Hz. Must satisfy 0 <= f_hz <= 1 / (2 * dt) to lie
        within the first Nyquist band; values outside are returned as-is
        (no aliasing wrap), so the caller can detect violations.
    dt : float
         the Sample period in seconds. The sampling rate is fs = 1 / dt.
    unit: {"cycles", "rad"}, default "cycles"
        Output convention. "cycles" returns f_hz * dt in cycles/sample
        (range [0, 0.5] up to Nyquist). "rad" returns 2 * pi * f_hz * dt
        in rad/sample (range [0, pi]).

    Returns
    -------
    numpy.ndarray
        Normalized frequency in the requested unit.
    """
    scalar_in = np.isscalar(f_hz)
    f_hz = np.asarray(f_hz, dtype=float)
    if unit == "cycles":
        out = f_hz * dt
    elif unit == "rad":
        out = 2.0 * np.pi * f_hz * dt
    else:
        raise ValueError(f"unit must be 'cycles' or 'rad', got {unit!r}")
    return float(out) if scalar_in else out


# ======================================================================================================================
def normalized_to_hz(f_norm, dt: float, unit: str = "cycles") -> float | np.ndarray:
    """Inverse of: func:`hz_to_normalized`.

    Parameters
    ----------
    f_norm : float or array_like
        Normalized frequency in cycles/sample (range [0, 0.5]) or rad/sample
        (range [0, pi]), depending on "unit".
    dt : float
         the Sample period in seconds.
    unit: {"cycles", "rad"}, default "cycles"
        Convention of "f_norm". See: func:`hz_to_normalized`.

    Returns
    -------
    numpy.ndarray
        Frequency in Hz.
    """
    scalar_in = np.isscalar(f_norm)
    f_norm = np.asarray(f_norm, dtype=float)
    if unit == "cycles":
        out = f_norm / dt
    elif unit == "rad":
        out = f_norm / (2.0 * np.pi * dt)
    else:
        raise ValueError(f"unit must be 'cycles' or 'rad', got {unit!r}")
    return float(out) if scalar_in else out


# ======================================================================================================================
def plot_impulse_spectrum(x: np.ndarray,
                          dt: float | None = None,
                          n_fft: int | None = None,
                          db: bool = True,
                          floor_db: float = -120.0,
                          show_phase: bool = False,
                          ax=None,
                          label: str | None = None,
                          **plot_kwargs):
    """Plot the magnitude (and optional phase) spectrum of a vector treated
    as an impulse response.

    Useful for visualizing how flat the spectrum of an excitation signal is,
    or for inspecting the frequency response implied by a finite impulse
    response. Computes the one-sided DFT via numpy.fft.rfft and plots
    magnitude on a linear or dB scale.

    Parameters
    ----------
    x : numpy.ndarray
        Real-valued impulse response or excitation vector of length N.
    dt : float, optional
        Sample period in seconds. If given, the frequency axis is in Hz from
        0 to fs/2. If None, frequencies are normalized to [0, 0.5] cycles
        per sample.
    n_fft : int, optional
        FFT length. Defaults to len(x). Pass a larger value for zero-padded
        interpolation of the spectrum.
    db : bool, default True
        If True, plot 20 * log10(|X|) in dB. Otherwise plot |X| linearly.
    floor_db : float, default -120.0
        Lower clamp for the dB plot. Values below this are clipped to
        floor_db so that numerical zeros do not drag the y-axis down to
        -6000 dB. The y-axis lower limit is also set to floor_db. Ignored
        when db is False.
    show_phase : bool, default False
        If True, add a second subplot with unwrapped phase in degrees.
    ax : matplotlib axes or pair of axes, optional
        Axes to draw into. If show_phase is True, expects a 2-element
        sequence (mag_ax, phase_ax). If None, a new figure is created.
    label : str, optional
        Legend label for the plotted curve.
    **plot_kwargs
        Forwarded to matplotlib's plot() (e.g. color, linestyle, alpha).

    Returns
    -------
    (freqs, magnitude, phase, axes)
        freqs is the frequency axis (Hz if dt given, normalized otherwise),
        magnitude and phase are the corresponding arrays (phase is None if
        show_phase is False), and axes is the list of axes drawn into.
    """
    x = np.asarray(x).ravel()
    N = len(x)
    if n_fft is None:
        n_fft = N

    X = np.fft.rfft(x, n=n_fft)
    mag = np.abs(X)
    phase = np.unwrap(np.angle(X)) if show_phase else None

    if dt is not None:
        freqs = np.fft.rfftfreq(n_fft, d=dt)  # type: ignore
        xlabel = "Frequency (Hz)"
    else:
        freqs = np.fft.rfftfreq(n_fft, d=1.0)  # type: ignore
        xlabel = "Normalized frequency (cycles/sample)"

    if ax is None:
        if show_phase:
            fig, axes = plt.subplots(2, 1, sharex=True, figsize=(7, 5))
        else:
            fig, ax_single = plt.subplots(figsize=(7, 3.5))
            axes = [ax_single]
    else:
        axes = list(ax) if show_phase else [ax]

    if db:
        floor_lin = 10.0 ** (floor_db / 20.0)
        mag_plot = 20.0 * np.log10(np.maximum(mag, floor_lin))
    else:
        mag_plot = mag
    axes[0].plot(freqs, mag_plot, label=label, **plot_kwargs)
    axes[0].set_ylabel("Magnitude (dB)" if db else "Magnitude")
    axes[0].grid(True, alpha=0.3)
    if db:
        peak = float(np.max(mag_plot))
        axes[0].set_ylim(floor_db, peak + 6.0)
    if label is not None:
        axes[0].legend()

    if show_phase:
        axes[1].plot(freqs, np.degrees(phase), label=label, **plot_kwargs)
        axes[1].set_ylabel("Phase (deg)")
        axes[1].set_xlabel(xlabel)
        axes[1].grid(True, alpha=0.3)
    else:
        axes[0].set_xlabel(xlabel)

    return freqs, mag, phase, axes
