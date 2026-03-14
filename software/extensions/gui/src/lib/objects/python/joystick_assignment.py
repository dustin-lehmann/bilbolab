from typing import Any, Callable

from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.dict_utils import update_dict
from core.utils.logging_utils import Logger
from extensions.gui.src.lib.objects.objects import Widget, Widget_Callbacks


# === JOYSTICK ASSIGNMENT WIDGET =======================================================================================
@callback_definition
class JoystickAssignmentWidgetCallbacks(Widget_Callbacks):
    connection_made: CallbackContainer      # Called when a connection is made (joystick_id, robot_id)
    connection_removed: CallbackContainer   # Called when a connection is removed (joystick_id, robot_id)
    joystick_double_click: CallbackContainer  # Called when joystick box is double-clicked (joystick_id)
    robot_double_click: CallbackContainer     # Called when robot box is double-clicked (robot_id)
    clear_all: CallbackContainer              # Called when clear all button is clicked
    auto_assign: CallbackContainer            # Called when auto button is clicked


class JoystickAssignmentWidget(Widget):
    """
    Widget for assigning joysticks to robots via drag-and-drop connections.

    Shows joysticks on the left and robots on the right. Users can draw
    connection lines from joystick handles to robot handles.

    Interaction:
    - Drag from joystick handle to robot handle to create connection
    - Double-click on connection line to remove it
    - Double-click on joystick/robot box triggers callback (no connection change)
    - Clear All button removes all connections
    - Auto button auto-assigns joysticks to robots in order

    Each joystick/robot dict can include an optional 'color' field [r,g,b,a]
    (values 0-1) to subtly tint the box background.
    """
    type = 'joystick_assignment'

    callbacks: JoystickAssignmentWidgetCallbacks

    # === INIT =========================================================================================================
    def __init__(self, widget_id: str | None = None, **kwargs):
        super().__init__(widget_id)

        default_config = {
            # Data
            # Joysticks/robots can include 'color' field for subtle background tint: [r, g, b, a] (0-1 range)
            'joysticks': [],  # List: [{'id': 'joy1', 'name': 'Joystick 1', 'color': [r,g,b,a]}, ...]
            'robots': [],     # List: [{'id': 'bilbo1', 'name': 'BILBO 1', 'color': [r,g,b,a]}, ...]
            'connections': {},  # Dict mapping joystick_id to robot_id: {'joy1': 'bilbo1', ...}

            # Styling
            'background_color': [0.15, 0.15, 0.18, 1],
            'box_color': [0.25, 0.25, 0.28, 1],
            'box_hover_color': [0.35, 0.35, 0.38, 1],
            'line_color': [0.3, 0.7, 1.0, 1],
            'line_width': 3,
            'handle_color': [0.5, 0.5, 0.55, 1],
            'handle_hover_color': [0.3, 0.7, 1.0, 1],
            'handle_size': 18,
            'text_color': [1, 1, 1, 0.9],
            'id_font_size': 10,
            'box_min_width': 80,
            'box_max_width': 80,
            'box_min_height': 80,
            'box_max_height': 80,
            'box_gap': 8,
            'column_gap': 80,
            'box_border_radius': 8,
            'button_color': [0.3, 0.3, 0.35, 1],
            'button_hover_color': [0.4, 0.4, 0.45, 1],
            'button_text_color': [1, 1, 1, 0.9],
            'button_font_size': 11,
            'button_height': 32,
            'button_gap': 10,

            # Images (relative paths from assets folder)
            'joystick_image': '/src/lib/assets/gamepad.png',
            'robot_image': '/src/lib/assets/bilbo_icon.png',
            'image_opacity': 0.7,
            'image_min_size': 18,
            'image_max_size': 40,
        }

        self.logger = Logger(f"JoystickAssignmentWidget {self.id}", 'DEBUG')
        self.callbacks = JoystickAssignmentWidgetCallbacks()

        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)

        # Internal state
        self._joysticks: list[dict] = list(self.config.get('joysticks', []))
        self._robots: list[dict] = list(self.config.get('robots', []))
        self._connections: dict[str, str] = dict(self.config.get('connections', {}))

    # === PROPERTIES ===================================================================================================
    @property
    def joysticks(self) -> list[dict]:
        return self._joysticks

    @joysticks.setter
    def joysticks(self, value: list[dict]):
        self._joysticks = list(value) if value else []
        self.config['joysticks'] = self._joysticks
        self._sendStateUpdate()

    @property
    def robots(self) -> list[dict]:
        return self._robots

    @robots.setter
    def robots(self, value: list[dict]):
        self._robots = list(value) if value else []
        self.config['robots'] = self._robots
        self._sendStateUpdate()

    @property
    def connections(self) -> dict[str, str]:
        return self._connections

    @connections.setter
    def connections(self, value: dict[str, str]):
        self._connections = dict(value) if value else {}
        self.config['connections'] = self._connections
        self._sendStateUpdate()

    # === METHODS ======================================================================================================
    def setJoysticks(self, joysticks: list[dict]):
        """Set the list of joysticks. Each dict should have 'id' and optionally 'name'."""
        self.joysticks = joysticks

    def setRobots(self, robots: list[dict]):
        """Set the list of robots. Each dict should have 'id' and optionally 'name'."""
        self.robots = robots

    def setConnections(self, connections: dict[str, str]):
        """Set all connections at once. Dict maps joystick_id to robot_id."""
        self.connections = connections

    def addConnection(self, joystick_id: str, robot_id: str):
        """Add a single connection."""
        self._connections[joystick_id] = robot_id
        self.config['connections'] = self._connections
        self._sendStateUpdate()

    def removeConnection(self, joystick_id: str):
        """Remove a connection by joystick_id."""
        if joystick_id in self._connections:
            del self._connections[joystick_id]
            self.config['connections'] = self._connections
            self._sendStateUpdate()

    def clearAllConnections(self):
        """Remove all connections."""
        self._connections.clear()
        self.config['connections'] = self._connections
        self._sendStateUpdate()

    def autoAssign(self):
        """Auto-assign joysticks to robots (one-to-one in order)."""
        self._connections.clear()
        for i, joystick in enumerate(self._joysticks):
            if i < len(self._robots):
                self._connections[joystick['id']] = self._robots[i]['id']
        self.config['connections'] = self._connections
        self._sendStateUpdate()

    def getConfiguration(self) -> dict:
        return {
            'type': self.type,
            'id': self.id,
            'joysticks': self._joysticks,
            'robots': self._robots,
            'connections': self._connections,
            **{k: v for k, v in self.config.items() if k not in ['joysticks', 'robots', 'connections']},
        }

    def handleEvent(self, message, sender=None) -> Any:
        event = message.get('event')
        data = message.get('data', {})

        if event == 'connection_made':
            joystick_id = data.get('joystick_id')
            robot_id = data.get('robot_id')
            if joystick_id and robot_id:
                self._connections[joystick_id] = robot_id
                self.config['connections'] = self._connections
                self.logger.debug(f"Connection made: {joystick_id} -> {robot_id}")
                for callback in self.callbacks.connection_made:
                    callback(widget=self, joystick_id=joystick_id, robot_id=robot_id, sender=sender)

        elif event == 'connection_removed':
            joystick_id = data.get('joystick_id')
            robot_id = data.get('robot_id')
            if joystick_id and joystick_id in self._connections:
                del self._connections[joystick_id]
                self.config['connections'] = self._connections
                self.logger.debug(f"Connection removed: {joystick_id}")
                for callback in self.callbacks.connection_removed:
                    callback(widget=self, joystick_id=joystick_id, robot_id=robot_id, sender=sender)

        elif event == 'joystick_double_click':
            joystick_id = data.get('joystick_id')
            self.logger.debug(f"Joystick double-clicked: {joystick_id}")
            for callback in self.callbacks.joystick_double_click:
                callback(widget=self, joystick_id=joystick_id, sender=sender)

        elif event == 'robot_double_click':
            robot_id = data.get('robot_id')
            self.logger.debug(f"Robot double-clicked: {robot_id}")
            for callback in self.callbacks.robot_double_click:
                callback(widget=self, robot_id=robot_id, sender=sender)

        elif event == 'clear_all':
            self._connections.clear()
            self.config['connections'] = self._connections
            self.logger.debug("All connections cleared")
            for callback in self.callbacks.clear_all:
                callback(widget=self, sender=sender)

        elif event == 'auto_assign':
            self.autoAssign()
            self.logger.debug("Auto-assigned joysticks to robots")
            for callback in self.callbacks.auto_assign:
                callback(widget=self, connections=self._connections.copy(), sender=sender)

    def init(self, *args, **kwargs):
        pass

    # === PRIVATE METHODS ==============================================================================================
    def _sendStateUpdate(self):
        """Send current state to frontend."""
        self.function(
            function_name='updateState',
            args={
                'joysticks': self._joysticks,
                'robots': self._robots,
                'connections': self._connections,
            }
        )
