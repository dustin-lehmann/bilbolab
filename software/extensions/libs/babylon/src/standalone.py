from __future__ import annotations

import os
import time
import webbrowser
from urllib.parse import urlencode

from core.utils.dict_utils import update_dict
from core.utils.exit import register_exit_callback
from core.utils.files import get_absolute_path
from core.utils.js.vite import run_vite_app
from core.utils.logging_utils import Logger
from extensions.libs.babylon.src.babylon import (
    BabylonVisualization, BabylonObject, BabylonObjectGroup, BabylonCamera, BabylonConfig,
)
from extensions.libs.babylon.src.scenarios.scenario import BabylonScenario


class StandaloneBabylon:
    """Minimal BabylonJS visualization - opens a browser window, no GUI framework needed."""

    def __init__(self,
                 title: str = "Babylon Visualization",
                 host: str = 'localhost',
                 ws_port: int = 9000,
                 http_port: int = 9200,
                 babylon_config: BabylonConfig | dict | None = None,
                 scenario: BabylonScenario | None = None,
                 open_browser: bool = True):

        self.logger = Logger('StandaloneBabylon', 'INFO')

        self._host = host
        self._ws_port = ws_port
        self._http_port = http_port
        self._title = title
        self._open_browser = open_browser

        self._id = 'babylon'
        self._babylon_config = babylon_config
        self._scenario: BabylonScenario | None = None
        self._babylon: BabylonVisualization | None = None
        self._vite_process = None

        if scenario is not None:
            self.load_scenario(scenario)

        config_dict = {'title': self._title}
        if self._scenario is not None:
            config_dict = update_dict(config_dict, self._scenario.get_config())

        # Apply user-level overrides (BabylonConfig or raw dict)
        if isinstance(self._babylon_config, BabylonConfig):
            config_dict = update_dict(config_dict, self._babylon_config.to_dict())
        elif isinstance(self._babylon_config, dict):
            config_dict = update_dict(config_dict, self._babylon_config)

        self._babylon = BabylonVisualization(
            id=self._id,
            host=self._host,
            port=self._ws_port,
            babylon_config=config_dict,
        )

        register_exit_callback(self.close)

    # === SCENARIO =====================================================================================================
    def load_scenario(self, scenario: BabylonScenario):
        """Load a scenario. Must be called before start()."""
        self._scenario = scenario

    # === LIFECYCLE =====================================================================================================
    def start(self):
        """Start WebSocket server, Vite dev server, and optionally open the browser."""
        # Build merged config dict: scenario config + user overrides
        # Use get_config() so subclasses that override it (returning dicts) still work.

        self._babylon.init()
        self._babylon.start()

        # Start Vite dev server pointing at the GUI extension directory
        gui_path = get_absolute_path(os.path.join(os.path.dirname(__file__), '../../gui'))
        self._vite_process = run_vite_app(
            gui_path,
            host=self._host,
            port=self._http_port,
            print_link=False,
        )

        self.logger.info(f"Vite dev server started on http://{self._host}:{self._http_port}")

        if self._open_browser:
            # Give Vite a moment to start up
            time.sleep(1.5)
            self._open()

        # Run scenario setup (adds objects to the scene)
        if self._scenario is not None:
            self._scenario.setup(self._babylon)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        """Stop everything."""
        if self._vite_process is not None:
            self._vite_process.terminate()
            self._vite_process = None

        if self._babylon is not None:
            self._babylon.close()
        self.logger.info("StandaloneBabylon closed")

    # === CONTEXT MANAGER ==============================================================================================
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # === DELEGATES ====================================================================================================
    def addObject(self, obj: BabylonObject | BabylonObjectGroup):
        """Add an object to the 3D scene."""
        self._babylon.addObject(obj)

    def removeObject(self, obj: BabylonObject | BabylonObjectGroup | str):
        """Remove an object from the 3D scene."""
        self._babylon.removeObject(obj)

    def start_recording(self, **kwargs):
        """Start recording the visualization. See BabylonVisualization.start_recording for args."""
        self._babylon.start_recording(**kwargs)

    def stop_recording(self):
        """Stop the current recording."""
        self._babylon.stop_recording()

    @property
    def is_recording(self) -> bool:
        return self._babylon.is_recording

    @property
    def callbacks(self):
        return self._babylon.callbacks

    def set_title(self, text: str):
        """Update the title text shown in the top bar overlay."""
        self._babylon.set_title(text)

    def set_label(self, label_id: str, text: str, **kwargs):
        """Create or update an overlay label. Set text to '' to hide it.

        See BabylonVisualization.set_label for kwargs (x, y, font_size, color, background).
        """
        self._babylon.set_label(label_id, text, **kwargs)

    def remove_label(self, label_id: str):
        """Remove an overlay label."""
        self._babylon.remove_label(label_id)

    def add_camera(self, camera: BabylonCamera):
        """Add a named camera view button to the UI."""
        self._babylon.add_camera(camera)

    def center_camera_on(self, obj):
        """Start following a BabylonObject with the camera."""
        self._babylon.center_camera_on(obj)

    def stop_following(self):
        """Stop following any object with the camera."""
        self._babylon.stop_following()

    def send(self, message, client=None):
        """Send a raw message to connected clients."""
        self._babylon.send(message, client)

    # === PRIVATE ======================================================================================================
    def _open(self):
        """Open the browser to the babylon popup page."""
        params = urlencode({
            'id': self._id,
            'host': self._host,
            'port': str(self._ws_port),
            'title': self._title,
        })
        url = f"http://{self._host}:{self._http_port}/babylon-popup.html?{params}"
        self.logger.info(f"Opening browser: {url}")
        webbrowser.open(url)
