import dataclasses

import qmt

from core.utils.logging_utils import Logger
from core.utils.timecode.timecode import Timecode
from core.utils.timecode.timecode_server import TimecodeServerStatus
from extensions.libs.babylon.src.babylon import BabylonVisualization
from extensions.libs.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.libs.babylon.src.lib.objects.box.box import Box
from extensions.libs.babylon.src.lib.objects.drawings.path import PathDrawing
from extensions.libs.babylon.src.lib.objects.drawings.points import PointsDrawing
from robots.bilbo.robot.bilbo_position_control import PathData
from robots.bilbo.tools.babylon.scenarios.arena import ArenaScenario
from robots.bilbo.tools.babylon.scenarios.lab import LabScenario
from robots.bilbo.tools.babylon.scenarios.track import TrackScenario
from extensions.gui.src.gui import Page
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.indicators import CircleIndicator
from extensions.gui.src.lib.objects.python.bilbo_mode import BilboModeWidget
from extensions.gui.src.lib.objects.python.buttons import MultiStateButton
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget, DigitalClockWidget
from extensions.gui.src.lib.objects.python.sliders import ClassicSliderWidget
from extensions.gui.src.lib.objects.python.table import Table, TextColumn, IndicatorColumn, NumberColumn
from extensions.gui.src.lib.objects.python.text import TextWidget, StatusWidget, StatusWidgetElement
from extensions.gui.src.lib.objects.python.text_input import InputWidget
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from robots.bilbo.robot.bilbo_utilities import CONTROL_MODE_COLORS
from robots.bilbo.testbed.objects import TestbedBILBO, RealTestbedBILBO, BoxObstacle
from robots.bilbo.testbed.testbed_manager import TestbedManager

PATH_WIDTH = 0.03
PATH_ENDPOINT_SIZE = 0.04
PATH_START_COLOR = [0.3, 0.9, 0.3, 0.9]
PATH_END_COLOR = [1.0, 0.3, 0.3, 0.9]


