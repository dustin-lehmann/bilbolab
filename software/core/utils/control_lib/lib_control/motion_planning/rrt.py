"""
RRT / RRT* Motion Planner for BILBO robots.

Computes collision-free paths through a 2D workspace with:
- Weighted waypoints (weight controls proximity requirement)
- Circle and box obstacles (boxes support rotation via psi angle)
- Workspace boundaries
- Adaptive curvature-based output sampling

Algorithm pipeline:
    1. Segment-wise goal-biased RRT (straight line preferred when free)
    2. Greedy path pruning per segment
    3. Global waypoint zone optimization (minimize path length within zones)
    4. Re-planning between optimized waypoints
    5. Cubic spline smoothing with collision safety
    6. Adaptive curvature-based resampling

Usage:
    from core.utils.control_lib.lib_control.motion_planning import *

    path = plan_path(
        start=(0.3, 0.3),
        end=(2.7, 2.7),
        waypoints=[Waypoint(1.5, 0.5, weight=0.8), Waypoint(1.5, 2.0, weight=0.2)],
        obstacles=[CircleObstacle(1.5, 1.2, 0.3)],
        bounds=Bounds(0, 3, 0, 3),
    )

    # Debug mode — returns PlanResult with all intermediate stages:
    result = plan_path(..., debug=True)
    plot_stages(result)
"""

import math
import random
import time

import numpy as np

from .common import (
    OBSTACLE_MARGIN, OPTIMIZATION_ITERATIONS, SAMPLE_DS_MAX, SAMPLE_DS_MIN,
    UNIFORM_DS, WAYPOINT_RADIUS_MAX, WAYPOINT_RADIUS_MIN,
    Bounds, BoxObstacle, CircleObstacle, Obstacle, PlanResult,
    StateConstraints, Waypoint,
    _SEGMENT_COLORS,
    _bounds_to_walls, _dist, _draw_background, _draw_box_patch,
    _draw_padding, _draw_state_constraints,
    _edge_clearance_cost, _ensure_spline_safety,
    _fit_parametric_spline, _line_collides, _min_clearance,
    _optimize_connection_points, _point_collides, _prune_path,
    _rotate_to_local, _seg_intersects_aabb, _seg_point_dist,
    _state_constraints_to_walls, _subdivide_polyline,
    _uniform_resample, _uniform_spline_samples,
    _waypoint_zone_radius, plot_path,
)

# ============================================================================
# RRT Parameters
# ============================================================================

# RRT
RRT_STEP_SIZE = 0.10         # [m] max extension per iteration
RRT_MAX_ITERATIONS = 10000   # max iterations per segment
RRT_GOAL_BIAS = 0.10         # fraction of samples aimed at goal

# RRT*
RRT_STAR_REWIRE_RADIUS = 0.30  # [m] neighborhood radius for rewiring (~3x step size)
RRT_STAR_MAX_ITERATIONS = 30000  # default iterations for RRT* (needs more for rewiring benefit)

# ============================================================================
# RRT Planner
# ============================================================================

class _RRTNode:
    __slots__ = ('x', 'y', 'parent', 'cost')

    def __init__(self, x: float, y: float, parent=None, cost: float = 0.0):
        self.x = x
        self.y = y
        self.parent = parent
        self.cost = cost


