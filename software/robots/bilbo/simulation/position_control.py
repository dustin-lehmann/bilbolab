"""Python port of the BILBO firmware position control module.

Faithfully implements the firmware's three position control modes:
1. TURN_TO_HEADING: Rotate in place to a target heading (PI angular control)
2. DRIVE_TO_POINT: Drive to a single XY position (pure pursuit + reverse mode)
3. FOLLOW_PATH: Follow a dense pre-planned path (curvature-based speed, pure pursuit)

Output is (v_cmd, psi_dot_cmd) which feeds into the velocity control layer.

Reference: robots/bilbo/firmware/firmware/control/bilbo_position_control.cpp
"""

import dataclasses
import enum
import math

import numpy as np

from core.utils.logging_utils import Logger

EPSILON = 1e-6
PROJECTION_SEARCH_WINDOW = 30
SPEED_SMOOTH_TAU = 0.1  # [s] Low-pass filter time constant
HEADING_ARRIVAL_TOLERANCE = 0.05  # [rad] ~3 degrees


# ======================================================================================================================
# Enumerations
# ======================================================================================================================

class PositionControlMode(enum.IntEnum):
    IDLE = 0
    TURN_TO_HEADING = 1
    DRIVE_TO_POINT = 2
    FOLLOW_PATH = 3


class PathState(enum.IntEnum):
    IDLE = 0
    RUNNING = 1
    PAUSED = 2


# ======================================================================================================================
# Data structures
# ======================================================================================================================

@dataclasses.dataclass
class PositionControlConfig:
    """Configuration parameters matching firmware bilbo_position_control_config_t."""
    Ts: float = 0.01
    kp_angular: float = 10.0
    ki_angular: float = 0.3
    kp_angular_heading: float = 0.0
    ki_angular_heading: float = 0.0
    kp_linear: float = 2.0
    ki_linear: float = 0.0
    kd_linear: float = 0.5
    max_speed: float = 1.0
    max_turn_rate: float = 5.0
    lookahead_base: float = 0.15
    lookahead_min: float = 0.03
    arrival_tolerance: float = 0.05
    arrival_dwell_time: float = 0.5
    stop_dwell_time: float = 1.0
    reverse_enter_angle: float = 2.1
    reverse_exit_angle: float = 1.05
    decel_limit: float = 0.6
    curvature_gain: float = 0.2
    curvature_lookahead: float = 0.05


@dataclasses.dataclass
class PositionControlOutput:
    v_cmd: float = 0.0
    psi_dot_cmd: float = 0.0


@dataclasses.dataclass
class PathStartCommand:
    max_speed: float = 0.0
    max_spacing: float = 0.0
    timeout: float = 0.0
    allow_reverse: bool = False


@dataclasses.dataclass
class TurnToHeadingCommand:
    heading_ref: float = 0.0
    timeout: float = 0.0
    max_angular_speed: float = 0.0


@dataclasses.dataclass
class MoveToPointCommand:
    x_target: float = 0.0
    y_target: float = 0.0
    timeout: float = 0.0
    max_speed: float = 0.0


# ======================================================================================================================
# Utilities
# ======================================================================================================================

def _normalize_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


# ======================================================================================================================
# BILBO_PositionControl
# ======================================================================================================================

