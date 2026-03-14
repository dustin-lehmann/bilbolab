import dataclasses
import enum
import math
import time
import re

import numpy as np
import qmt

from applications.FRODO.algorithm.algorithm import AlgorithmAgentInput, get_covariance_ellipse
from applications.FRODO.algorithm.algorithm_centralized_alternative import CentralizedAgent, CentralizedAlgorithm
from applications.FRODO.algorithm.algorithm_distributed import AlgorithmAgent, AlgorithmAgentState, \
    AlgorithmAgentMeasurement, DistributedAlgorithm, DistributedUpdateType, DistributedAgent
from applications.FRODO.frodo_application import AlgorithmState
from applications.FRODO.navigation.multi_agent_navigator import MultiAgentNavigator, NavigatorPlan, ActionGroup, Move, \
    Wait
from applications.FRODO.navigation.navigator import CoordinatedMoveTo, MoveTo
from applications.FRODO.navigation.utilities import FRODO_Sim_NavigatedObject

from applications.FRODO.simulation.frodo_simulation import FRODO_Simulation, FRODO_VisionAgent, \
    FRODO_VisionAgent_Interactive, FRODO_Static, FRODO_ENVIRONMENT_ACTIONS
from core.utils.colors import random_color_from_palette, get_color_from_palette, LIGHT_GREEN, LIGHT_RED, NamedColor
from core.utils.exit import register_exit_callback
from core.utils.files import get_absolute_path
from core.utils.logging_utils import Logger, LOGGING_COLORS, addLogRedirection
from core.utils.network.network import getHostIP
from core.utils.sound.sound import SoundSystem
from core.utils.time import setTimeout
from extensions.libs.babylon.src.babylon import BabylonVisualization
from extensions.libs.babylon.src.lib.objects.box.box import WallFancy
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.libs.babylon.src.lib.objects.frodo.frodo import BabylonFrodo
from extensions.libs.babylon.src.lib.objects.static.static import BabylonStatic
from extensions.tools.cli.cli import CommandSet, Command, CommandArgument, CLI
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.map.map import MapWidget
from extensions.gui.src.lib.map.map_objects import VisionAgent, MapObjectGroup, Point, CoordinateSystem, Agent, Line, \
    Circle, Ellipse
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.plot.realtime.rt_plot import RT_Plot_Widget, Y_Axis, TimeSeries
from extensions.hardware.joystick.joystick_manager import Joystick, JoystickManager
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

from core.utils.colors import darken_color

TS = 0.05

TESTBED_SIZE = [5, 5]
TESTBED_TILE_SIZE = 0.5

INITIAL_GUESS_AGENTS = np.asarray([0.01, 0.012, 0.002])
INITIAL_GUESS_AGENTS_COVARIANCE = 1e5 * np.diag([1, 1, 1])

STATIC_AGENTS_COVARIANCE = 1e-15 * np.diag([1, 1, 1])


@dataclasses.dataclass
class AlgorithmDisplayStates:
    distributed: bool = False
    centralized: bool = False


# === HELPERS ==========================================================================================================
def extract_number(s: str):
    # Search for a sequence of digits in the string
    match = re.search(r'\d+', s)
    if match:
        return int(match.group())  # Return the number as an integer
    return s  # If no number found, return the full string


@dataclasses.dataclass
class AlgorithmAgentMapContainer:
    agent: Agent
    covariance_ellipse: Ellipse
    group: MapObjectGroup


@dataclasses.dataclass
class AgentMapContainer:
    group: MapObjectGroup
    agent: VisionAgent
    measurements: MapObjectGroup
    lines: MapObjectGroup
    algorithm_centralized: AlgorithmAgentMapContainer
    algorithm_distributed: AlgorithmAgentMapContainer


@dataclasses.dataclass
class AgentPlotContainer:
    error_distributed: TimeSeries | None = None
    error_centralized: TimeSeries | None = None
    covariance_distributed: TimeSeries | None = None
    covariance_centralized: TimeSeries | None = None


@dataclasses.dataclass
class AgentContainer:
    agent: FRODO_VisionAgent
    babylon: BabylonFrodo
    map: AgentMapContainer
    plot: AgentPlotContainer
    color: list
    centralized_algorithm_agent: CentralizedAgent
    distributed_algorithm_agent: DistributedAgent


@dataclasses.dataclass
class StaticContainer:
    object: FRODO_Static
    babylon: BabylonStatic
    map: CoordinateSystem
    centralized_algorithm_agent: CentralizedAgent
    distributed_algorithm_agent: DistributedAgent


