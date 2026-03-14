"""
Shared types, geometry, post-processing, and visualization for motion planning.

This module contains everything that is common across different planners
(RRT, PRM, etc.):
- Data structures (Waypoint, obstacles, Bounds, PlanResult, ...)
- Constants (margins, sampling parameters, ...)
- Geometry and collision utilities
- Clearance cost utilities
- Path post-processing (pruning, optimization, spline fitting, resampling)
- Visualization helpers (drawing obstacles, backgrounds, standalone path plot)
"""

import dataclasses
import math
from typing import Union

import numpy as np
from scipy.interpolate import CubicSpline

# ============================================================================
# Parameters
# ============================================================================

# Waypoint zone radii
WAYPOINT_RADIUS_MIN = 0.05   # [m] zone radius at weight=1 (must get close)
WAYPOINT_RADIUS_MAX = 3.0    # [m] zone radius at weight=0 (can pass far)

# Safety
OBSTACLE_MARGIN = 0.05       # [m] clearance around obstacles

# Adaptive output sampling
SAMPLE_DS_MIN = 0.005        # [m] min sample spacing (tight curves)
SAMPLE_DS_MAX = 0.10         # [m] max sample spacing (straight segments)
SAMPLE_CURVATURE_GAIN = 2.0  # curvature sensitivity for step size

# Optimization
OPTIMIZATION_ITERATIONS = 5  # rounds of waypoint position relaxation

# Uniform output spacing
UNIFORM_DS = 0.015  # [m] Default uniform spacing for path output (~15mm)

# ============================================================================
# Data Structures
# ============================================================================

@dataclasses.dataclass
class Waypoint:
    """Waypoint with proximity weight.
    weight=0 → large zone (WAYPOINT_RADIUS_MAX), path can pass far
    weight=1 → tight zone (WAYPOINT_RADIUS_MIN), path must pass close
    stop=True → STOP waypoint: zone_radius forced to 0 so spline passes
    through it exactly, and the planner inserts deceleration ramps.
    """
    x: float
    y: float
    weight: float = 0.5
    stop: bool = False


@dataclasses.dataclass
class CircleObstacle:
    cx: float
    cy: float
    radius: float


@dataclasses.dataclass
class BoxObstacle:
    """Box defined by center, full dimensions, and rotation angle.

    Parameters
    ----------
    cx, cy : float
        Center of the box.
    width : float
        Full extent along the box's local x-axis.
    height : float
        Full extent along the box's local y-axis.
    psi : float
        Rotation angle in radians around the center (counterclockwise).
        Default 0.0 gives an axis-aligned box.
    """
    cx: float
    cy: float
    width: float
    height: float
    psi: float = 0.0


@dataclasses.dataclass
class Bounds:
    """Workspace limits. Treated as 4 wall obstacles internally."""
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclasses.dataclass
class StateConstraints:
    """Optional per-axis position constraints.
    Only specified limits (non-None) are enforced as wall obstacles."""
    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None


Obstacle = Union[CircleObstacle, BoxObstacle]


@dataclasses.dataclass
class PlanResult:
    """All intermediate stages from the planning pipeline (debug mode)."""
    path: list                  # final adaptively sampled path
    # Problem definition
    start: tuple
    end: tuple
    waypoints: list
    obstacles: list
    bounds: 'Bounds'
    padding: float              # robot padding used for planning
    state_constraints: 'StateConstraints | None'  # per-axis position constraints
    # Phase 1: raw RRT / straight-line paths per segment
    rrt_trees: list             # [[(p1,p2), ...], ...] tree edges per segment
    rrt_paths: list             # [[(x,y), ...], ...]   solution path per segment
    # Phase 2: after pruning
    pruned_paths: list          # [[(x,y), ...], ...]   pruned path per segment
    # Connection points
    connection_points_before: list   # before optimization
    connection_points_after: list    # after optimization
    # Phase 3: merged polyline after re-planning
    polyline: list              # [(x,y), ...] full polyline before spline
    # Phase 4: spline curve (densely sampled for plotting)
    spline_curve: list          # [(x,y), ...] uniform dense samples


# ============================================================================
# Geometry & Collision Utilities
# ============================================================================

