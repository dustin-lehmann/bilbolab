from __future__ import annotations

import copy
import threading
import time

from core.utils.dict_utils import update_dict
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.network.network import getHostIP
from core.utils.websockets import WebsocketServer
from extensions.gui.src.lib.map.map_objects import MapObjectGroup, MapObject
from extensions.gui.src.lib.objects.objects import Widget
from extensions.gui.src.lib.utilities import split_path

# ======================================================================================================================
MAP_DEFAULT_WS_PORT = 8700
UPDATE_FREQUENCY = 20

# ======================================================================================================================
MAP_DEFAULT_CONFIG = {
    # Geometry
    "limits": {"x": [0, 3], "y": [0, 3]},
    "origin": [0, 0],
    "rotation": 0,  # in degrees

    # Coordinate System
    "coordinate_system_size": 0.5,  # in m
    "coordinate_system_alpha": 0.9,
    "coordinate_system_width": 3,  # px

    # General Styling
    "map_border_width": 1,  # px
    "map_border_color": [1, 1, 1, 1],
    "map_border_radius": 0.1,  # in world units
    "map_color": [1, 1, 1, 0],
    "background_color": [0, 0, 0, 0],

    # Grid
    "show_grid": False,
    "show_grid_coordinates": True,
    "adaptive_grid": False,
    "major_grid_size": 1,
    "minor_grid_size": 0.5,
    "major_grid_width": 1,  # px
    "major_grid_style": "solid",
    "major_grid_color": [0.5, 0.5, 0.5, 0.4],
    "minor_grid_width": 1,  # px
    "minor_grid_style": "dotted",
    "minor_grid_color": [0.5, 0.5, 0.5, 0.4],

    # Tiling
    "tiles": True,
    "tile_size": 0.5,
    "tile_colors": [
        [0.3, 0.3, 0.3, 1],
        [28 / 255, 27 / 255, 43 / 255, 0.6]
    ],
    "tile_border_width": 1,  # px
    "tile_border_color": [0, 0, 0, 1],
    "show_tile_coordinates": True,

    # Ticks / labels
    "ticks_color": [1, 1, 1, 1],  # label color (RGBA 0..1)
    "ticks_bar_color": [0, 0, 0, 0.4],  # bar background under ticks (RGBA 0..1)
    "ticks_bar_size_px": 22,  # thickness of left / bottom bars
    "ticks_padding_px": 4,  # inner padding for text
    "min_label_px": 20,  # minimal spacing between labels (px)

    # Behaviour
    "allow_zoom": True,
    "allow_drag": True,
    "allow_rotate": False,  # user-rotate not implemented

    # Display
    "initial_display_center": [1.5, 1.5],
    "initial_display_zoom": 0.75,

    # Overlay
    "enable_overlay": True,
    "overlay_type": "side",  # Can be 'side', 'full', or 'external'

    # Rendering
    "fps": 30,
}


# ======================================================================================================================

@event_definition
class MapEvents:
    click: Event
    double_click: Event
    right_click: Event
    middle_click: Event


