import base64
import copy
import dataclasses
import math
import os
import threading
import time
from typing import Dict

import yaml as yaml_module

import numpy as np

from core.utils.uuid_utils import generate_uuid
from core.utils.colors import get_palette
from core.utils.lipo import lipo_soc
from core.utils.callbacks import Callback
from core.utils.logging_utils import Logger
from core.utils.time import set_timeout
from extensions.gui.src.app import App, Folder, FolderPage
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.map.map import MapWidget
from extensions.gui.src.lib.map.map_objects import Agent, Point, Line, Rectangle, MapObject
from extensions.gui.src.lib.objects.objects import Widget_Group, ContextMenuItem, ContextMenuGroup
from extensions.gui.src.lib.objects.python.bilbo_mode import BilboModeWidget
from extensions.gui.src.lib.objects.python.buttons import MultiStateButton, Button
from extensions.gui.src.lib.objects.python.checkbox import CheckboxWidget
from extensions.gui.src.lib.objects.python.popup import Popup
from extensions.gui.src.lib.objects.python.experiment_designer import ExperimentDesignerWidget, ActionLibrary
from extensions.gui.src.lib.objects.python.indicators import (
    BatteryIndicatorWidget, ConnectionIndicator, InternetIndicator, JoystickIndicator,
)
from extensions.gui.src.lib.objects.python.joystick import JoystickWidget
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget
from extensions.gui.src.lib.objects.python.select import MultiSelectWidget
from extensions.gui.src.lib.objects.python.table import Table, TextColumn, TextInputColumn, TableGroup
from extensions.gui.src.lib.objects.python.text import TextWidget, StatusWidget, StatusWidgetElement, LineScrollWidget
from extensions.gui.src.lib.objects.python.text_input import InputWidget
from extensions.gui.src.lib.plot.realtime.rt_plot import TimeSeries, RT_Plot_Widget
from robots.bilbo.gui.applications.dilc_app import DILC_APP
from robots.bilbo.gui.applications.dilc_page import DILC_ExperimentPage
from robots.bilbo.gui.applications.limbobar_dilc_app import LimboBar_DILC_APP
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_data import BILBO_Sample
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_ControlConfig
from robots.bilbo.robot.bilbo_position_control import MoveToPointCommand, TurnToHeadingCommand, PathData
from robots.bilbo.robot.bilbo_utilities import CONTROL_MODE_COLORS
from core.utils.experiments.types import ExperimentStatus
from robots.bilbo.testbed.objects import BoxObstacle
from robots.bilbo.testbed.testbed_manager import TestbedManager


