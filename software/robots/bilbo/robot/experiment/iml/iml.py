"""
Host-side IML (Iterative Model Learning) experiment proxy.

Mirrors the robot-side IML model-identification experiment and provides a
host-side proxy class that:
  - Serializes experiment settings (including the learning set of input
    trajectories) and sends them to the robot via the ``run_iml_experiment``
    WiFi command
  - Receives real-time WiFi events from the robot during execution
  - Forwards user interactions (resume, repeat, abort) back to the robot
  - Maintains local state and events for GUI consumption
  - Downloads the results JSON and the identified ``.bmvec`` model on completion

The actual IML algorithm runs on the robot (Raspberry Pi); this class is a
remote controller and event relay, exactly as the DILC/IITL host proxies are.

The learning set is a list of input trajectories. It can be assembled from a
list of ``.bitrj`` files (:meth:`IML_Experiment.configure_from_files`) or
referenced from a YAML config (:meth:`IML_Experiment.configure_from_yaml`).
"""
import dataclasses
import enum
import json
import os
import tempfile
import threading
from dataclasses import asdict
from datetime import datetime

import numpy as np

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, Event, pred_flag_equals
from core.utils.logging_utils import Logger
from core.utils.sound.sound import speak
from core.utils.yaml_utils import load_yaml
from robots.bilbo.settings import get_settings
from robots.bilbo.robot.experiment.experiment_definitions import read_input_file


# === Settings dataclasses (mirror the robot-side IML settings) ======================

@dataclasses.dataclass
class FIR_Design_Params:
    """FIR low-pass filter design parameters for Q-filter construction."""
    fc: float
    L: int
    window: str = "hann"


@dataclasses.dataclass
class IML_InitialConditions:
    """Starting pose the robot navigates to before each trial."""
    x: float
    y: float
    psi: float


@dataclasses.dataclass
class IML_Experiment_Meta_Settings:
    """Behavioral settings controlling the experiment flow (see DILC)."""
    automatic_initial_conditions_reset: bool = True
    check_if_robot_is_static: bool = True
    static_timeout_s: float = 10.0
    auto_start_trials: bool = False
    auto_accept_trials: bool = False
    enable_psi_control: bool = False
    disable_tracker_during_trajectory: bool = False


@dataclasses.dataclass
class IML_LearningInput:
    """One input trajectory of the learning set.

    Field names match the robot-side ``IML_LearningInput`` so the serialized
    dict deserializes directly on the robot.
    """
    input: np.ndarray | list
    id: str = ""


@dataclasses.dataclass
class IML_Experiment_Settings:
    """Configuration for an IML experiment (mirrors the robot-side settings).

    See the robot module for full attribute docs. ``method`` is a plain string
    ("iterative" | "rls") so it serializes cleanly to the robot's IML_Method
    StrEnum.
    """
    id: str
    description: str
    J: int
    learning_set: list[IML_LearningInput]
    Ts: float
    initial_conditions: IML_InitialConditions

    # method selection
    method: str = "iterative"

    # regularisation
    s_m: float | None = None
    adaptive_s_m: bool = True
    kappa: float = 100.0

    # Q-filter
    model_lowpass: FIR_Design_Params | None = None

    # model structure (length truncation + decay regularisation)
    model_length: int | None = None
    model_horizon_s: float | None = None
    tail_penalty: float = 0.0
    tail_penalty_type: str = "linear"

    # initial estimate / reference
    m0: np.ndarray | list | None = None
    reference_model: np.ndarray | list | None = None

    # safety
    max_input_abs: float | None = None
    input_safety_factor: float = 1.5

    # shared flow
    initial_conditions_u0: IML_InitialConditions | None = None
    meta: IML_Experiment_Meta_Settings = dataclasses.field(
        default_factory=IML_Experiment_Meta_Settings)


# === Trial data (received from robot events) ========================================

@dataclasses.dataclass
class IML_Trial_Data:
    """Per-trial data received via WiFi. Array fields may be None."""
    trial_index: int
    model_output_error_norm: float
    model_fit_error_norm: float | None = None
    model_estimation_error_norm: float | None = None
    t: list[float] | None = None
    u: list[float] | None = None
    y: list[float] | None = None
    model_vector: list[float] | None = None
    model_vector_update: list[float] | None = None


