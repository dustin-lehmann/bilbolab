"""Top-level limbo passage planner combining C-space, RRT, and trajectory optimization."""

import dataclasses

import numpy as np

from robots.bilbo.simulation.model import (
    BilboModel, DEFAULT_BILBO_MODEL, BILBO_2D_POLES,
    BILBO_Dynamics_2D, BILBO_Dynamics_2D_Linear,
)
from .geometry import RobotGeometry, LimboBar, LimboRectangle, Obstacle
from .cspace import ConfigurationSpace, CSpaceConfig, CSpaceObstacle
from .rrt_planner import RRTPlanner, RRTConfig, RRTResult, path_to_trajectory
from .kinodynamic_rrt import (
    KinodynamicRRTPlanner, KinodynamicRRTConfig, KinodynamicRRTResult,
    refine_trajectory, smooth_trajectory, truncate_after_obstacles,
)
from .guided_kinodynamic_rrt import GuidedKinodynamicRRTPlanner, GuidedKinodynamicRRTConfig


@dataclasses.dataclass
class PlannerConfig:
    """Full planner configuration."""
    cspace: CSpaceConfig = dataclasses.field(default_factory=CSpaceConfig)
    rrt: KinodynamicRRTConfig = dataclasses.field(default_factory=KinodynamicRRTConfig)
    Ts: float = 0.01                # Sample time [s]
    poles: list | np.ndarray = dataclasses.field(default_factory=lambda: list(BILBO_2D_POLES))
    truncate: bool = True            # Truncate trajectory after obstacle clearance
    truncate_margin_steps: int = 50  # Steps to keep after last obstacle proximity
    truncate_settling_steps: int = 300  # Coast-to-rest steps after truncation
    smooth: bool = True              # Smooth u_ff away from obstacles (zero non-critical inputs)
    smooth_margin: float = 0.3      # s-distance beyond obstacle region to keep u_ff [m]
    smooth_taper_steps: int = 50    # Timesteps over which to taper u_ff to zero
    ilc_iterations: int = 0         # Number of ILC refinement iterations (0 = skip)
    ilc_r: float = 1e-4             # ILC input regularization weight
    ilc_s: float = 1e-2             # ILC robustness weight
    s_start: float = 0.0
    s_end: float = 2.0
    theta_start: float = 0.0
    theta_end: float = 0.0


@dataclasses.dataclass
class PlannerResult:
    """Full result of the limbo passage planning pipeline."""
    cspace: ConfigurationSpace
    rrt_result: KinodynamicRRTResult | RRTResult
    t: np.ndarray          # (N+1,) time vector
    x_ref: np.ndarray      # (N+1, 4) reference trajectory [s, v, theta, theta_dot]
    x_traj: np.ndarray     # (N+1, 4) simulated trajectory
    u_ff: np.ndarray       # (N,) feedforward inputs
    K: np.ndarray          # State feedback gain
    A_cl: np.ndarray       # Closed-loop A matrix
    B: np.ndarray           # Input B matrix (open-loop)
    config: PlannerConfig
    geom: RobotGeometry
    bars: list[Obstacle]

    @property
    def s(self) -> np.ndarray:
        return self.x_traj[:, 0]

    @property
    def v(self) -> np.ndarray:
        return self.x_traj[:, 1]

    @property
    def theta(self) -> np.ndarray:
        return self.x_traj[:, 2]

    @property
    def theta_dot(self) -> np.ndarray:
        return self.x_traj[:, 3]

    @property
    def Ts(self) -> float:
        return self.config.Ts

    @property
    def N(self) -> int:
        return len(self.u_ff)


class LimboPlanner:
    """Kinodynamic planner for BILBO limbo bar passage.

    Pipeline:
    1. Create stabilized dynamics via pole placement (linear + nonlinear)
    2. Build configuration space with obstacle occupancy
    3. Plan dynamically feasible trajectory with kinodynamic RRT
    4. Optionally refine via ILC (ilc_iterations > 0)
    """

    def __init__(self, model: BilboModel = None, geom: RobotGeometry = None,
                 bars: list[Obstacle | CSpaceObstacle] = None, config: PlannerConfig = None):
        if model is None:
            model = DEFAULT_BILBO_MODEL
        if geom is None:
            geom = RobotGeometry(body_height=0.185, body_width=0.085, wheel_radius=0.06)
        if bars is None:
            bars = []
        if config is None:
            config = PlannerConfig()

        # Separate physical obstacles from C-space obstacles
        physical = []
        for obs in bars:
            if isinstance(obs, CSpaceObstacle):
                config.cspace.obstacles.append(obs)
            else:
                physical.append(obs)

        self.model = model
        self.geom = geom
        self.bars = physical
        self.config = config

    def show_cspace(self):
        """Build and display the configuration space (blocking).

        Use this before plan() to visualize the obstacle regions and decide
        where to place CSpaceObstacle entries.
        """
        import matplotlib.pyplot as plt

        cfg = self.config
        cspace = ConfigurationSpace(self.geom, self.bars, config=cfg.cspace)

        ax = cspace.plot()

        # Mark start and goal
        ax.plot(cfg.s_start, np.degrees(cfg.theta_start), 'go', markersize=12,
                label='Start', zorder=20)
        ax.plot(cfg.s_end, np.degrees(cfg.theta_end), 'r*', markersize=15,
                label='Goal', zorder=20)
        ax.legend(loc='upper right', fontsize=8)

        plt.show()

    def plan(self) -> PlannerResult:
        """Run the full planning pipeline."""
        cfg = self.config

        # 1. Build stabilized dynamics
        # Linear model: for steering law and optional ILC
        dynamics_linear = BILBO_Dynamics_2D_Linear(self.model, Ts=cfg.Ts)
        K = dynamics_linear.polePlacement(cfg.poles, apply_poles_to_system=True)
        A_cl = np.array(dynamics_linear.system.A)
        B = np.array(dynamics_linear.system.B)

        # Nonlinear model: for dynamics simulation
        dynamics_nonlinear = BILBO_Dynamics_2D(self.model, Ts=cfg.Ts)
        dynamics_nonlinear.polePlacement(cfg.poles, apply_poles_to_system=True)

        # 2. Build configuration space
        cspace = ConfigurationSpace(self.geom, self.bars, config=cfg.cspace)

        # 3. Kinodynamic RRT planning (guided or unguided)
        start = (cfg.s_start, cfg.theta_start)
        goal = (cfg.s_end, cfg.theta_end)
        if isinstance(cfg.rrt, GuidedKinodynamicRRTConfig):
            rrt = GuidedKinodynamicRRTPlanner(cspace, dynamics_nonlinear, dynamics_linear,
                                               config=cfg.rrt)
        else:
            rrt = KinodynamicRRTPlanner(cspace, dynamics_nonlinear, dynamics_linear,
                                         config=cfg.rrt)
        rrt_result = rrt.plan(start, goal, Ts=cfg.Ts)

        if not rrt_result.success:
            raise RuntimeError(
                f"Kinodynamic RRT failed to find trajectory after "
                f"{rrt_result.iterations_used} iterations. "
                "Try increasing max_iterations or adjusting parameters."
            )

        # 3.5. Truncate trajectory after obstacle clearance
        if cfg.truncate:
            rrt_result = truncate_after_obstacles(
                rrt_result, dynamics_nonlinear, cspace,
                margin_steps=cfg.truncate_margin_steps,
                settling_steps=cfg.truncate_settling_steps,
            )

        # 4. Smooth u_ff away from obstacles
        if cfg.smooth:
            rrt_result = smooth_trajectory(
                rrt_result, dynamics_nonlinear, cspace,
                margin=cfg.smooth_margin,
                taper_steps=cfg.smooth_taper_steps,
            )

        # 5. Optional ILC refinement
        if cfg.ilc_iterations > 0:
            x_ref = rrt_result.x_traj.copy()
            x_traj, u_ff = refine_trajectory(
                rrt_result, dynamics_nonlinear, dynamics_linear,
                ilc_iterations=cfg.ilc_iterations,
                ilc_r=cfg.ilc_r,
                ilc_s=cfg.ilc_s,
            )
            t = rrt_result.t
        else:
            x_ref = rrt_result.x_traj.copy()
            x_traj = rrt_result.x_traj
            u_ff = rrt_result.u_ff
            t = rrt_result.t

        return PlannerResult(
            cspace=cspace,
            rrt_result=rrt_result,
            t=t,
            x_ref=x_ref,
            x_traj=x_traj,
            u_ff=u_ff,
            K=K,
            A_cl=A_cl,
            B=B,
            config=cfg,
            geom=self.geom,
            bars=self.bars,
        )
