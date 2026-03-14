"""
Simulated BILBO_Communication for digital twin mode.

Replaces the real Serial/SPI hardware communication with a SimulatedFirmware.
All register read/write/function calls are routed to the firmware simulation.
Sample and event callbacks are bridged from the firmware thread to the BILBO
callback/event system exactly as the real SPI/Serial path would.
"""
from __future__ import annotations

import ctypes
import dataclasses
import threading
from typing import Any

from core.utils.callbacks import callback_definition, CallbackContainer, OPTIONAL
from core.utils.dataclass_utils import asdict_optimized
from core.utils.events import Event, event_definition
from core.utils.logging_utils import Logger
from robot.bilbo_common import BILBO_Common
from robot.communication.serial.bilbo_serial_messages import (
    BILBO_SERIAL_MESSAGES,
)
from robot.communication.wifi.bilbo_wifi import BILBO_WIFI_Interface
from robot.lowlevel.stm32_addresses import (
    BILBO_ControlAddresses,
    BILBO_PositionControlAddresses,
    BILBO_EstimationAddresses,
    BILBO_SystemAddresses,
)
from robot.lowlevel.stm32_control import (
    BILBO_Control_Event_Message,
    BILBO_PositionControl_Event_Message,
    control_event_t,
    position_control_event_t,
    bilbo_position_control_data,
)
from robot.lowlevel.stm32_sample import BILBO_LL_Sample
from simulation.control import PIDConfig, FeedforwardConfig, TICConfig, VICConfig, PSIConfig
from simulation.firmware import SimulatedFirmware
from simulation.position_control import PositionControlConfig

logger = Logger("SIM-COMM")
logger.setLevel("INFO")


# ─── Callback / Event definitions (same shape as real BILBO_Communication) ────

@callback_definition
class SimulatedCommunication_Callbacks:
    rx_stm32_sample: CallbackContainer


@event_definition
class SimulatedCommunication_Events:
    rx_stm32_sample: Event = Event(data_type=BILBO_LL_Sample, copy_data_on_set=False)
    stm32_tick: Event


# ─── Simulated Serial ────────────────────────────────────────────────────────

@callback_definition
class _SimSerialCallbacks:
    rx: CallbackContainer
    event: CallbackContainer = CallbackContainer(parameters=[('messages', list, OPTIONAL)])
    error: CallbackContainer
    debug: CallbackContainer


@event_definition
class _SimSerialEvents:
    rx: Event
    event: Event
    error: Event
    debug: Event


