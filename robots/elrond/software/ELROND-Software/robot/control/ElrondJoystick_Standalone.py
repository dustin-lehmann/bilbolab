import threading
import time

from _tests.test_trajectories_elrond import elrond_experiment_test_trajectory, startManualExperimentButton, stopManualExperimentButton
from utils.files import relativeToFullPath
from utils.joystick.joystick import JoystickManager, Joystick
from utils.logging_utils import Logger
from robot.control.definitions import BILBO_Control_Mode
from robot.drive.actuator_dynamixel import ELROND_Dynamixel_Handler
from robot.elrond import BILBO


class ElrondJoystick:
    _elrond: BILBO
    joystick: Joystick
    _joystick_manager: JoystickManager
    _joystick_thread: threading.Thread
    _exit_joystick_thread: bool

    def __init__(self, elrond : BILBO, logger : Logger):

        self._elrond = elrond
        self._joystick_manager = JoystickManager()
        self._joystick_manager.callbacks.new_joystick.register(self._onNewJoystick)
        self._joystick_manager.callbacks.joystick_disconnected.register(self._onJoystickDisconnect)
        self.joystick = None  # type: ignore

        self.logger = logger

        self._exit_joystick_thread = False
        self._joystick_thread = None  # type: ignore

    def start(self):
        self._joystick_manager.start()
        self.logger.info("Joystick manager started!")


    def reset(self):
        ...
        #self._xgo.rider_reset()

    def move(self, forward=0, turn=0):
        forward = self._map_value(forward, -1, 1, -5, 5)
        turn = self._map_value(turn, -1, 1, -300, 300)
        #self._xgo.rider_move_x(forward)
        #self._xgo.rider_turn(turn)

    def setHeight(self, height: float):
        height = self._map_value(height, 0, 1, -255, 200)
        #self._xgo.rider_height(height)

    def setRoll(self, roll: float):
        roll = self._map_value(roll, -1, 1, -20, 20)
        #self._xgo.rider_roll(roll)

    @staticmethod
    def _map_value(value, from_low, from_high, to_low, to_high):
        return (value - from_low) * (to_high - to_low) / (from_high - from_low) + to_low

    def _onNewJoystick(self, joystick):
        if self.joystick is not None:
            return

        self.joystick = joystick
        # set all the button callbacks
        #self.joystick.setButtonCallback(0, 'down', self.reset)

        # B Button on joystick
        self.joystick.setButtonCallback(button=0,
                                        event='down',
                                        function=self._elrond.control.setMode,
                                        parameters={'mode': BILBO_Control_Mode.OFF})
        # A Button on joystick
        self.joystick.setButtonCallback(button=1,
                                        event='down',
                                        function=self._elrond.control.setMode,
                                        parameters={'mode': BILBO_Control_Mode.BALANCING})

        # Start Button on joystick
        self.joystick.setButtonCallback(button=7,
                                        event='down',
                                        function=startManualExperimentButton,
                                        parameters={'elrond' :self._elrond})
        # Select Button on joystick
        self.joystick.setButtonCallback(button=6,
                                        event='down',
                                        function=stopManualExperimentButton,
                                        parameters={'elrond' :self._elrond})
        # Pixel Heart Button on joystick
        self.joystick.setButtonCallback(button=10,
                                       event='down',
                                       function=elrond_experiment_test_trajectory,
                                       parameters={'elrond': self._elrond})

        self.logger.info(f"New Joystick connected: {joystick.name}")

        self._joystick_thread = threading.Thread(target=self._joystick_task, daemon=True)
        self._joystick_thread.start()

    def _onJoystickDisconnect(self, joystick):
        """
        Callback function for when a joystick is disconnected.

        When a joystick is disconnected, this function is called. It checks if the
        disconnected joystick is the one currently being used, and if so, sets the
        control mode to OFF and stops the joystick thread.

        Args:
            joystick (Joystick): The joystick that was disconnected.
        """
        if joystick == self.joystick:
            self._elrond.control.setMode(BILBO_Control_Mode.OFF)
            self.logger.warning(f"Joystick disconnected: {joystick.name}")
            self.joystick = None  # type: ignore
            #self.move(0, 0)

            self._exit_joystick_thread = True
            self._joystick_thread.join()
            self._exit_joystick_thread = False
            self._joystick_thread = None  # type: ignore

    def _joystick_task(self):
        while not self._exit_joystick_thread:
            if self.joystick is not None:
                axis_forward = -self.joystick.axis[1]
                axis_turn = -self.joystick.axis[3]
                #axis_height = self.joystick.axis[2]
                #print(axis_forward, axis_turn)
                # Check the control mode
                #if self._elrond.control.mode == BILBO_Control_Mode.OFF:
                #    return

                #if self._elrond.control.mode == BILBO_Control_Mode.BALANCING:
                self._elrond.control.setNormalizedBalancingInput(axis_forward, axis_turn)

            else:
                self._elrond.control.setNormalizedBalancingInput(0, 0)

            time.sleep(0.1)
