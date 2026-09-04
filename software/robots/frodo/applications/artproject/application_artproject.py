"""
FRODO Art Project -- host-side application.

Multi-robot navigation framework for the art project. The host does not drive the robots itself: each FRODO
localizes and controls its position on its own (robots/frodo/software/FRODO-Software/applications/art_project).
The host hands out targets, waits for the robots to report back, and reacts to errors.

Architecture
------------

    ArtProject_Application
        |
        |  plan(step) -> {robot_id: ArtProject_Target}                     <-- YOUR CODE (planning)
        |
        |  move_robots(targets):
        |      1. build wait condition:  OR( AND(all position_reached), OR(any error / aborted / robot lost) )
        |      2. dispatch go_to_position to every robot (parallel, non-blocking)
        |      3. wait for the condition with a timeout
        |      4. on failure / timeout: stop_all()
        |
        v
    ArtProject_FRODO (one per connected robot)                             <-- YOUR CODE (per-robot host logic)
        |   go_to_position(target)  ->  frodo.device.executeFunction('go_to_position', ...)
        |   stop()                  ->  frodo.device.executeFunction('stop')
        |   events.{move_started, position_reached, error, aborted}
        ^
        |   device.events.event, flag event == 'art_project', data {'type': ..., 'data': {...}}
        |
    FRODO (robots/frodo/robot/frodo.py)  <-- WiFi -->  robot-side ArtProject

Where to put your code
----------------------
1. `ArtProject_Application.plan(step)`   which robot goes where in mission step `step`.
2. `ArtProject_FRODO.on_position_reached / on_error`   optional per-robot hooks on the host.
3. Anything else you need per robot goes into ArtProject_FRODO, anything global into ArtProject_Application.

Run on the host with:
    cd software && python robots/frodo/applications/artproject/application_artproject.py
Then type `help` in the terminal, e.g. `goto frodo1 1.0 0.5`, `mission`, `stop`.
"""
from __future__ import annotations

import dataclasses
import re
import threading
import time

from core.utils.events import AND, OR, TIMEOUT, Event, EventContainer, EventFlag, Subscriber, event_definition, \
    pred_flag_equals
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from extensions.tools.cli.cli import CLI, Command, CommandArgument, CommandSet
from robots.frodo.robot.frodo import FRODO
from robots.frodo.robot.frodo_manager import FRODO_Manager

# Name of the WiFi event container the robot side uses. Must match the robot side.
WIFI_EVENT_CONTAINER = 'art_project'


# === DEFINITIONS ======================================================================================================
@dataclasses.dataclass
class ArtProject_Target:
    x: float  # [m] world frame
    y: float  # [m] world frame
    psi: float | None = None  # [rad] final heading, None = don't care
    speed: float | None = None  # [m/s], None = robot default
    tolerance: float | None = None  # [m], None = robot default

    def to_arguments(self) -> dict:
        return {'x': self.x, 'y': self.y, 'psi': self.psi, 'speed': self.speed, 'tolerance': self.tolerance}


@dataclasses.dataclass
class ArtProject_Pose:
    x: float
    y: float
    psi: float
    time: float

    @classmethod
    def from_dict(cls, data: dict | None) -> ArtProject_Pose | None:
        if not isinstance(data, dict):
            return None
        try:
            return cls(x=float(data['x']), y=float(data['y']), psi=float(data['psi']), time=float(data['time']))
        except (KeyError, TypeError, ValueError):
            return None


@dataclasses.dataclass
class ArtProject_Settings:
    move_timeout: float = 60.0  # [s] host-side timeout for one synchronized move (all robots of a step)
    request_timeout: float = 2.0  # [s] timeout for request/response calls (get_pose, get_status)


# === ART PROJECT FRODO (per-robot proxy) ==============================================================================
@event_definition
class ArtProject_FRODO_Events(EventContainer):
    """Host-side mirror of the robot's art_project events. The container id is the robot id (uid 'frodo1:error')."""
    move_started: Event  # data: target dict
    position_reached: Event  # data: {'pose': {...}, 'target': {...}}
    error: Event = Event(flags=EventFlag('type', str))  # data: {'type', 'message', 'pose'}
    aborted: Event  # data: {'pose': {...} | None}


