import dataclasses

from core.utils.dict_utils import update_dict
from extensions.libs.babylon.src.babylon import BabylonObject


@dataclasses.dataclass
class LaserLineData:
    start: list = dataclasses.field(default_factory=lambda: [0.0, 0.0, 0.0])
    end: list = dataclasses.field(default_factory=lambda: [1.0, 0.0, 0.0])


class LaserLine(BabylonObject):
    """A glowing laser line between two 3D points."""

    type: str = 'laser_line'

    def __init__(self, object_id: str, **kwargs):
        super().__init__(object_id, **kwargs)

        default_config = {
            'color': [1, 0, 0],
            'width': 0.005,
            'glow_intensity': 2.0,
            'alpha': 1.0,
        }

        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)
        self.data = LaserLineData(
            start=kwargs.get('start', [0.0, 0.0, 0.0]),
            end=kwargs.get('end', [1.0, 0.0, 0.0]),
        )

    # === METHODS ======================================================================================================
    def setStart(self, x: float = None, y: float = None, z: float = None):
        if x is not None:
            self.data.start[0] = x
        if y is not None:
            self.data.start[1] = y
        if z is not None:
            self.data.start[2] = z
        self.update()

    def setEnd(self, x: float = None, y: float = None, z: float = None):
        if x is not None:
            self.data.end[0] = x
        if y is not None:
            self.data.end[1] = y
        if z is not None:
            self.data.end[2] = z
        self.update()

    def setPoints(self, start: list = None, end: list = None):
        if start is not None:
            self.data.start = list(start)
        if end is not None:
            self.data.end = list(end)
        self.update()

    # === SERIALIZATION ================================================================================================
    def getConfig(self) -> dict:
        return {**self.config}

    def getData(self) -> dict:
        return {
            'start': list(self.data.start),
            'end': list(self.data.end),
        }
