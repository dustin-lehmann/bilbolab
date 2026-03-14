import math
import time

import numpy as np

from extensions.libs.babylon.src.standalone import StandaloneBabylon
from extensions.libs.babylon.src.scenarios import ArenaScenario
from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.libs.babylon.src.lib.objects.box.box import Box


def example_standalone():
    """Standalone BabylonJS visualization with three BILBOs driving in circles inside a walled arena."""

    # Create and start the standalone visualization (opens browser automatically)
    scenario = ArenaScenario(size=3)
    babylon = StandaloneBabylon(title="BILBO Standalone Demo", ws_port=9000, http_port=9200,
                                scenario=scenario)
    babylon.start()

    # Three BILBOs with distinct colors
    robots = [
        BabylonBilbo('bilbo1', color=[0.7, 0.1, 0.1], text='1'),
        BabylonBilbo('bilbo2', color=[0.1, 0.5, 0.8], text='2'),
        BabylonBilbo('bilbo3', color=[0.2, 0.65, 0.2], text='3'),
    ]
    for robot in robots:
        babylon.addObject(robot)

    # A small marker box in the center
    marker = Box('marker', size={'x': 0.08, 'y': 0.08, 'z': 0.08}, color=[1, 0.8, 0.2])
    babylon.addObject(marker)
    marker.setPosition(z=0.04)

    # Animate: each BILBO orbits the center at a different radius and speed
    orbits = [
        {'radius': 0.5, 'speed': 0.8,  'phase': 0},
        {'radius': 0.9, 'speed': -0.5, 'phase': 2 * np.pi / 3},
        {'radius': 1.2, 'speed': 0.3,  'phase': 4 * np.pi / 3},
    ]

    t0 = time.time()
    dt = 0.02

    try:
        while True:
            t = time.time() - t0
            for robot, orbit in zip(robots, orbits):
                angle = orbit['speed'] * t + orbit['phase']
                x = orbit['radius'] * math.cos(angle)
                y = orbit['radius'] * math.sin(angle)
                # theta = heading tangent to the circle
                theta = angle + (math.pi / 2 if orbit['speed'] > 0 else -math.pi / 2)
                # gentle rocking psi (pitch) for visual flair
                psi = 0.05 * math.sin(3 * t + orbit['phase'])
                robot.set_state(x=x, y=y, theta=theta, psi=psi)

            time.sleep(dt)
    except KeyboardInterrupt:
        pass
    finally:
        babylon.close()


if __name__ == '__main__':
    example_standalone()
