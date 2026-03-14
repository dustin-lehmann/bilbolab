from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

import numpy as np

from extensions.libs.babylon.src.lib.objects.box.box import WallFancy
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.libs.babylon.src.scenarios.scenario import BabylonScenario

if TYPE_CHECKING:
    from extensions.libs.babylon.src.babylon import BabylonVisualization


class ArenaScenario(BabylonScenario):
    """Walled square arena with floor.

    Creates a floor and four walls. Objects stored in self.objects with keys:
    floor, wall_north, wall_south, wall_east, wall_west.
    """

    def __init__(self,
                 size: float = 3.0,
                 floor_size: float = 10.0,
                 floor_texture: str = 'floor_bright.png',
                 wall_texture: str = 'wood4.png',
                 wall_height: float = 0.25,
                 include_end_caps: bool = True,
                 background_color: list | None = None,
                 camera_radius: float | None = None,
                 camera_alpha: float | None = None,
                 camera_beta: float | None = None,
                 camera_target: list | None = None,
                 show_coordinate_system: bool = False,
                 fog: bool = True,
                 lights: dict | None = None):
        super().__init__()

        self.size = size
        self.floor_size = floor_size
        self.floor_texture = floor_texture
        self.wall_texture = wall_texture
        self.wall_height = wall_height
        self.include_end_caps = include_end_caps
        self.background_color = background_color
        self.camera_radius = camera_radius
        self.camera_alpha = camera_alpha
        self.camera_beta = camera_beta
        self.camera_target = camera_target
        self.show_coordinate_system = show_coordinate_system
        self.fog = fog
        self.lights = lights

    def get_config(self) -> dict:
        config = {}

        config['show_coordinate_system'] = self.show_coordinate_system

        if self.background_color is not None:
            config['background_color'] = self.background_color

        camera = {}
        if self.camera_radius is not None:
            camera['radius'] = self.camera_radius
        if self.camera_alpha is not None:
            camera['alpha'] = self.camera_alpha
        if self.camera_beta is not None:
            camera['beta'] = self.camera_beta
        if self.camera_target is not None:
            camera['target'] = self.camera_target
        if camera:
            config['camera'] = camera

        if not self.fog:
            config['scene'] = {'add_fog': False}

        if self.lights is not None:
            config['lights'] = self.lights

        return config

    def setup(self, babylon: BabylonVisualization):
        super().setup(babylon)

        # Floor
        floor = SimpleFloor('floor', size_x=self.floor_size, size_y=self.floor_size,
                            texture=self.floor_texture)
        babylon.addObject(floor)
        self.objects['floor'] = floor

        # Walls
        half = self.size / 2
        wall_defs = [
            ('wall_north', {'y': half}),
            ('wall_south', {'y': -half}),
            ('wall_east', {'x': half, 'angle': np.pi / 2}),
            ('wall_west', {'x': -half, 'angle': np.pi / 2}),
        ]
        for wall_id, props in wall_defs:
            wall = WallFancy(wall_id, length=self.size, texture=self.wall_texture,
                             height=self.wall_height, include_end_caps=self.include_end_caps)
            wall.setPosition(x=props.get('x', 0), y=props.get('y', 0))
            if 'angle' in props:
                wall.setAngle(props['angle'])
            babylon.addObject(wall)
            self.objects[wall_id] = wall


if __name__ == '__main__':
    from extensions.libs.babylon.src.standalone import StandaloneBabylon
    from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo

    scenario = ArenaScenario(size=3)
    babylon = StandaloneBabylon(title="Arena Scenario", ws_port=9000, http_port=9200,
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
                x=0.8 * math.cos(angle),
                y=0.8 * math.sin(angle),
                theta=angle + math.pi / 2,
                psi=0.04 * math.sin(3 * t),
            )
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        babylon.close()
