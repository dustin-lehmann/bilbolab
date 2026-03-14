from typing import Any, Callable

from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.dict_utils import update_dict
from core.utils.logging_utils import Logger
from extensions.gui.src.lib.objects.objects import Widget, Widget_Callbacks


# === BILBO MODE WIDGET ================================================================================================
@callback_definition
class BilboModeWidgetCallbacks(Widget_Callbacks):
    mode_clicked: CallbackContainer      # Called when a mode is clicked (mode_id)
    mode_changed: CallbackContainer      # Called when the mode changes (old_mode, new_mode)


class BilboModeWidget(Widget):
    """
    Widget for displaying and selecting BILBO control modes as a state machine graph.

    Modes are displayed as colored circles with labels. The current mode is highlighted,
    available modes (reachable from current mode) are shown normally, and unavailable
    modes are dimmed. Lines between modes indicate allowed transitions (edges).

    Can be displayed horizontally or vertically based on the orientation setting.
    """
    type = 'bilbo_mode'

    callbacks: BilboModeWidgetCallbacks

    # Default BILBO modes configuration
    DEFAULT_MODES = [
        {'id': 'OFF', 'name': 'Off', 'color': [0.5, 0.5, 0.5]},
        {'id': 'BALANCING', 'name': 'Balancing', 'color': [0, 0.7, 0]},
        {'id': 'VELOCITY', 'name': 'Velocity', 'color': [0, 0.7, 0.7]},
        {'id': 'POSITION', 'name': 'Position', 'color': [0.7, 0, 0.7]},
    ]

    # Default transitions (edges) - list of [from_mode, to_mode] pairs
    DEFAULT_EDGES = [
        ['OFF', 'BALANCING'],
        ['BALANCING', 'VELOCITY'],
        ['BALANCING', 'POSITION'],
        ['BALANCING', 'OFF'],
        ['VELOCITY', 'POSITION'],
        ['VELOCITY', 'BALANCING'],
        ['VELOCITY', 'OFF'],
        ['POSITION', 'BALANCING'],
        ['POSITION', 'VELOCITY'],
        ['POSITION', 'OFF'],
    ]

    # === INIT =========================================================================================================
    def __init__(self, widget_id: str | None = None, **kwargs):
        super().__init__(widget_id)

        default_config = {
            # Mode data
            'modes': self.DEFAULT_MODES.copy(),
            'edges': self.DEFAULT_EDGES.copy(),
            'current_mode': 'OFF',

            # Layout
            'orientation': 'horizontal',  # 'horizontal' or 'vertical'

            # Styling (sizes are calculated responsively by JS based on widget dimensions)
            'background_color': [0.15, 0.15, 0.18, 0.2],
            'circle_border_width': 2,
            'circle_border_color': [1, 1, 1, 0.3],
            'circle_active_border_color': [1, 1, 1, 0.8],
            'circle_hover_scale': 1.08,

            'label_color': [1, 1, 1, 0.9],

            'line_color': [1, 1, 1, 0.2],
            'line_width': 2,

            'padding': 16,
        }

        self.logger = Logger(f"BilboModeWidget {self.id}", 'DEBUG')
        self.callbacks = BilboModeWidgetCallbacks()

        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)

        # Internal state
        self._modes: list[dict] = list(self.config.get('modes', []))
        self._edges: list[list[str]] = list(self.config.get('edges', []))
        self._current_mode: str = self.config.get('current_mode', 'OFF')

        # Build adjacency for quick lookup
        self._adjacency = self._buildAdjacency()

    # === PROPERTIES ===================================================================================================
    @property
    def modes(self) -> list[dict]:
        return self._modes

    @modes.setter
    def modes(self, value: list[dict]):
        self._modes = list(value) if value else []
        self.config['modes'] = self._modes
        self._adjacency = self._buildAdjacency()
        self._sendStateUpdate()

    @property
    def edges(self) -> list[list[str]]:
        return self._edges

    @edges.setter
    def edges(self, value: list[list[str]]):
        self._edges = list(value) if value else []
        self.config['edges'] = self._edges
        self._adjacency = self._buildAdjacency()
        self._sendStateUpdate()

    @property
    def current_mode(self) -> str:
        return self._current_mode

    @current_mode.setter
    def current_mode(self, value: str):
        if value != self._current_mode:
            old_mode = self._current_mode
            self._current_mode = value
            self.config['current_mode'] = self._current_mode
            self._sendStateUpdate()
            for callback in self.callbacks.mode_changed:
                callback(widget=self, old_mode=old_mode, new_mode=value)

    @property
    def orientation(self) -> str:
        return self.config.get('orientation', 'horizontal')

    @orientation.setter
    def orientation(self, value: str):
        self.config['orientation'] = value
        self._sendStateUpdate()

    # === METHODS ======================================================================================================
    def setMode(self, mode_id: str):
        """Set the current mode."""
        self.current_mode = mode_id

    def setModes(self, modes: list[dict]):
        """Set the list of modes. Each dict should have 'id', 'name', and 'color'."""
        self.modes = modes

    def setEdges(self, edges: list[list[str]]):
        """Set the transitions (edges). Each edge is [from_mode, to_mode]."""
        self.edges = edges

    def setOrientation(self, orientation: str):
        """Set the widget orientation ('horizontal' or 'vertical')."""
        self.orientation = orientation

    def getAvailableModes(self) -> list[str]:
        """Get list of mode IDs that can be reached from the current mode."""
        return self._adjacency.get(self._current_mode, [])

    def isModeAvailable(self, mode_id: str) -> bool:
        """Check if a mode can be reached from the current mode."""
        return mode_id in self._adjacency.get(self._current_mode, [])

    def getModeById(self, mode_id: str) -> dict | None:
        """Get mode configuration by ID."""
        for mode in self._modes:
            if mode['id'] == mode_id:
                return mode
        return None

    def getConfiguration(self) -> dict:
        return {
            'type': self.type,
            'id': self.id,
            'modes': self._modes,
            'edges': self._edges,
            'current_mode': self._current_mode,
            'available_modes': self.getAvailableModes(),
            **{k: v for k, v in self.config.items() if k not in ['modes', 'edges', 'current_mode']},
        }

    def handleEvent(self, message, sender=None) -> Any:
        event = message.get('event')
        data = message.get('data', {})

        if event == 'mode_clicked':
            mode_id = data.get('mode_id')
            if mode_id:
                self.logger.debug(f"Mode clicked: {mode_id}")
                for callback in self.callbacks.mode_clicked:
                    callback(widget=self, mode_id=mode_id, sender=sender)

    def init(self, *args, **kwargs):
        pass

    # === PRIVATE METHODS ==============================================================================================
    def _buildAdjacency(self) -> dict[str, list[str]]:
        """Build adjacency list from edges for quick lookup of available transitions."""
        adjacency = {}
        for mode in self._modes:
            adjacency[mode['id']] = []

        for edge in self._edges:
            if len(edge) >= 2:
                from_mode, to_mode = edge[0], edge[1]
                # Unidirectional: only add from_mode -> to_mode
                if from_mode in adjacency:
                    if to_mode not in adjacency[from_mode]:
                        adjacency[from_mode].append(to_mode)

        return adjacency

    def _sendStateUpdate(self):
        """Send current state to frontend."""
        self.function(
            function_name='updateState',
            args={
                'modes': self._modes,
                'edges': self._edges,
                'current_mode': self._current_mode,
                'available_modes': self.getAvailableModes(),
                'orientation': self.config.get('orientation', 'horizontal'),
            }
        )
