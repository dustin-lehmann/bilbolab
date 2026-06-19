"""IML (Iterative Model Learning) experiment module.

Plain model identification on the BILBO robot. Where DILC jointly learns an
input *and* a model and IITL learns an input *transfer*, IML does only the model
step: it drives a set of known input trajectories, measures the responses, and
iteratively identifies the system's impulse-response (Markov-parameter) vector
``m``. There is no reference output to track and no input update -- the inputs
come from a fixed learning set (typically a list of ``.bitrj`` files).

Per trial ``j`` (cyclic over the learning set L of input trajectories):

    1. Select the input         u_j = L[j mod |L|]
    2. Apply u_j to the robot and measure the output y_j
    3. IML step -- refine the model estimate from the prediction error:
         - ITERATIVE (norm-optimal IML):
               e_j     = y_j - M(u_j) m_j
               K_j     = (U_j^T U_j + s_m I)^{-1} U_j^T       (U_j = M(u_j))
               m_{j+1} = Q_m (m_j + K_j e_j)
         - RLS (accumulated-information batch least squares):
               G_j     = G_{j-1} + U_j^T U_j
               b_j     = b_{j-1} + U_j^T y_j
               m_{j+1} = Q_m (G_j + s_m I)^{-1} b_j

Where ``M(v)`` is the lifted (lower-triangular Toeplitz) matrix of ``v`` and
``Q_m`` is an optional zero-phase FIR low-pass that smooths the model estimate
across its coefficients (built with DILC's :meth:`_build_q_filter`).

The headline output is the identified model ``m``. The experiment tracks the
*best* estimate -- the one whose post-update residual ``||y_j - M(u_j) m_{j+1}||``
is smallest over the run -- and, on completion, saves it as a ``.bmvec`` model
vector file alongside the full results JSON. A subsequent host-side step can fit
those Markov parameters to physical BILBO model parameters (NLS); that lives on
the host and is out of scope here.

Generic hardware/state-machine plumbing is shared with DILC: this experiment
subclasses :class:`DILC_Experiment` and inherits ``prepare_trial()``, the
lifecycle hooks, the Q-filter builder, log capture, ``stop()``, ``set_auto_*()``
and the common WiFi-data property; it overrides only the IML-specific parts.
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
from core.utils.control_lib.lib_control.learning.q_filter import (
    FIR_Design_Params, design_zero_phase_fir, build_Qf_zero_padded,
)
from core.utils.control_lib.lib_control.learning.lifted import vector_to_lifted_matrix
from core.utils.control_lib.lib_control.learning.iml.iml import (
    iml_get_norm_optimal_matrices,
    iml_get_learning_gain,
    iml_update,
)
from core.utils.data import generate_time_vector_by_length
from core.utils.events import wait_for_events, OR, TIMEOUT
from core.utils.logging_utils import Logger

from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.config import BILBO_Config
from robot.control.bilbo_control import BILBO_Control
from robot.control.bilbo_control_definitions import BILBO_ControlConfig
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment import BILBO_InputTrajectory, BILBO_ExperimentHandler
from robot.experiment.definitions import (
    BILBO_ModelVectorFileData,
    write_model_vector_file,
    MODEL_VECTOR_FILE_EXTENSION,
)
from robot.interfaces.bilbo_interfaces import BILBO_Interfaces
from robot.core import get_logging_provider
from robot.lowlevel.stm32_general import MAX_STEPS_TRAJECTORY
from robot.utilities.buzzer import beep

from robot.experiment.trial_experiments.dilc import (
    DILC_Experiment,
    DILC_InitialConditions as IML_InitialConditions,
    DILC_Experiment_Meta_Settings as IML_Experiment_Meta_Settings,
    DILC_Requirements as IML_Requirements,
    DILC_Trial_Meta as IML_Trial_Meta,
    DILC_Experiment_State as IML_Experiment_State,
    DILC_Phase as IML_Phase,
    DILC_Experiment_Events as IML_Experiment_Events,
    DILC_Experiment_Callbacks as IML_Experiment_Callbacks,
    TrialResult,
)


# === Data Structures ==============================================================================================

class IML_Method(enum.StrEnum):
    """Model-identification scheme.

    ITERATIVE accumulates the model across trials with the per-trial
    norm-optimal IML update (Sec.~iml). RLS maintains the cumulative regressor
    Gramian and re-solves the ridge-regularised batch least-squares estimate
    every trial -- the model-identification analogue of the RLS IITL design.
    """
    ITERATIVE = "iterative"
    RLS = "rls"


@dataclasses.dataclass
class IML_LearningInput:
    """One input trajectory of the learning set.

    Attributes:
        input: Input trajectory of length N (the signal driven on the robot).
        id: Optional identifier (e.g. the source ``.bitrj`` file name) for logs.
    """
    input: np.ndarray
    id: str = ""


@dataclasses.dataclass
class IML_Experiment_Settings:
    """Configuration for an IML (model identification) experiment.

    Attributes:
        id: Unique experiment identifier.
        description: Human-readable description.
        J: Number of trials (model-learning iterations).
        learning_set: Input trajectories to drive (the learning set L). Every
            input must share the horizon N. Selected cyclically across trials.
        Ts: Sampling period in seconds (must match the control loop, e.g. 0.01).
        initial_conditions: Starting pose for each trial.
        method: Identification scheme (see IML_Method).
        s_m: Model regularisation, s_m > 0. Required only when ``adaptive_s_m``
            is False; ignored otherwise. Applies to both methods.
        adaptive_s_m: Recompute s_m per trial with a condition-number heuristic
            (cap ``kappa``). ITERATIVE uses the current input's regressor; RLS
            uses the accumulated Gramian (s_m = sigma_max(G) / kappa).
        kappa: Condition-number cap for the adaptive regulariser.
        model_lowpass: FIR low-pass for the model update (Q_m). None leaves the
            norm-optimal IML filter (identity at r=0) in place for ITERATIVE and
            applies no smoothing for RLS.
        model_length: Number of impulse-response taps M to identify (M <= N).
            The model is truncated to M taps and the rest treated as exactly
            zero -- use it to match the system's settling time and avoid a
            noisy, under-determined tail. None -> full N (or derived from
            ``model_horizon_s``).
        model_horizon_s: Alternative to ``model_length``: model length in
            seconds, converted to ``round(model_horizon_s / Ts)`` taps.
            ``model_length`` takes precedence if both are given.
        tail_penalty: Decay-promoting (tap-weighted) ridge strength. 0 -> uniform
            ridge (off). When > 0 the regulariser grows along the coefficient
            axis, shrinking late taps toward zero (good for a controlled system
            whose impulse response should decay). Combine with ``model_length``
            or use on its own.
        tail_penalty_type: 'linear' (weight 1 .. 1+tail_penalty across the taps)
            or 'exponential' (weight 1 .. exp(tail_penalty)).
        m0: Initial model estimate (length M, or N when not truncated). Defaults
            to zeros; longer vectors are truncated to the model length.
        reference_model: Optional reference Markov vector m_ref. When given,
            ``||m_ref - m_j||`` is logged per trial.
        max_input_abs: Hard cap on peak |u|. None -> auto-derived as
            ``input_safety_factor * max|u|`` over the learning set.
        input_safety_factor: Multiplier for the auto-derived cap.
        meta / requirements: Shared flow / requirement settings (same semantics
            as DILC).
    """
    id: str
    description: str
    J: int
    learning_set: list[IML_LearningInput]
    Ts: float
    initial_conditions: IML_InitialConditions

    # --- method selection -----------------------------------------------------
    method: IML_Method = IML_Method.ITERATIVE

    # --- regularisation -------------------------------------------------------
    s_m: float | None = None
    adaptive_s_m: bool = True
    kappa: float = 100.0

    # --- Q-filter (reuse DILC's zero-phase FIR design) ------------------------
    model_lowpass: FIR_Design_Params | None = None

    # --- model structure (length truncation + decay regularisation) -----------
    model_length: int | None = None
    model_horizon_s: float | None = None
    tail_penalty: float = 0.0
    tail_penalty_type: str = "linear"

    # --- initial estimate / reference -----------------------------------------
    m0: np.ndarray | None = None
    reference_model: np.ndarray | None = None

    # --- safety ---------------------------------------------------------------
    max_input_abs: float | None = None
    input_safety_factor: float = 1.5

    # --- shared flow / requirements (same semantics as DILC) ------------------
    initial_conditions_u0: IML_InitialConditions | None = None
    meta: IML_Experiment_Meta_Settings = dataclasses.field(
        default_factory=IML_Experiment_Meta_Settings)
    requirements: IML_Requirements = dataclasses.field(
        default_factory=IML_Requirements)


@dataclasses.dataclass(frozen=True)
class IML_Trial_Data:
    """Recorded data and computed update for a single completed IML trial.

    Attributes:
        index: Trial index (0-based).
        t: Time vector for this trial.
        input_id: Identifier of the learning-set input used this trial.
        u: Input trajectory that was applied.
        y: Measured output.
        model_vector: Model estimate carried into this trial (m_j).
        model_vector_update: Updated model estimate (m_{j+1}).
        model_prediction: Predicted output M(u) m_j.
        model_output_error: Prediction error y - M(u) m_j.
        model_output_error_norm: L2 norm of the pre-update prediction error.
        model_fit_error_norm: L2 norm of the post-update residual y - M(u) m_{j+1}.
        model_learning_matrix: IML learning matrix K_j (ITERATIVE only; None for RLS).
        model_q_filter: Q_m filter matrix applied to the update (or None).
        model_estimation_error_norm: ||m_ref - m_{j+1}|| if reference_model given.
        s_m: Realised model regularisation this trial.
    """
    index: int
    t: np.ndarray
    input_id: str
    u: np.ndarray
    y: np.ndarray
    model_vector: np.ndarray
    model_vector_update: np.ndarray
    model_prediction: np.ndarray
    model_output_error: np.ndarray
    model_output_error_norm: float
    model_fit_error_norm: float
    model_learning_matrix: np.ndarray | None
    model_q_filter: np.ndarray | None
    model_estimation_error_norm: float | None
    s_m: float

    meta: IML_Trial_Meta | None = None
    samples: list[dict] | None = None


@dataclasses.dataclass
class IML_Results_Meta:
    """Metadata recorded alongside experiment results for reproducibility."""
    robot_id: str
    date: str
    robot_config: BILBO_Config
    control_config: BILBO_ControlConfig
    settings: IML_Experiment_Settings
    logs: list[dict] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class IML_Results:
    """Complete results of an IML experiment (partial on error/abort).

    Attributes:
        meta: Experiment metadata (robot config, control config, settings).
        state: Final experiment state (FINISHED or ERROR).
        trials: List of trial data, one entry per completed trial.
        best_model: Best identified model vector over the run (lowest fit residual).
        best_model_trial_index: Trial index that produced ``best_model``.
        final_model: Model estimate after the last completed trial.
    """
    meta: IML_Results_Meta
    state: IML_Experiment_State
    trials: list[IML_Trial_Data]
    best_model: np.ndarray | None = None
    best_model_trial_index: int | None = None
    final_model: np.ndarray | None = None


# === WiFi Events ==================================================================================================

_IML_WIFI_EVENT = WifiEvent(data_type=dict, flags=WifiEventFlag('group', str))


@wifi_event_definition
class IML_WifiEvents(WifiEventContainer):
    """WiFi events sent by the IML experiment to the host.

    Same lifecycle as DILC, under the ``'iml_experiment'`` group so the host can
    route IML telemetry independently.
    """
    experiment_initialized: WifiEvent = _IML_WIFI_EVENT
    experiment_started: WifiEvent = _IML_WIFI_EVENT
    experiment_finished: WifiEvent = _IML_WIFI_EVENT
    experiment_error: WifiEvent = _IML_WIFI_EVENT

    trajectory_loaded: WifiEvent = _IML_WIFI_EVENT
    trajectory_started: WifiEvent = _IML_WIFI_EVENT
    trajectory_error: WifiEvent = _IML_WIFI_EVENT
    trajectory_finished: WifiEvent = _IML_WIFI_EVENT

    trial_started: WifiEvent = _IML_WIFI_EVENT
    trial_prepared: WifiEvent = _IML_WIFI_EVENT
    trial_reverted: WifiEvent = _IML_WIFI_EVENT
    trial_finished: WifiEvent = _IML_WIFI_EVENT
    trial_error: WifiEvent = _IML_WIFI_EVENT

    meta_settings_changed: WifiEvent = _IML_WIFI_EVENT


# === IML Experiment ===============================================================================================

class IML_Experiment(DILC_Experiment):
    """Iterative Model Learning (model identification) experiment on BILBO.

    Subclasses :class:`DILC_Experiment` to inherit the hardware/state-machine
    plumbing (trial preparation, navigation, user-interaction waits, Q-filter
    builder, log capture, abort handling, WiFi-data property). Overrides the
    IML-specific pieces: initialisation of the model state, the per-trial
    drive-and-update logic, and results building/saving.
    """
    settings: IML_Experiment_Settings
    trials: list[IML_Trial_Data]

    _WIFI_FLAGS = {'group': 'iml_experiment'}

    # === INIT =====================================================================================================
    def __init__(self, common: BILBO_Common,
                 estimation: BILBO_Estimation,
                 control: BILBO_Control,
                 communication: BILBO_Communication,
                 interfaces: BILBO_Interfaces,
                 experiment_handler: BILBO_ExperimentHandler,
                 settings: IML_Experiment_Settings):
        self.common = common
        self.settings = settings
        self.control = control
        self.communication = communication
        self.estimation = estimation
        self.interfaces = interfaces
        self.experiment_handler = experiment_handler

        self.trials = []
        self.phase = IML_Phase.IDLE

        self._auto_start_trials = settings.meta.auto_start_trials
        self._auto_accept_trials = settings.meta.auto_accept_trials

        self.logger = Logger(f"IML Experiment {self.settings.id}", "DEBUG")
        self.events = IML_Experiment_Events()
        self.callbacks = IML_Experiment_Callbacks()

        self._logs = []
        self._log_capture_enabled = False

        self.wifi_events = IML_WifiEvents(
            wifi=communication.wifi.wifi,
            id='iml_experiment',
        )

        # IML learning state (set in initialize())
        self._m: np.ndarray | None = None    # current model estimate (length M)
        self._G: np.ndarray | None = None     # cumulative regressor Gramian (RLS, MxM)
        self._b: np.ndarray | None = None     # cumulative regressor/output product (RLS, M)
        self._Q_m: np.ndarray | None = None   # model Q-filter (MxM)
        self._max_input_abs: float | None = None
        self._M: int = 0                       # number of identified taps (model length)
        self._reg_weights: np.ndarray | None = None  # per-tap ridge weights (length M)

        # Best-model tracking
        self._best_model: np.ndarray | None = None
        self._best_fit_norm: float = float('inf')
        self._best_model_trial_index: int | None = None

        self.common.interaction_events.stop.on(self.stop, once=True)

    # === INITIALIZATION ===========================================================================================
    def initialize(self):
        """Validate settings and set up the model state and Q-filter.

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

        # Every learning input must share the horizon N.
        for k, item in enumerate(ls):
            if len(item.input) != self.N:
                raise ValueError(
                    f"Learning input {k} has length {len(item.input)}; "
                    f"expected N={self.N}.")

        # Method-consistency checks. Both schemes accept an adaptive regulariser;
        # an explicit s_m is only required when adaptive_s_m is disabled.
        if not self.settings.adaptive_s_m and self.settings.s_m is None:
            raise ValueError(
                f"s_m is required when adaptive_s_m is False "
                f"(method={self.settings.method.value}).")

        self.t_vector = generate_time_vector_by_length(num_samples=self.N, dt=self.settings.Ts)

        # --- Model length M (number of identified taps; M <= N) ---
        if self.settings.model_length is not None:
            self._M = int(self.settings.model_length)
        elif self.settings.model_horizon_s is not None:
            self._M = int(round(self.settings.model_horizon_s / self.settings.Ts))
        else:
            self._M = self.N
        if not (1 <= self._M <= self.N):
            raise ValueError(
                f"Model length M={self._M} must be in [1, N={self.N}].")
        if self._M < self.N:
            self.logger.info(f"Identifying a truncated model: M={self._M} taps "
                             f"({self._M * self.settings.Ts:.2f}s of {self.N * self.settings.Ts:.2f}s).")

        # --- Initial model estimate m_0 (length M) ---
        if self.settings.m0 is None:
            self._m = np.zeros(self._M)
            self.logger.info("No m0 provided. Starting the model from zeros.")
        else:
            m0 = np.asarray(self.settings.m0, dtype=float).ravel()
            if len(m0) != self._M:
                self.logger.warning(f"m0 length {len(m0)} != model length {self._M}; "
                                    f"truncating/padding to M.")
                m0 = (m0[:self._M] if len(m0) >= self._M
                      else np.pad(m0, (0, self._M - len(m0))))
            self._m = m0.copy()
            self.logger.info("Using provided initial model m0.")

        self._G = np.zeros((self._M, self._M))
        self._b = np.zeros(self._M)
        self.j = 0

        # --- Per-tap ridge weights (decay-promoting tail penalty) ---
        self._reg_weights = self._build_reg_weights(self._M)

        # --- Q-filter (zero-phase FIR), built on the model length M ---
        self._Q_m = (self._build_model_q_filter(self.settings.model_lowpass, self._M)
                     if self.settings.model_lowpass is not None else None)

        # --- Safety cap on the driven input ---
        peak_input = max(float(np.max(np.abs(item.input))) for item in ls)
        if self.settings.max_input_abs is not None:
            self._max_input_abs = float(self.settings.max_input_abs)
        else:
            self._max_input_abs = self.settings.input_safety_factor * peak_input
        self.logger.info(f"Input safety cap: |u| <= {self._max_input_abs:.4f} "
                         f"(learning-set peak {peak_input:.4f}).")

        # --- Best-model tracking reset ---
        self._best_model = None
        self._best_fit_norm = float('inf')
        self._best_model_trial_index = None

        self._finished = False
        self._abort_requested = False
        self.trials = []
        self.phase = IML_Phase.IDLE

        self._on_initialize()

        self.state = IML_Experiment_State.INITIALIZED
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
        self.logger.info("IML experiment initialized successfully")

    # === MAIN LOOP ================================================================================================
    def run(self) -> IML_Results | None:
        """Run the full IML experiment (initialize, then J trials)."""
        try:
            self.initialize()
        except Exception as e:
            self.logger.error(f"Failed to initialize experiment: {e}")
            self.state = IML_Experiment_State.ERROR
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
        self.state = IML_Experiment_State.RUNNING
        self.logger.info("=" * 60)
        self.logger.info(f"Starting IML experiment '{self.settings.id}'")
        self.logger.info(f"  Trials: {self.settings.J}")
        self.logger.info(f"  Trajectory length: {self.N} samples "
                         f"({self.N * self.settings.Ts:.2f}s)")
        self.logger.info(f"  Learning set: {len(self.settings.learning_set)} inputs")
        self.logger.info(f"  Method: {self.settings.method.value}")
        self.logger.info(f"  Q_m (model): {'on' if self._Q_m is not None else 'off'}")
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
                self.phase = IML_Phase.IDLE
                self.state = IML_Experiment_State.ERROR
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
                model_filepath = self._save_best_model_to_file(results)
                self.wifi_events.experiment_error.send(data={
                    **self._wifi_data, 'message': error_msg,
                    'results_filepath': results_filepath,
                    'model_filepath': model_filepath,
                }, flags=self._WIFI_FLAGS)
                beep(frequency='low', repeats=3)
                self._on_cleanup()
                return results

        self.phase = IML_Phase.IDLE
        if self._abort_requested:
            self.state = IML_Experiment_State.ERROR
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
            model_filepath = self._save_best_model_to_file(results)
            self.wifi_events.experiment_error.send(data={
                **self._wifi_data, 'message': 'Experiment aborted by user',
                'results_filepath': results_filepath,
                'model_filepath': model_filepath,
            }, flags=self._WIFI_FLAGS)
            self._on_cleanup()
            return results

        self.state = IML_Experiment_State.FINISHED
        self._finished = True
        self._stop_log_capture()
        results = self._build_results()
        results_filepath = self._save_results_to_file(results)
        model_filepath = self._save_best_model_to_file(results)

        self.logger.info("=" * 60)
        self.logger.info(f"IML experiment '{self.settings.id}' completed successfully")
        self.logger.info(f"  Completed trials: {len(self.trials)}/{self.settings.J}")
        if self.trials:
            self.logger.info(f"  Final model output-error norm: "
                             f"{self.trials[-1].model_output_error_norm:.6f}")
            best_trial_str = (self._best_model_trial_index + 1
                              if self._best_model_trial_index is not None else '-')
            self.logger.info(f"  Best model: trial {best_trial_str} "
                             f"(aggregate residual over all trials: {self._best_fit_norm:.6f})")
        self.logger.info("=" * 60)

        self.events.experiment_finished.set(data=results)
        self.callbacks.experiment_finished.call()
        self.wifi_events.experiment_finished.send(data={
            **self._wifi_data,
            **self._extra_experiment_finished_wifi_data(),
            'final_model_output_error_norm':
                float(self.trials[-1].model_output_error_norm) if self.trials else None,
            'model_output_error_norms':
                [float(t.model_output_error_norm) for t in self.trials],
            'model_fit_error_norms': [float(t.model_fit_error_norm) for t in self.trials],
            'model_estimation_error_norms':
                [t.model_estimation_error_norm for t in self.trials],
            'best_fit_error_norm':
                float(self._best_fit_norm) if self._best_model is not None else None,
            'best_model_trial_index': self._best_model_trial_index,
            'best_model': self._best_model,
            'final_model': self._m,
            'results_filepath': results_filepath,
            'model_filepath': model_filepath,
        }, flags=self._WIFI_FLAGS)
        beep(frequency='high', repeats=3)

        self._on_cleanup()
        return results

    # === TRIAL ====================================================================================================
    def run_trial(self) -> TrialResult:
        """Execute one IML trial: drive an input, measure, update the model.

        Mirrors DILC.run_trial's prepare/preview/run/accept flow; the
        IML-specific parts are the fixed driven input ``u`` (with the safety
        check), the prediction error against the current model, and the model
        update of ``_compute_iml_update``.
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info(f"Trial {self.j + 1}/{self.settings.J}")
            self.logger.info("=" * 60)

            self.phase = IML_Phase.PREPARING
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
            self.phase = IML_Phase.WAITING_FOR_START

            # --- Step 2: Select the input for this trial ---
            L = len(self.settings.learning_set)
            learning_input = self.settings.learning_set[self.j % L]
            u = np.asarray(learning_input.input, dtype=float)
            input_id = learning_input.id or f"input {self.j % L + 1}/{L}"

            # Safety: refuse to inject an over-amplitude input.
            peak = float(np.max(np.abs(u)))
            if peak > self._max_input_abs:
                msg = (f"Input peak |u|={peak:.4f} exceeds the safety cap "
                       f"{self._max_input_abs:.4f}; aborting trial.")
                self.logger.error(msg)
                self._emit_trial_error(msg)
                return TrialResult.ERROR

            input_trajectory = BILBO_InputTrajectory.from_vector(
                vector=u,
                name=f"IML trial {self.j + 1} ({input_id})",
                id=self.j + 1,
                delta=self.common.config.model.trajectory_delta,
            )
            self.logger.info(f"Input trajectory: {input_trajectory.length} steps, "
                             f"u range [{u.min():.4f}, {u.max():.4f}], "
                             f"peak {peak:.4f}/{self._max_input_abs:.4f}")
            self.events.trajectory_loaded.set(data={
                'trajectory': input_trajectory, 'trial_index': self.j,
            })
            self.wifi_events.trajectory_loaded.send(data={
                **self._wifi_data,
                'trajectory_length': input_trajectory.length,
                'u_min': float(u.min()), 'u_max': float(u.max()),
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
            self.phase = IML_Phase.RUNNING_TRAJECTORY
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

            # Blocking call — the robot executes the full input.
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
            self.phase = IML_Phase.WAITING_FOR_ACCEPTANCE

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

            # --- Step 5: Extract the measured output ---
            y = np.asarray([
                state.theta for state in trajectory_data.data.state_trajectory.states
            ])
            n_out = len(y)
            if n_out != self.N:
                self.logger.warning(
                    f"Output length ({n_out}) differs from N={self.N} "
                    f"(delta {n_out - self.N}).")
                if n_out > self.N:
                    y = y[:self.N]
                else:
                    pad_value = y[-1] if n_out > 0 else 0.0
                    y = np.pad(y, (0, self.N - n_out),
                               mode='constant', constant_values=pad_value)

            # Pre-update prediction error against the current model estimate.
            prediction = self._regressor(u) @ self._m
            output_error = y - prediction
            error_norm = float(np.linalg.norm(output_error))
            max_abs_error = float(np.max(np.abs(output_error)))
            self.logger.info(f"Trajectory finished. Model output-error norm "
                             f"||y - M(u) m||: {error_norm:.6f} "
                             f"(max abs {max_abs_error:.6f})")

            self.events.trajectory_finished.set(data={
                'trajectory': input_trajectory, 'trial_index': self.j,
                'y': y, 'model_output_error': output_error, 'error_norm': error_norm,
            })
            self.callbacks.trajectory_finished.call()
            self.wifi_events.trajectory_finished.send(data={
                **self._wifi_data, **extra_trial_data,
                'error_norm': float(error_norm), 'max_abs_error': max_abs_error,
                'u': u, 'y': y, 'model_prediction': prediction,
                'model_output_error': output_error, 't': self.t_vector,
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

            # --- Step 7: Compute the IML model update ---
            self.phase = IML_Phase.COMPUTING_UPDATE
            self.logger.info("Computing IML update...")
            upd = self._compute_iml_update(u, y, prediction, output_error)

            self.logger.info(f"  Model output error norm: {error_norm:.6f}")
            self.logger.info(f"  Post-update fit residual: {upd['fit_error_norm']:.6f}")
            self.logger.info(f"  Model change ||m_new - m||: "
                             f"{float(np.linalg.norm(upd['m_new'] - self._m)):.6f}")
            if upd['model_estimation_error_norm'] is not None:
                self.logger.info(f"  Model estimation error ||m_ref - m_new||: "
                                 f"{upd['model_estimation_error_norm']:.6f}")

            # --- Step 8: Store trial data and advance ---
            trial_meta = IML_Trial_Meta(
                timecode=trajectory_start_timecode,
                tick_start=trajectory_data.meta.start_tick,
                tick_end=trajectory_data.meta.end_tick,
                time_start=self.common.get_time_for_tick(trajectory_data.meta.start_tick),
                time_end=self.common.get_time_for_tick(trajectory_data.meta.end_tick),
            )
            trial_data = IML_Trial_Data(
                index=self.j,
                t=self.t_vector,
                input_id=input_id,
                u=u, y=y,
                model_vector=self._m.copy(),
                model_vector_update=upd['m_new'],
                model_prediction=prediction,
                model_output_error=output_error,
                model_output_error_norm=error_norm,
                model_fit_error_norm=upd['fit_error_norm'],
                model_learning_matrix=upd['K_j'],
                model_q_filter=self._Q_m,
                model_estimation_error_norm=upd['model_estimation_error_norm'],
                s_m=upd['s_m'],
                meta=trial_meta, samples=trial_samples,
            )
            self.trials.append(trial_data)

            # Apply the update for the next trial.
            self._m = upd['m_new']
            self._G = upd['G_new']
            self._b = upd['b_new']

            # NB: the best model is selected at the end over the whole learning
            # set (see _select_best_model), NOT by the per-trial fit residual.
            # A model fit to a single trajectory can match it almost exactly
            # (overfit) while generalising poorly -- especially trial 1 of RLS,
            # which fits only its own data -- so single-trial residual is not a
            # valid selection criterion.

            self.logger.info(f"Trial {self.j + 1}/{self.settings.J} completed and saved")
            self.events.trial_finished.set(data=trial_data)
            self.callbacks.trial_finished.call()
            self.wifi_events.trial_finished.send(data={
                **self._wifi_data, **extra_trial_data,
                'model_output_error_norm': error_norm,
                'model_fit_error_norm': upd['fit_error_norm'],
                'model_estimation_error_norm': upd['model_estimation_error_norm'],
                't': self.t_vector,
                'u': u, 'y': y,
                'model_vector': trial_data.model_vector,
                'model_vector_update': upd['m_new'],
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

    # === IML UPDATE MATH ==========================================================================================
    def _regressor(self, u) -> np.ndarray:
        """Lifted regressor ``U_M = M(u)[:, :M]`` (N x M) for the truncated model."""
        U = vector_to_lifted_matrix(np.asarray(u, dtype=float))
        return U[:, :self._M] if self._M < U.shape[1] else U

    def _build_reg_weights(self, M: int) -> np.ndarray:
        """Per-tap ridge weights for the decay-promoting tail penalty.

        Returns ones (uniform ridge) when ``tail_penalty == 0``. Otherwise the
        weight grows along the coefficient axis so late taps are regularised
        more strongly and shrink toward zero::

            linear:      w_k = 1 + tail_penalty * k/(M-1)
            exponential: w_k = exp(tail_penalty * k/(M-1))
        """
        p = float(self.settings.tail_penalty)
        if p <= 0.0 or M <= 1:
            return np.ones(M)
        frac = np.arange(M, dtype=float) / (M - 1)
        if self.settings.tail_penalty_type == "exponential":
            w = np.exp(p * frac)
        else:
            w = 1.0 + p * frac
        self.logger.info(f"Tail-penalty ridge: type={self.settings.tail_penalty_type}, "
                         f"strength={p}, w[0]={w[0]:.3f} .. w[-1]={w[-1]:.3f}")
        return w

    def _build_model_q_filter(self, params: FIR_Design_Params, length: int) -> np.ndarray:
        """Symmetric, DC-normalised zero-phase FIR Q-filter, sized to the model.

        Same construction as DILC's ``_build_q_filter`` but on the model length M
        (the coefficient vector being smoothed) rather than the trajectory N.
        """
        h = design_zero_phase_fir(fc=params.fc, L=params.L, window=params.window)
        Q = build_Qf_zero_padded(h, length)
        Q = 0.5 * (Q + Q.T)
        ones = np.ones(length)
        dc_gain = (ones @ (Q @ ones)) / (ones @ ones)
        if abs(dc_gain) > 1e-12:
            Q = Q / dc_gain
        self.logger.info(f"Built IML model (Q_m) Q-filter: fc={params.fc} Hz, "
                         f"L={params.L}, window='{params.window}', size={length}")
        return Q

    def _compute_iml_update(self, u, y, prediction, output_error) -> dict:
        """One IML model update step (covers both ITERATIVE and RLS schemes).

        Uses the truncated regressor ``U_M = M(u)[:, :M]`` (N x M) and a
        (possibly tap-weighted) ridge ``S = s_m * diag(reg_weights)`` so the
        model length and the decay-promoting tail penalty apply uniformly to
        both schemes.

        Returns a dict with the next model estimate ``m_new`` (length M), the
        cumulative Gramian/product ``G_new``/``b_new`` (RLS), the learning matrix
        ``K_j`` (ITERATIVE only), the realised regulariser ``s_m``, the
        post-update fit residual norm, and the optional model-estimation error.
        """
        U = self._regressor(u)              # N x M
        W = np.diag(self._reg_weights)      # M x M (identity if no tail penalty)

        if self.settings.method == IML_Method.ITERATIVE:
            # Per-trial regularised pseudo-inverse update (norm-optimal IML, r=0):
            #   K_j = (U^T U + s_m W)^{-1} U^T,  m_{j+1} = Q_m (m_j + K_j e_j)
            if self.settings.adaptive_s_m:
                s_m = iml_get_learning_gain(u, self.settings.kappa)
            else:
                s_m = self.settings.s_m
            A = U.T @ U + s_m * W
            K_j = np.linalg.solve(A, U.T)            # M x N
            m_new = self._m + K_j @ output_error
            if self._Q_m is not None:
                m_new = self._Q_m @ m_new
            G_new = self._G  # iterative scheme does not accumulate the Gramian
            b_new = self._b
        else:
            # RLS: accumulate the regressor Gramian and re-solve the ridge LS.
            G_new = self._G + U.T @ U
            b_new = self._b + U.T @ y
            if self.settings.adaptive_s_m:
                # Ridge that caps the regularised condition number of G at ~kappa:
                # s_m = sigma_max(G) / kappa, so it tracks the accumulated data scale.
                s_m = float(np.linalg.norm(G_new, 2) / self.settings.kappa)
            else:
                s_m = self.settings.s_m
            m_new = np.linalg.solve(G_new + s_m * W, b_new)
            if self._Q_m is not None:
                m_new = self._Q_m @ m_new
            K_j = None

        # Post-update residual on this trial's data (diagnostic).
        fit_error = y - U @ m_new
        fit_error_norm = float(np.linalg.norm(fit_error))

        if self.settings.reference_model is not None:
            ref = np.asarray(self.settings.reference_model, dtype=float).ravel()
            if len(ref) >= self._M:
                model_estimation_error_norm = float(np.linalg.norm(ref[:self._M] - m_new))
            else:
                model_estimation_error_norm = None
        else:
            model_estimation_error_norm = None

        return {
            'm_new': m_new, 'G_new': G_new, 'b_new': b_new,
            'K_j': K_j, 's_m': float(s_m),
            'fit_error_norm': fit_error_norm,
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
    def _select_best_model(self):
        """Pick the best identified model over the *whole* learning set.

        Each trial's updated model is scored by its aggregate residual across
        all recorded trials, ``sqrt(sum_k ||y_k - M(u_k) m||^2)`` -- how well it
        explains every driven input, not just the one that produced it.
        Per-trial fit residual alone is misleading (a model fit to a single
        trajectory can match it almost exactly while generalising poorly), so
        selection is deferred to here, once all trials are available.
        """
        if not self.trials:
            return
        lifted = [(self._regressor(t.u), np.asarray(t.y, dtype=float))
                  for t in self.trials]
        best_norm = float('inf')
        for t in self.trials:
            m = np.asarray(t.model_vector_update, dtype=float)
            total_sq = 0.0
            for U, y in lifted:
                r = y - U @ m
                total_sq += float(r @ r)
            agg = float(np.sqrt(total_sq))
            if agg < best_norm:
                best_norm = agg
                self._best_model = m.copy()
                self._best_model_trial_index = t.index
        self._best_fit_norm = best_norm

    def _build_results(self) -> IML_Results:
        self._select_best_model()
        meta = IML_Results_Meta(
            robot_id=self.common.id,
            date=datetime.now().isoformat(),
            robot_config=self.common.config,
            control_config=self.control.get_control_config(),
            settings=self.settings,
            logs=self._logs,
        )
        return IML_Results(
            meta=meta,
            state=self.state,
            trials=self.trials,
            best_model=self._best_model,
            best_model_trial_index=self._best_model_trial_index,
            final_model=self._m,
        )

    def _save_results_to_file(self, results: IML_Results) -> str | None:
        from core.utils.json_utils import writeJSON_mp

        experiments_dir = os.path.expanduser("~/robot/experiments")
        os.makedirs(experiments_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = os.path.join(experiments_dir,
                                f"iml_{self.settings.id}_{timestamp}.json")
        self.logger.info(f"Saving IML results to {filepath} ...")
        if writeJSON_mp(filepath, results, convert_dataclass=True):
            self.logger.info(f"Saved IML results to {filepath}")
            return filepath
        self.logger.error(f"Failed to save IML results to {filepath}")
        return None

    def _save_best_model_to_file(self, results: IML_Results) -> str | None:
        """Save the best identified model vector as a ``.bmvec`` file.

        Returns the file path (without re-appending the extension), or None if
        no model was identified or the write failed.
        """
        model = self._best_model if self._best_model is not None else self._m
        if model is None:
            self.logger.warning("No model to save (no completed trials).")
            return None

        experiments_dir = os.path.expanduser("~/robot/experiments")
        os.makedirs(experiments_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f"iml_{self.settings.id}_{timestamp}"
        filepath = os.path.join(experiments_dir, f"{file_name}{MODEL_VECTOR_FILE_EXTENSION}")

        description = (f"IML-identified model ({self.settings.method.value}); "
                       f"best aggregate residual {self._best_fit_norm:.6f} over all trials "
                       f"(trial {self._best_model_trial_index + 1 if self._best_model_trial_index is not None else '-'})")
        data = BILBO_ModelVectorFileData(
            id=self.settings.id,
            description=description,
            vector=np.asarray(model, dtype=float).tolist(),
            dt=self.settings.Ts,
        )
        self.logger.info(f"Saving best IML model to {filepath} ...")
        try:
            write_model_vector_file(file_name, experiments_dir, data)
            self.logger.info(f"Saved best IML model to {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"Failed to save IML model vector: {e}")
            return None
