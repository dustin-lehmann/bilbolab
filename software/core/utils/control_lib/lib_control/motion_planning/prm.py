"""
Probabilistic Roadmap (PRM) Planner for multi-query path planning.

PRM pre-builds a graph (roadmap) of collision-free configurations in a static
environment.  Once built, any start/goal pair can be connected to the roadmap
and solved with a fast graph search (Dijkstra) instead of re-running a
sampling-based planner from scratch.

This is ideal for static testbed environments where the obstacle layout does
not change between queries — the roadmap is built once (or loaded from disk)
and reused for many path requests near-instantly.

Usage:
    from core.utils.control_lib.lib_control.motion_planning import (
        PRMRoadmap, PRMConfig, plan_path_prm, plot_roadmap,
        Bounds, CircleObstacle,
    )

    # Build roadmap once
    rm = PRMRoadmap(
        obstacles=[CircleObstacle(1.5, 1.5, 0.3)],
        bounds=Bounds(0, 3, 0, 3),
    )
    rm.build()

    # Query many times (fast!)
    path1 = rm.query((0.3, 0.3), (2.7, 2.7))
    path2 = rm.query((0.5, 2.5), (2.5, 0.5))

    # Save / load for later use
    rm.save('/tmp/roadmap.json')
    rm2 = PRMRoadmap.load('/tmp/roadmap.json')
"""

import dataclasses
import heapq
import json
import math
import random

import numpy as np

from .common import (
    OBSTACLE_MARGIN, Bounds, BoxObstacle, CircleObstacle, Obstacle,
    StateConstraints, Waypoint,
    _bounds_to_walls, _dist, _draw_box_patch, _edge_clearance_cost,
    _ensure_spline_safety,
    _line_collides, _optimize_connection_points, _point_collides, _prune_path,
    _state_constraints_to_walls, _subdivide_polyline,
    _uniform_resample, _waypoint_zone_radius,
)


@dataclasses.dataclass
class PRMConfig:
    """Configuration for PRM roadmap construction.

    Parameters
    ----------
    n_samples : int
        Number of random collision-free nodes to sample in the roadmap.
        More nodes → better coverage but slower build.
    k_neighbors : int
        Maximum number of nearest neighbors to attempt connecting per node.
    connection_radius : float
        Maximum edge length [m]. Edges longer than this are not attempted.
    margin : float
        Obstacle clearance [m] used during collision checking.
    clearance_weight : float
        Obstacle proximity penalty added to edge weights.  0.0 = standard
        distance-only weights (default).  Higher values make the planner
        prefer paths that stay away from obstacles.
    clearance_threshold : float
        Distance [m] below which the clearance penalty activates.  Edges
        whose sampled points are all farther than this from any obstacle
        receive zero penalty.
    seed : int | None
        RNG seed for reproducible roadmap construction.
    """
    n_samples: int = 500
    k_neighbors: int = 10
    connection_radius: float = 1.0
    margin: float = OBSTACLE_MARGIN
    clearance_weight: float = 0.0
    clearance_threshold: float = 0.5
    seed: int | None = None


def _build_prm_worker(obstacles, bounds, config, result_queue):
    """Subprocess target for PRMRoadmap.build_mp()."""
    rm = PRMRoadmap(obstacles, bounds, config)
    rm.build()
    result_queue.put((rm._nodes, rm._adj))


