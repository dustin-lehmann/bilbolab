import dataclasses
import threading
import time
import cv2
import cv2.aruco as arc
import numpy as np

# === LOCAL IMPORTS ====================================================================================================
from archive.robot_old.sensing.camera.pycamera import PyCamera, PyCameraType
from archive.robot_old.utilities.video_streamer.video_streamer import VideoStreamer
from archive.robot_old.sensing.aruco.calibration.calibration import CameraCalibrationData, ArucoCalibration
from utils.callbacks import callback_handler, CallbackContainer
from utils.events import ConditionEvent, event_handler
from utils.logging_utils import Logger
from utils.time import IntervalTimer, Timer
from utils.exit import ExitHandler

# ======================================================================================================================
logger = Logger("Aruco")
logger.setLevel('DEBUG')


# === CALLBACKS and EVENTS =============================================================================================
@callback_handler
class ArucoDetector_Callbacks:
    new_measurement: CallbackContainer


@event_handler
class ArucoDetector_Events:
    new_measurement: ConditionEvent


@dataclasses.dataclass
class ArucoMeasurement:
    marker_id: int
    rotation_vec: np.array
    translation_vec: np.array
    distance: float


# === ArucoDetector ====================================================================================================
class ArucoDetector:
    camera: PyCamera
    measurements: list[ArucoMeasurement]
    callbacks: ArucoDetector_Callbacks
    events: ArucoDetector_Events
    calibration_data: CameraCalibrationData

    Ts: float
    loop_time: float

    timer: IntervalTimer
    _exit: bool = False

    _overlay_frame_lock = threading.Lock()
    frame_out: np.array = None

    def __init__(self, camera_version: PyCameraType = PyCameraType.V3, image_resolution: tuple = None,
                 aruco_dict: int = arc.DICT_4X4_1000,
                 marker_size: float = 0.08, run_in_thread: bool = True, Ts: float = 0.1, exposure_time = None, gain=None):

        self.Ts = Ts
        # init program parameters
        self.camera_version = camera_version
        self.run_in_thread = run_in_thread

        # Init Aruco Detector
        self.marker_size = marker_size
        self.dictionary = arc.getPredefinedDictionary(aruco_dict)
        self.detector_params = arc.DetectorParameters()

        self.detector_params.adaptiveThreshWinSizeMin = 3
        self.detector_params.adaptiveThreshWinSizeMax = 23
        self.detector_params.adaptiveThreshWinSizeStep = 10
        self.detector_params.minMarkerPerimeterRate = 0.03
        self.detector_params.maxMarkerPerimeterRate = 4.0
        self.detector_params.polygonalApproxAccuracyRate = 0.03

        self.detector = arc.ArucoDetector(self.dictionary, self.detector_params)

        # Initialize the camera
        if camera_version == PyCameraType.V3:
            autofocus = True
        else:
            autofocus = False
        self.camera = PyCamera(version=camera_version, resolution=image_resolution, auto_focus=autofocus, exposure_time=exposure_time, gain=gain)

        # Load calibration data
        calibration_name = ArucoCalibration.getCalibrationName(camera_version, image_resolution)
        self.calibration_data = ArucoCalibration.readCalibrationFile(calibration_name)

        if self.calibration_data is None:
            raise Exception(
                f"No Calibration Data found for Camera Version {camera_version} and Resolution {image_resolution}")

        # init tasks
        self.task = threading.Thread(target=self._task)
        self.exit = ExitHandler()
        self.exit.register(self.close)
        self.timer = IntervalTimer(self.Ts, catch_race_condition=False)
        self.loop_time = 0
        self.callbacks = ArucoDetector_Callbacks()
        self.events = ArucoDetector_Events()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        """start Aruco Detector, activate configured features"""
        self.camera.start()
        self.task.start()
        logger.info("Aruco Detector started!")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        logger.info("Close Aruco Detector")
        self._exit = True
        self.task.join()

    # ------------------------------------------------------------------------------------------------------------------
    def getOverlayFrame(self):
        with self._overlay_frame_lock:
            if self.frame_out is not None:
                return self.camera.getImageBufferBytes(self.frame_out)
            else:
                return None

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        first_run = True  # Detect the first run, because it takes longer
        self.timer.reset()
        while not self._exit:

            # time1 = time.perf_counter()
            # Reset the measurement
            self.measurements = []

            # Capture a camera frame
            frame = self.camera.takeFrame()

            # Copy the frame to not mess with the original frame

            frame_out = np.copy(frame)

            # Run Aruco Detection
            time_11 = time.perf_counter()
            marker_corners, marker_ids, rejected_candidates = self.detector.detectMarkers(frame)
            # print(f"Aruco Detection took {((time.perf_counter() - time_11) * 1000):.2f} ms")

            # Check if Marker IDs have been detected
            if marker_ids is not [] and marker_ids is not None:

                # Generate an overlay frame with detected markers
                frame_out = arc.drawDetectedMarkers(frame_out, marker_corners, marker_ids)

                # Run Aruco Measurement
                rotation_vec, translation_vec, objpts = cv2.aruco.estimatePoseSingleMarkers(marker_corners,
                                                                                            self.marker_size,
                                                                                            self.calibration_data.camera_matrix,
                                                                                            self.calibration_data.dist_coeff)
                for i, marker_id in enumerate(marker_ids):
                    self.measurements.append(self._processMeasurement(marker_id, translation_vec[i], rotation_vec[i]))

            else:
                # No markers have been detected
                ...

            with self._overlay_frame_lock:
                self.frame_out = frame_out

            # self.callbacks.new_measurement.call(self.measurements)
            self.events.new_measurement.set(self.measurements)

            # print(f"Aruco took {((time.perf_counter() - time1) * 1000):.2f} ms")
            self.loop_time = self.timer.time

            if not first_run and self.loop_time > self.Ts:
                ...

            if first_run:
                first_run = False

            self.timer.sleep_until_next()

    # ------------------------------------------------------------------------------------------------------------------
    def _captureImage(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _runMeasurement(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _processMeasurement(marker_id: int,
                            translation_vec: np.ndarray,
                            rotation_vec: np.ndarray) -> ArucoMeasurement:

        distance = float(np.linalg.norm(translation_vec))
        return ArucoMeasurement(marker_id, rotation_vec, translation_vec, distance)


# ======================================================================================================================
timer1 = Timer()


def print_measurements(measurements):
    if timer1 > 0.25:
        timer1.reset()
        if len(measurements) == 0:
            return

        for measurement in measurements:
            print(f"Marker ID: {measurement.marker_id}, Distance: {(measurement.distance * 100):.1f} cm")


# ======================================================================================================================
if __name__ == '__main__':
    arc_detector = ArucoDetector(camera_version=PyCameraType.GS, marker_size=0.08, image_resolution=(960, 540),
                                 Ts=0.05, exposure_time = 2000, gain= 10)
    arc_detector.callbacks.new_measurement.register(print_measurements)
    arc_detector.start()

    streamer = VideoStreamer()
    streamer.image_fetcher = arc_detector.getOverlayFrame
    streamer.start()

    while True:
        time.sleep(10)
