from __future__ import annotations

from typing import TYPE_CHECKING

from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.libs.babylon.src.scenarios.scenario import BabylonScenario

if TYPE_CHECKING:
    from extensions.libs.babylon.src.babylon import BabylonVisualization


class EmptyScenario(BabylonScenario):
    """Just a floor, no walls.

    Parameters
    ----------
    floor_size : float
        Floor tile area side length.
    floor_texture : str
        Floor texture filename.
    background_color : list or None
        Override scene background color [r, g, b].
    camera_radius : float or None
        Override camera distance.
    camera_alpha : float or None
        Override camera azimuth angle (radians).
    camera_beta : float or None
        Override camera elevation angle (radians).
    camera_target : list or None
        Override camera look-at target [x, y, z].
    show_coordinate_system : bool
        Whether to show the coordinate system axes.
    fog : bool
        Whether to enable fog.
    lights : dict or None
        Override light settings. Keys: hemispheric_direction, hemispheric_intensity,
        directional_direction, directional_position, directional_intensity,
        directional2_direction, directional2_position, directional2_intensity.
    """

    def __init__(self,
                 floor_size: float = 10.0,
                 floor_texture: str = 'floor_bright.png',
                 background_color: list | None = None,
                 camera_radius: float | None = None,
                 camera_alpha: float | None = None,
                 camera_beta: float | None = None,
                 camera_target: list | None = None,
                 show_coordinate_system: bool = False,
                 fog: bool = True,
                 lights: dict | None = None):
        super().__init__()

        self.floor_size = floor_size
        self.floor_texture = floor_texture
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

        # Camera
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

        # Fog
        if not self.fog:
            config['scene'] = {'add_fog': False}

        if self.lights is not None:
            config['lights'] = self.lights

        return config

    def setup(self, babylon: BabylonVisualization):
        super().setup(babylon)

        floor = SimpleFloor('floor', size_x=self.floor_size, size_y=self.floor_size,
                            texture=self.floor_texture)
        babylon.addObject(floor)
        self.objects['floor'] = floor
