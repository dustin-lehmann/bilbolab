import dataclasses
import time
from typing import Iterable, List, Sequence, Tuple, Union, Optional

from core.utils.exit import register_exit_callback
from core.utils.websockets import WebsocketClient
from core.utils.network.network import resolveHostname
from core.utils.time import wait_until

# === LIMBO BAR INDICATOR ==============================================================================================
WEBSOCKET_PORT = 7777
DEFAULT_HOST = "display.lan"

# Local defaults (also carried in the config we can push to the Pi)
HEIGHT_OFFSET_TO_PIXEL_0 = 0.0  # physical height (same units as 'height') at pixel 0
DISTANCE_BETWEEN_PIXELS = 17  # distance (same units) between successive pixels
DEFAULT_HEIGHT_COLOR = (50, 0, 50)
DEFAULT_NUM_PIXELS = 30
DEFAULT_MAX_BRIGHTNESS = 40  # max per-channel value after scaling (0..255)


def _as_color_triplet(
        color: Union[Sequence[int], Tuple[int, int, int]],
        max_brightness: Optional[int] = None
) -> Tuple[int, int, int]:
    """
    Convert to (r,g,b) clamped to 0..255 and (optionally) scale down uniformly so that
    no channel exceeds max_brightness, preserving the overall color ratios.

    Example:
      (200, 50, 0) with max_brightness=100 -> scale by 0.5 -> (100, 25, 0)
    """
    r, g, b = int(color[0]), int(color[1]), int(color[2])
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))

    if max_brightness is None:
        return (r, g, b)

    mb = int(max_brightness)
    mb = max(0, min(255, mb))
    if mb == 0:
        return (0, 0, 0)

    peak = max(r, g, b)
    if peak <= mb:
        return (r, g, b)

    scale = mb / float(peak)
    rr = int(round(r * scale))
    gg = int(round(g * scale))
    bb = int(round(b * scale))

    # Safety (rounding could barely overshoot)
    rr = min(rr, mb)
    gg = min(gg, mb)
    bb = min(bb, mb)
    return (rr, gg, bb)


@dataclasses.dataclass
class HeightIndicatorConfig:
    height_offset_to_pixel_0: float = HEIGHT_OFFSET_TO_PIXEL_0
    distance_between_pixels: float = DISTANCE_BETWEEN_PIXELS
    height_color: Tuple[int, int, int] = dataclasses.field(
        default_factory=lambda: _as_color_triplet(DEFAULT_HEIGHT_COLOR))
    num_pixels: int = DEFAULT_NUM_PIXELS
    websocket_port: int = WEBSOCKET_PORT
    max_brightness: int = DEFAULT_MAX_BRIGHTNESS  # applied client-side before sending