@dataclasses.dataclass
class IML_Trajectory_Data:
    """Trajectory data from a single trajectory execution (received via WiFi)."""
    trial_index: int
    error_norm: float
    max_abs_error: float
    u: list[float]
    y: list[float]
    model_prediction: list[float]
    model_output_error: list[float]
    t: list[float]


@dataclasses.dataclass
class IML_Results_Meta:
    robot_id: str
    date: str
    robot_config: dict
    control_config: dict
    settings: dict
    logs: list[dict] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class IML_Results:
    meta: IML_Results_Meta
    state: str
    trials: list[dict]
    best_model: list[float] | None = None
    best_model_trial_index: int | None = None
    final_model: list[float] | None = None


# === State / Events / Callbacks =====================================================

class IML_Experiment_State(enum.StrEnum):
    NONE = "NONE"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    FINISHED = "FINISHED"


@event_definition
class IML_Experiment_Events:
    """Asynchronous events mirroring the robot-side IML lifecycle."""
    experiment_initialized: Event = Event(copy_data_on_set=False)
    experiment_started: Event = Event(copy_data_on_set=False)
    experiment_finished: Event = Event(copy_data_on_set=False)
    experiment_error: Event = Event(copy_data_on_set=False)

    trial_started: Event = Event(copy_data_on_set=False)
    trial_prepared: Event = Event(copy_data_on_set=False)
    trial_finished: Event = Event(copy_data_on_set=False)
    trial_reverted: Event = Event(copy_data_on_set=False)
    trial_error: Event = Event(copy_data_on_set=False)

    trajectory_loaded: Event = Event(copy_data_on_set=False)
    trajectory_started: Event = Event(copy_data_on_set=False)
    trajectory_finished: Event = Event(copy_data_on_set=False)
    trajectory_error: Event = Event(copy_data_on_set=False)

    meta_settings_changed: Event = Event(copy_data_on_set=False)


@callback_definition
class IML_Experiment_Callbacks:
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


# === Main proxy class ===============================================================

