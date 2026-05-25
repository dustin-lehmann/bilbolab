import numpy as np
import scipy.signal as sig


# ======================================================================================================================
def random_flat_spectrum_vector(N: int, rng: np.random.Generator | None = None,
                                tail_sigma: float | None = None,
                                leading_tap: float = 1.0) -> np.ndarray:
    """Length-N real vector with an approximately flat DFT magnitude spectrum
    whose lifted causal Toeplitz matrix M(x) is well-conditioned.

    The construction is impulse-like: a strong unit-magnitude spike at x[0]
    plus small broadband Gaussian noise at the remaining taps. Writing the
    vector as x = leading_tap * e_0 + tail_sigma * n with n ~ N(0, I_N), the
    DFT is X(w) = leading_tap + tail_sigma * Z(w), where Z(w) is a sum of N
    unit-variance Gaussians weighted by unit-modulus complex exponentials and
    therefore has standard deviation sqrt(N). Hence, |X(w)| ~ leading_tap
    uniformly up to a stochastic band of width tail_sigma * sqrt(N) in DFT
    magnitude. With the default tail_sigma = 1 / sqrt(N), that band is O(1)
    and comparable to leading_tap.

    In the lifted matrix vec2liftedMatrix(x) (lower-triangular Toeplitz), the
    diagonal equals x[0] = leading_tap and the determinant is leading_tap**N,
    so the matrix is well-conditioned: singular values concentrate around
    |leading_tap| on a spread that shrinks as tail_sigma -> 0.

    This is the same construction as random_lttm in
    transfer/iitl/convergence_analysis/excitation_conditioning.py.

    Parameters
    ----------
    N : int
        Horizon length.
    rng : numpy.random.Generator, optional
        Random generator. If None, np.random.default_rng() is used.
    tail_sigma : float, optional
        Standard deviation of the Gaussian noise tail. Defaults to
        1 / sqrt (N), so the tail's total 2-norm is O(1) and comparable to
        leading_tap.
    leading_tap : float, default 1.0
        Magnitude of the impulse at x[0]. Controls the condition number:
        larger values give a better-conditioned LTTM matrix at the price
        of a less-flat spectrum.

    Returns
    -------
    numpy.ndarray
        Real vector of length N.
    """
    if rng is None:
        rng = np.random.default_rng()
    if tail_sigma is None:
        tail_sigma = 1.0 / np.sqrt(N)

    x = tail_sigma * rng.standard_normal(N)  # type: ignore
    x[0] += leading_tap * (np.sign(x[0]) if x[0] != 0.0 else 1.0)
    return x


# ======================================================================================================================
def multisine_vector(N: int,
                     rng: np.random.Generator | None = None,
                     amplitude: float = 1.0,
                     phase: str = "schroeder") -> np.ndarray:
    """Length-N real vector with an exactly flat DFT magnitude spectrum,
    constructed in the frequency domain as a multisine.

    Every nonzero DFT bin has magnitude ``amplitude``; only the phases vary.
    The result is real-valued (Hermitian symmetry enforced) and its lifted
    causal Toeplitz matrix is well-conditioned, with singular values that
    cluster tightly around ``amplitude``.

    Trade-off versus :func:`random_flat_spectrum_vector`: the spectrum is exactly
    flat (zero stochastic ripple), but the time-domain signal is no longer
    impulse-like and is spread over the full horizon.

    Parameters
    ----------
    N : int
        Horizon length.
    rng : numpy.random.Generator, optional
        Random generator used only when ``phase="random"``. If None,
        ``np.random.default_rng()`` is used.
    amplitude : float, default 1.0
        Per-bin DFT magnitude. By Parseval, the resulting time-domain
        signal has standard deviation approximately amplitude / sqrt(N).
    phase : {"schroeder", "random"}, default "schroeder"
        Phase assignment for the nonzero bins. "schroeder" uses
        phi_k = -k * (k - 1) * pi / M with M = N // 2 + 1, which minimizes
        peak-to-peak amplitude (low crest factor). "random" draws phases
        uniformly from [0, 2*pi), giving a noise-like time signal.

    Returns
    -------
    numpy.ndarray
        Real vector of length N with an exactly flat magnitude spectrum.
    """
    if rng is None:
        rng = np.random.default_rng()

    M = N // 2 + 1
    if phase == "schroeder":
        k = np.arange(M)
        phases = -np.pi * k * (k - 1) / M
    elif phase == "random":
        phases = rng.uniform(0.0, 2.0 * np.pi, size=M)
    else:
        raise ValueError(f"phase must be 'schroeder' or 'random', got {phase!r}")

    phases[0] = 0.0
    if N % 2 == 0:
        phases[-1] = 0.0

    X = amplitude * np.exp(1j * phases)
    return np.fft.irfft(X, n=N)


