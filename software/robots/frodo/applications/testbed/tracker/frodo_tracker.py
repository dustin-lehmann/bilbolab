import dataclasses
import enum
import time

import numpy as np

from applications.FRODO.testbed.tracker.definitions import TrackedFRODO, TrackedOrigin, ORIGINS, \
    TrackedStatic, TRACKED_STATICS, TRACKED_FRODO_DEFINITIONS
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from extensions.hardware.optitrack.optitrack import OptiTrack, RigidBodySample
from core.utils.callbacks import callback_definition, CallbackContainer


# =====================================================================================================================

@callback_definition
class FRODO_Tracker_Callbacks:
    initialized: CallbackContainer
    new_sample: CallbackContainer
    description_received: CallbackContainer


@event_definition
class FRODO_Tracker_Events:
    initialized: Event
    new_sample: Event
    description_received: Event


class FRODO_Tracker_State(enum.StrEnum):
    NOT_RUNNING = "not_running"
    RUNNING = "running"


class FRODO_Tracker:
    optitrack: OptiTrack

    robots: dict[str, TrackedFRODO]
    statics: dict[str, TrackedStatic]
    origin: TrackedOrigin | None = None

    state: FRODO_Tracker_State = FRODO_Tracker_State.NOT_RUNNING
    # === INIT =========================================================================================================
    def __init__(self, robots: dict[str, TrackedFRODO] = None, origin: TrackedOrigin = None):
        self.logger = Logger('BILBO Tracker', 'DEBUG')

        if robots is None:
            robots = {}
        self.robots = robots
        self.origin = origin
        self.statics = {}

        self.callbacks = FRODO_Tracker_Callbacks()
        self.events = FRODO_Tracker_Events()

        self.optitrack = OptiTrack(server_address='bree.local')
        self.optitrack.events.sample.on(self._onSample)
        self.optitrack.callbacks.description_received.register(self._onDescriptionReceived)
        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self.optitrack.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        success = self.optitrack.start()

        if not success:
            self.logger.error("Could not start OptiTrack. Tracking disabled")
            return False
        self.logger.info("Starting Tracker")

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.optitrack.close()

    # === PRIVATE METHODS ==============================================================================================
    def _onSample(self, sample: dict[str, RigidBodySample]):
        for robot in self.robots.values():
            robot.tracking_valid = False

        for name, data in sample.items():
            if name in self.robots:
                self.robots[name].update(data)
                self.robots[name].tracking_valid = data.valid

            if name in self.statics:
                self.statics[name].update(data)
                self.statics[name].tracking_valid = data.valid

        if self.origin is not None:
            if self.origin.id in sample:
                self.origin.update(sample[self.origin.id])
                self.origin.tracking_valid = sample[self.origin.id].valid
            else:
                self.origin.tracking_valid = False

    # ------------------------------------------------------------------------------------------------------------------
    def _onDescriptionReceived(self, rigid_bodies: dict):
        self.logger.info(f"Received description from OptiTrack: {rigid_bodies}")

        for id, body_description in rigid_bodies.items():
            if id in TRACKED_FRODO_DEFINITIONS:
                self.robots[id] = TRACKED_FRODO_DEFINITIONS[id]
                self.logger.info(f"Added {id} to tracked frodo objects")

            if id in ORIGINS:
                if self.origin is not None:
                    self.logger.warning(f"Origin {self.origin.id} already exists, overwriting")
                self.origin = ORIGINS[id]
                self.logger.info(f"Added {id} to tracked origins")

            if id in TRACKED_STATICS:
                self.statics[id] = TRACKED_STATICS[id]
                self.logger.info(f"Added {id} to tracked statics")

        # Add the origin to the robots
        if self.origin is not None:
            for robot in self.robots.values():
                robot.setOrigin(self.origin)
                self.logger.info(f"Added origin {self.origin.id} to {robot.id}")

            for static in self.statics.values():
                static.setOrigin(self.origin)
                self.logger.info(f"Added origin {self.origin.id} to {static.id}")

        self.state = FRODO_Tracker_State.RUNNING
        self.callbacks.description_received.call()
        self.events.description_received.set()
        self.callbacks.initialized.call()
        self.events.initialized.set()


if __name__ == '__main__':
    tracker = FRODO_Tracker()
    tracker.init()
    tracker.start()

    while True:
        time.sleep(3)
