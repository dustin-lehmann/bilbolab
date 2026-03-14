"""Example: Complete System Identification Pipeline for BILBO
=============================================================

Uses existing BILBO dynamics classes (bilbo_model.py) for:
  - Nonlinear simulation: BILBO_Dynamics_3D
  - Linearized model:     BILBO_Dynamics_3D_Linear
  - Controller synthesis:  eigenstructureAssignment

Then identifies both linear and nonlinear models from the simulated data.

Run from the software/ directory:
    python robots/bilbo/utilities/identification/example_identification.py

Or from the identification/ directory:
    python example_identification.py
"""

import os
import sys
import logging

# ── Path setup ────────────────────────────────────────────────────────────────
_this_dir = os.path.dirname(os.path.abspath(__file__))
_software_dir = os.path.abspath(os.path.join(_this_dir, '..', '..', '..', '..'))
for _p in [_software_dir, _this_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import matplotlib.pyplot as plt

# ── Existing BILBO model classes ──────────────────────────────────────────────
from robots.bilbo.simulation.model import (
    BilboModel, DEFAULT_BILBO_MODEL,
    BILBO_Dynamics_3D, BILBO_Dynamics_3D_Linear,
    BILBO_3D_State, BILBO_3D_Input,
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS,
)

# ── Identification modules ────────────────────────────────────────────────────
from system_identification import (
    TrajectoryData, IdentificationConfig, identify_system,
    simulate_linear, simulate_hybrid, print_model,
    IX, IY, IV, ITHETA, ITHETA_DOT, IPSI, IPSI_DOT,
    N_STATES, N_INPUTS, STATE_NAMES, INPUT_NAMES, DYNAMIC_ROWS,
)
from nonlinear_identification import (
    identify_nonlinear, NonlinearConfig, get_default_parameter_specs,
    simulate_nonlinear, bilbo_dynamics_3d,
    print_result, model_to_params, PARAM_NAMES,
)

logging.basicConfig(level=logging.INFO, format='%(message)s')

DT = 0.01
MODEL = DEFAULT_BILBO_MODEL
TRUE_PARAMS = model_to_params(MODEL)


# ===========================================================================
# Data generation using existing BILBO_Dynamics_3D
# ===========================================================================

def generate_trajectories(model, K, n_trajectories=30, T=800,
                          input_std=0.08, noise_std=0.001, seed=42,
                          max_theta=0.8):
    """Generate closed-loop trajectories using BILBO_Dynamics_3D.

    The dynamics internally compute u_actual = u_ext - K @ x.
    We store u_ext in the trajectory (what the identification needs).
    """
    rng = np.random.default_rng(seed)
    trajectories = []

    for _ in range(n_trajectories):
        dynamics = BILBO_Dynamics_3D(model=model, Ts=DT)
        dynamics.K = K

        x0 = BILBO_3D_State(
            x=0, y=0,
            v=rng.uniform(-0.3, 0.3),
            theta=rng.uniform(-0.5, 0.5),
            theta_dot=rng.uniform(-1.0, 1.0),
            psi=rng.uniform(-0.5, 0.5),
            psi_dot=rng.uniform(-0.5, 0.5),
        )
        dynamics.setState(x0)

        states_list = [dynamics.state.asarray().copy()]
        inputs_list = []

        for k in range(T - 1):
            u_ext = rng.normal(0, input_std, 2)
            inputs_list.append(u_ext)

            inp = BILBO_3D_Input(M_L=float(u_ext[0]), M_R=float(u_ext[1]))
            dynamics.step(inp)

            state_arr = dynamics.state.asarray()
            if abs(state_arr[ITHETA]) > max_theta or not np.all(np.isfinite(state_arr)):
                break
            states_list.append(state_arr.copy())

        if len(states_list) < 10:
            continue

        states = np.array(states_list)
        inputs = np.array(inputs_list)
        noisy_states = states + rng.normal(0, noise_std, states.shape)
        trajectories.append(TrajectoryData(states=noisy_states, inputs=inputs, dt=DT))

    return trajectories


# ===========================================================================
# Plotting
# ===========================================================================

def fig1_training_overview(train_data):
    """Sample training trajectories."""
    fig, axes = plt.subplots(3, 2, figsize=(12, 8), sharex='col')
    fig.suptitle('Training Data Overview (3 sample trajectories)',
                 fontsize=13, fontweight='bold')

    colors = ['#2196F3', '#FF5722', '#4CAF50']
    for i, traj in enumerate(train_data[:3]):
        t = np.arange(traj.T) * traj.dt
        t_u = np.arange(traj.inputs.shape[0]) * traj.dt
        c = colors[i]
        lbl = f'Traj {i + 1}'
        axes[0, 0].plot(t, traj.states[:, ITHETA], color=c, alpha=0.8, label=lbl)
        axes[0, 1].plot(t, traj.states[:, IV], color=c, alpha=0.8)
        axes[1, 0].plot(t, traj.states[:, ITHETA_DOT], color=c, alpha=0.8)
        axes[1, 1].plot(t, traj.states[:, IPSI_DOT], color=c, alpha=0.8)
        axes[2, 0].plot(t_u, traj.inputs[:, 0], color=c, alpha=0.6, linewidth=0.7)
        axes[2, 1].plot(traj.states[:, IX], traj.states[:, IY], color=c, alpha=0.8)

    axes[0, 0].set_ylabel(r'$\theta$ [rad]')
    axes[0, 1].set_ylabel('v [m/s]')
    axes[1, 0].set_ylabel(r'$\dot{\theta}$ [rad/s]')
    axes[1, 1].set_ylabel(r'$\dot{\psi}$ [rad/s]')
    axes[2, 0].set_ylabel(r'$u_\mathrm{ext,L}$ [Nm]')
    axes[2, 0].set_xlabel('Time [s]')
    axes[2, 1].set_xlabel('x [m]')
    axes[2, 1].set_ylabel('y [m]')
    axes[2, 1].set_aspect('equal')
    axes[0, 0].legend(fontsize=8, loc='upper right')
    fig.tight_layout()
    return fig


def fig2_rollout_comparison(test_data, lin_result, nl_result, K):
    """Multi-step rollout: Actual vs Linear vs Hybrid vs Nonlinear."""
    traj = test_data[0]
    n_steps = min(500, traj.T - 1)
    x0 = traj.states[0]
    u_seg = traj.inputs[:n_steps]
    actual = traj.states[:n_steps + 1]

    pred_lin = simulate_linear(lin_result, x0, u_seg)
    pred_hyb = simulate_hybrid(lin_result, x0, u_seg)
    pred_nl = simulate_nonlinear(nl_result.params, x0, u_seg, K, DT)

    # Clip nonlinear at first NaN
    valid_nl = n_steps + 1
    for k in range(n_steps + 1):
        if not np.all(np.isfinite(pred_nl[k])):
            valid_nl = k
            break

    t = np.arange(n_steps + 1) * DT

    fig, axes = plt.subplots(4, 2, figsize=(14, 10), sharex='col')
    fig.suptitle(
        f'Model Comparison \u2014 {n_steps}-step ({n_steps * DT:.1f}s) Rollout',
        fontsize=13, fontweight='bold',
    )

    specs = [
        (0, 0, ITHETA,     r'$\theta$ [rad]'),
        (0, 1, IV,          'v [m/s]'),
        (1, 0, ITHETA_DOT, r'$\dot{\theta}$ [rad/s]'),
        (1, 1, IPSI_DOT,   r'$\dot{\psi}$ [rad/s]'),
        (2, 0, IX,          'x [m]'),
        (2, 1, IY,          'y [m]'),
        (3, 0, IPSI,        r'$\psi$ [rad]'),
    ]

    for r, c, idx, label in specs:
        ax = axes[r, c]
        ax.plot(t, actual[:, idx], 'k-', lw=1.5, label='Actual (NL truth)')
        ax.plot(t, pred_lin[:, idx], '#2196F3', ls='--', lw=1.0, alpha=0.85,
                label='Linear')
        ax.plot(t, pred_hyb[:, idx], '#FF9800', ls='--', lw=1.0, alpha=0.85,
                label='Hybrid (lin dyn + NL kin)')
        ax.plot(t[:valid_nl], pred_nl[:valid_nl, idx], '#F44336', ls='-.',
                lw=1.0, alpha=0.85, label='Nonlinear (identified)')
        ax.set_ylabel(label)
        if r == 0 and c == 0:
            ax.legend(fontsize=7, loc='best')

    # XY path
    ax = axes[3, 1]
    ax.plot(actual[:, IX], actual[:, IY], 'k-', lw=1.5, label='Actual')
    ax.plot(pred_lin[:, IX], pred_lin[:, IY], '#2196F3', ls='--', lw=1.0,
            alpha=0.85, label='Linear')
    ax.plot(pred_hyb[:, IX], pred_hyb[:, IY], '#FF9800', ls='--', lw=1.0,
            alpha=0.85, label='Hybrid')
    ax.plot(pred_nl[:valid_nl, IX], pred_nl[:valid_nl, IY], '#F44336',
            ls='-.', lw=1.0, alpha=0.85, label='Nonlinear')
    ax.set_xlabel('x [m]')
    ax.set_ylabel('y [m]')
    ax.set_aspect('equal')
    ax.legend(fontsize=7)

    for c in range(2):
        axes[-1, c].set_xlabel('Time [s]')
    fig.tight_layout()

    # RMSE table
    vl = min(valid_nl, n_steps + 1)
    print(f"\n  {n_steps}-step rollout RMSE (over {vl} valid steps):")
    print(f"  {'State':>12s}  {'Linear':>12s}  {'Hybrid':>12s}  {'Nonlinear':>12s}")
    for i, name in enumerate(STATE_NAMES):
        rmse_l = np.sqrt(np.mean((actual[:vl, i] - pred_lin[:vl, i])**2))
        rmse_h = np.sqrt(np.mean((actual[:vl, i] - pred_hyb[:vl, i])**2))
        rmse_n = np.sqrt(np.mean((actual[:vl, i] - pred_nl[:vl, i])**2))
        print(f"  {name:>12s}  {rmse_l:12.2e}  {rmse_h:12.2e}  {rmse_n:12.2e}")

    return fig


def fig3_parameter_comparison(nl_result, true_params):
    """Bar chart: true vs estimated parameters."""
    free = nl_result.free_params
    if not free:
        return None

    true_vals = np.array([true_params[n] for n in free])
    est_vals = np.array([nl_result.params[n] for n in free])

    x = np.arange(len(free))
    w = 0.35

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7),
                                    gridspec_kw={'height_ratios': [2, 1]})
    fig.suptitle('Nonlinear Identification \u2014 Parameter Recovery',
                 fontsize=13, fontweight='bold')

    ax1.bar(x - w/2, true_vals, w, label='True', color='#2196F3',
            alpha=0.8, edgecolor='white')
    ax1.bar(x + w/2, est_vals, w, label='Estimated', color='#FF5722',
            alpha=0.8, edgecolor='white')
    ax1.set_xticks(x)
    ax1.set_xticklabels(free, fontsize=9)
    ax1.set_ylabel('Value')
    ax1.legend(fontsize=9)
    ax1.set_title('Absolute Parameter Values', fontsize=11)

    rel_err = np.array([
        abs(e - t) / abs(t) * 100 if abs(t) > 1e-12 else 0
        for t, e in zip(true_vals, est_vals)
    ])
    bar_colors = ['#4CAF50' if r < 5 else '#FF9800' if r < 20 else '#F44336'
                  for r in rel_err]
    bars = ax2.bar(x, rel_err, 0.6, color=bar_colors, alpha=0.85,
                   edgecolor='white')
    ax2.set_xticks(x)
    ax2.set_xticklabels(free, fontsize=9)
    ax2.set_ylabel('Relative Error [%]')
    ax2.set_title('Estimation Error', fontsize=11)
    ax2.axhline(y=5, color='#9E9E9E', ls='--', alpha=0.6, label='5% threshold')
    ax2.legend(fontsize=8)
    for bar, err in zip(bars, rel_err):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 f'{err:.1f}%', ha='center', va='bottom', fontsize=8)

    fig.tight_layout()
    return fig