# ======================================================================================================================
def dft_amplitude_for_peak(N: int, target_peak: float,
                           cutoff_cps: float | None = None,
                           mode: str = "expected",
                           low_cps: float = 0.0) -> float:
    """Per-bin DFT magnitude that yields a desired time-domain amplitude
    for a random-phase multisine of length N.

    Background. A single bin k (1 <= k < N/2) with DFT magnitude A produces
    a cosine of time-domain amplitude 2*A/N. The bandlimited / multisine
    constructions in this module sum K such cosines (plus a DC and possibly
    a Nyquist contribution). For random phases the signal is approximately
    Gaussian with time-domain standard deviation

        sigma = (A / N) * sqrt(2 * K_inner + alpha),

    where K_inner is the number of inner bins (1 <= k < N/2) and alpha
    counts the DC bin (and the Nyquist bin when included). Three modes:

    - mode="expected": sizes for the typical maximum over N samples,
      peak ~ sigma * sqrt(2 * ln(N)), matching what the eye sees on a
      time-domain plot. This is the recommended default for visual targets.
    - mode="rms": sizes for sigma = target_peak (time-domain standard
      deviation = target_peak). Useful for energy / RMS targets.
    - mode="worst": guarantees |x[n]| <= target_peak for every phase
      realization (all cosines aligning at one sample). Tight bound but
      typically pessimistic by a factor of ~2-4.

    Parameters
    ----------
    N : int
        Horizon length.
    target_peak : float
        Desired time-domain amplitude (peak or RMS, depending on mode).
    cutoff_cps : float, optional
        If given, treats the signal as bandlimited with upper edge
        cutoff_cps in cycles/sample and counts only in-band bins. If None,
        treats it as a full-band multisine (K = N // 2 + 1).
    mode : {"expected", "rms", "worst"}, default "expected"
        Sizing convention. See above.
    low_cps : float, default 0.0
        Lower edge of the spectral support in cycles per sample. Bins at or
        below this value are excluded from the in-band count, matching the
        random_bandlimited_vector(low_cps=...) convention. Default 0 keeps
        DC in the band.

    Returns
    -------
    float
        Per-bin DFT magnitude to pass as the "amplitude" argument to
        random_bandlimited_vector or multisine_vector.
    """
    rfreqs = np.fft.rfftfreq(N, d=1.0)
    if cutoff_cps is None:
        in_band = np.ones_like(rfreqs, dtype=bool)
    else:
        if not (0.0 < cutoff_cps <= 0.5):
            raise ValueError(
                f"cutoff_cps must be in (0, 0.5]; got {cutoff_cps}")
        if not (0.0 <= low_cps < cutoff_cps):
            raise ValueError(
                f"low_cps must be in [0, cutoff_cps); "
                f"got low_cps={low_cps}, cutoff_cps={cutoff_cps}")
        in_band = (rfreqs > low_cps) & (rfreqs <= cutoff_cps)

    K = int(np.sum(in_band))
    if K < 1:
        raise ValueError("No in-band bins; cutoff_cps too small for this N.")

    has_dc = bool(in_band[0])
    has_nyq = bool(N % 2 == 0 and in_band[-1])
    K_inner = K - int(has_dc) - int(has_nyq)
    alpha = int(has_dc) + int(has_nyq)

    sigma_per_A = np.sqrt(2.0 * K_inner + alpha) / N

    if mode == "expected":
        peak_factor = np.sqrt(2.0 * np.log(max(N, 2)))
        return target_peak / (peak_factor * sigma_per_A)
    if mode == "rms":
        return target_peak / sigma_per_A
    if mode == "worst":
        worst_per_A = (2.0 * K_inner + alpha) / N
        return target_peak / worst_per_A
    raise ValueError(
        f"mode must be 'expected', 'rms', or 'worst'; got {mode!r}")


