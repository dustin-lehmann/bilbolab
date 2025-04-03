from typing import Union

from core.communication.protocol import Protocol, Message
from utils.network import ipv4_to_bytes, bytes_to_ipv4


class TCP_Base_Message(Message):
    data_protocol_id: int
    source: str
    address: str
    data: list

    def __init__(self):
        self.data_protocol_id = None
        self.source = None
        self.address = None
        self.data = None


class TCP_Base_Protocol(Protocol):
    """
    |   BYTE    |   NAME            |   DESCRIPTION                 |   VALUE
    |   0       |   HEADER[0]       |   first header byte           |   0x55
    |   1       |   HEADER[1]       |   second header byte          |   0x55
    |   2       |   SRC[0]          |   Source Address                   |
    |   3       |   SRC[1]          |   Source Address                   |
    |   4       |   SRC[2]          |   Source Address                   |
    |   5       |   SRC[3]          |   Source Address                   |
    |   6       |   ADD[0]          |   Target Address                     |
    |   7       |   ADD[1]          |   Target Address                     |
    |   8       |   ADD[2]          |   Target Address                     |
    |   9       |   ADD[3]          |   Target Address                     |
    |   10       |   PROTOCOL        |   Protocol ID                 |
    |   11       |   LEN[0]          |   Length of the payload       |
    |   12       |   LEN[1]          |   Length of the payload       |
    |   13      |   LEN[2]          |   Length of the payload       |
    |   14       |   LEN[3]          |   Length of the payload       |
    |   15       |   PAYLOAD[0]      |   Payload                     |
    |   15+N-1   |   PAYLOAD[N-1]    |   Payload                     |
    |   15+N     |   CRC8            |   CRC8 of the Payload         |
    |   16+N     |   FOOTER          |   Footer                      |   0x5D
    """
    base = None
    identifier = 0
    Message = TCP_Base_Message

    idx_protocol = 10
    idx_src = slice(2, 6)
    idx_add = slice(6, 10)
    idx_len = slice(11, 15)
    idx_payload = 15
    offset_crc = 15
    offset_footer = 16

    header_0 = 0x55
    header_1 = 0x55
    footer = 0x5D

    protocol_overhead = 17

    def __init__(self):
        super().__init__()

    @classmethod
    def decode(cls, data: Union[list, bytes, bytearray]) -> TCP_Base_Message:
        check = cls.check(data)

        if not check:
            # logger.debug(f"Corrupted TCP message received")
            return None

        msg = TCP_Base_Message()
        msg.data_protocol_id = data[cls.idx_protocol]
        msg.source = bytes_to_ipv4(data[cls.idx_src])
        msg.address = bytes_to_ipv4(data[cls.idx_add])
        payload_len = int.from_bytes(data[cls.idx_len], byteorder="little")
        msg.data = data[cls.idx_payload:cls.idx_payload + payload_len]
        # logging.debug( f"TCP Message:[PROTOCOL: [{bytearray_to_string(msg.data_protocol_id)}],
        # SRC: [{bytearray_to_string(msg.src)}], ADD: " f"[{bytearray_to_string(msg.add)}],
        # DATA: [{bytearray_to_string(msg.data)}]]")
        return msg

    @classmethod
    def encode(cls, msg: TCP_Base_Message, *args, **kwargs):
        """
        - Encode a TCP message from a given TCP_Message
        :param msg: TCP_Message object
        :param base_encode: Since the TCP_Protocol has no base protocol, this is not used
        :return: byte buffer of the message
        """
        assert (isinstance(msg, TCP_Base_Message))
        buffer = [0] * (len(msg.data) + cls.protocol_overhead)
        buffer[0] = cls.header_0
        buffer[1] = cls.header_1
        buffer[cls.idx_src] = ipv4_to_bytes(msg.source)
        buffer[cls.idx_add] = ipv4_to_bytes(msg.address)

        if hasattr(msg, 'data_protocol_id'):
            buffer[cls.idx_protocol] = msg.data_protocol_id
        else:
            buffer[cls.idx_protocol] = 0

        buffer[cls.idx_len] = len(msg.data).to_bytes(length=4, byteorder="little")
        buffer[cls.idx_payload: cls.idx_payload + len(msg.data)] = msg.data
        buffer[cls.offset_crc + len(msg.data)] = 0x00  # TODO
        buffer[cls.offset_footer + len(msg.data)] = cls.footer
        buffer = bytes(buffer)
        return buffer

    @classmethod
    def check(cls, data):
        if not data[0] == cls.header_0:
            return 0
        if not data[1] == cls.header_1:
            return 0

        payload_len = int.from_bytes(data[cls.idx_len], byteorder="little")
        if not len(data) == payload_len + cls.protocol_overhead:
            return 0

        if not data[payload_len + cls.offset_footer] == cls.footer:
            return 0

        return 1


TCP_Base_Message._protocol = TCP_Base_Protocol
