from __future__ import annotations

import abc
import copy
import dataclasses
import enum
import threading
import time
from typing import Any, Union

import numpy as np

from applications.FRODO.agent_manager import FRODO_AgentManager, AgentManager_Sample, AgentContainer, StaticContainer
from applications.FRODO.algorithm.algorithm import AlgorithmAgentInput, AlgorithmAgentMeasurement, AlgorithmAgentState
from applications.FRODO.algorithm.algorithm_manager import FRODO_AlgorithmManager, AlgorithmAgentUpdateData, \
    AlgorithmAgentConfig, AlgorithmManager_Sample

from applications.FRODO.algorithm.algorithm_manager import AlgorithmAgentContainer
from applications.FRODO.navigation.multi_agent_navigator import MultiAgentNavigator, Move, NavigatorPlan
from applications.FRODO.navigation.navigator import CoordinatedMoveTo
from core.utils.callbacks import Callback
from core.utils.dataclass_utils import update_dataclass_from_dict
from core.utils.events import event_definition, Event, SubscriberListener, EventContainer, EventFlag
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.sound.sound import speak, beep
from core.utils.time import IntervalTimer
from extensions.tools.cli.cli import CommandSet, Command


# ======================================================================================================================
@event_definition
class ExperimentActionEvents:
    started: Event
    finished: Event
    timeout: Event
    error: Event


@dataclasses.dataclass(kw_only=True)
class ExperimentAction(abc.ABC):
    type: str
    id: str
    data: Any = None
    description: str | None = None
    after: str | None = None  # Specify the id of an action after which this action should be executed
    time: float | None = None  # Time in seconds after which the action should be executed (in the experiment time)

    timeout: float | None = None

    _experiment: FRODO_Experiment | None = None
    started: bool = False
    finished: bool = False

    def __post_init__(self):
        self.events = ExperimentActionEvents()
        if self.time is not None and self.after is not None:
            raise ValueError("Cannot specify both time and after for an action.")
        if self.time is None and self.after is None:
            self.time = 0.0

    def initialize(self, experiment: FRODO_Experiment):
        self._experiment = experiment

    @abc.abstractmethod
    def execute(self):
        self._on_started()

    def _on_started(self):
        self.started = True
        self.events.started.set()

    def _on_finished(self):
        self.finished = True
        self.events.finished.set(data=self.data)

    def _on_timeout(self):
        self.events.timeout.set()

    def _on_error(self):
        self.events.error.set()


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class AddSimulatedAgent(ExperimentAction):
    type: str = "add_simulated_agent"
    agent_id: str
    config: dict[str, Any]

    def execute(self):
        super().execute()
        raise NotImplementedError("Not implemented yet.")


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class RemoveSimulatedAgent(ExperimentAction):
    type: str = "remove_simulated_agent"
    agent_id: str

    def execute(self):
        super().execute()
        raise NotImplementedError("Not implemented yet.")


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class AddSimulatedStatic(ExperimentAction):
    type: str = "add_simulated_static"
    static_id: str
    config: dict[str, Any]

    def execute(self):
        super().execute()
        raise NotImplementedError("Not implemented yet.")


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class RemoveSimulatedStatic(ExperimentAction):
    type: str = "remove_simulated_static"
    static_id: str

    def execute(self):
        super().execute()
        raise NotImplementedError("Not implemented yet.")


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SetState(ExperimentAction):
    type: str = "set_agent_state"
    object_id: str
    state: list

    def execute(self):
        super().execute()
        raise NotImplementedError("Not implemented yet.")


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SetMarker(ExperimentAction):
    type: str = "set_marker"
    id: str
    value: str

    def execute(self):
        super().execute()
        raise NotImplementedError("Not implemented yet.")


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class StartAlgorithm(ExperimentAction):
    type: str = "start_algorithm"

    def execute(self):
        super().execute()
        self._experiment.experiment_handler.start_algorithm()
        self._on_finished()


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class StopAlgorithm(ExperimentAction):
    type: str = "stop_algorithm"

    def execute(self):
        super().execute()
        self._experiment.experiment_handler.stop_algorithm()
        self._on_finished()


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class StartLogging(ExperimentAction):
    type: str = "start_logging"
    id: str

    def execute(self):
        super().execute()
        raise NotImplementedError("Not implemented yet.")


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class StopLogging(ExperimentAction):
    type: str = "stop_logging"
    id: str

    def execute(self):
        super().execute()
        raise NotImplementedError("Not implemented yet.")


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class Speak(ExperimentAction):
    type: str = "speak"
    text: str

    def execute(self):
        super().execute()
        speak(self.text)
        self._on_finished()


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class Beep(ExperimentAction):
    type: str = "beep"
    frequency: float = 1000.0
    duration: float = 250
    repeats: int = 1
    volume: float = 1.0

    def execute(self):
        super().execute()
        beep(self.frequency, self.duration, self.repeats, self.volume)
        self._on_finished()


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class RunPlan(ExperimentAction):
    type: str = "run_plan"
    plan: NavigatorPlan

    def execute(self):
        super().execute()
        raise NotImplementedError("Not implemented yet.")