def _rrt_plan(start, goal_center, goal_radius, obstacles, bounds, rng,
              return_tree=False, margin=OBSTACLE_MARGIN,
              max_iterations=RRT_MAX_ITERATIONS,
              step_size=RRT_STEP_SIZE, goal_bias=RRT_GOAL_BIAS):
    """
    Goal-biased Rapidly-exploring Random Tree (RRT).

    Parameters
    ----------
    start : (x, y)
        Root of the tree.
    goal_center : (x, y)
        Center of the goal region.
    goal_radius : float
        The tree reaches the goal when a node falls within this radius.
    obstacles : list of Obstacle
        All obstacles to avoid (including wall obstacles).
    bounds : Bounds
        Workspace limits.
    rng : random.Random
        Random number generator.
    return_tree : bool
        If True, also return all tree edges for visualization.
    margin : float
        Safety clearance around obstacles.
    max_iterations : int
        Maximum tree-growth iterations before giving up.
    step_size : float
        Maximum extension distance per iteration.
    goal_bias : float
        Fraction of samples aimed directly at the goal.

    Returns
    -------
    If return_tree=False:
        path : list of (x, y) or None
    If return_tree=True:
        (path, tree_edges)
    """

    root = _RRTNode(start[0], start[1])
    nodes = [root]
    tree_edges = [] if return_tree else None

    for _ in range(max_iterations):

        if rng.random() < goal_bias:
            sx, sy = goal_center
        else:
            sx = rng.uniform(bounds.x_min, bounds.x_max)
            sy = rng.uniform(bounds.y_min, bounds.y_max)

        best = min(nodes, key=lambda n: (n.x - sx) ** 2 + (n.y - sy) ** 2)
        d = math.hypot(sx - best.x, sy - best.y)
        if d < 1e-9:
            continue

        step = min(step_size, d)
        nx = best.x + (sx - best.x) / d * step
        ny = best.y + (sy - best.y) / d * step

        if _line_collides((best.x, best.y), (nx, ny), obstacles, margin):
            continue

        node = _RRTNode(nx, ny, parent=best)
        nodes.append(node)

        if return_tree:
            tree_edges.append(((best.x, best.y), (nx, ny)))

        if (nx - goal_center[0]) ** 2 + (ny - goal_center[1]) ** 2 <= goal_radius ** 2:
            path = []
            n = node
            while n is not None:
                path.append((n.x, n.y))
                n = n.parent
            path = path[::-1]
            if return_tree:
                return path, tree_edges
            return path

    if return_tree:
        return None, tree_edges
    return None


def _rrt_star_plan(start, goal_center, goal_radius, obstacles, bounds, rng,
                   return_tree=False, margin=OBSTACLE_MARGIN,
                   max_iterations=RRT_MAX_ITERATIONS,
                   clearance_weight=0.0, clearance_threshold=0.5,
                   step_size=RRT_STEP_SIZE, goal_bias=RRT_GOAL_BIAS,
                   rewire_radius=RRT_STAR_REWIRE_RADIUS):
    """
    RRT* (optimal RRT) — same interface as _rrt_plan but produces shorter paths.

    RRT* extends basic RRT with:
    - Best parent selection within rewire radius
    - Rewire neighbors through the new node if cheaper

    Parameters / Returns are identical to _rrt_plan, plus:

    clearance_weight : float
        Penalty strength for obstacle proximity. 0 = standard RRT*.
    clearance_threshold : float
        Distance [m] below which the clearance penalty activates.
    """

    root = _RRTNode(start[0], start[1], cost=0.0)
    nodes = [root]
    tree_edges = [] if return_tree else None

    for _ in range(max_iterations):

        if rng.random() < goal_bias:
            sx, sy = goal_center
        else:
            sx = rng.uniform(bounds.x_min, bounds.x_max)
            sy = rng.uniform(bounds.y_min, bounds.y_max)

        best = min(nodes, key=lambda n: (n.x - sx) ** 2 + (n.y - sy) ** 2)
        d = math.hypot(sx - best.x, sy - best.y)
        if d < 1e-9:
            continue

        step = min(step_size, d)
        nx = best.x + (sx - best.x) / d * step
        ny = best.y + (sy - best.y) / d * step

        if _line_collides((best.x, best.y), (nx, ny), obstacles, margin):
            continue

        # Best parent selection within rewire radius
        r_sq = rewire_radius ** 2
        neighbors = [n for n in nodes
                     if (n.x - nx) ** 2 + (n.y - ny) ** 2 <= r_sq]

        edge_dist = math.hypot(nx - best.x, ny - best.y)
        edge_clear = _edge_clearance_cost(
            (best.x, best.y), (nx, ny), obstacles,
            clearance_weight, clearance_threshold)
        best_parent = best
        best_cost = best.cost + edge_dist + edge_clear

        for nb in neighbors:
            nb_dist = math.hypot(nx - nb.x, ny - nb.y)
            nb_clear = _edge_clearance_cost(
                (nb.x, nb.y), (nx, ny), obstacles,
                clearance_weight, clearance_threshold)
            candidate_cost = nb.cost + nb_dist + nb_clear
            if candidate_cost < best_cost:
                if not _line_collides((nb.x, nb.y), (nx, ny), obstacles, margin):
                    best_parent = nb
                    best_cost = candidate_cost

        node = _RRTNode(nx, ny, parent=best_parent, cost=best_cost)
        nodes.append(node)

        if return_tree:
            tree_edges.append(((best_parent.x, best_parent.y), (nx, ny)))

        # Rewire neighbors
        for nb in neighbors:
            if nb is best_parent or nb is root:
                continue
            nb_dist = math.hypot(nx - nb.x, ny - nb.y)
            nb_clear = _edge_clearance_cost(
                (nx, ny), (nb.x, nb.y), obstacles,
                clearance_weight, clearance_threshold)
            new_cost = node.cost + nb_dist + nb_clear
            if new_cost < nb.cost:
                if not _line_collides((nx, ny), (nb.x, nb.y), obstacles, margin):
                    if return_tree:
                        old_edge = ((nb.parent.x, nb.parent.y), (nb.x, nb.y))
                        if old_edge in tree_edges:
                            tree_edges.remove(old_edge)
                        tree_edges.append(((nx, ny), (nb.x, nb.y)))
                    nb.parent = node
                    nb.cost = new_cost

        # Goal check
        if (nx - goal_center[0]) ** 2 + (ny - goal_center[1]) ** 2 <= goal_radius ** 2:
            path = []
            n = node
            while n is not None:
                path.append((n.x, n.y))
                n = n.parent
            path = path[::-1]
            if return_tree:
                return path, tree_edges
            return path

    if return_tree:
        return None, tree_edges
    return None


