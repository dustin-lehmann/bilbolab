import dataclasses
from typing import Optional

import numpy as np

from robots.frodo.applications.algorithm.algorithm import LocalizationAlgorithm, AlgorithmAgent, augment_state, \
    augment_covariance, INDEX_COS, INDEX_SIN, INDEX_X, INDEX_Y, AlgorithmAgentMeasurement, \
    augment_measurement_covariance, augment_measurement, get_state_from_augmented, get_covariance_from_augmented, \
    augment_state_array, AlgorithmAgentState
from core.utils.logging_utils import Logger

AUGMENTED_STATE_DIM = 4

DEBUG = False


# === CENTRALIZED AGENT ================================================================================================
@dataclasses.dataclass
class CentralizedAgent_Sample:
    id: str
    state: AlgorithmAgentState
    covariance: np.ndarray
    input: np.ndarray
    measurements: list[AlgorithmAgentMeasurement]
    is_anchor: bool


class CentralizedAgent(AlgorithmAgent):
    index: int | None = None

    def prediction(self) -> np.ndarray:
        # augmented_state = augment_state(self.state)
        # state_hat_augmented_direct = np.array([
        #     augmented_state[INDEX_X] + self.Ts * self.input.v * augmented_state[INDEX_COS],
        #     augmented_state[INDEX_Y] + self.Ts * self.input.v * augmented_state[INDEX_SIN],
        #     augmented_state[INDEX_SIN] + self.Ts * self.input.psi_dot * augmented_state[INDEX_COS],
        #     augmented_state[INDEX_COS] - self.Ts * self.input.psi_dot * augmented_state[INDEX_SIN]
        # ])

        # Predict the state
        state_hat = np.array([
            self.state.x + self.Ts * np.cos(self.state.psi) * self.input.v,
            self.state.y + self.Ts * np.sin(self.state.psi) * self.input.v,
            self.state.psi + self.Ts * self.input.psi_dot,
        ])

        state_hat_augmented = augment_state_array(state_hat)

        # psi = self.state.psi
        # psi_hat = state_hat[2]
        # # Predict the covariance (non-augmented)
        #
        # F = self.get_dynamics_jacobian_non_augmented()
        # R = self.input_covariance_from_input(self.input, self.is_anchor)
        # G = self.get_input_jacobian_non_augmented()
        # Q = self.settings.static_noise_floor * self.Ts * np.eye(3)
        # new_covariance = F @ self.covariance @ F.T + G @ R @ G.T + Q
        #
        # # predict the covariance (augmented)
        # F = self.get_dynamics_jacobian()
        # R = self.input_covariance_from_input(self.input, self.is_anchor)
        # G = self.get_input_jacobian()
        # Q = self.settings.static_noise_floor * self.Ts * np.eye(3)
        #
        # new_covariance_augmented = F @ augment_covariance(self.covariance,
        #                                                   psi) @ F.T + G @ R @ G.T + augment_covariance(Q,
        #                                                                                                            psi)
        #
        # new_covariance_deaugmented = get_covariance_from_augmented(new_covariance_augmented, psi_hat)
        # if np.linalg.norm(new_covariance-new_covariance_deaugmented) > 1e1:
        #     pass

        return state_hat_augmented

    def get_dynamics_jacobian(self):
        F = np.array([
            [1, 0, 0, self.Ts * self.input.v],
            [0, 1, self.Ts * self.input.v, 0],
            [0, 0, 1, self.Ts * self.input.psi_dot],
            [0, 0, -self.Ts * self.input.psi_dot, 1]
        ])
        return F

    # ----------------------------------------------------------------------------------------------------------------------
    def get_dynamics_jacobian_non_augmented(self):
        F = np.array([
            [1.0, 0.0, -self.Ts * self.input.v * np.sin(self.state.psi)],
            [0.0, 1.0, self.Ts * self.input.v * np.cos(self.state.psi)],
            [0.0, 0.0, 1.0],
        ])
        return F

    def get_input_jacobian(self):
        state_augmented = augment_state(self.state)
        G = np.array([
            [self.Ts * state_augmented[INDEX_COS], 0.0],
            [self.Ts * state_augmented[INDEX_SIN], 0.0],
            [0.0, self.Ts * state_augmented[INDEX_COS]],
            [0.0, -1.0 * self.Ts * state_augmented[INDEX_SIN]],
        ])
        return G

    # ----------------------------------------------------------------------------------------------------------------------
    def get_input_jacobian_non_augmented(self):
        jacobian = np.array([
            [self.Ts * np.cos(self.state.psi), 0],
            [self.Ts * np.sin(self.state.psi), 0],
            [0, self.Ts],
        ])
        return jacobian

    # ----------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> CentralizedAgent_Sample:
        return CentralizedAgent_Sample(
            id=self.id,
            state=get_state_from_augmented(self.state.as_array()),
            input=self.input.as_array(),
            measurements=self.measurements,
            covariance=get_covariance_from_augmented(self.covariance, self.state.psi),
            is_anchor=self.is_anchor
        )