# ======================================================================================================================
def random_bandlimited_vector(N: int, cutoff_cps: float,
                              rng: np.random.Generator | None = None,
                              amplitude: float = 1.0,
                              target_peak: float | None = None,
                              mode: str = "expected",
                              low_cps: float = 0.0) -> np.ndarray:
    """Length-N real vector with DFT content strictly bounded to
    low_cps < |f| <= cutoff_cps (zero outside that band), built as a
    band-limited random-phase multisine. In-band bins all have the same
    magnitude; phases are drawn uniformly from [0, 2*pi).

    With the default low_cps = 0 this is a low-pass random vector. Setting
    low_cps > 0 turns it into a band-pass random vector (e.g. a "noise"
    confined to a particular frequency range).

    Unlike random_flat_spectrum_vector (broadband, impulse-like) or
    multisine_vector (broadband, full Nyquist support), this vector has
    exactly zero spectral content outside the band. Useful as a t_true
    when you want eta = ||(I - Q) t_true||_2 to be zero whenever Q's
    pass-band contains (low_cps, cutoff_cps].

    Parameters
    ----------
    N : int
        Horizon length.
    cutoff_cps : float
        Upper edge of the spectral support in cycles per sample,
        0 < cutoff_cps <= 0.5. The effective cutoff is rounded down to the
        nearest DFT bin k/N.
    rng : numpy.random.Generator, optional
        Random generator. If None, np.random.default_rng() is used.
    amplitude : float, default 1.0
        Per-bin DFT magnitude inside the pass-band. By Parseval, the time-
        domain standard deviation is roughly amplitude * sqrt(2 * K / N),
        where K is the number of in-band bins. Ignored when target_peak is
        given.
    target_peak : float, optional
        If given, the per-bin DFT magnitude is computed via
        dft_amplitude_for_peak so that the time-domain signal has the
        requested peak. Overrides amplitude. The bin count correctly
        accounts for low_cps.
    mode : {"expected", "worst"}, default "expected"
        Peak convention used when target_peak is given. See
        dft_amplitude_for_peak.
    low_cps : float, default 0.0
        Lower edge of the spectral support in cycles per sample,
        0 <= low_cps < cutoff_cps. Bins at or below this value are zeroed.
        Default 0 keeps DC and yields the original low-pass behaviour.

    Returns
    -------
    numpy.ndarray
        Real vector of length N with DFT supported strictly in
        (low_cps, cutoff_cps] (and its negative-frequency mirror).
    """
    if not (0.0 < cutoff_cps <= 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5]; got {cutoff_cps}")
    if not (0.0 <= low_cps < cutoff_cps):
        raise ValueError(
            f"low_cps must be in [0, cutoff_cps); "
            f"got low_cps={low_cps}, cutoff_cps={cutoff_cps}")
    if rng is None:
        rng = np.random.default_rng()

    if target_peak is not None:
        amplitude = dft_amplitude_for_peak(
            N, target_peak=target_peak, cutoff_cps=cutoff_cps, mode=mode,
            low_cps=low_cps)

    M = N // 2 + 1
    freqs = np.fft.rfftfreq(N, d=1.0)
    mask = (freqs > low_cps) & (freqs <= cutoff_cps)

    phases = rng.uniform(0.0, 2.0 * np.pi, size=M)
    phases[0] = 0.0
    if N % 2 == 0:
        phases[-1] = 0.0

    X = np.where(mask, amplitude * np.exp(1j * phases), 0.0 + 0.0j)
    return np.fft.irfft(X, n=N)


