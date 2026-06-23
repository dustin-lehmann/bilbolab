"""Big testbed-camera view for the IdeenExpo 2026 application.

Provides a large :class:`CameraWidget` (≈70% of the page width) that enumerates
the cameras connected to the host (the testbed machine), auto-selects one
(configurable via the expo settings' ``camera`` block) and streams its MJPEG
feed — blown up for the expo audience. The operator can still switch cameras via
the widget's dropdown.

The remaining ≈30% on the right is a live status column for the *currently
connected robots* (one compact slot per robot), modelled on the per-robot
overview in :class:`robots.bilbo.gui.robot_ui.RobotUI`: control mode, battery,
Wi-Fi strength and Pi temperature. Slots bind to robots as they connect (via the
testbed manager's ``new_bilbo`` / ``bilbo_removed`` events) and clear on
disconnect. The page is added to the standard *Application* category by the GUI
(see ``gui.py``).
"""
from __future__ import annotations

from collections.abc import Callable

from core.utils.lipo import lipo_soc
from core.utils.logging_utils import Logger
from extensions.gui.src.gui import Page
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.camera import CameraWidget
from extensions.gui.src.lib.objects.python.indicators import BatteryIndicatorWidget
from extensions.gui.src.lib.objects.python.text import TextWidget, StatusWidget, StatusWidgetElement
from robots.bilbo.applications.ideenexpo_2026.settings import CameraSettings, JoystickSpeedSettings
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_utilities import CONTROL_MODE_COLORS
from robots.bilbo.testbed.objects import RealTestbedBILBO, TestbedBILBO
from robots.bilbo.testbed.testbed_manager import TestbedManager

# Page grid is 18 rows x 50 columns. Split it ~70% / ~30%.
_CAMERA_WIDTH = 35           # columns 1..35  (camera)
_PANEL_COLUMN = 36           # columns 36..50 (robot data)
_PANEL_WIDTH = 50 - _CAMERA_WIDTH  # 15 columns

# Number of robot slots reserved in the right column (pre-allocated so the page
# layout is fixed; slots bind/unbind as robots connect/disconnect). The expo runs
# at most 3 robots; the freed space below holds the master-controller panel.
_MAX_ROBOT_SLOTS = 3
_SLOT_HEIGHT = 4             # rows per slot (header row + 3-row status block)
_SLOT_START_ROW = 2         # row 1 holds the panel header

# Master-controller panel sits directly below the last robot slot.
_MASTER_ROW = _SLOT_START_ROW + _MAX_ROBOT_SLOTS * _SLOT_HEIGHT  # row 14
_MASTER_HEIGHT = 4

_GREY = [0.5, 0.5, 0.5]
_GREEN = [0.1, 0.55, 0.15]
_AMBER = [0.7, 0.5, 0.0]
_RED = [0.7, 0.15, 0.1]
_BLUE = [0.2, 0.4, 0.7]


def _speed_color(index: int, count: int) -> list:
    """Colour for a speed level by its rank: slow → green, fast → orange."""
    if count <= 1:
        return [0.2, 0.5, 0.8]
    frac = index / (count - 1)
    return [0.2 + 0.6 * frac, 0.55 - 0.2 * frac, 0.15]


