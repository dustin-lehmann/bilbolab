import abc
import dataclasses
from typing import Callable

import numpy as np


def cilc_update_agent(*,
                      u_j: np.ndarray,
                      e_j: np.ndarray,
                      alpha: float,
                      L: np.ndarray,
                      Q: np.ndarray = None,
                      u_group: np.ndarray,
                      e_group: np.ndarray,
                      L_group: np.ndarray = None,
                      Q_group: np.ndarray = None) -> np.ndarray:
    N = len(u_j)

    if Q is None:
        Q = np.eye(N)

    if Q_group is None:
        Q_group = Q

    if L_group is None:
        L_group = L

    u_next = alpha * Q @ (u_j + L @ e_j) + (1 - alpha) * Q_group @ (u_group + L_group @ e_group)

    return u_next


# ======================================================================================================================
def cilc_get_agent_weight(agent_error: np.ndarray,
                          all_agents_errors: list[np.ndarray],
                          sharpness: float,
                          norm: Callable = np.linalg.norm,
                          normalized: bool = False) -> float:
    # Exponential / softmin weight:        w^(i) = exp(-sigma * ||e^(i)||)       / sum_k exp(-sigma * ||e^(k)||)
    # Normalized (scale-invariant) form:   w^(i) = exp(-sigma * ||e^(i)|| / ebar) / sum_k exp(-sigma * ||e^(k)|| / ebar),
    #                                      with ebar = (1/N) * sum_k ||e^(k)||.
    agent_norm = float(norm(agent_error))
    all_norms = np.asarray([norm(e) for e in all_agents_errors], dtype=float)

    if normalized:
        e_bar = all_norms.mean()
        agent_norm = agent_norm / e_bar
        all_norms = all_norms / e_bar

    # Shift by min(all_norms) so the largest exponent is 0 (numerical stability for large sigma).
    shift = all_norms.min()
    numerator = np.exp(-sharpness * (agent_norm - shift))
    denominator = np.sum(np.exp(-sharpness * (all_norms - shift)))

    return float(numerator / denominator)  # type: ignore


# ======================================================================================================================
def cilc_get_agent_weights(all_agents_errors: list[np.ndarray],
                           sharpness: float,
                           norm: Callable = np.linalg.norm,
                           normalized: bool = False) -> np.ndarray:
    # Vectorized softmin: returns the full weight vector w in one shot. Same formula as
    # cilc_get_agent_weight, but evaluated for all agents simultaneously.
    all_norms = np.asarray([norm(e) for e in all_agents_errors], dtype=float)

    if normalized:
        all_norms = all_norms / all_norms.mean()

    # Shift by min(all_norms) so the largest exponent is 0 (numerical stability for large sigma).
    shift = all_norms.min()
    exponents = np.exp(-sharpness * (all_norms - shift))
    return exponents / exponents.sum()


# ======================================================================================================================
def cilc_weighted_group_input(all_agents_inputs: list[np.ndarray],
                              weights: list[float] | np.ndarray) -> np.ndarray:
    # Performance-weighted group input:  u_bar = sum_i w^(i) * u^(i)
    assert len(weights) == len(all_agents_inputs), \
        f"weights/inputs length mismatch: {len(weights)} vs {len(all_agents_inputs)}"
    return sum(w * u for w, u in zip(weights, all_agents_inputs))  # type: ignore


# ======================================================================================================================
def cilc_weighted_group_error(all_agents_errors: list[np.ndarray],
                              weights: list[float] | np.ndarray) -> np.ndarray:
    # Performance-weighted group error:  e_bar = sum_i w^(i) * e^(i)
    assert len(weights) == len(all_agents_errors), \
        f"weights/errors length mismatch: {len(weights)} vs {len(all_agents_errors)}"
    return sum(w * e for w, e in zip(weights, all_agents_errors))  # type: ignore


# ======================================================================================================================
@dataclasses.dataclass(kw_only=True)
class CILC_TrialData:
    u: np.ndarray
    e: np.ndarray
    L: np.ndarray
    Q: np.ndarray
    alpha: float
    u_group: np.ndarray
    e_group: np.ndarray
    L_group: np.ndarray | None = None
    Q_group: np.ndarray | None = None
    e_norm: float
    e_norm_group: float


# ======================================================================================================================


