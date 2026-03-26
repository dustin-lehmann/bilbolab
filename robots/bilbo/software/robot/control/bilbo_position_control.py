"""
BILBO Position Control

High-level interface to the position control subsystem on the STM32.
Maintains a local representation of the path state and controller state,
synchronized via serial events from the firmware.

Control modes:
- IDLE: No active command
- TURN_TO_HEADING: Rotating in place to target heading
- DRIVE_TO_POINT: Driving to a single point
- FOLLOW_PATH: Following a dense pre-planned path
"""

import base64
import ctypes
import dataclasses
import enum
import math
import struct
import threading
import time
import zlib
from typing import Any

from core.communication.wifi.bilbolab_wifi_interface import (
    wifi_event_definition, WifiEventContainer, WifiEvent, WifiEventFlag,
)
from core.communication.wifi.data_link import CommandArgument
from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, Event, EventFlag, wait_for_events, OR, TIMEOUT
from core.utils.logging_utils import Logger
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control_definitions import PositionControl_Config, PlanningConfig, BILBO_Control_Mode
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.lowlevel.stm32_general import LOOP_TIME_CONTROL
from robot.lowlevel.stm32_addresses import BILBO_AddressTables, BILBO_PositionControlAddresses
from robot.lowlevel.stm32_control import (
    BILBO_PositionControl_Event_Message,
    position_control_event_t,
    position_control_event_data,
    bilbo_position_control_data,
    bilbo_position_control_data_t,
    path_point_t,
    bilbo_path_start_cmd_t,
    turn_to_heading_command_t,
    move_to_point_command_t,
    bilbo_position_control_config_t,
)
from robot.lowlevel.stm32_sample import BILBO_LL_Sample
from core.utils.control_lib.lib_control.motion_planning import (
    plan_path as _plan_path,
    plan_path_mp as _plan_path_mp,
    Waypoint as PlannerWaypoint,
    CircleObstacle,
    BoxObstacle,
    Bounds,
    Obstacle,
    PRMRoadmap,
    PRMConfig as PlannerPRMConfig,
)


# =============================================================================
# ENUMS
# =============================================================================

class PositionControlMode(enum.IntEnum):
    """Position control operating modes"""
    IDLE = 0
    TURN_TO_HEADING = 1
    DRIVE_TO_POINT = 2
    FOLLOW_PATH = 3


class PathState(enum.IntEnum):
    """Path execution state"""
    IDLE = 0
    RUNNING = 1
    PAUSED = 2


# =============================================================================
# DATA CLASSES
# =============================================================================

def position_control_config_to_ctypes(config: PositionControl_Config) -> bilbo_position_control_config_t:
    """Convert PositionControl_Config to ctypes struct for serial transmission"""
    return bilbo_position_control_config_t(
        Ts=LOOP_TIME_CONTROL,
        kp_angular=config.kp_angular,
        ki_angular=config.ki_angular,
        kp_angular_heading=config.kp_angular_heading,
        ki_angular_heading=config.ki_angular_heading,
        kp_linear=config.kp_linear,
        ki_linear=config.ki_linear,
        kd_linear=config.kd_linear,
        max_speed=config.max_speed,
        max_turn_rate=config.max_turn_rate,
        lookahead_base=config.lookahead_base,
        lookahead_min=config.lookahead_min,
        arrival_tolerance=config.arrival_tolerance,
        arrival_dwell_time=config.arrival_dwell_time,
        stop_dwell_time=config.stop_dwell_time,
        reverse_enter_angle=config.reverse_enter_angle,
        reverse_exit_angle=config.reverse_exit_angle,
        decel_limit=config.decel_limit,
        curvature_gain=config.curvature_gain,
        curvature_lookahead=config.curvature_lookahead,
    )


@dataclasses.dataclass
class PositionControlData:
    """Telemetry data from the position controller"""
    mode: PositionControlMode = PositionControlMode.IDLE
    path_state: PathState = PathState.IDLE
    buffer_capacity: int = 0  # max path points the STM32 buffer can hold
    buffer_used: int = 0  # current path points in STM32 buffer
    path_point_count: int = 0
    current_index: int = 0
    carrot_x: float = 0.0
    carrot_y: float = 0.0
    carrot_distance: float = 0.0  # [m] distance from robot to carrot
    heading_error: float = 0.0  # [rad] heading error to carrot
    speed_limit: float = 0.0  # [m/s] current speed limit
    v_cmd: float = 0.0
    psi_dot_cmd: float = 0.0
    elapsed_time: float = 0.0
    remaining_path_length: float = 0.0
    progress: float = 0.0  # floating-point index [0, N-1]


@dataclasses.dataclass
class MoveToPointCommand:
    """Tracking data for active move_to_point command"""
    x: float = 0.0
    y: float = 0.0
    max_speed: float = 0.0
    timeout: float = 0.0
    active: bool = False


@dataclasses.dataclass
class TurnToHeadingCommand:
    """Tracking data for active turn_to_heading command"""
    heading: float = 0.0
    max_angular_speed: float = 0.0
    timeout: float = 0.0
    active: bool = False


@dataclasses.dataclass
class MoveToPoseCommand:
    """Tracking data for active move_to_pose command"""
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    max_speed: float = 0.0
    max_angular_speed: float = 0.0
    timeout: float = 0.0
    active: bool = False
    phase: str = ''  # 'move' or 'turn'


# =============================================================================
# EVENTS AND CALLBACKS
# =============================================================================

@event_definition
class PositionControlEvents:
    """Events emitted by the position controller"""
    # Path events
    path_started: Event
    path_paused: Event
    path_resumed: Event
    path_finished: Event
    path_aborted: Event
    path_timeout: Event

    # Stop events (dense path uses stop indices instead of waypoints)
    stop_reached: Event = Event(flags=EventFlag('index', int))
    stop_completed: Event = Event(flags=EventFlag('index', int))
    path_buffer_full: Event  # STM32 buffer is full

    # Single-point command events
    move_to_point_started: Event
    move_to_point_completed: Event
    move_to_point_timeout: Event
    turn_to_heading_started: Event
    turn_to_heading_completed: Event
    turn_to_heading_timeout: Event

    # Compound pose command events
    move_to_pose_started: Event
    move_to_pose_completed: Event
    move_to_pose_timeout: Event

    # Mode change
    mode_changed: Event = Event(flags=EventFlag('mode', PositionControlMode))


@callback_definition
class PositionControlCallbacks:
    """Callbacks for position control events"""
    path_started: CallbackContainer
    path_finished: CallbackContainer
    path_timeout: CallbackContainer
    path_aborted: CallbackContainer
    stop_completed: CallbackContainer
    path_buffer_full: CallbackContainer
    mode_changed: CallbackContainer


# =============================================================================
# WIFI EVENTS
# =============================================================================

@dataclasses.dataclass
class PositionControlCommonData:
    """Common data sent with every position control WiFi event"""
    mode: int = 0
    mode_name: str = ''
    path_state: int = 0
    path_point_count: int = 0
    current_index: int = 0


# Template: every position control WiFi event carries a 'group' flag
_PC_WIFI_EVENT = WifiEvent(data_type=dict, flags=WifiEventFlag('group', str))


@wifi_event_definition
class PositionControlWifiEvents(WifiEventContainer):
    """WiFi events sent by position control to host"""
    # Path events
    path_loaded: WifiEvent = _PC_WIFI_EVENT
    path_started: WifiEvent = _PC_WIFI_EVENT
    path_paused: WifiEvent = _PC_WIFI_EVENT
    path_resumed: WifiEvent = _PC_WIFI_EVENT
    path_finished: WifiEvent = _PC_WIFI_EVENT
    path_timeout: WifiEvent = _PC_WIFI_EVENT
    path_aborted: WifiEvent = _PC_WIFI_EVENT

    # Stop events
    stop_reached: WifiEvent = _PC_WIFI_EVENT
    stop_completed: WifiEvent = _PC_WIFI_EVENT
    path_buffer_full: WifiEvent = _PC_WIFI_EVENT

    # Single-point command events
    move_to_point_started: WifiEvent = _PC_WIFI_EVENT
    move_to_point_completed: WifiEvent = _PC_WIFI_EVENT
    move_to_point_timeout: WifiEvent = _PC_WIFI_EVENT
    turn_to_heading_started: WifiEvent = _PC_WIFI_EVENT
    turn_to_heading_completed: WifiEvent = _PC_WIFI_EVENT
    turn_to_heading_timeout: WifiEvent = _PC_WIFI_EVENT

    # Compound pose command events
    move_to_pose_started: WifiEvent = _PC_WIFI_EVENT
    move_to_pose_completed: WifiEvent = _PC_WIFI_EVENT
    move_to_pose_timeout: WifiEvent = _PC_WIFI_EVENT

    # Planning
    path_planning_started: WifiEvent = _PC_WIFI_EVENT
    path_planned: WifiEvent = _PC_WIFI_EVENT
    path_cleared: WifiEvent = _PC_WIFI_EVENT

    # Mode change
    mode_changed: WifiEvent = _PC_WIFI_EVENT


# =============================================================================
# MAIN CLASS
# =============================================================================