@dataclasses.dataclass(kw_only=True)
class RunPlanFromFile(ExperimentAction):
    type: str = "run_plan_from_file"
    file: str

    def execute(self):
        super().execute()
        raise NotImplementedError("Not implemented yet.")


# ----------------------------------------------------------------------------------------------------------------------

# ----------------------------------------------------------------------------------------------------------------------

# ----------------------------------------------------------------------------------------------------------------------


# === EXPERIMENT =======================================================================================================
@dataclasses.dataclass
class FRODO_Experiment_Definition:
    id: str
    description: str = ''

    robots: list[str] = dataclasses.field(default_factory=list)
    statics: list[str] = dataclasses.field(default_factory=list)

    virtual_robots: list[str] = dataclasses.field(default_factory=list)
    virtual_statics: list[str] = dataclasses.field(default_factory=list)

    joystick_assignments: list[tuple[str, str]] = dataclasses.field(default_factory=list)

    initial_states: dict[str, dict[str, float]] = dataclasses.field(default_factory=dict)

    movement_plan: str | None = None  # File of the movement yaml file
    algorithm_settings: dict[str, dict[str, str | float | int]] = dataclasses.field(default_factory=dict)

    length: float | None = None  # Length of the experiment in s
    actions: list[ExperimentAction] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ActionContainer:
    action: ExperimentAction
    started: bool = False
    finished: bool = False
    handled: bool = False
    listeners: list[SubscriberListener] = dataclasses.field(default_factory=list)
    following_actions: list[ActionContainer] = dataclasses.field(default_factory=list)


