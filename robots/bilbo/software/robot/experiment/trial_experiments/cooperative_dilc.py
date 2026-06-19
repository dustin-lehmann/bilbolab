"""
Cooperative DILC Experiment (multi-agent method, run sequentially on one robot).

This is the single-robot emulation of the cooperative DG Dual-ILC method: a bank
of ``A`` heterogeneous agents that, in simulation, run on ``A`` robots in
parallel. Here a single physical robot plays every agent in turn -- each trial
runs the robot once per agent (agent 1, then agent 2, ... then agent A), each
with that agent's own input, and only *after* all A runs are collected is the
cooperative update applied. There is no inheritance from the base DILC
experiment; this is a standalone experiment that reuses the same robot
primitives (navigation, trajectory execution, logging) and shared data
structures (events, state, results).

Per trial j:
    for i in 1..A:
        prepare (navigate to initial conditions, wait static)
        execute the robot with agent i's input u_i  ->  measured output y_i
    cooperative update (all agents at once):
        - pooled stacked-RLS identification over { (u_i, y_i) } -> shared model m
        - SNR-adaptive regulariser s_j (with warm-up floor)
        - per-agent NO-ILC own gain L_i and shared cooperative gain L_safe
        - smoothed best-performance (BP) fusion -> group input/error
        - decoupled-gain update of every u_i (own term blended with coop term)

The update law matches the simulation's ``cooperative_run``
(``external/experiments/learning/scripts/transfer_exp_draft.py``).
"""
import dataclasses
import os
import time
from datetime import datetime

import numpy as np

from core.utils.control_lib.lib_control.learning.q_filter import (
    FIR_Design_Params, design_zero_phase_fir, build_Qf_zero_padded,
)
from core.utils.control_lib.lib_control.learning.lifted import vector_to_lifted_matrix
from core.utils.data import generate_time_vector_by_length, generate_random_input
from core.utils.events import wait_for_events, OR, TIMEOUT
from core.utils.logging_utils import Logger
from core.utils.time import wait_until, interruptible_sleep
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control
from robot.control.bilbo_control_definitions import BILBO_Control_Mode
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment import BILBO_InputTrajectory, BILBO_ExperimentHandler
from robot.interfaces.bilbo_interfaces import BILBO_Interfaces
from robot.core import get_logging_provider
from robot.lowlevel.stm32_general import MAX_STEPS_TRAJECTORY
from robot.utilities.buzzer import beep

# Reused data structures from the base DILC experiment (no behaviour inherited).
from robot.experiment.trial_experiments.dilc import (
    DILC_InitialConditions,
    DILC_Experiment_Meta_Settings,
    DILC_Requirements,
    DILC_U0_Params,
    DILC_Phase,
    DILC_Experiment_State,
    DILC_Experiment_Events,
    DILC_Experiment_Callbacks,
    DILC_WifiEvents,
    DILC_Results,
    DILC_Results_Meta,
    TrialResult,
)

_JITTER = 1e-8


# === Settings =====================================================================================================

