import dataclasses
import queue
import threading
import time

import core.communication.wifi.tcp.tcp as tcp
import core.communication.wifi.udp.udp as udp
import utils.network as network
from core.communication.protocol import Message
from core.communication.wifi.tcp.protocols.tcp_base_protocol import TCP_Base_Message, TCP_Base_Protocol
from core.communication.wifi.tcp.protocols.tcp_json_protocol import TCP_JSON_Protocol, TCP_JSON_Message
from utils.callbacks import callback_handler, CallbackContainer
import core.settings as settings
from utils.logging_utils import Logger, setLoggerLevel

logger = Logger('wifi')
logger.setLevel('DEBUG')
setLoggerLevel(logger='udp', level='WARNING')
setLoggerLevel(logger='UDP', level='WARNING')
setLoggerLevel(logger='tcp', level='DEBUG')


# ======================================================================================================================
@dataclasses.dataclass
class ServerData:
    address: str = None
    port: int = None
    uid: list = None


@callback_handler
class WIFI_Connection_Callbacks:
    rx: CallbackContainer
    connected: CallbackContainer
    disconnected: CallbackContainer


# ======================================================================================================================
class WIFI_Connection:
    callbacks: WIFI_Connection_Callbacks
    events: dict[str, threading.Event]

    id: str
    address: str
    config: dict
    rx_queue: queue.Queue
    connected: bool = False
    registered: bool = False

    base_protocol = TCP_Base_Protocol
    protocol = TCP_JSON_Protocol

    _server_data: ServerData
    _thread: threading.Thread
    _udp: udp.UDP
    _tcp_socket: tcp.TCP_Socket
    _exit: bool = False

    # === INIT =========================================================================================================
    def __init__(self, id: str = '', config: dict = None):

        # Config
        default_config = {
            'rx_queue': False
        }

        if config is None:
            config = {}

        self.config = {**default_config, **config}

        self.id = id

        self.address = network.getLocalIP_RPi()

        if self.address is None:
            logger.warning("No local IP address found. Wifi Mode disabled")

        self._server_data = ServerData()
        self._udp_server_broadcast = udp.UDP(address=self.address, port=settings.UDP_PORT_ADDRESS_STREAM)
        self._udp_server_broadcast.callbacks.rx.register(self._udp_serverBroadcast_rxCallback)

        tcp_socket_config = {
            'rx_queue': False
        }

        self._tcp_socket = tcp.TCP_Socket(config=tcp_socket_config)
        self._tcp_socket.callbacks.rx.register(self._tcp_rxCallback)
        self._tcp_socket.callbacks.disconnected.register(self._tcp_disconnectedCallback)

        self.callbacks = WIFI_Connection_Callbacks()

        self.events = {
            'rx': threading.Event()
        }

        self.rx_queue = queue.Queue()
        self._thread = threading.Thread(target=self._threadFunction, daemon=True)

    # === METHODS ======================================================================================================
    def start(self):
        logger.info("Start WIFI Connection")
        self._thread.start()
        self._udp_server_broadcast.start()
        self._tcp_socket.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self._exit = True
        self._udp_server_broadcast.close()
        self._tcp_socket.close()
        self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def disconnect(self):
        self._tcp_socket.disconnect()
        self.connected = False

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message: Message):
        self._send(message)

    # === PRIVATE METHODS ==============================================================================================
    def _threadFunction(self):

        while not self._exit:
            if not self.connected:
                success = self._connect()

                if not success:
                    logger.warning(f'Cannot connect to server. Retry in 5s ...')
                    time.sleep(1)

            time.sleep(0.1)

    # ------------------------------------------------------------------------------------------------------------------
    def _connect(self) -> bool:
        logger.debug("Starting to connect to Server")
        success = self._listenForServerData(timeout=3)

        if not success:
            return False

        self._tcp_socket.connect(address=self._server_data.address, port=self._server_data.port)
        connected = self._tcp_socket.events['connected'].wait(timeout=1)

        if connected:
            self.connected = True
            # Send the handshake message
            logger.debug(f"Sending handshake to server {self._server_data.address}:{self._server_data.port} ...")
            self._sendHandshake()
        else:
            logger.error(f"Cannot connect to server {self._server_data.address}:{self._server_data.port}")
            return False

        logger.info(f"Connected to server {self._server_data.address}:{self._server_data.port}")

        for callback in self.callbacks.connected:
            callback()

        return self.connected

    # ------------------------------------------------------------------------------------------------------------------
    def _listenForServerData(self, timeout=2):
        self._server_data = ServerData()
        # Listen for the server address on UDP
        logger.debug(f"Listening for server data on UDP port {self._udp_server_broadcast.ports[0]}...")

        start_time = time.time()
        while self._server_data.address is None:
            time.sleep(1)
            elapsed_time = time.time() - start_time
            if elapsed_time >= timeout:
                logger.warning("Timeout reached while waiting for server data.")
                return False

        logger.debug(f"Server data received: {self._server_data.address}:{self._server_data.port}")

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _send(self, message: Message):

        # Check if the tcp socket is connected
        if not self._tcp_socket.connected:
            # logger.error(f"Cannot send message over TCP: Not connected")
            return

        # Check if the protocol of the message is supported
        if message._protocol is not self.protocol:
            logger.error(f"Cannot send message with protocol: {message._protocol}")

        # Generate the payload buffer from the message
        payload = message.encode()

        # Generate a base message for the tcp socket
        tcp_msg = self._tcp_socket.protocol.Message()
        tcp_msg.data = payload
        tcp_msg.data_protocol_id = message._protocol.identifier
        tcp_msg.source = self.address

        tcp_msg.address = self._server_data.address

        # Generate the buffer from the base message
        buffer = tcp_msg.encode()
        # Send the buffer over the tcp socket
        self._tcp_socket.send(buffer)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendHandshake(self):

        # Generate the handshake message
        handshake_message = TCP_JSON_Message()
        handshake_message.type = 'event'
        handshake_message.event = 'handshake'
        handshake_message.data = {
            'address': self.address,
            'name': self.id
        }

        self._send(handshake_message)

    # ------------------------------------------------------------------------------------------------------------------
    def _receiveServerHandshake(self, message):
        logger.info(f"Received server data. Name: {message.id}, UID: {message.uid}.")

    # ------------------------------------------------------------------------------------------------------------------
    def _tcp_rxCallback(self, message: bytes):
        """
        This function is called if a message is received from the server
        Args:
            message:
        """

        message = self._tcp_decodeMessage(message)

        if message is not None:
            if self.config['rx_queue']:
                self.rx_queue.put_nowait(message)

            for callback in self.callbacks.rx:
                callback(message)

            self.events['rx'].set()

    # ------------------------------------------------------------------------------------------------------------------
    def _tcp_disconnectedCallback(self, tcp_socket, *args, **kwargs):
        self.connected = False

        logger.warning("Lost connection to server")
        for callback in self.callbacks.disconnected:
            callback()

    # ------------------------------------------------------------------------------------------------------------------
    def _udp_serverBroadcast_rxCallback(self, message: udp.UDP_JSON_Message, *args, **kwargs):
        # Try to decode the UDP message and look for address and port of the server
        try:
            address = message.data['address']
            port = message.data['port']
            if address is not None and port is not None:
                self._server_data.address = address
                self._server_data.port = port
        except Exception as e:
            logger.warning("Server Address Broadcast not readable")

    # ------------------------------------------------------------------------------------------------------------------
    def _tcp_decodeMessage(self, data):

        try:
            base_message: TCP_Base_Message = TCP_Base_Protocol.decode(data)
        except Exception as e:
            logger.info(f"Received faulty TCP message")
            return

        if base_message is None:
            logger.info(f"Received faulty TCP message")
            return

        # Check if the protocol is correct
        if not base_message.data_protocol_id == self.protocol.identifier:
            logger.warning(f"Received faulty TCP message with protocol {base_message.data_protocol_id}")
            return

        try:
            message = self.protocol.decode(base_message.data)
        except Exception as e:
            logger.warning(f"Received faulty TCP message with protocol {base_message.data_protocol_id}")
            return
        return message
