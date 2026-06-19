# Tile Viewer

Web-based view + control surface for the IdeenExpo 2026 lighted tile floor
(`projects/IdeenExpo2026/testbed/tiles/`).

The backend is a generic Flask-SocketIO server (`backend/server.py`) that
wraps any `TileController` instance — it knows nothing about hardware.
Whether the controller drives real QuinLED boards or runs in mock-up mode
is decided by the script that creates it.

## Run (mock-up mode)

```bash
# 1. Build the frontend once (or after frontend changes)
cd software/extensions/apps/tile_viewer/frontend
npm install
npm run build

# 2. Start controller + server
cd software/projects/IdeenExpo2026/testbed/tiles
python run_mock.py
# -> http://localhost:8530
```

## Run (live mode, real QuinLED boards)

```bash
cd software/projects/IdeenExpo2026/testbed/tiles
python run_live.py
```

Reads `config/tiles.yaml` (`grid:` + `mapping:` sections) and attaches a
`QuinLEDTileDriver` (tile_mapping.py) alongside the web viewer. Offline
boards only warn; output starts as soon as they appear on the network.
Verify the mapping on the physical floor with the `ID Tiles` and
`ID Edges` patterns.

## Frontend development

```bash
cd software/extensions/apps/tile_viewer/frontend
npm run dev
# -> http://localhost:9230 (hot reload, proxies /api and /socket.io to :8530)
```

## Embedding in your own script

```python
from tile_controller import TileController, TileGridConfig
from extensions.apps.tile_viewer.backend.server import TileViewerServer

controller = TileController(TileGridConfig(modules_x=4, modules_y=2))
# controller.attach_driver(QuinLEDTileDriver(...))   # later: real hardware
server = TileViewerServer(controller, port=8530)
server.run()
```

## UI

- **View modes** (header toggle, also `?view=real|schematic` URL param,
  persisted in localStorage): *Schematic* is the chunky editing view;
  *Real* is dimensionally accurate — 20 mm LED band around each 500 mm
  tile, 460 mm carpet inlay (textures from `extensions/gui/.../textures`,
  pre-darkened copies in `frontend/public/textures/`), 6 physical LEDs
  per 100 mm segment, with diffused light bleeding onto the carpet.
  Carpet colors alternate blue/gray by tile parity — change `carpetFor()`
  in `TileFloor.vue` if the real floor differs. Interaction is identical
  in both modes.
- **Paint**: pick a scope (segment / edge / tile / all — hotkeys 1–4) and a
  color, then click or drag on the floor. Right-click erases.
- **Output**: master on/off (blanks output, keeps the painted state) and
  master brightness.
- **Layouts**: save the currently painted floor as a named YAML file and
  reload it later (panel section "Layouts"). Files live in the `layouts/`
  directory passed to `TileViewerServer(layouts_dir=...)` — for the
  IdeenExpo project: `projects/IdeenExpo2026/testbed/tiles/layouts/`.
  Loading a layout is undoable.
- **Blink**: the small bolt button inside each tile flashes that tile
  white five times and restores it — for locating tiles on the real floor.
- **Undo/redo**: Cmd/Ctrl+Z and Cmd/Ctrl+Shift+Z (or the panel buttons).
  One undo step per paint stroke; starting an animation also checkpoints,
  so undo after stopping restores the previous painting. History lives
  server-side in the TileController (50 steps).
- **Test patterns**: checkerboard, identify-tiles (unique hue per tile) and
  identify-edges (N=red, E=green, S=blue, W=yellow, brightness ramp along
  the segments) — these are the tools for verifying the physical wiring
  /mapping later.
- **Animations**: chase (twin streams sweeping each tile frame), rainbow,
  plasma, scanner, breathe, sparkle, rain — scanner/breathe/sparkle use the
  selected paint color. **Ripple** is interactive: while it (or rain) is
  active, clicking anywhere on the floor spawns a water wave in the
  selected color that radiates outward and fades.

## Protocol

SocketIO events (client → server): `set_segment {x, y, edge, segment, color}`,
`set_edge`, `set_tile`, `set_all {color}`, `clear`, `set_on {on}`,
`set_brightness {brightness}`, `set_max_brightness {max_brightness}`,
`set_pattern {name, color?}`, `stop_pattern`, `ripple {x, y, color?}`
(world coordinates in tile units), `blink {x, y}`, `checkpoint`, `undo`,
`redo`, `save_layout {name}`, `load_layout {name}`, `delete_layout {name}`.

Server → client: `init {config, state, animation}`, `state {on, brightness,
max_brightness, pixels[y][x][edge][segment] = [r,g,b]}` (throttled to
~30 fps), `animation {name}`.

REST: `GET /api/config`, `GET /api/state`.
