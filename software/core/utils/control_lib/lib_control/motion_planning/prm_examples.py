"""
PRM (Probabilistic Roadmap) Examples.

Run directly:
    python -m core.utils.control_lib.lib_control.motion_planning.prm_examples

Demonstrates building, querying, saving/loading, waypoints, and
a timing comparison with RRT.
"""

import math
import os
import tempfile
import time

from core.utils.control_lib.lib_control.motion_planning.common import (
    Bounds, BoxObstacle, CircleObstacle, Waypoint, _dist,
)
from core.utils.control_lib.lib_control.motion_planning.prm import (
    PRMConfig, PRMRoadmap, plan_path_prm, plot_roadmap,
)
from core.utils.control_lib.lib_control.motion_planning.rrt import plan_path

BOUNDS = Bounds(0, 3, 0, 3)


# ============================================================================
# Individual examples
# ============================================================================

def example_1():
    """Basic PRM — build, query, plot"""
    print("\n  Building PRM roadmap (500 nodes)...")
    obstacles = [
        CircleObstacle(1.5, 1.2, 0.3),
        BoxObstacle(1.5, 2.2, 1.0, 0.15),
        CircleObstacle(0.8, 0.8, 0.2),
    ]

    rm = PRMRoadmap(
        obstacles=obstacles,
        bounds=BOUNDS,
        config=PRMConfig(n_samples=500, k_neighbors=10,
                         connection_radius=0.8, seed=42),
    )

    t0 = time.perf_counter()
    rm.build()
    t_build = time.perf_counter() - t0
    print(f"  Built: {rm.node_count} nodes, {rm.edge_count} edges "
          f"({t_build:.3f} s)")

    start, end = (0.3, 0.3), (2.7, 2.7)

    t0 = time.perf_counter()
    path = rm.query(start, end)
    t_query = time.perf_counter() - t0

    path_len = sum(_dist(path[i], path[i + 1])
                   for i in range(len(path) - 1))
    print(f"  Query: {len(path)} points, length {path_len:.3f} m "
          f"({t_query * 1000:.1f} ms)")

    plot_roadmap(rm, path=path, start=start, end=end,
                 title="Example 1: Basic PRM")


