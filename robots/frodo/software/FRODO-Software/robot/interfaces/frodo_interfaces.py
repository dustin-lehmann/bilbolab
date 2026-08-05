import time

import numpy as np

from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from robot.common import FRODO_Common
from robot.communication.frodo_communication import FRODO_Communication
from robot.definitions import VIDEO_STREAMER_PORT
from robot.sensing.frodo_sensors import FRODO_Sensors
from robot.utilities.video_streamer.video_streamer import VideoStreamer
from robot.control.frodo_control import FRODO_Control
from core.utils.joystick.joystick_manager import JoystickManager, Joystick
import threading

class FRODO_Interfaces:
    _joystick: Joystick
    _joystick_manager: JoystickManager
    _joystick_thread: threading.Thread
    _exit_joystick_task: bool = False

    # === INIT =========================================================================================================
    def __init__(self, common: FRODO_Common, communication: FRODO_Communication, sensors: FRODO_Sensors,
                 control: FRODO_Control):

        self.logger = Logger("INTERFACES", "DEBUG")
        self.common = common
        self.communication = communication
        self.sensors = sensors
        self.control = control

        self.streamer = VideoStreamer(image_fetcher=self.sensors.aruco_detector.getOverlayFrame,
                                      fetch_hz=20,
                                      port=VIDEO_STREAMER_PORT, )

        self._joystick_manager = JoystickManager(accept_unmapped_joysticks=False)
        self._joystick_manager.callbacks.new_joystick.register(self._onJoystickConnected)
        self._joystick_manager.callbacks.joystick_disconnected.register(self._onJoystickDisconnected)

        self._joystick = None  # type: ignore
        self._joystick_thread = None  # type: ignore

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.streamer.start()
        self._joystick_manager.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.streamer.stop()

    # === PRIVATE METHODS ==============================================================================================
    def _onJoystickConnected(self, joystick, *args, **kwargs):
        self.logger.info(f'Joystick connected: {joystick.name}')
        self._joystick = joystick

        self._exit_joystick_task = False
        self._joystick_thread = threading.Thread(target=self._joystickTask, daemon=True)
        self._joystick_thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def _onJoystickDisconnected(self, joystick, *args, **kwargs):
        if joystick == self._joystick:
            self._joystick = None  # type: ignore
            joystick.clearAllButtonCallbacks()
            self.logger.info(f'Joystick disconnected: {joystick.name}')

            if self._joystick_thread is not None and self._joystick_thread.is_alive():
                self._exit_joystick_task = True
                self._joystick_thread.join()
                self._joystick_thread = None  # type: ignore

    def _joystickTask(self):
        while self._joystick is not None and not self._exit_joystick_task:

            # === Read controller inputs ===
            forward = -self._joystick.getAxis("LEFT_VERTICAL")  # Forward/backward
            turn = self._joystick.getAxis("RIGHT_HORIZONTAL")  # Turning

            # === Exponential response mapping (for finer low-speed control) ===
            def map_input(x, factor=10.0):
                sign = np.sign(x)
                x = abs(x)
                return sign * (np.exp(x * np.log(factor)) - 1) / (factor - 1)

            turn = map_input(turn)

            # === Normalize so combined magnitude doesn’t exceed 1 ===
            sum_axis = abs(forward) + abs(turn)
            if sum_axis > 1:
                forward /= sum_axis
                turn /= sum_axis

            # === Mix forward + turn into left/right speeds ===
            speed_left = forward + turn
            speed_right = forward - turn

            # === Apply to control system ===
            self.control.setTrackSpeedNormalized(
                speed_left, speed_right
            )

            time.sleep(0.1)
