import time

from core.communication.device_server import Device
from core.utils.callbacks import callback_definition
from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger
from core.utils.time import delayed_execution, setTimeout
from robots.frodo.robot.frodo_control import FRODO_Control
from robots.frodo.robot.frodo_core import FRODO_Core
from robots.frodo.robot.frodo_definitions import FRODO_Config, FRODO_ControlMode
from robots.frodo.robot.frodo_interfaces import FRODO_Interfaces


# ======================================================================================================================
@callback_definition
class FRODO_Callbacks:
    ...


@event_definition
class FRODO_Events:
    ...


# === FRODO ============================================================================================================
class FRODO:
    id: str
    device: Device

    callbacks: FRODO_Callbacks
    events: FRODO_Events

    # === INIT =========================================================================================================
    def __init__(self, device: Device, config: FRODO_Config):
        self.device = device
        self.config = config
        self.logger = Logger(f"{self.id}")
        self.core = FRODO_Core(robot_id=self.id, device=self.device, config=config)
        self.control = FRODO_Control(device=self.device, information=config)
        self.interfaces = FRODO_Interfaces(core=self.core, control=self.control)
        self.callbacks = FRODO_Callbacks()
        self.events = FRODO_Events()

    # === PROPERTIES ===================================================================================================
    @property
    def id(self):
        return self.config.id

    # === METHODS ======================================================================================================
    def setLEDs(self, red, green, blue):
        self.device.executeFunction('setLEDs', arguments={'red': red, 'green': green, 'blue': blue})

    # ------------------------------------------------------------------------------------------------------------------
    def beep(self, frequency=1000, time_ms=250, repeats=1):
        self.device.executeFunction(function_name='beep',
                                    arguments={'frequency': frequency, 'time_ms': time_ms, 'repeats': repeats})

    # === PRIVATE METHODS ==============================================================================================

    # ------------------------------------------------------------------------------------------------------------------
