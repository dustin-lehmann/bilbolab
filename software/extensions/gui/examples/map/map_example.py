"""
Map Visualization Example
=========================

Demonstrates the 2D MapWidget with:
  - Static objects: points, circles, rectangles
  - Grouped waypoints connected by dashed lines
  - Moving agents: regular Agent and VisionAgent (with FOV cone)
  - Animated path following and orbital motion

Run from the `software/` directory:
    python -m extensions.gui.examples.map.map_example
"""

import math
import time

from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.map.map import MapWidget
from extensions.gui.src.lib.map.map_objects import (
    Point,
    Circle,
    Rectangle,
    Agent,
    VisionAgent,
    Line,
    MapObjectGroup,
)


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    category = Category(id='map_demo', name='Map', icon='M')
    app.addCategory(category)

    page = Page(id='map_page', name='Map')
    category.addPage(page, position=1)

    # =========================================================================
    # Map widget — 3 m x 3 m area
    # =========================================================================
    map_widget = MapWidget(
        widget_id='demo_map',
        limits={'x': [-1, 4], 'y': [-1, 4]},
        origin=[0, 0],
        tiles=True,
        tile_size=0.5,
        show_grid=True,
        major_grid_size=1,
        minor_grid_size=0.5,
        initial_display_center=[1.5, 1.5],
        initial_display_zoom=0.85,
    )
    page.addWidget(map_widget, row=1, column=1, width=18, height=18)

    the_map = map_widget.map

    # --- Static objects: corner markers --------------------------------------
    corners = [(0, 0, 'Origin'), (3, 0, '(3,0)'), (3, 3, '(3,3)'), (0, 3, '(0,3)')]
    for i, (x, y, name) in enumerate(corners):
        the_map.addObject(Point(
            f'corner_{i}', x=x, y=y,
            color=[1, 1, 1, 0.6], size=0.04, name=name))

    # Obstacle rectangle
    the_map.addObject(Rectangle(
        'obstacle', x=1.8, y=0.5, width=0.6, height=0.4,
        color=[0.8, 0.2, 0.1, 0.4], border_color=[0.8, 0.2, 0.1, 0.8],
        border_width=2, name='Obstacle'))

    # Target zone circle
    the_map.addObject(Circle(
        'target_zone', x=2.5, y=2.5, radius=0.3,
        color=[0.1, 0.7, 0.2, 0.15], border_color=[0.1, 0.7, 0.2, 0.5],
        border_width=2, name='Target'))

    # --- Waypoints group with connecting lines -------------------------------
    wp_group = MapObjectGroup('waypoints', name='Waypoints')
    the_map.addGroup(wp_group)

    wp_positions = [(0.5, 0.5), (1.0, 1.5), (1.5, 2.5), (2.5, 2.5)]
    for i, (wx, wy) in enumerate(wp_positions):
        wp_group.addObject(Point(
            f'wp{i}', x=wx, y=wy,
            color=[1, 0.8, 0, 0.8], size=0.035,
            shape='diamond', name=f'WP{i}', border_width=0))

    for i in range(len(wp_positions) - 1):
        wp_a = wp_group.objects[f'wp{i}']
        wp_b = wp_group.objects[f'wp{i + 1}']
        wp_group.addObject(Line(
            f'path_{i}_{i+1}', start=wp_a, end=wp_b,
            color=[1, 0.8, 0, 0.3], width=2, style='dashed', show_name=False))

    # --- Moving agents -------------------------------------------------------
    agent_a = Agent(
        'robot_a', x=0.5, y=0.5, psi=0,
        color=[0, 0.7, 0.9, 1], size=0.07, name='Robot A')
    the_map.addObject(agent_a)

    agent_b = VisionAgent(
        'robot_b', x=2.0, y=1.0, psi=math.pi / 2,
        color=[0.9, 0.4, 0.1, 1], size=0.07, name='Robot B',
        fov=math.pi / 3, vision_radius=0.6)
    the_map.addObject(agent_b)

    # --- Start ---------------------------------------------------------------
    app.start()

    # --- Animation loop (20 Hz) ----------------------------------------------
    t0 = time.time()
    path = wp_positions
    speed = 0.3  # m/s

    # Pre-compute path segment lengths
    segments = []
    total_len = 0
    for i in range(len(path) - 1):
        dx = path[i + 1][0] - path[i][0]
        dy = path[i + 1][1] - path[i][1]
        seg_len = math.hypot(dx, dy)
        segments.append((path[i], path[i + 1], seg_len))
        total_len += seg_len

    while True:
        t = time.time() - t0

        # Robot A: follows waypoint path in a loop
        progress = (t * speed) % total_len
        acc = 0
        for (sx, sy), (ex, ey), seg_len in segments:
            if acc + seg_len >= progress:
                frac = (progress - acc) / seg_len
                ax = sx + frac * (ex - sx)
                ay = sy + frac * (ey - sy)
                apsi = math.atan2(ey - sy, ex - sx)
                break
            acc += seg_len
        else:
            ax, ay, apsi = path[-1][0], path[-1][1], 0

        agent_a.update({'x': ax, 'y': ay, 'psi': apsi})

        # Robot B: orbits around map centre
        cx, cy = 1.5, 1.5
        orbit_r = 1.0
        omega = 0.4
        bx = cx + orbit_r * math.cos(omega * t)
        by = cy + orbit_r * math.sin(omega * t)
        bpsi = omega * t + math.pi / 2
        agent_b.update({'x': bx, 'y': by, 'psi': bpsi})

        time.sleep(0.05)


if __name__ == '__main__':
    main()
