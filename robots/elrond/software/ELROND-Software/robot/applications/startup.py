import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from RPi import GPIO

top_level_module = os.path.expanduser("~/robot/software")

if top_level_module not in sys.path:
    sys.path.insert(0, top_level_module)

from utils.network import get_current_user, get_own_hostname, getLocalIP_RPi, check_internet, get_wifi_ssid
from utils.button import Button
from utils.joystick.joystick_utils import scan_and_connect, find_connected_device_with_pattern
from control_board.board_config import getBoardConfig
from robot.utilities.display.display import Display
from robot.utilities.display.pages import StatusPage
from utils.singletonlock.singletonlock import terminate, check_for_running_lock_holder, get_lock_mode
from utils.sound.sound import SoundSystem
from robot.hardware import get_hardware_definition


def get_full_path(relative_path):
    """
    Resolve the absolute path from a relative path.

    :param relative_path: Relative path to resolve.
    :return: Absolute path.
    """
    # Get the current script's directory
    script_dir = Path(__file__).parent.resolve()

    # Resolve the full path
    full_path = (script_dir / relative_path).resolve()

    return str(full_path)


def start_script_in_new_process(script_path, *args):
    """
    Start a Python script in a new process.

    :param script_path: Path to the Python script to execute.
    :param args: Additional arguments to pass to the script.
    :return: A Popen object representing the started process.
    """
    try:
        # Start the script with subprocess.Popen
        process = subprocess.Popen(
            ['python', script_path, *args],
            stdout=subprocess.PIPE,  # Capture stdout (optional)
            stderr=subprocess.PIPE,  # Capture stderr (optional)
            text=True  # Output and errors as strings (not bytes)
        )
        print(f"Started script: {script_path} with PID: {process.pid}")
        return process
    except Exception as e:
        print(f"Failed to start script: {script_path}. Error: {e}")
        return None


class Startup:
    display: Display

    _thread: threading.Thread
    _joystick_thread: threading.Thread
    _exit = False

    joystick_pattern = '8BitDo'
    sound_system: SoundSystem

    def __init__(self):
        self.display = Display()
        self.config = getBoardConfig()
        self.hardware = get_hardware_definition()

        self.program_running = False
        self.joystick_connected = False
        self.long_press_detected = False

        self.LED_PIN = self.hardware['electronics']['buttons']['primary']['led']['pin']
        self.BUTTON_PIN = self.hardware['electronics']['buttons']['primary']['pin']

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.LED_PIN, GPIO.OUT)
        GPIO.output(self.LED_PIN, False)

        self.button = Button(self.BUTTON_PIN,
                             short_press_callback=self.button_short_press_callback,
                             long_press_callback=self.button_long_press_callback,
                             double_click_callback=self.button_double_press_callback)

        self.status_page = StatusPage()
        self.display.add_page(self.status_page)

        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        self.sound_system = SoundSystem(volume=0.4)

        self._thread = threading.Thread(target=self.task, daemon=True)
        self._joystick_thread = threading.Thread(target=self.joystick_task, daemon=True)

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        self.update_status_page()
        self.setLED(0)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.sound_system.start()
        self.display.change_page('Status', start_thread=False)
        self.display.start()
        self._thread.start()
        self._joystick_thread.start()
        self.sound_system.play('startup', volume=0.4)

    # ------------------------------------------------------------------------------------------------------------------
    def task(self):
        while not self._exit:

            # Check the Joystick:
            if self.joystick_connected:
                self.setLED(1)
            else:
                self.setLED(0)

            self.update_status_page()

            if self.long_press_detected:
                self.long_press_detected = False

                if check_for_running_lock_holder(lock_file='/tmp/twipr.lock'):
                    self.sound_system.speak("Terminate running application")
                    terminate('/tmp/twipr.lock')
                else:
                    if self.joystick_connected:
                        self.sound_system.speak("Start Standalone Mode")
                        process = start_script_in_new_process(script_path=get_full_path('./standalone/standalone.py'))
                    else:
                        self.sound_system.speak("Please connect a joystick before starting standalone mode")

            time.sleep(2)

    def joystick_task(self):
        while not self._exit:
            self.update_joystick()
            time.sleep(5)

    def update_joystick(self):
        connected_joystick = find_connected_device_with_pattern(self.joystick_pattern)
        if connected_joystick is not None:
            if not self.joystick_connected:
                self.sound_system.speak('Joystick connected')
                self.joystick_connected = True
        else:
            if self.joystick_connected:
                self.joystick_connected = False
                self.sound_system.speak('Joystick disconnected')

    def update_status_page(self):
        # Check the network things:
        username = get_current_user()
        hostname = get_own_hostname()
        self.status_page.set_user_and_hostname(username, hostname)

        ip = getLocalIP_RPi()
        self.status_page.set_ip_address(ip)

        self.status_page.set_internet_status(check_internet(timeout=1))

        ssid = get_wifi_ssid()
        self.status_page.set_ssid(ssid)

        # Check if there is currently a TWIPR Process is running:
        if check_for_running_lock_holder(lock_file='/tmp/twipr.lock'):
            self.program_running = True
        else:
            self.program_running = False

        mode = get_lock_mode(lock_file='/tmp/twipr.lock')

        self.status_page.set_mode(mode)

        self.status_page.set_battery(level='empty', voltage=0)

    # ------------------------------------------------------------------------------------------------------------------
    def setLED(self, state):
        if state == 1:
            GPIO.output(self.LED_PIN, GPIO.HIGH)
        elif state == 0:
            GPIO.output(self.LED_PIN, GPIO.LOW)
        elif state == -1:
            GPIO.output(self.LED_PIN, not GPIO.input(self.LED_PIN))

    # ------------------------------------------------------------------------------------------------------------------
    def button_short_press_callback(self, *args, **kwargs):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def button_long_press_callback(self, *args, **kwargs):
        self.long_press_detected = True

    # ------------------------------------------------------------------------------------------------------------------
    def button_double_press_callback(self, *args, **kwargs):
        self.display.displayText('Joystick Search ... ', return_time=60)
        result = scan_and_connect(pattern=self.joystick_pattern)
        if result:
            self.display.displayText('Joystick connected')
        else:
            self.display.displayText('No Joystick found')

    def signal_handler(self, signum, frame):
        self.shutdown()

    def shutdown(self):
        self._exit = True  # Set the exit flag to stop threads
        self.sound_system.speak("Shutdown")
        time.sleep(2)
        print("Signal received, shutting down...")
        time.sleep(0.5)
        GPIO.cleanup()  # Release GPIO resources
        sys.exit(0)  # Exit the script


if __name__ == '__main__':
    startup = Startup()
    startup.init()
    startup.start()

    try:
        while not False:
            time.sleep(20)
    except KeyboardInterrupt:
        print("Keyboard interrupt received.")
    finally:

        ...
        # startup.shutdown()
        # startup.cleanup()