# ======================================================================================================================
class RobotUI:
    _built: bool = False

    plots: list[RT_Plot_Widget]
    overview_page_data: dict

    _additional_map_objects: list[MapObject] = []

    # === INIT =========================================================================================================
    def __init__(self, robot: BILBO, manager: TestbedManager, gui: GUI, app: App, application_settings,
                 joystick_control=None):
        self.robot = robot
        self.gui = gui
        self.app = app
        self.manager = manager
        self.application_settings = application_settings
        self.joystick_control = joystick_control

        self.pages: Dict[str, Page] = {}
        self.category = Category(id=robot.id, icon='🤖', bottom_group_size=[3, 3])
        self.gui.categories['robots'].addCategory(self.category)

        self._additional_map_objects: list[MapObject] = []
        self._obstacle_map_objects: dict[str, MapObject] = {}  # obstacle_id -> map object

        # Load robot image for folder buttons if available
        self._robot_image_uri = None
        assets_dir = os.path.join(os.path.dirname(__file__), 'assets', 'robots')
        image_path = os.path.join(assets_dir, f'{robot.id}.png')
        if os.path.isfile(image_path):
            with open(image_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode()
            self._robot_image_uri = f'data:image/png;base64,{img_b64}'

        folder_kwargs = {'image': self._robot_image_uri, 'image_opacity': 0.7, 'text_position': 'top'} if self._robot_image_uri else {}
        self.folder = Folder(folder_id=robot.id, **folder_kwargs)

        self.robot.core.events.stream.on(self.on_robot_stream)
        if self.manager.tracker is not None:
            self.manager.tracker.events.new_sample.on(self.on_new_tracker_sample, max_rate=20)
        self.logger = Logger(f"Category {self.robot.id}")

        # Register DILC experiment events (via experiment_handler, which owns the event)
        # Save listener handles so they can be stopped in close()
        self._event_listeners = [
            self.robot.experiment_handler.events.dilc_experiment_initialized.on(
                self.on_dilc_experiment_initialized, spawn_new_threads=True),
            self.robot.experiment_handler.events.limbobar_dilc_experiment_initialized.on(
                self.on_limbobar_dilc_experiment_initialized, spawn_new_threads=True),
            self.robot.experiment_handler.events.experiment_started.on(self._on_experiment_started),
            self.robot.experiment_handler.events.experiment_finished.on(lambda *a, **kw: self._on_experiment_finished(*a, status=ExperimentStatus.FINISHED, **kw)),
            self.robot.experiment_handler.events.experiment_error.on(lambda *a, **kw: self._on_experiment_finished(*a, status=ExperimentStatus.ERROR, **kw)),
            self.robot.experiment_handler.events.experiment_timeout.on(lambda *a, **kw: self._on_experiment_finished(*a, status=ExperimentStatus.TIMEOUT, **kw)),
            self.robot.experiment_handler.events.action_started.on(self._on_action_started),
            self.robot.experiment_handler.events.action_finished.on(self._on_action_finished),
        ]

        self.robot.device.callbacks.disconnected.register(self.close)
        # Handle Mode changes
        self.robot.core.events.control_mode_changed.on(self.on_control_mode_changed)
        self.robot.control.events.tic_mode_changed.on(self.on_tic_mode_changed)
        self.robot.control.events.vic_mode_changed.on(self.on_vic_mode_changed)
        self.robot.control.events.psi_mode_changed.on(self.on_psi_mode_changed)

        # Build
        self.plots = []
        self.overview_page_data = {}

        self.build()
        self.build_folder()

    # === METHODS ======================================================================================================
    def build(self):
        time.sleep(0.5)
        self.page_overview = Page(id='overview', name='🤖 Overview', icon='🤖')
        self.build_overview_page(self.page_overview)
        self.category.addPage(self.page_overview)
        page_control = Page(id='control', name='🎛️ Control', icon='🎛️')
        self.build_control_page(page_control)
        self.category.addPage(page_control)
        page_debug = Page(id='debug', name='🔧 Debug', icon='🔧')
        self.build_debug_page(page_debug)
        self.category.addPage(page_debug)

        page_exp = Page(id='experiment', name='🚀 Experiment', icon='🚀')
        self.build_experiment_page(page_exp)
        self.category.addPage(page_exp)

        # Mode widget in category bottom group (visible on all pages)
        self.bottom_mode_widget = BilboModeWidget(widget_id='bottom_mode',
                                                   current_mode=self.robot.control.mode.name)

        def update_bottom_mode(mode: BILBO_Control_Mode, *args, **kwargs):
            self.bottom_mode_widget.current_mode = mode.name

        def bottom_mode_clicked(mode_id, *args, **kwargs):
            match mode_id:
                case 'OFF':
                    self.robot.control.setControlMode(BILBO_Control_Mode.OFF)
                case 'DIRECT':
                    self.robot.control.setControlMode(BILBO_Control_Mode.DIRECT)
                case 'BALANCING':
                    self.robot.control.setControlMode(BILBO_Control_Mode.BALANCING)
                case 'VELOCITY':
                    self.robot.control.setControlMode(BILBO_Control_Mode.VELOCITY)
                case 'POSITION':
                    self.robot.control.setControlMode(BILBO_Control_Mode.POSITION)

        self.bottom_mode_widget.callbacks.mode_clicked.register(bottom_mode_clicked)
        self.robot.control.events.mode_changed.on(update_bottom_mode)
        self.category.bottom_group.addWidget(self.bottom_mode_widget, row=3, column=1, width=3, height=1)

        self._built = True

        self.gui.function(
            function_name='setPage',
            args=[self.page_overview.uid]
        )

    # ------------------------------------------------------------------------------------------------------------------
    def build_overview_page(self, page):
        # --- GENERAL GROUP --------------------------------------------------------------------------------------------
        general_group = Widget_Group(group_id='general', title='General', rows=7, columns=11)
        page.addWidget(general_group, row=1, column=1, width=11, height=8)

        robot_id_label = TextWidget(
            widget_id='robot_id_label',
            text=self.robot.id,
            font_size=14,
            font_weight='bold',
            horizontal_alignment='center',
        )
        general_group.addWidget(robot_id_label, row=1, column=1, width=11, height=1)

        self.general_status_widget = StatusWidget(
            widget_id='general_status_widget',
            title='Status',
            elements={
                'status': StatusWidgetElement(label='Status',
                                              color=[0, 0.5, 0],
                                              status='ok',
                                              ),
                'mode': StatusWidgetElement(label='Control Mode',
                                            color=CONTROL_MODE_COLORS[self.robot.control.mode],
                                            status=self.robot.control.mode.name,
                                            ),
            }
        )
        general_group.addWidget(self.general_status_widget, row=2, column=1, width=11, height=2)

        # Battery
        self.battery_indicator = BatteryIndicatorWidget(
            widget_id='battery_indicator',
            label_position='center',
            show='voltage',
        )
        general_group.addWidget(self.battery_indicator, row=4, column=9, width=3, height=2)

        # Connection
        self.connection_strength_indicator = ConnectionIndicator(widget_id='connection_strength_indicator')
        general_group.addWidget(self.connection_strength_indicator, row=4, column=1, width=3, height=2)
        #
        # Internet
        self.internet_indicator = InternetIndicator(widget_id='internet_indicator')
        general_group.addWidget(self.internet_indicator, row=4, column=4, width=2, height=2)
        #
        # Joystick indicator + context menu
        self.joystick_indicator = JoystickIndicator(widget_id='joystick_indicator')
        self.joystick_indicator.setValue(False)
        general_group.addWidget(self.joystick_indicator, row=4, column=6, width=3, height=2)

        self.pi_status_widget = StatusWidget(
            widget_id='pi_status_widget',
            title='Pi Status',
            elements={
                'temp': StatusWidgetElement(label='Temp', color=[0.5, 0.5, 0.5], status="--"),
                'throttle': StatusWidgetElement(label='Throttled', color=[0.5, 0.5, 0.5], status="--"),
            }
        )

        general_group.addWidget(self.pi_status_widget, width=11, height=2)

        # Joystick context menu
        js_control = self.joystick_control

        joystick_group = ContextMenuGroup(id='joystick_group', name='Joysticks')
        self.joystick_indicator.context_menu.addItem(joystick_group)

        if js_control is not None:
            self.joystick_contextmenu_items: Dict[str, dict] = {}
            no_joystick_item = ContextMenuItem(id='no_joysticks', name='No joysticks connected')
            self._joystick_placeholder_visible = False

            def _show_placeholder():
                if not self._joystick_placeholder_visible:
                    joystick_group.addItem(no_joystick_item)
                    self._joystick_placeholder_visible = True

            def _hide_placeholder():
                if self._joystick_placeholder_visible:
                    joystick_group.removeItem(no_joystick_item)
                    self._joystick_placeholder_visible = False

            def _register_item(joystick):
                joystick_id = str(joystick.id)
                _hide_placeholder()
                item = ContextMenuItem(id=joystick_id, name=f"{joystick.name} (ID: {joystick_id})")
                joystick_group.addItem(item)

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

            # Show placeholder if no joysticks were found
            if len(self.joystick_contextmenu_items) == 0:
                _show_placeholder()

            # Live updates
            def add_joystick_menu_item(joystick, *args, **kwargs):
                _register_item(joystick)

            def remove_joystick_menu_item(joystick, *args, **kwargs):
                jid = str(joystick.id)
                if jid in self.joystick_contextmenu_items:
                    joystick_group.removeItem(self.joystick_contextmenu_items[jid]['item'])
                    del self.joystick_contextmenu_items[jid]
                if len(self.joystick_contextmenu_items) == 0:
                    _show_placeholder()

            def new_assignment(joystick, robot: BILBO, *args, **kwargs):
                jid = str(joystick.id)
                if jid in self.joystick_contextmenu_items:
                    item = self.joystick_contextmenu_items[jid]
                    if robot == self.robot:
                        item['item'].name = f"{item['joystick'].name} (ID: {jid}) ✅"
                    else:
                        item['item'].name = f"{item['joystick'].name} (ID: {jid}) (-> {robot.id})"

            def assignment_removed(joystick, robot: BILBO, *args, **kwargs):
                jid = str(joystick.id)
                if jid in self.joystick_contextmenu_items:
                    item = self.joystick_contextmenu_items[jid]
                    item['item'].name = f"{item['joystick'].name} (ID: {jid})"

            js_control.callbacks.new_joystick.register(add_joystick_menu_item)
            js_control.callbacks.joystick_disconnected.register(remove_joystick_menu_item)
            js_control.callbacks.new_assignment.register(new_assignment)
            js_control.callbacks.assignment_removed.register(assignment_removed)

            # Click on joystick indicator rumbles the assigned joystick
            def joystick_indicator_click_callback(*args, **kwargs):
                joystick = js_control.robotIsAssigned(self.robot)
                if joystick is not None:
                    joystick.rumble(strength=1, duration=1000)

            self.joystick_indicator.callbacks.click.register(joystick_indicator_click_callback)

        # Control Group
        control_group = Widget_Group(title='Control', rows=8, columns=10, show_title=True)
        page.addWidget(control_group, column=1, row=9, width=11, height=10)

        self.control_status_widget = StatusWidget(
            widget_id='control_status_widget',
            title='Status',
            elements={
                'mode': StatusWidgetElement(label='Control Mode',
                                            color=CONTROL_MODE_COLORS[self.robot.control.mode],
                                            status=self.robot.control.mode.name,
                                            ),
                'tic': StatusWidgetElement(label='Theta IntCtrl',
                                           color=[0.5, 0.5, 0.5] if not self.robot.core.data.control.tic_enabled else [
                                               0, 0.5, 0],
                                           status='disabled' if not self.robot.core.data.control.tic_enabled else 'enabled',
                                           ),
                'vic': StatusWidgetElement(label='Velocity IntCtrl',
                                           color=[0.5, 0.5, 0.5] if not self.robot.core.data.control.vic_enabled else [
                                               0, 0.5, 0],
                                           status='disabled' if not self.robot.core.data.control.vic_enabled else 'enabled',
                                           ),
                'psi': StatusWidgetElement(label='Psi Ctrl',
                                           color=[0.5, 0.5, 0.5] if not self.robot.core.data.control.psi_enabled else [
                                               0, 0.5, 0],
                                           status='disabled' if not self.robot.core.data.control.psi_enabled else 'enabled',
                                           ),
                'static': StatusWidgetElement(label='Static',
                                              color=[0.5, 0.5, 0.5],
                                              status='false',
                                              ),

            }
        )
        control_group.addWidget(self.control_status_widget, row=1, column=1, width=10, height=3)

        tic_button = MultiStateButton(
            id='tic_button',
            title='TIC',
            widget_id='tic_button',
            states=[
                'OFF', 'ON'
            ],
            current_state=self.robot.core.data.control.tic_enabled,
            color=[
                [0.5, 0.5, 0.5],
                [0, 0.3, 0],
            ]
        )

        def tic_button_clicked(state: str, *args, **kwargs):
            match state:
                case 'ON':
                    self.robot.control.enableTIC(False)
                case 'OFF':
                    self.robot.control.enableTIC(True)

        def on_tic_mode_changed(enabled: bool, *args, **kwargs):
            if enabled:
                tic_button.state = 'ON'
            else:
                tic_button.state = 'OFF'

        tic_button.callbacks.click.register(tic_button_clicked)
        self.robot.control.events.tic_mode_changed.on(on_tic_mode_changed)

        control_group.addWidget(tic_button, column=1, row=7, width=2, height=2)

        psi_toggle_button = MultiStateButton(
            id='psi_toggle_button',
            title='PSI',
            widget_id='psi_toggle_button',
            states=[
                'OFF', 'ON'
            ],
            current_state=self.robot.core.data.control.psi_enabled,
            color=[
                [0.5, 0.5, 0.5],
                [0, 0.3, 0],
            ]
        )

        def psi_button_clicked(state: str, *args, **kwargs):
            match state:
                case 'ON':
                    self.robot.control.enablePSI(False)
                case 'OFF':
                    self.robot.control.enablePSI(True)

        def on_psi_mode_changed(enabled: bool, *args, **kwargs):
            if enabled:
                psi_toggle_button.state = 'ON'
            else:
                psi_toggle_button.state = 'OFF'

        psi_toggle_button.callbacks.click.register(psi_button_clicked)
        self.robot.control.events.psi_mode_changed.on(on_psi_mode_changed)

        control_group.addWidget(psi_toggle_button, column=3, row=7, width=2, height=2)

        self.mode_widget = BilboModeWidget(current_mode=self.robot.control.mode.name)
        control_group.addWidget(self.mode_widget, column=1, height=3, width=10)

        def update_mode_widget(mode: BILBO_Control_Mode, *args, **kwargs):
            self.mode_widget.current_mode = mode.name

        def mode_widget_click_callback(mode_id, *args, **kwargs):
            match mode_id:
                case 'OFF':
                    self.robot.control.setControlMode(BILBO_Control_Mode.OFF)
                case 'DIRECT':
                    self.robot.control.setControlMode(BILBO_Control_Mode.DIRECT)
                case 'POSITION':
                    self.robot.control.setControlMode(BILBO_Control_Mode.POSITION)
                case 'VELOCITY':
                    self.robot.control.setControlMode(BILBO_Control_Mode.VELOCITY)
                case 'BALANCING':
                    self.robot.control.setControlMode(BILBO_Control_Mode.BALANCING)

        self.mode_widget.callbacks.mode_clicked.register(mode_widget_click_callback)
        self.robot.control.events.mode_changed.on(update_mode_widget)

        self.robot.control.events.mode_changed.on(update_mode_widget)

        states_group = Widget_Group(title='States', rows=7, columns=10, show_title=True)
        page.addWidget(states_group, column=12, width=10, height=8)
        self.x_digital_number = DigitalNumberWidget(widget_id='x_digital_number',
                                                    title='X',
                                                    min_value=-99,
                                                    max_value=99,
                                                    increment=0.01,
                                                    )
        states_group.addWidget(self.x_digital_number, row=1, column=1, width=7, height=1)

        self.y_digital_number = DigitalNumberWidget(widget_id='y_digital_number',
                                                    title='Y',
                                                    min_value=-99,
                                                    max_value=99,
                                                    increment=0.01,
                                                    )
        states_group.addWidget(self.y_digital_number, row=2, column=1, width=7, height=1)

        self.v_digital_number = DigitalNumberWidget(widget_id='v_digital_number',
                                                    title='V',
                                                    min_value=-9,
                                                    max_value=9,
                                                    increment=0.01,
                                                    color_ranges=[
                                                        {'min': -0.05, 'max': 0.05, 'color': [0, 0.8, 0]}
                                                    ]
                                                    )
        states_group.addWidget(self.v_digital_number, row=3, column=1, width=7, height=1)
        self.theta_digital_number = DigitalNumberWidget(widget_id='theta_digital_number',
                                                        title='Theta (deg)',
                                                        min_value=-999,
                                                        max_value=999,
                                                        increment=0.1,
                                                        color_ranges=[
                                                            {'min': -0.15, 'max': 0.15, 'color': [0, 0.8, 0]}
                                                        ]
                                                        )

        states_group.addWidget(self.theta_digital_number, row=4, column=1, width=7, height=1)

        theta_button = Button(widget_id='theta_button', text='→ rad', color=[0.4, 0.4, 0.4])
        self.overview_page_data['theta_digital_number_format'] = 'grad'

        def theta_button_click(*args, **kwargs):
            if self.overview_page_data['theta_digital_number_format'] == 'rad':
                self.overview_page_data['theta_digital_number_format'] = 'grad'
                theta_button.updateConfig(text='→ rad')
                self.theta_digital_number.updateConfig(title='Theta (deg)')
                self.theta_digital_number.format = 'grad'
            else:
                self.overview_page_data['theta_digital_number_format'] = 'rad'
                theta_button.updateConfig(text='→ deg')
                self.theta_digital_number.updateConfig(title='Theta (rad)')
                self.theta_digital_number.format = 'rad'

        theta_button.callbacks.click.register(theta_button_click)

        states_group.addWidget(theta_button, row=4, column=8, width=3, height=1)
        self.theta_dot_digital_number = DigitalNumberWidget(widget_id='theta_dot_digital_number',
                                                            title='Theta Dot (deg)',
                                                            min_value=-999,
                                                            max_value=999,
                                                            increment=0.1,
                                                            )
        states_group.addWidget(self.theta_dot_digital_number, row=5, column=1, width=7, height=1)
        theta_dot_button = Button(widget_id='theta_dot_button', text='→ rad', color=[0.4, 0.4, 0.4])

        self.overview_page_data['theta_dot_digital_number_format'] = 'grad'

        def theta_dot_button_click(*args, **kwargs):
            if self.overview_page_data['theta_dot_digital_number_format'] == 'rad':
                self.overview_page_data['theta_dot_digital_number_format'] = 'grad'
                theta_dot_button.updateConfig(text='→ rad')
                self.theta_dot_digital_number.updateConfig(title='Theta Dot (deg)')
                self.theta_dot_digital_number.format = 'grad'
            else:
                self.overview_page_data['theta_dot_digital_number_format'] = 'rad'
                theta_dot_button.updateConfig(text='→ deg')
                self.theta_dot_digital_number.updateConfig(title='Theta Dot (rad)')
                self.theta_dot_digital_number.format = 'rad'

        theta_dot_button.callbacks.click.register(theta_dot_button_click)

        states_group.addWidget(theta_dot_button, row=5, column=8, width=3, height=1)
        self.psi_digital_number = DigitalNumberWidget(widget_id='psi_digital_number',
                                                      title='Psi (deg)',
                                                      min_value=-999,
                                                      max_value=999,
                                                      increment=0.1,
                                                      )
        states_group.addWidget(self.psi_digital_number, row=6, column=1, width=7, height=1)
        psi_button = Button(widget_id='psi_button', text='→ rad', color=[0.4, 0.4, 0.4])

        self.overview_page_data['psi_digital_number_format'] = 'grad'

        def psi_button_click(*args, **kwargs):
            if self.overview_page_data['psi_digital_number_format'] == 'rad':
                self.overview_page_data['psi_digital_number_format'] = 'grad'
                psi_button.updateConfig(text='→ rad')
                self.psi_digital_number.updateConfig(title='Psi (deg)')
                self.psi_digital_number.format = 'grad'
            else:
                self.overview_page_data['psi_digital_number_format'] = 'rad'
                psi_button.updateConfig(text='→ deg')
                self.psi_digital_number.updateConfig(title='Psi (rad)')
                self.psi_digital_number.format = 'rad'

        psi_button.callbacks.click.register(psi_button_click)

        states_group.addWidget(psi_button, row=6, column=8, width=3, height=1)
        self.psi_dot_digital_number = DigitalNumberWidget(widget_id='psi_dot_digital_number',
                                                          title='Psi Dot (deg)',
                                                          min_value=-999,
                                                          max_value=999,
                                                          increment=0.1,
                                                          )
        states_group.addWidget(self.psi_dot_digital_number, row=7, column=1, width=7, height=1)
        psi_dot_button = Button(widget_id='psi_dot_button', text='→ rad', color=[0.4, 0.4, 0.4])

        self.overview_page_data['psi_dot_digital_number_format'] = 'grad'

        def psi_dot_button_click(*args, **kwargs):
            if self.overview_page_data['psi_dot_digital_number_format'] == 'rad':
                self.overview_page_data['psi_dot_digital_number_format'] = 'grad'
                psi_dot_button.updateConfig(text='→ rad')
                self.psi_dot_digital_number.updateConfig(title='Psi Dot (deg)')
                self.psi_dot_digital_number.format = 'grad'
            else:
                self.overview_page_data['psi_dot_digital_number_format'] = 'rad'
                psi_dot_button.updateConfig(text='→ deg')
                self.psi_dot_digital_number.updateConfig(title='Psi Dot (rad)')
                self.psi_dot_digital_number.format = 'rad'

        psi_dot_button.callbacks.click.register(psi_dot_button_click)

        states_group.addWidget(psi_dot_button, row=7, column=8, width=3, height=1)

        # === ESTIMATION GROUP ===
        estimation_group = Widget_Group(title='Estimation', rows=7, columns=10, show_title=True)
        page.addWidget(estimation_group, column=22, row=1, width=9, height=8)

        # Status widget showing dead-reckoning vs tracked
        self.estimation_status_widget = StatusWidget(
            widget_id='estimation_status_widget',
            title='Status',
            elements={
                'tracking': StatusWidgetElement(
                    label='Source',
                    color=[0.6, 0.2, 0.2],  # Red for dead-reckoning initially
                    status='Dead-Reckoning',
                ),
            }
        )
        estimation_group.addWidget(self.estimation_status_widget, row=1, column=1, width=10, height=2)

        # Reset estimation button
        self.reset_estimation_button = Button(
            widget_id='reset_estimation_button',
            text='Reset Estimation',
            color=[0.5, 0.3, 0.2],
        )
        estimation_group.addWidget(self.reset_estimation_button, row=3, column=1, width=10, height=1)

        def on_reset_estimation_clicked(*args, **kwargs):
            self.logger.info("Resetting estimation")
            self.robot.estimation.reset()

        self.reset_estimation_button.callbacks.click.register(on_reset_estimation_clicked)

        # Gyroscope readings (smaller digital numbers)
        gyro_label = TextWidget(widget_id='gyro_label', text='Gyro (deg/s)', fontSize=10,
                                textColor=[0.7, 0.7, 0.7, 1.0])
        estimation_group.addWidget(gyro_label, row=4, column=1, width=10, height=1)

        self.gyro_x_number = DigitalNumberWidget(
            widget_id='gyro_x_number',
            title='X',
            min_value=-999,
            max_value=999,
            increment=0.1,
        )
        estimation_group.addWidget(self.gyro_x_number, row=5, column=1, width=3, height=1)

        self.gyro_y_number = DigitalNumberWidget(
            widget_id='gyro_y_number',
            title='Y',
            min_value=-999,
            max_value=999,
            increment=0.1,
        )
        estimation_group.addWidget(self.gyro_y_number, row=5, column=4, width=3, height=1)

        self.gyro_z_number = DigitalNumberWidget(
            widget_id='gyro_z_number',
            title='Z',
            min_value=-999,
            max_value=999,
            increment=0.1,
        )
        estimation_group.addWidget(self.gyro_z_number, row=5, column=7, width=3, height=1)

        # Accelerometer readings (smaller digital numbers)
        acc_label = TextWidget(widget_id='acc_label', text='Acc (m/s²)', fontSize=10, textColor=[0.7, 0.7, 0.7, 1.0])
        estimation_group.addWidget(acc_label, row=6, column=1, width=10, height=1)

        self.acc_x_number = DigitalNumberWidget(
            widget_id='acc_x_number',
            title='X',
            min_value=-99,
            max_value=99,
            increment=0.01,
        )
        estimation_group.addWidget(self.acc_x_number, row=7, column=1, width=3, height=1)

        self.acc_y_number = DigitalNumberWidget(
            widget_id='acc_y_number',
            title='Y',
            min_value=-99,
            max_value=99,
            increment=0.01,
        )
        estimation_group.addWidget(self.acc_y_number, row=7, column=4, width=3, height=1)

        self.acc_z_number = DigitalNumberWidget(
            widget_id='acc_z_number',
            title='Z',
            min_value=-99,
            max_value=99,
            increment=0.01,
        )
        estimation_group.addWidget(self.acc_z_number, row=7, column=7, width=3, height=1)

        # Make the plots

        palette = get_palette('pastel', 7)

        v_plot = RT_Plot_Widget(
            widget_id='v_plot',
            plot_config={
                'title': 'V',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_v = v_plot.plot.add_y_axis(
            'v',
            {
                "label": f"v [m/s]",
                "min": -2,
                "max": 2,
                "color": palette[0],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 2,
                "highlight_zero": True,
                "side": "left",
            },
        )
        self.timeseries_v = TimeSeries(
            id='v',
            y_axis=y_axis_v,  # can pass the object or its id
            name='v',
            unit='m/s',
            color=palette[0],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        self.timeseries_v.set_value(0.0)
        v_plot.plot.add_timeseries(self.timeseries_v)
        page.addWidget(v_plot, column=31, row=7, width=10, height=6)

        theta_plot = RT_Plot_Widget(
            widget_id='theta_plot',
            plot_config={
                'title': 'Theta',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_theta = theta_plot.plot.add_y_axis(
            'theta',
            {
                "label": f"Theta [deg]",
                "min": -100,
                "max": 100,
                "color": palette[1],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 1,
                "highlight_zero": True,
            }
        )
        self.timeseries_theta = TimeSeries(
            id='theta',
            y_axis=y_axis_theta,  # can pass the object or its id
            name='theta',
            unit='deg',
            color=palette[1],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        theta_plot.plot.add_timeseries(self.timeseries_theta)
        page.addWidget(theta_plot, column=41, row=1, width=10, height=6)

        theta_dot_plot = RT_Plot_Widget(
            widget_id='theta_dot_plot',
            plot_config={
                'title': 'Theta Dot',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_theta_dot = theta_dot_plot.plot.add_y_axis(
            'theta_dot',
            {
                "label": f"Theta Dot [deg/s]",
                "min": -300,
                "max": 300,
                "color": palette[2],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 1,
                "highlight_zero": True,
            }
        )
        self.theta_dot_timeseries = TimeSeries(
            id='theta_dot',
            y_axis=y_axis_theta_dot,  # can pass the object or its id
            name='theta_dot',
            unit='deg',
            color=palette[2],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        theta_dot_plot.plot.add_timeseries(self.theta_dot_timeseries)
        page.addWidget(theta_dot_plot, column=41, row=7, width=10, height=6)

        psi_plot = RT_Plot_Widget(
            widget_id='psi_plot',
            plot_config={
                'title': 'Psi',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_psi = psi_plot.plot.add_y_axis(
            'psi',
            {
                "label": f"Psi [deg]",
                "min": -180,
                "max": 180,
                "color": palette[3],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 1,
                "highlight_zero": True,
            }
        )
        self.psi_plot_timeseries = TimeSeries(
            id='psi',
            y_axis=y_axis_psi,  # can pass the object or its id
            name='psi',
            unit='deg',
            color=palette[3],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        psi_plot.plot.add_timeseries(self.psi_plot_timeseries)
        page.addWidget(psi_plot, column=31, row=13, width=10, height=6)

        psi_dot_plot = RT_Plot_Widget(
            widget_id='psi_dot_plot',
            plot_config={
                'title': 'Psi Dot',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_psi_dot = psi_dot_plot.plot.add_y_axis(
            'psi_dot',
            {
                "label": f"Psi Dot [deg/s]",
                "min": -200,
                "max": 200,
                "color": palette[4],
                "precision": 1,
                "highlight_zero": True,
            }
        )
        self.psi_dot_timeseries = TimeSeries(
            id='psi_dot',
            y_axis=y_axis_psi_dot,  # can pass the object or its id
            name='psi_dot',
            unit='deg/s',
            color=palette[4],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        psi_dot_plot.plot.add_timeseries(self.psi_dot_timeseries)
        page.addWidget(psi_dot_plot, column=41, row=13, width=10, height=6)

        position_plot = RT_Plot_Widget(
            widget_id='position_plot',
            plot_config={
                'title': 'Position',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_position = position_plot.plot.add_y_axis(
            'position',
            {
                "label": f"Position [m]",
                "min": -4,
                "max": 4,
                "color": [0.5, 0.5, 0.5, 0.7],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 1,
                "highlight_zero": True,
            }
        )
        self.x_timeseries = TimeSeries(
            id='x',
            y_axis=y_axis_position,  # can pass the object or its id
            name='x',
            unit='m',
            color=palette[5],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        self.x_timeseries.set_value(0.0)
        position_plot.plot.add_timeseries(self.x_timeseries)

        self.y_timeseries = TimeSeries(
            id='y',
            y_axis=y_axis_position,  # can pass the object or its id
            name='y',
            unit='m',
            color=palette[6],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        self.y_timeseries.set_value(0.0)
        position_plot.plot.add_timeseries(self.y_timeseries)
        page.addWidget(position_plot, column=31, row=1, width=10, height=6)

        self.plots.append(v_plot)
        self.plots.append(theta_plot)
        self.plots.append(theta_dot_plot)
        self.plots.append(psi_plot)
        self.plots.append(psi_dot_plot)
        self.plots.append(position_plot)

        testbed_size = self.manager.testbed_definition.size
        self.map_widget = MapWidget(widget_id='map_widget',
                                    title='Testbed',
                                    limits={"x": [self.manager.testbed_definition.size['x'][0],
                                                  self.manager.testbed_definition.size['x'][1]],
                                            "y": [self.manager.testbed_definition.size['y'][0],
                                                  self.manager.testbed_definition.size['y'][1]]},
                                    initial_display_center=[(self.manager.testbed_definition.size['x'][0] +
                                                             self.manager.testbed_definition.size['x'][1]) / 2,
                                                            (self.manager.testbed_definition.size['y'][0] +
                                                             self.manager.testbed_definition.size['y'][1]) / 2],
                                    tiles=True,
                                    tile_size=0.5,
                                    show_grid=False,
                                    )

        # Single map agent — color changes based on tracking source:
        #   Green = tracked (OptiTrack), Red = dead-reckoning
        self.robot_map_agent = Agent(
            id=f"robot_map_agent", x=0, y=0, psi=0,
            size=0.1, arrow_length=0.25, arrow_width=0.05,
            color=[0.6, 0.2, 0.2],  # Red (dead-reckoning) initially
            show_name=False
        )
        self._first_stream_tick: int | None = None
        self.map_widget.map.addObject(self.robot_map_agent)

        def map_double_click(data, *args, **kwargs):
            x = data['x']
            y = data['y']
            if testbed_size['x'][0] < x < testbed_size['x'][1] and testbed_size['y'][0] < y < testbed_size['y'][1]:
                if self.nav_mode_button.state == 'Path':
                    self.robot.position_control.plan_and_follow(target=(x, y))
                else:
                    self.robot.position_control.move_to(x, y)
            else:
                self.logger.warning(f"Position out of bounds: {x}, {y}")

        self.map_widget.map.events.double_click.on(map_double_click)

        # === POSITION CONTROL VISUALIZATION ===
        STOP_POINT_COLOR = [1.0, 0.4, 0.2, 1.0]  # Orange for stop points
        STOP_DIM_ALPHA = 0.3  # Alpha for completed stop points
        PATH_LINE_COLOR = [0.4, 0.7, 1.0, 0.6]  # Light blue for path lines
        MOVE_TO_POINT_COLOR = [0.9, 0.3, 0.9, 1.0]  # Magenta for move_to_point target
        TURN_TO_HEADING_COLOR = [0.2, 0.9, 0.5, 0.8]  # Green for turn_to_heading indicator

        # Track path stop point objects for completion dimming
        self._path_stop_objects: list[Point] = []
        self._path_line_objects: list[Line] = []
        self._planned_path_objects: list[MapObject] = []
        self._planning_preview_objects: list[MapObject] = []

        def _clear_position_objects():
            """Clear all position control visualization objects"""
            for obj in self._additional_map_objects:
                try:
                    if obj.id in self.map_widget.map.objects:
                        self.map_widget.map.removeObject(obj)
                except Exception:
                    pass
            self._additional_map_objects = []
            self._path_stop_objects = []
            self._path_line_objects = []

        def _clear_planned_path():
            """Clear planned path preview objects"""
            for obj in self._planned_path_objects:
                try:
                    if obj.id in self.map_widget.map.objects:
                        self.map_widget.map.removeObject(obj)
                except Exception:
                    pass
            self._planned_path_objects = []

        # --- Planning preview (shown immediately on path_planning_started) ---
        PLANNING_START_COLOR = [0.3, 0.9, 0.3, 0.9]  # Green for start point
        PLANNING_TARGET_COLOR = [1.0, 0.3, 0.3, 0.9]  # Red for target point
        PLANNING_WAYPOINT_COLOR = [0.5, 0.6, 1.0, 0.8]  # Blue for waypoints
        PLANNING_PREVIEW_SIZE = 0.04
        PLANNING_PREVIEW_BORDER = [1.0, 1.0, 1.0, 0.8]

        def _clear_planning_preview():
            """Clear planning preview markers (start/target/waypoints shown before plan is ready)."""
            for obj in self._planning_preview_objects:
                try:
                    if obj.id in self.map_widget.map.objects:
                        self.map_widget.map.removeObject(obj)
                except Exception:
                    pass
            self._planning_preview_objects = []

        def _on_path_planning_started(data, *args, **kwargs):
            """Draw start, target, and waypoints immediately when planning begins."""
            if data is None:
                return
            _clear_planning_preview()

            start = data.get('start')
            target = data.get('target')
            waypoints = data.get('waypoints', [])

            if start:
                pt = Point(
                    id=f"planning_start_{generate_uuid()[:8]}",
                    x=start['x'], y=start['y'],
                    size=PLANNING_PREVIEW_SIZE,
                    color=PLANNING_START_COLOR,
                    border_color=PLANNING_PREVIEW_BORDER,
                    border_width=2,
                    shape='circle',
                    show_name=False,
                )
                self.map_widget.map.addObject(pt)
                self._planning_preview_objects.append(pt)

            if target:
                pt = Point(
                    id=f"planning_target_{generate_uuid()[:8]}",
                    x=target['x'], y=target['y'],
                    size=PLANNING_PREVIEW_SIZE * 1.2,
                    color=PLANNING_TARGET_COLOR,
                    border_color=PLANNING_PREVIEW_BORDER,
                    border_width=2,
                    shape='star',
                    show_name=False,
                )
                self.map_widget.map.addObject(pt)
                self._planning_preview_objects.append(pt)

            for i, wp in enumerate(waypoints):
                pt = Point(
                    id=f"planning_wp_{i}_{generate_uuid()[:8]}",
                    x=wp['x'], y=wp['y'],
                    size=PLANNING_PREVIEW_SIZE * 0.8,
                    color=PLANNING_WAYPOINT_COLOR,
                    border_color=PLANNING_PREVIEW_BORDER,
                    border_width=1,
                    shape='diamond',
                    show_name=False,
                )
                self.map_widget.map.addObject(pt)
                self._planning_preview_objects.append(pt)

        self.robot.position_control.events.path_planning_started.on(_on_path_planning_started)

        def _on_position_mode_changed(*args, **kwargs):
            _clear_planning_preview()
            if self._additional_map_objects:
                _clear_position_objects()

        self.robot.position_control.events.mode_changed.on(_on_position_mode_changed)

        def _on_path_loaded(path_data: PathData, *args, **kwargs):
            """Visualize loaded dense path — path info only (no individual points)"""
            if not path_data or path_data.path_point_count == 0:
                return

            _clear_position_objects()

            # For dense paths we don't visualize individual points (too many).
            # We show stop indices as orange markers if available.
            # The actual path polyline would require the full point data
            # which is only on the robot/firmware side.

        self.robot.position_control.events.path_loaded.on(_on_path_loaded)

        def _on_path_started(path_data: PathData, *args, **kwargs):
            """Ensure visualization exists when path starts"""
            if not path_data or path_data.path_point_count == 0:
                return
            if not self._path_stop_objects and not self._path_line_objects:
                _on_path_loaded(path_data)

        self.robot.position_control.events.path_started.on(_on_path_started)

        def _on_path_finished(*args, **kwargs):
            """Clear path visualization when finished"""
            _clear_position_objects()
            _clear_planning_preview()

        self.robot.position_control.events.path_finished.on(_on_path_finished)
        self.robot.position_control.events.path_aborted.on(_on_path_finished)
        self.robot.position_control.events.path_timeout.on(_on_path_finished)

        def _on_stop_completed(data: dict, *args, **kwargs):
            """Dim completed stop point"""
            if data is None:
                return
            idx = data.get('index', 0)

            # Dim the completed stop point
            if idx < len(self._path_stop_objects):
                obj = self._path_stop_objects[idx]
                current_color = obj.config.get('color', [0.5, 0.5, 0.5, 1.0])
                dimmed_color = current_color[:3] + [STOP_DIM_ALPHA]
                obj.updateConfig(color=dimmed_color)

        self.robot.position_control.events.stop_completed.on(_on_stop_completed)

        def _on_move_to_point_started(command: MoveToPointCommand, *args, **kwargs):
            """Show move_to_point target"""
            if command is None:
                return

            point = Point(
                id=f"move_to_target_{generate_uuid()[:8]}",
                x=command.x,
                y=command.y,
                size=0.07,
                color=MOVE_TO_POINT_COLOR,
                border_color=[1, 1, 1, 0.9],
                border_width=2,
                shape='circle',
                show_name=False,
            )
            self.map_widget.map.addObject(point)
            self._additional_map_objects.append(point)

        self.robot.position_control.events.move_to_point_started.on(_on_move_to_point_started)

        def _on_move_to_point_completed(*args, **kwargs):
            """Dim move_to_point target when completed"""
            # Find and dim the target point (last added point with move_to color)
            for obj in reversed(self._additional_map_objects):
                if isinstance(obj, Point) and obj.id.startswith('move_to_target_'):
                    current_color = obj.config.get('color', MOVE_TO_POINT_COLOR)
                    dimmed_color = current_color[:3] + [STOP_DIM_ALPHA]
                    obj.updateConfig(color=dimmed_color)
                    break

        self.robot.position_control.events.move_to_point_completed.on(_on_move_to_point_completed)
        self.robot.position_control.events.move_to_point_timeout.on(_on_move_to_point_completed)

        def _on_turn_to_heading_started(command: TurnToHeadingCommand, *args, **kwargs):
            """Show turn_to_heading indicator as a line from robot"""
            if command is None:
                return

            # Get current robot position
            robot_x = self.robot_map_agent.data.get('x', 0)
            robot_y = self.robot_map_agent.data.get('y', 0)

            # Calculate endpoint of heading indicator line
            line_length = 0.3
            end_x = robot_x + line_length * math.cos(command.heading)
            end_y = robot_y + line_length * math.sin(command.heading)

            # Create start point (at robot position, small)
            start_point = Point(
                id=f"heading_start_{generate_uuid()[:8]}",
                x=robot_x,
                y=robot_y,
                size=0.02,
                color=TURN_TO_HEADING_COLOR,
                show_name=False,
            )
            self.map_widget.map.addObject(start_point)
            self._additional_map_objects.append(start_point)

            # Create end point (at target heading)
            end_point = Point(
                id=f"heading_end_{generate_uuid()[:8]}",
                x=end_x,
                y=end_y,
                size=0.04,
                color=TURN_TO_HEADING_COLOR,
                border_color=[1, 1, 1, 0.8],
                border_width=1,
                shape='triangle',
                show_name=False,
            )
            self.map_widget.map.addObject(end_point)
            self._additional_map_objects.append(end_point)

            # Create line between them
            line = Line(
                id=f"heading_line_{generate_uuid()[:8]}",
                start=start_point,
                end=end_point,
                color=TURN_TO_HEADING_COLOR,
                width=2,
                style='solid',
                show_name=False,
            )
            self.map_widget.map.addObject(line)
            self._additional_map_objects.append(line)

        self.robot.position_control.events.turn_to_heading_started.on(_on_turn_to_heading_started)

        def _on_turn_to_heading_completed(*args, **kwargs):
            """Dim turn_to_heading indicator when completed"""
            # Find and dim the heading indicator objects
            for obj in self._additional_map_objects:
                if isinstance(obj, (Point, Line)) and ('heading_' in obj.id):
                    current_color = obj.config.get('color', TURN_TO_HEADING_COLOR)
                    dimmed_color = current_color[:3] + [STOP_DIM_ALPHA]
                    obj.updateConfig(color=dimmed_color)

        self.robot.position_control.events.turn_to_heading_completed.on(_on_turn_to_heading_completed)
        self.robot.position_control.events.turn_to_heading_timeout.on(_on_turn_to_heading_completed)

        # --- Obstacle visualization (from testbed) ---
        OBSTACLE_FILL_COLOR = [0.9, 0.2, 0.2, 0.3]  # Transparent red fill
        OBSTACLE_BORDER_COLOR = [1.0, 1.0, 1.0, 0.8]  # White border
        OBSTACLE_BORDER_WIDTH = 2

        def _add_obstacle_to_map(obstacle, *args, **kwargs):
            """Add a testbed obstacle to the 2D map."""
            if not isinstance(obstacle, BoxObstacle):
                return
            obs_id = obstacle.id
            if obs_id in self._obstacle_map_objects:
                return
            state = obstacle.state
            map_obj = Rectangle(
                id=f"obstacle_{obs_id}",
                x=state.x, y=state.y, psi=state.psi,
                width=obstacle.config.width, height=obstacle.config.height,
                color=OBSTACLE_FILL_COLOR,
                border_color=OBSTACLE_BORDER_COLOR,
                border_width=OBSTACLE_BORDER_WIDTH,
                show_name=False,
                layer=0,
            )
            self.map_widget.map.addObject(map_obj)
            self._obstacle_map_objects[obs_id] = map_obj

        def _remove_obstacle_from_map(obstacle, *args, **kwargs):
            """Remove a testbed obstacle from the 2D map."""
            if isinstance(obstacle, BoxObstacle):
                obs_id = obstacle.id
            elif isinstance(obstacle, str):
                obs_id = obstacle
            else:
                return
            if obs_id in self._obstacle_map_objects:
                obj = self._obstacle_map_objects.pop(obs_id)
                try:
                    self.map_widget.map.removeObject(obj)
                except Exception:
                    pass

        # Add existing obstacles
        for obs in self.manager.testbed.obstacles.values():
            _add_obstacle_to_map(obs)

        # Subscribe to testbed obstacle events
        self.manager.testbed.events.obstacle_added.on(_add_obstacle_to_map)
        self.manager.testbed.events.obstacle_removed.on(_remove_obstacle_from_map)

        # --- Planned path visualization ---
        PLANNED_PATH_COLOR = [0.4, 0.8, 1.0, 0.5]  # Light blue, semi-transparent
        PLANNED_PATH_POINT_SIZE = 0.015  # Small dots along path
        PLANNED_PATH_LINE_WIDTH = 2
        PLANNED_PATH_TARGET_COLOR = [0.2, 1.0, 0.4, 0.9]  # Green target point
        PLANNED_PATH_TARGET_SIZE = 0.04
        PLANNED_PATH_SUBSAMPLE = 5  # Show every Nth point to avoid clutter
        WAYPOINT_PASS_COLOR = [1.0, 0.8, 0.2, 0.9]  # Yellow for PASS waypoints
        WAYPOINT_STOP_COLOR = [1.0, 0.3, 0.3, 0.9]  # Red for STOP waypoints
        WAYPOINT_SIZE = 0.035  # Waypoint marker size
        WAYPOINT_BORDER_COLOR = [1.0, 1.0, 1.0, 0.9]  # White border

        def _draw_planned_path(path_data: PathData):
            """Draw a planned/loaded path as a polyline with target marker."""
            _clear_planned_path()

            points = path_data.path_points
            if not points or len(points) < 2:
                return

            # Subsample for visualization (dense paths may have 500+ points)
            vis_indices = list(range(0, len(points), PLANNED_PATH_SUBSAMPLE))
            if vis_indices[-1] != len(points) - 1:
                vis_indices.append(len(points) - 1)

            # Create point objects along the path
            prev_point_obj = None
            for i, idx in enumerate(vis_indices):
                x, y = points[idx]
                is_last = (idx == len(points) - 1)

                pt = Point(
                    id=f"planned_path_pt_{generate_uuid()[:8]}",
                    x=x, y=y,
                    size=PLANNED_PATH_TARGET_SIZE if is_last else PLANNED_PATH_POINT_SIZE,
                    color=PLANNED_PATH_TARGET_COLOR if is_last else PLANNED_PATH_COLOR,
                    border_color=[1, 1, 1, 0.8] if is_last else [0, 0, 0, 0],
                    border_width=2 if is_last else 0,
                    shape='circle',
                    show_name=False,
                )
                self.map_widget.map.addObject(pt)
                self._planned_path_objects.append(pt)

                # Connect consecutive points with lines
                if prev_point_obj is not None:
                    ln = Line(
                        id=f"planned_path_ln_{generate_uuid()[:8]}",
                        start=prev_point_obj,
                        end=pt,
                        color=PLANNED_PATH_COLOR,
                        width=PLANNED_PATH_LINE_WIDTH,
                        style='solid',
                        show_name=False,
                    )
                    self.map_widget.map.addObject(ln)
                    self._planned_path_objects.append(ln)

                prev_point_obj = pt

            # Draw waypoint markers (on top of path)
            if path_data.waypoints:
                for i, wp in enumerate(path_data.waypoints):
                    wx = wp.get('x', 0)
                    wy = wp.get('y', 0)
                    wp_type = wp.get('type', 'PASS').upper()
                    is_stop = wp_type == 'STOP'
                    color = WAYPOINT_STOP_COLOR if is_stop else WAYPOINT_PASS_COLOR

                    wp_pt = Point(
                        id=f"planned_path_wp_{generate_uuid()[:8]}",
                        x=wx, y=wy,
                        size=WAYPOINT_SIZE,
                        color=color,
                        border_color=WAYPOINT_BORDER_COLOR,
                        border_width=2,
                        shape='diamond',
                        show_name=False,
                    )
                    self.map_widget.map.addObject(wp_pt)
                    self._planned_path_objects.append(wp_pt)

        def _on_path_planned(path_data: PathData, *args, **kwargs):
            """Visualize a planned path preview."""
            _clear_planning_preview()
            if not path_data or path_data.path_point_count == 0:
                return
            _draw_planned_path(path_data)

        self.robot.position_control.events.path_planned.on(_on_path_planned)

        # Also draw path when loaded (has compressed points now)
        def _on_path_loaded_viz(path_data: PathData, *args, **kwargs):
            _clear_planning_preview()
            if not path_data or not path_data.path_points:
                return
            _draw_planned_path(path_data)

        self.robot.position_control.events.path_loaded.on(_on_path_loaded_viz)

        # Clear planned path when path finishes/aborts/cleared or a new path starts
        self.robot.position_control.events.path_finished.on(lambda *a, **kw: _clear_planned_path())
        self.robot.position_control.events.path_aborted.on(lambda *a, **kw: _clear_planned_path())
        self.robot.position_control.events.path_timeout.on(lambda *a, **kw: _clear_planned_path())
        self.robot.position_control.events.path_cleared.on(lambda *a, **kw: _clear_planned_path())

        navigation_group = Widget_Group(widget_id='navigation_group',
                                        title='Navigation',
                                        columns=9,
                                        rows=4,
                                        show_title=True,
                                        )
        page.addWidget(navigation_group, column=22, row=9, width=9, height=5)

        self.nav_mode_button = MultiStateButton(
            id='nav_mode_button',
            states=['MoveTo', 'Path'],
            current_state='Path',
            color=[
                [0.6, 0.3, 0.6],  # Purple for MoveTo
                [0.3, 0.5, 0.7],  # Blue for Path
            ],
            title='Click Mode',
        )
        navigation_group.addWidget(self.nav_mode_button, row=1, column=1, width=4, height=2)

        def nav_mode_clicked(state: str, *args, **kwargs):
            match state:
                case 'MoveTo':
                    self.nav_mode_button.state = 'Path'
                case 'Path':
                    self.nav_mode_button.state = 'MoveTo'

        self.nav_mode_button.callbacks.click.register(nav_mode_clicked)

        psi_zero_button = Button(widget_id='psi_zero_button', text='Ψ=0', color=[0.4, 0.4, 0.4])
        psi_zero_button.callbacks.click.register(lambda *args, **kwargs: self.robot.position_control.turn_to(0))
        navigation_group.addWidget(psi_zero_button, row=1, column=5, width=2, height=2)

        build_prm_button = Button(widget_id='build_prm_button', text='Build PRM', color=[0.4, 0.4, 0.4])
        build_prm_button.callbacks.click.register(lambda *args, **kwargs: self.robot.position_control.build_prm())
        navigation_group.addWidget(build_prm_button, row=1, column=7, width=3, height=2)

        turn_to_input_field = InputWidget(
            widget_id='turn_to_input_field',
            title='Psi (deg)',
            title_position='left',
            datatype='float',
            tooltip=None,
            value=None,
            commit_on_blur=True,
        )
        navigation_group.addWidget(turn_to_input_field, row=3, column=1, width=6, height=1)

        x_input_field = InputWidget(
            widget_id='x_input_field',
            title='x',
            title_position='left',
            datatype='float',
            tooltip=None,
            commit_on_blur=True,
        )

        y_input_field = InputWidget(
            widget_id='y_input_field',
            title='y',
            title_position='left',
            datatype='float',
            tooltip=None,
            commit_on_blur=True,
        )

        navigation_group.addWidget(x_input_field, row=4, column=1, width=3, height=1)
        navigation_group.addWidget(y_input_field, row=4, column=4, width=3, height=1)

        move_to_button = Button(widget_id='move_to_button', text='Move To', color=[0.4, 0.4, 0.4])

        navigation_group.addWidget(move_to_button, row=4, column=7, width=3, height=1)

        turn_to_button = Button(widget_id='turn_to_button', text='Turn To', color=[0.4, 0.4, 0.4])

        navigation_group.addWidget(turn_to_button, row=3, column=7, width=3, height=1)

        def turn_to_button_clicked(*args, **kwargs):
            psi = turn_to_input_field.value
            if psi is None:
                return
            self.robot.position_control.turn_to(np.deg2rad(psi))
            # turn_to_input_field.value = None

        def move_to_button_clicked(*args, **kwargs):
            x = x_input_field.value
            y = y_input_field.value
            if x is None or y is None:
                return
            self.robot.position_control.move_to(x, y)
            # x_input_field.value = None
            # y_input_field.value = None

        move_to_button.callbacks.click.register(move_to_button_clicked)
        turn_to_button.callbacks.click.register(turn_to_button_clicked)

        page.addWidget(self.map_widget, row=9, width=10, height=10)

        experiment_group = Widget_Group(widget_id='exp_group',
                                        title='Experiment',
                                        columns=9,
                                        rows=6,
                                        show_title=True,
                                        )
        page.addWidget(experiment_group, column=22, row=14, width=9, height=5)

        # --- Run experiment button ---
        self.exp_run_button = Button(widget_id='exp_run_button', text='Run', color=[0.3, 0.5, 0.3])
        experiment_group.addWidget(self.exp_run_button, row=1, column=1, width=3, height=2)

        def on_run_experiment_clicked(*args, **kwargs):
            threading.Thread(target=self._run_experiment_from_picker, daemon=True).start()

        self.exp_run_button.callbacks.click.register(on_run_experiment_clicked)

        # --- Stop experiment button ---
        self.exp_stop_button = Button(widget_id='exp_stop_button', text='Stop', color=[0.6, 0.2, 0.2])
        experiment_group.addWidget(self.exp_stop_button, row=1, column=4, width=3, height=2)
        self.exp_stop_button.callbacks.click.register(
            lambda *args, **kwargs: self.robot.experiment_handler.stop_experiment()
        )

        # --- Experiment status text ---
        self.exp_status_text = TextWidget(widget_id='exp_status', text='Idle', font_size=11)
        experiment_group.addWidget(self.exp_status_text, row=1, column=7, width=3, height=2)

        # --- Current action text ---
        self.exp_action_text = TextWidget(widget_id='exp_action', text='', font_size=11)
        experiment_group.addWidget(self.exp_action_text, row=3, column=1, width=9, height=4)

    # ------------------------------------------------------------------------------------------------------------------
    def build_control_page(self, page):
        # Parameter registry: (row_key, display_name, description, config_path, setter_key)
        # config_path is a dot-separated path into BILBO_ControlConfig
        self._control_param_registry = [
            # General
            ('general', 'General', [0.3, 0.3, 0.5, 0.9], [
                ('general.max_wheel_torque', 'Max Wheel Torque', 'Nm', 'general'),
                ('general.max_wheel_speed', 'Max Wheel Speed', 'rad/s', 'general'),
            ]),
            # Balancing TIC
            ('tic', 'Balancing TIC', [0.4, 0.3, 0.3, 0.9], [
                ('balancing_control.tic.ki', 'Ki', 'Integral gain', 'tic'),
                ('balancing_control.tic.max_torque', 'Max Torque', 'Nm', 'tic'),
                ('balancing_control.tic.theta_limit', 'Theta Limit', 'rad', 'tic'),
            ]),
            # Balancing VIC
            ('vic', 'Balancing VIC', [0.3, 0.4, 0.3, 0.9], [
                ('balancing_control.vic.ki', 'Ki', 'Integral gain', 'vic'),
                ('balancing_control.vic.max_torque', 'Max Torque', 'Nm', 'vic'),
                ('balancing_control.vic.v_limit', 'V Limit', 'm/s', 'vic'),
                ('balancing_control.vic.theta_limit', 'Theta Limit', 'rad', 'vic'),
            ]),
            # Balancing PSI
            ('psi', 'Balancing PSI', [0.3, 0.3, 0.5, 0.9], [
                ('balancing_control.psi.kp', 'Kp', 'Proportional gain', 'psi'),
                ('balancing_control.psi.ki', 'Ki', 'Integral gain', 'psi'),
                ('balancing_control.psi.max_torque', 'Max Torque', 'Nm', 'psi'),
            ]),
            # State Feedback
            ('statefeedback', 'State Feedback K', [0.45, 0.25, 0.35, 0.9], [
                ('balancing_control.K.0', 'K_v', 'Velocity gain', 'statefeedback'),
                ('balancing_control.K.1', 'K_theta', 'Pitch angle gain', 'statefeedback'),
                ('balancing_control.K.2', 'K_theta_dot', 'Pitch rate gain', 'statefeedback'),
                ('balancing_control.K.3', 'K_psi_dot', 'Yaw rate gain', 'statefeedback'),
            ]),
            # Velocity Forward PID
            ('vel_fwd_pid', 'Velocity Forward PID', [0.2, 0.5, 0.3, 0.9], [
                ('velocity_control.v.pid.Kp', 'Kp', 'Proportional gain', 'vel_fwd_pid'),
                ('velocity_control.v.pid.Ki', 'Ki', 'Integral gain', 'vel_fwd_pid'),
                ('velocity_control.v.pid.Kd', 'Kd', 'Derivative gain', 'vel_fwd_pid'),
                ('velocity_control.v.pid.i_term_limit', 'I-Term Limit', '', 'vel_fwd_pid'),
                ('velocity_control.v.pid.output_limit', 'Output Limit', '', 'vel_fwd_pid'),
                ('velocity_control.v.pid.Td_filter', 'D-Filter Td', 's', 'vel_fwd_pid'),
                ('velocity_control.v.pid.rate_limit', 'Rate Limit', '', 'vel_fwd_pid'),
                ('velocity_control.v.pid.setpoint_rate_limit', 'SP Rate Limit', '', 'vel_fwd_pid'),
            ]),
            # Velocity Forward FF
            ('vel_fwd_ff', 'Velocity Forward FF', [0.2, 0.4, 0.5, 0.9], [
                ('velocity_control.v.feedforward.Kv', 'Kv', 'Velocity gain', 'vel_fwd_ff'),
                ('velocity_control.v.feedforward.Ka', 'Ka', 'Acceleration gain', 'vel_fwd_ff'),
                ('velocity_control.v.feedforward.Kc', 'Kc', 'Constant gain', 'vel_fwd_ff'),
                ('velocity_control.v.feedforward.vref_slew_rate', 'Vref Slew Rate', '', 'vel_fwd_ff'),
                ('velocity_control.v.feedforward.Ta_filter', 'Accel Filter Ta', 's', 'vel_fwd_ff'),
                ('velocity_control.v.feedforward.v0_stiction', 'Stiction V0', 'm/s', 'vel_fwd_ff'),
                ('velocity_control.v.feedforward.v_decay_stiction', 'Stiction V Decay', '', 'vel_fwd_ff'),
                ('velocity_control.v.feedforward.output_limit', 'Output Limit', '', 'vel_fwd_ff'),
                ('velocity_control.v.feedforward.output_slew_rate', 'Output Slew Rate', '', 'vel_fwd_ff'),
            ]),
            # Velocity Turn PID
            ('vel_turn_pid', 'Velocity Turn PID', [0.5, 0.3, 0.2, 0.9], [
                ('velocity_control.psidot.pid.Kp', 'Kp', 'Proportional gain', 'vel_turn_pid'),
                ('velocity_control.psidot.pid.Ki', 'Ki', 'Integral gain', 'vel_turn_pid'),
                ('velocity_control.psidot.pid.Kd', 'Kd', 'Derivative gain', 'vel_turn_pid'),
                ('velocity_control.psidot.pid.i_term_limit', 'I-Term Limit', '', 'vel_turn_pid'),
                ('velocity_control.psidot.pid.output_limit', 'Output Limit', '', 'vel_turn_pid'),
                ('velocity_control.psidot.pid.Td_filter', 'D-Filter Td', 's', 'vel_turn_pid'),
                ('velocity_control.psidot.pid.rate_limit', 'Rate Limit', '', 'vel_turn_pid'),
                ('velocity_control.psidot.pid.setpoint_rate_limit', 'SP Rate Limit', '', 'vel_turn_pid'),
            ]),
            # Velocity Turn FF
            ('vel_turn_ff', 'Velocity Turn FF', [0.5, 0.2, 0.4, 0.9], [
                ('velocity_control.psidot.feedforward.Kv', 'Kv', 'Velocity gain', 'vel_turn_ff'),
                ('velocity_control.psidot.feedforward.Ka', 'Ka', 'Acceleration gain', 'vel_turn_ff'),
                ('velocity_control.psidot.feedforward.Kc', 'Kc', 'Constant gain', 'vel_turn_ff'),
                ('velocity_control.psidot.feedforward.vref_slew_rate', 'Vref Slew Rate', '', 'vel_turn_ff'),
                ('velocity_control.psidot.feedforward.Ta_filter', 'Accel Filter Ta', 's', 'vel_turn_ff'),
                ('velocity_control.psidot.feedforward.v0_stiction', 'Stiction V0', 'm/s', 'vel_turn_ff'),
                ('velocity_control.psidot.feedforward.v_decay_stiction', 'Stiction V Decay', '', 'vel_turn_ff'),
                ('velocity_control.psidot.feedforward.output_limit', 'Output Limit', '', 'vel_turn_ff'),
                ('velocity_control.psidot.feedforward.output_slew_rate', 'Output Slew Rate', '', 'vel_turn_ff'),
            ]),
            # Position Control
            ('position', 'Position Control', [0.4, 0.2, 0.5, 0.9], [
                ('position_control.kp_angular', 'Kp Angular', 'rad/s per rad', 'position'),
                ('position_control.ki_angular', 'Ki Angular', 'rad/s per rad*s', 'position'),
                ('position_control.kp_angular_heading', 'Kp Angular Heading', 'rad/s per rad', 'position'),
                ('position_control.ki_angular_heading', 'Ki Angular Heading', 'rad/s per rad*s', 'position'),
                ('position_control.kp_linear', 'Kp Linear', '1/s', 'position'),
                ('position_control.ki_linear', 'Ki Linear', '1/s^2', 'position'),
                ('position_control.kd_linear', 'Kd Linear', '-', 'position'),
                ('position_control.max_speed', 'Max Speed', 'm/s', 'position'),
                ('position_control.max_turn_rate', 'Max Turn Rate', 'rad/s', 'position'),
                ('position_control.lookahead_base', 'Lookahead Base', 'm', 'position'),
                ('position_control.lookahead_min', 'Lookahead Min', 'm', 'position'),
                ('position_control.arrival_tolerance', 'Arrival Tolerance', 'm', 'position'),
                ('position_control.arrival_dwell_time', 'Arrival Dwell', 's', 'position'),
                ('position_control.decel_limit', 'Decel Limit', 'm/s^2', 'position'),
                ('position_control.curvature_gain', 'Curvature Gain', '-', 'position'),
                ('position_control.curvature_lookahead', 'Curvature Lookahead', 'm', 'position'),
            ]),
        ]

        # Build the table
        self.control_config_table = Table(widget_id='control_config_table')
        self.control_config_table.add_column(
            TextColumn(id='name', title='Parameter', width=0.3, font_align='left',
                       font_size=9, padding='1px 1px 1px 6px'))
        self.control_config_table.add_column(
            TextColumn(id='description', title='Description', width=0.3, font_align='left',
                       text_color=[1, 1, 1, 0.5], font_size=8, padding='1px 1px 1px 6px'))
        self.control_config_table.add_column(
            TextInputColumn(id='value', title='Value', width=0.4, font_align='right', text_color=[1, 1, 1, 0.8]))

        # Build groups and rows
        self._control_row_map = {}  # row_key -> (row, config_path, setter_key)

        for group_id, group_title, group_color, params in self._control_param_registry:
            group = TableGroup(
                id=f'ctrl_{group_id}',
                title=group_title,
                collapsible=True,
                group_color=group_color,
            )
            self.control_config_table.items[group.id] = group
            group._table = self.control_config_table

            for config_path, display_name, desc, setter_key in params:
                row_key = config_path  # use full path as unique key
                row = group.make_row(
                    name=display_name,
                    description=desc,
                    value='—',
                )
                self._control_row_map[row_key] = (row, config_path, setter_key)

                # Register update_request callback on the value cell
                value_cell = row.cells['value']
                value_cell.callbacks.update_request.register(
                    self._on_control_param_edit,
                    inputs={'row_key': row_key, 'row_id': row.id},
                )

        page.addWidget(self.control_config_table, column=1, row=1, width=18, height=16)

        # --- Auto/Manual write mode ---
        self._control_auto_write = True  # True = AUTO, False = MANUAL
        self._control_pending_changes = {}  # row_key -> float_value
        self._control_initial_config = None  # snapshot taken on first fetch

        self.control_write_mode_button = MultiStateButton(
            id='control_write_mode',
            states=['AUTO', 'MANUAL'],
            current_state='AUTO',
            color=[
                [0.2, 0.5, 0.3],  # Green for AUTO
                [0.6, 0.4, 0.2],  # Orange for MANUAL
            ],
            title='Write Mode',
        )
        page.addWidget(self.control_write_mode_button, column=1, row=17, width=3, height=2)

        def on_write_mode_toggle(state, *args, **kwargs):
            if state == 'AUTO':
                self._control_auto_write = False
                self.control_write_mode_button.state = 'MANUAL'
                self.control_send_button.updateConfig(color=[0.5, 0.3, 0.2])
            else:
                # Switching back to AUTO: send any pending changes first
                if self._control_pending_changes:
                    self._send_pending_control_changes()
                self._control_auto_write = True
                self.control_write_mode_button.state = 'AUTO'
                self.control_send_button.updateConfig(color=[0.3, 0.3, 0.3])

        self.control_write_mode_button.callbacks.click.register(on_write_mode_toggle)

        self.control_send_button = Button(
            widget_id='control_send',
            text='Send',
            color=[0.3, 0.3, 0.3],
            callback=lambda *a, **kw: self._send_pending_control_changes(),
        )
        page.addWidget(self.control_send_button, row=17, width=3, height=2)

        self.control_restore_button = Button(
            widget_id='control_restore',
            text='Restore',
            color=[0.4, 0.25, 0.25],
            callback=lambda *a, **kw: self._restore_initial_control_config(),
        )
        page.addWidget(self.control_restore_button, row=17, width=3, height=2)

        self.control_copy_yaml_button = Button(
            widget_id='control_copy_yaml',
            text='Copy YAML',
            color=[0.3, 0.3, 0.5],
            callback=lambda *a, **kw: self._copy_control_config_yaml(),
        )
        page.addWidget(self.control_copy_yaml_button, row=17, width=3, height=2)

        # Initialize table and listen for config changes from robot
        self._initialize_control_table_from_config()
        self.robot.control.events.configuration_changed.on(self._on_control_config_changed)

    # ------------------------------------------------------------------------------------------------------------------
    def build_debug_page(self, page):
        """Build the Debug page for temporary/experimental features."""

        # === ESTIMATION DEBUG GROUP ===
        estimation_group = Widget_Group(
            group_id='estimation_debug',
            title='Estimation',
            rows=6,
            columns=12,
            show_title=True
        )
        page.addWidget(estimation_group, column=1, row=1, width=12, height=7)

        # Dead-reckoning toggle button
        self.dead_reckoning_button = MultiStateButton(
            id='dead_reckoning_toggle',
            states=['ON', 'OFF'],
            current_state='ON',
            color=[
                [0.2, 0.6, 0.2],  # Green for ON
                [0.6, 0.3, 0.2],  # Red for OFF
            ],
            title='Dead Reckoning EKF'
        )
        estimation_group.addWidget(self.dead_reckoning_button, row=1, column=1, width=12, height=2)

        def on_dead_reckoning_toggle(state, *args, **kwargs):
            enable = (state == 'OFF')  # If currently OFF, enable it
            self.robot.estimation.set_dead_reckoning_enabled(enable)
            # Toggle to opposite state
            new_state = 'ON' if enable else 'OFF'
            self.dead_reckoning_button.state = new_state

        self.dead_reckoning_button.callbacks.click.register(on_dead_reckoning_toggle)

        # Tracker updates toggle button (simulate tracker unavailable)
        self.tracker_updates_button = MultiStateButton(
            id='tracker_updates_toggle',
            states=['ON', 'OFF'],
            current_state='ON',
            color=[
                [0.2, 0.6, 0.2],  # Green for ON
                [0.6, 0.3, 0.2],  # Red for OFF
            ],
            title='Tracker → Lowlevel'
        )
        estimation_group.addWidget(self.tracker_updates_button, row=3, column=1, width=12, height=2)

        def on_tracker_updates_toggle(state, *args, **kwargs):
            enable = (state == 'OFF')  # If currently OFF, enable it
            self.robot.estimation.set_tracker_updates_enabled(enable)
            # Toggle to opposite state
            new_state = 'ON' if enable else 'OFF'
            self.tracker_updates_button.state = new_state

        self.tracker_updates_button.callbacks.click.register(on_tracker_updates_toggle)

        # Initialize from robot state (delayed to allow connection)
        def init_estimation_debug_state():
            try:
                # Dead-reckoning state
                dr_enabled = self.robot.estimation.get_dead_reckoning_enabled()
                if dr_enabled is not None:
                    self.dead_reckoning_button.state = 'ON' if dr_enabled else 'OFF'

                # Tracker updates state
                tracker_enabled = self.robot.estimation.get_tracker_updates_enabled()
                if tracker_enabled is not None:
                    self.tracker_updates_button.state = 'ON' if tracker_enabled else 'OFF'
            except Exception as e:
                self.logger.warning(f"Could not get estimation debug state: {e}")

        set_timeout(init_estimation_debug_state, 1.0)

    # ------------------------------------------------------------------------------------------------------------------
    def build_experiment_page(self, page):
        """Build the Experiment page for running experiments."""
        self.experiment_designer = ExperimentDesignerWidget(
            widget_id='experiment_designer',
            on_play=self.on_experiment_play,
            on_stop=self.on_experiment_stop,
            transparent=True,
            action_library=ActionLibrary.BILBO
        )

        page.addWidget(self.experiment_designer, row=1, column=1, width=50, height=18)

    # ------------------------------------------------------------------------------------------------------------------
    def on_experiment_play(self, yaml: str = None, file_path: str = None, *args, **kwargs):
        yaml_string = yaml
        try:
            definition = yaml_module.safe_load(yaml_string)
        except Exception as e:
            self.logger.error(f"Failed to parse experiment YAML: {e}")
            return
        # Use per-tab file path from frontend, fall back to Python-tracked path
        designer_file = file_path or self.experiment_designer.current_file_path
        if designer_file:
            self._show_experiment_popup(definition, source='file', file_path=designer_file,
                                        yaml_string=yaml_string)
        else:
            self._show_experiment_popup(definition, source='yaml_string', yaml_string=yaml_string)

    # ------------------------------------------------------------------------------------------------------------------
    def on_experiment_stop(self, *args, **kwargs):
        self.robot.experiment_handler.stop_experiment()

    # ------------------------------------------------------------------------------------------------------------------
    def build_folder(self):
        folder_kwargs = {'image': self._robot_image_uri, 'image_opacity': 0.7, 'text_position': 'top'} if self._robot_image_uri else {}
        self.app_folder = Folder(folder_id=self.robot.id, rows=4, columns=8, **folder_kwargs)

        # ==============================================================================================================
        # PAGE 1: MAIN STATUS/CONTROL (uses auto-created page at position 0)
        # ==============================================================================================================

        # --- Row 1: Mode widget + Battery + Connection ---
        self.app_bilbo_mode_widget = BilboModeWidget(widget_id='app_mode_widget',
                                                     current_mode=self.robot.control.mode.name)

        def app_update_mode_widget(mode: BILBO_Control_Mode, *args, **kwargs):
            self.app_bilbo_mode_widget.current_mode = mode.name

        def app_mode_widget_click(mode_id, *args, **kwargs):
            match mode_id:
                case 'OFF':
                    self.robot.control.setControlMode(BILBO_Control_Mode.OFF)
                case 'DIRECT':
                    self.robot.control.setControlMode(BILBO_Control_Mode.DIRECT)
                case 'BALANCING':
                    self.robot.control.setControlMode(BILBO_Control_Mode.BALANCING)
                case 'VELOCITY':
                    self.robot.control.setControlMode(BILBO_Control_Mode.VELOCITY)
                case 'POSITION':
                    self.robot.control.setControlMode(BILBO_Control_Mode.POSITION)

        self.app_bilbo_mode_widget.callbacks.mode_clicked.register(app_mode_widget_click)
        self.robot.control.events.mode_changed.on(app_update_mode_widget)
        self.app_folder.addObject(self.app_bilbo_mode_widget, row=1, column=1, width=4, height=1)

        self.app_battery_indicator = BatteryIndicatorWidget(
            widget_id='app_battery', label_position='center', show='voltage',
        )
        self.app_folder.addObject(self.app_battery_indicator, row=1, column=5, width=1, height=1)

        self.app_connection_indicator = ConnectionIndicator(widget_id='app_connection')
        self.app_folder.addObject(self.app_connection_indicator, row=1, column=6, width=1, height=1)

        self.app_temp_widget = StatusWidget(
            widget_id='app_temp_status',
            elements={
                'temp': StatusWidgetElement(label='Temp', color=[0.5, 0.5, 0.5], status='--'),
            },
            font_size=9,
        )
        self.app_folder.addObject(self.app_temp_widget, row=1, column=7, width=1, height=1)

        self.app_joystick_indicator = JoystickIndicator(widget_id='app_joystick')
        self.app_joystick_indicator.setValue(False)
        self.app_folder.addObject(self.app_joystick_indicator, row=1, column=8, width=1, height=1)

        # --- Row 2: Status widget (mode, TIC, VIC, PSI, static, experiment) ---
        _white = [1, 1, 1]
        self.app_status_widget = StatusWidget(
            widget_id='app_status_widget',
            title='Status',
            elements={
                'mode': StatusWidgetElement(
                    label='Mode',
                    color=CONTROL_MODE_COLORS[self.robot.control.mode],
                    status=self.robot.control.mode.name,
                    label_color=_white, status_color=_white,
                ),
                'tic': StatusWidgetElement(
                    label='TIC',
                    color=[0.5, 0.5, 0.5] if not self.robot.core.data.control.tic_enabled else [0, 0.5, 0],
                    status='disabled' if not self.robot.core.data.control.tic_enabled else 'enabled',
                    label_color=_white, status_color=_white,
                ),
                'vic': StatusWidgetElement(
                    label='VIC',
                    color=[0.5, 0.5, 0.5] if not self.robot.core.data.control.vic_enabled else [0, 0.5, 0],
                    status='disabled' if not self.robot.core.data.control.vic_enabled else 'enabled',
                    label_color=_white, status_color=_white,
                ),
                'psi': StatusWidgetElement(
                    label='PSI',
                    color=[0.5, 0.5, 0.5] if not self.robot.core.data.control.psi_enabled else [0, 0.5, 0],
                    status='disabled' if not self.robot.core.data.control.psi_enabled else 'enabled',
                    label_color=_white, status_color=_white,
                ),
                'static': StatusWidgetElement(
                    label='Static',
                    color=[0.5, 0.5, 0.5],
                    status='false',
                    label_color=_white, status_color=_white,
                ),
                'experiment': StatusWidgetElement(
                    label='Experiment',
                    color=[0.5, 0.5, 0.5],
                    status='Idle',
                    label_color=_white, status_color=_white,
                ),
            }
        )
        self.app_folder.addObject(self.app_status_widget, row=2, column=1, width=4, height=1)

        # --- Rows 2-4, columns 7-8: Digital numbers group ---
        app_numbers_group = Widget_Group(
            group_id='app_numbers', rows=5, columns=1,
            background_color='transparent', border_width=0, fill_empty=False,
        )
        self.app_x_number = DigitalNumberWidget(
            widget_id='app_x_number', title='X',
            min_value=-99, max_value=99, increment=0.01,
        )
        app_numbers_group.addWidget(self.app_x_number, row=1, column=1, width=1, height=1)

        self.app_y_number = DigitalNumberWidget(
            widget_id='app_y_number', title='Y',
            min_value=-99, max_value=99, increment=0.01,
        )
        app_numbers_group.addWidget(self.app_y_number, row=2, column=1, width=1, height=1)

        self.app_v_number_main = DigitalNumberWidget(
            widget_id='app_v_number_main', title='V',
            min_value=-9, max_value=9, increment=0.01,
            color_ranges=[{'min': -0.05, 'max': 0.05, 'color': [0, 0.8, 0]}]
        )
        app_numbers_group.addWidget(self.app_v_number_main, row=3, column=1, width=1, height=1)

        self.app_theta_number = DigitalNumberWidget(
            widget_id='app_theta_number', title='Theta',
            min_value=-999, max_value=999, increment=0.1,
            color_ranges=[{'min': -0.15, 'max': 0.15, 'color': [0, 0.8, 0]}]
        )
        app_numbers_group.addWidget(self.app_theta_number, row=4, column=1, width=1, height=1)

        self.app_psi_number = DigitalNumberWidget(
            widget_id='app_psi_number', title='Psi',
            min_value=-999, max_value=999, increment=0.1,
        )
        app_numbers_group.addWidget(self.app_psi_number, row=5, column=1, width=1, height=1)

        self.app_folder.addObject(app_numbers_group, row=2, column=7, width=2, height=3)

        # --- Rows 2-4, columns 1-6: Buttons ---
        # Row 3
        app_start_button = Button(widget_id='app_start_btn', text='Start', color=[0.0, 0.4, 0.0])
        app_start_button.callbacks.click.register(self.robot.core.set_start_event_robot, discard_inputs=True)
        self.app_folder.addObject(app_start_button, row=3, column=1, width=1, height=1)

        app_stop_button = Button(widget_id='app_stop_btn', text='Stop', color=[0.4, 0, 0])
        app_stop_button.callbacks.click.register(self.robot.core.set_stop_event_robot, discard_inputs=True)
        self.app_folder.addObject(app_stop_button, row=3, column=2, width=1, height=1)

        app_resume_button = Button(widget_id='app_resume_btn', text='Resume', color=[75 / 255, 82 / 255, 56 / 255])
        app_resume_button.callbacks.click.register(self.robot.core.set_resume_event_robot, discard_inputs=True)
        self.app_folder.addObject(app_resume_button, row=3, column=3, width=1, height=1)

        app_revert_button = Button(widget_id='app_revert_btn', text='Revert', color=[59 / 255, 20 / 255, 120 / 255])
        app_revert_button.callbacks.click.register(self.robot.core.set_repeat_event_robot, discard_inputs=True)
        self.app_folder.addObject(app_revert_button, row=3, column=4, width=1, height=1)

        app_fall_forward_button = Button(widget_id='app_fall_fwd_btn', text='Fall ↑', color=[0.6, 0.2, 0.1])
        app_fall_forward_button.callbacks.click.register(
            lambda *args, **kwargs: self.robot.control.fall_down('forward'))
        self.app_folder.addObject(app_fall_forward_button, row=3, column=5, width=1, height=1)

        app_fall_backward_button = Button(widget_id='app_fall_bwd_btn', text='Fall ↓', color=[0.6, 0.2, 0.1])
        app_fall_backward_button.callbacks.click.register(
            lambda *args, **kwargs: self.robot.control.fall_down('backward'))
        self.app_folder.addObject(app_fall_backward_button, row=3, column=6, width=1, height=1)

        # --- Row 4: TIC + PSI toggles (1 col each) ---
        app_tic_button = MultiStateButton(
            id='app_tic_button', title='TIC',
            states=['OFF', 'ON'],
            current_state=self.robot.core.data.control.tic_enabled,
            color=[[0.5, 0.5, 0.5], [0, 0.3, 0]],
        )

        def app_tic_clicked(state: str, *args, **kwargs):
            match state:
                case 'ON':
                    self.robot.control.enableTIC(False)
                case 'OFF':
                    self.robot.control.enableTIC(True)

        app_tic_button.callbacks.click.register(app_tic_clicked)
        self.robot.control.events.tic_mode_changed.on(
            lambda enabled, *a, **kw: setattr(app_tic_button, 'state', 'ON' if enabled else 'OFF'))
        self.app_folder.addObject(app_tic_button, row=4, column=1, width=1, height=1)

        app_psi_button = MultiStateButton(
            id='app_psi_button', title='PSI',
            states=['OFF', 'ON'],
            current_state=self.robot.core.data.control.psi_enabled,
            color=[[0.5, 0.5, 0.5], [0, 0.3, 0]],
        )

        def app_psi_clicked(state: str, *args, **kwargs):
            match state:
                case 'ON':
                    self.robot.control.enablePSI(False)
                case 'OFF':
                    self.robot.control.enablePSI(True)

        app_psi_button.callbacks.click.register(app_psi_clicked)
        self.robot.control.events.psi_mode_changed.on(
            lambda enabled, *a, **kw: setattr(app_psi_button, 'state', 'ON' if enabled else 'OFF'))
        self.app_folder.addObject(app_psi_button, row=4, column=2, width=1, height=1)

        app_go_to_pose_button = Button(widget_id='app_go_to_pose_btn', text='Default', color=[0.3, 0.3, 0.5])

        def on_default_pose_clicked(*args, **kwargs):
            pose = self.manager.testbed.poses.get('default')
            if pose is None:
                self.logger.warning("Pose 'default' not found in testbed")
                return
            self.robot.position_control.move_to_pose(x=pose.x, y=pose.y, heading=pose.psi)

        app_go_to_pose_button.callbacks.click.register(on_default_pose_clicked)
        self.app_folder.addObject(app_go_to_pose_button, row=4, column=3, width=1, height=1)

        # ==============================================================================================================
        # PAGE 2: MAP
        # ==============================================================================================================
        map_page = FolderPage(page_id='map', name='Map', rows=5, columns=8)
        self.app_folder.addPage(map_page)

        testbed_size = self.manager.testbed_definition.size
        self.app_map_widget = MapWidget(
            widget_id='app_map_widget',
            title='Map',
            limits={"x": [testbed_size['x'][0], testbed_size['x'][1]],
                    "y": [testbed_size['y'][0], testbed_size['y'][1]]},
            initial_display_center=[(testbed_size['x'][0] + testbed_size['x'][1]) / 2,
                                    (testbed_size['y'][0] + testbed_size['y'][1]) / 2],
            tiles=True,
            tile_size=0.5,
            show_grid=False,
        )

        self.app_map_agent = Agent(
            id="app_map_agent", x=0, y=0, psi=0,
            size=0.1, arrow_length=0.25, arrow_width=0.05,
            color=[0.6, 0.2, 0.2],
            show_name=False
        )
        self.app_map_widget.map.addObject(self.app_map_agent)
        map_page.addObject(self.app_map_widget, row=1, column=1, width=8, height=4)

        # Double-tap on app map → move_to (direct)
        def app_map_double_tap(data, *args, **kwargs):
            x = data['x']
            y = data['y']
            if testbed_size['x'][0] < x < testbed_size['x'][1] and testbed_size['y'][0] < y < testbed_size['y'][1]:
                self.robot.position_control.move_to(x, y)
            else:
                self.logger.warning(f"Position out of bounds: {x}, {y}")

        # Long-press on app map → navigate (plan_and_follow)
        def app_map_long_press(data, *args, **kwargs):
            x = data['x']
            y = data['y']
            if testbed_size['x'][0] < x < testbed_size['x'][1] and testbed_size['y'][0] < y < testbed_size['y'][1]:
                self.robot.position_control.plan_and_follow(target=(x, y))
            else:
                self.logger.warning(f"Position out of bounds: {x}, {y}")

        self.app_map_widget.map.events.double_click.on(app_map_double_tap)
        self.app_map_widget.map.events.long_press.on(app_map_long_press)

        # --- App map: position control visualization (mirrors desktop GUI) ---
        self._app_map_objects: list[MapObject] = []

        APP_MOVE_TO_COLOR = [0.9, 0.3, 0.9, 1.0]
        APP_HEADING_COLOR = [0.2, 0.9, 0.5, 0.8]
        APP_DIM_ALPHA = 0.3

        def _app_clear_map_objects():
            for obj in self._app_map_objects:
                try:
                    if obj.id in self.app_map_widget.map.objects:
                        self.app_map_widget.map.removeObject(obj)
                except Exception:
                    pass
            self._app_map_objects = []

        def _app_on_move_to_started(command: MoveToPointCommand, *args, **kwargs):
            if command is None:
                return
            point = Point(
                id=f"app_move_target_{generate_uuid()[:8]}",
                x=command.x, y=command.y,
                size=0.07,
                color=APP_MOVE_TO_COLOR,
                border_color=[1, 1, 1, 0.9],
                border_width=2,
                shape='circle',
                show_name=False,
            )
            self.app_map_widget.map.addObject(point)
            self._app_map_objects.append(point)

        def _app_on_move_to_completed(*args, **kwargs):
            for obj in reversed(self._app_map_objects):
                if isinstance(obj, Point) and obj.id.startswith('app_move_target_'):
                    dimmed = obj.config.get('color', APP_MOVE_TO_COLOR)[:3] + [APP_DIM_ALPHA]
                    obj.updateConfig(color=dimmed)
                    break

        def _app_on_turn_to_started(command: TurnToHeadingCommand, *args, **kwargs):
            if command is None:
                return
            robot_x = self.app_map_agent.data.get('x', 0)
            robot_y = self.app_map_agent.data.get('y', 0)
            line_length = 0.3
            end_x = robot_x + line_length * math.cos(command.heading)
            end_y = robot_y + line_length * math.sin(command.heading)

            start_pt = Point(
                id=f"app_heading_start_{generate_uuid()[:8]}",
                x=robot_x, y=robot_y, size=0.02,
                color=APP_HEADING_COLOR, show_name=False,
            )
            self.app_map_widget.map.addObject(start_pt)
            self._app_map_objects.append(start_pt)

            end_pt = Point(
                id=f"app_heading_end_{generate_uuid()[:8]}",
                x=end_x, y=end_y, size=0.04,
                color=APP_HEADING_COLOR,
                border_color=[1, 1, 1, 0.8], border_width=1,
                shape='triangle', show_name=False,
            )
            self.app_map_widget.map.addObject(end_pt)
            self._app_map_objects.append(end_pt)

            line = Line(
                id=f"app_heading_line_{generate_uuid()[:8]}",
                start=start_pt, end=end_pt,
                color=APP_HEADING_COLOR, width=2, style='solid',
                show_name=False,
            )
            self.app_map_widget.map.addObject(line)
            self._app_map_objects.append(line)

        def _app_on_turn_to_completed(*args, **kwargs):
            for obj in self._app_map_objects:
                if isinstance(obj, (Point, Line)) and 'app_heading_' in obj.id:
                    dimmed = obj.config.get('color', APP_HEADING_COLOR)[:3] + [APP_DIM_ALPHA]
                    obj.updateConfig(color=dimmed)

        def _app_on_position_mode_changed(*args, **kwargs):
            _app_clear_map_objects()

        # --- App map: planned path visualization ---
        self._app_planned_path_objects: list[MapObject] = []

        APP_PATH_COLOR = [0.4, 0.8, 1.0, 0.5]
        APP_PATH_POINT_SIZE = 0.015
        APP_PATH_LINE_WIDTH = 2
        APP_PATH_TARGET_COLOR = [0.2, 1.0, 0.4, 0.9]
        APP_PATH_TARGET_SIZE = 0.04
        APP_PATH_SUBSAMPLE = 5
        APP_WP_PASS_COLOR = [1.0, 0.8, 0.2, 0.9]
        APP_WP_STOP_COLOR = [1.0, 0.3, 0.3, 0.9]
        APP_WP_SIZE = 0.035
        APP_WP_BORDER = [1.0, 1.0, 1.0, 0.9]

        def _app_clear_planned_path():
            for obj in self._app_planned_path_objects:
                try:
                    if obj.id in self.app_map_widget.map.objects:
                        self.app_map_widget.map.removeObject(obj)
                except Exception:
                    pass
            self._app_planned_path_objects = []

        def _app_draw_planned_path(path_data: PathData):
            _app_clear_planned_path()
            points = path_data.path_points
            if not points or len(points) < 2:
                return

            vis_indices = list(range(0, len(points), APP_PATH_SUBSAMPLE))
            if vis_indices[-1] != len(points) - 1:
                vis_indices.append(len(points) - 1)

            prev_pt_obj = None
            for i, idx in enumerate(vis_indices):
                x, y = points[idx]
                is_last = (idx == len(points) - 1)
                pt = Point(
                    id=f"app_path_pt_{generate_uuid()[:8]}",
                    x=x, y=y,
                    size=APP_PATH_TARGET_SIZE if is_last else APP_PATH_POINT_SIZE,
                    color=APP_PATH_TARGET_COLOR if is_last else APP_PATH_COLOR,
                    border_color=[1, 1, 1, 0.8] if is_last else [0, 0, 0, 0],
                    border_width=2 if is_last else 0,
                    shape='circle', show_name=False,
                )
                self.app_map_widget.map.addObject(pt)
                self._app_planned_path_objects.append(pt)

                if prev_pt_obj is not None:
                    ln = Line(
                        id=f"app_path_ln_{generate_uuid()[:8]}",
                        start=prev_pt_obj, end=pt,
                        color=APP_PATH_COLOR, width=APP_PATH_LINE_WIDTH,
                        style='solid', show_name=False,
                    )
                    self.app_map_widget.map.addObject(ln)
                    self._app_planned_path_objects.append(ln)
                prev_pt_obj = pt

            if path_data.waypoints:
                for wp in path_data.waypoints:
                    wx, wy = wp.get('x', 0), wp.get('y', 0)
                    is_stop = wp.get('type', 'PASS').upper() == 'STOP'
                    wp_pt = Point(
                        id=f"app_path_wp_{generate_uuid()[:8]}",
                        x=wx, y=wy,
                        size=APP_WP_SIZE,
                        color=APP_WP_STOP_COLOR if is_stop else APP_WP_PASS_COLOR,
                        border_color=APP_WP_BORDER, border_width=2,
                        shape='diamond', show_name=False,
                    )
                    self.app_map_widget.map.addObject(wp_pt)
                    self._app_planned_path_objects.append(wp_pt)

        def _app_on_path_planned(path_data: PathData, *args, **kwargs):
            if not path_data or path_data.path_point_count == 0:
                return
            _app_draw_planned_path(path_data)

        def _app_on_path_loaded(path_data: PathData, *args, **kwargs):
            if not path_data or not path_data.path_points:
                return
            _app_draw_planned_path(path_data)

        self.robot.position_control.events.move_to_point_started.on(_app_on_move_to_started)
        self.robot.position_control.events.move_to_point_completed.on(_app_on_move_to_completed)
        self.robot.position_control.events.move_to_point_timeout.on(_app_on_move_to_completed)
        self.robot.position_control.events.turn_to_heading_started.on(_app_on_turn_to_started)
        self.robot.position_control.events.turn_to_heading_completed.on(_app_on_turn_to_completed)
        self.robot.position_control.events.turn_to_heading_timeout.on(_app_on_turn_to_completed)
        self.robot.position_control.events.mode_changed.on(_app_on_position_mode_changed)
        self.robot.position_control.events.path_planned.on(_app_on_path_planned)
        self.robot.position_control.events.path_loaded.on(_app_on_path_loaded)
        self.robot.position_control.events.path_finished.on(lambda *a, **kw: (_app_clear_map_objects(), _app_clear_planned_path()))
        self.robot.position_control.events.path_aborted.on(lambda *a, **kw: (_app_clear_map_objects(), _app_clear_planned_path()))
        self.robot.position_control.events.path_timeout.on(lambda *a, **kw: (_app_clear_map_objects(), _app_clear_planned_path()))
        self.robot.position_control.events.path_cleared.on(lambda *a, **kw: _app_clear_planned_path())

        # --- Row 5: Pose dropdown + Go button ---
        pose_options = {pid: {'label': pid} for pid in self.manager.testbed.poses}
        if not pose_options:
            pose_options = {'default': {'label': 'default'}}
        first_pose = next(iter(pose_options))

        self.app_pose_select = MultiSelectWidget(
            widget_id='app_pose_select',
            options=pose_options,
            value=first_pose,
            title='Pose',
            title_position='left',
        )
        map_page.addObject(self.app_pose_select, row=5, column=1, width=2, height=1)

        app_go_pose_button = Button(widget_id='app_go_pose_btn', text='Go', color=[0.3, 0.5, 0.3])

        def on_go_pose_clicked(*args, **kwargs):
            pose_id = self.app_pose_select.value
            if pose_id:
                pose = self.manager.testbed.poses.get(pose_id)
                if pose is None:
                    self.logger.warning(f"Pose '{pose_id}' not found in testbed")
                    return
                self.robot.position_control.move_to_pose(x=pose.x, y=pose.y, heading=pose.psi)

        app_go_pose_button.callbacks.click.register(on_go_pose_clicked)
        map_page.addObject(app_go_pose_button, row=5, column=3, width=1, height=1)

        app_psi_zero_button = Button(widget_id='app_psi_zero_btn', text='Ψ=0', color=[0.4, 0.4, 0.4])
        app_psi_zero_button.callbacks.click.register(lambda *args, **kwargs: self.robot.position_control.turn_to(0))
        map_page.addObject(app_psi_zero_button, row=5, column=4, width=1, height=1)

        app_build_prm_button = Button(widget_id='app_build_prm_btn', text='Build PRM', color=[0.4, 0.4, 0.4])
        app_build_prm_button.callbacks.click.register(lambda *args, **kwargs: self.robot.position_control.build_prm())
        map_page.addObject(app_build_prm_button, row=5, column=5, width=2, height=1)

        # ==============================================================================================================
        # PAGE 3: DRIVE (virtual joysticks)
        # ==============================================================================================================
        drive_page = FolderPage(page_id='drive', name='Drive', rows=3, columns=8)
        self.app_folder.addPage(drive_page)

        joystick_forward = JoystickWidget(
            widget_id='joystick_forward',
            title='Forward',
            fixed_axis='vertical',
            return_to_center=True,
            continuous_updates=True,
            max_updates_per_second=20,
            show_values=True,
            deadzone=0.05,
        )
        drive_page.addObject(joystick_forward, row=1, column=1, width=3, height=3)

        joystick_turn = JoystickWidget(
            widget_id='joystick_turn',
            title='Turn',
            fixed_axis='horizontal',
            return_to_center=True,
            continuous_updates=True,
            max_updates_per_second=20,
            show_values=True,
            deadzone=0.05,
        )
        drive_page.addObject(joystick_turn, row=1, column=6, width=3, height=3)

        joystick_forward.disable()
        joystick_turn.disable()

        def joystick_enable_clicked(*args, **kwargs):
            if self.robot.interfaces.app_joystick_widgets is not None:
                joystick_forward.disable()
                joystick_turn.disable()
                self.robot.interfaces.app_joystick_widgets = None
                joystick_enable_button.updateConfig(text="Enable Joysticks")
            else:
                joystick_forward.enable(True)
                joystick_turn.enable(True)
                self.robot.interfaces.set_app_joystick_widgets({
                    'forward': joystick_forward,
                    'turn': joystick_turn,
                })
                joystick_enable_button.updateConfig(text="Disable Joysticks")

        joystick_enable_button = Button(widget_id='joystick_enable_button',
                                        text='Enable Joysticks',
                                        color=[0.5, 0.3, 0.2],
                                        callback=joystick_enable_clicked)
        drive_page.addObject(joystick_enable_button, row=1, column=4, width=2, height=1)

        # ==============================================================================================================
        # PAGE 4: EXPERIMENT (shown automatically when an experiment is loaded)
        # ==============================================================================================================
        self.app_experiment_page = FolderPage(page_id='experiment', name='Experiment', rows=4, columns=8)
        self.app_folder.addPage(self.app_experiment_page)

        # Row 1: Experiment status (ID + status in compact widget)
        self.app_exp_status_widget = StatusWidget(
            widget_id='app_exp_status_widget',
            elements={
                'id': StatusWidgetElement(label='Experiment', color=[0.5, 0.5, 0.5], status='—'),
                'status': StatusWidgetElement(label='Status', color=[0.5, 0.5, 0.5], status='Idle'),
            },
            font_size=9,
        )
        self.app_experiment_page.addObject(self.app_exp_status_widget, row=1, column=1, width=4, height=1)

        # Row 2-3: Message scroll log
        self.app_exp_message_scroll = LineScrollWidget(
            widget_id='app_exp_message_scroll',
            font_size=8,
            include_time_stamp=True,
        )
        self.app_experiment_page.addObject(self.app_exp_message_scroll, row=2, column=1, width=4, height=2)

        # Row 4: Interaction buttons
        exp_start_button = Button(widget_id='app_exp_start_btn', text='Start', color=[0.0, 0.4, 0.0])
        exp_start_button.callbacks.click.register(self.robot.core.set_start_event_robot, discard_inputs=True)
        self.app_experiment_page.addObject(exp_start_button, row=4, column=1, width=1, height=1)

        exp_stop_button = Button(widget_id='app_exp_stop_btn', text='Stop', color=[0.4, 0, 0])
        exp_stop_button.callbacks.click.register(self.robot.core.set_stop_event_robot, discard_inputs=True)
        self.app_experiment_page.addObject(exp_stop_button, row=4, column=2, width=1, height=1)

        exp_resume_button = Button(widget_id='app_exp_resume_btn', text='Resume', color=[75 / 255, 82 / 255, 56 / 255])
        exp_resume_button.callbacks.click.register(self.robot.core.set_resume_event_robot, discard_inputs=True)
        self.app_experiment_page.addObject(exp_resume_button, row=4, column=3, width=1, height=1)

        exp_repeat_button = Button(widget_id='app_exp_repeat_btn', text='Repeat', color=[59 / 255, 20 / 255, 120 / 255])
        exp_repeat_button.callbacks.click.register(self.robot.core.set_repeat_event_robot, discard_inputs=True)
        self.app_experiment_page.addObject(exp_repeat_button, row=4, column=4, width=1, height=1)

        # ==============================================================================================================
        # PAGE 5: DILC EXPERIMENT (shown when a DILC or LimboBar DILC experiment is initialized)
        # ==============================================================================================================
        self.dilc_page = DILC_ExperimentPage(robot=self.robot)
        self.app_folder.addPage(self.dilc_page.page)

        self.app.addFolder(self.app_folder)

        # Navigate to experiment page when an experiment is loaded on the robot
        self._event_listeners.append(
            self.robot.experiment_handler.events.experiment_loaded.on(self._on_experiment_loaded_app))
        self._event_listeners.append(
            self.robot.experiment_handler.events.experiment_message.on(self._on_experiment_message))

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_loaded_app(self, data=None, *args, **kwargs):
        """Switch the mobile app to the experiment page when an experiment is loaded."""
        exp_id = ''
        if isinstance(data, dict):
            exp_id = data.get('experiment_id', '')
        elif self.robot.experiment_handler.current_experiment_definition:
            exp_id = self.robot.experiment_handler.current_experiment_definition.get('id', '')

        # Update status widgets
        self.app_status_widget.elements['experiment'].status = ExperimentStatus.LOADED.value.capitalize()
        self.app_status_widget.elements['experiment'].color = [0.7, 0.5, 0.1]
        self.app_status_widget.updateConfig()

        self.exp_status_text.text = f"Loaded: {exp_id}"
        self.exp_status_text.updateConfig()

        # Update experiment page
        self.app_exp_status_widget.elements['id'].status = exp_id or '—'
        self.app_exp_status_widget.elements['id'].color = [0.7, 0.5, 0.1]
        self.app_exp_status_widget.elements['status'].status = ExperimentStatus.LOADED.value.capitalize()
        self.app_exp_status_widget.elements['status'].color = [0.7, 0.5, 0.1]
        self.app_exp_status_widget.updateConfig()

        # Navigate to experiment page
        if hasattr(self, 'app_experiment_page') and self.app_experiment_page.folder is not None:
            self.app.function('setPage', [self.app_experiment_page.uid])

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_message(self, data=None, *args, **kwargs):
        """Update experiment page with a message from the running experiment."""
        if not data:
            return
        text = data.get('text', '')
        level = data.get('level', 'info')

        message_colors = {
            'info': [0.8, 0.8, 0.8, 1],
            'warning': [0.8, 0.6, 0.1, 1],
            'error': [0.8, 0.2, 0.2, 1],
        }
        self.app_exp_message_scroll.addLine(text, color=message_colors.get(level, [0.8, 0.8, 0.8, 1]))

    # ------------------------------------------------------------------------------------------------------------------
    def on_robot_stream(self, sample: BILBO_Sample, *args, **kwargs):
        if not self._built:
            return

        if self.robot.core.tick % 100 == 0:
            # Check the static state
            robot_is_static = sample.estimation.static
            if robot_is_static:
                self.control_status_widget.elements['static'].status = 'true'
                self.control_status_widget.elements['static'].color = [0, 0.6, 0]
            else:
                self.control_status_widget.elements['static'].status = 'false'
                self.control_status_widget.elements['static'].color = [0.6, 0.4, 0.0]
            self.control_status_widget.updateConfig()

            # --- App status widget updates ---
            self.app_status_widget.elements['mode'].status = self.robot.control.mode.name
            self.app_status_widget.elements['mode'].color = CONTROL_MODE_COLORS[self.robot.control.mode]
            self.app_status_widget.elements['tic'].status = 'enabled' if sample.control.tic_enabled else 'disabled'
            self.app_status_widget.elements['tic'].color = [0, 0.5, 0] if sample.control.tic_enabled else [0.5, 0.5, 0.5]
            self.app_status_widget.elements['vic'].status = 'enabled' if sample.control.vic_enabled else 'disabled'
            self.app_status_widget.elements['vic'].color = [0, 0.5, 0] if sample.control.vic_enabled else [0.5, 0.5, 0.5]
            self.app_status_widget.elements['psi'].status = 'enabled' if sample.control.psi_enabled else 'disabled'
            self.app_status_widget.elements['psi'].color = [0, 0.5, 0] if sample.control.psi_enabled else [0.5, 0.5, 0.5]
            if robot_is_static:
                self.app_status_widget.elements['static'].status = 'true'
                self.app_status_widget.elements['static'].color = [0, 0.6, 0]
            else:
                self.app_status_widget.elements['static'].status = 'false'
                self.app_status_widget.elements['static'].color = [0.6, 0.4, 0.0]
            self.app_status_widget.updateConfig()

            if sample.control.vic_enabled:
                self.control_status_widget.elements['vic'].status = 'enabled'
                self.control_status_widget.elements['vic'].color = [0, 0.5, 0]
            else:
                self.control_status_widget.elements['vic'].status = 'disabled'
                self.control_status_widget.elements['vic'].color = [0.5, 0.5, 0.5]

            if sample.control.psi_enabled:
                self.control_status_widget.elements['psi'].status = 'enabled'
                self.control_status_widget.elements['psi'].color = [0, 0.5, 0]
            else:
                self.control_status_widget.elements['psi'].status = 'disabled'
                self.control_status_widget.elements['psi'].color = [0.5, 0.5, 0.5]
            self.control_status_widget.updateConfig()

            # Update estimation status (dead-reckoning vs tracked)
            is_dead_reckoning = sample.estimation.is_dead_reckoning
            if is_dead_reckoning:
                self.estimation_status_widget.elements['tracking'].status = 'Dead-Reckoning'
                self.estimation_status_widget.elements['tracking'].color = [0.6, 0.2, 0.2]  # Red
            else:
                self.estimation_status_widget.elements['tracking'].status = 'Tracked'
                self.estimation_status_widget.elements['tracking'].color = [0.2, 0.6, 0.2]  # Green
            self.estimation_status_widget.updateConfig()

            # Experiment progress is updated via event callbacks (_on_experiment_started, etc.)

        if self.robot.core.tick % 200 == 0:
            # Update the overview widgets
            voltage = sample.sensors.power.bat_voltage
            cells = self.robot.config.electronics.battery_cells
            self.battery_indicator.setValue(percentage=lipo_soc(voltage=voltage, cells=cells), voltage=voltage)

            # Connection
            self.connection_strength_indicator.setValue(
                'high' if sample.general.connection_strength > 85 else
                'medium' if sample.general.connection_strength > 30 else
                'low'
            )

            # Internet
            self.internet_indicator.setValue(sample.general.internet_connected)

            # Pi status (temperature + throttle)
            temp = sample.general.rpi_temperature
            throttle = sample.general.rpi_throttle
            if temp > 0:
                self.pi_status_widget.elements['temp'].status = f"{temp:.1f} °C"
                if temp >= 80:
                    self.pi_status_widget.elements['temp'].color = [0.7, 0.1, 0.1]
                elif temp >= 70:
                    self.pi_status_widget.elements['temp'].color = [0.7, 0.5, 0.0]
                else:
                    self.pi_status_widget.elements['temp'].color = [0, 0.5, 0]

            if throttle > 0:
                flags = []
                if throttle & (1 << 0): flags.append("UV")
                if throttle & (1 << 1): flags.append("Freq")
                if throttle & (1 << 2): flags.append("Throttled")
                if throttle & (1 << 3): flags.append("TempLim")
                self.pi_status_widget.elements['throttle'].status = ', '.join(flags) if flags else 'OK'
                self.pi_status_widget.elements['throttle'].color = [0.7, 0.1, 0.1] if flags else [0, 0.5, 0]
            else:
                self.pi_status_widget.elements['throttle'].status = 'OK'
                self.pi_status_widget.elements['throttle'].color = [0, 0.5, 0]
            self.pi_status_widget.updateConfig()

            # Joystick assigned?
            if self.joystick_control is not None:
                self.joystick_indicator.setValue(self.joystick_control.robotIsAssigned(self.robot) is not None)
            else:
                self.joystick_indicator.setValue(False)

            # --- App battery + connection + temp + joystick ---
            self.app_battery_indicator.setValue(percentage=lipo_soc(voltage=voltage, cells=cells), voltage=voltage)
            self.app_connection_indicator.setValue(
                'high' if sample.general.connection_strength > 85 else
                'medium' if sample.general.connection_strength > 30 else
                'low'
            )

            if temp > 0:
                self.app_temp_widget.elements['temp'].status = f"{temp:.0f} °C"
                if temp >= 80:
                    self.app_temp_widget.elements['temp'].color = [0.7, 0.1, 0.1]
                elif temp >= 70:
                    self.app_temp_widget.elements['temp'].color = [0.7, 0.5, 0.0]
                else:
                    self.app_temp_widget.elements['temp'].color = [0, 0.5, 0]
                self.app_temp_widget.updateConfig()

            if self.joystick_control is not None:
                self.app_joystick_indicator.setValue(self.joystick_control.robotIsAssigned(self.robot) is not None)
            else:
                self.app_joystick_indicator.setValue(False)

        # Update the states digital numbers (desktop GUI)
        self.x_digital_number.value = sample.estimation.state.x
        self.y_digital_number.value = sample.estimation.state.y
        self.v_digital_number.value = sample.estimation.state.v

        # Update app digital numbers (guard: build_folder may still be running)
        if hasattr(self, 'app_psi_number'):
            self.app_v_number_main.value = sample.estimation.state.v
            self.app_x_number.value = sample.estimation.state.x
            self.app_y_number.value = sample.estimation.state.y
            self.app_theta_number.value = np.rad2deg(sample.estimation.state.theta)
            self.app_psi_number.value = np.rad2deg(sample.estimation.state.psi)

        self.theta_digital_number.value = np.rad2deg(sample.estimation.state.theta) if self.overview_page_data[
                                                                                           'theta_digital_number_format'] == 'grad' else sample.estimation.state.theta
        self.theta_dot_digital_number.value = np.rad2deg(sample.estimation.state.theta_dot) if self.overview_page_data[
                                                                                                   'theta_dot_digital_number_format'] == 'grad' else sample.estimation.state.theta_dot
        self.psi_digital_number.value = (sample.estimation.state.psi) if self.overview_page_data[
                                                                             'psi_digital_number_format'] == 'rad' else np.rad2deg(
            sample.estimation.state.psi)
        self.psi_dot_digital_number.value = (sample.estimation.state.psi_dot) if self.overview_page_data[
                                                                                     'psi_dot_digital_number_format'] == 'rad' else np.rad2deg(
            sample.estimation.state.psi_dot)

        # Update gyro readings (convert to deg/s)
        self.gyro_x_number.value = np.rad2deg(sample.lowlevel.sensors.gyr.x)
        self.gyro_y_number.value = np.rad2deg(sample.lowlevel.sensors.gyr.y)
        self.gyro_z_number.value = np.rad2deg(sample.lowlevel.sensors.gyr.z)

        # Update accelerometer readings
        self.acc_x_number.value = sample.lowlevel.sensors.acc.x
        self.acc_y_number.value = sample.lowlevel.sensors.acc.y
        self.acc_z_number.value = sample.lowlevel.sensors.acc.z

        self.timeseries_v.set_value(sample.estimation.state.v)
        self.timeseries_theta.set_value(np.rad2deg(sample.estimation.state.theta))
        self.theta_dot_timeseries.set_value(np.rad2deg(sample.estimation.state.theta_dot))
        self.psi_plot_timeseries.set_value(np.rad2deg(sample.estimation.state.psi))
        self.psi_dot_timeseries.set_value(np.rad2deg(sample.estimation.state.psi_dot))
        self.x_timeseries.set_value(sample.estimation.state.x)
        self.y_timeseries.set_value(sample.estimation.state.y)

        # Update map agent position from robot estimation state
        tick = self.robot.core.tick
        if self._first_stream_tick is None:
            self._first_stream_tick = tick
        if (tick - self._first_stream_tick) % 5 == 0:
            self.robot_map_agent.update(
                x=sample.estimation.state.x,
                y=sample.estimation.state.y,
                psi=sample.estimation.state.psi
            )

            # Set agent color based on tracking source (resent every tick to guard against missed updates)
            is_tracked = not sample.estimation.is_dead_reckoning
            color = [0.2, 0.6, 0.2] if is_tracked else [0.6, 0.2, 0.2]
            self.robot_map_agent.updateConfig(color=color)

            # Update app map agent
            if hasattr(self, 'app_map_agent'):
                self.app_map_agent.update(
                    x=sample.estimation.state.x,
                    y=sample.estimation.state.y,
                    psi=sample.estimation.state.psi
                )
                self.app_map_agent.updateConfig(color=color)

    # ------------------------------------------------------------------------------------------------------------------
    def on_new_tracker_sample(self, sample, *args, **kwargs):
        if not self._built:
            return

        # Update obstacle positions on map
        for obs_id, map_obj in self._obstacle_map_objects.items():
            if obs_id in self.manager.testbed.obstacles:
                obs = self.manager.testbed.obstacles[obs_id]
                s = obs.state
                map_obj.update(x=s.x, y=s.y, psi=s.psi)

    # ------------------------------------------------------------------------------------------------------------------
    def on_control_mode_changed(self, mode: BILBO_Control_Mode, *args, **kwargs):
        if not self._built:
            return
        # Overview Status Widget
        self.general_status_widget.elements['mode'].status = mode.name
        self.general_status_widget.elements['mode'].color = CONTROL_MODE_COLORS[mode]
        self.general_status_widget.updateConfig()

        self.control_status_widget.elements['mode'].status = mode.name
        self.control_status_widget.elements['mode'].color = CONTROL_MODE_COLORS[mode]
        self.control_status_widget.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def on_tic_mode_changed(self, mode: bool, *args, **kwargs):
        self.control_status_widget.elements['tic'].status = 'enabled' if mode else 'disabled'
        self.control_status_widget.elements['tic'].color = [0, 0.5, 0] if mode else [0.5, 0.5, 0.5]
        self.control_status_widget.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def on_vic_mode_changed(self, mode: bool):
        self.control_status_widget.elements['vic'].status = 'enabled' if mode else 'disabled'
        self.control_status_widget.elements['vic'].color = [0, 0.5, 0] if mode else [0.5, 0.5, 0.5]
        self.control_status_widget.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def on_psi_mode_changed(self, mode: bool, *args, **kwargs):
        self.control_status_widget.elements['psi'].status = 'enabled' if mode else 'disabled'
        self.control_status_widget.elements['psi'].color = [0, 0.5, 0] if mode else [0.5, 0.5, 0.5]
        self.control_status_widget.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_started(self, data, *args, **kwargs):
        """Event callback: experiment has started."""
        exp_def = self.robot.experiment_handler.current_experiment_definition
        exp_id = ''
        if exp_def and isinstance(exp_def, dict):
            exp_id = exp_def.get('id', '') or exp_def.get('name', '')

        self.exp_status_text.text = f"Running: {exp_id}"
        self.exp_action_text.text = ''
        self.exp_status_text.updateConfig()
        self.exp_action_text.updateConfig()

        # Update app experiment status
        self.app_status_widget.elements['experiment'].status = ExperimentStatus.RUNNING.value.capitalize()
        self.app_status_widget.elements['experiment'].color = [0.2, 0.5, 0.8]
        self.app_status_widget.updateConfig()

        # Update experiment page status
        self.app_exp_status_widget.elements['status'].status = ExperimentStatus.RUNNING.value.capitalize()
        self.app_exp_status_widget.elements['status'].color = [0.2, 0.5, 0.8]
        self.app_exp_status_widget.updateConfig()

        # Enter playback mode in the designer and dim all actions
        if hasattr(self, 'experiment_designer'):
            actions = self.robot.experiment_handler.experiment_actions
            action_ids = [a.get('id') for a in actions if a.get('id')]
            self.experiment_designer.set_mode('playback')
            self.experiment_designer.set_action_states({aid: 'dimmed' for aid in action_ids})

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_finished(self, data=None, *args, status=ExperimentStatus.FINISHED, **kwargs):
        """Event callback: experiment finished, errored, or timed out."""
        self.exp_status_text.text = 'Idle'
        self.exp_action_text.text = ''
        self.exp_status_text.updateConfig()
        self.exp_action_text.updateConfig()

        # Update app experiment status
        self.app_status_widget.elements['experiment'].status = 'Idle'
        self.app_status_widget.elements['experiment'].color = [0.5, 0.5, 0.5]
        self.app_status_widget.updateConfig()

        # Update experiment page status
        status_colors = {
            ExperimentStatus.FINISHED: [0.2, 0.8, 0.2],
            ExperimentStatus.ERROR: [0.8, 0.2, 0.2],
            ExperimentStatus.TIMEOUT: [0.8, 0.5, 0.1],
            ExperimentStatus.ABORTED: [0.8, 0.5, 0.1],
        }
        self.app_exp_status_widget.elements['status'].status = status.value.capitalize()
        self.app_exp_status_widget.elements['status'].color = status_colors.get(status, [0.5, 0.5, 0.5])
        self.app_exp_status_widget.updateConfig()

        # Exit playback mode in the designer
        if hasattr(self, 'experiment_designer'):
            self.experiment_designer.clear_action_states()
            self.experiment_designer.set_mode('edit')

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _short_params(params: dict) -> str:
        """Return a compact one-line summary of action params for the progress bar."""
        if not params:
            return ''
        parts = []
        for k, v in params.items():
            if isinstance(v, (dict, list)):
                continue  # skip bulky nested values
            parts.append(f"{k}={v}")
        return ', '.join(parts)

    def _on_action_started(self, data, *args, **kwargs):
        """Event callback: an experiment action has started."""
        if not isinstance(data, dict):
            return
        action_id = data.get('action_id', '')
        action_type = data.get('action_type', action_id)

        # Look up params from the action summary
        params_str = ''
        for a in self.robot.experiment_handler.experiment_actions:
            if a.get('id') == action_id:
                params_str = self._short_params(a.get('params', {}))
                break

        label = f"{action_type}  {params_str}" if params_str else action_type
        self.exp_action_text.text = f"{action_id}: {label}"
        self.exp_action_text.updateConfig()

        # Highlight active action in the designer
        if hasattr(self, 'experiment_designer'):
            self.experiment_designer.set_action_state(action_id, 'active')

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_finished(self, data, *args, **kwargs):
        """Event callback: an experiment action has finished."""
        if not isinstance(data, dict):
            return
        action_id = data.get('action_id', '')
        action_status = data.get('action_status', '')

        if hasattr(self, 'experiment_designer'):
            state = 'error' if action_status == 'error' else 'completed'
            self.experiment_designer.set_action_state(action_id, state)

    # ------------------------------------------------------------------------------------------------------------------
    def _run_experiment_from_picker(self):
        """Open a native file picker and show experiment confirmation popup."""
        from core.utils.filepicker import pick_file
        file_path = pick_file(
            title="Select experiment file",
            allowed_extensions=['.yaml', '.yml', '.json'],
        )
        if file_path is None:
            return

        try:
            with open(file_path, 'r') as f:
                if file_path.lower().endswith(('.yml', '.yaml')):
                    definition = yaml_module.safe_load(f)
                else:
                    import json
                    definition = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load experiment file: {e}")
            return

        self._show_experiment_popup(definition, source='file', file_path=file_path)

    # ------------------------------------------------------------------------------------------------------------------
    def _count_actions(self, actions: list) -> int:
        """Count total actions recursively (including nested groups/loops)."""
        count = 0
        for action in actions:
            count += 1
            sub_actions = action.get('actions', [])
            if isinstance(sub_actions, list):
                count += self._count_actions(sub_actions)
        return count

    # ------------------------------------------------------------------------------------------------------------------
    def _show_experiment_popup(self, definition: dict, source: str, file_path: str = None,
                               yaml_string: str = None):
        """Show a confirmation popup before starting an experiment.

        Args:
            definition: Parsed experiment definition dict.
            source: 'file' or 'yaml_string'.
            file_path: Path to experiment file (if source='file').
            yaml_string: Raw YAML string (if source='yaml_string').
        """
        import os

        # Ensure yaml_string is available for bundle export
        if yaml_string is None:
            yaml_string = yaml_module.dump(definition, default_flow_style=False, sort_keys=False)

        exp_id = definition.get('id', 'unknown')
        exp_description = definition.get('description', '')
        exp_label = definition.get('label', exp_id)
        actions = definition.get('actions', [])
        num_actions = self._count_actions(actions)
        exp_timeout = definition.get('timeout')

        # Determine default output path
        if file_path:
            default_output = os.path.dirname(os.path.abspath(file_path))
        elif self.application_settings.paths.experiments:
            default_output = os.path.abspath(self.application_settings.paths.experiments)
        else:
            default_output = ''

        # Build info lines
        info_parts = [f"Actions: {num_actions}"]
        if exp_timeout:
            info_parts.append(f"Timeout: {exp_timeout}s")
        action_types = [a.get('type', '?') for a in actions]
        summary = ', '.join(action_types[:8])
        if len(action_types) > 8:
            summary += f', ... (+{len(action_types) - 8})'

        # --- Build popup (8 rows x 8 cols) ---
        popup = Popup(
            popup_id=f'exp_confirm_{id(definition)}',
            type='dialog',
            title='Start Experiment',
            closeable=True,
            minimizable=False,
            size=[520, 340],
            grid=[8, 8],
            disable_gui=True,
        )

        # Row 1: experiment name
        id_label = TextWidget(widget_id='exp_info_id', text=exp_label,
                              font_size=14, font_weight='bold',
                              horizontal_alignment='left')
        popup.group.addWidget(id_label, row=1, column=1, width=8, height=1)

        # Row 2: description (or actions info if no description)
        if exp_description:
            desc_label = TextWidget(widget_id='exp_info_desc', text=exp_description,
                                    font_size=11, horizontal_alignment='left',
                                    text_color=[0.7, 0.7, 0.7])
            popup.group.addWidget(desc_label, row=2, column=1, width=8, height=1)
            info_row = 3
        else:
            info_row = 2

        # Actions info + summary
        info_label = TextWidget(widget_id='exp_info_actions',
                                text='  |  '.join(info_parts),
                                font_size=11, horizontal_alignment='left')
        popup.group.addWidget(info_label, row=info_row, column=1, width=8, height=1)

        summary_label = TextWidget(widget_id='exp_info_summary', text=summary,
                                   font_size=10, horizontal_alignment='left',
                                   text_color=[0.5, 0.5, 0.5])
        popup.group.addWidget(summary_label, row=info_row + 1, column=1, width=8, height=1)

        # Row 5: save checkbox + bundle checkbox
        save_checkbox = CheckboxWidget(widget_id='exp_save_checkbox', value=False,
                                       title='Save experiment data')
        popup.group.addWidget(save_checkbox, row=5, column=1, width=4, height=1)

        bundle_checkbox = CheckboxWidget(widget_id='exp_bundle_checkbox', value=False,
                                          title='Save as bundle (.zip)')
        popup.group.addWidget(bundle_checkbox, row=5, column=5, width=4, height=1)
        bundle_checkbox.disable()

        # Row 6: output path input + browse button
        output_input = InputWidget(
            widget_id='exp_output_path',
            value=default_output,
            title='Output folder:',
            title_position='left',
            inputFieldAlign='left',
            inputFieldFontSize=10,
            commit_on_blur=True,
        )
        popup.group.addWidget(output_input, row=6, column=1, width=7, height=1)
        output_input.disable()

        browse_button = Button(widget_id='exp_browse_btn', text='...', color=[0.3, 0.3, 0.4])
        popup.group.addWidget(browse_button, row=6, column=8, width=1, height=1)
        browse_button.disable()

        def on_browse(*args, **kwargs):
            def do_pick():
                from core.utils.filepicker import pick_directory
                current = output_input.value.strip() if output_input.value else None
                folder = pick_directory(title='Select output folder', initial_dir=current or None)
                if folder:
                    output_input.value = folder
            threading.Thread(target=do_pick, daemon=True).start()

        browse_button.callbacks.click.register(on_browse)

        # Wire checkbox to enable/disable output controls
        def on_save_changed(value, *args, **kwargs):
            output_input.enable(bool(value))
            browse_button.enable(bool(value))
            bundle_checkbox.enable(bool(value))

        save_checkbox.callbacks.changed.register(on_save_changed)

        # Row 8: buttons
        start_button = Button(widget_id='exp_start_btn', text='Start', color=[0.2, 0.5, 0.2])
        cancel_button = Button(widget_id='exp_cancel_btn', text='Cancel', color=[0.4, 0.2, 0.2])
        popup.group.addWidget(start_button, row=8, column=6, width=1, height=1)
        popup.group.addWidget(cancel_button, row=8, column=7, width=1, height=1)

        def on_start(*args, **kwargs):
            popup.close()
            save = save_checkbox.value
            bundle = bundle_checkbox.value if save else False
            output = output_input.value.strip() if save else None
            if output == '':
                output = None

            def run():
                exp_source_dir = None
                if source == 'file':
                    exp_source_dir = os.path.dirname(os.path.abspath(file_path))
                    result = self.robot.experiment_handler.run_experiment(
                        definition,
                        experiment_file_folder=output,
                        source_dir=exp_source_dir,
                        blocking=True,
                    )
                else:
                    result = self.robot.experiment_handler.run_experiment_from_yaml_string(
                        yaml_string, output=output, blocking=True
                    )

                if bundle and output and result is not None:
                    self.robot.experiment_handler.create_experiment_bundle(
                        output_dir=output,
                        experiment_data=result,
                        yaml_string=yaml_string,
                        source_dir=exp_source_dir,
                    )

            threading.Thread(target=run, daemon=True).start()

        def on_cancel(*args, **kwargs):
            popup.close()

        start_button.callbacks.click.register(on_start)
        cancel_button.callbacks.click.register(on_cancel)

        self.gui.openPopup(popup)

    # ------------------------------------------------------------------------------------------------------------------
    def on_dilc_experiment_initialized(self, data, *args, **kwargs):
        self.logger.info("DILC experiment initialized — opening DILC app")
        dilc_experiment = data.get('experiment')
        if dilc_experiment is None:
            self.logger.error("No DILC experiment handle in event data")
            return
        self.dilc_app = DILC_APP(
            gui=self.gui,
            robot=self.robot,
            experiment=dilc_experiment,
        )
        self.dilc_app.open(self.gui)

        # Bind and navigate to DILC page in the app
        if hasattr(self, 'dilc_page'):
            self.dilc_page.bind_experiment(dilc_experiment)
            self.app.function('setPage', [self.dilc_page.page.uid])

    # ------------------------------------------------------------------------------------------------------------------
    def on_limbobar_dilc_experiment_initialized(self, data, *args, **kwargs):
        self.logger.info("LimboBar DILC experiment initialized — opening LimboBar DILC app")
        experiment = data.get('experiment')
        if experiment is None:
            self.logger.error("No LimboBar DILC experiment handle in event data")
            return
        self.limbobar_dilc_app = LimboBar_DILC_APP(
            gui=self.gui,
            robot=self.robot,
            experiment=experiment,
        )
        self.limbobar_dilc_app.open(self.gui)

        # Bind and navigate to DILC page in the app
        if hasattr(self, 'dilc_page'):
            self.dilc_page.bind_experiment(experiment)
            self.app.function('setPage', [self.dilc_page.page.uid])

    # ------------------------------------------------------------------------------------------------------------------
    def _initialize_control_table_from_config(self):
        """Populate all control table cells with current values from robot."""

        def do_init():
            try:
                config = self.robot.control.get_control_config()
                if config is None:
                    self.logger.warning("Could not read control config for initialization")
                    return
                self._control_initial_config = copy.deepcopy(config)
                self._sync_control_table_values(config)
            except Exception as e:
                self.logger.warning(f"Failed to initialize control table: {e}")

        set_timeout(do_init, 1.0)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_control_config_changed(self, *args, **kwargs):
        """Called when the robot signals that its control config has changed."""
        try:
            config = self.robot.control.get_control_config()
            if config is not None:
                self._sync_control_table_values(config)
        except Exception as e:
            self.logger.debug(f"Control config sync failed: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def _sync_control_table_values(self, config: BILBO_ControlConfig):
        """Update all control table cells from a config object."""
        for row_key, (row, config_path, _) in self._control_row_map.items():
            # Skip cells with pending changes in manual mode
            if not self._control_auto_write and row_key in self._control_pending_changes:
                continue
            try:
                value = self._resolve_config_path(config, config_path)
                formatted = f"{value:.6g}" if isinstance(value, float) else str(value)
                row.cells['value'].set(formatted)
            except Exception:
                pass

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _resolve_config_path(obj, path: str):
        """Navigate a dot-separated path on a dataclass/object. Supports list indices (e.g. 'K.0')."""
        for part in path.split('.'):
            if isinstance(obj, (list, tuple)) and part.isdigit():
                obj = obj[int(part)]
            else:
                obj = getattr(obj, part)
        return obj

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _set_config_path(obj, path: str, value):
        """Set a value at a dot-separated path on a dataclass/object. Supports list indices."""
        parts = path.split('.')
        for part in parts[:-1]:
            if isinstance(obj, (list, tuple)) and part.isdigit():
                obj = obj[int(part)]
            else:
                obj = getattr(obj, part)
        last = parts[-1]
        if isinstance(obj, list) and last.isdigit():
            obj[int(last)] = value
        else:
            setattr(obj, last, value)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_control_param_edit(self, value, row_key, row_id, *args, **kwargs):
        """Called when user edits a value cell in the control config table."""
        row, config_path, setter_key = self._control_row_map[row_key]

        # Validate as float
        try:
            float_value = float(value)
        except (ValueError, TypeError):
            self.control_config_table.reject_cell(row_id, 'value')
            return

        formatted = f"{float_value:.6g}"

        if not self._control_auto_write:
            # MANUAL mode: buffer the change, mark cell dirty
            self._control_pending_changes[row_key] = float_value
            self.control_config_table.accept_cell(row_id, 'value', formatted)
            self.control_config_table.mark_cell_dirty(row_id, 'value')
            return

        # AUTO mode: immediately write to robot
        try:
            config = self.robot.control.get_control_config()
            if config is None:
                self.control_config_table.reject_cell(row_id, 'value')
                return

            self._set_config_path(config, config_path, float_value)
            self._dispatch_control_setter(config, setter_key)

            self.control_config_table.accept_cell(row_id, 'value', formatted)

        except Exception as e:
            self.logger.warning(f"Failed to apply control param edit ({row_key}): {e}")
            self.control_config_table.reject_cell(row_id, 'value')

    # ------------------------------------------------------------------------------------------------------------------
    def _dispatch_control_setter(self, config: BILBO_ControlConfig, setter_key: str):
        """Dispatch a control config section to the appropriate robot setter."""
        match setter_key:
            case 'general':
                self.robot.control.set_general_config(
                    max_wheel_torque=config.general.max_wheel_torque,
                    max_wheel_speed=config.general.max_wheel_speed,
                )
            case 'tic':
                self.robot.control.set_tic_config(config.balancing_control.tic)
            case 'vic':
                self.robot.control.set_vic_config(config.balancing_control.vic)
            case 'psi':
                self.robot.control.set_psi_config(config.balancing_control.psi)
            case 'statefeedback':
                # Reconstruct full 8-element K: row 2 mirrors row 1 with negated psi_dot
                K = config.balancing_control.K
                k_v, k_theta, k_theta_dot, k_psi_dot = K[0], K[1], K[2], K[3]
                full_K = [k_v, k_theta, k_theta_dot, k_psi_dot,
                          k_v, k_theta, k_theta_dot, -k_psi_dot]
                config.balancing_control.K = full_K
                self.robot.control.set_statefeedback_gain(full_K)
            case 'vel_fwd_pid':
                self.robot.control.set_velocity_control_config_v(config.velocity_control.v.pid)
            case 'vel_fwd_ff':
                self.robot.control.set_velocity_ff_config_v(config.velocity_control.v.feedforward)
            case 'vel_turn_pid':
                self.robot.control.set_velocity_control_config_psi_dot(config.velocity_control.psidot.pid)
            case 'vel_turn_ff':
                self.robot.control.set_velocity_ff_config_psi_dot(config.velocity_control.psidot.feedforward)
            case 'position':
                self.robot.control.set_position_control_config(config.position_control)

    # ------------------------------------------------------------------------------------------------------------------
    def _send_pending_control_changes(self):
        """Send all buffered pending changes to the robot."""
        if not self._control_pending_changes:
            return

        try:
            config = self.robot.control.get_control_config()
            if config is None:
                self.logger.warning("Could not fetch control config for sending pending changes")
                return

            # Apply all pending values to the config
            affected_setters = set()
            for row_key, float_value in self._control_pending_changes.items():
                row, config_path, setter_key = self._control_row_map[row_key]
                self._set_config_path(config, config_path, float_value)
                affected_setters.add(setter_key)

            # Dispatch each affected setter once
            for setter_key in affected_setters:
                self._dispatch_control_setter(config, setter_key)

            # Clear dirty marks
            for row_key in self._control_pending_changes:
                row, _, _ = self._control_row_map[row_key]
                self.control_config_table.mark_cell_clean(row.id, 'value')

            self._control_pending_changes.clear()
            self.logger.info("Sent pending control config changes to robot")

        except Exception as e:
            self.logger.warning(f"Failed to send pending control changes: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def _restore_initial_control_config(self):
        """Restore the control config to the snapshot taken when the robot first connected."""
        if self._control_initial_config is None:
            self.logger.warning("No initial control config available to restore")
            return

        try:
            config = copy.deepcopy(self._control_initial_config)

            # Dispatch all setter keys to push the full initial config to the robot
            for setter_key in {'general', 'statefeedback', 'tic', 'vic', 'psi', 'vel_fwd_pid', 'vel_fwd_ff',
                               'vel_turn_pid', 'vel_turn_ff', 'position'}:
                self._dispatch_control_setter(config, setter_key)

            # Clear any pending changes and dirty marks
            for row_key in list(self._control_pending_changes.keys()):
                row, _, _ = self._control_row_map[row_key]
                self.control_config_table.mark_cell_clean(row.id, 'value')
            self._control_pending_changes.clear()

            # Sync the table with the restored config
            self._sync_control_table_values(config)
            self.logger.info("Restored initial control config")

        except Exception as e:
            self.logger.warning(f"Failed to restore initial control config: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def _copy_control_config_yaml(self):
        try:
            config = self.robot.control.get_control_config()
            if config is None:
                self.logger.warning("Could not read control config from robot")
                return
            config_dict = dataclasses.asdict(config)

            # Block style for dicts, flow style for lists of scalars (like K matrix)
            class BlockDumper(yaml_module.SafeDumper):
                pass

            def represent_dict(dumper, data):
                return dumper.represent_mapping('tag:yaml.org,2002:map', data.items(), flow_style=False)

            def represent_list(dumper, data):
                flow = all(isinstance(v, (int, float, bool, str)) for v in data)
                return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=flow)

            BlockDumper.add_representer(dict, represent_dict)
            BlockDumper.add_representer(list, represent_list)

            yaml_str = yaml_module.dump(config_dict, Dumper=BlockDumper, sort_keys=False)
            self.gui.function(function_name='copyToClipboard', args={'text': yaml_str}, spread_args=False)
            self.logger.info("Control config YAML copied to clipboard")
        except Exception as e:
            self.logger.warning(f"Failed to copy control config: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        # Stop all event listeners to prevent duplicate callbacks on reconnect
        for listener in getattr(self, '_event_listeners', []):
            try:
                listener.stop()
            except Exception:
                pass
        self._event_listeners = []

        try:
            self.gui.categories['robots'].removeCategory(self.category)
        except Exception:
            pass

        try:
            self.app.removeFolder(self.app_folder)
        except Exception:
            pass

        for plot in self.plots:
            # plot.
            ...
        self.map_widget.onDelete()
