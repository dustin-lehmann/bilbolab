"""
SNR-adaptive DILC Experiment (model-free Dual-ILC, single agent).

Extends the standard DILC experiment by replacing the fixed-gain ILC *input*
update + FIR Q-filter with a norm-optimal (NO-ILC) update whose regularisation
is adapted to the measured signal-to-noise ratio each trial, with a warm-up
floor and a model-derived Q-filter from an input-magnitude weight ``r``:

    sigma_n = ||e_iml|| / sqrt(N)                              (online noise est.)
    s_snr   = clip( c * sigma_n^2 * N / ||e_ilc||^2, s_min, s_max )
    s_j     = max( s_snr, s_warm * warm_decay^j )              (warm-up floor)
    L_ilc   = (M^T M + s_j I)^-1 M^T                           (NO-ILC gain)
    Q_r     = (M^T M + (s_j + r) I)^-1 (M^T M + s_j I)         (Q-filter from r)
    u_{j+1} = Q_r (u_j + L_ilc e_ilc)

Here ``M = M(m_{j+1})`` is the lifted (lower-triangular Toeplitz) matrix of the
just-updated model. The IML model-learning loop (``m_{j+1}``) is inherited
unchanged from the base DILC; only the ILC input update is overridden.

Key differences from the base DILC experiment:
  - Settings drop ``ilc_gain`` and the FIR ``input_lowpass`` (Q_ilc) and add the
    SNR-adaptive parameters (``c_snr``, ``s_min``, ``s_max``), the warm-up
    schedule (``s_warm``, ``warm_decay``) and the Q-filter weight ``r``.
  - The ILC input update law is replaced via ``_compute_ilc_update``.
  - The ILC Q-filter is model-derived per trial, so ``_build_ilc_q_filter``
    returns identity.
  - WiFi events are routed under ``snr_dilc_experiment`` and results are saved
    with the ``snr_dilc_`` filename prefix.
"""
import dataclasses
import os
from datetime import datetime

import numpy as np

from core.utils.control_lib.lib_control.learning.lifted import vector_to_lifted_matrix
from core.utils.control_lib.lib_control.learning.q_filter import FIR_Design_Params

from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment import BILBO_ExperimentHandler
from robot.interfaces.bilbo_interfaces import BILBO_Interfaces
from robot.experiment.trial_experiments.dilc import (
    DILC_Experiment,
    DILC_InitialConditions,
    DILC_Experiment_Meta_Settings,
    DILC_Requirements,
    DILC_U0_Params,
    DILC_Results,
    DILC_Results_Meta,
    DILC_WifiEvents,
)

# Numerical jitter added to the lifted normal matrix for invertibility.
_JITTER = 1e-8


# === Settings =====================================================================================================

@dataclasses.dataclass
class SNR_DILC_Experiment_Settings:
    """Configuration for an SNR-adaptive DILC experiment.

    Mirrors ``DILC_Experiment_Settings`` but the fixed ``ilc_gain`` and the FIR
    ``input_lowpass`` (Q_ilc) are replaced by the SNR-adaptive NO-ILC update
    parameters. The IML model-learning settings (``iml_gain``,
    ``model_lowpass``) are unchanged.

    Attributes:
        c_snr: SNR regulariser scale ``c`` (larger -> more regularisation).
        s_min, s_max: bounds on the SNR-adaptive regulariser ``s``.
        s_warm: warm-up regulariser floor at trial 0.
        warm_decay: geometric decay of the warm-up floor over trials.
        r: input-magnitude weight defining the NO-ILC Q-filter (0 disables it).
    """
    id: str
    description: str
    J: int
    reference: np.ndarray
    Ts: float
    initial_conditions: DILC_InitialConditions
    model_lowpass: FIR_Design_Params                       # IML Q-filter (Q_iml)
    # --- SNR-adaptive NO-ILC input update ---
    c_snr: float = 0.1
    s_min: float = 1e-4
    s_max: float = 10.0
    s_warm: float = 0.3
    warm_decay: float = 0.4
    r: float = 0.0
    # Per-agent regulariser factor (the bank's gamma_i): multiplies the final
    # SNR-adaptive s. 1.0 -> the plain SNR agent; use < 1 for an aggressive
    # tuning and > 1 for a conservative one, to reproduce a single bank agent
    # run solo for comparison against the cooperative experiment.
    s_scale: float = 1.0
    # --- IML model learning (inherited behaviour) ---
    iml_gain: float = 1.5
    # --- Common DILC fields ---
    initial_conditions_u0: DILC_InitialConditions | None = None
    meta: DILC_Experiment_Meta_Settings = dataclasses.field(default_factory=DILC_Experiment_Meta_Settings)
    requirements: DILC_Requirements = dataclasses.field(default_factory=DILC_Requirements)
    u0_params: DILC_U0_Params = dataclasses.field(default_factory=DILC_U0_Params)
    u0: np.ndarray | None = None
    u0_scale: float = 1.0
    m0: np.ndarray | None = None