class SimulatedSerial:
    """Mock of BILBO_Serial_Communication that routes commands to SimulatedFirmware."""

    def __init__(self, firmware: SimulatedFirmware):
        self._fw = firmware
        self.callbacks = _SimSerialCallbacks()
        self.events = _SimSerialEvents()

    # ── Lifecycle ─────────────────────────────────────────────────────
    def init(self): pass
    def start(self): pass
    def close(self): pass

    def addMessage(self, messages):
        """Accept message registration (no-op in simulation)."""
        pass

    # ── Register protocol ─────────────────────────────────────────────

    def readValue(self, address: int, module: int = 0, type=ctypes.c_uint8):
        """Read a register value from simulated firmware."""
        if address == BILBO_ControlAddresses.READ_MODE:
            return int(self._fw.mode)
        logger.warning(f"readValue: unhandled address 0x{address:02X}")
        return None

    def writeValue(self, module: int = 0, address: int | list = None, value=None, type=ctypes.c_uint8):
        """Write a register value to simulated firmware."""
        if address == BILBO_ControlAddresses.RW_MAX_WHEEL_SPEED:
            # Not critical for simulation
            return
        logger.warning(f"writeValue: unhandled address 0x{address:02X}")

    def executeFunction(self, address, module: int = 0, data=None,
                        input_type=None, output_type=None, timeout=1):
        """Execute a firmware function. Routes to SimulatedFirmware methods."""
        try:
            return self._handle_function(address, data, input_type, output_type)
        except Exception as e:
            logger.error(f"executeFunction error at 0x{address:02X}: {e}")
            return None

    def readTick(self):
        return self._fw.tick

    def readFirmwareRevision(self):
        return {'major': 99, 'minor': 0}

    def readFirmwareInfo(self):
        return {'board_revision': 4, 'model': 0, 'drive_interface': 2}

    def debug(self, state):
        pass

    # ── Event dispatching (called by SimulatedCommunication) ──────────

    def dispatch_event(self, message):
        """Dispatch a firmware event to registered callbacks (mirrors real serial)."""
        for callback in self.callbacks.event:
            msgs = callback.parameters.get('messages')
            if msgs is not None:
                if type(message) in msgs:
                    callback(message)
            else:
                callback(message)

    # ── Internal routing ──────────────────────────────────────────────

    def _handle_function(self, address: int, data, input_type, output_type):
        fw = self._fw

        # === SYSTEM ===
        if address == BILBO_SystemAddresses.FIRMWARE_RESET:
            return fw.firmware_reset()

        if address == BILBO_SystemAddresses.DRIVE_RESET:
            # In simulation, drive is always OK - just acknowledge
            return True

        # === CONTROL ===
        if address == BILBO_ControlAddresses.SET_MODE:
            fw.set_mode(_val(data, input_type))
            return True

        if address == BILBO_ControlAddresses.SET_K:
            K = _extract_k(data)
            fw.set_K(K)
            return True

        if address == BILBO_ControlAddresses.SET_BALANCING_INPUT:
            u_left = _get(data, 'u_left', 0.0)
            u_right = _get(data, 'u_right', 0.0)
            fw.set_external_input(u_left, u_right)
            return True

        if address == BILBO_ControlAddresses.SET_SPEED_INPUT:
            v = _get(data, 'v', 0.0)
            psi_dot = _get(data, 'psi_dot', 0.0)
            fw.set_velocity_command(v, psi_dot)
            return True

        if address == BILBO_ControlAddresses.SET_VELOCITY_CONFIG_V:
            fw.set_velocity_config_v_pid(_pid_config(data))
            return True

        if address == BILBO_ControlAddresses.SET_VELOCITY_CONFIG_V_FF:
            fw.set_velocity_config_v_ff(_ff_config(data))
            return True

        if address == BILBO_ControlAddresses.SET_VELOCITY_CONFIG_PSIDOT:
            fw.set_velocity_config_psidot_pid(_pid_config(data))
            return True

        if address == BILBO_ControlAddresses.SET_VELOCITY_CONFIG_PSIDOT_FF:
            fw.set_velocity_config_psidot_ff(_ff_config(data))
            return True

        if address == BILBO_ControlAddresses.SET_POSITION_CONFIG:
            fw.set_position_config(_pos_config(data))
            return True

        if address == BILBO_ControlAddresses.SET_TIC_CONFIG:
            fw.set_tic_config(_tic_config(data))
            return True

        if address == BILBO_ControlAddresses.SET_VIC_CONFIG:
            fw.set_vic_config(_vic_config(data))
            return True

        if address == BILBO_ControlAddresses.SET_MAX_TORQUE:
            fw.set_max_torque(float(_val(data, input_type)))
            return True

        if address == BILBO_ControlAddresses.ENABLE_TIC:
            fw.set_tic_enabled(bool(_val(data, input_type)))
            return True

        if address == BILBO_ControlAddresses.ENABLE_VIC:
            fw.set_vic_enabled(bool(_val(data, input_type)))
            return True

        if address == BILBO_ControlAddresses.SET_PSI_CONFIG:
            fw.set_psi_config(_psi_config(data))
            return True

        if address == BILBO_ControlAddresses.ENABLE_PSI:
            fw.set_psi_enabled(bool(_val(data, input_type)))
            return True

        if address == BILBO_ControlAddresses.SET_PSI_SETPOINT:
            fw.set_psi_setpoint(float(_val(data, input_type)))
            return True

        # === POSITION CONTROL ===
        if address == BILBO_PositionControlAddresses.SET_CONFIG:
            fw.set_position_config(_pos_config(data))
            return True

        if address == BILBO_PositionControlAddresses.CLEAR_PATH:
            fw.pc_clear_path()
            return True

        if address == BILBO_PositionControlAddresses.ADD_PATH_POINT:
            fw.pc_add_path_point(_get(data, 'x', 0.0), _get(data, 'y', 0.0))
            return True

        if address == BILBO_PositionControlAddresses.ADD_PATH_BATCH:
            count = _get(data, 'count', 0)
            start_index = _get(data, 'start_index', 0)
            points_arr = getattr(data, 'points', None)
            if points_arr is not None:
                for i in range(int(count)):
                    pt = points_arr[i]
                    fw.pc_add_path_point(float(pt.x), float(pt.y))
            return True

        if address == BILBO_PositionControlAddresses.ADD_STOP_INDEX:
            idx = int(_val(data, input_type))
            fw.pc_add_stop_index(idx)
            return True

        if address == BILBO_PositionControlAddresses.START_PATH:
            fw.pc_start_path(
                max_speed=_get(data, 'max_speed', 0.0),
                max_spacing=_get(data, 'max_spacing', 0.0),
                timeout=_get(data, 'timeout', 0.0),
                allow_reverse=bool(_get(data, 'allow_reverse', False)),
            )
            return True

        if address == BILBO_PositionControlAddresses.PAUSE_PATH:
            fw.pc_pause_path()
            return True

        if address == BILBO_PositionControlAddresses.RESUME_PATH:
            fw.pc_resume_path()
            return True

        if address == BILBO_PositionControlAddresses.ABORT_PATH:
            fw.pc_abort_path()
            return True

        if address == BILBO_PositionControlAddresses.READ_PATH_STATE:
            return int(fw.position_control.path_state)

        if address == BILBO_PositionControlAddresses.READ_DATA:
            return _pc_data_to_dict(fw.position_control.get_data())

        if address == BILBO_PositionControlAddresses.READ_PATH_POINT_COUNT:
            return fw.position_control.path_point_count

        if address == BILBO_PositionControlAddresses.TURN_TO_HEADING:
            fw.pc_turn_to_heading(
                heading=_get(data, 'heading_ref', 0.0),
                timeout=_get(data, 'timeout', 0.0),
                max_angular_speed=_get(data, 'max_angular_speed', 0.0),
                cmd_id=int(_get(data, 'id', 0)),
            )
            return True

        if address == BILBO_PositionControlAddresses.MOVE_TO_POINT:
            fw.pc_move_to_point(
                x=_get(data, 'x_target', 0.0),
                y=_get(data, 'y_target', 0.0),
                timeout=_get(data, 'timeout', 0.0),
                max_speed=_get(data, 'max_speed', 0.0),
                cmd_id=int(_get(data, 'id', 0)),
            )
            return True

        if address == BILBO_PositionControlAddresses.RESET:
            fw.pc_reset()
            return True

        # === ESTIMATION ===
        if address == BILBO_EstimationAddresses.SET_THETA_OFFSET:
            fw.set_theta_offset(float(_val(data, input_type)))
            return True

        if address == BILBO_EstimationAddresses.SET_POSITION_STATE:
            fw.set_position_state(
                x=_get(data, 'x', 0.0),
                y=_get(data, 'y', 0.0),
                psi=_get(data, 'psi', 0.0),
            )
            return True

        if address == BILBO_EstimationAddresses.SET_POSITION_UPDATE:
            fw.set_position_update(
                x=_get(data, 'x', 0.0),
                y=_get(data, 'y', 0.0),
                psi=_get(data, 'psi', 0.0),
            )
            return True

        if address == BILBO_EstimationAddresses.RESET:
            fw.firmware_reset()
            return True

        if address == BILBO_EstimationAddresses.SET_DEAD_RECKONING_ENABLE:
            fw.set_dead_reckoning_enabled(bool(_val(data, input_type)))
            return True

        if address in (BILBO_EstimationAddresses.GET_VELOCITY_LPF,
                       BILBO_EstimationAddresses.GET_PSIDOT_LPF,
                       BILBO_EstimationAddresses.GET_THETA_DOT_LPF):
            # Return a mock config - simulation doesn't use these filters
            return {'enable': False, 'cutoff_hz': 10.0, 'reset_on_start': False}

        if address in (BILBO_EstimationAddresses.SET_VELOCITY_LPF,
                       BILBO_EstimationAddresses.SET_PSIDOT_LPF,
                       BILBO_EstimationAddresses.SET_THETA_DOT_LPF):
            # Accept but ignore - simulation doesn't use these filters
            return True

        if address == BILBO_EstimationAddresses.GET_CONFIG:
            # Return a mock full estimation config
            return {}

        if address == BILBO_EstimationAddresses.SET_CONFIG:
            # Accept but ignore
            return True

        logger.warning(f"executeFunction: unhandled address 0x{address:02X}")
        return True


