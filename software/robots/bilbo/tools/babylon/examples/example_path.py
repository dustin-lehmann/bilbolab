import math
import time

from extensions.libs.babylon.src.standalone import StandaloneBabylon
from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.libs.babylon.src.lib.objects.drawings.path import PathDrawing
from extensions.libs.babylon.src.lib.objects.drawings.points import PointsDrawing
from robots.bilbo.utilities.babylon.scenarios.lab import LabScenario


if __name__ == '__main__':

    scenario = LabScenario(size=3, texture_1='carpet_blue.png', texture_2='carpet_dark.png')
    babylon = StandaloneBabylon(title="Path Drawing Example", ws_port=9000, http_port=9200,
                                scenario=scenario)
    babylon.start()

    robot = BabylonBilbo('bilbo1', color=[0.7, 0.1, 0.1], text='1')
    babylon.addObject(robot)

    path = PathDrawing('robot_path', pathColor=[1, 0.3, 0.1, 0.4], pathWidth=0.008)
    babylon.addObject(path)

    # Waypoints: blue dots along the trajectory
    waypoints = PointsDrawing('waypoints',
                              fillColor=[0.2, 0.5, 1.0, 0.5],
                              pointSize=0.04)
    babylon.addObject(waypoints)
    for i in range(12):
        t_wp = i * (2 * math.pi / 0.3) / 12
        waypoints.addPoint(1.0 * math.sin(0.3 * t_wp), 1.0 * math.sin(0.5 * t_wp))
    waypoints.update()

    # Start marker: large green dot at origin
    markers = PointsDrawing('markers',
                            fillColor=[0.1, 0.8, 0.2, 0.4],
                            pointSize=0.08)
    babylon.addObject(markers)
    markers.setPoints([[0, 0]])

    # Obstacles: small red dots scattered around the arena
    obstacles = PointsDrawing('obstacles',
                              fillColor=[1.0, 0.15, 0.1, 0.6],
                              pointSize=0.025)
    babylon.addObject(obstacles)
    obstacles.setPoints([
        [0.6, 0.8], [-0.5, 0.9], [0.9, -0.7],
        [-0.8, -0.5], [-0.3, -0.9], [0.7, 0.2],
    ])

    t0 = time.time()
    last_path_update = 0
    try:
        while True:
            t = time.time() - t0
            # Lissajous figure covering the arena
            x = 1.0 * math.sin(0.3 * t)
            y = 1.0 * math.sin(0.5 * t)
            theta = math.atan2(0.5 * math.cos(0.5 * t), 0.3 * math.cos(0.3 * t))
            robot.set_state(
                x=x, y=y,
                theta=theta,
                psi=0.04 * math.sin(3 * t),
            )
            path.addPoint(x, y)
            # Push path to frontend every 0.25s
            if t - last_path_update > 0.25:
                path.update()
                last_path_update = t
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        babylon.close()
