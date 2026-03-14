"""
BILBO 2D Nonlinear Dynamics with Unity-Gain Allpass Filter on Velocity Sensor

Simulates a step response of the BILBO 2D nonlinear dynamics stabilized via
pole placement. The velocity sensor is modeled as a first-order discrete-time
allpass filter: unity gain at all frequencies, but frequency-dependent phase shift.

The allpass-filtered v is fed back to the controller, while the true physical
dynamics integrates from the true state. This models a real sensor that measures
the correct amplitude but introduces phase distortion.

Allpass filter (first-order, discrete):

    H(z) = (z^{-1} - a) / (1 - a * z^{-1})

    Difference equation:  y[n] = -a * x[n] + x[n-1] + a * y[n-1]

    |H(e^{jw})| = 1 for all w (unity gain), but phase varies with frequency.
    Pole at z = a introduces phase lag; equivalent continuous-time pole at
    s = ln(a) / Ts.
"""

import copy
import os

import numpy as np
import matplotlib.gridspec as gridspec
from matplotlib import pyplot as plt

from robots.bilbo.simulation.model import (
    BILBO_Dynamics_2D,
    DEFAULT_BILBO_MODEL,
    BILBO_2D_POLES,
    BILBO_2D_State,
    BILBO_2D_Input,
)


class AllpassFilter:
    """First-order unity-gain allpass filter (discrete-time).

    H(z) = (z^{-1} - a) / (1 - a * z^{-1})

    Difference equation:  y[n] = -a * x[n] + x[n-1] + a * y[n-1]

    Parameters:
        a: Pole location on real axis (0 < a < 1). Larger values shift
           more phase at lower frequencies. The equivalent continuous-time
           pole is at s = ln(a) / Ts.
    """

    def __init__(self, a: float, x0: float = 0.0):
        self.a = a
        self.x_prev = x0
        self.y_prev = x0

    def step(self, x: float) -> float:
        y = -self.a * x + self.x_prev + self.a * self.y_prev
        self.x_prev = x
        self.y_prev = y
        return y

    def reset(self, x0: float = 0.0):
        self.x_prev = x0
        self.y_prev = x0


def simulate_with_allpass(model, Ts, K, u_ext, a_allpass):
    """Simulation with allpass sensor on velocity.

    The true dynamics integrates from the true physical state.
    The controller receives the allpass-filtered velocity measurement.

    Args:
        u_ext: External input array (length N).
    """
    dynamics = BILBO_Dynamics_2D(model=model, Ts=Ts)
    dynamics.K = None

    allpass = AllpassFilter(a=a_allpass, x0=0.0)
    x_true = copy.deepcopy(dynamics.x0)

    states_true = [copy.deepcopy(x_true)]
    v_meas_list = [0.0]

    for k in range(len(u_ext)):
        # Sensor: allpass on true velocity
        v_meas = allpass.step(x_true.v)
        v_meas_list.append(v_meas)

        # Controller sees measured v, true s/theta/theta_dot
        x_meas = np.array([x_true.s, v_meas, x_true.theta, x_true.theta_dot])
        u_total = u_ext[k] - (K @ x_meas).item()

        # Dynamics integrates from TRUE state
        dynamics.state = copy.deepcopy(x_true)
        dynamics.step(BILBO_2D_Input(M=u_total))
        x_true = copy.deepcopy(dynamics.state)

        states_true.append(copy.deepcopy(x_true))

    return states_true, v_meas_list


def simulate_nominal(model, Ts, K, u_ext):
    """Standard simulation without allpass (reference)."""
    dynamics = BILBO_Dynamics_2D(model=model, Ts=Ts)
    dynamics.setStateFeedbackControl(K.flatten())
    return dynamics.simulate(u_ext, reset=True, include_zero_step=True)


