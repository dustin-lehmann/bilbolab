import os
import numpy as np
import matplotlib
if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
    matplotlib.use('Agg')
from matplotlib import pyplot as plt

from robots.bilbo.simulation.model import BILBO_Dynamics_2D, DEFAULT_BILBO_MODEL

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def simulate_with_K(K, N=500, Ts=0.01, u_amp=-1.0):
    """Simulate nonlinear BILBO 2D dynamics with a given K and step input."""
    dynamics = BILBO_Dynamics_2D(model=DEFAULT_BILBO_MODEL, Ts=Ts)
    dynamics.setStateFeedbackControl(K)

    u = np.ones(N) * u_amp
    states = dynamics.simulate(u)

    t = np.arange(len(states)) * Ts
    v = np.array([s.v for s in states])
    theta = np.array([s.theta for s in states])

    # Detect instability
    stable = not (np.any(np.abs(theta) > np.pi / 2) or np.any(np.abs(v) > 50))

    return t, v, theta, stable


def compute_v_overshoot(v):
    """Compute velocity overshoot percentage relative to steady-state."""
    n = len(v)
    v_ss = np.mean(v[int(0.9 * n):])

    if abs(v_ss) < 1e-10:
        return 0.0, v_ss

    # Peak in the direction of motion
    v_peak = np.min(v) if v_ss < 0 else np.max(v)
    overshoot_pct = (abs(v_peak) - abs(v_ss)) / abs(v_ss) * 100

    return overshoot_pct, v_ss