# ─── Simulated SPI ────────────────────────────────────────────────────────────

class SimulatedSPI:
    """Mock of BILBO_SPI_Interface."""

    def __init__(self, firmware: SimulatedFirmware = None):
        self._firmware = firmware
        self.callbacks = type('SPICallbacks', (), {
            'rx_latest_sample': CallbackContainer(),
            'rx_samples': CallbackContainer(),
        })()

    def init(self): pass
    def start(self): pass
    def close(self, *args, **kwargs): pass
    def startSampleListener(self): pass

    def sendTrajectoryData(self, trajectory_length, trajectory_data_bytes):
        logger.debug(f"sendTrajectoryData: {trajectory_length} points (ignored in simulation)")

    def sendPathData(self, path_length: int, path_data_bytes: bytes | bytearray):
        """Decode path_point_t array and forward to simulated firmware."""
        if self._firmware is None:
            return
        from robot.lowlevel.stm32_control import path_point_t
        ArrayType = path_point_t * path_length
        c_array = ArrayType.from_buffer_copy(path_data_bytes)
        for i in range(path_length):
            self._firmware.pc_add_path_point(float(c_array[i].x), float(c_array[i].y))


# ─── Main SimulatedCommunication ──────────────────────────────────────────────

class SimulatedCommunication:
    """Drop-in replacement for BILBO_Communication in simulation mode.

    Routes all serial register calls to a SimulatedFirmware and bridges
    firmware samples/events to the BILBO callback/event system.
    """

    def __init__(self, core: BILBO_Common, model_yaml_path: str | None = None):
        self.core = core
        self._firmware = SimulatedFirmware(model_yaml_path=model_yaml_path)

        self.serial = SimulatedSerial(self._firmware)
        self.spi = SimulatedSPI(self._firmware)
        self.wifi = BILBO_WIFI_Interface(core=self.core)

        self.callbacks = SimulatedCommunication_Callbacks()
        self.events = SimulatedCommunication_Events()

        # Buffer to accumulate samples into batches of 10 (matching real SPI behavior)
        self._sample_buffer: list[dict] = []

    @property
    def firmware(self) -> SimulatedFirmware:
        """Access to the underlying firmware simulation (for testing/debugging)."""
        return self._firmware

    # ── Lifecycle ─────────────────────────────────────────────────────

    def init(self):
        logger.info("SimulatedCommunication initialized")

    def start(self):
        self._firmware.start(
            sample_callback=self._on_firmware_sample,
            event_callback=self._on_firmware_event,
        )
        self.wifi.start()
        logger.info("SimulatedCommunication started (firmware running at 100 Hz)")

    def startSampleListener(self):
        # Already started in start() - nothing extra needed
        pass

    def close(self, *args, **kwargs):
        logger.info("Closing SimulatedCommunication")
        self._firmware.stop()

    # ── Firmware callbacks ────────────────────────────────────────────

    def _on_firmware_sample(self, sample: BILBO_LL_Sample):
        """Called by firmware thread at 100 Hz with new sample."""
        # Buffer samples into batches of 10 (matching real SPI: 100 Hz firmware / 10 Hz read)
        self._sample_buffer.append(asdict_optimized(sample))

        if len(self._sample_buffer) >= 10:
            batch = self._sample_buffer
            self._sample_buffer = []

            for callback in self.spi.callbacks.rx_samples:
                callback(batch)

            # Execute registered callbacks with the latest sample
            for callback in self.callbacks.rx_stm32_sample:
                callback(sample)

            # Set events
            self.events.rx_stm32_sample.set(sample)
            self.events.stm32_tick.set(sample.tick)

    def _on_firmware_event(self, event_type: str, event_data: dict):
        """Called by firmware thread when a control/position event fires."""
        if event_type == 'control':
            self._dispatch_control_event(event_data)
        elif event_type == 'position_control':
            self._dispatch_position_control_event(event_data)

    def _dispatch_control_event(self, event_data: dict):
        """Create and dispatch a BILBO_Control_Event_Message."""
        msg = BILBO_Control_Event_Message()
        msg.data = event_data
        self.serial.dispatch_event(msg)

    def _dispatch_position_control_event(self, event_data: dict):
        """Create and dispatch a BILBO_PositionControl_Event_Message."""
        msg = BILBO_PositionControl_Event_Message()
        msg.data = event_data
        self.serial.dispatch_event(msg)


