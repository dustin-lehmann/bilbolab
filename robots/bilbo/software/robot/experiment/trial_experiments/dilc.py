"""
DILC (Dual Iterative Learning Control) Experiment Module.

Implements a data-driven Dual Iterative Learning Control experiment for the BILBO robot.
DILC jointly learns two quantities across trials:

1. **ILC (Iterative Learning Control)**: Updates the input trajectory u_j to reduce
   the tracking error between the reference and the measured output.
2. **IML (Iterative Model Learning)**: Updates the model m_j (impulse response estimate)
   to improve the learning gain computation.

Algorithm per trial j:
    1. Apply input u_j to the system and measure output y_j
    2. Compute model prediction error:  e_iml = y_j - M(m_j) * u_j
    3. Update model:                    m_{j+1} = Q_iml * (m_j + L_iml(u_j) * e_iml)
    4. Compute tracking error:          e_ilc = r - y_j
    5. Update input:                    u_{j+1} = Q_ilc * (u_j + L_ilc(m_{j+1}) * e_ilc)

Where:
    - M(m) is the lifted (lower-triangular Toeplitz) matrix of impulse response m
    - L_iml, L_ilc are regularized pseudo-inverse learning gain matrices
    - Q_iml, Q_ilc are zero-phase FIR low-pass filters for iteration-domain robustness
    - r is the reference trajectory
    - The ILC gain L_ilc uses the *updated* model m_{j+1} (the "dual" coupling)
"""
import dataclasses
import enum
import os
import time
from datetime import datetime

import numpy as np

from core.communication.wifi.bilbolab_wifi_interface import (
    wifi_event_definition, WifiEventContainer, WifiEvent, WifiEventFlag,
)
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.control_lib.lib_control.il.q_filter import FIR_Design_Params, design_zero_phase_fir, \
    build_Qf_zero_padded
from core.utils.control_lib.lib_control.lifted_systems import vec2liftedMatrix
from core.utils.data import generate_time_vector_by_length, generate_random_input
from core.utils.events import event_definition, Event, wait_for_events, OR, TIMEOUT
from core.utils.logging_utils import Logger, enable_redirection, disable_redirection
from core.utils.time import wait_until, interruptible_sleep
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.config import BILBO_Config
from robot.control.bilbo_control import BILBO_Control
from robot.control.bilbo_control_definitions import BILBO_ControlConfig, BILBO_Control_Mode
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment import BILBO_InputTrajectory, BILBO_ExperimentHandler
from robot.interfaces.bilbo_interfaces import BILBO_Interfaces
from robot.core import get_logging_provider
from robot.lowlevel.stm32_general import MAX_STEPS_TRAJECTORY
from robot.utilities.buzzer import beep


# === Data Structures ==============================================================================================

@dataclasses.dataclass
class DILC_InitialConditions:
    """Starting pose the robot navigates to before each trial.

    Attributes:
        x: Initial x-position in meters.
        y: Initial y-position in meters.
        psi: Initial heading angle in radians.
    """
    x: float
    y: float
    psi: float


@dataclasses.dataclass
class DILC_Experiment_Meta_Settings:
    """Behavioral settings that control the experiment flow.

    Attributes:
        automatic_initial_conditions_reset: If True, the robot navigates to the initial
            pose before each trial. Set to False for manual positioning.
        check_if_robot_is_static: If True, waits for the robot to be stationary before
            starting a trial. Prevents trajectory injection while the robot is swaying.
        static_timeout_s: Maximum time in seconds to wait for the robot to become
            static before a trial. Only used when check_if_robot_is_static is True.
        auto_start_trials: If True, trials start automatically after the robot is
            prepared (no resume needed). If False, user must send resume to start each trial.
        auto_accept_trials: If True, trial results are accepted automatically (no
            resume/revert needed). If False, user must accept, repeat, or stop each trial.
        enable_psi_control: If True, enables heading (psi) control before each trajectory
            execution and keeps it enabled throughout.
        disable_tracker_during_trajectory: If True, disables the OptiTrack tracker before
            each trajectory and re-enables it after the trajectory finishes. Useful to
            prevent tracker corrections from disturbing the control during injection.
    """
    automatic_initial_conditions_reset: bool = True
    check_if_robot_is_static: bool = True
    static_timeout_s: float = 10.0
    auto_start_trials: bool = False
    auto_accept_trials: bool = False
    enable_psi_control: bool = False
    disable_tracker_during_trajectory: bool = False


@dataclasses.dataclass
class DILC_Requirements:
    """Requirements that must be met before the experiment can start.

    Each requirement defaults to False (not required). Set to True in
    the experiment settings to enforce the check during initialization.
    """
    tracker: bool = False
    timecode: bool = False


@dataclasses.dataclass
class DILC_U0_Params:
    """Parameters for random initial input trajectory generation.

    When u0 is not explicitly provided, these parameters control how
    the random initial input is generated via generate_random_input().

    Attributes:
        f_cutoff: Butterworth cutoff frequency [Hz].
        sigma: Signal amplitude/scaling.
        bias: Constant offset added to the signal.
    """
    f_cutoff: float = 1.5
    sigma: float = 0.2
    bias: float = -0.03


@dataclasses.dataclass
class DILC_Experiment_Settings:
    """Configuration for a DILC experiment.

    Attributes:
        id: Unique experiment identifier.
        description: Human-readable description of the experiment.
        J: Number of trials (learning iterations) to run.
        u0: Initial input trajectory (length N). If None, a random trajectory is generated.
        m0: Initial model / impulse response estimate (length N). If None, zeros are used.
        reference: Reference output trajectory to track (e.g., desired theta profile).
        Ts: Sampling period in seconds (should match the control loop, typically 0.01s).
        initial_conditions: Starting pose for each trial.
        input_lowpass: FIR low-pass filter parameters for the ILC input update (Q_ilc).
        model_lowpass: FIR low-pass filter parameters for the IML model update (Q_iml).
        u0_params: Parameters for random u0 generation (used when u0 is None).
    """
    id: str
    description: str
    J: int
    reference: np.ndarray
    Ts: float
    initial_conditions: DILC_InitialConditions
    input_lowpass: FIR_Design_Params
    model_lowpass: FIR_Design_Params
    initial_conditions_u0: DILC_InitialConditions | None = None
    ilc_gain: float = 1.5
    iml_gain: float = 1.5
    meta: DILC_Experiment_Meta_Settings = dataclasses.field(default_factory=DILC_Experiment_Meta_Settings)
    requirements: DILC_Requirements = dataclasses.field(default_factory=DILC_Requirements)
    u0_params: DILC_U0_Params = dataclasses.field(default_factory=DILC_U0_Params)
    u0: np.ndarray | None = None
    m0: np.ndarray | None = None


@dataclasses.dataclass(frozen=True, kw_only=True)
class DILC_Trial_Meta:
    """Metadata for a single trial."""
    timecode: str | None = None
    tick_start: int | None = None
    tick_end: int | None = None
    time_start: float | None = None
    time_end: float | None = None


