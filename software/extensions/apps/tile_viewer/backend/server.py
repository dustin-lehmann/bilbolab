"""
Tile Viewer Server

Generic Flask-SocketIO server that exposes a `TileController` (see
projects/IdeenExpo2026/testbed/tiles/tile_controller.py) to the web:

- serves the built Vue frontend (frontend/dist)
- pushes state updates to all clients (throttled to ~30 fps)
- accepts paint/control commands from clients
- runs animated test patterns (chase, rainbow) in a background task

The server does not know anything about hardware. Whether the controller
has a QuinLED driver attached or runs in mock-up mode is decided by the
caller (see projects/IdeenExpo2026/testbed/tiles/run_mock.py).
"""

from __future__ import annotations

import math
import random
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO

BROADCAST_INTERVAL = 1 / 30  # state push throttle (s)
ANIMATION_INTERVAL = 1 / 25  # animated pattern step (s)

# Animated patterns (run in the background task); everything else in
# set_pattern is applied once, statically.
ANIMATED_PATTERNS = {
    'chase', 'chase_rainbow', 'comets', 'marquee', 'rainbow', 'plasma',
    'scanner', 'radar', 'sonar', 'breathe', 'sparkle', 'snakes', 'tetris',
    'life', 'storm', 'rain', 'ripple',
}

# Tetris piece set for the small floor (piece-local cells + colors):
# small pieces plus most classic tetrominoes (no 4-long I — vertical it
# spans all 4 lanes and would be a free clear). In our tetris gravity
# points in -x: pieces enter right and fall left.
_TETRIS_PIECES = {
    'dot': ([(0, 0)], (230, 230, 230)),
    'i2': ([(0, 0), (1, 0)], (0, 240, 240)),
    'i3': ([(0, 0), (1, 0), (2, 0)], (0, 150, 255)),
    'corner': ([(0, 0), (1, 0), (0, 1)], (240, 60, 180)),
    'O': ([(0, 0), (1, 0), (0, 1), (1, 1)], (240, 200, 0)),
    'T': ([(0, 0), (1, 0), (2, 0), (1, 1)], (170, 0, 240)),
    'S': ([(1, 0), (2, 0), (0, 1), (1, 1)], (0, 230, 70)),
    'Z': ([(0, 0), (1, 0), (1, 1), (2, 1)], (240, 40, 40)),
    'J': ([(0, 0), (1, 0), (2, 0), (0, 1)], (40, 90, 240)),
    'L': ([(0, 0), (1, 0), (2, 0), (2, 1)], (240, 130, 0)),
}


def _rotated(cells):
    """Rotate piece-local cells 90 deg and normalize to non-negative."""
    cells = [(y, -x) for x, y in cells]
    mnx = min(x for x, _ in cells)
    mny = min(y for _, y in cells)
    return [(x - mnx, y - mny) for x, y in cells]

# Ripple wave model (units: tiles and seconds)
RIPPLE_SPEED = 3.0   # ring expansion speed
RIPPLE_WIDTH = 0.4   # ring thickness (gaussian sigma)
RIPPLE_TAU = 1.6     # amplitude decay time constant


