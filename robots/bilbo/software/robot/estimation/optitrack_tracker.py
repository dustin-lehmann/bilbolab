import dataclasses
import enum
from copy import copy

import numpy as np
import qmt

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.orientation.orientation_3d import vector_from_local_to_global, vector_from_global_to_local, \
    calculate_intersection
from extensions.optitrack.optitrack import RigidBodySample, OptiTrack
from robot.bilbo_common import BILBO_Common
from robot.bilbo_definitions import BILBO_OriginConfig, BILBO_ConfigurationState
from robot.config import BILBO_OptiTrack_Definition, BILBO_Config


# ======================================================================================================================
@dataclasses.dataclass
class OptiTrackOutlierFilterConfig:
    enabled: bool = True
    window_size: int = 3


class OptiTrackOutlierFilter:
    """Element-wise median filter over a sliding window of (x, y, z, theta, psi) states.

    Rejects single-sample position/orientation spikes caused by symmetric confusion
    at calibration volume edges. Angular channels (theta, psi) are unwrapped before
    computing the median to handle the +/-pi discontinuity correctly.
    """

    def __init__(self, config: OptiTrackOutlierFilterConfig = None):
        self.config = config or OptiTrackOutlierFilterConfig()
        self._window_size = self.config.window_size
        self._buffer = np.empty((self._window_size, 5))
        self._count = 0

    def update(self, x: float, y: float, z: float, theta: float, psi: float) -> tuple[float, float, float, float, float]:
        if not self.config.enabled:
            return x, y, z, theta, psi

        idx = self._count % self._window_size
        self._buffer[idx] = [x, y, z, theta, psi]
        self._count += 1

        if self._count < self._window_size:
            return x, y, z, theta, psi

        # Compute element-wise median with angular unwrapping for theta and psi
        buf = self._buffer.copy()
        oldest_idx = self._count % self._window_size
        for col in (3, 4):  # theta, psi
            ref = buf[oldest_idx, col]
            for i in range(self._window_size):
                diff = buf[i, col] - ref
                buf[i, col] = ref + (diff + np.pi) % (2 * np.pi) - np.pi

        result = np.median(buf, axis=0)

        # Rewrap angles to [-pi, pi]
        for col in (3, 4):
            result[col] = (result[col] + np.pi) % (2 * np.pi) - np.pi

        return result[0], result[1], result[2], result[3], result[4]

    def reset(self):
        self._count = 0


# ======================================================================================================================
@dataclasses.dataclass
class TrackedOrigin_State:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    orientation: np.ndarray = dataclasses.field(default_factory=lambda: np.asarray([1, 0, 0, 0]))


class TrackedOrigin:
    id: str
    definition: BILBO_OriginConfig
    state: TrackedOrigin_State
    tracking_valid: bool = False

    # === INIT =========================================================================================================
    def __init__(self, id: str, definition: BILBO_OriginConfig):
        self.id = id
        self.definition = definition
        self.state = TrackedOrigin_State(x=0, y=0, z=0, orientation=np.asarray([1, 0, 0, 0]))

    # === METHODS ======================================================================================================
    def update(self, data: RigidBodySample):
        # Check if tracking is valid
        if not data.valid:
            self.tracking_valid = False
            return

        x_start = np.asarray(data.markers[self.definition.x_start])
        x_end = np.asarray(data.markers[self.definition.x_end])
        y_start = np.asarray(data.markers[self.definition.y_start])
        y_end = np.asarray(data.markers[self.definition.y_end])

        # Origin is the intersection of the two axes
        origin = calculate_intersection(x_start, x_end, y_start, y_end)

        x_axis = x_end - origin
        y_axis = y_end - origin

        orientation = qmt.quatFrom2Axes(
            x=x_axis,
            y=y_axis,
            exactAxis='x'
        )

        local_offset = np.asarray([
            self.definition.offset_x,
            self.definition.offset_y,
            self.definition.offset_z + 0.5 * self.definition.marker_size
        ])

        # Rotate offset into global frame
        global_offset = vector_from_local_to_global(
            vector_in_local_frame=local_offset,
            local_orientation=orientation
        )

        # Final origin position in global frame
        position = origin + global_offset

        self.state = TrackedOrigin_State(
            x=position[0],
            y=position[1],
            z=position[2],
            orientation=orientation
        )
        self.tracking_valid = True


# ======================================================================================================================

@callback_definition
class TrackedBILBO_Callbacks:
    sample: CallbackContainer


@event_definition
class TrackedBILBO_Events:
    update: Event


