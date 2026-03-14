import ctypes
import enum

from core.utils.ctypes_utils import STRUCTURE

LOOP_TIME_CONTROL = 0.01
BILBO_CONTROL_DT = LOOP_TIME_CONTROL
LOOP_TIME = 0.1

MAX_STEPS_TRAJECTORY = 3000


@STRUCTURE
class bilbo_firmware_revision:
    FIELDS = {
        'major': ctypes.c_uint8,
        'minor': ctypes.c_uint8,
    }


# --- Firmware info: compile-time settings reported by STM32 ---

class BILBO_BoardRevision(enum.IntEnum):
    # Must match firmware bilbo_board_revision_t : uint8_t
    REV_3 = 3
    REV_4 = 4


class BILBO_ModelType(enum.IntEnum):
    # Must match firmware bilbo_model_type_t : uint8_t
    NORMAL = 0
    SMALL = 1
    BIG = 2


class BILBO_DriveInterface(enum.IntEnum):
    # Must match firmware bilbo_drive_interface_t : uint8_t
    RS485 = 1
    CAN = 2


@STRUCTURE
class bilbo_firmware_info:
    FIELDS = {
        'board_revision': ctypes.c_uint8,
        'model': ctypes.c_uint8,
        'drive_interface': ctypes.c_uint8,
    }
