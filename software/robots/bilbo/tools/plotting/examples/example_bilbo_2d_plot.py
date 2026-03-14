"""
BILBO 2D Plot Examples

Demonstrates the BILBO_2D_Plot class for side-view visualization of BILBO robots,
including plot elements: rectangles, circles, dots, labels, and lines.
"""
import os

import numpy as np
import matplotlib.pyplot as plt

from robots.bilbo.utilities.plotting.bilbo_plot import (
    BILBO_2D_Plot,
    BILBO_2D_Plot_Config,
    Plotted_BILBO_Config,
    Plotted_BILBO_Model,
    Plotted_BILBO_State,
    RectangleConfig,
    CircleConfig,
    DotConfig,
    LabelConfig,
    LineConfig,
    PathConfig,
)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')


def _save_plot(plot: BILBO_2D_Plot, name: str):
    """Save a static plot as PNG and PDF."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plot.save_png(os.path.join(OUTPUT_DIR, f'{name}.png'))
    plot.save_pdf(os.path.join(OUTPUT_DIR, f'{name}.pdf'))


def _save_animation(anim, name: str, fps: int = 30):
    """Save an animation as MP4."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f'{name}.mp4')
    anim.save(path, writer='ffmpeg', fps=fps)
    print(f'Saved {path}')


def example_single_bilbo():
    """Single BILBO standing upright."""
    plot = BILBO_2D_Plot(x_range=(-0.5, 0.5), title="Single BILBO", show_x_axis=False,
                         background_color=[0.9, 0.9, 0.9])
    plot.add_bilbo(state=Plotted_BILBO_State(x=0, theta=0))
    _save_plot(plot, 'single_bilbo')
    plot.show()


def example_tilted():
    """Single BILBO leaning forward."""
    plot = BILBO_2D_Plot(x_range=(-0.5, 0.5), title="BILBO Tilted Forward")
    plot.add_bilbo(state=Plotted_BILBO_State(x=0, theta=np.deg2rad(20)))
    _save_plot(plot, 'tilted')
    plot.show()


def example_multiple_bilbos():
    """Multiple BILBOs at different positions and angles."""
    plot = BILBO_2D_Plot(x_range=(-1.0, 1.0), title="Multiple BILBOs")

    plot.add_bilbo(state=Plotted_BILBO_State(x=-0.6, theta=0), body_color=[0.2, 0.6, 0.2])
    plot.add_bilbo(state=Plotted_BILBO_State(x=0, theta=np.deg2rad(15)), body_color=[0.9, 0.3, 0.2])
    plot.add_bilbo(state=Plotted_BILBO_State(x=0.6, theta=np.deg2rad(-10)), body_color=[0.3, 0.5, 0.9])

    _save_plot(plot, 'multiple_bilbos')
    plot.show()


def example_fallen():
    """BILBO in various states including fallen over."""
    plot = BILBO_2D_Plot(x_range=(-1.2, 1.2), title="BILBO States: Upright, Tilted, Fallen")

    plot.add_bilbo(state=Plotted_BILBO_State(x=-0.7, theta=0), body_color=[0.3, 0.7, 0.3])
    plot.add_bilbo(state=Plotted_BILBO_State(x=0, theta=np.deg2rad(30)), body_color=[0.9, 0.7, 0.1])
    plot.add_bilbo(state=Plotted_BILBO_State(x=0.7, theta=np.deg2rad(90)), body_color=[0.9, 0.2, 0.2])

    _save_plot(plot, 'fallen')
    plot.show()