@dataclasses.dataclass
class CentralizedAlgorithm_Sample:
    step: int
    agents: dict[str, CentralizedAgent_Sample]


class CentralizedAlgorithm(LocalizationAlgorithm):
    state: Optional[np.ndarray]
    covariance: Optional[np.ndarray]

    state_prediction: Optional[np.ndarray]
    covariance_prediction: Optional[np.ndarray]

    agents: dict[str, CentralizedAgent]
    step: int = 0

    # === INIT =========================================================================================================
    def __init__(self, Ts: float):
        super().__init__(Ts)
        self.state = None
        self.covariance = None
        self.state_prediction = None
        self.covariance_prediction = None
        self.agents = {}
        self.logger = Logger('CentralizedAlgorithm', 'INFO')

    # === METHODS ======================================================================================================
    def initialize(self, agents: list[CentralizedAgent]):
        self.reset()

        # Build the agent dictionary
        for index, agent in enumerate(agents):
            self.agents[agent.id] = agent
            agent.index = index

        # Build the state
        self.state = np.zeros(len(agents) * AUGMENTED_STATE_DIM)

        for index, agent in enumerate(agents):
            self.state[self._get_agent_slice(index)] = augment_state(agent.state)

        # Build the state covariance
        self.covariance = np.zeros((len(agents) * AUGMENTED_STATE_DIM, len(agents) * AUGMENTED_STATE_DIM))
        for index, agent in enumerate(agents):
            self.covariance[self._get_agent_slice(agent), self._get_agent_slice(agent)] = augment_covariance(
                agent.covariance,
                agent.state.psi)
        self.logger.info(
            f"Algorithm initialized with {len(agents)} agents: {[agent.id for agent in self.agents.values()]}")

        self.step = 0

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        self.state = None
        self.covariance = None
        self.state_prediction = None
        self.covariance_prediction = None
        self.step = 0
        self.agents = {}

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> CentralizedAlgorithm_Sample:
        return CentralizedAlgorithm_Sample(step=self.step,
                                           agents={agent.id: agent.get_sample() for agent in self.agents.values()})

    # ------------------------------------------------------------------------------------------------------------------
    def prediction(self):
        self.state_prediction, self.covariance_prediction = self._prediction()

    # ------------------------------------------------------------------------------------------------------------------
    def correction(self):

        if self.state_prediction is None or self.covariance_prediction is None:
            return

        # Step 1: Extract the measurements
        measurements = self._extract_measurements_from_agents()

        if len(measurements) > 0:

            # Calculate the measurement jacobian
            H = self._get_measurement_jacobian(measurements)

            # Build the measurement covariance
            W = self._get_measurement_covariance(measurements)

            W = 0.5 * (W + W.T)

            # Calculate the Kalman Gain
            # K = self.covariance_prediction @ H.T @ np.linalg.inv(H @ self.covariance_prediction @ H.T + W)

            # more stable version
            S = H @ self.covariance_prediction @ H.T + W
            L = np.linalg.cholesky(0.5 * (S + S.T))  # ensure symmetry
            K = self.covariance_prediction @ H.T @ np.linalg.solve(L.T, np.linalg.solve(L, np.eye(L.shape[0])))

            # Build the measurement vector
            y = self._get_measurement_vector(measurements)

            # Build the predicted measurement vector
            y_est = self._get_measurement_prediction(measurements)

            # Calculate the difference
            diff = y - y_est

            # Correction
            new_state = self.state_prediction + K @ diff
            new_covariance = (np.eye(len(self.agents) * AUGMENTED_STATE_DIM) - K @ H) @ self.covariance_prediction @ (
                    np.eye(len(self.agents) * AUGMENTED_STATE_DIM) - K @ H).T + K @ W @ K.T

        else:
            new_state = self.state_prediction
            new_covariance = self.covariance_prediction

        self.state = new_state
        self.covariance = new_covariance

        self.covariance = 0.5 * (self.covariance + self.covariance.T)

        # Write the state and covariance back to the agents
        for i in range(len(self.agents)):
            agent = self._get_agent_by_index(i)
            if agent is None:
                raise ValueError(f"Agent with index {i} does not exist.")

            agent.state = get_state_from_augmented(self.state[self._get_agent_slice(agent)])
            agent.covariance = get_covariance_from_augmented(
                self.covariance[self._get_agent_slice(agent), self._get_agent_slice(agent)], agent.state.psi)

            agent.covariance = 0.5 * (agent.covariance + agent.covariance.T)

        if (self.step % 10) == 0 or self.step == 1:
            self.logger.debug("--------------------------------")
            self.logger.debug(f"Step: {self.step}")
            for agent in self.agents.values():
                self.logger.debug(
                    f"{agent.id}: \t x: {agent.state.x:.3f} \t y: {agent.state.y:.3f} \t psi: {agent.state.psi:.2f} \t "
                    f"Cov: {np.linalg.norm(agent.covariance, 'fro'):.1f}")

        self.step += 1

    # === PRIVATE METHODS ==============================================================================================
    def _prediction(self) -> tuple[np.ndarray, np.ndarray]:

        # Predict the state
        x_hat = np.zeros(len(self.agents) * AUGMENTED_STATE_DIM)

        # Predict the state of each agent
        for i in range(len(self.agents)):
            agent = self._get_agent_by_index(i)

            if agent is None:
                raise ValueError(
                    f"Agent with index {i} does not exist. There seems to be something wrong in the algorithm")

            x_hat_agent = agent.prediction()
            r = max(np.sqrt(float(x_hat_agent[INDEX_SIN]) ** 2 + float(x_hat_agent[INDEX_COS]) ** 2), 1e-12)
            x_hat_agent[INDEX_SIN] /= r
            x_hat_agent[INDEX_COS] /= r
            x_hat[self._get_agent_slice(i)] = x_hat_agent
            # x_hat[self._get_agent_slice(i)] = agent.prediction()

        # Calculate the dynamics jacobian
        F = self._get_dynamics_jacobian()

        Q = np.zeros_like(self.covariance)
        q_floor = 1e-12

        for i in range(len(self.agents)):
            agent = self._get_agent_by_index(i)
            G = agent.get_input_jacobian()
            Ru = agent.input_covariance_from_input(agent.input, agent.is_anchor)
            Qi = G @ Ru @ G.T
            if not agent.is_anchor:
                Qi += augment_covariance(agent.settings.static_noise_floor * self.Ts * np.eye(3), agent.state.psi)
                Qi += q_floor * np.eye(AUGMENTED_STATE_DIM)

            Q[self._get_agent_slice(agent), self._get_agent_slice(agent)] = Qi

        P_hat = F @ self.covariance @ F.T + Q

        P_hat = 0.5 * (P_hat + P_hat.T)
        return x_hat, P_hat

    # ------------------------------------------------------------------------------------------------------------------
    def _get_dynamics_jacobian(self):
        F = np.zeros((len(self.agents) * AUGMENTED_STATE_DIM, len(self.agents) * AUGMENTED_STATE_DIM))

        for i in range(len(self.agents)):
            agent = self._get_agent_by_index(i)
            if agent is None:
                raise ValueError(f"Agent with index {i} does not exist.")

            F[self._get_agent_slice(agent), self._get_agent_slice(agent)] = agent.get_dynamics_jacobian()

        return F

    # ------------------------------------------------------------------------------------------------------------------
    def _extract_measurements_from_agents(self) -> list[AlgorithmAgentMeasurement]:
        measurements = []
        for i in range(len(self.agents)):
            agent = self._get_agent_by_index(i)
            if agent is None:
                raise ValueError(f"Agent with index {i} does not exist.")

            if len(agent.measurements) > 0:
                measurements.extend(agent.measurements)

        return measurements

    # ------------------------------------------------------------------------------------------------------------------
    def _get_measurement_jacobian(self, measurements: list[AlgorithmAgentMeasurement]) -> np.ndarray:
        H = np.zeros((AUGMENTED_STATE_DIM * len(measurements), len(self.agents) * AUGMENTED_STATE_DIM))

        for i, measurement in enumerate(measurements):
            agent_from = measurement.agent_from
            agent_to = measurement.agent_to

            source_prediction_augmented = self.state_prediction[self._get_agent_slice(agent_from)]
            target_prediction_augmented = self.state_prediction[self._get_agent_slice(agent_to)]

            H_source = self._get_measurement_jacobian_for_two_agents(source_prediction_augmented,
                                                                     target_prediction_augmented,
                                                                     reference_agent='source')
            H_target = self._get_measurement_jacobian_for_two_agents(source_prediction_augmented,
                                                                     target_prediction_augmented,
                                                                     reference_agent='target')

            r = i * AUGMENTED_STATE_DIM

            H[r:r + AUGMENTED_STATE_DIM, self._get_agent_slice(agent_from)] = H_source
            H[r:r + AUGMENTED_STATE_DIM, self._get_agent_slice(agent_to)] = H_target

        return H

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _get_measurement_jacobian_for_two_agents(source_agent_state_augmented: np.ndarray,
                                                 target_agent_state_augmented: np.ndarray,
                                                 reference_agent: str):
        x1, y1, s1, c1 = source_agent_state_augmented[INDEX_X], source_agent_state_augmented[INDEX_Y], \
            source_agent_state_augmented[INDEX_SIN], source_agent_state_augmented[INDEX_COS]
        x2, y2, s2, c2 = target_agent_state_augmented[INDEX_X], target_agent_state_augmented[INDEX_Y], \
            target_agent_state_augmented[INDEX_SIN], target_agent_state_augmented[INDEX_COS]
        if reference_agent == 'source':
            return np.array([
                [-c1, -s1, y2 - y1, x2 - x1],
                [s1, -c1, -x2 + x1, y2 - y1],
                [0, 0, -c2, s2],
                [0, 0, s2, c2],
            ])
        elif reference_agent == 'target':
            return np.array([
                [c1, s1, 0, 0],
                [-s1, c1, 0, 0],
                [0, 0, c1, -s1],
                [0, 0, s1, c1],
            ])
        else:
            raise ValueError(f"Invalid reference agent: {reference_agent}")

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _get_measurement_covariance(measurements: list[AlgorithmAgentMeasurement]) -> np.ndarray:
        W = np.zeros((len(measurements) * AUGMENTED_STATE_DIM, len(measurements) * AUGMENTED_STATE_DIM))

        for i, measurement in enumerate(measurements):
            W_meas = augment_measurement_covariance(measurement)
            W[i * AUGMENTED_STATE_DIM:(i + 1) * AUGMENTED_STATE_DIM,
            i * AUGMENTED_STATE_DIM:(i + 1) * AUGMENTED_STATE_DIM] = W_meas

        return W

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _get_measurement_vector(measurements: list[AlgorithmAgentMeasurement]) -> np.ndarray:
        y = np.zeros(len(measurements) * AUGMENTED_STATE_DIM)

        for i, measurement in enumerate(measurements):
            y[i * AUGMENTED_STATE_DIM:(i + 1) * AUGMENTED_STATE_DIM] = augment_measurement(measurement)

        return y

    # ------------------------------------------------------------------------------------------------------------------
    def _get_measurement_prediction(self, measurements: list[AlgorithmAgentMeasurement]) -> np.ndarray:
        y_est = np.zeros(len(measurements) * AUGMENTED_STATE_DIM)

        for i, measurement in enumerate(measurements):
            src_aug = self.state_prediction[self._get_agent_slice(measurement.agent_from)]
            tgt_aug = self.state_prediction[self._get_agent_slice(measurement.agent_to)]
            predicted_measurement = self._get_measurement_prediction_for_two_agents(src_aug, tgt_aug)

            y_est[i * AUGMENTED_STATE_DIM:(i + 1) * AUGMENTED_STATE_DIM] = predicted_measurement.flatten()

        return y_est

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _get_measurement_prediction_for_two_agents(src_aug: np.ndarray, tgt_aug: np.ndarray) -> np.ndarray:

        x1, y1, s1, c1 = src_aug[INDEX_X], src_aug[INDEX_Y], src_aug[INDEX_SIN], src_aug[INDEX_COS]
        x2, y2, s2, c2 = tgt_aug[INDEX_X], tgt_aug[INDEX_Y], tgt_aug[INDEX_SIN], tgt_aug[INDEX_COS]

        return np.array([
            [c1 * (x2 - x1) + s1 * (y2 - y1)],
            [-s1 * (x2 - x1) + c1 * (y2 - y1)],
            [s2 * c1 - c2 * s1],
            [c2 * c1 + s2 * s1],
        ])

    # ------------------------------------------------------------------------------------------------------------------
    def _get_agent_slice(self, agent: AlgorithmAgent | CentralizedAgent | int) -> slice:
        if isinstance(agent, int):
            idx = agent  # keep a copy
            agent = self._get_agent_by_index(idx)
            if agent is None:
                raise ValueError(f"Agent with index {idx} does not exist.")
        if agent.index is None:
            raise ValueError(f"Agent with id {agent.id} does not have an index.")

        return slice(agent.index * AUGMENTED_STATE_DIM, (agent.index + 1) * AUGMENTED_STATE_DIM)

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _get_agent_index(agent: CentralizedAgent | AlgorithmAgent) -> int:
        return agent.index

    # ------------------------------------------------------------------------------------------------------------------
    def _get_agent_by_index(self, index: int) -> CentralizedAgent | None:
        for agent in self.agents.values():
            if agent.index == index:
                return agent
        return None