# ======================================================================================================================
class Map:
    groups: dict[str, MapObjectGroup]
    objects: dict[str, MapObject]

    config: dict

    server: WebsocketServer
    id: str

    _exit: bool = False

    # === INIT =========================================================================================================
    def __init__(self, id, server_host, server_port=MAP_DEFAULT_WS_PORT, **kwargs):
        self.id = id

        self.logger = Logger(f"Map {id}", 'DEBUG')
        self.config = update_dict(copy.deepcopy(MAP_DEFAULT_CONFIG), kwargs)
        self.events = MapEvents()
        self.groups = {}
        self.objects = {}

        self.update_data = {}
        self.update_config = {}

        self.server = WebsocketServer(server_host, server_port, heartbeats=False)
        self.server.callbacks.message.register(self._onMessage)
        self.server.callbacks.new_client.register(self._onNewClient)

        self._thread = threading.Thread(target=self._task, daemon=True)

        register_exit_callback(self.close)

    # === PROPERTIES ===================================================================================================
    @property
    def uid(self):
        return f"{self.id}"

    # === METHODS ======================================================================================================
    def start(self):
        self.logger.info(f'Starting Map {self.id} on {self.server.host}:{self.server.port}')
        self.server.start()
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.server.stop()
        self._exit = True
        if self._thread.is_alive():
            self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def getMap(self):
        return self

    # ------------------------------------------------------------------------------------------------------------------
    def addObject(self, object: MapObject) -> MapObject | None:

        if object.id in self.objects:
            self.logger.warning(f"Object with id '{object.id}' already exists in map '{self.id}'.")
            return None

        self.objects[object.id] = object
        object.parent = self

        message = {
            'type': 'add',
            'parent': self.uid,
            'payload': object.getPayload()
        }
        self.sendMessage(message)

        return object

    # ------------------------------------------------------------------------------------------------------------------
    def removeObject(self, object: MapObject):

        if object.parent is not self:
            self.logger.debug(
                f"Object with id '{object.id}' does not belong to map '{self.id}'. Redirecting to real parent")
            parent = object.parent
            if parent is None:
                self.logger.warning(f"Object with id '{object.id}' has no parent.")
                return
            parent.removeObject(object)
            return

        if object.id not in self.objects:
            self.logger.warning(f"Object with id '{object.id}' does not exist in map '{self.id}'.")
            return

        message = {
            'type': 'remove',
            'parent': self.uid,
            'id': object.uid
        }

        self.sendMessage(message)

        del self.objects[object.id]

    # ------------------------------------------------------------------------------------------------------------------
    def addGroup(self, group: MapObjectGroup) -> MapObjectGroup | None:
        if group.id in self.groups:
            self.logger.warning(f"Group with id '{group.id}' already exists in map '{self.id}'.")
            return None

        self.groups[group.id] = group
        group.parent = self

        message = {
            'type': 'add',
            'parent': self.uid,
            'payload': group.getPayload()
        }
        self.sendMessage(message)

        return group

    # ------------------------------------------------------------------------------------------------------------------
    def removeGroup(self, group: MapObjectGroup):

        if group.parent is not self:
            self.logger.debug(
                f"Group with id '{group.id}' does not belong to map '{self.id}'. Redirecting to real parent")
            parent = group.parent
            if parent is None:
                self.logger.warning(f"Group with id '{group.id}' has no parent.")
                return
            parent.removeGroup(group)
            return

        if group.id not in self.groups:
            self.logger.warning(f"Group with id '{group.id}' does not exist in map '{self.id}'.")
            return
        del self.groups[group.id]
        message = {
            'type': 'remove',
            'parent': self.uid,
            'id': group.uid
        }
        self.sendMessage(message)

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByUID(self, uid) -> Map | MapObject | MapObjectGroup | None:

        key, remainder = split_path(uid)

        if key != self.uid:
            self.logger.warning(f"Object with id '{uid}' not found in map '{self.id}'.")
            return None

        if not remainder:
            return self

        key, remainder = split_path(remainder)

        if key in self.groups:
            if not remainder:
                return self.groups[key]
            return self.groups[key].getObjectByPath(remainder)

        elif key in self.objects:
            return self.objects[key]

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, object: MapObject):
        self.update_data[object.uid] = object.getData()

    # ------------------------------------------------------------------------------------------------------------------
    def updateConfig(self, object: MapObject | MapObjectGroup):
        self.update_config[object.uid] = object.getConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self):
        for object in list(self.objects.values()):
            self.removeObject(object)
        for group in list(self.groups.values()):
            self.removeGroup(group)

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'id': self.id,
            'groups': {k: v.getPayload() for k, v in self.groups.items()},
            'objects': {k: v.getPayload() for k, v in self.objects.items()},
            'config': self.config,
            'websocket': {
                'host': self.server.host,
                'port': self.server.port,
            }
        }
        return payload

    # === PRIVATE METHODS ==============================================================================================
    def _task(self):
        while not self._exit:

            # Send the data update
            if len(self.update_data) > 0:
                self._sendDataUpdate()
                self.update_data = {}

            # Send the config update
            if len(self.update_config) > 0:
                self._sendConfigUpdate()
                self.update_config = {}

            time.sleep(1 / UPDATE_FREQUENCY)

    # ------------------------------------------------------------------------------------------------------------------
    def sendMessage(self, message: dict, client=None):
        if client is not None:
            self.server.sendToClient(client, message)
        else:
            self.server.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendDataUpdate(self):
        message = {
            'type': 'update',
            'data': self.update_data
        }

        self.sendMessage(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendConfigUpdate(self):
        message = {
            'type': 'update_config',
            'data': self.update_config
        }

        self.sendMessage(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _onMessage(self, client, message):
        self.logger.debug(f"Received message: {message}")
        match message['type']:
            case 'event':
                self._handle_event(message['data'])
            case _:
                self.logger.warning(f"Unknown message type. {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_event(self, event: dict):
        match event['type']:
            case 'click':
                self.events.click.set({
                    'x': event['x'],
                    'y': event['y']
                })
            case 'double_click':
                self.events.double_click.set({
                    'x': event['x'],
                    'y': event['y']
                })
            case 'right_click':
                self.events.right_click.set({
                    'x': event['x'],
                    'y': event['y']
                })
            case 'middle_click':
                self.events.middle_click.set({
                    'x': event['x'],
                    'y': event['y']
                })
            case _:
                self.logger.warning(f"Unknown event type. {event}")

    # ------------------------------------------------------------------------------------------------------------------
    def _onNewClient(self, client, *args, **kwargs):
        self._initializeClient(client)

    # ------------------------------------------------------------------------------------------------------------------
    def _initializeClient(self, client):
        message = {
            'type': 'init',
            'payload': self.getPayload()
        }
        self.sendMessage(message, client=client)


# === MAP WIDGET =======================================================================================================
class MapWidget(Widget):
    type = 'map'

    # === INIT =========================================================================================================
    def __init__(self, widget_id, **kwargs):
        super().__init__(widget_id, **kwargs)

        server_host = getHostIP()
        if server_host is None:
            server_host = 'localhost'

        # Auto-find a free port if the default (or specified) port is already in use
        port = kwargs.pop('server_port', MAP_DEFAULT_WS_PORT)
        self.map = Map(f"{self.id}_map", server_host, server_port=port, **kwargs)

        max_attempts = 20
        for attempt in range(max_attempts):
            try:
                self.map.start()
                break
            except OSError:
                port += 1
                self.map.server.port = port
        else:
            raise OSError(f"Could not find a free port for map widget '{self.id}' "
                          f"(tried {MAP_DEFAULT_WS_PORT}–{port - 1})")

    # === METHODS ======================================================================================================
    def getPayload(self) -> dict:
        payload = super().getPayload()
        payload['map'] = self.map.getPayload()
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        return {}

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> None:
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def onDelete(self):
        self.map.close()
