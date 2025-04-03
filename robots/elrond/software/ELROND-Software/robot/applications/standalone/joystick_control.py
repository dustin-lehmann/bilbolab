import threading
import time

from utils.exit import ExitHandler
from utils.joystick.joystick import JoystickManager, JoystickManager_Callbacks, Joystick
from utils.logging_utils import Logger
from robot.control.definitions import BILBO_Control_Mode
from robot.bilbo import BILBO

# from robot.setup import readSettings

logger = Logger("JoystickControl")
logger.setLevel('INFO')


# ======================================================================================================================
class StandaloneJoystickControl:
    joystick_manager: JoystickManager
    joystick: Joystick
    twipr: BILBO

    _exit: bool = False
    _thread: threading.Thread

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, bilbo: BILBO):
        self.twipr = bilbo
        self.joystick_manager = JoystickManager()

        self.joystick_manager.callbacks.new_joystick.register(self._newJoystick_callback)
        self.joystick_manager.callbacks.joystick_disconnected.register(self._joystickDisconnected_callback)

        self.joystick = None
        self.exit = ExitHandler()
        self.exit.register(self.close)
        self._thread = threading.Thread(target=self._task, daemon=True)

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        self.joystick_manager.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.joystick_manager.start()
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self._exit = True
        if self._thread.is_alive():
            self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        while not self._exit:
            self._updateInputs()
            time.sleep(0.01)

    # ------------------------------------------------------------------------------------------------------------------
    def _updateInputs(self):
        if self.joystick is None:
            return
        # Read the controller inputs
        axis_forward = -self.joystick.axis[1]
        axis_turn = -self.joystick.axis[3]

        # Check the control mode
        if self.twipr.control.mode == BILBO_Control_Mode.OFF:
            return

        if self.twipr.control.mode == BILBO_Control_Mode.BALANCING:
            self.twipr.control.setNormalizedBalancingInput(axis_forward, axis_turn)

        elif self.twipr.control.mode == BILBO_Control_Mode.VELOCITY:
            ...
            # forward_cmd = axis_forward * self.robot_settings['external_inputs']['normalized_velocity_scale']['forward']
            # turn_cmd = axis_turn * self.robot_settings['external_inputs']['normalized_velocity_scale']['turn']
            # self.twipr.control.setSpeed(v=forward_cmd, psi_dot=turn_cmd)

    # ------------------------------------------------------------------------------------------------------------------
    def _newJoystick_callback(self, joystick, *args, **kwargs):
        if self.joystick is None:
            self.joystick = joystick

        self.joystick.setButtonCallback(button=0,
                                        event='down',
                                        function=self.twipr.control.setMode,
                                        parameters={'mode': BILBO_Control_Mode.OFF})

        self.joystick.setButtonCallback(button=1,
                                        event='down',
                                        function=self.twipr.control.setMode,
                                        parameters={'mode': BILBO_Control_Mode.BALANCING})

        self.joystick.setButtonCallback(button=2,
                                        event='down',
                                        function=self.twipr.control.setMode,
                                        parameters={'mode': BILBO_Control_Mode.VELOCITY})

        self.joystick.setButtonCallback(button=5,
                                        event='down',
                                        function=self.twipr.control.enableVelocityIntegralControl,
                                        parameters={'enable': True})

        self.joystick.setButtonCallback(button=4,
                                        event='down',
                                        function=self.twipr.control.enableVelocityIntegralControl,
                                        parameters={'enable': False})


        logger.info("Joystick connected and assigned")

    # ------------------------------------------------------------------------------------------------------------------
    def _joystickDisconnected_callback(self, joystick, *args, **kwargs):
        if joystick == self.joystick:
            self.joystick = None

        self.twipr.control.setMode(BILBO_Control_Mode.OFF)
        logger.info("Joystick disconnected")

    # ------------------------------------------------------------------------------------------------------------------
