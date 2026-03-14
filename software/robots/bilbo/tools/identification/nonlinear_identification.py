"""Nonlinear Parameter Estimation for BILBO 3D Dynamics
=====================================================

Estimates physical parameters of the BILBO nonlinear model from
trajectory data. The model structure (differential equations) is known
from bilbo_model.py; only the parameter values are unknown.

Approach: derivative matching with scipy.optimize.least_squares.
  1. Compute observed derivatives: s_dot = (s_{k+1} - s_k) / dt
  2. Compute model-predicted derivatives: s_dot_model = f(s_k, u_actual; params)
     where u_actual = u_ext - K @ s_k
  3. Minimize ||s_dot - s_dot_model||^2 over the free parameters

This avoids simulating the unstable system forward (which would diverge
with wrong parameters). Each data point is evaluated independently.

Usage:
    from nonlinear_identification import (
        identify_nonlinear, ParameterSpec, TrajectoryData
    )

    specs = get_default_parameter_specs()
    specs['m_b'].fixed = True    # measured: 1.2 kg
    specs['l'].value = 0.03      # initial guess

    result = identify_nonlinear(trajectories, specs, K=my_K, dt=0.01)
    print_result(result)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import logging

try:
    from scipy.optimize import least_squares
except ImportError:
    least_squares = None

from system_identification import (
    TrajectoryData, N_STATES, N_INPUTS,
    IX, IY, IV, ITHETA, ITHETA_DOT, IPSI, IPSI_DOT,
    STATE_NAMES, INPUT_NAMES, DYNAMIC_ROWS,
)

logger = logging.getLogger(__name__)

# ── Parameter specification ──────────────────────────────────────────────────

PARAM_NAMES = [
    'm_b', 'm_w', 'l', 'd_w', 'I_w', 'I_y', 'I_x', 'I_z',
    'c_alpha', 'r_w', 'tau_theta', 'tau_x',
]


@dataclass
class ParameterSpec:
    """Specification for a single model parameter.

    Attributes:
        value: Known value (if fixed) or initial guess (if free).
        fixed: If True, parameter is held at value during optimization.
        lower: Lower bound for optimization.
        upper: Upper bound for optimization.
    """
    value: float
    fixed: bool = False
    lower: float = -np.inf
    upper: float = np.inf


def get_default_parameter_specs() -> Dict[str, ParameterSpec]:
    """Return default parameter specs based on DEFAULT_BILBO_MODEL.

    Easily measurable params (m_b, m_w, r_w, d_w) are fixed by default.
    Inertias, CoG, friction, and damping are free with sensible bounds.
    """
    return {
        'm_b':      ParameterSpec(value=1.2,       fixed=True),
        'm_w':      ParameterSpec(value=0.4,       fixed=True),
        'l':        ParameterSpec(value=0.026,      lower=0.005,  upper=0.15),
        'd_w':      ParameterSpec(value=0.22,       fixed=True),
        'I_w':      ParameterSpec(value=2e-4,       lower=1e-6,   upper=1e-2),
        'I_y':      ParameterSpec(value=0.005,      lower=1e-4,   upper=0.1),
        'I_x':      ParameterSpec(value=0.02,       lower=1e-3,   upper=0.2),
        'I_z':      ParameterSpec(value=0.03,       lower=1e-3,   upper=0.2),
        'c_alpha':  ParameterSpec(value=4.6302e-4,  lower=0.0,    upper=0.01),
        'r_w':      ParameterSpec(value=0.06,       fixed=True),
        'tau_theta': ParameterSpec(value=0.4,       lower=0.0,    upper=10.0),
        'tau_x':    ParameterSpec(value=0.4,        lower=0.0,    upper=10.0),
    }


# ── Nonlinear dynamics ───────────────────────────────────────────────────────


def bilbo_dynamics_3d(states: np.ndarray, u_actual: np.ndarray,
                      p: Dict[str, float]) -> np.ndarray:
    """Compute state derivatives for the BILBO 3D nonlinear model (vectorized).

    Equations match BILBO_Dynamics_3D._dynamics() from bilbo_model.py exactly.

    Args:
        states: (N, 7) state vectors [x, y, v, theta, theta_dot, psi, psi_dot]
        u_actual: (N, 2) actual motor torques [u_l, u_r]
        p: Dict of model parameters (all 12 values).

    Returns:
        (N, 7) state derivatives.
    """
    g = 9.81

    v         = states[:, IV]
    theta     = states[:, ITHETA]
    theta_dot = states[:, ITHETA_DOT]
    psi       = states[:, IPSI]
    psi_dot   = states[:, IPSI_DOT]

    u_sum  = u_actual[:, 0] + u_actual[:, 1]
    u_diff = u_actual[:, 0] - u_actual[:, 1]

    cos_t = np.cos(theta)
    sin_t = np.sin(theta)

    m_b = p['m_b']
    m_w = p['m_w']
    l   = p['l']
    d_w = p['d_w']
    I_w = p['I_w']
    I_y = p['I_y']
    I_x = p['I_x']
    I_z = p['I_z']
    c_a = p['c_alpha']
    r_w = p['r_w']
    tau_t = p['tau_theta']
    tau_v = p['tau_x']

    M = m_b + 2 * m_w + 2 * I_w / r_w**2     # total effective mass
    J = I_y + m_b * l**2                        # pitch effective inertia
    ml = m_b * l
    ml2 = m_b * l**2

    # ── Denominators ──
    V_1 = M * J - ml**2 * cos_t**2
    V_2 = (I_z + 2 * I_w + (m_w + I_w / r_w**2) * d_w**2 / 2
            - (I_z - I_x - ml2) * sin_t**2)

    # ── Coriolis / centrifugal terms ──
    C_11 = ml**2 * cos_t
    C_12 = J * ml
    C_13 = J * ml + ml * (I_z - I_x - ml2) * cos_t**2
    C_21 = M * ml
    C_22 = ml**2 * cos_t
    C_23 = (ml**2 + M * (I_z - I_x - ml2)) * cos_t
    C_31 = 2 * (I_z - I_x - ml2) * cos_t
    C_32 = ml

    # ── Damping terms ──
    D_11 = J * 2 * c_a / r_w**2 - 2 * ml * cos_t * c_a / r_w
    D_12 = J * 2 * c_a / r_w - ml * cos_t * 2 * c_a
    D_21 = M * 2 * c_a / r_w + ml * cos_t * 2 * c_a / r_w**2
    D_22 = M * 2 * c_a + ml * cos_t * 2 * c_a / r_w
    D_33 = d_w**2 / (2 * r_w**2) * c_a

    # ── Input coupling ──
    B_1 = J / r_w + ml * cos_t
    B_2 = ml / r_w * cos_t + M
    B_3 = d_w / (2 * r_w)

    # ── State derivatives ──
    N = states.shape[0]
    s_dot = np.zeros((N, N_STATES))

    s_dot[:, IX] = v * np.cos(psi)
    s_dot[:, IY] = v * np.sin(psi)

    s_dot[:, IV] = (
        (sin_t / V_1) * (-C_11 * g + C_12 * theta_dot**2 + C_13 * psi_dot**2)
        - (D_11 / V_1) * v
        + (D_12 / V_1) * theta_dot
        + (B_1 / V_1) * u_sum
        - tau_v * v
    )

    s_dot[:, ITHETA] = theta_dot

    s_dot[:, ITHETA_DOT] = (
        (sin_t / V_1) * (C_21 * g - C_22 * theta_dot**2 - C_23 * psi_dot**2)
        + (D_21 / V_1) * v
        - (D_22 / V_1) * theta_dot
        - (B_2 / V_1) * u_sum
        - tau_t * theta_dot
    )

    s_dot[:, IPSI] = psi_dot

    s_dot[:, IPSI_DOT] = (
        (sin_t / V_2) * (C_31 * theta_dot * psi_dot - C_32 * psi_dot * v)
        - (D_33 / V_2) * psi_dot
        - (B_3 / V_2) * u_diff
    )

    return s_dot


# ── Identification ───────────────────────────────────────────────────────────


@dataclass
class NonlinearConfig:
    """Configuration for nonlinear parameter estimation.

    Attributes:
        theta_max: Discard data with |theta| above this [rad].
        method: scipy.optimize.least_squares method ('trf', 'dogbox', 'lm').
        max_nfev: Maximum number of function evaluations.
        weights: Optional (3,) weights for [v_dot, theta_ddot, psi_ddot] residuals.
            Default: auto-normalize by observed derivative std.
        verbose: Verbosity level (0=silent, 1=progress, 2=detailed).
    """
    theta_max: float = 0.5
    method: str = 'trf'
    max_nfev: int = 2000
    weights: Optional[np.ndarray] = None
    verbose: int = 1


@dataclass
class NonlinearResult:
    """Result of nonlinear parameter estimation.

    Attributes:
        params: Dict of all parameter values (fixed + identified).
        cost: Final cost (sum of squared residuals).
        r_squared: R² per dynamic state derivative.
        rmse: RMSE per dynamic state derivative.
        n_samples: Number of data points used.
        n_free: Number of free parameters.
        fixed_params: Names of fixed parameters.
        free_params: Names of identified parameters.
        scipy_result: Raw scipy OptimizeResult (for Jacobian, etc.)
    """
    params: Dict[str, float]
    cost: float
    r_squared: Dict[str, float]
    rmse: Dict[str, float]
    n_samples: int
    n_free: int
    fixed_params: List[str]
    free_params: List[str]
    scipy_result: object = None


def identify_nonlinear(
    trajectories: List[TrajectoryData],
    parameter_specs: Dict[str, ParameterSpec],
    K: np.ndarray,
    config: Optional[NonlinearConfig] = None,
) -> NonlinearResult:
    """Estimate BILBO model parameters from trajectory data.

    Uses derivative matching: minimizes the squared difference between
    observed and model-predicted state derivatives for the dynamic states
    (v, theta_dot, psi_dot).

    Args:
        trajectories: Measured trajectories (inputs are u_ext).
        parameter_specs: Dict mapping parameter names to ParameterSpec.
            Must include all parameters in PARAM_NAMES.
        K: (2, 7) state-feedback gain. u_actual = u_ext - K @ x.
        config: Estimation settings.

    Returns:
        NonlinearResult with identified parameters and diagnostics.
    """
    if least_squares is None:
        raise ImportError("scipy is required for nonlinear identification")

    if config is None:
        config = NonlinearConfig()

    K = np.asarray(K, dtype=np.float64)
    if K.shape != (N_INPUTS, N_STATES):
        raise ValueError(f"K must be ({N_INPUTS}, {N_STATES}), got {K.shape}")

    # Validate parameter specs
    for name in PARAM_NAMES:
        if name not in parameter_specs:
            raise ValueError(f"Missing parameter spec for '{name}'")

    dt = trajectories[0].dt

    # Collect data pairs
    sk_list, skp1_list, uk_list = [], [], []
    for traj in trajectories:
        if abs(traj.dt - dt) > 1e-10:
            raise ValueError("All trajectories must share the same dt")
        T = min(traj.states.shape[0], traj.inputs.shape[0])
        sk_list.append(traj.states[:T - 1])
        skp1_list.append(traj.states[1:T])
        uk_list.append(traj.inputs[:T - 1])

    s_k = np.vstack(sk_list)
    s_kp1 = np.vstack(skp1_list)
    u_ext = np.vstack(uk_list)

    # Filter by theta
    mask = np.abs(s_k[:, ITHETA]) <= config.theta_max
    n_discarded = np.sum(~mask)
    if n_discarded > 0:
        logger.info(f"Discarded {n_discarded}/{len(mask)} samples (|theta| > {config.theta_max:.2f})")
    s_k = s_k[mask]
    s_kp1 = s_kp1[mask]
    u_ext = u_ext[mask]

    n_samples = s_k.shape[0]
    logger.info(f"Nonlinear identification: {n_samples} data points")

    # Compute u_actual and observed derivatives
    u_actual = u_ext - (K @ s_k.T).T  # (N, 2)
    s_dot_obs = (s_kp1 - s_k) / dt    # (N, 7)

    # Dynamic state derivative indices (what we fit)
    deriv_indices = [IV, ITHETA_DOT, IPSI_DOT]
    deriv_names = [STATE_NAMES[i] for i in deriv_indices]

    # Compute weights (auto-normalize by std of each derivative)
    if config.weights is not None:
        weights = np.asarray(config.weights, dtype=np.float64)
    else:
        stds = np.array([
            max(np.std(s_dot_obs[:, i]), 1e-8) for i in deriv_indices
        ])
        weights = 1.0 / stds
    logger.info(f"Residual weights: {dict(zip(deriv_names, weights))}")

    # Separate fixed and free parameters
    fixed_params = {}
    free_names = []
    free_x0 = []
    free_lower = []
    free_upper = []

    for name in PARAM_NAMES:
        spec = parameter_specs[name]
        if spec.fixed:
            fixed_params[name] = spec.value
        else:
            free_names.append(name)
            free_x0.append(spec.value)
            free_lower.append(spec.lower)
            free_upper.append(spec.upper)

    n_free = len(free_names)
    logger.info(f"Fixed: {list(fixed_params.keys())}")
    logger.info(f"Free ({n_free}): {free_names}")

    if n_free == 0:
        raise ValueError("All parameters are fixed — nothing to identify")

    free_x0 = np.array(free_x0)
    bounds = (np.array(free_lower), np.array(free_upper))

    def build_params(free_vec):
        """Combine fixed and free parameters into a full dict."""
        p = dict(fixed_params)
        for name, val in zip(free_names, free_vec):
            p[name] = val
        return p

    def residual_fn(free_vec):
        """Compute weighted residuals for all data points."""
        p = build_params(free_vec)
        s_dot_model = bilbo_dynamics_3d(s_k, u_actual, p)

        # Residuals for the 3 dynamic derivatives, weighted
        res = np.empty(n_samples * 3)
        for idx_out, idx_state in enumerate(deriv_indices):
            start = idx_out * n_samples
            res[start:start + n_samples] = (
                (s_dot_obs[:, idx_state] - s_dot_model[:, idx_state]) * weights[idx_out]
            )
        return res

    # Run optimization
    logger.info("Running least_squares optimization...")
    result = least_squares(
        residual_fn, free_x0,
        bounds=bounds,
        method=config.method,
        max_nfev=config.max_nfev,
        verbose=config.verbose,
    )

    # Extract results
    final_params = build_params(result.x)
    final_s_dot = bilbo_dynamics_3d(s_k, u_actual, final_params)

    r_squared = {}
    rmse_dict = {}
    for idx_out, idx_state in enumerate(deriv_indices):
        name = STATE_NAMES[idx_state]
        obs = s_dot_obs[:, idx_state]
        pred = final_s_dot[:, idx_state]
        ss_res = np.sum((obs - pred) ** 2)
        ss_tot = np.sum((obs - np.mean(obs)) ** 2)
        r_squared[name] = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
        rmse_dict[name] = float(np.sqrt(ss_res / n_samples))

    return NonlinearResult(
        params=final_params,
        cost=float(result.cost),
        r_squared=r_squared,
        rmse=rmse_dict,
        n_samples=n_samples,
        n_free=n_free,
        fixed_params=list(fixed_params.keys()),
        free_params=free_names,
        scipy_result=result,
    )


# ── Simulation ───────────────────────────────────────────────────────────────


def simulate_nonlinear(
    params: Dict[str, float],
    x0: np.ndarray,
    inputs_ext: np.ndarray,
    K: np.ndarray,
    dt: float,
) -> np.ndarray:
    """Forward-simulate the nonlinear model with Euler integration.

    Args:
        params: Model parameters.
        x0: Initial state (7,).
        inputs_ext: External input sequence (T, 2).
        K: Feedback gain (2, 7).
        dt: Time step.

    Returns:
        (T+1, 7) state trajectory including x0.
    """
    T = inputs_ext.shape[0]
    states = np.zeros((T + 1, N_STATES))
    states[0] = x0

    for k in range(T):
        s = states[k:k + 1]  # (1, 7) for vectorized dynamics
        u_actual = inputs_ext[k:k + 1] - (K @ s.T).T  # (1, 2)
        s_dot = bilbo_dynamics_3d(s, u_actual, params)
        states[k + 1] = states[k] + s_dot[0] * dt

    return states


# ── Printing ─────────────────────────────────────────────────────────────────


def print_result(result: NonlinearResult, true_params: Optional[Dict[str, float]] = None):
    """Pretty-print identification result."""
    print("\n" + "=" * 72)
    print("NONLINEAR PARAMETER ESTIMATION RESULT")
    print(f"  {result.n_samples} data points, {result.n_free} free parameters")
    print(f"  Final cost: {result.cost:.6e}")
    print("=" * 72)

    header = f"  {'Parameter':>12s}  {'Value':>12s}"
    if true_params:
        header += f"  {'True':>12s}  {'Error':>12s}  {'Rel.Err':>10s}"
    header += f"  {'Status':>8s}"
    print(header)

    for name in PARAM_NAMES:
        val = result.params[name]
        line = f"  {name:>12s}  {val:12.6g}"
        if true_params and name in true_params:
            true_val = true_params[name]
            err = val - true_val
            rel = abs(err / true_val) if abs(true_val) > 1e-12 else float('inf')
            line += f"  {true_val:12.6g}  {err:+12.2e}  {rel:10.2%}"
        status = "FIXED" if name in result.fixed_params else "free"
        line += f"  {status:>8s}"
        print(line)

    print(f"\nDerivative fit quality:")
    print(f"  {'Derivative':>12s}  {'R²':>10s}  {'RMSE':>12s}")
    for name in [STATE_NAMES[i] for i in DYNAMIC_ROWS]:
        if name in result.r_squared:
            print(f"  {name:>12s}  {result.r_squared[name]:10.6f}  {result.rmse[name]:12.2e}")


# ── Synthetic test ───────────────────────────────────────────────────────────


# ── BilboModel ↔ dict conversion ─────────────────────────────────────────────


def model_to_params(model) -> Dict[str, float]:
    """Convert a BilboModel dataclass to a parameter dict."""
    return {name: getattr(model, name) for name in PARAM_NAMES}


def params_to_model(params: Dict[str, float]):
    """Convert a parameter dict to a BilboModel dataclass.

    Requires BilboModel to be importable from bilbo_model.py.
    """
    try:
        from robots.bilbo.simulation.model import BilboModel
    except ImportError:
        raise ImportError("BilboModel not available — ensure software/ is in sys.path")
    import numpy as _np
    return BilboModel(**params, max_pitch=_np.deg2rad(105))


# Ground truth parameters (DEFAULT_BILBO_MODEL from bilbo_model.py)
try:
    from robots.bilbo.simulation.model import DEFAULT_BILBO_MODEL as _DEFAULT
    TRUE_PARAMS = model_to_params(_DEFAULT)
except ImportError:
    TRUE_PARAMS = {
        'm_b': 1.2, 'm_w': 0.4, 'l': 0.026, 'd_w': 0.22,
        'I_w': 2e-4, 'I_y': 0.005, 'I_x': 0.02, 'I_z': 0.03,
        'c_alpha': 4.6302e-4, 'r_w': 0.06,
        'tau_theta': 0.4, 'tau_x': 0.4,
    }


def generate_synthetic_data(
    params: Dict[str, float],
    K: np.ndarray,
    dt: float = 0.01,
    n_trajectories: int = 15,
    T: int = 500,
    noise_std: float = 0.001,
    input_std: float = 0.05,
    seed: int = 42,
    max_theta: float = 1.0,
) -> List[TrajectoryData]:
    """Generate trajectories from the nonlinear model with feedback control.

    Trajectories are truncated if |theta| exceeds max_theta to prevent
    numerical divergence.
    """
    rng = np.random.default_rng(seed)
    trajectories = []

    for _ in range(n_trajectories):
        states_list = []
        inputs_list = []

        s = np.zeros(N_STATES)
        s[ITHETA] = rng.uniform(-0.1, 0.1)
        s[IV] = rng.uniform(-0.1, 0.1)
        s[IPSI] = rng.uniform(-0.3, 0.3)
        s[IPSI_DOT] = rng.uniform(-0.2, 0.2)

        for k in range(T):
            states_list.append(s.copy())
            u_ext = rng.normal(0, input_std, N_INPUTS)
            inputs_list.append(u_ext)

            if k < T - 1:
                u_actual = u_ext - K @ s
                s_arr = s.reshape(1, -1)
                ua_arr = u_actual.reshape(1, -1)
                s_dot = bilbo_dynamics_3d(s_arr, ua_arr, params)[0]

                s = s + s_dot * dt

                # Truncate trajectory if theta diverges
                if abs(s[ITHETA]) > max_theta or not np.all(np.isfinite(s)):
                    break

        if len(states_list) < 10:
            continue

        states = np.array(states_list)
        inputs = np.array(inputs_list)

        noisy = states + rng.normal(0, noise_std, states.shape)
        trajectories.append(TrajectoryData(states=noisy, inputs=inputs, dt=dt))

    return trajectories


def get_test_feedback_gain() -> np.ndarray:
    """Stabilizing K for the default BILBO nonlinear model (Euler, dt=0.01).

    The BILBO has very high input-to-theta_ddot gain (~233), so K_theta
    must be small for discrete stability. Valid K_theta per wheel: ~(0.12, 0.43).
    """
    K = np.zeros((N_INPUTS, N_STATES))
    K[0, ITHETA] = -0.35
    K[0, ITHETA_DOT] = -0.08
    K[0, IV] = -0.015
    K[1, ITHETA] = -0.35
    K[1, ITHETA_DOT] = -0.08
    K[1, IV] = -0.015
    K[0, IPSI_DOT] = 0.01
    K[1, IPSI_DOT] = -0.01
    return K


def run_test():
    """Test nonlinear identification on synthetic data.

    Note on identifiability:
      tau_theta and c_alpha (via D_22/V_1) both contribute to theta_dot
      damping. Near theta=0 they are partially confounded — the optimizer
      may trade one for the other while maintaining good prediction.
      Having data at moderate theta values helps separate them.
    """
    dt = 0.01
    K = get_test_feedback_gain()

    print("Generating synthetic data from true nonlinear model...")
    train = generate_synthetic_data(TRUE_PARAMS, K, dt=dt,
                                    n_trajectories=30, T=800,
                                    noise_std=0.001, input_std=0.08, seed=42)
    test = generate_synthetic_data(TRUE_PARAMS, K, dt=dt,
                                   n_trajectories=5, T=800,
                                   noise_std=0.001, input_std=0.08, seed=123)
    print(f"  Train: {len(train)} trajs, {sum(t.T for t in train)} samples")
    print(f"  Test:  {len(test)} trajs, {sum(t.T for t in test)} samples")

    # Set up parameter specs: fix measurable, identify the rest
    specs = get_default_parameter_specs()

    # Perturb initial guesses away from truth to test convergence
    specs['l'].value = 0.04          # true: 0.026
    specs['I_y'].value = 0.01        # true: 0.005
    specs['I_x'].value = 0.015       # true: 0.02
    specs['I_z'].value = 0.025       # true: 0.03
    specs['I_w'].value = 3e-4        # true: 2e-4
    specs['c_alpha'].value = 5e-4    # true: 4.63e-4
    specs['tau_theta'].value = 0.2   # true: 0.4
    specs['tau_x'].value = 0.6       # true: 0.4

    print("\nInitial guesses (perturbed from truth):")
    for name in PARAM_NAMES:
        if not specs[name].fixed:
            print(f"  {name:>12s}: {specs[name].value:.6g}  (true: {TRUE_PARAMS[name]:.6g})")

    # Use theta_max=0.5 to include more data with moderate angles
    cfg = NonlinearConfig(theta_max=0.5, verbose=1)
    result = identify_nonlinear(train, specs, K, cfg)

    print_result(result, true_params=TRUE_PARAMS)

    # Validate: simulate a test trajectory
    print("\n" + "=" * 72)
    print("VALIDATION: multi-step rollout on test trajectory")
    print("=" * 72)
    test_traj = test[0]
    n_steps = min(300, test_traj.T - 1)
    x0 = test_traj.states[0]
    u_seg = test_traj.inputs[:n_steps]

    pred = simulate_nonlinear(result.params, x0, u_seg, K, dt)
    actual = test_traj.states[:n_steps + 1]

    # Only compute RMSE over valid (finite) portion
    valid_len = n_steps + 1
    for k in range(n_steps + 1):
        if not np.all(np.isfinite(pred[k])):
            valid_len = k
            break

    if valid_len > 10:
        print(f"\n  {valid_len}-step rollout RMSE:")
        for i, name in enumerate(STATE_NAMES):
            rmse = np.sqrt(np.mean((actual[:valid_len, i] - pred[:valid_len, i]) ** 2))
            print(f"    {name:>12s}: {rmse:.2e}")
    else:
        print("\n  Rollout diverged early — model may need better parameters or stronger K")

    # Optional plot
    try:
        import matplotlib.pyplot as plt

        t = np.arange(valid_len) * dt
        fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
        fig.suptitle('Nonlinear Model: Predicted vs Actual', fontsize=13)

        for ax, (idx, label) in zip(axes, [
            (IV, 'v [m/s]'), (ITHETA, 'theta [rad]'), (IPSI_DOT, 'psi_dot [rad/s]'),
        ]):
            ax.plot(t, actual[:valid_len, idx], 'k-', linewidth=1.2, label='Actual')
            ax.plot(t, pred[:valid_len, idx], 'r--', linewidth=0.9, alpha=0.8, label='Identified model')
            ax.set_ylabel(label)
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3)
        axes[-1].set_xlabel('Time [s]')

        plt.tight_layout()
        plt.show()
    except Exception as e:
        print(f"\n(Plotting skipped: {e})")

    return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    run_test()
