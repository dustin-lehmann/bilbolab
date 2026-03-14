"""
Simulated firmware control algorithms.

1:1 replica of the STM32 firmware control hierarchy:
  - PID controller (with anti-windup, D-filter, rate limiting, setpoint slew)
  - Feedforward controller (Kv, Ka, Kc with Stribeck stiction model)
  - LQR balancing (8-gain state feedback)
  - Velocity control (PID + FF for forward v and yaw rate psi_dot)
  - TIC / VIC integral augmentation with dual-enable pattern
  - PSI heading hold with auto-capture setpoint
"""
from __future__ import annotations

import dataclasses
import math


# =============================================================================
# PID Controller  (mirrors firmware pid.h / pid.cpp)
# =============================================================================
@dataclasses.dataclass
class PIDConfig:
    Kp: float = 0.0
    Ki: float = 0.0
    Kd: float = 0.0
    Ts: float = 0.01
    enable_i_limit: bool = False
    i_term_limit: float = 0.0
    enable_input_limit: bool = False
    input_limit: float = 0.0
    enable_output_limit: bool = False
    output_limit: float = 0.0
    enable_d_filter: bool = False
    Td_filter: float = 0.0
    enable_rate_limit: bool = False
    rate_limit: float = 0.0
    enable_setpoint_rate_limit: bool = False
    setpoint_rate_limit: float = 0.0


class PIDController:
    def __init__(self, config: PIDConfig | None = None):
        self.config = config or PIDConfig()
        self.reset()

    def reset(self):
        self._i_term = 0.0
        self._error_last = 0.0
        self._d_error_filt = 0.0
        self._last_output = 0.0
        self._setpoint_limited = 0.0

    def update(self, setpoint: float, measurement: float) -> float:
        c = self.config
        Ts = c.Ts
        if Ts <= 0.0:
            return self._last_output

        # Setpoint rate limiting
        if c.enable_setpoint_rate_limit and c.setpoint_rate_limit > 0:
            delta = setpoint - self._setpoint_limited
            max_delta = abs(c.setpoint_rate_limit) * Ts
            delta = max(-max_delta, min(max_delta, delta))
            self._setpoint_limited += delta
        else:
            self._setpoint_limited = setpoint

        # Error
        error = self._setpoint_limited - measurement

        # Input saturation
        if c.enable_input_limit and c.input_limit > 0:
            error = max(-c.input_limit, min(c.input_limit, error))

        # P term
        p_term = c.Kp * error

        # D term with optional filter
        d_error_raw = (error - self._error_last) / Ts
        if c.enable_d_filter and c.Td_filter > 0:
            alpha = Ts / (Ts + c.Td_filter)
            self._d_error_filt += (d_error_raw - self._d_error_filt) * alpha
        else:
            self._d_error_filt = d_error_raw
        d_term = c.Kd * self._d_error_filt

        # Predict output BEFORE updating integrator (for anti-windup)
        u_pred = p_term + self._i_term + d_term

        # Anti-windup: only integrate when output is NOT saturated
        saturated = False
        if c.enable_output_limit and abs(c.output_limit) > 0.0:
            lim = abs(c.output_limit)
            saturated = (u_pred > lim) or (u_pred < -lim)

        if not saturated and c.Ki != 0.0:
            self._i_term += c.Ki * error * Ts
            if c.enable_i_limit:
                ilim = abs(c.i_term_limit)
                if ilim > 0:
                    self._i_term = max(-ilim, min(ilim, self._i_term))
                else:
                    self._i_term = 0.0
            # Recompute with updated I
            u_pred = p_term + self._i_term + d_term

        # Output saturation
        output = u_pred
        if c.enable_output_limit and abs(c.output_limit) > 0:
            lim = abs(c.output_limit)
            output = max(-lim, min(lim, output))

        # Output rate limiting
        if c.enable_rate_limit and abs(c.rate_limit) > 0:
            max_delta = abs(c.rate_limit) * Ts
            delta = output - self._last_output
            delta = max(-max_delta, min(max_delta, delta))
            output = self._last_output + delta

        self._error_last = error
        self._last_output = output
        return output

    def set_config(self, config: PIDConfig):
        self.reset()
        self.config = config


