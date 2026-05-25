from __future__ import annotations

import dataclasses
import math

import numpy as np
from prompt_toolkit.history import ThreadedHistory
from scipy.linalg import block_diag

from robots.frodo.applications.algorithm.algorithm import get_covariance_ellipse
from robots.frodo.applications.definitions import get_simulated_agent_definition_by_id
from robots.frodo.applications.simulation.frodo_simulation import FRODO_Simulation, FRODO_VisionAgent, FRODO_Static
from robots.frodo.applications.testbed.testbed_manager import FRODO_TestbedManager, TestbedObject, TestbedObject_FRODO, \
    TestbedObject_STATIC

from robots.frodo.applications.testbed.tracker.definitions import TrackedFRODO, TrackedStatic
from robots.frodo.applications.testbed.tracker.frodo_tracker import FRODO_Tracker
from core.utils.callbacks import Callback
from core.utils.colors import random_color_from_palette
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.time import Timer
from core.utils.video.camera_streamer import VideoStreamer
from extensions.libs.babylon.src.babylon import BabylonVisualization
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.tools.cli.cli import CLI, CommandSet
from extensions.gui.src.app import App
from extensions.gui.src.gui import GUI, Page, Category
from extensions.gui.src.lib.map.map import MapWidget
from extensions.gui.src.lib.map.map_objects import Agent, CoordinateSystem, VisionAgent, MapObjectGroup, Point, \
    Line, Ellipse
from extensions.gui.src.lib.objects.objects import Widget_Group, PagedWidgetGroup, GroupPageWidget
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.indicators import BatteryIndicatorWidget, ConnectionIndicator, \
    InternetIndicator, JoystickIndicator
from extensions.gui.src.lib.objects.python.video import VideoWidget
from extensions.gui.src.lib.objects.python.text import TextWidget

from extensions.gui.src.lib.terminal.terminal_widget import TerminalWidget
from robots.frodo.robot.frodo import FRODO
from robots.frodo.robot.frodo_definitions import STATIC_DEFINITIONS, FRODO_Sample, TESTBED_SIZE, \
    TESTBED_TILE_SIZE, FRODO_VIDEO_PORT, FRODO_COLORS
from robots.frodo.robot.frodo_manager import FRODO_Manager
from core.utils.lipo import lipo_soc
from robots.frodo.robot.frodo_utilities import vector2GlobalFrame
import robots.frodo.applications.agent_manager as agent_manager

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from robots.frodo.applications.frodo_application import FRODO_Application


class FRODO_SSH_Page:
    page: Page

    # === INIT =========================================================================================================
    def __init__(self, gui: GUI):
        self.gui = gui
        self.page = Page(id='ssh_page', name='SSH')
        self._buildPage()

    # ------------------------------------------------------------------------------------------------------------------
    def _buildPage(self, *args, **kwargs):
        ...
        # self.terminal_widget_1 = TerminalWidget(widget_id='terminal_widget', host='localhost')
        # self.page.addWidget( self.terminal_widget_1, width=20, height=9)


# === TRACKER PAGE =====================================================================================================
class FRODO_Tracker_Page:
    page: Page
    gui: GUI

    agents: dict
    statics: dict

    # === INIT =========================================================================================================
    def __init__(self, gui: GUI, tracker: FRODO_Tracker):
        self.gui = gui
        self.tracker = tracker
        self.logger = Logger('FRODO Tracker Page', 'DEBUG')
        self.page = Page(id='tracker_page', name='Tracker')

        # Build the map
        self.map_widget = MapWidget(widget_id='map_widget',
                                    limits={"x": [0, 3], "y": [0, 3]},
                                    initial_display_center=[1.5, 1.5],
                                    tiles=False,
                                    show_grid=True,
                                    major_grid_size=0.5,
                                    minor_grid_size=0.1,
                                    )

        self.page.addWidget(self.map_widget, width=18, height=18)
        self.map = self.map_widget.map
        self.agents = {}
        self.statics = {}

        self.tracker.events.description_received.on(self._onTrackerDescriptionReceived, once=True)

    # === METHODS ======================================================================================================

    # === PRIVATE METHODS ==============================================================================================
    def _onTrackerDescriptionReceived(self, *args, **kwargs):
        for frodo_id, frodo_tracked_agent in self.tracker.robots.items():
            # Add an agent to the map
            map_agent = Agent(id=frodo_id,
                              color=FRODO_COLORS[frodo_id],
                              size=0.07,
                              arrow_length=0.25,
                              arrow_width=0.05,
                              x=0,
                              y=0,
                              )

            self.agents[frodo_id] = {
                'map_object': map_agent,
                'tracked_object': frodo_tracked_agent,
            }
            frodo_tracked_agent.events.update.on(
                callback=Callback(function=self._onTrackedAgentUpdate, inputs={'frodo_id': frodo_id},
                                  discard_inputs=True),
                max_rate=10)

            self.map.addObject(map_agent)

        for static_id, static_marker in self.tracker.statics.items():
            if not static_id in STATIC_DEFINITIONS:
                self.logger.warning(f"Static ID {static_id} not found in STATIC_DEFINITIONS")
                continue
            static_definition = STATIC_DEFINITIONS[static_id]

            map_static = CoordinateSystem(id=static_id,
                                          name=static_id,
                                          show_name=True
                                          )

            self.statics[static_id] = {
                'map_object': map_static,
                'tracked_object': static_marker,
            }
            static_marker.events.update.on(
                callback=Callback(function=self._onTrackedStaticUpdate, inputs={'static_id': static_id},
                                  discard_inputs=True),
                max_rate=10)
            self.map.addObject(map_static)

    # ------------------------------------------------------------------------------------------------------------------
    def _onTrackedAgentUpdate(self, frodo_id):
        tracked_object: TrackedFRODO = self.agents[frodo_id]['tracked_object']
        x = tracked_object.state.x
        y = tracked_object.state.y
        psi = tracked_object.state.psi

        map_object: Agent = self.agents[frodo_id]['map_object']
        map_object.update(x=x, y=y, psi=psi)

    # ------------------------------------------------------------------------------------------------------------------
    def _onTrackedStaticUpdate(self, static_id):
        tracked_object: TrackedStatic = self.statics[static_id]['tracked_object']
        x = tracked_object.state.x
        y = tracked_object.state.y
        psi = tracked_object.state.psi

        map_object: CoordinateSystem = self.statics[static_id]['map_object']
        map_object.update(x=x, y=y, psi=psi)


# === OVERVIEW PAGE ====================================================================================================

@dataclasses.dataclass
class RobotOverviewWidgets:
    battery_widget: BatteryIndicatorWidget
    connection_strength_widget: ConnectionIndicator
    internet_indicator_widget: InternetIndicator
    joystick_indicator_widget: JoystickIndicator


