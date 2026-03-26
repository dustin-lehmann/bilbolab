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
_COLOR_HIT = [0.7, 0.0, 0.0]
_COLOR_MISS = [0.0, 0.5, 0.0]


class DILC_ExperimentPage:
    """Manages a FolderPage for DILC and LimboBar DILC experiments.

    Pre-builds the page with status, table, buttons, and plots.
    Call `bind_experiment()` when an experiment is initialized and
    `unbind_experiment()` on cleanup.
    """

    def __init__(self, robot):
        self.robot = robot
        self.logger = Logger("DILC Page")
        self.experiment: DILC_Experiment | None = None
        self._is_limbobar = False
        self._trial_rows = []
        self._event_handles = []

        self.page = FolderPage(page_id='dilc', name='DILC', rows=10, columns=8)
        self._build_page()

    # === BUILD ============================================================================================

    def _build_page(self):
        # --- Row 1: Status ---
        self.status_widget = StatusWidget(
            widget_id='dilc_page_status',
            title='DILC',
            elements={
                'state': StatusWidgetElement(label='State:', color=_COLOR_IDLE, status='No Experiment'),
                'trial': StatusWidgetElement(label='Trial:', color=_COLOR_IDLE, status='--'),
                'best': StatusWidgetElement(label='Best:', color=_COLOR_IDLE, status='--'),
                'hits': StatusWidgetElement(label='Hits:', color=_COLOR_IDLE, status='--'),
            },
            font_size=9,
        )
        self.page.addObject(self.status_widget, row=1, column=1, width=4, height=2)

        # --- Row 1-2: Trial table ---
        self.trial_table = Table(widget_id='dilc_page_table')
        self.trial_table.add_column(TextColumn(id='num', title='#', width=0.10, font_align='center'))
        self.trial_table.add_column(TextColumn(id='e_ilc', title='ILC Err', width=0.25, font_align='right'))
        self.trial_table.add_column(TextColumn(id='e_iml', title='IML Err', width=0.25, font_align='right'))
        self.trial_table.add_column(TextColumn(id='hit', title='Hit', width=0.15, font_align='center'))
        self.page.addObject(self.trial_table, row=1, column=5, width=4, height=2)

        # --- Row 3: Control buttons ---
        self.group_control = Widget_Group(group_id='dilc_page_control', title='Control',
                                          show_title=False, rows=1, columns=8)
        self.page.addObject(self.group_control, row=3, column=1, width=8, height=1)

        self.resume_button = Button(widget_id='dilc_page_resume', text='Resume', color=[0.0, 0.4, 0.0])
        self.resume_button.callbacks.click.register(self.robot.core.set_resume_event_robot, discard_inputs=True)
        self.group_control.addWidget(self.resume_button, row=1, column=1, width=1, height=1)

        self.revert_button = Button(widget_id='dilc_page_revert', text='Revert', color=[110 / 255, 82 / 255, 0])
        self.revert_button.callbacks.click.register(self.robot.core.set_repeat_event_robot, discard_inputs=True)
        self.group_control.addWidget(self.revert_button, row=1, column=2, width=1, height=1)

        self.stop_button = Button(widget_id='dilc_page_stop', text='Stop', color=[0.5, 0.0, 0.0])
        self.stop_button.callbacks.click.register(self._on_stop, discard_inputs=True)
        self.group_control.addWidget(self.stop_button, row=1, column=3, width=1, height=1)

        self.auto_start_button = MultiStateButton(
            id='dilc_page_auto_start', states=['OFF', 'ON'],
            current_state='OFF',
            color=[[0.5, 0.5, 0.5], [0, 0.4, 0]], title='Auto Start',
        )
        self.auto_start_button.callbacks.click.register(self._on_auto_start_toggle)
        self.group_control.addWidget(self.auto_start_button, row=1, column=5, width=2, height=1)

        self.auto_accept_button = MultiStateButton(
            id='dilc_page_auto_accept', states=['OFF', 'ON'],
            current_state='OFF',
            color=[[0.5, 0.5, 0.5], [0, 0.4, 0]], title='Auto Accept',
        )
        self.auto_accept_button.callbacks.click.register(self._on_auto_accept_toggle)
        self.group_control.addWidget(self.auto_accept_button, row=1, column=7, width=2, height=1)

        # --- Rows 4-6: Output + Input plots ---
        self.plot_outputs = UpdatableImageWidget(widget_id='dilc_page_plot_outputs')
        self.page.addObject(self.plot_outputs, row=4, column=1, width=4, height=3)

        self.plot_inputs = UpdatableImageWidget(widget_id='dilc_page_plot_inputs')
        self.page.addObject(self.plot_inputs, row=4, column=5, width=4, height=3)

        # --- Rows 7-9: Error norm plots ---
        self.plot_error_ilc = UpdatableImageWidget(widget_id='dilc_page_plot_error_ilc')
        self.page.addObject(self.plot_error_ilc, row=7, column=1, width=4, height=3)

        self.plot_error_iml = UpdatableImageWidget(widget_id='dilc_page_plot_error_iml')
        self.page.addObject(self.plot_error_iml, row=7, column=5, width=4, height=3)

    # === EXPERIMENT BINDING ================================================================================

    def bind_experiment(self, experiment: DILC_Experiment):
        """Bind to a DILC or LimboBar DILC experiment and start updating the page."""
        self.unbind_experiment()
        self.experiment = experiment
        self._is_limbobar = hasattr(experiment, 'limbo_bar_settings')
        self._has_target_zone = (self._is_limbobar
                                 and experiment.settings is not None
                                 and getattr(experiment.settings, 'target_zone', None) is not None)
        self._trial_rows = []

        # Update title
        exp_id = experiment.settings.id if experiment.settings else 'DILC'
        title = f'LimboBar DILC -- {exp_id}' if self._is_limbobar else f'DILC -- {exp_id}'
        if self._is_limbobar and experiment.settings:
            limbo_height = getattr(experiment.settings, 'limbo_bar', None)
            if limbo_height is not None:
                title += f' (h={limbo_height.height}m)'
        self.status_widget.title = title
        self._set_state('Initialized', _COLOR_PREPARING)
        self.status_widget.elements['trial'].status = '--'
        self.status_widget.elements['best'].status = '--'
        self.status_widget.elements['hits'].status = '--'
        if self._has_target_zone:
            self.status_widget.elements['passes'] = StatusWidgetElement(
                label='Passes:', color=_COLOR_IDLE, status='0 / 0')
        elif 'passes' in self.status_widget.elements:
            del self.status_widget.elements['passes']
        self.status_widget.updateConfig()

        # Sync toggle states
        self.auto_start_button.state = 'ON' if experiment.auto_start_trials else 'OFF'
        self.auto_accept_button.state = 'ON' if experiment.auto_accept_trials else 'OFF'

        # Register experiment events
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

        # Draw initial plots
        self._plot_all()

    def unbind_experiment(self):
        """Disconnect from the current experiment."""
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

        # Clear table rows
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

    def _update_best_trial(self):
        if not self.experiment or not self.experiment.trials:
            return
        trials = self.experiment.trials
        best = min(trials, key=lambda t: t.e_norm_ilc)
        suffix = ''
        if self._is_limbobar and hasattr(best, 'limbo_bar_hit') and best.limbo_bar_hit:
            suffix = ' (HIT)'
        self.status_widget.elements['best'].status = f'Trial {best.trial_index + 1}  ({best.e_norm_ilc:.6f}){suffix}'
        self.status_widget.elements['best'].color = _COLOR_BEST
        self.status_widget.updateConfig()

    def _update_hits_counter(self):
        if not self.experiment or not self._is_limbobar:
            return
        trials = self.experiment.trials
        total_hits = sum(1 for t in trials if getattr(t, 'limbo_bar_hit', False))
        total = len(trials)
        color = _COLOR_HIT if total_hits > 0 else _COLOR_MISS
        self.status_widget.elements['hits'].status = f'{total_hits} / {total}'
        self.status_widget.elements['hits'].color = color
        if self._has_target_zone:
            total_passes = sum(1 for t in trials if getattr(t, 'limbo_bar_passed', None) is True)
            pass_color = _COLOR_MISS if total_passes > 0 else _COLOR_HIT
            self.status_widget.elements['passes'].status = f'{total_passes} / {total}'
            self.status_widget.elements['passes'].color = pass_color
        self.status_widget.updateConfig()

    def _rebuild_table(self):
        for row in self._trial_rows:
            try:
                row.delete()
            except Exception:
                pass
        self._trial_rows = []

        if not self.experiment:
            return
        trials = self.experiment.trials
        if not trials:
            return

        best_idx = min(range(len(trials)), key=lambda i: trials[i].e_norm_ilc)

        for i, trial in enumerate(trials):
            hit_text = '--'
            is_hit = False
            if self._is_limbobar and hasattr(trial, 'limbo_bar_hit'):
                hit_text = 'HIT' if trial.limbo_bar_hit else '--'
                is_hit = trial.limbo_bar_hit

            row_kwargs = dict(
                num=str(trial.trial_index + 1),
                e_ilc=f'{trial.e_norm_ilc:.6f}',
                e_iml=f'{trial.e_norm_iml:.6f}',
                hit=hit_text,
            )
            row = self.trial_table.make_row(**row_kwargs)
            if i == best_idx:
                row.highlight = True
                row.row_background_color = [0, 0.35, 0.15, 0.3]
            if is_hit:
                row.row_background_color = [0.5, 0.0, 0.0, 0.15]
            elif getattr(trial, 'limbo_bar_passed', None) is True:
                row.row_background_color = [0.0, 0.35, 0.15, 0.15]
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
        if self._is_limbobar:
            self._update_hits_counter()
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

    def _get_output_colors(self):
        if not self.experiment or not self.experiment.settings:
            return []
        J = self.experiment.settings.J
        anchors = [[0.09, 0.28, 0.67], [0.00, 0.60, 0.33], [0.95, 0.60, 0.10]]
        return get_segmented_progression_colors(max(J, 1), anchors, gamma=1.0)

    def _plot_all(self):
        self._plot_outputs()
        self._plot_inputs()
        self._plot_error_norms_ilc()
        self._plot_error_norms_iml()

    def _plot_outputs(self):
        fig, ax = self._new_figure()
        ax.set_title("Outputs", color="black", fontsize=10)
        ax.set_xlabel("Time [s]", fontsize=8)
        ax.set_ylabel("Angle [deg]", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3)

        if not self.experiment:
            self.plot_outputs.setFromMatplotLib(fig, dpi=150)
            return

        trials = self.experiment.trials
        colors = self._get_output_colors()

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

            is_hit = self._is_limbobar and getattr(trial, 'limbo_bar_hit', False)
            color = 'red' if is_hit else colors[i % max(1, len(colors))]
            linestyle = '--' if is_hit else '-'

            label_parts = []
            if is_latest:
                label_parts.append(f"Trial {i + 1}")
            if is_hit:
                label_parts.append("HIT")
            label = ' '.join(label_parts) if label_parts else None

            ax.plot(t, theta,
                    lw=2.5 if is_latest else 1.2,
                    color=color, linestyle=linestyle,
                    alpha=1.0 if is_latest else 0.3,
                    label=label, zorder=3 if is_latest else 2)

        ax.legend(loc="upper right", fontsize=7)
        fig.tight_layout()
        self.plot_outputs.setFromMatplotLib(fig, dpi=150)

    def _plot_inputs(self):
        fig, ax = self._new_figure()
        ax.set_title("Inputs", color="black", fontsize=10)
        ax.set_xlabel("Time [s]", fontsize=8)
        ax.set_ylabel("Input", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3)

        if not self.experiment:
            self.plot_inputs.setFromMatplotLib(fig, dpi=150)
            return

        trials = self.experiment.trials
        colors = self._get_output_colors()
        n = len(trials)

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

        ax.legend(loc="upper right", fontsize=7)
        fig.tight_layout()
        self.plot_inputs.setFromMatplotLib(fig, dpi=150)

    def _plot_error_norms_ilc(self):
        fig, ax = self._new_figure()
        ax.set_title("Error Norms ILC", color="black", fontsize=10)
        ax.set_xlabel("Trial", fontsize=8)
        ax.set_ylabel("Error Norm", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3)

        if self.experiment and self.experiment.settings:
            J = self.experiment.settings.J
            ax.set_xlim([0, J + 1])

            trials = self.experiment.trials
            if trials:
                x = np.arange(1, len(trials) + 1)
                y = np.array([t.e_norm_ilc for t in trials], dtype=float)
                ymax = np.nanmax(y) if np.nanmax(y) > 0 else 1.0
                ax.set_ylim(0, ymax * 1.15)
                ax.plot(x, y, color="red", lw=2, zorder=1, label="Error norm")
                ax.scatter(x, y, s=36, color="red", edgecolors="white", linewidths=0.8, zorder=2)

                if self._is_limbobar:
                    hit_x = [i + 1 for i, t in enumerate(trials) if getattr(t, 'limbo_bar_hit', False)]
                    hit_y = [t.e_norm_ilc for t in trials if getattr(t, 'limbo_bar_hit', False)]
                    if hit_x:
                        ax.scatter(hit_x, hit_y, s=100, color="red", marker='x',
                                   linewidths=2.0, zorder=3, label="Hit")

        ax.legend(loc="upper right", fontsize=7)
        fig.tight_layout()
        self.plot_error_ilc.setFromMatplotLib(fig, dpi=150)

    def _plot_error_norms_iml(self):
        fig, ax = self._new_figure()
        ax.set_title("Error Norms IML", color="black", fontsize=10)
        ax.set_xlabel("Trial", fontsize=8)
        ax.set_ylabel("Error Norm", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3)

        if self.experiment and self.experiment.settings:
            J = self.experiment.settings.J
            ax.set_xlim([0, J + 1])

            trials = self.experiment.trials
            if trials:
                x = np.arange(1, len(trials) + 1)
                y = np.array([t.e_norm_iml for t in trials], dtype=float)
                ymax = np.nanmax(y) if np.nanmax(y) > 0 else 1.0
                ax.set_ylim(0, ymax * 1.15)
                ax.plot(x, y, color="red", lw=2, zorder=1, label="Error norm")
                ax.scatter(x, y, s=36, color="red", edgecolors="white", linewidths=0.8, zorder=2)

        ax.legend(loc="upper right", fontsize=7)
        fig.tight_layout()
        self.plot_error_iml.setFromMatplotLib(fig, dpi=150)
