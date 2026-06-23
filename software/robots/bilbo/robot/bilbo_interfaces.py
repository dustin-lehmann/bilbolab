import math
import threading
import time
from enum import Enum

# === CUSTOM PACKAGES ==================================================================================================
from core.utils.sound.sound import speak
from extensions.tools.cli.cli import CommandSet, Command, CommandArgument
from extensions.gui.src.lib.objects.python.joystick import JoystickWidget
from extensions.hardware.joystick.joystick_manager import Joystick
from core.utils.curve_utils import shape_joystick, JoystickCurve
from robots.bilbo.robot.bilbo_control import BILBO_Control
from robots.bilbo.robot.bilbo_core import BILBO_Core
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from robots.bilbo.robot.bilbo_position_control import BILBO_PositionControl
from robots.bilbo.robot.bilbo_data import bilboSampleFromDict
from core.utils.callbacks import CallbackContainer, callback_definition, Callback
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from robots.bilbo.robot.experiment.bilbo_experiment_handler import BILBO_ExperimentHandler
from robots.bilbo.robot.bilbo_utilities import BILBO_Utilities

# ======================================================================================================================

JOYSTICK_UPDATE_TIME = 0.075


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


# Assist-mixing strategies (how the master's axis is combined with the user's). See
# _mix_assist. Selectable per robot via set_assist_joystick(..., mode=...).
ASSIST_MIX_ADDITIVE = 'additive'    # output = clamp(user + gain * master)  — legacy
ASSIST_MIX_AUTHORITY = 'authority'  # master authority grows with its own deflection
ASSIST_MIX_MODES = (ASSIST_MIX_ADDITIVE, ASSIST_MIX_AUTHORITY)


