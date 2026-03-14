"""
Motion Planning Examples.

Run directly:
    python -m core.utils.control_lib.lib_control.motion_planning.examples

Lists all available examples and lets you pick which one to run.
"""

import math
import time

from core.utils.control_lib.lib_control.motion_planning.common import (
    SAMPLE_DS_MAX, SAMPLE_DS_MIN, _SEGMENT_COLORS, Bounds, BoxObstacle,
    CircleObstacle, PlanResult, StateConstraints, Waypoint, _dist,
    _draw_background, _waypoint_zone_radius,
)
from core.utils.control_lib.lib_control.motion_planning.rrt import (
    plan_path, plot_stages,
)

BOUNDS = Bounds(0, 3, 0, 3)


def _total_turning_angle(path) -> float:
    """Sum of absolute angular deflections along a path [rad].

    For each consecutive triplet (A, B, C), compute the angle between
    vectors BA and BC.  A perfectly straight path returns 0; every wiggle
    adds to the total.
    """
    total = 0.0
    for i in range(1, len(path) - 1):
        ax, ay = path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]
        bx, by = path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]
        # atan2 of the cross/dot product gives the signed angle; abs for total
        cross = ax * by - ay * bx
        dot = ax * bx + ay * by
        total += abs(math.atan2(cross, dot))
    return total


def _print_result(result: PlanResult, name: str):
    """Print summary statistics for a planning result."""
    print(f"\n{'─' * 50}")
    print(f"  {name}")
    print(f"{'─' * 50}")
    spacings = [_dist(result.path[i], result.path[i + 1])
                for i in range(len(result.path) - 1)]
    total_len = sum(spacings) if spacings else 0
    turning = _total_turning_angle(result.path)
    print(f"  Samples: {len(result.path)}")
    print(f"  Length:  {total_len:.3f} m")
    print(f"  Turning: {math.degrees(turning):.1f} deg ({turning:.2f} rad)")
    if spacings:
        print(f"  Spacing: {min(spacings):.4f}–{max(spacings):.4f} m "
              f"(mean {sum(spacings) / len(spacings):.4f})")
    for i, seg in enumerate(result.rrt_paths):
        tree_n = len(result.rrt_trees[i]) if i < len(result.rrt_trees) else 0
        pruned_n = len(result.pruned_paths[i])
        straight = " (straight)" if tree_n == 0 else ""
        print(f"  Seg {i + 1}: {len(seg)} RRT nodes, "
              f"{tree_n} tree edges, {pruned_n} pruned{straight}")


