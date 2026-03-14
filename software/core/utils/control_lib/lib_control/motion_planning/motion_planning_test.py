"""
RRT* with Obstacle Clearance Cost — Comparison Test.

Demonstrates the effect of adding a clearance penalty to the RRT* cost
function.  Standard RRT* minimizes path length only; the clearance-aware
variant adds a cost term that penalizes proximity to obstacle surfaces.
This naturally pushes the path toward corridor midlines and away from
tight wall-hugging trajectories.

The clearance cost for each tree edge is computed by sampling points along
the edge and applying a quadratic penalty when the distance to the nearest
obstacle surface falls below a configurable threshold:

    penalty(d) = ((threshold - d) / threshold)^2     for d < threshold
    penalty(d) = 0                                    for d >= threshold

The total edge cost becomes:

    cost(edge) = euclidean_length + weight * avg_penalty * euclidean_length

Higher weight = stronger midline preference (at the expense of longer paths).

Usage:
    python -m core.utils.control_lib.lib_control.motion_planning.motion_planning_test

Or run directly from the motion_planning directory:
    python motion_planning_test.py
"""

import math
import time

from core.utils.control_lib.lib_control.motion_planning.common import (
    Bounds, BoxObstacle, CircleObstacle, PlanResult, Waypoint,
    _dist, _draw_background, _draw_box_patch,
    _line_collides, _rotate_to_local,
    OBSTACLE_MARGIN,
)
from core.utils.control_lib.lib_control.motion_planning.rrt import (
    _RRTNode, RRT_GOAL_BIAS, RRT_STAR_MAX_ITERATIONS,
    RRT_STAR_REWIRE_RADIUS, RRT_STEP_SIZE,
    plan_path,
)
import sys

# Get a reference to the module object that defines plan_path, so we can
# monkey-patch _rrt_star_plan at the module level.
_mp = sys.modules[plan_path.__module__]


# ============================================================================
# Clearance Utilities
# ============================================================================

def _min_clearance(px, py, obstacles):
    """Minimum distance from point (px, py) to the nearest obstacle surface.

    Returns the shortest Euclidean distance to any obstacle boundary.
    Positive = outside the obstacle, negative = inside (should not happen
    since collision checking prevents placement inside obstacles).

    Handles both CircleObstacle and BoxObstacle (with rotation).
    """
    min_d = float('inf')
    for obs in obstacles:
        if isinstance(obs, CircleObstacle):
            d = math.hypot(px - obs.cx, py - obs.cy) - obs.radius
        elif isinstance(obs, BoxObstacle):
            cos_psi = math.cos(obs.psi)
            sin_psi = math.sin(obs.psi)
            lx, ly = _rotate_to_local(px, py, obs.cx, obs.cy, cos_psi, sin_psi)
            # Signed distance to axis-aligned box in local frame
            dx = abs(lx) - obs.width / 2
            dy = abs(ly) - obs.height / 2
            if dx <= 0 and dy <= 0:
                # Inside the box — distance to nearest edge (negative)
                d = max(dx, dy)
            else:
                # Outside — Euclidean distance to nearest corner/edge
                d = math.hypot(max(dx, 0.0), max(dy, 0.0))
        else:
            continue
        min_d = min(min_d, d)
    return min_d


def _edge_clearance_cost(p1, p2, obstacles, weight, threshold):
    """Additional clearance-based cost for a tree edge.

    Samples points along the edge p1->p2 and penalizes proximity to
    obstacles.  Points closer than `threshold` to any obstacle surface
    receive a quadratic penalty that increases as clearance decreases.

    Parameters
    ----------
    p1, p2 : (x, y)
        Edge endpoints.
    obstacles : list[Obstacle]
        All obstacles including wall obstacles.
    weight : float
        Penalty strength.  Higher = stronger midline preference.
    threshold : float
        Distance [m] below which the penalty activates.

    Returns
    -------
    float
        Additional cost to add to the edge's Euclidean length.
    """
    edge_len = _dist(p1, p2)
    if edge_len < 1e-9 or weight <= 0:
        return 0.0

    # Sample 5 evenly spaced points along the edge (including endpoints)
    n_samples = 5
    total_penalty = 0.0
    for i in range(n_samples + 1):
        t = i / n_samples
        px = p1[0] + t * (p2[0] - p1[0])
        py = p1[1] + t * (p2[1] - p1[1])
        clearance = _min_clearance(px, py, obstacles)
        if clearance < threshold:
            normalized = (threshold - clearance) / threshold  # 0..1
            total_penalty += normalized * normalized          # quadratic
    avg_penalty = total_penalty / (n_samples + 1)

    # Scale by edge length so longer edges near walls accumulate more cost
    return weight * avg_penalty * edge_len