class FRODO_Robots_Page:
    page: Page
    gui: GUI
    manager: FRODO_Manager

    robots: dict
    _num_robots: int = 0

    _timer_overview_updates: Timer

    # === INIT =========================================================================================================
    def __init__(self, gui: GUI, manager: FRODO_Manager):
        self.gui = gui
        self.manager = manager
        self.page = Page(id='robots_page', name='Robots')

        self.manager.events.new_robot.on(self._buildPage)
        self.manager.events.robot_disconnected.on(self._buildPage)
        self.robots = {}

        self._timer_overview_updates = Timer()

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # === PRIVATE METHODS ==============================================================================================
    def _buildPage(self, *args, **kwargs):
        self.page.clear()
        self._num_robots = 0
        self.robots = {}

    # ------------------------------------------------------------------------------------------------------------------
    def _onRobotUpdate(self, robot_id):
        data: FRODO_Sample = self.robots[robot_id]['robot'].core.data

        if self._timer_overview_updates > 2:
            self._timer_overview_updates.reset()
            # Update the overview widgets
            overview_widgets: RobotOverviewWidgets = self.robots[robot_id]['overview_widgets']
            lipo_percentage = lipo_soc(data.general.battery, cells=2)
            overview_widgets.battery_widget.setValue(percentage=lipo_percentage, voltage=data.general.battery)

            overview_widgets.connection_strength_widget.setValue(
                self._classify_connection_strength(data.general.connection_strength))
            overview_widgets.internet_indicator_widget.setValue(data.general.internet_connection)

            overview_widgets.joystick_indicator_widget.setValue(False)

    # ------------------------------------------------------------------------------------------------------------------
    def _addRobot(self, robot: FRODO):
        column = int(36 / 4 * self._num_robots) + 1

        robot_group = Widget_Group(group_id=f'robot_{robot.id}',
                                   title=robot.id,
                                   show_title=True,
                                   rows=18,
                                   columns=9,
                                   border_color=FRODO_COLORS[robot.id],
                                   border_width=2, )
        self.page.addWidget(robot_group, column=column, row=1, width=int(36 / 4), height=18)

        overview_group = Widget_Group(group_id=f'overview_{robot.id}',
                                      rows=1,
                                      columns=4,
                                      )
        robot_group.addWidget(overview_group, row=1, column=1, width=9, height=2)

        battery_widget = BatteryIndicatorWidget(widget_id=f'battery_{robot.id}',
                                                label_position='center',
                                                show='voltage',
                                                )
        overview_group.addWidget(battery_widget, row=1, column=1, width=1, height=1)

        connection_strength_widget = ConnectionIndicator(widget_id=f'connection_{robot.id}')
        overview_group.addWidget(connection_strength_widget, row=1, column=2, width=1, height=1)

        internet_indicator_widget = InternetIndicator(widget_id=f'internet_{robot.id}')
        overview_group.addWidget(internet_indicator_widget, row=1, column=3, width=1, height=1)

        joystick_indicator_widget = JoystickIndicator(widget_id=f'joystick_{robot.id}')
        overview_group.addWidget(joystick_indicator_widget, row=1, column=4, width=1, height=1)

        self.robots[robot.id] = {}
        self.robots[robot.id]['robot'] = robot
        self.robots[robot.id]['overview_widgets'] = RobotOverviewWidgets(battery_widget,
                                                                         connection_strength_widget,
                                                                         internet_indicator_widget,
                                                                         joystick_indicator_widget)

        robot.core.events.stream.on(
            callback=Callback(function=self._onRobotUpdate, inputs={'robot_id': robot.id}, discard_inputs=True), )

        control_status_group = Widget_Group(group_id=f'control_status_{robot.id}',
                                            rows=1,
                                            columns=1,
                                            )
        robot_group.addWidget(control_status_group, column=1, width=9, height=3)

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _classify_connection_strength(signal_strength: float) -> str:
        """Map a numeric signal strength (0..100) to low/medium/high."""
        if signal_strength > 85:
            return 'high'
        if signal_strength > 30:
            return 'medium'
        return 'low'


