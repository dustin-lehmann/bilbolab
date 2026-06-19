"""
IML experiment plotting helpers.

Provides intermediate and report plotting functions for IML (Iterative Model
Learning / model identification) experiments using the core.utils.plotting.plot
framework. Mirrors ``dilc_helpers`` and reuses its best-trial sample plots.
"""
import json
from pathlib import Path

import numpy as np

from core.utils.plotting.plot import (
    Plot, PlotConfig,
    Axis, AxisConfig,
    SeriesConfig,
    LegendConfig,
)
from robots.bilbo.robot.experiment.dilc.dilc_helpers import (
    _trial_colors,
    _get_trial_index,
    _get_change_percent,
    plot_best_trial_states,
    plot_best_trial_control,
)


def _trial_field(trial, name):
    """Read a field from a trial that may be a dict or a dataclass/object."""
    return trial.get(name) if isinstance(trial, dict) else getattr(trial, name, None)


def aggregate_residual(model, trials) -> float:
    """Aggregate residual of ``model`` over all trials: sqrt(sum ||y - M(u) m||^2).

    Measures how well a single model explains *every* driven input, not just
    the trial that produced it. ``M(u) m`` is the causal convolution ``u * m``.
    Trials accept dict or dataclass form.
    """
    if model is None:
        return float('inf')
    m = np.asarray(model, dtype=float)
    total = 0.0
    for tr in trials:
        u = _trial_field(tr, 'u')
        y = _trial_field(tr, 'y')
        if u is None or y is None:
            continue
        u = np.asarray(u, dtype=float)
        y = np.asarray(y, dtype=float)
        pred = np.convolve(u, m)[:len(u)]
        n = min(len(y), len(pred))
        r = y[:n] - pred[:n]
        total += float(r @ r)
    return float(np.sqrt(total))


def best_trial_index(trials) -> int | None:
    """List index of the trial whose *updated* model best explains the whole set.

    Uses :func:`aggregate_residual` (generalisation), not the per-trial fit
    residual (which rewards single-trajectory overfitting). Returns None when no
    candidate model is available.
    """
    best_i, best_norm = None, float('inf')
    for i, tr in enumerate(trials):
        m = _trial_field(tr, 'model_vector_update')
        if m is None:
            continue
        agg = aggregate_residual(m, trials)
        if agg < best_norm:
            best_norm, best_i = agg, i
    return best_i


def plot_outputs(
        trials: list[dict],
        total_trials: int | None = None,
        show: bool = True,
) -> Plot:
    """Plot measured output (theta/y) trajectories with trial progression gradient.

    Args:
        trials: List of trial dicts. Each should have 't' (time) and 'y' (output).
        total_trials: Total number of trials for fixed color scaling.
        show: If True, open a temporary PDF preview.

    Returns:
        The Plot instance.
    """
    if total_trials is None:
        total_trials = max(len(trials), 1)

    plot = Plot(1, 1, PlotConfig(size=(10, 5)), use_agg_backend=True)
    axis = Axis('output', AxisConfig(
        title='Measured Output Trajectories',
        xlabel='Time [s]',
        ylabel='Output',
        legend=LegendConfig(loc='upper right'),
    ))
    plot.set_axis(1, 1, axis)

    colors = _trial_colors(len(trials), total_trials)
    for i, trial in enumerate(trials):
        y = trial.get('y')
        t = trial.get('t')
        if y is None or t is None:
            continue
        label = f'Trial {_get_trial_index(trial, i) + 1}' if i in (0, len(trials) - 1) else None
        axis.plot(t, y, SeriesConfig(color=colors[i], linewidth=1.2, label=label))

    if show:
        plot.show_temp_pdf()
    return plot


