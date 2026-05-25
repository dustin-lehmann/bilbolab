# centralized.py

from typing import Optional

import numpy as np

from robots.frodo.applications.algorithm.algorithm import (
    LocalizationAlgorithm,
    AlgorithmAgent,
    AlgorithmAgentMeasurement,
    augment_measurement,
    augment_measurement_covariance,
    INDEX_X,
    INDEX_Y,
    INDEX_PSI,
)
from core.utils.logging_utils import Logger

STATE_DIM = 3  # [x, y, psi]
MEAS_DIM = 4  # [dx_body, dy_body, sin(psi_rel), cos(psi_rel)]


# === CENTRALIZED AGENT ================================================================================================
class CentralizedAgent(AlgorithmAgent):
    """
    Holds its own local model & helpers. The centralized filter builds F, G and Q by
    assembling each agent's Jacobians into block-diagonal global matrices.
    """
    index: int | None = None

    # --- Motion model (non-augmented) -------------------------------------------------------------------------------
    def prediction(self) -> np.ndarray:
        """
        One-step open-loop state prediction for this agent (non-augmented).
        Returns a 3-vector [x_hat, y_hat, psi_hat].
        """
        Ts = self.Ts
        v = self.input.v
        w = self.input.psi_dot

        x_hat = self.state.x + Ts * v * np.cos(self.state.psi)
        y_hat = self.state.y + Ts * v * np.sin(self.state.psi)
        psi_hat = self.state.psi + Ts * w

        return np.array([x_hat, y_hat, psi_hat])

    def get_dynamics_jacobian(self) -> np.ndarray:
        """
        ∂f/∂x for non-augmented state [x, y, psi].
        """
        Ts = self.Ts
        v = self.input.v
        psi = self.state.psi

        F = np.array([
            [1.0, 0.0, -Ts * v * np.sin(psi)],
            [0.0, 1.0, Ts * v * np.cos(psi)],
            [0.0, 0.0, 1.0],
        ])
        return F

    def get_input_jacobian(self) -> np.ndarray:
        """
        ∂f/∂u for non-augmented state; u = [v, psi_dot].
        """
        Ts = self.Ts
        psi = self.state.psi

        G = np.array([
            [Ts * np.cos(psi), 0.0],
            [Ts * np.sin(psi), 0.0],
            [0.0, Ts],
        ])
        return G