class IML_Experiment:
    """Host-side proxy for an IML experiment running on the robot."""

    settings: IML_Experiment_Settings | None
    state: IML_Experiment_State
    trials: list[IML_Trial_Data]

    def __init__(self, core):
        self.core = core
        self.device = core.device
        self.logger = Logger("IML Experiment (Host)")

        self.settings = None
        self.state = IML_Experiment_State.NONE
        self.trials = []
        self.last_trajectory_data: IML_Trajectory_Data | None = None
        self.results: IML_Results | None = None
        self._yaml_file_path: str | None = None
        self._run_id: str | None = None
        self._run_dir: str | None = None

        # Local paths to the downloaded results artifacts (set on completion).
        self.results_file: str | None = None
        self.model_file: str | None = None

        self.auto_start_trials: bool = False
        self.auto_accept_trials: bool = False

        # Auto-generate + open an HTML report when the experiment ends.
        self.auto_report: bool = True

        host_settings = get_settings()
        self.output_dir: str | None = (host_settings.get('paths') or {}).get('reference_trajectories')

        self.events = IML_Experiment_Events()
        self.callbacks = IML_Experiment_Callbacks()

        # Subscribe to WiFi events from the robot's IML experiment.
        self._event_listener = self.device.events.event.on(
            self._handle_iml_event,
            predicate=pred_flag_equals('container', 'iml_experiment'),
        )

    # === Configuration =================================================================

    def configure(self, settings: IML_Experiment_Settings):
        """Configure the experiment with the given settings."""
        if not settings.learning_set:
            raise ValueError("IML settings must include a non-empty learning_set")

        self.settings = settings
        self.state = IML_Experiment_State.INITIALIZED
        self.trials = []
        self.last_trajectory_data = None
        self.results = None
        self.auto_start_trials = settings.meta.auto_start_trials
        self.auto_accept_trials = settings.meta.auto_accept_trials
        self.logger = Logger(f"IML Experiment \"{settings.id}\" (Host)")

        N = len(np.asarray(settings.learning_set[0].input))
        self.logger.info(f"Configured: {settings.J} trials, Ts={settings.Ts}s, "
                         f"N={N} samples, {len(settings.learning_set)} learning inputs, "
                         f"method={settings.method}")

        self.events.experiment_initialized.set(data={
            'id': settings.id, 'J': settings.J, 'N': N, 'Ts': settings.Ts,
            'duration_s': N * settings.Ts,
        })
        self.callbacks.experiment_initialized.call()

    def configure_from_files(self, files: list[str],
                             initial_conditions: IML_InitialConditions,
                             *,
                             id: str | None = None,
                             J: int | None = None,
                             m0=None,
                             reference_model=None,
                             model_lowpass: FIR_Design_Params | None = None,
                             **setting_overrides):
        """Build settings from a list of ``.bitrj`` files and configure.

        Each input file contributes one input trajectory to the learning set
        (single-channel, via ``InputTrajectory.to_vector(single_input=True)``).
        ``Ts`` is taken from the first trajectory's ``dt`` and ``J`` defaults to
        the number of inputs (one trial per input). ``m0`` and
        ``reference_model`` may each be an array/list or a path to a ``.json``
        list. Extra keyword arguments are forwarded to
        :class:`IML_Experiment_Settings` (e.g. ``method``, ``s_m``,
        ``adaptive_s_m``).
        """
        if not files:
            raise ValueError("No input files provided for the learning set")

        learning_set: list[IML_LearningInput] = []
        Ts: float | None = None
        for f in files:
            file_data = read_input_file(f)
            if file_data is None:
                raise ValueError(f"Failed to read input file: {f}")
            traj = file_data.trajectory
            vec = traj.to_vector(single_input=True)
            learning_set.append(IML_LearningInput(
                input=vec, id=file_data.id or os.path.basename(f)))
            if Ts is None:
                Ts = traj.dt

        settings = IML_Experiment_Settings(
            id=id or "iml_experiment",
            description=f"IML model identification from {len(files)} input(s)",
            J=J if J is not None else len(learning_set),
            learning_set=learning_set,
            Ts=Ts or 0.01,
            initial_conditions=initial_conditions,
            model_lowpass=model_lowpass,
            m0=self._resolve_vector(m0),
            reference_model=self._resolve_vector(reference_model),
            **setting_overrides,
        )
        self.configure(settings)
        return settings

    @staticmethod
    def _resolve_vector(value):
        """Resolve a vector given as an array/list or a path to a JSON list."""
        if value is None:
            return None
        if isinstance(value, str):
            with open(value) as f:
                value = json.load(f)
        return np.asarray(value, dtype=float)

    def configure_from_yaml(self, file_path: str):
        """Load IML experiment settings from a YAML file and configure.

        The learning set is referenced by paths (``learning_set: [a.bitrj,
        b.bitrj]`` or a glob directory); the scalar reference vectors
        (``m0``, ``reference_model``) may be given as paths to JSON lists.
        Relative paths resolve against the YAML file's directory.
        """
        settings = load_iml_settings_from_yaml(file_path, self.output_dir)
        self.configure(settings)
        self._yaml_file_path = os.path.abspath(file_path)
        return settings

    # === Lifecycle =====================================================================

    def start(self) -> bool:
        """Serialize settings and start the experiment on the robot."""
        if self.settings is None:
            self.logger.error("Cannot start: no settings configured")
            return False
        if self.state not in (IML_Experiment_State.INITIALIZED, IML_Experiment_State.FINISHED,
                              IML_Experiment_State.ERROR, IML_Experiment_State.NONE):
            self.logger.warning(f"Cannot start: experiment is in state {self.state}")
            return False

        settings_dict = self._serialize_settings()
        self.state = IML_Experiment_State.RUNNING
        self.trials = []

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        robot_id = getattr(self.core, 'id', None) or 'robot'
        self._run_id = f"iml_{robot_id}_{self.settings.id}_{timestamp}"

        # Place run artifacts next to the source yaml if known.
        self._run_dir = None
        if self._yaml_file_path:
            self._run_dir = os.path.join(os.path.dirname(self._yaml_file_path), self._run_id)
            os.makedirs(self._run_dir, exist_ok=True)

        self.logger.info(f"Experiment run ID: {self._run_id}")
        self.logger.info("Sending IML experiment settings to robot...")
        self.device.executeFunction(
            function_name='run_iml_experiment',
            arguments={'settings': settings_dict},
        )
        self.logger.info("Experiment start command sent")
        return True

    def start_blocking(self, timeout: float = None) -> bool:
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
        self.logger.info("Sending resume command")
        self.device.executeFunction('resume', arguments={'data': {}})

    def repeat(self):
        self.logger.info("Sending repeat command")
        self.device.executeFunction('repeat', arguments={'data': {}})

    def stop(self):
        self.logger.warning("Sending stop command")
        self.device.executeFunction('stop', arguments={'data': {}})

    def close(self):
        if self._event_listener is not None:
            self._event_listener.stop()
            self._event_listener = None

    def set_auto_start_trials(self, value: bool):
        self.logger.info(f"Setting auto_start_trials to {value}")
        self.device.executeFunction('set_iml_auto_start_trials', arguments={'value': bool(value)})

    def set_auto_accept_trials(self, value: bool):
        self.logger.info(f"Setting auto_accept_trials to {value}")
        self.device.executeFunction('set_iml_auto_accept_trials', arguments={'value': bool(value)})

    # === WiFi Event Handler ============================================================

    def _handle_iml_event(self, event_data, **kwargs):
        """Route incoming WiFi events from the robot's IML experiment."""
        data = event_data.get('data', {}) or {}
        event_name = event_data.get('event', '')

        remote_state = data.get('state', None)
        if remote_state:
            try:
                self.state = IML_Experiment_State(remote_state)
            except ValueError:
                pass

        if 'auto_start_trials' in data:
            self.auto_start_trials = data['auto_start_trials']
        if 'auto_accept_trials' in data:
            self.auto_accept_trials = data['auto_accept_trials']

        trial_index = data.get('trial_index', None)
        total_trials = data.get('total_trials', None)

        if event_name == 'experiment_initialized':
            self.logger.info(f"Robot: experiment initialized (N={data.get('N')}, "
                             f"duration={data.get('duration_s', 0):.2f}s)")
            self.events.experiment_initialized.set(data=data)

        elif event_name == 'experiment_started':
            self.logger.info("Robot: experiment started")
            self.state = IML_Experiment_State.RUNNING
            speak(f"Starting IML experiment with {total_trials} trials")
            self.events.experiment_started.set(data=data)
            self.callbacks.experiment_started.call()

        elif event_name == 'experiment_finished':
            self.logger.info("Robot: experiment finished")
            self.state = IML_Experiment_State.FINISHED
            speak("IML experiment finished successfully")
            self._download_and_save_results(data)
            self.events.experiment_finished.set(data=data)
            self.callbacks.experiment_finished.call()
            self._maybe_generate_report()

        elif event_name == 'experiment_error':
            msg = data.get('message', 'Unknown error')
            self.logger.error(f"Robot: experiment error — {msg}")
            self.state = IML_Experiment_State.ERROR
            speak("IML experiment failed")
            self._download_and_save_results(data)
            self.events.experiment_error.set(data=data)
            self.callbacks.experiment_error.call()
            self._maybe_generate_report()

        elif event_name == 'trial_started':
            self.logger.info(f"Robot: trial {(trial_index or 0) + 1}/{total_trials} started")
            speak(f"Trial {(trial_index or 0) + 1} of {total_trials}")
            self.events.trial_started.set(data=data)
            self.callbacks.trial_started.call()

        elif event_name == 'trial_prepared':
            self.events.trial_prepared.set(data=data)

        elif event_name == 'trial_finished':
            trial_data = IML_Trial_Data(
                trial_index=trial_index or 0,
                model_output_error_norm=data.get('model_output_error_norm', 0.0),
                model_fit_error_norm=data.get('model_fit_error_norm'),
                model_estimation_error_norm=data.get('model_estimation_error_norm'),
                t=data.get('t'),
                u=data.get('u'),
                y=data.get('y'),
                model_vector=data.get('model_vector'),
                model_vector_update=data.get('model_vector_update'),
            )
            self.trials.append(trial_data)
            self.logger.info(f"Robot: trial {(trial_index or 0) + 1}/{total_trials} finished "
                             f"(output err={trial_data.model_output_error_norm:.6f})")
            speak(f"Trial {(trial_index or 0) + 1} finished")
            self.events.trial_finished.set(data=data)
            self.callbacks.trial_finished.call()

        elif event_name == 'trial_reverted':
            self.events.trial_reverted.set(data=data)
            self.callbacks.trial_reverted.call()

        elif event_name == 'trial_error':
            self.logger.error(f"Robot: trial error — {data.get('message', 'Unknown error')}")
            self.events.trial_error.set(data=data)
            self.callbacks.trial_error.call()

        elif event_name == 'trajectory_loaded':
            self.events.trajectory_loaded.set(data=data)

        elif event_name == 'trajectory_started':
            self.events.trajectory_started.set(data=data)
            self.callbacks.trajectory_started.call()

        elif event_name == 'trajectory_finished':
            error_norm = data.get('error_norm', 0)
            self.logger.info(f"Robot: trajectory finished (output err={error_norm:.6f})")
            if data.get('y') is not None:
                self.last_trajectory_data = IML_Trajectory_Data(
                    trial_index=trial_index or 0,
                    error_norm=error_norm,
                    max_abs_error=data.get('max_abs_error', 0),
                    u=data.get('u', []),
                    y=data.get('y', []),
                    model_prediction=data.get('model_prediction', []),
                    model_output_error=data.get('model_output_error', []),
                    t=data.get('t', []),
                )
            self.events.trajectory_finished.set(data=data)
            self.callbacks.trajectory_finished.call()

        elif event_name == 'trajectory_error':
            self.logger.error("Robot: trajectory error")
            self.events.trajectory_error.set(data=data)

        elif event_name == 'meta_settings_changed':
            self.auto_start_trials = data.get('auto_start_trials', self.auto_start_trials)
            self.auto_accept_trials = data.get('auto_accept_trials', self.auto_accept_trials)
            self.events.meta_settings_changed.set(data=data)
            self.callbacks.meta_settings_changed.call()

        else:
            self.logger.warning(f"Unknown IML event: {event_name}")

    # === Results Download ==============================================================

    def _download_and_save_results(self, event_data: dict):
        """Download the results JSON and the identified ``.bmvec`` model file."""
        if not hasattr(self.core, 'file_handler') or self.core.file_handler is None:
            self.logger.warning("No file handler available — skipping results download")
            return
        download_dir = self._run_dir or tempfile.gettempdir()

        results_filepath = event_data.get('results_filepath')
        if results_filepath:
            try:
                local_filepath = self.core.file_handler.download_file(results_filepath, download_dir)
                self.results_file = local_filepath
                self.logger.info(f"IML results downloaded to: {local_filepath}")
                with open(local_filepath, 'r') as f:
                    results_dict = json.load(f)
                self.results = IML_Results(
                    meta=from_dict_auto(IML_Results_Meta, results_dict.get('meta', {})),
                    state=results_dict.get('state', 'UNKNOWN'),
                    trials=results_dict.get('trials', []),
                    best_model=results_dict.get('best_model'),
                    best_model_trial_index=results_dict.get('best_model_trial_index'),
                    final_model=results_dict.get('final_model'),
                )
                self.logger.info(f"Loaded {len(self.results.trials)} trials, "
                                 f"state={self.results.state}")
            except Exception as e:
                self.logger.error(f"Failed to download/parse IML results: {e}")

        model_filepath = event_data.get('model_filepath')
        if model_filepath:
            try:
                self.model_file = self.core.file_handler.download_file(model_filepath, download_dir)
                self.logger.info(f"IML model downloaded to: {self.model_file}")
            except Exception as e:
                self.logger.error(f"Failed to download IML model file: {e}")

    # === Report ========================================================================

    def _maybe_generate_report(self):
        """Generate and open an HTML report when the experiment ends (best effort).

        Runs in a background thread so it never blocks the WiFi event handler,
        and is a no-op if ``auto_report`` is disabled or no results were
        downloaded. The report is saved next to the downloaded results JSON.
        """
        if not self.auto_report:
            return
        if not self.results_file:
            self.logger.info("No local results file — skipping report generation")
            return

        results_file = self.results_file

        def _run():
            try:
                from robots.bilbo.robot.experiment.iml.iml_helpers import generate_iml_report
                output = os.path.splitext(results_file)[0] + ".html"
                generate_iml_report(results_file, output=output, show=True)
                self.logger.info(f"IML report generated: {output}")
            except Exception as e:
                self.logger.error(f"Failed to generate IML report: {e}")

        threading.Thread(target=_run, name="iml-report", daemon=True).start()

    # === Serialization =================================================================

    def _serialize_settings(self) -> dict:
        """Convert settings to a JSON-serializable dict (numpy arrays -> lists)."""
        def convert_value(v):
            if isinstance(v, np.ndarray):
                return v.tolist()
            if isinstance(v, dict):
                return {k: convert_value(val) for k, val in v.items()}
            if isinstance(v, (list, tuple)):
                return [convert_value(item) for item in v]
            return v

        return convert_value(asdict(self.settings))