#
# # # === VISION PAGE ======================================================================================================
# # class FRODO_Vision_Page:
# #     page: Page
# #     gui: GUI
# #     manager: FRODO_Manager
# #
# #     robots: dict
# #     num_robots: int = 0
# #
# #     # === INIT =========================================================================================================
# #     def __init__(self, gui: GUI, manager: FRODO_Manager):
# #         self.gui = gui
# #         self.manager = manager
# #         self.page = Page(id='vision_page', name='Vision')
# #         self._buildPage()
# #
# #         self.manager.callbacks.new_robot.register(self._addRobot)
# #         self.manager.callbacks.robot_disconnected.register(self._removeRobot)
# #
# #         self.robots = {}
# #
# #     # === METHODS ======================================================================================================
# #     ...
# #
# #     # === PRIVATE METHODS ==============================================================================================
# #     def _buildPage(self, *args, **kwargs):
# #         # Add a big map
# #         self.map_widget = MapWidget(widget_id='vision_map_widget',
# #                                     limits={"x": [0, TESTBED_SIZE[0]], "y": [0, TESTBED_SIZE[1]]},
# #                                     initial_display_center=[TESTBED_SIZE[0] / 2, TESTBED_SIZE[1] / 2],
# #                                     tiles=True,
# #                                     tile_size=TESTBED_TILE_SIZE,
# #                                     show_grid=False,
# #                                     server_port=8101,
# #                                     # major_grid_size=0.5,
# #                                     # minor_grid_size=0.1,
# #                                     )
# #         self.page.addWidget(self.map_widget, width=18, height=18)
# #
# #     # ------------------------------------------------------------------------------------------------------------------
# #     def _addRobot(self, robot: FRODO):
# #         self.robots[robot.id] = {}
# #         self.robots[robot.id]['robot'] = robot
# #
# #         robot_group = MapObjectGroup(id=f'robot_{robot.id}_vision', )
# #         vision_elements_group = MapObjectGroup(id=f'robot_{robot.id}_vision_elements', )
# #         self.robots[robot.id]['group'] = robot_group
# #         self.robots[robot.id]['vision_elements_group'] = vision_elements_group
# #
# #         self.robots[robot.id]['vision_map_widget'] = VisionAgent(id=robot.id,
# #                                                                  color=FRODO_DEFINITIONS[robot.id].color,
# #                                                                  size=0.07,
# #                                                                  arrow_length=0.3,
# #                                                                  arrow_width=0.05,
# #                                                                  vision_radius=1.5,
# #                                                                  vision_fov=math.radians(120),
# #                                                                  x=0,
# #                                                                  y=0,
# #                                                                  )
# #
# #         robot_group.addObject(self.robots[robot.id]['vision_map_widget'])
# #         robot_group.addGroup(vision_elements_group)
# #         self.map_widget.map.addGroup(robot_group)
# #
# #         # Add the video output
# #         robot_video_widget = VideoWidget(widget_id=f'{robot.id}_video_widget',
# #                                          path=f"http://{robot.id}.local:{FRODO_VIDEO_PORT}/video",
# #                                          title=f"{robot.id}",
# #                                          title_color=FRODO_DEFINITIONS[robot.id].color, )
# #
# #         row, column = self._get_robot_video_spot(robot.id)
# #         self.page.addWidget(robot_video_widget, column=column, row=row, width=12, height=9)
# #
# #         self.robots[robot.id]['video_widget'] = robot_video_widget
# #
# #         robot.core.events.stream.on(
# #             callback=Callback(function=self._onRobotUpdate, inputs={'robot_id': robot.id}, discard_inputs=True), )
# #
# #         self.num_robots += 1
# #
# #     # ------------------------------------------------------------------------------------------------------------------
# #     def _removeRobot(self, robot: FRODO):
# #
# #         robot_id = robot.id
# #
# #         # Remove the video widget
# #         self.page.removeWidget(self.robots[robot_id]['video_widget'])
# #
# #         # Remove the robot from the map
# #         robot_group: MapObjectGroup = self.robots[robot_id]['group']
# #         self.map_widget.map.removeGroup(robot_group)
# #
# #     # ------------------------------------------------------------------------------------------------------------------
# #     def _onRobotUpdate(self, robot_id):
# #         robot: FRODO = self.robots[robot_id]['robot']
# #         data: FRODO_Sample = self.robots[robot_id]['robot'].core.data
# #
# #         # Update the vision map
# #
# #         # 1. Update the robot
# #         vision_map_widget: VisionAgent = self.robots[robot_id]['vision_map_widget']
# #         vision_map_widget.update(x=data.estimation.state.x, y=data.estimation.state.y, psi=data.estimation.state.psi)
# #
# #         # 2. Update the vision elements
# #
# #         vision_elements_group: MapObjectGroup = self.robots[robot_id]['vision_elements_group']
# #
# #         # Make all measurements invisible
# #         for element in vision_elements_group.objects.values():
# #             element.visible(False)
# #
# #         # Update the measurements that are visible
# #         for measurement in data.measurements.aruco_measurements:
# #             object_id = str(measurement.measured_aruco_id)
# #             position = measurement.position
# #             psi = measurement.psi
# #
# #             position_global = vector2GlobalFrame(position, robot.core.data.estimation.state.psi)
# #             position_global = [position_global[0] + robot.core.data.estimation.state.x,
# #                                position_global[1] + robot.core.data.estimation.state.y, ]
# #
# #             if vision_elements_group.objectInGroup(object_id):
# #                 element = vision_elements_group.getObjectByPath(object_id)
# #                 element.visible(True)
# #                 element.update(x=position_global[0], y=position_global[1])
# #
# #             else:
# #                 vision_element = Point(id=object_id,
# #                                        color=[0.8, 0.8, 0.8],
# #                                        size=0.05,
# #                                        x=position_global[0],
# #                                        y=position_global[1],
# #                                        )
# #                 vision_elements_group.addObject(vision_element)
# #
# #     # ------------------------------------------------------------------------------------------------------------------
# #     def _get_robot_video_spot(self, robot_id):
# #
# #         match robot_id:
# #             case 'frodo1':
# #                 return (1, 24)
# #             case 'frodo2':
# #                 return (1, 36)
# #             case 'frodo3':
# #                 return (10, 24)
# #             case 'frodo4':
# #                 return (10, 36)
# #             case _:
# #                 raise ValueError(f"Unknown robot ID {robot_id}")
# class FRODO_Vision_Page:
#     page: Page
#     gui: GUI
#     manager: FRODO_Manager
#
#     robots: dict
#     num_robots: int = 0
#
#     @dataclasses.dataclass
#     class VisionMeasurementContainer:
#         id: str
#         point: Point
#         covariance: Ellipse
#
#     # === INIT =========================================================================================================
#     def __init__(self, gui: GUI, manager: FRODO_Manager):
#         self.gui = gui
#         self.manager = manager
#         self.page = Page(id='vision_page', name='Vision')
#         self._buildPage()
#
#         self.manager.callbacks.new_robot.register(self._addRobot)
#         self.manager.callbacks.robot_disconnected.register(self._removeRobot)
#
#         self.robots = {}
#
#     # === METHODS ======================================================================================================
#     ...
#
#     # === PRIVATE METHODS ==============================================================================================
#     def _buildPage(self, *args, **kwargs):
#         # Add a big map
#         self.map_widget = MapWidget(widget_id='vision_map_widget',
#                                     limits={"x": [0, TESTBED_SIZE[0]], "y": [0, TESTBED_SIZE[1]]},
#                                     initial_display_center=[TESTBED_SIZE[0] / 2, TESTBED_SIZE[1] / 2],
#                                     tiles=True,
#                                     tile_size=TESTBED_TILE_SIZE,
#                                     show_grid=False,
#                                     server_port=8101,
#                                     )
#         self.page.addWidget(self.map_widget, width=18, height=18)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _addRobot(self, robot: FRODO):
#         self.robots[robot.id] = {}
#         self.robots[robot.id]['robot'] = robot
#
#         robot_group = MapObjectGroup(id=f'robot_{robot.id}_vision', )
#         vision_elements_group = MapObjectGroup(id=f'robot_{robot.id}_vision_elements', )
#         self.robots[robot.id]['group'] = robot_group
#         self.robots[robot.id]['vision_elements_group'] = vision_elements_group
#         self.robots[robot.id]['measurements'] = {}  # str -> VisionMeasurementContainer
#
#         self.robots[robot.id]['vision_map_widget'] = VisionAgent(id=robot.id,
#                                                                  color=FRODO_COLORS[robot.id],
#                                                                  size=0.07,
#                                                                  arrow_length=0.3,
#                                                                  arrow_width=0.05,
#                                                                  vision_radius=1.5,
#                                                                  vision_fov=math.radians(120),
#                                                                  x=0,
#                                                                  y=0,
#                                                                  )
#
#         robot_group.addObject(self.robots[robot.id]['vision_map_widget'])
#         robot_group.addGroup(vision_elements_group)
#         self.map_widget.map.addGroup(robot_group)
#
#         # Add the video output
#         robot_video_widget = VideoWidget(widget_id=f'{robot.id}_video_widget',
#                                          path=f"http://{robot.id}.local:{FRODO_VIDEO_PORT}/video",
#                                          title=f"{robot.id}",
#                                          title_color=FRODO_COLORS[robot.id])
#
#         row, column = self._get_robot_video_spot(robot.id)
#         self.page.addWidget(robot_video_widget, column=column, row=row, width=12, height=9)
#
#         self.robots[robot.id]['video_widget'] = robot_video_widget
#
#         robot.core.events.stream.on(
#             callback=Callback(function=self._onRobotUpdate, inputs={'robot_id': robot.id}, discard_inputs=True), )
#
#         self.num_robots += 1
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _removeRobot(self, robot: FRODO):
#
#         robot_id = robot.id
#
#         # Remove the video widget
#         self.page.removeWidget(self.robots[robot_id]['video_widget'])
#
#         # Remove the robot from the map
#         robot_group: MapObjectGroup = self.robots[robot_id]['group']
#         self.map_widget.map.removeGroup(robot_group)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _normalize_covariance_xy(self, P_raw) -> np.ndarray:
#         """
#         Robustly extract a 2x2 (x,y) covariance from various possible representations.
#         Falls back to a tiny isotropic covariance if unknown.
#         """
#         if isinstance(P_raw, np.ndarray):
#             if P_raw.ndim == 2:
#                 if P_raw.shape == (3, 3):
#                     P_xy = P_raw[:2, :2]
#                 elif P_raw.shape == (2, 2):
#                     P_xy = P_raw
#                 else:
#                     diag = np.diag(P_raw)
#                     P_xy = np.diag(diag[:2]) if diag.size >= 2 else np.eye(2) * 1e-6
#             elif P_raw.ndim == 1:
#                 P_xy = np.diag(P_raw[:2]) if P_raw.size >= 2 else np.eye(2) * 1e-6
#             else:
#                 P_xy = np.eye(2) * 1e-6
#         else:
#             P_xy = np.eye(2) * 1e-6
#
#         # Symmetrize for safety
#         return 0.5 * (P_xy + P_xy.T)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _onRobotUpdate(self, robot_id):
#         robot: FRODO = self.robots[robot_id]['robot']
#         data: FRODO_Sample = self.robots[robot_id]['robot'].core.data
#
#         # Update the vision map
#
#         # 1. Update the robot
#         vision_map_widget: VisionAgent = self.robots[robot_id]['vision_map_widget']
#         vision_map_widget.update(x=data.estimation.state.x, y=data.estimation.state.y, psi=data.estimation.state.psi)
#
#         # 2. Update the vision elements (points + covariance ellipses)
#         vision_elements_group: MapObjectGroup = self.robots[robot_id]['vision_elements_group']
#         measurements_dict: dict[str, FRODO_Vision_Page.VisionMeasurementContainer] = self.robots[robot_id][
#             'measurements'
#         ]
#
#         active_ids = set()
#
#         # Make everything invisible for this tick; we'll re-enable the ones we see
#         for container in measurements_dict.values():
#             container.point.visible(False)
#             container.covariance.visible(False)
#
#         # Update the measurements that are visible
#         for measurement in getattr(data.measurements, 'aruco_measurements', []):
#             object_id = str(measurement.measured_aruco_id)
#
#             # Relative position of the measured object in the robot frame
#             # existing code uses "measurement.position" (likely [x, y] in robot frame)
#             rel_pos = np.asarray(measurement.position[:2], dtype=float)
#
#             # Convert to global coordinates using current robot pose
#             rel_global = vector2GlobalFrame(rel_pos, robot.core.data.estimation.state.psi)
#             meas_x = float(rel_global[0] + robot.core.data.estimation.state.x)
#             meas_y = float(rel_global[1] + robot.core.data.estimation.state.y)
#
#             # Create or fetch map objects
#             if object_id not in measurements_dict:
#                 point = Point(
#                     id=object_id,
#                     color=[0.8, 0.8, 0.8],
#                     size=0.05,
#                     x=meas_x,
#                     y=meas_y,
#                 )
#                 ellipse = Ellipse(
#                     id=f"{object_id}_covariance",
#                     opacity=0.2,
#                     color=[0.8, 0.8, 0.8],
#                     x=meas_x,
#                     y=meas_y,
#                     rx=0.0,
#                     ry=0.0,
#                     psi=0.0,
#                 )
#                 vision_elements_group.addObject(point)
#                 vision_elements_group.addObject(ellipse)
#
#                 measurements_dict[object_id] = self.VisionMeasurementContainer(
#                     id=object_id,
#                     point=point,
#                     covariance=ellipse,
#                 )
#             else:
#                 # Re-enable visibility
#                 measurements_dict[object_id].point.visible(True)
#                 measurements_dict[object_id].covariance.visible(True)
#
#             container = measurements_dict[object_id]
#             container.point.update(x=meas_x, y=meas_y)
#
#             # --- Covariance handling (mirror of Testbed page logic) ---
#             # Try a few attribute names to be robust across message versions
#             P_raw = block_diag(measurement.uncertainty_position, measurement.uncertainty_psi)
#
#             P_xy_agent = self._normalize_covariance_xy(P_raw)
#
#             # Rotate into global frame using robot heading
#             psi_robot = robot.core.data.estimation.state.psi
#             c, s = np.cos(psi_robot), np.sin(psi_robot)
#             R = np.array([[c, -s],
#                           [s, c]], dtype=float)
#             P_xy_global = R @ P_xy_agent @ R.T
#
#             # Convert covariance to ellipse radii / orientation
#             rx, ry, psi_ellipse = get_covariance_ellipse(P_xy_global)
#
#             container.covariance.update(
#                 x=meas_x,
#                 y=meas_y,
#                 rx=rx,
#                 ry=ry,
#                 psi=psi_ellipse,
#             )
#
#             active_ids.add(object_id)
#
#         # Hide any measurements not present this tick
#         for mid, container in list(measurements_dict.items()):
#             if mid not in active_ids:
#                 container.point.visible(False)
#                 container.covariance.visible(False)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _get_robot_video_spot(self, robot_id):
#
#         match robot_id:
#             case 'frodo1':
#                 return (1, 24)
#             case 'frodo2':
#                 return (1, 36)
#             case 'frodo3':
#                 return (10, 24)
#             case 'frodo4':
#                 return (10, 36)
#             case _:
#                 raise ValueError(f"Unknown robot ID {robot_id}")