@dataclasses.dataclass
class CooperativeDILC_Experiment_Settings:
    """Configuration for a cooperative (multi-agent) DILC experiment run on one
    robot. All agents track the same ``reference``; the bank heterogeneity is in
    the per-agent regulariser factors ``het_gain_factors``.

    Attributes:
        n_agents: bank size A (number of agents replayed per trial).
        het_gain_factors: per-agent gamma_i scaling the regulariser s_i = gamma_i*s.
            Length must be >= n_agents (extra entries ignored).
        gamma_safe: shared cooperative gain factor (s_coop = gamma_safe*s).
        alpha: own/cooperative blend (stubbornness) in [0, 1].
        bp_sharpness: smoothed best-performance selectivity (large -> hard max).
        bp_window: number of trials averaged in the BP error history.
        c_snr, s_min, s_max: SNR-adaptive regulariser scale and bounds.
        s_warm, warm_decay: warm-up regulariser floor and its geometric decay.
        group_r: per-agent input-magnitude weight r for the own-term Q-filter
            (0 -> no Q-filter). Length must be >= n_agents.
        iml_gain, iml_forgetting, rho_iml: pooled RLS identification parameters.
        kappa_kick: per-agent initial impulse kick (tap shifted by agent index).
        kappa_explore, explore_decay: rotating exploration-probe amplitude/decay.
        model_lowpass: IML model Q-filter (FIR low-pass).
    """
    id: str
    description: str
    J: int
    reference: np.ndarray
    Ts: float
    initial_conditions: DILC_InitialConditions
    model_lowpass: FIR_Design_Params
    # --- Bank / cooperation ---
    n_agents: int = 3
    het_gain_factors: list = dataclasses.field(default_factory=lambda: [1e-3, 1e-1, 10.0])
    gamma_safe: float = 1e-2
    alpha: float = 0.5
    bp_sharpness: float = 1e6
    bp_window: int = 2
    # --- SNR-adaptive NO-ILC update ---
    c_snr: float = 0.1
    s_min: float = 1e-4
    s_max: float = 10.0
    s_warm: float = 0.3
    warm_decay: float = 0.4
    group_r: list = dataclasses.field(default_factory=lambda: [0.0, 0.0, 0.0])
    # --- Pooled RLS identification ---
    iml_gain: float = 1.5
    iml_forgetting: float = 0.95
    rho_iml: float = 1e-5
    # --- Initial excitation ---
    kappa_kick: float = 1.0
    kappa_explore: float = 0.3
    explore_decay: float = 0.85
    # --- Common DILC fields ---
    initial_conditions_u0: DILC_InitialConditions | None = None
    meta: DILC_Experiment_Meta_Settings = dataclasses.field(default_factory=DILC_Experiment_Meta_Settings)
    requirements: DILC_Requirements = dataclasses.field(default_factory=DILC_Requirements)
    u0_params: DILC_U0_Params = dataclasses.field(default_factory=DILC_U0_Params)
    u0: np.ndarray | None = None       # shared initial input for every agent (None -> random)
    u0_scale: float = 1.0
    m0: np.ndarray | None = None       # shared initial model (None -> zeros)


# === Trial data / results =========================================================================================

@dataclasses.dataclass(frozen=True)
class CooperativeDILC_Trial_Data:
    """Recorded data for one cooperative trial (all agents)."""
    index: int
    t: np.ndarray
    leader: int                         # BP-selected agent index
    u_per_agent: np.ndarray             # (A, N) applied inputs (with probe)
    y_per_agent: np.ndarray             # (A, N) measured outputs
    u_next_per_agent: np.ndarray        # (A, N) updated inputs for next trial
    e_norm_per_agent: np.ndarray        # (A,) measured tracking-error norms
    m: np.ndarray                       # shared model after this trial
    e_norm_ilc: float                   # leader's tracking-error norm
    e_norm_iml: float                   # pooled RLS residual norm
    s_applied: float                    # SNR-adaptive regulariser used
    bp_weights: np.ndarray              # (A,) fusion weights
    samples: list | None = None


# === Experiment ===================================================================================================

