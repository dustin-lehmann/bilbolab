import dataclasses

import numpy as np
import matplotlib.pyplot as plt

from core.utils.control_lib.lib_control.learning.vector_generation import multisine_vector
from core.utils.data import generate_time_vector_by_length
from robots.bilbo.simulation.model import BILBO_Dynamics_3D, DEFAULT_BILBO_MODEL, \
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES, BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS, BilboModel


def offline_simulation_example():
    model = BilboModel(
        m_b=1.2,
        m_w=0.4,
        l=0.026,
        d_w=0.22,
        I_w=2e-4,
        I_y=0.005,
        I_x=0.02,
        I_z=0.03,
        c_alpha=4.6302e-4,
        r_w=0.06,
        tau_theta=0.2,
        tau_x=0.2,
        max_pitch=np.deg2rad(105)
    )

    bilbo_dynamics = BILBO_Dynamics_3D(model=model)
    bilbo_dynamics.eigenstructureAssignment(poles=BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
                                            eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS)

    u_l = np.concatenate([np.zeros(100), -0.25 * np.ones(500)])
    u_r = np.concatenate([np.zeros(100), -0.25 * np.ones(500)])

    u_l = multisine_vector(600, phase='random')
    u_r = multisine_vector(600, phase='random')

    # Combine the left/right channels into an N x 2 array. Each row [M_L, M_R]
    # is turned into a BILBO_3D_Input by simulate().
    u = np.column_stack([u_l, u_r])

    # BILBO_Dynamics_3D.simulate() returns (state_list, input_list).
    states, inputs = bilbo_dynamics.simulate(input=u, include_zero_step=False)
    time_vector = generate_time_vector_by_length(num_samples=len(states), dt=0.01, start=0)

    plot_simulation(time_vector, states, inputs)


def plot_simulation(time_vector, states, inputs):
    """Comprehensive plot of every BILBO_3D state and the applied motor input."""
    t = np.asarray(time_vector)

    # --- Collect every state channel individually ----------------------------
    x = np.array([s.x for s in states])
    y = np.array([s.y for s in states])
    v = np.array([s.v for s in states])
    theta = np.rad2deg([s.theta for s in states])
    theta_dot = np.rad2deg([s.theta_dot for s in states])
    psi = np.rad2deg([s.psi for s in states])
    psi_dot = np.rad2deg([s.psi_dot for s in states])

    # Applied input (post-feedback motor torques), shape (N, 2) -> M_L, M_R.
    inputs = np.asarray(inputs)

    # (axes title, y-data, y-label, line colour)
    panels = [
        ('x position', x, 'x [m]', 'tab:blue'),
        ('y position', y, 'y [m]', 'tab:blue'),
        ('Forward velocity', v, 'v [m/s]', 'tab:green'),
        ('Pitch angle', theta, r'$\theta$ [deg]', 'tab:red'),
        ('Pitch rate', theta_dot, r'$\dot{\theta}$ [deg/s]', 'tab:orange'),
        ('Yaw angle', psi, r'$\psi$ [deg]', 'tab:purple'),
        ('Yaw rate', psi_dot, r'$\dot{\psi}$ [deg/s]', 'tab:brown'),
    ]

    fig, axes = plt.subplots(4, 2, figsize=(13, 11), sharex=True)
    fig.suptitle('BILBO 3D — Offline Simulation', fontsize=14, fontweight='bold')
    axes = axes.ravel()

    for ax, (title, data, ylabel, color) in zip(axes, panels):
        ax.plot(t, data, color=color, linewidth=1.6)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
        ax.axhline(0.0, color='0.6', linewidth=0.8, zorder=0)

    # --- Last panel: the applied motor input --------------------------------
    ax_input = axes[7]
    ax_input.plot(t, inputs[:, 0], label=r'$M_L$', color='tab:cyan', linewidth=1.6)
    ax_input.plot(t, inputs[:, 1], label=r'$M_R$', color='tab:pink',
                  linewidth=1.6, linestyle='--')
    ax_input.set_title('Applied motor input', fontsize=10)
    ax_input.set_ylabel('M [Nm]')
    ax_input.grid(True, alpha=0.3)
    ax_input.axhline(0.0, color='0.6', linewidth=0.8, zorder=0)
    ax_input.legend(loc='best', fontsize=9)

    for ax in axes[6:]:
        ax.set_xlabel('time [s]')

    fig.tight_layout(rect=(0, 0, 1, 0.97))

    # --- Extra: XY trajectory in the plane ----------------------------------
    fig_xy, ax_xy = plt.subplots(figsize=(6, 6))
    ax_xy.plot(x, y, color='tab:blue', linewidth=1.6)
    ax_xy.scatter([x[0]], [y[0]], color='green', zorder=5, label='start')
    ax_xy.scatter([x[-1]], [y[-1]], color='red', zorder=5, label='end')
    ax_xy.set_title('XY trajectory')
    ax_xy.set_xlabel('x [m]')
    ax_xy.set_ylabel('y [m]')
    ax_xy.set_aspect('equal', adjustable='datalim')
    ax_xy.grid(True, alpha=0.3)
    ax_xy.legend(loc='best', fontsize=9)
    fig_xy.tight_layout()

    plt.show()