# === DATA PAGE ========================================================================================================
class FRODO_TestbedData_Page:
    page: Page
    gui: GUI
    manager: FRODO_Manager
    testbed_manager: FRODO_TestbedManager

    agents: dict[str, AgentContainer]
    statics: dict[str, StaticContainer]

    # === INIT =========================================================================================================
    def __init__(self, gui: GUI, manager: FRODO_Manager, testbed_manager: FRODO_TestbedManager):
        self.gui = gui
        self.manager = manager
        self.testbed_manager = testbed_manager
        self.page = Page(id='data_page', name='Testbed Data')

        # Start the camera stream from USB if possible
        self.streamer = VideoStreamer(
            camera_source=0,
            host='0.0.0.0',
            port=8000,
            path='/video',
            stream_type='mjpeg',
            width=1280,
            height=720,
            fps=24
        )
        try:
            self.streamer.start()
        except KeyboardInterrupt:
            self.streamer.stop()

        self._buildPage()

        self.agents = {}
        self.statics = {}
        self._add_listeners()

        register_exit_callback(self.stop)

    # === CLASSES ======================================================================================================
    @dataclasses.dataclass
    class MeasurementContainer:
        id: str
        object_to: str
        object: Agent
        line: Line
        covariance: Ellipse

    @dataclasses.dataclass
    class AgentContainer:
        object: TestbedObject_FRODO
        group: MapObjectGroup
        map_object: Agent
        measurements: dict[str, "FRODO_TestbedData_Page.MeasurementContainer"]
        measurements_group: MapObjectGroup

    @dataclasses.dataclass
    class StaticContainer:
        object: TestbedObject_STATIC
        map: CoordinateSystem

    # === PROPERTIES ===================================================================================================

    # === METHODS ======================================================================================================
    def stop(self, *args, **kwargs):
        self.streamer.stop()

    # === PRIVATE METHODS ==============================================================================================
    def _buildPage(self):

        self.map_widget = MapWidget(widget_id='data_map_widget',
                                    limits={"x": [0, TESTBED_SIZE[0]], "y": [0, TESTBED_SIZE[1]]},
                                    initial_display_center=[TESTBED_SIZE[0] / 2, TESTBED_SIZE[1] / 2],
                                    tiles=True,
                                    tile_size=TESTBED_TILE_SIZE,
                                    show_grid=False,
                                    server_port=8102,
                                    )
        self.page.addWidget(self.map_widget, width=18, height=18)

        # self.testbed_video = TextWidget(text='Testbed Video')
        self.testbed_video = VideoWidget(widget_id='testbed_video',
                                         path=f"http://localhost:8000/video",
                                         title="Testbed Video",
                                         )
        self.page.addWidget(self.testbed_video, row=1, column=19, width=12, height=9)

        self.agent_data = TextWidget(text='Agent Data')
        self.page.addWidget(self.agent_data, row=10, column=19, width=12, height=9)

        self.agent_video_1 = VideoWidget(widget_id=f'{'frodo1'}_video_widget',
                                         path=f"http://frodo1.local:{FRODO_VIDEO_PORT}/video",
                                         title="FRODO 1",
                                         title_color=FRODO_COLORS['frodo1'])
        self.page.addWidget(self.agent_video_1, row=1, column=31, width=10, height=9)

        self.agent_video_2 = VideoWidget(widget_id=f'{'frodo2'}_video_widget',
                                         path=f"http://frodo2.local:{FRODO_VIDEO_PORT}/video",
                                         title="FRODO 2",
                                         title_color=FRODO_COLORS['frodo2'])
        self.page.addWidget(self.agent_video_2, row=1, column=41, width=10, height=9)

        self.agent_video_3 = VideoWidget(widget_id=f'{'frodo3'}_video_widget',
                                         path=f"http://frodo3.local:{FRODO_VIDEO_PORT}/video",
                                         title="FRODO 3",
                                         title_color=FRODO_COLORS['frodo3'])
        self.page.addWidget(self.agent_video_3, row=10, column=31, width=10, height=9)

        self.agent_video_4 = VideoWidget(widget_id=f'{'frodo4'}_video_widget',
                                         path=f"http://frodo4.local:{FRODO_VIDEO_PORT}/video",
                                         title="FRODO 4",
                                         title_color=FRODO_COLORS['frodo4'])
        self.page.addWidget(self.agent_video_4, row=10, column=41, width=10, height=9)

    # ------------------------------------------------------------------------------------------------------------------
    def _add_listeners(self):
        self.testbed_manager.events.new_object.on(self._on_testbed_manager_new_object)
        self.testbed_manager.events.update.on(self._on_testbed_manager_update)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_testbed_manager_new_object(self, testbed_object, *args, **kwargs):
        self.addTestbedObject(testbed_object)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_testbed_manager_update(self, *args, **kwargs):
        for agent in list(self.agents.values()):
            # 1) Update agent pose on map
            agent.map_object.update(x=agent.object.state.x,
                                    y=agent.object.state.y,
                                    psi=agent.object.state.psi)

            active_measurement_ids = set()
            active_line_ids = set()

            # 2) Handle all current measurements from this agent
            for measurement in agent.object.measurements:
                measured_object_id = measurement.object_to.id
                measurement_id = f"{agent.object.id} -> {measured_object_id}"
                measurement_line_id = f"{agent.object.id}_to_{measured_object_id}_line"

                active_measurement_ids.add(measurement_id)
                active_line_ids.add(measurement_line_id)

                # Create map objects on first sight
                if measurement_id not in agent.measurements:
                    measurement_object = Agent(
                        id=measurement_id,
                        color=[0.8, 0.8, 0.8],
                        size=0.05,
                        opacity=0.5,
                    )
                    agent.measurements_group.addObject(measurement_object)
                    measurement_line = Line(
                        id=measurement_line_id,
                        name=measurement_id,
                        color=[0.8, 0.8, 0.8],
                        start=agent.map_object,  # dynamic endpoint
                        end=measurement_object,  # dynamic endpoint
                    )
                    covariance = Ellipse(
                        id=f"{measurement_id}_covariance",
                        opacity=0.2,
                        color=[0.8, 0.8, 0.8],
                    )

                    # Store and add to the map group so they render
                    agent.measurements[measurement_id] = self.MeasurementContainer(
                        id=measurement_id,
                        object_to=measured_object_id,
                        object=measurement_object,
                        line=measurement_line,
                        covariance=covariance,
                    )

                    agent.measurements_group.addObject(measurement_line)
                    agent.measurements_group.addObject(covariance)
                else:
                    # Make visible again this tick
                    agent.measurements[measurement_id].object.visible(True)
                    agent.measurements[measurement_id].line.visible(True)
                    agent.measurements[measurement_id].covariance.visible(True)

                mc = agent.measurements[measurement_id]

                # 3) Compute the global position for the measured object
                rel_vec_agent = np.asarray([measurement.relative.x, measurement.relative.y])
                rel_global = vector2GlobalFrame(rel_vec_agent, agent.object.state.psi)
                meas_x = rel_global[0] + agent.object.state.x
                meas_y = rel_global[1] + agent.object.state.y
                meas_psi_global = measurement.relative.psi + agent.object.state.psi

                mc.object.update(x=meas_x, y=meas_y, psi=meas_psi_global)

                # 4) Update covariance ellipse
                # measurement.covariance is in the measuring agent frame.
                # We need a 2x2 position covariance in *global* frame.
                P = measurement.covariance

                # Normalize to a 2x2 (x,y) covariance in the agent frame
                if isinstance(P, np.ndarray):
                    if P.ndim == 2:
                        if P.shape == (3, 3):
                            P_xy_agent = P[:2, :2]
                        elif P.shape == (2, 2):
                            P_xy_agent = P
                        else:
                            # Fallback: try to interpret diagonal [var_x, var_y, ...]
                            diag = np.diag(P)
                            P_xy_agent = np.diag(diag[:2]) if diag.size >= 2 else np.eye(2) * 1e-6
                    elif P.ndim == 1:  # diagonal provided as vector
                        P_xy_agent = np.diag(P[:2]) if P.size >= 2 else np.eye(2) * 1e-6
                    else:
                        P_xy_agent = np.eye(2) * 1e-6
                else:
                    # Unknown type → tiny isotropic cov to stay robust
                    P_xy_agent = np.eye(2) * 1e-6

                # Rotate into global frame using the agent's current heading
                c, s = np.cos(agent.object.state.psi), np.sin(agent.object.state.psi)
                R = np.array([[c, -s],
                              [s, c]], dtype=float)
                P_xy_global = R @ (0.5 * (P_xy_agent + P_xy_agent.T)) @ R.T  # symmetrize for safety

                # Convert 2x2 covariance to ellipse radii/orientation
                rx, ry, psi_ellipse = get_covariance_ellipse(P_xy_global)

                # 5) Push ellipse update (center at measured global position)
                mc.covariance.update(
                    x=meas_x,
                    y=meas_y,
                    rx=rx,
                    ry=ry,
                    psi=psi_ellipse,
                )

            # 6) Hide any measurements not present this tick
            for mid, container in list(agent.measurements.items()):
                if mid not in active_measurement_ids:
                    container.object.visible(False)
                    container.line.visible(False)
                    container.covariance.visible(False)

    # ------------------------------------------------------------------------------------------------------------------
    def addTestbedObject(self, object: TestbedObject):

        if isinstance(object, TestbedObject_FRODO):

            group = MapObjectGroup(id=f'object_{object.id}_group')
            agent = Agent(id=object.id,
                          color=FRODO_COLORS[object.id],
                          size=0.07,
                          arrow_length=0.3,
                          arrow_width=0.05,
                          opacity=0.5,
                          )

            group.addObject(agent)
            self.map_widget.map.addGroup(group)

            agent_container = self.AgentContainer(object=object,
                                                  group=group,
                                                  map_object=agent,
                                                  measurements_group=MapObjectGroup(
                                                      id=f'object_{object.id}_measurements'),
                                                  measurements={}
                                                  )

            agent_container.group.addGroup(agent_container.measurements_group)

            self.agents[object.id] = agent_container

        elif isinstance(object, TestbedObject_STATIC):
            ...
        else:
            raise ValueError(f"Unknown object type {type(object)}")

    # ------------------------------------------------------------------------------------------------------------------
    def removeTestbedObject(self, robot_id):
        ...
    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------