# ======================================================================================================================
# === PLOT ELEMENT EXAMPLES ============================================================================================
def example_obstacles():
    """BILBO navigating between rectangular and circular obstacles."""
    plot = BILBO_2D_Plot(x_range=(-1.0, 1.0), title="Obstacles")

    # Rectangular wall
    plot.add_rectangle(position=(-0.85, 0), width=0.1, height=0.2,
                       color='sienna', edge_color='saddlebrown', edge_width=1.5, opacity=0.9)

    # Circular obstacle on the floor
    plot.add_circle(position=(0.6, 0.08), radius=0.08,
                    color='slategray', edge_color='darkslategray', opacity=0.8)

    # Semi-transparent danger zone behind the robot
    plot.add_rectangle(position=(0.15, 0), width=0.3, height=0.3,
                       color='red', opacity=0.15, edge_color='red', edge_width=1.0, edge_style='--')

    plot.add_bilbo(state=Plotted_BILBO_State(x=-0.3, theta=np.deg2rad(5)))

    _save_plot(plot, 'obstacles')
    plot.show()


def example_dots_and_labels():
    """Annotated BILBO with dots marking key points and labels."""
    plot = BILBO_2D_Plot(x_range=(-0.6, 0.6), show_x_axis=False)

    bilbo = plot.add_bilbo(state=Plotted_BILBO_State(x=0, theta=np.deg2rad(10)))

    # Wheel center dot
    r = 0.065
    plot.add_dot(position=(0, r), color='red', size=0.008, zorder=20)
    plot.add_label('wheel center', (0, r), ha='left', va='bottom',
                   fontsize=8, color='red',
                   background=True, background_color='white', background_opacity=0.7,
                   zorder=20)

    # Center of gravity dot (approximate, along the body)
    cog_height = 0.10
    theta = np.deg2rad(10)
    cog_x = -np.sin(theta) * cog_height
    cog_y = r + np.cos(theta) * cog_height
    plot.add_dot(position=(cog_x, cog_y), color='darkgreen', size=0.008, zorder=20)
    plot.add_label('CoG', (cog_x, cog_y), ha='right', va='bottom',
                   fontsize=8, color='darkgreen',
                   background=True, background_color='white', background_opacity=0.7,
                   zorder=20)

    # Ground contact dot
    plot.add_dot(position=(0, 0), color='orange', size=0.006, zorder=20)
    plot.add_label('ground contact', (0, 0), ha='left', va='top',
                   fontsize=7, color='orange', zorder=20)

    _save_plot(plot, 'dots_and_labels')
    plot.show()


def example_lines():
    """Lines showing trajectories and dimensions."""
    plot = BILBO_2D_Plot(x_range=(-0.8, 0.8), title="Lines & Dimensions")

    plot.add_bilbo(state=Plotted_BILBO_State(x=0, theta=0))

    # Dimension line for body height
    r = 0.065
    h = 0.20
    plot.add_line(
        points=[(0.12, r), (0.12, r + h)],
        color='gray', width=1.0, style='-', zorder=15,
    )
    # Caps
    plot.add_line(points=[(0.10, r), (0.14, r)], color='gray', width=1.0, zorder=15)
    plot.add_line(points=[(0.10, r + h), (0.14, r + h)], color='gray', width=1.0, zorder=15)
    plot.add_label('200 mm', (0.15, r + h / 2), ha='left', va='center', fontsize=8, color='gray')

    # Trajectory path (dashed)
    xs = np.linspace(-0.6, 0.6, 50)
    ys = 0.005 * np.sin(8 * xs) - 0.005
    plot.add_line(
        points=list(zip(xs, ys)),
        color='dodgerblue', width=1.5, style='--', opacity=0.6, zorder=0,
    )
    plot.add_label('planned path', (0.4, -0.02), ha='center', va='top',
                   fontsize=7, color='dodgerblue')

    _save_plot(plot, 'lines')
    plot.show()


def example_zorder():
    """Demonstrates zorder: elements behind and in front of the robot."""
    plot = BILBO_2D_Plot(x_range=(-0.7, 0.7), title="Z-Order Demo", show_x_axis=False)

    # Background rectangle (behind robot, zorder < 10)
    plot.add_rectangle(position=(-0.15, 0), width=0.30, height=0.30,
                       color='lightyellow', edge_color='goldenrod', edge_width=1.5,
                       opacity=0.8, zorder=3)
    plot.add_label('behind', (0, 0.15), fontsize=8, color='goldenrod', opacity=0.7, zorder=4)

    plot.add_bilbo(state=Plotted_BILBO_State(x=0, theta=0))

    # Foreground circle (in front of robot, zorder > 10)
    plot.add_circle(position=(0.05, 0.12), radius=0.03,
                    color='red', edge_color='darkred', opacity=0.9, zorder=20)
    plot.add_label('in front', (0.05, 0.18), fontsize=8, color='darkred', zorder=21)

    _save_plot(plot, 'zorder')
    plot.show()


