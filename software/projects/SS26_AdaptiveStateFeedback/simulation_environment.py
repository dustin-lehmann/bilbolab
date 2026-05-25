"""
SS26 — Adaptive State Feedback Simulation Environment
=====================================================

A real-time BILBO simulation built for studying *adaptive state feedback
control*. Unlike the SS25 navigation example, there is **no velocity or
position control** here — the robot only ever runs balancing (LQR-style
state feedback) control.

The point of this environment is to study what happens when the plant the
controller was designed for no longer matches the real plant:

  * The **plant model** (body mass `m_b`, COG height `l`, wheel mass `m_w`,
    body inertia `I_y`) can be changed live, while the simulation runs.
  * The **state feedback gain `K`** can be re-tuned live, either manually
    ("retune" command/button) or automatically ("adaptive" mode, where every
    model change immediately triggers a re-tune).

Typical experiment:
  1. Start the simulation — the robot balances.
  2. Disable "adaptive" mode.
  3. Increase the body mass / raise the COG with the sliders — the controller
     `K` is now designed for the *wrong* plant and the robot starts to wobble
     or fall.
  4. Press "Retune" (or re-enable adaptive mode) — `K` is recomputed for the
     current plant and the robot recovers.

The single robot is created automatically and is always present — there is
deliberately no add/remove-robot command.

Run from the `software/` directory:
    python -m projects.SS26_AdaptiveStateFeedback.simulation_environment
"""

from __future__ import annotations

import copy
import time

import numpy as np

from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from extensions.libs.babylon.src.babylon import BabylonVisualization
from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.tools.cli.cli import CLI, CommandSet, Command, CommandArgument
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.checkbox import CheckboxWidget
from extensions.gui.src.lib.objects.python.sliders import SliderWidget
from extensions.gui.src.lib.objects.python.text import TextWidget, StatusWidget, StatusWidgetElement
from extensions.gui.src.lib.plot.realtime.rt_plot import RT_Plot_Widget, TimeSeries
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS
from simulation.objects.base_environment import BaseEnvironment
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from robots.bilbo.simulation.model import (
    BILBO_DynamicAgent,
    BILBO_3D_State,
    BILBO_3D_Input,
    DEFAULT_BILBO_MODEL,
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS,
)

ROBOT_ID = 'bilbo'
TS = 0.01

# Plant model parameters that are exposed as live-editable sliders.
# Each entry: attribute name on BilboModel -> (label, min, max, increment).
MODEL_PARAMETERS = {
    'm_b': ('Body mass  m_b [kg]', 0.4, 3.0, 0.05),
    'l': ('COG height  l [m]', 0.0, 0.15, 0.005),
    'm_w': ('Wheel mass  m_w [kg]', 0.1, 1.0, 0.05),
    'I_y': ('Body inertia  I_y', 0.001, 0.05, 0.001),
}