# === FRODO AGENTS PAGE ================================================================================================
class FRODO_Agents_Page:
    page: Page
    gui: GUI
    manager: agent_manager.FRODO_AgentManager

    @dataclasses.dataclass
    class AgentPage_AgentContainer:
        id: str
        agent: agent_manager.AgentContainer
        map_group: MapObjectGroup
        map_object: Agent
        measurements: MapObjectGroup
        lines: MapObjectGroup

    @dataclasses.dataclass
    class AgentPage_StaticContainer:
        static: agent_manager.StaticContainer
        map_group: MapObjectGroup
        map_object: Point

    agents: dict[str, AgentPage_AgentContainer]
    statics: dict[str, AgentPage_StaticContainer]

    # === INIT =========================================================================================================
    def __init__(self, gui: GUI, manager: agent_manager.FRODO_AgentManager):
        self.gui = gui
        self.manager = manager
        self.page = Page(id='agents_page', name='Agents')
        self.agents = {}
        self.statics = {}
        self._buildPage()

        self.manager.events.update.on(self._on_agent_manager_update)
        self.manager.events.new_agent.on(self._on_new_agent)

    def _buildPage(self):
        self.map_widget = MapWidget(widget_id='agent_map_widget',
                                    limits={"x": [0, TESTBED_SIZE[0]], "y": [0, TESTBED_SIZE[1]]},
                                    initial_display_center=[TESTBED_SIZE[0] / 2, TESTBED_SIZE[1] / 2],
                                    tiles=True,
                                    tile_size=TESTBED_TILE_SIZE,
                                    show_grid=False,
                                    server_port=8107,
                                    )
        self.page.addWidget(self.map_widget, width=18, height=18)

    # ------------------------------------------------------------------------------------------------------------------
    def _clear(self):
        self.map_widget.map.clear()
        self.agents = {}
        self.statics = {}

    # ------------------------------------------------------------------------------------------------------------------
    def _add_agent(self, agent: agent_manager.AgentContainer):
        agent_id = agent.id

        if agent_id in FRODO_COLORS:
            color = FRODO_COLORS[agent_id]
        elif get_simulated_agent_definition_by_id(agent_id) is not None:
            color = get_simulated_agent_definition_by_id(agent_id).color
        else:
            color = [0.8, 0.8, 0.8]

        group = MapObjectGroup(id=f'object_{agent_id}_group')

        map_object = Agent(id=agent_id,
                           color=color,
                           size=0.07,
                           arrow_length=0.3,
                           arrow_width=0.05,
                           opacity=0.5,
                           )

        map_object.update(x=agent.state.x, y=agent.state.y, psi=agent.state.psi)

        group.addObject(map_object)

        measurements_group = MapObjectGroup(id=f'object_{agent_id}_measurements')
        lines_group = MapObjectGroup(id=f'object_{agent_id}_lines')
        group.addGroup(measurements_group)
        group.addGroup(lines_group)
        self.map_widget.map.addGroup(group)

        container = self.AgentPage_AgentContainer(id=agent_id,
                                                  agent=agent,
                                                  map_group=group,
                                                  map_object=map_object,
                                                  measurements=measurements_group,
                                                  lines=lines_group,
                                                  )

        self.agents[agent_id] = container

    # ------------------------------------------------------------------------------------------------------------------
    def _add_static(self, static: agent_manager.StaticContainer):
        static_id = static.id
        map_object = Point(id=static_id,
                           color=[0.8, 0.8, 0.8],
                           size=0.05,
                           )
        group = MapObjectGroup(id=f'static_{static_id}_group')
        group.addObject(map_object)
        self.map_widget.map.addGroup(group)
        container = self.AgentPage_StaticContainer(static=static,
                                                   map_group=group,
                                                   map_object=map_object,
                                                   )
        self.statics[static_id] = container

    # ------------------------------------------------------------------------------------------------------------------
    def _on_agent_manager_update(self, *args, **kwargs):

        # Update the agents
        for agent_id, agent_container in self.agents.items():
            # Update agent pose
            agent_container.map_object.update(x=agent_container.agent.state.x,
                                              y=agent_container.agent.state.y,
                                              psi=agent_container.agent.state.psi)

        # Update the statics
        for static_id, static_container in self.statics.items():
            static_container.map_object.update(x=static_container.static.state.x,
                                               y=static_container.static.state.y,
                                               psi=static_container.static.state.psi)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_agent(self, agent: agent_manager.AgentContainer, *args, **kwargs):
        self._add_agent(agent)