def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _waypoint_zone_radius(weight: float) -> float:
    """Zone radius from weight. Higher weight → smaller radius."""
    w = max(0.0, min(1.0, weight))
    return WAYPOINT_RADIUS_MAX - w * (WAYPOINT_RADIUS_MAX - WAYPOINT_RADIUS_MIN)


def _seg_point_dist(p1, p2, cx, cy) -> float:
    """Minimum distance from line segment p1→p2 to point (cx, cy)."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return math.hypot(cx - p1[0], cy - p1[1])
    t = max(0.0, min(1.0, ((cx - p1[0]) * dx + (cy - p1[1]) * dy) / len_sq))
    return math.hypot(cx - (p1[0] + t * dx), cy - (p1[1] + t * dy))


def _seg_intersects_aabb(p1, p2, xmin, ymin, xmax, ymax) -> bool:
    """Liang-Barsky line segment vs AABB intersection test."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    t0, t1 = 0.0, 1.0
    for origin, delta, lo, hi in [(p1[0], dx, xmin, xmax),
                                   (p1[1], dy, ymin, ymax)]:
        if abs(delta) < 1e-12:
            if origin < lo or origin > hi:
                return False
        else:
            ta = (lo - origin) / delta
            tb = (hi - origin) / delta
            if ta > tb:
                ta, tb = tb, ta
            t0 = max(t0, ta)
            t1 = min(t1, tb)
            if t0 > t1:
                return False
    return True


def _rotate_to_local(px, py, cx, cy, cos_psi, sin_psi):
    """Transform point (px, py) into the local frame of a box at (cx, cy)
    rotated by psi. cos_psi and sin_psi are precomputed."""
    dx = px - cx
    dy = py - cy
    # Inverse rotation (rotate by -psi)
    lx = cos_psi * dx + sin_psi * dy
    ly = -sin_psi * dx + cos_psi * dy
    return lx, ly


def _point_collides(px, py, obstacles: list[Obstacle],
                    margin: float = OBSTACLE_MARGIN) -> bool:
    for obs in obstacles:
        if isinstance(obs, CircleObstacle):
            if ((px - obs.cx) ** 2 + (py - obs.cy) ** 2
                    <= (obs.radius + margin) ** 2):
                return True
        elif isinstance(obs, BoxObstacle):
            cos_psi = math.cos(obs.psi)
            sin_psi = math.sin(obs.psi)
            lx, ly = _rotate_to_local(px, py, obs.cx, obs.cy, cos_psi, sin_psi)
            if (abs(lx) <= obs.width / 2 + margin
                    and abs(ly) <= obs.height / 2 + margin):
                return True
    return False


def _line_collides(p1, p2, obstacles: list[Obstacle],
                   margin: float = OBSTACLE_MARGIN) -> bool:
    """Check if line segment p1→p2 intersects any obstacle (with margin)."""
    for obs in obstacles:
        if isinstance(obs, CircleObstacle):
            if _seg_point_dist(p1, p2, obs.cx, obs.cy) <= obs.radius + margin:
                return True
        elif isinstance(obs, BoxObstacle):
            hw = obs.width / 2 + margin
            hh = obs.height / 2 + margin
            # Transform segment endpoints into the box's local frame
            cos_psi = math.cos(obs.psi)
            sin_psi = math.sin(obs.psi)
            lp1 = _rotate_to_local(p1[0], p1[1], obs.cx, obs.cy, cos_psi, sin_psi)
            lp2 = _rotate_to_local(p2[0], p2[1], obs.cx, obs.cy, cos_psi, sin_psi)
            if _seg_intersects_aabb(lp1, lp2, -hw, -hh, hw, hh):
                return True
    return False


def _bounds_to_walls(bounds: Bounds) -> list[BoxObstacle]:
    """Convert workspace bounds to 4 thick wall obstacles."""
    wt = 1.0  # wall thickness [m]
    w = bounds.x_max - bounds.x_min
    h = bounds.y_max - bounds.y_min
    mx = (bounds.x_min + bounds.x_max) / 2
    my = (bounds.y_min + bounds.y_max) / 2
    return [
        BoxObstacle(mx, bounds.y_min - wt / 2, w + 2 * wt, wt),  # bottom
        BoxObstacle(mx, bounds.y_max + wt / 2, w + 2 * wt, wt),  # top
        BoxObstacle(bounds.x_min - wt / 2, my, wt, h + 2 * wt),  # left
        BoxObstacle(bounds.x_max + wt / 2, my, wt, h + 2 * wt),  # right
    ]