class TrackedBILBO:
    id: str
    config: BILBO_Config
    state: BILBO_ConfigurationState
    tracking_valid: bool = False

    origin: TrackedOrigin | None = None

    callbacks: TrackedBILBO_Callbacks

    def __init__(self, id: str, config: BILBO_Config, origin: TrackedOrigin = None):
        self.id = id
        self.config = config
        self.state = BILBO_ConfigurationState(x=0, y=0, z=self.config.model.wheel_diameter / 2, theta=0, psi=0)
        self.origin = origin

        self.outlier_filter = OptiTrackOutlierFilter()

        self.callbacks = TrackedBILBO_Callbacks()
        self.events = TrackedBILBO_Events()

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, data: RigidBodySample):
        # Check if tracking is valid
        if not data.valid:
            self.tracking_valid = False
            self.outlier_filter.reset()
            return

        x_axis_point_start = np.asarray(data.markers[self.config.optitrack.point_x_axis_start])
        x_axis_point_end = np.asarray(data.markers[self.config.optitrack.point_x_axis_end])
        y_axis_point_start = np.asarray(data.markers[self.config.optitrack.point_y_axis_start])
        y_axis_point_end = np.asarray(data.markers[self.config.optitrack.point_y_axis_end])

        center_point = calculate_intersection(x_axis_point_start,
                                              x_axis_point_end,
                                              y_axis_point_start,
                                              y_axis_point_end)

        x_vector = x_axis_point_end - center_point
        y_vector = y_axis_point_end - center_point

        orientation = qmt.quatFrom2Axes(
            x=x_vector,
            y=y_vector,
            exactAxis='x'
        )

        wheel_mid_point_local = np.asarray([
            0,
            0,
            - (self.config.model.vertical_offset + 0.5 * self.config.optitrack.marker_size)
        ])

        wheel_mid_point_global = center_point + vector_from_local_to_global(
            vector_in_local_frame=wheel_mid_point_local,
            local_orientation=orientation
        )

        # Calculate the orientation relative to the origin
        if self.origin is not None:
            orientation = qmt.qmult(
                qmt.qinv(copy(self.origin.state.orientation)), orientation)

        psi, theta, _ = qmt.eulerAngles(orientation, axes='zyx', intrinsic=True)

        # Calculate the position relative to the origin
        if self.origin is not None:
            # 1. Get the global difference vector
            diff_vector = wheel_mid_point_global - np.asarray([
                self.origin.state.x,
                self.origin.state.y,
                self.origin.state.z
            ])


            # 2. Transform this difference vector into the local frame of the origin
            position = vector_from_global_to_local(
                vector_in_global_frame=diff_vector,
                target_frame_global_orientation=self.origin.state.orientation
            )
        else:
            position = wheel_mid_point_global

        x, y, z, theta, psi = self.outlier_filter.update(position[0], position[1], position[2], theta, psi)
        self.state = BILBO_ConfigurationState(x=x, y=y, z=z, theta=theta, psi=psi)

        self.tracking_valid = True
        self.callbacks.sample.call(self.state, self.tracking_valid)
        self.events.update.set(self.state)


# ======================================================================================================================
@callback_definition
class BILBO_OptitrackListener_Callbacks:
    sample: CallbackContainer


@event_definition
class BILBO_OptitrackListener_Events:
    sample: Event


class BILBO_OptitrackListener_Status(enum.StrEnum):
    RUNNING = 'RUNNING'
    DISABLED = 'DISABLED'
    ERROR = 'ERROR'
    NONE = 'NONE'


class BILBO_OptiTrackListener:
    optitrack: OptiTrack

    callbacks: BILBO_OptitrackListener_Callbacks
    events: BILBO_OptitrackListener_Events
    status: BILBO_OptitrackListener_Status = BILBO_OptitrackListener_Status.NONE

    # === INIT =========================================================================================================
    def __init__(self, common: BILBO_Common, server_address: str = 'palantir.lan'):
        self.optitrack = OptiTrack(server_address=server_address, max_sample_rate=50)
        self.callbacks = BILBO_OptitrackListener_Callbacks()
        self.events = BILBO_OptitrackListener_Events()
        self.common = common
        self.logger = Logger("OptiTrack Listener", "INFO")

        self.tracked_origin: TrackedOrigin | None = None
        self.tracked_object: TrackedBILBO | None = None

        self.optitrack.callbacks.description_received.register(self._description_received_callback)
        self.optitrack.events.sample.on(self._sample_callback, max_rate=50)

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self.optitrack.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        success = self.optitrack.start()
        if success:
            self.status = BILBO_OptitrackListener_Status.RUNNING
        else:
            self.status = BILBO_OptitrackListener_Status.DISABLED
            self.logger.warning("Cannot start Optitrack listener")

    # ------------------------------------------------------------------------------------------------------------------
    def get_state(self) -> BILBO_ConfigurationState | None:
        if self.tracked_object is not None:
            return self.tracked_object.state
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.optitrack.close()

    # === PRIVATE METHODS ==============================================================================================
    def _description_received_callback(self, rigid_bodies: dict):
        names = list(rigid_bodies.keys())
        self.logger.info(f"Description received: {len(names)} rigid bodies: {names}")
        self.logger.debug(f"Full rigid body descriptions: {rigid_bodies}")

        # Validate tracked origin against available rigid bodies
        if self.tracked_origin is not None:
            if self.tracked_origin.id not in rigid_bodies:
                self.logger.warning(f"Origin ID {self.tracked_origin.id} not found in OptiTrack Rigid Bodies")

        # Get the tracked object for the robot
        if self.common.id in rigid_bodies:
            self.logger.info(f"ID {self.common.id} found in OptiTrack Rigid Bodies")
            self.tracked_object = TrackedBILBO(id=self.common.id,
                                               config=self.common.config,
                                               origin=self.tracked_origin)
        else:
            self.logger.warning(f"ID {self.common.id} not found in OptiTrack Rigid Bodies")
            self.status = BILBO_OptitrackListener_Status.ERROR
            return

    # ------------------------------------------------------------------------------------------------------------------
    def _sample_callback(self, sample: dict[str, RigidBodySample]):
        if self.tracked_origin is not None:
            if self.tracked_origin.id in sample:
                self.tracked_origin.update(sample[self.tracked_origin.id])
            else:
                self.logger.warning(f"ID {self.tracked_origin.id} not found in OptiTrack Rigid Bodies Sample")

        if self.tracked_object is not None:
            if self.tracked_object.id in sample:
                if sample[self.tracked_object.id].valid:
                    self.tracked_object.update(sample[self.tracked_object.id])
                    self.callbacks.sample.call(self.tracked_object.state)
                    self.events.sample.set(self.tracked_object.state)
            else:
                self.logger.warning(f"ID {self.tracked_object.id} not found in OptiTrack Rigid Bodies Sample")
