from __future__ import annotations

import copy
import dataclasses
import threading
import time

import numpy as np

# ======================================================================================================================
from applications.FRODO.navigation.multi_agent_navigator import MultiAgentNavigator, NavigatorPlan, \
    MultiAgentNavigator_Sample
from applications.FRODO.navigation.navigator import NavigatedObject
from applications.FRODO.navigation.utilities import FRODO_Real_NavigatedObject, FRODO_Sim_NavigatedObject
from applications.FRODO.testbed.testbed_manager import TestbedObject_FRODO, TestbedObject_STATIC, FRODO_TestbedManager, \
    TestbedObject
from applications.FRODO.simulation.frodo_simulation import FRODO_VisionAgent, FRODO_Static, FRODO_Simulation, \
    FRODO_VisionAgent_Config
from applications.FRODO.utilities.measurement_model import FRODO_MeasurementModel
from applications.FRODO.utilities.measurements import agent_is_in_fov, generate_noisy_measurement, \
    generate_ideal_measurement
from core.utils.events import Event, event_definition, EventFlag
from core.utils.exit import register_exit_callback
from core.utils.files import file_exists
from core.utils.logging_utils import Logger
from core.utils.states import State
from extensions.tools.cli.cli import CommandSet, Command, CommandArgument

"""
The agent manager manages real and simulated agents and statics as well as their interactions and prepares the measurements
for the algorithm. It also calculates the simulated measurements between real and virtual agents
"""


@dataclasses.dataclass(frozen=True)
class AgentMeasurement:
    agent_from: str
    agent_to: str
    measurement: np.ndarray
    covariance: np.ndarray


@dataclasses.dataclass
class AgentState(State):
    x: float = 0.0
    y: float = 0.0
    psi: float = 0.0
    v: float = 0.0
    psi_dot: float = 0.0


@dataclasses.dataclass
class AgentInput(State):
    v: float = 0.0
    psi_dot: float = 0.0


@dataclasses.dataclass
class AgentConfiguration:
    measurement_model: FRODO_MeasurementModel

    def __repr__(self):
        return (
            f"{self.__class__.__name__}("
            f"measurement_model={repr(self.measurement_model)}"
            ")"
        )


@dataclasses.dataclass
class AgentContainer:
    id: str
    state: AgentState = dataclasses.field(init=False)
    input: AgentInput = dataclasses.field(init=False)
    config: AgentConfiguration
    measurements: list[AgentMeasurement] = dataclasses.field(default_factory=list)
    navigator_object: NavigatedObject | None = None


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class RealAgentContainer(AgentContainer):
    @dataclasses.dataclass(frozen=True)
    class Sample:
        id: str
        state: AgentState
        measurements: list[AgentMeasurement]
        # TODO: Navigation Objectives?

    testbed_object: TestbedObject_FRODO
    navigator_object: FRODO_Real_NavigatedObject | None = None

    @property
    def state(self) -> AgentState:
        return AgentState(
            x=self.testbed_object.dynamic_state.x,
            y=self.testbed_object.dynamic_state.y,
            psi=self.testbed_object.dynamic_state.psi,
            v=self.testbed_object.dynamic_state.v,
            psi_dot=self.testbed_object.dynamic_state.psi_dot,
        )

    @property
    def input(self) -> AgentInput:
        return AgentInput(
            v=self.testbed_object.dynamic_state.v,
            psi_dot=self.testbed_object.dynamic_state.psi_dot,
        )

    def get_sample(self):
        sample = RealAgentContainer.Sample(id=self.id,
                                           state=copy.copy(self.state),
                                           measurements=copy.copy(self.measurements))
        return sample