def _mix_assist(user: float, master: float, gain: float, mode: str) -> float:
    """Combine a primary (``user``) axis with the master's ``assist`` axis, in [-1, 1].

    additive (legacy):
        ``clamp(user + gain*master)``. Equal-and-opposite inputs simply cancel, so a
        full-deflection user can tie a full-deflection master regardless of intent.

    authority:
        The master's authority scales with how hard *it* pushes. With its gain-scaled
        command ``m = clamp(gain*master)`` and weight ``w = |m|``::

            output = clamp((1 - w) * user + m)

        So the master crossfades the user out as it pushes harder and injects its own
        command: at full master deflection (×gain) it overrides the user entirely; at
        rest the user has full control. With gain=1, master 100% one way → that way;
        master 50% vs a full-opposite user → they tie. ``gain`` (assist_gain) caps the
        master's reachable authority: 1.0 lets it fully override, 0.5 only neutralise.
    """
    if mode == ASSIST_MIX_AUTHORITY:
        m = _clamp(gain * master)
        return _clamp((1.0 - abs(m)) * user + m)
    # Default / legacy additive mixing.
    return _clamp(user + gain * master)


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
    app_joystick_widgets: dict[str, JoystickWidget] | None

    joystick: Joystick | None
    # Optional low-authority "assist" input (e.g. the expo master joystick) whose
    # axes are mixed into the primary input. See _joystick_task / set_assist_joystick.
    assist_joystick: Joystick | None
    assist_gain: float
    assist_mix_mode: str  # how the assist axis is mixed with the user's — see _mix_assist
    # Per-robot input "speed": scales the primary (user) input axes before they are sent.
    # 1.0 = full range; forward and turn scale independently. Bypassed while the master
    # fully overrides this robot so the operator always has full range. See _joystick_task.
    input_scale_forward: float
    input_scale_turn: float
    bypass_input_scale: bool
    # Optional "boost" input (e.g. the expo master joystick): its RIGHT_TRIGGER (R2)
    # multiplies the forward command in BALANCING/VELOCITY. See _joystick_task / set_boost.
    boost_joystick: Joystick | None
    boost_scale_balancing: float
    boost_scale_velocity: float
    live_plots: list[dict]

    _joystick_thread: threading.Thread | None
    _joystick_stop_event: threading.Event
    _joystick_lock: threading.Lock

    joystick_enabled: bool = True

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, core: BILBO_Core,
                 control: BILBO_Control,
                 position_control: BILBO_PositionControl,
                 utilities: BILBO_Utilities,
                 experiments: BILBO_ExperimentHandler):

        self.core = core
        self.control = control
        self.position_control = position_control
        self.utilities = utilities
        self.experiments = experiments
        self.cli_command_set = BILBO_CLI_CommandSet(core=self.core,
                                                    control=self.control,
                                                    position_control=self.position_control,
                                                    experiments=self.experiments,
                                                    utilities=self.utilities,
                                                    interfaces=self)

        self.joystick = None
        self.app_joystick_widgets = None
        self.assist_joystick = None
        self.assist_gain = 0.5
        self.assist_mix_mode = ASSIST_MIX_ADDITIVE
        self.input_scale_forward = 1.0
        self.input_scale_turn = 1.0
        self.bypass_input_scale = False
        self.boost_joystick = None
        self.boost_scale_balancing = 0.0
        self.boost_scale_velocity = 0.0
        self.boost_scale_turn_balancing = 0.0
        self.boost_scale_turn_velocity = 0.0
        # Last (forward, turn) boost factors pushed to the robot (so we only send on change).
        self._last_boost_sent: tuple[float, float] | None = None

        self._joystick_thread = None
        self._joystick_stop_event = threading.Event()
        self._joystick_lock = threading.Lock()

        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.clear_boost()
        self.clear_assist_joystick()
        self.removeJoystick()
        self.remove_app_joystick_widgets()

    # ------------------------------------------------------------------------------------------------------------------
    def addJoystick(self, joystick: Joystick):
        # Remove any existing joystick first
        if self.joystick is not None:
            self.removeJoystick()

        self.core.logger.info("Add Joystick")
        speak(f"Joystick {joystick.id} assigned to {self.core.id}")

        self.joystick = joystick

        self.bind_buttons(joystick)

        self.set_input_source('WIFI_JOYSTICK')
        self._start_joystick_thread()

    # ------------------------------------------------------------------------------------------------------------------
    def bind_buttons(self, joystick: Joystick):
        """Wire a joystick's buttons to this robot's control actions.

        Used for a robot's own assigned joystick (via :meth:`addJoystick`) and for
        the expo master joystick when it targets this robot — so the master can
        actuate the robot's buttons (A/B/X/Y/...) without being its primary driver.
        Only registers button callbacks; it does not touch the input source or the
        drive thread.

        Button mappings (matching on-robot bilbo_interfaces):
          A press      → BALANCING mode      A long press → VELOCITY mode
          B press      → OFF mode            X press      → beep
          Y press      → POSITION mode       L1           → reset drive
          DPAD_UP/DOWN → enable/disable TIC  DPAD_RIGHT/LEFT → resume/revert
        """
        joystick.buttons['A'].callbacks.pressed.register(
            self.control.setControlMode, mode=BILBO_Control_Mode.BALANCING)
        joystick.buttons['A'].callbacks.long_pressed.register(
            self.control.setControlMode, mode=BILBO_Control_Mode.VELOCITY)

        joystick.buttons['B'].callbacks.pressed.register(
            self.control.setControlMode, mode=BILBO_Control_Mode.OFF)

        joystick.buttons['X'].callbacks.pressed.register(self.core.beep)

        joystick.buttons['Y'].callbacks.pressed.register(
            self.control.setControlMode, mode=BILBO_Control_Mode.POSITION)

        joystick.buttons['L1'].callbacks.pressed.register(self.core.reset_drive)

        # DPAD: on macOS these are buttons, on Linux they are hat events.
        # Register on both so it works regardless of platform.
        if 'DPAD_UP' in joystick.buttons:
            joystick.buttons['DPAD_UP'].callbacks.pressed.register(
                self.control.enableTIC, state=True)
            joystick.buttons['DPAD_DOWN'].callbacks.pressed.register(
                self.control.enableTIC, state=False)
            joystick.buttons['DPAD_RIGHT'].callbacks.pressed.register(self.core.set_resume_event_robot)
            joystick.buttons['DPAD_LEFT'].callbacks.pressed.register(self.core.set_repeat_event_robot)

        joystick.hat['up'].callbacks.pressed.register(self.control.enableTIC, state=True)
        joystick.hat['down'].callbacks.pressed.register(self.control.enableTIC, state=False)
        joystick.hat['right'].callbacks.pressed.register(self.core.set_resume_event_robot)
        joystick.hat['left'].callbacks.pressed.register(self.core.set_repeat_event_robot)

    # ------------------------------------------------------------------------------------------------------------------
    def set_app_joystick_widgets(self, widgets: dict[str, JoystickWidget]):
        if 'forward' not in widgets or 'turn' not in widgets:
            self.core.logger.error("Joystick widgets must contain 'forward' and 'turn' keys")
            return

        self.app_joystick_widgets = widgets
        self.core.logger.info("App Joystick Widgets set")

        self.set_input_source('WIFI_JOYSTICK')
        self._start_joystick_thread()

    # ------------------------------------------------------------------------------------------------------------------
    def remove_app_joystick_widgets(self):
        if self.app_joystick_widgets is None:
            return

        self.core.logger.info("Remove App Joystick Widgets")
        self.app_joystick_widgets = None

        # Stop joystick thread if no input source remains
        if self.joystick is None and self.assist_joystick is None:
            self._stop_joystick_thread()
            self.set_input_source('NONE')

    # ------------------------------------------------------------------------------------------------------------------
    def set_assist_joystick(self, joystick: Joystick, gain: float | None = None,
                            mode: str | None = None):
        """Add a low-authority *assist* input that is mixed into the primary input.

        Used by the expo master joystick's "Assist" override mode: the master can
        nudge a robot that is otherwise driven by its own (user) joystick or app
        widgets. ``mode`` selects how the master's axis is combined with the user's
        (``'additive'`` legacy or ``'authority'`` — see :meth:`_mix_assist`); ``gain``
        is the master's authority. If the robot currently has no primary input source,
        the assist input becomes the only contributor (scaled by ``gain``).
        """
        self.assist_joystick = joystick
        if gain is not None:
            self.assist_gain = gain
        if mode is not None:
            if mode not in ASSIST_MIX_MODES:
                self.core.logger.warning(
                    f"Unknown assist mix mode '{mode}', keeping '{self.assist_mix_mode}'")
            else:
                self.assist_mix_mode = mode
        self.core.logger.info(
            f"Assist joystick {joystick.id} set (gain={self.assist_gain}, mix={self.assist_mix_mode})")

        self.set_input_source('WIFI_JOYSTICK')
        self._start_joystick_thread()

    # ------------------------------------------------------------------------------------------------------------------
    def clear_assist_joystick(self):
        if self.assist_joystick is None:
            return

        self.core.logger.info("Clear assist joystick")
        self.assist_joystick = None

        # Stop joystick thread if no input source remains
        if self.joystick is None and self.app_joystick_widgets is None:
            self._stop_joystick_thread()
            self.set_input_source('NONE')

    # ------------------------------------------------------------------------------------------------------------------
    def set_input_scale(self, forward: float, turn: float):
        """Set this robot's input "speed": scale the primary (user) joystick axes.

        ``forward`` / ``turn`` in [0, 1] (1.0 = full range, scaled independently). Applied
        to whatever currently drives the robot (physical joystick or app widgets), except
        while the master fully overrides it (see :meth:`set_input_scale_bypass`).
        """
        self.input_scale_forward = _clamp(forward, 0.0, 1.0)
        self.input_scale_turn = _clamp(turn, 0.0, 1.0)
        self.core.logger.info(
            f"Input speed set (forward={self.input_scale_forward}, turn={self.input_scale_turn})")

    # ------------------------------------------------------------------------------------------------------------------
    def set_input_scale_bypass(self, bypass: bool):
        """Temporarily ignore the input speed and drive at full range.

        Used when the master joystick takes a robot over completely (Full override), so the
        operator always has full authority regardless of the robot's selected speed.
        """
        self.bypass_input_scale = bool(bypass)

    # ------------------------------------------------------------------------------------------------------------------
    def set_boost(self, joystick: Joystick, scale_balancing: float, scale_velocity: float,
                  scale_turn_balancing: float = 0.0, scale_turn_velocity: float = 0.0):
        """Use ``joystick``'s triggers as "turbo" boosts: R2 → forward, L2 → turn.

        While set, :meth:`_joystick_task` pushes boost factors ``trigger * scale`` (per-mode)
        to the robot, which scales that axis by ``max * (1 + boost)`` — so the forward / turn
        commands can exceed their configured maxima. Does not by itself keep the joystick
        thread alive — it is meant to accompany a primary/assist input (the expo master's
        Assist/Full).
        """
        self.boost_joystick = joystick
        self.boost_scale_balancing = scale_balancing
        self.boost_scale_velocity = scale_velocity
        self.boost_scale_turn_balancing = scale_turn_balancing
        self.boost_scale_turn_velocity = scale_turn_velocity
        self.core.logger.info(
            f"Boost joystick {joystick.id} set (fwd balancing={scale_balancing}, fwd velocity={scale_velocity}, "
            f"turn balancing={scale_turn_balancing}, turn velocity={scale_turn_velocity})")

    # ------------------------------------------------------------------------------------------------------------------
    def clear_boost(self):
        if self.boost_joystick is None:
            return
        self.core.logger.info("Clear boost joystick")
        self.boost_joystick = None
        # Make sure the robot drops back to its normal forward / turn maxima.
        self._send_input_boost(0.0, 0.0)

    # ------------------------------------------------------------------------------------------------------------------
    def _send_input_boost(self, forward: float, turn: float):
        """Push the (forward, turn) turbo boost factors to the robot, only when they change.

        Factors are rounded so analog-trigger jitter doesn't spam the link; the robot
        keeps the last values until the next change, so a final ``0`` on release is
        required (handled here and in :meth:`clear_boost`).
        """
        forward = round(max(0.0, forward), 2)
        turn = round(max(0.0, turn), 2)
        if (forward, turn) == self._last_boost_sent:
            return
        self._last_boost_sent = (forward, turn)
        try:
            self.core.device.executeFunction(function_name='set_input_boost',
                                             arguments={'forward': forward, 'turn': turn})
        except Exception as e:
            self.core.logger.warning(f"Could not send input boost: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def enable_joystick(self):
        self.joystick_enabled = True

    # ------------------------------------------------------------------------------------------------------------------
    def disable_joystick(self):
        self.joystick_enabled = False

    # ------------------------------------------------------------------------------------------------------------------
    def enable_external_input(self):
        """Enable external input on the robot (joystick/wifi commands)"""
        self.core.device.executeFunction(
            function_name='set_external_input_enabled',
            arguments={'enabled': True}
        )

    # ------------------------------------------------------------------------------------------------------------------
    def disable_external_input(self):
        """Disable external input on the robot (joystick/wifi commands)"""
        self.core.device.executeFunction(
            function_name='set_external_input_enabled',
            arguments={'enabled': False}
        )

    # ------------------------------------------------------------------------------------------------------------------
    def set_external_input_enabled(self, enabled: bool):
        """Enable or disable external input on the robot"""
        self.core.device.executeFunction(
            function_name='set_external_input_enabled',
            arguments={'enabled': enabled}
        )

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self):
        if self.joystick is None:
            return

        self.core.logger.info("Remove Joystick")
        speak(f"Joystick {self.joystick.id} removed from {self.core.id}")

        self.joystick.clearAllButtonCallbacks()
        self.joystick = None

        # Stop joystick thread if no input source remains
        if self.app_joystick_widgets is None and self.assist_joystick is None:
            self._stop_joystick_thread()
            self.set_input_source('NONE')

    # ------------------------------------------------------------------------------------------------------------------
    def set_input_source(self, input_source: str):
        if input_source not in ['NONE', 'JOYSTICK', 'WIFI_JOYSTICK']:
            raise ValueError(f"Invalid input source: {input_source}. Must be 'NONE', 'JOYSTICK', or 'WIFI_JOYSTICK'")

        self.core.device.executeFunction(
            function_name='set_input_source',
            arguments={'source': input_source}
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _stop_joystick_thread(self):
        with self._joystick_lock:
            if self._joystick_thread is None or not self._joystick_thread.is_alive():
                return

            self._joystick_stop_event.set()

        # Join outside the lock to avoid deadlock
        self._joystick_thread.join(timeout=2.0)

        with self._joystick_lock:
            self._joystick_thread = None
            self.core.logger.info("Joystick thread stopped.")

    # ------------------------------------------------------------------------------------------------------------------
    def _start_joystick_thread(self):
        with self._joystick_lock:
            # Check if thread is already running
            if self._joystick_thread is not None and self._joystick_thread.is_alive():
                return

            # Clear the stop event before starting
            self._joystick_stop_event.clear()

            self._joystick_thread = threading.Thread(target=self._joystick_task, daemon=True)
            self._joystick_thread.start()
            self.core.logger.info(f"Joystick thread started for {self.core.id}.")

    # ------------------------------------------------------------------------------------------------------------------
    def _joystick_task(self):
        while not self._joystick_stop_event.is_set():
            # Primary input: physical joystick (priority) or app widgets.
            if self.joystick:
                raw_forward = -self.joystick.getAxis('LEFT_VERTICAL')
                raw_turn = -self.joystick.getAxis('RIGHT_HORIZONTAL')
            elif self.app_joystick_widgets:
                raw_forward = self.app_joystick_widgets['forward'].y
                raw_turn = -self.app_joystick_widgets['turn'].x
            elif self.assist_joystick is not None:
                # No primary source, but a master is assisting → primary contributes nothing.
                raw_forward = 0.0
                raw_turn = 0.0
            else:
                # No input source available, exit thread
                self.core.logger.info("Joystick thread exiting: no input source available.")
                return

            # Per-robot "speed": scale the primary (user) input. Skipped while bypassed
            # (master Full override drives at full range); the assist/master input mixed
            # in below is never throttled by the user's speed setting.
            if not self.bypass_input_scale:
                raw_forward *= self.input_scale_forward
                raw_turn *= self.input_scale_turn

            # Mix in the assist (master) joystick, if any. The strategy is selectable
            # (see _mix_assist): 'additive' adds gain*master and saturates; 'authority'
            # gives the master more say the harder it pushes. Either way the result is
            # clamped to [-1, 1] (the Pi maps this normalized range to the configured
            # velocity limits, so clamping = "normalize back to their scale").
            if self.assist_joystick is not None:
                assist_forward = -self.assist_joystick.getAxis('LEFT_VERTICAL')
                assist_turn = -self.assist_joystick.getAxis('RIGHT_HORIZONTAL')
                raw_forward = _mix_assist(raw_forward, assist_forward, self.assist_gain, self.assist_mix_mode)
                raw_turn = _mix_assist(raw_turn, assist_turn, self.assist_gain, self.assist_mix_mode)

            # "Turbo" boosts from the master's triggers (R2 → forward, L2 → turn), only in
            # BALANCING / VELOCITY. The normalized inputs we send are still capped at [-1, 1]
            # (the robot rejects anything outside that), so the boost can't be applied here
            # without clamping it away. Instead we push boost *factors* (trigger * per-mode
            # scale) to the robot, which scales forward.max / turn.max by (1 + boost) — letting
            # the commands actually exceed the normal maxima. Triggers are floored at 0 to
            # ignore the released state (reads negative on some pads).
            boost_forward = 0.0
            boost_turn = 0.0
            if self.boost_joystick is not None and self.control.mode in (
                    BILBO_Control_Mode.BALANCING, BILBO_Control_Mode.VELOCITY):
                is_balancing = self.control.mode == BILBO_Control_Mode.BALANCING
                r2 = max(0.0, self.boost_joystick.getAxis('RIGHT_TRIGGER'))
                l2 = max(0.0, self.boost_joystick.getAxis('LEFT_TRIGGER'))
                boost_forward = r2 * (self.boost_scale_balancing if is_balancing
                                      else self.boost_scale_velocity)
                boost_turn = l2 * (self.boost_scale_turn_balancing if is_balancing
                                   else self.boost_scale_turn_velocity)
            self._send_input_boost(boost_forward, boost_turn)

            if not self.joystick_enabled:
                self._joystick_stop_event.wait(JOYSTICK_UPDATE_TIME)
                continue

            forward_joystick = raw_forward
            turn_joystick = raw_turn

            self.core.device.executeFunction(
                function_name='set_joystick_input',
                arguments={'forward': forward_joystick, 'turn': turn_joystick}
            )
            self._joystick_stop_event.wait(JOYSTICK_UPDATE_TIME)

    # ------------------------------------------------------------------------------------------------------------------


# ======================================================================================================================
class BILBO_CLI_CommandSet(CommandSet):

    def __init__(self, core: BILBO_Core, control: BILBO_Control, position_control: BILBO_PositionControl,
                 experiments: BILBO_ExperimentHandler, utilities: BILBO_Utilities, interfaces: 'BILBO_Interfaces'):
        self.core = core
        self.control = control
        self.position_control = position_control
        self.experiments = experiments
        self.utilities = utilities
        self.interfaces = interfaces

        # Set lazily by TestbedManager when the robot connects
        self.testbed = None

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

        velocity_command = Command(name='vel',
                                   function=self.control.set_velocity_command,
                                   allow_positionals=True,
                                   arguments=[
                                       CommandArgument(name='v',
                                                       type=float),
                                       CommandArgument(name='psi_dot',
                                                       short_name='p',
                                                       type=float, )
                                   ],
                                   )

        stop_command = Command(name='stop',
                               function=Callback(
                                   function=self.control.setControlMode,
                                   inputs={'mode': BILBO_Control_Mode.OFF},
                                   discard_inputs=True,
                               ),
                               description='Deactivates the control on the robot',
                               arguments=[])

        nudge_command = Command(
            name='nudge',
            function=self.control.nudge,
            description='One-shot position nudge to free the robot from a wall. OFF mode only, robot must be lying over. Distance in meters; direction auto-picked from theta.',
            allow_positionals=True,
            execute_in_thread=True,
            arguments=[
                CommandArgument(name='distance', short_name='d', type=float, optional=True, default=0.2,
                                description='Travel distance in meters (magnitude; direction away from the fall)'),
            ])

        stable_command = Command(name='stable',
                                 description='Checks if the robot is stable',
                                 function=self._check_stable,
                                 )

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

        reset_drive_command = Command(
            name='resetDrive',
            function=self.core.reset_drive,
            description='Reset motor drive after error state',
            arguments=[])

        external_input_command = Command(
            name='extInput',
            function=self._set_external_input,
            allow_positionals=True,
            description='Enable or disable external input (joystick/wifi) on the robot',
            arguments=[
                CommandArgument(name='enabled',
                                short_name='e',
                                type=int,
                                description='1 to enable, 0 to disable external input')
            ])

        # --- CONTROL ----

        set_control_mode_command = Command(name='mode',
                                           function=self.control.setControlMode,
                                           allow_positionals=True,
                                           arguments=[
                                               CommandArgument(name='mode', type=int, short_name='m'),
                                           ], )

        get_velocity_config_command = Command(name='getVelConfig',
                                              function=self._read_velocity_config,
                                              description='Reads the velocity configuration from the robot',
                                              arguments=[])

        set_velocity_turn_pid_command = Command(name='setVelTurnPID',
                                                function=self.control.set_turn_pid,
                                                arguments=[
                                                    CommandArgument(name='P', type=float, optional=True, default=None),
                                                    CommandArgument(name='I', type=float, optional=True, default=None),
                                                    CommandArgument(name='D', type=float, optional=True, default=None),
                                                ],
                                                allow_positionals=False)

        set_velocity_forward_pid_command = Command(name='setVelForwardPID',
                                                   function=self.control.set_forward_pid,
                                                   arguments=[
                                                       CommandArgument(name='P', type=float, optional=True,
                                                                       default=None),
                                                       CommandArgument(name='I', type=float, optional=True,
                                                                       default=None),
                                                       CommandArgument(name='D', type=float, optional=True,
                                                                       default=None),
                                                   ],
                                                   allow_positionals=False
                                                   )

        # get_position_control_config_command = Command(
        #     name='getPosConfig',
        #     function=self._read_position_control_config,
        #     description='Reads the position control configuration from the robot',
        #     arguments=[]
        # )
        #
        # set_position_control_forward_pi_command = Command(
        #     name='setPosForwardPI',
        #     function=self.control.set_position_forward_pi,
        #     arguments=[
        #         CommandArgument(name='P', type=float, optional=True, default=None),
        #         CommandArgument(name='I', type=float, optional=True, default=None),
        #     ],
        #     allow_positionals=False
        # )
        # set_position_control_turn_pi_command = Command(
        #     name='setPosTurnPI',
        #     function=self.control.set_position_turn_pi,
        #     arguments=[
        #         CommandArgument(name='P', type=float, optional=True, default=None),
        #         CommandArgument(name='I', type=float, optional=True, default=None),
        #     ],
        #     allow_positionals=False
        # )

        control_command_set = CommandSet(name='control', commands=[
            set_control_mode_command,
            get_velocity_config_command,
            set_velocity_turn_pid_command,
            set_velocity_forward_pid_command,
            # get_position_control_config_command,
            # set_position_control_forward_pi_command,
            # set_position_control_turn_pi_command,
        ])

        # --- EXPERIMENT SET ---
        test_trajectory_command = Command(name='random_traj',
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

        test_experiment_command = Command(
            name='exp',
            function=self._run_experiment,
            description='Run experiment from file. Opens native file picker if no file specified.',
            allow_positionals=True,
            execute_in_thread=True,
            arguments=[
                CommandArgument(name='file',
                                short_name='f',
                                type=str,
                                description='Path to experiment file (YAML/JSON). Opens native picker if not specified.',
                                optional=True,
                                default=None),
                CommandArgument(name='output',
                                short_name='o',
                                type=str,
                                description='Output directory for experiment data. Defaults to file\'s directory.',
                                optional=True,
                                default=None)
            ])

        dilc_command = Command(
            name='dilc',
            function=self._run_dilc,
            description='Run a DILC experiment from a YAML config file. Opens native file picker if no file specified.',
            allow_positionals=True,
            execute_in_thread=True,
            arguments=[
                CommandArgument(name='file',
                                short_name='f',
                                type=str,
                                description='Path to DILC experiment YAML file. Opens native picker if not specified.',
                                optional=True,
                                default=None),
            ])

        snr_dilc_command = Command(
            name='snr_dilc',
            function=self._run_snr_dilc,
            description='Run an SNR-adaptive DILC experiment from a YAML config file. Opens native file picker if no file specified.',
            allow_positionals=True,
            execute_in_thread=True,
            arguments=[
                CommandArgument(name='file',
                                short_name='f',
                                type=str,
                                description='Path to SNR DILC experiment YAML file. Opens native picker if not specified.',
                                optional=True,
                                default=None),
            ])

        cooperative_dilc_command = Command(
            name='cooperative_dilc',
            function=self._run_cooperative_dilc,
            description='Run a cooperative (multi-agent, single-robot) DILC experiment from a YAML config file. Opens native file picker if no file specified.',
            allow_positionals=True,
            execute_in_thread=True,
            arguments=[
                CommandArgument(name='file',
                                short_name='f',
                                type=str,
                                description='Path to cooperative DILC experiment YAML file. Opens native picker if not specified.',
                                optional=True,
                                default=None),
            ])

        limbobar_dilc_command = Command(
            name='limbobar_dilc',
            function=self._run_limbobar_dilc,
            description='Run a LimboBar DILC experiment from a YAML config file. Opens native file picker if no file specified.',
            allow_positionals=True,
            execute_in_thread=True,
            arguments=[
                CommandArgument(name='file',
                                short_name='f',
                                type=str,
                                description='Path to LimboBar DILC experiment YAML file. Opens native picker if not specified.',
                                optional=True,
                                default=None),
            ])

        iitl_command = Command(
            name='iitl',
            function=self._run_iitl,
            description='Run an IITL experiment from a YAML config file. Opens native file picker if no file specified.',
            allow_positionals=True,
            execute_in_thread=True,
            arguments=[
                CommandArgument(name='file',
                                short_name='f',
                                type=str,
                                description='Path to IITL experiment YAML file. Opens native picker if not specified.',
                                optional=True,
                                default=None),
            ])

        iml_command = Command(
            name='iml',
            function=self._run_iml,
            description='Run an IML (model identification) experiment from a YAML config file. Opens native file picker if no file specified.',
            allow_positionals=True,
            execute_in_thread=True,
            arguments=[
                CommandArgument(name='file',
                                short_name='f',
                                type=str,
                                description='Path to IML experiment YAML file. Opens native picker if not specified.',
                                optional=True,
                                default=None),
            ])

        plot_last_experiment_command = Command(name='plot',
                                               function=self.experiments.plot_last_experiment)

        stop_experiment_command = Command(
            name='stop',
            function=self.experiments.stop_experiment,
            description='Stop the currently running experiment on the robot',
            arguments=[
                CommandArgument(name='reason',
                               short_name='r',
                               type=str,
                               optional=True,
                               default='CLI stop request',
                               description='Reason for stopping the experiment')
            ])

        experiment_command_set = CommandSet(name='experiment',
                                            commands=[test_trajectory_command,
                                                      plot_last_experiment_command,
                                                      dilc_command,
                                                      snr_dilc_command,
                                                      cooperative_dilc_command,
                                                      limbobar_dilc_command,
                                                      iitl_command,
                                                      iml_command,
                                                      test_experiment_command,
                                                      stop_experiment_command])

        navigation_command_set = CommandSet(name='nav')

        # Position mode command
        position_mode_command = Command(
            name='mode',
            function=Callback(
                function=self.control.setControlMode,
                inputs={'mode': BILBO_Control_Mode.POSITION},
            ),
            description='Switch to position control mode',
            arguments=[]
        )

        # Simple movement commands
        move_to_command = Command(
            name='moveTo',
            function=self.position_control.move_to,
            description='Move to a single point',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='x', type=float, description='X coordinate [m]'),
                CommandArgument(name='y', type=float, description='Y coordinate [m]'),
                CommandArgument(name='max_speed', short_name='s', type=float, optional=True, default=0.0,
                                description='Max speed [m/s] (0=default)'),
                CommandArgument(name='timeout', short_name='t', type=float, optional=True, default=0.0,
                                description='Timeout [s] (0=none)'),
            ]
        )

        turn_to_command = Command(
            name='turnTo',
            function=self.position_control.turn_to,
            description='Turn to a heading',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='heading', short_name='h', type=float, description='Heading [rad]'),
                CommandArgument(name='max_angular_speed', short_name='s', type=float, optional=True, default=0.0,
                                description='Max angular speed [rad/s] (0=default)'),
                CommandArgument(name='timeout', short_name='t', type=float, optional=True, default=0.0,
                                description='Timeout [s] (0=none)'),
            ]
        )

        move_to_pose_command = Command(
            name='moveToPose',
            function=self.position_control.move_to_pose,
            description='Move to a pose (position + heading). Drives to the point, then turns to the heading.',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='x', type=float, description='X coordinate [m]'),
                CommandArgument(name='y', type=float, description='Y coordinate [m]'),
                CommandArgument(name='heading', short_name='h', type=float, description='Heading [rad]'),
                CommandArgument(name='max_speed', short_name='s', type=float, optional=True, default=0.0,
                                description='Max speed [m/s] (0=default)'),
                CommandArgument(name='max_angular_speed', short_name='a', type=float, optional=True, default=3.0,
                                description='Max angular speed [rad/s]'),
                CommandArgument(name='timeout', short_name='t', type=float, optional=True, default=0.0,
                                description='Timeout [s] (0=none)'),
            ]
        )

        go_to_pose_command = Command(
            name='goToPose',
            function=self._go_to_pose,
            description='Move to a named pose from the testbed definition',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='pose_id', type=str, description='Pose ID from testbed'),
                CommandArgument(name='max_speed', short_name='s', type=float, optional=True, default=0.0,
                                description='Max speed [m/s] (0=default)'),
                CommandArgument(name='max_angular_speed', short_name='a', type=float, optional=True, default=3.0,
                                description='Max angular speed [rad/s]'),
                CommandArgument(name='timeout', short_name='t', type=float, optional=True, default=0.0,
                                description='Timeout [s] (0=none)'),
            ]
        )

        # Path management commands
        clear_path_command = Command(
            name='clearPath',
            function=self.position_control.clear_path,
            description='Clear all path points',
            arguments=[]
        )

        # Path control commands
        start_path_command = Command(
            name='start',
            function=self.position_control.start_path,
            description='Start following loaded path',
            arguments=[
                CommandArgument(name='allow_reverse', short_name='r', type=bool, optional=True, default=False,
                                description='Allow reverse driving'),
                CommandArgument(name='timeout', short_name='t', type=float, optional=True, default=0.0,
                                description='Timeout [s] (0=none)'),
                CommandArgument(name='max_speed', short_name='s', type=float, optional=True, default=0.0,
                                description='Max speed [m/s] (0=default)'),
            ]
        )

        abort_path_command = Command(
            name='abort',
            function=self.position_control.abort_path,
            description='Abort path execution',
            arguments=[]
        )

        # State commands
        get_state_command = Command(
            name='state',
            function=self._print_position_control_state,
            description='Show position control state',
            arguments=[]
        )

        reset_command = Command(
            name='reset',
            function=self.position_control.reset,
            description='Reset position control',
            arguments=[]
        )

        # Plan and follow command
        go_to_command = Command(
            name='goTo',
            function=self._plan_and_follow,
            description='Plan path to target and follow it. Use --wp for waypoints: "x,y; x,y,weight; x,y,weight,STOP"',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='x', type=float, description='Target X coordinate [m]'),
                CommandArgument(name='y', type=float, description='Target Y coordinate [m]'),
                CommandArgument(name='wp', short_name='w', type=str, optional=True, default='',
                                description='Waypoints: "x,y; x,y,weight; x,y,weight,STOP" (semicolon-separated)'),
                CommandArgument(name='max_speed', short_name='s', type=float, optional=True, default=0.0,
                                description='Max speed [m/s] (0=default)'),
                CommandArgument(name='timeout', short_name='t', type=float, optional=True, default=0.0,
                                description='Timeout [s] (0=none)'),
                CommandArgument(name='allow_reverse', short_name='r', type=bool, optional=True, default=False,
                                description='Allow reverse driving'),
            ]
        )

        # Plan path (preview only) command
        plan_path_command = Command(
            name='planPath',
            function=self._plan_path,
            description='Plan path to target (preview only, does not drive). Use --wp for waypoints: "x,y; x,y,weight; x,y,weight,STOP"',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='x', type=float, description='Target X coordinate [m]'),
                CommandArgument(name='y', type=float, description='Target Y coordinate [m]'),
                CommandArgument(name='wp', short_name='w', type=str, optional=True, default='',
                                description='Waypoints: "x,y; x,y,weight; x,y,weight,STOP" (semicolon-separated)'),
            ]
        )

        # Build PRM roadmap command
        build_prm_command = Command(
            name='buildPRM',
            function=self._build_prm,
            description='Build PRM roadmap from current testbed obstacles (required before PRM planning)',
            arguments=[]
        )

        # Add all commands to navigation set
        navigation_command_set.addCommand(position_mode_command)
        navigation_command_set.addCommand(move_to_command)
        navigation_command_set.addCommand(turn_to_command)
        navigation_command_set.addCommand(move_to_pose_command)
        navigation_command_set.addCommand(go_to_pose_command)
        navigation_command_set.addCommand(go_to_command)
        navigation_command_set.addCommand(plan_path_command)
        navigation_command_set.addCommand(build_prm_command)
        navigation_command_set.addCommand(clear_path_command)
        navigation_command_set.addCommand(start_path_command)
        navigation_command_set.addCommand(abort_path_command)
        navigation_command_set.addCommand(get_state_command)
        navigation_command_set.addCommand(reset_command)

        super().__init__(name=f"{self.core.id}", commands=[beep_command,
                                                           speak_command,
                                                           mode_command,
                                                           velocity_command,
                                                           stop_command,
                                                           stable_command,
                                                           test_communication,
                                                           external_input_command,
                                                           reset_drive_command,
                                                           nudge_command],

                         children=[control_command_set, experiment_command_set, navigation_command_set])

    def _check_stable(self):
        self.core.logger.warning("Stable check is currently not implemented")
        # stable = self.core.is_upright_and_static()
        # if stable:
        #     self.core.logger.info("Robot is stable.")
        # else:
        #     self.core.logger.warning("Robot is not stable.")

    # ------------------------------------------------------------------------------------------------------------------
    def _read_velocity_config(self):
        cfg = self.control.get_velocity_control_config()

        def log_velocity_channel(name: str, vc):
            pid = vc.pid
            ff = vc.feedforward

            self.core.logger.info(f"  {name} controller:")

            # --- PID ---
            self.core.logger.info("    PID:")
            self.core.logger.info(
                f"      Kp={pid.Kp}, Ki={pid.Ki}, Kd={pid.Kd}"
            )
            self.core.logger.info(
                f"      limits: "
                f"i={pid.enable_i_limit}({pid.i_term_limit}), "
                f"input={pid.enable_input_limit}({pid.input_limit}), "
                f"output={pid.enable_output_limit}({pid.output_limit})"
            )
            self.core.logger.info(
                f"      filters: "
                f"d_filter={pid.enable_d_filter}(Td={pid.Td_filter}), "
                f"rate_limit={pid.enable_rate_limit}({pid.rate_limit}), "
                f"sp_rate_limit={pid.enable_setpoint_rate_limit}({pid.setpoint_rate_limit})"
            )

            # --- Feedforward ---
            self.core.logger.info("    Feedforward:")
            self.core.logger.info(
                f"      gains: Kv={ff.Kv}, Ka={ff.Ka}, Kc={ff.Kc}"
            )
            self.core.logger.info(
                f"      vref slew: "
                f"enabled={ff.enable_vref_slew}({ff.vref_slew_rate})"
            )
            self.core.logger.info(
                f"      accel filter: "
                f"enabled={ff.enable_a_filter}(Ta={ff.Ta_filter})"
            )
            self.core.logger.info(
                f"      stiction: "
                f"enabled={ff.enable_stiction}(v0={ff.v0_stiction})"
            )
            self.core.logger.info(
                f"      output limits: "
                f"limit={ff.enable_output_limit}({ff.output_limit}), "
                f"slew={ff.enable_output_slew}({ff.output_slew_rate})"
            )

        self.core.logger.info("Velocity Control Configuration:")

        log_velocity_channel("Linear velocity (v)", cfg.v)
        log_velocity_channel("Angular velocity (psidot)", cfg.psidot)

    # ------------------------------------------------------------------------------------------------------------------
    def _print_position_control_state(self):
        """Print current position control state"""
        state = self.position_control.get_state()
        if state is None:
            self.core.logger.error("Failed to get position control state")
            return

        self.core.logger.info("Position Control State:")
        self.core.logger.info(f"  Mode: {state.get('mode_name', 'UNKNOWN')} ({state.get('mode', -1)})")
        self.core.logger.info(f"  Path State: {state.get('path_state', 0)}")
        self.core.logger.info(f"  Path Points: {state.get('path_point_count', 0)}")
        self.core.logger.info(f"  Current Index: {state.get('current_index', 0)}")
        self.core.logger.info(f"  Is Busy: {state.get('is_busy', False)}")

        # Print data if available
        data = state.get('data', {})
        if data:
            self.core.logger.info("  Telemetry:")
            self.core.logger.info(f"    Carrot: ({data.get('carrot_x', 0):.3f}, {data.get('carrot_y', 0):.3f})")
            self.core.logger.info(f"    Heading error: {data.get('heading_error', 0):.3f} rad")
            self.core.logger.info(f"    Speed limit: {data.get('speed_limit', 0):.3f} m/s")
            self.core.logger.info(f"    Progress: {data.get('progress', 0):.1f}")
            self.core.logger.info(f"    Elapsed time: {data.get('elapsed_time', 0):.2f} s")

    # ------------------------------------------------------------------------------------------------------------------
    def _set_external_input(self, enabled: int):
        """Set external input enabled state (helper for CLI int->bool conversion)"""
        self.interfaces.set_external_input_enabled(bool(enabled))

    # ------------------------------------------------------------------------------------------------------------------
    def _plan_and_follow(self, x: float, y: float, wp: str = '',
                         max_speed: float = 0.0,
                         timeout: float = 0.0,
                         allow_reverse: bool = False):
        """Plan path to target and follow it"""
        waypoints = self._parse_waypoints_string(wp) if wp else None
        result = self.position_control.plan_and_follow(
            target=(x, y),
            waypoints=waypoints,
            max_speed=max_speed,
            timeout=timeout,
            allow_reverse=allow_reverse,
        )
        if result:
            wp_str = f" with {len(waypoints)} waypoints" if waypoints else ""
            self.core.logger.info(f"Planning and following path to ({x:.2f}, {y:.2f}){wp_str}")
        else:
            self.core.logger.error(f"Failed to plan and follow path to ({x:.2f}, {y:.2f})")

    # ------------------------------------------------------------------------------------------------------------------
    def _plan_path(self, x: float, y: float, wp: str = ''):
        """Plan path to target (preview only, does not drive)"""
        waypoints = self._parse_waypoints_string(wp) if wp else None
        result = self.position_control.plan_path(target=(x, y), waypoints=waypoints)
        if result:
            wp_str = f" with {len(waypoints)} waypoints" if waypoints else ""
            self.core.logger.info(f"Planned path to ({x:.2f}, {y:.2f}){wp_str}")
        else:
            self.core.logger.error(f"Failed to plan path to ({x:.2f}, {y:.2f})")

    # ------------------------------------------------------------------------------------------------------------------
    def _go_to_pose(self, pose_id: str, max_speed: float = 0.0,
                    max_angular_speed: float = 0.0, timeout: float = 0.0):
        """Look up a named pose from the testbed and move to it"""
        if self.testbed is None:
            self.core.logger.error("No testbed available")
            return

        pose = self.testbed.poses.get(pose_id)
        if pose is None:
            available = ', '.join(self.testbed.poses.keys()) if self.testbed.poses else '(none)'
            self.core.logger.error(f"Pose '{pose_id}' not found. Available: {available}")
            return

        self.core.logger.info(
            f"Going to pose '{pose_id}' ({pose.x:.2f}, {pose.y:.2f}, psi={pose.psi:.2f} rad)"
        )
        self.position_control.move_to_pose(
            x=pose.x, y=pose.y, heading=pose.psi,
            max_speed=max_speed, max_angular_speed=max_angular_speed,
            timeout=timeout,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _build_prm(self):
        """Build PRM roadmap from current testbed obstacles"""
        self.position_control.build_prm()

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _parse_waypoints_string(wp_str: str) -> list[dict] | None:
        """Parse waypoint string into list of dicts.
        Format: "x,y; x,y,weight; x,y,weight,STOP" (semicolon-separated)
        Each entry: x,y[,weight[,type]]  where type is PASS or STOP (default PASS)
        """
        if not wp_str or not wp_str.strip():
            return None
        waypoints = []
        for entry in wp_str.split(';'):
            entry = entry.strip()
            if not entry:
                continue
            parts = [p.strip() for p in entry.split(',')]
            if len(parts) < 2:
                continue
            wp = {'x': float(parts[0]), 'y': float(parts[1])}
            if len(parts) >= 3:
                # Check if third part is a type string or a weight
                third = parts[2].strip().upper()
                if third in ('PASS', 'STOP'):
                    wp['type'] = third
                else:
                    wp['weight'] = float(parts[2])
            if len(parts) >= 4:
                wp['type'] = parts[3].strip().upper()
            waypoints.append(wp)
        return waypoints if waypoints else None

    # ------------------------------------------------------------------------------------------------------------------
    def _run_dilc(self, file: str | None = None):
        """CLI handler for DILC command. Opens file picker if no file given."""
        if not file:
            self.core.logger.info("No file specified, opening native file picker...")
            try:
                from core.utils.filepicker import pick_file
                file = pick_file(
                    title='Select DILC Experiment File',
                    allowed_extensions=['yaml', 'yml']
                )
            except Exception as e:
                self.core.logger.error(f"File picker failed: {e}. Use -f <path> to specify a file.")
                return
            if not file:
                self.core.logger.info("File selection cancelled.")
                return
        self.experiments.run_dilc_from_file(file)

    # ------------------------------------------------------------------------------------------------------------------
    def _run_snr_dilc(self, file: str | None = None):
        """CLI handler for SNR DILC command. Opens file picker if no file given."""
        if not file:
            self.core.logger.info("No file specified, opening native file picker...")
            try:
                from core.utils.filepicker import pick_file
                file = pick_file(
                    title='Select SNR DILC Experiment File',
                    allowed_extensions=['yaml', 'yml']
                )
            except Exception as e:
                self.core.logger.error(f"File picker failed: {e}. Use -f <path> to specify a file.")
                return
            if not file:
                self.core.logger.info("File selection cancelled.")
                return
        self.experiments.run_snr_dilc_from_file(file)

    # ------------------------------------------------------------------------------------------------------------------
    def _run_cooperative_dilc(self, file: str | None = None):
        """CLI handler for cooperative DILC command. Opens file picker if no file given."""
        if not file:
            self.core.logger.info("No file specified, opening native file picker...")
            try:
                from core.utils.filepicker import pick_file
                file = pick_file(
                    title='Select Cooperative DILC Experiment File',
                    allowed_extensions=['yaml', 'yml']
                )
            except Exception as e:
                self.core.logger.error(f"File picker failed: {e}. Use -f <path> to specify a file.")
                return
            if not file:
                self.core.logger.info("File selection cancelled.")
                return
        self.experiments.run_cooperative_dilc_from_file(file)

    # ------------------------------------------------------------------------------------------------------------------
    def _run_limbobar_dilc(self, file: str | None = None):
        """CLI handler for LimboBar DILC command. Opens file picker if no file given."""
        if not file:
            self.core.logger.info("No file specified, opening native file picker...")
            try:
                from core.utils.filepicker import pick_file
                file = pick_file(
                    title='Select LimboBar DILC Experiment File',
                    allowed_extensions=['yaml', 'yml']
                )
            except Exception as e:
                self.core.logger.error(f"File picker failed: {e}. Use -f <path> to specify a file.")
                return
            if not file:
                self.core.logger.info("File selection cancelled.")
                return
        self.experiments.run_limbobar_dilc_from_file(file)

    # ------------------------------------------------------------------------------------------------------------------
    def _run_iitl(self, file: str | None = None):
        """CLI handler for IITL command. Opens file picker if no file given."""
        if not file:
            self.core.logger.info("No file specified, opening native file picker...")
            try:
                from core.utils.filepicker import pick_file
                file = pick_file(
                    title='Select IITL Experiment File',
                    allowed_extensions=['yaml', 'yml']
                )
            except Exception as e:
                self.core.logger.error(f"File picker failed: {e}. Use -f <path> to specify a file.")
                return
            if not file:
                self.core.logger.info("File selection cancelled.")
                return
        self.experiments.run_iitl_from_file(file)

    # ------------------------------------------------------------------------------------------------------------------
    def _run_iml(self, file: str | None = None):
        """CLI handler for IML command. Opens file picker if no file given."""
        if not file:
            self.core.logger.info("No file specified, opening native file picker...")
            try:
                from core.utils.filepicker import pick_file
                file = pick_file(
                    title='Select IML Experiment File',
                    allowed_extensions=['yaml', 'yml']
                )
            except Exception as e:
                self.core.logger.error(f"File picker failed: {e}. Use -f <path> to specify a file.")
                return
            if not file:
                self.core.logger.info("File selection cancelled.")
                return
        self.experiments.run_iml_from_file(file)

    # ------------------------------------------------------------------------------------------------------------------
    def _run_experiment(self, file: str | None = None, output: str | None = None):
        """CLI handler for experiment command. Opens file picker if no file given."""
        if not file:
            self.core.logger.info("No file specified, opening native file picker...")
            try:
                from core.utils.filepicker import pick_file
                file = pick_file(
                    title='Select Experiment File',
                    allowed_extensions=['yaml', 'yml', 'json']
                )
            except Exception as e:
                self.core.logger.error(f"File picker failed: {e}. Use -f <path> to specify a file.")
                return
            if not file:
                self.core.logger.info("File selection cancelled.")
                return
        self.experiments.run_experiment_from_file(file, output=output)


