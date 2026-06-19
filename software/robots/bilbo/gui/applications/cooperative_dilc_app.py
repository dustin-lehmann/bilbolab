"""GUI popup for the cooperative (multi-agent) DILC experiment.

Mirrors the structure of ``DILC_APP`` but shows the multi-agent information the
base DILC panel cannot: the per-agent input/output traces, the per-agent
tracking-error convergence, which agent was elected leader each trial, and the
best-performance fusion weights.

The per-agent data is read from the ``trial_finished`` event payload (the robot
sends ``u_per_agent`` / ``y_per_agent`` / ``e_norm_per_agent`` / ``leader`` /
``bp_weights``), accumulated locally per trial -- the host proxy's ``trials``
list only carries the leader's trace.
"""
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from core.utils.exit import register_exit_callback
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.buttons import Button, MultiStateButton
from extensions.gui.src.lib.objects.python.image import UpdatableImageWidget
from extensions.gui.src.lib.objects.python.popup import Popup
from extensions.gui.src.lib.objects.python.popup_application import GUI_Popup_Application
from extensions.gui.src.lib.objects.python.table import Table, TextColumn
from extensions.gui.src.lib.objects.python.text import StatusWidget, StatusWidgetElement
from robots.bilbo.robot.bilbo import BILBO

# Status indicator colors
_COLOR_IDLE = [0.4, 0.4, 0.4]
_COLOR_PREPARING = [0.2, 0.55, 0.85]
_COLOR_TRAJECTORY = [0.86, 0.87, 0.29]
_COLOR_WAITING = [0.72, 0.42, 0.19]
_COLOR_COMPUTING = [0.3, 0.3, 0.75]
_COLOR_FINISHED = [0.0, 0.5, 0.0]
_COLOR_ERROR = [0.7, 0.0, 0.0]
_COLOR_BEST = [0.0, 0.6, 0.25]

# Per-agent colours (aggressive / balanced / conservative / ...).
_AGENT_COLORS = [
    [0.30, 0.45, 0.69],   # blue
    [0.77, 0.31, 0.32],   # red
    [0.33, 0.66, 0.41],   # green
    [0.87, 0.52, 0.32],   # orange
    [0.51, 0.45, 0.70],   # purple
    [0.55, 0.55, 0.55],   # grey
]


def _agent_color(i: int):
    return _AGENT_COLORS[i % len(_AGENT_COLORS)]