# ======================================================================================================================
def lowpass_vector(N: int,
                   cutoff_cps: float,
                   order: int = 4,
                   amplitude: float = 1.0,
                   target_peak: float | None = None,
                   mode: str = "peak") -> np.ndarray:
    """Length-N real vector equal to the causal impulse response of a
    Butterworth low-pass filter with the given cut-off and order, optionally
    rescaled to a target time-domain amplitude.

    Designed with scipy.signal.butter and evaluated as the response to a
    unit delta via scipy.signal.lfilter. Being a direct-form IIR, the digital
    Butterworth has relative degree 0 (immediate feedthrough b[0]/a[0]), so
    x[0] != 0 and the lifted Toeplitz matrix vec2liftedMatrix(x) has a
    non-zero diagonal, consistent with the "relative degree absorbed" LTTM
    convention used throughout this thesis.

    Unlike random_bandlimited_vector (brick-wall, exactly zero stop-band) the
    Butterworth has a smooth roll-off tail and non-zero spectral content
    above cutoff_cps; choose the construction that matches whether you need
    strict bandlimiting or a realistic analogue-style filter.

    Parameters
    ----------
    N : int
        Horizon length.
    cutoff_cps : float
        Cut-off frequency in cycles per sample, 0 < cutoff_cps < 0.5
        (Nyquist is 0.5).
    order : int, default 4
        Butterworth order. Each order adds 20 dB/decade of roll-off in the
        stop-band; typical values are 2--6.
    amplitude : float, default 1.0
        Direct scaling factor applied to the raw impulse response. Ignored
        when target_peak is given.
    target_peak : float, optional
        If given, the output is rescaled so that the requested time-domain
        amplitude is met (see mode). Overrides amplitude.
    mode : {"peak", "rms", "norm"}, default "peak"
        Sizing convention used when target_peak is given.

        - "peak": max(|x|) = target_peak.
        - "rms":  std(x)   = target_peak.
        - "norm": ||x||_2  = target_peak.

    Returns
    -------
    numpy.ndarray
        Real vector of length N.
    """
    if not (0.0 < cutoff_cps < 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5); got {cutoff_cps}")

    b, a = sig.butter(order, 2.0 * cutoff_cps, btype="low", output="ba")
    delta = np.zeros(N)
    delta[0] = 1.0
    x = sig.lfilter(b, a, delta)

    if target_peak is not None:
        if mode == "peak":
            ref = float(np.max(np.abs(x)))
        elif mode == "rms":
            ref = float(np.std(x))
        elif mode == "norm":
            ref = float(np.linalg.norm(x))
        else:
            raise ValueError(
                f"mode must be 'peak', 'rms', or 'norm'; got {mode!r}")
        if ref > 0.0:
            x = x * (target_peak / ref)
    else:
        x = x * amplitude

    return x


# ======================================================================================================================
def firwin_lowpass_vector(N: int, cutoff_cps: float,
                          order: int = 16,
                          window: str = "hann",
                          normalise: bool = True) -> np.ndarray:
    """Length-N vector built from a linear-phase Hann-windowed FIR low-pass
    kernel placed at x[0:order+1] and zero-padded elsewhere.

    Contrast with lowpass_vector (Butterworth IIR, causal, full-length tail
    decaying from x[0]): here the FIR kernel is symmetric around its centre,
    so x[0] is tiny (the edge of a Hann-windowed sinc). Consequently the
    lifted matrix vector_to_lifted_matrix(x) has a near-zero diagonal and
    is numerically rank-deficient — exactly the structural property used in
    the thesis "rate-sharpening" experiment, where a Q-filter that excises
    the stop-band singular modes of F^(beta) makes the filtered iteration
    converge faster than the unfiltered one.

    Parameters
    ----------
    N : int
        Horizon length.
    cutoff_cps : float
        FIR cutoff in cycles per sample, 0 < cutoff_cps < 0.5.
    order : int, default 16
        FIR order. The kernel has order + 1 symmetric taps; the rest of
        the vector is zero-padded.
    window : str, default "hann"
        Window passed to scipy.signal.firwin.
    normalise : bool, default True
        Divide by ||x||_2 before returning, so different cutoff/order
        combinations compare at unit-norm scale.

    Returns
    -------
    numpy.ndarray
        Real vector of length N.
    """
    if not (0.0 < cutoff_cps < 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5); got {cutoff_cps}")
    h = sig.firwin(order + 1, 2.0 * cutoff_cps, window=window)
    h = h / h.sum()  # DC gain 1
    if len(h) > N:
        raise ValueError(
            f"FIR length {len(h)} exceeds horizon N={N}; lower the order")
    x = np.zeros(N)
    x[: len(h)] = h
    if normalise:
        x = x / (np.linalg.norm(x) + 1e-12)
    return x


