import ctypes
import dataclasses

from robot.lowlevel.stm32_control import bilbo_ll_control_data_t, bilbo_ll_control_data
from robot.lowlevel.stm32_errors import bilbo_ll_log_entry_t, BILBO_LL_Log_Entry, BILBO_ErrorType

# Samples LL
SAMPLE_BUFFER_LL_SIZE = 10
MAX_PENDING_BATCHES = 4


class bilbo_ll_sample_general_struct(ctypes.Structure):
    _fields_ = [
        ("status", ctypes.c_int8),
    ]


@dataclasses.dataclass
class BILBO_LL_Sample_General:
    status: int = 0


class bilbo_ll_sample_errors_struct(ctypes.Structure):
    _fields_ = [("state", ctypes.c_uint8),
                ("last_entry", bilbo_ll_log_entry_t), ]


@dataclasses.dataclass
class BILBO_LL_Sample_Errors:
    state: BILBO_ErrorType = BILBO_ErrorType.NONE
    last_entry: BILBO_LL_Log_Entry = dataclasses.field(default_factory=BILBO_LL_Log_Entry)


class bilbo_ll_gyr_data_struct(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float),
                ("y", ctypes.c_float),
                ("z", ctypes.c_float)]


@dataclasses.dataclass
class BILBO_LL_GYR_Data:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class bilbo_ll_acc_data_struct(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float),
                ("y", ctypes.c_float),
                ("z", ctypes.c_float)]


@dataclasses.dataclass
class BILBO_LL_Acc_Data:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class bilbo_ll_sensor_data_struct(ctypes.Structure):
    _fields_ = [("speed_left", ctypes.c_float),
                ("speed_right", ctypes.c_float),
                ("acc", bilbo_ll_acc_data_struct),
                ("gyr", bilbo_ll_gyr_data_struct),
                ("battery_voltage", ctypes.c_float)]


@dataclasses.dataclass
class BILBO_LL_Sensor_Data:
    speed_left: float = 0.0
    speed_right: float = 0.0
    acc: BILBO_LL_Acc_Data = dataclasses.field(default_factory=BILBO_LL_Acc_Data)
    gyr: BILBO_LL_GYR_Data = dataclasses.field(default_factory=BILBO_LL_GYR_Data)
    battery_voltage: float = 0.0


class bilbo_ll_estimation_data_struct(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float),
                ("y", ctypes.c_float),
                ("v", ctypes.c_float),
                ("theta", ctypes.c_float),
                ("theta_dot", ctypes.c_float),
                ("psi", ctypes.c_float),
                ("psi_dot", ctypes.c_float)]


@dataclasses.dataclass
class BILBO_LL_Estimation_Data:
    x: float = 0.0
    y: float = 0.0
    v: float = 0.0
    theta: float = 0.0
    theta_dot: float = 0.0
    psi: float = 0.0
    psi_dot: float = 0.0


class bilbo_ll_sample_estimation_struct(ctypes.Structure):
    _fields_ = [('state', bilbo_ll_estimation_data_struct),
                ('is_dead_reckoning', ctypes.c_bool)]


@dataclasses.dataclass
class BILBO_LL_Sample_Estimation:
    state: BILBO_LL_Estimation_Data = dataclasses.field(default_factory=BILBO_LL_Estimation_Data)
    is_dead_reckoning: bool = False


# LPF Config Types for Estimation
class velocity_lowpass_filter_config_t(ctypes.Structure):
    _fields_ = [
        ("enable", ctypes.c_bool),
        ("cutoff_hz", ctypes.c_float),
        ("reset_on_start", ctypes.c_bool),
    ]


@dataclasses.dataclass
class VelocityLowpassFilterConfig:
    enable: bool = True
    cutoff_hz: float = 30.0
    reset_on_start: bool = True


class theta_dot_lowpass_filter_config_t(ctypes.Structure):
    _fields_ = [
        ("enable", ctypes.c_bool),
        ("cutoff_hz", ctypes.c_float),
        ("reset_on_start", ctypes.c_bool),
    ]


@dataclasses.dataclass
class ThetaDotLowpassFilterConfig:
    enable: bool = True
    cutoff_hz: float = 30.0
    reset_on_start: bool = True


class psi_dot_lowpass_filter_config_t(ctypes.Structure):
    _fields_ = [
        ("enable", ctypes.c_bool),
        ("cutoff_hz", ctypes.c_float),
        ("reset_on_start", ctypes.c_bool),
    ]


@dataclasses.dataclass
class PsiDotLowpassFilterConfig:
    enable: bool = True
    cutoff_hz: float = 30.0
    reset_on_start: bool = True


class position_ekf_config_t(ctypes.Structure):
    _fields_ = [
        ("enable", ctypes.c_bool),
        ("std_dev_position", ctypes.c_float),
        ("std_dev_psi", ctypes.c_float),
        ("sigma_v_base", ctypes.c_float),
        ("sigma_v_scale", ctypes.c_float),
        ("sigma_psi_dot_base", ctypes.c_float),
        ("sigma_psi_dot_scale", ctypes.c_float),
        ("min_position_variance", ctypes.c_float),
        ("min_psi_variance", ctypes.c_float),
        ("dead_reckoning_timeout", ctypes.c_uint16),
    ]


