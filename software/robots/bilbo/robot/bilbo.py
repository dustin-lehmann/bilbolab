import threading
import time

from core.communication.device_server import Device
from core.utils.events import Event, event_definition
from robots.bilbo.robot.bilbo_control import BILBO_Control
from robots.bilbo.robot.bilbo_core import BILBO_Core
from robots.bilbo.robot.bilbo_estimation import BILBO_Estimation
from robots.bilbo.robot.bilbo_position_control import BILBO_PositionControl
from robots.bilbo.robot.experiment.bilbo_experiment_handler import BILBO_ExperimentHandler
from robots.bilbo.robot.bilbo_interfaces import BILBO_Interfaces
from robots.bilbo.robot.bilbo_data import BILBO_Sample, bilboSampleFromDict
from robots.bilbo.robot.bilbo_definitions import *
from robots.bilbo.robot.bilbo_utilities import BILBO_Utilities


# ======================================================================================================================
class BILBO:
    device: Device

    config: BILBO_Config

    core: BILBO_Core
    control: BILBO_Control
    position_control: BILBO_PositionControl
    estimation: BILBO_Estimation
    experiment_handler: BILBO_ExperimentHandler
    interfaces: BILBO_Interfaces
    data: BILBO_Sample

    _exit_task: bool = False

    # ==================================================================================================================
    def __init__(self, device: Device, config: BILBO_Config, *args, **kwargs):
        self.device = device

        self.config = config

        self.core = BILBO_Core(device=device, robot_id=self.device.information.device_id, robot=self)

        self.control = BILBO_Control(core=self.core)
        self.position_control = BILBO_PositionControl(core=self.core)
        self.estimation = BILBO_Estimation(core=self.core)
        self.experiment_handler = BILBO_ExperimentHandler(core=self.core, control=self.control)
        self.utilities = BILBO_Utilities(core=self.core)
        self.interfaces = BILBO_Interfaces(core=self.core,
                                           control=self.control,
                                           position_control=self.position_control,
                                           experiments=self.experiment_handler,
                                           utilities=self.utilities)

        self.data = BILBO_Sample()

        self.device.callbacks.stream.register(self._onStreamCallback)
        self.device.callbacks.disconnected.register(self._disconnected_callback)

        # self._thread = threading.Thread(target=self._task, daemon=True)
        # self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def setControlConfiguration(self, config):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def loadControlConfiguration(self, name):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def saveControlConfiguration(self, name):
        raise NotImplementedError

    # === CLASS METHODS ================================================================================================

    # === METHODS ======================================================================================================

    # === PROPERTIES ===================================================================================================
    @property
    def id(self):
        return self.device.information.device_id

    # === COMMANDS ===========================================================================
    def balance(self, state):
        self.control.setControlMode(BILBO_Control_Mode.BALANCING)

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        self.control.setControlMode(0)

    # ------------------------------------------------------------------------------------------------------------------
    def setLEDs(self, red, green, blue):
        self.device.executeFunction('setLEDs', arguments={'red': red, 'green': green, 'blue': blue})

    # ------------------------------------------------------------------------------------------------------------------
    def _onStreamCallback(self, stream, *args, **kwargs):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _disconnected_callback(self, *args, **kwargs):
        # self._exit_task = True
        # self._thread.join()
        del self.experiment_handler

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        while not self._exit_task:
            time.sleep(0.1)

    # ------------------------------------------------------------------------------------------------------------------
    def __del__(self):
        print(f"Deleting {self.id}")
