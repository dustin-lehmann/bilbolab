"""Kinodynamic RRT planner for BILBO limbo bar passage.

Plans in the full 4D state space [s, v, theta, theta_dot] by extending the
tree via nonlinear dynamics simulation. Every trajectory in the tree is
physically achievable by construction, enabling maneuvers like the "backslide"
(drive fast, lean backward, coast through on forward momentum).

The steering law uses the closed-loop linear model to compute a constant
feedforward input that approximately steers from x_near toward x_target over
`extension_steps` time steps. The actual extension is simulated with the
nonlinear dynamics, ensuring dynamic feasibility.
"""

import dataclasses

import numpy as np

from .cspace import ConfigurationSpace


@dataclasses.dataclass
class KinodynamicRRTConfig:
    """Kinodynamic RRT planner parameters."""
    max_iterations: int = 10000
    extension_steps: int = 20       # dynamics steps per tree extension
    goal_bias: float = 0.15
    u_max: float = 2.0              # max feedforward torque [Nm]
    goal_radius_s: float = 0.1      # [m]
    goal_radius_theta: float = 0.05 # [rad]
    goal_v_max: float = 0.5         # max |v| at goal [m/s]
    goal_theta_dot_max: float = 1.0 # max |theta_dot| at goal [rad/s]
    v_range: tuple[float, float] = (-1.5, 2.0)
    theta_dot_range: tuple[float, float] = (-5.0, 5.0)
    s_weight: float = 1.0
    v_weight: float = 0.3
    theta_weight: float = 1.0
    theta_dot_weight: float = 0.1
    settling_steps: int = 100       # extra steps with u_ff=0 at goal
    seed: int | None = None


@dataclasses.dataclass
class KinodynamicRRTResult:
    """Result of kinodynamic RRT planning."""
    t: np.ndarray | None = None           # (N+1,) time vector
    x_traj: np.ndarray | None = None      # (N+1, 4) full state trajectory
    u_ff: np.ndarray | None = None        # (N,) feedforward inputs
    tree_nodes: list = dataclasses.field(default_factory=list)   # list of 4D state arrays
    tree_edges: list = dataclasses.field(default_factory=list)   # list of ((s1,t1),(s2,t2)) for C-space viz
    iterations_used: int = 0
    success: bool = False


