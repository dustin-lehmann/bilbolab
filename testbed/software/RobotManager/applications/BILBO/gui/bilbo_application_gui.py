import dataclasses
import time
from typing import Dict, Optional, Callable

import numpy as np
from qmt import wrapToPi

# === CUSTOM MODULES ===================================================================================================
from applications.BILBO.gui.applications.dilc_app import DILC_App
from applications.BILBO.gui.applications.input_viewer import InputViewerApplication
from applications.BILBO.testbed_manager import BILBO_TestbedManager, BILBO_TestbedAgent
from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.colors import get_color_from_palette
from core.utils.lipo import lipo_soc
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from extensions.babylon.src.babylon import BabylonVisualization
from extensions.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.babylon.src.lib.objects.box.box import WallFancy
from extensions.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.cli.cli import CLI
from extensions.gui.src.app import App, Folder
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.objects import Widget_Group, ContextMenuItem, ContextMenuGroup
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.buttons import MultiStateButton, Button
from extensions.gui.src.lib.objects.python.indicators import BatteryIndicatorWidget, ConnectionIndicator, \
    InternetIndicator, JoystickIndicator, ProgressIndicator
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget
from extensions.gui.src.lib.objects.python.popup import YesNoPopup
from extensions.gui.src.lib.objects.python.text import TextWidget, StatusWidget, StatusWidgetElement
from extensions.gui.src.lib.plot.realtime.rt_plot import ServerMode, UpdateMode, TimeSeries, RT_Plot_Widget
from extensions.joystick.joystick_manager import Joystick
from robots.bilbo.manager.bilbo_joystick_control import BILBO_JoystickControl
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_data import BILBO_Sample
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from robots.bilbo.robot.experiment.bilbo_experiment import BILBO_ExperimentHandler_Status
from robots.bilbo.robot.experiment.experiment_definitions import BILBO_InputTrajectory
# from robots.bilbo.robot.experiment.experiments import DILC_Experiment

# === GLOBAL VARIABLES =================================================================================================
js_control: Optional[BILBO_JoystickControl] = None


