"""
World-frame tile LED controller for the IdeenExpo 2026 lighted floor.

Geometry
--------
- The floor is a grid of modules; each module carries 2x2 tiles.
- Each tile is 0.5 m x 0.5 m and is framed by a WS2811 strip (60 LED/m,
  6 physical LEDs per IC -> 1 logical LED per 10 cm). Each tile edge
  therefore has 5 logical LEDs ("segments"); a tile has 4 edges = 20
  segments; a module has 4 tiles = 80 segments per QuinLED output.

Coordinate convention (world frame)
-----------------------------------
- Tile (0, 0) is the bottom-left tile; x grows to the right, y grows up.
- Edges are named by compass direction in the world frame: NORTH (top),
  EAST (right), SOUTH (bottom), WEST (left).
- Segment indices run 0..4 in +x direction on NORTH/SOUTH edges and in
  +y direction on EAST/WEST edges.

This is deliberately NOT the chain/wiring order. Physical wiring (which
QuinLED output, chain position within a module, module rotation, winding
direction around a tile) is resolved by a mapping/glue layer that
implements `TileDriver` and translates world-frame frames into per-output
pixel arrays for `quinled_dig.QuinLEDDig`.

Usage
-----
    controller = TileController(TileGridConfig(modules_x=4, modules_y=2))
    controller.set_all((30, 30, 30))
    controller.set_tile(0, 0, (255, 0, 0))
    controller.set_edge(2, 1, Edge.NORTH, (0, 255, 0))
    controller.set_segment(7, 3, 'W', 4, (0, 0, 255))

    with controller.batch():        # one driver update for many changes
        for x in range(controller.tiles_x):
            controller.set_tile(x, 0, (0, 40, 80))

Drivers and listeners are notified with a `TileFrame` (copy of the state)
on every change. In "mock-up mode" simply attach no hardware driver — the
web viewer subscribes as a listener and shows the state regardless.
"""

from __future__ import annotations

import colorsys
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Union

import numpy as np
import yaml
from dacite import from_dict

Color = tuple[int, int, int]

SEGMENTS_PER_EDGE = 5
EDGES_PER_TILE = 4
SEGMENTS_PER_TILE = EDGES_PER_TILE * SEGMENTS_PER_EDGE  # 20
TILES_PER_MODULE_X = 2
TILES_PER_MODULE_Y = 2


# ---------------------------------------------------------------------- #
# Geometry definitions
# ---------------------------------------------------------------------- #
class Edge(IntEnum):
    """Tile edge in the world frame (not wiring order)."""
    NORTH = 0
    EAST = 1
    SOUTH = 2
    WEST = 3

    @classmethod
    def parse(cls, value: Union['Edge', int, str]) -> 'Edge':
        """Accept Edge, int, or names/aliases like 'N', 'north', 'top'."""
        if isinstance(value, Edge):
            return value
        if isinstance(value, int):
            return cls(value)
        name = str(value).strip().upper()
        aliases = {
            'N': 'NORTH', 'E': 'EAST', 'S': 'SOUTH', 'W': 'WEST',
            'TOP': 'NORTH', 'RIGHT': 'EAST', 'BOTTOM': 'SOUTH', 'LEFT': 'WEST',
        }
        try:
            return cls[aliases.get(name, name)]
        except KeyError:
            raise ValueError(f"Unknown edge {value!r}") from None


@dataclass
class TileGridConfig:
    modules_x: int = 4
    modules_y: int = 2
    tile_size: float = 0.5  # m, informational (webapp scaling, future maps)
    # Global output ceiling (0..255): everything is scaled by
    # max_brightness/255 on top of the runtime master brightness.
    # Power/eye safety knob for the exhibition.
    max_brightness: int = 255

    @property
    def tiles_x(self) -> int:
        return self.modules_x * TILES_PER_MODULE_X

    @property
    def tiles_y(self) -> int:
        return self.modules_y * TILES_PER_MODULE_Y

    @classmethod
    def from_yaml(cls, path: str) -> 'TileGridConfig':
        """Load from a YAML file with a top-level `grid:` section."""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        return from_dict(data_class=cls, data=data['grid'])


