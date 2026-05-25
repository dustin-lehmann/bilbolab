from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

import numpy as np

from extensions.libs.babylon.src.babylon import BabylonCamera, BabylonConfig, BabylonScene, BabylonLights
from extensions.libs.babylon.src.lib.objects.box.box import WallFancy
from extensions.libs.babylon.src.lib.objects.floor.checkered_floor import CheckeredFloor
from extensions.libs.babylon.src.scenarios.scenario import BabylonScenario

if TYPE_CHECKING:
    from extensions.libs.babylon.src.babylon import BabylonVisualization


class LabScenario(BabylonScenario):
    """Walled arena with a checkered floor.

    Accepts either rectangular ranges via ``x_range``/``y_range`` or a single
    ``size`` (square, backward-compatible).

    Uses a two-tone checkered floor. Optionally surrounded by walls or a
    floor border line — but not both.  Set ``walls=True`` (default) for
    fancy walls, or ``walls=False`` to fall back to the floor's border.

    Objects stored in self.objects with keys:
    floor, and optionally wall_north, wall_south, wall_east, wall_west.
    """

    def __init__(self,
                 size: float | None = None,
                 x_range: list | None = None,
                 y_range: list | None = None,
                 tile_size: float = 0.5,
                 color1: list | None = None,
                 color2: list | None = None,
                 texture_1: str | None = 'carpet_light_blue.png',
                 texture_2: str | None = 'carpet.png',
                 brightness_1: float = 1.0,
                 brightness_2: float = 0.9,
                 walls: bool = True,
                 border_type: str | None = 'line',
                 wall_texture: str = 'wood4.png',
                 wall_height: float = 0.25,
                 wall_alpha: float = 0.6,
                 include_end_caps: bool = True,
                 background_color: list | None = None,
                 camera: BabylonCamera | None = None,
                 show_coordinate_system: bool = True,
                 fog: bool = True,
                 scene: BabylonScene | None = None,
                 lights: BabylonLights | None = None):

        # Resolve rectangle: explicit ranges win; otherwise fall back to square `size` (default 3.0)
        square = size if size is not None else 3.0
        if x_range is None:
            x_range = [0, square]
        if y_range is None:
            y_range = [0, square]

        length_x = x_range[1] - x_range[0]
        length_y = y_range[1] - y_range[0]
        center_x = (x_range[0] + x_range[1]) / 2
        center_y = (y_range[0] + y_range[1]) / 2
        max_len = max(length_x, length_y)

        if camera is None:
            # Radius scales with the larger dimension so the whole arena fits in view.
            camera = BabylonCamera(target=[center_x, center_y, 0.00],
                                   alpha=1.5705, beta=0.8705,
                                   radius=1.04 * max_len, fov=1.1345)

        if scene is None:
            scene = BabylonScene(add_fog=fog)
        config = BabylonConfig(
            camera=camera,
            scene=scene,
            lights=lights or BabylonLights(
                hemispheric_direction=[0.5, 0.5, 1],
                hemispheric_intensity=0.5,
                directional_position=[4, -2, 4],
                directional_direction=[-2, 1, -2],
                directional_intensity=0.8,
                directional_shadow_darkness=0.1
            ),
            show_coordinate_system=show_coordinate_system,
        )
        if background_color is not None:
            config.background_color = background_color

        super().__init__(config=config)

        self.x_range = x_range
        self.y_range = y_range
        self.length_x = length_x
        self.length_y = length_y
        self.center_x = center_x
        self.center_y = center_y
        self.tile_size = tile_size
        self.color1 = color1 if color1 is not None else [0.5, 0.5, 0.5]
        self.color2 = color2 if color2 is not None else [0.65, 0.65, 0.65]
        self.texture_1 = texture_1
        self.texture_2 = texture_2
        self.brightness_1 = brightness_1
        self.brightness_2 = brightness_2
        self.walls = walls
        self.border_type = border_type
        self.wall_texture = wall_texture
        self.wall_height = wall_height
        self.wall_alpha = wall_alpha
        self.include_end_caps = include_end_caps

    def setup(self, babylon: BabylonVisualization):
        super().setup(babylon)

        max_len = max(self.length_x, self.length_y)
        self.babylon.add_camera(
            BabylonCamera(name="Top",
                          target=[self.center_x, self.center_y, 0.0],
                          alpha=1.5708, beta=0.0000,
                          radius=3.03 * max_len, fov=0.3840))

        # Checkered floor — compute tile counts per dimension
        tiles_x = max(1, round(self.length_x / self.tile_size))
        tiles_y = max(1, round(self.length_y / self.tile_size))

        # When walls are shown, disable the floor border (and vice versa)
        if self.walls:
            floor_border = None
        else:
            floor_border = self.border_type

        floor_kwargs = {
            'tile_size': self.tile_size,
            'tiles_x': tiles_x,
            'tiles_y': tiles_y,
            'offset': [self.center_x, self.center_y],
            'color1': self.color1,
            'color2': self.color2,
            'texture_1': self.texture_1,
            'texture_2': self.texture_2,
            'brightness_1': self.brightness_1,
            'brightness_2': self.brightness_2,
            'border_type': floor_border,
        }

        floor = CheckeredFloor('floor', **floor_kwargs)
        babylon.addObject(floor)
        self.objects['floor'] = floor

        # Walls (only when enabled). North/south run along X (length_x); east/west along Y (length_y).
        if self.walls:
            wall_defs = [
                ('wall_north', {'x': self.center_x, 'y': self.y_range[1], 'length': self.length_x}),
                ('wall_south', {'x': self.center_x, 'y': self.y_range[0], 'length': self.length_x}),
                ('wall_east',  {'x': self.x_range[1], 'y': self.center_y, 'length': self.length_y, 'angle': np.pi / 2}),
                ('wall_west',  {'x': self.x_range[0], 'y': self.center_y, 'length': self.length_y, 'angle': np.pi / 2}),
            ]
            for wall_id, props in wall_defs:
                wall = WallFancy(wall_id, length=props['length'], texture=self.wall_texture,
                                 height=self.wall_height, alpha=self.wall_alpha,
                                 include_end_caps=self.include_end_caps)
                wall.setPosition(x=props.get('x', 0), y=props.get('y', 0))
                if 'angle' in props:
                    wall.setAngle(props['angle'])
                babylon.addObject(wall)
                self.objects[wall_id] = wall


if __name__ == '__main__':
    from extensions.libs.babylon.src.standalone import StandaloneBabylon
    from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo

    #
    scenario = LabScenario(size=3,
                           background_color=[1, 1, 1])

    # scenario = LabScenario(size=3,
    #
    #                        background_color=[1, 1, 1])

    babylon = StandaloneBabylon(title="Lab Scenario", ws_port=9000, http_port=9200,
                                scenario=scenario)
    babylon.start()

    robot = BabylonBilbo('bilbo1', color=[0.7, 0.1, 0.1], text='1')
    babylon.addObject(robot)

    t0 = time.time()
    try:
        while True:
            t = time.time() - t0
            angle = 0.5 * t
            robot.set_state(
                x=1.5 + 0.8 * math.cos(angle),
                y=1.5 + 0.8 * math.sin(angle),
                theta=angle + math.pi / 2,
                psi=0.04 * math.sin(3 * t),
            )
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        babylon.close()
