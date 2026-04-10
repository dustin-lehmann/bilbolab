"""Velocity control tuning: step responses at various setpoints.

Tests the feedforward + PID velocity controller with different velocity
step commands to evaluate steady-state accuracy, transient response, and
the contribution of the feedforward vs. the integral correction.

Demonstrates auto_tune_velocity_ff() which computes the correct Kv from
the model dynamics and K matrix, so the FF handles steady-state and the
PID only corrects small residuals.

Run from the software/ directory:
    python robots/bilbo/simulation/examples/velocity_control_tuning.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

import numpy as np
import matplotlib.pyplot as plt

from robots.bilbo.simulation.agent import (
    BILBO_CompleteAgent,
    VelocityControllerConfig,
    FeedforwardConfig,
)
from robots.bilbo.simulation.model import BILBO_3D_State
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from simulation.objects.base_environment import BaseEnvironment
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS

# === Configuration ===
Ts = 0.01
DURATION = 20.0

# Velocity command schedule: (start_time_s, v_cmd, psi_dot_cmd)
COMMAND_SCHEDULE = [
    (0.0,  0.0,  0.0),
    (1.0,  0.15, 0.0),      # gentle forward
    (4.0,  0.0,  0.0),      # stop
    (5.0,  0.3,  0.0),      # medium forward
    (8.0,  0.0,  0.0),      # stop
    (9.0,  0.5,  0.0),      # fast forward
    (12.0, 0.0,  0.0),      # stop
    (13.0, -0.3, 0.0),      # reverse
    (16.0, 0.0,  0.0),      # stop
    (17.0, 0.3,  1.0),      # forward + turn
    (19.0, 0.0,  0.0),      # stop
]


def run_simulation(agent_label: str, agent: BILBO_CompleteAgent):
    """Run one simulation with the given agent and return recorded data."""
    agent.set_mode(BILBO_Control_Mode.VELOCITY)

    env = BaseEnvironment(Ts=Ts, run_mode='fast')
    env.addObject(agent)

    steps = int(DURATION / Ts)
    data = {
        't': [], 'v': [], 'psi_dot': [], 'theta': [],
        'x': [], 'y': [], 'psi': [],
        'v_cmd': [], 'psi_dot_cmd': [],
        'u_l': [], 'u_r': [],
    }

    schedule_idx = [0]
    current_cmd = [0.0, 0.0]

    def collect():
        t = env.scheduling.tick * Ts

        # Advance schedule
        while (schedule_idx[0] < len(COMMAND_SCHEDULE) - 1
               and t >= COMMAND_SCHEDULE[schedule_idx[0] + 1][0]):
            schedule_idx[0] += 1
        cmd = COMMAND_SCHEDULE[schedule_idx[0]]
        current_cmd[0], current_cmd[1] = cmd[1], cmd[2]
        agent.set_velocity(v=current_cmd[0], psi_dot=current_cmd[1])

        state = agent.state
        data['t'].append(t)
        data['v'].append(state.v)
        data['psi_dot'].append(state.psi_dot)
        data['theta'].append(state.theta)
        data['x'].append(state.x)
        data['y'].append(state.y)
        data['psi'].append(state.psi)
        data['v_cmd'].append(current_cmd[0])
        data['psi_dot_cmd'].append(current_cmd[1])
        data['u_l'].append(agent.velocity_controller_output[0])
        data['u_r'].append(agent.velocity_controller_output[1])

    env.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(collect)
    env.init()
    env.initialize()

    print(f"  Running '{agent_label}' ({DURATION}s, {steps} steps)...")
    env.start(steps=steps)

    # Convert to numpy
    for k in data:
        data[k] = np.array(data[k])
    data['label'] = agent_label
    return data


def make_agent(velocity_config: VelocityControllerConfig | None = None,
               auto_tune: bool = False,
               poles: list | None = None) -> BILBO_CompleteAgent:
    x0 = BILBO_3D_State(x=0, y=0, v=0, theta=0, theta_dot=0, psi=0, psi_dot=0)
    agent = BILBO_CompleteAgent(agent_id='bilbo1', Ts=Ts, x0=x0,
                                velocity_config=velocity_config,
                                poles=poles)
    if auto_tune:
        agent.auto_tune_velocity_ff()
    return agent


def main():
    # --- Define configurations to compare ---
    results = {}

    # 1) Auto-tuned FF + PID (recommended usage)
    results['auto-tuned FF + PID'] = run_simulation(
        'auto-tuned FF + PID',
        make_agent(auto_tune=True))

    # 2) Auto-tuned FF only — no PID, shows FF accuracy alone
    results['auto-tuned FF only'] = run_simulation(
        'auto-tuned FF only',
        make_agent(VelocityControllerConfig(
            k_p_v=0.0, k_i_v=0.0, k_d_v=0.0,
            k_p_psi_dot=0.0, k_i_psi_dot=0.0, k_d_psi_dot=0.0,
        ), auto_tune=True))

    # 3) PID only — no feedforward, shows slow integral wind-up
    results['PID only (no FF)'] = run_simulation(
        'PID only (no FF)',
        make_agent(VelocityControllerConfig(
            k_p_v=-0.179, k_i_v=-0.8, k_d_v=-0.005,
            ff_v=FeedforwardConfig(),
            k_p_psi_dot=0.35121, k_i_psi_dot=7.6256, k_d_psi_dot=0.0023,
            ff_psi_dot=FeedforwardConfig(),
        )))

    print("All simulations complete.\n")

    # --- Plot ---
    colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
    fig, axes = plt.subplots(5, 1, figsize=(12, 11), sharex=True)

    # Use the first result for the command reference
    ref = next(iter(results.values()))
    t_ref = ref['t']

    # Forward velocity
    ax = axes[0]
    ax.step(t_ref, ref['v_cmd'], 'k--', linewidth=1.5, label='v cmd', where='post')
    for i, (label, d) in enumerate(results.items()):
        ax.plot(d['t'], d['v'], color=colors[i % len(colors)], label=label)
    ax.set_ylabel('Forward velocity [m/s]')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.3)

    # Yaw rate
    ax = axes[1]
    ax.step(t_ref, ref['psi_dot_cmd'], 'k--', linewidth=1.5, label='ψ̇ cmd', where='post')
    for i, (label, d) in enumerate(results.items()):
        ax.plot(d['t'], d['psi_dot'], color=colors[i % len(colors)], label=label)
    ax.set_ylabel('Yaw rate [rad/s]')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.3)

    # Pitch angle
    ax = axes[2]
    for i, (label, d) in enumerate(results.items()):
        ax.plot(d['t'], np.degrees(d['theta']), color=colors[i % len(colors)], label=label)
    ax.set_ylabel('Pitch θ [deg]')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.3)

    # Controller output (u_forward = (u_l + u_r) / 2)
    ax = axes[3]
    for i, (label, d) in enumerate(results.items()):
        u_forward = (d['u_l'] + d['u_r']) / 2
        ax.plot(d['t'], u_forward, color=colors[i % len(colors)], label=label)
    ax.set_ylabel('u_forward')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.3)

    # Velocity tracking error
    ax = axes[4]
    for i, (label, d) in enumerate(results.items()):
        ax.plot(d['t'], d['v_cmd'] - d['v'], color=colors[i % len(colors)], label=label)
    ax.set_ylabel('v error [m/s]')
    ax.set_xlabel('Time [s]')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.suptitle('BILBO Velocity Control Tuning — Step Responses', fontsize=13)
    plt.tight_layout()
    plt.show()


if __name__ == '__main__':
    main()
