"""
Host-side DILC (Dual Iterative Learning Control) experiment proxy.

This module mirrors the robot-side DILC experiment dataclasses and provides a
host-side proxy class that:
  - Sends experiment settings to the robot via WiFi
  - Receives real-time WiFi events from the robot during execution
  - Forwards user interactions (resume, repeat, abort) back to the robot
  - Maintains local state and events for GUI consumption

The actual DILC algorithm runs entirely on the robot (Raspberry Pi). This class
acts as a remote controller and event relay.
"""
import dataclasses
import enum
import json
import os
import shutil
import tempfile
from dataclasses import asdict
from datetime import datetime
import numpy as np

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, Event, pred_flag_equals
from core.utils.logging_utils import Logger
from core.utils.yaml_utils import load_yaml
from robots.bilbo.robot.experiment.experiment_definitions import (
    read_output_file, write_output_file, OutputTrajectoryFileData,
    read_input_file, write_input_file, InputTrajectory,
    read_model_vector_file, write_model_vector_file, ModelVector, ModelVectorFileData,
)
from core.utils.sound.sound import speak
from robots.bilbo.settings import get_settings


# TODO: Add log saving during the experiment
# Add timeout for the whole experiment


@dataclasses.dataclass
class FIR_Design_Params:
    """FIR low-pass filter design parameters for Q-filter construction."""
    fc: float
    L: int
    window: str = "hann"


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
            pose before each trial.
        check_if_robot_is_static: If True, waits for the robot to be stationary before
            starting a trial.
        static_timeout_s: Maximum time in seconds to wait for the robot to become
            static before a trial. Only used when check_if_robot_is_static is True.
        auto_start_trials: If True, trials start automatically after the robot is
            prepared (no resume needed). If False, user must send resume to start each trial.
        auto_accept_trials: If True, trial results are accepted automatically (no
            resume/revert needed). If False, user must accept, repeat, or abort each trial.
        enable_psi_control: If True, enables heading (psi) control before each trajectory.
        disable_tracker_during_trajectory: If True, disables the OptiTrack tracker before
            starting the trajectory and re-enables it after.
    """
    automatic_initial_conditions_reset: bool = True
    check_if_robot_is_static: bool = True
    static_timeout_s: float = 10.0
    auto_start_trials: bool = False
    auto_accept_trials: bool = False
    enable_psi_control: bool = False
    disable_tracker_during_trajectory: bool = False


@dataclasses.dataclass
class DILC_U0_Params:
    """Parameters for random initial input trajectory generation.

    When u0 is not explicitly provided, these parameters control how
    the random initial input is generated on the robot.

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
        reference: Reference output trajectory to track (e.g., desired theta profile).
        Ts: Sampling period in seconds.
        initial_conditions: Starting pose for each trial.
        input_lowpass: FIR low-pass filter parameters for the ILC input update (Q_ilc).
        model_lowpass: FIR low-pass filter parameters for the IML model update (Q_iml).
        meta: Behavioral settings for the experiment flow.
        u0_params: Parameters for random u0 generation (used when u0 is None).
        u0: Initial input trajectory. If None, a random trajectory is generated on the robot.
        m0: Initial model / impulse response estimate. If None, zeros are used.
    """
    id: str
    description: str
    J: int
    reference: np.ndarray | list | str
    Ts: float
    initial_conditions: DILC_InitialConditions
    input_lowpass: FIR_Design_Params
    model_lowpass: FIR_Design_Params
    initial_conditions_u0: DILC_InitialConditions | None = None
    ilc_gain: float = 1.5
    iml_gain: float = 1.5
    meta: DILC_Experiment_Meta_Settings = dataclasses.field(default_factory=DILC_Experiment_Meta_Settings)
    u0_params: DILC_U0_Params = dataclasses.field(default_factory=DILC_U0_Params)
    u0: np.ndarray | list | str | None = None
    m0: np.ndarray | list | str | None = None


# === Trial Data (received from robot events) ===

@dataclasses.dataclass
class DILC_Trial_Result:
    """Summary of a single completed trial, received from robot WiFi events.

    Attributes:
        trial_index: Trial index (0-based).
        e_norm_ilc: L2 norm of the tracking error (reference - output).
        e_norm_iml: L2 norm of the model prediction error.
        input_change_norm: L2 norm of the input change (||u_new - u_old||).
        model_change_norm: L2 norm of the model change (||m_new - m_old||).
    """
    trial_index: int
    e_norm_ilc: float
    e_norm_iml: float
    input_change_norm: float
    model_change_norm: float


@dataclasses.dataclass
class DILC_Trajectory_Data:
    """Trajectory data from a single trajectory execution (received via WiFi)."""
    trial_index: int
    error_norm: float
    max_abs_error: float
    reference: list[float]
    theta: list[float]
    error: list[float]
    u: list[float]
    t: list[float]


@dataclasses.dataclass
class DILC_Trial_Data:
    """Full trial data received via WiFi (superset of DILC_Trial_Result).

    Array fields are None when received from older robots that only send scalars.
    """
    trial_index: int
    e_norm_ilc: float
    e_norm_iml: float
    input_change_norm: float
    model_change_norm: float
    t: list[float] | None = None
    u: list[float] | None = None
    theta: list[float] | None = None
    m: list[float] | None = None
    e_ilc: list[float] | None = None
    e_iml: list[float] | None = None
    u_p1: list[float] | None = None
    m_p1: list[float] | None = None
    reference: list[float] | None = None
    samples: list[dict] | None = None


@dataclasses.dataclass
class DILC_Results_Meta:
    """Metadata from the full DILC results file."""
    robot_id: str
    date: str
    robot_config: dict
    control_config: dict
    settings: dict
    logs: list[dict] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class DILC_Results:
    """Complete DILC results downloaded from robot JSON file."""
    meta: DILC_Results_Meta
    state: str
    trials: list[dict]


# === State ===

class DILC_Experiment_State(enum.StrEnum):
    """High-level state machine for the host-side DILC experiment proxy."""
    NONE = "NONE"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    FINISHED = "FINISHED"


# === Events ===

@event_definition
class DILC_Experiment_Events:
    """Asynchronous events mirroring the robot-side DILC experiment lifecycle.

    These events are fired when the corresponding WiFi event is received from the robot.
    """
    # Experiment lifecycle
    experiment_initialized: Event = Event(copy_data_on_set=False)
    experiment_started: Event = Event(copy_data_on_set=False)
    experiment_finished: Event = Event(copy_data_on_set=False)
    experiment_error: Event = Event(copy_data_on_set=False)

    # Trial lifecycle
    trial_started: Event = Event(copy_data_on_set=False)
    trial_prepared: Event = Event(copy_data_on_set=False)
    trial_finished: Event = Event(copy_data_on_set=False)
    trial_reverted: Event = Event(copy_data_on_set=False)
    trial_error: Event = Event(copy_data_on_set=False)

    # Trajectory lifecycle (within a trial)
    trajectory_loaded: Event = Event(copy_data_on_set=False)
    trajectory_started: Event = Event(copy_data_on_set=False)
    trajectory_finished: Event = Event(copy_data_on_set=False)
    trajectory_error: Event = Event(copy_data_on_set=False)

    # Settings changes (during experiment)
    meta_settings_changed: Event = Event(copy_data_on_set=False)


# === Callbacks ===

@callback_definition
class DILC_Experiment_Callbacks:
    """Synchronous callbacks for GUI and external consumers."""
    experiment_initialized: CallbackContainer
    experiment_started: CallbackContainer
    experiment_finished: CallbackContainer
    experiment_error: CallbackContainer
    trial_started: CallbackContainer
    trial_finished: CallbackContainer
    trial_reverted: CallbackContainer
    trial_error: CallbackContainer
    trajectory_started: CallbackContainer
    trajectory_finished: CallbackContainer
    meta_settings_changed: CallbackContainer


# === Main Class ===

class DILC_Experiment:
    """Host-side proxy for a DILC experiment running on the robot.

    This class does not run the DILC algorithm itself. Instead, it:
      - Serializes experiment settings and sends them to the robot via WiFi
      - Subscribes to WiFi events from the robot and relays them as local events
      - Provides methods for user interactions (resume, repeat, abort)
      - Maintains local state for GUI consumption

    Args:
        core: The host-side BILBO_Core instance providing device communication.
    """

    settings: DILC_Experiment_Settings | None
    state: DILC_Experiment_State
    trials: list[DILC_Trial_Data]

    def __init__(self, core):
        self.core = core
        self.device = core.device
        self.logger = Logger("DILC Experiment (Host)")

        self.settings = None
        self.state = DILC_Experiment_State.NONE
        self.trials = []
        self.last_trajectory_data: DILC_Trajectory_Data | None = None
        self.results: DILC_Results | None = None
        self._yaml_file_path: str | None = None
        self._run_id: str | None = None  # Full experiment run ID (e.g. dilc_test_2026-02-13_14-30-00)
        self._run_dir: str | None = None  # Subfolder for this run's artifacts

        # Runtime meta settings (updated from robot WiFi events)
        self.auto_start_trials: bool = False
        self.auto_accept_trials: bool = False

        # Load reference trajectory directory from host settings
        host_settings = get_settings()
        self.reference_trajectory_dir: str | None = (host_settings.get('paths') or {}).get('reference_trajectories')

        self.events = DILC_Experiment_Events()
        self.callbacks = DILC_Experiment_Callbacks()

        # Subscribe to WiFi events from the robot's DILC experiment
        self._event_listener = self.device.events.event.on(
            self._handle_dilc_event,
            predicate=pred_flag_equals('container', 'dilc_experiment'),
        )

    # === Configuration =================================================================

    def configure(self, settings: DILC_Experiment_Settings):
        """Configure the experiment with the given settings.

        If settings.reference is a string, it is treated as a file path to an
        output trajectory file (.botrj) and loaded automatically.

        If settings.u0 is a string, it is treated as a file path to an
        input trajectory file (.bitrj) and loaded automatically.

        If settings.m0 is a string, it is treated as a file path to a model
        vector file (.bmvec) and loaded automatically.

        Args:
            settings: The experiment settings to use.
        """
        # Resolve reference from file path if needed.
        # Note: from_dict_auto may wrap a string in a 0-d ndarray when the type
        # hint is np.ndarray|list|str — unwrap it before the isinstance check.
        ref = settings.reference
        if isinstance(ref, np.ndarray) and ref.ndim == 0:
            ref = str(ref)
        if isinstance(ref, str):
            file_data = read_output_file(ref)
            settings.reference = file_data.to_array()
        elif isinstance(ref, list):
            settings.reference = np.asarray(ref)
        elif isinstance(ref, np.ndarray):
            settings.reference = ref
        else:
            raise TypeError(f"Unexpected reference type: {type(ref)}")

        # Resolve u0 from file path if needed (same unwrapping as reference).
        u0 = settings.u0
        if isinstance(u0, np.ndarray) and u0.ndim == 0:
            u0 = str(u0)
        if isinstance(u0, str):
            file_data = read_input_file(u0)
            settings.u0 = file_data.trajectory.to_vector(single_input=True)
        elif isinstance(u0, list):
            settings.u0 = np.asarray(u0)
        elif isinstance(u0, np.ndarray) or u0 is None:
            pass  # already correct
        else:
            raise TypeError(f"Unexpected u0 type: {type(u0)}")

        # Resolve m0 from file path if needed (same unwrapping as reference).
        m0 = settings.m0
        if isinstance(m0, np.ndarray) and m0.ndim == 0:
            m0 = str(m0)
        if isinstance(m0, str):
            file_data = read_model_vector_file(m0)
            settings.m0 = file_data.to_array()
        elif isinstance(m0, list):
            settings.m0 = np.asarray(m0)
        elif isinstance(m0, np.ndarray) or m0 is None:
            pass  # already correct
        else:
            raise TypeError(f"Unexpected m0 type: {type(m0)}")

        self.settings = settings
        self.state = DILC_Experiment_State.INITIALIZED
        self.trials = []
        self.last_trajectory_data = None
        self.results = None
        self.auto_start_trials = settings.meta.auto_start_trials
        self.auto_accept_trials = settings.meta.auto_accept_trials
        self.logger = Logger(f"DILC Experiment \"{settings.id}\" (Host)")
        self.logger.info(f"Configured: {settings.J} trials, Ts={settings.Ts}s, "
                         f"N={len(settings.reference)} samples")

        self.events.experiment_initialized.set(data={
            'id': settings.id,
            'J': settings.J,
            'N': len(settings.reference),
            'Ts': settings.Ts,
            'duration_s': len(settings.reference) * settings.Ts,
        })
        self.callbacks.experiment_initialized.call()

    def configure_from_yaml(self, file_path: str):
        """Load experiment settings from a YAML file and configure.

        If the ``reference`` field is a string (file path), it is resolved in order:
          1. Relative to the YAML file's directory
          2. Inside ``self.reference_trajectory_dir`` (if set)
          3. As-is (will fail in ``configure()`` if not found)

        The same resolution order applies to ``u0`` (path to a ``.bitrj``
        input trajectory file) and ``m0`` (path to a ``.bmvec`` model vector
        file) when given as strings.

        Args:
            file_path: Path to the YAML configuration file.
        """
        yaml_data = load_yaml(file_path)
        settings = from_dict_auto(DILC_Experiment_Settings, yaml_data)

        yaml_dir = os.path.dirname(os.path.abspath(file_path))

        # from_dict_auto wraps strings in 0-d ndarray when the type hint
        # includes np.ndarray — unwrap so path resolution works correctly.
        if isinstance(settings.reference, np.ndarray) and settings.reference.ndim == 0:
            settings.reference = str(settings.reference)

        # Resolve relative reference path
        if isinstance(settings.reference, str) and not os.path.isabs(settings.reference):
            candidate = os.path.join(yaml_dir, settings.reference)

            if os.path.isfile(candidate):
                settings.reference = candidate  # type: ignore
            elif self.reference_trajectory_dir and os.path.isfile(
                    os.path.join(self.reference_trajectory_dir, settings.reference)):
                settings.reference = os.path.join(self.reference_trajectory_dir, settings.reference)  # type: ignore
            else:
                # Fall through with the yaml-relative path (will error in configure if missing)
                settings.reference = candidate  # type: ignore

        # Unwrap and resolve u0 file path (same logic as reference)
        if isinstance(settings.u0, np.ndarray) and settings.u0.ndim == 0:
            settings.u0 = str(settings.u0)

        if isinstance(settings.u0, str) and not os.path.isabs(settings.u0):
            candidate = os.path.join(yaml_dir, settings.u0)

            if os.path.isfile(candidate):
                settings.u0 = candidate  # type: ignore
            elif self.reference_trajectory_dir and os.path.isfile(
                    os.path.join(self.reference_trajectory_dir, settings.u0)):
                settings.u0 = os.path.join(self.reference_trajectory_dir, settings.u0)  # type: ignore
            else:
                settings.u0 = candidate  # type: ignore

        # Unwrap and resolve m0 file path (same logic as reference)
        if isinstance(settings.m0, np.ndarray) and settings.m0.ndim == 0:
            settings.m0 = str(settings.m0)

        if isinstance(settings.m0, str) and not os.path.isabs(settings.m0):
            candidate = os.path.join(yaml_dir, settings.m0)

            if os.path.isfile(candidate):
                settings.m0 = candidate  # type: ignore
            elif self.reference_trajectory_dir and os.path.isfile(
                    os.path.join(self.reference_trajectory_dir, settings.m0)):
                settings.m0 = os.path.join(self.reference_trajectory_dir, settings.m0)  # type: ignore
            else:
                settings.m0 = candidate  # type: ignore

        self.configure(settings)
        self._yaml_file_path = os.path.abspath(file_path)

    # === Experiment Control ============================================================

    def start(self) -> bool:
        """Start the DILC experiment on the robot.

        Serializes the current settings and sends them to the robot via the
        ``run_dilc_experiment`` WiFi command. The robot will then run the
        experiment autonomously, sending WiFi events back for each lifecycle step.

        Returns:
            True if the command was sent successfully, False otherwise.
        """
        if self.settings is None:
            self.logger.error("Cannot start: no settings configured")
            return False

        if self.state not in (DILC_Experiment_State.INITIALIZED, DILC_Experiment_State.FINISHED,
                              DILC_Experiment_State.ERROR, DILC_Experiment_State.NONE):
            self.logger.warning(f"Cannot start: experiment is in state {self.state}")
            return False

        settings_dict = self._serialize_settings()
        self.state = DILC_Experiment_State.RUNNING
        self.trials = []

        # Generate a unique run ID and create a subfolder for this run's artifacts
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._run_id = f"dilc_{self.settings.id}_{timestamp}"
        self._run_dir = None

        if self._yaml_file_path:
            yaml_dir = os.path.dirname(self._yaml_file_path)
            self._run_dir = os.path.join(yaml_dir, self._run_id)
            os.makedirs(self._run_dir, exist_ok=True)
            # Copy the YAML config into the run folder
            try:
                shutil.copy2(self._yaml_file_path, self._run_dir)
                self.logger.info(f"Copied YAML config to {self._run_dir}")
            except Exception as e:
                self.logger.warning(f"Failed to copy YAML config: {e}")
            # Save the reference trajectory
            try:
                ref_path = os.path.join(self._run_dir, "reference.botrj")
                ref_data = OutputTrajectoryFileData(
                    id=self.settings.id,
                    description=self.settings.description,
                    output_name='theta',
                    output=np.asarray(self.settings.reference).tolist(),
                    dt=self.settings.Ts,
                )
                write_output_file(ref_path, ref_data)
                self.logger.info(f"Saved reference trajectory to {ref_path}")
            except Exception as e:
                self.logger.warning(f"Failed to save reference trajectory: {e}")
            # Save the initial model vector (m0) if provided
            if self.settings.m0 is not None:
                try:
                    m0_model = ModelVector.from_vector(
                        vector=np.asarray(self.settings.m0),
                        name="m0",
                        id=0,
                        dt=self.settings.Ts,
                    )
                    m0_file_data = m0_model.to_file_data(
                        id=self.settings.id,
                        description="Initial model vector (m0)",
                    )
                    m0_path = os.path.join(self._run_dir, "m0.bmvec")
                    write_model_vector_file(m0_path, m0_file_data)
                    self.logger.info(f"Saved initial model vector to {m0_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to save initial model vector: {e}")
            # Save the initial input trajectory (u0) if provided
            if self.settings.u0 is not None:
                try:
                    u0_trajectory = InputTrajectory.from_vector(
                        vector=np.asarray(self.settings.u0),
                        name="u0",
                        id=0,
                        dt=self.settings.Ts,
                    )
                    u0_file_data = u0_trajectory.to_file_data(
                        id=self.settings.id,
                        description="Initial input trajectory (u0)",
                    )
                    write_input_file("u0", self._run_dir, u0_file_data)
                    self.logger.info(f"Saved initial input trajectory to {self._run_dir}/u0.bitrj")
                except Exception as e:
                    self.logger.warning(f"Failed to save initial input trajectory: {e}")

        self.logger.info(f"Experiment run ID: {self._run_id}")
        self.logger.info("Sending experiment settings to robot...")

        self.device.executeFunction(
            function_name='run_dilc_experiment',
            arguments={'settings': settings_dict},
        )
        self.logger.info("Experiment start command sent")
        return True

    def start_blocking(self, timeout: float = None) -> bool:
        """Start the experiment and wait for it to finish.

        Args:
            timeout: Maximum time to wait in seconds. None for no timeout.

        Returns:
            True if the experiment finished successfully, False on error or timeout.
        """
        if not self.start():
            return False

        from core.utils.events import wait_for_events, OR, TIMEOUT
        data, trace = wait_for_events(
            OR(self.events.experiment_finished, self.events.experiment_error),
            timeout=timeout,
        )

        if data is TIMEOUT:
            self.logger.error("Experiment timed out")
            return False

        return trace.caused_by(self.events.experiment_finished)

    def resume(self):
        """Send resume command to the robot (accept trial / start trajectory)."""
        self.logger.info("Sending resume command")
        self.device.executeFunction('resume', arguments={'data': {}})

    def repeat(self):
        """Send repeat command to the robot (discard trial and re-run)."""
        self.logger.info("Sending repeat command")
        self.device.executeFunction('repeat', arguments={'data': {}})

    def stop(self):
        """Send stop command to the robot (robot-side handles BALANCING switch)."""
        self.logger.warning("Sending stop command")
        self.device.executeFunction('stop', arguments={'data': {}})

    def close(self):
        """Unsubscribe from device events. Call before discarding this instance."""
        if self._event_listener is not None:
            self._event_listener.stop()
            self._event_listener = None

    def set_auto_start_trials(self, value: bool):
        """Send command to robot to enable/disable auto-start of trials."""
        self.logger.info(f"Setting auto_start_trials to {value}")
        self.device.executeFunction('set_dilc_auto_start_trials', arguments={'value': bool(value)})

    def set_auto_accept_trials(self, value: bool):
        """Send command to robot to enable/disable auto-accept of trials."""
        self.logger.info(f"Setting auto_accept_trials to {value}")
        self.device.executeFunction('set_dilc_auto_accept_trials', arguments={'value': bool(value)})

    def generate_report(self, output: str | None = None, format: str = 'html', show: bool = True):
        """Generate an HTML/PDF report for this DILC experiment.

        Uses the downloaded DILC_Results if available, otherwise falls back
        to the WiFi-received trial data.

        Args:
            output: Output file path. If None and show=True, opens in viewer.
            format: Output format: 'html' or 'pdf'.
            show: If True and output is None, opens the report in a viewer.
        """
        from robots.bilbo.robot.experiment.dilc.dilc_helpers import generate_dilc_report

        self.logger.info("Generating DILC report...")
        try:
            return generate_dilc_report(self, output=output, format=format, show=show)
        except Exception as e:
            self.logger.error(f"Failed to generate report: {e}")
            raise

    # === WiFi Event Handler ============================================================

    def _handle_dilc_event(self, event_data, **kwargs):
        """Handle incoming WiFi events from the robot's DILC experiment.

        Routes events by name to update local state, store trial results,
        and fire corresponding local events and callbacks.
        """
        data = event_data.get('data', {}) or {}
        event_name = event_data.get('event', '')

        # Update state from common fields
        remote_state = data.get('state', None)
        if remote_state:
            try:
                self.state = DILC_Experiment_State(remote_state)
            except ValueError:
                pass

        # Track runtime meta settings from every event (included in _wifi_data)
        if 'auto_start_trials' in data:
            self.auto_start_trials = data['auto_start_trials']
        if 'auto_accept_trials' in data:
            self.auto_accept_trials = data['auto_accept_trials']

        trial_index = data.get('trial_index', None)
        total_trials = data.get('total_trials', None)

        # Route by event name
        if event_name == 'experiment_initialized':
            self.logger.info(f"Robot: experiment initialized (N={data.get('N')}, "
                             f"duration={data.get('duration_s', 0):.2f}s)")
            self.events.experiment_initialized.set(data=data)

        elif event_name == 'experiment_started':
            self.logger.info(f"Robot: experiment started")
            self.state = DILC_Experiment_State.RUNNING
            speak(f"Starting DILC experiment with {total_trials} trials")
            self.events.experiment_started.set(data=data)
            self.callbacks.experiment_started.call()

        elif event_name == 'experiment_finished':
            self.logger.info(f"Robot: experiment finished")
            self.state = DILC_Experiment_State.FINISHED

            speak("Experiment finished successfully")

            results_filepath = data.get('results_filepath')
            if results_filepath:
                self._download_and_save_results(results_filepath)

            self._save_best_input()
            self._save_best_model()
            self._auto_generate_report()

            self.events.experiment_finished.set(data=data)
            self.callbacks.experiment_finished.call()

        elif event_name == 'experiment_error':
            msg = data.get('message', 'Unknown error')
            self.logger.error(f"Robot: experiment error — {msg}")
            self.state = DILC_Experiment_State.ERROR

            speak("Experiment failed")

            results_filepath = data.get('results_filepath')
            if results_filepath:
                self._download_and_save_results(results_filepath)

            self._auto_generate_report()

            self.events.experiment_error.set(data=data)
            self.callbacks.experiment_error.call()

        elif event_name == 'trial_started':
            self.logger.info(f"Robot: trial {(trial_index or 0) + 1}/{total_trials} started")
            speak(f"Trial {(trial_index or 0) + 1} of {total_trials}")
            self.events.trial_started.set(data=data)
            self.callbacks.trial_started.call()

        elif event_name == 'trial_prepared':
            self.logger.info(f"Robot: trial {(trial_index or 0) + 1}/{total_trials} prepared")
            self.events.trial_prepared.set(data=data)

        elif event_name == 'trial_finished':
            e_norm_ilc = data.get('e_norm_ilc', 0)
            e_norm_iml = data.get('e_norm_iml', 0)
            input_change = data.get('input_change_norm', 0)
            model_change = data.get('model_change_norm', 0)

            trial_data = DILC_Trial_Data(
                trial_index=trial_index or 0,
                e_norm_ilc=e_norm_ilc,
                e_norm_iml=e_norm_iml,
                input_change_norm=input_change,
                model_change_norm=model_change,
                t=data.get('t'),
                u=data.get('u'),
                theta=data.get('theta'),
                m=data.get('m'),
                e_ilc=data.get('e_ilc'),
                e_iml=data.get('e_iml'),
                u_p1=data.get('u_p1'),
                m_p1=data.get('m_p1'),
                reference=data.get('reference'),
            )
            self.trials.append(trial_data)

            self.logger.info(f"Robot: trial {(trial_index or 0) + 1}/{total_trials} finished "
                             f"(e_ilc={e_norm_ilc:.6f}, e_iml={e_norm_iml:.6f})")
            speak(f"Trial {(trial_index or 0) + 1} finished")
            self.events.trial_finished.set(data=data)
            self.callbacks.trial_finished.call()

        elif event_name == 'trial_reverted':
            self.logger.info(f"Robot: trial {(trial_index or 0) + 1}/{total_trials} reverted")
            self.events.trial_reverted.set(data=data)
            self.callbacks.trial_reverted.call()

        elif event_name == 'trial_error':
            msg = data.get('message', 'Unknown error')
            self.logger.error(f"Robot: trial error — {msg}")
            self.events.trial_error.set(data=data)
            self.callbacks.trial_error.call()

        elif event_name == 'trajectory_loaded':
            self.logger.info(f"Robot: trajectory loaded")
            self.events.trajectory_loaded.set(data=data)

        elif event_name == 'trajectory_started':
            self.logger.info(f"Robot: trajectory started")
            self.events.trajectory_started.set(data=data)
            self.callbacks.trajectory_started.call()

        elif event_name == 'trajectory_finished':
            error_norm = data.get('error_norm', 0)
            self.logger.info(f"Robot: trajectory finished (error_norm={error_norm:.6f})")

            if data.get('reference') is not None:
                self.last_trajectory_data = DILC_Trajectory_Data(
                    trial_index=trial_index or 0,
                    error_norm=error_norm,
                    max_abs_error=data.get('max_abs_error', 0),
                    reference=data.get('reference', []),
                    theta=data.get('theta', []),
                    error=data.get('error', []),
                    u=data.get('u', []),
                    t=data.get('t', []),
                )

            self.events.trajectory_finished.set(data=data)
            self.callbacks.trajectory_finished.call()

        elif event_name == 'trajectory_error':
            self.logger.error(f"Robot: trajectory error")
            self.events.trajectory_error.set(data=data)

        elif event_name == 'meta_settings_changed':
            self.auto_start_trials = data.get('auto_start_trials', self.auto_start_trials)
            self.auto_accept_trials = data.get('auto_accept_trials', self.auto_accept_trials)
            self.logger.info(f"Robot: meta settings changed — "
                             f"auto_start={self.auto_start_trials}, auto_accept={self.auto_accept_trials}")
            self.events.meta_settings_changed.set(data=data)
            self.callbacks.meta_settings_changed.call()

        else:
            self.logger.warning(f"Unknown DILC event: {event_name}")

    # === Results Download ==============================================================

    def _download_and_save_results(self, remote_filepath: str):
        """Download DILC results JSON from the robot and parse into DILC_Results.

        Args:
            remote_filepath: The remote file path on the robot (e.g., ~/robot/experiments/...).
        """
        if not hasattr(self.core, 'file_handler') or self.core.file_handler is None:
            self.logger.warning("No file handler available — skipping results download")
            return

        download_dir = (self._run_dir
                        or (os.path.dirname(self._yaml_file_path) if self._yaml_file_path else None)
                        or tempfile.gettempdir())

        try:
            local_filepath = self.core.file_handler.download_file(remote_filepath, download_dir)
            self.logger.info(f"DILC results downloaded to: {local_filepath}")

            with open(local_filepath, 'r') as f:
                results_dict = json.load(f)

            self.results = DILC_Results(
                meta=from_dict_auto(DILC_Results_Meta, results_dict.get('meta', {})),
                state=results_dict.get('state', 'UNKNOWN'),
                trials=results_dict.get('trials', []),
            )
            self.logger.info(f"Loaded {len(self.results.trials)} trials, state={self.results.state}")
        except Exception as e:
            self.logger.error(f"Failed to download/parse DILC results: {e}")

    # === Best Input Extraction ========================================================

    def _save_best_input(self):
        """Save the input trajectory from the trial with the lowest ILC error norm."""
        if not self._run_dir:
            return

        # Prefer full results from JSON (has u arrays); fall back to WiFi trial data
        trials = (self.results.trials if self.results and self.results.trials else None)
        if trials is None and self.trials:
            trials = [dataclasses.asdict(t) for t in self.trials]
        if not trials:
            self.logger.debug("No trial data available — skipping best input save")
            return

        try:
            best_trial = min(trials, key=lambda t: t.get('e_norm_ilc', float('inf')))
            u = best_trial.get('u')
            if u is None:
                self.logger.warning("Best trial has no input trajectory data — skipping")
                return

            best_index = best_trial.get('trial_index', best_trial.get('index', '?'))
            e_norm = best_trial.get('e_norm_ilc', 0)
            self.logger.info(f"Best trial: {int(best_index) + 1} (e_norm_ilc={e_norm:.6f})")

            trajectory = InputTrajectory.from_vector(
                vector=np.asarray(u),
                name=f"best_u (trial {int(best_index) + 1})",
                id=int(best_index) + 1,
                dt=self.settings.Ts if self.settings else 0.01,
            )
            file_data = trajectory.to_file_data(
                id=self.settings.id if self.settings else 'dilc',
                description=f"Best input trajectory (trial {int(best_index) + 1}, e_norm_ilc={e_norm:.6f})",
            )
            file_name = self._run_id or "best_input"
            write_input_file(file_name, self._run_dir, file_data)
            self.logger.info(f"Saved best input trajectory to {self._run_dir}/{file_name}.bitrj")
        except Exception as e:
            self.logger.warning(f"Failed to save best input trajectory: {e}")

    def _save_best_model(self):
        """Save the model vector from the trial with the lowest IML error norm."""
        if not self._run_dir:
            return

        # Prefer full results from JSON (has m arrays); fall back to WiFi trial data
        trials = (self.results.trials if self.results and self.results.trials else None)
        if trials is None and self.trials:
            trials = [dataclasses.asdict(t) for t in self.trials]
        if not trials:
            self.logger.debug("No trial data available — skipping best model save")
            return

        try:
            best_trial = min(trials, key=lambda t: t.get('e_norm_iml', float('inf')))
            m = best_trial.get('m')
            if m is None:
                self.logger.warning("Best trial has no model vector data — skipping")
                return

            best_index = best_trial.get('trial_index', best_trial.get('index', '?'))
            e_norm = best_trial.get('e_norm_iml', 0)
            self.logger.info(f"Best model trial: {int(best_index) + 1} (e_norm_iml={e_norm:.6f})")

            model = ModelVector.from_vector(
                vector=np.asarray(m),
                name=f"best_m (trial {int(best_index) + 1})",
                id=int(best_index) + 1,
                dt=self.settings.Ts if self.settings else 0.01,
            )
            file_data = model.to_file_data(
                id=self.settings.id if self.settings else 'dilc',
                description=f"Best model vector (trial {int(best_index) + 1}, e_norm_iml={e_norm:.6f})",
            )
            file_path = os.path.join(self._run_dir, f"{self._run_id or 'best_model'}.bmvec")
            write_model_vector_file(file_path, file_data)
            self.logger.info(f"Saved best model vector to {file_path}")
        except Exception as e:
            self.logger.warning(f"Failed to save best model vector: {e}")

    # === Auto Report ==================================================================

    def _auto_generate_report(self):
        """Auto-generate an HTML report in the run subfolder (or YAML directory as fallback)."""
        if not self._yaml_file_path:
            self.logger.debug("No YAML file path — skipping auto report")
            return

        if self.results is None and not self.trials:
            self.logger.debug("No results or trials available — skipping auto report")
            return

        try:
            report_dir = self._run_dir or os.path.dirname(self._yaml_file_path)
            report_name = f"{self._run_id}.html" if self._run_id else "dilc_report.html"
            report_path = os.path.join(report_dir, report_name)

            self.generate_report(output=report_path, format='html', show=True)
            self.logger.info(f"Auto-generated report: {report_path}")
        except Exception as e:
            self.logger.warning(f"Failed to auto-generate report: {e}")

    # === Serialization =================================================================

    def _serialize_settings(self) -> dict:
        """Convert DILC_Experiment_Settings to a JSON-serializable dict.

        Handles numpy arrays by converting them to lists.
        """
        settings = self.settings

        def convert_value(v):
            if isinstance(v, np.ndarray):
                return v.tolist()
            if isinstance(v, dict):
                return {k: convert_value(val) for k, val in v.items()}
            if isinstance(v, (list, tuple)):
                return [convert_value(item) for item in v]
            return v

        settings_dict = asdict(settings)
        return convert_value(settings_dict)


# === Utility Functions ================================================================

def load_dilc_settings_from_yaml(file_path: str) -> DILC_Experiment_Settings:
    """Load DILC experiment settings from a YAML file.

    Args:
        file_path: Path to the YAML configuration file.

    Returns:
        Parsed DILC_Experiment_Settings instance.
    """
    yaml_data = load_yaml(file_path)
    return from_dict_auto(DILC_Experiment_Settings, yaml_data)