# === FRODO SIMULATION PAGE ============================================================================================
class FRODO_Simulation_Page:
    page: Page
    gui: GUI
    simulation: FRODO_Simulation

    @dataclasses.dataclass
    class SimulationAgentContainer:
        id: str
        agent: FRODO_VisionAgent
        map_object: VisionAgent
        group: MapObjectGroup
        measurements: MapObjectGroup
        lines: MapObjectGroup

    @dataclasses.dataclass
    class SimulationStaticContainer:
        id: str
        static: FRODO_Static
        map_object: CoordinateSystem
        group: MapObjectGroup

    agents: dict[str, SimulationAgentContainer]
    statics: dict[str, SimulationStaticContainer]

    # === INIT =========================================================================================================
    def __init__(self, gui: GUI, simulation: FRODO_Simulation):
        self.gui = gui
        self.simulation = simulation
        self.agents = {}
        self.statics = {}
        self.page = Page(id='simulation_page', name='Simulation')
        self.logger = Logger('Simulation Page')
        self._buildPage()

        self.simulation.events.initialized.on(self._on_simulation_initialized)
        self.simulation.events.update.on(self._on_simulation_update, max_rate=20)
        self.simulation.events.new_agent.on(self._on_simulation_new_agent)
        self.simulation.events.removed_agent.on(self._on_simulation_removed_agent)
        self.simulation.events.new_static.on(self._on_simulation_new_static)
        self.simulation.events.removed_static.on(self._on_simulation_removed_static)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildPage(self):

        group_2d = PagedWidgetGroup('2d', title='2D Map', rows=1, columns=1)

        self.map_widget = MapWidget(widget_id='data_map_widget',
                                    limits={"x": [0, TESTBED_SIZE[0]], "y": [0, TESTBED_SIZE[1]]},
                                    initial_display_center=[TESTBED_SIZE[0] / 2, TESTBED_SIZE[1] / 2],
                                    tiles=True,
                                    tile_size=TESTBED_TILE_SIZE,
                                    show_grid=False,
                                    server_port=8109,
                                    )

        group_2d.addWidget(self.map_widget, width=1, height=1)
        group_3d = PagedWidgetGroup('3d', title='3D Map', rows=1, columns=1)

        self.babylon_widget = BabylonWidget(widget_id='babylon_widget')
        self.babylon = BabylonVisualization('babylon')

        floor = SimpleFloor('floor', size_y=50, size_x=50, texture='carpet.png')
        self.babylon.addObject(floor)

        self.babylon.start()

        self.babylon_widget.babylon = self.babylon
        group_3d.addWidget(self.babylon_widget, width=1, height=1)

        self.simulation_overview = TextWidget(text='Simulation Overview')
        self.page.addWidget(self.simulation_overview, row=1, column=19, width=12, height=9)

        self.simulation_agent_data = TextWidget(text='Simulation Agent Data')
        self.page.addWidget(self.simulation_agent_data, row=10, column=19, width=12, height=9)

        self.map_group = GroupPageWidget(group_id='maps')
        self.page.addWidget(self.map_group, row=1, column=1, width=18, height=18)

        self.map_group.addGroup(group_2d)
        self.map_group.addGroup(group_3d)

    # ------------------------------------------------------------------------------------------------------------------
    def _add_agent(self, agent: FRODO_VisionAgent):
        agent_id = agent.agent_id
        agent_definition = get_simulated_agent_definition_by_id(agent.agent_id)
        if agent_definition is not None:
            agent_color = agent_definition.color
        else:
            agent_color = [0.8, 0.8, 0.8]

        map_object = VisionAgent(agent_id, name=agent_id, color=agent_color, fov=agent.config.fov,
                                 vision_radius=agent.config.vision_radius, )

        group = MapObjectGroup(id=f'object_{agent_id}_group')
        group.addObject(map_object)
        measurements_group = MapObjectGroup(id=f'object_{agent_id}_measurements')
        lines_group = MapObjectGroup(id=f'object_{agent_id}_lines')
        group.addGroup(measurements_group)
        group.addGroup(lines_group)
        self.map_widget.map.addGroup(group)
        container = self.SimulationAgentContainer(
            id=agent_id,
            agent=agent,
            map_object=map_object,
            group=group,
            measurements=measurements_group,
            lines=lines_group,
        )
        self.agents[agent_id] = container

    # ------------------------------------------------------------------------------------------------------------------
    def _remove_agent(self, agent: SimulationAgentContainer | str):
        if isinstance(agent, str):
            agent_id = agent
        else:
            agent_id = agent.id
        self.map_widget.map.removeGroup(self.agents[agent_id].group)
        del self.agents[agent_id]

    # ------------------------------------------------------------------------------------------------------------------
    def _add_static(self, static: FRODO_Static):
        static_id = static.agent_id

        map_object = CoordinateSystem(id=f"{static_id}",
                                      x=static.state.x,
                                      y=static.state.y,
                                      psi=static.state.psi,
                                      show_name=True)

        group = MapObjectGroup(id=f'static_{static_id}_group')
        group.addObject(map_object)
        self.map_widget.map.addGroup(group)
        container = self.SimulationStaticContainer(
            id=static_id,
            static=static,
            map_object=map_object,
            group=group,
        )
        self.statics[static_id] = container

    # ------------------------------------------------------------------------------------------------------------------
    def _remove_static(self, static: FRODO_Static):
        static_id = static.agent_id
        self.map_widget.map.removeGroup(f'static_{static_id}_group')
        del self.statics[static_id]

    # ------------------------------------------------------------------------------------------------------------------
    def _on_simulation_initialized(self, *args, **kwargs):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _on_simulation_update(self, *args, **kwargs):

        # Update the agents
        for agent_id, agent_container in self.agents.items():
            # Update the agent object
            agent_container.map_object.update(x=agent_container.agent.state.x,
                                              y=agent_container.agent.state.y,
                                              psi=agent_container.agent.state.psi)

            # Update the measurements
            # vnjkdfvnkdjfsnvkjfd
            #
            # ADD THIS
            #
            # ALSO ADD TITLES TO ALL PAGES SAYING IF THEY ARE INITIALIZED YET!

        # Update the statics
        for static_id, static_container in self.statics.items():
            static_container.map_object.update(x=static_container.static.state.x,
                                               y=static_container.static.state.y,
                                               psi=static_container.static.state.psi)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_simulation_new_agent(self, agent: FRODO_VisionAgent, *args, **kwargs):
        if agent.agent_id not in self.agents:
            self._add_agent(agent)
        else:
            self.logger.warning(f"Agent {agent.agent_id} already exists in simulation page")

    # ------------------------------------------------------------------------------------------------------------------
    def _on_simulation_removed_agent(self, agent: str, *args, **kwargs):
        if agent in self.agents:
            self._remove_agent(self.agents[agent])
        else:
            self.logger.warning(f"Agent {agent} does not exist in simulation page")

    # ------------------------------------------------------------------------------------------------------------------
    def _on_simulation_new_static(self, static: FRODO_Static, *args, **kwargs):
        if static.agent_id not in self.statics:
            self._add_static(static)
        else:
            self.logger.warning(f"Static {static.agent_id} already exists in simulation page")

    # ------------------------------------------------------------------------------------------------------------------
    def _on_simulation_removed_static(self, static: FRODO_Static, *args, **kwargs):
        if static.agent_id in self.statics:
            self._remove_static(static)
        else:
            self.logger.warning(f"Static {static.agent_id} does not exist in simulation page")
    # ------------------------------------------------------------------------------------------------------------------


