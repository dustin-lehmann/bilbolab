# frodo_new.py

import dataclasses
import math
import time
from typing import Optional

import numpy as np

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import Event, event_definition
from core.utils.orientation.orientation_2d import calculate_projection, calculate_rotation_angle
from core.utils.states import State
from core.utils.time import setInterval
from extensions.hardware.optitrack.optitrack import RigidBodySample
from robots.frodo.frodo_definitions import TrackedOrigin_Definition, STATIC_DEFINITIONS, \
    ORIGIN_FRODO_DEFINITION, FRODO1_OPTITRACK_SETTINGS, FRODO2_OPTITRACK_SETTINGS, FRODO3_OPTITRACK_SETTINGS, \
    FRODO4_OPTITRACK_SETTINGS


@dataclasses.dataclass
class TrackedOrigin_State:
    x: float
    y: float
    psi: float


class TrackedOrigin:
    id: str
    definition: TrackedOrigin_Definition
    state: TrackedOrigin_State
    tracking_valid: bool = False

    # === INIT =========================================================================================================
    def __init__(self, id: str, definition: TrackedOrigin_Definition):
        self.id = id
        self.definition = definition
        self.state = TrackedOrigin_State(x=0, y=0, psi=0)

    # === METHODS ======================================================================================================
    def update(self, data: RigidBodySample):
        # Check if tracking is valid
        if not data.valid:
            self.tracking_valid = False
            return

        # Raw marker positions (OptiTrack/world frame)
        origin = np.asarray(data.markers[self.definition.origin][0:2], dtype=float)
        x_axis_end = np.asarray(data.markers[self.definition.x_axis_end][0:2], dtype=float)
        y_axis_end = np.asarray(data.markers[self.definition.y_axis_end][0:2], dtype=float)

        # Heading from x-arrow
        x_axis = x_axis_end - origin
        psi = float(calculate_rotation_angle(vector=x_axis))

        # Apply local (intrinsic) offset: [x_offset, y_offset] in the origin's own axes
        # Positive x_offset moves along +x-arrow; positive y_offset along +y-arrow.
        ox = float(self.definition.x_offset)
        oy = float(self.definition.y_offset)

        c = math.cos(psi)
        s = math.sin(psi)
        # Rotation from local -> world
        # R(psi) @ [ox, oy]
        dx = c * ox - s * oy
        dy = s * ox + c * oy

        # Shift the origin position by that rotated offset
        x_adj = origin[0] + dx
        y_adj = origin[1] + dy

        # Update state
        self.state.x = float(x_adj)
        self.state.y = float(y_adj)
        self.state.psi = psi

        self.tracking_valid = True


# ======================================================================================================================
@dataclasses.dataclass
class TrackedFRODO_Definition:
    points: list[int]
    point_x_axis_start: int
    point_y_axis_start: int
    point_y_axis_end: int


@dataclasses.dataclass
class TrackedFRODO_State:
    x: float
    y: float
    v: float
    psi: float
    psi_dot: float


@callback_definition
class TrackedFRODO_Callbacks:
    update: CallbackContainer


@event_definition
class TrackedFRODO_Events:
    update: Event


