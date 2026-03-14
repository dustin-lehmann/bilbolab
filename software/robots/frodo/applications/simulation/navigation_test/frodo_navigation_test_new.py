from __future__ import annotations

import dataclasses
import enum
import math
import queue
import threading
import time
from typing import Optional, Callable, Tuple

import numpy as np

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.network.network import getHostIP
from core.utils.sound.sound import SoundSystem
from core.utils.time import setInterval, delayed_execution
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

# If you run this inside your sim example file, these come from:
# from extensions.simulation.src.objects.frodo_new import (
#     FRODO_DynamicAgent, DEFAULT_SAMPLE_TIME, FRODO_Input_LR, FRODO_State
# )
# For this module we only need FRODO_State's shape (x, y, v, psi, psi_dot).
# We'll type against it but not import here to keep this file self-contained.
# Replace 'FRODO_State' below with your sim's class when integrating.


# === TUNABLE CONSTANTS ================================================================================================
class _NavConfig:
    """
    Central place for navigation/control constants.

    NOTE: Values below are conservative defaults and are meant as a starting point.
    - MAX_TRACK_SPEED:    Individual track limit (m/s).
    - TRACK_WIDTH:        Distance between left/right tracks (m).
    - CONTROL_TS:         Control loop period (s).
    - LOOKAHEAD:          Carrot lookahead distance (m). Used to soften heading when far.
    - LIN/ANG PI:         Small integrators to fight friction/imperfections.
    - SOFT_V_LIMIT:       Nominal linear speed cap during navigation (m/s).
    """

    MAX_TRACK_SPEED = 0.2
    TRACK_WIDTH = 0.150
    CONTROL_TS = 0.02

    # Carrot-chasing lookahead (increase for straighter paths)
    LOOKAHEAD = 0.25

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


# Small helper used by primitives
def _pi_update(err: float, i_acc: float, kp: float, ki: float, i_limit: float, dt: float) -> tuple[float, float]:
    i_acc = _clamp(i_acc + err * dt * ki, -i_limit, i_limit)
    u = kp * err + i_acc
    return u, i_acc


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


# === PRIMITIVE CONTEXT (what Navigator passes into each primitive step) ===============================================
@dataclasses.dataclass
class PrimitiveContext:
    config: _NavConfig
    control_ts: float
    now: float
    t0: float
    exp_t0: float
    internal_event: Event  # NavigatorInternal_Events.event

    def event_matched(self, name: str, stale_window: float = 0.5) -> bool:
        """Return True if the string event occurred within the stale_window."""
        return self.internal_event.has_match_in_window(lambda _f, d: d == name, window=stale_window)


@dataclasses.dataclass
class NavigationElement:
    """
    Base type for all primitives.

    Lifecycle flags are handled by Navigator.
    Each primitive may implement:
      - on_start(state, ctx): optional initialization when primitive becomes active.
      - step(state, ctx) -> (v_cmd, w_cmd, done): compute command and completion.

    The Navigator converts (v_cmd, w_cmd) to track speeds and applies saturation.
    """
    active: bool = False
    finished: bool = False
    error: bool = False

    callbacks: NavigationElement_Callbacks = dataclasses.field(default_factory=NavigationElement_Callbacks)
    events: NavigationElement_Events = dataclasses.field(default_factory=NavigationElement_Events)

    min_duration: float | None = None
    max_duration: float | None = None

    stop_flag: bool = False

    # Navigator-managed timestamps
    _t0: float | None = None
    _exp_t0: float | None = None

    # --- API for subclasses -------------------------------------------------------------------------------------------
    def on_start(self, state, ctx: PrimitiveContext):
        """Optional hook run once when the element is activated."""
        return

    def step(self, state, ctx: PrimitiveContext) -> Tuple[float, float, bool]:
        """Return (v_cmd [m/s], w_cmd [rad/s], done: bool)."""
        return 0.0, 0.0, True  # default: do nothing and finish immediately