# === FRODO ALGORITHM PAGE =============================================================================================
class FRODO_Algorithm_Page:
    page: Page

    # === INIT =========================================================================================================
    def __init__(self, application: FRODO_Application):
        self.application = application
        self._build_page()
        self.add_listeners()

    # === METHODS ======================================================================================================
    def _build_page(self):
        self.page = Page(id='algorithm_page', name='Algorithm')

        self.map_widget = MapWidget(widget_id='algorithm_map_widget',
                                    limits={"x": [0, TESTBED_SIZE[0]], "y": [0, TESTBED_SIZE[1]]},
                                    initial_display_center=[TESTBED_SIZE[0] / 2, TESTBED_SIZE[1] / 2],
                                    tiles=True,
                                    tile_size=TESTBED_TILE_SIZE,
                                    show_grid=False,
                                    server_port=8103,
                                    )
        self.page.addWidget(self.map_widget, width=18, height=18)

        # Overview Group
        overview_group = Widget_Group(group_id='overview', rows=1, columns=4, show_title=True,
                                      title='Algorithm Overview')

        self.page.addWidget(overview_group, column=19, row=1, width=9, height=3)

        controls_group = Widget_Group(group_id='controls', rows=1, columns=1, show_title=True,
                                      title='Algorithm Control')
        self.page.addWidget(controls_group, column=19, row=4, width=9, height=15)

        # self.error_plot_widget = PlotWidget(widget_id='plot_widget_1', title='Plot 1',
        #                                     server_mode=ServerMode.EXTERNAL,
        #                                     update_mode=UpdateMode.CONTINUOUS)

        # dataseries_1 = JSPlotTimeSeries(timeseries_id='ds1',
        #                                 name='Data 1',
        #                                 unit='V',
        #                                 min=-10,
        #                                 max=10,
        #                                 color=random_color_from_palette('pastel'), )
        # dataseries_2 = JSPlotTimeSeries(timeseries_id='ds2',
        #                                 name='Data 2',
        #                                 unit='V',
        #                                 min=-10,
        #                                 max=10,
        #                                 color=random_color_from_palette('pastel'), )
        # dataseries_3 = JSPlotTimeSeries(timeseries_id='ds3',
        #                                 name='Data 3',
        #                                 unit='V',
        #                                 min=-10,
        #                                 max=10,
        #                                 color=random_color_from_palette('pastel'), )
        # dataseries_4 = JSPlotTimeSeries(timeseries_id='ds4',
        #                                 name='Data 4',
        #                                 unit='V',
        #                                 min=-10,
        #                                 max=10,
        #                                 color=random_color_from_palette('pastel'), )
        # self.error_plot_widget.plot.addTimeseries(dataseries_1)
        # self.error_plot_widget.plot.addTimeseries(dataseries_2)
        # self.error_plot_widget.plot.addTimeseries(dataseries_3)
        # self.error_plot_widget.plot.addTimeseries(dataseries_4)

        # self.page.addWidget(self.error_plot_widget, column=28, row=1, width=9, height=9)

    # ------------------------------------------------------------------------------------------------------------------
    def add_listeners(self):
        ...


