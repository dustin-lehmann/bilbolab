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
from robots.bilbo.robot.experiment.dilc import DILC_Experiment

# Status indicator colors
_COLOR_IDLE = [0.4, 0.4, 0.4]
_COLOR_PREPARING = [0.2, 0.55, 0.85]
_COLOR_TRAJECTORY = [0.86, 0.87, 0.29]
_COLOR_WAITING = [0.72, 0.42, 0.19]
_COLOR_COMPUTING = [0.3, 0.3, 0.75]
_COLOR_FINISHED = [0.0, 0.5, 0.0]
_COLOR_ERROR = [0.7, 0.0, 0.0]
_COLOR_BEST = [0.0, 0.6, 0.25]


class DILC_APP(GUI_Popup_Application):
    experiment: DILC_Experiment

    def __init__(self, gui, robot: BILBO, experiment: DILC_Experiment, config: dict = None):
        super().__init__('dilc_app', 'DILC APP', config)
        self.gui = gui
        self.robot = robot
        self.experiment = experiment
        self._trial_rows = []

        exp_id = experiment.settings.id if experiment.settings else 'DILC'
        self.popup = Popup(f"{self.id}_popup",
                           title=f'DILC — {exp_id}',
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
        # --- LEFT PANEL: Status, Table, Controls (col 1–6) ---

        # Status: state, trial counter, best trial
        self.status_widget = StatusWidget(
            widget_id='experiment_status',
            title='Experiment',
            elements={
                'state': StatusWidgetElement(label='State:', color=_COLOR_IDLE, status='Idle'),
                'trial': StatusWidgetElement(label='Trial:', color=[0.4, 0.4, 0.4], status='—'),
                'best': StatusWidgetElement(label='Best:', color=[0.4, 0.4, 0.4], status='—'),
            }
        )
        self.popup.group.addWidget(self.status_widget, row=1, column=1, width=6, height=3)

        # Trial results table
        self.trial_table = Table(widget_id='trial_table')
        self.trial_table.add_column(TextColumn(id='num', title='#', width=0.12, font_align='center'))
        self.trial_table.add_column(TextColumn(id='e_ilc', title='ILC Error', width=0.40, font_align='right'))
        self.trial_table.add_column(TextColumn(id='e_iml', title='IML Error', width=0.40, font_align='right'))
        self.popup.group.addWidget(self.trial_table, row=4, column=1, width=6, height=10)

        # Control group
        self.group_control = Widget_Group(group_id='control', title='Control',
                                          show_title=True, rows=2, columns=5)
        self.popup.group.addWidget(self.group_control, row=14, column=1, width=6, height=4)

        # Resume
        self.resume_button = Button(widget_id='resume_button', text='Resume', color=[0.0, 0.4, 0.0])
        self.resume_button.callbacks.click.register(self.robot.core.set_resume_event_robot, discard_inputs=True)
        self.group_control.addWidget(self.resume_button, row=1, column=3, width=1, height=1)

        # Revert
        self.revert_button = Button(widget_id='revert_button', text='Revert', color=[110 / 255, 82 / 255, 0])
        self.revert_button.callbacks.click.register(self.robot.core.set_repeat_event_robot, discard_inputs=True)
        self.group_control.addWidget(self.revert_button, row=1, column=4, width=1, height=1)

        # Abort
        self.stop_button = Button(widget_id='stop_button', text='Stop', color=[0.5, 0.0, 0.0])
        self.stop_button.callbacks.click.register(self._onStop, discard_inputs=True)
        self.group_control.addWidget(self.stop_button, row=1, column=5, width=1, height=1)

        # Auto-start toggle
        self.auto_start_button = MultiStateButton(
            id='auto_start_button', states=['OFF', 'ON'],
            current_state='ON' if self.experiment.auto_start_trials else 'OFF',
            color=[[0.5, 0.5, 0.5], [0, 0.4, 0]], title='Auto Start',
        )
        self.auto_start_button.callbacks.click.register(self._onAutoStartToggle)
        self.group_control.addWidget(self.auto_start_button, row=2, column=1, width=2, height=1)

        # Auto-accept toggle
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

        self.plot_error_norms = UpdatableImageWidget(widget_id='plot_error_norms')
        self.popup.group.addWidget(self.plot_error_norms, row=11, column=7, width=7, height=10)

        self.plot_iml_error_norms = UpdatableImageWidget(widget_id='plot_iml_error_norms')
        self.popup.group.addWidget(self.plot_iml_error_norms, row=11, column=14, width=7, height=10)

        # Initial plots (reference + u0 on load)
        self._plotOutputData()
        self._plotInputs()
        self._plotErrorNorms()
        self._plotIMLErrorNorms()

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
        best = min(trials, key=lambda t: t.e_norm_ilc)
        self.status_widget.elements['best'].status = f'Trial {best.trial_index + 1}  ({best.e_norm_ilc:.6f})'
        self.status_widget.elements['best'].color = _COLOR_BEST
        self.status_widget.updateConfig()

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

        best_idx = min(range(len(trials)), key=lambda i: trials[i].e_norm_ilc)

        for i, trial in enumerate(trials):
            row = self.trial_table.make_row(
                num=str(trial.trial_index + 1),
                e_ilc=f'{trial.e_norm_ilc:.6f}',
                e_iml=f'{trial.e_norm_iml:.6f}',
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
        self._plotOutputData()
        self._plotInputs()
        self._plotErrorNorms()
        self._plotIMLErrorNorms()

    def _onTrialReverted(self, *args, **kwargs):
        self._set_state('Trial Reverted', _COLOR_WAITING)

    def _onExperimentFinished(self, *args, **kwargs):
        self._set_state('Finished', _COLOR_FINISHED)
        j = len(self.experiment.trials)
        J = self.experiment.settings.J if self.experiment.settings else j
        self._set_trial_counter(j, J)

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

    def _get_output_colors(self):
        J = self.experiment.settings.J if self.experiment.settings else 10
        anchors = [[0.09, 0.28, 0.67], [0.00, 0.60, 0.33], [0.95, 0.60, 0.10]]
        return get_segmented_progression_colors(max(J, 1), anchors, gamma=1.0)

    # === PLOT METHODS =================================================================================================

    def _plotOutputData(self):
        fig, ax = self._new_figure()
        ax.set_title("Outputs", color="black")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Angle [deg]")
        ax.grid(True, alpha=0.3)

        trials = self.experiment.trials
        colors = self._get_output_colors()

        # Reference trajectory (always shown)
        if self.experiment.settings and self.experiment.settings.reference is not None:
            ref = np.asarray(self.experiment.settings.reference)
            if trials and trials[-1].t is not None:
                t_ref = np.asarray(trials[-1].t)
            else:
                t_ref = np.arange(len(ref)) * self.experiment.settings.Ts
            ax.plot(t_ref, np.rad2deg(ref), color="black", lw=2, linestyle="--",
                    label="Reference", zorder=1)

        n = len(trials)
        for i, trial in enumerate(trials):
            if trial.theta is None or trial.t is None:
                continue
            t = np.asarray(trial.t)
            theta = np.rad2deg(np.asarray(trial.theta))
            is_latest = (i == n - 1)
            ax.plot(t, theta,
                    lw=2.5 if is_latest else 1.2,
                    color=colors[i % max(1, len(colors))],
                    alpha=1.0 if is_latest else 0.3,
                    label=f"Trial {i + 1}" if is_latest else None,
                    zorder=3 if is_latest else 2)

        ax.legend(loc="upper right")
        self.plot_outputs.setFromMatplotLib(fig, dpi=200)

    def _plotInputs(self):
        fig, ax = self._new_figure()
        ax.set_title("Inputs", color="black")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Input")
        ax.grid(True, alpha=0.3)

        trials = self.experiment.trials
        colors = self._get_output_colors()
        n = len(trials)

        # Show u0 when no trials yet
        if n == 0 and self.experiment.settings and self.experiment.settings.u0 is not None:
            u0 = np.asarray(self.experiment.settings.u0)
            t_u0 = np.arange(len(u0)) * self.experiment.settings.Ts
            ax.plot(t_u0, u0, lw=1.5, color="gray", linestyle="--", label="u0", zorder=1)

        for i, trial in enumerate(trials):
            if trial.u is None or trial.t is None:
                continue
            t = np.asarray(trial.t)
            u = np.asarray(trial.u)
            is_latest = (i == n - 1)
            ax.plot(t, u,
                    lw=2.5 if is_latest else 1.2,
                    color=colors[i % max(1, len(colors))],
                    alpha=1.0 if is_latest else 0.3,
                    label=f"Input {i + 1}" if is_latest else None,
                    zorder=3 if is_latest else 2)

        ax.legend(loc="upper right")
        self.plot_inputs.setFromMatplotLib(fig, dpi=200)

    def _plotErrorNorms(self):
        J = self.experiment.settings.J if self.experiment.settings else 10

        fig, ax = self._new_figure()
        ax.set_title("Error Norms ILC", color="black")
        ax.set_xlabel("Trial")
        ax.set_ylabel("Error Norm")
        ax.set_xlim([0, J + 1])
        ax.grid(True, alpha=0.3)

        trials = self.experiment.trials
        if trials:
            x = np.arange(1, len(trials) + 1)
            y = np.array([t.e_norm_ilc for t in trials], dtype=float)
            ymax = np.nanmax(y) if np.nanmax(y) > 0 else 1.0
            ax.set_ylim(0, ymax * 1.15)
            ax.plot(x, y, color="red", lw=2, zorder=1, label="Error norm")
            ax.scatter(x, y, s=36, color="red", edgecolors="white", linewidths=0.8, zorder=2)

        ax.legend(loc="upper right")
        self.plot_error_norms.setFromMatplotLib(fig, dpi=200)

    def _plotIMLErrorNorms(self):
        J = self.experiment.settings.J if self.experiment.settings else 10

        fig, ax = self._new_figure()
        ax.set_title("Error Norms IML", color="black")
        ax.set_xlabel("Trial")
        ax.set_ylabel("Error Norm")
        ax.set_xlim([0, J + 1])
        ax.grid(True, alpha=0.3)

        trials = self.experiment.trials
        if trials:
            x = np.arange(1, len(trials) + 1)
            y = np.array([t.e_norm_iml for t in trials], dtype=float)
            ymax = np.nanmax(y) if np.nanmax(y) > 0 else 1.0
            ax.set_ylim(0, ymax * 1.15)
            ax.plot(x, y, color="red", lw=2, zorder=1, label="Error norm")
            ax.scatter(x, y, s=36, color="red", edgecolors="white", linewidths=0.8, zorder=2)

        ax.legend(loc="upper right")
        self.plot_iml_error_norms.setFromMatplotLib(fig, dpi=200)