# =============================================================================
# Feedforward Controller  (mirrors firmware feedforward.h / feedforward.cpp)
# =============================================================================
@dataclasses.dataclass
class FeedforwardConfig:
    Kv: float = 0.0
    Ka: float = 0.0
    Kc: float = 0.0
    Ts: float = 0.01
    enable_vref_slew: bool = False
    vref_slew_rate: float = 0.0
    enable_a_filter: bool = False
    Ta_filter: float = 0.0
    enable_stiction: bool = False
    v0_stiction: float = 0.0
    v_decay_stiction: float = 0.0
    enable_output_limit: bool = False
    output_limit: float = 0.0
    enable_output_slew: bool = False
    output_slew_rate: float = 0.0


class FeedforwardController:
    def __init__(self, config: FeedforwardConfig | None = None):
        self.config = config or FeedforwardConfig()
        self.reset()

    def reset(self):
        self._vref_limited = 0.0
        self._vref_last = 0.0
        self._dvref_dt = 0.0
        self._last_output = 0.0

    def _apply_vref_slew(self, v_ref: float) -> float:
        c = self.config
        if not c.enable_vref_slew:
            self._vref_limited = v_ref
            return self._vref_limited
        Ts = c.Ts
        if Ts <= 0.0:
            self._vref_limited = v_ref
            return self._vref_limited
        rate = abs(c.vref_slew_rate)
        if rate <= 0.0:
            return self._vref_limited
        max_delta = rate * Ts
        delta = v_ref - self._vref_limited
        delta = max(-max_delta, min(max_delta, delta))
        self._vref_limited += delta
        return self._vref_limited

    def _compute_accel(self, vref_now: float) -> float:
        c = self.config
        Ts = c.Ts
        if Ts <= 0.0:
            return 0.0
        a_raw = (vref_now - self._vref_last) / Ts
        if not c.enable_a_filter:
            self._dvref_dt = a_raw
            return self._dvref_dt
        T = c.Ta_filter
        if T <= 0.0:
            self._dvref_dt = a_raw
            return self._dvref_dt
        alpha = Ts / (T + Ts)
        self._dvref_dt += (a_raw - self._dvref_dt) * alpha
        return self._dvref_dt

    def _stiction_term(self, vref_now: float) -> float:
        c = self.config
        if not c.enable_stiction or c.Kc == 0.0:
            return 0.0
        v0 = c.v0_stiction
        if v0 <= 0.0:
            if vref_now > 0.0:
                s = 1.0
            elif vref_now < 0.0:
                s = -1.0
            else:
                return 0.0
        else:
            s = math.tanh(vref_now / v0)
        # Stribeck decay: stiction DECREASES with speed (matches firmware)
        decay = 1.0
        if c.v_decay_stiction > 0.0:
            decay = math.exp(-abs(vref_now) / c.v_decay_stiction)
        return c.Kc * s * decay

    def _apply_output_limit(self, tau: float) -> float:
        c = self.config
        if not c.enable_output_limit:
            return tau
        lim = abs(c.output_limit)
        if lim <= 0.0:
            return 0.0
        return max(-lim, min(lim, tau))

    def _apply_output_slew(self, tau: float) -> float:
        c = self.config
        if not c.enable_output_slew:
            return tau
        Ts = c.Ts
        if Ts <= 0.0:
            return tau
        rate = abs(c.output_slew_rate)
        if rate <= 0.0:
            return self._last_output
        max_delta = rate * Ts
        delta = tau - self._last_output
        delta = max(-max_delta, min(max_delta, delta))
        return self._last_output + delta

    def update(self, v_ref: float) -> float:
        c = self.config
        Ts = c.Ts
        if Ts <= 0.0:
            return self._last_output

        # 1) Slew-limit reference
        v_limited = self._apply_vref_slew(v_ref)

        # 2) Acceleration estimate
        a_ref = self._compute_accel(v_limited)

        # 3) FF components
        tau_v = c.Kv * v_limited
        tau_a = c.Ka * a_ref
        tau_c = self._stiction_term(v_limited)

        tau = tau_v + tau_a + tau_c

        # 4) Output limit, slew, then re-apply limit (matches firmware)
        tau = self._apply_output_limit(tau)
        tau = self._apply_output_slew(tau)
        tau = self._apply_output_limit(tau)

        # 5) Update state
        self._vref_last = v_limited
        self._last_output = tau

        return tau

    def set_config(self, config: FeedforwardConfig):
        self.config = config
        self.reset()


