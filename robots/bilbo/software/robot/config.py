import dataclasses
import enum
import yaml

from core.utils.dataclass_utils import from_dict_auto
from core.utils.files import file_exists
from core.hardware.network import get_own_hostname
from robot.paths import CONFIG_PATH


# === ROBOT DEFINITIONS ================================================================================================
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
    trajectory_delta: float = 0.0  # Asymmetric torque split: left = u*(0.5+delta), right = u*(0.5-delta)


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
    simulation: bool = False


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


@dataclasses.dataclass
class BILBO_EstimationConfig:
    enable_dead_reckoning: bool = True


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_Config:
    general: BILBO_General_Information
    network: BILBO_Network_Information
    optitrack: BILBO_OptiTrack_Definition
    model: BILBO_PhysicalModel
    electronics: BILBO_Hardware_Electronics
    estimation: BILBO_EstimationConfig = dataclasses.field(default_factory=BILBO_EstimationConfig)


# ======================================================================================================================
def bilbo_config_from_file(file_name: str) -> BILBO_Config:
    file_path = f"{CONFIG_PATH}/{file_name}"
    if not file_exists(file_path):
        raise FileNotFoundError(f"File '{file_path}' not found")

    with open(file_path, 'r') as file:
        data = yaml.safe_load(file)

    information = from_dict_auto(BILBO_Config, data)
    return information


# ----------------------------------------------------------------------------------------------------------------------
def bilbo_config_to_file(file_name: str, information: BILBO_Config):
    file_path = f"{CONFIG_PATH}/{file_name}"
    with open(file_path, 'w') as file:
        yaml.dump(dataclasses.asdict(information), file)


# ----------------------------------------------------------------------------------------------------------------------
def get_bilbo_config(bilbo_id: str | None = None) -> BILBO_Config:

    if bilbo_id is None:
        bilbo_id = get_own_hostname()

    return bilbo_config_from_file(f"{bilbo_id}.yaml")