def main():
    Ts = 0.01
    u_step = 0.4
    a_allpass = 0.5

    N_pre = int(1.0 / Ts)   # 1 s of zero input
    N_step = int(4.0 / Ts)  # 4 s of step input
    N = N_pre + N_step

    u_ext = np.concatenate([np.zeros(N_pre), np.ones(N_step) * u_step])
    t = np.arange(N + 1) * Ts

    # --- Design controller via pole placement ---
    dynamics = BILBO_Dynamics_2D(model=DEFAULT_BILBO_MODEL, Ts=Ts)
    K = dynamics.polePlacement(poles=BILBO_2D_POLES, apply_poles_to_system=False)
    K_flat = K.flatten()

    print(f"Poles:              {BILBO_2D_POLES}")
    print(f"K (discrete):       {K_flat}")
    print(f"Allpass coeff a:    {a_allpass}")
    print(f"  equiv. cont. pole: s = {np.log(a_allpass) / Ts:.1f} rad/s")
    print(f"Step input u:       {u_step} Nm at t = {N_pre * Ts:.1f} s")

    # --- Simulate nominal (no allpass) ---
    states_nom = simulate_nominal(DEFAULT_BILBO_MODEL, Ts, K, u_ext)

    # --- Simulate with allpass on v ---
    states_ap, v_meas = simulate_with_allpass(
        DEFAULT_BILBO_MODEL, Ts, K_flat, u_ext, a_allpass
    )

    # --- Extract signals ---
    v_nom = np.array([s.v for s in states_nom])
    theta_nom = np.array([s.theta for s in states_nom])
    s_nom = np.array([s.s for s in states_nom])
    theta_dot_nom = np.array([s.theta_dot for s in states_nom])

    v_true = np.array([s.v for s in states_ap])
    v_meas = np.array(v_meas)
    theta_ap = np.array([s.theta for s in states_ap])
    s_ap = np.array([s.s for s in states_ap])
    theta_dot_ap = np.array([s.theta_dot for s in states_ap])

    # --- Plot 1: Full response ---
    fig, axes = plt.subplots(4, 1, figsize=(10, 10), sharex=True)

    fig.suptitle(
        f'BILBO 2D Nonlinear Step Response (u = {u_step} Nm at t = {N_pre * Ts:.0f} s)\n'
        f'Unity-gain allpass on velocity sensor (a = {a_allpass})',
        fontsize=13,
    )

    axes[0].plot(t, v_nom, 'b-', label='v nominal', linewidth=1.5)
    axes[0].plot(t, v_true, 'r-', label='v true (with allpass sensor)', linewidth=1.5)
    axes[0].plot(t, v_meas, 'r--', label='v measured (allpass output)', linewidth=1, alpha=0.7)
    axes[0].set_ylabel('v [m/s]')
    axes[0].legend()
    axes[0].grid(True)

    axes[1].plot(t, np.rad2deg(theta_nom), 'b-', label='θ nominal', linewidth=1.5)
    axes[1].plot(t, np.rad2deg(theta_ap), 'r-', label='θ with allpass sensor', linewidth=1.5)
    axes[1].set_ylabel('θ [deg]')
    axes[1].legend()
    axes[1].grid(True)

    axes[2].plot(t, theta_dot_nom, 'b-', label='θ̇ nominal', linewidth=1.5)
    axes[2].plot(t, theta_dot_ap, 'r-', label='θ̇ with allpass sensor', linewidth=1.5)
    axes[2].set_ylabel('θ̇ [rad/s]')
    axes[2].legend()
    axes[2].grid(True)

    axes[3].plot(t, s_nom, 'b-', label='s nominal', linewidth=1.5)
    axes[3].plot(t, s_ap, 'r-', label='s with allpass sensor', linewidth=1.5)
    axes[3].set_ylabel('s [m]')
    axes[3].set_xlabel('Time [s]')
    axes[3].legend()
    axes[3].grid(True)

    plt.tight_layout()

    # --- Plot 2: Zoomed transient around step at t=1s ---
    t_zoom_start = 0.5
    t_zoom_end = 1.5
    idx_start = int(t_zoom_start / Ts)
    idx_end = int(t_zoom_end / Ts) + 1
    t_zoom = t[idx_start:idx_end]

    fig2, ax2 = plt.subplots(4, 1, figsize=(10, 10), sharex=True)

    fig2.suptitle(
        f'Transient Zoom (t = {t_zoom_start} .. {t_zoom_end} s)\n'
        f'Unity-gain allpass on velocity sensor (a = {a_allpass})',
        fontsize=13,
    )

    ax2[0].plot(t_zoom, v_nom[idx_start:idx_end], 'b-', label='v nominal', linewidth=1.5)
    ax2[0].plot(t_zoom, v_true[idx_start:idx_end], 'r-', label='v true (with allpass sensor)', linewidth=1.5)
    ax2[0].plot(t_zoom, v_meas[idx_start:idx_end], 'r--', label='v measured (allpass output)', linewidth=1, alpha=0.7)
    ax2[0].axvline(N_pre * Ts, color='k', linestyle=':', linewidth=0.8, label='step onset')
    ax2[0].set_ylabel('v [m/s]')
    ax2[0].legend()
    ax2[0].grid(True)

    ax2[1].plot(t_zoom, np.rad2deg(theta_nom[idx_start:idx_end]), 'b-', label='θ nominal', linewidth=1.5)
    ax2[1].plot(t_zoom, np.rad2deg(theta_ap[idx_start:idx_end]), 'r-', label='θ with allpass sensor', linewidth=1.5)
    ax2[1].axvline(N_pre * Ts, color='k', linestyle=':', linewidth=0.8)
    ax2[1].set_ylabel('θ [deg]')
    ax2[1].legend()
    ax2[1].grid(True)

    ax2[2].plot(t_zoom, theta_dot_nom[idx_start:idx_end], 'b-', label='θ̇ nominal', linewidth=1.5)
    ax2[2].plot(t_zoom, theta_dot_ap[idx_start:idx_end], 'r-', label='θ̇ with allpass sensor', linewidth=1.5)
    ax2[2].axvline(N_pre * Ts, color='k', linestyle=':', linewidth=0.8)
    ax2[2].set_ylabel('θ̇ [rad/s]')
    ax2[2].legend()
    ax2[2].grid(True)

    ax2[3].plot(t_zoom, s_nom[idx_start:idx_end], 'b-', label='s nominal', linewidth=1.5)
    ax2[3].plot(t_zoom, s_ap[idx_start:idx_end], 'r-', label='s with allpass sensor', linewidth=1.5)
    ax2[3].axvline(N_pre * Ts, color='k', linestyle=':', linewidth=0.8)
    ax2[3].set_ylabel('s [m]')
    ax2[3].set_xlabel('Time [s]')
    ax2[3].legend()
    ax2[3].grid(True)

    plt.tight_layout()

    # --- Plot 3: Summary figure (v zoomed + small state plots) ---
    fig3 = plt.figure(figsize=(12, 8))
    gs = gridspec.GridSpec(2, 3, height_ratios=[3, 1], hspace=0.35, wspace=0.3,
                           left=0.08, right=0.97, top=0.90, bottom=0.08)

    ax_v = fig3.add_subplot(gs[0, :])
    t_z0, t_z1 = 0.5, 2.5
    iz = (t >= t_z0) & (t <= t_z1)
    ax_v.plot(t[iz], v_nom[iz], 'b-', label='v nominal', linewidth=2)
    ax_v.plot(t[iz], v_true[iz], 'r-', label='v true (allpass sensor)', linewidth=2)
    ax_v.plot(t[iz], v_meas[iz], 'r--', label='v measured (allpass out)', linewidth=1.2, alpha=0.7)
    ax_v.axvline(N_pre * Ts, color='0.4', linestyle=':', linewidth=1, label='step onset')
    ax_v.set_ylabel('v  [m/s]', fontsize=12)
    ax_v.set_xlabel('Time [s]', fontsize=11)
    ax_v.legend(fontsize=10, loc='upper right')
    ax_v.grid(True, alpha=0.4)
    ax_v.set_title(
        f'Velocity transient  —  allpass on v sensor (a = {a_allpass}),  step u = {u_step} Nm',
        fontsize=13, fontweight='bold',
    )

    ax_th = fig3.add_subplot(gs[1, 0])
    ax_th.plot(t, np.rad2deg(theta_nom), 'b-', linewidth=1.2, label='nominal')
    ax_th.plot(t, np.rad2deg(theta_ap), 'r-', linewidth=1.2, label='allpass')
    ax_th.axvline(N_pre * Ts, color='0.4', linestyle=':', linewidth=0.8)
    ax_th.set_ylabel(r'$\theta$ [deg]', fontsize=10)
    ax_th.set_xlabel('t [s]', fontsize=9)
    ax_th.legend(fontsize=8)
    ax_th.grid(True, alpha=0.3)
    ax_th.tick_params(labelsize=8)

    ax_td = fig3.add_subplot(gs[1, 1])
    ax_td.plot(t, theta_dot_nom, 'b-', linewidth=1.2, label='nominal')
    ax_td.plot(t, theta_dot_ap, 'r-', linewidth=1.2, label='allpass')
    ax_td.axvline(N_pre * Ts, color='0.4', linestyle=':', linewidth=0.8)
    ax_td.set_ylabel(r'$\dot{\theta}$ [rad/s]', fontsize=10)
    ax_td.set_xlabel('t [s]', fontsize=9)
    ax_td.legend(fontsize=8)
    ax_td.grid(True, alpha=0.3)
    ax_td.tick_params(labelsize=8)

    ax_s = fig3.add_subplot(gs[1, 2])
    ax_s.plot(t, s_nom, 'b-', linewidth=1.2, label='nominal')
    ax_s.plot(t, s_ap, 'r-', linewidth=1.2, label='allpass')
    ax_s.axvline(N_pre * Ts, color='0.4', linestyle=':', linewidth=0.8)
    ax_s.set_ylabel('s [m]', fontsize=10)
    ax_s.set_xlabel('t [s]', fontsize=9)
    ax_s.legend(fontsize=8)
    ax_s.grid(True, alpha=0.3)
    ax_s.tick_params(labelsize=8)

    png_path = os.path.expanduser('~/Desktop/bilbo_allpass_velocity_sensor.png')
    fig3.savefig(png_path, dpi=180)
    print(f"Summary saved to {png_path}")

    plt.show()


if __name__ == '__main__':
    main()