class CILC_Agent(abc.ABC):
    id: str
    dynamics: Callable
    reference: np.ndarray
    trials: list[CILC_TrialData]

    # Gain matrices: set on the instance (in __init__ or as dataclass fields by the subclass).
    # Q defaults to identity, L_group defaults to L, Q_group defaults to Q -- mirrors cilc_update_agent.
    L: np.ndarray
    Q: np.ndarray | None = None
    L_group: np.ndarray | None = None
    Q_group: np.ndarray | None = None

    # Current trial data
    u: np.ndarray | None = None
    y: np.ndarray | None = None
    e: np.ndarray | None = None
    j: int

    def __init__(self,
                 id: str,
                 dynamics: Callable,
                 reference: np.ndarray,
                 L: np.ndarray,
                 Q: np.ndarray | None = None,
                 L_group: np.ndarray | None = None,
                 Q_group: np.ndarray | None = None):
        self.id = id
        self.reference = reference
        self.L = L
        self.Q = Q
        self.dynamics = dynamics
        self.L_group = L_group
        self.Q_group = Q_group
        self.trials = []
        self.j = 0

        self.u = None
        self.e = None
        self.y = None

    # ----- main DOF: stubbornness schedule (must be implemented by every subclass) -----
    @abc.abstractmethod
    def get_alpha(self, j: int) -> float:
        ...

    # ----- hook methods for the gains (override only to make them trial-varying) -----
    def get_L(self, j: int) -> np.ndarray:
        return self.L

    # ------------------------------------------------------------------------------------------------------------------
    def get_Q(self, j: int) -> np.ndarray:
        return self.Q if self.Q is not None else np.eye(len(self.reference))

    # ------------------------------------------------------------------------------------------------------------------
    def get_L_group(self, j: int) -> np.ndarray:
        return self.L_group if self.L_group is not None else self.get_L(j)

    # ------------------------------------------------------------------------------------------------------------------
    def get_Q_group(self, j: int) -> np.ndarray:
        return self.Q_group if self.Q_group is not None else self.get_Q(j)

    # ------------------------------------------------------------------------------------------------------------------
    def set_u(self, u: np.ndarray):
        self.u = u

    # ------------------------------------------------------------------------------------------------------------------
    def run_trial(self):
        self.y = self.dynamics(self.u)
        self.e = self.reference - self.y
        self.j += 1

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, u_group: np.ndarray, e_group: np.ndarray):
        # After run_trial, self.j has been incremented; the trial whose data we just collected has index j.
        j = self.j - 1
        alpha = self.get_alpha(j)
        L = self.get_L(j)
        Q = self.get_Q(j)
        L_group = self.get_L_group(j)
        Q_group = self.get_Q_group(j)

        # Save the trial data BEFORE overwriting self.u with the next input.
        self.trials.append(CILC_TrialData(
            u=self.u,  # type: ignore
            e=self.e,  # type: ignore
            L=L,
            Q=Q,
            alpha=alpha,
            u_group=u_group,
            e_group=e_group,
            L_group=L_group,
            Q_group=Q_group,
            e_norm=float(np.linalg.norm(self.e)),
            e_norm_group=float(np.linalg.norm(e_group)),
        ))

        # GCILC update: u_{j+1} = alpha * Q (u_j + L e_j) + (1 - alpha) * Q_group (u_bar_j + L_group e_bar_j)
        self.u = cilc_update_agent(
            u_j=self.u,  # type: ignore
            e_j=self.e,  # type: ignore
            alpha=alpha,
            L=L,
            Q=Q,
            u_group=u_group,
            e_group=e_group,
            L_group=L_group,
            Q_group=Q_group,
        )


# ======================================================================================================================
class CILC_Group:
    agents: list[CILC_Agent]
    sharpness: float
    normalized: bool = False
    norm: Callable = np.linalg.norm
    reference: np.ndarray

    # ==================================================================================================================
    def __init__(self, reference: np.ndarray,
                 sharpness: float,
                 normalized: bool = False,
                 norm: Callable = np.linalg.norm):

        self.reference = reference
        self.norm = norm
        self.normalized = normalized
        self.sharpness = sharpness
        self.agents = []

    # ==================================================================================================================
    def add_agent(self, agent: CILC_Agent) -> CILC_Agent:
        # Common-reference assumption (cf. cilc.tex sec:cilc-setting): all agents track the same y*.
        # The group is the source of truth, so we overwrite whatever reference the agent was created with.
        agent.reference = self.reference
        self.agents.append(agent)
        return agent

    # ==================================================================================================================
    def add_agents(self, agents: list[CILC_Agent]) -> list[CILC_Agent]:
        for agent in agents:
            self.add_agent(agent)

        return agents
    # ==================================================================================================================
    def run_cilc(self, J: int):
        # Initialize any agent that doesn't yet have an input (default: zero input of reference shape).
        for agent in self.agents:
            if agent.u is None:
                agent.set_u(np.zeros_like(self.reference))

        for _ in range(J):
            # 1. Run a trial on each agent (produces y, e; advances agent.j).
            for agent in self.agents:
                agent.run_trial()

            # 2. Compute softmin weights and group-fused (u, e).
            errors = [agent.e for agent in self.agents]
            inputs = [agent.u for agent in self.agents]
            weights = cilc_get_agent_weights(errors, self.sharpness, self.norm, self.normalized)
            u_group = cilc_weighted_group_input(inputs, weights)
            e_group = cilc_weighted_group_error(errors, weights)

            # 3. Each agent applies the GCILC update law to compute its next input.
            for agent in self.agents:
                agent.update(u_group=u_group, e_group=e_group)
