from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from extensions.libs.babylon.src.babylon import BabylonCamera, BabylonConfig, BabylonScene, BabylonLights
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.libs.babylon.src.scenarios.scenario import BabylonScenario

if TYPE_CHECKING:
    from extensions.libs.babylon.src.babylon import BabylonVisualization


class CyberScenario(BabylonScenario):
    """Large open plane with tiled floor and white background."""

    def __init__(self,
                 size: float = 50.0,
                 tile_size: float = 0.5,
                 texture: str = 'floor_tile.svg',
                 coordinate_system: bool = False,
                 camera: BabylonCamera | None = None,
                 lights: BabylonLights | None = None):

        if camera is None:
            camera = BabylonCamera(target=[0.00, 0.00, 0.00], alpha=1.1014, beta=1.2099, radius=2.24, fov=0.7679)

        config = BabylonConfig(
            camera=camera,
            scene=BabylonScene(add_fog=True, fog_color=[1, 1, 1], fog_density=0.04),
            background_color=[1, 1, 1],
            lights=lights or BabylonLights(
                hemispheric_direction=[0, 0, 1],
                hemispheric_intensity=0.6,
                directional_position=[10, -5, 10],
                directional_direction=[-1, 1, -1],
                directional_intensity=0.7,
                directional_shadow_darkness=0.1,
            ),
            show_coordinate_system=coordinate_system,
            coordinate_system_length = 0.1
        )

        super().__init__(config=config)

        self.size = size
        self.tile_size = tile_size
        self.texture = texture

    def setup(self, babylon: BabylonVisualization):
        super().setup(babylon)

        half = self.size / 2
        floor = SimpleFloor('floor',
                            size_x=[-half, half],
                            size_y=[-half, half],
                            tile_size=self.tile_size,
                            texture=self.texture)
        babylon.addObject(floor)
        self.objects['floor'] = floor


if __name__ == '__main__':
    from extensions.libs.babylon.src.standalone import StandaloneBabylon
    from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo

    scenario = CyberScenario()

    babylon = StandaloneBabylon(title="Cyber Scenario", ws_port=9000, http_port=9200,
                                scenario=scenario)
    babylon.start()

    robot = BabylonBilbo('bilbo1', color=[0.7, 0.1, 0.1], text='1')
    babylon.addObject(robot)

    t0 = time.time()
    try:
        while True:
            # t = time.time() - t0
            # angle = 0.5 * t
            # robot.set_state(
            #     x=2.0 * math.cos(angle),
            #     y=2.0 * math.sin(angle),
            #     theta=angle + math.pi / 2,
            #     psi=0.04 * math.sin(3 * t),
            # )
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        babylon.close()
