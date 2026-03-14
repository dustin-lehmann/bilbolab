from __future__ import annotations

import dataclasses
import enum
import math
import time

import numpy as np
import qmt

import extensions.simulation.src.core as core
from applications.FRODO.definitions import get_simulated_agent_definition_by_id
from applications.FRODO.navigation.navigator import Navigator, NavigatorExecutionMode, NavigatedObjectState, \
    MoveTo, NavigatorSpeedControlMode, TurnTo, TurnToPoint
from applications.FRODO.simulation.frodo_simulation_utils import is_view_obstructed
from applications.FRODO.utilities.measurements import agent_is_in_fov
from core.utils.dataclass_utils import update_dataclass_from_dict
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.files import get_absolute_path, get_absolute_path
from core.utils.logging_utils import Logger
from core.utils.states import State
from extensions.tools.cli.cli import CommandSet, Command, CommandArgument
from extensions.hardware.joystick.joystick_manager import Joystick
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS, Object
from extensions.simulation.src.objects.base_environment import BaseEnvironment
from extensions.simulation.src.objects.frodo.frodo import FRODO_DynamicAgent, FRODO_Input
from robots.frodo.frodo_definitions import FRODO_ControlMode
from applications.FRODO.utilities.measurement_model import measurement_model_from_file

# Global registries
SIMULATED_AGENTS: dict[str, "FRODO_VisionAgent"] = {}
SIMULATED_STATICS: dict[str, FRODO_Static] = {}

# ======================================================================================================================
USE_AGENT_DEFINITIONS = True


# ======================================================================================================================
class FRODO_ENVIRONMENT_ACTIONS(enum.StrEnum):
    PREDICTION = 'frodo_prediction'
    MEASUREMENT = 'frodo_measurement'
    COMMUNICATION = 'frodo_communication'
    ESTIMATION = 'frodo_estimation'
    CORRECTION = 'frodo_correction'