# === SNR DILC Experiment ==========================================================================================

class SNR_DILC_Experiment(DILC_Experiment):
    """DILC with an SNR-adaptive, norm-optimal ILC input update.

    Inherits the full DILC experiment flow (trial loop, IML model update, user
    interaction, prepare_trial, stop handling) and overrides only the ILC input
    update law and its Q-filter. See the module docstring for the update.
    """

    def __init__(self, common: BILBO_Common,
                 estimation: BILBO_Estimation,
                 control: BILBO_Control,
                 communication: BILBO_Communication,
                 interfaces: BILBO_Interfaces,
                 experiment_handler: BILBO_ExperimentHandler,
                 settings: SNR_DILC_Experiment_Settings):
        super().__init__(common, estimation, control, communication,
                         interfaces, experiment_handler, settings)
        self.logger.name = f"SNR DILC {settings.id}"

        # Route WiFi events to the host-side SNR DILC proxy container.
        self.wifi_events = DILC_WifiEvents(
            wifi=communication.wifi.wifi,
            id='snr_dilc_experiment',
        )

    # === Overridden update law ====================================================================================

    def _build_ilc_q_filter(self) -> np.ndarray:
        """The SNR Q-filter is model-derived and rebuilt each trial inside
        ``_compute_ilc_update``; no fixed FIR matrix is needed."""
        return np.eye(self.N)

    def _compute_ilc_update(self, u_j: np.ndarray, mp1: np.ndarray,
                            error_ilc: np.ndarray, error_iml: np.ndarray):
        """SNR-adaptive NO-ILC input update (see module docstring)."""
        s = self.settings
        N = self.N

        # Online measurement-noise estimate from the IML prediction residual.
        sigma_n = float(np.linalg.norm(error_iml)) / np.sqrt(max(N, 1))
        e_sq = float(np.linalg.norm(error_ilc)) ** 2

        # Inverse-SNR regulariser, floored so it stays bounded once the tracking
        # error drops to the measurement-noise level.
        denom = max(e_sq, sigma_n ** 2 * N * 0.1)
        s_snr = float(np.clip(s.c_snr * sigma_n ** 2 * N / denom,
                              s.s_min, s.s_max))
        # Warm-up floor: conservative while the model is still uncertain;
        # then the per-agent gamma factor (s_scale) scales the whole schedule.
        s_j = s.s_scale * max(s_snr, s.s_warm * (s.warm_decay ** self.j))

        # Norm-optimal learning gain L and Q-filter Q from the input-magnitude
        # weight r, built against the just-updated model m_{j+1}:
        #   H  = M^T M + s_j I
        #   L  = (H + r I)^-1 M^T
        #   Q  = (H + r I)^-1 H        (= I when r = 0)
        M = vector_to_lifted_matrix(mp1)
        H = M.T @ M + (s_j + _JITTER) * np.eye(N)
        if s.r > 0.0:
            HR = H + s.r * np.eye(N)
            L_ilc = np.linalg.solve(HR, M.T)
            Q = np.linalg.solve(HR, H)
        else:
            L_ilc = np.linalg.solve(H, M.T)
            Q = np.eye(N)

        up1 = Q @ (u_j + L_ilc @ error_ilc)

        self.logger.info(
            f"  SNR-ILC: sigma_n={sigma_n:.5f} s_snr={s_snr:.3e} "
            f"s_j={s_j:.3e} r={s.r:.3e}")
        return up1, L_ilc

    # === Result handling ==========================================================================================

    def _build_results(self) -> DILC_Results:
        """Reuse the base DILC results container (carries the SNR settings)."""
        meta = DILC_Results_Meta(
            robot_id=self.common.id,
            date=datetime.now().isoformat(),
            robot_config=self.common.config,
            control_config=self.control.get_control_config(),
            settings=self.settings,
            logs=self._logs,
        )
        return DILC_Results(meta=meta, state=self.state, trials=self.trials)

    def _save_results_to_file(self, results: DILC_Results) -> str | None:
        from core.utils.json_utils import writeJSON_mp

        experiments_dir = os.path.expanduser("~/robot/experiments")
        os.makedirs(experiments_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"snr_dilc_{self.settings.id}_{timestamp}.json"
        filepath = os.path.join(experiments_dir, filename)

        self.logger.info(f"Saving SNR DILC results to {filepath} ...")
        if writeJSON_mp(filepath, results, convert_dataclass=True):
            self.logger.info(f"Saved SNR DILC results to {filepath}")
            return filepath
        self.logger.error(f"Failed to save SNR DILC results to {filepath}")
        return None
