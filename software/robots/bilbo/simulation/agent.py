import dataclasses
import math
import time
from typing import Callable

import numpy as np

from core.utils.logging_utils import Logger
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from robots.bilbo.simulation.model import (
    BILBO_DynamicAgent,
    BILBO_3D_Input,
    BILBO_3D_State,
    BilboModel,
    DEFAULT_BILBO_MODEL,
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS,
    DEFAULT_SAMPLE_TIME,
)
from robots.bilbo.simulation.position_control import (
    BILBO_PositionControl,
    PositionControlConfig,
    PathStartCommand,
)
from robots.bilbo.simulation.experiment import ExperimentRunner, ExperimentBuilder, ExperimentAction, load_experiment
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS
from core.utils.control_lib.lib_control.motion_planning import (
    plan_path,
    plan_path_prm,
    CircleObstacle,
    BoxObstacle,
    Bounds,
    Waypoint,
    PRMRoadmap,
    PRMConfig,
)

# Type alias for obstacles
Obstacle = CircleObstacle | BoxObstacle

# Planner selection
PLANNER_RRT = 'rrt'
PLANNER_PRM = 'prm'


# ======================================================================================================================
# Config dataclasses
# ======================================================================================================================

@dataclasses.dataclass
class VelocityCommand:
    v: float = 0.0
    psi_dot: float = 0.0


@dataclasses.dataclass
class VelocityControllerConfig:
    # Longitudinal velocity PID
    k_p_v: float = -0.179
    k_i_v: float = -0.8
    k_d_v: float = -0.005

    # Yaw rate (psi_dot) PID
    k_p_psi_dot: float = 0.35121
    k_i_psi_dot: float = 7.6256
    k_d_psi_dot: float = 0.0023

    # Integral limits
    k_integral_max_v: float = 10.0
    k_integral_max_psi_dot: float = 10.0


# ======================================================================================================================
# Helpers
# ======================================================================================================================

def _clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


# ======================================================================================================================
# BILBO_CompleteAgent
# ======================================================================================================================