def example_styled_labels():
    """Various label styles: bold, italic, rotated, with backgrounds."""
    plot = BILBO_2D_Plot(x_range=(-0.8, 0.8), show_x_axis=False)

    plot.add_bilbo(state=Plotted_BILBO_State(x=0, theta=0), body_color='steelblue')

    plot.add_label('Bold', (-0.5, 0.22), font_weight='bold', fontsize=11, zorder=20)
    plot.add_label('Italic', (-0.5, 0.16), font_style='italic', fontsize=11, color='gray', zorder=20)
    plot.add_label('Boxed', (0.5, 0.22), fontsize=10,
                   background=True, background_color='lightyellow',
                   background_edge_color='orange', background_edge_width=1.0, zorder=20)
    plot.add_label(r'$\theta = 0$', (0.5, 0.14), fontsize=11, color='darkblue', zorder=20)
    plot.add_label('rotated', (0.5, 0.06), rotation=30, fontsize=8, color='purple', zorder=20)

    _save_plot(plot, 'styled_labels')
    plot.show()


def example_full_scene():
    """A complete scene with obstacles, annotations, and multiple robots."""
    plot = BILBO_2D_Plot(x_range=(-1.5, 1.5), title="Full Scene")

    # Walls
    plot.add_rectangle(position=(-1.45, 0), width=0.08, height=0.30,
                       color='dimgray', edge_color='black', opacity=0.9)
    plot.add_rectangle(position=(1.37, 0), width=0.08, height=0.30,
                       color='dimgray', edge_color='black', opacity=0.9)

    # Target zone
    plot.add_circle(position=(1.0, 0.01), radius=0.04,
                    color='limegreen', edge_color='green', edge_width=1.5, opacity=0.6, zorder=3)
    plot.add_label('target', (1.0, 0.09), fontsize=7, color='green',
                   background=True, background_opacity=0.6, zorder=20)

    # Obstacle
    plot.add_rectangle(position=(0.2, 0), width=0.15, height=0.12,
                       color='indianred', edge_color='darkred', opacity=0.7)

    # Planned path around obstacle
    path = [(-0.5, 0.01), (-0.1, 0.01), (0.1, 0.15), (0.45, 0.15), (0.7, 0.01), (1.0, 0.01)]
    plot.add_line(path, color='dodgerblue', width=1.2, style='--', opacity=0.5, zorder=3)

    # Start dot
    plot.add_dot(position=(-0.5, 0.01), color='green', size=0.012, zorder=15)

    # Robots
    plot.add_bilbo(state=Plotted_BILBO_State(x=-0.5, theta=np.deg2rad(3)), body_color=[0.8, 0.2, 0.2])
    plot.add_bilbo(state=Plotted_BILBO_State(x=0.7, theta=np.deg2rad(-2)), body_color=[0.2, 0.5, 0.8])

    _save_plot(plot, 'full_scene')
    plot.show()


# ======================================================================================================================
# === PATH EXAMPLES ====================================================================================================
def example_path_simple():
    """A simple solid-color path on the floor."""
    plot = BILBO_2D_Plot(x_range=(-1.0, 1.0), title="Simple Path")

    plot.add_bilbo(state=Plotted_BILBO_State(x=-0.7, theta=np.deg2rad(3)), body_color=[0.8, 0.2, 0.2])

    # Wavy path along the floor
    xs = np.linspace(-0.7, 0.8, 100)
    ys = 0.005 * np.sin(12 * xs)
    plot.add_path(xs, ys, color='navy', width=1.5, opacity=0.6, zorder=3)

    plot.add_dot(position=(-0.7, 0), color='green', size=0.01, zorder=15)
    plot.add_dot(position=(0.8, 0), color='red', size=0.01, zorder=15)
    plot.add_label('start', (-0.7, -0.015), fontsize=7, color='green', va='top')
    plot.add_label('goal', (0.8, -0.015), fontsize=7, color='red', va='top')

    _save_plot(plot, 'path_simple')
    plot.show()


