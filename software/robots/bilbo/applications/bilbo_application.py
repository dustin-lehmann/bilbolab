import logging
import os
import sys
import time
import subprocess

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Go up one or more levels as needed
top_level_module = os.path.abspath(os.path.join(current_dir, '..', '..'))  # adjust as needed

if top_level_module not in sys.path:
    sys.path.insert(0, top_level_module)

# === CUSTOM MODULES ===================================================================================================
from robots.bilbo.gui.bilbo_gui import BILBO_Application_GUI
from extensions.tools.cli.cli import CLI
from core.utils.exit import register_exit_callback, exit_program
from core.utils.logging_utils import setLoggerLevel, Logger
from core.utils import colors
from core.utils.exit import infinite_loop
from core.utils.sound.sound import speak, SoundSystem
from robots.bilbo.testbed.testbed_manager import TestbedManager
from core.utils.network.network import getHostIP
from robots.bilbo.manager.bilbo_joystick_control import BILBO_JoystickControl
from robots.bilbo.settings import ApplicationSettings, load_settings

# ======================================================================================================================
ENABLE_SPEECH_OUTPUT = True


# ======================================================================================================================
class BILBO_Application:
    manager: TestbedManager
    soundsystem: SoundSystem
    joystick_control: BILBO_JoystickControl | None

    # === INIT =========================================================================================================
    def __init__(self, settings: ApplicationSettings):

        self.settings = settings

        # Logging
        self.logger = Logger('APP')
        self.logger.setLevel('INFO')

        # Check if there is a valid host IP
        ip = getHostIP()
        if ip is None:
            self.logger.error("No valid IP address for the server")
            exit_program()

        Logger.banner([f"BILBO Application — {ip}"])
        time.sleep(0.01)
        self.manager = TestbedManager(settings=settings.testbed_manager_settings)

        # CLI
        self.cli = CLI(id='bilbo_app_cli')

        # Sound System for speaking and sounds
        self.soundsystem = SoundSystem(primary_engine='etts', volume=1)
        self.soundsystem.start()

        # Joystick Control
        if settings.extensions.joystick:
            self.joystick_control = BILBO_JoystickControl(self.manager.robot_manager)
        else:
            self.joystick_control = None

        # GUI
        self.gui = BILBO_Application_GUI(settings=self.settings,
                                         host=self.manager.robot_manager.host,
                                         testbed_manager=self.manager,
                                         cli=self.cli,
                                         joystick_control=self.joystick_control,
                                         enable_mdns=settings.mdns.enabled,
                                         mdns_hostname=settings.mdns.hostname,
                                         mdns_use_port_80=settings.mdns.use_port_80)

        self.gui.callbacks.emergency_stop.register(self.manager.emergency_stop)

        # Network Monitor (runs as subprocess to avoid eventlet monkey_patch conflicts)
        self._network_monitor_proc = None

        # Exit Handling
        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
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
        if self.joystick_control is not None:
            self.cli.root.addChild(self.joystick_control.cli_command_set)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        speak('Start Bilbo application')

        self.manager.start()

        if self.joystick_control is not None:
            Logger.section("Joystick")
            self.joystick_control.start()

        Logger.section("GUI")
        self.gui.start()

        Logger.section("Network Monitor")
        software_dir = os.path.abspath(os.path.join(top_level_module, '..'))
        network_monitor_script = os.path.join(software_dir, 'extensions', 'apps', 'network_monitor',
                                              'network_monitor_app.py')
        self._network_monitor_proc = subprocess.Popen(
            [sys.executable, network_monitor_script],
            cwd=software_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        Logger.banner(["BILBO Application Running"])

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        Logger.banner(["Shutting down BILBO Application"], color=colors.MEDIUM_ORANGE)
        speak('Stop Bilbo application')
        if self.joystick_control is not None:
            self.joystick_control.close()
        if self._network_monitor_proc and self._network_monitor_proc.poll() is None:
            self._network_monitor_proc.terminate()
        self.gui.close()
        time.sleep(2)
        global ENABLE_SPEECH_OUTPUT
        ENABLE_SPEECH_OUTPUT = False


# ======================================================================================================================
def run_bilbo_application():
    # Load settings from YAML file
    settings = load_settings()

    app = BILBO_Application(settings=settings)
    app.init()
    app.start()

    infinite_loop()


if __name__ == '__main__':
    run_bilbo_application()