# === COST FUNCTION OVER THE COG HEIGHT l ==============================================================================
def _states_to_array(states):
    """Stack a list of State objects into an (N, n_states) array."""
    return np.array([s.asarray() for s in states])


def simulate_for_l(l, base_model, u, K):
    """Simulate the closed-loop BILBO dynamics for a single COG height `l`.

    The feedback gain `K` is passed in and held fixed — this mirrors a system
    identification setting, where the physical controller is fixed and only the
    plant parameter `l` is being fitted to the data.
    """
    model = dataclasses.replace(base_model, l=l)
    dynamics = BILBO_Dynamics_3D(model=model)
    dynamics.K = K
    states, _ = dynamics.simulate(input=u, include_zero_step=False)
    return states


def cost_l(l, reference_states, base_model, u, K):
    """Cost for a single value of `l`.

    Returns the Euclidean (2-)norm of the difference between the reference state
    trajectory and the trajectory simulated with the candidate COG height `l`.
    """
    sim_states = simulate_for_l(l, base_model, u, K)
    error = _states_to_array(reference_states) - _states_to_array(sim_states)
    return float(np.linalg.norm(error))


def plot_cost_over_l(reference_states, base_model, u, K, true_l=None):
    """Evaluate the cost J(l) for l in [0, 0.05] (step 0.001) and plot it."""
    l_values = np.arange(0.0, 0.05 + 1e-9, 0.001)
    costs = np.array([cost_l(l, reference_states, base_model, u, K) for l in l_values])

    # Diverged simulations produce inf/nan — drop them so the line just breaks.
    costs = np.where(np.isfinite(costs), costs, np.nan)
    l_best = l_values[np.nanargmin(costs)]
    j_best = np.nanmin(costs)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(l_values, costs, color='tab:blue', linewidth=1.8, label='J(l)')
    ax.scatter([l_best], [j_best], color='red', zorder=5,
               label=f'minimum (l = {l_best:.3f})')
    if true_l is not None:
        ax.axvline(true_l, color='green', linestyle='--', linewidth=1.2,
                   label=f'true l = {true_l:.3f}')

    ax.set_title(r'Cost  $J(l) = \|\, X_\mathrm{ref} - X_\mathrm{sim}(l)\,\|_2$')
    ax.set_xlabel('COG height  l [m]')
    ax.set_ylabel('cost  J(l)')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best', fontsize=9)
    fig.tight_layout()
    plt.show()


def simulate_for_lm(l, m_b, base_model, u, K):
    """Simulate the closed-loop BILBO dynamics for a single (l, m_b) pair,
    keeping the feedback gain `K` fixed. Returns the list of states."""
    model = dataclasses.replace(base_model, l=l, m_b=m_b)
    dynamics = BILBO_Dynamics_3D(model=model)
    dynamics.K = K
    states, _ = dynamics.simulate(input=u, include_zero_step=False)
    return states


