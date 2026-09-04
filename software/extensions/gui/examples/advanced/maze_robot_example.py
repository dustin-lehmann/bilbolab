"""
Maze-Solving Robot Showcase
===========================

A self-contained simulation of a differential-drive robot exploring and solving
a 5 m x 3 m maze, visualised live in the BilboLab GUI. No hardware needed.

Left side — MapWidget (5 x 3 m, 0.5 m cells):
  - Maze walls appear as soon as the robot's distance sensors "see" them.
    Undiscovered walls can be revealed as faint ground truth with a button.
  - Explored cells are shaded, the driven path is drawn on the floor
    (blue = exploration, orange = return run on the shortest known path).
  - Start / target markers, live sensor rays with hit markers.

Right side — dashboard:
  - Digital readouts for the three distance sensors (left / front / right)
    with threshold colouring (red < 12 cm, amber < 30 cm).
  - Robot state numbers (speed, yaw rate, heading, odometry).
  - Mission status panel, coverage bar, mission clock, battery.
  - Real-time plot of the sensor readings and a scrolling event log.
  - Buttons: Pause/Resume, Reset, New Maze, Speed, Reveal walls, Auto-loop.

Mission sequence:
  SCAN (360 deg sweep) -> EXPLORE (DFS, greedy towards the target)
  -> TARGET REACHED -> RETURN (BFS shortest path on the known map) -> DONE

Run from the `software/` directory:
    python -m extensions.gui.examples.advanced.maze_robot_example
"""

import collections
import math
import random
import time

from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.map.map import MapWidget
from extensions.gui.src.lib.map.map_objects import (
    Point,
    Rectangle,
    Line,
    Agent,
    MapObjectGroup,
)
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.buttons import Button, MultiStateButton
from extensions.gui.src.lib.objects.python.callout import Callout, CalloutType
from extensions.gui.src.lib.objects.python.indicators import ProgressIndicator, BatteryIndicatorWidget
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget
from extensions.gui.src.lib.objects.python.text import StatusWidget, StatusWidgetElement, LineScrollWidget
from extensions.gui.src.lib.plot.realtime.rt_plot import RT_Plot_Widget

# ======================================================================================================================
# Maze geometry
# ======================================================================================================================
COLS, ROWS = 10, 6                 # 10 x 6 cells of 0.5 m  ->  5 m x 3 m
CELL = 0.5                         # m
START_CELL = (0, 0)                # bottom-left
TARGET_CELL = (COLS - 1, ROWS - 1)  # top-right
N_LOOPS = 4                        # extra interior walls removed -> maze has loops, so the return path can differ
MIN_DEAD_ENDS = 2                  # only use mazes that make the greedy explorer backtrack at least this often

# Robot / sensors
SENSOR_RANGE = 2.0                 # m
SENSOR_ANGLES = {'left': math.pi / 2, 'front': 0.0, 'right': -math.pi / 2}   # relative to heading
BASE_SPEED = 0.6                   # m/s  (at speed factor 1x)
BASE_TURN_RATE = 3.5               # rad/s
WALL_THICKNESS = 0.035             # m (drawn)

# Directions: index * 90 deg = heading.  0 = East, 1 = North, 2 = West, 3 = South
DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]
DIR_NAMES = ['E', 'N', 'W', 'S']

# Map draw layers: 0 explored cells < 1 walls < 3 paths/plan (ids sort plan_* < seg_*) < 4 rays, robot
# Colours (RGBA 0..1)
COL_WALL_KNOWN = [0.92, 0.92, 0.96, 0.95]
COL_WALL_HIDDEN = [0.6, 0.6, 0.75, 0.2]
COL_VISITED = [0.25, 0.55, 0.95, 0.13]
COL_PATH_EXPLORE = [0.3, 0.75, 1.0, 0.85]
COL_PATH_RETURN = [1.0, 0.7, 0.2, 0.9]
COL_PLAN = [1.0, 0.7, 0.2, 0.45]
COL_ROBOT = [0.3, 0.75, 1.0, 1]
COL_RAY = [0.45, 1.0, 0.6, 0.55]
COL_RAY_HIT = [0.45, 1.0, 0.6, 0.9]
COL_START = [0.2, 0.85, 0.4, 1]
COL_TARGET = [1.0, 0.35, 0.3, 1]


# ----------------------------------------------------------------------------------------------------------------------
def wall_key(cell, d):
    """Key of the wall on side `d` of `cell`. Vertical walls ('v', i, j) sit at x = i*CELL spanning cell row j,
    horizontal walls ('h', i, j) sit at y = j*CELL spanning cell column i."""
    cx, cy = cell
    if d == 0:
        return 'v', cx + 1, cy
    if d == 1:
        return 'h', cx, cy + 1
    if d == 2:
        return 'v', cx, cy
    return 'h', cx, cy


def wall_segment(key):
    kind, i, j = key
    x, y = i * CELL, j * CELL
    if kind == 'v':
        return x, y, x, y + CELL
    return x, y, x + CELL, y


def wall_id(key):
    return f'{key[0]}_{key[1]}_{key[2]}'


def is_boundary(key):
    kind, i, j = key
    return (kind == 'v' and i in (0, COLS)) or (kind == 'h' and j in (0, ROWS))


