import ctypes
import dataclasses
import enum


class TWIPR_ErrorType(enum.IntEnum):
    NONE = 0,
    MINOR = 1,
    MAJOR = 2,
    CRITICAL = 3,


class TWIPR_ErrorCodes(enum.IntEnum):
    UNSPECIFIED = 0,
    WHEEL_SPEED = 1,
    MANUAL_STOP = 2,
    INIT = 3,
    START = 4,
    IMU_INITIALIZE = 5,
    MOTOR_RACECONDITIONS = 6,
    FIRMWARE_RACECONDITION = 7


class bilbo_ll_log_entry_t(ctypes.Structure):
    _fields_ = [("tick", ctypes.c_uint32),
                ("type", ctypes.c_int8),
                ("error", ctypes.c_int8)]


@dataclasses.dataclass
class BILBO_LL_Log_Entry:
    tick: int = 0
    type: TWIPR_ErrorType = TWIPR_ErrorType.NONE
    error: TWIPR_ErrorCodes = TWIPR_ErrorCodes.UNSPECIFIED