def fig4_one_step_derivatives(test_data, lin_result, nl_result, K):
    """Scatter: observed vs predicted one-step derivatives."""
    s_k_l, s_kp1_l, u_k_l = [], [], []
    for traj in test_data:
        T = min(traj.T, traj.inputs.shape[0])
        s_k_l.append(traj.states[:T-1])
        s_kp1_l.append(traj.states[1:T])
        u_k_l.append(traj.inputs[:T-1])
    s_k = np.vstack(s_k_l)
    s_kp1 = np.vstack(s_kp1_l)
    u_ext = np.vstack(u_k_l)

    mask = np.abs(s_k[:, ITHETA]) <= 1.0
    s_k, s_kp1, u_ext = s_k[mask], s_kp1[mask], u_ext[mask]

    s_dot_obs = (s_kp1 - s_k) / DT

    # Linear
    A_cl = lin_result.A_d_cl
    s_kp1_lin = (A_cl @ s_k.T).T + (lin_result.B_d @ u_ext.T).T + lin_result.bias
    s_dot_lin = (s_kp1_lin - s_k) / DT

    # Nonlinear
    u_actual = u_ext - (K @ s_k.T).T
    s_dot_nl = bilbo_dynamics_3d(s_k, u_actual, nl_result.params)

    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    fig.suptitle('One-Step Derivative Prediction (test data)',
                 fontsize=13, fontweight='bold')

    deriv_specs = [
        (IV,         r'$\dot{v}$ [m/s$^2$]'),
        (ITHETA_DOT, r'$\ddot{\theta}$ [rad/s$^2$]'),
        (IPSI_DOT,   r'$\ddot{\psi}$ [rad/s$^2$]'),
    ]

    for col, (idx, label) in enumerate(deriv_specs):
        obs = s_dot_obs[:, idx]
        ss_tot = np.sum((obs - obs.mean())**2)

        # Linear (top)
        ax = axes[0, col]
        pred = s_dot_lin[:, idx]
        ax.scatter(obs, pred, s=1.5, alpha=0.25, color='#2196F3', rasterized=True)
        lims = [min(obs.min(), pred.min()), max(obs.max(), pred.max())]
        m = (lims[1] - lims[0]) * 0.05
        lims = [lims[0]-m, lims[1]+m]
        ax.plot(lims, lims, 'k--', lw=0.8, alpha=0.5)
        r2 = 1 - np.sum((obs-pred)**2)/ss_tot if ss_tot > 1e-12 else 0
        ax.set_title(f'Linear \u2014 {label}\nR\u00b2 = {r2:.6f}', fontsize=10)
        ax.set_xlim(lims); ax.set_ylim(lims)
        if col == 0: ax.set_ylabel('Predicted')

        # Nonlinear (bottom)
        ax = axes[1, col]
        pred_nl = s_dot_nl[:, idx]
        ax.scatter(obs, pred_nl, s=1.5, alpha=0.25, color='#FF5722', rasterized=True)
        lims2 = [min(obs.min(), pred_nl.min()), max(obs.max(), pred_nl.max())]
        m2 = (lims2[1]-lims2[0])*0.05
        lims2 = [lims2[0]-m2, lims2[1]+m2]
        ax.plot(lims2, lims2, 'k--', lw=0.8, alpha=0.5)
        r2n = 1 - np.sum((obs-pred_nl)**2)/ss_tot if ss_tot > 1e-12 else 0
        ax.set_title(f'Nonlinear \u2014 {label}\nR\u00b2 = {r2n:.6f}', fontsize=10)
        ax.set_xlabel('Observed')
        ax.set_xlim(lims2); ax.set_ylim(lims2)
        if col == 0: ax.set_ylabel('Predicted')

    fig.tight_layout()
    return fig


