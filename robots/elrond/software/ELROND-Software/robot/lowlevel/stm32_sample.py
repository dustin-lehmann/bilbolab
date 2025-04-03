import ctypes
import dataclasses

from robot.lowlevel.stm32_errors import bilbo_ll_log_entry_t, BILBO_LL_Log_Entry, TWIPR_ErrorType

# Samples LL
SAMPLE_BUFFER_LL_SIZE = 10


class bilbo_ll_sample_general_struct(ctypes.Structure):
    _fields_ = [("tick", ctypes.c_uint32),
                ("status", ctypes.c_int8)]


@dataclasses.dataclass
class BILBO_LL_Sample_General:
    tick: int = 0
    status: int = 0
    error: int = 0


class bilbo_ll_sample_errors_struct(ctypes.Structure):
    _fields_ = [("state", ctypes.c_int8),
                ("last_entry", bilbo_ll_log_entry_t), ]


@dataclasses.dataclass
class BILBO_LL_Sample_Errors:
    state: TWIPR_ErrorType = TWIPR_ErrorType.NONE
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
    _fields_ = [("v", ctypes.c_float),
                ("theta", ctypes.c_float),
                ("theta_dot", ctypes.c_float),
                ("psi", ctypes.c_float),
                ("psi_dot", ctypes.c_float)]


@dataclasses.dataclass
class BILBO_LL_Estimation_Data:
    v: float = 0.0
    theta: float = 0.0
    theta_dot: float = 0.0
    psi: float = 0.0
    psi_dot: float = 0.0


class bilbo_ll_sample_estimation_struct(ctypes.Structure):
    _fields_ = [('state', bilbo_ll_estimation_data_struct)]


@dataclasses.dataclass
class BILBO_LL_Sample_Estimation:
    state: BILBO_LL_Estimation_Data = dataclasses.field(default_factory=BILBO_LL_Estimation_Data)


class bilbo_ll_control_external_input_struct(ctypes.Structure):
    _fields_ = [("u_direct_1", ctypes.c_float),
                ("u_direct_2", ctypes.c_float),
                ("u_balancing_1", ctypes.c_float),
                ("u_balancing_2", ctypes.c_float),
                ("u_velocity_forward", ctypes.c_float),
                ("u_velocity_turn", ctypes.c_float),
                ]


@dataclasses.dataclass
class BILBO_LL_Control_External_Input:
    u_direct_1: float = 0.0
    u_direct_2: float = 0.0
    u_balancing_1: float = 0.0
    u_balancing_2: float = 0.0
    u_velocity_forward: float = 0.0
    u_velocity_turn: float = 0.0


class bilbo_ll_control_data_struct(ctypes.Structure):
    _fields_ = [("input_velocity_forward", ctypes.c_float),
                ("input_velocity_turn", ctypes.c_float),
                ("input_balancing_1", ctypes.c_float),
                ("input_balancing_2", ctypes.c_float),
                ("input_left", ctypes.c_float),
                ("input_right", ctypes.c_float),
                ("output_left", ctypes.c_float),
                ("output_right", ctypes.c_float),
                ]


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


class bilbo_ll_sample_control_struct(ctypes.Structure):
    _fields_ = [('status', ctypes.c_int8),
                ('mode', ctypes.c_int8),
                ("external_input", bilbo_ll_control_external_input_struct),
                ("data", bilbo_ll_control_data_struct),
                ]


@dataclasses.dataclass
class BILBO_LL_Sample_Control:
    status: int = 0
    mode: int = 0
    external_input: BILBO_LL_Control_External_Input = dataclasses.field(default_factory=BILBO_LL_Control_External_Input)
    data: BILBO_LL_Control_Data = dataclasses.field(default_factory=BILBO_LL_Control_Data)


class bilbo_ll_sample_sequence_struct(ctypes.Structure):
    _fields_ = [("sequence_id", ctypes.c_uint16),
                ("sequence_tick", ctypes.c_uint32)
                ]


@dataclasses.dataclass
class BILBO_LL_Sample_Sequence:
    sequence_id: int = 0
    sequence_tick: int = 0


class bilbo_ll_sample_debug_struct(ctypes.Structure):
    _fields_ = [("debug1", ctypes.c_uint8),
                ("debug2", ctypes.c_uint8),
                ("debug3", ctypes.c_int8),
                ("debug4", ctypes.c_int8),
                ("debug5", ctypes.c_uint16),
                ("debug6", ctypes.c_int16),
                ("debug7", ctypes.c_float),
                ("debug8", ctypes.c_float),
                ]


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


class bilbo_ll_sample_struct(ctypes.Structure):
    _fields_ = [("general", bilbo_ll_sample_general_struct),
                ("errors", bilbo_ll_sample_errors_struct),
                ("control", bilbo_ll_sample_control_struct),
                ("estimation", bilbo_ll_sample_estimation_struct),
                ("sensors", bilbo_ll_sensor_data_struct),
                ("sequence", bilbo_ll_sample_sequence_struct),
                ("debug", bilbo_ll_sample_debug_struct), ]


@dataclasses.dataclass
class BILBO_LL_Sample:
    general: BILBO_LL_Sample_General = dataclasses.field(default_factory=BILBO_LL_Sample_General)
    errors: BILBO_LL_Sample_Errors = dataclasses.field(default_factory=BILBO_LL_Sample_Errors)
    control: BILBO_LL_Sample_Control = dataclasses.field(default_factory=BILBO_LL_Sample_Control)
    estimation: BILBO_LL_Sample_Estimation = dataclasses.field(default_factory=BILBO_LL_Sample_Estimation)
    sensors: BILBO_LL_Sensor_Data = dataclasses.field(default_factory=BILBO_LL_Sensor_Data)
    sequence: BILBO_LL_Sample_Sequence = dataclasses.field(default_factory=BILBO_LL_Sample_Sequence)
    debug: BILBO_LL_Sample_Debug = dataclasses.field(default_factory=BILBO_LL_Sample_Debug)
