from __future__ import annotations

import dataclasses
import enum
import math
import queue
import threading
import time
from typing import Optional, Callable

import numpy as np

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.network.network import getHostIP
from core.utils.sound.sound import SoundSystem
from core.utils.time import setInterval
from extensions.libs.babylon.src.babylon import BabylonVisualization
from extensions.libs.babylon.src.lib.objects.box.box import WallFancy
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.libs.babylon.src.lib.objects.frodo.frodo import BabylonFrodo
from extensions.tools.cli.cli import CLI, CommandSet, Command, CommandArgument
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.hardware.joystick.joystick_manager import Joystick, JoystickManager
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS
from extensions.simulation.src.objects.base_environment import BaseEnvironment
from extensions.simulation.src.objects.frodo_new import FRODO_DynamicAgent, DEFAULT_SAMPLE_TIME, FRODO_Input_LR, \
    FRODO_State


# === NAVIGATOR ================================================================================================

# === TUNABLE CONSTANTS ================================================================================================
class _NavConfig:
    """
    Central place for navigation/control constants.

    NOTE: Values below are conservative defaults and are meant as a starting point.
    - MAX_TRACK_SPEED:    Individual track limit (m/s).
    - TRACK_WIDTH:        Distance between left/right tracks (m).
    - CONTROL_TS:         Control loop period (s).
    - LOOKAHEAD:          Carrot lookahead distance (m). Used to soften heading when far.
    - LIN:                PI for linear (distance) channel.
    - ANG:                PI for angular (heading) channel.
    - SOFT_V_LIMIT:       Nominal linear speed cap during navigation (m/s).
    """

    MAX_TRACK_SPEED = 0.20
    TRACK_WIDTH = 0.150
    CONTROL_TS = 0.05

    # Carrot chasing on a point-to-point: we drive toward a "carrot" placed ahead
    # on the line-to-goal. Bigger lookahead -> softer turns.
    # LOOKAHEAD = 0.25
    LOOKAHEAD = 0.5

    # Linear (distance) PI
    LIN_KP = 0.9
    LIN_KI = 0.4
    LIN_I_LIMIT = 0.10  # clamp on the integrator (m/s contribution)

    # Angular (heading) PI
    ANG_KP = 2.2
    ANG_KI = 0.2
    ANG_I_LIMIT = 0.50  # clamp on the integrator (rad/s contribution)

    # Nominal caps (tighter than the physical limit to preserve headroom)
    SOFT_V_LIMIT = 0.18  # m/s
    SOFT_OMEGA_LIMIT = 2.0  # rad/s

    # Timeouts / defaults
    DEFAULT_MIN_DURATION = 0.0
    DEFAULT_MAX_DURATION = 60.0  # safety cap for a single element (s)


# === UTILS ============================================================================================================
def _wrap_angle(angle: float) -> float:
    """Wrap angle to [-pi, pi]."""
    a = (angle + math.pi) % (2.0 * math.pi) - math.pi
    return a


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _v_omega_to_tracks(v: float, omega: float, track_width: float) -> tuple[float, float]:
    """
    Convert body-frame (v, omega) to left/right track speeds.
    Unicycle-to-differential mapping:
        v = (vr + vl)/2
        omega = (vr - vl)/W
      -> vr = v + (W/2)*omega
         vl = v - (W/2)*omega
    """
    halfW = 0.5 * track_width
    vr = v + halfW * omega
    vl = v - halfW * omega
    return vl, vr


def _saturate_tracks(vl: float, vr: float, limit: float) -> tuple[float, float]:
    """
    Uniformly scale (if needed) to ensure |vl|, |vr| <= limit while preserving curvature.
    """
    max_mag = max(abs(vl), abs(vr), 1e-9)
    if max_mag <= limit:
        return vl, vr
    scale = limit / max_mag
    return vl * scale, vr * scale


# ======================================================================================================================
class TimeRef(enum.StrEnum):
    EXPERIMENT = "EXPERIMENT"  # time referenced to experiment start
    PRIMITIVE = "PRIMITIVE"  # time referenced to primitive start
    ABSOLUTE = "ABSOLUTE"  # time referenced to absolute time


@callback_definition
class NavigationElement_Callbacks:
    started: CallbackContainer
    finished: CallbackContainer
    error: CallbackContainer


