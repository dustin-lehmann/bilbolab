#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# Created By  : David Stoll
# Supervisor  : Dustin Lehmann
# Created Date: date/month/time ..etc
# version ='1.0'
# ---------------------------------------------------------------------------
""" This Module is responsible for receiving the Host-Server Ip via UDP """
# ---------------------------------------------------------------------------
# Module Imports
import errno
import queue
import select
import socket
import threading
import time
import cobs.cobs as cobs

from utils.time import time_ms
from utils.callbacks import callback_handler, CallbackContainer
from core.communication.wifi.tcp.protocols.tcp_base_protocol import TCP_Base_Protocol
from core.communication.protocol import Protocol
from utils.logging_utils import Logger

MAX_SOCKET_READ = 8192

logger = Logger('tcp')
logger.setLevel('DEBUG')


@callback_handler
class TCP_Socket_Callbacks:
    connected: CallbackContainer
    disconnected: CallbackContainer
    rx: CallbackContainer
    error: CallbackContainer


# TODO:
# - give the user the possibility to decide whether he wants to use the queue or callbacks or both
# ---------------------------------------------------------------------------
class TCP_Socket:
    """
    TCP socket wrapper for Raspberry Pi client side.
    Manages connection, sending, and receiving data with proper handling of partial packets.
    """
    server_address: str
    server_port: int

    rx_queue: queue.Queue
    tx_queue: queue.Queue

    config: dict
    connected: bool
    protocol: Protocol = TCP_Base_Protocol

    _socket: socket.socket
    _input_connections: list
    _output_connections: list
    _exit: bool

    _thread: threading.Thread
    _tx_thread: threading.Thread

    _close_check_time: int
    _close_check_interval_ms = 1000

    callbacks: TCP_Socket_Callbacks
    events: dict[str, threading.Event]

    _rx_buffer: bytes

    # === INIT =========================================================================================================
    def __init__(self, server_address: str = None, server_port: int = 6666, config: dict = None):
        """
        Initialize the TCP_Socket instance.
        """
        self.server_address = server_address
        self.server_port = server_port

        self.connected = False

        self.rx_queue = queue.Queue()
        self.tx_queue = queue.Queue()

        self._socket = None
        self._exit = False

        self._input_connections = []
        self._output_connections = []

        if config is None:
            config = {}

        default_config = {
            'delimiter': b'\x00',
            'cobs': True,
            'rx_queue': False,
        }
        self.config = {**default_config, **config}

        self.callbacks = TCP_Socket_Callbacks()

        self.events = {
            'connected': threading.Event(),
            'disconnected': threading.Event(),
            'error': threading.Event(),
            'rx': threading.Event()
        }

        self._close_check_time = 0

        # Initialize the receive buffer for handling partial packets.
        self._rx_buffer = b''

    # === METHODS ======================================================================================================
    def init(self):
        ...

    def start(self):
        """
        Start the main socket thread.
        """
        self._thread = threading.Thread(target=self._threadFunction)
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def connect(self, address=None, port=None):
        if address is not None:
            self.server_address = address
        if port is not None:
            self.server_port = port

        assert (self.server_address is not None and self.server_port is not None)

        self._connect(self.server_address, self.server_port)

    # ------------------------------------------------------------------------------------------------------------------
    def disconnect(self):
        self.connected = False
        time.sleep(0.01)
        for connection in self._input_connections:
            connection.close()
        for connection in self._output_connections:
            connection.close()
        self._input_connections = []
        self._output_connections = []
        self._socket.close()

        self.callbacks.disconnected.call()
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        """
        Close the socket connection.
        """
        self._exit = True
        self.connected = False
        self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, data):
        """
        Prepare and queue data for sending over the socket.
        """
        if self.connected:
            buffer = self._prepareTxData(data)
            self.tx_queue.put_nowait(buffer)
            return True
        else:
            return False

    # === PRIVATE METHODS ==============================================================================================
    def _connect(self, server_address, server_port):
        """
        Connect to the server.
        """
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            logger.info(f"Connect to server {self.server_address}:{server_port} ...")
            self._socket.connect((server_address, server_port))
            logger.info(f"Success! Connected to server {server_address}:{server_port}!")
            self._socket.setblocking(False)
            self._output_connections.append(self._socket)
            self._input_connections.append(self._socket)
            self.connected = True

            for callback in self.callbacks.connected:
                callback(self, server_address)

            self.events['connected'].set()

            return True
        except Exception as e:
            self.connected = False
            print("CANNOT CONNECT")
            return False

    # ------------------------------------------------------------------------------------------------------------------
    def _threadFunction(self):
        """
        Main thread function to manage the socket connection.
        """
        while not self._exit:
            self._updateFunction()
            time.sleep(0.0001)  # TODO: Magic Number

        if self._socket is not None:
            self._socket.close()
        logger.info("Close TCP Socket")

    # ------------------------------------------------------------------------------------------------------------------
    def _updateFunction(self):
        """
        Handle socket events such as receiving data, sending data, and checking for disconnection.
        """
        if self.connected:
            readable, writable, exceptional = select.select(self._input_connections, self._output_connections,
                                                            self._input_connections, 0)

            # Check if the connection was closed:
            if time_ms() > (self._close_check_time + self._close_check_interval_ms):
                closed = self._remote_connection_closed()
                self._close_check_time = time_ms()

                if closed:
                    logger.warning(f"Socket: Lost connection to server on {self.server_address}")
                    self.connected = False
                    self.events['connected'].clear()
                    for callback in self.callbacks.disconnected:
                        callback(self)
                    return

            # rx data
            for connection in readable:
                try:
                    data = connection.recv(MAX_SOCKET_READ)
                    if len(data) > 0:
                        self._rxFunction(data)
                except (ConnectionResetError, ConnectionAbortedError, InterruptedError):
                    logger.warning(f"Lost connection with TCP server {self.server_address}")
                    if connection in self._output_connections:
                        self._output_connections.remove(connection)
                    if connection in self._input_connections:
                        self._input_connections.remove(connection)
                    connection.close()
                    self.connected = False
                    self._socket.close()
                    self.events['connected'].clear()
                    for callback in self.callbacks.disconnected:
                        callback(self)
                    return

            if writable:
                self._sendTxData()

            for connection in exceptional:
                logger.error(f"Server exception with {connection.getpeername()}")
                if connection in self._input_connections:
                    self._input_connections.remove(connection)
                if connection in self._output_connections:
                    self._output_connections.remove(connection)
                connection.close()
                self._socket.close()
                for callback in self.callbacks.error:
                    callback(self)

    # ------------------------------------------------------------------------------------------------------------------
    def _prepareTxData(self, data: (str, list)):
        """
        Prepare data for transmission.
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        elif isinstance(data, list):
            data = bytes(data)

        assert (isinstance(data, (bytes, bytearray)))

        if self.config['cobs']:
            data = cobs.encode(data)

        if self.config['delimiter'] is not None:
            data = data + self.config['delimiter']

        return data

    # ------------------------------------------------------------------------------------------------------------------
    def _sendTxData(self):
        """
        Send queued data over the socket.
        """
        try:
            data = self.tx_queue.get_nowait()
        except queue.Empty:
            return

        try:
            self._socket.send(data)
        except (ConnectionResetError, BrokenPipeError):
            logger.warning(f"Broken pipe with server {self.server_address}. Closing the TCP Socket.")
            self.close()

    # ------------------------------------------------------------------------------------------------------------------
    def _rxFunction(self, data: bytes):
        """
        Process received data. Accumulate data in a buffer and extract complete packets.
        Partial packets are stored until the delimiter is encountered.
        """
        # Append new data to the persistent receive buffer.
        self._rx_buffer += data
        delimiter = self.config["delimiter"]

        while True:
            index = self._rx_buffer.find(delimiter)
            if index == -1:
                # No complete packet found yet.
                break

            # Extract one complete packet.
            packet = self._rx_buffer[:index]
            # Remove the processed packet and delimiter from the buffer.
            self._rx_buffer = self._rx_buffer[index + len(delimiter):]

            # If COBS encoding is enabled, decode the packet.
            if self.config["cobs"]:
                try:
                    packet = cobs.decode(packet)
                except Exception:
                    # Skip the packet if decoding fails.
                    continue

            # Process the individual packet.
            if self.config['rx_queue']:
                self.rx_queue.put_nowait(packet)
            for callback in self.callbacks.rx:
                callback(packet)
            self.events['rx'].set()

    # ------------------------------------------------------------------------------------------------------------------
    def _remote_connection_closed(self) -> bool:
        """
        Returns True if the remote side closed the connection.
        """
        try:
            buf = self._socket.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
            if buf == b'':
                return True
        except BlockingIOError as exc:
            if exc.errno != errno.EAGAIN:
                pass
        except:
            pass
        return False
