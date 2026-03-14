from __future__ import annotations

import dataclasses
import enum
import numpy as np
import qmt

from core.utils.control_lib.lib_control.estimation.data_fusion import covariance_intersection
from core.utils.control_lib.lib_control.orientation import align_angle
from core.utils.logging_utils import Logger

INDEX_X = 0
INDEX_Y = 1
INDEX_PSI = 2


def get_rotation_matrix(psi: float):
    R = np.array([
        [np.cos(psi), -np.sin(psi), 0, ],
        [np.sin(psi), np.cos(psi), 0, ],
        [0, 0, 1, ],
    ])
    return R


def dR_dpsi_times_vec(psi: float, z: np.ndarray) -> np.ndarray:
    """
    Compute (d/dpsi) [ R(psi) * z ] for 3x1 z = [z_x, z_y, z_psi].
    Only x,y depend on psi; psi row is zero. For 2x2 R(psi) = [[c,-s],[s,c]]:
      dR/dpsi = [[-s, -c],
                 [ c, -s]]
    """
    c, s = np.cos(psi), np.sin(psi)
    J2 = np.array([[-s, -c],
                   [c, -s]])
    xy = J2 @ z[:2]
    out = np.array([xy[0], xy[1], 0.0])
    return out


class UpdateAlgorithm(enum.StrEnum):
    EKF = "EKF"
    CI = "CI"


@dataclasses.dataclass
class AlgorithmAgentState:
    x: float = 0.0
    y: float = 0.0
    psi: float = 0.0

    def as_array(self):
        return np.array([self.x, self.y, self.psi])

    @staticmethod
    def from_array(array):
        return AlgorithmAgentState(array[0], array[1], array[2])


# ======================================================================================================================
@dataclasses.dataclass
class AlgorithmAgentInput:
    v: float = 0.0
    psi_dot: float = 0.0

    def as_array(self):
        return np.array([self.v, self.psi_dot])

    @classmethod
    def from_array(cls, array):
        new_input = cls()
        new_input.v = array[0]
        new_input.psi_dot = array[1]
        return new_input


# ======================================================================================================================
@dataclasses.dataclass
class AlgorithmAgentMeasurement:
    agent_from: AlgorithmAgent
    agent_to: AlgorithmAgent
    measurement: np.ndarray
    covariance: np.ndarray


# ======================================================================================================================
@dataclasses.dataclass
class AlgorithmAgent:
    id: str
    Ts: float
    state: AlgorithmAgentState
    covariance: np.ndarray
    is_anchor: bool = False
    static_covariance: float = 1e-3
    input: AlgorithmAgentInput = dataclasses.field(default_factory=AlgorithmAgentInput)
    measurements: list[AlgorithmAgentMeasurement] = dataclasses.field(default_factory=list)

    # ----------------------------------------------------------------------------------------------------------------------
    def prediction(self):

        if self.is_anchor:
            self.state.psi = qmt.wrapToPi(self.state.psi)  # optional small drift handling
            return self.state

        Ts = self.Ts
        new_state = AlgorithmAgentState()
        new_state.x = self.state.x + Ts * self.input.v * np.cos(self.state.psi)
        new_state.y = self.state.y + Ts * self.input.v * np.sin(self.state.psi)
        new_state.psi = self.state.psi + Ts * self.input.psi_dot

        self.state = new_state

        F = self.get_dynamics_jacobian()
        R = self.input_covariance_from_input(self.input, self.is_anchor)
        G = self.get_input_jacobian()
        Q = self.static_covariance * Ts * np.eye(3)
        self.covariance = F @ self.covariance @ F.T + G @ R @ G.T + Q

        self.state.psi = qmt.wrapToPi(self.state.psi)
        return new_state

    # ----------------------------------------------------------------------------------------------------------------------
    def get_input_jacobian(self):
        jacobian = np.array([
            [self.Ts * np.cos(self.state.psi), 0],
            [self.Ts * np.sin(self.state.psi), 0],
            [0, self.Ts],
        ])
        return jacobian

    # ----------------------------------------------------------------------------------------------------------------------
    def get_dynamics_jacobian(self):
        F = np.array([
            [1.0, 0.0, -self.Ts * self.input.v * np.sin(self.state.psi)],
            [0.0, 1.0, self.Ts * self.input.v * np.cos(self.state.psi)],
            [0.0, 0.0, 1.0],
        ])
        return F

    # ----------------------------------------------------------------------------------------------------------------------
    def input_covariance_from_input(self, u: AlgorithmAgentInput, is_anchor: bool = False):
        if is_anchor:
            # Anchors: no input-driven process noise at all
            return np.zeros((2, 2))

        v = abs(u.v)
        w = abs(u.psi_dot)

        # Example: linear growth model
        sigma_v0, kv = 0.005, 2  # std_v = 0.005 + 0.10*|v|
        sigma_w0, kw = 0.002, 0.20  # std_w = 0.002 + 0.10*|w|

        # sigma_v0, kv = 0.005, 0.60  # std_v = 0.005 + 0.10*|v|
        # sigma_w0, kw = 0.002, 0.60  # std_w = 0.002 + 0.10*|w|


        # sigma_v0, kv = 0.01, 3 # std_v = 0.005 + 0.10*|v|
        # sigma_w0, kw = 0.01, 3  # std_w = 0.002 + 0.10*|w|

        std_v = sigma_v0 + kv * v
        std_w = sigma_w0 + kw * w
        return np.diag([std_v ** 2, std_w ** 2])

    # ----------------------------------------------------------------------------------------------------------------------
    def update_from_estimated_state(self, estimated_state, covariance, update_method: UpdateAlgorithm):

        assert update_method in UpdateAlgorithm, f"Invalid update method: {update_method}"

        estimated_state = np.array(estimated_state, dtype=float, copy=True)

        estimated_state[INDEX_PSI] = align_angle(self.state.psi, float(estimated_state[INDEX_PSI]))

        if update_method == UpdateAlgorithm.EKF:
            # K = self.covariance @ np.linalg.inv(self.covariance + covariance)

            S = self.covariance + covariance
            K = np.linalg.solve(S.T, self.covariance.T).T  # P S^{-1}

            innovation = estimated_state - self.state.as_array()
            innovation[INDEX_PSI] = qmt.wrapToPi(innovation[INDEX_PSI])
            new_estimate = self.state.as_array() + K @ innovation
            new_estimate[INDEX_PSI] = qmt.wrapToPi(new_estimate[INDEX_PSI])
            new_covariance = (np.eye(3) - K) @ self.covariance
            new_covariance = 0.5 * (new_covariance + new_covariance.T)

        elif update_method == UpdateAlgorithm.CI:
            new_estimate, new_covariance = covariance_intersection(
                mean1=self.state.as_array(),
                covariance1=self.covariance,
                mean2=estimated_state,
                covariance2=covariance,
            )

            new_estimate[INDEX_PSI] = qmt.wrapToPi(new_estimate[INDEX_PSI])

        else:
            raise ValueError("Invalid update method")

        self.state = AlgorithmAgentState.from_array(new_estimate)
        self.covariance = new_covariance
        self.covariance = 0.5 * (self.covariance + self.covariance.T)