class BILBO_PositionControl:
    """
    High-level interface to STM32 position control subsystem.

    For FOLLOW_PATH mode, dense pre-planned paths are sent as arrays of (x, y)
    path points with optional stop indices. The firmware handles adaptive speed
    from inter-point spacing and pure-pursuit tracking.
    """

    def __init__(self, common: BILBO_Common,
                 estimation: BILBO_Estimation,
                 communication: BILBO_Communication):

        self.logger = Logger("POS_CTRL", "DEBUG")
        self.common = common
        self.communication = communication
        self.estimation = estimation

        # Events and callbacks
        self.events = PositionControlEvents()
        self.callbacks = PositionControlCallbacks()

        # WiFi events (registered on the interface, each sent as its own event)
        self.wifi_events = PositionControlWifiEvents(
            wifi=communication.wifi.wifi,
            id='position_control',
        )

        # Local state (mirrors STM32)
        self._mode = PositionControlMode.IDLE
        self._mode_event_time: float = 0.0  # timestamp of last event-driven mode change
        self._path_state = PathState.IDLE
        self._path_point_count: int = 0
        self._current_index: int = 0
        self._data = PositionControlData()
        self._config = PositionControl_Config()
        self._planning_config = PlanningConfig()
        self._prm_roadmap: PRMRoadmap | None = None

        # Track top-level control mode for validation
        self._top_level_control_mode = None

        # Command tracking
        self._command_id_counter: int = 0

        # Track active single-point commands for logging
        self._current_move_to_point = MoveToPointCommand()
        self._current_turn_to_heading = TurnToHeadingCommand()
        self._current_move_to_pose = MoveToPoseCommand()

        # Track current path data for visualization
        self._current_path_points: list[tuple[float, float]] = []
        self._current_path_data: dict | list | None = None
        self._current_path_settings: dict = {}
        self._current_path_waypoints: list[dict] | None = None

        # Testbed manager reference (set after construction via set_testbed_manager)
        self.testbed_manager = None

        # Register for position control events from STM32
        self.communication.serial.callbacks.event.register(
            self._handle_position_control_event,
            parameters={'messages': [BILBO_PositionControl_Event_Message]}
        )

        # Register for sample updates to sync state
        self.communication.callbacks.rx_stm32_sample.register(self._lowlevel_sample_callback)

        # Register for control mode changes
        self.common.events.control_mode_change.on(self._on_control_mode_change)

        # Register WiFi commands
        self._register_wifi_commands()

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def mode(self) -> PositionControlMode:
        """Current position control mode"""
        return self._mode

    @property
    def path_state(self) -> PathState:
        """Current path execution state"""
        return self._path_state

    @property
    def path_point_count(self) -> int:
        """Number of path points loaded on STM32"""
        return self._path_point_count

    @property
    def current_index(self) -> int:
        """Current path index (floor of progress)"""
        return self._current_index

    @property
    def is_busy(self) -> bool:
        """True if executing any command"""
        return self._mode != PositionControlMode.IDLE

    def _set_mode(self, mode: PositionControlMode):
        """Set mode from an authoritative source (event handler, control mode change).
        Stamps a timestamp so the sample callback won't overwrite with stale data."""
        self._mode = mode
        self._mode_event_time = time.time()

    @property
    def is_path_running(self) -> bool:
        """True if currently following a path"""
        return self._mode == PositionControlMode.FOLLOW_PATH and self._path_state == PathState.RUNNING

    @property
    def data(self) -> PositionControlData:
        """Current telemetry data"""
        return self._data

    @property
    def buffer_capacity(self) -> int:
        """Maximum path points the STM32 buffer can hold"""
        return self._data.buffer_capacity

    @property
    def buffer_used(self) -> int:
        """Current number of path points in STM32 buffer"""
        return self._data.buffer_used

    @property
    def buffer_available(self) -> int:
        """Number of path points that can still be added"""
        return max(0, self._data.buffer_capacity - self._data.buffer_used)

    @property
    def current_move_to_point_command(self) -> MoveToPointCommand | None:
        """Active move_to_point command, or None if not active"""
        return self._current_move_to_point if self._current_move_to_point.active else None

    @property
    def current_turn_to_heading_command(self) -> TurnToHeadingCommand | None:
        """Active turn_to_heading command, or None if not active"""
        return self._current_turn_to_heading if self._current_turn_to_heading.active else None

    @property
    def current_move_to_pose_command(self) -> MoveToPoseCommand | None:
        """Active move_to_pose command, or None if not active"""
        return self._current_move_to_pose if self._current_move_to_pose.active else None

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    def set_config(self, config: PositionControl_Config) -> bool:
        """Set position control configuration on STM32"""
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_PositionControlAddresses.SET_CONFIG,
            input_type=bilbo_position_control_config_t,
            output_type=ctypes.c_bool,
            data=position_control_config_to_ctypes(config)
        )
        if result:
            self._config = config
            self.logger.info("Position control config set successfully")
        else:
            self.logger.error("Failed to set position control config")
        return result or False

    def get_config(self) -> PositionControl_Config:
        """Get current configuration"""
        return self._config

    def set_planning_config(self, config: PlanningConfig):
        """Set planning config (Python-only, not sent to firmware)."""
        self._planning_config = config
        self._prm_roadmap = None  # invalidate — will rebuild on next PRM query
        self.logger.info(f"Planning config set: method={config.method}, smoothing={config.smoothing}")

    def build_prm_map(self):
        """Build (or rebuild) the PRM roadmap in a separate process (non-blocking for GIL)."""
        obstacles = self._get_planner_obstacles()
        bounds = self._get_testbed_bounds()
        if bounds is None:
            self.logger.warning("Cannot build PRM: no testbed bounds")
            return
        cfg = self._planning_config
        prm_cfg = PlannerPRMConfig(
            n_samples=cfg.prm.n_samples,
            k_neighbors=cfg.prm.k_neighbors,
            connection_radius=cfg.prm.connection_radius,
            clearance_weight=cfg.clearance_weight,
            clearance_threshold=cfg.clearance_threshold,
            seed=cfg.prm.seed,
        )
        self._prm_roadmap = PRMRoadmap(obstacles, bounds, prm_cfg)
        self._prm_roadmap.build_mp()
        self.logger.info(f"PRM roadmap built: {self._prm_roadmap.node_count} nodes, "
                         f"{self._prm_roadmap.edge_count} edges")

    # =========================================================================
    # TESTBED MANAGER
    # =========================================================================

    def set_testbed_manager(self, testbed_manager):
        """Set the testbed manager reference (called after construction)."""
        self.testbed_manager = testbed_manager

    def _get_planner_obstacles(self, extra_obstacles: list[dict] | None = None) -> list[Obstacle]:
        """Collect obstacles from testbed manager (inflated by safety_margin) and merge with optional per-call extras."""
        from robot.testbed.obstacles import CircleObstacle as TestbedCircle, BoxObstacle as TestbedBox
        pad = self._planning_config.safety_margin
        result = []
        # Convert testbed manager obstacles to planner format with padding.
        if self.testbed_manager is not None:
            for obs in self.testbed_manager.obstacles:
                if isinstance(obs, TestbedCircle):
                    result.append(CircleObstacle(cx=obs.x, cy=obs.y, radius=obs.radius + pad))
                elif isinstance(obs, TestbedBox):
                    result.append(BoxObstacle(cx=obs.x, cy=obs.y,
                                              width=obs.width + 2 * pad,
                                              height=obs.height + 2 * pad,
                                              psi=obs.psi))
        # Add per-call extras (no padding — caller controls sizing)
        if extra_obstacles:
            result.extend(self._parse_planner_obstacles(extra_obstacles))
        return result

    def _get_testbed_bounds(self) -> Bounds | None:
        """Get workspace bounds from testbed manager config, if available."""
        if self.testbed_manager is None or self.testbed_manager.testbed_config is None:
            return None
        size = self.testbed_manager.testbed_config.size
        return Bounds(x_min=size.x_min, x_max=size.x_max, y_min=size.y_min, y_max=size.y_max)

    def _log_planner_inputs(self, start, target, waypoints, obstacles, bounds):
        """Debug-log all inputs passed to the motion planner."""
        self.logger.debug(f"--- Planner inputs ---")
        self.logger.debug(f"  start:  ({start[0]:.3f}, {start[1]:.3f})")
        self.logger.debug(f"  target: ({target[0]:.3f}, {target[1]:.3f})")
        if bounds is not None:
            self.logger.debug(f"  bounds: x=[{bounds.x_min:.3f}, {bounds.x_max:.3f}] "
                              f"y=[{bounds.y_min:.3f}, {bounds.y_max:.3f}]")
        else:
            self.logger.debug(f"  bounds: None (planner will infer)")
        for i, wp in enumerate(waypoints or []):
            self.logger.debug(f"  waypoint[{i}]: ({wp.x:.3f}, {wp.y:.3f}) weight={wp.weight:.2f}")
        for i, obs in enumerate(obstacles or []):
            if isinstance(obs, CircleObstacle):
                self.logger.debug(f"  obstacle[{i}]: circle cx={obs.cx:.3f} cy={obs.cy:.3f} r={obs.radius:.3f}")
            elif isinstance(obs, BoxObstacle):
                self.logger.debug(f"  obstacle[{i}]: box cx={obs.cx:.3f} cy={obs.cy:.3f} "
                                  f"w={obs.width:.3f} h={obs.height:.3f}")
        cfg = self._planning_config
        self.logger.debug(f"  method: {cfg.method}")
        self.logger.debug(f"  smoothing: {cfg.smoothing:.2f}")
        if cfg.method == 'rrt':
            self.logger.debug(f"  rrt_star: {cfg.rrt.rrt_star}, max_iterations: {cfg.rrt.max_iterations}")
            self.logger.debug(
                f"  step_size: {cfg.rrt.step_size}, goal_bias: {cfg.rrt.goal_bias}, rewire_radius: {cfg.rrt.rewire_radius}")
        else:
            self.logger.debug(f"  prm n_samples: {cfg.prm.n_samples}, k_neighbors: {cfg.prm.k_neighbors}")
        self.logger.debug(f"  safety_margin: {cfg.safety_margin}")
        if cfg.clearance_weight > 0:
            self.logger.debug(
                f"  clearance_weight: {cfg.clearance_weight}, clearance_threshold: {cfg.clearance_threshold}")
        self.logger.debug(f"--- end planner inputs ---")

    # =========================================================================
    # PATH MANAGEMENT
    # =========================================================================

    def clear_path(self) -> bool:
        """Clear all path points from STM32 buffer"""
        if self.is_busy:
            self.logger.warning("Cannot clear path while busy")
            return False

        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_PositionControlAddresses.CLEAR_PATH,
            input_type=None,
            output_type=ctypes.c_bool,
        )

        if result:
            self._path_point_count = 0
            self._current_index = 0
            self.logger.debug("Path cleared")
            self.wifi_events.path_cleared.send(
                data=self._common_event_data(),
                flags=self._WIFI_FLAGS,
            )
        else:
            self.logger.error("Failed to clear path on STM32")

        return result or False

    def add_stop_index(self, index: int) -> bool:
        """Mark a path point index as a STOP point on STM32"""
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            self.logger.warning("Cannot add stop index when not in POSITION mode")
            return False

        if self.is_busy:
            self.logger.warning("Cannot add stop index while busy")
            return False

        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_PositionControlAddresses.ADD_STOP_INDEX,
            input_type=ctypes.c_uint16,
            output_type=ctypes.c_bool,
            data=ctypes.c_uint16(index)
        )

        if result:
            self.logger.debug(f"Added stop index {index}")
        else:
            self.logger.error(f"Failed to add stop index {index}")

        return result or False

    def get_path_point_count(self) -> int:
        """Get current number of path points on STM32"""
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_PositionControlAddresses.READ_PATH_POINT_COUNT,
            input_type=None,
            output_type=ctypes.c_uint16
        )
        if result is not None:
            self._path_point_count = result
        return self._path_point_count

    @staticmethod
    def _path_points_to_bytes(points: list[tuple[float, float]]) -> bytes:
        """Convert a list of (x, y) tuples to a flat byte array of path_point_t structs."""
        ArrayType = path_point_t * len(points)
        c_array = ArrayType()
        for i, (x, y) in enumerate(points):
            c_array[i].x = x
            c_array[i].y = y
        return bytes(c_array)

    def upload_path_spi(self, points: list[tuple[float, float]]) -> bool:
        """Upload path points to STM32 via SPI bulk transfer.

        Sends all points in a single SPI DMA transfer, then verifies the
        firmware received the correct count by reading back the path point
        count register over UART.

        Args:
            points: List of (x, y) tuples to upload.

        Returns:
            True if the firmware confirmed receiving the correct number of points.
        """
        path_bytes = self._path_points_to_bytes(points)
        self.communication.spi.sendPathData(len(points), path_bytes)

        # Wait for firmware to process the DMA transfer
        time.sleep(0.05)

        # Verify by reading back the path point count via UART
        fw_count = self.get_path_point_count()
        if fw_count != len(points):
            self.logger.error(
                f"SPI path upload verification failed: sent {len(points)} points, "
                f"firmware reports {fw_count}"
            )
            return False

        self._path_point_count = fw_count
        return True

    # =========================================================================
    # PATH FOLLOWING
    # =========================================================================

    # ------------------------------------------------------------------------------------------------------------------
    def start_path(self, max_speed: float = 0.0,
                   max_spacing: float = 0.0,
                   timeout: float = 0.0,
                   allow_reverse: bool = False) -> bool:
        """
        Start following the loaded dense path.

        Args:
            max_speed: Speed override [m/s] (0 = use config default)
            max_spacing: Max inter-point spacing [m] (0 = auto-detect from path)
            timeout: Maximum time for path execution [s] (0 = no timeout)
            allow_reverse: If True, robot may drive backwards when efficient
        """
        if self.is_busy:
            self.logger.warning("Cannot start path: already busy")
            return False

        if self._path_point_count < 2:
            self.logger.warning("Cannot start path: need at least 2 path points")
            return False

        cmd = bilbo_path_start_cmd_t(
            max_speed=max_speed,
            max_spacing=max_spacing,
            timeout=timeout,
            allow_reverse=1 if allow_reverse else 0
        )

        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_PositionControlAddresses.START_PATH,
            input_type=bilbo_path_start_cmd_t,
            output_type=ctypes.c_bool,
            data=cmd
        )

        if result:
            self._current_index = 0
            # Update path settings
            self._current_path_settings = {
                'max_speed': max_speed,
                'max_spacing': max_spacing,
                'allow_reverse': allow_reverse,
                'timeout': timeout
            }
            self.logger.info(f"Started path with {self._path_point_count} points")
        else:
            self.logger.error("Failed to start path on STM32")

        return result or False

    # ------------------------------------------------------------------------------------------------------------------
    def abort_path(self) -> bool:
        """Abort path execution"""
        if self._mode != PositionControlMode.FOLLOW_PATH:
            self.logger.warning("Cannot stop: not following path")
            return False

        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_PositionControlAddresses.ABORT_PATH,
            input_type=None,
            output_type=ctypes.c_bool,
        )

        if result:
            self.logger.info("Path aborted")
        else:
            self.logger.error("Failed to stop path")

        return result or False

    # ------------------------------------------------------------------------------------------------------------------
    def load_path(self, path_data: 'dict | list[tuple[float, float]]',
                  start: bool = False,
                  clear_existing: bool = True,
                  stop_indices: list[int] | None = None,
                  max_speed: float | None = None,
                  max_spacing: float | None = None,
                  allow_reverse: bool | None = None,
                  timeout: float | None = None) -> bool:
        """
        Load a dense path onto the STM32.

        Accepts either:
        - A list of (x, y) tuples (e.g. output of plan_path())
        - A dict with path data and optional settings

        List format:
            [(x0, y0), (x1, y1), ...]

        Dict format:
            {
                "max_speed": 0.3,         # optional, m/s (0 = use config default)
                "max_spacing": 0.0,       # optional, m (0 = auto-detect)
                "allow_reverse": false,   # optional, default: false
                "timeout": 30.0,          # optional, seconds (0 = no timeout)
                "points": [
                    {"x": 1.0, "y": 0.0},
                    {"x": 1.01, "y": 0.02},
                    ...
                ],
                "stop_indices": [50, 200]  # optional, indices of points where robot should stop
            }

        Also accepts legacy dict format with "waypoints" key (treated as dense points).

        Args:
            path_data: Path as list of (x,y) tuples or dict with points and settings
            start: If True, automatically start the path after loading
            clear_existing: If True, clear existing path before loading
            stop_indices: Stop indices (used when path_data is a list; for dicts,
                can also be specified inside the dict)
            max_speed: Override for max_speed (None = use dict value or default 0)
            max_spacing: Override for max_spacing (None = use dict value or default 0)
            allow_reverse: Override for allow_reverse (None = use dict value or default False)
            timeout: Override for timeout (None = use dict value or default 0)

        Returns:
            True if path was loaded (and started if requested) successfully
        """
        # Normalize input: convert list of tuples to internal dict-like handling
        if isinstance(path_data, list):
            parsed_points = []
            for i, pt in enumerate(path_data):
                try:
                    parsed_points.append((float(pt[0]), float(pt[1])))
                except (ValueError, IndexError, TypeError) as e:
                    self.logger.error(f"Failed to parse path point {i}: {e}")
                    return False
            effective_stop_indices = list(stop_indices) if stop_indices else []
            effective_max_speed = max_speed if max_speed is not None else 0.0
            effective_max_spacing = max_spacing if max_spacing is not None else 0.0
            effective_allow_reverse = allow_reverse if allow_reverse is not None else False
            effective_timeout = timeout if timeout is not None else 0.0
        elif isinstance(path_data, dict):
            # Extract optional path settings from dict (function args override if provided)
            dict_max_speed = float(path_data.get('max_speed', 0.0))
            dict_max_spacing = float(path_data.get('max_spacing', 0.0))
            dict_allow_reverse = bool(path_data.get('allow_reverse', False))
            dict_timeout = float(path_data.get('timeout', 0.0))

            effective_max_speed = max_speed if max_speed is not None else dict_max_speed
            effective_max_spacing = max_spacing if max_spacing is not None else dict_max_spacing
            effective_allow_reverse = allow_reverse if allow_reverse is not None else dict_allow_reverse
            effective_timeout = timeout if timeout is not None else dict_timeout

            # Extract points (support both "points" and legacy "waypoints" key)
            points_data = path_data.get('points', path_data.get('waypoints'))
            if points_data is None:
                self.logger.error("Path data missing 'points' key")
                return False

            if not isinstance(points_data, list) or len(points_data) == 0:
                self.logger.error("Path data 'points' must be a non-empty list")
                return False

            # Parse points — support both dict {"x":..,"y":..} and tuple formats
            parsed_points = []
            for i, pt in enumerate(points_data):
                try:
                    if isinstance(pt, dict):
                        parsed_points.append((float(pt['x']), float(pt['y'])))
                    else:
                        parsed_points.append((float(pt[0]), float(pt[1])))
                except (ValueError, KeyError, IndexError, TypeError) as e:
                    self.logger.error(f"Failed to parse path point {i}: {e}")
                    return False

            # Stop indices: function arg overrides dict value
            dict_stop_indices = path_data.get('stop_indices', [])
            effective_stop_indices = list(stop_indices) if stop_indices is not None else list(dict_stop_indices)
        else:
            self.logger.error(f"path_data must be a list or dict, got {type(path_data).__name__}")
            return False

        if len(parsed_points) == 0:
            self.logger.error("No path points to load")
            return False

        # Clear existing path if requested
        if clear_existing:
            if not self.clear_path():
                self.logger.error("Failed to clear existing path")
                return False
            time.sleep(0.005)  # yield GIL

        # Upload all path points via SPI (single bulk transfer)
        total = len(parsed_points)
        self.logger.info(f"Loading {total} path points via SPI")
        if not self.upload_path_spi(parsed_points):
            self.logger.error("SPI path upload failed")
            return False
        time.sleep(0.005)  # yield GIL

        # Add stop indices
        for idx in effective_stop_indices:
            idx = int(idx)
            if not self.add_stop_index(idx):
                self.logger.error(f"Failed to add stop index {idx}")
                return False

        self.logger.info(f"Loaded path: {total} points, {len(effective_stop_indices)} stops")
        time.sleep(0.005)  # yield GIL

        # Store path data for visualization
        self._current_path_points = parsed_points
        self._current_path_data = path_data
        self._current_path_settings = {
            'max_speed': effective_max_speed,
            'max_spacing': effective_max_spacing,
            'allow_reverse': effective_allow_reverse,
            'timeout': effective_timeout
        }

        # Send path_loaded event with compressed path points for host visualization
        self.wifi_events.path_loaded.send(
            data=self._common_event_data(
                path_point_count=total,
                stop_indices=effective_stop_indices,
                settings=self._current_path_settings,
                waypoints=self._current_path_waypoints,
                path_points_compressed=self._compress_path_points(parsed_points),
            ),
            flags=self._WIFI_FLAGS,
        )
        self._current_path_waypoints = None

        # Start path if requested
        if start:
            return self.start_path(
                max_speed=effective_max_speed,
                max_spacing=effective_max_spacing,
                timeout=effective_timeout,
                allow_reverse=effective_allow_reverse
            )

        return True

    # =========================================================================
    # MOTION PLANNING + PATH FOLLOWING
    # =========================================================================

    def _run_planner(self, start, target, waypoints, obstacles, bounds, seed,
                     target_heading=None, heading_strength=1.0):
        """Dispatch to RRT or PRM based on config.method."""
        if self._planning_config.method == 'prm':
            return self._plan_prm(start, target, waypoints, bounds,
                                  target_heading=target_heading,
                                  heading_strength=heading_strength)
        return self._plan_rrt(start, target, waypoints, obstacles, bounds, seed,
                              target_heading=target_heading,
                              heading_strength=heading_strength)

    def _plan_rrt(self, start, target, waypoints, obstacles, bounds, seed,
                  target_heading=None, heading_strength=1.0):
        """Plan using RRT/RRT* (existing behavior, extracted)."""
        cfg = self._planning_config
        return _plan_path_mp(
            timeout=10.0,
            start=start,
            end=target,
            waypoints=waypoints or None,
            obstacles=obstacles or None,
            bounds=bounds,
            seed=seed,
            smoothing=cfg.smoothing,
            rrt_star=cfg.rrt.rrt_star,
            max_iterations=cfg.rrt.max_iterations,
            clearance_weight=cfg.clearance_weight,
            clearance_threshold=cfg.clearance_threshold,
            step_size=cfg.rrt.step_size,
            goal_bias=cfg.rrt.goal_bias,
            rewire_radius=cfg.rrt.rewire_radius,
            target_heading=target_heading,
            heading_strength=heading_strength,
        )

    def _plan_prm(self, start, target, waypoints, bounds, target_heading=None,
                  heading_strength=1.0):
        """Plan using PRM. Roadmap must be built beforehand via build_prm_map()."""
        if self._prm_roadmap is None or not self._prm_roadmap.is_built():
            self.logger.error("PRM roadmap not built. Call build_prm_map() first.")
            raise RuntimeError("PRM roadmap not built. Call build_prm_map() first.")
        cfg = self._planning_config
        return self._prm_roadmap.query(
            start=start,
            end=target,
            waypoints=waypoints or None,
            smoothing=cfg.smoothing,
            target_heading=target_heading,
            heading_strength=heading_strength,
        )

    def plan_and_follow(self,
                        target: tuple[float, float],
                        waypoints: list[dict | tuple] | None = None,
                        obstacles: list[dict] | None = None,
                        bounds: dict | tuple | None = None,
                        stop_indices: list[int] | None = None,
                        max_speed: float = 0.0,
                        max_spacing: float = 0.0,
                        timeout: float = 0.0,
                        allow_reverse: bool = False,
                        seed: int | None = None,
                        start: tuple[float, float] | None = None,
                        blocking: bool = False,
                        target_heading: float | None = None,
                        heading_strength: float = 1.0) -> bool:
        """
        Plan a collision-free path from the current position to target,
        load it onto the STM32, and start following it.

        Uses the stored obstacle list plus any extra obstacles passed here.

        Args:
            target: (x, y) destination in world coordinates [m]
            waypoints: Intermediate points with proximity weights.
                Each entry is either:
                - (x, y) or (x, y, weight) tuple
                - {"x": ..., "y": ..., "weight": ...} dict
            obstacles: Extra obstacle dicts (merged with stored obstacles):
                - {"type": "circle", "cx": ..., "cy": ..., "radius": ...}
                - {"type": "box", "cx": ..., "cy": ..., "width": ..., "height": ...}
            bounds: Workspace limits as dict or (x_min, x_max, y_min, y_max) tuple.
            stop_indices: Path point indices where the robot should pause.
            max_speed: Speed limit [m/s] (0 = use config default)
            max_spacing: Max inter-point spacing [m] (0 = auto-detect)
            timeout: Path timeout [s] (0 = no timeout)
            allow_reverse: Allow reverse driving
            seed: RNG seed for motion planner reproducibility
            target_heading: Desired heading [rad] at the target (None = unconstrained)
            heading_strength: Magnitude of the clamped end tangent (default 1.0).
                Larger values create a longer approach corridor aligned with target_heading.
            start: Override start position (default: current estimation state)
            blocking: If True, block until path finished or timeout

        Returns:
            True if path was planned, loaded, and started successfully
        """
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            self.logger.warning(
                f"Cannot plan path: not in POSITION mode (current: "
                f"{self._top_level_control_mode.name if self._top_level_control_mode else 'None'})"
            )
            return False

        # Get start position
        if start is None:
            start = self._get_current_position()
            if start is None:
                self.logger.error("Cannot plan path: no position estimate available")
                return False

        # Parse waypoints
        planner_waypoints = self._parse_planner_waypoints(waypoints)

        # Merge stored obstacles with per-call extras
        planner_obstacles = self._get_planner_obstacles(obstacles)

        # Parse bounds (explicit > testbed > None → planner infers)
        planner_bounds = self._parse_planner_bounds(bounds) if bounds is not None else self._get_testbed_bounds()

        # Notify host that planning has started
        self.wifi_events.path_planning_started.send(
            data=self._common_event_data(
                start={'x': start[0], 'y': start[1]},
                target={'x': target[0], 'y': target[1]},
                waypoints=[{'x': wp.x, 'y': wp.y, 'weight': wp.weight} for wp in planner_waypoints],
            ),
            flags=self._WIFI_FLAGS,
        )

        # Run motion planner
        try:
            self.logger.info(
                f"Planning path: ({start[0]:.2f}, {start[1]:.2f}) → "
                f"({target[0]:.2f}, {target[1]:.2f}), "
                f"{len(planner_waypoints)} waypoints, {len(planner_obstacles)} obstacles"
            )
            self._log_planner_inputs(start, target, planner_waypoints, planner_obstacles, planner_bounds)
            dense_points = self._run_planner(
                start, target, planner_waypoints, planner_obstacles, planner_bounds, seed,
                target_heading=target_heading, heading_strength=heading_strength)
        except (ValueError, RuntimeError, TimeoutError) as e:
            self.logger.error(f"Motion planning failed: {e}")
            return False

        if not dense_points or len(dense_points) < 2:
            self.logger.error(
                f"Motion planner returned insufficient points ({len(dense_points) if dense_points else 0})")
            return False

        self.logger.info(f"Motion planner produced {len(dense_points)} dense path points")
        time.sleep(0.005)  # yield GIL

        # Compute stop indices from STOP waypoints if none were explicitly provided
        if stop_indices is None:
            stop_indices = self._compute_stop_indices_from_waypoints(waypoints, dense_points)
            if stop_indices:
                self.logger.info(f"STOP waypoints mapped to path indices: {stop_indices}")

        # Load and start
        result = self.load_path(
            path_data=dense_points,
            start=True,
            stop_indices=stop_indices,
            max_speed=max_speed,
            max_spacing=max_spacing,
            timeout=timeout,
            allow_reverse=allow_reverse,
        )

        if not result:
            return False

        if not blocking:
            return True

        # Block until path finishes or times out
        wait_timeout = timeout + 5.0 if timeout > 0 else 120.0
        data, trace = wait_for_events(
            OR(
                self.events.path_finished,
                self.events.path_timeout,
                self.events.path_aborted,
            ),
            timeout=wait_timeout
        )

        if data is TIMEOUT:
            self.logger.warning("plan_and_follow: Python wait expired")
            self.abort_path()
            return False

        if trace.caused_by(self.events.path_finished):
            self.logger.info("plan_and_follow: path finished successfully")
            return True

        if trace.caused_by(self.events.path_timeout):
            self.logger.warning("plan_and_follow: firmware path timeout")
            return False

        self.logger.warning("plan_and_follow: path aborted")
        return False

    # ------------------------------------------------------------------------------------------------------------------
    def plan_path(self,
                  target: tuple[float, float],
                  waypoints: list[dict | tuple] | None = None,
                  obstacles: list[dict] | None = None,
                  bounds: dict | tuple | None = None,
                  seed: int | None = None,
                  start: tuple[float, float] | None = None,
                  target_heading: float | None = None,
                  heading_strength: float = 1.0) -> list[tuple[float, float]] | None:
        """
        Plan a path without loading or starting it. Useful for preview/visualization.
        Uses stored obstacles merged with any extra obstacles passed here.

        Returns the list of dense (x, y) path points, or None on failure.
        """
        if start is None:
            start = self._get_current_position()
            if start is None:
                self.logger.error("Cannot plan path: no position estimate available")
                return None

        planner_waypoints = self._parse_planner_waypoints(waypoints)
        planner_obstacles = self._get_planner_obstacles(obstacles)
        planner_bounds = self._parse_planner_bounds(bounds) if bounds is not None else self._get_testbed_bounds()

        self._log_planner_inputs(start, target, planner_waypoints, planner_obstacles, planner_bounds)

        self.wifi_events.path_planning_started.send(
            data=self._common_event_data(
                start={'x': start[0], 'y': start[1]},
                target={'x': target[0], 'y': target[1]},
                waypoints=[{'x': wp.x, 'y': wp.y, 'weight': wp.weight} for wp in planner_waypoints],
            ),
            flags=self._WIFI_FLAGS,
        )

        try:
            return self._run_planner(
                start, target, planner_waypoints, planner_obstacles, planner_bounds, seed,
                target_heading=target_heading, heading_strength=heading_strength)
        except (ValueError, RuntimeError, TimeoutError) as e:
            self.logger.error(f"Motion planning failed: {e}")
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def _get_current_position(self) -> tuple[float, float] | None:
        """Get current robot (x, y) from estimation state."""
        try:
            estimation = self.common.bilbo.estimation
            return (float(estimation.state.x), float(estimation.state.y))
        except Exception as e:
            self.logger.error(f"Failed to get current position: {e}")
            return None

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _parse_planner_waypoints(waypoints: list[dict | tuple] | None) -> list[PlannerWaypoint]:
        """Convert user waypoint input to PlannerWaypoint list.

        Supports stop flag via:
        - dict: {'x': ..., 'y': ..., 'type': 'STOP'} or {'stop': True}
        - tuple/list: (x, y, weight, 'STOP')
        """
        if not waypoints:
            return []
        result = []
        for wp in waypoints:
            if isinstance(wp, dict):
                stop = (wp.get('type', 'PASS').upper() == 'STOP') or wp.get('stop', False)
                result.append(PlannerWaypoint(
                    x=float(wp['x']),
                    y=float(wp['y']),
                    weight=float(wp.get('weight', 0.5)),
                    stop=stop,
                ))
            elif isinstance(wp, (list, tuple)):
                x, y = float(wp[0]), float(wp[1])
                weight = float(wp[2]) if len(wp) > 2 else 0.5
                stop = len(wp) >= 4 and str(wp[3]).upper() == 'STOP'
                result.append(PlannerWaypoint(x=x, y=y, weight=weight, stop=stop))
            else:
                raise ValueError(f"Invalid waypoint format: {wp}")
        return result

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _compute_stop_indices_from_waypoints(waypoints: list[dict | tuple] | None,
                                             dense_points: list[tuple[float, float]]) -> list[int]:
        """Find nearest dense path point index for each STOP waypoint.

        Args:
            waypoints: User waypoint list (dicts with x, y, type or tuples)
            dense_points: Dense (x, y) path points from the motion planner

        Returns:
            Sorted list of path point indices corresponding to STOP waypoints
        """
        if not waypoints or not dense_points:
            return []

        stop_indices = []
        for wp in waypoints:
            # Determine type
            if isinstance(wp, dict):
                wp_type = wp.get('type', 'PASS').upper()
                if wp_type != 'STOP':
                    continue
                wx, wy = float(wp['x']), float(wp['y'])
            elif isinstance(wp, (list, tuple)) and len(wp) >= 4:
                if str(wp[3]).upper() != 'STOP':
                    continue
                wx, wy = float(wp[0]), float(wp[1])
            else:
                continue

            # Find nearest dense path point
            best_idx = 0
            best_dist_sq = float('inf')
            for i, (px, py) in enumerate(dense_points):
                dsq = (px - wx) ** 2 + (py - wy) ** 2
                if dsq < best_dist_sq:
                    best_dist_sq = dsq
                    best_idx = i
            stop_indices.append(best_idx)

        # Sort and deduplicate
        return sorted(set(stop_indices))

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _parse_planner_obstacles(obstacles: list[dict] | None) -> list[Obstacle]:
        """Convert user obstacle input to planner Obstacle list."""
        if not obstacles:
            return []
        result = []
        for obs in obstacles:
            obs_type = obs.get('type', 'circle')
            if obs_type == 'circle':
                result.append(CircleObstacle(
                    cx=float(obs['cx']),
                    cy=float(obs['cy']),
                    radius=float(obs['radius'])
                ))
            elif obs_type == 'box':
                result.append(BoxObstacle(
                    cx=float(obs['cx']),
                    cy=float(obs['cy']),
                    width=float(obs['width']),
                    height=float(obs['height'])
                ))
            else:
                raise ValueError(f"Unknown obstacle type: {obs_type}")
        return result

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _parse_planner_bounds(bounds: dict | tuple | None) -> Bounds | None:
        """Convert user bounds input to planner Bounds."""
        if bounds is None:
            return None
        if isinstance(bounds, dict):
            return Bounds(
                x_min=float(bounds['x_min']),
                x_max=float(bounds['x_max']),
                y_min=float(bounds['y_min']),
                y_max=float(bounds['y_max'])
            )
        if isinstance(bounds, (list, tuple)):
            return Bounds(
                x_min=float(bounds[0]),
                x_max=float(bounds[1]),
                y_min=float(bounds[2]),
                y_max=float(bounds[3])
            )
        raise ValueError(f"Invalid bounds format: {bounds}")

    # =========================================================================
    # SINGLE-POINT COMMANDS
    # =========================================================================

    # ------------------------------------------------------------------------------------------------------------------
    def move_to_point(self, x: float, y: float,
                      max_speed: float = 0.0,
                      timeout: float = 0.0,
                      blocking: bool = False) -> bool:
        """
        Drive to a single point.

        Args:
            x, y: Target position in world coordinates [m]
            max_speed: Maximum speed (0 = use config default)
            timeout: Command timeout (0 = no timeout)
        """

        # Check if in POSITION mode
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            self.logger.warning(
                f"Cannot move to point: not in POSITION mode (current: "
                f"{self._top_level_control_mode.name if self._top_level_control_mode else 'None'})"
            )
            return False

        if self.is_busy:
            self.logger.warning(f"Cannot move to point: already busy (mode: {self._mode.name})")
            return False

        self._command_id_counter = (self._command_id_counter + 1) % 256
        cmd = move_to_point_command_t(
            id=self._command_id_counter,
            x_target=x,
            y_target=y,
            timeout=timeout,
            max_speed=max_speed
        )

        # Track the command BEFORE sending (event may arrive before executeFunction returns)
        self._current_move_to_point = MoveToPointCommand(
            x=x, y=y, max_speed=max_speed, timeout=timeout, active=True
        )

        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_PositionControlAddresses.MOVE_TO_POINT,
            input_type=move_to_point_command_t,
            output_type=ctypes.c_bool,
            data=cmd
        )

        if result:
            self.logger.info(f"Moving to point ({x:.2f}, {y:.2f})")
        else:
            # Reset tracking if command failed
            self._current_move_to_point = MoveToPointCommand()
            self.logger.error("Failed to start move_to_point command")
            return False

        if not blocking:
            return True

        wait_timeout = timeout + 5.0 if timeout > 0 else 30.0  # maximum time of 30 seconds to go to a point
        data, trace = wait_for_events(
            OR(
                self.events.move_to_point_completed,
                self.events.move_to_point_timeout
            ),
            timeout=wait_timeout
        )

        if data is TIMEOUT or trace.caused_by(self.events.move_to_point_timeout):
            self.logger.warning(f"Move to point timed out")
            self._current_move_to_point = MoveToPointCommand()
            if data is TIMEOUT:
                # Python wait expired but firmware still running — force stop
                self.reset()
            return False

        self.logger.info(f"Move to point completed ({x:.2f}, {y:.2f})")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def turn_to_heading(self, heading: float,
                        max_angular_speed: float = 0.0,
                        timeout: float = 0.0,
                        blocking: bool = False) -> bool:
        """
        Rotate in place to face target heading.

        Args:
            heading: Target heading [rad]
            max_angular_speed: Maximum turn rate (0 = use config default)
            timeout: Command timeout (0 = no timeout)
            blocking: If True, block until heading reached or timeout
        """
        from robot.control.bilbo_control_definitions import BILBO_Control_Mode

        # Check if in POSITION mode
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            self.logger.warning(
                f"Cannot turn to heading: not in POSITION mode (current: "
                f"{self._top_level_control_mode.name if self._top_level_control_mode else 'None'})"
            )
            return False

        if self.is_busy:
            self.logger.warning(f"Cannot turn to heading: already busy (mode: {self._mode.name})")
            return False

        self._command_id_counter = (self._command_id_counter + 1) % 256
        cmd = turn_to_heading_command_t(
            id=self._command_id_counter,
            heading_ref=heading,
            timeout=timeout,
            max_angular_speed=max_angular_speed
        )

        # Track the command BEFORE sending (event may arrive before executeFunction returns)
        self._current_turn_to_heading = TurnToHeadingCommand(
            heading=heading, max_angular_speed=max_angular_speed, timeout=timeout, active=True
        )

        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_PositionControlAddresses.TURN_TO_HEADING,
            input_type=turn_to_heading_command_t,
            output_type=ctypes.c_bool,
            data=cmd
        )

        if result:
            self.logger.info(f"Turning to heading {heading:.2f} rad ({math.degrees(heading):.1f} deg)")
        else:
            # Reset tracking if command failed
            self._current_turn_to_heading = TurnToHeadingCommand()
            self.logger.error("Failed to start turn_to_heading command")
            return False

        if not blocking:
            return True

        wait_timeout = timeout + 5.0 if timeout > 0 else 15.0
        data, trace = wait_for_events(
            OR(
                self.events.turn_to_heading_completed,
                self.events.turn_to_heading_timeout
            ),
            timeout=wait_timeout
        )

        if data is TIMEOUT or trace.caused_by(self.events.turn_to_heading_timeout):
            self.logger.warning(f"Turn to heading timed out")
            self._current_turn_to_heading = TurnToHeadingCommand()
            if data is TIMEOUT:
                # Python wait expired but firmware still running — force stop
                self.reset()
            return False

        self.logger.info(f"Turn to heading completed ({math.degrees(heading):.1f} deg)")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def move_to_pose(self, x: float, y: float, heading: float,
                     max_speed: float = 0.0,
                     max_angular_speed: float = 3.0,
                     position_tolerance: float = 0.0,
                     max_corrections: int = 3,
                     timeout: float = 0.0,
                     blocking: bool = False) -> bool:
        """
        Drive to a pose (position + heading).
        First moves to the target point, then rotates to the target heading.
        If turning causes the robot to drift away from the target position,
        it repeats the move+turn cycle up to max_corrections times.

        Args:
            x, y: Target position in world coordinates [m]
            y:
            x:
            heading: Target heading [rad]
            max_speed: Maximum speed for move phase (0 = use config default)
            max_angular_speed: Maximum turn rate for turn phase [rad/s]
            position_tolerance: Max drift before re-correcting [m] (0 = use arrival_tolerance from config)
            max_corrections: Maximum number of move+turn correction cycles
            timeout: Total command timeout (0 = no timeout)
            blocking: If True, block until pose reached or timeout
        """
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            self.logger.warning(
                f"Cannot move to pose: not in POSITION mode (current: "
                f"{self._top_level_control_mode.name if self._top_level_control_mode else 'None'})"
            )
            return False

        if self.is_busy:
            self.logger.warning(f"Cannot move to pose: already busy (mode: {self._mode.name})")
            return False

        self._current_move_to_pose = MoveToPoseCommand(
            x=x, y=y, heading=heading, max_speed=max_speed,
            max_angular_speed=max_angular_speed, timeout=timeout,
            active=True, phase='move',
        )

        self.events.move_to_pose_started.set()
        self.wifi_events.move_to_pose_started.send(
            data=self._common_event_data(
                target={'x': x, 'y': y},
                heading=heading, heading_deg=math.degrees(heading),
                max_speed=max_speed, max_angular_speed=max_angular_speed,
                timeout=timeout,
            ),
            flags=self._WIFI_FLAGS,
        )
        self.logger.info(f"Moving to pose ({x:.2f}, {y:.2f}, {math.degrees(heading):.1f} deg)")

        # Resolve position tolerance
        tol = position_tolerance if position_tolerance > 0 else self._config.arrival_tolerance

        def _remaining(start_time):
            if timeout <= 0:
                return 0.0
            r = timeout - (time.time() - start_time)
            return r if r > 0.1 else -1.0  # -1 signals expired

        def _emit_timeout(phase):
            self._current_move_to_pose.active = False
            self.logger.warning(f"Move to pose failed during {phase} phase")
            self.events.move_to_pose_timeout.set()
            self.wifi_events.move_to_pose_timeout.send(
                data=self._common_event_data(
                    target={'x': x, 'y': y},
                    heading=heading, heading_deg=math.degrees(heading),
                    phase=phase,
                ),
                flags=self._WIFI_FLAGS,
            )

        def _execute():
            start_time = time.time()

            for attempt in range(1 + max_corrections):
                # ── Move to point ────────────────────────────────────────
                self._current_move_to_pose.phase = 'move'
                move_timeout = _remaining(start_time)
                if move_timeout < 0:
                    _emit_timeout('move')
                    return False

                move_success = self.move_to_point(
                    x=x, y=y, max_speed=max_speed, timeout=move_timeout, blocking=True,
                )
                if not move_success:
                    _emit_timeout('move')
                    return False

                # ── Turn to heading ──────────────────────────────────────
                self._current_move_to_pose.phase = 'turn'
                turn_timeout = _remaining(start_time)
                if turn_timeout < 0:
                    _emit_timeout('turn')
                    return False

                turn_success = self.turn_to_heading(
                    heading=heading, max_angular_speed=max_angular_speed,
                    timeout=turn_timeout, blocking=True,
                )
                if not turn_success:
                    _emit_timeout('turn')
                    return False

                # ── Check position drift ─────────────────────────────────
                pos = self._get_current_position()
                if pos is not None:
                    dx = pos[0] - x
                    dy = pos[1] - y
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist <= tol:
                        break  # close enough
                    if attempt < max_corrections:
                        self.logger.info(
                            f"Position drifted {dist:.3f}m during turn, "
                            f"correcting (attempt {attempt + 1}/{max_corrections})"
                        )
                    else:
                        self.logger.warning(
                            f"Position still {dist:.3f}m off after {max_corrections} corrections"
                        )
                else:
                    break  # can't check, accept result

            self._current_move_to_pose.active = False
            self.logger.info(
                f"Reached pose ({x:.2f}, {y:.2f}, {math.degrees(heading):.1f} deg)"
            )
            self.events.move_to_pose_completed.set()
            self.wifi_events.move_to_pose_completed.send(
                data=self._common_event_data(
                    target={'x': x, 'y': y},
                    heading=heading, heading_deg=math.degrees(heading),
                ),
                flags=self._WIFI_FLAGS,
            )
            return True

        if blocking:
            return _execute()

        threading.Thread(target=_execute, daemon=True).start()
        return True

    # =========================================================================
    # RESET
    # =========================================================================

    def reset(self) -> bool:
        """Reset position control to idle state"""
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_PositionControlAddresses.RESET,
            input_type=None,
            output_type=ctypes.c_bool,
        )

        if result:
            self._set_mode(PositionControlMode.IDLE)
            self._path_state = PathState.IDLE
            self._path_point_count = 0
            self._current_index = 0
            # Clear command tracking
            self._current_move_to_point = MoveToPointCommand()
            self._current_turn_to_heading = TurnToHeadingCommand()
            self._current_move_to_pose = MoveToPoseCommand()
            self.logger.info("Position control reset")
        else:
            self.logger.error("Failed to reset position control")

        return result or False

    # =========================================================================
    # DATA RETRIEVAL
    # =========================================================================

    def get_data_from_stm32(self) -> PositionControlData | None:
        """Read current telemetry data from STM32"""
        data = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_PositionControlAddresses.READ_DATA,
            input_type=None,
            output_type=bilbo_position_control_data_t
        )
        if data is None:
            return None

        data_dict = from_dict_auto(bilbo_position_control_data, data)
        self._update_data_from_dict(dataclasses.asdict(data_dict))
        return self._data

    # =========================================================================
    # EVENT HANDLING
    # =========================================================================

    def _handle_position_control_event(self, message: BILBO_PositionControl_Event_Message):
        """Handle events from STM32 position controller"""
        try:
            event_data = from_dict_auto(position_control_event_data, message.data)
            event = position_control_event_t(event_data.event)
        except (KeyError, ValueError) as e:
            self.logger.warning(f"Invalid position control event: {e}")
            return

        self.logger.debug(f"Position control event: {event.name}")

        # Update local data from event
        self._update_data_from_dict(dataclasses.asdict(event_data.data))

        match event:
            # Path events
            case position_control_event_t.PATH_STARTED:
                self._set_mode(PositionControlMode.FOLLOW_PATH)
                self._path_state = PathState.RUNNING
                self.events.path_started.set()
                self.callbacks.path_started.call()
                self.wifi_events.path_started.send(
                    data=self._common_event_data(
                        settings=self._current_path_settings,
                    ),
                    flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.PATH_PAUSED:
                self._path_state = PathState.PAUSED
                self.events.path_paused.set()
                self.wifi_events.path_paused.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            case position_control_event_t.PATH_RESUMED:
                self._path_state = PathState.RUNNING
                self.events.path_resumed.set()
                self.wifi_events.path_resumed.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            case position_control_event_t.PATH_FINISHED:
                self._set_mode(PositionControlMode.IDLE)
                self._path_state = PathState.IDLE
                self.logger.info("Path finished!")
                self._path_point_count = 0
                self.events.path_finished.set()
                self.callbacks.path_finished.call()
                self.wifi_events.path_finished.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            case position_control_event_t.PATH_TIMEOUT:
                self._set_mode(PositionControlMode.IDLE)
                self._path_state = PathState.IDLE
                self.logger.warning("Path timed out!")
                self._path_point_count = 0
                self.events.path_timeout.set()
                self.callbacks.path_timeout.call()
                self.wifi_events.path_timeout.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            case position_control_event_t.PATH_ABORTED:
                self._set_mode(PositionControlMode.IDLE)
                self._path_state = PathState.IDLE
                self.logger.warning("Path aborted!")
                self._path_point_count = 0
                self.events.path_aborted.set()
                self.callbacks.path_aborted.call()
                self.wifi_events.path_aborted.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            # Stop events (repurposed from waypoint events, same numeric values)
            case position_control_event_t.WAYPOINT_REACHED:
                idx = event_data.waypoint_index
                self.logger.info(f"Reached stop point at index {idx}")
                self.events.stop_reached.set(flags={'index': idx})
                self.wifi_events.stop_reached.send(
                    data=self._common_event_data(stop_index=idx),
                    flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.WAYPOINT_COMPLETED:
                idx = event_data.waypoint_index
                self.logger.info(f"Completed stop point at index {idx}")
                self._current_index = idx
                self.events.stop_completed.set(flags={'index': idx})
                self.callbacks.stop_completed.call(idx)
                self.wifi_events.stop_completed.send(
                    data=self._common_event_data(stop_index=idx),
                    flags=self._WIFI_FLAGS,
                )

            # Single-point command events
            case position_control_event_t.MOVE_TO_POINT_STARTED:
                self._set_mode(PositionControlMode.DRIVE_TO_POINT)
                self.events.move_to_point_started.set()
                # Send target coordinates with event
                cmd = self._current_move_to_point
                self.wifi_events.move_to_point_started.send(
                    data=self._common_event_data(
                        target={'x': cmd.x, 'y': cmd.y}, max_speed=cmd.max_speed, timeout=cmd.timeout,
                    ),
                    flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.MOVE_TO_POINT_COMPLETED:
                self._set_mode(PositionControlMode.IDLE)
                # Log with target coordinates
                cmd = self._current_move_to_point
                target_data = {'x': cmd.x, 'y': cmd.y} if cmd.active else None
                if cmd.active:
                    self.logger.info(f"Reached point ({cmd.x:.2f}, {cmd.y:.2f})")
                    self._current_move_to_point.active = False
                else:
                    self.logger.info("Move to point completed")
                self.events.move_to_point_completed.set()
                self.wifi_events.move_to_point_completed.send(
                    data=self._common_event_data(target=target_data), flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.MOVE_TO_POINT_TIMEOUT:
                self._set_mode(PositionControlMode.IDLE)
                # Log with target coordinates
                cmd = self._current_move_to_point
                target_data = {'x': cmd.x, 'y': cmd.y} if cmd.active else None
                if cmd.active:
                    self.logger.warning(f"Move to point ({cmd.x:.2f}, {cmd.y:.2f}) timed out")
                    self._current_move_to_point.active = False
                else:
                    self.logger.warning("Move to point timed out")
                self.events.move_to_point_timeout.set()
                self.wifi_events.move_to_point_timeout.send(
                    data=self._common_event_data(target=target_data), flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.TURN_TO_HEADING_STARTED:
                self._set_mode(PositionControlMode.TURN_TO_HEADING)
                self.events.turn_to_heading_started.set()
                # Send target heading with event
                cmd = self._current_turn_to_heading
                self.wifi_events.turn_to_heading_started.send(
                    data=self._common_event_data(
                        heading=cmd.heading, heading_deg=math.degrees(cmd.heading),
                        max_angular_speed=cmd.max_angular_speed, timeout=cmd.timeout,
                    ),
                    flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.TURN_TO_HEADING_COMPLETED:
                self._set_mode(PositionControlMode.IDLE)
                # Log with target heading
                cmd = self._current_turn_to_heading
                heading_data = {'heading': cmd.heading,
                                'heading_deg': math.degrees(cmd.heading)} if cmd.active else None
                if cmd.active:
                    self.logger.info(f"Reached heading {cmd.heading:.2f} rad ({math.degrees(cmd.heading):.1f} deg)")
                    self._current_turn_to_heading.active = False
                else:
                    self.logger.info("Turn to heading completed")
                self.events.turn_to_heading_completed.set()
                self.wifi_events.turn_to_heading_completed.send(
                    data=self._common_event_data(**(heading_data or {})), flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.TURN_TO_HEADING_TIMEOUT:
                self._set_mode(PositionControlMode.IDLE)
                # Log with target heading
                cmd = self._current_turn_to_heading
                heading_data = {'heading': cmd.heading,
                                'heading_deg': math.degrees(cmd.heading)} if cmd.active else None
                if cmd.active:
                    self.logger.warning(
                        f"Turn to heading {cmd.heading:.2f} rad ({math.degrees(cmd.heading):.1f} deg) timed out")
                    self._current_turn_to_heading.active = False
                else:
                    self.logger.warning("Turn to heading timed out")
                self.events.turn_to_heading_timeout.set()
                self.wifi_events.turn_to_heading_timeout.send(
                    data=self._common_event_data(**(heading_data or {})), flags=self._WIFI_FLAGS,
                )

            # Mode change
            case position_control_event_t.MODE_CHANGED:
                new_mode = PositionControlMode(event_data.data.mode)
                self._mode = new_mode
                self.events.mode_changed.set(flags={'mode': new_mode})
                self.callbacks.mode_changed.call(new_mode)
                self.wifi_events.mode_changed.send(
                    data=self._common_event_data(new_mode=new_mode.value, new_mode_name=new_mode.name),
                    flags=self._WIFI_FLAGS,
                )

            # Buffer full
            case position_control_event_t.PATH_BUFFER_FULL:
                self.logger.warning("Path buffer full on STM32")
                self.events.path_buffer_full.set()
                self.callbacks.path_buffer_full.call()
                self.wifi_events.path_buffer_full.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            case _:
                self.logger.warning(f"Unhandled position control event: {event}")

    def _update_data_from_dict(self, data_dict: dict):
        """Update local telemetry data from dictionary"""
        try:
            self._data.mode = PositionControlMode(data_dict.get('mode', 0))
            self._data.path_state = PathState(data_dict.get('path_state', 0))
            self._data.buffer_capacity = data_dict.get('buffer_capacity', 0)
            self._data.buffer_used = data_dict.get('buffer_used', 0)
            self._data.path_point_count = data_dict.get('path_point_count', 0)
            self._data.current_index = data_dict.get('current_index', 0)
            self._data.carrot_x = data_dict.get('carrot_x', 0.0)
            self._data.carrot_y = data_dict.get('carrot_y', 0.0)
            self._data.carrot_distance = data_dict.get('carrot_distance', 0.0)
            self._data.heading_error = data_dict.get('heading_error', 0.0)
            self._data.speed_limit = data_dict.get('speed_limit', 0.0)
            self._data.elapsed_time = data_dict.get('elapsed_time', 0.0)
            self._data.remaining_path_length = data_dict.get('remaining_path_length', 0.0)
            self._data.progress = data_dict.get('progress', 0.0)

            if 'output' in data_dict:
                self._data.v_cmd = data_dict['output'].get('v_cmd', 0.0)
                self._data.psi_dot_cmd = data_dict['output'].get('psi_dot_cmd', 0.0)
        except Exception as e:
            self.logger.warning(f"Failed to update data from dict: {e}")

    def _lowlevel_sample_callback(self, sample: BILBO_LL_Sample):
        """Handle low-level sample updates"""
        # Only sync position control state when top-level control is in POSITION mode.
        # The firmware's position control mode is stale/meaningless in other modes.
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            return

        # Sync position control data from sample if available
        if hasattr(sample, 'control') and hasattr(sample.control, 'position_control_data'):
            pos_data = sample.control.position_control_data
            # Check for mode mismatch — but don't let stale SPI samples
            # overwrite a recent event-driven transition (e.g. completion event
            # already set IDLE, but the next sample still reports DRIVE_TO_POINT).
            stm32_mode = PositionControlMode(pos_data.mode)
            if stm32_mode != self._mode:
                age = time.time() - self._mode_event_time
                if age < 0.2:
                    self.logger.debug(
                        f"Mode mismatch (ignored, event {age * 1000:.0f}ms ago): "
                        f"local={self._mode.name}, STM32={stm32_mode.name}"
                    )
                else:
                    self.logger.debug(f"Mode mismatch: local={self._mode.name}, STM32={stm32_mode.name}")
                    self._mode = stm32_mode

    def _on_control_mode_change(self, mode, *args, **kwargs):
        """Handle top-level control mode changes"""
        from robot.control.bilbo_control_definitions import BILBO_Control_Mode

        # Track top-level control mode
        self._top_level_control_mode = mode

        if mode == BILBO_Control_Mode.POSITION:
            # Entering POSITION mode: clear local state to sync with firmware
            # (firmware clears path when entering POSITION mode)
            had_path = self._path_point_count > 0
            self._path_point_count = 0
            self._current_index = 0
            self._set_mode(PositionControlMode.IDLE)
            self._path_state = PathState.IDLE
            # Clear command tracking, but preserve commands that are already active
            # (auto mode-switching in BILBO_Control may store the command before the
            # async MODE_CHANGED event arrives from STM32)
            if not self._current_move_to_point.active:
                self._current_move_to_point = MoveToPointCommand()
            if not self._current_turn_to_heading.active:
                self._current_turn_to_heading = TurnToHeadingCommand()
            if not self._current_move_to_pose.active:
                self._current_move_to_pose = MoveToPoseCommand()
            # Notify host that path was cleared by firmware
            if had_path:
                self.wifi_events.path_cleared.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)
        else:
            # Leaving POSITION mode: fire termination events if commands were active.
            # Use _path_state (not _mode) for the FOLLOW_PATH check because firmware
            # MODE_CHANGED serial events can overwrite _mode with a stale value after
            # PATH_FINISHED already set it to IDLE.
            if self._mode == PositionControlMode.FOLLOW_PATH and self._path_state == PathState.RUNNING:
                self.logger.warning(f"Control mode changed to {mode.name} while path was running, aborting path")
                self._set_mode(PositionControlMode.IDLE)
                self._path_state = PathState.IDLE
                self._path_point_count = 0
                self.events.path_aborted.set()
                self.callbacks.path_aborted.call()
                self.wifi_events.path_aborted.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)
            elif self._mode == PositionControlMode.DRIVE_TO_POINT:
                self.logger.warning(f"Control mode changed to {mode.name} while move_to_point was active")
                cmd = self._current_move_to_point
                target_data = {'x': cmd.x, 'y': cmd.y} if cmd.active else None
                self._set_mode(PositionControlMode.IDLE)
                self._current_move_to_point = MoveToPointCommand()
                self.events.move_to_point_timeout.set()
                self.wifi_events.move_to_point_timeout.send(
                    data=self._common_event_data(target=target_data), flags=self._WIFI_FLAGS,
                )
            elif self._mode == PositionControlMode.TURN_TO_HEADING:
                self.logger.warning(f"Control mode changed to {mode.name} while turn_to_heading was active")
                cmd = self._current_turn_to_heading
                heading_data = {'heading': cmd.heading,
                                'heading_deg': math.degrees(cmd.heading)} if cmd.active else None
                self._set_mode(PositionControlMode.IDLE)
                self._current_turn_to_heading = TurnToHeadingCommand()
                self.events.turn_to_heading_timeout.set()
                self.wifi_events.turn_to_heading_timeout.send(
                    data=self._common_event_data(**(heading_data or {})), flags=self._WIFI_FLAGS,
                )
            elif self._mode != PositionControlMode.IDLE:
                self.logger.info(f"Control mode changed to {mode.name}, resetting position control state")
            elif self._path_point_count > 0:
                # IDLE with loaded-but-not-started path: notify host that path is gone
                self.wifi_events.path_cleared.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            # Always clean up local state
            self._set_mode(PositionControlMode.IDLE)
            self._path_state = PathState.IDLE
            self._path_point_count = 0
            self._current_index = 0
            self._current_move_to_point = MoveToPointCommand()
            self._current_turn_to_heading = TurnToHeadingCommand()
            self._current_move_to_pose = MoveToPoseCommand()

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    @staticmethod
    def _compress_path_points(points: list[tuple[float, float]]) -> str:
        """Compress path points to a base64-encoded zlib-compressed binary string.
        Format: packed array of (float32 x, float32 y) pairs → zlib → base64.
        """
        raw = struct.pack(f'<{len(points) * 2}f', *[v for pt in points for v in pt])
        return base64.b64encode(zlib.compress(raw, level=6)).decode('ascii')

    def get_sample_dict(self) -> dict:
        """Get current state as dictionary for logging/streaming"""
        return {
            'mode': self._mode.value,
            'mode_name': self._mode.name,
            'path_state': self._path_state.value,
            'path_state_name': self._path_state.name,
            'path_point_count': self._path_point_count,
            'current_index': self._current_index,
            'is_busy': self.is_busy,
            'data': dataclasses.asdict(self._data),
        }

    # =========================================================================
    # WIFI COMMANDS
    # =========================================================================

    def _register_wifi_commands(self):
        """Register WiFi commands for remote position control"""

        # Configuration
        self.communication.wifi.newCommand(
            identifier='position_control_set_config',
            function=self._wifi_set_config,
            arguments=['config'],
            description='Set position control configuration'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_get_config',
            function=lambda: dataclasses.asdict(self._config),
            arguments=[],
            description='Get position control configuration'
        )

        # Path management
        self.communication.wifi.newCommand(
            identifier='position_control_clear_path',
            function=self.clear_path,
            arguments=[],
            description='Clear all path points'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_add_stop_index',
            function=self._wifi_add_stop_index,
            arguments=['index'],
            description='Mark a path point index as STOP'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_get_path_point_count',
            function=self.get_path_point_count,
            arguments=[],
            description='Get number of path points on STM32'
        )

        # Path management (non-motion: these don't start movement, so no auto mode-switch needed)
        self.communication.wifi.newCommand(
            identifier='position_control_abort_path',
            function=self.abort_path,
            arguments=[],
            description='Abort path execution'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_plan_path',
            function=self._wifi_plan_path,
            arguments=[
                'target',
                CommandArgument(name='waypoints', type=list, optional=True, default=None),
                CommandArgument(name='obstacles', type=list, optional=True, default=None),
                CommandArgument(name='bounds', type=dict, optional=True, default=None),
                CommandArgument(name='seed', type=int, optional=True, default=None),
                CommandArgument(name='target_heading', type=float, optional=True, default=None),
                CommandArgument(name='heading_strength', type=float, optional=True, default=1.0),
            ],
            description='Plan path from current position to target (preview only, no load/start)',
            execute_in_thread=True
        )

        self.communication.wifi.newCommand(
            identifier='position_control_build_prm',
            function=self._wifi_build_prm,
            arguments=[],
            description='Build PRM roadmap from current testbed obstacles',
            execute_in_thread=True
        )

        # Status
        self.communication.wifi.newCommand(
            identifier='position_control_get_state',
            function=self.get_sample_dict,
            arguments=[],
            description='Get current position control state'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_reset',
            function=self.reset,
            arguments=[],
            description='Reset position control'
        )

    def _wifi_set_config(self, config: dict) -> bool:
        """Set config from WiFi (dict input)"""
        try:
            cfg = from_dict_auto(PositionControl_Config, config)
            return self.set_config(cfg)
        except Exception as e:
            self.logger.error(f"Failed to parse config: {e}")
            return False

    def _wifi_add_stop_index(self, index: int) -> bool:
        """Add stop index from WiFi command"""
        return self.add_stop_index(index=int(index))

    def _wifi_plan_path(self, target, waypoints=None, obstacles=None, bounds=None, seed=None,
                        target_heading=None, heading_strength=1.0) -> bool:
        """Plan path from WiFi command. Plans, emits preview event, and loads onto STM32 (without starting)."""
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            self.logger.warning(
                f"Cannot plan path: not in POSITION mode (current: "
                f"{self._top_level_control_mode.name if self._top_level_control_mode else 'None'})"
            )
            return False

        if isinstance(target, dict):
            target = (float(target['x']), float(target['y']))
        elif isinstance(target, (list, tuple)):
            target = (float(target[0]), float(target[1]))

        dense_points = self.plan_path(
            target=target,
            waypoints=waypoints,
            obstacles=obstacles,
            bounds=bounds,
            seed=int(seed) if seed is not None else None,
            target_heading=float(target_heading) if target_heading is not None else None,
            heading_strength=float(heading_strength),
        )

        if dense_points is None or len(dense_points) < 2:
            return False

        # Serialize waypoints for host visualization
        wp_list = None
        if waypoints:
            wp_list = []
            for wp in waypoints:
                if isinstance(wp, dict):
                    wp_list.append(wp)
                elif isinstance(wp, (list, tuple)):
                    d = {'x': float(wp[0]), 'y': float(wp[1])}
                    if len(wp) > 2:
                        d['weight'] = float(wp[2])
                    wp_list.append(d)

        # Store waypoints so load_path can include them in path_loaded event
        self._current_path_waypoints = wp_list

        # Emit path_planned event with compressed path for host visualization
        self.wifi_events.path_planned.send(
            data=self._common_event_data(
                path_point_count=len(dense_points),
                target={'x': target[0], 'y': target[1]},
                waypoints=wp_list,
                path_points_compressed=self._compress_path_points(dense_points),
            ),
            flags=self._WIFI_FLAGS,
        )

        # Compute stop indices from STOP waypoints
        stop_indices = self._compute_stop_indices_from_waypoints(waypoints, dense_points)
        if stop_indices:
            self.logger.info(f"STOP waypoints mapped to path indices: {stop_indices}")

        # Load onto STM32 so "start" can be called immediately
        return self.load_path(path_data=dense_points, start=False, stop_indices=stop_indices)

    def _wifi_build_prm(self) -> bool:
        """Build PRM roadmap from WiFi command."""
        try:
            self.build_prm_map()
            return True
        except Exception as e:
            self.logger.error(f"PRM build failed: {e}")
            return False

    # =========================================================================
    # WIFI EVENT EMISSION
    # =========================================================================

    _WIFI_FLAGS = {'group': 'position_control'}

    def _common_event_data(self, **extra) -> dict:
        """Build common event data dict, optionally merged with extra fields."""
        data = dataclasses.asdict(PositionControlCommonData(
            mode=self._mode.value,
            mode_name=self._mode.name,
            path_state=self._path_state.value,
            path_point_count=self._path_point_count,
            current_index=self._current_index,
        ))
        if extra:
            data.update(extra)
        return data
