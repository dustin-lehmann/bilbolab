from typing import Any

from core.utils.callbacks import CallbackContainer, callback_definition
from extensions.gui.src.lib.objects.objects import Widget
from core.utils.dict_utils import update_dict, ObservableDict


# === CIRCLE INDICATOR =================================================================================================
class CircleIndicator(Widget):
    type = 'circle_indicator'

    def __init__(self, widget_id=None, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'background_color': 'transparent',
            'color': [1, 1, 1, 0.8],  # Color of the circle indicator
            'visible': True,  # Whether the circle indicator is visible
            'size': 50,  # Diameter of the circle indicator in percentage of the widget's width
            'blinking': False,  # Whether the circle indicator is blinking
            'blinking_frequency': 1.0,  # Speed of the blinking animation
        }

        self.config = {**default_config, **kwargs}

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            **self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> Any:
        self.logger.warning(
            f"CircleIndicator {self.id} received message: {message} from {sender}. Should not receive messages.")

    # ------------------------------------------------------------------------------------------------------------------
    def blink(self, time=250):
        self.function(function_name='singleBlink', args=time)


# === LOADING INDICATOR ================================================================================================
class LoadingIndicator(Widget):
    type = 'loading_indicator'

    visible: bool
    spinning: bool

    def __init__(self, widget_id, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'background_color': 'transparent',
            'color': [0.8, 0.8, 0.8],  # Color of the loading indicator
            'thickness': 20,  # Percentage of the width of the circle relative to its diameter
            'size': 50,  # Size of the loading indicator in percentage of the widget's width
            'speed': 1.0,  # Speed of the spinning animation
            'spinning': True,
            'visible': True,  # Whether the loading indicator is visible
        }

        self.config = {**default_config, **kwargs}

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def visible(self):
        return self.config.get('visible')

    @visible.setter
    def visible(self, value: bool):
        self.config['visible'] = value
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def spinning(self):
        return self.config.get('spinning')

    @spinning.setter
    def spinning(self, value: bool):
        self.config['spinning'] = value
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            **self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        pass

    def handleEvent(self, message, sender=None) -> Any:
        self.logger.warning(
            f"LoadingIndicator {self.id} received message: {message} from {sender}. Should not receive messages.")


# === PROGRESS INDICATOR ===============================================================================================
class ProgressIndicator(Widget):
    type = 'progress_indicator'
    value: float  # Value between 0 and 1

    def __init__(self, widget_id, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'background_color': 'transparent',
            'track_fill_color': [0, 0.8, 0, 0.5],  # Color of the progress indicator
            'track_visible': True,
            'type': 'linear',  # Type of the progress indicator (linear or circular)
            'direction': 'horizontal',  # Direction of the progress indicator (horizontal or vertical)
            'thickness': 10,  # Percentage of the line thickness relative to its width
            'thickness_mode': 'absolute',
            'value': 0.0,  # Value of the progress indicator
            'title': '',  # Title of the progress indicator
            'title_position': 'top',  # 'top' or 'left'
            'label': '',  # Label of the progress indicator
            'label_position': 'bottom',  # 'bottom' or 'right'
        }

        self.config = update_dict(self.config, default_config, kwargs)

        if self.config.get('label_position') == 'right':
            self.logger.warning(
                "ProgressIndicator label_position 'right' is not fully implemented. Use 'bottom' instead.")

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def value(self) -> float:
        return self.config.get('value', 0.0)

    @value.setter
    def value(self, value: float):
        if not (0.0 <= value <= 1.0):
            raise ValueError("Value must be between 0.0 and 1.0")
        self.config['value'] = value
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def label(self) -> str:
        return self.config.get('label', '')

    @label.setter
    def label(self, value: str):
        self.config['label'] = value
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def showTrack(self, show: bool):
        self.config['track_visible'] = show
        self.function(function_name='showBar', args=show)

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> Any:
        self.logger.warrning(
            f"ProgressIndicator {self.id} received message: {message} from {sender}. Should not receive messages.")

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            **self.config,
        }
        return config


# === BATTERY INDICATOR ================================================================================================
class BatteryIndicatorWidget(Widget):
    type = 'battery_indicator'

    def __init__(self, widget_id, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'show': 'percentage',  # 'percentage', 'voltage', or None
            'label_position': 'center',  # 'left', 'center', 'right'
            'label_color': [1, 1, 1, 1],  # RGBA
            'thresholds': {  # thresholds applied to value (0..1)
                'low': 0.2,
                'medium': 0.7,
            },
            'value': 0.6,  # 0.0 .. 1.0
            'voltage': 0.1,  # numeric
            'visible': True,
            'background_color': 'transparent',
        }
        self.config = {**default_config, **kwargs}

    # ----- properties --------------------------------------------------------------------------------------------------
    @property
    def value(self) -> float:
        return self.config.get('value', 0.0)

    @value.setter
    def value(self, v: float):
        if not (0.0 <= v <= 1.0):
            self.logger.warning(f"BatteryIndicatorWidget.value must be between 0.0 and 1.0. Got {v}")
            return
        self.config['value'] = v
        self.updateConfig()

    @property
    def voltage(self) -> float:
        return self.config.get('voltage', 0.0)

    @voltage.setter
    def voltage(self, v: float):
        self.config['voltage'] = v
        self.updateConfig()

    @property
    def show(self) -> str:
        return self.config.get('show', 'percentage')

    @show.setter
    def show(self, mode: str):
        if mode not in ('percentage', 'voltage', None):
            raise ValueError("BatteryIndicatorWidget.show must be 'percentage', 'voltage', or None")
        self.config['show'] = mode
        self.updateConfig()

    @property
    def label_position(self) -> str:
        return self.config.get('label_position', 'right')

    @label_position.setter
    def label_position(self, pos: str):
        if pos not in ('left', 'center', 'right'):
            raise ValueError("BatteryIndicatorWidget.label_position must be 'left', 'center', or 'right'")
        self.config['label_position'] = pos
        self.updateConfig()

    # ----- lifecycle ---------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        return {**self.config}

    def init(self, *args, **kwargs):
        pass

    def handleEvent(self, message, sender=None) -> Any:
        self.logger.warning(
            f"BatteryIndicatorWidget {self.id} received message: {message} from {sender}. Should not receive messages."
        )

    # convenience, mirrors JS setValue
    def setValue(self, percentage: float, voltage: float):
        self.value = percentage
        self.voltage = voltage