@dataclass
class TileFrame:
    """Snapshot of the controller state handed to drivers/listeners.

    `pixels` has shape (tiles_y, tiles_x, EDGES_PER_TILE, SEGMENTS_PER_EDGE, 3),
    dtype uint8, indexed [y, x, edge, segment] in the world frame. It holds
    the *intended* colors; `on`/`brightness` are kept separate so views can
    show the painted state even while the output is blanked or dimmed.
    """
    pixels: np.ndarray
    on: bool
    brightness: int  # 0..255 master brightness
    max_brightness: int  # 0..255 global output ceiling

    def composited(self) -> np.ndarray:
        """Pixels with on/brightness/ceiling applied — what the LEDs show."""
        if not self.on:
            return np.zeros_like(self.pixels)
        scale = (self.brightness / 255.0) * (self.max_brightness / 255.0)
        if scale <= 0.0:
            return np.zeros_like(self.pixels)
        if scale >= 1.0:
            return self.pixels.copy()
        return (self.pixels.astype(np.float32) * scale).astype(np.uint8)


# ---------------------------------------------------------------------- #
# Driver interface
# ---------------------------------------------------------------------- #
class TileDriver(ABC):
    """Output backend for a TileController.

    Implementations translate the world-frame `TileFrame` into hardware
    commands (e.g. the QuinLED mapping/glue layer) or into a view.
    """

    @abstractmethod
    def update(self, frame: TileFrame) -> None:
        ...

    def close(self) -> None:
        pass


class MockTileDriver(TileDriver):
    """No hardware — stores the last frame, optionally prints a summary."""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.last_frame: TileFrame | None = None
        self.update_count = 0

    def update(self, frame: TileFrame) -> None:
        self.last_frame = frame
        self.update_count += 1
        if self.verbose:
            lit = int(np.count_nonzero(frame.pixels.any(axis=-1)))
            total = frame.pixels.shape[0] * frame.pixels.shape[1] * SEGMENTS_PER_TILE
            print(
                f"[MockTileDriver] update #{self.update_count}: "
                f"on={frame.on} brightness={frame.brightness} "
                f"lit_segments={lit}/{total}"
            )


