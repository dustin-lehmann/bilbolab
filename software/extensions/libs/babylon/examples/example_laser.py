import math
import time

import numpy as np

from extensions.libs.babylon.src.standalone import StandaloneBabylon
from extensions.libs.babylon.src.scenarios import ArenaScenario
from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.libs.babylon.src.lib.objects.laser.laser import LaserLine


def example_laser():
    """Three orbiting BILBOs connected by laser lines that form a rotating triangle."""

    scenario = ArenaScenario(size=3)
    babylon = StandaloneBabylon(title="Laser Line Demo", ws_port=9000, http_port=9200,
                                scenario=scenario)
    babylon.start()

    # Three BILBOs
    robots = [
        BabylonBilbo('bilbo1', color=[0.7, 0.1, 0.1], text='1'),
        BabylonBilbo('bilbo2', color=[0.1, 0.5, 0.8], text='2'),
        BabylonBilbo('bilbo3', color=[0.2, 0.65, 0.2], text='3'),
    ]
    for robot in robots:
        babylon.addObject(robot)

    # Laser lines connecting each pair — forms a triangle
    laser_height = 0.12
    lasers = [
        LaserLine('laser_12', color=[1, 0.2, 0.2], width=0.005, glow_intensity=2.5,
                  start=[0, 0, laser_height], end=[1, 0, laser_height]),
        LaserLine('laser_23', color=[0.2, 0.5, 1], width=0.005, glow_intensity=2.5,
                  start=[0, 0, laser_height], end=[0, 1, laser_height]),
        LaserLine('laser_31', color=[0.2, 0.9, 0.3], width=0.005, glow_intensity=2.5,
                  start=[0, 0, laser_height], end=[0, 0, laser_height]),
    ]
    for laser in lasers:
        babylon.addObject(laser)

    # Orbit parameters
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

            # Update robot positions
            positions = []
            for robot, orbit in zip(robots, orbits):
                angle = orbit['speed'] * t + orbit['phase']
                x = orbit['radius'] * math.cos(angle)
                y = orbit['radius'] * math.sin(angle)
                theta = angle + (math.pi / 2 if orbit['speed'] > 0 else -math.pi / 2)
                psi = 0.05 * math.sin(3 * t + orbit['phase'])
                robot.set_state(x=x, y=y, theta=theta, psi=psi)
                positions.append((x, y))

            # Update laser endpoints to connect the robots
            pairs = [(0, 1), (1, 2), (2, 0)]
            for laser, (i, j) in zip(lasers, pairs):
                laser.setPoints(
                    start=[positions[i][0], positions[i][1], laser_height],
                    end=[positions[j][0], positions[j][1], laser_height],
                )

            time.sleep(dt)
    except KeyboardInterrupt:
        pass
    finally:
        babylon.close()


if __name__ == '__main__':
    example_laser()
