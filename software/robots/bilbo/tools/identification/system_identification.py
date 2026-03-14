"""System Identification for BILBO Two-Wheeled Inverted Pendulum Robot
===================================================================

Identifies a discrete-time linear state-space model from trajectory data:

    x_{k+1} = A_d @ x_k + B_d @ u_k

With state-feedback control u_actual = u_ext - K @ x, the data contains
u_ext and the closed-loop dynamics are:

    x_{k+1} = (A_d - B_d @ K) @ x_k + B_d @ u_ext
            = A_d_cl @ x_k + B_d @ u_ext

The identification recovers A_d_cl and B_d from data, then computes the
open-loop A_d = A_d_cl + B_d @ K.

State vector (7): [x, y, v, theta, theta_dot, psi, psi_dot]
Input vector (2): [u_left, u_right]

Usage:
    from system_identification import identify_system, TrajectoryData

    traj = TrajectoryData(states=states_array, inputs=inputs_array, dt=0.01)
    result = identify_system([traj], K=my_feedback_gain)
    print_model(result)
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# ── State and input indices ──────────────────────────────────────────────────

IX = 0           # x position [m]
IY = 1           # y position [m]
IV = 2           # forward velocity [m/s]
ITHETA = 3       # pitch angle [rad]
ITHETA_DOT = 4   # pitch rate [rad/s]
IPSI = 5         # yaw angle [rad]
IPSI_DOT = 6     # yaw rate [rad/s]

N_STATES = 7
N_INPUTS = 2

STATE_NAMES = ['x', 'y', 'v', 'theta', 'theta_dot', 'psi', 'psi_dot']
INPUT_NAMES = ['u_left', 'u_right']

KINEMATIC_ROWS = [IX, IY, ITHETA, IPSI]
DYNAMIC_ROWS = [IV, ITHETA_DOT, IPSI_DOT]

# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class TrajectoryData:
    """A single measured trajectory.

    Attributes:
        states: (T, 7) state measurements [x, y, v, theta, theta_dot, psi, psi_dot]
        inputs: (T, 2) input commands [u_left, u_right].
                When K is provided to identify_system, these are u_ext (external).
                Otherwise these are u_actual (total torque applied).
        dt: sampling period [s]
    """
    states: np.ndarray
    inputs: np.ndarray
    dt: float

    def __post_init__(self):
        self.states = np.asarray(self.states, dtype=np.float64)
        self.inputs = np.asarray(self.inputs, dtype=np.float64)
        if self.states.ndim != 2 or self.states.shape[1] != N_STATES:
            raise ValueError(f"states must be (T, {N_STATES}), got {self.states.shape}")
        if self.inputs.ndim != 2 or self.inputs.shape[1] != N_INPUTS:
            raise ValueError(f"inputs must be (T, {N_INPUTS}), got {self.inputs.shape}")
        T_s, T_u = self.states.shape[0], self.inputs.shape[0]
        if abs(T_s - T_u) > 1:
            raise ValueError(f"states ({T_s}) and inputs ({T_u}) length mismatch")

    @property
    def T(self) -> int:
        return self.states.shape[0]


@dataclass
class IdentificationConfig:
    """Configuration for system identification.

    Attributes:
        alpha: Ridge regularization strength (larger = more regularization)
        theta_max: Discard data with |theta| above this [rad] (~17 deg default)
        use_physics_mask: Enforce known sparsity on A_d. Only used when K is
            None, since A_cl = A - B@K has no known sparsity.
        include_bias: Fit an affine offset term (nonzero equilibrium)
    """
    alpha: float = 1e-3
    theta_max: float = 0.3
    use_physics_mask: bool = True
    include_bias: bool = False


@dataclass
class IdentificationResult:
    """System identification result.

    A_d is the open-loop plant matrix. When K is provided, A_d is recovered
    from the closed-loop: A_d = A_d_cl + B_d @ K.
    """
    A_d: np.ndarray              # (7,7) open-loop discrete state matrix
    B_d: np.ndarray              # (7,2) discrete input matrix
    bias: np.ndarray             # (7,) affine bias term
    K: Optional[np.ndarray]      # (2,7) feedback gain, or None
    dt: float
    r_squared: Dict[str, float]  # R² for each identified state
    rmse: Dict[str, float]       # one-step RMSE for each identified state
    n_samples: int
    config: IdentificationConfig

    @property
    def A_d_cl(self) -> np.ndarray:
        """Closed-loop A_d for simulation: A_d - B_d @ K.
        Same as A_d when K is None."""
        if self.K is not None:
            return self.A_d - self.B_d @ self.K
        return self.A_d

    @property
    def A_c(self) -> np.ndarray:
        """Continuous-time A (Euler: A_d = I + dt * A_c)."""
        return (self.A_d - np.eye(N_STATES)) / self.dt

    @property
    def B_c(self) -> np.ndarray:
        """Continuous-time B (Euler: B_d = dt * B_c)."""
        return self.B_d / self.dt


# ── Core identification ──────────────────────────────────────────────────────


def identify_system(
    trajectories: List[TrajectoryData],
    config: Optional[IdentificationConfig] = None,
    K: Optional[np.ndarray] = None,
) -> IdentificationResult:
    """Identify linear discrete-time model from trajectory data.

    Args:
        trajectories: One or more measured trajectories.
        config: Identification settings. Uses defaults if None.
        K: (2, 7) state-feedback gain. If provided, the inputs in the
           trajectories are interpreted as u_ext, and the open-loop A_d
           is recovered via A_d = A_d_cl + B_d @ K.

    Returns:
        IdentificationResult with open-loop A_d, B_d and quality metrics.
    """
    if config is None:
        config = IdentificationConfig()

    if K is not None:
        K = np.asarray(K, dtype=np.float64)
        if K.shape != (N_INPUTS, N_STATES):
            raise ValueError(f"K must be ({N_INPUTS}, {N_STATES}), got {K.shape}")

    dt = trajectories[0].dt
    for traj in trajectories:
        if abs(traj.dt - dt) > 1e-10:
            raise ValueError("All trajectories must share the same dt")

    # Collect consecutive (s_k, u_k, s_{k+1}) pairs
    sk_list, skp1_list, uk_list = [], [], []
    for traj in trajectories:
        T = min(traj.states.shape[0], traj.inputs.shape[0])
        sk_list.append(traj.states[:T - 1])
        skp1_list.append(traj.states[1:T])
        uk_list.append(traj.inputs[:T - 1])

    s_k = np.vstack(sk_list)
    s_kp1 = np.vstack(skp1_list)
    u_k = np.vstack(uk_list)

    # Filter by linearization region
    theta_mask = np.abs(s_k[:, ITHETA]) <= config.theta_max
    n_discarded = np.sum(~theta_mask)
    if n_discarded > 0:
        logger.info(
            f"Discarded {n_discarded}/{len(theta_mask)} samples "
            f"with |theta| > {config.theta_max:.2f} rad"
        )
    s_k = s_k[theta_mask]
    s_kp1 = s_kp1[theta_mask]
    u_k = u_k[theta_mask]

    n_samples = s_k.shape[0]
    min_required = N_STATES + N_INPUTS + 5
    if n_samples < min_required:
        raise ValueError(
            f"Only {n_samples} samples after filtering (need >= {min_required})"
        )
    logger.info(f"Identifying from {n_samples} data points (dt={dt})")

    # Initialize with kinematic structure
    A_d = np.eye(N_STATES)
    B_d = np.zeros((N_STATES, N_INPUTS))
    bias = np.zeros(N_STATES)

    A_d[IX, IV] = dt
    A_d[ITHETA, ITHETA_DOT] = dt
    A_d[IPSI, IPSI_DOT] = dt

    # Physics masks for open-loop A (only used when K is None)
    physics_masks = {
        IV: [IV, ITHETA, ITHETA_DOT],
        ITHETA_DOT: [IV, ITHETA, ITHETA_DOT],
        IPSI_DOT: [IV, IPSI_DOT],
    }

    r_squared = {}
    rmse_dict = {}

    for row_idx in DYNAMIC_ROWS:
        y = s_kp1[:, row_idx]

        # When K is provided, A_cl has no known sparsity (K couples everything),
        # so we must use all state features. Physics mask only applies to
        # the open-loop A, which we recover after identification.
        if K is not None:
            state_cols = list(range(N_STATES))
        elif config.use_physics_mask:
            state_cols = physics_masks[row_idx]
        else:
            state_cols = list(range(N_STATES))

        # Feature matrix: [selected_states, inputs, (bias)]
        parts = [s_k[:, state_cols], u_k]
        if config.include_bias:
            parts.append(np.ones((n_samples, 1)))
        X = np.hstack(parts)

        # Ridge regression
        n_feat = X.shape[1]
        w = np.linalg.solve(
            X.T @ X + config.alpha * np.eye(n_feat),
            X.T @ y,
        )

        # Extract A_cl row and B row from regression weights
        n_sc = len(state_cols)
        A_cl_row = np.zeros(N_STATES)
        for j, col in enumerate(state_cols):
            A_cl_row[col] = w[j]
        B_d[row_idx, :] = w[n_sc:n_sc + N_INPUTS]
        if config.include_bias:
            bias[row_idx] = w[-1]

        # Recover open-loop A: A = A_cl + B @ K
        if K is not None:
            A_d[row_idx, :] = A_cl_row + B_d[row_idx, :] @ K
        else:
            A_d[row_idx, :] = A_cl_row

        # Quality metrics (on the closed-loop regression, which is what we fit)
        y_pred = X @ w
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
        rmse_val = np.sqrt(ss_res / len(y))

        name = STATE_NAMES[row_idx]
        r_squared[name] = r2
        rmse_dict[name] = rmse_val
        logger.info(f"  {name:>10s}: R²={r2:.6f}, RMSE={rmse_val:.2e}")

    return IdentificationResult(
        A_d=A_d, B_d=B_d, bias=bias, K=K, dt=dt,
        r_squared=r_squared, rmse=rmse_dict,
        n_samples=n_samples, config=config,
    )


# ── Simulation ───────────────────────────────────────────────────────────────


def simulate_linear(
    result: IdentificationResult,
    x0: np.ndarray,
    inputs: np.ndarray,
) -> np.ndarray:
    """Simulate purely linear model.

    If K is set, inputs are u_ext and the closed-loop matrix is used:
        x_{k+1} = A_d_cl @ x_k + B_d @ u_ext
    Otherwise inputs are u_actual:
        x_{k+1} = A_d @ x_k + B_d @ u_actual

    Returns (T+1, 7) trajectory including x0.
    """
    A = result.A_d_cl  # equals A_d when K is None
    T = inputs.shape[0]
    states = np.zeros((T + 1, N_STATES))
    states[0] = x0
    for k in range(T):
        states[k + 1] = A @ states[k] + result.B_d @ inputs[k] + result.bias
    return states


def simulate_hybrid(
    result: IdentificationResult,
    x0: np.ndarray,
    inputs: np.ndarray,
) -> np.ndarray:
    """Simulate with nonlinear kinematics + linear identified dynamics.

    Uses exact Euler kinematics for x, y, theta, psi and the
    identified linear model for v, theta_dot, psi_dot.
    Uses A_d_cl when K is set (inputs = u_ext).

    Returns (T+1, 7) trajectory including x0.
    """
    A_cl = result.A_d_cl
    dt = result.dt
    T = inputs.shape[0]
    states = np.zeros((T + 1, N_STATES))
    states[0] = x0

    for k in range(T):
        s = states[k]
        u = inputs[k]

        # Nonlinear kinematics
        states[k + 1, IX] = s[IX] + dt * s[IV] * np.cos(s[IPSI])
        states[k + 1, IY] = s[IY] + dt * s[IV] * np.sin(s[IPSI])
        states[k + 1, ITHETA] = s[ITHETA] + dt * s[ITHETA_DOT]
        states[k + 1, IPSI] = s[IPSI] + dt * s[IPSI_DOT]

        # Identified linear dynamics (closed-loop)
        for row in DYNAMIC_ROWS:
            states[k + 1, row] = (
                A_cl[row] @ s + result.B_d[row] @ u + result.bias[row]
            )

    return states


# ── Validation ───────────────────────────────────────────────────────────────


def validate_model(
    result: IdentificationResult,
    test_trajectories: List[TrajectoryData],
    n_steps_list: Optional[List[int]] = None,
) -> Dict:
    """Validate model on held-out test trajectories.

    Returns dict with one-step and multi-step RMSE for both
    the purely linear and the hybrid (nonlinear kinematics) model.
    """
    if n_steps_list is None:
        n_steps_list = [1, 10, 50, 100]

    A_cl = result.A_d_cl
    metrics: Dict = {'one_step': {}, 'multi_step_linear': {}, 'multi_step_hybrid': {}}
    dt = result.dt

    # ── One-step prediction ──
    all_actual, all_pred_lin, all_pred_hyb = [], [], []

    for traj in test_trajectories:
        T = min(traj.states.shape[0], traj.inputs.shape[0])
        s, u = traj.states[:T], traj.inputs[:T]
        valid = np.abs(s[:-1, ITHETA]) <= result.config.theta_max

        for k in np.where(valid)[0]:
            actual = s[k + 1]
            pred_lin = A_cl @ s[k] + result.B_d @ u[k] + result.bias

            pred_hyb = np.zeros(N_STATES)
            pred_hyb[IX] = s[k, IX] + dt * s[k, IV] * np.cos(s[k, IPSI])
            pred_hyb[IY] = s[k, IY] + dt * s[k, IV] * np.sin(s[k, IPSI])
            pred_hyb[ITHETA] = s[k, ITHETA] + dt * s[k, ITHETA_DOT]
            pred_hyb[IPSI] = s[k, IPSI] + dt * s[k, IPSI_DOT]
            for row in DYNAMIC_ROWS:
                pred_hyb[row] = (
                    A_cl[row] @ s[k] + result.B_d[row] @ u[k] + result.bias[row]
                )

            all_actual.append(actual)
            all_pred_lin.append(pred_lin)
            all_pred_hyb.append(pred_hyb)

    actual_arr = np.array(all_actual)
    pred_lin_arr = np.array(all_pred_lin)
    pred_hyb_arr = np.array(all_pred_hyb)

    for i, name in enumerate(STATE_NAMES):
        metrics['one_step'][name] = {
            'rmse_linear': float(np.sqrt(np.mean((actual_arr[:, i] - pred_lin_arr[:, i]) ** 2))),
            'rmse_hybrid': float(np.sqrt(np.mean((actual_arr[:, i] - pred_hyb_arr[:, i]) ** 2))),
        }

    # ── Multi-step rollout ──
    for n_steps in n_steps_list:
        errs_lin = {n: [] for n in STATE_NAMES}
        errs_hyb = {n: [] for n in STATE_NAMES}

        for traj in test_trajectories:
            T = min(traj.states.shape[0], traj.inputs.shape[0])
            if T < n_steps + 1:
                continue
            stride = max(1, n_steps // 2)
            for start in range(0, T - n_steps, stride):
                seg_s = traj.states[start:start + n_steps + 1]
                if np.any(np.abs(seg_s[:, ITHETA]) > result.config.theta_max * 1.5):
                    continue

                x0 = traj.states[start]
                u_seg = traj.inputs[start:start + n_steps]

                pred_lin = simulate_linear(result, x0, u_seg)
                pred_hyb = simulate_hybrid(result, x0, u_seg)

                for i, name in enumerate(STATE_NAMES):
                    errs_lin[name].append((seg_s[-1, i] - pred_lin[-1, i]) ** 2)
                    errs_hyb[name].append((seg_s[-1, i] - pred_hyb[-1, i]) ** 2)

        key = f'{n_steps}_steps'
        metrics['multi_step_linear'][key] = {}
        metrics['multi_step_hybrid'][key] = {}
        for name in STATE_NAMES:
            if errs_lin[name]:
                metrics['multi_step_linear'][key][name] = float(np.sqrt(np.mean(errs_lin[name])))
                metrics['multi_step_hybrid'][key][name] = float(np.sqrt(np.mean(errs_hyb[name])))

    return metrics


# ── Synthetic test data ──────────────────────────────────────────────────────


def get_test_system(dt: float = 0.01) -> Tuple[np.ndarray, np.ndarray]:
    """Return a plausible BILBO discrete-time model for testing.

    Continuous-time dynamics (linearized at theta=0):
      v_dot       = -2v + 4*theta                  + 8*(u_l + u_r)
      theta_ddot  = -0.5v + 45*theta - 1.5*theta_dot - 15*(u_l + u_r)
      psi_ddot    = -3*psi_dot                      + 12*(-u_l + u_r)

    Returns (A_d, B_d) via Euler discretization.
    """
    A_c = np.zeros((N_STATES, N_STATES))
    B_c = np.zeros((N_STATES, N_INPUTS))

    A_c[IX, IV] = 1.0
    A_c[ITHETA, ITHETA_DOT] = 1.0
    A_c[IPSI, IPSI_DOT] = 1.0

    A_c[IV, IV] = -2.0
    A_c[IV, ITHETA] = 4.0
    B_c[IV, :] = [8.0, 8.0]

    A_c[ITHETA_DOT, IV] = -0.5
    A_c[ITHETA_DOT, ITHETA] = 45.0
    A_c[ITHETA_DOT, ITHETA_DOT] = -1.5
    B_c[ITHETA_DOT, :] = [-15.0, -15.0]

    A_c[IPSI_DOT, IPSI_DOT] = -3.0
    B_c[IPSI_DOT, :] = [-12.0, 12.0]

    A_d = np.eye(N_STATES) + dt * A_c
    B_d = dt * B_c
    return A_d, B_d


def get_test_feedback_gain() -> np.ndarray:
    """Return a stabilizing feedback gain K (2, 7) for testing.

    u_actual = u_ext - K @ x
    Both wheels respond to theta, theta_dot, v for balancing.
    Differential response to psi_dot for yaw damping.
    """
    K = np.zeros((N_INPUTS, N_STATES))
    K[0, ITHETA] = -3.0
    K[0, ITHETA_DOT] = -0.5
    K[0, IV] = -0.1
    K[1, ITHETA] = -3.0
    K[1, ITHETA_DOT] = -0.5
    K[1, IV] = -0.1
    K[0, IPSI_DOT] = 0.1
    K[1, IPSI_DOT] = -0.1
    return K


def generate_synthetic_trajectories(
    A_d: np.ndarray,
    B_d: np.ndarray,
    dt: float = 0.01,
    K: Optional[np.ndarray] = None,
    n_trajectories: int = 10,
    T: int = 500,
    noise_std: float = 0.001,
    input_std: float = 0.05,
    seed: int = 42,
) -> List[TrajectoryData]:
    """Generate synthetic trajectories from a known linear model.

    Args:
        A_d, B_d: True system matrices (open-loop).
        dt: Sampling period.
        K: If provided, the controller u_actual = u_ext - K @ x is used,
           and u_ext is stored in the trajectory. If None, an internal
           stabilizing controller is used and u_actual is stored.
        n_trajectories, T: Number and length of trajectories.
        noise_std: Measurement noise std.
        input_std: Exploration noise std (= u_ext when K is given).
        seed: Random seed.
    """
    rng = np.random.default_rng(seed)

    # When K is not provided, use an internal controller for stabilization
    K_internal = get_test_feedback_gain() if K is None else None

    trajectories = []
    for _ in range(n_trajectories):
        states = np.zeros((T, N_STATES))
        inputs = np.zeros((T, N_INPUTS))

        states[0, ITHETA] = rng.uniform(-0.05, 0.05)
        states[0, IV] = rng.uniform(-0.1, 0.1)
        states[0, IPSI] = rng.uniform(-0.3, 0.3)
        states[0, IPSI_DOT] = rng.uniform(-0.2, 0.2)

        for k in range(T - 1):
            u_ext = rng.normal(0, input_std, N_INPUTS)

            if K is not None:
                # Known feedback: u_actual = u_ext - K @ x
                u_actual = u_ext - K @ states[k]
                inputs[k] = u_ext  # store external command
            else:
                # Internal controller: u_actual = -K_int @ x + noise
                u_actual = -K_internal @ states[k] + u_ext
                inputs[k] = u_actual  # store total torque

            s = states[k]
            states[k + 1, IX] = s[IX] + dt * s[IV] * np.cos(s[IPSI])
            states[k + 1, IY] = s[IY] + dt * s[IV] * np.sin(s[IPSI])
            states[k + 1, ITHETA] = s[ITHETA] + dt * s[ITHETA_DOT]
            states[k + 1, IPSI] = s[IPSI] + dt * s[IPSI_DOT]
            for row in DYNAMIC_ROWS:
                states[k + 1, row] = A_d[row] @ s + B_d[row] @ u_actual

        # Last input
        u_ext_last = rng.normal(0, input_std, N_INPUTS)
        if K is not None:
            inputs[-1] = u_ext_last
        else:
            inputs[-1] = -K_internal @ states[-1] + u_ext_last

        noisy_states = states + rng.normal(0, noise_std, states.shape)
        trajectories.append(TrajectoryData(states=noisy_states, inputs=inputs, dt=dt))

    return trajectories


# ── Printing utilities ───────────────────────────────────────────────────────


def print_model(result: IdentificationResult):
    """Pretty-print the identified model matrices and quality metrics."""
    print("\n" + "=" * 72)
    title = "IDENTIFIED DISCRETE-TIME MODEL"
    if result.K is not None:
        title += " (open-loop, recovered via A = A_cl + B@K)"
    print(title)
    print(f"  dt = {result.dt} s  |  {result.n_samples} data points")
    print("=" * 72)

    print("\nA_d (7x7) — [K]=kinematic, [D]=identified from data:")
    print("           " + "".join(f"{n:>11s}" for n in STATE_NAMES))
    for i, name in enumerate(STATE_NAMES):
        tag = "[K]" if i in KINEMATIC_ROWS else "[D]"
        vals = "".join(f"{result.A_d[i, j]:11.6f}" for j in range(N_STATES))
        print(f"  {name:>9s} {tag} {vals}")

    print("\nB_d (7x2):")
    print("           " + "".join(f"{n:>11s}" for n in INPUT_NAMES))
    for i, name in enumerate(STATE_NAMES):
        tag = "[K]" if i in KINEMATIC_ROWS else "[D]"
        vals = "".join(f"{result.B_d[i, j]:11.6f}" for j in range(N_INPUTS))
        print(f"  {name:>9s} {tag} {vals}")

    if np.any(np.abs(result.bias) > 1e-10):
        print(f"\nBias: {result.bias}")

    if result.K is not None:
        print("\nFeedback gain K (2x7):")
        print("           " + "".join(f"{n:>11s}" for n in STATE_NAMES))
        for i, name in enumerate(INPUT_NAMES):
            vals = "".join(f"{result.K[i, j]:11.6f}" for j in range(N_STATES))
            print(f"  {name:>9s}     {vals}")

    print("\nOne-step identification quality:")
    print(f"  {'State':>12s}  {'R²':>10s}  {'RMSE':>12s}")
    for row in DYNAMIC_ROWS:
        n = STATE_NAMES[row]
        print(f"  {n:>12s}  {result.r_squared[n]:10.6f}  {result.rmse[n]:12.2e}")

    print("\nContinuous-time interpretation (d/dt = A_c @ s + B_c @ u):")
    for row in DYNAMIC_ROWS:
        name = STATE_NAMES[row]
        ac, bc = result.A_c[row], result.B_c[row]
        terms = []
        for j in range(N_STATES):
            if abs(ac[j]) > 1e-4:
                terms.append(f"{ac[j]:+.3f}*{STATE_NAMES[j]}")
        for j in range(N_INPUTS):
            if abs(bc[j]) > 1e-4:
                terms.append(f"{bc[j]:+.3f}*{INPUT_NAMES[j]}")
        print(f"  d({name})/dt = {' '.join(terms) if terms else '0'}")


def print_validation(metrics: Dict):
    """Pretty-print validation metrics."""
    print("\n" + "=" * 72)
    print("VALIDATION METRICS")
    print("=" * 72)

    print("\nOne-step prediction RMSE:")
    print(f"  {'State':>12s}  {'Linear':>12s}  {'Hybrid':>12s}")
    for name in STATE_NAMES:
        m = metrics['one_step'][name]
        print(f"  {name:>12s}  {m['rmse_linear']:12.2e}  {m['rmse_hybrid']:12.2e}")

    for key_prefix, label in [
        ('multi_step_linear', 'Linear'),
        ('multi_step_hybrid', 'Hybrid (nonlinear kinematics)'),
    ]:
        section = metrics[key_prefix]
        if not section:
            continue
        print(f"\nMulti-step rollout RMSE — {label}:")
        for horizon, state_rmses in section.items():
            print(f"  {horizon}:")
            for name in STATE_NAMES:
                if name in state_rmses:
                    print(f"    {name:>12s}: {state_rmses[name]:.2e}")


# ── Plotting (optional) ─────────────────────────────────────────────────────


def plot_trajectory_comparison(
    result: IdentificationResult,
    test_traj: TrajectoryData,
    n_steps: int = 200,
    start: int = 0,
    save_path: Optional[str] = None,
):
    """Plot actual vs predicted trajectory. Requires matplotlib."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping plot")
        return

    T = min(test_traj.T, start + n_steps + 1)
    actual = test_traj.states[start:T]
    u_seg = test_traj.inputs[start:T - 1]
    x0 = test_traj.states[start]

    pred_lin = simulate_linear(result, x0, u_seg)
    pred_hyb = simulate_hybrid(result, x0, u_seg)

    t = np.arange(actual.shape[0]) * result.dt

    fig, axes = plt.subplots(4, 2, figsize=(14, 10), sharex=True)
    fig.suptitle(f'Model Prediction vs Actual ({n_steps} steps)', fontsize=13)

    plot_info = [
        (0, 0, IX, 'x [m]'), (0, 1, IY, 'y [m]'),
        (1, 0, IV, 'v [m/s]'), (1, 1, ITHETA, 'theta [rad]'),
        (2, 0, ITHETA_DOT, 'theta_dot [rad/s]'), (2, 1, IPSI, 'psi [rad]'),
        (3, 0, IPSI_DOT, 'psi_dot [rad/s]'),
    ]
    for r, c, idx, label in plot_info:
        ax = axes[r, c]
        ax.plot(t, actual[:, idx], 'k-', linewidth=1.2, label='Actual')
        ax.plot(t, pred_lin[:, idx], 'b--', linewidth=0.9, alpha=0.8, label='Linear')
        ax.plot(t, pred_hyb[:, idx], 'r-.', linewidth=0.9, alpha=0.8, label='Hybrid')
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.3)
        if r == 0 and c == 0:
            ax.legend(fontsize=8)

    ax = axes[3, 1]
    ax.plot(actual[:, IX], actual[:, IY], 'k-', linewidth=1.2, label='Actual')
    ax.plot(pred_lin[:, IX], pred_lin[:, IY], 'b--', linewidth=0.9, alpha=0.8, label='Linear')
    ax.plot(pred_hyb[:, IX], pred_hyb[:, IY], 'r-.', linewidth=0.9, alpha=0.8, label='Hybrid')
    ax.set_xlabel('x [m]')
    ax.set_ylabel('y [m]')
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    for ax in axes[-1, :]:
        ax.set_xlabel('Time [s]')

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved plot to {save_path}")
    else:
        plt.show()


