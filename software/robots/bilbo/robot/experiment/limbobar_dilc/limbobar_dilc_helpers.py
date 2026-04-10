"""
LimboBar DILC experiment plotting helpers.

Extends the DILC plotting helpers with limbo bar hit visualization.
"""
import base64
import io
import json
import math
from pathlib import Path

import matplotlib
import numpy as np
from markupsafe import Markup

from core.utils.plotting.plot import (
    Plot, PlotConfig,
    Axis, AxisConfig, LegendConfig,
    SeriesConfig,
)
from robots.bilbo.tools.plotting.bilbo_plot import (
    BILBO_2D_Plot, BILBO_2D_Plot_Config,
    Plotted_BILBO_Config, Plotted_BILBO_State, Plotted_BILBO_Model,
    CircleConfig, PathConfig, LabelConfig,
)


def _trial_colors(n_trials: int, total_trials: int | None = None):
    if total_trials is None:
        total_trials = n_trials
    cmap = matplotlib.colormaps['Blues']
    colors = []
    for i in range(n_trials):
        t = 0.25 + 0.75 * (i / max(total_trials - 1, 1))
        colors.append(cmap(t))
    return colors


def _get_trial_index(trial: dict, fallback: int) -> int:
    return trial.get('trial_index', trial.get('index', fallback))


def _get_output(trial: dict) -> list | None:
    return trial.get('theta') or trial.get('y')


def _get_change_percent(trial: dict, current_key: str, next_key: str) -> float | None:
    current = trial.get(current_key)
    nxt = trial.get(next_key)
    if current is None or nxt is None:
        return None
    current_arr = np.asarray(current)
    nxt_arr = np.asarray(nxt)
    base_norm = float(np.linalg.norm(current_arr))
    if base_norm < 1e-12:
        return None
    return float(np.linalg.norm(nxt_arr - current_arr) / base_norm) * 100


def plot_outputs(
        trials: list[dict],
        total_trials: int | None = None,
        reference: list | np.ndarray | None = None,
        show: bool = True,
) -> Plot:
    """Plot output trajectories with limbo bar hit markers."""
    if total_trials is None:
        total_trials = max(len(trials), 1)

    plot = Plot(1, 1, PlotConfig(size=(10, 5)), use_agg_backend=True)
    axis = Axis('output', AxisConfig(
        title='Output Trajectories',
        xlabel='Time [s]',
        ylabel='Output',
        legend=LegendConfig(loc='upper right'),
    ))
    plot.set_axis(1, 1, axis)

    colors = _trial_colors(len(trials), total_trials)

    ref = reference
    if ref is None:
        for trial in trials:
            ref = trial.get('reference')
            if ref is not None:
                break

    if ref is not None:
        t_ref = trials[0].get('t') if trials else None
        if t_ref is not None:
            axis.plot(t_ref, ref, SeriesConfig(
                color='black',
                linewidth=2.0,
                linestyle='--',
                label='Reference',
            ))

    for i, trial in enumerate(trials):
        output = _get_output(trial)
        t = trial.get('t')
        if output is None or t is None:
            continue
        hit = trial.get('limbo_bar_hit', False)
        label_parts = []
        if i in (0, len(trials) - 1):
            label_parts.append(f'Trial {_get_trial_index(trial, i) + 1}')
        if hit:
            label_parts.append('HIT')
        label = ' '.join(label_parts) if label_parts else None

        color = 'red' if hit else colors[i]
        linestyle = '--' if hit else '-'
        axis.plot(t, output, SeriesConfig(
            color=color,
            linewidth=1.2,
            linestyle=linestyle,
            label=label,
        ))

    if show:
        plot.show_temp_pdf()

    return plot


