from __future__ import annotations

import copy
import dataclasses
import time

import numpy as np

from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.sound.sound import SoundSystem
from extensions.libs.babylon.src.babylon import BabylonVisualization
from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.libs.babylon.src.lib.objects.box.box import WallFancy
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.tools.cli.cli import CommandSet, CLI, Command, CommandArgument
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.plot.realtime.rt_plot import RT_Plot_Widget, TimeSeries
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS
from extensions.simulation.src.objects.base_environment import BaseEnvironment
from extensions.simulation.src.objects.bilbo import (
    BILBO_DynamicAgent,
    BILBO_Control_Mode,
    DEFAULT_BILBO_MODEL,
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS,
    BILBO_3D_Input,
    BILBO_3D_State,
)
from extensions.hardware.joystick.joystick_manager import JoystickManager, Joystick

# === Navigator imports ================================================================================================
# Adjust this import to your project layout if needed (e.g. core.navigation.bilbo_navigator)
from bilbo_navigator import (
    BILBO_Navigator,
    BILBO_NavigatorSettings,
    MoveToTarget,
    TurnTowardsTarget,
    TurnTowardsHeading,
    CoordinatedMove,
    Wait as NavWait,
)

# ======================================================================================================================
# MAPPINGS
# ======================================================================================================================
BILBO_MAPPINGS = {
    "bilbo1": {"color": [0.7, 0, 0], "text": "1"},
    "bilbo2": {"color": [0, 0.7, 0], "text": "2"},
    "bilbo3": {"color": [0, 0.4, 0.9], "text": "3"},
}


# ======================================================================================================================
# UTILS
# ======================================================================================================================
def _wrap_to_pi(a: float) -> float:
    """Wrap angle to (-pi, pi]."""
    return float((a + np.pi) % (2.0 * np.pi) - np.pi)


def _clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


# ======================================================================================================================
# COMMANDS / CONFIGS
# ======================================================================================================================
@dataclasses.dataclass
class VelocityCommand:
    v: float = 0.0
    psi_dot: float = 0.0


@dataclasses.dataclass
class VelocityControllerConfig:
    # Longitudinal velocity PID
    k_p_v: float = -0.179
    k_i_v: float = -0.8
    k_d_v: float = -0.005

    # Yaw rate (psi_dot) PID
    k_p_psi_dot: float = 0.35121
    k_i_psi_dot: float = 7.6256
    k_d_psi_dot: float = 0.0023

    # Integral limits
    k_integral_max_v: float = 10.0
    k_integral_max_psi_dot: float = 10.0


