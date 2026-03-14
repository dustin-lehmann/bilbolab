import math
import os
import threading
import time

import numpy as np

from core.utils.video.video import webm_to_mp4
from extensions.libs.babylon.src.standalone import StandaloneBabylon
from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.libs.babylon.src.lib.objects.box.box import Box, WallFancy

RECORD_DELAY = 10   # seconds before recording starts
RECORD_DURATION = 10  # seconds of recording
SAVE_PATH = os.path.expanduser("~/Desktop/bilbo_recording.webm")


def example_record():
    """Same scene as example_simple, but records a 30-second video after a 10-second warm-up."""

    babylon = StandaloneBabylon(title="BILBO Recording Demo", ws_port=9000, http_port=9200)
    babylon.start()

    # Event to signal that the file has been written
    save_done = threading.Event()
    babylon.callbacks.recording_saved.register(lambda path: save_done.set())

    # Floor
    floor = SimpleFloor('floor', size_x=10, size_y=10, texture='floor_bright.png')
    babylon.addObject(floor)

    # Walled arena (3x3 m)
    wall_length = 3
    walls = [
        ('wall_north', {'y': wall_length / 2}),
        ('wall_south', {'y': -wall_length / 2}),
        ('wall_east',  {'x': wall_length / 2, 'angle': np.pi / 2}),
        ('wall_west',  {'x': -wall_length / 2, 'angle': np.pi / 2}),
    ]
    for wall_id, props in walls:
        wall = WallFancy(wall_id, length=wall_length, texture='wood4.png', include_end_caps=True)
        wall.setPosition(x=props.get('x', 0), y=props.get('y', 0))
        if 'angle' in props:
            wall.setAngle(props['angle'])
        babylon.addObject(wall)

    # Three BILBOs
    robots = [
        BabylonBilbo('bilbo1', color=[0.7, 0.1, 0.1], text='1'),
        BabylonBilbo('bilbo2', color=[0.1, 0.5, 0.8], text='2'),
        BabylonBilbo('bilbo3', color=[0.2, 0.65, 0.2], text='3'),
    ]
    for robot in robots:
        babylon.addObject(robot)

    # Center marker
    marker = Box('marker', size={'x': 0.08, 'y': 0.08, 'z': 0.08}, color=[1, 0.8, 0.2])
    babylon.addObject(marker)
    marker.setPosition(z=0.04)

    # Orbit parameters
    orbits = [
        {'radius': 0.5, 'speed': 0.8,  'phase': 0},
        {'radius': 0.9, 'speed': -0.5, 'phase': 2 * np.pi / 3},
        {'radius': 1.2, 'speed': 0.3,  'phase': 4 * np.pi / 3},
    ]

    recording_started = False
    recording_stopped = False
    t0 = time.time()
    dt = 0.02

    print(f"Recording will start in {RECORD_DELAY}s, run for {RECORD_DURATION}s, and save to {SAVE_PATH}")

    try:
        while True:
            t = time.time() - t0

            # Update robot positions
            for robot, orbit in zip(robots, orbits):
                angle = orbit['speed'] * t + orbit['phase']
                x = orbit['radius'] * math.cos(angle)
                y = orbit['radius'] * math.sin(angle)
                theta = angle + (math.pi / 2 if orbit['speed'] > 0 else -math.pi / 2)
                psi = 0.05 * math.sin(3 * t + orbit['phase'])
                robot.set_state(x=x, y=y, theta=theta, psi=psi)

            # Start recording after delay
            if not recording_started and t >= RECORD_DELAY:
                print(f"[{t:.1f}s] Starting recording...")
                babylon.start_recording(save_path=SAVE_PATH, fps=60, bitrate=12_000_000)
                recording_started = True

            # Stop recording after duration
            if recording_started and not recording_stopped and t >= RECORD_DELAY + RECORD_DURATION:
                print(f"[{t:.1f}s] Stopping recording... waiting for data transfer")
                babylon.stop_recording()
                recording_stopped = True

            # Wait for the file to actually be saved, or timeout after 60s
            if recording_stopped:
                if save_done.wait(timeout=0.02):
                    print(f"Recording saved to {SAVE_PATH}")
                    break
                if t >= RECORD_DELAY + RECORD_DURATION + 60:
                    print("Timed out waiting for recording data.")
                    break

            time.sleep(dt)
    except KeyboardInterrupt:
        if recording_started and not recording_stopped:
            babylon.stop_recording()
    finally:
        babylon.close()

    # Convert .webm to .mp4
    if os.path.isfile(SAVE_PATH):
        print("Converting to MP4...")
        mp4_path = webm_to_mp4(SAVE_PATH)
        print(f"Done. MP4 saved to {mp4_path}")


if __name__ == '__main__':
    example_record()