# ---------------------------------------------------------------------- #
# Controller
# ---------------------------------------------------------------------- #
class TileController:
    """Holds the intended LED state of the whole floor in the world frame.

    Pure model: no networking, no hardware. Attach `TileDriver`s and/or
    plain listener callables; they are notified with a `TileFrame` copy
    after every change (or once per `batch()` block). Thread-safe.
    """

    def __init__(self, config: TileGridConfig | None = None) -> None:
        self.config = config or TileGridConfig()
        self._pixels = np.zeros(
            (self.config.tiles_y, self.config.tiles_x,
             EDGES_PER_TILE, SEGMENTS_PER_EDGE, 3),
            dtype=np.uint8,
        )
        self._on = True
        self._brightness = 255
        self._max_brightness = max(0, min(255, int(self.config.max_brightness)))

        self._lock = threading.RLock()
        self._drivers: list[TileDriver] = []
        self._listeners: list[Callable[[TileFrame], None]] = []
        self._batch_depth = 0
        self._batch_dirty = False
        self._undo_stack: list[np.ndarray] = []
        self._redo_stack: list[np.ndarray] = []

    # ------------------------------ geometry ------------------------------ #
    @property
    def tiles_x(self) -> int:
        return self.config.tiles_x

    @property
    def tiles_y(self) -> int:
        return self.config.tiles_y

    @property
    def on(self) -> bool:
        return self._on

    @property
    def brightness(self) -> int:
        return self._brightness

    @property
    def max_brightness(self) -> int:
        return self._max_brightness

    def _check_tile(self, x: int, y: int) -> None:
        if not (0 <= x < self.tiles_x and 0 <= y < self.tiles_y):
            raise IndexError(
                f"Tile ({x}, {y}) out of range "
                f"(0..{self.tiles_x - 1}, 0..{self.tiles_y - 1})"
            )

    # --------------------------- driver/listener -------------------------- #
    def attach_driver(self, driver: TileDriver) -> None:
        with self._lock:
            self._drivers.append(driver)
        driver.update(self.get_frame())

    def detach_driver(self, driver: TileDriver) -> None:
        with self._lock:
            self._drivers.remove(driver)

    def add_listener(self, listener: Callable[[TileFrame], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[TileFrame], None]) -> None:
        with self._lock:
            self._listeners.remove(listener)

    def close(self) -> None:
        with self._lock:
            drivers = list(self._drivers)
        for driver in drivers:
            driver.close()

    # ------------------------------- setters ------------------------------ #
    def set_segment(self, x: int, y: int, edge: Union[Edge, int, str],
                    segment: int, color: Color) -> None:
        """Set one logical LED (6 physical LEDs / 10 cm)."""
        self._check_tile(x, y)
        e = Edge.parse(edge)
        if not 0 <= segment < SEGMENTS_PER_EDGE:
            raise IndexError(
                f"Segment {segment} out of range (0..{SEGMENTS_PER_EDGE - 1})"
            )
        with self._lock:
            self._pixels[y, x, e, segment] = _clamp_color(color)
            self._changed()

    def set_edge(self, x: int, y: int, edge: Union[Edge, int, str],
                 color: Color) -> None:
        """Set all 5 segments of one tile edge."""
        self._check_tile(x, y)
        e = Edge.parse(edge)
        with self._lock:
            self._pixels[y, x, e, :] = _clamp_color(color)
            self._changed()

    def set_tile(self, x: int, y: int, color: Color) -> None:
        """Set all 20 segments of one tile."""
        self._check_tile(x, y)
        with self._lock:
            self._pixels[y, x] = _clamp_color(color)
            self._changed()

    def set_tile_pixels(self, x: int, y: int, pixels: np.ndarray) -> None:
        """Overwrite one tile's pixels, shape (4, 5, 3) — counterpart of
        get_tile_pixels()."""
        self._check_tile(x, y)
        pixels = np.asarray(pixels, dtype=np.uint8)
        expected = (EDGES_PER_TILE, SEGMENTS_PER_EDGE, 3)
        if pixels.shape != expected:
            raise ValueError(f"Expected shape {expected}, got {pixels.shape}")
        with self._lock:
            self._pixels[y, x] = pixels
            self._changed()

    def set_all(self, color: Color) -> None:
        with self._lock:
            self._pixels[:] = _clamp_color(color)
            self._changed()

    def clear(self) -> None:
        self.set_all((0, 0, 0))

    def set_pixels(self, pixels: np.ndarray) -> None:
        """Overwrite the full frame (for animations / generated content)."""
        if pixels.shape != self._pixels.shape:
            raise ValueError(
                f"Expected shape {self._pixels.shape}, got {pixels.shape}"
            )
        with self._lock:
            self._pixels[:] = pixels
            self._changed()

    def set_on(self, on: bool) -> None:
        """Blank/unblank the output without losing the painted state."""
        with self._lock:
            self._on = bool(on)
            self._changed()

    def all_on(self) -> None:
        self.set_on(True)

    def all_off(self) -> None:
        self.set_on(False)

    def set_brightness(self, brightness: int) -> None:
        with self._lock:
            self._brightness = max(0, min(255, int(brightness)))
            self._changed()

    def set_max_brightness(self, max_brightness: int) -> None:
        """Global output ceiling applied on top of the master brightness."""
        with self._lock:
            self._max_brightness = max(0, min(255, int(max_brightness)))
            self._changed()

    # ------------------------------- getters ------------------------------ #
    def get_segment(self, x: int, y: int, edge: Union[Edge, int, str],
                    segment: int) -> Color:
        self._check_tile(x, y)
        e = Edge.parse(edge)
        with self._lock:
            return tuple(int(v) for v in self._pixels[y, x, e, segment])

    def get_tile_pixels(self, x: int, y: int) -> np.ndarray:
        """Copy of one tile's pixels, shape (4, 5, 3)."""
        self._check_tile(x, y)
        with self._lock:
            return self._pixels[y, x].copy()

    def get_frame(self) -> TileFrame:
        with self._lock:
            return TileFrame(
                pixels=self._pixels.copy(),
                on=self._on,
                brightness=self._brightness,
                max_brightness=self._max_brightness,
            )

    def get_state_dict(self) -> dict:
        """JSON-serializable snapshot (used by the web viewer)."""
        frame = self.get_frame()
        return {
            'on': frame.on,
            'brightness': frame.brightness,
            'max_brightness': frame.max_brightness,
            'pixels': frame.pixels.tolist(),
        }

    # -------------------------------- undo -------------------------------- #
    UNDO_DEPTH = 50

    def save_checkpoint(self) -> None:
        """Snapshot the current pixels onto the undo stack.

        Callers decide what one undo step is — e.g. the web viewer
        checkpoints once per paint stroke, not per segment.
        """
        with self._lock:
            self._undo_stack.append(self._pixels.copy())
            if len(self._undo_stack) > self.UNDO_DEPTH:
                self._undo_stack.pop(0)
            self._redo_stack.clear()

    def undo(self) -> bool:
        """Restore the most recent checkpoint. Returns False if none left."""
        with self._lock:
            if not self._undo_stack:
                return False
            self._redo_stack.append(self._pixels.copy())
            self._pixels[:] = self._undo_stack.pop()
            self._changed()
        return True

    def redo(self) -> bool:
        with self._lock:
            if not self._redo_stack:
                return False
            self._undo_stack.append(self._pixels.copy())
            self._pixels[:] = self._redo_stack.pop()
            self._changed()
        return True

    # ------------------------------- batching ----------------------------- #
    @contextmanager
    def batch(self):
        """Suppress driver/listener updates until the block ends.

        Nested batches are allowed; notification fires once at the
        outermost exit (and only if something actually changed).
        """
        with self._lock:
            self._batch_depth += 1
        try:
            yield self
        finally:
            notify = False
            with self._lock:
                self._batch_depth -= 1
                if self._batch_depth == 0 and self._batch_dirty:
                    self._batch_dirty = False
                    notify = True
            if notify:
                self._notify()

    def _changed(self) -> None:
        # Called with the lock held by every mutating method.
        if self._batch_depth > 0:
            self._batch_dirty = True
        else:
            self._notify()

    def _notify(self) -> None:
        frame = self.get_frame()
        with self._lock:
            targets = [d.update for d in self._drivers] + list(self._listeners)
        for target in targets:
            target(frame)

    # ---------------------------- test patterns --------------------------- #
    # Static patterns for checking the floor and (later) verifying the
    # physical wiring/mapping against the world frame.

    def pattern_checkerboard(self, color_a: Color = (255, 255, 255),
                             color_b: Color = (0, 0, 0)) -> None:
        """Tile-parity checkerboard."""
        with self.batch():
            for y in range(self.tiles_y):
                for x in range(self.tiles_x):
                    self.set_tile(x, y, color_a if (x + y) % 2 == 0 else color_b)

    def pattern_identify_tiles(self) -> None:
        """One color per module, dot count per tile.

        Each module shows a distinct high-contrast color. Within a module
        each tile lights 1..4 segments per edge: 1 = bottom-left,
        2 = bottom-right, 3 = top-left, 4 = top-right (world frame).
        On the physical floor a wrong module position shows as a wrong
        color; a wrong rotation or tile chain order shows as the wrong
        dot count in the wrong corner of the module.
        """
        palette = [
            (255, 0, 0), (0, 255, 0), (0, 90, 255), (255, 200, 0),
            (0, 255, 255), (255, 0, 255), (255, 100, 0), (255, 255, 255),
        ]
        dots = {1: (2,), 2: (1, 3), 3: (0, 2, 4), 4: (0, 1, 3, 4)}
        with self.batch():
            self.set_all((0, 0, 0))
            for y in range(self.tiles_y):
                for x in range(self.tiles_x):
                    mx = x // TILES_PER_MODULE_X
                    my = y // TILES_PER_MODULE_Y
                    color = palette[
                        (my * self.config.modules_x + mx) % len(palette)
                    ]
                    count = (1 + (x % TILES_PER_MODULE_X)
                             + TILES_PER_MODULE_X * (y % TILES_PER_MODULE_Y))
                    for edge in Edge:
                        for s in dots[count]:
                            self.set_segment(x, y, edge, s, color)

    def pattern_identify_edges(self) -> None:
        """Color-code edges and ramp brightness along the segments.

        NORTH=red, EAST=green, SOUTH=blue, WEST=yellow; each edge ramps
        dark -> bright from segment 0 to 4. On the physical floor this
        reveals module rotation and strip winding direction at a glance.
        """
        edge_colors = {
            Edge.NORTH: (255, 0, 0),
            Edge.EAST: (0, 255, 0),
            Edge.SOUTH: (0, 0, 255),
            Edge.WEST: (255, 200, 0),
        }
        with self.batch():
            for y in range(self.tiles_y):
                for x in range(self.tiles_x):
                    for edge, color in edge_colors.items():
                        for seg in range(SEGMENTS_PER_EDGE):
                            level = 0.25 + 0.75 * seg / (SEGMENTS_PER_EDGE - 1)
                            self.set_segment(
                                x, y, edge, seg,
                                tuple(int(c * level) for c in color),
                            )


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _clamp_color(color: Color) -> tuple[int, int, int]:
    r, g, b = color
    return (
        max(0, min(255, int(r))),
        max(0, min(255, int(g))),
        max(0, min(255, int(b))),
    )


def _hsv(hue: float, saturation: float = 1.0, value: float = 1.0) -> Color:
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, saturation, value)
    return (int(r * 255), int(g * 255), int(b * 255))
