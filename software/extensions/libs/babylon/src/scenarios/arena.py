from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from extensions.libs.babylon.src.babylon import BabylonCamera, BabylonConfig, BabylonScene, BabylonLights
from extensions.libs.babylon.src.lib.objects.box.box import WallFancy
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.libs.babylon.src.scenarios.scenario import BabylonScenario

if TYPE_CHECKING:
    from extensions.libs.babylon.src.babylon import BabylonVisualization


class ArenaScenario(BabylonScenario):
    """Walled rectangular arena with floor.

    Creates a floor and four walls forming a rectangular arena. Wall and floor
    objects are stored in self.objects with keys: floor, wall_north, wall_south,
    wall_east, wall_west.

    Parameters
    ----------
    size : float
        Arena side length in meters (square arena).
    floor_size : float
        Floor tile area side length.
    floor_texture : str
        Floor texture filename.
    wall_texture : str
        Wall texture filename.
    wall_height : float
        Wall height in meters.
    include_end_caps : bool
        Whether walls have decorative end caps.
    background_color : list or None
        Override scene background color [r, g, b].
    camera : BabylonCamera or None
        Override default camera settings.
    show_coordinate_system : bool
        Whether to show the coordinate system axes.
    fog : bool
        Whether to enable fog. Ignored if ``scene`` is provided.
    scene : BabylonScene or None
        Override fog/atmosphere settings (overrides ``fog``).
    lights : BabylonLights or None
        Override light settings.
    """

    def __init__(self,
                 size: float = 3.0,
                 floor_size: float = 10.0,
                 floor_texture: str = 'floor_bright.png',
                 wall_texture: str = 'wood4.png',
                 wall_height: float = 0.25,
                 include_end_caps: bool = True,
                 background_color: list | None = None,
                 camera: BabylonCamera | None = None,
                 show_coordinate_system: bool = False,
                 fog: bool = True,
                 scene: BabylonScene | None = None,
                 lights: BabylonLights | None = None):

        if scene is None:
            scene = BabylonScene(add_fog=fog)
        config = BabylonConfig(
            camera=camera or BabylonCamera(),
            scene=scene,
            lights=lights or BabylonLights(),
            show_coordinate_system=show_coordinate_system,
        )
        if background_color is not None:
            config.background_color = background_color

        super().__init__(config=config)

        self.size = size
        self.floor_size = floor_size
        self.floor_texture = floor_texture
        self.wall_texture = wall_texture
        self.wall_height = wall_height
        self.include_end_caps = include_end_caps

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
