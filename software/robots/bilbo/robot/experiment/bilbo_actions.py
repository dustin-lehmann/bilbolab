"""
Host-side BILBO action definitions for the new experiment framework.

These mirror the on-robot actions at:
    robots/bilbo/software/robot/experiment/actions.py

The class hierarchy, type_ids, Params, Data, and transition_ports are identical.
The execute() methods are stubs — they immediately complete without touching hardware.
This allows the host side (and the experiment designer) to:
  - Register BILBO actions in the new ActionRegistry
  - Introspect parameters (parameter_defs, data_defs) for validation and UI generation
  - Parse and validate experiment definitions before sending to the robot

To keep in sync: diff this file against the on-robot actions.py.
Only the execute() bodies and the helper imports should differ.

Usage:
    from core.utils.experiments import ActionRegistry, register_builtin_actions
    from robots.bilbo.robot.experiment.bilbo_actions import register_bilbo_actions

    registry = ActionRegistry()
    register_builtin_actions(registry)
    register_bilbo_actions(registry)

    # Introspect
    for cls in ALL_BILBO_ACTIONS:
        print(f"{cls.type_id}: {cls.__doc__}")
        for name, pdef in cls.parameter_defs.items():
            print(f"  {name}: required={pdef.required}, default={pdef.default}")
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar

from core.utils.experiments.types import ActionResult
from core.utils.experiments.action import ActionBase, ActionContext, ActionRegistry
from core.utils.experiments.guard import GuardBase, GuardContext, GuardRegistry


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
        context.complete()
        return ActionResult.COMPLETED

SetModeAction.parameter_defs['mode'].options = ['OFF', 'DIRECT', 'BALANCING', 'VELOCITY', 'POSITION']


@dataclass
class SetFeedbackGainAction(ActionBase):
    """Set the LQR state feedback gain vector K."""
    type_id: ClassVar[str] = 'set_feedback_gain'

    @dataclass
    class Params:
        K: list  # 8-element gain vector

    def execute(self, context: ActionContext) -> ActionResult:
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
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class ResetControlAction(ActionBase):
    """Reload control parameters from the default config file."""
    type_id: ClassVar[str] = 'reset_control'

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class LoadControlConfigAction(ActionBase):
    """Load a named control configuration (e.g. 'default', 'lab')."""
    type_id: ClassVar[str] = 'load_control_config'

    @dataclass
    class Params:
        name: str  # Config name (matches filename in configs/control/)

    def execute(self, context: ActionContext) -> ActionResult:
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
        max_speed: float = 0.0    # 0 = use default
        timeout: float = 0.0      # 0 = no timeout
        wait: bool = True

    @dataclass
    class Data:
        reached: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete(data={'reached': True})
        return ActionResult.COMPLETED


@dataclass
class TurnToAction(ActionBase):
    """Turn robot to an absolute heading."""
    type_id: ClassVar[str] = 'turn_to'
    transition_ports: ClassVar[list[str]] = ['done', 'timeout']

    @dataclass
    class Params:
        heading: float = 0.0         # [rad]
        heading_deg: float = None    # [deg], alternative to heading
        max_angular_speed: float = 0.0
        timeout: float = 0.0
        wait: bool = True

    @dataclass
    class Data:
        reached: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete(data={'reached': True})
        return ActionResult.COMPLETED


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
        max_angular_speed: float = 1.0  # [rad/s]
        position_tolerance: float = 0.0  # 0 = use config arrival_tolerance
        max_corrections: int = 3
        timeout: float = 0.0  # 0 = no timeout
        wait: bool = True

    @dataclass
    class Data:
        reached: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete(data={'reached': True})
        return ActionResult.COMPLETED


@dataclass
class FollowPathAction(ActionBase):
    """Plan and follow a collision-free path to a target position."""
    type_id: ClassVar[str] = 'follow_path'
    transition_ports: ClassVar[list[str]] = ['done', 'timeout']

    @dataclass
    class Params:
        target_x: float = 0.0
        target_y: float = 0.0
        waypoints: list = None    # [[x, y], [x, y, weight], ...]
        max_speed: float = 0.0
        timeout: float = 0.0
        allow_reverse: bool = False
        seed: int = None
        target_heading: float = None     # [rad]
        target_heading_deg: float = None # [deg]
        wait: bool = True

    @dataclass
    class Data:
        path_points: list = None
        planning_time: float = 0.0

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class StopPathAction(ActionBase):
    """Abort the current path execution."""
    type_id: ClassVar[str] = 'stop_path'

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class WaitPositionEventAction(ActionBase):
    """Wait for a position control event (path_finished, waypoint_reached, etc.)."""
    type_id: ClassVar[str] = 'wait_position_event'
    transition_ports: ClassVar[list[str]] = ['done', 'timeout']

    @dataclass
    class Params:
        event: str      # path_finished, path_started, waypoint_reached, move_to_point_completed, ...
        timeout: float = None

    @dataclass
    class Data:
        event_data: Any = None
        timed_out: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete(data={'event_data': None, 'timed_out': False})
        return ActionResult.COMPLETED


@dataclass
class SetPlannerAction(ActionBase):
    """Switch the motion planner algorithm (rrt or prm)."""
    type_id: ClassVar[str] = 'set_planner'

    @dataclass
    class Params:
        method: str = 'rrt'  # 'rrt' or 'prm'

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete()
        return ActionResult.COMPLETED

SetPlannerAction.parameter_defs['method'].options = ['rrt', 'prm']


@dataclass
class SetPlannerConfigAction(ActionBase):
    """Set motion planner configuration parameters."""
    type_id: ClassVar[str] = 'set_planner_config'

    @dataclass
    class Params:
        method: str = None           # 'rrt' or 'prm' (optional, keeps current if None)
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
        forward: float = 0.0   # [m/s] or normalized [-1, 1]
        turn: float = 0.0      # [rad/s] or normalized [-1, 1]
        normalized: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetInputAction(ActionBase):
    """Set direct torque/input values (simulates joystick)."""
    type_id: ClassVar[str] = 'set_input'

    @dataclass
    class Params:
        input: list       # [forward, turn] values
        normalized: bool = False

    def execute(self, context: ActionContext) -> ActionResult:
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
        context.complete(data={'result': None})
        return ActionResult.COMPLETED


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
        context.complete(data={'trajectory': None, 'result': None})
        return ActionResult.COMPLETED


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
        context.complete()
        return ActionResult.COMPLETED


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
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetLEDAction(ActionBase):
    """Set the external RGB LED color."""
    type_id: ClassVar[str] = 'set_led'

    @dataclass
    class Params:
        red: int = 0    # 0-255
        green: int = 0
        blue: int = 0

    def execute(self, context: ActionContext) -> ActionResult:
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
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class ResetAction(ActionBase):
    """Reset robot state (re-enable external input, clear errors)."""
    type_id: ClassVar[str] = 'reset'

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class WaitForExternalEventAction(ActionBase):
    """Wait for a robot-level event by UID pattern (e.g. '*:resume', '*:control_mode_change')."""
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
        context.complete(data={'data': None, 'timed_out': False})
        return ActionResult.COMPLETED


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
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class AddObstacleAction(ActionBase):
    """Add an obstacle to the testbed environment."""
    type_id: ClassVar[str] = 'add_obstacle'

    @dataclass
    class Params:
        id: str
        type: str = 'circle'   # 'circle' or 'box'
        x: float = 0.0
        y: float = 0.0
        radius: float = 0.1    # for circle
        width: float = 0.1     # for box
        height: float = 0.1    # for box
        psi: float = 0.0       # rotation for box [rad]

    def execute(self, context: ActionContext) -> ActionResult:
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
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class ClearObstaclesAction(ActionBase):
    """Remove all obstacles from the testbed."""
    type_id: ClassVar[str] = 'clear_obstacles'

    def execute(self, context: ActionContext) -> ActionResult:
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
        theta: float = 0.0       # pitch [rad]
        theta_dot: float = 0.0
        psi: float = 0.0         # yaw [rad]
        psi_dot: float = 0.0

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete(data={
            'x': 0.0, 'y': 0.0, 'v': 0.0,
            'theta': 0.0, 'theta_dot': 0.0,
            'psi': 0.0, 'psi_dot': 0.0,
        })
        return ActionResult.COMPLETED


@dataclass
class FlushLogsAction(ActionBase):
    """Force all buffered log data to disk."""
    type_id: ClassVar[str] = 'flush_logs'

    def execute(self, context: ActionContext) -> ActionResult:
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
# ACTION CATALOG (for experiment designer / introspection)
# ═══════════════════════════════════════════════════════════════════════════════

# Category assignments for UI grouping (mirrors the on-robot file sections)
ACTION_CATEGORIES = {
    'set_mode': 'control', 'set_feedback_gain': 'control', 'set_tic': 'control',
    'set_vic': 'control', 'set_psi_control': 'control', 'set_psi_setpoint': 'control',
    'reset_control': 'control', 'load_control_config': 'control',
    'set_velocity_pid': 'control', 'set_turn_pid': 'control',
    'set_velocity_feedforward': 'control', 'set_position_control_config': 'control',
    'set_max_wheel_speed': 'control',
    'move_to': 'navigation', 'turn_to': 'navigation', 'move_to_pose': 'navigation',
    'follow_path': 'navigation',
    'stop_path': 'navigation', 'wait_position_event': 'navigation',
    'set_planner': 'navigation', 'set_planner_config': 'navigation',
    'set_velocity': 'drive', 'set_input': 'drive',
    'run_trajectory': 'trajectory', 'random_input': 'trajectory',
    'enable_tracking': 'estimation', 'wait_for_static': 'estimation',
    'beep': 'audio', 'speak': 'audio', 'play_tone': 'audio',
    'set_led': 'io', 'set_marker': 'io',
    'enable_external_input': 'input', 'reset': 'input', 'wait_for_external_event': 'input',
    'load_testbed': 'testbed', 'build_roadmap': 'navigation',
    'add_obstacle': 'testbed', 'remove_obstacle': 'testbed', 'clear_obstacles': 'testbed',
    'read_state': 'data', 'flush_logs': 'data',
}


def _python_type_to_str(tp) -> str | None:
    """Convert a Python type hint to a simple string for the frontend."""
    if tp is None:
        return None
    import typing
    # Unwrap Optional (Union[X, None])
    origin = getattr(tp, '__origin__', None)
    if origin is typing.Union:
        args = [a for a in tp.__args__ if a is not type(None)]
        if len(args) == 1:
            return _python_type_to_str(args[0])
    type_map = {int: 'int', float: 'float', str: 'str', bool: 'bool', list: 'list', dict: 'dict'}
    return type_map.get(tp)


def get_action_catalog() -> list[dict]:
    """Export all BILBO actions as a list of dicts for the experiment designer.

    Each entry contains:
        type_id, description, category, params, dataDefs, transitionPorts

    The format matches what actionRegistry.js expects, so the designer can
    merge these into its ACTIONS object dynamically.
    """
    catalog = []
    for cls in ALL_BILBO_ACTIONS:
        params = {}
        for name, pdef in cls.parameter_defs.items():
            params[name] = {
                'required': pdef.required,
                'default': pdef.default if pdef.default is not _MISSING else None,
            }
            type_str = _python_type_to_str(pdef.type)
            if type_str:
                params[name]['type'] = type_str
            if pdef.description:
                params[name]['description'] = pdef.description
            if pdef.options:
                params[name]['options'] = pdef.options

        data_defs = {}
        for name, ddef in cls.data_defs.items():
            data_defs[name] = {}
            if ddef.description:
                data_defs[name]['description'] = ddef.description

        catalog.append({
            'type': cls.type_id,
            'description': cls.__doc__ or '',
            'category': ACTION_CATEGORIES.get(cls.type_id, 'other'),
            'params': params,
            'dataDefs': data_defs,
            'transitionPorts': list(cls.transition_ports),
        })
    return catalog


# Import the MISSING sentinel for the catalog export
from core.utils.experiments.types import MISSING as _MISSING


# ═══════════════════════════════════════════════════════════════════════════════
# REQUIREMENTS (for experiment designer)
# ═══════════════════════════════════════════════════════════════════════════════

BILBO_REQUIREMENTS = {
    'require_optitrack': {
        'category': 'requirements',
        'description': 'Require OptiTrack motion capture to be active',
        'params': {},
        'dataDefs': {},
        'yamlMapping': {'type': 'flag', 'key': 'optitrack'},
    },
    'require_robot_id': {
        'category': 'requirements',
        'description': 'Require robot ID to match a pattern',
        'params': {
            'pattern': {'type': 'str', 'default': 'bilbo.*', 'required': True, 'description': 'Robot ID pattern (regex)'},
        },
        'dataDefs': {},
        'yamlMapping': {'type': 'param', 'key': 'robot_id', 'param': 'pattern'},
    },
    'require_control_mode': {
        'category': 'requirements',
        'description': 'Require a specific control mode before starting',
        'params': {
            'mode': {'type': 'str', 'default': 'OFF', 'required': True, 'description': 'Required control mode',
                     'options': ['OFF', 'DIRECT', 'BALANCING', 'VELOCITY', 'POSITION']},
        },
        'dataDefs': {},
        'yamlMapping': {'type': 'param', 'key': 'control_mode', 'param': 'mode'},
    },
    'require_control_config': {
        'category': 'requirements',
        'description': 'Require a specific control config to be loaded',
        'params': {
            'config': {'type': 'str', 'default': '', 'required': True, 'description': 'Control config name'},
        },
        'dataDefs': {},
        'yamlMapping': {'type': 'param', 'key': 'control_config', 'param': 'config'},
    },
    'require_state_range': {
        'category': 'requirements',
        'description': 'Require a robot state to be within a range',
        'params': {
            'state': {'type': 'str', 'default': 'theta', 'required': True, 'description': 'State variable name',
                      'options': ['x', 'y', 'v', 'theta', 'theta_dot', 'psi', 'psi_dot']},
            'min': {'type': 'float', 'default': None, 'description': 'Minimum value (inclusive)'},
            'max': {'type': 'float', 'default': None, 'description': 'Maximum value (inclusive)'},
        },
        'dataDefs': {},
        'yamlMapping': {'type': 'state_range'},
    },
    'require_static': {
        'category': 'requirements',
        'description': 'Require the robot to be static (not moving)',
        'params': {},
        'dataDefs': {},
        'yamlMapping': {'type': 'flag', 'key': 'static'},
    },
    'require_testbed': {
        'category': 'requirements',
        'description': 'Require the current testbed ID to match',
        'params': {
            'testbed': {'type': 'str', 'default': '', 'required': True, 'description': 'Required testbed ID (e.g. lab, track)'},
        },
        'dataDefs': {},
        'yamlMapping': {'type': 'param', 'key': 'testbed', 'param': 'testbed'},
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# GUARDS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DisableExternalInputGuard(GuardBase):
    """Disable external input during experiment, re-enable on teardown."""
    type_id: ClassVar[str] = 'disable_external_input'

    def setup(self, context: GuardContext):
        pass  # No-op on host side (stub)

    def teardown(self, context: GuardContext):
        pass  # No-op on host side (stub)


@dataclass
class ZeroInputGuard(GuardBase):
    """Zero all control inputs on teardown without changing the control mode."""
    type_id: ClassVar[str] = 'zero_input'

    def setup(self, context: GuardContext):
        pass

    def teardown(self, context: GuardContext):
        pass  # Executed on robot


@dataclass
class RestoreControlConfigGuard(GuardBase):
    """Save the current control config on setup and restore it on teardown."""
    type_id: ClassVar[str] = 'restore_control_config'

    def setup(self, context: GuardContext):
        pass  # Executed on robot

    def teardown(self, context: GuardContext):
        pass  # Executed on robot


@dataclass
class PsiControlGuard(GuardBase):
    """Enable psi (yaw/heading) control on setup, disable on teardown."""
    type_id: ClassVar[str] = 'psi_control'

    def setup(self, context: GuardContext):
        pass  # Executed on robot

    def teardown(self, context: GuardContext):
        pass  # Executed on robot


@dataclass
class ResumeGuard(GuardBase):
    """Block experiment start until the resume interaction event is received.

    Waits for the robot's interaction resume event (triggered by WiFi 'resume'
    command or DPAD_RIGHT button press) before allowing actions to execute.
    If the timeout expires without a resume signal, the experiment fails.
    """
    type_id: ClassVar[str] = 'resume'

    @dataclass
    class Params:
        timeout: float = 60.0

    def setup(self, context: GuardContext):
        pass  # Executed on robot

    def teardown(self, context: GuardContext):
        pass  # No cleanup needed


ALL_BILBO_GUARDS = [
    DisableExternalInputGuard,
    ZeroInputGuard,
    RestoreControlConfigGuard,
    PsiControlGuard,
    ResumeGuard,
]


def register_bilbo_guards(registry: GuardRegistry):
    """Register all BILBO-specific guard types with a registry."""
    for cls in ALL_BILBO_GUARDS:
        registry.register(cls)


BILBO_GUARDS = {
    'disable_external_input': {
        'category': 'guards',
        'description': 'Disable external input during experiment, re-enable on teardown',
        'params': {},
    },
    'zero_input': {
        'category': 'guards',
        'description': 'Zero all control inputs on teardown without changing the control mode',
        'params': {},
    },
    'restore_control_config': {
        'category': 'guards',
        'description': 'Save the current control config on setup and restore it on teardown',
        'params': {},
    },
    'psi_control': {
        'category': 'guards',
        'description': 'Enable psi (yaw/heading) control on setup, disable on teardown',
        'params': {},
    },
    'resume': {
        'category': 'guards',
        'description': 'Wait for resume event before starting experiment actions',
        'params': {
            'timeout': {'required': False, 'default': 60.0, 'type': 'float',
                        'description': 'Seconds to wait for resume before failing'},
        },
    },
}


def get_bilbo_guards_catalog() -> dict:
    """Export BILBO guards for the experiment designer."""
    return dict(BILBO_GUARDS)


# ═══════════════════════════════════════════════════════════════════════════════
# DESIGNER EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

# Category metadata for the experiment designer UI
BILBO_DESIGNER_CATEGORIES = {
    'control':    {'label': 'Control',    'color': '#fc5c65', 'icon': '\u2699'},
    'navigation': {'label': 'Navigation', 'color': '#2bcbba', 'icon': '\u2316'},
    'drive':      {'label': 'Drive',      'color': '#fd9644', 'icon': '\u25B6'},
    'trajectory': {'label': 'Trajectory', 'color': '#a55eea', 'icon': '\u223F'},
    'estimation': {'label': 'Estimation', 'color': '#4ecdc4', 'icon': '\u2295'},
    'audio':      {'label': 'Audio',      'color': '#f7b731', 'icon': '\u266B'},
    'io':         {'label': 'I/O',        'color': '#778ca3', 'icon': '\u25A3'},
    'input':      {'label': 'Input',      'color': '#26de81', 'icon': '\u21C4'},
    'testbed':    {'label': 'Testbed',    'color': '#eb3b5a', 'icon': '\u25A6'},
    'data':       {'label': 'Data',       'color': '#45aaf2', 'icon': '\u25CE'},
}


def export_for_designer(output_dir: str | None = None):
    """Export BILBO actions as JSON for the experiment designer.

    Writes bilbo.json and updates manifest.json in the output directory.

    Args:
        output_dir: Path to experiment_designer/public/actions/.
                    Defaults to auto-detect relative to this file.
    """
    import json
    import os

    if output_dir is None:
        # Auto-detect: this file is at software/robots/bilbo/robot/experiment/bilbo_actions.py
        # Designer is at software/extensions/apps/experiment_designer/public/actions/
        this_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(this_dir, '..', '..', '..', '..', 'extensions',
                                  'apps', 'experiment_designer', 'public', 'actions')
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Build action definitions in the format actionRegistry.js expects
    catalog = get_action_catalog()
    actions = {}
    for entry in catalog:
        type_id = entry['type']
        params = {}
        for pname, pdef in entry['params'].items():
            p = {'required': pdef['required'], 'default': pdef.get('default')}
            if 'type' in pdef:
                p['type'] = pdef['type']
            if 'description' in pdef:
                p['description'] = pdef['description']
            if 'options' in pdef:
                p['options'] = pdef['options']
            params[pname] = p
        actions[type_id] = {
            'category': entry['category'],
            'description': entry['description'],
            'transitionPorts': entry['transitionPorts'],
            'params': params,
            'dataDefs': entry['dataDefs'],
        }

    robot_data = {
        'robot': 'bilbo',
        'label': 'BILBO',
        'categories': BILBO_DESIGNER_CATEGORIES,
        'actions': actions,
        'requirements': BILBO_REQUIREMENTS,
        'guards': BILBO_GUARDS,
    }

    # Write bilbo.json
    robot_file = os.path.join(output_dir, 'bilbo.json')
    with open(robot_file, 'w') as f:
        json.dump(robot_data, f, indent=2)

    # Update manifest.json
    manifest_file = os.path.join(output_dir, 'manifest.json')
    try:
        with open(manifest_file) as f:
            manifest = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        manifest = []
    # Upsert entry
    ids = [e['id'] for e in manifest]
    entry = {'id': 'bilbo', 'label': 'BILBO'}
    if 'bilbo' in ids:
        manifest[ids.index('bilbo')] = entry
    else:
        manifest.append(entry)
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"Exported {len(actions)} BILBO actions to {robot_file}")
    print(f"Updated manifest at {manifest_file}")

    # ── Export templates ─────────────────────────────────────────────────────
    export_templates_for_designer(output_dir)


def export_templates_for_designer(actions_output_dir: str | None = None):
    """Export BILBO experiment templates to the experiment designer.

    Scans experiment_templates/ for YAML files organized in category subfolders,
    copies them to the designer's public/templates/bilbo/ directory, and generates
    a manifest.json for the template registry.

    Args:
        actions_output_dir: Path to experiment_designer/public/actions/.
                            Used to derive the templates output path.
    """
    import json
    import os
    import shutil

    this_dir = os.path.dirname(os.path.abspath(__file__))
    templates_src = os.path.join(this_dir, 'experiment_templates')

    if not os.path.isdir(templates_src):
        print("No experiment_templates/ directory found, skipping template export")
        return

    if actions_output_dir is None:
        actions_output_dir = os.path.join(this_dir, '..', '..', '..', '..', 'extensions',
                                          'apps', 'experiment_designer', 'public', 'actions')
    actions_output_dir = os.path.abspath(actions_output_dir)

    # Templates go to public/templates/bilbo/
    templates_dest = os.path.join(os.path.dirname(actions_output_dir), 'templates', 'bilbo')
    os.makedirs(templates_dest, exist_ok=True)

    # Category label mapping (reuse designer categories)
    category_labels = {k: v['label'] for k, v in BILBO_DESIGNER_CATEGORIES.items()}

    manifest = {}
    template_count = 0

    for folder_name in sorted(os.listdir(templates_src)):
        folder_path = os.path.join(templates_src, folder_name)
        if not os.path.isdir(folder_path):
            continue

        dest_folder = os.path.join(templates_dest, folder_name)
        os.makedirs(dest_folder, exist_ok=True)

        templates = []
        for fname in sorted(os.listdir(folder_path)):
            if not fname.endswith(('.yaml', '.yml')):
                continue

            src_file = os.path.join(folder_path, fname)
            shutil.copy2(src_file, os.path.join(dest_folder, fname))

            # Extract id and description from YAML (simple line parsing, no yaml dependency)
            tmpl_id = fname.rsplit('.', 1)[0]
            tmpl_desc = ''
            try:
                with open(src_file) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('id:'):
                            tmpl_id = line.split(':', 1)[1].strip().strip('"').strip("'")
                        elif line.startswith('description:'):
                            tmpl_desc = line.split(':', 1)[1].strip().strip('"').strip("'")
                        elif line.startswith('actions:') or line.startswith('requirements:'):
                            break
            except Exception:
                pass

            # Label from id: balance_test -> Balance Test
            tmpl_label = tmpl_id.replace('_', ' ').title()

            templates.append({
                'id': tmpl_id,
                'label': tmpl_label,
                'file': f'bilbo/{folder_name}/{fname}',
                'description': tmpl_desc,
            })
            template_count += 1

        if templates:
            manifest[folder_name] = {
                'label': category_labels.get(folder_name, folder_name.title()),
                'templates': templates,
            }

    # Write the robot template manifest as a library entry
    # Format: { "bilbo": { label, folders: { ... } } }
    robot_manifest = {
        'bilbo': {
            'label': 'BILBO',
            'folders': manifest,
        }
    }

    manifest_file = os.path.join(templates_dest, 'manifest.json')
    with open(manifest_file, 'w') as f:
        json.dump(robot_manifest, f, indent=2)

    print(f"Exported {template_count} BILBO templates to {templates_dest}")


if __name__ == '__main__':
    export_for_designer()
