# from __future__ import annotations

import dataclasses
import queue
import time
import logging
from websocket_server import WebsocketServer as ws_server
from websocket_server.websocket_server import WebSocketHandler as _WebSocketHandler
import websocket
import threading
import json

# === CUSTOM PACKAGES ==================================================================================================
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.json_utils import jsonEncode
from core.utils.logging_utils import Logger


# Monkey-patch: the upstream WebSocketHandler.handshake() catches AssertionError
# but not KeyError, so a plain HTTP request without an 'upgrade' header crashes
# the handler thread.  Wrap it so that any exception during handshake simply
# closes the connection instead of printing a noisy traceback.
_original_handshake = _WebSocketHandler.handshake

def _safe_handshake(self):
    try:
        _original_handshake(self)
    except (KeyError, Exception):
        self.keep_alive = False

_WebSocketHandler.handshake = _safe_handshake


# ======================================================================================================================
@callback_definition
class WebsocketServerClient_Callbacks:
    disconnected: CallbackContainer
    message: CallbackContainer


@event_definition
class WebsocketServerClient_Events:
    disconnected: Event
    message: Event


class WebsocketServerClient:
    client: dict
    callbacks: WebsocketServerClient_Callbacks
    server: 'WebsocketServer'
    connected: bool

    rx_queue: queue.Queue
    # Heartbeat tracking (server-side)
    last_pong_ts: float

    # === INIT =========================================================================================================
    def __init__(self, client, server):
        self.client = client
        self.callbacks = WebsocketServerClient_Callbacks()
        self.events = WebsocketServerClient_Events()
        self.server = server
        self.connected = True
        self.rx_queue = queue.Queue()
        # initialize to "now" so a brand-new client isn't reaped before first pong
        self.last_pong_ts = time.time()

    # === PROPERTIES ===================================================================================================
    @property
    def address(self):
        return self.client['address'][0]

    @property
    def port(self):
        return self.client['address'][1]

    # === METHODS ======================================================================================================
    def onMessage(self, message):
        # NOTE: app-level messages only (no heartbeats)
        self.rx_queue.put_nowait(message)
        self.callbacks.message.call(message, self)
        self.events.message.set(data=message)

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message):
        self.server.sendToClient(self.client, message)

    # ------------------------------------------------------------------------------------------------------------------
    def onDisconnect(self):
        self.connected = False
        self.callbacks.disconnected.call()

    # ------------------------------------------------------------------------------------------------------------------
    def mark_pong(self):
        self.last_pong_ts = time.time()


# ======================================================================================================================
@callback_definition
class SyncWebsocketServer_Callbacks:
    new_client: CallbackContainer
    client_disconnected: CallbackContainer
    message: CallbackContainer


@event_definition
class SyncWebsocketServer_Events:
    new_client: Event = Event(copy_data_on_set=False)
    message: Event
    client_disconnected: Event = Event(copy_data_on_set=False)