# === GUI ==============================================================================================================
class FRODO_GUI:
    gui: GUI
    app: App

    categories: dict

    tracker: FRODO_Tracker

    # === INIT =========================================================================================================
    def __init__(self,
                 host,
                 application,
                 testbed_manager: FRODO_TestbedManager,
                 cli: CLI = None):
        self.logger = Logger('FRODO GUI', 'DEBUG')
        self.gui = GUI(
            id='frodo_gui',
            host=host,
            run_js=True
        )

        if cli is not None:
            self.gui.cli_terminal.setCLI(cli)
        self.categories = {}

        self.application = application
        self.testbed_manager = testbed_manager
        self.tracker = self.testbed_manager.tracker
        self.robot_manager = self.testbed_manager.robot_manager

        self._buildOverviewCategory()
        addLogRedirection(self._logRedirection, minimum_level='DEBUG')

        self.commands = self.Commands(self)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.gui.start()

    # === PRIVATE METHODS ==============================================================================================
    def _buildOverviewCategory(self):
        self.overview_category = Category(id='overview', name='FRODO App')
        self.gui.addCategory(self.overview_category)

        self.ssh_page = FRODO_SSH_Page(self.gui)
        self.overview_category.addPage(self.ssh_page.page)

        self.robots_page = FRODO_Robots_Page(self.gui, self.robot_manager)
        self.overview_category.addPage(self.robots_page.page)

        self.tracker_page = FRODO_Tracker_Page(self.gui,
                                               tracker=self.tracker)

        self.overview_category.addPage(self.tracker_page.page)

        self.data_page = FRODO_TestbedData_Page(self.gui, manager=self.robot_manager,
                                                testbed_manager=self.testbed_manager)
        self.overview_category.addPage(self.data_page.page)

        self.simulation_page = FRODO_Simulation_Page(self.gui, self.application.simulation)
        self.overview_category.addPage(self.simulation_page.page)

        self.agents_page = FRODO_Agents_Page(self.gui, manager=self.application.agent_manager)
        self.overview_category.addPage(self.agents_page.page)

        self.algorithm_page = FRODO_Algorithm_Page(self.application)
        self.overview_category.addPage(self.algorithm_page.page)

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        print_text = f"[{logger.name}] {log}"
        color = LOGGING_COLORS[level]
        color = [c / 255 for c in color]
        self.gui.print(print_text, color=color)

    # ------------------------------------------------------------------------------------------------------------------

    # === CLASSES ======================================================================================================
    class Commands(CommandSet):
        def __init__(self, gui: FRODO_GUI):
            super().__init__('gui')
            self.gui = gui
