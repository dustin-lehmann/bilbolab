"""
Babylon Objects Module

This module defines the base BabylonObject class and several subclasses
that represent simulation entities. These objects can be created on the
Python side and then sent (via their serialized message) to the BabylonJS
web application for rendering.
"""
from extensions.simulation.src.utils.orientations import twiprToRotMat
from core.utils.callbacks import callback_definition, CallbackContainer


@callback_definition
class BabylonObjectCallbacks:
    update: CallbackContainer


class BabylonObject:
    """
    Base class for Babylon visualization objects.
    """

    def __init__(self, object_id: str):
        """
        Initialize a BabylonObject.
        """
        self.object_id = object_id
        self.object_type = None  # To be defined in subclasses.
        self.data = {}  # Renamed from 'config' to 'data'

        self.callbacks = BabylonObjectCallbacks()

    def to_message(self):
        """
        Serialize the object into a message dictionary for the web app.
        """
        return {
            'type': 'addObject',
            'data': {
                'id': self.object_id,
                'class': self.object_type,
                'data': self.data
            }
        }

    def update_from_data(self, data: dict):
        """
        Update object parameters from a data dictionary.
        """
        self.data.update(data)
        self.callbacks.update.call(self)

    def on_remove(self):
        """
        Cleanup actions when the object is removed.
        """
        pass


# -----------------------------------------------------------------------------------------------
class BILBO(BabylonObject):
    """
    Class representing a TWIPR robot.
    """

    def __init__(self, object_id: str, **kwargs):
        """
        Initialize a TWIPR object with optional parameters.
        """
        super().__init__(object_id)
        self.object_type = "twipr"  # Must match the key in the object mappings.


        self.data = {
            'mesh': "./models/twipr/twipr_generic",
            'show_collision_frame': False,
            'wheel_diameter': 0.125,
            'color': [0.5, 0.5, 0.5],
            'configuration': {
                'pos': {'x': 0, 'y': 0, 'z': 0},
                'ori': [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
            }
        }
        # Update defaults with any provided overrides.
        self.data.update(kwargs)

        if 'pos' in kwargs:
            self.data['configuration']['pos'] = kwargs['pos']
        if 'ori' in kwargs:
            self.data['configuration']['ori'] = kwargs['ori']

    def setPosition(self, x, y):
        self.data['configuration']['pos'] = {'x': x, 'y': y, 'z': 0}
        self.callbacks.update.call(self)

    def setConfiguration(self, x, y, theta, psi):
        self.data['configuration']['pos'] = {'x': x, 'y': y, 'z': 0}

        rot = twiprToRotMat(theta, psi)

        self.data['configuration']['ori'] = rot
        self.callbacks.update.call(self)


# -----------------------------------------------------------------------------------------------
class Floor(BabylonObject):
    """
    Class representing a floor or tiled ground.
    """

    def __init__(self, object_id: str, tile_size: float = 1.0, tiles_x: int = 10, tiles_y: int = 10, **kwargs):
        """
        Initialize a Floor object.
        """
        super().__init__(object_id)
        self.object_type = "floor"  # Must match the mapping.
        self.data = {
            'tile_size': tile_size,
            'tiles_x': tiles_x,
            'tiles_y': tiles_y,
            'color1': [0.5, 0.5, 0.5],
            'color2': [0.65, 0.65, 0.65]
        }
        self.data.update(kwargs)


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
