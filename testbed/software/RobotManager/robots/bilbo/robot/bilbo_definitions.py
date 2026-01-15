import dataclasses
import enum


HOST_EXPERIMENT_FOLDER = "/Users/tizianohumpert/Documents/IMES/Bilbo_Main/bilbolab/testbed/software/RobotManager/applications/BILBO/experiments/general/test/"


BILBO_HOST_NAMES = ['bilbo1', 'bilbo2', 'bilbo3', 'bilbo4', 'bilbo5','bilbo2-imes']

PATH_TO_MAIN = '/home/admin/robot/software/main.py'
PYENV_SHIM_PATH = '/home/admin/.pyenv/shims/python3'
BILBO_USER_NAME = 'admin'
BILBO_PASSWORD = 'beutlin'

BILBO_CONTROL_DT = 0.01
MAX_STEPS_TRAJECTORY = 3000


class BILBO_Control_Mode(enum.IntEnum):
    OFF = 0,
    DIRECT = 1,
    BALANCING = 2,
    VELOCITY = 3
    POSITION = 4


# ----------------------------------------------------------------------------------------------------------------------

# === CONFIG ==========================================================================================================
@dataclasses.dataclass
class BILBO_PhysicalModel:
    type: str
    wheel_diameter: float
    vertical_offset: float
    mass: float
    height: float
    width: float
    depth: float
    distance_wheels: float
    l_cg: float
    theta_offset: float


@dataclasses.dataclass
class BILBO_OptiTrack_Definition:
    points: list[int]
    point_x_axis_start: int
    point_x_axis_end: int
    point_y_axis_start: int
    point_y_axis_end: int
    marker_size: float


@dataclasses.dataclass
class BILBO_General_Information:
    id: str
    short_id: str
    type: str
    version: str
    color: list | None


@dataclasses.dataclass
class BILBO_Network_Information:
    address: str
    data_stream_port: int
    gui_port: int
    ssid: str
    username: str
    password: str


# === HARDWARE DEFINITIONS =============================================================================================
@dataclasses.dataclass
class DisplaySettings:
    active: bool
    resolution: list | None


@dataclasses.dataclass
class SoundSettings:
    active: bool
    gain: float | None


@dataclasses.dataclass
class ButtonSettings:
    type: str | None  # Can be 'internal', 'sx1508', 'sx1509' or None
    pin: int | None


@dataclasses.dataclass
class Buttons:
    primary: ButtonSettings
    secondary: ButtonSettings


class BILBO_Shields(enum.StrEnum):
    BILBO_SHIELD_REV2 = 'bilbo_shield_rev2'
    NONE = 'none'


@dataclasses.dataclass
class BILBO_Hardware_Electronics:
    board_revision: str
    compute_module: str
    shield: BILBO_Shields
    display: DisplaySettings
    sound: SoundSettings
    battery_cells: int
    buttons: Buttons


@dataclasses.dataclass
class Model:
    type: str
    theta_offset: float = 0.0


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_Config:
    general: BILBO_General_Information
    network: BILBO_Network_Information
    optitrack: BILBO_OptiTrack_Definition
    model: BILBO_PhysicalModel
    electronics: BILBO_Hardware_Electronics


# ----------------------------------------------------------------------------------------------------------------------
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
class BILBO_OriginConfig:
    id: str
    points: list
    origin: int
    x_axis_end: int
    y_axis_end: int
    marker_size: float
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0


@dataclasses.dataclass(kw_only=True)
class BILBO_LimboMarkerConfig:
    id: str = 'limbo-marker'
    points: list
    x_start: int
    x_end: int
    y_start: int
    y_end: int