class ArtProject_FRODO:
    """
    Host-side proxy for one FRODO in the art project. Wraps the WiFi commands and turns the robot's WiFi events
    into local Event objects that can be combined with AND / OR. Put your per-robot host-side logic in here.
    """
    frodo: FRODO
    events: ArtProject_FRODO_Events

    last_pose: ArtProject_Pose | None
    last_error: dict | None

    # === INIT =========================================================================================================
    def __init__(self, frodo: FRODO, settings: ArtProject_Settings | None = None):
        self.frodo = frodo
        self.settings = settings if settings is not None else ArtProject_Settings()
        # Event container ids may only contain letters, digits and '_' (robot ids are hostnames)
        self.events = ArtProject_FRODO_Events(id=re.sub(r'[^A-Za-z0-9_]', '_', frodo.id))
        self.logger = Logger(f"ArtProject {frodo.id}", "DEBUG")

        self.last_pose = None
        self.last_error = None

        # Every event the robot-side ArtProject sends arrives on device.events.event with the flag
        # event == 'art_project'. _on_robot_event demultiplexes it into self.events.
        self._event_listener = self.frodo.device.events.event.on(
            self._on_robot_event,
            predicate=pred_flag_equals('event', WIFI_EVENT_CONTAINER),
        )

    # === PROPERTIES ===================================================================================================
    @property
    def id(self) -> str:
        return self.frodo.id

    # === METHODS ======================================================================================================
    def go_to_position(self, target: ArtProject_Target) -> bool:
        """Send a target to the robot. Non-blocking: wait for events.position_reached / error / aborted."""
        try:
            self.frodo.device.executeFunction(function_name='go_to_position', arguments=target.to_arguments())
        except Exception as e:
            self.logger.error(f"Could not send go_to_position: {e}")
            return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self) -> bool:
        try:
            self.frodo.device.executeFunction(function_name='stop', arguments={})
        except Exception as e:
            self.logger.error(f"Could not send stop: {e}")
            return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def get_pose(self) -> ArtProject_Pose | None:
        """Ask the robot for its latest pose (blocking request/response)."""
        try:
            data = self.frodo.device.executeFunction(function_name='get_pose', arguments={}, return_type=dict,
                                                     request_response=True, timeout=self.settings.request_timeout)
        except TimeoutError:
            self.logger.warning("get_pose timed out")
            return None
        pose = ArtProject_Pose.from_dict(data)
        if pose is not None:
            self.last_pose = pose
        return pose

    # ------------------------------------------------------------------------------------------------------------------
    def get_status(self) -> dict | None:
        try:
            return self.frodo.device.executeFunction(function_name='get_status', arguments={}, return_type=dict,
                                                     request_response=True, timeout=self.settings.request_timeout)
        except TimeoutError:
            self.logger.warning("get_status timed out")
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self._event_listener.stop()

    # === STUDENT HOOKS ================================================================================================
    def on_position_reached(self, pose: ArtProject_Pose | None, target: dict):
        """Optional (student): called on the host whenever this robot reports a reached position."""
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def on_error(self, error_type: str, message: str, pose: ArtProject_Pose | None):
        """Optional (student): called on the host whenever this robot reports an error."""
        ...

    # === PRIVATE METHODS ==============================================================================================
    def _on_robot_event(self, event_data, *args, **kwargs):
        # event_data: {'event': 'art_project', 'container': ..., 'data': {'type': <type>, 'data': {...}}}
        payload = (event_data or {}).get('data', {}) or {}
        event_type = payload.get('type', None)
        data = payload.get('data', {}) or {}

        match event_type:
            case 'move_started':
                self.logger.debug(f"Move started: {data.get('target')}")
                self.events.move_started.set(data=data.get('target'))

            case 'position_reached':
                pose = ArtProject_Pose.from_dict(data.get('pose'))
                if pose is not None:
                    self.last_pose = pose
                self.logger.info(f"Position reached: {data.get('pose')}")
                self.events.position_reached.set(data=data)
                self.on_position_reached(pose, data.get('target', {}))

            case 'error':
                error_type = str(data.get('type', 'UNKNOWN'))
                message = str(data.get('message', ''))
                pose = ArtProject_Pose.from_dict(data.get('pose'))
                self.last_error = data
                self.logger.error(f"Robot error {error_type}: {message}")
                self.events.error.set(data=data, flags={'type': error_type})
                self.on_error(error_type, message, pose)

            case 'aborted':
                self.logger.warning("Move aborted on the robot")
                self.events.aborted.set(data=data)

            case _:
                self.logger.warning(f"Unknown art_project event: {event_type}")


# === ART PROJECT APPLICATION ==========================================================================================
@event_definition
class ArtProject_Application_Events:
    robot_connected: Event = Event(copy_data_on_set=False)  # data: ArtProject_FRODO
    robot_lost: Event = Event(copy_data_on_set=False)  # data: robot id (str)
    mission_finished: Event  # data: number of steps
    mission_failed: Event  # data: reason (str)