def plot_inputs(
        trials: list[dict],
        total_trials: int | None = None,
        show: bool = True,
) -> Plot:
    if total_trials is None:
        total_trials = max(len(trials), 1)

    plot = Plot(1, 1, PlotConfig(size=(10, 5)), use_agg_backend=True)
    axis = Axis('input', AxisConfig(
        title='Input Trajectories',
        xlabel='Time [s]',
        ylabel='Input',
        legend=LegendConfig(loc='upper right'),
    ))
    plot.set_axis(1, 1, axis)

    colors = _trial_colors(len(trials), total_trials)

    for i, trial in enumerate(trials):
        u = trial.get('u')
        t = trial.get('t')
        if u is None or t is None:
            continue
        label = f'Trial {_get_trial_index(trial, i) + 1}' if i in (0, len(trials) - 1) else None
        axis.plot(t, u, SeriesConfig(
            color=colors[i],
            linewidth=1.2,
            label=label,
        ))

    if show:
        plot.show_temp_pdf()

    return plot


def plot_ilc_error_norms(
        trials: list[dict],
        total_trials: int | None = None,
        show: bool = True,
) -> Plot:
    if total_trials is None:
        total_trials = max(len(trials), 1)

    indices = [_get_trial_index(trial, i) + 1 for i, trial in enumerate(trials)]
    norms = [trial.get('e_norm_ilc', 0.0) for trial in trials]

    plot = Plot(1, 1, PlotConfig(size=(8, 4)), use_agg_backend=True)
    axis = Axis('ilc_error', AxisConfig(
        title='ILC Error Norm Progression',
        xlabel='Trial',
        ylabel=r'$\|e_{\mathrm{ILC}}\|$',
        xlim=(0.5, total_trials + 0.5),
        xticks=list(range(1, total_trials + 1)),
        legend=False,
    ))
    plot.set_axis(1, 1, axis)

    axis.plot(indices, norms, SeriesConfig(
        color='tab:blue',
        linewidth=1.5,
        marker='o',
        marker_size=5.0,
        label='ILC error norm',
    ))

    # Mark trials where limbo bar was hit
    hit_indices = [_get_trial_index(trial, i) + 1
                   for i, trial in enumerate(trials) if trial.get('limbo_bar_hit', False)]
    hit_norms = [trial.get('e_norm_ilc', 0.0)
                 for trial in trials if trial.get('limbo_bar_hit', False)]
    if hit_indices:
        axis.plot(hit_indices, hit_norms, SeriesConfig(
            color='red',
            linewidth=0,
            marker='x',
            marker_size=10.0,
            label='Limbo bar hit',
        ))

    if show:
        plot.show_temp_pdf()

    return plot


def plot_iml_error_norms(
        trials: list[dict],
        total_trials: int | None = None,
        show: bool = True,
) -> Plot:
    if total_trials is None:
        total_trials = max(len(trials), 1)

    indices = [_get_trial_index(trial, i) + 1 for i, trial in enumerate(trials)]
    norms = [trial.get('e_norm_iml', 0.0) for trial in trials]

    plot = Plot(1, 1, PlotConfig(size=(8, 4)), use_agg_backend=True)
    axis = Axis('iml_error', AxisConfig(
        title='IML Error Norm Progression',
        xlabel='Trial',
        ylabel=r'$\|e_{\mathrm{IML}}\|$',
        xlim=(0.5, total_trials + 0.5),
        xticks=list(range(1, total_trials + 1)),
        legend=False,
    ))
    plot.set_axis(1, 1, axis)

    axis.plot(indices, norms, SeriesConfig(
        color='tab:orange',
        linewidth=1.5,
        marker='o',
        marker_size=5.0,
        label='IML error norm',
    ))

    if show:
        plot.show_temp_pdf()

    return plot


def plot_limbo_bar_hits(
        trials: list[dict],
        total_trials: int | None = None,
        show: bool = True,
) -> Plot:
    """Plot limbo bar hit status per trial as a bar chart."""
    if total_trials is None:
        total_trials = max(len(trials), 1)

    indices = [_get_trial_index(trial, i) + 1 for i, trial in enumerate(trials)]
    hits = [1.0 if trial.get('limbo_bar_hit', False) else 0.0 for trial in trials]

    plot = Plot(1, 1, PlotConfig(size=(8, 4)), use_agg_backend=True)
    axis = Axis('limbo_hits', AxisConfig(
        title='Limbo Bar Hits',
        xlabel='Trial',
        ylabel='Hit',
        xlim=(0.5, total_trials + 0.5),
        xticks=list(range(1, total_trials + 1)),
        ylim=(-0.1, 1.5),
        legend=False,
    ))
    plot.set_axis(1, 1, axis)

    colors = ['red' if h > 0 else 'green' for h in hits]
    axis.ax.bar(indices, hits, color=colors, width=0.6)

    if show:
        plot.show_temp_pdf()

    return plot