# ======================================================================================================================
class _RobotSlot:
    """One pre-allocated robot status slot in the right-hand column.

    Holds the widgets and (when bound) the robot it is showing plus the stream
    subscription handle so it can be torn down on disconnect.
    """

    def __init__(self, page: Page, index: int,
                 show_speed: bool = False,
                 speed_resolver: Callable[[float], tuple[str, list] | None] | None = None):
        row = _SLOT_START_ROW + index * _SLOT_HEIGHT
        self._speed_resolver = speed_resolver

        self.group = Widget_Group(group_id=f'cam_robot_slot_{index}', rows=_SLOT_HEIGHT, columns=_PANEL_WIDTH,
                                  show_title=False)
        page.addWidget(self.group, row=row, column=_PANEL_COLUMN, width=_PANEL_WIDTH, height=_SLOT_HEIGHT)

        self.id_label = TextWidget(widget_id=f'cam_robot_slot_{index}_id', text='—',
                                   font_size=12, font_weight='bold', horizontal_alignment='center')
        self.group.addWidget(self.id_label, row=1, column=1, width=_PANEL_WIDTH, height=1)

        # Build the status elements (Speed only when configured/enabled).
        elements = {'mode': StatusWidgetElement(label='Mode', color=_GREY, status='--')}
        if show_speed:
            elements['speed'] = StatusWidgetElement(label='Speed', color=_GREY, status='--')
        elements['conn'] = StatusWidgetElement(label='Wi-Fi', color=_GREY, status='--')
        elements['temp'] = StatusWidgetElement(label='Temp', color=_GREY, status='--')

        self.status = StatusWidget(widget_id=f'cam_robot_slot_{index}_status', elements=elements)
        self.group.addWidget(self.status, row=2, column=1, width=10, height=3)

        self.battery = BatteryIndicatorWidget(widget_id=f'cam_robot_slot_{index}_battery',
                                              label_position='center', show='voltage')
        self.group.addWidget(self.battery, row=2, column=11, width=5, height=3)

        self.robot: BILBO | None = None
        self._listener = None

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def is_free(self) -> bool:
        return self.robot is None

    # ------------------------------------------------------------------------------------------------------------------
    def bind(self, robot: BILBO, max_rate: float):
        """Show ``robot`` in this slot and subscribe to its data stream."""
        self.robot = robot
        self.id_label.text = robot.id  # setter pushes the update
        # Throttle the panel updates; the stream itself runs much faster.
        self._listener = robot.core.events.stream.on(self._on_stream, max_rate=max_rate)

    # ------------------------------------------------------------------------------------------------------------------
    def unbind(self):
        """Detach from the current robot and reset the slot to its empty state."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self.robot = None

        self.id_label.text = '—'  # setter pushes the update
        for element in self.status.elements.values():
            element.status = '--'
            element.color = _GREY
        self.status.updateConfig()
        self.battery.setValue(percentage=0, voltage=0)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_stream(self, sample, *args, **kwargs):
        robot = self.robot
        if robot is None:
            return
        try:
            # Control mode (held live on the robot, mirrors RobotUI).
            mode = robot.control.mode
            self.status.elements['mode'].status = mode.name
            self.status.elements['mode'].color = CONTROL_MODE_COLORS[mode]

            # Input "speed" level (Slow/Medium/Fast), set from the app's Master folder.
            if 'speed' in self.status.elements and self._speed_resolver is not None:
                resolved = self._speed_resolver(robot.interfaces.input_scale_forward)
                if resolved is not None:
                    self.status.elements['speed'].status, self.status.elements['speed'].color = resolved

            # Wi-Fi connection strength.
            strength = sample.general.connection_strength
            if strength > 85:
                self.status.elements['conn'].status, self.status.elements['conn'].color = 'strong', [0, 0.5, 0]
            elif strength > 30:
                self.status.elements['conn'].status, self.status.elements['conn'].color = 'medium', [0.7, 0.5, 0.0]
            else:
                self.status.elements['conn'].status, self.status.elements['conn'].color = 'weak', [0.7, 0.1, 0.1]

            # Pi temperature.
            temp = sample.general.rpi_temperature
            if temp > 0:
                self.status.elements['temp'].status = f"{temp:.0f} °C"
                if temp >= 80:
                    self.status.elements['temp'].color = [0.7, 0.1, 0.1]
                elif temp >= 70:
                    self.status.elements['temp'].color = [0.7, 0.5, 0.0]
                else:
                    self.status.elements['temp'].color = [0, 0.5, 0]
            self.status.updateConfig()

            # Battery (voltage + state-of-charge).
            voltage = sample.sensors.power.bat_voltage
            cells = robot.config.electronics.battery_cells
            self.battery.setValue(percentage=lipo_soc(voltage=voltage, cells=cells), voltage=voltage)
        except Exception:
            # A malformed/partial sample must never take down the page.
            pass


# ======================================================================================================================
class IdeenExpo2026_CameraPage:
    """A camera page (≈70%) with a live connected-robots status column (≈30%).

    Exposes ``self.page``; the GUI adds it to the Application category.
    """

    page: Page
    camera_widget: CameraWidget

    # Panel refresh rate [Hz] — kept low; this is an at-a-glance status column.
    PANEL_UPDATE_RATE = 5

    def __init__(self, settings: CameraSettings, host: str | None = None,
                 manager: TestbedManager | None = None,
                 speed_settings: JoystickSpeedSettings | None = None,
                 joystick_control=None):
        self.settings = settings
        self.manager = manager
        # Only the expo joystick control exposes master state; guard against the base one.
        self.joystick_control = joystick_control if hasattr(joystick_control, 'master_callbacks') else None
        self.logger = Logger("Camera Page")

        # Speed levels (Slow/Medium/Fast) for mapping a robot's input scale → level name.
        self._speed_levels: list[tuple[str, float]] = []
        if speed_settings is not None and speed_settings.enabled:
            self._speed_levels = [(lvl.name, lvl.forward) for lvl in speed_settings.levels]
        show_speed = bool(self._speed_levels)

        self.page = Page(id='camera_page', name='Camera', icon='📷')

        # Big camera widget filling the left ~70% of the (18 x 50) page grid.
        self.camera_widget = CameraWidget(
            widget_id='bigview_camera_widget',
            host=host,
            auto_start=True,
            width=settings.width,
            height=settings.height,
            fps=settings.fps,
            excluded=settings.excluded,
            priority=settings.priority,
        )
        self.page.addWidget(self.camera_widget, row=1, column=1, width=_CAMERA_WIDTH, height=18)

        # Right ~30%: connected-robots status column.
        self._header = TextWidget(widget_id='cam_robots_header', text='Connected Robots',
                                  font_size=12, font_weight='bold', horizontal_alignment='center')
        self.page.addWidget(self._header, row=1, column=_PANEL_COLUMN, width=_PANEL_WIDTH, height=1)

        self.slots = [_RobotSlot(self.page, i, show_speed=show_speed, speed_resolver=self._resolve_speed)
                      for i in range(_MAX_ROBOT_SLOTS)]

        # Track which robot id occupies which slot, so disconnects can be matched.
        self._slot_by_robot_id: dict[str, _RobotSlot] = {}

        # Master-controller panel below the robot slots (only if master is available).
        self._master_status = None
        self._master_callbacks = []  # (container, callback) pairs, for teardown
        if self.joystick_control is not None:
            self._build_master_panel()

        if self.manager is not None:
            self.manager.events.new_bilbo.on(self._on_new_bilbo)
            self.manager.events.bilbo_removed.on(self._on_bilbo_removed)

    # ------------------------------------------------------------------------------------------------------------------
    def _build_master_panel(self):
        """Build the master-controller status block and subscribe to master events."""
        group = Widget_Group(group_id='cam_master_panel', rows=_MASTER_HEIGHT, columns=_PANEL_WIDTH,
                             show_title=False)
        self.page.addWidget(group, row=_MASTER_ROW, column=_PANEL_COLUMN,
                            width=_PANEL_WIDTH, height=_MASTER_HEIGHT)

        header = TextWidget(widget_id='cam_master_header', text='🕹️ Master Controller',
                            font_size=12, font_weight='bold', horizontal_alignment='center')
        group.addWidget(header, row=1, column=1, width=_PANEL_WIDTH, height=1)

        self._master_status = StatusWidget(
            widget_id='cam_master_status',
            elements={
                'state': StatusWidgetElement(label='State', color=_GREY, status='not connected'),
                'target': StatusWidgetElement(label='Robot', color=_GREY, status='—'),
                'mode': StatusWidgetElement(label='Mode', color=_GREY, status='—'),
            },
        )
        group.addWidget(self._master_status, row=2, column=1, width=_PANEL_WIDTH, height=3)

        # Refresh on any master state change. discard_inputs=True so the various
        # callback payloads (joystick / robot / mode) are ignored — we re-read state.
        jc = self.joystick_control
        for name in ('master_connected', 'master_disconnected', 'master_target_changed',
                     'master_mode_changed', 'master_override', 'master_released'):
            container = getattr(jc.master_callbacks, name, None)
            if container is not None:
                container.register(self._refresh_master, discard_inputs=True)
                self._master_callbacks.append((container, self._refresh_master))

        self._refresh_master()  # initial state

    # ------------------------------------------------------------------------------------------------------------------
    def _refresh_master(self, *args, **kwargs):
        """Reflect the current master-controller state in the panel."""
        jc = self.joystick_control
        if jc is None or self._master_status is None:
            return
        try:
            elements = self._master_status.elements
            if getattr(jc, 'master_joystick', None) is None:
                elements['state'].status, elements['state'].color = 'not connected', _GREY
                elements['target'].status, elements['target'].color = '—', _GREY
                elements['mode'].status, elements['mode'].color = '—', _GREY
            else:
                elements['state'].status, elements['state'].color = 'connected', _GREEN
                target = getattr(jc, 'master_target', None)
                if target is None:
                    elements['target'].status, elements['target'].color = 'none', _GREY
                    elements['mode'].status, elements['mode'].color = 'idle', _GREY
                else:
                    elements['target'].status, elements['target'].color = target.id, _BLUE
                    # master_mode is 'Full' (MasterOverrideMode.FULL) or 'Assist'.
                    if getattr(jc, 'master_mode', None) == 'Full':
                        elements['mode'].status, elements['mode'].color = 'Override', _RED
                    else:
                        elements['mode'].status, elements['mode'].color = 'Assist', _AMBER
            self._master_status.updateConfig()
        except Exception:
            pass

    # ------------------------------------------------------------------------------------------------------------------
    def _resolve_speed(self, forward_scale: float) -> tuple[str, list] | None:
        """Map a robot's forward input scale back to the nearest configured level name."""
        if not self._speed_levels:
            return None
        best_index = min(range(len(self._speed_levels)),
                         key=lambda i: abs(self._speed_levels[i][1] - forward_scale))
        name = self._speed_levels[best_index][0]
        return name, _speed_color(best_index, len(self._speed_levels))

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_bilbo(self, testbed_bilbo: TestbedBILBO, *args, **kwargs):
        """Bind a newly connected (real, initialized) robot to a free slot."""
        if not isinstance(testbed_bilbo, RealTestbedBILBO):
            return
        robot = testbed_bilbo.robot

        # Wait for the first sample before binding, mirroring RobotUI.
        if robot.core.initialized:
            self._bind_robot(robot)
        else:
            robot.core.events.initialized.on(lambda *a, **k: self._bind_robot(robot),
                                             once=True, discard_data=True)

    # ------------------------------------------------------------------------------------------------------------------
    def _bind_robot(self, robot: BILBO):
        if robot.id in self._slot_by_robot_id:
            return
        slot = next((s for s in self.slots if s.is_free), None)
        if slot is None:
            self.logger.warning(f"No free robot slot for {robot.id} (max {_MAX_ROBOT_SLOTS} shown)")
            return
        slot.bind(robot, max_rate=self.PANEL_UPDATE_RATE)
        self._slot_by_robot_id[robot.id] = slot

    # ------------------------------------------------------------------------------------------------------------------
    def _on_bilbo_removed(self, robot_id: str, *args, **kwargs):
        slot = self._slot_by_robot_id.pop(robot_id, None)
        if slot is not None:
            slot.unbind()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        """Stop the camera stream, detach all robot slots and master subscriptions."""
        for slot in self.slots:
            slot.unbind()
        for container, callback in self._master_callbacks:
            try:
                container.remove(callback)
            except Exception:
                pass
        self._master_callbacks = []
        self.camera_widget.close()
