import ctypes
import dataclasses
import enum


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


class bilbo_ll_log_entry_t(ctypes.Structure):
    _fields_ = [("tick", ctypes.c_uint32),
                ("type", ctypes.c_uint8),
                ("error", ctypes.c_uint8)]


@dataclasses.dataclass
class BILBO_LL_Log_Entry:
    tick: int = 0
    type: BILBO_ErrorType = BILBO_ErrorType.NONE
    error: BILBO_ErrorCodes = BILBO_ErrorCodes.UNSPECIFIED