def main():
    N = 500
    Ts = 0.01
    u_amp = -1.0

    # --- Compute K for both pole sets ---
    good_poles = [0, -10, -5 + 3j, -5 - 3j]
    bad_poles = [0, -10, -5 + 7j, -5 - 7j]

    dynamics_tmp = BILBO_Dynamics_2D(model=DEFAULT_BILBO_MODEL, Ts=Ts)
    K_good = dynamics_tmp.polePlacement(poles=good_poles, apply_poles_to_system=False).flatten()
    K_bad = dynamics_tmp.polePlacement(poles=bad_poles, apply_poles_to_system=False).flatten()

    labels = ['K_s', 'K_v', 'K_theta', 'K_theta_dot']

    print("=" * 70)
    print("K gain comparison: good poles vs bad poles")
    print("=" * 70)
    print(f"Good poles: {good_poles}")
    print(f"Bad poles:  {bad_poles}")
    print()
    print(f"{'':>16} {'K_s':>10} {'K_v':>10} {'K_theta':>10} {'K_tdot':>10}")
    print("-" * 70)
    print(f"{'K_good':>16} {K_good[0]:>10.6f} {K_good[1]:>10.6f} {K_good[2]:>10.6f} {K_good[3]:>10.6f}")
    print(f"{'K_bad':>16} {K_bad[0]:>10.6f} {K_bad[1]:>10.6f} {K_bad[2]:>10.6f} {K_bad[3]:>10.6f}")
    print(f"{'Delta (bad-good)':>16} {K_bad[0]-K_good[0]:>+10.6f} {K_bad[1]-K_good[1]:>+10.6f} "
          f"{K_bad[2]-K_good[2]:>+10.6f} {K_bad[3]-K_good[3]:>+10.6f}")
    safe_ratio = np.where(np.abs(K_good) > 1e-10, K_bad / K_good, np.nan)
    print(f"{'Ratio bad/good':>16} {safe_ratio[0]:>10.3f} {safe_ratio[1]:>10.3f} "
          f"{safe_ratio[2]:>10.3f} {safe_ratio[3]:>10.3f}")
    print("=" * 70)

    # --- Figure 1: Good vs Bad poles comparison ---
    t_good, v_good, theta_good, _ = simulate_with_K(K_good, N, Ts, u_amp)
    t_bad, v_bad, theta_bad, _ = simulate_with_K(K_bad, N, Ts, u_amp)

    os_good, vss_good = compute_v_overshoot(v_good)
    os_bad, vss_bad = compute_v_overshoot(v_bad)

    fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax1.plot(t_good, v_good, 'C0', linewidth=2, label=f'Good poles (overshoot: {os_good:.1f}%)')
    ax1.plot(t_bad, v_bad, 'C3', linewidth=2, label=f'Bad poles (overshoot: {os_bad:.1f}%)')
    ax1.axhline(y=vss_good, color='C0', linestyle=':', alpha=0.4)
    ax1.axhline(y=vss_bad, color='C3', linestyle=':', alpha=0.4)
    ax1.set_ylabel('v [m/s]')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_title('Good vs Bad poles — step response comparison')

    ax2.plot(t_good, theta_good, 'C0', linewidth=2, label='Good poles')
    ax2.plot(t_bad, theta_bad, 'C3', linewidth=2, label='Bad poles')
    ax2.axhline(y=0, color='gray', linestyle=':', alpha=0.4)
    ax2.set_ylabel(r'$\theta$ [rad]')
    ax2.set_xlabel('Time [s]')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    fig1.tight_layout()
    fig1.savefig(os.path.join(SCRIPT_DIR, 'k_comparison_poles.png'), dpi=150, bbox_inches='tight')

    # --- Figure 2: Sensitivity analysis — vary each K gain ---
    K_baseline = K_good
    factors = [0.95, 0.975, 1.0, 1.25, 1.5]
    cmap = plt.cm.coolwarm
    cmap_vals = np.linspace(0.05, 0.95, len(factors))
    colors = [cmap(c) for c in cmap_vals]
    colors[len(factors) // 2] = (0.15, 0.15, 0.15, 1.0)  # baseline = black

    state_labels = [r'$K_s$', r'$K_v$', r'$K_\theta$', r'$K_{\dot{\theta}}$']

    fig2, axes = plt.subplots(3, 4, figsize=(20, 11),
                               gridspec_kw={'height_ratios': [2, 2, 1.2]})

    overshoot_table = np.full((len(factors), 4), np.nan)

    for col in range(4):
        ax_v = axes[0, col]
        ax_theta = axes[1, col]
        ax_bar = axes[2, col]

        bar_vals = []
        bar_labels_list = []

        for i, factor in enumerate(factors):
            K_mod = K_baseline.copy()
            K_mod[col] *= factor

            t, v, theta, stable = simulate_with_K(K_mod, N, Ts, u_amp)

            if not stable:
                # Find where instability starts and only plot up to there
                unstable_idx = np.argmax(np.abs(theta) > np.pi / 2)
                if unstable_idx == 0:
                    unstable_idx = len(t)
                t_plot, v_plot, theta_plot = t[:unstable_idx], v[:unstable_idx], theta[:unstable_idx]
                os_pct = np.nan
            else:
                t_plot, v_plot, theta_plot = t, v, theta
                os_pct, _ = compute_v_overshoot(v)

            overshoot_table[i, col] = os_pct
            bar_vals.append(os_pct)

            lw = 2.5 if factor == 1.0 else 1.2
            alpha = 1.0 if factor == 1.0 else 0.75
            label = f'{factor:.2f}x (K={K_mod[col]:.4f})'
            if not stable:
                label += ' UNSTABLE'

            ax_v.plot(t_plot, v_plot, color=colors[i], linewidth=lw, alpha=alpha, label=label)
            ax_theta.plot(t_plot, theta_plot, color=colors[i], linewidth=lw, alpha=alpha, label=label)

            bar_labels_list.append(f'{factor:.2f}x')

        # v steady state reference line from baseline
        _, v_base, _, _ = simulate_with_K(K_baseline, N, Ts, u_amp)
        v_ss_base = np.mean(v_base[int(0.9 * len(v_base)):])
        ax_v.axhline(y=v_ss_base, color='gray', linestyle=':', alpha=0.4, linewidth=0.8)

        # Style
        ax_v.set_title(f'Vary {state_labels[col]}', fontsize=13, fontweight='bold')
        ax_theta.set_xlabel('Time [s]')
        ax_v.grid(True, alpha=0.3)
        ax_theta.grid(True, alpha=0.3)
        ax_v.legend(fontsize=6.5, loc='best')
        ax_theta.axhline(y=0, color='gray', linestyle=':', alpha=0.4, linewidth=0.8)

        if col == 0:
            ax_v.set_ylabel('v [m/s]')
            ax_theta.set_ylabel(r'$\theta$ [rad]')
            ax_bar.set_ylabel('v overshoot [%]')

        # Overshoot bar chart
        bar_plot_vals = [v if not np.isnan(v) else 0 for v in bar_vals]
        bars = ax_bar.bar(bar_labels_list, bar_plot_vals, color=colors, edgecolor='white', linewidth=0.5)

        for bar, ov in zip(bars, bar_vals):
            txt = 'unstable' if np.isnan(ov) else f'{ov:.1f}%'
            y_pos = max(bar.get_height(), 0) + 0.5
            ax_bar.text(bar.get_x() + bar.get_width() / 2, y_pos,
                        txt, ha='center', va='bottom', fontsize=7, fontweight='bold')

        ax_bar.axhline(y=0, color='black', linewidth=0.5)
        ax_bar.grid(True, alpha=0.3, axis='y')
        ax_bar.set_xlabel(f'{state_labels[col]} multiplier')

    fig2.suptitle(f'K gain sensitivity — nonlinear step response (u = {u_amp} Nm)\n'
                  f'Baseline: poles {good_poles}   |   '
                  f'K = [{", ".join(f"{k:.4f}" for k in K_baseline)}]',
                  fontsize=13, fontweight='bold')
    fig2.tight_layout()
    fig2.savefig(os.path.join(SCRIPT_DIR, 'k_comparison_sensitivity.png'), dpi=150, bbox_inches='tight')

    # --- Print overshoot summary table ---
    print("\nOvershoot summary (v overshoot %):")
    print(f"{'Factor':<10}", end="")
    for name in labels:
        print(f"{name:>14}", end="")
    print()
    print("-" * 66)
    for i, factor in enumerate(factors):
        print(f"{factor:<10.2f}", end="")
        for col in range(4):
            val = overshoot_table[i, col]
            print(f"{'unstable':>14}" if np.isnan(val) else f"{val:>13.1f}%", end="")
        print()
    print()

    plt.show()


if __name__ == '__main__':
    main()
