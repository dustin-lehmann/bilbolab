import time

from core.communication.device_server import Device
from core.communication.protocol import JSON_Message
from core.utils.dataclass_utils import from_dict_auto
from core.utils.logging_utils import Logger, LOG_LEVELS
from core.utils.sound.sound import speak
from robots.frodo.robot.frodo_definitions import FRODO_Sample, FRODO_ControlMode, FRODO_Config
from core.utils.events import pred_flag_equals, event_definition, Event, EventFlag


@event_definition
class FRODO_Core_Events:
    control_mode_changed: Event = Event(flags=EventFlag('mode', FRODO_ControlMode))
    control_configuration_changed: Event
    control_error: Event

    stream: Event = Event(data_type=FRODO_Sample)
    initialized: Event = Event(data_type=FRODO_Sample)


class FRODO_Core:
    device: Device
    _last_stream_time: float = None
    initialized: bool = False
    tick: int | None = None
    data: FRODO_Sample | None = None
    events: FRODO_Core_Events
    config: FRODO_Config | None

    # === INIT =========================================================================================================
    def __init__(self, robot_id: str, device: Device, config: FRODO_Config | None = None):
        self.device = device
        self.id = robot_id
        self.logger = Logger(f"{self.id}")
        self.logger.setLevel('DEBUG')

        self.config = config
        self.events = FRODO_Core_Events()

        self.device.events.event.on(self._handleLogMessage,
                                    predicate=pred_flag_equals('container', 'log'),
                                    )

        self.device.events.event.on(self._handleSpeakEventMessage,
                                    predicate=pred_flag_equals('container', 'speak'),
                                    )

        self.device.callbacks.stream.register(self._handleStream)

    # === METHODS ======================================================================================================
    def beep(self, frequency=1000, time_ms=250, repeats=1):
        self.device.executeFunction(function_name='beep',
                                    arguments={'frequency': frequency, 'time_ms': time_ms, 'repeats': repeats})

    # === PRIVATE METHODS ==============================================================================================
    def _handleLogMessage(self, event_data, **kwargs):
        log_data = event_data.get('data', {}) or {}

        if 'level' not in log_data or 'message' not in log_data or 'logger' not in log_data:
            self.logger.error(f"Invalid log message: {log_data}")
            return

        if log_data['level'] == LOG_LEVELS['ERROR']:
            self.logger.error(f"({log_data['logger']}): {log_data['message']}")
        elif log_data['level'] == LOG_LEVELS['WARNING']:
            self.logger.warning(f"({log_data['logger']}): {log_data['message']}")
        elif log_data['level'] == LOG_LEVELS['INFO']:
            self.logger.info(f"({log_data['logger']}): {log_data['message']}")
        elif log_data['level'] == LOG_LEVELS['DEBUG']:
            self.logger.debug(f"({log_data['logger']}): {log_data['message']}")
        elif log_data['level'] == LOG_LEVELS['IMPORTANT']:
            self.logger.important(f"({log_data['logger']}): {log_data['message']}")
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

        sample = stream.data['data']

        self.data = from_dict_auto(FRODO_Sample, sample)
        tick = self.data.general.step

        if self.tick is not None:
            if (tick - self.tick) != 1:
                self.logger.warning(
                    f"Tick difference: {tick - self.tick}. Last tick: {self.tick}, current tick: {tick}.")

        if self._last_stream_time is not None:
            time_between_streams = current_time - self._last_stream_time
            if time_between_streams > 0.3:
                self.logger.warning(
                    f"Time between two streams: {time_between_streams:.2f} seconds. "
                    f"Last tick: {self.tick}, current tick: {tick}.")

        self._last_stream_time = current_time
        self.tick = tick

        if not self.initialized:
            self.initialized = True
            self.logger.info(f"FRODO Initialized")
            self.logger.info(f"Battery voltage: {self.data.general.battery:.1f} V")
            self.events.initialized.set(data=self.data)

        self.events.stream.set(data=self.data)
