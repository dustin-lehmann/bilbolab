import dataclasses
import enum

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger
from extensions.hardware.optitrack import OptiTrack, RigidBodySample
from robots.bilbo.robot.bilbo_definitions import BILBO_Config
from robots.bilbo.testbed.tracker.tracked_objects import TrackedBILBO, TrackedOrigin, TrackedLimboBar, TrackedBox, \
    TrackedWall, Origin_OptiTrack_Config, BoxObstacle_OptiTrack_Config, WallObstacle_OptiTrack_Config, \
    LimboMarker_OptiTrack_Config, OptiTrackOutlierFilterConfig


@callback_definition
class BILBO_Tracker_Callbacks:
    new_sample: CallbackContainer
    description_received: CallbackContainer
    new_rigid_body: CallbackContainer


@event_definition
class BILBO_Tracker_Events:
    new_sample: Event
    description_received: Event
    initialized: Event
    error: Event
    new_rigid_body: Event
    new_tracked_object: Event = Event(copy_data_on_set=False)
    tracked_object_removed: Event = Event(copy_data_on_set=False)


@dataclasses.dataclass
class BILBO_Tracker_Config:
    server: str
    max_sample_rate: float = 50.0
    origin: Origin_OptiTrack_Config | None = None
    outlier_filter: OptiTrackOutlierFilterConfig = dataclasses.field(default_factory=OptiTrackOutlierFilterConfig)


class BILBO_Tracker_Status(enum.StrEnum):
    RUNNING = "RUNNING"
    DISABLED = "DISABLED"
    NONE = "NONE"


