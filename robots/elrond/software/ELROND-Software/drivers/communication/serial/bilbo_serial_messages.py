import ctypes
import enum

from core.communication.serial.core.serial_protocol import UART_Message
from core.communication.serial.serial_interface import Serial_Interface, SerialMessage, SerialCommandType
import drivers.lowlevel.stm32_addresses as addresses
from drivers.lowlevel.stm32_general import twipr_firmware_revision
from drivers.lowlevel.stm32_messages import *
from utils.callbacks import callback_handler, CallbackContainer
from utils.ctypes_utils import CType
from utils.events import ConditionEvent
from utils.logging_utils import Logger
from utils .teleplot import sendValue


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
            sendToPlot(text)
        if flag == 1:
            logger.info(f"{text}")
        if flag == 2:
            logger.warning(f"{text}")
        if flag == 3:
            logger.error(f"{text}")
    except Exception as e:
        ...

def sendToPlot(text):
    parts = text.split()
    if (parts[0] == "m1" or parts[0] == "m2") and len(parts) == 3:
        motor_name = parts[0]
        motor_speed_read = float(parts[1])
        motor_speed_calculated = float(parts[2])
        #motor_speed_calculated2 = float(parts[3])
        sendValue(f"{motor_name}_speed_read", motor_speed_read)
        sendValue(f"{motor_name}_speed_calculated", motor_speed_calculated)
        #sendValue(f"{motor_name}_speed_calculated2", motor_speed_calculated2)
    else:
        raise ValueError(f"Failed to parse speeds from text for motor {motor_name}")

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
