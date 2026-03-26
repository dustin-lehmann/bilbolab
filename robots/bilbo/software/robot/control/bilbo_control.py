import ctypes
import dataclasses
import threading
import time

import numpy as np

from core.communication.wifi.bilbolab_wifi_interface import (
    wifi_event_definition, WifiEventContainer, WifiEvent,
)
from core.communication.wifi.data_link import CommandArgument
from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, EventFlag, Event, pred_flag_equals, TIMEOUT, wait_for_events, OR
from core.utils.logging_utils import Logger
from core.utils.time import setTimeout
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.communication.serial.bilbo_serial_messages import BILBO_Control_Event_Message
from robot.control.bilbo_control_config import load_config_by_name
from robot.control.bilbo_control_definitions import BILBO_Control_Mode, BILBO_ControlConfig, PID_Config, \
    BILBO_Control_Status, \
    BILBO_Control_Event_Type, BILBO_Control_Inputs, VelocityControl_Config, PositionControl_Config, TIC_Config, \
    VIC_Config, PSI_Config, BILBO_Control_Sample, Feedforward_Config
from robot.control.bilbo_position_control import BILBO_PositionControl
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.lowlevel.stm32_addresses import BILBO_AddressTables, BILBO_ControlAddresses
from robot.lowlevel.stm32_control import bilbo_velocity_control_command_t, bilbo_control_input_ext_t, \
    bilbo_control_config_t, bilbo_tic_config_t, bilbo_vic_config_t, bilbo_psi_config_t, \
    bilbo_velocity_control_config_t, pid_control_config_t, feedforward_config_t
from robot.lowlevel.stm32_general import LOOP_TIME_CONTROL
from robot.lowlevel.stm32_sample import BILBO_LL_Sample

CONTROL_MODE_COLORS = {
    None: [5, 5, 5],
    BILBO_Control_Mode.DIRECT: [5, 5, 5],
    BILBO_Control_Mode.OFF: [5, 5, 5],
    BILBO_Control_Mode.BALANCING: [0, 5, 0],
    BILBO_Control_Mode.VELOCITY: [0, 5, 5],
    BILBO_Control_Mode.POSITION: [5, 0, 5]
}


# === BILBO Control Callbacks ==========================================================================================
@callback_definition
class BILBO_Control_Callbacks:
    mode_change: CallbackContainer
    status_change: CallbackContainer
    config_change: CallbackContainer
    error: CallbackContainer
    update: CallbackContainer


@event_definition
class BILBO_Control_Events:
    mode_change: Event = Event(flags=EventFlag('mode', BILBO_Control_Mode))
    config_change: Event
    error: Event
    status_change: Event = Event(flags=EventFlag('status', str))
    vic_change: Event
    tic_change: Event
    psi_change: Event
    lowlevel_mode_change: Event = Event(flags=EventFlag('mode', BILBO_Control_Mode))


_CONTROL_WIFI_EVENT = WifiEvent(data_type=dict)


@wifi_event_definition
class ControlWifiEvents(WifiEventContainer):
    mode_change: WifiEvent = _CONTROL_WIFI_EVENT
    vic_change: WifiEvent = _CONTROL_WIFI_EVENT
    tic_change: WifiEvent = _CONTROL_WIFI_EVENT
    psi_change: WifiEvent = _CONTROL_WIFI_EVENT
    configuration_change: WifiEvent = _CONTROL_WIFI_EVENT


# TODO: this needs to be initially set somehow
@dataclasses.dataclass
class BILBO_Control_Controller_Status:
    vic_enabled: bool = False
    tic_enabled: bool = False
    psi_enabled: bool = False


