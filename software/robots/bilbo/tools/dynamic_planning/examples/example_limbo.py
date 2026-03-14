"""Example: BILBO robot passing under a limbo bar.

The robot starts at s=0 upright and must reach s=2.0 upright.
A limbo bar at x=1.0 has ground clearance 0.19m, which is below the
robot's upright height of 0.245m (0.06m wheel + 0.185m body).
The robot must lean to pass underneath.

The planner uses a kinodynamic RRT that extends the tree via nonlinear
dynamics simulation, ensuring every trajectory is physically achievable.
This enables "backslide" maneuvers: driving fast toward the bar, leaning
backward while coasting through on forward momentum.
"""

import numpy as np
import matplotlib.pyplot as plt

from robots.bilbo.simulation.model import DEFAULT_BILBO_MODEL
from robots.bilbo.utilities.dynamic_planning import (
    LimboPlanner, PlannerConfig, RobotGeometry, LimboBar,
    CSpaceConfig, KinodynamicRRTConfig, LimboRectangle, CSpaceObstacle,
)
from robots.bilbo.utilities.dynamic_planning.visualization import (
    plot_scene, plot_cspace, plot_trajectory, animate,
)


def main():
    # --- Robot geometry ---
    geom = RobotGeometry(body_height=0.185, body_width=0.085, wheel_radius=0.06)

    # --- Limbo bar ---
    # Ground clearance 0.19m: robot height upright is 0.06 + 0.185 = 0.245m,
    # so the robot must lean to fit underneath.
    # bars = [LimboBar.from_clearance(x=1.0, ground_clearance=0.185, diameter=0.02)]
    bars = [LimboRectangle.from_clearance(x=1.0, ground_clearance=0.180, width=0.08, height=0.02),
            CSpaceObstacle(s_min=0.9, s_max=1.1, theta_min=0, theta_max=np.deg2rad(89))
            ]

    # --- Planner config ---
    config = PlannerConfig(
        cspace=CSpaceConfig(
            s_range=(-0.3, 2.3),
            theta_range=(np.deg2rad(-89), np.deg2rad(89)),
            s_resolution=400,
            theta_resolution=400,
            safety_margin=0.015,
        ),
        rrt=KinodynamicRRTConfig(
            max_iterations=20000,
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
    # --- Preview C-space (close window to continue with planning) ---
    # planner.show_cspace()

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
