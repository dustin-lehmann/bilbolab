"""
Glue layer: world-frame TileController -> physical QuinLED Dig boards.

All wiring complexity (which output drives which module, module rotation,
tile chain order, strip winding) is resolved ONCE at startup into a lookup
table (LUT) per board: ``lut[chain_position] = flat world pixel index``.
The per-frame path is then two numpy fancy-indexings and one UDP packet
per board.

Conventions
-----------
World frame (see tile_controller.py): tile (0,0) bottom-left, x right,
y up; edges N/E/S/W; segments 0..4 in +x (N/S) / +y (E/W).

Module frame: each module is 2x2 tiles described AS BUILT, before any
rotation. Module-frame tile coords: [0,0] bottom-left .. [1,1] top-right.

`start_edge` + `winding` fully determine a tile's 20-segment chain: the
strip starts at the corner where the winding direction enters that edge.
Examples (tile frame):
    start_edge=S, winding=ccw -> S0..S4, E0..E4, N4..N0, W4..W0
    start_edge=S, winding=cw  -> S4..S0, W0..W4, N0..N4, E4..E0

`rotation` is the placement rotation of the whole module in the world,
in degrees clockwise (0/90/180/270).

Use `identify_tiles` / `identify_edges` patterns on the real floor to
verify the configuration: wrong module positions, rotations or windings
show up immediately.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import yaml
from dacite import from_dict

try:
    from .tile_controller import (
        Edge, TileDriver, TileFrame, TileGridConfig,
        EDGES_PER_TILE, SEGMENTS_PER_EDGE, SEGMENTS_PER_TILE,
        TILES_PER_MODULE_X, TILES_PER_MODULE_Y,
    )
    from .quinled_dig import QuinLEDDig, StripConfig
except ImportError:  # imported as a plain module (scripts in this dir)
    from tile_controller import (
        Edge, TileDriver, TileFrame, TileGridConfig,
        EDGES_PER_TILE, SEGMENTS_PER_EDGE, SEGMENTS_PER_TILE,
        TILES_PER_MODULE_X, TILES_PER_MODULE_Y,
    )
    from quinled_dig import QuinLEDDig, StripConfig


# ---------------------------------------------------------------------- #
# Configuration dataclasses (YAML `mapping:` section via dacite)
# ---------------------------------------------------------------------- #
@dataclass
class WiringConfig:
    """How a module is wired internally, in the module frame."""
    tile_order: list[list[int]]  # chain order of module-frame tile coords
    start_edge: str = 'S'        # first wired edge of each tile: N|E|S|W
    winding: str = 'ccw'         # strip direction around each tile: cw|ccw


@dataclass
class OutputConfig:
    strip: str                       # QuinLEDDig strip name == WLED output
    module: list[int]                # module grid position [mx, my]
    rotation: int = 0                # placement rotation, deg cw: 0/90/180/270
    wiring: Optional[WiringConfig] = None  # override if built differently


@dataclass
class ControllerConfig:
    name: str
    host: str
    outputs: list[OutputConfig]      # ORDER must match WLED's output order!
    port: int = 80
    udp_port: int = 21324
    max_channel_sum: int = 765       # per-LED power cap (see StripConfig)


@dataclass
class TileMappingConfig:
    wiring: WiringConfig             # default wiring for all modules
    controllers: list[ControllerConfig]

    @classmethod
    def from_yaml(cls, path: str) -> 'TileMappingConfig':
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        return from_dict(data_class=cls, data=data['mapping'])


# ---------------------------------------------------------------------- #
# Geometry: tile chain + rotation transforms
# ---------------------------------------------------------------------- #
def _cw_ring() -> list[tuple[int, int]]:
    """Clockwise perimeter as (edge, segment) pairs in world-style indices:
    N 0->4 (left to right along the top), E 4->0 (down), S 4->0 (right to
    left), W 0->4 (up, back to the start corner)."""
    n = SEGMENTS_PER_EDGE
    ring = [(0, s) for s in range(n)]
    ring += [(1, s) for s in reversed(range(n))]
    ring += [(2, s) for s in reversed(range(n))]
    ring += [(3, s) for s in range(n)]
    return ring


def tile_chain(start_edge: Edge, winding: str) -> list[tuple[int, int]]:
    """The 20 (edge, segment) pairs of one tile in wire order (tile frame).

    The chain starts at the first segment of `start_edge` in the winding
    direction (i.e. at the corner where the winding enters that edge).
    """
    if winding not in ('cw', 'ccw'):
        raise ValueError(f"winding must be 'cw' or 'ccw', got {winding!r}")
    ring = _cw_ring()
    if winding == 'ccw':
        ring = list(reversed(ring))
    k = next(i for i, (e, _) in enumerate(ring) if e == int(start_edge))
    return ring[k:] + ring[:k]


def rotate_edge_seg(edge: int, seg: int, steps: int) -> tuple[int, int]:
    """Rotate a tile-frame (edge, segment) by `steps` x 90 deg clockwise.

    World segment indices always run +x (N/S) and +y (E/W) while the
    physical strip direction rotates with the module, so N/S edges flip
    their segment index on each step (derived from direction vectors:
    e.g. tile +x -> world -y under one cw step).
    """
    for _ in range(steps % 4):
        if edge in (0, 2):  # N, S
            seg = SEGMENTS_PER_EDGE - 1 - seg
        edge = (edge + 1) % 4
    return edge, seg


def rotate_module_coord(x: int, y: int, steps: int) -> tuple[int, int]:
    """Rotate a module-frame tile coord (2x2 footprint) by steps x 90 cw."""
    for _ in range(steps % 4):
        x, y = y, TILES_PER_MODULE_X - 1 - x
    return x, y


# ---------------------------------------------------------------------- #
# LUT builder + validation
# ---------------------------------------------------------------------- #
def build_luts(grid: TileGridConfig,
               mapping: TileMappingConfig) -> dict[str, np.ndarray]:
    """Per controller: array of flat world pixel indices in chain order.

    Flat index = ((y * tiles_x + x) * 4 + edge) * 5 + segment, i.e. the
    order of TileFrame.pixels.reshape(-1, 3).
    """
    luts: dict[str, np.ndarray] = {}
    for ctrl in mapping.controllers:
        indices: list[int] = []
        for out in ctrl.outputs:
            wiring = out.wiring or mapping.wiring
            if out.rotation % 90 != 0:
                raise ValueError(
                    f"{ctrl.name}/{out.strip}: rotation must be a multiple "
                    f"of 90, got {out.rotation}"
                )
            steps = (out.rotation // 90) % 4
            mx, my = out.module
            if not (0 <= mx < grid.modules_x and 0 <= my < grid.modules_y):
                raise ValueError(
                    f"{ctrl.name}/{out.strip}: module {out.module} outside "
                    f"grid {grid.modules_x}x{grid.modules_y}"
                )
            chain = tile_chain(Edge.parse(wiring.start_edge), wiring.winding)
            for coord in wiring.tile_order:
                ox, oy = rotate_module_coord(coord[0], coord[1], steps)
                wx = mx * TILES_PER_MODULE_X + ox
                wy = my * TILES_PER_MODULE_Y + oy
                for edge, seg in chain:
                    we, ws = rotate_edge_seg(edge, seg, steps)
                    indices.append(
                        ((wy * grid.tiles_x + wx) * EDGES_PER_TILE + we)
                        * SEGMENTS_PER_EDGE + ws
                    )
        luts[ctrl.name] = np.array(indices, dtype=np.int64)
    return luts


def _decode(grid: TileGridConfig, flat: int) -> str:
    s = flat % SEGMENTS_PER_EDGE
    flat //= SEGMENTS_PER_EDGE
    e = flat % EDGES_PER_TILE
    flat //= EDGES_PER_TILE
    x = flat % grid.tiles_x
    y = flat // grid.tiles_x
    return f"tile({x},{y}).{'NESW'[e]}{s}"


def validate_luts(grid: TileGridConfig, luts: dict[str, np.ndarray],
                  require_full: bool = True) -> None:
    """Assert the mapping is a bijection onto the world segments.

    With require_full=False only duplicates are rejected — useful while
    commissioning with a subset of the boards connected.
    """
    total = grid.tiles_x * grid.tiles_y * SEGMENTS_PER_TILE
    all_idx = (np.concatenate(list(luts.values()))
               if luts else np.array([], dtype=np.int64))
    unique, counts = np.unique(all_idx, return_counts=True)
    dups = unique[counts > 1]
    if dups.size:
        names = ', '.join(_decode(grid, int(i)) for i in dups[:8])
        raise ValueError(
            f"Mapping assigns {dups.size} world segment(s) more than once: "
            f"{names}{' ...' if dups.size > 8 else ''}"
        )
    if require_full and unique.size != total:
        missing = sorted(set(range(total)) - set(unique.tolist()))
        names = ', '.join(_decode(grid, i) for i in missing[:8])
        raise ValueError(
            f"Mapping covers only {unique.size}/{total} world segments; "
            f"missing e.g. {names}{' ...' if len(missing) > 8 else ''}"
        )


# ---------------------------------------------------------------------- #
# The driver
# ---------------------------------------------------------------------- #
class QuinLEDTileDriver(TileDriver):
    """TileDriver that renders world-frame frames onto QuinLED Dig boards.

    Brightness, max-brightness ceiling and the on-flag are baked into the
    pixel values via TileFrame.composited(); the boards' own master
    brightness is pinned to 255 by init_realtime().
    """

    def __init__(
        self,
        grid: TileGridConfig,
        mapping: TileMappingConfig,
        connect: bool = True,
        strict: bool = True,
        keepalive_s: float = 60.0,
    ) -> None:
        self.grid = grid
        self.mapping = mapping
        luts = build_luts(grid, mapping)
        validate_luts(grid, luts, require_full=strict)

        self._boards: list[tuple[str, QuinLEDDig, np.ndarray]] = []
        for ctrl in mapping.controllers:
            strips = [
                StripConfig(
                    name=out.strip,
                    length=len((out.wiring or mapping.wiring).tile_order)
                    * SEGMENTS_PER_TILE,
                    max_channel_sum=ctrl.max_channel_sum,
                )
                for out in ctrl.outputs
            ]
            board = QuinLEDDig(
                host=ctrl.host, strips=strips,
                port=ctrl.port, udp_port=ctrl.udp_port,
            )
            self._boards.append((ctrl.name, board, luts[ctrl.name]))

        self._lock = threading.Lock()
        self._last_frame: np.ndarray | None = None
        self._last_send = 0.0
        self._closed = False
        self._send_warned: set[str] = set()

        if connect:
            for name, board, _ in self._boards:
                try:
                    board.init_realtime()
                except Exception as e:
                    print(f"[QuinLEDTileDriver] WARNING: init_realtime "
                          f"failed for {name} ({board.host}): {e}")

        # Re-send the last frame periodically so WLED never drops out of
        # realtime mode while the floor is static.
        if keepalive_s:
            self._keepalive_s = keepalive_s
            threading.Thread(
                target=self._keepalive_loop, daemon=True,
                name='QuinLEDTileDriver-keepalive',
            ).start()

    @classmethod
    def from_yaml(cls, path: str, **kwargs) -> 'QuinLEDTileDriver':
        """Build from tiles.yaml (reads the `grid:` and `mapping:` sections)."""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        grid = from_dict(data_class=TileGridConfig, data=data['grid'])
        mapping = from_dict(data_class=TileMappingConfig, data=data['mapping'])
        return cls(grid, mapping, **kwargs)

    # ------------------------------- output ------------------------------- #
    def update(self, frame: TileFrame) -> None:
        self._send(frame.composited().reshape(-1, 3))

    def _send(self, flat: np.ndarray) -> None:
        with self._lock:
            for name, board, lut in self._boards:
                try:
                    board.show_frame(flat[lut])
                    self._send_warned.discard(name)
                except OSError as e:
                    # Board unreachable/unresolvable — warn once, keep the
                    # rest of the floor (and the viewer) running.
                    if name not in self._send_warned:
                        self._send_warned.add(name)
                        print(f"[QuinLEDTileDriver] WARNING: send to {name} "
                              f"({board.host}) failed: {e}")
            self._last_frame = flat
            self._last_send = time.time()

    def _keepalive_loop(self) -> None:
        while not self._closed:
            time.sleep(1.0)
            if (self._last_frame is not None
                    and time.time() - self._last_send > self._keepalive_s):
                try:
                    self._send(self._last_frame)
                except Exception:
                    pass  # board offline — keep trying, UDP is cheap

    def close(self) -> None:
        self._closed = True
        for _name, board, _ in self._boards:
            try:
                board.all_off()
            except Exception:
                pass

    # ----------------------------- diagnostics ---------------------------- #
    def test_connection(self, verbose: bool = True) -> bool:
        ok = True
        for name, board, _ in self._boards:
            if verbose:
                print(f"--- {name} ({board.host}) ---")
            ok &= board.test_connection(verbose=verbose)
        return ok

    def power_report(self) -> str:
        return '\n'.join(
            f"{name}:\n{board.power_report()}"
            for name, board, _ in self._boards
        )
