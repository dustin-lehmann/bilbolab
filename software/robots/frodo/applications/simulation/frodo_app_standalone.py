import dataclasses
import enum
import math
import time
import re

import numpy as np
import qmt

from applications.FRODO.algorithm.archive.algorithm_centralized_2 import CentralizedLocationAlgorithm, FRODO_AlgorithmAgent, \
    AlgorithmAgentState, AlgorithmAgentMeasurement, AlgorithmAgentInput, AlgorithmState
from applications.FRODO.simulation.frodo_simulation import FRODO_Simulation, FRODO_VisionAgent, \
    FRODO_VisionAgent_Interactive, FRODO_Static, FRODO_ENVIRONMENT_ACTIONS
from core.utils.colors import random_color_from_palette, get_color_from_palette
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger, LOGGING_COLORS, addLogRedirection
from core.utils.network.network import getHostIP
from core.utils.sound.sound import SoundSystem
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
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.hardware.joystick.joystick_manager import Joystick, JoystickManager
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

TS = 0.05

TESTBED_SIZE = [5, 5]
TESTBED_TILE_SIZE = 0.5

INITIAL_GUESS_AGENTS = np.asarray([0.01, 0.012, 0.002])
INITIAL_GUESS_AGENTS_COVARIANCE = 1e5 * np.diag([1, 1, 1])

STATIC_AGENTS_COVARIANCE = 0 * np.diag([1, 1, 1])


# === HELPERS ==========================================================================================================
def extract_number(s: str):
    # Search for a sequence of digits in the string
    match = re.search(r'\d+', s)
    if match:
        return int(match.group())  # Return the number as an integer
    return s  # If no number found, return the full string


@dataclasses.dataclass
class AgentMapContainer:
    group: MapObjectGroup
    agent: VisionAgent
    agent_estimated: Agent
    covariance_circle: Circle
    covariance_ellipse: Ellipse
    measurements: MapObjectGroup
    lines: MapObjectGroup


@dataclasses.dataclass
class AgentContainer:
    agent: FRODO_VisionAgent
    babylon: BabylonFrodo
    map: AgentMapContainer
    algorithm: FRODO_AlgorithmAgent


@dataclasses.dataclass
class StaticContainer:
    object: FRODO_Static
    babylon: BabylonStatic
    map: CoordinateSystem
    algorithm: FRODO_AlgorithmAgent