class BILBO_CompleteAgent(BILBO_DynamicAgent):
    """Self-contained simulation agent with OFF/BALANCING/VELOCITY/POSITION modes.

    Extends BILBO_DynamicAgent with:
    - Velocity PID controller (v + psi_dot)
    - Firmware-style position control (outputs v_cmd, psi_dot_cmd)
    - Motion planning with RRT/PRM for obstacle avoidance

    Control hierarchy (matches firmware):
        Position Control -> (v_cmd, psi_dot_cmd)
            -> Velocity PID -> [u_l, u_r]
                -> Balancing (K @ state) -> Motor Torques
    """

    def __init__(
            self,
            agent_id: str,
            model: BilboModel = DEFAULT_BILBO_MODEL,
            Ts: float = DEFAULT_SAMPLE_TIME,
            x0: BILBO_3D_State | None = None,
            poles: list[float] | None = None,
            velocity_config: VelocityControllerConfig | None = None,
            position_config: PositionControlConfig | None = None,
    ):
        super().__init__(agent_id=agent_id, model=model, Ts=Ts, x0=x0)

        self.logger = Logger(f"BILBO_CompleteAgent {agent_id}", "DEBUG")

        # Eigenstructure assignment for balancing

        if poles is None:
            poles = BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES

        self.eigenstructureAssignment(
            poles=poles,
            eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS,
        )

        # Velocity controller
        self.velocity_command = VelocityCommand()
        self.velocity_controller_config = velocity_config or VelocityControllerConfig()
        self.velocity_controller_output = np.zeros(2, dtype=float)

        self._v_integral: float = 0.0
        self._v_last_error: float = 0.0
        self._psi_dot_integral: float = 0.0
        self._psi_dot_last_error: float = 0.0

        # Position controller (firmware-style)
        pos_cfg = position_config or PositionControlConfig(Ts=float(self.Ts))
        self._position_control = BILBO_PositionControl(config=pos_cfg)

        # Wire up position control callbacks
        self._position_control.on_path_finished = self._on_position_finished
        self._position_control.on_move_completed = self._on_position_finished
        self._position_control.on_turn_completed = self._on_position_finished

        # Obstacles and workspace bounds
        self._obstacles: list[Obstacle] = []
        self._bounds: Bounds | None = None

        # Path planning tuning
        self.planner: str = PLANNER_RRT  # Default planner: 'rrt' or 'prm'
        self.clearance_weight: float = 1.0
        self.clearance_threshold: float = 0.5

        # PRM roadmap (must be built before use)
        self._prm_roadmap: PRMRoadmap | None = None

        # Track position control idle transition
        self._position_control_was_idle: bool = True
        self._pending_heading: float | None = None

        # Navigation state machine
        self._nav_targets: list[list[float]] = []
        self._nav_target_idx: int = 0
        self._nav_active: bool = False
        self._nav_loop: bool = False
        self._nav_max_speed: float = 0.0
        self._nav_settling_time: float = 0.5
        self._nav_settling_start: float | None = None
        self._nav_started_current: bool = False
        self._nav_tick: int = 0

        # Navigation callbacks
        self.on_target_reached: Callable | None = None
        self.on_navigation_completed: Callable | None = None

        # Trajectory playback state
        self._trajectory_buffer: np.ndarray | None = None  # shape (N, 2): [u_left, u_right]
        self._trajectory_index: int = 0
        self.on_trajectory_finished: Callable | None = None

        # Experiment runner
        self._experiment: ExperimentRunner | None = None
        self.on_experiment_finished: Callable | None = None

        # Register LOGIC actions
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._experiment_step)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._navigation_step)

    # === PROPERTIES ===================================================================================================

    @property
    def position_control(self) -> BILBO_PositionControl:
        return self._position_control

    @property
    def obstacles(self) -> list[Obstacle]:
        return self._obstacles

    @property
    def bounds(self) -> Bounds | None:
        return self._bounds

    # === PUBLIC API ===================================================================================================

    def set_mode(self, mode: BILBO_Control_Mode):
        """Switch control mode and reset relevant controller state."""
        if mode == BILBO_Control_Mode.VELOCITY:
            self._reset_velocity_pid()
        elif mode == BILBO_Control_Mode.POSITION:
            self._position_control.reset()

        self.setMode(mode)
        self.logger.info(f"Mode set to {mode.name}")

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity(self, v: float, psi_dot: float):
        """Set the velocity command for VELOCITY mode."""
        self.velocity_command.v = v
        self.velocity_command.psi_dot = psi_dot

    # -- Obstacle management --

    def set_obstacles(self, obstacles: list[Obstacle]):
        """Replace all obstacles."""
        self._obstacles = list(obstacles)

    def add_obstacle(self, obstacle: Obstacle):
        """Add a single obstacle."""
        self._obstacles.append(obstacle)

    def clear_obstacles(self):
        """Remove all obstacles."""
        self._obstacles.clear()

    def set_bounds(self, bounds: Bounds | None):
        """Set workspace bounds."""
        self._bounds = bounds

    # -- PRM roadmap management --

    def build_prm(self, config: PRMConfig | None = None):
        """Build a PRM roadmap from the current obstacles and bounds.

        Must be called before using planner='prm'. The roadmap is static —
        rebuild if obstacles or bounds change.

        Args:
            config: PRM configuration. Uses defaults if not given.
        """
        if not self._obstacles and self._bounds is None:
            self.logger.error("build_prm: set obstacles and/or bounds first")
            return
        if self._bounds is None:
            self.logger.error("build_prm: bounds required for PRM")
            return

        cfg = config or PRMConfig(
            clearance_weight=self.clearance_weight,
            clearance_threshold=self.clearance_threshold,
        )
        self._prm_roadmap = PRMRoadmap(
            obstacles=self._obstacles, bounds=self._bounds, config=cfg)
        self._prm_roadmap.build()
        self.logger.info(f"PRM roadmap built: {self._prm_roadmap.node_count} nodes, "
                         f"{self._prm_roadmap.edge_count} edges")

    def set_prm_roadmap(self, roadmap: PRMRoadmap):
        """Set an externally built PRM roadmap."""
        self._prm_roadmap = roadmap

    @property
    def prm_roadmap(self) -> PRMRoadmap | None:
        return self._prm_roadmap

    # -- Position commands --

    def move_to_point(self, x: float, y: float, timeout: float = 0.0,
                      max_speed: float = 0.0,
                      target_heading: float | None = None,
                      heading_strength: float = 1.0,
                      planner: str | None = None):
        """Drive to a point. Uses path planning if obstacles are set.

        Args:
            x, y: Target position in world coordinates [m].
            timeout: Command timeout in seconds (0 = none).
            max_speed: Speed limit [m/s] (0 = use config default).
            target_heading: Desired heading at target [rad] (None = unconstrained).
            heading_strength: Strength of the heading constraint on the spline (default 1.0).
            planner: 'rrt' or 'prm'. None = use self.planner default.
        """
        self._position_control.reset()
        self._reset_velocity_pid()
        self._pending_heading = None

        if self._obstacles:
            start = (float(self.state.x), float(self.state.y))
            end = (float(x), float(y))
            path = self._plan_path(start, end, target_heading=target_heading,
                                   heading_strength=heading_strength, planner=planner)
            if path is None:
                self.logger.error("Path planning failed for move_to_point")
                return
            self._position_control.set_path(path)
            self._position_control.start_path(PathStartCommand(
                max_speed=max_speed, allow_reverse=False, timeout=timeout))
        else:
            self._position_control.move_to_point(
                x, y, timeout=timeout, max_speed=max_speed)

        if target_heading is not None:
            self._pending_heading = target_heading

        self._position_control_was_idle = False
        self.setMode(BILBO_Control_Mode.POSITION)

    # ------------------------------------------------------------------------------------------------------------------
    def turn_to_heading(self, psi: float, timeout: float = 0.0):
        """Turn in place to target heading."""
        self._position_control.reset()
        self._reset_velocity_pid()
        self._position_control.turn_to_heading(psi, timeout=timeout)
        self._position_control_was_idle = False
        self.setMode(BILBO_Control_Mode.POSITION)

    # ------------------------------------------------------------------------------------------------------------------
    def follow_path(self, waypoints: list[list[float]], max_speed: float = 0.0,
                    allow_reverse: bool = False, timeout: float = 0.0,
                    stop_indices: list[int] | None = None,
                    target_heading: float | None = None,
                    heading_strength: float = 1.0,
                    planner: str | None = None):
        """Follow a path through waypoints.

        If obstacles are set, uses motion planning to find a collision-free dense path.
        Otherwise, plans a direct dense path through the waypoints.

        Args:
            waypoints: List of [x, y] waypoints (at least 2)
            max_speed: Max speed override (0 = use config default)
            allow_reverse: Allow reverse driving
            timeout: Path timeout in seconds (0 = none)
            stop_indices: Indices into waypoints that are STOP points
            target_heading: Desired heading at final waypoint [rad] (None = unconstrained)
            heading_strength: Strength of the heading constraint on the spline (default 1.0).
            planner: 'rrt' or 'prm'. None = use self.planner default.
        """
        self._position_control.reset()
        self._reset_velocity_pid()

        if len(waypoints) < 2:
            self.logger.error("Need at least 2 waypoints")
            return

        start = (float(self.state.x), float(self.state.y))
        end = (float(waypoints[-1][0]), float(waypoints[-1][1]))

        # Build Waypoint objects for intermediate points
        intermediate = []
        for i, wp in enumerate(waypoints[:-1]):
            is_stop = (stop_indices is not None and i in stop_indices)
            intermediate.append(Waypoint(
                x=float(wp[0]), y=float(wp[1]), weight=0.8, stop=is_stop))

        path = self._plan_path(start, end,
                               waypoints=intermediate if intermediate else None,
                               target_heading=target_heading,
                               heading_strength=heading_strength,
                               planner=planner)
        if path is None:
            self.logger.error("Path planning failed for follow_path")
            return

        # Map stop waypoint indices to dense path indices
        dense_stop_indices = []
        if stop_indices:
            path_arr = np.array(path)
            for si in stop_indices:
                if si < len(waypoints):
                    wp = waypoints[si]
                    dists = np.hypot(path_arr[:, 0] - wp[0],
                                     path_arr[:, 1] - wp[1])
                    dense_stop_indices.append(int(np.argmin(dists)))

        self._position_control.set_path(
            path, stop_indices=dense_stop_indices if dense_stop_indices else None)
        self._position_control.start_path(PathStartCommand(
            max_speed=max_speed, allow_reverse=allow_reverse, timeout=timeout))
        self._position_control_was_idle = False
        self.setMode(BILBO_Control_Mode.POSITION)

    # -- Trajectory playback --

    def run_trajectory(self, trajectory, blocking: bool = False):
        """Run an open-loop input trajectory in BALANCING mode.

        Plays back a sequence of (u_left, u_right) torque commands at the
        simulation rate, matching the firmware sequencer behaviour. The
        balancing controller (LQR) stays active; the trajectory torques are
        added as feedforward inputs.

        Args:
            trajectory: One of:
                - InputTrajectory object (from experiment_definitions)
                - np.ndarray of shape (N, 2) with columns [u_left, u_right]
                - np.ndarray of shape (N,) for symmetric input (same torque both sides)
            blocking: If True, block until the trajectory finishes.
        """
        # Normalise to (N, 2) array
        if hasattr(trajectory, 'inputs'):
            # InputTrajectory object
            buf = np.array([[s.left, s.right] for s in trajectory.inputs],
                           dtype=float)
        else:
            buf = np.asarray(trajectory, dtype=float)
            if buf.ndim == 1:
                buf = np.column_stack([buf, buf])

        self._trajectory_buffer = buf
        self._trajectory_index = 0
        self.setMode(BILBO_Control_Mode.BALANCING)
        self.logger.info(f"Trajectory started ({len(buf)} samples)")

        if blocking:
            # Spin until finished (only works when env runs in a thread)
            while self._trajectory_buffer is not None:
                time.sleep(0.01)

    # ------------------------------------------------------------------------------------------------------------------
    def abort_trajectory(self):
        """Stop a running trajectory and zero the external input."""
        if self._trajectory_buffer is not None:
            self._trajectory_buffer = None
            self._trajectory_index = 0
            self.input = BILBO_3D_Input(M_L=0, M_R=0)
            self.logger.info("Trajectory aborted")

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def is_trajectory_running(self) -> bool:
        """True while a trajectory is being played back."""
        return self._trajectory_buffer is not None

    # -- Experiment handling --

    def run_experiment(self, experiment: list[ExperimentAction] | ExperimentBuilder,
                       blocking: bool = False):
        """Run a simulation experiment.

        Args:
            experiment: A list of ExperimentAction objects (from
                ExperimentBuilder.build()) or an ExperimentBuilder instance.
            blocking: If True, block until the experiment finishes.
        """
        if isinstance(experiment, ExperimentBuilder):
            actions = experiment.build()
        else:
            actions = experiment

        # Stop any active navigation / position control
        self.stop_navigation()
        self.abort_trajectory()
        self._position_control.reset()

        self._experiment = ExperimentRunner(self, actions)
        self._experiment.on_finished = self._on_experiment_finished
        self.logger.info(f"Experiment started ({len(actions)} actions)")

        if blocking:
            while self._experiment and not self._experiment.finished and not self._experiment.aborted:
                time.sleep(0.01)

    # ------------------------------------------------------------------------------------------------------------------
    def run_experiment_from_file(self, file: str, blocking: bool = False):
        """Load and run an experiment from a YAML or JSON file.

        Convenience wrapper around ``run_experiment(load_experiment(file))``.
        Supports the same format as the real robot's experiment YAML files,
        including .bitrj trajectory file references.

        Args:
            file: Path to the YAML/JSON experiment file.
            blocking: If True, block until the experiment finishes.
        """
        actions = load_experiment(file)
        self.run_experiment(actions, blocking=blocking)

    # ------------------------------------------------------------------------------------------------------------------
    def abort_experiment(self):
        """Stop a running experiment."""
        if self._experiment and not self._experiment.finished:
            self._experiment.abort()
            self._position_control.reset()
            self.abort_trajectory()
            self._experiment = None

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def is_experiment_running(self) -> bool:
        """True while an experiment is executing."""
        return self._experiment is not None and not self._experiment.finished

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_finished(self):
        if self.on_experiment_finished:
            self.on_experiment_finished()

    # ------------------------------------------------------------------------------------------------------------------
    def _experiment_step(self):
        """Called each LOGIC tick to advance the experiment runner."""
        if self._experiment and not self._experiment.finished:
            self._experiment.step()

    # ------------------------------------------------------------------------------------------------------------------
    def visit_points(self, targets: list[list[float]], max_speed: float = 0.35,
                     settling_time: float = 0.5, loop: bool = False,
                     planner: str | None = None):
        """Navigate through a sequence of target points.

        The agent moves to each target in order, waits for settling_time at each,
        then proceeds to the next. Obstacle avoidance is used automatically if
        obstacles are set.

        Args:
            targets: List of [x, y] target positions.
            max_speed: Maximum speed for each move.
            settling_time: Seconds to wait at each target before moving to the next.
            loop: If True, restart from the first target after the last.
            planner: 'rrt' or 'prm'. None = use self.planner default.
        """
        if len(targets) < 1:
            self.logger.error("visit_points: need at least 1 target")
            return

        self._nav_targets = [list(t) for t in targets]
        self._nav_target_idx = 0
        self._nav_active = True
        self._nav_loop = loop
        self._nav_max_speed = max_speed
        self._nav_settling_time = settling_time
        self._nav_settling_start = None
        self._nav_started_current = False
        self._nav_tick = 0
        self._nav_planner = planner

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def is_navigating(self) -> bool:
        """True while visit_points sequence is active."""
        return self._nav_active

    # ------------------------------------------------------------------------------------------------------------------
    def stop_navigation(self):
        """Stop any active position control and navigation sequence."""
        self._nav_active = False
        self._nav_started_current = False
        self._pending_heading = None
        self._position_control.reset()
        self.velocity_command = VelocityCommand()

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self, x0: BILBO_3D_State | None = None):
        """Full reset: state, velocity PID, position control, navigation, trajectory."""
        super().reset(x0 or BILBO_3D_State(0, 0, 0, 0, 0, 0, 0))
        self._reset_velocity_pid()
        self.velocity_command = VelocityCommand()
        self.velocity_controller_output = np.zeros(2, dtype=float)
        self._position_control.reset()
        self._pending_heading = None
        self._trajectory_buffer = None
        self._trajectory_index = 0
        self._experiment = None
        self._nav_active = False
        self._nav_started_current = False
        self._nav_tick = 0

    # === CONTROLLER (override) ========================================================================================

    def _controller(self) -> BILBO_3D_Input:
        if self.mode == BILBO_Control_Mode.OFF:
            controller_input = BILBO_3D_Input(M_L=0, M_R=0)

        elif self.mode == BILBO_Control_Mode.BALANCING:
            # Advance trajectory playback if active
            if self._trajectory_buffer is not None:
                idx = self._trajectory_index
                if idx < len(self._trajectory_buffer):
                    self.input = BILBO_3D_Input(
                        M_L=float(self._trajectory_buffer[idx, 0]),
                        M_R=float(self._trajectory_buffer[idx, 1]))
                    self._trajectory_index += 1
                else:
                    # Trajectory finished
                    self.input = BILBO_3D_Input(M_L=0, M_R=0)
                    self._trajectory_buffer = None
                    self._trajectory_index = 0
                    self.logger.info("Trajectory finished")
                    if self.on_trajectory_finished is not None:
                        self.on_trajectory_finished()

            controller_input = self.input.asarray() - self.K @ self.dynamics.state.asarray()

        elif self.mode == BILBO_Control_Mode.VELOCITY:
            self.velocity_controller_output = self._velocity_control()
            controller_input = (self.velocity_controller_output -
                                self.K @ self.dynamics.state.asarray())

        elif self.mode == BILBO_Control_Mode.POSITION:
            # Position control -> velocity commands -> velocity PID -> balancing
            state = self.dynamics.state

            # Chain a turn to heading after move/path completed
            if self._position_control.is_idle and self._pending_heading is not None:
                heading = self._pending_heading
                self._pending_heading = None
                self._position_control.turn_to_heading(heading)
                self._position_control_was_idle = False

            if self._position_control.is_idle:
                # Position control finished — pure balancing to hold position
                if not self._position_control_was_idle:
                    self.velocity_command = VelocityCommand()
                    self._reset_velocity_pid()
                    self._position_control_was_idle = True
                controller_input = (self.input.asarray() -
                                    self.K @ self.dynamics.state.asarray())
            else:
                self._position_control_was_idle = False
                pos_output = self._position_control.update(
                    x=float(state.x), y=float(state.y),
                    psi=float(state.psi), v=float(state.v))

                self.velocity_command.v = pos_output.v_cmd
                self.velocity_command.psi_dot = pos_output.psi_dot_cmd

                self.velocity_controller_output = self._velocity_control()
                controller_input = (self.velocity_controller_output -
                                    self.K @ self.dynamics.state.asarray())

        else:
            raise ValueError(f"Unknown mode: {self.mode}")

        return BILBO_3D_Input.as_state(controller_input)

    # === VELOCITY PID =================================================================================================

    def _velocity_control(self) -> np.ndarray:
        """PID on forward velocity v and yaw rate psi_dot -> [u_l, u_r]."""
        state = self.dynamics.state
        cfg = self.velocity_controller_config

        e_v = self.velocity_command.v - state.v
        e_psi_dot = self.velocity_command.psi_dot - state.psi_dot

        # Integrals
        self._v_integral += e_v * self.Ts
        self._psi_dot_integral += e_psi_dot * self.Ts

        # Derivatives
        e_v_dot = (e_v - self._v_last_error) / self.Ts
        self._v_last_error = e_v

        e_psi_dot_dot = (e_psi_dot - self._psi_dot_last_error) / self.Ts
        self._psi_dot_last_error = e_psi_dot

        # Saturate integrals
        self._v_integral = _clamp(self._v_integral,
                                  -cfg.k_integral_max_v, cfg.k_integral_max_v)
        self._psi_dot_integral = _clamp(self._psi_dot_integral,
                                        -cfg.k_integral_max_psi_dot,
                                        cfg.k_integral_max_psi_dot)

        # PID for v
        u_v = (cfg.k_p_v * e_v + cfg.k_i_v * self._v_integral +
               cfg.k_d_v * e_v_dot)

        # PID for psi_dot
        u_psi = (cfg.k_p_psi_dot * e_psi_dot +
                 cfg.k_i_psi_dot * self._psi_dot_integral +
                 cfg.k_d_psi_dot * e_psi_dot_dot)

        u_l = u_v - u_psi
        u_r = u_v + u_psi
        return np.asarray([u_l, u_r], dtype=float)

    # === PATH PLANNING ================================================================================================

    def _plan_path(self, start: tuple[float, float], end: tuple[float, float],
                   waypoints: list[Waypoint] | None = None,
                   target_heading: float | None = None,
                   heading_strength: float = 1.0,
                   planner: str | None = None,
                   ) -> list[tuple[float, float]] | None:
        """Plan a collision-free path using RRT* or PRM.

        Args:
            start: Start position (x, y).
            end: End position (x, y).
            waypoints: Intermediate waypoints.
            target_heading: Desired heading at end [rad].
            heading_strength: Strength of the heading constraint on the spline (default 1.0).
            planner: 'rrt' or 'prm'. None = use self.planner default.
        """
        use_planner = planner or self.planner

        try:
            if use_planner == PLANNER_PRM:
                if self._prm_roadmap is None or not self._prm_roadmap.is_built():
                    self.logger.warning("PRM roadmap not built, falling back to RRT")
                    use_planner = PLANNER_RRT
                else:
                    result = self._prm_roadmap.query(
                        start=start,
                        end=end,
                        waypoints=waypoints,
                        smoothing=0.8,
                        padding=0.05,
                        target_heading=target_heading,
                        heading_strength=heading_strength,
                    )
                    return result

            if use_planner == PLANNER_RRT:
                result = plan_path(
                    start=start,
                    end=end,
                    waypoints=waypoints,
                    obstacles=self._obstacles if self._obstacles else None,
                    bounds=self._bounds,
                    padding=0.05,
                    smoothing=0.8,
                    target_heading=target_heading,
                    heading_strength=heading_strength,
                    rrt_star=True,
                    clearance_weight=self.clearance_weight,
                    clearance_threshold=self.clearance_threshold,
                )
                if isinstance(result, list):
                    return result
                return result.path

        except Exception as e:
            self.logger.error(f"Path planning failed ({use_planner}): {e}")
            return None

    # === NAVIGATION STATE MACHINE =====================================================================================

    def _navigation_step(self):
        """Called each LOGIC tick. Advances the visit_points sequence."""
        if not self._nav_active:
            return

        self._nav_tick += 1

        # Start moving to the current target
        if not self._nav_started_current:
            target = self._nav_targets[self._nav_target_idx]
            tx, ty = target[0], target[1]
            heading = target[2] if len(target) >= 3 else None
            self.logger.info(f"Navigating to target {self._nav_target_idx}: "
                             f"({tx:.2f}, {ty:.2f})"
                             + (f", heading {heading:.2f}" if heading is not None else ""))
            self.move_to_point(tx, ty, max_speed=self._nav_max_speed,
                               target_heading=heading,
                               planner=getattr(self, '_nav_planner', None))
            self._nav_started_current = True
            self._nav_settling_start = None
            return

        # Wait for position control to finish
        if not self._position_control.is_idle:
            return

        # Settle at target
        t_sim = self._nav_tick * float(self.Ts)
        if self._nav_settling_start is None:
            self._nav_settling_start = t_sim
            return

        if t_sim - self._nav_settling_start < self._nav_settling_time:
            return

        # Target reached
        self.logger.info(f"Reached target {self._nav_target_idx}")
        if self.on_target_reached is not None:
            self.on_target_reached(self._nav_target_idx)

        # Advance to next target
        self._nav_target_idx += 1
        if self._nav_target_idx >= len(self._nav_targets):
            if self._nav_loop:
                self._nav_target_idx = 0
            else:
                self._nav_active = False
                self.logger.info("Navigation sequence completed")
                if self.on_navigation_completed is not None:
                    self.on_navigation_completed()
                return

        self._nav_started_current = False

    # === CALLBACKS ====================================================================================================

    def _on_position_finished(self):
        """Called when position control finishes its active command."""
        self.logger.info("Position control finished")

    # === INTERNAL HELPERS =============================================================================================

    def _reset_velocity_pid(self):
        self._v_integral = 0.0
        self._v_last_error = 0.0
        self._psi_dot_integral = 0.0
        self._psi_dot_last_error = 0.0
