from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extensions.libs.babylon.src.babylon import BabylonConfig, BabylonVisualization


class BabylonScenario:
    """Base class for reusable Babylon scene configurations.

    Subclasses override get_config() to provide scene settings (camera, background, fog, etc.)
    and setup() to create and add objects to the scene.

    Usage:
        scenario = ArenaScenario(size=3)
        babylon = StandaloneBabylon(title="Demo", scenario=scenario)
        babylon.start()

        while True:
            scenario.update(t, dt)
            time.sleep(dt)
    """

    def __init__(self, config: BabylonConfig | None = None, **kwargs):
        from extensions.libs.babylon.src.babylon import BabylonConfig as _BabylonConfig
        self.objects: dict = {}
        self.babylon: BabylonVisualization | None = None
        self.config = config or _BabylonConfig()

    def get_config(self) -> dict:
        """Return babylon_config dict (camera, background, fog, lighting, etc.).

        Keys returned here are merged into the BabylonVisualization config before start().
        """
        return self.config.to_dict()

    def setup(self, babylon: BabylonVisualization):
        """Create and add objects to the scene. Store references in self.objects."""
        self.babylon = babylon

    def update(self, t: float, dt: float):
        """Optional per-tick update called by the user's loop (not auto-managed)."""
        pass