# ─── Data extraction helpers ──────────────────────────────────────────────────

def _get(data, key: str, default=0.0):
    """Get a value from a ctypes struct or dict."""
    if data is None:
        return default
    if isinstance(data, dict):
        return data.get(key, default)
    if hasattr(data, key):
        val = getattr(data, key)
        # Convert ctypes values to Python
        if hasattr(val, 'value'):
            return val.value
        return val
    return default


def _val(data, input_type=None):
    """Extract a simple scalar value from data."""
    if data is None:
        return 0
    if isinstance(data, (int, float, bool)):
        return data
    if hasattr(data, 'value'):
        return data.value
    return data


def _extract_k(data) -> list[float]:
    """Extract 8-element K gain list."""
    if isinstance(data, list):
        return [float(x) for x in data]
    if isinstance(data, (tuple, range)):
        return [float(x) for x in data]
    # ctypes array
    if hasattr(data, '__len__') and len(data) == 8:
        return [float(data[i]) for i in range(8)]
    return [0.0] * 8


def _pid_config(data) -> PIDConfig:
    """Convert ctypes pid_control_config_t or dict to PIDConfig."""
    return PIDConfig(
        Kp=float(_get(data, 'Kp', 0.0)),
        Ki=float(_get(data, 'Ki', 0.0)),
        Kd=float(_get(data, 'Kd', 0.0)),
        Ts=float(_get(data, 'Ts', 0.01)),
        enable_i_limit=bool(_get(data, 'enable_i_limit', False)),
        i_term_limit=float(_get(data, 'i_term_limit', 0.0)),
        enable_input_limit=bool(_get(data, 'enable_input_limit', False)),
        input_limit=float(_get(data, 'input_limit', 0.0)),
        enable_output_limit=bool(_get(data, 'enable_output_limit', False)),
        output_limit=float(_get(data, 'output_limit', 0.0)),
        enable_d_filter=bool(_get(data, 'enable_d_filter', False)),
        Td_filter=float(_get(data, 'Td_filter', 0.0)),
        enable_rate_limit=bool(_get(data, 'enable_rate_limit', False)),
        rate_limit=float(_get(data, 'rate_limit', 0.0)),
        enable_setpoint_rate_limit=bool(_get(data, 'enable_setpoint_rate_limit', False)),
        setpoint_rate_limit=float(_get(data, 'setpoint_rate_limit', 0.0)),
    )


