import collections
import dataclasses
import enum
import math
import time
from typing import Deque, Optional, Tuple

import dacite
import numpy as np
from dacite import from_dict

from core.communication.protocol import JSON_Message
from core.communication.device_server import Device
from core.utils.remote_file.remote_file import RemoteFileClient
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event, EventFlag, pred_flag_equals
from core.utils.logging_utils import Logger, LOG_LEVELS
from core.utils.sound.sound import speak, playSound

from robots.bilbo.robot.bilbo_data import BILBO_Sample, bilboSampleFromDict
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_PASSWORD, BILBO_USER_NAME


@callback_definition
class BILBO_Core_Callbacks:
    stream: CallbackContainer


# ======================================================================================================================
@event_definition
class BILBO_Core_Events:
    control_mode_changed: Event = Event(flags=EventFlag('mode', BILBO_Control_Mode))
    control_configuration_changed: Event
    control_error: Event

    stream: Event = Event(data_type=BILBO_Sample)
    initialized: Event = Event(data_type=BILBO_Sample)


@event_definition
class BILBO_Interface_Events:
    resume: Event
    revert: Event
    stop: Event
    start: Event


@dataclasses.dataclass
class _UprightStaticEntry:
    t: float  # monotonic time [s]
    theta: float  # pitch [rad]
    v: float  # forward velocity [m/s]


class BILBO_Core:
    device: Device

    _last_stream_time: float = None
    initialized: bool = False
    tick: int | None = None
    data: BILBO_Sample | None = None

    file_handler: RemoteFileClient

    # ==================================================================================================================
    def __init__(self, robot_id: str, device: Device, robot):
        self.bilbo = robot
        self.device = device
        self.id = robot_id
        self.logger = Logger(f"{self.id}")
        self.logger.setLevel('DEBUG')

        self.events = BILBO_Core_Events()
        self.interface_events = BILBO_Interface_Events()

        self.device.events.event.on(self._handleLogMessage,
                                    predicate=pred_flag_equals('container', 'log'))

        self.device.events.event.on(self._handleSpeakEventMessage,
                                    predicate=pred_flag_equals('container', 'speak'))

        # self.device.events.stream.on(self._handleStream, input_data=True)
        self.device.callbacks.stream.register(self._handleStream)

        if not robot.config.general.simulation:
            self.file_handler = RemoteFileClient(
                host=device.address,
                username=BILBO_USER_NAME,
                password=BILBO_PASSWORD
            )
            self.file_handler.connect()
        else:
            self.file_handler = None

    # ------------------------------------------------------------------------------------------------------------------
    def get_robot(self):
        return self.bilbo

    # ------------------------------------------------------------------------------------------------------------------
    def beep(self, frequency=1000, time_ms=250, repeats=1):
        self.device.executeFunction(function_name='beep',
                                    arguments={'frequency': frequency, 'time_ms': time_ms, 'repeats': repeats})

    # ------------------------------------------------------------------------------------------------------------------
    def speakOnHost(self, text):
        speak(f"{self.id}: {text}")

    # ------------------------------------------------------------------------------------------------------------------
    def playSound(self, sound_id):
        playSound(sound_id)

    # ------------------------------------------------------------------------------------------------------------------
    def speak(self, text):
        self.device.executeFunction(function_name='speak', arguments={'message': text})

    # ------------------------------------------------------------------------------------------------------------------
    def reset_drive(self):
        self.logger.info("Resetting drive")
        self.device.executeFunction(function_name='reset_drive', arguments={})

    # # ------------------------------------------------------------------------------------------------------------------
    # def setResumeEvent(self):
    #     self.logger.info(f"Set Resume Event")
    #     self.interface_events.resume.set()

    # ------------------------------------------------------------------------------------------------------------------
    def set_resume_event_robot(self):
        self.logger.info(f"Set Resume Event Robot")
        self.device.executeFunction(function_name='resume', arguments={})

    # # ----------------------------------------------------------------------------------------------------------------
    # def setRevertEvent(self):
    #     self.logger.info(f"Set Revert Event")
    #     self.interface_events.revert.set()

    # ------------------------------------------------------------------------------------------------------------------
    def set_start_event_robot(self):
        self.logger.info(f"Set Start Event Robot")
        self.device.executeFunction(function_name='start', arguments={})

    # ------------------------------------------------------------------------------------------------------------------
    def set_stop_event_robot(self):
        self.logger.info(f"Set Stop Event Robot")
        self.device.executeFunction(function_name='stop', arguments={})

    # ------------------------------------------------------------------------------------------------------------------
    def set_repeat_event_robot(self):
        self.logger.info(f"Set repeat Event Robot")
        self.device.executeFunction(function_name='repeat', arguments={})

    # # ------------------------------------------------------------------------------------------------------------------
    # def setStopEvent(self):
    #     self.logger.info(f"Set Stop Event")
    #     self.interface_events.stop.set()

    # ------------------------------------------------------------------------------------------------------------------
    def set_stop_event_robot(self):
        self.logger.info(f"Set Stop Event Robot")
        self.device.executeFunction(function_name='stop', arguments={})

    # ------------------------------------------------------------------------------------------------------------------
    def _handleLogMessage(self, event_data, **kwargs):
        log_data = event_data.get('data', {}) or {}

        if 'level' not in log_data or 'message' not in log_data or 'logger' not in log_data:
            self.logger.error(f"Invalid log message: {log_data}")
            return

        if log_data['level'] == LOG_LEVELS['ERROR']:
            self.logger.error(f"(from {log_data['logger']}): {log_data['message']}")
        elif log_data['level'] == LOG_LEVELS['WARNING']:
            self.logger.warning(f"(from {log_data['logger']}): {log_data['message']}")
        elif log_data['level'] == LOG_LEVELS['INFO']:
            self.logger.info(f"(from {log_data['logger']}): {log_data['message']}")
        elif log_data['level'] == LOG_LEVELS['DEBUG']:
            self.logger.debug(f"(from {log_data['logger']}): {log_data['message']}")

        if log_data.get('speak', False):
            speak(f"{self.id}: {log_data['message']}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleSpeakEventMessage(self, event_data, **kwargs):
        data = event_data.get('data', {}) or {}
        if data.get('message', None) is not None:
            speak(f"{self.id}: {data['message']}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleStream(self, stream: JSON_Message):
        current_time = time.monotonic()

        samples = stream.data['data']

        self.data = bilboSampleFromDict(samples[0])
        tick = self.data.general.tick

        if self.tick is not None:
            if (tick - self.tick) != 10:
                self.logger.warning(
                    f"Tick difference: {tick - self.tick}. Last tick: {self.tick}, current tick: {tick}.")

        if self._last_stream_time is not None:
            time_between_streams = current_time - self._last_stream_time
            if time_between_streams > 1.0:
                self.logger.warning(
                    f"Time between two streams: {time_between_streams:.2f} seconds. "
                    f"Last tick: {self.tick}, current tick: {tick}.")

        self._last_stream_time = current_time
        self.tick = tick

        if not self.initialized:
            self.initialized = True
            self.logger.info(f"First sample received.")
            self.events.initialized.set(data=self.data)

        self.events.stream.set(data=self.data)