# === Best Trial Sample Plots ===========================================================

_STATE_UNITS = {
    'theta': 'rad', 'theta_dot': 'rad/s',
    'v': 'm/s', 'psi': 'rad', 'psi_dot': 'rad/s',
    'x': 'm', 'y': 'm',
}

_DEFAULT_STATES = ['theta', 'theta_dot', 'v', 'psi', 'psi_dot', 'x', 'y']


def _time_vector_from_samples(samples: list[dict], control_dt: float = 0.01) -> np.ndarray:
    ticks = np.array([s.get('tick', i) for i, s in enumerate(samples)], dtype=float)
    return (ticks - ticks[0]) * control_dt


def _extract_state_from_samples(samples: list[dict], state_name: str) -> np.ndarray:
    values = []
    for s in samples:
        ll = s.get('lowlevel') or {}
        ll_est = ll.get('estimation') or {}
        ll_state = ll_est.get('state') or {}
        values.append(ll_state.get(state_name, 0.0) or 0.0)
    return np.array(values)


def _extract_control_from_samples(samples: list[dict], path: list[str]) -> np.ndarray:
    values = []
    for s in samples:
        ll = s.get('lowlevel') or {}
        ctrl = ll.get('control') or {}
        val = ctrl
        for key in path:
            val = (val.get(key) if isinstance(val, dict) else None) or {}
        values.append(val if isinstance(val, (int, float)) else 0.0)
    return np.array(values)


def plot_best_trial_states(samples: list[dict], states: list[str] | None = None) -> list[dict]:
    if states is None:
        states = _DEFAULT_STATES

    t = _time_vector_from_samples(samples)

    plots = []
    for state_name in states:
        y = _extract_state_from_samples(samples, state_name)
        if not np.any(y):
            continue

        unit = _STATE_UNITS.get(state_name, '')
        ylabel = f"{state_name} [{unit}]" if unit else state_name

        p = Plot(1, 1, PlotConfig(size=(10, 3.5)), use_agg_backend=True)
        axis = Axis(state_name, AxisConfig(
            xlabel='Time [s]',
            ylabel=ylabel,
            grid=True,
            label_font_size=14,
            tick_font_size=12,
            xlim=(t[0], t[-1]),
        ))
        p.set_axis(1, 1, axis)
        axis.plot(t, y, SeriesConfig(color='#2c3e50', linewidth=1.8))
        plots.append({'title': ylabel, 'image': p})

    return plots


def plot_best_trial_control(samples: list[dict]) -> list[dict]:
    t = _time_vector_from_samples(samples)

    def make_dual_plot(title, data1, data2, label1, label2, ylabel):
        p = Plot(1, 1, PlotConfig(size=(10, 3.5)), use_agg_backend=True)
        axis = Axis('main', AxisConfig(
            xlabel='Time [s]',
            ylabel=ylabel,
            grid=True,
            label_font_size=14,
            tick_font_size=12,
            xlim=(t[0], t[-1]),
            legend=True,
        ))
        p.set_axis(1, 1, axis)
        axis.plot(t, data1, SeriesConfig(color='#e74c3c', linewidth=1.8, label=label1))
        axis.plot(t, data2, SeriesConfig(color='#3498db', linewidth=1.8, label=label2))
        return p

    plots = []

    inp_l = _extract_control_from_samples(samples, ['input_ext', 'u_left'])
    inp_r = _extract_control_from_samples(samples, ['input_ext', 'u_right'])
    if np.any(inp_l) or np.any(inp_r):
        plots.append({
            'title': 'External Input',
            'image': make_dual_plot('External Input', inp_l, inp_r, 'left', 'right', 'u'),
        })

    bal_1 = _extract_control_from_samples(samples, ['balancing_output', 'u_1'])
    bal_2 = _extract_control_from_samples(samples, ['balancing_output', 'u_2'])
    if np.any(bal_1) or np.any(bal_2):
        plots.append({
            'title': 'Balancing Output',
            'image': make_dual_plot('Balancing Output', bal_1, bal_2, 'left', 'right', 'u'),
        })

    out_l = _extract_control_from_samples(samples, ['output', 'u_left'])
    out_r = _extract_control_from_samples(samples, ['output', 'u_right'])
    if np.any(out_l) or np.any(out_r):
        plots.append({
            'title': 'Control Output',
            'image': make_dual_plot('Control Output', out_l, out_r, 'left', 'right', 'u'),
        })

    return plots


