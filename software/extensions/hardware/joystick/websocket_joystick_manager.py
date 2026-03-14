from __future__ import annotations

import dataclasses
import time
from typing import Any, Dict, List, Optional, Union

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event, EventFlag, EventListener
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.network.network import getHostIP
from core.utils.websockets import WebsocketServer, WebsocketServerClient


# --- WEBSOCKET JOYSTICK MANAGER =======================================================================================
@callback_definition
class WebsocketJoystickManager_Callbacks:
    new_joystick: CallbackContainer
    removed_joystick: CallbackContainer


@event_definition
class WebsocketJoystickManager_Events:
    new_joystick: Event = Event(copy_data_on_set=False)
    removed_joystick: Event = Event(copy_data_on_set=False)


class WebsocketJoystickManager:
    host: str
    port: int

    websocket: WebsocketServer

    callbacks: WebsocketJoystickManager_Callbacks
    events: WebsocketJoystickManager_Events

    joysticks: Dict[str, WebsocketJoystick]
    _unregistered_clients: List[WebsocketServerClient]

    # === INIT =========================================================================================================
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = int(port)

        self.websocket = WebsocketServer(host=host, port=port, heartbeats=False)
        self.websocket.callbacks.new_client.register(self._newClient_callback)

        self.logger = Logger("WebsocketJoystickManager", "DEBUG")
        self.callbacks = WebsocketJoystickManager_Callbacks()
        self.events = WebsocketJoystickManager_Events()

        self.joysticks = {}
        self._unregistered_clients = []

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        """
        Prepare internal state. This exists for API symmetry; currently all state is
        initialised in __init__, so we only log here.
        """
        self.logger.debug("WebsocketJoystickManager initialised")

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.debug("Starting websocket joystick manager on %s:%s", self.host, self.port)
        self.websocket.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        try:
            self.websocket.stop()
        finally:
            self.logger.debug("Websocket joystick manager closed")

    # --- Helper / Introspection ---------------------------------------------------------------------------------------
    def _client_key(self, client: WebsocketServerClient) -> str:
        """
        Create a stable key for indexing joysticks.
        Prefers client.id if present; falls back to id(client).
        """
        cid = getattr(client, "id", None)
        if cid is None:
            return f"client:{id(client)}"
        return f"client:{cid}"

    def count(self) -> int:
        """Return number of active WebsocketJoystick instances."""
        return len(self.joysticks)

    def list(self) -> List[Dict[str, Any]]:
        """Return a snapshot of all active websocket joysticks."""
        out: List[Dict[str, Any]] = []
        for key, js in self.joysticks.items():
            info = js.information
            out.append(
                {
                    "key": key,
                    "client_connected": js.client.connected if hasattr(js.client, "connected") else True,
                    "joystick_index": info.index,
                    "joystick_id": info.id,
                    "mapping": info.mapping,
                    "axes": info.axes,
                    "buttons": info.buttons,
                    "identified": js.identified,
                    "last_axes": js._axes,
                }
            )
        return out

    def get(self, key: str) -> Optional["WebsocketJoystick"]:
        """Get a joystick wrapper by its manager key (see list())."""
        return self.joysticks.get(key)

    # === PRIVATE METHODS ==============================================================================================
    def _newClient_callback(self, client: WebsocketServerClient, *args, **kwargs):
        """
        Whenever a new client connects, we wait for its initial identification message.
        Until then, it lives in _unregistered_clients and all messages are routed to
        _client_message_callback to detect the 'identify' payload.
        """
        self.logger.debug("New client connected; awaiting identification…")
        self._unregistered_clients.append(client)
        client.callbacks.message.register(self._client_message_callback)

    # ------------------------------------------------------------------------------------------------------------------
    def _client_message_callback(self, message: Dict[str, Any], client: WebsocketServerClient):
        """
        Expect the first message from a new client to be:
            { type: 'identify',
              joystick: { index, id, mapping, axes, buttons, connected },
              ts }
        """
        if not isinstance(message, dict):
            return  # ignore garbage

        msg_type = message.get("type")
        if msg_type != "identify":
            # Not an identification message yet; continue waiting.
            return

        js_info = message.get("joystick") or {}
        try:
            information = WebsocketJoystickInformation(
                index=int(js_info.get("index", -1)),
                id=str(js_info.get("id") or ""),
                mapping=js_info.get("mapping"),
                axes=int(js_info.get("axes") or 0),
                buttons=int(js_info.get("buttons") or 0),
                connected=bool(js_info.get("connected", True)),
            )
        except Exception as e:
            self.logger.error("Invalid identification payload from client: %s (%s)", js_info, e)
            return

        # Create wrapper and wire up lifecycle
        new_websocket_joystick = WebsocketJoystick(client, information=information)

        key = self._client_key(client)
        self.joysticks[key] = new_websocket_joystick

        # Remove client from "unregistered" list and stop listening here
        try:
            self._unregistered_clients.remove(client)
        except ValueError:
            pass
        client.callbacks.message.remove(self._client_message_callback)

        # When that joystick disconnects, clean up the manager's table.
        new_websocket_joystick.callbacks.disconnected.register(self._joystick_disconnected_callback)

        # Emit the callback and Event
        self.logger.debug("Registered joystick %s (index=%s, id=%s)", key, information.index, information.id)
        self.callbacks.new_joystick.call(new_websocket_joystick)
        self.events.new_joystick.set(data=new_websocket_joystick)

    # ------------------------------------------------------------------------------------------------------------------
    def _joystick_disconnected_callback(self, joystick: "WebsocketJoystick", *args, **kwargs):
        """Remove a joystick from registry after it disconnected."""
        # Find key by value
        keys = [k for k, v in self.joysticks.items() if v is joystick]
        for k in keys:
            self.logger.debug("Removing joystick %s (client disconnected)", k)
            self.joysticks.pop(k, None)
            self.callbacks.removed_joystick.call(k)
            self.events.removed_joystick.set(data=k)


