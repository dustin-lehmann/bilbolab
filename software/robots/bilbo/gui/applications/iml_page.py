import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from core.utils.colors import get_segmented_progression_colors
from core.utils.logging_utils import Logger
from extensions.gui.src.app import FolderPage
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.buttons import Button, MultiStateButton
from extensions.gui.src.lib.objects.python.image import UpdatableImageWidget
from extensions.gui.src.lib.objects.python.table import Table, TextColumn
from extensions.gui.src.lib.objects.python.text import StatusWidget, StatusWidgetElement
from robots.bilbo.robot.experiment.iml import IML_Experiment, aggregate_residual, best_trial_index

# Status indicator colors
_COLOR_IDLE = [0.4, 0.4, 0.4]
_COLOR_PREPARING = [0.2, 0.55, 0.85]
_COLOR_TRAJECTORY = [0.86, 0.87, 0.29]
_COLOR_WAITING = [0.72, 0.42, 0.19]
_COLOR_COMPUTING = [0.3, 0.3, 0.75]
_COLOR_FINISHED = [0.0, 0.5, 0.0]
_COLOR_ERROR = [0.7, 0.0, 0.0]
_COLOR_BEST = [0.0, 0.6, 0.25]


class IML_ExperimentPage:
    """Manages a FolderPage for IML experiments.

    Pre-builds the page with status, table, buttons, and plots. Call
    ``bind_experiment()`` when an experiment is initialized and
    ``unbind_experiment()`` on cleanup.
    """

    def __init__(self, robot):
        self.robot = robot
        self.logger = Logger("IML Page")
        self.experiment: IML_Experiment | None = None
        self._trial_rows = []
        self._event_handles = []

        self.page = FolderPage(page_id='iml', name='IML', rows=10, columns=8)
        self._build_page()

    # === BUILD ============================================================================================

    def _build_page(self):
        self.status_widget = StatusWidget(
            widget_id='iml_page_status',
            title='IML',
            elements={
                'state': StatusWidgetElement(label='State:', color=_COLOR_IDLE, status='No Experiment'),
                'trial': StatusWidgetElement(label='Trial:', color=_COLOR_IDLE, status='--'),
                'best': StatusWidgetElement(label='Best:', color=_COLOR_IDLE, status='--'),
                'merr': StatusWidgetElement(label='m-err:', color=_COLOR_IDLE, status='--'),
            },
            font_size=9,
        )
        self.page.addObject(self.status_widget, row=1, column=1, width=4, height=2)

        self.trial_table = Table(widget_id='iml_page_table')
        self.trial_table.add_column(TextColumn(id='num', title='#', width=0.13, font_align='center'))
        self.trial_table.add_column(TextColumn(id='e_out', title='Out Err', width=0.30, font_align='right'))
        self.trial_table.add_column(TextColumn(id='e_fit', title='Fit Res', width=0.29, font_align='right'))
        self.trial_table.add_column(TextColumn(id='e_m', title='Est Err', width=0.28, font_align='right'))
        self.page.addObject(self.trial_table, row=1, column=5, width=4, height=2)

        self.group_control = Widget_Group(group_id='iml_page_control', title='Control',
                                          show_title=False, rows=1, columns=8)
        self.page.addObject(self.group_control, row=3, column=1, width=8, height=1)

        self.resume_button = Button(widget_id='iml_page_resume', text='Resume', color=[0.0, 0.4, 0.0])
        self.resume_button.callbacks.click.register(self.robot.core.set_resume_event_robot, discard_inputs=True)
        self.group_control.addWidget(self.resume_button, row=1, column=1, width=1, height=1)

        self.revert_button = Button(widget_id='iml_page_revert', text='Revert', color=[110 / 255, 82 / 255, 0])
        self.revert_button.callbacks.click.register(self.robot.core.set_repeat_event_robot, discard_inputs=True)
        self.group_control.addWidget(self.revert_button, row=1, column=2, width=1, height=1)

        self.stop_button = Button(widget_id='iml_page_stop', text='Stop', color=[0.5, 0.0, 0.0])
        self.stop_button.callbacks.click.register(self._on_stop, discard_inputs=True)
        self.group_control.addWidget(self.stop_button, row=1, column=3, width=1, height=1)

        self.auto_start_button = MultiStateButton(
            id='iml_page_auto_start', states=['OFF', 'ON'], current_state='OFF',
            color=[[0.5, 0.5, 0.5], [0, 0.4, 0]], title='Auto Start',
        )
        self.auto_start_button.callbacks.click.register(self._on_auto_start_toggle)
        self.group_control.addWidget(self.auto_start_button, row=1, column=5, width=2, height=1)

        self.auto_accept_button = MultiStateButton(
            id='iml_page_auto_accept', states=['OFF', 'ON'], current_state='OFF',
            color=[[0.5, 0.5, 0.5], [0, 0.4, 0]], title='Auto Accept',
        )
        self.auto_accept_button.callbacks.click.register(self._on_auto_accept_toggle)
        self.group_control.addWidget(self.auto_accept_button, row=1, column=7, width=2, height=1)

        self.plot_outputs = UpdatableImageWidget(widget_id='iml_page_plot_outputs')
        self.page.addObject(self.plot_outputs, row=4, column=1, width=4, height=3)

        self.plot_inputs = UpdatableImageWidget(widget_id='iml_page_plot_inputs')
        self.page.addObject(self.plot_inputs, row=4, column=5, width=4, height=3)

        self.plot_convergence = UpdatableImageWidget(widget_id='iml_page_plot_convergence')
        self.page.addObject(self.plot_convergence, row=7, column=1, width=4, height=3)

        self.plot_model = UpdatableImageWidget(widget_id='iml_page_plot_model')
        self.page.addObject(self.plot_model, row=7, column=5, width=4, height=3)

    # === EXPERIMENT BINDING ================================================================================

    def bind_experiment(self, experiment: IML_Experiment):
        self.unbind_experiment()
        self.experiment = experiment
        self._trial_rows = []

        exp_id = experiment.settings.id if experiment.settings else 'IML'
        self.status_widget.title = f'IML -- {exp_id}'
        self._set_state('Initialized', _COLOR_PREPARING)
        self.status_widget.elements['trial'].status = '--'
        self.status_widget.elements['best'].status = '--'
        self.status_widget.elements['merr'].status = '--'
        self.status_widget.updateConfig()

        self.auto_start_button.state = 'ON' if experiment.auto_start_trials else 'OFF'
        self.auto_accept_button.state = 'ON' if experiment.auto_accept_trials else 'OFF'

        ev = experiment.events
        self._event_handles = [
            ev.experiment_started.on(self._on_experiment_started),
            ev.trial_started.on(self._on_trial_started),
            ev.trial_prepared.on(self._on_trial_prepared),
            ev.trajectory_started.on(self._on_trajectory_started),
            ev.trajectory_finished.on(self._on_trajectory_finished),
            ev.trial_finished.on(self._on_trial_finished),
            ev.trial_reverted.on(self._on_trial_reverted),
            ev.experiment_finished.on(self._on_experiment_finished),
            ev.experiment_error.on(self._on_experiment_error),
        ]
        experiment.callbacks.meta_settings_changed.register(
            self._on_meta_settings_changed, discard_inputs=True)

        self._plot_all()

    def unbind_experiment(self):
        for handle in self._event_handles:
            try:
                handle.stop()
            except Exception:
                pass
        self._event_handles = []

        if self.experiment is not None:
            try:
                self.experiment.callbacks.meta_settings_changed.unregister(self._on_meta_settings_changed)
            except Exception:
                pass

        for row in self._trial_rows:
            try:
                row.delete()
            except Exception:
                pass
        self._trial_rows = []
        self.experiment = None

    # === STATUS HELPERS ====================================================================================

    def _set_state(self, text, color):
        self.status_widget.elements['state'].status = text
        self.status_widget.elements['state'].color = color
        self.status_widget.updateConfig()

    def _set_trial_counter(self, current, total):
        self.status_widget.elements['trial'].status = f'{current} / {total}'
        self.status_widget.updateConfig()

    @staticmethod
    def _fmt(v):
        return f'{v:.6f}' if v is not None else '--'

    def _update_best_trial(self):
        if not self.experiment or not self.experiment.trials:
            return
        trials = self.experiment.trials
        bi = best_trial_index(trials)
        if bi is not None:
            best = trials[bi]
            agg = aggregate_residual(best.model_vector_update, trials)
            self.status_widget.elements['best'].status = \
                f'Trial {best.trial_index + 1}  ({agg:.6f})'
            self.status_widget.elements['best'].color = _COLOR_BEST
        last = trials[-1]
        if last.model_estimation_error_norm is not None:
            self.status_widget.elements['merr'].status = f'{last.model_estimation_error_norm:.6f}'
            self.status_widget.elements['merr'].color = _COLOR_BEST
        self.status_widget.updateConfig()

    def _rebuild_table(self):
        for row in self._trial_rows:
            try:
                row.delete()
            except Exception:
                pass
        self._trial_rows = []

        if not self.experiment or not self.experiment.trials:
            return
        trials = self.experiment.trials
        best_idx = best_trial_index(trials)
        for i, trial in enumerate(trials):
            row = self.trial_table.make_row(
                num=str(trial.trial_index + 1),
                e_out=f'{trial.model_output_error_norm:.6f}',
                e_fit=self._fmt(trial.model_fit_error_norm),
                e_m=self._fmt(trial.model_estimation_error_norm),
            )
            if i == best_idx:
                row.highlight = True
                row.row_background_color = [0, 0.35, 0.15, 0.3]
            self._trial_rows.append(row)

    # === EVENT HANDLERS ====================================================================================

    def _on_experiment_started(self, *args, **kwargs):
        self._set_state('Started', _COLOR_PREPARING)

    def _on_trial_started(self, *args, **kwargs):
        if not self.experiment:
            return
        j = len(self.experiment.trials) + 1
        J = self.experiment.settings.J if self.experiment.settings else '?'
        self._set_state('Preparing Trial', _COLOR_PREPARING)
        self._set_trial_counter(j, J)

    def _on_trial_prepared(self, *args, **kwargs):
        self._set_state('Waiting for Input', _COLOR_WAITING)

    def _on_trajectory_started(self, *args, **kwargs):
        self._set_state('Running Trajectory', _COLOR_TRAJECTORY)

    def _on_trajectory_finished(self, *args, **kwargs):
        self._set_state('Computing Update', _COLOR_COMPUTING)

    def _on_trial_finished(self, *args, **kwargs):
        if not self.experiment:
            return
        if self.experiment.auto_accept_trials:
            self._set_state('Trial Done', _COLOR_PREPARING)
        else:
            self._set_state('Accept / Revert?', _COLOR_WAITING)
        self._update_best_trial()
        self._rebuild_table()
        self._plot_all()

    def _on_trial_reverted(self, *args, **kwargs):
        self._set_state('Trial Reverted', _COLOR_WAITING)

    def _on_experiment_finished(self, *args, **kwargs):
        self._set_state('Finished', _COLOR_FINISHED)
        if self.experiment:
            j = len(self.experiment.trials)
            J = self.experiment.settings.J if self.experiment.settings else j
            self._set_trial_counter(j, J)
            self._plot_all()

    def _on_experiment_error(self, *args, **kwargs):
        self._set_state('Error', _COLOR_ERROR)

    def _on_stop(self):
        if self.experiment:
            self.experiment.stop()

    def _on_auto_start_toggle(self, state, *args, **kwargs):
        if not self.experiment:
            return
        enable = (state == 'OFF')
        self.experiment.set_auto_start_trials(enable)
        self.auto_start_button.state = 'ON' if enable else 'OFF'

    def _on_auto_accept_toggle(self, state, *args, **kwargs):
        if not self.experiment:
            return
        enable = (state == 'OFF')
        self.experiment.set_auto_accept_trials(enable)
        self.auto_accept_button.state = 'ON' if enable else 'OFF'

    def _on_meta_settings_changed(self):
        if not self.experiment:
            return
        self.auto_start_button.state = 'ON' if self.experiment.auto_start_trials else 'OFF'
        self.auto_accept_button.state = 'ON' if self.experiment.auto_accept_trials else 'OFF'

    # === PLOTTING =========================================================================================

    @staticmethod
    def _new_figure(figsize=(5, 3), dpi=150):
        fig = Figure(figsize=figsize, dpi=dpi)
        FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        return fig, ax

    def _get_colors(self):
        if not self.experiment or not self.experiment.settings:
            return []
        J = self.experiment.settings.J
        anchors = [[0.09, 0.28, 0.67], [0.00, 0.60, 0.33], [0.95, 0.60, 0.10]]
        return get_segmented_progression_colors(max(J, 1), anchors, gamma=1.0)

    def _plot_all(self):
        self._plot_outputs()
        self._plot_inputs()
        self._plot_convergence()
        self._plot_model()

    @staticmethod
    def _predict(u, m):
        """Predicted output of the current model: M(u) m as a causal convolution."""
        u = np.asarray(u, dtype=float)
        m = np.asarray(m, dtype=float)
        return np.convolve(u, m)[:len(u)]

    def _plot_outputs(self):
        fig, ax = self._new_figure()
        ax.set_title("Measured vs predicted", color="black", fontsize=10)
        ax.set_xlabel("Time [s]", fontsize=8)
        ax.set_ylabel("Angle [deg]", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3)

        if self.experiment and self.experiment.trials:
            trial = self.experiment.trials[-1]
            if trial.y is not None and trial.t is not None:
                t = np.asarray(trial.t)
                y = np.asarray(trial.y)
                n = min(len(t), len(y))
                ax.plot(t[:n], np.rad2deg(y[:n]), color="C0", lw=2.0,
                        label=f"Measured (trial {trial.trial_index + 1})", zorder=3)
                m = trial.model_vector_update
                if m is not None and trial.u is not None:
                    pred = self._predict(trial.u, m)
                    nn = min(len(t), len(pred))
                    ax.plot(t[:nn], np.rad2deg(pred[:nn]), color="C3", lw=1.8,
                            linestyle="--", label="Predicted (current model)", zorder=4)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc="upper right", fontsize=7)
        self.plot_outputs.setFromMatplotLib(fig, dpi=150)

    def _plot_inputs(self):
        fig, ax = self._new_figure()
        ax.set_title("Inputs", color="black", fontsize=10)
        ax.set_xlabel("Time [s]", fontsize=8)
        ax.set_ylabel("Input", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3)

        if self.experiment:
            trials = self.experiment.trials
            colors = self._get_colors()
            n = len(trials)
            for i, trial in enumerate(trials):
                if trial.u is None or trial.t is None:
                    continue
                t = np.asarray(trial.t)
                is_latest = (i == n - 1)
                ax.plot(t, np.asarray(trial.u),
                        lw=2.5 if is_latest else 1.0,
                        color=colors[i % max(1, len(colors))],
                        alpha=1.0 if is_latest else 0.25,
                        label=f"u {i + 1}" if is_latest else None,
                        zorder=3 if is_latest else 2)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc="upper right", fontsize=7)
        self.plot_inputs.setFromMatplotLib(fig, dpi=150)

    def _plot_convergence(self):
        fig, ax = self._new_figure()
        ax.set_title("Convergence", color="black", fontsize=10)
        ax.set_xlabel("Trial", fontsize=8)
        ax.set_ylabel("Norm (log)", fontsize=8)
        ax.set_yscale("log")
        ax.tick_params(labelsize=7)
        ax.grid(True, which="both", alpha=0.3)

        if self.experiment and self.experiment.settings:
            ax.set_xlim([0, self.experiment.settings.J + 1])
            trials = self.experiment.trials
            if trials:
                x = np.arange(1, len(trials) + 1)
                ax.plot(x, [t.model_output_error_norm for t in trials],
                        color="C1", lw=2, marker="o", ms=3, label="output err")
                e_fit = np.array([t.model_fit_error_norm if t.model_fit_error_norm is not None
                                  else np.nan for t in trials], dtype=float)
                if np.any(np.isfinite(e_fit)):
                    ax.plot(x, e_fit, color="C0", lw=2, marker="s", ms=3, label="fit res")
                e_m = np.array([t.model_estimation_error_norm if t.model_estimation_error_norm is not None
                                else np.nan for t in trials], dtype=float)
                if np.any(np.isfinite(e_m)):
                    ax.plot(x, e_m, color="C2", lw=1.5, marker="^", ms=3, label="est err")
                ax.legend(loc="upper right", fontsize=7)
        self.plot_convergence.setFromMatplotLib(fig, dpi=150)

    def _plot_model(self):
        fig, ax = self._new_figure()
        ax.set_title("Identified model", color="black", fontsize=10)
        ax.set_xlabel("Tap k", fontsize=8)
        ax.set_ylabel("m[k]", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3)

        if self.experiment:
            ref = self.experiment.settings.reference_model if self.experiment.settings else None
            if ref is not None:
                ax.plot(np.asarray(ref), color="black", lw=1.5, linestyle="--", label="ref")
            trials = self.experiment.trials
            if trials and trials[-1].model_vector_update is not None:
                ax.plot(np.asarray(trials[-1].model_vector_update),
                        color="C0", lw=2, label=f"m (trial {len(trials)})")
        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc="upper right", fontsize=7)
        self.plot_model.setFromMatplotLib(fig, dpi=150)
