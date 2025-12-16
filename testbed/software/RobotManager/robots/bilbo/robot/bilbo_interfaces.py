import math
import threading
import time
from enum import Enum

# === CUSTOM PACKAGES ==================================================================================================
from core.utils.sound.sound import speak
from extensions.cli.cli import CommandSet, Command, CommandArgument
from extensions.joystick.joystick_manager import Joystick
from core.utils.curve_utils import shape_joystick, JoystickCurve
from robots.bilbo.robot.bilbo_control import BILBO_Control
from robots.bilbo.robot.bilbo_core import BILBO_Core
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from robots.bilbo.robot.bilbo_data import bilboSampleFromDict
from core.utils.callbacks import CallbackContainer, callback_definition, Callback
from core.utils.events import event_definition, Event, pred_flag_contains, SubscriberListener
from core.utils.exit import register_exit_callback
from robots.bilbo.robot.experiment.bilbo_experiment import BILBO_ExperimentHandler
from robots.bilbo.robot.bilbo_utilities import BILBO_Utilities

# ======================================================================================================================

JOYSTICK_UPDATE_TIME = 0.05


# ======================================================================================================================
@callback_definition
class BILBO_Interfaces_Callbacks:
    joystick_connected: CallbackContainer
    joystick_disconnected: CallbackContainer


@event_definition
class BILBO_Interfaces_Events:
    joystick_connected: Event
    joystick_disconnected: Event