# ======================================================================================================================
def step_vector(N: int,
                amplitude: float = 1.0,
                start: int = 0,
                end: int | None = None,
                bias: float = 0.0) -> np.ndarray:
    """Length-N rectangular pulse: bias + amplitude on [start, end), bias
    elsewhere. With end=None (default), the output is bias + amplitude
    for every n >= start, i.e. an open-ended unit step.

    Parameters
    ----------
    N : int
        Horizon length.
    amplitude : float, default 1.0
        Step / pulse amplitude.
    start : int, default 0
        First active sample index, 0 <= start <= N.
    end : int, optional
        First sample *after* the active interval. If given, must satisfy
        start <= end <= N, producing a rectangular pulse on [start, end).
        Default None turns the output into an open-ended step.
    bias : float, default 0.0
        Constant offset applied everywhere.

    Returns
    -------
    numpy.ndarray
        Real vector of length N.
    """
    if not (0 <= start <= N):
        raise ValueError(f"start must be in [0, N]; got {start} for N={N}")
    if end is not None and not (start <= end <= N):
        raise ValueError(
            f"end must be in [start, N]; got end={end}, start={start}, N={N}")
    x = np.full(N, bias, dtype=float)
    stop = N if end is None else end
    x[start:stop] = bias + amplitude
    return x


# ======================================================================================================================
def random_smooth_input(N: int,
                        cutoff_cps: float,
                        amplitude: float = 1.0,
                        bias: float = 0.0,
                        order: int = 6,
                        max_crest: float = 3.0,
                        align_start_to_zero: bool = True,
                        max_attempts: int = 100,
                        rng: np.random.Generator | None = None) -> np.ndarray:
    """Length-N real vector built by zero-phase Butterworth low-pass
    filtering of i.i.d. uniform noise, rejection-sampled until the crest
    factor max(|u|) / RMS(u) is below max_crest, then optionally trimmed
    so that u[0] is close to zero.

    Compare random_bandlimited_vector (brick-wall, no time-domain
    constraints) and multisine_vector (exact-flat spectrum, no crest
    control). Use this generator when you need a smooth, low-crest random
    input that is safe to apply to a physical actuator — typically in
    IITL / ILC trajectory excitation.

    The amplitude rescaling enforces 2 * std(u) = amplitude, so most
    samples lie in [bias - amplitude, bias + amplitude] (roughly the 95 %
    band of a Gaussian); paired with max_crest = 3 the absolute peak is
    bounded by ~1.5 * amplitude.

    Parameters
    ----------
    N : int
        Output length (samples).
    cutoff_cps : float
        Butterworth cut-off in cycles per sample, 0 < cutoff_cps < 0.5.
    amplitude : float, default 1.0
        Scaling such that 2 * std(u) = amplitude. Not the strict peak —
        peaks up to max_crest * amplitude / 2 are admissible.
    bias : float, default 0.0
        Constant offset added to the output.
    order : int, default 6
        Butterworth order applied via scipy.signal.filtfilt (zero-phase,
        so the effective stop-band attenuation is doubled vs. one-pass).
    max_crest : float, default 3.0
        Upper bound on max(|u|) / RMS(u) before rescaling. Trajectories
        exceeding this are rejected and re-drawn.
    align_start_to_zero : bool, default True
        If True, oversample by 2x and start the returned segment at the
        first sample whose magnitude is below
        amplitude * 10 / (100 * ln(N / 2)) so that u[0] ~ 0 — useful when
        the trajectory must not jolt the system at t = 0.
    max_attempts : int, default 100
        Maximum number of rejection draws before raising. Hitting this
        limit usually means cutoff_cps is too high (signal is noise-like
        with high crest) or order is too low.
    rng : numpy.random.Generator, optional
        Source of the underlying uniform noise. If None, uses
        numpy.random.default_rng().

    Returns
    -------
    numpy.ndarray
        Real vector of length N.

    Raises
    ------
    RuntimeError
        If max_attempts is reached without a sample meeting max_crest, or
        if align_start_to_zero is requested but no near-zero sample is
        found in the oversampled draw.
    """
    if not (0.0 < cutoff_cps < 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5); got {cutoff_cps}")
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1; got {max_attempts}")
    if rng is None:
        rng = np.random.default_rng()

    b, a = sig.butter(order, 2.0 * cutoff_cps, btype="low")

    u = None
    for _ in range(max_attempts):
        raw = 2.0 * (rng.random(2 * N) - 0.5)
        candidate = sig.filtfilt(b, a, raw)
        rms = float(np.sqrt(np.mean(candidate ** 2)))
        if rms == 0.0:
            continue
        if float(np.max(np.abs(candidate))) / rms <= max_crest:
            u = candidate
            break
    if u is None:
        raise RuntimeError(
            f"could not draw a sample with crest factor <= {max_crest} "
            f"in {max_attempts} attempts "
            f"(cutoff_cps={cutoff_cps}, order={order})")

    u = amplitude * u / (2.0 * np.std(u))  # type: ignore

    if align_start_to_zero:
        threshold = amplitude * 10.0 / (100.0 * np.log(max(N / 2.0, np.e)))
        idx = np.where(np.abs(u) < threshold)[0]
        if len(idx) == 0 or int(idx[0]) + N > len(u):  # type: ignore
            raise RuntimeError(
                "no near-zero starting sample found within the oversampled "
                "draw; either increase N, lower cutoff_cps, or set "
                "align_start_to_zero=False")
        start = int(idx[0])
        u = u[start:start + N]  # type: ignore
    else:
        u = u[:N]  # type: ignore

    return u + bias


