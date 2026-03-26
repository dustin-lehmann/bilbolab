"""
Simulated STM32 firmware.

Runs the complete firmware control hierarchy in a 100 Hz thread:
  1. Read commands (from register handler)
  2. Run control (balancing / velocity / position)
  3. Step dynamics
  4. Generate sample (BILBO_LL_Sample)
  5. Fire sample callback

This is the central class that ties dynamics, control, and position control together.
"""
from __future__ import annotations

import copy
import dataclasses
import math
import threading
import time
from typing import Callable

from robot.lowlevel.stm32_control import (
    bilbo_control_mode_t,
    bilbo_ll_control_data,
    bilbo_position_control_data,
    bilbo_position_control_output,
    bilbo_velocity_control_command,
    bilbo_velocity_control_output,
    bilbo_control_input_ext,
    bilbo_balancing_control_output,
    bilbo_control_output,
    position_control_event_t,
    position_control_event_data,
    control_event_t,
)
from robot.lowlevel.stm32_sample import (
    BILBO_LL_Sample,
    BILBO_LL_Sample_General,
    BILBO_LL_Sample_Errors,
    BILBO_LL_Sample_Estimation,
    BILBO_LL_Estimation_Data,
    BILBO_LL_Sensor_Data,
    BILBO_LL_Acc_Data,
    BILBO_LL_GYR_Data,
    BILBO_LL_Sample_Drive,
    BILBO_LL_Sample_Sequence,
    BILBO_LL_Sample_Debug,
)
from simulation.dynamics import BilboDynamics3D, BilboModel, load_model
from simulation.control import (
    BalancingController,
    VelocityController,
    VelocityControlOutput,
    TICController, TICConfig,
    VICController, VICConfig,
    PSIController, PSIConfig,
    PIDConfig, FeedforwardConfig,
)
from simulation.position_control import (
    SimulatedPositionControl,
    PositionControlConfig,
    PositionControlMode,
    PositionControlEvent,  # Used for velocity reset on command finish
    PathState,
)


