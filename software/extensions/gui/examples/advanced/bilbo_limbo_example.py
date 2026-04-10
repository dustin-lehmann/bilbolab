"""
BILBO Limbo Widget Example
===========================

Demonstrates the BilboLimboWidget — a specialised 2D scene renderer
for visualising BILBO robots ducking under obstacles:
  - Page 1: Limbo bar scene with a single robot
  - Page 2: Multi-robot layouts (small, medium, tall, course)
  - Page 3: Dynamic scene with live trajectory, labels, and obstacles

All scenes are animated in a single 20 Hz main loop.

Run from the `software/` directory:
    python -m extensions.gui.examples.advanced.bilbo_limbo_example
"""

import math
import time

from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.bilbo_limbo import BilboLimboWidget, LimboBilboConfig


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    category = Category(id='limbo', name='Limbo', icon='L')
    app.addCategory(category)

    # =========================================================================
    # Page 1: Limbo bar scene
    # =========================================================================
    page1 = Page(id='limbo', name='Limbo Bar')
    category.addPage(page1, position=1)

    limbo = BilboLimboWidget(
        widget_id='limbo_scene',
        x_range=[-0.8, 0.8],
        show_grid=True,
        grid_spacing=0.1,
    )
    page1.addWidget(limbo, row=1, column=1, width=50, height=10)

    # =========================================================================
    # Page 2: Multi-robot layouts
    # =========================================================================
    page2 = Page(id='multi', name='Multi-Robot')
    category.addPage(page2, position=2)

    small = BilboLimboWidget(
        widget_id='small_view', x_range=[-0.2, 0.2],
        background_color=[0.12, 0.12, 0.18])
    page2.addWidget(small, row=1, column=1, width=12, height=9)

    medium = BilboLimboWidget(
        widget_id='medium_view', x_range=[-0.5, 0.5],
        show_grid=True, grid_spacing=0.05,
        background_color=[0.1, 0.14, 0.2])
    page2.addWidget(medium, row=1, column=13, width=20, height=9)

    tall = BilboLimboWidget(
        widget_id='tall_view', x_range=[-0.25, 0.25],
        show_grid=True, grid_spacing=0.05,
        background_color=[0.15, 0.1, 0.15])
    page2.addWidget(tall, row=1, column=33, width=10, height=18)

    course = BilboLimboWidget(
        widget_id='course_view', x_range=[-1.5, 1.5],
        show_grid=True, grid_spacing=0.2,
        floor_color=[0.75, 0.75, 0.7], floor_edge_color=[0.3, 0.3, 0.25],
        background_color=[0.18, 0.18, 0.22])
    page2.addWidget(course, row=10, column=1, width=32, height=9)

    # =========================================================================
    # Page 3: Dynamic scene with trajectory
    # =========================================================================
    page3 = Page(id='showcase', name='Dynamic Scene')
    category.addPage(page3, position=3)

    dynamic = BilboLimboWidget(
        widget_id='dynamic_view', x_range=[-1.0, 1.0],
        show_grid=True, grid_spacing=0.1)
    page3.addWidget(dynamic, row=1, column=1, width=50, height=14)

    # --- Start GUI -----------------------------------------------------------
    app.start()

    # =========================================================================
    # Populate scenes
    # =========================================================================

    # Page 1: Robot + limbo bar
    limbo.add_bilbo('robot', config=LimboBilboConfig(body_color=[0.3, 0.5, 0.9]),
                    state={'x': -0.5, 'theta': 0.0})
    bar_y = 0.18
    limbo.add_rectangle('post_l', x=-0.22, y=0.0, width=0.015, height=bar_y,
                        color=[0.55, 0.55, 0.55], edge_color=[0.3, 0.3, 0.3])
    limbo.add_rectangle('post_r', x=0.205, y=0.0, width=0.015, height=bar_y,
                        color=[0.55, 0.55, 0.55], edge_color=[0.3, 0.3, 0.3])
    limbo.add_rectangle('bar', x=-0.22, y=bar_y, width=0.44, height=0.015,
                        color=[0.95, 0.8, 0.15], edge_color=[0.7, 0.55, 0.05], edge_width=1.5)
    limbo.set_label('left', 'Limbo Bar', color=[1, 1, 1], font_size=16, font_weight='bold')
    limbo.set_label('right', 'h = 0.18 m', color=[0.9, 0.8, 0.2], font_size=13)

    ref_xs = [round(-0.5 + i * 0.01, 3) for i in range(116)]
    ref_ys = [round(0.06, 3)] * len(ref_xs)
    limbo.add_path('ref_path', x=ref_xs, y=ref_ys,
                   color=[0.5, 0.5, 0.5], width=1.5, dash=[6, 4], opacity=0.5)

    # Page 2: Multi-robot
    small.add_bilbo('solo', config=LimboBilboConfig(body_color=[0.9, 0.35, 0.25]),
                    state={'x': 0.0, 'theta': 0.0})
    small.set_label('left', 'Solo', color=[0.9, 0.35, 0.25], font_size=11, font_weight='bold')

    medium.add_bilbo('blue', config=LimboBilboConfig(body_color=[0.25, 0.45, 0.85]),
                     state={'x': -0.2, 'theta': 0.0})
    medium.add_bilbo('green', config=LimboBilboConfig(body_color=[0.2, 0.75, 0.35]),
                     state={'x': 0.2, 'theta': 0.0})
    medium.add_circle('ball', x=0.0, y=0.1, radius=0.035,
                      color=[0.9, 0.5, 0.1], edge_color=[0.6, 0.3, 0.05])
    medium.set_label('left', 'Dual', color=[1, 1, 1], font_size=11, font_weight='bold')

    tall.add_bilbo('climber', config=LimboBilboConfig(body_color=[0.7, 0.3, 0.8]),
                   state={'x': 0.0, 'theta': 0.0})
    for i, h in enumerate([0.08, 0.16, 0.24]):
        w = 0.18 - i * 0.04
        tall.add_rectangle(f'bar_{i}', x=-w / 2, y=h, width=w, height=0.012,
                           color=[0.4 + i * 0.2, 0.4 + i * 0.15, 0.2],
                           edge_color=[0.3, 0.3, 0.2])

    course.add_bilbo('r1', config=LimboBilboConfig(body_color=[0.85, 0.25, 0.25]),
                     state={'x': -1.0, 'theta': 0.0})
    course.add_bilbo('r2', config=LimboBilboConfig(body_color=[0.25, 0.7, 0.25]),
                     state={'x': 0.0, 'theta': 0.0})
    course.add_bilbo('r3', config=LimboBilboConfig(body_color=[0.25, 0.4, 0.9]),
                     state={'x': 1.0, 'theta': 0.0})
    course.add_rectangle('wall1', x=-0.52, y=0.0, width=0.03, height=0.22,
                         color=[0.5, 0.5, 0.55], edge_color=[0.3, 0.3, 0.3])
    course.add_rectangle('wall2', x=0.49, y=0.0, width=0.03, height=0.22,
                         color=[0.5, 0.5, 0.55], edge_color=[0.3, 0.3, 0.3])
    course.add_rectangle('low_bar', x=-0.52, y=0.15, width=1.04, height=0.012,
                         color=[0.9, 0.7, 0.1], edge_color=[0.6, 0.4, 0.05])
    for i, cx in enumerate([-0.8, -0.3, 0.25, 0.75]):
        course.add_circle(f'bump_{i}', x=cx, y=0.04, radius=0.04,
                          color=[0.6, 0.35, 0.15, 0.8], edge_color=[0.4, 0.2, 0.1])
    course.set_label('left', 'Course', color=[1, 1, 1], font_size=12, font_weight='bold')
    course.set_label('right', '3 robots', color=[0.7, 0.7, 0.7], font_size=11)

    # Page 3: Dynamic scene
    dynamic.add_bilbo('main', config=LimboBilboConfig(body_color=[0.3, 0.6, 0.9]),
                      state={'x': 0.0, 'theta': 0.0})
    ref_xs_d = [round(-0.8 + i * 0.016, 3) for i in range(101)]
    ref_ys_d = [round(0.06, 3)] * len(ref_xs_d)
    dynamic.add_path('ref', x=ref_xs_d, y=ref_ys_d,
                     color=[0.4, 0.4, 0.5], width=1.5, dash=[6, 4], opacity=0.4)
    dynamic.add_path('trail', x=[], y=[], gradient=True,
                     gradient_start_color=[0.2, 0.4, 0.8, 0.1],
                     gradient_end_color=[0.3, 0.9, 1.0, 1.0], width=2.5)
    dynamic.set_label('left', 'Dynamic Scene', color=[1, 1, 1], font_size=16, font_weight='bold')

    # =========================================================================
    # Animation loop
    # =========================================================================
    t0 = time.time()
    next_obstacle_time = 3.0
    obstacle_idx = 0
    dynamic_obstacles = []
    trail_x, trail_y = [], []
    trail_max = 200

    while True:
        t = time.time() - t0

        # Page 1: Limbo robot
        limbo_x = -0.5 + 0.65 * (0.5 + 0.5 * math.sin(0.35 * t - math.pi / 2))
        dist = abs(limbo_x)
        lean = 0.4 * math.exp(-(dist / 0.15) ** 2) * math.copysign(1, math.cos(0.35 * t))
        limbo.update_bilbo('robot', x=limbo_x, theta=lean)

        # Page 2: Animations
        small.update_bilbo('solo', theta=0.2 * math.sin(1.5 * t))
        medium.update_bilbo('blue', x=-0.2 + 0.08 * math.sin(0.6 * t),
                            theta=0.15 * math.sin(t))
        medium.update_bilbo('green', x=0.2 - 0.08 * math.sin(0.6 * t),
                            theta=-0.15 * math.sin(t))
        tall.update_bilbo('climber', theta=0.5 * math.sin(0.8 * t))
        course.update_bilbo('r1', x=-1.0 + 0.4 * math.sin(0.5 * t),
                            theta=0.2 * math.sin(0.5 * t))
        course.update_bilbo('r2', x=0.3 * math.sin(0.3 * t),
                            theta=0.25 * math.sin(0.7 * t))
        course.update_bilbo('r3', x=1.0 - 0.4 * math.sin(0.4 * t + 1),
                            theta=-0.2 * math.sin(0.6 * t))

        # Page 3: Dynamic scene
        main_x = 0.5 * math.sin(0.4 * t)
        dynamic.update_bilbo('main', x=main_x, theta=0.3 * math.sin(0.8 * t))

        trail_x.append(main_x)
        trail_y.append(0.06 + 0.03 * math.sin(0.8 * t))
        if len(trail_x) > trail_max:
            trail_x[:] = trail_x[-trail_max:]
            trail_y[:] = trail_y[-trail_max:]
        dynamic.update_path('trail', x=trail_x, y=trail_y)
        dynamic.set_label('right', f'x = {main_x:+.2f} m',
                          color=[0.6, 0.9, 1.0], font_size=13, font_family='monospace')

        if t >= next_obstacle_time:
            if len(dynamic_obstacles) >= 5:
                dynamic.remove_rectangle(dynamic_obstacles.pop(0))
            oid = f'obs_{obstacle_idx}'
            ox = 0.7 * math.sin(obstacle_idx * 1.7)
            oy = 0.05 + 0.12 * abs(math.sin(obstacle_idx * 0.9))
            r = 0.3 + 0.5 * abs(math.sin(obstacle_idx * 2.3))
            g = 0.3 + 0.5 * abs(math.sin(obstacle_idx * 1.1))
            b = 0.3 + 0.5 * abs(math.sin(obstacle_idx * 3.7))
            dynamic.add_rectangle(oid, x=ox - 0.06, y=oy, width=0.12, height=0.015,
                                  color=[r, g, b, 0.9], edge_color=[r * 0.5, g * 0.5, b * 0.5])
            dynamic_obstacles.append(oid)
            obstacle_idx += 1
            next_obstacle_time = t + 2.5

        dynamic.set_grid(show=(int(t / 15) % 2 == 0))
        time.sleep(0.05)


if __name__ == '__main__':
    main()