class KinodynamicRRTPlanner:
    """Kinodynamic RRT planner in 4D state space [s, v, theta, theta_dot].

    Uses the closed-loop linear model for approximate steering and the
    nonlinear dynamics for actual tree extension, ensuring dynamic feasibility.
    """

    def __init__(self, cspace: ConfigurationSpace, dynamics_nonlinear, dynamics_linear,
                 config: KinodynamicRRTConfig = None):
        """
        Args:
            cspace: Configuration space for collision checking.
            dynamics_nonlinear: BILBO_Dynamics_2D with pole placement applied.
            dynamics_linear: BILBO_Dynamics_2D_Linear with pole placement applied.
            config: Planner parameters.
        """
        self.cspace = cspace
        self.dynamics_nl = dynamics_nonlinear
        self.dynamics_lin = dynamics_linear
        if config is None:
            config = KinodynamicRRTConfig()
        self.config = config

        # Precompute steering matrices from the closed-loop linear model
        A_cl = np.array(dynamics_linear.system.A)
        B = np.array(dynamics_linear.system.B)
        n = config.extension_steps

        # A_cl^n
        self._A_cl_n = np.linalg.matrix_power(A_cl, n)

        # G = sum_{k=0}^{n-1} A_cl^k @ B — maps constant input to state offset
        G = np.zeros((A_cl.shape[0], B.shape[1]))
        A_power = np.eye(A_cl.shape[0])
        for _ in range(n):
            G += A_power @ B
            A_power = A_power @ A_cl
        self._G = G

        # G_pinv for scalar input: G.T / (G.T @ G)
        # G is (4,1), so G.T @ G is (1,1) scalar
        GtG = G.T @ G
        self._G_pinv = G.T / GtG  # (1, 4)

    def plan(self, start: tuple[float, float], goal: tuple[float, float],
             Ts: float) -> KinodynamicRRTResult:
        """Run the kinodynamic RRT.

        Args:
            start: (s_start, theta_start) initial configuration.
            goal: (s_goal, theta_goal) goal configuration.
            Ts: Sample time [s].

        Returns:
            KinodynamicRRTResult with trajectory and tree.
        """
        cfg = self.config
        rng = np.random.default_rng(cfg.seed)

        s_start, theta_start = start
        s_goal, theta_goal = goal

        x_start = np.array([s_start, 0.0, theta_start, 0.0])
        x_goal = np.array([s_goal, 0.0, theta_goal, 0.0])

        # Validate start/goal in C-space
        if not self.cspace.is_free(s_start, theta_start):
            raise ValueError(f"Start configuration ({s_start}, {theta_start}) is in collision")
        if not self.cspace.is_free(s_goal, theta_goal):
            raise ValueError(f"Goal configuration ({s_goal}, {theta_goal}) is in collision")

        # Tree storage
        nodes = [x_start.copy()]               # list of 4D state vectors
        parents = [-1]                          # parent index for each node
        traj_segments = [None]                  # trajectory segment leading to each node
        input_segments = [None]                 # input segment leading to each node
        tree_edges = []

        s_lo, s_hi = self.cspace.config.s_range
        t_lo, t_hi = self.cspace.config.theta_range

        weights = np.array([cfg.s_weight, cfg.v_weight, cfg.theta_weight, cfg.theta_dot_weight])

        collisions_total = 0
        best_goal_dist_s = abs(s_start - s_goal)
        best_goal_dist_theta = abs(theta_start - theta_goal)
        log_interval = max(1, cfg.max_iterations // 20)  # ~20 progress prints

        for iteration in range(cfg.max_iterations):
            # --- Progress logging ---
            if iteration % log_interval == 0 and iteration > 0:
                print(f"  [RRT] iter {iteration}/{cfg.max_iterations} | "
                      f"nodes: {len(nodes)} | collisions: {collisions_total} | "
                      f"best dist to goal: ds={best_goal_dist_s:.3f}m, "
                      f"dtheta={np.degrees(best_goal_dist_theta):.1f}deg")

            # --- Sample ---
            if rng.random() < cfg.goal_bias:
                x_rand = x_goal.copy()
            else:
                x_rand = np.array([
                    rng.uniform(s_lo, s_hi),
                    rng.uniform(cfg.v_range[0], cfg.v_range[1]),
                    rng.uniform(t_lo, t_hi),
                    rng.uniform(cfg.theta_dot_range[0], cfg.theta_dot_range[1]),
                ])

            # --- Nearest neighbor (weighted Euclidean) ---
            best_idx = -1
            best_dist = np.inf
            for i, node in enumerate(nodes):
                diff = node - x_rand
                d = np.sqrt(np.sum((weights * diff) ** 2))
                if d < best_dist:
                    best_dist = d
                    best_idx = i

            x_near = nodes[best_idx]

            # --- Steer: compute constant feedforward input ---
            x_target_offset = x_rand - self._A_cl_n @ x_near
            u_scalar = float(self._G_pinv @ x_target_offset)
            u_scalar = np.clip(u_scalar, -cfg.u_max, cfg.u_max)

            # --- Extend: simulate nonlinear dynamics ---
            u_seq = np.full(cfg.extension_steps, u_scalar)
            from robots.bilbo.simulation.model import BILBO_2D_State
            x0_state = BILBO_2D_State(s=x_near[0], v=x_near[1],
                                       theta=x_near[2], theta_dot=x_near[3])
            states = self.dynamics_nl.simulate(
                input=u_seq, x0=x0_state, reset=False, include_zero_step=False,
            )

            # Convert states to array
            seg_states = np.array([[st.s, st.v, st.theta, st.theta_dot] for st in states])

            # --- Collision & bounds check at each simulated state ---
            collision = False
            for k in range(len(seg_states)):
                sk, thetak = seg_states[k, 0], seg_states[k, 2]
                # Reject states outside C-space bounds
                if (sk < s_lo or sk > s_hi or thetak < t_lo or thetak > t_hi):
                    collision = True
                    break
                if not self.cspace.is_free(sk, thetak):
                    collision = True
                    break
            if collision:
                collisions_total += 1
                continue

            # --- Add to tree ---
            x_new = seg_states[-1]
            new_idx = len(nodes)
            nodes.append(x_new.copy())
            parents.append(best_idx)
            traj_segments.append(seg_states)
            input_segments.append(u_seq)
            tree_edges.append(((x_near[0], x_near[2]), (x_new[0], x_new[2])))

            # Track best distance to goal
            dist_s = abs(x_new[0] - s_goal)
            dist_theta = abs(x_new[2] - theta_goal)
            if dist_s < best_goal_dist_s:
                best_goal_dist_s = dist_s
            if dist_theta < best_goal_dist_theta:
                best_goal_dist_theta = dist_theta

            # --- Goal check ---
            if (abs(x_new[0] - s_goal) < cfg.goal_radius_s and
                    abs(x_new[2] - theta_goal) < cfg.goal_radius_theta and
                    abs(x_new[1]) < cfg.goal_v_max and
                    abs(x_new[3]) < cfg.goal_theta_dot_max):
                print(f"  [RRT] Goal reached at iter {iteration + 1} | "
                      f"nodes: {len(nodes)} | collisions: {collisions_total} | "
                      f"x_new=[s={x_new[0]:.3f}, v={x_new[1]:.3f}, "
                      f"theta={np.degrees(x_new[2]):.1f}deg, "
                      f"theta_dot={x_new[3]:.2f}]")
                return self._extract_trajectory(
                    nodes, parents, traj_segments, input_segments,
                    new_idx, tree_edges, iteration + 1, Ts,
                )

        # Failed
        print(f"  [RRT] FAILED after {cfg.max_iterations} iterations | "
              f"nodes: {len(nodes)} | collisions: {collisions_total} | "
              f"best dist: ds={best_goal_dist_s:.3f}m, "
              f"dtheta={np.degrees(best_goal_dist_theta):.1f}deg")
        return KinodynamicRRTResult(
            tree_nodes=[n.copy() for n in nodes],
            tree_edges=tree_edges,
            iterations_used=cfg.max_iterations,
            success=False,
        )

    def _extract_trajectory(self, nodes, parents, traj_segments, input_segments,
                            goal_idx, tree_edges, iterations_used, Ts):
        """Backtrack through parents, concatenate segments, add settling phase."""
        cfg = self.config

        # Backtrack to get path of node indices
        path_indices = []
        idx = goal_idx
        while idx >= 0:
            path_indices.append(idx)
            idx = parents[idx]
        path_indices.reverse()

        # Concatenate trajectory segments (skip the root which has no segment)
        all_states = [nodes[path_indices[0]].reshape(1, 4)]  # start state
        all_inputs = []
        for i in range(1, len(path_indices)):
            node_idx = path_indices[i]
            all_states.append(traj_segments[node_idx])
            all_inputs.append(input_segments[node_idx])

        x_traj = np.vstack(all_states)
        u_ff = np.concatenate(all_inputs)

        # --- Settling phase: u_ff=0 to let controller bring robot to rest ---
        if cfg.settling_steps > 0:
            from robots.bilbo.simulation.model import BILBO_2D_State
            u_settle = np.zeros(cfg.settling_steps)
            x_last = x_traj[-1]
            x0_state = BILBO_2D_State(s=x_last[0], v=x_last[1],
                                       theta=x_last[2], theta_dot=x_last[3])
            settle_states = self.dynamics_nl.simulate(
                input=u_settle, x0=x0_state, reset=False, include_zero_step=False,
            )
            settle_arr = np.array([[st.s, st.v, st.theta, st.theta_dot]
                                   for st in settle_states])
            x_traj = np.vstack([x_traj, settle_arr])
            u_ff = np.concatenate([u_ff, u_settle])

        # Build time vector
        N = len(u_ff)
        t = np.arange(N + 1) * Ts

        return KinodynamicRRTResult(
            t=t,
            x_traj=x_traj,
            u_ff=u_ff,
            tree_nodes=[n.copy() for n in nodes],
            tree_edges=tree_edges,
            iterations_used=iterations_used,
            success=True,
        )


def smooth_trajectory(rrt_result: KinodynamicRRTResult,
                      dynamics_nonlinear,
                      cspace: ConfigurationSpace,
                      margin: float = 0.3,
                      taper_steps: int = 50) -> KinodynamicRRTResult:
    """Smooth a kinodynamic RRT trajectory by zeroing u_ff away from obstacles.

    Identifies the "critical region" where the trajectory passes near obstacles
    (based on C-space proximity), keeps the RRT's u_ff there, and smoothly
    tapers it to zero outside. The stabilizing controller naturally produces
    clean driving when u_ff=0, eliminating unnecessary theta oscillations in
    the approach and departure phases.

    Args:
        rrt_result: Successful KinodynamicRRTResult.
        dynamics_nonlinear: BILBO_Dynamics_2D with pole placement applied.
        cspace: Configuration space (for obstacle proximity check).
        margin: s-distance beyond obstacle region to keep u_ff active [m].
        taper_steps: Number of timesteps over which to taper u_ff to zero.

    Returns:
        New KinodynamicRRTResult with smoothed trajectory.
    """
    x_traj = rrt_result.x_traj
    u_ff = rrt_result.u_ff.copy()
    N = len(u_ff)

    # Find timesteps near obstacles: where (s, theta) is close to occupied cells
    near_obstacle = np.zeros(N + 1, dtype=bool)
    for k in range(N + 1):
        s_k, theta_k = x_traj[k, 0], x_traj[k, 2]
        i, j = cspace._to_index(s_k, theta_k)
        # Check a neighborhood around the current grid cell
        radius = 15  # grid cells
        i_lo = max(0, i - radius)
        i_hi = min(cspace.config.s_resolution, i + radius + 1)
        j_lo = max(0, j - radius)
        j_hi = min(cspace.config.theta_resolution, j + radius + 1)
        if cspace.occupied[i_lo:i_hi, j_lo:j_hi].any():
            near_obstacle[k] = True

    # Expand the critical region by margin (in terms of s distance)
    critical = near_obstacle.copy()
    Ts = rrt_result.t[1] - rrt_result.t[0] if len(rrt_result.t) > 1 else 0.01
    margin_steps = max(1, int(margin / (abs(x_traj[:, 1].mean()) * Ts + 1e-6)))
    margin_steps = min(margin_steps, N // 4)  # don't expand more than 25% of trajectory

    # Simple dilation: expand True regions by margin_steps in both directions
    critical_indices = np.where(critical)[0]
    if len(critical_indices) > 0:
        first_critical = max(0, critical_indices[0] - margin_steps)
        last_critical = min(N, critical_indices[-1] + margin_steps)
    else:
        # No obstacles nearby at all — zero everything
        first_critical = N
        last_critical = 0

    # Build smooth window: 1 in critical region, tapers to 0 outside
    window = np.zeros(N)
    for k in range(N):
        if first_critical <= k <= last_critical:
            window[k] = 1.0
        elif k < first_critical:
            dist = first_critical - k
            if dist <= taper_steps:
                window[k] = 0.5 * (1 + np.cos(np.pi * dist / taper_steps))
        else:  # k > last_critical
            dist = k - last_critical
            if dist <= taper_steps:
                window[k] = 0.5 * (1 + np.cos(np.pi * dist / taper_steps))

    # Apply window to u_ff
    u_ff_smooth = u_ff * window

    # Re-simulate with smoothed inputs
    states = dynamics_nonlinear.simulate(
        input=u_ff_smooth, reset=True, include_zero_step=True,
    )
    x_traj_new = np.array([[s.s, s.v, s.theta, s.theta_dot] for s in states])

    return KinodynamicRRTResult(
        t=rrt_result.t,
        x_traj=x_traj_new,
        u_ff=u_ff_smooth,
        tree_nodes=rrt_result.tree_nodes,
        tree_edges=rrt_result.tree_edges,
        iterations_used=rrt_result.iterations_used,
        success=True,
    )


def truncate_after_obstacles(rrt_result: KinodynamicRRTResult,
                             dynamics_nonlinear,
                             cspace: ConfigurationSpace,
                             margin_steps: int = 50,
                             settling_steps: int = 300,
                             proximity_radius: int = 15) -> KinodynamicRRTResult:
    """Truncate trajectory after the last obstacle proximity and coast to rest.

    After the kinodynamic RRT clears all obstacles, the remaining trajectory
    tends to be unnecessarily convoluted. This function cuts the trajectory
    shortly after obstacle clearance and appends a settling phase with u_ff=0,
    letting the closed-loop controller naturally bring the robot to rest.

    Args:
        rrt_result: Successful KinodynamicRRTResult.
        dynamics_nonlinear: BILBO_Dynamics_2D with pole placement applied.
        cspace: Configuration space (for obstacle proximity check).
        margin_steps: Extra timesteps to keep after last obstacle proximity.
        settling_steps: Number of u_ff=0 steps to simulate for coasting to rest.
        proximity_radius: Grid cell radius for obstacle neighborhood check.

    Returns:
        New KinodynamicRRTResult with truncated + settling trajectory.
    """
    x_traj = rrt_result.x_traj
    u_ff = rrt_result.u_ff
    N = len(u_ff)

    # Find the last timestep near any obstacle
    last_near_obstacle = -1
    for k in range(N + 1):
        s_k, theta_k = x_traj[k, 0], x_traj[k, 2]
        i, j = cspace._to_index(s_k, theta_k)
        i_lo = max(0, i - proximity_radius)
        i_hi = min(cspace.config.s_resolution, i + proximity_radius + 1)
        j_lo = max(0, j - proximity_radius)
        j_hi = min(cspace.config.theta_resolution, j + proximity_radius + 1)
        if cspace.occupied[i_lo:i_hi, j_lo:j_hi].any():
            last_near_obstacle = k

    if last_near_obstacle < 0:
        # No obstacles encountered — nothing to truncate
        return rrt_result

    # Cut point: margin after last obstacle proximity, capped at trajectory length
    cut_k = min(last_near_obstacle + margin_steps, N)

    # Keep trajectory up to cut point
    x_kept = x_traj[:cut_k + 1]
    u_kept = u_ff[:cut_k]

    # Simulate settling phase from the truncation state with u_ff=0
    if settling_steps > 0:
        from robots.bilbo.simulation.model import BILBO_2D_State
        x_last = x_kept[-1]
        x0_state = BILBO_2D_State(s=x_last[0], v=x_last[1],
                                   theta=x_last[2], theta_dot=x_last[3])
        u_settle = np.zeros(settling_steps)
        settle_states = dynamics_nonlinear.simulate(
            input=u_settle, x0=x0_state, reset=False, include_zero_step=False,
        )
        settle_arr = np.array([[st.s, st.v, st.theta, st.theta_dot]
                               for st in settle_states])
        x_traj_new = np.vstack([x_kept, settle_arr])
        u_ff_new = np.concatenate([u_kept, u_settle])
    else:
        x_traj_new = x_kept
        u_ff_new = u_kept

    # Build time vector
    Ts = rrt_result.t[1] - rrt_result.t[0] if len(rrt_result.t) > 1 else 0.01
    N_new = len(u_ff_new)
    t_new = np.arange(N_new + 1) * Ts

    print(f"  [Truncate] Cut at step {cut_k}/{N} "
          f"(last obstacle at {last_near_obstacle}, +{margin_steps} margin), "
          f"added {settling_steps} settling steps → {N_new} total steps")

    return KinodynamicRRTResult(
        t=t_new,
        x_traj=x_traj_new,
        u_ff=u_ff_new,
        tree_nodes=rrt_result.tree_nodes,
        tree_edges=rrt_result.tree_edges,
        iterations_used=rrt_result.iterations_used,
        success=True,
    )


def refine_trajectory(rrt_result: KinodynamicRRTResult,
                      dynamics_nonlinear, dynamics_linear,
                      ilc_iterations: int = 20,
                      ilc_r: float = 1e-4,
                      ilc_s: float = 1e-2) -> tuple[np.ndarray, np.ndarray]:
    """Refine a kinodynamic RRT trajectory using ILC.

    Uses the theta profile from the RRT result as the ILC reference and
    initializes the ILC with the kinodynamic u_ff (already close to the
    solution). Runs ILC iterations to produce smoother inputs.

    Args:
        rrt_result: Successful KinodynamicRRTResult.
        dynamics_nonlinear: BILBO_Dynamics_2D with pole placement applied.
        dynamics_linear: BILBO_Dynamics_2D_Linear with pole placement applied.
        ilc_iterations: Number of ILC refinement iterations.
        ilc_r: ILC input regularization weight.
        ilc_s: ILC robustness weight.

    Returns:
        (x_traj_refined, u_ff_refined) where:
          x_traj_refined: (N+1, 4) refined trajectory from nonlinear dynamics.
          u_ff_refined: (N,) refined feedforward inputs.
    """
    from core.utils.control_lib.lib_control.il.ilc import (
        getTransitionMatrixFromSystem, getLearningMatricesOptimal,
    )

    N = len(rrt_result.u_ff)
    theta_reference = rrt_result.x_traj[1:, 2]  # theta at steps 1..N

    # Compute ILC learning matrix from closed-loop linear system
    P = getTransitionMatrixFromSystem(dynamics_linear.system, N=N)
    L, _ = getLearningMatricesOptimal(P, r=ilc_r, s=ilc_s)

    # Start from kinodynamic u_ff (warm start)
    u_ff = rrt_result.u_ff.copy()

    for _ in range(ilc_iterations):
        states = dynamics_nonlinear.simulate(
            input=u_ff, reset=True, include_zero_step=False,
        )
        theta_sim = np.array([state.theta for state in states])
        error = theta_reference - theta_sim
        u_ff = u_ff + L @ error

    # Final simulation
    states = dynamics_nonlinear.simulate(
        input=u_ff, reset=True, include_zero_step=True,
    )
    x_traj = np.array([[s.s, s.v, s.theta, s.theta_dot] for s in states])

    return x_traj, u_ff
