"""
3D Visualization (BabylonJS) Example
=====================================

Demonstrates the BabylonWidget for 3D visualization inside the GUI:
  - Checkered floor with arena walls
  - Boxes, cylinders, and laser lines
  - Path drawing (polyline on the ground)
  - Point markers on the ground
  - Camera presets and animated transitions
  - Floor click interaction (place markers)
  - Object click interaction
  - Dynamic animation loop (orbiting objects)
  - GUI buttons to control the scene

Run from the `software/` directory:
    python -m extensions.gui.examples.babylon.babylon_example
"""

import math
import time

from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.sliders import SliderWidget
from extensions.gui.src.lib.objects.python.text import TextWidget
from extensions.libs.babylon.src.babylon import (
    BabylonVisualization,
    BabylonCamera,
    BabylonConfig,
    BabylonScene,
    BabylonLights,
)
from extensions.libs.babylon.src.lib.objects.box.box import Box, WallFancy
from extensions.libs.babylon.src.lib.objects.cylinder.cylinder import Cylinder
from extensions.libs.babylon.src.lib.objects.drawings.path import PathDrawing
from extensions.libs.babylon.src.lib.objects.drawings.points import PointsDrawing
from extensions.libs.babylon.src.lib.objects.floor.checkered_floor import CheckeredFloor
from extensions.libs.babylon.src.lib.objects.laser.laser import LaserLine

