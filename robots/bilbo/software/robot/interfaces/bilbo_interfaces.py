import enum
import threading
import time

from core.communication.wifi.data_link import CommandArgument
# === CUSTOM PACKAGES ==================================================================================================
from core.hardware.joystick.joystick_manager import JoystickManager, Joystick
from core.utils.logging_utils import Logger
from core.utils.sound.sound import playSound
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control
from core.utils.exit import register_exit_callback
from robot.control.bilbo_control_definitions import BILBO_Control_Mode
from robot.drive.bilbo_drive import BILBO_Drive
from robot.interfaces.bilbo_display import BILBO_Display


# ======================================================================================================================
class InputSource(enum.Enum):
    NONE = 'NONE'
    JOYSTICK = 'JOYSTICK'
    WIFI_JOYSTICK = 'WIFI_JOYSTICK'
    # APP = 'APP'
    # EXTERNAL = 'EXTERNAL'


# ======================================================================================================================
JOYSTICK_MAPPING = {
    'CONTROL_MODE_BALANCING': "A",
    'CONTROL_MODE_OFF': "B",
    'CONTROL_MODE_VELOCITY': "X",
    "TIC_ENABLE": "DPAD_UP",
    "TIC_DISABLE": "DPAD_DOWN",
    "AXIS_TORQUE_FORWARD": "LEFT_VERTICAL",
    "AXIS_TORQUE_TURN": "RIGHT_HORIZONTAL",
    "ACCEPT": "DPAD_RIGHT",
    "CANCEL": "DPAD_LEFT"
}