# ======================================================================================================================
# INTERACTIVE BILBO AGENT
# ======================================================================================================================
class ProjectBILBO(BILBO_DynamicAgent):
    joystick: Joystick | None = None
    cli: CommandSet

    _v_integral: float = 0.0
    _v_last_error: float = 0.0

    _psi_dot_integral: float = 0.0
    _psi_dot_last_error: float = 0.0

    _last_state: BILBO_3D_State | None = None

    debug: float

    # Navigator
    navigator: BILBO_Navigator
    _nav_torque: np.ndarray

    # === INIT =========================================================================================================
    def __init__(self, agent_id, *args, **kwargs):
        super().__init__(agent_id, model=DEFAULT_BILBO_MODEL, *args, **kwargs)

        self.logger = Logger(f"InteractiveBILBO {agent_id}", "DEBUG")

        self.eigenstructureAssignment(
            poles=BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
            eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS,
        )

        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self.input_function)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self.output_function)

        self.cli = CommandSet(f"{agent_id}")

        # --------------------------------------------------------------------------------------------------------------
        # Controller / State commands
        # --------------------------------------------------------------------------------------------------------------
        change_controller_command = Command(
            "mode",
            function=self._set_control_mode,
            arguments=[
                CommandArgument(name="mode", short_name="m", type=int, optional=False),
            ],
            allow_positionals=True,
        )
        self.cli.addCommand(change_controller_command)

        set_position_command = Command(
            function=self._set_state,
            name="set_state",
            arguments=[
                CommandArgument(name="x", type=float, description="x position", optional=True, default=None),
                CommandArgument(name="y", type=float, description="y position", optional=True, default=None),
                CommandArgument(name="theta", type=float, description="theta position", optional=True, default=None),
                CommandArgument(name="psi", type=float, description="psi position", optional=True, default=None),
            ],
        )
        self.cli.addCommand(set_position_command)

        self.cli.addCommand(
            Command(
                name="set_velocity",
                function=self._set_velocity,
                arguments=[
                    CommandArgument(name="v", type=float, description="velocity", optional=False),
                    CommandArgument(name="psi_dot", type=float, description="angular velocity", optional=False),
                ],
            )
        )

        self.cli.addCommand(Command(name="reset", function=self.reset))

        self.cli.addCommand(
            Command(
                name="set_pid",
                function=self._set_velocity_pid,
                arguments=[
                    CommandArgument(name="kp", type=float, description="Proportional gain", optional=False),
                    CommandArgument(name="ki", type=float, description="Integral gain", optional=False),
                    CommandArgument(name="kd", type=float, description="Derivative gain", optional=False),
                ],
            )
        )

        # --------------------------------------------------------------------------------------------------------------
        # Navigator commands
        # --------------------------------------------------------------------------------------------------------------
        self.cli.addCommand(
            Command(
                name="nav_add_move",
                function=self._nav_add_move,
                description="Add MoveToTarget element to navigator queue",
                allow_positionals=True,
                arguments=[
                    CommandArgument(name="x", type=float, description="target x [m]", optional=False),
                    CommandArgument(name="y", type=float, description="target y [m]", optional=False),
                    CommandArgument(name="timeout", type=float, description="optional timeout [s]", optional=True,
                                    default=None),
                ],
            )
        )

        self.cli.addCommand(
            Command(
                name="nav_add_turn_target",
                function=self._nav_add_turn_target,
                description="Add TurnTowardsTarget element to navigator queue",
                allow_positionals=True,
                arguments=[
                    CommandArgument(name="x", type=float, description="target x [m]", optional=False),
                    CommandArgument(name="y", type=float, description="target y [m]", optional=False),
                    CommandArgument(name="timeout", type=float, description="optional timeout [s]", optional=True,
                                    default=None),
                ],
            )
        )

        self.cli.addCommand(
            Command(
                name="nav_add_turn_heading",
                function=self._nav_add_turn_heading,
                description="Add TurnTowardsHeading element to navigator queue",
                allow_positionals=True,
                arguments=[
                    CommandArgument(name="psi", type=float, description="target heading [rad]", optional=False),
                    CommandArgument(name="timeout", type=float, description="optional timeout [s]", optional=True,
                                    default=None),
                ],
            )
        )

        self.cli.addCommand(
            Command(
                name="nav_add_coord",
                function=self._nav_add_coord,
                description="Add CoordinatedMove element to navigator queue (go to x,y then align psi)",
                allow_positionals=True,
                arguments=[
                    CommandArgument(name="x", type=float, description="target x [m]", optional=False),
                    CommandArgument(name="y", type=float, description="target y [m]", optional=False),
                    CommandArgument(name="psi", type=float, description="arrival heading [rad]", optional=False),
                    CommandArgument(name="timeout", type=float, description="optional timeout [s]", optional=True,
                                    default=None),
                ],
            )
        )

        self.cli.addCommand(
            Command(
                name="nav_add_wait",
                function=self._nav_add_wait,
                description="Add Wait element to navigator queue",
                allow_positionals=True,
                arguments=[
                    CommandArgument(name="duration", type=float, description="wait duration [s]", optional=False),
                    CommandArgument(name="timeout", type=float, description="optional timeout [s]", optional=True,
                                    default=None),
                ],
            )
        )

        self.cli.addCommand(
            Command(
                name="nav_start",
                function=self._nav_start,
                description="Start navigator queue execution (also sets mode=POSITION)",
            )
        )

        self.cli.addCommand(
            Command(
                name="nav_clear",
                function=self._nav_clear,
                description="Clear navigator queue and stop current element",
            )
        )

        self.cli.addCommand(
            Command(
                name="nav_skip",
                function=self._nav_skip,
                description="Skip current navigator element",
            )
        )

        self.cli.addCommand(
            Command(
                name="nav_status",
                function=self._nav_status,
                description="Print navigator status info",
            )
        )

        # --------------------------------------------------------------------------------------------------------------
        # State / controllers
        # --------------------------------------------------------------------------------------------------------------
        self.velocity_command = VelocityCommand()
        self.velocity_controller_config = VelocityControllerConfig()
        self.velocity_controller_output = np.zeros(2, dtype=float)

        self.debug_value = 0.0

        # --------------------------------------------------------------------------------------------------------------
        # Navigator object inside ProjectBILBO
        # --------------------------------------------------------------------------------------------------------------
        self._nav_torque = np.zeros(2, dtype=float)

        nav_settings = BILBO_NavigatorSettings(
            Ts=float(self.Ts),
            # You can tune these in one place if desired:
            # allow_backwards_drive=True,
        )

        self.navigator = BILBO_Navigator(
            settings=nav_settings,
            state_fetch_function=self._nav_fetch_state,
            torque_set_function=self._nav_set_torque,
        )


    # ==============================================================================================================
    # Navigator glue
    # ==============================================================================================================
    def _nav_fetch_state(self) -> BILBO_3D_State:
        return self.dynamics.state

    def _nav_set_torque(self, left: float, right: float) -> None:
        self._nav_torque[0] = float(left)
        self._nav_torque[1] = float(right)

    # ==============================================================================================================
    # Navigator CLI helpers
    # ==============================================================================================================
    def _nav_add_move(self, x: float, y: float, timeout: float | None = None):
        el = MoveToTarget(target=[float(x), float(y)], timeout=timeout)
        self.navigator.add_element(el)
        self.logger.info(f"[NAV] queued MoveToTarget -> ({x:.3f}, {y:.3f})")

    def _nav_add_turn_target(self, x: float, y: float, timeout: float | None = None):
        el = TurnTowardsTarget(target=[float(x), float(y)], timeout=timeout)
        self.navigator.add_element(el)
        self.logger.info(f"[NAV] queued TurnTowardsTarget -> ({x:.3f}, {y:.3f})")

    def _nav_add_turn_heading(self, psi: float, timeout: float | None = None):
        el = TurnTowardsHeading(psi=float(psi), timeout=timeout)
        self.navigator.add_element(el)
        self.logger.info(f"[NAV] queued TurnTowardsHeading -> psi={psi:.3f} rad")

    def _nav_add_coord(self, x: float, y: float, psi: float, timeout: float | None = None):
        el = CoordinatedMove(target=[float(x), float(y)], psi=float(psi), timeout=timeout)
        self.navigator.add_element(el)
        self.logger.info(f"[NAV] queued CoordinatedMove -> ({x:.3f}, {y:.3f}), psi={psi:.3f}")

    def _nav_add_wait(self, duration: float, timeout: float | None = None):
        el = NavWait(duration=float(duration), timeout=timeout)
        self.navigator.add_element(el)
        self.logger.info(f"[NAV] queued Wait -> {duration:.3f}s")

    def _nav_start(self):
        # Ensure we are in POSITION mode so the navigator torques are applied
        self.setMode(BILBO_Control_Mode.POSITION)
        self.navigator.start_queue()
        self.logger.info("[NAV] started queue (mode set to POSITION)")

    def _nav_clear(self):
        self.navigator.clear_queue()
        self._nav_torque[:] = 0.0
        self.logger.info("[NAV] cleared queue")

    def _nav_skip(self):
        self.navigator.skip_current_element()
        self._nav_torque[:] = 0.0
        self.logger.info("[NAV] skipped current element")

    def _nav_status(self):
        el = self.navigator._current_element  # simple introspection
        if el is None:
            self.logger.info(
                f"[NAV] status={self.navigator.status}, current=None, queued={self.navigator.movement_queue.qsize()}")
        else:
            self.logger.info(
                f"[NAV] status={self.navigator.status}, current={el.type}, el_status={el.status}, queued={self.navigator.movement_queue.qsize()}"
            )

    # === METHODS ======================================================================================================
    def assignJoystick(self, joystick: Joystick):
        self.joystick = joystick

        self.joystick.callbacks.A.register(self.enableController)
        self.joystick.callbacks.B.register(self.disableController)
        self.joystick.callbacks.X.register(self.setMode, inputs={"mode": BILBO_Control_Mode.VELOCITY})
        # If your joystick has Y, you can uncomment to quickly switch to position mode:
        # self.joystick.callbacks.Y.register(self.setMode, inputs={"mode": BILBO_Control_Mode.POSITION})

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self):
        if self.joystick is None:
            return
        self.joystick.callbacks.A.remove(self.enableController)
        self.joystick.callbacks.B.remove(self.disableController)

        self.joystick = None
        self.velocity_command = VelocityCommand()

    # ------------------------------------------------------------------------------------------------------------------
    def enableController(self):
        self.logger.info("Controller enabled")
        self.mode = BILBO_Control_Mode.BALANCING

    # ------------------------------------------------------------------------------------------------------------------
    def disableController(self):
        self.logger.info("Controller disabled")
        self.mode = BILBO_Control_Mode.OFF

    # ------------------------------------------------------------------------------------------------------------------
    def input_function(self):
        if self.joystick is None:
            return
        if self.mode != BILBO_Control_Mode.VELOCITY:
            return

        axis_forward = -self.joystick.getAxis("LEFT_VERTICAL")
        axis_turn = -self.joystick.getAxis("RIGHT_HORIZONTAL")

        velocity_command = VelocityCommand(v=axis_forward * 2, psi_dot=axis_turn * 6)
        self.velocity_command = velocity_command

    # ------------------------------------------------------------------------------------------------------------------
    def _controller(self) -> BILBO_3D_Input:
        """
        Runs every timestep before the dynamics.
        Returns wheel torques (left/right) that are combined with the stabilizing state feedback.
        """
        if self.mode == BILBO_Control_Mode.OFF:
            controller_input = BILBO_3D_Input(M_L=0, M_R=0)

        elif self.mode == BILBO_Control_Mode.BALANCING:
            controller_input = self.input.asarray() - self.K @ self.dynamics.state.asarray()

        elif self.mode == BILBO_Control_Mode.VELOCITY:
            self.velocity_controller_output = self._velocity_control()
            controller_input = self.velocity_controller_output - self.K @ self.dynamics.state.asarray()

        elif self.mode == BILBO_Control_Mode.POSITION:
            # Use the Navigator in POSITION mode (queue-based motion primitives).
            # Navigator computes wheel torques and writes them into self._nav_torque.
            self.navigator._step()
            u_pos = self._nav_torque.copy()
            controller_input = u_pos - self.K @ self.dynamics.state.asarray()

        else:
            raise ValueError(f"Unknown mode: {self.mode}")

        return BILBO_3D_Input.as_state(controller_input)

    # ------------------------------------------------------------------------------------------------------------------
    def _velocity_control(self) -> np.ndarray:
        """
        Combined PID control for forward velocity v and yaw rate psi_dot.
        Produces left/right wheel torques.
        """
        state = self.dynamics.state

        v = state.v
        psi_dot = state.psi_dot

        # Errors
        e_v = self.velocity_command.v - v
        e_psi_dot = self.velocity_command.psi_dot - psi_dot

        # Integrals
        self._v_integral += e_v * self.Ts
        self._psi_dot_integral += e_psi_dot * self.Ts

        # Derivatives
        e_v_dot = (e_v - self._v_last_error) / self.Ts
        self._v_last_error = e_v

        e_psi_dot_dot = (e_psi_dot - self._psi_dot_last_error) / self.Ts
        self._psi_dot_last_error = e_psi_dot

        # Saturate integrals
        self._v_integral = _clamp(
            self._v_integral,
            -self.velocity_controller_config.k_integral_max_v,
            self.velocity_controller_config.k_integral_max_v,
        )
        self._psi_dot_integral = _clamp(
            self._psi_dot_integral,
            -self.velocity_controller_config.k_integral_max_psi_dot,
            self.velocity_controller_config.k_integral_max_psi_dot,
        )

        # PID for v
        u_v = (
                self.velocity_controller_config.k_p_v * e_v
                + self.velocity_controller_config.k_i_v * self._v_integral
                + self.velocity_controller_config.k_d_v * e_v_dot
        )

        # PID for psi_dot
        u_psi = (
                self.velocity_controller_config.k_p_psi_dot * e_psi_dot
                + self.velocity_controller_config.k_i_psi_dot * self._psi_dot_integral
                + self.velocity_controller_config.k_d_psi_dot * e_psi_dot_dot
        )

        # Debug (e.g. psi_dot control output)
        self.debug_value = float(u_psi)

        # Combine into wheel torques:
        u_l = u_v - u_psi
        u_r = u_v + u_psi

        return np.asarray([u_l, u_r], dtype=float)

    # ------------------------------------------------------------------------------------------------------------------
    def _set_velocity(self, v: float, psi_dot: float):
        self.velocity_command.v = v
        self.velocity_command.psi_dot = psi_dot

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self, x0=None):
        super().reset(BILBO_3D_State(0, 0, 0, 0, 0, 0, 0))
        self.velocity_command.v = 0
        self.velocity_command.psi_dot = 0
        self._last_state = copy.deepcopy(self.dynamics.state)

        # Reset velocity PID states
        self._v_integral = 0.0
        self._v_last_error = 0.0
        self._psi_dot_integral = 0.0
        self._psi_dot_last_error = 0.0

        self.velocity_controller_output = np.zeros(2, dtype=float)

        # Reset navigator state/torques
        try:
            self.navigator.clear_queue()
        except Exception:
            pass
        self._nav_torque[:] = 0.0

    # ------------------------------------------------------------------------------------------------------------------
    def _set_velocity_pid(self, kp: float, ki: float, kd: float):
        """
        Set PID gains for the forward velocity v.
        psi_dot gains are configured separately (for now, just in code).
        """
        self.velocity_controller_config.k_p_v = kp
        self.velocity_controller_config.k_i_v = ki
        self.velocity_controller_config.k_d_v = kd
        self.logger.info(f"Velocity PID gains set to: kp={kp}, ki={ki}, kd={kd}")

    # ------------------------------------------------------------------------------------------------------------------
    def _set_control_mode(self, mode: int):
        if mode not in [0, 2, 3, 4]:
            self.logger.warning(f"Unknown mode: {mode}")
            return

        # VELOCITY mode: reset PID states
        if mode == int(BILBO_Control_Mode.VELOCITY):
            self._v_integral = 0.0
            self._v_last_error = 0.0
            self._psi_dot_integral = 0.0
            self._psi_dot_last_error = 0.0
            self._last_state = BILBO_3D_State(0, 0, 0, 0, 0, 0, 0)
            self.velocity_controller_output = np.zeros(2)

        # POSITION mode: clear any old nav torques (do NOT clear queue automatically)
        if mode == int(BILBO_Control_Mode.POSITION):
            self._nav_torque[:] = 0.0

        self.logger.info(f"Controller mode set to {BILBO_Control_Mode(mode)}")
        self.setMode(BILBO_Control_Mode(mode))

    # ------------------------------------------------------------------------------------------------------------------
    def _set_state(self, x: float | None = None, y: float | None = None, theta: float | None = None,
                   psi: float | None = None):
        state = copy.copy(self.dynamics.state)

        if x is not None:
            state.x = x
        if y is not None:
            state.y = y
        if theta is not None:
            state.theta = theta
        if psi is not None:
            state.psi = psi

        self.dynamics.state = state

    # ------------------------------------------------------------------------------------------------------------------
    def output_function(self):
        # This can be used for logging/telemetry; control happens in _controller().
        # Keep it lightweight.
        return