class CooperativeDILC_Experiment:
    """Standalone single-robot cooperative DG Dual-ILC experiment."""

    _WIFI_FLAGS = None

    def __init__(self, common: BILBO_Common,
                 estimation: BILBO_Estimation,
                 control: BILBO_Control,
                 communication: BILBO_Communication,
                 interfaces: BILBO_Interfaces,
                 experiment_handler: BILBO_ExperimentHandler,
                 settings: CooperativeDILC_Experiment_Settings):
        self.common = common
        self.settings = settings
        self.control = control
        self.communication = communication
        self.estimation = estimation
        self.interfaces = interfaces
        self.experiment_handler = experiment_handler

        self.A = int(settings.n_agents)
        self.N = 0
        self.j = 0
        self.t_vector = None
        self.trials: list[CooperativeDILC_Trial_Data] = []
        self.phase = DILC_Phase.IDLE
        self.state = DILC_Experiment_State.NONE

        self._u: list[np.ndarray] = []     # per-agent learned input (no probe)
        self._m: np.ndarray | None = None  # shared pooled model
        self._Sj: np.ndarray | None = None
        self._Q_iml: np.ndarray | None = None
        self._e_pred_hist: list[list[float]] = []
        self._e_norm_sq_avg = 0.0
        self._abort_requested = False
        self._finished = False
        self._logs: list[dict] = []

        self._auto_start_trials = settings.meta.auto_start_trials
        self._auto_accept_trials = settings.meta.auto_accept_trials

        self.logger = Logger(f"Cooperative DILC {settings.id}", "DEBUG")
        self.events = DILC_Experiment_Events()
        self.callbacks = DILC_Experiment_Callbacks()
        self.wifi_events = DILC_WifiEvents(
            wifi=communication.wifi.wifi,
            id='cooperative_dilc_experiment',
        )
        self.common.interaction_events.stop.on(self.stop, once=True)

    # === Public control ===========================================================================================

    def set_auto_start_trials(self, value: bool):
        self._auto_start_trials = bool(value)

    def set_auto_accept_trials(self, value: bool):
        self._auto_accept_trials = bool(value)

    def stop(self, *args, **kwargs):
        self._abort_requested = True
        self.logger.warning("Abort requested — interrupting experiment")
        self.control.set_mode(BILBO_Control_Mode.BALANCING)
        self.common.interaction_events.stop.set()

    @property
    def _wifi_data(self) -> dict:
        return {
            'state': self.state.value,
            'phase': self.phase.value,
            'experiment_id': self.settings.id,
            'trial_index': self.j,
            'total_trials': self.settings.J,
            'completed_trials': len(self.trials),
            'n_agents': self.A,
        }

    # === Initialization ===========================================================================================

    def initialize(self):
        s = self.settings
        if not s.requirements.tracker or self.common.is_tracker_connected() or True:
            pass  # requirements are advisory here; navigation guards handle absence

        self.N = len(s.reference)
        if self.N % 10 != 0:
            raise ValueError(f"Reference length N={self.N} must be a multiple of 10 (STM32 sequencer).")
        if self.N > MAX_STEPS_TRAJECTORY:
            raise ValueError(f"Reference length N={self.N} exceeds MAX_STEPS_TRAJECTORY={MAX_STEPS_TRAJECTORY}.")

        self.t_vector = generate_time_vector_by_length(num_samples=self.N, dt=s.Ts)

        # Shared initial input for every agent.
        if s.u0 is None:
            u0 = generate_random_input(t_vector=self.t_vector,
                                       f_cutoff=s.u0_params.f_cutoff,
                                       sigma_I=s.u0_params.sigma,
                                       bias=s.u0_params.bias)
        else:
            u0 = np.asarray(s.u0, dtype=float).copy()
        u0 = u0 * s.u0_scale
        self._u = [u0.copy() for _ in range(self.A)]

        # Shared initial model.
        self._m = (np.zeros(self.N) if s.m0 is None
                   else np.asarray(s.m0, dtype=float).copy())

        self._Sj = np.zeros((self.N, self.N))
        self._Q_iml = self._build_q_filter(s.model_lowpass, "IML model")
        self._e_pred_hist = [[] for _ in range(self.A)]
        self._e_norm_sq_avg = float(np.linalg.norm(s.reference) ** 2)
        self.j = 0
        self.trials = []
        self._abort_requested = False
        self._finished = False
        self.phase = DILC_Phase.IDLE

        self.state = DILC_Experiment_State.INITIALIZED
        self.events.experiment_initialized.set(data={'settings': s, 'N': self.N})
        self.wifi_events.experiment_initialized.send(
            data={**self._wifi_data, 'N': self.N,
                  'duration_s': self.N * s.Ts}, flags=self._WIFI_FLAGS)
        self.logger.info(f"Initialized cooperative DILC: A={self.A}, N={self.N}, J={s.J}")

    def _build_q_filter(self, params: FIR_Design_Params, label: str) -> np.ndarray:
        h = design_zero_phase_fir(fc=params.fc, L=params.L, window=params.window)
        Q = build_Qf_zero_padded(h, self.N)
        Q = 0.5 * (Q + Q.T)
        ones = np.ones(self.N)
        dc = (ones @ (Q @ ones)) / (ones @ ones)
        if abs(dc) > 1e-12:
            Q = Q / dc
        self.logger.info(f"Built {label} Q-filter: fc={params.fc}, L={params.L}")
        return Q

    # === Run ======================================================================================================

    def run(self) -> DILC_Results | None:
        try:
            self.initialize()
        except Exception as e:
            self.logger.error(f"Failed to initialize experiment: {e}")
            self.state = DILC_Experiment_State.ERROR
            self.wifi_events.experiment_error.send(
                data={**self._wifi_data, 'message': f"Initialization failed: {e}"},
                flags=self._WIFI_FLAGS)
            return None

        self.state = DILC_Experiment_State.RUNNING
        self.events.experiment_started.set(data={'settings': self.settings})
        self.wifi_events.experiment_started.send(
            data={**self._wifi_data, 'N': self.N,
                  'duration_s': self.N * self.settings.Ts}, flags=self._WIFI_FLAGS)

        while self.j < self.settings.J:
            if self._abort_requested:
                self.logger.warning("Experiment aborted by external request")
                break
            result = self.run_trial()
            if result == TrialResult.FINISHED:
                continue
            if result == TrialResult.REVERT:
                continue
            if result == TrialResult.ERROR:
                self.state = DILC_Experiment_State.ERROR
                self._finished = True
                results = self._build_results()
                fp = self._save_results_to_file(results)
                self.wifi_events.experiment_error.send(
                    data={**self._wifi_data, 'message': f"trial {self.j + 1} failed",
                          'results_filepath': fp}, flags=self._WIFI_FLAGS)
                beep(frequency='low', repeats=3)
                return results

        self.phase = DILC_Phase.IDLE
        self.state = (DILC_Experiment_State.ERROR if self._abort_requested
                      else DILC_Experiment_State.FINISHED)
        self._finished = True
        results = self._build_results()
        fp = self._save_results_to_file(results)
        self.events.experiment_finished.set(data=results)
        self.wifi_events.experiment_finished.send(
            data={**self._wifi_data,
                  'error_norms_ilc': [float(t.e_norm_ilc) for t in self.trials],
                  'error_norms_iml': [float(t.e_norm_iml) for t in self.trials],
                  'results_filepath': fp}, flags=self._WIFI_FLAGS)
        beep(frequency='high', repeats=3)
        return results

    # === One cooperative trial ====================================================================================

    def run_trial(self) -> TrialResult:
        try:
            self.logger.info("=" * 60)
            self.logger.info(f"Cooperative trial {self.j + 1}/{self.settings.J} "
                             f"({self.A} agents)")
            self.phase = DILC_Phase.PREPARING
            self.events.trial_started.set(data={'trial_index': self.j})
            self.wifi_events.trial_started.send(data={**self._wifi_data},
                                                flags=self._WIFI_FLAGS)

            # --- Build this trial's per-agent applied inputs (kick + probe) ---
            u_exec = self._build_agent_inputs()

            # --- Run the robot once per agent ---
            y_per = []
            for i in range(self.A):
                if self._abort_requested:
                    return TrialResult.ERROR
                self.logger.info(f"--- Agent {i + 1}/{self.A} ---")
                theta = self._run_agent(i, u_exec[i])
                if theta is None:
                    return TrialResult.ERROR
                y_per.append(theta)

            # --- Optional user acceptance gate (once per trial) ---
            if not self._auto_accept_trials:
                gate = self._wait_for_acceptance()
                if gate == TrialResult.ERROR:
                    return TrialResult.ERROR
                if gate == TrialResult.REVERT:
                    return TrialResult.REVERT

            # --- Cooperative update ---
            self.phase = DILC_Phase.COMPUTING_UPDATE
            trial_data = self._cooperative_update(u_exec, y_per)
            self.trials.append(trial_data)

            self.wifi_events.trial_finished.send(data={
                **self._wifi_data,
                'leader': int(trial_data.leader),
                'e_norm_ilc': float(trial_data.e_norm_ilc),
                'e_norm_iml': float(trial_data.e_norm_iml),
                's_applied': float(trial_data.s_applied),
                'bp_weights': trial_data.bp_weights.tolist(),
                'e_norm_per_agent': trial_data.e_norm_per_agent.tolist(),
                't': self.t_vector,
                'reference': self.settings.reference,
                # Leader's trace as the primary u/theta (for the base DILC panel).
                'u': trial_data.u_per_agent[trial_data.leader],
                'theta': trial_data.y_per_agent[trial_data.leader],
                'm': trial_data.m,
                # Per-agent traces for the cooperative GUI (A x N each).
                'u_per_agent': trial_data.u_per_agent.tolist(),
                'y_per_agent': trial_data.y_per_agent.tolist(),
            }, flags=self._WIFI_FLAGS)

            self.j += 1
            return TrialResult.FINISHED

        except Exception as e:
            self.logger.error(f"Unexpected error during cooperative trial: {e}")
            self.wifi_events.trial_error.send(
                data={**self._wifi_data, 'message': str(e)}, flags=self._WIFI_FLAGS)
            return TrialResult.ERROR
        finally:
            self.interfaces.enable_external_input()
            self.control.enable_external_input()
            self.control.enable_psi_control(False)
            self.estimation.set_tracker_updates_enabled(True)

    def _build_agent_inputs(self) -> list[np.ndarray]:
        """Per-agent applied input for this trial: the learned input plus the
        trial-0 impulse kick and a rotating exploration probe (both per agent)."""
        s = self.settings
        probe_amp = s.kappa_explore * (s.explore_decay ** self.j)
        u_exec = []
        for i in range(self.A):
            ui = self._u[i].copy()
            if self.j == 0:
                ui[i % self.N] += s.kappa_kick
            ui[(i + self.A * self.j) % self.N] += probe_amp
            u_exec.append(ui)
        return u_exec

    # === Robot primitives (reused from the base flow, standalone) =================================================

    def _run_agent(self, i: int, u_exec: np.ndarray) -> np.ndarray | None:
        """Prepare the robot and execute one agent's input; return measured theta."""
        if not self._prepare():
            self.logger.error(f"Preparation failed for agent {i + 1}")
            return None

        self.phase = DILC_Phase.RUNNING_TRAJECTORY
        self.interfaces.disable_external_input()
        self.control.disable_external_input()
        if self.settings.meta.enable_psi_control:
            self.control.enable_psi_control(True)
        if self.settings.meta.disable_tracker_during_trajectory:
            self.estimation.set_tracker_updates_enabled(False)

        trajectory = BILBO_InputTrajectory.from_vector(
            vector=u_exec, name=f"Trial {self.j + 1} agent {i + 1}",
            id=self.j + 1, delta=self.common.config.model.trajectory_delta)
        trajectory_data = self.experiment_handler.run_trajectory(trajectory)

        if self.settings.meta.enable_psi_control:
            self.control.enable_psi_control(False)
        if self.settings.meta.disable_tracker_during_trajectory:
            self.estimation.set_tracker_updates_enabled(True)

        if trajectory_data is None:
            self.logger.error(f"Trajectory execution failed for agent {i + 1}")
            return None

        theta = np.asarray([st.theta for st in
                            trajectory_data.data.state_trajectory.states])
        # Align to N (truncate or pad-with-last like the base experiment).
        n_out = len(theta)
        if n_out > self.N:
            theta = theta[:self.N]
        elif n_out < self.N:
            theta = np.pad(theta, (0, self.N - n_out), mode='constant',
                           constant_values=(theta[-1] if n_out > 0 else 0.0))
        err_norm = float(np.linalg.norm(self.settings.reference - theta))
        self.logger.info(f"  Agent {i + 1} tracking error norm: {err_norm:.6f}")
        return theta

    def _prepare(self) -> bool:
        """Navigate to the initial conditions and wait for the robot to settle."""
        s = self.settings
        stop = self.common.interaction_events.stop
        if self.control.mode != BILBO_Control_Mode.BALANCING:
            self.control.set_mode(BILBO_Control_Mode.BALANCING)
            if not interruptible_sleep(1, stop):
                return False

        if s.meta.automatic_initial_conditions_reset:
            self.control.set_mode(BILBO_Control_Mode.POSITION)
            if not interruptible_sleep(1, stop):
                return False
            ic = (s.initial_conditions_u0 if (self.j == 0 and s.initial_conditions_u0)
                  else s.initial_conditions)
            if not self.control.position_control.move_to_point(
                    x=ic.x, y=ic.y, blocking=True, timeout=10):
                self.logger.error("Failed to reach initial position")
                return False
            if not interruptible_sleep(0.5, stop):
                return False
            if not self.control.position_control.turn_to_heading(
                    heading=ic.psi, max_angular_speed=np.deg2rad(180),
                    blocking=True, timeout=10):
                self.logger.error("Failed to reach initial heading")
                return False
            if not interruptible_sleep(1, stop):
                return False
            self.control.set_mode(BILBO_Control_Mode.BALANCING)
            if not interruptible_sleep(0.25, stop):
                return False

        self.control.enable_tic_control(True)
        if s.meta.check_if_robot_is_static:
            if not wait_until(lambda: self.estimation.static or self._abort_requested,
                              timeout_s=s.meta.static_timeout_s, poll_period_s=0.25):
                self.logger.error("Robot did not become static in time")
                return False
            if self._abort_requested:
                return False
        time.sleep(1)
        return True

    def _wait_for_acceptance(self) -> TrialResult | None:
        self.phase = DILC_Phase.WAITING_FOR_ACCEPTANCE
        self.logger.info("Waiting for user to review... (Accept / Repeat / Abort)")
        data, trace = wait_for_events(
            OR(self.common.interaction_events.resume,
               self.common.interaction_events.repeat,
               self.common.interaction_events.stop),
            timeout=120.0)
        if data is TIMEOUT:
            return TrialResult.ERROR
        if trace.caused_by(self.common.interaction_events.stop):
            return TrialResult.ERROR
        if trace.caused_by(self.common.interaction_events.repeat):
            return TrialResult.REVERT
        return None

    # === Cooperative update (ported from the simulation) ==========================================================

    def _cooperative_update(self, u_exec: list[np.ndarray],
                            y_per: list[np.ndarray]) -> CooperativeDILC_Trial_Data:
        s = self.settings
        A, N = self.A, self.N
        ref = np.asarray(s.reference, dtype=float)
        gamma = np.asarray(s.het_gain_factors[:A], dtype=float)
        group_r = (s.group_r or [0.0] * A)

        # --- Pooled stacked-RLS identification over all agents' (u, y) ---
        U_per = [vector_to_lifted_matrix(ui) for ui in u_exec]
        U_st = np.vstack(U_per)
        y_st = np.hstack(y_per)
        smax = max(float(np.linalg.norm(U_st, 2)), 1e-12)
        W = (1.0 / smax) * np.eye(U_st.shape[0])
        R = s.rho_iml * np.eye(N)
        Sjm1 = s.iml_forgetting * self._Sj
        self._Sj = Sjm1 + U_st.T @ W @ U_st + R
        Amat = U_st.T @ W @ U_st + Sjm1 + _JITTER * np.eye(N)
        Lm = np.linalg.solve(Amat, U_st.T @ W)
        Qm = np.linalg.solve(Amat + R, U_st.T @ W @ U_st + Sjm1)
        m = Qm @ (self._m + Lm @ (y_st - U_st @ self._m))
        # Optional IML output-Q-filter (iteration-domain robustness).
        m = self._Q_iml @ m

        ep = y_st - U_st @ m
        sigma_n = float(np.sqrt(np.linalg.norm(ep) ** 2 / (N * A)))

        # --- SNR-adaptive regulariser with warm-up floor ---
        denom = max(self._e_norm_sq_avg, sigma_n ** 2 * N * 0.1)
        s_snr = float(np.clip(s.c_snr * sigma_n ** 2 * N / denom, s.s_min, s.s_max))
        s_base = max(s_snr, s.s_warm * (s.warm_decay ** self.j))

        # --- NO-ILC gains: per-agent own gain (+ optional Q from group_r) and
        #     the shared cooperative gain L_safe ---
        M = vector_to_lifted_matrix(m)
        MtM = M.T @ M
        L_per, Q_per = [], []
        for i in range(A):
            H = MtM + (s_base * gamma[i] + _JITTER) * np.eye(N)
            ri = float(group_r[i])
            if ri > 0.0:
                HR = H + ri * np.eye(N)
                L_per.append(np.linalg.solve(HR, M.T))
                Q_per.append(np.linalg.solve(HR, H))
            else:
                L_per.append(np.linalg.solve(H, M.T))
                Q_per.append(np.eye(N))
        Hs = MtM + (s_base * s.gamma_safe + _JITTER) * np.eye(N)
        L_safe = np.linalg.solve(Hs, M.T)

        # --- Smoothed best-performance fusion ---
        et_per = [ref - y for y in y_per]
        for i in range(A):
            self._e_pred_hist[i].append(float(np.linalg.norm(ref - M @ self._u[i])))
        smoothed = np.array([float(np.mean(self._e_pred_hist[i][-s.bp_window:]))
                             for i in range(A)])
        ex = np.exp(-s.bp_sharpness * (smoothed - smoothed.min()))
        w = ex / ex.sum()
        leader = int(np.argmax(w))
        u_g = sum(w[i] * self._u[i] for i in range(A))
        et_g = sum(w[i] * et_per[i] for i in range(A))

        # --- Decoupled-gain update: own term (with Q-filter) + cooperative term ---
        alpha = s.alpha
        u_next = [alpha * (Q_per[i] @ (self._u[i] + L_per[i] @ et_per[i]))
                  + (1.0 - alpha) * (u_g + L_safe @ et_g) for i in range(A)]

        e_norm_per_agent = np.array([float(np.linalg.norm(e)) for e in et_per])
        self._e_norm_sq_avg = float(np.mean(e_norm_per_agent ** 2))

        # Commit state for the next trial.
        self._u = u_next
        self._m = m

        self.logger.info(
            f"  pooled RLS: sigma_n={sigma_n:.5f} s={s_base:.3e} leader=agent{leader + 1} "
            f"e_norm(leader)={e_norm_per_agent[leader]:.4f}")

        return CooperativeDILC_Trial_Data(
            index=self.j,
            t=self.t_vector,
            leader=leader,
            u_per_agent=np.asarray(u_exec),
            y_per_agent=np.asarray(y_per),
            u_next_per_agent=np.asarray(u_next),
            e_norm_per_agent=e_norm_per_agent,
            m=m.copy(),
            e_norm_ilc=float(e_norm_per_agent[leader]),
            e_norm_iml=float(np.linalg.norm(ep)),
            s_applied=float(s_base),
            bp_weights=w.copy(),
        )

    # === Results ==================================================================================================

    def _build_results(self) -> DILC_Results:
        meta = DILC_Results_Meta(
            robot_id=self.common.id,
            date=datetime.now().isoformat(),
            robot_config=self.common.config,
            control_config=self.control.get_control_config(),
            settings=self.settings,
            logs=self._logs,
        )
        return DILC_Results(meta=meta, state=self.state, trials=self.trials)

    def _save_results_to_file(self, results) -> str | None:
        from core.utils.json_utils import writeJSON_mp
        experiments_dir = os.path.expanduser("~/robot/experiments")
        os.makedirs(experiments_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = os.path.join(experiments_dir,
                                f"cooperative_dilc_{self.settings.id}_{timestamp}.json")
        self.logger.info(f"Saving cooperative DILC results to {filepath} ...")
        if writeJSON_mp(filepath, results, convert_dataclass=True):
            return filepath
        self.logger.error(f"Failed to save cooperative DILC results to {filepath}")
        return None