class ArtProject_Application:
    manager: FRODO_Manager
    robots: dict[str, ArtProject_FRODO]
    events: ArtProject_Application_Events
    settings: ArtProject_Settings

    # === INIT =========================================================================================================
    def __init__(self, settings: ArtProject_Settings | None = None):
        self.settings = settings if settings is not None else ArtProject_Settings()
        self.logger = Logger("ART APP", "DEBUG")

        self.manager = FRODO_Manager()
        self.robots = {}
        self.events = ArtProject_Application_Events()

        self._mission_thread: threading.Thread | None = None
        self._mission_abort = threading.Event()

        self.manager.events.new_robot.on(self._on_new_robot)
        self.manager.events.robot_disconnected.on(self._on_robot_disconnected)

        # CLI: our own commands plus the FRODO manager's 'robots' set
        self.command_set = ArtProject_CommandSet(self)
        self.command_set.addChild(self.manager.cli)
        self.cli = CLI(id='art_project', root=self.command_set)

        register_exit_callback(self.close, priority=5)

    # === METHODS ======================================================================================================
    def init(self):
        self.manager.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.manager.start()
        self.logger.info("Art project application started. Waiting for robots...")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.abort_mission()
        for robot in list(self.robots.values()):
            robot.close()

    # ------------------------------------------------------------------------------------------------------------------
    def stop_all(self):
        """Stop every connected robot. This is the default reaction to any failure."""
        self.logger.warning("Stopping all robots")
        for robot in list(self.robots.values()):
            robot.stop()

    # ------------------------------------------------------------------------------------------------------------------
    def wait_for_robots(self, robot_ids: list[str], timeout: float | None = None) -> bool:
        """Block until all robots in `robot_ids` are connected."""
        deadline = None if timeout is None else time.monotonic() + timeout

        # One wait per robot (a single AND cannot hold the same Event twice with different predicates).
        # The stale window covers a robot that connects right between the membership check and the wait.
        for robot_id in robot_ids:
            while robot_id not in self.robots:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                result, _ = self.events.robot_connected.wait(predicate=_pred_robot_id_is(robot_id),
                                                            timeout=remaining, stale_event_time=1.0)
                if result is TIMEOUT:
                    return False
        return True

    # === MISSION ======================================================================================================
    def plan(self, step: int) -> dict[str, ArtProject_Target] | None:
        """
        TODO (student): the planning. Called once per mission step, starting with step 0.

        Return {robot_id: ArtProject_Target} for every robot that should move in this step. The mission runner
        dispatches all of them in parallel and only continues with the next step after ALL of them reported
        `position_reached`. Return None when the mission is complete. `self.robots` holds the connected robots,
        `self.robots[robot_id].last_pose` their last reported poses.

        Placeholder: a two-step demo that sends every connected robot 0.5 m forward in x and then back.
        """
        robot_ids = sorted(self.robots.keys())
        if not robot_ids:
            return None

        match step:
            case 0:
                return {robot_id: ArtProject_Target(x=0.5, y=0.0) for robot_id in robot_ids}
            case 1:
                return {robot_id: ArtProject_Target(x=0.0, y=0.0, psi=0.0) for robot_id in robot_ids}
            case _:
                return None

    # ------------------------------------------------------------------------------------------------------------------
    def run_mission(self, blocking: bool = False) -> bool:
        """Run plan() step by step in a background thread (or blocking)."""
        if self._mission_thread is not None and self._mission_thread.is_alive():
            self.logger.warning("A mission is already running")
            return False

        self._mission_abort.clear()
        self._mission_thread = threading.Thread(target=self._mission_task, daemon=True)
        self._mission_thread.start()

        if blocking:
            self._mission_thread.join()
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def abort_mission(self):
        if self._mission_thread is not None and self._mission_thread.is_alive():
            self.logger.warning("Aborting mission")
            self._mission_abort.set()
            self.stop_all()

    # ------------------------------------------------------------------------------------------------------------------
    def move_robots(self, targets: dict[str, ArtProject_Target], timeout: float | None = None) -> tuple[bool, str]:
        """
        Send each robot its target in parallel and wait until ALL of them reached it, ANY of them failed,
        or the timeout expired. On failure or timeout all robots are stopped.

        Returns (success, reason).
        """
        if timeout is None:
            timeout = self.settings.move_timeout

        robots = []
        for robot_id in targets:
            if robot_id not in self.robots:
                return False, f"Robot {robot_id} is not connected"
            robots.append(self.robots[robot_id])

        if not robots:
            return True, "No robots to move"

        robot_ids = [robot.id for robot in robots]

        # 1. Build the wait condition BEFORE dispatching. Subscribers only see events that happen after they
        #    exist, so building it first guarantees we cannot miss a robot that answers very quickly.
        build_time = time.monotonic()
        all_reached = AND(*[robot.events.position_reached for robot in robots])
        any_failed = OR(
            *[robot.events.error for robot in robots],
            *[robot.events.aborted for robot in robots],
            (self.events.robot_lost, _pred_robot_id_in(robot_ids)),
        )
        condition = OR(all_reached, any_failed)

        try:
            # 2. Dispatch (non-blocking on the robot side)
            for robot in robots:
                self.logger.info(f"{robot.id} -> {targets[robot.id]}")
                if not robot.go_to_position(targets[robot.id]):
                    self.stop_all()
                    return False, f"Robot {robot.id} did not accept its target"

            # 3. Wait. The stale window reaches back to build_time, so a match that fired between dispatch and
            #    this call is still returned. It cannot pick up anything older, the condition did not exist yet.
            result, match = condition.wait(timeout=timeout,
                                           stale_event_time=(time.monotonic() - build_time) + 1.0)
        finally:
            _stop_subscriber_tree(condition)

        # 4. Evaluate
        if result is TIMEOUT:
            self.stop_all()
            return False, f"Timeout ({timeout:.0f} s): not all of {robot_ids} reached their target"

        if match.caused_by_group(all_reached):
            return True, f"All of {robot_ids} reached their target"

        # Something failed. The leaf events tell us which robot; the details are in the robot proxies.
        reasons = []
        for event, _, _ in match.group_causal_events(any_failed):
            if event is self.events.robot_lost:
                lost = [robot_id for robot_id in robot_ids if robot_id not in self.robots]
                reasons.append(f"robot(s) {lost} disconnected")
                continue
            for robot in robots:
                if event is robot.events.error:
                    error = robot.last_error or {}
                    reasons.append(f"{robot.id} error {error.get('type')}: {error.get('message')}")
                elif event is robot.events.aborted:
                    reasons.append(f"{robot.id} aborted")

        self.stop_all()
        return False, "; ".join(reasons) if reasons else "Unknown failure"

    # === PRIVATE METHODS ==============================================================================================
    def _mission_task(self):
        self.logger.important("Mission started")
        step = 0
        while not self._mission_abort.is_set():
            targets = self.plan(step)
            if targets is None:
                self.logger.important(f"Mission finished after {step} steps")
                self.events.mission_finished.set(step)
                return

            self.logger.important(f"Mission step {step}: {len(targets)} robot(s)")
            success, reason = self.move_robots(targets)
            if not success:
                self.logger.error(f"Mission failed in step {step}: {reason}")
                self.events.mission_failed.set(reason)
                return

            self.logger.info(f"Step {step} done: {reason}")
            step += 1

        self.logger.warning("Mission aborted")
        self.events.mission_failed.set("aborted")

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_robot(self, frodo: FRODO, *args, **kwargs):
        self.logger.info(f"New robot connected: {frodo.id}")
        robot = ArtProject_FRODO(frodo, settings=self.settings)
        self.robots[robot.id] = robot
        self.events.robot_connected.set(robot)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_robot_disconnected(self, frodo: FRODO, *args, **kwargs):
        self.logger.warning(f"Robot disconnected: {frodo.id}")
        robot = self.robots.pop(frodo.id, None)
        if robot is not None:
            robot.close()
        # A running move_robots() that involves this robot fails through this event
        self.events.robot_lost.set(frodo.id)


# === CLI ==============================================================================================================
class ArtProject_CommandSet(CommandSet):
    """Terminal commands for manual testing: list, goto, stop, pose, mission, abort."""

    def __init__(self, app: ArtProject_Application):
        self.app = app
        super().__init__(name='art', description='Art project commands')

        self.addCommand(Command(
            name='help',
            function=self._help,
            description='List all commands',
        ))

        self.addCommand(Command(
            name='list',
            function=self._list,
            description='List connected robots',
        ))

        self.addCommand(Command(
            name='goto',
            function=self._goto,
            execute_in_thread=True,
            arguments=[
                CommandArgument(name='robot', type=str, description='Robot id'),
                CommandArgument(name='x', type=float, description='Target X [m]'),
                CommandArgument(name='y', type=float, description='Target Y [m]'),
                CommandArgument(name='psi', type=float, short_name='p', description='Final heading [rad]',
                                optional=True, default=None),
                CommandArgument(name='speed', type=float, short_name='s', description='Speed [m/s]',
                                optional=True, default=None),
            ],
            description='Send one robot to a position and wait for the result (e.g. "goto frodo1 1.0 0.5")',
        ))

        self.addCommand(Command(
            name='stop',
            function=self._stop,
            arguments=[
                CommandArgument(name='robot', type=str, description='Robot id (omit for all)',
                                optional=True, default=None),
            ],
            description='Stop one robot, or all robots',
        ))

        self.addCommand(Command(
            name='pose',
            function=self._pose,
            arguments=[
                CommandArgument(name='robot', type=str, description='Robot id (omit for all)',
                                optional=True, default=None),
            ],
            description='Query the pose of one robot, or all robots',
        ))

        self.addCommand(Command(
            name='mission',
            function=self._mission,
            description='Run the mission defined by ArtProject_Application.plan()',
        ))

        self.addCommand(Command(
            name='abort',
            function=self.app.abort_mission,
            description='Abort the running mission and stop all robots',
        ))

    # ------------------------------------------------------------------------------------------------------------------
    def _help(self):
        for command in self.commands.values():
            arguments = " ".join(
                f"[{arg.name}]" if arg.optional else f"<{arg.name}>" for arg in command.arguments.values()
            )
            print(f"  {command.name:10s} {arguments:30s} {command.description}")
        for child in self.children.values():
            print(f"  {child.name + '/':10s} {'':30s} {child.description} ({len(child.commands)} commands)")

    # ------------------------------------------------------------------------------------------------------------------
    def _list(self):
        if not self.app.robots:
            print("No robots connected")
        for robot in self.app.robots.values():
            print(f"{robot.id}: last pose {robot.last_pose}")

    # ------------------------------------------------------------------------------------------------------------------
    def _goto(self, robot: str, x: float, y: float, psi: float | None = None, speed: float | None = None):
        target = ArtProject_Target(x=x, y=y, psi=psi, speed=speed)
        success, reason = self.app.move_robots({robot: target})
        print(f"{'OK' if success else 'FAILED'}: {reason}")

    # ------------------------------------------------------------------------------------------------------------------
    def _stop(self, robot: str | None = None):
        if robot is None:
            self.app.stop_all()
        elif robot in self.app.robots:
            self.app.robots[robot].stop()
        else:
            print(f"Unknown robot {robot}")

    # ------------------------------------------------------------------------------------------------------------------
    def _pose(self, robot: str | None = None):
        if robot is None:
            robots = list(self.app.robots.values())
        elif robot in self.app.robots:
            robots = [self.app.robots[robot]]
        else:
            print(f"Unknown robot {robot}")
            return
        if not robots:
            print("No robots connected")
        for r in robots:
            print(f"{r.id}: {r.get_pose()}")

    # ------------------------------------------------------------------------------------------------------------------
    def _mission(self):
        if not self.app.run_mission(blocking=False):
            print("Mission not started")


