import dataclasses
import os

from core.utils.dataclass_utils import from_dict_auto
from core.utils.files import get_absolute_path
from core.utils.yaml_utils import load_yaml
from robots.bilbo.testbed.testbed_manager import TestbedManagerSettings, \
    TrackerSettings, ExtensionsSettings, RobotSettings
from robots.bilbo.simulation.virtual_testbed import VirtualTestbed_Config

SETTINGS_FILE = get_absolute_path('./settings.yaml')
_SETTINGS_DIR = os.path.dirname(SETTINGS_FILE)


# ======================================================================================================================
@dataclasses.dataclass
class PathSettings:
    experiments: str = ''
    reference_trajectories: str = ''


@dataclasses.dataclass
class MDNSSettings:
    enabled: bool = True
    hostname: str = 'bilbolab'
    use_port_80: bool = False


@dataclasses.dataclass
class ApplicationSettings:
    """Settings as loaded from settings.yaml. Top-level keys map 1:1 to the YAML."""
    paths: PathSettings = dataclasses.field(default_factory=PathSettings)
    testbed: str = 'lab'  # Testbed ID — resolved to a definition file at runtime
    robots: RobotSettings = dataclasses.field(default_factory=RobotSettings)
    extensions: ExtensionsSettings = dataclasses.field(default_factory=ExtensionsSettings)
    simulation: VirtualTestbed_Config = dataclasses.field(default_factory=VirtualTestbed_Config)
    tracker: TrackerSettings = dataclasses.field(default_factory=TrackerSettings)
    mdns: MDNSSettings = dataclasses.field(default_factory=MDNSSettings)

    @property
    def testbed_manager_settings(self) -> TestbedManagerSettings:
        return TestbedManagerSettings(
            testbed=self.testbed,
            robots=self.robots,
            tracker=self.tracker,
            extensions=self.extensions,
            simulation=self.simulation,
        )


# ======================================================================================================================
def load_settings(path: str | None = None) -> ApplicationSettings:
    """Load typed application settings from settings.yaml."""
    if path is None:
        path = SETTINGS_FILE

    yaml_data = load_yaml(path)

    # Resolve all paths relative to the settings file location
    settings_dir = os.path.dirname(path)
    paths = yaml_data.get('paths')
    if isinstance(paths, dict):
        for key, value in paths.items():
            if isinstance(value, str):
                paths[key] = os.path.normpath(os.path.join(settings_dir, value))

    return from_dict_auto(ApplicationSettings, yaml_data)


def get_settings() -> dict:
    """Load host-side BILBO settings from settings.yaml as a raw dict.

    Paths under the ``paths`` key are resolved relative to the settings file's
    directory so that the YAML can use ``./`` style references.
    """
    data = load_yaml(SETTINGS_FILE)

    # Resolve all paths relative to the settings file location
    paths = data.get('paths')
    if isinstance(paths, dict):
        for key, value in paths.items():
            if isinstance(value, str):
                paths[key] = os.path.normpath(os.path.join(_SETTINGS_DIR, value))

    return data
