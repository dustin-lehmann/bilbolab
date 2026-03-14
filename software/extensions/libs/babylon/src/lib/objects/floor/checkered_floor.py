from core.utils.dict_utils import update_dict
from extensions.libs.babylon.src.babylon import BabylonObject


class CheckeredFloor(BabylonObject):
    """Checkered floor with two alternating tile colors/textures.

    Uses the instanced floor on the JS side (type 'floor') which creates
    a grid of tiles with alternating materials in a checkerboard pattern.
    """
    type = 'floor'
    pollable = False

    def __init__(self, object_id: str, **kwargs):
        super().__init__(object_id, **kwargs)

        default_config = {
            'tile_size': 0.5,
            'tiles_x': 10,
            'tiles_y': 10,
            'offset': [0, 0],
            'color1': [0.5, 0.5, 0.5],
            'color2': [0.65, 0.65, 0.65],
            'texture_1': 'drawing_board.png',
            'texture_2': 'drawing_board.png',
            'brightness_1': 1,
            'brightness_2': 0.9,
            'border_type': 'line',
            'border_color': [0.4, 0.4, 0.4],
            'border_width': 0.025,
            'border_texture': 'floor_bright.png',
            'border_texture_brightness': 0.6,
        }

        self.config = update_dict(default_config, kwargs)

    def getConfig(self) -> dict:
        return {**self.config}

    def getData(self) -> dict:
        return {}