class TestbedLimboIndicator:
    client: WebsocketClient
    connected: bool = False

    # Local client-side state you can read/persist from your GUI
    current_height: float | None = None
    current_height_pixels: List[int] = dataclasses.field(default_factory=list)  # type: ignore[assignment]
    config: HeightIndicatorConfig

    # === INIT =========================================================================================================
    def __init__(
            self,
            host: str = DEFAULT_HOST,
            port: int = WEBSOCKET_PORT,
            max_brightness: int = DEFAULT_MAX_BRIGHTNESS
    ):

        host_ip = resolveHostname(host)

        self.client = WebsocketClient(host_ip, port)
        self.client.callbacks.connected.register(self._websocket_connected_callback)
        self.client.callbacks.disconnected.register(self._websocket_disconnected_callback)

        self.max_brightness = int(max(0, min(255, max_brightness)))

        # initialize client-side state
        self.current_height = None
        self.current_height_pixels = []
        self.config = HeightIndicatorConfig(websocket_port=port, max_brightness=self.max_brightness)

        register_exit_callback(self.close, priority=100)

        # Optional: set True if you want to attempt to connect automatically on first send.
        # Per your request ("before sending things, check if it's connected"), default is False.
        self._auto_connect_on_send = False

        # Optional: store last send error for debugging / GUI display (not required)
        self._last_send_error: Optional[str] = None

    # === STATE ACCESS ================================================================================================
    def get_state_dict(self) -> dict:
        """
        Snapshot local client-side state (useful for GUI persistence).
        Note: This reflects what you last *sent* from the client, not what the Pi computed/rendered.
        """
        return {
            "connected": bool(self.connected),
            "current_height": self.current_height,
            "current_height_pixels": list(self.current_height_pixels),
            "max_brightness": int(self.max_brightness),
            "config": dataclasses.asdict(self.config),
            "last_send_error": self._last_send_error,
        }

    # === METHODS ======================================================================================================
    def start(self):
        # WebsocketClient.connect() should be safe, but we still guard so callers can call start() freely.
        try:
            self.client.connect()
            result = wait_until(lambda: self.connected, timeout_s=2)
            return result


        except Exception as e:  # noqa: BLE001
            # Don't crash the app if networking isn't available.
            self.connected = False
            self._last_send_error = f"{type(e).__name__}: {e}"
            return False

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        try:
            self.clear()
            time.sleep(2)
        finally:
            try:
                self.client.close()
            except Exception as e:  # noqa: BLE001
                self.connected = False
                self._last_send_error = f"{type(e).__name__}: {e}"

    # ------------------------------------------------------------------------------------------------------------------
    def setConfig(self, config: HeightIndicatorConfig):
        """
        Send runtime configuration to the Pi.
        You can change mapping parameters, num_pixels, and height_color.

        Note: max_brightness is applied client-side before sending colors. We also
        include it in the config payload for completeness (the Pi may ignore it).
        """
        # Adopt brightness locally so subsequent sends are scaled
        self.max_brightness = int(max(0, min(255, int(config.max_brightness))))

        # Update local client-side state
        # Keep websocket_port consistent with the actual connection port we were constructed with.
        config = dataclasses.replace(config, websocket_port=self.config.websocket_port,
                                     max_brightness=self.max_brightness)
        self.config = config

        config_dict = dataclasses.asdict(config)
        self.send({'type': 'set_config', 'data': config_dict})

    # ------------------------------------------------------------------------------------------------------------------
    def setMaxBrightness(self, max_brightness: int):
        """Set client-side max per-channel brightness (0..255)."""
        self.max_brightness = int(max(0, min(255, int(max_brightness))))
        # Update local config snapshot too (so GUI persistence stays consistent)
        self.config = dataclasses.replace(self.config, max_brightness=self.max_brightness)

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self):
        """Turn everything off."""
        # Update local client-side state
        self.current_height = None
        self.current_height_pixels = []
        self.send({'type': 'clear'})

    # ------------------------------------------------------------------------------------------------------------------
    def setPixel(self, index: int, color: Union[Sequence[int], Tuple[int, int, int]]):
        """Set a single pixel to a color (scaled to max_brightness)."""
        r, g, b = _as_color_triplet(color, self.max_brightness)
        self.send({'type': 'set_pixel', 'data': {'index': int(index), 'color': [r, g, b]}})

    # ------------------------------------------------------------------------------------------------------------------
    def fill(self, color: Union[Sequence[int], Tuple[int, int, int]]):
        """Fill the entire strip with a color (scaled to max_brightness)."""
        r, g, b = _as_color_triplet(color, self.max_brightness)
        self.send({'type': 'set_all', 'data': {'color': [r, g, b]}})

    # ------------------------------------------------------------------------------------------------------------------
    def blink(self, color: Union[Sequence[int], Tuple[int, int, int]], num_blinks: int = 1, time_ms: int = 250):
        """Flash the whole strip a number of times (scaled to max_brightness)."""
        r, g, b = _as_color_triplet(color, self.max_brightness)
        self.send({'type': 'blink', 'data': {'color': [r, g, b], 'times': int(num_blinks), 'time_ms': int(time_ms)}})

    # ------------------------------------------------------------------------------------------------------------------
    def blinkRed(self):
        self.blink((255, 0, 0), 3, 150)

    # ------------------------------------------------------------------------------------------------------------------
    def blinkGreen(self):
        self.blink((0, 255, 0), 3, 150)

    # ------------------------------------------------------------------------------------------------------------------
    def setHeight(self, height: float | None):
        """
        Ask the Pi to compute and render the nearest pixel for a given physical height
        using its current mapping config.
        """
        # Update local client-side state (what we requested)
        self.current_height = height
        self.current_height_pixels = []
        self.send({'type': 'set_height', 'data': {'height': height}})

    # ------------------------------------------------------------------------------------------------------------------
    def setHeightPixels(self, height_pixels: Iterable[int]):
        """
        Light multiple pixel indices at once using the Pi's configured height color.
        """
        indices: List[int] = [int(i) for i in height_pixels]
        # Update local client-side state (explicit indices)
        self.current_height = None
        self.current_height_pixels = list(indices)
        self.send({'type': 'set_height_pixels', 'data': {'indices': indices}})

    # === PRIVATE METHODS ==============================================================================================
    def send(self, data: dict):
        """
        Safe send:
        - If not connected, do nothing (but keep local state updated by callers).
        - If sending throws, suppress and mark disconnected to avoid repeated errors.
        """
        if not self.connected:
            if self._auto_connect_on_send:
                self.start()
            if not self.connected:
                return

        try:
            self.client.send(data)
            self._last_send_error = None
        except Exception as e:  # noqa: BLE001
            # Don't crash the app if the connection drops mid-run.
            self.connected = False
            self._last_send_error = f"{type(e).__name__}: {e}"

    # ------------------------------------------------------------------------------------------------------------------
    def _websocket_connected_callback(self, *args, **kwargs):
        self.connected = True
        self._last_send_error = None
        self.blinkGreen()

    # ------------------------------------------------------------------------------------------------------------------
    def _websocket_disconnected_callback(self, *args, **kwargs):
        self.connected = False


if __name__ == '__main__':
    height_indicator = TestbedLimboIndicator()
    height_indicator.start()

    while not height_indicator.connected:
        time.sleep(1)
    # Tiny demo script (safe to remove)
    height_indicator.clear()
    time.sleep(0.5)

    # cfg = HeightIndicatorConfig()
    # height_indicator.setConfig(cfg)
    #
    # time.sleep(1)
    #
    height_indicator.setHeight(200)
    time.sleep(3)
    #
    # # Example: read local state snapshot
    # print(height_indicator.get_state_dict())
    #
    # time.sleep(3)

    while True:

        # height_indicator.blinkRed()
        # time.sleep(30)
    #     height_indicator.blinkGreen()
        time.sleep(3)