# ======================================================================================================================
class FrodoEnvironment(BaseEnvironment):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger = Logger('FRODO ENV')
        self.logger.setLevel('INFO')

        # Put actions between communication and logic
        core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.PREDICTION,
                               object=self,
                               function=self.action_prediction,
                               priority=21,
                               parent=self.scheduling.actions['objects'])

        # Dyanmics has priority 50

        # Put actions between communication and logic
        core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.MEASUREMENT,
                               object=self,
                               function=self.action_measurement,
                               priority=81,
                               parent=self.scheduling.actions['objects'])

        core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.CORRECTION,
                               object=self,
                               function=self.action_frodo_communication,
                               priority=86,
                               parent=self.scheduling.actions['objects'])

        # OUTPUT HAS 100

        # core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.ESTIMATION,
        #                        object=self,
        #                        function=self.action_estimation,
        #                        priority=86,
        #                        parent=self.scheduling.actions['objects'])

    # ------------------------------------------------------------------------------------------------------------------
    def start(self, *args, **kwargs):
        self.logger.info("Starting FRODO Simulation Environment")
        super().start(*args, **kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def action_prediction(self):
        self.logger.debug(f"{self.scheduling.tick}: Action Frodo Prediction")

    # ------------------------------------------------------------------------------------------------------------------
    def action_measurement(self):
        self.logger.debug(f"{self.scheduling.tick}: Action Frodo Measurement")

    # ------------------------------------------------------------------------------------------------------------------
    def action_frodo_communication(self):
        self.logger.debug(f"{self.scheduling.tick}: Action Frodo Communication")

    # ------------------------------------------------------------------------------------------------------------------
    def action_estimation(self):
        self.logger.debug(f"{self.scheduling.tick}: Action Frodo Estimation")

    # ------------------------------------------------------------------------------------------------------------------
    def action_dynamics(self, *args, **kwargs):
        self.logger.debug(f"{self.scheduling.tick}: Action Frodo Dynamics")
        super().action_dynamics(*args, **kwargs)


# ======================================================================================================================
class FRODO_SimulationObject(Object):
    """
    Base mixin for any object that can live in the simulation/world and be measured/occlude vision.
    Expected attributes (by convention):
      - state with x, y, psi (for statics / many dynamics)
      - or .position -> np.ndarray shape (2,)
      - optional .size (diameter) used for occlusion modeling
    """
    agent_id: str
    ...


# === FRODO SIMULATED AGENT ============================================================================================
@dataclasses.dataclass
class SimulatedAgentMeasurement:
    object_from: FRODO_SimulationObject
    object_to: FRODO_SimulationObject
    position: np.ndarray  # relative position in agent (body) frame (x,y)
    psi: float  # relative heading of target w.r.t. agent heading
    covariance: np.ndarray  # 3x3 covariance for [dx, dy, dpsi]

    def as_vector(self):
        return np.asarray([self.position[0], self.position[1], self.psi, ])


# ======================================================================================================================
@dataclasses.dataclass
class FRODO_VisionAgent_Config:
    fov: float = np.deg2rad(100)
    vision_radius: float = 1.5
    size: float = 0.2
    color: list | tuple = dataclasses.field(default_factory=lambda: [.8, .8, .8])


class FRODO_VisionAgent(FRODO_DynamicAgent, FRODO_SimulationObject):
    measurements: list[SimulatedAgentMeasurement]

    config: FRODO_VisionAgent_Config

    control_mode: FRODO_ControlMode = FRODO_ControlMode.NAVIGATION

    navigator: Navigator | None

    joystick: Joystick | None = None

    cli: FRODO_VisionAgent_CommandSet

    # === INIT =========================================================================================================
    def __init__(self, agent_id,
                 Ts=None,
                 config: FRODO_VisionAgent_Config = None,
                 *args,
                 **kwargs):

        super().__init__(agent_id, Ts=Ts, *args, **kwargs)

        self.logger = Logger(self.agent_id)
        self.logger.setLevel('INFO')

        if config is None:
            config = FRODO_VisionAgent_Config()

        self.config = config

        self.navigator = Navigator(mode=NavigatorExecutionMode.EXTERNAL,
                                   speed_control_mode=NavigatorSpeedControlMode.SPEED_CONTROL,
                                   speed_command_function=self._navigator_set_speed,
                                   state_fetch_function=self._navigator_get_state,
                                   id=self.agent_id)

        core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.MEASUREMENT,
                               object=self,
                               function=self.action_measurement,
                               priority=1)

        core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.COMMUNICATION,
                               object=self,
                               function=self.action_frodo_communication,
                               priority=2)

        core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.ESTIMATION,
                               object=self,
                               function=self.action_estimation,
                               priority=3)

        self.scheduling.actions['output'].addAction(self.action_custom_output)

        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._control)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self._input_function)

        self.input = [0, 0]
        self.measurements = []

        self.measurement_model = measurement_model_from_file(get_absolute_path('./model.yaml'))

        self.cli = FRODO_VisionAgent_CommandSet(self)

    # === METHODS ======================================================================================================
    def action_prediction(self):
        self.logger.debug(f"{self.agent_id}: Action Frodo Prediction")

    def action_measurement(self):
        self._generate_measurements()

    def action_frodo_communication(self):
        self.logger.debug(f"{self.agent_id}: Action Frodo Communication")

    def action_estimation(self):
        self.logger.debug(f"{self.agent_id}: Action Frodo Estimation")

    def action_custom_output(self):
        self.logger.debug(f"{self.agent_id}: {self.state}")

    def set_mode(self, mode: FRODO_ControlMode):
        self.control_mode = mode

    # ------------------------------------------------------------------------------------------------------------------
    def assign_joystick(self, joystick):
        self.logger.info(f"{self.agent_id}: Assigning Joystick {joystick.id} ({joystick.name})")
        self.joystick = joystick

        self.navigator.stopNavigation()
        self.set_mode(FRODO_ControlMode.EXTERNAL)

    # ------------------------------------------------------------------------------------------------------------------
    def remove_joystick(self):
        self.logger.info(f"{self.agent_id}: Removing Joystick {self.joystick.id} ({self.joystick.name})")
        self.joystick = None
        self.input = [0, 0]
        self.set_mode(FRODO_ControlMode.NAVIGATION)

    # ------------------------------------------------------------------------------------------------------------------
    def move_to(self, x, y, force=False):

        # Start Navigation of not already started
        self.navigator.startNavigation()

        element = MoveTo(
            x=x,
            y=y
        )
        self.navigator.addElement(element, force_element=force)

    # ------------------------------------------------------------------------------------------------------------------
    def turn_to(self, psi):
        self.navigator.startNavigation()

        element = TurnTo(
            psi=psi
        )
        self.navigator.addElement(element)

    # ------------------------------------------------------------------------------------------------------------------
    def turn_to_point(self, x, y):
        self.navigator.startNavigation()
        element = TurnToPoint(
            x=x,
            y=y
        )
        self.navigator.addElement(element)

    # ------------------------------------------------------------------------------------------------------------------
    def abort_navigation_element(self):
        self.navigator.skip_element()

    # ------------------------------------------------------------------------------------------------------------------
    def set_state(self, x: float = None, y: float = None, psi: float = None, v: float = None, psi_dot: float = None):
        if x is not None:
            self.state.x = x
        if y is not None:
            self.state.y = y
        if psi is not None:
            self.state.psi = psi
        if v is not None:
            self.state.v = v
        if psi_dot is not None:
            self.state.psi_dot = psi_dot

    # === PRIVATE METHODS ==============================================================================================
    def _generate_measurements(self):
        """
        Simulated vision agent:
        - Computes measurements to ALL objects from global registries:
            * Agents: SIMULATED_AGENTS + REAL_AGENTS (excluding self)
            * Statics: SIMULATED_STATICS + REAL_STATICS
        - Uses FOV, range, and occlusion checks
        - Measurements are expressed in the agent's local frame
        """
        self.measurements = []
        # Targets from globals
        agent_targets = [a for a in list(SIMULATED_AGENTS.values())
                         if getattr(a, 'agent_id', None) != self.agent_id]
        static_targets = list(SIMULATED_STATICS.values())

        # Occluders: everything except self (we'll exclude the current target per check)
        occluders: list[FRODO_SimulationObject] = []
        occluders.extend(agent_targets)
        occluders.extend(static_targets)

        def obj_position(o: FRODO_SimulationObject) -> np.ndarray:
            if hasattr(o, 'position'):
                return np.asarray(o.position).reshape(2)
            elif hasattr(o, 'state'):
                return np.array([o.state.x, o.state.y])
            else:
                raise AttributeError("Object has no position/state")

        def obj_psi(o: FRODO_SimulationObject) -> float:
            if hasattr(o, 'state'):
                return float(o.state.psi)
            else:
                # For objects without orientation, zero is fine
                return 0.0

        def obj_size(o: FRODO_SimulationObject) -> float:
            # Diameter; fall back to a small default if not present
            return float(getattr(o, 'size', 0.2))

        own_pos = np.array([self.state.x, self.state.y])
        own_psi = float(self.state.psi)

        # Local-frame transform: world -> agent body
        R_world_to_body = np.array([
            [math.cos(own_psi), math.sin(own_psi)],
            [-math.sin(own_psi), math.cos(own_psi)]
        ])

        for target in [*agent_targets, *static_targets]:
            t_pos = obj_position(target)

            # FOV + range check
            if not agent_is_in_fov(
                    agent_from_state=self.state.asarray(),
                    agent_to_state=target.state.asarray(),
                    agent_from_fov=self.config.fov,
                    agent_from_min_distance=0,
                    agent_from_max_distance=self.config.vision_radius
            ):
                continue

            # Occlusion check (ignore the target itself)
            other_occluders = [o for o in occluders if o is not target]
            obstacles = []
            for o in other_occluders:
                c = obj_position(o)
                r = obj_size(o) * 0.5  # size is diameter -> radius
                obstacles.append((c, r))

            if is_view_obstructed(own_pos, t_pos, obstacles):
                continue

            # Relative vector in world frame -> transform to body frame
            rel_vec_world = t_pos - own_pos
            rel_vec_body = R_world_to_body @ rel_vec_world

            # Relative orientation (target vs self)
            rel_psi = qmt.wrapToPi(obj_psi(target) - own_psi)

            cov = self.measurement_model.covariance.covariance(
                measurement=np.asarray([rel_vec_body[0], rel_vec_body[1], rel_psi]),
                v=self.state.v,
                psi_dot=self.state.psi_dot
            )
            measurement = SimulatedAgentMeasurement(
                object_from=self,
                object_to=target,
                position=rel_vec_body,
                psi=rel_psi,
                covariance=cov
            )
            self.measurements.append(measurement)

    # ------------------------------------------------------------------------------------------------------------------
    def _control(self):
        if self.control_mode == FRODO_ControlMode.NAVIGATION:
            self.navigator.update()

    # ------------------------------------------------------------------------------------------------------------------
    def _navigator_set_speed(self, v, psi_dot):
        if self.control_mode == FRODO_ControlMode.NAVIGATION:
            self.input.v = v
            self.input.psi_dot = psi_dot

    # ------------------------------------------------------------------------------------------------------------------
    def _navigator_get_state(self) -> NavigatedObjectState:
        return NavigatedObjectState(x=self.state.x, y=self.state.y, psi=self.state.psi, v=self.state.v,
                                    psi_dot=self.state.psi_dot)

    # ------------------------------------------------------------------------------------------------------------------
    def _input_function(self):
        if self.joystick is None or self.control_mode != FRODO_ControlMode.EXTERNAL:
            return

        axis_forward = self.joystick.getAxis('LEFT_VERTICAL')

        if abs(axis_forward) < 0.05:
            axis_forward = 0

        axis_turn = self.joystick.getAxis('RIGHT_HORIZONTAL')

        if abs(axis_turn) < 0.05:
            axis_turn = 0

        self.input.v = -3 * axis_forward * 0.2
        self.input.psi_dot = -3 * axis_turn


