"""
DILC experiment plotting helpers.

Provides intermediate and report plotting functions for DILC experiments
using the core.utils.plotting.plot framework.
"""
import json
from pathlib import Path

import matplotlib
import numpy as np

from core.utils.plotting.plot import (
    Plot, PlotConfig,
    Axis, AxisConfig, LegendConfig,
    SeriesConfig,
)


def _trial_colors(n_trials: int, total_trials: int | None = None):
    """Generate a list of colors with a gradient from light to dark.

    Uses the 'Blues' colormap, sampling from 0.25 (light) to 1.0 (dark)
    so that earlier trials are faint and later trials are vivid.

    Args:
        n_trials: Number of trials that will be plotted.
        total_trials: Total expected number of trials (for fixed color mapping).
            If None, defaults to n_trials.

    Returns:
        List of RGBA tuples, one per trial.
    """
    if total_trials is None:
        total_trials = n_trials
    cmap = matplotlib.colormaps['Blues']
    colors = []
    for i in range(n_trials):
        # Map trial index into [0.25, 1.0] range of the colormap
        t = 0.25 + 0.75 * (i / max(total_trials - 1, 1))
        colors.append(cmap(t))
    return colors


def _get_trial_index(trial: dict, fallback: int) -> int:
    """Get the trial index from a trial dict, checking both key conventions."""
    idx = trial.get('trial_index', trial.get('index', fallback))
    return idx


def _get_output(trial: dict) -> list | None:
    """Get the output trajectory, checking both 'theta' (host) and 'y' (robot) keys."""
    return trial.get('theta') or trial.get('y')


def _get_change_percent(trial: dict, current_key: str, next_key: str) -> float | None:
    """Compute relative change as percentage: ||next - current|| / ||current|| * 100.

    Returns None if the data is not available.
    """
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
    """Plot reference and output (theta/y) trajectories with trial progression gradient.

    Args:
        trials: List of trial dicts (from DILC_Results.trials or DILC_Trial_Data dicts).
            Each dict should have 't' (time) and 'theta' or 'y' (output).
        total_trials: Total number of trials for fixed color scaling. If None, uses len(trials).
        reference: Reference trajectory. If None, tries to find it inside trial dicts
            (key 'reference'), which is present in WiFi-received data but not in JSON files.
        show: If True, open a temporary PDF preview.

    Returns:
        The Plot instance.
    """
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

    # Resolve reference: explicit argument > per-trial key
    ref = reference
    if ref is None:
        for trial in trials:
            ref = trial.get('reference')
            if ref is not None:
                break

    # Plot reference using the time vector from the first trial
    if ref is not None:
        t_ref = trials[0].get('t') if trials else None
        if t_ref is not None:
            axis.plot(t_ref, ref, SeriesConfig(
                color='black',
                linewidth=2.0,
                linestyle='--',
                label='Reference',
            ))

    # Plot output trajectories with gradient
    for i, trial in enumerate(trials):
        output = _get_output(trial)
        t = trial.get('t')
        if output is None or t is None:
            continue
        label = f'Trial {_get_trial_index(trial, i) + 1}' if i in (0, len(trials) - 1) else None
        axis.plot(t, output, SeriesConfig(
            color=colors[i],
            linewidth=1.2,
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
    """Plot input trajectories with trial progression gradient.

    Args:
        trials: List of trial dicts. Each dict should have 't' (time) and 'u' (input).
        total_trials: Total number of trials for fixed color scaling.
        show: If True, open a temporary PDF preview.

    Returns:
        The Plot instance.
    """
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
    """Plot ILC tracking error norm progression across trials.

    Args:
        trials: List of trial dicts. Each should have 'trial_index' and 'e_norm_ilc'.
        total_trials: Total expected trials (fixes the x-axis range). If None, uses len(trials).
        show: If True, open a temporary PDF preview.

    Returns:
        The Plot instance.
    """
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

    if show:
        plot.show_temp_pdf()

    return plot


def plot_iml_error_norms(
        trials: list[dict],
        total_trials: int | None = None,
        show: bool = True,
) -> Plot:
    """Plot IML model error norm progression across trials.

    Args:
        trials: List of trial dicts. Each should have 'trial_index' and 'e_norm_iml'.
        total_trials: Total expected trials (fixes the x-axis range). If None, uses len(trials).
        show: If True, open a temporary PDF preview.

    Returns:
        The Plot instance.
    """
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


# === Best Trial Sample Plots ===========================================================

# State definitions for axis labels
_STATE_UNITS = {
    'theta': 'rad', 'theta_dot': 'rad/s',
    'v': 'm/s', 'psi': 'rad', 'psi_dot': 'rad/s',
    'x': 'm', 'y': 'm',
}

_DEFAULT_STATES = ['theta', 'theta_dot', 'v', 'psi', 'psi_dot', 'x', 'y']


def _time_vector_from_samples(samples: list[dict], control_dt: float = 0.01) -> np.ndarray:
    """Build a time vector from sample tick values.

    Each sample has a 'tick' field (absolute tick number at 100 Hz).
    We convert to seconds relative to the first sample.
    """
    ticks = np.array([s.get('tick', i) for i, s in enumerate(samples)], dtype=float)
    return (ticks - ticks[0]) * control_dt


def _extract_state_from_samples(samples: list[dict], state_name: str) -> np.ndarray:
    """Extract a state variable from lowlevel.estimation.state in sample dicts."""
    values = []
    for s in samples:
        ll = s.get('lowlevel') or {}
        ll_est = ll.get('estimation') or {}
        ll_state = ll_est.get('state') or {}
        values.append(ll_state.get(state_name, 0.0) or 0.0)
    return np.array(values)


def _extract_control_from_samples(samples: list[dict], path: list[str]) -> np.ndarray:
    """Extract a control variable from lowlevel.control in sample dicts."""
    values = []
    for s in samples:
        ll = s.get('lowlevel') or {}
        ctrl = ll.get('control') or {}
        val = ctrl
        for key in path:
            val = (val.get(key) if isinstance(val, dict) else None) or {}
        values.append(val if isinstance(val, (int, float)) else 0.0)
    return np.array(values)


def plot_best_trial_states(
        samples: list[dict],
        states: list[str] | None = None,
) -> list[dict]:
    """Plot state variables from the best trial's lowlevel samples.

    Args:
        samples: List of sample dicts from the best trial.
        states: State names to plot. Defaults to all standard states.

    Returns:
        List of dicts with 'title' and 'image' (Plot) keys.
    """
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


def plot_best_trial_control(
        samples: list[dict],
) -> list[dict]:
    """Plot control outputs from the best trial's lowlevel samples.

    Plots (when non-zero): external input, balancing output, control output.

    Args:
        samples: List of sample dicts from the best trial.

    Returns:
        List of dicts with 'title' and 'image' (Plot) keys.
    """
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

    # External input
    inp_l = _extract_control_from_samples(samples, ['input_ext', 'u_left'])
    inp_r = _extract_control_from_samples(samples, ['input_ext', 'u_right'])
    if np.any(inp_l) or np.any(inp_r):
        plots.append({
            'title': 'External Input',
            'image': make_dual_plot('External Input', inp_l, inp_r, 'left', 'right', 'u'),
        })

    # Balancing output
    bal_1 = _extract_control_from_samples(samples, ['balancing_output', 'u_1'])
    bal_2 = _extract_control_from_samples(samples, ['balancing_output', 'u_2'])
    if np.any(bal_1) or np.any(bal_2):
        plots.append({
            'title': 'Balancing Output',
            'image': make_dual_plot('Balancing Output', bal_1, bal_2, 'left', 'right', 'u'),
        })

    # Control output (final motor command)
    out_l = _extract_control_from_samples(samples, ['output', 'u_left'])
    out_r = _extract_control_from_samples(samples, ['output', 'u_right'])
    if np.any(out_l) or np.any(out_r):
        plots.append({
            'title': 'Control Output',
            'image': make_dual_plot('Control Output', out_l, out_r, 'left', 'right', 'u'),
        })

    return plots


# === Report Generation ================================================================

def generate_dilc_report(
        experiment_data,
        output: str | None = None,
        format: str = 'html',
        show: bool = True,
) -> 'Report':
    """Generate an HTML/PDF report for a DILC experiment.

    Parameters
    ----------
    experiment_data : str | dict | DILC_Results | DILC_Experiment
        Experiment data source:
        - str: Path to the DILC results JSON file
        - dict: Raw results dict (with 'meta', 'state', 'trials' keys)
        - DILC_Results: Parsed results dataclass
        - DILC_Experiment: Live experiment instance (uses .results or .trials)
    output : str | None
        Output file path. If None and show=True, opens in browser/viewer.
    format : str
        Output format: 'html' or 'pdf'.
    show : bool
        If True and output is None, opens the report in a viewer.

    Returns
    -------
    Report
        The Report object.
    """
    from core.utils.report import Report
    from robots.bilbo.robot.experiment.dilc.dilc import (
        DILC_Results, DILC_Experiment,
    )

    # --- Resolve experiment data into trials list and metadata ----
    if isinstance(experiment_data, str):
        with open(experiment_data, 'r') as f:
            results_dict = json.load(f)
        trials = results_dict.get('trials', [])
        meta = results_dict.get('meta', {})
        state = results_dict.get('state', 'UNKNOWN')
    elif isinstance(experiment_data, DILC_Results):
        trials = experiment_data.trials
        meta = {
            'robot_id': experiment_data.meta.robot_id,
            'date': experiment_data.meta.date,
            'settings': experiment_data.meta.settings,
            'logs': experiment_data.meta.logs,
        }
        state = experiment_data.state
    elif isinstance(experiment_data, DILC_Experiment):
        if experiment_data.results is not None and experiment_data.results.trials:
            trials = experiment_data.results.trials
            meta = {
                'robot_id': experiment_data.results.meta.robot_id,
                'date': experiment_data.results.meta.date,
                'settings': experiment_data.results.meta.settings,
                'logs': experiment_data.results.meta.logs,
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

    # --- Extract settings -----------------------------------------
    settings_dict = meta.get('settings', {})
    exp_id = settings_dict.get('id', 'dilc')
    description = settings_dict.get('description', '')
    total_trials = settings_dict.get('J', len(trials))
    Ts = settings_dict.get('Ts', None)
    date = meta.get('date', '')

    # Duration per trial from first trial's time vector
    first_t = trials[0].get('t')
    duration_per_trial = first_t[-1] if first_t else None

    # --- Determine success ----------------------------------------
    is_success = state in ('FINISHED', 'finished')
    is_error = state in ('ERROR', 'error')

    status_info = {
        'status': state,
        'is_success': is_success,
        'is_error': is_error,
        'status_label': 'Success' if is_success else state.upper() if isinstance(state, str) else str(state),
        'status_class': 'success' if is_success else 'error' if is_error else 'warning',
        'error_message': None,
    }

    # --- Build error norms table ----------------------------------
    norms_table = []
    for i, trial in enumerate(trials):
        e_ilc = trial.get('e_norm_ilc', 0.0)
        e_iml = trial.get('e_norm_iml', 0.0)

        # Compute percentage change from previous trial
        e_ilc_change = None
        e_iml_change = None
        if i > 0:
            prev_ilc = trials[i - 1].get('e_norm_ilc', 0.0)
            prev_iml = trials[i - 1].get('e_norm_iml', 0.0)
            if prev_ilc > 0:
                e_ilc_change = ((e_ilc - prev_ilc) / prev_ilc) * 100
            if prev_iml > 0:
                e_iml_change = ((e_iml - prev_iml) / prev_iml) * 100

        norms_table.append({
            'trial': _get_trial_index(trial, i) + 1,
            'e_ilc': e_ilc,
            'e_iml': e_iml,
            'e_ilc_change': e_ilc_change,
            'e_iml_change': e_iml_change,
            'input_change_pct': _get_change_percent(trial, 'u', 'u_p1'),
            'model_change_pct': _get_change_percent(trial, 'm', 'm_p1'),
        })

    # --- Extract reference from settings (not stored per-trial in JSON) ---
    reference = settings_dict.get('reference', None)

    # --- Generate plots (no preview, for embedding) ---------------
    p_outputs = plot_outputs(trials, total_trials=total_trials, reference=reference, show=False)
    p_inputs = plot_inputs(trials, total_trials=total_trials, show=False)
    p_ilc = plot_ilc_error_norms(trials, total_trials=total_trials, show=False)
    p_iml = plot_iml_error_norms(trials, total_trials=total_trials, show=False)

    # --- Best trial sample plots ----------------------------------
    best_trial_state_plots = []
    best_trial_control_plots = []
    best_trial_index = None

    # Find the trial with the lowest ILC error norm that has samples
    trials_with_samples = [t for t in trials if t.get('samples')]
    if trials_with_samples:
        best_trial = min(trials_with_samples, key=lambda t: t.get('e_norm_ilc', float('inf')))
        best_trial_index = _get_trial_index(best_trial, 0) + 1
        best_samples = best_trial['samples']
        best_trial_state_plots = plot_best_trial_states(best_samples)
        best_trial_control_plots = plot_best_trial_control(best_samples)

    # --- Format settings for display ------------------------------
    display_settings = {}
    if settings_dict:
        display_settings['Trials (J)'] = total_trials
        if Ts is not None:
            display_settings['Sampling Period (Ts)'] = f"{Ts}s"
        ic = settings_dict.get('initial_conditions', {})
        if ic:
            display_settings['Initial Conditions'] = (
                f"x={ic.get('x', 0)}, y={ic.get('y', 0)}, psi={ic.get('psi', 0)}"
            )
        ic_u0 = settings_dict.get('initial_conditions_u0')
        if ic_u0:
            display_settings['Initial Conditions (u0 trial)'] = (
                f"x={ic_u0.get('x', 0)}, y={ic_u0.get('y', 0)}, psi={ic_u0.get('psi', 0)}"
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
    u0_params = settings_dict.get('u0_params', {})
    if u0_params:
        display_settings['u0 Cutoff Freq'] = f"{u0_params.get('f_cutoff', '?')} Hz"
        display_settings['u0 Amplitude'] = u0_params.get('sigma', '?')
        display_settings['u0 Bias'] = u0_params.get('bias', '?')
    if meta.get('robot_id'):
        display_settings['Robot'] = meta['robot_id']

    # --- Process logs ---------------------------------------------
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

    # --- Render report --------------------------------------------
    template_path = Path(__file__).parent / "dilc_report_template.html"
    report = Report(template_path, plot_dpi=120, plot_width="100%")

    report.render(
        title=f"DILC Report: {exp_id}",
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
        best_trial_index=best_trial_index,
        best_trial_state_plots=best_trial_state_plots,
        best_trial_control_plots=best_trial_control_plots,
        settings=display_settings,
        logs=logs,
    )

    # --- Output ---------------------------------------------------
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



if __name__ == '__main__':
    generate_dilc_report('/Users/lehmann/Desktop/dilc/dilc_dilc_test_2026-02-13_10-43-30.json')