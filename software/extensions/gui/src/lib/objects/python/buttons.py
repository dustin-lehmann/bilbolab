from typing import Any, Callable

from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.dict_utils import update_dict
from core.utils.logging_utils import Logger
from extensions.gui.src.lib.objects.objects import Widget, Widget_Callbacks


# === BUTTON ===========================================================================================================
@callback_definition
class ButtonCallbacks(Widget_Callbacks):
    click: CallbackContainer
    doubleClick: CallbackContainer
    longClick: CallbackContainer
    rightClick: CallbackContainer


class Button(Widget):
    type = 'button'
    text: str
    config: dict

    callbacks: ButtonCallbacks

    # === INIT =========================================================================================================
    def __init__(self, widget_id: str | None = None, text=None, callback: Callable | Callback | None = None, **kwargs):
        super().__init__(widget_id)

        self.text = text if text is not None else widget_id

        default_config = {
            'text': '',
            'color': [0.2, 0.2, 0.2],
            'text_color': [1, 1, 1, 0.8],
            'font_size': 10,
        }

        self.logger = Logger(f"Button {self.id}", 'DEBUG')
        self.callbacks = ButtonCallbacks()

        # self.config = {**default_config, **kwargs}
        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)

        if text is not None:
            self.config['text'] = text

        if callback is not None:
            self.callbacks.click.register(callback, discard_inputs=True)

    # === METHODS ======================================================================================================
    def getConfiguration(self) -> dict:
        config = {
            'type': self.type,
            'id': self.id,
            **self.config,
        }

        return config

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> Any:
        if message['event'] == 'click':
            self.logger.debug(f"Button {self.id} clicked")
            for callback in self.callbacks.click:
                callback(button=self, sender=sender)
        elif message['event'] == 'doubleClick':
            self.logger.debug(f"Button {self.id} double clicked")
            for callback in self.callbacks.doubleClick:
                callback(button=self, sender=sender)
        elif message['event'] == 'longClick':
            self.logger.debug(f"Button {self.id} long clicked")
            for callback in self.callbacks.longClick:
                callback(button=self, sender=sender)
        elif message['event'] == 'rightClick':
            self.logger.debug(f"Button {self.id} right clicked")
            for callback in self.callbacks.rightClick:
                callback(button=self, sender=sender)

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        pass


# === MULTI-STATE BUTTON ===============================================================================================
@callback_definition
class MultiStateButtonCallbacks(Widget_Callbacks):
    click: CallbackContainer
    doubleClick: CallbackContainer
    longClick: CallbackContainer
    rightClick: CallbackContainer
    indicatorClick: CallbackContainer
    state: CallbackContainer


class MultiStateButton(Widget):
    type: str = 'multi_state_button'

    callbacks: MultiStateButtonCallbacks

    config: dict
    states: list[str]
    state: str

    _state_index: int

    # === INIT =========================================================================================================
    def __init__(self, id, states, current_state=None, config=None, **kwargs):
        super().__init__(id)

        default_config = {
            'color': [0.2, 0.2, 0.2],
            'textColor': [1, 1, 1, 0.8],
            'fontSize': 12,
        }

        self.config = update_dict(default_config, kwargs)

        # self.config = {**default_config, **(config or {}), **kwargs}

        # Check the color array. It can be an array of arrays, but then it has to have the same length as the states
        if isinstance(self.config['color'], list) and all(isinstance(color, list) for color in self.config['color']):
            if not len([color for color in self.config['color']]) == len(states):
                raise ValueError("The color array has to have the same length as the states")

        self.logger = Logger(f"MultiStateButton {self.id}", 'DEBUG')
        self.callbacks = MultiStateButtonCallbacks()

        self.states = states

        # Check if all states are strings and different from each other
        if not all(isinstance(state, str) for state in states):
            raise ValueError("All states must be strings")
        if len(states) != len(set(states)):
            raise ValueError("All states must be unique")

        if isinstance(current_state, int):
            self._state_index = current_state
        elif isinstance(current_state, str):
            self._state_index = self.states.index(current_state)
        else:
            self._state_index = 0

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def state(self):
        return self.states[self._state_index]

    # ------------------------------------------------------------------------------------------------------------------
    @state.setter
    def state(self, value):
        if value not in self.states:
            raise ValueError(f"State '{value}' not found in states")

        if value == self.state:
            return

        self._state_index = self.states.index(value)
        self.logger.debug(f"Setting state to {value}")
        for callback in self.callbacks.state:
            callback(button=self, state=value, index=self.state_index)
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def state_index(self):
        return self._state_index

    # ------------------------------------------------------------------------------------------------------------------
    @state_index.setter
    def state_index(self, value):
        value = value % len(self.states)

        if value == self.state_index:
            return

        self._state_index = value
        self.logger.debug(f"Setting state index to {value}")
        for callback in self.callbacks.state:
            callback(button=self, state=self.state, index=self.state_index)

        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def getStateByIndex(self, index):

        # Normalize index
        index = index % len(self.states)
        return self.states[index]

    # ------------------------------------------------------------------------------------------------------------------
    def increaseIndex(self):
        self.state_index = self.state_index + 1

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        configuration = {
            'type': self.type,
            'id': self.id,
            'states': self.states,
            'state': self.state,
            'state_index': self.state_index,
            **self.config,
        }
        return configuration

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> Any:
        match message['event']:
            case 'click':
                # self.state_index = (self.state_index + 1) % len(self.states)
                for callback in self.callbacks.click:
                    callback(button=self, state=self.state, index=self.state_index)
            case 'rightClick':
                # self.state_index = (self.state_index - 1) % len(self.states)
                for callback in self.callbacks.rightClick:
                    callback(button=self, state=self.state, index=self.state_index)
            case 'indicatorClick':
                index = message['data']['index']
                # self.state_index = index % len(self.states)
                for callback in self.callbacks.indicatorClick:
                    callback(button=self, state=self.state, index=self.state_index)

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        pass
