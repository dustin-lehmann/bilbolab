import dataclasses
import enum


class BILBO_Control_Mode(enum.IntEnum):
    OFF = 0,
    DIRECT = 1,
    BALANCING = 2,
    VELOCITY = 3,
    POSITION = 4,



@dataclasses.dataclass
class TIC_Config:
    enabled: bool = False
    ki: float = 0.0
    max_error: float = 0.0
    theta_limit: float = 0.0


@dataclasses.dataclass
class VIC_Config:
    enabled: bool = False
    ki: float = 0.0
    max_error: float = 0.0
    v_limit: float = 0.0


@dataclasses.dataclass
class TWIPR_Balancing_Control_Config:
    K: list = dataclasses.field(default_factory=list)  # State Feedback Gain
    tic: TIC_Config = dataclasses.field(default_factory=TIC_Config)
    vic: VIC_Config = dataclasses.field(default_factory=VIC_Config)


@dataclasses.dataclass
class TWIPR_PID_Control_Config:
    Kp: float = 0.0
    Kd: float = 0.0
    Ki: float = 0.0
    # anti_windup: float = 0
    # integrator_saturation: float = None


@dataclasses.dataclass
class SpeedControl_Config:
    v: TWIPR_PID_Control_Config = dataclasses.field(default_factory=TWIPR_PID_Control_Config)
    psidot: TWIPR_PID_Control_Config = dataclasses.field(default_factory=TWIPR_PID_Control_Config)
    max_speeds: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class General_Control_Config:
    max_wheel_speed: float = 0.0
    max_wheel_torque: float = 0.0
    enable_external_inputs: bool = False
    torque_offset: dict = dataclasses.field(default_factory=lambda: {'left': 0, 'right': 0})


@dataclasses.dataclass
class ExternalInputsConfig:
    balancing_input_gain: dict = dataclasses.field(default_factory=dict)  # 'forward' and 'turn'
    speed_input_gain: dict = dataclasses.field(default_factory=dict)  # 'forward' and 'turn'


@dataclasses.dataclass
class BILBO_ControlConfig:
    name: str = ''
    description: str = ''
    mode: BILBO_Control_Mode = dataclasses.field(default=BILBO_Control_Mode(BILBO_Control_Mode.OFF))
    general: General_Control_Config = dataclasses.field(default_factory=General_Control_Config)
    external_inputs: ExternalInputsConfig = dataclasses.field(default_factory=ExternalInputsConfig)
    balancing_control: TWIPR_Balancing_Control_Config = dataclasses.field(
        default_factory=TWIPR_Balancing_Control_Config)
    speed_control: SpeedControl_Config = dataclasses.field(default_factory=SpeedControl_Config)


@dataclasses.dataclass
class BILBO_LL_ControlConfig:
    K: list = dataclasses.field(default_factory=list)
    forward_p: float = 0.0
    forward_i: float = 0.0
    forward_d: float = 0.0
    turn_p: float = 0.0
    turn_i: float = 0.0
    turn_d: float = 0.0
    vic_enabled: bool = False
    vic_ki: float = 0.0
    vic_max_error: float = 0.0
    vic_v_limit: float = 0.0
    tic_enabled: bool = False
    tic_ki: float = 0.0
    tic_max_error: float = 0.0
    tic_theta_limit: float = 0.0


class BILBO_Control_Status(enum.IntEnum):
    ERROR = 0
    NORMAL = 1


@dataclasses.dataclass
class BILBO_Control_Input:
    u_ext: list = dataclasses.field(default_factory=lambda: [0.0, 0.0])
    v: list = dataclasses.field(default_factory=lambda: [0.0, 0.0])

    # direct: BILBO_Control_Input_Direct = dataclasses.field(default_factory=BILBO_Control_Input_Direct)
    # balancing: BILBO_Control_Input_Balancing = dataclasses.field(default_factory=BILBO_Control_Input_Balancing)
    # velocity: BILBO_Control_Input_Velocity = dataclasses.field(default_factory=BILBO_Control_Input_Velocity)
    # position: BILBO_Control_Input_Position = dataclasses.field(default_factory=BILBO_Control_Input_Position)

@dataclasses.dataclass(frozen=True)
class BILBO_Control_Sample:
    status: BILBO_Control_Status = dataclasses.field(default=BILBO_Control_Status(BILBO_Control_Status.NORMAL))
    mode: BILBO_Control_Mode = dataclasses.field(default=BILBO_Control_Mode(BILBO_Control_Mode.OFF))
    tic_enabled: bool = False
    configuration: str = ''
    # input: BILBO_Control_Input = dataclasses.field(default_factory=BILBO_Control_Input)


class BILBO_Control_Event_Type(enum.IntEnum):
    ERROR = 0
    MODE_CHANGED = 1
    CONFIGURATION_CHANGED = 2
    VIC_CHANGED = 3
    TIC_CHANGED = 4
