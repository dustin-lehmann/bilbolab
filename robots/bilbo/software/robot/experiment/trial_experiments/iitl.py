"""
IITL (Iterative Input Transfer Learning) Experiment Module.

Runs Iterative Input Transfer Learning on the BILBO robot, mirroring the
hardware-in-the-loop trial structure of :mod:`dilc`. Where DILC learns an input
to track a reference *output* on a single robot, IITL learns an *input transfer
vector* ``t`` that maps a known *source* input to the input this (target) robot
must apply to reproduce the source's behaviour.

Per trial ``j`` (cyclic over the learning set L of source input/output pairs):

    1. Select source pair (u_source, y_source) = L[j mod |L|]
    2. Transfer the input:           u_target = M(t_j) * u_source
    3. Apply u_target to the robot and measure the output y_target
    4. (model-free only) inner IML loop -- refine the target-model estimate:
           e_f   = y_target - M(u_target) * f_j
           f_{j+1} = Q_m * (f_j + K_j * e_f)            (K_j norm-optimal IML)
    5. Outer transfer loop:
           e_j   = y_source - y_target                   (learning error)
           L_j   from the model estimate (scalar or accumulated-information RLS)
           t_{j+1} = Q * (t_j + L_j * e_j)

This single class is configurable across the four schemes of the simulation
study via :class:`IITL_Experiment_Settings`:

    * ``model_free``  -- estimate the target model on the fly (True), or use a
      supplied known model ``f_target`` (False).
    * ``outer_design`` -- per-trial scalar weight, or one of the cumulative
      regressor-Gramian ("RLS") designs. The headline method of the
      experimental chapter is ``model_free=True`` with ``outer_design=RLS`` and
      an inner Q-filter ``model_lowpass`` (model-free RLS+Q IITL).

The Q-filters reuse DILC's zero-phase FIR design (``_build_q_filter``): the
inner ``model_lowpass`` filters the IML model update (the "Q" of RLS+Q), the
outer ``transfer_lowpass`` optionally filters the transfer-vector update.

If a ``reference_transfer_vector`` is supplied (e.g. the model-based ``t_ref``
identified from a DILC ``.bmvec``), the transfer-vector error
``||t_ref - t_j||`` is logged per trial. Likewise ``f_target`` (in model-free
mode, for logging only) yields the per-trial model-estimation error.

Safety: the transferred input ``u_target`` can grow when ``t_j`` is still poorly
estimated. Before every injection the peak ``|u_target|`` is checked against
``max_input_abs`` (auto-derived from the learning-set peak if not set) and the
trial is aborted if it would exceed the bound -- on top of the inherited
DILC-style manual per-trial preview/accept.
"""
import dataclasses
import enum
import os
import threading
from datetime import datetime

import numpy as np

from core.communication.wifi.bilbolab_wifi_interface import (
    wifi_event_definition, WifiEventContainer, WifiEvent, WifiEventFlag,
)
from core.utils.control_lib.lib_control.learning.q_filter import FIR_Design_Params
from core.utils.control_lib.lib_control.learning.lifted import vector_to_lifted_matrix
from core.utils.control_lib.lib_control.learning.transfer.iitl import (
    RLSDesign,
    iitl_get_scalar_learning_matrix,
    iitl_get_rls_learning_matrix,
    iitl_get_exploration_biased_learning_matrix,
    iitl_get_hybrid_rls_exploration_learning_matrix,
    iitl_update,
    iitl_update_rls_gramian,
    iitl_get_learning_gain,
)
from core.utils.control_lib.lib_control.learning.iml.iml import (
    iml_get_norm_optimal_matrices,
    iml_get_learning_gain,
    iml_update,
)
from core.utils.data import generate_time_vector_by_length
from core.utils.events import wait_for_events, OR, TIMEOUT
from core.utils.logging_utils import Logger
from core.utils.control_lib.lib_control.learning.transfer.iitl_utils import TrajectoryPair

from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.config import BILBO_Config
from robot.control.bilbo_control import BILBO_Control
from robot.control.bilbo_control_definitions import BILBO_ControlConfig
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment import BILBO_InputTrajectory, BILBO_ExperimentHandler
from robot.interfaces.bilbo_interfaces import BILBO_Interfaces
from robot.core import get_logging_provider
from robot.lowlevel.stm32_general import MAX_STEPS_TRAJECTORY
from robot.utilities.buzzer import beep

# Generic hardware/state-machine plumbing is shared with DILC. The IITL
# experiment subclasses DILC_Experiment and inherits prepare_trial(), the
# lifecycle hooks, the Q-filter builder, log capture, stop(), set_auto_*() and
# the common WiFi-data property; it overrides only the IITL-specific parts.
from robot.experiment.trial_experiments.dilc import (
    DILC_Experiment,
    DILC_InitialConditions as IITL_InitialConditions,
    DILC_Experiment_Meta_Settings as IITL_Experiment_Meta_Settings,
    DILC_Requirements as IITL_Requirements,
    DILC_Trial_Meta as IITL_Trial_Meta,
    DILC_Experiment_State as IITL_Experiment_State,
    DILC_Phase as IITL_Phase,
    DILC_Experiment_Events as IITL_Experiment_Events,
    DILC_Experiment_Callbacks as IITL_Experiment_Callbacks,
    TrialResult,
)


# === Data Structures ==============================================================================================

