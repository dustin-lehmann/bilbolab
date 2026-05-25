import copy
import dataclasses
import math
from typing import TypeVar, Generic, Type, Optional
import numpy as np
from core.utils.states import State
from simulation.core.agents import Agent
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS

DEFAULT_SAMPLE_TIME = 0.05


# === MODEL ============================================================================================================
@dataclasses.dataclass
class FRODO_Model:
    d_wheels: float  # track width [m]


FRODO_MODEL_STANDARD = FRODO_Model(d_wheels=0.15)


# === INPUTS ===========================================================================================================
@dataclasses.dataclass
class FRODO_Input(State):
    v: float = 0  # linear speed [m/s]
    psi_dot: float = 0  # yaw rate [rad/s]


@dataclasses.dataclass
class FRODO_Input_LR(State):
    left: float = 0  # left track linear speed [m/s]
    right: float = 0  # right track linear speed [m/s]


TInput = TypeVar("TInput", FRODO_Input, FRODO_Input_LR)


# === State ==================================================================================
@dataclasses.dataclass
class FRODO_State(State):
    x: float
    y: float
    v: float
    psi: float
    psi_dot: float


# === Dynamics ===============================================================================
class FRODO_Dynamics(Generic[TInput]):
    x0: FRODO_State | None = None
    state: FRODO_State
    input_type: Type[TInput]

    # === INIT =========================================================================================================
    def __init__(
            self,
            model: FRODO_Model = FRODO_MODEL_STANDARD,
            Ts: float = DEFAULT_SAMPLE_TIME,
            x0: Optional[FRODO_State] = None,
            input_type: Type[TInput] = FRODO_Input,
    ):

        if x0 is None:
            x0 = FRODO_State(0, 0, 0, 0, 0)

        self.x0 = x0

        if model.d_wheels <= 0:
            raise ValueError("d_wheels must be > 0")
        self.model = model
        self.Ts = Ts
        self.state = FRODO_State.as_state(self.x0)
        self.input_type = input_type

    # === METHODS ======================================================================================================
    def setState(self, state: FRODO_State | np.ndarray | list) -> None:
        self.state = FRODO_State.as_state(state)

    # ------------------------------------------------------------------------------------------------------------------
    def step(self, u: TInput | np.ndarray | list) -> FRODO_State:
        # normalize to the chosen input dataclass
        u_norm = self.input_type.as_state(u)
        # compute next state
        self.state = self._dynamics(self.state, u_norm)
        return copy.deepcopy(self.state)

    # === PRIVATE METHODS ==============================================================================================
    def _dynamics(self, s: FRODO_State, u: TInput) -> FRODO_State:
        s_next = copy.deepcopy(s)

        if self.input_type is FRODO_Input:
            v = u.v
            psi_dot = u.psi_dot
        elif self.input_type is FRODO_Input_LR:
            vL = u.left
            vR = u.right
            v = 0.5 * (vR + vL)
            psi_dot = (vR - vL) / self.model.d_wheels
        else:
            raise TypeError("Unsupported input type")

        # Forward Euler unicycle kinematics
        s_next.x += self.Ts * v * np.cos(s.psi)
        s_next.y += self.Ts * v * np.sin(s.psi)
        s_next.psi += self.Ts * psi_dot
        # optional: wrap heading
        s_next.psi = (s_next.psi + np.pi) % (2 * np.pi) - np.pi

        s_next.v = v
        s_next.psi_dot = psi_dot
        return s_next


# === FRODO DYNAMIC AGENT ==============================================================================================
class FRODO_DynamicAgent(Generic[TInput], Agent):
    dynamics: FRODO_Dynamics[TInput]
    input_type: Type[TInput]

    input: TInput

    # === INIT =========================================================================================================
    def __init__(self,
                 agent_id: str,
                 Ts: float = DEFAULT_SAMPLE_TIME,
                 model: FRODO_Model = FRODO_MODEL_STANDARD,
                 input_type: Type[TInput] = FRODO_Input,
                 *args, **kwargs):
        super().__init__(agent_id, *args, **kwargs)

        self.dynamics = FRODO_Dynamics[TInput](Ts=Ts, model=model, input_type=input_type)
        self.input_type = input_type
        self._input = self.input_type()

        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.DYNAMICS].addAction(self._dynamics)

    # === PROPERTIES ===================================================================================================
    @property
    def state(self) -> FRODO_State:
        return self.dynamics.state

    @state.setter
    def state(self, value: FRODO_State | np.ndarray | list) -> None:
        self.dynamics.setState(value)

    @property
    def input(self) -> TInput:
        return self._input

    @input.setter
    def input(self, value: TInput | np.ndarray | list) -> None:
        self._input = self.input_type.as_state(value)

    @property
    def position(self):
        return np.asarray([self.state.x, self.state.y])

    # === METHODS ======================================================================================================
    def step(self, u: TInput | np.ndarray | list) -> FRODO_State:
        return self.dynamics.step(u)

    # ------------------------------------------------------------------------------------------------------------------
    def setInput(self, u: TInput | np.ndarray | list) -> None:
        self.input = self.input_type.as_state(u)

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self, x0: FRODO_State | np.ndarray | list = None) -> None:
        if x0 is not None:
            self.dynamics.x0 = FRODO_State.as_state(x0)
        self.dynamics.state = copy.deepcopy(self.dynamics.x0)
        self.input = self.input_type()

    # === PRIVATE METHODS ==============================================================================================

    def _dynamics(self):
        self.dynamics.step(self.input)
