import time
from datetime import datetime
from typing import Any

from core.utils.dict_utils import update_dict
from extensions.gui.src.lib.objects.objects import Widget


class DigitalNumberWidget(Widget):
    type: str = "digital_number"
    value: int | float

    def __init__(self, widget_id: str = None,
                 value: int | float = 0,
                 min_value: int | float = 0,
                 max_value: int | float = 100,
                 increment: int | float = 1,
                 warn_on_out_of_bounds: bool = True,
                 **kwargs):
        super().__init__(widget_id)

        # Default configuration

        default_config = {
            'title': None,
            'title_position': 'left',  # 'left' or 'top'
            'show_unused_digits': True,
            'color': [0.5, 0.5, 0.5, 0.0],
            'text_color': [1.0, 1.0, 1.0],
            'value_color': [1.0, 1.0, 1.0],
            'color_ranges': [],
        }

        self.config = {**default_config, **kwargs}

        self.warn_on_out_of_bounds = warn_on_out_of_bounds

        self.min_value = min_value
        self.max_value = max_value
        self.increment = increment

        self.value = value

        if self.config['title'] is None:
            self.config['title'] = widget_id

    # ------------------------------------------------------------------------------------------------------
    @property
    def value(self) -> int | float:
        return self._value

    @value.setter
    def value(self, new_value: int | float):
        if not isinstance(new_value, (int, float)):
            raise ValueError("Value must be an integer or float.")

        self._value = new_value
        self._sendValueToFrontend(new_value)

    # ------------------------------------------------------------------------------------------------------
    def _sendValueToFrontend(self, value):
        self.sendUpdate(value)

    # ------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            'value': self.value,
            'min_value': self.min_value,
            'max_value': self.max_value,
            'increment': self.increment,
            **self.config
        }
        return config

    def handleEvent(self, message, sender=None) -> Any:
        self.logger.error(f"DigitalNumberWidget does not support handleEvent: {message}")

    def init(self, *args, **kwargs):
        pass


class DigitalClockWidget(Widget):
    type: str = "digital_clock"

    _start_time: float | None = None  # monotonic start time when running
    _stopped_time: float | None = None  # accumulated seconds when stopped; None => placeholder
    _running: bool = False

    # === INIT =====================================================================================================
    def __init__(self, widget_id: str = None, **kwargs):
        super().__init__(widget_id)

        default_config = {
            "visible": True,
            "color": [0, 0, 0, 0],
            "text_color": [1.0, 1.0, 1.0, 0.8],
            "display_format": "HH:mm:ss.SS",

            # relative timer state
            "running": False,
            "increment": 0.1,  # discrete step size in seconds
            "allow_negative": False,

            # default placeholder
            "value": None,
        }

        self.config = update_dict(default_config, kwargs)

        self._running = bool(self.config.get("running", False))
        cfg_value = self.config.get("value", None)
        self._stopped_time = None if cfg_value is None else float(cfg_value)

        # Cannot be running with None value
        if self._running and self._stopped_time is None:
            self._running = False
            self.config["running"] = False

        self._start_time = time.monotonic() if self._running else None

    # === INTERNAL ===================================================================================================
    def _inc_safe(self) -> float:
        inc = float(self.config.get("increment", 0.1) or 0.1)
        return inc if inc > 0 else 0.1

    def _quantize(self, v: float) -> float:
        inc = self._inc_safe()
        q = round(v / inc) * inc
        return float(f"{q:.9f}")

    # === PROPERTIES ===================================================================================================
    @property
    def value(self) -> float | None:
        """
        Current clock value in seconds, or None => placeholder.
        Uses discrete stepping based on increment:
            base + floor(elapsed/inc)*inc
        """
        if self._stopped_time is None:
            return None

        base = float(self._stopped_time)

        if not self._running or self._start_time is None:
            return self._quantize(base)

        inc = self._inc_safe()
        elapsed = time.monotonic() - self._start_time
        steps = int(elapsed // inc) * inc
        v = base + steps

        if not self.config.get("allow_negative", False):
            v = max(0.0, v)

        return self._quantize(v)

    # === CONFIG ===================================================================================================
    def getConfiguration(self) -> dict:
        return {
            **self.config,
            "running": self._running,
            "value": self.value,
        }

    # === FRONTEND CONTROL =========================================================================================
    def start(self):
        """
        Start the relative clock.
        If value is None, start from 0.0 (or keep whatever was set).
        """
        if self._running:
            self.config["running"] = True
            return self.function(function_name="start", args=None)

        if self._stopped_time is None:
            self._stopped_time = 0.0
            self.config["value"] = 0.0

        self._running = True
        self.config["running"] = True
        self._start_time = time.monotonic()

        self.function(function_name="set", args=self.value)
        self.function(function_name="start", args=None)

    def stop(self):
        """
        Stop the relative clock and freeze the value.
        """
        if not self._running:
            self._running = False
            self.config["running"] = False
            self.config["value"] = self._stopped_time if self._stopped_time is not None else None
            return self.function(function_name="stop", args=None)

        frozen = self.value  # quantized float (not None)
        self._stopped_time = float(frozen) if frozen is not None else None

        self._running = False
        self.config["running"] = False
        self.config["value"] = self._stopped_time
        self._start_time = None

        self.function(function_name="stop", args=None)
        self.function(function_name="set", args=self.value)

    def set(self, seconds: float | None):
        """
        Set the clock to seconds, or None => placeholder.
        - If None: stops and shows placeholder
        - If float: sets base; if running, continues from that base
        """
        if seconds is None:
            self._running = False
            self.config["running"] = False
            self._start_time = None
            self._stopped_time = None
            self.config["value"] = None
            # JS set() treats null/undefined as placeholder
            return self.function(function_name="set", args=None)

        v = float(seconds)
        if not self.config.get("allow_negative", False):
            v = max(0.0, v)

        v = self._quantize(v)

        self._stopped_time = v
        self.config["value"] = v

        if self._running:
            self._start_time = time.monotonic()

        self.function(function_name="set", args=v)

    def reset(self):
        """
        Reset to placeholder by default.
        """
        self.stop()
        self.set(None)

    def set_to_wall_clock_now(self):
        """
        Set to current wall clock time-of-day (seconds since midnight).
        """
        now = datetime.now()
        seconds = (
                now.hour * 3600
                + now.minute * 60
                + now.second
                + now.microsecond / 1_000_000.0
        )
        self.set(seconds)
        self.function(function_name="setToWallClockNow", args=None)

    # === EVENTS ===================================================================================================
    def handleEvent(self, message, sender=None) -> Any:
        self.logger.error(f"DigitalClockWidget does not support handleEvent: {message}")

    def init(self, *args, **kwargs):
        pass