@event_definition
class NavigationElement_Events:
    started: Event
    finished: Event
    error: Event


@dataclasses.dataclass
class NavigationElement:
    """
    Base type for all primitives.

    Life-cycle flags are set/cleared by Navigator.
    Subclasses don't need to spawn threads; the Navigator calls into them from a periodic _control_step.
    """
    active: bool = False
    finished: bool = False
    error: bool = False

    callbacks: NavigationElement_Callbacks = dataclasses.field(default_factory=NavigationElement_Callbacks)
    events: NavigationElement_Events = dataclasses.field(default_factory=NavigationElement_Events)

    min_duration: float | None = None
    max_duration: float | None = None

    stop_flag: bool = False

    # The Navigator sets these when scheduling/starting an element:
    _t0: float | None = None  # primitive (local) start time
    _exp_t0: float | None = None  # experiment/global start time

    def run(self):
        """
        Compatibility hook if you ever want a blocking primitive.
        We keep the non-blocking/step-based design, so this stays as a no-op.
        """
        ...


# === PRIMITIVES =======================================================================================================
# --- WAITING PRIMITIVES -----------------------------------------------------------------------------------------------
class Wait(NavigationElement):
    """
    Base for wait-like primitives. The Navigator will handle timing/event waits inside _control_step.
    """
    pass


@dataclasses.dataclass
class TimeWait(Wait):
    duration: float = 0.0
    reference: TimeRef = TimeRef.PRIMITIVE

    def __post_init__(self):
        if self.reference == TimeRef.ABSOLUTE:
            raise ValueError("Absolute time reference is not supported here. Use AbsoluteTimeWait instead.")


@dataclasses.dataclass
class AbsoluteTimeWait(Wait):
    unix_time: float = 0.0
    reference: TimeRef = TimeRef.ABSOLUTE


@dataclasses.dataclass
class EventWait(Wait):
    event: str = ""  # Name string to be delivered via Navigator.triggerEvent(...)


# --- MOVEMENT PRIMITIVES ----------------------------------------------------------------------------------------------
@dataclasses.dataclass
class RelativeStraightMove(NavigationElement):
    """
    Drive a given signed distance along the current heading (captured at start).
    """
    distance: float = 0.0
    speed: float | None = None
    arrive_tolerance: float = 0.05  # meters

    # Internal targets captured when the element starts
    _goal_x: Optional[float] = None
    _goal_y: Optional[float] = None


@dataclasses.dataclass
class MoveTo(NavigationElement):
    x: float = 0.0
    y: float = 0.0
    speed: float | None = None
    arrive_tolerance: float = 0.05  # in meters


@dataclasses.dataclass
class MoveToRelative(NavigationElement):
    dx: float = 0.0
    dy: float = 0.0
    speed: float | None = None
    arrive_tolerance: float = 0.05  # in meters

    # Internal
    _goal_x: Optional[float] = None
    _goal_y: Optional[float] = None


@dataclasses.dataclass
class TurnTo(NavigationElement):
    psi: float = 0.0
    speed: float | None = None
    arrive_tolerance: float = 0.02  # in radians


@dataclasses.dataclass
class RelativeTurn(NavigationElement):
    dpsi: float = 0.0  # in radians
    speed: float | None = None
    arrive_tolerance: float = 0.02  # in radians

    # Internal
    _goal_psi: Optional[float] = None


# ======================================================================================================================
@event_definition
class Navigator_Events:
    element_started: Event
    element_finished: Event
    element_error: Event
    navigation_started: Event
    navigation_paused: Event
    navigation_resumed: Event
    navigation_finished: Event
    navigation_error: Event


@callback_definition
class Navigator_Callbacks:
    element_started: CallbackContainer
    element_finished: CallbackContainer
    element_error: CallbackContainer
    navigation_started: CallbackContainer
    navigation_paused: CallbackContainer
    navigation_resumed: CallbackContainer
    navigation_finished: CallbackContainer
    navigation_error: CallbackContainer


@event_definition
class NavigatorInternal_Events:
    event: Event = Event(data_type=str)
    stop: Event


