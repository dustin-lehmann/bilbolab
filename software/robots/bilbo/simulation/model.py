import copy
import dataclasses
import enum
import math
import pickle

import control
import matplotlib.pyplot as plt
import numpy as np
from control import ss
from numpy import nan, hstack

from core.utils.logging_utils import Logger
from core.utils.states import State, listToStateList, vectorToStateList
from simulation import core as core
from simulation.core import spaces as sp
from simulation.core.agents import Agent
from simulation.core.dynamics import LinearDynamics
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS
from simulation.core.scheduling import ScheduledObject
from core.utils.control_lib import lib_control
from simulation.utils.orientations import bilboToRotMat, bilboFromRotMat
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode

DEFAULT_SAMPLE_TIME = 0.01


@dataclasses.dataclass
class BilboModel:
    m_b: float  # Mass of body
    m_w: float  # Mass of wheels
    l: float  # COG position
    d_w: float  # Distance between of the wheels
    I_w: float  # Inertia of the wheels
    I_y: float  # Inertia of the body
    I_x: float  # Inertia of the body
    I_z: float  # Inertia of the body
    c_alpha: float  # Drag coefficient, speed dependent
    r_w: float  # Radius of the wheels
    tau_theta: float  # Drag coefficient, theta dependent
    tau_x: float  # Drag coefficient, speed dependent
    max_pitch: float  # Max pitch for floor contact


DEFAULT_BILBO_MODEL = BilboModel(
    m_b=1.2,
    m_w=0.4,
    l=0.026,
    d_w=0.22,
    I_w=2e-4,
    I_y=0.005,
    I_x=0.02,
    I_z=0.03,
    c_alpha=4.6302e-4,
    r_w=0.06,
    tau_theta=0.4,
    tau_x=0.4,
    max_pitch=np.deg2rad(105)
)

BILBO_MICHAEL_MODEL = BilboModel(
    m_b=2.5,
    m_w=0.636,
    l=0.026,
    d_w=0.28,
    I_w=5.1762e-4,
    I_y=0.01648,
    I_x=0.02,
    I_z=0.03,
    c_alpha=4.6302e-4,
    r_w=0.055,
    tau_theta=0.0,
    tau_x=0.0,
    max_pitch=np.deg2rad(105)
)

# Default model parameters (formerly TWIPR_Michael_Model)
BILBO_SMALL = BilboModel(
    m_b=1,
    m_w=0.292,
    l=0.01,
    d_w=0.168,
    I_w=2.773e-4,
    I_y=0.001,
    I_x=0.01,
    I_z=0.03,
    c_alpha=4.6302e-4,
    r_w=0.062,
    tau_theta=0.5,
    tau_x=0.5,
    max_pitch=np.deg2rad(105)
)

BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES = [0, -10, -5 + 3j, -5 - 3j, 0, -15]

BILBO_2D_POLES = [0, -10, -5 + 3j, -5 - 3j]

BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS = np.array([[1, nan, nan, nan, 0, nan],
                                                          [nan, 1, nan, nan, nan, nan],
                                                          [nan, nan, 1, 1, nan, 0],
                                                          [nan, nan, nan, nan, nan, nan],
                                                          [0, nan, nan, nan, 1, 1],
                                                          [nan, 0, 0, 0, nan, nan]])


# ======================================================================================================================
# === BILBO 2D =========================================================================================================
@dataclasses.dataclass
class BILBO_2D_State(State):
    s: float
    v: float
    theta: float
    theta_dot: float


@dataclasses.dataclass
class BILBO_2D_Input(State):
    M: float


class BILBO_Dynamics_2D_Linear:
    system: control.StateSpace = None

    x0: BILBO_2D_State = BILBO_2D_State(s=0, v=0, theta=0, theta_dot=0)
    state: BILBO_2D_State = None
    K: np.ndarray = None

    # === INIT =========================================================================================================
    def __init__(self, model: BilboModel, Ts=DEFAULT_SAMPLE_TIME, x0=None):
        if x0 is not None:
            self.x0 = x0

        self.model = model
        self.Ts = Ts

        self.state = BILBO_2D_State.as_state(self.x0)

        A, B, C, D = self._getLinearModel()
        system_continuous = control.StateSpace(A, B, C, D, remove_useless_states=False)
        self.system = control.c2d(system_continuous, Ts)

    # === METHODS ======================================================================================================
    def polePlacement(self, poles: list[float] | np.ndarray, apply_poles_to_system: bool = True) -> np.ndarray:
        poles = np.asarray(poles)

        K_discrete = np.asarray(control.place(self.system.A, self.system.B, np.exp(poles * self.Ts)))

        if apply_poles_to_system:
            self.system = control.StateSpace((self.system.A - self.system.B @ K_discrete), self.system.B,
                                             self.system.C, self.system.D, self.Ts, remove_useless_states=False)

            self.K = K_discrete

        return K_discrete

    # ------------------------------------------------------------------------------------------------------------------
    def setState(self, state: BILBO_2D_State | np.ndarray | list):
        self.state = BILBO_2D_State.as_state(state)

    # ------------------------------------------------------------------------------------------------------------------
    def simulate(self, input: list[BILBO_2D_Input],
                 reset: bool = True,
                 x0: BILBO_2D_State = None,
                 include_zero_step: bool = True) -> list[BILBO_2D_State]:

        input = listToStateList(input, BILBO_2D_Input)
        state_list = []

        if x0 is not None:
            self.state = BILBO_2D_State.as_state(x0)
        elif reset:
            self.state = copy.deepcopy(self.x0)

        if include_zero_step:
            state_list.append(self.state)

        for inp_i in input:
            self.step(inp_i)
            state_list.append(self.state)

        return state_list

    # ------------------------------------------------------------------------------------------------------------------
    def step(self, input: BILBO_2D_Input):
        self.state = self._dynamics(self.state, input)

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        self.state = copy.deepcopy(self.x0)

    # === PRIVATE METHODS ==============================================================================================
    def _dynamics(self, state: BILBO_2D_State, input: BILBO_2D_Input) -> BILBO_2D_State:
        new_state = self.system.A @ state.asarray() + self.system.B @ input.asarray()
        return BILBO_2D_State.fromarray(new_state)

    # ------------------------------------------------------------------------------------------------------------------
    def _getLinearModel(self):
        g = 9.81
        model = self.model
        C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
        V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2
        D_22 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * 2 * model.c_alpha / model.r_w
        D_21 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * 2 * model.c_alpha / model.r_w ** 2
        C_11 = model.m_b ** 2 * model.l ** 2
        D_12 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * 2 * model.c_alpha
        D_11 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - model.m_b * model.l * 2 * model.c_alpha / model.r_w

        A = np.array([
            [0, 1, 0, 0],
            [0, -D_11 / V_1, -C_11 * g / V_1, D_12 / V_1],
            [0, 0, 0, 1],
            [0, D_21 / V_1, C_21 * g / V_1, -D_22 / V_1]
        ])

        B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l
        B_2 = model.m_b * model.l / model.r_w + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2

        B = np.array([
            [0],
            [B_1 / V_1],
            [0],
            [-B_2 / V_1]
        ])
        C = np.array([[0, 0, 1, 0]])
        D = 0
        return A, B, C, D