# === PRIMITIVES =======================================================================================================
# --- WAITING PRIMITIVES -----------------------------------------------------------------------------------------------
class Wait(NavigationElement):
    pass


@dataclasses.dataclass
class TimeWait(Wait):
    duration: float = 0.0
    reference: TimeRef = TimeRef.PRIMITIVE

    def __post_init__(self):
        if self.reference == TimeRef.ABSOLUTE:
            raise ValueError("Absolute time reference is not supported here. Use AbsoluteTimeWait instead.")

    def step(self, state, ctx: PrimitiveContext):
        ref_t0 = ctx.t0 if self.reference == TimeRef.PRIMITIVE else ctx.exp_t0
        done = (time.monotonic() - ref_t0) >= self.duration
        return 0.0, 0.0, done


@dataclasses.dataclass
class AbsoluteTimeWait(Wait):
    unix_time: float = 0.0
    reference: TimeRef = TimeRef.ABSOLUTE

    def step(self, state, ctx: PrimitiveContext):
        done = time.time() >= self.unix_time
        return 0.0, 0.0, done


@dataclasses.dataclass
class EventWait(Wait):
    event: str = ""

    def step(self, state, ctx: PrimitiveContext):
        done = ctx.event_matched(self.event, stale_window=0.5)
        return 0.0, 0.0, done


# --- MOVEMENT PRIMITIVES ----------------------------------------------------------------------------------------------
@dataclasses.dataclass
class _MovementBase(NavigationElement):
    """Common PI and limits for movement primitives."""
    speed: float | None = None
    arrive_tolerance: float = 0.05  # meters or radians (override meaning per primitive)

    # Per-primitive integrators
    _i_lin: float = 0.0
    _i_ang: float = 0.0

    def on_start(self, state, ctx: PrimitiveContext):
        self._i_lin = 0.0
        self._i_ang = 0.0


@dataclasses.dataclass
class RelativeStraightMove(_MovementBase):
    """Drive a signed distance along the heading captured at start."""
    distance: float = 0.0
    _goal_x: Optional[float] = None
    _goal_y: Optional[float] = None

    def on_start(self, state, ctx: PrimitiveContext):
        super().on_start(state, ctx)
        psi0 = state.psi
        self._goal_x = state.x + self.distance * math.cos(psi0)
        self._goal_y = state.y + self.distance * math.sin(psi0)

    def step(self, state, ctx: PrimitiveContext):
        assert self._goal_x is not None and self._goal_y is not None
        xg, yg = self._goal_x, self._goal_y

        dx, dy = xg - state.x, yg - state.y
        dist = math.hypot(dx, dy)

        if dist <= self.arrive_tolerance:
            return 0.0, 0.0, True

        # Carrot placement
        look = ctx.config.LOOKAHEAD
        step = max(0.0, dist - look) if dist > 1e-6 else 0.0
        cx = xg - (dx / (dist + 1e-9)) * step
        cy = yg - (dy / (dist + 1e-9)) * step

        psi_des = math.atan2(cy - state.y, cx - state.x)
        e_psi = _wrap_angle(psi_des - state.psi)

        # PI channels
        v_sp = self.speed if self.speed is not None else ctx.config.SOFT_V_LIMIT
        v_pi, self._i_lin = _pi_update(dist, self._i_lin,
                                       ctx.config.LIN_KP, ctx.config.LIN_KI, ctx.config.LIN_I_LIMIT,
                                       ctx.control_ts)
        v_cmd = _clamp(v_pi, -v_sp, v_sp) * math.cos(e_psi)

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = _clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return v_cmd, w_cmd, False