# ======================================================================================================================
class BILBO_Interfaces:
    communication: BILBO_Communication

    display: BILBO_Display | None = None

    input_source: InputSource

    external_input_enabled: bool = True

    _external_joystick_input: tuple[float, float] = (0, 0)
    _app_input: tuple[float, float] = (0, 0)
    _joystick_input: tuple[float, float] = (0, 0)

    _joystick: Joystick
    _joystick_manager: JoystickManager | None
    _input_thread: threading.Thread
    _exit_input_task: bool

    def __init__(self, core: BILBO_Common,
                 communication: BILBO_Communication,
                 drive: BILBO_Drive,
                 control: BILBO_Control,
                 joystick_enabled: bool = True):
        self.logger = Logger('interfaces')
        self.logger.setLevel('DEBUG')
        self.core = core
        self.communication = communication
        self.control = control
        self.drive = drive

        self.joystick_enabled = joystick_enabled

        config = self.core.config

        self.has_display = config.electronics.display.active is not False

        if self.has_display:
            self.display = BILBO_Display(core=self.core)

        if self.joystick_enabled:
            self._joystick_manager = JoystickManager()
            self._joystick_manager.callbacks.new_joystick.register(self._onJoystickConnected)
            self._joystick_manager.callbacks.joystick_disconnected.register(self._onJoystickDisconnected)
        else:
            self._joystick_manager = None
            self.logger.info('Joystick disabled by settings')

        self._joystick = None  # type: ignore

        self.communication.wifi.newCommand(
            identifier='resume',
            function=self.core.setResumeEvent,
            arguments=[CommandArgument(
                name='data',
                type='any',
                optional=True,
                default=None,
                description='Data to resume with (optional)'
            )],
            description='Resume the robot'
        )

        self.communication.wifi.newCommand(
            identifier='repeat',
            function=self.core.setRepeatEvent,
            arguments=[CommandArgument(
                name='data',
                type='any',
                optional=True,
                default=None,
                description='Data to repeat with (optional)'
            )],
            description='Repeat the last action'
        )

        self.communication.wifi.newCommand(
            identifier='stop',
            function=self.core.setStopEvent,
            arguments=[CommandArgument(
                name='data',
                type='any',
                optional=True,
                default=None,
                description='Data to stop with (optional)'
            )],
            description='Stop the current action'
        )

        self.communication.wifi.newCommand(
            identifier='start',
            function=self.core.setStartEvent,
            arguments=[CommandArgument(
                name='data',
                type='any',
                optional=True,
                default=None,
                description='Data to start with (optional)'
            )],
            description='Start the current action'
        )

        self.communication.wifi.newCommand(
            identifier='set_joystick_input',
            function=self._set_external_joystick_input,
            arguments=[CommandArgument(name='forward', type=float), CommandArgument(name='turn', type=float)],
            description='Set the joystick input'
        )

        self.communication.wifi.newCommand(
            identifier='set_input_source',
            function=self.set_input_source,
            arguments=[CommandArgument(name='source', type=str)],
            description='Set the input source'
        )

        self.communication.wifi.newCommand(
            identifier='set_external_input_enabled',
            function=self.set_external_input_enabled,
            arguments=[CommandArgument(name='enabled', type=bool)],
            description='Enable or disable external input (joystick/wifi)'
        )

        self._input_thread = None  # type: ignore
        self._exit_input_task = False

        self.input_source = InputSource.NONE

        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info('Start Interfaces')
        if self._joystick_manager is not None:
            self._joystick_manager.start()

        if self.has_display:
            self.display.start()

        self._input_thread = threading.Thread(target=self._input_task, daemon=True)
        self._input_thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.logger.info('Stop Interfaces')
        if self._joystick_manager is not None:
            self._joystick_manager.close()

        self._exit_input_task = True
        if self._input_thread is not None and self._input_thread.is_alive():
            self._input_thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def enable_external_input(self):
        self.external_input_enabled = True
        # Zero the relevant input for the current mode
        if self.control.mode == BILBO_Control_Mode.BALANCING:
            self.control.set_external_input(0, 0)
        elif self.control.mode == BILBO_Control_Mode.VELOCITY:
            self.control.set_velocity(0, 0)

    # ------------------------------------------------------------------------------------------------------------------
    def disable_external_input(self):
        self.external_input_enabled = False
        # Zero the relevant input for the current mode
        if self.control.mode == BILBO_Control_Mode.BALANCING:
            self.control.set_external_input(0, 0)
        elif self.control.mode == BILBO_Control_Mode.VELOCITY:
            self.control.set_velocity(0, 0)

    # === PRIVATE METHODS ==============================================================================================
    def _onJoystickConnected(self, joystick, *args, **kwargs):
        self.logger.info(f'Joystick connected: {joystick.name}')
        self.core.joystick_connected = True
        self.core.events.joystick_connected.set()
        self._joystick = joystick

        self.input_source = InputSource.JOYSTICK

        self._joystick.buttons['A'].callbacks.pressed.register(
            self.control.set_mode,
            mode=BILBO_Control_Mode.BALANCING,
        )
        self._joystick.buttons['A'].callbacks.long_pressed.register(
            self.control.set_mode,
            mode=BILBO_Control_Mode.VELOCITY,
        )

        self._joystick.buttons['B'].callbacks.pressed.register(
            self.control.set_mode,
            mode=BILBO_Control_Mode.OFF,
        )

        self._joystick.buttons['X'].callbacks.pressed.register(
            playSound,
            file='horn_double.mp3',
            volume=2
        )

        self._joystick.buttons['Y'].callbacks.pressed.register(
            self.control.set_mode,
            mode=BILBO_Control_Mode.POSITION,
        )

        self._joystick.hat['up'].callbacks.pressed.register(self.control.enable_tic_control, enable=True)
        self._joystick.hat['down'].callbacks.pressed.register(self.control.enable_tic_control, enable=False)
        self._joystick.hat['right'].callbacks.pressed.register(self.core.setResumeEvent, data=True)
        self._joystick.buttons['L1'].callbacks.pressed.register(self.drive.reset)

    # ------------------------------------------------------------------------------------------------------------------
    def _onJoystickDisconnected(self, joystick, *args, **kwargs):
        if joystick == self._joystick:
            self._joystick = None  # type: ignore
            # joystick.clearAllButtonCallbacks()
            self.logger.info(f'Joystick disconnected: {joystick.name}')
            self.core.joystick_connected = False
            self.core.events.joystick_disconnected.set()
            self.input_source = InputSource.NONE

    # ------------------------------------------------------------------------------------------------------------------
    def _input_task(self):

        while not self._exit_input_task:
            time.sleep(0.1)

            if not self.external_input_enabled:
                continue

            match self.input_source:
                case InputSource.JOYSTICK:
                    if self._joystick is not None:
                        axis_forward = self._joystick.get_axis("LEFT_VERTICAL")
                        axis_turn = -self._joystick.get_axis("RIGHT_HORIZONTAL")
                        axis_boost = (self._joystick.get_axis("TRIGGER_RIGHT") + 1) / 2  # now is 0 to 1

                        match self.control.mode:
                            case BILBO_Control_Mode.BALANCING:

                                # print(f"axis_forward: {axis_forward:.1f}, axis_turn: {axis_turn:.1f}")
                                self.control.set_external_input_forward_turn(axis_forward, axis_turn, normalized=True)
                            case BILBO_Control_Mode.VELOCITY:
                                scale = (2 / 3) + (1 / 3) * axis_boost
                                # forward_command = axis_forward * scale
                                forward_command = axis_forward
                                self.control.set_velocity(forward_command, axis_turn, normalized=True)
                case InputSource.WIFI_JOYSTICK:
                    input = self._external_joystick_input

                case _:
                    input = (0, 0)

            # self.control.setNormalizedBalancingInput(*input)

    # ------------------------------------------------------------------------------------------------------------------
    def _set_external_joystick_input(self, forward, turn):
        self._external_joystick_input = (forward, turn)

        if not self.external_input_enabled:
            return

        if self.control.mode == BILBO_Control_Mode.BALANCING:
            if self.input_source == InputSource.WIFI_JOYSTICK:
                self.control.set_external_input_forward_turn(forward, turn, normalized=True)
        elif self.control.mode == BILBO_Control_Mode.VELOCITY:
            self.control.set_velocity(forward, turn, normalized=True)

    # ------------------------------------------------------------------------------------------------------------------
    def set_input_source(self, source: str):
        self.input_source = InputSource[source]
        self.logger.info(f'Set input source to {source}')

    # ------------------------------------------------------------------------------------------------------------------
    def set_external_input_enabled(self, enabled: bool):
        if enabled:
            self.enable_external_input()
        else:
            self.disable_external_input()
        self.logger.info(f'External input {"enabled" if enabled else "disabled"}')
