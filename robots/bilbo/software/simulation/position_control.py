"""
Simulated firmware position control.

1:1 replica of the STM32 bilbo_position_control.cpp:
  - Dense path following with adaptive lookahead (pure pursuit)
  - Curvature-based speed control with exponential smoothing
  - Turn-to-heading (in-place rotation)
  - Drive-to-point (single waypoint tracking with reverse)
  - Stop indices with dwell time
  - Final approach override with reverse for overshoot recovery
  - Event generation for waypoint reached / path finished / timeouts
"""
from __future__ import annotations

import dataclasses
import enum
import math

EPSILON = 1e-6
PROJECTION_SEARCH_WINDOW = 30
SPEED_SMOOTH_TAU = 0.1  # [s] exponential smoothing time constant


def _normalize_angle(a: float) -> float:
    """Wrap angle to [-pi, pi]."""
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# =============================================================================
# Enums (mirror firmware)
# =============================================================================
class PositionControlMode(enum.IntEnum):
    IDLE = 0
    TURN_TO_HEADING = 1
    DRIVE_TO_POINT = 2
    FOLLOW_PATH = 3


class PathState(enum.IntEnum):
    IDLE = 0
    RUNNING = 1
    PAUSED = 2


class PositionControlEvent(enum.IntEnum):
    PATH_STARTED = 0
    WAYPOINT_REACHED = 2
    WAYPOINT_COMPLETED = 3
    PATH_PAUSED = 4
    PATH_RESUMED = 5
    PATH_FINISHED = 6
    PATH_TIMEOUT = 7
    PATH_ABORTED = 8
    MOVE_TO_POINT_STARTED = 9
    MOVE_TO_POINT_COMPLETED = 10
    MOVE_TO_POINT_TIMEOUT = 11
    TURN_TO_HEADING_STARTED = 12
    TURN_TO_HEADING_COMPLETED = 13
    TURN_TO_HEADING_TIMEOUT = 14
    MODE_CHANGED = 15
    PATH_BUFFER_FULL = 16


# =============================================================================
# Configuration (defaults match firmware bilbo_position_control_config_t)
# =============================================================================
@dataclasses.dataclass
class PositionControlConfig:
    Ts: float = 0.01

    # Angular control
    kp_angular: float = 10.0
    ki_angular: float = 0.3
    kp_angular_heading: float = 0.0
    ki_angular_heading: float = 0.0

    # Linear control
    kp_linear: float = 2.0
    ki_linear: float = 0.0
    kd_linear: float = 0.5

    # Speed limits
    max_speed: float = 0.5
    max_turn_rate: float = 5.0

    # Lookahead
    lookahead_base: float = 0.15
    lookahead_min: float = 0.03

    # Arrival
    arrival_tolerance: float = 0.05
    arrival_dwell_time: float = 0.5
    stop_dwell_time: float = 1.0

    # Reverse mode
    reverse_enter_angle: float = 2.1
    reverse_exit_angle: float = 1.05

    # Deceleration
    decel_limit: float = 0.0

    # Curvature-based speed (path following)
    curvature_gain: float = 2.0
    curvature_lookahead: float = 0.3


# =============================================================================
# Telemetry data
# =============================================================================
@dataclasses.dataclass
class PositionControlData:
    mode: int = 0
    path_state: int = 0
    buffer_capacity: int = 1024
    buffer_used: int = 0
    path_point_count: int = 0
    current_index: int = 0
    carrot_x: float = 0.0
    carrot_y: float = 0.0
    carrot_distance: float = 0.0
    heading_error: float = 0.0
    speed_limit: float = 0.0
    v_cmd: float = 0.0
    psi_dot_cmd: float = 0.0
    elapsed_time: float = 0.0
    remaining_path_length: float = 0.0
    progress: float = 0.0