class TrackedFRODO:
    """
    A more stable TrackedFRODO variant that:
      - primes its internal state on the first valid sample (no cold-start spike),
      - uses two-sample warmup before reporting non-zero velocities,
      - applies adaptive low-pass filtering with time constants,
      - snaps tiny motion to zero via stationary detection and deadbands.
    """

    id: str
    definition: TrackedFRODO_Definition
    state: "TrackedFRODO_State"
    tracking_valid: bool = False

    origin: TrackedOrigin | None = None

    callbacks: TrackedFRODO_Callbacks
    events: TrackedFRODO_Events

    # === INIT =========================================================================================================
    def __init__(self, id: str, definition: TrackedFRODO_Definition, origin: TrackedOrigin = None):
        self.id = id
        self.definition = definition
        self.state = TrackedFRODO_State(x=0, y=0, v=0, psi=0, psi_dot=0)
        self.origin = origin

        self.callbacks = TrackedFRODO_Callbacks()
        self.events = TrackedFRODO_Events()

        # --- INTERNAL FLAGS ---------------------------------------------------------
        self._primed: bool = False  # set after first valid sample initializes pose & buffers
        self._had_two_samples: bool = False  # set after we have at least two samples in window

        # --- VELOCITY ESTIMATION: buffer & params ----------------------------------
        # Buffer of (timestamp, x, y, psi) for short-window derivative estimates.
        self._state_buffer: list[tuple[float, float, float, float]] = []
        # Duration of window used to compute derivatives (seconds).
        self._window_duration: float = 0.08  # slightly longer for stability at high-rate input
        # Smoothing time constants (seconds) -> alpha = 1 - exp(-dt/tau)
        self._tau_v: float = 0.15
        self._tau_psi: float = 0.15
        # Deadbands for tiny motion (units: meters/s and rad/s)
        self._deadband_v: float = 0.01
        self._deadband_psi_dot: float = np.deg2rad(0.5)
        # Stationary detector thresholds over the window (meters and radians)
        self._stationary_disp_thresh: float = 0.004  # 4 mm across the window
        self._stationary_angle_thresh: float = np.deg2rad(0.4)

        # ------------------------------------------------------------------------------------------------------------------
        # setInterval(self._print_state, 1)

    # ==================================================================================================================
    def _print_state(self):
        if self.tracking_valid:
            # Keep your debug printer but make it private to avoid name collision
            print(f"------------ FRODO {self.id} STATE ------------")
            print(f"x: {self.state.x:.2f}")
            print(f"y: {self.state.y:.2f}")
            print(f"v: {self.state.v:.1f}")
            print(f"psi: {np.rad2deg(self.state.psi):.1f}")
            print(f"psi_dot: {self.state.psi_dot:.1f}")

    # ------------------------------------------------------------------------------------------------------------------
    def setOrigin(self, origin: "TrackedOrigin"):
        self.origin = origin

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _wrap_angle(a: float) -> float:
        # Wrap to [-pi, pi]
        return math.atan2(math.sin(a), math.cos(a))

    # ------------------------------------------------------------------------------------------------------------------
    def _prime_from_first_sample(self, pos_xy: np.ndarray, psi: float):
        """
        Initialize internal state and buffer from the first valid sample.
        Sets velocities to zero to avoid a cold-start spike.
        """
        if self.origin is not None:
            ox = self.origin.state.x
            oy = self.origin.state.y
            opsi = self.origin.state.psi

            dx = float(pos_xy[0]) - ox
            dy = float(pos_xy[1]) - oy

            c = math.cos(opsi)
            s = math.sin(opsi)
            x_rel = c * dx + s * dy
            y_rel = -s * dx + c * dy

            self.state.x = x_rel
            self.state.y = y_rel
            self.state.psi = self._wrap_angle(float(psi) - opsi)
        else:
            self.state.x = float(pos_xy[0])
            self.state.y = float(pos_xy[1])
            self.state.psi = float(psi)

        # Zero initial velocities
        self.state.v = 0.0
        self.state.psi_dot = 0.0

        # Seed buffer with the current state/time so the next sample has a sane dt
        now = time.perf_counter()
        self._state_buffer = [(now, self.state.x, self.state.y, self.state.psi)]
        self._primed = True
        self._had_two_samples = False

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, data: "RigidBodySample"):
        # Check if tracking is valid
        if not data.valid:
            self.tracking_valid = False
            # Avoid mixing stale with fresh data
            self._state_buffer.clear()
            self._primed = False
            self._had_two_samples = False
            return

        # Compute pose from markers
        y_axis_point_start = np.asarray(data.markers[self.definition.point_y_axis_start][0:2])
        y_axis_point_end = np.asarray(data.markers[self.definition.point_y_axis_end][0:2])
        x_axis_point_start = np.asarray(data.markers[self.definition.point_x_axis_start][0:2])

        center_point = calculate_projection(y_axis_point_start, y_axis_point_end, x_axis_point_start)
        position = center_point
        x_axis = center_point - x_axis_point_start
        psi = calculate_rotation_angle(vector=x_axis)

        # First valid sample: prime & return with zero velocity (prevents spike)
        if not self._primed:
            self._prime_from_first_sample(position, psi)
            self.tracking_valid = True
            # Notify position/heading immediately (v, psi_dot = 0)
            self.callbacks.update.call(self.state, True)
            self.events.update.set(self.state)
            return

        # Express (x, y, psi) in origin's frame if provided; else global
        if self.origin is not None:
            ox = self.origin.state.x
            oy = self.origin.state.y
            opsi = self.origin.state.psi

            dx = float(position[0]) - ox
            dy = float(position[1]) - oy

            c = math.cos(opsi)
            s = math.sin(opsi)
            x_rel = c * dx + s * dy
            y_rel = -s * dx + c * dy

            self.state.x = x_rel
            self.state.y = y_rel
            self.state.psi = self._wrap_angle(float(psi) - opsi)
        else:
            self.state.x = float(position[0])
            self.state.y = float(position[1])
            self.state.psi = float(psi)

        # --- VELOCITY ESTIMATION ----------------------------------------------------
        self.state.v, self.state.psi_dot = self._calculateVelocities()

        self.tracking_valid = True

        # Callbacks
        self.callbacks.update.call(self.state, self.tracking_valid)
        self.events.update.set(self.state)

    # --- VELOCITY ESTIMATION CORE ----------------------------------------------------
    def _calculateVelocities(self) -> tuple[float, float]:
        """
        Estimate forward velocity v (signed, along robot x-axis) and yaw rate psi_dot
        using a short buffer of (x, y, psi) samples with:
          - two-sample warmup,
          - stationary detection over the window,
          - adaptive exponential smoothing (time-constant based),
          - deadbands to snap tiny velocities to zero.
        """
        now = time.perf_counter()
        # Append current measurement
        self._state_buffer.append((now, self.state.x, self.state.y, self.state.psi))
        # Keep only recent samples inside the window
        window = self._window_duration
        self._state_buffer = [(t, x, y, p) for (t, x, y, p) in self._state_buffer if (now - t) <= window]

        n = len(self._state_buffer)
        # Need at least 2 points to form a derivative
        if n < 2:
            return self.state.v, self.state.psi_dot

        t0, x0, y0, psi0 = self._state_buffer[0]
        t1, x1, y1, psi1 = self._state_buffer[-1]
        dt = t1 - t0
        if dt <= 1e-6:
            return self.state.v, self.state.psi_dot

        # Displacement in world frame
        dx = x1 - x0
        dy = y1 - y0
        disp2 = dx * dx + dy * dy

        # Heading change (wrapped)
        dpsi = psi1 - psi0
        dpsi = math.atan2(math.sin(dpsi), math.cos(dpsi))

        # Stationary detector: if tiny motion over the entire window, snap to zero and
        # keep buffer trimmed to the latest point to avoid slow decay.
        if disp2 <= (self._stationary_disp_thresh ** 2) and abs(dpsi) <= self._stationary_angle_thresh:
            v_out = 0.0
            psi_dot_out = 0.0
            # Keep only the last sample to prevent residual integrated deltas
            self._state_buffer = [(t1, x1, y1, psi1)]
            return v_out, psi_dot_out

        # Average heading over the window to define the robot-forward axis
        avg_heading = math.atan2(
            math.sin(psi0) + math.sin(psi1),
            math.cos(psi0) + math.cos(psi1)
        )

        # Project displacement onto forward axis => signed forward displacement
        disp_fwd = dx * math.cos(avg_heading) + dy * math.sin(avg_heading)
        v_raw = disp_fwd / dt

        psi_dot_raw = dpsi / dt

        # Two-sample warmup: first time we reach n >= 2, report zero once to avoid a jump,
        # then start reporting filtered derivatives on subsequent calls.
        if not self._had_two_samples:
            self._had_two_samples = True
            # Keep last sample only, so the next step uses a short clean dt
            self._state_buffer = [(t1, x1, y1, psi1)]
            return 0.0, 0.0

        # Adaptive exponential smoothing with time constants
        # Compute effective alpha from dt between consecutive emissions.
        # Use the time since the previous buffer head to avoid dependency on external rate.
        # For stability, clamp dt_eff.
        dt_eff = max(1e-3, self._state_buffer[-1][0] - self._state_buffer[-2][0]) if len(
            self._state_buffer) >= 2 else max(1e-3, dt / max(1, (len(self._state_buffer) - 1)))
        a_v = 1.0 - math.exp(-dt_eff / self._tau_v)
        a_psi = 1.0 - math.exp(-dt_eff / self._tau_psi)

        v_filt = a_v * v_raw + (1.0 - a_v) * self.state.v
        psi_dot_filt = a_psi * psi_dot_raw + (1.0 - a_psi) * self.state.psi_dot

        # Deadbands
        if abs(v_filt) < self._deadband_v:
            v_filt = 0.0
        if abs(psi_dot_filt) < self._deadband_psi_dot:
            psi_dot_filt = 0.0

        return float(v_filt), float(psi_dot_filt)


