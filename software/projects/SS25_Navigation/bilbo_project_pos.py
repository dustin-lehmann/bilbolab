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


@dataclasses.dataclass
class PositionCommand:
    x: float = 0.0
    y: float = 0.0
    psi: float = 0.0
    enabled: bool = False  # if False, position controller outputs zeros


@dataclasses.dataclass
class PositionControllerConfig:
    """
    Carrot-chase position controller that directly outputs wheel torques.

    Interpretation:
      - A "linear" PI acts on distance-to-goal -> common torque u_v
      - An "angular" PI acts on heading error -> differential torque u_psi
      - Carrot lookahead smooths heading when far from goal
      - When near goal position, it switches to heading-only control to reach psi target
    """

    # Carrot lookahead distance [m]
    lookahead: float = 0.3

    # Position and heading tolerances
    arrive_tolerance_xy: float = 0.05  # [m]
    arrive_tolerance_psi: float = 0.05  # [rad]

    # Linear (distance) PI gains -> common torque
    lin_kp: float = -0.1
    lin_ki: float = -0.15
    lin_i_limit: float = 0.2  # torque contribution clamp

    # Angular (heading) PI gains -> differential torque
    ang_kp: float = 1
    ang_ki: float = 0.2
    ang_i_limit: float = 0.1
    # Output torque limits (soft clamp)
    max_common_torque: float = 1
    max_diff_torque: float = 1

    # Optional slowdown near goal (distance shaping)
    slow_radius: float = 0.4  # [m]
    min_speed_cos_scale: float = 0.0  # keep >=0 so you don't "reverse into" heading errors


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

    # Position controller internal PI accumulators
    _pos_i_lin: float = 0.0
    _pos_i_ang: float = 0.0

    _last_state: BILBO_3D_State | None = None

    debug: float

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

        # Position target command (carrot-chase)
        self.cli.addCommand(
            Command(
                name="set_target",
                function=self._set_target,
                arguments=[
                    CommandArgument(name="x", type=float, description="target x [m]", optional=True, default=None),
                    CommandArgument(name="y", type=float, description="target y [m]", optional=True, default=None),
                    CommandArgument(name="psi", type=float, description="target psi [rad]", optional=True,
                                    default=None),
                ],
            )
        )

        self.cli.addCommand(
            Command(
                name="clear_target",
                function=self._clear_target,
            )
        )

        self.cli.addCommand(
            Command(
                name="reset",
                function=self.reset,
            )
        )

        # This still only sets the v PID from CLI (psi_dot PID gains can be set in code for now)
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

        self.velocity_command = VelocityCommand()
        self.velocity_controller_config = VelocityControllerConfig()
        self.velocity_controller_output = np.zeros(2)

        self.position_command = PositionCommand()
        self.position_controller_config = PositionControllerConfig()

        self.debug_value = 0.0

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
            u_pos = self._position_control()  # wheel torques directly (NOT cascaded through velocity PID)
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
        #   forward term u_v is same on both wheels,
        #   turning term u_psi is differential.
        u_l = u_v - u_psi
        u_r = u_v + u_psi

        return np.asarray([u_l, u_r], dtype=float)

    def _set_target(self, x: float | None = None, y: float | None = None, psi: float | None = None):
        """
        Set the position target for carrot-chase.

        New behavior:
          - If psi is None: go to (x,y) only, no final turn.
          - If x and y are None: turn in place to psi (heading-only mode).
          - If x,y given and psi given: go to (x,y), then align to psi.

        Notes:
          - We reset PI integrators here to avoid carrying windup between targets.
        """
        st = self.dynamics.state

        # Allow "turn-only" mode: x=y=None, psi provided
        if x is None and y is None:
            if psi is None:
                self.logger.warning("set_target called with x=None,y=None and psi=None. Nothing to do.")
                return
            self.position_command.x = None
            self.position_command.y = None
            self.position_command.psi = float(psi)
            self.position_command.enabled = True

            # Reset integrators on new target
            self._pos_i_lin = 0.0
            self._pos_i_ang = 0.0

            self.logger.info(f"Target set to TURN-ONLY psi={self.position_command.psi:.3f} (enabled)")
            return

        # Position mode requires both x and y
        if x is None or y is None:
            self.logger.warning("Position target requires both x and y (or neither for turn-only).")
            return

        self.position_command.x = float(x)
        self.position_command.y = float(y)

        # If psi is omitted, we do NOT enforce a final heading alignment
        self.position_command.psi = (None if psi is None else float(psi))
        self.position_command.enabled = True

        # Reset integrators on new target to avoid windup carryover
        self._pos_i_lin = 0.0
        self._pos_i_ang = 0.0

        if self.position_command.psi is None:
            self.logger.info(
                f"Target set to x={self.position_command.x:.3f}, y={self.position_command.y:.3f}, psi=None (pos-only, enabled)"
            )
        else:
            self.logger.info(
                f"Target set to x={self.position_command.x:.3f}, y={self.position_command.y:.3f}, psi={self.position_command.psi:.3f} (enabled)"
            )

    def _clear_target(self):
        self.position_command.enabled = False
        self.position_command.x = None
        self.position_command.y = None
        self.position_command.psi = None
        self._pos_i_lin = 0.0
        self._pos_i_ang = 0.0
        self.logger.info("Target cleared (position controller disabled)")

    def _position_control(self) -> np.ndarray:
        """
        Carrot-chase position controller for differential drive (non-holonomic),
        implemented to output wheel torques directly.

        Modes:
          1) Turn-only: (x,y)=None and psi != None  -> turn in place to psi.
          2) Position-only: (x,y) set and psi=None -> drive to (x,y) and stop (no final turn).
          3) Pose: (x,y) set and psi set          -> drive to (x,y) then align to psi.

        Important fixes:
          - Reset yaw integrator when switching from "drive" to "final turn".
          - Anti-windup: don't integrate angular error when output saturates.
          - Reset linear integrator when entering final turn.
        """
        cfg = self.position_controller_config
        st = self.dynamics.state

        if not self.position_command.enabled:
            return np.asarray([0.0, 0.0], dtype=float)

        x = float(st.x)
        y = float(st.y)
        psi = float(st.psi)

        xg = self.position_command.x
        yg = self.position_command.y
        psig = self.position_command.psi  # can be None now

        # ---------------------------
        # TURN-ONLY MODE
        # ---------------------------
        if xg is None and yg is None:
            if psig is None:
                return np.asarray([0.0, 0.0], dtype=float)

            e_psi = _wrap_to_pi(float(psig) - psi)

            if abs(e_psi) <= cfg.arrive_tolerance_psi:
                self._pos_i_ang = 0.0
                self._pos_i_lin = 0.0
                self.debug_value = 0.0
                return np.asarray([0.0, 0.0], dtype=float)

            # PI on heading -> diff torque, with anti-windup on saturation
            u_psi_unsat = cfg.ang_kp * e_psi + self._pos_i_ang
            u_psi = _clamp(u_psi_unsat, -cfg.max_diff_torque, cfg.max_diff_torque)

            # integrate only if not saturated (or if integration would reduce saturation)
            if abs(u_psi_unsat) < cfg.max_diff_torque or np.sign(u_psi_unsat) != np.sign(e_psi):
                self._pos_i_ang = _clamp(
                    self._pos_i_ang + e_psi * cfg.ang_ki * self.Ts,
                    -cfg.ang_i_limit,
                    cfg.ang_i_limit,
                )
                # recompute after integration (optional but keeps it consistent)
                u_psi = _clamp(cfg.ang_kp * e_psi + self._pos_i_ang, -cfg.max_diff_torque, cfg.max_diff_torque)

            self.debug_value = float(e_psi)
            return np.asarray([-u_psi, +u_psi], dtype=float)

        # ---------------------------
        # POSITION (or POSE) MODE
        # ---------------------------
        dx = float(xg) - x
        dy = float(yg) - y
        dist = float(np.hypot(dx, dy))

        # If we reached the goal position:
        if dist <= cfg.arrive_tolerance_xy:
            # Always stop forward motion here
            self._pos_i_lin = 0.0

            # If psi target is None -> no final turn (position-only)
            if psig is None:
                self._pos_i_ang = 0.0
                self.debug_value = 0.0
                return np.asarray([0.0, 0.0], dtype=float)

            # Final heading alignment
            e_psi_goal = _wrap_to_pi(float(psig) - psi)

            if abs(e_psi_goal) <= cfg.arrive_tolerance_psi:
                self._pos_i_ang = 0.0
                self.debug_value = 0.0
                return np.asarray([0.0, 0.0], dtype=float)

            if getattr(self, "_pos_final_turn_active", False) is False:
                self._pos_i_ang = 0.0
                self._pos_final_turn_active = True
            # If we ever leave the region, we’ll clear this flag below.

            u_psi_unsat = cfg.ang_kp * e_psi_goal + self._pos_i_ang
            u_psi = _clamp(u_psi_unsat, -cfg.max_diff_torque, cfg.max_diff_torque)

            # Anti-windup integration
            if abs(u_psi_unsat) < cfg.max_diff_torque or np.sign(u_psi_unsat) != np.sign(e_psi_goal):
                self._pos_i_ang = _clamp(
                    self._pos_i_ang + e_psi_goal * cfg.ang_ki * self.Ts,
                    -cfg.ang_i_limit,
                    cfg.ang_i_limit,
                )
                u_psi = _clamp(cfg.ang_kp * e_psi_goal + self._pos_i_ang, -cfg.max_diff_torque, cfg.max_diff_torque)

            self.debug_value = float(e_psi_goal)
            return np.asarray([-u_psi, +u_psi], dtype=float)

        # We are not at goal position -> driving region
        # Ensure final-turn flag is reset when moving again
        self._pos_final_turn_active = False

        # Carrot-chase point between current pose and goal
        look = max(1e-6, float(cfg.lookahead))
        step_back = max(0.0, dist - look) if dist > 1e-9 else 0.0
        ux = dx / (dist + 1e-9)
        uy = dy / (dist + 1e-9)
        cx = float(xg) - ux * step_back
        cy = float(yg) - uy * step_back

        psi_des = float(np.arctan2(cy - y, cx - x))
        e_psi = _wrap_to_pi(psi_des - psi)

        # Linear PI on distance -> common torque, with slowdown near goal
        slow = 1.0
        if cfg.slow_radius > 1e-6:
            slow = _clamp(dist / cfg.slow_radius, 0.0, 1.0)

        # (Optional) reset lin integrator if we are "facing away" a lot, to avoid pushing into walls
        # if abs(e_psi) > np.deg2rad(100):
        #     self._pos_i_lin = 0.0

        u_v_unsat = (cfg.lin_kp * dist + self._pos_i_lin) * slow

        # Project forward to reduce drive when misaligned
        cos_scale = float(np.cos(e_psi))
        cos_scale = max(cfg.min_speed_cos_scale, cos_scale)
        u_v_unsat *= cos_scale

        u_v = _clamp(u_v_unsat, -cfg.max_common_torque, cfg.max_common_torque)

        # Anti-windup linear integrator: integrate only if not saturated (or if helping)
        if abs(u_v_unsat) < cfg.max_common_torque or np.sign(u_v_unsat) != np.sign(dist):
            self._pos_i_lin = _clamp(
                self._pos_i_lin + dist * cfg.lin_ki * self.Ts,
                -cfg.lin_i_limit,
                cfg.lin_i_limit,
            )
            u_v = _clamp((cfg.lin_kp * dist + self._pos_i_lin) * slow * cos_scale, -cfg.max_common_torque,
                         cfg.max_common_torque)

        # Angular PI on heading error -> differential torque
        u_psi_unsat = cfg.ang_kp * e_psi + self._pos_i_ang
        u_psi = _clamp(u_psi_unsat, -cfg.max_diff_torque, cfg.max_diff_torque)

        # Anti-windup angular integrator: integrate only if not saturated (or if helping)
        if abs(u_psi_unsat) < cfg.max_diff_torque or np.sign(u_psi_unsat) != np.sign(e_psi):
            self._pos_i_ang = _clamp(
                self._pos_i_ang + e_psi * cfg.ang_ki * self.Ts,
                -cfg.ang_i_limit,
                cfg.ang_i_limit,
            )
            u_psi = _clamp(cfg.ang_kp * e_psi + self._pos_i_ang, -cfg.max_diff_torque, cfg.max_diff_torque)

        # Combine to wheel torques
        u_l = u_v - u_psi
        u_r = u_v + u_psi

        self.debug_value = float(dist)
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

        # Reset position PI states
        self._pos_i_lin = 0.0
        self._pos_i_ang = 0.0
        self.position_command.enabled = False

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

        # POSITION mode: reset position PI accumulators (keep target as-is)
        if mode == int(BILBO_Control_Mode.POSITION):
            self._pos_i_lin = 0.0
            self._pos_i_ang = 0.0

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
        ...


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
                state = robot["robot"].state
                robot["babylon"].set_state(x=state.x, y=state.y, theta=state.theta, psi=state.psi)
                robot["timeseries_v"].set_value(state.v)
                robot["timeseries_v_cmd"].set_value(robot["robot"].velocity_command.v)
                robot["timeseries_psi_dot"].set_value(state.psi_dot)
                robot["timeseries_psi_dot_cmd"].set_value(robot["robot"].velocity_command.psi_dot)
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
