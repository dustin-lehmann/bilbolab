from __future__ import annotations

import copy
import dataclasses

import numpy as np

from robots.frodo.applications.algorithm.algorithm import AlgorithmAgentState, AlgorithmAgentSettings, AlgorithmAgentInput, \
    AlgorithmAgentMeasurement
from robots.frodo.applications.algorithm.algorithm_centralized import CentralizedAlgorithm, CentralizedAlgorithm_Sample, \
    CentralizedAgent
from robots.frodo.applications.algorithm.algorithm_distributed import DistributedAlgorithm, DistributedAlgorithm_Sample, \
    DistributedAgent
from core.utils.logging_utils import Logger
from extensions.tools.cli.cli import CommandSet, Command

"""
The algorithm manager manages the running algorithms, sets them up with parameters and updates them based on 
given agent measurements and inputs
"""


@dataclasses.dataclass
class AlgorithmAgentUpdateData:
    input: AlgorithmAgentInput


@dataclasses.dataclass
class AlgorithmAgentConfig:
    id: str
    anchor: bool
    initial_state: AlgorithmAgentState | np.ndarray
    initial_covariance: np.ndarray
    settings: AlgorithmAgentSettings = dataclasses.field(default_factory=AlgorithmAgentSettings)


@dataclasses.dataclass
class AlgorithmAgentContainer:
    id: str
    config: AlgorithmAgentConfig
    centralized_agent: CentralizedAgent
    distributed_agent: DistributedAgent
    measurements: list[AlgorithmAgentMeasurement] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class AlgorithmManager_Sample:
    step: int
    centralized: CentralizedAlgorithm_Sample
    distributed: DistributedAlgorithm_Sample


@dataclasses.dataclass
class AlgorithmSettings:
    Ts: float


class FRODO_AlgorithmManager:
    algorithm_centralized: CentralizedAlgorithm
    algorithm_distributed: DistributedAlgorithm

    agents: dict[str, AlgorithmAgentContainer]

    # === INIT =========================================================================================================
    def __init__(self, settings: AlgorithmSettings):
        self.settings = settings
        self.agents = {}
        self.algorithm_centralized = CentralizedAlgorithm(settings.Ts)
        self.algorithm_distributed = DistributedAlgorithm(settings.Ts)
        self.logger = Logger('Algorithm Manager', 'DEBUG')

        self.commands = self.Commands(self)

    # === METHODS ======================================================================================================
    def initialize(self, agents: list[AlgorithmAgentConfig]):
        self.logger.info("Initializing algorithm manager")
        # Clear the agents
        self.agents = {}

        # Build the agents
        for agent_config in agents:
            if agent_config.id in self.agents:
                raise ValueError(f"Agent with ID {agent_config.id} already exists")

            centralized_agent = CentralizedAgent(
                id=agent_config.id,
                Ts=self.settings.Ts,
                state=AlgorithmAgentState.from_array(agent_config.initial_state),
                covariance=agent_config.initial_covariance,
                is_anchor=agent_config.anchor,
                settings=agent_config.settings
            )

            distributed_agent = DistributedAgent(
                id=agent_config.id,
                Ts=self.settings.Ts,
                state=AlgorithmAgentState.from_array(agent_config.initial_state),
                covariance=agent_config.initial_covariance,
                is_anchor=agent_config.anchor,
                settings=agent_config.settings
            )

            agent_container = AlgorithmAgentContainer(
                id=agent_config.id,
                config=agent_config,
                centralized_agent=centralized_agent,
                distributed_agent=distributed_agent)

            self.agents[agent_config.id] = agent_container
            self.logger.info(f"Added agent {agent_config.id} to algorithm manager")

        self.initialize_algorithms()

    # ------------------------------------------------------------------------------------------------------------------
    def reset_algorithms(self):
        self.algorithm_centralized.reset()
        self.algorithm_distributed.reset()

    # ------------------------------------------------------------------------------------------------------------------
    def initialize_algorithms(self):
        self.algorithm_centralized.reset()
        self.algorithm_distributed.reset()

        self.algorithm_centralized.initialize([container.centralized_agent for container in self.agents.values()])
        self.algorithm_distributed.initialize([container.distributed_agent for container in self.agents.values()])

    # ------------------------------------------------------------------------------------------------------------------
    def restart(self):
        self.logger.info("Restarting algorithm manager")
        configs = [agent.config for agent in self.agents.values()]
        self.initialize(configs)

    # ------------------------------------------------------------------------------------------------------------------
    def prediction(self, update_data: dict[str, AlgorithmAgentUpdateData]) -> None:
        # Update the inputs of the distributed and centralized agents
        for agent_id, agent_container in self.agents.items():
            if agent_id not in update_data:
                self.logger.error(f"No input data for agent {agent_id} found")
                continue
            agent_container.centralized_agent.input = copy.copy(update_data[agent_id].input)
            agent_container.distributed_agent.input = copy.copy(update_data[agent_id].input)

        self.algorithm_centralized.prediction()
        self.algorithm_distributed.prediction()

    # ------------------------------------------------------------------------------------------------------------------
    def correction(self, measurements: dict[str, list[AlgorithmAgentMeasurement]]) -> None:

        for agent_id, agent_container in self.agents.items():
            # 1. Wipe all measurements from the algorithm agents
            agent_container.centralized_agent.measurements.clear()
            agent_container.distributed_agent.measurements.clear()

            # 2. Add the measurements
            for measurement in measurements[agent_id]:
                # Centralized
                agent_container.centralized_agent.measurements.append(measurement)

                # Distributed
                agent_container.distributed_agent.measurements.append(measurement)

        self.algorithm_centralized.correction()
        self.algorithm_distributed.correction()

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> AlgorithmManager_Sample:
        sample = AlgorithmManager_Sample(step=self.algorithm_centralized.step,
                                         centralized=self.algorithm_centralized.get_sample(),
                                         distributed=self.algorithm_distributed.get_sample())
        return sample

    # === CLASSES ======================================================================================================
    class Commands(CommandSet):
        def __init__(self, manager: FRODO_AlgorithmManager):
            super().__init__('algorithm')
            self.manager = manager

            info_command = Command(
                name='info',
                arguments=None,
                description='Print algorithm manager information',
                function=self._show_info
            )

        # --------------------------------------------------------------------------------------------------------------
        def _show_info(self):
            self.logger.warning("Not implemented yet")

            # Should show if it is running
