from __future__ import annotations

import time

import numpy as np

from core.utils.callbacks import Callback
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.sound.sound import SoundSystem
from extensions.libs.babylon.src.babylon import BabylonVisualization
from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.libs.babylon.src.lib.objects.box.box import WallFancy, Wall
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.tools.cli.cli import CommandSet, CLI, Command, CommandArgument
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.buttons import Button
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS
from simulation.objects.base_environment import BaseEnvironment
from robots.bilbo.simulation.model import BILBO_DynamicAgent, BILBO_Control_Mode, DEFAULT_BILBO_MODEL, \
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES, BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS
from extensions.hardware.joystick.joystick_manager import JoystickManager, Joystick

BILBO_MAPPINGS = {
    'bilbo1': {
        'color': [0.7, 0, 0],
        'text': '1'
    },
    'bilbo2': {
        'color': [0, 0.7, 0],
        'text': '2'
    },
    'bilbo3': {
        'color': [0, 0.4, 0.9],
        'text': '3'
    }

}


# === INTERACTIVE BILBO ================================================================================================
class InteractiveBILBO(BILBO_DynamicAgent):
    joystick: Joystick | None = None

    # === INIT =========================================================================================================
    def __init__(self, agent_id, *args, **kwargs):
        super().__init__(agent_id, model=DEFAULT_BILBO_MODEL, *args, **kwargs)

        self.logger = Logger(f'InteractiveBILBO {agent_id}', 'DEBUG')

        self.eigenstructureAssignment(poles=BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
                                      eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS)

        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self.input_function)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self.output_function)

    # === METHODS ======================================================================================================
    def assignJoystick(self, joystick: Joystick):
        self.joystick = joystick

        self.joystick.callbacks.A.register(self.enableController)
        self.joystick.callbacks.B.register(self.disableController)

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self):
        if self.joystick is None:
            return
        self.joystick.callbacks.A.remove(self.enableController)
        self.joystick.callbacks.B.remove(self.disableController)
        self.joystick = None

    # ------------------------------------------------------------------------------------------------------------------
    def enableController(self):
        self.logger.info(f'Controller enabled')
        self.mode = BILBO_Control_Mode.BALANCING

    # ------------------------------------------------------------------------------------------------------------------
    def disableController(self):
        self.logger.info(f'Controller disabled')
        self.mode = BILBO_Control_Mode.OFF

    # ------------------------------------------------------------------------------------------------------------------
    def input_function(self):
        if self.joystick is None:
            self.input = [0, 0]
            return

        axis_forward = self.joystick.getAxis('LEFT_VERTICAL')
        axis_turn = self.joystick.getAxis('RIGHT_HORIZONTAL')

        left_wheel = axis_forward * 0.7 + axis_turn * 1
        right_wheel = axis_forward * 0.7 - axis_turn * 1

        self.input = [left_wheel, right_wheel]

    # ------------------------------------------------------------------------------------------------------------------
    def output_function(self):
        ...


# === PRIVATE METHODS ==================================================================================================