# === Trial Side-View Plots =============================================================

_FALLBACK_WHEEL_RADIUS = 0.06
_FALLBACK_BODY_HEIGHT = 0.185
_FALLBACK_BODY_DEPTH = 0.085


def _get_robot_dimensions(robot_config: dict | None) -> tuple[float, float, float]:
    """Extract wheel_radius, body_height, and body_depth from robot_config.model, with fallbacks."""
    model = {}
    if isinstance(robot_config, dict):
        model = robot_config.get('model', {}) or {}

    wheel_diameter = model.get('wheel_diameter', 0)
    wheel_radius = wheel_diameter / 2 if wheel_diameter > 0 else _FALLBACK_WHEEL_RADIUS

    body_height = model.get('height', 0)
    if not body_height or body_height <= 0:
        body_height = _FALLBACK_BODY_HEIGHT

    body_depth = model.get('depth', 0)
    if not body_depth or body_depth <= 0:
        body_depth = _FALLBACK_BODY_DEPTH

    return wheel_radius, body_height, body_depth


def plot_trial_side_view(
        trial: dict,
        trial_index: int,
        limbo_bar_settings: dict,
        wheel_radius: float = _FALLBACK_WHEEL_RADIUS,
        body_height: float = _FALLBACK_BODY_HEIGHT,
        body_depth: float = _FALLBACK_BODY_DEPTH,
        x_range: tuple[float, float] | None = None,
) -> 'BILBO_2D_Plot | None':
    """Plot a 2D side-view for a single trial showing the upper-point trajectory and limbo bar.

    Args:
        trial: Trial dict with 'samples' (lowlevel data) and optional 'limbo_bar_hit_data'.
        trial_index: 1-based trial index (for the title).
        limbo_bar_settings: Dict with 'start_x', 'end_x', 'height' from experiment settings.
        wheel_radius: Robot wheel radius in meters.
        body_height: Robot body height in meters (from axle to top).
        body_depth: Robot body depth in meters (x-direction, side-view width).
        x_range: Fixed (x_min, x_max) range for consistent aspect ratio across trials.
            If None, auto-computed from trajectory data.

    Returns:
        BILBO_2D_Plot instance, or None if no samples available.
    """
    samples = trial.get('samples')
    if not samples:
        return None

    # Extract x and theta from lowlevel samples
    x_vals = []
    theta_vals = []
    for s in samples:
        ll = s.get('lowlevel') or {}
        ll_est = ll.get('estimation') or {}
        ll_state = ll_est.get('state') or {}
        x_vals.append(ll_state.get('x', 0.0) or 0.0)
        theta_vals.append(ll_state.get('theta', 0.0) or 0.0)

    if not x_vals:
        return None

    x_arr = np.array(x_vals)
    theta_arr = np.array(theta_vals)

    # Compute upper-point trajectory
    upper_x = x_arr + body_height * np.sin(theta_arr)
    upper_z = wheel_radius + body_height * np.cos(theta_arr)

    # Limbo bar position
    bar_start_x = limbo_bar_settings.get('start_x', 0)
    bar_end_x = limbo_bar_settings.get('end_x', bar_start_x)
    bar_x = (bar_start_x + bar_end_x) / 2
    bar_height = limbo_bar_settings.get('height', 0.2)

    # Determine x range
    if x_range is None:
        all_x = np.concatenate([x_arr, upper_x, [bar_x]])
        x_min = float(np.min(all_x)) - 0.1
        x_max = float(np.max(all_x)) + 0.1
    else:
        x_min, x_max = x_range

    hit = trial.get('limbo_bar_hit', False)
    hit_data = trial.get('limbo_bar_hit_data')

    title = f"Trial {trial_index}"
    if hit:
        title += " — HIT"
    else:
        title += " — OK"

    plot = BILBO_2D_Plot(BILBO_2D_Plot_Config(
        x_range=(x_min, x_max),
        fig_width=10,
        min_fig_height=4.0,
        title=title,
        show_x_axis=True,
    ))

    # a) Upper-point trajectory
    path_color = '#e74c3c' if hit else '#3498db'
    plot.add_path(
        upper_x, upper_z,
        PathConfig(
            color=path_color,
            width=2.0,
            gradient=True,
            gradient_start_color=(0.7, 0.85, 1.0),
            gradient_end_color=path_color,
            zorder=6,
        ),
    )

    # b) Limbo bar as circle with 1cm diameter
    plot.add_circle(CircleConfig(
        position=(bar_x, bar_height),
        radius=0.005,
        color='#e74c3c',
        edge_color='#c0392b',
        edge_width=1.5,
        zorder=8,
    ))
    # Label the bar
    plot.add_label(
        'bar', (bar_x, bar_height + 0.025),
        LabelConfig(
            fontsize=8,
            color='#7f8c8d',
            ha='center',
            va='bottom',
        ),
    )

    # c) Draw robot at the relevant pose
    bilbo_model = Plotted_BILBO_Model(
        wheel_radius=wheel_radius,
        body_height=body_height,
        body_width=body_depth,
    )

    if hit and hit_data:
        # HIT: draw robot at exact hit pose (red)
        hit_x = hit_data.get('x', 0.0)
        hit_theta = hit_data.get('theta', 0.0)
        plot.add_bilbo(
            Plotted_BILBO_Config(
                model=bilbo_model,
                body_color=(0.9, 0.3, 0.3),
                body_opacity=0.7,
            ),
            Plotted_BILBO_State(x=hit_x, theta=hit_theta),
        )
    else:
        # PASS: draw robot at the instant closest to hitting the bar
        dist_sq = (upper_x - bar_x) ** 2 + (upper_z - bar_height) ** 2
        closest_idx = int(np.argmin(dist_sq))
        plot.add_bilbo(
            Plotted_BILBO_Config(
                model=bilbo_model,
                body_color=(0.3, 0.75, 0.3),
                body_opacity=0.5,
            ),
            Plotted_BILBO_State(x=float(x_arr[closest_idx]), theta=float(theta_arr[closest_idx])),
        )

    plot.draw()
    return plot


