import copy
import dataclasses
import threading
import time

import numpy as np
import qmt

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dict_utils import optimized_deepcopy
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.time import TimeoutTimer
from robot.common import FRODO_Common, ErrorSeverity
from robot.definitions import get_all_aruco_ids
from robot.sensing.aruco.aruco_detector import ArucoDetector, ArucoDetectorStatus
from robot.sensing.camera.pycamera import PyCamera
from robot.sensing.measurement_model import measurement_model_from_file
from robot.utilities.orientation import is_mostly_z_axis


@dataclasses.dataclass
class FRODO_SensorStatus:
    aruco_detector: ArucoDetectorStatus = ArucoDetectorStatus.ERROR


# ======================================================================================================================
@dataclasses.dataclass(frozen=True)
class FRODO_ArucoMeasurement:
    measured_aruco_id: int
    position: np.ndarray
    psi: float
    uncertainty_position: np.ndarray
    uncertainty_psi: float


# ======================================================================================================================
@dataclasses.dataclass
class FRODO_Measurements_Sample:
    status: FRODO_SensorStatus
    aruco_measurements: list[FRODO_ArucoMeasurement]


# ======================================================================================================================
@callback_definition
class FRODO_Sensors_Callbacks:
    new_aruco_measurement: CallbackContainer


@event_definition
class FRODO_Sensors_Events:
    new_aruco_measurement: Event


# === FRODO SENSORS ====================================================================================================
class FRODO_Sensors:
    status: FRODO_SensorStatus
    common: FRODO_Common
    logger: Logger
    camera: PyCamera
    aruco_detector: ArucoDetector
    aruco_measurements: list[FRODO_ArucoMeasurement]

    callbacks: FRODO_Sensors_Callbacks
    events: FRODO_Sensors_Events

    data_lock: threading.Lock

    # === INIT =========================================================================================================
    def __init__(self, common: FRODO_Common):
        self.common = common
        self.logger = Logger("SENSORS", "INFO")
        self.callbacks = FRODO_Sensors_Callbacks()
        self.events = FRODO_Sensors_Events()

        self.settings = common.getDefinitions()
        self.data_lock = threading.Lock()

        # Create the camera
        self.camera = PyCamera(version=self.settings.camera.camera,
                               resolution=self.settings.camera.resolution,
                               auto_focus=self.settings.camera.autofocus,
                               exposure_time=self.settings.camera.exposure_time,
                               gain=self.settings.camera.gain,
                               image_format=self.settings.camera.image_format,
                               frame_rate=self.settings.camera.frame_rate, )

        all_marker_ids = get_all_aruco_ids()

        self.aruco_detector = ArucoDetector(
            camera=self.camera,
            Ts=1 / self.settings.aruco.detection_rate,
            image_resolution=self.settings.camera.resolution,
            aruco_dict=self.settings.aruco.dictionary,
            marker_size=self.settings.aruco.marker_size,
            allowed_marker_ids=all_marker_ids,
        )

        self.aruco_measurements = []

        self.vision_measurement_model = measurement_model_from_file('./model.yaml', local=True)

        self.timeout_timer = TimeoutTimer(timeout_time=1, timeout_callback=self._onArucoTimeout)
        self.aruco_detector.callbacks.new_measurement.register(self._onNewArucoMeasurement)

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self.camera.init()
        self.aruco_detector.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info("Starting FRODO Sensors")
        self.camera.start()
        self.aruco_detector.start()
        self.timeout_timer.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def status(self):
        return FRODO_SensorStatus(
            aruco_detector=self.aruco_detector.status,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self) -> FRODO_Measurements_Sample:
        with self.data_lock:
            sample = FRODO_Measurements_Sample(
                status=self.status,
                aruco_measurements=copy.copy(self.aruco_measurements),
            )
        return sample

    # === PRIVATE METHODS ==============================================================================================
    def _onNewArucoMeasurement(self, measurements, *args, **kwargs):
        self.timeout_timer.reset()
        self._processArucoMeasurements(measurements)

    # ------------------------------------------------------------------------------------------------------------------
    def _onArucoTimeout(self):
        self.common.errorHandler(ErrorSeverity.MAJOR, "Timeout on Aruco Detector!")

    # ------------------------------------------------------------------------------------------------------------------
    def _processArucoMeasurements(self, measurements):
        aruco_measurements_processed = []

        for measurement in measurements:
            time1 = time.perf_counter()
            # Get the 2D measurement
            x = measurement.translation_vec[2] + self.settings.camera.camera_to_center_distance
            y = -measurement.translation_vec[0]

            position = np.asarray([x, y], dtype=np.float32)

            angle = np.linalg.norm(measurement.rotation_vec)
            axis = measurement.rotation_vec / angle

            q_camera_marker = qmt.quatFromAngleAxis(angle, axis)

            q_ME_M = qmt.qmult(qmt.quatFromAngleAxis(angle=np.deg2rad(90), axis=np.asarray([0, 0, 1])),
                               qmt.quatFromAngleAxis(angle=np.deg2rad(90), axis=np.asarray([1, 0, 0])))

            q_CE_C = qmt.qmult(qmt.quatFromAngleAxis(angle=np.deg2rad(-90), axis=np.asarray([1, 0, 0])),
                               qmt.quatFromAngleAxis(angle=np.deg2rad(90), axis=np.asarray([0, 1, 0])))

            q_CE_ME = qmt.qmult(q1=qmt.qmult(q1=q_CE_C, q2=q_camera_marker),
                                q2=qmt.qinv(q_ME_M))

            axis = qmt.quatAxis(q_CE_ME).squeeze()
            angle = qmt.quatAngle(q_CE_ME)

            # Check if the axis is mostly around the z-axis
            if not is_mostly_z_axis(axis):
                self.logger.debug(f"Aruco Measurement not mostly around z-axis: {measurement}")
                continue

            psi = qmt.wrapToPi(angle - np.deg2rad(180))

            # Correct the angle with the direction of the z-axis:
            if axis[2] < 0:
                psi = -psi

            state = self.common.getDynamicState()

            if state is None:
                continue

            covariance = self.vision_measurement_model.covariance.covariance(
                measurement=np.asarray([x, y, psi]),
                v=state.v,
                psi_dot=state.psi_dot,
            )

            measurement_processed = FRODO_ArucoMeasurement(
                measured_aruco_id=measurement.marker_id,
                position=position,
                psi=psi,
                uncertainty_position=covariance[0:2, 0:2],
                uncertainty_psi=covariance[2, 2]
            )
            aruco_measurements_processed.append(measurement_processed)

        with self.data_lock:
            self.aruco_measurements = aruco_measurements_processed