def _state_constraints_to_walls(constraints: StateConstraints,
                                bounds: Bounds) -> list[BoxObstacle]:
    """Convert per-axis state constraints to wall obstacles."""
    walls = []
    wt = 1.0  # wall thickness
    w = bounds.x_max - bounds.x_min
    h = bounds.y_max - bounds.y_min
    mx = (bounds.x_min + bounds.x_max) / 2
    my = (bounds.y_min + bounds.y_max) / 2
    if constraints.x_min is not None:
        walls.append(BoxObstacle(constraints.x_min - wt / 2, my, wt, h + 2 * wt))
    if constraints.x_max is not None:
        walls.append(BoxObstacle(constraints.x_max + wt / 2, my, wt, h + 2 * wt))
    if constraints.y_min is not None:
        walls.append(BoxObstacle(mx, constraints.y_min - wt / 2, w + 2 * wt, wt))
    if constraints.y_max is not None:
        walls.append(BoxObstacle(mx, constraints.y_max + wt / 2, w + 2 * wt, wt))
    return walls


# ============================================================================
# Clearance Cost Utilities
# ============================================================================

def _min_clearance(px, py, obstacles):
    """Minimum distance from point (px, py) to the nearest obstacle surface."""
    min_d = float('inf')
    for obs in obstacles:
        if isinstance(obs, CircleObstacle):
            d = math.hypot(px - obs.cx, py - obs.cy) - obs.radius
        elif isinstance(obs, BoxObstacle):
            cos_psi = math.cos(obs.psi)
            sin_psi = math.sin(obs.psi)
            lx, ly = _rotate_to_local(px, py, obs.cx, obs.cy, cos_psi, sin_psi)
            dx = abs(lx) - obs.width / 2
            dy = abs(ly) - obs.height / 2
            if dx <= 0 and dy <= 0:
                d = max(dx, dy)
            else:
                d = math.hypot(max(dx, 0.0), max(dy, 0.0))
        else:
            continue
        min_d = min(min_d, d)
    return min_d


def _edge_clearance_cost(p1, p2, obstacles, weight, threshold):
    """Additional clearance-based cost for a tree edge.

    Samples points along the edge and penalizes proximity to obstacles.
    Points closer than *threshold* to any obstacle surface receive a
    quadratic penalty.  Returns 0.0 immediately when weight <= 0.

    cost = weight * avg_penalty * edge_length
    """
    edge_len = _dist(p1, p2)
    if edge_len < 1e-9 or weight <= 0:
        return 0.0

    n_samples = 5
    total_penalty = 0.0
    for i in range(n_samples + 1):
        t = i / n_samples
        px = p1[0] + t * (p2[0] - p1[0])
        py = p1[1] + t * (p2[1] - p1[1])
        clearance = _min_clearance(px, py, obstacles)
        if clearance < threshold:
            normalized = (threshold - clearance) / threshold
            total_penalty += normalized * normalized
    avg_penalty = total_penalty / (n_samples + 1)

    return weight * avg_penalty * edge_len


# ============================================================================
# Path Pruning
# ============================================================================

def _prune_path(path, obstacles, margin=OBSTACLE_MARGIN):
    """
    Greedy path pruning (shortcutting).

    The raw RRT path typically has many small zig-zag steps (each ≤ RRT_STEP_SIZE).
    Most of these intermediate nodes are unnecessary — a straight line between
    distant nodes is often collision-free. Pruning removes these redundant nodes.

    Algorithm:
        1. Start at the first path node (i = 0)
        2. Try to connect directly to the LAST node in the path
        3. If that line collides, try the second-to-last, then third-to-last, etc.
        4. When a collision-free connection is found, add that node and jump there
        5. Repeat from the new position until the end is reached

    This greedy "furthest reachable" strategy produces a minimal set of
    straight-line segments that together form a collision-free polyline.
    """
    if len(path) <= 2:
        return list(path)

    result = [path[0]]
    i = 0
    while i < len(path) - 1:
        j = len(path) - 1
        while j > i + 1:
            if not _line_collides(path[i], path[j], obstacles, margin):
                break
            j -= 1
        result.append(path[j])
        i = j

    return result