class IITL_OuterDesign(enum.StrEnum):
    """Outer (transfer-vector) learning-matrix design.

    SCALAR uses the per-trial scalar-weight matrix (Sec.~iitl_estimation); the
    remaining designs maintain the cumulative regressor Gramian and map onto
    :class:`RLSDesign`. The headline experimental method uses RLS.
    """
    SCALAR = "scalar"
    RLS = "rls"
    EXPLORATION_BIASED = "exploration_biased"
    HYBRID = "hybrid_rls_exploration"

    def to_rls_design(self) -> RLSDesign:
        """Map a (non-scalar) outer design onto its RLSDesign member."""
        return {
            IITL_OuterDesign.RLS: RLSDesign.PLAIN,
            IITL_OuterDesign.EXPLORATION_BIASED: RLSDesign.EXPLORATION_BIASED,
            IITL_OuterDesign.HYBRID: RLSDesign.HYBRID,
        }[self]


@dataclasses.dataclass
class IITL_Experiment_Settings:
    """Configuration for an IITL experiment.

    Attributes:
        id: Unique experiment identifier.
        description: Human-readable description.
        J: Number of trials (transfer-learning iterations).
        learning_set: Source input/output pairs (the learning set L). Each
            pair's input and output must have equal length N. Selected cyclically.
        Ts: Sampling period in seconds (must match the control loop, e.g. 0.01).
        initial_conditions: Starting pose for each trial.
        model_free: Estimate the target model on the fly (True) or use the
            supplied known model ``f_target`` (False).
        outer_design: Outer transfer learning-matrix design (see IITL_OuterDesign).
        s: Outer (transfer) regularisation, s > 0. Mandatory for the RLS designs;
            used for SCALAR unless ``adaptive_s`` is set.
        adaptive_s: SCALAR only -- recompute s per trial from the current
            regressor (condition-number heuristic with cap ``kappa``).
        s_m: Inner (model) regularisation, model-free only. Ignored when
            ``adaptive_s_m`` is set.
        adaptive_s_m: Recompute the inner regularisation per trial (model-free).
        kappa: Condition-number cap for the adaptive regularisers.
        eps, delta: Knee/floor parameters of the exploration-shaped designs.
        model_lowpass: FIR low-pass for the inner IML model update (Q_m). None
            leaves the norm-optimal IML filter (identity at r=0) in place.
        transfer_lowpass: FIR low-pass for the outer transfer update (Q). None
            applies no outer filter.
        t_1: Initial transfer vector. Defaults to the unity transfer [1,0,...,0]
            so trial 0 applies the source input unchanged (a safe start).
        f_0: Initial target-model estimate (model-free). Defaults to zeros; a
            coarse plant-class prior is recommended to warm up the inner loop.
        f_target: Known target Markov vector. REQUIRED when model_free=False
            (it is the model used). In model-free mode it is optional and used
            only to log the per-trial model-estimation error.
        reference_transfer_vector: Optional reference t_ref (e.g. from a DILC
            .bmvec identification). When given, ||t_ref - t_j|| is logged per trial.
        max_input_abs: Hard cap on peak |u_target|. None -> auto-derived as
            ``input_safety_factor * max|u_source|`` over the learning set.
        input_safety_factor: Multiplier for the auto-derived cap.
    """
    id: str
    description: str
    J: int
    learning_set: list[TrajectoryPair]
    Ts: float
    initial_conditions: IITL_InitialConditions

    # --- method selection -----------------------------------------------------
    model_free: bool = True
    outer_design: IITL_OuterDesign = IITL_OuterDesign.RLS

    # --- regularisation -------------------------------------------------------
    s: float = 1e-2
    adaptive_s: bool = False
    s_m: float | None = None
    adaptive_s_m: bool = True
    kappa: float = 100.0
    eps: float | None = None
    delta: float = 1e-4

    # --- Q-filters (reuse DILC's FIR design) ----------------------------------
    model_lowpass: FIR_Design_Params | None = None
    transfer_lowpass: FIR_Design_Params | None = None

    # --- initial estimates / references ---------------------------------------
    t_1: np.ndarray | None = None
    f_0: np.ndarray | None = None
    f_target: np.ndarray | None = None
    reference_transfer_vector: np.ndarray | None = None

    # --- safety ---------------------------------------------------------------
    max_input_abs: float | None = None
    input_safety_factor: float = 4.0

    # --- shared flow / requirements (same semantics as DILC) ------------------
    initial_conditions_u0: IITL_InitialConditions | None = None
    meta: IITL_Experiment_Meta_Settings = dataclasses.field(
        default_factory=IITL_Experiment_Meta_Settings)
    requirements: IITL_Requirements = dataclasses.field(
        default_factory=IITL_Requirements)


@dataclasses.dataclass(frozen=True)
class IITL_Trial_Data:
    """Recorded data and computed updates for a single completed IITL trial.

    Mirrors ModelFreeIITL_Trial_Data of the simulation study, plus the robot
    trial metadata/samples and the optional transfer-vector error. Inner
    (model-loop) fields are None / nan in known-model mode.
    """
    index: int
    t: np.ndarray
    # --- outer (transfer) loop ---
    u_source: np.ndarray
    y_source: np.ndarray
    u_target: np.ndarray
    y_target: np.ndarray
    learning_error: np.ndarray
    learning_error_norm: float
    s: float
    learning_matrix: np.ndarray
    q_filter: np.ndarray | None
    transfer_vector: np.ndarray            # t_j (carried into this trial)
    transfer_vector_update: np.ndarray     # t_{j+1}
    transfer_vector_error_norm: float | None  # ||t_ref - t_{j+1}|| if t_ref given
    # --- inner (model-learning) loop (model-free only) ---
    model_vector: np.ndarray | None
    model_vector_update: np.ndarray | None
    model_prediction: np.ndarray | None
    model_output_error: np.ndarray | None
    model_output_error_norm: float | None
    model_learning_matrix: np.ndarray | None
    model_q_filter: np.ndarray | None
    model_estimation_error_norm: float | None  # ||f_target - f_{j}|| if f_target given
    s_m: float | None

    meta: IITL_Trial_Meta | None = None
    samples: list[dict] | None = None


