"""
Motion planning helper functions for visualizing firmware-like path tracking.

Simulates the BILBO firmware's position control algorithm (pure pursuit with
curvature-based speed) in Python, producing speed/turn rate profiles and
animated visualizations.

The simulation mirrors the logic in bilbo_position_control.cpp:
  - Menger curvature estimation with adaptive stride
  - Curvature-based speed: v = max_speed / (1 + curvature_gain * kappa)
  - Exponential smoothing of speed target (tau = 0.1s)
  - Deceleration profiles near stops and path end
  - Adaptive lookahead pure pursuit
  - cos(heading_error) speed scaling
  - PI angular control with saturation and fade

Usage:
    from core.utils.control_lib.lib_control.motion_planning import plan_path, Bounds
    from core.utils.control_lib.lib_control.motion_planning.motion_planning_helpers import (
        simulate_path_tracking, plot_speed_profile, animate_path_tracking,
    )

    path = plan_path(start=(0, 0), end=(2, 2), bounds=Bounds(0, 3, 0, 3))
    result = simulate_path_tracking(path)
    plot_speed_profile(path, result)
    animate_path_tracking(path, result)
"""

import dataclasses
import math

import numpy as np


# ============================================================================
# Result dataclass
# ============================================================================

@dataclasses.dataclass
class PathTrackingResult:
    """Time-series output of the path tracking simulation."""
    time: np.ndarray            # [s]
    x: np.ndarray               # [m] robot x position
    y: np.ndarray               # [m] robot y position
    psi: np.ndarray             # [rad] robot heading
    v_cmd: np.ndarray           # [m/s] forward velocity command
    psi_dot_cmd: np.ndarray     # [rad/s] yaw rate command
    v_target: np.ndarray        # [m/s] speed limit (from curvature + decel)
    curvature: np.ndarray       # [1/m] estimated path curvature ahead
    progress: np.ndarray        # [-] floating-point path index
    carrot_x: np.ndarray        # [m] lookahead carrot x
    carrot_y: np.ndarray        # [m] lookahead carrot y
    heading_error: np.ndarray   # [rad] heading error to carrot


# ============================================================================
# Internal helpers (mirror firmware logic)
# ============================================================================