# =============================================================================
# TIC - Theta Integral Control (matches firmware bilbo_vic_tic.h)
# =============================================================================
@dataclasses.dataclass
class TICConfig:
    enabled: bool = False
    Ts: float = 0.01
    ki: float = 0.0
    max_torque: float = 0.0
    theta_limit: float = 0.0


class TICController:
    def __init__(self, config: TICConfig | None = None):
        self.config = config or TICConfig()
        self._integral = 0.0
        self._enabled = False  # Runtime enable (separate from config.enabled)
        self.active = False

    def reset(self):
        self._integral = 0.0

    def set_enabled(self, state: bool):
        """Runtime enable/disable (firmware pattern: config.enabled gates this)."""
        if not self.config.enabled:
            self._enabled = False
            self.reset()
            return
        if self._enabled != state:
            self.reset()
        self._enabled = state

    def set_config(self, config: TICConfig):
        self.config = config
        if not self.config.enabled:
            self._enabled = False
        self.reset()

    def is_enabled(self) -> bool:
        return self._enabled

    def update(self, theta: float) -> float:
        if not self.config.enabled or not self._enabled:
            self.active = False
            return 0.0

        # Safety: permanently disable if pitch exceeds limit
        if self.config.theta_limit != 0.0:
            if abs(theta) > self.config.theta_limit:
                self.reset()
                self._enabled = False
                self.active = False
                return 0.0

        self.active = True
        self._integral += self.config.ki * theta * self.config.Ts

        if self.config.max_torque > 0.0:
            self._integral = max(-self.config.max_torque,
                                 min(self.config.max_torque, self._integral))

        return self._integral


# =============================================================================
# VIC - Velocity Integral Control (matches firmware bilbo_vic_tic.h)
# =============================================================================
@dataclasses.dataclass
class VICConfig:
    enabled: bool = False
    Ts: float = 0.01
    ki: float = 0.0
    max_torque: float = 0.0
    v_limit: float = 0.0
    theta_limit: float = 0.0


class VICController:
    def __init__(self, config: VICConfig | None = None):
        self.config = config or VICConfig()
        self._integral = 0.0
        self._enabled = False  # Runtime enable
        self.active = False

    def reset(self):
        self._integral = 0.0

    def set_enabled(self, state: bool):
        """Runtime enable/disable (firmware pattern: config.enabled gates this)."""
        if not self.config.enabled:
            self._enabled = False
            self.reset()
            return
        if self._enabled != state:
            self.reset()
        self._enabled = state

    def set_config(self, config: VICConfig):
        self.config = config
        if not self.config.enabled:
            self._enabled = False
        self.reset()

    def is_enabled(self) -> bool:
        return self._enabled

    def is_active(self) -> bool:
        return self.active and self._enabled

    def update(self, velocity: float, theta: float) -> float:
        self.active = False
        if not self.config.enabled or not self._enabled:
            return 0.0

        if self.config.v_limit != 0.0:
            if abs(velocity) > self.config.v_limit:
                self.reset()
                return 0.0

        if self.config.theta_limit != 0.0:
            if abs(theta) > self.config.theta_limit:
                self.reset()
                return 0.0

        self._integral += self.config.ki * velocity * self.config.Ts

        if self.config.max_torque > 0.0:
            self._integral = max(-self.config.max_torque,
                                 min(self.config.max_torque, self._integral))

        self.active = True
        return self._integral


# =============================================================================
# PSI Controller (heading hold via PI on psi, matches firmware bilbo_vic_tic.h)
# =============================================================================
@dataclasses.dataclass
class PSIConfig:
    enabled: bool = False
    Ts: float = 0.01
    kp: float = 0.0
    ki: float = 0.0
    max_torque: float = 0.0


