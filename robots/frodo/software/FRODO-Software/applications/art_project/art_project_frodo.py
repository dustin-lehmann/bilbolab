# 1. Goal (05.08.2026)
# - Detect a line (Whether a line is there or not, estimate our deviation from the line)
import threading
import time
from typing import Optional

import cv2
import numpy as np

from robot.frodo import FRODO
from robot.sensing.camera.pycamera import PyCamera
from robot.utilities.video_streamer.video_streamer import VideoStreamer
from core.utils.logging_utils import Logger
from core.utils.network import getInterfaceIP


# 2. Goal
# - Line Following Controller


class AP_LineDetector:

    streamer: Optional[VideoStreamer]
    stream_port: int

    _stream_frame_lock = threading.Lock()
    frame_out: Optional[np.ndarray] = None

    # ==================================================================================================================
    def __init__(self, camera: PyCamera, stream_port: int = 5001):
        self.camera = camera
        self.camera.events.frame.on(self.update)
        self.streamer = None
        self.stream_port = stream_port
        self.logger = Logger("LineDetector")

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, frame):
        # TODO: line detection goes here. Draw the detected line into the frame passed to update_stream.
        self.update_stream(frame)

    # ------------------------------------------------------------------------------------------------------------------
    def update_stream(self, frame):
        if frame is None:
            return

        # The frame is shared with other event subscribers: convert/copy before drawing on it.
        if frame.ndim == 2:
            stream_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        else:
            stream_frame = frame.copy()

        cv2.putText(
            stream_frame,
            "Line Detection",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

        with self._stream_frame_lock:
            self.frame_out = stream_frame

    # ------------------------------------------------------------------------------------------------------------------
    def getStreamFrame(self) -> Optional[bytes]:
        with self._stream_frame_lock:
            if self.frame_out is not None:
                return self.camera.getImageBufferBytes(self.frame_out)
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def start_stream(self):
        if self.streamer is not None:
            return
        self.streamer = VideoStreamer(image_fetcher=self.getStreamFrame, port=self.stream_port)
        self.streamer.start()
        ip = getInterfaceIP("wlan0")
        self.logger.info(f"Line detection stream: http://{ip}:{self.stream_port}/preview")



# class AP_LineFollowingController:
#     ...


if __name__ == '__main__':
    frodo = FRODO()
    frodo.init()

    line_detector = AP_LineDetector(frodo.sensors.camera)

    frodo.start()

    line_detector.start_stream()

    while True:
        time.sleep(10)