class WebsocketServer:
    callbacks: SyncWebsocketServer_Callbacks
    events: SyncWebsocketServer_Events

    clients: list[WebsocketServerClient]

    _server: ws_server | None

    def __init__(self, host, port, heartbeats: bool = True):
        self.host = host
        self.port = port
        self._server = None
        self.clients = []  # Store the connected clients
        self.running = False
        self.thread = None

        self.heartbeats = heartbeats

        self.logger = Logger('Websocket Server', 'INFO')

        self.events = SyncWebsocketServer_Events()
        self.callbacks = SyncWebsocketServer_Callbacks()

        # Heartbeat configuration (server => client)
        self.heartbeat_interval = 5  # seconds between pings
        self.heartbeat_timeout = 30  # max age of last_pong_ts before we assume dead
        self._hb_stop = threading.Event()
        self._hb_thread: threading.Thread | None = None

        # Exit handling
        register_exit_callback(self.stop)

    # === METHODS ======================================================================================================
    def start(self):
        """
        Start the WebSocket server in a separate thread (non-blocking).
        """
        if not self.running:
            self._server = ws_server(host=self.host, port=self.port)
            self.running = True
            self.thread = threading.Thread(target=self._run_server, daemon=True)
            self.thread.start()

            if self.heartbeats:
                # start heartbeat loop
                self._hb_stop.clear()
                self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
                self._hb_thread.start()

    # === PRIVATE METHODS ==============================================================================================
    def _run_server(self):
        """
        Run the WebSocket server (blocking call). Should be run in a separate thread.
        """
        # Attach callbacks
        self._server.set_fn_new_client(self._on_new_client)
        self._server.set_fn_client_left(self._on_client_left)
        self._server.set_fn_message_received(self._on_message_received)

        try:
            self._server.run_forever()
        except Exception as e:
            print(f"Error in server loop: {e}")
        finally:
            self.running = False

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_client(self, client, server):
        websocket_client = WebsocketServerClient(client, self)
        self.clients.append(websocket_client)  # Add a client to the list
        self.logger.info(f"New client connected: {client['address']}")
        self.callbacks.new_client.call(websocket_client)
        self.events.new_client.set(websocket_client)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_client_left(self, client, server):
        websocket_client = next((c for c in self.clients if c.client == client), None)

        if websocket_client:
            self.logger.info(f"Client disconnected: {client['address']}")
            try:
                self.clients.remove(websocket_client)
            except ValueError:
                ...  # Client already removed
            self.callbacks.client_disconnected.call(websocket_client)
            self.events.client_disconnected.set(websocket_client)
            websocket_client.onDisconnect()

    # Helper to forcefully drop a client (e.g., heartbeat timeout) and emit normal signals
    def _force_client_disconnect(self, websocket_client: WebsocketServerClient, reason: str = "heartbeat timeout"):
        self.logger.warning(f"Forcing disconnect for {websocket_client.client['address']} ({reason})")
        try:
            addr = websocket_client.client.get('address')
        except Exception:
            addr = None

        self.logger.info(f"Forcing disconnect for {addr} ({reason})")
        try:
            self.clients.remove(websocket_client)
        except ValueError:
            pass

        # Best effort: ask underlying server to close this socket if available
        try:
            self._server.client_left(websocket_client.client)
        except Exception:
            # Fall back to just firing callbacks
            pass

        self.callbacks.client_disconnected.call(websocket_client)
        self.events.client_disconnected.set(websocket_client)
        websocket_client.onDisconnect()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_message_received(self, client, server, message):
        # Parse JSON first
        try:
            data = json.loads(message)
        except Exception as e:
            self.logger.warning(f"Non-JSON message from {client['address']}, dropping: {e}")
            return

        websocket_client = next((c for c in self.clients if c.client == client), None)
        if not websocket_client:
            return

        # Handle internal heartbeat quietly (do NOT expose to callbacks/events)
        if isinstance(data, dict) and data.get("__hb__") == "pong":
            websocket_client.mark_pong()
            return

        # Normal application message flow
        self.logger.debug(f"Message received from {client['address']}: {data}")

        self.callbacks.message.call(websocket_client, data)
        self.events.message.set(data=data)
        websocket_client.onMessage(data)

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message):
        """
        Send a message to all connected clients.
        """
        if isinstance(message, dict):
            message = json.dumps(message)
        for client in list(self.clients):
            try:
                self._server.send_message(client.client, message)
            except Exception:
                # If send fails, reap the client
                self._force_client_disconnect(client, reason="send error")

    # ------------------------------------------------------------------------------------------------------------------
    def sendToClient(self, client, message):
        """
        Send a message to a specific client.
        """
        if isinstance(message, dict):
            message = jsonEncode(message)
            # message = json.dumps(message)

        if isinstance(client, WebsocketServerClient):
            if client in self.clients:
                try:
                    self._server.send_message(client.client, message)
                except Exception:
                    self._force_client_disconnect(client, reason="send error")
        elif isinstance(client, dict):
            try:
                self._server.send_message(client, message)
            except Exception:
                ws_client = next((c for c in self.clients if c.client == client), None)
                if ws_client:
                    self._force_client_disconnect(ws_client, reason="send error")

    # ------------------------------------------------------------------------------------------------------------------
    def _heartbeat_loop(self):
        """
        Periodically send an app-level ping and reap clients that don't reply with a pong in time.
        """
        while not self._hb_stop.is_set():
            now = time.time()
            # snapshot to avoid mutation during iteration
            for c in list(self.clients):
                # If the last pong is too old, disconnect
                if now - c.last_pong_ts > self.heartbeat_timeout:
                    self.logger.warning(f"Heartbeat timeout for {c.client['address']}")
                    self._force_client_disconnect(c, reason="heartbeat timeout")
                    continue

                # Send ping (internal control message)
                ping_msg = {"__hb__": "ping", "t": now}
                try:
                    self.logger.debug(f"Sending ping to {c.client['address']}")
                    self._server.send_message(c.client, json.dumps(ping_msg))
                except Exception as e:
                    self.logger.warning(f"Ping send failed: {e}")
                    self._force_client_disconnect(c, reason="ping send error")
                    continue

            # sleep until next cycle (wakes early if stop set)
            self._hb_stop.wait(self.heartbeat_interval)

    def stop(self, *args, **kwargs):
        """
        Stop the WebSocket server.
        """
        # stop heartbeat thread first so it doesn't race shutdown
        if self.heartbeats:
            self._hb_stop.set()
            if self._hb_thread and self._hb_thread.is_alive():
                self._hb_thread.join(timeout=2.0)

        if self.running:
            try:
                self._server.server_close()
            except Exception:
                pass
            try:
                self._server.disconnect_clients_gracefully()
            except Exception:
                pass
            try:
                self._server.shutdown()
            except Exception:
                pass
            if self.thread:
                self.thread.join()
            self.running = False

        self.logger.info("Server stopped")


# ======================================================================================================================
@callback_definition
class SyncWebsocketClient_Callbacks:
    message: CallbackContainer
    connected: CallbackContainer
    disconnected: CallbackContainer
    error: CallbackContainer


@event_definition
class SyncWebsocketClient_Events:
    message: Event
    connected: Event
    disconnected: Event
    error: Event


