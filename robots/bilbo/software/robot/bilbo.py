import ctypes
import dataclasses
from dataclasses import field
import os
import time

import math
import yaml

# === OWN PACKAGES =====================================================================================================
from core.utils.delayed_executor import delayed_execution
from simulation.simulated_board import SimulatedBoard
from simulation.simulated_communication import SimulatedCommunication

try:
    from hardware.control_board import RobotControl_Board
    from hardware.stm32.stm32 import resetSTM32
except ImportError:
    RobotControl_Board = None
    resetSTM32 = None

from robot.bilbo_common import BILBO_Common
from robot.core import MainProvider, set_main_provider
from robot.experiment.experiment_handler import BILBO_ExperimentHandler
from robot.interfaces.bilbo_interfaces import BILBO_Interfaces
from robot.testbed.bilbo_testbed_manager import BILBO_TestbedManager
from robot.utilities.bilbo_utilities import BILBO_Utilities
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import Event, event_definition, SubscriberListener
from core.utils.singletonlock.singletonlock import SingletonLock, terminate
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control_definitions import BILBO_Control_Mode
from robot.control.bilbo_control import BILBO_Control
from robot.drive.bilbo_drive import BILBO_Drive
from robot.estimation.bilbo_estimation import BILBO_Estimation, BILBO_TrackerSettings
from robot.logging.bilbo_logging import BILBO_Logging
from robot.logging.bilbo_sample import BILBO_Sample_General
from robot.sensors.bilbo_sensors import BILBO_Sensors
from core.utils.logging_utils import Logger, setLoggerLevel
from core.utils import colors
from robot.supervisor.bilbo_supervisor import BILBO_Supervisor
from robot.error_handler import report_error, ErrorSeverity
from core.hardware.revisions import get_versions, is_ll_version_compatible
import robot.lowlevel.stm32_addresses as stm32_addresses
from robot.lowlevel.stm32_general import BILBO_BoardRevision, BILBO_ModelType, BILBO_DriveInterface
from core.utils.exit import register_exit_callback
from core.utils.dataclass_utils import from_dict_auto
from robot.paths import init_paths

# === GLOBAL VARIABLES =================================================================================================
setLoggerLevel('wifi', 'ERROR')
setLoggerLevel('Sound', 'ERROR')


# === Settings =========================================================================================================
@dataclasses.dataclass
class BILBO_PathSettings:
    main: str = '~/robot'


@dataclasses.dataclass
class BILBO_JoystickSettings:
    enabled: bool = True


@dataclasses.dataclass
class BILBO_SoundSettings:
    volume: float = 0.5
    voice: str = 'female'  # female, male, or robot


@dataclasses.dataclass
class BILBO_MiscSettings:
    warn_on_sample_batching: bool = True


@dataclasses.dataclass
class STM32_Settings:
    reset: bool = False


@dataclasses.dataclass
class BILBO_TestbedSettings:
    id: str = 'default'


@dataclasses.dataclass
class BILBO_Settings:
    stm32: STM32_Settings = field(default_factory=STM32_Settings)
    testbed: BILBO_TestbedSettings = field(default_factory=BILBO_TestbedSettings)
    paths: BILBO_PathSettings = field(default_factory=BILBO_PathSettings)
    tracker: BILBO_TrackerSettings = field(default_factory=BILBO_TrackerSettings)
    joystick: BILBO_JoystickSettings = field(default_factory=BILBO_JoystickSettings)
    sound: BILBO_SoundSettings = field(default_factory=BILBO_SoundSettings)
    misc: BILBO_MiscSettings = field(default_factory=BILBO_MiscSettings)


def _load_settings(settings_path: str | None = None) -> BILBO_Settings:
    if settings_path is None:
        settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'settings.yaml')
    settings_path = os.path.abspath(settings_path)
    if not os.path.exists(settings_path):
        return BILBO_Settings()
    with open(settings_path, 'r') as f:
        data = yaml.safe_load(f) or {}
    return from_dict_auto(BILBO_Settings, data)


# === Callbacks ========================================================================================================
@callback_definition
class BILBO_Callbacks:
    update: CallbackContainer


# === Events ===========================================================================================================
@event_definition
class BILBO_Events:
    update: Event


