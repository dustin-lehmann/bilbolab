"""Example: Two limbo bars with 0.3m spacing, guided kinodynamic RRT.

The robot must pass under two limbo bars at x=0.8 and x=1.1 (0.3m apart).
C-space obstacles block the forward-lean passage at both bars, forcing the
robot to find a backward-lean trajectory through both gaps.

This is a harder planning problem because the robot must maintain momentum
through two successive narrow passages.
"""

import numpy as np
import matplotlib.pyplot as plt

from robots.bilbo.simulation.model import DEFAULT_BILBO_MODEL
from robots.bilbo.utilities.dynamic_planning import (
    LimboPlanner, PlannerConfig, RobotGeometry, LimboRectangle,
    CSpaceConfig, CSpaceObstacle, GuidedKinodynamicRRTConfig,
)
from robots.bilbo.utilities.dynamic_planning.rrt_planner import RRTConfig
from robots.bilbo.utilities.dynamic_planning.visualization import (
    plot_scene, plot_cspace, plot_trajectory, animate,
)


def main():
    # --- Robot geometry ---
    geom = RobotGeometry(body_height=0.185, body_width=0.085, wheel_radius=0.06)

    # --- Two limbo bars, 0.3m apart ---
    x1 = 0.85
    x2 = x1 + 0.5
    clearance = 0.18
    bar_width = 0.02
    bar_height = 0.02

    bars = [
        # Physical obstacles
        LimboRectangle.from_clearance(x=x1, ground_clearance=clearance, width=bar_width, height=bar_height),
        LimboRectangle.from_clearance(x=x2, ground_clearance=clearance, width=bar_width, height=bar_height),
        # Block forward-lean passage at both bars
        # CSpaceObstacle(s_min=x1 - 0.1, s_max=x1 + 0.1, theta_min=0, theta_max=np.deg2rad(89)),
        # CSpaceObstacle(s_min=x2 - 0.1, s_max=x2 + 0.1, theta_min=0, theta_max=np.deg2rad(89)),
    ]

    # --- Planner config ---
    config = PlannerConfig(
        cspace=CSpaceConfig(
            s_range=(-0.3, 2.5),
            theta_range=(np.deg2rad(-89), np.deg2rad(89)),
            s_resolution=400,
            theta_resolution=400,
            safety_margin=0.015,
        ),
        rrt=GuidedKinodynamicRRTConfig(
            max_iterations=30000,
            extension_steps=20,
            goal_bias=0.15,
            u_max=3.0,
            goal_radius_s=0.1,
            goal_radius_theta=0.05,
            goal_v_max=0.5,
            goal_theta_dot_max=1.0,
            s_weight=1.0,
            v_weight=0.3,
            theta_weight=1.0,
            theta_dot_weight=0.1,
            settling_steps=100,
            seed=42,
            # Guide params
            guide_bias=0.05,
            guide_s_noise=0.15,
            guide_theta_noise=0.1,
            guide_rrt=RRTConfig(
                max_iterations=5000,
                step_size=0.06,
                goal_bias=0.15,
                goal_radius=0.04,
                s_weight=1.0,
                theta_weight=0.3,
                shortcut_iterations=300,
                seed=42,
            ),
        ),
        Ts=0.01,
        s_start=0.0,
        s_end=2.0,
    )

    # --- Plan ---
    planner = LimboPlanner(
        model=DEFAULT_BILBO_MODEL,
        geom=geom,
        bars=bars,
        config=config,
    )

    # Preview C-space (uncomment to inspect before planning)
    planner.show_cspace()

    # return
    print(f"Planning with {planner.config.rrt.max_iterations} iterations...")
    result = planner.plan()

    print(f"Kinodynamic RRT converged in {result.rrt_result.iterations_used} iterations")
    print(f"Tree nodes: {len(result.rrt_result.tree_nodes)}")
    print(f"Trajectory: {result.N} steps, {result.t[-1]:.1f}s")
    print(f"Max theta: {np.degrees(result.theta.max()):.1f} deg")
    print(f"Min theta: {np.degrees(result.theta.min()):.1f} deg")
    print(f"Max |v|:   {np.abs(result.v).max():.2f} m/s")

    # --- Collision check (physical obstacles only) ---
    from robots.bilbo.utilities.dynamic_planning.geometry import check_collision
    physical_bars = [b for b in bars if not isinstance(b, CSpaceObstacle)]
    collisions = 0
    for k in range(len(result.s)):
        for bar in physical_bars:
            if check_collision(result.s[k], result.theta[k], geom, bar):
                collisions += 1
                break
    print(f"Trajectory collisions: {collisions}/{len(result.s)}")

    # --- Plot C-space ---
    fig_cs, ax_cs = plt.subplots(figsize=(10, 7))
    plot_cspace(result, ax=ax_cs)

    # --- Plot physical scene ---
    scene = plot_scene(result)
    scene.show()

    # --- Plot trajectory time series ---
    plot_trajectory(result)

    # --- Animation ---
    anim = animate(result)

    plt.show()


if __name__ == '__main__':
    main()
