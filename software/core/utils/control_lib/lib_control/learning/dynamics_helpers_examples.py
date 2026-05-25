"""Examples showcasing the helpers in dynamics_helpers.py.

Run this file directly to produce the figures.
"""
import matplotlib.pyplot as plt
import numpy as np

from core.utils.control_lib.lib_control.learning.dynamics_helpers import (
    hz_to_normalized,
    plot_impulse_spectrum,
)
from core.utils.control_lib.lib_control.learning.vector_generation import (
    random_bandlimited_vector, random_flat_spectrum_vector,
)
from core.utils.control_lib.lib_control.learning.filters import (
    signal_matched_q,
)


def example_signal_matched_q_recovers_band():
    """Build a bandlimited input, derive a brick-wall Q-filter from it via
    signal_matched_q, and verify that the Q-filter passband matches the
    input's spectral support — i.e. Q @ u recovers u exactly.
    """
    N, dt = 200, 0.01

    # Bandlimited input: random-phase multisine with content only in
    # [0, cutoff_hz]. Outside that band the spectrum is exactly zero.
    cutoff_hz = 8.0
    low_hz = 2.0
    cutoff = hz_to_normalized(cutoff_hz, dt=dt)
    low = hz_to_normalized(low_hz, dt=dt)
    rng = np.random.default_rng(seed=0)
    u = random_bandlimited_vector(N=N, low_cps=low, cutoff_cps=cutoff, rng=rng,
                                  target_peak=1.0)

    # Data-driven Q-filter: keep all bins whose magnitude exceeds 1% of the
    # peak input magnitude, zero everything else. No fixed cutoff supplied.
    Q = signal_matched_q(signal=u, shape="brickwall", threshold=0.01)

    # Apply Q to u. Because Q's passband is exactly the support of u, this
    # should reproduce u up to floating-point error.
    y = Q @ u
    err = np.linalg.norm(y - u) / np.linalg.norm(u)
    print(f"||Q @ u - u||_2 / ||u||_2 = {err:.2e}")

    # Visualise: input spectrum vs Q's effective frequency response, plus
    # time-domain comparison of u and Q @ u.
    fig, (ax_t, ax_f) = plt.subplots(2, 1, figsize=(8, 6))
    t = np.arange(N) * dt
    ax_t.plot(t, u, label="input u (bandlimited)", alpha=0.7)
    ax_t.plot(t, y, label="Q @ u (recovered)", linestyle="--")
    ax_t.set_xlabel("Time (s)")
    ax_t.set_ylabel("Amplitude")
    ax_t.set_title(f"Bandlimited input passed through signal_matched_q "
                   f"(cutoff = {cutoff_hz} Hz)")
    ax_t.legend()
    ax_t.grid(True, alpha=0.3)

    plot_impulse_spectrum(u, dt=dt, db=True, floor_db=-100,
                          label="input |U(omega)|", ax=ax_f)
    plot_impulse_spectrum(Q[:, 0], dt=dt, db=True, floor_db=-100,
                          label="Q response (Q[:, 0])", ax=ax_f,
                          linestyle="--")
    ax_f.axvline(cutoff_hz, color="k", lw=0.8, ls="--",
                 label=f"input cutoff = {cutoff_hz} Hz")
    ax_f.legend()
    plt.tight_layout()


def example_signal_matched_q_wiener_vs_brickwall():
    """Same setup, comparing the brick-wall and Wiener shaping rules."""
    N, dt = 200, 0.01
    cutoff_hz = 8.0
    cutoff = hz_to_normalized(cutoff_hz, dt=dt)
    rng = np.random.default_rng(seed=0)
    u = random_bandlimited_vector(N=N, cutoff_cps=cutoff, rng=rng,
                                  target_peak=1.0)

    Q_brick = signal_matched_q(u, shape="brickwall", threshold=0.01)
    Q_wien = signal_matched_q(u, shape="wiener", alpha=0.05)

    fig, ax = plt.subplots(figsize=(8, 4))
    plot_impulse_spectrum(u, dt=dt, db=True, floor_db=-100,
                          label="input |U(omega)|", ax=ax)
    plot_impulse_spectrum(Q_brick[:, 0], dt=dt, db=True, floor_db=-100,
                          label="Q (brickwall)", ax=ax, linestyle="--")
    plot_impulse_spectrum(Q_wien[:, 0], dt=dt, db=True, floor_db=-100,
                          label="Q (wiener, alpha=0.05)", ax=ax,
                          linestyle=":")
    ax.axvline(cutoff_hz, color="k", lw=0.8, ls="--",
               label=f"cutoff = {cutoff_hz} Hz")
    ax.set_title("signal_matched_q: brickwall vs Wiener shaping")
    ax.legend()
    plt.tight_layout()


if __name__ == "__main__":
    vector = random_flat_spectrum_vector(N = 400)
    plt.plot(vector)
    plt.show()
