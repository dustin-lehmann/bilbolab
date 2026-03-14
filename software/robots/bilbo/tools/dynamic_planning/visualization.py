"""Visualization functions for limbo passage planning results."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.animation import FuncAnimation

from robots.bilbo.utilities.plotting.bilbo_plot import (
    BILBO_2D_Plot, BILBO_2D_Plot_Config,
    Plotted_BILBO_Config, Plotted_BILBO_State,
    CircleConfig, PathConfig,
)
from .geometry import get_body_corners, LimboBar, LimboRectangle


def plot_scene(result, n_snapshots: int = 7) -> BILBO_2D_Plot:
    """Plot physical scene with robot snapshots at evenly-spaced times, limbo bars, and wheel path.

    Args:
        result: PlannerResult from LimboPlanner.plan().
        n_snapshots: Number of robot snapshots to show.

    Returns:
        BILBO_2D_Plot instance.
    """
    s = result.s
    theta = result.theta
    geom = result.geom

    # Determine x_range from trajectory
    s_min, s_max = s.min(), s.max()
    margin = 0.3
    x_range = (s_min - margin, s_max + margin)

    plot = BILBO_2D_Plot(
        x_range=x_range,
        fig_width=12,
        title='Limbo Bar Passage',
    )

    # Add obstacles
    for obs in result.bars:
        if isinstance(obs, LimboBar):
            plot.add_circle(
                position=(obs.x, obs.z),
                radius=obs.radius,
                color=(0.85, 0.2, 0.2),
                opacity=0.9,
                edge_color='darkred',
                edge_width=1.5,
                zorder=8,
            )
        elif isinstance(obs, LimboRectangle):
            plot.add_rectangle(
                position=(obs.x_min, obs.z_min),
                width=obs.width,
                height=obs.height,
                color=(0.85, 0.2, 0.2),
                opacity=0.9,
                edge_color='darkred',
                edge_width=1.5,
                zorder=8,
            )

    # Add wheel trajectory as gradient path
    wheel_z = np.full_like(s, geom.wheel_radius)
    plot.add_path(
        x=s, y=wheel_z,
        gradient=True,
        gradient_start_color=(0.2, 0.6, 1.0),
        gradient_end_color=(0.1, 0.3, 0.7),
        width=2.5,
        opacity=0.6,
        zorder=3,
    )

    # Add robot snapshots at evenly spaced times
    snapshot_indices = np.linspace(0, len(s) - 1, n_snapshots, dtype=int)
    for idx in snapshot_indices:
        opacity = 0.3 + 0.6 * (idx / (len(s) - 1))
        config = Plotted_BILBO_Config(body_opacity=opacity)
        state = Plotted_BILBO_State(x=s[idx], theta=theta[idx])
        plot.add_bilbo(config=config, state=state)

    return plot


def plot_cspace(result, ax: plt.Axes = None) -> plt.Axes:
    """Plot C-space with occupancy, RRT tree, paths, and dynamic trajectory.

    Args:
        result: PlannerResult from LimboPlanner.plan().
        ax: Matplotlib axes (created if None).

    Returns:
        Axes with the C-space plot.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 7))

    cspace = result.cspace
    rrt = result.rrt_result

    # C-space occupancy heatmap
    extent = [
        cspace.config.s_range[0], cspace.config.s_range[1],
        np.degrees(cspace.config.theta_range[0]),
        np.degrees(cspace.config.theta_range[1]),
    ]
    ax.imshow(
        cspace.occupied.T,
        origin='lower', aspect='auto', extent=extent,
        cmap='Reds', alpha=0.5, interpolation='nearest',
    )

    # RRT tree edges
    for (s1, t1), (s2, t2) in rrt.tree_edges:
        ax.plot([s1, s2], [np.degrees(t1), np.degrees(t2)],
                color=(0.7, 0.7, 0.7), linewidth=0.3, alpha=0.4)

    # Raw path (geometric RRT only)
    if hasattr(rrt, 'raw_path') and rrt.raw_path is not None:
        ax.plot(rrt.raw_path[:, 0], np.degrees(rrt.raw_path[:, 1]),
                'o-', color='orange', linewidth=1.5, markersize=3,
                label='RRT raw path', alpha=0.7)

    # Smoothed path (geometric RRT only)
    if hasattr(rrt, 'smoothed_path') and rrt.smoothed_path is not None:
        ax.plot(rrt.smoothed_path[:, 0], np.degrees(rrt.smoothed_path[:, 1]),
                's-', color='limegreen', linewidth=2, markersize=4,
                label='Smoothed path')

    # Dynamic trajectory overlay
    ax.plot(result.s, np.degrees(result.theta),
            '-', color='blue', linewidth=2.5, label='Dynamic trajectory')

    # Start and goal markers
    cfg = result.config
    ax.plot(cfg.s_start, np.degrees(cfg.theta_start), 'go', markersize=12,
            label='Start', zorder=20)
    ax.plot(cfg.s_end, np.degrees(cfg.theta_end), 'r*', markersize=15,
            label='Goal', zorder=20)

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_xlabel('s [m]')
    ax.set_ylabel('theta [deg]')
    ax.set_title('Configuration Space')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.3)

    return ax