@dataclasses.dataclass
class MoveTo(_MovementBase):
    x: float = 0.0
    y: float = 0.0

    def step(self, state, ctx: PrimitiveContext):
        dx, dy = self.x - state.x, self.y - state.y
        dist = math.hypot(dx, dy)

        if dist <= self.arrive_tolerance:
            return 0.0, 0.0, True

        look = ctx.config.LOOKAHEAD
        step = max(0.0, dist - look) if dist > 1e-6 else 0.0
        cx = self.x - (dx / (dist + 1e-9)) * step
        cy = self.y - (dy / (dist + 1e-9)) * step

        psi_des = math.atan2(cy - state.y, cx - state.x)
        e_psi = _wrap_angle(psi_des - state.psi)

        v_sp = self.speed if self.speed is not None else ctx.config.SOFT_V_LIMIT
        v_pi, self._i_lin = _pi_update(dist, self._i_lin,
                                       ctx.config.LIN_KP, ctx.config.LIN_KI, ctx.config.LIN_I_LIMIT,
                                       ctx.control_ts)
        v_cmd = _clamp(v_pi, -v_sp, v_sp) * math.cos(e_psi)

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = _clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return v_cmd, w_cmd, False


@dataclasses.dataclass
class MoveToRelative(_MovementBase):
    dx: float = 0.0
    dy: float = 0.0
    _goal_x: Optional[float] = None
    _goal_y: Optional[float] = None

    def on_start(self, state, ctx: PrimitiveContext):
        super().on_start(state, ctx)
        self._goal_x = state.x + self.dx
        self._goal_y = state.y + self.dy

    def step(self, state, ctx: PrimitiveContext):
        assert self._goal_x is not None and self._goal_y is not None
        dx, dy = self._goal_x - state.x, self._goal_y - state.y
        dist = math.hypot(dx, dy)

        if dist <= self.arrive_tolerance:
            return 0.0, 0.0, True

        look = ctx.config.LOOKAHEAD
        step = max(0.0, dist - look) if dist > 1e-6 else 0.0
        cx = self._goal_x - (dx / (dist + 1e-9)) * step
        cy = self._goal_y - (dy / (dist + 1e-9)) * step

        psi_des = math.atan2(cy - state.y, cx - state.x)
        e_psi = _wrap_angle(psi_des - state.psi)

        v_sp = self.speed if self.speed is not None else ctx.config.SOFT_V_LIMIT
        v_pi, self._i_lin = _pi_update(dist, self._i_lin,
                                       ctx.config.LIN_KP, ctx.config.LIN_KI, ctx.config.LIN_I_LIMIT,
                                       ctx.control_ts)
        v_cmd = _clamp(v_pi, -v_sp, v_sp) * math.cos(e_psi)

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = _clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return v_cmd, w_cmd, False


@dataclasses.dataclass
class TurnTo(_MovementBase):
    psi: float = 0.0
    arrive_tolerance: float = 0.02  # radians

    def step(self, state, ctx: PrimitiveContext):
        e_psi = _wrap_angle(self.psi - state.psi)
        if abs(e_psi) <= self.arrive_tolerance:
            return 0.0, 0.0, True

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = _clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return 0.0, w_cmd, False


@dataclasses.dataclass
class RelativeTurn(_MovementBase):
    dpsi: float = 0.0
    arrive_tolerance: float = 0.02  # radians
    _goal_psi: Optional[float] = None

    def on_start(self, state, ctx: PrimitiveContext):
        super().on_start(state, ctx)
        self._goal_psi = _wrap_angle(state.psi + self.dpsi)

    def step(self, state, ctx: PrimitiveContext):
        assert self._goal_psi is not None
        e_psi = _wrap_angle(self._goal_psi - state.psi)
        if abs(e_psi) <= self.arrive_tolerance:
            return 0.0, 0.0, True

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = _clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return 0.0, w_cmd, False


