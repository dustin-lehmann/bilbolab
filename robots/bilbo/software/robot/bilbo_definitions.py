import dataclasses
import enum
import yaml


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class BILBO_DynamicState:
    x: float = 0.0
    y: float = 0.0
    v: float = 0.0
    theta: float = 0.0
    theta_dot: float = 0.0
    psi: float = 0.0
    psi_dot: float = 0.0


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class BILBO_ConfigurationState:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    theta: float = 0.0
    psi: float = 0.0


# === TESTBED ==========================================================================================================
@dataclasses.dataclass
class BILBO_OriginConfig:
    id: str
    points: list
    x_start: int
    x_end: int
    y_start: int
    y_end: int
    marker_size: float
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0



