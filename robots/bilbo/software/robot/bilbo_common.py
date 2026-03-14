import dataclasses
import os
import subprocess
import threading
import time
from typing import Callable

import yaml

from core.utils.dataclass_utils import from_dict_auto
# ======================================================================================================================
from core.utils.exit import register_exit_callback
from core.hardware.network import getSignalStrength, check_internet
from core.utils.timecode.timecode import Timecode
from core.utils.timecode.timecode_client import TimecodeClient
from hardware.control_board import RobotControl_Board
from .config import BILBO_Config, get_bilbo_config
from .core import get_logging_provider
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.files import file_exists
from core.utils.experiments.experiment_wrapper import _collect_git_info
from core.utils.json_utils import readJSON
from core.utils.logging_utils import Logger
from robot.paths import CONFIG_PATH, ROBOT_PATH


# ======================================================================================================================
@event_definition
class BILBO_Common_Interaction_Events:
    resume: Event = Event(id='resume')
    repeat: Event
    abort: Event


@event_definition
class BILBO_Common_Events:
    sample: Event
    control_mode_change: Event
    control_config_change: Event
    experiment_mode_change: Event
    error: Event
    server_connected: Event
    server_disconnected: Event
    joystick_connected: Event
    joystick_disconnected: Event


@callback_definition
class BILBO_Common_Callbacks:
    end_of_step: CallbackContainer