@dataclasses.dataclass(kw_only=True)
class SimulatedAgentContainer(AgentContainer):
    @dataclasses.dataclass(frozen=True)
    class Sample:
        id: str
        state: AgentState
        measurements: list[AgentMeasurement]

    agent: FRODO_VisionAgent
    navigator_object: FRODO_Sim_NavigatedObject | None = None

    @property
    def state(self) -> AgentState:
        return AgentState(
            x=self.agent.state.x,
            y=self.agent.state.y,
            psi=self.agent.state.psi,
            v=self.agent.state.v,
            psi_dot=self.agent.state.psi_dot,
        )

    @property
    def input(self) -> AgentInput:
        return AgentInput(
            v=self.agent.state.v,
            psi_dot=self.agent.state.psi_dot,
        )

    def get_sample(self):
        sample = SimulatedAgentContainer.Sample(id=self.id,
                                                state=copy.copy(self.state),
                                                measurements=copy.copy(self.measurements))
        return sample


@dataclasses.dataclass
class StaticContainer:
    id: str
    state: AgentState = dataclasses.field(init=False)


@dataclasses.dataclass(kw_only=True)
class RealStaticContainer(StaticContainer):
    @dataclasses.dataclass(frozen=True)
    class Sample:
        id: str
        state: AgentState

    testbed_object: TestbedObject_STATIC

    @property
    def state(self) -> AgentState:
        return AgentState(
            x=self.testbed_object.state.x,
            y=self.testbed_object.state.y,
            psi=self.testbed_object.state.psi,
            v=0.0,
            psi_dot=0.0,
        )

    def get_sample(self):
        sample = RealStaticContainer.Sample(id=self.id, state=copy.copy(self.state))
        return sample


@dataclasses.dataclass(kw_only=True)
class SimulatedStaticContainer(StaticContainer):
    @dataclasses.dataclass(frozen=True)
    class Sample:
        id: str
        state: AgentState

    static: FRODO_Static

    @property
    def state(self) -> AgentState:
        return AgentState(
            x=self.static.state.x,
            y=self.static.state.y,
            psi=self.static.state.psi,
            v=0.0,
            psi_dot=0.0,
        )

    def get_sample(self):
        sample = SimulatedStaticContainer.Sample(id=self.id, state=copy.copy(self.state))
        return sample


@event_definition
class FRODO_AgentManager_Events:
    update: Event
    error: Event  # Error coming from one of the real agents or the testbed manager
    new_agent: Event = Event(copy_data_on_set=False, flags=[EventFlag('id', str), EventFlag('type', str)])
    new_static: Event = Event(copy_data_on_set=False, flags=[EventFlag('id', str), EventFlag('type', str)])
    removed_static: Event = Event(copy_data_on_set=False, flags=[EventFlag('id', str), EventFlag('type', str)])
    removed_agent: Event = Event(copy_data_on_set=False, flags=[EventFlag('id', str), EventFlag('type', str)])


@dataclasses.dataclass(frozen=True)
class AgentManager_Sample:
    real_agents: dict[str, RealAgentContainer.Sample]
    simulated_agents: dict[str, SimulatedAgentContainer.Sample]
    real_statics: dict[str, RealStaticContainer.Sample]
    simulated_statics: dict[str, SimulatedStaticContainer.Sample]
    navigator: MultiAgentNavigator_Sample


@dataclasses.dataclass
class AgentManager_Config:
    virtual_measurements_fuse_factor = 0.5