# ======================================================================================================================
@dataclasses.dataclass
class FRODO_Static_State(State):
    x: float
    y: float
    psi: float


class FRODO_Static(FRODO_SimulationObject):
    state: FRODO_Static_State
    size: float = 0.2  # optional diameter for occlusion

    def __init__(self, static_id, x: float = None, y: float = None, psi: float = None, size: float = 0.2, *args,
                 **kwargs):
        super().__init__(static_id, *args, **kwargs)
        self.agent_id = static_id
        self.size = size
        self.state = FRODO_Static_State(0, 0, 0)
        self.set_state(x, y, psi)
        print(f"Created static {static_id} at ({self.state.x}, {self.state.y})")

    # ------------------------------------------------------------------------------------------------------------------
    def set_state(self, x: float = None, y: float = None, psi: float = None):
        if x is not None:
            self.state.x = x
        if y is not None:
            self.state.y = y
        if psi is not None:
            self.state.psi = psi


@event_definition
class FRODO_Simulation_Events:
    initialized: Event
    update: Event
    new_agent: Event = Event(copy_data_on_set=False)
    removed_agent: Event = Event(copy_data_on_set=False)
    new_static: Event = Event(copy_data_on_set=False)
    removed_static: Event = Event(copy_data_on_set=False)


# === FRODO SIMULATION =================================================================================================
class FRODO_Simulation:
    environment: FrodoEnvironment

    cli: FRODO_Simulation_CommandSet | None = None

    agents: dict[str, FRODO_VisionAgent]
    statics: dict[str, FRODO_Static]

    events: FRODO_Simulation_Events

    # === INIT =========================================================================================================
    def __init__(self, Ts=0.05):
        self.Ts = Ts
        self.logger = Logger('FRODO Simulation', 'DEBUG')
        self.environment = FrodoEnvironment(Ts=Ts, run_mode='rt')

        self.events = FRODO_Simulation_Events()

        self.cli = FRODO_Simulation_CommandSet(self)

        self.environment.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self.events.update.set)

        self.agents = SIMULATED_AGENTS
        self.statics = SIMULATED_STATICS

        register_exit_callback(self.stop)

    # === METHODS ======================================================================================================
    def init(self):
        self.environment.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info("Starting FRODO Simulation")
        self.environment.start(thread=True, )
        self.events.initialized.set()

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        self.logger.info("Stopping FRODO Simulation")
        self.environment.stop()

    # ------------------------------------------------------------------------------------------------------------------
    def new_agent(self,
                  agent_id: str,
                  config: FRODO_VisionAgent_Config | None = None,
                  *args,
                  **kwargs) -> FRODO_VisionAgent | None:

        if agent_id in SIMULATED_AGENTS:
            self.logger.warning(f"Simulated agent {agent_id} already exists. Cannot add it again")
            return None

        if USE_AGENT_DEFINITIONS:
            agent_definition = get_simulated_agent_definition_by_id(agent_id)
            if agent_definition is None:
                self.logger.warning(
                    f"Agent definition for {agent_id} not found. Cannot add it. "
                    f"Either disable the use of predefined agent definitions by setting USE_AGENT_DEFINITIONS to False "
                    f"or define the agent definition in the definitions.py file.")
                return None

            config = FRODO_VisionAgent_Config(
                fov=agent_definition.fov,
                vision_radius=agent_definition.vision_radius,
                color=agent_definition.color,
                size=agent_definition.size,
            )

        if config is None:
            config = FRODO_VisionAgent_Config()

        update_dataclass_from_dict(config, kwargs)

        agent = FRODO_VisionAgent(agent_id, self.Ts, *args, **kwargs)
        self.add_agent(agent)
        return agent

    # ------------------------------------------------------------------------------------------------------------------
    def add_agent(self,
                  agent: FRODO_VisionAgent) -> FRODO_VisionAgent:

        global SIMULATED_AGENTS
        SIMULATED_AGENTS[agent.agent_id] = agent

        # Enforce Ts on agent
        agent.scheduling.Ts = self.Ts
        agent.dynamics.Ts = self.Ts

        self.environment.addAgent(agent)
        self.logger.info(f"Simulated agent {agent.agent_id} added")
        self.cli.addChild(agent.cli)

        self.events.new_agent.set(agent)

        return agent

    # ------------------------------------------------------------------------------------------------------------------
    def remove_agent(self, agent: FRODO_VisionAgent | str):
        if isinstance(agent, FRODO_VisionAgent):
            agent = agent.agent_id

        if agent in SIMULATED_AGENTS:
            self.environment.removeObject(SIMULATED_AGENTS[agent])
            self.cli.removeChild(SIMULATED_AGENTS[agent].cli)
            del SIMULATED_AGENTS[agent]
            self.logger.info(f"Simulated agent {agent} removed")
            self.events.removed_agent.set(agent)
        else:
            self.logger.warning(f"Simulated agent {agent} not found. Cannot remove it from the simulation")

    # ------------------------------------------------------------------------------------------------------------------
    def new_static(self, static_id: str, *args, **kwargs) -> FRODO_Static:
        static = FRODO_Static(static_id, *args, **kwargs)
        self.add_static(static)
        return static

    # ------------------------------------------------------------------------------------------------------------------
    def add_static(self, static: FRODO_Static) -> FRODO_Static | None:

        if static.agent_id in SIMULATED_STATICS:
            self.logger.warning(f"Simulated static {static.agent_id} already exists. Cannot add it again")
            return None

        SIMULATED_STATICS[static.agent_id] = static
        # statics are environment "objects" (not agents)
        self.environment.addObject(static)
        self.logger.info(f"Simulated static {static.agent_id} added")
        self.events.new_static.set(static)
        return static

    # ------------------------------------------------------------------------------------------------------------------
    def remove_static(self, static: str | FRODO_SimulationObject):
        # allow passing id or object
        if not isinstance(static, str):
            # try to find id by object identity
            found_id = None
            for sid, sobj in SIMULATED_STATICS.items():
                if sobj is static:
                    found_id = sid
                    break
            static_id = found_id
        else:
            static_id = static

        if static_id in SIMULATED_STATICS:
            self.environment.removeObject(SIMULATED_STATICS[static_id])
            self.logger.info(f"Simulated static {static_id} removed")
            self.events.removed_static.set(static)
            del SIMULATED_STATICS[static_id]
        else:
            self.logger.warning(f"Simulated static {static_id} not found. Cannot remove it from the simulation")

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self):
        for agent in list(SIMULATED_AGENTS.values()):
            self.remove_agent(agent)
        for static in list(SIMULATED_STATICS.values()):
            self.remove_static(static)
    # === PRIVATE METHODS ==============================================================================================