class PRMRoadmap:
    """Probabilistic Roadmap for multi-query path planning in static environments.

    Build the roadmap once for a given obstacle layout, then query it
    repeatedly with different start/goal pairs.  Each query runs Dijkstra
    on the pre-built graph, which is orders of magnitude faster than
    re-running RRT.

    Parameters
    ----------
    obstacles : list[Obstacle]
        Circle and box obstacles in the workspace.
    bounds : Bounds
        Workspace limits.
    config : PRMConfig, optional
        Roadmap construction parameters.  Uses defaults if not given.
    """

    def __init__(self, obstacles: list[Obstacle], bounds: Bounds,
                 config: PRMConfig | None = None):
        self.obstacles = list(obstacles) if obstacles else []
        self.bounds = bounds
        self.config = config or PRMConfig()

        # Internal graph representation
        self._nodes: list[tuple[float, float]] = []
        # Adjacency list: node_id → [(neighbor_id, weight), ...]
        self._adj: dict[int, list[tuple[int, float]]] = {}
        self._built = False

        # All obstacles including walls (for collision checks)
        self._all_obstacles = self.obstacles + _bounds_to_walls(bounds)

    def build(self) -> None:
        """Sample nodes and connect neighbors.  Call once per environment."""
        cfg = self.config
        rng = random.Random(cfg.seed)
        margin = cfg.margin

        # Step 1: Sample N collision-free points uniformly in bounds
        nodes: list[tuple[float, float]] = []
        max_attempts = cfg.n_samples * 20  # avoid infinite loop
        attempts = 0
        while len(nodes) < cfg.n_samples and attempts < max_attempts:
            x = rng.uniform(self.bounds.x_min, self.bounds.x_max)
            y = rng.uniform(self.bounds.y_min, self.bounds.y_max)
            if not _point_collides(x, y, self._all_obstacles, margin):
                nodes.append((x, y))
            attempts += 1

        self._nodes = nodes
        n = len(nodes)

        # Step 2: Build adjacency list
        adj: dict[int, list[tuple[int, float]]] = {i: [] for i in range(n)}

        # For each node, find k nearest neighbors and attempt connection
        for i in range(n):
            # Compute distances to all other nodes
            dists = []
            for j in range(n):
                if j == i:
                    continue
                d = _dist(nodes[i], nodes[j])
                if d <= cfg.connection_radius:
                    dists.append((d, j))

            # Sort by distance, take k nearest
            dists.sort()
            candidates = dists[:cfg.k_neighbors]

            for d, j in candidates:
                # Check if edge already exists (avoid duplicates)
                if any(nb_id == j for nb_id, _ in adj[i]):
                    continue

                # Attempt straight-line connection
                if not _line_collides(nodes[i], nodes[j],
                                      self._all_obstacles, margin):
                    w = d + _edge_clearance_cost(
                        nodes[i], nodes[j], self._all_obstacles,
                        cfg.clearance_weight, cfg.clearance_threshold)
                    adj[i].append((j, w))
                    adj[j].append((i, w))

        self._adj = adj
        self._built = True

    def build_mp(self, timeout: float = 30.0) -> None:
        """Build the roadmap in a separate process (does not block the GIL).

        Spawns a child process that runs ``build()``, then transfers the
        resulting graph back.  The calling thread blocks on
        ``result.get(timeout)`` but releases the GIL while waiting, so
        the 100 Hz control loop keeps running.

        Parameters
        ----------
        timeout : float
            Maximum wall-clock seconds to wait for the build process.
            Raises ``TimeoutError`` if exceeded.
        """
        import multiprocessing as mp

        result_queue = mp.Queue()
        proc = mp.Process(
            target=_build_prm_worker,
            args=(self.obstacles, self.bounds, self.config, result_queue),
            daemon=True,
        )
        proc.start()
        try:
            self._nodes, self._adj = result_queue.get(timeout=timeout)
            self._built = True
        except Exception:
            proc.kill()
            raise TimeoutError(
                f"PRM build did not complete within {timeout}s"
            )
        finally:
            proc.join(timeout=2.0)
            if proc.is_alive():
                proc.kill()

    def query(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        waypoints: list[Waypoint] | None = None,
        smoothing: float = 1.0,
        padding: float = 0.0,
        state_constraints: StateConstraints | None = None,
        target_heading: float | None = None,
        heading_strength: float = 1.0,
    ) -> list[tuple[float, float]]:
        """Find a path through the roadmap from start to end.

        Waypoints are handled with the same zone-based approach as the RRT
        planner: each waypoint defines a proximity zone (radius determined
        by its weight).  The path must pass *through* the zone but not
        necessarily through the exact center.  After initial routing, the
        zone entry points are optimized to minimize total path length.

        Parameters
        ----------
        start : (x, y)
            Start position.
        end : (x, y)
            End position.
        waypoints : list[Waypoint], optional
            Intermediate waypoints with proximity weights.
            weight=0: large zone (path can pass far from waypoint)
            weight=1: tight zone (path must pass close)
            stop=True: path must pass through exactly
        smoothing : float
            Spline smoothing factor [0, 1]. 1.0 = maximum smoothing.
        padding : float
            Robot half-width [m], inflates obstacles during post-processing.
        state_constraints : StateConstraints, optional
            Per-axis position constraints.
        target_heading : float or None
            If given, the spline is shaped so that the path arrives at the
            endpoint with approximately this heading angle [rad].  The end
            tangent of the cubic spline is clamped to (cos(h), sin(h)).
        heading_strength : float
            Magnitude of the clamped end tangent.  Larger values create a
            longer approach corridor aligned with the target heading.
            Default 1.0.

        Returns
        -------
        list[(x, y)]
            Post-processed path (uniformly sampled, ~15mm spacing).

        Raises
        ------
        RuntimeError
            If no path can be found through the roadmap.
        """
        if not self._built:
            raise RuntimeError("Roadmap not built. Call build() first.")

        margin = self.config.margin + max(0.0, padding)

        # Build extended obstacle list for post-processing
        all_obstacles = list(self._all_obstacles)
        if state_constraints is not None:
            all_obstacles += _state_constraints_to_walls(
                state_constraints, self.bounds)

        waypoints = waypoints or []

        if not waypoints:
            raw_path = self._query_pair(start, end, margin)
        else:
            # ── Zone-based waypoint handling (mirrors RRT pipeline) ──
            # Build target sequence with zone radii
            targets = [start] + [(wp.x, wp.y) for wp in waypoints] + [end]
            zone_radii = ([0.0]
                          + [0.0 if wp.stop else _waypoint_zone_radius(wp.weight)
                             for wp in waypoints]
                          + [0.0])
            zone_centers = list(targets)

            # Phase 1: Segment-wise Dijkstra with zone goals
            # For each segment, find the shortest path that enters the
            # next waypoint's zone (not necessarily its exact center).
            connection = start
            segment_paths = []

            for i in range(len(targets) - 1):
                seg_start = connection
                seg_goal_center = targets[i + 1]
                seg_goal_radius = zone_radii[i + 1]

                seg_path = self._query_pair_zone(
                    seg_start, seg_goal_center, seg_goal_radius, margin)

                connection = seg_path[-1]
                segment_paths.append(seg_path)

            # Phase 2: Prune each segment
            pruned_segments = [_prune_path(seg, all_obstacles, margin)
                               for seg in segment_paths]

            # Extract connection points (where path enters each zone)
            conn_points = [pruned_segments[0][0]]
            for seg in pruned_segments:
                conn_points.append(seg[-1])
            conn_points[0] = start
            conn_points[-1] = end

            # Phase 3: Optimize connection points within zones
            conn_optimized = _optimize_connection_points(
                conn_points, zone_centers, zone_radii, all_obstacles, margin)

            # Phase 4: Re-connect between optimized points
            full_path = []
            for i in range(len(conn_optimized) - 1):
                p1, p2 = conn_optimized[i], conn_optimized[i + 1]
                if _dist(p1, p2) < 1e-6:
                    segment = [p1]
                elif not _line_collides(p1, p2, all_obstacles, margin):
                    segment = [p1, p2]
                else:
                    raw = self._query_pair(p1, p2, margin)
                    segment = _prune_path(raw, all_obstacles, margin)

                if i == 0:
                    full_path.extend(segment)
                else:
                    full_path.extend(segment[1:])

            # Deduplicate
            raw_path = [full_path[0]]
            for p in full_path[1:]:
                if _dist(raw_path[-1], p) > 1e-6:
                    raw_path.append(p)
            if len(raw_path) < 2:
                raw_path = [start, end]

        # Post-processing: spline smooth → uniform resample
        # When waypoints are present, the waypoint pipeline (phases 1-4) already
        # handled per-segment pruning and connection point optimization.  A global
        # prune here would shortcut through waypoint detours whenever a clear line
        # of sight exists between start and end.
        if waypoints:
            pruned = raw_path
        else:
            pruned = _prune_path(raw_path, all_obstacles, margin)

        smoothing = max(0.0, min(1.0, smoothing))
        polyline = list(pruned)

        if smoothing < 1.0 and len(polyline) >= 2:
            ds_knot = 0.01 + smoothing * 0.49
            polyline = _subdivide_polyline(polyline, ds_knot)

        cs_x, cs_y, L, _ = _ensure_spline_safety(
            polyline, all_obstacles, margin=margin,
            target_heading=target_heading,
            heading_strength=heading_strength)

        if cs_x is None:
            return pruned

        # Insert exact stop points for stop-waypoints
        stop_arc_lengths = []
        if waypoints:
            for wp in waypoints:
                if wp.stop:
                    n_search = max(int(L / 0.005), 200)
                    ts = np.linspace(0, L, n_search)
                    dsq = (cs_x(ts) - wp.x) ** 2 + (cs_y(ts) - wp.y) ** 2
                    stop_arc_lengths.append(float(ts[int(np.argmin(dsq))]))

        final, _ = _uniform_resample(
            cs_x, cs_y, L,
            stop_arc_lengths=stop_arc_lengths if stop_arc_lengths else None,
        )
        return final

    def _query_pair_zone(
        self,
        start: tuple[float, float],
        goal_center: tuple[float, float],
        goal_radius: float,
        margin: float,
    ) -> list[tuple[float, float]]:
        """Find a raw path from start into a goal zone.

        Like _query_pair, but the goal is a circular zone — any roadmap
        node within goal_radius of goal_center counts as reaching it.
        If goal_radius <= 0, falls back to exact-point _query_pair.
        """
        if goal_radius <= 0:
            return self._query_pair(start, goal_center, margin)

        # NOTE: We intentionally do NOT shortcut to the goal center here.
        # Even if a clear line to the center exists, the optimal entry point
        # is typically on the zone edge (closest to the straight prev→next
        # line).  Dijkstra will find the shortest path to any node *inside*
        # the zone, which naturally favours the near edge.  The connection
        # point is then refined by _optimize_connection_points later.

        n = len(self._nodes)

        # Add temporary start node (exempt from obstacle checking — the
        # robot is physically at this position so it cannot be inside an
        # obstacle; apparent collisions are due to margin inflation).
        cfg = self.config
        start_id = n
        start_edges: list[tuple[int, float]] = []
        for i in range(n):
            d = _dist(start, self._nodes[i])
            if d <= cfg.connection_radius:
                if not _line_collides(start, self._nodes[i],
                                      self._all_obstacles, margin):
                    w = d + _edge_clearance_cost(
                        start, self._nodes[i], self._all_obstacles,
                        cfg.clearance_weight, cfg.clearance_threshold)
                    start_edges.append((i, w))

        # Fallback: if the start appears to be inside an inflated obstacle,
        # connect to the nearest roadmap nodes without collision checking.
        if not start_edges:
            fallback = []
            for i in range(n):
                fallback.append((_dist(start, self._nodes[i]), i))
            fallback.sort()
            for d, i in fallback[:cfg.k_neighbors]:
                start_edges.append((i, d))
            if not start_edges:
                raise RuntimeError(
                    f"PRM query: start {start} cannot connect to any "
                    f"roadmap node (roadmap has no nodes).")

        # Dijkstra — goal is ANY node within the zone
        dist: dict[int, float] = {start_id: 0.0}
        prev: dict[int, int | None] = {start_id: None}
        pq: list[tuple[float, int]] = [(0.0, start_id)]

        goal_radius_sq = goal_radius * goal_radius

        while pq:
            d_u, u = heapq.heappop(pq)

            # Check if this node is inside the goal zone
            if u != start_id:
                node_pos = self._nodes[u]
                if ((node_pos[0] - goal_center[0]) ** 2
                        + (node_pos[1] - goal_center[1]) ** 2
                        <= goal_radius_sq):
                    # Reached the zone — reconstruct path
                    path_ids = []
                    cur = u
                    while cur is not None:
                        path_ids.append(cur)
                        cur = prev.get(cur)
                    path_ids.reverse()
                    path = []
                    for pid in path_ids:
                        if pid == start_id:
                            path.append(start)
                        else:
                            path.append(self._nodes[pid])
                    return path

            if d_u > dist.get(u, float('inf')):
                continue

            # Expand neighbors
            if u == start_id:
                neighbors = start_edges
            else:
                neighbors = self._adj.get(u, [])

            for v, w in neighbors:
                d_v = d_u + w
                if d_v < dist.get(v, float('inf')):
                    dist[v] = d_v
                    prev[v] = u
                    heapq.heappush(pq, (d_v, v))

        # No roadmap node found in zone — fall back to exact query
        return self._query_pair(start, goal_center, margin)

    def _query_pair(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        margin: float,
    ) -> list[tuple[float, float]]:
        """Find a raw path between two points through the roadmap."""
        # Try direct connection first
        if not _line_collides(start, end, self._all_obstacles, margin):
            return [start, end]

        n = len(self._nodes)

        # Add temporary start node (exempt from obstacle checking — the
        # robot is physically at this position so it cannot be inside an
        # obstacle; apparent collisions are due to margin inflation).
        cfg = self.config
        start_id = n
        start_edges: list[tuple[int, float]] = []
        for i in range(n):
            d = _dist(start, self._nodes[i])
            if d <= cfg.connection_radius:
                if not _line_collides(start, self._nodes[i],
                                      self._all_obstacles, margin):
                    w = d + _edge_clearance_cost(
                        start, self._nodes[i], self._all_obstacles,
                        cfg.clearance_weight, cfg.clearance_threshold)
                    start_edges.append((i, w))

        # Fallback: if the start appears to be inside an inflated obstacle,
        # connect to the nearest roadmap nodes without collision checking.
        if not start_edges:
            fallback = []
            for i in range(n):
                fallback.append((_dist(start, self._nodes[i]), i))
            fallback.sort()
            for d, i in fallback[:cfg.k_neighbors]:
                start_edges.append((i, d))

        # Add temporary end node
        end_id = n + 1
        end_edges: list[tuple[int, float]] = []
        for i in range(n):
            d = _dist(end, self._nodes[i])
            if d <= cfg.connection_radius:
                if not _line_collides(end, self._nodes[i],
                                      self._all_obstacles, margin):
                    end_edges.append((i, d + _edge_clearance_cost(
                        end, self._nodes[i], self._all_obstacles,
                        cfg.clearance_weight, cfg.clearance_threshold)))

        # Check direct start→end through roadmap connection
        d_direct = _dist(start, end)
        if d_direct <= self.config.connection_radius:
            if not _line_collides(start, end, self._all_obstacles, margin):
                return [start, end]

        if not start_edges:
            raise RuntimeError(
                f"PRM query: start {start} cannot connect to any roadmap node "
                f"(roadmap has no nodes).")
        if not end_edges:
            raise RuntimeError(
                f"PRM query: end {end} cannot connect to any roadmap node. "
                f"Try increasing connection_radius or n_samples.")

        # Dijkstra with temporary nodes
        # dist[node_id] = shortest distance from start_id
        dist: dict[int, float] = {start_id: 0.0}
        prev: dict[int, int | None] = {start_id: None}
        # Priority queue: (distance, node_id)
        pq: list[tuple[float, int]] = [(0.0, start_id)]

        def _get_neighbors(node_id: int) -> list[tuple[int, float]]:
            if node_id == start_id:
                return start_edges
            elif node_id == end_id:
                return []  # end is a sink
            else:
                # Regular node: its normal edges + check if connected to end
                edges = list(self._adj.get(node_id, []))
                # Also check if this node can reach end
                node_pos = self._nodes[node_id]
                d_to_end = _dist(node_pos, end)
                if d_to_end <= cfg.connection_radius:
                    if not _line_collides(node_pos, end,
                                          self._all_obstacles, margin):
                        w_to_end = d_to_end + _edge_clearance_cost(
                            node_pos, end, self._all_obstacles,
                            cfg.clearance_weight, cfg.clearance_threshold)
                        edges.append((end_id, w_to_end))
                return edges

        while pq:
            d_u, u = heapq.heappop(pq)

            if u == end_id:
                # Reconstruct path
                path_ids = []
                cur = end_id
                while cur is not None:
                    path_ids.append(cur)
                    cur = prev.get(cur)
                path_ids.reverse()

                # Convert IDs to coordinates
                path = []
                for pid in path_ids:
                    if pid == start_id:
                        path.append(start)
                    elif pid == end_id:
                        path.append(end)
                    else:
                        path.append(self._nodes[pid])
                return path

            if d_u > dist.get(u, float('inf')):
                continue

            for v, w in _get_neighbors(u):
                d_v = d_u + w
                if d_v < dist.get(v, float('inf')):
                    dist[v] = d_v
                    prev[v] = u
                    heapq.heappush(pq, (d_v, v))

        raise RuntimeError(
            f"PRM query: no path found from {start} to {end}. "
            f"The roadmap may be disconnected. Try increasing n_samples "
            f"or connection_radius.")

    def save(self, filepath: str) -> None:
        """Save roadmap to a JSON file.

        Stores nodes, edges, obstacles, bounds, and config so the roadmap
        can be reloaded without rebuilding.
        """
        if not self._built:
            raise RuntimeError("Roadmap not built. Call build() first.")

        # Serialize obstacles
        obs_list = []
        for obs in self.obstacles:
            if isinstance(obs, CircleObstacle):
                obs_list.append({
                    'type': 'circle',
                    'cx': obs.cx, 'cy': obs.cy, 'radius': obs.radius,
                })
            elif isinstance(obs, BoxObstacle):
                obs_list.append({
                    'type': 'box',
                    'cx': obs.cx, 'cy': obs.cy,
                    'width': obs.width, 'height': obs.height,
                    'psi': obs.psi,
                })

        # Serialize edges as [i, j, weight]
        edge_set: set[tuple[int, int]] = set()
        edges_list = []
        for i, neighbors in self._adj.items():
            for j, w in neighbors:
                key = (min(i, j), max(i, j))
                if key not in edge_set:
                    edge_set.add(key)
                    edges_list.append([key[0], key[1], w])

        data = {
            'version': 1,
            'nodes': self._nodes,
            'edges': edges_list,
            'obstacles': obs_list,
            'bounds': {
                'x_min': self.bounds.x_min,
                'x_max': self.bounds.x_max,
                'y_min': self.bounds.y_min,
                'y_max': self.bounds.y_max,
            },
            'config': {
                'n_samples': self.config.n_samples,
                'k_neighbors': self.config.k_neighbors,
                'connection_radius': self.config.connection_radius,
                'margin': self.config.margin,
                'clearance_weight': self.config.clearance_weight,
                'clearance_threshold': self.config.clearance_threshold,
                'seed': self.config.seed,
            },
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "PRMRoadmap":
        """Load a roadmap from a JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Deserialize obstacles
        obstacles: list[Obstacle] = []
        for obs_d in data['obstacles']:
            if obs_d['type'] == 'circle':
                obstacles.append(CircleObstacle(
                    obs_d['cx'], obs_d['cy'], obs_d['radius']))
            elif obs_d['type'] == 'box':
                obstacles.append(BoxObstacle(
                    obs_d['cx'], obs_d['cy'],
                    obs_d['width'], obs_d['height'],
                    obs_d.get('psi', 0.0)))

        # Deserialize bounds
        b = data['bounds']
        bounds = Bounds(b['x_min'], b['x_max'], b['y_min'], b['y_max'])

        # Deserialize config
        cfg_d = data['config']
        config = PRMConfig(
            n_samples=cfg_d['n_samples'],
            k_neighbors=cfg_d['k_neighbors'],
            connection_radius=cfg_d['connection_radius'],
            margin=cfg_d['margin'],
            clearance_weight=cfg_d.get('clearance_weight', 0.0),
            clearance_threshold=cfg_d.get('clearance_threshold', 0.5),
            seed=cfg_d.get('seed'),
        )

        # Create roadmap instance
        rm = cls(obstacles, bounds, config)

        # Restore nodes
        rm._nodes = [tuple(n) for n in data['nodes']]

        # Restore adjacency list
        n = len(rm._nodes)
        adj: dict[int, list[tuple[int, float]]] = {i: [] for i in range(n)}
        for edge in data['edges']:
            i, j, w = int(edge[0]), int(edge[1]), float(edge[2])
            adj[i].append((j, w))
            adj[j].append((i, w))
        rm._adj = adj
        rm._built = True

        return rm

    @property
    def node_count(self) -> int:
        """Number of nodes in the roadmap."""
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """Number of unique edges in the roadmap."""
        total = sum(len(neighbors) for neighbors in self._adj.values())
        return total // 2  # each edge counted twice (undirected)

    def is_built(self) -> bool:
        """Whether the roadmap has been built."""
        return self._built


def plan_path_prm(
    roadmap: PRMRoadmap,
    start: tuple[float, float],
    end: tuple[float, float],
    waypoints: list[Waypoint] | None = None,
    smoothing: float = 1.0,
    padding: float = 0.0,
    target_heading: float | None = None,
    heading_strength: float = 1.0,
) -> list[tuple[float, float]]:
    """One-shot query wrapper around PRMRoadmap.query().

    Parameters
    ----------
    roadmap : PRMRoadmap
        A built roadmap.
    start, end : (x, y)
        Start and end positions.
    waypoints : list[Waypoint], optional
        Intermediate waypoints to visit in order.
    smoothing : float
        Spline smoothing [0, 1].
    padding : float
        Robot half-width [m].
    target_heading : float or None
        Desired arrival heading [rad] at the endpoint.
    heading_strength : float
        Magnitude of the clamped end tangent.  Default 1.0.

    Returns
    -------
    list[(x, y)]
        Post-processed path.
    """
    return roadmap.query(start, end, waypoints=waypoints,
                         smoothing=smoothing, padding=padding,
                         target_heading=target_heading,
                         heading_strength=heading_strength)


def plot_roadmap(
    roadmap: PRMRoadmap,
    path: list[tuple[float, float]] | None = None,
    start: tuple[float, float] | None = None,
    end: tuple[float, float] | None = None,
    waypoints: list[Waypoint] | None = None,
    title: str = "PRM Roadmap",
    figsize: tuple[float, float] = (10, 10),
):
    """Visualize the PRM roadmap, optionally with a query result.

    Parameters
    ----------
    roadmap : PRMRoadmap
        The roadmap to visualize.
    path : list[(x, y)], optional
        A query result path to overlay.
    start, end : (x, y), optional
        Start and end positions to mark.
    waypoints : list[Waypoint], optional
        Waypoints to show.
    title : str
        Plot title.
    figsize : tuple
        Figure size.

    Returns
    -------
    (fig, ax)
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    fig, ax = plt.subplots(1, 1, figsize=figsize)
    ax.set_aspect('equal')
    ax.set_title(title, fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.2)

    b = roadmap.bounds
    plot_margin = 0.2
    ax.set_xlim(b.x_min - plot_margin, b.x_max + plot_margin)
    ax.set_ylim(b.y_min - plot_margin, b.y_max + plot_margin)

    # Bounds rectangle
    rect = patches.Rectangle(
        (b.x_min, b.y_min), b.x_max - b.x_min, b.y_max - b.y_min,
        linewidth=1.5, edgecolor='#2d3436', facecolor='none',
        linestyle='--', alpha=0.5)
    ax.add_patch(rect)

    # Obstacles
    for obs in roadmap.obstacles:
        if isinstance(obs, CircleObstacle):
            c = patches.Circle(
                (obs.cx, obs.cy), obs.radius,
                facecolor='#ff6b6b', edgecolor='#c0392b',
                alpha=0.5, linewidth=1)
            ax.add_patch(c)
        elif isinstance(obs, BoxObstacle):
            _draw_box_patch(ax, obs, alpha=0.5, linewidth=1)

    # Roadmap edges
    if roadmap.is_built():
        from matplotlib.collections import LineCollection
        edge_set: set[tuple[int, int]] = set()
        segments = []
        for i, neighbors in roadmap._adj.items():
            for j, _ in neighbors:
                key = (min(i, j), max(i, j))
                if key not in edge_set:
                    edge_set.add(key)
                    p1 = roadmap._nodes[i]
                    p2 = roadmap._nodes[j]
                    segments.append([(p1[0], p1[1]), (p2[0], p2[1])])
        if segments:
            lc = LineCollection(segments, colors='#b2bec3', alpha=0.4,
                                linewidths=0.6, zorder=2)
            ax.add_collection(lc)

        # Roadmap nodes
        node_xs = [n[0] for n in roadmap._nodes]
        node_ys = [n[1] for n in roadmap._nodes]
        ax.scatter(node_xs, node_ys, c='#636e72', s=8, alpha=0.5,
                   zorder=3, edgecolors='none', label=f'Nodes ({len(node_xs)})')

    # Waypoint zones
    if waypoints:
        for wp in waypoints:
            r = _waypoint_zone_radius(wp.weight)
            zone = patches.Circle(
                (wp.x, wp.y), r,
                facecolor='#74b9ff', edgecolor='#0984e3',
                alpha=0.15, linewidth=1, linestyle='--')
            ax.add_patch(zone)
            ax.plot(wp.x, wp.y, 'o', color='#0984e3', markersize=6, zorder=5)

    # Path overlay
    if path and len(path) >= 2:
        xs = [p[0] for p in path]
        ys = [p[1] for p in path]
        ax.plot(xs, ys, '-', color='#2d3436', linewidth=2, zorder=6,
                label='Path')
        ax.scatter(xs, ys, c='#2d3436', s=4, zorder=7, edgecolors='none')

    # Start / End markers
    if start:
        ax.plot(start[0], start[1], 's', color='#00b894',
                markersize=10, zorder=8, label='Start')
    if end:
        ax.plot(end[0], end[1], '*', color='#d63031',
                markersize=14, zorder=8, label='End')

    # Stats annotation
    if roadmap.is_built():
        ax.text(
            0.02, 0.02,
            f'Nodes: {roadmap.node_count}\n'
            f'Edges: {roadmap.edge_count}',
            transform=ax.transAxes, fontsize=8, verticalalignment='bottom',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.legend(loc='upper right', fontsize=8)
    ax.set_xlabel('x [m]')
    ax.set_ylabel('y [m]')
    plt.tight_layout()
    plt.show()
    return fig, ax