class TileViewerServer:
    """Web view + control surface for one TileController instance."""

    def __init__(
        self,
        controller,
        host: str = '0.0.0.0',
        port: int = 8530,
        static_folder: str | None = None,
        layouts_dir: str | None = None,
    ) -> None:
        self.controller = controller
        self.host = host
        self.port = port

        # Saved "pictures": one YAML file per layout
        self.layouts_dir = (Path(layouts_dir) if layouts_dir
                            else Path.cwd() / 'layouts')
        self.layouts_dir.mkdir(parents=True, exist_ok=True)

        if static_folder is None:
            static_folder = str(Path(__file__).parent.parent / 'frontend' / 'dist')
        self.static_folder = static_folder

        self.app = Flask(__name__, static_folder=self.static_folder)
        CORS(self.app)
        # threading mode (not eventlet): the same process may later drive
        # QuinLED hardware via requests/UDP, which eventlet monkey-patching
        # tends to interfere with.
        self.socketio = SocketIO(
            self.app, cors_allowed_origins='*', async_mode='threading'
        )

        self._dirty = False
        self._animation: str | None = None
        self._broadcast_task = None
        self._animation_task = None
        self._chase_steps: list[list[int]] | None = None
        self._chase_shape = None
        self._ring_pos: np.ndarray | None = None
        self._ring_pos_shape = None
        self._tetris: dict | None = None
        self._life: dict | None = None
        self._snakes: list | None = None
        self._storm: dict | None = None
        self._anim_color = (255, 176, 0)  # color for breathe/sparkle/scanner
        self._blinking: set[tuple[int, int]] = set()
        self._ripples: list[dict] = []
        self._sparkle: np.ndarray | None = None
        self._centers: np.ndarray | None = None
        self._centers_shape = None

        self.controller.add_listener(self._on_controller_change)
        self._register_routes()
        self._register_socketio()

    # ------------------------------------------------------------------ #
    # Controller -> clients
    # ------------------------------------------------------------------ #
    def _on_controller_change(self, frame) -> None:
        self._dirty = True

    def _broadcast_loop(self) -> None:
        while True:
            self.socketio.sleep(BROADCAST_INTERVAL)
            if self._dirty:
                self._dirty = False
                self.socketio.emit('state', self.controller.get_state_dict())

    def _config_dict(self) -> dict:
        cfg = self.controller.config
        return {
            'modules_x': cfg.modules_x,
            'modules_y': cfg.modules_y,
            'tiles_x': cfg.tiles_x,
            'tiles_y': cfg.tiles_y,
            'tile_size': cfg.tile_size,
        }

    # ------------------------------------------------------------------ #
    # Animated patterns
    # ------------------------------------------------------------------ #
    def _stop_animation(self) -> None:
        self._animation = None

    def _start_animation(self, name: str) -> None:
        self._animation = name
        if self._animation_task is None:
            self._animation_task = self.socketio.start_background_task(
                self._animation_loop
            )

    def _animation_loop(self) -> None:
        step = 0
        last = None
        while True:
            self.socketio.sleep(ANIMATION_INTERVAL)
            name = self._animation
            if name != last:
                step = 0  # each animation starts from its beginning
                last = name
                if name not in ('ripple', 'rain'):
                    self._ripples.clear()
            if name is None:
                continue
            getattr(self, '_animate_' + name)(step)
            step += 1

    # -------------------------- shared geometry --------------------------- #
    def _get_centers(self, shape) -> np.ndarray:
        """World-frame center positions of all segments, shape (N, 2), in
        tile units (tile (x, y) spans [x, x+1] x [y, y+1])."""
        if self._centers is None or self._centers_shape != shape:
            tiles_y, tiles_x, n_edges, n_segs = shape[:4]
            centers = np.zeros((tiles_y, tiles_x, n_edges, n_segs, 2),
                               dtype=np.float32)
            for y in range(tiles_y):
                for x in range(tiles_x):
                    for s in range(n_segs):
                        along = (s + 0.5) / n_segs
                        centers[y, x, 0, s] = (x + along, y + 1.0)  # N
                        centers[y, x, 1, s] = (x + 1.0, y + along)  # E
                        centers[y, x, 2, s] = (x + along, y + 0.0)  # S
                        centers[y, x, 3, s] = (x + 0.0, y + along)  # W
            self._centers = centers.reshape(-1, 2)
            self._centers_shape = shape
        return self._centers

    @staticmethod
    def _hue_rgb(hue: np.ndarray) -> np.ndarray:
        """Vectorized hue -> RGB (full saturation/value), result (N, 3) 0..255."""
        h6 = (hue % 1.0) * 6.0
        i = h6.astype(int) % 6
        f = h6 - np.floor(h6)
        q = 1.0 - f
        one = np.ones_like(f)
        zero = np.zeros_like(f)
        r = np.choose(i, [one, q, zero, zero, f, one])
        g = np.choose(i, [f, one, one, q, zero, zero])
        b = np.choose(i, [zero, zero, f, one, one, q])
        return np.stack([r, g, b], axis=-1) * 255.0

    def _build_chase_steps(self, shape) -> list[list[int]]:
        """Chase as a list of steps; each step lists the flat pixel
        indices of the pulse head(s).

        On each tile the pulse enters at the segment facing the previous
        tile, splits into two streams that run opposite ways around the
        perimeter, and the streams meet again at the segment facing the
        next tile (for straight-through tiles exactly on the opposite
        edge). The merged pulse then hops to the neighboring strip of the
        next tile. Tiles are visited in serpentine order (bottom row left
        to right, next row right to left, ...).
        """
        tiles_y, tiles_x, n_edges, n_segs = shape[:4]
        mid = n_segs // 2

        def idx(y, x, e, s):
            return ((y * tiles_x + x) * n_edges + e) * n_segs + s

        # Clockwise perimeter ring in world-frame indices: N 0->4 (left to
        # right along the top), E 4->0 (down), S 4->0 (right to left),
        # W 0->4 (up, back to the start corner).
        ring = [(0, s) for s in range(n_segs)]
        ring += [(1, s) for s in reversed(range(n_segs))]
        ring += [(2, s) for s in reversed(range(n_segs))]
        ring += [(3, s) for s in range(n_segs)]
        ring_pos = {es: i for i, es in enumerate(ring)}
        n_ring = len(ring)

        def facing(dx, dy):
            """Ring position of the middle segment of the edge that faces
            a neighboring tile at world offset (dx, dy)."""
            edge = {(1, 0): 1, (-1, 0): 3, (0, 1): 0, (0, -1): 2}[(dx, dy)]
            return ring_pos[(edge, mid)]

        tiles = []
        for y in range(tiles_y):
            xs = range(tiles_x) if y % 2 == 0 else reversed(range(tiles_x))
            tiles += [(x, y) for x in xs]

        steps: list[list[int]] = []
        for k, (x, y) in enumerate(tiles):
            if k > 0:
                px, py = tiles[k - 1]
                a = facing(px - x, py - y)  # entry: facing the previous tile
            else:
                a = ring_pos[(3, mid)]  # first tile: enter at the west edge
            if k + 1 < len(tiles):
                nx, ny = tiles[k + 1]
                b = facing(nx - x, ny - y)  # meeting point: facing the next tile
            else:
                b = (a + n_ring // 2) % n_ring  # last tile: meet opposite

            def seg(p):
                e, s = ring[p % n_ring]
                return idx(y, x, e, s)

            cw = (b - a) % n_ring   # clockwise distance to the meeting point
            ccw = (a - b) % n_ring  # counterclockwise distance
            steps.append([seg(a)])  # merged pulse on the entry segment
            for j in range(1, max(cw, ccw) + 1):
                heads = set()
                if j <= cw:
                    heads.add(seg(a + j))
                if j <= ccw:
                    heads.add(seg(a - j))
                steps.append(sorted(heads))
        return steps

    def _chase_frame(self, step: int, color_for) -> None:
        """Render one chase frame; `color_for(k, level)` returns the RGB
        for tail offset k (0 = head) at dim factor `level`."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        if self._chase_steps is None or self._chase_shape != shape:
            self._chase_steps = self._build_chase_steps(shape)
            self._chase_shape = shape
        chase = self._chase_steps
        pixels = np.zeros(shape, dtype=np.uint8).reshape(-1, 3)
        for k in range(11, -1, -1):  # tail (dim) first so the head wins
            t = step - k
            if t < 0:
                continue  # no tail before the start of the animation
            level = (1 - k / 12) ** 2
            color = color_for(k, level)
            for i in chase[t % len(chase)]:
                pixels[i] = color
        c.set_pixels(pixels.reshape(shape))

    def _animate_chase(self, step: int) -> None:
        """Twin pulse streams sweeping both halves of each tile's frame,
        with fading tails, in the selected color. Good for spotting dead
        segments."""
        r, g, b = self._anim_color
        self._chase_frame(
            step,
            lambda k, level: (int(r * level), int(g * level), int(b * level)),
        )

    def _animate_chase_rainbow(self, step: int) -> None:
        """Chase whose hue cycles continuously — a rainbow comet with a
        hue-shifted tail."""
        base_hue = step * ANIMATION_INTERVAL * 0.15  # full cycle ~6.7 s

        def color_for(k, level):
            r, g, b = _hsv_to_rgb(base_hue - k * 0.012)
            return (int(r * level), int(g * level), int(b * level))

        self._chase_frame(step, color_for)

    def _animate_comets(self, step: int) -> None:
        """Several comets on the chase path at once, evenly spaced, each
        with its own slowly drifting hue."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        if self._chase_steps is None or self._chase_shape != shape:
            self._chase_steps = self._build_chase_steps(shape)
            self._chase_shape = shape
        chase = self._chase_steps
        n_comets = 6
        spacing = len(chase) // n_comets
        pixels = np.zeros(shape, dtype=np.uint8).reshape(-1, 3)
        for j in range(n_comets):
            r, g, b = _hsv_to_rgb(j / n_comets + step * 0.001)
            for k in range(11, -1, -1):  # tail first so heads win overlaps
                t = step + j * spacing - k
                if t < 0:
                    continue  # comets fade in at animation start
                level = (1 - k / 12) ** 2
                col = (int(r * level), int(g * level), int(b * level))
                for i in chase[t % len(chase)]:
                    pixels[i] = col
        c.set_pixels(pixels.reshape(shape))

    def _animate_marquee(self, step: int) -> None:
        """Theater marquee: every 4th segment around each tile frame,
        stepping around the ring, in the selected color. (Period 4 divides
        the 20-segment ring evenly — no seam.)"""
        c = self.controller
        shape = c.get_frame().pixels.shape
        if self._ring_pos is None or self._ring_pos_shape != shape:
            n_segs = shape[3]
            ring = [(0, s) for s in range(n_segs)]
            ring += [(1, s) for s in reversed(range(n_segs))]
            ring += [(2, s) for s in reversed(range(n_segs))]
            ring += [(3, s) for s in range(n_segs)]
            pos = np.zeros(shape[:4], dtype=np.int64)
            for p, (e, s) in enumerate(ring):
                pos[:, :, e, s] = p
            self._ring_pos = pos.reshape(-1)
            self._ring_pos_shape = shape
        shift = step // 3  # advance one ring position every 3 ticks
        mask = (self._ring_pos - shift) % 4 == 0
        pixels = np.zeros((mask.size, 3), dtype=np.uint8)
        pixels[mask] = self._anim_color
        c.set_pixels(pixels.reshape(shape))

    def _animate_sonar(self, step: int) -> None:
        """Concentric waves expanding from the floor center."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        centers = self._get_centers(shape)
        d = np.hypot(centers[:, 0] - shape[1] / 2, centers[:, 1] - shape[0] / 2)
        t = step * ANIMATION_INTERVAL
        wavelength, speed = 2.4, 2.0  # tiles, tiles/s
        amp = (0.5 + 0.5 * np.cos(2 * np.pi * (d - speed * t) / wavelength)) ** 3
        color = np.array(self._anim_color, dtype=np.float32)
        pixels = np.clip(amp[:, None] * color, 0, 255)
        c.set_pixels(pixels.astype(np.uint8).reshape(shape))

    def _animate_radar(self, step: int) -> None:
        """A beam rotating around the floor center with an afterglow
        trail, like a radar sweep."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        centers = self._get_centers(shape)
        ang = np.arctan2(centers[:, 1] - shape[0] / 2,
                         centers[:, 0] - shape[1] / 2)
        period = 4.0  # s per revolution
        theta = (step * ANIMATION_INTERVAL / period) * 2 * np.pi
        delta = (theta - ang) % (2 * np.pi)  # angle behind the beam
        amp = np.exp(-delta * 2.2)
        color = np.array(self._anim_color, dtype=np.float32)
        pixels = np.clip(amp[:, None] * color, 0, 255)
        c.set_pixels(pixels.astype(np.uint8).reshape(shape))

    def _animate_rainbow(self, step: int) -> None:
        """Hue wave sweeping across the floor in +x direction."""
        c = self.controller
        frame = c.get_frame()
        shape = frame.pixels.shape
        pixels = np.zeros(shape, dtype=np.uint8)
        t = step * 0.02
        for x in range(shape[1]):
            hue = (x / shape[1] + t) % 1.0
            rgb = _hsv_to_rgb(hue)
            pixels[:, x] = rgb
        c.set_pixels(pixels)

    def _animate_plasma(self, step: int) -> None:
        """Classic plasma: layered sine fields mapped onto the hue wheel."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        centers = self._get_centers(shape)
        xs, ys = centers[:, 0], centers[:, 1]
        t = step * ANIMATION_INTERVAL
        v = (
            np.sin(1.1 * xs + 1.6 * t)
            + np.sin(1.5 * ys - 1.2 * t)
            + np.sin(0.9 * (xs + ys) + 0.8 * t)
            + np.sin(np.hypot(xs - shape[1] / 2, ys - shape[0] / 2) * 1.7 - 1.9 * t)
        )
        hue = v / 8.0 + 0.03 * t  # slow global hue drift
        pixels = self._hue_rgb(hue).astype(np.uint8).reshape(shape)
        c.set_pixels(pixels)

    def _animate_scanner(self, step: int) -> None:
        """A bright bar sweeping left-right across the floor."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        centers = self._get_centers(shape)
        xs = centers[:, 0]
        period = 4.0
        phase = (step * ANIMATION_INTERVAL % period) / period
        pos = (2 * phase if phase < 0.5 else 2 - 2 * phase) * shape[1]
        amp = np.exp(-(((xs - pos) / 0.6) ** 2))
        color = np.array(self._anim_color, dtype=np.float32)
        pixels = (amp[:, None] * color).astype(np.uint8).reshape(shape)
        c.set_pixels(pixels)

    def _animate_breathe(self, step: int) -> None:
        """The whole floor breathing in the selected color."""
        period = 4.0
        t = step * ANIMATION_INTERVAL
        level = (1 - math.cos(2 * math.pi * t / period)) / 2
        level = level ** 2.2  # perceptual gamma
        r, g, b = self._anim_color
        self.controller.set_all((int(r * level), int(g * level), int(b * level)))

    def _animate_sparkle(self, step: int) -> None:
        """Random segments flash in the selected color and fade out."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        n = self._get_centers(shape).shape[0]
        if self._sparkle is None or len(self._sparkle) != n:
            self._sparkle = np.zeros(n, dtype=np.float32)
        self._sparkle *= 0.90
        for _ in range(random.randint(1, 2)):
            self._sparkle[random.randrange(n)] = 1.0
        color = np.array(self._anim_color, dtype=np.float32)
        pixels = np.clip(self._sparkle[:, None] * color, 0, 255)
        c.set_pixels(pixels.astype(np.uint8).reshape(shape))

    # --------------------------- tile-grid games -------------------------- #
    def _animate_tetris(self, step: int) -> None:
        """Self-playing Tetris with simplified pieces and an AI solver.
        Gravity points in -x: pieces enter at the right edge and fall
        left; full depth columns clear. The solver picks rotation + lane
        at spawn, so each piece visibly falls straight into its slot."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        ty, tx = shape[0], shape[1]
        if step == 0 or self._tetris is None:
            self._tetris = {'board': np.zeros((ty, tx, 3), np.uint8),
                            'piece': None}
        st = self._tetris
        if step % 3 == 0:
            self._tetris_step(st, ty, tx)
        pixels = np.zeros(shape, dtype=np.uint8)
        locked = (st['board'].astype(np.float32) * 0.8).astype(np.uint8)
        pixels[:, :] = locked[:, :, None, None, :]
        if st['piece'] is not None:
            for x, y in st['piece']['cells']:
                if 0 <= x < tx:
                    pixels[y, x] = st['piece']['color']
        c.set_pixels(pixels)

    def _tetris_step(self, st: dict, ty: int, tx: int) -> None:
        board = st['board']
        if st['piece'] is None:
            st['piece'] = self._tetris_plan(board, ty, tx)
            return
        piece = st['piece']
        piece['idx'] += 1
        if piece['idx'] < len(piece['path']):
            rot, px, py = piece['path'][piece['idx']]
            piece['cells'] = [(px + cx, py + cy)
                              for cx, cy in piece['rots'][rot]]
            return
        # plan finished -> lock the piece
        if any(x >= tx for x, _y in piece['cells']):
            board[:] = 0  # stack reached the spawn edge -> new game
        else:
            for x, y in piece['cells']:
                board[y, x] = piece['color']
            x = 0
            while x < tx:  # clear full depth-columns
                if all(board[yy, x].any() for yy in range(ty)):
                    board[:, x:tx - 1] = board[:, x + 1:tx]
                    board[:, tx - 1] = 0
                else:
                    x += 1
        st['piece'] = None

    def _tetris_plan(self, board, ty: int, tx: int) -> dict:
        """Pick a random piece, then BFS over all states reachable with
        falls, mid-fall slides and in-place rotations (each only into
        free space). Every reachable resting position — including tucks
        under overhangs — is scored; the piece executes the move path to
        the best one, one move per game tick."""
        base, color = _TETRIS_PIECES[random.choice(list(_TETRIS_PIECES))]
        rots = [base]
        r = _rotated(base)
        while frozenset(r) not in {frozenset(c) for c in rots}:
            rots.append(r)
            r = _rotated(r)
        n_rots = len(rots)
        filled = board.any(axis=2)

        def fits(rot, px, py):
            for cx, cy in rots[rot]:
                x, y = px + cx, py + cy
                if y < 0 or y >= ty or x < 0:
                    return False
                if x < tx and filled[y, x]:
                    return False
            return True

        height0 = max(y for _, y in rots[0]) + 1
        start = (0, tx, (ty - height0) // 2)  # spawn offboard, mid lane
        parent = {start: None}
        queue = [start]
        resting = []
        while queue:
            state = queue.pop(0)
            rot, px, py = state
            if not fits(rot, px - 1, py):
                resting.append(state)
            for nxt in (
                (rot, px - 1, py),             # fall
                (rot, px, py - 1),             # slide
                (rot, px, py + 1),             # slide
                ((rot + 1) % n_rots, px, py),  # rotate in place
            ):
                if nxt not in parent and nxt[1] <= tx and fits(*nxt):
                    parent[nxt] = state
                    queue.append(nxt)

        best, best_score = None, None
        for state in resting:
            rot, px, py = state
            landing = [(px + cx, py + cy) for cx, cy in rots[rot]]
            score = self._tetris_rate(filled, landing, ty, tx)
            score += random.random() * 0.01  # tie-break variety
            if best_score is None or score > best_score:
                best, best_score = state, score

        path = []
        s = best
        while s is not None:
            path.append(s)
            s = parent[s]
        path.reverse()
        rot, px, py = path[0]
        return {'path': path, 'idx': 0, 'rots': rots, 'color': color,
                'cells': [(px + cx, py + cy) for cx, cy in rots[rot]]}

    @staticmethod
    def _tetris_rate(filled, landing, ty: int, tx: int) -> float:
        """Rate a locked placement: cleared columns good; stack height,
        buried holes and surface bumpiness bad."""
        if any(x >= tx for x, _ in landing):
            return -1e9  # would top out and end the game
        test = filled.copy()
        for x, y in landing:
            test[y, x] = True
        keep = [x for x in range(tx) if not test[:, x].all()]
        cleared = tx - len(keep)
        if cleared:
            packed = np.zeros_like(test)
            packed[:, :len(keep)] = test[:, keep]
            test = packed

        heights = np.zeros(ty, dtype=int)
        holes = 0
        for y in range(ty):
            xs = np.nonzero(test[y])[0]
            if len(xs):
                heights[y] = xs.max() + 1
                holes += int(heights[y] - len(xs))
        bumpiness = int(np.abs(np.diff(heights)).sum())
        return (8.0 * cleared - 1.0 * float(heights.sum())
                - 5.0 * holes - 0.6 * bumpiness)

    def _animate_life(self, step: int) -> None:
        """Conway's Game of Life, tiles as cells (torus topology), in the
        selected color; newborn cells flash brighter. Reseeds itself on
        extinction or stagnation (still lifes / oscillators)."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        ty, tx = shape[0], shape[1]

        def seed():
            return {'board': np.random.random((ty, tx)) < 0.38,
                    'prev': np.zeros((ty, tx), dtype=bool),
                    'hist': [], 'stale': 0}

        if step == 0 or self._life is None:
            self._life = seed()
        st = self._life
        if step % 12 == 0 and step > 0:  # one generation every ~0.5 s
            a = st['board']
            n = sum(np.roll(np.roll(a, dy, 0), dx, 1).astype(int)
                    for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                    if (dy, dx) != (0, 0))
            new = (n == 3) | (a & (n == 2))
            st['prev'], st['board'] = a, new
            key = new.tobytes()
            st['stale'] = st['stale'] + 1 if key in st['hist'] else 0
            st['hist'] = (st['hist'] + [key])[-8:]
            if not new.any() or st['stale'] >= 6:
                self._life = {**seed(), 'prev': new}
                st = self._life
        color = np.array(self._anim_color, dtype=np.float32)
        newborn = (color + (255 - color) * 0.55).astype(np.uint8)
        alive_c = color.astype(np.uint8)
        born = st['board'] & ~st['prev']
        pixels = np.zeros(shape, dtype=np.uint8)
        for y in range(ty):
            for x in range(tx):
                if st['board'][y, x]:
                    pixels[y, x] = newborn if born[y, x] else alive_c
        c.set_pixels(pixels)

    def _animate_snakes(self, step: int) -> None:
        """Colorful serpents wandering the tile grid, bodies fading
        toward the tail, each with its own slowly drifting hue."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        ty, tx = shape[0], shape[1]
        if step == 0 or self._snakes is None:
            self._snakes = [
                {'body': [(random.randrange(tx), random.randrange(ty))],
                 'hue': j / 3, 'len': 6}
                for j in range(3)
            ]
        if step % 4 == 0:
            for s in self._snakes:
                hx, hy = s['body'][0]
                prev = s['body'][1] if len(s['body']) > 1 else None
                options = [(hx + dx, hy + dy)
                           for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
                options = [(x, y) for x, y in options
                           if 0 <= x < tx and 0 <= y < ty and (x, y) != prev]
                free = [o for o in options if o not in s['body']]
                s['body'].insert(0, random.choice(free or options))
                del s['body'][s['len']:]
                s['hue'] = (s['hue'] + 0.002) % 1.0
        pixels = np.zeros(shape, dtype=np.float32)
        for s in self._snakes:
            r, g, b = _hsv_to_rgb(s['hue'])
            for i, (x, y) in enumerate(s['body']):
                level = (1 - i / s['len']) ** 1.5
                cell = np.array((r * level, g * level, b * level), np.float32)
                pixels[y, x] = np.maximum(pixels[y, x], cell[None, None, :])
        c.set_pixels(pixels.astype(np.uint8))

    def _animate_storm(self, step: int) -> None:
        """Thunderstorm: dark cloud ambience, drizzle on the strips, and
        random lightning — jagged bolts or whole-floor sheet flashes with
        a flickering envelope."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        ty, tx = shape[0], shape[1]
        n = self._get_centers(shape).shape[0]
        if step == 0 or self._storm is None or len(self._storm['rain']) != n:
            self._storm = {'rain': np.zeros(n, dtype=np.float32),
                           'flash': None}
        st = self._storm
        t = step * ANIMATION_INTERVAL

        # heavy, slowly breathing cloud base
        ambient = (np.array((9, 13, 30), dtype=np.float32)
                   * (0.7 + 0.3 * math.sin(t * 0.4)))
        # drizzle on the strips
        st['rain'] *= 0.86
        for _ in range(2):
            if random.random() < 0.8:
                st['rain'][random.randrange(n)] = 0.5
        rain_color = np.array((110, 140, 220), dtype=np.float32)
        flat = ambient[None, :] + st['rain'][:, None] * rain_color[None, :]
        pixels = flat.reshape(shape[:4] + (3,))

        # lightning
        if st['flash'] is None and random.random() < 0.014:
            if random.random() < 0.3:  # sheet lightning: the whole floor
                cells = [(x, y) for x in range(tx) for y in range(ty)]
            else:  # jagged bolt running top to bottom
                cells = []
                x = random.randrange(tx)
                for y in range(ty - 1, -1, -1):
                    nx = min(tx - 1, max(0, x + random.choice((-1, 0, 0, 1))))
                    if nx != x:
                        cells.append((x, y))
                    x = nx
                    cells.append((x, y))
            st['flash'] = {'cells': cells, 'tick': 0,
                           'env': (1.0, 0.3, 0.85, 0.5, 0.25, 0.12, 0.05)}
        if st['flash'] is not None:
            f = st['flash']
            white = np.array((235, 240, 255), np.float32) * f['env'][f['tick']]
            for x, y in f['cells']:
                pixels[y, x] = np.maximum(pixels[y, x], white[None, None, :])
            f['tick'] += 1
            if f['tick'] >= len(f['env']):
                st['flash'] = None
        c.set_pixels(np.clip(pixels, 0, 255).astype(np.uint8))

    # ------------------------------- ripples ------------------------------ #
    def _spawn_ripple(self, x: float, y: float, color) -> None:
        """Add a wave source at world position (x, y) in tile units."""
        shape = self.controller.get_frame().pixels.shape
        centers = self._get_centers(shape)
        dist = np.hypot(centers[:, 0] - x, centers[:, 1] - y)
        self._ripples.append({
            'age': 0.0,
            'dist': dist,
            'max_dist': float(dist.max()),
            'color': np.array(color, dtype=np.float32),
        })

    def _render_ripples(self) -> None:
        """Expanding rings: gaussian ring profile, exponential fade-out."""
        c = self.controller
        shape = c.get_frame().pixels.shape
        n = self._get_centers(shape).shape[0]
        acc = np.zeros((n, 3), dtype=np.float32)
        alive = []
        for rp in self._ripples:
            rp['age'] += ANIMATION_INTERVAL
            envelope = math.exp(-rp['age'] / RIPPLE_TAU)
            radius = RIPPLE_SPEED * rp['age']
            if envelope < 0.02 or radius > rp['max_dist'] + 4 * RIPPLE_WIDTH:
                continue  # fully faded or past every segment -> drop
            amp = np.exp(-(((rp['dist'] - radius) / RIPPLE_WIDTH) ** 2)) * envelope
            acc += amp[:, None] * rp['color']
            alive.append(rp)
        self._ripples = alive
        pixels = np.clip(acc, 0, 255).astype(np.uint8).reshape(shape)
        c.set_pixels(pixels)

    def _animate_ripple(self, step: int) -> None:
        """Interactive mode: waves spawn where clients click the floor."""
        self._render_ripples()

    def _animate_rain(self, step: int) -> None:
        """Random colored drops falling onto the floor (auto-ripples).
        Clicking the floor still adds your own drops."""
        if random.random() < 0.07:
            shape = self.controller.get_frame().pixels.shape
            x = random.uniform(0, shape[1])
            y = random.uniform(0, shape[0])
            color = self._hue_rgb(np.array([random.random()]))[0]
            self._spawn_ripple(x, y, color)
        self._render_ripples()

    # ------------------------------------------------------------------ #
    # Layouts — save/load painted "pictures" as YAML files
    # ------------------------------------------------------------------ #
    def _layout_names(self) -> list[str]:
        return sorted(p.stem for p in self.layouts_dir.glob('*.yaml'))

    def _emit_layouts(self) -> None:
        self.socketio.emit('layouts', {'names': self._layout_names()})

    def _layout_path(self, name: str) -> Path:
        return self.layouts_dir / f'{name}.yaml'

    # ------------------------------------------------------------------ #
    # Blink — flash one tile to locate it on the physical floor
    # ------------------------------------------------------------------ #
    def _blink_task(self, x: int, y: int, blinks: int = 5) -> None:
        c = self.controller
        try:
            saved = c.get_tile_pixels(x, y)
            for _ in range(blinks):
                c.set_tile(x, y, (255, 255, 255))
                self.socketio.sleep(0.18)
                c.set_tile(x, y, (0, 0, 0))
                self.socketio.sleep(0.12)
            c.set_tile_pixels(x, y, saved)
        finally:
            self._blinking.discard((x, y))

    # ------------------------------------------------------------------ #
    # Routes
    # ------------------------------------------------------------------ #
    def _register_routes(self) -> None:
        app = self.app

        @app.route('/')
        def index():
            return send_from_directory(self.static_folder, 'index.html')

        @app.route('/<path:path>')
        def static_files(path):
            return send_from_directory(self.static_folder, path)

        @app.route('/api/config')
        def api_config():
            return jsonify(self._config_dict())

        @app.route('/api/state')
        def api_state():
            return jsonify(self.controller.get_state_dict())

    # ------------------------------------------------------------------ #
    # SocketIO events
    # ------------------------------------------------------------------ #
    def _register_socketio(self) -> None:
        sio = self.socketio
        c = self.controller

        @sio.on('connect')
        def on_connect():
            sio.emit('init', {
                'config': self._config_dict(),
                'state': c.get_state_dict(),
                'animation': self._animation,
                'layouts': self._layout_names(),
            })

        @sio.on('set_segment')
        def on_set_segment(data):
            self._stop_animation()
            c.set_segment(
                int(data['x']), int(data['y']),
                data['edge'], int(data['segment']),
                tuple(data['color']),
            )

        @sio.on('set_edge')
        def on_set_edge(data):
            self._stop_animation()
            c.set_edge(
                int(data['x']), int(data['y']),
                data['edge'], tuple(data['color']),
            )

        @sio.on('set_tile')
        def on_set_tile(data):
            self._stop_animation()
            c.set_tile(int(data['x']), int(data['y']), tuple(data['color']))

        @sio.on('set_all')
        def on_set_all(data):
            self._stop_animation()
            c.set_all(tuple(data['color']))

        @sio.on('clear')
        def on_clear(_data=None):
            self._stop_animation()
            c.clear()

        @sio.on('set_on')
        def on_set_on(data):
            c.set_on(bool(data['on']))

        @sio.on('set_brightness')
        def on_set_brightness(data):
            c.set_brightness(int(data['brightness']))

        @sio.on('set_max_brightness')
        def on_set_max_brightness(data):
            c.set_max_brightness(int(data['max_brightness']))

        @sio.on('set_pattern')
        def on_set_pattern(data):
            name = data['name']
            color = data.get('color')
            if color:
                self._anim_color = tuple(int(v) for v in color)
            if name in ANIMATED_PATTERNS:
                if self._animation is None:
                    c.save_checkpoint()  # one undo step back to pre-animation
                self._start_animation(name)
                sio.emit('animation', {'name': name})
                return
            self._stop_animation()
            sio.emit('animation', {'name': None})
            c.save_checkpoint()
            if name == 'checkerboard':
                c.pattern_checkerboard((255, 255, 255), (0, 0, 40))
            elif name == 'identify_tiles':
                c.pattern_identify_tiles()
            elif name == 'identify_edges':
                c.pattern_identify_edges()

        @sio.on('stop_pattern')
        def on_stop_pattern(_data=None):
            self._stop_animation()
            sio.emit('animation', {'name': None})

        @sio.on('set_anim_color')
        def on_set_anim_color(data):
            # Live color updates: running color-based animations (breathe,
            # sparkle, scanner) read _anim_color every frame.
            self._anim_color = tuple(int(v) for v in data['color'])

        @sio.on('ripple')
        def on_ripple(data):
            color = data.get('color') or self._anim_color
            if self._animation not in ('ripple', 'rain'):
                if self._animation is None:
                    c.save_checkpoint()
                self._start_animation('ripple')
                sio.emit('animation', {'name': 'ripple'})
            self._spawn_ripple(
                float(data['x']), float(data['y']),
                tuple(int(v) for v in color),
            )

        @sio.on('blink')
        def on_blink(data):
            x, y = int(data['x']), int(data['y'])
            self._stop_animation()
            sio.emit('animation', {'name': None})
            if (x, y) in self._blinking:
                return  # already blinking — ignore repeated clicks
            self._blinking.add((x, y))
            sio.start_background_task(self._blink_task, x, y)

        @sio.on('checkpoint')
        def on_checkpoint(_data=None):
            c.save_checkpoint()

        @sio.on('save_layout')
        def on_save_layout(data):
            name = _sanitize_name(data.get('name') or '')
            if not name:
                name = 'layout-' + datetime.now().strftime('%Y%m%d-%H%M%S')
            payload = {
                'name': name,
                'created': datetime.now().isoformat(timespec='seconds'),
                'grid': {'tiles_x': c.config.tiles_x,
                         'tiles_y': c.config.tiles_y},
                # [y][x][edge][segment] = [r, g, b], world frame
                'pixels': c.get_frame().pixels.tolist(),
            }
            with open(self._layout_path(name), 'w') as f:
                yaml.safe_dump(payload, f,
                               default_flow_style=None, sort_keys=False)
            self._emit_layouts()
            sio.emit('layout_msg', {'text': f'Saved "{name}"'})

        @sio.on('load_layout')
        def on_load_layout(data):
            name = _sanitize_name(data['name'])
            try:
                with open(self._layout_path(name)) as f:
                    payload = yaml.safe_load(f)
                pixels = np.array(payload['pixels'], dtype=np.uint8)
                expected = c.get_frame().pixels.shape
                if pixels.shape != expected:
                    raise ValueError(
                        f'grid mismatch: layout is '
                        f'{pixels.shape[1]}x{pixels.shape[0]} tiles, floor '
                        f'is {expected[1]}x{expected[0]}'
                    )
                self._stop_animation()
                sio.emit('animation', {'name': None})
                c.save_checkpoint()  # loading is undoable
                c.set_pixels(pixels)
                sio.emit('layout_msg', {'text': f'Loaded "{name}"'})
            except Exception as e:
                sio.emit('layout_msg', {'text': f'Load failed: {e}'})

        @sio.on('delete_layout')
        def on_delete_layout(data):
            name = _sanitize_name(data['name'])
            self._layout_path(name).unlink(missing_ok=True)
            self._emit_layouts()
            sio.emit('layout_msg', {'text': f'Deleted "{name}"'})

        @sio.on('undo')
        def on_undo(_data=None):
            self._stop_animation()
            sio.emit('animation', {'name': None})
            c.undo()

        @sio.on('redo')
        def on_redo(_data=None):
            self._stop_animation()
            sio.emit('animation', {'name': None})
            c.redo()

    # ------------------------------------------------------------------ #
    # Run
    # ------------------------------------------------------------------ #
    def run(self, debug: bool = False) -> None:
        self._broadcast_task = self.socketio.start_background_task(
            self._broadcast_loop
        )
        print(f"Tile viewer running on http://localhost:{self.port}")
        self.socketio.run(
            self.app,
            host=self.host,
            port=self.port,
            debug=debug,
            allow_unsafe_werkzeug=True,
        )


def _sanitize_name(name: str) -> str:
    """Layout names become filenames — keep them strictly safe."""
    return re.sub(r'[^A-Za-z0-9_\-]+', '_', name.strip())[:40].strip('_')


def _hsv_to_rgb(hue: float) -> tuple[int, int, int]:
    h = (hue % 1.0) * 6
    i = math.floor(h)
    f = h - i
    p, q, t = 0, 1 - f, f
    rgb = [(1, t, p), (q, 1, p), (p, 1, t), (p, q, 1), (t, p, 1), (1, p, q)][int(i) % 6]
    return tuple(int(v * 255) for v in rgb)