# === BILBO Control ====================================================================================================
class BILBO_Control:
    mode: BILBO_Control_Mode | None = None
    callbacks: BILBO_Control_Callbacks
    events: BILBO_Control_Events
    controller_status: BILBO_Control_Controller_Status
    inputs: BILBO_Control_Inputs

    status: BILBO_Control_Status = BILBO_Control_Status.NORMAL
    _config: BILBO_ControlConfig | None = None

    external_input_enabled: bool = True

    # Number of consecutive sample-batch mismatches before syncing mode from firmware.
    # The callback fires once per batch at ~10 Hz, so 3 batches ≈ 300 ms.
    _MODE_MISMATCH_THRESHOLD: int = 3

    # === INIT =========================================================================================================
    def __init__(self, common: BILBO_Common,
                 estimation: BILBO_Estimation,
                 comm: BILBO_Communication,
                 control_settings=None):

        self.callbacks = BILBO_Control_Callbacks()
        self.events = BILBO_Control_Events()
        self.logger = Logger("CONTROL", "DEBUG")

        # --- Settings ---
        self._auto_position_mode = control_settings.auto_position_mode if control_settings else False

        # --- Input Handling ---
        self.common = common
        self.estimation = estimation
        self.communication = comm

        # WiFi events
        self.wifi_events = ControlWifiEvents(wifi=comm.wifi.wifi, id='control')

        self.position_control = BILBO_PositionControl(common=self.common,
                                                      estimation=self.estimation,
                                                      communication=self.communication)

        # --- Register communication callbacks ---
        self.communication.serial.callbacks.event.register(self._lowlevel_control_event_callback,
                                                           parameters={'messages': [BILBO_Control_Event_Message]})

        self.communication.callbacks.rx_stm32_sample.register(self._lowlevel_sample_callback)

        self._register_wifi_commands()

        # --- Variables ---
        self.controller_status = BILBO_Control_Controller_Status()
        self.inputs = BILBO_Control_Inputs()
        self.inputs.reset()
        self._mode_transition_pending = False
        self._mode_mismatch_count = 0

    # === METHODS ======================================================================================================
    def init(self) -> bool:
        config = self.load_config("default")
        if config is None:
            self.logger.error("Failed to load default control config. Control will not work!")
            return False
        result = self.set_config(config)
        if not result:
            self.logger.error("Failed to set default control config. Control will not work!")
            return False
        # Reset position control to clear any stale firmware state from a previous run
        self.position_control.reset()
        self.controller_status.vic_enabled = False
        self.controller_status.tic_enabled = False
        self.controller_status.psi_enabled = False
        self.logger.info("Control initialized successfully")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info("Starting control")
        self.set_mode(BILBO_Control_Mode.OFF, wait_for_change=False)
        self.status = BILBO_Control_Status.NORMAL

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.logger.info("Closing control")
        self.set_mode(BILBO_Control_Mode.OFF)

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        if self.status != BILBO_Control_Status.NORMAL:
            return

        match self.mode:
            case BILBO_Control_Mode.OFF:
                # Send [0,0], just in case
                self._set_lowlevel_external_input(0, 0)

            case BILBO_Control_Mode.BALANCING:
                if self.external_input_enabled:
                    self._set_lowlevel_external_input(self.inputs.external.left, self.inputs.external.right)

            case BILBO_Control_Mode.VELOCITY:
                self._set_lowlevel_velocity_command(self.inputs.velocity.forward, self.inputs.velocity.turn)

            case BILBO_Control_Mode.POSITION:
                ...
                # Do nothing for now

            case _:
                self.logger.warning(f"Mode \"{self.mode}\" is not supported")

        self.callbacks.update.call()

    # ------------------------------------------------------------------------------------------------------------------
    def enable_external_input(self):
        self.external_input_enabled = True

    # ------------------------------------------------------------------------------------------------------------------
    def disable_external_input(self):
        self.external_input_enabled = False

    # ------------------------------------------------------------------------------------------------------------------
    def set_mode(self, mode: BILBO_Control_Mode | int, *, wait_for_change: bool = True) -> bool:

        self.logger.debug(f"Setting control mode to {mode} at tick {self.common.tick}")
        if isinstance(mode, int):
            mode_int = mode
            try:
                mode = BILBO_Control_Mode(mode_int)
            except ValueError:
                self.logger.warning(f"Failed to convert mode {mode_int} to BILBO_Control_Mode")
                return False

        if mode == self.mode:
            return True

        self._mode_transition_pending = True
        try:
            return self._set_mode_internal(mode, wait_for_change=wait_for_change)
        finally:
            self._mode_transition_pending = False
            self._mode_mismatch_count = 0

    # ------------------------------------------------------------------------------------------------------------------
    def _set_mode_internal(self, mode: BILBO_Control_Mode, *, wait_for_change: bool = True) -> bool:
        self.logger.info(f"Setting control mode to \"{mode.name}\"")
        previous_mode = self.mode
        result = None
        match mode:
            case BILBO_Control_Mode.OFF:
                self.mode = BILBO_Control_Mode.OFF
                result = self._set_lowlevel_control_mode(BILBO_Control_Mode.OFF)
            case BILBO_Control_Mode.DIRECT:
                self.logger.warning("Direct mode is not supported yet")
                return False
                # result = self._set_lowlevel_control_mode(BILBO_Control_Mode.DIRECT)
            case BILBO_Control_Mode.BALANCING:
                self.mode = BILBO_Control_Mode.BALANCING
                result = self._set_lowlevel_control_mode(BILBO_Control_Mode.BALANCING)
            case BILBO_Control_Mode.VELOCITY:

                if self.mode == BILBO_Control_Mode.OFF:
                    self.logger.warning("Cannot set velocity mode while in OFF mode. Go to BALANCING first")
                    return False

                self.mode = BILBO_Control_Mode.VELOCITY
                result = self._set_lowlevel_control_mode(BILBO_Control_Mode.VELOCITY)
            case BILBO_Control_Mode.POSITION:

                dead_reckoning = self.estimation.get_dead_reckoning_enabled()
                tracker_position = (
                        self.estimation.get_tracker_updates_enabled()
                        and self.estimation.tracker_connected
                )

                if not (dead_reckoning or tracker_position):
                    self.logger.warning(
                        "Cannot set position mode: no position source available "
                        "(dead reckoning disabled and tracker unavailable)"
                    )
                    return False

                if self.mode == BILBO_Control_Mode.OFF:
                    self.logger.warning("Cannot set position mode while in OFF mode. Go to BALANCING or VELOCITY first")
                    return False
                self.mode = BILBO_Control_Mode.POSITION
                # Reset position control and clear any old paths/commands (firmware also does this)
                self.position_control.reset()
                result = self._set_lowlevel_control_mode(BILBO_Control_Mode.POSITION)
            case _:
                self.logger.warning(f"Mode \"{mode}\" is not supported")
                return False

        if result is None or not result:
            self.logger.warning("Failed to set control mode")
            self.mode = previous_mode
            self.status = BILBO_Control_Status.ERROR
            return False

        # Reset the external inputs
        self.inputs.reset()

        # Wait for the low-level mode change event
        if wait_for_change:
            result, _ = self.events.lowlevel_mode_change.wait(timeout=0.5,
                                                              stale_event_time=0.1,
                                                              predicate=pred_flag_equals('mode', mode))

            if result is TIMEOUT:
                self.logger.warning(f"Failed to set control mode to \"{mode.name}\". Low-level mode change event "
                                    f"timed out")
                self.mode = previous_mode
                return False

        self.common.board.setRGBLEDExtern(
            CONTROL_MODE_COLORS[mode]
        )
        self.callbacks.mode_change.call(mode, forced_change=False)
        self.events.mode_change.set(mode)
        self.common.events.control_mode_change.set(mode)
        self.wifi_events.mode_change.send(data={'mode': mode.value})
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def set_config(self, config: BILBO_ControlConfig):

        result = self._set_lowlevel_control_config(config)
        if result is None:
            self.logger.warning("Failed to set control config")
            return False
        self._config = config
        self.logger.info(f"Control config \"{config.name}\" set successfully")
        self.callbacks.config_change.call(config)
        self.events.config_change.set(config)
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def load_config(self, name: str):
        self.logger.debug(f"Loading config \"{name}\"")
        config = load_config_by_name(name)

        if config is None:
            self.logger.warning(f"Failed to load config \"{name}\"")
            return None

        return config

    # ------------------------------------------------------------------------------------------------------------------
    def save_current_config(self):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def load_and_set_default_config(self) -> BILBO_ControlConfig | None:
        """Load default config from file and apply it to the robot."""
        self.logger.info("Loading and setting default control config")
        config = self.load_config("default")
        if config is None:
            self.logger.error("Failed to load default config")
            return None
        result = self.set_config(config)
        if not result:
            self.logger.error("Failed to set default config")
            return None
        return self._config

    # ------------------------------------------------------------------------------------------------------------------
    def get_control_config(self) -> BILBO_ControlConfig | None:
        return self._config

    # ------------------------------------------------------------------------------------------------------------------
    def stand_up(self) -> None:
        if self.mode != BILBO_Control_Mode.OFF:
            self.logger.warning(f"Cannot stand up while in mode \"{self.mode}\"")
            return
        self.set_mode(BILBO_Control_Mode.BALANCING)

    # ------------------------------------------------------------------------------------------------------------------
    def fall_down(self, direction='forward') -> None:
        if self.mode == BILBO_Control_Mode.OFF:
            self.logger.warning("Cannot fall down while in OFF mode. Go to BALANCING first")
            return
        self.logger.info(f"Falling down in direction {direction}")
        self.set_mode(BILBO_Control_Mode.BALANCING)
        time.sleep(0.1)
        abs_input = 0.2
        input = -abs_input if direction == 'forward' else abs_input
        self.disable_external_input()
        self._set_lowlevel_external_input(left=input, right=input)

        def _fall_down_callback():
            self._set_lowlevel_external_input(left=0, right=0)
            self.set_mode(BILBO_Control_Mode.OFF)
            self.enable_external_input()

        setTimeout(_fall_down_callback, 0.1)

    # ------------------------------------------------------------------------------------------------------------------
    def set_external_input(self, left: float, right: float) -> None:
        if self.mode != BILBO_Control_Mode.BALANCING:
            self.logger.warning("Cannot set external input while not in BALANCING mode")
            return
        self.inputs.external.left = left + self._config.general.torque_offset[0]
        self.inputs.external.right = right + self._config.general.torque_offset[1]

    # ------------------------------------------------------------------------------------------------------------------
    def set_external_input_forward_turn(self, forward: float, turn: float, normalized: bool = True) -> None:
        if normalized:
            if not (-1 <= forward <= 1 and -1 <= turn <= 1):
                self.logger.warning(
                    f"External input must be between -1 and 1. Got forward: {forward} and turn: {turn}"
                )
                return
            forward = forward * self._config.inputs.balancing.forward.max
            turn = turn * self._config.inputs.balancing.turn.max

            torque_left = -(forward + turn)
            torque_right = -(forward - turn)
        else:
            torque_left = forward + turn
            torque_right = forward - turn

        if self.mode == BILBO_Control_Mode.BALANCING:
            self.set_external_input(torque_left, torque_right)

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity(self, forward: float, turn: float, normalized: bool = True) -> None:
        if self.mode != BILBO_Control_Mode.VELOCITY:
            self.logger.warning("Cannot set velocity while not in VELOCITY mode")
            return

        if normalized:
            if not (-1 <= forward <= 1 and -1 <= turn <= 1):
                self.logger.warning(
                    f"Velocity inputs must be between -1 and 1. Got forward: {forward} and turn: {turn}"
                )
                return
            forward = forward * self._config.inputs.velocity.forward.max
            turn = turn * self._config.inputs.velocity.turn.max

        self.inputs.velocity.forward = forward
        self.inputs.velocity.turn = turn

    # ------------------------------------------------------------------------------------------------------------------
    def set_statefeedback_gain(self, K: list | np.ndarray) -> bool:
        """Set the state feedback gain K for balancing control."""
        if isinstance(K, np.ndarray):
            K = K.tolist()

        if len(K) != 8:
            self.logger.error(f"State feedback gain must have 8 elements, got {len(K)}")
            return False

        result = self._set_lowlevel_state_feedback_gain(K)
        if result:
            self._config.balancing_control.K = K
            self.logger.info(f"State feedback gain set to {K}")
            self._notify_config_changed()
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def set_forward_velocity_pid_config(self, config: PID_Config | dict) -> bool:
        if isinstance(config, dict):
            config = from_dict_auto(PID_Config, config)

        self.logger.info(f"Setting forward velocity PID config to {config}")
        self._config.velocity_control.v.pid = config
        result = self._set_lowlevel_velocity_control_config(self._config.velocity_control)
        self._notify_config_changed()
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def set_forward_velocity_ff_config(self, config: Feedforward_Config | dict):
        if isinstance(config, dict):
            config = from_dict_auto(Feedforward_Config, config)

        self.logger.info(f"Setting forward velocity FF config to {config}")
        self._config.velocity_control.v.feedforward = config
        result = self._set_lowlevel_velocity_control_config(self._config.velocity_control)
        self._notify_config_changed()
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def set_turn_velocity_pid_config(self, config: PID_Config | dict) -> bool:
        if isinstance(config, dict):
            config = from_dict_auto(PID_Config, config)

        self.logger.info(f"Setting turn velocity PID config to {config}")
        self._config.velocity_control.psidot.pid = config
        result = self._set_lowlevel_velocity_control_config(self._config.velocity_control)
        self._notify_config_changed()
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def set_turn_velocity_ff_config(self, config: Feedforward_Config | dict):
        if isinstance(config, dict):
            config = from_dict_auto(Feedforward_Config, config)

        self.logger.info(f"Setting turn velocity FF config to {config}")
        self._config.velocity_control.psidot.feedforward = config
        result = self._set_lowlevel_velocity_control_config(self._config.velocity_control)
        self._notify_config_changed()
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def set_position_control_config(self, config: PositionControl_Config | dict):
        if isinstance(config, dict):
            config = from_dict_auto(PositionControl_Config, config)

        self.logger.info(f"Setting position control config to {config}")
        self._config.position_control = config
        result = self._set_lowlevel_position_control_config(self._config.position_control)
        self._notify_config_changed()
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def set_max_wheel_speed(self, speed: float):
        self.logger.info(f"Setting max wheel speed to {speed:.1f} m/s")
        self._config.general.max_wheel_speed = speed
        self._lowlevel_set_max_wheel_speed(speed)

    # ------------------------------------------------------------------------------------------------------------------
    def enable_vic_control(self, enable: bool = True):
        if not self._config.balancing_control.vic.enabled:
            self.logger.warning("Cannot set VIC control while VIC control is disabled. Change control config first")
            return
        self._set_lowlevel_vic_enabled(enable)

    # ------------------------------------------------------------------------------------------------------------------
    def enable_tic_control(self, enable: bool = True):

        if not self._config.balancing_control.tic.enabled:
            self.logger.warning("Cannot set TIC control while TIC control is disabled. Change control config first")
            return

        self._set_lowlevel_tic_enabled(enable)

    # ------------------------------------------------------------------------------------------------------------------
    def enable_psi_control(self, enable: bool = True):
        self._set_lowlevel_psi_enabled(enable)

    # ------------------------------------------------------------------------------------------------------------------
    def set_psi_setpoint(self, psi: float):
        self._set_lowlevel_psi_setpoint(psi)

    # === POSITION CONTROL WRAPPERS ====================================================================================
    def _ensure_position_mode(self) -> BILBO_Control_Mode | None:
        """Switch to POSITION mode if allowed. Returns the previous mode if a switch happened, None otherwise."""
        if self.mode == BILBO_Control_Mode.POSITION:
            return None
        if not self._auto_position_mode:
            self.logger.warning("Not in POSITION mode and auto_position_mode is disabled")
            return None
        if self.mode == BILBO_Control_Mode.OFF:
            self.logger.warning("Cannot auto-switch to POSITION mode from OFF")
            return None
        previous_mode = self.mode
        self.logger.info(f"Auto-switching to POSITION mode (from {previous_mode.name})")
        if not self.set_mode(BILBO_Control_Mode.POSITION):
            return None
        # Ensure position_control sees the mode change immediately (the event callback
        # may run in a separate thread and not complete before we call into position_control)
        self.position_control._top_level_control_mode = BILBO_Control_Mode.POSITION
        return previous_mode

    # ------------------------------------------------------------------------------------------------------------------
    def _restore_mode_after(self, previous_mode: BILBO_Control_Mode, terminal_events: list[Event]):
        """Spawn a daemon thread that waits for any terminal event or an external mode change,
        then restores the previous mode (only if no external mode change occurred)."""

        def _wait_and_restore():
            # Wait for either a terminal event (command done) or an external mode change
            all_events = terminal_events + [self.events.mode_change]
            data, trace = wait_for_events(OR(*all_events), timeout=120)

            if data is TIMEOUT:
                self.logger.warning("Auto-mode-restore timed out (120s), not restoring")
                return

            # If mode_change fired, someone else changed the mode — don't restore
            if trace is not None and trace.caused_by(self.events.mode_change):
                self.logger.debug("External mode change detected, skipping auto-restore")
                return

            # Terminal event fired — restore previous mode
            if self.mode == BILBO_Control_Mode.POSITION:
                self.logger.info(f"Position command finished, restoring {previous_mode.name} mode")
                self.set_mode(previous_mode)

        thread = threading.Thread(target=_wait_and_restore, daemon=True)
        thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def _restore_mode_direct(self, previous_mode: BILBO_Control_Mode):
        """Restore the previous mode immediately (for use after blocking calls).
        Only restores if no external mode change occurred in the meantime."""
        if self.mode == BILBO_Control_Mode.POSITION:
            self.logger.info(f"Position command finished, restoring {previous_mode.name} mode")
            self.set_mode(previous_mode)

    # ------------------------------------------------------------------------------------------------------------------
    def move_to_point(self, x: float, y: float,
                      max_speed: float = 0.0,
                      timeout: float = 0.0,
                      blocking: bool = False) -> bool:
        previous_mode = self._ensure_position_mode()
        if self.mode != BILBO_Control_Mode.POSITION:
            return False
        result = self.position_control.move_to_point(x, y, max_speed=max_speed, timeout=timeout, blocking=blocking)
        if result and previous_mode is not None:
            self._restore_mode_after(previous_mode, [
                self.position_control.events.move_to_point_completed,
                self.position_control.events.move_to_point_timeout,
            ])
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def turn_to_heading(self, heading: float,
                        max_angular_speed: float = 0.0,
                        timeout: float = 0.0,
                        blocking: bool = False) -> bool:
        previous_mode = self._ensure_position_mode()
        if self.mode != BILBO_Control_Mode.POSITION:
            return False
        result = self.position_control.turn_to_heading(heading, max_angular_speed=max_angular_speed,
                                                       timeout=timeout, blocking=blocking)
        if result and previous_mode is not None:
            self._restore_mode_after(previous_mode, [
                self.position_control.events.turn_to_heading_completed,
                self.position_control.events.turn_to_heading_timeout,
            ])
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def move_to_pose(self, x: float, y: float, heading: float,
                     max_speed: float = 0.0,
                     max_angular_speed: float = 3.0,
                     position_tolerance: float = 0.0,
                     max_corrections: int = 3,
                     timeout: float = 0.0,
                     blocking: bool = False) -> bool:
        previous_mode = self._ensure_position_mode()
        if self.mode != BILBO_Control_Mode.POSITION:
            return False
        result = self.position_control.move_to_pose(x, y, heading, max_speed=max_speed,
                                                     max_angular_speed=max_angular_speed,
                                                     position_tolerance=position_tolerance,
                                                     max_corrections=max_corrections,
                                                     timeout=timeout, blocking=blocking)
        if result and previous_mode is not None:
            if blocking:
                # Blocking call already waited for completion — restore mode directly
                self._restore_mode_direct(previous_mode)
            else:
                self._restore_mode_after(previous_mode, [
                    self.position_control.events.move_to_pose_completed,
                    self.position_control.events.move_to_pose_timeout,
                ])
        return result

    # ------------------------------------------------------------------------------------------------------------------
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
        previous_mode = self._ensure_position_mode()
        if self.mode != BILBO_Control_Mode.POSITION:
            return False
        result = self.position_control.plan_and_follow(
            target=target, waypoints=waypoints, obstacles=obstacles, bounds=bounds,
            stop_indices=stop_indices, max_speed=max_speed, max_spacing=max_spacing,
            timeout=timeout, allow_reverse=allow_reverse, seed=seed, start=start,
            blocking=blocking, target_heading=target_heading, heading_strength=heading_strength)
        if result and previous_mode is not None:
            self._restore_mode_after(previous_mode, [
                self.position_control.events.path_finished,
                self.position_control.events.path_timeout,
                self.position_control.events.path_aborted,
            ])
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def start_path(self, max_speed: float = 0.0, max_spacing: float = 0.0,
                   timeout: float = 0.0, allow_reverse: bool = False) -> bool:
        previous_mode = self._ensure_position_mode()
        if self.mode != BILBO_Control_Mode.POSITION:
            return False
        result = self.position_control.start_path(max_speed=max_speed, max_spacing=max_spacing,
                                                   timeout=timeout, allow_reverse=allow_reverse)
        if result and previous_mode is not None:
            self._restore_mode_after(previous_mode, [
                self.position_control.events.path_finished,
                self.position_control.events.path_timeout,
                self.position_control.events.path_aborted,
            ])
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def load_path(self, path_data, start: bool = False, clear_existing: bool = True) -> bool:
        if start:
            previous_mode = self._ensure_position_mode()
            if self.mode != BILBO_Control_Mode.POSITION:
                return False
        else:
            previous_mode = None
        result = self.position_control.load_path(path_data=path_data, start=start,
                                                  clear_existing=clear_existing)
        if start and result and previous_mode is not None:
            self._restore_mode_after(previous_mode, [
                self.position_control.events.path_finished,
                self.position_control.events.path_timeout,
                self.position_control.events.path_aborted,
            ])
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> BILBO_Control_Sample:
        sample = BILBO_Control_Sample(
            status=self.status,
            mode=self.mode,
            input=self.inputs,
            tic_enabled=self.controller_status.tic_enabled,
            vic_enabled=self.controller_status.vic_enabled,
            psi_enabled=self.controller_status.psi_enabled,
            input_enabled=self.inputs.enabled
        )
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample_dict(self) -> dict:
        sample_dict = {
            'status': self.status.value,
            'mode': self.mode.value,
            'input': dataclasses.asdict(self.inputs),
            'tic_enabled': self.controller_status.tic_enabled,
            'vic_enabled': self.controller_status.vic_enabled,
            'psi_enabled': self.controller_status.psi_enabled,
            'input_enabled': self.inputs.enabled,
            'position_control': self.position_control.get_sample_dict()
        }
        return sample_dict

    # === PRIVATE METHODS ==============================================================================================
    def _register_wifi_commands(self):

        self.communication.wifi.newCommand(identifier='set_control_mode',
                                           function=self.set_mode,
                                           arguments=['mode'],
                                           description='Sets the control mode')

        self.communication.wifi.newCommand(identifier='set_external_input_forward_turn',
                                           function=self.set_external_input_forward_turn,
                                           arguments=['forward', 'turn', 'normalized'],
                                           description='Sets the Input')

        self.communication.wifi.newCommand(identifier='set_velocity',
                                           function=self.set_velocity,
                                           arguments=['forward', 'turn', 'normalized'],
                                           description='Sets the Speed')

        self.communication.wifi.newCommand(identifier='enable_tic',
                                           function=self.enable_tic_control,
                                           arguments=['enable'],
                                           description='Enables or disables the TIC control')

        self.communication.wifi.newCommand(identifier='enable_vic',
                                           function=self.enable_vic_control,
                                           arguments=['enable'],
                                           description='Enables or disables the VIC control'
                                           )

        self.communication.wifi.newCommand(identifier='set_velocity_pid_config_forward',
                                           function=self.set_forward_velocity_pid_config,
                                           arguments=['config'],
                                           description='Sets the forward velocity PID config')

        self.communication.wifi.newCommand(identifier='get_velocity_config_forward',
                                           function=lambda: self._config.velocity_control.v,
                                           arguments=[],
                                           description='Gets the forward velocity PID config')

        self.communication.wifi.newCommand(identifier='set_velocity_pid_config_turn',
                                           function=self.set_turn_velocity_pid_config,
                                           arguments=['config'],
                                           description='Sets the turn velocity PID config')

        self.communication.wifi.newCommand(identifier='get_velocity_config_turn',
                                           function=lambda: self._config.velocity_control.psidot,
                                           arguments=[],
                                           description='Gets the turn velocity PID config')

        self.communication.wifi.newCommand(identifier='set_position_control_config',
                                           function=self.set_position_control_config,
                                           arguments=['config'],
                                           description='Sets the position control config'
                                           )

        self.communication.wifi.newCommand(identifier='get_position_control_config',
                                           function=lambda: self._config.position_control,
                                           arguments=[],
                                           description='Gets the position control config'
                                           )

        self.communication.wifi.newCommand(identifier='get_control_config',
                                           function=self.get_control_config,
                                           arguments=[],
                                           description='Gets the control config')

        self.communication.wifi.newCommand(identifier='load_default_control_config',
                                           function=self.load_and_set_default_config,
                                           arguments=[],
                                           description='Loads and applies the default control config')

        self.communication.wifi.newCommand(identifier='set_velocity_ff_config_forward',
                                           function=self.set_forward_velocity_ff_config,
                                           arguments=['config'],
                                           description='Sets the forward velocity feedforward config')

        self.communication.wifi.newCommand(identifier='set_velocity_ff_config_turn',
                                           function=self.set_turn_velocity_ff_config,
                                           arguments=['config'],
                                           description='Sets the turn velocity feedforward config')

        self.communication.wifi.newCommand(identifier='set_tic_config',
                                           function=self._set_tic_config_from_wifi,
                                           arguments=['config'],
                                           description='Sets the TIC config')

        self.communication.wifi.newCommand(identifier='set_vic_config',
                                           function=self._set_vic_config_from_wifi,
                                           arguments=['config'],
                                           description='Sets the VIC config')

        self.communication.wifi.newCommand(identifier='enable_psi',
                                           function=self.enable_psi_control,
                                           arguments=['enable'],
                                           description='Enables or disables the PSI control')

        self.communication.wifi.newCommand(identifier='set_psi_config',
                                           function=self._set_psi_config_from_wifi,
                                           arguments=['config'],
                                           description='Sets the PSI config')

        self.communication.wifi.newCommand(identifier='set_psi_setpoint',
                                           function=self.set_psi_setpoint,
                                           arguments=['psi'],
                                           description='Sets the PSI controller setpoint')

        self.communication.wifi.newCommand(identifier='set_general_config',
                                           function=self._set_general_config_from_wifi,
                                           arguments=['max_wheel_torque', 'max_wheel_speed'],
                                           description='Sets general control config (max torque/speed)')

        self.communication.wifi.newCommand(identifier='set_statefeedback_gain',
                                           function=self._set_statefeedback_gain_from_wifi,
                                           arguments=['K'],
                                           description='Sets the state feedback gain K (flat list of 8)')

        self.communication.wifi.newCommand(identifier='fall_down',
                                           function=self.fall_down,
                                           arguments=['direction'],
                                           description='Falls over in the given direction (forward/backward)')

        # Position control motion commands (with auto mode-switching)
        self.communication.wifi.newCommand(
            identifier='position_control_move_to',
            function=self._wifi_move_to,
            arguments=[
                'x', 'y',
                CommandArgument(name='max_speed', type=float, optional=True, default=0.0),
                CommandArgument(name='timeout', type=float, optional=True, default=0.0)
            ],
            description='Move to a single point (auto-switches to POSITION mode)'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_turn_to',
            function=self._wifi_turn_to,
            arguments=[
                'heading',
                CommandArgument(name='max_angular_speed', type=float, optional=True, default=0.0),
                CommandArgument(name='timeout', type=float, optional=True, default=0.0)
            ],
            description='Turn to a heading in radians (auto-switches to POSITION mode)'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_move_to_pose',
            function=self._wifi_move_to_pose,
            arguments=[
                'x', 'y', 'heading',
                CommandArgument(name='max_speed', type=float, optional=True, default=0.0),
                CommandArgument(name='max_angular_speed', type=float, optional=True, default=1.0),
                CommandArgument(name='position_tolerance', type=float, optional=True, default=0.0),
                CommandArgument(name='max_corrections', type=int, optional=True, default=3),
                CommandArgument(name='timeout', type=float, optional=True, default=0.0),
            ],
            description='Move to a pose (auto-switches to POSITION mode)',
            execute_in_thread=True
        )

        self.communication.wifi.newCommand(
            identifier='position_control_plan_and_follow',
            function=self._wifi_plan_and_follow,
            arguments=[
                'target',
                CommandArgument(name='waypoints', type=list, optional=True, default=None),
                CommandArgument(name='obstacles', type=list, optional=True, default=None),
                CommandArgument(name='bounds', type=dict, optional=True, default=None),
                CommandArgument(name='stop_indices', type=list, optional=True, default=None),
                CommandArgument(name='max_speed', type=float, optional=True, default=0.0),
                CommandArgument(name='max_spacing', type=float, optional=True, default=0.0),
                CommandArgument(name='timeout', type=float, optional=True, default=0.0),
                CommandArgument(name='allow_reverse', type=bool, optional=True, default=False),
                CommandArgument(name='seed', type=int, optional=True, default=None),
                CommandArgument(name='target_heading', type=float, optional=True, default=None),
                CommandArgument(name='heading_strength', type=float, optional=True, default=1.0),
            ],
            description='Plan path to target and follow it (auto-switches to POSITION mode)',
            execute_in_thread=True
        )

        self.communication.wifi.newCommand(
            identifier='position_control_start_path',
            function=self._wifi_start_path,
            arguments=[
                CommandArgument(name='max_speed', type=float, optional=True, default=0.0),
                CommandArgument(name='max_spacing', type=float, optional=True, default=0.0),
                CommandArgument(name='timeout', type=float, optional=True, default=0.0),
                CommandArgument(name='allow_reverse', type=bool, optional=True, default=False),
            ],
            description='Start following loaded path (auto-switches to POSITION mode)'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_load_path',
            function=self._wifi_load_path,
            arguments=[
                'path',
                CommandArgument(name='start', type=bool, optional=True, default=False),
                CommandArgument(name='clear_existing', type=bool, optional=True, default=True),
            ],
            description='Load a path (auto-switches to POSITION mode if start=True)',
            execute_in_thread=True
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _wifi_move_to(self, x: float, y: float, max_speed: float = 0.0, timeout: float = 0.0) -> bool:
        return self.move_to_point(x=x, y=y, max_speed=max_speed, timeout=timeout)

    def _wifi_turn_to(self, heading: float, max_angular_speed: float = 0.0, timeout: float = 0.0) -> bool:
        return self.turn_to_heading(heading=heading, max_angular_speed=max_angular_speed, timeout=timeout)

    def _wifi_move_to_pose(self, x: float, y: float, heading: float,
                           max_speed: float = 0.0, max_angular_speed: float = 1.0,
                           position_tolerance: float = 0.0, max_corrections: int = 3,
                           timeout: float = 0.0) -> bool:
        return self.move_to_pose(
            x=x, y=y, heading=heading,
            max_speed=max_speed, max_angular_speed=max_angular_speed,
            position_tolerance=position_tolerance, max_corrections=max_corrections,
            timeout=timeout, blocking=True,
        )

    def _wifi_plan_and_follow(self, target, waypoints=None, obstacles=None, bounds=None,
                              stop_indices=None, max_speed=0.0, max_spacing=0.0,
                              timeout=0.0, allow_reverse=False, seed=None,
                              target_heading=None, heading_strength=1.0) -> bool:
        if isinstance(target, dict):
            target = (float(target['x']), float(target['y']))
        elif isinstance(target, (list, tuple)):
            target = (float(target[0]), float(target[1]))
        return self.plan_and_follow(
            target=target,
            waypoints=waypoints,
            obstacles=obstacles,
            bounds=bounds,
            stop_indices=stop_indices,
            max_speed=float(max_speed),
            max_spacing=float(max_spacing),
            timeout=float(timeout),
            allow_reverse=bool(allow_reverse),
            seed=int(seed) if seed is not None else None,
            target_heading=float(target_heading) if target_heading is not None else None,
            heading_strength=float(heading_strength),
        )

    def _wifi_start_path(self, max_speed: float = 0.0, max_spacing: float = 0.0,
                         timeout: float = 0.0, allow_reverse: bool = False) -> bool:
        return self.start_path(max_speed=max_speed, max_spacing=max_spacing,
                               timeout=timeout, allow_reverse=allow_reverse)

    def _wifi_load_path(self, path: dict, start: bool = False, clear_existing: bool = True) -> bool:
        return self.load_path(path_data=path, start=start, clear_existing=clear_existing)

    # ------------------------------------------------------------------------------------------------------------------
    def _notify_config_changed(self):
        """Send a configuration_change WiFi event to the host."""
        try:
            self.wifi_events.configuration_change.send(data={})
        except Exception:
            pass

    # ------------------------------------------------------------------------------------------------------------------
    def _set_statefeedback_gain_from_wifi(self, K: list):
        self.logger.info(f"Setting state feedback gain: {K}")
        return self.set_statefeedback_gain(K)

    # ------------------------------------------------------------------------------------------------------------------
    def _set_tic_config_from_wifi(self, config: dict):
        tic = from_dict_auto(TIC_Config, config)
        self._config.balancing_control.tic = tic
        result = self._set_lowlevel_tic_config(tic)
        self._notify_config_changed()
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def _set_vic_config_from_wifi(self, config: dict):
        vic = from_dict_auto(VIC_Config, config)
        self._config.balancing_control.vic = vic
        result = self._set_lowlevel_vic_config(vic)
        self._notify_config_changed()
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def _set_psi_config_from_wifi(self, config: dict):
        psi = from_dict_auto(PSI_Config, config)
        self._config.balancing_control.psi = psi
        result = self._set_lowlevel_psi_config(psi)
        self._notify_config_changed()
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def _set_general_config_from_wifi(self, max_wheel_torque: float, max_wheel_speed: float):
        self.logger.info(
            f"Setting general config: max_torque={max_wheel_torque:.3f} Nm, max_speed={max_wheel_speed:.3f} rad/s")
        self._config.general.max_wheel_torque = max_wheel_torque
        self._config.general.max_wheel_speed = max_wheel_speed
        self._set_lowlevel_max_torque(max_wheel_torque)
        self._lowlevel_set_max_wheel_speed(max_wheel_speed)
        self._notify_config_changed()
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_sample_callback(self, sample: BILBO_LL_Sample):

        # Update the controller status
        self.controller_status.vic_enabled = bool(sample.control.vic_enabled)
        self.controller_status.tic_enabled = bool(sample.control.tic_enabled)
        self.controller_status.psi_enabled = bool(sample.control.psi_enabled)

        # Mode mismatch detection from samples (safeguard against missed UART events)
        ll_mode = BILBO_Control_Mode(sample.control.mode)
        if ll_mode != self.mode and not self._mode_transition_pending:
            self._mode_mismatch_count += 1
            if self._mode_mismatch_count >= self._MODE_MISMATCH_THRESHOLD:
                self.logger.warning(
                    f"Mode mismatch detected from samples (firmware={ll_mode}, local={self.mode}). "
                    f"Syncing to firmware mode."
                )
                self._mode_mismatch_count = 0
                self._lowlevel_mode_change_event(ll_mode)
        else:
            self._mode_mismatch_count = 0

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_mode_change_event(self, mode_ll: BILBO_Control_Mode, *args, **kwargs):
        self.logger.debug(f"LL Mode changed to {mode_ll}")
        if mode_ll != self.mode:
            self.logger.info(
                f"LL Mode changed to {mode_ll.name}, local mode is {self.mode.name}. Syncing to firmware mode.")
            self.set_mode(mode_ll, wait_for_change=False)

        self.events.lowlevel_mode_change.set(mode_ll, flags={'mode': mode_ll})

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_vic_change_event(self, data: dict, *args, **kwargs):
        control_data = data.get('data', None)
        if control_data is None:
            self.logger.warning("Failed to read control data from LL. Something is wrong.")
            return
        vic_enabled = control_data.get('vic_enabled', None)
        if vic_enabled is None:
            self.logger.warning("Failed to read VIC enabled state from LL. Something is wrong.")
            return
        self.controller_status.vic_enabled = bool(vic_enabled)
        self.events.vic_change.set(vic_enabled)
        self.wifi_events.vic_change.send(data={'vic_enabled': self.controller_status.vic_enabled})
        self.logger.debug(f"VIC enabled state changed to {vic_enabled}")

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_tic_change_event(self, data: dict, *args, **kwargs):
        control_data = data.get('data', None)
        if control_data is None:
            self.logger.warning("Failed to read control data from LL. Something is wrong.")
            return
        tic_enabled = control_data.get('tic_enabled', None)
        if tic_enabled is None:
            self.logger.warning("Failed to read TIC enabled state from LL. Something is wrong.")
            return

        self.controller_status.tic_enabled = bool(tic_enabled)
        self.events.tic_change.set(tic_enabled)
        self.wifi_events.tic_change.send(data={'tic_enabled': self.controller_status.tic_enabled})

        self.logger.debug(f"TIC enabled state changed to {tic_enabled}")

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_psi_change_event(self, data: dict, *args, **kwargs):
        control_data = data.get('data', None)
        if control_data is None:
            self.logger.warning("Failed to read control data from LL. Something is wrong.")
            return
        psi_enabled = control_data.get('psi_enabled', None)
        if psi_enabled is None:
            self.logger.warning("Failed to read PSI enabled state from LL. Something is wrong.")
            return

        self.controller_status.psi_enabled = bool(psi_enabled)
        self.events.psi_change.set(psi_enabled)
        self.wifi_events.psi_change.send(data={'psi_enabled': self.controller_status.psi_enabled})

        if psi_enabled:
            current_psi = self.estimation.state.psi
            self.logger.info(
                f"PSI control enabled. Tracking psi = {current_psi:.4f} rad ({np.degrees(current_psi):.2f} deg)")
        else:
            self.logger.info("PSI control disabled")

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_control_config(self, config: BILBO_ControlConfig) -> bool:

        result = self._set_lowlevel_velocity_control_config(config.velocity_control)
        if not result: return False

        result = self._set_lowlevel_position_control_config(config.position_control)
        if not result: return False

        self.position_control.set_planning_config(config.planning)

        result = self._set_lowlevel_tic_config(config.balancing_control.tic)
        if not result: return False

        result = self._set_lowlevel_vic_config(config.balancing_control.vic)
        if not result: return False

        result = self._set_lowlevel_psi_config(config.balancing_control.psi)
        if not result: return False

        result = self._set_lowlevel_max_torque(config.general.max_wheel_torque)
        if not result: return False

        result = self._set_lowlevel_state_feedback_gain(config.balancing_control.K)
        if not result: return False

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_velocity_control_config(self, config: VelocityControl_Config) -> bool:
        pid_config_v = pid_control_config_t(
            Kp=config.v.pid.Kp,
            Ki=config.v.pid.Ki,
            Kd=config.v.pid.Kd,
            Ts=LOOP_TIME_CONTROL,
            enable_i_limit=config.v.pid.enable_i_limit,
            i_term_limit=config.v.pid.i_term_limit,
            enable_input_limit=config.v.pid.enable_input_limit,
            input_limit=config.v.pid.input_limit,
            enable_output_limit=config.v.pid.enable_output_limit,
            output_limit=config.v.pid.output_limit,
            enable_d_filter=config.v.pid.enable_d_filter,
            Td_filter=config.v.pid.Td_filter,
            enable_rate_limit=config.v.pid.enable_rate_limit,
            rate_limit=config.v.pid.rate_limit,
            enable_setpoint_rate_limit=config.v.pid.enable_setpoint_rate_limit,
            setpoint_rate_limit=config.v.pid.setpoint_rate_limit,
        )
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_VELOCITY_CONFIG_V,
            input_type=pid_control_config_t,
            output_type=ctypes.c_bool,
            data=pid_config_v
        )

        if result is None or not result:
            self.logger.error("Failed to set velocity PID config")
            return False

        ff_config_v = feedforward_config_t(
            Kv=config.v.feedforward.Kv,
            Ka=config.v.feedforward.Ka,
            Kc=config.v.feedforward.Kc,
            Ts=LOOP_TIME_CONTROL,
            enable_vref_slew=config.v.feedforward.enable_vref_slew,
            vref_slew_rate=config.v.feedforward.vref_slew_rate,
            enable_a_filter=config.v.feedforward.enable_a_filter,
            Ta_filter=config.v.feedforward.Ta_filter,
            enable_stiction=config.v.feedforward.enable_stiction,
            v0_stiction=config.v.feedforward.v0_stiction,
            v_decay_stiction=config.v.feedforward.v_decay_stiction,
            enable_output_limit=config.v.feedforward.enable_output_limit,
            output_limit=config.v.feedforward.output_limit,
            enable_output_slew=config.v.feedforward.enable_output_slew,
            output_slew_rate=config.v.feedforward.output_slew_rate,
        )

        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_VELOCITY_CONFIG_V_FF,
            input_type=feedforward_config_t,
            output_type=ctypes.c_bool,
            data=ff_config_v
        )
        if not result:
            self.logger.error("Failed to set velocity feedforward config")
            return False

        pid_config_psi_dot = pid_control_config_t(
            Kp=config.psidot.pid.Kp,
            Ki=config.psidot.pid.Ki,
            Kd=config.psidot.pid.Kd,
            Ts=LOOP_TIME_CONTROL,
            enable_i_limit=config.psidot.pid.enable_i_limit,
            i_term_limit=config.psidot.pid.i_term_limit,
            enable_input_limit=config.psidot.pid.enable_input_limit,
            input_limit=config.psidot.pid.input_limit,
            enable_output_limit=config.psidot.pid.enable_output_limit,
            output_limit=config.psidot.pid.output_limit,
            enable_d_filter=config.psidot.pid.enable_d_filter,
            enable_rate_limit=config.psidot.pid.enable_rate_limit,
            rate_limit=config.psidot.pid.rate_limit,
            enable_setpoint_rate_limit=config.psidot.pid.enable_setpoint_rate_limit,
            setpoint_rate_limit=config.psidot.pid.setpoint_rate_limit,
        )

        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_VELOCITY_CONFIG_PSIDOT,
            input_type=pid_control_config_t,
            output_type=ctypes.c_bool,
            data=pid_config_psi_dot
        )

        if result is None or not result:
            self.logger.error("Failed to set psi_dot PID config")
            return False

        ff_config_psi_dot = feedforward_config_t(
            Kv=config.psidot.feedforward.Kv,
            Ka=config.psidot.feedforward.Ka,
            Kc=config.psidot.feedforward.Kc,
            Ts=LOOP_TIME_CONTROL,
            enable_vref_slew=config.psidot.feedforward.enable_vref_slew,
            vref_slew_rate=config.psidot.feedforward.vref_slew_rate,
            enable_a_filter=config.psidot.feedforward.enable_a_filter,
            Ta_filter=config.psidot.feedforward.Ta_filter,
            enable_stiction=config.psidot.feedforward.enable_stiction,
            v0_stiction=config.psidot.feedforward.v0_stiction,
            v_decay_stiction=config.psidot.feedforward.v_decay_stiction,
            enable_output_limit=config.psidot.feedforward.enable_output_limit,
            output_limit=config.psidot.feedforward.output_limit,
            enable_output_slew=config.psidot.feedforward.enable_output_slew,
            output_slew_rate=config.psidot.feedforward.output_slew_rate,
        )
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_VELOCITY_CONFIG_PSIDOT_FF,
            input_type=feedforward_config_t,
            output_type=ctypes.c_bool,
            data=ff_config_psi_dot
        )
        if not result:
            self.logger.error("Failed to set psi_dot feedforward config")
            return False

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_position_control_config(self, config: PositionControl_Config) -> bool:
        # Config is sent to STM32 via position_control.set_config() which handles
        # the ctypes conversion and serial transmission internally.
        return self.position_control.set_config(config)

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_tic_config(self, config: TIC_Config) -> bool:
        tic_config = bilbo_tic_config_t(
            enabled=config.enabled,
            Ts=LOOP_TIME_CONTROL,
            ki=config.ki,
            max_torque=config.max_torque,
            theta_limit=config.theta_limit
        )
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_TIC_CONFIG,
            input_type=bilbo_tic_config_t,
            output_type=ctypes.c_bool,
            data=tic_config
        )
        if result is None or not result:
            self.logger.error("Failed to set TIC config")
            return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_vic_config(self, config: VIC_Config) -> bool:
        vic_config = bilbo_vic_config_t(
            enabled=config.enabled,
            Ts=LOOP_TIME_CONTROL,
            ki=config.ki,
            max_torque=config.max_torque,
            v_limit=config.v_limit
        )
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_VIC_CONFIG,
            input_type=bilbo_vic_config_t,
            output_type=ctypes.c_bool,
            data=vic_config
        )
        if result is None or not result:
            self.logger.error("Failed to set VIC config")
            return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_psi_config(self, config: PSI_Config) -> bool:
        psi_config = bilbo_psi_config_t(
            enabled=config.enabled,
            Ts=LOOP_TIME_CONTROL,
            kp=config.kp,
            ki=config.ki,
            max_torque=config.max_torque,
        )
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_PSI_CONFIG,
            input_type=bilbo_psi_config_t,
            output_type=ctypes.c_bool,
            data=psi_config
        )
        self.logger.info(
            f"Setting PSI config: Kp: {psi_config.kp:.3f}, Ki: {psi_config.ki:.3f}, enabled: {psi_config.enabled}")
        if result is None or not result:
            self.logger.error("Failed to set PSI config")
            return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_psi_enabled(self, enabled: bool):
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.ENABLE_PSI,
            input_type=ctypes.c_bool,
            output_type=ctypes.c_bool,
            data=enabled
        )
        if result is None:
            self.logger.warning("Failed to set PSI enabled state")
            return
        if not result:
            self.logger.warning("Failed to set PSI enabled state. Return value: false")
            return

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_psi_setpoint(self, psi: float):
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_PSI_SETPOINT,
            input_type=ctypes.c_float,
            output_type=ctypes.c_bool,
            data=psi
        )
        if result is None:
            self.logger.warning("Failed to set PSI setpoint")
            return
        if not result:
            self.logger.warning("Failed to set PSI setpoint. Return value: false")
            return

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_max_torque(self, torque: float) -> bool:
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_MAX_TORQUE,
            input_type=ctypes.c_float,
            output_type=ctypes.c_bool,
            data=torque
        )
        if result is None or not result:
            self.logger.error("Failed to set max torque")
            return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _get_lowlevel_control_config(self) -> bilbo_control_config_t | None:
        raise NotImplementedError("This is probably longer than 128 Bytes. I need to rework this")

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_control_mode(self, mode: BILBO_Control_Mode) -> bool:
        self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_MODE,
            input_type=ctypes.c_uint8,
            output_type=None,
            data=mode.value
        )
        # if result is None:
        #     self.logger.warning("Failed to set control mode")
        #     return False
        # if not result:
        #     self.logger.warning("Failed to set control mode. Return value: false")
        #     return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _get_lowlevel_control_mode(self) -> BILBO_Control_Mode | None:
        mode = self.communication.serial.readValue(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.READ_MODE,
            type=ctypes.c_uint8,
        )
        if mode is None:
            self.logger.warning("Failed to read control mode")
            return None
        return BILBO_Control_Mode(mode)

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_vic_enabled(self, enabled: bool):
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.ENABLE_VIC,
            input_type=ctypes.c_bool,
            output_type=ctypes.c_bool,
            data=enabled
        )
        if result is None:
            self.logger.warning("Failed to set VIC enabled state")
            return
        if not result:
            self.logger.warning("Failed to set VIC enabled state. Return value: false")
            return

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_tic_enabled(self, enabled: bool):
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.ENABLE_TIC,
            input_type=ctypes.c_bool,
            output_type=ctypes.c_bool,
            data=enabled
        )
        if result is None:
            self.logger.warning("Failed to set TIC enabled state")
            return
        if not result:
            self.logger.warning("Failed to set TIC enabled state. Return value: false")
            return

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_external_input(self, left: float, right: float):
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_BALANCING_INPUT,
            input_type=bilbo_control_input_ext_t,
            data={
                'u_left': left,
                'u_right': right
            },
            output_type=ctypes.c_bool,
        )
        if result is None:
            self.logger.warning("Failed to set external input")
            return
        if not result:
            self.logger.warning("Failed to set external input. Return value: false")
            return

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_velocity_command(self, forward: float, turn: float):
        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_SPEED_INPUT,
            input_type=bilbo_velocity_control_command_t,
            data={
                'v': forward,
                'psi_dot': turn
            },
            output_type=ctypes.c_bool,
        )
        if result is None:
            self.logger.warning("Failed to set velocity command")
            return

        if not result:
            self.logger.warning("Failed to set velocity command. Return value: false")
            return

    # NOTE: Legacy position/heading command methods removed - functionality is now in bilbo_position_control.py

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_set_max_wheel_speed(self, speed: float):
        self.communication.serial.writeValue(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.RW_MAX_WHEEL_SPEED,
            value=float(speed),
            type=ctypes.c_float
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_state_feedback_gain(self, gain: list | np.ndarray):
        if isinstance(gain, np.ndarray): gain = gain.tolist()

        assert (isinstance(gain, list))
        assert (len(gain) == 8)
        assert (all(isinstance(elem, (float, int)) for elem in gain))

        result = self.communication.serial.executeFunction(
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=BILBO_ControlAddresses.SET_K,
            data=gain,
            input_type=ctypes.c_float * 8,  # type: Ignore
            output_type=ctypes.c_bool,
        )

        if result is None or not result:
            self.logger.error("Failed to set state feedback gain")
            return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_control_event_callback(self, message: BILBO_Control_Event_Message):
        event = BILBO_Control_Event_Type(message.data['event'])

        self.logger.debug(f"Received control event: {event}")

        match event:
            case BILBO_Control_Event_Type.ERROR:
                self.logger.error(f"Error in the LL Control Module: {message.data['error']}")
            case BILBO_Control_Event_Type.MODE_CHANGED:
                self._lowlevel_mode_change_event(BILBO_Control_Mode(message.data['mode']))
            case BILBO_Control_Event_Type.VIC_CHANGED:
                self._lowlevel_vic_change_event(message.data)
            case BILBO_Control_Event_Type.TIC_CHANGED:
                self._lowlevel_tic_change_event(message.data)
            case BILBO_Control_Event_Type.PSI_CHANGED:
                self._lowlevel_psi_change_event(message.data)
            case _:
                self.logger.warning(f"Unhandled control event: {event}")
    # ------------------------------------------------------------------------------------------------------------------
