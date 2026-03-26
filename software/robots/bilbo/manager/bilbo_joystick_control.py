import dataclasses

from extensions.tools.cli.cli import CommandSet, Command, CommandArgument
from extensions.hardware.joystick.joystick_manager import JoystickManager, Joystick
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.manager.bilbo_manager import BILBO_Manager
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger

LIMIT_TORQUE_FORWARD_DEFAULT = 1
LIMIT_TORQUE_TURN_DEFAULT = 1
LIMIT_SPEED_FORWARD_DEFAULT = 1.25
LIMIT_SPEED_TURN_DEFAULT = 5

logger = Logger('joystickcontrol')


@callback_definition
class BILBOJoystickControlCallbacks:
    new_assignment: CallbackContainer
    assignment_removed: CallbackContainer
    new_joystick: CallbackContainer
    joystick_disconnected: CallbackContainer


@event_definition
class BILBOJoystickControlEvents:
    new_assignment: Event
    assignment_removed: Event
    new_joystick: Event
    joystick_disconnected: Event


@dataclasses.dataclass
class JoystickAssignment:
    joystick: Joystick
    robot: BILBO


class BILBO_JoystickControl:
    bilbo_manager: BILBO_Manager
    joystick_manager: JoystickManager
    limits: dict
    assignments: dict[str, JoystickAssignment]

    callbacks: BILBOJoystickControlCallbacks

    # ==================================================================================================================
    def __init__(self, bilbo_manager: BILBO_Manager, auto_assign: bool = False):
        self.bilbo_manager = bilbo_manager
        self.auto_assign = auto_assign

        self.joystick_manager = JoystickManager()

        self.bilbo_manager.callbacks.new_robot.register(self._newRobot_callback)
        self.bilbo_manager.callbacks.robot_disconnected.register(self._robotDisconnected_callback)
        self.joystick_manager.callbacks.new_joystick.register(self._newJoystick_callback)
        self.joystick_manager.callbacks.joystick_disconnected.register(self._joystickDisconnected_callback)

        self.limits = {
            'torque': {
                'forward': LIMIT_TORQUE_FORWARD_DEFAULT,
                'turn': LIMIT_TORQUE_TURN_DEFAULT,
            },
            'speed': {
                'forward': LIMIT_SPEED_FORWARD_DEFAULT,
                'turn': LIMIT_SPEED_TURN_DEFAULT,
            }
        }

        self.assignments = {}

        self.callbacks = BILBOJoystickControlCallbacks()
        self.events = BILBOJoystickControlEvents()

        self.cli_command_set = BILBO_JoystickManager_CommandSet(self)

    # ==================================================================================================================
    def init(self):
        self.joystick_manager.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.joystick_manager.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def assignJoystick(self, joystick, bilbo):

        logger.info(f"Try to assign Joystick: {joystick.id} -> Robot: {bilbo.id}")
        if isinstance(joystick, str):
            joystick = self.joystick_manager.getJoystickById(joystick)
            if joystick is None:
                return
        if isinstance(bilbo, str):
            bilbo = self.bilbo_manager.getRobotById(bilbo)
            if bilbo is None:
                return

        if joystick.id in self.assignments:
            self.unassignJoystick(joystick)

        self.assignments[joystick.id] = JoystickAssignment(joystick, bilbo)

        bilbo.interfaces.addJoystick(joystick)

        logger.info(f"Assign Joystick: {joystick.id} -> Robot: {bilbo.id}")

        for callback in self.callbacks.new_assignment:
            callback(joystick, bilbo)

    # ------------------------------------------------------------------------------------------------------------------
    def unassignJoystick(self, joystick):
        if isinstance(joystick, str):
            joystick = self.joystick_manager.getJoystickById(joystick)
            if joystick is None:
                return

        for key, assignment in self.assignments.items():
            if assignment.joystick == joystick:
                self.assignments.pop(key)
                logger.info(f"Unassign Joystick: {joystick.id} -> Robot: {assignment.robot.id}")
                joystick.clearAllButtonCallbacks()
                assignment.robot.interfaces.removeJoystick()

                for callback in self.callbacks.assignment_removed:
                    callback(joystick, assignment.robot)
                return

    # ------------------------------------------------------------------------------------------------------------------
    def robotIsAssigned(self, robot: BILBO):
        for assignment in self.assignments.values():
            if assignment.robot == robot:
                return assignment.joystick
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getJoysticksWithAssignments(self):
        out = {}
        for joystick in self.joystick_manager.joysticks.values():
            out[joystick.id] = {
                'joystick': joystick,
                'assigned_robot': self.assignments[joystick.id].robot.id if joystick.id in self.assignments else None,
            }

        return out

    # ------------------------------------------------------------------------------------------------------------------
    def getFirstJoystick(self):
        if len(self.joystick_manager.joysticks) == 0:
            return None
        return list(self.joystick_manager.joysticks.values())[0]

    # ------------------------------------------------------------------------------------------------------------------
    def resetLimits(self):
        self.limits['torque']['forward'] = LIMIT_TORQUE_FORWARD_DEFAULT
        self.limits['torque']['turn'] = LIMIT_TORQUE_TURN_DEFAULT
        self.limits['speed']['forward'] = LIMIT_SPEED_FORWARD_DEFAULT
        self.limits['speed']['turn'] = LIMIT_SPEED_TURN_DEFAULT

    # ------------------------------------------------------------------------------------------------------------------
    def _getFirstFreeJoystick(self):
        for joystick in self.joystick_manager.joysticks.values():
            if joystick.id not in self.assignments:
                return joystick
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _getFirstUnassignedRobot(self):
        assigned_robot_ids = {a.robot.id for a in self.assignments.values()}
        for robot in self.bilbo_manager.robots.values():
            if robot.id not in assigned_robot_ids:
                return robot
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _newRobot_callback(self, robot, *args, **kwargs):
        if self.auto_assign:
            joystick = self._getFirstFreeJoystick()
            if joystick is not None:
                logger.info(f"Auto-assigning joystick {joystick.id} to new robot {robot.id}")
                self.assignJoystick(joystick, robot)

    # ------------------------------------------------------------------------------------------------------------------
    def _robotDisconnected_callback(self, robot, *args, **kwargs):
        for assignment in self.assignments.values():
            if assignment.robot == robot:
                self.unassignJoystick(assignment.joystick)
                return

    # ------------------------------------------------------------------------------------------------------------------
    def _newJoystick_callback(self, joystick, *args, **kwargs):
        if self.auto_assign:
            robot = self._getFirstUnassignedRobot()
            if robot is not None:
                logger.info(f"Auto-assigning new joystick {joystick.id} to robot {robot.id}")
                self.assignJoystick(joystick, robot)

        for callback in self.callbacks.new_joystick:
            callback(joystick)

    # ------------------------------------------------------------------------------------------------------------------
    def _joystickDisconnected_callback(self, joystick, *args, **kwargs):
        try:
            for assignment in self.assignments.values():
                if assignment.joystick == joystick:
                    self.unassignJoystick(assignment.joystick)
        except Exception as e:
            ...
        for callback in self.callbacks.joystick_disconnected:
            callback(joystick)


