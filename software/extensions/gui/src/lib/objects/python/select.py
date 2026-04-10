from typing import Any

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.logging_utils import Logger
from extensions.gui.src.lib.objects.objects import Widget


@callback_definition
class MultiSelectWidgetCallbacks:
    """
    Defines callbacks for MultiSelectWidget:
      - selection_changed: fired when the user picks a new option
      - long_click: fired when the user long-presses on the widget
    """
    selection_changed: CallbackContainer
    long_click: CallbackContainer


class MultiSelectWidget(Widget):
    """
    A drop-down (multi-select) widget that shows a list of options, displays the current selection,
    and optionally can be locked to prevent changes.
    """

    type = "multi_select"
    callbacks: MultiSelectWidgetCallbacks

    # === INIT =========================================================================================================
    def __init__(
            self,
            widget_id: str,
            *,
            options: dict = None,
            value=None,
            config: dict | None = None,
            **kwargs
    ):
        super().__init__(widget_id)

        self.logger = Logger(f"MultiSelectWidget {self.id}", "DEBUG")
        self.callbacks = MultiSelectWidgetCallbacks()

        if config is None:
            config = {}

        # Default configuration values
        default_config = {
            "lockable": False,
            "locked": False,
            "title": None,
            "title_position": 'top',  # 'top' or 'left'
            "titleStyle": 'bold',
            "color": [0.2, 0.2, 0.2],
            "text_color": [1, 1, 1],
            "visible": True,
        }

        # Merge defaults, caller args, and any extra kwargs
        self.config = {**default_config, **config, **kwargs}

        if self.config['title'] is None:
            self.config['title'] = self.id

        self.options = options

        # Check if options is looking correct
        if not isinstance(options, dict):
            raise TypeError("options must be a dict")

        if value is not None:
            if value not in self.options:
                raise ValueError(f"Value {value} is not a valid option")

            self.value = value

        # Validate that if color is a list, its length matches options
        col = self.config["color"]
        opts = self.options
        if isinstance(col, list) and len(col) != len(opts) and not (
                isinstance(col, list) and all(isinstance(c, (str, list)) for c in col)
        ):
            # If it’s a list of colors, expect length == len(options).
            self.logger.debug("Color list length does not match number of options; ignoring per-option mapping.")

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, value: Any):
        if value not in self.options:
            self.logger.error(f"Value {value} is not a valid option")
        else:
            self._value = value
        self._sendValueToFrontend(self.value)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        """
        Returns a dictionary describing this widget’s state for front-end rendering.
        """
        config = {
            'type': 'multi_select',
            'id': self.id,
            'options': self.options,
            'value': self.value,
            **self.config,
        }

        return config

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message: dict, sender=None) -> Any:
        """
        Handle incoming messages from the front-end. Expected message shapes:
          { "event": "multi_select_change", "data": { "value": new_value } }
          { "event": "multi_select_long_click" }
        """
        self.logger.debug(f"Received message: {message}")

        if 'event' not in message:
            self.logger.warning(f"Unknown message received: {message}")
            return

        match message['event']:
            case 'multi_select_change':
                self.value = message['data']['value']
                self.callbacks.selection_changed.call(self.value)

        # event = message.get("event")
        # data = message.get("data", {})
        #
        # if event == "multi_select_change":
        #     new_val = data.get("value")
        #     # Only proceed if new_val exists among options or is None
        #     valid_values = [opt["value"] for opt in self.config["options"]]
        #     if new_val not in valid_values and new_val is not None:
        #         self.logger.debug(f"Ignoring invalid selection '{new_val}'.")
        #         return
        #
        #     self.config["value"] = new_val
        #     self.logger.debug(f"Selection changed to {new_val!r}")
        #
        #     # Fire the callback
        #     for cb in self.callbacks.selection_changed:
        #         cb(widget=self, value=new_val)
        #
        # elif event == "multi_select_long_click":
        #     self.logger.debug("Long-click detected on MultiSelectWidget")
        #     for cb in self.callbacks.long_click:
        #         cb(widget=self)
        #
        # return None

    # ------------------------------------------------------------------------------------------------------------------
    def _sendValueToFrontend(self, value):
        self.function(
            function_name='setValue',
            args=value
        )

    # ------------------------------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        """
        Called once when the GUI is first constructed.
        You may push the initial state to the front-end here if needed.
        """
        pass