# ============================================================================
# Main Entry Point
# ============================================================================

def plan_path(
    start: tuple[float, float],
    end: tuple[float, float],
    waypoints: list[Waypoint] | None = None,
    obstacles: list[Obstacle] | None = None,
    bounds: Bounds | None = None,
    state_constraints: StateConstraints | None = None,
    padding: float = 0.0,
    smoothing: float = 1.0,
    seed: int | None = None,
    debug: bool = False,
    rrt_star: bool = False,
    max_iterations: int | None = None,
    clearance_weight: float = 0.0,
    clearance_threshold: float = 0.5,
    step_size: float | None = None,
    goal_bias: float | None = None,
    rewire_radius: float | None = None,
    target_heading: float | None = None,
    heading_strength: float = 1.0,
) -> 'list[tuple[float, float]] | PlanResult':
    """
    Plan a collision-free path from start to end through weighted waypoints.

    Parameters
    ----------
    start : (x, y)
        Start position (exact).
    end : (x, y)
        End position (exact).
    waypoints : list of Waypoint, optional
        Intermediate targets with proximity weights.
    obstacles : list of CircleObstacle / BoxObstacle, optional
    bounds : Bounds, optional
        Workspace limits (converted to wall obstacles).
    state_constraints : StateConstraints, optional
        Per-axis position constraints.
    padding : float
        Robot half-width [m]. Inflates all obstacles by this amount.
    smoothing : float
        Controls spline closeness to polyline. Range [0, 1].
    seed : int, optional
        RNG seed for reproducibility.
    debug : bool
        If True, return PlanResult with all intermediate pipeline stages.
    rrt_star : bool
        If True, use RRT* instead of basic RRT.
    max_iterations : int, optional
        Maximum RRT/RRT* iterations per segment.
    clearance_weight : float
        Obstacle proximity penalty for RRT* cost. 0.0 = standard.
    clearance_threshold : float
        Distance [m] below which clearance penalty activates.
    step_size : float, optional
        Override RRT step size.
    goal_bias : float, optional
        Override RRT goal bias.
    rewire_radius : float, optional
        Override RRT* rewire radius.
    target_heading : float or None
        Desired arrival heading [rad] at the endpoint.  The spline's end
        tangent is clamped to this direction.
    heading_strength : float
        Magnitude of the clamped end tangent.  Larger values create a
        longer approach corridor aligned with the target heading.
        Default 1.0.

    Returns
    -------
    list of (x, y)  —  if debug=False (default)
    PlanResult  —  if debug=True
    """
    # ══════════════════════════════════════════════════════════════════════
    #  Setup
    # ══════════════════════════════════════════════════════════════════════

    if max_iterations is None:
        max_iterations = RRT_STAR_MAX_ITERATIONS if rrt_star else RRT_MAX_ITERATIONS

    _step_size = step_size if step_size is not None else RRT_STEP_SIZE
    _goal_bias = goal_bias if goal_bias is not None else RRT_GOAL_BIAS
    _rewire_radius = rewire_radius if rewire_radius is not None else RRT_STAR_REWIRE_RADIUS

    rng = random.Random(seed)
    waypoints = waypoints or []
    obstacles = list(obstacles) if obstacles else []
    smoothing = max(0.0, min(1.0, smoothing))

    margin = OBSTACLE_MARGIN + max(0.0, padding)

    if bounds is None:
        all_x = [start[0], end[0]] + [wp.x for wp in waypoints]
        all_y = [start[1], end[1]] + [wp.y for wp in waypoints]
        pad = 2.0
        bounds = Bounds(min(all_x) - pad, max(all_x) + pad,
                        min(all_y) - pad, max(all_y) + pad)

    all_obstacles = obstacles + _bounds_to_walls(bounds)

    if state_constraints is not None:
        all_obstacles += _state_constraints_to_walls(state_constraints, bounds)
        eff_bounds = Bounds(
            max(bounds.x_min, state_constraints.x_min) if state_constraints.x_min is not None else bounds.x_min,
            min(bounds.x_max, state_constraints.x_max) if state_constraints.x_max is not None else bounds.x_max,
            max(bounds.y_min, state_constraints.y_min) if state_constraints.y_min is not None else bounds.y_min,
            min(bounds.y_max, state_constraints.y_max) if state_constraints.y_max is not None else bounds.y_max,
        )
    else:
        eff_bounds = bounds

    if _point_collides(start[0], start[1], all_obstacles, margin):
        raise ValueError(f"Start {start} is inside an obstacle or out of bounds")
    if _point_collides(end[0], end[1], all_obstacles, margin):
        raise ValueError(f"End {end} is inside an obstacle or out of bounds")

    if _dist(start, end) < 1e-6 and not waypoints:
        if debug:
            return PlanResult(
                path=[start], start=start, end=end, waypoints=waypoints,
                obstacles=obstacles, bounds=bounds, padding=padding,
                state_constraints=state_constraints,
                rrt_trees=[], rrt_paths=[],
                pruned_paths=[], connection_points_before=[start],
                connection_points_after=[start], polyline=[start],
                spline_curve=[start])
        return [start]

    targets = [start] + [(wp.x, wp.y) for wp in waypoints] + [end]
    zone_radii = ([0.0]
                  + [0.0 if wp.stop else _waypoint_zone_radius(wp.weight) for wp in waypoints]
                  + [0.0])
    zone_centers = list(targets)

    # ══════════════════════════════════════════════════════════════════════
    #  Phase 1: Segment-wise RRT planning
    # ══════════════════════════════════════════════════════════════════════
    connection = start
    rrt_paths_all = []
    rrt_trees_all = []

    for i in range(len(targets) - 1):
        seg_start = connection
        seg_goal = targets[i + 1]

        goal_r = max(zone_radii[i + 1], _step_size)

        if not _line_collides(seg_start, seg_goal, all_obstacles, margin):
            raw_path = [seg_start, seg_goal]
            connection = seg_goal
            if debug:
                rrt_trees_all.append([])
        else:
            _planner = _rrt_star_plan if rrt_star else _rrt_plan
            _rrt_kw = dict(step_size=_step_size, goal_bias=_goal_bias)
            if rrt_star:
                _rrt_kw.update(clearance_weight=clearance_weight,
                               clearance_threshold=clearance_threshold,
                               rewire_radius=_rewire_radius)
            if debug:
                raw_path, tree = _planner(
                    seg_start, seg_goal, goal_r, all_obstacles, eff_bounds, rng,
                    return_tree=True, margin=margin,
                    max_iterations=max_iterations, **_rrt_kw)
                rrt_trees_all.append(tree if tree else [])
            else:
                raw_path = _planner(
                    seg_start, seg_goal, goal_r, all_obstacles, eff_bounds, rng,
                    margin=margin, max_iterations=max_iterations,
                    **_rrt_kw)

            if raw_path is None:
                raise RuntimeError(
                    f"RRT failed for segment {i}: {seg_start} → {seg_goal}. "
                    f"Try increasing max_iterations or check obstacles.")

            if zone_radii[i + 1] == 0.0 and _dist(raw_path[-1], seg_goal) > 1e-6:
                if not _line_collides(raw_path[-1], seg_goal, all_obstacles, margin):
                    raw_path.append(seg_goal)
                    connection = seg_goal
                else:
                    connection = raw_path[-1]
            else:
                connection = raw_path[-1]

        rrt_paths_all.append(raw_path)

    time.sleep(0.005)  # yield GIL for multiprocess wrapper

    # ══════════════════════════════════════════════════════════════════════
    #  Phase 2: Prune each segment's RRT path
    # ══════════════════════════════════════════════════════════════════════
    pruned_all = [_prune_path(seg, all_obstacles, margin) for seg in rrt_paths_all]

    conn_before = [pruned_all[0][0]]
    for seg in pruned_all:
        conn_before.append(seg[-1])
    conn_before[0] = start
    conn_before[-1] = end

    time.sleep(0.005)

    # ══════════════════════════════════════════════════════════════════════
    #  Phase 3: Optimize connection points within waypoint zones
    # ══════════════════════════════════════════════════════════════════════
    conn_after = _optimize_connection_points(
        conn_before, zone_centers, zone_radii, all_obstacles, margin
    )

    time.sleep(0.005)

    # ══════════════════════════════════════════════════════════════════════
    #  Phase 4: Re-plan between optimized connection points
    # ══════════════════════════════════════════════════════════════════════
    full_path = []
    for i in range(len(conn_after) - 1):
        p1, p2 = conn_after[i], conn_after[i + 1]

        if _dist(p1, p2) < 1e-6:
            segment = [p1]
        elif not _line_collides(p1, p2, all_obstacles, margin):
            segment = [p1, p2]
        else:
            _planner = _rrt_star_plan if rrt_star else _rrt_plan
            _rrt_kw = dict(step_size=_step_size, goal_bias=_goal_bias)
            if rrt_star:
                _rrt_kw.update(clearance_weight=clearance_weight,
                               clearance_threshold=clearance_threshold,
                               rewire_radius=_rewire_radius)
            raw = _planner(p1, p2, _step_size, all_obstacles, eff_bounds, rng,
                           margin=margin, max_iterations=max_iterations,
                           **_rrt_kw)
            if raw is None:
                raise RuntimeError(
                    f"Re-plan failed between optimized points {p1} → {p2}")
            segment = _prune_path(raw, all_obstacles, margin)

        if i == 0:
            full_path.extend(segment)
        else:
            full_path.extend(segment[1:])

    deduped = [full_path[0]]
    for p in full_path[1:]:
        if _dist(deduped[-1], p) > 1e-6:
            deduped.append(p)

    if len(deduped) < 2:
        deduped = [start, end]

    polyline = list(deduped)

    time.sleep(0.005)

    # ══════════════════════════════════════════════════════════════════════
    #  Phase 4.5: Smoothing control
    # ══════════════════════════════════════════════════════════════════════
    if smoothing < 1.0 and len(deduped) >= 2:
        ds_knot = 0.01 + smoothing * 0.49
        deduped = _subdivide_polyline(deduped, ds_knot)

    time.sleep(0.005)

    # ══════════════════════════════════════════════════════════════════════
    #  Phase 5: Spline smoothing with collision safety
    # ══════════════════════════════════════════════════════════════════════
    cs_x, cs_y, L, final_pts = _ensure_spline_safety(deduped, all_obstacles,
                                                      margin=margin,
                                                      target_heading=target_heading,
                                                      heading_strength=heading_strength)
    if cs_x is None:
        if debug:
            return PlanResult(
                path=deduped, start=start, end=end, waypoints=waypoints,
                obstacles=obstacles, bounds=bounds, padding=padding,
                state_constraints=state_constraints,
                rrt_trees=rrt_trees_all if debug else [],
                rrt_paths=rrt_paths_all, pruned_paths=pruned_all,
                connection_points_before=conn_before,
                connection_points_after=conn_after,
                polyline=polyline, spline_curve=deduped)
        return deduped

    time.sleep(0.005)

    # ══════════════════════════════════════════════════════════════════════
    #  Phase 6: Uniform Resampling
    # ══════════════════════════════════════════════════════════════════════
    stop_arc_lengths = []
    if waypoints:
        for wp in waypoints:
            if wp.stop:
                n_search = max(int(L / 0.005), 200)
                ts_search = np.linspace(0, L, n_search)
                xs_search = cs_x(ts_search)
                ys_search = cs_y(ts_search)
                dsq_arr = (xs_search - wp.x) ** 2 + (ys_search - wp.y) ** 2
                best_idx = int(np.argmin(dsq_arr))
                stop_arc_lengths.append(float(ts_search[best_idx]))

    final, _ = _uniform_resample(
        cs_x, cs_y, L,
        stop_arc_lengths=stop_arc_lengths if stop_arc_lengths else None,
    )

    if debug:
        spline_curve = _uniform_spline_samples(cs_x, cs_y, L)
        return PlanResult(
            path=final, start=start, end=end, waypoints=waypoints,
            obstacles=obstacles, bounds=bounds, padding=padding,
            state_constraints=state_constraints,
            rrt_trees=rrt_trees_all, rrt_paths=rrt_paths_all,
            pruned_paths=pruned_all,
            connection_points_before=conn_before,
            connection_points_after=conn_after,
            polyline=polyline, spline_curve=spline_curve)

    return final