def plot_inputs(
        trials: list[dict],
        total_trials: int | None = None,
        show: bool = True,
) -> Plot:
    """Plot driven input trajectories with trial progression gradient.

    Args:
        trials: List of trial dicts. Each should have 't' (time) and 'u' (input).
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
        axis.plot(t, u, SeriesConfig(color=colors[i], linewidth=1.2, label=label))

    if show:
        plot.show_temp_pdf()
    return plot


def plot_output_error_norms(
        trials: list[dict],
        total_trials: int | None = None,
        show: bool = True,
) -> Plot:
    """Plot the model output-error (and fit/estimation) norm progression across trials.

    Args:
        trials: List of trial dicts. Each should carry 'model_output_error_norm'
            and optionally 'model_fit_error_norm' / 'model_estimation_error_norm'.
        total_trials: Total expected trials (fixes the x-axis range).
        show: If True, open a temporary PDF preview.

    Returns:
        The Plot instance.
    """
    if total_trials is None:
        total_trials = max(len(trials), 1)

    indices = [_get_trial_index(trial, i) + 1 for i, trial in enumerate(trials)]
    out_norms = [trial.get('model_output_error_norm', 0.0) for trial in trials]

    plot = Plot(1, 1, PlotConfig(size=(8, 4)), use_agg_backend=True)
    axis = Axis('iml_error', AxisConfig(
        title='Model Error Norm Progression',
        xlabel='Trial',
        ylabel=r'$\|e\|$',
        xlim=(0.5, total_trials + 0.5),
        xticks=list(range(1, total_trials + 1)),
        legend=LegendConfig(loc='upper right'),
    ))
    plot.set_axis(1, 1, axis)

    axis.plot(indices, out_norms, SeriesConfig(
        color='tab:orange', linewidth=1.5, marker='o', marker_size=5.0,
        label='Output error',
    ))

    fit_norms = [trial.get('model_fit_error_norm') for trial in trials]
    if any(v is not None for v in fit_norms):
        axis.plot(indices, [v if v is not None else np.nan for v in fit_norms],
                  SeriesConfig(color='tab:blue', linewidth=1.5, marker='s',
                               marker_size=4.0, label='Fit residual'))

    est_norms = [trial.get('model_estimation_error_norm') for trial in trials]
    if any(v is not None for v in est_norms):
        axis.plot(indices, [v if v is not None else np.nan for v in est_norms],
                  SeriesConfig(color='tab:green', linewidth=1.2, marker='^',
                               marker_size=4.0, label='Estimation error'))

    if show:
        plot.show_temp_pdf()
    return plot


def plot_identified_model(
        trials: list[dict],
        reference_model: list | np.ndarray | None = None,
        best_model: list | np.ndarray | None = None,
        Ts: float | None = None,
        show: bool = True,
) -> Plot:
    """Plot the identified model (impulse response) vector.

    Plots the final trial's updated model and, if available, the best model and
    a reference model.

    Args:
        trials: List of trial dicts (each with 'model_vector_update').
        reference_model: Optional reference Markov vector m_ref.
        best_model: Optional best identified model vector (overlaid).
        Ts: Optional sampling period; if given the x-axis is time, else tap index.
        show: If True, open a temporary PDF preview.

    Returns:
        The Plot instance.
    """
    plot = Plot(1, 1, PlotConfig(size=(10, 5)), use_agg_backend=True)
    xlabel = 'Time [s]' if Ts else 'Tap k'
    axis = Axis('model', AxisConfig(
        title='Identified Model (impulse response)',
        xlabel=xlabel,
        ylabel='m[k]',
        legend=LegendConfig(loc='upper right'),
    ))
    plot.set_axis(1, 1, axis)

    def _x(vec):
        n = len(vec)
        return (np.arange(n) * Ts) if Ts else np.arange(n)

    if reference_model is not None:
        ref = np.asarray(reference_model)
        axis.plot(_x(ref), ref, SeriesConfig(
            color='black', linewidth=1.5, linestyle='--', label='Reference'))

    if trials and trials[-1].get('model_vector_update') is not None:
        m = np.asarray(trials[-1]['model_vector_update'])
        axis.plot(_x(m), m, SeriesConfig(
            color='tab:blue', linewidth=1.5, label=f'Final (trial {len(trials)})'))

    if best_model is not None:
        bm = np.asarray(best_model)
        axis.plot(_x(bm), bm, SeriesConfig(
            color='tab:green', linewidth=1.8, label='Best'))

    if show:
        plot.show_temp_pdf()
    return plot


# === Report Generation ================================================================

def generate_iml_report(
        experiment_data,
        output: str | None = None,
        format: str = 'html',
        show: bool = True,
) -> 'Report':
    """Generate an HTML/PDF report for an IML experiment.

    Parameters
    ----------
    experiment_data : str | dict | IML_Results | IML_Experiment
        Experiment data source:
        - str: Path to the IML results JSON file
        - dict: Raw results dict (with 'meta', 'state', 'trials' keys)
        - IML_Results: Parsed results dataclass
        - IML_Experiment: Live experiment instance (uses .results or .trials)
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
    import dataclasses as dc

    from core.utils.report import Report
    from robots.bilbo.robot.experiment.iml.iml import IML_Results, IML_Experiment

    # --- Resolve experiment data into trials list and metadata ----
    best_model = None
    final_model = None
    if isinstance(experiment_data, str):
        with open(experiment_data, 'r') as f:
            results_dict = json.load(f)
        trials = results_dict.get('trials', [])
        meta = results_dict.get('meta', {})
        state = results_dict.get('state', 'UNKNOWN')
        best_model = results_dict.get('best_model')
        final_model = results_dict.get('final_model')
    elif isinstance(experiment_data, IML_Results):
        trials = experiment_data.trials
        meta = {
            'robot_id': experiment_data.meta.robot_id,
            'date': experiment_data.meta.date,
            'settings': experiment_data.meta.settings,
            'logs': experiment_data.meta.logs,
        }
        state = experiment_data.state
        best_model = experiment_data.best_model
        final_model = experiment_data.final_model
    elif isinstance(experiment_data, IML_Experiment):
        if experiment_data.results is not None and experiment_data.results.trials:
            res = experiment_data.results
            trials = res.trials
            meta = {
                'robot_id': res.meta.robot_id,
                'date': res.meta.date,
                'settings': res.meta.settings,
                'logs': res.meta.logs,
            }
            state = res.state
            best_model = res.best_model
            final_model = res.final_model
        else:
            trials = [dc.asdict(t) for t in experiment_data.trials]
            meta = {}
            state = experiment_data.state.value if experiment_data.state else 'UNKNOWN'
    elif isinstance(experiment_data, dict):
        trials = experiment_data.get('trials', [])
        meta = experiment_data.get('meta', {})
        state = experiment_data.get('state', 'UNKNOWN')
        best_model = experiment_data.get('best_model')
        final_model = experiment_data.get('final_model')
    else:
        raise TypeError(f"Unsupported experiment_data type: {type(experiment_data)}")

    if not trials:
        raise ValueError("No trial data available for report generation")

    # --- Extract settings -----------------------------------------
    settings_dict = meta.get('settings', {}) or {}
    exp_id = settings_dict.get('id', 'iml')
    description = settings_dict.get('description', '')
    total_trials = settings_dict.get('J', len(trials))
    Ts = settings_dict.get('Ts', None)
    method = settings_dict.get('method', 'iterative')
    date = meta.get('date', '')
    reference_model = settings_dict.get('reference_model')

    first_t = trials[0].get('t')
    duration_per_trial = first_t[-1] if first_t else None

    # --- Determine success ----------------------------------------
    is_success = state in ('FINISHED', 'finished')
    is_error = state in ('ERROR', 'error')
    status_info = {
        'status': state,
        'is_success': is_success,
        'is_error': is_error,
        'status_label': 'Success' if is_success else (state.upper() if isinstance(state, str) else str(state)),
        'status_class': 'success' if is_success else 'error' if is_error else 'warning',
        'error_message': None,
    }

    # --- Build error norms table ----------------------------------
    norms_table = []
    for i, trial in enumerate(trials):
        e_out = trial.get('model_output_error_norm', 0.0)
        e_fit = trial.get('model_fit_error_norm')
        e_est = trial.get('model_estimation_error_norm')

        e_out_change = None
        if i > 0:
            prev = trials[i - 1].get('model_output_error_norm', 0.0)
            if prev > 0:
                e_out_change = ((e_out - prev) / prev) * 100

        norms_table.append({
            'trial': _get_trial_index(trial, i) + 1,
            'e_out': e_out,
            'e_fit': e_fit,
            'e_est': e_est,
            'e_out_change': e_out_change,
            'model_change_pct': _get_change_percent(trial, 'model_vector', 'model_vector_update'),
        })

    # --- Generate plots (no preview, for embedding) ---------------
    p_outputs = plot_outputs(trials, total_trials=total_trials, show=False)
    p_inputs = plot_inputs(trials, total_trials=total_trials, show=False)
    p_error = plot_output_error_norms(trials, total_trials=total_trials, show=False)
    p_model = plot_identified_model(trials, reference_model=reference_model,
                                    best_model=best_model, Ts=Ts, show=False)

    # --- Best trial sample plots ----------------------------------
    best_trial_state_plots = []
    best_trial_control_plots = []
    best_trial_index = None
    trials_with_samples = [t for t in trials if t.get('samples')]
    if trials_with_samples:
        # Best = the sampled trial whose model best explains the whole set
        # (aggregate residual), matching the robot's .bmvec selection.
        best_trial = min(trials_with_samples,
                         key=lambda t: aggregate_residual(
                             t.get('model_vector_update'), trials))
        best_trial_index = _get_trial_index(best_trial, 0) + 1
        best_samples = best_trial['samples']
        best_trial_state_plots = plot_best_trial_states(best_samples)
        best_trial_control_plots = plot_best_trial_control(best_samples)

    # --- Format settings for display ------------------------------
    display_settings = {}
    if settings_dict:
        display_settings['Trials (J)'] = total_trials
        display_settings['Method'] = method
        if Ts is not None:
            display_settings['Sampling Period (Ts)'] = f"{Ts}s"
        ls = settings_dict.get('learning_set')
        if isinstance(ls, list):
            display_settings['Learning Set Size'] = len(ls)
        if settings_dict.get('s_m') is not None:
            display_settings['Model Regularisation (s_m)'] = settings_dict['s_m']
        display_settings['Adaptive s_m'] = settings_dict.get('adaptive_s_m', '?')
        mlp = settings_dict.get('model_lowpass')
        if mlp:
            display_settings['Q-filter'] = (
                f"fc={mlp.get('fc', '?')}, L={mlp.get('L', '?')}, window={mlp.get('window', '?')}"
            )
        ic = settings_dict.get('initial_conditions', {})
        if ic:
            display_settings['Initial Conditions'] = (
                f"x={ic.get('x', 0)}, y={ic.get('y', 0)}, psi={ic.get('psi', 0)}"
            )
    if meta.get('robot_id'):
        display_settings['Robot'] = meta['robot_id']

    # --- Summary stats --------------------------------------------
    best_fit = None
    if trials:
        fits = [t.get('model_fit_error_norm') for t in trials if t.get('model_fit_error_norm') is not None]
        best_fit = min(fits) if fits else None

    # --- Process logs ---------------------------------------------
    LOG_LEVEL_NAMES = {10: 'DEBUG', 20: 'INFO', 25: 'IMPORTANT', 30: 'WARNING', 40: 'ERROR', 50: 'CRITICAL'}
    logs = []
    for log in (meta.get('logs', []) or []):
        level = log.get('level', 20)
        logs.append({
            'tick': log.get('tick', ''),
            'level': level,
            'level_name': LOG_LEVEL_NAMES.get(level, 'INFO'),
            'logger': log.get('logger', ''),
            'message': log.get('message', ''),
        })

    # --- Render report --------------------------------------------
    template_path = Path(__file__).parent / "iml_report_template.html"
    report = Report(template_path, plot_dpi=120, plot_width="100%")

    report.render(
        title=f"IML Report: {exp_id}",
        experiment_id=exp_id,
        description=description,
        date=date,
        method=method,
        status=status_info,
        completed_trials=len(trials),
        total_trials=total_trials,
        duration_per_trial=duration_per_trial,
        sampling_period=Ts,
        best_fit=best_fit,
        norms=norms_table,
        plot_outputs=p_outputs,
        plot_inputs=p_inputs,
        plot_error=p_error,
        plot_model=p_model,
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
    import sys
    if len(sys.argv) > 1:
        generate_iml_report(sys.argv[1])
