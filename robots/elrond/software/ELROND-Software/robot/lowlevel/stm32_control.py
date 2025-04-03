import ctypes
import enum

from utils.ctypes_utils import STRUCTURE


# Structures
@STRUCTURE
class bilbo_control_external_input_t:
    FIELDS = [("u_direct_1", ctypes.c_float),
              ("u_direct_2", ctypes.c_float),
              ("u_balancing_1", ctypes.c_float),
              ('u_balancing_2', ctypes.c_float),
              ("u_velocity_forward", ctypes.c_float),
              ("u_velocity_turn", ctypes.c_float)]


class bilbo_control_direct_input_t(ctypes.Structure):
    _fields_ = [("u_left", ctypes.c_float),
                ("u_right", ctypes.c_float), ]


class bilbo_control_balancing_input_t(ctypes.Structure):
    _fields_ = [("u_left", ctypes.c_float),
                ("u_right", ctypes.c_float), ]


class bilbo_control_speed_input_t(ctypes.Structure):
    _fields_ = [("forward", ctypes.c_float),
                ("turn", ctypes.c_float), ]


class BILBO_Control_Status_LL(enum.IntEnum):
    ERROR = -1
    IDLE = 0
    RUNNING = 1


class BILBO_Control_Mode_LL(enum.IntEnum):
    OFF = 0,
    DIRECT = 1,
    BALANCING = 2,
    VELOCITY = 3


@STRUCTURE
class bilbo_control_configuration_ll_t:
    FIELDS = {
        'K': ctypes.c_float * 8,  # type: ignore
        'forward_p': ctypes.c_float,
        'forward_i': ctypes.c_float,
        'forward_d': ctypes.c_float,
        'turn_p': ctypes.c_float,
        'turn_i': ctypes.c_float,
        'turn_d': ctypes.c_float,
        'vic_enabled': ctypes.c_bool,
        'vic_ki': ctypes.c_float,
        'vic_max_error': ctypes.c_float,
        'vic_v_limit': ctypes.c_float,
    }