# ======================================================================================================================
class BILBO_Interfaces:
    joystick: Joystick | None
    live_plots: list[dict]

    joystick_thread: threading.Thread | None
    _exit_joystick_thread: bool

    _joystick_event_listeners: list[SubscriberListener]

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, core: BILBO_Core,
                 control: BILBO_Control,
                 utilities: BILBO_Utilities,
                 experiments: BILBO_ExperimentHandler):

        self.core = core
        self.control = control
        self.utilities = utilities
        self.experiments = experiments
        self.cli_command_set = BILBO_CLI_CommandSet(core=self.core,
                                                    control=self.control,
                                                    experiments=self.experiments,
                                                    utilities=self.utilities)

        self.joystick = None
        self.joystick_thread = None

        self._exit_joystick_thread = False
        self._joystick_event_listeners = []

        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.removeJoystick()

    # ------------------------------------------------------------------------------------------------------------------
    def addJoystick(self, joystick: Joystick):

        self.core.logger.info("Add Joystick")
        speak(f"Joystick {joystick.id} assigned to {self.core.id}")

        self.joystick = joystick

        listener = self.joystick.events.button.on(self.core.setResumeEvent,
                                                  predicate=pred_flag_contains('button', 'DPAD_RIGHT'),
                                                  discard_data=True)
        self._joystick_event_listeners.append(listener)

        listener = self.joystick.events.button.on(self.core.setRevertEvent,
                                                  predicate=pred_flag_contains('button', 'DPAD_LEFT'),
                                                  discard_data=True)
        self._joystick_event_listeners.append(listener)

        listener = self.joystick.events.button.on(Callback(self.control.enableTIC,
                                                           inputs={'state': True},
                                                           discard_inputs=True),
                                                  predicate=pred_flag_contains('button', 'DPAD_UP'),
                                                  discard_data=True)
        self._joystick_event_listeners.append(listener)
        listener = self.joystick.events.button.on(Callback(self.control.enableTIC,
                                                           inputs={'state': False},
                                                           discard_inputs=True),
                                                  predicate=pred_flag_contains('button', 'DPAD_DOWN'),
                                                  discard_data=True)
        self._joystick_event_listeners.append(listener)
        listener = self.joystick.events.button.on(Callback(self.control.setControlMode,
                                                           inputs={'mode': BILBO_Control_Mode.BALANCING},
                                                           discard_inputs=True),
                                                  predicate=pred_flag_contains('button', 'A'),
                                                  discard_data=True,
                                                  )
        self._joystick_event_listeners.append(listener)
        listener = self.joystick.events.button.on(Callback(self.control.setControlMode,
                                                           inputs={'mode': BILBO_Control_Mode.OFF},
                                                           discard_inputs=True),
                                                  predicate=pred_flag_contains('button', 'B'),
                                                  )
        self._joystick_event_listeners.append(listener)
        listener = self.joystick.events.button.on(callback=self.core.beep,
                                                  predicate=pred_flag_contains('button', 'X'),
                                                  discard_data=True,
                                                  )
        self._joystick_event_listeners.append(listener)
        self._startJoystickThread()

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self):
        if self.joystick is not None:
            self.core.logger.info("Remove Joystick")
            speak(f"Joystick {self.joystick.id} removed from {self.core.id}")
            self.joystick.clearAllButtonCallbacks()
            try:
                for listener in self._joystick_event_listeners:
                    listener.stop()
            except Exception as e:
                self.core.logger.error(f"Error stopping joystick event listeners: {e}")
            self._joystick_event_listeners = []
            self.joystick = None

        if self.joystick_thread is not None and self.joystick_thread.is_alive():
            self._exit_joystick_thread = True
            self.joystick_thread.join()
            self.joystick_thread = None
            self.core.logger.info("Joystick thread closed.")

    # ------------------------------------------------------------------------------------------------------------------
    def _startJoystickThread(self):
        self.joystick_thread = threading.Thread(target=self._joystick_task, daemon=True)
        self.joystick_thread.start()
        self.core.logger.info(
            f"Joystick thread started for {self.core.id}."
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _joystick_task(self):
        self._exit_joystick_thread = False
        while not self._exit_joystick_thread:
            # Raw inputs still expected in [-1, 1]
            raw_forward = -self.joystick.getAxis('LEFT_VERTICAL')
            raw_turn = -self.joystick.getAxis('RIGHT_HORIZONTAL')

            # Shape them using the global curve
            forward_joystick = shape_joystick(raw_forward, JoystickCurve.POWER, 2)
            turn_joystick = shape_joystick(raw_turn, JoystickCurve.POWER, 2)

            # Send normalized, shaped inputs to the controller
            self.control.setNormalizedBalancingInput(forward_joystick, turn_joystick)

            time.sleep(JOYSTICK_UPDATE_TIME)

    # ------------------------------------------------------------------------------------------------------------------


# ======================================================================================================================
class BILBO_CLI_CommandSet(CommandSet):

    def __init__(self, core: BILBO_Core, control: BILBO_Control, experiments: BILBO_ExperimentHandler,
                 utilities: BILBO_Utilities):
        self.core = core
        self.control = control
        self.experiments = experiments
        self.utilities = utilities

        beep_command = Command(name='beep',
                               function=self.core.beep,
                               allow_positionals=True,
                               arguments=[
                                   CommandArgument(name='frequency',
                                                   type=int,
                                                   short_name='f',
                                                   description='Frequency of the beep',
                                                   is_flag=False,
                                                   optional=True,
                                                   default=700),
                                   CommandArgument(name='time_ms',
                                                   type=int,
                                                   short_name='t',
                                                   description='Time of the beep in milliseconds',
                                                   is_flag=False,
                                                   optional=True,
                                                   default=250),
                                   CommandArgument(name='repeats',
                                                   type=int,
                                                   short_name='r',
                                                   description='Number of repeats',
                                                   is_flag=False,
                                                   optional=True,
                                                   default=1)
                               ],
                               description='Beeps the Buzzer')

        speak_command = Command(name='speak',
                                function=self.core.speak,
                                allow_positionals=True,
                                arguments=[
                                    CommandArgument(name='text',
                                                    type=str,
                                                    short_name='t',
                                                    description='Text to speak',
                                                    is_flag=False,
                                                    optional=True,
                                                    default=None)
                                ], )

        mode_command = Command(name='mode',
                               function=self.control.setControlMode,
                               allow_positionals=True,
                               arguments=[
                                   CommandArgument(name='mode',
                                                   type=int,
                                                   short_name='m',
                                                   description='Mode of control (0:off, 1:direct, 2:torque)',
                                                   is_flag=False,
                                                   optional=False,
                                                   default=None)
                               ], )

        stop_command = Command(name='stop',
                               function=Callback(
                                   function=self.control.setControlMode,
                                   inputs={'mode': BILBO_Control_Mode.OFF},
                                   discard_inputs=True,
                               ),
                               description='Deactivates the control on the robot',
                               arguments=[])

        read_state_command = Command(name='read',
                                     function=self.control.getControlState,
                                     description='Reads the current control state and mode', )


        test_communication = Command(name='testComm',
                                     function=Callback(
                                         function=self.utilities.test_response_time,
                                         execute_in_thread=True,
                                     ),
                                     description='Tests the communication with the robot',
                                     arguments=[
                                         CommandArgument(name='iterations',
                                                         short_name='i',
                                                         type=int,
                                                         optional=True,
                                                         default=10,
                                                         description='Number of iterations to test')
                                     ])

        statefeedback_command = Command(name='sfg',
                                        function=self.control.setStateFeedbackGain,
                                        allow_positionals=True,
                                        arguments=[
                                            CommandArgument(name='gain',
                                                            type=list[float],
                                                            array_size=8,
                                                            short_name='g',
                                                            description='State feedback gain',
                                                            )
                                        ], )

        forward_pid_command = Command(name='fpid',
                                      function=self.control.setForwardPID,
                                      allow_positionals=True,
                                      arguments=[
                                          CommandArgument(name='p',
                                                          type=float,
                                                          short_name='p',
                                                          description='Forward PID P',
                                                          ),
                                          CommandArgument(name='i',
                                                          type=float,
                                                          short_name='i',
                                                          description='Forward PID I',
                                                          ),
                                          CommandArgument(name='d',
                                                          type=float,
                                                          short_name='d',
                                                          description='Forward PID D',
                                                          ),
                                      ], )

        turn_pid_command = Command(name='tpid',
                                   allow_positionals=True,
                                   function=self.control.setTurnPID,
                                   arguments=[
                                       CommandArgument(name='p',
                                                       type=float,
                                                       short_name='p',
                                                       description='Turn PID P',
                                                       ),
                                       CommandArgument(name='i',
                                                       type=float,
                                                       short_name='i',
                                                       description='Turn PID I',
                                                       ),
                                       CommandArgument(name='d',
                                                       type=float,
                                                       short_name='d',
                                                       description='Turn PID D',
                                                       ),
                                   ])

        read_control_config_command = Command(name='read',
                                              function=self.control.readControlConfiguration,
                                              description='Reads the current control configuration',
                                              arguments=[])

        control_command_set = CommandSet(name='control', commands=[
            statefeedback_command,
            forward_pid_command,
            turn_pid_command,
            read_control_config_command,
        ])

        test_trajectory_command = Command(name='traj',
                                          allow_positionals=True,
                                          function=self.experiments.run_random_trajectory,
                                          execute_in_thread=True,
                                          arguments=[
                                              CommandArgument(name='time_s',
                                                              short_name='t',
                                                              type=float,
                                                              description='Time to run the trajectory',
                                                              optional=False, ),
                                              CommandArgument(name='frequency',
                                                              short_name='f',
                                                              type=float,
                                                              description='Frequency of the Input',
                                                              optional=True,
                                                              default=3),
                                              CommandArgument(name='gain',
                                                              short_name='g',
                                                              type=float,
                                                              description='Gain of the Input',
                                                              optional=True,
                                                              default=0.1),
                                          ])

        test_experiment_command = Command(name='exp',
                                          function=self.experiments.run_experiment_from_file,
                                          allow_positionals=True,
                                          execute_in_thread=True,
                                          arguments=[
                                              CommandArgument(name='file',
                                                              short_name='f',
                                                              type=str,
                                                              description='File to run the experiment from',
                                                              optional=False, )

                                          ])

        experiment_command_set = CommandSet(name='experiment',
                                            commands=[test_trajectory_command, test_experiment_command])


        super().__init__(name=f"{self.core.id}", commands=[beep_command,
                                                           speak_command,
                                                           mode_command,
                                                           # sendWaypoints_command,
                                                           # send_K_Pos_command,
                                                           # send_Pos_config,
                                                           stop_command,
                                                           read_state_command,
                                                           test_communication],

                         children=[control_command_set, experiment_command_set])