def _ff_config(data) -> FeedforwardConfig:
    """Convert ctypes feedforward_config_t or dict to FeedforwardConfig."""
    return FeedforwardConfig(
        Kv=float(_get(data, 'Kv', 0.0)),
        Ka=float(_get(data, 'Ka', 0.0)),
        Kc=float(_get(data, 'Kc', 0.0)),
        Ts=float(_get(data, 'Ts', 0.01)),
        enable_vref_slew=bool(_get(data, 'enable_vref_slew', False)),
        vref_slew_rate=float(_get(data, 'vref_slew_rate', 0.0)),
        enable_a_filter=bool(_get(data, 'enable_a_filter', False)),
        Ta_filter=float(_get(data, 'Ta_filter', 0.0)),
        enable_stiction=bool(_get(data, 'enable_stiction', False)),
        v0_stiction=float(_get(data, 'v0_stiction', 0.0)),
        v_decay_stiction=float(_get(data, 'v_decay_stiction', 0.0)),
        enable_output_limit=bool(_get(data, 'enable_output_limit', False)),
        output_limit=float(_get(data, 'output_limit', 0.0)),
        enable_output_slew=bool(_get(data, 'enable_output_slew', False)),
        output_slew_rate=float(_get(data, 'output_slew_rate', 0.0)),
    )