# ============================================================================
# Waypoint Zone Optimization
# ============================================================================

def _optimize_connection_points(points, zone_centers, zone_radii, obstacles,
                                margin=OBSTACLE_MARGIN):
    """
    Waypoint zone optimization — minimize total path length.

    After RRT + pruning, each waypoint's connection point sits wherever the
    RRT happened to enter the waypoint's zone. This is typically not optimal.
    This function slides each connection point within its waypoint zone disk
    to shorten the total path length.

    Start and end points (zone_radius=0) are kept fixed.
    Candidates are only accepted if the connections to neighbors are collision-free.
    """
    pts = list(points)

    for _ in range(OPTIMIZATION_ITERATIONS):
        changed = False
        for i in range(1, len(pts) - 1):
            r = zone_radii[i]
            if r <= 0:
                continue

            prev, nxt = pts[i - 1], pts[i + 1]
            center = zone_centers[i]

            dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
            L2 = dx * dx + dy * dy
            if L2 < 1e-12:
                candidate = center
            else:
                t = ((center[0] - prev[0]) * dx + (center[1] - prev[1]) * dy) / L2
                t = max(0.0, min(1.0, t))
                proj = (prev[0] + t * dx, prev[1] + t * dy)
                d = _dist(proj, center)
                if d <= r:
                    candidate = proj
                else:
                    candidate = (
                        center[0] + (proj[0] - center[0]) / d * r,
                        center[1] + (proj[1] - center[1]) / d * r,
                    )

            if (not _point_collides(candidate[0], candidate[1], obstacles, margin)
                    and not _line_collides(prev, candidate, obstacles, margin)
                    and not _line_collides(candidate, nxt, obstacles, margin)):
                if _dist(candidate, pts[i]) > 1e-6:
                    pts[i] = candidate
                    changed = True

        if not changed:
            break

    return pts


# ============================================================================
# Spline Fitting & Collision Safety
# ============================================================================

def _fit_parametric_spline(points, target_heading=None, heading_strength=1.0):
    """
    Fit a parametric cubic spline through a sequence of (x, y) points.

    Parameters
    ----------
    points : list[(x, y)]
        Control points for the spline.
    target_heading : float or None
        If given, the spline's tangent at the last point is clamped to this
        heading angle [rad].  The start boundary condition remains 'natural'.
        This makes the path arrive at the endpoint with the desired heading.
    heading_strength : float
        Magnitude of the clamped end tangent vector.  Controls how far
        "upstream" the heading influence reaches.  A larger value creates a
        longer, smoother approach corridor aligned with the target heading.
        A smaller value (e.g. 0.3) only affects the very last portion of the
        path.  Default 1.0.

    Returns (cs_x, cs_y, total_arc_length) or (None, None, 0) if degenerate.
    """
    arr = np.array(points)
    seg_lengths = np.sqrt(np.sum(np.diff(arr, axis=0) ** 2, axis=1))
    t = np.concatenate([[0.0], np.cumsum(seg_lengths)])
    total = t[-1]
    if total < 1e-9:
        return None, None, 0.0

    if target_heading is not None:
        # Clamped end: set the derivative at the last knot to point in
        # the desired heading direction.  The magnitude (heading_strength)
        # controls how strongly the spline is pulled toward this direction
        # — larger values produce a longer approach corridor.
        s = max(0.0, heading_strength)
        dx_end = s * math.cos(target_heading)
        dy_end = s * math.sin(target_heading)
        bc_x = ((2, 0.0), (1, dx_end))  # natural start, clamped end
        bc_y = ((2, 0.0), (1, dy_end))
        cs_x = CubicSpline(t, arr[:, 0], bc_type=bc_x)
        cs_y = CubicSpline(t, arr[:, 1], bc_type=bc_y)
    else:
        cs_x = CubicSpline(t, arr[:, 0], bc_type='natural')
        cs_y = CubicSpline(t, arr[:, 1], bc_type='natural')

    return cs_x, cs_y, total