# --- NEW: TURN TO POINT -----------------------------------------------------------------------------------------------
@dataclasses.dataclass
class TurnToPoint(_MovementBase):
    """
    Pivot in place to face the world-frame point (x, y).
    Useful before a MoveTo if you want straighter approaches.
    """
    x: float = 0.0
    y: float = 0.0
    arrive_tolerance: float = 0.02  # radians

    def step(self, state, ctx: PrimitiveContext):
        psi_des = math.atan2(self.y - state.y, self.x - state.x)
        e_psi = _wrap_angle(psi_des - state.psi)
        if abs(e_psi) <= self.arrive_tolerance:
            return 0.0, 0.0, True

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = _clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return 0.0, w_cmd, False


# --- COMPOSITE: COORDINATED MOVE TO -----------------------------------------------------------------
@dataclasses.dataclass
class CoordinatedMoveTo(NavigationElement):
    """
    Composite primitive:
      1) TurnToPoint(x, y)
      2) MoveTo(x, y)
      3) (optional) TurnTo(psi_end)

    Tolerances are exposed so you can tune how 'tight' each stage is.
    """
    x: float = 0.0
    y: float = 0.0
    psi_end: float | None = None

    # Per-stage tolerances / speed
    pre_rotate_tolerance: float = 0.02  # rad for the initial TurnToPoint
    arrive_tolerance: float = 0.05  # m for the MoveTo
    final_heading_tolerance: float = 0.02  # rad for the final TurnTo
    speed: float | None = None  # linear speed cap during MoveTo

    # Internal sub-primitives & stage
    _stage: str = dataclasses.field(default="TURN1", init=False)
    _turn1: TurnToPoint | None = dataclasses.field(default=None, init=False)
    _move: MoveTo | None = dataclasses.field(default=None, init=False)
    _turn2: TurnTo | None = dataclasses.field(default=None, init=False)

    def on_start(self, state, ctx: PrimitiveContext):
        # Build sub-primitives with requested tolerances/speed.
        self._turn1 = TurnToPoint(x=self.x, y=self.y,
                                  arrive_tolerance=self.pre_rotate_tolerance)
        self._move = MoveTo(x=self.x, y=self.y,
                            arrive_tolerance=self.arrive_tolerance,
                            speed=self.speed)
        self._turn2 = TurnTo(psi=self.psi_end if self.psi_end is not None else 0.0,
                             arrive_tolerance=self.final_heading_tolerance) if self.psi_end is not None else None

        # Initialize sub-primitives (reset their integrators, etc.)
        self._turn1.on_start(state, ctx)
        self._move.on_start(state, ctx)
        if self._turn2 is not None:
            self._turn2.on_start(state, ctx)

        # Smart skip: if we already face the target within tolerance, start with MOVE.
        psi_des = math.atan2(self.y - state.y, self.x - state.x)
        if abs(_wrap_angle(psi_des - state.psi)) <= self.pre_rotate_tolerance:
            self._stage = "MOVE"
        else:
            self._stage = "TURN1"

        # Also skip final turn if psi_end is effectively aligned at start (rare but cheap)
        if self._turn2 is not None and self._stage == "TURN1":
            if abs(_wrap_angle(self._turn2.psi - state.psi)) <= self.final_heading_tolerance \
                    and math.hypot(self.x - state.x, self.y - state.y) <= self.arrive_tolerance:
                self._stage = "DONE"

    def step(self, state, ctx: PrimitiveContext) -> tuple[float, float, bool]:
        # Stage machine
        if self._stage == "TURN1":
            v, w, done = self._turn1.step(state, ctx)
            if done:
                self._stage = "MOVE"
                # brief settle: stop this tick; next tick MOVE will start
                return 0.0, 0.0, False
            return v, w, False

        if self._stage == "MOVE":
            v, w, done = self._move.step(state, ctx)
            if done:
                if self._turn2 is not None:
                    self._stage = "TURN2"
                    return 0.0, 0.0, False
                else:
                    self._stage = "DONE"
                    return 0.0, 0.0, True
            return v, w, False

        if self._stage == "TURN2":
            assert self._turn2 is not None
            v, w, done = self._turn2.step(state, ctx)
            if done:
                self._stage = "DONE"
                return 0.0, 0.0, True
            return v, w, False

        # DONE
        return 0.0, 0.0, True


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
    Background worker:
      - dequeues elements and calls their `on_start` (once) and `step` (periodic).
      - converts (v, ω) to (left, right) track speeds and sends them via provided callback.
      - handles lifecycle, min/max duration, and logging.

    You pass in:
      - speed_command_function(left, right)
      - state_fetch_function() -> FRODO_State
    """
    speed_command_function: Callable[[float, float], None]
    state_fetch_function: Callable[[], "FRODO_State"]
    movement_queue: queue.Queue
    status: NavigatorStatus = NavigatorStatus.IDLE

    control_ts: float = _NavConfig.CONTROL_TS
    config = _NavConfig

    active_element: NavigationElement | None = None
    _exit: bool = False

    events: Navigator_Events
    callbacks: Navigator_Callbacks
    _internal_events: NavigatorInternal_Events

    def __init__(self, speed_command_function: Callable[[float, float], None],
                 state_fetch_function: Callable[[], "FRODO_State"]):

        self.speed_command_function = speed_command_function
        self.state_fetch_function = state_fetch_function
        self.movement_queue = queue.Queue()
        self.logger = Logger("NAVIGATOR", "DEBUG")
        self.callbacks = Navigator_Callbacks()
        self.events = Navigator_Events()
        self._internal_events = NavigatorInternal_Events()

        self._thread = threading.Thread(target=self._task, daemon=True)

    # === PUBLIC API ===================================================================================================
    def start(self):
        self._thread.start()
        self.logger.info("Navigator started")

    def stop(self):
        self._exit = True
        if self._thread.is_alive():
            self._thread.join()
        self.logger.info("Navigator stopped")

    def startNavigation(self):
        if self.status in (NavigatorStatus.IDLE, NavigatorStatus.PAUSED, NavigatorStatus.STOPPED):
            self.status = NavigatorStatus.RUNNING
            self.events.navigation_started.set()
            self.callbacks.navigation_started.call()
            self.logger.info("Navigation started")

    def stopNavigation(self):
        self.status = NavigatorStatus.STOPPED
        if self.active_element:
            self.active_element.stop_flag = True
        self.speed_command_function(0.0, 0.0)
        self.events.navigation_finished.set()
        self.callbacks.navigation_finished.call()
        self.logger.info("Navigation stopped")

    def pauseNavigation(self):
        if self.status == NavigatorStatus.RUNNING:
            self.status = NavigatorStatus.PAUSED
            self.speed_command_function(0.0, 0.0)
            self.events.navigation_paused.set()
            self.callbacks.navigation_paused.call()
            self.logger.info("Navigation paused")

    def resumeNavigation(self):
        if self.status == NavigatorStatus.PAUSED:
            self.status = NavigatorStatus.RUNNING
            self.events.navigation_resumed.set()
            self.callbacks.navigation_resumed.call()
            self.logger.info("Navigation resumed")

    def runElement(self, element: NavigationElement):
        self.active_element = element
        element.active = True
        element.finished = False
        element.error = False
        element.stop_flag = False
        element._t0 = time.monotonic()
        if element._exp_t0 is None:
            element._exp_t0 = element._t0

        # Default durations
        if element.min_duration is None:
            element.min_duration = self.config.DEFAULT_MIN_DURATION
        if element.max_duration is None:
            element.max_duration = self.config.DEFAULT_MAX_DURATION

        st = self.state_fetch_function()
        ctx = self._make_ctx(element)
        # Per-primitive init
        try:
            element.on_start(st, ctx)
        except Exception as e:
            self.logger.error(f"Element on_start failed: {e}")
            element.error = True

        # Notifications
        self.events.element_started.set(data=element)
        element.events.started.set()
        self.callbacks.element_started.call(element=element)
        element.callbacks.started.call()
        self.logger.debug(f"Element started: {element}")

    def abortElement(self):
        if self.active_element:
            self.active_element.stop_flag = True
            self.active_element.active = False
            self.active_element = None
            self.speed_command_function(0.0, 0.0)
            self.logger.warning("Active element aborted")

    def clearQueue(self):
        cleared = 0
        while True:
            try:
                _ = self.movement_queue.get_nowait()
                cleared += 1
            except queue.Empty:
                break
        if cleared:
            self.logger.info(f"Cleared {cleared} queued elements")

    def addElement(self, element: NavigationElement):
        self.movement_queue.put(element)

    def triggerEvent(self, name: str):
        self._internal_events.event.set(data=name)

    # === PRIVATE ======================================================================================================
    def _make_ctx(self, element: NavigationElement) -> PrimitiveContext:
        now = time.monotonic()
        return PrimitiveContext(
            config=self.config,
            control_ts=self.control_ts,
            now=now,
            t0=element._t0 or now,
            exp_t0=element._exp_t0 or now,
            internal_event=self._internal_events.event
        )

    def _task(self):
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
                self.speed_command_function(0.0, 0.0)
                self.events.navigation_error.set(data=str(e))
                self.callbacks.navigation_error.call(error=e)

    def _finish_active(self, ok: bool = True):
        if not self.active_element:
            return
        el = self.active_element
        el.active = False
        el.finished = ok
        el.error = not ok
        self.active_element = None

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

        self.speed_command_function(0.0, 0.0)

    def _control_step(self):
        if self.status != NavigatorStatus.RUNNING:
            self.speed_command_function(0.0, 0.0)
            return

        if self.active_element is None:
            try:
                nxt: NavigationElement = self.movement_queue.get_nowait()
            except queue.Empty:
                self.speed_command_function(0.0, 0.0)
                return
            self.runElement(nxt)

        el = self.active_element
        assert el is not None

        if el.stop_flag:
            self._finish_active(ok=False)
            return

        # Timeouts
        t = time.monotonic()
        t0 = el._t0 or t
        elapsed = t - t0
        if el.max_duration is not None and elapsed > el.max_duration:
            self.logger.warning(f"Element timeout (> {el.max_duration:.1f}s)")
            self._finish_active(ok=False)
            return

        # Primitive step
        st = self.state_fetch_function()
        ctx = self._make_ctx(el)
        v_cmd, w_cmd, done = el.step(st, ctx)

        # Enforce min_duration at finish
        if done and elapsed < (el.min_duration or 0.0):
            done = False

        # Convert & saturate
        vl, vr = _v_omega_to_tracks(v_cmd, w_cmd, self.config.TRACK_WIDTH)
        vl, vr = _saturate_tracks(vl, vr, self.config.MAX_TRACK_SPEED)
        self.speed_command_function(vl, vr)

        if done:
            self._finish_active(ok=True)


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
        movement2 = CoordinatedMoveTo(x=1, y=1)
        movement3 = EventWait(event='test3')
        movement4 = CoordinatedMoveTo(x=-1, y=-1, psi_end=0)
        # movement2 = MoveTo(x=1, y=1)
        # movement3 = TimeWait(duration=2)
        # movement4 = TurnToPoint(x=-1, y=-1)
        # movement5 = MoveTo(x=-1, y=-1)
        # movement6 = TurnTo(psi=0)
        # movement7 = TimeWait(reference=TimeRef.EXPERIMENT, duration=1)
        # movement8 = MoveTo(x=10, y=-1)

        self.navigator.addElement(movement1)
        self.navigator.addElement(movement2)
        self.navigator.addElement(movement3)
        self.navigator.addElement(movement4)
        # self.navigator.addElement(movement5)
        # self.navigator.addElement(movement6)
        # self.navigator.addElement(movement7)
        # self.navigator.addElement(movement8)

        self.navigator.start()
        self.navigator.startNavigation()

        delayed_execution(self.navigator.triggerEvent, 15, name='test3')

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
        self.soundsystem = SoundSystem(primary_engine='etts', volume=0)
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
