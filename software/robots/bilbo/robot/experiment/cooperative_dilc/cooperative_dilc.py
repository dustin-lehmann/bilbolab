"""Host-side proxy for the cooperative (multi-agent) DILC experiment.

The robot-side experiment is standalone (``trial_experiments/cooperative_dilc.py``)
but emits the same WiFi-event structure as the base DILC, so this host proxy
reuses the DILC host machinery (file resolution, serialization, event handling,
GUI app) and only overrides three seams:

  - WiFi event container (``cooperative_dilc_experiment``),
  - robot RPC name (``run_cooperative_dilc_experiment``),
  - settings type (``CooperativeDILC_Experiment_Settings``).

Settings mirror the robot-side ``CooperativeDILC_Experiment_Settings``.
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
class CooperativeDILC_Experiment_Settings:
    """Host-side settings for a cooperative (multi-agent) DILC experiment.

    Mirrors the robot-side ``CooperativeDILC_Experiment_Settings``.
    """
    id: str
    description: str
    J: int
    reference: np.ndarray | list | str
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
    u0_params: DILC_U0_Params = dataclasses.field(default_factory=DILC_U0_Params)
    u0: np.ndarray | list | str | None = None
    u0_scale: float = 1.0
    m0: np.ndarray | list | str | None = None


# === Host proxy ===================================================================================================

class CooperativeDILC_Experiment(DILC_Experiment):
    """Host-side proxy for the robot's cooperative (multi-agent) DILC experiment."""

    _WIFI_CONTAINER = 'cooperative_dilc_experiment'
    _RUN_FUNCTION = 'run_cooperative_dilc_experiment'
    _SETTINGS_TYPE = CooperativeDILC_Experiment_Settings

    def __init__(self, core):
        super().__init__(core)
        self.logger.name = "Cooperative DILC Experiment (Host)"


# === Utility Functions ============================================================================================

def load_cooperative_dilc_settings_from_yaml(file_path: str) -> CooperativeDILC_Experiment_Settings:
    """Load cooperative DILC experiment settings from a YAML file."""
    yaml_data = load_yaml(file_path)
    return from_dict_auto(CooperativeDILC_Experiment_Settings, yaml_data)