# ============================================================================
# Multiprocess Wrapper
# ============================================================================

from concurrent.futures import ProcessPoolExecutor, TimeoutError as _FuturesTimeoutError

_pool: ProcessPoolExecutor | None = None


def _get_pool() -> ProcessPoolExecutor:
    """Get or create the persistent single-worker process pool."""
    global _pool
    if _pool is None or _pool._broken:
        _pool = ProcessPoolExecutor(max_workers=1)
    return _pool


def plan_path_mp(timeout: float = 10.0, **kwargs):
    """Run plan_path in a separate process to avoid blocking the GIL.

    Uses a persistent worker process — the first call pays the fork cost,
    subsequent calls reuse the warm worker with numpy/scipy already loaded.

    Parameters
    ----------
    timeout : float
        Maximum seconds to wait for the planner. Default 10.0.
    **kwargs
        Forwarded to plan_path().

    Returns
    -------
    list of (x, y)
        The planned path (same as plan_path).

    Raises
    ------
    TimeoutError
        If planning exceeds the timeout.
    """
    global _pool
    pool = _get_pool()
    future = pool.submit(plan_path, **kwargs)
    try:
        return future.result(timeout=timeout)
    except _FuturesTimeoutError:
        pool.shutdown(wait=False, cancel_futures=True)
        _pool = None
        raise TimeoutError(f"Motion planning exceeded {timeout:.1f}s timeout")