# ── Main test ────────────────────────────────────────────────────────────────


def run_test():
    """Run identification tests: without K (legacy) and with K (feedback-aware)."""
    dt = 0.01
    A_d_true, B_d_true = get_test_system(dt)
    K_true = get_test_feedback_gain()

    print("True continuous-time dynamics:")
    A_c_true = (A_d_true - np.eye(N_STATES)) / dt
    B_c_true = B_d_true / dt
    for row in DYNAMIC_ROWS:
        name = STATE_NAMES[row]
        terms = []
        for j in range(N_STATES):
            if abs(A_c_true[row, j]) > 1e-4:
                terms.append(f"{A_c_true[row, j]:+.2f}*{STATE_NAMES[j]}")
        for j in range(N_INPUTS):
            if abs(B_c_true[row, j]) > 1e-4:
                terms.append(f"{B_c_true[row, j]:+.2f}*{INPUT_NAMES[j]}")
        print(f"  d({name})/dt = {' '.join(terms)}")

    def print_comparison(result, label):
        print(f"\n  {label}:")
        print(f"  {'Row':>12s}  {'A_d max err':>12s}  {'B_d max err':>12s}")
        for row in DYNAMIC_ROWS:
            name = STATE_NAMES[row]
            a_err = np.max(np.abs(result.A_d[row] - A_d_true[row]))
            b_err = np.max(np.abs(result.B_d[row] - B_d_true[row]))
            print(f"  {name:>12s}  {a_err:12.2e}  {b_err:12.2e}")

    # ════════════════════════════════════════════════════════════════════
    # TEST 1: Without K (legacy behavior, u_actual in trajectory)
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("TEST 1: Identification WITHOUT K (u_actual in trajectory)")
    print("=" * 72)

    train_no_k = generate_synthetic_trajectories(
        A_d_true, B_d_true, dt=dt, K=None,
        n_trajectories=15, T=500, noise_std=0.001, seed=42,
    )
    config = IdentificationConfig(alpha=1e-3, theta_max=0.3, use_physics_mask=True)
    result_no_k = identify_system(train_no_k, config, K=None)
    print_comparison(result_no_k, "Recovered A_d (open-loop, no K)")

    # ════════════════════════════════════════════════════════════════════
    # TEST 2: With K (feedback-aware, u_ext in trajectory)
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("TEST 2: Identification WITH K (u_ext in trajectory)")
    print("=" * 72)

    train_with_k = generate_synthetic_trajectories(
        A_d_true, B_d_true, dt=dt, K=K_true,
        n_trajectories=15, T=500, noise_std=0.001, seed=42,
    )
    test_with_k = generate_synthetic_trajectories(
        A_d_true, B_d_true, dt=dt, K=K_true,
        n_trajectories=5, T=500, noise_std=0.001, seed=123,
    )

    result_with_k = identify_system(train_with_k, config, K=K_true)
    print_model(result_with_k)
    print_comparison(result_with_k, "Recovered A_d (open-loop, with K)")

    # ════════════════════════════════════════════════════════════════════
    # TEST 3: What happens if you IGNORE K (common mistake)
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("TEST 3: IGNORING K on feedback data (wrong!)")
    print("  Identifies A_cl as if it were A — should show large error")
    print("=" * 72)

    config_no_mask = IdentificationConfig(alpha=1e-3, theta_max=0.3, use_physics_mask=False)
    result_wrong = identify_system(train_with_k, config_no_mask, K=None)
    print_comparison(result_wrong, "A_d error when K is IGNORED")

    # ════════════════════════════════════════════════════════════════════
    # Validation
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("VALIDATION (with K, on test data)")
    print("=" * 72)
    metrics = validate_model(result_with_k, test_with_k, n_steps_list=[1, 10, 50])
    print_validation(metrics)

    try:
        plot_trajectory_comparison(result_with_k, test_with_k[0], n_steps=200)
    except Exception as e:
        print(f"\n(Plotting skipped: {e})")

    return result_with_k


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    run_test()