def example_path_gradient():
    """Paths with color gradients showing time progression."""
    plot = BILBO_2D_Plot(x_range=(-1.0, 1.0), title="Gradient Paths")

    plot.add_bilbo(state=Plotted_BILBO_State(x=0, theta=0))

    # Custom start/end color gradient
    xs = np.linspace(-0.8, 0.8, 80)
    ys = 0.12 + 0.04 * np.sin(6 * xs)
    plot.add_path(xs, ys, gradient=True,
                  gradient_start_color='blue', gradient_end_color='red',
                  width=3, zorder=3)

    # Colormap gradient
    xs2 = np.linspace(-0.6, 0.6, 60)
    ys2 = 0.24 + 0.02 * np.cos(8 * xs2)
    plot.add_path(xs2, ys2, gradient=True, gradient_cmap='viridis',
                  width=2.5, opacity=0.8, zorder=3)

    _save_plot(plot, 'path_gradient')
    plot.show()


def example_path_comparison():
    """Comparing multiple paths (e.g. reference vs actual trajectory)."""
    plot = BILBO_2D_Plot(x_range=(-1.0, 1.0), title="Reference vs Actual")

    plot.add_bilbo(state=Plotted_BILBO_State(x=-0.7, theta=np.deg2rad(2)), body_color=[0.2, 0.5, 0.8])

    # Reference path (dashed)
    xs = np.linspace(-0.7, 0.8, 100)
    ys_ref = np.zeros_like(xs)
    plot.add_path(xs, ys_ref, color='gray', width=1.5, style='--', opacity=0.5, zorder=3)
    plot.add_label('reference', (0.82, 0), ha='left', fontsize=7, color='gray')

    # Actual path (solid, with noise)
    np.random.seed(42)
    ys_actual = np.cumsum(0.002 * np.random.randn(len(xs)))
    plot.add_path(xs, ys_actual, gradient=True,
                  gradient_start_color='dodgerblue', gradient_end_color='orangered',
                  width=2, zorder=4)
    plot.add_label('actual', (0.82, ys_actual[-1]), ha='left', fontsize=7, color='orangered')

    _save_plot(plot, 'path_comparison')
    plot.show()


# ======================================================================================================================
# === ANIMATION ========================================================================================================
def example_animation():
    """Animated BILBO swinging back and forth using matplotlib animation."""
    from matplotlib.animation import FuncAnimation

    plot = BILBO_2D_Plot(x_range=(-0.5, 0.5), title="BILBO Animation")
    bilbo = plot.add_bilbo(state=Plotted_BILBO_State(x=0, theta=0))
    plot.draw()

    def update(frame):
        t = frame / 30.0
        bilbo.set_state(x=0.15 * np.sin(0.5 * t), theta=0.3 * np.sin(2.0 * t))
        bilbo.draw(plot.ax)
        return []

    anim = FuncAnimation(plot.fig, update, frames=300, interval=33, blit=True)
    _save_animation(anim, 'animation', fps=30)
    plt.show()