def example_2():
    """Multi-query — same roadmap, different start/goal pairs"""
    obstacles = [
        BoxObstacle(1.5, 1.5, 1.6, 0.15),
        BoxObstacle(1.5, 0.8, 0.15, 1.0),
        CircleObstacle(2.3, 2.0, 0.25),
        CircleObstacle(0.7, 1.0, 0.2),
    ]

    rm = PRMRoadmap(
        obstacles=obstacles,
        bounds=BOUNDS,
        config=PRMConfig(n_samples=600, k_neighbors=12,
                         connection_radius=0.8, seed=42),
    )

    print("\n  Building roadmap...")
    t0 = time.perf_counter()
    rm.build()
    t_build = time.perf_counter() - t0
    print(f"  Built: {rm.node_count} nodes, {rm.edge_count} edges "
          f"({t_build:.3f} s)")

    queries = [
        ((0.3, 0.3), (2.7, 2.7)),
        ((0.3, 2.7), (2.7, 0.3)),
        ((1.0, 0.3), (2.0, 2.7)),
        ((0.3, 1.5), (2.7, 1.5)),
    ]

    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(14, 14))

    for idx, ((sx, sy), (ex, ey)) in enumerate(queries):
        t0 = time.perf_counter()
        path = rm.query((sx, sy), (ex, ey))
        t_q = time.perf_counter() - t0
        path_len = sum(_dist(path[i], path[i + 1])
                       for i in range(len(path) - 1))
        print(f"  Query {idx + 1}: ({sx},{sy})→({ex},{ey})  "
              f"{len(path)} pts, {path_len:.3f} m, {t_q * 1000:.1f} ms")

        ax = axes[idx // 2, idx % 2]
        # Plot manually since plot_roadmap creates its own figure
        import matplotlib.patches as patches
        from matplotlib.collections import LineCollection

        ax.set_aspect('equal')
        ax.set_title(f'Query {idx + 1}: ({sx},{sy}) → ({ex},{ey})',
                     fontsize=10, fontweight='bold')
        ax.grid(True, alpha=0.2)

        b = BOUNDS
        ax.set_xlim(b.x_min - 0.2, b.x_max + 0.2)
        ax.set_ylim(b.y_min - 0.2, b.y_max + 0.2)

        rect = patches.Rectangle(
            (b.x_min, b.y_min), b.x_max - b.x_min, b.y_max - b.y_min,
            linewidth=1.5, edgecolor='#2d3436', facecolor='none',
            linestyle='--', alpha=0.5)
        ax.add_patch(rect)

        for obs in obstacles:
            if isinstance(obs, CircleObstacle):
                c = patches.Circle((obs.cx, obs.cy), obs.radius,
                                   facecolor='#ff6b6b', edgecolor='#c0392b',
                                   alpha=0.5, linewidth=1)
                ax.add_patch(c)
            elif isinstance(obs, BoxObstacle):
                from core.utils.control_lib.lib_control.motion_planning.common import _draw_box_patch
                _draw_box_patch(ax, obs, alpha=0.5, linewidth=1)

        # Roadmap edges (faint)
        edge_set = set()
        segs = []
        for i, nbs in rm._adj.items():
            for j, _ in nbs:
                key = (min(i, j), max(i, j))
                if key not in edge_set:
                    edge_set.add(key)
                    segs.append([rm._nodes[i], rm._nodes[j]])
        if segs:
            lc = LineCollection(segs, colors='#dfe6e9', alpha=0.4,
                                linewidths=0.4, zorder=2)
            ax.add_collection(lc)

        # Path
        pxs = [p[0] for p in path]
        pys = [p[1] for p in path]
        ax.plot(pxs, pys, '-', color='#2d3436', lw=2, zorder=5)
        ax.scatter(pxs, pys, c='#636e72', s=3, zorder=6)
        ax.plot(sx, sy, 's', color='#00b894', markersize=8, zorder=7)
        ax.plot(ex, ey, '*', color='#d63031', markersize=10, zorder=7)

        ax.text(0.02, 0.02,
                f'{len(path)} pts, {path_len:.2f} m\n{t_q * 1000:.1f} ms',
                transform=ax.transAxes, fontsize=8, verticalalignment='bottom',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                          alpha=0.8))

    fig.suptitle(f'Example 2: Multi-Query PRM ({rm.node_count} nodes)',
                 fontsize=13, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()


def example_3():
    """Save / load — build, save to JSON, load, query"""
    obstacles = [
        CircleObstacle(1.5, 1.5, 0.3),
        BoxObstacle(0.8, 2.0, 0.6, 0.15, psi=math.pi / 5),
    ]

    rm = PRMRoadmap(
        obstacles=obstacles,
        bounds=BOUNDS,
        config=PRMConfig(n_samples=300, seed=42),
    )
    rm.build()
    print(f"\n  Built: {rm.node_count} nodes, {rm.edge_count} edges")

    # Save
    filepath = os.path.join(tempfile.gettempdir(), 'test_roadmap.json')
    rm.save(filepath)
    file_size = os.path.getsize(filepath) / 1024
    print(f"  Saved to {filepath} ({file_size:.1f} KB)")

    # Load
    t0 = time.perf_counter()
    rm2 = PRMRoadmap.load(filepath)
    t_load = time.perf_counter() - t0
    print(f"  Loaded: {rm2.node_count} nodes, {rm2.edge_count} edges "
          f"({t_load * 1000:.1f} ms)")

    # Query both
    start, end = (0.3, 0.3), (2.7, 2.7)
    path1 = rm.query(start, end)
    path2 = rm2.query(start, end)
    len1 = sum(_dist(path1[i], path1[i + 1])
               for i in range(len(path1) - 1))
    len2 = sum(_dist(path2[i], path2[i + 1])
               for i in range(len(path2) - 1))
    print(f"  Original path: {len(path1)} pts, {len1:.3f} m")
    print(f"  Loaded path:   {len(path2)} pts, {len2:.3f} m")
    print(f"  Paths match: {abs(len1 - len2) < 0.01}")

    plot_roadmap(rm2, path=path2, start=start, end=end,
                 title="Example 3: Loaded PRM Roadmap")

    # Clean up
    os.remove(filepath)


def example_4():
    """PRM with intermediate waypoints"""
    obstacles = [
        CircleObstacle(1.0, 1.5, 0.25),
        CircleObstacle(2.0, 1.5, 0.25),
        BoxObstacle(1.5, 0.8, 0.8, 0.15),
        BoxObstacle(1.5, 2.2, 0.8, 0.15),
    ]
    waypoints = [
        Waypoint(0.5, 2.5, weight=0.8),
        Waypoint(2.5, 0.5, weight=0.8),
    ]

    rm = PRMRoadmap(
        obstacles=obstacles,
        bounds=BOUNDS,
        config=PRMConfig(n_samples=500, seed=42),
    )
    rm.build()
    print(f"\n  Built: {rm.node_count} nodes, {rm.edge_count} edges")

    start, end = (0.3, 0.3), (2.7, 2.7)

    t0 = time.perf_counter()
    path = rm.query(start, end, waypoints=waypoints)
    t_q = time.perf_counter() - t0

    path_len = sum(_dist(path[i], path[i + 1])
                   for i in range(len(path) - 1))
    print(f"  Query with waypoints: {len(path)} pts, {path_len:.3f} m "
          f"({t_q * 1000:.1f} ms)")

    plot_roadmap(rm, path=path, start=start, end=end,
                 waypoints=waypoints,
                 title="Example 4: PRM with Waypoints")


def example_5():
    """Smoothing comparison — same path with different smoothing values"""
    obstacles = [
        CircleObstacle(1.5, 1.2, 0.3),
        BoxObstacle(1.5, 2.2, 1.0, 0.15),
        CircleObstacle(0.8, 0.8, 0.2),
        BoxObstacle(2.3, 0.7, 0.15, 0.8),
    ]
    waypoints = [
        Waypoint(0.5, 2.5, weight=0.7),
        Waypoint(2.5, 0.5, weight=0.7),
    ]

    rm = PRMRoadmap(
        obstacles=obstacles,
        bounds=BOUNDS,
        config=PRMConfig(n_samples=500, seed=42),
    )
    rm.build()
    print(f"\n  Built: {rm.node_count} nodes, {rm.edge_count} edges")

    start, end = (0.3, 0.3), (2.7, 2.7)
    smoothing_values = [0.0, 0.3, 0.6, 1.0]

    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.collections import LineCollection

    fig, axes = plt.subplots(1, len(smoothing_values),
                             figsize=(5 * len(smoothing_values), 5))

    for idx, s in enumerate(smoothing_values):
        path = rm.query(start, end, waypoints=waypoints, smoothing=s)
        path_len = sum(_dist(path[i], path[i + 1])
                       for i in range(len(path) - 1))
        print(f"  smoothing={s:.1f}: {len(path)} pts, {path_len:.3f} m")

        ax = axes[idx]
        ax.set_aspect('equal')
        ax.set_title(f'smoothing = {s}', fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.2)

        b = BOUNDS
        ax.set_xlim(b.x_min - 0.2, b.x_max + 0.2)
        ax.set_ylim(b.y_min - 0.2, b.y_max + 0.2)

        # Bounds
        rect = patches.Rectangle(
            (b.x_min, b.y_min), b.x_max - b.x_min, b.y_max - b.y_min,
            linewidth=1.5, edgecolor='#2d3436', facecolor='none',
            linestyle='--', alpha=0.5)
        ax.add_patch(rect)

        # Obstacles
        for obs in obstacles:
            if isinstance(obs, CircleObstacle):
                c = patches.Circle((obs.cx, obs.cy), obs.radius,
                                   facecolor='#ff6b6b', edgecolor='#c0392b',
                                   alpha=0.5, linewidth=1)
                ax.add_patch(c)
            elif isinstance(obs, BoxObstacle):
                from core.utils.control_lib.lib_control.motion_planning.common import (
                    _draw_box_patch, _waypoint_zone_radius,
                )
                _draw_box_patch(ax, obs, alpha=0.5, linewidth=1)

        # Waypoint zones
        from core.utils.control_lib.lib_control.motion_planning.common import _waypoint_zone_radius
        for wp in waypoints:
            r = _waypoint_zone_radius(wp.weight)
            zone = patches.Circle(
                (wp.x, wp.y), r,
                facecolor='#74b9ff', edgecolor='#0984e3',
                alpha=0.12, linewidth=1, linestyle='--')
            ax.add_patch(zone)
            ax.plot(wp.x, wp.y, 'o', color='#0984e3', markersize=5, zorder=5)

        # Roadmap edges (very faint)
        edge_set = set()
        segs = []
        for i, nbs in rm._adj.items():
            for j, _ in nbs:
                key = (min(i, j), max(i, j))
                if key not in edge_set:
                    edge_set.add(key)
                    segs.append([rm._nodes[i], rm._nodes[j]])
        if segs:
            lc = LineCollection(segs, colors='#dfe6e9', alpha=0.25,
                                linewidths=0.3, zorder=2)
            ax.add_collection(lc)

        # Path
        pxs = [p[0] for p in path]
        pys = [p[1] for p in path]
        ax.plot(pxs, pys, '-', color='#2d3436', linewidth=2, zorder=5)

        # Start / End
        ax.plot(start[0], start[1], 's', color='#00b894', markersize=8,
                zorder=7)
        ax.plot(end[0], end[1], '*', color='#d63031', markersize=12,
                zorder=7)

        ax.text(0.02, 0.02,
                f'{len(path)} pts\n{path_len:.2f} m',
                transform=ax.transAxes, fontsize=8, verticalalignment='bottom',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                          alpha=0.8))

    fig.suptitle(
        'Example 5: Smoothing Comparison\n'
        '0.0 = tight (follows polyline corners)  →  1.0 = smooth (round curves)',
        fontsize=12, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.92])
    plt.show()