# === CENTRALIZED FILTER ===============================================================================================
class CentralizedAlgorithm(LocalizationAlgorithm):
    """
    Centralized EKF over stacked non-augmented states:
        X = [x1, y1, psi1, x2, y2, psi2, ..., xN, yN, psiN]^T

    Only the correction step uses sin/cos(psi) "augmentation" internally to build:
      - the predicted measurement vector h(X)
      - the measurement Jacobian H = ∂h/∂X (via chain rule)
      - the measurement covariance W (via your existing augmentation utility)
    """
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

        self.logger = Logger('CentralizedAlgorithm', 'INFO')

    # === PUBLIC API ===================================================================================================
    def initialize(self, agents: list[CentralizedAgent]):
        """
        Build the stacked state and covariance directly in [x, y, psi].
        """
        self.agents = {}

        # Assign indices & register
        for idx, agent in enumerate(agents):
            agent.index = idx
            self.agents[agent.id] = agent

        n = len(self.agents)
        self.state = np.zeros(n * STATE_DIM)

        # Initialize the stacked state
        for i in range(n):
            agent = self._get_agent_by_index(i)
            self.state[self._get_agent_slice(i)] = np.array(
                [agent.state.x, agent.state.y, agent.state.psi], dtype=float
            )

        # Initialize the stacked covariance (block-diagonal copy of each agent's 3x3 covariance)
        P = np.zeros((n * STATE_DIM, n * STATE_DIM))
        for i in range(n):
            agent = self._get_agent_by_index(i)
            P[self._get_agent_slice(i), self._get_agent_slice(i)] = np.array(agent.covariance, dtype=float)

        # Symmetrize for numerical hygiene
        self.covariance = 0.5 * (P + P.T)

        self.logger.info(
            f"Algorithm initialized with {n} agents: {[agent.id for agent in self.agents.values()]}"
        )
        self.step = 1

    # ------------------------------------------------------------------------------------------------------------------
    def prediction(self):
        """
        EKF time-update over [x, y, psi] stacked state.
        """
        x_hat, P_hat = self._prediction()
        self.state_prediction = x_hat
        self.covariance_prediction = P_hat

    # ------------------------------------------------------------------------------------------------------------------
    def correction(self):
        """
        EKF measurement-update. Uses augmentation only inside this method to construct:
          - y (measured, 4 per measurement)
          - h(X_hat) (predicted)
          - H (Jacobian wrt non-augmented state, via chain rule)
          - W (measurement cov, via your augmentation utility)
        """
        if self.state_prediction is None or self.covariance_prediction is None:
            return

        measurements = self._extract_measurements_from_agents()
        if len(measurements) == 0:
            # No measurements -> carry prediction forward
            self.state = self.state_prediction
            self.covariance = self.covariance_prediction
            self._write_back_to_agents()
            self._maybe_log_step()
            self.step += 1
            return

        # Build measurement pieces
        H = self._get_measurement_jacobian(measurements)
        W = self._get_measurement_covariance(measurements)
        W = 0.5 * (W + W.T)

        # Innovation covariance (stabilized)
        S = H @ self.covariance_prediction @ H.T + W
        L = np.linalg.cholesky(0.5 * (S + S.T))
        S_inv = np.linalg.solve(L.T, np.linalg.solve(L, np.eye(L.shape[0])))

        K = self.covariance_prediction @ H.T @ S_inv

        y = self._get_measurement_vector(measurements)  # stacked 4*M
        y_hat = self._get_measurement_prediction(measurements)  # stacked 4*M

        innovation = y - y_hat

        # State & covariance update (Joseph form for robustness)
        I = np.eye(self.state_prediction.shape[0])
        x_new = self.state_prediction + K @ innovation
        P_new = (I - K @ H) @ self.covariance_prediction @ (I - K @ H).T + K @ W @ K.T

        # Normalize angles (psi) after update
        x_new = self._wrap_all_heading_angles(x_new)

        self.state = x_new
        self.covariance = 0.5 * (P_new + P_new.T)

        # Push results back to agents
        self._write_back_to_agents()

        self._maybe_log_step()
        self.step += 1

    # === PRIVATE: PREDICTION ==========================================================================================
    def _prediction(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Build x̂ and P̂ with non-augmented blocks only.
        """
        n = len(self.agents)

        # Predict states per agent
        x_hat = np.zeros(n * STATE_DIM)
        for i in range(n):
            agent = self._get_agent_by_index(i)
            x_hat_i = agent.prediction()
            # wrap agent heading in the predicted vector
            x_hat_i[INDEX_PSI] = self._wrap_angle(float(x_hat_i[INDEX_PSI]))
            x_hat[self._get_agent_slice(i)] = x_hat_i

        # Build F and Q
        F = np.zeros((n * STATE_DIM, n * STATE_DIM))
        Q = np.zeros_like(self.covariance)
        q_floor = 1e-12  # tiny diagonal to help conditioning

        for i in range(n):
            agent = self._get_agent_by_index(i)

            # Local Jacobians
            Fi = agent.get_dynamics_jacobian()
            Gi = agent.get_input_jacobian()
            Ru = agent.input_covariance_from_input(agent.input, agent.is_anchor)

            # Process noise for this agent
            Qi = Gi @ Ru @ Gi.T
            if not agent.is_anchor:
                Qi += agent.settings.static_noise_floor * self.Ts * np.eye(STATE_DIM)
                Qi += q_floor * np.eye(STATE_DIM)

            sl = self._get_agent_slice(i)
            F[sl, sl] = Fi
            Q[sl, sl] = Qi

        P_hat = F @ self.covariance @ F.T + Q
        P_hat = 0.5 * (P_hat + P_hat.T)

        return x_hat, P_hat

    # === PRIVATE: MEASUREMENTS ========================================================================================
    def _extract_measurements_from_agents(self) -> list[AlgorithmAgentMeasurement]:
        measurements: list[AlgorithmAgentMeasurement] = []
        for i in range(len(self.agents)):
            agent = self._get_agent_by_index(i)
            if agent is None:
                raise ValueError(f"Agent with index {i} does not exist.")
            if len(agent.measurements) > 0:
                measurements.extend(agent.measurements)
        return measurements

    # ------------------------------------------------------------------------------------------------------------------
    def _get_measurement_vector(self, measurements: list[AlgorithmAgentMeasurement]) -> np.ndarray:
        """
        Stacks the *augmented* measurement vectors (4 per relative measurement).
        """
        y = np.zeros(len(measurements) * MEAS_DIM)
        for i, meas in enumerate(measurements):
            y[i * MEAS_DIM:(i + 1) * MEAS_DIM] = augment_measurement(meas)
        return y

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _get_measurement_covariance(measurements: list[AlgorithmAgentMeasurement]) -> np.ndarray:
        """
        Block-diagonal W with 4x4 augmented covariance per measurement.
        """
        W = np.zeros((len(measurements) * MEAS_DIM, len(measurements) * MEAS_DIM))
        for i, meas in enumerate(measurements):
            W_meas = augment_measurement_covariance(meas)
            r = i * MEAS_DIM
            W[r:r + MEAS_DIM, r:r + MEAS_DIM] = W_meas
        return W

    # ------------------------------------------------------------------------------------------------------------------
    def _get_measurement_prediction(self, measurements: list[AlgorithmAgentMeasurement]) -> np.ndarray:
        """
        h(X_hat): predicted *augmented* measurement for each relative constraint, stacked.
        Each measurement is defined in the *source* (agent_from) frame.
        """
        y_hat = np.zeros(len(measurements) * MEAS_DIM)

        for i, meas in enumerate(measurements):
            src = meas.agent_from
            tgt = meas.agent_to

            xs = self.state_prediction[self._get_agent_slice(src)]
            xt = self.state_prediction[self._get_agent_slice(tgt)]

            y_hat_block = self._predict_measurement_for_pair(xs, xt)  # (4,)
            y_hat[i * MEAS_DIM:(i + 1) * MEAS_DIM] = y_hat_block

        return y_hat

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _predict_measurement_for_pair(xs: np.ndarray, xt: np.ndarray) -> np.ndarray:
        """
        Given source and target local states (non-augmented), return the *augmented* predicted measurement:
            z = [dx_body, dy_body, sin(psi_t - psi_s), cos(psi_t - psi_s)]
        where [dx_body, dy_body] = R(psi_s)^T * ([x_t, y_t] - [x_s, y_s])
        """
        x1, y1, psi1 = float(xs[INDEX_X]), float(xs[INDEX_Y]), float(xs[INDEX_PSI])
        x2, y2, psi2 = float(xt[INDEX_X]), float(xt[INDEX_Y]), float(xt[INDEX_PSI])

        c1, s1 = np.cos(psi1), np.sin(psi1)
        c2, s2 = np.cos(psi2), np.sin(psi2)

        dx = x2 - x1
        dy = y2 - y1

        # Rotate delta into source frame
        dx_body = c1 * dx + s1 * dy
        dy_body = -s1 * dx + c1 * dy

        # Relative heading as sin/cos
        s_rel = s2 * c1 - c2 * s1
        c_rel = c2 * c1 + s2 * s1

        return np.array([dx_body, dy_body, s_rel, c_rel], dtype=float)

    # ------------------------------------------------------------------------------------------------------------------
    def _get_measurement_jacobian(self, measurements: list[AlgorithmAgentMeasurement]) -> np.ndarray:
        """
        Build H = ∂h/∂X for the stacked non-augmented state. We start from your augmented-form
        Jacobians and apply the chain rule:
            ds/dpsi =  cos(psi),   dc/dpsi = -sin(psi)

        For a single measurement (source s, target t), the 4x(3N) block has two non-zero
        4x3 sub-blocks (one per agent). The resulting derivatives are:

        For source (w.r.t [x1, y1, psi1]):
          row1: [-c1,  -s1,  c1*(y2 - y1) - s1*(x2 - x1)]
          row2: [ s1,  -c1,  c1*(-x2 + x1) - s1*(y2 - y1)]
          row3: [  0,    0,  -cos(psi2 - psi1)]
          row4: [  0,    0,   sin(psi2 - psi1)]

        For target (w.r.t [x2, y2, psi2]):
          row1: [ c1,   s1,   0]
          row2: [-s1,   c1,   0]
          row3: [  0,    0,   cos(psi2 - psi1)]
          row4: [  0,    0,  -sin(psi2 - psi1)]
        """
        n = len(self.agents)
        H = np.zeros((len(measurements) * MEAS_DIM, n * STATE_DIM))

        for i, meas in enumerate(measurements):
            src = meas.agent_from
            tgt = meas.agent_to

            xs = self.state_prediction[self._get_agent_slice(src)]
            xt = self.state_prediction[self._get_agent_slice(tgt)]

            x1, y1, psi1 = float(xs[INDEX_X]), float(xs[INDEX_Y]), float(xs[INDEX_PSI])
            x2, y2, psi2 = float(xt[INDEX_X]), float(xt[INDEX_Y]), float(xt[INDEX_PSI])

            dx = x2 - x1
            dy = y2 - y1

            c1, s1 = np.cos(psi1), np.sin(psi1)
            dpsi = psi2 - psi1
            c_rel = np.cos(dpsi)
            s_rel = np.sin(dpsi)

            # Source block (4x3)
            Hs = np.array([
                [-c1, -s1, c1 * (y2 - y1) - s1 * (x2 - x1)],
                [s1, -c1, c1 * (-x2 + x1) - s1 * (y2 - y1)],
                [0.0, 0.0, -c_rel],
                [0.0, 0.0, s_rel],
            ], dtype=float)

            # Target block (4x3)
            Ht = np.array([
                [c1, s1, 0.0],
                [-s1, c1, 0.0],
                [0.0, 0.0, c_rel],
                [0.0, 0.0, -s_rel],
            ], dtype=float)

            r = i * MEAS_DIM
            H[r:r + MEAS_DIM, self._get_agent_slice(src)] = Hs
            H[r:r + MEAS_DIM, self._get_agent_slice(tgt)] = Ht

        return H

    # === PRIVATE: STATE BOOKKEEPING ===================================================================================
    def _get_agent_slice(self, agent: CentralizedAgent | AlgorithmAgent | int) -> slice:
        """
        Slice for the agent's [x, y, psi] in the stacked vector/matrix.
        """
        if isinstance(agent, int):
            idx = agent
            agent = self._get_agent_by_index(idx)
            if agent is None:
                raise ValueError(f"Agent with index {idx} does not exist.")
        if agent.index is None:
            raise ValueError(f"Agent with id {agent.id} does not have an index.")

        start = agent.index * STATE_DIM
        return slice(start, start + STATE_DIM)

    @staticmethod
    def _get_agent_index(agent: CentralizedAgent | AlgorithmAgent) -> int:
        return agent.index

    def _get_agent_by_index(self, index: int) -> CentralizedAgent | None:
        for agent in self.agents.values():
            if agent.index == index:
                return agent
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _write_back_to_agents(self):
        """
        Push the centralized estimate back into each agent object.
        """
        for i in range(len(self.agents)):
            agent = self._get_agent_by_index(i)
            if agent is None:
                raise ValueError(f"Agent with index {i} does not exist.")

            sl = self._get_agent_slice(i)
            xi = self.state[sl]
            Pi = self.covariance[sl, sl]

            # Write state
            agent.state.x = float(xi[INDEX_X])
            agent.state.y = float(xi[INDEX_Y])
            agent.state.psi = float(self._wrap_angle(xi[INDEX_PSI]))

            # Write covariance (symmetrized)
            agent.covariance = 0.5 * (Pi + Pi.T)

    # ------------------------------------------------------------------------------------------------------------------
    def _wrap_all_heading_angles(self, x: np.ndarray) -> np.ndarray:
        """
        Wrap every psi component in the stacked state to [-pi, pi).
        """
        x = x.copy()
        for i in range(len(self.agents)):
            sl = self._get_agent_slice(i)
            x[sl.start + INDEX_PSI] = self._wrap_angle(x[sl.start + INDEX_PSI])
        return x

    @staticmethod
    def _wrap_angle(phi: float) -> float:
        """
        Wrap angle to [-pi, pi).
        """
        return (phi + np.pi) % (2.0 * np.pi) - np.pi

    # ------------------------------------------------------------------------------------------------------------------
    def _maybe_log_step(self):
        """
        Occasional debug logging, similar to your original pattern.
        """
        if (self.step % 10) == 0 or self.step == 1:
            self.logger.debug("--------------------------------")
            self.logger.debug(f"Step: {self.step}")
            for agent in self.agents.values():
                Pn = np.linalg.norm(agent.covariance, ord='fro')
                self.logger.debug(
                    f"{agent.id}: \t x: {agent.state.x:.3f} \t y: {agent.state.y:.3f} \t "
                    f"psi: {agent.state.psi:.2f} \t Cov: {Pn:.1f}"
                )
