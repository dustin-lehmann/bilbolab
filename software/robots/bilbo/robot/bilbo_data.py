import dataclasses
import enum
import math

import dacite
from dacite import from_dict

from core.utils.dataclass_utils import from_dict_auto
from robots.bilbo.definitions import BILBO_DynamicState
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_Control_Status, BILBO_Control_Inputs


@dataclasses.dataclass
class BILBO_LL_Sample_General:
    tick: int = 0
    status: int = 0


class BILBO_ErrorType(enum.IntEnum):
    # Must match firmware bilbo_error_type_t : uint8_t
    NONE = 0
    WARNING = 1
    MINOR = 2
    MAJOR = 3
    CRITICAL = 4


class BILBO_ErrorCodes(enum.IntEnum):
    # Must match firmware bilbo_error_t : uint8_t
    UNSPECIFIED = 0
    WHEEL_SPEED = 1
    MANUAL_STOP = 2
    INIT = 3
    START = 4
    IMU_INITIALIZE = 5
    MOTOR_RACECONDITIONS = 6
    FIRMWARE_RACECONDITION = 7
    MOTOR_COMM = 8


@dataclasses.dataclass
class BILBO_LL_Log_Entry:
    tick: int = 0
    type: BILBO_ErrorType = BILBO_ErrorType.NONE
    error: BILBO_ErrorCodes = BILBO_ErrorCodes.UNSPECIFIED


@dataclasses.dataclass
class BILBO_LL_Sample_Errors:
    state: BILBO_ErrorType = BILBO_ErrorType.NONE
    last_entry: BILBO_LL_Log_Entry = dataclasses.field(default_factory=BILBO_LL_Log_Entry)


@dataclasses.dataclass
class BILBO_LL_GYR_Data:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclasses.dataclass
class BILBO_LL_Acc_Data:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclasses.dataclass
class BILBO_LL_Sensor_Data:
    speed_left: float = 0.0
    speed_right: float = 0.0
    acc: BILBO_LL_Acc_Data = dataclasses.field(default_factory=BILBO_LL_Acc_Data)
    gyr: BILBO_LL_GYR_Data = dataclasses.field(default_factory=BILBO_LL_GYR_Data)
    battery_voltage: float = 0.0


@dataclasses.dataclass
class BILBO_LL_Estimation_Data:
    x: float = 0.0
    y: float = 0.0
    v: float = 0.0
    theta: float = 0.0
    theta_dot: float = 0.0
    psi: float = 0.0
    psi_dot: float = 0.0


@dataclasses.dataclass
class BILBO_LL_Sample_Estimation:
    state: BILBO_LL_Estimation_Data = dataclasses.field(default_factory=BILBO_LL_Estimation_Data)


@dataclasses.dataclass
class BILBO_LL_Control_External_Input:
    u_direct_1: float = 0.0
    u_direct_2: float = 0.0
    u_balancing_1: float = 0.0
    u_balancing_2: float = 0.0
    u_velocity_forward: float = 0.0
    u_velocity_turn: float = 0.0


@dataclasses.dataclass
class BILBO_LL_Control_Data:
    input_velocity_forward: float = 0.0
    input_velocity_turn: float = 0.0
    input_balancing_1: float = 0.0
    input_balancing_2: float = 0.0
    input_left: float = 0.0
    input_right: float = 0.0
    output_left: float = 0.0
    output_right: float = 0.0


@dataclasses.dataclass
class bilbo_position_command:
    x_target: float = 0.0
    y_target: float = 0.0
    psi_target: float = 0.0


@dataclasses.dataclass
class bilbo_position_control_output:
    u_l: float = 0.0
    u_r: float = 0.0


@dataclasses.dataclass
class bilbo_velocity_control_command:
    v: float = 0.0
    psi_dot: float = 0.0


@dataclasses.dataclass
class bilbo_velocity_control_output:
    u_l: float = 0.0
    u_r: float = 0.0


@dataclasses.dataclass
class bilbo_control_input_ext:
    u_left: float = 0.0
    u_right: float = 0.0


@dataclasses.dataclass
class bilbo_balancing_control_output:
    u_1: float = 0.0
    u_2: float = 0.0


@dataclasses.dataclass
class bilbo_control_output:
    u_left: float = 0.0
    u_right: float = 0.0