def _normalize_angle(angle):
    """Wrap angle to [-pi, pi]."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _compute_cumulative_distances(path_x, path_y):
    """Precompute cumulative arc lengths."""
    dx = np.diff(path_x)
    dy = np.diff(path_y)
    seg_lengths = np.sqrt(dx ** 2 + dy ** 2)
    return np.concatenate([[0.0], np.cumsum(seg_lengths)])


def _estimate_curvature_ahead(path_x, path_y, cumul_dist, total_length,
                              at_progress, lookahead_dist, N):
    """
    Estimate max Menger curvature in a lookahead window.
    Mirrors _estimate_curvature_ahead() in bilbo_position_control.cpp.
    """
    if N < 3:
        return 0.0

    start_idx = int(at_progress)
    if start_idx >= N - 1:
        start_idx = N - 2

    start_arc = cumul_dist[start_idx]
    end_arc = start_arc + lookahead_dist

    end_idx = start_idx
    while end_idx < N - 1 and cumul_dist[end_idx] < end_arc:
        end_idx += 1

    # Adaptive stride: ~50mm chord for robust curvature estimation
    avg_spacing = total_length / max(N - 1, 1) if N > 1 else 0.015
    stride = int(0.05 / max(avg_spacing, 0.001))
    stride = max(1, min(15, stride))

    # Need at least 2*stride points
    if end_idx < start_idx + 2 * stride:
        if start_idx + 2 * stride < N:
            end_idx = start_idx + 2 * stride
        else:
            return 0.0

    max_kappa = 0.0
    i = start_idx
    while i + 2 * stride <= end_idx and i + 2 * stride < N:
        ax, ay = path_x[i], path_y[i]
        bx, by = path_x[i + stride], path_y[i + stride]
        cx, cy = path_x[i + 2 * stride], path_y[i + 2 * stride]

        abx, aby = bx - ax, by - ay
        bcx, bcy = cx - bx, cy - by
        acx, acy = cx - ax, cy - ay

        cross_mag = abs(abx * acy - aby * acx)
        ab_len = math.sqrt(abx ** 2 + aby ** 2)
        bc_len = math.sqrt(bcx ** 2 + bcy ** 2)
        ac_len = math.sqrt(acx ** 2 + acy ** 2)

        denom = ab_len * bc_len * ac_len
        if denom > 1e-10:
            kappa = 2.0 * cross_mag / denom
            if kappa > max_kappa:
                max_kappa = kappa

        i += 1

    return max_kappa


def _project_onto_path(robot_x, robot_y, path_x, path_y, last_progress, N,
                       search_window=30):
    """
    Project robot position onto path, searching forward from last_progress.
    Returns floating-point progress index (monotonic forward).
    """
    start_seg = int(last_progress)
    if start_seg >= N - 1:
        start_seg = N - 2

    end_seg = min(start_seg + search_window, N - 2)

    best_progress = last_progress
    best_dist_sq = 1e30

    for i in range(start_seg, end_seg + 1):
        ax, ay = path_x[i], path_y[i]
        bx, by = path_x[i + 1], path_y[i + 1]

        dx, dy = bx - ax, by - ay
        len_sq = dx * dx + dy * dy

        if len_sq < 1e-6:
            t = 0.0
        else:
            t = ((robot_x - ax) * dx + (robot_y - ay) * dy) / len_sq
            t = _clamp(t, 0.0, 1.0)

        proj_x = ax + t * dx
        proj_y = ay + t * dy
        dist_sq = (robot_x - proj_x) ** 2 + (robot_y - proj_y) ** 2

        candidate = float(i) + t
        if candidate >= last_progress and dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best_progress = candidate

    return best_progress


def _cumul_dist_at(progress, cumul_dist, N):
    """Interpolated cumulative distance at floating-point progress."""
    if N < 2:
        return 0.0
    if progress <= 0.0:
        return cumul_dist[0]
    if progress >= N - 1:
        return cumul_dist[N - 1]
    idx = int(progress)
    t = progress - idx
    return cumul_dist[idx] + t * (cumul_dist[idx + 1] - cumul_dist[idx])


def _advance_along_path(from_progress, distance_meters, cumul_dist, N):
    """Advance along path by arc-length distance. Returns new progress."""
    if N < 2:
        return from_progress

    current_arc = _cumul_dist_at(from_progress, cumul_dist, N)
    target_arc = current_arc + distance_meters

    if target_arc >= cumul_dist[N - 1]:
        return float(N - 1)
    if target_arc <= 0.0:
        return 0.0

    # Binary search
    lo, hi = 0, N - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if cumul_dist[mid] <= target_arc:
            lo = mid
        else:
            hi = mid

    seg_start = cumul_dist[lo]
    seg_end = cumul_dist[lo + 1]
    seg_len = seg_end - seg_start
    t = 0.0
    if seg_len > 1e-6:
        t = _clamp((target_arc - seg_start) / seg_len, 0.0, 1.0)

    return float(lo) + t


def _interpolate_path(progress, path_x, path_y, N):
    """Interpolate path position at floating-point progress."""
    if N == 0:
        return 0.0, 0.0
    if progress <= 0.0:
        return path_x[0], path_y[0]
    if progress >= N - 1:
        return path_x[N - 1], path_y[N - 1]
    idx = int(progress)
    t = progress - idx
    x = path_x[idx] + t * (path_x[idx + 1] - path_x[idx])
    y = path_y[idx] + t * (path_y[idx + 1] - path_y[idx])
    return x, y


# ============================================================================
# Main simulation
# ============================================================================

_SPEED_SMOOTH_TAU = 0.1  # [s] exponential smoothing time constant


def simulate_path_tracking(
    path: list[tuple[float, float]],
    start_heading: float | None = None,
    max_speed: float = 0.5,
    curvature_gain: float = 2.0,
    curvature_lookahead: float = 0.3,
    kp_linear: float = 2.0,
    kd_linear: float = 0.5,
    kp_angular: float = 10.0,
    ki_angular: float = 0.3,
    max_turn_rate: float = 5.0,
    lookahead_base: float = 0.15,
    lookahead_min: float = 0.03,
    decel_limit: float = 0.0,
    arrival_tolerance: float = 0.05,
    arrival_dwell_time: float = 0.5,
    stop_indices: list[int] | None = None,
    stop_dwell_time: float = 1.0,
    Ts: float = 0.01,
) -> PathTrackingResult:
    """
    Simulate the firmware's path tracking algorithm on a planned path.

    Mirrors the logic in bilbo_position_control.cpp (_update_follow_path):
    curvature-based speed limiting, pure pursuit with adaptive lookahead,
    deceleration profiles, and cos(heading_error) scaling.

    Parameters
    ----------
    path : list of (x, y)
        Dense path from plan_path() (typically ~15mm uniform spacing).
    start_heading : float, optional
        Initial robot heading [rad]. If None, inferred from first path segment.
    max_speed : float
        Maximum forward speed [m/s]. Default 0.5.
    curvature_gain : float
        Curvature sensitivity for speed: v = max_speed / (1 + gain * kappa).
    curvature_lookahead : float
        Distance ahead [m] to scan for curvature. Default 0.3.
    kp_linear : float
        Linear proportional gain [1/s]. Also sets lookahead = v/kp.
    kd_linear : float
        Velocity damping factor. Subtracts kd * |v| from speed command.
    kp_angular : float
        Angular proportional gain [rad/s per rad].
    ki_angular : float
        Angular integral gain [rad/s per rad*s].
    max_turn_rate : float
        Maximum yaw rate [rad/s].
    lookahead_base : float
        Base lookahead distance [m]. Used when kp_linear=0 as fallback:
        lookahead = lookahead_base * (v_target / max_speed).
    lookahead_min : float
        Minimum lookahead distance [m]. Floor for the lookahead.
    decel_limit : float
        Deceleration limit [m/s^2] for sqrt brake profile. 0 = use kp*d.
    arrival_tolerance : float
        Distance [m] to consider "arrived" at waypoint/endpoint.
    arrival_dwell_time : float
        Time [s] to hold at path end before finishing.
    stop_indices : list of int, optional
        Path indices where the robot should stop and dwell.
    stop_dwell_time : float
        Time [s] to hold at each stop waypoint.
    Ts : float
        Simulation timestep [s]. Default 0.01 (100 Hz, matching firmware).

    Returns
    -------
    PathTrackingResult
        Time-series of robot state and control commands.
    """
    path_x = np.array([p[0] for p in path], dtype=float)
    path_y = np.array([p[1] for p in path], dtype=float)
    N = len(path)

    if N < 2:
        raise ValueError("Path must have at least 2 points")

    # Precompute cumulative distances
    cumul_dist = _compute_cumulative_distances(path_x, path_y)
    total_length = cumul_dist[-1]

    # Resolve start heading
    if start_heading is None:
        start_heading = math.atan2(
            path_y[1] - path_y[0], path_x[1] - path_x[0])

    # Stop handling
    stops = sorted(stop_indices) if stop_indices else []
    next_stop_ptr = 0

    # Robot state
    robot_x = float(path_x[0])
    robot_y = float(path_y[0])
    robot_psi = start_heading
    current_v = 0.0
    progress = 0.0
    v_target_smooth = 0.0
    angular_integral = 0.0

    # Dwell state machine
    FOLLOWING, AT_STOP, AT_END = 0, 1, 2
    state = FOLLOWING
    dwell_timer = 0.0

    # Storage (pre-allocate generously, trim at end)
    max_steps = int(total_length / max(max_speed * 0.1, 0.01) / Ts * 5) + 1000
    max_steps = min(max_steps, 1_000_000)  # hard cap

    time_arr = np.zeros(max_steps)
    x_arr = np.zeros(max_steps)
    y_arr = np.zeros(max_steps)
    psi_arr = np.zeros(max_steps)
    v_cmd_arr = np.zeros(max_steps)
    psi_dot_arr = np.zeros(max_steps)
    v_target_arr = np.zeros(max_steps)
    curvature_arr = np.zeros(max_steps)
    progress_arr = np.zeros(max_steps)
    carrot_x_arr = np.zeros(max_steps)
    carrot_y_arr = np.zeros(max_steps)
    heading_err_arr = np.zeros(max_steps)

    step = 0
    finished = False

    while step < max_steps and not finished:
        t = step * Ts

        # Record current state
        time_arr[step] = t
        x_arr[step] = robot_x
        y_arr[step] = robot_y
        psi_arr[step] = robot_psi

        v_cmd = 0.0
        w_cmd = 0.0
        kappa = 0.0
        v_target = 0.0
        carrot_x, carrot_y = robot_x, robot_y
        heading_error = 0.0

        if state == AT_STOP:
            # Dwelling at stop point
            dwell_timer += Ts
            if dwell_timer >= stop_dwell_time:
                next_stop_ptr += 1
                dwell_timer = 0.0
                angular_integral = 0.0
                state = FOLLOWING

        elif state == AT_END:
            # Dwelling at path end
            dwell_timer += Ts
            if dwell_timer >= arrival_dwell_time:
                finished = True

        elif state == FOLLOWING:
            # --- Core path tracking (mirrors firmware) ---

            # 1. Project robot onto path
            progress = _project_onto_path(
                robot_x, robot_y, path_x, path_y, progress, N)

            # 2. Curvature estimation
            kappa = _estimate_curvature_ahead(
                path_x, path_y, cumul_dist, total_length,
                progress, curvature_lookahead, N)

            # 3. Target speed from curvature
            v_target_raw = max_speed / (1.0 + curvature_gain * kappa)
            v_target_raw = _clamp(v_target_raw, 0.0, max_speed)

            # 4. Exponential smoothing
            alpha = Ts / (Ts + _SPEED_SMOOTH_TAU)
            v_target_smooth = (alpha * v_target_raw
                               + (1.0 - alpha) * v_target_smooth)
            v_target = v_target_smooth

            # 5. Deceleration near stops
            robot_arc = _cumul_dist_at(progress, cumul_dist, N)

            if next_stop_ptr < len(stops):
                stop_idx = stops[next_stop_ptr]
                d_to_stop = cumul_dist[stop_idx] - robot_arc
                if d_to_stop > 0.0:
                    if decel_limit > 0:
                        v_brake = math.sqrt(2.0 * decel_limit * d_to_stop)
                    else:
                        v_brake = kp_linear * d_to_stop
                    v_target = min(v_target, v_brake)

            # 6. Deceleration near path end
            d_to_end = cumul_dist[-1] - robot_arc
            if d_to_end > 0.0:
                if decel_limit > 0:
                    v_brake_end = math.sqrt(2.0 * decel_limit * d_to_end)
                else:
                    v_brake_end = kp_linear * d_to_end
                v_target = min(v_target, v_brake_end)
            else:
                v_target = 0.0

            # 7. Compute lookahead
            if kp_linear > 1e-6:
                lookahead = v_target / kp_linear
            else:
                lookahead = lookahead_base * (
                    v_target / max(max_speed, 1e-6))
            lookahead = max(lookahead, lookahead_min)

            # 8. Place carrot along path
            carrot_progress = _advance_along_path(
                progress, lookahead, cumul_dist, N)

            # Clamp at next stop
            if next_stop_ptr < len(stops):
                stop_idx = stops[next_stop_ptr]
                if carrot_progress > float(stop_idx):
                    carrot_progress = float(stop_idx)

            # Clamp at path end
            if carrot_progress > float(N - 1):
                carrot_progress = float(N - 1)

            carrot_x, carrot_y = _interpolate_path(
                carrot_progress, path_x, path_y, N)

            # 9. Heading error
            dx_c = carrot_x - robot_x
            dy_c = carrot_y - robot_y
            carrot_dist = math.sqrt(dx_c ** 2 + dy_c ** 2)
            angle_to_carrot = math.atan2(dy_c, dx_c)
            heading_error = _normalize_angle(angle_to_carrot - robot_psi)

            # 10. Speed command
            if decel_limit > 1e-6:
                v_cmd = v_target * (1.0 + kd_linear)
            else:
                v_cmd = min(v_target, kp_linear * carrot_dist)
            v_cmd = max(0.0, v_cmd - kd_linear * abs(current_v))
            cos_scale = max(0.0, math.cos(heading_error))
            v_cmd *= cos_scale

            # 11. Angular command (PI with anti-windup)
            w_p = kp_angular * heading_error
            w_unsat = w_p + angular_integral
            w_sat = _clamp(w_unsat, -max_turn_rate, max_turn_rate)

            is_saturated = abs(w_unsat - w_sat) > 1e-6
            would_push = (is_saturated
                          and ((w_unsat > w_sat and heading_error > 0)
                               or (w_unsat < w_sat and heading_error < 0)))
            if not would_push:
                angular_integral += ki_angular * heading_error * Ts
                max_int = max_turn_rate / max(ki_angular, 0.01)
                angular_integral = _clamp(
                    angular_integral, -max_int, max_int)

            # Fade yaw rate near carrot (prevents jitter at stops)
            fade_radius = 2.0 * arrival_tolerance
            w_fade = _clamp(carrot_dist / fade_radius, 0.0, 1.0)
            w_cmd = w_sat * w_fade

            # 12. Check stop arrival
            if next_stop_ptr < len(stops):
                stop_idx = stops[next_stop_ptr]
                stop_dist = math.sqrt(
                    (robot_x - path_x[stop_idx]) ** 2
                    + (robot_y - path_y[stop_idx]) ** 2)
                if (progress >= float(stop_idx) - 1.0
                        and stop_dist < arrival_tolerance):
                    state = AT_STOP
                    dwell_timer = 0.0
                    v_cmd = 0.0
                    w_cmd = 0.0

            # 13. Check end arrival
            end_dist = math.sqrt(
                (robot_x - path_x[-1]) ** 2
                + (robot_y - path_y[-1]) ** 2)
            if (progress >= float(N - 1) - 1.0
                    and end_dist < arrival_tolerance):
                state = AT_END
                dwell_timer = 0.0
                v_cmd = 0.0
                w_cmd = 0.0

        # Record control outputs
        v_cmd_arr[step] = v_cmd
        psi_dot_arr[step] = w_cmd
        v_target_arr[step] = v_target
        curvature_arr[step] = kappa
        progress_arr[step] = progress
        carrot_x_arr[step] = carrot_x
        carrot_y_arr[step] = carrot_y
        heading_err_arr[step] = heading_error

        # 14. Integrate robot motion (unicycle model, perfect tracking)
        robot_x += v_cmd * math.cos(robot_psi) * Ts
        robot_y += v_cmd * math.sin(robot_psi) * Ts
        robot_psi = _normalize_angle(robot_psi + w_cmd * Ts)
        current_v = v_cmd

        step += 1

    # Trim arrays
    n = step
    return PathTrackingResult(
        time=time_arr[:n],
        x=x_arr[:n],
        y=y_arr[:n],
        psi=psi_arr[:n],
        v_cmd=v_cmd_arr[:n],
        psi_dot_cmd=psi_dot_arr[:n],
        v_target=v_target_arr[:n],
        curvature=curvature_arr[:n],
        progress=progress_arr[:n],
        carrot_x=carrot_x_arr[:n],
        carrot_y=carrot_y_arr[:n],
        heading_error=heading_err_arr[:n],
    )


# ============================================================================
# Static speed/turn profile plot
# ============================================================================

def plot_speed_profile(
    path: list[tuple[float, float]],
    result: PathTrackingResult | None = None,
    figsize: tuple[float, float] = (12, 6),
    title: str = "Path Tracking Speed Profile",
    **sim_kwargs,
):
    """
    Plot forward speed and yaw rate profiles over time.

    If ``result`` is None, runs simulate_path_tracking() first.
    Extra keyword arguments are forwarded to simulate_path_tracking().

    Parameters
    ----------
    path : list of (x, y)
    result : PathTrackingResult, optional
    figsize : figure size
    title : str
    **sim_kwargs : forwarded to simulate_path_tracking()

    Returns
    -------
    (fig, axes) : matplotlib Figure and (ax_speed, ax_yaw) Axes
    """
    import matplotlib.pyplot as plt

    if result is None:
        result = simulate_path_tracking(path, **sim_kwargs)

    fig, (ax_v, ax_w) = plt.subplots(2, 1, figsize=figsize, sharex=True)
    fig.suptitle(title, fontsize=13, fontweight='bold')

    # Speed profile
    ax_v.plot(result.time, result.v_cmd, color='#2d3436', linewidth=1.2,
              label='v_cmd (actual command)')
    ax_v.plot(result.time, result.v_target, color='#0984e3', linewidth=1,
              linestyle='--', alpha=0.7, label='v_target (speed limit)')
    ax_v.set_ylabel('Forward speed [m/s]')
    ax_v.legend(loc='upper right', fontsize=8)
    ax_v.grid(True, alpha=0.3)
    ax_v.set_ylim(bottom=-0.02)

    # Yaw rate profile
    ax_w.plot(result.time, result.psi_dot_cmd, color='#d63031', linewidth=1.2,
              label='psi_dot_cmd')
    ax_w.axhline(0, color='#636e72', linewidth=0.5, alpha=0.5)
    ax_w.set_ylabel('Yaw rate [rad/s]')
    ax_w.set_xlabel('Time [s]')
    ax_w.legend(loc='upper right', fontsize=8)
    ax_w.grid(True, alpha=0.3)

    # Mark stop dwell periods (v_cmd = 0 for > 2 timesteps, not at start)
    dt = result.time[1] - result.time[0] if len(result.time) > 1 else 0.01
    zero_mask = np.abs(result.v_cmd) < 1e-4
    # Find contiguous zero regions (skip the very first few samples)
    in_dwell = False
    dwell_start = 0.0
    for i in range(max(5, 1), len(result.time)):
        if zero_mask[i] and not in_dwell:
            in_dwell = True
            dwell_start = result.time[i]
        elif not zero_mask[i] and in_dwell:
            in_dwell = False
            if result.time[i] - dwell_start > 3 * dt:
                ax_v.axvspan(dwell_start, result.time[i], alpha=0.08,
                             color='#fdcb6e', zorder=0)
                ax_w.axvspan(dwell_start, result.time[i], alpha=0.08,
                             color='#fdcb6e', zorder=0)

    plt.tight_layout()
    plt.show()
    return fig, (ax_v, ax_w)


# ============================================================================
# Animated path tracking visualization
# ============================================================================

def animate_path_tracking(
    path: list[tuple[float, float]],
    result: PathTrackingResult | None = None,
    obstacles: list | None = None,
    bounds=None,
    waypoints: list | None = None,
    figsize: tuple[float, float] = (14, 7),
    interval: int = 30,
    speedup: float = 1.0,
    agent_radius: float = 0.06,
    trail_length: int = 200,
    title: str = "Path Tracking Simulation",
    **sim_kwargs,
):
    """
    Animated visualization of an agent following a path.

    Shows a point + heading arrow agent marker tracking the path at
    the simulated speed, alongside live speed and yaw rate profiles.

    Parameters
    ----------
    path : list of (x, y)
    result : PathTrackingResult, optional
        If None, runs simulate_path_tracking() first.
    obstacles : list of CircleObstacle / BoxObstacle, optional
    bounds : Bounds, optional
    waypoints : list of Waypoint, optional
    figsize : figure size
    interval : int
        Milliseconds between animation frames.
    speedup : float
        Playback speed multiplier. 1.0 = real-time.
    agent_radius : float
        Radius [m] of the agent marker circle.
    trail_length : int
        Number of past positions to show as trail.
    title : str
    **sim_kwargs : forwarded to simulate_path_tracking()

    Returns
    -------
    matplotlib.animation.FuncAnimation
        Call plt.show() to display, or anim.save() to export.
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.animation import FuncAnimation

    if result is None:
        result = simulate_path_tracking(path, **sim_kwargs)

    # Compute frame indices: each frame advances by (interval * speedup) ms
    Ts = result.time[1] - result.time[0] if len(result.time) > 1 else 0.01
    dt_frame = (interval / 1000.0) * speedup
    steps_per_frame = max(1, int(dt_frame / Ts))
    n_total = len(result.time)
    frame_indices = list(range(0, n_total, steps_per_frame))
    if frame_indices[-1] != n_total - 1:
        frame_indices.append(n_total - 1)

    # --- Layout: map on left, speed/yaw on right ---
    fig = plt.figure(figsize=figsize)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.3, 1], hspace=0.35,
                          wspace=0.3)
    ax_map = fig.add_subplot(gs[:, 0])
    ax_v = fig.add_subplot(gs[0, 1])
    ax_w = fig.add_subplot(gs[1, 1], sharex=ax_v)

    fig.suptitle(title, fontsize=13, fontweight='bold')

    # --- Map setup ---
    ax_map.set_aspect('equal')
    ax_map.grid(True, alpha=0.2)
    ax_map.set_xlabel('x [m]')
    ax_map.set_ylabel('y [m]')

    path_x = [p[0] for p in path]
    path_y = [p[1] for p in path]

    # Auto-compute axis limits from path
    if bounds is not None:
        margin = 0.15
        ax_map.set_xlim(bounds.x_min - margin, bounds.x_max + margin)
        ax_map.set_ylim(bounds.y_min - margin, bounds.y_max + margin)
    else:
        margin = 0.3
        ax_map.set_xlim(min(path_x) - margin, max(path_x) + margin)
        ax_map.set_ylim(min(path_y) - margin, max(path_y) + margin)

    # Draw bounds
    if bounds is not None:
        rect = patches.Rectangle(
            (bounds.x_min, bounds.y_min),
            bounds.x_max - bounds.x_min, bounds.y_max - bounds.y_min,
            linewidth=1.5, edgecolor='#2d3436', facecolor='none',
            linestyle='--', alpha=0.5)
        ax_map.add_patch(rect)

    # Draw obstacles
    if obstacles:
        # Import locally to avoid hard dependency
        from core.utils.control_lib.lib_control.motion_planning.common import (
            CircleObstacle, BoxObstacle, _draw_box_patch)
        for obs in obstacles:
            if isinstance(obs, CircleObstacle):
                c = patches.Circle(
                    (obs.cx, obs.cy), obs.radius,
                    facecolor='#ff6b6b', edgecolor='#c0392b',
                    alpha=0.5, linewidth=1)
                ax_map.add_patch(c)
            elif isinstance(obs, BoxObstacle):
                _draw_box_patch(ax_map, obs, alpha=0.5, linewidth=1)

    # Draw waypoints
    if waypoints:
        from core.utils.control_lib.lib_control.motion_planning.common import (
            _waypoint_zone_radius)
        for wp in waypoints:
            r = _waypoint_zone_radius(wp.weight)
            zone = patches.Circle(
                (wp.x, wp.y), r,
                facecolor='#74b9ff', edgecolor='#0984e3',
                alpha=0.1, linewidth=0.8, linestyle='--')
            ax_map.add_patch(zone)
            ax_map.plot(wp.x, wp.y, 'o', color='#0984e3', markersize=4)

    # Path line
    ax_map.plot(path_x, path_y, '-', color='#b2bec3', linewidth=1, zorder=1)

    # Path sample points (shows sampling density)
    ax_map.plot(path_x, path_y, '.', color='#636e72', markersize=2, zorder=2,
                alpha=0.5)

    # Start / end markers
    ax_map.plot(path_x[0], path_y[0], 's', color='#00b894', markersize=8,
                zorder=5)
    ax_map.plot(path_x[-1], path_y[-1], '*', color='#d63031', markersize=10,
                zorder=5)

    # --- Animated elements on map ---
    # Trail (past positions)
    trail_line, = ax_map.plot([], [], '-', color='#0984e3', linewidth=2,
                              alpha=0.6, zorder=3)
    # Agent body (circle)
    agent_circle = patches.Circle(
        (0, 0), agent_radius,
        facecolor='#0984e3', edgecolor='#2d3436',
        linewidth=1.5, zorder=10, alpha=0.9)
    ax_map.add_patch(agent_circle)

    # Agent heading arrow
    arrow_len = agent_radius * 2.5
    agent_arrow, = ax_map.plot([], [], '-', color='#2d3436', linewidth=2.5,
                               solid_capstyle='round', zorder=11)

    # Carrot marker
    carrot_marker, = ax_map.plot([], [], 'x', color='#e17055', markersize=8,
                                 markeredgewidth=2, zorder=8)

    # --- Speed profile setup ---
    ax_v.plot(result.time, result.v_cmd, color='#b2bec3', linewidth=0.8,
              alpha=0.4)
    ax_v.plot(result.time, result.v_target, color='#74b9ff', linewidth=0.8,
              alpha=0.3, linestyle='--')
    v_line, = ax_v.plot([], [], color='#2d3436', linewidth=1.5,
                        label='v_cmd')
    v_target_line, = ax_v.plot([], [], color='#0984e3', linewidth=1,
                               linestyle='--', alpha=0.7, label='v_target')
    v_cursor = ax_v.axvline(0, color='#d63031', linewidth=1, alpha=0.5)
    ax_v.set_ylabel('Speed [m/s]')
    ax_v.set_ylim(-0.02, max(0.1, result.v_cmd.max() * 1.15))
    ax_v.legend(loc='upper right', fontsize=7)
    ax_v.grid(True, alpha=0.2)

    # --- Yaw rate profile setup ---
    ax_w.plot(result.time, result.psi_dot_cmd, color='#b2bec3', linewidth=0.8,
              alpha=0.4)
    w_line, = ax_w.plot([], [], color='#d63031', linewidth=1.5,
                        label='psi_dot_cmd')
    w_cursor = ax_w.axvline(0, color='#d63031', linewidth=1, alpha=0.5)
    w_max = max(0.5, np.abs(result.psi_dot_cmd).max() * 1.15)
    ax_w.set_ylabel('Yaw rate [rad/s]')
    ax_w.set_xlabel('Time [s]')
    ax_w.set_ylim(-w_max, w_max)
    ax_w.axhline(0, color='#636e72', linewidth=0.5, alpha=0.3)
    ax_w.legend(loc='upper right', fontsize=7)
    ax_w.grid(True, alpha=0.2)

    # Time annotation
    time_text = ax_map.text(
        0.02, 0.98, '', transform=ax_map.transAxes,
        fontsize=9, verticalalignment='top',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    def _init():
        trail_line.set_data([], [])
        agent_circle.center = (0, 0)
        agent_arrow.set_data([], [])
        carrot_marker.set_data([], [])
        v_line.set_data([], [])
        v_target_line.set_data([], [])
        w_line.set_data([], [])
        v_cursor.set_xdata([0])
        w_cursor.set_xdata([0])
        time_text.set_text('')
        return (trail_line, agent_circle, agent_arrow, carrot_marker,
                v_line, v_target_line, w_line, v_cursor, w_cursor, time_text)

    def _update(frame_num):
        idx = frame_indices[frame_num]

        rx = result.x[idx]
        ry = result.y[idx]
        rpsi = result.psi[idx]
        t = result.time[idx]

        # Trail
        trail_start = max(0, idx - trail_length)
        trail_line.set_data(result.x[trail_start:idx + 1],
                            result.y[trail_start:idx + 1])

        # Agent body
        agent_circle.center = (rx, ry)

        # Agent heading arrow
        ax_tip = rx + arrow_len * math.cos(rpsi)
        ay_tip = ry + arrow_len * math.sin(rpsi)
        agent_arrow.set_data([rx, ax_tip], [ry, ay_tip])

        # Carrot
        carrot_marker.set_data([result.carrot_x[idx]],
                               [result.carrot_y[idx]])

        # Speed plot (draw up to current time)
        v_line.set_data(result.time[:idx + 1], result.v_cmd[:idx + 1])
        v_target_line.set_data(result.time[:idx + 1],
                               result.v_target[:idx + 1])
        v_cursor.set_xdata([t])

        # Yaw rate plot
        w_line.set_data(result.time[:idx + 1], result.psi_dot_cmd[:idx + 1])
        w_cursor.set_xdata([t])

        # Time annotation
        time_text.set_text(
            f't = {t:.2f}s\n'
            f'v = {result.v_cmd[idx]:.3f} m/s\n'
            f'\u03C8\u0307 = {result.psi_dot_cmd[idx]:.2f} rad/s')

        return (trail_line, agent_circle, agent_arrow, carrot_marker,
                v_line, v_target_line, w_line, v_cursor, w_cursor, time_text)

    anim = FuncAnimation(
        fig, _update, init_func=_init,
        frames=len(frame_indices), interval=interval, blit=True)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    return anim


# ============================================================================
# Examples
# ============================================================================

if __name__ == '__main__':
    import matplotlib.pyplot as plt
    from core.utils.control_lib.lib_control.motion_planning.common import (
        Bounds, Waypoint, CircleObstacle, BoxObstacle,
    )
    from core.utils.control_lib.lib_control.motion_planning.rrt import plan_path

    # # ------------------------------------------------------------------
    # # Example 1: Simple curved path (no obstacles)
    # # ------------------------------------------------------------------
    # print("=== Example 1: Simple curved path ===")
    #
    bounds = Bounds(0, 3, 0, 3)
    waypoints = [Waypoint(1.0, 2.0, weight=0.8)]
    # path = plan_path(
    #     start=(0.3, 0.3),
    #     end=(2.7, 2.7),
    #     waypoints=waypoints,
    #     bounds=bounds,
    #     seed=42,
    # )
    # print(f"  Path: {len(path)} points")
    #
    # result = simulate_path_tracking(path, max_speed=0.4)
    # print(f"  Simulation: {result.time[-1]:.2f}s, "
    #       f"peak speed {result.v_cmd.max():.3f} m/s")
    #
    # plot_speed_profile(path, result,
    #                    title="Example 1: Simple Curved Path")
    #
    # # ------------------------------------------------------------------
    # # Example 2: S-curve with obstacles — shows curvature-based slowdown
    # # ------------------------------------------------------------------
    # print("\n=== Example 2: S-curve with obstacles ===")
    #
    # obstacles = [
    #     CircleObstacle(1.5, 1.0, 0.3),
    #     CircleObstacle(1.5, 2.0, 0.3),
    # ]
    # path2 = plan_path(
    #     start=(0.3, 1.5),
    #     end=(2.7, 1.5),
    #     obstacles=obstacles,
    #     bounds=bounds,
    #     seed=42,
    # )
    # print(f"  Path: {len(path2)} points")
    #
    # result2 = simulate_path_tracking(path2, max_speed=0.5, curvature_gain=3.0)
    # print(f"  Simulation: {result2.time[-1]:.2f}s, "
    #       f"peak speed {result2.v_cmd.max():.3f} m/s")
    #
    # plot_speed_profile(path2, result2,
    #                    title="Example 2: S-Curve with Obstacles "
    #                          "(curvature_gain=3.0)")
    #
    # # ------------------------------------------------------------------
    # # Example 3: Path with STOP waypoint — shows dwell behavior
    # # ------------------------------------------------------------------
    # print("\n=== Example 3: Path with STOP waypoint ===")
    #
    # stop_wp = Waypoint(1.5, 1.5, weight=1.0, stop=True)
    # path3 = plan_path(
    #     start=(0.3, 0.3),
    #     end=(2.7, 2.7),
    #     waypoints=[stop_wp],
    #     bounds=bounds,
    #     seed=42,
    # )
    # # Find the stop index (closest path point to the STOP waypoint)
    # stop_dists = [(p[0] - stop_wp.x) ** 2 + (p[1] - stop_wp.y) ** 2
    #               for p in path3]
    # stop_idx = int(np.argmin(stop_dists))
    # print(f"  Path: {len(path3)} points, STOP at index {stop_idx}")
    #
    # result3 = simulate_path_tracking(
    #     path3, max_speed=0.4, stop_indices=[stop_idx], stop_dwell_time=1.0)
    # print(f"  Simulation: {result3.time[-1]:.2f}s")
    #
    # plot_speed_profile(path3, result3,
    #                    title="Example 3: Path with STOP Waypoint")
    #
    # # ------------------------------------------------------------------
    # # Example 4: Decel-limit mode (sqrt braking profile)
    # # ------------------------------------------------------------------
    # print("\n=== Example 4: Deceleration limit (sqrt profile) ===")
    #
    # path4 = plan_path(
    #     start=(0.3, 1.5),
    #     end=(2.7, 1.5),
    #     bounds=bounds,
    #     seed=42,
    # )
    # print(f"  Path: {len(path4)} points (straight-ish)")
    #
    # result4_kp = simulate_path_tracking(
    #     path4, max_speed=0.5, decel_limit=0.0)
    # result4_sqrt = simulate_path_tracking(
    #     path4, max_speed=0.5, decel_limit=1.0)
    #
    # fig, (ax_v, ax_w) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
    # fig.suptitle("Example 4: Deceleration Modes Compared",
    #              fontsize=13, fontweight='bold')
    # ax_v.plot(result4_kp.time, result4_kp.v_cmd, color='#0984e3',
    #           linewidth=1.2, label='kp*d mode (decel_limit=0)')
    # ax_v.plot(result4_sqrt.time, result4_sqrt.v_cmd, color='#d63031',
    #           linewidth=1.2, label='sqrt mode (decel_limit=1.0)')
    # ax_v.set_ylabel('Forward speed [m/s]')
    # ax_v.legend(fontsize=8)
    # ax_v.grid(True, alpha=0.3)
    # ax_w.plot(result4_kp.time, result4_kp.psi_dot_cmd, color='#0984e3',
    #           linewidth=1.2, label='kp*d mode')
    # ax_w.plot(result4_sqrt.time, result4_sqrt.psi_dot_cmd, color='#d63031',
    #           linewidth=1.2, label='sqrt mode')
    # ax_w.axhline(0, color='#636e72', linewidth=0.5, alpha=0.5)
    # ax_w.set_ylabel('Yaw rate [rad/s]')
    # ax_w.set_xlabel('Time [s]')
    # ax_w.legend(fontsize=8)
    # ax_w.grid(True, alpha=0.3)
    # plt.tight_layout()
    # plt.show()

    # # ------------------------------------------------------------------
    # # Example 5: Animated path tracking
    # # ------------------------------------------------------------------
    # print("\n=== Example 5: Animated path tracking ===")
    # print("  (close the animation window to exit)")
    #
    # obstacles5 = [
    #     CircleObstacle(1.5, 1.0, 0.25),
    #     BoxObstacle(1.5, 2.2, 0.8, 0.3, psi=0.3),
    # ]
    # waypoints5 = [Waypoint(0.8, 2.0, weight=0.7),
    #               Waypoint(2.2, 1.0, weight=0.7)]
    #
    #
    #
    # path5 = plan_path(
    #     start=(0.3, 0.3),
    #     end=(2.7, 2.7),
    #     waypoints=waypoints5,
    #     obstacles=obstacles5,
    #     bounds=bounds,
    #     seed=42,
    # )
    # print(f"  Path: {len(path5)} points")
    #
    # # Parameters from bilbo2 lab config (configs/control/bilbo2/lab.yaml)
    # bilbo2_lab = dict(
    #     max_speed=0.6,
    #     kp_angular=8.0,
    #     ki_angular=0.25,
    #     kp_linear=0.0,          # unused when decel_limit > 0
    #     kd_linear=0.5,
    #     max_turn_rate=5.0,
    #     lookahead_min=0.03,
    #     decel_limit=0.6,
    #     curvature_gain=0.2,
    #     curvature_lookahead=0.1,
    #     arrival_tolerance=0.05,
    #     arrival_dwell_time=0.5,
    #     stop_dwell_time=1.0,
    # )
    #
    # result5 = simulate_path_tracking(path5, **bilbo2_lab)
    # print(f"  Simulation: {result5.time[-1]:.2f}s")
    #
    # anim = animate_path_tracking(
    #     path5, result5,
    #     obstacles=obstacles5,
    #     bounds=bounds,
    #     waypoints=waypoints5,
    #     speedup=1.0,
    #     title="Example 5: Animated Path Tracking (bilbo2 lab config)",
    # )
    # plt.show()

    # ------------------------------------------------------------------
    # Example 6: Animated path tracking
    # ------------------------------------------------------------------
    print("\n=== Example 5: Animated path tracking ===")
    print("  (close the animation window to exit)")

    obstacles5 = [
        CircleObstacle(1.5, 1.0, 0.25),
        BoxObstacle(1.5, 2.2, 0.8, 0.3, psi=0.3),
    ]

    waypoints5 = [Waypoint(0.1, 1.0, weight=1.0),
                  Waypoint(1.0, 1.0, weight=1.0),
                  Waypoint(1.5, 0.5, weight=1.0)]

    path5 = plan_path(
        start=(0.1, 0.1),
        end=(2.7, 2.7),
        waypoints=waypoints5,
        obstacles=obstacles5,
        bounds=bounds,
        seed=42,
        smoothing=0.2
    )
    print(f"  Path: {len(path5)} points")

    # Parameters from bilbo2 lab config (configs/control/bilbo2/lab.yaml)
    bilbo2_lab = dict(
        max_speed=0.6,
        kp_angular=8.0,
        ki_angular=0.0,
        kp_linear=0.0,  # unused when decel_limit > 0
        kd_linear=0.5,
        max_turn_rate=50.0,
        lookahead_min=0.03,
        decel_limit=0.6,
        curvature_gain=0.05,
        curvature_lookahead=0.1,
        arrival_tolerance=0.05,
        arrival_dwell_time=0.5,
        stop_dwell_time=1.0,
    )

    result5 = simulate_path_tracking(path5, **bilbo2_lab)
    print(f"  Simulation: {result5.time[-1]:.2f}s")

    anim = animate_path_tracking(
        path5, result5,
        obstacles=obstacles5,
        bounds=bounds,
        waypoints=waypoints5,
        speedup=1.0,
        title="Example 5: Animated Path Tracking (bilbo2 lab config)",
    )
    plt.show()