@dataclasses.dataclass
class IITL_Results_Meta:
    """Metadata recorded alongside experiment results for reproducibility."""
    robot_id: str
    date: str
    robot_config: BILBO_Config
    control_config: BILBO_ControlConfig
    settings: IITL_Experiment_Settings
    logs: list[dict] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class IITL_Results:
    """Complete results of an IITL experiment (partial on error/abort)."""
    meta: IITL_Results_Meta
    state: IITL_Experiment_State
    trials: list[IITL_Trial_Data]


# === WiFi Events ==================================================================================================

_IITL_WIFI_EVENT = WifiEvent(data_type=dict, flags=WifiEventFlag('group', str))


@wifi_event_definition
class IITL_WifiEvents(WifiEventContainer):
    """WiFi events sent by the IITL experiment to the host.

    Same lifecycle as DILC, under the ``'iitl_experiment'`` group so the host
    can route IITL telemetry independently.
    """
    experiment_initialized: WifiEvent = _IITL_WIFI_EVENT
    experiment_started: WifiEvent = _IITL_WIFI_EVENT
    experiment_finished: WifiEvent = _IITL_WIFI_EVENT
    experiment_error: WifiEvent = _IITL_WIFI_EVENT

    trajectory_loaded: WifiEvent = _IITL_WIFI_EVENT
    trajectory_started: WifiEvent = _IITL_WIFI_EVENT
    trajectory_error: WifiEvent = _IITL_WIFI_EVENT
    trajectory_finished: WifiEvent = _IITL_WIFI_EVENT

    trial_started: WifiEvent = _IITL_WIFI_EVENT
    trial_prepared: WifiEvent = _IITL_WIFI_EVENT
    trial_reverted: WifiEvent = _IITL_WIFI_EVENT
    trial_finished: WifiEvent = _IITL_WIFI_EVENT
    trial_error: WifiEvent = _IITL_WIFI_EVENT

    meta_settings_changed: WifiEvent = _IITL_WIFI_EVENT


# === IITL Experiment ==============================================================================================