# ============================================================================
# Clearance-Aware RRT* Planner
# ============================================================================

def make_clearance_rrt_star(clearance_weight=3.0, clearance_threshold=0.5):
    """Factory: return an RRT* planner with clearance-based cost.

    The returned function has the same signature as ``_rrt_star_plan`` and
    can be used as a drop-in replacement.  The only difference is that the
    cost of each tree edge includes a clearance penalty term in addition
    to the Euclidean distance.

    Parameters
    ----------
    clearance_weight : float
        Penalty strength.  Typical range 1..10.
        0 = standard RRT* (distance only).
        5 = strong midline preference.
    clearance_threshold : float
        Distance [m] below which the penalty activates.  Points farther
        than this from all obstacles incur zero penalty.
    """

    def _rrt_star_clearance(start, goal_center, goal_radius, obstacles,
                            bounds, rng, return_tree=False,
                            margin=OBSTACLE_MARGIN,
                            max_iterations=RRT_STAR_MAX_ITERATIONS):

        root = _RRTNode(start[0], start[1], cost=0.0)
        nodes = [root]
        tree_edges = [] if return_tree else None

        for _ in range(max_iterations):
            # ── Sample ──
            if rng.random() < RRT_GOAL_BIAS:
                sx, sy = goal_center
            else:
                sx = rng.uniform(bounds.x_min, bounds.x_max)
                sy = rng.uniform(bounds.y_min, bounds.y_max)

            # ── Nearest ──
            best = min(nodes,
                       key=lambda n: (n.x - sx) ** 2 + (n.y - sy) ** 2)
            d = math.hypot(sx - best.x, sy - best.y)
            if d < 1e-9:
                continue

            # ── Steer ──
            step = min(RRT_STEP_SIZE, d)
            nx = best.x + (sx - best.x) / d * step
            ny = best.y + (sy - best.y) / d * step

            # ── Collision check ──
            if _line_collides((best.x, best.y), (nx, ny), obstacles, margin):
                continue

            # ── Best parent with clearance cost ──
            r_sq = RRT_STAR_REWIRE_RADIUS ** 2
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
                    if not _line_collides((nb.x, nb.y), (nx, ny),
                                         obstacles, margin):
                        best_parent = nb
                        best_cost = candidate_cost

            # ── Add node ──
            node = _RRTNode(nx, ny, parent=best_parent, cost=best_cost)
            nodes.append(node)

            if return_tree:
                tree_edges.append(
                    ((best_parent.x, best_parent.y), (nx, ny)))

            # ── Rewire neighbors with clearance cost ──
            for nb in neighbors:
                if nb is best_parent or nb is root:
                    continue
                nb_dist = math.hypot(nx - nb.x, ny - nb.y)
                nb_clear = _edge_clearance_cost(
                    (nx, ny), (nb.x, nb.y), obstacles,
                    clearance_weight, clearance_threshold)
                new_cost = node.cost + nb_dist + nb_clear
                if new_cost < nb.cost:
                    if not _line_collides((nx, ny), (nb.x, nb.y),
                                         obstacles, margin):
                        if return_tree:
                            old_edge = ((nb.parent.x, nb.parent.y),
                                        (nb.x, nb.y))
                            if old_edge in tree_edges:
                                tree_edges.remove(old_edge)
                            tree_edges.append(((nx, ny), (nb.x, nb.y)))
                        nb.parent = node
                        nb.cost = new_cost

            # ── Goal check ──
            if ((nx - goal_center[0]) ** 2
                    + (ny - goal_center[1]) ** 2 <= goal_radius ** 2):
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

    return _rrt_star_clearance


# ============================================================================
# Helper: plan with clearance cost via monkey-patching
# ============================================================================

def plan_path_clearance(clearance_weight=3.0, clearance_threshold=0.5,
                        **kwargs):
    """Run plan_path with clearance-aware RRT*.

    Temporarily swaps the module-level ``_rrt_star_plan`` with a
    clearance-aware version, runs ``plan_path(rrt_star=True, ...)``,
    then restores the original.

    Parameters
    ----------
    clearance_weight : float
        Penalty strength (0 = standard, 5 = strong midline preference).
    clearance_threshold : float
        Distance [m] below which the penalty activates.
    **kwargs
        All remaining arguments forwarded to ``plan_path``.
    """
    original = _mp._rrt_star_plan
    _mp._rrt_star_plan = make_clearance_rrt_star(clearance_weight,
                                                  clearance_threshold)
    try:
        return plan_path(rrt_star=True, **kwargs)
    finally:
        _mp._rrt_star_plan = original


# ============================================================================
# Visualization helpers
# ============================================================================