class SimulatedFirmware:
    """Simulated STM32 firmware running at 100 Hz."""

    def __init__(self, model_yaml_path: str | None = None):
        # Load model
        model, self.Ts, self._battery_voltage = load_model(model_yaml_path)

        # Dynamics
        self.dynamics = BilboDynamics3D(model, Ts=self.Ts)

        # Control
        self.balancing = BalancingController()
        self.velocity = VelocityController(Ts=self.Ts)
        self.tic = TICController(TICConfig(Ts=self.Ts))
        self.vic = VICController(VICConfig(Ts=self.Ts))
        self.psi_ctrl = PSIController(PSIConfig(Ts=self.Ts))
        self.position_control = SimulatedPositionControl(PositionControlConfig(Ts=self.Ts))

        # State
        self.tick: int = 0
        self.mode = bilbo_control_mode_t.OFF
        self.max_torque: float = 0.5

        # Commands (written by register handler, consumed by control loop)
        self._ext_input_left: float = 0.0
        self._ext_input_right: float = 0.0
        self._velocity_cmd_v: float = 0.0
        self._velocity_cmd_psidot: float = 0.0

        # Estimation state (can be overridden by external position updates)
        self._theta_offset: float = 0.0
        self._dead_reckoning_enabled: bool = True

        # Control output (stored for sample)
        self._last_vel_output = VelocityControlOutput()
        self._last_bal_left: float = 0.0
        self._last_bal_right: float = 0.0
        self._last_output_left: float = 0.0
        self._last_output_right: float = 0.0
        self._last_pos_v_cmd: float = 0.0
        self._last_pos_psidot_cmd: float = 0.0

        # Thread
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Callbacks
        self._sample_callback: Callable[[BILBO_LL_Sample], None] | None = None
        self._event_callback: Callable | None = None

    # ── Lifecycle ───────────────────────────────────────────────────────

    def start(self, sample_callback: Callable[[BILBO_LL_Sample], None],
              event_callback: Callable | None = None):
        self._sample_callback = sample_callback
        self._event_callback = event_callback
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='SimFirmware')
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    # ── Register interface (called from simulated serial) ───────────────

    def set_mode(self, mode: int):
        with self._lock:
            new_mode = bilbo_control_mode_t(mode)
            if new_mode == self.mode:
                return

            old_mode = self.mode

            # Transition logic (mirrors firmware bilbo_control.cpp set_mode)
            if new_mode == bilbo_control_mode_t.OFF:
                self.vic.set_enabled(False)
                self.tic.set_enabled(False)
                self.psi_ctrl.set_enabled(False)
                self._ext_input_left = 0.0
                self._ext_input_right = 0.0
                self._velocity_cmd_v = 0.0
                self._velocity_cmd_psidot = 0.0
            elif new_mode == bilbo_control_mode_t.DIRECT:
                self.vic.set_enabled(False)
                self.tic.set_enabled(False)
                self.psi_ctrl.set_enabled(False)
            elif new_mode == bilbo_control_mode_t.BALANCING:
                self.vic.reset()
                self.psi_ctrl.reset()
                self.vic.set_enabled(True)
                self.tic.set_enabled(False)
                self.psi_ctrl.set_enabled(False)
            elif new_mode == bilbo_control_mode_t.VELOCITY:
                # Cannot go from OFF directly to VELOCITY (firmware blocks this)
                if old_mode == bilbo_control_mode_t.OFF:
                    return
                self.velocity.reset()
                self.vic.set_enabled(False)
                self.tic.set_enabled(False)
                self.psi_ctrl.set_enabled(False)
            elif new_mode == bilbo_control_mode_t.POSITION:
                # Cannot go from OFF directly to POSITION (firmware blocks this)
                if old_mode == bilbo_control_mode_t.OFF:
                    return
                self.vic.set_enabled(False)
                self.tic.set_enabled(False)
                self.psi_ctrl.set_enabled(False)
                self.velocity.reset()
                self.position_control.reset()
                self.position_control.clear_path()

            # General reset on every mode change (firmware: this->reset())
            # Resets balancing, velocity, position controllers and external input
            self.velocity.reset()
            self.position_control.reset()
            self._ext_input_left = 0.0
            self._ext_input_right = 0.0

            self.mode = new_mode

        # Fire mode change event
        self._fire_control_event(control_event_t.CONTROL_MODE_CHANGED)

    def set_K(self, K: list[float]):
        with self._lock:
            self.balancing.set_K(K)

    def set_external_input(self, left: float, right: float):
        with self._lock:
            self._ext_input_left = left
            self._ext_input_right = right

    def set_velocity_command(self, v: float, psi_dot: float):
        with self._lock:
            self._velocity_cmd_v = v
            self._velocity_cmd_psidot = psi_dot

    def set_velocity_config_v_pid(self, config: PIDConfig):
        with self._lock:
            self.velocity.pid_v.set_config(config)

    def set_velocity_config_v_ff(self, config: FeedforwardConfig):
        with self._lock:
            self.velocity.ff_v.set_config(config)

    def set_velocity_config_psidot_pid(self, config: PIDConfig):
        with self._lock:
            self.velocity.pid_psidot.set_config(config)

    def set_velocity_config_psidot_ff(self, config: FeedforwardConfig):
        with self._lock:
            self.velocity.ff_psidot.set_config(config)

    def set_tic_config(self, config: TICConfig):
        with self._lock:
            self.tic.set_config(config)

    def set_vic_config(self, config: VICConfig):
        with self._lock:
            self.vic.set_config(config)

    def set_tic_enabled(self, enabled: bool):
        with self._lock:
            if not self.tic.config.enabled:
                return  # Config master switch off → can't enable
            self.tic.set_enabled(enabled)
        self._fire_control_event(control_event_t.TIC_CHANGED)

    def set_vic_enabled(self, enabled: bool):
        with self._lock:
            if not self.vic.config.enabled:
                return  # Config master switch off → can't enable
            self.vic.set_enabled(enabled)
        self._fire_control_event(control_event_t.VIC_CHANGED)

    def set_psi_config(self, config: PSIConfig):
        with self._lock:
            self.psi_ctrl.set_config(config)

    def set_psi_enabled(self, enabled: bool):
        with self._lock:
            if enabled == self.psi_ctrl.is_enabled():
                return  # No change (matches firmware)
            self.psi_ctrl.set_enabled(enabled)
        self._fire_control_event(control_event_t.PSI_CHANGED)

    def set_psi_setpoint(self, psi_ref: float):
        with self._lock:
            self.psi_ctrl.set_setpoint(psi_ref)

    def set_max_torque(self, torque: float):
        with self._lock:
            self.max_torque = torque

    def set_position_config(self, config: PositionControlConfig):
        with self._lock:
            self.position_control.set_config(config)

    def set_theta_offset(self, offset: float):
        with self._lock:
            self._theta_offset = offset

    def set_position_state(self, x: float, y: float, psi: float):
        with self._lock:
            self.dynamics.set_state(x=x, y=y, psi=psi)

    def set_position_update(self, x: float, y: float, psi: float):
        with self._lock:
            self.dynamics.set_state(x=x, y=y, psi=psi)

    def set_dead_reckoning_enabled(self, enabled: bool):
        with self._lock:
            self._dead_reckoning_enabled = enabled

    def firmware_reset(self) -> bool:
        with self._lock:
            self.tick = 0
            self.mode = bilbo_control_mode_t.OFF
            self.dynamics.reset()
            self.velocity.reset()
            self.tic.reset()
            self.vic.reset()
            self.psi_ctrl.reset()
            self.position_control.reset()
            self._ext_input_left = 0.0
            self._ext_input_right = 0.0
            self._velocity_cmd_v = 0.0
            self._velocity_cmd_psidot = 0.0
        return True

    # ── Position control commands ───────────────────────────────────────

    def pc_clear_path(self):
        with self._lock:
            self.position_control.clear_path()

    def pc_add_path_point(self, x: float, y: float):
        with self._lock:
            self.position_control.add_path_point(x, y)

    def pc_add_stop_index(self, index: int):
        with self._lock:
            self.position_control.add_stop_index(index)

    def pc_start_path(self, max_speed: float = 0.0, max_spacing: float = 0.0,
                      timeout: float = 0.0, allow_reverse: bool = False):
        with self._lock:
            self.position_control.start_path(max_speed, max_spacing, timeout, allow_reverse)

    def pc_pause_path(self):
        with self._lock:
            self.position_control.pause_path()

    def pc_resume_path(self):
        with self._lock:
            self.position_control.resume_path()

    def pc_abort_path(self):
        with self._lock:
            self.position_control.abort_path()

    def pc_turn_to_heading(self, heading: float, timeout: float = 0.0,
                           max_angular_speed: float = 0.0, cmd_id: int = 0):
        with self._lock:
            self.position_control.turn_to_heading(heading, timeout, max_angular_speed, cmd_id)

    def pc_move_to_point(self, x: float, y: float, timeout: float = 0.0,
                         max_speed: float = 0.0, cmd_id: int = 0):
        with self._lock:
            self.position_control.move_to_point(x, y, timeout, max_speed, cmd_id)

    def pc_reset(self):
        with self._lock:
            self.position_control.reset()

    # ── Main loop ───────────────────────────────────────────────────────

    def _run_loop(self):
        next_time = time.perf_counter()
        while self._running:
            next_time += self.Ts
            self._step()
            # Sleep until next tick
            sleep_time = next_time - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                # Overrun - reset timing
                next_time = time.perf_counter()

    def _step(self):
        with self._lock:
            state = self.dynamics.state

            tau_left = 0.0
            tau_right = 0.0

            if self.mode == bilbo_control_mode_t.OFF:
                tau_left = 0.0
                tau_right = 0.0

            elif self.mode == bilbo_control_mode_t.DIRECT:
                tau_left = self._ext_input_left
                tau_right = self._ext_input_right

            elif self.mode == bilbo_control_mode_t.BALANCING:
                # 1. LQR with external input
                bal_left, bal_right = self.balancing.update(
                    state.v, state.theta, state.theta_dot, state.psi_dot,
                    self._ext_input_left, self._ext_input_right)
                # 2. VIC
                vic_torque = self.vic.update(state.v, state.theta)
                # 3. TIC
                tic_torque = self.tic.update(state.theta)
                # 4. PSI (differential: +left, -right)
                psi_torque = self.psi_ctrl.update(state.psi)
                # 5. Combine (matches firmware bilbo_control.cpp:435-436)
                tau_left = bal_left + vic_torque + tic_torque + psi_torque
                tau_right = bal_right + vic_torque + tic_torque - psi_torque
                self._last_bal_left = bal_left
                self._last_bal_right = bal_right

            elif self.mode == bilbo_control_mode_t.VELOCITY:
                # Velocity control
                vel_out = self.velocity.update(
                    self._velocity_cmd_v, self._velocity_cmd_psidot,
                    state.v, state.psi_dot)
                self._last_vel_output = vel_out
                # TIC
                tic_torque = self.tic.update(state.theta)
                # LQR with velocity output as external input
                bal_left, bal_right = self.balancing.update(
                    state.v, state.theta, state.theta_dot, state.psi_dot,
                    vel_out.u_left, vel_out.u_right)
                tau_left = bal_left + tic_torque
                tau_right = bal_right + tic_torque
                self._last_bal_left = bal_left
                self._last_bal_right = bal_right

            elif self.mode == bilbo_control_mode_t.POSITION:
                # Position control
                pos_v_cmd, pos_psidot_cmd = self.position_control.update(
                    state.x, state.y, state.psi, state.v)
                self._last_pos_v_cmd = pos_v_cmd
                self._last_pos_psidot_cmd = pos_psidot_cmd
                # Velocity control
                vel_out = self.velocity.update(
                    pos_v_cmd, pos_psidot_cmd,
                    state.v, state.psi_dot)
                self._last_vel_output = vel_out
                # TIC
                tic_torque = self.tic.update(state.theta)
                # LQR
                bal_left, bal_right = self.balancing.update(
                    state.v, state.theta, state.theta_dot, state.psi_dot,
                    vel_out.u_left, vel_out.u_right)
                tau_left = bal_left + tic_torque
                tau_right = bal_right + tic_torque
                self._last_bal_left = bal_left
                self._last_bal_right = bal_right

            # Clamp torque
            tau_left = max(-self.max_torque, min(self.max_torque, tau_left))
            tau_right = max(-self.max_torque, min(self.max_torque, tau_right))
            self._last_output_left = tau_left
            self._last_output_right = tau_right

            # Step dynamics (skip when lying on ground in OFF mode)
            if not (self.mode == bilbo_control_mode_t.OFF and self.dynamics._ground_contact):
                self.dynamics.step(tau_left, tau_right)
            new_state = self.dynamics.state

            # Get wheel speeds
            speed_left, speed_right = self.dynamics.get_wheel_speeds(tau_left, tau_right)

            # Build sample
            sample = self._build_sample(new_state, speed_left, speed_right)

            # Collect position control events
            pc_events = list(self.position_control.pending_events)
            self.position_control.pending_events.clear()

            # Reset velocity control on path finish/timeout/stop
            # (mirrors firmware _on_position_command_finished callback —
            #  only registered for path events, NOT move_to_point or turn_to_heading)
            _vel_reset_events = {
                PositionControlEvent.PATH_FINISHED,
                PositionControlEvent.PATH_TIMEOUT,
                PositionControlEvent.PATH_ABORTED,
            }
            for evt, _ in pc_events:
                if evt in _vel_reset_events:
                    self.velocity.reset()
                    break

            self.tick += 1

        # Outside lock: fire callbacks
        if self._sample_callback:
            self._sample_callback(sample)

        for evt, extra in pc_events:
            self._fire_position_control_event(evt, extra)

    def _build_sample(self, state, speed_left: float, speed_right: float) -> BILBO_LL_Sample:
        """Build a BILBO_LL_Sample from current simulator state."""
        theta = state.theta + self._theta_offset

        # Simple IMU simulation: derive from dynamics state
        g = 9.81
        acc_x = 0.0  # Forward acceleration (simplified)
        acc_y = g * math.sin(theta)  # Gravity component in pitch
        acc_z = g * math.cos(theta)
        gyr_x = state.theta_dot  # Pitch rate
        gyr_y = 0.0  # Roll rate (near zero for 2-wheel)
        gyr_z = state.psi_dot  # Yaw rate

        # Position control data
        pc_data = self.position_control.get_data()

        return BILBO_LL_Sample(
            tick=self.tick,
            general=BILBO_LL_Sample_General(status=1),
            errors=BILBO_LL_Sample_Errors(),
            control=bilbo_ll_control_data(
                mode=int(self.mode),
                status=1,
                vic_enabled=int(self.vic.is_active()),
                tic_enabled=int(self.tic.is_enabled()),
                psi_enabled=int(self.psi_ctrl.is_active()),
                position_control_data=bilbo_position_control_data(
                    mode=pc_data.mode,
                    path_state=pc_data.path_state,
                    buffer_capacity=pc_data.buffer_capacity,
                    buffer_used=pc_data.buffer_used,
                    path_point_count=pc_data.path_point_count,
                    current_index=pc_data.current_index,
                    carrot_x=pc_data.carrot_x,
                    carrot_y=pc_data.carrot_y,
                    carrot_distance=pc_data.carrot_distance,
                    heading_error=pc_data.heading_error,
                    speed_limit=pc_data.speed_limit,
                    output=bilbo_position_control_output(
                        v_cmd=self._last_pos_v_cmd,
                        psi_dot_cmd=self._last_pos_psidot_cmd,
                    ),
                    elapsed_time=pc_data.elapsed_time,
                    remaining_path_length=pc_data.remaining_path_length,
                    progress=pc_data.progress,
                ),
                velocity_command=bilbo_velocity_control_command(
                    v=self._last_vel_output.v_cmd,
                    psi_dot=self._last_vel_output.psi_dot_cmd,
                ),
                velocity_output=bilbo_velocity_control_output(
                    u_l=self._last_vel_output.u_left,
                    u_r=self._last_vel_output.u_right,
                ),
                input_ext=bilbo_control_input_ext(
                    u_left=self._ext_input_left,
                    u_right=self._ext_input_right,
                ),
                balancing_output=bilbo_balancing_control_output(
                    u_1=self._last_bal_left,
                    u_2=self._last_bal_right,
                ),
                output=bilbo_control_output(
                    u_left=self._last_output_left,
                    u_right=self._last_output_right,
                ),
            ),
            estimation=BILBO_LL_Sample_Estimation(
                state=BILBO_LL_Estimation_Data(
                    x=state.x,
                    y=state.y,
                    v=state.v,
                    theta=theta,
                    theta_dot=state.theta_dot,
                    psi=state.psi,
                    psi_dot=state.psi_dot,
                ),
                is_dead_reckoning=self._dead_reckoning_enabled,
            ),
            sensors=BILBO_LL_Sensor_Data(
                speed_left=speed_left,
                speed_right=speed_right,
                acc=BILBO_LL_Acc_Data(x=acc_x, y=acc_y, z=acc_z),
                gyr=BILBO_LL_GYR_Data(x=gyr_x, y=gyr_y, z=gyr_z),
                battery_voltage=self._battery_voltage,
            ),
            drive=BILBO_LL_Sample_Drive(
                status=1,
                motor_mode_left=40,  # SM_MODE_TORQUE
                motor_mode_right=40,  # SM_MODE_TORQUE
            ),
            sequence=BILBO_LL_Sample_Sequence(),
            debug=BILBO_LL_Sample_Debug(),
        )

    # ── Event helpers ───────────────────────────────────────────────────

    def _fire_control_event(self, event: control_event_t):
        if self._event_callback:
            self._event_callback('control', {
                'event': int(event),
                'mode': int(self.mode),
                'data': {
                    'vic_enabled': int(self.vic.is_active()),
                    'tic_enabled': int(self.tic.is_enabled()),
                    'psi_enabled': int(self.psi_ctrl.is_active()),
                },
                'tick': self.tick,
            })

    def _fire_position_control_event(self, event: PositionControlEvent, extra: dict):
        if self._event_callback:
            pc_data = self.position_control.get_data()
            self._event_callback('position_control', {
                'event': int(event),
                'tick': self.tick,
                'waypoint_index': extra.get('waypoint_index', 0),
                'command_id': extra.get('command_id', 0),
                'data': dataclasses.asdict(pc_data),
            })
