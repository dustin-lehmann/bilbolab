"""
Visualize the stiction (Coulomb friction compensation) term of the velocity feedforward.

tau_c = Kc * tanh(v_ref / v0_stiction)

Shows how the stiction torque varies with commanded velocity for different v0_stiction values,
and how it varies for different Kc values.
"""

import numpy as np
import matplotlib.pyplot as plt


if __name__ == '__main__':

    # Default values from bilbo2_default.yaml / floor_roughness config
    Kc_default = -0.011  # kc_max from floor roughness config
    v0_default = 0.08    # v0_stiction from config

    v_cmd = np.linspace(-0.5, 0.5, 1000)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # --- Left plot: vary v0_stiction, fixed Kc ---
    ax = axes[0]
    v0_values = [0.02, 0.05, 0.08, 0.15, 0.30]
    for v0 in v0_values:
        tau_c = Kc_default * np.tanh(v_cmd / v0)
        label = f"v0 = {v0} m/s"
        if v0 == v0_default:
            label += " (config)"
        ax.plot(v_cmd, tau_c, label=label, linewidth=2 if v0 == v0_default else 1.2)

    ax.axhline(y=Kc_default, color='gray', linestyle='--', alpha=0.5, label=f'Kc = {Kc_default}')
    ax.axhline(y=-Kc_default, color='gray', linestyle='--', alpha=0.5)
    ax.axhline(y=0, color='black', linewidth=0.5)
    ax.axvline(x=0, color='black', linewidth=0.5)
    ax.set_xlabel('v_cmd [m/s]')
    ax.set_ylabel('tau_stiction [Nm]')
    ax.set_title(f'Stiction torque vs v_cmd (Kc = {Kc_default})')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # --- Right plot: vary Kc, fixed v0 ---
    ax = axes[1]
    Kc_values = [-0.005, -0.008, -0.011, -0.015, -0.020]
    for Kc in Kc_values:
        tau_c = Kc * np.tanh(v_cmd / v0_default)
        label = f"Kc = {Kc}"
        if Kc == Kc_default:
            label += " (config kc_max)"
        ax.plot(v_cmd, tau_c, label=label, linewidth=2 if Kc == Kc_default else 1.2)

    ax.axhline(y=0, color='black', linewidth=0.5)
    ax.axvline(x=0, color='black', linewidth=0.5)
    ax.set_xlabel('v_cmd [m/s]')
    ax.set_ylabel('tau_stiction [Nm]')
    ax.set_title(f'Stiction torque vs v_cmd (v0 = {v0_default} m/s)')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    fig.suptitle('Feedforward Stiction Term:  tau_c = Kc * tanh(v_cmd / v0)', fontsize=13, y=1.02)
    plt.tight_layout()
    plt.show()
