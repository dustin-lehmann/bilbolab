from __future__ import annotations

import dataclasses

import numpy as np
from scipy.fft import rfftfreq, rfft
from scipy.signal import find_peaks

from robots.bilbo.robot.experiment.experiment_definitions import InputTrajectory


# === ANALYTICS ========================================================================================================
@dataclasses.dataclass
class FrequencyComponent:
    frequency: float
    weight: float  # relative amplitude (normalized to 1)


@dataclasses.dataclass
class BILBO_InputAnalytics:
    steps: int
    Ts: float
    max_amplitude: float
    dominant_frequencies: list[FrequencyComponent]
    is_2d: bool


def generateInputTrajectoryAnalytics(input_trajectory: InputTrajectory,
                                     num_dominant: int = 5) -> BILBO_InputAnalytics:
    steps = input_trajectory.length
    time_vector = input_trajectory.time_vector
    Ts = float(time_vector[1] - time_vector[0])  # Sampling time

    # Extract signal vectors
    left_signal = np.array([input_trajectory.inputs[i].left for i in sorted(input_trajectory.inputs)])
    right_signal = np.array([input_trajectory.inputs[i].right for i in sorted(input_trajectory.inputs)])
    is_2d = not np.allclose(left_signal, right_signal)

    # Use average of both channels for analysis
    combined_signal = 0.5 * (left_signal + right_signal)

    # FFT analysis
    freqs = rfftfreq(steps, Ts)
    fft_magnitude = np.abs(rfft(combined_signal))

    # Remove DC component
    fft_magnitude[0] = 0.0

    # Find all peaks above a threshold (e.g., 5% of max)
    peak_indices, _ = find_peaks(fft_magnitude, height=np.max(fft_magnitude) * 0.05)

    if len(peak_indices) == 0:
        dominant_components = []
    else:
        # Sort by amplitude
        sorted_indices = peak_indices[np.argsort(fft_magnitude[peak_indices])[::-1]]

        # Pick top N
        top_indices = sorted_indices[:num_dominant]
        top_freqs = freqs[top_indices]
        top_amps = fft_magnitude[top_indices]

        # Normalize weights
        total_amp = np.sum(top_amps)
        weights = top_amps / total_amp if total_amp > 0 else np.zeros_like(top_amps)

        dominant_components = [
            FrequencyComponent(frequency=freq, weight=float(weight))
            for freq, weight in zip(top_freqs, weights)
        ]

    # Max signal amplitude (could be RMS, but sticking to peak for now)
    max_amplitude = np.max(np.abs(combined_signal))

    return BILBO_InputAnalytics(
        steps=steps,
        Ts=Ts,
        max_amplitude=max_amplitude,
        dominant_frequencies=dominant_components,
        is_2d=is_2d,
    )