# =============================================================================
# Position Controller
# =============================================================================
class SimulatedPositionControl:
    """Firmware-equivalent position control with path following, turn, and drive-to-point."""

    @property
    def path_point_count(self) -> int:
        return len(self._path)

    def __init__(self, config: PositionControlConfig | None = None):
        self.config = config or PositionControlConfig()

        # Path buffer
        self._path: list[tuple[float, float]] = []
        self._cumul_dist: list[float] = []
        self._stop_indices: list[int] = []
        self._path_max_speed: float = 0.0
        self._path_max_spacing: float = 0.0
        self._path_total_length: float = 0.0

        # Path command
        self._allow_reverse: bool = False
        self._path_timeout: float = 0.0

        # State
        self.mode = PositionControlMode.IDLE
        self.path_state = PathState.IDLE
        self._progress: float = 0.0
        self._elapsed_time: float = 0.0
        self._angular_integral: float = 0.0
        self._linear_integral: float = 0.0
        self._reverse_mode: bool = False
        self._arrival_timer: float = 0.0
        self._v_target_smooth: float = 0.0

        # Stop tracking (matches firmware _next_stop_ptr pattern)
        self._next_stop_ptr: int = 0
        self._stop_reached_sent: bool = False

        # Carrot position
        self._carrot_x: float = 0.0
        self._carrot_y: float = 0.0

        # Turn-to-heading
        self._heading_target: float = 0.0
        self._heading_cmd_id: int = 0
        self._heading_max_angular_speed: float = 0.0
        self._heading_timeout: float = 0.0

        # Drive-to-point
        self._point_target_x: float = 0.0
        self._point_target_y: float = 0.0
        self._point_cmd_id: int = 0
        self._point_timeout: float = 0.0
        self._point_max_speed: float = 0.0

        # Event queue (consumed by firmware.py)
        self.pending_events: list[tuple[PositionControlEvent, dict]] = []

        # Telemetry
        self.data = PositionControlData()

    def _emit(self, event: PositionControlEvent, **extra):
        self.pending_events.append((event, extra))

    # ── Public API ──────────────────────────────────────────────────────

    def set_config(self, config: PositionControlConfig):
        self.config = config

    def clear_path(self):
        self._path.clear()
        self._cumul_dist.clear()
        self._stop_indices.clear()
        self._progress = 0.0
        self._angular_integral = 0.0
        self._linear_integral = 0.0
        self._arrival_timer = 0.0
        self._reverse_mode = False
        self._stop_reached_sent = False
        self._next_stop_ptr = 0
        self._path_max_speed = 0.0
        self._path_max_spacing = 0.0
        self._path_total_length = 0.0
        self._v_target_smooth = 0.0

    def add_path_point(self, x: float, y: float):
        self._path.append((x, y))

    def add_stop_index(self, index: int):
        if len(self._stop_indices) < 16:
            self._stop_indices.append(index)

    def start_path(self, max_speed: float = 0.0, max_spacing: float = 0.0,
                   timeout: float = 0.0, allow_reverse: bool = False):
        if len(self._path) < 2:
            return
        if self.mode != PositionControlMode.IDLE:
            return

        # Compute cumulative distances
        self._compute_cumulative_distances()

        # Resolve max speed
        self._path_max_speed = max_speed if max_speed > 0 else self.config.max_speed

        # Resolve max spacing: auto-detect from path if not specified
        if max_spacing > 0:
            self._path_max_spacing = max_spacing
        else:
            self._path_max_spacing = 0.0
            for i in range(1, len(self._path)):
                seg_len = self._cumul_dist[i] - self._cumul_dist[i - 1]
                if seg_len > self._path_max_spacing:
                    self._path_max_spacing = seg_len
            if self._path_max_spacing < EPSILON:
                self._path_max_spacing = 0.01

        self._path_total_length = self._cumul_dist[-1] if self._cumul_dist else 0.0

        # Initialize state
        self._path_timeout = timeout
        self._allow_reverse = allow_reverse
        self._progress = 0.0
        self._elapsed_time = 0.0
        self._angular_integral = 0.0
        self._linear_integral = 0.0
        self._arrival_timer = 0.0
        self._reverse_mode = False
        self._stop_reached_sent = False
        self._next_stop_ptr = 0
        self._v_target_smooth = 0.0

        # Initialize carrot at first path point
        self._carrot_x = self._path[0][0]
        self._carrot_y = self._path[0][1]

        self.path_state = PathState.RUNNING
        self.mode = PositionControlMode.FOLLOW_PATH
        self._emit(PositionControlEvent.PATH_STARTED)
        self._emit(PositionControlEvent.MODE_CHANGED)

    def pause_path(self):
        if self.path_state == PathState.RUNNING:
            self.path_state = PathState.PAUSED
            self._emit(PositionControlEvent.PATH_PAUSED)

    def resume_path(self):
        if self.path_state == PathState.PAUSED:
            self.path_state = PathState.RUNNING
            self._emit(PositionControlEvent.PATH_RESUMED)

    def abort_path(self):
        if self.mode == PositionControlMode.FOLLOW_PATH:
            self._emit(PositionControlEvent.PATH_ABORTED)
            self.path_state = PathState.IDLE
            self.mode = PositionControlMode.IDLE
            self._emit(PositionControlEvent.MODE_CHANGED)

    def turn_to_heading(self, heading: float, timeout: float = 0.0,
                        max_angular_speed: float = 0.0, cmd_id: int = 0):
        if self.mode != PositionControlMode.IDLE:
            return

        self._heading_target = heading
        self._heading_cmd_id = cmd_id
        self._heading_timeout = timeout
        self._heading_max_angular_speed = max_angular_speed if max_angular_speed > 0 else self.config.max_turn_rate
        self._elapsed_time = 0.0
        self._angular_integral = 0.0
        self._arrival_timer = 0.0

        self.mode = PositionControlMode.TURN_TO_HEADING
        self._emit(PositionControlEvent.TURN_TO_HEADING_STARTED, command_id=cmd_id)
        self._emit(PositionControlEvent.MODE_CHANGED)

    def move_to_point(self, x: float, y: float, timeout: float = 0.0,
                      max_speed: float = 0.0, cmd_id: int = 0):
        if self.mode != PositionControlMode.IDLE:
            return

        self._point_target_x = x
        self._point_target_y = y
        self._point_cmd_id = cmd_id
        self._point_timeout = timeout
        self._point_max_speed = max_speed if max_speed > 0 else self.config.max_speed
        self._elapsed_time = 0.0
        self._angular_integral = 0.0
        self._linear_integral = 0.0
        self._arrival_timer = 0.0
        self._reverse_mode = False

        self.mode = PositionControlMode.DRIVE_TO_POINT
        self._emit(PositionControlEvent.MOVE_TO_POINT_STARTED, command_id=cmd_id)
        self._emit(PositionControlEvent.MODE_CHANGED)

    def reset(self):
        self.clear_path()
        self.mode = PositionControlMode.IDLE
        self.path_state = PathState.IDLE
        self._progress = 0.0
        self._elapsed_time = 0.0
        self._angular_integral = 0.0
        self._linear_integral = 0.0
        self._reverse_mode = False
        self._arrival_timer = 0.0

    # ── Main update (called at 100 Hz) ──────────────────────────────────

    def update(self, robot_x: float, robot_y: float, robot_psi: float,
               current_v: float) -> tuple[float, float]:
        """Returns (v_cmd, psi_dot_cmd)."""
        if self.mode != PositionControlMode.IDLE:
            self._elapsed_time += self.config.Ts

        if self.mode == PositionControlMode.IDLE:
            out = (0.0, 0.0)
        elif self.mode == PositionControlMode.TURN_TO_HEADING:
            out = self._update_turn_to_heading(robot_psi)
        elif self.mode == PositionControlMode.DRIVE_TO_POINT:
            out = self._update_drive_to_point(robot_x, robot_y, robot_psi, current_v)
        elif self.mode == PositionControlMode.FOLLOW_PATH:
            if self.path_state == PathState.PAUSED:
                out = (0.0, 0.0)
            else:
                out = self._update_follow_path(robot_x, robot_y, robot_psi, current_v)
        else:
            out = (0.0, 0.0)

        # Update telemetry
        self.data.mode = int(self.mode)
        self.data.path_state = int(self.path_state)
        self.data.buffer_capacity = 1024
        self.data.buffer_used = len(self._path)
        self.data.elapsed_time = self._elapsed_time
        self.data.v_cmd = out[0]
        self.data.psi_dot_cmd = out[1]

        return out

    def get_data(self) -> PositionControlData:
        return dataclasses.replace(self.data)

    # ── Turn to heading (matches firmware _update_turn_to_heading) ──────

    def _update_turn_to_heading(self, robot_psi: float) -> tuple[float, float]:
        c = self.config

        heading_error = _normalize_angle(self._heading_target - robot_psi)
        self.data.heading_error = heading_error

        max_rate = self._heading_max_angular_speed

        # Resolve effective angular gains (heading-specific overrides, 0 = use base)
        eff_kp = c.kp_angular_heading if c.kp_angular_heading > 0 else c.kp_angular
        eff_ki = c.ki_angular_heading if c.ki_angular_heading > 0 else c.ki_angular

        # PI control
        w_p = eff_kp * heading_error
        w_i = self._angular_integral
        w_unsat = w_p + w_i
        w_sat = _clamp(w_unsat, -max_rate, max_rate)

        # Anti-windup
        is_saturated = abs(w_unsat - w_sat) > EPSILON
        would_push_further = is_saturated and (
            (w_unsat > w_sat and heading_error > 0.0) or
            (w_unsat < w_sat and heading_error < 0.0))

        if not would_push_further:
            self._angular_integral += eff_ki * heading_error * c.Ts
            max_integral = max_rate / max(eff_ki, 0.01)
            self._angular_integral = _clamp(self._angular_integral, -max_integral, max_integral)

        # Check completion
        angle_tolerance = 0.05  # ~3 degrees
        if abs(heading_error) < angle_tolerance:
            self._arrival_timer += c.Ts
            if self._arrival_timer >= c.arrival_dwell_time:
                self._angular_integral = 0.0
                self._arrival_timer = 0.0
                self.mode = PositionControlMode.IDLE
                self._emit(PositionControlEvent.TURN_TO_HEADING_COMPLETED,
                           command_id=self._heading_cmd_id)
                self._emit(PositionControlEvent.MODE_CHANGED)
                return 0.0, w_sat
        else:
            self._arrival_timer = 0.0

        # Check timeout
        if self._heading_timeout > 0 and self._elapsed_time > self._heading_timeout:
            self._angular_integral = 0.0
            self._arrival_timer = 0.0
            self.mode = PositionControlMode.IDLE
            self._emit(PositionControlEvent.TURN_TO_HEADING_TIMEOUT,
                       command_id=self._heading_cmd_id)
            self._emit(PositionControlEvent.MODE_CHANGED)

        return 0.0, w_sat

    # ── Drive to point (matches firmware _update_drive_to_point) ────────

    def _update_drive_to_point(self, rx: float, ry: float, rpsi: float,
                               current_v: float) -> tuple[float, float]:
        c = self.config

        dx = self._point_target_x - rx
        dy = self._point_target_y - ry
        dist = math.hypot(dx, dy)

        # Arrival check
        if dist < c.arrival_tolerance:
            self._arrival_timer += c.Ts
            if self._arrival_timer >= c.arrival_dwell_time:
                self._angular_integral = 0.0
                self._linear_integral = 0.0
                self._arrival_timer = 0.0
                self._reverse_mode = False
                self.mode = PositionControlMode.IDLE
                self._emit(PositionControlEvent.MOVE_TO_POINT_COMPLETED,
                           command_id=self._point_cmd_id)
                self._emit(PositionControlEvent.MODE_CHANGED)
                return 0.0, 0.0
            self.data.speed_limit = 0.0
            self.data.remaining_path_length = dist
            return 0.0, 0.0
        self._arrival_timer = 0.0

        # Reverse mode with hysteresis (always enabled for drive-to-point)
        angle_to_target = math.atan2(dy, dx)
        heading_error_fwd = _normalize_angle(angle_to_target - rpsi)
        abs_heading_error = abs(heading_error_fwd)

        if not self._reverse_mode and abs_heading_error > c.reverse_enter_angle:
            self._reverse_mode = True
            self._angular_integral = 0.0
        elif self._reverse_mode and abs_heading_error < c.reverse_exit_angle:
            self._reverse_mode = False
            self._angular_integral = 0.0

        # Carrot on line to target, pulled back by lookahead_base
        lookahead = c.lookahead_base
        carrot_x = self._point_target_x
        carrot_y = self._point_target_y

        if dist > EPSILON and lookahead > EPSILON:
            step_back = max(0.0, dist - lookahead)
            inv_dist = 1.0 / (dist + EPSILON)
            carrot_x = self._point_target_x - dx * inv_dist * step_back
            carrot_y = self._point_target_y - dy * inv_dist * step_back

        # Heading toward carrot
        dx_carrot = carrot_x - rx
        dy_carrot = carrot_y - ry
        psi_carrot = math.atan2(dy_carrot, dx_carrot)
        carrot_dist = math.hypot(dx_carrot, dy_carrot)

        # In reverse mode, flip heading
        if self._reverse_mode:
            psi_carrot = _normalize_angle(psi_carrot + math.pi)

        heading_error = _normalize_angle(psi_carrot - rpsi)
        self.data.heading_error = heading_error

        # Velocity command
        max_speed = self._point_max_speed

        # Velocity profile: use actual distance to target
        if c.decel_limit > 0.0 and dist > 0.0:
            v_p = math.sqrt(2.0 * c.decel_limit * dist)
        else:
            v_p = c.kp_linear * dist

        # Velocity damping
        v_p = max(0.0, v_p - c.kd_linear * abs(current_v))

        # PI velocity with integral on carrot_dist
        v_i = self._linear_integral
        v_unsat = v_p + v_i
        v_sat = _clamp(v_unsat, 0.0, max_speed)

        if abs(v_unsat - v_sat) < EPSILON:
            self._linear_integral += c.ki_linear * carrot_dist * c.Ts
            self._linear_integral = _clamp(self._linear_integral, 0.0, max_speed)

        cos_scale = max(0.0, math.cos(heading_error))
        v_cmd = v_sat * cos_scale

        if self._reverse_mode:
            v_cmd = -v_cmd

        # Angular command - PI with anti-windup
        w_p = c.kp_angular * heading_error
        w_i = self._angular_integral
        w_unsat = w_p + w_i
        w_sat = _clamp(w_unsat, -c.max_turn_rate, c.max_turn_rate)

        is_saturated = abs(w_unsat - w_sat) > EPSILON
        would_push_further = is_saturated and (
            (w_unsat > w_sat and heading_error > 0.0) or
            (w_unsat < w_sat and heading_error < 0.0))

        if not would_push_further:
            self._angular_integral += c.ki_angular * heading_error * c.Ts
            max_integral = c.max_turn_rate / max(c.ki_angular, 0.01)
            self._angular_integral = _clamp(self._angular_integral, -max_integral, max_integral)

        # Fade near goal
        fade_radius = 2.0 * c.arrival_tolerance
        w_fade = _clamp(dist / fade_radius, 0.0, 1.0)

        psi_dot_cmd = w_sat * w_fade

        # Check timeout
        if self._point_timeout > 0 and self._elapsed_time > self._point_timeout:
            self._angular_integral = 0.0
            self._linear_integral = 0.0
            self._arrival_timer = 0.0
            self._reverse_mode = False
            self.mode = PositionControlMode.IDLE
            self._emit(PositionControlEvent.MOVE_TO_POINT_TIMEOUT,
                       command_id=self._point_cmd_id)
            self._emit(PositionControlEvent.MODE_CHANGED)

        return v_cmd, psi_dot_cmd

    # ── Path following (matches firmware _update_follow_path) ───────────

    def _update_follow_path(self, rx: float, ry: float, rpsi: float,
                            current_v: float) -> tuple[float, float]:
        c = self.config
        path = self._path
        N = len(path)

        if self.path_state != PathState.RUNNING or N < 2:
            return 0.0, 0.0

        # 1. Timeout check
        if self._path_timeout > 0 and self._elapsed_time > self._path_timeout:
            self._emit(PositionControlEvent.PATH_TIMEOUT)
            self.path_state = PathState.IDLE
            self.mode = PositionControlMode.IDLE
            self._emit(PositionControlEvent.MODE_CHANGED)
            return 0.0, 0.0

        # 2. Project robot onto path (monotonic forward)
        self._progress = self._project_onto_path(rx, ry, self._progress)

        # 3-4. Curvature-based speed with exponential smoothing
        kappa = self._estimate_curvature_ahead(self._progress, c.curvature_lookahead)
        v_target_raw = self._path_max_speed / (1.0 + c.curvature_gain * kappa)
        v_target_raw = _clamp(v_target_raw, 0.0, self._path_max_speed)

        alpha_smooth = c.Ts / (c.Ts + SPEED_SMOOTH_TAU)
        self._v_target_smooth = alpha_smooth * v_target_raw + (1.0 - alpha_smooth) * self._v_target_smooth
        v_target = self._v_target_smooth

        # 5. Stop deceleration
        robot_arc = self._cumul_dist_at(self._progress)

        if self._next_stop_ptr < len(self._stop_indices):
            stop_idx = self._stop_indices[self._next_stop_ptr]
            d_to_stop = self._cumul_dist[stop_idx] - robot_arc
            if d_to_stop > 0.0:
                if c.decel_limit > 0.0:
                    v_brake = math.sqrt(2.0 * c.decel_limit * d_to_stop)
                else:
                    v_brake = c.kp_linear * d_to_stop
                v_target = min(v_target, v_brake)

        # Always decelerate toward path end
        d_to_end = self._cumul_dist[N - 1] - robot_arc if self._cumul_dist else 0.0
        if d_to_end > 0.0:
            if c.decel_limit > 0.0:
                v_brake_end = math.sqrt(2.0 * c.decel_limit * d_to_end)
            else:
                v_brake_end = c.kp_linear * d_to_end
            v_target = min(v_target, v_brake_end)
        else:
            v_target = 0.0

        # 6. Compute lookahead
        if c.kp_linear > EPSILON:
            lookahead = v_target / c.kp_linear
        else:
            lookahead = c.lookahead_base * (v_target / max(self._path_max_speed, EPSILON))
        lookahead = max(lookahead, c.lookahead_min)

        # 7. Place carrot along path
        carrot_progress = self._advance_along_path(self._progress, lookahead)

        # Clamp carrot at next stop index
        if self._next_stop_ptr < len(self._stop_indices):
            stop_idx = self._stop_indices[self._next_stop_ptr]
            if carrot_progress > float(stop_idx):
                carrot_progress = float(stop_idx)

        # Clamp at path end
        if carrot_progress > float(N - 1):
            carrot_progress = float(N - 1)

        self._carrot_x, self._carrot_y = self._interpolate_path(carrot_progress)

        # Distance and angle to carrot
        dx_carrot = self._carrot_x - rx
        dy_carrot = self._carrot_y - ry
        carrot_dist = math.hypot(dx_carrot, dy_carrot)
        angle_to_carrot = math.atan2(dy_carrot, dx_carrot)

        # Heading error (forward)
        heading_error_fwd = _normalize_angle(angle_to_carrot - rpsi)

        # 8. Reverse mode (if allow_reverse)
        heading_error = heading_error_fwd

        if self._allow_reverse:
            abs_he = abs(heading_error_fwd)

            if not self._reverse_mode and abs_he > c.reverse_enter_angle:
                self._reverse_mode = True
                self._angular_integral = 0.0
            elif self._reverse_mode and abs_he < c.reverse_exit_angle:
                self._reverse_mode = False
                self._angular_integral = 0.0

            if self._reverse_mode:
                heading_error = _normalize_angle(heading_error_fwd + math.pi)

        self.data.heading_error = heading_error
        self.data.carrot_distance = carrot_dist
        self.data.carrot_x = self._carrot_x
        self.data.carrot_y = self._carrot_y

        # 9. Speed command
        if c.decel_limit > EPSILON:
            # Pre-compensate for velocity damping so steady-state matches v_target
            v_cmd = v_target * (1.0 + c.kd_linear)
        else:
            # Proportional fallback
            v_cmd = min(v_target, c.kp_linear * carrot_dist)

        # Velocity damping
        v_cmd = max(0.0, v_cmd - c.kd_linear * abs(current_v))

        # Scale by cos(heading_error)
        cos_scale = max(0.0, math.cos(heading_error))
        v_cmd *= cos_scale

        # Reverse mode: negate velocity
        if self._reverse_mode:
            v_cmd = -v_cmd

        self.data.speed_limit = v_target

        # 10. Angular command - PI with anti-windup
        w_p = c.kp_angular * heading_error
        w_i = self._angular_integral
        w_unsat = w_p + w_i
        w_sat = _clamp(w_unsat, -c.max_turn_rate, c.max_turn_rate)

        is_saturated = abs(w_unsat - w_sat) > EPSILON
        would_push_further = is_saturated and (
            (w_unsat > w_sat and heading_error > 0.0) or
            (w_unsat < w_sat and heading_error < 0.0))

        if not would_push_further:
            self._angular_integral += c.ki_angular * heading_error * c.Ts
            max_integral = c.max_turn_rate / max(c.ki_angular, 0.01)
            self._angular_integral = _clamp(self._angular_integral, -max_integral, max_integral)

        # Fade yaw rate near carrot
        fade_radius = 2.0 * c.arrival_tolerance
        w_fade = _clamp(carrot_dist / fade_radius, 0.0, 1.0)

        v_out = v_cmd
        w_out = w_sat * w_fade

        # 11. Arrival checks

        # PATH END check
        last_pt_dist = math.hypot(path[-1][0] - rx, path[-1][1] - ry)
        progress_threshold = float(N - 1) - 1.0
        near_end = (self._progress >= progress_threshold) and \
                   (last_pt_dist < c.arrival_tolerance)

        # STOP check
        near_stop = False
        current_stop_idx = 0
        if self._next_stop_ptr < len(self._stop_indices):
            current_stop_idx = self._stop_indices[self._next_stop_ptr]
            stop_pt_dist = math.hypot(path[current_stop_idx][0] - rx,
                                      path[current_stop_idx][1] - ry)
            near_stop = (self._progress >= float(current_stop_idx) - 1.0) and \
                        (stop_pt_dist < c.arrival_tolerance)

        if near_end:
            # PATH END arrival — output zero while dwelling
            v_out = 0.0
            w_out = 0.0
            self._arrival_timer += c.Ts
            if self._arrival_timer >= c.arrival_dwell_time:
                self._emit(PositionControlEvent.PATH_FINISHED)
                self.path_state = PathState.IDLE
                self.mode = PositionControlMode.IDLE
                self._emit(PositionControlEvent.MODE_CHANGED)
            self._update_path_telemetry(N, d_to_end)
            return v_out, w_out

        elif near_stop:
            # STOP point arrival — output zero while dwelling
            if not self._stop_reached_sent:
                self._emit(PositionControlEvent.WAYPOINT_REACHED,
                           waypoint_index=current_stop_idx)
                self._stop_reached_sent = True

            v_out = 0.0
            w_out = 0.0
            self._arrival_timer += c.Ts
            if self._arrival_timer >= c.stop_dwell_time:
                self._emit(PositionControlEvent.WAYPOINT_COMPLETED,
                           waypoint_index=current_stop_idx)
                self._next_stop_ptr += 1
                self._arrival_timer = 0.0
                self._angular_integral = 0.0
                self._stop_reached_sent = False
            self._update_path_telemetry(N, d_to_end)
            return v_out, w_out

        else:
            self._arrival_timer = 0.0
            self._stop_reached_sent = False

        # 12. Final approach — move_to_point-like override near end/stop
        #     Allows reverse to recover from overshoot without oscillation.

        # 12a. Path endpoint approach — activate within stopping distance
        stopping_dist_end = (self._path_max_speed ** 2 / (2.0 * c.decel_limit)) \
            if c.decel_limit > EPSILON else 0.5
        approaching_end = (d_to_end < stopping_dist_end) or (d_to_end < 0.0)

        if approaching_end and not near_end:
            dx_last = path[-1][0] - rx
            dy_last = path[-1][1] - ry
            dist_last = math.hypot(dx_last, dy_last)
            angle_to_last = math.atan2(dy_last, dx_last)
            he_last = _normalize_angle(angle_to_last - rpsi)

            # Speed: sqrt decel toward last point
            if c.decel_limit > EPSILON:
                v_final = math.sqrt(2.0 * c.decel_limit * dist_last)
            else:
                v_final = c.kp_linear * dist_last
            v_final = max(0.0, v_final - c.kd_linear * abs(current_v))
            v_final = min(v_final, self._path_max_speed)

            # Allow reverse if overshot (heading > reverse_enter_angle)
            reverse_last = abs(he_last) > c.reverse_enter_angle
            if reverse_last:
                he_last = _normalize_angle(he_last + math.pi)
                v_out = -v_final * max(0.0, math.cos(he_last))
            else:
                v_out = v_final * max(0.0, math.cos(he_last))

            # Angular with fade near target
            w_last = _clamp(c.kp_angular * he_last, -c.max_turn_rate, c.max_turn_rate)
            fade_last = _clamp(dist_last / (2.0 * c.arrival_tolerance), 0.0, 1.0)
            w_out = w_last * fade_last

        # 12b. STOP waypoint approach — move_to_point-like drive toward stop
        if self._next_stop_ptr < len(self._stop_indices) and not near_stop:
            stop_idx = self._stop_indices[self._next_stop_ptr]
            stop_x, stop_y = path[stop_idx]
            dx_stop = stop_x - rx
            dy_stop = stop_y - ry
            dist_stop = math.hypot(dx_stop, dy_stop)

            stopping_dist = (self._path_max_speed ** 2 / (2.0 * c.decel_limit)) \
                if c.decel_limit > EPSILON else 0.5

            arc_to_stop = self._cumul_dist[stop_idx] - robot_arc
            approaching_stop = (arc_to_stop < stopping_dist) or (arc_to_stop < 0.0)

            if approaching_stop:
                angle_to_stop = math.atan2(dy_stop, dx_stop)
                he_stop = _normalize_angle(angle_to_stop - rpsi)

                if c.decel_limit > EPSILON:
                    v_stop = math.sqrt(2.0 * c.decel_limit * dist_stop)
                else:
                    v_stop = c.kp_linear * dist_stop
                v_stop = max(0.0, v_stop - c.kd_linear * abs(current_v))
                v_stop = min(v_stop, self._path_max_speed)

                # Allow reverse if overshot
                reverse_stop = abs(he_stop) > c.reverse_enter_angle
                if reverse_stop:
                    he_stop = _normalize_angle(he_stop + math.pi)
                    v_out = -v_stop * max(0.0, math.cos(he_stop))
                else:
                    v_out = v_stop * max(0.0, math.cos(he_stop))

                w_stop = _clamp(c.kp_angular * he_stop, -c.max_turn_rate, c.max_turn_rate)
                fade_stop = _clamp(dist_stop / (2.0 * c.arrival_tolerance), 0.0, 1.0)
                w_out = w_stop * fade_stop

        # Update telemetry
        self._update_path_telemetry(N, d_to_end)
        return v_out, w_out

    def _update_path_telemetry(self, N: int, d_to_end: float):
        self.data.path_point_count = N
        self.data.current_index = int(self._progress)
        self.data.remaining_path_length = max(0.0, d_to_end)
        self.data.progress = self._progress

    # ── Path geometry helpers ───────────────────────────────────────────

    def _compute_cumulative_distances(self):
        """Compute cumulative arc-length distances for the path."""
        self._cumul_dist = [0.0]
        for i in range(1, len(self._path)):
            dx = self._path[i][0] - self._path[i - 1][0]
            dy = self._path[i][1] - self._path[i - 1][1]
            self._cumul_dist.append(self._cumul_dist[-1] + math.hypot(dx, dy))

    def _cumul_dist_at(self, progress: float) -> float:
        """Get cumulative arc length at a floating-point progress value."""
        N = len(self._cumul_dist)
        if N < 2:
            return 0.0
        if progress <= 0.0:
            return self._cumul_dist[0]
        if progress >= N - 1:
            return self._cumul_dist[-1]
        idx = int(progress)
        t = progress - idx
        return self._cumul_dist[idx] + t * (self._cumul_dist[idx + 1] - self._cumul_dist[idx])

    def _estimate_curvature_ahead(self, at_progress: float, lookahead_dist: float) -> float:
        """Estimate max path curvature in a lookahead window using Menger curvature."""
        N = len(self._path)
        if N < 3:
            return 0.0

        start_idx = int(at_progress)
        if start_idx >= N - 1:
            start_idx = N - 2

        # Find end index based on lookahead distance
        start_arc = self._cumul_dist[start_idx]
        end_arc = start_arc + lookahead_dist

        end_idx = start_idx
        while end_idx < N - 1 and self._cumul_dist[end_idx] < end_arc:
            end_idx += 1

        # Compute stride: ~50mm chord for robust curvature estimation
        avg_spacing = (self._path_total_length / (N - 1)) if N > 1 else 0.015
        stride = int(0.05 / max(avg_spacing, 0.001))
        stride = max(1, min(stride, 15))

        # Need at least 2*stride points for a single curvature measurement
        if end_idx < start_idx + 2 * stride:
            if start_idx + 2 * stride < N:
                end_idx = start_idx + 2 * stride
            else:
                return 0.0

        max_kappa = 0.0

        i = start_idx
        while i + 2 * stride <= end_idx and i + 2 * stride < N:
            ax, ay = self._path[i]
            bx, by = self._path[i + stride]
            cx, cy = self._path[i + 2 * stride]

            abx, aby = bx - ax, by - ay
            bcx, bcy = cx - bx, cy - by
            acx, acy = cx - ax, cy - ay

            cross_mag = abs(abx * acy - aby * acx)
            ab_len = math.hypot(abx, aby)
            bc_len = math.hypot(bcx, bcy)
            ac_len = math.hypot(acx, acy)

            denom = ab_len * bc_len * ac_len
            if denom > 1e-10:
                kappa = 2.0 * cross_mag / denom
                if kappa > max_kappa:
                    max_kappa = kappa
            i += 1

        return max_kappa

    def _project_onto_path(self, rx: float, ry: float, last_progress: float) -> float:
        """Find closest point on path ahead of last_progress (monotonic forward)."""
        path = self._path
        N = len(path)
        if N < 2:
            return 0.0

        start_seg = int(last_progress)
        if start_seg >= N - 1:
            start_seg = N - 2

        end_seg = min(start_seg + PROJECTION_SEARCH_WINDOW, N - 2)

        best_progress = last_progress
        best_dist_sq = 1e30

        for i in range(start_seg, end_seg + 1):
            ax, ay = path[i]
            bx, by = path[i + 1]
            dx, dy = bx - ax, by - ay
            seg_len_sq = dx * dx + dy * dy

            if seg_len_sq < EPSILON:
                t = 0.0
            else:
                t = ((rx - ax) * dx + (ry - ay) * dy) / seg_len_sq
                t = _clamp(t, 0.0, 1.0)

            proj_x = ax + t * dx
            proj_y = ay + t * dy
            dist_sq = (rx - proj_x) ** 2 + (ry - proj_y) ** 2

            candidate = float(i) + t

            # Only accept if monotonically forward
            if candidate >= last_progress and dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_progress = candidate

        return best_progress

    def _advance_along_path(self, from_progress: float, distance: float) -> float:
        """Advance along path by arc distance. Uses binary search like firmware."""
        N = len(self._path)
        if N < 2:
            return from_progress

        current_arc = self._cumul_dist_at(from_progress)
        target_arc = current_arc + distance

        # Clamp to path end
        if target_arc >= self._cumul_dist[-1]:
            return float(N - 1)
        if target_arc <= 0.0:
            return 0.0

        # Binary search for segment containing target_arc
        lo, hi = 0, N - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if self._cumul_dist[mid] <= target_arc:
                lo = mid
            else:
                hi = mid

        # Interpolate within segment [lo, lo+1]
        seg_start = self._cumul_dist[lo]
        seg_end = self._cumul_dist[lo + 1]
        seg_len = seg_end - seg_start

        t = 0.0
        if seg_len > EPSILON:
            t = _clamp((target_arc - seg_start) / seg_len, 0.0, 1.0)

        return float(lo) + t

    def _interpolate_path(self, progress: float) -> tuple[float, float]:
        path = self._path
        N = len(path)
        if N == 0:
            return 0.0, 0.0
        if progress <= 0:
            return path[0]
        if progress >= N - 1:
            return path[-1]
        idx = int(progress)
        frac = progress - idx
        ax, ay = path[idx]
        bx, by = path[min(idx + 1, N - 1)]
        return ax + frac * (bx - ax), ay + frac * (by - ay)
