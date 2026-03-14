"""
Example: Camera Follow
======================
Demonstrates the object_click callback and center_camera_on() follow feature.

- Three robots orbit at different speeds
- Click on any robot in the 3D view → the backend receives the click event
  and tells the camera to follow that robot
- A green "Following: ..." badge appears in the top bar
- Click the badge (or any camera preset) to stop following
"""

import math
import time

import numpy as np

from extensions.libs.babylon.src.babylon import BabylonCamera
from extensions.libs.babylon.src.standalone import StandaloneBabylon
from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from robots.bilbo.utilities.babylon.scenarios.lab import LabScenario


def main():
    # --- Setup ---
    scenario = LabScenario(size=3)
    babylon = StandaloneBabylon(
        title="Camera Follow Demo",
        ws_port=9000,
        http_port=9200,
        scenario=scenario,
    )
    babylon.start()

    # Add some camera presets so we can test that they stop following
    babylon.add_camera(BabylonCamera(name="Overview", target=[0, 0, 0], alpha=-0.3, beta=1.2, radius=4.0))
    babylon.add_camera(BabylonCamera(name="Top Down", target=[0, 0, 0], alpha=0, beta=0.1, radius=5.0))

    # --- Robots ---
    robots = {
        'bilbo1': BabylonBilbo('bilbo1', color=[0.7, 0.1, 0.1], text='1'),
        'bilbo2': BabylonBilbo('bilbo2', color=[0.1, 0.5, 0.8], text='2'),
        'bilbo3': BabylonBilbo('bilbo3', color=[0.2, 0.65, 0.2], text='3'),
    }
    for robot in robots.values():
        babylon.addObject(robot)

    # --- Object click callback ---
    # Object IDs arrive as full UIDs, e.g. "babylon/bilbo1"
    robot_uids = {f"babylon/{rid}" for rid in robots}

    def on_object_click(object_id):
        print(f"\n{'='*50}")
        print(f"  CLICK EVENT received from JS")
        print(f"  Object: {object_id}")
        print(f"{'='*50}")

        if object_id in robot_uids:
            print(f"  → Calling center_camera_on('{object_id}')")
            babylon.center_camera_on(object_id)
            print(f"  → Camera is now following {object_id}")
        else:
            print(f"  → Not a robot, ignoring")

    babylon.callbacks.object_click.register(on_object_click)
    print("\n  Registered object_click callback")
    print("  Click on any robot in the 3D view to follow it!")
    print("  Click the green badge or a camera button to stop.\n")

    # --- Animation loop ---
    orbits = [
        {'radius': 0.5, 'speed': 0.8, 'phase': 0},
        {'radius': 0.9, 'speed': -0.5, 'phase': 2 * np.pi / 3},
        {'radius': 1.2, 'speed': 0.3, 'phase': 4 * np.pi / 3},
    ]

    t0 = time.time()
    dt = 0.02

    try:
        while True:
            t = time.time() - t0
            for (name, robot), orbit in zip(robots.items(), orbits):
                angle = orbit['speed'] * t + orbit['phase']
                x = orbit['radius'] * math.cos(angle)
                y = orbit['radius'] * math.sin(angle)
                theta = angle + (math.pi / 2 if orbit['speed'] > 0 else -math.pi / 2)
                psi = 0.05 * math.sin(3 * t + orbit['phase'])
                robot.set_state(x=x, y=y, theta=theta, psi=psi)

            time.sleep(dt)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        babylon.close()


if __name__ == '__main__':
    main()
