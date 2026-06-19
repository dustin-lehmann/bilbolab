"""Host-side proxy for the SNR-adaptive DILC experiment.

Mirror of the host ``DILC_Experiment`` proxy for the robot-side
``SNR_DILC_Experiment``. It reuses the full DILC host machinery (file
resolution, settings serialization, WiFi event handling, reporting) and only
overrides three seams:

  - the WiFi event container (``snr_dilc_experiment``),
  - the robot RPC name (``run_snr_dilc_experiment``),
  - the settings type (``SNR_DILC_Experiment_Settings``).

The settings mirror the robot-side ``SNR_DILC_Experiment_Settings``: the fixed
``ilc_gain`` and FIR ``input_lowpass`` of the base DILC are replaced by the
SNR-adaptive NO-ILC parameters (``c_snr``, ``s_min``, ``s_max``, ``s_warm``,
``warm_decay``, ``r``); the IML settings (``iml_gain``, ``model_lowpass``) are
unchanged.
"""
import dataclasses

import numpy as np

from core.utils.dataclass_utils import from_dict_auto
from core.utils.yaml_utils import load_yaml

from robots.bilbo.robot.experiment.dilc.dilc import (
    DILC_Experiment,
    FIR_Design_Params,
    DILC_InitialConditions,
    DILC_Experiment_Meta_Settings,
    DILC_U0_Params,
)


# === Settings =====================================================================================================

@dataclasses.dataclass
class SNR_DILC_Experiment_Settings:
    """Host-side settings for an SNR-adaptive DILC experiment.

    Mirrors the robot-side ``SNR_DILC_Experiment_Settings``.
    """
    id: str
    description: str
    J: int
    reference: np.ndarray | list | str
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
    # SNR-adaptive s, so a single bank agent can be run solo for comparison.
    s_scale: float = 1.0
    # --- IML model learning ---
    iml_gain: float = 1.5
    # --- Common DILC fields ---
    initial_conditions_u0: DILC_InitialConditions | None = None
    meta: DILC_Experiment_Meta_Settings = dataclasses.field(default_factory=DILC_Experiment_Meta_Settings)
    u0_params: DILC_U0_Params = dataclasses.field(default_factory=DILC_U0_Params)
    u0: np.ndarray | list | str | None = None
    u0_scale: float = 1.0
    m0: np.ndarray | list | str | None = None


# === Host proxy ===================================================================================================

class SNR_DILC_Experiment(DILC_Experiment):
    """Host-side proxy for the robot's SNR-adaptive DILC experiment."""

    _WIFI_CONTAINER = 'snr_dilc_experiment'
    _RUN_FUNCTION = 'run_snr_dilc_experiment'
    _SETTINGS_TYPE = SNR_DILC_Experiment_Settings

    def __init__(self, core):
        super().__init__(core)
        self.logger.name = "SNR DILC Experiment (Host)"


# === Utility Functions ============================================================================================

def load_snr_dilc_settings_from_yaml(file_path: str) -> SNR_DILC_Experiment_Settings:
    """Load SNR DILC experiment settings from a YAML file."""
    yaml_data = load_yaml(file_path)
    return from_dict_auto(SNR_DILC_Experiment_Settings, yaml_data)