# ===========================================================================
# Main pipeline
# ===========================================================================

def main():
    print("=" * 72)
    print("  BILBO System Identification \u2014 Complete Example")
    print("=" * 72)

    # ── Step 1: Create nonlinear dynamics and design controller ───────────
    print("\n[Step 1] Setting up BILBO_Dynamics_3D and controller...")
    dynamics = BILBO_Dynamics_3D(model=MODEL, Ts=DT)
    K = dynamics.eigenstructureAssignment(
        poles=BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
        eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS,
    )
    print(f"  K shape: {K.shape}")
    print(f"  K_theta  = {K[0, ITHETA]:.6f} (per wheel)")
    print(f"  K_v      = {K[0, IV]:.6f}")
    print(f"  K_tdot   = {K[0, ITHETA_DOT]:.6f}")
    print(f"  K_psidot = {K[0, IPSI_DOT]:.6f} / {K[1, IPSI_DOT]:.6f}")

    # Show the existing linear model for reference
    linear = BILBO_Dynamics_3D_Linear(model=MODEL, Ts=DT)
    A_d_zoh = np.array(linear.system.A)
    B_d_zoh = np.array(linear.system.B)
    print(f"\n  Reference: existing linear model (ZOH-discretized)")
    print(f"  A_d[theta_dot, theta] = {A_d_zoh[ITHETA_DOT, ITHETA]:.6f}")
    print(f"  B_d[theta_dot, u_l]   = {B_d_zoh[ITHETA_DOT, 0]:.6f}")
    print(f"  Note: BILBO_Dynamics_3D uses Euler integration, so our")
    print(f"  identified A_d will match the Euler version, not ZOH.")

    # ── Step 2: Generate training data ───────────────────────────────────
    print("\n[Step 2] Generating training data from BILBO_Dynamics_3D...")
    train_data = generate_trajectories(
        MODEL, K, n_trajectories=30, T=800,
        input_std=0.3, noise_std=0.001, seed=42, max_theta=1.2,
    )
    n_train = sum(t.T for t in train_data)
    print(f"  {len(train_data)} trajectories, {n_train} total samples")

    # ── Step 3a: Linear identification ───────────────────────────────────
    print("\n" + "=" * 72)
    print("[Step 3a] Linear System Identification")
    print("=" * 72)
    lin_config = IdentificationConfig(alpha=1e-3, theta_max=0.5)
    lin_result = identify_system(train_data, lin_config, K=K)
    print_model(lin_result)

    # ── Step 3b: Nonlinear identification ────────────────────────────────
    print("\n" + "=" * 72)
    print("[Step 3b] Nonlinear Parameter Estimation")
    print("=" * 72)
    specs = get_default_parameter_specs()

    # Perturb initial guesses away from truth
    specs['l'].value = 0.04
    specs['I_y'].value = 0.01
    specs['I_x'].value = 0.015
    specs['I_z'].value = 0.025
    specs['I_w'].value = 3e-4
    specs['c_alpha'].value = 5e-4
    specs['tau_theta'].value = 0.2
    specs['tau_x'].value = 0.6

    print("\nInitial guesses (perturbed from truth):")
    for name in PARAM_NAMES:
        if not specs[name].fixed:
            err_pct = abs(specs[name].value - TRUE_PARAMS[name]) / TRUE_PARAMS[name] * 100
            print(f"  {name:>12s}: {specs[name].value:.6g} "
                  f"(true: {TRUE_PARAMS[name]:.6g}, {err_pct:.0f}% off)")

    nl_config = NonlinearConfig(theta_max=1.0, verbose=1)
    nl_result = identify_nonlinear(train_data, specs, K, nl_config)
    print_result(nl_result, true_params=TRUE_PARAMS)

    # ── Step 4: Generate test data ───────────────────────────────────────
    print("\n" + "=" * 72)
    print("[Step 4] Validation on New Test Trajectories")
    print("=" * 72)
    test_data = generate_trajectories(
        MODEL, K, n_trajectories=5, T=1000,
        input_std=0.25, noise_std=0.0005, seed=999, max_theta=1.2,
    )
    n_test = sum(t.T for t in test_data)
    print(f"  {len(test_data)} test trajectories, {n_test} total samples")
    print("  (different seed, different initial conditions, lower noise)")

    # ── Step 5: Create plots ─────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("[Step 5] Creating Plots")
    print("=" * 72)

    plt.rcParams.update({
        'font.size': 10,
        'axes.grid': True,
        'grid.alpha': 0.3,
        'figure.facecolor': 'white',
    })

    fig1_training_overview(train_data)
    fig2_rollout_comparison(test_data, lin_result, nl_result, K)
    fig3_parameter_comparison(nl_result, TRUE_PARAMS)
    fig4_one_step_derivatives(test_data, lin_result, nl_result, K)

    print("\n" + "=" * 72)
    print("  Done! Close plot windows to exit.")
    print("=" * 72)
    plt.show()


if __name__ == '__main__':
    main()
