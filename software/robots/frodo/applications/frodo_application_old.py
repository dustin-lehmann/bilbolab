import dataclasses
import enum
import threading
import time

import numpy as np

from applications.FRODO.agent_manager import FRODO_AgentManager
from applications.FRODO.algorithm.algorithm import AlgorithmAgentState, AlgorithmAgentMeasurement, AlgorithmAgentInput
from applications.FRODO.algorithm.algorithm_centralized import CentralizedAgent, CentralizedAlgorithm
from applications.FRODO.algorithm.algorithm_distributed import DistributedAlgorithm, DistributedAgent
from applications.FRODO.definitions import PLANS_DIR
from applications.FRODO.navigation.multi_agent_navigator import NavigatorPlan, Move
from applications.FRODO.navigation.navigator import MoveTo
from applications.FRODO.testbed.testbed_manager import FRODO_TestbedManager, TestbedObject_FRODO, TestbedObject_STATIC
from applications.FRODO.gui.frodo_gui import FRODO_GUI
from applications.FRODO.simulation.frodo_simulation import FRODO_Simulation, FRODO_VisionAgent, FRODO_Static, \
    SIMULATED_AGENTS, SIMULATED_STATICS
from applications.FRODO.testbed.tracker.frodo_tracker import FRODO_Tracker
from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.files import file_exists
from core.utils.logging_utils import Logger
from core.utils.network.network import getHostIP
from core.utils.sound.sound import SoundSystem, speak
from core.utils.time import IntervalTimer
from extensions.tools.cli.cli import CLI, CommandSet, Command, CommandArgument
from extensions.hardware.joystick.joystick_manager import JoystickManager
from robots.frodo.frodo import FRODO
from robots.frodo.frodo_manager import FRODO_Manager

# ----------------------------------------------------------------------------------------------------------------------
# TODO:
# - allow adding agents during runtime
# - make agent configs
#
#


# ----------------------------------------------------------------------------------------------------------------------

SIMULATION_UPDATE_TIME = 0.01
UPDATE_TIME = 0.05

INITIAL_GUESS_AGENTS = np.asarray([0.01, 0.012, 0.002])
INITIAL_GUESS_AGENTS_COVARIANCE = 1e5 * np.diag([1, 1, 1])
STATIC_AGENTS_COVARIANCE = 1e-8 * np.diag([1, 1, 1])

@event_definition
class FRODO_Application_Events:
    algorithm_started: Event
    algorithm_stopped: Event
    update: Event


@callback_definition
class FRODO_Application_Callbacks:
    algorithm_started: CallbackContainer
    algorithm_stopped: CallbackContainer
    update: CallbackContainer