class FRODO_VisionAgent_CommandSet(CommandSet):

    def __init__(self, agent: FRODO_VisionAgent):
        super().__init__(name=agent.agent_id)
        self.agent = agent

        command_move_to = Command(
            name='move_to',
            description='Move the agent to a given position',
            arguments=[
                CommandArgument(name='x', type=float, description='x position'),
                CommandArgument(name='y', type=float, description='y position'),
                CommandArgument(name='force', short_name='f', type=bool, is_flag=True, optional=True, default=False),
            ],
            function=self.agent.move_to,
            allow_positionals=True
        )

        command_turn_to = Command(
            name='turn_to',
            description='Turn the agent to a given orientation',
            arguments=[
                CommandArgument(name='psi', type=float, description='orientation in radians'),
            ],
            function=self.agent.turn_to,
            allow_positionals=True
        )

        command_turn_to_point = Command(
            name='turn_to_point',
            description='Turn the agent to a given orientation (pointing towards the given position)',
            arguments=[
                CommandArgument(name='x', type=float, description='x position'),
                CommandArgument(name='y', type=float, description='y position'),
            ],
            function=self.agent.turn_to_point,
            allow_positionals=True
        )

        command_skip_element = Command(
            name='skip',
            description='',
            arguments=[],
            function=self.agent.abort_navigation_element,
            allow_positionals=False
        )

        command_set_state = Command(
            name='set_state',
            description='Set the agent state directly',
            arguments=[
                CommandArgument(name='x', type=float, description='x position', optional=True, default=None),
                CommandArgument(name='y', type=float, description='y position', optional=True, default=None),
                CommandArgument(name='psi', type=float, description='orientation in radians', optional=True,
                                default=None),
            ],
            function=self.agent.set_state,
            allow_positionals=True
        )

        self.addCommand(command_move_to)
        self.addCommand(command_turn_to)
        self.addCommand(command_turn_to_point)
        self.addCommand(command_set_state)
        self.addCommand(command_skip_element)


