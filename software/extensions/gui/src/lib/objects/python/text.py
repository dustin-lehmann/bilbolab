import dataclasses
from typing import Any

from core.utils.dict_utils import ObservableDict, update_dict
from extensions.gui.src.lib.objects.objects import Widget


class TextWidget(Widget):
    type = 'text'

    def __init__(self, widget_id: str = None, text: str = "", **kwargs):
        super().__init__(widget_id)

        default_config = {
            'color': 'transparent',
            'text_color': [1, 1, 1],
            'title': None,
            'font_size': 12,
            'font_family': 'inherit',
            'vertical_alignment': 'center',  # 'center', 'top, 'bottom'
            'horizontal_alignment': 'center',  # 'left', 'right', 'center'
            'font_weight': 'normal',
            'font_style': 'normal',
        }

        self.text = text

        self.config = {**default_config, **kwargs}

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, new_text):
        self._text = new_text
        self.updateConfig()

    def getConfiguration(self) -> dict:
        config = {
            'text': self.text,
            **self.config
        }
        return config

    def handleEvent(self, message, sender=None) -> Any:
        pass

    def init(self, *args, **kwargs):
        pass


# ======================================================================================================================
@dataclasses.dataclass
class StatusWidgetElement:
    label: str = ''
    color: list = dataclasses.field(default_factory=lambda: [0.0, 0.0, 0.0])
    status: str = ''
    label_color: list = dataclasses.field(default_factory=lambda: [1, 1, 1, 0.8])
    status_color: list = dataclasses.field(default_factory=lambda: [1, 1, 1, 0.8])


class StatusWidget(Widget):
    type = 'status'
    elements: dict[str, StatusWidgetElement]

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, widget_id, elements: dict, **kwargs):
        super().__init__(widget_id)

        default_config = {
            'color': 'transparent',
            'text_color': [1, 1, 1],
            'title': None,
            'font_size': 10,
        }

        self.config = {**default_config, **kwargs}

        if elements is None:
            elements = {}

        self._elements = ObservableDict(elements, on_change=self._on_elements_changed)

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def elements(self):
        return self._elements

    @elements.setter
    def elements(self, value):
        self._elements = ObservableDict(value, on_change=self._on_elements_changed)
        self._on_elements_changed()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_elements_changed(self):
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            'elements': {k: dataclasses.asdict(v) for k, v in self.elements.items()},
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> Any:
        self.logger.warning(f"StatusWidget does not support handleEvent: {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        pass


# ======================================================================================================================
class LineScrollWidget(Widget):
    type = 'line_scroll_widget'

    lines: list

    # === INIT =========================================================================================================
    def __init__(self, widget_id: str, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'background_color': [0, 0, 0, 0],
            'font_size': 7,
            'text_color': [1, 1, 1, 0.8],
            'include_time_stamp': True,
        }
        self.lines = []
        self.config = update_dict(default_config, self.config, kwargs)

    # === METHODS ======================================================================================================
    def addLine(self, text, color=None):
        self.lines.append({
            'text': text,
            'color': color if color is not None else self.config['text_color']
        })

        self.function(
            function_name="addLine",
            args=[text, color if color is not None else self.config['text_color']],
            spread_args=True
        )

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            **self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = super().getPayload()
        payload['lines'] = self.lines
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> None:
        pass
    # === PRIVATE METHODS ==============================================================================================
