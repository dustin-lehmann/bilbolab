import ctypes

from utils.ctypes_utils import STRUCTURE


@STRUCTURE
class bilbo_sequence_input_t:
    FIELDS = [
        ('step', ctypes.c_uint32),
        ('u_1', ctypes.c_float),
        ('u_2', ctypes.c_float),
    ]


@STRUCTURE
class bilbo_sequence_description_t:
    FIELDS = [
        ('sequence_id', ctypes.c_uint16),
        ('length', ctypes.c_uint16),
        ('require_control_mode', ctypes.c_bool),
        ('wait_time_beginning', ctypes.c_uint16),
        ('wait_time_end', ctypes.c_uint16),
        ('control_mode', ctypes.c_uint8),
        ('control_mode_end', ctypes.c_uint8),
        ('loaded', ctypes.c_bool),
    ]