@dataclasses.dataclass
class PositionEkfConfig:
    enable: bool = True
    std_dev_position: float = 0.0005
    std_dev_psi: float = 0.005
    sigma_v_base: float = 0.10
    sigma_v_scale: float = 0.10
    sigma_psi_dot_base: float = 0.15
    sigma_psi_dot_scale: float = 0.15
    min_position_variance: float = 0.0001
    min_psi_variance: float = 0.001
    dead_reckoning_timeout: int = 10


class bilbo_estimation_config_t(ctypes.Structure):
    _fields_ = [
        ("velocity_filter_config", velocity_lowpass_filter_config_t),
        ("theta_dot_filter_config", theta_dot_lowpass_filter_config_t),
        ("psi_dot_filter_config", psi_dot_lowpass_filter_config_t),
        ("position_ekf_config", position_ekf_config_t),
    ]


@dataclasses.dataclass
class EstimationConfig:
    velocity_filter_config: VelocityLowpassFilterConfig = dataclasses.field(default_factory=VelocityLowpassFilterConfig)
    theta_dot_filter_config: ThetaDotLowpassFilterConfig = dataclasses.field(
        default_factory=ThetaDotLowpassFilterConfig)
    psi_dot_filter_config: PsiDotLowpassFilterConfig = dataclasses.field(default_factory=PsiDotLowpassFilterConfig)
    position_ekf_config: PositionEkfConfig = dataclasses.field(default_factory=PositionEkfConfig)


class bilbo_ll_sample_drive_struct(ctypes.Structure):
    _fields_ = [
        ("status", ctypes.c_uint8),
        ("motor_mode_left", ctypes.c_uint8),
        ("motor_mode_right", ctypes.c_uint8),
    ]


@dataclasses.dataclass
class BILBO_LL_Sample_Drive:
    status: int = 0
    motor_mode_left: int = 0
    motor_mode_right: int = 0


class bilbo_ll_sample_sequence_struct(ctypes.Structure):
    _fields_ = [
        ("mode", ctypes.c_uint8),
        ("sequence_id", ctypes.c_uint16),
        ("sequence_tick", ctypes.c_uint32)
    ]


@dataclasses.dataclass
class BILBO_LL_Sample_Sequence:
    mode: int = 0
    sequence_id: int = 0
    sequence_tick: int = 0

class bilbo_ll_sample_debug_struct(ctypes.Structure):
    _fields_ = [("debug1", ctypes.c_uint8),
                # ("debug2", ctypes.c_uint8),
                # ("debug3", ctypes.c_int8),
                # ("debug4", ctypes.c_int8),
                # ("debug5", ctypes.c_uint16),
                # ("debug6", ctypes.c_int16),
                # ("debug7", ctypes.c_float),
                # ("debug8", ctypes.c_float),
                ]


@dataclasses.dataclass
class BILBO_LL_Sample_Debug:
    debug1: int = 0
    # debug2: int = 0
    # debug3: int = 0
    # debug4: int = 0
    # debug5: int = 0
    # debug6: int = 0
    # debug7: float = 0.0
    # debug8: float = 0.0


class bilbo_ll_sample_struct(ctypes.Structure):
    _fields_ = [
        ("tick", ctypes.c_uint32),
        ("general", bilbo_ll_sample_general_struct),
        ("errors", bilbo_ll_sample_errors_struct),
        ("control", bilbo_ll_control_data_t),
        ("estimation", bilbo_ll_sample_estimation_struct),
        ("sensors", bilbo_ll_sensor_data_struct),
        ("drive", bilbo_ll_sample_drive_struct),
        ("sequence", bilbo_ll_sample_sequence_struct),
        ("debug", bilbo_ll_sample_debug_struct),
    ]


@dataclasses.dataclass
class BILBO_LL_Sample:
    tick: int = 0
    general: BILBO_LL_Sample_General = dataclasses.field(default_factory=BILBO_LL_Sample_General)
    errors: BILBO_LL_Sample_Errors = dataclasses.field(default_factory=BILBO_LL_Sample_Errors)
    control: bilbo_ll_control_data = dataclasses.field(default_factory=bilbo_ll_control_data)
    estimation: BILBO_LL_Sample_Estimation = dataclasses.field(default_factory=BILBO_LL_Sample_Estimation)
    sensors: BILBO_LL_Sensor_Data = dataclasses.field(default_factory=BILBO_LL_Sensor_Data)
    drive: BILBO_LL_Sample_Drive = dataclasses.field(default_factory=BILBO_LL_Sample_Drive)
    sequence: BILBO_LL_Sample_Sequence = dataclasses.field(default_factory=BILBO_LL_Sample_Sequence)
    debug: BILBO_LL_Sample_Debug = dataclasses.field(default_factory=BILBO_LL_Sample_Debug)
