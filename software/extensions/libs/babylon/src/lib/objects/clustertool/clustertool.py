import dataclasses

from extensions.libs.babylon.src.babylon import BabylonObject


@dataclasses.dataclass
class ClusterToolData:
    arm_angle: float = 0


class ClusterTool_BabylonObject(BabylonObject):
    type = 'clustertool'

    def __init__(self, object_id: str, **kwargs):
        super().__init__(object_id, **kwargs)
        self.data = ClusterToolData()

    def set_arm_angle(self, angle: float):
        self.data.arm_angle = angle
        self.update()

    def test(self, value):
        self.function(
            function_name='test_function',
            x=value
        )

    def getConfig(self) -> dict:
        config = {

        }
        return config

    def getData(self) -> dict:
        data = {
            'arm_angle': self.data.arm_angle
        }
        return data
