from __future__ import annotations

import abc
import base64
import dataclasses
import math
import os
import threading
import uuid
from dataclasses import is_dataclass
from typing import Any

import numpy as np

# === CUSTOM MODULES ===================================================================================================
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import asdict_optimized
from core.utils.dict_utils import update_dict
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.time import IntervalTimer
from core.utils.websockets import WebsocketServer
from extensions.gui.src.lib.objects.objects import Widget
from extensions.gui.src.lib.utilities import split_path

babylon_path = os.path.join(os.path.dirname(__file__), "babylon_lib")


# === BABYLON OBJECT ===================================================================================================
@callback_definition
class BabylonObjectCallbacks:
    update: CallbackContainer


# ----------------------------------------------------------------------------------------------------------------------
class BabylonObject(abc.ABC):
    """
    Base class for Babylon visualization objects.
    """

    parent: BabylonObjectGroup | BabylonVisualization | None = None

    type: str = None
    id: str = None

    pollable: bool = True

    config: dict = None
    data: Any | None = None

    # === INIT =========================================================================================================
    def __init__(self, object_id: str, **kwargs):
        """
        Initialize a BabylonObject.
        """

        default_config = {
            'name': '',
            'visible': True,
            'dim': False,
            'highlight': False,
        }

        self.config = update_dict(default_config, kwargs, allow_add=False)
        if self.config['name'] == '':
            self.config['name'] = object_id

        self.id = object_id
        self.object_type = None  # To be defined in subclasses.
        self.data = None

        self.callbacks = BabylonObjectCallbacks()

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        if self.parent is None:
            return self.id
        else:
            return f"{self.parent.uid}/{self.id}"

    # === METHODS ======================================================================================================
    def getBabylon(self) -> BabylonVisualization | None:
        if isinstance(self.parent, BabylonVisualization):
            return self.parent
        elif isinstance(self.parent, BabylonObjectGroup):
            return self.parent.getBabylon()
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        babylon = self.getBabylon()
        if babylon is None:
            return

        if isinstance(babylon, BabylonVisualization):
            babylon.updateObject(
                object=self,
                data=self.getData()
            )

    # ------------------------------------------------------------------------------------------------------------------
    def updateConfig(self):

        babylon = self.getBabylon()

        if babylon is None:
            return

        if isinstance(babylon, BabylonVisualization):
            babylon.updateObjectConfig(
                object_id=self.uid,
                config=self.getConfig()
            )

    # ------------------------------------------------------------------------------------------------------------------
    def function(self, function_name, **kwargs):

        babylon = self.getBabylon()
        if babylon is None:
            return

        if isinstance(babylon, BabylonVisualization):
            babylon.objectFunction(
                object_id=self.uid,
                function_name=function_name,
                arguments=kwargs
            )

    # ------------------------------------------------------------------------------------------------------------------
    def set_visible(self, visible: bool):
        """Show or hide this object in the 3D scene."""
        self.function('setVisibility', visible=visible)

    # ------------------------------------------------------------------------------------------------------------------
    def setConfig(self, key, value):
        self.config[key] = value
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def getConfig(self) -> dict:
        """
        Serialize the object into a message dictionary for the web app.
        """
        ...

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def getData(self) -> dict:
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message, client=None):
        babylon = self.getBabylon()

        if babylon is not None:
            babylon.send(message, client)

    # ------------------------------------------------------------------------------------------------------------------
    def update_from_data(self, data: dict):
        """
        Update object parameters from a data dictionary.
        """
        self.data.update(data)
        self.callbacks.update.call(self)

    # ------------------------------------------------------------------------------------------------------------------
    def on_remove(self):
        """
        Cleanup actions when the object is removed.
        """
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self):
        payload = {
            'type': self.type,
            'id': self.uid,
            'config': self.getConfig(),
            'data': self.getData()
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def visible(self, visible: bool):
        self.setConfig('visible', visible)

    # ------------------------------------------------------------------------------------------------------------------
    def dim(self, dim: bool):
        self.setConfig('dim', dim)

    # ------------------------------------------------------------------------------------------------------------------
    def highlight(self, highlight: bool):
        self.setConfig('highlight', highlight)


# ======================================================================================================================
class BabylonObjectGroup:
    object_id: str
    objects: dict[str, BabylonObject | BabylonObjectGroup]

    parent: BabylonObjectGroup | BabylonVisualization | None = None

    config: dict

    # === INIT =========================================================================================================
    def __init__(self, object_id: str = None, **kwargs):

        if object_id is None:
            object_id = f"group_{str(uuid.uuid4())}"

        self.object_id = object_id

        default_config = {

        }

        self.config = update_dict(default_config, kwargs)
        self.data = {}
        self.objects = {}
        self.logger = Logger(f'Object Group {self.object_id}')

    # === PROPERTIES ===================================================================================================
    @property
    def uid(self):
        if self.parent is None:
            return self.object_id
        else:
            return f"{self.parent.uid}/{self.object_id}"

    # === METHODS ======================================================================================================
    def getBabylon(self) -> BabylonVisualization | None:
        if isinstance(self.parent, BabylonVisualization):
            return self.parent
        elif isinstance(self.parent, BabylonObjectGroup):
            return self.parent.getBabylon()
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def addObject(self, object: BabylonObject | BabylonObjectGroup) -> BabylonObject | BabylonObjectGroup | None:
        if object.parent is not None:
            self.logger.warning(f"Object {object.object_id} already has a parent.")
            return None

        if object.object_id in self.objects:
            self.logger.warning(f"Object {object.object_id} already exists in group {self.object_id}.")
            return None

        object.parent = self
        self.objects[object.object_id] = object

        message = {
            'type': 'addObject',
            'id': object.uid,
            'object_type': object.object_type,
            'payload': object.getPayload()
        }

        self.getBabylon().broadcast(message)

        return object

    # ------------------------------------------------------------------------------------------------------------------
    def removeObject(self, object: BabylonObject | BabylonObjectGroup | str) -> None:

        if isinstance(object, str):
            if object not in self.objects:
                self.logger.warning(f"Object {object} not found in group {self.object_id}.")
                return
            object = self.objects[object]

        if not isinstance(object, BabylonObject | BabylonObjectGroup):
            self.logger.warning(f"Object {object} is not a BabylonObject or BabylonObjectGroup.")
            return

        message = {
            'type': 'removeObject',
            'id': object.uid
        }

        self.objects.pop(object.object_id)
        object.parent = None
        object.on_remove()

        self.getBabylon().broadcast(message)

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByPath(self, path) -> BabylonObject | BabylonObjectGroup | None:

        # 1) normalize slashes
        trimmed = path.strip("/")

        # 2) Split the path
        object_id, remainder = split_path(trimmed)

        if not object_id or object_id not in self.objects:
            self.logger.warning(f"Object with id {object_id} not found in group {self.object_id}.")
            return None

        if not remainder:
            return self.objects[object_id]
        else:
            if isinstance(self.objects[object_id], BabylonObjectGroup):
                return self.objects[object_id].getObjectByPath(remainder)
            else:
                self.logger.warning(
                    f"Object with id {object_id} is not a BabylonObjectGroup but remainder is not empty")
                return None

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self) -> dict:
        config = {
            **self.config
        }

        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self) -> dict:
        data = {
            **self.data,
        }
        return data

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'id': self.uid,
            'type': 'group',
            'config': self.getConfig(),
            'objects': {k: v.getPayload() for k, v in self.objects.items()},
            'data': self.getData(),
        }

        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def visible(self, visible: bool):
        for obj in self.objects.values():
            obj.visible(visible)

    # ------------------------------------------------------------------------------------------------------------------
    def dim(self, dim: bool):
        for obj in self.objects.values():
            obj.dim(dim)

    # ------------------------------------------------------------------------------------------------------------------
    def highlight(self, highlight: bool):
        for obj in self.objects.values():
            obj.highlight(highlight)


