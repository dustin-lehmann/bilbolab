"""
LimboBar DILC Experiment Module.

Extends the standard DILC experiment with limbo bar collision detection.
A limbo bar is created in the testbed manager at experiment start and checked
after each trajectory execution.  The collision result (hit / not hit) is
recorded in the trial data and sent to the host via WiFi events.

Key differences from the base DILC experiment:
  - Settings include a ``LimboBarGeometry`` describing the bar.
  - A limbo bar is registered in the testbed manager on ``initialize()``.
  - After each trajectory, ``bar.hit`` is read and stored in the trial data.
  - The bar is reset only *after* the robot returns to the initial conditions
    (so driving back through the bar doesn't create a false negative).
  - On experiment finish / error / stop the bar is removed from the testbed.
"""
import dataclasses

import numpy as np

from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment import BILBO_ExperimentHandler
from robot.experiment.trial_experiments.dilc import (
    DILC_Experiment,
    DILC_Experiment_Settings,
    DILC_Trial_Data,
    DILC_Trial_Meta,
    DILC_Requirements,
    DILC_Results,
    DILC_Results_Meta,
    DILC_InitialConditions,
    DILC_Experiment_Meta_Settings,
    DILC_U0_Params,
    DILC_WifiEvents,
)
from robot.interfaces.bilbo_interfaces import BILBO_Interfaces
from robot.config import BILBO_Config
from robot.control.bilbo_control_definitions import BILBO_ControlConfig
from robot.testbed.obstacles import LimboBarGeometry
from core.utils.control_lib.lib_control.il.q_filter import FIR_Design_Params


# === Data Structures ==============================================================================================

@dataclasses.dataclass
class TargetZone:
    """Polygon defining the zone the robot must reach to count as 'passed'.

    Each point is an [x, y] coordinate pair. At least 3 points are required
    to form a valid polygon.
    """
    points: list[list[float]]


@dataclasses.dataclass
class LimboBar_DILC_Experiment_Settings:
    """Configuration for a LimboBar DILC experiment.

    Same as DILC_Experiment_Settings with the addition of ``limbo_bar``
    which defines the geometry of the bar to check against, and an optional
    ``target_zone`` polygon the robot must reach for a trial to count as
    'passed'.
    """
    id: str
    description: str
    J: int
    reference: np.ndarray
    Ts: float
    initial_conditions: DILC_InitialConditions
    input_lowpass: FIR_Design_Params
    model_lowpass: FIR_Design_Params
    limbo_bar: LimboBarGeometry
    initial_conditions_u0: DILC_InitialConditions | None = None
    ilc_gain: float = 1.5
    iml_gain: float = 1.5
    meta: DILC_Experiment_Meta_Settings = dataclasses.field(default_factory=DILC_Experiment_Meta_Settings)
    requirements: DILC_Requirements = dataclasses.field(default_factory=DILC_Requirements)
    u0_params: DILC_U0_Params = dataclasses.field(default_factory=DILC_U0_Params)
    u0: np.ndarray | None = None
    m0: np.ndarray | None = None
    target_zone: TargetZone | None = None


@dataclasses.dataclass(frozen=True)
class LimboBar_DILC_Trial_Data:
    """Recorded data for a single completed LimboBar DILC trial.

    Same as DILC_Trial_Data with the addition of ``limbo_bar_hit`` and
    ``limbo_bar_passed``.

    ``limbo_bar_passed`` is True if the robot did not hit the bar AND ended
    inside the target zone. It is None if no target zone was configured.
    """
    index: int
    t: np.ndarray
    u: np.ndarray
    y: np.ndarray
    m: np.ndarray
    e_ilc: np.ndarray
    e_iml: np.ndarray
    e_norm_ilc: float
    e_norm_iml: float
    u_p1: np.ndarray
    m_p1: np.ndarray
    L_ilc: np.ndarray
    L_iml: np.ndarray
    limbo_bar_hit: bool
    limbo_bar_passed: bool | None = None
    meta: DILC_Trial_Meta | None = None

    samples: list[dict] | None = None


@dataclasses.dataclass
class LimboBar_DILC_Results_Meta:
    robot_id: str
    date: str
    robot_config: BILBO_Config
    control_config: BILBO_ControlConfig
    settings: LimboBar_DILC_Experiment_Settings
    logs: list[dict] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class LimboBar_DILC_Results:
    meta: LimboBar_DILC_Results_Meta
    state: str
    trials: list[LimboBar_DILC_Trial_Data]


# === LimboBar DILC Experiment ====================================================================================