class WebsocketClient:
    callbacks: SyncWebsocketClient_Callbacks
    events: SyncWebsocketClient_Events

    _thread: threading.Thread
    _exit: bool = False
    _debug: bool

    _port = 0
    _address = ''

    # === INIT =========================================================================================================
    def __init__(self, address=None, port=None, debug=True, reconnect=True):

        self.address = address
        self.port = port

        self.uri = f"ws://{address}:{port}"
        self.ws = None
        self.connected = False

        self.reconnect = reconnect
        self._debug = debug

        self.callbacks = SyncWebsocketClient_Callbacks()
        self.events = SyncWebsocketClient_Events()

        self._thread = threading.Thread(target=self.task, daemon=True)
        self.ws_thread = None

        # Disable the internal websocket logger, since it messes with other modules
        self.logger = Logger('Websocket Client', 'INFO')
        logging.getLogger("websocket").setLevel(logging.CRITICAL)
        register_exit_callback(self.close)

    # === PROPERTIES ===================================================================================================
    @property
    def address(self):
        return self._address

    @address.setter
    def address(self, value):
        self._address = value
        self.uri = f"ws://{value}:{self.port}"

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, value):
        self._port = value
        self.uri = f"ws://{self.address}:{value}"

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.logger.info("Connection closed")
        self._exit = True
        try:
            self.ws.close()
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------------------------------------------------------
    def task(self):
        while not self._exit:
            if not self.connected:
                self.logger.debug("Attempting to connect...")
                self._connect()
            time.sleep(1)

    # ------------------------------------------------------------------------------------------------------------------
    def connect(self):
        self._thread = threading.Thread(target=self.task, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def _connect(self):
        """
        Attempt to connect to the WebSocket server with retry logic.
        """

        try:
            # Create WebSocket app
            self.ws = websocket.WebSocketApp(
                self.uri,
                on_open=self.on_open,
                on_close=self.on_close,
                on_message=self.on_message,
                on_error=self.on_error
            )

            # Run in a separate thread
            self.ws_thread = threading.Thread(
                target=lambda: self.ws.run_forever(
                    ping_interval=5,  # client -> server control frames (optional; server also pings via app messages)
                    ping_timeout=2,
                    reconnect=False
                ),
                daemon=True
            )
            self.ws_thread.start()

            # Wait for connection success or failure
            timeout = 5  # Adjust timeout as needed
            start_time = time.time()

            while not self.connected and not self._exit and time.time() - start_time < timeout:
                time.sleep(0.5)

            if self.connected:
                return True
            else:
                try:
                    self.ws.close()
                except Exception:
                    pass
                if self.ws_thread:
                    self.ws_thread.join()
                return False

        except Exception as e:
            if self._debug:
                self.logger.warning(f"Error in connection attempt: {e}")
            return False

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message):
        """
        Send a message to the server.
        """
        if self.connected:
            if isinstance(message, dict):
                message = json.dumps(message)
            try:
                self.ws.send(message)
            except Exception as e:
                self.logger.warning(f"Send failed: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def disconnect(self):
        """
        Close the WebSocket connection.
        """
        if self.connected:
            try:
                self.ws.close()
            except Exception:
                pass
            if self._thread and self._thread.is_alive():
                self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def on_open(self, ws):
        self.connected = True
        self.logger.info("Connection successful.")
        self.callbacks.connected.call()
        self.events.connected.set()

    # ------------------------------------------------------------------------------------------------------------------
    def on_close(self, ws, close_status_code, close_msg):
        if self.connected:
            self.connected = False
            self.callbacks.disconnected.call()
            self.events.disconnected.set()
            self.logger.info("Connection closed by server")

    # ------------------------------------------------------------------------------------------------------------------
    def on_message(self, ws, message):
        self.logger.debug(f"Message received: {message}")
        # swallow internal heartbeats (no callbacks/events)
        try:
            data = json.loads(message)
        except Exception:
            # non-JSON -> treat as app data
            self.callbacks.message.call(message)
            self.events.message.set(message)
            return

        if isinstance(data, dict) and data.get("__hb__") == "ping":
            # respond silently
            try:
                ws.send(json.dumps({"__hb__": "pong", "t": data.get("t", time.time())}))
            except Exception:
                pass
            return

        # normal messages
        self.callbacks.message.call(data)
        self.events.message.set(data)

    # ------------------------------------------------------------------------------------------------------------------
    def on_error(self, ws, error):
        self.callbacks.error.call(error)
        self.events.error.set(error)


# ======================================================================================================================
@dataclasses.dataclass
class WebsocketMessage:
    address: str
    source: str

    id: str
    type: str
    data: dict

    request: bool = False


if __name__ == '__main__':
    host = 'localhost'
    port = 8080
    # Start the server
    server = WebsocketServer('localhost', 8080)
    server.start()

    # Start the client
    client = WebsocketClient(host, port)
    client.connect()

    time.sleep(5)

    server.stop()
    time.sleep(6)
    server.start()

    while True:
        client.send({'test': 'test'})
        time.sleep(1)
        server.send({'a': 2})
        time.sleep(1)
