import dataclasses
import enum
import sys
import threading
import time

from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.dataclass_utils import from_dict, from_dict_auto
from core.utils.events import Event, event_definition
from core.utils.exit import register_exit_callback
from core.utils.files import fileExists
from core.utils.json_utils import readJSON
from core.utils.logging_utils import Logger
from core.utils.network import get_own_hostname, getSignalStrength, check_internet
from robot.definitions import FRODO_Information, FRODO_DynamicState, FRODO_Network_Settings
from robot.settings import settings_file_path
from robot.setup import FRODO_Definition


class ErrorSeverity(enum.StrEnum):
    MINOR = 'minor'
    MAJOR = 'major'
    CRITICAL = 'critical'


@callback_definition
class FRODO_Common_Callbacks:
    lowlevel_sample: CallbackContainer


@event_definition
class FRODO_Common_Events:
    lowlevel_sample: Event


class FRODO_Common:
    step: int = 0
    callbacks: FRODO_Common_Callbacks
    events: FRODO_Common_Events
    information: FRODO_Information

    joystick_connected: bool = False
    server_connected: bool = False

    dynamic_state: FRODO_DynamicState | None = None

    _connection_strength: float = 0.0
    _internet_connected: bool = False
    _exit: bool = False
    _thread: threading.Thread = None

    # === INIT =========================================================================================================
    def __init__(self):
        self.callbacks = FRODO_Common_Callbacks()
        self.events = FRODO_Common_Events()
        self.logger = Logger("COMMON", "DEBUG")
        self._id = get_own_hostname()

        # Check if the settings file exists
        if not fileExists(settings_file_path):
            raise FileNotFoundError(
                f"Settings file '{settings_file_path}' not found. Please run setup first."
            )

        self.information = self._collectInformation()

        self._thread = threading.Thread(target=self._connection_check_task)
        self._thread.start()
        register_exit_callback(self.close)

    # === PROPERTIES ===================================================================================================
    @property
    def id(self):
        return self._id

    # === METHODS ======================================================================================================
    def getConnectionStrength(self):
        return self._connection_strength

    # ------------------------------------------------------------------------------------------------------------------
    def getInternetConnected(self):
        return self._internet_connected

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self._exit = True
        if self._thread.is_alive():
            self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def getDynamicState(self) -> FRODO_DynamicState | None:
        return self.dynamic_state

    # ------------------------------------------------------------------------------------------------------------------
    def setDynamicState(self, state: FRODO_DynamicState):
        self.dynamic_state = state

    # ------------------------------------------------------------------------------------------------------------------
    def incrementStep(self):
        self.step += 1

    # ------------------------------------------------------------------------------------------------------------------
    def getStep(self):
        return self.step

    # ------------------------------------------------------------------------------------------------------------------
    def errorHandler(self, severity, message):
        self.logger.error(f"ERROR {severity}: {message}")
        if severity == ErrorSeverity.CRITICAL:
            sys.exit(1)

    # ------------------------------------------------------------------------------------------------------------------
    def _collectInformation(self) -> FRODO_Information:
        definition = self.getDefinitions()
        information = FRODO_Information(
            id=self.id,
            color=definition.color,
            network=FRODO_Network_Settings(
                address='',
                gui_port=0,
                data_stream_port=0,
                ssid='',
                username='admin',
                password='beutlin',
            ),
            camera=definition.camera,
            aruco=definition.aruco,
            optitrack=definition.optitrack,
            physical_model=definition.physical_model,
        )
        return information

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def getDefinitions() -> FRODO_Definition:
        settings_dict = readJSON(settings_file_path)
        settings = from_dict_auto(FRODO_Definition, settings_dict)
        return settings

    # ------------------------------------------------------------------------------------------------------------------
    def _connection_check_task(self):
        while not self._exit:
            self._connection_strength = getSignalStrength('wlan0')['percent']
            self._internet_connected = check_internet(timeout=1)
            time.sleep(2)


if __name__ == '__main__':
    common = FRODO_Common()
    print(common.getDefinitions())
