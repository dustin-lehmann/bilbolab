import dataclasses
import enum


@dataclasses.dataclass
class TWIPR_Balancing_Control_Config:
    available: bool = False
    K: list = dataclasses.field(default_factory=list)  # State Feedback Gain
    u_lim: list = dataclasses.field(default_factory=list)  # Input Limits
    external_input_gain: list = dataclasses.field(
        default_factory=list)  # When using balancing control without speed control, this can scale the external input


@dataclasses.dataclass
class TWIPR_PID_Control_Config:
    Kp: float = 0.0
    Kd: float = 0.0
    Ki: float = 0.0
    # anti_windup: float = 0
    # integrator_saturation: float = None


@dataclasses.dataclass
class TWIPR_Speed_Control_Config:
    available: bool = False
    v: TWIPR_PID_Control_Config = dataclasses.field(default_factory=TWIPR_PID_Control_Config)
    psidot: TWIPR_PID_Control_Config = dataclasses.field(default_factory=TWIPR_PID_Control_Config)
    external_input_gain: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class TWIPR_Control_Config:
    name: str = ''
    description: str = ''
    balancing_control: TWIPR_Balancing_Control_Config = dataclasses.field(
        default_factory=TWIPR_Balancing_Control_Config)
    speed_control: TWIPR_Speed_Control_Config = dataclasses.field(default_factory=TWIPR_Speed_Control_Config)


class BILBO_Control_Mode(enum.IntEnum):
    OFF = 0,
    DIRECT = 1,
    BALANCING = 2,
    VELOCITY = 3,
    # TWIPR_CONTROL_MODE_POS = 4


class BILBO_Control_Status(enum.IntEnum):
    ERROR = 0
    NORMAL = 1


@dataclasses.dataclass
class BILBO_Control_Input_Direct:
    u_left: float = 0.0
    u_right: float = 0.0


@dataclasses.dataclass
class BILBO_Control_Input_Balancing:
    u_left: float = 0.0
    u_right: float = 0.0


@dataclasses.dataclass
class BILBO_Control_Input_Velocity:
    forward: float = 0.0
    turn: float = 0.0


@dataclasses.dataclass
class BILBO_Control_Input:
    direct: BILBO_Control_Input_Direct = dataclasses.field(default_factory=BILBO_Control_Input_Direct)
    balancing: BILBO_Control_Input_Balancing = dataclasses.field(default_factory=BILBO_Control_Input_Balancing)
    velocity: BILBO_Control_Input_Velocity = dataclasses.field(default_factory=BILBO_Control_Input_Velocity)


@dataclasses.dataclass(frozen=True)
class TWIPR_Control_Sample:
    status: BILBO_Control_Status = dataclasses.field(
        default=BILBO_Control_Status(BILBO_Control_Status.ERROR)
    )
    mode: BILBO_Control_Mode = dataclasses.field(default=BILBO_Control_Mode(BILBO_Control_Mode.OFF))
    configuration: str = ''
    input: BILBO_Control_Input = dataclasses.field(default_factory=BILBO_Control_Input)
