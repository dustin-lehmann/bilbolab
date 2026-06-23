"""IdeenExpo 2026 BILBO application.

A special application for presenting BILBO at the IdeenExpo expo. It mirrors the
standard :class:`BILBO_Application` (testbed manager, GUI, mobile app, CLI,
sound) but swaps in expo-specific building blocks:

* :class:`IdeenExpo2026_JoystickControl` — standard user-joystick control plus a
  privileged *master joystick* (identified by GUID in the settings YAML).
* :class:`IdeenExpo2026_GUI` — standard GUI plus master-control buttons.
* :class:`IdeenExpo2026_CommandSet` — an ``expo`` CLI namespace.

The master-joystick behaviour is currently groundwork (see
``joystick_control.py``); with the default settings (master disabled) this app
behaves like the standard application.
"""
import logging
import os
import sys
import time
import subprocess

# === PATH SETUP =======================================================================================================
# Make the host software root (".../software") importable so the absolute
# "robots.* / core.* / extensions.*" imports below resolve.
current_dir = os.path.dirname(os.path.abspath(__file__))
software_dir = os.path.abspath(os.path.join(current_dir, '..', '..', '..', '..'))
if software_dir not in sys.path:
    sys.path.insert(0, software_dir)

# === CUSTOM MODULES ===================================================================================================
# Import the GUI first. This transitively imports robots.bilbo.gui.bilbo_gui, which
# resolves the robots.bilbo import graph (settings, testbed_manager, robot, ...) in an
# order that avoids a pre-existing circular import between robots.bilbo.settings and the
# experiment/dilc modules — exactly as the standard bilbo_application does by importing
# bilbo_gui first. Importing testbed_manager or settings before this would fail.
from robots.bilbo.applications.ideenexpo_2026.gui import IdeenExpo2026_GUI

from extensions.tools.cli.cli import CLI
from core.utils.exit import register_exit_callback, exit_program, infinite_loop
from core.utils.logging_utils import setLoggerLevel, Logger
from core.utils import colors
from core.utils.sound.sound import speak, SoundSystem
from core.utils.network.network import getHostIP
from robots.bilbo.testbed.testbed_manager import TestbedManager

from robots.bilbo.applications.ideenexpo_2026.settings import IdeenExpo2026_Settings, load_settings
from robots.bilbo.applications.ideenexpo_2026.joystick_control import (
    IdeenExpo2026_JoystickControl,
    MasterOverrideMode,
)
from robots.bilbo.applications.ideenexpo_2026.cli import IdeenExpo2026_CommandSet

# ======================================================================================================================
ENABLE_SPEECH_OUTPUT = True


# ======================================================================================================================
class IdeenExpo2026_Application:
    manager: TestbedManager
    soundsystem: SoundSystem
    joystick_control: IdeenExpo2026_JoystickControl | None
    gui: IdeenExpo2026_GUI

    # === INIT =========================================================================================================
    def __init__(self, settings: IdeenExpo2026_Settings):

        self.settings = settings

        # Logging
        self.logger = Logger('EXPO')
        self.logger.setLevel('INFO')

        # Check if there is a valid host IP
        ip = getHostIP()
        if ip is None:
            self.logger.error("No valid IP address for the server")
            exit_program()

        Logger.banner([f"BILBO IdeenExpo 2026 — {ip}"])
        time.sleep(0.01)
        self.manager = TestbedManager(settings=settings.testbed_manager_settings)

        # CLI
        self.cli = CLI(id='ideenexpo_2026_cli')

        # Sound System for speaking and sounds
        self.soundsystem = SoundSystem(primary_engine='etts', volume=1)
        self.soundsystem.start()

        # Joystick Control (user joysticks + master joystick)
        if settings.extensions.joystick:
            self.joystick_control = IdeenExpo2026_JoystickControl(
                self.manager.robot_manager,
                master_settings=settings.master_joystick,
                auto_assign=settings.extensions.joystick_auto_assign,
            )
        else:
            self.joystick_control = None

        # Expo CLI command set
        self.expo_cli_command_set = IdeenExpo2026_CommandSet(self)

        # GUI (desktop + mobile app)
        self.gui = IdeenExpo2026_GUI(settings=self.settings,
                                     host=self.manager.robot_manager.host,
                                     testbed_manager=self.manager,
                                     cli=self.cli,
                                     joystick_control=self.joystick_control,
                                     enable_mdns=settings.mdns.enabled,
                                     mdns_hostname=settings.mdns.hostname,
                                     mdns_use_port_80=settings.mdns.use_port_80)

        self.gui.callbacks.emergency_stop.register(self.manager.emergency_stop)

        # Wire the GUI master-control buttons to the joystick control.
        self._wire_master_gui()

        # Network Monitor (runs as subprocess to avoid eventlet monkey_patch conflicts)
        self._network_monitor_proc = None

        # Exit Handling
        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def _wire_master_gui(self):
        """Connect the GUI master-control callbacks to the joystick control."""
        if self.joystick_control is None:
            return
        master_cb = self.gui.master_callbacks
        # Route the desktop "Override" button through the mode system so it stays
        # consistent with the App's "Override Mode" selector.
        master_cb.override.register(lambda *a, **k: self.joystick_control.setMasterMode(MasterOverrideMode.FULL))
        master_cb.all_robots_on.register(self.joystick_control.allRobotsOn)
        master_cb.all_robots_off.register(self.joystick_control.allRobotsOff)

    # === METHODS ======================================================================================================
    def init(self):
        setLoggerLevel(logger=['tcp', 'server', 'UDP', 'UDP Socket', 'Sound'], level=logging.WARNING)

        self.manager.init()

        Logger.section("Joystick")
        if self.joystick_control is not None:
            self.joystick_control.init()
        else:
            self.logger.info("Joystick disabled")

        Logger.section("CLI")
        self.cli.root.addChild(self.manager.robot_manager.cli)
        self.cli.root.addChild(self.manager.cli)
        self.cli.root.addChild(self.expo_cli_command_set)
        if self.joystick_control is not None:
            self.cli.root.addChild(self.joystick_control.cli_command_set)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        speak('Start Bilbo Ideenexpo application')

        self.manager.start()

        if self.joystick_control is not None:
            Logger.section("Joystick")
            self.joystick_control.start()

        Logger.section("GUI")
        self.gui.start()

        Logger.section("Network Monitor")
        network_monitor_script = os.path.join(software_dir, 'extensions', 'apps', 'network_monitor',
                                              'network_monitor_app.py')
        self._network_monitor_proc = subprocess.Popen(
            [sys.executable, network_monitor_script],
            cwd=software_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        Logger.banner(["BILBO IdeenExpo 2026 Application Running"])

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        Logger.banner(["Shutting down BILBO IdeenExpo 2026 Application"], color=colors.MEDIUM_ORANGE)
        speak('Stop Bilbo Ideenexpo application')
        if self.joystick_control is not None:
            self.joystick_control.close()
        if self._network_monitor_proc and self._network_monitor_proc.poll() is None:
            self._network_monitor_proc.terminate()
        self.gui.close()
        time.sleep(2)
        global ENABLE_SPEECH_OUTPUT
        ENABLE_SPEECH_OUTPUT = False


# ======================================================================================================================
def run_ideenexpo_2026():
    # Load expo settings from the local YAML file
    settings = load_settings()

    app = IdeenExpo2026_Application(settings=settings)
    app.init()
    app.start()

    infinite_loop()


if __name__ == '__main__':
    run_ideenexpo_2026()
