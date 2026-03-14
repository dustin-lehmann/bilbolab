import dataclasses

import numpy as np
import qmt

from core.utils.dataclass_utils import update_dataclass_from_dict
from core.utils.dict_utils import update_dict
from extensions.libs.babylon.src.babylon import BabylonObject


@dataclasses.dataclass
class CylinderData:
    x: float = 0
    y: float = 0
    z: float = 0
    orientation: np.ndarray = dataclasses.field(default_factory=lambda: np.asarray([1, 0, 0, 0]))


class Cylinder(BabylonObject):
    """A cylinder primitive for the Babylon visualization.

    The cylinder is defined by height (along z) and diameter. Position is at the
    center of the cylinder.
    """
    type = 'cylinder'

    def __init__(self, object_id: str, **kwargs):
        super().__init__(object_id, **kwargs)

        default_config = {
            'color': [0.5, 0.5, 0.5],
            'diameter': 0.1,
            'height': 1.0,
            'tessellation': 24,
            'alpha': 1.0,
            'accept_shadows': True,
            'glow': False,
            'glow_intensity': 2.0,
        }
        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)
        self.data = CylinderData()
        update_dataclass_from_dict(self.data, kwargs)

    def setPosition(self, x=None, y=None, z=None):
        if x is not None:
            self.data.x = x
        if y is not None:
            self.data.y = y
        if z is not None:
            self.data.z = z
        self.update()

    def setOrientation(self, quat=None):
        if quat is not None:
            self.data.orientation = np.asarray(quat, dtype=float)
            self.update()

    def setAngle(self, angle: float):
        quat = qmt.quatFromAngleAxis(angle, [0, 0, 1])
        self.setOrientation(quat)

    def getConfig(self) -> dict:
        return {**self.config}

    def getData(self) -> dict:
        return {
            'position': {
                'x': float(self.data.x),
                'y': float(self.data.y),
                'z': float(self.data.z),
            },
            'orientation': self.data.orientation.tolist(),
        }
