import enum
import threading
import time

from core.utils.callbacks import CallbackContainer, Callback, callback_definition
from core.utils.events import EventContainer, Event, event_definition
from core.utils.network import getInterfaceIP


def disableLibcameraLogs():
    import os
    os.environ["LIBCAMERA_LOG_LEVELS"] = "*:4"


disableLibcameraLogs()

import cv2
from libcamera import controls
from picamera2 import picamera2
from robot.utilities.video_streamer.video_streamer import VideoStreamer
from core.utils.logging_utils import Logger

# ======================================================================================================================
logger = Logger("PyCamera")
logger.setLevel('DEBUG')

class PyCameraType(enum.StrEnum):
    V1 = 'V1',
    V2 = 'V2',
    V3 = 'V3',
    GS = 'GS',


class PyCameraNativeResolutions(enum.Enum):
    V1 = (1280, 720)
    V2 = (1640, 1232)
    V3 = (2304, 1296)
    GS = (1456, 1088)


@callback_definition
class PyCameraCallbacks:
    frame: CallbackContainer

@event_definition
class PyCameraEvents(EventContainer):
    frame: Event

# ======================================================================================================================
class PyCamera:
    """
    image_format:
        - "rgb":  return a standard 3-channel BGR image (good for JPEG/OpenCV). Internally we request RGB888.
        - "gray": return a single-channel grayscale image. Internally we request a YUV420 stream and take the Y plane.
    """
    picam: picamera2.Picamera2
    resolution: tuple
    version: PyCameraType
    running: bool = False
    _camera_lock: threading.Lock

    def __init__(
            self,
            version: PyCameraType,
            resolution: tuple,
            auto_focus: bool = False,
            lens_position: float = 0.0,
            exposure_time: int = None,
            gain: int | float = None,
            image_format: str = "rgb",
            frame_rate: int = 60,
    ):

        self.logger = Logger("PyCamera", "INFO")

        self.version = version
        self.resolution = resolution
        self.image_format = image_format.lower().strip()
        self.frame_rate = frame_rate
        self.gain = gain
        self.exposure_time = exposure_time
        self.auto_focus = auto_focus
        self.lens_position = lens_position

        if self.image_format not in ("rgb", "gray"):
            raise ValueError('image_format must be "rgb" or "gray"')

        self.picam = picamera2.Picamera2()

        # Decide the libcamera "main" stream format from the user's desired output
        # - For "rgb"  -> RGB888 (then we hand BGR to OpenCV by swapping channels)
        # - For "gray" -> YUV420 (planar). We will extract the Y plane (true luma) and return it.
        main_format = "RGB888" if self.image_format == "rgb" else "YUV420"

        # Keep your per-sensor raw sizes as-is.
        if self.version == PyCameraType.V2:
            self.picam_config = self.picam.create_video_configuration(
                raw={"size": (1640, 1232)},
                main={"format": main_format, "size": resolution},
                buffer_count=5,
            )
        elif self.version == PyCameraType.V3:
            self.picam_config = self.picam.create_video_configuration(
                raw={"size": (2304, 1296)},
                main={"format": main_format, "size": resolution},
                buffer_count=5,
            )
        elif self.version == PyCameraType.V1:
            self.picam_config = self.picam.create_video_configuration(
                raw={"size": (2592, 1944)},
                main={"format": main_format, "size": resolution},
                buffer_count=5,
            )
        elif self.version == PyCameraType.GS:
            self.picam_config = self.picam.create_video_configuration(
                raw={"size": (1456, 1088)},
                main={"format": main_format, "size": resolution},
                buffer_count=5,
            )
        else:
            raise ValueError("Unknown camera type")

        self.picam.configure(self.picam_config)

        new_controls = {}
        if exposure_time is not None:
            new_controls["ExposureTime"] = exposure_time
        if gain is not None:
            new_controls["AnalogueGain"] = gain
        # The GS (Global Shutter) camera has a fixed lens and does not advertise
        # focus controls; only set them when libcamera actually supports them.
        if "AfMode" in self.picam.camera_controls:
            if auto_focus:
                new_controls["AfMode"] = controls.AfModeEnum.Continuous
            else:
                new_controls["AfMode"] = controls.AfModeEnum.Manual
                new_controls["LensPosition"] = lens_position

        if frame_rate is not None:
            new_controls["FrameRate"] = frame_rate

        self.picam.set_controls(new_controls)

        # self.picam.set_controls({
        #     "NoiseReductionMode": 0,  # disable auto NR
        #     "ExposureValue": 0.0,
        #     "Brightness": 0.0,
        #     "Contrast": 1.0,
        # })

        self._camera_lock = threading.Lock()

        # Cache the configured main size for plane slicing (avoids problems with padded stride)
        self._w, self._h = self.picam_config["main"]["size"]

        self.callbacks = PyCameraCallbacks()
        self.events = PyCameraEvents()

        self.logger.info(
            f"PyCamera initialized: {self.resolution} @ {self.version} (image_format={self.image_format}, auto_focus={auto_focus}, exposure_time={exposure_time}, gain={gain})")

    # === METHODS ======================================================================================================
    def init(self):
        ...

    def start(self):
        if self.running:
            return
        self.running = True
        self.picam.start()
        logger.info("PyCamera started!")
        self.getCameraSettings()

    def getCameraSettings(self):
        """
        Returns a dict with:
          - static/class config: version, resolution, image_format
          - requested controls (what you asked for)
          - actual runtime metadata (what the camera is doing)
          - derived values like fps
        """
        md = self.picam.capture_metadata() or {}

        # Metadata values (may be None if not supported by the sensor/driver)
        exposure_time_us = md.get("ExposureTime")  # µs
        analogue_gain = md.get("AnalogueGain")
        digital_gain = md.get("DigitalGain")
        colour_gains = md.get("ColourGains")  # (r, b) if AWB is on
        frame_duration_us = md.get("FrameDuration")  # µs
        af_mode_md = md.get("AfMode")
        af_state_md = md.get("AfState")

        fps = (1e6 / frame_duration_us) if frame_duration_us else None

        data = {
            "camera": {
                "version": str(self.version),
                "resolution": tuple(self.resolution),
                "image_format": self.image_format,
            },
            "requested_controls": {
                # what you asked libcamera to do
                "exposure_time_us": self.exposure_time,
                "analogue_gain": self.gain,
                "auto_focus": self.auto_focus,
                "frame_rate_fps": self.frame_rate,
            },
            "actual_metadata": {
                # what the camera is actually doing now
                "exposure_time_us": exposure_time_us,
                "analogue_gain": analogue_gain,
                "digital_gain": digital_gain,
                "colour_gains": colour_gains,
                "frame_duration_us": frame_duration_us,
                "fps": fps,
                "af_mode": af_mode_md,  # may be None if not supported
                "af_state": af_state_md,  # may be None if not supported
            },
        }

        # Optional: quick log for human-friendly visibility
        try:
            self.logger.info(
                "Camera settings | "
                f"cfg fps={self.frame_rate} | actual fps={fps:.1f} | "
                f"exp={exposure_time_us}us | again={analogue_gain} | dgain={digital_gain} | "
                f"AF mode/state={af_mode_md}/{af_state_md}"
            )
        except Exception:
            # fps can be None the first few frames; don't let logging raise.
            pass

        return data

    def _capture_rgb(self):
        # Picamera2 returns RGB when the stream is RGB888. OpenCV expects BGR for correct colors,
        # so we convert to BGR in-place for consistency with typical OpenCV pipelines.
        rgb = self.picam.capture_array()  # HxWx3 (may have stride padding, but width is OK)
        # bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return rgb

    def _capture_gray_from_yuv420(self):
        """
        For YUV420 the buffer returned by Picamera2 is a 2D array with shape (h*3/2, stride),
        where:
            - first h rows are the full-resolution Y (luma) plane
            - remaining h/2 rows contain interleaved U and V at half resolution

        If you naively treat that buffer as an image, it looks "taller" (h*1.5) and shows
        the subsampled chroma planes stacked under the luma—this is exactly the "copies below"
        you were seeing.

        We take only the Y plane and crop to the configured width to remove stride padding.
        """
        yuv = self.picam.capture_array()  # shape: (h*3/2, stride)
        h, w = self._h, self._w
        y_plane = yuv[:h, :w]  # drop padding and chroma planes
        return y_plane

    def takeFrame(self):
        with self._camera_lock:
            if self.image_format == "gray":
                frame = self._capture_gray_from_yuv420()
            else:  # "rgb"
                frame = self._capture_rgb()

        self.callbacks.frame.call(frame)
        self.events.frame.set(frame)
        return frame

    @staticmethod
    def getImageBuffer(frame):
        # Works for both BGR color and single-channel grayscale frames
        _, buffer = cv2.imencode('.jpg', frame)
        return buffer

    def getImageBufferBytes(self, frame):
        return self.getImageBuffer(frame).tobytes()


# ======================================================================================================================
class PyCameraStreamer(VideoStreamer):
    pycamera: PyCamera

    def __init__(self, pycamera: PyCamera = None, resolution: tuple = None):
        super().__init__(self.getCameraFrame, max_clients=1)

        self.camera = pycamera

    def start(self):
        if not self.camera.running:
            self.camera.start()

        super().start()

    def getCameraFrame(self):
        frame = self.camera.takeFrame()
        return self.camera.getImageBufferBytes(frame)


if __name__ == '__main__':
    # Example: GS camera, grayscale output using the Y plane from YUV420.
    camera = PyCamera(
        PyCameraType.GS,
        (1456, 1088),
        exposure_time=2000,
        gain=10,
        frame_rate=60,
        image_format="rgb",  # <- choose "rgb" or "gray"
    )

    camera.init()
    camera.start()


    # for i in range(10):
    #     time1 = time.perf_counter()
    #     frame = camera.takeFrame()
    #     time2 = time.perf_counter()
    #     print(f"Time to capture frame: {((time2 - time1) * 1000):.1f} ms")

    #
    streamer = PyCameraStreamer(pycamera=camera)
    streamer.start()
    while True:
        time.sleep(10)