class NavigatorStatus(enum.StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class Navigator:
    """
    Simple single-threaded (plus one worker) Navigator:
    - A background thread runs a periodic loop at CONTROL_TS.
    - It dequeues one element at a time and drives it to completion.
    - Movement control = carrot-chasing with small PI on linear and angular channels.
    """
    speed_command_function: Callable[[float, float], None]
    state_fetch_function: Callable[[], FRODO_State]
    movement_queue: queue.Queue
    status: NavigatorStatus = NavigatorStatus.IDLE

    control_ts: float = _NavConfig.CONTROL_TS

    active_element: NavigationElement | None = None
    _exit: bool = False

    events: Navigator_Events
    callbacks: Navigator_Callbacks
    _internal_events: NavigatorInternal_Events

    # Integrators (reset per element)
    _i_lin: float = 0.0
    _i_ang: float = 0.0

    # === INIT =========================================================================================================
    def __init__(self, speed_command_function: Callable[[float, float], None],
                 state_fetch_function: Callable[[], FRODO_State]):

        self.speed_command_function = speed_command_function
        self.state_fetch_function = state_fetch_function
        self.movement_queue = queue.Queue()
        self.logger = Logger("NAVIGATOR", "DEBUG")
        self.callbacks = Navigator_Callbacks()
        self.events = Navigator_Events()
        self._internal_events = NavigatorInternal_Events()

        self._thread = threading.Thread(target=self._task, daemon=True)

    # === METHODS ======================================================================================================
    def start(self):
        self._thread.start()
        self.logger.info("Navigator started")

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        self._exit = True
        if self._thread.is_alive():
            self._thread.join()

        self.logger.info("Navigator stopped")

    # ------------------------------------------------------------------------------------------------------------------
    def startNavigation(self):
        """
        Start/arm the navigation loop if idle or paused.
        """
        if self.status in (NavigatorStatus.IDLE, NavigatorStatus.PAUSED, NavigatorStatus.STOPPED):
            self.status = NavigatorStatus.RUNNING
            self.events.navigation_started.set()
            self.callbacks.navigation_started.call()
            self.logger.info("Navigation started")

    # ------------------------------------------------------------------------------------------------------------------
    def stopNavigation(self):
        """
        Immediately stop current element and become IDLE.
        """
        self.status = NavigatorStatus.STOPPED
        self._i_lin = 0.0
        self._i_ang = 0.0
        if self.active_element:
            self.active_element.stop_flag = True
        self.speed_command_function(0.0, 0.0)
        self.events.navigation_finished.set()
        self.callbacks.navigation_finished.call()
        self.logger.info("Navigation stopped")

    # ------------------------------------------------------------------------------------------------------------------
    def pauseNavigation(self):
        """
        Pause: keep current element but freeze motion (zero speeds).
        """
        if self.status == NavigatorStatus.RUNNING:
            self.status = NavigatorStatus.PAUSED
            self.speed_command_function(0.0, 0.0)
            self.events.navigation_paused.set()
            self.callbacks.navigation_paused.call()
            self.logger.info("Navigation paused")

    # ------------------------------------------------------------------------------------------------------------------
    def resumeNavigation(self):
        if self.status == NavigatorStatus.PAUSED:
            self.status = NavigatorStatus.RUNNING
            self.events.navigation_resumed.set()
            self.callbacks.navigation_resumed.call()
            self.logger.info("Navigation resumed")

    # ------------------------------------------------------------------------------------------------------------------
    def runElement(self, element: NavigationElement):
        """
        Mark an element active and initialize its timing and any dynamic targets.
        """
        self.active_element = element
        element.active = True
        element.finished = False
        element.error = False
        element.stop_flag = False
        element._t0 = time.monotonic()
        if element._exp_t0 is None:
            element._exp_t0 = element._t0

        # Reset integrators per element
        self._i_lin = 0.0
        self._i_ang = 0.0

        # Fill defaults for duration caps
        if element.min_duration is None:
            element.min_duration = _NavConfig.DEFAULT_MIN_DURATION
        if element.max_duration is None:
            element.max_duration = _NavConfig.DEFAULT_MAX_DURATION

        # Per-primitive initialization that needs current state
        st = self.state_fetch_function()

        if isinstance(element, RelativeStraightMove):
            # Capture goal along current heading
            x0, y0, psi0 = st.x, st.y, st.psi
            element._goal_x = x0 + element.distance * math.cos(psi0)
            element._goal_y = y0 + element.distance * math.sin(psi0)

        elif isinstance(element, MoveToRelative):
            x0, y0 = st.x, st.y
            element._goal_x = x0 + element.dx
            element._goal_y = y0 + element.dy

        elif isinstance(element, RelativeTurn):
            psi0 = st.psi
            element._goal_psi = _wrap_angle(psi0 + element.dpsi)

        # Notify
        self.events.element_started.set(data=element)
        element.events.started.set()
        self.callbacks.element_started.call(element=element)
        element.callbacks.started.call()

        self.logger.debug(f"Element started: {element}")

    # ------------------------------------------------------------------------------------------------------------------
    def abortElement(self):
        """
        Abort current element and zero speeds.
        """
        if self.active_element:
            self.active_element.stop_flag = True
            self.active_element.active = False
            self.active_element = None
            self.speed_command_function(0.0, 0.0)
            self.logger.warning("Active element aborted")

    # ------------------------------------------------------------------------------------------------------------------
    def clearQueue(self):
        """
        Clear all pending elements. Current active element is not affected.
        """
        cleared = 0
        while True:
            try:
                _ = self.movement_queue.get_nowait()
                cleared += 1
            except queue.Empty:
                break
        if cleared:
            self.logger.info(f"Cleared {cleared} queued elements")

    # ------------------------------------------------------------------------------------------------------------------
    def addElement(self, element: NavigationElement):
        self.movement_queue.put(element)

    # ------------------------------------------------------------------------------------------------------------------
    def triggerEvent(self, name):
        """
        External hook to satisfy EventWait primitives:
        navigator.triggerEvent("ready") will complete a EventWait(event="ready").
        """
        self._internal_events.event.set(data=name)

    # === PRIVATE METHODS ==============================================================================================
    def _task(self):
        """
        Background worker. Dequeues elements and runs the control loop at fixed rate.
        """
        last = time.perf_counter()
        while not self._exit:
            now = time.perf_counter()
            dt = now - last
            if dt < self.control_ts:
                time.sleep(self.control_ts - dt)
                now = time.perf_counter()
            last = now

            try:
                self._control_step()
            except Exception as e:
                self.logger.error(f"Navigator control exception: {e}")
                # Fail-safe: stop robot and mark navigation error
                self.speed_command_function(0.0, 0.0)
                self.events.navigation_error.set(data=str(e))
                self.callbacks.navigation_error.call(error=e)

    # ------------------------------------------------------------------------------------------------------------------
    def _finish_active(self, ok: bool = True):
        """
        Mark active element finished/error, publish events/callbacks, and release it.
        """
        if not self.active_element:
            return
        el = self.active_element
        el.active = False
        el.finished = ok
        el.error = not ok
        self.active_element = None
        self._i_lin = 0.0
        self._i_ang = 0.0

        if ok:
            self.events.element_finished.set(data=el)
            el.events.finished.set()
            self.callbacks.element_finished.call(element=el)
            el.callbacks.finished.call()
            self.logger.debug(f"Element finished: {el}")
        else:
            self.events.element_error.set(data=el)
            el.events.error.set()
            self.callbacks.element_error.call(element=el)
            el.callbacks.error.call()
            self.logger.error(f"Element error/aborted: {el}")

        # Always stop the robot after a primitive unless another immediately starts
        self.speed_command_function(0.0, 0.0)

    # ------------------------------------------------------------------------------------------------------------------
    def _control_step(self):
        """
        One iteration of the navigation loop:
        - If RUNNING and no active element → dequeue next.
        - If PAUSED/IDLE → hold.
        - If there is an active element → compute command; check completion/timeout.
        """
        if self.status != NavigatorStatus.RUNNING:
            # Hold position
            self.speed_command_function(0.0, 0.0)
            return

        # No active element → fetch next (non-blocking)
        if self.active_element is None:
            try:
                nxt: NavigationElement = self.movement_queue.get_nowait()
            except queue.Empty:
                # Nothing to do; remain RUNNING and idle at zero
                self.speed_command_function(0.0, 0.0)
                return
            self.runElement(nxt)

        el = self.active_element
        assert el is not None

        # Safety: hard stop on external abort
        if el.stop_flag:
            self._finish_active(ok=False)
            return

        # Timeout management
        t = time.monotonic()
        t0 = el._t0 or t
        elapsed = t - t0
        if el.max_duration is not None and elapsed > el.max_duration:
            self.logger.warning(f"Element timeout (> {el.max_duration:.1f}s)")
            self._finish_active(ok=False)
            return

        # Dispatch per type
        st = self.state_fetch_function()

        # WAIT PRIMITIVES ----------------------------------------------------------------------------------------------
        if isinstance(el, TimeWait):
            # Choose reference
            ref_t0 = (el._t0 if el.reference == TimeRef.PRIMITIVE
                      else el._exp_t0 if el.reference == TimeRef.EXPERIMENT
            else None)
            assert ref_t0 is not None, "Invalid time reference for TimeWait"
            if (time.monotonic() - ref_t0) >= el.duration:
                self._finish_active(ok=True)
            else:
                self.speed_command_function(0.0, 0.0)
            return

        if isinstance(el, AbsoluteTimeWait):
            if time.time() >= el.unix_time:
                self._finish_active(ok=True)
            else:
                self.speed_command_function(0.0, 0.0)
            return

        if isinstance(el, EventWait):
            # Use the internal event bus (string payload). Accept stale in a short window.
            # If the event already happened shortly before, it will still complete thanks to history.
            got = self._internal_events.event.wait(
                predicate=lambda _f, d: d == el.event, stale_event_time=0.5, timeout=0.0
            )
            if got:
                self._finish_active(ok=True)
            else:
                self.speed_command_function(0.0, 0.0)
            return

        # MOVEMENT PRIMITIVES ------------------------------------------------------------------------------------------
        # Small helper: PI update with clamped integrator
        def _pi_update(err: float, i_acc: float, kp: float, ki: float, i_limit: float, dt: float) -> tuple[
            float, float]:
            i_acc = _clamp(i_acc + err * dt * ki, -i_limit, i_limit)
            u = kp * err + i_acc
            return u, i_acc

        # Command holders
        v_cmd = 0.0
        w_cmd = 0.0

        if isinstance(el, (MoveTo, MoveToRelative, RelativeStraightMove)):
            # Resolve target (xg, yg)
            if isinstance(el, MoveTo):
                xg, yg = el.x, el.y
            elif isinstance(el, MoveToRelative):
                if el._goal_x is None or el._goal_y is None:
                    # Should have been set at start
                    x0, y0 = st.x, st.y
                    el._goal_x = x0 + el.dx
                    el._goal_y = y0 + el.dy
                xg, yg = el._goal_x, el._goal_y
            else:  # RelativeStraightMove
                if el._goal_x is None or el._goal_y is None:
                    x0, y0, psi0 = st.x, st.y, st.psi
                    el._goal_x = x0 + el.distance * math.cos(psi0)
                    el._goal_y = y0 + el.distance * math.sin(psi0)
                xg, yg = el._goal_x, el._goal_y

            # Geometry
            dx = xg - st.x
            dy = yg - st.y
            dist = math.hypot(dx, dy)

            # Completion check (respect minimum duration too)
            if dist <= getattr(el, "arrive_tolerance", 0.05) and elapsed >= (el.min_duration or 0.0):
                self._finish_active(ok=True)
                return

            # Carrot heading: point somewhere between current pos and goal.
            # We place a "carrot" LOOKAHEAD meters short of the goal along the line-to-goal.
            if dist > 1e-6:
                step = max(0.0, dist - _NavConfig.LOOKAHEAD)
                cx = xg - (dx / dist) * step
                cy = yg - (dy / dist) * step
            else:
                cx, cy = xg, yg

            psi_des = math.atan2(cy - st.y, cx - st.x)
            e_psi = _wrap_angle(psi_des - st.psi)

            # PI in both channels
            v_sp = el.speed if el.speed is not None else _NavConfig.SOFT_V_LIMIT
            # Distance error as input for linear channel; clamp sign to move forward towards goal
            v_pi, self._i_lin = _pi_update(dist, self._i_lin,
                                           _NavConfig.LIN_KP, _NavConfig.LIN_KI, _NavConfig.LIN_I_LIMIT,
                                           self.control_ts)
            # Limit linear speed and also taper with heading error to avoid cutting corners
            v_cmd = _clamp(v_pi, -v_sp, v_sp) * math.cos(e_psi)

            w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                           _NavConfig.ANG_KP, _NavConfig.ANG_KI, _NavConfig.ANG_I_LIMIT,
                                           self.control_ts)
            w_cmd = _clamp(w_pi, -_NavConfig.SOFT_OMEGA_LIMIT, _NavConfig.SOFT_OMEGA_LIMIT)

        elif isinstance(el, (TurnTo, RelativeTurn)):
            # Resolve psi target
            if isinstance(el, TurnTo):
                psi_target = el.psi
            else:
                if el._goal_psi is None:
                    el._goal_psi = _wrap_angle(st.psi + el.dpsi)
                psi_target = el._goal_psi

            e_psi = _wrap_angle(psi_target - st.psi)

            # Completion?
            if abs(e_psi) <= el.arrive_tolerance and elapsed >= (el.min_duration or 0.0):
                self._finish_active(ok=True)
                return

            # Angular PI; keep v=0 to pivot in place (safer for tight environments)
            w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                           _NavConfig.ANG_KP, _NavConfig.ANG_KI, _NavConfig.ANG_I_LIMIT,
                                           self.control_ts)
            w_cmd = _clamp(w_pi, -_NavConfig.SOFT_OMEGA_LIMIT, _NavConfig.SOFT_OMEGA_LIMIT)
            v_cmd = 0.0

        else:
            # Unknown element type → error & stop
            self.logger.error(f"Unknown element type: {type(el).__name__}")
            self._finish_active(ok=False)
            return

        # Convert to track speeds + saturation
        vl, vr = _v_omega_to_tracks(v_cmd, w_cmd, _NavConfig.TRACK_WIDTH)
        vl, vr = _saturate_tracks(vl, vr, _NavConfig.MAX_TRACK_SPEED)

        # Dispatch to robot
        self.speed_command_function(vl, vr)