class LimboBar_DILC_Experiment(DILC_Experiment):
    """DILC experiment extended with limbo bar collision detection.

    Inherits the full DILC experiment flow (trial loop, ILC/IML updates,
    user interaction, prepare_trial, interruptible sleeps, stop handling)
    and adds limbo bar collision detection via the base class hook system.

    Overridden hooks
    ----------------
    _on_initialize()
        Registers a virtual limbo bar in the testbed manager using the
        geometry from ``settings.limbo_bar``, and validates the optional
        ``settings.target_zone`` polygon (must have ≥3 numeric [x,y] points).

    _on_cleanup()
        Removes the limbo bar from the testbed manager. Called on every
        exit path (success, error, abort, init failure).

    _on_trial_prepared()
        Resets the limbo bar's ``hit`` flag after the robot has navigated
        back to the initial conditions. This prevents the return drive
        from counting as a collision.

    _on_after_trajectory(trajectory_data) → dict
        Reads ``bar.hit`` from the testbed and checks whether the robot
        ended inside the target zone (if configured). Returns
        ``{'limbo_bar_hit': bool, 'limbo_bar_passed': bool | None}``.

    _build_trial_data(...)
        Returns a ``LimboBar_DILC_Trial_Data`` instead of ``DILC_Trial_Data``,
        adding the ``limbo_bar_hit`` and ``limbo_bar_passed`` fields from
        the extra data dict returned by ``_on_after_trajectory()``.

    Other overrides
    ---------------
    _build_results()
        Returns ``LimboBar_DILC_Results`` with ``LimboBar_DILC_Results_Meta``.

    _save_results_to_file()
        Saves with filename prefix ``limbobar_dilc_`` instead of ``dilc_``.

    Settings
    --------
    Uses ``LimboBar_DILC_Experiment_Settings`` which extends the base DILC
    settings with:
      - ``limbo_bar: LimboBarGeometry`` — bar position, height, and length
      - ``target_zone: TargetZone | None`` — optional polygon the robot must
        reach for a trial to count as "passed" (requires no bar hit)
    """

    def __init__(self, common: BILBO_Common,
                 estimation: BILBO_Estimation,
                 control: BILBO_Control,
                 communication: BILBO_Communication,
                 interfaces: BILBO_Interfaces,
                 experiment_handler: BILBO_ExperimentHandler,
                 settings: LimboBar_DILC_Experiment_Settings):
        super().__init__(common, estimation, control, communication,
                         interfaces, experiment_handler, settings)
        self._limbo_bar_id: str | None = None
        self.logger.name = f"LimboBar DILC {settings.id}"

        # Override WiFi event container so the host-side LimboBar DILC proxy
        # receives events under 'limbobar_dilc_experiment' instead of 'dilc_experiment'
        self.wifi_events = DILC_WifiEvents(
            wifi=communication.wifi.wifi,
            id='limbobar_dilc_experiment',
        )

        self.logger.warning(f"Experiment initialized with settings: {self.settings}")


    # === Hook overrides ===========================================================================================

    def _on_initialize(self):
        self._register_limbo_bar()
        self._validate_target_zone()

    def _on_cleanup(self):
        self._cleanup_limbo_bar()

    def _on_trial_prepared(self):
        self._reset_limbo_bar()

    def _on_after_trajectory(self, trajectory_data) -> dict:
        limbo_bar_hit = self._get_limbo_bar_hit()
        limbo_bar_passed = self._check_target_zone_passed(limbo_bar_hit)
        self.logger.info(f"Limbo bar hit: {limbo_bar_hit}")
        if limbo_bar_passed is not None:
            self.logger.info(f"Limbo bar passed: {limbo_bar_passed}")
        # Reset immediately so the return journey can trigger a fresh hit
        # (for visual feedback on the testbed display / video).
        self._reset_limbo_bar()
        return {
            'limbo_bar_hit': limbo_bar_hit,
            'limbo_bar_passed': limbo_bar_passed,
        }

    def _build_trial_data(self, *, trial_meta, theta_trajectory, tracking_error,
                          error_ilc, error_iml, e_norm_ilc, e_norm_iml,
                          up1, mp1, L_ilc, L_iml, trial_samples,
                          extra_trial_data: dict) -> LimboBar_DILC_Trial_Data:
        return LimboBar_DILC_Trial_Data(
            index=self.j,
            t=self.t_vector,
            u=self._u.copy(),
            y=theta_trajectory.copy(),
            m=self._m.copy(),
            e_ilc=error_ilc,
            e_iml=error_iml,
            e_norm_ilc=e_norm_ilc,
            e_norm_iml=e_norm_iml,
            u_p1=up1,
            m_p1=mp1,
            L_ilc=L_ilc,
            L_iml=L_iml,
            limbo_bar_hit=extra_trial_data.get('limbo_bar_hit', False),
            limbo_bar_passed=extra_trial_data.get('limbo_bar_passed'),
            meta=trial_meta,
            samples=trial_samples,
        )

    def _extra_experiment_finished_wifi_data(self) -> dict:
        return {
            'limbo_bar_hits': [t.limbo_bar_hit for t in self.trials],
            'limbo_bar_passes': [t.limbo_bar_passed for t in self.trials],
        }

    def _build_results(self):
        from datetime import datetime
        meta = LimboBar_DILC_Results_Meta(
            robot_id=self.common.id,
            date=datetime.now().isoformat(),
            robot_config=self.common.config,
            control_config=self.control.get_control_config(),
            settings=self.settings,
            logs=self._logs,
        )
        return LimboBar_DILC_Results(
            meta=meta,
            state=self.state,
            trials=self.trials,
        )

    def _save_results_to_file(self, results) -> str | None:
        from datetime import datetime
        from core.utils.json_utils import writeJSON_mp
        import os

        experiments_dir = os.path.expanduser("~/robot/experiments")
        os.makedirs(experiments_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"limbobar_dilc_{self.settings.id}_{timestamp}.json"
        filepath = os.path.join(experiments_dir, filename)

        self.logger.info(f"Saving LimboBar DILC results to {filepath} ...")
        if writeJSON_mp(filepath, results, convert_dataclass=True):
            self.logger.info(f"Saved LimboBar DILC results to {filepath}")
            return filepath
        else:
            self.logger.error(f"Failed to save LimboBar DILC results to {filepath}")
            return None

    # === Limbo bar methods ========================================================================================

    def _register_limbo_bar(self):
        """Add the experiment's limbo bar to the testbed manager."""
        testbed = self.experiment_handler.testbed
        geometry = self.settings.limbo_bar
        bar_id = testbed.add_limbo_bar({
            'id': f'dilc_{self.settings.id}',
            'start_x': geometry.start_x,
            'end_x': geometry.end_x,
            'start_y': geometry.start_y,
            'end_y': geometry.end_y,
            'height': geometry.height,
            'length': geometry.length,
        })
        self._limbo_bar_id = bar_id
        self.logger.info(f"Registered limbo bar '{bar_id}' (height={geometry.height})")

    def _cleanup_limbo_bar(self):
        """Remove the experiment's limbo bar from the testbed manager."""
        if self._limbo_bar_id is not None:
            self.experiment_handler.testbed.remove_limbo_bar(self._limbo_bar_id)
            self.logger.info(f"Removed limbo bar '{self._limbo_bar_id}'")
            self._limbo_bar_id = None

    def _reset_limbo_bar(self):
        """Reset the hit flag on the experiment's limbo bar."""
        if self._limbo_bar_id is not None:
            testbed = self.experiment_handler.testbed
            bar = next((b for b in testbed.limbo_bars if b.id == self._limbo_bar_id), None)
            if bar is not None:
                bar.reset()
                self.logger.debug(f"Reset limbo bar '{self._limbo_bar_id}'")

    def _get_limbo_bar_hit(self) -> bool:
        """Read the hit state of the experiment's limbo bar."""
        if self._limbo_bar_id is not None:
            testbed = self.experiment_handler.testbed
            bar = next((b for b in testbed.limbo_bars if b.id == self._limbo_bar_id), None)
            if bar is not None:
                return bar.hit
        return False

    def _validate_target_zone(self):
        """Validate target zone configuration at experiment init."""
        tz = self.settings.target_zone
        if tz is None:
            return

        if not isinstance(tz.points, list):
            raise ValueError(f"target_zone.points must be a list, got {type(tz.points).__name__}")

        if len(tz.points) < 3:
            raise ValueError(
                f"target_zone must have at least 3 points to form a polygon, got {len(tz.points)}"
            )

        for i, pt in enumerate(tz.points):
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                raise ValueError(
                    f"target_zone point {i} must be an [x, y] pair, got {pt!r}"
                )
            if not all(isinstance(v, (int, float)) for v in pt):
                raise ValueError(
                    f"target_zone point {i} coordinates must be numbers, got {pt!r}"
                )

        self.logger.info(f"Target zone validated: {len(tz.points)} points")

    def _check_target_zone_passed(self, limbo_bar_hit: bool) -> bool | None:
        """Check if the robot passed the limbo bar by reaching the target zone.

        Returns:
            True  -- robot did not hit the bar and is inside the target zone
            False -- robot hit the bar or is not inside the target zone
            None  -- no target zone configured
        """
        tz = self.settings.target_zone
        if tz is None:
            return None

        if limbo_bar_hit:
            return False

        x = self.estimation.state.x
        y = self.estimation.state.y
        return self._point_in_polygon(x, y, tz.points)

    @staticmethod
    def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
        """Ray-casting point-in-polygon test."""
        n = len(polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside
