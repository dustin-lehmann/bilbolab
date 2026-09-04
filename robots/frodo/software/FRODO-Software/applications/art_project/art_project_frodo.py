"""
FRODO Art Project -- robot-side application.

This is the robot-side half of the art-project navigation framework. It fixes *how* a FRODO executes a
"go to position" command and reports back to the host, and leaves *what* happens inside (vision-based
localization and the position controller) to you.

Architecture
------------

    Host (software/robots/frodo/applications/artproject/application_artproject.py)
        |   executeFunction('go_to_position', {x, y, psi, speed, tolerance})     (WiFi, JSON)
        |   executeFunction('stop')
        |   executeFunction('get_pose' / 'get_status', request_response=True)
        v
    +--------------------------------------------------------------------------+
    |  ArtProject (this file)                                                  |
    |                                                                          |
    |  camera frame event --> localize(frame) --> self.pose         <-- YOUR CODE
    |                                                                          |
    |  control loop (settings.control_rate):                                   |
    |      target_reached(pose, target) ?                           <-- YOUR CODE (optional)
    |      compute_control(pose, target) -> (v_left, v_right)       <-- YOUR CODE
    |      frodo.control.setTrackSpeed(v_left, v_right)                        |
    |                                                                          |
    |  state machine: IDLE -> MOVING -> REACHED | ERROR | ABORTED              |
    +--------------------------------------------------------------------------+
        |   sendEvent('art_project', {'type': <event>, 'data': {...}})
        v
    Host: ArtProject_FRODO.events.{move_started, position_reached, error, aborted}

Where to put your code
----------------------
1. `localize(frame)`               return an ArtProject_Pose estimated from a camera frame (or None).
2. `compute_control(pose, target)` return the (v_left, v_right) track speeds in m/s.
3. `target_reached(pose, target)`  optional: replace the default distance / heading check.

Everything else (WiFi commands, the control thread, the state machine, event reporting) can stay as it is.
You may also replace the whole class, as long as the WiFi commands and events keep their names and payloads,
because that is exactly what the host side waits for.

Run on the robot with:
    python applications/art_project/art_project_frodo.py
"""
import dataclasses
import enum
import math
import threading
import time
from typing import Optional

from core.communication.wifi.data_link import CommandArgument
from core.utils.events import Event, EventFlag, event_definition
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.time import IntervalTimer
from robot.control.frodo_control import FRODO_ControlMode
from robot.definitions import MAX_TRACK_SPEED
from robot.frodo import FRODO

# Name of the WiFi event container. Every event this module sends is wrapped as
#   {'type': <event type>, 'data': {...}}  and sent as event 'art_project'.
# The host demultiplexes on 'type'. Must match WIFI_EVENT_CONTAINER on the host side.
WIFI_EVENT_CONTAINER = 'art_project'


# === DEFINITIONS ======================================================================================================
class ArtProject_State(enum.StrEnum):
    IDLE = 'IDLE'  # no target
    MOVING = 'MOVING'  # driving towards self.target
    REACHED = 'REACHED'  # last target reached, motors stopped
    ERROR = 'ERROR'  # last move failed (see ArtProject_ErrorType), motors stopped
    ABORTED = 'ABORTED'  # last move was interrupted by stop(), motors stopped


class ArtProject_ErrorType(enum.StrEnum):
    LOCALIZATION_LOST = 'LOCALIZATION_LOST'  # no valid pose for longer than settings.pose_timeout
    MOVE_TIMEOUT = 'MOVE_TIMEOUT'  # target not reached within settings.move_timeout
    CONTROL_EXCEPTION = 'CONTROL_EXCEPTION'  # localize() / compute_control() / target_reached() raised
    INVALID_TARGET = 'INVALID_TARGET'  # go_to_position() received a non-finite target


@dataclasses.dataclass
class ArtProject_Settings:
    control_rate: float = 20.0  # [Hz] rate of the control loop
    localization_rate: float = 10.0  # [Hz] max rate at which localize() is called with camera frames
    default_speed: float = 0.1  # [m/s] used when the host does not specify a speed
    arrive_tolerance: float = 0.05  # [m] distance below which a target counts as reached
    heading_tolerance: float = 0.1  # [rad] only used when the target has a heading
    pose_timeout: float = 1.0  # [s] max age of the last valid pose before LOCALIZATION_LOST
    move_timeout: float = 60.0  # [s] robot-side safety timeout for a single go_to_position()
    track_width: float = 0.150  # [m] distance between the tracks (same value as the Navigator uses)
    publish_pose_to_estimation: bool = True  # write our pose into frodo.estimation.state (streams to the host)


