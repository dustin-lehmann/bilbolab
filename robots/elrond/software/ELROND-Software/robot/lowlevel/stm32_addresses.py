import enum
import ctypes
import dataclasses


class TWIPR_AddressTables(enum.IntEnum):
    REGISTER_TABLE_GENERAL = 0x01

class EXO_mab_motor_mode_t(enum.IntEnum):
	MAB_MOTOR_MODE_IDLE = 0x00
	MAB_MOTOR_MODE_POS_PID = 0x01
	MAB_MOTOR_MODE_VELOCITY_PID = 0x02
	MAB_MOTOR_MODE_RAW_TORQUE = 0x03
	MAB_MOTOR_MODE_IMPEDANCE = 0x04
	MAB_MOTOR_MODE_POSITION_PROFILE = 0x05
	MAB_MOTOR_MODE_VELOCITY_PROFILE = 0x06

class EXO_mab_motor_speed_calculated_struct(ctypes.Structure):
    _fields_ = [("speed", ctypes.c_float),
                ("pos", ctypes.c_float)]


@dataclasses.dataclass
class EXO_mab_motor_speed_calculated_t:
    speed: float = 0
    pos: float = 0

class EXO_mab_motor_impedance_const_struct(ctypes.Structure):
    _fields_ = [("kp", ctypes.c_float),
                ("kd", ctypes.c_float)]


@dataclasses.dataclass
class EXO_mab_motor_impedance_const_t:
    kp: float = 0
    kd: float = 0
    

class EXO_mab_motor_config_struct(ctypes.Structure):
    _fields_ = [("tick", ctypes.c_uint32),
                ("status", ctypes.c_int8),
                ("can", ctypes.c_uint32), 
                ("drive_id", ctypes.c_uint32),
                ("direction", ctypes.c_int8),
                ("can_watchdog_timeout", ctypes.c_uint16),
                ("torque_limit", ctypes.c_float),
                ("velocity_limit", ctypes.c_float)]


@dataclasses.dataclass
class EXO_mab_motor_config_t:
    can: int = 0
    drive_id: int = 0
    direction: int = 0
    can_watchdog_timeout: int = 500
    torque_limit: float = 1.75
    velocity_limit: float = 140.0


class EXO_MotorAddresses(enum.IntEnum):
    EXO_MOTOR_INIT = 0x42
    EXO_MOTOR_START = 0x43
    EXO_MOTOR_STOP = 0x44
    EXO_MOTOR_CHECK_COMMUNICATION = 0x45
    EXO_MOTOR_CHECK_MOTOR = 0x46
    EXO_MOTOR_BEEP = 0x47
    EXO_MOTOR_CLEAR_ERRORS = 0x48
    EXO_MOTOR_CLEAR_WARNINGS = 0x49
    EXO_MOTOR_RESET_MOTOR = 0x4A
    EXO_MOTOR_SET_MODE = 0x4B
    EXO_MOTOR_SET_WATCHDOG = 0x4C
    EXO_MOTOR_SET_VELOCITY_LIMIT = 0x4D
    EXO_MOTOR_SET_TORQUE_LIMIT = 0x4E
    EXO_MOTOR_SET_IMPEDANCE_CONSTS = 0x4F
    EXO_MOTOR_SET_TORQUE = 0x50
    EXO_MOTOR_SET_LED_BLINK = 0x51
    EXO_MOTOR_SET_TARGET_VELOCITY = 0x52
    EXO_MOTOR_SET_TARGET_POSITION = 0x53
    EXO_MOTOR_READ_MODE = 0x54
    EXO_MOTOR_READ_SPEED = 0x55
    EXO_MOTOR_READ_SPEED_CALCULATED = 0x56
    EXO_MOTOR_READ_POSITION = 0x57
    EXO_MOTOR_GET_TEMPERATURE = 0x58
    EXO_MOTOR_GET_VOLTAGE = 0x59

class TWIPR_GeneralAddresses(enum.IntEnum):
    ADDRESS_FIRMWARE_STATE = 0x01
    ADDRESS_FIRMWARE_TICK = 0x02
    ADDRESS_FIRMWARE_REVISION = 0x03
    ADDRESS_FIRMWARE_DEBUG = 0x04
    ADDRESS_FIRMWARE_BEEP = 0x05
    ADDRESS_BOARD_REVISION = 0x06
    ADDRESS_FIRMWARE_EXTERNAL_LED = 0x07
    ADDRESS_FIRMWARE_DEBUG_1_FLAG = 0x08

    ADDRESS_FIRMWARE_RESET = 0xF1


class TWIPR_ControlAddresses(enum.IntEnum):
    ADDRESS_CONTROL_READ_MODE = 0x10
    ADDRESS_CONTROL_SET_MODE = 0x11
    ADDRESS_CONTROL_SET_K = 0x12
    ADDRESS_CONTROL_SET_FORWARD_PID = 0x13
    ADDRESS_CONTROL_SET_TURN_PID = 0x14
    ADDRESS_CONTROL_SET_DIRECT_INPUT = 0x15
    ADDRESS_CONTROL_SET_BALANCING_INPUT = 0x16
    ADDRESS_CONTROL_SET_SPEED_INPUT = 0x17
    ADDRESS_CONTROL_READ_CONFIG = 0x18

    SET_CONFIG = 0x19

    ADDRESS_CONTROL_RW_MAX_WHEEL_SPEED = 0x20

    ENABLE_VELOCITY_INTEGRAL_CONTROL = 0x31

class TWIPR_ActuatorAddresses(enum.IntEnum):
    ADDRESS_ACTUATOR_SET_TORQUE_SINGLE = 0x43
    ADDRESS_ACTUATOR_SEND_PING_SINGLE = 0x44
    ADDRESS_ACTUATOR_SET_LED_SINGLE = 0x45
    ADDRESS_ACTUATOR_SET_POSITION_SINGLE = 0x46

    ADDRESS_ACTUATOR_GET_VOLTAGE_SINGLE = 0x4A
    ADDRESS_ACTUATOR_GET_TEMPERATURE_SINGLE = 0x4B
    ADDRESS_ACTUATORS_GET_GOAL_POSITION_SINGLE = 0x4C
    ADDRESS_ACTUATORS_GET_PRESENT_POSITION_SINGLE = 0x4D

    ADDRESS_ACTUATORS_SET_TORQUE_ALL = 0x52
    ADDRESS_ACTUATORS_SET_LED_ALL = 0x53
    ADDRESS_ACTUATORS_SET_POSITION_ALL = 0x54

    ADDRESS_ACTUATORS_GET_VOLTAGE_ALL = 0x57
    ADDRESS_ACTUATORS_GET_TEMPERATURE_ALL = 0x58
    ADDRESS_ACTUATORS_GET_GOAL_POSITION_ALL = 0x59
    ADDRESS_ACTUATORS_GET_PRESENT_POSITION_ALL = 0x5A

class TWIPR_EstimationAddresses(enum.IntEnum):
    SET_THETA_OFFSET = 0x50

class TWIPR_SequencerAddresses(enum.IntEnum):
    LOAD = 0x21
    START = 0x22
    STOP = 0x23
    READ = 0x24