# ======================================================================================================================
class BILBO_Common:
    interaction_events: BILBO_Common_Interaction_Events
    events: BILBO_Common_Events
    callbacks: BILBO_Common_Callbacks

    # timecode_listener: TimecodeListener

    information: BILBO_Config

    joystick_connected: bool = False
    server_connected: bool = False

    _exit: bool = False

    board: RobotControl_Board

    id: str
    config: BILBO_Config

    tracker_connected: bool = False

    # === INIT =========================================================================================================
    def __init__(self, bilbo, board: RobotControl_Board):
        self.interaction_events = BILBO_Common_Interaction_Events()
        self.events = BILBO_Common_Events()
        self.callbacks = BILBO_Common_Callbacks()

        self.board = board
        self.bilbo = bilbo

        self.id = self._get_id()
        self.config = self._get_config()
        # self.testbed_config = self._get_testbed_config()

        self.connection_strength = 0
        self.internet_connected = False
        self.rpi_temperature = 0.0
        self.rpi_throttle = 0x0

        self.git_info = _collect_git_info()

        self.logger = Logger("CORE", "INFO")
        self.timecode_listener = TimecodeClient()
        self.timecode_listener.callbacks.sync.register(self._on_timecode_sync)

        self._thread = threading.Thread(target=self._connection_check_task, daemon=True)
        self._throttle_thread = threading.Thread(target=self._throttle_check_task, daemon=True)

        register_exit_callback(self.stop)

    # === PROPERTIES ===================================================================================================
    @property
    def tick(self):
        return get_logging_provider().get_tick()

    # === METHODS ======================================================================================================
    def start(self):
        """Start background services (timecode, connection checks)."""
        self.timecode_listener.start()
        self._thread.start()
        self._throttle_thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def get_timecode(self) -> Timecode | None:
        return self.timecode_listener.get_timecode()

    # ------------------------------------------------------------------------------------------------------------------
    def is_tracker_connected(self) -> bool:
        return self.tracker_connected

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        self._exit = True
        if self._thread.is_alive():
            self._thread.join()
        if self._throttle_thread.is_alive():
            self._throttle_thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def get_data(self,
                 index: int | None = None,
                 start: int | None = None,
                 end: int | None = None,
                 signals: list[str] | None = None,
                 add_intermediate_samples: bool = False,
                 callback=None):
        return get_logging_provider().get_data(index, start, end, signals, add_intermediate_samples, callback=callback)

    # ------------------------------------------------------------------------------------------------------------------
    def get_lowlevel_data(self,
                          index: int | None = None,
                          start: int | None = None,
                          end: int | None = None,
                          signals: list[str] | None = None) -> dict | None:
        return get_logging_provider().get_lowlevel_data(index, start, end, signals)

    # ------------------------------------------------------------------------------------------------------------------
    def flush_logs(self):
        """Force flush all H5 log data to disk. Call before reading data to ensure all samples are available."""
        logging_provider = get_logging_provider()
        if hasattr(logging_provider, 'flush'):
            logging_provider.flush()

    # ------------------------------------------------------------------------------------------------------------------
    def getConnectionStatus(self, as_dict: bool = False):
        return {
            'strength': self.connection_strength,
            'internet': self.internet_connected
        }

    # ------------------------------------------------------------------------------------------------------------------
    def setResumeEvent(self, data):
        self.logger.info("Set resume event")
        self.interaction_events.resume.set(data=data)

    def setRepeatEvent(self, data):
        self.logger.info("Set repeat event")
        self.interaction_events.repeat.set(data=data)

    def setAbortEvent(self, data):
        self.logger.warning("Set abort event")
        self.interaction_events.abort.set(data=data)

    # ------------------------------------------------------------------------------------------------------------------
    def get_general_sample_dict(self) -> dict:

        current_timecode = self.timecode_listener.get_timecode()

        # Adapt the timecode for the time of the LL sample. Since this is 0.1 seconds in the past, we have to adjust it
        if current_timecode is not None:
            current_timecode = current_timecode - 0.1

        sample = {
            'status': 'none',
            'time': 0,
            'time_global': time.monotonic(),
            'tick': self.tick,
            'connection_strength': self.connection_strength,
            'internet_connected': self.internet_connected,
            'timecode': current_timecode.to_string() if current_timecode is not None else '00:00:00:00',
            'timecode_fps': current_timecode.fps if current_timecode is not None else 0,
            'rpi_temperature': self.rpi_temperature,
            'rpi_throttle': self.rpi_throttle,
        }

        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def end_of_step(self):
        self.callbacks.end_of_step.call()

    # ------------------------------------------------------------------------------------------------------------------
    def run_function_on_robot(self, function: str, *args, arguments: dict | None = None, **kwargs):
        """
        Run a function on the robot by navigating through the object hierarchy.

        Args:
            function: A dot-separated path to the function, e.g. ".control.set_mode"
            *args: Positional arguments to pass to the function
            arguments: Optional dict of keyword arguments (merged with kwargs)
            **kwargs: Keyword arguments to pass to the function

        Returns:
            The return value of the called function

        Example:
            run_function_on_robot(".control.set_mode", mode=1)
            run_function_on_robot(".control.set_mode", arguments={'mode': 1})
        """
        # Merge arguments dict with kwargs (kwargs takes precedence)
        if arguments is not None:
            kwargs = {**arguments, **kwargs}

        # Remove leading dot if present and split the path
        if function.startswith('.'):
            function = function[1:]

        parts = function.split('.')

        # Start from bilbo and navigate through the path
        obj = self.bilbo
        for part in parts[:-1]:
            if not hasattr(obj, part):
                raise AttributeError(f"Object {type(obj).__name__} has no attribute '{part}'")
            obj = getattr(obj, part)

        # Get the final function
        func_name = parts[-1]
        if not hasattr(obj, func_name):
            raise AttributeError(f"Object {type(obj).__name__} has no attribute '{func_name}'")

        func = getattr(obj, func_name)

        if not callable(func):
            raise TypeError(f"'{func_name}' is not callable")

        return func(*args, **kwargs)

    # === PRIVATE METHODS ==============================================================================================
    def _get_config(self) -> BILBO_Config:
        config = get_bilbo_config(self._get_id())
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def _connection_check_task(self):
        while not self._exit:
            try:
                result = getSignalStrength('wlan0')
                if result is not None:
                    self.connection_strength = result['percent']
                else:
                    # No wlan0 interface (e.g. simulation on Mac) — stop checking
                    return
            except Exception:
                return
            self.internet_connected = check_internet(timeout=1)
            time.sleep(2)

    # ------------------------------------------------------------------------------------------------------------------
    def _throttle_check_task(self):
        # Check if vcgencmd is available (only on Raspberry Pi)
        if not os.path.exists('/usr/bin/vcgencmd'):
            return

        while not self._exit:
            try:
                # Read CPU temperature
                temp_result = subprocess.run(
                    ['vcgencmd', 'measure_temp'],
                    capture_output=True, text=True, timeout=2
                )
                temp_str = temp_result.stdout.strip()  # e.g. "temp=55.3'C"
                temperature = float(temp_str.split('=')[1].split("'")[0])

                # Read throttle status
                throttle_result = subprocess.run(
                    ['vcgencmd', 'get_throttled'],
                    capture_output=True, text=True, timeout=2
                )
                throttle_str = throttle_result.stdout.strip()  # e.g. "throttled=0x50005"
                throttle_hex = int(throttle_str.split('=')[1], 16)

                self.rpi_temperature = temperature
                self.rpi_throttle = throttle_hex

                # Bit flags (currently active):
                #   0: Under-voltage detected
                #   1: Arm frequency capped
                #   2: Currently throttled
                #   3: Soft temperature limit active
                warnings = []
                if throttle_hex & (1 << 0):
                    warnings.append("UNDER-VOLTAGE")
                if throttle_hex & (1 << 1):
                    warnings.append("FREQ CAPPED")
                if throttle_hex & (1 << 2):
                    warnings.append("THROTTLED")
                if throttle_hex & (1 << 3):
                    warnings.append("SOFT TEMP LIMIT")

                if warnings:
                    now = time.time()
                    if now - getattr(self, '_last_throttle_log', 0) >= 10:
                        self._last_throttle_log = now
                        # self.logger.warning(
                        #     f"RPi THROTTLING: {', '.join(warnings)} | Temp: {temperature:.1f}°C | Flags: {throttle_str}"
                        # )

            except Exception:
                return

            time.sleep(1)

    # ------------------------------------------------------------------------------------------------------------------
    # def _get_testbed_config(self) -> BILBO_TestbedConfig:
    #     testbed_file = f"{CONFIG_PATH}/testbed.yaml"
    #
    #     if not file_exists(testbed_file):
    #         raise FileNotFoundError("Testbed file not found. Run Bilbo Setup first")
    #
    #     with open(testbed_file, 'r') as file:
    #         config = yaml.safe_load(file)
    #
    #     config = from_dict_auto(BILBO_TestbedConfig, config)
    #     return config

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _get_id() -> str:
        id_file = f"{ROBOT_PATH}/ID"
        if not file_exists(id_file):
            raise FileNotFoundError("ID file not found. Run Bilbo Setup first")
        else:
            with open(id_file, 'r') as file:
                id = file.read()
            return id

    # ------------------------------------------------------------------------------------------------------------------
    def _on_timecode_sync(self, timecode: Timecode):
        if timecode.fps != 25.0:
            self.logger.warning(f"Timecode FPS is not 25.0. Got {timecode.fps}")
        else:
            self.timecode_listener.internal_fps = 50.0
            self.logger.info(f"Timecode synced: {timecode}. Set to 50 FPS internally.")
