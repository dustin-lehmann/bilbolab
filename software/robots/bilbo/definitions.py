import dataclasses

from core.utils.files import get_absolute_path
from core.utils.states import State
from core.utils.uuid_utils import generate_uuid

# ======================================================================================================================
EXPERIMENT_DIR = get_absolute_path('./definitions/tests/')


# === COMMON OBJECTS AND CONFIGS =======================================================================================
@dataclasses.dataclass
class BoxObstacle_Config:
    id: str | None = None
    width: float = 0
    height: float = 0

    # Convenience fields for YAML shorthand (e.g. size: [1, 0.5], state: [1, 1, 1.57])
    size: list | None = dataclasses.field(default=None, repr=False)
    state: list | None = dataclasses.field(default=None, repr=False)
    type: str | None = dataclasses.field(default=None, repr=False)

    def __post_init__(self):
        self.id = self.id or generate_uuid(prefix="box_obstacle_")
        if self.size is not None and len(self.size) >= 2:
            if self.width == 0:
                self.width = float(self.size[0])
            if self.height == 0:
                self.height = float(self.size[1])
            self.size = None
        self.type = None  # Not needed after init
        # state is consumed by VirtualTestbed.init(), not cleaned here


@dataclasses.dataclass
class Line_Config:
    id: str | None = None
    start: list | None = None  # [x, y]
    end: list | None = None  # [x, y]


@dataclasses.dataclass
class Point_Config:
    id: str | None = None
    position: list | None = None  # [x, y]


@dataclasses.dataclass
class Pose_Config:
    id: str | None = None
    x: float = 0.0
    y: float = 0.0
    psi: float = 0.0

    # YAML shorthand: pose: [x, y, psi]
    pose: list | None = dataclasses.field(default=None, repr=False)

    def __post_init__(self):
        if self.pose is not None and len(self.pose) >= 2:
            if self.x == 0.0:
                self.x = float(self.pose[0])
            if self.y == 0.0:
                self.y = float(self.pose[1])
            if self.psi == 0.0 and len(self.pose) > 2:
                self.psi = float(self.pose[2])
            self.pose = None


@dataclasses.dataclass
class BoxObstacle_State:
    x: float = 0
    y: float = 0
    psi: float = 0


@dataclasses.dataclass
class BILBO_DynamicState(State):
    x: float = 0.0
    y: float = 0.0
    v: float = 0.0
    theta: float = 0.0
    theta_dot: float = 0.0
    psi: float = 0.0
    psi_dot: float = 0.0