# ======================================================================================================================
class BILBO(MainProvider):
    id: str

    common: BILBO_Common
    board: RobotControl_Board | SimulatedBoard

    communication: BILBO_Communication | SimulatedCommunication
    control: BILBO_Control
    estimation: BILBO_Estimation
    drive: BILBO_Drive
    sensors: BILBO_Sensors
    experiment_handler: BILBO_ExperimentHandler
    logging: BILBO_Logging
    utilities: BILBO_Utilities
    testbed_manager: BILBO_TestbedManager

    events: BILBO_Events

    supervisor: BILBO_Supervisor
    lock: SingletonLock

    loop_time: float

    _initialized: bool = False
    _last_update_time: float = 0
    _first_sample_user_message_sent: bool = False
    _eventListener: SubscriberListener

    # === INIT =========================================================================================================
    def __init__(self, simulation: bool = False, settings_path: str | None = None):

        self.settings = _load_settings(settings_path)
        init_paths(self.settings.paths.main)

        self.lock = SingletonLock(lock_file="/tmp/bilbo.lock", timeout=10, override=True, override_timeout=5)
        self.lock.__enter__()

        self.logger = Logger("BILBO")
        self.simulation = simulation

        if self.simulation:
            self.logger.important("=== SIMULATION MODE (Digital Twin) ===")
            self.board = SimulatedBoard()
        else:
            if self.settings.stm32.reset:
                self.logger.info(f"Reset STM32. This takes ~2 Seconds")
                resetSTM32()
                time.sleep(3)

            # Set up the control board
            self.board = RobotControl_Board()

        self.common = BILBO_Common(bilbo=self, board=self.board)

        # Read the ID from the ID file
        self.id = self.common.id

        Logger.banner([f"BILBO Startup \u2014 {self.id}"])

        self.loop_time = 0
        self.update_time = 0
        self._last_update_time = 0

        self._initialized = False

        set_main_provider(self)

        # Start the communication module (WI-FI, Serial and SPI)
        if self.simulation:
            self.communication = SimulatedCommunication(core=self.common)
        else:
            self.communication = BILBO_Communication(board=self.board, core=self.common)

        # Set up the individual modules
        self.estimation = BILBO_Estimation(common=self.common,
                                           comm=self.communication,
                                           tracker_settings=self.settings.tracker)

        self.control = BILBO_Control(common=self.common, comm=self.communication, estimation=self.estimation)
        self.drive = BILBO_Drive(comm=self.communication)
        self.sensors = BILBO_Sensors(comm=self.communication)

        self.interfaces = BILBO_Interfaces(communication=self.communication,
                                           control=self.control,
                                           core=self.common,
                                           joystick_enabled=self.settings.joystick.enabled,
                                           drive=self.drive)

        self.utilities = BILBO_Utilities(core=self.common,
                                         communication=self.communication,
                                         board=self.board,
                                         sound_settings=self.settings.sound)

        self.supervisor = BILBO_Supervisor(comm=self.communication, control=self.control, utilities=self.utilities)

        self.testbed_manager = BILBO_TestbedManager(common=self.common, communication=self.communication,
                                                    control=self.control, estimation=self.estimation,
                                                    testbed_id=self.settings.testbed.id)
        self.control.position_control.set_testbed_manager(self.testbed_manager)

        self.experiment_handler = BILBO_ExperimentHandler(common=self.common,
                                                          communication=self.communication,
                                                          interfaces=self.interfaces,
                                                          utilities=self.utilities,
                                                          control=self.control,
                                                          estimation=self.estimation,
                                                          testbed=self.testbed_manager)

        self.logging = BILBO_Logging(common=self.common,
                                     communication=self.communication,
                                     control=self.control,
                                     estimation=self.estimation,
                                     drive=self.drive,
                                     sensors=self.sensors,
                                     experiment_handler=self.experiment_handler,
                                     )

        self.events = BILBO_Events()
        self.callbacks = BILBO_Callbacks()

        register_exit_callback(self._shutdown, priority=0)
        register_exit_callback(self._shutdownInit, priority=2)

        self._startup_phase = True

        def on_new_timecode(timecode):
            self.board.status_led.toggle()

        self.common.timecode_listener.callbacks.new_timecode.register(on_new_timecode)

    # === METHODS ======================================================================================================
    def init(self):
        Logger.section("Hardware")
        self.board.init()
        self.board.start()

        Logger.section("Communication")
        self.communication.init()
        self.communication.start()

        Logger.section("Estimation")
        self.estimation.init()

        Logger.section("Supervisor")
        self.supervisor.init()

        Logger.section("Interfaces")
        self.interfaces.init()

        Logger.section("Control")
        result = self.control.init()
        if not result:
            report_error(ErrorSeverity.CRITICAL, "BILBO", "Control init failed")

        Logger.section("Sensors")
        self.sensors.init()

        Logger.section("Logging")
        self.logging.init()

        Logger.section("Experiments")
        self.experiment_handler.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        Logger.section("Starting Services")
        self.common.start()
        self.utilities.start()
        self.control.start()
        self.supervisor.start()
        self.sensors.start()
        self.logging.start()

        Logger.section("OptiTrack")
        self.estimation.start()
        # Wait for OptiTrack to finish connecting (async NatNet logs)
        if self.estimation.tracker is not None and self.estimation.tracker_settings.enabled:
            tracker_optitrack = self.estimation.tracker.optitrack
            deadline = time.perf_counter() + 3.0
            while not tracker_optitrack.first_data_frame_received and time.perf_counter() < deadline:
                time.sleep(0.05)

        Logger.section("Firmware Reset")
        self._last_update_time = time.perf_counter()
        time.sleep(0.5)
        if not self._resetLowLevel():
            self.logger.error("Failed to reset lowlevel firmware")
            raise Exception("Failed to reset lowlevel firmware")

        Logger.section("Sample Listener")
        self.communication.startSampleListener()
        self._eventListener = self.communication.events.rx_stm32_sample.on(self.update, spawn_new_threads=False)
        self.interfaces.start()

        self.utilities.playTone('notification')
        delayed_execution(lambda: setattr(self, '_startup_phase', False), 1)

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, *args, **kwargs):
        """
        This is the main update function for the robot
        """
        # if not self._initialized:
        #     return
        time_loop_start = time.perf_counter()
        self.update_time = time.perf_counter() - self._last_update_time
        self._last_update_time = time.perf_counter()

        # Update the logging
        self.logging.update()

        self.estimation.update()

        # Update the experiment handler
        self.experiment_handler.step()

        # Update the control
        self.control.update()

        # Callbacks
        self.callbacks.update.call()

        # Events
        self.events.update.set()

        if not self._first_sample_user_message_sent:
            self._sendFirstSampleMessage()

        self.loop_time = time.perf_counter() - time_loop_start

        if self.loop_time > 1.0:
            self.logger.warning(f"Loop took {self.loop_time * 1000:.2f} ms")

        if self.update_time > 1.0 and self._startup_phase == False:
            self.logger.warning(f"Update took {self.update_time * 1000:.2f} ms")

        self.common.end_of_step()

    # === PRIVATE METHODS ==============================================================================================
    def _resetLowLevel(self):
        result = self.communication.serial.executeFunction(
            module=stm32_addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=stm32_addresses.BILBO_SystemAddresses.FIRMWARE_RESET,
            input_type=None,
            output_type=ctypes.c_bool,
            timeout=1
        )

        if result:
            self._readFirmwareInfo()

        return result

    # ------------------------------------------------------------------------------------------------------------------
    def _readFirmwareInfo(self):
        info = self.communication.serial.readFirmwareInfo()
        if info is None:
            self.logger.warning("Could not read firmware info from STM32")
            return

        try:
            board_rev = BILBO_BoardRevision(info['board_revision'])
            model = BILBO_ModelType(info['model'])
            drive = BILBO_DriveInterface(info['drive_interface'])
            self.logger.info(f"Firmware info: board={board_rev.name}, model={model.name}, drive={drive.name}")
        except (ValueError, KeyError) as e:
            self.logger.warning(f"Unknown firmware info values: {info} ({e})")

    # ------------------------------------------------------------------------------------------------------------------
    def _shutdownInit(self):
        Logger.banner([f"Shutting down {self.id}"], color=colors.MEDIUM_ORANGE)
        self.control.set_mode(BILBO_Control_Mode.OFF)
        self._eventListener.stop()
        self.utilities.playTone('warning')
        self.board.setRGBLEDExtern([2, 2, 2])

    # ------------------------------------------------------------------------------------------------------------------
    def _shutdown(self, *args, **kwargs):
        self.logger.info("Shutdown BILBO")
        time.sleep(1)
        self.lock.__exit__(None, None, None)

    # ------------------------------------------------------------------------------------------------------------------
    def _checkFirmwareRevision(self) -> bool:
        revision_stm32 = self.communication.serial.readFirmwareRevision()
        revision_data = get_versions()

        # Check if the LL firmware is compatible
        if revision_stm32 is None or not is_ll_version_compatible(current_ll_version=(revision_stm32['major'],
                                                                                      revision_stm32['minor']),
                                                                  min_ll_version=(
                                                                          revision_data['stm32_firmware']['major'],
                                                                          revision_data['stm32_firmware'][
                                                                              'minor'])):
            self.logger.error(
                f"STM32 Firmware not compatible. Current Version: {revision_stm32['major']}.{revision_stm32['minor']}."
                f" Required > {revision_data['stm32_firmware']['major']}.{revision_data['stm32_firmware']['minor']}")
            return False

        self.logger.info(
            f"Software Version {revision_data['software']['major']}.{revision_data['software']['minor']}"
            f" (STM32: {revision_stm32['major']}.{revision_stm32['minor']})")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def _sendFirstSampleMessage(self):
        Logger.banner([
            f"BILBO is running! ({self.id})",
            f"Battery: {self.logging.sample.sensors.power.bat_voltage:.2f} V",
        ])
        self._first_sample_user_message_sent = True

    # ------------------------------------------------------------------------------------------------------------------
    def __del__(self):
        if hasattr(self, 'lock'):
            self.lock.__exit__(None, None, None)
