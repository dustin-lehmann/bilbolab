"""
BILBO-specific experiment actions for the new experiment framework.

All actions expect a 'robot' context object (the BILBO instance) to be
registered with the ExperimentRunner:

    runner.initialize(context_objects={'robot': bilbo})

Actions are organized by category:
  - Control       : mode, gains, PID, feedforward, config
  - Navigation    : move_to, turn_to, follow_path, planner config
  - Drive         : velocity, direct input
  - Trajectory    : run pre-computed input trajectory
  - Estimation    : tracking enable/disable
  - Audio / IO    : beep, speak, LED, marker
  - Input         : external input enable/disable
  - Testbed       : obstacles, environment
"""
from __future__ import annotations
import copy
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar, TYPE_CHECKING

from core.utils.experiments.types import ActionResult, ActionParameterDef
from core.utils.experiments.action import ActionBase, ActionContext, ActionRegistry
from core.utils.experiments.guard import GuardBase, GuardContext, GuardRegistry
from robot.control.bilbo_control_definitions import BILBO_Control_Mode
from core.utils.events import wait_for_events, TIMEOUT as EV_TIMEOUT

if TYPE_CHECKING:
    from robot.bilbo import BILBO


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_robot(context: ActionContext | RequirementContext) -> BILBO:
    """Get the BILBO robot instance from context."""
    robot = context.runner.get_context_object('robot')
    if robot is None:
        raise RuntimeError("No 'robot' context object registered with ExperimentRunner")
    return robot


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROL
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SetModeAction(ActionBase):
    """Change the robot's control mode."""
    type_id: ClassVar[str] = 'set_mode'

    @dataclass
    class Params:
        mode: str  # OFF, DIRECT, BALANCING, VELOCITY, POSITION

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        mode = BILBO_Control_Mode[params.mode] if isinstance(params.mode, str) else params.mode
        robot.control.set_mode(mode)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetFeedbackGainAction(ActionBase):
    """Set the LQR state feedback gain vector K."""
    type_id: ClassVar[str] = 'set_feedback_gain'

    @dataclass
    class Params:
        K: list  # 8-element gain vector

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.control.set_statefeedback_gain(params.K)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetTICAction(ActionBase):
    """Enable/disable theta integral control (pitch drift compensation)."""
    type_id: ClassVar[str] = 'set_tic'

    @dataclass
    class Params:
        enabled: bool = True

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.control.enable_tic_control(params.enabled)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetVICAction(ActionBase):
    """Enable/disable velocity integral control."""
    type_id: ClassVar[str] = 'set_vic'

    @dataclass
    class Params:
        enabled: bool = True

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.control.enable_vic_control(params.enabled)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetPSIControlAction(ActionBase):
    """Enable/disable psi (yaw/heading) control."""
    type_id: ClassVar[str] = 'set_psi_control'

    @dataclass
    class Params:
        enabled: bool = True

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.control.enable_psi_control(params.enabled)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetPSISetpointAction(ActionBase):
    """Set the yaw/heading setpoint for PSI control."""
    type_id: ClassVar[str] = 'set_psi_setpoint'

    @dataclass
    class Params:
        psi: float = 0.0  # Target heading [rad]

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.control.set_psi_setpoint(params.psi)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class ResetControlAction(ActionBase):
    """Reload control parameters from the default config file."""
    type_id: ClassVar[str] = 'reset_control'

    def execute(self, context: ActionContext) -> ActionResult:
        robot = _get_robot(context)
        robot.control.load_and_set_default_config()
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class LoadControlConfigAction(ActionBase):
    """Load a control configuration by name or from a file.

    Use ``name`` to load from configs/control/ (deep-merged on top of default).
    Use ``file`` to reference a YAML file relative to the experiment YAML on the
    host — the host resolves and inlines it as ``config`` before sending.
    """
    type_id: ClassVar[str] = 'load_control_config'

    @dataclass
    class Params:
        name: str = None    # Config name (matches filename in configs/control/)
        file: str = None    # Relative path to YAML file (resolved by host, arrives as 'config')
        config: dict = None  # Inlined config dict (set by host after resolving 'file')

    def execute(self, context: ActionContext) -> ActionResult:
        from robot.control.bilbo_control_config import load_config_from_dict

        params = self.get_params(context)
        robot = _get_robot(context)

        if params.config is not None:
            config = load_config_from_dict(params.config)
        elif params.name is not None:
            config = robot.control.load_config(params.name)
        else:
            context.fail("Either 'name' or 'file' must be specified")
            return ActionResult.ERROR

        if config is None:
            context.fail("Failed to load control config")
            return ActionResult.ERROR

        robot.control.set_config(config)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetVelocityPIDAction(ActionBase):
    """Set forward velocity PID gains."""
    type_id: ClassVar[str] = 'set_velocity_pid'

    @dataclass
    class Params:
        Kp: float = None
        Ki: float = None
        Kd: float = None

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        config = {k: v for k, v in {'Kp': params.Kp, 'Ki': params.Ki, 'Kd': params.Kd}.items() if v is not None}
        robot.control.set_forward_velocity_pid_config(config)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetTurnPIDAction(ActionBase):
    """Set turn rate (psidot) PID gains."""
    type_id: ClassVar[str] = 'set_turn_pid'

    @dataclass
    class Params:
        Kp: float = None
        Ki: float = None
        Kd: float = None

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        config = {k: v for k, v in {'Kp': params.Kp, 'Ki': params.Ki, 'Kd': params.Kd}.items() if v is not None}
        robot.control.set_turn_velocity_pid_config(config)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetVelocityFeedforwardAction(ActionBase):
    """Set forward velocity feedforward parameters."""
    type_id: ClassVar[str] = 'set_velocity_feedforward'

    @dataclass
    class Params:
        Kv: float = None
        Ka: float = None
        Kc: float = None
        enable_stiction: bool = None
        v0_stiction: float = None
        v_decay_stiction: float = None

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        config = {k: v for k, v in {
            'Kv': params.Kv, 'Ka': params.Ka, 'Kc': params.Kc,
            'enable_stiction': params.enable_stiction,
            'v0_stiction': params.v0_stiction,
            'v_decay_stiction': params.v_decay_stiction,
        }.items() if v is not None}
        robot.control.set_forward_velocity_ff_config(config)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetPositionControlConfigAction(ActionBase):
    """Set position control parameters (path following gains, limits, lookahead)."""
    type_id: ClassVar[str] = 'set_position_control_config'

    @dataclass
    class Params:
        kp_angular: float = None
        ki_angular: float = None
        kp_linear: float = None
        ki_linear: float = None
        kd_linear: float = None
        max_speed: float = None
        max_turn_rate: float = None
        lookahead_base: float = None
        arrival_tolerance: float = None
        decel_limit: float = None
        curvature_gain: float = None
        curvature_lookahead: float = None

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        config = {}
        for f in ['kp_angular', 'ki_angular', 'kp_linear', 'ki_linear', 'kd_linear',
                  'max_speed', 'max_turn_rate', 'lookahead_base', 'arrival_tolerance',
                  'decel_limit', 'curvature_gain', 'curvature_lookahead']:
            val = getattr(params, f)
            if val is not None:
                config[f] = val
        robot.control.set_position_control_config(config)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetMaxWheelSpeedAction(ActionBase):
    """Set the maximum wheel speed limit."""
    type_id: ClassVar[str] = 'set_max_wheel_speed'

    @dataclass
    class Params:
        speed: float  # [rad/s]

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.control.set_max_wheel_speed(params.speed)
        context.complete()
        return ActionResult.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════════
# NAVIGATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MoveToAction(ActionBase):
    """Move robot to an absolute XY position."""
    type_id: ClassVar[str] = 'move_to'
    transition_ports: ClassVar[list[str]] = ['done', 'timeout']

    @dataclass
    class Params:
        x: float = 0.0
        y: float = 0.0
        max_speed: float = 0.0  # 0 = use default
        timeout: float = 0.0  # 0 = no timeout
        wait: bool = True

    @dataclass
    class Data:
        reached: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)

        robot.control.position_control.move_to_point(
            x=params.x, y=params.y,
            max_speed=params.max_speed,
            timeout=params.timeout,
        )

        if not params.wait:
            context.complete(data={'reached': True})
            return ActionResult.COMPLETED

        thread = threading.Thread(
            target=self._wait_completion, args=(context, robot, params.timeout), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _wait_completion(self, context, robot, timeout):
        event = robot.control.position_control.events.move_to_point_completed
        result = event.wait(timeout=timeout if timeout > 0 else None)
        if result is None:
            context.complete(port='timeout', data={'reached': False})
        else:
            context.complete(port='done', data={'reached': True})


@dataclass
class TurnToAction(ActionBase):
    """Turn robot to an absolute heading."""
    type_id: ClassVar[str] = 'turn_to'
    transition_ports: ClassVar[list[str]] = ['done', 'timeout']

    @dataclass
    class Params:
        heading: float = 0.0  # [rad]
        heading_deg: float = None  # [deg], alternative to heading
        max_angular_speed: float = 0.0
        timeout: float = 0.0
        wait: bool = True

    @dataclass
    class Data:
        reached: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)

        heading = params.heading
        if params.heading_deg is not None:
            heading = math.radians(params.heading_deg)

        robot.control.position_control.turn_to_heading(
            heading=heading,
            max_angular_speed=params.max_angular_speed,
            timeout=params.timeout,
        )

        if not params.wait:
            context.complete(data={'reached': True})
            return ActionResult.COMPLETED

        thread = threading.Thread(
            target=self._wait_completion, args=(context, robot, params.timeout), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _wait_completion(self, context, robot, timeout):
        event = robot.control.position_control.events.turn_to_heading_completed
        result = event.wait(timeout=timeout if timeout > 0 else None)
        if result is None:
            context.complete(port='timeout', data={'reached': False})
        else:
            context.complete(port='done', data={'reached': True})


@dataclass
class MoveToPoseAction(ActionBase):
    """Move robot to a pose (position + heading). Drives to the point, then turns to the heading.
    Specify either explicit x/y/psi or a named pose from the testbed."""
    type_id: ClassVar[str] = 'move_to_pose'
    transition_ports: ClassVar[list[str]] = ['done', 'timeout']

    @dataclass
    class Params:
        pose: str = None  # Named pose from testbed (overrides x/y/psi)
        x: float = 0.0
        y: float = 0.0
        psi: float = 0.0  # [rad]
        psi_deg: float = None  # [deg], alternative to psi
        max_speed: float = 0.0  # 0 = use default
        max_angular_speed: float = 3.0  # [rad/s]
        position_tolerance: float = 0.0  # 0 = use config arrival_tolerance
        max_corrections: int = 3
        timeout: float = 0.0  # 0 = no timeout
        wait: bool = True

    @dataclass
    class Data:
        reached: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)

        x, y, heading = params.x, params.y, params.psi

        # Look up named pose from testbed
        if params.pose is not None:
            pose = None
            for p in robot.testbed_manager.poses:
                if p.id == params.pose:
                    pose = p
                    break
            if pose is None:
                available = [p.id for p in robot.testbed_manager.poses]
                context.complete(port='timeout', data={'reached': False})
                context.logger.error(
                    f"Pose '{params.pose}' not found. Available: {available}"
                )
                return ActionResult.COMPLETED
            x, y, heading = pose.x, pose.y, pose.psi

        if params.psi_deg is not None and params.pose is None:
            heading = math.radians(params.psi_deg)

        robot.control.position_control.move_to_pose(
            x=x, y=y, heading=heading,
            max_speed=params.max_speed,
            max_angular_speed=params.max_angular_speed,
            position_tolerance=params.position_tolerance,
            max_corrections=params.max_corrections,
            timeout=params.timeout,
        )

        if not params.wait:
            context.complete(data={'reached': True})
            return ActionResult.COMPLETED

        thread = threading.Thread(
            target=self._wait_completion, args=(context, robot, params.timeout), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _wait_completion(self, context, robot, timeout):
        event = robot.control.position_control.events.move_to_pose_completed
        timeout_event = robot.control.position_control.events.move_to_pose_timeout
        from core.utils.events import wait_for_events, OR
        _, trace = wait_for_events(
            OR(event, timeout_event),
            timeout=timeout if timeout > 0 else None,
        )
        if trace is None or trace.caused_by(timeout_event):
            context.complete(port='timeout', data={'reached': False})
        else:
            context.complete(port='done', data={'reached': True})


@dataclass
class FollowPathAction(ActionBase):
    """Plan and follow a collision-free path to a target position."""
    type_id: ClassVar[str] = 'follow_path'
    transition_ports: ClassVar[list[str]] = ['done', 'timeout']

    @dataclass
    class Params:
        target_x: float = 0.0
        target_y: float = 0.0
        waypoints: list = None  # [[x, y], [x, y, weight], ...]
        max_speed: float = 0.0
        timeout: float = 0.0
        allow_reverse: bool = False
        seed: int = None
        target_heading: float = None  # [rad]
        target_heading_deg: float = None  # [deg]
        wait: bool = True

    @dataclass
    class Data:
        path_points: list = None
        planning_time: float = 0.0

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)

        target_heading = params.target_heading
        if params.target_heading_deg is not None:
            target_heading = math.radians(params.target_heading_deg)

        robot.control.position_control.follow_path(
            target_x=params.target_x, target_y=params.target_y,
            waypoints=params.waypoints or [],
            max_speed=params.max_speed,
            timeout=params.timeout,
            allow_reverse=params.allow_reverse,
            seed=params.seed,
            target_heading=target_heading,
        )

        if not params.wait:
            context.complete()
            return ActionResult.COMPLETED

        thread = threading.Thread(
            target=self._wait_completion, args=(context, robot, params.timeout), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _wait_completion(self, context, robot, timeout):
        event = robot.control.position_control.events.path_finished
        result = event.wait(timeout=timeout if timeout > 0 else None)
        if result is None:
            context.complete(port='timeout')
        else:
            context.complete(port='done')


@dataclass
class StopPathAction(ActionBase):
    """Abort the current path execution."""
    type_id: ClassVar[str] = 'stop_path'

    def execute(self, context: ActionContext) -> ActionResult:
        robot = _get_robot(context)
        robot.control.position_control.stop_path()
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class WaitPositionEventAction(ActionBase):
    """Wait for a position control event (path_finished, waypoint_reached, etc.)."""
    type_id: ClassVar[str] = 'wait_position_event'
    transition_ports: ClassVar[list[str]] = ['done', 'timeout']

    @dataclass
    class Params:
        event: str  # path_finished, path_started, waypoint_reached, move_to_point_completed, ...
        timeout: float = None

    @dataclass
    class Data:
        event_data: Any = None
        timed_out: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)

        thread = threading.Thread(
            target=self._wait, args=(context, robot, params.event, params.timeout), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _wait(self, context, robot, event_name, timeout):
        event = getattr(robot.control.position_control.events, event_name, None)
        if event is None:
            context.fail(f"Unknown position event: {event_name}")
            return
        result = event.wait(timeout=timeout)
        if result is None:
            self._data['timed_out'] = True
            context.complete(port='timeout', data={'timed_out': True})
        else:
            self._data['event_data'] = result
            context.complete(port='done', data={'event_data': result})


@dataclass
class SetPlannerAction(ActionBase):
    """Switch the motion planner algorithm (rrt or prm)."""
    type_id: ClassVar[str] = 'set_planner'

    @dataclass
    class Params:
        method: str = 'rrt'  # 'rrt' or 'prm'

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        config = robot.control.get_control_config()
        config.planning.method = params.method
        robot.control.set_config(config)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetPlannerConfigAction(ActionBase):
    """Set motion planner configuration parameters."""
    type_id: ClassVar[str] = 'set_planner_config'

    @dataclass
    class Params:
        method: str = None  # 'rrt' or 'prm' (optional, keeps current if None)
        smoothing: float = None
        safety_margin: float = None
        clearance_weight: float = None
        # RRT-specific
        rrt_star: bool = None
        rrt_max_iterations: int = None
        rrt_step_size: float = None
        rrt_goal_bias: float = None
        rrt_rewire_radius: float = None
        # PRM-specific
        prm_n_samples: int = None
        prm_k_neighbors: int = None
        prm_connection_radius: float = None
        prm_seed: int = None

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        config = robot.control.get_control_config()

        if params.method is not None:
            config.planning.method = params.method
        if params.smoothing is not None:
            config.planning.smoothing = params.smoothing
        if params.safety_margin is not None:
            config.planning.safety_margin = params.safety_margin
        if params.clearance_weight is not None:
            config.planning.clearance_weight = params.clearance_weight

        # RRT
        if params.rrt_star is not None:
            config.planning.rrt.rrt_star = params.rrt_star
        if params.rrt_max_iterations is not None:
            config.planning.rrt.max_iterations = params.rrt_max_iterations
        if params.rrt_step_size is not None:
            config.planning.rrt.step_size = params.rrt_step_size
        if params.rrt_goal_bias is not None:
            config.planning.rrt.goal_bias = params.rrt_goal_bias
        if params.rrt_rewire_radius is not None:
            config.planning.rrt.rewire_radius = params.rrt_rewire_radius

        # PRM
        if params.prm_n_samples is not None:
            config.planning.prm.n_samples = params.prm_n_samples
        if params.prm_k_neighbors is not None:
            config.planning.prm.k_neighbors = params.prm_k_neighbors
        if params.prm_connection_radius is not None:
            config.planning.prm.connection_radius = params.prm_connection_radius
        if params.prm_seed is not None:
            config.planning.prm.seed = params.prm_seed

        robot.control.set_config(config)
        context.complete()
        return ActionResult.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════════
# DRIVE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SetVelocityAction(ActionBase):
    """Set forward velocity and turn rate commands."""
    type_id: ClassVar[str] = 'set_velocity'

    @dataclass
    class Params:
        forward: float = 0.0  # [m/s] or normalized [-1, 1]
        turn: float = 0.0  # [rad/s] or normalized [-1, 1]
        normalized: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.control.set_velocity(params.forward, params.turn, normalized=params.normalized)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetInputAction(ActionBase):
    """Set direct torque/input values (simulates joystick)."""
    type_id: ClassVar[str] = 'set_input'

    @dataclass
    class Params:
        input: list  # [forward, turn] values
        normalized: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)

        robot.control.set_external_input_forward_turn(forward=params.input[0], turn=params.input[1],
                                                      normalized=params.normalized)
        context.complete()
        return ActionResult.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════════