@dataclasses.dataclass
class bilbo_ll_control_data:
    mode: int = 0
    status: int = 0

    vic_enabled: int = 0
    tic_enabled: int = 0

    position_command: bilbo_position_command = dataclasses.field(default_factory=bilbo_position_command)
    position_output: bilbo_position_control_output = dataclasses.field(default_factory=bilbo_position_control_output)

    velocity_command: bilbo_velocity_control_command = dataclasses.field(default_factory=bilbo_velocity_control_command)
    velocity_output: bilbo_velocity_control_output = dataclasses.field(default_factory=bilbo_velocity_control_output)

    input_ext: bilbo_control_input_ext = dataclasses.field(default_factory=bilbo_control_input_ext)
    balancing_output: bilbo_balancing_control_output = dataclasses.field(default_factory=bilbo_balancing_control_output)

    output: bilbo_control_output = dataclasses.field(default_factory=bilbo_control_output)


@dataclasses.dataclass
class BILBO_LL_Sample_Drive:
    status: int = 0
    motor_mode_left: int = 0
    motor_mode_right: int = 0


@dataclasses.dataclass
class BILBO_LL_Sample_Sequence:
    sequence_id: int = 0
    sequence_tick: int = 0


@dataclasses.dataclass
class BILBO_LL_Sample_Debug:
    debug1: int = 0
    debug2: int = 0
    debug3: int = 0
    debug4: int = 0
    debug5: int = 0
    debug6: int = 0
    debug7: float = 0.0
    debug8: float = 0.0


@dataclasses.dataclass
class BILBO_LL_Sample:
    general: BILBO_LL_Sample_General = dataclasses.field(default_factory=BILBO_LL_Sample_General)
    errors: BILBO_LL_Sample_Errors = dataclasses.field(default_factory=BILBO_LL_Sample_Errors)
    control: bilbo_ll_control_data = dataclasses.field(default_factory=bilbo_ll_control_data)
    estimation: BILBO_LL_Sample_Estimation = dataclasses.field(default_factory=BILBO_LL_Sample_Estimation)
    sensors: BILBO_LL_Sensor_Data = dataclasses.field(default_factory=BILBO_LL_Sensor_Data)
    drive: BILBO_LL_Sample_Drive = dataclasses.field(default_factory=BILBO_LL_Sample_Drive)
    sequence: BILBO_LL_Sample_Sequence = dataclasses.field(default_factory=BILBO_LL_Sample_Sequence)
    debug: BILBO_LL_Sample_Debug = dataclasses.field(default_factory=BILBO_LL_Sample_Debug)


@dataclasses.dataclass
class BILBO_Sample_General:
    status: str = ''
    time: float = 0.0
    time_global: float = 0.0
    tick: int = 0
    connection_strength: float = 0.0
    internet_connected: bool = False
    timecode: str = '00:00:00:00'
    timecode_fps: float = 0.0
    rpi_temperature: float = 0.0
    rpi_throttle: int = 0


@dataclasses.dataclass
class BILBO_ConfigurationState:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    theta: float = 0.0
    psi: float = 0.0


class BILBO_Estimation_Status(enum.IntEnum):
    ERROR = 0,
    NORMAL = 1,


@dataclasses.dataclass(frozen=True)
class BILBO_Estimation_Sample:
    status: BILBO_Estimation_Status = BILBO_Estimation_Status.ERROR
    state: BILBO_DynamicState = dataclasses.field(default_factory=BILBO_DynamicState)
    state_optitrack: BILBO_ConfigurationState | None = dataclasses.field(default_factory=BILBO_ConfigurationState)
    static: bool = False
    is_dead_reckoning: bool = True


class BILBO_Drive_Status(enum.IntEnum):
    BILBO_DRIVE_STATUS_OFF = 1,
    BILBO_DRIVE_STATUS_ERROR = 0
    BILBO_DRIVE_STATUS_NORMAL = 2


@dataclasses.dataclass
class BILBO_Drive_Data:
    status: BILBO_Drive_Status = BILBO_Drive_Status.BILBO_DRIVE_STATUS_OFF
    torque: float = 0
    speed: float = 0
    input: float = 0
    motor_mode: int = 255


@dataclasses.dataclass
class BILBO_Drive_Sample:
    status: BILBO_Drive_Status = BILBO_Drive_Status.BILBO_DRIVE_STATUS_OFF
    left: BILBO_Drive_Data = dataclasses.field(default_factory=BILBO_Drive_Data)
    right: BILBO_Drive_Data = dataclasses.field(default_factory=BILBO_Drive_Data)


@dataclasses.dataclass
class BILBO_Sensors_IMU:
    gyr: dict = dataclasses.field(default_factory=dict)
    acc: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class BILBO_Sensors_Power:
    bat_voltage: float = 0
    bat_current: float = 0