class FRODO_App_Standalone:
    simulation: FRODO_Simulation
    gui: GUI
    cli: CLI

    algorithm_centralized: CentralizedAlgorithm
    algorithm_distributed: DistributedAlgorithm

    agents: dict[str, AgentContainer]
    statics: dict[str, StaticContainer]

    joystick_manager: JoystickManager

    algorithm_state = AlgorithmState.STOPPED
    algorithm_display_states = AlgorithmDisplayStates(distributed=True, centralized=True)

    navigator: MultiAgentNavigator

    # === INIT =========================================================================================================
    def __init__(self):
        host = 'localhost'
        self.simulation = FRODO_Simulation(Ts=TS)
        self.babylon_visualization = BabylonVisualization(id='babylon', host=host, babylon_config={
            'title': 'FRODO Standalone'})
        self.simulation.environment.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.ENV_OUTPUT].addAction(
            self._simulationOutputStep)

        self.simulation.environment.scheduling.actions[FRODO_ENVIRONMENT_ACTIONS.PREDICTION].addAction(
            self._predictionStep)

        self.simulation.environment.scheduling.actions[FRODO_ENVIRONMENT_ACTIONS.MEASUREMENT].addAction(
            self._measurementStep)

        self.simulation.environment.scheduling.actions[FRODO_ENVIRONMENT_ACTIONS.CORRECTION].addAction(
            self._correctionStep)

        self.simulation.environment.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.DYNAMICS].addAction(
            self._dynamicsStep)

        self.simulation.environment.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(
            self._inputStep)

        self.navigator = MultiAgentNavigator()

        self.gui = GUI('frodo_simulation_standalone_gui', host=host, run_js=True)
        self.cli = CLI(id='frodo_simulation_standalone_cli', root=FRODO_Simulation_CLI(self))

        self.algorithm_centralized = CentralizedAlgorithm(Ts=TS)
        self.algorithm_distributed = DistributedAlgorithm(Ts=TS, update_method=DistributedUpdateType.CI)

        self.gui.cli_terminal.setCLI(self.cli)
        self.soundsystem = SoundSystem(primary_engine='etts', volume=1)
        self.joystick_manager = JoystickManager()

        self.logger = Logger('FRODO_Simulation_Standalone', 'DEBUG')

        self.agents = {}
        self.statics = {}
        addLogRedirection(self._logRedirection, minimum_level='DEBUG')

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self.simulation.init()
        self.joystick_manager.init()

        self._buildGUI()
        self._buildBabylon()

        self.cli.root.addChild(self.simulation.cli)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.gui.start()
        self.joystick_manager.start()
        self.simulation.start()
        self.babylon_visualization.start()
        self.logger.info("Start FRODO Simulation Standalone")
        self.soundsystem.speak('Start FRODO Simulation Standalone')

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.simulation.stop()
        self.gui.close()
        self.logger.info("Stop FRODO Simulation Standalone")
        self.soundsystem.speak('Stop FRODO Simulation Standalone')

    # ------------------------------------------------------------------------------------------------------------------
    def startAlgorithm(self):

        if self.algorithm_state == AlgorithmState.RUNNING:
            self.logger.warning("Algorithm is already running")
            return

        centralized_algorithm_agents = []
        distributed_algorithm_agents = []

        for agent_id, agent_container in self.agents.items():
            agent_container.centralized_algorithm_agent.state = AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS)
            agent_container.centralized_algorithm_agent.covariance = INITIAL_GUESS_AGENTS_COVARIANCE
            centralized_algorithm_agents.append(agent_container.centralized_algorithm_agent)

            agent_container.distributed_algorithm_agent.state = AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS)
            agent_container.distributed_algorithm_agent.covariance = INITIAL_GUESS_AGENTS_COVARIANCE
            distributed_algorithm_agents.append(agent_container.distributed_algorithm_agent)

        for static_id, static_container in self.statics.items():
            centralized_algorithm_agents.append(static_container.centralized_algorithm_agent)
            distributed_algorithm_agents.append(static_container.distributed_algorithm_agent)

        self.algorithm_centralized.initialize(centralized_algorithm_agents)
        self.algorithm_distributed.initialize(distributed_algorithm_agents)

        # Make all estimated agents visible
        for agent_id, agent_container in self.agents.items():
            agent_container.map.algorithm_centralized.group.visible(True)
            agent_container.map.algorithm_distributed.group.visible(True)

        # Clear the error plot
        self.error_plot.plot.remove_all_timeseries()
        self.covariance_plot.plot.remove_all_timeseries()

        # Add timeseries for each agent
        for agent_id, agent_container in self.agents.items():
            self.error_plot.plot.add_timeseries(agent_container.plot.error_distributed)
            self.covariance_plot.plot.add_timeseries(agent_container.plot.covariance_distributed)
            self.covariance_plot.plot.add_timeseries(agent_container.plot.covariance_centralized)

        self.algorithm_state = AlgorithmState.RUNNING
        self.logger.info("Start FRODO Algorithm")
        self.soundsystem.speak('Start FRODO Algorithm')

        # Print the initial covariances for each agent
        for agent_id, agent_container in self.agents.items():
            self.logger.important(
                f"{agent_id}: {agent_container.distributed_algorithm_agent.get_covariance_norm():.1f}")

    # ------------------------------------------------------------------------------------------------------------------
    def stopAlgorithm(self):
        self.algorithm_state = AlgorithmState.STOPPED
        self.logger.info("Stop FRODO Algorithm")
        self.soundsystem.speak('Stop FRODO Algorithm')

        # Make all estimated agents invisible
        for agent_id, agent_container in self.agents.items():
            agent_container.map.algorithm_centralized.group.visible(False)
            agent_container.map.algorithm_distributed.group.visible(False)

        # Remove the error plot
        self.error_plot.plot.remove_all_timeseries()

        # Remove the covariance plot
        self.covariance_plot.plot.remove_all_timeseries()

    # ------------------------------------------------------------------------------------------------------------------
    def addAgent(self, agent_id, fov, vision_radius, position=None, psi=0.0, interactive=False):

        if agent_id in self.agents:
            self.logger.warning(f'Agent with ID {agent_id} already exists')
            return

        if position is None:
            position = [0, 0]

        agent = self.simulation.add_agent(agent_id, fov, vision_radius, interactive)

        agent.state.x = position[0]
        agent.state.y = position[1]
        agent.state.psi = psi

        # Display
        agent_color = get_color_from_palette('bright', 9, len(self.agents) + 1)
        babylon_text = f"v{extract_number(agent_id)}"

        frodo_babylon = BabylonFrodo(agent_id,
                                     text=babylon_text,
                                     color=agent_color,
                                     fov=fov,
                                     vision_radius=vision_radius, )

        self.babylon_visualization.addObject(frodo_babylon)

        # Map
        map_container = AgentMapContainer(
            group=MapObjectGroup(id=f"map_group_{agent_id}"),
            agent=VisionAgent(agent_id, name=babylon_text, color=agent_color, fov=math.radians(fov),
                              vision_radius=vision_radius, ),
            measurements=MapObjectGroup(id=f"measurements_group_{agent_id}"),
            lines=MapObjectGroup(id=f"lines_group_{agent_id}"),
            algorithm_centralized=AlgorithmAgentMapContainer(
                agent=Agent(id=f"estimated_point_{agent_id}", name=f"{agent_id}_hat_c", x=position[0],
                            y=position[1], psi=0, visible=False),
                covariance_ellipse=Ellipse(id=f"covariance_ellipse_{agent_id}_c",
                                           x=position[0],
                                           y=position[1],
                                           rx=1,
                                           ry=0.5,
                                           color=agent_color,
                                           opacity=0.5,
                                           visible=False
                                           ),
                group=MapObjectGroup(id=f"algorithm_centralized_group_{agent_id}_c")
            ),
            algorithm_distributed=AlgorithmAgentMapContainer(
                agent=Agent(id=f"estimated_point_{agent_id}", name=f"{agent_id}_hat_d", x=position[0],
                            y=position[1], psi=0, visible=False),
                covariance_ellipse=Ellipse(id=f"covariance_ellipse_{agent_id}_d",
                                           x=position[0],
                                           y=position[1],
                                           rx=1,
                                           ry=0.5,
                                           color=agent_color,
                                           opacity=0.5,
                                           visible=False
                                           ),
                group=MapObjectGroup(id=f"algorithm_centralized_group_{agent_id}_d")
            )
        )

        # Add all objects to groups
        map_container.algorithm_centralized.group.addObject(map_container.algorithm_centralized.agent)
        map_container.algorithm_centralized.group.addObject(map_container.algorithm_centralized.covariance_ellipse)

        map_container.algorithm_distributed.group.addObject(map_container.algorithm_distributed.agent)
        map_container.algorithm_distributed.group.addObject(map_container.algorithm_distributed.covariance_ellipse)

        map_container.group.addObject(map_container.agent)
        map_container.group.addGroup(map_container.measurements)
        map_container.group.addGroup(map_container.lines)
        map_container.group.addGroup(map_container.algorithm_centralized.group)
        map_container.group.addGroup(map_container.algorithm_distributed.group)

        self.map.addGroup(map_container.group)

        centralized_agent = CentralizedAgent(agent_id,
                                             Ts=TS,
                                             state=AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS),
                                             covariance=INITIAL_GUESS_AGENTS_COVARIANCE,
                                             is_anchor=False)

        distributed_agent = DistributedAgent(agent_id,
                                             Ts=TS,
                                             state=AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS),
                                             covariance=INITIAL_GUESS_AGENTS_COVARIANCE,
                                             is_anchor=False)

        agent_plot_container = AgentPlotContainer(
            error_centralized=TimeSeries(id=f"agent_{agent_id}_error_centralized",
                                         y_axis="y_axis_1",
                                         name=agent_id,
                                         color=agent_color, ),
            error_distributed=TimeSeries(id=f"agent_{agent_id}_error_distributed",
                                         y_axis="y_axis_1",
                                         name=agent_id,
                                         color=agent_color,
                                         ),
            covariance_centralized=TimeSeries(id=f"agent_{agent_id}_covariance_centralized",
                                              y_axis="y_axis_2",
                                              name=f"{agent_id}_c",
                                              color=darken_color(agent_color, 0.4),
                                              ),
            covariance_distributed=TimeSeries(id=f"agent_{agent_id}_covariance_distributed",
                                              y_axis="y_axis_2",
                                              name=f"{agent_id}_d",
                                              color=agent_color,
                                              stepped=True
                                              )
        )

        self.agents[agent_id] = AgentContainer(
            agent=agent,
            babylon=frodo_babylon,
            map=map_container,
            color=agent_color,
            plot=agent_plot_container,
            centralized_algorithm_agent=centralized_agent,
            distributed_algorithm_agent=distributed_agent,

        )

    # ------------------------------------------------------------------------------------------------------------------
    def removeAgent(self, agent: str | AgentContainer):
        if isinstance(agent, AgentContainer):
            agent = agent.agent.agent_id

        # Check if there is such an agent in our agents
        if not agent in self.agents:
            self.logger.warning(f"Agent with ID {agent} does not exist")
            return

        agent = self.agents[agent]

        # Remove the agent from the simulation
        self.simulation.remove_agent(agent.agent)

        # Remove the agent from the GUI
        self.map.removeGroup(agent.map.group)
        self.error_plot.plot.remove_timeseries(agent.plot.error_distributed)
        self.covariance_plot.plot.remove_timeseries(agent.plot.covariance_distributed)
        self.covariance_plot.plot.remove_timeseries(agent.plot.covariance_centralized)

        # Remove it from Babylon
        self.babylon_visualization.removeObject(agent.babylon)

        del self.agents[agent.agent.agent_id]

    # ------------------------------------------------------------------------------------------------------------------
    def removeAllAgents(self):
        # Get a list of agent IDs to avoid modifying dictionary during iteration
        agent_ids = list(self.agents.keys())

        # Remove each agent
        for agent_id in agent_ids:
            self.removeAgent(agent_id)

        self.logger.info("All agents removed")

    # ------------------------------------------------------------------------------------------------------------------
    def addStatic(self, object_id, position, psi=0.0):
        if object_id in self.simulation.environment.objects:
            self.logger.warning(f'Object with ID {object_id} already exists')
            return

        static_obj = self.simulation.add_static(object_id)
        static_obj.state.x = position[0]
        static_obj.state.y = position[1]
        static_obj.state.psi = psi

        # Algorithm
        algorithm_state = AlgorithmAgentState(
            x=position[0],
            y=position[1],
            psi=psi,
        )

        centralized_agent = CentralizedAgent(object_id,
                                             state=algorithm_state,
                                             covariance=STATIC_AGENTS_COVARIANCE,
                                             Ts=TS,
                                             is_anchor=True)

        distributed_agent = DistributedAgent(object_id,
                                             state=algorithm_state,
                                             covariance=STATIC_AGENTS_COVARIANCE,
                                             Ts=TS,
                                             is_anchor=True)

        # Map
        map_object = CoordinateSystem(id=f"{object_id}", x=position[0], y=position[1], psi=psi, show_name=True)
        self.map.addObject(map_object)

        # Babylon
        babylon_object = BabylonStatic(f"static_{object_id}", x=position[0], y=position[1], psi=psi)
        self.babylon_visualization.addObject(babylon_object)

        static_container = StaticContainer(
            object=static_obj,
            babylon=babylon_object,
            map=map_object,
            centralized_algorithm_agent=centralized_agent,
            distributed_algorithm_agent=distributed_agent,
        )
        self.statics[object_id] = static_container

    # ------------------------------------------------------------------------------------------------------------------
    def removeStatic(self, static: str | StaticContainer):
        if isinstance(static, StaticContainer):
            static = static.object.agent_id

        # Check if there is such a static in our statics
        if not static in self.statics:
            self.logger.warning(f"Static object with ID {static} does not exist")
            return

        static = self.statics[static]

        # Remove the static from the simulation
        self.simulation.remove_static(static.object)

        # Remove the static from the GUI
        self.map.removeObject(static.map)

        # Remove it from Babylon
        self.babylon_visualization.removeObject(static.babylon)

        # Remove from statics dictionary
        del self.statics[static.object.agent_id]

    # ------------------------------------------------------------------------------------------------------------------
    def removeAllStatics(self):
        # Get a list of static IDs to avoid modifying dictionary during iteration
        static_ids = list(self.statics.keys())

        # Remove each static
        for static_id in static_ids:
            self.removeStatic(static_id)

        self.logger.info("All static objects removed")

    # ------------------------------------------------------------------------------------------------------------------
    def assignJoystick(self, joystick: int, agent: str):
        if agent not in self.agents:
            self.logger.warning(f'Agent with ID {agent} does not exist')
            return

        agent = self.agents[agent].agent

        if not isinstance(agent, FRODO_VisionAgent_Interactive):
            self.logger.warning(f"Cannot assign joystick to agent {agent.agent_id} because it is not interactive")
            return

        joystick_obj = self.joystick_manager.getJoystickById(joystick)

        if joystick_obj is None:
            self.logger.warning(f"Joystick with ID {joystick} does not exist")
            return

        agent.add_joystick(joystick_obj)
        self.logger.info(f"Joystick {joystick_obj.id} assigned to agent {agent.agent_id}")

    # ------------------------------------------------------------------------------------------------------------------
    def set_algorithm_display_state(self, algorithm: str, state: bool):
        if algorithm not in ['centralized', 'distributed']:
            self.logger.warning(f"Algorithm {algorithm} does not exist")
            return

        state = bool(state)
        if algorithm == 'centralized':
            # Make all estimated agents invisible
            for agent_id, agent_container in self.agents.items():
                agent_container.map.algorithm_centralized.group.visible(state)
            self.algorithm_centralized.display_state = state
        elif algorithm == 'distributed':
            for agent_id, agent_container in self.agents.items():
                agent_container.map.algorithm_distributed.group.visible(state)
            self.algorithm_distributed.display_state = state

        self.logger.info(f"Algorithm {algorithm} display state set to {state}")

    # === PRIVATE METHODS ==============================================================================================
    def _buildGUI(self):
        category = Category(id="frodo_standalone_category", name="FRODO Sim", max_pages=2)
        page_3d = Page(id="frodo_standalone_page", name="3D")
        category.addPage(page_3d)

        self.gui.addCategory(category)

        # Add the Babylon Widget
        self.babylon_widget = BabylonWidget(widget_id='babylon_widget')
        page_3d.addWidget(self.babylon_widget, row=1, column=1, height=18, width=36)

        page_2d = Page(id="frodo_standalone_page_2d", name="2D")
        category.addPage(page_2d)

        map_widget = MapWidget(widget_id='vision_map_widget',
                               limits={"x": [-TESTBED_SIZE[0] / 2, TESTBED_SIZE[0] / 2],
                                       "y": [-TESTBED_SIZE[1] / 2, TESTBED_SIZE[1] / 2]},
                               initial_display_center=[0, 0],
                               tiles=True,
                               tile_size=TESTBED_TILE_SIZE,
                               show_grid=False,
                               server_port=8101,
                               )
        page_2d.addWidget(map_widget, width=18, height=18)

        # Add the error plot
        self.error_plot = RT_Plot_Widget(widget_id='error_plot_widget',
                                         title='Position Error',
                                         use_local_time=True,
                                         x_axis_config={
                                             'window_time': 10
                                         })

        page_2d.addWidget(self.error_plot, width=16, height=9)
        y_axis_error = Y_Axis(id="y_axis_1",
                              label='Error [m]',
                              min=0,
                              max=5,
                              grid=True
                              )
        self.error_plot.plot.add_y_axis(y_axis_error)

        self.covariance_plot = RT_Plot_Widget(widget_id='covariance_plot_widget',
                                              title='Covariance',
                                              use_local_time=True,
                                              x_axis_config={
                                                  'window_time': 10
                                              })

        y_axis_covariance = Y_Axis(id="y_axis_2",
                                   label='Covariance Norm',
                                   min=-6,
                                   max=6,
                                   grid=True
                                   )

        self.covariance_plot.plot.add_y_axis(y_axis_covariance)

        page_2d.addWidget(self.covariance_plot, width=16, height=9, row=10)

        scenario_group = Widget_Group(title='Scenarios', show_title=True, rows=1, columns=4)
        page_2d.addWidget(scenario_group, width=8, height=3, row=1)

        button_scenario_1 = Button(text='Scenario 1', callback=self._scenario1)
        scenario_group.addWidget(button_scenario_1, row=1, column=1)

        button_scenario_2 = Button(text='Scenario 2')
        scenario_group.addWidget(button_scenario_2, row=1, column=2)
        button_scenario_3 = Button(text='Scenario 3')
        scenario_group.addWidget(button_scenario_3, row=1, column=3)
        button_scenario_4 = Button(text='Scenario 4')
        scenario_group.addWidget(button_scenario_4, row=1, column=4)

        algorithm_control_group = Widget_Group(title='Algorithm Control', show_title=True, rows=1, columns=4)
        page_2d.addWidget(algorithm_control_group, width=8, height=3, row=4)

        button_start_algorithm = Button(text='Start',
                                        color=NamedColor.LIGHTGREEN,
                                        text_color=NamedColor.BLACK,
                                        callback=self.startAlgorithm)
        algorithm_control_group.addWidget(button_start_algorithm, row=1, column=1)
        button_stop_algorithm = Button(text='Stop',
                                       color=NamedColor.LIGHTRED,
                                       text_color=NamedColor.BLACK,
                                       callback=self.stopAlgorithm)
        algorithm_control_group.addWidget(button_stop_algorithm, row=1, column=2)

        self.map = map_widget.map

    # ------------------------------------------------------------------------------------------------------------------
    def _buildBabylon(self):
        floor = SimpleFloor('floor', size_y=50, size_x=50, texture='carpet.png')
        self.babylon_visualization.addObject(floor)

        wall1 = WallFancy('wall1', length=TESTBED_SIZE[0], texture='wood4.png', include_end_caps=True)
        wall1.setPosition(y=TESTBED_SIZE[1] / 2)
        self.babylon_visualization.addObject(wall1)

        wall2 = WallFancy('wall2', length=TESTBED_SIZE[0], texture='wood4.png', include_end_caps=True)
        self.babylon_visualization.addObject(wall2)
        wall2.setPosition(y=-TESTBED_SIZE[1] / 2)

        wall3 = WallFancy('wall3', length=TESTBED_SIZE[1], texture='wood4.png')
        wall3.setPosition(x=TESTBED_SIZE[0] / 2)
        wall3.setAngle(np.pi / 2)
        self.babylon_visualization.addObject(wall3)

        wall4 = WallFancy('wall4', length=TESTBED_SIZE[1], texture='wood4.png')
        wall4.setPosition(x=-TESTBED_SIZE[0] / 2)
        wall4.setAngle(np.pi / 2)
        self.babylon_visualization.addObject(wall4)

    # ------------------------------------------------------------------------------------------------------------------
    def _predictionStep(self):
        # self.logger.info("Prediction Step")
        if self.algorithm_state == AlgorithmState.RUNNING:

            for agent_id, agent_container in self.agents.items():
                agent_container.centralized_algorithm_agent.input = AlgorithmAgentInput.from_array(np.asarray([
                    agent_container.agent.input.v,
                    agent_container.agent.input.psi_dot
                ]))

                agent_container.distributed_algorithm_agent.input = AlgorithmAgentInput.from_array(np.asarray([
                    agent_container.agent.input.v,
                    agent_container.agent.input.psi_dot
                ]))

            self.algorithm_centralized.prediction()
            self.algorithm_distributed.prediction()

    # ------------------------------------------------------------------------------------------------------------------
    def _measurementStep(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _inputStep(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _dynamicsStep(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _correctionStep(self):
        # self.logger.info("Correction Step")
        if self.algorithm_state == AlgorithmState.RUNNING:
            # Update the measurements of the algorithm agents
            for agent_id, agent_container in self.agents.items():

                # 1. Wipe all measurements from the algorithm agents
                agent_container.centralized_algorithm_agent.measurements.clear()
                agent_container.distributed_algorithm_agent.measurements.clear()

                # 2. Add measurements from the simulated agent
                for measurement in agent_container.agent.measurements:
                    to_id = measurement.object_to.agent_id

                    # For the centralized agent
                    algorithm_measurement_for_centralized = AlgorithmAgentMeasurement(
                        agent_from=agent_container.agent.agent_id,
                        agent_to=to_id,
                        measurement=np.asarray([measurement.position[0], measurement.position[1], measurement.psi]),
                        covariance=measurement.covariance
                    )
                    agent_container.centralized_algorithm_agent.measurements.append(
                        algorithm_measurement_for_centralized)

                    # For the distributed agent
                    algorithm_measurement_for_distributed = AlgorithmAgentMeasurement(
                        agent_from=agent_container.agent.agent_id,
                        agent_to=to_id,
                        measurement=np.asarray([measurement.position[0], measurement.position[1], measurement.psi]),
                        covariance=measurement.covariance
                    )
                    agent_container.distributed_algorithm_agent.measurements.append(
                        algorithm_measurement_for_distributed)

            # Update the algorithms
            self.algorithm_centralized.correction()
            self.algorithm_distributed.correction()

    # ------------------------------------------------------------------------------------------------------------------
    def _simulationOutputStep(self):
        # Update the Agents
        for agent_id, agent_container in self.agents.items():
            agent_container.babylon.setState(x=agent_container.agent.state.x,
                                             y=agent_container.agent.state.y,
                                             psi=agent_container.agent.state.psi)

            agent_container.map.agent.update(x=agent_container.agent.state.x,
                                             y=agent_container.agent.state.y,
                                             psi=agent_container.agent.state.psi, )

            # Look if the agent has measurements
            current_measurements = []
            for measurement in agent_container.agent.measurements:
                measured_object_id = measurement.object_to.agent_id
                measurement_line_id = f"{agent_id}_to_{measured_object_id}"

                if measurement_line_id in agent_container.map.lines.objects:
                    agent_container.map.lines.objects[measurement_line_id].visible(True)
                else:

                    # Get the end object first
                    if measured_object_id in self.agents:
                        end_object = self.agents[measured_object_id].map.agent
                    elif measured_object_id in self.statics:
                        end_object = self.statics[measured_object_id].map
                    else:
                        self.logger.warning(f"Object with ID {measured_object_id} does not exist")
                        continue

                    measurement_line = Line(
                        id=measurement_line_id,
                        start=agent_container.map.agent,
                        end=end_object,
                    )

                    # Add it to the agent container
                    agent_container.map.lines.addObject(measurement_line)

                current_measurements.append(measurement_line_id)

            # make all lines invisible that are currently not there
            for line in agent_container.map.lines.objects.values():
                if line.id not in current_measurements:
                    line.visible(False)

        if self.algorithm_state == AlgorithmState.RUNNING:
            # Update the plotted elements, based on the algorithm
            for agent_id, agent_container in self.agents.items():
                # Update the centralized algorithm map objects
                agent_container.map.algorithm_centralized.agent.visible(True)
                agent_container.map.algorithm_centralized.covariance_ellipse.visible(True)
                agent_container.map.algorithm_centralized.agent.update(
                    x=agent_container.centralized_algorithm_agent.state.x,
                    y=agent_container.centralized_algorithm_agent.state.y,
                    psi=agent_container.centralized_algorithm_agent.state.psi, )

                rx, ry, psi = get_covariance_ellipse(agent_container.centralized_algorithm_agent.covariance[0:2, 0:2])

                agent_container.map.algorithm_centralized.covariance_ellipse.update(
                    x=agent_container.centralized_algorithm_agent.state.x,
                    y=agent_container.centralized_algorithm_agent.state.y,
                    rx=rx,
                    ry=ry,
                    psi=psi
                )

                # Update the distributed algorithm map objects
                agent_container.map.algorithm_distributed.agent.visible(True)
                agent_container.map.algorithm_distributed.agent.update(
                    x=agent_container.distributed_algorithm_agent.state.x,
                    y=agent_container.distributed_algorithm_agent.state.y,
                    psi=agent_container.distributed_algorithm_agent.state.psi,
                )
                rx, ry, psi = get_covariance_ellipse(agent_container.distributed_algorithm_agent.covariance[0:2, 0:2])

                agent_container.map.algorithm_distributed.covariance_ellipse.visible(True)
                agent_container.map.algorithm_distributed.covariance_ellipse.update(
                    x=agent_container.distributed_algorithm_agent.state.x,
                    y=agent_container.distributed_algorithm_agent.state.y,
                    rx=rx,
                    ry=ry,
                    psi=psi
                )

                # Plot the errors
                position_error_distributed = np.linalg.norm(np.asarray([
                    agent_container.agent.state.x - agent_container.distributed_algorithm_agent.state.x,
                    agent_container.agent.state.y - agent_container.distributed_algorithm_agent.state.y,
                ]))

                agent_container.plot.error_distributed.set_value(float(position_error_distributed))

                agent_container.plot.covariance_distributed.set_value(
                    1 * math.log10(agent_container.distributed_algorithm_agent.get_covariance_norm()))

                agent_container.plot.covariance_centralized.set_value(
                    1 * math.log10(agent_container.centralized_algorithm_agent.get_covariance_norm())
                )

            # if (self.algorithm_centralized.step % 40) == 0:
            #     self.logger.info("----------------")
            #     self.logger.info(f"Algorithm Step: {self.algorithm_centralized.step}")
            #     for agent_id, agent_container in self.agents.items():
            #         self.logger.info(
            #             f"Agent {agent_id}: C: {agent_container.centralized_algorithm_agent.covariance[2, 2]:.2f}, D: {agent_container.distributed_algorithm_agent.covariance[2, 2]:.2f}")

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        print_text = f"[{logger.name}] {log}"
        color = LOGGING_COLORS[level]
        color = [c / 255 for c in color]
        self.gui.print(print_text, color=color)

    # ------------------------------------------------------------------------------------------------------------------
    def _reset(self):
        self.logger.info("Resetting Simulation")
        self.algorithm_state = AlgorithmState.STOPPED

        self.removeAllAgents()
        self.removeAllStatics()

    # ------------------------------------------------------------------------------------------------------------------
    def _scenario1(self):
        self._reset()
        self.addAgent('agent1', 110, 1.5, [0, 0.5], math.pi / 2, interactive=True)
        time.sleep(0.05)
        self.addAgent('agent2', 110, 1.5, [1.5, -0.25], -3 * math.pi / 4)
        time.sleep(0.05)
        self.addAgent('agent3', 110, 1.5, [1.0, 0.5], math.pi / 2)
        time.sleep(0.05)
        self.addStatic('static1', [0.5, -1], 0)

    def run_singleagent_demo(self):
        self.logger.info("Single-agent demo plan for scenario1...")
        adapters = [FRODO_Sim_NavigatedObject(cont.agent) for _, cont in self.agents.items()]
        self.navigator.initialize(adapters)
        # self.navigator.start()  # tick the MAN in the background

        plan = NavigatorPlan(
            id="demo_plan_scenario1",
            actions=[
                Move(id="m_a1_wp1", agent_id="agent1", element=CoordinatedMoveTo(x=-0.50, y=-0.50), blocking=True),
                Wait(id="sleep2", seconds=2),
                Move(id="m_a1_wp2", conditions=['signal/test'], agent_id="agent1", element=MoveTo(x=0, y=0),
                     blocking=True),
            ],
        )
        self.navigator.load_plan(plan, start=True)

        setTimeout(lambda: self.navigator.bus.publish("signal/test", "test"), 15)

    def multi_agent_demo(self):
        self.logger.info("Multi-agent demo plan for scenario1...")
        adapters = [FRODO_Sim_NavigatedObject(cont.agent) for _, cont in self.agents.items()]
        self.navigator.initialize(adapters)

        plan = NavigatorPlan(
            id="ma_plan_scenario1",
            actions=[
                ActionGroup(
                    'group1',
                    actions=[
                        Move(id="m_a1_wp1", agent_id="agent1", element=CoordinatedMoveTo(x=-2, y=-2),
                             blocking=True),
                        Wait(id="sleep2", seconds=2, finished_emit_signal="sigA"),
                        Move(id="m_a1_wp2", conditions=[], agent_id="agent1", element=MoveTo(x=0, y=0),
                             blocking=True),
                    ],
                    blocking=False,
                    finished_emit_signal='group1_finished'
                ),
                ActionGroup(
                    'group2',
                    actions=[
                        Wait(id="wait_sigA", conditions=["signal/sigA"]),
                        Move(id="m_a2_wp1", agent_id="agent3", element=CoordinatedMoveTo(x=1.5, y=-0.50),
                             blocking=True),
                    ],
                )
            ]
        )

        self.navigator.load_plan(plan, start=True)

    def multi_agent_demo_2(self):
        self.logger.info("Multi-agent demo plan for scenario1...")
        adapters = [FRODO_Sim_NavigatedObject(cont.agent) for _, cont in self.agents.items()]
        self.navigator.initialize(adapters)

        plan = NavigatorPlan(
            id="ma_plan_scenario1",
            actions=[
                ActionGroup(
                    'group1',
                    actions=[
                        Move(id="m_a1_wp1",
                             agent_id="agent1",
                             abort_signal='signal/abort_move_1',
                             element=CoordinatedMoveTo(x=-2, y=-2),
                             blocking=True),
                        Move(id="m_a1_wp2", conditions=[], agent_id="agent1", element=MoveTo(x=0, y=0),
                             blocking=True),
                    ],
                    blocking=False,
                    finished_emit_signal='group1_finished'
                ),
                ActionGroup(
                    'group2',
                    actions=[
                        Wait(id="wait_sigA", seconds=3, finished_emit_signal='abort_move_1'),
                        Move(id="m_a2_wp1", agent_id="agent3", element=CoordinatedMoveTo(x=1.5, y=-0.50),
                             blocking=True),
                    ],
                )
            ]
        )

        self.navigator.load_plan(plan, start=True)

    def multi_agent_demo_yaml(self):

        file = get_absolute_path('./multi_agent_scenario_1.yml')
        adapters = [FRODO_Sim_NavigatedObject(cont.agent) for _, cont in self.agents.items()]
        self.navigator.initialize(adapters)
        plan = NavigatorPlan.from_yaml(file)
        self.navigator.load_plan(plan, start=True)

    # ------------------------------------------------------------------------------------------------------------------
    def _is_agent_deadreckoning(self, agent_id):
        # Check if this agent is involved in any measurements
        if len(self.agents[agent_id].agent.measurements) > 0:
            return False

        for other_agent in self.agents.values():
            for measurement in other_agent.agent.measurements:
                if measurement.object_to.agent_id == agent_id:
                    return False

        return True


# ======================================================================================================================
class FRODO_Simulation_CLI(CommandSet):
    name = 'simulation'

    def __init__(self, app: FRODO_App_Standalone):
        super().__init__(self.name)
        self.app = app

        command_add_agent = Command(name='add_agent',
                                    function=self._add_agent,
                                    description='Add a new agent to the simulation',
                                    arguments=[
                                        CommandArgument(name='agent_id', type=str,
                                                        short_name='a',
                                                        description='ID of the agent to add'),
                                        CommandArgument(name='fov', type=float,
                                                        short_name='f',
                                                        description='Field of view of the agent', optional=True,
                                                        default=110),
                                        CommandArgument(name='vision_radius', type=float,
                                                        short_name='r',
                                                        description='Vision radius of the agent', optional=True,
                                                        default=1.5),
                                        CommandArgument(name='position', type=list[float],
                                                        array_size=2,
                                                        short_name='pos',
                                                        description='Position of the agent', optional=True,
                                                        default=[0, 0]),
                                        CommandArgument(name='psi', type=float,
                                                        short_name='psi',
                                                        description='Orientation of the agent',
                                                        optional=True,
                                                        default=0),
                                        CommandArgument(name='interactive', type=bool,
                                                        is_flag=True,
                                                        optional=True,
                                                        default=False,
                                                        short_name='i', )
                                    ]
                                    )

        command_remove_agent = Command(name='remove_agent',
                                       description='Remove an agent from the simulation',
                                       arguments=[
                                           CommandArgument(name='agent_id', type=str,
                                                           short_name='a',
                                                           description='ID of the agent to remove'),
                                       ])

        command_assign_joystick = Command(name='assign_joystick',
                                          function=self.app.assignJoystick,
                                          allow_positionals=True,
                                          description='Assign a joystick to an agent',
                                          arguments=[
                                              CommandArgument(name='joystick', type=int,
                                                              short_name='j',
                                                              description='ID of the joystick to assign'),
                                              CommandArgument(name='agent', type=str,
                                                              short_name='a',
                                                              description='ID of the agent to assign the joystick to')
                                          ]
                                          )

        command_remove_joystick = Command(name='remove_joystick',
                                          description='Remove a joystick from an agent',
                                          arguments=[
                                              CommandArgument(name='agent', type=str,
                                                              short_name='a',
                                                              description='ID of the agent to remove the joystick from')
                                          ]
                                          )

        command_list_joystick_assignments = Command(name='list_joystick_assignments',
                                                    description='List all joystick assignments')

        command_add_static = Command(name='add_static',
                                     allow_positionals=True,
                                     function=self.app.addStatic,
                                     description='Add a new static object to the simulation',
                                     arguments=[
                                         CommandArgument(name='object_id', type=str,
                                                         short_name='o',
                                                         description='ID of the object to add'),
                                         CommandArgument(name='position', type=list[float],
                                                         array_size=2,
                                                         short_name='pos',
                                                         description='Position of the object', optional=True,
                                                         default=[0, 0]),
                                         CommandArgument(name='psi', type=float,
                                                         short_name='psi',
                                                         description='Orientation of the object',
                                                         optional=True,
                                                         default=0),
                                     ]
                                     )

        command_remove_static = Command(name='remove_static',
                                        description='Remove a static object from the simulation',
                                        arguments=[
                                            CommandArgument(name='object_id', type=str,
                                                            short_name='o',
                                                            description='ID of the object to remove'),
                                        ])

        command_start_algorithm = Command(name='start',
                                          function=self.app.startAlgorithm,
                                          description='Start the algorithm')

        command_stop_algorithm = Command(name='stop',
                                         function=self.app.stopAlgorithm,
                                         description='Stop the algorithm')

        command_reset_algorithm = Command(name='reset',
                                          description='Reset the algorithm')

        command_scenario1 = Command(name='scenario1',
                                    function=self.app._scenario1,
                                    description='Scenario 1: Two agents in a square')

        command_display_state = Command(name='display',
                                        function=self._set_algorithm_display_state,
                                        description='Display the algorithm state',
                                        arguments=[
                                            CommandArgument(name='algorithm', type=str,
                                                            short_name='a',
                                                            description='Name of the algorithm to display',
                                                            optional=True,
                                                            default=None),
                                            CommandArgument(name='state', type=int,
                                                            short_name='s',
                                                            description='State of the algorithm to display',
                                                            optional=True,
                                                            default=None
                                                            )
                                        ])

        navigator_test_command = Command(name='nav',
                                         function=self.app.run_singleagent_demo,
                                         arguments=[])

        navigator_ma_test_command = Command(name='nav_ma',
                                            function=self.app.multi_agent_demo_yaml,
                                            arguments=[])

        self.addCommand(command_display_state)
        self.addCommand(command_add_agent)
        self.addCommand(command_remove_agent)
        self.addCommand(command_assign_joystick)
        self.addCommand(command_remove_joystick)
        self.addCommand(command_list_joystick_assignments)
        self.addCommand(command_add_static)
        self.addCommand(command_remove_static)
        self.addCommand(command_start_algorithm)
        self.addCommand(command_stop_algorithm)
        self.addCommand(command_reset_algorithm)
        self.addCommand(command_scenario1)
        self.addCommand(navigator_test_command)
        self.addCommand(navigator_ma_test_command)

    def _add_agent(self, agent_id, fov, vision_radius, position, psi, interactive=False):
        self.app.addAgent(agent_id, fov, vision_radius, position, psi, interactive)

    def _set_algorithm_display_state(self, algorithm: str | None = None, state: bool | int | None = None):
        if algorithm is None:
            # Display the current display states
            self.app.logger.info(
                f"Algorith Display: Centralized: {self.app.algorithm_display_states.centralized}. Distributed: {self.app.algorithm_display_states.distributed}")
            return

        if algorithm == 'centralized':
            if state is None:
                self.app.set_algorithm_display_state('centralized', not self.app.algorithm_display_states.centralized)
            else:
                print(bool(state))
                self.app.set_algorithm_display_state('centralized', bool(state))
        elif algorithm == 'distributed':
            if state is None:
                self.app.set_algorithm_display_state('distributed', not self.app.algorithm_display_states.distributed)
            else:
                self.app.set_algorithm_display_state('distributed', bool(state))
        else:
            self.app.logger.warning(f"Algorithm {algorithm} not found")


if __name__ == '__main__':
    app = FRODO_App_Standalone()
    app.init()
    app.start()

    while True:
        time.sleep(10)