# ======================================================================================================================
class BILBO_Dynamics_2D:
    x0: BILBO_2D_State = BILBO_2D_State(s=0, v=0, theta=0, theta_dot=0)

    K: np.ndarray = None
    state: BILBO_2D_State = None

    model: BilboModel
    Ts: float

    # === INIT =========================================================================================================
    def __init__(self, model: BilboModel, Ts=DEFAULT_SAMPLE_TIME, x0: BILBO_2D_State = None):
        if x0 is not None:
            self.x0 = x0

        self.model = model
        self.Ts = Ts

        self.state = BILBO_2D_State.as_state(self.x0)

    # === METHODS ======================================================================================================
    def setState(self, state: BILBO_2D_State | np.ndarray | list):
        self.state = BILBO_2D_State.as_state(state)

    # ------------------------------------------------------------------------------------------------------------------
    def step(self, input: BILBO_2D_Input):
        self.state = self._dynamics(self.state, input)

    # ------------------------------------------------------------------------------------------------------------------
    def setStateFeedbackControl(self, K: np.ndarray):
        self.K = K

    # ------------------------------------------------------------------------------------------------------------------
    def simulate(self, input: list[BILBO_2D_Input] | np.ndarray,
                 reset: bool = True,
                 x0: BILBO_2D_State = None,
                 include_zero_step: bool = True) -> list[BILBO_2D_State]:

        if isinstance(input, list):
            input = listToStateList(input, BILBO_2D_Input)
        elif isinstance(input, np.ndarray):
            input = vectorToStateList(input, BILBO_2D_Input)
        else:
            raise TypeError('input must be a list or a numpy array')
        state_list = []

        if x0 is not None:
            self.state = BILBO_2D_State.as_state(x0)
        elif reset:
            self.state = copy.deepcopy(self.x0)

        if include_zero_step:
            state_list.append(self.state)

        for inp_i in input:
            self.step(inp_i)
            state_list.append(self.state)

        return state_list

    # ------------------------------------------------------------------------------------------------------------------
    def polePlacement(self, poles, apply_poles_to_system: bool = True):
        # For pole placement, we need to make a linear system first
        linear_dynamics = BILBO_Dynamics_2D_Linear(self.model, self.Ts)
        K = linear_dynamics.polePlacement(poles, apply_poles_to_system=False)

        if apply_poles_to_system:
            self.setStateFeedbackControl(K)
        return K

    # === PRIVATE METHODS ==============================================================================================
    def _dynamics(self, state: BILBO_2D_State, input: BILBO_2D_Input) -> BILBO_2D_State:
        g = 9.81
        s = state.s
        v = state.v
        theta = state.theta
        theta_dot = state.theta_dot

        if self.K is not None:
            u = input.asarray() - self.K @ state.asarray()
        else:
            u = input.asarray()

        model = self.model
        C_12 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l
        C_22 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
        C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
        V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2 * np.cos(theta) ** 2
        D_22 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha / model.r_w
        D_21 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha / model.r_w ** 2
        C_11 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
        D_12 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha
        D_11 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - 2 * model.m_b * model.l * np.cos(
            theta) * model.c_alpha / model.r_w
        B_2 = model.m_b * model.l / model.r_w * np.cos(
            theta) + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2
        B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l * np.cos(theta)
        C_31 = 2 * (model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta)
        C_32 = model.m_b * model.l
        D_33 = model.d_w ** 2 / (2 * model.r_w ** 2) * model.c_alpha
        V_2 = model.I_z + 2 * model.I_w + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2 - (
                model.I_z - model.I_x - model.m_b * model.l ** 2) * np.sin(theta) ** 2
        B_3 = model.d_w / (2 * model.r_w)
        C_13 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l + model.m_b * model.l * (
                model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta) ** 2
        C_23 = (model.m_b ** 2 * model.l ** 2 + (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_z - model.I_x - model.m_b * model.l ** 2)) * np.cos(theta)

        state_dot = np.zeros(len(state.asarray()))
        state_dot[0] = v
        state_dot[1] = (np.sin(theta) / V_1) * (-C_11 * g + C_12 * theta_dot ** 2) - (D_11 / V_1) * v + (
                D_12 / V_1) * theta_dot + (B_1 / V_1) * u[0] - model.tau_x * v
        state_dot[2] = theta_dot
        state_dot[3] = (np.sin(theta) / V_1) * (C_21 * g - C_22 * theta_dot ** 2) + (D_21 / V_1) * v - (
                D_22 / V_1) * theta_dot - (B_2 / V_1) * u[0] - model.tau_theta * theta_dot
        state_new = state.asarray() + state_dot * self.Ts
        return BILBO_2D_State.fromarray(state_new)


# ======================================================================================================================
# === BILBO 3D =========================================================================================================
@dataclasses.dataclass
class BILBO_3D_State_reduced(State):
    s: float
    v: float
    theta: float
    theta_dot: float
    psi: float
    psi_dot: float


@dataclasses.dataclass
class BILBO_3D_State(State):
    x: float
    y: float
    v: float
    theta: float
    theta_dot: float
    psi: float
    psi_dot: float


@dataclasses.dataclass
class BILBO_3D_Input(State):
    M_L: float
    M_R: float


