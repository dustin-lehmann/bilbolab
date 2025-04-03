import ctypes
import dataclasses
import enum
import threading

# === OWN PACKAGES =====================================================================================================
from core.communication.serial.core.serial_protocol import UART_Message
from core.communication.serial.core.serial_connection import SerialConnection
import utils
from utils.ctypes_utils import is_valid_ctype, ctype_to_value, value_to_ctype, bytes_to_ctype, ctype_to_bytes, \
    bytes_to_value, value_to_bytes
from utils.callbacks import callback_handler, CallbackContainer, Callback
from utils.events import event_handler, ConditionEvent
from utils.logging_utils import Logger

# === GLOBAL VARIABLES =================================================================================================

logger = Logger('SERIAL')
logger.setLevel('INFO')


# known_messages = []  # Holds all defined SerialMessages

# === SerialCommandType ================================================================================================
class SerialCommandType(enum.IntEnum):
    UART_CMD_WRITE = 0x01
    UART_CMD_READ = 0x02
    UART_CMD_ANSWER = 0x03
    UART_CMD_STREAM = 0x04
    UART_CMD_EVENT = 0x05
    UART_CMD_MSG = 0x06
    UART_CMD_FCT = 0x07
    UART_CMD_ECHO = 0x08


# === SerialMessage ====================================================================================================
class SerialMessage:
    module: int = 1
    tick: int = 0
    address: int = None
    command: SerialCommandType = None
    flag: int = None
    data: dict = None
    callback: Callback = None
    data_type: type = None

    @classmethod
    def decode(cls, message: UART_Message) -> 'SerialMessage':
        if cls.data_type is None:
            return None
        try:
            msg = cls()
            msg.data = bytes_to_value(message.data, cls.data_type)
            msg.command = SerialCommandType(message.cmd)
            msg.tick = message.tick
            return msg
        except Exception as e:
            return None


# ======================================================================================================================
class ReadRequest:
    event: threading.Event
    module: int = 0
    address: int
    msg: UART_Message = None
    timeout: bool = True
    flag: int = 0

    def __init__(self):
        self.event = threading.Event()


# === CALLBACKS ========================================================================================================
@callback_handler
class SerialInterface_Callbacks:
    rx_all: CallbackContainer
    event_all: CallbackContainer
    stream_all: CallbackContainer
    error_all: CallbackContainer
    rx: CallbackContainer
    event: CallbackContainer
    stream: CallbackContainer
    error: CallbackContainer


# === EVENTS ===========================================================================================================
@event_handler
class SerialInterface_Events:
    rx: ConditionEvent
    event: ConditionEvent
    stream: ConditionEvent
    error: ConditionEvent