TRACKED_FRODO_DEFINITIONS = {
    'frodo1': TrackedFRODO_Definition(points=[1, 2, 3, 4, 5],
                                      point_x_axis_start=FRODO1_OPTITRACK_SETTINGS.x_start,
                                      point_y_axis_start=FRODO1_OPTITRACK_SETTINGS.y_start,
                                      point_y_axis_end=FRODO1_OPTITRACK_SETTINGS.y_end, ),
    'frodo2': TrackedFRODO_Definition(points=[1, 2, 3, 4, 5],
                                      point_x_axis_start=FRODO2_OPTITRACK_SETTINGS.x_start,
                                      point_y_axis_start=FRODO2_OPTITRACK_SETTINGS.y_start,
                                      point_y_axis_end=FRODO2_OPTITRACK_SETTINGS.y_end, ),
    'frodo3': TrackedFRODO_Definition(points=[1, 2, 3, 4, 5],
                                      point_x_axis_start=FRODO3_OPTITRACK_SETTINGS.x_start,
                                      point_y_axis_start=FRODO3_OPTITRACK_SETTINGS.y_start,
                                      point_y_axis_end=FRODO3_OPTITRACK_SETTINGS.y_end, ),
    'frodo4': TrackedFRODO_Definition(points=[1, 2, 3, 4, 5],
                                      point_x_axis_start=FRODO4_OPTITRACK_SETTINGS.x_start,
                                      point_y_axis_start=FRODO4_OPTITRACK_SETTINGS.y_start,
                                      point_y_axis_end=FRODO4_OPTITRACK_SETTINGS.y_end, )
}