# ======================================================================================================================
@dataclasses.dataclass
class BabylonCamera:
    name: str = 'Camera'
    target: list[float] = dataclasses.field(default_factory=lambda: [0, 0, 0])
    alpha: float = math.radians(-18)
    beta: float = math.radians(70)
    radius: float = 3.5
    fov: float = math.radians(65)
    radius_lower_limit: float = 0.5
    radius_upper_limit: float = 10.0

    def __post_init__(self):
        if self.radius > self.radius_upper_limit:
            import warnings
            warnings.warn(
                f"BabylonCamera '{self.name}': radius ({self.radius}) exceeds "
                f"radius_upper_limit ({self.radius_upper_limit})",
                stacklevel=2,
            )

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'target': list(self.target),
            'alpha': self.alpha,
            'beta': self.beta,
            'radius': self.radius,
            'fov': self.fov,
            'radius_lower_limit': self.radius_lower_limit,
            'radius_upper_limit': self.radius_upper_limit,
        }


# ======================================================================================================================
@dataclasses.dataclass
class BabylonScene:
    """Fog and atmosphere settings.

    When ``fog_auto_scale`` is True, the fog density is automatically scaled
    with the camera radius so that the apparent fog strength stays constant
    regardless of zoom level.  The ``fog_density`` value is then treated as
    the density at ``fog_reference_radius`` (defaults to the camera's initial
    radius).  Set ``fog_reference_radius`` explicitly to anchor the density to
    a specific viewing distance.
    """
    add_fog: bool = True
    fog_color: list[float] = dataclasses.field(default_factory=lambda: [31 / 255, 32 / 255, 35 / 255])
    fog_density: float = 0.08
    fog_mode: str = 'exp2'
    fog_auto_scale: bool = True
    fog_reference_radius: float = 0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ======================================================================================================================
