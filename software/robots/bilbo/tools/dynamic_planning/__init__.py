"""
Kinodynamic motion planner for BILBO limbo bar passage.

This package implements trajectory optimization for a two-wheeled inverted
pendulum robot (BILBO) passing under limbo bar obstacles. The robot is
assumed to be stabilized by pole-placement state feedback (u = u_ff - K@x).
The planner optimizes the feedforward input u_ff(t) so the closed-loop
system produces a collision-free passage.

Key classes:
    LimboPlanner         - Trajectory optimization planner (see planner.py)
    PlannerConfig        - Configuration parameters
    PlannerResult        - Optimization result with full trajectory
    RobotGeometry        - Body geometry for collision checking
    LimboBar             - Obstacle definition
    ConfigurationSpace   - C-space computation and visualization (see cspace.py)
    RRTPlanner           - RRT path planner in C-space (see rrt_planner.py)
    RRTResult            - RRT planning result

Usage:
    from robots.bilbo.simulation.model import DEFAULT_BILBO_MODEL
    from robots.bilbo.utilities.kinodynamic_planner import (
        LimboPlanner, RobotGeometry, LimboBar, PlannerConfig
    )

    geom = RobotGeometry(body_height=0.185, body_width=0.085, wheel_radius=0.06)
    bars = [LimboBar.from_clearance(x=0.5, ground_clearance=0.22, diameter=0.02)]
    planner = LimboPlanner(DEFAULT_BILBO_MODEL, geom, bars)
    result = planner.plan()
"""

from .geometry import RobotGeometry, LimboBar, LimboRectangle, Obstacle
from .planner import LimboPlanner, PlannerConfig, PlannerResult
from .visualization import plot_trajectory, plot_scene, animate
from .cspace import ConfigurationSpace, CSpaceConfig, CSpaceObstacle
from .rrt_planner import RRTPlanner, RRTConfig, RRTResult, path_to_trajectory
from .kinodynamic_rrt import KinodynamicRRTPlanner, KinodynamicRRTConfig, KinodynamicRRTResult
from .guided_kinodynamic_rrt import GuidedKinodynamicRRTPlanner, GuidedKinodynamicRRTConfig