def _ensure_spline_safety(points, obstacles, max_rounds=5,
                          margin=OBSTACLE_MARGIN, target_heading=None,
                          heading_strength=1.0):
    """
    Fit a smooth spline through the polyline and ensure it doesn't collide.

    Iterative subdivision: if a collision is detected along the spline,
    insert the midpoint of the offending polyline segment as a new control
    point. Repeat until no collisions remain (or max_rounds exceeded).

    Parameters
    ----------
    target_heading : float or None
        If given, the spline's end tangent is clamped to this heading [rad].
    heading_strength : float
        Magnitude of the clamped end tangent (see _fit_parametric_spline).

    Returns (cs_x, cs_y, total_length, final_control_points).
    """
    pts = list(points)

    for _ in range(max_rounds):
        cs_x, cs_y, L = _fit_parametric_spline(pts, target_heading=target_heading,
                                                heading_strength=heading_strength)
        if cs_x is None:
            return None, None, 0.0, pts

        n_check = max(int(L / 0.005), 100)
        ts = np.linspace(0, L, n_check)
        xs, ys = cs_x(ts), cs_y(ts)

        collision_t = None
        for k in range(n_check):
            if _point_collides(float(xs[k]), float(ys[k]), obstacles, margin):
                collision_t = ts[k]
                break

        if collision_t is None:
            return cs_x, cs_y, L, pts

        arr = np.array(pts)
        seg_d = np.sqrt(np.sum(np.diff(arr, axis=0) ** 2, axis=1))
        seg_t = np.concatenate([[0.0], np.cumsum(seg_d)])
        seg_idx = int(np.searchsorted(seg_t, collision_t, side='right')) - 1
        seg_idx = max(0, min(seg_idx, len(pts) - 2))

        mid = (
            (pts[seg_idx][0] + pts[seg_idx + 1][0]) / 2,
            (pts[seg_idx][1] + pts[seg_idx + 1][1]) / 2,
        )
        pts.insert(seg_idx + 1, mid)

    cs_x, cs_y, L = _fit_parametric_spline(pts, target_heading=target_heading,
                                            heading_strength=heading_strength)
    return cs_x, cs_y, L, pts


# ============================================================================
# Resampling
# ============================================================================

def _adaptive_resample(cs_x, cs_y, total_length,
                       ds_min=SAMPLE_DS_MIN, ds_max=SAMPLE_DS_MAX,
                       curvature_gain=SAMPLE_CURVATURE_GAIN):
    """
    Walk along the spline with curvature-adaptive step size.

    Note: This function is no longer used in the main pipeline (replaced by
    _uniform_resample), but kept for reference and debugging.
    """
    if total_length < 1e-9:
        return [(float(cs_x(0.0)), float(cs_y(0.0)))]

    samples = []
    t = 0.0

    while t <= total_length:
        x = float(cs_x(t))
        y = float(cs_y(t))
        samples.append((x, y))

        dx = float(cs_x(t, 1))
        dy = float(cs_y(t, 1))
        ddx = float(cs_x(t, 2))
        ddy = float(cs_y(t, 2))

        speed_sq = dx * dx + dy * dy
        speed = math.sqrt(speed_sq) if speed_sq > 1e-12 else 1.0
        if speed_sq > 1e-12:
            kappa = abs(dx * ddy - dy * ddx) / (speed_sq ** 1.5)
        else:
            kappa = 0.0

        ds_euclidean = ds_min + (ds_max - ds_min) / (1.0 + curvature_gain * kappa)
        t += ds_euclidean / speed

    end_pt = (float(cs_x(total_length)), float(cs_y(total_length)))
    if not samples or _dist(samples[-1], end_pt) > 1e-6:
        samples.append(end_pt)

    return samples