# ======================================================================================================================
def lowpass_random_input(N: int,
                         cutoff_cps: float,
                         sigma: float = 1.0,
                         u0_bias: float = 0.0,
                         rng: np.random.Generator | None = None) -> np.ndarray:
    """Length-N real vector built by FFT-masking standard Gaussian noise to
    the band [0, cutoff_cps], rescaling to a target standard deviation, and
    optionally kicking u[0] away from zero by u0_bias.

    Designed for IITL deployment / source inputs whose lifted Toeplitz
    matrix M(u) must remain invertible: a non-zero leading sample (set via
    u0_bias) keeps the diagonal of M(u) nonzero. Compare random_smooth_input
    (Butterworth filtfilt + crest control + start-aligned to zero — the
    opposite trade-off) and random_bandlimited_vector (random-phase
    multisine, no time-domain rescaling).

    Procedure:
        1. Draw u_0 ~ N(0, I_N).
        2. FFT-mask: zero bins with frequency > cutoff_cps.
        3. Rescale: u <- sigma * u / std(u).
        4. u[0] += u0_bias * sign(u[0])  (or +u0_bias if u[0] == 0).

    Parameters
    ----------
    N : int
        Output length (samples).
    cutoff_cps : float
        Pass-band edge in cycles per sample, 0 < cutoff_cps <= 0.5. Bins
        with frequency strictly greater than cutoff_cps are zeroed.
    sigma : float, default 1.0
        Target standard deviation after rescaling, before the u0_bias
        kick is applied.
    u0_bias : float, default 0.0
        Magnitude added to u[0] in the direction of its sign, ensuring a
        non-zero first sample. With the default 0.0 the kick is omitted
        and u[0] retains its FFT-masked / rescaled value.
    rng : numpy.random.Generator, optional
        Source of the underlying Gaussian noise. If None, uses
        numpy.random.default_rng().

    Returns
    -------
    numpy.ndarray
        Real vector of length N.
    """
    if not (0.0 < cutoff_cps <= 0.5):
        raise ValueError(f"cutoff_cps must be in (0, 0.5]; got {cutoff_cps}")
    if rng is None:
        rng = np.random.default_rng()

    raw = rng.standard_normal(N)
    freqs = np.fft.rfftfreq(N, d=1.0)
    keep = (freqs <= cutoff_cps).astype(float)
    U = np.fft.rfft(raw) * keep
    u = np.fft.irfft(U, n=N)

    u = sigma * u / (float(np.std(u)) + 1e-12)
    if u0_bias != 0.0:
        u[0] += u0_bias * (np.sign(u[0]) if u[0] != 0.0 else 1.0)
    return u