# TRAJECTORY
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RunTrajectoryAction(ActionBase):
    """Execute a pre-computed input trajectory via SPI injection."""
    type_id: ClassVar[str] = 'run_trajectory'

    @dataclass
    class Params:
        trajectory: Any = None  # BILBO_InputTrajectory, file path, or dict

    @dataclass
    class Data:
        result: Any = None  # BILBO_TrajectoryExperimentData

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)

        thread = threading.Thread(
            target=self._run, args=(context, robot, params.trajectory), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _run(self, context, robot, trajectory):
        try:
            result = robot.experiment_handler.run_trajectory(trajectory)
            context.complete(data={'result': result})
        except Exception as e:
            context.fail(str(e))


@dataclass
class RandomInputAction(ActionBase):
    """Generate a random input trajectory and execute it via SPI injection."""
    type_id: ClassVar[str] = 'random_input'

    @dataclass
    class Params:
        time_s: float = 10.0        # Duration in seconds
        frequency: float = 1.0      # Cutoff frequency for filtering [Hz]
        gain: float = 0.1           # Amplitude scaling factor
        bias: float = 0.0           # Constant offset (positive = forward bias)
        trajectory_id: int = 0      # Numeric ID for the trajectory

    @dataclass
    class Data:
        trajectory: list = None     # Generated trajectory as [[left, right], ...]
        result: Any = None          # Trajectory execution result

    def execute(self, context: ActionContext) -> ActionResult:
        from robot.experiment.helpers import generate_random_input_trajectory
        params = self.get_params(context)
        robot = _get_robot(context)

        trajectory = generate_random_input_trajectory(
            trajectory_id=params.trajectory_id,
            time_s=params.time_s,
            frequency=params.frequency,
            gain=params.gain,
            bias=params.bias,
        )
        if trajectory is None:
            context.fail('Trajectory too long (exceeds maximum steps)')
            return ActionResult.ERROR

        # Store trajectory as list of [left, right] pairs
        traj_list = [[s.left, s.right] for s in trajectory.inputs]

        thread = threading.Thread(
            target=self._run, args=(context, robot, trajectory, traj_list), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _run(self, context, robot, trajectory, traj_list):
        try:
            result = robot.experiment_handler.run_trajectory(trajectory)
            context.complete(data={'trajectory': traj_list, 'result': result})
        except Exception as e:
            context.fail(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# ESTIMATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EnableTrackingAction(ActionBase):
    """Enable or disable OptiTrack position tracking updates."""
    type_id: ClassVar[str] = 'enable_tracking'

    @dataclass
    class Params:
        enabled: bool = True

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.estimation.set_tracker_updates_enabled(params.enabled)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class WaitForStaticAction(ActionBase):
    """Wait until the robot is stationary and upright."""
    type_id: ClassVar[str] = 'wait_for_static'
    transition_ports: ClassVar[list[str]] = ['done', 'timeout']

    @dataclass
    class Params:
        timeout: float = 10.0

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)

        thread = threading.Thread(
            target=self._wait, args=(context, robot, params.timeout), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _wait(self, context, robot, timeout):
        from core.utils.time import precise_sleep
        deadline = time.monotonic() + timeout if timeout > 0 else None
        while True:
            if robot.estimation.is_static():
                context.complete(port='done')
                return
            if deadline and time.monotonic() >= deadline:
                context.complete(port='timeout')
                return
            precise_sleep(0.05)


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO / IO
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BeepAction(ActionBase):
    """Play a beep on the robot's buzzer."""
    type_id: ClassVar[str] = 'beep'

    @dataclass
    class Params:
        frequency: int = 1000  # Hz (or "low"/"medium"/"high")
        time_ms: int = 250
        repeats: int = 1

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.utilities.beep(params.frequency, params.time_ms, params.repeats)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SpeakAction(ActionBase):
    """Speak text using text-to-speech."""
    type_id: ClassVar[str] = 'speak'

    @dataclass
    class Params:
        text: str

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.utilities.speak(params.text)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class PlayToneAction(ActionBase):
    """Play a named tone (notification, warning, etc.)."""
    type_id: ClassVar[str] = 'play_tone'

    @dataclass
    class Params:
        tone: str = 'notification'

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.utilities.playTone(params.tone)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetLEDAction(ActionBase):
    """Set the external RGB LED color."""
    type_id: ClassVar[str] = 'set_led'

    @dataclass
    class Params:
        red: int = 0  # 0-255
        green: int = 0
        blue: int = 0

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.utilities.setLEDs(params.red, params.green, params.blue)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetMarkerAction(ActionBase):
    """Set a named marker in the experiment/log data."""
    type_id: ClassVar[str] = 'set_marker'

    @dataclass
    class Params:
        marker_id: str
        marker_value: str = ''

    @dataclass
    class Data:
        marker_id: str = ''
        marker_value: str = ''

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.experiment_handler.set_marker(params.marker_id, params.marker_value)
        context.complete(data={'marker_id': params.marker_id, 'marker_value': params.marker_value})
        return ActionResult.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════════
# INPUT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EnableExternalInputAction(ActionBase):
    """Enable or disable external input (joystick/WiFi)."""
    type_id: ClassVar[str] = 'enable_external_input'

    @dataclass
    class Params:
        enabled: bool = True

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        if params.enabled:
            robot.control.enable_external_input()
        else:
            robot.control.disable_external_input()
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class ResetAction(ActionBase):
    """Reset robot state (re-enable external input, clear errors)."""
    type_id: ClassVar[str] = 'reset'

    def execute(self, context: ActionContext) -> ActionResult:
        robot = _get_robot(context)
        robot.control.enable_external_input()
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class WaitForExternalEventAction(ActionBase):
    """Wait for a robot-level event by UID pattern.

    Uses the global EventLoop's pattern matching (fnmatch) against Event UIDs.
    All Events register themselves with the EventLoop on creation, so any
    robot event can be matched.

    Examples:
      event: "*:resume"              — interaction resume (DPAD right)
      event: "*:repeat"              — interaction repeat/revert (DPAD left)
      event: "*:stop"               — interaction stop
      event: "*:control_mode_change" — control mode changed
      event: "*:error"               — robot error
    """
    type_id: ClassVar[str] = 'wait_for_external_event'
    transition_ports: ClassVar[list[str]] = ['done', 'timeout']

    @dataclass
    class Params:
        event: str  # Event UID pattern (fnmatch, e.g. '*:resume')
        timeout: float = None

    @dataclass
    class Data:
        data: Any = None
        timed_out: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)

        thread = threading.Thread(
            target=self._wait, args=(context, params.event, params.timeout), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    @staticmethod
    def _wait(context: ActionContext, pattern: str, timeout: float | None):

        data, match = wait_for_events(pattern, timeout=timeout)
        if data is EV_TIMEOUT:
            context.complete(port='timeout', data={'timed_out': True})
        else:
            context.complete(port='done', data={'data': data})


# ═══════════════════════════════════════════════════════════════════════════════
# TESTBED
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LoadTestbedAction(ActionBase):
    """Load a complete testbed environment (config, obstacles, lines, points, poses).

    Clears all existing testbed state and replaces it with the provided data.
    Accepts either inline data or a file path to an environment YAML file.
    When a file is specified, the host resolves it before sending to the robot.
    """
    type_id: ClassVar[str] = 'load_testbed'

    @dataclass
    class Params:
        file: str = None  # Path to environment YAML file (resolved by host before sending)
        config: dict = None  # {id, size: {x_min, x_max, y_min, y_max}}
        obstacles: list = None  # [{id, type, x, y, radius/width/height/psi}, ...]
        lines: list = None  # [{id, start: [x,y], end: [x,y]}, ...]
        points: list = None  # [{id, position: [x,y]}, ...]
        poses: list = None  # [{id, x, y, psi}, ...]

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        data = {}
        if params.config is not None:
            data['config'] = params.config
        if params.obstacles is not None:
            data['obstacles'] = params.obstacles
        if params.lines is not None:
            data['lines'] = params.lines
        if params.points is not None:
            data['points'] = params.points
        if params.poses is not None:
            data['poses'] = params.poses
        robot.testbed.load(data)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class BuildRoadmapAction(ActionBase):
    """Build the PRM roadmap for path planning.

    Uses the current testbed obstacles and bounds. Must be called after
    setting the planner to 'prm' and loading the testbed environment.
    """
    type_id: ClassVar[str] = 'build_roadmap'

    def execute(self, context: ActionContext) -> ActionResult:
        robot = _get_robot(context)
        robot.control.position_control.build_prm_map()
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class AddObstacleAction(ActionBase):
    """Add an obstacle to the testbed environment."""
    type_id: ClassVar[str] = 'add_obstacle'

    @dataclass
    class Params:
        id: str
        type: str = 'circle'  # 'circle' or 'box'
        x: float = 0.0
        y: float = 0.0
        radius: float = 0.1  # for circle
        width: float = 0.1  # for box
        height: float = 0.1  # for box
        psi: float = 0.0  # rotation for box [rad]

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        obstacle = {
            'id': params.id,
            'type': params.type,
            'x': params.x, 'y': params.y,
        }
        if params.type == 'circle':
            obstacle['radius'] = params.radius
        else:
            obstacle['width'] = params.width
            obstacle['height'] = params.height
            obstacle['psi'] = params.psi
        robot.testbed.add_obstacle(obstacle)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class RemoveObstacleAction(ActionBase):
    """Remove an obstacle from the testbed by ID."""
    type_id: ClassVar[str] = 'remove_obstacle'

    @dataclass
    class Params:
        id: str

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)
        robot = _get_robot(context)
        robot.testbed.remove_obstacle(params.id)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class ClearObstaclesAction(ActionBase):
    """Remove all obstacles from the testbed."""
    type_id: ClassVar[str] = 'clear_obstacles'

    def execute(self, context: ActionContext) -> ActionResult:
        robot = _get_robot(context)
        robot.testbed.clear_obstacles()
        context.complete()
        return ActionResult.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════════
# DATA ACCESS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ReadStateAction(ActionBase):
    """Read the current robot state and expose it as action data."""
    type_id: ClassVar[str] = 'read_state'

    @dataclass
    class Data:
        x: float = 0.0
        y: float = 0.0
        v: float = 0.0
        theta: float = 0.0  # pitch [rad]
        theta_dot: float = 0.0
        psi: float = 0.0  # yaw [rad]
        psi_dot: float = 0.0

    def execute(self, context: ActionContext) -> ActionResult:
        robot = _get_robot(context)
        state = robot.estimation.get_state()
        context.complete(data={
            'x': state.x, 'y': state.y, 'v': state.v,
            'theta': state.theta, 'theta_dot': state.theta_dot,
            'psi': state.psi, 'psi_dot': state.psi_dot,
        })
        return ActionResult.COMPLETED


@dataclass
class FlushLogsAction(ActionBase):
    """Force all buffered log data to disk."""
    type_id: ClassVar[str] = 'flush_logs'

    def execute(self, context: ActionContext) -> ActionResult:
        robot = _get_robot(context)
        robot.common.flush_logs()
        context.complete()
        return ActionResult.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

ALL_BILBO_ACTIONS = [
    # Control
    SetModeAction,
    SetFeedbackGainAction,
    SetTICAction,
    SetVICAction,
    SetPSIControlAction,
    SetPSISetpointAction,
    ResetControlAction,
    LoadControlConfigAction,
    SetVelocityPIDAction,
    SetTurnPIDAction,
    SetVelocityFeedforwardAction,
    SetPositionControlConfigAction,
    SetMaxWheelSpeedAction,
    # Navigation
    MoveToAction,
    TurnToAction,
    MoveToPoseAction,
    FollowPathAction,
    StopPathAction,
    WaitPositionEventAction,
    SetPlannerAction,
    SetPlannerConfigAction,
    # Drive
    SetVelocityAction,
    SetInputAction,
    # Trajectory
    RunTrajectoryAction,
    RandomInputAction,
    # Estimation
    EnableTrackingAction,
    WaitForStaticAction,
    # Audio / IO
    BeepAction,
    SpeakAction,
    PlayToneAction,
    SetLEDAction,
    SetMarkerAction,
    # Input
    EnableExternalInputAction,
    ResetAction,
    WaitForExternalEventAction,
    # Testbed
    LoadTestbedAction,
    BuildRoadmapAction,
    AddObstacleAction,
    RemoveObstacleAction,
    ClearObstaclesAction,
    # Data
    ReadStateAction,
    FlushLogsAction,
]


def register_bilbo_actions(registry: ActionRegistry):
    """Register all BILBO-specific action types with a registry."""
    for cls in ALL_BILBO_ACTIONS:
        registry.register(cls)


# ═══════════════════════════════════════════════════════════════════════════════
# REQUIREMENTS
# ═══════════════════════════════════════════════════════════════════════════════

from core.utils.experiments.requirement import RequirementBase, RequirementContext, RequirementResult, \
    RequirementRegistry


@dataclass
class OptiTrackRequirement(RequirementBase):
    """Require OptiTrack motion capture to be active."""
    type_id: ClassVar[str] = 'require_optitrack'

    def check(self, context: RequirementContext) -> RequirementResult:
        robot = context.context_objects.get('robot')
        if robot is None:
            return RequirementResult(passed=False, message="No robot context object")
        if robot.estimation.tracker_connected:
            return RequirementResult(passed=True)
        return RequirementResult(passed=False, message="OptiTrack tracker not connected")



@dataclass
class RobotIdRequirement(RequirementBase):
    """Require robot ID to match a pattern."""
    type_id: ClassVar[str] = 'require_robot_id'

    @dataclass
    class Params:
        pattern: str = 'bilbo.*'  # Regex pattern

    def check(self, context: RequirementContext) -> RequirementResult:
        # TODO: check robot.common.id against params.pattern
        raise NotImplementedError("RobotIdRequirement check not implemented")


@dataclass
class ControlModeRequirement(RequirementBase):
    """Require a specific control mode before starting."""
    type_id: ClassVar[str] = 'require_control_mode'

    @dataclass
    class Params:
        mode: str = 'OFF'  # OFF, DIRECT, BALANCING, VELOCITY, POSITION

    def check(self, context: RequirementContext) -> RequirementResult:
        params = self.get_params_raw()
        robot = context.get_object('robot')
        if robot is None:
            return RequirementResult(passed=False, message="No robot object in context")
        current_mode = robot.control.mode
        required_mode = BILBO_Control_Mode[params.mode]
        if current_mode != required_mode:
            return RequirementResult(passed=False, message=f"Control mode is {current_mode.name}, required {required_mode.name}")
        return RequirementResult(passed=True)


@dataclass
class ControlConfigRequirement(RequirementBase):
    """Require a specific control config to be loaded."""
    type_id: ClassVar[str] = 'require_control_config'

    @dataclass
    class Params:
        config: str  # Control config name

    def check(self, context: RequirementContext) -> RequirementResult:
        # TODO: check that the named control config is loaded
        raise NotImplementedError("ControlConfigRequirement check not implemented")


@dataclass
class StateRangeRequirement(RequirementBase):
    """Require a robot state variable to be within a range."""
    type_id: ClassVar[str] = 'require_state_range'

    @dataclass
    class Params:
        state: str = 'theta'  # x, y, v, theta, theta_dot, psi, psi_dot
        min: float = None
        max: float = None

    def check(self, context: RequirementContext) -> RequirementResult:
        # TODO: read robot state and check against min/max
        raise NotImplementedError("StateRangeRequirement check not implemented")


@dataclass
class StaticRequirement(RequirementBase):
    """Require the robot to be static (not moving) before starting."""
    type_id: ClassVar[str] = 'require_static'

    def check(self, context: RequirementContext) -> RequirementResult:
        robot = context.get_object('robot')
        if robot is None:
            return RequirementResult(passed=False, message="No robot object in context")
        if not robot.estimation.static:
            return RequirementResult(passed=False, message="Robot is not static")
        return RequirementResult(passed=True)


@dataclass
class TestbedRequirement(RequirementBase):
    """Require the current testbed ID to match a given value."""
    type_id: ClassVar[str] = 'require_testbed'

    @dataclass
    class Params:
        testbed: str  # Expected testbed ID (e.g. 'lab', 'track')

    def check(self, context: RequirementContext) -> RequirementResult:
        params = self.get_params_raw()
        robot = context.get_object('robot')
        if robot is None:
            return RequirementResult(passed=False, message="No robot object in context")
        config = robot.testbed_manager.testbed_config
        current_id = config.id if config is not None else None
        if current_id != params.testbed:
            return RequirementResult(
                passed=False,
                message=f"Testbed is '{current_id}', required '{params.testbed}'",
            )
        return RequirementResult(passed=True)


ALL_BILBO_REQUIREMENTS = [
    OptiTrackRequirement,
    RobotIdRequirement,
    ControlModeRequirement,
    ControlConfigRequirement,
    StateRangeRequirement,
    StaticRequirement,
    TestbedRequirement,
]


def register_bilbo_requirements(registry: RequirementRegistry):
    """Register all BILBO-specific requirement types with a registry."""
    for cls in ALL_BILBO_REQUIREMENTS:
        registry.register(cls)


# ═══════════════════════════════════════════════════════════════════════════════
# GUARDS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DisableExternalInputGuard(GuardBase):
    """Disable external input during experiment, re-enable on teardown."""
    type_id: ClassVar[str] = 'disable_external_input'

    def setup(self, context: GuardContext):
        robot: BILBO = context.get_object('robot')
        if robot is None:
            raise RuntimeError("No 'robot' context object registered")
        robot.interfaces.disable_external_input()

    def teardown(self, context: GuardContext):
        robot = context.get_object('robot')
        if robot is None:
            return
        robot.interfaces.enable_external_input()


@dataclass
class ZeroInputGuard(GuardBase):
    """Zero all control inputs on teardown without changing the control mode."""
    type_id: ClassVar[str] = 'zero_input'

    def setup(self, context: GuardContext):
        pass  # Nothing to do on setup

    def teardown(self, context: GuardContext):
        robot: BILBO = context.get_object('robot')
        if robot is None:
            return
        mode = robot.control.mode
        match mode:
            case BILBO_Control_Mode.BALANCING:
                robot.control.set_external_input(0, 0)
            case BILBO_Control_Mode.VELOCITY:
                robot.control.set_velocity(0, 0)
            case BILBO_Control_Mode.POSITION:
                robot.control.position_control.abort_path()
            case _:
                pass


@dataclass
class RestoreControlConfigGuard(GuardBase):
    """Save the current control config on setup and restore it on teardown."""
    type_id: ClassVar[str] = 'restore_control_config'

    _saved_config: Any = field(default=None, init=False, repr=False)

    def setup(self, context: GuardContext):
        robot: BILBO = context.get_object('robot')
        if robot is None:
            raise RuntimeError("No 'robot' context object registered")
        self._saved_config = copy.deepcopy(robot.control.get_control_config())

    def teardown(self, context: GuardContext):
        if self._saved_config is None:
            return
        robot: BILBO = context.get_object('robot')
        if robot is None:
            return
        robot.control.set_config(self._saved_config)


@dataclass
class PsiControlGuard(GuardBase):
    """Enable psi (yaw/heading) control on setup, disable on teardown."""
    type_id: ClassVar[str] = 'psi_control'

    def setup(self, context: GuardContext):
        robot: BILBO = context.get_object('robot')
        if robot is None:
            raise RuntimeError("No 'robot' context object registered")
        robot.control.enable_psi_control(True)

    def teardown(self, context: GuardContext):
        robot: BILBO = context.get_object('robot')
        if robot is None:
            return
        robot.control.enable_psi_control(False)


@dataclass
class StartGuard(GuardBase):
    """Block experiment start until the start interaction event is received.

    Waits for the robot's interaction start event before allowing actions to execute.
    If the timeout expires without a start signal, the experiment fails.
    """
    type_id: ClassVar[str] = 'start'
    default_message_before: ClassVar[str] = 'Waiting for start event...'

    @dataclass
    class Params:
        timeout: float = 60.0

    def setup(self, context: GuardContext):
        params = self.get_params_raw()
        robot: BILBO = context.get_object('robot')
        if robot is None:
            raise RuntimeError("No 'robot' context object registered")
        self.logger.info(f"Waiting for start event (timeout={params.timeout}s)...")
        data, match = wait_for_events(robot.common.interaction_events.start, timeout=params.timeout)
        if data is EV_TIMEOUT:
            raise RuntimeError(f"Start guard timed out after {params.timeout}s")
        self.logger.info("Start event received, proceeding")

    def teardown(self, context: GuardContext):
        pass  # No cleanup needed


@dataclass
class TimecodeGuard(GuardBase):
    """Require a timecode connection before allowing the experiment to start.

    Waits until the robot's timecode client has received at least one sync,
    or fails after the configured timeout.
    """
    type_id: ClassVar[str] = 'timecode'
    default_message_before: ClassVar[str] = 'Waiting for timecode...'

    @dataclass
    class Params:
        timeout: float = 10.0

    def setup(self, context: GuardContext):
        params = self.get_params_raw()
        robot: BILBO = context.get_object('robot')
        if robot is None:
            raise RuntimeError("No 'robot' context object registered")
        deadline = time.monotonic() + params.timeout
        while robot.common.get_timecode() is None:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timecode guard timed out after {params.timeout}s — no timecode received")
            time.sleep(0.1)
        self.logger.info("Timecode connected, proceeding")

    def teardown(self, context: GuardContext):
        pass  # No cleanup needed


ALL_BILBO_GUARDS = [
    DisableExternalInputGuard,
    ZeroInputGuard,
    RestoreControlConfigGuard,
    PsiControlGuard,
    StartGuard,
    TimecodeGuard,
]


def register_bilbo_guards(registry: GuardRegistry):
    """Register all BILBO-specific guard types with a registry."""
    for cls in ALL_BILBO_GUARDS:
        registry.register(cls)