# === BILBO INTERACTIVE EXAMPLE ========================================================================================
class BILBO_InteractiveExample:
    joystick_manager: JoystickManager
    babylon_visualization: BabylonVisualization
    robots: dict[str, dict]

    cli: CLI
    gui: GUI
    command_set: BILBO_Interactive_CommandSet
    soundsystem: SoundSystem

    # === INIT =========================================================================================================
    def __init__(self):
        self.logger = Logger('BILBO_InteractiveExample', 'DEBUG')
        self.joystick_manager = JoystickManager()
        self.joystick_manager.callbacks.new_joystick.register(self._newJoystick_callback)
        self.joystick_manager.callbacks.joystick_disconnected.register(self._joystickDisconnected_callback)

        self.robots = {}

        self.command_set = BILBO_Interactive_CommandSet(self)

        self.cli = CLI(id='bilbo_interactive', root=self.command_set)

        self.gui = GUI(id='bilbo_interactive', host='localhost', run_js=True)
        self.gui.cli_terminal.setCLI(self.cli)

        self.babylon_visualization = BabylonVisualization(id='babylon', babylon_config={
            'title': 'BILBO Interactive'})

        # Sound System for speaking and sounds
        self.soundsystem = SoundSystem(primary_engine='etts', volume=1)
        self.soundsystem.start()

        # Simulation Environment
        self.env = BaseEnvironment(Ts=0.01, run_mode='rt')

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
        self.joystick_manager.start()
        self.gui.start()
        self.babylon_visualization.start()
        self.env.start()
        self.logger.info("BILBO interactive started")
        self.soundsystem.speak('BILBO interactive started')

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.soundsystem.speak('BILBO interactive stopped')
        self.joystick_manager.exit()
        self.logger.info("BILBO interactive stopped")
        time.sleep(2)

    # ------------------------------------------------------------------------------------------------------------------
    def addRobot(self, robot_id: str):

        # Check if the robot already exists
        if robot_id in self.robots:
            self.logger.warning(f'Robot with ID {robot_id} already exists')
            return

        if robot_id not in BILBO_MAPPINGS:
            self.logger.warning(f'Robot with ID {robot_id} is not mapped. Please use one of:')
            for robot_id, mapping in BILBO_MAPPINGS.items():
                self.logger.warning(f'  {robot_id}: {mapping}')
            return

        # Create a new simulated robot
        robot = InteractiveBILBO(agent_id=robot_id)

        # Add it to the environment
        self.env.addObject(robot)

        self.robots[robot_id] = {'robot': robot}

        # Add a babylon object

        robot_babylon = BabylonBilbo(object_id=robot_id, color=BILBO_MAPPINGS[robot_id]['color'],
                                     text=BILBO_MAPPINGS[robot_id]['text'])
        self.babylon_visualization.addObject(robot_babylon)

        self.robots[robot_id]['babylon'] = robot_babylon
        self.logger.info(f'Robot with ID {robot_id} added')

    # ------------------------------------------------------------------------------------------------------------------
    def removeRobot(self, robot: str | InteractiveBILBO):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def assignJoystick(self, joystick: int, robot: str | InteractiveBILBO):

        joystick = self.joystick_manager.getJoystickById(joystick)
        if joystick is None:
            self.logger.warning(f'Joystick with ID {joystick} does not exist')
            return
        robot = self.getRobotByID(robot)
        if robot is None:
            self.logger.warning(f'Robot with ID {robot} does not exist')

        # Check if this joystick is already assigned to another robot
        for robot_id, robot_data in self.robots.items():
            if robot_data['robot'].joystick == joystick:
                self.logger.warning(f'Joystick with ID {joystick} is already assigned to robot {robot_id}')
                robot_data['robot'].removeJoystick()

        robot.assignJoystick(joystick)
        self.logger.info(f'Joystick assigned: {joystick.id} -> {robot.agent_id}')

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self, robot: str | InteractiveBILBO):
        robot = self.getRobotByID(robot)
        if robot is None:
            self.logger.warning(f'Robot with ID {robot} does not exist')
            return
        robot.removeJoystick()
        self.logger.info(f'Joystick of robot {robot.agent_id} removed')

    # ------------------------------------------------------------------------------------------------------------------
    def getRobotByID(self, robot_id: str) -> InteractiveBILBO | None:
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
    def reset(self):
        # Delete all robots
        self.logger.info('Resetting simulation')
        for robot in list(self.robots.values()):
            robot['robot'].removeJoystick()
            self.env.removeObject(robot['robot'])
            self.babylon_visualization.removeObject(robot['babylon'])
            self.logger.info(f'Robot {robot["robot"].agent_id} removed')
            self.robots.pop(robot['robot'].agent_id)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildGUI(self):

        # Add a simple category
        cat1 = Category('cat1', max_pages=10)

        # Add a page
        page1 = Page('page1')
        cat1.addPage(page1)

        # Add it to the GUI
        self.gui.addCategory(cat1)

        # Add the Babylon Widget
        self.babylon_widget = BabylonWidget(widget_id='babylon_widget')
        page1.addWidget(self.babylon_widget, row=1, column=1, height=18, width=36)

        # Reset Button
        reset_button = Button(text="Reset", callback=self.reset)
        page1.addWidget(reset_button, height=2, width=4)

        bilbo1_button = Button(text="Add BILBO 1", callback=Callback(
            function=self.addRobot,
            inputs={
                'robot_id': 'bilbo1'
            },
            discard_inputs=True,
        ))
        page1.addWidget(bilbo1_button, height=2, width=4)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildBabylon(self):

        floor = SimpleFloor('floor', size_y=50, size_x=50, texture='floor_bright.png')
        self.babylon_visualization.addObject(floor)

        wall1 = WallFancy('wall1', length=5, texture='wood4.png', include_end_caps=True)
        wall1.setPosition(y=2.5)
        self.babylon_visualization.addObject(wall1)

        wall2 = WallFancy('wall2', length=5, texture='wood4.png', include_end_caps=True)
        self.babylon_visualization.addObject(wall2)
        wall2.setPosition(y=-2.5)

        wall3 = WallFancy('wall3', length=5, texture='wood4.png')
        wall3.setPosition(x=2.5)
        wall3.setAngle(np.pi / 2)
        self.babylon_visualization.addObject(wall3)

        wall4 = WallFancy('wall4', length=5, texture='wood4.png')
        wall4.setPosition(x=-2.5)
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
                                           theta=state.theta,
                                           psi=state.psi)
            except Exception as e:
                self.logger.error(f'Error updating robot {robot["robot"].agent_id}: {e}')


# === BILBO INTERACTIVE CLI ============================================================================================
class BILBO_Interactive_CommandSet(CommandSet):

    def __init__(self, example: BILBO_InteractiveExample):
        super().__init__('bilbo_interactive')
        self.example = example

        add_robot_command = Command(
            function=self.example.addRobot,
            name='add_robot',
            description='Add a new robot to the simulation',
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


def main():
    example = BILBO_InteractiveExample()

    example.init()
    example.start()

    while True:
        time.sleep(10)


if __name__ == '__main__':
    main()