class CooperativeDILC_APP(GUI_Popup_Application):
    """Popup application for the cooperative multi-agent DILC experiment."""

    def __init__(self, gui, robot: BILBO, experiment, config: dict = None):
        super().__init__('cooperative_dilc_app', 'Cooperative DILC APP', config)
        self.gui = gui
        self.robot = robot
        self.experiment = experiment
        self._trial_rows = []
        self._coop_trials: list[dict] = []   # accumulated per-trial cooperative records

        exp_id = experiment.settings.id if experiment.settings else 'Cooperative DILC'
        self.popup = Popup(f"{self.id}_popup",
                           title=f'Cooperative DILC — {exp_id}',
                           allow_multiple=False,
                           grid=[20, 20],
                           size=[1400, 850],
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

    @property
    def _n_agents(self) -> int:
        s = self.experiment.settings
        return int(getattr(s, 'n_agents', 3)) if s else 3

    def _agent_label(self, i: int) -> str:
        s = self.experiment.settings
        g = getattr(s, 'het_gain_factors', None) if s else None
        if g is not None and i < len(g):
            return f"agent {i + 1} (γ={g[i]:g})"
        return f"agent {i + 1}"

    # === BUILD UI =====================================================================================================

    def _build_popup(self):
        # --- LEFT PANEL: Status, Table, Controls (col 1–6) ---
        self.status_widget = StatusWidget(
            widget_id='experiment_status',
            title='Experiment',
            elements={
                'state': StatusWidgetElement(label='State:', color=_COLOR_IDLE, status='Idle'),
                'trial': StatusWidgetElement(label='Trial:', color=[0.4, 0.4, 0.4], status='—'),
                'leader': StatusWidgetElement(label='Leader:', color=[0.4, 0.4, 0.4], status='—'),
                'best': StatusWidgetElement(label='Best:', color=[0.4, 0.4, 0.4], status='—'),
            }
        )
        self.popup.group.addWidget(self.status_widget, row=1, column=1, width=6, height=4)

        # Trial results table: #, leader, leader error, model error
        self.trial_table = Table(widget_id='trial_table')
        self.trial_table.add_column(TextColumn(id='num', title='#', width=0.12, font_align='center'))
        self.trial_table.add_column(TextColumn(id='leader', title='Leader', width=0.24, font_align='center'))
        self.trial_table.add_column(TextColumn(id='e_ilc', title='Best e', width=0.32, font_align='right'))
        self.trial_table.add_column(TextColumn(id='e_iml', title='Model e', width=0.32, font_align='right'))
        self.popup.group.addWidget(self.trial_table, row=5, column=1, width=6, height=9)

        # Control group
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

        self.plot_leader = UpdatableImageWidget(widget_id='plot_leader')
        self.popup.group.addWidget(self.plot_leader, row=11, column=14, width=7, height=10)

        self._plotPerAgentOutputs()
        self._plotPerAgentInputs()
        self._plotConvergence()
        self._plotLeader()

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

    def _set_leader(self, leader):
        if leader is None:
            self.status_widget.elements['leader'].status = '—'
            self.status_widget.elements['leader'].color = [0.4, 0.4, 0.4]
        else:
            self.status_widget.elements['leader'].status = f'agent {leader + 1}'
            self.status_widget.elements['leader'].color = _agent_color(leader)
        self.status_widget.updateConfig()

    def _update_best_trial(self):
        if not self._coop_trials:
            return
        best_i = int(np.argmin([t['e_norm_ilc'] for t in self._coop_trials]))
        best = self._coop_trials[best_i]
        self.status_widget.elements['best'].status = f"Trial {best_i + 1}  ({best['e_norm_ilc']:.6f})"
        self.status_widget.elements['best'].color = _COLOR_BEST
        self.status_widget.updateConfig()

    def _rebuild_table(self):
        for row in self._trial_rows:
            try:
                row.delete()
            except Exception:
                pass
        self._trial_rows = []
        if not self._coop_trials:
            return
        best_i = int(np.argmin([t['e_norm_ilc'] for t in self._coop_trials]))
        for i, trial in enumerate(self._coop_trials):
            row = self.trial_table.make_row(
                num=str(i + 1),
                leader=f"a{trial['leader'] + 1}",
                e_ilc=f"{trial['e_norm_ilc']:.5f}",
                e_iml=f"{trial['e_norm_iml']:.5f}",
            )
            if i == best_i:
                row.highlight = True
                row.row_background_color = [0, 0.35, 0.15, 0.3]
            self._trial_rows.append(row)

    # === EVENT HANDLERS ===============================================================================================

    @staticmethod
    def _event_data(data, kwargs) -> dict:
        if isinstance(data, dict):
            return data
        d = kwargs.get('data')
        return d if isinstance(d, dict) else {}

    def _onExperimentStarted(self, *args, **kwargs):
        self._set_state('Started', _COLOR_PREPARING)

    def _onTrialStarted(self, *args, **kwargs):
        j = len(self._coop_trials) + 1
        J = self.experiment.settings.J if self.experiment.settings else '?'
        self._set_state('Preparing Trial', _COLOR_PREPARING)
        self._set_trial_counter(j, J)

    def _onTrialPrepared(self, *args, **kwargs):
        self._set_state('Running Agents', _COLOR_WAITING)

    def _onTrajectoryStarted(self, *args, **kwargs):
        self._set_state('Running Trajectory', _COLOR_TRAJECTORY)

    def _onTrajectoryFinished(self, *args, **kwargs):
        self._set_state('Computing Update', _COLOR_COMPUTING)

    def _onTrialFinished(self, data=None, *args, **kwargs):
        d = self._event_data(data, kwargs)
        if d:
            self._coop_trials.append({
                'leader': int(d.get('leader', 0)),
                'e_norm_ilc': float(d.get('e_norm_ilc', 0.0)),
                'e_norm_iml': float(d.get('e_norm_iml', 0.0)),
                's_applied': float(d.get('s_applied', 0.0)),
                'bp_weights': np.asarray(d.get('bp_weights', []), dtype=float),
                'e_norm_per_agent': np.asarray(d.get('e_norm_per_agent', []), dtype=float),
                'u_per_agent': np.asarray(d.get('u_per_agent', []), dtype=float),
                'y_per_agent': np.asarray(d.get('y_per_agent', []), dtype=float),
                't': np.asarray(d.get('t', []), dtype=float),
                'reference': np.asarray(d.get('reference', []), dtype=float),
            })
            self._set_leader(int(d.get('leader', 0)))

        if self.experiment.auto_accept_trials:
            self._set_state('Trial Done', _COLOR_PREPARING)
        else:
            self._set_state('Accept / Revert?', _COLOR_WAITING)

        self._update_best_trial()
        self._rebuild_table()
        self._plotPerAgentOutputs()
        self._plotPerAgentInputs()
        self._plotConvergence()
        self._plotLeader()

    def _onTrialReverted(self, *args, **kwargs):
        self._set_state('Trial Reverted', _COLOR_WAITING)

    def _onExperimentFinished(self, *args, **kwargs):
        self._set_state('Finished', _COLOR_FINISHED)

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

    def _reference(self):
        s = self.experiment.settings
        if s is not None and getattr(s, 'reference', None) is not None:
            return np.asarray(s.reference, dtype=float)
        if self._coop_trials:
            return self._coop_trials[-1]['reference']
        return None

    # === PLOT METHODS =================================================================================================

    def _plotPerAgentOutputs(self):
        fig, ax = self._new_figure()
        ax.set_title("Per-agent outputs (latest trial)", color="black")
        ax.set_xlabel("Time [s]"); ax.set_ylabel("Angle [deg]")
        ax.grid(True, alpha=0.3)

        ref = self._reference()
        if self._coop_trials:
            trial = self._coop_trials[-1]
            t = trial['t']
            if ref is not None and ref.size:
                t_ref = t if t.size == ref.size else np.arange(ref.size)
                ax.plot(t_ref, np.rad2deg(ref), color="black", lw=2, ls="--",
                        label="reference", zorder=1)
            y = trial['y_per_agent']
            for i in range(y.shape[0]):
                lead = (i == trial['leader'])
                ax.plot(t if t.size == y.shape[1] else np.arange(y.shape[1]),
                        np.rad2deg(y[i]), color=_agent_color(i),
                        lw=2.6 if lead else 1.4, alpha=1.0 if lead else 0.6,
                        label=self._agent_label(i) + (" [leader]" if lead else ""),
                        zorder=3 if lead else 2)
        elif ref is not None and ref.size:
            ax.plot(np.arange(ref.size), np.rad2deg(ref), color="black", lw=2, ls="--",
                    label="reference")
        ax.legend(loc="upper right", fontsize=7)
        self.plot_outputs.setFromMatplotLib(fig, dpi=200)

    def _plotPerAgentInputs(self):
        fig, ax = self._new_figure()
        ax.set_title("Per-agent inputs (latest trial)", color="black")
        ax.set_xlabel("Time [s]"); ax.set_ylabel("Input")
        ax.grid(True, alpha=0.3)
        if self._coop_trials:
            trial = self._coop_trials[-1]
            t = trial['t']; u = trial['u_per_agent']
            for i in range(u.shape[0]):
                lead = (i == trial['leader'])
                ax.plot(t if t.size == u.shape[1] else np.arange(u.shape[1]),
                        u[i], color=_agent_color(i),
                        lw=2.6 if lead else 1.4, alpha=1.0 if lead else 0.6,
                        label=self._agent_label(i) + (" [leader]" if lead else ""),
                        zorder=3 if lead else 2)
            ax.legend(loc="upper right", fontsize=7)
        self.plot_inputs.setFromMatplotLib(fig, dpi=200)

    def _plotConvergence(self):
        J = self.experiment.settings.J if self.experiment.settings else 10
        fig, ax = self._new_figure()
        ax.set_title("Per-agent tracking-error convergence", color="black")
        ax.set_xlabel("Trial"); ax.set_ylabel("Error norm")
        ax.set_xlim([0, J + 1]); ax.grid(True, alpha=0.3)
        if self._coop_trials:
            x = np.arange(1, len(self._coop_trials) + 1)
            ea = np.array([t['e_norm_per_agent'] for t in self._coop_trials])  # (T, A)
            if ea.ndim == 2 and ea.shape[1] > 0:
                for i in range(ea.shape[1]):
                    ax.plot(x, ea[:, i], color=_agent_color(i), lw=1.4, alpha=0.7,
                            marker='o', markersize=3, label=self._agent_label(i))
            # Best (deployed leader) error in bold black.
            best = np.array([t['e_norm_ilc'] for t in self._coop_trials])
            ax.plot(x, best, color="black", lw=2.4, marker='*', markersize=8,
                    label="deployed (leader)", zorder=5)
            ax.set_yscale('log')
            ax.legend(loc="upper right", fontsize=7)
        self.plot_convergence.setFromMatplotLib(fig, dpi=200)

    def _plotLeader(self):
        fig, ax = self._new_figure()
        ax.set_title("Leader per trial  &  BP weights (latest)", color="black")
        ax.grid(True, alpha=0.3)
        if self._coop_trials:
            A = self._coop_trials[-1]['e_norm_per_agent'].shape[0]
            x = np.arange(1, len(self._coop_trials) + 1)
            leaders = np.array([t['leader'] for t in self._coop_trials])
            # Leader per trial (scatter, coloured by agent).
            for i in range(A):
                mask = leaders == i
                if mask.any():
                    ax.scatter(x[mask], leaders[mask] + 1, s=90, color=_agent_color(i),
                               edgecolors="white", linewidths=0.8, zorder=3,
                               label=self._agent_label(i))
            ax.step(x, leaders + 1, where='mid', color=[0.6, 0.6, 0.6], lw=1.0, zorder=1)
            ax.set_xlabel("Trial"); ax.set_ylabel("Elected agent")
            ax.set_yticks(range(1, A + 1))
            ax.set_xlim([0, (self.experiment.settings.J if self.experiment.settings else 10) + 1])
            ax.set_ylim([0.5, A + 0.5])
            ax.legend(loc="upper right", fontsize=7)
        self.plot_leader.setFromMatplotLib(fig, dpi=200)