# ======================================================================================================================
class Serial_Interface:
    device: SerialConnection
    callbacks: SerialInterface_Callbacks
    known_messages: list[SerialMessage]

    _thread: threading.Thread
    _exit: bool = False
    _readRequest = list[ReadRequest]

    def __init__(self, port: str, baudrate: int = 115200):
        self.device = SerialConnection(device=port, baudrate=baudrate)

        self.callbacks = SerialInterface_Callbacks()

        self.known_messages = []

        self._readRequests = []

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def addMessage(self, messages: (object, list[object])):
        if not isinstance(messages, list):
            messages = [messages]

        for message in messages:
            self.known_messages.append(message)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.device.start()
        self._thread = threading.Thread(target=self._thread_function, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.device.close()

    # ------------------------------------------------------------------------------------------------------------------
    def write(self, module: int = 0, address: (int, list) = None, value=None, type=ctypes.c_uint8):
        assert (type is None or is_valid_ctype(type))

        if value is None:
            return

        data_bytes = value_to_bytes(value, type)

        self._send(cmd=SerialCommandType.UART_CMD_WRITE, module=module, address=address, flag=0, data=data_bytes)

    # ------------------------------------------------------------------------------------------------------------------
    def echo(self, module: int = 0, address: (int, list) = None, value=None, type=ctypes.c_uint8, flag: int = 0):
        assert (type is None or is_valid_ctype(type))
        raise NotImplementedError()

        # if not isinstance(value, type):
        #     value = type(value)
        # data_bytes = bytes(value)
        #
        # self._send(cmd=SerialCommandType.UART_CMD_ECHO, module=module, address=address, flag=flag, data=data_bytes)

    # ------------------------------------------------------------------------------------------------------------------

    def read(self, address, module: int = 1, type=None):
        assert (type is None or is_valid_ctype(type))

        # Send the message for reading
        self._send(cmd=SerialCommandType.UART_CMD_READ, module=module, address=address, flag=0, data=[])
        request = self._registerRead(module=module, address=address)

        event_success = request.event.wait(timeout=0.1)

        if event_success and request.msg.flag == 1:
            # Check if the data length matches the data type
            if not ctypes.sizeof(type) == len(request.msg.data):
                return None
            else:
                return bytes_to_value(request.msg.data, type)
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------

    def function(self, address, module: int = 1, data=None, input_type=None, output_type=None, timeout=1):

        assert (input_type is None or is_valid_ctype(input_type))
        assert (output_type is None or is_valid_ctype(output_type))

        # Convert the input data
        if input_type is not None:
            data = value_to_ctype(data, input_type)
            buffer = ctype_to_bytes(data)
        else:
            buffer = None

        # logger.info(f"Sending function call to module {module} and address {address} with data {buffer}")
        self._send(cmd=SerialCommandType.UART_CMD_FCT, module=module, address=address, flag=0, data=buffer)

        # Register for reading if type is not None
        if output_type is not None:
            req = self._registerRead(module=module, address=address)
            event_success = req.event.wait(timeout=timeout)
            if event_success and req.msg.flag == 1:
                # Check if the data length matches the data type
                if not ctypes.sizeof(output_type) == len(req.msg.data):
                    return None
                else:
                    x = ctype_to_value(bytes_to_ctype(req.msg.data, output_type), output_type)
                    return ctype_to_value(bytes_to_ctype(req.msg.data, output_type), output_type)
            else:
                return None
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def isRunning(self):
        return self._thread.is_alive()

    # === PRIVATE METHODS ==============================================================================================

    def _thread_function(self):
        while not self._exit:
            # Wait until there is a message in the rx queue of the device
            msg = self.device.rx_queue.get(timeout=None)

            # Handle the rx message and then go back to waiting
            self._handleIncomingMessage(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleIncomingMessage(self, message: UART_Message):
        if message.cmd == SerialCommandType.UART_CMD_WRITE:
            # ERROR. Should not happen
            logger.warning(f"Received write request for module {message.module} and address {message.address}. Not "
                           f"supported")
            pass
        elif message.cmd == SerialCommandType.UART_CMD_READ:
            # ERROR. Should not happen
            logger.warning(f"Received read request for module {message.module} and address {message.address}. Not "
                           f"supported")
            pass
        elif message.cmd == SerialCommandType.UART_CMD_ANSWER:
            self._handleMessage_answer(message)

        elif message.cmd == SerialCommandType.UART_CMD_FCT:
            logger.warning(f"Received function call for module {message.module} and address {message.address}. Not "
                           f"supported")
            pass
        elif message.cmd == SerialCommandType.UART_CMD_STREAM:
            self._handleMessage_stream(message)
            ...
        elif message.cmd == SerialCommandType.UART_CMD_EVENT:
            self._handleMessage_event(message)

        else:
            logger.warning(f"Received message with unknown command {message.cmd} for module {message.module} and "
                           f"address {message.address}. Not supported")

        # self.callbacks.rx_all.call(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleMessage_answer(self, msg):

        # Go through all the read requests and check if anyone waits for this
        if len(self._readRequests) == 0:
            return

        found_request = None
        for req in self._readRequests:
            if req.module == msg.module and req.address == msg.address:
                logger.debug(f"Got an answer for request {req.module}:{req.address}")
                req.msg = msg
                req.event.set()
                found_request = req
                break

        if found_request is not None:
            self._readRequests.remove(found_request)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleMessage_stream(self, message):
        self.callbacks.stream_all.call(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleMessage_event(self, message):

        known_message_type = next((m for m in self.known_messages if message.address == m.address), None)

        if known_message_type is not None:
            known_message = known_message_type.decode(message)
            if known_message is not None:
                if known_message.callback is not None:
                    known_message.callback(known_message.data)
                self.callbacks.event.call(known_message)

        # self.callbacks.event_all.call(message)

    # ------------------------------------------------------------------------------------------------------------------

    def _registerRead(self, module, address):
        request = ReadRequest()

        request.address = address
        request.module = module

        logger.debug(f"Register read request for module {module} and address {address}")
        self._readRequests.append(request)
        return request

    # ------------------------------------------------------------------------------------------------------------------
    def _send(self, cmd: int = 0, module: int = 0, address: (bytes, bytearray, list, int) = None, flag: int = 0,
              data=None):
        if isinstance(address, int):
            address = list(utils.bytes_utils.intToByte(address, 2))
        elif isinstance(address, bytes):
            address = list(address)
        elif isinstance(address, bytearray):
            address = list(address)

        msg = UART_Message()
        msg.cmd = cmd
        msg.module = module
        msg.address = address
        msg.flag = flag

        if data is None:
            data = []

        msg.data = data
        self._sendMessage(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendMessage(self, msg: UART_Message):
        # Check the Message
        assert (msg.data is not None)
        assert (len(msg.address) == 2)
        assert (msg.cmd in iter(SerialCommandType))

        self.device.send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendRaw(self, buffer):
        self.device.sendRaw(buffer)

    # # ------------------------------------------------------------------------------------------------------------------
    # def _uart_rx_callback(self, message: UART_Message, **kwargs):
    #     ...
    #     # if message.cmd == SerialCommandType.UART_CMD_EVENT:
    #     #
    #     #     if message.address == self.known_messages[1].address:
    #     #         x = self.known_messages[1].decode(message)
    #     #         x.executeCallback()
    #     #
    #     # for callback in self.callbacks['rx']:
    #     #     callback(message)
