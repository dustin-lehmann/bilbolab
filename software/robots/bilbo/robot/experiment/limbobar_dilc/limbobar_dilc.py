"""
Host-side LimboBar DILC experiment proxy.

Mirrors the robot-side LimboBar DILC experiment and provides a host-side proxy
that:
  - Sends experiment settings (including limbo bar geometry) to the robot via WiFi
  - Receives real-time WiFi events from the robot during execution
  - Forwards user interactions (resume, repeat, abort) back to the robot
  - Tracks limbo bar hit state per trial
  - Maintains local state and events for GUI consumption

The actual algorithm runs entirely on the robot. This class acts as a remote
controller and event relay.
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


# === Settings Dataclasses (mirror robot side) =============================================

@dataclasses.dataclass
class FIR_Design_Params:
    fc: float
    L: int
    window: str = "hann"


@dataclasses.dataclass
class DILC_InitialConditions:
    x: float
    y: float
    psi: float


@dataclasses.dataclass
class DILC_Experiment_Meta_Settings:
    automatic_initial_conditions_reset: bool = True
    check_if_robot_is_static: bool = True
    static_timeout_s: float = 10.0
    auto_start_trials: bool = False
    auto_accept_trials: bool = False
    enable_psi_control: bool = False
    disable_tracker_during_trajectory: bool = False


@dataclasses.dataclass
class DILC_U0_Params:
    f_cutoff: float = 1.5
    sigma: float = 0.2
    bias: float = -0.03


@dataclasses.dataclass
class LimboBarGeometry:
    start_x: float | None = None
    end_x: float | None = None
    length: float | None = None
    start_y: float | None = None
    end_y: float | None = None
    height: float | None = None


@dataclasses.dataclass
class TargetZone:
    points: list[list[float]]


@dataclasses.dataclass
class LimboBar_DILC_Experiment_Settings:
    """Configuration for a LimboBar DILC experiment.

    Same as DILC_Experiment_Settings with the addition of ``limbo_bar``
    which defines the geometry of the bar to check against.
    """
    id: str
    description: str
    J: int
    reference: np.ndarray | list | str
    Ts: float
    initial_conditions: DILC_InitialConditions
    input_lowpass: FIR_Design_Params
    model_lowpass: FIR_Design_Params
    limbo_bar: LimboBarGeometry
    target_zone: TargetZone | None = None
    initial_conditions_u0: DILC_InitialConditions | None = None
    ilc_gain: float = 1.5
    iml_gain: float = 1.5
    meta: DILC_Experiment_Meta_Settings = dataclasses.field(default_factory=DILC_Experiment_Meta_Settings)
    u0_params: DILC_U0_Params = dataclasses.field(default_factory=DILC_U0_Params)
    u0: np.ndarray | list | str | None = None
    m0: np.ndarray | list | str | None = None


# === Trial Data (received from robot events) ==============================================

@dataclasses.dataclass
class LimboBar_DILC_Trial_Result:
    trial_index: int
    e_norm_ilc: float
    e_norm_iml: float
    input_change_norm: float
    model_change_norm: float
    limbo_bar_hit: bool
    limbo_bar_passed: bool | None = None


@dataclasses.dataclass
class LimboBar_DILC_Trajectory_Data:
    trial_index: int
    error_norm: float
    max_abs_error: float
    limbo_bar_hit: bool
    limbo_bar_passed: bool | None = None
    reference: list[float] = dataclasses.field(default_factory=list)
    theta: list[float] = dataclasses.field(default_factory=list)
    error: list[float] = dataclasses.field(default_factory=list)
    u: list[float] = dataclasses.field(default_factory=list)
    t: list[float] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class LimboBar_DILC_Trial_Data:
    trial_index: int
    e_norm_ilc: float
    e_norm_iml: float
    input_change_norm: float
    model_change_norm: float
    limbo_bar_hit: bool
    limbo_bar_passed: bool | None = None
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
class LimboBar_DILC_Results_Meta:
    robot_id: str
    date: str
    robot_config: dict
    control_config: dict
    settings: dict
    logs: list[dict] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class LimboBar_DILC_Results:
    meta: LimboBar_DILC_Results_Meta
    state: str
    trials: list[dict]


# === State ================================================================================

class LimboBar_DILC_Experiment_State(enum.StrEnum):
    NONE = "NONE"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    FINISHED = "FINISHED"


# === Events ===============================================================================

@event_definition
class LimboBar_DILC_Experiment_Events:
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

    limbo_bar_hit: Event = Event(copy_data_on_set=False)

    meta_settings_changed: Event = Event(copy_data_on_set=False)


# === Callbacks ============================================================================

@callback_definition
class LimboBar_DILC_Experiment_Callbacks:
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
    limbo_bar_hit: CallbackContainer
    meta_settings_changed: CallbackContainer


# === Main Class ===========================================================================

class LimboBar_DILC_Experiment:
    """Host-side proxy for a LimboBar DILC experiment running on the robot.

    Identical to DILC_Experiment except:
      - Settings include a ``LimboBarGeometry`` describing the bar.
      - Trial data includes ``limbo_bar_hit`` per trial.
      - Summary includes total hits across trials.

    Args:
        core: The host-side BILBO_Core instance providing device communication.
    """

    settings: LimboBar_DILC_Experiment_Settings | None
    state: LimboBar_DILC_Experiment_State
    trials: list[LimboBar_DILC_Trial_Data]

    def __init__(self, core):
        self.core = core
        self.device = core.device
        self.logger = Logger("LimboBar DILC Experiment (Host)")

        self.settings = None
        self.state = LimboBar_DILC_Experiment_State.NONE
        self.trials = []
        self.last_trajectory_data: LimboBar_DILC_Trajectory_Data | None = None
        self.results: LimboBar_DILC_Results | None = None
        self._yaml_file_path: str | None = None
        self._run_id: str | None = None
        self._run_dir: str | None = None

        self.auto_start_trials: bool = False
        self.auto_accept_trials: bool = False

        host_settings = get_settings()
        self.reference_trajectory_dir: str | None = (host_settings.get('paths') or {}).get('reference_trajectories')

        self.events = LimboBar_DILC_Experiment_Events()
        self.callbacks = LimboBar_DILC_Experiment_Callbacks()

        self._event_listener = self.device.events.event.on(
            self._handle_event,
            predicate=pred_flag_equals('container', 'limbobar_dilc_experiment'),
        )

        self._limbo_bar_hit_listener = self.device.events.event.on(
            self._handle_limbo_bar_hit_event,
            predicate=lambda flags, data: (
                flags.get('container') == 'testbed'
                and flags.get('event') == 'limbo_bar_hit'
            ),
        )

    # === Configuration =================================================================

    def configure(self, settings: LimboBar_DILC_Experiment_Settings):
        # Resolve reference from file path if needed.
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

        # Resolve u0 from file path if needed.
        u0 = settings.u0
        if isinstance(u0, np.ndarray) and u0.ndim == 0:
            u0 = str(u0)
        if isinstance(u0, str):
            file_data = read_input_file(u0)
            settings.u0 = file_data.trajectory.to_vector(single_input=True)
        elif isinstance(u0, list):
            settings.u0 = np.asarray(u0)
        elif isinstance(u0, np.ndarray) or u0 is None:
            pass
        else:
            raise TypeError(f"Unexpected u0 type: {type(u0)}")

        # Resolve m0 from file path if needed.
        m0 = settings.m0
        if isinstance(m0, np.ndarray) and m0.ndim == 0:
            m0 = str(m0)
        if isinstance(m0, str):
            file_data = read_model_vector_file(m0)
            settings.m0 = file_data.to_array()
        elif isinstance(m0, list):
            settings.m0 = np.asarray(m0)
        elif isinstance(m0, np.ndarray) or m0 is None:
            pass
        else:
            raise TypeError(f"Unexpected m0 type: {type(m0)}")

        self.settings = settings
        self.state = LimboBar_DILC_Experiment_State.INITIALIZED
        self.trials = []
        self.last_trajectory_data = None
        self.results = None
        self.auto_start_trials = settings.meta.auto_start_trials
        self.auto_accept_trials = settings.meta.auto_accept_trials
        self.logger = Logger(f"LimboBar DILC \"{settings.id}\" (Host)")
        tz_str = ""
        if settings.target_zone is not None:
            tz_str = f", target zone: {len(settings.target_zone.points)} points"
        self.logger.info(f"Configured: {settings.J} trials, Ts={settings.Ts}s, "
                         f"N={len(settings.reference)} samples, "
                         f"limbo bar height={settings.limbo_bar.height}{tz_str}")

        self.events.experiment_initialized.set(data={
            'id': settings.id,
            'J': settings.J,
            'N': len(settings.reference),
            'Ts': settings.Ts,
            'duration_s': len(settings.reference) * settings.Ts,
            'limbo_bar_height': settings.limbo_bar.height,
        })
        self.callbacks.experiment_initialized.call()

    def configure_from_yaml(self, file_path: str):
        yaml_data = load_yaml(file_path)
        settings = from_dict_auto(LimboBar_DILC_Experiment_Settings, yaml_data)

        yaml_dir = os.path.dirname(os.path.abspath(file_path))

        # Unwrap 0-d ndarray strings
        if isinstance(settings.reference, np.ndarray) and settings.reference.ndim == 0:
            settings.reference = str(settings.reference)

        # Resolve relative reference path
        if isinstance(settings.reference, str) and not os.path.isabs(settings.reference):
            candidate = os.path.join(yaml_dir, settings.reference)
            if os.path.isfile(candidate):
                settings.reference = candidate
            elif self.reference_trajectory_dir and os.path.isfile(
                    os.path.join(self.reference_trajectory_dir, settings.reference)):
                settings.reference = os.path.join(self.reference_trajectory_dir, settings.reference)
            else:
                settings.reference = candidate

        # Unwrap and resolve u0 file path
        if isinstance(settings.u0, np.ndarray) and settings.u0.ndim == 0:
            settings.u0 = str(settings.u0)
        if isinstance(settings.u0, str) and not os.path.isabs(settings.u0):
            candidate = os.path.join(yaml_dir, settings.u0)
            if os.path.isfile(candidate):
                settings.u0 = candidate
            elif self.reference_trajectory_dir and os.path.isfile(
                    os.path.join(self.reference_trajectory_dir, settings.u0)):
                settings.u0 = os.path.join(self.reference_trajectory_dir, settings.u0)
            else:
                settings.u0 = candidate

        # Unwrap and resolve m0 file path
        if isinstance(settings.m0, np.ndarray) and settings.m0.ndim == 0:
            settings.m0 = str(settings.m0)
        if isinstance(settings.m0, str) and not os.path.isabs(settings.m0):
            candidate = os.path.join(yaml_dir, settings.m0)
            if os.path.isfile(candidate):
                settings.m0 = candidate
            elif self.reference_trajectory_dir and os.path.isfile(
                    os.path.join(self.reference_trajectory_dir, settings.m0)):
                settings.m0 = os.path.join(self.reference_trajectory_dir, settings.m0)
            else:
                settings.m0 = candidate

        self.configure(settings)
        self._yaml_file_path = os.path.abspath(file_path)

    # === Experiment Control ============================================================

    def start(self) -> bool:
        if self.settings is None:
            self.logger.error("Cannot start: no settings configured")
            return False

        if self.state not in (LimboBar_DILC_Experiment_State.INITIALIZED,
                              LimboBar_DILC_Experiment_State.FINISHED,
                              LimboBar_DILC_Experiment_State.ERROR,
                              LimboBar_DILC_Experiment_State.NONE):
            self.logger.warning(f"Cannot start: experiment is in state {self.state}")
            return False

        settings_dict = self._serialize_settings()
        self.state = LimboBar_DILC_Experiment_State.RUNNING
        self.trials = []

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._run_id = f"limbobar_dilc_{self.settings.id}_{timestamp}"
        self._run_dir = None

        if self._yaml_file_path:
            yaml_dir = os.path.dirname(self._yaml_file_path)
            self._run_dir = os.path.join(yaml_dir, self._run_id)
            os.makedirs(self._run_dir, exist_ok=True)
            try:
                shutil.copy2(self._yaml_file_path, self._run_dir)
                self.logger.info(f"Copied YAML config to {self._run_dir}")
            except Exception as e:
                self.logger.warning(f"Failed to copy YAML config: {e}")
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

        self.logger.info(f"Experiment run ID: {self._run_id}")
        self.logger.info("Sending experiment settings to robot...")

        self.device.executeFunction(
            function_name='run_limbobar_dilc_experiment',
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
        if self._limbo_bar_hit_listener is not None:
            self._limbo_bar_hit_listener.stop()
            self._limbo_bar_hit_listener = None

    def set_auto_start_trials(self, value: bool):
        self.logger.info(f"Setting auto_start_trials to {value}")
        self.device.executeFunction('set_dilc_auto_start_trials', arguments={'value': bool(value)})

    def set_auto_accept_trials(self, value: bool):
        self.logger.info(f"Setting auto_accept_trials to {value}")
        self.device.executeFunction('set_dilc_auto_accept_trials', arguments={'value': bool(value)})

    def generate_report(self, output: str | None = None, format: str = 'html', show: bool = True):
        from robots.bilbo.robot.experiment.limbobar_dilc.limbobar_dilc_helpers import generate_limbobar_dilc_report

        self.logger.info("Generating LimboBar DILC report...")
        try:
            return generate_limbobar_dilc_report(self, output=output, format=format, show=show)
        except Exception as e:
            self.logger.error(f"Failed to generate report: {e}")
            raise

    # === Limbo Bar Hit (real-time WiFi event from testbed) ============================

    def _handle_limbo_bar_hit_event(self, event_data, **kwargs):
        """Called immediately when the robot detects a limbo bar collision.

        This arrives via the 'testbed' WiFi event container, well before the
        trial_finished event.  Override or connect to ``events.limbo_bar_hit``
        / ``callbacks.limbo_bar_hit`` to react (e.g. testbed LED feedback).
        """
        data = event_data.get('data', {}) or {}
        bar_id = data.get('bar_id')
        self.logger.info(f"Limbo bar hit! (bar_id={bar_id})")
        self.events.limbo_bar_hit.set(data=data)
        self.callbacks.limbo_bar_hit.call(data)

    # === WiFi Event Handler ============================================================

    def _handle_event(self, event_data, **kwargs):
        data = event_data.get('data', {}) or {}
        event_name = event_data.get('event', '')

        remote_state = data.get('state', None)
        if remote_state:
            try:
                self.state = LimboBar_DILC_Experiment_State(remote_state)
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
                             f"duration={data.get('duration_s', 0):.2f}s, "
                             f"limbo bar height={data.get('limbo_bar_height')})")
            self.events.experiment_initialized.set(data=data)

        elif event_name == 'experiment_started':
            self.logger.info(f"Robot: experiment started")
            self.state = LimboBar_DILC_Experiment_State.RUNNING
            speak(f"Starting LimboBar DILC experiment with {total_trials} trials")
            self.events.experiment_started.set(data=data)
            self.callbacks.experiment_started.call()

        elif event_name == 'experiment_finished':
            self.logger.info(f"Robot: experiment finished")
            self.state = LimboBar_DILC_Experiment_State.FINISHED

            hits = data.get('limbo_bar_hits', [])
            total_hits = sum(1 for h in hits if h) if hits else 0
            passes = data.get('limbo_bar_passes', [])
            total_passes = sum(1 for p in passes if p is True) if passes else 0
            pass_str = f", {total_passes} passes" if passes else ""
            speak(f"Experiment finished. {total_hits} limbo bar hits{pass_str} in {total_trials} trials")

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
            self.logger.error(f"Robot: experiment error -- {msg}")
            self.state = LimboBar_DILC_Experiment_State.ERROR

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
            limbo_bar_hit = data.get('limbo_bar_hit', False)
            limbo_bar_passed = data.get('limbo_bar_passed', None)

            trial_data = LimboBar_DILC_Trial_Data(
                trial_index=trial_index or 0,
                e_norm_ilc=e_norm_ilc,
                e_norm_iml=e_norm_iml,
                input_change_norm=input_change,
                model_change_norm=model_change,
                limbo_bar_hit=limbo_bar_hit,
                limbo_bar_passed=limbo_bar_passed,
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

            hit_str = "HIT" if limbo_bar_hit else "miss"
            passed_str = ""
            if limbo_bar_passed is not None:
                passed_str = f", passed: {'YES' if limbo_bar_passed else 'NO'}"
            self.logger.info(f"Robot: trial {(trial_index or 0) + 1}/{total_trials} finished "
                             f"(e_ilc={e_norm_ilc:.6f}, limbo bar: {hit_str}{passed_str})")
            speak(f"Trial {(trial_index or 0) + 1} finished")
            self.events.trial_finished.set(data=data)
            self.callbacks.trial_finished.call()

        elif event_name == 'trial_reverted':
            self.logger.info(f"Robot: trial {(trial_index or 0) + 1}/{total_trials} reverted")
            self.events.trial_reverted.set(data=data)
            self.callbacks.trial_reverted.call()

        elif event_name == 'trial_error':
            msg = data.get('message', 'Unknown error')
            self.logger.error(f"Robot: trial error -- {msg}")
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
            limbo_bar_hit = data.get('limbo_bar_hit', False)
            limbo_bar_passed = data.get('limbo_bar_passed', None)
            hit_str = "HIT" if limbo_bar_hit else "miss"
            passed_str = ""
            if limbo_bar_passed is not None:
                passed_str = f", passed: {'YES' if limbo_bar_passed else 'NO'}"
            self.logger.info(f"Robot: trajectory finished (error_norm={error_norm:.6f}, limbo bar: {hit_str}{passed_str})")

            if data.get('reference') is not None:
                self.last_trajectory_data = LimboBar_DILC_Trajectory_Data(
                    trial_index=trial_index or 0,
                    error_norm=error_norm,
                    max_abs_error=data.get('max_abs_error', 0),
                    limbo_bar_hit=limbo_bar_hit,
                    limbo_bar_passed=limbo_bar_passed,
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
            self.logger.info(f"Robot: meta settings changed -- "
                             f"auto_start={self.auto_start_trials}, auto_accept={self.auto_accept_trials}")
            self.events.meta_settings_changed.set(data=data)
            self.callbacks.meta_settings_changed.call()

        else:
            self.logger.warning(f"Unknown LimboBar DILC event: {event_name}")

    # === Results Download ==============================================================

    def _download_and_save_results(self, remote_filepath: str):
        if not hasattr(self.core, 'file_handler') or self.core.file_handler is None:
            self.logger.warning("No file handler available -- skipping results download")
            return

        download_dir = (self._run_dir
                        or (os.path.dirname(self._yaml_file_path) if self._yaml_file_path else None)
                        or tempfile.gettempdir())

        try:
            local_filepath = self.core.file_handler.download_file(remote_filepath, download_dir)
            self.logger.info(f"Results downloaded to: {local_filepath}")

            with open(local_filepath, 'r') as f:
                results_dict = json.load(f)

            self.results = LimboBar_DILC_Results(
                meta=from_dict_auto(LimboBar_DILC_Results_Meta, results_dict.get('meta', {})),
                state=results_dict.get('state', 'UNKNOWN'),
                trials=results_dict.get('trials', []),
            )
            self.logger.info(f"Loaded {len(self.results.trials)} trials, state={self.results.state}")
        except Exception as e:
            self.logger.error(f"Failed to download/parse results: {e}")

    # === Best Input Extraction ========================================================

    def _save_best_input(self):
        if not self._run_dir:
            return

        trials = (self.results.trials if self.results and self.results.trials else None)
        if trials is None and self.trials:
            trials = [dataclasses.asdict(t) for t in self.trials]
        if not trials:
            return

        try:
            best_trial = min(trials, key=lambda t: t.get('e_norm_ilc', float('inf')))
            u = best_trial.get('u')
            if u is None:
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
                id=self.settings.id if self.settings else 'limbobar_dilc',
                description=f"Best input trajectory (trial {int(best_index) + 1}, e_norm_ilc={e_norm:.6f})",
            )
            file_name = self._run_id or "best_input"
            write_input_file(file_name, self._run_dir, file_data)
            self.logger.info(f"Saved best input trajectory to {self._run_dir}/{file_name}.bitrj")
        except Exception as e:
            self.logger.warning(f"Failed to save best input trajectory: {e}")

    def _save_best_model(self):
        if not self._run_dir:
            return

        trials = (self.results.trials if self.results and self.results.trials else None)
        if trials is None and self.trials:
            trials = [dataclasses.asdict(t) for t in self.trials]
        if not trials:
            return

        try:
            best_trial = min(trials, key=lambda t: t.get('e_norm_iml', float('inf')))
            m = best_trial.get('m')
            if m is None:
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
                id=self.settings.id if self.settings else 'limbobar_dilc',
                description=f"Best model vector (trial {int(best_index) + 1}, e_norm_iml={e_norm:.6f})",
            )
            file_path = os.path.join(self._run_dir, f"{self._run_id or 'best_model'}.bmvec")
            write_model_vector_file(file_path, file_data)
            self.logger.info(f"Saved best model vector to {file_path}")
        except Exception as e:
            self.logger.warning(f"Failed to save best model vector: {e}")

    # === Auto Report ==================================================================

    def _auto_generate_report(self):
        if not self._yaml_file_path:
            return

        if self.results is None and not self.trials:
            return

        try:
            report_dir = self._run_dir or os.path.dirname(self._yaml_file_path)
            report_name = f"{self._run_id}.html" if self._run_id else "limbobar_dilc_report.html"
            report_path = os.path.join(report_dir, report_name)

            self.generate_report(output=report_path, format='html', show=True)
            self.logger.info(f"Auto-generated report: {report_path}")
        except Exception as e:
            self.logger.warning(f"Failed to auto-generate report: {e}")

    # === Serialization =================================================================

    def _serialize_settings(self) -> dict:
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

def load_limbobar_dilc_settings_from_yaml(file_path: str) -> LimboBar_DILC_Experiment_Settings:
    yaml_data = load_yaml(file_path)
    return from_dict_auto(LimboBar_DILC_Experiment_Settings, yaml_data)
