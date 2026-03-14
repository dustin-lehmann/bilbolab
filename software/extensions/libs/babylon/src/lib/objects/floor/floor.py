from core.utils.dict_utils import update_dict
from extensions.libs.babylon.src.babylon import BabylonObject


class SimpleFloor(BabylonObject):
    type = 'floor_simple'
    pollable = False

    def __init__(self, object_id: str, **kwargs):
        super().__init__(object_id, **kwargs)

        default_config = {
            'size_x': [-2.5, 2.5],  # [min, max] range in meters, or scalar for centered floor
            'size_y': [-2.5, 2.5],  # [min, max] range in meters, or scalar for centered floor
            'tile_size': 0.5,
            'texture': 'floor_bright.png',
        }

        self.config = update_dict(default_config, kwargs)

        # Normalize size_x and size_y to [min, max] format
        # Supports both scalar (legacy: centered at origin) and array [min, max] formats
        if not isinstance(self.config['size_x'], list):
            half = self.config['size_x'] / 2
            self.config['size_x'] = [-half, half]
        if not isinstance(self.config['size_y'], list):
            half = self.config['size_y'] / 2
            self.config['size_y'] = [-half, half]

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self) -> dict:
        config = {
            **self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self) -> dict:
        return {}