def _plot_clearance_field(ax, obstacles, bounds, threshold, fig):
    """Draw a clearance heat map on the given axes."""
    import numpy as np
    import matplotlib.patches as mpatches

    ax.set_aspect('equal')
    ax.grid(True, alpha=0.2)

    nx_grid, ny_grid = 200, 150
    xs = np.linspace(bounds.x_min, bounds.x_max, nx_grid)
    ys = np.linspace(bounds.y_min, bounds.y_max, ny_grid)
    clearance_grid = np.zeros((ny_grid, nx_grid))
    for iy in range(ny_grid):
        for ix in range(nx_grid):
            clearance_grid[iy, ix] = _min_clearance(xs[ix], ys[iy], obstacles)
    clearance_grid = np.maximum(clearance_grid, 0)

    im = ax.imshow(clearance_grid,
                   extent=[bounds.x_min, bounds.x_max,
                           bounds.y_min, bounds.y_max],
                   origin='lower', cmap='RdYlGn', vmin=0, vmax=1.2,
                   aspect='equal', zorder=1)
    cb = fig.colorbar(im, ax=ax, shrink=0.7, pad=0.02)
    cb.set_label('Clearance [m]', fontsize=8)
    cb.ax.tick_params(labelsize=7)

    # Obstacles drawn on top
    for obs in obstacles:
        if isinstance(obs, CircleObstacle):
            p = mpatches.Circle((obs.cx, obs.cy), obs.radius,
                                facecolor='#2d3436', edgecolor='#2d3436',
                                alpha=0.8, linewidth=1, zorder=3)
            ax.add_patch(p)
        elif isinstance(obs, BoxObstacle):
            r = _draw_box_patch(ax, obs, facecolor='#2d3436',
                                edgecolor='#2d3436', alpha=0.8)
            r.set_zorder(3)

    # Threshold contour
    ax.contour(xs, ys, clearance_grid, levels=[threshold],
               colors='#e17055', linewidths=1.5, linestyles='--', zorder=4)

    ax.set_xlim(bounds.x_min - 0.1, bounds.x_max + 0.1)
    ax.set_ylim(bounds.y_min - 0.1, bounds.y_max + 0.1)
    ax.set_xlabel('x [m]')
    ax.set_ylabel('y [m]')
    return clearance_grid


def _plot_path_panel(ax, result, obstacles, threshold, title):
    """Draw a single path panel with tree, path, and clearance stats."""
    import matplotlib.patches as mpatches
    from matplotlib.collections import LineCollection

    _draw_background(ax, result, title)

    # Clearance threshold zones around obstacles
    for obs in obstacles:
        if isinstance(obs, CircleObstacle):
            zone = mpatches.Circle(
                (obs.cx, obs.cy), obs.radius + threshold,
                facecolor='#ffeaa7', edgecolor='#fdcb6e',
                alpha=0.12, linewidth=1, linestyle=':', zorder=1)
            ax.add_patch(zone)
        elif isinstance(obs, BoxObstacle):
            _draw_box_patch(ax, obs, facecolor='#ffeaa7',
                            edgecolor='#fdcb6e', alpha=0.12,
                            linewidth=1, inflate=threshold)

    # RRT tree (faint)
    for seg_idx in range(len(result.rrt_trees)):
        if result.rrt_trees[seg_idx]:
            edges = result.rrt_trees[seg_idx]
            segments = [[(p1[0], p1[1]), (p2[0], p2[1])]
                        for p1, p2 in edges]
            lc = LineCollection(segments, colors='#b2bec3', alpha=0.2,
                                linewidths=0.4, zorder=2)
            ax.add_collection(lc)

    # Final path
    path = result.path
    if len(path) >= 2:
        pxs = [p[0] for p in path]
        pys = [p[1] for p in path]
        ax.plot(pxs, pys, '-', color='#2d3436', lw=2.5, zorder=5,
                label='Path')
        ax.scatter(pxs, pys, c='#636e72', s=4, zorder=6)

    # Stats
    spacings = [_dist(path[i], path[i + 1]) for i in range(len(path) - 1)]
    path_len = sum(spacings) if spacings else 0
    clearances = [_min_clearance(p[0], p[1], obstacles) for p in path]
    min_c = min(clearances)
    avg_c = sum(clearances) / len(clearances)
    ax.text(
        0.02, 0.02,
        f'Length: {path_len:.2f} m\n'
        f'Min clearance: {min_c:.2f} m\n'
        f'Avg clearance: {avg_c:.2f} m',
        transform=ax.transAxes, fontsize=8, verticalalignment='bottom',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.85),
        zorder=10)
    ax.legend(loc='upper right', fontsize=8)
    return path_len, min_c, avg_c


