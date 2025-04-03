import typing
import utils as utils
import core.communication.protocol as protocol
from utils.bytes_utils import byteArrayToInt
from ctypes import Structure, c_ubyte, c_uint8, c_uint16, c_uint32


# noinspection PyTypeChecker
class UART_Message(protocol.Message):
    cmd: int
    tick: int = 1
    flag: int
    module: int
    address: list
    data: typing.Union[list, bytes]

class UART_Protocol(protocol.Protocol):
    """
       |   BYTE    |   NAME            |   DESCRIPTION                 |   VALUE
       |   0       |   HEADER[0]       |   Header byte                 |   0x55
       |   1       |   TICK[0]         |   First Byte of Tick          |
       |   2       |   TICK[1]         |   Second Byte of Tick         |
       |   3       |   TICK[2]         |   Third Byte of Tick          |
       |   4       |   TICK[3]         |   Fourth Byte of Tick         |
       |   5       |   CMD             |   Command                     |
       |   6       |   MODULE          |   Module Address              |
       |   7       |   ADD[0]          |   Address                     |
       |   8       |   ADD[1]          |   Address                     |
       |   9       |   FLAG            |   Flag                        |
       |   10      |   LEN[0]          |   Length of the payload       |
       |   11      |   LEN[1]          |   Length of the payload       |
       |   12      |   PAYLOAD[0]      |   Payload                     |
       |   12+N-1  |   PAYLOAD[N-1]    |   Payload                     |
       |   12+N    |   CRC8            |   CRC8 of the Payload         |
       """

    base_protocol = None
    protocol_identifier = 0
    Message = UART_Message

    idx_header = 0
    header = 0x55
    idx_tick = 1
    idx_cmd = 5
    idx_module = 6
    idx_add_0 = 7
    idx_add_1 = 8
    idx_flag = 9
    idx_len = 10
    idx_payload = 12
    offset_crc8 = 12

    protocol_overhead = 13

    @classmethod
    def decode(cls, data):
        """

        :param data:
        :return:
        """
        msg = cls.Message()
        msg.tick = utils.bytes_utils.byteArrayToInt(data[cls.idx_tick:cls.idx_tick + 4], "little")

        payload_len = utils.bytes_utils.byteArrayToInt(data[cls.idx_len:cls.idx_len + 2])
        msg.cmd = data[cls.idx_cmd]
        msg.module = data[cls.idx_module]
        msg.flag = data[cls.idx_flag]
        msg.address = byteArrayToInt(data[cls.idx_add_0:cls.idx_add_1+1])
        msg.data = data[cls.idx_payload:cls.idx_payload + payload_len]

        return msg

    @classmethod
    def encode(cls, msg: UART_Message):
        """

        :param msg:
        :return:
        """
        buffer = [0] * (cls.protocol_overhead + len(msg.data))

        buffer[cls.idx_header] = cls.header
        buffer[cls.idx_tick:cls.idx_tick+4] = utils.bytes_utils.intToByteList(msg.tick, num_bytes=4, byteorder="little")

        buffer[cls.idx_cmd] = msg.cmd
        buffer[cls.idx_module] = msg.module
        buffer[cls.idx_add_0:cls.idx_add_1+1] = msg.address
        buffer[cls.idx_flag] = msg.flag
        buffer[cls.idx_len:cls.idx_len+2] = utils.bytes_utils.intToByteList(len(msg.data), num_bytes=2)
        buffer[cls.idx_payload:cls.idx_payload + len(msg.data)] = msg.data
        buffer[cls.offset_crc8 + len(msg.data)] = 0
        buffer = bytes(buffer)
        return buffer

    @classmethod
    def check(cls, data):
        """

        :param data:
        :return:
        """
        payload_len = data[cls.idx_len]

        if not data[cls.idx_header] == cls.header:
            return 0

        if not len(data) == (payload_len + cls.protocol_overhead):
            return 0


UART_Message._protocol = UART_Protocol