class FRODO_Experiment_Status(enum.StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


@event_definition
class FRODO_Experiment_Events(EventContainer):
    action_started: Event = Event(copy_data_on_set=False, flags=[EventFlag('action_id', str)])
    finished: Event = Event(copy_data_on_set=False)
    error: Event = Event(copy_data_on_set=False)
    timeout: Event = Event(copy_data_on_set=False)


@dataclasses.dataclass
class ExperimentSample:
    time: float  # Internal time of the experiment
    time_absolute: float  # Absolute time of the experiment
    id: str  # Experiment ID
    current_action: str | list[str] | None = None


class FRODO_Experiment:
    definition: FRODO_Experiment_Definition
    actions: dict[str, ActionContainer]

    time: float = 0.0  # Internal time of the experiment
    time_absolut: float = 0.0  # Absolute time of the experiment
    timeout: float | None = None

    _step: int = 0
    _timer: IntervalTimer | None = None
    status: FRODO_Experiment_Status = FRODO_Experiment_Status.NOT_STARTED
    experiment_handler: FRODO_ExperimentManager | None = None
    _thread: threading.Thread | None = None
    _exit: bool = False

    _start_time: float = 0.0

    _current_action_sample_buffer: list[str]

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, definition: FRODO_Experiment_Definition):
        self.definition = definition
        self.logger = Logger(f'Experiment {self.definition.id}', 'DEBUG')
        self._thread = None
        self._timer = IntervalTimer(interval=0.1, raise_race_condition_error=False)
        self.events = FRODO_Experiment_Events()

        self._current_action_sample_buffer = []
        self.actions = {}
        for action in self.definition.actions:
            if action.id in self.actions:
                self.logger.error(f"Duplicate action ID {action.id}")
                continue

            self.actions[action.id] = ActionContainer(action=action)

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def experiment_time(self):
        return time.monotonic() - self._start_time

    # ------------------------------------------------------------------------------------------------------------------
    def initialize(self, experiment_handler: FRODO_ExperimentManager) -> bool:
        if self.status == FRODO_Experiment_Status.RUNNING:
            self.logger.error("Experiment is already running. Cannot initialize.")
            return False
        self.experiment_handler = experiment_handler
        self.status = FRODO_Experiment_Status.NOT_STARTED
        self._thread = threading.Thread(target=self._task, daemon=True)
        self._exit = False
        self._step = 0
        self._current_action_sample_buffer = []

        # Check the prerequisites of the experiment
        result = self._handle_prerequisites()

        if not result:
            self.status = FRODO_Experiment_Status.ERROR
            return False

        for action in self.actions.values():
            action.following_actions = []

        for action in self.actions.values():
            action.action.initialize(self)
            if action.action.after is not None:
                self.actions[action.action.after].following_actions.append(action)

        # Initialize the experiment handler agents
        # TODO Handle overrides
        overrides = {}

        # We need a small sleep here because we are dealing with event listeners that are attached to the simulation
        time.sleep(0.1)
        self.experiment_handler.initialize_agents(**overrides)

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        if self.status != FRODO_Experiment_Status.NOT_STARTED:
            self.logger.error("Experiment cannot be started.")
            return
        self.logger.info("Starting")
        self.status = FRODO_Experiment_Status.RUNNING
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def to_file(self, file: str):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def from_file(self, file: str):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> ExperimentSample:
        sample = ExperimentSample(
            time=self.experiment_time,
            time_absolute=time.monotonic(),
            id=self.definition.id,
            current_action=copy.copy(self._current_action_sample_buffer)
        )
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        self._timer.reset()
        self._start_time = time.monotonic()
        beep(1000, 250, 1, 3, force=True)
        speak(f"Experiment {self.definition.id} started")
        while not self._exit:
            self._update()
            self._timer.sleep_until_next()

    # ------------------------------------------------------------------------------------------------------------------
    def _update(self):

        for action_id, action_container in self.actions.items():
            if action_container.handled:
                continue

            # If the action is not started yet, and the action is time-dependent, not action-dependent, start it
            if not action_container.started and action_container.action.time is not None and self.experiment_time >= action_container.action.time:
                self._start_action(action_container)

            if action_container.finished:
                self._handle_action_finished(action_container)

                # Remove from the list

        if all(action_container.handled for action_container in self.actions.values()):
            self._handle_experiment_finished()

        # TODO: HAndle the length of the experiment!
        if self.definition.length is not None and self.experiment_time >= self.definition.length:
            self.logger.warning("Experiment reached length. Stopping. Not implemented yet.")

        if self.timeout is not None and self.experiment_time >= self.timeout:
            self.status = FRODO_Experiment_Status.ERROR
            self._handle_experiment_timeout()
            self.events.timeout.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_action_finished(self, container: ActionContainer):

        for action_container in container.following_actions:
            self._start_action(action_container)

        container.handled = True

    # ------------------------------------------------------------------------------------------------------------------
    def _start_action(self, container: ActionContainer):

        # Attach the events
        listener = container.action.events.finished.on(
            callback=Callback(
                function=self._on_action_finished,
                discard_inputs=True,
                inputs={
                    'container': container
                }
            ),
            once=True
        )

        container.listeners.append(listener)

        listener = container.action.events.error.on(
            callback=Callback(
                function=self._on_action_error,
                discard_inputs=True,
                inputs={
                    'container': container
                }
            ),
            once=True
        )
        container.listeners.append(listener)

        listener = container.action.events.timeout.on(
            callback=Callback(
                function=self._on_action_timeout,
                discard_inputs=True,
                inputs={
                    'container': container
                }
            ),
            once=True
        )
        container.listeners.append(listener)

        self.logger.info(f"Start action {container.action.id}")
        # Start the action
        container.action.execute()
        container.started = True
        self._mark_action_running(container.action.id)

        self.events.action_started.set(flags={'action_id': container.action.id})

    # ------------------------------------------------------------------------------------------------------------------
    def _mark_action_running(self, action_id: str):
        """
        Ensure that the given action ID is present in the current sample buffer.
        Used to mark actions as 'running' for this step, including those that start
        and finish within the same _update() iteration.
        """
        if action_id not in self._current_action_sample_buffer:
            self._current_action_sample_buffer.append(action_id)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_finished(self, container: ActionContainer):
        self.logger.info(f"Action {container.action.id} finished")
        container.finished = True

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_error(self, container: ActionContainer):
        self.logger.error(f"Action {container.action.id} failed")

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_timeout(self, container: ActionContainer):
        self.logger.warning(f"Action {container.action.id} timed out")

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_experiment_timeout(self):
        self.logger.error("Experiment timed out")
        self.status = FRODO_Experiment_Status.ERROR

        # Check if there are running actions
        for action_container in self.actions.values():
            if action_container.started and not action_container.finished:
                action_container.action.stop()

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_experiment_finished(self):
        beep(1000, 250, 2, 3, force=True)
        self.logger.info("Experiment finished")
        speak(f"Experiment {self.definition.id} finished")
        self.status = FRODO_Experiment_Status.FINISHED
        self._exit = True

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_prerequisites(self):
        self.logger.info("Checking prerequisites ...")
        # 1. Check if all robots are presents
        self.logger.info(f"Checking robots {self.definition.robots} ...")

        for robot_id in self.definition.robots:
            if not robot_id in self.experiment_handler.agent_manager.real_agents:
                self.logger.error(f"❌ Robot {robot_id} is not present in the experiment.")
                return False

        self.logger.info(f"All robots are present ✅")

        # Check if there are additional robots in the agent manager that are not in the experiment definition
        for agent_id in self.experiment_handler.agent_manager.real_agents:
            if agent_id not in self.definition.robots:
                self.logger.warning(
                    f"⚠️ Agent {agent_id} is present in the agent manager but not in the experiment definition.")

        # 2. Check the statics
        self.logger.info(f"Checking statics {self.definition.statics} ...")

        for static_id in self.definition.statics:
            if not static_id in self.experiment_handler.agent_manager.real_statics:
                self.logger.error(f"❌ Static {static_id} is not present in the experiment.")
                return False

        self.logger.info(f"All statics are present ✅")

        for static_id in self.experiment_handler.agent_manager.real_statics:
            if static_id not in self.definition.statics:
                self.logger.warning(
                    f"⚠️ Static {static_id} is present in the agent manager but not in the experiment definition.")

        # 3. Clear the simulation
        self.logger.info("Clearing simulation ...")
        self.experiment_handler.agent_manager.simulation.clear()

        # 4. Set-Up the simulation
        self.logger.info("Setting up simulation ...")
        for robot_id in self.definition.virtual_robots:
            agent = self.experiment_handler.agent_manager.simulation.new_agent(robot_id)
            if agent is None:
                self.logger.error(f"❌ Could not create agent {robot_id}.")
                return False

            # Set initial state of agent
            initial_state = self.definition.initial_states.get(robot_id, None)
            if initial_state is None:
                self.logger.warning(f"⚠️ No initial state for agent {robot_id}.")
                continue

            x = initial_state.get("x", None)
            y = initial_state.get("y", None)
            psi = initial_state.get("psi", None)

            agent.set_state(x=x, y=y, psi=psi)

        for static_id in self.definition.virtual_statics:
            static = self.experiment_handler.agent_manager.simulation.new_static(static_id)
            if static is None:
                self.logger.error(f"❌ Could not create static {static_id}.")
                return False

            initial_state = self.definition.initial_states.get(static_id, None)
            if initial_state is None:
                self.logger.warning(f"⚠️ No initial state for static {static_id}.")
                continue

            x = initial_state.get("x", None)
            y = initial_state.get("y", None)
            psi = initial_state.get("psi", None)
            static.set_state(x=x, y=y, psi=psi)

        self.logger.info("Simulation set up successfully ✅")

        # 5. Generate a movement plan for the initial states of the experimental agents
        self.logger.info("Generating initial movement plan ...")
        actions = []

        for robot_id in self.definition.robots:
            if robot_id not in self.definition.initial_states:
                self.logger.warning(f"⚠️ No initial state for agent {robot_id}.")
                continue

            move_action = Move(
                id=f"initial_movement_{robot_id}",
                agent_id=robot_id,
                element=CoordinatedMoveTo(
                    x=self.definition.initial_states[robot_id]["x"],
                    y=self.definition.initial_states[robot_id]["y"],
                    psi_end=self.definition.initial_states[robot_id]["psi"],
                ),
                blocking=True
            )
            actions.append(move_action)

        if len(actions) > 0:
            plan = NavigatorPlan(id='initial_movements',
                                 actions=actions)

            load_result = self.experiment_handler.agent_manager.navigator.load_plan(plan)

            if not load_result:
                self.logger.error("❌ Could not load movement plan.")
                return False

            self.logger.info("Initial movement plan loaded successfully ✅")

            self.logger.info("Moving agents to initial positions ...")
            result = self.experiment_handler.agent_manager.navigator.run_current_plan(blocking=True, timeout=15)

            if not result:
                self.logger.error("❌ Could not move agents to initial positions.")
                return False
            self.logger.info("Agents moved successfully ✅")

        self.logger.info("Experiment ready ✅")
        return True


