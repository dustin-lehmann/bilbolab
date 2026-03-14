"""
Plot the sqrt deceleration law for v_cmd vs distance to target.

v_cmd = min(max_speed, sqrt(2 * decel_limit * d))

Compared to the linear fallback: v_cmd = min(max_speed, kp_linear * d)

Steady-state damping effect (assuming current_v ≈ v_cmd):
  v_cmd = sqrt(2 * a * d) / (1 + kd)
"""

import numpy as np
import matplotlib.pyplot as plt


if __name__ == '__main__':

    max_speed = 0.5  # m/s
    kp_linear = 1.0  # 1/s (default config value)
    kd_linear = 0.5  # [-] velocity damping (default config value)

    d = np.linspace(0, 1.5, 500)  # distance in meters

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # --- Left: vary decel_limit ---
    ax = axes[0]
    decel_limits = [0.1, 0.25, 0.5, 1.0, 2.0]
    colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(decel_limits)))

    for a, c in zip(decel_limits, colors):
        v_raw = np.minimum(max_speed, np.sqrt(2 * a * d))
        v_damped = np.minimum(max_speed, np.sqrt(2 * a * d) / (1 + kd_linear))
        ax.plot(d, v_raw, color=c, linewidth=2, label=f'a={a:.2f} m/s²')
        ax.plot(d, v_damped, color=c, linewidth=1, linestyle='--', alpha=0.6)

    # Linear fallback
    v_linear = np.minimum(max_speed, kp_linear * d)
    ax.plot(d, v_linear, 'k--', linewidth=1.5, label=f'linear kp={kp_linear}')

    ax.set_xlabel('Distance to target [m]')
    ax.set_ylabel('v_cmd [m/s]')
    ax.set_title(f'Vary decel_limit (solid=raw, dashed=with kd={kd_linear})')
    ax.set_xlim(0, d[-1])
    ax.set_ylim(0, max_speed * 1.1)
    ax.axhline(max_speed, color='gray', linestyle=':', linewidth=1, alpha=0.5)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # --- Right: vary kd for a fixed decel_limit ---
    ax = axes[1]
    a_fixed = 0.5
    kd_values = [0.0, 0.25, 0.5, 1.0, 2.0]
    colors2 = plt.cm.plasma(np.linspace(0.15, 0.85, len(kd_values)))

    for kd, c in zip(kd_values, colors2):
        v = np.minimum(max_speed, np.sqrt(2 * a_fixed * d) / (1 + kd))
        ax.plot(d, v, color=c, linewidth=2, label=f'kd={kd:.2f}')

    ax.set_xlabel('Distance to target [m]')
    ax.set_ylabel('v_cmd [m/s]')
    ax.set_title(f'Vary kd_linear (decel_limit={a_fixed} m/s²)')
    ax.set_xlim(0, d[-1])
    ax.set_ylim(0, max_speed * 1.1)
    ax.axhline(max_speed, color='gray', linestyle=':', linewidth=1, alpha=0.5)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.suptitle('$v_{cmd} = \\min\\left(v_{max},\\; \\frac{\\sqrt{2 \\cdot a \\cdot d}}{1 + k_d}\\right)$',
                 fontsize=13, y=1.02)
    plt.tight_layout()
    plt.show()