def plot_trial_side_views(
        trials: list[dict],
        limbo_bar_settings: dict,
        robot_config: dict | None = None,
        testbed_size: dict | None = None,
        best_trial_index: int | None = None,
) -> list[dict]:
    """Generate side-view plots for all trials that have samples.

    Args:
        trials: List of trial dicts.
        limbo_bar_settings: Limbo bar geometry dict from experiment settings.
        robot_config: Robot config dict (from meta.robot_config) for dimensions.
        testbed_size: Dict with 'x_min', 'x_max' from testbed config for consistent x-range.
        best_trial_index: 1-based index of the best trial (lowest ILC error).

    Returns:
        List of dicts with 'title', 'image' (BILBO_2D_Plot), 'hit', 'passed', 'is_best' keys.
    """
    wheel_radius, body_height, body_depth = _get_robot_dimensions(robot_config)

    x_range = None
    if isinstance(testbed_size, dict) and 'x_min' in testbed_size and 'x_max' in testbed_size:
        x_range = (testbed_size['x_min'], testbed_size['x_max'])

    plots = []
    for i, trial in enumerate(trials):
        idx = _get_trial_index(trial, i) + 1
        p = plot_trial_side_view(trial, idx, limbo_bar_settings,
                                 wheel_radius=wheel_radius, body_height=body_height,
                                 body_depth=body_depth, x_range=x_range)
        if p is not None:
            plots.append({
                'title': f"Trial {idx}",
                'image': p,
                'hit': trial.get('limbo_bar_hit', False),
                'passed': trial.get('limbo_bar_passed'),
                'is_best': idx == best_trial_index,
            })
    return plots