# === ADAPTIVE BILBO ===================================================================================================
class AdaptiveBILBO(BILBO_DynamicAgent):
    """A simulated BILBO that only runs balancing state feedback control, but
    whose plant model and feedback gain `K` can be changed at runtime."""

    cli: CommandSet

    base_poles: list
    eigenvectors: np.ndarray
    pole_scale: float
    adaptive: bool

    last_input: BILBO_3D_Input
    _controller_model = None

    # === INIT =========================================================================================================
    def __init__(self, agent_id: str, *args, **kwargs):
        # Each robot gets its own copy of the model so it can be mutated freely.
        super().__init__(agent_id, model=copy.deepcopy(DEFAULT_BILBO_MODEL), Ts=TS, *args, **kwargs)

        self.logger = Logger(f'AdaptiveBILBO {agent_id}', 'DEBUG')

        self.base_poles = list(BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES)
        self.eigenvectors = BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS
        self.pole_scale = 1.0
        self.adaptive = True

        self.last_input = BILBO_3D_Input(M_L=0, M_R=0)
        self.mode = BILBO_Control_Mode.BALANCING

        # Compute the initial feedback gain for the nominal model.
        self.recomputeController()

        self.cli = self._buildCLI()

    # === CONTROLLER ===================================================================================================
    def recomputeController(self):
        """Recompute the state feedback gain `K` for the *current* plant model
        and the current set of (scaled) poles."""
        poles = [p * self.pole_scale for p in self.base_poles]
        self.eigenstructureAssignment(poles=poles, eigenvectors=self.eigenvectors)
        # Remember which model this controller was designed for.
        self._controller_model = copy.deepcopy(self.model)
        self.logger.info(f'Controller re-tuned for current model (pole scale {self.pole_scale:.2f})')

    # ------------------------------------------------------------------------------------------------------------------
    def controllerMismatch(self) -> bool:
        """True if the plant model has been changed since the controller was
        last tuned (i.e. `K` no longer matches the plant)."""
        return self._controller_model != self.model

    # ------------------------------------------------------------------------------------------------------------------
    def setAdaptive(self, adaptive: bool):
        """Enable/disable automatic re-tuning on every model change."""
        self.adaptive = bool(adaptive)
        self.logger.info(f'Adaptive re-tuning {"enabled" if self.adaptive else "disabled"}')
        if self.adaptive and self.controllerMismatch():
            self.recomputeController()

    # ------------------------------------------------------------------------------------------------------------------
    def _cliSetAdaptive(self, state: str):
        """CLI wrapper — parses an 'on/off/true/false/1/0' string."""
        self.setAdaptive(str(state).strip().lower() in ('on', 'true', '1', 'yes'))

    # ------------------------------------------------------------------------------------------------------------------
    def setPoleScale(self, scale: float):
        """Scale all design poles by a common factor (controller aggressiveness)."""
        self.pole_scale = max(0.1, float(scale))
        # A pole change is always an explicit controller change -> always retune.
        self.recomputeController()

    # === MODEL ========================================================================================================
    def setModelParameter(self, parameter: str, value: float):
        """Change a single plant model parameter live. The nonlinear dynamics
        read the model every step, so the change takes effect immediately."""
        if not hasattr(self.model, parameter):
            self.logger.warning(f'Unknown model parameter: {parameter}')
            return
        setattr(self.model, parameter, float(value))
        self.logger.info(f'Model parameter {parameter} -> {value}')
        # In adaptive mode the controller immediately follows the plant.
        if self.adaptive:
            self.recomputeController()

    # ------------------------------------------------------------------------------------------------------------------
    def getModelString(self) -> str:
        m = self.model
        return (f'm_b={m.m_b:.3f}  m_w={m.m_w:.3f}  l={m.l:.4f}  '
                f'I_y={m.I_y:.4f}  d_w={m.d_w:.3f}  r_w={m.r_w:.3f}')

    # === CONTROL ======================================================================================================
    def enableController(self):
        self.mode = BILBO_Control_Mode.BALANCING
        self.logger.info('Balancing controller enabled')

    # ------------------------------------------------------------------------------------------------------------------
    def disableController(self):
        self.mode = BILBO_Control_Mode.OFF
        self.logger.info('Controller disabled (motors off)')

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self, x0: BILBO_3D_State = None):
        self.dynamics.setState(x0 if x0 is not None else BILBO_3D_State(0, 0, 0, 0, 0, 0, 0))
        self.input = BILBO_3D_Input(M_L=0, M_R=0)
        self.last_input = BILBO_3D_Input(M_L=0, M_R=0)
        self.logger.info('State reset to upright')

    # ------------------------------------------------------------------------------------------------------------------
    def push(self, delta_theta: float):
        """Apply an instantaneous pitch disturbance (a 'push')."""
        self.dynamics.state.theta += float(delta_theta)
        self.logger.info(f'Push: theta += {delta_theta:.3f} rad')

    # ------------------------------------------------------------------------------------------------------------------
    def setDisturbance(self, torque: float):
        """Apply a constant disturbance torque (feedforward on both wheels)."""
        self.input = BILBO_3D_Input(M_L=float(torque), M_R=float(torque))
        self.logger.info(f'Disturbance torque -> {torque:.3f} Nm')

    # ------------------------------------------------------------------------------------------------------------------
    def isFallen(self) -> bool:
        return abs(float(self.dynamics.state.theta)) > 0.9 * float(self.model.max_pitch)

    # === PRIVATE METHODS ==============================================================================================
    def _controller(self) -> BILBO_3D_Input:
        """Runs every time step before the dynamics. Balancing-only."""
        if self.mode == BILBO_Control_Mode.BALANCING:
            controller_input = self.input.asarray() - self.K @ self.dynamics.state.asarray()
        else:  # OFF (or anything else) -> no motor torque
            controller_input = np.zeros(2)

        self.last_input = BILBO_3D_Input.as_state(controller_input)
        return self.last_input

    # ------------------------------------------------------------------------------------------------------------------
    def _buildCLI(self) -> CommandSet:
        cli = CommandSet(self.agent_id, description='Adaptive state feedback BILBO')

        cli.addCommand(Command(name='enable', function=self.enableController,
                               description='Enable the balancing controller'))
        cli.addCommand(Command(name='disable', function=self.disableController,
                               description='Disable the controller (motors off)'))
        cli.addCommand(Command(name='reset', function=self.reset,
                               description='Reset the robot to the upright state'))
        cli.addCommand(Command(name='retune', function=self.recomputeController,
                               description='Recompute K for the current plant model'))
        cli.addCommand(Command(name='model', function=lambda: self.logger.info(self.getModelString()),
                               description='Print the current plant model parameters'))
        cli.addCommand(Command(name='gain',
                               function=lambda: self.logger.info(
                                   f'\nK =\n{np.array2string(np.asarray(self.K), precision=3)}'),
                               description='Print the current feedback gain K'))

        cli.addCommand(Command(
            name='adaptive', function=self._cliSetAdaptive, allow_positionals=True,
            description='Enable/disable automatic re-tuning on model changes (on/off)',
            arguments=[CommandArgument(name='state', type=str, description='on/off')],
        ))
        cli.addCommand(Command(
            name='set_model', function=self.setModelParameter, allow_positionals=True,
            description='Set a plant model parameter (e.g. set_model m_b 2.0)',
            arguments=[
                CommandArgument(name='parameter', type=str, description='Model parameter name'),
                CommandArgument(name='value', type=float, description='New value'),
            ],
        ))
        cli.addCommand(Command(
            name='pole_scale', function=self.setPoleScale, allow_positionals=True,
            description='Scale all design poles (controller aggressiveness)',
            arguments=[CommandArgument(name='scale', type=float, description='Scaling factor')],
        ))
        cli.addCommand(Command(
            name='push', function=self.push, allow_positionals=True,
            description='Apply an instantaneous pitch disturbance [rad]',
            arguments=[CommandArgument(name='delta_theta', type=float, description='Pitch offset [rad]')],
        ))
        cli.addCommand(Command(
            name='disturbance', function=self.setDisturbance, allow_positionals=True,
            description='Apply a constant disturbance torque [Nm]',
            arguments=[CommandArgument(name='torque', type=float, description='Torque [Nm]')],
        ))
        return cli