# === CONNECTION INDICATOR =============================================================================================
class ConnectionIndicator(Widget):
    type = 'connection_indicator'

    def __init__(self, widget_id, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'color': [0.8, 0.8, 0.8, 1],  # RGBA for filled bars/border
            'value': 'medium',  # 'low', 'medium', 'high'
            'visible': True,
            'background_color': 'transparent',
        }
        self.config = {**default_config, **kwargs}

    # ----- properties --------------------------------------------------------------------------------------------------
    @property
    def value(self) -> str:
        return self.config.get('value', 'medium')

    @value.setter
    def value(self, level: str):
        if level not in ('low', 'medium', 'high'):
            raise ValueError("ConnectionIndicator.value must be 'low', 'medium', or 'high'")
        self.config['value'] = level
        self.updateConfig()

    # ----- lifecycle ---------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        return {**self.config}

    def init(self, *args, **kwargs):
        pass

    def handleEvent(self, message, sender=None) -> Any:
        self.logger.warning(
            f"ConnectionIndicator {self.id} received message: {message} from {sender}. Should not receive messages."
        )

    # convenience
    def setValue(self, level: str):
        self.value = level


# === INTERNET INDICATOR ===============================================================================================
class InternetIndicator(Widget):
    type = 'internet_indicator'

    def __init__(self, widget_id, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'available': True,  # True → icon on; False → crossed out
            'visible': True,
            'background_color': 'transparent',
            'fit_to_container': True,
        }
        self.config = {**default_config, **kwargs}

    # ----- properties --------------------------------------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self.config.get('available', True)

    @available.setter
    def available(self, val: bool):
        self.config['available'] = bool(val)
        self.updateConfig()

    # ----- lifecycle ---------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        return {**self.config}

    def init(self, *args, **kwargs):
        pass

    def handleEvent(self, message, sender=None) -> Any:
        self.logger.warning(
            f"InternetIndicator {self.id} received message: {message} from {sender}. Should not receive messages."
        )

    # convenience
    def setValue(self, available: bool):
        self.available = available


# === NETWORK INDICATOR ================================================================================================
class NetworkIndicator(Widget):
    type = 'network_indicator'

    def __init__(self, widget_id, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'available': True,  # True → icon on; False → crossed out
            'visible': True,
            'background_color': 'transparent',
        }
        self.config = {**default_config, **kwargs}

    # ----- properties --------------------------------------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self.config.get('available', True)

    @available.setter
    def available(self, val: bool):
        self.config['available'] = bool(val)
        self.updateConfig()

    # ----- lifecycle ---------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        return {**self.config}

    def init(self, *args, **kwargs):
        pass

    def handleEvent(self, message, sender=None) -> Any:
        self.logger.warning(
            f"NetworkIndicator {self.id} received message: {message} from {sender}. Should not receive messages."
        )

    # convenience
    def setValue(self, available: bool):
        self.available = available


# === JOYSTICK INDICATOR ===============================================================================================
@callback_definition
class JoystickIndicatorCallbacks:
    click: CallbackContainer


class JoystickIndicator(Widget):
    type = 'joystick_indicator'

    def __init__(self, widget_id, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'available': True,
            'use_png_icon': True,  # choose img vs emoji/div on front‑end
            'png_icon_path': '/gamepad.png',  # path for PNG icon (if used client‑side)
            'visible': True,
            'background_color': 'transparent',
        }
        self.config = {**default_config, **kwargs}
        self.callbacks = JoystickIndicatorCallbacks()

    # ----- properties --------------------------------------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self.config.get('available', True)

    @available.setter
    def available(self, val: bool):
        self.config['available'] = bool(val)
        self.updateConfig()

    @property
    def use_png_icon(self) -> bool:
        return self.config.get('use_png_icon', True)

    @use_png_icon.setter
    def use_png_icon(self, val: bool):
        self.config['use_png_icon'] = bool(val)
        self.updateConfig()

    @property
    def png_icon_path(self) -> str:
        return self.config.get('png_icon_path', '/gamepad.png')

    @png_icon_path.setter
    def png_icon_path(self, path: str):
        self.config['png_icon_path'] = path
        self.updateConfig()

    # ----- lifecycle ---------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        return {**self.config}

    def init(self, *args, **kwargs):
        pass

    def handleEvent(self, message, sender=None) -> Any:
        if message['event'] == 'click':
            self.callbacks.click.call()

    # convenience
    def setValue(self, available: bool):
        self.available = available
