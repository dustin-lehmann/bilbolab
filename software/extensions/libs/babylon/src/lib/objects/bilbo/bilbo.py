import dataclasses

from core.utils.dataclass_utils import update_dataclass_from_dict
from core.utils.dict_utils import update_dict
from extensions.libs.babylon.src.babylon import BabylonObject


@dataclasses.dataclass
class BabylonBilboData:
    x: float = 0
    y: float = 0
    theta: float = 0
    psi: float = 0


class BabylonBilbo(BabylonObject):
    type: str = 'bilbo'

    def __init__(self, object_id: str, **kwargs):
        super().__init__(object_id, **kwargs)

        default_config = {
            'text': '1',
            'color': [1, 0, 0],
            'text_color': [1, 1, 1]
        }

        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)
        self.data = BabylonBilboData()
        update_dataclass_from_dict(self.data, kwargs)

    # === METHODS ======================================================================================================
    def setPosition(self, x=None, y=None):
        if x is not None:
            self.data.x = x
        if y is not None:
            self.data.y = y
        self.update()

    # ------------------------------------------------------------------------------------------------------------------
    def setOrientation(self, theta=None, psi=None):
        if theta is not None:
            self.data.theta = theta
        if psi is not None:
            self.data.psi = psi

        self.update()

    # ------------------------------------------------------------------------------------------------------------------
    def set_state(self, x=None, y=None, theta=None, psi=None):
        self.setPosition(x, y)
        self.setOrientation(theta, psi)

    # ------------------------------------------------------------------------------------------------------------------
    def set_color(self, color: list):
        self.config['color'] = color
        self.function('setColor', color=color)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self) -> dict:
        config = {
            **self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self) -> dict:
        data = {
            'x': self.data.x,
            'y': self.data.y,
            'theta': self.data.theta,
            'psi': self.data.psi,
        }
        return data

    # === PRIVATE METHODS ==============================================================================================