class PSIController:
    """PI controller on heading angle psi. Outputs a differential torque:
    add to u_left, subtract from u_right."""

    def __init__(self, config: PSIConfig | None = None):
        self.config = config or PSIConfig()
        self._integral = 0.0
        self._setpoint = 0.0
        self._setpoint_captured = False
        self._enabled = False
        self.active = False

    def reset(self):
        self._integral = 0.0
        self._setpoint = 0.0
        self._setpoint_captured = False

    def set_enabled(self, state: bool):
        if self._enabled != state:
            self.reset()
        self._enabled = state

    def set_config(self, config: PSIConfig):
        self.config = config
        self.reset()

    def set_setpoint(self, psi_ref: float):
        self._setpoint = psi_ref
        self._setpoint_captured = True

    def is_enabled(self) -> bool:
        return self._enabled

    def is_active(self) -> bool:
        return self.active and self._enabled

    def update(self, psi: float) -> float:
        self.active = False
        if not self._enabled:
            return 0.0

        # Auto-capture setpoint on first update after enable/reset
        if not self._setpoint_captured:
            self._setpoint = psi
            self._setpoint_captured = True

        # Angle wrapping
        error = self._setpoint - psi
        while error > math.pi:
            error -= 2 * math.pi
        while error < -math.pi:
            error += 2 * math.pi

        # PI control
        p_term = self.config.kp * error
        self._integral += self.config.ki * error * self.config.Ts

        # Clamp integral only (firmware does NOT clamp total output)
        if self.config.max_torque > 0.0:
            self._integral = max(-self.config.max_torque,
                                 min(self.config.max_torque, self._integral))

        self.active = True
        return p_term + self._integral


# =============================================================================
# Balancing Control (LQR state feedback)
# =============================================================================
class BalancingController:
    """LQR balancing: u = K * [v, theta, theta_dot, psi_dot] + external_input.

    K is 8 elements: K[0:4] for left motor, K[4:8] for right motor.
    State order: [v, theta, theta_dot, psi_dot].
    """

    def __init__(self):
        self.K = [0.0] * 8

    def set_K(self, K: list[float]):
        assert len(K) == 8
        self.K = list(K)

    def update(self, v: float, theta: float, theta_dot: float, psi_dot: float,
               ext_left: float = 0.0, ext_right: float = 0.0) -> tuple[float, float]:
        state = [v, theta, theta_dot, psi_dot]
        u_left = sum(self.K[i] * state[i] for i in range(4)) + ext_left
        u_right = sum(self.K[i + 4] * state[i] for i in range(4)) + ext_right
        return u_left, u_right


# =============================================================================
# Velocity Control (PID + FF for v and psi_dot)
# =============================================================================
@dataclasses.dataclass
class VelocityControlOutput:
    u_left: float = 0.0
    u_right: float = 0.0
    v_meas: float = 0.0
    psi_dot_meas: float = 0.0
    v_cmd: float = 0.0
    psi_dot_cmd: float = 0.0


class VelocityController:
    """Two-channel velocity controller: forward v and yaw rate psi_dot.

    Each channel has PID + feedforward. Outputs are mixed to left/right torques.
    """

    def __init__(self, Ts: float = 0.01):
        self.Ts = Ts
        self.pid_v = PIDController(PIDConfig(Ts=Ts))
        self.ff_v = FeedforwardController(FeedforwardConfig(Ts=Ts))
        self.pid_psidot = PIDController(PIDConfig(Ts=Ts))
        self.ff_psidot = FeedforwardController(FeedforwardConfig(Ts=Ts))

    def reset(self):
        self.pid_v.reset()
        self.ff_v.reset()
        self.pid_psidot.reset()
        self.ff_psidot.reset()

    def update(self, v_cmd: float, psi_dot_cmd: float,
               v_meas: float, psi_dot_meas: float) -> VelocityControlOutput:
        # Feedforward terms
        u_forward_ff = self.ff_v.update(v_cmd)
        u_turn_ff = self.ff_psidot.update(psi_dot_cmd)

        # Feedback terms (PID)
        u_forward_pid = self.pid_v.update(v_cmd, v_meas)
        u_turn_pid = self.pid_psidot.update(psi_dot_cmd, psi_dot_meas)

        # Sum FF + PID
        u_forward = u_forward_ff + u_forward_pid
        u_turn = u_turn_ff + u_turn_pid

        # Mix to left/right (left = forward - turn, right = forward + turn)
        u_left = u_forward - u_turn
        u_right = u_forward + u_turn

        return VelocityControlOutput(
            u_left=u_left,
            u_right=u_right,
            v_meas=v_meas,
            psi_dot_meas=psi_dot_meas,
            v_cmd=v_cmd,
            psi_dot_cmd=psi_dot_cmd,
        )
