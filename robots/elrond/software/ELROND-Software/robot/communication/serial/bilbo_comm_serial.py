import ctypes

from core.communication.serial.serial_interface import Serial_Interface, SerialMessage
import robot.lowlevel.stm32_addresses as addresses
from robot.communication.serial.bilbo_serial_messages import BILBO_SERIAL_MESSAGES
from robot.lowlevel.stm32_general import twipr_firmware_revision
from robot.lowlevel.stm32_messages import *
from utils.callbacks import callback_handler, CallbackContainer, OPTIONAL
from utils.ctypes_utils import CType
from utils.events import ConditionEvent, event_handler
from utils.logging_utils import Logger

logger = Logger("BILBO SERIAL")
logger.setLevel("INFO")


# === CALLBACKS ========================================================================================================
@callback_handler
class BILBO_Serial_Communication_Callbacks:
    rx: CallbackContainer
    event: CallbackContainer(parameters=[('messages', list, OPTIONAL)])
    error: CallbackContainer
    debug: CallbackContainer


# === EVENTS ===========================================================================================================
@event_handler
class BILBO_Serial_Communication_Events:
    rx: ConditionEvent
    event = ConditionEvent(flags=[('type', type)])
    error: ConditionEvent
    debug: ConditionEvent


# === BILBO_Serial_Communication =======================================================================================
class BILBO_Serial_Communication:
    interface: Serial_Interface
    callbacks: BILBO_Serial_Communication_Callbacks

    def __init__(self, interface: Serial_Interface):
        self.interface = interface
        self.interface.callbacks.rx.register(self._rx_callback)
        self.interface.callbacks.event.register(self._rx_event_callback)
        self.callbacks = BILBO_Serial_Communication_Callbacks()
        self.events = BILBO_Serial_Communication_Events()
        self.interface.addMessage(BILBO_SERIAL_MESSAGES)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        if not self.interface.isRunning():
            self.interface.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.interface.close()

    # ------------------------------------------------------------------------------------------------------------------
    def writeValue(self, module: int = 0, address: (int, list) = None, value=None, type=ctypes.c_uint8):
        self.interface.write(module, address, value, type)

    # ------------------------------------------------------------------------------------------------------------------
    def readValue(self, address: int, module: int = 0, type=ctypes.c_uint8):
        return self.interface.read(address, module, type)

    # ------------------------------------------------------------------------------------------------------------------
    def executeFunction(self, address, module: int = 0, data=None, input_type: CType = None, output_type=None,
                        timeout=1):
        return self.interface.function(address, module, data, input_type, output_type, timeout)

    # ------------------------------------------------------------------------------------------------------------------
    def readTick(self):
        tick = self.interface.read(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                   address=addresses.TWIPR_GeneralAddresses.ADDRESS_FIRMWARE_TICK,
                                   type=ctypes.c_uint32)

        return tick

    # ------------------------------------------------------------------------------------------------------------------
    def readFirmwareRevision(self):
        revision = self.interface.read(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                       address=addresses.TWIPR_GeneralAddresses.ADDRESS_FIRMWARE_REVISION,
                                       type=twipr_firmware_revision)

        return revision

    # ------------------------------------------------------------------------------------------------------------------
    def debug(self, state):
        self.interface.function(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                address=addresses.TWIPR_GeneralAddresses.ADDRESS_FIRMWARE_DEBUG,
                                data=state,
                                input_type=ctypes.c_uint8)

    # === PRIVATE METHODS ==============================================================================================
    def _rx_callback(self, message: SerialMessage, *args, **kwargs):
        pass
        # message.executeCallback()

    def _rx_event_callback(self, message: SerialMessage, *args, **kwargs):
        for callback in self.callbacks.event:
            if callback.parameters['messages'] is not None:
                if type(message) in callback.parameters['messages']:
                    callback(message)
            else:
                callback(message)

        self.events.event.set(resource=message, flags={'type': type(message)})
