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
  - On experiment finish / error / abort the bar is removed from the testbed.
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
from core.utils.control_lib.lib_control.il.q_filter import FIR_Design_Params, design_zero_phase_fir, build_Qf_zero_padded
from core.utils.control_lib.lib_control.lifted_systems import vec2liftedMatrix
from core.utils.data import generate_time_vector_by_length, generate_random_input
from core.utils.events import event_definition, Event, wait_for_events, OR, TIMEOUT
from core.utils.logging_utils import Logger, enable_redirection, disable_redirection
from core.utils.time import wait_until
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
from robot.testbed.obstacles import LimboBarGeometry
from robot.utilities.buzzer import beep


# === Data Structures ==============================================================================================

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


@dataclasses.dataclass
class DILC_U0_Params:
    f_cutoff: float = 1.5
    sigma: float = 0.2
    bias: float = -0.03


@dataclasses.dataclass
class LimboBar_DILC_Experiment_Settings:
    """Configuration for a LimboBar DILC experiment.

    Same as DILC_Experiment_Settings with the addition of ``limbo_bar``
    which defines the geometry of the bar to check against.
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
    u0_params: DILC_U0_Params = dataclasses.field(default_factory=DILC_U0_Params)
    u0: np.ndarray | None = None
    m0: np.ndarray | None = None


@dataclasses.dataclass(frozen=True)
class LimboBar_DILC_Trial_Data:
    """Recorded data for a single completed LimboBar DILC trial.

    Same as DILC_Trial_Data with the addition of ``limbo_bar_hit``.
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

    samples: list[dict] | None = None


class TrialResult(enum.Enum):
    ERROR = "ERROR"
    REVERT = "REVERT"
    FINISHED = "FINISHED"


class LimboBar_DILC_Experiment_State(enum.StrEnum):
    NONE = "NONE"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    FINISHED = "FINISHED"


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
    state: LimboBar_DILC_Experiment_State
    trials: list[LimboBar_DILC_Trial_Data]


# === Callbacks & Events ===========================================================================================

@callback_definition
class LimboBar_DILC_Experiment_Callbacks:
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
class LimboBar_DILC_Experiment_Events:
    experiment_initialized: Event = Event(copy_data_on_set=False)
    experiment_started: Event = Event(copy_data_on_set=False)
    experiment_finished: Event = Event(copy_data_on_set=False)
    experiment_error: Event = Event(copy_data_on_set=False)

    trajectory_loaded: Event = Event(copy_data_on_set=False)
    trajectory_started: Event = Event(copy_data_on_set=False)
    trajectory_error: Event = Event(copy_data_on_set=False)
    trajectory_finished: Event = Event(copy_data_on_set=False)

    trial_started: Event = Event(copy_data_on_set=False)
    trial_prepared: Event = Event(copy_data_on_set=False)
    trial_reverted: Event = Event(copy_data_on_set=False)
    trial_finished: Event = Event(copy_data_on_set=False)
    trial_error: Event = Event(copy_data_on_set=False)


# === WiFi Events ==================================================================================================

_LBDILC_WIFI_EVENT = WifiEvent(data_type=dict, flags=WifiEventFlag('group', str))


@wifi_event_definition
class LimboBar_DILC_WifiEvents(WifiEventContainer):
    experiment_initialized: WifiEvent = _LBDILC_WIFI_EVENT
    experiment_started: WifiEvent = _LBDILC_WIFI_EVENT
    experiment_finished: WifiEvent = _LBDILC_WIFI_EVENT
    experiment_error: WifiEvent = _LBDILC_WIFI_EVENT

    trajectory_loaded: WifiEvent = _LBDILC_WIFI_EVENT
    trajectory_started: WifiEvent = _LBDILC_WIFI_EVENT
    trajectory_error: WifiEvent = _LBDILC_WIFI_EVENT
    trajectory_finished: WifiEvent = _LBDILC_WIFI_EVENT

    trial_started: WifiEvent = _LBDILC_WIFI_EVENT
    trial_prepared: WifiEvent = _LBDILC_WIFI_EVENT
    trial_reverted: WifiEvent = _LBDILC_WIFI_EVENT
    trial_finished: WifiEvent = _LBDILC_WIFI_EVENT
    trial_error: WifiEvent = _LBDILC_WIFI_EVENT

    meta_settings_changed: WifiEvent = _LBDILC_WIFI_EVENT