# ======================================================================================================================
class BILBO_GUI_OverviewPage:
    page: Page
    manager: TestbedManager

    @dataclasses.dataclass
    class RobotContainer:
        robot: TestbedBILBO
        babylon: BabylonBilbo
        group: Widget_Group | None = None
        status_widget: StatusWidget | None = None
        mode_widget: BilboModeWidget | None = None

    robots: dict[str, RobotContainer]
    _obstacle_babylon_objects: dict[str, Box]

    def __init__(self, manager: TestbedManager):
        self.manager = manager

        self.logger = Logger("Testbed Page")
        self.page = Page(id='testbed_page', name='Testbed')
        self.robots = {}
        self._obstacle_babylon_objects = {}
        self.babylon_visualization = None
        self._selected_robot: str | None = None
        self._path_objects: dict[str, list] = {}  # robot_id → [PathDrawing, PointsDrawing, ...]
        self._data_source = 'OptiTrack'  # 'OptiTrack' or 'Robots'

        self._buildPage()

        self.manager.events.new_bilbo.on(self._on_new_testbed_robot)
        self.manager.events.bilbo_removed.on(self._on_testbed_robot_disconnected)
        self.manager.events.new_tracker_sample.on(self._on_new_tracker_sample)
        self.manager.events.initialized.on(self._on_testbed_initialized)
        self.manager.testbed.events.obstacle_added.on(self._on_obstacle_added)
        self.manager.testbed.events.obstacle_removed.on(self._on_obstacle_removed)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildPage(self):
        # Statuses
        # Make a group
        # status_group = Widget_Group(group_id='status_group', title='Status', rows=1, columns=1, show_title=True)
        # self.page.addWidget(status_group, row=1, column=1, width=8, height=8)

        # Build tracker overview (disabled if OptiTrack not enabled)
        self._build_tracker_overview()

        # Build timecode group (disabled if timecode not enabled)
        self._build_timecode()

        # Babylon group (full height right side)
        babylon_group = Widget_Group(
            group_id='babylon_group',
            title='3D View',
            rows=18,
            columns=21,
            show_title=True
        )
        self.page.addWidget(babylon_group, row=1, column=30, height=18, width=21)

        self.babylon_widget = BabylonWidget(widget_id='babylon_widget')
        babylon_group.addWidget(self.babylon_widget, row=1, column=1, height=13, width=21)

        # Data source toggle
        self._data_source_button = MultiStateButton(
            id='data_source_toggle',
            states=['OptiTrack', 'Robots'],
            current_state='OptiTrack',
            color=[[0.15, 0.25, 0.35], [0.25, 0.2, 0.15]],
            title='Data Source',
            fontSize=10,
        )
        babylon_group.addWidget(self._data_source_button, row=14, column=1, height=2, width=3)
        self._data_source_button.callbacks.click.register(self._on_data_source_click)
        self._data_source_button.callbacks.indicatorClick.register(self._on_data_source_indicator_click)

        # Build extensions group (individual widgets disabled based on settings)
        self._build_display_group()

        # self.joystick_manager_widget = JoystickAssignmentWidget(
        #     joysticks= [
        #         {
        #             'id': 'joy1',
        #             'name': 'Joystick 1'
        #         },
        #         {
        #             'id': 'joy2',
        #             'name': 'Joystick 2'
        #         },
        #
        #     ],
        #     robots = [
        #         {
        #             'id': 'bilbo1',
        #             'name': 'BILBO 1'
        #         },
        #         {
        #             'id': 'bilbo2',
        #             'name': 'BILBO 2'
        #         },
        #         {
        #             'id': 'bilbo3',
        #             'name': 'BILBO 3'
        #         },
        #         {
        #             'id': 'bilbo4',
        #             'name': 'BILBO 4'
        #         },
        #         {
        #             'id': 'bilbo5',
        #             'name': 'BILBO 5'
        #         },
        #
        #     ]
        # )
        #
        # self.page.addWidget(self.joystick_manager_widget, row=5, width=14, height=14)

    # ------------------------------------------------------------------------------------------------------------------
    def _build_timecode(self):
        """Build the timecode group. Disabled if timecode is not enabled in settings."""
        timecode_enabled = self.manager.settings.extensions.timecode

        timecode_group = Widget_Group(group_id='timecode_group',
                                      title='Timecode',
                                      rows=1,
                                      columns=4,
                                      fill_empty=True,
                                      show_title=True)
        timecode_status_indicator = CircleIndicator()
        timecode_group.addWidget(timecode_status_indicator, row=1, column=1, width=1, height=1)
        timecode_fps = DigitalNumberWidget(increment=0.01, min_value=0, max_value=100, value=0,
                                           show_unused_digits=False)
        timecode_group.addWidget(timecode_fps, row=1, column=2, width=1, height=1)
        timecode_clock = DigitalClockWidget(display_format="hh:mm:ss")
        timecode_group.addWidget(timecode_clock, row=1, column=3, width=2, height=1)

        self.page.addWidget(timecode_group, row=13, column=1, width=10, height=2)

        # If timecode is not enabled, disable the group and skip callback registration
        if not timecode_enabled:
            timecode_group.disable()
            return

        def initialize_timecode(*args, **kwargs):
            fps = self.manager.timecode_server.get_fps()
            timecode_fps.value = fps
            timecode_status_indicator.updateConfig(color=[0, 0.8, 0])
            timecode_clock.set(self.manager.timecode_server.get_time())
            timecode_clock.start()

        def stop_timecode(*args, **kwargs):
            timecode_status_indicator.updateConfig(color=[0.8, 0, 0])
            timecode_clock.stop()
            timecode_clock.set(None)

        def update_timecode(timecode: Timecode):
            timecode_clock.set(timecode.to_seconds())
            timecode_status_indicator.blink(250)

        if self.manager.timecode_server.status == TimecodeServerStatus.running:
            initialize_timecode()
        else:
            stop_timecode()

        self.manager.timecode_server.events.initialized.on(initialize_timecode)
        self.manager.timecode_server.events.error.on(stop_timecode)
        self.manager.timecode_server.callbacks.zero_frame.register(update_timecode)

    # ------------------------------------------------------------------------------------------------------------------
    def _build_tracker_overview(self):
        """Build the tracker overview group. Disabled if OptiTrack is not enabled in settings."""
        optitrack_enabled = self.manager.settings.tracker.enabled

        tracker_group = Widget_Group(group_id='tracker_group',
                                     title='Tracker',
                                     rows=11,
                                     columns=3,
                                     show_title=True)
        self.page.addWidget(tracker_group, row=1, column=1, width=10, height=12)

        tracker_status = CircleIndicator()
        tracker_group.addWidget(tracker_status, row=1, column=1, width=1, height=1)

        rigid_body_text = TextWidget(text='Rigid Bodies')
        tracker_group.addWidget(rigid_body_text, row=2, column=1, width=3, height=1)

        # Table
        rb_table = Table(title='Rigid Bodies')
        rb_table.add_column(
            TextColumn(
                id='object_id',
                title='ID',
                width=0.7
            )
        )
        rb_table.add_column(
            IndicatorColumn(
                id='valid',
                title='Valid'
            )
        )

        tracker_group.addWidget(rb_table, row=3, column=1, width=3, height=4)

        tracked_objects_text = TextWidget(text='Tracked Objects')
        tracker_group.addWidget(tracked_objects_text, row=7, column=1, width=3, height=1)

        tracker_table = Table()
        tracker_table.add_column(
            TextColumn(
                id='object_id',
                title='ID',
                width=0.4
            )
        )
        tracker_table.add_column(
            NumberColumn(
                id='x',
                title='X',
                increment=0.01,
            )
        )
        tracker_table.add_column(
            NumberColumn(
                id='y',
                title='Y',
                increment=0.01,
            )
        )
        tracker_table.add_column(
            IndicatorColumn(
                id='valid',
                title='Valid'
            )
        )

        tracker_group.addWidget(tracker_table, row=8, column=1, width=3, height=4)

        # If OptiTrack is not enabled, disable the group and skip callback registration
        if not optitrack_enabled:
            tracker_group.disable()
            return

        def initialize_tracker(*args, **kwargs):
            tracker_status.updateConfig(color=[0, 0.8, 0])

            for obj_id, rigid_body in self.manager.tracker.rigid_bodies.items():
                rb_table.make_row(id=obj_id, object_id=obj_id, valid=[0.8, 0, 0])

        def tracker_error(*args, **kwargs):
            tracker_status.updateConfig(color=[0.8, 0, 0])

        def on_new_tracked_object(tracked_object):
            existing_row = tracker_table.get_row_by_id(row_id=tracked_object.id)
            if existing_row:
                return
            tracker_table.make_row(id=tracked_object.id,
                                   object_id=tracked_object.id,
                                   x=tracked_object.state.x,
                                   y=tracked_object.state.y,
                                   valid=[0.8, 0, 0])

        def on_tracked_object_removed(obj_id: str):
            row = tracker_table.get_row_by_id(row_id=obj_id)
            if row:
                tracker_table.delete_row(row)

        def tracker_new_sample(*args, **kwargs):
            tracker_status.blink(250)
            # Go through the rigid bodies
            for rb_id, rigid_body_sample in self.manager.tracker.sample.items():
                row = rb_table.get_row_by_id(row_id=rb_id)
                if row:
                    cell = row.get_cell('valid')
                    if rigid_body_sample.valid:
                        cell.color = [0, 0.8, 0]
                    else:
                        cell.color = [0.8, 0, 0]

            # Go through the BILBOs
            for bilbo_id, bilbo in self.manager.tracker.bilbos.items():
                row = tracker_table.get_row_by_id(row_id=bilbo_id)
                if row:
                    cell_x = row.get_cell('x')
                    cell_y = row.get_cell('y')
                    cell_valid = row.get_cell('valid')
                    cell_x.set(bilbo.state.x)
                    cell_y.set(bilbo.state.y)

                    if bilbo.tracking_valid:
                        cell_valid.color = [0, 0.8, 0]
                    else:
                        cell_valid.color = [0.8, 0, 0]

            if self.manager.tracker.origin:
                row = tracker_table.get_row_by_id(row_id=self.manager.tracker.origin.id)
                if row:
                    cell_x = row.get_cell('x')
                    cell_y = row.get_cell('y')
                    cell_valid = row.get_cell('valid')
                    cell_x.set(self.manager.tracker.origin.state.x)
                    cell_y.set(self.manager.tracker.origin.state.y)
                    if self.manager.tracker.origin.tracking_valid:
                        cell_valid.color = [0, 0.8, 0]
                    else:
                        cell_valid.color = [0.8, 0, 0]

            if self.manager.tracker.limbo_bar:
                row = tracker_table.get_row_by_id(row_id=self.manager.tracker.limbo_bar.id)
                if row:
                    cell_x = row.get_cell('x')
                    cell_y = row.get_cell('y')
                    cell_valid = row.get_cell('valid')
                    cell_x.set(self.manager.tracker.limbo_bar.state.x)
                    cell_y.set(self.manager.tracker.limbo_bar.state.y)
                    if self.manager.tracker.limbo_bar.tracking_valid:
                        cell_valid.color = [0, 0.8, 0]
                    else:
                        cell_valid.color = [0.8, 0, 0]

        self.manager.tracker.events.initialized.on(initialize_tracker)
        self.manager.tracker.events.error.on(tracker_error)
        self.manager.tracker.events.new_sample.on(tracker_new_sample, max_rate=2)
        self.manager.tracker.events.new_tracked_object.on(on_new_tracked_object)
        self.manager.tracker.events.tracked_object_removed.on(on_tracked_object_removed)

    # ------------------------------------------------------------------------------------------------------------------
    def _build_display_group(self):
        """Build the display/extensions group with display text input and limbo bar slider.

        Widgets are disabled if their corresponding feature is not enabled in settings.
        """
        use_display = self.manager.settings.extensions.display
        use_limbobar = self.manager.settings.extensions.limbobar

        display_group = Widget_Group(
            group_id='display_group',
            title='Extensions',
            rows=2,
            columns=2,
            show_title=True
        )
        self.page.addWidget(display_group, row=15, column=1, width=10, height=4)

        # === Display Text Input ===
        self.display_text_input = InputWidget(
            widget_id='display_text_input',
            value='',
            datatype=None,
            title='Display',
            title_position='left',
            inputFieldAlign='center',
            inputFieldFontSize=12,
        )
        display_group.addWidget(self.display_text_input, row=1, column=1, width=2, height=1)

        if use_display:
            def on_display_text_changed(text: str):
                self.logger.info(f"Setting display text to: {text}")
                self.manager.extensions.display.set_text(text)

            self.display_text_input.callbacks.value_changed.register(on_display_text_changed)
        else:
            self.display_text_input.disable()

        # === Limbo Height Slider ===
        self.limbo_height_slider = ClassicSliderWidget(
            widget_id='limbo_height_slider',
            min_value=0,
            max_value=400,
            increment=5,
            value=0,
            title='Limbo Height',
            title_position='left',
            direction='horizontal',
            continuousUpdates=False,
            valuePosition='right',
        )
        display_group.addWidget(self.limbo_height_slider, row=2, column=1, width=2, height=1)

        if use_limbobar:
            def on_limbo_height_changed(height: float):
                height_m = height
                self.logger.info(f"Setting limbo bar height to: {height} mm")
                self.manager.extensions.limbo_bar.setHeight(height_m)

            self.manager.extensions.limbo_bar.setHeight(0)
            self.limbo_height_slider.callbacks.value_changed.register(on_limbo_height_changed)
        else:
            self.limbo_height_slider.disable()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_data_source_click(self, button, **kwargs):
        button.increaseIndex()
        self._data_source = button.state

    def _on_data_source_indicator_click(self, button, index, **kwargs):
        button.state_index = index
        self._data_source = button.state

    # ------------------------------------------------------------------------------------------------------------------
    def _build_robot_group(self, container: 'BILBO_GUI_OverviewPage.RobotContainer'):
        robot = container.robot
        raw_color = robot.config.general.color if robot.config else [0.5, 0.5, 0.5]
        # Normalize color components (may be floats or fraction strings like "201/255")
        color = [eval(c) if isinstance(c, str) else float(c) for c in raw_color[:3]]
        border_color = [int(c * 255) for c in color] + [0.8]

        group = Widget_Group(
            group_id=f'robot_{robot.id}',
            title=robot.id,
            rows=3,
            columns=1,
            show_title=True,
            border_color=border_color,
            border_width=2,
        )

        # Status widget
        mode = robot.robot.control.mode if isinstance(robot, RealTestbedBILBO) else BILBO_Control_Mode.OFF
        status_widget = StatusWidget(
            widget_id=f'status_{robot.id}',
            elements={
                'status': StatusWidgetElement(
                    label='Status',
                    color=[0, 0.5, 0],
                    status='connected',
                ),
                'static': StatusWidgetElement(
                    label='Static',
                    color=[0.5, 0.5, 0.5],
                    status='—',
                ),
            },
        )
        group.addWidget(status_widget, row=1, column=1, height=1, width=1)

        mode = BILBO_Control_Mode.OFF
        # Mode widget
        mode_widget = BilboModeWidget(
            widget_id=f'mode_{robot.id}',
            current_mode=mode.name,
            orientation='horizontal',
        )
        group.addWidget(mode_widget, row=2, column=1, height=2, width=1)

        # Place group on page (column 11, stacked per robot index)
        idx = len([r for r in self.robots.values() if r.group is not None])
        row = 1 + idx * 5
        self.page.addWidget(group, row=row, column=11, width=10, height=5)

        container.group = group
        container.status_widget = status_widget
        container.mode_widget = mode_widget

        # Wire up callbacks for real robots
        if isinstance(robot, RealTestbedBILBO):
            def on_mode_clicked(mode_id, _robot=robot, **kwargs):
                try:
                    _robot.robot.control.setControlMode(BILBO_Control_Mode[mode_id])
                except (KeyError, Exception) as e:
                    self.logger.warning(f'Failed to set mode {mode_id}: {e}')

            mode_widget.callbacks.mode_clicked.register(on_mode_clicked)

            def on_mode_changed(mode, _sw=status_widget, _mw=mode_widget, **kwargs):
                _mw.current_mode = mode.name
                _sw.elements['status'].status = mode.name
                _sw.elements['status'].color = CONTROL_MODE_COLORS.get(mode, [0.5, 0.5, 0.5])
                _sw.updateConfig()

            robot.robot.control.events.mode_changed.on(on_mode_changed)

            def on_stream(sample, _sw=status_widget, **kwargs):
                is_static = sample.estimation.static
                _sw.elements['static'].status = 'yes' if is_static else 'no'
                _sw.elements['static'].color = [0, 0.5, 0] if is_static else [0.6, 0.4, 0]
                _sw.updateConfig()

            robot.robot.core.events.stream.on(on_stream, max_rate=5)

    # ------------------------------------------------------------------------------------------------------------------
    def _remove_robot_group(self, container: 'BILBO_GUI_OverviewPage.RobotContainer'):
        if container.group is not None:
            self.page.removeWidget(container.group)
            container.group = None
            container.status_widget = None
            container.mode_widget = None

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_testbed_robot(self, robot: TestbedBILBO, *args, **kwargs):
        if robot.id in self.robots:
            self.logger.warning(f'Testbed robot {robot.id} already exists. Skipping.')
            return

        raw_color = robot.config.general.color if robot.config else [0.5, 0.5, 0.5]
        color = [eval(c) if isinstance(c, str) else float(c) for c in raw_color[:3]]
        text = robot.config.general.short_id if robot.config else robot.id

        container = self.RobotContainer(
            robot=robot,
            babylon=BabylonBilbo(object_id=robot.id, color=color, text=text)
        )

        self.robots[robot.id] = container
        self.babylon_visualization.addObject(container.babylon)

        # Build per-robot status group
        self._build_robot_group(container)

        # Subscribe to the robot's own stream so the 3D model updates
        # from estimation state (works even without OptiTrack tracker)

        def _on_stream(sample, _b=container.babylon, _s=container.status_widget, **kwargs):
            _b.set_state(
                x=sample.estimation.state.x,
                y=sample.estimation.state.y,
                theta=sample.estimation.state.theta,
                psi=sample.estimation.state.psi,
            ) if self._data_source == 'Robots' else None

        if isinstance(robot, RealTestbedBILBO):
            robot.robot.core.events.stream.on(
                _on_stream,
                max_rate=20,
            )

            # if isinstance(robot, RealTestbedBILBO):
            #     babylon_ref = container.babylon
            #     robot.robot.core.events.stream.on(
            #         lambda sample, _b=babylon_ref: (
            #             _b.set_state(
            #                 x=sample.estimation.state.x,
            #                 y=sample.estimation.state.y,
            #                 theta=sample.estimation.state.theta,
            #                 psi=sample.estimation.state.psi,
            #             ) if self._data_source == 'Robots' else None
            #         ),
            #         max_rate=20,
            #     )

            # Subscribe to planner events for path visualization
            rid = robot.id
            pc = robot.robot.position_control
            pc.events.path_planned.on(lambda data, _rid=rid: self._on_path_planned(_rid, data))
            pc.events.path_loaded.on(lambda data, _rid=rid: self._on_path_planned(_rid, data))
            pc.events.path_finished.on(lambda *a, _rid=rid, **kw: self._clear_path(_rid))
            pc.events.path_aborted.on(lambda *a, _rid=rid, **kw: self._clear_path(_rid))
            pc.events.path_timeout.on(lambda *a, _rid=rid, **kw: self._clear_path(_rid))
            pc.events.path_cleared.on(lambda *a, _rid=rid, **kw: self._clear_path(_rid))

        self._update_babylon_dropdown()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_testbed_robot_disconnected(self, robot_id: str, *args, **kwargs):
        if robot_id not in self.robots:
            self.logger.warning(f'Testbed robot {robot_id} not found. Skipping.')
            return

        self._clear_path(robot_id)
        self._remove_robot_group(self.robots[robot_id])
        self.babylon_visualization.removeObject(self.robots[robot_id].babylon)
        del self.robots[robot_id]
        self._update_babylon_dropdown()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_tracker_sample(self, *args, **kwargs):
        if self._data_source == 'OptiTrack':
            for robot in self.robots.values():
                robot.babylon.set_state(
                    x=robot.robot.true_state.x,
                    y=robot.robot.true_state.y,
                    theta=robot.robot.true_state.theta,
                    psi=robot.robot.true_state.psi,
                )

        # Always update obstacle 3D positions from tracker
        for obs_id, box in self._obstacle_babylon_objects.items():
            if obs_id in self.manager.testbed.obstacles:
                obs = self.manager.testbed.obstacles[obs_id]
                s = obs.state
                box.setPosition(x=s.x, y=s.y, z=0.125)
                box.setOrientation(qmt.quatFromAngleAxis(s.psi, [0, 0, 1]))

    # ------------------------------------------------------------------------------------------------------------------
    def _on_obstacle_added(self, obstacle, *args, **kwargs):
        """Add a box obstacle to the Babylon 3D view."""
        if not isinstance(obstacle, BoxObstacle):
            return
        if self.babylon_visualization is None:
            return
        obs_id = obstacle.id
        if obs_id in self._obstacle_babylon_objects:
            return

        s = obstacle.state
        box = Box(
            object_id=f"obstacle_{obs_id}",
            color=[0.8, 0.15, 0.15],
            alpha=0.5,
            size={'x': obstacle.config.width, 'y': obstacle.config.height, 'z': 0.25},
        )
        box.setPosition(x=s.x, y=s.y, z=0.125)
        box.setOrientation(qmt.quatFromAngleAxis(s.psi, [0, 0, 1]))
        self.babylon_visualization.addObject(box)
        self._obstacle_babylon_objects[obs_id] = box

    # ------------------------------------------------------------------------------------------------------------------
    def _on_obstacle_removed(self, obstacle, *args, **kwargs):
        """Remove a box obstacle from the Babylon 3D view."""
        if isinstance(obstacle, BoxObstacle):
            obs_id = obstacle.id
        elif isinstance(obstacle, str):
            obs_id = obstacle
        else:
            return
        if obs_id in self._obstacle_babylon_objects:
            box = self._obstacle_babylon_objects.pop(obs_id)
            if self.babylon_visualization is not None:
                self.babylon_visualization.removeObject(box)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_testbed_initialized(self, *args, **kwargs):
        self._testbed_size = self.manager.testbed_definition.size
        testbed_id = self.manager.testbed_definition.id

        size_x = self._testbed_size['x'][1] - self._testbed_size['x'][0]
        size_y = self._testbed_size['y'][1] - self._testbed_size['y'][0]
        size = max(size_x, size_y)

        # Choose scenario based on testbed ID
        if testbed_id == 'lab':
            scenario = LabScenario(
                x_range=[self._testbed_size['x'][0], self._testbed_size['x'][1]],
                y_range=[self._testbed_size['y'][0], self._testbed_size['y'][1]],
            )
        elif testbed_id == 'lab-hannover':
            scenario = LabScenario(
                x_range=[self._testbed_size['x'][0], self._testbed_size['x'][1]],
                y_range=[self._testbed_size['y'][0], self._testbed_size['y'][1]],
            )
        elif testbed_id == 'track':
            scenario = TrackScenario(
                x_range=[self._testbed_size['x'][0], self._testbed_size['x'][1]],
                y_range=[self._testbed_size['y'][0], self._testbed_size['y'][1]],
            )
        else:
            scenario = ArenaScenario(size=size)

        config = scenario.get_config()
        config['title'] = 'BILBO Testbed'

        self.babylon_visualization = BabylonVisualization(
            id='babylon', babylon_config=config
        )

        self.babylon_widget.set_babylon(self.babylon_visualization)
        self.babylon_visualization.start()

        scenario.setup(self.babylon_visualization)

        # Register floor double-click and dropdown callbacks
        self.babylon_visualization.callbacks.floor_doubleclick.register(self._on_babylon_floor_doubleclick)
        self.babylon_visualization.callbacks.dropdown_select.register(self._on_babylon_dropdown_select)

        # Add existing testbed obstacles to Babylon
        for obstacle in self.manager.testbed.obstacles.values():
            self._on_obstacle_added(obstacle)

    # ------------------------------------------------------------------------------------------------------------------
    def _update_babylon_dropdown(self):
        """Rebuild the Babylon dropdown from the current robot list."""
        if self.babylon_visualization is None:
            return
        items = [{'key': rid, 'label': rid} for rid in self.robots]
        # Keep current selection if still valid, otherwise pick the first
        selected = self._selected_robot if self._selected_robot in self.robots else None
        if selected is None and items:
            selected = items[0]['key']
        self._selected_robot = selected
        self.babylon_visualization.set_dropdown(items, selected)
        self._highlight_selected_robot()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_babylon_dropdown_select(self, selected: str):
        self._selected_robot = selected
        self.logger.info(f"Babylon dropdown selection: {selected}")
        # Sync selection across all connected clients
        self.babylon_visualization.update_dropdown_selection(selected)
        self._highlight_selected_robot()

    # ------------------------------------------------------------------------------------------------------------------
    def _highlight_selected_robot(self):
        """Highlight the selected robot's 3D object, unhighlight all others."""
        for rid, container in self.robots.items():
            container.babylon.highlight(rid == self._selected_robot)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_babylon_floor_doubleclick(self, x: float, y: float):
        selected = self._selected_robot
        if not selected or selected not in self.robots:
            self.logger.warning("No robot selected for navigation")
            return

        container = self.robots[selected]
        if not isinstance(container.robot, RealTestbedBILBO):
            self.logger.warning(f"Robot {selected} is not a real robot")
            return

        # Bounds check
        ts = self._testbed_size
        if not (ts['x'][0] < x < ts['x'][1] and ts['y'][0] < y < ts['y'][1]):
            self.logger.warning(f"Position out of bounds: ({x:.2f}, {y:.2f})")
            return

        self.logger.info(f"Planning path for {selected} to ({x:.2f}, {y:.2f})")
        container.robot.robot.position_control.plan_and_follow(target=(x, y))

    # ------------------------------------------------------------------------------------------------------------------
    def _on_path_planned(self, robot_id: str, path_data: PathData):
        """Draw the planned path with start/end markers in the 3D view."""
        if self.babylon_visualization is None:
            return
        if not path_data or not path_data.path_points:
            return

        # Remove previous path objects for this robot
        self._clear_path(robot_id)

        # Get robot color for the path
        robot_color = [0.5, 0.5, 0.5]
        if robot_id in self.robots and self.robots[robot_id].robot.config:
            raw = self.robots[robot_id].robot.config.general.color
            robot_color = [eval(c) if isinstance(c, str) else float(c) for c in raw[:3]]
        path_color = robot_color + [0.8]

        objects = []

        # Path line
        drawing = PathDrawing(
            object_id=f"path_{robot_id}",
            pathColor=path_color,
            pathWidth=PATH_WIDTH,
        )
        self.babylon_visualization.addObject(drawing)
        drawing.setPoints(path_data.path_points)
        objects.append(drawing)

        # Start point
        start = path_data.path_points[0]
        start_pt = PointsDrawing(
            object_id=f"path_start_{robot_id}",
            fillColor=PATH_START_COLOR,
            pointSize=PATH_ENDPOINT_SIZE,
        )
        self.babylon_visualization.addObject(start_pt)
        start_pt.setPoints([start])
        objects.append(start_pt)

        # End point
        end = path_data.path_points[-1]
        end_pt = PointsDrawing(
            object_id=f"path_end_{robot_id}",
            fillColor=PATH_END_COLOR,
            pointSize=PATH_ENDPOINT_SIZE,
        )
        self.babylon_visualization.addObject(end_pt)
        end_pt.setPoints([end])
        objects.append(end_pt)

        self._path_objects[robot_id] = objects

    # ------------------------------------------------------------------------------------------------------------------
    def _clear_path(self, robot_id: str):
        """Remove all path objects (line + endpoints) for a robot."""
        if robot_id in self._path_objects:
            objects = self._path_objects.pop(robot_id)
            if self.babylon_visualization is not None:
                for obj in objects:
                    try:
                        self.babylon_visualization.removeObject(obj)
                    except Exception:
                        pass