def cost_lm(l, m_b, reference_states, base_model, u, K):
    """Cost for a single (l, m_b) pair: the 2-norm of the difference between the
    reference state trajectory and the trajectory simulated with (l, m_b)."""
    sim_states = simulate_for_lm(l, m_b, base_model, u, K)
    error = _states_to_array(reference_states) - _states_to_array(sim_states)
    return float(np.linalg.norm(error))


def plot_cost_2d(reference_states, base_model, u, K, true_l=None, true_m_b=None):
    """Evaluate the cost J(l, m_b) on a grid and plot it as a 2D map.

    l   in [0, 0.05] (step 0.001),  m_b in [0, 2] kg (step 0.04).
    """
    l_values = np.arange(0.0, 0.05 + 1e-9, 0.001)
    m_b_values = np.arange(0.0, 2.0 + 1e-9, 0.04)

    cost = np.full((len(m_b_values), len(l_values)), np.nan)
    for i, m_b in enumerate(m_b_values):
        for j, l in enumerate(l_values):
            cost[i, j] = cost_lm(l, m_b, reference_states, base_model, u, K)

    # Diverged simulations produce inf/nan — keep them out of the colour scale.
    cost = np.where(np.isfinite(cost), cost, np.nan)

    # Global minimum location.
    i_min, j_min = np.unravel_index(np.nanargmin(cost), cost.shape)
    l_best, m_b_best = l_values[j_min], m_b_values[i_min]

    # Huge dynamic range (≈0 at the optimum, ~1e3 far away) -> show log10(cost).
    log_cost = np.log10(np.clip(cost, 1e-4, None))
    grid_l, grid_m_b = np.meshgrid(l_values, m_b_values)

    fig, ax = plt.subplots(figsize=(9, 6))
    mesh = ax.pcolormesh(grid_l, grid_m_b, log_cost, cmap='viridis', shading='auto')
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label(r'$\log_{10}\, J(l, m_b)$')

    contours = ax.contour(grid_l, grid_m_b, log_cost, colors='white',
                          linewidths=0.6, alpha=0.6)
    ax.clabel(contours, inline=True, fontsize=7, fmt='%.0f')

    ax.scatter([l_best], [m_b_best], marker='x', s=90, color='red', linewidths=2,
               label=f'minimum (l={l_best:.3f}, m_b={m_b_best:.2f})')
    if true_l is not None and true_m_b is not None:
        ax.scatter([true_l], [true_m_b], marker='o', s=80, facecolors='none',
                   edgecolors='lime', linewidths=2,
                   label=f'true (l={true_l:.3f}, m_b={true_m_b:.2f})')

    ax.set_title(r'Cost  $J(l, m_b) = \|\, X_\mathrm{ref} - X_\mathrm{sim}\,\|_2$')
    ax.set_xlabel('COG height  l [m]')
    ax.set_ylabel(r'body mass  $m_b$ [kg]')
    ax.legend(loc='upper right', fontsize=8)
    fig.tight_layout()
    plt.show()


def cost_function_example():
    """Build a reference trajectory and plot the cost J(l, m_b)."""
    base_model = dataclasses.replace(DEFAULT_BILBO_MODEL, tau_theta=0.2, tau_x=0.2)
    true_l = 0.026
    true_m_b = base_model.m_b

    # Excitation input — the SAME signal must be used for the reference and for
    # every candidate simulation, otherwise the cost is not comparable.
    u_l = multisine_vector(600, phase='random')
    u_r = multisine_vector(600, phase='random')
    u = np.column_stack([u_l, u_r])

    # Design the (fixed) feedback controller and generate the reference data
    # using the true model.
    true_model = dataclasses.replace(base_model, l=true_l, m_b=true_m_b)
    reference_dynamics = BILBO_Dynamics_3D(model=true_model)
    K = reference_dynamics.eigenstructureAssignment(
        poles=BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
        eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS)
    reference_states, _ = reference_dynamics.simulate(input=u, include_zero_step=False)

    plot_cost_2d(reference_states, base_model, u, K, true_l=true_l, true_m_b=true_m_b)


if __name__ == '__main__':
    cost_function_example()
