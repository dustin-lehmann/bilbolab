"""RRT path planner in (s, theta) configuration space with trajectory conversion."""

import dataclasses

import numpy as np
from scipy.interpolate import CubicSpline

from .cspace import ConfigurationSpace


@dataclasses.dataclass
class RRTConfig:
    """RRT planner parameters."""
    max_iterations: int = 5000
    step_size: float = 0.05           # Max extension per iteration in weighted metric
    goal_bias: float = 0.15           # Fraction of samples aimed at goal
    goal_radius: float = 0.03         # Acceptance radius around goal
    s_weight: float = 1.0             # Weight for s in distance metric
    theta_weight: float = 0.5         # Weight for theta in distance metric
    shortcut_iterations: int = 200    # Random shortcutting passes
    seed: int | None = None


@dataclasses.dataclass
class RRTResult:
    """Result of RRT planning."""
    raw_path: np.ndarray | None        # (N, 2) raw RRT path [(s, theta), ...]
    smoothed_path: np.ndarray | None   # (M, 2) shortcut-smoothed path
    tree_edges: list                    # List of ((s1,t1),(s2,t2)) edges for visualization
    iterations_used: int
    success: bool


class RRTPlanner:
    """Goal-biased RRT in configuration space with weighted distance metric."""

    def __init__(self, cspace: ConfigurationSpace, config: RRTConfig = None):
        self.cspace = cspace
        if config is None:
            config = RRTConfig()
        self.config = config

    def plan(self, start: tuple[float, float], goal: tuple[float, float]) -> RRTResult:
        """Plan a path from start to goal in (s, theta) space.

        Args:
            start: (s, theta) start configuration.
            goal: (s, theta) goal configuration.

        Returns:
            RRTResult with raw and smoothed paths.
        """
        cfg = self.config
        rng = np.random.default_rng(cfg.seed)

        # Validate start/goal
        if not self.cspace.is_free(*start):
            raise ValueError(f"Start configuration {start} is in collision")
        if not self.cspace.is_free(*goal):
            raise ValueError(f"Goal configuration {goal} is in collision")

        # Tree storage
        nodes = [np.array(start)]
        parents = [-1]
        tree_edges = []

        s_lo, s_hi = self.cspace.config.s_range
        t_lo, t_hi = self.cspace.config.theta_range

        ws = cfg.s_weight
        wt = cfg.theta_weight
        goal_arr = np.array(goal)

        for iteration in range(cfg.max_iterations):
            # Sample random configuration (with goal bias)
            if rng.random() < cfg.goal_bias:
                q_rand = goal_arr.copy()
            else:
                q_rand = np.array([
                    rng.uniform(s_lo, s_hi),
                    rng.uniform(t_lo, t_hi),
                ])

            # Find nearest node (weighted distance)
            best_idx = -1
            best_dist = np.inf
            for i, node in enumerate(nodes):
                d = np.sqrt((ws * (node[0] - q_rand[0])) ** 2 +
                            (wt * (node[1] - q_rand[1])) ** 2)
                if d < best_dist:
                    best_dist = d
                    best_idx = i

            q_near = nodes[best_idx]

            # Steer towards q_rand
            direction = q_rand - q_near
            dist = np.sqrt((ws * direction[0]) ** 2 + (wt * direction[1]) ** 2)
            if dist < 1e-12:
                continue
            if dist > cfg.step_size:
                direction = direction * (cfg.step_size / dist)
            q_new = q_near + direction

            # Collision check on edge
            if not self.cspace.is_edge_free(q_near[0], q_near[1], q_new[0], q_new[1]):
                continue

            # Add to tree
            new_idx = len(nodes)
            nodes.append(q_new)
            parents.append(best_idx)
            tree_edges.append(((q_near[0], q_near[1]), (q_new[0], q_new[1])))

            # Check if we reached the goal
            goal_dist = np.sqrt((ws * (q_new[0] - goal_arr[0])) ** 2 +
                                (wt * (q_new[1] - goal_arr[1])) ** 2)
            if goal_dist < cfg.goal_radius:
                # Extract path
                path = [q_new]
                idx = new_idx
                while parents[idx] >= 0:
                    idx = parents[idx]
                    path.append(nodes[idx])
                path.reverse()
                raw_path = np.array(path)

                # Smooth path
                smoothed = self._shortcut_smooth(raw_path, rng)

                return RRTResult(
                    raw_path=raw_path,
                    smoothed_path=smoothed,
                    tree_edges=tree_edges,
                    iterations_used=iteration + 1,
                    success=True,
                )

        return RRTResult(
            raw_path=None,
            smoothed_path=None,
            tree_edges=tree_edges,
            iterations_used=cfg.max_iterations,
            success=False,
        )

    def _shortcut_smooth(self, path: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """Random shortcutting: repeatedly try to skip intermediate waypoints."""
        path = path.copy()
        for _ in range(self.config.shortcut_iterations):
            if len(path) <= 2:
                break
            i = rng.integers(0, len(path) - 2)
            j = rng.integers(i + 2, len(path))
            if self.cspace.is_edge_free(path[i, 0], path[i, 1], path[j, 0], path[j, 1]):
                path = np.vstack([path[:i + 1], path[j:]])
        return path


def path_to_trajectory(path: np.ndarray, dynamics_nonlinear, dynamics_linear,
                       Ts: float, T: float,
                       ilc_iterations: int = 20,
                       ilc_r: float = 1e-4,
                       ilc_s: float = 1e-2) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert a geometric (s, theta) path to a dynamically feasible trajectory.

    Uses cubic spline interpolation with smooth time parameterization to generate
    a reference theta trajectory, then finds feedforward inputs via Iterative
    Learning Control (ILC) using the nonlinear dynamics.

    The ILC tracks the theta component of the reference. The transition matrix P
    is computed from the closed-loop linear system (after pole placement), and the
    optimal learning matrix L is used to iteratively update the feedforward input.

    Args:
        path: (M, 2) array of (s, theta) waypoints.
        dynamics_nonlinear: BILBO_Dynamics_2D with pole placement applied.
        dynamics_linear: BILBO_Dynamics_2D_Linear with pole placement applied.
        Ts: Sample time [s].
        T: Total trajectory duration [s].
        ilc_iterations: Number of ILC iterations.
        ilc_r: ILC input regularization weight.
        ilc_s: ILC robustness weight.

    Returns:
        (t, x_ref, x_traj, u_ff) where:
          t: (N+1,) time vector.
          x_ref: (N+1, 4) reference trajectory [s, v, theta, theta_dot].
          x_traj: (N+1, 4) actual trajectory from nonlinear dynamics.
          u_ff: (N,) feedforward inputs.
    """
    from core.utils.control_lib.lib_control.il.ilc import (
        getTransitionMatrixFromSystem, getLearningMatricesOptimal,
    )

    N = int(round(T / Ts))

    # --- 1. Cubic spline interpolation of path ---
    arc = np.zeros(len(path))
    for i in range(1, len(path)):
        arc[i] = arc[i - 1] + np.linalg.norm(path[i] - path[i - 1])
    arc /= arc[-1]  # Normalize to [0, 1]

    cs_s = CubicSpline(arc, path[:, 0], bc_type='clamped')
    cs_theta = CubicSpline(arc, path[:, 1], bc_type='clamped')

    # --- 2. Smooth time parameterization ---
    # alpha(t) = 10*(t/T)^3 - 15*(t/T)^4 + 6*(t/T)^5  (quintic, zero vel/accel at ends)
    t = np.linspace(0, T, N + 1)
    tau = t / T
    alpha = 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5
    alpha_dot = (30 * tau ** 2 - 60 * tau ** 3 + 30 * tau ** 4) / T

    # --- 3. Reference trajectory: x_ref = [s, v, theta, theta_dot] ---
    s_ref = cs_s(alpha)
    theta_ref = cs_theta(alpha)

    # Velocities via chain rule
    ds_dalpha = cs_s(alpha, 1)
    dtheta_dalpha = cs_theta(alpha, 1)
    v_ref = ds_dalpha * alpha_dot
    theta_dot_ref = dtheta_dalpha * alpha_dot

    x_ref = np.column_stack([s_ref, v_ref, theta_ref, theta_dot_ref])

    # --- 4. ILC to find feedforward inputs ---
    # The transition matrix P maps u_ff[0..N-1] -> theta[1..N] for the
    # closed-loop linear system (C selects theta).
    P = getTransitionMatrixFromSystem(dynamics_linear.system, N=N)
    L, _ = getLearningMatricesOptimal(P, r=ilc_r, s=ilc_s)

    # ILC reference: theta at steps 1..N (output after each input step)
    theta_reference = theta_ref[1:]

    u_ff = np.zeros(N)
    for _ in range(ilc_iterations):
        states = dynamics_nonlinear.simulate(
            input=u_ff, reset=True, include_zero_step=False,
        )
        theta_sim = np.asarray([state.theta for state in states])
        error = theta_reference - theta_sim
        u_ff = u_ff + L @ error

    # --- 5. Final simulation to get full state trajectory ---
    states = dynamics_nonlinear.simulate(
        input=u_ff, reset=True, include_zero_step=True,
    )
    x_traj = np.array([[s.s, s.v, s.theta, s.theta_dot] for s in states])

    return t, x_ref, x_traj, u_ff