def _uniform_resample(
    cs_x, cs_y, total_length,
    ds: float = UNIFORM_DS,
    stop_arc_lengths: list[float] | None = None,
) -> tuple[list[tuple[float, float]], list[int]]:
    """
    Uniformly resample the spline at constant arc-length intervals.

    Parameters
    ----------
    cs_x, cs_y : CubicSpline
        Arc-length-parameterized spline.
    total_length : float
        Total arc length of the spline.
    ds : float
        Target spacing between consecutive points [m]. Default ~15mm.
    stop_arc_lengths : list[float] | None
        Arc-length positions of STOP waypoints on the spline.

    Returns
    -------
    (points, stop_indices) : (list[(x,y)], list[int])
    """
    if total_length < 1e-9:
        return [(float(cs_x(0.0)), float(cs_y(0.0)))], []

    stops = sorted(stop_arc_lengths) if stop_arc_lengths else []

    n_samples = max(int(total_length / ds), 2)
    t_uniform = np.linspace(0, total_length, n_samples + 1)

    stop_indices = []
    if stops:
        t_list = list(t_uniform)
        for s_stop in stops:
            idx_near = int(np.argmin(np.abs(np.array(t_list) - s_stop)))
            t_list[idx_near] = s_stop
            stop_indices.append(idx_near)
        t_uniform = np.array(sorted(t_list))
        stop_indices = []
        for s_stop in stops:
            idx = int(np.argmin(np.abs(t_uniform - s_stop)))
            stop_indices.append(idx)

    x_vals = cs_x(t_uniform)
    y_vals = cs_y(t_uniform)
    points = [(float(x_vals[i]), float(y_vals[i])) for i in range(len(t_uniform))]

    return points, sorted(stop_indices)


def _speed_profile_resample(
    cs_x, cs_y, total_length,
    max_speed: float,
    decel_limit: float,
    curvature_gain: float = 2.0,
    curvature_window: float = 0.15,
    ds_min: float = SAMPLE_DS_MIN,
    ds_max: float = SAMPLE_DS_MAX,
    stop_arc_lengths: list[float] | None = None,
) -> list[tuple[float, float]]:
    """
    Legacy: Build a smooth speed profile then encode it into inter-point spacing.

    DEPRECATED — kept for backward compatibility / debugging.
    """
    points, _ = _uniform_resample(cs_x, cs_y, total_length,
                                   stop_arc_lengths=stop_arc_lengths)
    return points


def _uniform_spline_samples(cs_x, cs_y, total_length, ds=0.005):
    """Uniformly sample spline for plotting."""
    n = max(int(total_length / ds), 2)
    ts = np.linspace(0, total_length, n)
    return [(float(cs_x(t)), float(cs_y(t))) for t in ts]


def _subdivide_polyline(points, max_seg_length):
    """
    Subdivide polyline segments so no segment exceeds max_seg_length.

    Used to control the smoothing parameter: when smoothing < 1.0, the
    polyline is densely subdivided before spline fitting.
    """
    result = [points[0]]
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        seg_len = _dist(p1, p2)
        n_sub = max(1, int(math.ceil(seg_len / max_seg_length)))
        for j in range(1, n_sub + 1):
            t = j / n_sub
            result.append((
                p1[0] + t * (p2[0] - p1[0]),
                p1[1] + t * (p2[1] - p1[1]),
            ))
    return result


# ============================================================================
# Visualization Helpers
# ============================================================================

_SEGMENT_COLORS = [
    '#e17055', '#00b894', '#0984e3', '#6c5ce7', '#fdcb6e', '#e84393',
    '#00cec9', '#fab1a0', '#a29bfe', '#ffeaa7',
]


def _draw_box_patch(ax, obs: BoxObstacle, facecolor='#ff6b6b',
                    edgecolor='#c0392b', alpha=0.6, linewidth=1.5,
                    inflate=0.0):
    """Draw a (possibly rotated) BoxObstacle as a matplotlib patch.
    inflate > 0 expands width/height by 2*inflate (for padding visualization)."""
    import matplotlib.patches as patches
    import matplotlib.transforms as transforms

    w = obs.width + 2 * inflate
    h = obs.height + 2 * inflate
    r = patches.Rectangle(
        (-w / 2, -h / 2), w, h,
        facecolor=facecolor, edgecolor=edgecolor,
        alpha=alpha, linewidth=linewidth,
    )
    t = (transforms.Affine2D()
         .rotate(obs.psi)
         .translate(obs.cx, obs.cy)
         + ax.transData)
    r.set_transform(t)
    ax.add_patch(r)
    return r


