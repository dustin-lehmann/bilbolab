"""Settings for the IdeenExpo 2026 BILBO application.

Extends the standard :class:`robots.bilbo.settings.ApplicationSettings` with
expo-specific options. Right now the only addition is the *master joystick*
configuration; this is intentionally structured so that more expo-specific
settings can be added later without touching the standard application.
"""
import dataclasses
import os

from core.utils.dataclass_utils import from_dict_auto
from core.utils.files import get_absolute_path
from core.utils.yaml_utils import load_yaml
from robots.bilbo.settings import ApplicationSettings

# Resolved relative to *this* file's directory (the ideenexpo_2026 package).
SETTINGS_FILE = get_absolute_path('./ideenexpo_2026_settings.yaml')


# ======================================================================================================================
@dataclasses.dataclass
class MasterJoystickSettings:
    """Configuration of the privileged *master* joystick.

    The master joystick is identified by its pygame ``guid`` (and optionally a
    ``name`` fallback). Unlike regular user joysticks it is never auto-assigned
    as a normal controller. Instead it is given special privileges:

    * it can take over (override) *any* robot (Full mode),
    * it can mix its input into the user's to "help" (Assist mode),
    * it can switch all robots on/off.

    The target robot and override mode are selected from the App's "Master" folder.
    """
    enabled: bool = False
    guid: str | None = None              # pygame GUID of the master joystick (see `joysticks list-guids` CLI)
    name: str | None = None              # Optional human-readable / fallback match by joystick name

    # --- Assist (help) mode: master input is mixed into the user's input ---
    assist_gain: float = 0.5             # Master authority in assist mode (0..1). 0 = no help, 1 = equal to user.
    # How the master's axis is combined with the user's (see bilbo_interfaces._mix_assist):
    #   'additive'  : output = clamp(user + gain*master)  — legacy; opposite inputs cancel.
    #   'authority' : the master gets more say the harder it pushes; at full deflection (×gain)
    #                 it overrides the user, at rest the user has full control. With gain=1,
    #                 master 100% one way wins; master 50% vs a full-opposite user ties.
    assist_mix_mode: str = 'additive'

    # --- Trigger "turbo" boosts (active in Assist/Full when the robot is BALANCING/VELOCITY) ---
    # The master's RIGHT_TRIGGER (R2) boosts forward and LEFT_TRIGGER (L2) boosts turn: the
    # robot scales that axis by max * (1 + trigger * scale), so the command can exceed the
    # configured max. Separate scales per mode (forward/turn map to torque in BALANCING vs
    # velocity / yaw-rate in VELOCITY).
    boost_scale_balancing: float = 0.5        # R2 → forward, BALANCING
    boost_scale_velocity: float = 1.0         # R2 → forward, VELOCITY
    boost_scale_turn_balancing: float = 0.5   # L2 → turn, BALANCING
    boost_scale_turn_velocity: float = 1.0    # L2 → turn, VELOCITY

    # --- Release behaviour ---
    restore_user_on_release: bool = True  # On release, hand the robot back to its previous user joystick


# ======================================================================================================================
@dataclasses.dataclass
class CameraSettings:
    """Configuration of the USB testbed camera shown on the big *Camera* page.

    The :class:`CameraWidget` enumerates the cameras connected to the host
    (the testbed machine), auto-selects one and streams its MJPEG feed. Use
    ``excluded`` / ``priority`` (case-insensitive regex on the camera label) to
    skip built-in cameras and prefer the USB one. The frontend dropdown still
    lets the operator switch cameras at runtime.
    """
    enabled: bool = True
    width: int = 1280
    height: int = 720
    fps: int = 30
    # Skip built-in / continuity cameras so a USB camera is picked by default.
    excluded: list[str] = dataclasses.field(default_factory=lambda: ['iPhone', 'FaceTime'])
    # Prefer cameras whose label matches these patterns (earlier = higher priority).
    priority: list[str] = dataclasses.field(default_factory=list)


# ======================================================================================================================
@dataclasses.dataclass
class SpeedLevel:
    """One selectable input "speed": independent forward / turn scale factors (0..1)."""
    name: str
    forward: float
    turn: float


@dataclasses.dataclass
class JoystickSpeedSettings:
    """Per-robot, switchable input "speed" (selected from the App's Master folder).

    Each level scales the *primary* (visitor) joystick's forward and turn axes before
    they are sent to the robot — ``Fast`` (1.0/1.0) is the full ±1 range. Turn is scaled
    less aggressively than forward so steering stays responsive at lower speeds. The
    master's Full override always drives at full range regardless of this setting.
    """
    enabled: bool = True
    default_level: str = 'Fast'          # level applied to a robot when it connects
    levels: list[SpeedLevel] = dataclasses.field(default_factory=lambda: [
        SpeedLevel('Slow', 0.50, 0.70),
        SpeedLevel('Medium', 0.75, 0.85),
        SpeedLevel('Fast', 1.00, 1.00),
    ])


# ======================================================================================================================
@dataclasses.dataclass
class IdeenExpo2026_Settings(ApplicationSettings):
    """Top-level settings for the IdeenExpo 2026 application.

    Inherits every field of the standard :class:`ApplicationSettings`
    (paths, testbed, robots, extensions, simulation, tracker, mdns) and adds
    the expo-specific ``master_joystick`` and ``camera`` blocks.
    """
    master_joystick: MasterJoystickSettings = dataclasses.field(default_factory=MasterJoystickSettings)
    camera: CameraSettings = dataclasses.field(default_factory=CameraSettings)
    speed: JoystickSpeedSettings = dataclasses.field(default_factory=JoystickSpeedSettings)


# ======================================================================================================================
def load_settings(path: str | None = None) -> IdeenExpo2026_Settings:
    """Load typed IdeenExpo 2026 settings from the expo settings YAML."""
    if path is None:
        path = SETTINGS_FILE

    yaml_data = load_yaml(path)

    # Resolve all paths relative to the settings file location (mirrors robots.bilbo.settings).
    settings_dir = os.path.dirname(path)
    paths = yaml_data.get('paths')
    if isinstance(paths, dict):
        for key, value in paths.items():
            if isinstance(value, str):
                paths[key] = os.path.normpath(os.path.join(settings_dir, value))

    return from_dict_auto(IdeenExpo2026_Settings, yaml_data)
