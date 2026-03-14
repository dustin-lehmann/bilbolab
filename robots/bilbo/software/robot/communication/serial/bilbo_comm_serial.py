import ctypes

from core.communication.serial.serial_interface import Serial_Interface, SerialMessage
import robot.lowlevel.stm32_addresses as addresses
from robot.communication.serial.bilbo_serial_messages import BILBO_SERIAL_MESSAGES
from robot.lowlevel.stm32_general import bilbo_firmware_revision, bilbo_firmware_info
from core.utils.callbacks import callback_definition, CallbackContainer, OPTIONAL
from core.utils.ctypes_utils import CType
from core.utils.events import Event, event_definition, EventFlag
from core.utils.logging_utils import Logger

logger = Logger("BILBO SERIAL")
logger.setLevel("INFO")


# === CALLBACKS ========================================================================================================
@callback_definition
class BILBO_Serial_Communication_Callbacks:
    rx: CallbackContainer
    event: CallbackContainer = CallbackContainer(parameters=[('messages', list, OPTIONAL)])
    # event: CallbackContainer
    error: CallbackContainer
    debug: CallbackContainer


# === EVENTS ===========================================================================================================
@event_definition
class BILBO_Serial_Communication_Events:
    rx: Event
    event = Event(flags=EventFlag('type', type))
    error: Event
    debug: Event


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
    def writeValue(self, module: int = 0, address: int | list = None, value=None, type=ctypes.c_uint8):
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
        tick = self.interface.read(module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
                                   address=addresses.BILBO_SystemAddresses.FIRMWARE_TICK,
                                   type=ctypes.c_uint32)

        return tick

    # ------------------------------------------------------------------------------------------------------------------
    def readFirmwareRevision(self):
        revision = self.interface.read(module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
                                       address=addresses.BILBO_SystemAddresses.FIRMWARE_REVISION,
                                       type=bilbo_firmware_revision)

        return revision

    # ------------------------------------------------------------------------------------------------------------------
    def readFirmwareInfo(self):
        info = self.interface.read(module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
                                   address=addresses.BILBO_SystemAddresses.FIRMWARE_INFO,
                                   type=bilbo_firmware_info)

        return info

    # ------------------------------------------------------------------------------------------------------------------
    def debug(self, state):
        self.interface.function(module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
                                address=addresses.BILBO_SystemAddresses.FIRMWARE_DEBUGFUNCTION,
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

        self.events.event.set(data=message, flags={'type': type(message)})
