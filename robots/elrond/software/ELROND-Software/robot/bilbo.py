import ctypes
import os
import time

# === OWN PACKAGES =====================================================================================================
from control_board.control_board import RobotControl_Board
from control_board.stm32.stm32 import resetSTM32
from robot.experiment.bilbo_experiment import BILBO_ExperimentHandler
from robot.utilities.bilbo_utilities import BILBO_Utilities
from robot.utilities.id import readID
from utils.callbacks import callback_handler, CallbackContainer
from utils.events import EventListener, ConditionEvent, event_handler
from utils.exit import ExitHandler, stop_program
from utils.singletonlock.singletonlock import SingletonLock, terminate
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.definitions import BILBO_Control_Mode
from robot.control.bilbo_control import BILBO_Control
from robot.drive.bilbo_drive import BILBO_Drive
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.logging.bilbo_logging import BILBO_Logging
from robot.logging.bilbo_sample import BILBO_Sample_General
from robot.sensors.bilbo_sensors import BILBO_Sensors
from utils.logging_utils import Logger, setLoggerLevel
from robot.supervisor.twipr_supervisor import TWIPR_Supervisor
from utils.revisions import get_versions, is_ll_version_compatible
import robot.lowlevel.stm32_addresses as stm32_addresses
from utils.time import precise_sleep, PerformanceTimer

# === GLOBAL VARIABLES =================================================================================================

setLoggerLevel('wifi', 'ERROR')
setLoggerLevel('Sound', 'ERROR')


# === Callbacks ========================================================================================================
@callback_handler
class BILBO_Callbacks:
    update: CallbackContainer


# === Events ===========================================================================================================
@event_handler
class BILBO_Events:
    update: ConditionEvent


