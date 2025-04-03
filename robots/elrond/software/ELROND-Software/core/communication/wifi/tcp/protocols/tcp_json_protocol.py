import dataclasses
import logging
import time as t
import orjson

from core.communication.protocol import Protocol, Message
from .tcp_base_protocol import TCP_Base_Protocol


# ======================================================================================================================
@dataclasses.dataclass
class TCP_JSON_Message(Message):
    address: (str, dict) = None
    source: str = None

    type: str = ''
    time: float = 0
    id: int = 0
    event: str = ''
    request_id: int = 0
    request_response: bool = False
    data: dict = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        self.id = id(self)
        self.time = t.time()


# ======================================================================================================================
class TCP_JSON_Protocol(Protocol):
    base = TCP_Base_Protocol
    Message = TCP_JSON_Message
    identifier = 0x02
    allowed_types = ['write', 'read', 'response', 'function', 'event', 'stream']
    meta_fields = ['time', 'id']

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def decode(cls, data: bytes):
        assert (isinstance(data, bytes))
        msg = cls.Message()
        msg_content = orjson.loads(data)

        if 'data' in msg_content:
            msg.data = msg_content['data']
        if 'address' in msg_content:
            msg.address = msg_content['address']
        if 'source' in msg_content:
            msg.source = msg_content['source']
        if 'type' in msg_content:
            msg.type = msg_content['type']
        if 'request_response' in msg_content:
            msg.request_response = msg_content['request_response']
        if 'id' in msg_content:
            msg.id = msg_content['id']
        if 'time' in msg_content:
            msg.time = msg_content['time']
        if 'request_id' in msg_content:
            msg.request_id = msg_content['request_id']
        if 'event' in msg_content:
            msg.event = msg_content['event']
        return msg

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def encode(cls, msg: TCP_JSON_Message, *args, **kwargs):
        """
        :param msg:
        :return:
        """
        # Check if the command is allowed
        if msg.type not in cls.allowed_types:
            logging.error(f"Command not allowed!")
            return

        # Check if it correctly set up for a command
        data = orjson.dumps(msg)

        return data

    @classmethod
    def check(cls, data):
        return 1


TCP_JSON_Message._protocol = TCP_JSON_Protocol  # Type: Ignore
