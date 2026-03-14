import time

from extensions.libs.babylon.src.standalone import StandaloneBabylon
from extensions.libs.babylon.src.babylon import BabylonConfig, BabylonLights, BabylonCamera
from extensions.libs.babylon.src.scenarios import EmptyScenario
from extensions.libs.babylon.src.lib.objects.box.box import Box


def example_light():
    """Standalone scene with a cube and custom lights to verify light helper visualization."""

    lights = BabylonLights(
        hemispheric_direction=[0.5, 0.5, 1],
        hemispheric_intensity=0.7,
        hemispheric_ground_color=[0.3, 0.3, 0.3],
        directional_direction=[-1, -1, -1],
        directional_position=[3, 3, 5],
        directional_intensity=0.8,
        directional2_direction=[1, -1, -1],
        directional2_position=[-3, 2, 4],
        directional2_intensity=0.0,
    )

    camera = BabylonCamera(
        target=[0, 0, 0.5],
        radius=8,
    )

    config = BabylonConfig(
        lights=lights,
        camera=camera,
        show_coordinate_system=True,
    )

    scenario = EmptyScenario(floor_size=10, fog=False)
    babylon = StandaloneBabylon(
        title="Light Test",
        ws_port=9000,
        http_port=9200,
        babylon_config=config,
        scenario=scenario,
    )
    babylon.start()

    # A cube in the center so we can see how lights hit it
    cube = Box('cube', size={'x': 0.6, 'y': 0.6, 'z': 0.6}, color=[0.8, 0.8, 0.8])
    babylon.addObject(cube)
    cube.setPosition(z=0.3, x=1, y=1)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        babylon.close()


if __name__ == '__main__':
    example_light()