# === SIMULATION ENVIRONMENT ===========================================================================================
class AdaptiveStateFeedbackSimulation:
    babylon_visualization: BabylonVisualization
    robot: AdaptiveBILBO

    cli: CLI
    gui: GUI

    # === INIT =========================================================================================================
    def __init__(self):
        self.logger = Logger('AdaptiveStateFeedbackSim', 'DEBUG')

        # --- The (single, always-present) simulated robot --------------------
        self.robot = AdaptiveBILBO(ROBOT_ID)

        # --- CLI --------------------------------------------------------------
        root = CommandSet('adaptive_sf', description='Adaptive state feedback simulation')
        root.addChild(self.robot.cli)
        self.cli = CLI(id='adaptive_sf', root=root, allow_set_change=True)

        # --- GUI --------------------------------------------------------------
        self.gui = GUI(id='adaptive_sf', host='localhost', run_js=True)
        self.gui.cli_terminal.setCLI(self.cli)

        # --- 3D visualization -------------------------------------------------
        self.babylon_visualization = BabylonVisualization(
            id='babylon', babylon_config={'title': 'Adaptive State Feedback'})

        # --- Real-time simulation environment ---------------------------------
        self.env = BaseEnvironment(Ts=TS, run_mode='rt')
        self.env.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self._simulationOutputStep)

        # Widget handles populated in _buildGUI()
        self.widgets: dict = {}
        self._status_cache: dict = {}

        addLogRedirection(self._logRedirection, minimum_level='DEBUG')
        register_exit_callback(self.close)

    # === LIFECYCLE ====================================================================================================
    def init(self):
        self._buildGUI()
        self._buildBabylon()
        self.widgets['babylon'].set_babylon(self.babylon_visualization)
        self.babylon_visualization.init()

        # The robot is always present — add it to the environment and the scene.
        self.env.addObject(self.robot)

        self.env.init()
        self.env.initialize()

        self._updateGainDisplay()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.gui.start()
        self.babylon_visualization.start()
        self.env.start()
        self.logger.info('Adaptive state feedback simulation started')

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.logger.info('Adaptive state feedback simulation stopped')
        time.sleep(1)

    # === GUI ==========================================================================================================
    def _buildGUI(self):
        category = Category('adaptive_sf', name='Adaptive SF', icon='K', max_pages=1)
        # A taller-than-default grid (25 rows) so the 3D view, plots and the
        # tuning controls all fit onto a single page.
        page = Page('main', name='Adaptive State Feedback', grid_size=(25, 50))
        category.addPage(page)
        self.gui.addCategory(category)
        self.page = page

        # --- 3D view ----------------------------------------------------------
        babylon_widget = BabylonWidget(widget_id='babylon_widget')
        page.addWidget(babylon_widget, row=1, column=1, width=25, height=15)
        self.widgets['babylon'] = babylon_widget

        # --- Pitch plot -------------------------------------------------------
        pitch_plot = RT_Plot_Widget(plot_config={
            'title': 'Pitch angle', 'show_title': True, 'legend_label_type': 'point'})
        y_pitch = pitch_plot.plot.add_y_axis('pitch', {
            'label': 'theta [deg]', 'min': -30, 'max': 30, 'color': [1, 1, 1],
            'grid_color': [0.5, 0.5, 0.5, 0.4], 'precision': 1,
            'highlight_zero': True, 'side': 'left'})
        ts_theta = TimeSeries(id='theta', y_axis=y_pitch, name='theta', unit='deg',
                              color=[1, 0.3, 0.3], fill=False, tension=0.0, precision=1, width=2)
        ts_theta_dot = TimeSeries(id='theta_dot', y_axis=y_pitch, name='theta_dot', unit='deg/s',
                                  color=[0.3, 0.6, 1], fill=False, tension=0.0, precision=1, width=2)
        ts_theta.set_value(0.0)
        ts_theta_dot.set_value(0.0)
        pitch_plot.plot.add_timeseries(ts_theta)
        pitch_plot.plot.add_timeseries(ts_theta_dot)
        page.addWidget(pitch_plot, row=1, column=27, width=24, height=7)
        self.widgets['ts_theta'] = ts_theta
        self.widgets['ts_theta_dot'] = ts_theta_dot

        # --- Motor torque plot ------------------------------------------------
        torque_plot = RT_Plot_Widget(plot_config={
            'title': 'Control effort', 'show_title': True, 'legend_label_type': 'point'})
        y_torque = torque_plot.plot.add_y_axis('torque', {
            'label': 'M [Nm]', 'min': -1.0, 'max': 1.0, 'color': [1, 1, 1],
            'grid_color': [0.5, 0.5, 0.5, 0.4], 'precision': 3,
            'highlight_zero': True, 'side': 'left'})
        ts_ml = TimeSeries(id='M_L', y_axis=y_torque, name='M_L', unit='Nm',
                           color=[0.3, 0.9, 0.4], fill=False, tension=0.0, precision=3, width=2)
        ts_mr = TimeSeries(id='M_R', y_axis=y_torque, name='M_R', unit='Nm',
                           color=[0.9, 0.7, 0.2], fill=False, tension=0.0, precision=3, width=2)
        ts_ml.set_value(0.0)
        ts_mr.set_value(0.0)
        torque_plot.plot.add_timeseries(ts_ml)
        torque_plot.plot.add_timeseries(ts_mr)
        page.addWidget(torque_plot, row=8, column=27, width=24, height=7)
        self.widgets['ts_ml'] = ts_ml
        self.widgets['ts_mr'] = ts_mr

        # --- Section headers --------------------------------------------------
        page.addWidget(TextWidget(widget_id='hdr_model', text='PLANT MODEL',
                                  font_size=13, font_weight='bold', horizontal_alignment='left'),
                       row=16, column=1, width=25, height=1)
        page.addWidget(TextWidget(widget_id='hdr_ctrl', text='CONTROLLER',
                                  font_size=13, font_weight='bold', horizontal_alignment='left'),
                       row=16, column=27, width=24, height=1)

        # --- Plant model sliders (live-editable mass / COG / inertia) --------
        slider_positions = [(17, 1), (17, 14), (20, 1), (20, 14)]
        self.widgets['model_sliders'] = {}
        for (param, (label, vmin, vmax, step)), (row, col) in zip(MODEL_PARAMETERS.items(), slider_positions):
            slider = SliderWidget(
                widget_id=f'slider_{param}', min_value=vmin, max_value=vmax,
                increment=step, value=getattr(self.robot.model, param),
                color=[0.3, 0.6, 0.9], direction='horizontal',
                continuousUpdates=True, title=label)
            slider.callbacks.value_changed.register(
                lambda value, p=param: self.robot.setModelParameter(p, value))
            page.addWidget(slider, row=row, column=col, width=12, height=3)
            self.widgets['model_sliders'][param] = slider

        # --- Adaptive checkbox -----------------------------------------------
        adaptive_checkbox = CheckboxWidget(
            widget_id='adaptive', title='Adaptive (auto re-tune K on model change):',
            title_position='left', value=self.robot.adaptive)
        adaptive_checkbox.callbacks.changed.register(
            lambda value, *a, **kw: self.robot.setAdaptive(value))
        page.addWidget(adaptive_checkbox, row=23, column=1, width=25, height=1)

        # --- Controller: pole scale slider + retune --------------------------
        pole_slider = SliderWidget(
            widget_id='slider_pole_scale', min_value=0.3, max_value=3.0,
            increment=0.1, value=self.robot.pole_scale, color=[0.8, 0.5, 0.2],
            direction='horizontal', continuousUpdates=True, title='Pole scale (aggressiveness)')
        pole_slider.callbacks.value_changed.register(
            lambda value, *a, **kw: self._onPoleScale(value))
        page.addWidget(pole_slider, row=17, column=27, width=24, height=3)

        btn_retune = Button(widget_id='btn_retune', text='Retune K', color=[0.2, 0.45, 0.3])
        btn_retune.callbacks.click.register(lambda *a, **kw: self._onRetune())
        page.addWidget(btn_retune, row=20, column=27, width=11, height=2)

        # --- K gain display ---------------------------------------------------
        gain_display = TextWidget(
            widget_id='gain_display', text='K = ...', font_size=11,
            font_family='monospace', horizontal_alignment='left', vertical_alignment='top',
            text_color=[0.7, 0.9, 0.7])
        page.addWidget(gain_display, row=20, column=39, width=12, height=6)
        self.widgets['gain_display'] = gain_display

        # --- Status widget ----------------------------------------------------
        status = StatusWidget(widget_id='status', elements={
            'mode': StatusWidgetElement(label='Controller', color=[0.4, 0.4, 0.4], status='—'),
            'tuning': StatusWidgetElement(label='Tuning', color=[0.4, 0.4, 0.4], status='—'),
            'balance': StatusWidgetElement(label='Balance', color=[0.4, 0.4, 0.4], status='—'),
        })
        page.addWidget(status, row=22, column=27, width=11, height=4)
        self.widgets['status'] = status

        # --- Action buttons --------------------------------------------------
        btn_enable = Button(widget_id='btn_enable', text='Enable', color=[0.2, 0.45, 0.3])
        btn_enable.callbacks.click.register(lambda *a, **kw: self.robot.enableController())
        page.addWidget(btn_enable, row=24, column=1, width=6, height=2)

        btn_disable = Button(widget_id='btn_disable', text='Disable', color=[0.45, 0.25, 0.25])
        btn_disable.callbacks.click.register(lambda *a, **kw: self.robot.disableController())
        page.addWidget(btn_disable, row=24, column=8, width=6, height=2)

        btn_reset = Button(widget_id='btn_reset', text='Reset', color=[0.3, 0.35, 0.5])
        btn_reset.callbacks.click.register(lambda *a, **kw: self.robot.reset())
        page.addWidget(btn_reset, row=24, column=15, width=6, height=2)

        btn_push = Button(widget_id='btn_push', text='Push +0.15', color=[0.5, 0.4, 0.2])
        btn_push.callbacks.click.register(lambda *a, **kw: self.robot.push(0.15))
        page.addWidget(btn_push, row=24, column=22, width=5, height=2)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildBabylon(self):
        floor = SimpleFloor('floor', size_x=[-10, 10], size_y=[-10, 10], texture='floor_bright.png')
        self.babylon_visualization.addObject(floor)

        robot_babylon = BabylonBilbo(object_id=ROBOT_ID, color=[0.7, 0, 0], text='SF')
        self.babylon_visualization.addObject(robot_babylon)
        self.widgets['robot_babylon'] = robot_babylon

    # === CALLBACKS ====================================================================================================
    def _onPoleScale(self, value):
        self.robot.setPoleScale(value)
        self._updateGainDisplay()

    # ------------------------------------------------------------------------------------------------------------------
    def _onRetune(self):
        self.robot.recomputeController()
        self._updateGainDisplay()

    # ------------------------------------------------------------------------------------------------------------------
    def _updateGainDisplay(self):
        k = np.asarray(self.robot.K)
        lines = ['K (feedback gain):']
        for row in k:
            lines.append('  ' + '  '.join(f'{v:+7.3f}' for v in row))
        self.widgets['gain_display'].text = '\n'.join(lines)

    # ------------------------------------------------------------------------------------------------------------------
    def _simulationOutputStep(self):
        """Runs every simulation step (real-time) — pushes the robot state into
        the 3D scene, the plots and the status widget."""
        try:
            state = self.robot.state

            # 3D scene
            self.widgets['robot_babylon'].set_state(
                x=state.x, y=state.y, theta=state.theta, psi=state.psi)

            # Plots
            self.widgets['ts_theta'].set_value(np.rad2deg(state.theta))
            self.widgets['ts_theta_dot'].set_value(np.rad2deg(state.theta_dot))
            self.widgets['ts_ml'].set_value(self.robot.last_input.M_L)
            self.widgets['ts_mr'].set_value(self.robot.last_input.M_R)

            self._updateStatus()
        except Exception as e:
            self.logger.error(f'Error in simulation output step: {e}')

    # ------------------------------------------------------------------------------------------------------------------
    def _updateStatus(self):
        """Recompute the status widget contents; only push an update when
        something actually changed (the loop runs at 100 Hz)."""
        if self.robot.mode == BILBO_Control_Mode.BALANCING:
            mode = ('Balancing', [0.2, 0.6, 0.3])
        else:
            mode = ('Off', [0.5, 0.5, 0.5])

        if self.robot.adaptive:
            tuning = ('Adaptive', [0.2, 0.55, 0.7])
        elif self.robot.controllerMismatch():
            tuning = ('Mismatch — retune!', [0.8, 0.45, 0.1])
        else:
            tuning = ('Matched', [0.2, 0.6, 0.3])

        if self.robot.isFallen():
            balance = ('Fallen', [0.8, 0.2, 0.2])
        else:
            balance = ('Upright', [0.2, 0.6, 0.3])

        new_state = {'mode': mode, 'tuning': tuning, 'balance': balance}
        if new_state == self._status_cache:
            return
        self._status_cache = new_state

        status = self.widgets['status']
        for key, (text, color) in new_state.items():
            status.elements[key].status = text
            status.elements[key].color = color
        status.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        color = [c / 255 for c in LOGGING_COLORS[level]]
        self.gui.print(f'[{logger.name}] {log}', color=color)


# === MAIN =============================================================================================================
def main():
    simulation = AdaptiveStateFeedbackSimulation()
    simulation.init()
    simulation.start()

    while True:
        time.sleep(10)


if __name__ == '__main__':
    main()