def example_simulation():
    """Simulate a BILBO with the 2D dynamics and plot snapshots."""
    from robots.bilbo.simulation.model import (
        BILBO_Dynamics_2D, DEFAULT_BILBO_MODEL, BILBO_2D_State, BILBO_2D_POLES,
    )

    dynamics = BILBO_Dynamics_2D(model=DEFAULT_BILBO_MODEL, Ts=0.01)
    dynamics.polePlacement(poles=BILBO_2D_POLES)

    N = 300
    u = np.zeros(N)
    states = dynamics.simulate(u, x0=BILBO_2D_State(s=0, v=0, theta=np.deg2rad(30), theta_dot=0))

    snapshot_indices = [0, 30, 60, 120, 299]
    colors = ['red', 'orange', 'gold', 'limegreen', 'dodgerblue']

    plot = BILBO_2D_Plot(x_range=(-0.3, 0.3), title="BILBO Recovery from 30 deg Tilt (Snapshots)")

    for idx, color in zip(snapshot_indices, colors):
        state = states[idx]
        plot.add_bilbo(
            state=Plotted_BILBO_State(x=state.s, theta=state.theta),
            body_color=color, body_opacity=0.7,
        )

    _save_plot(plot, 'simulation_snapshots')
    plot.show()


def example_simulation_animated():
    """Simulate BILBO with a step input and animate the result."""
    from matplotlib.animation import FuncAnimation
    from robots.bilbo.simulation.model import (
        BILBO_Dynamics_2D, DEFAULT_BILBO_MODEL, BILBO_2D_State, BILBO_2D_POLES,
    )

    # Set up dynamics with the state feedback controller
    Ts = 0.01
    T_total = 5.0
    N = int(T_total / Ts)

    dynamics = BILBO_Dynamics_2D(model=DEFAULT_BILBO_MODEL, Ts=Ts)
    dynamics.polePlacement(poles=BILBO_2D_POLES)

    # Step input of -0.6 active between t=1s and t=4s
    u = np.zeros(N)
    t1, t2 = int(1.0 / Ts), int(4.0 / Ts)
    u[t1:t2] = -0.6

    # Simulate
    states = dynamics.simulate(u, x0=BILBO_2D_State(s=0, v=0, theta=0, theta_dot=0))

    # Pre-compute top-point trajectory for x_range sizing
    model = Plotted_BILBO_Model()
    x_top_all = [st.s + np.sin(st.theta) * model.body_height for st in states]
    y_top_all = [model.wheel_radius + np.cos(st.theta) * model.body_height for st in states]
    s_all = [st.s for st in states]

    x_lo = min(min(s_all), min(x_top_all))
    x_hi = max(max(s_all), max(x_top_all))
    margin = 0.15
    x_range = (x_lo - margin, x_hi + margin)

    # Build the plot
    plot = BILBO_2D_Plot(x_range=x_range, show_x_axis=True)
    bilbo = plot.add_bilbo(state=Plotted_BILBO_State(x=0, theta=0))
    plot.draw()

    # Add a line artist for the top-point trail (revealed progressively)
    (trail_line,) = plot.ax.plot([], [], color='orangered', linewidth=1.5, alpha=0.5, zorder=3)

    # Playback speed: skip frames to run at roughly real-time (Ts=10ms, target ~30fps -> step by 3)
    skip = 3
    frame_indices = list(range(0, len(states), skip))

    def update(frame_idx):
        st = states[frame_idx]
        bilbo.set_state(x=st.s, theta=st.theta)
        bilbo.draw(plot.ax)
        # Reveal the top-point trail up to the current frame
        trail_line.set_data(x_top_all[:frame_idx + 1], y_top_all[:frame_idx + 1])
        t = frame_idx * Ts
        plot.ax.set_title(f't = {t:.2f} s    input = {u[min(frame_idx, N - 1)]:.1f}')
        return []

    anim = FuncAnimation(plot.fig, update, frames=frame_indices, interval=33, blit=True)
    _save_animation(anim, 'simulation_animated', fps=30)
    plt.show()


if __name__ == '__main__':
    # example_single_bilbo()
    # example_tilted()
    # example_multiple_bilbos()
    # example_fallen()
    # example_obstacles()
    # example_dots_and_labels()
    # example_lines()
    # example_zorder()
    # example_styled_labels()
    example_full_scene()
    # example_path_simple()
    # example_path_gradient()
    # example_path_comparison()
    # example_animation()
    # example_simulation()
    # example_simulation_animated()