def _draw_padding(ax, obstacles, padding):
    """Draw padding envelopes around obstacles."""
    import matplotlib.patches as patches

    if padding <= 0:
        return
    total = OBSTACLE_MARGIN + padding
    for obs in obstacles:
        if isinstance(obs, CircleObstacle):
            p = patches.Circle(
                (obs.cx, obs.cy), obs.radius + total,
                facecolor='#fdcb6e', edgecolor='#f39c12',
                alpha=0.15, linewidth=0.8, linestyle=':')
            ax.add_patch(p)
        elif isinstance(obs, BoxObstacle):
            _draw_box_patch(ax, obs, facecolor='#fdcb6e', edgecolor='#f39c12',
                            alpha=0.15, linewidth=0.8, inflate=total)


def _draw_state_constraints(ax, state_constraints, bounds):
    """Draw state constraint boundaries as shaded forbidden regions."""
    import matplotlib.patches as patches

    if state_constraints is None:
        return

    color = '#e17055'  # coral/orange
    b = bounds

    if state_constraints.x_min is not None:
        ax.axvline(state_constraints.x_min, color=color, linestyle='--',
                   linewidth=1.2, alpha=0.7, zorder=1)
        rect = patches.Rectangle(
            (b.x_min, b.y_min),
            state_constraints.x_min - b.x_min, b.y_max - b.y_min,
            facecolor=color, alpha=0.08, edgecolor='none')
        ax.add_patch(rect)

    if state_constraints.x_max is not None:
        ax.axvline(state_constraints.x_max, color=color, linestyle='--',
                   linewidth=1.2, alpha=0.7, zorder=1)
        rect = patches.Rectangle(
            (state_constraints.x_max, b.y_min),
            b.x_max - state_constraints.x_max, b.y_max - b.y_min,
            facecolor=color, alpha=0.08, edgecolor='none')
        ax.add_patch(rect)

    if state_constraints.y_min is not None:
        ax.axhline(state_constraints.y_min, color=color, linestyle='--',
                   linewidth=1.2, alpha=0.7, zorder=1)
        rect = patches.Rectangle(
            (b.x_min, b.y_min),
            b.x_max - b.x_min, state_constraints.y_min - b.y_min,
            facecolor=color, alpha=0.08, edgecolor='none')
        ax.add_patch(rect)

    if state_constraints.y_max is not None:
        ax.axhline(state_constraints.y_max, color=color, linestyle='--',
                   linewidth=1.2, alpha=0.7, zorder=1)
        rect = patches.Rectangle(
            (b.x_min, state_constraints.y_max),
            b.x_max - b.x_min, b.y_max - state_constraints.y_max,
            facecolor=color, alpha=0.08, edgecolor='none')
        ax.add_patch(rect)


def _draw_background(ax, result: PlanResult, title, draw_zones=True):
    """Draw obstacles, bounds, waypoint zones, start/end on an axes."""
    import matplotlib.patches as patches

    ax.set_aspect('equal')
    ax.set_title(title, fontsize=10, fontweight='bold')
    ax.grid(True, alpha=0.2)

    b = result.bounds
    plot_margin = 0.2
    ax.set_xlim(b.x_min - plot_margin, b.x_max + plot_margin)
    ax.set_ylim(b.y_min - plot_margin, b.y_max + plot_margin)

    # Bounds rectangle
    rect = patches.Rectangle(
        (b.x_min, b.y_min), b.x_max - b.x_min, b.y_max - b.y_min,
        linewidth=1.5, edgecolor='#2d3436', facecolor='none',
        linestyle='--', alpha=0.5)
    ax.add_patch(rect)

    # State constraints
    _draw_state_constraints(ax, result.state_constraints, result.bounds)

    # Padding envelopes (behind obstacles)
    if result.padding > 0:
        _draw_padding(ax, result.obstacles, result.padding)

    # Obstacles
    for obs in result.obstacles:
        if isinstance(obs, CircleObstacle):
            p = patches.Circle(
                (obs.cx, obs.cy), obs.radius,
                facecolor='#ff6b6b', edgecolor='#c0392b',
                alpha=0.5, linewidth=1)
            ax.add_patch(p)
        elif isinstance(obs, BoxObstacle):
            _draw_box_patch(ax, obs, alpha=0.5, linewidth=1)

    # Waypoint zones
    if draw_zones:
        for idx, wp in enumerate(result.waypoints):
            r = _waypoint_zone_radius(wp.weight)
            zone = patches.Circle(
                (wp.x, wp.y), r,
                facecolor='#74b9ff', edgecolor='#0984e3',
                alpha=0.12, linewidth=0.8, linestyle='--')
            ax.add_patch(zone)
            ax.plot(wp.x, wp.y, 'o', color='#0984e3', markersize=4, zorder=5)
            ax.annotate(str(idx + 1), (wp.x, wp.y),
                        textcoords="offset points", xytext=(-3, -10),
                        fontsize=7, fontweight='bold', color='#0984e3',
                        ha='center', zorder=11)

    # Start / End
    ax.plot(result.start[0], result.start[1], 's', color='#00b894',
            markersize=8, zorder=10)
    ax.plot(result.end[0], result.end[1], '*', color='#d63031',
            markersize=10, zorder=10)


