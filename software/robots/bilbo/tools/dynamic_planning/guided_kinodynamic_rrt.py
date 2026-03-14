"""Guided kinodynamic RRT planner for BILBO limbo bar passage.

Uses a geometric RRT as a preprocessing step to find the collision-free
corridor in (s, theta) C-space, then biases kinodynamic RRT sampling toward
that corridor. This dramatically speeds up the search by focusing the 4D
exploration on the region that matters.

The geometric RRT finds the narrow passage in milliseconds (2D search).
The kinodynamic RRT then only needs to figure out the velocity/momentum
profile to traverse that corridor — a much easier problem than blind 4D search.
"""

import dataclasses

import numpy as np

from .cspace import ConfigurationSpace
from .rrt_planner import RRTPlanner, RRTConfig, RRTResult
from .kinodynamic_rrt import KinodynamicRRTConfig, KinodynamicRRTResult
from robots.bilbo.simulation.model import BILBO_2D_State


@dataclasses.dataclass
class GuidedKinodynamicRRTConfig(KinodynamicRRTConfig):
    """Config for guided kinodynamic RRT.

    Extends KinodynamicRRTConfig with geometric guide parameters.
    """
    # Geometric RRT config for the guide path
    guide_rrt: RRTConfig = dataclasses.field(default_factory=lambda: RRTConfig(
        max_iterations=5000,
        step_size=0.06,
        goal_bias=0.15,
        goal_radius=0.04,
        s_weight=1.0,
        theta_weight=0.3,
        shortcut_iterations=300,
    ))
    guide_bias: float = 0.5        # fraction of samples drawn near the guide path
    guide_s_noise: float = 0.15    # std dev of noise added to s when sampling near guide [m]
    guide_theta_noise: float = 0.1 # std dev of noise added to theta when sampling near guide [rad]