def example_6():
    """RRT vs PRM timing comparison"""
    obstacles = [
        BoxObstacle(1.5, 1.5, 1.6, 0.15),
        BoxObstacle(1.5, 0.8, 0.15, 1.0),
        CircleObstacle(2.3, 2.0, 0.25),
        CircleObstacle(0.7, 1.0, 0.2),
        BoxObstacle(2.2, 0.8, 0.8, 0.12, psi=math.pi / 5),
    ]

    start, end = (0.3, 0.3), (2.7, 2.7)
    n_queries = 5

    # Alternate start/end points for multi-query test
    queries = [
        ((0.3, 0.3), (2.7, 2.7)),
        ((0.3, 2.7), (2.7, 0.3)),
        ((1.0, 0.3), (2.0, 2.7)),
        ((0.3, 1.5), (2.7, 1.5)),
        ((2.5, 0.3), (0.5, 2.5)),
    ]

    print(f"\n  Running {n_queries} queries: RRT vs PRM")

    # --- RRT ---
    rrt_times = []
    rrt_lengths = []
    for (s, e) in queries:
        t0 = time.perf_counter()
        path = plan_path(start=s, end=e, obstacles=obstacles,
                         bounds=BOUNDS, seed=42)
        t_rrt = time.perf_counter() - t0
        rrt_times.append(t_rrt)
        rrt_lengths.append(sum(_dist(path[i], path[i + 1])
                               for i in range(len(path) - 1)))

    # --- PRM (build + queries) ---
    t0 = time.perf_counter()
    rm = PRMRoadmap(
        obstacles=obstacles,
        bounds=BOUNDS,
        config=PRMConfig(n_samples=600, k_neighbors=12,
                         connection_radius=0.8, seed=42),
    )
    rm.build()
    t_build = time.perf_counter() - t0

    prm_times = []
    prm_lengths = []
    for (s, e) in queries:
        t0 = time.perf_counter()
        path = rm.query(s, e)
        t_prm = time.perf_counter() - t0
        prm_times.append(t_prm)
        prm_lengths.append(sum(_dist(path[i], path[i + 1])
                               for i in range(len(path) - 1)))

    # --- Print results ---
    print(f"\n  {'':>8}   {'RRT':>10}   {'PRM':>10}   {'Speedup':>8}")
    print(f"  {'':>8}   {'─' * 10}   {'─' * 10}   {'─' * 8}")
    for i, (s, e) in enumerate(queries):
        speedup = rrt_times[i] / prm_times[i] if prm_times[i] > 0 else float('inf')
        print(f"  Query {i + 1}   {rrt_times[i] * 1000:>7.1f} ms   "
              f"{prm_times[i] * 1000:>7.1f} ms   {speedup:>6.1f}x")

    total_rrt = sum(rrt_times)
    total_prm = t_build + sum(prm_times)
    print(f"  {'─' * 45}")
    print(f"  RRT total:        {total_rrt * 1000:.1f} ms")
    print(f"  PRM build:        {t_build * 1000:.1f} ms")
    print(f"  PRM queries:      {sum(prm_times) * 1000:.1f} ms")
    print(f"  PRM total:        {total_prm * 1000:.1f} ms")
    print(f"  Overall speedup:  {total_rrt / total_prm:.1f}x")

    # Side-by-side plot
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Left: RRT timing bar chart
    ax = axes[0]
    x = range(n_queries)
    ax.bar(x, [t * 1000 for t in rrt_times], color='#e17055', alpha=0.7,
           label='RRT')
    ax.bar(x, [t * 1000 for t in prm_times], color='#0984e3', alpha=0.7,
           label='PRM query')
    ax.axhline(t_build * 1000, color='#0984e3', linestyle='--',
               linewidth=1, alpha=0.5, label=f'PRM build ({t_build * 1000:.0f} ms)')
    ax.set_xlabel('Query')
    ax.set_ylabel('Time [ms]')
    ax.set_title('Query Time Comparison', fontsize=10, fontweight='bold')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.2)

    # Right: Path length comparison
    ax = axes[1]
    width = 0.35
    ax.bar([i - width / 2 for i in x], rrt_lengths, width,
           color='#e17055', alpha=0.7, label='RRT')
    ax.bar([i + width / 2 for i in x], prm_lengths, width,
           color='#0984e3', alpha=0.7, label='PRM')
    ax.set_xlabel('Query')
    ax.set_ylabel('Path length [m]')
    ax.set_title('Path Length Comparison', fontsize=10, fontweight='bold')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.2)

    fig.suptitle('Example 6: RRT vs PRM Comparison', fontsize=13,
                 fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()


def example_7():
    """Clearance-weighted PRM — corridor with corners"""
    # U-shaped corridor (0.8 m wide) with two 90-degree corners.
    # At corners the shortest path cuts the inner wall; with clearance
    # weighting the path stays centred and takes wider turns.
    t = 0.06  # wall half-thickness
    cw_width = 0.8  # corridor width

    # Corridor outline (outer walls):
    #  Segment A: horizontal bottom,  x: 0→2.0, y ≈ 0.5
    #  Corner 1:  turn up at x ≈ 2.0
    #  Segment B: vertical right,     x ≈ 2.0, y: 0.5→2.5
    #  Corner 2:  turn left at y ≈ 2.5
    #  Segment C: horizontal top,     x: 2.0→0, y ≈ 2.5

    obstacles = [
        # --- Segment A: horizontal bottom corridor ---
        # outer (bottom) wall
        BoxObstacle(1.0, 0.5 - cw_width / 2 - t, 2.4, 2 * t),
        # inner (top) wall — stops before corner to leave gap
        BoxObstacle(0.8, 0.5 + cw_width / 2 + t, 1.6, 2 * t),

        # --- Corner 1 + Segment B: vertical right corridor ---
        # outer (right) wall
        BoxObstacle(2.0 + cw_width / 2 + t, 1.5, 2 * t, 2.4),
        # inner (left) wall
        BoxObstacle(2.0 - cw_width / 2 - t, 1.5, 2 * t, 1.2),

        # --- Corner 2 + Segment C: horizontal top corridor ---
        # outer (top) wall
        BoxObstacle(1.0, 2.5 + cw_width / 2 + t, 2.4, 2 * t),
        # inner (bottom) wall — stops before corner to leave gap
        BoxObstacle(0.8, 2.5 - cw_width / 2 - t, 1.6, 2 * t),
    ]

    bounds = Bounds(-0.5, 3.0, -0.5, 3.5)
    start = (0.15, 0.5)
    end = (0.15, 2.5)
    waypoints = [Waypoint(2.0, 1.0, weight=1), Waypoint(2.0, 2.5, weight=1)]

    clearance_weights = [0.0, 2.0, 5.0, 20.0]

    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.collections import LineCollection
    from core.utils.control_lib.lib_control.motion_planning.common import (
        _draw_box_patch, _min_clearance,
    )

    fig, axes = plt.subplots(1, len(clearance_weights),
                             figsize=(5 * len(clearance_weights), 5))

    for idx, cw in enumerate(clearance_weights):
        rm = PRMRoadmap(
            obstacles=obstacles,
            bounds=bounds,
            config=PRMConfig(
                n_samples=2000, k_neighbors=15,
                connection_radius=0.6, seed=42,
                clearance_weight=cw, clearance_threshold=0.8),
        )
        rm.build()

        path = rm.query(start, end, waypoints=waypoints)
        path_len = sum(_dist(path[i], path[i + 1])
                       for i in range(len(path) - 1))
        min_clear = min(_min_clearance(p[0], p[1], obstacles) for p in path)
        avg_clear = (sum(_min_clearance(p[0], p[1], obstacles) for p in path)
                     / len(path))
        print(f"  cw={cw:.1f}: {len(path)} pts, length={path_len:.3f} m, "
              f"min_clear={min_clear:.3f} m, avg_clear={avg_clear:.3f} m")

        ax = axes[idx]
        ax.set_aspect('equal')
        ax.set_title(f'clearance_weight = {cw}', fontsize=11,
                     fontweight='bold')
        ax.grid(True, alpha=0.2)

        b = bounds
        ax.set_xlim(b.x_min - 0.15, b.x_max + 0.15)
        ax.set_ylim(b.y_min - 0.15, b.y_max + 0.15)

        # Bounds
        rect = patches.Rectangle(
            (b.x_min, b.y_min), b.x_max - b.x_min, b.y_max - b.y_min,
            linewidth=1.5, edgecolor='#2d3436', facecolor='none',
            linestyle='--', alpha=0.5)
        ax.add_patch(rect)

        # Obstacles
        for obs in obstacles:
            if isinstance(obs, BoxObstacle):
                _draw_box_patch(ax, obs, alpha=0.6, linewidth=1)
            elif isinstance(obs, CircleObstacle):
                c = patches.Circle((obs.cx, obs.cy), obs.radius,
                                   facecolor='#ff6b6b', edgecolor='#c0392b',
                                   alpha=0.5, linewidth=1)
                ax.add_patch(c)

        # Waypoint zones
        from core.utils.control_lib.lib_control.motion_planning.common import _waypoint_zone_radius
        for wp in waypoints:
            r = _waypoint_zone_radius(wp.weight)
            zone = patches.Circle(
                (wp.x, wp.y), r,
                facecolor='#74b9ff', edgecolor='#0984e3',
                alpha=0.12, linewidth=1, linestyle='--')
            ax.add_patch(zone)
            ax.plot(wp.x, wp.y, 'o', color='#0984e3', markersize=5,
                    zorder=5)

        # Roadmap edges (very faint)
        edge_set = set()
        segs = []
        for i, nbs in rm._adj.items():
            for j, _ in nbs:
                key = (min(i, j), max(i, j))
                if key not in edge_set:
                    edge_set.add(key)
                    segs.append([rm._nodes[i], rm._nodes[j]])
        if segs:
            lc = LineCollection(segs, colors='#dfe6e9', alpha=0.2,
                                linewidths=0.3, zorder=2)
            ax.add_collection(lc)

        # Path
        pxs = [p[0] for p in path]
        pys = [p[1] for p in path]
        ax.plot(pxs, pys, '-', color='#2d3436', linewidth=2.5, zorder=5)

        # Start / End
        ax.plot(start[0], start[1], 's', color='#00b894', markersize=8,
                zorder=7)
        ax.plot(end[0], end[1], '*', color='#d63031', markersize=12,
                zorder=7)

        ax.text(0.02, 0.02,
                f'{path_len:.2f} m\n'
                f'min clear: {min_clear:.3f} m\n'
                f'avg clear: {avg_clear:.3f} m',
                transform=ax.transAxes, fontsize=8, verticalalignment='bottom',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                          alpha=0.8))

    fig.suptitle(
        'Example 7: Clearance-Weighted PRM — Corridor with Corners\n'
        'Higher clearance_weight pushes the path away from walls',
        fontsize=12, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.90])
    plt.show()


# ============================================================================
# Registry and interactive runner
# ============================================================================

EXAMPLES = [
    (1, "Basic PRM — build, query, plot",          example_1),
    (2, "Multi-query — same roadmap, 4 queries",   example_2),
    (3, "Save / load — JSON serialization",        example_3),
    (4, "PRM with intermediate waypoints",         example_4),
    (5, "Smoothing comparison — 4 levels",         example_5),
    (6, "RRT vs PRM — timing comparison",          example_6),
    (7, "Clearance-weighted — corridor corners",   example_7),
]


def run_examples():
    """Interactive example picker."""
    while True:
        print(f"\n{'=' * 55}")
        print("  PRM Motion Planning Examples")
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