class BILBO_PositionControl:
    """Python port of the firmware position control module.

    Outputs (v_cmd, psi_dot_cmd) velocity commands that feed into
    the velocity controller layer.
    """

    def __init__(self, config: PositionControlConfig | None = None):
        self.config = config or PositionControlConfig()
        self.mode = PositionControlMode.IDLE
        self.logger = Logger("BILBO_PositionControl", "DEBUG")

        # Path buffer
        self._path: np.ndarray = np.empty((0, 2), dtype=float)
        self._cumul_dist: np.ndarray = np.empty(0, dtype=float)
        self._stop_indices: list[int] = []

        # Path state
        self._path_state = PathState.IDLE
        self._progress: float = 0.0
        self._path_max_speed: float = 0.0
        self._path_max_spacing: float = 0.0
        self._path_total_length: float = 0.0
        self._next_stop_ptr: int = 0

        # Carrot
        self._carrot_x: float = 0.0
        self._carrot_y: float = 0.0

        # Control state
        self._angular_integral: float = 0.0
        self._linear_integral: float = 0.0
        self._arrival_timer: float = 0.0
        self._elapsed_time: float = 0.0
        self._reverse_mode_active: bool = False
        self._stop_reached_sent: bool = False
        self._v_target_smooth: float = 0.0

        # Active commands
        self._active_turn_command = TurnToHeadingCommand()
        self._active_move_command = MoveToPointCommand()
        self._active_path_command = PathStartCommand()

        # Callbacks (user-settable)
        self.on_path_finished = None
        self.on_path_timeout = None
        self.on_move_completed = None
        self.on_turn_completed = None
        self.on_stop_reached = None
        self.on_stop_completed = None

    # === CONFIGURATION ================================================================================================

    def set_config(self, config: PositionControlConfig) -> bool:
        if config.Ts <= 0 or config.max_speed <= 0 or config.max_turn_rate <= 0:
            return False
        self.config = config
        return True

    # === SINGLE-POINT COMMANDS ========================================================================================

    def turn_to_heading(self, heading_ref: float, timeout: float = 0.0,
                        max_angular_speed: float = 0.0) -> bool:
        if self.mode != PositionControlMode.IDLE:
            return False

        self._active_turn_command = TurnToHeadingCommand(
            heading_ref=heading_ref, timeout=timeout,
            max_angular_speed=max_angular_speed)
        self._elapsed_time = 0.0
        self._angular_integral = 0.0
        self._arrival_timer = 0.0
        self._set_mode(PositionControlMode.TURN_TO_HEADING)
        return True

    def move_to_point(self, x: float, y: float, timeout: float = 0.0,
                      max_speed: float = 0.0) -> bool:
        if self.mode != PositionControlMode.IDLE:
            return False

        self._active_move_command = MoveToPointCommand(
            x_target=x, y_target=y, timeout=timeout, max_speed=max_speed)
        self._elapsed_time = 0.0
        self._angular_integral = 0.0
        self._linear_integral = 0.0
        self._arrival_timer = 0.0
        self._reverse_mode_active = False
        self._set_mode(PositionControlMode.DRIVE_TO_POINT)
        return True

    # === PATH MANAGEMENT ==============================================================================================

    def clear_path(self):
        self._path = np.empty((0, 2), dtype=float)
        self._cumul_dist = np.empty(0, dtype=float)
        self._stop_indices = []
        self._path_state = PathState.IDLE
        self._progress = 0.0
        self._angular_integral = 0.0
        self._linear_integral = 0.0
        self._arrival_timer = 0.0
        self._reverse_mode_active = False
        self._stop_reached_sent = False
        self._next_stop_ptr = 0
        self._path_max_speed = 0.0
        self._path_max_spacing = 0.0
        self._path_total_length = 0.0
        self._v_target_smooth = 0.0

    def set_path(self, points, stop_indices: list[int] | None = None):
        """Set path from a list/array of (x, y) points."""
        self._path = np.asarray(points, dtype=float).reshape(-1, 2)
        self._stop_indices = list(stop_indices) if stop_indices else []

    def start_path(self, command: PathStartCommand | None = None) -> bool:
        cmd = command or PathStartCommand()
        n = len(self._path)
        if n < 2:
            return False
        if self.mode != PositionControlMode.IDLE:
            return False

        self._compute_cumulative_distances()

        self._path_max_speed = cmd.max_speed if cmd.max_speed > 0 else self.config.max_speed

        if cmd.max_spacing > 0:
            self._path_max_spacing = cmd.max_spacing
        else:
            diffs = np.diff(self._cumul_dist)
            self._path_max_spacing = float(np.max(diffs)) if len(diffs) > 0 else 0.01
            if self._path_max_spacing < EPSILON:
                self._path_max_spacing = 0.01

        self._path_total_length = float(self._cumul_dist[-1])

        self._progress = 0.0
        self._angular_integral = 0.0
        self._linear_integral = 0.0
        self._arrival_timer = 0.0
        self._elapsed_time = 0.0
        self._reverse_mode_active = False
        self._stop_reached_sent = False
        self._next_stop_ptr = 0
        self._v_target_smooth = 0.0

        self._carrot_x = float(self._path[0, 0])
        self._carrot_y = float(self._path[0, 1])

        self._active_path_command = cmd
        self._path_state = PathState.RUNNING
        self._set_mode(PositionControlMode.FOLLOW_PATH)

        self.logger.info(f"PATH START: {n} pts, {len(self._stop_indices)} stops, "
                         f"max_speed={self._path_max_speed:.2f}, "
                         f"total_len={self._path_total_length:.2f}")
        return True

    def pause_path(self):
        if self._path_state == PathState.RUNNING:
            self._path_state = PathState.PAUSED

    def resume_path(self):
        if self._path_state == PathState.PAUSED:
            self._path_state = PathState.RUNNING

    def abort_path(self):
        if self.mode == PositionControlMode.FOLLOW_PATH:
            self._path_state = PathState.IDLE
            self._set_mode(PositionControlMode.IDLE)

    # === STATUS =======================================================================================================

    @property
    def is_idle(self) -> bool:
        return self.mode == PositionControlMode.IDLE

    @property
    def is_running(self) -> bool:
        return self._path_state == PathState.RUNNING

    @property
    def progress(self) -> float:
        return self._progress

    # === MAIN UPDATE ==================================================================================================

    def update(self, x: float, y: float, psi: float, v: float) -> PositionControlOutput:
        """Main update. Call every Ts.

        Args:
            x, y: Robot position [m]
            psi: Robot heading [rad]
            v: Forward velocity [m/s]

        Returns:
            PositionControlOutput with v_cmd and psi_dot_cmd
        """
        output = PositionControlOutput()

        if self.mode != PositionControlMode.IDLE:
            self._elapsed_time += self.config.Ts

        if self.mode == PositionControlMode.IDLE:
            pass
        elif self.mode == PositionControlMode.TURN_TO_HEADING:
            output = self._update_turn_to_heading(x, y, psi)
        elif self.mode == PositionControlMode.DRIVE_TO_POINT:
            output = self._update_drive_to_point(x, y, psi, v)
        elif self.mode == PositionControlMode.FOLLOW_PATH:
            output = self._update_follow_path(x, y, psi, v)

        return output

    def reset(self):
        self._angular_integral = 0.0
        self._linear_integral = 0.0
        self._arrival_timer = 0.0
        self._elapsed_time = 0.0
        self._reverse_mode_active = False
        self.clear_path()
        self._set_mode(PositionControlMode.IDLE)

    # === PRIVATE: MODE TRANSITIONS ====================================================================================

    def _set_mode(self, new_mode: PositionControlMode):
        self.mode = new_mode

    # === PRIVATE: TURN TO HEADING =====================================================================================

    def _update_turn_to_heading(self, x: float, y: float, psi: float) -> PositionControlOutput:
        output = PositionControlOutput()
        cfg = self.config
        cmd = self._active_turn_command

        heading_error = _normalize_angle(cmd.heading_ref - psi)
        max_rate = cmd.max_angular_speed if cmd.max_angular_speed > 0 else cfg.max_turn_rate

        # Resolve effective angular gains (heading-specific overrides, 0 = use base)
        eff_kp = cfg.kp_angular_heading if cfg.kp_angular_heading > 0 else cfg.kp_angular
        eff_ki = cfg.ki_angular_heading if cfg.ki_angular_heading > 0 else cfg.ki_angular

        # PI control with anti-windup
        w_p = eff_kp * heading_error
        w_i = self._angular_integral
        w_unsat = w_p + w_i
        w_sat = _clamp(w_unsat, -max_rate, max_rate)

        is_saturated = abs(w_unsat - w_sat) > EPSILON
        would_push_further = is_saturated and (
            (w_unsat > w_sat and heading_error > 0) or
            (w_unsat < w_sat and heading_error < 0))

        if not would_push_further:
            self._angular_integral += eff_ki * heading_error * cfg.Ts
            max_integral = max_rate / max(eff_ki, 0.01)
            self._angular_integral = _clamp(self._angular_integral, -max_integral, max_integral)

        output.psi_dot_cmd = w_sat

        # Check completion
        if abs(heading_error) < HEADING_ARRIVAL_TOLERANCE:
            self._arrival_timer += cfg.Ts
            if self._arrival_timer >= cfg.arrival_dwell_time:
                self._angular_integral = 0.0
                self._arrival_timer = 0.0
                self._set_mode(PositionControlMode.IDLE)
                if self.on_turn_completed:
                    self.on_turn_completed()
                return output
        else:
            self._arrival_timer = 0.0

        # Timeout
        if cmd.timeout > 0 and self._elapsed_time > cmd.timeout:
            self._angular_integral = 0.0
            self._arrival_timer = 0.0
            self._set_mode(PositionControlMode.IDLE)

        return output

    # === PRIVATE: DRIVE TO POINT ======================================================================================

    def _update_drive_to_point(self, x: float, y: float, psi: float,
                               v: float) -> PositionControlOutput:
        output = PositionControlOutput()
        cfg = self.config
        cmd = self._active_move_command

        dx = cmd.x_target - x
        dy = cmd.y_target - y
        dist = math.hypot(dx, dy)

        # Check completion
        if dist < cfg.arrival_tolerance:
            self._arrival_timer += cfg.Ts
            if self._arrival_timer >= cfg.arrival_dwell_time:
                self._angular_integral = 0.0
                self._linear_integral = 0.0
                self._arrival_timer = 0.0
                self._reverse_mode_active = False
                self._set_mode(PositionControlMode.IDLE)
                if self.on_move_completed:
                    self.on_move_completed()
                return output
            return output
        self._arrival_timer = 0.0

        # Reverse mode with hysteresis
        angle_to_target = math.atan2(dy, dx)
        heading_error_fwd = _normalize_angle(angle_to_target - psi)
        abs_heading_error = abs(heading_error_fwd)

        if not self._reverse_mode_active and abs_heading_error > cfg.reverse_enter_angle:
            self._reverse_mode_active = True
            self._angular_integral = 0.0
        elif self._reverse_mode_active and abs_heading_error < cfg.reverse_exit_angle:
            self._reverse_mode_active = False
            self._angular_integral = 0.0

        # Carrot on line to target
        lookahead = cfg.lookahead_base
        carrot_x = cmd.x_target
        carrot_y = cmd.y_target

        if dist > EPSILON and lookahead > EPSILON:
            step_back = max(0.0, dist - lookahead)
            inv_dist = 1.0 / (dist + EPSILON)
            carrot_x = cmd.x_target - dx * inv_dist * step_back
            carrot_y = cmd.y_target - dy * inv_dist * step_back

        dx_carrot = carrot_x - x
        dy_carrot = carrot_y - y
        psi_carrot = math.atan2(dy_carrot, dx_carrot)
        carrot_dist = math.hypot(dx_carrot, dy_carrot)

        if self._reverse_mode_active:
            psi_carrot = _normalize_angle(psi_carrot + math.pi)

        heading_error = _normalize_angle(psi_carrot - psi)

        # Velocity command
        max_speed = cmd.max_speed if cmd.max_speed > 0 else cfg.max_speed

        if cfg.decel_limit > 0 and dist > 0:
            v_p = math.sqrt(2.0 * cfg.decel_limit * dist)
        else:
            v_p = cfg.kp_linear * dist

        v_p = max(0.0, v_p - cfg.kd_linear * abs(v))

        v_i = self._linear_integral
        v_unsat = v_p + v_i
        v_sat = _clamp(v_unsat, 0.0, max_speed)

        if abs(v_unsat - v_sat) < EPSILON:
            self._linear_integral += cfg.ki_linear * carrot_dist * cfg.Ts
            self._linear_integral = _clamp(self._linear_integral, 0.0, max_speed)

        cos_scale = max(0.0, math.cos(heading_error))
        v_cmd = v_sat * cos_scale

        if self._reverse_mode_active:
            v_cmd = -v_cmd

        output.v_cmd = v_cmd

        # Angular command with anti-windup
        w_p = cfg.kp_angular * heading_error
        w_i = self._angular_integral
        w_unsat = w_p + w_i
        w_sat = _clamp(w_unsat, -cfg.max_turn_rate, cfg.max_turn_rate)

        is_saturated = abs(w_unsat - w_sat) > EPSILON
        would_push_further = is_saturated and (
            (w_unsat > w_sat and heading_error > 0) or
            (w_unsat < w_sat and heading_error < 0))

        if not would_push_further:
            self._angular_integral += cfg.ki_angular * heading_error * cfg.Ts
            max_integral = cfg.max_turn_rate / max(cfg.ki_angular, 0.01)
            self._angular_integral = _clamp(self._angular_integral, -max_integral, max_integral)

        fade_radius = 2.0 * cfg.arrival_tolerance
        w_fade = _clamp(dist / fade_radius, 0.0, 1.0)
        output.psi_dot_cmd = w_sat * w_fade

        # Timeout
        if cmd.timeout > 0 and self._elapsed_time > cmd.timeout:
            self._angular_integral = 0.0
            self._linear_integral = 0.0
            self._arrival_timer = 0.0
            self._reverse_mode_active = False
            self._set_mode(PositionControlMode.IDLE)

        return output

    # === PRIVATE: FOLLOW PATH =========================================================================================

    def _update_follow_path(self, x: float, y: float, psi: float,
                            v: float) -> PositionControlOutput:
        output = PositionControlOutput()
        cfg = self.config
        n = len(self._path)

        if self._path_state != PathState.RUNNING or n < 2:
            return output

        # 1. Timeout
        if self._active_path_command.timeout > 0 and \
                self._elapsed_time > self._active_path_command.timeout:
            self._path_state = PathState.IDLE
            self._set_mode(PositionControlMode.IDLE)
            if self.on_path_timeout:
                self.on_path_timeout()
            return output

        # 2. Project robot onto path (monotonic forward)
        self._progress = self._project_onto_path(x, y, self._progress)

        # 3. Curvature-based speed target
        kappa = self._estimate_curvature_ahead(self._progress, cfg.curvature_lookahead)
        v_target_raw = self._path_max_speed / (1.0 + cfg.curvature_gain * kappa)
        v_target_raw = _clamp(v_target_raw, 0.0, self._path_max_speed)

        # 4. Exponential smoothing
        alpha_smooth = cfg.Ts / (cfg.Ts + SPEED_SMOOTH_TAU)
        self._v_target_smooth = (alpha_smooth * v_target_raw +
                                 (1.0 - alpha_smooth) * self._v_target_smooth)
        v_target = self._v_target_smooth

        # 5. Stop deceleration
        robot_arc = self._cumul_dist_at(self._progress)

        if self._next_stop_ptr < len(self._stop_indices):
            stop_idx = self._stop_indices[self._next_stop_ptr]
            d_to_stop = float(self._cumul_dist[stop_idx]) - robot_arc
            if d_to_stop > 0:
                if cfg.decel_limit > 0:
                    v_brake = math.sqrt(2.0 * cfg.decel_limit * d_to_stop)
                else:
                    v_brake = cfg.kp_linear * d_to_stop
                v_target = min(v_target, v_brake)

        # Decelerate toward path end
        d_to_end = float(self._cumul_dist[-1]) - robot_arc
        if d_to_end > 0:
            if cfg.decel_limit > 0:
                v_brake_end = math.sqrt(2.0 * cfg.decel_limit * d_to_end)
            else:
                v_brake_end = cfg.kp_linear * d_to_end
            v_target = min(v_target, v_brake_end)
        else:
            v_target = 0.0

        # 6. Compute lookahead
        if cfg.kp_linear > EPSILON:
            lookahead = v_target / cfg.kp_linear
        else:
            lookahead = cfg.lookahead_base * (v_target / max(self._path_max_speed, EPSILON))
        lookahead = max(lookahead, cfg.lookahead_min)

        # 7. Place carrot along path
        carrot_progress = self._advance_along_path(self._progress, lookahead)

        if self._next_stop_ptr < len(self._stop_indices):
            stop_idx = self._stop_indices[self._next_stop_ptr]
            if carrot_progress > float(stop_idx):
                carrot_progress = float(stop_idx)

        carrot_progress = min(carrot_progress, float(n - 1))

        cx, cy = self._interpolate_path(carrot_progress)
        self._carrot_x = cx
        self._carrot_y = cy

        dx_carrot = cx - x
        dy_carrot = cy - y
        carrot_dist = math.hypot(dx_carrot, dy_carrot)
        angle_to_carrot = math.atan2(dy_carrot, dx_carrot)

        heading_error_fwd = _normalize_angle(angle_to_carrot - psi)
        heading_error = heading_error_fwd

        # 8. Reverse mode
        if self._active_path_command.allow_reverse:
            abs_he = abs(heading_error_fwd)
            if not self._reverse_mode_active and abs_he > cfg.reverse_enter_angle:
                self._reverse_mode_active = True
                self._angular_integral = 0.0
            elif self._reverse_mode_active and abs_he < cfg.reverse_exit_angle:
                self._reverse_mode_active = False
                self._angular_integral = 0.0
            if self._reverse_mode_active:
                heading_error = _normalize_angle(heading_error_fwd + math.pi)

        # 9. Speed command
        if cfg.decel_limit > EPSILON:
            v_cmd = v_target * (1.0 + cfg.kd_linear)
        else:
            v_cmd = min(v_target, cfg.kp_linear * carrot_dist)

        v_cmd = max(0.0, v_cmd - cfg.kd_linear * abs(v))
        cos_scale = max(0.0, math.cos(heading_error))
        v_cmd *= cos_scale

        if self._reverse_mode_active:
            v_cmd = -v_cmd

        output.v_cmd = v_cmd

        # 10. Angular command with anti-windup
        w_p = cfg.kp_angular * heading_error
        w_i = self._angular_integral
        w_unsat = w_p + w_i
        w_sat = _clamp(w_unsat, -cfg.max_turn_rate, cfg.max_turn_rate)

        is_saturated = abs(w_unsat - w_sat) > EPSILON
        would_push_further = is_saturated and (
            (w_unsat > w_sat and heading_error > 0) or
            (w_unsat < w_sat and heading_error < 0))

        if not would_push_further:
            self._angular_integral += cfg.ki_angular * heading_error * cfg.Ts
            max_integral = cfg.max_turn_rate / max(cfg.ki_angular, 0.01)
            self._angular_integral = _clamp(self._angular_integral,
                                            -max_integral, max_integral)

        fade_radius = 2.0 * cfg.arrival_tolerance
        w_fade = _clamp(carrot_dist / fade_radius, 0.0, 1.0)
        output.psi_dot_cmd = w_sat * w_fade

        # 11. Arrival checks
        last_pt_dist = math.hypot(x - float(self._path[-1, 0]),
                                  y - float(self._path[-1, 1]))
        progress_threshold = float(n - 1) - 1.0
        near_end = (self._progress >= progress_threshold and
                    last_pt_dist < cfg.arrival_tolerance)

        near_stop = False
        current_stop_idx = 0
        if self._next_stop_ptr < len(self._stop_indices):
            current_stop_idx = self._stop_indices[self._next_stop_ptr]
            stop_pt_dist = math.hypot(
                x - float(self._path[current_stop_idx, 0]),
                y - float(self._path[current_stop_idx, 1]))
            near_stop = (self._progress >= float(current_stop_idx) - 1.0 and
                         stop_pt_dist < cfg.arrival_tolerance)

        if near_end:
            output.v_cmd = 0.0
            output.psi_dot_cmd = 0.0
            self._arrival_timer += cfg.Ts
            if self._arrival_timer >= cfg.arrival_dwell_time:
                self._path_state = PathState.IDLE
                self._set_mode(PositionControlMode.IDLE)
                if self.on_path_finished:
                    self.on_path_finished()
            return output
        elif near_stop:
            if not self._stop_reached_sent:
                if self.on_stop_reached:
                    self.on_stop_reached(current_stop_idx)
                self._stop_reached_sent = True

            output.v_cmd = 0.0
            output.psi_dot_cmd = 0.0
            self._arrival_timer += cfg.Ts
            if self._arrival_timer >= cfg.stop_dwell_time:
                if self.on_stop_completed:
                    self.on_stop_completed(current_stop_idx)
                self._next_stop_ptr += 1
                self._arrival_timer = 0.0
                self._angular_integral = 0.0
                self._stop_reached_sent = False
            return output
        else:
            self._arrival_timer = 0.0
            self._stop_reached_sent = False

        # 12. Final approach — move_to_point-like drive near path end or stop
        stopping_dist_end = ((self._path_max_speed ** 2 / (2.0 * cfg.decel_limit))
                             if cfg.decel_limit > EPSILON else 0.5)
        approaching_end = (d_to_end < stopping_dist_end) or (d_to_end < 0)

        if approaching_end and not near_end:
            dx_last = float(self._path[-1, 0]) - x
            dy_last = float(self._path[-1, 1]) - y
            dist_last = math.hypot(dx_last, dy_last)
            angle_to_last = math.atan2(dy_last, dx_last)
            he_last = _normalize_angle(angle_to_last - psi)

            if cfg.decel_limit > EPSILON:
                v_final = math.sqrt(2.0 * cfg.decel_limit * dist_last)
            else:
                v_final = cfg.kp_linear * dist_last
            v_final = max(0.0, v_final - cfg.kd_linear * abs(v))
            v_final = min(v_final, self._path_max_speed)

            reverse_last = abs(he_last) > cfg.reverse_enter_angle
            if reverse_last:
                he_last = _normalize_angle(he_last + math.pi)
                output.v_cmd = -v_final * max(0.0, math.cos(he_last))
            else:
                output.v_cmd = v_final * max(0.0, math.cos(he_last))

            w_last = _clamp(cfg.kp_angular * he_last,
                            -cfg.max_turn_rate, cfg.max_turn_rate)
            fade_last = _clamp(dist_last / (2.0 * cfg.arrival_tolerance), 0.0, 1.0)
            output.psi_dot_cmd = w_last * fade_last

        # Stop waypoint approach
        if self._next_stop_ptr < len(self._stop_indices) and not near_stop:
            stop_idx = self._stop_indices[self._next_stop_ptr]
            stop_x = float(self._path[stop_idx, 0])
            stop_y = float(self._path[stop_idx, 1])
            dx_stop = stop_x - x
            dy_stop = stop_y - y
            dist_stop = math.hypot(dx_stop, dy_stop)

            stopping_dist = ((self._path_max_speed ** 2 / (2.0 * cfg.decel_limit))
                             if cfg.decel_limit > EPSILON else 0.5)
            arc_to_stop = float(self._cumul_dist[stop_idx]) - robot_arc
            approaching_stop = (arc_to_stop < stopping_dist) or (arc_to_stop < 0)

            if approaching_stop:
                angle_to_stop = math.atan2(dy_stop, dx_stop)
                he_stop = _normalize_angle(angle_to_stop - psi)

                if cfg.decel_limit > EPSILON:
                    v_stop = math.sqrt(2.0 * cfg.decel_limit * dist_stop)
                else:
                    v_stop = cfg.kp_linear * dist_stop
                v_stop = max(0.0, v_stop - cfg.kd_linear * abs(v))
                v_stop = min(v_stop, self._path_max_speed)

                reverse_stop = abs(he_stop) > cfg.reverse_enter_angle
                if reverse_stop:
                    he_stop = _normalize_angle(he_stop + math.pi)
                    output.v_cmd = -v_stop * max(0.0, math.cos(he_stop))
                else:
                    output.v_cmd = v_stop * max(0.0, math.cos(he_stop))

                w_stop = _clamp(cfg.kp_angular * he_stop,
                                -cfg.max_turn_rate, cfg.max_turn_rate)
                fade_stop = _clamp(dist_stop / (2.0 * cfg.arrival_tolerance),
                                   0.0, 1.0)
                output.psi_dot_cmd = w_stop * fade_stop

        return output

    # === PRIVATE: PATH GEOMETRY =======================================================================================

    def _compute_cumulative_distances(self):
        n = len(self._path)
        self._cumul_dist = np.zeros(n, dtype=float)
        if n < 2:
            return
        diffs = np.diff(self._path, axis=0)
        seg_lengths = np.hypot(diffs[:, 0], diffs[:, 1])
        self._cumul_dist[1:] = np.cumsum(seg_lengths)

    def _project_onto_path(self, robot_x: float, robot_y: float,
                           last_progress: float) -> float:
        n = len(self._path)
        start_seg = int(last_progress)
        if start_seg >= n - 1:
            start_seg = n - 2

        end_seg = min(start_seg + PROJECTION_SEARCH_WINDOW, n - 2)

        best_progress = last_progress
        best_dist_sq = 1e30

        for i in range(start_seg, end_seg + 1):
            ax = float(self._path[i, 0])
            ay = float(self._path[i, 1])
            bx = float(self._path[i + 1, 0])
            by = float(self._path[i + 1, 1])

            dx = bx - ax
            dy = by - ay
            len_sq = dx * dx + dy * dy

            if len_sq < EPSILON:
                t = 0.0
            else:
                t = ((robot_x - ax) * dx + (robot_y - ay) * dy) / len_sq
                t = _clamp(t, 0.0, 1.0)

            proj_x = ax + t * dx
            proj_y = ay + t * dy
            dist_sq = (robot_x - proj_x) ** 2 + (robot_y - proj_y) ** 2

            candidate = float(i) + t
            if candidate >= last_progress and dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_progress = candidate

        return best_progress

    def _advance_along_path(self, from_progress: float,
                            distance_meters: float) -> float:
        n = len(self._path)
        if n < 2:
            return from_progress

        current_arc = self._cumul_dist_at(from_progress)
        target_arc = current_arc + distance_meters

        if target_arc >= float(self._cumul_dist[-1]):
            return float(n - 1)
        if target_arc <= 0.0:
            return 0.0

        lo, hi = 0, n - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if self._cumul_dist[mid] <= target_arc:
                lo = mid
            else:
                hi = mid

        seg_start = float(self._cumul_dist[lo])
        seg_end = float(self._cumul_dist[lo + 1])
        seg_len = seg_end - seg_start

        t = 0.0
        if seg_len > EPSILON:
            t = _clamp((target_arc - seg_start) / seg_len, 0.0, 1.0)

        return float(lo) + t

    def _interpolate_path(self, progress: float) -> tuple[float, float]:
        n = len(self._path)
        if n == 0:
            return 0.0, 0.0
        if progress <= 0.0:
            return float(self._path[0, 0]), float(self._path[0, 1])
        if progress >= float(n - 1):
            return float(self._path[-1, 0]), float(self._path[-1, 1])

        idx = int(progress)
        t = progress - float(idx)
        out_x = (float(self._path[idx, 0]) +
                 t * (float(self._path[idx + 1, 0]) - float(self._path[idx, 0])))
        out_y = (float(self._path[idx, 1]) +
                 t * (float(self._path[idx + 1, 1]) - float(self._path[idx, 1])))
        return out_x, out_y

    def _cumul_dist_at(self, progress: float) -> float:
        n = len(self._path)
        if n < 2:
            return 0.0
        if progress <= 0.0:
            return float(self._cumul_dist[0])
        if progress >= float(n - 1):
            return float(self._cumul_dist[-1])

        idx = int(progress)
        t = progress - float(idx)
        return (float(self._cumul_dist[idx]) +
                t * (float(self._cumul_dist[idx + 1]) - float(self._cumul_dist[idx])))

    def _estimate_curvature_ahead(self, at_progress: float,
                                  lookahead_dist: float) -> float:
        n = len(self._path)
        if n < 3:
            return 0.0

        start_idx = int(at_progress)
        if start_idx >= n - 1:
            start_idx = n - 2

        start_arc = float(self._cumul_dist[start_idx])
        end_arc = start_arc + lookahead_dist

        end_idx = start_idx
        while end_idx < n - 1 and float(self._cumul_dist[end_idx]) < end_arc:
            end_idx += 1

        # Stride: ~50mm chord for robust curvature estimation
        avg_spacing = (self._path_total_length / float(n - 1)) if n > 1 else 0.015
        stride = int(0.05 / max(avg_spacing, 0.001))
        stride = max(1, min(stride, 15))

        if end_idx < start_idx + 2 * stride:
            if start_idx + 2 * stride < n:
                end_idx = start_idx + 2 * stride
            else:
                return 0.0

        max_kappa = 0.0
        i = start_idx
        while i + 2 * stride <= end_idx and i + 2 * stride < n:
            ax = float(self._path[i, 0])
            ay = float(self._path[i, 1])
            bx = float(self._path[i + stride, 0])
            by = float(self._path[i + stride, 1])
            cx = float(self._path[i + 2 * stride, 0])
            cy = float(self._path[i + 2 * stride, 1])

            abx, aby = bx - ax, by - ay
            acx, acy = cx - ax, cy - ay

            cross_mag = abs(abx * acy - aby * acx)
            ab_len = math.hypot(abx, aby)
            bc_len = math.hypot(cx - bx, cy - by)
            ac_len = math.hypot(acx, acy)

            denom = ab_len * bc_len * ac_len
            if denom > 1e-10:
                kappa = 2.0 * cross_mag / denom
                if kappa > max_kappa:
                    max_kappa = kappa
            i += 1

        return max_kappa
