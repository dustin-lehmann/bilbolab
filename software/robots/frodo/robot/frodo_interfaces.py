import threading
import time

import numpy as np

from extensions.tools.cli.cli import CommandSet, CommandArgument, Command
from extensions.hardware.joystick.joystick_manager import Joystick
from robots.frodo.robot.frodo import FRODO_Control
from robots.frodo.robot.frodo_core import FRODO_Core
from robots.frodo.robot.frodo_definitions import FRODO_ControlMode


class FRODO_Interfaces:
    core: FRODO_Core
    control: FRODO_Control
    joystick: Joystick | None = None
    cli_command_set: CommandSet

    _exit_joystick_task: bool = False
    _joystick_thread: threading.Thread | None = None




    # === INIT =========================================================================================================
    def __init__(self, core: FRODO_Core,
                 control: FRODO_Control, ):
        self.core = core
        self.control = control

        self.cli_command_set = FRODO_CLI_CommandSet(core=self.core,
                                                    control=self.control)

        self._joystick_thread = None

    # === METHODS ======================================================================================================
    def assignJoystick(self, joystick: Joystick):
        self.joystick = joystick
        self._joystick_thread = threading.Thread(target=self._joystick_task, daemon=True)
        self._exit_joystick_task = False
        self._joystick_thread.start()
        self.joystick.callbacks.B.register(self.core.beep)
        self.core.logger.info("Joystick assigned")

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self):
        self.joystick.callbacks.B.remove(self.core.beep)
        self.joystick = None
        self._exit_joystick_task = True
        if self._joystick_thread is not None and self._joystick_thread.is_alive():
            self._joystick_thread.join()

        self.core.logger.info("Joystick removed")

    # === PRIVATE METHODS ==============================================================================================
    def _joystick_task(self):
        while not self._exit_joystick_task:
            if self.joystick is None:
                time.sleep(0.1)
                continue

            # === Read controller inputs ===
            forward = -self.joystick.getAxis("LEFT_VERTICAL")  # Forward/backward
            turn = self.joystick.getAxis("RIGHT_HORIZONTAL")  # Turning

            # === Exponential response mapping (for finer low-speed control) ===
            def map_input(x, factor=10.0):
                sign = np.sign(x)
                x = abs(x)
                return sign * (np.exp(x * np.log(factor)) - 1) / (factor - 1)

            turn = map_input(turn)

            # === Normalize so combined magnitude doesn’t exceed 1 ===
            sum_axis = abs(forward) + abs(turn)
            if sum_axis > 1:
                forward /= sum_axis
                turn /= sum_axis

            # === Mix forward + turn into left/right speeds ===
            speed_left = forward + turn
            speed_right = forward - turn

            # === Apply to control system ===
            self.control.setSpeedNormalized(
                speed_left_normalized=speed_left,
                speed_right_normalized=speed_right
            )

            time.sleep(0.1)