class BILBO_Tracker:
    config: BILBO_Tracker_Config
    rigid_bodies: dict[str, dict]

    bilbos: dict[str, TrackedBILBO]
    origin: TrackedOrigin | None = None
    limbo_bar: TrackedLimboBar | None = None
    obstacles: dict[str, TrackedBox]
    walls: dict[str, TrackedWall]

    events: BILBO_Tracker_Events
    callbacks: BILBO_Tracker_Callbacks
    samples: int = 0
    status: BILBO_Tracker_Status = BILBO_Tracker_Status.NONE

    # === INIT =========================================================================================================
    def __init__(self, config: BILBO_Tracker_Config):
        self.logger = Logger('BILBO Tracker', 'DEBUG')
        self.config = config

        self.rigid_bodies = {}
        self.bilbos = {}
        self.obstacles = {}
        self.walls = {}

        self.events = BILBO_Tracker_Events()
        self.callbacks = BILBO_Tracker_Callbacks()

        self.optitrack = OptiTrack(max_sample_rate=self.config.max_sample_rate, server_address=self.config.server)
        self.optitrack.events.sample.on(self._onSample)
        self.optitrack.callbacks.description_received.register(self._onDescriptionReceived)

    # === METHODS ======================================================================================================
    def init(self):
        self.optitrack.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        success = self.optitrack.start()

        if not success:
            self.logger.warning("Could not start OptiTrack. Tracking disabled")
            self.status = BILBO_Tracker_Status.DISABLED
            self.events.error.set()
            return False
        self.logger.info("Starting Tracker")

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def add_robot(self, robot_id: str, config: BILBO_Config) -> TrackedBILBO | None:
        if self.status == BILBO_Tracker_Status.DISABLED:
            self.logger.warning("Cannot add robot to tracker when tracking is disabled")
            return None

        if robot_id in self.bilbos:
            self.logger.error(f"BILBO robot {robot_id} already exists. Cannot add another robot with the same ID")
            return None

        if robot_id not in self.rigid_bodies:
            self.logger.error(
                f"BILBO robot {robot_id} not found in rigid bodies. Ensure to enable the rigid body in OptiTrack")
            return None

        bilbo = TrackedBILBO(id=robot_id, config=config, origin=self.origin,
                             outlier_filter_config=self.config.outlier_filter)
        self.bilbos[robot_id] = bilbo
        self.events.new_tracked_object.set(bilbo)
        self.logger.info(f"Added tracked BILBO robot {robot_id}")
        return bilbo

    # ------------------------------------------------------------------------------------------------------------------
    def remove_robot(self, robot_id: str):
        if robot_id not in self.bilbos:
            self.logger.warning(f"BILBO robot {robot_id} not found in tracker")
            return
        bilbo = self.bilbos.pop(robot_id)
        self.events.tracked_object_removed.set(bilbo)
        self.logger.info(f"Removed tracked BILBO robot {robot_id}")

    # ------------------------------------------------------------------------------------------------------------------
    def add_origin(self, origin_id: str, config: Origin_OptiTrack_Config) -> TrackedOrigin | None:
        if self.status == BILBO_Tracker_Status.DISABLED:
            self.logger.warning("Cannot add origin to tracker when tracking is disabled")
            return None

        if self.origin is not None:
            self.logger.error(f"Origin {origin_id} already exists")
            return None
        if origin_id not in self.rigid_bodies:
            self.logger.error(
                f"Origin {origin_id} not found in rigid bodies. Ensure to enable the rigid body in OptiTrack")
            return None
        self.origin = TrackedOrigin(id=origin_id, definition=config)
        self.events.new_tracked_object.set(self.origin)

        # Ensure to add the origin to each of the other objects
        for bilbo in self.bilbos.values():
            bilbo.origin = self.origin

        for obstacle in self.obstacles.values():
            obstacle.origin = self.origin

        for wall in self.walls.values():
            wall.origin = self.origin

        if self.limbo_bar is not None:
            self.limbo_bar.origin = self.origin

        self.logger.info(f"Added tracked origin {origin_id}")
        return self.origin

    # ------------------------------------------------------------------------------------------------------------------
    def add_limbo_bar(self, limbo_bar_id: str, config: LimboMarker_OptiTrack_Config) -> TrackedLimboBar | None:
        if self.status == BILBO_Tracker_Status.DISABLED:
            self.logger.warning("Cannot add limbo bar to tracker when tracking is disabled")
            return None

        if self.limbo_bar is not None:
            self.logger.error(f"Limbo bar {limbo_bar_id} already exists")
            return None

        if limbo_bar_id not in self.rigid_bodies:
            self.logger.error(
                f"Limbo bar {limbo_bar_id} not found in rigid bodies. Ensure to enable the rigid body in OptiTrack")
            return None

        self.limbo_bar = TrackedLimboBar(id=limbo_bar_id, config=config, origin=self.origin)
        self.events.new_tracked_object.set(self.limbo_bar)
        self.logger.info(f"Added tracked limbo bar {limbo_bar_id}")
        return self.limbo_bar

    # ------------------------------------------------------------------------------------------------------------------
    def add_obstacle(self, obstacle_id: str, config: BoxObstacle_OptiTrack_Config) -> TrackedBox | None:
        if self.status == BILBO_Tracker_Status.DISABLED:
            self.logger.warning("Cannot add obstacle to tracker when tracking is disabled")
            return None

        if obstacle_id in self.obstacles:
            self.logger.error(f"Obstacle {obstacle_id} already exists. Cannot add another obstacle with the same ID")
            return None

        if obstacle_id not in self.rigid_bodies:
            self.logger.error(
                f"Obstacle {obstacle_id} not found in rigid bodies. Ensure to enable the rigid body in OptiTrack")
            return None

        obstacle = TrackedBox(id=obstacle_id, config=config, origin=self.origin)
        self.obstacles[obstacle_id] = obstacle
        self.events.new_tracked_object.set(obstacle)
        self.logger.info(f"Added tracked obstacle {obstacle_id}")
        return obstacle

    # ------------------------------------------------------------------------------------------------------------------
    def add_wall(self, wall_id: str, config: WallObstacle_OptiTrack_Config) -> TrackedWall | None:
        if self.status == BILBO_Tracker_Status.DISABLED:
            self.logger.warning("Cannot add wall to tracker when tracking is disabled")
            return None

        if wall_id in self.walls:
            self.logger.error(f"Wall {wall_id} already exists. Cannot add another wall with the same ID")
            return None
        if wall_id not in self.rigid_bodies:
            self.logger.error(
                f"Wall {wall_id} not found in rigid bodies. Ensure to enable the rigid body in OptiTrack")

        wall = TrackedWall(id=wall_id, config=config, origin=self.origin)
        self.walls[wall_id] = wall
        self.events.new_tracked_object.set(wall)
        self.logger.info(f"Added tracked wall {wall_id}")
        return wall

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # === PRIVATE METHODS ==============================================================================================
    def _onDescriptionReceived(self, rigid_bodies: dict):
        self.logger.info(f"Received description from OptiTrack: {rigid_bodies}")

        for id in rigid_bodies:
            self.rigid_bodies[id] = rigid_bodies[id]

        self.status = BILBO_Tracker_Status.RUNNING
        self.callbacks.description_received.call(rigid_bodies)
        self.events.description_received.set()
        self.events.initialized.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _onSample(self, sample: dict[str, RigidBodySample]):
        self.sample = sample
        self.samples += 1

        # Set all trackings to invalid
        for bilbo in self.bilbos.values():
            bilbo.tracking_valid = False

        for obstacle in self.obstacles.values():
            obstacle.tracking_valid = False

        for wall in self.walls.values():
            wall.tracking_valid = False

        if self.limbo_bar is not None:
            self.limbo_bar.tracking_valid = False

        if self.origin is not None:
            self.origin.tracking_valid = False

        # Update all objects
        if self.origin is not None and self.origin.id in sample:
            self.origin.update(sample[self.origin.id])
            self.origin.tracking_valid = sample[self.origin.id].valid

        if self.limbo_bar is not None and self.limbo_bar.id in sample:
            self.limbo_bar.update(sample[self.limbo_bar.id])
            self.limbo_bar.tracking_valid = sample[self.limbo_bar.id].valid

        for name, data in sample.items():
            if name in self.bilbos:
                self.bilbos[name].update(data)
                self.bilbos[name].tracking_valid = data.valid
            elif name in self.obstacles:
                self.obstacles[name].update(data)
                self.obstacles[name].tracking_valid = data.valid
            elif name in self.walls:
                self.walls[name].update(data)
                self.walls[name].tracking_valid = data.valid

            if name not in self.rigid_bodies:
                self.logger.info(f"New rigid body found: {name}")
                self.callbacks.new_rigid_body.call(name)
                self.events.new_rigid_body.set(name)

        self.callbacks.new_sample.call()
        self.events.new_sample.set()
