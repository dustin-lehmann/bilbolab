from __future__ import annotations

import abc
import math
from typing import Any

from core.utils.dict_utils import update_dict
from core.utils.logging_utils import Logger
from extensions.gui.src.lib.utilities import split_path


# === MAP OBJECT =======================================================================================================
class MapObject(abc.ABC):
    config: dict
    data: dict
    id: str

    type: str
    parent: Any | None = None

    # === INIT =========================================================================================================
    def __init__(self, id, **kwargs):

        self.id = id
        default_config = {
            'name': id,

            'highlight': False,
            'visible': True,
            'dim': False,
            'show_trail': False,

            'show_name': True,
            'show_coordinates': False,

            'tooltip': None
        }

        self.config = update_dict(default_config, kwargs)
        self.data = {}
        self.logger = Logger(f"Map Object {id}", 'DEBUG')

    # === PROPERTIES ===================================================================================================
    @property
    def uid(self):
        if self.parent:
            return f"{self.parent.uid}/{self.id}"
        else:
            return self.id

    # === METHODS ======================================================================================================
    def update(self, data=None, **kwargs):
        if data is None:
            data = {}

        self.data = update_dict(self.data, data, kwargs)
        self._sendUpdate()

    # ------------------------------------------------------------------------------------------------------------------
    def updateConfig(self, **kwargs):
        self.config = update_dict(self.config, kwargs)
        self._sendUpdateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def getMap(self):
        if self.parent:
            return self.parent.getMap()
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self):
        return self.config

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self):
        return self.data

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self):
        payload = {
            'id': self.uid,
            'type': self.type,
            'data': self.data,
            'config': self.config,
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def highlight(self, highlight: bool):
        self.config['highlight'] = highlight
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def dim(self, dim: bool):
        self.config['dim'] = dim
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def visible(self, visible: bool):
        self.config['visible'] = visible
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def clearHistory(self):
        ...

    # === PRIVATE METHODS ==============================================================================================
    def _sendMessage(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _sendUpdateConfig(self):
        map = self.getMap()
        if map is not None:
            map.updateConfig(self)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendUpdate(self):
        map = self.getMap()
        if map is not None:
            map.update(self)


# === MAP OBJECT GROUP =================================================================================================
class MapObjectGroup:
    id: str

    objects: dict[str, MapObject]
    groups: dict[str, MapObjectGroup]
    parent: Any | None = None

    config: dict

    # === INIT =========================================================================================================
    def __init__(self, id, **kwargs):

        self.id = id
        self.logger = Logger(f"Group {id}", 'DEBUG')

        default_config = {
            'name': id,
            'visible': True,
            'dim': False,
        }

        self.config = update_dict(default_config, kwargs)

        self.objects = {}
        self.groups = {}

    # === PROPERTIES ===================================================================================================
    @property
    def uid(self):
        if self.parent:
            return f"{self.parent.uid}/{self.id}"
        else:
            return self.id

    # === METHODS ======================================================================================================
    def addObject(self, obj: MapObject) -> MapObject | None:

        if obj.id in self.objects:
            self.logger.error(f"Object with id {obj.id} already exists in group {self.id}")
            return None

        obj.parent = self
        self.objects[obj.id] = obj

        message = {
            'type': 'add',
            'parent': self.uid,
            'payload': obj.getPayload()
        }

        self._sendMessage(message)

        return obj

    # ------------------------------------------------------------------------------------------------------------------
    def removeObject(self, obj: MapObject):

        if obj.parent is not self:
            self.logger.error(
                f"Object with id '{obj.id}' does not belong to group '{self.id}'. Cannot remove.")
            return

        del self.objects[obj.id]
        message = {
            'type': 'remove',
            'parent': self.uid,
            'id': obj.uid
        }
        self._sendMessage(message)

    # ------------------------------------------------------------------------------------------------------------------
    def addGroup(self, group: MapObjectGroup) -> MapObjectGroup | None:
        if group.id in self.groups:
            self.logger.error(f"Group with id '{group.id}' already exists in group '{self.id}'.")
            return None

        group.parent = self
        self.groups[group.id] = group
        message = {
            'type': 'add',
            'parent': self.uid,
            'payload': group.getPayload()
        }
        self._sendMessage(message)
        return group

    # ------------------------------------------------------------------------------------------------------------------
    def removeGroup(self, group: MapObjectGroup):
        if group.parent is not self:
            self.logger.error(
                f"Group with id '{group.id}' does not belong to group '{self.id}'. Cannot remove.")
            return

        del self.groups[group.id]
        message = {
            'type': 'remove',
            'parent': self.uid,
            'id': group.uid
        }
        self._sendMessage(message)

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByPath(self, path) -> MapObject | MapObjectGroup | None:

        key, remainder = split_path(path)

        if key in self.groups:
            if not remainder:
                return self.groups[key]
            else:
                return self.groups[key].getObjectByPath(remainder)

        if key in self.objects:
            return self.objects[key]

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getMap(self):
        if self.parent:
            return self.parent.getMap()
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self):
        return self.config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self):
        payload = {
            'id': self.uid,
            'type': 'group',
            'config': self.config,
            'objects': {k: v.getPayload() for k, v in self.objects.items()},
            'groups': {k: v.getPayload() for k, v in self.groups.items()}
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def visible(self, visible: bool):
        self.config['visible'] = visible
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def highlight(self, highlight: bool):
        self.config['highlight'] = highlight
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def dim(self, dim: bool):
        self.config['dim'] = dim
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def updateConfig(self, **kwargs):
        self.config = update_dict(self.config, kwargs)
        self._sendUpdateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def objectInGroup(self, element_id: str) -> bool:
        if element_id in self.objects:
            return True
        elif element_id in self.groups:
            return True
        else:
            return False

    # === PRIVATE METHODS ==============================================================================================
    def _sendMessage(self, message):
        map = self.getMap()
        if map is not None:
            map.sendMessage(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendUpdateConfig(self):
        map = self.getMap()
        if map is not None:
            map.updateConfig(self)
    # ------------------------------------------------------------------------------------------------------------------


# === POINT ============================================================================================================
class Point(MapObject):
    type = 'point'

    # === INIT =========================================================================================================
    def __init__(self, id, **kwargs):
        super().__init__(id, **kwargs)

        default_config = {
            "size": 0.05,  # radius; units depend on size_mode
            "size_mode": "meter",  # 'pixel' | 'meter'
            "color": [255 / 255, 134 / 255, 125 / 255, 1],  # RGBA 0..1
            "border_width": 1,  # in px
            "border_color": [0, 0, 0, 1],  # RGBA 0..1
            "shape": "circle",  # 'circle' | 'square' | 'triangle' | 'diamond'
        }

        default_data = {
            'x': 0,
            'y': 0,
        }

        self.config = update_dict(self.config, default_config, kwargs)
        self.data = update_dict(default_data, kwargs, allow_add=False)

    # === METHODS ======================================================================================================


# === LINE =============================================================================================================
class Line(MapObject):
    type = 'line'

    def __init__(self, id, start, end, **kwargs):
        super().__init__(id, **kwargs)

        default_config = {
            'visible': True,
            'color': [0.9, 0.9, 0.9, 0.6],  # RGBA 0..1
            'width': 2,  # px
            'style': 'dashed',  # 'solid' | 'dashed' | 'dotted'
            'dash_px': [6, 4],  # used when style='dashed'
            'dot_px': [2, 3],  # used when style='dotted' (dot, gap)
            'show_name': True,
            'label_px': 12,
            'label_offset_px': 8,  # px offset along normal
            'layer': 2,  # default below points
        }

        if isinstance(start, MapObject):
            if start.parent is None:
                self.logger.warning(f"Object with id '{start.id}' has no parent. This will not work")

            start = start.uid

        if isinstance(end, MapObject):
            if end.parent is None:
                self.logger.warning(f"Object with id '{end.id}' has no parent. This will not work")

            end = end.uid

        default_data = {
            'start': start,
            'end': end,
        }

        self.config = update_dict(self.config, default_config, kwargs)
        self.data = update_dict(default_data, kwargs, allow_add=False)


# === CIRCLE ===========================================================================================================
class Circle(MapObject):
    type = 'circle'

    def __init__(self, id, **kwargs):
        super().__init__(id, **kwargs)

        default_config = {
            'color': [1, 0, 0, 1],  # fill RGBA
            'border_color': [0, 0, 0, 1],  # stroke RGBA
            'border_width': 1,  # px
            'show_name': False,
            'label_px': 12,
            'layer': 1,
            'opacity': 1,
        }

        default_data = {
            'x': 0,
            'y': 0,
            'radius': 1,  # meters (world units)
        }

        self.config = update_dict(self.config, default_config, kwargs)
        self.data = update_dict(default_data, kwargs, allow_add=False)


# === ELLIPSE ==========================================================================================================
class Ellipse(MapObject):
    type = 'ellipse'

    def __init__(self, id, **kwargs):
        super().__init__(id, **kwargs)

        # Visual config mirrors JS: fill/border RGBA, px-accurate border, label opts, layer, opacity
        default_config = {
            'color': [1, 0, 0, 0.35],  # fill RGBA
            'border_color': [0, 0, 0, 1],  # stroke RGBA
            'border_width': 1,  # px
            'show_name': False,
            'label_px': 12,
            'layer': 1,
            'opacity': 1,
        }

        # Geometry in meters (world units), with rotation in radians (CCW from +x)
        default_data = {
            'x': 0.0,
            'y': 0.0,
            'rx': 1.0,  # x-radius (semi-major/minor; no ordering enforced)
            'ry': 0.5,  # y-radius
            'psi': 0.0,  # rotation [rad], CCW from +x
        }

        self.config = update_dict(self.config, default_config, kwargs)
        self.data = update_dict(default_data, kwargs, allow_add=False)


# === RECTANGLE ========================================================================================================
class Rectangle(MapObject):
    type = 'rectangle'

    def __init__(self, id, **kwargs):
        super().__init__(id, **kwargs)

        default_config = {
            'color': [1, 0, 0, 0.35],  # fill RGBA
            'border_color': [0, 0, 0, 1],  # stroke RGBA
            'border_width': 1,  # px
            'show_name': False,
            'label_px': 12,
            'layer': 1,
        }

        default_data = {
            'x': 0,
            'y': 0,
            'width': 1,
            'height': 1,  # meters (world units)
            'psi': 0,  # rotation angle in radians (counter-clockwise)
        }

        self.config = update_dict(self.config, default_config, kwargs)
        self.data = update_dict(default_data, kwargs, allow_add=False)


# === AGENT ============================================================================================================
class Agent(MapObject):
    type = 'agent'

    def __init__(self, id, **kwargs):
        super().__init__(id, **kwargs)

        default_config = {
            # body
            'size': 0.05,
            'size_mode': 'meter',  # 'meter' | 'pixel'
            'color': [0, 0.7, 0.7, 1],
            'border_color': [0, 0, 0, 1],
            'border_width': 1,  # px

            # arrow
            'arrow_length': 0.2,
            'arrow_length_mode': 'meter',
            'arrow_width': 0.02,
            'arrow_width_mode': 'meter',
            'arrow_color': 'inherit',  # 'inherit' | RGBA array

            # highlight
            'highlight': False,
            'highlight_margin_px': 4,

            'label_px': 12,

            'layer': 4,
        }

        default_data = {
            'x': 0,
            'y': 0,
            'psi': 0,  # radians (CCW from +x)
        }

        self.config = update_dict(self.config, default_config, kwargs)
        self.data = update_dict(default_data, kwargs, allow_add=False)


# === VISION AGENT =====================================================================================================
class VisionAgent(Agent):
    type = 'vision_agent'

    def __init__(self, id, **kwargs):
        # First, init as an Agent (gets Agent defaults + kwargs)
        super().__init__(id, **kwargs)

        # JS sets arrow defaults to 0.25/0.03 for the Vision Agent, but lets payload override.
        # Only bump them if the caller *didn't* supply them.
        if 'arrow_length' not in kwargs:
            self.config['arrow_length'] = 0.25
        if 'arrow_width' not in kwargs:
            self.config['arrow_width'] = 0.03

        # Vision-specific defaults (again, caller can override via kwargs)
        self.config.setdefault('fov', math.pi / 2)  # radians
        self.config.setdefault('vision_radius', 0.5)  # world units
        self.config.setdefault('vision_opacity', 0.3)  # 0..1


# === COORDINATE SYSTEM ================================================================================================
class CoordinateSystem(MapObject):
    type = 'coordinate_system'

    def __init__(self, id, **kwargs):
        super().__init__(id, **kwargs)

        default_config = {
            'x_color': [1, 0, 0, 1],
            'y_color': [0, 1, 0, 1],
            'origin_color': [0.8, 0.8, 1, 1],
            'length': 0.25,  # meters
            'width': 0.02,  # meters (shaft width)
            'opacity': 1,

            # labels
            'show_name': False,
            'show_coordinates': False,
            'label_color': [0.9, 0.9, 0.9, 1],
            'label_px': 12,

            'layer': 2,
        }

        default_data = {
            'x': 0,
            'y': 0,
            'psi': 0,  # radians
        }

        self.config = update_dict(self.config, default_config, kwargs)
        self.data = update_dict(default_data, kwargs, allow_add=False)