def cell_center(cell):
    return cell[0] * CELL + CELL / 2, cell[1] * CELL + CELL / 2


def in_bounds(cell):
    return 0 <= cell[0] < COLS and 0 <= cell[1] < ROWS


def neighbor(cell, d):
    return cell[0] + DIRS[d][0], cell[1] + DIRS[d][1]


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def wrap_angle(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


# ======================================================================================================================
# Maze: ground truth + what the robot knows about it
# ======================================================================================================================
class Maze:
    def __init__(self, seed: int):
        self.seed = seed
        self.walls = self._generate(seed)                      # ground truth
        self.segments = {k: wall_segment(k) for k in self.walls}
        self.interior = {k for k in self.walls if not is_boundary(k)}
        # Robot knowledge: outer boundary is known (arena size), interior walls must be discovered
        self.known_walls = {k for k in self.walls if is_boundary(k)}
        self.known_open = set()                                # passages known to be free

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _generate(seed: int) -> set:
        """Perfect maze via iterative recursive backtracker, then a few walls removed to create loops."""
        rng = random.Random(seed)
        walls = set()
        for cx in range(COLS):
            for cy in range(ROWS):
                for d in range(4):
                    walls.add(wall_key((cx, cy), d))

        visited = {START_CELL}
        stack = [START_CELL]
        while stack:
            cell = stack[-1]
            options = [d for d in range(4)
                       if in_bounds(neighbor(cell, d)) and neighbor(cell, d) not in visited]
            if not options:
                stack.pop()
                continue
            d = rng.choice(options)
            walls.discard(wall_key(cell, d))
            nxt = neighbor(cell, d)
            visited.add(nxt)
            stack.append(nxt)

        interior = sorted(k for k in walls if not is_boundary(k))
        rng.shuffle(interior)
        for k in interior[:N_LOOPS]:
            walls.discard(k)
        return walls

    # ------------------------------------------------------------------------------------------------------------------
    def sense_grid(self, cell, d, max_cells=int(SENSOR_RANGE / CELL)):
        """Grid ray from a cell centre along axis `d`: marks passages as open until the first wall, which becomes
        known. Returns the wall key or None if nothing is within range."""
        c = cell
        for _ in range(max_cells):
            key = wall_key(c, d)
            if key in self.walls:
                self.known_walls.add(key)
                return key
            self.known_open.add(key)
            c = neighbor(c, d)
            if not in_bounds(c):
                return None
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def raycast(self, x, y, angle, max_range=SENSOR_RANGE):
        """Geometric ray against all (axis-aligned) wall segments. Returns (distance, wall key or None)."""
        ca, sa = math.cos(angle), math.sin(angle)
        best_t, best_key = max_range, None
        eps = 1e-6
        for key, (x0, y0, x1, y1) in self.segments.items():
            if key[0] == 'v':
                if abs(ca) < 1e-9:
                    continue
                t = (x0 - x) / ca
                if t <= 0 or t >= best_t:
                    continue
                yi = y + t * sa
                if y0 - eps <= yi <= y1 + eps:
                    best_t, best_key = t, key
            else:
                if abs(sa) < 1e-9:
                    continue
                t = (y0 - y) / sa
                if t <= 0 or t >= best_t:
                    continue
                xi = x + t * ca
                if x0 - eps <= xi <= x1 + eps:
                    best_t, best_key = t, key
        return best_t, best_key

    # ------------------------------------------------------------------------------------------------------------------
    def shortest_known_path(self, a, b):
        """BFS over passages the robot knows to be open."""
        prev = {a: None}
        queue = collections.deque([a])
        while queue:
            c = queue.popleft()
            if c == b:
                break
            for d in range(4):
                if wall_key(c, d) in self.known_open:
                    n = neighbor(c, d)
                    if in_bounds(n) and n not in prev:
                        prev[n] = c
                        queue.append(n)
        if b not in prev:
            return None
        path, c = [], b
        while c is not None:
            path.append(c)
            c = prev[c]
        return path[::-1]


# ======================================================================================================================
# Robot simulation
# ======================================================================================================================
class MazeRobotSim:
    """Differential-drive robot: 360 deg scan, DFS exploration (greedy towards the target), BFS return run."""

    STATES = ('IDLE', 'SCANNING', 'EXPLORING', 'BACKTRACKING', 'TARGET', 'RETURNING', 'DONE')

    def __init__(self, maze: Maze, fast: bool = False):
        self.maze = maze
        self.fast = fast                       # True: skip the geometric sensor raycasts (dry runs)
        self.events = collections.deque()     # (level, text) — drained by the dashboard
        self.speed_factor = 1.0
        self.running = True

        # Pose
        self.x, self.y = cell_center(START_CELL)
        self.psi = 0.0
        self.heading = 0                       # axis-aligned heading index (0..3)
        self.v = 0.0
        self.omega = 0.0

        # Mission
        self.state = 'IDLE'
        self.cell = START_CELL
        self.visited = {START_CELL}
        self.stack = []
        self.motion = None                     # None | 'turn' | 'drive'
        self.target_cell = None
        self.target_heading = 0
        self.return_path = []
        self.return_index = 0

        self.t = 0.0
        self.time_in_state = 0.0
        self.wait = 1.0                        # initial pause before the sweep
        self.scan_angle = 0.0
        self.scan_next = 0.0

        # Statistics
        self.odometry = 0.0
        self.explore_distance = None
        self.explore_time = None
        self.turns = 0
        self.dead_ends = 0

        # Sensors
        self.sensors = {name: SENSOR_RANGE for name in SENSOR_ANGLES}
        self.sensor_hits = {name: (self.x, self.y) for name in SENSOR_ANGLES}

        self.log('info', f'Maze #{maze.seed}: {COLS} x {ROWS} cells, {len(maze.interior)} interior walls')
        self._set_state('SCANNING')
        self.log('info', 'Initial 360 deg sensor sweep')

    # ------------------------------------------------------------------------------------------------------------------
    def log(self, level, text):
        self.events.append((level, text))

    def _set_state(self, state):
        self.state = state
        self.time_in_state = 0.0

    @property
    def battery(self):
        return max(0.0, 1.0 - 0.004 * self.odometry - 0.0003 * self.t)

    @property
    def coverage(self):
        return len(self.visited) / (COLS * ROWS)

    # ------------------------------------------------------------------------------------------------------------------
    def step(self, dt):
        self.v = 0.0
        self.omega = 0.0

        if not self.running or self.state in ('IDLE', 'DONE'):
            if self.state == 'DONE':
                self.time_in_state += dt      # used by the auto-loop; mission clock stays frozen
            self._update_sensors()
            return

        self.t += dt
        self.time_in_state += dt

        if self.wait > 0:
            self.wait -= dt
            self._update_sensors()
            return

        v_max = BASE_SPEED * self.speed_factor
        w_max = BASE_TURN_RATE * self.speed_factor

        if self.state == 'TARGET':
            # Dwell at the target is over — head home on the shortest known path
            self._start_return()

        elif self.state == 'SCANNING':
            dpsi = w_max * dt
            self.psi = wrap_angle(self.psi + dpsi)
            self.scan_angle += dpsi
            self.omega = w_max
            # Sense with the three sensors each time the heading passes an axis
            while self.scan_next <= self.scan_angle and self.scan_next < 2 * math.pi:
                self._sense_from_cell(int(round(self.scan_next / (math.pi / 2))) % 4)
                self.scan_next += math.pi / 2
            if self.scan_angle >= 2 * math.pi:
                self.psi = 0.0
                self.heading = 0
                self._set_state('EXPLORING')
                self.log('info', f'Exploration started, target at {TARGET_CELL}')
                self._decide()

        elif self.motion == 'turn':
            target_psi = self.target_heading * math.pi / 2
            err = wrap_angle(target_psi - self.psi)
            if abs(err) <= w_max * dt:
                self.psi = wrap_angle(target_psi)
                self.heading = self.target_heading
                self.motion = 'drive'
            else:
                self.omega = math.copysign(w_max, err)
                self.psi = wrap_angle(self.psi + self.omega * dt)

        elif self.motion == 'drive':
            tx, ty = cell_center(self.target_cell)
            dist = math.hypot(tx - self.x, ty - self.y)
            step = v_max * dt
            self.v = v_max
            if step >= dist:
                self.x, self.y = tx, ty
                self.odometry += dist
                self.motion = None
                self._arrive()
            else:
                self.x += step * math.cos(self.psi)
                self.y += step * math.sin(self.psi)
                self.odometry += step

        self._update_sensors()

    # ------------------------------------------------------------------------------------------------------------------
    def _update_sensors(self):
        """Continuous geometric raycast for the three sensors (display + discovery of any wall a ray hits)."""
        if self.fast:
            return
        for name, offset in SENSOR_ANGLES.items():
            angle = self.psi + offset
            dist, key = self.maze.raycast(self.x, self.y, angle)
            if key is not None:
                self.maze.known_walls.add(key)
            self.sensors[name] = dist
            self.sensor_hits[name] = (self.x + dist * math.cos(angle), self.y + dist * math.sin(angle))

    # ------------------------------------------------------------------------------------------------------------------
    def _sense_from_cell(self, heading):
        """Grid-based sensing from the current cell centre with left/front/right sensors for a given heading."""
        for d in ((heading + 1) % 4, heading, (heading - 1) % 4):
            self.maze.sense_grid(self.cell, d)

    # ------------------------------------------------------------------------------------------------------------------
    def _go(self, d, state=None):
        """Start moving into direction d (turn first if needed)."""
        self.target_cell = neighbor(self.cell, d)
        self.target_heading = d
        if d != self.heading:
            self.turns += 1
            self.motion = 'turn'
        else:
            self.motion = 'drive'
        if state is not None and state != self.state:
            self._set_state(state)

    # ------------------------------------------------------------------------------------------------------------------
    def _arrive(self):
        self.cell = self.target_cell
        self.visited.add(self.cell)

        if self.state in ('EXPLORING', 'BACKTRACKING'):
            self._sense_from_cell(self.heading)
            self._decide()
        elif self.state == 'RETURNING':
            self.return_index += 1          # index of the cell we just reached
            if self.cell == START_CELL or self.return_index + 1 >= len(self.return_path):
                self._finish()
            else:
                nxt = self.return_path[self.return_index + 1]
                d = DIRS.index((nxt[0] - self.cell[0], nxt[1] - self.cell[1]))
                self._go(d)

    # ------------------------------------------------------------------------------------------------------------------
    def _decide(self):
        """DFS step: prefer unvisited neighbours closer to the target, then the one needing the smallest turn."""
        if self.cell == TARGET_CELL:
            self._on_target()
            return

        options = []
        for d in range(4):
            n = neighbor(self.cell, d)
            if in_bounds(n) and n not in self.visited and wall_key(self.cell, d) in self.maze.known_open:
                options.append(d)

        if options:
            def score(d):
                turn = min((d - self.heading) % 4, (self.heading - d) % 4)
                return manhattan(neighbor(self.cell, d), TARGET_CELL), turn
            d = min(options, key=score)
            self.stack.append(self.cell)
            self._go(d, 'EXPLORING')
        else:
            if not self.stack:
                self.log('error', 'No path to target — maze fully explored')
                self._set_state('DONE')
                return
            if self.state != 'BACKTRACKING':
                self.dead_ends += 1
                self.log('warning', f'Dead end at {self.cell} — backtracking')
            prev = self.stack.pop()
            d = DIRS.index((prev[0] - self.cell[0], prev[1] - self.cell[1]))
            self._go(d, 'BACKTRACKING')

    # ------------------------------------------------------------------------------------------------------------------
    def _on_target(self):
        self.explore_distance = self.odometry
        self.explore_time = self.t
        self._set_state('TARGET')
        self.log('success', f'Target reached: {self.odometry:.1f} m driven, {len(self.visited)} cells visited, '
                            f'{self.dead_ends} dead ends')

        self.return_path = self.maze.shortest_known_path(TARGET_CELL, START_CELL) or [TARGET_CELL]
        self.return_index = 0
        self.log('info', f'Shortest known path home: {len(self.return_path) - 1} cells '
                         f'({(len(self.return_path) - 1) * CELL:.1f} m) — returning')
        self.wait = 1.5     # dwell at the target before heading home (see step())

    # ------------------------------------------------------------------------------------------------------------------
    def _start_return(self):
        if len(self.return_path) > 1:
            nxt = self.return_path[1]
            d = DIRS.index((nxt[0] - self.cell[0], nxt[1] - self.cell[1]))
            self._go(d, 'RETURNING')
        else:
            self._finish()

    # ------------------------------------------------------------------------------------------------------------------
    def _finish(self):
        self._set_state('DONE')
        ret = self.odometry - (self.explore_distance or 0.0)
        self.log('success', f'Mission complete in {self.t:.0f} s — explore {self.explore_distance or 0:.1f} m, '
                            f'return {ret:.1f} m, {len(self.maze.known_walls & self.maze.interior)}/'
                            f'{len(self.maze.interior)} interior walls mapped')


# ----------------------------------------------------------------------------------------------------------------------
def find_interesting_seed(seed: int, max_tries: int = 200) -> int:
    """Many random mazes let the greedy explorer walk straight to the target. Dry-run the mission (no kinematics
    cost: high speed factor, no sensor raycasts) and return the first seed >= `seed` with enough dead ends."""
    for candidate in range(seed, seed + max_tries):
        sim = MazeRobotSim(Maze(candidate), fast=True)
        sim.speed_factor = 8.0
        for _ in range(20000):
            sim.step(0.05)
            if sim.state == 'DONE':
                break
        if sim.dead_ends >= MIN_DEAD_ENDS:
            return candidate
    return seed


# ======================================================================================================================
# Map view: keeps the MapWidget in sync with maze + robot
# ======================================================================================================================
class MazeMapView:
    def __init__(self, the_map):
        self.map = the_map
        self.generation = 0
        self.reveal_hidden = False

        # Persistent objects -------------------------------------------------------------------------------------
        sx, sy = cell_center(START_CELL)
        tx, ty = cell_center(TARGET_CELL)
        self.map.addObject(Point('start', x=sx, y=sy, color=COL_START, size=0.08, shape='square',
                                 border_width=0, name='START', layer=3))
        self.map.addObject(Point('target', x=tx, y=ty, color=COL_TARGET, size=0.1, shape='diamond',
                                 border_width=0, name='TARGET', layer=3))

        self.rays = {}
        self.ray_hits = {}
        for name in SENSOR_ANGLES:
            self.rays[name] = Line(f'ray_{name}', start=[sx, sy], end=[sx, sy],
                                   color=COL_RAY, width=1.5, style='solid', show_name=False, layer=4)
            self.map.addObject(self.rays[name])
            self.ray_hits[name] = Point(f'hit_{name}', x=sx, y=sy, color=COL_RAY_HIT, size=3,
                                        size_mode='pixel', border_width=0, show_name=False, layer=4)
            self.map.addObject(self.ray_hits[name])

        self.robot = Agent('robot', x=sx, y=sy, psi=0.0, color=COL_ROBOT, size=0.09,
                           arrow_length=0.16, arrow_width=0.03, name='Robot', layer=4)
        self.map.addObject(self.robot)

        # Per-maze objects ----------------------------------------------------------------------------------------
        self.walls_group = None
        self.visited_group = None
        self.path_group = None
        self.plan_group = None
        self.wall_objects = {}
        self.drawn_known = set()
        self.drawn_visited = set()
        self.path_segments = 0
        self.live_segment = None
        self.live_color = None
        self.plan_drawn = False
        self.last_cell = None

    # ------------------------------------------------------------------------------------------------------------------
    def build(self, maze: Maze):
        """(Re)create all maze-dependent map layers."""
        for group in (self.walls_group, self.visited_group, self.path_group, self.plan_group):
            if group is not None:
                self.map.removeGroup(group)
        self.generation += 1
        g = self.generation

        self.visited_group = self.map.addGroup(MapObjectGroup(f'visited_{g}', name='Explored cells'))
        self.walls_group = self.map.addGroup(MapObjectGroup(f'walls_{g}', name='Walls'))
        self.path_group = self.map.addGroup(MapObjectGroup(f'path_{g}', name='Driven path'))
        self.plan_group = self.map.addGroup(MapObjectGroup(f'plan_{g}', name='Planned path'))

        self.wall_objects = {}
        for key in maze.walls:
            x0, y0, x1, y1 = wall_segment(key)
            horizontal = key[0] == 'h'
            known = key in maze.known_walls
            rect = Rectangle(
                wall_id(key),
                x=(x0 + x1) / 2, y=(y0 + y1) / 2,
                width=CELL + WALL_THICKNESS if horizontal else WALL_THICKNESS,
                height=WALL_THICKNESS if horizontal else CELL + WALL_THICKNESS,
                color=COL_WALL_KNOWN if known else COL_WALL_HIDDEN,
                border_width=0, show_name=False, layer=1,
                visible=known or self.reveal_hidden,
            )
            self.walls_group.addObject(rect)
            self.wall_objects[key] = rect

        self.drawn_known = set(maze.known_walls)
        self.drawn_visited = set()
        self.path_segments = 0
        self.live_segment = None
        self.live_color = None
        self.plan_drawn = False
        self.last_cell = None

        sx, sy = cell_center(START_CELL)
        self.robot.update({'x': sx, 'y': sy, 'psi': 0.0})

    # ------------------------------------------------------------------------------------------------------------------
    def set_reveal(self, reveal: bool, maze: Maze):
        self.reveal_hidden = reveal
        for key, rect in self.wall_objects.items():
            if key not in maze.known_walls:
                rect.visible(reveal)

    # ------------------------------------------------------------------------------------------------------------------
    def sync(self, sim: MazeRobotSim):
        maze = sim.maze

        # Newly discovered walls
        for key in maze.known_walls - self.drawn_known:
            rect = self.wall_objects.get(key)
            if rect is not None:
                rect.updateConfig(color=COL_WALL_KNOWN, visible=True)
            self.drawn_known.add(key)

        # Newly visited cells
        for cell in sim.visited - self.drawn_visited:
            cx, cy = cell_center(cell)
            self.visited_group.addObject(Rectangle(
                f'cell_{cell[0]}_{cell[1]}', x=cx, y=cy, width=CELL, height=CELL,
                color=COL_VISITED, border_width=0, show_name=False, layer=0))
            self.drawn_visited.add(cell)

        # Planned return path (dashed), drawn once the plan exists
        if sim.return_path and not self.plan_drawn and len(sim.return_path) > 1:
            for i in range(len(sim.return_path) - 1):
                a, b = cell_center(sim.return_path[i]), cell_center(sim.return_path[i + 1])
                self.plan_group.addObject(Line(f'plan_{i}', start=list(a), end=list(b), color=COL_PLAN,
                                               width=2, style='dashed', dash_px=[8, 6], show_name=False, layer=3))
            self.plan_drawn = True

        # Driven path: one solid segment per cell transition, the current one follows the robot live.
        # A new segment also starts when the colour changes (exploration -> return run).
        color = COL_PATH_RETURN if sim.state in ('RETURNING', 'DONE') else COL_PATH_EXPLORE
        if self.live_segment is None or sim.cell != self.last_cell or color is not self.live_color:
            if self.live_segment is not None:
                # Finalise the previous segment at the centre of the cell the robot is in now
                self.live_segment.update(end=list(cell_center(sim.cell)))
            self.path_segments += 1
            self.live_segment = Line(
                f'seg_{self.path_segments}', start=list(cell_center(sim.cell)), end=[sim.x, sim.y],
                color=color, width=3.5 if color is COL_PATH_RETURN else 2.5, style='solid', show_name=False,
                layer=3)
            self.path_group.addObject(self.live_segment)
            self.live_color = color
            self.last_cell = sim.cell
        else:
            self.live_segment.update(end=[sim.x, sim.y])

        # Robot + sensor rays
        self.robot.update({'x': sim.x, 'y': sim.y, 'psi': sim.psi})
        for name in SENSOR_ANGLES:
            hx, hy = sim.sensor_hits[name]
            self.rays[name].update(start=[sim.x, sim.y], end=[hx, hy])
            self.ray_hits[name].update(x=hx, y=hy)


# ======================================================================================================================
# GUI
# ======================================================================================================================
def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    category = Category(id='maze', name='Maze Robot', icon='M')
    app.addCategory(category)

    page = Page(id='mission', name='Mission Control')
    category.addPage(page, position=1)

    # =========================================================================
    # Map (left, 29 x 18 grid cells)
    # =========================================================================
    map_widget = MapWidget(
        widget_id='maze_map',
        limits={'x': [-0.25, COLS * CELL + 0.25], 'y': [-0.25, ROWS * CELL + 0.25]},
        origin=[0, 0],
        tiles=False,
        show_grid=True,
        major_grid_size=1.0,
        minor_grid_size=CELL,
        major_grid_color=[0.5, 0.5, 0.6, 0.35],
        minor_grid_color=[0.5, 0.5, 0.6, 0.18],
        map_color=[0.08, 0.09, 0.13, 1],
        coordinate_system_size=0.3,
        initial_display_center=[COLS * CELL / 2, ROWS * CELL / 2],
        initial_display_zoom=0.95,
    )
    page.addWidget(map_widget, row=1, column=1, width=29, height=18)

    view = MazeMapView(map_widget.map)

    # =========================================================================
    # Right panel
    # =========================================================================
    PANEL_COL, PANEL_W = 30, 21

    # --- Distance sensors ----------------------------------------------------
    sensor_group = Widget_Group(
        group_id='sensors_group', border=True, border_color=[0.35, 0.5, 0.4], border_width=1,
        title='DISTANCE SENSORS [cm]', show_title=True, title_color=[0.6, 0.9, 0.7], title_font_size=8,
        rows=1, columns=3)
    page.addWidget(sensor_group, row=1, column=PANEL_COL, width=PANEL_W, height=3)

    sensor_ranges = [
        {'max': 12, 'color': [1.0, 0.3, 0.25]},
        {'max': 30, 'color': [1.0, 0.75, 0.2]},
        {'min': 30, 'color': [0.45, 1.0, 0.6]},
    ]
    sensor_numbers = {}
    for i, (name, title) in enumerate([('left', 'LEFT'), ('front', 'FRONT'), ('right', 'RIGHT')]):
        num = DigitalNumberWidget(
            widget_id=f'dist_{name}', title=title, title_position='top',
            value=SENSOR_RANGE * 100, min_value=0, max_value=SENSOR_RANGE * 100, increment=0.1,
            color='transparent', text_color=[0.8, 0.8, 0.8], color_ranges=sensor_ranges)
        sensor_group.addWidget(num, row=1, column=1 + i, width=1, height=1)
        sensor_numbers[name] = num

    # --- Robot state ---------------------------------------------------------
    state_group = Widget_Group(
        group_id='state_group', border=True, border_color=[0.35, 0.45, 0.6], border_width=1,
        title='ROBOT STATE', show_title=True, title_color=[0.6, 0.8, 1.0], title_font_size=8,
        rows=1, columns=4)
    page.addWidget(state_group, row=4, column=PANEL_COL, width=PANEL_W, height=3)

    num_speed = DigitalNumberWidget(
        widget_id='speed', title='SPEED [m/s]', title_position='top', value=0.0,
        min_value=0, max_value=9.99, increment=0.01, color='transparent', text_color=[0.6, 0.8, 1.0])
    num_yaw = DigitalNumberWidget(
        widget_id='yaw_rate', title='YAW RATE [deg/s]', title_position='top', value=0.0,
        min_value=-999, max_value=999, increment=1, color='transparent', text_color=[0.6, 0.8, 1.0])
    num_heading = DigitalNumberWidget(
        widget_id='heading', title='HEADING [deg]', title_position='top', value=0.0,
        min_value=0, max_value=359, increment=1, color='transparent', text_color=[0.6, 0.8, 1.0])
    num_odo = DigitalNumberWidget(
        widget_id='odometry', title='ODOMETRY [m]', title_position='top', value=0.0,
        min_value=0, max_value=99.99, increment=0.01, color='transparent', text_color=[0.6, 0.8, 1.0])
    for i, num in enumerate([num_speed, num_yaw, num_heading, num_odo]):
        state_group.addWidget(num, row=1, column=1 + i, width=1, height=1)

    # --- Mission panel -------------------------------------------------------
    mission_group = Widget_Group(
        group_id='mission_group', border=True, border_color=[0.55, 0.45, 0.3], border_width=1,
        title='MISSION', show_title=True, title_color=[1.0, 0.8, 0.5], title_font_size=8,
        rows=4, columns=21)
    page.addWidget(mission_group, row=7, column=PANEL_COL, width=PANEL_W, height=4)

    status = StatusWidget(
        widget_id='mission_status',
        font_size=9,
        elements={
            'mode': StatusWidgetElement(label='Mode', color=[0.3, 0.3, 0.3], status='IDLE'),
            'cell': StatusWidgetElement(label='Cell', color=[0.3, 0.5, 0.8], status='(0, 0)'),
            'target': StatusWidgetElement(label='Target dist.', color=[0.8, 0.35, 0.3], status='-'),
            'walls': StatusWidgetElement(label='Walls mapped', color=[0.6, 0.6, 0.7], status='0'),
            'cells': StatusWidgetElement(label='Cells visited', color=[0.25, 0.55, 0.95], status='1'),
        },
    )
    mission_group.addWidget(status, row=1, column=1, width=10, height=4)

    coverage = ProgressIndicator(
        widget_id='coverage', value=0.0, title='Maze coverage', label='0 %',
        type='linear', direction='horizontal', track_fill_color=[0.25, 0.55, 0.95, 0.8])
    mission_group.addWidget(coverage, row=1, column=11, width=7, height=2)

    num_time = DigitalNumberWidget(
        widget_id='mission_time', title='MISSION TIME [s]', title_position='left', value=0,
        min_value=0, max_value=999, increment=1, color='transparent', text_color=[1.0, 0.8, 0.5])
    mission_group.addWidget(num_time, row=3, column=11, width=7, height=2)

    battery = BatteryIndicatorWidget(widget_id='battery', value=1.0, voltage=12.6, show='percentage')
    mission_group.addWidget(battery, row=1, column=18, width=4, height=1)

    num_voltage = DigitalNumberWidget(
        widget_id='battery_voltage', title='BATT [V]', title_position='top', value=12.6,
        min_value=0, max_value=99.9, increment=0.1, color='transparent', text_color=[1.0, 0.8, 0.5])
    mission_group.addWidget(num_voltage, row=2, column=18, width=4, height=3)

    # --- Sensor plot ---------------------------------------------------------
    plot = RT_Plot_Widget(
        widget_id='sensor_plot',
        plot_config={
            'title': 'Distance sensors',
            'x_axis_config': {'window_time': 20, 'pre_delay': 0.15},
            'buffer_size': 800,
            'show_legend': True,
            'legend_position': 'bottom',
        },
    )
    page.addWidget(plot, row=11, column=PANEL_COL, width=11, height=6)
    plot.plot.add_y_axis('dist', config={
        'label': 'm', 'side': 'left', 'precision': 1, 'min': 0, 'max': SENSOR_RANGE,
        'color': [0.7, 0.7, 0.7, 1]})
    ts_sensors = {
        'left': plot.plot.add_timeseries('left', config={
            'y_axis': 'dist', 'name': 'Left', 'color': [0.95, 0.6, 0.2, 1], 'width': 1.5}),
        'front': plot.plot.add_timeseries('front', config={
            'y_axis': 'dist', 'name': 'Front', 'color': [0.45, 1.0, 0.6, 1], 'width': 2}),
        'right': plot.plot.add_timeseries('right', config={
            'y_axis': 'dist', 'name': 'Right', 'color': [0.4, 0.7, 1.0, 1], 'width': 1.5}),
    }

    # --- Event log -----------------------------------------------------------
    log_widget = LineScrollWidget(widget_id='event_log', font_size=7, include_time_stamp=True,
                                  background_color=[0, 0, 0, 0.25])
    page.addWidget(log_widget, row=11, column=PANEL_COL + 11, width=10, height=6)

    LOG_COLORS = {
        'info': [0.8, 0.8, 0.85, 0.9],
        'warning': [1.0, 0.75, 0.2, 1],
        'error': [1.0, 0.35, 0.3, 1],
        'success': [0.45, 1.0, 0.6, 1],
        'user': [0.6, 0.8, 1.0, 1],
    }

    # =========================================================================
    # Simulation state shared with button callbacks
    # =========================================================================
    world = {'seed': 1, 'maze': None, 'sim': None, 'loop': True}

    def new_mission(seed):
        # (uses the buttons defined below — only called after the GUI is fully built)
        seed = find_interesting_seed(seed)
        world['seed'] = seed
        world['maze'] = Maze(seed)
        sim = MazeRobotSim(world['maze'])
        sim.speed_factor = speed_factors[msb_speed.state_index]
        world['sim'] = sim
        view.build(world['maze'])
        for ts in ts_sensors.values():
            ts.set_value(SENSOR_RANGE)
        btn_start.updateConfig(text='Pause', color=[0.55, 0.45, 0.1])
        return sim

    # --- Buttons -------------------------------------------------------------
    btn_start = Button(widget_id='btn_start', text='Pause', color=[0.55, 0.45, 0.1], font_size=10)
    page.addWidget(btn_start, row=17, column=PANEL_COL, width=4, height=2)

    def toggle_run(*args, **kwargs):
        sim = world['sim']
        if sim.state == 'DONE':
            return
        sim.running = not sim.running
        if sim.running:
            btn_start.updateConfig(text='Pause', color=[0.55, 0.45, 0.1])
            sim.log('user', 'Resumed')
        else:
            btn_start.updateConfig(text='Resume', color=[0.15, 0.5, 0.25])
            sim.log('user', 'Paused')

    btn_start.callbacks.click.register(toggle_run)

    btn_reset = Button(widget_id='btn_reset', text='Reset', color=[0.5, 0.2, 0.15], font_size=10)
    page.addWidget(btn_reset, row=17, column=PANEL_COL + 4, width=3, height=2)
    btn_reset.callbacks.click.register(
        lambda *a, **kw: (new_mission(world['seed']), log_widget.addLine('Mission reset', LOG_COLORS['user'])))

    btn_new = Button(widget_id='btn_new_maze', text='New Maze', color=[0.2, 0.35, 0.55], font_size=10)
    page.addWidget(btn_new, row=17, column=PANEL_COL + 7, width=4, height=2)

    def new_maze(*args, **kwargs):
        new_mission(world['seed'] + 1)
        log_widget.addLine(f"New maze #{world['seed']} generated", LOG_COLORS['user'])

    btn_new.callbacks.click.register(new_maze)

    speed_factors = [0.5, 1.0, 2.0]
    msb_speed = MultiStateButton(
        id='msb_speed', states=['Speed 0.5x', 'Speed 1x', 'Speed 2x'], current_state=1,
        color=[[0.25, 0.3, 0.4], [0.25, 0.4, 0.45], [0.3, 0.45, 0.3]], fontSize=10)
    page.addWidget(msb_speed, row=17, column=PANEL_COL + 11, width=4, height=2)

    def change_speed(button, *args, **kwargs):
        button.increaseIndex()
        world['sim'].speed_factor = speed_factors[button.state_index]
        world['sim'].log('user', f'Speed factor {world["sim"].speed_factor}x')

    msb_speed.callbacks.click.register(change_speed)

    msb_reveal = MultiStateButton(
        id='msb_reveal', states=['Walls: hidden', 'Walls: shown'], current_state=0,
        color=[[0.3, 0.3, 0.35], [0.45, 0.35, 0.55]], fontSize=10)
    page.addWidget(msb_reveal, row=17, column=PANEL_COL + 15, width=3, height=2)

    def toggle_reveal(button, *args, **kwargs):
        button.increaseIndex()
        view.set_reveal(button.state_index == 1, world['maze'])

    msb_reveal.callbacks.click.register(toggle_reveal)

    msb_loop = MultiStateButton(
        id='msb_loop', states=['Loop: OFF', 'Loop: ON'], current_state=1,
        color=[[0.3, 0.3, 0.35], [0.2, 0.45, 0.3]], fontSize=10)
    page.addWidget(msb_loop, row=17, column=PANEL_COL + 18, width=3, height=2)

    def toggle_loop(button, *args, **kwargs):
        button.increaseIndex()
        world['loop'] = button.state_index == 1

    msb_loop.callbacks.click.register(toggle_loop)

    # =========================================================================
    # Start
    # =========================================================================
    app.start()
    time.sleep(0.5)
    new_mission(world['seed'])

    last_status = None
    last_time = time.time()
    done_announced = False

    while True:
        now = time.time()
        dt = min(0.1, now - last_time)
        last_time = now

        sim = world['sim']
        sim.step(dt)
        view.sync(sim)

        # --- Numbers ---------------------------------------------------------
        for name, num in sensor_numbers.items():
            num.value = round(sim.sensors[name] * 100, 1)
            ts_sensors[name].set_value(sim.sensors[name])
        num_speed.value = round(sim.v, 2)
        num_yaw.value = round(math.degrees(sim.omega))
        num_heading.value = round(math.degrees(sim.psi) % 360) % 360
        num_odo.value = round(sim.odometry, 2)
        num_time.value = int(sim.t)

        # --- Slow-changing widgets: only push on change ------------------------
        n_known = len(sim.maze.known_walls & sim.maze.interior)
        snapshot = (sim.state, sim.running, sim.cell, n_known, len(sim.visited), int(sim.battery * 100))
        if snapshot != last_status:
            last_status = snapshot
            mode_colors = {
                'IDLE': [0.3, 0.3, 0.3], 'SCANNING': [0.5, 0.4, 0.7], 'EXPLORING': [0.25, 0.55, 0.95],
                'BACKTRACKING': [0.85, 0.6, 0.15], 'TARGET': [0.2, 0.75, 0.35],
                'RETURNING': [0.95, 0.65, 0.2], 'DONE': [0.2, 0.75, 0.35],
            }
            status.elements['mode'].status = sim.state if sim.running else f'{sim.state} (paused)'
            status.elements['mode'].color = mode_colors[sim.state]
            status.elements['cell'].status = f'{sim.cell}  {DIR_NAMES[sim.heading]}'
            status.elements['target'].status = f'{manhattan(sim.cell, TARGET_CELL)} cells'
            status.elements['walls'].status = f'{n_known} / {len(sim.maze.interior)}'
            status.elements['cells'].status = f'{len(sim.visited)} / {COLS * ROWS}'
            status.updateConfig()

            coverage.config['value'] = sim.coverage
            coverage.updateConfig(label=f'{sim.coverage * 100:.0f} %')
            voltage = round(10.5 + 2.1 * sim.battery, 1)
            battery.updateConfig(value=sim.battery, voltage=voltage)
            num_voltage.value = voltage

        # --- Event log + callouts --------------------------------------------
        while sim.events:
            level, text = sim.events.popleft()
            log_widget.addLine(text, LOG_COLORS.get(level, LOG_COLORS['info']))
            if level == 'success':
                app.callout_handler.add(Callout(content=text, callout_type=CalloutType.SUCCESS, timeout=5000))

        # --- Auto-loop: next maze a few seconds after the mission is done -------
        if sim.state == 'DONE':
            if not done_announced:
                done_announced = True
                btn_start.updateConfig(text='Done', color=[0.2, 0.45, 0.3])
            if world['loop'] and sim.time_in_state > 6.0:
                done_announced = False
                new_maze()
        else:
            done_announced = False

        time.sleep(0.05)


if __name__ == '__main__':
    main()