# === Report Generation ================================================================

def generate_limbobar_dilc_report(
        experiment_data,
        output: str | None = None,
        format: str = 'html',
        show: bool = True,
) -> 'Report':
    """Generate an HTML/PDF report for a LimboBar DILC experiment.

    Parameters
    ----------
    experiment_data : str | dict | LimboBar_DILC_Results | LimboBar_DILC_Experiment
        Experiment data source.
    output : str | None
        Output file path.
    format : str
        Output format: 'html' or 'pdf'.
    show : bool
        If True and output is None, opens the report in a viewer.
    """
    from core.utils.report import Report
    from robots.bilbo.robot.experiment.limbobar_dilc.limbobar_dilc import (
        LimboBar_DILC_Results, LimboBar_DILC_Experiment,
    )

    if isinstance(experiment_data, str):
        with open(experiment_data, 'r') as f:
            results_dict = json.load(f)
        trials = results_dict.get('trials', [])
        meta = results_dict.get('meta', {})
        state = results_dict.get('state', 'UNKNOWN')
    elif isinstance(experiment_data, LimboBar_DILC_Results):
        trials = experiment_data.trials
        meta = {
            'robot_id': experiment_data.meta.robot_id,
            'date': experiment_data.meta.date,
            'settings': experiment_data.meta.settings,
            'logs': experiment_data.meta.logs,
            'robot_config': experiment_data.meta.robot_config,
            'testbed_size': experiment_data.meta.testbed_size,
        }
        state = experiment_data.state
    elif isinstance(experiment_data, LimboBar_DILC_Experiment):
        if experiment_data.results is not None and experiment_data.results.trials:
            trials = experiment_data.results.trials
            meta = {
                'robot_id': experiment_data.results.meta.robot_id,
                'date': experiment_data.results.meta.date,
                'settings': experiment_data.results.meta.settings,
                'logs': experiment_data.results.meta.logs,
                'robot_config': experiment_data.results.meta.robot_config,
                'testbed_size': experiment_data.results.meta.testbed_size,
            }
            state = experiment_data.results.state
        else:
            import dataclasses as dc
            trials = [dc.asdict(t) for t in experiment_data.trials]
            meta = {}
            state = experiment_data.state.value if experiment_data.state else 'UNKNOWN'
    elif isinstance(experiment_data, dict):
        trials = experiment_data.get('trials', [])
        meta = experiment_data.get('meta', {})
        state = experiment_data.get('state', 'UNKNOWN')
    else:
        raise TypeError(f"Unsupported experiment_data type: {type(experiment_data)}")

    if not trials:
        raise ValueError("No trial data available for report generation")

    settings_dict = meta.get('settings', {})
    if isinstance(settings_dict, str):
        settings_dict = {}
    exp_id = settings_dict.get('id', 'limbobar_dilc')
    description = settings_dict.get('description', '')
    total_trials = settings_dict.get('J', len(trials))
    Ts = settings_dict.get('Ts', None)
    date = meta.get('date', '')

    first_t = trials[0].get('t')
    duration_per_trial = first_t[-1] if first_t else None

    is_success = state in ('FINISHED', 'finished')
    is_error = state in ('ERROR', 'error')

    # Limbo bar summary
    limbo_bar_settings = settings_dict.get('limbo_bar', {})
    limbo_bar_height = limbo_bar_settings.get('height', '?') if isinstance(limbo_bar_settings, dict) else '?'
    total_hits = sum(1 for t in trials if t.get('limbo_bar_hit', False))
    has_target_zone = any(t.get('limbo_bar_passed') is not None for t in trials)
    total_passes = sum(1 for t in trials if t.get('limbo_bar_passed') is True) if has_target_zone else 0

    status_info = {
        'status': state,
        'is_success': is_success,
        'is_error': is_error,
        'status_label': 'Success' if is_success else state.upper() if isinstance(state, str) else str(state),
        'status_class': 'success' if is_success else 'error' if is_error else 'warning',
        'error_message': None,
    }

    # Build norms table with hit column
    norms_table = []
    for i, trial in enumerate(trials):
        e_ilc = trial.get('e_norm_ilc', 0.0)
        e_iml = trial.get('e_norm_iml', 0.0)
        hit = trial.get('limbo_bar_hit', False)

        e_ilc_change = None
        e_iml_change = None
        if i > 0:
            prev_ilc = trials[i - 1].get('e_norm_ilc', 0.0)
            prev_iml = trials[i - 1].get('e_norm_iml', 0.0)
            if prev_ilc > 0:
                e_ilc_change = ((e_ilc - prev_ilc) / prev_ilc) * 100
            if prev_iml > 0:
                e_iml_change = ((e_iml - prev_iml) / prev_iml) * 100

        passed = trial.get('limbo_bar_passed')

        norms_table.append({
            'trial': _get_trial_index(trial, i) + 1,
            'e_ilc': e_ilc,
            'e_iml': e_iml,
            'e_ilc_change': e_ilc_change,
            'e_iml_change': e_iml_change,
            'input_change_pct': _get_change_percent(trial, 'u', 'u_p1'),
            'model_change_pct': _get_change_percent(trial, 'm', 'm_p1'),
            'limbo_bar_hit': hit,
            'limbo_bar_passed': passed,
        })

    reference = settings_dict.get('reference', None)

    p_outputs = plot_outputs(trials, total_trials=total_trials, reference=reference, show=False)
    p_inputs = plot_inputs(trials, total_trials=total_trials, show=False)
    p_ilc = plot_ilc_error_norms(trials, total_trials=total_trials, show=False)
    p_iml = plot_iml_error_norms(trials, total_trials=total_trials, show=False)

    best_trial_state_plots = []
    best_trial_control_plots = []
    best_trial_index = None

    trials_with_samples = [t for t in trials if t.get('samples')]
    if trials_with_samples:
        best_trial = min(trials_with_samples, key=lambda t: t.get('e_norm_ilc', float('inf')))
        best_trial_index = _get_trial_index(best_trial, 0) + 1
        best_samples = best_trial['samples']

        # Mark the best trial in the norms table
        for row in norms_table:
            row['is_best'] = (row['trial'] == best_trial_index)
        best_trial_state_plots = plot_best_trial_states(best_samples)
        best_trial_control_plots = plot_best_trial_control(best_samples)

    # --- Trial side-view plots ----------------------------------------
    robot_config = meta.get('robot_config')
    testbed_size = meta.get('testbed_size')
    trial_side_view_plots = []
    if trials_with_samples and limbo_bar_settings:
        raw_plots = plot_trial_side_views(trials, limbo_bar_settings,
                                          robot_config=robot_config, testbed_size=testbed_size,
                                          best_trial_index=best_trial_index)
        for p in raw_plots:
            # Convert BILBO_2D_Plot (matplotlib figure) to embedded img tag
            bilbo_plot = p['image']
            buf = io.BytesIO()
            bilbo_plot.fig.savefig(buf, format='png', dpi=120, bbox_inches='tight',
                                   facecolor=bilbo_plot.fig.get_facecolor())
            buf.seek(0)
            b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            buf.close()
            bilbo_plot.close()
            trial_side_view_plots.append({
                'title': p['title'],
                'image': Markup(f'<img src="data:image/png;base64,{b64}" width="100%" />'),
                'hit': p['hit'],
                'passed': p['passed'],
                'is_best': p.get('is_best', False),
            })

    display_settings = {}
    if settings_dict:
        display_settings['Trials (J)'] = total_trials
        if Ts is not None:
            display_settings['Sampling Period (Ts)'] = f"{Ts}s"
        display_settings['Limbo Bar Height'] = f"{limbo_bar_height} m"
        display_settings['Limbo Bar Hits'] = f"{total_hits} / {len(trials)}"
        ic = settings_dict.get('initial_conditions', {})
        if ic:
            display_settings['Initial Conditions'] = (
                f"x={ic.get('x', 0)}, y={ic.get('y', 0)}, psi={ic.get('psi', 0)}"
            )
        ilp = settings_dict.get('input_lowpass', {})
        if ilp:
            display_settings['ILC Q-filter'] = (
                f"fc={ilp.get('fc', '?')}, L={ilp.get('L', '?')}, window={ilp.get('window', '?')}"
            )
        mlp = settings_dict.get('model_lowpass', {})
        if mlp:
            display_settings['IML Q-filter'] = (
                f"fc={mlp.get('fc', '?')}, L={mlp.get('L', '?')}, window={mlp.get('window', '?')}"
            )
        if 'ilc_gain' in settings_dict:
            display_settings['ILC Gain'] = settings_dict['ilc_gain']
        if 'iml_gain' in settings_dict:
            display_settings['IML Gain'] = settings_dict['iml_gain']
    if meta.get('robot_id'):
        display_settings['Robot'] = meta['robot_id']

    # --- Robot model info -----------------------------------------------
    robot_model_display = {}
    if isinstance(robot_config, dict):
        model = robot_config.get('model') or {}
        _model_fields = [
            ('Type', 'type', None),
            ('Wheel Diameter', 'wheel_diameter', 'm'),
            ('Height', 'height', 'm'),
            ('Width', 'width', 'm'),
            ('Depth', 'depth', 'm'),
            ('Distance Wheels', 'distance_wheels', 'm'),
            ('Vertical Offset', 'vertical_offset', 'm'),
            ('Mass', 'mass', 'kg'),
            ('L_cg', 'l_cg', 'm'),
            ('Theta Offset', 'theta_offset', 'rad'),
            ('Trajectory Delta', 'trajectory_delta', ''),
        ]
        for label, key, unit in _model_fields:
            val = model.get(key)
            if val is not None:
                robot_model_display[label] = f"{val} {unit}" if unit else str(val)
        general = robot_config.get('general') or {}
        if general.get('id'):
            robot_model_display = {'Robot ID': general['id'], **robot_model_display}
        if general.get('version'):
            robot_model_display['Version'] = general['version']

    LOG_LEVEL_NAMES = {10: 'DEBUG', 20: 'INFO', 25: 'IMPORTANT', 30: 'WARNING', 40: 'ERROR', 50: 'CRITICAL'}
    logs_raw = meta.get('logs', []) or []
    logs = []
    for log in logs_raw:
        level = log.get('level', 20)
        logs.append({
            'tick': log.get('tick', ''),
            'level': level,
            'level_name': LOG_LEVEL_NAMES.get(level, 'INFO'),
            'logger': log.get('logger', ''),
            'message': log.get('message', ''),
        })

    template_path = Path(__file__).parent / "limbobar_dilc_report_template.html"
    report = Report(template_path, plot_dpi=120, plot_width="100%")

    report.render(
        title=f"LimboBar DILC Report: {exp_id}",
        experiment_id=exp_id,
        description=description,
        date=date,
        status=status_info,
        completed_trials=len(trials),
        total_trials=total_trials,
        duration_per_trial=duration_per_trial,
        sampling_period=Ts,
        norms=norms_table,
        plot_outputs=p_outputs,
        plot_inputs=p_inputs,
        plot_ilc_error=p_ilc,
        plot_iml_error=p_iml,
        limbo_bar_height=limbo_bar_height,
        limbo_bar_total_hits=total_hits,
        has_target_zone=has_target_zone,
        limbo_bar_total_passes=total_passes,
        best_trial_index=best_trial_index,
        best_trial_state_plots=best_trial_state_plots,
        best_trial_control_plots=best_trial_control_plots,
        trial_side_view_plots=trial_side_view_plots,
        settings=display_settings,
        robot_model=robot_model_display,
        logs=logs,
    )

    if output:
        if format == 'pdf':
            report.save_pdf(output)
        else:
            report.save_html(output)
        if show:
            import webbrowser
            webbrowser.open(f'file://{Path(output).resolve()}')
    elif show:
        if format == 'pdf':
            report.show_pdf()
        else:
            report.show_html()

    return report
