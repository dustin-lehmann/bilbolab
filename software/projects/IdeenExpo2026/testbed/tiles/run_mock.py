"""
Run the tile controller in mock-up mode with the web viewer.

No hardware needed: the controller state is only shown in (and set from)
the tile viewer webapp.

    python run_mock.py
    -> http://localhost:8530        (built frontend, run `npm run build` once)
    -> http://localhost:9230        (or use the vite dev server: `npm run dev`
                                     in extensions/apps/tile_viewer/frontend)
"""

import sys
from pathlib import Path

TILES_DIR = Path(__file__).resolve().parent
SOFTWARE_ROOT = TILES_DIR.parents[3]
sys.path.insert(0, str(SOFTWARE_ROOT))
sys.path.insert(0, str(TILES_DIR))

from tile_controller import TileController, TileGridConfig, MockTileDriver
from extensions.apps.tile_viewer.backend.server import TileViewerServer


def main():
    config = TileGridConfig.from_yaml(str(TILES_DIR / 'config' / 'tiles.yaml'))
    controller = TileController(config)
    controller.attach_driver(MockTileDriver(verbose=False))

    # Something to look at on startup
    controller.pattern_identify_tiles()

    server = TileViewerServer(controller, port=8530,
                              layouts_dir=str(TILES_DIR / 'layouts'))
    server.run()


if __name__ == '__main__':
    main()