# === Utility Functions ================================================================

# Scalar reference vectors that may be given in the yaml as a path to a JSON list.
_IML_VECTOR_FIELDS = ("m0", "reference_model")


def _resolve_path(value: str, *search_dirs: str) -> str:
    """Return the first existing match for ``value`` across ``search_dirs``.

    Absolute paths are returned as-is. Relative paths are tried against each
    search directory in order; if none exists, the first candidate is returned
    (so the eventual open() raises a clear, yaml-relative error).
    """
    if os.path.isabs(value):
        return value
    candidates = [os.path.join(d, value) for d in search_dirs if d]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return candidates[0] if candidates else value


def load_iml_settings_from_yaml(file_path: str,
                                reference_trajectory_dir: str | None = None
                                ) -> IML_Experiment_Settings:
    """Load IML experiment settings from a YAML file.

    The learning set is referenced by paths -- a list of ``.bitrj`` files
    (``learning_set: [a.bitrj, b.bitrj]``). The scalar reference vectors
    (``m0``, ``reference_model``) may be paths to JSON lists. Relative paths
    resolve against the yaml's directory first, then
    ``reference_trajectory_dir``. Resolution happens at the dict level (before
    ``from_dict_auto``) so the learning-set inputs and arrays deserialize
    cleanly into the dataclass.

    Args:
        file_path: Path to the IML experiment YAML file.
        reference_trajectory_dir: Optional fallback directory for relative paths.

    Returns:
        Parsed and resolved IML_Experiment_Settings instance.
    """
    yaml_data = load_yaml(file_path)
    yaml_dir = os.path.dirname(os.path.abspath(file_path))
    search_dirs = (yaml_dir, reference_trajectory_dir)

    # Learning set: resolve each .bitrj path and expand into an input vector.
    learning_set = yaml_data.get("learning_set")
    if isinstance(learning_set, list) and learning_set and isinstance(learning_set[0], str):
        expanded = []
        Ts_from_files = None
        for entry in learning_set:
            file_data = read_input_file(_resolve_path(entry, *search_dirs))
            if file_data is None:
                raise ValueError(f"Failed to read learning-set input file: {entry}")
            traj = file_data.trajectory
            expanded.append({
                "input": traj.to_vector(single_input=True).tolist(),
                "id": file_data.id or os.path.basename(entry),
            })
            if Ts_from_files is None:
                Ts_from_files = traj.dt
        yaml_data["learning_set"] = expanded
        # Inherit the sampling rate from the learning set if the yaml omits it.
        if Ts_from_files is not None:
            yaml_data.setdefault("Ts", Ts_from_files)

    # Scalar reference vectors: resolve path strings into JSON lists.
    for field in _IML_VECTOR_FIELDS:
        value = yaml_data.get(field)
        if isinstance(value, str):
            vec_path = _resolve_path(value, *search_dirs)
            with open(vec_path) as f:
                yaml_data[field] = json.load(f)

    return from_dict_auto(IML_Experiment_Settings, yaml_data)