class FRODO_Simulation_CommandSet(CommandSet):
    def __init__(self, sim: FRODO_Simulation):
        super().__init__(name='simulation')
        self.sim = sim
        command_list = Command(
            name='list',
            description='List all agents and statics',
            arguments=[],
            function=lambda: self.sim.logger.info(
                f"Agents: {list(SIMULATED_AGENTS.keys())}\nStatic: {list(SIMULATED_STATICS.keys())}")
        )

        command_add_agent = Command(
            name='add_agent',
            description='Add a simulated agent',
            arguments=[
                CommandArgument(name='agent_id', short_name='i', type=str, description='Agent ID'),
                CommandArgument(name='fov_deg', short_name='f', type=float, description='Field of view in degrees',
                                default=100),
                CommandArgument(name='vision_radius', short_name='r', type=float, description='Vision radius in meters',
                                default=1.5),
                CommandArgument(name='interactive', short_name='i', type=bool,
                                description='Whether to use interactive mode',
                                default=False),
                CommandArgument(name='x', type=float, description='x position', optional=True, default=None),
                CommandArgument(name='y', type=float, description='y position', optional=True, default=None),
                CommandArgument(name='psi', type=float, description='orientation in radians', optional=True, )
            ],
            function=self.sim.new_agent,
        )

        command_remove_agent = Command(
            name='remove_agent',
            description='Remove an agent',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='agent', short_name='a', type=str, description='Agent ID'),
            ],
            function=self.sim.remove_agent,
        )

        command_add_static = Command(
            name='add_static',
            description='Add a static object',
            arguments=[
                CommandArgument(name='static_id', short_name='i', type=str, description='Static ID'),
                CommandArgument(name='x', type=float, description='x position', optional=True, default=None),
                CommandArgument(name='y', type=float, description='y position', optional=True, default=None),
                CommandArgument(name='psi', type=float, description='orientation in radians', optional=True,
                                default=None),
            ],
            function=self.sim.new_static,
        )

        self.addCommand(command_list)
        self.addCommand(command_add_agent)
        self.addCommand(command_add_static)
        self.addCommand(command_remove_agent)

    if __name__ == '__main__':
        sim = FRODO_Simulation()
        sim.init()

        # Example: add one simulated agent
        sim.new_agent(agent_id='frodo1', fov_deg=100, vision_radius=1.5)

        sim.start()

        while True:
            time.sleep(10)