def _plot_rrt_comparison(r_rrt: PlanResult, r_star: PlanResult, title: str):
    """Side-by-side 4x2 figure comparing RRT (left) vs RRT* (right)."""
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    fig, axes = plt.subplots(4, 2, figsize=(14, 22))
    labels = ['RRT', 'RRT*']
    results = [r_rrt, r_star]

    for col, (label, result) in enumerate(zip(labels, results)):

        # Row 1: Problem Setup
        ax = axes[0, col]
        _draw_background(ax, result, f'{label} — 1. Problem Setup')
        ax.plot([], [], 's', color='#00b894', markersize=8, label='Start')
        ax.plot([], [], '*', color='#d63031', markersize=10, label='End')
        if result.waypoints:
            ax.plot([], [], 'o', color='#0984e3', markersize=5, label='Waypoint')
        ax.legend(loc='upper right', fontsize=7)

        # Row 2: Tree Exploration
        ax = axes[1, col]
        _draw_background(ax, result, f'{label} — 2. Tree Exploration')
        total_nodes = 0
        for seg_idx in range(len(result.rrt_paths)):
            color = _SEGMENT_COLORS[seg_idx % len(_SEGMENT_COLORS)]
            if seg_idx < len(result.rrt_trees) and result.rrt_trees[seg_idx]:
                edges = result.rrt_trees[seg_idx]
                segments = [[(p1[0], p1[1]), (p2[0], p2[1])]
                            for p1, p2 in edges]
                lc = LineCollection(segments, colors=color, alpha=0.45,
                                    linewidths=0.7, zorder=2)
                ax.add_collection(lc)
                node_set = set()
                for (x1, y1), (x2, y2) in edges:
                    node_set.add((x1, y1))
                    node_set.add((x2, y2))
                ax.scatter([n[0] for n in node_set], [n[1] for n in node_set],
                           c=color, s=6, alpha=0.6, zorder=3, edgecolors='none')
                total_nodes += len(node_set)
            path = result.rrt_paths[seg_idx]
            if len(path) >= 2:
                xs = [p[0] for p in path]
                ys = [p[1] for p in path]
                ax.plot(xs, ys, '-', color=color, lw=2.5, alpha=0.9, zorder=5,
                        label=f'Seg {seg_idx + 1} ({len(path)} nodes)')
                ax.scatter(xs, ys, c=color, s=15, zorder=6, edgecolors='white',
                           linewidths=0.4)
        total_edges = sum(len(t) for t in result.rrt_trees)
        ax.text(0.02, 0.02,
                f'Nodes: {total_nodes}  Edges: {total_edges}',
                transform=ax.transAxes, fontsize=7, verticalalignment='bottom',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
        ax.legend(loc='upper right', fontsize=6)

        # Row 3: Pruned + Optimized
        ax = axes[2, col]
        _draw_background(ax, result, f'{label} — 3. Pruned + Optimized')
        for seg_idx, seg_path in enumerate(result.pruned_paths):
            color = _SEGMENT_COLORS[seg_idx % len(_SEGMENT_COLORS)]
            xs = [p[0] for p in seg_path]
            ys = [p[1] for p in seg_path]
            ax.plot(xs, ys, 'o--', color=color, lw=1, markersize=3, alpha=0.5)
        if len(result.polyline) >= 2:
            xs = [p[0] for p in result.polyline]
            ys = [p[1] for p in result.polyline]
            ax.plot(xs, ys, '.-', color='#2d3436', lw=2, markersize=5,
                    zorder=5, label='Optimized polyline')
        ax.legend(loc='upper right', fontsize=6)

        # Row 4: Final Path
        ax = axes[3, col]
        _draw_background(ax, result, f'{label} — 4. Final Path')
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
            ax.scatter(xs, ys, c=sp_colors, cmap='coolwarm_r', s=8,
                       zorder=4, vmin=SAMPLE_DS_MIN, vmax=SAMPLE_DS_MAX,
                       edgecolors='none')
            total_len = sum(spacings)
            ax.text(0.02, 0.02,
                    f'{len(result.path)} samples\nLength: {total_len:.2f} m',
                    transform=ax.transAxes, fontsize=7, verticalalignment='bottom',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
        ax.legend(loc='upper right', fontsize=7)

    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.995)
    plt.tight_layout(rect=[0, 0, 1, 0.99])
    plt.show()
    return fig, axes


def _run_rrt_comparison(name, obstacles, bounds, seed, start, end,
                        waypoints=None):
    """Run RRT and RRT* on the same problem, print stats, and plot comparison."""
    t0 = time.perf_counter()
    r_rrt = plan_path(
        start=start, end=end, waypoints=waypoints,
        obstacles=obstacles, bounds=bounds, seed=seed, debug=True,
        rrt_star=False,
    )
    t_rrt = time.perf_counter() - t0

    t0 = time.perf_counter()
    r_star = plan_path(
        start=start, end=end, waypoints=waypoints,
        obstacles=obstacles, bounds=bounds, seed=seed, debug=True,
        rrt_star=True,
    )
    t_star = time.perf_counter() - t0

    _print_result(r_rrt, f"{name} — RRT")
    _print_result(r_star, f"{name} — RRT*")

    len_rrt = sum(_dist(r_rrt.path[i], r_rrt.path[i + 1])
                  for i in range(len(r_rrt.path) - 1))
    len_star = sum(_dist(r_star.path[i], r_star.path[i + 1])
                   for i in range(len(r_star.path) - 1))
    turn_rrt = _total_turning_angle(r_rrt.path)
    turn_star = _total_turning_angle(r_star.path)
    print(f"\n  Comparison:")
    print(f"             length      turning       time")
    print(f"    RRT:  {len_rrt:>7.3f} m   {math.degrees(turn_rrt):>7.1f} deg   {t_rrt:.3f} s")
    print(f"    RRT*: {len_star:>7.3f} m   {math.degrees(turn_star):>7.1f} deg   {t_star:.3f} s")
    print(f"    diff: {(len_star - len_rrt) / len_rrt * 100:>+6.1f} %   "
          f"{(turn_star - turn_rrt) / turn_rrt * 100:>+6.1f} %   "
          f"{t_star / t_rrt:>5.1f}x")

    _plot_rrt_comparison(r_rrt, r_star,
                         f'RRT vs RRT* — {name}')


# ============================================================================
# Individual example functions
# ============================================================================

def example_1():
    """No waypoints, wall with gap"""
    r = plan_path(
        start=(0.3, 0.5),
        end=(2.7, 2.5),
        obstacles=[
            BoxObstacle(1.2, 1.5, 2.0, 0.15),
            CircleObstacle(2.5, 1.0, 0.25),
            CircleObstacle(0.5, 2.2, 0.2),
        ],
        bounds=BOUNDS, seed=42, debug=True,
    )
    _print_result(r, "Example 1: No waypoints — wall with gap")
    plot_stages(r)


def example_2():
    """Narrow corridor with waypoints"""
    r = plan_path(
        start=(0.3, 1.5),
        end=(2.7, 1.5),
        waypoints=[
            Waypoint(1.5, 1.5, weight=0.95),
            Waypoint(2.5, 0.5, weight=0.4),
        ],
        obstacles=[
            BoxObstacle(1.5, 1.15, 1.8, 0.12),
            BoxObstacle(1.5, 1.85, 1.8, 0.12),
            CircleObstacle(2.3, 1.5, 0.15),
        ],
        bounds=BOUNDS, seed=7, debug=True,
    )
    _print_result(r, "Example 2: Narrow corridor with waypoints")
    plot_stages(r)


def example_3():
    """Scattered circles, zig-zag waypoints"""
    r = plan_path(
        start=(0.2, 0.2),
        end=(2.8, 2.8),
        waypoints=[
            Waypoint(0.5, 2.0, weight=0.8),
            Waypoint(1.5, 0.5, weight=0.3),
            Waypoint(2.5, 2.0, weight=0.6),
        ],
        obstacles=[
            CircleObstacle(0.9, 1.2, 0.2),
            CircleObstacle(1.8, 1.8, 0.25),
            CircleObstacle(1.2, 2.3, 0.15),
            CircleObstacle(2.3, 1.0, 0.2),
            CircleObstacle(0.6, 0.7, 0.15),
            BoxObstacle(2.0, 2.6, 0.3, 0.25),
        ],
        bounds=BOUNDS, seed=13, debug=True,
    )
    _print_result(r, "Example 3: Scattered circles, zig-zag waypoints")
    plot_stages(r)


def example_4():
    """Dense box maze, single waypoint"""
    r = plan_path(
        start=(0.2, 2.5),
        end=(2.8, 0.3),
        waypoints=[
            Waypoint(2.5, 2.5, weight=0.9),
        ],
        obstacles=[
            BoxObstacle(1.0, 2.0, 0.15, 1.2),
            BoxObstacle(2.0, 1.0, 0.15, 1.2),
            BoxObstacle(1.5, 1.5, 0.8, 0.15),
            CircleObstacle(0.5, 1.0, 0.2),
            CircleObstacle(2.5, 1.8, 0.15),
        ],
        bounds=BOUNDS, seed=99, debug=True,
    )
    _print_result(r, "Example 4: Dense box maze, single tight waypoint")
    plot_stages(r)


def example_5():
    """Waypoints only — weight showcase (mixed)"""
    r = plan_path(
        start=(0.2, 1.5),
        end=(2.8, 1.5),
        waypoints=[
            Waypoint(0.7, 2.5, weight=0.0),
            Waypoint(1.1, 0.3, weight=0.25),
            Waypoint(1.5, 2.7, weight=0.5),
            Waypoint(1.9, 0.3, weight=0.75),
            Waypoint(2.3, 2.7, weight=1.0),
        ],
        bounds=BOUNDS, seed=0, debug=True,
    )
    _print_result(r, "Example 5: Waypoints only — weight showcase (mixed)")
    for i, wp in enumerate(r.waypoints):
        closest = min(_dist(p, (wp.x, wp.y)) for p in r.path)
        zone_r = _waypoint_zone_radius(wp.weight)
        print(f"  WP{i + 1} ({wp.x}, {wp.y}) w={wp.weight:.2f}  "
              f"zone={zone_r:.2f}m  closest={closest:.4f}m")
    plot_stages(r)


def example_6():
    """Waypoints only — all tight, path follows them"""
    r = plan_path(
        start=(0.2, 1.5),
        end=(2.8, 1.5),
        waypoints=[
            Waypoint(0.7, 2.5, weight=0.95),
            Waypoint(1.1, 0.3, weight=0.90),
            Waypoint(1.5, 2.7, weight=0.95),
            Waypoint(1.9, 0.3, weight=0.90),
            Waypoint(2.3, 2.7, weight=1.00),
        ],
        bounds=BOUNDS, seed=0, debug=True,
    )
    _print_result(r, "Example 6: Waypoints only — all tight weights")
    for i, wp in enumerate(r.waypoints):
        closest = min(_dist(p, (wp.x, wp.y)) for p in r.path)
        zone_r = _waypoint_zone_radius(wp.weight)
        print(f"  WP{i + 1} ({wp.x}, {wp.y}) w={wp.weight:.2f}  "
              f"zone={zone_r:.2f}m  closest={closest:.4f}m")
    plot_stages(r)


def example_7():
    """Rotated box obstacles (45 deg and 30 deg)"""
    r = plan_path(
        start=(0.3, 0.5),
        end=(2.7, 2.5),
        obstacles=[
            BoxObstacle(1.5, 1.5, 2.0, 0.15, psi=math.pi / 4),
            BoxObstacle(2.0, 0.8, 0.8, 0.15, psi=math.pi / 6),
            CircleObstacle(0.8, 2.0, 0.2),
        ],
        bounds=BOUNDS, seed=42, debug=True,
    )
    _print_result(r, "Example 7: Rotated box obstacles (45 deg and 30 deg)")
    plot_stages(r)


def example_8():
    """Rotated box chicane"""
    r = plan_path(
        start=(0.2, 1.5),
        end=(2.8, 1.5),
        waypoints=[
            Waypoint(1.5, 1.5, weight=0.7),
        ],
        obstacles=[
            BoxObstacle(0.8, 1.5, 1.2, 0.12, psi=math.pi / 3),
            BoxObstacle(1.5, 1.5, 1.2, 0.12, psi=-math.pi / 4),
            BoxObstacle(2.2, 1.5, 1.2, 0.12, psi=math.pi / 6),
        ],
        bounds=BOUNDS, seed=21, debug=True,
    )
    _print_result(r, "Example 8: Rotated box chicane")
    plot_stages(r)


def example_9():
    """Mixed rotated and axis-aligned obstacles"""
    r = plan_path(
        start=(0.3, 0.3),
        end=(2.7, 2.7),
        waypoints=[
            Waypoint(0.5, 2.5, weight=0.85),
            Waypoint(2.5, 0.5, weight=0.85),
        ],
        obstacles=[
            BoxObstacle(1.5, 1.5, 0.8, 0.15),
            BoxObstacle(1.5, 1.5, 0.15, 0.8),
            BoxObstacle(0.8, 2.0, 0.6, 0.12, psi=math.pi / 5),
            BoxObstacle(2.2, 1.0, 0.6, 0.12, psi=-math.pi / 5),
            CircleObstacle(1.5, 0.5, 0.15),
            CircleObstacle(1.5, 2.5, 0.15),
        ],
        bounds=BOUNDS, seed=55, debug=True,
    )
    _print_result(r, "Example 9: Mixed rotated and axis-aligned obstacles")
    plot_stages(r)


def example_10():
    """Padding = 0.15 m (robot half-width)"""
    r = plan_path(
        start=(0.3, 0.5),
        end=(2.7, 2.5),
        obstacles=[
            BoxObstacle(1.2, 1.5, 2.0, 0.15),
            CircleObstacle(2.5, 1.0, 0.25),
            CircleObstacle(0.5, 2.2, 0.2),
        ],
        bounds=BOUNDS, seed=42, padding=0.15, debug=True,
    )
    _print_result(r, "Example 10: Padding = 0.15 m (robot half-width)")
    plot_stages(r)


def example_11():
    """Smoothing comparison (0.0, 0.5, 1.0 side by side)"""
    import matplotlib.pyplot as plt

    obstacles = [
        BoxObstacle(1.2, 1.5, 2.0, 0.15),
        CircleObstacle(2.5, 1.0, 0.25),
        CircleObstacle(0.5, 2.2, 0.2),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    for ax, s in zip(axes, [0.0, 0.75, 1.0]):
        result = plan_path(
            start=(0.3, 0.5), end=(2.7, 2.5),
            obstacles=obstacles,
            bounds=BOUNDS, seed=42, smoothing=s, debug=True,
        )
        spacings = [_dist(result.path[k], result.path[k + 1])
                     for k in range(len(result.path) - 1)]
        total_len = sum(spacings) if spacings else 0
        _print_result(result, f"Example 11: smoothing={s}")

        _draw_background(ax, result, f'smoothing = {s}')

        if len(result.polyline) >= 2:
            xs = [p[0] for p in result.polyline]
            ys = [p[1] for p in result.polyline]
            ax.plot(xs, ys, '--', color='#b2bec3', lw=1, zorder=2, label='Polyline')

        xs = [p[0] for p in result.path]
        ys = [p[1] for p in result.path]
        ax.plot(xs, ys, '-', color='#2d3436', lw=1.5, zorder=3, label='Final path')
        ax.scatter(xs, ys, c='#636e72', s=4, zorder=4)

        ax.text(
            0.02, 0.02,
            f'{len(result.path)} samples\nLength: {total_len:.2f} m',
            transform=ax.transAxes, fontsize=8, verticalalignment='bottom',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
        ax.legend(loc='upper right', fontsize=7)

    fig.suptitle('Smoothing Comparison', fontsize=13, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()


def example_12():
    """Padding + rotated obstacles"""
    r = plan_path(
        start=(0.3, 0.5),
        end=(2.7, 2.5),
        obstacles=[
            BoxObstacle(1.5, 1.5, 2.0, 0.15, psi=math.pi / 4),
            BoxObstacle(2.0, 0.8, 0.8, 0.15, psi=math.pi / 6),
            CircleObstacle(0.8, 2.0, 0.2),
        ],
        bounds=BOUNDS, seed=42, padding=0.12, debug=True,
    )
    _print_result(r, "Example 12: Padding + rotated obstacles")
    plot_stages(r)


def example_13():
    """State constraints — restricted x/y corridor"""
    r = plan_path(
        start=(0.5, 0.5),
        end=(2.0, 2.5),
        waypoints=[
            Waypoint(1.0, 2.0, weight=0.99),
            Waypoint(1.5, 1.0, weight=0.99),
            Waypoint(2.0, 1.5, weight=0.99),
        ],
        obstacles=[
            CircleObstacle(1.5, 1.5, 0.3),
            CircleObstacle(0.8, 1.0, 0.15),
        ],
        bounds=BOUNDS,
        state_constraints=StateConstraints(x_min=0.3, x_max=2.2, y_min=0.3),
        seed=42, debug=True,
        padding=0.05
    )
    _print_result(r, "Example 13: State constraints — restricted corridor")
    plot_stages(r)


def example_14():
    """RRT vs RRT* comparison (no waypoints, obstacles only)"""
    _run_rrt_comparison(
        name="Example 14",
        start=(0.3, 0.3), end=(2.7, 2.7),
        obstacles=[
            BoxObstacle(1.5, 1.5, 1.6, 0.15),
            BoxObstacle(1.5, 0.8, 0.15, 1.0),
            CircleObstacle(2.3, 2.0, 0.25),
            CircleObstacle(0.7, 1.0, 0.2),
            BoxObstacle(2.2, 0.8, 0.8, 0.12, psi=math.pi / 5),
        ],
        bounds=BOUNDS, seed=42,
    )


def example_15():
    """RRT vs RRT* — dense maze with multiple narrow passages"""
    _run_rrt_comparison(
        name="Example 15 — Dense Maze",
        start=(0.3, 0.3), end=(2.7, 2.7),
        obstacles=[
            # Two horizontal walls with a narrow off-center gap
            BoxObstacle(0.85, 1.0, 1.3, 0.12),
            BoxObstacle(2.25, 1.0, 1.1, 0.12),
            BoxObstacle(2.15, 2.0, 0.9, 0.12),
            BoxObstacle(0.75, 2.0, 1.1, 0.12),
            # Vertical barriers creating a zig-zag corridor
            BoxObstacle(1.0, 1.6, 0.12, 0.8),
            BoxObstacle(2.0, 1.4, 0.12, 0.8),
            # Scattered circle obstacles in the open areas
            CircleObstacle(0.4, 0.5, 0.15),
            CircleObstacle(2.4, 2.5, 0.15),
            CircleObstacle(2.5, 0.5, 0.18),
            CircleObstacle(0.5, 2.5, 0.12),
        ],
        bounds=BOUNDS, seed=42,
    )


def example_16():
    """RRT vs RRT* — serpentine with rotated barriers"""
    # Alternating horizontal walls with gaps on opposite sides force the path
    # into a serpentine. Rotated barriers in the corridors create multiple
    # viable routes of different lengths.
    _run_rrt_comparison(
        name="Example 16 — Serpentine",
        start=(0.2, 0.2), end=(2.8, 2.8),
        obstacles=[
            # Row 1 (y=0.8): gap on the right (x ~ 2.2–2.8)
            BoxObstacle(0.95, 0.8, 1.7, 0.10),
            # Row 2 (y=1.5): gap on the left (x ~ 0.2–0.8)
            BoxObstacle(1.95, 1.5, 1.9, 0.10),
            # Row 3 (y=2.2): gap on the right (x ~ 2.2–2.8)
            BoxObstacle(0.95, 2.2, 1.7, 0.10),
            # Rotated barriers in the corridors — create alternate routes
            BoxObstacle(2.3, 1.1, 0.45, 0.08, psi=math.pi / 4),
            BoxObstacle(0.7, 1.85, 0.45, 0.08, psi=-math.pi / 4),
            # Circle obstacles adding complexity within corridors
            CircleObstacle(1.5, 1.1, 0.12),
            CircleObstacle(1.5, 1.9, 0.12),
            CircleObstacle(2.5, 1.9, 0.10),
            CircleObstacle(0.5, 1.1, 0.10),
        ],
        bounds=BOUNDS, seed=17,
    )


def example_17():
    """RRT vs RRT* — obstacle course with waypoints"""
    # Tight waypoints force the path through specific narrow passages between
    # dense obstacles. Each segment must navigate a constrained region, so
    # tree quality matters for every segment independently.
    _run_rrt_comparison(
        name="Example 17 — Obstacle Course + Waypoints",
        start=(0.2, 1.5), end=(2.8, 1.5),
        waypoints=[
            Waypoint(1.0, 2.5, weight=0.95),   # top-left pocket
            Waypoint(1.5, 0.5, weight=0.90),   # bottom-center pocket
            Waypoint(2.3, 2.3, weight=0.95),   # top-right pocket
        ],
        obstacles=[
            # Central cross barrier
            BoxObstacle(1.5, 1.5, 1.4, 0.12),  # horizontal bar
            BoxObstacle(1.5, 1.5, 0.12, 1.4),  # vertical bar
            # Perimeter barriers — create pockets around the waypoints
            BoxObstacle(0.5, 2.0, 0.8, 0.10),  # shelf above start
            BoxObstacle(2.5, 2.0, 0.8, 0.10),  # shelf above end
            BoxObstacle(0.5, 1.0, 0.8, 0.10),  # shelf below start
            BoxObstacle(2.5, 1.0, 0.8, 0.10),  # shelf below end
            # Rotated gates near the waypoints
            BoxObstacle(0.7, 2.3, 0.5, 0.08, psi=math.pi / 6),
            BoxObstacle(2.0, 0.7, 0.5, 0.08, psi=-math.pi / 6),
            BoxObstacle(2.0, 2.5, 0.4, 0.08, psi=math.pi / 5),
            # Circles blocking shortcuts
            CircleObstacle(1.0, 1.5, 0.12),
            CircleObstacle(2.0, 1.5, 0.12),
            CircleObstacle(1.5, 2.5, 0.10),
            CircleObstacle(1.5, 0.5, 0.10),
            CircleObstacle(0.3, 2.2, 0.08),
            CircleObstacle(2.7, 0.8, 0.08),
        ],
        bounds=BOUNDS, seed=31,
    )


def example_18():
    """Heading strength comparison — same target heading, varying strength"""
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    import numpy as np

    obstacles = [
        CircleObstacle(1.5, 1.5, 0.3),
        BoxObstacle(0.8, 2.2, 0.6, 0.12),
    ]
    start = (0.3, 0.5)
    end = (2.7, 2.0)
    target_heading = math.pi  # arrive heading left (180 deg)

    strengths = [0.3, 1.0, 3.0, 6.0]
    fig, axes = plt.subplots(1, len(strengths), figsize=(6 * len(strengths), 6))

    for ax, s in zip(axes, strengths):
        result = plan_path(
            start=start, end=end,
            obstacles=obstacles,
            bounds=BOUNDS, seed=42,
            target_heading=target_heading,
            heading_strength=s,
            debug=True,
        )

        _draw_background(ax, result, f'heading_strength = {s}', draw_zones=False)

        # Draw spline curve
        if result.spline_curve and len(result.spline_curve) >= 2:
            xs = [p[0] for p in result.spline_curve]
            ys = [p[1] for p in result.spline_curve]
            ax.plot(xs, ys, '-', color='#b2bec3', lw=1, zorder=2, label='Spline')

        # Draw final path
        xs = [p[0] for p in result.path]
        ys = [p[1] for p in result.path]
        ax.plot(xs, ys, '-', color='#2d3436', lw=1.5, zorder=3, label='Final path')
        ax.scatter(xs, ys, c='#636e72', s=4, zorder=4)

        # Draw target heading arrow at the endpoint
        arrow_len = 0.25
        dx = arrow_len * math.cos(target_heading)
        dy = arrow_len * math.sin(target_heading)
        ax.annotate(
            '', xy=(end[0] + dx, end[1] + dy), xytext=end,
            arrowprops=dict(arrowstyle='->', color='#d63031', lw=2.5),
            zorder=12)

        # Draw actual arrival tangent (from last two path points)
        if len(result.path) >= 2:
            p_last = result.path[-1]
            p_prev = result.path[-2]
            arr_dx = p_last[0] - p_prev[0]
            arr_dy = p_last[1] - p_prev[1]
            arr_len = math.hypot(arr_dx, arr_dy)
            if arr_len > 1e-9:
                arr_dx = arr_dx / arr_len * arrow_len
                arr_dy = arr_dy / arr_len * arrow_len
                ax.annotate(
                    '', xy=(end[0] + arr_dx, end[1] + arr_dy), xytext=end,
                    arrowprops=dict(arrowstyle='->', color='#0984e3', lw=2),
                    zorder=11)

        spacings = [_dist(result.path[k], result.path[k + 1])
                    for k in range(len(result.path) - 1)]
        total_len = sum(spacings)
        ax.text(
            0.02, 0.02,
            f'{len(result.path)} samples\nLength: {total_len:.2f} m',
            transform=ax.transAxes, fontsize=8, verticalalignment='bottom',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

        # Legend entries for the arrows
        ax.plot([], [], '-', color='#d63031', lw=2.5, label='Target heading')
        ax.plot([], [], '-', color='#0984e3', lw=2, label='Actual tangent')
        ax.legend(loc='upper right', fontsize=7)

    fig.suptitle(
        f'Heading Strength Comparison  (target_heading = {math.degrees(target_heading):.0f} deg)',
        fontsize=13, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()


# ============================================================================
# Registry and interactive runner
# ============================================================================

EXAMPLES = [
    (1,  "No waypoints — wall with gap",              example_1),
    (2,  "Narrow corridor with waypoints",             example_2),
    (3,  "Scattered circles, zig-zag waypoints",       example_3),
    (4,  "Dense box maze, single tight waypoint",      example_4),
    (5,  "Waypoints only — weight showcase (mixed)",   example_5),
    (6,  "Waypoints only — all tight weights",         example_6),
    (7,  "Rotated box obstacles (45 deg and 30 deg)",  example_7),
    (8,  "Rotated box chicane",                        example_8),
    (9,  "Mixed rotated and axis-aligned obstacles",   example_9),
    (10, "Padding = 0.15 m (robot half-width)",        example_10),
    (11, "Smoothing comparison (side by side)",         example_11),
    (12, "Padding + rotated obstacles",                example_12),
    (13, "State constraints — restricted corridor",    example_13),
    (14, "RRT vs RRT* comparison",                     example_14),
    (15, "RRT vs RRT* — dense maze",                  example_15),
    (16, "RRT vs RRT* — serpentine + rotated barriers", example_16),
    (17, "RRT vs RRT* — obstacle course + waypoints", example_17),
    (18, "Heading strength comparison",                example_18),
]


def run_examples():
    """Interactive example picker. Lists examples and lets the user choose."""
    while True:
        print(f"\n{'=' * 55}")
        print("  Motion Planning Examples")
        print(f"{'=' * 55}")
        for num, desc, _ in EXAMPLES:
            print(f"  {num:>2}.  {desc}")
        print(f"   a.  Run all")
        print(f"   q.  Quit")
        print(f"{'─' * 55}")

        choice = input("  Select example: ").strip().lower()

        if choice == 'q':
            break

        if choice == 'a':
            for num, _, func in EXAMPLES:
                func()
            continue

        try:
            num = int(choice)
        except ValueError:
            print(f"  Invalid input: '{choice}'")
            continue

        match = [func for n, _, func in EXAMPLES if n == num]
        if not match:
            print(f"  No example {num}. Choose 1–{EXAMPLES[-1][0]}.")
            continue

        match[0]()


if __name__ == '__main__':
    run_examples()
