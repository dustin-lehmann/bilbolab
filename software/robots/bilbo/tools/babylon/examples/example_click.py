import time

from extensions.libs.babylon.src.standalone import StandaloneBabylon
from extensions.libs.babylon.src.lib.objects.drawings.path import PathDrawing
from extensions.libs.babylon.src.lib.objects.drawings.points import PointsDrawing
from robots.bilbo.utilities.babylon.scenarios.lab import LabScenario


if __name__ == '__main__':

    scenario = LabScenario(size=3, texture_1='carpet_blue.png', texture_2='carpet_dark.png')
    babylon = StandaloneBabylon(title="Click Example", ws_port=9000, http_port=9200,
                                scenario=scenario)
    babylon.start()

    # Double-click: place blue waypoints connected by a path
    waypoints = PointsDrawing('waypoints', fillColor=[0.2, 0.5, 1.0, 0.7], pointSize=0.04)
    babylon.addObject(waypoints)

    waypoint_path = PathDrawing('waypoint_path', pathColor=[0.2, 0.5, 1.0, 0.4], pathWidth=0.008)
    babylon.addObject(waypoint_path)

    # Right-click: place red waypoints connected by a wider red path
    red_points = PointsDrawing('red_points', fillColor=[1.0, 0.15, 0.1, 0.7], pointSize=0.04)
    babylon.addObject(red_points)

    red_path = PathDrawing('red_path', pathColor=[1.0, 0.15, 0.1, 0.4], pathWidth=0.02)
    babylon.addObject(red_path)

    def on_doubleclick(x, y):
        print(f"Double-click at ({x:.3f}, {y:.3f})")
        waypoints.addPoint(x, y)
        waypoints.update()
        waypoint_path.addPoint(x, y)
        waypoint_path.update()

    def on_rightclick(x, y):
        print(f"Right-click at ({x:.3f}, {y:.3f})")
        red_points.addPoint(x, y)
        red_points.update()
        red_path.addPoint(x, y)
        red_path.update()

    def on_middleclick(x, y):
        print("Middle-click: clearing all")
        waypoints.clearPoints()
        waypoint_path.clearPoints()
        red_points.clearPoints()
        red_path.clearPoints()

    babylon.callbacks.floor_doubleclick.register(on_doubleclick)
    babylon.callbacks.floor_rightclick.register(on_rightclick)
    babylon.callbacks.floor_middleclick.register(on_middleclick)

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        babylon.close()
