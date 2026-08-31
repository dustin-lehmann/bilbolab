import dataclasses
import enum
import os
import sys
import threading
import time
from typing import List, Optional, Tuple

import cv2
import cv2.aruco as arc
import numpy as np

# === LOCAL IMPORTS ====================================================================================================
from robot.sensing.camera.pycamera import PyCamera, PyCameraType
from robot.utilities.video_streamer.video_streamer import VideoStreamer
from robot.sensing.aruco.calibration.calibration import CameraCalibrationData, ArucoCalibration
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import Event, event_definition
from core.utils.logging_utils import Logger
from core.utils.time import IntervalTimer, Timer, TimeoutTimer
from core.utils.exit import register_exit_callback

# ======================================================================================================================
DEBUG = False  # Set to True to enable debug logging


# === CALLBACKS and EVENTS =============================================================================================
@callback_definition
class ArucoDetector_Callbacks:
    new_measurement: CallbackContainer


@event_definition
class ArucoDetector_Events:
    new_measurement: Event


@dataclasses.dataclass
class ArucoMeasurement:
    """
    A single ArUco marker pose estimate (camera frame).
    - rotation_vec, translation_vec are OpenCV Rodrigues vectors (rvec/tvec) for the marker.
    - distance is ||tvec|| in the same units as the calibration/marker size (typically meters).
    """
    marker_id: int
    rotation_vec: np.ndarray
    translation_vec: np.ndarray
    distance: float


class ArucoDetectorStatus(enum.StrEnum):
    OK = "OK"
    ERROR = "ERROR"