@dataclasses.dataclass
class BabylonLights:
    """Scene lighting: one hemispheric + two directional lights."""
    hemispheric_direction: list[float] = dataclasses.field(default_factory=lambda: [2, -1, 0])
    hemispheric_intensity: float = 0.5
    hemispheric_ground_color: list[float] = dataclasses.field(default_factory=lambda: [0, 0, 0])
    directional_direction: list[float] = dataclasses.field(default_factory=lambda: [-1, -1, -1])
    directional_position: list[float] = dataclasses.field(default_factory=lambda: [1, 1, 10])
    directional_intensity: float = 1.1
    directional_shadows: bool = True
    directional_shadow_darkness: float = 0.4
    directional2_direction: list[float] = dataclasses.field(default_factory=lambda: [1, -1, -1])
    directional2_position: list[float] = dataclasses.field(default_factory=lambda: [1, -1, 10])
    directional2_intensity: float = 0.4
    directional2_shadows: bool = False
    directional2_shadow_darkness: float = 0.4

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ======================================================================================================================
@dataclasses.dataclass
class BabylonUI:
    """HUD / overlay text settings."""
    text_color: list[float] = dataclasses.field(default_factory=lambda: [1, 1, 1])
    font_size: int = 40

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ======================================================================================================================
@dataclasses.dataclass
class BabylonConfig:
    """Complete visualization config. Does NOT include runtime settings (title, host, port)."""
    camera: BabylonCamera = dataclasses.field(default_factory=BabylonCamera)
    scene: BabylonScene = dataclasses.field(default_factory=BabylonScene)
    lights: BabylonLights = dataclasses.field(default_factory=BabylonLights)
    ui: BabylonUI = dataclasses.field(default_factory=BabylonUI)

    background_color: list[float] = dataclasses.field(default_factory=lambda: [31 / 255, 32 / 255, 35 / 255])
    ambient_color: list[float] = dataclasses.field(default_factory=lambda: [0.5, 0.5, 0.5])
    show_coordinate_system: bool = True
    coordinate_system_length: float = 0.1

    def to_dict(self) -> dict:
        return {
            'camera': self.camera.to_dict(),
            'scene': self.scene.to_dict(),
            'lights': self.lights.to_dict(),
            'ui': self.ui.to_dict(),
            'background_color': list(self.background_color),
            'ambient_color': list(self.ambient_color),
            'show_coordinate_system': self.show_coordinate_system,
            'coordinate_system_length': self.coordinate_system_length,
        }


