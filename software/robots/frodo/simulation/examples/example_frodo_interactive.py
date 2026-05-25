from __future__ import annotations

import time

import numpy as np

from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.network.network import getHostIP
from core.utils.sound.sound import SoundSystem
from extensions.libs.babylon.src.babylon import BabylonVisualization
from extensions.libs.babylon.src.lib.objects.box.box import WallFancy
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.libs.babylon.src.lib.objects.frodo.frodo import BabylonFrodo
from extensions.tools.cli.cli import CLI, CommandSet, Command, CommandArgument
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.hardware.joystick.joystick_manager import Joystick, JoystickManager
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS
from simulation.objects.base_environment import BaseEnvironment
from robots.frodo.simulation.frodo import FRODO_DynamicAgent, DEFAULT_SAMPLE_TIME


# === INTERACTIVE FRODO ================================================================================================
class InteractiveFrodo(FRODO_DynamicAgent):
    joystick: Joystick | None = None

    # === INIT =========================================================================================================
    def __init__(self, agent_id, *args, **kwargs):
        super().__init__(agent_id)
        self.logger = Logger(f'InteractiveFrodo {agent_id}', 'DEBUG')

        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self._input_function)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self._output_function)

    # === METHODS ======================================================================================================
    def assignJoystick(self, joystick: Joystick):
        self.joystick = joystick

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self):
        if self.joystick is None:
            return
        self.joystick = None

    # === PRIVATE METHODS ==============================================================================================
    def _input_function(self):
        if self.joystick is None:
            self.input = [0, 0]
            return
        axis_forward = self.joystick.getAxis('LEFT_VERTICAL')

        if abs(axis_forward) < 0.05:
            axis_forward = 0

        axis_turn = self.joystick.getAxis('RIGHT_HORIZONTAL')

        if abs(axis_turn) < 0.05:
            axis_turn = 0

        self.input.v = -3*axis_forward * 0.2
        self.input.psi_dot = -3*axis_turn

    # ------------------------------------------------------------------------------------------------------------------
    def _output_function(self):
        ...