# === ArucoDetector ====================================================================================================
class ArucoDetector:
    """
    Simple ArUco detector loop that:
      - Captures frames from a PyCamera
      - Detects markers
      - Estimates pose using camera calibration
      - Emits callbacks and events with the current measurements
      - Optionally serves an overlay image (markers drawn)
    """
    status: ArucoDetectorStatus = ArucoDetectorStatus.ERROR
    camera: PyCamera
    measurements: List[ArucoMeasurement]
    callbacks: ArucoDetector_Callbacks
    events: ArucoDetector_Events
    calibration_data: CameraCalibrationData

    Ts: float
    loop_time: float

    timer: IntervalTimer
    _exit: bool = False
    _running: bool = False

    _overlay_frame_lock = threading.Lock()
    frame_out: Optional[np.ndarray] = None

    # --- DEBUG STATE -----------------------------------------------------------------------------------------------
    _loop_times: List[float]
    _last_debug_report: float
    _marker_state: dict  # marker_id -> { "seen": bool, "misses": int }

    def __init__(
            self,
            camera: PyCamera,
            image_resolution: tuple | list | None = None,
            aruco_dict: int = arc.DICT_4X4_1000,
            marker_size: float = 0.08,
            run_in_thread: bool = True,
            Ts: float = 0.1,
            allowed_marker_ids: list | None = None,
    ):
        self.Ts = Ts
        self.camera = camera
        self.run_in_thread = run_in_thread

        self.logger = Logger("ArucoDetector", "DEBUG")

        # ArUco setup
        self.marker_size = float(marker_size)
        self.dictionary = arc.getPredefinedDictionary(aruco_dict)

        self.detector_params = arc.DetectorParameters()
        self.detector_params.adaptiveThreshWinSizeMin = 3
        self.detector_params.adaptiveThreshWinSizeMax = 23
        self.detector_params.adaptiveThreshWinSizeStep = 10
        self.detector_params.minMarkerPerimeterRate = 0.03
        self.detector_params.maxMarkerPerimeterRate = 4.0
        self.detector_params.polygonalApproxAccuracyRate = 0.03

        self.detector = arc.ArucoDetector(self.dictionary, self.detector_params)

        # Load calibration data
        calibration_name = ArucoCalibration.getCalibrationName(self.camera.version, image_resolution)
        self.calibration_data = ArucoCalibration.readCalibrationFile(calibration_name)

        if self.calibration_data is None:
            self.logger.error(
                f"No Calibration Data found for Camera Version {self.camera.version} and Resolution {image_resolution}"
            )
            sys.exit(1)

        # Runtime state
        self.measurements = []
        self.loop_time = 0.0
        self.timer = IntervalTimer(self.Ts, raise_race_condition_error=False)
        self.callbacks = ArucoDetector_Callbacks()
        self.events = ArucoDetector_Events()

        self.allowed_marker_ids = set(allowed_marker_ids) if allowed_marker_ids is not None else None

        self.timeout_timer = TimeoutTimer(timeout_time=2, timeout_callback=self._onTimeout)
        # Debug state
        self._loop_times = []
        self._last_debug_report = time.time()
        self._marker_state = {}

        # Worker thread
        self.task = threading.Thread(target=self._task, name="ArucoDetectorThread", daemon=True)

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    def start(self):
        if self._running:
            self.logger.debug("ArucoDetector already running; start() ignored.")
            return
        self.camera.start()
        self._exit = False
        self.timer.reset()
        self.task.start()
        self._running = True
        self.logger.info("Aruco Detector started!")
        if self.allowed_marker_ids is not None:
            self.logger.info(f"Allowed Marker IDs: {self.allowed_marker_ids}")

        self.status = ArucoDetectorStatus.OK

    def close(self, *args, **kwargs):
        if not self._running:
            return
        self.logger.info("Closing Aruco Detector...")
        self._exit = True
        try:
            if self.task.is_alive():
                self.task.join(timeout=2.0)
        except Exception as e:
            self.logger.warning(f"Join failed: {e}")
        self._running = False

    def getOverlayFrame(self) -> Optional[bytes]:
        with self._overlay_frame_lock:
            if self.frame_out is not None:
                return self.camera.getImageBufferBytes(self.frame_out)
            return None

    def testMaximumDetectionRate(self, N: int = 100) -> dict:
        times = []
        self.logger.info(f"Benchmarking ArucoDetector for {N} iterations...")
        for i in range(N):
            t0 = time.perf_counter()
            frame = self.camera.takeFrame()
            self._arucoDetection(frame)
            dt = time.perf_counter() - t0
            times.append(dt)
        mean_t = float(np.mean(times))
        min_t = float(np.min(times))
        max_t = float(np.max(times))
        fps_est = 1.0 / mean_t if mean_t > 0 else 0.0
        self.logger.info(
            f"Aruco benchmark ({N} iters): "
            f"mean={mean_t * 1000:.2f} ms, min={min_t * 1000:.2f} ms, "
            f"max={max_t * 1000:.2f} ms → ~{fps_est:.1f} FPS"
        )
        return {
            "mean_time_s": mean_t,
            "min_time_s": min_t,
            "max_time_s": max_t,
            "fps_estimate": fps_est,
        }

    # === PRIVATE METHODS ==============================================================================================
    def _task(self):
        first_run = True
        self.timer.reset()

        while not self._exit:
            t0 = time.perf_counter()
            self.measurements = []
            frame = self.camera.takeFrame()

            overlay = self._arucoDetection(frame)

            with self._overlay_frame_lock:
                self.frame_out = overlay

            try:
                self.callbacks.new_measurement.call(self.measurements)
            except Exception as e:
                self.logger.warning(f"Callback error: {e}")
            try:
                self.events.new_measurement.set(self.measurements)
            except Exception as e:
                self.logger.warning(f"Event set error: {e}")

            self.loop_time = time.perf_counter() - t0

            if DEBUG:
                self._debug_update()

            if not first_run and self.loop_time > self.Ts:
                self.logger.warning(f"Aruco Detector loop exceeded Ts: {self.loop_time:.3f} s > {self.Ts:.3f} s")

            first_run = False
            self.timeout_timer.reset()
            self.timer.sleep_until_next()

    # ------------------------------------------------------------------------------------------------------------------
    def _debug_update(self):
        """Update loop time stats and marker state."""
        self._loop_times.append(self.loop_time)
        now = time.time()

        # Report every 5s
        if now - self._last_debug_report >= 5.0 and self._loop_times:
            mean_t = float(np.mean(self._loop_times))
            max_t = float(np.max(self._loop_times))
            self.logger.info(
                f"[DEBUG] Loop stats (last 5s): mean={mean_t * 1000:.2f} ms, max={max_t * 1000:.2f} ms"
            )
            self._loop_times.clear()
            self._last_debug_report = now

        # Marker tracking
        current_ids = {m.marker_id for m in self.measurements}
        for mid in current_ids:
            state = self._marker_state.get(mid, {"seen": False, "misses": 0})
            if not state["seen"]:
                self.logger.info(f"[DEBUG] Marker {mid} seen")
            state["seen"] = True
            state["misses"] = 0
            self._marker_state[mid] = state

        # Update misses and check for lost markers
        for mid, state in list(self._marker_state.items()):
            if mid not in current_ids:
                state["misses"] += 1
                if state["seen"] and state["misses"] >= 3:
                    self.logger.info(f"[DEBUG] Marker {mid} lost")
                    state["seen"] = False
                self._marker_state[mid] = state

    # ------------------------------------------------------------------------------------------------------------------
    def _arucoDetection(self, frame: np.ndarray) -> np.ndarray | None:
        if frame is None:
            return frame
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        marker_corners, marker_ids, rejected = self.detector.detectMarkers(gray)

        if marker_ids is not None and len(marker_ids) > 0:

            if self.allowed_marker_ids is not None:
                # marker_ids is shape (N, 1); make a flat view for masking
                ids_flat = marker_ids.flatten()
                mask = np.array([mid in self.allowed_marker_ids for mid in ids_flat], dtype=bool)

                # If nothing allowed is present, bail early (no drawing / no pose)
                if not np.any(mask):
                    return frame

                # Keep only allowed ids/corners; keep shapes consistent for OpenCV
                marker_ids = marker_ids[mask].reshape(-1, 1)
                marker_corners = [c for c, keep in zip(marker_corners, mask) if keep]

            arc.drawDetectedMarkers(frame, marker_corners, marker_ids)
            rvecs, tvecs, _objpts = cv2.aruco.estimatePoseSingleMarkers(
                marker_corners,
                self.marker_size,
                self.calibration_data.camera_matrix,
                self.calibration_data.dist_coeff,
            )
            rvecs = np.squeeze(rvecs, axis=1)
            tvecs = np.squeeze(tvecs, axis=1)
            for i, marker_id in enumerate(marker_ids):
                rvec = rvecs[i]
                tvec = tvecs[i]
                distance = float(np.linalg.norm(tvec))
                self.measurements.append(ArucoMeasurement(int(marker_id[0]), rvec, tvec, distance))
        return frame

    # ------------------------------------------------------------------------------------------------------------------
    def _onTimeout(self):
        self.logger.warning("ArucoDetector timeout!")
        self.status = ArucoDetectorStatus.ERROR
# ======================================================================================================================
timer1 = Timer()


def print_measurements(measurements: List[ArucoMeasurement]):
    if timer1 > 0.25:
        timer1.reset()
        if not measurements:
            return
        for m in measurements:
            print(f"Marker ID: {m.marker_id}, Distance: {(m.distance * 100):.1f} cm")


if __name__ == '__main__':
    camera = PyCamera(
        PyCameraType.GS,
        (728, 544),
        exposure_time=1000,
        gain=100,
        frame_rate=60,
        image_format="gray",
    )

    arc_detector = ArucoDetector(
        camera=camera,
        Ts=0.025,
        image_resolution=camera.resolution,
        aruco_dict=arc.DICT_4X4_1000,
        marker_size=0.08,
    )
    camera.init()
    camera.start()
    arc_detector.callbacks.new_measurement.register(print_measurements)
    arc_detector.start()
    # arc_detector.testMaximumDetectionRate()

    streamer = VideoStreamer()
    streamer.image_fetcher = arc_detector.getOverlayFrame
    streamer.start()
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        arc_detector.close()
