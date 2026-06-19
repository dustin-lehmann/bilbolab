"""
Run the tile controller against the real QuinLED Dig boards, with the
web viewer attached (http://localhost:8530).

Reads grid + mapping from config/tiles.yaml. Boards that are offline at
startup only produce a warning — UDP output starts working as soon as
they come online (the keepalive re-sends the current frame).

    python run_live.py
"""

import sys
from pathlib import Path

TILES_DIR = Path(__file__).resolve().parent
SOFTWARE_ROOT = TILES_DIR.parents[3]
sys.path.insert(0, str(SOFTWARE_ROOT))
sys.path.insert(0, str(TILES_DIR))

from tile_controller import TileController, TileGridConfig
from tile_mapping import QuinLEDTileDriver
from extensions.apps.tile_viewer.backend.server import TileViewerServer

CONFIG = TILES_DIR / 'config' / 'tiles.yaml'


def main():
    config = TileGridConfig.from_yaml(str(CONFIG))
    controller = TileController(config)

    driver = QuinLEDTileDriver.from_yaml(str(CONFIG))
    print("Connection test:")
    driver.test_connection(verbose=True)
    controller.attach_driver(driver)

    server = TileViewerServer(controller, port=8530,
                              layouts_dir=str(TILES_DIR / 'layouts'))
    server.run()


if __name__ == '__main__':
    main()
