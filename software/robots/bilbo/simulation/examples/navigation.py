"""Babylon visualization of BILBO_CompleteAgent navigating around obstacles.

Demonstrates:
- BILBO simulation with full control stack (position -> velocity -> balancing)
- Obstacle avoidance via path planning
- visit_points() for autonomous waypoint sequencing
- Real-time 3D visualization with BabylonJS via BaseEnvironment

Run from the software/ directory:
    python robots/bilbo/simulation/examples/example_babylon_navigation.py
"""
import time

import qmt

from extensions.libs.babylon.src.standalone import StandaloneBabylon
from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.libs.babylon.src.lib.objects.box.box import Box
from extensions.libs.babylon.src.lib.objects.cylinder.cylinder import Cylinder
from extensions.libs.babylon.src.lib.objects.drawings.path import PathDrawing
from robots.bilbo.utilities.babylon.scenarios.lab import LabScenario

from robots.bilbo.simulation.agent import BILBO_CompleteAgent
from robots.bilbo.simulation.model import BILBO_3D_State
from simulation.objects.base_environment import BaseEnvironment
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS
from core.utils.control_lib.lib_control.motion_planning import (
    CircleObstacle,
    BoxObstacle,
    Bounds,
)

# === Configuration ===
ARENA_SIZE = 3.0
Ts = 0.01

CIRCLE_OBSTACLES = [
    {'cx': 1.0, 'cy': 1.5, 'radius': 0.2},
    {'cx': 2.0, 'cy': 1.0, 'radius': 0.15},
    {'cx': 1.5, 'cy': 2.3, 'radius': 0.18},
]

BOX_OBSTACLES = [
    {'cx': 2.2, 'cy': 2.0, 'width': 0.5, 'height': 0.2, 'psi': 0.3},
]

TARGETS = [
    [2.5, 0.5],
    [2.5, 2.5],
    [0.5, 2.5],
    [0.5, 0.5],
]


def main():
    # === Babylon scene ===
    scenario = LabScenario(size=ARENA_SIZE, background_color=[1, 1, 1])
    babylon = StandaloneBabylon(
        title="BILBO Navigation Demo",
        ws_port=9000,
        http_port=9200,
        scenario=scenario,
    )
    babylon.start()

    # === Robot visualization ===
    robot_viz = BabylonBilbo('bilbo1', color=[0.15, 0.4, 0.75], text='1')
    babylon.addObject(robot_viz)

    # === Visual obstacles ===
    for i, obs in enumerate(CIRCLE_OBSTACLES):
        cyl = Cylinder(
            f'obstacle_circle_{i}',
            color=[0.75, 0.25, 0.2],
            diameter=obs['radius'] * 2,
            height=0.15,
            alpha=0.85,
        )
        babylon.addObject(cyl)
        cyl.setPosition(x=obs['cx'], y=obs['cy'], z=0.075)

    for i, obs in enumerate(BOX_OBSTACLES):
        box = Box(
            f'obstacle_box_{i}',
            color=[0.75, 0.25, 0.2],
            size={'x': obs['width'], 'y': obs['height'], 'z': 0.15},
        )
        babylon.addObject(box)
        box.setPosition(x=obs['cx'], y=obs['cy'], z=0.075)
        box.setOrientation(qmt.quatFromAngleAxis(obs['psi'], [0, 0, 1]))

    # === Path drawings ===
    path_drawing = PathDrawing('planned_path', pathColor=[0.2, 0.6, 1.0, 0.8], pathWidth=0.008)
    babylon.addObject(path_drawing)

    trail_drawing = PathDrawing('trail', pathColor=[0.4, 0.4, 0.4, 0.5], pathWidth=0.005)
    babylon.addObject(trail_drawing)

    # === Target markers ===
    for i, (tx, ty) in enumerate(TARGETS):
        marker = Box(
            f'target_{i}',
            color=[0.2, 0.7, 0.3],
            size={'x': 0.06, 'y': 0.06, 'z': 0.06},
        )
        babylon.addObject(marker)
        marker.setPosition(x=tx, y=ty, z=0.03)

    # === Simulation obstacles ===
    sim_obstacles = []
    for obs in CIRCLE_OBSTACLES:
        sim_obstacles.append(CircleObstacle(cx=obs['cx'], cy=obs['cy'], radius=obs['radius']))
    for obs in BOX_OBSTACLES:
        sim_obstacles.append(BoxObstacle(
            cx=obs['cx'], cy=obs['cy'],
            width=obs['width'], height=obs['height'], psi=obs['psi']))

    bounds = Bounds(x_min=0.1, x_max=ARENA_SIZE - 0.1,
                    y_min=0.1, y_max=ARENA_SIZE - 0.1)

    # === Simulation agent ===
    x0 = BILBO_3D_State(x=0.5, y=0.5, v=0, theta=0, theta_dot=0, psi=0, psi_dot=0)
    agent = BILBO_CompleteAgent(agent_id='bilbo1', Ts=Ts, x0=x0)
    agent.set_obstacles(sim_obstacles)
    agent.set_bounds(bounds)

    # Start the navigation sequence — loops through targets indefinitely
    agent.visit_points(TARGETS, max_speed=0.6, settling_time=1.0, loop=True)

    # Show planned path whenever navigation starts a new move
    trail_points = []
    trail_step = [0]

    def visualization_output():
        state = agent.state
        robot_viz.set_state(
            x=float(state.x),
            y=float(state.y),
            theta=float(state.theta),
            psi=float(state.psi),
        )

        # Update planned path display
        if len(agent.position_control._path) > 0 and not agent.position_control.is_idle:
            path_drawing.setPoints(agent.position_control._path)
        elif agent.position_control.is_idle:
            path_drawing.clearPoints()

        # Record trail (every 10 steps)
        trail_step[0] += 1
        if trail_step[0] >= 10:
            trail_points.append([float(state.x), float(state.y)])
            if len(trail_points) > 500:
                del trail_points[:len(trail_points) - 500]
            trail_drawing.setPoints(trail_points)
            trail_step[0] = 0




    # === Environment ===
    env = BaseEnvironment(Ts=Ts, run_mode='rt')
    env.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(visualization_output)

    env.addObject(agent)
    env.init()
    env.initialize()



    print(f"Starting navigation demo — visiting {len(TARGETS)} waypoints in a loop")
    print("Press Ctrl+C to stop\n")

    try:
        env.start()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        babylon.close()


if __name__ == '__main__':
    main()