# ======================================================================================================================
class FRODO_AgentManager:
    agents: dict[str, AgentContainer]
    statics: dict[str, StaticContainer]
    events: FRODO_AgentManager_Events

    simulation: FRODO_Simulation
    testbed_manager: FRODO_TestbedManager
    navigator: MultiAgentNavigator

    settings: AgentManager_Config
    _agent_lock: threading.Lock
    _exit: bool = False
    _thread: threading.Thread

    # === INIT =========================================================================================================
    def __init__(self,
                 simulation: FRODO_Simulation,
                 testbed_manager: FRODO_TestbedManager,
                 settings: AgentManager_Config | None = None
                 ):

        if settings is None:
            settings = AgentManager_Config()

        self.settings = settings

        self.simulation = simulation
        self.testbed_manager = testbed_manager

        self.testbed_manager.events.new_object.on(self._on_new_testbed_object)
        self.testbed_manager.events.object_removed.on(self._on_testbed_object_removed)

        self.navigator = MultiAgentNavigator()

        self.agents = {}
        self.statics = {}

        self.simulation.events.new_agent.on(self._on_new_simulation_agent)
        self.simulation.events.removed_agent.on(self._on_agent_removed_simulation)
        self.simulation.events.new_static.on(self._on_new_simulated_static)
        self.simulation.events.removed_static.on(self._on_removed_simulated_static)

        self.events = FRODO_AgentManager_Events()
        self.logger = Logger('AgentManager', 'DEBUG')
        self._agent_lock = threading.Lock()

        self.commands = self.Commands(self)

        # self._thread = threading.Thread(target=self._task, daemon=True)
        register_exit_callback(self.close)

    # === PROPERTIES ===================================================================================================
    @property
    def real_agents(self) -> dict[str, RealAgentContainer]:
        return {k: v for k, v in self.agents.items() if isinstance(v, RealAgentContainer)}

    @property
    def simulated_agents(self) -> dict[str, SimulatedAgentContainer]:
        return {k: v for k, v in self.agents.items() if isinstance(v, SimulatedAgentContainer)}

    @property
    def real_statics(self) -> dict[str, RealStaticContainer]:
        return {k: v for k, v in self.statics.items() if isinstance(v, RealStaticContainer)}

    @property
    def simulated_statics(self) -> dict[str, SimulatedStaticContainer]:
        return {k: v for k, v in self.statics.items() if isinstance(v, SimulatedStaticContainer)}

    # === METHODS ======================================================================================================
    def start(self):
        # self.logger.warning("This starts the agent manager in a separate thread. This is for debug purposes only.")
        # self._thread.start()
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self._exit = True
        if self._thread.is_alive():
            self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self):
        self.agents.clear()
        self.statics.clear()

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> AgentManager_Sample:
        real_agent_samples = {}
        for id, agent in self.real_agents.items():
            real_agent_samples[id] = agent.get_sample()

        simulated_agent_samples = {}
        for id, agent in self.simulated_agents.items():
            simulated_agent_samples[id] = agent.get_sample()

        real_static_samples = {}
        for id, static in self.real_statics.items():
            real_static_samples[id] = static.get_sample()

        simulated_static_samples = {}
        for id, static in self.simulated_statics.items():
            simulated_static_samples[id] = static.get_sample()

        sample = AgentManager_Sample(real_agent_samples,
                                     simulated_agent_samples,
                                     real_static_samples,
                                     simulated_static_samples,
                                     self.navigator.get_sample())
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def new_virtual_agent(self,
                          agent_id: str,
                          config: FRODO_VisionAgent_Config | None = None, ):
        """
        Adds a virtual agent to the simulation
        Returns:

        """

        self.simulation.new_agent(agent_id, config)

    # ------------------------------------------------------------------------------------------------------------------
    def remove_simulated_agent(self, agent_id: str):
        self.simulation.remove_agent(agent_id)

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):

        # 1. Generate all measurements
        self._generate_measurements()

        self.events.update.set()

    # ------------------------------------------------------------------------------------------------------------------
    def get_navigation_objects(self) -> list[NavigatedObject]:
        navigated_objects = []
        for agent in self.agents.values():
            navigated_objects.append(agent.navigator_object)
        return navigated_objects

    # ------------------------------------------------------------------------------------------------------------------
    def run_plan(self, plan: NavigatorPlan):
        self.navigator.load_plan(plan, start=True)

    # ------------------------------------------------------------------------------------------------------------------
    def run_plan_from_file(self, plan_file):
        if not file_exists(plan_file):
            self.logger.error(f"Plan file {plan_file} does not exist")
            return

        self.navigator.load_plan_from_file(plan_file, start=True)

    # === PRIVATE METHODS ==============================================================================================
    def _generate_measurements(self):

        # Go through all agents and pull existing measurements
        for agent_id, container in self.real_agents.items():
            container.measurements = []

            for measurement in container.testbed_object.measurements:
                converted_measurement = AgentMeasurement(
                    agent_from=agent_id,
                    agent_to=measurement.object_to.id,
                    measurement=measurement.relative.asarray(),
                    covariance=measurement.covariance
                )
                container.measurements.append(converted_measurement)

        # Simulated agents with already existing measurements
        for agent_id, container in self.simulated_agents.items():
            container.measurements = []

            for measurement in container.agent.measurements:
                converted_measurement = AgentMeasurement(
                    agent_from=agent_id,
                    agent_to=measurement.object_to.agent_id,
                    measurement=np.asarray([measurement.position[0], measurement.position[1], measurement.psi]),
                    covariance=measurement.covariance
                )
                container.measurements.append(converted_measurement)

        # Now go through all virtual agents and generate measurements to real agents
        for agent_id, container in self.simulated_agents.items():
            for real_agent_id, real_agent_container in self.real_agents.items():
                measurement = self._generate_virtual_measurement(container, real_agent_container)

                if measurement is not None:
                    container.measurements.append(measurement)

        # Same for the real agents for measurements to simulated agents
        for real_agent_id, real_agent_container in self.real_agents.items():
            for agent_id, container in self.simulated_agents.items():
                measurement = self._generate_virtual_measurement(real_agent_container, container)
                if measurement is not None:
                    real_agent_container.measurements.append(measurement)

    # ------------------------------------------------------------------------------------------------------------------
    def _generate_virtual_measurement(self, agent_from: AgentContainer,
                                      agent_to: AgentContainer) -> AgentMeasurement | None:

        state_agent_from = agent_from.state
        state_agent_to = agent_to.state

        # Check if they are in FOV
        if not agent_is_in_fov(
                agent_from_state=state_agent_from.asarray(),
                agent_to_state=state_agent_to.asarray(),
                agent_from_fov=agent_from.config.measurement_model.fov,
                agent_from_min_distance=agent_from.config.measurement_model.min_measurement_distance,
                agent_from_max_distance=agent_from.config.measurement_model.max_measurement_distance,
        ):
            return None

        measurement, covariance = generate_noisy_measurement(
            agent_from_state=state_agent_from.asarray(),
            agent_to_state=state_agent_to.asarray(),
            measurement_model=agent_from.config.measurement_model,
            fuse_factor=self.settings.virtual_measurements_fuse_factor
        )

        return AgentMeasurement(
            agent_from=agent_from.id,
            agent_to=agent_to.id,
            measurement=measurement,
            covariance=covariance,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_simulation_agent(self, agent: FRODO_VisionAgent, *args, **kwargs):
        self._add_virtual_agent(agent)

    # ------------------------------------------------------------------------------------------------------------------
    def _add_virtual_agent(self, agent: FRODO_VisionAgent):
        if agent.agent_id in self.agents:
            self.logger.warning(f"Agent {agent.agent_id} already exists in agent manager")
            return

        agent_container = SimulatedAgentContainer(
            id=agent.agent_id,
            agent=agent,
            navigator_object=FRODO_Sim_NavigatedObject(
                agent=agent,
            ),
            config=AgentConfiguration(
                measurement_model=agent.measurement_model
            )
        )
        self.agents[agent.agent_id] = agent_container
        self.navigator.add_agent(agent_container.navigator_object)

        self.logger.info(f"Added virtual agent {agent.agent_id} to agent manager")
        self.events.new_agent.set(agent_container, flags={'type': 'simulation', 'id': agent.agent_id})

    # ------------------------------------------------------------------------------------------------------------------
    def _on_agent_removed_simulation(self, agent: str, *args, **kwargs):
        if agent in self.agents:
            self._remove_virtual_agent(self.agents[agent])

    # ------------------------------------------------------------------------------------------------------------------
    def _remove_virtual_agent(self, agent: AgentContainer):
        if agent.id in self.agents:
            self.navigator.remove_agent(agent.navigator_object)
            del self.agents[agent.id]
            self.logger.info(f"Removed virtual agent {agent.id} from agent manager")
            self.events.removed_agent.set(agent, flags={'type': 'simulation', 'id': agent.id})

    # ------------------------------------------------------------------------------------------------------------------
    def _add_real_agent(self, robot: TestbedObject_FRODO):
        with self._agent_lock:
            if robot.id in self.agents:
                self.logger.warning(f"Agent {robot.id} already exists in agent manager")
                return
            agent_container = RealAgentContainer(
                id=robot.id,
                testbed_object=robot,
                navigator_object=FRODO_Real_NavigatedObject(
                    robot=robot.robot,
                ),
                config=AgentConfiguration(
                    measurement_model=robot.robot.config.measurement_model
                )
            )
            self.agents[robot.id] = agent_container
            self.navigator.add_agent(agent_container.navigator_object)
            self.logger.info(f"Added real agent {robot.id} to agent manager")
            self.events.new_agent.set(agent_container, flags={'type': 'robot', 'id': robot.id})

    # ------------------------------------------------------------------------------------------------------------------
    def _remove_real_agent(self, robot: AgentContainer):
        if robot.id in self.agents:
            self.navigator.remove_agent(robot.navigator_object)
            del self.agents[robot.id]
            self.logger.info(f"Removed real agent {robot.id} from agent manager")
            self.events.removed_agent.set(robot, flags={'type': 'robot', 'id': robot.id})

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_simulated_static(self, static: FRODO_Static, *args, **kwargs):
        if static.agent_id in self.statics:
            self.logger.warning(f"Static {static.agent_id} already exists in agent manager")
            return
        static_container = SimulatedStaticContainer(
            id=static.agent_id,
            static=static,
        )
        self.statics[static.agent_id] = static_container
        self.logger.info(f"Added simulated static {static.agent_id} to agent manager")
        self.events.new_static.set(static_container, flags={'type': 'simulation', 'id': static.agent_id})

    # ------------------------------------------------------------------------------------------------------------------
    def _on_removed_simulated_static(self, static: str, *args, **kwargs):
        if static in self.statics:
            del self.statics[static]
            self.logger.info(f"Removed simulated static {static} from agent manager")
            self.events.removed_static.set(static, flags={'type': 'simulation', 'id': static})

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_testbed_object(self, object: TestbedObject, *args, **kwargs):
        if isinstance(object, TestbedObject_FRODO):
            self._add_real_agent(object)
        elif isinstance(object, TestbedObject_STATIC):
            self._add_real_static(object)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_testbed_object_removed(self, object: TestbedObject, *args, **kwargs):
        if isinstance(object, TestbedObject_FRODO):
            if object.id in self.agents:
                self._remove_real_agent(self.agents[object.id])
        elif isinstance(object, TestbedObject_STATIC):
            if object.id in self.statics:
                self._remove_real_static(self.statics[object.id])

    # ------------------------------------------------------------------------------------------------------------------
    def _add_real_static(self, static: TestbedObject_STATIC):
        if static.id in self.statics:
            self.logger.warning(f"Static {static.id} already exists in agent manager")
            return
        static_container = RealStaticContainer(
            id=static.id,
            testbed_object=static,
        )
        self.statics[static.id] = static_container
        self.logger.info(f"Added real static {static.id} to agent manager")
        self.events.new_static.set(static_container, flags={'type': 'real', 'id': static.id})

    # ------------------------------------------------------------------------------------------------------------------
    def _remove_real_static(self, static: StaticContainer):
        if static.id in self.statics:
            del self.statics[static.id]
            self.logger.info(f"Removed real static {static.id} from agent manager")
            self.events.removed_static.set(static, flags={'type': 'real', 'id': static.id})

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        raise NotImplementedError("Task is currently not used")
        while not self._exit:
            self.update()
            time.sleep(0.05)

    # === CLASSES ======================================================================================================
    class Commands(CommandSet):
        def __init__(self, manager: 'FRODO_AgentManager'):
            super().__init__('agents')
            self.manager = manager

            list_command = Command(
                name='list',
                arguments=None,
                description='List all agents',
                function=lambda *args, **kwargs: self.manager.logger.info(f"Agents: {list(self.manager.agents.keys())}")
            )

            self.addCommand(list_command)

            config_show_command = Command(
                name='config',
                arguments=[
                    CommandArgument(name='agent',
                                    short_name='a',
                                    type=str,
                                    optional=False, )
                ],
                function=self._show_config,
            )
            self.addCommand(config_show_command)

            info_show_command = Command(
                name='info',
                arguments=[
                    CommandArgument(name='agent',
                                    short_name='a',
                                    type=str,
                                    optional=False, )
                ],
                function=self._show_info,
            )
            self.addCommand(info_show_command)

        # --------------------------------------------------------------------------------------------------------------
        def _show_config(self, agent: str):
            if agent not in self.manager.agents:
                self.manager.logger.warning(f"Agent {agent} does not exist")

            self.manager.logger.info(f"Config for agent {agent}: {self.manager.agents[agent].config}")

        # --------------------------------------------------------------------------------------------------------------
        def _show_info(self, agent: str):
            if agent not in self.manager.agents:
                self.manager.logger.warning(f"Agent {agent} does not exist")
                return

            container = self.manager.agents[agent]

            # Determine agent type
            if isinstance(container, RealAgentContainer):
                agent_type = "real"
            elif isinstance(container, SimulatedAgentContainer):
                agent_type = "simulated"
            else:
                agent_type = "unknown"

            state = container.state
            agent_input = container.input

            lines: list[str] = []

            # Header
            lines.append(f"Agent '{container.id}' ({agent_type})")
            lines.append("-" * 60)

            # State
            lines.append(
                "State:"
                f" x={state.x: .3f} m,"
                f" y={state.y: .3f} m,"
                f" psi={state.psi: .3f} rad,"
                f" v={state.v: .3f} m/s,"
                f" psi_dot={state.psi_dot: .3f} rad/s"
            )

            # Input
            lines.append(
                "Input:"
                f" v={agent_input.v: .3f} m/s,"
                f" psi_dot={agent_input.psi_dot: .3f} rad/s"
            )

            # Config (short summary, full config via 'config' command)
            if hasattr(container, "config") and container.config is not None:
                mm = container.config.measurement_model
                lines.append(
                    "Measurement model:"
                    f" fov={mm.fov: .3f} rad,"
                    f" d_min={mm.min_measurement_distance: .3f} m,"
                    f" d_max={mm.max_measurement_distance: .3f} m,"
                    f" bias_x={mm.bias_x: .3f} m,"
                    f" bias_y={mm.bias_y: .3f} m,"
                    f" bias_psi={mm.bias_psi: .3f} rad"
                )

            # Navigator object
            lines.append(f"Navigator object: {repr(container.navigator_object)}")

            # Measurements
            lines.append("")
            lines.append(f"Measurements (n={len(container.measurements)}):")

            if not container.measurements:
                lines.append("  (no measurements)")
            else:
                for idx, meas in enumerate(container.measurements):
                    z = meas.measurement
                    # Be defensive about the measurement shape
                    try:
                        mx, my, mpsi = float(z[0]), float(z[1]), float(z[2])
                    except Exception:
                        mx = my = mpsi = float("nan")

                    distance = float(np.hypot(mx, my)) if np.isfinite(mx) and np.isfinite(my) else float("nan")
                    bearing = float(np.arctan2(my, mx)) if np.isfinite(mx) and np.isfinite(my) else float("nan")

                    cov_diag_str = "n/a"
                    cov = meas.covariance
                    if isinstance(cov, np.ndarray) and cov.ndim == 2 and cov.shape[0] == cov.shape[1]:
                        diag = np.diag(cov)
                        cov_diag_str = "[" + ", ".join(f"{d: .3e}" for d in diag) + "]"

                    lines.append(
                        f"  {idx:02d}: {meas.agent_from} -> {meas.agent_to} | "
                        f"z=[x={mx: .3f}, y={my: .3f}, psi={mpsi: .3f}] | "
                        f"r={distance: .3f} m, bearing={bearing: .3f} rad | "
                        f"cov_diag={cov_diag_str}"
                    )

            text = "\n".join(lines)
            self.manager.logger.info("\n" + text)
