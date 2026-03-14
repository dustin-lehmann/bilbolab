from __future__ import annotations

import dataclasses
import numpy as np

# === CUSTOM MODULES ===================================================================================================
from core.utils.dataclass_utils import update_dataclass_from_dict


# === PRIVATE METHODS ==============================================================================================


# ======================================================================================================================
# ======================================================================================================================
@dataclasses.dataclass
class BILBO_Data:
    x: float = 0
    y: float = 0
    theta: float = 0
    psi: float = 0


# ======================================================================================================================
class BILBO(BabylonObject):
    """
    Class representing a TWIPR robot.
    """
    type: str = 'bilbo'
    data: BILBO_Data

    def __init__(self, object_id: str, config=None, **kwargs):
        """
        Initialize a TWIPR object with optional parameters.
        """
        super().__init__(object_id)

        default_config = {
            'mesh': "./models/twipr/twipr_generic",
            'show_collision_frame': False,
            'wheel_diameter': 0.125,
            'color': [0.5, 0.5, 0.5],
        }
        if config is None:
            config = {}

        self.config = {**default_config, **config}

        self.data = BILBO_Data()

        update_dataclass_from_dict(self.data, kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def setPosition(self, x=None, y=None):
        if x is not None:
            self.data.x = x
        if y is not None:
            self.data.y = y

        self.callbacks.update.call(self)

    # ------------------------------------------------------------------------------------------------------------------
    def setOrientation(self, theta=None, psi=None):
        if theta is not None:
            self.data.theta = theta
        if psi is not None:
            self.data.psi = psi

        self.callbacks.update.call(self)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self):
        config = {
            'type': self.type,
            'id': self.object_id,
            'config': self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self):
        data = {
            'x': self.data.x,
            'y': self.data.y,
            'theta': self.data.theta,
            'psi': self.data.psi,
        }

        return data


# -----------------------------------------------------------------------------------------------
class Floor(BabylonObject):
    """
    Class representing a floor or tiled ground.
    """
    type: str = 'floor'

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, object_id: str, config=None, **kwargs):
        """
        Initialize a Floor object.
        """
        super().__init__(object_id)

        default_config = {
            'tile_size': 0.5,
            'tiles_x': 10,
            'tiles_y': 10,
            'color1': [0.5, 0.5, 0.5],
            'color2': [0.65, 0.65, 0.65]
        }

        if config is None:
            config = {}

        self.config = {**default_config, **config, **kwargs}

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self):
        config = {
            'type': self.type,
            'id': self.object_id,
            'config': self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self):
        data = {}
        return data


# ======================================================================================================================
@dataclasses.dataclass
class BoxData:
    x: float = 0
    y: float = 0
    z: float = 0
    orientation: np.ndarray = dataclasses.field(default_factory=lambda: np.asarray([1, 0, 0, 0]))


class Box(BabylonObject):
    type: str = 'box'
    data: BoxData

    def __init__(self, object_id: str, config=None, **kwargs):
        super().__init__(object_id)

        default_config = {
            'size': {'x': 1, 'y': 1, 'z': 1},
            'color': [0.5, 0.5, 0.5],
            'texture': None,
            'wireframe': False,
        }

        self.config = {**default_config, **config}
        self.config.update(kwargs)
        self.data = BoxData()
        update_dataclass_from_dict(self.data, kwargs)

    def getConfig(self):
        config = {
            'type': self.type,
            'id': self.object_id,
            'config': self.config,
        }

    def getData(self):
        data = {
            'x': self.data.x,
            'y': self.data.y,
            'z': self.data.z,
            'orientation': self.data.orientation,
        }
        return data


# -----------------------------------------------------------------------------------------------
class Obstacle(BabylonObject):
    """
    Class representing an obstacle.
    """

    def __init__(self, object_id: str, size: dict = None, pos: dict = None, color: list = None,
                 texture: str = "", wireframe: bool = False, **kwargs):
        """
        Initialize an Obstacle object.
        """
        super().__init__(object_id)
        self.object_type = "obstacle"  # Must match the mapping.
        self.data = {
            'size': size if size is not None else {'x': 1, 'y': 1, 'z': 1},
            'configuration': {
                'pos': pos if pos is not None else {'x': 0, 'y': 0, 'z': 0},
                'ori': [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
            },
            'color': color if color is not None else [0.5, 0.5, 0.5],
            'texture': texture,
            'wireframe': wireframe
        }
        self.data.update(kwargs)