class GuidedKinodynamicRRTPlanner:
    """Kinodynamic RRT with geometric guide path for focused sampling.

    Pipeline:
    1. Run geometric RRT in (s, theta) to find collision-free corridor
    2. Run kinodynamic RRT with sampling biased toward that corridor
    3. Guided samples: pick random point on guide path + noise for (s, theta),
       sample v and theta_dot freely
    """

    def __init__(self, cspace: ConfigurationSpace, dynamics_nonlinear, dynamics_linear,
                 config: GuidedKinodynamicRRTConfig = None):
        self.cspace = cspace
        self.dynamics_nl = dynamics_nonlinear
        self.dynamics_lin = dynamics_linear
        if config is None:
            config = GuidedKinodynamicRRTConfig()
        self.config = config

        # Precompute steering matrices from the closed-loop linear model
        A_cl = np.array(dynamics_linear.system.A)
        B = np.array(dynamics_linear.system.B)
        n = config.extension_steps

        self._A_cl_n = np.linalg.matrix_power(A_cl, n)

        G = np.zeros((A_cl.shape[0], B.shape[1]))
        A_power = np.eye(A_cl.shape[0])
        for _ in range(n):
            G += A_power @ B
            A_power = A_power @ A_cl
        self._G = G

        GtG = G.T @ G
        self._G_pinv = G.T / GtG

    def plan(self, start: tuple[float, float], goal: tuple[float, float],
             Ts: float) -> KinodynamicRRTResult:
        """Run the guided kinodynamic RRT.

        Args:
            start: (s_start, theta_start) initial configuration.
            goal: (s_goal, theta_goal) goal configuration.
            Ts: Sample time [s].

        Returns:
            KinodynamicRRTResult with trajectory and tree.
        """
        cfg = self.config

        # --- Phase 1: Geometric guide path ---
        print("  [Guided RRT] Phase 1: Running geometric RRT for guide path...")
        guide_rrt_config = cfg.guide_rrt
        # Use the same seed base for reproducibility
        if cfg.seed is not None:
            guide_rrt_config = dataclasses.replace(guide_rrt_config, seed=cfg.seed)
        geo_rrt = RRTPlanner(self.cspace, config=guide_rrt_config)
        geo_result = geo_rrt.plan(start, goal)

        if not geo_result.success:
            print("  [Guided RRT] Geometric RRT failed! Falling back to unguided kinodynamic RRT.")
            guide_path = None
        else:
            raw_path = geo_result.smoothed_path
            print(f"  [Guided RRT] Geometric path: {len(raw_path)} waypoints "
                  f"in {geo_result.iterations_used} iterations")

            # Resample to dense evenly-spaced points for uniform guide sampling
            guide_path = self._resample_path(raw_path, n_points=100)
            print(f"  [Guided RRT] Resampled guide path to {len(guide_path)} points")

            self._guide_path = guide_path

            # Compute per-point sampling weights: higher near obstacles
            weights = self._compute_obstacle_proximity_weights(guide_path, self.cspace)
            self._guide_weights = weights / weights.sum()  # normalize to probability distribution
            print(f"  [Guided RRT] Guide weight range: "
                  f"min={self._guide_weights.min():.4f}, max={self._guide_weights.max():.4f}")

        # --- Phase 2: Kinodynamic RRT with guided sampling ---
        print("  [Guided RRT] Phase 2: Running kinodynamic RRT...")
        rng = np.random.default_rng(cfg.seed)

        s_start, theta_start = start
        s_goal, theta_goal = goal

        x_start = np.array([s_start, 0.0, theta_start, 0.0])
        x_goal = np.array([s_goal, 0.0, theta_goal, 0.0])

        if not self.cspace.is_free(s_start, theta_start):
            raise ValueError(f"Start configuration ({s_start}, {theta_start}) is in collision")
        if not self.cspace.is_free(s_goal, theta_goal):
            raise ValueError(f"Goal configuration ({s_goal}, {theta_goal}) is in collision")

        nodes = [x_start.copy()]
        parents = [-1]
        traj_segments = [None]
        input_segments = [None]
        tree_edges = []

        s_lo, s_hi = self.cspace.config.s_range
        t_lo, t_hi = self.cspace.config.theta_range

        weights = np.array([cfg.s_weight, cfg.v_weight, cfg.theta_weight, cfg.theta_dot_weight])

        collisions_total = 0
        best_goal_dist_s = abs(s_start - s_goal)
        best_goal_dist_theta = abs(theta_start - theta_goal)
        guided_samples = 0
        log_interval = max(1, cfg.max_iterations // 20)

        for iteration in range(cfg.max_iterations):
            if iteration % log_interval == 0 and iteration > 0:
                guide_pct = (guided_samples / iteration * 100) if iteration > 0 else 0
                print(f"  [RRT] iter {iteration}/{cfg.max_iterations} | "
                      f"nodes: {len(nodes)} | collisions: {collisions_total} | "
                      f"guided: {guide_pct:.0f}% | "
                      f"best dist: ds={best_goal_dist_s:.3f}m, "
                      f"dtheta={np.degrees(best_goal_dist_theta):.1f}deg")

            # --- Sample ---
            r = rng.random()
            if r < cfg.goal_bias:
                x_rand = x_goal.copy()
            elif guide_path is not None and r < cfg.goal_bias + cfg.guide_bias:
                # Sample near the guide path
                x_rand = self._sample_near_guide(rng, cfg, s_lo, s_hi, t_lo, t_hi)
                guided_samples += 1
            else:
                x_rand = np.array([
                    rng.uniform(s_lo, s_hi),
                    rng.uniform(cfg.v_range[0], cfg.v_range[1]),
                    rng.uniform(t_lo, t_hi),
                    rng.uniform(cfg.theta_dot_range[0], cfg.theta_dot_range[1]),
                ])

            # --- Nearest neighbor ---
            best_idx = -1
            best_dist = np.inf
            for i, node in enumerate(nodes):
                diff = node - x_rand
                d = np.sqrt(np.sum((weights * diff) ** 2))
                if d < best_dist:
                    best_dist = d
                    best_idx = i

            x_near = nodes[best_idx]

            # --- Steer ---
            x_target_offset = x_rand - self._A_cl_n @ x_near
            u_scalar = float(self._G_pinv @ x_target_offset)
            u_scalar = np.clip(u_scalar, -cfg.u_max, cfg.u_max)

            # --- Extend ---
            u_seq = np.full(cfg.extension_steps, u_scalar)
            x0_state = BILBO_2D_State(s=x_near[0], v=x_near[1],
                                       theta=x_near[2], theta_dot=x_near[3])
            states = self.dynamics_nl.simulate(
                input=u_seq, x0=x0_state, reset=False, include_zero_step=False,
            )

            seg_states = np.array([[st.s, st.v, st.theta, st.theta_dot] for st in states])

            # --- Collision & bounds check ---
            collision = False
            for k in range(len(seg_states)):
                sk, thetak = seg_states[k, 0], seg_states[k, 2]
                if sk < s_lo or sk > s_hi or thetak < t_lo or thetak > t_hi:
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

    @staticmethod
    def _resample_path(path: np.ndarray, n_points: int = 100) -> np.ndarray:
        """Resample a path to n_points evenly spaced along arc length."""
        arc = np.zeros(len(path))
        for i in range(1, len(path)):
            arc[i] = arc[i - 1] + np.linalg.norm(path[i] - path[i - 1])
        total = arc[-1]
        if total < 1e-12:
            return path

        target_arc = np.linspace(0, total, n_points)
        resampled = np.zeros((n_points, path.shape[1]))
        for i, t in enumerate(target_arc):
            idx = np.searchsorted(arc, t, side='right') - 1
            idx = np.clip(idx, 0, len(path) - 2)
            seg_len = arc[idx + 1] - arc[idx]
            alpha = (t - arc[idx]) / seg_len if seg_len > 1e-12 else 0.0
            resampled[i] = path[idx] + alpha * (path[idx + 1] - path[idx])
        return resampled

    @staticmethod
    def _compute_obstacle_proximity_weights(path: np.ndarray, cspace: ConfigurationSpace,
                                            kernel_radius: int = 10) -> np.ndarray:
        """Compute per-point weights based on proximity to occupied C-space cells.

        Points near obstacles get higher weight so the guided sampling
        concentrates on the narrow passage where the kinodynamic RRT needs
        the most help.

        Args:
            path: (N, 2) resampled guide path in (s, theta).
            cspace: Configuration space with occupancy grid.
            kernel_radius: Radius in grid cells to search for nearby obstacles.

        Returns:
            (N,) weight array (unnormalized, all > 0).
        """
        n = len(path)
        weights = np.ones(n)  # baseline weight so every point has some chance

        for i in range(n):
            gi, gj = cspace._to_index(path[i, 0], path[i, 1])

            # Extract local patch around this grid cell
            i_lo = max(0, gi - kernel_radius)
            i_hi = min(cspace.config.s_resolution, gi + kernel_radius + 1)
            j_lo = max(0, gj - kernel_radius)
            j_hi = min(cspace.config.theta_resolution, gj + kernel_radius + 1)

            patch = cspace.occupied[i_lo:i_hi, j_lo:j_hi]
            n_occupied = patch.sum()

            # Weight = 1 + occupied neighbor count (so near-obstacle points dominate)
            weights[i] = 1.0 + n_occupied

        return weights

    def _sample_near_guide(self, rng, cfg, s_lo, s_hi, t_lo, t_hi) -> np.ndarray:
        """Sample a 4D state near the geometric guide path.

        Picks a guide point weighted by obstacle proximity, adds Gaussian noise
        to (s, theta), and samples v and theta_dot from the full range.
        """
        # Pick a guide point, weighted toward obstacle-adjacent regions
        idx = rng.choice(len(self._guide_path), p=self._guide_weights)
        pt = self._guide_path[idx]

        # Add noise and clamp to C-space bounds
        s = np.clip(pt[0] + rng.normal(0, cfg.guide_s_noise), s_lo, s_hi)
        theta = np.clip(pt[1] + rng.normal(0, cfg.guide_theta_noise), t_lo, t_hi)

        # v and theta_dot sampled freely
        v = rng.uniform(cfg.v_range[0], cfg.v_range[1])
        theta_dot = rng.uniform(cfg.theta_dot_range[0], cfg.theta_dot_range[1])

        return np.array([s, v, theta, theta_dot])

    def _extract_trajectory(self, nodes, parents, traj_segments, input_segments,
                            goal_idx, tree_edges, iterations_used, Ts):
        """Backtrack through parents, concatenate segments, add settling phase."""
        cfg = self.config

        path_indices = []
        idx = goal_idx
        while idx >= 0:
            path_indices.append(idx)
            idx = parents[idx]
        path_indices.reverse()

        all_states = [nodes[path_indices[0]].reshape(1, 4)]
        all_inputs = []
        for i in range(1, len(path_indices)):
            node_idx = path_indices[i]
            all_states.append(traj_segments[node_idx])
            all_inputs.append(input_segments[node_idx])

        x_traj = np.vstack(all_states)
        u_ff = np.concatenate(all_inputs)

        if cfg.settling_steps > 0:
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