# ======================================================================================================================
@callback_definition
class BabylonCallbacks:
    new_client: CallbackContainer
    client_disconnected: CallbackContainer
    client_loaded: CallbackContainer
    object_event: CallbackContainer
    recording_started: CallbackContainer
    recording_stopped: CallbackContainer
    recording_saved: CallbackContainer
    object_click: CallbackContainer
    floor_doubleclick: CallbackContainer
    floor_middleclick: CallbackContainer
    floor_rightclick: CallbackContainer
    dropdown_select: CallbackContainer


# ======================================================================================================================
@dataclasses.dataclass
class Babylon_UpdateMessage:
    updates: dict[str, dict | list[dict]] = dataclasses.field(default_factory=dict)
    type: str = 'update'


# ======================================================================================================================
class BabylonVisualization:
    """
    Manages the BabylonJS visualization web application.
    """

    objects: dict[str, BabylonObject]

    config: dict
    server: WebsocketServer

    _clients: list
    _update_message: Babylon_UpdateMessage
    _update_message_lock = threading.Lock()

    _poll_objects: bool = True

    _exit: bool = False
    Ts: float = 0.05

    # === INIT =========================================================================================================
    def __init__(self,
                 id: str,
                 host='localhost',
                 port=9000,
                 config: BabylonConfig | None = None,
                 babylon_config: dict | None = None):

        # Build the internal config dict from typed config or defaults
        default = BabylonConfig() if config is None else config
        config_dict = default.to_dict()

        # Runtime keys (not part of BabylonConfig)
        config_dict['title'] = 'ABCDEF'
        config_dict['websocket_host'] = host
        config_dict['websocket_port'] = str(port)

        # Legacy dict override (for existing callers passing raw dicts)
        self.config = update_dict(config_dict, babylon_config or {})

        self.id = id

        self.callbacks = BabylonCallbacks()
        self.logger = Logger('BABYLON', 'INFO')

        self.server = WebsocketServer(host=host, port=port, heartbeats=False)
        self.server.callbacks.new_client.register(self._new_client_callback)
        self.server.callbacks.client_disconnected.register(self._client_disconnected_callback)
        self.server.callbacks.message.register(self._client_message_callback)

        self.objects = {}
        self._clients = []
        self._cameras = []

        self.update_message = Babylon_UpdateMessage()

        self.timer = IntervalTimer(self.Ts, raise_race_condition_error=False)

        register_exit_callback(self.close)

        self._thread = None

        # Dropdown state (persisted so new clients receive it)
        self._dropdown_items: list[dict] = []
        self._dropdown_selected: str | None = None

        # Recording state
        self._is_recording = False
        self._recording_save_path: str | None = None
        self._recording_chunks: list[bytes] = []
        self._recording_total_chunks: int = 0
        self._recording_complete_received: bool = False

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        """
        Initialize the web app visualization.
        (Any additional initialization code can be added here.)
        """
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        """
        Start the visualization in a separate thread.
        """
        self.logger.info("Starting Babylon visualization")

        self.server.start()

        self._thread = threading.Thread(target=self._task, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        # Tell browser to disable reconnect and close
        try:
            self.send({'type': 'command', 'command': 'close'})
        except Exception:
            pass

        import time
        time.sleep(0.5)

        self._exit = True

        if hasattr(self, '_thread') and self._thread is not None and self._thread.is_alive():
            self._thread.join()

        self.server.stop()
        self.logger.info(f"Babylon visualization stopped")

    # === RECORDING ====================================================================================================
    @property
    def is_recording(self) -> bool:
        return self._is_recording

    # ------------------------------------------------------------------------------------------------------------------
    def start_recording(self,
                        filename: str = "babylonjs.webm",
                        fps: int = 60,
                        bitrate: int = 12_000_000,
                        save_path: str | None = None,
                        overlay: bool = False,
                        upscale: float = 1.0):
        """Start recording the BabylonJS visualization.

        Args:
            filename: Output filename.
            fps: Recording frames per second.
            bitrate: Video bitrate in bits/second.
            save_path: If set, the recording will be saved to this server-side path
                       instead of triggering a browser download.
            overlay: If True, include HUD overlay in the recording.
            upscale: Resolution upscale factor.
        """
        if self._is_recording:
            self.logger.warning("Already recording.")
            return

        if save_path:
            self._recording_save_path = os.path.expanduser(save_path)
            self._recording_chunks = []
            self._recording_total_chunks = 0
            self._recording_complete_received = False

        message = {
            'type': 'command',
            'command': 'startRecording',
            'params': {
                'filename': filename,
                'fps': fps,
                'bitrate': bitrate,
                'save_path': save_path,
                'overlay': overlay,
                'upscale': upscale,
            }
        }
        self.send(message)
        self.logger.info(f"Sent start recording command: {filename}")

    # ------------------------------------------------------------------------------------------------------------------
    def set_title(self, text: str):
        """Update the title text shown in the top bar overlay."""
        self.send({'type': 'command', 'command': 'setTitle', 'params': {'text': text}})

    # ------------------------------------------------------------------------------------------------------------------
    def set_label(self, label_id: str, text: str, *,
                  x: float | None = None, y: float | None = None,
                  font_size: float | None = None,
                  color: str | None = None,
                  background: str | None = None):
        """Create or update an overlay label. Set text to '' to hide it.

        Args:
            label_id: Unique identifier for the label.
            text: Label text. Empty string hides the label.
            x: Horizontal position (0.0 = left, 1.0 = right). Default 0.05.
            y: Vertical position (0.0 = top, 1.0 = bottom). Default 0.95.
            font_size: Font size in px. Default 14.
            color: Text color CSS string. Default '#fff'.
            background: Background color CSS string. Default 'rgba(0,0,0,0.6)'.
        """
        params = {'id': label_id, 'text': text}
        if x is not None:
            params['x'] = x
        if y is not None:
            params['y'] = y
        if font_size is not None:
            params['fontSize'] = font_size
        if color is not None:
            params['color'] = color
        if background is not None:
            params['background'] = background
        self.send({'type': 'command', 'command': 'setLabel', 'params': params})

    # ------------------------------------------------------------------------------------------------------------------
    def remove_label(self, label_id: str):
        """Remove an overlay label."""
        self.send({'type': 'command', 'command': 'removeLabel', 'params': {'id': label_id}})

    # ------------------------------------------------------------------------------------------------------------------
    def stop_recording(self):
        """Stop the current recording."""
        if not self._is_recording:
            self.logger.warning("Not currently recording.")
            return

        message = {
            'type': 'command',
            'command': 'stopRecording',
        }
        self.send(message)
        self.logger.info("Sent stop recording command.")

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        return self.id

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByUID(self, uid):

        # 1) drop any leading slash
        trimmed = uid.lstrip("/")

        # 2) Split off the GUI ID
        babylon_id, remainder = split_path(trimmed)

        if not babylon_id or babylon_id != self.id:
            self.logger.warning(f"UID '{uid}' does not match this Babylon's ID '{self.id}'")
            return None

        if not remainder:
            return self

        object_id, remainder = split_path(remainder)

        if object_id not in self.objects:
            self.logger.warning(f"Object with id {object_id} not found in scene.")
            return None

        if not remainder:
            return self.objects[object_id]
        else:
            if isinstance(self.objects[object_id], BabylonObjectGroup):
                return self.objects[object_id].getObjectByPath(remainder)
            else:
                self.logger.warning(
                    f"Object with id {object_id} is not a BabylonObjectGroup but remainder is not empty")
                return None

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):

        self.timer.reset()
        while not self._exit:
            if self._poll_objects:
                self._pollObjects()
            self._sendUpdate()
            self.timer.sleep_until_next()

    # ------------------------------------------------------------------------------------------------------------------
    def addObject(self, obj: BabylonObject):
        """
        Add a BabylonObject instance to the scene.
        """

        if obj.id in self.objects:
            raise ValueError(f"Object with id {obj.id} already exists.")

        self.objects[obj.id] = obj

        # Set the visualization reference so the object can send updates automatically.
        obj.parent = self

        payload = obj.getPayload()

        message = {
            'type': 'addObject',
            'id': obj.uid,
            'object_type': obj.object_type,
            'payload': payload
        }

        self.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def removeObject(self, object: Widget | BabylonObject | str):
        """
        Remove an object from the scene by its ID.
        """

        if isinstance(object, str):
            if object not in self.objects:
                self.logger.warning(f"Object {object} not found in scene.")
                return
            object = self.objects[object]

        message = {
            'type': 'removeObject',
            'id': object.uid
        }

        self.objects[object.id].on_remove()
        del self.objects[object.id]

        self.send(message)
        self.logger.info(f"Object {object.uid} removed from scene.")

    # ------------------------------------------------------------------------------------------------------------------
    def updateObjectConfig(self, object_id, config):
        """
        Update the configuration of an object in the scene.
        """
        message = {
            'type': 'updateObjectConfig',
            'id': object_id,
            'config': config
        }

        self.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def updateObject(self, object: BabylonObject | BabylonObjectGroup, data):
        with self._update_message_lock:
            self.update_message.updates[object.uid] = data

    # ------------------------------------------------------------------------------------------------------------------
    def objectFunction(self, object_id, function_name, arguments: dict):
        """
        Call a function on an object in the scene.
        """
        message = {
            'type': 'objectFunction',
            'id': object_id,
            'function': function_name,
            'arguments': arguments
        }

        self.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def add_camera(self, camera: BabylonCamera):
        """Add a named camera view button to the UI."""
        cam_dict = camera.to_dict()
        self._cameras.append(cam_dict)
        self.send({'type': 'add_camera', 'camera': cam_dict})

    # ------------------------------------------------------------------------------------------------------------------
    def set_camera(self, camera: BabylonCamera):
        """Set the camera parameters immediately (no UI button)."""
        self.send({
            'type': 'set_camera',
            'target': list(camera.target),
            'alpha': camera.alpha,
            'beta': camera.beta,
            'radius': camera.radius,
            'fov': camera.fov,
        })

    # ------------------------------------------------------------------------------------------------------------------
    def animate_camera(self, end: BabylonCamera, duration: float = 2.0,
                       start: BabylonCamera | None = None,
                       easing: str = 'smoothstep'):
        """Animate the camera from start to end over duration seconds.

        Args:
            end: Target camera state.
            duration: Animation duration in seconds.
            start: Starting camera state. If None, animates from the current camera position.
            easing: Easing function ('linear', 'smoothstep', 'ease_in', 'ease_out').
        """
        msg = {
            'type': 'animate_camera',
            'end': {
                'target': list(end.target),
                'alpha': end.alpha,
                'beta': end.beta,
                'radius': end.radius,
                'fov': end.fov,
            },
            'duration': duration,
            'easing': easing,
        }
        if start is not None:
            msg['start'] = {
                'target': list(start.target),
                'alpha': start.alpha,
                'beta': start.beta,
                'radius': start.radius,
                'fov': start.fov,
            }
        self.send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def center_camera_on(self, obj):
        """Start following a BabylonObject with the camera.

        Args:
            obj: A BabylonObject instance or an object id string.
        """
        object_id = obj if isinstance(obj, str) else obj.uid
        self.send({'type': 'follow_object', 'object_id': object_id})

    # ------------------------------------------------------------------------------------------------------------------
    def stop_following(self):
        """Stop following any object with the camera."""
        self.send({'type': 'stop_following'})

    # ------------------------------------------------------------------------------------------------------------------
    def set_dropdown(self, items: list[dict], selected: str = None):
        """Set the dropdown overlay items. Empty/None hides it.

        Args:
            items: List of dicts with 'key' and 'label' keys.
            selected: Optional key to pre-select.
        """
        self._dropdown_items = items or []
        self._dropdown_selected = selected
        self.send({'type': 'set_dropdown', 'items': self._dropdown_items, 'selected': selected})

    # ------------------------------------------------------------------------------------------------------------------
    def update_dropdown_selection(self, selected: str):
        """Change the selected dropdown value without rebuilding items."""
        self._dropdown_selected = selected
        self.send({'type': 'update_dropdown_selection', 'selected': selected})

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self):
        config = dict(self.config)
        config_cameras = list(config.get('cameras', []))
        all_cameras = config_cameras + list(self._cameras)
        if all_cameras:
            config['cameras'] = all_cameras

        payload = {
            'config': config,
            'objects': {k: v.getPayload() for k, v in self.objects.items()},
        }

        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def broadcast(self, message):

        if is_dataclass(message):
            message = asdict_optimized(message)

        self.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message, client=None):

        if is_dataclass(message):
            message = asdict_optimized(message)

        if client:
            self.server.sendToClient(client, message)
        else:
            self.server.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def onEvent(self, event_message, sender):
        # self.logger.important(f"Received event message: {event_message} from {sender}")

        # Handle recording events from the browser
        if isinstance(event_message, dict) and 'event' in event_message:
            event = event_message['event']
            if isinstance(event, dict):
                event_type = event.get('type')
                if event_type == 'record_start':
                    self._is_recording = True
                    filename = event.get('data', {}).get('fileName', '')
                    self.callbacks.recording_started.call(filename)
                elif event_type == 'record_stop':
                    self._is_recording = False
                    self.callbacks.recording_stopped.call()
                elif event_type == 'object_click':
                    object_id = event.get('object_id', '')
                    self.callbacks.object_click.call(object_id)
                elif event_type == 'floor_doubleclick':
                    pos = event.get('position', [0, 0, 0])
                    self.callbacks.floor_doubleclick.call(pos[0], pos[1])
                elif event_type == 'floor_middleclick':
                    pos = event.get('position', [0, 0, 0])
                    self.callbacks.floor_middleclick.call(pos[0], pos[1])
                elif event_type == 'floor_rightclick':
                    pos = event.get('position', [0, 0, 0])
                    self.callbacks.floor_rightclick.call(pos[0], pos[1])
                elif event_type == 'dropdown_select':
                    selected = event.get('selected', '')
                    self.callbacks.dropdown_select.call(selected)

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # === PRIVATE METHODS ==============================================================================================
    def _pollObjects(self):
        for id, obj in self.objects.items():
            if obj.pollable:
                data = obj.getData()
                self.updateObject(obj, data)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendUpdate(self):
        with self._update_message_lock:
            if len(self.update_message.updates) == 0:
                return

            update_message_dict = asdict_optimized(self.update_message)
            self.update_message = Babylon_UpdateMessage()
            self.send(update_message_dict)

    # ------------------------------------------------------------------------------------------------------------------
    def _initializeClient(self, client):
        message = {
            'type': 'init',
            'payload': self.getPayload()
        }
        self.send(message, client)

    # ------------------------------------------------------------------------------------------------------------------
    def _onMessage(self, message, sender=None):
        self.logger.debug(f"Received message: {message}")

        if 'type' not in message:
            self.logger.warning(f"Message does not contain a type: {message}")
            return

        match message['type']:
            case 'loaded':
                ...
            case 'event':
                self._handleEventMessage(message, sender)
            case 'recordingData':
                self._handle_recording_data(message)
            case 'recordingComplete':
                self._handle_recording_complete(message)
            case _:
                self.logger.warning(f"Unknown message type: {message['type']}")

    # ------------------------------------------------------------------------------------------------------------------
    def _new_client_callback(self, client):
        self.logger.debug(f"New client connected: {client}")

        if client not in self._clients:
            self._clients.append(client)
            self.callbacks.new_client.call(client)
            self._initializeClient(client)

            # Resend dropdown state so late-joining clients see it
            if self._dropdown_items:
                self.send({'type': 'set_dropdown', 'items': self._dropdown_items,
                           'selected': self._dropdown_selected}, client)
        else:
            self.logger.warning(f"Client already connected: {client}")

    # ------------------------------------------------------------------------------------------------------------------
    def _client_disconnected_callback(self, client, *args, **kwargs):

        if client in self._clients:
            self._clients.remove(client)
            self.callbacks.client_disconnected.call(client)
            self.logger.debug(f"Client disconnected: {client}")
        else:
            self.logger.warning(f"Client not found: {client}")

    # ------------------------------------------------------------------------------------------------------------------
    def _client_message_callback(self, client, message):
        self._onMessage(message, client)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleEventMessage(self, message, sender=None):
        # Scene-level events (no object id)
        if 'id' not in message or message['id'] is None:
            self.onEvent(message, sender)
            return

        object = self.getObjectByUID(message['id'])

        if object is None:
            self.logger.warning(f"Object with id {message['id']} not found.")

        object.onEvent(message, sender)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_recording_data(self, message):
        chunk_index = message.get('chunkIndex', 0)
        total_chunks = message.get('totalChunks', 0)
        data_b64 = message.get('data', '')

        if not self._recording_save_path:
            self.logger.warning("Received recording data but no save_path was set.")
            return

        if chunk_index == 0:
            self._recording_chunks = []
            self._recording_total_chunks = total_chunks

        chunk_bytes = base64.b64decode(data_b64)
        self._recording_chunks.append(chunk_bytes)
        self.logger.debug(f"Received recording chunk {chunk_index + 1}/{total_chunks} "
                          f"({len(chunk_bytes)} bytes)")

        # Write when all chunks arrived (handles race where recordingComplete arrives first)
        if len(self._recording_chunks) >= total_chunks:
            self._finalize_recording()

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_recording_complete(self, message):
        self._recording_complete_received = True

        # If all chunks already arrived, finalize now
        if self._recording_chunks and len(self._recording_chunks) >= self._recording_total_chunks > 0:
            self._finalize_recording()
        else:
            self.logger.debug("recordingComplete received, waiting for data chunks...")

    # ------------------------------------------------------------------------------------------------------------------
    def _finalize_recording(self):
        if not self._recording_save_path:
            self.logger.warning("Cannot finalize recording: no save_path set.")
            self._recording_chunks = []
            return

        save_path = self._recording_save_path

        # Ensure directory exists
        save_dir = os.path.dirname(save_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)

        # Assemble and write
        full_data = b''.join(self._recording_chunks)
        with open(save_path, 'wb') as f:
            f.write(full_data)

        self.logger.info(f"Recording saved to {save_path} ({len(full_data)} bytes, "
                         f"{len(self._recording_chunks)} chunks)")

        # Cleanup
        self._recording_chunks = []
        self._recording_total_chunks = 0
        self._recording_save_path = None
        self._recording_complete_received = False

        self.callbacks.recording_saved.call(save_path)