logger = Logger('babylon')


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    # Forward Python logs to the GUI terminal
    def _log_to_gui(log_entry, log, log_logger, level):
        text = f'[{log_logger.name}] {log}'
        color = [c / 255 for c in LOGGING_COLORS[level]]
        app.print(text, color=color)

    addLogRedirection(_log_to_gui, minimum_level='INFO')

    category = Category(id='babylon_demo', name='Babylon', icon='B')
    app.addCategory(category)

    page = Page(id='main', name='3D Scene')
    category.addPage(page, position=1)

    # =========================================================================
    # BabylonWidget + Visualization setup
    # =========================================================================
    babylon_widget = BabylonWidget(widget_id='babylon_view')

    babylon_config = BabylonConfig(
        camera=BabylonCamera(
            name='Default',
            target=[0, 0, 0],
            alpha=math.radians(-30),
            beta=math.radians(65),
            radius=4.0,
            fov=math.radians(60),
            radius_upper_limit=12.0,
        ),
        scene=BabylonScene(
            add_fog=True,
            fog_density=0.06,
        ),
        lights=BabylonLights(
            directional_shadows=True,
            directional_shadow_darkness=0.35,
        ),
        show_coordinate_system=True,
        coordinate_system_length=0.15,
    )
    babylon = BabylonVisualization(id='babylon', config=babylon_config)
    babylon_widget.set_babylon(babylon)

    page.addWidget(babylon_widget, row=1, column=1, width=30, height=16)

    # =========================================================================
    # Camera presets
    # =========================================================================
    cam_top = BabylonCamera(
        name='Top Down',
        target=[0, 0, 0],
        alpha=0,
        beta=math.radians(5),
        radius=5.0,
        radius_upper_limit=12.0,
    )
    cam_front = BabylonCamera(
        name='Front',
        target=[0, 0, 0.3],
        alpha=math.radians(-90),
        beta=math.radians(80),
        radius=3.5,
        radius_upper_limit=12.0,
    )
    cam_iso = BabylonCamera(
        name='Isometric',
        target=[0, 0, 0],
        alpha=math.radians(-45),
        beta=math.radians(55),
        radius=5.0,
        radius_upper_limit=12.0,
    )

    # =========================================================================
    # Floor and walls
    # =========================================================================
    floor = CheckeredFloor(
        'floor',
        tile_size=0.5,
        tiles_x=12,
        tiles_y=12,
        color1=[0.42, 0.42, 0.42],
        color2=[0.52, 0.52, 0.52],
        border_type='line',
        border_color=[0.35, 0.35, 0.35],
        border_width=0.02,
    )
    babylon.addObject(floor)

    # Arena walls
    arena_size = 2.5
    half = arena_size / 2
    wall_cfg = dict(length=arena_size, height=0.2, thickness=0.02,
                    texture='wood4.png', include_end_caps=True)
    for wall_id, x, y, angle in [
        ('wall_n', 0, half, 0),
        ('wall_s', 0, -half, 0),
        ('wall_e', half, 0, math.pi / 2),
        ('wall_w', -half, 0, math.pi / 2),
    ]:
        wall = WallFancy(wall_id, **wall_cfg)
        wall.setPosition(x=x, y=y)
        wall.setAngle(angle)
        babylon.addObject(wall)

    # =========================================================================
    # Static objects — boxes
    # =========================================================================
    red_box = Box('red_box', color=[0.85, 0.15, 0.1],
                  size={'x': 0.3, 'y': 0.3, 'z': 0.3})
    red_box.setPosition(x=-0.8, y=0.6, z=0.15)
    babylon.addObject(red_box)

    blue_box = Box('blue_box', color=[0.1, 0.3, 0.85],
                   size={'x': 0.5, 'y': 0.2, 'z': 0.15})
    blue_box.setPosition(x=0.7, y=-0.5, z=0.075)
    babylon.addObject(blue_box)

    green_box = Box('green_box', color=[0.15, 0.7, 0.2],
                    size={'x': 0.2, 'y': 0.2, 'z': 0.6})
    green_box.setPosition(x=-0.5, y=-0.8, z=0.3)
    babylon.addObject(green_box)

    # =========================================================================
    # Cylinders — pillars
    # =========================================================================
    pillar_positions = [(0.9, 0.9), (-0.9, -0.9), (0.9, -0.9), (-0.9, 0.9)]
    pillar_colors = [
        [0.7, 0.5, 0.2],
        [0.5, 0.2, 0.7],
        [0.2, 0.6, 0.6],
        [0.6, 0.6, 0.2],
    ]
    pillars = []
    for i, ((px, py), color) in enumerate(zip(pillar_positions, pillar_colors)):
        pillar = Cylinder(f'pillar_{i}', color=color, diameter=0.08,
                          height=0.5, tessellation=16)
        pillar.setPosition(x=px, y=py, z=0.25)
        babylon.addObject(pillar)
        pillars.append(pillar)

    # =========================================================================
    # Laser lines — connecting pillars
    # =========================================================================
    laser_h = 0.5  # height of the laser lines
    lasers = []
    laser_colors = [
        [1.0, 0.3, 0.3],
        [0.3, 1.0, 0.3],
        [0.3, 0.3, 1.0],
        [1.0, 1.0, 0.3],
    ]
    for i in range(4):
        j = (i + 1) % 4
        px1, py1 = pillar_positions[i]
        px2, py2 = pillar_positions[j]
        laser = LaserLine(f'laser_{i}', color=laser_colors[i], width=0.006,
                          glow_intensity=2.5,
                          start=[px1, py1, laser_h], end=[px2, py2, laser_h])
        babylon.addObject(laser)
        lasers.append(laser)

    # =========================================================================
    # Orbiting object (animated in the main loop)
    # =========================================================================
    orbiter = Box('orbiter', color=[1.0, 0.8, 0.1],
                  size={'x': 0.12, 'y': 0.12, 'z': 0.12})
    orbiter.setPosition(x=0.6, y=0, z=0.7)
    babylon.addObject(orbiter)

    orbit_trail = PathDrawing('orbit_trail',
                              pathColor=[1.0, 0.8, 0.2, 0.5],
                              pathWidth=0.008)
    babylon.addObject(orbit_trail)

    # =========================================================================
    # Path drawing — a star shape on the ground
    # =========================================================================
    star_path = PathDrawing('star_path',
                            pathColor=[0.3, 0.8, 1.0, 0.8],
                            pathWidth=0.012)
    # Generate star points
    star_points = []
    for i in range(11):
        angle = i * 2 * math.pi / 10
        r = 0.5 if i % 2 == 0 else 0.25
        star_points.append([r * math.cos(angle), r * math.sin(angle)])
    star_path.setPoints(star_points)
    babylon.addObject(star_path)

    # =========================================================================
    # Click markers — placed by double-clicking on the floor
    # =========================================================================
    click_markers = PointsDrawing('click_markers',
                                  fillColor=[1.0, 0.4, 0.1, 0.9],
                                  pointSize=0.04)
    babylon.addObject(click_markers)

    click_state = {'points': []}

    # =========================================================================
    # Info text panel
    # =========================================================================
    info_text = TextWidget(
        widget_id='info',
        text='Double-click floor to place markers\nClick objects to identify them',
        font_size=11,
        horizontal_alignment='left',
        vertical_alignment='top',
        text_color=[0.7, 0.85, 0.7],
    )
    page.addWidget(info_text, row=1, column=31, width=10, height=3)

    # =========================================================================
    # GUI controls
    # =========================================================================
    # Orbit speed slider
    speed_slider = SliderWidget(
        widget_id='orbit_speed',
        min_value=0, max_value=3.0, increment=0.1, value=1.0,
        color=[0.8, 0.6, 0.1], continuousUpdates=True,
        title='Orbit Speed',
    )
    page.addWidget(speed_slider, row=4, column=31, width=10, height=2)

    orbit_state = {'speed': 1.0, 'radius': 0.6, 'height': 0.7}

    def on_speed(value, *args, **kwargs):
        orbit_state['speed'] = value

    speed_slider.callbacks.value_changed.register(on_speed)

    # Orbit radius slider
    radius_slider = SliderWidget(
        widget_id='orbit_radius',
        min_value=0.2, max_value=1.2, increment=0.05, value=0.6,
        color=[0.3, 0.6, 0.8], continuousUpdates=True,
        title='Orbit Radius',
    )
    page.addWidget(radius_slider, row=6, column=31, width=10, height=2)

    def on_radius(value, *args, **kwargs):
        orbit_state['radius'] = value
        orbit_trail.clearPoints()

    radius_slider.callbacks.value_changed.register(on_radius)

    # Camera buttons
    btn_top = Button(widget_id='cam_top', text='Top View', color=[0.2, 0.35, 0.5])
    page.addWidget(btn_top, row=9, column=31, width=5, height=2)
    btn_top.callbacks.click.register(
        lambda *a, **kw: babylon.animate_camera(cam_top, duration=1.5))

    btn_front = Button(widget_id='cam_front', text='Front View', color=[0.2, 0.35, 0.5])
    page.addWidget(btn_front, row=9, column=36, width=5, height=2)
    btn_front.callbacks.click.register(
        lambda *a, **kw: babylon.animate_camera(cam_front, duration=1.5))

    btn_iso = Button(widget_id='cam_iso', text='Isometric', color=[0.2, 0.35, 0.5])
    page.addWidget(btn_iso, row=11, column=31, width=5, height=2)
    btn_iso.callbacks.click.register(
        lambda *a, **kw: babylon.animate_camera(cam_iso, duration=1.5))

    btn_follow = Button(widget_id='cam_follow', text='Follow Orbiter', color=[0.5, 0.35, 0.2])
    page.addWidget(btn_follow, row=11, column=36, width=5, height=2)
    btn_follow.callbacks.click.register(
        lambda *a, **kw: babylon.center_camera_on(orbiter))

    # Clear markers button
    btn_clear = Button(widget_id='clear_markers', text='Clear Markers', color=[0.5, 0.2, 0.2])
    page.addWidget(btn_clear, row=13, column=31, width=5, height=2)

    def clear_markers(*args, **kwargs):
        click_state['points'].clear()
        click_markers.clearPoints()
        logger.info('Cleared all floor markers')

    btn_clear.callbacks.click.register(clear_markers)

    # Clear trail button
    btn_clear_trail = Button(widget_id='clear_trail', text='Clear Trail', color=[0.4, 0.3, 0.15])
    page.addWidget(btn_clear_trail, row=13, column=36, width=5, height=2)

    def clear_trail(*args, **kwargs):
        orbit_trail.clearPoints()
        logger.info('Cleared orbit trail')

    btn_clear_trail.callbacks.click.register(clear_trail)

    # =========================================================================
    # Interaction callbacks
    # =========================================================================
    def on_floor_doubleclick(x, y, *args, **kwargs):
        click_state['points'].append([x, y])
        click_markers.setPoints(click_state['points'])
        logger.info(f'Marker placed at ({x:.2f}, {y:.2f})')
        info_text.updateConfig(
            text=f'Marker placed at ({x:.2f}, {y:.2f})\n'
                 f'Total markers: {len(click_state["points"])}')

    def on_object_click(object_id, *args, **kwargs):
        logger.info(f'Clicked object: {object_id}')
        info_text.updateConfig(text=f'Clicked: {object_id}')

    babylon.callbacks.floor_doubleclick.register(on_floor_doubleclick)
    babylon.callbacks.object_click.register(on_object_click)

    # =========================================================================
    # Start
    # =========================================================================
    babylon.start()

    # Add camera presets after start so the buttons appear in the viewer
    babylon.add_camera(cam_top)
    babylon.add_camera(cam_front)
    babylon.add_camera(cam_iso)

    app.start()

    # =========================================================================
    # Animation loop
    # =========================================================================
    t0 = time.time()
    trail_point_count = 0

    while True:
        t = time.time() - t0
        spd = orbit_state['speed']
        r = orbit_state['radius']
        h = orbit_state['height']

        # Orbit the golden box around the origin
        angle = spd * t
        ox = r * math.cos(angle)
        oy = r * math.sin(angle)
        orbiter.setPosition(x=ox, y=oy, z=h + 0.05 * math.sin(3 * angle))

        # Append trail point (limit to avoid unbounded growth)
        if spd > 0:
            orbit_trail.addPoint(ox, oy)
            trail_point_count += 1
            # Push trail update every 5 points for performance
            if trail_point_count % 5 == 0:
                orbit_trail.update()
            # Trim trail to last 500 points
            if len(orbit_trail._points) > 500:
                orbit_trail._points = orbit_trail._points[-300:]

        # Pulse laser glow by modulating alpha
        for i, laser in enumerate(lasers):
            pulse = 0.6 + 0.4 * math.sin(2 * t + i * math.pi / 2)
            laser.config['alpha'] = pulse
            laser.updateConfig()

        time.sleep(0.03)


if __name__ == '__main__':
    main()
