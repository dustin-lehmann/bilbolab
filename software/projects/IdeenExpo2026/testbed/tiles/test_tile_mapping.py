"""
Offline tests for the QuinLED glue layer (no hardware required).

    cd testbed/tiles && python3 -m pytest test_tile_mapping.py -v

The end-to-end tests use real QuinLEDDig instances pointed at 127.0.0.1
(UDP is fire-and-forget) with connect=False, and inspect the boards'
internal pixel buffers.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tile_controller import Edge, TileController, TileGridConfig
from tile_mapping import (
    ControllerConfig, OutputConfig, QuinLEDTileDriver, TileMappingConfig,
    WiringConfig, build_luts, rotate_edge_seg, rotate_module_coord,
    tile_chain, validate_luts,
)

N, E, S, W = 0, 1, 2, 3


# ---------------------------------------------------------------------- #
# Chain + rotation conventions
# ---------------------------------------------------------------------- #
def test_tile_chain_s_ccw():
    chain = tile_chain(Edge.SOUTH, 'ccw')
    expected = (
        [(S, s) for s in range(5)]
        + [(E, s) for s in range(5)]
        + [(N, s) for s in reversed(range(5))]
        + [(W, s) for s in reversed(range(5))]
    )
    assert chain == expected


def test_tile_chain_s_cw():
    chain = tile_chain(Edge.SOUTH, 'cw')
    expected = (
        [(S, s) for s in reversed(range(5))]
        + [(W, s) for s in range(5)]
        + [(N, s) for s in range(5)]
        + [(E, s) for s in reversed(range(5))]
    )
    assert chain == expected


def test_tile_chain_covers_all_segments():
    for edge in (Edge.NORTH, Edge.EAST, Edge.SOUTH, Edge.WEST):
        for winding in ('cw', 'ccw'):
            chain = tile_chain(edge, winding)
            assert len(chain) == 20
            assert len(set(chain)) == 20
            assert chain[0][0] == int(edge)


def test_rotate_edge_seg():
    # identity
    assert rotate_edge_seg(N, 1, 0) == (N, 1)
    assert rotate_edge_seg(E, 2, 4) == (E, 2)
    # one cw step: N->E reversed, E->S kept, S->W reversed, W->N kept
    assert rotate_edge_seg(N, 1, 1) == (E, 3)
    assert rotate_edge_seg(E, 2, 1) == (S, 2)
    assert rotate_edge_seg(S, 0, 1) == (W, 4)
    assert rotate_edge_seg(W, 3, 1) == (N, 3)
    # 180: every edge maps to its opposite, every index reversed
    for edge in range(4):
        for seg in range(5):
            e2, s2 = rotate_edge_seg(edge, seg, 2)
            assert e2 == (edge + 2) % 4
            assert s2 == 4 - seg


def test_rotate_module_coord():
    assert rotate_module_coord(0, 0, 1) == (0, 1)
    assert rotate_module_coord(1, 0, 1) == (0, 0)
    assert rotate_module_coord(1, 1, 1) == (1, 0)
    assert rotate_module_coord(0, 1, 1) == (1, 1)
    assert rotate_module_coord(1, 0, 4) == (1, 0)


# ---------------------------------------------------------------------- #
# LUT building + validation
# ---------------------------------------------------------------------- #
def _mapping(rotations=(0,) * 8, wiring=None):
    """4x2-module mapping: quinled1 = bottom row, quinled2 = top row."""
    wiring = wiring or WiringConfig(
        tile_order=[[0, 0], [1, 0], [1, 1], [0, 1]],
        start_edge='S', winding='ccw',
    )
    return TileMappingConfig(
        wiring=wiring,
        controllers=[
            ControllerConfig(
                name='quinled1', host='127.0.0.1',
                outputs=[
                    OutputConfig(strip=f'strip{i + 1}', module=[i, 0],
                                 rotation=rotations[i])
                    for i in range(4)
                ],
            ),
            ControllerConfig(
                name='quinled2', host='127.0.0.1',
                outputs=[
                    OutputConfig(strip=f'strip{i + 1}', module=[i, 1],
                                 rotation=rotations[4 + i])
                    for i in range(4)
                ],
            ),
        ],
    )


GRID = TileGridConfig(modules_x=4, modules_y=2)


def test_luts_bijection_default():
    luts = build_luts(GRID, _mapping())
    assert all(len(lut) == 4 * 80 for lut in luts.values())
    validate_luts(GRID, luts)  # raises on any gap/duplicate


def test_luts_bijection_all_rotations_and_windings():
    for winding in ('cw', 'ccw'):
        for start_edge in 'NESW':
            wiring = WiringConfig(
                tile_order=[[0, 0], [1, 0], [1, 1], [0, 1]],
                start_edge=start_edge, winding=winding,
            )
            mapping = _mapping(rotations=(0, 90, 180, 270, 90, 270, 180, 0),
                               wiring=wiring)
            validate_luts(GRID, build_luts(GRID, mapping))


def test_validate_rejects_duplicates():
    mapping = _mapping()
    mapping.controllers[1].outputs[0].module = [0, 0]  # collides with quinled1
    with pytest.raises(ValueError, match='more than once'):
        validate_luts(GRID, build_luts(GRID, mapping))


def test_validate_partial_setup():
    mapping = _mapping()
    mapping.controllers = mapping.controllers[:1]  # only the bottom row
    luts = build_luts(GRID, mapping)
    with pytest.raises(ValueError, match='missing'):
        validate_luts(GRID, luts, require_full=True)
    validate_luts(GRID, luts, require_full=False)  # ok while commissioning


def test_yaml_config_loads_and_validates():
    path = Path(__file__).resolve().parent / 'config' / 'tiles.yaml'
    driver = QuinLEDTileDriver.from_yaml(
        str(path), connect=False, keepalive_s=0)
    assert len(driver._boards) == 2


# ---------------------------------------------------------------------- #
# End-to-end: world segment -> chain position on the board
# ---------------------------------------------------------------------- #
def _driver(rotations=(0,) * 8):
    return QuinLEDTileDriver(GRID, _mapping(rotations=rotations),
                             connect=False, keepalive_s=0)


def _board(driver, name):
    return next(b for n, b, _ in driver._boards if n == name)


def test_first_chain_led_unrotated():
    """Module [0,0], rot 0, start S+ccw: chain LED 0 == world (0,0).S0."""
    driver = _driver()
    controller = TileController(GRID)
    controller.set_segment(0, 0, 'S', 0, (255, 0, 0))
    driver.update(controller.get_frame())
    board = _board(driver, 'quinled1')
    assert board._pixel_buf['strip1'][0] == (255, 0, 0)
    assert sum(c != (0, 0, 0) for buf in board._pixel_buf.values()
               for c in buf) == 1


def test_first_chain_led_rotated_90():
    """Module [1,0] rotated 90 cw: module-frame tile (0,0) lands at world
    tile (2,1); chain entry (S,0) becomes world (W,4)."""
    driver = _driver(rotations=(0, 90, 0, 0, 0, 0, 0, 0))
    controller = TileController(GRID)
    controller.set_segment(2, 1, 'W', 4, (0, 255, 0))
    driver.update(controller.get_frame())
    board = _board(driver, 'quinled1')
    assert board._pixel_buf['strip2'][0] == (0, 255, 0)


def test_chain_walks_whole_module():
    """Chain LEDs 0..19 = first tile, 20..39 = second tile, etc."""
    driver = _driver()
    controller = TileController(GRID)
    controller.set_tile(1, 0, (0, 0, 255))  # second tile in default order
    driver.update(controller.get_frame())
    board = _board(driver, 'quinled1')
    buf = board._pixel_buf['strip1']
    assert all(c == (0, 0, 0) for c in buf[:20])
    assert all(c == (0, 0, 255) for c in buf[20:40])
    assert all(c == (0, 0, 0) for c in buf[40:])


def test_brightness_is_baked_into_pixels():
    driver = _driver()
    controller = TileController(GRID)
    controller.set_all((255, 255, 255))
    controller.set_brightness(128)
    driver.update(controller.get_frame())
    board = _board(driver, 'quinled1')
    assert board._pixel_buf['strip1'][0] == (128, 128, 128)
    controller.all_off()
    driver.update(controller.get_frame())
    assert board._pixel_buf['strip1'][0] == (0, 0, 0)


def test_full_frame_roundtrip():
    """Every world segment must arrive at exactly one chain position."""
    driver = _driver(rotations=(0, 90, 180, 270, 90, 270, 180, 0))
    controller = TileController(GRID)
    # encode each world flat index in the pixel value
    pixels = controller.get_frame().pixels
    flat = pixels.reshape(-1, 3)
    for i in range(len(flat)):
        flat[i] = (i % 256, (i // 256) % 256, 7)
    controller.set_pixels(pixels)
    driver.update(controller.get_frame())

    seen = set()
    for _name, board, lut in driver._boards:
        chain = [c for s in board._strips.values()
                 for c in board._pixel_buf[s.name]]
        assert len(chain) == len(lut)
        for pos, color in enumerate(chain):
            world_idx = color[0] + color[1] * 256
            assert color[2] == 7
            assert world_idx == lut[pos]  # LUT and pixel path agree
            seen.add(world_idx)
    assert len(seen) == 8 * 4 * 20


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