class IITL_Experiment(DILC_Experiment):
    """Iterative Input Transfer Learning experiment on the BILBO robot.

    Subclasses :class:`DILC_Experiment` to inherit the hardware/state-machine
    plumbing (trial preparation, navigation, user-interaction waits, Q-filter
    builder, log capture, abort handling, WiFi-data property). Overrides the
    IITL-specific pieces: initialisation of the transfer/model state, the
    per-trial transfer-and-update logic, and results building/saving.
    """
    settings: IITL_Experiment_Settings
    trials: list[IITL_Trial_Data]

    _WIFI_FLAGS = {'group': 'iitl_experiment'}

    # === INIT =====================================================================================================
    def __init__(self, common: BILBO_Common,
                 estimation: BILBO_Estimation,
                 control: BILBO_Control,
                 communication: BILBO_Communication,
                 interfaces: BILBO_Interfaces,
                 experiment_handler: BILBO_ExperimentHandler,
                 settings: IITL_Experiment_Settings):
        self.common = common
        self.settings = settings
        self.control = control
        self.communication = communication
        self.estimation = estimation
        self.interfaces = interfaces
        self.experiment_handler = experiment_handler

        self.trials = []
        self.phase = IITL_Phase.IDLE

        self._auto_start_trials = settings.meta.auto_start_trials
        self._auto_accept_trials = settings.meta.auto_accept_trials

        self.logger = Logger(f"IITL Experiment {self.settings.id}", "DEBUG")
        self.events = IITL_Experiment_Events()
        self.callbacks = IITL_Experiment_Callbacks()

        self._logs = []
        self._log_capture_enabled = False

        self.wifi_events = IITL_WifiEvents(
            wifi=communication.wifi.wifi,
            id='iitl_experiment',
        )

        # IITL learning state (set in initialize())
        self._t: np.ndarray | None = None   # current transfer vector
        self._f: np.ndarray | None = None    # current model estimate (model-free)
        self._G: np.ndarray | None = None    # cumulative regressor Gramian (RLS)
        self._Q: np.ndarray | None = None     # outer transfer Q-filter
        self._Q_m: np.ndarray | None = None   # inner IML Q-filter
        self._max_input_abs: float | None = None

        self.common.interaction_events.stop.on(self.stop, once=True)

    # === INITIALIZATION ===========================================================================================
    def initialize(self):
        """Validate settings and set up the transfer/model state and Q-filters.

        Emits: ``experiment_initialized``. Raises on invalid settings or unmet
        requirements.
        """
        self._check_requirements()

        ls = self.settings.learning_set
        if not ls:
            raise ValueError("learning_set is empty")
        self.N = len(ls[0].input)

        # STM32 sequencer constraints (same as DILC).
        if self.N % 10 != 0:
            raise ValueError(
                f"Trajectory length N={self.N} is not a multiple of 10 "
                f"(required by the STM32 sequencer).")
        if self.N > MAX_STEPS_TRAJECTORY:
            raise ValueError(
                f"Trajectory length N={self.N} exceeds MAX_STEPS_TRAJECTORY="
                f"{MAX_STEPS_TRAJECTORY}.")

        # Every learning pair must share the horizon N.
        for k, pair in enumerate(ls):
            if len(pair.input) != self.N or len(pair.output) != self.N:
                raise ValueError(
                    f"Learning pair {k} has input/output length "
                    f"({len(pair.input)}, {len(pair.output)}); expected N={self.N}.")

        # Method-consistency checks.
        if not self.settings.model_free and self.settings.f_target is None:
            raise ValueError("f_target is required when model_free=False "
                             "(it is the known model used in the update).")
        if self.settings.outer_design != IITL_OuterDesign.SCALAR:
            if self.settings.s is None:
                raise ValueError("Outer regularisation s is required for the RLS designs.")
            if self.settings.adaptive_s:
                raise ValueError("adaptive_s is only valid for outer_design=SCALAR.")
        if self.settings.model_free and not self.settings.adaptive_s_m \
                and self.settings.s_m is None:
            raise ValueError("s_m is required when model_free and not adaptive_s_m.")

        self.t_vector = generate_time_vector_by_length(num_samples=self.N, dt=self.settings.Ts)

        # --- Initial transfer vector t_1 (unity transfer by default) ---
        if self.settings.t_1 is None:
            self._t = np.zeros(self.N)
            self._t[0] = 1.0
            self.logger.info("No t_1 provided. Starting from the unity transfer "
                             "[1, 0, ...]: trial 0 applies the source input unchanged.")
        else:
            self._t = np.asarray(self.settings.t_1, dtype=float).copy()

        # --- Initial model estimate f_0 ---
        if self.settings.model_free:
            if self.settings.f_0 is None:
                self._f = np.zeros(self.N)
                self.logger.info("No f_0 provided. Starting the inner model loop from zeros.")
            else:
                self._f = np.asarray(self.settings.f_0, dtype=float).copy()
        else:
            self._f = np.asarray(self.settings.f_target, dtype=float).copy()
            self.logger.info("Known-model mode: using the supplied f_target as the model.")

        self._G = np.zeros((self.N, self.N))
        self.j = 0

        # --- Q-filters (reuse DILC's zero-phase FIR builder) ---
        self._Q_m = (self._build_q_filter(self.settings.model_lowpass, "IML model (Q_m)")
                     if self.settings.model_lowpass is not None else None)
        self._Q = (self._build_q_filter(self.settings.transfer_lowpass, "transfer (Q)")
                   if self.settings.transfer_lowpass is not None else None)

        # --- Safety cap on the transferred input ---
        peak_source = max(float(np.max(np.abs(p.input))) for p in ls)
        if self.settings.max_input_abs is not None:
            self._max_input_abs = float(self.settings.max_input_abs)
        else:
            self._max_input_abs = self.settings.input_safety_factor * peak_source
        self.logger.info(f"Transferred-input safety cap: |u_target| <= "
                         f"{self._max_input_abs:.4f} (learning-set peak {peak_source:.4f}).")

        self._finished = False
        self._abort_requested = False
        self.trials = []
        self.phase = IITL_Phase.IDLE

        self._on_initialize()

        self.state = IITL_Experiment_State.INITIALIZED
        self.events.experiment_initialized.set(data={
            'settings': self.settings,
            'N': self.N,
            'duration_s': self.N * self.settings.Ts,
        })
        self.wifi_events.experiment_initialized.send(data={
            **self._wifi_data,
            'N': self.N,
            'duration_s': self.N * self.settings.Ts,
        }, flags=self._WIFI_FLAGS)
        self.logger.info("IITL experiment initialized successfully")

    # === MAIN LOOP ================================================================================================
    def run(self) -> IITL_Results | None:
        """Run the full IITL experiment (initialize, then J trials)."""
        try:
            self.initialize()
        except Exception as e:
            self.logger.error(f"Failed to initialize experiment: {e}")
            self.state = IITL_Experiment_State.ERROR
            self.events.experiment_error.set(data={
                'message': f"Initialization failed: {e}",
                'trial_index': 0, 'completed_trials': 0,
            })
            self.callbacks.experiment_error.call()
            self.wifi_events.experiment_error.send(data={
                **self._wifi_data, 'message': f"Initialization failed: {e}",
            }, flags=self._WIFI_FLAGS)
            self._on_cleanup()
            return None

        self._start_log_capture()
        self.state = IITL_Experiment_State.RUNNING
        self.logger.info("=" * 60)
        self.logger.info(f"Starting IITL experiment '{self.settings.id}'")
        self.logger.info(f"  Trials: {self.settings.J}")
        self.logger.info(f"  Trajectory length: {self.N} samples "
                         f"({self.N * self.settings.Ts:.2f}s)")
        self.logger.info(f"  Learning set: {len(self.settings.learning_set)} pairs")
        self.logger.info(f"  Mode: {'model-free' if self.settings.model_free else 'known-model'}, "
                         f"outer design: {self.settings.outer_design.value}")
        self.logger.info(f"  Q_m (IML): {'on' if self._Q_m is not None else 'off'}, "
                         f"Q (transfer): {'on' if self._Q is not None else 'off'}")
        self.logger.info("=" * 60)

        self.events.experiment_started.set(data={
            'settings': self.settings, 'meta': self.settings.meta,
        })
        self.callbacks.experiment_started.call()
        self.wifi_events.experiment_started.send(data={
            **self._wifi_data,
            'N': self.N,
            'duration_s': self.N * self.settings.Ts,
            'auto_initial_conditions': self.settings.meta.automatic_initial_conditions_reset,
        }, flags=self._WIFI_FLAGS)

        while self.j < self.settings.J:
            if self._abort_requested:
                self.logger.warning("Experiment aborted by external request")
                break

            result = self.run_trial()
            if result == TrialResult.FINISHED:
                continue
            elif result == TrialResult.REVERT:
                self.logger.info(f"Trial {self.j + 1} will be repeated")
                continue
            elif result == TrialResult.ERROR:
                self.phase = IITL_Phase.IDLE
                self.state = IITL_Experiment_State.ERROR
                self._finished = True
                self._stop_log_capture()
                error_msg = f"Experiment stopped: trial {self.j + 1} failed"
                self.logger.error(error_msg)
                self.events.experiment_error.set(data={
                    'message': error_msg, 'trial_index': self.j,
                    'completed_trials': len(self.trials),
                })
                self.callbacks.experiment_error.call()
                results = self._build_results()
                results_filepath = self._save_results_to_file(results)
                self.wifi_events.experiment_error.send(data={
                    **self._wifi_data, 'message': error_msg,
                    'results_filepath': results_filepath,
                }, flags=self._WIFI_FLAGS)
                beep(frequency='low', repeats=3)
                self._on_cleanup()
                return results

        self.phase = IITL_Phase.IDLE
        if self._abort_requested:
            self.state = IITL_Experiment_State.ERROR
            self._finished = True
            self._stop_log_capture()
            self.logger.warning(f"Experiment aborted after {len(self.trials)} of "
                                f"{self.settings.J} trials")
            self.events.experiment_error.set(data={
                'message': 'Experiment aborted by user', 'trial_index': self.j,
                'completed_trials': len(self.trials),
            })
            self.callbacks.experiment_error.call()
            results = self._build_results()
            results_filepath = self._save_results_to_file(results)
            self.wifi_events.experiment_error.send(data={
                **self._wifi_data, 'message': 'Experiment aborted by user',
                'results_filepath': results_filepath,
            }, flags=self._WIFI_FLAGS)
            self._on_cleanup()
            return results

        self.state = IITL_Experiment_State.FINISHED
        self._finished = True
        self._stop_log_capture()
        results = self._build_results()
        results_filepath = self._save_results_to_file(results)

        self.logger.info("=" * 60)
        self.logger.info(f"IITL experiment '{self.settings.id}' completed successfully")
        self.logger.info(f"  Completed trials: {len(self.trials)}/{self.settings.J}")
        if self.trials:
            self.logger.info(f"  Final learning error norm: "
                             f"{self.trials[-1].learning_error_norm:.6f}")
            if self.trials[-1].transfer_vector_error_norm is not None:
                self.logger.info(f"  Final transfer-vector error: "
                                 f"{self.trials[-1].transfer_vector_error_norm:.6f}")
        self.logger.info("=" * 60)

        self.events.experiment_finished.set(data=results)
        self.callbacks.experiment_finished.call()
        self.wifi_events.experiment_finished.send(data={
            **self._wifi_data,
            **self._extra_experiment_finished_wifi_data(),
            'final_learning_error_norm':
                float(self.trials[-1].learning_error_norm) if self.trials else None,
            'learning_error_norms': [float(t.learning_error_norm) for t in self.trials],
            'transfer_vector_error_norms':
                [t.transfer_vector_error_norm for t in self.trials],
            'results_filepath': results_filepath,
        }, flags=self._WIFI_FLAGS)
        beep(frequency='high', repeats=3)

        self._on_cleanup()
        return results

    # === TRIAL ====================================================================================================
    def run_trial(self) -> TrialResult:
        """Execute one IITL trial: transfer, run, measure, update.

        Mirrors DILC.run_trial's prepare/preview/run/accept flow; the
        IITL-specific parts are the transferred input ``u_target = M(t)
        u_source`` (with the safety check), the learning error
        ``y_source - y_target``, and the transfer/model update of
        ``_compute_iitl_update``.
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info(f"Trial {self.j + 1}/{self.settings.J}")
            self.logger.info("=" * 60)

            self.phase = IITL_Phase.PREPARING
            self.events.trial_started.set(data={
                'trial_index': self.j, 'total_trials': self.settings.J,
            })
            self.callbacks.trial_started.call()
            self.wifi_events.trial_started.send(data={**self._wifi_data},
                                                flags=self._WIFI_FLAGS)

            # --- Step 1: Prepare the robot (navigate to initial conditions) ---
            if not self.prepare_trial():
                self.logger.error("Failed to prepare the trial")
                self._emit_trial_error('Preparation failed')
                return TrialResult.ERROR

            self._on_trial_prepared()
            self.phase = IITL_Phase.WAITING_FOR_START

            # --- Step 2: Select the source pair and form the transferred input ---
            L = len(self.settings.learning_set)
            learning_pair = self.settings.learning_set[self.j % L]
            u_source = np.asarray(learning_pair.input, dtype=float)
            y_source = np.asarray(learning_pair.output, dtype=float)
            u_target = vector_to_lifted_matrix(self._t) @ u_source

            # Safety: refuse to inject an over-amplitude transferred input.
            peak = float(np.max(np.abs(u_target)))
            if peak > self._max_input_abs:
                msg = (f"Transferred input peak |u_target|={peak:.4f} exceeds the "
                       f"safety cap {self._max_input_abs:.4f}; aborting trial.")
                self.logger.error(msg)
                self._emit_trial_error(msg)
                return TrialResult.ERROR

            input_trajectory = BILBO_InputTrajectory.from_vector(
                vector=u_target,
                name=f"IITL trial {self.j + 1} (src {self.j % L + 1}/{L})",
                id=self.j + 1,
                delta=self.common.config.model.trajectory_delta,
            )
            self.logger.info(f"Transferred trajectory: {input_trajectory.length} steps, "
                             f"u_target range [{u_target.min():.4f}, {u_target.max():.4f}], "
                             f"peak {peak:.4f}/{self._max_input_abs:.4f}")
            self.events.trajectory_loaded.set(data={
                'trajectory': input_trajectory, 'trial_index': self.j,
            })
            self.wifi_events.trajectory_loaded.send(data={
                **self._wifi_data,
                'trajectory_length': input_trajectory.length,
                'u_min': float(u_target.min()), 'u_max': float(u_target.max()),
            }, flags=self._WIFI_FLAGS)

            # --- Step 3: Wait for user to start the trial (unless auto-start) ---
            if self._auto_start_trials:
                self.logger.info("Auto-starting trial (auto_start_trials=True)")
            else:
                self.logger.info("Waiting for user to start the trial... (Resume / Abort)")
                data, trace = wait_for_events(
                    OR(self.common.interaction_events.resume,
                       self.common.interaction_events.stop),
                    timeout=60,
                )
                if data is TIMEOUT:
                    self.logger.warning("Timed out waiting for user to start (60s)")
                    self._emit_trial_error('Timeout waiting for user to start trial')
                    return TrialResult.ERROR
                if trace.caused_by(self.common.interaction_events.stop):
                    self.logger.warning("User aborted before trajectory start")
                    self._emit_trial_error('User aborted')
                    return TrialResult.ERROR

            # --- Step 4: Execute the trajectory ---
            self.phase = IITL_Phase.RUNNING_TRAJECTORY
            self.logger.info("Starting trajectory execution...")
            self.interfaces.disable_external_input()
            self.control.disable_external_input()
            if self.settings.meta.enable_psi_control:
                self.control.enable_psi_control(True)
            if self.settings.meta.disable_tracker_during_trajectory:
                self.estimation.set_tracker_updates_enabled(False)

            self.events.trajectory_started.set(data={
                'trajectory': input_trajectory, 'trial_index': self.j,
            })
            self.callbacks.trajectory_started.call()
            self.wifi_events.trajectory_started.send(data={**self._wifi_data},
                                                     flags=self._WIFI_FLAGS)

            # Blocking call — the robot executes the full transferred input.
            trajectory_data = self.experiment_handler.run_trajectory(input_trajectory)

            if self.settings.meta.enable_psi_control:
                self.control.enable_psi_control(False)
            if self.settings.meta.disable_tracker_during_trajectory:
                self.estimation.set_tracker_updates_enabled(True)

            trajectory_start_timecode = None
            if trajectory_data is not None:
                tc = self.common.get_timecode_for_tick(trajectory_data.meta.start_tick)
                if tc is not None:
                    trajectory_start_timecode = tc.to_string()
                    self.logger.info(f"Trajectory start timecode: {trajectory_start_timecode}")

            extra_trial_data = self._on_after_trajectory(trajectory_data)
            self.phase = IITL_Phase.WAITING_FOR_ACCEPTANCE

            if trajectory_data is None:
                self.logger.error("Trajectory execution failed (run_trajectory returned None)")
                self.events.trajectory_error.set(data={
                    'trajectory': input_trajectory, 'trial_index': self.j,
                })
                self.wifi_events.trajectory_error.send(data={
                    **self._wifi_data, 'message': 'Trajectory execution failed',
                }, flags=self._WIFI_FLAGS)
                self._emit_trial_error('Trajectory execution failed')
                return TrialResult.ERROR

            # --- Step 4b: Collect full samples for offline analysis ---
            trial_samples = self._collect_trial_samples(trajectory_data)

            # --- Step 5: Extract the measured output and the learning error ---
            y_target = np.asarray([
                state.theta for state in trajectory_data.data.state_trajectory.states
            ])
            n_out = len(y_target)
            if n_out != self.N:
                self.logger.warning(
                    f"Output length ({n_out}) differs from N={self.N} "
                    f"(delta {n_out - self.N}).")
                if n_out > self.N:
                    y_target = y_target[:self.N]
                else:
                    pad_value = y_target[-1] if n_out > 0 else 0.0
                    y_target = np.pad(y_target, (0, self.N - n_out),
                                      mode='constant', constant_values=pad_value)

            learning_error = y_source - y_target
            error_norm = float(np.linalg.norm(learning_error))
            max_abs_error = float(np.max(np.abs(learning_error)))
            self.logger.info(f"Trajectory finished. Learning error norm "
                             f"||y_source - y_target||: {error_norm:.6f} "
                             f"(max abs {max_abs_error:.6f})")

            self.events.trajectory_finished.set(data={
                'trajectory': input_trajectory, 'trial_index': self.j,
                'y_target': y_target, 'learning_error': learning_error,
                'error_norm': error_norm,
            })
            self.callbacks.trajectory_finished.call()
            self.wifi_events.trajectory_finished.send(data={
                **self._wifi_data, **extra_trial_data,
                'error_norm': float(error_norm), 'max_abs_error': max_abs_error,
                'y_source': y_source, 'y_target': y_target,
                'learning_error': learning_error,
                'u_source': u_source, 'u_target': u_target, 't': self.t_vector,
            }, flags=self._WIFI_FLAGS)

            # --- Step 6: Wait for user acceptance (unless auto-accept) ---
            if self._auto_accept_trials:
                self.logger.info(f"Auto-accepting trial {self.j + 1} "
                                 f"(error norm: {error_norm:.6f})")
            else:
                self.logger.info("Waiting for user to review... (Accept / Repeat / Abort)")
                data, trace = wait_for_events(
                    OR(self.common.interaction_events.resume,
                       self.common.interaction_events.repeat,
                       self.common.interaction_events.stop),
                    timeout=120.0,
                )
                if data is TIMEOUT:
                    self.logger.warning("Timed out waiting for user review (120s)")
                    self._emit_trial_error('Timeout waiting for trial acceptance')
                    return TrialResult.ERROR
                if trace.caused_by(self.common.interaction_events.stop):
                    self.logger.warning("User aborted after trajectory")
                    self._emit_trial_error('User aborted')
                    return TrialResult.ERROR
                if trace.caused_by(self.common.interaction_events.repeat):
                    self.logger.info(f"User requested to repeat trial {self.j + 1}")
                    self.events.trial_reverted.set(data={
                        'trial_index': self.j, 'error_norm': error_norm,
                    })
                    self.callbacks.trial_reverted.call()
                    self.wifi_events.trial_reverted.send(data={
                        **self._wifi_data, 'error_norm': float(error_norm),
                    }, flags=self._WIFI_FLAGS)
                    return TrialResult.REVERT
                self.logger.info("Trial accepted by user")

            # --- Step 7: Compute the IITL transfer (and model) update ---
            self.phase = IITL_Phase.COMPUTING_UPDATE
            self.logger.info("Computing IITL update...")
            upd = self._compute_iitl_update(u_source, u_target, y_source,
                                            y_target, learning_error)

            self.logger.info(f"  Learning error norm: {error_norm:.6f}")
            if self.settings.model_free:
                self.logger.info(f"  Model output error norm: "
                                 f"{upd['model_output_error_norm']:.6f}")
            self.logger.info(f"  Transfer change ||t_new - t||: "
                             f"{float(np.linalg.norm(upd['t_new'] - self._t)):.6f}")
            if upd['transfer_vector_error_norm'] is not None:
                self.logger.info(f"  Transfer-vector error ||t_ref - t_new||: "
                                 f"{upd['transfer_vector_error_norm']:.6f}")

            # --- Step 8: Store trial data and advance ---
            trial_meta = IITL_Trial_Meta(
                timecode=trajectory_start_timecode,
                tick_start=trajectory_data.meta.start_tick,
                tick_end=trajectory_data.meta.end_tick,
                time_start=self.common.get_time_for_tick(trajectory_data.meta.start_tick),
                time_end=self.common.get_time_for_tick(trajectory_data.meta.end_tick),
            )
            trial_data = IITL_Trial_Data(
                index=self.j,
                t=self.t_vector,
                u_source=u_source, y_source=y_source,
                u_target=u_target, y_target=y_target,
                learning_error=learning_error, learning_error_norm=error_norm,
                s=upd['s'], learning_matrix=upd['L_j'], q_filter=self._Q,
                transfer_vector=self._t.copy(),
                transfer_vector_update=upd['t_new'],
                transfer_vector_error_norm=upd['transfer_vector_error_norm'],
                model_vector=(self._f.copy() if self.settings.model_free else None),
                model_vector_update=upd['f_new'],
                model_prediction=upd['model_prediction'],
                model_output_error=upd['model_output_error'],
                model_output_error_norm=upd['model_output_error_norm'],
                model_learning_matrix=upd['K_j'],
                model_q_filter=self._Q_m,
                model_estimation_error_norm=upd['model_estimation_error_norm'],
                s_m=upd['s_m'],
                meta=trial_meta, samples=trial_samples,
            )
            self.trials.append(trial_data)

            # Apply updates for the next trial.
            self._t = upd['t_new']
            if self.settings.model_free:
                self._f = upd['f_new']
            self._G = upd['G_new']

            self.logger.info(f"Trial {self.j + 1}/{self.settings.J} completed and saved")
            self.events.trial_finished.set(data=trial_data)
            self.callbacks.trial_finished.call()
            self.wifi_events.trial_finished.send(data={
                **self._wifi_data, **extra_trial_data,
                'learning_error_norm': error_norm,
                'transfer_vector_error_norm': upd['transfer_vector_error_norm'],
                'model_output_error_norm': upd['model_output_error_norm'],
                'model_estimation_error_norm': upd['model_estimation_error_norm'],
                't': self.t_vector,
                'u_source': u_source, 'u_target': u_target,
                'y_source': y_source, 'y_target': y_target,
                'transfer_vector': self._t,
                'transfer_vector_update': upd['t_new'],
            }, flags=self._WIFI_FLAGS)

            self.j += 1
            return TrialResult.FINISHED

        except Exception as e:
            self.logger.error(f"Unexpected error during trial: {e}")
            self._emit_trial_error(str(e))
            return TrialResult.ERROR

        finally:
            self.interfaces.enable_external_input()
            self.control.enable_external_input()
            self.control.enable_psi_control(False)
            self.estimation.set_tracker_updates_enabled(True)

    # === IITL UPDATE MATH =========================================================================================
    def _compute_iitl_update(self, u_source, u_target, y_source, y_target,
                             learning_error) -> dict:
        """One IITL update step (covers all four method variants).

        Returns a dict with the next transfer vector ``t_new``, the next model
        estimate ``f_new`` (model-free) or the fixed model, the Gramian
        ``G_new``, the learning matrices, the realised regularisers, and the
        optional logging errors. Mirrors the per-trial body of the simulation
        runners (run_iitl / run_rls_iitl / run_model_free_iitl /
        run_model_free_rls_iitl).
        """
        kappa = self.settings.kappa

        # --- inner loop: model estimate -------------------------------------
        if self.settings.model_free:
            model_prediction = vector_to_lifted_matrix(u_target) @ self._f
            model_output_error = y_target - model_prediction
            if self.settings.adaptive_s_m:
                s_m = iml_get_learning_gain(u_target, kappa)
            else:
                s_m = self.settings.s_m
            K_j, Q_iml = iml_get_norm_optimal_matrices(u_target, s=s_m, r=0.0)
            Q_inner = self._Q_m if self._Q_m is not None else Q_iml
            f_new = iml_update(self._f, model_output_error, K_j, Q_inner)
            model_output_error_norm = float(np.linalg.norm(model_output_error))
        else:
            # Known model: no inner loop, the model stays fixed at f_target.
            f_new = self._f
            model_prediction = None
            model_output_error = None
            model_output_error_norm = None
            K_j = None
            s_m = None

        F_model = vector_to_lifted_matrix(f_new)

        # --- outer loop: transfer-vector update -----------------------------
        if self.settings.outer_design == IITL_OuterDesign.SCALAR:
            if self.settings.adaptive_s:
                s = iitl_get_learning_gain(f_new, u_source, kappa)
            else:
                s = self.settings.s
            L_j = iitl_get_scalar_learning_matrix(F_model, u_source, s)
            G_new = self._G  # scalar design does not accumulate the Gramian
        else:
            s = self.settings.s
            P_j = F_model @ vector_to_lifted_matrix(u_source)
            G_new = iitl_update_rls_gramian(self._G, P_j)
            design = self.settings.outer_design
            if design == IITL_OuterDesign.RLS:
                L_j = iitl_get_rls_learning_matrix(G_new, P_j, s)
            elif design == IITL_OuterDesign.EXPLORATION_BIASED:
                L_j = iitl_get_exploration_biased_learning_matrix(
                    P_j, G_new, s, eps=self.settings.eps, delta=self.settings.delta)
            else:  # HYBRID
                L_j = iitl_get_hybrid_rls_exploration_learning_matrix(
                    P_j, G_new, s, eps=self.settings.eps, delta=self.settings.delta)

        t_new = iitl_update(self._t, L_j, learning_error, self._Q)

        # --- logging errors -------------------------------------------------
        if self.settings.reference_transfer_vector is not None:
            transfer_vector_error_norm = float(np.linalg.norm(
                np.asarray(self.settings.reference_transfer_vector) - t_new))
        else:
            transfer_vector_error_norm = None

        if self.settings.model_free and self.settings.f_target is not None:
            model_estimation_error_norm = float(np.linalg.norm(
                np.asarray(self.settings.f_target) - f_new))
        else:
            model_estimation_error_norm = None

        return {
            't_new': t_new, 'f_new': f_new, 'G_new': G_new,
            'L_j': L_j, 's': s,
            'K_j': K_j, 's_m': s_m,
            'model_prediction': model_prediction,
            'model_output_error': model_output_error,
            'model_output_error_norm': model_output_error_norm,
            'transfer_vector_error_norm': transfer_vector_error_norm,
            'model_estimation_error_norm': model_estimation_error_norm,
        }

    # === HELPERS ==================================================================================================
    def _emit_trial_error(self, message: str):
        """Emit the trial_error event/callback/wifi triple."""
        self.events.trial_error.set(data={'trial_index': self.j, 'message': message})
        self.callbacks.trial_error.call()
        self.wifi_events.trial_error.send(data={**self._wifi_data, 'message': message},
                                          flags=self._WIFI_FLAGS)

    def _collect_trial_samples(self, trajectory_data) -> list | None:
        """Retrieve logged samples for the trajectory tick range (best effort)."""
        try:
            lp = get_logging_provider()
            start_tick = (trajectory_data.meta.start_tick // 10) * 10
            end_tick = ((trajectory_data.meta.end_tick + 9) // 10) * 10
            samples_ready = threading.Event()
            samples_container = [None]

            def _on_samples(data):
                samples_container[0] = data
                samples_ready.set()

            lp.get_data(start=start_tick, end=end_tick,
                        add_intermediate_samples=True, callback=_on_samples)
            samples_ready.wait(timeout=10.0)
            samples = samples_container[0]
            if samples is not None:
                self.logger.info(f"Collected {len(samples)} samples "
                                 f"(ticks {start_tick}..{end_tick})")
            else:
                self.logger.warning("Failed to retrieve trial samples")
            return samples
        except Exception as e:
            self.logger.warning(f"Could not collect trial samples: {e}")
            return None

    # === RESULTS ==================================================================================================
    def _build_results(self) -> IITL_Results:
        meta = IITL_Results_Meta(
            robot_id=self.common.id,
            date=datetime.now().isoformat(),
            robot_config=self.common.config,
            control_config=self.control.get_control_config(),
            settings=self.settings,
            logs=self._logs,
        )
        return IITL_Results(meta=meta, state=self.state, trials=self.trials)

    def _save_results_to_file(self, results: IITL_Results) -> str | None:
        from core.utils.json_utils import writeJSON_mp

        experiments_dir = os.path.expanduser("~/robot/experiments")
        os.makedirs(experiments_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = os.path.join(experiments_dir,
                                f"iitl_{self.settings.id}_{timestamp}.json")
        self.logger.info(f"Saving IITL results to {filepath} ...")
        if writeJSON_mp(filepath, results, convert_dataclass=True):
            self.logger.info(f"Saved IITL results to {filepath}")
            return filepath
        self.logger.error(f"Failed to save IITL results to {filepath}")
        return None
