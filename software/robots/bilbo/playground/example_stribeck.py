"""
Visualize the current stiction model vs a Stribeck-like decay model.

Current:   tau_c = Kc * tanh(v / v0)
Proposed:  tau_c = Kc * tanh(v / v0) * exp(-|v| / v_decay)

Shows the total feedforward (Kv*v + stiction) for both approaches.
"""

import numpy as np
import matplotlib.pyplot as plt

if __name__ == '__main__':

    # Config values
    Kv = -0.25
    Kc = -0.011
    v0 = 0.08

    v_cmd = np.linspace(-0.5, 0.5, 1000)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # ---- Top left: stiction term only, current vs Stribeck for different v_decay ----
    ax = axes[0, 0]
    tau_current = Kc * np.tanh(v_cmd / v0)
    ax.plot(v_cmd, tau_current, 'k--', linewidth=2, label='Current: tanh only')

    v_decay_values = [0.05, 0.10, 0.20, 0.40]
    for vd in v_decay_values:
        tau_stribeck = Kc * np.tanh(v_cmd / v0) * np.exp(-np.abs(v_cmd) / vd)
        ax.plot(v_cmd, tau_stribeck, linewidth=1.5, label=f'Stribeck, v_decay = {vd} m/s')

    ax.axhline(y=0, color='black', linewidth=0.5)
    ax.axvline(x=0, color='black', linewidth=0.5)
    ax.set_xlabel('v_cmd [m/s]')
    ax.set_ylabel('tau_stiction [Nm]')
    ax.set_title('Stiction term only')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # ---- Top right: total feedforward (Kv*v + stiction), current vs Stribeck ----
    ax = axes[0, 1]
    tau_ff_no_stiction = Kv * v_cmd
    tau_ff_current = Kv * v_cmd + Kc * np.tanh(v_cmd / v0)

    ax.plot(v_cmd, tau_ff_no_stiction, 'gray', linewidth=1, label='Kv*v only (no stiction)')
    ax.plot(v_cmd, tau_ff_current, 'k--', linewidth=2, label='Current: Kv*v + tanh')

    for vd in [0.10, 0.20]:
        tau_stribeck = Kc * np.tanh(v_cmd / v0) * np.exp(-np.abs(v_cmd) / vd)
        tau_ff_stribeck = Kv * v_cmd + tau_stribeck
        ax.plot(v_cmd, tau_ff_stribeck, linewidth=1.5, label=f'Stribeck, v_decay = {vd} m/s')

    ax.axhline(y=0, color='black', linewidth=0.5)
    ax.axvline(x=0, color='black', linewidth=0.5)
    ax.set_xlabel('v_cmd [m/s]')
    ax.set_ylabel('tau_ff total [Nm]')
    ax.set_title('Total feedforward: Kv*v + stiction')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # ---- Bottom left: relative contribution of stiction to total FF ----
    ax = axes[1, 0]
    v_pos = np.linspace(0.01, 0.5, 500)

    stiction_current = np.abs(Kc * np.tanh(v_pos / v0))
    total_current = np.abs(Kv * v_pos) + stiction_current
    ratio_current = stiction_current / total_current * 100

    ax.plot(v_pos, ratio_current, 'k--', linewidth=2, label='Current: tanh only')

    for vd in [0.10, 0.20]:
        stiction_stribeck = np.abs(Kc * np.tanh(v_pos / v0) * np.exp(-v_pos / vd))
        total_stribeck = np.abs(Kv * v_pos) + stiction_stribeck
        ratio_stribeck = stiction_stribeck / total_stribeck * 100
        ax.plot(v_pos, ratio_stribeck, linewidth=1.5, label=f'Stribeck, v_decay = {vd} m/s')

    ax.set_xlabel('v_cmd [m/s]')
    ax.set_ylabel('Stiction contribution [%]')
    ax.set_title('Stiction as % of total feedforward')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # ---- Bottom right: stiction term zoomed into low-speed region ----
    ax = axes[1, 1]
    v_zoom = np.linspace(-0.15, 0.15, 500)

    tau_current_zoom = Kc * np.tanh(v_zoom / v0)
    ax.plot(v_zoom, tau_current_zoom, 'k--', linewidth=2, label='Current: tanh only')

    for vd in [0.10, 0.20]:
        tau_stribeck_zoom = Kc * np.tanh(v_zoom / v0) * np.exp(-np.abs(v_zoom) / vd)
        ax.plot(v_zoom, tau_stribeck_zoom, linewidth=1.5, label=f'Stribeck, v_decay = {vd} m/s')

    ax.axhline(y=0, color='black', linewidth=0.5)
    ax.axvline(x=0, color='black', linewidth=0.5)
    ax.axvline(x=v0, color='orange', linewidth=0.8, linestyle=':', label=f'v0 = {v0} m/s')
    ax.axvline(x=-v0, color='orange', linewidth=0.8, linestyle=':')
    ax.set_xlabel('v_cmd [m/s]')
    ax.set_ylabel('tau_stiction [Nm]')
    ax.set_title('Stiction term — low-speed zoom')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    fig.suptitle(f'Current vs Stribeck stiction model  (Kv={Kv}, Kc={Kc}, v0={v0} m/s)', fontsize=13)
    plt.tight_layout()
    plt.show()
