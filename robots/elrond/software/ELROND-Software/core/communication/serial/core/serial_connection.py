import logging
import queue
import threading

from core.communication.serial.core.uart import UART_Socket
from core.communication.serial.core.serial_protocol import UART_Protocol, UART_Message
from utils.callbacks import callback_handler, CallbackContainer
from utils.exit import ExitHandler


@callback_handler
class SerialConnection_Callbacks:
    rx: CallbackContainer


class SerialConnection:
    _socket: UART_Socket

    rx_queue: queue.Queue
    tx_queue: queue.Queue

    protocol = UART_Protocol

    config: dict

    callbacks: SerialConnection_Callbacks
    events: dict[str, threading.Event]
    exit: ExitHandler
    _thread: threading.Thread
    _exit: bool

    def __init__(self, device: str, baudrate: int = 115200, config: dict = None):

        default_config = {
            'cobs': True,
            'delimiter': b'\x00',
            'use_queues': True
        }

        if config is None:
            config = {}

        self.config = {**default_config, **config}

        self._socket = UART_Socket(device=device, baudrate=baudrate, config=self.config)

        # Prepare the callbacks and events
        self.callbacks = SerialConnection_Callbacks()

        self.events = {
            'rx': threading.Event(),
            'error': threading.Event()
        }

        # self.exit = ExitHandler()
        # self.exit.register(self.close)
        self._exit = False
        self.rx_queue = queue.Queue()

    # === METHODS ======================================================================================================
    def start(self):

        # Start the socket
        self._socket.start()
        self._thread = threading.Thread(target=self._thread_fun, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self._exit = True
        # self._thread.join()
        self._socket.close()

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, msg: protocol.Message):
        buffer = self._encode_message(msg)
        if buffer is not None:
            self._socket.send(buffer)

    # ------------------------------------------------------------------------------------------------------------------
    def sendRaw(self, buffer):
        self._socket.send(buffer)

    # === PRIVATE METHODS ==============================================================================================
    def _encode_message(self, msg: protocol.Message):
        buffer = msg.encode()
        return buffer

    # ------------------------------------------------------------------------------------------------------------------
    def _decode_message(self, buffer):
        msg = self.protocol.decode(buffer)

        return msg

    # ------------------------------------------------------------------------------------------------------------------
    def _rx_handling(self, buffer):
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def _thread_fun(self):

        while not self._exit:
            try:
                data = self._socket.rx_queue.get(timeout=1)
                msg = self._decode_message(data)
                if msg is not None:
                    if self.config['use_queues']:
                        self.rx_queue.put(msg)
                    for cb in self.callbacks.rx:
                        cb(msg)
                    self.events['rx'].set()
            except queue.Empty:
                ...
        # Exit