# ----------------------------------------------------------------------------------------------------------------------
def get_estimated_state(agent, measurement: AlgorithmAgentMeasurement) -> tuple[np.ndarray, np.ndarray]:
    agent_from = measurement.agent_from
    agent_to = measurement.agent_to

    # psi_meas_time = agent_from.state.psi - agent_from.Ts * agent_from.input.psi_dot
    # Rg = get_rotation_matrix(psi_meas_time)
    # Jpsi = dR_dpsi_times_vec(psi_meas_time, measurement.measurement).reshape(3,1)


    Rg = get_rotation_matrix(agent_from.state.psi)
    Rz = Rg @ measurement.covariance @ Rg.T
    variance_psi_from = float(agent_from.covariance[INDEX_PSI, INDEX_PSI])

    Jpsi = dR_dpsi_times_vec(agent_from.state.psi, measurement.measurement).reshape(3, 1)  # 3x1
    Cpsi = (Jpsi @ Jpsi.T) * variance_psi_from

    if agent is measurement.agent_to:
        estimated_state = agent_from.state.as_array() + Rg @ measurement.measurement
        covariance = agent_from.covariance + Rz + Cpsi

    elif agent is measurement.agent_from:
        estimated_state = agent_to.state.as_array() - Rg @ measurement.measurement
        covariance = agent_to.covariance + Rz + Cpsi
    else:
        raise ValueError("Invalid agent for measurement")

    estimated_state[INDEX_PSI] = qmt.wrapToPi(estimated_state[INDEX_PSI])
    return estimated_state, covariance


# ======================================================================================================================

class DistributedAlgorithmState(enum.StrEnum):
    RUNNING = 'RUNNING'
    STOPPED = 'STOPPED'


class DistributedAlgorithm:
    agents: dict[str, AlgorithmAgent]
    step: int = 0

    def __init__(self, Ts: float, update_method: UpdateAlgorithm = UpdateAlgorithm.EKF):
        self.Ts = Ts
        self.update_method = update_method
        self.agents = {}
        self.logger = Logger('DistributedAlgorithm', 'DEBUG')

    # ------------------------------------------------------------------------------------------------------------------
    def initialize(self, agents: list[AlgorithmAgent]):

        self.agents = {}
        for agent in agents:
            self.agents[agent.id] = agent

        self.logger.info(
            f"Initialized distributed algorithm with {len(agents)} agents: {[agent.id for agent in self.agents.values()]}")

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def prediction(self):
        for agent in self.agents.values():
            agent.prediction()
    # ------------------------------------------------------------------------------------------------------------------
    def update(self):

        # 2. Collect the measurements
        all_measurements = {}
        # Make a measurement dict for each agent with all the estimated states and covariances it is involved in
        for agent_id in self.agents.keys():
            all_measurements[agent_id] = []

        for agent in self.agents.values():
            for measurement in agent.measurements:
                agent_from = measurement.agent_from
                agent_to = measurement.agent_to

                # From the measurement, we can get two estimated states: from measurer and the measured agent
                agent_from_estimated_state, agent_from_covariance = get_estimated_state(agent, measurement)
                agent_to_estimated_state, agent_to_covariance = get_estimated_state(measurement.agent_to, measurement)

                all_measurements[agent_from.id].append((agent_from_estimated_state, agent_from_covariance))
                all_measurements[agent_to.id].append((agent_to_estimated_state, agent_to_covariance))

        # 3. Update each agent with the measurements
        for agent in self.agents.values():
            agent_measurements = all_measurements[agent.id]
            for meas in agent_measurements:
                agent.update_from_estimated_state(estimated_state=meas[0],
                                                  covariance=meas[1],
                                                  update_method=self.update_method, )



        self.step += 1