# ======================================================================================================================
def prbs_vector(N: int,
                n_bits: int = 11,
                amplitude: float = 1.0,
                bias: float = 0.0,
                hold_samples: int = 1,
                rng: np.random.Generator | None = None) -> np.ndarray:
    """Length-N pseudo-random binary sequence (PRBS) drawn from a
    maximum-length linear feedback shift register of register length
    n_bits. Output values lie in {bias - amplitude, bias + amplitude}
    and the underlying bit stream has period 2**n_bits - 1.

    The m-sequence has nearly white autocorrelation
    (R(0) = amplitude**2, R(k != 0) = -amplitude**2 / (2**n_bits - 1)),
    so its DFT magnitude is approximately flat. PRBS is therefore a
    canonical excitation for linear system identification — every
    frequency in [0, Nyquist] is excited at near-equal energy with a
    deterministic, repeatable, two-level signal.

    Compare multisine_vector (exact-flat spectrum, real-valued multi-
    cosine) and random_bandlimited_vector (brick-wall random-phase): PRBS
    sacrifices a perfectly flat spectrum for a deterministic two-level
    waveform that is easy to apply on hardware (no DAC resolution loss,
    on-off toggling actuators).

    Parameters
    ----------
    N : int
        Output length (samples).
    n_bits : int, default 11
        LFSR register length, 2 <= n_bits <= 16. The bit-stream period
        is 2**n_bits - 1; with the default n_bits = 11 that is 2047.
    amplitude : float, default 1.0
        Output level; values are bias +/- amplitude.
    bias : float, default 0.0
        Constant offset.
    hold_samples : int, default 1
        Number of consecutive output samples per PRBS bit. Values greater
        than 1 slow the switching rate so the input matches the bandwidth
        of the system under test — a PRBS held for hold_samples samples
        concentrates its energy in [0, 1 / (2 * hold_samples)] cycles per
        sample.
    rng : numpy.random.Generator, optional
        Source for the random initial register state. If None, the LFSR
        is initialised to all ones (deterministic, canonical m-sequence).
        Pass a seeded Generator for a different but reproducible phase.

    Returns
    -------
    numpy.ndarray
        Real vector of length N taking exactly two distinct values.

    Notes
    -----
    Delegates to :func:`scipy.signal.max_len_seq`; the bit stream is
    tiled when N exceeds (2**n_bits - 1) * hold_samples.
    """
    if not (2 <= n_bits <= 16):
        raise ValueError(f"n_bits must be in [2, 16]; got {n_bits}")
    if hold_samples < 1:
        raise ValueError(f"hold_samples must be >= 1; got {hold_samples}")
    if N <= 0:
        raise ValueError(f"N must be positive; got {N}")

    period = 2 ** n_bits - 1
    n_bit_samples = (N + hold_samples - 1) // hold_samples

    if rng is None:
        initial_state = None
    else:
        state_int = int(rng.integers(1, period + 1))
        initial_state = np.array(
            [(state_int >> i) & 1 for i in range(n_bits)], dtype=np.int8)

    if n_bit_samples <= period:
        seq, _ = sig.max_len_seq(n_bits, state=initial_state,
                                 length=n_bit_samples)
    else:
        seq_one, _ = sig.max_len_seq(n_bits, state=initial_state,
                                     length=period)
        n_repeats = (n_bit_samples + period - 1) // period
        seq = np.tile(seq_one, n_repeats)[:n_bit_samples]

    if hold_samples > 1:
        seq = np.repeat(seq, hold_samples)
    seq = seq[:N]

    return bias + amplitude * (2.0 * seq.astype(float) - 1.0)