# === HELPERS ==========================================================================================================
def _pred_robot_id_is(robot_id: str):
    """Predicate for events whose data is an ArtProject_FRODO or a robot id."""

    def _pred(flags, data):
        return getattr(data, 'id', data) == robot_id

    return _pred


def _pred_robot_id_in(robot_ids: list[str]):
    def _pred(flags, data):
        return getattr(data, 'id', data) in robot_ids

    return _pred


def _stop_subscriber_tree(root: Subscriber):
    """Stop a subscriber built with AND()/OR() including all of its children, so nothing keeps listening."""
    seen = set()

    def _dfs(subscriber: Subscriber):
        if subscriber in seen:
            return
        seen.add(subscriber)
        for child in getattr(subscriber, '_compiled_children', []):
            _dfs(child)
        try:
            subscriber.stop()
        except Exception:
            pass

    _dfs(root)


# === MAIN =============================================================================================================
def main():
    app = ArtProject_Application()
    app.init()
    app.start()

    # Minimal terminal front-end for the CLI (the GUI is not needed for the art project)
    print("Art project CLI. Type 'help' for commands, Ctrl-C to exit.")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            time.sleep(1)
            continue
        if not line:
            continue
        try:
            app.cli.runCommand(line, from_root=True)
        except Exception as e:
            print(f"Error: {e}")


if __name__ == '__main__':
    main()
