import dataclasses

from core.utils.dataclass_utils import update_dataclass_from_dict
from core.utils.dict_utils import update_dict
from extensions.libs.babylon.src.babylon import BabylonObject


@dataclasses.dataclass
class BabylonStaticData:
    x: float = 0
    y: float = 0
    psi: float = 0

class BabylonStatic(BabylonObject):
    type: str = 'static'
    data: BabylonStaticData

    def __init__(self, object_id: str, **kwargs):
        super().__init__(object_id, **kwargs)

        default_config = {
        }

        self.config = update_dict(self.config, default_config, kwargs)
        self.data = BabylonStaticData()
        update_dataclass_from_dict(self.data, kwargs)


    def setPosition(self, x=None, y=None):
        if x is not None:
            self.data.x = x
        if y is not None:
            self.data.y = y
        self.update()

    def setOrientation(self, psi=None):
        if psi is not None:
            self.data.psi = psi

        self.update()

    def setState(self, x=None, y=None, psi=None):
        self.setPosition(x, y)
        self.setOrientation(psi)

    def getConfig(self) -> dict:
        config = {
            **self.config,
        }
        return config

    def getData(self) -> dict:
        data = {
            'x': self.data.x,
            'y': self.data.y,
            'psi': self.data.psi,
        }
        return data