# ======================================================================================================================
class BILBO_Application_GUI_Robot_Category:
    robot: BILBO
    category: Category
    pages: Dict[str, Page]
    gui: GUI

    # === INIT =========================================================================================================
    def __init__(self, robot: BILBO, gui: GUI):
        self.robot = robot
        self.gui = gui

        self.pages: Dict[str, Page] = {}
        self.category = Category(id=robot.id, icon='🤖')
        self._buildPages()

        self.robot.core.events.stream.on(self._streamCallback)
        self.logger = Logger(f"Category {self.robot.id}")

    # === METHODS ======================================================================================================

    # === PRIVATE HELPERS ==============================================================================================
    @staticmethod
    def _palette(i: int) -> list[float]:
        """Convenience access to a consistent pastel palette."""
        return get_color_from_palette('pastel', 5, i)

    @staticmethod
    def _classify_connection_strength(signal_strength: float) -> str:
        """Map a numeric signal strength (0..100) to low/medium/high."""
        if signal_strength > 85:
            return 'high'
        if signal_strength > 30:
            return 'medium'
        return 'low'

    @staticmethod
    def _create_toggle_button(
            parent_group: Widget_Group,
            *,
            widget_id: str,
            title: str,
            grid_row: int,
            grid_column: int,
            states: tuple[str, str] = ('OFF', 'ON'),
            colors: tuple[list[float], list[float]] = ([0.4, 0, 0], [0, 0.4, 0]),
            on_click: Optional[Callable[[str], None]] = None,
            **kwargs
    ) -> MultiStateButton:
        """
        Create a 2-state toggle button and (optionally) wire a simple on_click handler
        that gets the chosen state ('OFF'|'ON' or custom states).

        NOTE: The click callback from MultiStateButton may pass (state, index, ...)
        OR just (index, ...). This handler handles both.
        """
        btn = MultiStateButton(
            id=widget_id,
            states=list(states),
            color=[list(colors[0]), list(colors[1])],
            title=title,
            **kwargs,
        )
        parent_group.addWidget(btn, row=grid_row, column=grid_column, width=2, height=2)

        if on_click is not None:
            def _handler(*cb_args, **cb_kwargs):
                # Try to find the index argument in a resilient way
                idx = cb_kwargs.get('index', None)
                if idx is None:
                    if len(cb_args) >= 2:
                        # (state, index, ...)
                        idx = cb_args[1]
                    elif len(cb_args) >= 1:
                        # (index, ...)
                        idx = cb_args[0]
                    else:
                        # Fallback: use current state position (best-effort)
                        try:
                            idx = btn.states.index(btn.state)
                        except Exception:
                            idx = 0
                # Convert to int in case we got a string/np scalar
                idx = int(idx)
                desired_state = btn.getStateByIndex(idx + 1)  # API is 1-based
                on_click(desired_state)

            btn.callbacks.click.register(_handler)

        return btn

    def _add_plot(
            self,
            page: Page,
            *,
            widget_id: str,
            title: str,
            color_index: int,
            timeseries_id: str,
            series_name: str,
            unit: str,
            vmin: float,
            vmax: float,
            grid_column: int,
            grid_width: int = 9,
            grid_height: int = 9,
    ):
        """Create a plot widget with a dedicated Y-axis + a single timeseries, add to page, and return both."""
        # New widget class + API: Y-axis is separate from the timeseries
        plot = RT_Plot_Widget(
            widget_id=widget_id,
            plot_config={
                "title": title,
                "show_title": True,
                "legend_label_type": "point",
            },
            server_mode=ServerMode.EXTERNAL,
            update_mode=UpdateMode.CONTINUOUS,
        )
        page.addWidget(plot, column=grid_column, width=grid_width, height=grid_height)

        # Palette helper -> ensure RGBA
        base_col = list(self._palette(color_index))
        if len(base_col) == 3:
            rgba = base_col + [1.0]
        else:
            rgba = base_col[:4]

        # Add a dedicated Y axis for this series
        y_axis_id = f"{timeseries_id}_y"
        y_axis = plot.plot.add_y_axis(
            y_axis_id,
            {
                "label": f"{series_name} [{unit}]" if unit else series_name,
                "min": vmin,
                "max": vmax,
                "color": rgba,
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 2,
                "highlight_zero": True,
                "side": "left",
            },
        )

        # Add the timeseries bound to that Y axis
        ts = TimeSeries(
            id=timeseries_id,
            y_axis=y_axis,  # can pass the object or its id
            name=series_name,
            unit=unit,
            color=rgba,
            fill_color=rgba[:-1] + [0.15] if len(rgba) == 4 else base_col + [0.15],
            fill=False,
            tension=0.0,
            precision=2,
            width=2,
        )
        ts.set_value(0.0)
        plot.plot.add_timeseries(ts)

        return plot, ts

    @staticmethod
    def _add_digital_number(
            parent_group: Widget_Group,
            *,
            widget_id: str,
            row: int,
            title: str,
            min_value: float,
            max_value: float,
            increment: float,
            **kwargs
    ) -> DigitalNumberWidget:
        dn = DigitalNumberWidget(
            widget_id=widget_id,
            min_value=min_value,
            max_value=max_value,
            value=0,
            increment=increment,
            title=title,
            title_position='left',
            color=[0.3, 0.3, 0.3],
            warn_on_out_of_bounds=False,
            **kwargs,
        )
        parent_group.addWidget(dn, row=row, column=1, width=10, height=1)
        return dn

    # === PRIVATE METHODS ==============================================================================================
    def _buildPages(self):
        page_overview = Page(id='overview', name='Overview')
        self.category.addPage(page_overview)
        self.pages['overview'] = page_overview

        self._buildOverviewPage()

        page_control = Page(id='control', name='Control', icon='🎛️')
        self.category.addPage(page_control)
        self.pages['control'] = page_control

        page_experiment = Page(id='experiment', name='Experiment', icon='🧪')
        self.category.addPage(page_experiment)
        self.pages['experiment'] = page_experiment

        page_data = Page(id='data', name='Data', icon='📈')
        self.category.addPage(page_data)
        self.pages['data'] = page_data

    # ------------------------------------------------------------------------------------------------------------------
    def _buildOverviewPage(self):
        time.sleep(0.01)
        overview_page = self.pages['overview']

        # --- GENERAL GROUP ---
        self.general_group = Widget_Group(group_id='general_group', title='General', rows=5, columns=11)
        overview_page.addWidget(self.general_group, row=1, column=1, width=11, height=6)
        self._createGeneralGroup()

        # --- CONTROL GROUP ---
        self.control_group = Widget_Group(group_id='control_group', title='Control', rows=11, columns=11,
                                          show_title=True)
        overview_page.addWidget(self.control_group, row=7, column=1, width=11, height=12)

        # --- EXPERIMENT GROUP ---
        self.experiment_group = Widget_Group(group_id='experiment_group', title='Experiment', rows=17, columns=11,
                                             show_title=True)
        overview_page.addWidget(self.experiment_group, row=1, column=12, width=11, height=18)
        self._createExperimentGroup()

        # --- DATA GROUP ---
        self.data_group = Widget_Group(group_id='data_group', title='Data', rows=17, columns=10, show_title=True)
        overview_page.addWidget(self.data_group, row=1, column=23, width=10, height=18)
        self._createDataGroup()

        # --- MODE BUTTON ---
        mode_button = self._create_toggle_button(
            self.control_group,
            widget_id='mode_button',
            title='Mode',
            grid_row=5,
            grid_column=1,
            states=('OFF', 'BALANCING'),
            colors=([0.4, 0, 0], [0, 0.4, 0]),
            on_click=lambda desired: self.robot.control.setControlMode(
                BILBO_Control_Mode.OFF if desired == 'OFF' else BILBO_Control_Mode.BALANCING
            ),
            tooltip='Enable/disable control mode',
        )

        mode_mapping = {
            BILBO_Control_Mode.OFF: 'OFF',
            BILBO_Control_Mode.BALANCING: 'BALANCING',
            BILBO_Control_Mode.POSITION: 'BALANCING',
        }

        # Initial state
        if self.robot.control.mode is not None:
            mode_button.state = mode_mapping[self.robot.control.mode]

        # Keep the button in sync with robot mode changes
        def robot_control_mode_change_callback(mode):
            mode_button.state = mode_mapping[mode]

        self.robot.control.events.mode_changed.on(robot_control_mode_change_callback)

        # --- TIC BUTTON ---
        self.tic_button = self._create_toggle_button(
            self.control_group,
            widget_id='tic_button',
            title='TIC',
            grid_row=5,
            grid_column=4,
            on_click=lambda desired: self.robot.control.enableTIC(desired == 'ON'),
            tooltip='Enable/disable Theta Integral Control',
        )

        # --- VIC BUTTON ---
        # Note: In the original code, VIC button is display-only and driven by config changes.
        # We keep that behavior (no click handler) to avoid altering semantics.
        self.vic_button = self._create_toggle_button(
            self.control_group,
            widget_id='vic_button',
            title='VIC',
            grid_row=5,
            grid_column=7,
            on_click=None,
            tooltip='Enable/disable Velocity Integral Control',
        )

        # Keep TIC/VIC buttons in sync with configuration changes
        def robot_control_config_change_callback(config):
            self.logger.important("Control config changed")
            tic_enabled = config['balancing_control']['tic']['enabled']
            self.tic_button.state = 'ON' if tic_enabled else 'OFF'

            vic_enabled = config['balancing_control']['vic']['enabled']
            self.vic_button.state = 'ON' if vic_enabled else 'OFF'

        # self.robot.control.events.configuration_changed.on(robot_control_config_change_callback)

        def on_tic_mode_change(mode):
            self.tic_button.state = 'ON' if mode else 'OFF'

        self.robot.control.events.tic_mode_changed.on(on_tic_mode_change)

        # --- PLOTS ---
        # Theta
        self.theta_plot, self.theta_timeseries = self._add_plot(
            overview_page,
            widget_id='theta_plot',
            title='Theta',
            color_index=0,
            timeseries_id='theta_ds',
            series_name='Theta',
            unit='deg',
            vmin=-100,
            vmax=100,
            grid_column=33,
        )

        # Theta Dot
        self.theta_dot_plot, self.theta_dot_timeseries = self._add_plot(
            overview_page,
            widget_id='theta_dot_plot',
            title='Theta Dot',
            color_index=1,
            timeseries_id='theta_dot_ds',
            series_name='Theta Dot',
            unit='deg/s',
            vmin=-800,
            vmax=800,
            grid_column=33,
        )

        # V
        self.v_plot, self.v_timeseries = self._add_plot(
            overview_page,
            widget_id='v_plot',
            title='V',
            color_index=2,
            timeseries_id='v_ds',
            series_name='V',
            unit='m/s',
            vmin=-2,
            vmax=2,
            grid_column=42,
        )

        # Psi Dot
        self.psi_dot_plot, self.psi_dot_timeseries = self._add_plot(
            overview_page,
            widget_id='psi_dot_plot',
            title='Psi Dot',
            color_index=3,
            timeseries_id='psi_dot_ds',
            series_name='Psi Dot',
            unit='deg/s',
            vmin=-360,
            vmax=360,
            grid_column=42,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _createGeneralGroup(self):

        self.general_status_widget = StatusWidget(
            widget_id='general_status_widget',
            title='Status',
            elements={
                'el1': StatusWidgetElement(label='Status',
                                           color=[0, 0.5, 0],
                                           status='ok',
                                           ),
                'el2': StatusWidgetElement(label='Controller',
                                           color=[0, 0.5, 0],
                                           status='running',
                                           ),
                'el3': StatusWidgetElement(label='Experiment',
                                           color=[0.5, 0.5, 0.5],
                                           status='idle',
                                           )

            }
        )
        self.general_group.addWidget(self.general_status_widget, row=1, column=1, width=11, height=3)

        # Battery
        self.battery_indicator = BatteryIndicatorWidget(
            widget_id='battery_indicator',
            label_position='center',
            show='voltage',
        )
        self.general_group.addWidget(self.battery_indicator, row=4, column=9, width=3, height=2)

        # Connection
        self.connection_strength_indicator = ConnectionIndicator(widget_id='connection_strength_indicator')
        self.general_group.addWidget(self.connection_strength_indicator, row=4, column=1, width=3, height=2)

        # Internet
        self.internet_indicator = InternetIndicator(widget_id='internet_indicator')
        self.general_group.addWidget(self.internet_indicator, row=4, column=4, width=2, height=2)

        # Joystick indicator + context menu
        self.joystick_indicator = JoystickIndicator(widget_id='joystick_indicator')
        self.joystick_indicator.setValue(False)
        self.general_group.addWidget(self.joystick_indicator, row=4, column=6, width=3, height=2)

        # Context menu group
        joystick_group = ContextMenuGroup(id='joystick_group', name='Joysticks')
        self.joystick_indicator.context_menu.addItem(joystick_group)

        # Guard: if joystick control is not provided, stop here
        if js_control is None:
            return

        self.joystick_contextmenu_items: Dict[str, dict] = {}

        def _register_item(joystick):
            joystick_id = str(joystick.id)
            item = ContextMenuItem(id=joystick_id, name=f"{joystick.name} (ID: {joystick_id})")
            joystick_group.addItem(item)

            # Clicking assigns the joystick to this robot
            item.callbacks.click.register(
                Callback(function=js_control.assignJoystick, inputs={'joystick': joystick, 'bilbo': self.robot})
            )

            self.joystick_contextmenu_items[joystick_id] = {
                'item': item,
                'joystick': joystick,
                'assignment': None,
            }

        # Initial population
        for joystick_id, joystick_data in js_control.getJoysticksWithAssignments().items():
            _register_item(joystick_data['joystick'])

        # Live updates
        def add_joystick_menu_item(joystick, *args, **kwargs):
            _register_item(joystick)

        def remove_joystick_menu_item(joystick, *args, **kwargs):
            jid = str(joystick.id)
            if jid in self.joystick_contextmenu_items:
                joystick_group.removeItem(self.joystick_contextmenu_items[jid]['item'])
                del self.joystick_contextmenu_items[jid]

        def new_assignment(joystick, robot: BILBO, *args, **kwargs):
            self.logger.info(f'New assignment: {joystick.id} -> {robot.id}')
            jid = str(joystick.id)
            if jid in self.joystick_contextmenu_items:
                item = self.joystick_contextmenu_items[jid]
                if robot == self.robot:
                    item['item'].name = f"{item['joystick'].name} (ID: {jid}) ✅"
                else:
                    item['item'].name = f"{item['joystick'].name} (ID: {jid}) (-> {robot.id})"

        def assignment_removed(joystick, robot: BILBO, *args, **kwargs):
            self.logger.info(f'Assignment removed: {joystick.id} -> {robot.id}')
            jid = str(joystick.id)
            if jid in self.joystick_contextmenu_items:
                item = self.joystick_contextmenu_items[jid]
                item['item'].name = f"{item['joystick'].name} (ID: {jid})"

        js_control.callbacks.new_joystick.register(add_joystick_menu_item)
        js_control.callbacks.joystick_disconnected.register(remove_joystick_menu_item)
        js_control.callbacks.new_assignment.register(new_assignment)
        js_control.callbacks.assigment_removed.register(assignment_removed)

        # Click callback on the joystick indicator
        def joystick_indicator_click_callback(*args, **kwargs):
            # Check if our robot has a joystick assigned
            if js_control is not None:
                joystick = js_control.robotIsAssigned(self.robot)
                if joystick is not None:
                    # If so, open the context menu
                    joystick.rumble(strength=1, duration=1000)

        self.joystick_indicator.callbacks.click.register(joystick_indicator_click_callback)

    # ------------------------------------------------------------------------------------------------------------------
    def _createDataGroup(self):
        text_widget = TextWidget(widget_id='text_widget', color=[0.3, 0.3, 0.3], font_weight='bold')
        text_widget.text = 'States'
        self.data_group.addWidget(text_widget, row=13, column=1, width=10, height=1)

        # Digital numbers
        self.theta_digital_number = self._add_digital_number(
            self.data_group,
            widget_id='theta_dnw',
            row=14,
            title='Theta',
            min_value=-99,
            max_value=99,
            increment=0.1,
            color_ranges=[
                {'min': -0.15, 'max': 0.15, 'color': [0, 0.8, 0]}
            ]
        )
        self.v_digital_number = self._add_digital_number(
            self.data_group,
            widget_id='v_dnw',
            row=15,
            title='V',
            min_value=-2,
            max_value=2,
            increment=0.1,
        )
        self.theta_dot_digital_number = self._add_digital_number(
            self.data_group,
            widget_id='theta_dot_dnw',
            row=16,
            title='Theta Dot',
            min_value=-999,
            max_value=999,
            increment=0.1,
        )
        self.psi_dot_digital_number = self._add_digital_number(
            self.data_group,
            widget_id='psi_dot_dnw',
            row=17,
            title='Psi Dot',
            min_value=-999,
            max_value=999,
            increment=0.1,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _createExperimentGroup(self):

        self.experiment_handler_status_widget = StatusWidget(
            widget_id='experiment_handler_status_widget',
            title='Experiment',
            elements={
                'status': StatusWidgetElement(label='Experiment:',
                                              color=[0, 0.5, 0],
                                              status='idle',
                                              ),
            }
        )

        self.experiment_group.addWidget(self.experiment_handler_status_widget, row=1, column=1, width=11, height=1)

        def setExperimentHandlerStatus(status: BILBO_ExperimentHandler_Status):
            match status:
                case BILBO_ExperimentHandler_Status.IDLE:
                    self.experiment_handler_status_widget.elements['status'].status = '---'
                    self.experiment_handler_status_widget.elements['status'].color = [0.3, 0.3, 0.3]
                case BILBO_ExperimentHandler_Status.EXPERIMENT_RUNNING:
                    self.experiment_handler_status_widget.elements[
                        'status'].status = f'{type(self.robot.experiment_handler.experiment).__name__}'
                    self.experiment_handler_status_widget.elements['status'].color = [0, 0.5, 0]

            self.experiment_handler_status_widget.updateConfig()

        setExperimentHandlerStatus(self.robot.experiment_handler.status)

        self.robot.experiment_handler.events.status_changed.on(setExperimentHandlerStatus)

        # Experiment Status
        self.experiment_status_widget = StatusWidget(
            widget_id='experiment_status_widget',
            title='Experiment Status',
            elements={
                'status': StatusWidgetElement(label='Status:',
                                              color=[0, 0.5, 0],
                                              status='idle',
                                              ),
            }
        )

        self.experiment_group.addWidget(self.experiment_status_widget, row=2, column=1, width=11, height=1)

        def set_experiment_status(*args, **kwargs):
            try:
                if self.robot.experiment_handler.experiment is None:
                    self.experiment_status_widget.elements['status'].status = '---'
                    self.experiment_status_widget.elements['status'].color = [0.3, 0.3, 0.3]
                else:
                    match self.robot.experiment_handler.experiment.status:
                        case BILBO_Experiment_Status.NONE:
                            self.experiment_status_widget.elements['status'].status = '---'
                            self.experiment_status_widget.elements['status'].color = [0.3, 0.3, 0.3]
                        case BILBO_Experiment_Status.RUNNING_TRAJECTORY:
                            self.experiment_status_widget.elements['status'].status = 'running'
                            self.experiment_status_widget.elements['status'].color = [0, 0.5, 0]
                        case BILBO_Experiment_Status.CALCULATING:
                            self.experiment_status_widget.elements['status'].status = 'calculating'
                            self.experiment_status_widget.elements['status'].color = [0.0, 0.0, 0.5]
                        case BILBO_Experiment_Status.WAITING_FOR_USER:
                            self.experiment_status_widget.elements['status'].status = 'waiting for user'
                            self.experiment_status_widget.elements['status'].color = [184 / 255, 107 / 255, 48 / 255]

                self.experiment_status_widget.updateConfig()
            except Exception as e:
                ...

        set_experiment_status()

        # self.robot.experiment_handler.events.experiment_status_changed.on(set_experiment_status)

        # Text Widget Showing current trajectory info
        self.trajectory_info_widget = TextWidget(widget_id='trajectory_info_widget',
                                                 title='Trajectory Info',
                                                 horizontal_alignment='left',
                                                 vertical_alignment='top')

        def setTrajectoryInfo(trajectory: BILBO_InputTrajectory | None):
            if trajectory is None:
                self.trajectory_info_widget.text = f"<strong>Trajectory:</strong> ---"
                self.trajectory_info_widget.updateConfig()
                return

            self.trajectory_info_widget.text = f"""<strong>Trajectory:</strong> {trajectory.name}
            <strong>Status:</strong> {'loaded'}
            <strong>Steps:</strong> {trajectory.length}
            <strong>Duration:</strong> {trajectory.time_vector[-1]} s"""
            self.trajectory_info_widget.updateConfig()

        setTrajectoryInfo(self.robot.experiment_handler.current_trajectory)

        # Event Listeners

        def trajectory_started(*args, **kwargs):
            setTrajectoryInfo(self.robot.experiment_handler.getCurrentTrajectory())
            self.resume_button.disable()
            self.abort_button.enable()

        def trajectory_finished(*args, **kwargs):
            setTrajectoryInfo(None)
            self.resume_button.disable()
            self.abort_button.disable()

        def trajectory_stopped(*args, **kwargs):
            setTrajectoryInfo(None)
            self.resume_button.disable()
            self.abort_button.disable()

        def trajectory_loaded(*args, **kwargs):
            setTrajectoryInfo(self.robot.experiment_handler.getLoadedTrajectory())
            self.resume_button.enable()
            self.abort_button.enable()

        self.robot.experiment_handler.events.ll_trajectory_started.on(trajectory_started)
        self.robot.experiment_handler.events.ll_trajectory_finished.on(trajectory_finished)
        self.robot.experiment_handler.events.ll_trajectory_aborted.on(trajectory_stopped)
        self.robot.experiment_handler.events.trajectory_loaded.on(trajectory_loaded)

        self.experiment_group.addWidget(self.trajectory_info_widget, row=8, column=1, width=11, height=3)

        # Loading Bar Indicator
        self.experiment_progress_bar_indicator = ProgressIndicator(widget_id='experiment_loading_bar_indicator',
                                                                   track_fill_color=[0.2, 0.5, 0.2],
                                                                   track_visible=False)
        self.experiment_progress_bar_indicator.value = 0.5

        self.experiment_group.addWidget(self.experiment_progress_bar_indicator, row=11, column=1, width=11, height=1)

        # Controls
        self.experiment_control_group = Widget_Group(
            group_id='experiment_control_group',
            title='Experiment Control',
            rows=1,
            columns=5,
            show_title=True,
        )
        self.experiment_group.addWidget(self.experiment_control_group, row=12, column=1, width=11, height=3)

        self.resume_button = Button(widget_id='resume_button', text='Resume', color=[0.0, 0.4, 0.0])
        self.resume_button.disable()
        self.resume_button.callbacks.click.register(self.robot.core.interface_events.resume.set, discard_inputs=True)

        self.experiment_control_group.addWidget(self.resume_button, row=1, column=1, width=1, height=1)

        self.abort_button = Button(widget_id='abort_button', text='Abort', color=[0.4, 0.0, 0.0])
        self.experiment_control_group.addWidget(self.abort_button, row=1, column=2, width=1, height=1)
        self.abort_button.disable()

        self.stop_button = Button(widget_id='stop_button', text='Stop Exp', color=[0.4, 0, 0])
        # self.stop_button.callbacks.click.register(self.robot.experiment_handler.stopExperiment, discard_inputs=True)
        self.experiment_control_group.addWidget(self.stop_button, row=1, column=5, width=1, height=1)

        self.experiment_apps_group = Widget_Group(
            group_id='experiment_apps_group',
            title='Apps',
            rows=1,
            columns=5,
            show_title=True,
        )
        self.experiment_group.addWidget(self.experiment_apps_group, row=15, column=1, width=11, height=3)

        dilc_button = Button(widget_id='dilc_button', text='DILC', color=[0.4, 0.4, 0.4])
        # dilc_button.callbacks.click.register(self.robot.experiments.startDILC)
        self.experiment_apps_group.addWidget(dilc_button, row=1, column=1, width=1, height=1)

        def dilc_button_click(*args, **kwargs):
            self.robot.experiment_handler.runExperiment(DILC_Experiment)
            self._openDILCApp()

        dilc_button.callbacks.click.register(dilc_button_click)

        iml_button = Button(widget_id='iml_button', text='IML', color=[0.4, 0.4, 0.4])
        self.experiment_apps_group.addWidget(iml_button, row=1, column=2, width=1, height=1)
        iml_button.disable()

        iitl_button = Button(widget_id='iitl_button', text='IITL', color=[0.4, 0.4, 0.4])
        self.experiment_apps_group.addWidget(iitl_button, row=1, column=3, width=1, height=1)
        iitl_button.disable()

        dilc_rls_button = Button(widget_id='dilc_rls_button', text='DILC RLS', color=[0.4, 0.4, 0.4])
        self.experiment_apps_group.addWidget(dilc_rls_button, row=1, column=4, width=1, height=1)
        dilc_rls_button.disable()

    # ------------------------------------------------------------------------------------------------------------------
    def _openDILCApp(self, *args, **kwargs):
        dilc_app = DILC_App(self.robot)
        dilc_app.open(gui=self.gui)

    # ------------------------------------------------------------------------------------------------------------------
    def _streamCallback(self, sample: BILBO_Sample, *args, **kwargs):
        # Digital numbers
        self.theta_digital_number.value = np.rad2deg(wrapToPi(sample.lowlevel.estimation.state.theta))
        self.v_digital_number.value = sample.lowlevel.estimation.state.v
        self.theta_dot_digital_number.value = np.rad2deg(sample.lowlevel.estimation.state.theta_dot)
        self.psi_dot_digital_number.value = np.rad2deg(sample.lowlevel.estimation.state.psi_dot)

        # Plots (new API uses set_value)
        self.theta_timeseries.set_value(sample.lowlevel.estimation.state.theta * 180.0 / 3.141592653589793)
        self.v_timeseries.set_value(sample.lowlevel.estimation.state.v)
        self.theta_dot_timeseries.set_value(sample.lowlevel.estimation.state.theta_dot * 180.0 / 3.141592653589793)
        self.psi_dot_timeseries.set_value(sample.lowlevel.estimation.state.psi_dot * 180.0 / 3.141592653589793)

        # Battery / indicators — throttle to every ~200 ticks
        if self.robot.core.tick % 200 == 0:
            voltage = sample.sensors.power.bat_voltage
            cells = self.robot.config.electronics.battery_cells
            self.battery_indicator.setValue(percentage=lipo_soc(voltage=voltage, cells=cells), voltage=voltage)

            # Connection
            signal_strength = sample.connection.strength
            self.connection_strength_indicator.setValue(self._classify_connection_strength(signal_strength))

            # Internet
            self.internet_indicator.setValue(sample.connection.internet)

            # Joystick assigned?
            if js_control is not None:
                self.joystick_indicator.setValue(js_control.robotIsAssigned(self.robot) is not None)
            else:
                self.joystick_indicator.setValue(False)

        # TIC (reserved for future logic if needed)


# ======================================================================================================================
class BILBO_Application_App_Robot_Folder:
    folder: Folder

    # === INIT =========================================================================================================
    def __init__(self, robot: BILBO, app: App):
        self.robot = robot
        self.app = app
        self.folder = Folder(folder_id=robot.core.id)

        self._buildFolder()

    # === METHODS ======================================================================================================
    def _buildFolder(self):
        # --- MODE BUTTON (same behavior as in GUI Category) ---
        self.mode_button = MultiStateButton(
            id='mode_button',
            states=['OFF', 'BALANCING'],
            color=[[0.4, 0, 0], [0, 0.4, 0]],
            title='Mode',
        )
        self.folder.addObject(self.mode_button, row=1, column=2, width=1, height=1)

        # Map robot control mode <-> button label
        _mode_mapping = {
            BILBO_Control_Mode.OFF: 'OFF',
            BILBO_Control_Mode.BALANCING: 'BALANCING',
        }

        # Initialize button state from current robot mode
        try:
            self.mode_button.state = _mode_mapping[self.robot.control.mode]
        except Exception:
            # Fallback if anything unexpected happens
            self.mode_button.state = 'OFF'

        # Click handler: set robot control mode based on desired state
        def _mode_click_handler(*cb_args, **cb_kwargs):
            # Be defensive about callback signature: could be (state, index, ...) or (index, ...)
            idx = cb_kwargs.get('index', None)
            if idx is None:
                if len(cb_args) >= 2:
                    idx = cb_args[1]
                elif len(cb_args) >= 1:
                    idx = cb_args[0]
                else:
                    # Fallback to current state index if not provided
                    try:
                        idx = self.mode_button.states.index(self.mode_button.state)
                    except Exception:
                        idx = 0
            idx = int(idx)
            desired = self.mode_button.getStateByIndex(idx + 1)  # API is 1-based
            self.robot.control.setControlMode(
                BILBO_Control_Mode.OFF if desired == 'OFF' else BILBO_Control_Mode.BALANCING
            )

        self.mode_button.callbacks.click.register(_mode_click_handler)

        # --- TIC BUTTON (same behavior as in GUI Category) ---
        self.tic_button = MultiStateButton(
            id='tic_button',
            states=['OFF', 'ON'],
            color=[[0.4, 0, 0], [0, 0.4, 0]],
            title='TIC',
        )
        self.folder.addObject(self.tic_button, row=1, column=3, width=1, height=1)

        # Click handler: toggle TIC on the controller
        def _tic_click_handler(*cb_args, **cb_kwargs):
            idx = cb_kwargs.get('index', None)
            if idx is None:
                if len(cb_args) >= 2:
                    idx = cb_args[1]
                elif len(cb_args) >= 1:
                    idx = cb_args[0]
                else:
                    try:
                        idx = self.tic_button.states.index(self.tic_button.state)
                    except Exception:
                        idx = 0
            idx = int(idx)
            desired = self.tic_button.getStateByIndex(idx + 1)
            self.robot.control.enableTIC(desired == 'ON')

        self.tic_button.callbacks.click.register(_tic_click_handler)

        def robot_control_config_change_callback(config):
            tic_enabled = config['balancing_control']['tic']['enabled']
            self.tic_button.state = 'ON' if tic_enabled else 'OFF'

        self.robot.control.callbacks.configuration_changed.register(robot_control_config_change_callback)

        _mode_mapping = {
            BILBO_Control_Mode.OFF: 'OFF',
            BILBO_Control_Mode.BALANCING: 'BALANCING',
        }

        def robot_control_mode_change_callback(mode):
            self.mode_button.state = _mode_mapping[mode]

        self.robot.control.callbacks.mode_changed.register(robot_control_mode_change_callback)

        # --- Interface Buttons ---
        self.start_button = Button(widget_id='start_button', text='Start', color=[0.0, 0.4, 0.0])
        self.start_button.callbacks.click.register(self.robot.core.interface_events.start.set, discard_inputs=True)
        self.folder.addObject(self.start_button, row=2, column=1, width=1, height=1)

        self.resume_button = Button(widget_id='resume_button', text='Resume', color=[75 / 255, 82 / 255, 56 / 255])
        self.resume_button.callbacks.click.register(self.robot.core.interface_events.resume.set, discard_inputs=True)
        self.folder.addObject(self.resume_button, row=2, column=2, width=1, height=1)

        self.revert_button = Button(widget_id='revert_button', text='Revert', color=[59 / 255, 20 / 255, 120 / 255])
        self.revert_button.callbacks.click.register(self.robot.core.interface_events.revert.set, discard_inputs=True)
        self.folder.addObject(self.revert_button, row=2, column=3, width=1, height=1)

        self.stop_button = Button(widget_id='stop_button', text='Stop', color=[0.4, 0, 0])
        self.stop_button.callbacks.click.register(self.robot.core.interface_events.stop.set, discard_inputs=True)
        self.folder.addObject(self.stop_button, row=2, column=4, width=1, height=1)

        # --- Joystick Button ---
        self.joystick_button = Button(widget_id='joystick_button', image='gamepad.png')
        self.folder.addObject(self.joystick_button, row=2, column=6, width=1, height=1)

        # Check if joystick is assigned
        if js_control.robotIsAssigned(self.robot):
            self.joystick_button.dim(False)
        else:
            self.joystick_button.dim(True)

        def joystick_button_callback(*args, **kwargs):
            if js_control.robotIsAssigned(self.robot):
                return
            joystick = js_control.getFirstJoystick()
            if joystick is None:
                return
            js_control.assignJoystick(joystick, self.robot)

        def joystick_button_long_callback(*args, **kwargs):
            if js_control.robotIsAssigned(self.robot):
                js_control.unassignJoystick(self.robot.interfaces.joystick)

        self.joystick_button.callbacks.click.register(joystick_button_callback)
        self.joystick_button.callbacks.longClick.register(joystick_button_long_callback)

        def new_js_assignment_callback(joystick: Joystick, robot: BILBO):
            if robot == self.robot:
                self.joystick_button.dim(False)

        def js_assignment_removed_callback(joystick: Joystick, robot: BILBO):
            if robot == self.robot:
                self.joystick_button.dim(True)

        js_control.callbacks.new_assignment.register(new_js_assignment_callback)
        js_control.callbacks.assigment_removed.register(js_assignment_removed_callback)


# ======================================================================================================================
class BILBO_GUI_TestbedPage:
    page: Page
    manager: BILBO_TestbedManager

    @dataclasses.dataclass
    class RobotContainer:
        robot: BILBO_TestbedAgent
        babylon: BabylonBilbo

    robots: dict[str, RobotContainer]

    def __init__(self, manager: BILBO_TestbedManager):
        self.manager = manager

        self.logger = Logger("Testbed Page")
        self.page = Page(id='testbed_page', name='Testbed')
        self.robots = {}

        self.babylon_visualization = BabylonVisualization(id='babylon', babylon_config={
            'title': 'BILBO Testbed'})
        self.babylon_visualization.start()
        self._buildPage()

        self.manager.events.new_robot.on(self._on_new_testbed_robot)
        self.manager.events.robot_disconnected.on(self._on_testbed_robot_disconnected)
        self.manager.events.new_tracker_sample.on(self._on_new_tracker_sample)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildPage(self):
        testbed_size = [3, 3]  # Size in meters
        self.babylon_widget = BabylonWidget(widget_id='babylon_widget')
        self.page.addWidget(self.babylon_widget, row=1, column=1, height=18, width=24)

        # Floor is kept larger than testbed for visual purposes
        floor = SimpleFloor('floor', size_y=50, size_x=50, texture='floor_bright.png')
        self.babylon_visualization.addObject(floor)

        # Wall length matches testbed size
        # Wall positions are offset by half the testbed size to create the boundary
        wall1 = WallFancy('wall1', length=testbed_size[0], texture='wood4.png', include_end_caps=True)
        wall1.setPosition(y=testbed_size[1] / 2)
        self.babylon_visualization.addObject(wall1)

        wall2 = WallFancy('wall2', length=testbed_size[0], texture='wood4.png', include_end_caps=True)
        self.babylon_visualization.addObject(wall2)
        wall2.setPosition(y=-testbed_size[1] / 2)

        wall3 = WallFancy('wall3', length=testbed_size[1], texture='wood4.png')
        wall3.setPosition(x=testbed_size[0] / 2)
        wall3.setAngle(np.pi / 2)
        self.babylon_visualization.addObject(wall3)

        wall4 = WallFancy('wall4', length=testbed_size[1], texture='wood4.png')
        wall4.setPosition(x=-testbed_size[0] / 2)
        wall4.setAngle(np.pi / 2)
        self.babylon_visualization.addObject(wall4)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_testbed_robot(self, robot: BILBO_TestbedAgent):
        if robot.id in self.robots:
            self.logger.warning(f'Testbed robot {robot.id} already exists. Skipping.')
            return

        container = self.RobotContainer(
            robot=robot,
            babylon=BabylonBilbo(object_id=robot.id,
                                 color=robot.robot.config.general.color,
                                 text=robot.robot.config.general.short_id)
        )

        self.robots[robot.id] = container
        self.babylon_visualization.addObject(container.babylon)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_testbed_robot_disconnected(self, robot: BILBO_TestbedAgent):
        if robot.id not in self.robots:
            self.logger.warning(f'Testbed robot {robot.id} not found. Skipping.')
            return

        self.babylon_visualization.removeObject(self.robots[robot.id].babylon)
        del self.robots[robot.id]

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_tracker_sample(self, *args, **kwargs):
        for robot in self.robots.values():
            robot.babylon.set_state(
                x=robot.robot.tracked_object.state.x,
                y=robot.robot.tracked_object.state.y,
                theta=robot.robot.tracked_object.state.theta,
                psi=robot.robot.tracked_object.state.psi,
            )


# ======================================================================================================================
@callback_definition
class BILBO_Application_GUI_Callbacks:
    emergency_stop: CallbackContainer


class BILBO_Application_GUI:
    gui: GUI
    app: App
    categories: dict
    robot_categories: dict[str, BILBO_Application_GUI_Robot_Category]
    robot_app_folders: dict[str, BILBO_Application_App_Robot_Folder]

    # === INIT =========================================================================================================
    def __init__(self, host,
                 testbed_manager: BILBO_TestbedManager,
                 cli: CLI = None,
                 joystick_control: BILBO_JoystickControl = None):
        self.callbacks = BILBO_Application_GUI_Callbacks()

        self.gui = GUI(
            id='bilbo_application',
            host=host,
            run_js=True
        )

        self.app = App(
            app_id='bilbo_application_app',
            host=host,
            run_js_app=False,
        )
        self.testbed_manager = testbed_manager
        self.gui.cli_terminal.setCLI(cli)
        self.joystick_control = joystick_control

        global js_control
        js_control = joystick_control

        # GUI Callbacks
        self.gui.callbacks.emergency_stop.register(self.callbacks.emergency_stop.call)

        self.categories = {}
        self.robot_categories = {}
        self.robot_app_folders = {}

        self._addCategoriesAndPages()

        self._addApplications()

        # self.gui.addApplication(self.example_app)

        self.logger = Logger('gui')

        # Reroute all logs to the CLI
        addLogRedirection(self._logRedirection, minimum_level='INFO')

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.gui.start()
        self.app.start()

    # ------------------------------------------------------------------------------------------------------------------
    def addRobot(self, robot: BILBO):
        self._addRobotCategory(robot.id, robot)
        self._addRobotFolder_App(robot.id, robot)

    # ------------------------------------------------------------------------------------------------------------------
    def removeRobot(self, robot: BILBO):
        self.logger.important(f'Removing robot {robot.id} from GUI')
        if robot.id in self.robot_categories:
            self._removeRobotCategory(robot.id)
            self._removeRobotFolder_App(robot.id)

    # === PRIVATE METHODS ==============================================================================================
    def _addCategoriesAndPages(self):
        # Application category
        category_application = Category(id='application', name='Application', icon='🎛️')
        self.gui.addCategory(category_application)
        self.categories['application'] = {'category': category_application}

        # Pages
        # page_overview = Page(id='overview', name='Overview')
        # category_application.addPage(page_overview)
        #
        # page_robots = Page(id='robots', name='Robots')
        # category_application.addPage(page_robots)

        self.testbed_page = BILBO_GUI_TestbedPage(self.testbed_manager)
        category_application.addPage(self.testbed_page.page)

        self.categories['application']['pages'] = {
            'testbed': self.testbed_page.page,
        }

        # Robots Category
        category_robots = Category(id='robots', name='Robots', icon='🤖', number_of_pages=1, max_pages=1)
        self.gui.addCategory(category_robots)
        self.categories['robots'] = {'category': category_robots}

        robots_overview = Page(id='overview', name='Overview')
        category_robots.addPage(robots_overview)
        self.categories['robots']['pages'] = {'overview': robots_overview}

    # ------------------------------------------------------------------------------------------------------------------
    def _addRobotCategory(self, robot_id, robot: BILBO):
        self.robot_categories[robot_id] = BILBO_Application_GUI_Robot_Category(robot, self.gui)
        self.categories['robots']['category'].addCategory(self.robot_categories[robot_id].category)

    # ------------------------------------------------------------------------------------------------------------------
    def _removeRobotCategory(self, robot_id):
        if robot_id in self.robot_categories:
            self.categories['robots']['category'].removeCategory(self.robot_categories[robot_id].category)
            del self.robot_categories[robot_id]

    # ------------------------------------------------------------------------------------------------------------------
    def _addRobotFolder_App(self, robot_id, robot: BILBO):
        self.robot_app_folders[robot_id] = BILBO_Application_App_Robot_Folder(robot, self.app)
        self.app.addFolder(self.robot_app_folders[robot_id].folder)

    # ------------------------------------------------------------------------------------------------------------------
    def _removeRobotFolder_App(self, robot_id):
        if robot_id in self.robot_app_folders:
            self.app.removeFolder(self.robot_app_folders[robot_id].folder)
            del self.robot_app_folders[robot_id]

    # ------------------------------------------------------------------------------------------------------------------
    def _addApplications(self):
        # BILBO Applications
        # 1. Input viewer
        input_viewer_button = Button(widget_id='input_viewer_button', text='Input Viewer')
        # self.gui.addApplicationButton(input_viewer_button)
        # input_viewer_button.callbacks.click.register(self._openInputViewer)

    # ------------------------------------------------------------------------------------------------------------------
    def _testPopupOpen(self, sender, *args, **kwargs):

        popup = YesNoPopup()
        self.gui.openPopup(popup, client=sender)

    # ------------------------------------------------------------------------------------------------------------------
    def _openInputViewer(self, sender, *args, **kwargs):

        input_viewer_app = InputViewerApplication()
        input_viewer_app.open(self.gui, sender)

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        print_text = f"[{logger.name}] {log}"
        color = LOGGING_COLORS[level]
        color = [c / 255 for c in color]
        self.gui.print(print_text, color=color)
        self.app.print(print_text, color=color)