# === FRODO EXAMPLE INTERACTIVE ========================================================================================
class FRODO_ExampleInteractive:
    joystick_manager: JoystickManager
    babylon_visualization: BabylonVisualization

    cli: CLI
    gui: GUI
    command_set: FRODO_Interactive_CommandSet
    robots: dict[str, dict]
    soundsystem: SoundSystem

    # === INIT =========================================================================================================
    def __init__(self):
        self.logger = Logger('FRODO_ExampleInteractive', 'DEBUG')
        self.joystick_manager = JoystickManager()
        self.joystick_manager.callbacks.new_joystick.register(self._newJoystick_callback)
        self.joystick_manager.callbacks.joystick_disconnected.register(self._joystickDisconnected_callback)

        self.robots = {}
        host = 'localhost'
        self.command_set = FRODO_Interactive_CommandSet(self)

        self.cli = CLI(id='frodo_interactive', root=self.command_set)

        self.gui = GUI(id='frodo_interactive', host=host, run_js=True)
        self.gui.cli_terminal.setCLI(self.cli)

        self.babylon_visualization = BabylonVisualization(id='babylon', host=host, babylon_config={
            'title': 'FRODO Interactive'})

        # Sound System for speaking and sounds
        self.soundsystem = SoundSystem(primary_engine='etts', volume=1)
        self.soundsystem.start()

        # Simulation Environment
        self.env = BaseEnvironment(Ts=DEFAULT_SAMPLE_TIME, run_mode='rt')

        self.env.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self._simulationOutputStep)

        # Make a logging redirection
        addLogRedirection(self._logRedirection, minimum_level='DEBUG')

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self.joystick_manager.init()
        self._buildGUI()
        self._buildBabylon()
        self.babylon_visualization.init()
        self.env.init()
        self.env.initialize()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.soundsystem.speak('Start FRODO interactive')
        self.joystick_manager.start()
        self.gui.start()
        self.babylon_visualization.start()
        self.env.start()
        self.logger.info("FRODO interactive started")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.soundsystem.speak('FRODO interactive stopped')
        self.joystick_manager.exit()
        self.logger.info("FRODO interactive stopped")
        time.sleep(2)

    # ------------------------------------------------------------------------------------------------------------------
    def addRobot(self, robot_id: str):
        if robot_id in self.robots:
            self.logger.warning(f'Robot with ID {robot_id} already exists')
            return

        robot = InteractiveFrodo(agent_id=robot_id)

        self.env.addObject(robot)

        self.robots[robot_id] = {'robot': robot}

        robot_babylon = BabylonFrodo(object_id=robot_id)
        self.babylon_visualization.addObject(robot_babylon)

        self.robots[robot_id]['babylon'] = robot_babylon
        self.logger.info(f'Robot with ID {robot_id} added')

    # ------------------------------------------------------------------------------------------------------------------
    def assignJoystick(self, joystick: int, robot: str | InteractiveFrodo):
        if isinstance(robot, str):
            robot = self.getRobotByID(robot)
            if robot is None:
                self.logger.warning(f'Robot with ID {robot} does not exist')
                return

        joystick = self.joystick_manager.getJoystickById(joystick)
        if joystick is None:
            self.logger.warning(f'Joystick with ID {joystick} does not exist')

        robot.assignJoystick(joystick)
        self.logger.info(f'Joystick assigned: {joystick.id} -> {robot.agent_id}')

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self, robot: str | InteractiveFrodo):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def getRobotByID(self, robot_id: str) -> InteractiveFrodo | None:
        if robot_id in self.robots:
            return self.robots[robot_id]['robot']
        else:
            return None

    # === PRIVATE METHODS ==============================================================================================
    def _newJoystick_callback(self, joystick: Joystick):
        self.soundsystem.speak(f'New joystick {joystick.id} connected.')

    # ------------------------------------------------------------------------------------------------------------------
    def _joystickDisconnected_callback(self, joystick: Joystick):
        self.soundsystem.speak(f'Joystick with {joystick.id} disconnected.')

    # ------------------------------------------------------------------------------------------------------------------
    def _buildGUI(self):
        # Add a simple category
        cat1 = Category('FRODO Interactive', max_pages=1)

        # Add a page
        page1 = Page('page1')
        cat1.addPage(page1)

        # Add it to the GUI
        self.gui.addCategory(cat1)

        # Add the Babylon Widget
        self.babylon_widget = BabylonWidget(widget_id='babylon_widget')
        page1.addWidget(self.babylon_widget, row=1, column=1, height=18, width=36)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildBabylon(self):
        floor = SimpleFloor('floor', size_y=50, size_x=50, texture='floor_bright.png')
        self.babylon_visualization.addObject(floor)

        wall1 = WallFancy('wall1', length=3, texture='wood4.png', include_end_caps=True)
        wall1.setPosition(y=1.5)
        self.babylon_visualization.addObject(wall1)

        wall2 = WallFancy('wall2', length=3, texture='wood4.png', include_end_caps=True)
        self.babylon_visualization.addObject(wall2)
        wall2.setPosition(y=-1.5)

        wall3 = WallFancy('wall3', length=3, texture='wood4.png')
        wall3.setPosition(x=1.5)
        wall3.setAngle(np.pi / 2)
        self.babylon_visualization.addObject(wall3)

        wall4 = WallFancy('wall4', length=3, texture='wood4.png')
        wall4.setPosition(x=-1.5)
        wall4.setAngle(np.pi / 2)
        self.babylon_visualization.addObject(wall4)

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        print_text = f"[{logger.name}] {log}"
        color = LOGGING_COLORS[level]
        color = [c / 255 for c in color]
        self.gui.print(print_text, color=color)

    # ------------------------------------------------------------------------------------------------------------------
    def _simulationOutputStep(self):
        # Update all BILBOs
        for robot in self.robots.values():
            try:
                state = robot['robot'].state
                robot['babylon'].set_state(x=state.x,
                                           y=state.y,
                                           psi=state.psi)
            except Exception as e:
                self.logger.error(f'Error updating robot {robot["robot"].agent_id}: {e}')


# === FRODO INTERACTIVE CLI ============================================================================================
class FRODO_Interactive_CommandSet(CommandSet):
    def __init__(self, example: FRODO_ExampleInteractive):
        super().__init__('frodo_interactive')
        self.example = example

        add_robot_command = Command(
            function=self.example.addRobot,
            name='add_frodo',
            description='Add a new robot',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='robot_id', type=str, description='ID of the robot to add')
            ]
        )

        self.addCommand(add_robot_command)

        assign_joystick_command = Command(
            function=self.example.assignJoystick,
            name='assign_joystick',
            description='Assign a joystick to a robot',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='joystick', type=int, description='ID of the joystick to assign'),
                CommandArgument(name='robot', type=str, description='ID of the robot to assign the joystick to')
            ]
        )
        self.addCommand(assign_joystick_command)


# ======================================================================================================================


if __name__ == '__main__':
    example = FRODO_ExampleInteractive()
    example.init()
    example.start()

    while True:
        time.sleep(10)