# === WEBSOCKET JOYSTICK ===============================================================================================
@dataclasses.dataclass
class WebsocketJoystickInformation:
    index: int
    id: str
    mapping: Optional[str]
    axes: int
    buttons: int
    connected: bool = True


@callback_definition
class WebsocketJoystick_Callbacks:
    disconnected: CallbackContainer
    button: CallbackContainer
    axes: CallbackContainer  # optional: for consumers who want axes stream


@event_definition
class WebsocketJoystick_Events:
    disconnected: Event
    button: Event = Event(flags=EventFlag("button", (int, str)))
    axes: Event  # data is the axes list


class WebsocketJoystick:
    client: WebsocketServerClient

    callbacks: WebsocketJoystick_Callbacks
    events: WebsocketJoystick_Events

    information: WebsocketJoystickInformation
    identified: bool

    # cached / live state
    _axes: List[float]
    _buttons_analog: List[float]

    # === INIT =========================================================================================================
    def __init__(self, client: WebsocketServerClient, information: WebsocketJoystickInformation = None):
        self.client = client
        self.information = information or WebsocketJoystickInformation(
            index=-1, id="", mapping=None, axes=0, buttons=0, connected=False
        )
        self.identified = information is not None

        self.callbacks = WebsocketJoystick_Callbacks()
        self.events = WebsocketJoystick_Events()

        self.logger = Logger("WebsocketJoystick", "DEBUG")

        self._axes = [0.0 for _ in range(self.information.axes or 0)]
        self._buttons_analog = [0.0 for _ in range(self.information.buttons or 0)]

        # Lifecycle wiring
        self.client.callbacks.disconnected.register(self._client_disconnected_callback)

        # Route all future messages here
        self.event_listener = EventListener(event=self.client.events.message, callback=self._message_callback)
        self.event_listener.start()

    # === METHODS ======================================================================================================
    def getAxes(self) -> List[float]:
        """
        Return the latest axes snapshot as sent by the client.
        """
        # Ensure length matches advertised count
        if self.information.axes and len(self._axes) != self.information.axes:
            # resize conservatively
            self._axes = (self._axes + [0.0] * self.information.axes)[: self.information.axes]
        return list(self._axes)

    # ------------------------------------------------------------------------------------------------------------------
    def getAxis(self, identifier: Union[str, int]) -> float:
        """
        Get one axis by numeric index. If a string is passed, we currently return 0.0
        because the client streams axes as an array without per-axis names.
        """
        if isinstance(identifier, int):
            if 0 <= identifier < len(self._axes):
                return float(self._axes[identifier])
            return 0.0
        # Could be extended to support known names based on mapping in the future.
        return 0.0

    # ------------------------------------------------------------------------------------------------------------------
    def getButtonsAnalog(self) -> List[float]:
        """
        Return the latest analog values for all buttons (e.g., triggers).
        """
        # Normalize size
        if self.information.buttons and len(self._buttons_analog) != self.information.buttons:
            self._buttons_analog = (self._buttons_analog + [0.0] * self.information.buttons)[
                : self.information.buttons
            ]
        return list(self._buttons_analog)

    # ------------------------------------------------------------------------------------------------------------------
    def isConnected(self) -> bool:
        """
        Whether the underlying websocket client is connected and the joystick is not marked as disconnected.
        """
        return bool(getattr(self.client, "connected", True) and self.information.connected)

    # === PRIVATE METHODS ==============================================================================================
    def _client_disconnected_callback(self, *args, **kwargs):
        """
        Fired when the websocket connection drops.
        """
        self.information.connected = False
        self.callbacks.disconnected.call(self)
        self.events.disconnected.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _message_callback(self, message: Dict[str, Any], *args, **kwargs):
        """
        Route messages coming from the websocket client.

        Expected message shapes (from the frontend implementation):

        - Identify:
            {
              "type": "identify",
              "joystick": {
                "index": <int>, "id": <str>, "mapping": <str|null>,
                "axes": <int>, "buttons": <int>, "connected": <bool>
              },
              "ts": <number>
            }

        - Axes stream (continuous):
            {
              "type": "axes",
              "index": <int>,
              "axes": <list[float]>,
              "buttonsAnalog": <list[float]>,
              "ts": <number>
            }

        - Button edge/change event (forwarded as-is):
            {
              "type": "button",
              "index": <int>,
              "name": <str|null>,
              "event": "down" | "up" | "change",
              "value": <float>,
              "pressed": <bool>,
              "ts": <number>
            }

        - Joystick disconnected notice:
            { "type": "joystick_disconnected", "index": <int>, "ts": <number> }
        """
        if not isinstance(message, dict):
            return

        mtype = message.get("type")

        if mtype == "identify":
            # Late/duplicate identify — update known info and mark identified.
            js = message.get("joystick") or {}
            self.information.index = int(js.get("index", self.information.index))
            self.information.id = str(js.get("id", self.information.id))
            self.information.mapping = js.get("mapping", self.information.mapping)
            self.information.axes = int(js.get("axes", self.information.axes or 0))
            self.information.buttons = int(js.get("buttons", self.information.buttons or 0))
            self.information.connected = bool(js.get("connected", True))
            # resize caches if needed
            if self.information.axes and len(self._axes) != self.information.axes:
                self._axes = [0.0 for _ in range(self.information.axes)]
            if self.information.buttons and len(self._buttons_analog) != self.information.buttons:
                self._buttons_analog = [0.0 for _ in range(self.information.buttons)]
            self.identified = True
            return

        if mtype == "axes":
            self._handleAxisMessage(message)
            return

        if mtype == "button":
            self._handleButtonMessage(message)
            return

        if mtype == "joystick_disconnected":
            # peer explicitly told us its joystick disappeared
            self.information.connected = False
            self.callbacks.disconnected.call(self)
            self.events.disconnected.set(data=self)
            return

        # Unknown message types are ignored but logged at debug.
        self.logger.debug("Ignoring unknown joystick message type: %s", mtype)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleAxisMessage(self, message: Dict[str, Any]):
        axes = message.get("axes") or []
        btns = message.get("buttonsAnalog") or []

        # Update caches (resize if needed)
        if axes:
            self._axes = list(map(float, axes))
            # Normalise to advertised axes count if we have one
            if self.information.axes:
                self._axes = (self._axes + [0.0] * self.information.axes)[: self.information.axes]

        if btns:
            self._buttons_analog = list(map(float, btns))
            if self.information.buttons:
                self._buttons_analog = (self._buttons_analog + [0.0] * self.information.buttons)[
                    : self.information.buttons
                ]

        # Fire axes event/callback for consumers
        self.callbacks.axes.call(self._axes)
        self.events.axes.set(data=self._axes)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleButtonMessage(self, message: Dict[str, Any]):
        # Forward minimal useful payload and raise an event with a resolvable identifier flag
        index = int(message.get("index", -1))
        name = message.get("name")  # may be null
        identifier: Union[int, str] = name if (name is not None and name != "") else index

        payload = {
            "index": index,
            "name": name,
            "event": message.get("event"),
            "value": float(message.get("value", 0.0)),
            "pressed": bool(message.get("pressed", False)),
            "ts": message.get("ts"),
        }

        # Callbacks for convenience
        self.callbacks.button.call(payload)

        # We have to emit button events like this:
        self.events.button.set(flags={"button": identifier}, data=payload)  # pass the button identifier

        self.logger.debug(f"Button event: {payload}")


if __name__ == '__main__':
    host = getHostIP()
    wsj = WebsocketJoystickManager(host=host, port=8765)
    wsj.init()
    wsj.start()



    while True:
        time.sleep(2)