@dataclasses.dataclass(frozen=True)
class BILBO_Sensors_Sample:
    imu: BILBO_Sensors_IMU = dataclasses.field(default_factory=BILBO_Sensors_IMU)
    power: BILBO_Sensors_Power = dataclasses.field(default_factory=BILBO_Sensors_Power)


@dataclasses.dataclass
class BILBO_PositionControl_Sample:
    """Sample data for position control state"""
    mode: int = 0
    mode_name: str = ''
    path_state: int = 0
    path_state_name: str = ''
    path_point_count: int = 0
    current_index: int = 0
    is_busy: bool = False
    data: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class BILBO_Control_Sample:
    status: BILBO_Control_Status = dataclasses.field(default=BILBO_Control_Status(BILBO_Control_Status.NORMAL))
    mode: BILBO_Control_Mode = dataclasses.field(default=BILBO_Control_Mode(BILBO_Control_Mode.OFF))
    input: BILBO_Control_Inputs = dataclasses.field(default_factory=BILBO_Control_Inputs)
    tic_enabled: bool = False
    vic_enabled: bool = False
    psi_enabled: bool = False
    input_enabled: bool = False
    position_control: BILBO_PositionControl_Sample = dataclasses.field(default_factory=BILBO_PositionControl_Sample)


@dataclasses.dataclass(kw_only=True, frozen=True)
class ExperimentSample:
    id: str = ""
    tick: int = -1
    actions: list[str] = dataclasses.field(default_factory=lambda: [""])


@dataclasses.dataclass
class BILBO_ExperimentHandler_Sample:
    status: str = ""
    markers_json: str = ''
    experiment: ExperimentSample = dataclasses.field(default_factory=ExperimentSample)
    experiment_id: str = ""
    trajectory_id: str = ""


@dataclasses.dataclass
class BILBO_Sample:
    tick: int = 0
    time: float = 0.0
    general: BILBO_Sample_General = dataclasses.field(default_factory=BILBO_Sample_General)
    control: BILBO_Control_Sample = dataclasses.field(default_factory=BILBO_Control_Sample)
    estimation: BILBO_Estimation_Sample = dataclasses.field(default_factory=BILBO_Estimation_Sample)
    drive: BILBO_Drive_Sample = dataclasses.field(default_factory=BILBO_Drive_Sample)
    sensors: BILBO_Sensors_Sample = dataclasses.field(default_factory=BILBO_Sensors_Sample)
    lowlevel: BILBO_LL_Sample = dataclasses.field(default_factory=BILBO_LL_Sample)
    experiment: BILBO_ExperimentHandler_Sample = dataclasses.field(default_factory=BILBO_ExperimentHandler_Sample)


type_hooks = {
    BILBO_Control_Mode: BILBO_Control_Mode,
    BILBO_Control_Status: BILBO_Control_Status,
    BILBO_Estimation_Status: BILBO_Estimation_Status,
    BILBO_Drive_Status: BILBO_Drive_Status,
    BILBO_ErrorType: BILBO_ErrorType,
    BILBO_ErrorCodes: BILBO_ErrorCodes
}


def bilboSampleFromDict(dict) -> BILBO_Sample:
    sample = from_dict_auto(BILBO_Sample, dict)
    return sample


BILBO_STATE_DATA_DEFINITIONS = {
    'x': {
        'type': 'float',
        'unit': 'm',
        'max': 3,
        'min': -3,
        'display_resolution': '.1f'
    },
    'y': {
        'type': 'float',
        'unit': 'm',
        'max': 3,
        'min': -3,
        'display_resolution': '.1f'
    },
    'theta': {
        'type': 'float',
        'unit': 'rad',
        'max': math.pi / 2,
        'min': -math.pi / 2,
        'display_resolution': '.1f'
    },
    'theta_dot': {
        'type': 'float',
        'unit': 'rad/s',
        'max': 10,
        'min': -10,
        'display_resolution': '.1f'
    },
    'v': {
        'type': 'float',
        'unit': 'm/s',
        'max': 10,
        'min': -10,
        'display_resolution': '.1f'
    },
    'psi': {
        'type': 'float',
        'unit': 'rad',
        'max': math.pi,
        'min': -math.pi,
        'display_resolution': '.1f'
    },
    'psi_dot': {
        'type': 'float',
        'unit': 'rad/s',
        'max': 10,
        'min': -10,
        'display_resolution': '.1f'
    }
}