@dataclasses.dataclass
class ArtProject_Pose:
    """Pose of the robot in the world frame (x, y in m, psi in rad, counter-clockwise, 0 = +x axis)."""
    x: float
    y: float
    psi: float
    time: float = dataclasses.field(default_factory=time.time)  # [s] unix time of the measurement

    def to_dict(self) -> dict:
        return {'x': self.x, 'y': self.y, 'psi': self.psi, 'time': self.time}


@dataclasses.dataclass
class ArtProject_Target:
    x: float  # [m] world frame
    y: float  # [m] world frame
    psi: float | None = None  # [rad] final heading, None = don't care
    speed: float = 0.1  # [m/s] nominal speed
    tolerance: float = 0.05  # [m] arrival tolerance

    def to_dict(self) -> dict:
        return {'x': self.x, 'y': self.y, 'psi': self.psi, 'speed': self.speed, 'tolerance': self.tolerance}


@event_definition
class ArtProject_Events:
    """
    Robot-local events. Use them for on-robot logic (e.g. `art_project.events.position_reached.wait()`).
    The same events are also forwarded to the host over WiFi (see ArtProject._send_wifi_event).
    """
    move_started: Event  # data: ArtProject_Target
    position_reached: Event  # data: ArtProject_Pose
    error: Event = Event(flags=EventFlag('type', str))  # data: message, flag 'type': ArtProject_ErrorType
    aborted: Event  # data: ArtProject_Pose | None
    pose: Event  # data: ArtProject_Pose, set on every successful localize()