# ======================================================================================================================
# BILBO INTERACTIVE EXAMPLE
# ======================================================================================================================
class BILBO_InteractiveExample:
    joystick_manager: JoystickManager
    babylon_visualization: BabylonVisualization
    robots: dict[str, dict]

    cli: CLI
    gui: GUI
    command_set: "BILBO_Interactive_CommandSet"
    soundsystem: SoundSystem

    # === INIT =========================================================================================================
    def __init__(self):
        self.logger = Logger("BILBO_InteractiveExample", "DEBUG")
        self.joystick_manager = JoystickManager()
        self.joystick_manager.callbacks.new_joystick.register(self._newJoystick_callback)
        self.joystick_manager.callbacks.joystick_disconnected.register(self._joystickDisconnected_callback)

        self.robots: dict[str, dict] = {}

        self.command_set = BILBO_Interactive_CommandSet(self)
        self.cli = CLI(id="bilbo_interactive", root=self.command_set)

        self.gui = GUI(id="bilbo_interactive", host="localhost", run_js=True)
        self.gui.cli_terminal.setCLI(self.cli)

        self.babylon_visualization = BabylonVisualization(id="babylon", babylon_config={"title": "BILBO Interactive"})

        # Sound System for speaking and sounds
        self.soundsystem = SoundSystem(primary_engine="etts", volume=1)
        self.soundsystem.start()

        # Simulation Environment
        self.env = BaseEnvironment(Ts=0.01, run_mode="rt")
        self.env.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self._simulationOutputStep)

        # Make a logging redirection
        addLogRedirection(self._logRedirection, minimum_level="DEBUG")

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self.joystick_manager.init()
        self._buildGUI()
        self._buildBabylon()
        self.babylon_visualization.init()
        self.env.init()
        self.env.initialize()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.joystick_manager.start()
        self.gui.start()
        self.babylon_visualization.start()
        self.env.start()
        self.logger.info("BILBO interactive started")
        self.soundsystem.speak("BILBO interactive started")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.soundsystem.speak("BILBO interactive stopped")
        self.joystick_manager.exit()
        self.logger.info("BILBO interactive stopped")
        time.sleep(2)

    # ------------------------------------------------------------------------------------------------------------------
    def addRobot(self, robot_id: str):
        # Check if the robot already exists
        if robot_id in self.robots:
            self.logger.warning(f"Robot with ID {robot_id} already exists")
            return

        if robot_id not in BILBO_MAPPINGS:
            self.logger.warning(f"Robot with ID {robot_id} is not mapped. Please use one of:")
            for rid, mapping in BILBO_MAPPINGS.items():
                self.logger.warning(f"  {rid}: {mapping}")
            return

        # Create a new simulated robot
        robot = ProjectBILBO(agent_id=robot_id, Ts=0.01)
        self.robots[robot_id] = {"robot": robot}

        # Add it to the environment
        self.env.addObject(robot)

        # Add a babylon object
        robot_babylon = BabylonBilbo(object_id=robot_id, color=BILBO_MAPPINGS[robot_id]["color"],
                                     text=BILBO_MAPPINGS[robot_id]["text"])
        self.babylon_visualization.addObject(robot_babylon)
        self.robots[robot_id]["babylon"] = robot_babylon

        plot = RT_Plot_Widget(
            plot_config={"title": f"{robot_id} Plot", "show_title": True, "legend_label_type": "point"},
        )

        self.cli.root.addChild(robot.cli)
        self.logger.info(f"Robot with ID {robot_id} added")

        # Add Plot
        y_axis = plot.plot.add_y_axis(
            f"{robot_id}_v",
            {
                "label": "v [m/s]",
                "min": -2,
                "max": 2,
                "color": [1, 1, 1],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 2,
                "highlight_zero": True,
                "side": "left",
            },
        )

        timeseries_v = TimeSeries(
            id=f"{robot_id}_v",
            y_axis=y_axis,
            name=f"{robot_id}_v",
            unit="m/s",
            color=[1, 0, 0],
            fill=False,
            tension=0.0,
            precision=2,
            width=2,
        )

        timeseries_v_cmd = TimeSeries(
            id=f"{robot_id}_v_cmd",
            y_axis=y_axis,
            name=f"{robot_id}_v_cmd",
            unit="m/s",
            color=[0, 0, 1],
            fill=False,
            tension=0.0,
            precision=2,
            width=2,
        )

        timeseries_psi_dot = TimeSeries(
            id=f"{robot_id}_psi_dot",
            y_axis=y_axis,
            name=f"{robot_id}_psi_dot",
            unit="rad/s",
            color=[0, 1, 0],
            fill=False,
            tension=0.0,
            precision=2,
            width=2,
        )

        timeseries_psi_dot_cmd = TimeSeries(
            id=f"{robot_id}_psi_dot_cmd",
            y_axis=y_axis,
            name=f"{robot_id}_psi_dot_cmd",
            unit="rad/s",
            color=[1, 0, 1],
            fill=False,
            tension=0.0,
            precision=2,
            width=2,
        )

        timeseries_v.set_value(0.0)
        timeseries_v_cmd.set_value(0.0)
        plot.plot.add_timeseries(timeseries_v)
        plot.plot.add_timeseries(timeseries_v_cmd)
        plot.plot.add_timeseries(timeseries_psi_dot_cmd)
        plot.plot.add_timeseries(timeseries_psi_dot)

        self.robots[robot_id]["plot"] = plot
        self.robots[robot_id]["timeseries_v"] = timeseries_v
        self.robots[robot_id]["timeseries_v_cmd"] = timeseries_v_cmd
        self.robots[robot_id]["timeseries_psi_dot"] = timeseries_psi_dot
        self.robots[robot_id]["timeseries_psi_dot_cmd"] = timeseries_psi_dot_cmd

        self.page.addWidget(plot, row=1, height=18, width=18)

    # ------------------------------------------------------------------------------------------------------------------
    def removeRobot(self, robot: str | ProjectBILBO):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def assignJoystick(self, joystick: int, robot: str | ProjectBILBO):
        js = self.joystick_manager.getJoystickById(joystick)
        if js is None:
            self.logger.warning(f"Joystick with ID {joystick} does not exist")
            return
        rb = self.getRobotByID(robot if isinstance(robot, str) else robot.agent_id)
        if rb is None:
            self.logger.warning(f"Robot with ID {robot} does not exist")
            return

        # Check if this joystick is already assigned to another robot
        for robot_id, robot_data in self.robots.items():
            if robot_data["robot"].joystick == js:
                self.logger.warning(f"Joystick with ID {js.id} is already assigned to robot {robot_id}")
                robot_data["robot"].removeJoystick()

        rb.assignJoystick(js)
        self.logger.info(f"Joystick assigned: {js.id} -> {rb.agent_id}")

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self, robot: str | ProjectBILBO):
        rb = self.getRobotByID(robot if isinstance(robot, str) else robot.agent_id)
        if rb is None:
            self.logger.warning(f"Robot with ID {robot} does not exist")
            return
        rb.removeJoystick()
        self.logger.info(f"Joystick of robot {rb.agent_id} removed")

    # ------------------------------------------------------------------------------------------------------------------
    def getRobotByID(self, robot_id: str) -> ProjectBILBO | None:
        if robot_id in self.robots:
            return self.robots[robot_id]["robot"]
        return None

    # === PRIVATE METHODS ==============================================================================================
    def _newJoystick_callback(self, joystick: Joystick):
        self.soundsystem.speak(f"New joystick {joystick.id} connected.")

    # ------------------------------------------------------------------------------------------------------------------
    def _joystickDisconnected_callback(self, joystick: Joystick):
        self.soundsystem.speak(f"Joystick with {joystick.id} disconnected.")

    # ------------------------------------------------------------------------------------------------------------------
    def _buildGUI(self):
        cat1 = Category("cat1", max_pages=1)
        page1 = Page("page1")
        cat1.addPage(page1)
        self.gui.addCategory(cat1)
        self.page = page1

        self.babylon_widget = BabylonWidget(widget_id="babylon_widget")
        page1.addWidget(self.babylon_widget, row=1, column=1, height=18, width=26)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildBabylon(self):
        floor = SimpleFloor("floor", size_y=50, size_x=50, texture="floor_bright.png")
        self.babylon_visualization.addObject(floor)

        wall1 = WallFancy("wall1", length=3, texture="wood4.png", include_end_caps=True)
        wall1.setPosition(y=1.5)
        self.babylon_visualization.addObject(wall1)

        wall2 = WallFancy("wall2", length=3, texture="wood4.png", include_end_caps=True)
        self.babylon_visualization.addObject(wall2)
        wall2.setPosition(y=-1.5)

        wall3 = WallFancy("wall3", length=3, texture="wood4.png")
        wall3.setPosition(x=1.5)
        wall3.setAngle(np.pi / 2)
        self.babylon_visualization.addObject(wall3)

        wall4 = WallFancy("wall4", length=3, texture="wood4.png")
        wall4.setPosition(x=-1.5)
        wall4.setAngle(np.pi / 2)
        self.babylon_visualization.addObject(wall4)

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        print_text = f"[{logger.name}] {log}"
        color = LOGGING_COLORS[level]
        color = [c / 255 for c in color]
        self.gui.print(print_text, color=color)

    # ------------------------------------------------------------------------------------------------------------------
    def _simulationOutputStep(self):
        for robot in self.robots.values():
            try:
                rb: ProjectBILBO = robot["robot"]
                state = rb.state
                robot["babylon"].set_state(x=state.x, y=state.y, theta=state.theta, psi=state.psi)

                # Plot actual v/psi_dot
                robot["timeseries_v"].set_value(state.v)
                robot["timeseries_psi_dot"].set_value(state.psi_dot)

                # Plot "commands":
                # - In VELOCITY mode, show velocity_command
                # - In POSITION mode (navigator), we don't have v_cmd directly; keep as 0 and just show psi_dot_cmd=0
                if rb.mode == BILBO_Control_Mode.VELOCITY:
                    robot["timeseries_v_cmd"].set_value(rb.velocity_command.v)
                    robot["timeseries_psi_dot_cmd"].set_value(rb.velocity_command.psi_dot)
                else:
                    robot["timeseries_v_cmd"].set_value(0.0)
                    robot["timeseries_psi_dot_cmd"].set_value(0.0)

            except Exception as e:
                self.logger.error(f'Error updating robot {robot["robot"].agent_id}: {e}')


# ======================================================================================================================
# CLI ROOT
# ======================================================================================================================
class BILBO_Interactive_CommandSet(CommandSet):
    def __init__(self, example: BILBO_InteractiveExample):
        super().__init__("bilbo_interactive")
        self.example = example

        add_robot_command = Command(
            function=self.example.addRobot,
            name="add_robot",
            description="Add a new robot to the simulation",
            allow_positionals=True,
            arguments=[CommandArgument(name="robot_id", type=str, description="ID of the robot to add")],
        )
        self.addCommand(add_robot_command)

        assign_joystick_command = Command(
            function=self.example.assignJoystick,
            name="assign_joystick",
            description="Assign a joystick to a robot",
            allow_positionals=True,
            arguments=[
                CommandArgument(name="joystick", type=int, description="ID of the joystick to assign"),
                CommandArgument(name="robot", type=str, description="ID of the robot to assign the joystick to"),
            ],
        )
        self.addCommand(assign_joystick_command)


# ======================================================================================================================
def main():
    example = BILBO_InteractiveExample()
    example.init()
    example.start()

    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