def _tic_config(data) -> TICConfig:
    """Convert ctypes bilbo_tic_config_t or dict to TICConfig."""
    return TICConfig(
        enabled=bool(_get(data, 'enabled', False)),
        Ts=float(_get(data, 'Ts', 0.01)),
        ki=float(_get(data, 'ki', 0.0)),
        max_torque=float(_get(data, 'max_torque', 0.0)),
        theta_limit=float(_get(data, 'theta_limit', 0.0)),
    )


def _vic_config(data) -> VICConfig:
    """Convert ctypes bilbo_vic_config_t or dict to VICConfig."""
    return VICConfig(
        enabled=bool(_get(data, 'enabled', False)),
        Ts=float(_get(data, 'Ts', 0.01)),
        ki=float(_get(data, 'ki', 0.0)),
        max_torque=float(_get(data, 'max_torque', 0.0)),
        v_limit=float(_get(data, 'v_limit', 0.0)),
        theta_limit=float(_get(data, 'theta_limit', 0.0)),
    )


def _psi_config(data) -> PSIConfig:
    """Convert ctypes bilbo_psi_config_t or dict to PSIConfig."""
    return PSIConfig(
        enabled=bool(_get(data, 'enabled', False)),
        Ts=float(_get(data, 'Ts', 0.01)),
        kp=float(_get(data, 'kp', 0.0)),
        ki=float(_get(data, 'ki', 0.0)),
        max_torque=float(_get(data, 'max_torque', 0.0)),
    )


def _pos_config(data) -> PositionControlConfig:
    """Convert ctypes bilbo_position_control_config_t or dict to PositionControlConfig."""
    return PositionControlConfig(
        Ts=float(_get(data, 'Ts', 0.01)),
        kp_angular=float(_get(data, 'kp_angular', 10.0)),
        ki_angular=float(_get(data, 'ki_angular', 0.3)),
        kp_angular_heading=float(_get(data, 'kp_angular_heading', 0.0)),
        ki_angular_heading=float(_get(data, 'ki_angular_heading', 0.0)),
        kp_linear=float(_get(data, 'kp_linear', 2.0)),
        ki_linear=float(_get(data, 'ki_linear', 0.0)),
        kd_linear=float(_get(data, 'kd_linear', 0.5)),
        max_speed=float(_get(data, 'max_speed', 0.5)),
        max_turn_rate=float(_get(data, 'max_turn_rate', 5.0)),
        lookahead_base=float(_get(data, 'lookahead_base', 0.15)),
        lookahead_min=float(_get(data, 'lookahead_min', 0.03)),
        arrival_tolerance=float(_get(data, 'arrival_tolerance', 0.05)),
        arrival_dwell_time=float(_get(data, 'arrival_dwell_time', 0.5)),
        stop_dwell_time=float(_get(data, 'stop_dwell_time', 1.0)),
        reverse_enter_angle=float(_get(data, 'reverse_enter_angle', 2.1)),
        reverse_exit_angle=float(_get(data, 'reverse_exit_angle', 1.05)),
        decel_limit=float(_get(data, 'decel_limit', 0.0)),
        curvature_gain=float(_get(data, 'curvature_gain', 2.0)),
        curvature_lookahead=float(_get(data, 'curvature_lookahead', 0.3)),
    )


def _pc_data_to_dict(data) -> dict:
    """Convert PositionControlData dataclass to dict matching ctypes layout."""
    d = dataclasses.asdict(data)
    d['output'] = {
        'v_cmd': d.pop('v_cmd', 0.0),
        'psi_dot_cmd': d.pop('psi_dot_cmd', 0.0),
    }
    return d