def _run_comparison(name, obstacles, bounds, start, end, seed,
                    clearance_weight, clearance_threshold,
                    max_iterations=30000):
    """Run standard vs clearance RRT*, print stats, and plot 1x3 figure."""
    import matplotlib.pyplot as plt

    print("=" * 60)
    print(f"  {name}")
    print("=" * 60)

    # ── Plan 1: Standard RRT* ──
    t0 = time.perf_counter()
    result_std = plan_path(
        start=start, end=end, obstacles=obstacles, bounds=bounds,
        rrt_star=True, seed=seed, debug=True,
        max_iterations=max_iterations,
    )
    t_std = time.perf_counter() - t0

    # ── Plan 2: Clearance-aware RRT* ──
    t0 = time.perf_counter()
    result_clr = plan_path_clearance(
        clearance_weight=clearance_weight,
        clearance_threshold=clearance_threshold,
        start=start, end=end, obstacles=obstacles, bounds=bounds,
        seed=seed, debug=True, max_iterations=max_iterations,
    )
    t_clr = time.perf_counter() - t0

    # ── Statistics ──
    for label, result, t_plan in [
        ("Standard RRT*", result_std, t_std),
        (f"Clearance RRT* (w={clearance_weight}, "
         f"thr={clearance_threshold})", result_clr, t_clr),
    ]:
        path = result.path
        spacings = [_dist(path[i], path[i + 1])
                     for i in range(len(path) - 1)]
        path_len = sum(spacings) if spacings else 0
        clearances = [_min_clearance(p[0], p[1], obstacles) for p in path]
        print(f"  {label}:")
        print(f"    Path length:   {path_len:.3f} m")
        print(f"    Min clearance: {min(clearances):.3f} m")
        print(f"    Avg clearance: {sum(clearances) / len(clearances):.3f} m")
        print(f"    Time:          {t_plan:.3f} s")

    # ── Visualization: 1x3 ──
    fig, axes = plt.subplots(1, 3, figsize=(21, 6))

    # Panel 0: clearance field
    ax = axes[0]
    ax.set_title('Clearance Field', fontsize=10, fontweight='bold')
    _plot_clearance_field(ax, obstacles, bounds, clearance_threshold, fig)
    ax.plot(start[0], start[1], 's', color='#00b894', markersize=10, zorder=6)
    ax.plot(end[0], end[1], '*', color='#d63031', markersize=14, zorder=6)

    # Panel 1: standard RRT*
    _plot_path_panel(axes[1], result_std, obstacles, clearance_threshold,
                     'Standard RRT* (shortest distance)')

    # Panel 2: clearance RRT*
    _plot_path_panel(axes[2], result_clr, obstacles, clearance_threshold,
                     f'Clearance RRT* (w={clearance_weight},'
                     f' thr={clearance_threshold} m)')

    fig.suptitle(name, fontsize=14, fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()
    return fig


# ============================================================================
# Examples
# ============================================================================

if __name__ == '__main__':

    # ── Scenario 1: Thick wall with narrow gap ──
    # A thick vertical wall (0.8 m deep) blocks the straight line.
    # The path must travel through a 0.6 m gap (midline y=1.5).
    # Standard RRT* clips the gap edge; clearance RRT* centers the path.
    _run_comparison(
        name='Scenario 1: Thick wall with narrow gap',
        obstacles=[
            # Thick wall at x=2.0, gap from y=1.2 to y=1.8 (0.6 m)
            BoxObstacle(2.0, 0.6, 0.8, 1.2),    # lower: y=0.0..1.2
            BoxObstacle(2.0, 2.4, 0.8, 1.2),    # upper: y=1.8..3.0
        ],
        bounds=Bounds(0, 4, 0, 3),
        start=(0.5, 0.5),
        end=(3.5, 0.5),
        seed=42,
        clearance_weight=10.0,
        clearance_threshold=0.4,
        max_iterations=40000,
    )

    # ── Scenario 2: Corridor with obstacle ──
    # Horizontal corridor (y=0.2..2.8) with a circular obstacle blocking
    # the center.  The path must navigate around it within the corridor.
    # Clearance RRT* maintains more distance from the obstacle AND walls.
    _run_comparison(
        name='Scenario 2: Corridor with obstacle',
        obstacles=[
            BoxObstacle(2.0, 0.1, 3.0, 0.2),    # lower wall (top y=0.2)
            BoxObstacle(2.0, 2.9, 3.0, 0.2),    # upper wall (bot y=2.8)
            CircleObstacle(2.0, 1.5, 0.4),       # obstacle blocking center
        ],
        bounds=Bounds(0, 4, 0, 3),
        start=(0.3, 1.5),
        end=(3.7, 1.5),
        seed=21,
        clearance_weight=8.0,
        clearance_threshold=0.6,
        max_iterations=40000,
    )