class FRODO_App_Standalone:
    simulation: FRODO_Simulation
    gui: GUI
    cli: CLI
    algorithm: CentralizedLocationAlgorithm

    agents: dict[str, AgentContainer]
    statics: dict[str, StaticContainer]

    joystick_manager: JoystickManager

    algorithm_state = AlgorithmState.STOPPED

    # === INIT =========================================================================================================
    def __init__(self):
        host = getHostIP()
        if host is None:
            host = 'localhost'

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
        #
        self.simulation.environment.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(
            self._inputStep)

        self.gui = GUI('frodo_simulation_standalone_gui', host=host, run_js=True)
        self.cli = CLI(id='frodo_simulation_standalone_cli', root=FRODO_Simulation_CLI(self))
        self.algorithm = CentralizedLocationAlgorithm(Ts=TS)
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
    # def initializeAlgorithm(self):
    #     ...
    #     algorithm_agents = []

    # ------------------------------------------------------------------------------------------------------------------
    def startAlgorithm(self):

        if self.algorithm_state == AlgorithmState.RUNNING:
            self.logger.warning("Algorithm is already running")
            return

        algorithm_agents = []

        for agent_id, agent_container in self.agents.items():
            agent_container.algorithm.state = AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS)
            agent_container.algorithm.state_covariance = INITIAL_GUESS_AGENTS_COVARIANCE
            algorithm_agents.append(agent_container.algorithm)

        for static_id, static_container in self.statics.items():
            algorithm_agents.append(static_container.algorithm)

        self.algorithm.init(algorithm_agents)
        self.algorithm_state = AlgorithmState.RUNNING
        self.logger.info("Start FRODO Algorithm")
        self.soundsystem.speak('Start FRODO Algorithm')

    # ------------------------------------------------------------------------------------------------------------------
    def stopAlgorithm(self):
        self.algorithm.reset()
        self.algorithm_state = AlgorithmState.STOPPED
        self.logger.info("Stop FRODO Algorithm")
        self.soundsystem.speak('Stop FRODO Algorithm')

        # Make all estimated agents invisible
        for agent_id, agent_container in self.agents.items():
            agent_container.map.agent_estimated.visible(False)
            agent_container.map.covariance_circle.visible(False)

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

        # Map Objects
        map_container = AgentMapContainer(
            group=MapObjectGroup(id=f"map_group_{agent_id}"),
            agent=VisionAgent(agent_id, name=babylon_text, color=agent_color, fov=math.radians(fov),
                              vision_radius=vision_radius, ),
            agent_estimated=Agent(id=f"estimated_point_{agent_id}", name=f"{agent_id}_hat", x=position[0],
                                  y=position[1], psi=0, visible=False),
            measurements=MapObjectGroup(id=f"measurements_group_{agent_id}"),
            lines=MapObjectGroup(id=f"lines_group_{agent_id}"),

            covariance_circle=Circle(id=f"covariance_circle_{agent_id}",
                                     x=position[0],
                                     y=position[1],
                                     radius=0.1,
                                     color=agent_color,
                                     opacity=0.5,
                                     visible=False),
            covariance_ellipse=Ellipse(id=f"covariance_ellipse_{agent_id}",
                                       x=position[0],
                                       y=position[1],
                                       rx=1,
                                       ry=0.5,
                                       color=agent_color,
                                       opacity=0.5,
                                       visible=False
                                       )
        )

        map_container.group.addObject(map_container.agent)
        map_container.group.addObject(map_container.agent_estimated)
        map_container.group.addGroup(map_container.measurements)
        map_container.group.addGroup(map_container.lines)
        map_container.group.addObject(map_container.covariance_circle)
        map_container.group.addObject(map_container.covariance_ellipse)

        self.map.addGroup(map_container.group)

        # Algorithm
        algorithm_agent = FRODO_AlgorithmAgent(id=agent_id,
                                               state=AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS),
                                               state_covariance=INITIAL_GUESS_AGENTS_COVARIANCE,
                                               is_anchor=False)

        self.agents[agent_id] = AgentContainer(agent, frodo_babylon, map_container, algorithm_agent)

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

        algorithm_agent = FRODO_AlgorithmAgent(id=object_id,
                                               state=algorithm_state,
                                               state_covariance=STATIC_AGENTS_COVARIANCE,
                                               is_anchor=True)

        # Map
        map_object = CoordinateSystem(id=f"{object_id}", x=position[0], y=position[1], psi=psi, show_name=True)
        self.map.addObject(map_object)

        # Babylon
        babylon_object = BabylonStatic(f"static_{object_id}", x=position[0], y=position[1], psi=psi)
        self.babylon_visualization.addObject(babylon_object)

        static_container = StaticContainer(static_obj, babylon_object, map_object, algorithm_agent)
        self.statics[object_id] = static_container

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
                               # major_grid_size=0.5,
                               # minor_grid_size=0.1,
                               )
        page_2d.addWidget(map_widget, width=18, height=18)

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

        if self.algorithm_state == AlgorithmState.RUNNING:
            # self.logger.info("Prediction Step")
            for agent_id, agent_container in self.agents.items():
                # 3. Set the inputs
                agent_container.algorithm.input = AlgorithmAgentInput.from_array(np.asarray([
                    agent_container.agent.input.v,
                    agent_container.agent.input.psi_dot
                ]))

            self.algorithm.prediction()
    # ------------------------------------------------------------------------------------------------------------------
    def _measurementStep(self):
        ...
        # self.logger.info("Measurement Step")

    # ------------------------------------------------------------------------------------------------------------------
    def _dynamicsStep(self):
        ...
        # self.logger.info("Dynamics Step")

    # ------------------------------------------------------------------------------------------------------------------
    def _correctionStep(self):
        if self.algorithm_state == AlgorithmState.RUNNING:

            for agent_id, agent_container in self.agents.items():

                # 1. Wipe all measurements from the algorithm agent
                agent_container.algorithm.measurements.clear()

                # 2. Add measurements from the simulated agent
                for measurement in agent_container.agent.measurements:
                    to_id = measurement.object_to.agent_id
                    algorithm_measurement = AlgorithmAgentMeasurement(
                        source=self.algorithm.agents[agent_id],
                        source_index=self.algorithm.agents[agent_id].index,
                        target=self.algorithm.agents[to_id],
                        target_index=self.algorithm.agents[to_id].index,
                        measurement=np.asarray([measurement.position[0], measurement.position[1], measurement.psi]),
                        measurement_covariance=measurement.covariance
                    )
                    agent_container.algorithm.measurements.append(algorithm_measurement)

                # Update the algorithm
            self.algorithm.update()

    # ------------------------------------------------------------------------------------------------------------------
    def _inputStep(self):
        ...
        # self.logger.info("Input Step")
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
                estimated_agent_point = agent_container.map.agent_estimated
                covariance_circle = agent_container.map.covariance_circle
                covariance_ellipse = agent_container.map.covariance_ellipse
                estimated_agent_point.visible(True)
                estimated_agent_point.update(x=agent_container.algorithm.state.x,
                                             y=agent_container.algorithm.state.y,
                                             psi=agent_container.algorithm.state.psi)

                # --- draw covariance ellipse (position-only) ---
                P_xy = agent_container.algorithm.state_covariance[0:2, 0:2]

                # Numerical hygiene: symmetrize and clip tiny negatives
                P_xy = 0.5 * (P_xy + P_xy.T)
                eigvals, eigvecs = np.linalg.eigh(P_xy)  # eigh for symmetric
                order = np.argsort(eigvals)[::-1]  # sort: λ_max first
                eigvals = eigvals[order]
                eigvecs = eigvecs[:, order]
                eigvals = np.maximum(eigvals, 0.0)

                # Choose confidence: 95% for 2 DoF → chi2 = 5.991
                # (68%: 2.279, 95%: 5.991, 99%: 9.210)
                # chi2 = 5.991
                chi2 = 1

                # Semi-axes (meters). NOTE: rx, ry are *radii* of the ellipse, not diameters.
                rx = float(np.sqrt(chi2 * eigvals[0]))  # major
                ry = float(np.sqrt(chi2 * eigvals[1]))  # minor

                # Orientation of major axis in global frame
                psi_ellipse = float(np.arctan2(eigvecs[1, 0], eigvecs[0, 0]))

                covariance_ellipse.visible(True)
                covariance_ellipse.update(
                    x=agent_container.algorithm.state.x,
                    y=agent_container.algorithm.state.y,
                    rx=rx,
                    ry=ry,
                    psi=psi_ellipse
                )



        else:
            ...

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        print_text = f"[{logger.name}] {log}"
        color = LOGGING_COLORS[level]
        color = [c / 255 for c in color]
        self.gui.print(print_text, color=color)

    # ------------------------------------------------------------------------------------------------------------------
    def _scenario1(self):
        self.addAgent('agent1', 110, 1.5, [0.5, -0.5], math.pi / 2, interactive=True)
        time.sleep(0.05)
        self.addAgent('agent2', 110, 1.5, [1.5, -0.25], -3 * math.pi / 4)
        time.sleep(0.05)
        self.addAgent('agent3', 110, 1.5, [1.0, 0.5], math.pi / 2)
        time.sleep(0.05)
        self.addStatic('static1', [0.5, -1], 0)

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

    def _add_agent(self, agent_id, fov, vision_radius, position, psi, interactive=False):
        self.app.addAgent(agent_id, fov, vision_radius, position, psi, interactive)


if __name__ == '__main__':
    app = FRODO_App_Standalone()
    app.init()
    app.start()

    while True:
        time.sleep(10)