# === BILBO DYNAMICS 3D LINEAR REDUCED =================================================================================
class BILBO_Dynamics_3D_Linear_reduced:
    x0: BILBO_3D_State_reduced = BILBO_3D_State_reduced(s=0, v=0, theta=0, theta_dot=0, psi=0, psi_dot=0)
    state: BILBO_3D_State_reduced = None
    K: np.ndarray = None

    system: control.StateSpace

    # === INIT =========================================================================================================
    def __init__(self, model: BilboModel, Ts=DEFAULT_SAMPLE_TIME, x0=None):
        if x0 is not None:
            self.x0 = x0

        self.model = model
        self.Ts = Ts

        self.state = BILBO_3D_State_reduced.as_state(self.x0)

        [A, B, C, D] = self._linearModelContinuous()
        self._system_continuous_uncontrolled = control.ss(A, B, C, D)
        self.system = control.c2d(self._system_continuous_uncontrolled, Ts)

    # === METHODS ======================================================================================================
    def eigenstructureAssignment(self, poles: list | np.ndarray = None,
                                 eigenvectors: list | np.ndarray = None,
                                 apply_poles_to_system: bool = True):

        if poles is None:
            poles = BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES

        if eigenvectors is None:
            eigenvectors = BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS

        poles = np.asarray(poles)

        # K = lib_control.eigenstructure_assignment(self._system_continuous_uncontrolled.A,
        #                                           self._system_continuous_uncontrolled.B,
        #                                           np.exp(poles * self.Ts), eigenvectors)

        K = lib_control.eigenstructure_assignment(self._system_continuous_uncontrolled.A,
                                                  self._system_continuous_uncontrolled.B,
                                                  poles, eigenvectors)

        if apply_poles_to_system:
            self.system = control.StateSpace((self.system.A - self.system.B @ K), self.system.B,
                                             self.system.C, self.system.D, self.Ts, remove_useless_states=False)

            self.K = K
        return K

    # === PRIVATE METHODS ==============================================================================================
    def _linearModelContinuous(self):
        g = 9.81
        model = self.model
        C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
        V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2
        D_22 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * 2 * model.c_alpha / model.r_w
        D_21 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * 2 * model.c_alpha / model.r_w ** 2
        C_11 = model.m_b ** 2 * model.l ** 2
        D_12 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * 2 * model.c_alpha
        D_11 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - model.m_b * model.l * 2 * model.c_alpha / model.r_w
        D_33 = model.d_w ** 2 / (2 * model.r_w ** 2) * model.c_alpha
        V_2 = model.I_z + 2 * model.I_w + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2
        A = np.array([
            [0, 1, 0, 0, 0, 0],
            [0, -D_11 / V_1, -C_11 * g / V_1, D_12 / V_1, 0, 0],
            [0, 0, 0, 1, 0, 0],
            [0, D_21 / V_1, C_21 * g / V_1, -D_22 / V_1, 0, 0],
            [0, 0, 0, 0, 0, 1],
            [0, 0, 0, 0, 0, -D_33 / V_2]
        ])
        B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l
        B_2 = model.m_b * model.l / model.r_w + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2
        B_3 = model.d_w / (2 * model.r_w)
        B = np.array([
            [0, 0],
            [B_1 / V_1, B_1 / V_1],
            [0, 0],
            [-B_2 / V_1, -B_2 / V_1],
            [0, 0],
            [-B_3 / V_2, B_3 / V_2]
        ])
        C = np.array([[0, 0, 1, 0, 0, 0]])
        D = [0, 0]
        return A, B, C, D