# === LimboBar DILC Experiment =====================================================================================

class LimboBar_DILC_Experiment:
    """DILC experiment with limbo bar collision detection.

    Identical to ``DILC_Experiment`` except:
      - A ``LimboBar`` is created in the testbed manager on ``initialize()``.
      - After each trajectory the hit flag is read and stored in the trial.
      - The bar is reset after the robot returns to initial conditions (not
        immediately after the trajectory, to avoid false negatives on the
        return drive).
      - The bar is removed from the testbed on experiment end / error / abort.
    """

    settings: LimboBar_DILC_Experiment_Settings

    common: BILBO_Common
    j: int = 0
    N: int = 0
    trials: list[LimboBar_DILC_Trial_Data]
    state: LimboBar_DILC_Experiment_State = LimboBar_DILC_Experiment_State.NONE

    _u: np.ndarray | None = None
    _m: np.ndarray | None = None
    _Q_ilc: np.ndarray | None = None
    _Q_iml: np.ndarray | None = None
    t_vector: np.ndarray | None = None

    _finished: bool = False
    _abort_requested: bool = False

    _limbo_bar_id: str | None = None

    _WIFI_FLAGS = {'group': 'limbobar_dilc_experiment'}

    # === INIT =====================================================================================================
    def __init__(self, common: BILBO_Common,
                 estimation: BILBO_Estimation,
                 control: BILBO_Control,
                 communication: BILBO_Communication,
                 interfaces: BILBO_Interfaces,
                 experiment_handler: BILBO_ExperimentHandler,
                 settings: LimboBar_DILC_Experiment_Settings):
        self.common = common
        self.settings = settings
        self.control = control
        self.communication = communication
        self.estimation = estimation
        self.interfaces = interfaces
        self.experiment_handler = experiment_handler

        self.trials = []

        self._auto_start_trials: bool = settings.meta.auto_start_trials
        self._auto_accept_trials: bool = settings.meta.auto_accept_trials

        self.logger = Logger(f"LimboBar DILC {self.settings.id}", "DEBUG")
        self.events = LimboBar_DILC_Experiment_Events()
        self.callbacks = LimboBar_DILC_Experiment_Callbacks()

        self._logs: list[dict] = []
        self._log_capture_enabled = False

        self.wifi_events = LimboBar_DILC_WifiEvents(
            wifi=communication.wifi.wifi,
            id='limbobar_dilc_experiment',
        )

        self.common.interaction_events.abort.on(self.abort, once=True)

    # === PUBLIC METHODS ===========================================================================================

    def initialize(self):
        self.N = len(self.settings.reference)

        if self.N % 10 != 0:
            raise ValueError(
                f"Reference trajectory length N={self.N} is not a multiple of 10. "
                f"The STM32 sequencer requires trajectory lengths that are multiples of 10."
            )

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

        # --- Initial model m_0 ---
        if self.settings.m0 is None:
            self.logger.info("No initial model m0 provided. Starting with zero model.")
            self._m = np.zeros(self.N)
        else:
            self.logger.info("Using provided initial model m0")
            self._m = self.settings.m0.copy()

        self.j = 0

        self._Q_iml = self._build_q_filter(self.settings.model_lowpass, "IML model")
        self._Q_ilc = self._build_q_filter(self.settings.input_lowpass, "ILC input")

        self._finished = False
        self._abort_requested = False
        self.trials = []

        # --- Register limbo bar in the testbed manager ---
        self._register_limbo_bar()

        self.state = LimboBar_DILC_Experiment_State.INITIALIZED
        self.events.experiment_initialized.set(data={
            'settings': self.settings,
            'N': self.N,
            'duration_s': self.N * self.settings.Ts,
        })
        self.wifi_events.experiment_initialized.send(data={
            **self._wifi_data,
            'N': self.N,
            'duration_s': self.N * self.settings.Ts,
            'limbo_bar_height': self.settings.limbo_bar.height,
        }, flags=self._WIFI_FLAGS)
        self.logger.info("Experiment initialized successfully")

    # ----------------------------------------------------------------------------------------------------------
    def run(self) -> LimboBar_DILC_Results | None:
        # --- Initialization ---
        try:
            self.initialize()
        except Exception as e:
            self.logger.error(f"Failed to initialize experiment: {e}")
            self.state = LimboBar_DILC_Experiment_State.ERROR
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
            self._cleanup_limbo_bar()
            return None

        # --- Start ---
        self._start_log_capture()
        self.state = LimboBar_DILC_Experiment_State.RUNNING
        self.logger.info("=" * 60)
        self.logger.info(f"Starting LimboBar DILC experiment '{self.settings.id}'")
        self.logger.info(f"  Trials: {self.settings.J}")
        self.logger.info(f"  Trajectory length: {self.N} samples ({self.N * self.settings.Ts:.2f}s)")
        self.logger.info(f"  Limbo bar height: {self.settings.limbo_bar.height}")
        self.logger.info(f"  Auto start trials: {self._auto_start_trials}")
        self.logger.info(f"  Auto accept trials: {self._auto_accept_trials}")
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
                self.state = LimboBar_DILC_Experiment_State.ERROR
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
                self._cleanup_limbo_bar()
                return results

        # --- Post-loop ---
        if self._abort_requested:
            self.state = LimboBar_DILC_Experiment_State.ERROR
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
            self._cleanup_limbo_bar()
            return results

        # All trials completed
        self.state = LimboBar_DILC_Experiment_State.FINISHED
        self._finished = True
        self._stop_log_capture()
        results = self._build_results()
        results_filepath = self._save_results_to_file(results)

        hits = sum(1 for t in self.trials if t.limbo_bar_hit)
        self.logger.info("=" * 60)
        self.logger.info(f"LimboBar DILC experiment '{self.settings.id}' completed successfully")
        self.logger.info(f"  Completed trials: {len(self.trials)}/{self.settings.J}")
        self.logger.info(f"  Limbo bar hits: {hits}/{len(self.trials)}")
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
            'final_e_norm_ilc': float(self.trials[-1].e_norm_ilc) if self.trials else None,
            'final_e_norm_iml': float(self.trials[-1].e_norm_iml) if self.trials else None,
            'error_norms_ilc': [float(t.e_norm_ilc) for t in self.trials],
            'error_norms_iml': [float(t.e_norm_iml) for t in self.trials],
            'limbo_bar_hits': [t.limbo_bar_hit for t in self.trials],
            'results_filepath': results_filepath,
        }, flags=self._WIFI_FLAGS)
        beep(frequency='high', repeats=3)

        self._cleanup_limbo_bar()
        return results

    # ----------------------------------------------------------------------------------------------------------
    def run_trial(self) -> TrialResult:
        try:
            self.logger.info("=" * 60)
            self.logger.info(f"Trial {self.j + 1}/{self.settings.J}")
            self.logger.info("=" * 60)

            self.events.trial_started.set(data={
                'trial_index': self.j,
                'total_trials': self.settings.J,
            })
            self.callbacks.trial_started.call()
            self.wifi_events.trial_started.send(data={
                **self._wifi_data,
            }, flags=self._WIFI_FLAGS)

            # --- Step 1: Prepare the robot ---
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

            # --- Step 1b: Reset limbo bar AFTER returning to initial conditions ---
            self._reset_limbo_bar()

            # --- Step 2: Build the input trajectory ---
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

            # --- Step 3: Wait for user to start ---
            if self._auto_start_trials:
                self.logger.info("Auto-starting trial (auto_start_trials=True)")
            else:
                self.logger.info("Waiting for user to start the trial... (Resume / Abort)")

                data, trace = wait_for_events(
                    OR(
                        self.common.interaction_events.resume,
                        self.common.interaction_events.abort,
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

                if trace.caused_by(self.common.interaction_events.abort):
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
            self.logger.info("Starting trajectory execution...")
            self.interfaces.disable_external_input()
            self.control.disable_external_input()

            self.events.trajectory_started.set(data={
                'trajectory': input_trajectory,
                'trial_index': self.j,
            })
            self.callbacks.trajectory_started.call()
            self.wifi_events.trajectory_started.send(data={
                **self._wifi_data,
            }, flags=self._WIFI_FLAGS)

            trajectory_data = self.experiment_handler.run_trajectory(input_trajectory)

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

            # --- Step 4b: Read limbo bar hit state ---
            limbo_bar_hit = self._get_limbo_bar_hit()
            self.logger.info(f"Limbo bar hit: {limbo_bar_hit}")

            # --- Step 4c: Collect samples ---
            trial_samples: list | None = None
            try:
                lp = get_logging_provider()
                start_tick = trajectory_data.meta.start_tick
                end_tick = trajectory_data.meta.end_tick
                start_tick_aligned = (start_tick // 10) * 10
                end_tick_aligned = ((end_tick + 9) // 10) * 10
                current_tick = lp.get_tick()
                self.logger.debug(f"Requesting samples: ticks {start_tick_aligned}..{end_tick_aligned}, "
                                  f"current logging tick: {current_tick}")

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
                trial_samples: list = samples_container[0]

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

            n_out = len(theta_trajectory)
            if n_out != self.N:
                self.logger.warning(
                    f"Output trajectory length ({n_out}) differs from expected N={self.N}. "
                    f"Delta: {n_out - self.N} samples."
                )
                if n_out > self.N:
                    theta_trajectory = theta_trajectory[:self.N]
                else:
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
            self.logger.info(f"  Limbo bar hit: {limbo_bar_hit}")

            self.events.trajectory_finished.set(data={
                'trajectory': input_trajectory,
                'trial_index': self.j,
                'theta': theta_trajectory,
                'error': tracking_error,
                'error_norm': error_norm,
                'limbo_bar_hit': limbo_bar_hit,
            })
            self.callbacks.trajectory_finished.call()
            self.wifi_events.trajectory_finished.send(data={
                **self._wifi_data,
                'error_norm': float(error_norm),
                'max_abs_error': max_abs_error,
                'limbo_bar_hit': limbo_bar_hit,
                'reference': self.settings.reference,
                'theta': theta_trajectory,
                'error': tracking_error,
                'u': self._u,
                't': self.t_vector,
            }, flags=self._WIFI_FLAGS)

            # --- Step 6: Wait for user acceptance ---
            if self._auto_accept_trials:
                self.logger.info(f"Auto-accepting trial {self.j + 1} (error norm: {error_norm:.6f})")
            else:
                self.logger.info("Waiting for user to review... (Accept / Repeat / Abort)")

                data, trace = wait_for_events(
                    OR(
                        self.common.interaction_events.resume,
                        self.common.interaction_events.repeat,
                        self.common.interaction_events.abort,
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

                if trace.caused_by(self.common.interaction_events.abort):
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

                self.logger.info("Trial accepted by user")

            # --- Step 7: Compute ILC and IML updates ---
            self.logger.info("Computing DILC update...")

            error_iml = theta_trajectory - vec2liftedMatrix(self._m) @ self._u
            L_iml = self._compute_iml_learning_matrix(self._u)
            mp1 = self._Q_iml @ (self._m + L_iml @ error_iml)

            error_ilc = tracking_error
            L_ilc = self._compute_ilc_learning_matrix(mp1)
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
            trial_data = LimboBar_DILC_Trial_Data(
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
                limbo_bar_hit=limbo_bar_hit,
                samples=trial_samples,
            )
            self.trials.append(trial_data)

            self._u = up1
            self._m = mp1

            self.logger.info(f"Trial {self.j + 1}/{self.settings.J} completed and saved")
            self.events.trial_finished.set(data=trial_data)
            self.callbacks.trial_finished.call()
            self.wifi_events.trial_finished.send(data={
                **self._wifi_data,
                'e_norm_ilc': e_norm_ilc,
                'e_norm_iml': e_norm_iml,
                'input_change_norm': input_change_norm,
                'model_change_norm': model_change_norm,
                'limbo_bar_hit': limbo_bar_hit,
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
            self.interfaces.enable_external_input()
            self.control.enable_external_input()

    # ----------------------------------------------------------------------------------------------------------
    def prepare_trial(self) -> bool:
        self.logger.info(f"Preparing trial {self.j + 1}/{self.settings.J}...")

        if self.control.mode != BILBO_Control_Mode.BALANCING:
            self.logger.info("Switching to BALANCING mode")
            self.control.set_mode(BILBO_Control_Mode.BALANCING)
            time.sleep(1)

        if self.settings.meta.automatic_initial_conditions_reset:
            self.control.set_mode(BILBO_Control_Mode.POSITION)
            time.sleep(1)

            if self.j == 0 and self.settings.initial_conditions_u0 is not None:
                ic = self.settings.initial_conditions_u0
                self.logger.info("Using u0-specific initial conditions for first trial")
            else:
                ic = self.settings.initial_conditions
            self.logger.info(f"Navigating to initial conditions: "
                             f"x={ic.x:.3f}m, y={ic.y:.3f}m, psi={np.rad2deg(ic.psi):.1f}deg")

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

            time.sleep(0.5)

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

            time.sleep(1)
            self.control.set_mode(BILBO_Control_Mode.BALANCING)
            time.sleep(0.25)

        else:
            self.logger.info("Skipping automatic positioning (disabled in meta settings)")

        self.control.enable_tic_control(True)

        if self.settings.meta.check_if_robot_is_static:
            timeout = self.settings.meta.static_timeout_s
            self.logger.info(f"Waiting for robot to become static (timeout={timeout}s)...")
            result = wait_until(
                lambda: self.estimation.static,
                timeout_s=timeout,
                poll_period_s=0.25,
            )
            if not result:
                self.logger.error(f"Robot did not become static within {timeout} seconds")
                return False
            self.logger.info("Robot is static and ready")

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
        self.logger.info("Trial preparation complete")
        return True

    # ----------------------------------------------------------------------------------------------------------
    def abort(self, *args, **kwargs):
        self._abort_requested = True
        self.logger.warning("Abort requested — interrupting experiment")
        self.control.set_mode(BILBO_Control_Mode.BALANCING)
        self.common.interaction_events.abort.set()

    # ----------------------------------------------------------------------------------------------------------
    def set_auto_start_trials(self, value: bool):
        self._auto_start_trials = bool(value)
        self.logger.info(f"auto_start_trials set to {self._auto_start_trials}")
        self._send_meta_settings_changed()

    # ----------------------------------------------------------------------------------------------------------
    def set_auto_accept_trials(self, value: bool):
        self._auto_accept_trials = bool(value)
        self.logger.info(f"auto_accept_trials set to {self._auto_accept_trials}")
        self._send_meta_settings_changed()

    # === PRIVATE METHODS ==========================================================================================

    @property
    def _wifi_data(self) -> dict:
        return {
            'state': self.state.value,
            'experiment_id': self.settings.id,
            'trial_index': self.j,
            'total_trials': self.settings.J,
            'completed_trials': len(self.trials),
            'auto_start_trials': self._auto_start_trials,
            'auto_accept_trials': self._auto_accept_trials,
        }

    # ----------------------------------------------------------------------------------------------------------
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

    # ----------------------------------------------------------------------------------------------------------
    def _cleanup_limbo_bar(self):
        """Remove the experiment's limbo bar from the testbed manager."""
        if self._limbo_bar_id is not None:
            self.experiment_handler.testbed.remove_limbo_bar(self._limbo_bar_id)
            self.logger.info(f"Removed limbo bar '{self._limbo_bar_id}'")
            self._limbo_bar_id = None

    # ----------------------------------------------------------------------------------------------------------
    def _reset_limbo_bar(self):
        """Reset the hit flag on the experiment's limbo bar."""
        if self._limbo_bar_id is not None:
            testbed = self.experiment_handler.testbed
            bar = next((b for b in testbed.limbo_bars if b.id == self._limbo_bar_id), None)
            if bar is not None:
                bar.reset()
                self.logger.debug(f"Reset limbo bar '{self._limbo_bar_id}'")

    # ----------------------------------------------------------------------------------------------------------
    def _get_limbo_bar_hit(self) -> bool:
        """Read the hit state of the experiment's limbo bar."""
        if self._limbo_bar_id is not None:
            testbed = self.experiment_handler.testbed
            bar = next((b for b in testbed.limbo_bars if b.id == self._limbo_bar_id), None)
            if bar is not None:
                return bar.hit
        return False

    # ----------------------------------------------------------------------------------------------------------
    def _send_meta_settings_changed(self):
        self.wifi_events.meta_settings_changed.send(data={
            **self._wifi_data,
        }, flags=self._WIFI_FLAGS)

    # ----------------------------------------------------------------------------------------------------------
    def _log_capture_callback(self, log_entry: str, log: str, logger: Logger, level: int):
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
        if not self._log_capture_enabled:
            self._logs = []
            enable_redirection(self._log_capture_callback, redirect_all=False)
            self._log_capture_enabled = True

    # ----------------------------------------------------------------------------------------------------------
    def _stop_log_capture(self):
        if self._log_capture_enabled:
            disable_redirection(self._log_capture_callback)
            self._log_capture_enabled = False

    # ----------------------------------------------------------------------------------------------------------
    def _build_results(self) -> LimboBar_DILC_Results:
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

    def _save_results_to_file(self, results: LimboBar_DILC_Results) -> str | None:
        from core.utils.json_utils import writeJSON_mp

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

    # ----------------------------------------------------------------------------------------------------------
    def _build_q_filter(self, params: FIR_Design_Params, label: str) -> np.ndarray:
        h = design_zero_phase_fir(fc=params.fc, L=params.L, window=params.window)
        Q = build_Qf_zero_padded(h, self.N)
        Q = 0.5 * (Q + Q.T)
        ones = np.ones(self.N)
        dc_gain = (ones @ (Q @ ones)) / (ones @ ones)
        if abs(dc_gain) > 1e-12:
            Q = Q / dc_gain
        self.logger.info(f"Built {label} Q-filter: fc={params.fc} Hz, L={params.L}, window='{params.window}'")
        return Q

    # ----------------------------------------------------------------------------------------------------------
    def _compute_iml_learning_matrix(self, u_j: np.ndarray) -> np.ndarray:
        U = vec2liftedMatrix(u_j)
        W = np.eye(self.N)
        S = self.settings.iml_gain * (U.T @ U + 1e-6 * np.eye(self.N))
        jitter = 1e-8 * np.eye(self.N)
        A = U @ W @ U.T + S + jitter
        gain = np.linalg.solve(A, U @ W)
        return gain.T

    # ----------------------------------------------------------------------------------------------------------
    def _compute_ilc_learning_matrix(self, m_j: np.ndarray) -> np.ndarray:
        M = vec2liftedMatrix(m_j)
        W = np.eye(self.N)
        S = self.settings.ilc_gain * (M.T @ M + 1e-6 * np.eye(self.N))
        jitter = 1e-8 * np.eye(self.N)
        A = M @ W @ M.T + S + jitter
        gain = np.linalg.solve(A, M @ W)
        return gain.T