class FRODO_CLI_CommandSet(CommandSet):
    def __init__(self, core: FRODO_Core, control: FRODO_Control):
        self.core = core
        self.control = control

        # --- BEEP ---
        beep_command = Command(
            name='beep',
            function=self.core.beep,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='frequency', type=int, short_name='f',
                                description='Frequency of the beep', is_flag=False, optional=True, default=700),
                CommandArgument(name='time_ms', type=int, short_name='t',
                                description='Time of the beep in milliseconds', is_flag=False, optional=True,
                                default=250),
                CommandArgument(name='repeats', type=int, short_name='r',
                                description='Number of repeats', is_flag=False, optional=True, default=1),
            ],
            description='Beeps the Buzzer'
        )

        # --- Control ---
        control_set = CommandSet(name='control')

        # speed in m/s (EXTERNAL mode)
        speed_cmd = Command(
            name='speed',
            function=self.control.setSpeed,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='left', type=float, short_name='l',
                                description='Left track speed [m/s]', is_flag=False, optional=False, default=None),
                CommandArgument(name='right', type=float, short_name='r',
                                description='Right track speed [m/s]', is_flag=False, optional=False, default=None),
            ],
            description='Set left/right track speeds in m/s (requires EXTERNAL mode).'
        )
        control_set.addCommand(speed_cmd)

        # normalized speed [-1..1] (EXTERNAL mode)
        speedn_cmd = Command(
            name='speedn',
            function=self.control.setSpeedNormalized,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='left', type=float, short_name='l',
                                description='Left track speed normalized [-1..1]', is_flag=False, optional=False,
                                default=None),
                CommandArgument(name='right', type=float, short_name='r',
                                description='Right track speed normalized [-1..1]', is_flag=False, optional=False,
                                default=None),
            ],
            description='Set left/right track speeds normalized to [-1..1] (requires EXTERNAL mode).'
        )
        control_set.addCommand(speedn_cmd)

        # mode switch (EXTERNAL / NAVIGATION)
        setmode_cmd = Command(
            name='mode',
            function=lambda mode: self.control.setMode(FRODO_ControlMode[mode]),
            allow_positionals=True,
            arguments=[
                CommandArgument(name='mode', type=str, short_name='m',
                                description='Target mode: EXTERNAL or NAVIGATION',
                                is_flag=False, optional=False, default=None),
            ],
            description='Switch control mode.'
        )
        control_set.addCommand(setmode_cmd)

        # navigation controls
        nav_start_cmd = Command(
            name='start',
            function=self.control.startNavigation,
            arguments=[],
            description='Start the navigator (process queued elements).'
        )
        control_set.addCommand(nav_start_cmd)

        nav_stop_cmd = Command(
            name='stop',
            function=self.control.stopNavigation,
            arguments=[],
            description='Stop the navigator and command zero speed.'
        )
        control_set.addCommand(nav_stop_cmd)

        nav_pause_cmd = Command(
            name='pause',
            function=self.control.pauseNavigation,
            arguments=[],
            description='Pause the navigator (robot will hold with zero speed).'
        )
        control_set.addCommand(nav_pause_cmd)

        nav_resume_cmd = Command(
            name='resume',
            function=self.control.resumeNavigation,
            arguments=[],
            description='Resume the navigator if paused.'
        )
        control_set.addCommand(nav_resume_cmd)

        nav_clear_cmd = Command(
            name='clear',
            function=self.control.clearNavigation,
            arguments=[],
            description='Stop navigation and clear queued elements.'
        )
        control_set.addCommand(nav_clear_cmd)

        # motion primitive: MoveTo (auto-start if not running)
        move_to_command = Command(
            name='move',
            function=self.control.moveTo,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='x', type=float, short_name='x',
                                description='X-Coordinate [m]', is_flag=False, optional=False, default=None),
                CommandArgument(name='y', type=float, short_name='y',
                                description='Y-Coordinate [m]', is_flag=False, optional=False, default=None),
            ],
            description='Queue a MoveTo(x, y) and start nav if not running.'
        )
        control_set.addCommand(move_to_command)

        # ---------------- Queue-only add* commands (do NOT start navigator) ----------------
        add_move_cmd = Command(
            name='add-move',
            function=self.control.addMoveTo,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='x', type=float, short_name='x',
                                description='Target X [m]', is_flag=False, optional=False, default=None),
                CommandArgument(name='y', type=float, short_name='y',
                                description='Target Y [m]', is_flag=False, optional=False, default=None),
            ],
            description='Enqueue MoveTo(x, y) without starting navigation.'
        )
        control_set.addCommand(add_move_cmd)

        add_move_rel_cmd = Command(
            name='add-moverel',
            function=self.control.addMoveToRelative,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='dx', type=float, short_name='x',
                                description='Relative X [m]', is_flag=False, optional=False, default=None),
                CommandArgument(name='dy', type=float, short_name='y',
                                description='Relative Y [m]', is_flag=False, optional=False, default=None),
            ],
            description='Enqueue MoveToRelative(dx, dy) without starting navigation.'
        )
        control_set.addCommand(add_move_rel_cmd)

        add_straight_cmd = Command(
            name='add-straight',
            function=self.control.addRelativeStraightMove,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='distance', type=float, short_name='d',
                                description='Distance along current heading [m]',
                                is_flag=False, optional=False, default=None),
            ],
            description='Enqueue RelativeStraightMove(distance) without starting navigation.'
        )
        control_set.addCommand(add_straight_cmd)

        add_turn_cmd = Command(
            name='add-turn',
            function=self.control.addTurnTo,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='psi', type=float, short_name='p',
                                description='Absolute heading [rad]', is_flag=False, optional=False, default=None),
            ],
            description='Enqueue TurnTo(psi) without starting navigation.'
        )
        control_set.addCommand(add_turn_cmd)

        add_turnrel_cmd = Command(
            name='add-turnrel',
            function=self.control.addRelativeTurn,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='dpsi', type=float, short_name='p',
                                description='Relative heading change [rad]',
                                is_flag=False, optional=False, default=None),
            ],
            description='Enqueue RelativeTurn(dpsi) without starting navigation.'
        )
        control_set.addCommand(add_turnrel_cmd)

        add_turnpt_cmd = Command(
            name='add-turnpoint',
            function=self.control.addTurnToPoint,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='x', type=float, short_name='x',
                                description='Point X [m]', is_flag=False, optional=False, default=None),
                CommandArgument(name='y', type=float, short_name='y',
                                description='Point Y [m]', is_flag=False, optional=False, default=None),
            ],
            description='Enqueue TurnToPoint(x, y) without starting navigation.'
        )
        control_set.addCommand(add_turnpt_cmd)

        add_wait_cmd = Command(
            name='add-wait',
            function=self.control.addTimeWait,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='duration', type=float, short_name='d',
                                description='Duration [s]', is_flag=False, optional=False, default=None),
                CommandArgument(name='reference', type=str, short_name='r',
                                description='Time reference ("PRIMITIVE" or "EXPERIMENT")',
                                is_flag=False, optional=True, default="PRIMITIVE"),
            ],
            description='Enqueue TimeWait without starting navigation.'
        )
        control_set.addCommand(add_wait_cmd)

        add_waitabs_cmd = Command(
            name='add-waitabs',
            function=self.control.addAbsoluteTimeWait,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='unix_time', type=float, short_name='t',
                                description='Unix timestamp [s]', is_flag=False, optional=False, default=None),
            ],
            description='Enqueue AbsoluteTimeWait(unix_time) without starting navigation.'
        )
        control_set.addCommand(add_waitabs_cmd)

        add_waitevt_cmd = Command(
            name='add-waitevent',
            function=self.control.addEventWait,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='event', type=str, short_name='e',
                                description='Event name', is_flag=False, optional=False, default=None),
            ],
            description='Enqueue EventWait(event) without starting navigation.'
        )
        control_set.addCommand(add_waitevt_cmd)

        add_coord_cmd = Command(
            name='add-coordmove',
            function=self.control.addCoordinatedMoveTo,
            allow_positionals=True,
            arguments=[
                CommandArgument(name='x', type=float, short_name='x',
                                description='Target X [m]', is_flag=False, optional=False, default=None),
                CommandArgument(name='y', type=float, short_name='y',
                                description='Target Y [m]', is_flag=False, optional=False, default=None),
                CommandArgument(name='psi_end', type=float, short_name='p',
                                description='Final heading [rad]; omit for none',
                                is_flag=False, optional=True, default=None),
            ],
            description='Enqueue CoordinatedMoveTo(x, y, psi_end?) without starting navigation.'
        )
        control_set.addCommand(add_coord_cmd)

        super().__init__(
            name=f"{self.core.id}",
            commands=[beep_command],
            children=[control_set]
        )