# ======================================================================================================================
class BILBO:
    id: str

    board: RobotControl_Board
    communication: BILBO_Communication
    control: BILBO_Control
    estimation: BILBO_Estimation
    drive: BILBO_Drive
    sensors: BILBO_Sensors
    experiment_handler: BILBO_ExperimentHandler
    logging: BILBO_Logging
    utilities: BILBO_Utilities

    events: BILBO_Events

    supervisor: TWIPR_Supervisor
    lock: SingletonLock
    exit: ExitHandler

    loop_time: float
    tick: int = 0

    _initialized: bool = False
    _last_update_time: float = 0
    _first_sample_user_message_sent: bool = False
    _eventListener: EventListener

    # _updateTimer: IntervalTimer = IntervalTimer(0.1)

    # === INIT =========================================================================================================
    def __init__(self, reset_stm32: bool = False):

        terminate(lock_file="/tmp/twipr.lock")
        self.lock = SingletonLock(lock_file="/tmp/twipr.lock", timeout=10)
        self.lock.__enter__()

        self.logger = Logger("BILBO")

        if reset_stm32:
            self.logger.info(f"Reset STM32. This takes ~2 Seconds")
            resetSTM32()
            time.sleep(3)

        # Read the ID from the ID file
        self.id = readID()

        self.loop_time = 0
        self.update_time = 0
        self._last_update_time = 0
        self.tick = 0

        self._initialized = False

        # Set up the control board
        self.board = RobotControl_Board(device_class='robot', device_type='bilbo', device_revision='v4',
                                        device_id=self.id, device_name=self.id)

        # Start the communication module (WI-FI, Serial and SPI)
        self.communication = BILBO_Communication(board=self.board)

        # Set up the individual modules
        self.control = BILBO_Control(comm=self.communication)
        self.estimation = BILBO_Estimation(comm=self.communication)
        self.drive = BILBO_Drive(comm=self.communication)
        self.sensors = BILBO_Sensors(comm=self.communication)
        self.supervisor = TWIPR_Supervisor(comm=self.communication)

        self.utilities = BILBO_Utilities(communication=self.communication)
        self.experiment_handler = BILBO_ExperimentHandler(communication=self.communication,
                                                          utils=self.utilities,
                                                          control=self.control, )

        self.logging = BILBO_Logging(comm=self.communication,
                                     control=self.control,
                                     estimation=self.estimation,
                                     drive=self.drive,
                                     sensors=self.sensors,
                                     experiment_handler=self.experiment_handler,
                                     general_sample_collect_function=self._getSample)

        # Test Command
        self.communication.wifi.addCommand(identifier='test',
                                           callback=self.test,
                                           arguments=['input'],
                                           description='Test the communication')

        self.events = BILBO_Events()
        self.callbacks = BILBO_Callbacks()
        self._eventListener = EventListener(event=self.communication.events.rx_stm32_sample, callback=self.update)
        self.exit = ExitHandler()
        self.exit.register(self._shutdown)

    # === METHODS ======================================================================================================
    def init(self):

        self.board.init()
        self.board.start()
        self.communication.init()
        self.communication.start()

        self.estimation.init()
        self.control.init()
        self.supervisor.init()
        self.sensors.init()
        self.logging.init()
        self.experiment_handler.init(self.logging)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):

        # self.communication.start()
        self.utilities.start()

        success = self.control.start()

        if not success:
            self.logger.error("Cannot write control configuration. Exit program")
            exit()

        self.supervisor.start()
        self.sensors.start()
        self.logging.start()

        self._last_update_time = time.perf_counter()
        time.sleep(0.05)
        if not self._resetLowLevel():
            self.logger.error("Failed to reset lowlevel firmware")
            stop_program()

        self.logger.info(f"Start {self.id}")
        self.utilities.playTone('notification')
        self.utilities.speak(f'Start {self.id}')

        self.communication.startSampleListener()
        self._eventListener.start()
        # self.board.setRGBLEDExtern([0, 0, 0])

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

        # Update the control
        self.control.update()

        self._setExternalLEDs()

        # Update the logging
        self.logging.update()

        # Callbacks
        self.callbacks.update.call()

        # Events
        with self.events.update:
            self.events.update.notify_all()

        if not self._first_sample_user_message_sent:
            self._sendFirstSampleMessage()

        self.tick += 10
        self.loop_time = time.perf_counter() - time_loop_start
        # print(f"Loop time {self.loop_time:.4f} s, Update time {self.update_time:.4f} s, Tick {self.tick}")

        if self.loop_time > 0.18:
            self.logger.warning(f"Loop took {self.loop_time * 1000:.2f} ms")

        if self.update_time > 0.2:
            self.logger.warning(f"Update took {self.update_time * 1000:.2f} ms")

    # === PRIVATE METHODS ==============================================================================================
    def _resetLowLevel(self):
        # self.board.beep()

        return self.communication.serial.executeFunction(
            module=stm32_addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=stm32_addresses.TWIPR_GeneralAddresses.ADDRESS_FIRMWARE_RESET,
            input_type=None,
            output_type=ctypes.c_bool,
            timeout=1
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _shutdown(self, *args, **kwargs):
        # Beep for audio reference
        self.utilities.playTone('warning')
        self.logger.info("Shutdown BILBO")
        self.control.setMode(BILBO_Control_Mode.OFF)
        self._eventListener.stop()
        time.sleep(1)
        self.board.setRGBLEDExtern([2, 2, 2])
        self.lock.__exit__(None, None, None)

        # Shutdown all modules
        # self.communication.close()

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
    def _getSample(self):
        sample = BILBO_Sample_General()
        # sample.status = 'ok'
        # sample.id = self.id
        # sample.configuration = ''
        # sample.time_global = self.communication.wifi.getTime()
        # sample.tick = self.tick
        # sample.sample_time = 0.1
        # sample.sample_time_ll = 0.01
        sample = {
            'status': 'ok',
            'id': self.id,
            'time': 0.0,
            'configuration': '',
            'time_global': self.communication.wifi.getTime(),
            'tick': self.tick,
            'sample_time': 0.1,
            'sample_time_ll': 0.01,
        }
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def _setExternalLEDs(self):
        if self.control.mode == BILBO_Control_Mode.OFF:
            self.board.setRGBLEDExtern([2, 2, 2])
        elif self.control.mode == BILBO_Control_Mode.BALANCING:
            self.board.setRGBLEDExtern([0, 10, 0])
        elif self.control.mode == BILBO_Control_Mode.VELOCITY:
            self.board.setRGBLEDExtern([0, 0, 10])

    # ------------------------------------------------------------------------------------------------------------------
    def _sendFirstSampleMessage(self):
        self.logger.info(f"BILBO is running!")
        self.logger.info(f"Battery Voltage: {self.logging.sample.sensors.power.bat_voltage:.2f} V")
        self._first_sample_user_message_sent = True

    # ------------------------------------------------------------------------------------------------------------------
    def test(self, input):
        return input

    # ------------------------------------------------------------------------------------------------------------------
    def __del__(self):
        if hasattr(self, 'lock'):
            self.lock.__exit__(None, None, None)