# === INTERACTIVE FRODO ================================================================================================
class InteractiveFrodo(FRODO_DynamicAgent):
    joystick: Joystick | None = None

    # === INIT =========================================================================================================
    def __init__(self, agent_id, *args, **kwargs):
        super().__init__(input_type=FRODO_Input_LR, agent_id=agent_id)
        self.logger = Logger(f'InteractiveFrodo {agent_id}', 'DEBUG')

        # self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self._input_function)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self._output_function)

        self.navigator = Navigator(speed_command_function=self.setMotorInput,
                                   state_fetch_function=self.getState, )

        self.startNavigation()

        setInterval(self.printState, 1)

    # === METHODS ======================================================================================================
    def startNavigation(self):

        # movement1 = RelativeStraightMove(distance=1)
        # movement2 = TimeWait(duration=2)
        # movement3 = RelativeTurn(dpsi=math.pi)
        # movement4 = RelativeStraightMove(distance=1.5)
        #
        # self.navigator.addElement(movement1)
        # self.navigator.addElement(movement2)
        # self.navigator.addElement(movement3)
        # self.navigator.addElement(movement4)

        movement1 = TimeWait(duration=2)
        movement2 = MoveTo(x=1, y=1)
        movement3 = TimeWait(duration=2)
        movement4 = MoveTo(x=-1, y=-1)
        movement5 = TurnTo(psi=0)

        self.navigator.addElement(movement1)
        self.navigator.addElement(movement2)
        self.navigator.addElement(movement3)
        self.navigator.addElement(movement4)
        self.navigator.addElement(movement5)

        self.navigator.start()
        self.navigator.startNavigation()

    # ------------------------------------------------------------------------------------------------------------------
    def setMotorInput(self, left, right):
        self.input.left = left
        self.input.right = right

    # ------------------------------------------------------------------------------------------------------------------
    def printState(self):
        print(self.state)
    # ------------------------------------------------------------------------------------------------------------------
    def getState(self) -> FRODO_State:
        return self.state

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
        self.soundsystem.speak('Start FRODO nav test')
        self.joystick_manager.start()
        self.gui.start()
        self.babylon_visualization.start()
        self.env.start()
        self.logger.info("FRODO nav test started")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.soundsystem.speak('FRODO nav test stopped')
        self.joystick_manager.exit()
        self.logger.info("FRODO nav test stopped")
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