# ======================================================================================================================
class FRODO_Application:
    testbed_manager: FRODO_TestbedManager

    gui: FRODO_GUI
    soundsystem: SoundSystem

    agent_manager: FRODO_AgentManager

    simulation: FRODO_Simulation

    _initialized: bool = False


    # === INIT =========================================================================================================
    def __init__(self):
        host = getHostIP()

        # Logger
        self.logger = Logger('FRODO Application', 'DEBUG')

        # Events
        self.events = FRODO_Application_Events()
        self.callbacks = FRODO_Application_Callbacks()

        # Manager

        # Joystick Manager
        self.joystick_manager = JoystickManager()

        # Sound
        self.soundsystem = SoundSystem(primary_engine='etts', volume=1)
        self.soundsystem.start()

        # Simulation
        self.simulation = FRODO_Simulation(Ts=UPDATE_TIME)

        # Testbed Manager
        self.testbed_manager = FRODO_TestbedManager()

        # Agent Manager
        self.agent_manager = FRODO_AgentManager(testbed_manager=self.testbed_manager,
                                                simulation=self.simulation)

        # CLI
        self.command_set = FRODO_Application_CLI(self)
        self.cli = CLI(id='frodo_app_cli', root=self.command_set)

        # GUI
        self.gui = FRODO_GUI(host,
                             application=self,
                             testbed_manager=self.testbed_manager,
                             cli=self.cli,
                             )

        # Timer
        self.timer = IntervalTimer(interval=UPDATE_TIME, raise_race_condition_error=False)

        # Thread
        self._exit = False
        self._thread = None

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self.simulation.init()
        self.gui.init()
        self.joystick_manager.init()
        self.testbed_manager.init()
        self.cli.root.addChild(self.testbed_manager.robot_manager.cli)
        self.cli.root.addChild(self.simulation.cli)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.gui.start()
        self.testbed_manager.start()
        self.joystick_manager.start()
        self.simulation.start()
        self.agent_manager.start()
        speak("Start Frodo Application")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        speak("Closing Frodo Application")
        time.sleep(1)
        self._exit = True

    # ------------------------------------------------------------------------------------------------------------------
    def task(self):
        while not self._exit:
            self.update()
            self.timer.sleep_until_next()

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        """
        This is the main update loop for acquiring data, processing the data, updating the algorithm and logging
        """

        # 1. Update the testbed manager
        self.testbed_manager.update()

        # 2. Update the agent manager
        self.agent_manager.update()

        # # 2. Update the Algorithms
        # if self.algorithm_state == AlgorithmState.RUNNING:
        #     # 2.1 Prediction Centralized
        #     self._prediction_centralized()
        #
        #     # 2.2 Prediction Distributed
        #     self._prediction_distributed()
        #
        #     # # 2.3 Update Centralized
        #     # self._update_centralized()
        #     #
        #     # # 2.4 Update Distributed
        #     # self._update_distributed()
        #
        #     # 4. Calculate the estimation error
        #     self._calculate_estimation_errors()

        # Emit the events
        self.events.update.set()
        self.callbacks.update.call()

    # ------------------------------------------------------------------------------------------------------------------
    def init_application(self):

        if self._thread is not None:
            self.logger.warning("Application is already running")
            return

        # 1. Initialize the testbed manager
        self.testbed_manager.initialize()

        # 2. Initialize the agent manager based on the testbed manager and the simulation
        self.agent_manager.initialize()

        self._exit = False
        self._initialized = True
        self.logger.important("Application initialized")
        self._thread = threading.Thread(target=self.task, daemon=True)
        self._thread.start()

        #
        #     self.agents = {}
        #     self.statics = {}
        #
        #     # Clear the aggregator
        #     self.testbed_manager.clear()
        #
        #     self.testbed_manager.initialize()
        #
        #     # Collect the real agents
        #     for robot in self.robot_manager.robots.values():
        #         testbed_object = self.testbed_manager.addRobot(robot)
        #
        #         centralized_algorithm_agent = CentralizedAgent(id=robot.id,
        #                                                        Ts=UPDATE_TIME,
        #                                                        state=AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS),
        #                                                        covariance=INITIAL_GUESS_AGENTS_COVARIANCE,
        #                                                        is_anchor=False)
        #
        #         distributed_algorithm_agent = DistributedAgent(id=robot.id,
        #                                                        Ts=UPDATE_TIME,
        #                                                        state=AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS),
        #                                                        covariance=INITIAL_GUESS_AGENTS_COVARIANCE,
        #                                                        is_anchor=False)
        #
        #         agent = RealAgentContainer(
        #             robot=robot,
        #             testbed_object=testbed_object,
        #             centralized_algorithm_agent=centralized_algorithm_agent,
        #             distributed_algorithm_agent=distributed_algorithm_agent,
        #         )
        #
        #         self.agents[robot.id] = agent
        #         if robot.id in self.agents:
        #             self.logger.warning(f"Agent {robot.id} is already in the application. Cannot be added.")
        #             continue
        #         self.logger.important(f"Added agent {robot.id} to the application")
        #
        #     # Collect the simulated agents
        #     for agent in SIMULATED_AGENTS.values():
        #         centralized_algorithm_agent = CentralizedAgent(id=agent.agent_id,
        #                                                        Ts=UPDATE_TIME,
        #                                                        state=AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS),
        #                                                        covariance=INITIAL_GUESS_AGENTS_COVARIANCE,
        #                                                        is_anchor=False)
        #
        #         distributed_algorithm_agent = DistributedAgent(id=agent.agent_id,
        #                                                        Ts=UPDATE_TIME,
        #                                                        state=AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS),
        #                                                        covariance=INITIAL_GUESS_AGENTS_COVARIANCE,
        #                                                        is_anchor=False)
        #
        #         simulated_agent_container = SimulatedAgentContainer(
        #             agent=agent,
        #             centralized_algorithm_agent=centralized_algorithm_agent,
        #             distributed_algorithm_agent=distributed_algorithm_agent,
        #         )
        #         if agent.agent_id in self.agents:
        #             self.logger.warning(f"Agent {agent.agent_id} is already in the application. Cannot be added.")
        #             continue
        #         self.agents[agent.agent_id] = simulated_agent_container
        #         self.logger.important(f"Added simulated agent {agent.agent_id} to the application")
        #
        #     # Collect the real statics. We get them from the tracker
        #     for static in self.tracker.statics.values():
        #         testbed_object = self.testbed_manager.addStatic(static)
        #
        #         centralized_algorithm_agent = CentralizedAgent(id=static.id,
        #                                                        Ts=UPDATE_TIME,
        #                                                        state=AlgorithmAgentState.from_array(static.state.asarray()),
        #                                                        covariance=STATIC_AGENTS_COVARIANCE,
        #                                                        is_anchor=True)
        #
        #         distributed_algorithm_agent = DistributedAgent(id=static.id,
        #                                                        Ts=UPDATE_TIME,
        #                                                        state=AlgorithmAgentState.from_array(static.state.asarray()),
        #                                                        covariance=STATIC_AGENTS_COVARIANCE,
        #                                                        is_anchor=True
        #                                                        )
        #
        #         static_container = RealStaticContainer(
        #             testbed_object=testbed_object,
        #             centralized_algorithm_agent=centralized_algorithm_agent,
        #             distributed_algorithm_agent=distributed_algorithm_agent,
        #         )
        #
        #     # Collect the simulated statics
        #     for static in SIMULATED_STATICS.values():
        #         centralized_algorithm_agent = CentralizedAgent(id=static.agent_id,
        #                                                        Ts=UPDATE_TIME,
        #                                                        state=AlgorithmAgentState.from_array(
        #                                                            static.state.asarray()
        #                                                        ),
        #                                                        covariance=STATIC_AGENTS_COVARIANCE,
        #                                                        is_anchor=True)
        #
        #         distributed_algorithm_agent = DistributedAgent(id=static.agent_id,
        #                                                        Ts=UPDATE_TIME,
        #                                                        state=AlgorithmAgentState.from_array(
        #                                                            static.state.asarray()
        #                                                        ),
        #                                                        covariance=STATIC_AGENTS_COVARIANCE,
        #                                                        is_anchor=True
        #                                                        )
        #
        #         static_container = SimulatedStaticContainer(
        #             static=static,
        #             centralized_algorithm_agent=centralized_algorithm_agent,
        #             distributed_algorithm_agent=distributed_algorithm_agent,
        #         )
        #
        #         self.statics[static.agent_id] = static_container
        #         if static.agent_id in self.statics:
        #             self.logger.warning(f"Static {static.agent_id} is already in the application. Cannot be added.")
        #             continue
        #         self.logger.important(f"Added simulated static {static.agent_id} to the application")
        #
        #     self.testbed_manager.initialize()
        #

    # ------------------------------------------------------------------------------------------------------------------
    def stop_application(self):
        self._exit = True

        if self._thread is not None and self._thread.is_alive():
            self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    # def start_algorithm(self):
    #     if self.algorithm_state == AlgorithmState.RUNNING:
    #         self.logger.warning("Algorithm is already running")
    #         return
    #
    #     if self._thread is None:
    #         self.logger.warning("Application is not initialized. Please initialize the application first")
    #         return
    #
    #     centralized_algorithm_agents = []
    #     distributed_algorithm_agents = []
    #
    #     for agent_id, agent_container in self.agents.items():
    #         agent_container.centralized_algorithm_agent.state = AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS)
    #         agent_container.centralized_algorithm_agent.state_covariance = INITIAL_GUESS_AGENTS_COVARIANCE
    #         centralized_algorithm_agents.append(agent_container.centralized_algorithm_agent)
    #
    #         agent_container.distributed_algorithm_agent.state = AlgorithmAgentState.from_array(INITIAL_GUESS_AGENTS)
    #         agent_container.distributed_algorithm_agent.state_covariance = INITIAL_GUESS_AGENTS_COVARIANCE
    #         distributed_algorithm_agents.append(agent_container.distributed_algorithm_agent)
    #
    #     for static_id, static_container in self.statics.items():
    #         centralized_algorithm_agents.append(static_container.centralized_algorithm_agent)
    #         distributed_algorithm_agents.append(static_container.distributed_algorithm_agent)
    #
    #     self.algorithm_centralized.initialize(centralized_algorithm_agents)
    #     self.algorithm_distributed.initialize(distributed_algorithm_agents)
    #
    #     self.algorithm_state = AlgorithmState.RUNNING
    #     self.logger.important("Start FRODO Algorithm")
    #     self.soundsystem.speak('Start FRODO Algorithm')
    #     self.events.algorithm_started.set()

    # ------------------------------------------------------------------------------------------------------------------

    def stop_algorithm(self):
        self.algorithm_state = AlgorithmState.STOPPED
        self.logger.info("Stop FRODO Algorithm")
        self.soundsystem.speak('Stop FRODO Algorithm')
        self.events.algorithm_stopped.set()

    # ------------------------------------------------------------------------------------------------------------------
    def reset_algorithm(self):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def add_simulated_agent(self, agent_id, *args, **kwargs):
        if self._initialized:
            self.logger.warning(f"Application is already initialized. Cannot add agent {agent_id}")
            return
        simulated_agent = self.simulation.add_agent(agent_id=agent_id, **kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def add_simulated_static(self, static_id, *args, **kwargs):
        if self._initialized:
            self.logger.warning(f"Application is already initialized. Cannot add static {static_id}")
            return
        static_object = self.simulation.add_static(static_id=static_id, **kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def remove_simulated_agent(self, agent_id):
        if self._initialized:
            self.logger.warning(f"Application is already initialized. Cannot remove simulated agent {agent_id}")
            return
        self.simulation.remove_agent(agent_id)

    # ------------------------------------------------------------------------------------------------------------------
    def remove_simulated_static(self, static_id):
        if self._initialized:
            self.logger.warning(f"Application is already initialized. Cannot remove simulated static {static_id}")
            return
        self.simulation.remove_static(static_id)

    # ------------------------------------------------------------------------------------------------------------------
    def clear_simulation(self):
        self.simulation.clear()

    # ------------------------------------------------------------------------------------------------------------------
    def test(self):
        self.logger.info("Running Test")

        plan = NavigatorPlan(
            id='test',
            actions=[
                Move(
                    id='move1',
                    agent_id='frodo1',
                    element=MoveTo(
                        x=2.75,
                        y=2.75,
                    ),
                    blocking=False
                ),
                # Move(
                #     id='move2',
                #     agent_id='frodo2',
                #     element=MoveTo(
                #         x=2.75,
                #         y=0.25,
                #     ),
                #     blocking=False
                # ),
                Move(
                    id='move3',
                    agent_id='frodo3',
                    element=MoveTo(
                        x=0.25,
                        y=2.75,
                    ),
                    blocking=False
                ),
                Move(
                    id='move4',
                    agent_id='frodo4',
                    element=MoveTo(
                        x=0.25,
                        y=0.25,
                    ),
                    blocking=False
                )
            ]
        )

        self.agent_manager.navigator.load_plan(plan, start=True)

    # ------------------------------------------------------------------------------------------------------------------
    def test2(self):
        self.logger.info("Running Test")

        plan = NavigatorPlan(
            id='test',
            actions=[
                Move(
                    id='move1',
                    agent_id='vfrodo1',
                    element=MoveTo(
                        x=2.75,
                        y=2.75,
                    ),
                    blocking=False
                ),
                # Move(
                #     id='move2',
                #     agent_id='frodo2',
                #     element=MoveTo(
                #         x=2.75,
                #         y=0.25,
                #     ),
                #     blocking=False
                # ),
                Move(
                    id='move3',
                    agent_id='vfrodo3',
                    element=MoveTo(
                        x=0.25,
                        y=2.75,
                    ),
                    blocking=False
                ),
                Move(
                    id='move4',
                    agent_id='vfrodo4',
                    element=MoveTo(
                        x=0.25,
                        y=0.25,
                    ),
                    blocking=False
                )
            ]
        )

        self.agent_manager.navigator.load_plan(plan, start=True)

    # ------------------------------------------------------------------------------------------------------------------
    def run_plan(self, plan_file: str):

        if not file_exists(plan_file):
            extended_plan_file = f"{PLANS_DIR}/{plan_file}"
            if not file_exists(extended_plan_file):
                self.logger.error(f"Plan file {plan_file} does not exist")
                return
            plan_file = extended_plan_file

        self.agent_manager.run_plan_from_file(plan_file)

    # === PRIVATE METHODS ==============================================================================================

    # === ALGORITHM METHODS ============================================================================================
    # def _prediction_centralized(self):
    #     if self.algorithm_state != AlgorithmState.RUNNING:
    #         return
    #
    #     for agent_id, agent_container in self.agents.items():
    #         # 3. Set the inputs
    #         agent_container.centralized_algorithm_agent.input = AlgorithmAgentInput.from_array(np.asarray([
    #             agent_container.testbed_object.dynamic_state.v,
    #             agent_container.testbed_object.dynamic_state.psi_dot
    #         ])
    #         )
    #
    #     self.algorithm_centralized.prediction()
    #
    # # ------------------------------------------------------------------------------------------------------------------
    # def _prediction_distributed(self):
    #     if self.algorithm_state != AlgorithmState.RUNNING:
    #         return
    #
    # # ------------------------------------------------------------------------------------------------------------------
    # def _prediction(self):
    #     if self.algorithm_state != AlgorithmState.RUNNING:
    #         return
    #
    #     for agent_id, agent_container in self.agents.items():
    #         agent_container.distributed_algorithm_agent.input = AlgorithmAgentInput.from_array(np.asarray([
    #             agent_container.testbed_object.dynamic_state.v,
    #             agent_container.testbed_object.dynamic_state.psi_dot
    #         ])
    #         )
    #
    #         agent_container.centralized_algorithm_agent.input = AlgorithmAgentInput.from_array(np.asarray([
    #             agent_container.testbed_object.dynamic_state.v,
    #             agent_container.testbed_object.dynamic_state.psi_dot
    #         ]))
    #
    #     self.algorithm_distributed.prediction()
    #     self.algorithm_centralized.prediction()
    #
    # # ------------------------------------------------------------------------------------------------------------------
    # def _correction(self):
    #     ...
    #
    # # ------------------------------------------------------------------------------------------------------------------
    # def _calculate_estimation_errors(self):
    #
    #     for agent_id, agent_container in self.agents.items():
    #         x_true = agent_container.testbed_object.state.x
    #         y_true = agent_container.testbed_object.state.y
    #         psi_true = agent_container.testbed_object.state.psi
    #
    #         x_estimated = agent_container.centralized_algorithm_agent.state.x
    #         y_estimated = agent_container.centralized_algorithm_agent.state.y
    #         psi_estimated = agent_container.centralized_algorithm_agent.state.psi
    #
    #         agent_container.error = AgentError(
    #             x=x_true - x_estimated,
    #             y=y_true - y_estimated,
    #             psi=psi_true - psi_estimated,
    #         )


# === FRODO APPLICATION CLI COMMAND SET ================================================================================
class FRODO_Application_CLI(CommandSet):
    name = 'frodo_app_cli'

    def __init__(self, app: FRODO_Application):
        super().__init__(self.name)
        self.app = app

        joystick_command_set = CommandSet('joystick')
        assign_joystick_command = Command(name='assign',
                                          function=self._assign_joystick,
                                          description='Assign a joystick to a robot',
                                          allow_positionals=True,
                                          arguments=[
                                              CommandArgument(name='joystick', type=int,
                                                              short_name='j',
                                                              description='ID of the joystick'),
                                              CommandArgument(name='robot',
                                                              short_name='r',
                                                              type=str,
                                                              description='ID of the robot')
                                          ]
                                          )

        joystick_command_set.addCommand(assign_joystick_command)

        remove_joystick_command = Command(name='remove',
                                          function=self._remove_joystick,
                                          description='Remove a joystick from an agent',
                                          allow_positionals=False,
                                          arguments=[
                                              CommandArgument(name='robot',
                                                              short_name='r',
                                                              type=str,
                                                              optional=True,
                                                              default=None,
                                                              description='ID of the robot to remove the joystick from'),
                                              CommandArgument(name='joystick',
                                                              short_name='j',
                                                              type=int,
                                                              optional=True,
                                                              default=None,
                                                              description='ID of the joystick to remove'
                                                              )
                                          ]
                                          )

        joystick_command_set.addCommand(remove_joystick_command)

        # start_command = Command(name='init',
        #                         function=self.app.init_application, )

        # self.addCommand(start_command)

        # test_command = Command(
        #     name='test',
        #     function=self.app.test2,
        #     description='Test the application',
        #
        # )
        # self.addCommand(test_command)

        rum_plan_command = Command(
            name='plan',
            function=self.app.run_plan,
            description='Run a plan',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='plan',
                                type=str,
                                short_name='p',
                                description='Name of the plan to run'),
            ]

        )
        self.addCommand(rum_plan_command)

        self.addChild(joystick_command_set)

    # ------------------------------------------------------------------------------------------------------------------
    def _assign_joystick(self, joystick: int, robot: str):

        # 1. get the joystick from the joystick manager
        joystick = self.app.joystick_manager.getJoystickById(joystick)

        if joystick is None:
            self.app.logger.warning(f'Joystick with ID {joystick} does not exist')
            return

        # 1. Check if this joystick is already assigned to a robot
        for r in self.app.testbed_manager.robot_manager.robots.values():
            if joystick == r.interfaces.joystick:
                self.app.logger.warning(f'Joystick {joystick.id} is already assigned to robot {r.id}')
                return

        # 2. Check if the joystick is assigned to an agent i nthe simulation
        for agent in self.app.simulation.agents.values():
            if joystick == agent.joystick:
                self.app.logger.warning(f"Joystick {joystick.id} is already assigned to robot {agent.agent_id}")

        # 2. Assign the joystick to the robot or agent
        if robot in self.app.testbed_manager.robot_manager.robots:
            robot = self.app.testbed_manager.robot_manager.getRobotById(robot)
            robot.interfaces.assignJoystick(joystick)
        elif robot in self.app.simulation.agents:
            agent = self.app.simulation.agents[robot]
            agent.assign_joystick(joystick)
        else:
            self.app.logger.warning(f'Robot with ID {robot} does not exist')

    # ------------------------------------------------------------------------------------------------------------------
    def _remove_joystick(self, robot: str = None, joystick: int = None):

        if robot is None and joystick is None:
            self.app.logger.warning('Either robot or joystick must be specified')
            return

        if robot is not None and joystick is not None:
            self.app.logger.warning('Either robot or joystick must be specified, not both')
            return

        if robot is not None:

            if robot in self.app.testbed_manager.robot_manager.robots:
                self.app.testbed_manager.robot_manager.robots[robot].interfaces.removeJoystick()
            elif robot in self.app.simulation.agents:
                self.app.simulation.agents[robot].remove_joystick()
            else:
                self.app.logger.warning(f'Robot with ID {robot} does not exist')
                return
        else:
            joystick = self.app.joystick_manager.getJoystickById(joystick)
            if joystick is None:
                self.app.logger.warning(f'Joystick with ID {joystick} does not exist')
                return

            owner_found = False
            for robot in self.app.testbed_manager.robot_manager.robots.values():
                if joystick == robot.interfaces.joystick:
                    robot.interfaces.removeJoystick()
                    owner_found = True
                    break

            if not owner_found:
                for agent in self.app.simulation.agents.values():
                    if joystick == agent.joystick:
                        agent.remove_joystick()
                        owner_found = True
                        break

            if not owner_found:
                self.app.logger.warning(f'Joystick {joystick.id} is not assigned to any robot')
                return

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------


if __name__ == '__main__':
    app = FRODO_Application()
    app.init()
    app.start()

    while True:
        time.sleep(10)