# === HELPERS ==========================================================================================================
def wrap_to_pi(angle: float) -> float:
    """Wrap an angle to (-pi, pi]."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


def v_omega_to_tracks(v: float, omega: float, track_width: float) -> tuple[float, float]:
    """Convert body-frame (v [m/s], omega [rad/s]) to differential track speeds (v_left, v_right) [m/s]."""
    half_width = 0.5 * track_width
    return v - half_width * omega, v + half_width * omega


# === ART PROJECT ======================================================================================================
class ArtProject:
    frodo: FRODO
    settings: ArtProject_Settings
    events: ArtProject_Events

    state: ArtProject_State
    target: ArtProject_Target | None
    pose: ArtProject_Pose | None
    last_frame = None  # the most recent camera frame (numpy array), for compute_control() if you need it

    # Gains of the placeholder controller in compute_control(). Replace the controller, not the gains.
    K_HEADING: float = 1.5  # [1/s]

    # === INIT =========================================================================================================
    def __init__(self, frodo: FRODO, settings: ArtProject_Settings | None = None):
        self.frodo = frodo
        self.settings = settings if settings is not None else ArtProject_Settings()
        self.logger = Logger("ART PROJECT", "DEBUG")
        self.events = ArtProject_Events()

        self.state = ArtProject_State.IDLE
        self.target = None
        self.pose = None
        self.last_frame = None

        self._move_start_time: float | None = None
        self._lock = threading.Lock()
        self._exit = False

        # Camera frames drive the localization. max_rate drops frames we cannot process in time.
        self._frame_listener = self.frodo.sensors.camera.events.frame.on(
            self._on_camera_frame,
            max_rate=self.settings.localization_rate,
        )

        self._register_wifi_commands()

        self._thread = threading.Thread(target=self._control_task, daemon=True)

        register_exit_callback(self.close, priority=5)

    # === METHODS ======================================================================================================
    def start(self):
        self._thread.start()
        self.logger.info("Art project started")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self._exit = True
        self._stop_motors()

    # === COMMANDS (called by the host over WiFi, or locally) ==========================================================
    def go_to_position(self, x: float, y: float, psi: float | None = None, speed: float | None = None,
                       tolerance: float | None = None) -> dict:
        """
        Start driving to (x, y[, psi]). Non-blocking: the control loop does the driving, the result is reported
        through the events 'position_reached', 'error' or 'aborted'. A new target while moving replaces the old one.
        """
        target = ArtProject_Target(
            x=float(x),
            y=float(y),
            psi=None if psi is None or math.isnan(psi) else float(psi),
            speed=float(speed) if speed is not None else self.settings.default_speed,
            tolerance=float(tolerance) if tolerance is not None else self.settings.arrive_tolerance,
        )

        if not (math.isfinite(target.x) and math.isfinite(target.y)):
            self._fail(ArtProject_ErrorType.INVALID_TARGET, f"Non-finite target {target}")
            return {'accepted': False}

        with self._lock:
            if self.state == ArtProject_State.MOVING:
                self.logger.warning(f"New target while moving. Replacing {self.target} by {target}")
            self.target = target
            self._move_start_time = time.time()
            self.state = ArtProject_State.MOVING

        # We command the track speeds ourselves, so the built-in navigator must not be active
        self.frodo.control.setMode(FRODO_ControlMode.EXTERNAL)

        self.logger.info(f"Go to {target}")
        self.events.move_started.set(target)
        self._send_wifi_event('move_started', {'target': target.to_dict()})
        return {'accepted': True}

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self) -> None:
        """Abort the current move (if any) and stop the motors."""
        with self._lock:
            was_moving = self.state == ArtProject_State.MOVING
            self.target = None
            self.state = ArtProject_State.ABORTED if was_moving else ArtProject_State.IDLE
            pose = self.pose

        self._stop_motors()

        if was_moving:
            self.logger.info("Move aborted")
            self.events.aborted.set(pose)
            self._send_wifi_event('aborted', {'pose': pose.to_dict() if pose is not None else None})

    # ------------------------------------------------------------------------------------------------------------------
    def get_pose(self) -> dict | None:
        """Latest pose as a dict (or None if we never localized)."""
        with self._lock:
            return self.pose.to_dict() if self.pose is not None else None

    # ------------------------------------------------------------------------------------------------------------------
    def get_status(self) -> dict:
        with self._lock:
            return {
                'state': str(self.state),
                'target': self.target.to_dict() if self.target is not None else None,
                'pose': self.pose.to_dict() if self.pose is not None else None,
            }

    # === STUDENT HOOKS ================================================================================================
    def localize(self, frame) -> Optional[ArtProject_Pose]:
        """
        TODO (student): estimate the robot pose in the world frame from a camera frame.

        Called at most `settings.localization_rate` times per second with the latest camera frame
        (numpy array, gray or RGB depending on the camera settings). Return an ArtProject_Pose, or None if no
        pose can be determined from this frame (the previous pose is then kept until `settings.pose_timeout`
        expires, after which a move fails with LOCALIZATION_LOST).

        You do not have to do everything in here: heavy processing can live in its own class, this method
        then only returns its latest result.

        Placeholder: falls back to the robot's built-in state estimate (OptiTrack, if it is running), so the
        whole framework can be tested end-to-end before your localization is ready.
        """
        state = self.frodo.common.getDynamicState()
        if state is None:
            return None
        return ArtProject_Pose(x=state.x, y=state.y, psi=state.psi)

    # ------------------------------------------------------------------------------------------------------------------
    def compute_control(self, pose: ArtProject_Pose, target: ArtProject_Target) -> tuple[float, float]:
        """
        TODO (student): your position controller.

        Called at `settings.control_rate` while a move is active. Return the track speeds (v_left, v_right) in m/s.
        `self.last_frame` holds the latest camera frame if your controller needs it (e.g. line following).
        Raising an exception in here aborts the move with a CONTROL_EXCEPTION error.

        Placeholder: proportional "turn towards the target, drive when facing it" controller.
        """
        dx = target.x - pose.x
        dy = target.y - pose.y
        distance = math.hypot(dx, dy)

        if distance < target.tolerance and target.psi is not None:
            # Position is fine, only the final heading is left: turn in place
            heading_error = wrap_to_pi(target.psi - pose.psi)
            v = 0.0
        else:
            heading_error = wrap_to_pi(math.atan2(dy, dx) - pose.psi)
            v = target.speed * max(0.0, math.cos(heading_error))  # slow down while not facing the target

        omega = self.K_HEADING * heading_error
        v_left, v_right = v_omega_to_tracks(v, omega, self.settings.track_width)

        v_left = max(-MAX_TRACK_SPEED, min(MAX_TRACK_SPEED, v_left))
        v_right = max(-MAX_TRACK_SPEED, min(MAX_TRACK_SPEED, v_right))
        return v_left, v_right

    # ------------------------------------------------------------------------------------------------------------------
    def target_reached(self, pose: ArtProject_Pose, target: ArtProject_Target) -> bool:
        """
        Optional (student): decide when a target counts as reached.

        Default: distance below `target.tolerance`, and, if the target has a heading, heading error below
        `settings.heading_tolerance`.
        """
        distance = math.hypot(target.x - pose.x, target.y - pose.y)
        if distance > target.tolerance:
            return False
        if target.psi is not None:
            return abs(wrap_to_pi(target.psi - pose.psi)) <= self.settings.heading_tolerance
        return True

    # === PRIVATE METHODS ==============================================================================================
    def _control_task(self):
        timer = IntervalTimer(interval=1.0 / self.settings.control_rate, raise_race_condition_error=False)
        while not self._exit:
            self._control_step()
            timer.sleep_until_next()

    # ------------------------------------------------------------------------------------------------------------------
    def _control_step(self):
        with self._lock:
            if self.state != ArtProject_State.MOVING:
                return
            target = self.target
            pose = self.pose
            move_start_time = self._move_start_time

        now = time.time()

        # 1. Do we have a fresh pose?
        if pose is None or (now - pose.time) > self.settings.pose_timeout:
            self._fail(ArtProject_ErrorType.LOCALIZATION_LOST,
                       f"No valid pose for more than {self.settings.pose_timeout:.1f} s")
            return

        # 2. Robot-side safety timeout (the host has its own, this one works even without a host)
        if (now - move_start_time) > self.settings.move_timeout:
            self._fail(ArtProject_ErrorType.MOVE_TIMEOUT,
                       f"Target {target} not reached within {self.settings.move_timeout:.1f} s")
            return

        # 3. Student code
        try:
            if self.target_reached(pose, target):
                self._reached(pose, target)
                return
            v_left, v_right = self.compute_control(pose, target)
        except Exception as e:
            self._fail(ArtProject_ErrorType.CONTROL_EXCEPTION, f"{type(e).__name__}: {e}")
            return

        self.frodo.control.setTrackSpeed(float(v_left), float(v_right))

    # ------------------------------------------------------------------------------------------------------------------
    def _on_camera_frame(self, frame, *args, **kwargs):
        self.last_frame = frame

        try:
            pose = self.localize(frame)
        except Exception as e:
            self.logger.error(f"localize() raised: {type(e).__name__}: {e}")
            with self._lock:
                moving = self.state == ArtProject_State.MOVING
            if moving:
                self._fail(ArtProject_ErrorType.CONTROL_EXCEPTION, f"localize(): {type(e).__name__}: {e}")
            return

        if pose is None:
            return

        with self._lock:
            self.pose = pose

        self.events.pose.set(pose)

        if self.settings.publish_pose_to_estimation:
            # Makes our pose part of the regular sample stream to the host (and usable by the built-in Navigator)
            estimation_state = self.frodo.estimation.state
            estimation_state.x = pose.x
            estimation_state.y = pose.y
            estimation_state.psi = pose.psi

    # ------------------------------------------------------------------------------------------------------------------
    def _reached(self, pose: ArtProject_Pose, target: ArtProject_Target):
        with self._lock:
            self.state = ArtProject_State.REACHED
            self.target = None
        self._stop_motors()

        self.logger.info(f"Position reached: ({pose.x:.2f}, {pose.y:.2f}, {pose.psi:.2f})")
        self.events.position_reached.set(pose)
        self._send_wifi_event('position_reached', {'pose': pose.to_dict(), 'target': target.to_dict()})

    # ------------------------------------------------------------------------------------------------------------------
    def _fail(self, error_type: ArtProject_ErrorType, message: str):
        with self._lock:
            self.state = ArtProject_State.ERROR
            self.target = None
            pose = self.pose
        self._stop_motors()

        self.logger.error(f"{error_type}: {message}")
        self.events.error.set(data=message, flags={'type': str(error_type)})
        self._send_wifi_event('error', {
            'type': str(error_type),
            'message': message,
            'pose': pose.to_dict() if pose is not None else None,
        })

    # ------------------------------------------------------------------------------------------------------------------
    def _stop_motors(self):
        self.frodo.control.setTrackSpeed(0.0, 0.0)

    # ------------------------------------------------------------------------------------------------------------------
    def _send_wifi_event(self, event_type: str, data: dict | None = None):
        self.frodo.communication.wifi.sendEvent(
            event=WIFI_EVENT_CONTAINER,
            data={'type': event_type, 'data': data if data is not None else {}},
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _register_wifi_commands(self):
        wifi = self.frodo.communication.wifi

        wifi.newCommand(
            identifier='go_to_position',
            function=self.go_to_position,
            description='Drive to a world-frame position. Non-blocking; reports via art_project events.',
            arguments=[
                CommandArgument(name='x', type=float, description='Target X [m]'),
                CommandArgument(name='y', type=float, description='Target Y [m]'),
                CommandArgument(name='psi', type=float, description='Final heading [rad] (optional)',
                                optional=True, default=None),
                CommandArgument(name='speed', type=float, description='Speed [m/s] (optional)',
                                optional=True, default=None),
                CommandArgument(name='tolerance', type=float, description='Arrival tolerance [m] (optional)',
                                optional=True, default=None),
            ]
        )

        wifi.newCommand(
            identifier='stop',
            function=self.stop,
            description='Abort the current move and stop the motors.',
            arguments=[]
        )

        wifi.newCommand(
            identifier='get_pose',
            function=self.get_pose,
            description='Return the latest pose estimate as a dict.',
            arguments=[]
        )

        wifi.newCommand(
            identifier='get_status',
            function=self.get_status,
            description='Return state, target and pose as a dict.',
            arguments=[]
        )


# ======================================================================================================================
if __name__ == '__main__':
    frodo = FRODO()
    frodo.init()

    art_project = ArtProject(frodo)

    frodo.start()
    art_project.start()

    while True:
        time.sleep(10)