# ======================================================================================================================
@dataclasses.dataclass
class TrackedStatic_Definition:
    points: list[int]
    origin: int
    x_axis_end: int
    y_axis_end: int


@dataclasses.dataclass
class TrackedStatic_State(State):
    x: float
    y: float
    psi: float


@callback_definition
class TrackedStatic_Callbacks:
    update: CallbackContainer


@event_definition
class TrackedStatic_Events:
    update: Event


class TrackedStatic:
    id: str
    definition: TrackedStatic_Definition
    state: TrackedStatic_State
    tracking_valid: bool = False

    origin: TrackedOrigin | None = None

    callbacks: TrackedStatic_Callbacks
    events: TrackedStatic_Events

    def __init__(self, id: str, definition: TrackedStatic_Definition, origin: TrackedOrigin = None):
        self.id = id
        self.definition = definition
        self.state = TrackedStatic_State(x=0, y=0, psi=0)
        self.origin = origin

        self.callbacks = TrackedStatic_Callbacks()
        self.events = TrackedStatic_Events()

    def setOrigin(self, origin: TrackedOrigin):
        self.origin = origin

    @staticmethod
    def _wrap_angle(a: float) -> float:
        # Wrap to [-pi, pi]
        return math.atan2(math.sin(a), math.cos(a))

    def update(self, data: RigidBodySample):
        # Validate tracking
        if not data.valid:
            self.tracking_valid = False
            return

        # Read markers for this static object (world/OptiTrack frame)
        origin_pt = np.asarray(data.markers[self.definition.origin][0:2], dtype=float)
        x_axis_end = np.asarray(data.markers[self.definition.x_axis_end][0:2], dtype=float)
        # y_axis_end is available in the definition for completeness/consistency
        # (not strictly required to compute psi if x-axis is reliable)
        # y_axis_end = np.asarray(data.markers[self.definition.y_axis_end][0:2], dtype=float)

        # Heading from x-axis
        x_axis_vec = x_axis_end - origin_pt
        psi_world = float(calculate_rotation_angle(vector=x_axis_vec))

        # Position at the tracked origin point
        xw = float(origin_pt[0])
        yw = float(origin_pt[1])

        if self.origin is not None and self.origin.tracking_valid:
            # Express pose in provided origin's coordinate frame
            ox = self.origin.state.x
            oy = self.origin.state.y
            opsi = self.origin.state.psi

            dx = xw - ox
            dy = yw - oy

            c = math.cos(opsi)
            s = math.sin(opsi)
            # rotate by -opsi (R^T)
            x_rel = c * dx + s * dy
            y_rel = -s * dx + c * dy
            psi_rel = self._wrap_angle(psi_world - opsi)

            self.state.x = float(x_rel)
            self.state.y = float(y_rel)
            self.state.psi = float(psi_rel)
        else:
            # Fall back to world/OptiTrack frame
            self.state.x = xw
            self.state.y = yw
            self.state.psi = psi_world

        self.tracking_valid = True

        if self.tracking_valid:
            self.callbacks.update.call(self.state, self.tracking_valid)
            self.events.update.set(self.state)

ORIGIN_FRODO = TrackedOrigin(id='origin_frodo',
                             definition=ORIGIN_FRODO_DEFINITION)

ORIGINS = {
    'origin_frodo': ORIGIN_FRODO,
}

STATIC1_TRACKED_OBJECT = TrackedStatic(id='static1',
                                       definition=TrackedStatic_Definition(points=[1, 2, 3, 4, 5],
                                                                           origin=STATIC_DEFINITIONS[
                                                                               'static1'].optitrack.origin,
                                                                           x_axis_end=STATIC_DEFINITIONS[
                                                                               'static1'].optitrack.x_end,
                                                                           y_axis_end=STATIC_DEFINITIONS[
                                                                               'static1'].optitrack.y_end,
                                                                           ))

TRACKED_STATICS = {
    'static1': STATIC1_TRACKED_OBJECT,
}
