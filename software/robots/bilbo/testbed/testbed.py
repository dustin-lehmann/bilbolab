import dataclasses

from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger
from robots.bilbo.definitions import Line_Config, Point_Config, Pose_Config
from robots.bilbo.testbed.objects import TestbedBILBO, Obstacle, LimboBar
from robots.bilbo.testbed.tracker.tracked_objects import Origin_OptiTrack_Config


@dataclasses.dataclass
class TestbedSize:
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclasses.dataclass
class TestbedConfig:
    size: TestbedSize
    id: str | None = None
    origin: Origin_OptiTrack_Config | None = None


@dataclasses.dataclass
class TestbedData:
    config: TestbedConfig | None = None


@event_definition
class Testbed_Events:
    bilbo_added: Event = Event(copy_data_on_set=False)
    bilbo_removed: Event = Event(copy_data_on_set=False)
    obstacle_added: Event = Event(copy_data_on_set=False)
    obstacle_removed: Event = Event(copy_data_on_set=False)


class Testbed:
    bilbos: dict[str, TestbedBILBO]
    obstacles: dict[str, Obstacle]
    lines: dict[str, Line_Config]
    points: dict[str, Point_Config]
    poses: dict[str, Pose_Config]
    limbo_bar: LimboBar | None
    config: TestbedConfig | None

    # === INIT =========================================================================================================
    def __init__(self, config: TestbedConfig | None = None):
        self.logger = Logger('Testbed', 'DEBUG')
        self.config = config
        self.bilbos = {}
        self.obstacles = {}
        self.lines = {}
        self.points = {}
        self.poses = {}
        self.limbo_bar = None
        self.events = Testbed_Events()

    # === METHODS ======================================================================================================
    def add_bilbo(self, bilbo: TestbedBILBO):
        if bilbo.id in self.bilbos:
            self.logger.warning(f"BILBO {bilbo.id} already exists in testbed")
            return
        self.bilbos[bilbo.id] = bilbo
        self.logger.info(f"Added BILBO {bilbo.id} to testbed")
        self.events.bilbo_added.set(bilbo)

    # ------------------------------------------------------------------------------------------------------------------
    def remove_bilbo(self, bilbo_id: str):
        if bilbo_id not in self.bilbos:
            self.logger.warning(f"BILBO {bilbo_id} not found in testbed")
            return
        bilbo = self.bilbos.pop(bilbo_id)
        self.logger.info(f"Removed BILBO {bilbo_id} from testbed")
        self.events.bilbo_removed.set(bilbo)

    # ------------------------------------------------------------------------------------------------------------------
    def add_obstacle(self, obstacle: Obstacle):
        if obstacle.id in self.obstacles:
            self.logger.warning(f"Obstacle {obstacle.id} already exists in testbed")
            return
        self.obstacles[obstacle.id] = obstacle
        self.logger.info(f"Added obstacle {obstacle.id} to testbed")
        self.events.obstacle_added.set(obstacle)

    # ------------------------------------------------------------------------------------------------------------------
    def remove_obstacle(self, obstacle_id: str):
        if obstacle_id not in self.obstacles:
            self.logger.warning(f"Obstacle {obstacle_id} not found in testbed")
            return
        obstacle = self.obstacles.pop(obstacle_id)
        self.logger.info(f"Removed obstacle {obstacle_id} from testbed")
        self.events.obstacle_removed.set(obstacle)

    # ------------------------------------------------------------------------------------------------------------------
    def add_line(self, line: Line_Config):
        line_id = line.id or f"line_{len(self.lines) + 1}"
        if line_id in self.lines:
            self.logger.warning(f"Line {line_id} already exists in testbed")
            return
        self.lines[line_id] = line
        self.logger.info(f"Added line {line_id} to testbed")

    # ------------------------------------------------------------------------------------------------------------------
    def add_point(self, point: Point_Config):
        point_id = point.id or f"point_{len(self.points) + 1}"
        if point_id in self.points:
            self.logger.warning(f"Point {point_id} already exists in testbed")
            return
        self.points[point_id] = point
        self.logger.info(f"Added point {point_id} to testbed")

    # ------------------------------------------------------------------------------------------------------------------
    def add_pose(self, pose: Pose_Config):
        pose_id = pose.id or f"pose_{len(self.poses) + 1}"
        if pose_id in self.poses:
            self.logger.warning(f"Pose {pose_id} already exists in testbed")
            return
        self.poses[pose_id] = pose
        self.logger.info(f"Added pose {pose_id} to testbed")

    # ------------------------------------------------------------------------------------------------------------------
    def add_limbo_bar(self):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        """Called on each tracker/simulation tick. Run collision checks etc."""
        if self.limbo_bar is not None:
            for bilbo in self.bilbos.values():
                self.limbo_bar.update(bilbo)

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> dict:
        """Get testbed configuration as dict for sending to robots."""
        if self.config is None:
            return {}
        config = {
            'size': {
                'x_min': self.config.size.x_min,
                'x_max': self.config.size.x_max,
                'y_min': self.config.size.y_min,
                'y_max': self.config.size.y_max,
            },
            'obstacles': [obs.to_dict() for obs in self.obstacles.values()],
            'lines': [dataclasses.asdict(l) for l in self.lines.values()],
            'points': [dataclasses.asdict(p) for p in self.points.values()],
            'poses': [dataclasses.asdict(p) for p in self.poses.values()],
        }
        if self.config.id is not None:
            config['id'] = self.config.id
        if self.config.origin is not None:
            config['origin'] = dataclasses.asdict(self.config.origin)
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def get_data(self) -> dict:
        """Get current testbed state as dict (for GUI etc.)."""
        return {
            'bilbos': {id: {'x': b.state.x, 'y': b.state.y, 'psi': b.state.psi}
                       for id, b in self.bilbos.items()},
            'obstacles': {id: obs.to_dict() for id, obs in self.obstacles.items()},
            'lines': {id: dataclasses.asdict(l) for id, l in self.lines.items()},
            'points': {id: dataclasses.asdict(p) for id, p in self.points.items()},
            'poses': {id: dataclasses.asdict(p) for id, p in self.poses.items()},
        }
