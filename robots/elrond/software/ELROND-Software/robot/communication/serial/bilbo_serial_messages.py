import ctypes
import enum

from core.communication.serial.core.serial_protocol import UART_Message
from core.communication.serial.serial_interface import Serial_Interface, SerialMessage, SerialCommandType
import robot.lowlevel.stm32_addresses as addresses
from robot.lowlevel.stm32_general import twipr_firmware_revision
from robot.lowlevel.stm32_messages import *
from utils.callbacks import callback_handler, CallbackContainer
from utils.ctypes_utils import CType
from utils.events import ConditionEvent
from utils.logging_utils import Logger


# ======================================================================================================================
class bilbo_debug_message_data_type(ctypes.Structure):
    _fields_ = [
        ("flag", ctypes.c_uint8),
        ("text", ctypes.c_char * 100)
    ]


def debugprint(data: bilbo_debug_message_data_type, *args, **kwargs):
    logger = Logger("BILBO DEBUG")
    try:
        flag = data['flag']
        text = data['text'].decode("utf-8")
        if flag == 0:
            logger.info(f"DEBUG: {text}")
        if flag == 1:
            logger.info(f"{text}")
        if flag == 2:
            logger.warning(f"{text}")
        if flag == 3:
            logger.error(f"{text}")
    except Exception as e:
        ...


class BILBO_Debug_Message(SerialMessage):
    module: int = 1
    address: int = BILBO_LL_MESSAGE_PRINT
    command: SerialCommandType = SerialCommandType.UART_CMD_EVENT
    data_type: type = bilbo_debug_message_data_type
    callback = staticmethod(debugprint)


# ======================================================================================================================
class sequencer_event_t(enum.IntEnum):
    STARTED = 1
    FINISHED = 2
    ABORTED = 3


class sequencer_event_message_data_t(ctypes.Structure):
    _fields_ = [
        ("event", ctypes.c_uint8),
        ("sequence_id", ctypes.c_uint16),
        ("sequence_tick", ctypes.c_uint32),
        ("tick", ctypes.c_uint32)
    ]


class BILBO_Sequencer_Event_Message(SerialMessage):
    module: int = 1
    address: int = BILBO_LL_MESSAGE_SEQUENCER_EVENT
    command: SerialCommandType = SerialCommandType.UART_CMD_EVENT
    data_type: type = sequencer_event_message_data_t


# ======================================================================================================================
class bilbo_error_message_data_type(ctypes.Structure):
    _fields_ = [
        ('type', ctypes.c_uint8),
        ('error', ctypes.c_uint8),
        ('overall_error', ctypes.c_uint8)
    ]


class BILBO_Error_Message(SerialMessage):
    module = 1
    address = BILBO_LL_MESSAGE_ERROR
    command = SerialCommandType.UART_CMD_EVENT
    data_type = bilbo_error_message_data_type


# ======================================================================================================================
BILBO_SERIAL_MESSAGES = [BILBO_Debug_Message, BILBO_Sequencer_Event_Message]
