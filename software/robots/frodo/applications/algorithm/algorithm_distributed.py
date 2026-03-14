from __future__ import annotations

import dataclasses
import enum
import numpy as np
import qmt

from applications.FRODO.algorithm.algorithm import AlgorithmAgent, AlgorithmAgentState, INDEX_PSI, \
    AlgorithmAgentMeasurement, get_rotation_matrix, dR_dpsi_times_vec, LocalizationAlgorithm
from core.utils.control_lib.lib_control.estimation.data_fusion import covariance_intersection
from core.utils.control_lib.lib_control.orientation import align_angle
from core.utils.logging_utils import Logger


class DistributedUpdateType(enum.StrEnum):
    EKF = "EKF"
    CI = "CI"


@dataclasses.dataclass(frozen=True)
class DistributedAgent_Sample:
    id: str
    state: AlgorithmAgentState
    covariance: np.ndarray
    input: np.ndarray
    measurements: list[AlgorithmAgentMeasurement]
    is_anchor: bool


class DistributedAgent(AlgorithmAgent):

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
        Q = self.settings.static_noise_floor * Ts * np.eye(3)
        self.covariance = F @ self.covariance @ F.T + G @ R @ G.T + Q

        self.covariance = 0.5 * (self.covariance + self.covariance.T)

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
    def update_from_estimated_state(self, estimated_state, covariance, update_method: DistributedUpdateType):

        assert isinstance(update_method, DistributedUpdateType), f"Invalid update method: {update_method}"

        estimated_state = np.array(estimated_state, dtype=float, copy=True)

        estimated_state[INDEX_PSI] = align_angle(self.state.psi, float(estimated_state[INDEX_PSI]))

        if update_method == DistributedUpdateType.EKF:
            S = self.covariance + covariance
            K = np.linalg.solve(S.T, self.covariance.T).T  # P S^{-1}

            innovation = estimated_state - self.state.as_array()
            innovation[INDEX_PSI] = qmt.wrapToPi(innovation[INDEX_PSI])
            new_estimate = self.state.as_array() + K @ innovation
            new_estimate[INDEX_PSI] = qmt.wrapToPi(new_estimate[INDEX_PSI])
            new_covariance = (np.eye(3) - K) @ self.covariance
            new_covariance = 0.5 * (new_covariance + new_covariance.T)

        elif update_method == DistributedUpdateType.CI:
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
    def get_sample(self):
        return DistributedAgent_Sample(id=self.id,
                                       state=self.state,
                                       covariance=self.covariance,
                                       input=self.input.as_array(),
                                       measurements=self.measurements,
                                       is_anchor=self.is_anchor)


# ----------------------------------------------------------------------------------------------------------------------
def get_estimated_state(agent, measurement: AlgorithmAgentMeasurement) -> tuple[np.ndarray, np.ndarray]:
    agent_from = measurement.agent_from
    agent_to = measurement.agent_to

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

@dataclasses.dataclass
class DistributedAlgorithm_Sample:
    step: int
    agents: dict[str, DistributedAgent_Sample]


class DistributedAlgorithm(LocalizationAlgorithm):
    agents: dict[str, DistributedAgent]

    # === INIT =========================================================================================================
    def __init__(self, Ts: float, update_method: DistributedUpdateType = DistributedUpdateType.EKF):
        super().__init__(Ts)

        self.logger = Logger('DistributedAlgorithm', 'DEBUG')
        self.update_method = update_method

    # === METHODS ======================================================================================================
    def initialize(self, agents: list[DistributedAgent]):

        self.reset()

        for agent in agents:
            self.agents[agent.id] = agent

        self.logger.info(
            f"Initialized distributed algorithm with {len(agents)} agents: "
            f"{[agent.id for agent in self.agents.values()]}")

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        self.agents = {}
        self.step = 0

    # ------------------------------------------------------------------------------------------------------------------
    def prediction(self):
        for agent in self.agents.values():
            agent.prediction()

    # ------------------------------------------------------------------------------------------------------------------
    def correction(self):
        # 1. Collect the measurements
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

        # 2. Update each agent with the measurements
        for agent in self.agents.values():
            agent_measurements = all_measurements[agent.id]
            for meas in agent_measurements:
                agent.update_from_estimated_state(estimated_state=meas[0],
                                                  covariance=meas[1],
                                                  update_method=self.update_method, )

        self.step += 1

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> DistributedAlgorithm_Sample:
        return DistributedAlgorithm_Sample(step=self.step,
                                           agents={agent.id: agent.get_sample() for agent in self.agents.values()})