# ============================================================================
# Visualization — RRT Tree Detail
# ============================================================================

def plot_rrt(result: PlanResult, figsize=(14, 6)):
    """
    2-panel plot showing:
        Left:  Full RRT tree exploration with solution path
        Right: Final path only (after full pipeline)

    Parameters
    ----------
    result : PlanResult from plan_path(..., debug=True)
    figsize : figure size

    Returns
    -------
    (fig, axes)
    """
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    fig, axes = plt.subplots(1, 2, figsize=figsize)

    # ── Left panel: RRT Tree + Solution Path ──
    ax = axes[0]
    _draw_background(ax, result, 'RRT Tree & Solution Path')
    n_seg = len(result.rrt_paths)

    total_nodes = 0
    for seg_idx in range(n_seg):
        color = _SEGMENT_COLORS[seg_idx % len(_SEGMENT_COLORS)]

        if seg_idx < len(result.rrt_trees) and result.rrt_trees[seg_idx]:
            edges = result.rrt_trees[seg_idx]
            segments = [[(p1[0], p1[1]), (p2[0], p2[1])] for p1, p2 in edges]
            lc = LineCollection(segments, colors=color, alpha=0.45,
                                linewidths=0.7, zorder=2)
            ax.add_collection(lc)
            node_set = set()
            for (x1, y1), (x2, y2) in edges:
                node_set.add((x1, y1))
                node_set.add((x2, y2))
            node_xs = [n[0] for n in node_set]
            node_ys = [n[1] for n in node_set]
            ax.scatter(node_xs, node_ys, c=color, s=6, alpha=0.6,
                       zorder=3, edgecolors='none')
            total_nodes += len(node_set)

        path = result.rrt_paths[seg_idx]
        if len(path) >= 2:
            xs = [p[0] for p in path]
            ys = [p[1] for p in path]
            ax.plot(xs, ys, '-', color=color, lw=2.5, alpha=0.9, zorder=5,
                    label=f'Seg {seg_idx + 1} ({len(path)} nodes)')
            ax.scatter(xs, ys, c=color, s=15, zorder=6, edgecolors='white',
                       linewidths=0.4)
            ax.plot(xs[0], ys[0], 'o', color=color, markersize=6, zorder=7)
            ax.plot(xs[-1], ys[-1], 'D', color=color, markersize=6, zorder=7)

    total_edges = sum(len(t) for t in result.rrt_trees)
    ax.text(
        0.02, 0.02,
        f'Tree nodes: {total_nodes}\n'
        f'Tree edges: {total_edges}\n'
        f'Path nodes: {len(result.path)}',
        transform=ax.transAxes, fontsize=8, verticalalignment='bottom',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.plot([], [], 's', color='#00b894', markersize=8, label='Start')
    ax.plot([], [], '*', color='#d63031', markersize=10, label='End')
    ax.legend(loc='upper right', fontsize=7)

    # ── Right panel: Final Path ──
    ax = axes[1]
    _draw_background(ax, result, 'Final Path')

    if len(result.path) >= 2:
        xs = [p[0] for p in result.path]
        ys = [p[1] for p in result.path]
        ax.plot(xs, ys, '-', color='#2d3436', lw=2, zorder=3, label='Path')
        ax.scatter(xs, ys, c='#636e72', s=6, zorder=4, label='Points')

        spacings = [_dist(result.path[k], result.path[k + 1])
                     for k in range(len(result.path) - 1)]
        total_len = sum(spacings)
        ax.text(
            0.02, 0.02,
            f'{len(result.path)} points\n'
            f'Length: {total_len:.2f} m',
            transform=ax.transAxes, fontsize=8, verticalalignment='bottom',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.plot([], [], 's', color='#00b894', markersize=8, label='Start')
    ax.plot([], [], '*', color='#d63031', markersize=10, label='End')
    ax.legend(loc='upper right', fontsize=7)

    fig.suptitle('RRT Motion Planning', fontsize=13, fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()
    return fig, axes


# ============================================================================
# Visualization — All Pipeline Stages
# ============================================================================

def plot_stages(result: PlanResult, figsize=(15, 13)):
    """
    4-panel plot showing all pipeline stages:
        1. Problem setup (input)
        2. RRT exploration + raw solution paths
        3. Pruned paths + optimized waypoints
        4. Final smoothed path with adaptive sampling

    Parameters
    ----------
    result : PlanResult from plan_path(..., debug=True)
    figsize : figure size

    Returns
    -------
    (fig, axes) — 2x2 array of axes
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.collections import LineCollection

    fig, axes = plt.subplots(2, 2, figsize=figsize)

    # ── Panel 1: Problem Setup ──
    ax = axes[0, 0]
    _draw_background(ax, result, '1. Problem Setup')
    for idx, wp in enumerate(result.waypoints):
        r = _waypoint_zone_radius(wp.weight)
        ax.annotate(
            f'WP{idx + 1}: w={wp.weight:.2f}, r={r:.2f}m',
            (wp.x, wp.y), textcoords="offset points", xytext=(8, 8),
            fontsize=7, color='#0984e3')
    ax.plot([], [], 's', color='#00b894', markersize=8, label='Start')
    ax.plot([], [], '*', color='#d63031', markersize=10, label='End')
    ax.plot([], [], 'o', color='#0984e3', markersize=5, label='Waypoint')
    ax.legend(loc='upper right', fontsize=7)

    # ── Panel 2: RRT Exploration ──
    ax = axes[0, 1]
    _draw_background(ax, result, '2. RRT Exploration')
    n_seg = len(result.rrt_paths)
    for seg_idx in range(n_seg):
        color = _SEGMENT_COLORS[seg_idx % len(_SEGMENT_COLORS)]

        if seg_idx < len(result.rrt_trees) and result.rrt_trees[seg_idx]:
            edges = result.rrt_trees[seg_idx]
            segments = [[(p1[0], p1[1]), (p2[0], p2[1])] for p1, p2 in edges]
            lc = LineCollection(segments, colors=color, alpha=0.45,
                                linewidths=0.7, zorder=2)
            ax.add_collection(lc)
            node_set = set()
            for (x1, y1), (x2, y2) in edges:
                node_set.add((x1, y1))
                node_set.add((x2, y2))
            node_xs = [n[0] for n in node_set]
            node_ys = [n[1] for n in node_set]
            ax.scatter(node_xs, node_ys, c=color, s=6, alpha=0.6,
                       zorder=3, edgecolors='none')

        path = result.rrt_paths[seg_idx]
        if len(path) >= 2:
            xs = [p[0] for p in path]
            ys = [p[1] for p in path]
            ax.plot(xs, ys, '-', color=color, lw=2.5, alpha=0.9, zorder=5,
                    label=f'Seg {seg_idx + 1} ({len(path)} nodes)')
            ax.scatter(xs, ys, c=color, s=15, zorder=6, edgecolors='white',
                       linewidths=0.4)
            ax.plot(xs[0], ys[0], 'o', color=color, markersize=6, zorder=7)
            ax.plot(xs[-1], ys[-1], 'D', color=color, markersize=6, zorder=7)

    ax.legend(loc='upper right', fontsize=6)

    # ── Panel 3: Pruned + Optimized ──
    ax = axes[1, 0]
    _draw_background(ax, result, '3. Pruned + Optimized')

    for seg_idx, seg_path in enumerate(result.pruned_paths):
        color = _SEGMENT_COLORS[seg_idx % len(_SEGMENT_COLORS)]
        xs = [p[0] for p in seg_path]
        ys = [p[1] for p in seg_path]
        ax.plot(xs, ys, 'o--', color=color, lw=1, markersize=3, alpha=0.5,
                label=f'Pruned {seg_idx + 1}' if seg_idx < 4 else None)

    cb = result.connection_points_before
    ca = result.connection_points_after
    for i in range(1, len(cb) - 1):
        bx, by = cb[i]
        ax_, ay_ = ca[i]
        ax.plot(bx, by, 'o', color='#636e72', markersize=7,
                markerfacecolor='none', markeredgewidth=1.5, zorder=7)
        ax.plot(ax_, ay_, 'o', color='#2d3436', markersize=5, zorder=8)
        ddx, ddy = ax_ - bx, ay_ - by
        if math.hypot(ddx, ddy) > 0.01:
            ax.annotate(
                '', xy=(ax_, ay_), xytext=(bx, by),
                arrowprops=dict(arrowstyle='->', color='#636e72', lw=1.2),
                zorder=7)

    if len(result.polyline) >= 2:
        xs = [p[0] for p in result.polyline]
        ys = [p[1] for p in result.polyline]
        ax.plot(xs, ys, '.-', color='#2d3436', lw=2, markersize=5,
                zorder=5, label='Optimized polyline')

    ax.plot([], [], 'o', color='#636e72', markerfacecolor='none',
            markeredgewidth=1.5, markersize=6, label='Before opt.')
    ax.plot([], [], 'o', color='#2d3436', markersize=5, label='After opt.')
    ax.legend(loc='upper right', fontsize=6)

    # ── Panel 4: Final Path with Adaptive Sampling ──
    ax = axes[1, 1]
    _draw_background(ax, result, '4. Final Path (adaptive sampling)')

    if result.spline_curve and len(result.spline_curve) >= 2:
        xs = [p[0] for p in result.spline_curve]
        ys = [p[1] for p in result.spline_curve]
        ax.plot(xs, ys, '-', color='#b2bec3', lw=1, zorder=2, label='Spline')

    if len(result.path) >= 2:
        xs = [p[0] for p in result.path]
        ys = [p[1] for p in result.path]
        spacings = [_dist(result.path[k], result.path[k + 1])
                     for k in range(len(result.path) - 1)]

        ax.plot(xs, ys, '-', color='#2d3436', lw=1.2, zorder=3)

        sp_colors = spacings + [spacings[-1]]
        sc = ax.scatter(xs, ys, c=sp_colors, cmap='coolwarm_r', s=8,
                        zorder=4, vmin=SAMPLE_DS_MIN, vmax=SAMPLE_DS_MAX,
                        edgecolors='none')
        cb = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.02)
        cb.set_label('Sample spacing [m]', fontsize=8)
        cb.ax.tick_params(labelsize=7)

        total_len = sum(spacings)
        ax.text(
            0.02, 0.02,
            f'{len(result.path)} samples\n'
            f'Length: {total_len:.2f} m\n'
            f'Spacing: {min(spacings):.3f}–{max(spacings):.3f} m',
            transform=ax.transAxes, fontsize=7, verticalalignment='bottom',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.legend(loc='upper right', fontsize=7)

    fig.suptitle('Motion Planning Pipeline', fontsize=13, fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()
    return fig, axes