# ======================================================================================================================
@dataclasses.dataclass
class ExperimentAgentContainer:
    id: str
    agent: AgentContainer
    algorithm: AlgorithmAgentContainer


@dataclasses.dataclass
class ExperimentStaticContainer:
    id: str
    static: StaticContainer
    algorithm: AlgorithmAgentContainer


# === EXPERIMENT HANDLER ===============================================================================================


@dataclasses.dataclass
class ExperimentSettings:
    update_time_algorithm: float = 0.2
    update_time_agents: float = 0.1

    initial_agent_state_algorithm: Union[AlgorithmAgentState, np.ndarray] = dataclasses.field(
        default_factory=lambda: np.array([0.0, 0.0, 0.0])
    )

    initial_agent_covariance_algorithm: np.ndarray = dataclasses.field(default_factory=lambda: 1e3 * np.eye(3))
    initial_static_covariance_algorithm: np.ndarray = dataclasses.field(default_factory=lambda: 1e-3 * np.eye(3))


class AlgorithmState(enum.StrEnum):
    RUNNING = "running"
    IDLE = "idle"


class ExperimentState(enum.StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"


class Sample:
    tick: int
    time: float
    experiment_id: str
    experiment: ExperimentSample
    agents: AgentManager_Sample  # Sample containing all true agent data
    # testbed: TestbedManager_Sample
    algorithm: AlgorithmManager_Sample


class FRODO_ExperimentManager:
    agents: dict[str, ExperimentAgentContainer]
    statics: dict[str, ExperimentStaticContainer]

    agent_manager: FRODO_AgentManager
    algorithm_manager: FRODO_AlgorithmManager
    algorithm_state: AlgorithmState = AlgorithmState.IDLE
    experiment_state: ExperimentState = ExperimentState.IDLE

    current_experiment: FRODO_Experiment | None = None

    step: int = 0

    _exit: bool = False
    _thread: threading.Thread

    # === INIT =========================================================================================================
    def __init__(self,
                 settings: ExperimentSettings,
                 agent_manager: FRODO_AgentManager,
                 algorithm_manager: FRODO_AlgorithmManager, ):
        self.settings = settings
        self.agents = {}
        self.statics = {}
        self.commands = self.Commands(self)
        self.logger = Logger('Experiment Handler', 'DEBUG')

        self.agent_manager = agent_manager
        self.algorithm_manager = algorithm_manager

        self.timer = IntervalTimer(interval=self.settings.update_time_agents, raise_race_condition_error=False)
        self._thread = threading.Thread(target=self._task, daemon=True)
        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.warning("Starting Experiment Handler in thread. This is for debug purposes only.")
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self._exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def initialize_agents(self, **overrides):
        self.logger.info("Initializing agents ...")
        self.agents = {}
        self.statics = {}

        settings = copy.copy(self.settings)
        update_dataclass_from_dict(settings, overrides)

        # Reset and populate the algorithm manager
        self.algorithm_manager.reset_algorithms()

        algorithm_agents: list[AlgorithmAgentConfig] = []

        # Get all the agents from the agent manager
        for agent_id, container in self.agent_manager.agents.items():
            new_config = AlgorithmAgentConfig(
                id=agent_id,
                anchor=False,
                initial_state=settings.initial_agent_state_algorithm,
                initial_covariance=settings.initial_agent_covariance_algorithm
            )
            algorithm_agents.append(new_config)

        for static_id, container in self.agent_manager.statics.items():
            new_config = AlgorithmAgentConfig(
                id=static_id,
                anchor=True,
                initial_state=np.array([container.state.x, container.state.y, container.state.psi]),
                initial_covariance=settings.initial_static_covariance_algorithm
            )
            algorithm_agents.append(new_config)

        # Initialize the algorithm manager
        self.algorithm_manager.initialize(algorithm_agents)

        # Initialize the agents
        for agent_id, container in self.agent_manager.agents.items():
            new_container = ExperimentAgentContainer(
                id=agent_id,
                agent=container,
                algorithm=self.algorithm_manager.agents[agent_id]
            )
            self.agents[agent_id] = new_container

        for static_id, container in self.agent_manager.statics.items():
            new_container = ExperimentStaticContainer(
                id=static_id,
                static=container,
                algorithm=self.algorithm_manager.agents[static_id]
            )
            self.statics[static_id] = new_container

        self.logger.info("Agents initialized successfully.")

    # ------------------------------------------------------------------------------------------------------------------
    def run_experiment(self, experiment: FRODO_Experiment | FRODO_Experiment_Definition):
        if self.experiment_state != ExperimentState.IDLE:
            self.logger.error("Experiment is already running.")
            return

        if isinstance(experiment, FRODO_Experiment_Definition):
            experiment = FRODO_Experiment(definition=experiment)

        experiment.initialize(self)

        # Attach events!!!!

        experiment.start()

    # ------------------------------------------------------------------------------------------------------------------
    def run_experiment_from_file(self, file: str):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        """
        Runs the update on the whole experiment (simulation, agent manager, algorithm manager ...)
        """

        # Update the agent manager?
        self.agent_manager.update()

        if self.algorithm_state == AlgorithmState.RUNNING:
            # 1. Do the prediction
            self._prediction()

            # 2. Do the correction
            self._correction()

        # Gather the sample
        self.step += 1

    # ------------------------------------------------------------------------------------------------------------------
    def start_algorithm(self):
        self.algorithm_manager.restart()
        self.algorithm_state = AlgorithmState.RUNNING

    # ------------------------------------------------------------------------------------------------------------------
    def stop_algorithm(self):
        self.algorithm_state = AlgorithmState.IDLE

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> Sample:
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self):
        raise NotImplementedError

    # === PRIVATE METHODS ==============================================================================================
    def _prediction(self):
        # we need to get the agent inputs and we need to put those in the algorithm manager
        prediction_data = {}

        for agent_id, container in self.agents.items():
            prediction_data[agent_id] = AlgorithmAgentUpdateData(
                input=AlgorithmAgentInput(
                    v=container.agent.input.v,
                    psi_dot=container.agent.input.psi_dot
                )
            )

        self.algorithm_manager.prediction(prediction_data)

    # ------------------------------------------------------------------------------------------------------------------
    def _correction(self):

        # Collect the measurements and update the algorithm manager
        correction_data = {}

        for agent_id, container in self.agents.items():
            agent_correction_data = []

            for measurement in container.agent.measurements:
                measurement_converted = AlgorithmAgentMeasurement(
                    agent_from=agent_id,
                    agent_to=measurement.agent_to,
                    measurement=measurement.measurement,
                    covariance=measurement.covariance
                )
                agent_correction_data.append(measurement_converted)

            correction_data[agent_id] = agent_correction_data

        self.algorithm_manager.correction(correction_data)

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        self.timer.reset()
        while not self._exit:
            self.update()
            self.timer.sleep_until_next()

    # === CLASSES ======================================================================================================
    class Commands(CommandSet):

        def __init__(self, handler: FRODO_ExperimentManager):
            super().__init__('experiment')
            self.handler = handler

            example_command = Command(
                name='example',
                function=self._example_experiment,
                arguments=None
            )

            self.addCommand(example_command)

            info_command = Command(
                name='info',
                function=self._info,
            )
            self.addCommand(info_command)

        # --------------------------------------------------------------------------------------------------------------
        def _info(self):
            self.handler.logger.info(
                f"Experiment State: {self.handler.experiment_state}. Active Experiment: {self.handler.current_experiment.definition.id if self.handler.current_experiment is not None else 'None'}")

        # --------------------------------------------------------------------------------------------------------------
        def _example_experiment(self):
            self.handler.logger.info("Running example experiment")

            experiment_definition = FRODO_Experiment_Definition(
                id="example",
                virtual_robots=["vfrodo1", "vfrodo2"],
                virtual_statics=['vstatic1'],
                initial_states={
                    "vfrodo1": {"x": 0.25, "y": 0.25, "psi": 1.57},
                    "vfrodo2": {"x": 2.75, "y": 1.5, "psi": -3.14159},
                    "vstatic1": {"x": 1.5, "y": 1.5, "psi": 0.0}
                },
                actions=[
                    Speak(
                        id="speak1",
                        text="Hello World!",
                        time=5,
                    ),
                    Speak(
                        id="speak2",
                        text="Action 2",
                        after="speak1",
                    ),
                    Speak(
                        id="speak3",
                        text="Action 3",
                        time=15
                    )
                ]
            )
            experiment = FRODO_Experiment(definition=experiment_definition)
            self.handler.run_experiment(experiment)