def plot_trajectory(result, axes: np.ndarray = None) -> tuple[plt.Figure, np.ndarray]:
    """Plot 4-panel time series: s(t), theta(t), v(t), u_ff(t).

    Args:
        result: PlannerResult from LimboPlanner.plan().
        axes: (4,) array of axes (created if None).

    Returns:
        (fig, axes) tuple.
    """
    if axes is None:
        fig, axes = plt.subplots(4, 1, figsize=(10, 10), sharex=True)
    else:
        fig = axes[0].figure

    t = result.t
    t_u = t[:-1]  # Input time (one shorter)

    # s(t)
    axes[0].plot(t, result.x_ref[:, 0], '--', color='gray', label='reference')
    axes[0].plot(t, result.s, '-', color='blue', linewidth=2, label='trajectory')
    axes[0].set_ylabel('s [m]')
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)
    axes[0].set_title('Trajectory Time Series')

    # theta(t)
    axes[1].plot(t, np.degrees(result.x_ref[:, 2]), '--', color='gray', label='reference')
    axes[1].plot(t, np.degrees(result.theta), '-', color='blue', linewidth=2, label='trajectory')
    axes[1].set_ylabel('theta [deg]')
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)

    # v(t)
    axes[2].plot(t, result.x_ref[:, 1], '--', color='gray', label='reference')
    axes[2].plot(t, result.v, '-', color='blue', linewidth=2, label='trajectory')
    axes[2].set_ylabel('v [m/s]')
    axes[2].legend(fontsize=8)
    axes[2].grid(True, alpha=0.3)

    # u_ff(t)
    u_plot = result.u_ff.ravel() if result.u_ff.ndim > 1 else result.u_ff
    axes[3].plot(t_u, u_plot, '-', color='red', linewidth=1.5, label='u_ff')
    axes[3].set_ylabel('u_ff [Nm]')
    axes[3].set_xlabel('t [s]')
    axes[3].legend(fontsize=8)
    axes[3].grid(True, alpha=0.3)

    fig.tight_layout()
    return fig, axes


def animate(result, interval: int = 20, decimate: int = 5) -> FuncAnimation:
    """Create animation of the robot passing under limbo bars.

    Args:
        result: PlannerResult from LimboPlanner.plan().
        interval: Frame interval in ms.
        decimate: Show every N-th timestep to keep animation fast.

    Returns:
        FuncAnimation object.
    """
    s = result.s[::decimate]
    theta = result.theta[::decimate]
    geom = result.geom

    s_min, s_max = result.s.min(), result.s.max()
    margin = 0.3

    plot = BILBO_2D_Plot(
        x_range=(s_min - margin, s_max + margin),
        fig_width=12,
        title='Limbo Bar Passage',
    )

    # Add obstacles
    for obs in result.bars:
        if isinstance(obs, LimboBar):
            plot.add_circle(
                position=(obs.x, obs.z),
                radius=obs.radius,
                color=(0.85, 0.2, 0.2),
                opacity=0.9,
                edge_color='darkred',
                edge_width=1.5,
                zorder=8,
            )
        elif isinstance(obs, LimboRectangle):
            plot.add_rectangle(
                position=(obs.x_min, obs.z_min),
                width=obs.width,
                height=obs.height,
                color=(0.85, 0.2, 0.2),
                opacity=0.9,
                edge_color='darkred',
                edge_width=1.5,
                zorder=8,
            )

    # Add robot (will be updated each frame)
    bilbo = plot.add_bilbo(state=Plotted_BILBO_State(x=s[0], theta=theta[0]))

    plot.draw()
    fig = plot.fig
    ax = plot.ax

    # Wheel trail
    trail_line, = ax.plot([], [], '-', color='dodgerblue', linewidth=2, alpha=0.5, zorder=2)

    def update(frame):
        bilbo.set_state(x=s[frame], theta=theta[frame])
        bilbo.draw(ax)
        # Update trail
        trail_line.set_data(s[:frame + 1], np.full(frame + 1, geom.wheel_radius))
        return []

    anim = FuncAnimation(fig, update, frames=len(s), interval=interval, blit=False)
    return anim
