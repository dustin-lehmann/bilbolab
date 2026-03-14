import queue
import socket
import threading
import time
from cobs import cobs

from core.utils.exit import register_exit_callback
from core.hardware.network import getLocalIP_RPi
from core.utils.logging_utils import Logger
from core.utils.callbacks import callback_definition, CallbackContainer

logger = Logger('udp')
logger.setLevel('DEBUG')


@callback_definition
class UDP_Socket_Callbacks:
    rx: CallbackContainer


########################################################################################################################
class UDP_Socket:
    _socket: socket.socket
    address: str
    port: int
    _thread: threading.Thread

    config: dict
    _exit: bool
    callbacks: UDP_Socket_Callbacks

    _filterBroadcastEcho: bool
    _rx_queue: queue.Queue
    _thread_timeout = 0.001

    # === INIT =========================================================================================================
    def __init__(self, address, port, config: dict = None):

        if address is None:
            address = getLocalIP_RPi()

        self.address = address

        if self.address is None:
            raise Exception('No Local IP address')

        self.port = port

        if config is None:
            config = {}

        default_config = {
            'cobs': False,
            'filterBroadcastEcho': False,
        }

        self.config = {**default_config, **config}

        self.callbacks = UDP_Socket_Callbacks()

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        self._socket.settimeout(0)

        self._socket.bind(("", self.port))
        self._thread = threading.Thread(target=self._thread_fun, daemon=True)
        register_exit_callback(self.close)
        self._exit = False

    # === METHODS ======================================================================================================
    def start(self):
        logger.info(
            f"Starting UDP socket on {self.address}:{self.port} (Filter Broadcast Echo={self.config['filterBroadcastEcho']})")
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, data, address: str = '<broadcast>'):

        if isinstance(data, list):
            data = bytes(data)
        if isinstance(data, str):
            data = data.encode('utf-8')

        if self.config['cobs']:
            data = cobs.encode(data)
            data = data + b'\x00'

        self._socket.sendto(data, (address, self.port))

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        """

        :return:
        """
        self._exit = True
        self._socket.close()
        if self._thread.is_alive():
            self._thread.join(timeout=1)

    # ------------------------------------------------------------------------------------------------------------------
    def _thread_fun(self):
        while not self._exit:
            try:
                data, address = self._socket.recvfrom(1024)
                self._handleIncomingMessage(data, address)
            except BlockingIOError:
                pass

            time.sleep(self._thread_timeout)

        logger.info(f"Closing UDP Server on {self.address}: {self.port}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleIncomingMessage(self, data, address):
        if len(data) > 0:
            if address[0] == self.address and self.config['filterBroadcastEcho']:
                ...
            else:
                for callback in self.callbacks.rx:
                    callback(data, address, self.port)
