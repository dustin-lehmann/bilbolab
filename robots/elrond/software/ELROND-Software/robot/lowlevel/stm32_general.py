import ctypes

from utils.ctypes_utils import STRUCTURE

LOOP_TIME_CONTROL = 0.01
LOOP_TIME = 0.1

MAX_STEPS_TRAJECTORY = 3000


@STRUCTURE
class twipr_firmware_revision:
    FIELDS = {
        'major': ctypes.c_uint8,
        'minor': ctypes.c_uint8,
    }