# ======================================================================================================================
class BILBO_JoystickManager_CommandSet(CommandSet):
    name = 'joysticks'
    description = 'Joystick Control of BILBO robots'

    def __init__(self, joystick_control: BILBO_JoystickControl):

        self.joystick_control = joystick_control

        list_joysticks_command = Command(name='list',
                                         function=self._list_joysticks,
                                         allow_positionals=False,
                                         description='Lists all joysticks')

        rumble_command = Command(name='rumble',
                                 function=self._rumble_joystick,
                                 allow_positionals=True,
                                 arguments=[
                                     CommandArgument(name='id',
                                                     short_name='i',
                                                     type=int,
                                                     description='ID of the joystick',
                                                     optional=False,
                                                     ),
                                 ],
                                 description='Rumbles the given joystick')

        assign_command = Command(name='assign',
                                 function=self._assign_joystick,
                                 allow_positionals=True,
                                 arguments=[
                                     CommandArgument(name='id',
                                                     short_name='i',
                                                     type=int,
                                                     description='ID of the joystick',
                                                     optional=False,
                                                     ),
                                     CommandArgument(name='robot',
                                                     short_name='r',
                                                     type=str,
                                                     description='ID of the robot',
                                                     optional=False,
                                                     ),
                                 ],
                                 description='Assigns a joystick to a robot')

        unassign_command = Command(name='unassign',
                                   function=self._unassign_joystick,
                                   allow_positionals=True,
                                   arguments=[
                                       CommandArgument(name='id',
                                                       short_name='i',
                                                       type=int,
                                                       description='ID of the joystick',
                                                       optional=True,
                                                       default=None
                                                       ),
                                       CommandArgument(name='all',
                                                       is_flag=True,
                                                       type=bool,
                                                       description='Unassign all joysticks',
                                                       default=False)
                                   ])

        super().__init__(name='joysticks', commands=[list_joysticks_command,
                                                      rumble_command,
                                                      assign_command,
                                                      unassign_command],
                         children=[])

    def _list_joysticks(self):
        output = ''
        for joystick in self.joystick_control.joystick_manager.joysticks.values():
            output += f"{joystick.id}: {joystick.name}\n"

        if output == "":
            output = "No joysticks connected"
        self.joystick_control.joystick_manager.logger.info(output)

    def _rumble_joystick(self, id: int):
        joystick = self.joystick_control.joystick_manager.getJoystickById(id)
        if joystick is None:
            return f"Joystick with ID {id} not found"
        joystick.rumble(strength=0.3, duration=300)

    def _assign_joystick(self, id: int, robot: str):
        joystick = self.joystick_control.joystick_manager.getJoystickById(id)
        if joystick is None:
            return f"Joystick with ID {id} not found"
        joystick.rumble(strength=0.3, duration=300)

        robot = self.joystick_control.bilbo_manager.getRobotById(robot)
        if robot is None:
            return f"Robot with ID {robot} not found"

        self.joystick_control.assignJoystick(joystick, robot)

    def _unassign_joystick(self, id: int = None, all: bool = False):

        if id and all:
            return f"Cannot assign joystick {id} and unassign all at the same time"

        if id:
            joystick = self.joystick_control.joystick_manager.getJoystickById(id)
            if joystick is None:
                return f"Joystick with ID {id} not found"

            self.joystick_control.unassignJoystick(joystick)
            return

        if all:
            for joystick in self.joystick_control.joystick_manager.joysticks.values():
                self.joystick_control.unassignJoystick(joystick)