@dataclasses.dataclass(frozen=True)
class DILC_Trial_Data:
    """Recorded data and computed updates for a single completed trial.

    Attributes:
        index: Trial index (0-based).
        t: Time vector for this trial.
        u: Input trajectory that was applied during this trial.
        y: Measured output states from the trajectory execution.
        m: Model (impulse response) that was used during this trial.
        e_ilc: Tracking error vector (reference - measured output).
        e_iml: Model prediction error vector (measured - model prediction).
        e_norm_ilc: L2 norm of the tracking error.
        e_norm_iml: L2 norm of the model prediction error.
        u_p1: Updated input trajectory for the next trial.
        m_p1: Updated model for the next trial.
        L_ilc: ILC learning gain matrix that was used for the input update.
        L_iml: IML learning gain matrix that was used for the model update.
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

    meta: DILC_Trial_Meta | None = None
    samples: list[dict] | None = None


class TrialResult(enum.Enum):
    """Outcome of a single trial execution."""
    ERROR = "ERROR"  # Trial failed (hardware error, timeout, user stop)
    REVERT = "REVERT"  # User requested to repeat this trial (discard result)
    FINISHED = "FINISHED"  # Trial completed and ILC/IML update was applied


class DILC_Experiment_State(enum.StrEnum):
    """High-level state machine for the DILC experiment."""
    NONE = "NONE"  # Not yet initialized
    INITIALIZED = "INITIALIZED"  # Initialized and ready to run
    RUNNING = "RUNNING"  # Currently executing trials
    ERROR = "ERROR"  # Stopped due to an error or stop
    FINISHED = "FINISHED"  # All trials completed successfully


class DILC_Phase(enum.StrEnum):
    """Fine-grained phase within a DILC trial.

    Tracks where the experiment is within its trial loop, allowing
    external consumers (e.g. testbed indicators) to react differently
    depending on whether the robot is actively running a trajectory
    vs. repositioning between trials.
    """
    IDLE = "IDLE"                                       # No trial in progress
    PREPARING = "PREPARING"                             # Driving to initial conditions
    WAITING_FOR_START = "WAITING_FOR_START"              # At IC, waiting for user resume
    RUNNING_TRAJECTORY = "RUNNING_TRAJECTORY"            # Trajectory executing
    WAITING_FOR_ACCEPTANCE = "WAITING_FOR_ACCEPTANCE"    # Trajectory done, awaiting review
    COMPUTING_UPDATE = "COMPUTING_UPDATE"                # ILC/IML computation


@dataclasses.dataclass
class DILC_Results_Meta:
    """Metadata recorded alongside experiment results for reproducibility."""
    robot_id: str
    date: str
    robot_config: BILBO_Config
    control_config: BILBO_ControlConfig
    settings: DILC_Experiment_Settings
    logs: list[dict] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class DILC_Results:
    """Complete results of a DILC experiment.

    Contains all trial data plus metadata. On error, contains partial results
    for all trials that were completed before the failure.

    Attributes:
        meta: Experiment metadata (robot config, control config, settings).
        state: Final experiment state (FINISHED or ERROR).
        trials: List of trial data, one entry per completed trial.
    """
    meta: DILC_Results_Meta
    state: DILC_Experiment_State
    trials: list[DILC_Trial_Data]


# === Callbacks & Events ===========================================================================================

@callback_definition
class DILC_Experiment_Callbacks:
    """Synchronous callbacks for GUI and external consumers.

    Register handlers via ``experiment.callbacks.<name>.register(handler)``.
    Callbacks are fired alongside events at each lifecycle transition.
    """
    experiment_started: CallbackContainer
    trajectory_started: CallbackContainer
    trajectory_finished: CallbackContainer
    trial_started: CallbackContainer
    trial_reverted: CallbackContainer
    trial_finished: CallbackContainer
    trial_error: CallbackContainer
    experiment_finished: CallbackContainer
    experiment_error: CallbackContainer


@event_definition
class DILC_Experiment_Events:
    """Asynchronous events for the DILC experiment lifecycle.

    These events can be awaited with ``wait_for_events()`` or subscribed to
    with ``.on()``. All events carry structured dict data for GUI consumption.

    Lifecycle order for a successful experiment::

        experiment_initialized -> experiment_started ->
        [trial_started -> trial_prepared -> trajectory_loaded ->
         trajectory_started -> trajectory_finished -> trial_finished] x J ->
        experiment_finished

    On user repeat: trial_reverted replaces trial_finished for that iteration.
    On error: trial_error and/or experiment_error are emitted.
    """
    # Experiment lifecycle
    experiment_initialized: Event = Event(copy_data_on_set=False)
    experiment_started: Event = Event(copy_data_on_set=False)
    experiment_finished: Event = Event(copy_data_on_set=False)
    experiment_error: Event = Event(copy_data_on_set=False)

    # Trajectory lifecycle (within a trial)
    trajectory_loaded: Event = Event(copy_data_on_set=False)
    trajectory_started: Event = Event(copy_data_on_set=False)
    trajectory_error: Event = Event(copy_data_on_set=False)
    trajectory_finished: Event = Event(copy_data_on_set=False)

    # Trial lifecycle
    trial_started: Event = Event(copy_data_on_set=False)
    trial_prepared: Event = Event(copy_data_on_set=False)
    trial_reverted: Event = Event(copy_data_on_set=False)
    trial_finished: Event = Event(copy_data_on_set=False)
    trial_error: Event = Event(copy_data_on_set=False)


# === WiFi Events ==================================================================================================

# Template: every DILC WiFi event carries a 'group' flag for host-side filtering
_DILC_WIFI_EVENT = WifiEvent(data_type=dict, flags=WifiEventFlag('group', str))


@wifi_event_definition
class DILC_WifiEvents(WifiEventContainer):
    """WiFi events sent by the DILC experiment to the host.

    All events carry a ``group`` flag set to ``'dilc_experiment'`` and include
    common experiment state (trial index, state, etc.) plus event-specific data.
    """
    # Experiment lifecycle
    experiment_initialized: WifiEvent = _DILC_WIFI_EVENT
    experiment_started: WifiEvent = _DILC_WIFI_EVENT
    experiment_finished: WifiEvent = _DILC_WIFI_EVENT
    experiment_error: WifiEvent = _DILC_WIFI_EVENT

    # Trajectory lifecycle (within a trial)
    trajectory_loaded: WifiEvent = _DILC_WIFI_EVENT
    trajectory_started: WifiEvent = _DILC_WIFI_EVENT
    trajectory_error: WifiEvent = _DILC_WIFI_EVENT
    trajectory_finished: WifiEvent = _DILC_WIFI_EVENT

    # Trial lifecycle
    trial_started: WifiEvent = _DILC_WIFI_EVENT
    trial_prepared: WifiEvent = _DILC_WIFI_EVENT
    trial_reverted: WifiEvent = _DILC_WIFI_EVENT
    trial_finished: WifiEvent = _DILC_WIFI_EVENT
    trial_error: WifiEvent = _DILC_WIFI_EVENT

    # Testbed events (forwarded by subclasses with phase filtering)
    limbo_bar_hit: WifiEvent = _DILC_WIFI_EVENT

    # Settings changes (during experiment)
    meta_settings_changed: WifiEvent = _DILC_WIFI_EVENT


# === DILC Experiment ==============================================================================================

class DILC_Experiment:
    """Dual Iterative Learning Control (DILC) experiment.

    Runs a sequence of J trials on the BILBO robot, jointly improving:
      - The input trajectory ``u_j`` (via ILC) to reduce tracking error
      - The system model ``m_j`` (via IML) to improve learning gain accuracy

    Experiment lifecycle and hook points
    =====================================

    The experiment is driven by ``run()``, which calls ``initialize()`` once,
    then loops over ``run_trial()`` for each of the J trials. The base class
    provides five **hook methods** (no-ops by default) that subclasses can
    override to inject behaviour without duplicating the core logic.

    ::

        run()
        ├── initialize()
        │   ├── _check_requirements()
        │   ├── ... (validate settings, build Q-filters, generate u0/m0)
        │   ├── _on_initialize()          ← HOOK: register external resources
        │   └── emit experiment_initialized
        │
        ├── for each trial j = 0 … J-1:
        │   └── run_trial()
        │       ├── emit trial_started
        │       ├── prepare_trial()         (navigate to IC, wait for static)
        │       ├── _on_trial_prepared()   ← HOOK: reset sensors / obstacles
        │       ├── build input trajectory
        │       ├── (wait for user resume, if not auto-start)
        │       ├── execute trajectory (blocking)
        │       ├── _on_after_trajectory() ← HOOK: read sensors → returns extra dict
        │       ├── collect samples
        │       ├── evaluate tracking error
        │       ├── (wait for user accept/repeat/stop, if not auto-accept)
        │       ├── compute ILC + IML updates
        │       ├── _build_trial_data()    ← HOOK: create trial data (subclass type)
        │       └── emit trial_finished
        │
        ├── _build_results() / _save_results_to_file()
        ├── emit experiment_finished / experiment_error
        └── _on_cleanup()                  ← HOOK: release external resources

    ``_on_cleanup()`` is called at **every** exit path (init failure, trial
    error, user abort, and successful completion).

    Hook summary
    ------------
    _on_initialize()
        Called once at the end of ``initialize()``, after Q-filters are built
        but before the ``experiment_initialized`` event is emitted.
        Use: register external resources (e.g. testbed obstacles).

    _on_cleanup()
        Called at every exit of ``run()`` (success, error, abort, init failure).
        Use: release external resources (e.g. remove obstacles from testbed).

    _on_trial_prepared()
        Called after ``prepare_trial()`` returns True, before the input
        trajectory is built. The robot is at the initial conditions.
        Use: reset per-trial sensors or obstacle flags.

    _on_after_trajectory(trajectory_data) → dict
        Called after the trajectory finishes (and psi control / tracker are
        restored), before the ``trajectory_data is None`` check. Receives
        the trajectory result (may be None on failure). The returned dict
        is forwarded to ``_build_trial_data()`` as ``extra_trial_data``.
        Use: read obstacle sensors, evaluate pass/fail conditions.

    _build_trial_data(..., extra_trial_data) → DILC_Trial_Data
        Factory method that creates the trial data object. Override to
        return a subclass of ``DILC_Trial_Data`` with additional fields,
        populated from ``extra_trial_data``.

    Trial flow
    ----------
    Each trial follows this flow:
      1. Navigate the robot to the initial conditions
      2. Wait for user to start the trial (or auto-start)
      3. Apply input trajectory ``u_j`` and record the output ``y_j``
      4. (Optional) Wait for user to accept, repeat, or stop the trial
      5. Compute IML model update: ``m_{j+1}``
      6. Compute ILC input update: ``u_{j+1}``

    The user can review each trial result and choose to:
      - **Accept**: Apply the update and proceed to the next trial
      - **Repeat**: Discard the result and re-run the same trial
      - **Abort**: Stop the experiment entirely

    Args:
        common: Shared robot state and interaction events.
        estimation: State estimation module (for static detection).
        control: Control module (mode switching, position control).
        communication: Communication module (WiFi event transmission).
        interfaces: External input interfaces (joystick disable/enable).
        experiment_handler: Handles trajectory execution on the robot hardware.
        settings: Experiment configuration (reference, filters, number of trials).
    """
    settings: DILC_Experiment_Settings

    common: BILBO_Common
    j: int = 0  # Current trial index (0-based)
    N: int = 0  # Trajectory length (samples)
    trials: list[DILC_Trial_Data]
    state: DILC_Experiment_State = DILC_Experiment_State.NONE

    _u: np.ndarray | None = None  # Current input trajectory
    _m: np.ndarray | None = None  # Current model (impulse response)
    _Q_ilc: np.ndarray | None = None  # ILC Q-filter matrix (N x N)
    _Q_iml: np.ndarray | None = None  # IML Q-filter matrix (N x N)
    t_vector: np.ndarray | None = None  # Time vector [0, Ts, 2Ts, ...]

    _finished: bool = False
    _abort_requested: bool = False

    _WIFI_FLAGS = {'group': 'dilc_experiment'}

    # === INIT =====================================================================================================
    def __init__(self, common: BILBO_Common,
                 estimation: BILBO_Estimation,
                 control: BILBO_Control,
                 communication: BILBO_Communication,
                 interfaces: BILBO_Interfaces,
                 experiment_handler: BILBO_ExperimentHandler,
                 settings: DILC_Experiment_Settings):
        self.common = common
        self.settings = settings
        self.control = control
        self.communication = communication
        self.estimation = estimation
        self.interfaces = interfaces
        self.experiment_handler = experiment_handler

        self.trials = []
        self.phase: DILC_Phase = DILC_Phase.IDLE

        # Runtime-mutable meta settings (initialized from settings in initialize())
        self._auto_start_trials: bool = settings.meta.auto_start_trials
        self._auto_accept_trials: bool = settings.meta.auto_accept_trials

        self.logger = Logger(f"DILC Experiment {self.settings.id}", "DEBUG")
        self.events = DILC_Experiment_Events()
        self.callbacks = DILC_Experiment_Callbacks()

        # Log capture
        self._logs: list[dict] = []
        self._log_capture_enabled = False

        # WiFi events — registered on the interface, sent to the host GUI
        self.wifi_events = DILC_WifiEvents(
            wifi=communication.wifi.wifi,
            id='dilc_experiment',
        )

        self.common.interaction_events.stop.on(self.stop, once=True)

    # === PUBLIC METHODS ===========================================================================================

    def _check_requirements(self):
        """Check all enabled requirements and raise if any are not met."""
        reqs = self.settings.requirements
        errors: list[str] = []

        if reqs.tracker:
            if not self.common.is_tracker_connected():
                errors.append("OptiTrack tracker is not connected")

        if reqs.timecode:
            if self.common.get_timecode() is None:
                errors.append("No timecode received yet")

        if errors:
            msg = "Experiment requirements not met: " + "; ".join(errors)
            self.logger.error(msg)
            raise RuntimeError(msg)

        self.logger.info("All requirements met")

    # ----------------------------------------------------------------------------------------------------------
    def initialize(self):
        """Initialize the experiment: set up trajectories, Q-filters, and state.

        Must be called before ``run()`` (it is called automatically by ``run()``).
        Sets up:
          - Requirement checks (tracker, timecode)
          - Initial input trajectory ``u_0`` (random if not provided)
          - Initial model ``m_0`` (zeros if not provided)
          - Zero-phase FIR Q-filter matrices for robustness

        Emits: ``experiment_initialized``
        Raises: RuntimeError if any enabled requirement is not met.
        """
        self._check_requirements()
        self.N = len(self.settings.reference)

        # Validate trajectory length: STM32 requires a multiple of 10
        if self.N % 10 != 0:
            raise ValueError(
                f"Reference trajectory length N={self.N} is not a multiple of 10. "
                f"The STM32 sequencer requires trajectory lengths that are multiples of 10."
            )

        # Validate trajectory length: must fit in STM32 buffer
        if self.N > MAX_STEPS_TRAJECTORY:
            raise ValueError(
                f"Reference trajectory length N={self.N} exceeds MAX_STEPS_TRAJECTORY={MAX_STEPS_TRAJECTORY}. "
                f"Maximum duration: {MAX_STEPS_TRAJECTORY * self.settings.Ts:.2f}s."
            )

        self.t_vector = generate_time_vector_by_length(num_samples=self.N, dt=self.settings.Ts)
        self.logger.info(f"Trajectory length: N={self.N} samples ({self.N * self.settings.Ts:.2f}s)")

        # --- Initial input trajectory u_0 ---
        if self.settings.u0 is None:
            u0p = self.settings.u0_params
            self.logger.info(f"No initial input u0 provided. Generating random trajectory "
                             f"(f_cutoff={u0p.f_cutoff} Hz, sigma={u0p.sigma}, bias={u0p.bias})")
            self._u = generate_random_input(
                t_vector=self.t_vector,
                f_cutoff=u0p.f_cutoff,
                sigma_I=u0p.sigma,
                bias=u0p.bias
            )
        else:
            self.logger.info("Using provided initial input trajectory u0")
            self._u = self.settings.u0.copy()

        # --- Initial model m_0 (impulse response estimate) ---
        if self.settings.m0 is None:
            self.logger.info("No initial model m0 provided. Starting with zero model.")
            self._m = np.zeros(self.N)
        else:
            self.logger.info("Using provided initial model m0")
            self._m = self.settings.m0.copy()

        self.j = 0

        # --- Build Q-filters for iteration-domain robustness ---
        # These zero-phase FIR low-pass filters suppress high-frequency noise
        # that would otherwise amplify across learning iterations.
        self._Q_iml = self._build_q_filter(self.settings.model_lowpass, "IML model")
        self._Q_ilc = self._build_q_filter(self.settings.input_lowpass, "ILC input")

        self._finished = False
        self._abort_requested = False
        self.trials = []
        self.phase = DILC_Phase.IDLE

        self._on_initialize()

        self.state = DILC_Experiment_State.INITIALIZED
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
        self.logger.info("Experiment initialized successfully")

    # ----------------------------------------------------------------------------------------------------------
    def run(self) -> DILC_Results | None:
        """Run the full DILC experiment.

        Initializes the experiment, then executes all J trials sequentially.
        Handles user interactions (accept, repeat, stop) between trials and
        applies the ILC/IML updates after each accepted trial.

        Returns:
            DILC_Results on completion (includes partial data on error/stop),
            or None if initialization itself fails.

        Emits: ``experiment_started``, then ``experiment_finished`` or ``experiment_error``
        """
        # --- Initialization ---
        try:
            self.initialize()
        except Exception as e:
            self.logger.error(f"Failed to initialize experiment: {e}")
            self.state = DILC_Experiment_State.ERROR
            self.events.experiment_error.set(data={
                'message': f"Initialization failed: {e}",
                'trial_index': 0,
                'completed_trials': 0,
            })
            self.callbacks.experiment_error.call()
            self.wifi_events.experiment_error.send(data={
                **self._wifi_data,
                'message': f"Initialization failed: {e}",
            }, flags=self._WIFI_FLAGS)
            self._on_cleanup()
            return None

        # --- Start ---
        self._start_log_capture()
        self.state = DILC_Experiment_State.RUNNING
        self.logger.info("=" * 60)
        self.logger.info(f"Starting DILC experiment '{self.settings.id}'")
        self.logger.info(f"  Trials: {self.settings.J}")
        self.logger.info(f"  Trajectory length: {self.N} samples ({self.N * self.settings.Ts:.2f}s)")
        self.logger.info(f"  Auto initial conditions: {self.settings.meta.automatic_initial_conditions_reset}")
        self.logger.info(f"  Auto start trials: {self._auto_start_trials}")
        self.logger.info(f"  Auto accept trials: {self._auto_accept_trials}")
        self.logger.info(f"  ILC gain: {self.settings.ilc_gain}")
        self.logger.info(f"  IML gain: {self.settings.iml_gain}")
        self.logger.info(f"  u0: {self._u}")
        self.logger.info("=" * 60)

        self.events.experiment_started.set(data={
            'settings': self.settings,
            'meta': self.settings.meta,
        })
        self.callbacks.experiment_started.call()
        self.wifi_events.experiment_started.send(data={
            **self._wifi_data,
            'N': self.N,
            'duration_s': self.N * self.settings.Ts,
            'auto_initial_conditions': self.settings.meta.automatic_initial_conditions_reset,
        }, flags=self._WIFI_FLAGS)

        # --- Main trial loop ---
        while self.j < self.settings.J:

            # Check for external stop request (e.g., from GUI stop button)
            if self._abort_requested:
                self.logger.warning("Experiment aborted by external request")
                break

            result = self.run_trial()

            if result == TrialResult.FINISHED:
                # Trial accepted and ILC/IML update applied. j was already incremented.
                continue

            elif result == TrialResult.REVERT:
                # User wants to repeat this trial. j stays the same, loop re-runs.
                self.logger.info(f"Trial {self.j + 1} will be repeated")
                continue

            elif result == TrialResult.ERROR:
                # Trial failed. Stop the experiment and return partial results.
                self.phase = DILC_Phase.IDLE
                self.state = DILC_Experiment_State.ERROR
                self._finished = True
                self._stop_log_capture()
                error_msg = f"Experiment stopped: trial {self.j + 1} failed"
                self.logger.error(error_msg)
                self.events.experiment_error.set(data={
                    'message': error_msg,
                    'trial_index': self.j,
                    'completed_trials': len(self.trials),
                })
                self.callbacks.experiment_error.call()
                results = self._build_results()
                results_filepath = self._save_results_to_file(results)
                self.wifi_events.experiment_error.send(data={
                    **self._wifi_data,
                    'message': error_msg,
                    'results_filepath': results_filepath,
                }, flags=self._WIFI_FLAGS)
                beep(frequency='low', repeats=3)
                self._on_cleanup()
                return results

        # --- Post-loop: completed or aborted ---
        self.phase = DILC_Phase.IDLE
        if self._abort_requested:
            self.state = DILC_Experiment_State.ERROR
            self._finished = True
            self._stop_log_capture()
            self.logger.warning(f"Experiment aborted after {len(self.trials)} of {self.settings.J} trials")
            self.events.experiment_error.set(data={
                'message': 'Experiment aborted by user',
                'trial_index': self.j,
                'completed_trials': len(self.trials),
            })
            self.callbacks.experiment_error.call()
            results = self._build_results()
            results_filepath = self._save_results_to_file(results)
            self.wifi_events.experiment_error.send(data={
                **self._wifi_data,
                'message': 'Experiment aborted by user',
                'results_filepath': results_filepath,
            }, flags=self._WIFI_FLAGS)
            self._on_cleanup()
            return results

        # All trials completed successfully
        self.state = DILC_Experiment_State.FINISHED
        self._finished = True
        self._stop_log_capture()
        results = self._build_results()
        results_filepath = self._save_results_to_file(results)

        self.logger.info("=" * 60)
        self.logger.info(f"DILC experiment '{self.settings.id}' completed successfully")
        self.logger.info(f"  Completed trials: {len(self.trials)}/{self.settings.J}")
        if self.trials:
            self.logger.info(f"  Final ILC error norm: {self.trials[-1].e_norm_ilc:.6f}")
            self.logger.info(f"  Final IML error norm: {self.trials[-1].e_norm_iml:.6f}")
            first_ilc = self.trials[0].e_norm_ilc
            last_ilc = self.trials[-1].e_norm_ilc
            if first_ilc > 0:
                self.logger.info(f"  ILC error reduction: {(1 - last_ilc / first_ilc) * 100:.1f}%")
        self.logger.info("=" * 60)

        self.events.experiment_finished.set(data=results)
        self.callbacks.experiment_finished.call()
        self.wifi_events.experiment_finished.send(data={
            **self._wifi_data,
            **self._extra_experiment_finished_wifi_data(),
            'final_e_norm_ilc': float(self.trials[-1].e_norm_ilc) if self.trials else None,
            'final_e_norm_iml': float(self.trials[-1].e_norm_iml) if self.trials else None,
            'error_norms_ilc': [float(t.e_norm_ilc) for t in self.trials],
            'error_norms_iml': [float(t.e_norm_iml) for t in self.trials],
            'results_filepath': results_filepath,
        }, flags=self._WIFI_FLAGS)
        beep(frequency='high', repeats=3)

        self._on_cleanup()
        return results

    # ------------------------------------------------------------------------------------------------------------------
    def run_trial(self) -> TrialResult:
        """Execute a single trial: prepare, run trajectory, compute ILC/IML update.

        Flow:
            1. Emit ``trial_started``
            2. Prepare the robot (navigate to initial conditions, stabilize)
            3. Build and preview the input trajectory
            4. Wait for user to start the trial (resume / stop)
            5. Execute the trajectory on the robot (blocking)
            6. Optionally wait for user to accept / repeat / stop
            7. Compute IML model update and ILC input update
            8. Store trial data and advance to the next trial

        Returns:
            TrialResult.FINISHED if the trial was accepted and the update applied.
            TrialResult.REVERT if the user requested to repeat this trial.
            TrialResult.ERROR if the trial failed or was aborted.

        Emits: ``trial_started``, ``trial_prepared``, ``trajectory_loaded``,
               ``trajectory_started``, ``trajectory_finished`` or ``trajectory_error``,
               ``trial_finished`` or ``trial_error`` or ``trial_reverted``
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info(f"Trial {self.j + 1}/{self.settings.J}")
            self.logger.info("=" * 60)

            self.phase = DILC_Phase.PREPARING

            self.events.trial_started.set(data={
                'trial_index': self.j,
                'total_trials': self.settings.J,
            })
            self.callbacks.trial_started.call()
            self.wifi_events.trial_started.send(data={
                **self._wifi_data,
            }, flags=self._WIFI_FLAGS)

            # --- Step 1: Prepare the robot (navigate to initial conditions) ---
            if not self.prepare_trial():
                self.logger.error("Failed to prepare the trial")
                self.events.trial_error.set(data={
                    'trial_index': self.j,
                    'message': 'Preparation failed',
                })
                self.callbacks.trial_error.call()
                self.wifi_events.trial_error.send(data={
                    **self._wifi_data,
                    'message': 'Preparation failed',
                }, flags=self._WIFI_FLAGS)
                return TrialResult.ERROR

            self._on_trial_prepared()
            self.phase = DILC_Phase.WAITING_FOR_START

            # --- Step 2: Build the input trajectory for this trial ---
            input_trajectory = BILBO_InputTrajectory.from_vector(
                vector=self._u,
                name=f"Trial {self.j + 1}",
                id=self.j + 1,
                delta=self.common.config.model.trajectory_delta,
            )

            self.logger.info(f"Trajectory loaded: {input_trajectory.length} steps, "
                             f"u range: [{self._u.min():.4f}, {self._u.max():.4f}], "
                             f"delta: {self.common.config.model.trajectory_delta}")
            self.events.trajectory_loaded.set(data={
                'trajectory': input_trajectory,
                'trial_index': self.j,
            })
            self.wifi_events.trajectory_loaded.send(data={
                **self._wifi_data,
                'trajectory_length': input_trajectory.length,
                'u_min': float(self._u.min()),
                'u_max': float(self._u.max()),
            }, flags=self._WIFI_FLAGS)

            # --- Step 3: Wait for user to start the trial (unless auto-start) ---
            if self._auto_start_trials:
                self.logger.info("Auto-starting trial (auto_start_trials=True)")
            else:
                self.logger.info("Waiting for user to start the trial... (Resume / Abort)")

                data, trace = wait_for_events(
                    OR(
                        self.common.interaction_events.resume,
                        self.common.interaction_events.stop,
                    ),
                    timeout=60,
                )

                if data is TIMEOUT:
                    self.logger.warning("Timed out waiting for user to start (60s)")
                    self.events.trial_error.set(data={
                        'trial_index': self.j,
                        'message': 'Timeout waiting for user to start trial',
                    })
                    self.callbacks.trial_error.call()
                    self.wifi_events.trial_error.send(data={
                        **self._wifi_data,
                        'message': 'Timeout waiting for user to start trial',
                    }, flags=self._WIFI_FLAGS)
                    return TrialResult.ERROR

                if trace.caused_by(self.common.interaction_events.stop):
                    self.logger.warning("User aborted before trajectory start")
                    self.events.trial_error.set(data={
                        'trial_index': self.j,
                        'message': 'User aborted',
                    })
                    self.callbacks.trial_error.call()
                    self.wifi_events.trial_error.send(data={
                        **self._wifi_data,
                        'message': 'User aborted',
                    }, flags=self._WIFI_FLAGS)
                    return TrialResult.ERROR

            # --- Step 4: Execute the trajectory ---
            self.phase = DILC_Phase.RUNNING_TRAJECTORY
            self.logger.info("Starting trajectory execution...")
            self.interfaces.disable_external_input()
            self.control.disable_external_input()

            if self.settings.meta.enable_psi_control:
                self.control.enable_psi_control(True)

            if self.settings.meta.disable_tracker_during_trajectory:
                self.estimation.set_tracker_updates_enabled(False)

            self.events.trajectory_started.set(data={
                'trajectory': input_trajectory,
                'trial_index': self.j,
            })
            self.callbacks.trajectory_started.call()
            self.wifi_events.trajectory_started.send(data={
                **self._wifi_data,
            }, flags=self._WIFI_FLAGS)

            # Blocking call — the robot executes the full input trajectory
            trajectory_data = self.experiment_handler.run_trajectory(input_trajectory)

            if self.settings.meta.enable_psi_control:
                self.control.enable_psi_control(False)

            if self.settings.meta.disable_tracker_during_trajectory:
                self.estimation.set_tracker_updates_enabled(True)

            # Determine the timecode at which the trajectory started
            trajectory_start_timecode: str | None = None
            if trajectory_data is not None:
                tc = self.common.get_timecode_for_tick(trajectory_data.meta.start_tick)
                if tc is not None:
                    trajectory_start_timecode = tc.to_string()
                    self.logger.info(f"Trajectory start timecode: {trajectory_start_timecode}")

            # Subclass hook: runs after trajectory completes (e.g., read sensors)
            extra_trial_data = self._on_after_trajectory(trajectory_data)
            self.phase = DILC_Phase.WAITING_FOR_ACCEPTANCE

            if trajectory_data is None:
                self.logger.error("Trajectory execution failed (run_trajectory returned None)")
                self.events.trajectory_error.set(data={
                    'trajectory': input_trajectory,
                    'trial_index': self.j,
                })
                self.events.trial_error.set(data={
                    'trial_index': self.j,
                    'message': 'Trajectory execution failed',
                })
                self.callbacks.trial_error.call()
                self.wifi_events.trajectory_error.send(data={
                    **self._wifi_data,
                    'message': 'Trajectory execution failed',
                }, flags=self._WIFI_FLAGS)
                self.wifi_events.trial_error.send(data={
                    **self._wifi_data,
                    'message': 'Trajectory execution failed',
                }, flags=self._WIFI_FLAGS)
                return TrialResult.ERROR

            # --- Step 4b: Collect full samples for offline analysis ---
            # Retrieve all logged samples for the trajectory tick range.
            # These are stored in the trial data and saved to file, but NOT
            # sent over WiFi (too large).
            trial_samples: list | None = None
            try:
                lp = get_logging_provider()
                start_tick = trajectory_data.meta.start_tick
                end_tick = trajectory_data.meta.end_tick
                # Align to multiples of 10 (required by the logging system)
                start_tick_aligned = (start_tick // 10) * 10
                end_tick_aligned = ((end_tick + 9) // 10) * 10
                current_tick = lp.get_tick()
                self.logger.debug(f"Requesting samples: ticks {start_tick_aligned}..{end_tick_aligned}, "
                                  f"current logging tick: {current_tick}")

                # Use async callback to avoid GIL contention from pickle
                # deserialization of the (large) result blocking the main loop.
                import threading
                samples_ready = threading.Event()
                samples_container = [None]

                def _on_samples(data):
                    samples_container[0] = data
                    samples_ready.set()

                lp.get_data(
                    start=start_tick_aligned,
                    end=end_tick_aligned,
                    add_intermediate_samples=True,
                    callback=_on_samples,
                )
                samples_ready.wait(timeout=10.0)
                trial_samples: list = samples_container[0]  # type: ignore

                if trial_samples is not None:
                    self.logger.info(f"Collected {len(trial_samples)} samples "
                                     f"(ticks {start_tick_aligned}..{end_tick_aligned})")
                else:
                    self.logger.warning(f"Failed to retrieve samples from logging provider "
                                        f"(ticks {start_tick_aligned}..{end_tick_aligned}, "
                                        f"current tick: {current_tick})")
            except Exception as e:
                self.logger.warning(f"Could not collect trial samples: {e}")

            # --- Step 5: Extract and evaluate results ---
            theta_trajectory = np.asarray([
                state.theta for state in trajectory_data.data.state_trajectory.states
            ])

            # Handle length mismatch between recorded output and reference
            n_out = len(theta_trajectory)
            if n_out != self.N:
                self.logger.warning(
                    f"Output trajectory length ({n_out}) differs from expected N={self.N}. "
                    f"Delta: {n_out - self.N} samples."
                )
                if n_out > self.N:
                    # More samples than expected — truncate to N
                    theta_trajectory = theta_trajectory[:self.N]
                else:
                    # Fewer samples than expected — pad with last value
                    pad_value = theta_trajectory[-1] if n_out > 0 else 0.0
                    theta_trajectory = np.pad(
                        theta_trajectory, (0, self.N - n_out),
                        mode='constant', constant_values=pad_value,
                    )

            tracking_error = self.settings.reference - theta_trajectory
            error_norm = np.linalg.norm(tracking_error)
            max_abs_error = float(np.max(np.abs(tracking_error)))

            self.logger.info(f"Trajectory finished successfully")
            self.logger.info(f"  Tracking error norm (||r - y||): {error_norm:.6f}")
            self.logger.info(f"  Max absolute error: {max_abs_error:.6f}")

            self.events.trajectory_finished.set(data={
                'trajectory': input_trajectory,
                'trial_index': self.j,
                'theta': theta_trajectory,
                'error': tracking_error,
                'error_norm': error_norm,
            })
            self.callbacks.trajectory_finished.call()
            self.wifi_events.trajectory_finished.send(data={
                **self._wifi_data,
                **extra_trial_data,
                'error_norm': float(error_norm),
                'max_abs_error': max_abs_error,
                'reference': self.settings.reference,
                'theta': theta_trajectory,
                'error': tracking_error,
                'u': self._u,
                't': self.t_vector,
            }, flags=self._WIFI_FLAGS)

            # --- Step 6: Wait for user acceptance (unless auto-accept) ---
            if self._auto_accept_trials:
                self.logger.info(f"Auto-accepting trial {self.j + 1} (error norm: {error_norm:.6f})")
            else:
                self.logger.info("Waiting for user to review... (Accept / Repeat / Abort)")

                data, trace = wait_for_events(
                    OR(
                        self.common.interaction_events.resume,
                        self.common.interaction_events.repeat,
                        self.common.interaction_events.stop,
                    ),
                    timeout=120.0,
                )

                if data is TIMEOUT:
                    self.logger.warning("Timed out waiting for user review (120s)")
                    self.events.trial_error.set(data={
                        'trial_index': self.j,
                        'message': 'Timeout waiting for trial acceptance',
                    })
                    self.callbacks.trial_error.call()
                    self.wifi_events.trial_error.send(data={
                        **self._wifi_data,
                        'message': 'Timeout waiting for trial acceptance',
                    }, flags=self._WIFI_FLAGS)
                    return TrialResult.ERROR

                if trace.caused_by(self.common.interaction_events.stop):
                    self.logger.warning("User aborted after trajectory")
                    self.events.trial_error.set(data={
                        'trial_index': self.j,
                        'message': 'User aborted',
                    })
                    self.callbacks.trial_error.call()
                    self.wifi_events.trial_error.send(data={
                        **self._wifi_data,
                        'message': 'User aborted',
                    }, flags=self._WIFI_FLAGS)
                    return TrialResult.ERROR

                if trace.caused_by(self.common.interaction_events.repeat):
                    self.logger.info(f"User requested to repeat trial {self.j + 1}")
                    self.events.trial_reverted.set(data={
                        'trial_index': self.j,
                        'error_norm': error_norm,
                    })
                    self.callbacks.trial_reverted.call()
                    self.wifi_events.trial_reverted.send(data={
                        **self._wifi_data,
                        'error_norm': float(error_norm),
                    }, flags=self._WIFI_FLAGS)
                    return TrialResult.REVERT

                # User accepted (resume event)
                self.logger.info("Trial accepted by user")

            # --- Step 7: Compute ILC and IML updates ---
            self.phase = DILC_Phase.COMPUTING_UPDATE
            self.logger.info("Computing DILC update...")

            # IML update: improve the model using the prediction error
            # e_iml = y_j - M(m_j) * u_j  where M is the lifted Toeplitz matrix
            error_iml = theta_trajectory - vec2liftedMatrix(self._m) @ self._u
            L_iml = self._compute_iml_learning_matrix(self._u)
            # m_{j+1} = Q_iml * (m_j + L_iml(u_j) * e_iml)
            mp1 = self._Q_iml @ (self._m + L_iml @ error_iml)

            # ILC update: improve the input using the tracking error
            # Note: uses the *updated* model m_{j+1} for the learning gain (dual coupling)
            error_ilc = tracking_error
            L_ilc = self._compute_ilc_learning_matrix(mp1)
            # u_{j+1} = Q_ilc * (u_j + L_ilc(m_{j+1}) * e_ilc)
            up1 = self._Q_ilc @ (self._u + L_ilc @ error_ilc)

            e_norm_ilc = float(np.linalg.norm(error_ilc))
            e_norm_iml = float(np.linalg.norm(error_iml))
            input_change_norm = float(np.linalg.norm(up1 - self._u))
            model_change_norm = float(np.linalg.norm(mp1 - self._m))

            self.logger.info(f"  IML error norm:   {e_norm_iml:.6f}")
            self.logger.info(f"  ILC error norm:   {e_norm_ilc:.6f}")
            self.logger.info(f"  Input change (||u_new - u||): {input_change_norm:.6f}")
            self.logger.info(f"  Model change (||m_new - m||): {model_change_norm:.6f}")

            # --- Step 8: Store trial data ---
            trial_meta = DILC_Trial_Meta(
                timecode=trajectory_start_timecode,
                tick_start=trajectory_data.meta.start_tick,
                tick_end=trajectory_data.meta.end_tick,
                time_start=self.common.get_time_for_tick(trajectory_data.meta.start_tick),
                time_end=self.common.get_time_for_tick(trajectory_data.meta.end_tick),
            )
            trial_data = self._build_trial_data(
                trial_meta=trial_meta,
                theta_trajectory=theta_trajectory,
                tracking_error=tracking_error,
                error_ilc=error_ilc,
                error_iml=error_iml,
                e_norm_ilc=e_norm_ilc,
                e_norm_iml=e_norm_iml,
                up1=up1,
                mp1=mp1,
                L_ilc=L_ilc,
                L_iml=L_iml,
                trial_samples=trial_samples,
                extra_trial_data=extra_trial_data,
            )
            self.trials.append(trial_data)

            # Apply updates for the next trial
            self._u = up1
            self._m = mp1

            self.logger.info(f"Trial {self.j + 1}/{self.settings.J} completed and saved")
            self.events.trial_finished.set(data=trial_data)
            self.callbacks.trial_finished.call()
            self.wifi_events.trial_finished.send(data={
                **self._wifi_data,
                **extra_trial_data,
                'e_norm_ilc': e_norm_ilc,
                'e_norm_iml': e_norm_iml,
                'input_change_norm': input_change_norm,
                'model_change_norm': model_change_norm,
                't': self.t_vector,
                'u': trial_data.u,
                'theta': trial_data.y,
                'm': trial_data.m,
                'e_ilc': error_ilc,
                'e_iml': error_iml,
                'u_p1': up1,
                'm_p1': mp1,
                'reference': self.settings.reference,
            }, flags=self._WIFI_FLAGS)

            self.j += 1
            return TrialResult.FINISHED

        except Exception as e:
            self.logger.error(f"Unexpected error during trial: {e}")
            self.events.trial_error.set(data={
                'trial_index': self.j,
                'message': str(e),
            })
            self.callbacks.trial_error.call()
            self.wifi_events.trial_error.send(data={
                **self._wifi_data,
                'message': str(e),
            }, flags=self._WIFI_FLAGS)
            return TrialResult.ERROR

        finally:
            # Always re-enable external inputs after a trial attempt
            self.interfaces.enable_external_input()
            self.control.enable_external_input()

            self.control.enable_psi_control(False)
            self.estimation.set_tracker_updates_enabled(True)

    # ----------------------------------------------------------------------------------------------------------
    def prepare_trial(self) -> bool:
        """Navigate the robot to the initial conditions and wait for stability.

        Steps:
            1. Ensure BALANCING mode is active
            2. Move to the initial (x, y) position (if auto-reset is enabled)
            3. Turn to the initial heading psi (if auto-reset is enabled)
            4. Enable TIC (Tilt-Integral-Control) for steady balancing
            5. Wait for the robot to become static (if checking is enabled)

        Returns:
            True if preparation succeeded, False otherwise.

        Emits: ``trial_prepared``
        """
        self.logger.info(f"Preparing trial {self.j + 1}/{self.settings.J}...")
        stop = self.common.interaction_events.stop

        # Ensure the robot is in BALANCING mode
        if self.control.mode != BILBO_Control_Mode.BALANCING:
            self.logger.info("Switching to BALANCING mode")
            self.control.set_mode(BILBO_Control_Mode.BALANCING)
            if not interruptible_sleep(1, stop):
                return False

        # Navigate to initial conditions (if enabled)
        if self.settings.meta.automatic_initial_conditions_reset:

            self.control.set_mode(BILBO_Control_Mode.POSITION)
            if not interruptible_sleep(1, stop):
                return False

            # Use separate initial conditions for the first trial (u0 trial) if provided
            if self.j == 0 and self.settings.initial_conditions_u0 is not None:
                ic = self.settings.initial_conditions_u0
                self.logger.info("Using u0-specific initial conditions for first trial")
            else:
                ic = self.settings.initial_conditions
            self.logger.info(f"Navigating to initial conditions: "
                             f"x={ic.x:.3f}m, y={ic.y:.3f}m, psi={np.rad2deg(ic.psi):.1f}deg")

            # Move to the (x, y) position
            result = self.control.position_control.move_to_point(
                x=ic.x,
                y=ic.y,
                blocking=True,
                timeout=10,
            )
            if not result:
                self.logger.error("Failed to reach initial position")
                return False
            self.logger.info("Reached initial position")

            if not interruptible_sleep(0.5, stop):
                return False

            # Turn to the desired heading
            result = self.control.position_control.turn_to_heading(
                heading=ic.psi,
                max_angular_speed=np.deg2rad(180),
                blocking=True,
                timeout=10,
            )
            if not result:
                self.logger.error("Failed to reach initial heading")
                return False
            self.logger.info("Reached initial heading")

            if not interruptible_sleep(1, stop):
                return False
            self.control.set_mode(BILBO_Control_Mode.BALANCING)
            if not interruptible_sleep(0.25, stop):
                return False
            self.logger.info("Reached initial conditions")

        else:
            self.logger.info("Skipping automatic positioning (disabled in meta settings)")

        self.control.enable_tic_control(True)

        # Wait for the robot to be stationary before injecting the trajectory
        if self.settings.meta.check_if_robot_is_static:
            timeout = self.settings.meta.static_timeout_s
            self.logger.info(f"Waiting for robot to become static (timeout={timeout}s)...")
            result = wait_until(
                lambda: self.estimation.static or self._abort_requested,
                timeout_s=timeout,
                poll_period_s=0.25,
            )
            if self._abort_requested:
                return False
            if not result:
                self.logger.error(f"Robot did not become static within {timeout} seconds")
                return False
            self.logger.info("Robot is static and ready")

        # Use separate initial conditions for the first trial (u0 trial) if provided
        if self.j == 0 and self.settings.initial_conditions_u0 is not None:
            ic = self.settings.initial_conditions_u0
        else:
            ic = self.settings.initial_conditions
        self.events.trial_prepared.set(data={
            'trial_index': self.j,
            'initial_conditions': ic,
        })
        self.wifi_events.trial_prepared.send(data={
            **self._wifi_data,
            'x': ic.x,
            'y': ic.y,
            'psi': ic.psi,
            'psi_deg': float(np.rad2deg(ic.psi)),
        }, flags=self._WIFI_FLAGS)
        time.sleep(2)
        self.logger.info("Trial preparation complete")
        return True

    # ----------------------------------------------------------------------------------------------------------
    def stop(self, *args, **kwargs):
        """Request experiment abortion from an external caller (e.g., GUI).

        Sets the stop flag, fires the interaction stop event (to unblock any
        wait_for_events calls), and switches to BALANCING mode to immediately
        interrupt position control moves.
        """
        self._abort_requested = True
        self.logger.warning("Abort requested — interrupting experiment")
        # Switch to BALANCING to cancel any active position control moves
        self.control.set_mode(BILBO_Control_Mode.BALANCING)
        # Fire the interaction stop event to unblock wait_for_events calls
        self.common.interaction_events.stop.set()

    # ----------------------------------------------------------------------------------------------------------
    def set_auto_start_trials(self, value: bool):
        """Enable or disable automatic trial start (no resume needed after preparation).

        Can be called during the experiment to change behavior mid-run.
        """
        self._auto_start_trials = bool(value)
        self.logger.info(f"auto_start_trials set to {self._auto_start_trials}")
        self._send_meta_settings_changed()

    # ----------------------------------------------------------------------------------------------------------
    def set_auto_accept_trials(self, value: bool):
        """Enable or disable automatic trial acceptance (no resume/revert after trial).

        Can be called during the experiment to change behavior mid-run.
        """
        self._auto_accept_trials = bool(value)
        self.logger.info(f"auto_accept_trials set to {self._auto_accept_trials}")
        self._send_meta_settings_changed()

    # === HOOKS (override in subclasses) ==========================================================================

    def _on_initialize(self):
        """Called at the end of initialize(), before events are emitted. Override to add setup."""
        pass

    def _on_cleanup(self):
        """Called at every exit point of run(). Override to release resources."""
        pass

    def _on_trial_prepared(self):
        """Called after prepare_trial() succeeds, before trajectory is built. Override to reset sensors etc."""
        pass

    def _on_after_trajectory(self, trajectory_data) -> dict:
        """Called after the trajectory finishes (even if it failed). Override to read sensors etc.

        Returns:
            Dict of extra data to pass to _build_trial_data(). Empty dict by default.
        """
        return {}

    def _extra_experiment_finished_wifi_data(self) -> dict:
        """Extra fields to include in the experiment_finished WiFi event.

        Override to add subclass-specific summary data (e.g. per-trial hit lists).
        """
        return {}

    def _build_trial_data(self, *, trial_meta, theta_trajectory, tracking_error,
                          error_ilc, error_iml, e_norm_ilc, e_norm_iml,
                          up1, mp1, L_ilc, L_iml, trial_samples,
                          extra_trial_data: dict) -> DILC_Trial_Data:
        """Create the trial data object. Override to return a subclass with extra fields."""
        return DILC_Trial_Data(
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
            meta=trial_meta,
            samples=trial_samples,
        )

    # === PRIVATE METHODS ==========================================================================================

    @property
    def _wifi_data(self) -> dict:
        """Common fields included in every WiFi event."""
        return {
            'state': self.state.value,
            'phase': self.phase.value,
            'experiment_id': self.settings.id,
            'trial_index': self.j,
            'total_trials': self.settings.J,
            'completed_trials': len(self.trials),
            'auto_start_trials': self._auto_start_trials,
            'auto_accept_trials': self._auto_accept_trials,
        }

    # ----------------------------------------------------------------------------------------------------------
    def _send_meta_settings_changed(self):
        """Send a WiFi event notifying the host that meta settings changed."""
        self.wifi_events.meta_settings_changed.send(data={
            **self._wifi_data,
        }, flags=self._WIFI_FLAGS)

    # ----------------------------------------------------------------------------------------------------------
    def _log_capture_callback(self, log_entry: str, log: str, logger: Logger, level: int):
        """Callback for capturing logs during the experiment."""
        lp = get_logging_provider()
        self._logs.append({
            'entry': log_entry.strip(),
            'message': log,
            'logger': logger.name,
            'level': level,
            'tick': lp.get_tick() if lp else 0,
        })

    # ----------------------------------------------------------------------------------------------------------
    def _start_log_capture(self):
        """Enable log redirection to capture logs during experiment."""
        if not self._log_capture_enabled:
            self._logs = []
            enable_redirection(self._log_capture_callback, redirect_all=False)
            self._log_capture_enabled = True

    # ----------------------------------------------------------------------------------------------------------
    def _stop_log_capture(self):
        """Disable log redirection."""
        if self._log_capture_enabled:
            disable_redirection(self._log_capture_callback)
            self._log_capture_enabled = False

    # ----------------------------------------------------------------------------------------------------------
    def _build_results(self) -> DILC_Results:
        """Construct the experiment results object with metadata and all completed trial data."""
        meta = DILC_Results_Meta(
            robot_id=self.common.id,
            date=datetime.now().isoformat(),
            robot_config=self.common.config,
            control_config=self.control.get_control_config(),
            settings=self.settings,
            logs=self._logs,
        )
        return DILC_Results(
            meta=meta,
            state=self.state,
            trials=self.trials,
        )

    def _save_results_to_file(self, results: DILC_Results) -> str | None:
        """Save experiment results to a JSON file on the robot.

        Serialization runs in a subprocess so the GIL is not blocked.

        Args:
            results: The complete experiment results to save.

        Returns:
            The file path if saved successfully, None otherwise.
        """
        from core.utils.json_utils import writeJSON_mp

        experiments_dir = os.path.expanduser("~/robot/experiments")
        os.makedirs(experiments_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"dilc_{self.settings.id}_{timestamp}.json"
        filepath = os.path.join(experiments_dir, filename)

        self.logger.info(f"Saving DILC results to {filepath} ...")
        if writeJSON_mp(filepath, results, convert_dataclass=True):
            self.logger.info(f"Saved DILC results to {filepath}")
            return filepath
        else:
            self.logger.error(f"Failed to save DILC results to {filepath}")
            return None

    # ----------------------------------------------------------------------------------------------------------
    def _build_q_filter(self, params: FIR_Design_Params, label: str) -> np.ndarray:
        """Build a symmetric, DC-normalized zero-phase FIR Q-filter matrix.

        The Q-filter is applied to ILC/IML updates to suppress high-frequency noise
        that would otherwise amplify across iterations. The filter matrix is made
        symmetric ``(Q + Q^T) / 2`` to preserve the zero-phase property, and
        normalized so the DC gain is unity.

        Args:
            params: FIR filter design parameters (cutoff frequency, length, window).
            label: Human-readable label for logging (e.g., "ILC input").

        Returns:
            N x N Q-filter matrix.
        """
        h = design_zero_phase_fir(fc=params.fc, L=params.L, window=params.window)
        Q = build_Qf_zero_padded(h, self.N)

        # Enforce symmetry for the zero-phase property
        Q = 0.5 * (Q + Q.T)

        # Normalize DC gain to unity so the filter doesn't attenuate constant signals
        ones = np.ones(self.N)
        dc_gain = (ones @ (Q @ ones)) / (ones @ ones)
        if abs(dc_gain) > 1e-12:
            Q = Q / dc_gain

        self.logger.info(f"Built {label} Q-filter: fc={params.fc} Hz, L={params.L}, window='{params.window}'")
        return Q

    # ----------------------------------------------------------------------------------------------------------
    def _compute_iml_learning_matrix(self, u_j: np.ndarray) -> np.ndarray:
        """Compute the IML (Iterative Model Learning) learning gain matrix.

        Computes a regularized pseudo-inverse learning matrix from the current
        input trajectory. Maps model prediction errors to model updates::

            L_iml = ( U W U^T + S + jitter )^{-1} U W )^T

        where U = lifted Toeplitz matrix of u_j, W = identity weight matrix,
        and S = regularization term proportional to U^T U.

        Args:
            u_j: Current input trajectory vector of length N.

        Returns:
            N x N learning gain matrix L_iml.
        """
        U = vec2liftedMatrix(u_j)
        W = np.eye(self.N)
        S = self.settings.iml_gain * (U.T @ U + 1e-6 * np.eye(self.N))  # Regularization
        jitter = 1e-8 * np.eye(self.N)  # Numerical stability
        A = U @ W @ U.T + S + jitter
        gain = np.linalg.solve(A, U @ W)
        return gain.T

    # ----------------------------------------------------------------------------------------------------------
    def _compute_ilc_learning_matrix(self, m_j: np.ndarray) -> np.ndarray:
        """Compute the ILC (Iterative Learning Control) learning gain matrix.

        Computes a regularized pseudo-inverse learning matrix from the current
        model estimate. Maps tracking errors to input updates::

            L_ilc = ( M W M^T + S + jitter )^{-1} M W )^T

        where M = lifted Toeplitz matrix of m_j, W = identity weight matrix,
        and S = regularization term proportional to M^T M.

        Args:
            m_j: Current model (impulse response) vector of length N.

        Returns:
            N x N learning gain matrix L_ilc.
        """
        M = vec2liftedMatrix(m_j)
        W = np.eye(self.N)
        S = self.settings.ilc_gain * (M.T @ M + 1e-6 * np.eye(self.N))  # Regularization
        jitter = 1e-8 * np.eye(self.N)  # Numerical stability
        A = M @ W @ M.T + S + jitter
        gain = np.linalg.solve(A, M @ W)
        return gain.T


# === IITL Experiment ==============================================================================================
class IITL_Experiment:
    ...
