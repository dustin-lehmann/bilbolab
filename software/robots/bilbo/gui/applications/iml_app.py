import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from core.utils.colors import get_segmented_progression_colors
from core.utils.exit import register_exit_callback
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.buttons import Button, MultiStateButton
from extensions.gui.src.lib.objects.python.image import UpdatableImageWidget
from extensions.gui.src.lib.objects.python.popup import Popup
from extensions.gui.src.lib.objects.python.popup_application import GUI_Popup_Application
from extensions.gui.src.lib.objects.python.table import Table, TextColumn
from extensions.gui.src.lib.objects.python.text import StatusWidget, StatusWidgetElement
from robots.bilbo.robot.bilbo import BILBO
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


class IML_APP(GUI_Popup_Application):
    """Popup application for an IML experiment running on the robot."""

    experiment: IML_Experiment

    def __init__(self, gui, robot: BILBO, experiment: IML_Experiment, config: dict = None):
        super().__init__('iml_app', 'IML APP', config)
        self.gui = gui
        self.robot = robot
        self.experiment = experiment
        self._trial_rows = []

        exp_id = experiment.settings.id if experiment.settings else 'IML'
        self.popup = Popup(f"{self.id}_popup",
                           title=f'IML — {exp_id}',
                           allow_multiple=False,
                           grid=[20, 20],
                           size=[1300, 800],
                           type='window')

        self._build_popup()
        self._register_events()
        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.popup.close()

    def onMessage(self, message, sender=None) -> None:
        pass

    def getConfiguration(self):
        pass

    def _onPopupClosed(self, *args, **kwargs):
        pass

    # === BUILD UI =====================================================================================================

    def _build_popup(self):
        self.status_widget = StatusWidget(
            widget_id='experiment_status',
            title='Experiment',
            elements={
                'state': StatusWidgetElement(label='State:', color=_COLOR_IDLE, status='Idle'),
                'trial': StatusWidgetElement(label='Trial:', color=[0.4, 0.4, 0.4], status='—'),
                'best': StatusWidgetElement(label='Best:', color=[0.4, 0.4, 0.4], status='—'),
                'merr': StatusWidgetElement(label='m-err:', color=[0.4, 0.4, 0.4], status='—'),
            }
        )
        self.popup.group.addWidget(self.status_widget, row=1, column=1, width=6, height=3)

        self.trial_table = Table(widget_id='trial_table')
        self.trial_table.add_column(TextColumn(id='num', title='#', width=0.13, font_align='center'))
        self.trial_table.add_column(TextColumn(id='e_out', title='Out Err', width=0.30, font_align='right'))
        self.trial_table.add_column(TextColumn(id='e_fit', title='Fit Res', width=0.29, font_align='right'))
        self.trial_table.add_column(TextColumn(id='e_m', title='Est Err', width=0.28, font_align='right'))
        self.popup.group.addWidget(self.trial_table, row=4, column=1, width=6, height=10)

        self.group_control = Widget_Group(group_id='control', title='Control',
                                          show_title=True, rows=2, columns=5)
        self.popup.group.addWidget(self.group_control, row=14, column=1, width=6, height=4)

        self.resume_button = Button(widget_id='resume_button', text='Resume', color=[0.0, 0.4, 0.0])
        self.resume_button.callbacks.click.register(self.robot.core.set_resume_event_robot, discard_inputs=True)
        self.group_control.addWidget(self.resume_button, row=1, column=3, width=1, height=1)

        self.revert_button = Button(widget_id='revert_button', text='Revert', color=[110 / 255, 82 / 255, 0])
        self.revert_button.callbacks.click.register(self.robot.core.set_repeat_event_robot, discard_inputs=True)
        self.group_control.addWidget(self.revert_button, row=1, column=4, width=1, height=1)

        self.stop_button = Button(widget_id='stop_button', text='Stop', color=[0.5, 0.0, 0.0])
        self.stop_button.callbacks.click.register(self._onStop, discard_inputs=True)
        self.group_control.addWidget(self.stop_button, row=1, column=5, width=1, height=1)

        self.auto_start_button = MultiStateButton(
            id='auto_start_button', states=['OFF', 'ON'],
            current_state='ON' if self.experiment.auto_start_trials else 'OFF',
            color=[[0.5, 0.5, 0.5], [0, 0.4, 0]], title='Auto Start',
        )
        self.auto_start_button.callbacks.click.register(self._onAutoStartToggle)
        self.group_control.addWidget(self.auto_start_button, row=2, column=1, width=2, height=1)

        self.auto_accept_button = MultiStateButton(
            id='auto_accept_button', states=['OFF', 'ON'],
            current_state='ON' if self.experiment.auto_accept_trials else 'OFF',
            color=[[0.5, 0.5, 0.5], [0, 0.4, 0]], title='Auto Accept',
        )
        self.auto_accept_button.callbacks.click.register(self._onAutoAcceptToggle)
        self.group_control.addWidget(self.auto_accept_button, row=2, column=3, width=2, height=1)

        # --- RIGHT PANEL: Plots (col 7–20) ---
        self.plot_outputs = UpdatableImageWidget(widget_id='plot_outputs')
        self.popup.group.addWidget(self.plot_outputs, row=1, column=7, width=7, height=10)

        self.plot_inputs = UpdatableImageWidget(widget_id='plot_inputs')
        self.popup.group.addWidget(self.plot_inputs, row=1, column=14, width=7, height=10)

        self.plot_convergence = UpdatableImageWidget(widget_id='plot_convergence')
        self.popup.group.addWidget(self.plot_convergence, row=11, column=7, width=7, height=10)

        self.plot_model = UpdatableImageWidget(widget_id='plot_model')
        self.popup.group.addWidget(self.plot_model, row=11, column=14, width=7, height=10)

        self._plot_all()

    # === EVENT REGISTRATION ===========================================================================================

    def _register_events(self):
        exp = self.experiment
        exp.events.experiment_started.on(self._onExperimentStarted)
        exp.events.trial_started.on(self._onTrialStarted)
        exp.events.trial_prepared.on(self._onTrialPrepared)
        exp.events.trajectory_started.on(self._onTrajectoryStarted)
        exp.events.trajectory_finished.on(self._onTrajectoryFinished)
        exp.events.trial_finished.on(self._onTrialFinished)
        exp.events.trial_reverted.on(self._onTrialReverted)
        exp.events.experiment_finished.on(self._onExperimentFinished)
        exp.events.experiment_error.on(self._onExperimentError)
        exp.callbacks.meta_settings_changed.register(self._onMetaSettingsChanged, discard_inputs=True)

    # === STATUS HELPERS ===============================================================================================

    def _set_state(self, text, color):
        self.status_widget.elements['state'].status = text
        self.status_widget.elements['state'].color = color
        self.status_widget.updateConfig()

    def _set_trial_counter(self, current, total):
        self.status_widget.elements['trial'].status = f'{current} / {total}'
        self.status_widget.updateConfig()

    def _update_best_trial(self):
        trials = self.experiment.trials
        if not trials:
            return
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

    @staticmethod
    def _fmt(v):
        return f'{v:.6f}' if v is not None else '—'

    def _rebuild_table(self):
        for row in self._trial_rows:
            try:
                row.delete()
            except Exception:
                pass
        self._trial_rows = []

        trials = self.experiment.trials
        if not trials:
            return
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

    # === EVENT HANDLERS ===============================================================================================

    def _onExperimentStarted(self, *args, **kwargs):
        self._set_state('Started', _COLOR_PREPARING)

    def _onTrialStarted(self, *args, **kwargs):
        j = len(self.experiment.trials) + 1
        J = self.experiment.settings.J if self.experiment.settings else '?'
        self._set_state('Preparing Trial', _COLOR_PREPARING)
        self._set_trial_counter(j, J)

    def _onTrialPrepared(self, *args, **kwargs):
        self._set_state('Waiting for Input', _COLOR_WAITING)

    def _onTrajectoryStarted(self, *args, **kwargs):
        self._set_state('Running Trajectory', _COLOR_TRAJECTORY)

    def _onTrajectoryFinished(self, *args, **kwargs):
        self._set_state('Computing Update', _COLOR_COMPUTING)

    def _onTrialFinished(self, *args, **kwargs):
        if self.experiment.auto_accept_trials:
            self._set_state('Trial Done', _COLOR_PREPARING)
        else:
            self._set_state('Accept / Revert?', _COLOR_WAITING)
        self._update_best_trial()
        self._rebuild_table()
        self._plot_all()

    def _onTrialReverted(self, *args, **kwargs):
        self._set_state('Trial Reverted', _COLOR_WAITING)

    def _onExperimentFinished(self, *args, **kwargs):
        self._set_state('Finished', _COLOR_FINISHED)
        j = len(self.experiment.trials)
        J = self.experiment.settings.J if self.experiment.settings else j
        self._set_trial_counter(j, J)
        self._plot_all()

    def _onExperimentError(self, *args, **kwargs):
        self._set_state('Error', _COLOR_ERROR)

    def _onStop(self):
        self.experiment.stop()

    def _onAutoStartToggle(self, state, *args, **kwargs):
        enable = (state == 'OFF')
        self.experiment.set_auto_start_trials(enable)
        self.auto_start_button.state = 'ON' if enable else 'OFF'

    def _onAutoAcceptToggle(self, state, *args, **kwargs):
        enable = (state == 'OFF')
        self.experiment.set_auto_accept_trials(enable)
        self.auto_accept_button.state = 'ON' if enable else 'OFF'

    def _onMetaSettingsChanged(self):
        self.auto_start_button.state = 'ON' if self.experiment.auto_start_trials else 'OFF'
        self.auto_accept_button.state = 'ON' if self.experiment.auto_accept_trials else 'OFF'

    # === PLOT HELPERS =================================================================================================

    @staticmethod
    def _new_figure(figsize=(6, 4), dpi=200):
        fig = Figure(figsize=figsize, dpi=dpi)
        FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        return fig, ax

    def _get_colors(self):
        J = self.experiment.settings.J if self.experiment.settings else 10
        anchors = [[0.09, 0.28, 0.67], [0.00, 0.60, 0.33], [0.95, 0.60, 0.10]]
        return get_segmented_progression_colors(max(J, 1), anchors, gamma=1.0)

    def _plot_all(self):
        self._plotOutputs()
        self._plotInputs()
        self._plotConvergence()
        self._plotModel()

    # === PLOT METHODS =================================================================================================

    @staticmethod
    def _predict(u, m):
        """Predicted output of the current model: M(u) m as a causal convolution."""
        u = np.asarray(u, dtype=float)
        m = np.asarray(m, dtype=float)
        return np.convolve(u, m)[:len(u)]

    def _plotOutputs(self):
        fig, ax = self._new_figure()
        ax.set_title("Measured vs predicted output (current model)", color="black")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Angle [deg]")
        ax.grid(True, alpha=0.3)

        trials = self.experiment.trials
        if trials:
            trial = trials[-1]
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
            ax.legend(loc="upper right")
        self.plot_outputs.setFromMatplotLib(fig, dpi=200)

    def _plotInputs(self):
        fig, ax = self._new_figure()
        ax.set_title("Inputs", color="black")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Input")
        ax.grid(True, alpha=0.3)

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
                    label=f"u (trial {i + 1})" if is_latest else None,
                    zorder=3 if is_latest else 2)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc="upper right")
        self.plot_inputs.setFromMatplotLib(fig, dpi=200)

    def _plotConvergence(self):
        J = self.experiment.settings.J if self.experiment.settings else 10
        fig, ax = self._new_figure()
        ax.set_title("Convergence", color="black")
        ax.set_xlabel("Trial")
        ax.set_ylabel("Norm (log)")
        ax.set_yscale("log")
        ax.set_xlim([0, J + 1])
        ax.grid(True, which="both", alpha=0.3)

        trials = self.experiment.trials
        if trials:
            x = np.arange(1, len(trials) + 1)
            e_out = np.array([t.model_output_error_norm for t in trials], dtype=float)
            ax.plot(x, e_out, color="C1", lw=2, marker="o", ms=4, label="output error")
            e_fit = np.array([t.model_fit_error_norm if t.model_fit_error_norm is not None
                              else np.nan for t in trials], dtype=float)
            if np.any(np.isfinite(e_fit)):
                ax.plot(x, e_fit, color="C0", lw=2, marker="s", ms=4, label="fit residual")
            e_m = np.array([t.model_estimation_error_norm if t.model_estimation_error_norm is not None
                            else np.nan for t in trials], dtype=float)
            if np.any(np.isfinite(e_m)):
                ax.plot(x, e_m, color="C2", lw=1.5, marker="^", ms=3, alpha=0.7, label="estimation error")
        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc="upper right")
        self.plot_convergence.setFromMatplotLib(fig, dpi=200)

    def _plotModel(self):
        fig, ax = self._new_figure()
        ax.set_title("Identified model (impulse response)", color="black")
        ax.set_xlabel("Tap k")
        ax.set_ylabel("m[k]")
        ax.grid(True, alpha=0.3)

        ref = None
        if self.experiment.settings is not None:
            ref = self.experiment.settings.reference_model
        if ref is not None:
            ax.plot(np.asarray(ref), color="black", lw=1.5, linestyle="--", label="reference")

        trials = self.experiment.trials
        if trials and trials[-1].model_vector_update is not None:
            m = np.asarray(trials[-1].model_vector_update)
            ax.plot(m, color="C0", lw=2, label=f"m (trial {len(trials)})")
        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc="upper right")
        self.plot_model.setFromMatplotLib(fig, dpi=200)
