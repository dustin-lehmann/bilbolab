from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from extensions.libs.babylon.src.babylon import BabylonCamera, BabylonConfig, BabylonScene, BabylonLights
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.libs.babylon.src.scenarios.scenario import BabylonScenario

if TYPE_CHECKING:
    from extensions.libs.babylon.src.babylon import BabylonVisualization


class TrackScenario(BabylonScenario):
    """Straight track scenario — floor only, no walls.

    A long narrow track (default x=[-0.25, 2.75], y=[-0.25, 0.25]) with tiled
    floor. Objects stored in self.objects with key: floor.
    """

    def __init__(self,
                 x_range: list | None = None,
                 y_range: list | None = None,
                 floor_texture: str = 'floor_bright.png',
                 background_color: list | None = None,
                 camera: BabylonCamera | None = None,
                 show_coordinate_system: bool = False,
                 fog: bool = True,
                 lights: BabylonLights | None = None):

        x_range = x_range if x_range is not None else [0, 3]
        y_range = y_range if y_range is not None else [0, 1]
        center_x = (x_range[0] + x_range[1]) / 2
        center_y = (y_range[0] + y_range[1]) / 2

        if camera is None:
            camera = BabylonCamera(
                target=[center_x, center_y, 0.0],
                alpha=1.5705,
                beta=0.8705,
                radius=2.18,
                fov=1.1345,
            )

        scene = BabylonScene(add_fog=fog)
        config = BabylonConfig(
            camera=camera,
            scene=scene,
            lights=lights or BabylonLights(directional_direction=[1, 1, -1]),
            show_coordinate_system=show_coordinate_system,
        )
        if background_color is not None:
            config.background_color = background_color

        super().__init__(config=config)

        self.x_range = x_range
        self.y_range = y_range
        self.floor_texture = floor_texture

        # Derived dimensions
        self.length_x = x_range[1] - x_range[0]
        self.length_y = y_range[1] - y_range[0]
        self.center_x = center_x
        self.center_y = center_y

    def setup(self, babylon: BabylonVisualization):
        super().setup(babylon)

        # Floor — use [min, max] range format
        floor = SimpleFloor('floor',
                            size_x=self.x_range,
                            size_y=self.y_range,
                            tile_size=0.5,
                            texture=self.floor_texture)
        babylon.addObject(floor)
        self.objects['floor'] = floor


if __name__ == '__main__':
    from extensions.libs.babylon.src.standalone import StandaloneBabylon
    from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo

    scenario = TrackScenario(background_color=[1, 1, 1])
    babylon = StandaloneBabylon(title="Track Scenario", ws_port=9000, http_port=9200,
                                scenario=scenario)
    babylon.start()

    robot = BabylonBilbo('bilbo1', color=[0.7, 0.1, 0.1], text='1')
    babylon.addObject(robot)

    t0 = time.time()
    try:
        while True:
            t = time.time() - t0
            # Drive back and forth along the track
            x = 1.25 + 1.0 * math.sin(0.4 * t)
            robot.set_state(
                x=x,
                y=0,
                theta=0 if math.cos(0.4 * t) > 0 else math.pi,
                psi=0.03 * math.sin(3 * t),
            )
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        babylon.close()
