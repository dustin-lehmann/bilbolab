"""
Robust WebSocket Server using aiohttp

A more stable alternative to websocket-server, especially for mobile clients.
Uses aiohttp which handles connection edge cases better.
"""

import asyncio
import json
import threading
import time
from typing import Optional, Callable
from dataclasses import dataclass

from aiohttp import web, WSMsgType
from core.utils.logging_utils import Logger
from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback


@dataclass
class AioHttpWebsocketClient:
    """Represents a connected WebSocket client."""
    ws: web.WebSocketResponse
    address: str
    port: int
    connected: bool = True
    _server: 'AioHttpWebsocketServer' = None

    def send(self, message: dict):
        """Send a message to this client."""
        if self._server and self.connected:
            self._server.send_to_client(self, message)

    def __hash__(self):
        return hash((self.address, self.port))


@callback_definition
class AioHttpWebsocketServer_Callbacks:
    new_client: CallbackContainer
    client_disconnected: CallbackContainer
    message: CallbackContainer


@event_definition
class AioHttpWebsocketServer_Events:
    new_client: Event = Event(copy_data_on_set=False)
    client_disconnected: Event = Event(copy_data_on_set=False)
    message: Event


class AioHttpWebsocketServer:
    """
    WebSocket server using aiohttp for better stability with mobile clients.

    Drop-in replacement for WebsocketServer with similar API.
    """

    def __init__(self, host: str, port: int, heartbeats: bool = False):
        self.host = host
        self.port = port
        self.heartbeats = heartbeats  # Not implemented yet, kept for API compatibility

        self.logger = Logger('AioHttpWS', 'INFO')
        self.callbacks = AioHttpWebsocketServer_Callbacks()
        self.events = AioHttpWebsocketServer_Events()

        self.clients: list[AioHttpWebsocketClient] = []
        self._client_websockets: dict[AioHttpWebsocketClient, web.WebSocketResponse] = {}

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._runner: Optional[web.AppRunner] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._app: Optional[web.Application] = None
        self.running = False

        # Queue for sending messages from other threads
        self._send_queue: asyncio.Queue = None

        register_exit_callback(self.stop)

    def start(self):
        """Start the WebSocket server in a background thread."""
        if self.running:
            self.logger.warning("Server already running")
            return

        def run_server():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._send_queue = asyncio.Queue()
            try:
                self._loop.run_until_complete(self._run())
            except Exception as e:
                self.logger.error(f"Server error: {e}")
            finally:
                # Properly shutdown the event loop
                try:
                    # Cancel all pending tasks
                    pending = asyncio.all_tasks(self._loop)
                    for task in pending:
                        task.cancel()
                    # Wait for tasks to be cancelled
                    if pending:
                        self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    # Shutdown async generators
                    self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                except Exception:
                    pass
                finally:
                    self._loop.close()
                    self._loop = None

        self._thread = threading.Thread(target=run_server, daemon=True)
        self._thread.start()

        # Wait for server to start
        time.sleep(0.3)

        if self._thread.is_alive():
            self.running = True
            self.logger.info(f"WebSocket server started on {self.host}:{self.port}")

    async def _run(self):
        """Internal async run method."""
        self._app = web.Application()
        self._app['websockets'] = set()
        self._app['server'] = self

        # WebSocket endpoint
        self._app.router.add_get('/ws', self._websocket_handler)
        self._app.router.add_get('/', self._websocket_handler)  # Also handle root path

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host=self.host, port=self.port)
        await site.start()

        self._stop_event = asyncio.Event()

        # Start message sender task
        sender_task = asyncio.create_task(self._message_sender())

        await self._stop_event.wait()

        # Cleanup
        sender_task.cancel()
        try:
            await sender_task
        except asyncio.CancelledError:
            pass

        # Close all WebSocket connections
        for ws in list(self._app.get('websockets', set())):
            try:
                await ws.close()
            except:
                pass

        await self._runner.cleanup()

    async def _websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse(
            autoping=True,
            heartbeat=30.0,  # Built-in ping/pong every 30 seconds
        )
        await ws.prepare(request)

        # Get client info
        peername = request.transport.get_extra_info('peername')
        if peername:
            client_address, client_port = peername
        else:
            client_address = 'unknown'
            client_port = 0

        # Create client object
        client = AioHttpWebsocketClient(
            ws=ws,
            address=client_address,
            port=client_port,
            connected=True,
            _server=self
        )

        self._app['websockets'].add(ws)
        self.clients.append(client)
        self._client_websockets[client] = ws

        self.logger.info(f"New client connected: {client_address}:{client_port}")

        # Fire callbacks (in separate thread to not block the event loop)
        self._loop.call_soon(lambda: self._fire_new_client_callback(client))

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        # Fire message callback
                        self._loop.call_soon(lambda d=data, c=client: self._fire_message_callback(c, d))
                    except json.JSONDecodeError as e:
                        self.logger.warning(f"Invalid JSON from {client_address}:{client_port}: {e}")
                elif msg.type == WSMsgType.ERROR:
                    self.logger.warning(f"WebSocket error from {client_address}:{client_port}: {ws.exception()}")
                    break
        except Exception as e:
            self.logger.error(f"Error handling client {client_address}:{client_port}: {e}")
        finally:
            # Client disconnected
            client.connected = False
            self._app['websockets'].discard(ws)
            if client in self.clients:
                self.clients.remove(client)
            if client in self._client_websockets:
                del self._client_websockets[client]

            self.logger.info(f"Client disconnected: {client_address}:{client_port}")
            self._fire_client_disconnected_callback(client)

        return ws

    async def _message_sender(self):
        """Background task to send messages from the queue."""
        while True:
            try:
                client, message = await self._send_queue.get()
                if client in self._client_websockets:
                    ws = self._client_websockets[client]
                    if not ws.closed:
                        try:
                            await ws.send_str(json.dumps(message))
                        except Exception as e:
                            self.logger.warning(f"Failed to send to {client.address}:{client.port}: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Message sender error: {e}")

    def _fire_new_client_callback(self, client: AioHttpWebsocketClient):
        """Fire new client callbacks (runs in asyncio thread)."""
        try:
            self.callbacks.new_client.call(client)
            self.events.new_client.set(client)
        except Exception as e:
            self.logger.error(f"Error in new_client callback: {e}")

    def _fire_message_callback(self, client: AioHttpWebsocketClient, message: dict):
        """Fire message callbacks (runs in asyncio thread)."""
        try:
            self.callbacks.message.call(client, message)  # client first, then message
            self.events.message.set(data=message)
        except Exception as e:
            self.logger.error(f"Error in message callback: {e}")

    def _fire_client_disconnected_callback(self, client: AioHttpWebsocketClient):
        """Fire client disconnected callbacks."""
        try:
            self.callbacks.client_disconnected.call(client)
            self.events.client_disconnected.set(client)
        except Exception as e:
            self.logger.error(f"Error in client_disconnected callback: {e}")

    def send_to_client(self, client: AioHttpWebsocketClient, message: dict):
        """Send a message to a specific client (thread-safe)."""
        if self._loop and self._send_queue:
            self._loop.call_soon_threadsafe(
                lambda: self._send_queue.put_nowait((client, message))
            )

    def sendToClient(self, client, message: dict):
        """Compatibility alias for send_to_client."""
        if isinstance(client, AioHttpWebsocketClient):
            self.send_to_client(client, message)
        else:
            # Try to find the AioHttpWebsocketClient for this raw client
            for c in self.clients:
                if c == client or getattr(c, 'client', None) == client:
                    self.send_to_client(c, message)
                    return
            self.logger.warning(f"Client not found for sendToClient: {client}")

    def broadcast(self, message: dict):
        """Send a message to all connected clients."""
        for client in list(self.clients):
            self.send_to_client(client, message)

    def stop(self, *args, **kwargs):
        """Stop the WebSocket server."""
        if not self.running:
            return

        self.running = False

        if self._loop and self._stop_event:
            try:
                self._loop.call_soon_threadsafe(self._stop_event.set)
            except RuntimeError:
                # Loop might already be closed
                pass

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        self.logger.info("WebSocket server stopped")

    def switchLoggingLevel(self, level1: str, level2: str):
        """Compatibility method - does nothing for now."""
        pass