def plot_path(path, start=None, end=None, waypoints=None, obstacles=None,
              bounds=None, state_constraints=None, padding=0.0,
              title="Motion Plan", figsize=(8, 8)):
    """
    Visualize the planned path with obstacles, waypoint zones, and bounds.
    Returns (fig, ax) for further customization.
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    fig, ax = plt.subplots(1, 1, figsize=figsize)
    ax.set_aspect('equal')
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    # Bounds
    if bounds:
        rect = patches.Rectangle(
            (bounds.x_min, bounds.y_min),
            bounds.x_max - bounds.x_min,
            bounds.y_max - bounds.y_min,
            linewidth=2, edgecolor='black', facecolor='none', linestyle='--',
        )
        ax.add_patch(rect)
        plot_margin = 0.3
        ax.set_xlim(bounds.x_min - plot_margin, bounds.x_max + plot_margin)
        ax.set_ylim(bounds.y_min - plot_margin, bounds.y_max + plot_margin)

    # State constraints
    if state_constraints and bounds:
        _draw_state_constraints(ax, state_constraints, bounds)

    # Padding envelopes (drawn first, behind obstacles)
    if obstacles and padding > 0:
        _draw_padding(ax, obstacles, padding)

    # Obstacles
    if obstacles:
        for obs in obstacles:
            if isinstance(obs, CircleObstacle):
                c = patches.Circle(
                    (obs.cx, obs.cy), obs.radius,
                    facecolor='#ff6b6b', edgecolor='#c0392b',
                    alpha=0.6, linewidth=1.5,
                )
                ax.add_patch(c)
            elif isinstance(obs, BoxObstacle):
                _draw_box_patch(ax, obs)

    # Waypoint zones
    if waypoints:
        for wp in waypoints:
            r = _waypoint_zone_radius(wp.weight)
            zone = patches.Circle(
                (wp.x, wp.y), r,
                facecolor='#74b9ff', edgecolor='#0984e3',
                alpha=0.15, linewidth=1, linestyle='--',
            )
            ax.add_patch(zone)
            ax.plot(wp.x, wp.y, 'o', color='#0984e3', markersize=6, zorder=5)
            ax.annotate(
                f'w={wp.weight:.1f}\nr={r:.2f}m',
                (wp.x, wp.y),
                textcoords="offset points", xytext=(10, 8),
                fontsize=7, color='#0984e3',
            )

    # Path with sample points
    if path and len(path) >= 2:
        xs = [p[0] for p in path]
        ys = [p[1] for p in path]
        ax.plot(xs, ys, '-', color='#2d3436', linewidth=1.5,
                zorder=3, label='Path')
        ax.scatter(xs, ys, c='#636e72', s=3, zorder=4, label='Samples')

    # Start / End markers
    if start:
        ax.plot(start[0], start[1], 's', color='#00b894',
                markersize=10, zorder=6, label='Start')
    if end:
        ax.plot(end[0], end[1], '*', color='#d63031',
                markersize=14, zorder=6, label='End')

    ax.legend(loc='upper right', fontsize=8)
    ax.set_xlabel('x [m]')
    ax.set_ylabel('y [m]')
    plt.tight_layout()
    plt.show()
    return fig, ax