# === BILBO DYNAMICS 3D LINEAR =========================================================================================
class BILBO_Dynamics_3D_Linear:
    x0: BILBO_3D_State = BILBO_3D_State(x=0, y=0, v=0, theta=0, theta_dot=0, psi=0, psi_dot=0)
    state: BILBO_3D_State = None
    K: np.ndarray = None

    # === INIT =========================================================================================================
    def __init__(self, model: BilboModel, Ts=DEFAULT_SAMPLE_TIME, x0=None):
        if x0 is not None:
            self.x0 = x0

        self.model = model
        self.Ts = Ts
        self.state = BILBO_3D_State.as_state(self.x0)

        A, B, C, D = self._linear_model()
        system_continuous_uncontrolled = control.ss(A, B, C, D)
        self.system = control.c2d(system_continuous_uncontrolled, Ts)

    # === METHODS ======================================================================================================
    def eigenstructureAssignment(self, poles: list | np.ndarray, eigenvectors: list | np.ndarray,
                                 apply_poles_to_system: bool = True):

        if not len(poles) == 6:
            raise ValueError(
                "The number of poles must be 6, "
                "since we use the reduced dynamics to calculate the eigenstructure assignment.")

        # Make the reduced dynamics system
        reduced_dynamics = BILBO_Dynamics_3D_Linear_reduced(self.model, Ts=self.Ts)
        K = reduced_dynamics.eigenstructureAssignment(poles, eigenvectors, apply_poles_to_system=apply_poles_to_system)
        K = np.hstack((np.zeros((2, 1)), K))

        if apply_poles_to_system:
            self.K = K
            self.system = control.StateSpace((self.system.A - self.system.B @ K), self.system.B,
                                             self.system.C, self.system.D, self.Ts, remove_useless_states=False)
        return K

    # ------------------------------------------------------------------------------------------------------------------
    def setState(self, state: BILBO_3D_State | np.ndarray | list):
        self.state = BILBO_3D_State.as_state(state)

    # ------------------------------------------------------------------------------------------------------------------
    def simulate(self, input: list[BILBO_3D_Input],
                 reset: bool = True,
                 x0: BILBO_3D_State = None,
                 include_zero_step: bool = True) -> list[BILBO_3D_State]:

        input = listToStateList(input, BILBO_3D_Input)
        state_list = []

        if x0 is not None:
            self.state = BILBO_3D_State.as_state(x0)
        elif reset:
            self.state = copy.deepcopy(self.x0)

        if include_zero_step:
            state_list.append(self.state)

        for inp_i in input:
            self.step(inp_i)
            state_list.append(self.state)

        return state_list

    # ------------------------------------------------------------------------------------------------------------------
    def step(self, input: BILBO_3D_Input):
        self.state = self._dynamics(self.state, input)

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        self.state = copy.deepcopy(self.x0)

    # === PRIVATE METHODS ==============================================================================================
    def _dynamics(self, state: BILBO_3D_State, input: BILBO_3D_Input):
        new_state = self.system.A @ state.asarray() + self.system.B @ input.asarray()
        return BILBO_3D_State.fromarray(new_state)

    # ------------------------------------------------------------------------------------------------------------------
    def _linear_model(self):
        g = 9.81
        model = self.model
        # Compute common terms from the original 3D linear model.
        C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
        V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2
        D_22 = ((
                        model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * 2 * model.c_alpha / model.r_w)
        D_21 = ((
                        model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * 2 * model.c_alpha / model.r_w ** 2)
        C_11 = model.m_b ** 2 * model.l ** 2
        D_12 = ((
                        model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * 2 * model.c_alpha)
        D_11 = ((
                        model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - model.m_b * model.l * 2 * model.c_alpha / model.r_w)
        D_33 = model.d_w ** 2 / (2 * model.r_w ** 2) * model.c_alpha
        V_2 = model.I_z + 2 * model.I_w + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2

        # Linearize the kinematic equations about (v0, psi0).
        cos_psi0 = np.cos(self.x0.psi)
        sin_psi0 = np.sin(self.x0.psi)

        # Construct A matrix with state ordering: [x, y, v, theta, theta_dot, psi, psi_dot]
        A = np.zeros((7, 7))
        # Kinematics for x and y:
        # x_dot = v*cos(psi) ≈ cos(psi0)*delta_v - v0*sin(psi0)*delta_psi
        A[0, 2] = cos_psi0
        A[0, 5] = -self.x0.v * sin_psi0
        # y_dot = v*sin(psi) ≈ sin(psi0)*delta_v + v0*cos(psi0)*delta_psi
        A[1, 2] = sin_psi0
        A[1, 5] = self.x0.v * cos_psi0

        # The remaining dynamics are taken from the original model.
        # v dynamics (originally row 1 for state 'v'):
        A[2, 2] = -D_11 / V_1
        A[2, 3] = -C_11 * g / V_1
        A[2, 4] = D_12 / V_1
        # Theta kinematics: theta_dot = dot(theta)
        A[3, 4] = 1.0
        # Theta_dot dynamics (originally row 3):
        A[4, 2] = D_21 / V_1
        A[4, 3] = C_21 * g / V_1
        A[4, 4] = -D_22 / V_1
        # Psi kinematics: psi_dot = dot(psi)
        A[5, 6] = 1.0
        # Psi_dot dynamics (originally row 5):
        A[6, 6] = -D_33 / V_2

        # Construct B matrix with ordering: [x, y, v, theta, theta_dot, psi, psi_dot]
        B = np.zeros((7, 2))
        # Only the internal dynamics (v, theta_dot, psi_dot) are actuated.
        # v dynamics (originally row 1):
        B[2, :] = [((model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l) / V_1,
                   ((model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l) / V_1]
        # Theta_dot dynamics (originally row 3):
        B[4, :] = [
            - (model.m_b * model.l / model.r_w + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) / V_1,
            - (model.m_b * model.l / model.r_w + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) / V_1]
        # Psi_dot dynamics (originally row 5):
        B[6, :] = [- model.d_w / (2 * model.r_w) / V_2,
                   model.d_w / (2 * model.r_w) / V_2]

        # Define the output matrix. Here we choose to output theta (state index 3), for example.
        C = np.array([[0, 0, 0, 1, 0, 0, 0]])
        D = np.array([0, 0])

        return A, B, C, D


class BILBO_Dynamics_3D:
    x0: BILBO_3D_State = BILBO_3D_State(x=0, y=0, v=0, theta=0, theta_dot=0, psi=0, psi_dot=0)
    state: BILBO_3D_State = None
    K: np.ndarray = None

    # === INIT =========================================================================================================
    def __init__(self, model: BilboModel, Ts=DEFAULT_SAMPLE_TIME, x0=None):
        if x0 is not None:
            self.x0 = x0

        self.model = model
        self.Ts = Ts
        self.state = BILBO_3D_State.as_state(self.x0)
        self.logger = Logger("BILBO Dynamics 3D", "DEBUG")

    # === METHODS ======================================================================================================
    def eigenstructureAssignment(self, poles: list | np.ndarray,
                                 eigenvectors: list | np.ndarray,
                                 apply_poles_to_system: bool = True):

        # Make the reduced linear system dynamics
        reduced_linear_dynamics = BILBO_Dynamics_3D_Linear_reduced(self.model, Ts=self.Ts)
        K = reduced_linear_dynamics.eigenstructureAssignment(poles, eigenvectors, apply_poles_to_system=False)

        K = np.hstack((np.zeros((2, 1)), K))

        if apply_poles_to_system:
            self.K = K

        self.logger.debug(f"Eigenstructure assignment: {K}")
        return K

    # ------------------------------------------------------------------------------------------------------------------
    def step(self, input: BILBO_3D_Input):
        self.state, dynamics_input = self._dynamics(self.state, input)
        return self.state, dynamics_input

    # ------------------------------------------------------------------------------------------------------------------
    def simulate(self, input: list | np.ndarray,
                 reset: bool = True,
                 x0: BILBO_3D_State = None,
                 include_zero_step: bool = True) -> tuple[list[BILBO_3D_State], list[BILBO_3D_Input]]:
        input = listToStateList(input, BILBO_3D_Input)
        state_list = []
        input_list = []
        if x0 is not None:
            self.state = BILBO_3D_State.as_state(x0)
        elif reset:
            self.state = copy.deepcopy(self.x0)

        if include_zero_step:
            state_list.append(self.state)
            input_list.append([0, 0])

        for inp_i in input:
            state, dynamics_input = self.step(inp_i)
            state_list.append(self.state)
            input_list.append(dynamics_input)
        return state_list, input_list

    # ------------------------------------------------------------------------------------------------------------------
    def setState(self, state: BILBO_3D_State | np.ndarray | list):
        self.state = BILBO_3D_State.as_state(state)

    # === PRIVATE METHODS ==============================================================================================
    def _dynamics(self, state: BILBO_3D_State, input: BILBO_3D_Input):
        g = 9.81
        x = state.x
        y = state.y
        v = state.v
        theta = state.theta
        theta_dot = state.theta_dot
        psi = state.psi
        psi_dot = state.psi_dot

        if self.K is not None:
            u = input.asarray() - self.K @ state.asarray()
        else:
            u = input.asarray()

        model = self.model
        C_12 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l
        C_22 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
        C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
        V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2 * np.cos(theta) ** 2
        D_22 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha / model.r_w
        D_21 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha / model.r_w ** 2
        C_11 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
        D_12 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha
        D_11 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - 2 * model.m_b * model.l * np.cos(
            theta) * model.c_alpha / model.r_w
        B_2 = model.m_b * model.l / model.r_w * np.cos(
            theta) + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2
        B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l * np.cos(theta)
        C_31 = 2 * (model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta)
        C_32 = model.m_b * model.l
        D_33 = model.d_w ** 2 / (2 * model.r_w ** 2) * model.c_alpha
        V_2 = model.I_z + 2 * model.I_w + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2 - (
                model.I_z - model.I_x - model.m_b * model.l ** 2) * np.sin(theta) ** 2
        B_3 = model.d_w / (2 * model.r_w)
        C_13 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l + model.m_b * model.l * (
                model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta) ** 2
        C_23 = (model.m_b ** 2 * model.l ** 2 + (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_z - model.I_x - model.m_b * model.l ** 2)) * np.cos(theta)

        state_dot = np.zeros(len(state.asarray()))
        state_dot[0] = v * np.cos(psi)
        state_dot[1] = v * np.sin(psi)
        state_dot[2] = (np.sin(theta) / V_1) * (-C_11 * g + C_12 * theta_dot ** 2 + C_13 * psi_dot ** 2) - (
                D_11 / V_1) * v + (D_12 / V_1) * theta_dot + (B_1 / V_1) * (u[0] + u[1]) - model.tau_x * v
        state_dot[3] = theta_dot
        state_dot[4] = (np.sin(theta) / V_1) * (C_21 * g - C_22 * theta_dot ** 2 - C_23 * psi_dot ** 2) + (
                D_21 / V_1) * v - (D_22 / V_1) * theta_dot - (B_2 / V_1) * (
                               u[0] + u[1]) - model.tau_theta * theta_dot
        state_dot[5] = psi_dot
        state_dot[6] = (np.sin(theta) / V_2) * (C_31 * theta_dot * psi_dot - C_32 * psi_dot * v) - (
                D_33 / V_2) * psi_dot - (B_3 / V_2) * (u[0] - u[1])

        new_state = state.asarray() + state_dot * self.Ts
        return BILBO_3D_State.fromarray(new_state), u


# ======================================================================================================================
def input3Dto2D(input: list[BILBO_3D_Input | np.ndarray | list]) -> list[BILBO_2D_Input]:
    input = listToStateList(input, BILBO_3D_Input)
    input_2D = []

    for inp_i in input:
        input_2D.append(BILBO_2D_Input(inp_i.M_L + inp_i.M_R))
    return input_2D


# ======================================================================================================================
def input2Dto3D(input: list[BILBO_2D_Input | np.ndarray | list]) -> list[BILBO_3D_Input]:
    input = listToStateList(input, BILBO_2D_Input)
    input_3D = []

    for inp_i in input:
        input_3D.append(BILBO_3D_Input(inp_i.M / 2, inp_i.M / 2))

    return input_3D


# ======================================================================================================================
# === BILBO AGENT ======================================================================================================
class BILBO_DynamicAgent(Agent):
    mode: BILBO_Control_Mode

    state: BILBO_3D_State
    input: BILBO_3D_Input
    dynamics: BILBO_Dynamics_3D | BILBO_Dynamics_3D_Linear

    K: np.ndarray = None

    _enable_state_constraints: bool = True

    # === INIT =========================================================================================================
    def __init__(self, agent_id: str, model: BilboModel, Ts=DEFAULT_SAMPLE_TIME, x0=None,
                 dynamics: type = BILBO_Dynamics_3D):
        super().__init__(agent_id)
        self.model = model
        self.Ts = Ts

        self.dynamics = dynamics(model, Ts=Ts, x0=x0)
        self.input = BILBO_3D_Input(M_L=0, M_R=0)

        self.mode = BILBO_Control_Mode.BALANCING

        # self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._controller)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.DYNAMICS].addAction(self._dynamics)

    # === PROPERTIES ===================================================================================================
    @property
    def state(self):
        return self.dynamics.state

    @state.setter
    def state(self, value):
        self.dynamics.state = BILBO_3D_State.as_state(value)

    @property
    def input(self):
        return self._input

    @input.setter
    def input(self, value):
        self._input = BILBO_3D_Input.as_state(value)

    # === METHODS ======================================================================================================
    def simulate(self, input: list[BILBO_3D_Input],
                 reset: bool = True,
                 x0: BILBO_3D_State = None,
                 include_zero_step: bool = True) -> list[BILBO_3D_State]:
        return self.dynamics.simulate(input, reset, x0, include_zero_step)

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self, x0: BILBO_3D_State = None):
        self.dynamics.setState(x0)

    # ------------------------------------------------------------------------------------------------------------------
    def setMode(self, mode: BILBO_Control_Mode):
        self.mode = mode

    # ------------------------------------------------------------------------------------------------------------------
    def eigenstructureAssignment(self, poles: list | np.ndarray,
                                 eigenvectors: list | np.ndarray):
        self.K = self.dynamics.eigenstructureAssignment(poles, eigenvectors, apply_poles_to_system=False)

    # ------------------------------------------------------------------------------------------------------------------

    # === PRIVATE METHODS ==============================================================================================
    def _controller(self) -> BILBO_3D_Input:

        if self.mode == BILBO_Control_Mode.OFF:
            controller_input = BILBO_3D_Input(M_L=0, M_R=0)
        elif self.mode == BILBO_Control_Mode.BALANCING:
            controller_input = self.input.asarray() - self.K @ self.dynamics.state.asarray()
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

        return BILBO_3D_Input.as_state(controller_input)

    # ------------------------------------------------------------------------------------------------------------------
    def _dynamics(self):
        controller_input = self._controller()
        # Skip dynamics integration when lying on the ground in OFF mode —
        # gravity would re-introduce tiny velocities each step otherwise.
        if not (self.mode == BILBO_Control_Mode.OFF and getattr(self, '_ground_contact', False)):
            self.dynamics.step(controller_input)
        self._calculateStateConstraints()

    # ------------------------------------------------------------------------------------------------------------------
    def _calculateStateConstraints(self):
        if not self._enable_state_constraints:
            return

        # --- dt & params ---
        dt = float(getattr(self.dynamics, "Ts", getattr(self, "Ts", DEFAULT_SAMPLE_TIME)))
        max_pitch = float(self.model.max_pitch)
        tol_enter = 1e-4
        tol_exit = 2e-4

        # contact tunables (feel free to expose in BilboModel)
        e_n = float(getattr(self.model, "restitution_n", 0.0))  # normal restitution
        k_t = float(getattr(self.model, "tangent_decay", 12.0))  # 1/s, v decay
        k_r = float(getattr(self.model, "yaw_decay", 10.0))  # 1/s, psi_dot decay

        # use slightly larger stick thresholds to kill drift
        v_stick = float(getattr(self.model, "v_stick", 5e-3))  # m/s
        w_stick = float(getattr(self.model, "w_stick", 5e-3))  # rad/s

        # --- initialize persistent stuff ---
        if not hasattr(self, "_ground_contact"):
            self._ground_contact = False
        if not hasattr(self, "_prev_pose"):
            self._prev_pose = {
                "x": float(self.state.x),
                "y": float(self.state.y),
                "psi": float(self.state.psi),
            }

        # --- read state ---
        x = float(self.state.x)
        y = float(self.state.y)
        v = float(self.state.v)
        theta = float(self.state.theta)
        theta_dot = float(self.state.theta_dot)
        psi = float(self.state.psi)
        psi_dot = float(self.state.psi_dot)

        # contact detection (hysteresis)
        side = 1.0 if theta >= 0.0 else -1.0
        depth = abs(theta) - max_pitch
        approaching = (theta_dot * side) > 0.0

        if depth > 0.0 or (abs(abs(theta) - max_pitch) <= tol_enter and approaching):
            self._ground_contact = True
        elif abs(abs(theta) - max_pitch) > tol_exit and not approaching:
            self._ground_contact = False

        sticking = False

        if self._ground_contact:
            # project onto contact manifold
            theta = side * max_pitch

            # normal velocity treatment
            if approaching:
                theta_dot = -e_n * theta_dot
            if abs(theta_dot) < w_stick:
                theta_dot = 0.0

            # tangential exponential decay (dt-aware)
            decay_t = math.exp(-k_t * dt)
            decay_r = math.exp(-k_r * dt)
            v *= decay_t
            psi_dot *= decay_r

            # stick if small
            if abs(v) < v_stick:
                v = 0.0
            if abs(psi_dot) < w_stick:
                psi_dot = 0.0

            sticking = (v == 0.0 and psi_dot == 0.0)

            # *** key anti-drift step: rollback pose when sticking ***
            if sticking:
                x = self._prev_pose["x"]
                y = self._prev_pose["y"]
                psi = self._prev_pose["psi"]

        else:
            # if we notice penetration outside contact, resolve once
            if depth > 0.0:
                theta = side * max_pitch
                if approaching:
                    theta_dot = -e_n * theta_dot

        # write back
        self.state.x = x
        self.state.y = y
        self.state.v = v
        self.state.theta = theta
        self.state.theta_dot = theta_dot
        self.state.psi = psi
        self.state.psi_dot = psi_dot

        # update snapshot for next step (must be after any rollback)
        self._prev_pose = {"x": x, "y": y, "psi": psi}


# ======================================================================================================================
def example_2D():
    dynamics_2d_linear = BILBO_Dynamics_2D_Linear(model=DEFAULT_BILBO_MODEL, Ts=DEFAULT_SAMPLE_TIME)
    dynamics_2d_linear.polePlacement(poles=BILBO_2D_POLES)

    step_input = -0.0 * np.ones(200)
    states_linear = dynamics_2d_linear.simulate(step_input,
                                                x0=BILBO_2D_State(s=0, v=0, theta=np.pi / 2, theta_dot=0),
                                                include_zero_step=True)
    theta_linear = [state.theta for state in states_linear]

    dynamics_2d = BILBO_Dynamics_2D(model=DEFAULT_BILBO_MODEL, Ts=DEFAULT_SAMPLE_TIME)
    dynamics_2d.polePlacement(poles=BILBO_2D_POLES)

    states = dynamics_2d.simulate(step_input,
                                  x0=BILBO_2D_State(s=0, v=0, theta=np.pi / 2, theta_dot=0),
                                  include_zero_step=True)
    theta = [state.theta for state in states]

    plt.plot(theta_linear, label='linear')
    plt.plot(theta, label='nonlinear')
    plt.grid()
    plt.legend()
    plt.show()


def example_3D():
    bilbo_3d_dynamics = BILBO_Dynamics_3D(model=DEFAULT_BILBO_MODEL, Ts=DEFAULT_SAMPLE_TIME)
    bilbo_3d_dynamics.eigenstructureAssignment(poles=BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
                                               eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS)

    input_2d: np.ndarray = -0.0 * np.ones(200)
    input_3d = input2Dto3D(input_2d)

    states = bilbo_3d_dynamics.simulate(input=input_3d,
                                        x0=BILBO_3D_State(x=0, y=0, v=0, theta=np.pi / 2, theta_dot=0, psi=0,
                                                          psi_dot=0),
                                        include_zero_step=True)
    theta = [state.theta for state in states]

    bilbo_3d_dynamics_linear = BILBO_Dynamics_3D_Linear(model=DEFAULT_BILBO_MODEL, Ts=DEFAULT_SAMPLE_TIME)
    bilbo_3d_dynamics_linear.eigenstructureAssignment(poles=BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
                                                      eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS)

    states_linear = bilbo_3d_dynamics_linear.simulate(input=input_3d,
                                                      x0=BILBO_3D_State(x=0, y=0, v=0, theta=np.pi / 2, theta_dot=0,
                                                                        psi=0,
                                                                        psi_dot=0),
                                                      include_zero_step=True)

    theta_linear = [state.theta for state in states_linear]

    plt.plot(theta, label='nonlinear')
    plt.plot(theta_linear, label='linear')
    plt.grid()
    plt.legend()
    plt.show()


if __name__ == '__main__':
    example_3D()
