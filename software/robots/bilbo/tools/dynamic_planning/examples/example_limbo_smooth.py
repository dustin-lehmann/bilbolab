"""Example: Trajectory smoothing for guided kinodynamic RRT.

Demonstrates the smooth_trajectory feature that eliminates unnecessary theta
oscillations before and after the obstacle region. The planner runs once, then
the result is shown both with and without smoothing for comparison.

With smooth=False (raw RRT output), the feedforward input u_ff is active over
the entire trajectory, causing small theta oscillations even far from obstacles.
With smooth=True, u_ff is tapered to zero outside the obstacle region, letting
the stabilizing controller produce clean driving in approach and departure.
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

    # --- Obstacles ---
    bars = [
        LimboRectangle.from_clearance(x=1.0, ground_clearance=0.2, width=0.02, height=0.02),
        CSpaceObstacle(s_min=0.9, s_max=1.1, theta_min=0, theta_max=np.deg2rad(89)),
    ]

    # --- Shared RRT config (same seed for reproducibility) ---
    rrt_config = GuidedKinodynamicRRTConfig(
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
        guide_bias=0.5,
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
    )

    cspace_config = CSpaceConfig(
        s_range=(-0.3, 2.3),
        theta_range=(np.deg2rad(-89), np.deg2rad(89)),
        s_resolution=400,
        theta_resolution=400,
        safety_margin=0.015,
    )

    # =====================================================================
    # Plan WITHOUT smoothing (raw RRT output)
    # =====================================================================
    print("=" * 60)
    print("Planning WITHOUT smoothing (raw RRT output)...")
    print("=" * 60)

    config_raw = PlannerConfig(
        cspace=cspace_config,
        rrt=rrt_config,
        Ts=0.01,
        s_start=0.0,
        s_end=2.0,
        smooth=False,  # <-- No smoothing
    )

    planner_raw = LimboPlanner(
        model=DEFAULT_BILBO_MODEL,
        geom=geom,
        bars=bars,
        config=config_raw,
    )
    result_raw = planner_raw.plan()

    print(f"  Converged in {result_raw.rrt_result.iterations_used} iterations")
    print(f"  Trajectory: {result_raw.N} steps, {result_raw.t[-1]:.1f}s")
    print(f"  Max |u_ff|: {np.abs(result_raw.u_ff).max():.2f} Nm")

    # =====================================================================
    # Plan WITH smoothing (same trajectory, smoothed u_ff)
    # =====================================================================
    print()
    print("=" * 60)
    print("Planning WITH smoothing...")
    print("=" * 60)

    config_smooth = PlannerConfig(
        cspace=cspace_config,
        rrt=rrt_config,
        Ts=0.01,
        s_start=0.0,
        s_end=2.0,
        smooth=True,              # <-- Enable smoothing
        smooth_margin=0.5,        # Keep u_ff active 0.3m beyond obstacle region
        smooth_taper_steps=50,    # Taper over 50 timesteps (cosine window)
    )

    planner_smooth = LimboPlanner(
        model=DEFAULT_BILBO_MODEL,
        geom=geom,
        bars=bars,
        config=config_smooth,
    )
    result_smooth = planner_smooth.plan()

    print(f"  Converged in {result_smooth.rrt_result.iterations_used} iterations")
    print(f"  Trajectory: {result_smooth.N} steps, {result_smooth.t[-1]:.1f}s")
    print(f"  Max |u_ff|: {np.abs(result_smooth.u_ff).max():.2f} Nm")

    # =====================================================================
    # Side-by-side comparison
    # =====================================================================
    fig, axes = plt.subplots(4, 2, figsize=(16, 12), sharex='row', sharey='row')
    fig.suptitle('Trajectory Smoothing Comparison', fontsize=14, fontweight='bold')

    for col, (result, label) in enumerate([(result_raw, 'Raw'), (result_smooth, 'Smoothed')]):
        t = result.t
        t_u = t[:-1]

        # s(t)
        axes[0, col].plot(t, result.s, '-', color='blue', linewidth=2)
        axes[0, col].set_ylabel('s [m]')
        axes[0, col].set_title(f'{label} trajectory')
        axes[0, col].grid(True, alpha=0.3)

        # theta(t)
        axes[1, col].plot(t, np.degrees(result.theta), '-', color='blue', linewidth=2)
        axes[1, col].set_ylabel('theta [deg]')
        axes[1, col].grid(True, alpha=0.3)

        # v(t)
        axes[2, col].plot(t, result.v, '-', color='blue', linewidth=2)
        axes[2, col].set_ylabel('v [m/s]')
        axes[2, col].grid(True, alpha=0.3)

        # u_ff(t)
        u_plot = result.u_ff.ravel() if result.u_ff.ndim > 1 else result.u_ff
        axes[3, col].plot(t_u, u_plot, '-', color='red', linewidth=1.5)
        axes[3, col].set_ylabel('u_ff [Nm]')
        axes[3, col].set_xlabel('t [s]')
        axes[3, col].grid(True, alpha=0.3)

    fig.tight_layout()

    # --- C-space plot for the smoothed result ---
    fig_cs, ax_cs = plt.subplots(figsize=(10, 7))
    plot_cspace(result_smooth, ax=ax_cs)
    ax_cs.set_title('C-Space (Smoothed Trajectory)')

    # --- Physical scene ---
    scene = plot_scene(result_smooth)
    scene.show()

    # --- Animation of smoothed result ---
    anim = animate(result_smooth)

    plt.show()


if __name__ == '__main__':
    main()
