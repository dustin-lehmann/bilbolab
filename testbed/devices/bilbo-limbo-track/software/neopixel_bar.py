import dataclasses
import time
import threading
from typing import Any, Dict, List, Tuple, Optional

from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.network import getHostIP
from core.utils.thread_utils import run_in_thread
from core.utils.websockets import WebsocketServer

import board
import neopixel

# Defaults (can be overridden by config messages from the PC)
DEFAULT_WEBSOCKET_PORT = 7777
DEFAULT_NUM_PIXELS = 30
DEFAULT_HEIGHT_OFFSET_TO_PIXEL_0 = 10.0  # physical height (same units as 'height') at pixel 0
DEFAULT_DISTANCE_BETWEEN_PIXELS = 16.5  # distance (same units) between successive pixels
# DEFAULT_HEIGHT_COLOR = (0, 0, 255)  # color for "height" indicator pixels
DEFAULT_HEIGHT_COLOR = (128,0,128)

DEFAULT_BLUE = (0, 0, 255)
DEFAULT_OFF = (0, 0, 0)

PIN = board.D18



@dataclasses.dataclass
class HeightIndicatorConfig:
    """Runtime-configurable parameters for mapping and visuals."""
    height_offset_to_pixel_0: float = DEFAULT_HEIGHT_OFFSET_TO_PIXEL_0
    distance_between_pixels: float = DEFAULT_DISTANCE_BETWEEN_PIXELS
    height_color: Tuple[int, int, int] = DEFAULT_HEIGHT_COLOR
    num_pixels: int = DEFAULT_NUM_PIXELS
    websocket_port: int = DEFAULT_WEBSOCKET_PORT


class HeightIndicator:
    server: WebsocketServer
    pixel_states: List[List[int]]

    # ==================================================================================================================
    def __init__(self, config: Optional[HeightIndicatorConfig] = None):
        self.logger = Logger('HeightIndicator', 'DEBUG')

        # Load initial config (can be changed later via websocket)
        self.config = config or HeightIndicatorConfig()

        host = getHostIP()
        if host is None:
            self.logger.error("Could not get host IP.")
            raise RuntimeError("No host IP found")

        # Start websocket server
        self.server = WebsocketServer(host, self.config.websocket_port, heartbeats=False)
        self.server.callbacks.new_client.register(self._newClient_callback)
        self.server.callbacks.message.register(self._client_message_callback)

        # Initialize LEDs
        self.pixels = neopixel.NeoPixel(PIN, self.config.num_pixels, auto_write=False)

        # Track intended/desired LED state here. Rendering applies this to hardware.
        self.pixel_states = [[0, 0, 0] for _ in range(self.config.num_pixels)]

        # Concurrency controls for flashing
        self._lock = threading.RLock()
        self._flash_thread = None
        self._flash_stop = threading.Event()

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def start(self):
        self.logger.info(
            f"Starting Height Indicator on ws://{self.server.host}:{self.config.websocket_port} "
            f"with {self.config.num_pixels} pixels"
        )

        # Put some rainbow initialization thing here
        run_in_thread(self.run_init_animation)

        self.server.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        with self._lock:
            self.pixels.fill(DEFAULT_OFF)
            self.pixels.show()
        self.server.close()

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self):
        """Clear the desired state and render."""
        with self._lock:
            self.pixel_states = [[0, 0, 0] for _ in range(len(self.pixel_states))]
            self._render_current_states_unlocked()

    # ------------------------------------------------------------------------------------------------------------------
    def setAll(self, r: int, g: int, b: int):
        """Set all LEDs to a color in desired state and render."""
        with self._lock:
            for i in range(len(self.pixel_states)):
                self.pixel_states[i] = [int(r), int(g), int(b)]
            self._render_current_states_unlocked()

    # ------------------------------------------------------------------------------------------------------------------
    def setPixel(self, idx: int, color: Tuple[int, int, int]):
        """Set a single pixel in desired state and render."""
        with self._lock:
            n = self._clamp_index(idx)
            self.pixel_states[n] = [int(color[0]), int(color[1]), int(color[2])]
            self._render_current_states_unlocked()

    # ------------------------------------------------------------------------------------------------------------------
    def flash(self, color: Tuple[int, int, int], times: int, time_ms: int):
        """Flash whole bar a color in a background thread."""
        self._start_flash_thread(color=color, times=times, time_ms=time_ms)

    # ------------------------------------------------------------------------------------------------------------------
    def setHeightPixel(self, pixel_num: int):
        """Set desired state to show a single pixel (using height_color) and render."""
        with self._lock:
            n = self._clamp_index(pixel_num)
            # Show only that pixel as height color; others off
            for i in range(len(self.pixel_states)):
                self.pixel_states[i] = [0, 0, 0]
            r, g, b = self.config.height_color
            self.pixel_states[n] = [int(r), int(g), int(b)]
            self._render_current_states_unlocked()

    # ------------------------------------------------------------------------------------------------------------------
    def setHeight(self, height: float):
        """
        Compute nearest pixel index from a physical 'height' using the CONFIGURED calibration constants
        and illuminate that single pixel (using height_color).
        """
        try:
            h = float(height)
        except (TypeError, ValueError):
            self.logger.error(f"Invalid height value: {height}")
            return

        idx = self._height_to_index(h)
        self.setHeightPixel(idx)

    # ------------------------------------------------------------------------------------------------------------------
    def setHeightPixels(self, pixel_indices: List[int]):
        """
        Illuminate multiple pixels at once using height_color.
        """
        with self._lock:
            # Reset to off
            for i in range(len(self.pixel_states)):
                self.pixel_states[i] = [0, 0, 0]

            r, g, b = self.config.height_color
            color = [int(r), int(g), int(b)]
            for raw_idx in pixel_indices:
                idx = self._clamp_index(int(raw_idx))
                self.pixel_states[idx] = color[:]
            self._render_current_states_unlocked()

    # ------------------------------------------------------------------------------------------------------------------
    def run_init_animation(
            self,
            max_channel: int = 20,  # cap per-channel brightness (0..255)
            wipe_step_s: float = 0.015,  # speed of wipe on/off
            wave_duration_s: float = 3,  # how long the wavy motion runs
            wave_fps: int = 40,  # update rate for the wave
            wave_cycles: float = 1.5,  # how many rainbow cycles fit across the strip
            blink_times: int = 3,
            blink_time_s: float = 0.12,
    ):
        """
        Boot animation:
          - Rainbow wipe up
          - Wavy rainbow shift
          - Wipe off
          - White blink
          - Restore desired pixel_states

        Writes directly to hardware (does NOT modify pixel_states).
        """

        def clamp8(x: int) -> int:
            return max(0, min(255, int(x)))

        def clamp_max(x: int) -> int:
            return max(0, min(int(max_channel), int(x)))

        def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
            h = h % 1.0
            i = int(h * 6.0)
            f = (h * 6.0) - i
            p = v * (1.0 - s)
            q = v * (1.0 - f * s)
            t = v * (1.0 - (1.0 - f) * s)
            i %= 6
            if i == 0:
                r, g, b = v, t, p
            elif i == 1:
                r, g, b = q, v, p
            elif i == 2:
                r, g, b = p, v, t
            elif i == 3:
                r, g, b = p, q, v
            elif i == 4:
                r, g, b = t, p, v
            else:
                r, g, b = v, p, q
            return (clamp8(r * 255), clamp8(g * 255), clamp8(b * 255))

        n = int(self.config.num_pixels)
        if n <= 0:
            return

        max_channel = max(0, min(255, int(max_channel)))
        white = (max_channel, max_channel, max_channel)

        try:
            # Start clean
            with self._lock:
                self.pixels.fill(DEFAULT_OFF)
                self.pixels.show()

            # 1) Wipe up (pixel 0 -> n-1)
            for i in range(n):
                hue = i / max(1, n)  # position-based rainbow
                r, g, b = hsv_to_rgb(hue, 1.0, 1.0)
                with self._lock:
                    self.pixels[i] = (clamp_max(r), clamp_max(g), clamp_max(b))
                    self.pixels.show()
                time.sleep(max(0.0, float(wipe_step_s)))

            # 2) Wavy / shifting rainbow motion
            #    We shift hue over time; wave_cycles controls "waviness" across the strip.
            frames = max(1, int(float(wave_duration_s) * max(1, int(wave_fps))))
            dt = 1.0 / max(1, int(wave_fps))
            for f in range(frames):
                t = f / max(1, frames)  # 0..1
                phase = t * 1.0  # overall hue shift speed (1.0 = one full turn over duration)
                with self._lock:
                    for i in range(n):
                        # hue varies with position + time shift -> looks like moving wave
                        hue = (i / max(1, n)) * float(wave_cycles) + phase
                        r, g, b = hsv_to_rgb(hue, 1.0, 1.0)
                        self.pixels[i] = (clamp_max(r), clamp_max(g), clamp_max(b))
                    self.pixels.show()
                time.sleep(max(0.0, dt))

            # 3) Wipe off (pixel 0 -> n-1)
            for i in range(n):
                with self._lock:
                    self.pixels[i] = DEFAULT_OFF
                    self.pixels.show()
                time.sleep(max(0.0, float(wipe_step_s)))

            # 4) Blink white
            for _ in range(max(0, int(blink_times))):
                with self._lock:
                    self.pixels.fill(white)
                    self.pixels.show()
                time.sleep(max(0.0, float(blink_time_s)))

                with self._lock:
                    self.pixels.fill(DEFAULT_OFF)
                    self.pixels.show()
                time.sleep(max(0.0, float(blink_time_s)))

        finally:
            # Restore desired state
            with self._lock:
                self._render_current_states_unlocked()

    # === PRIVATE METHODS ==============================================================================================
    def _height_to_index(self, height_value: float) -> int:
        offset = float(self.config.height_offset_to_pixel_0)
        dist = float(self.config.distance_between_pixels)
        if dist == 0:
            self.logger.error("distance_between_pixels cannot be zero; using index 0")
            return 0
        idx_float = (height_value - offset) / dist
        idx = int(round(idx_float))
        return self._clamp_index(idx)

    def _clamp_index(self, idx: int) -> int:
        return max(0, min(len(self.pixel_states) - 1, int(idx)))

    def _render_current_states_unlocked(self):
        """
        Apply self.pixel_states to the hardware strip.
        Call only while holding self._lock.
        """
        for i, rgb in enumerate(self.pixel_states):
            r, g, b = rgb
            self.pixels[i] = (int(r), int(g), int(b))
        self.pixels.show()

    def _start_flash_thread(self, color: Tuple[int, int, int], times: int, time_ms: int):
        """
        Start (or restart) a flashing thread. While flashing, the desired pixel_states are NOT modified.
        At the end (or if interrupted), the current pixel_states are re-rendered so any changes made
        during the flash are respected.
        """
        # If a flash is running, stop it first
        with self._lock:
            if self._flash_thread and self._flash_thread.is_alive():
                self._flash_stop.set()
        if self._flash_thread and self._flash_thread.is_alive():
            # Wait outside lock to avoid deadlocks
            self._flash_thread.join(timeout=2)

        # Reset stop flag and start a new thread
        self._flash_stop.clear()
        self._flash_thread = threading.Thread(
            target=self._flash_worker,
            args=(tuple(int(c) for c in color), int(times), int(time_ms)),
            daemon=True
        )
        self._flash_thread.start()

    def _flash_worker(self, color: Tuple[int, int, int], times: int, time_ms: int):
        on_off_delay = max(0, time_ms) / 1000.0
        try:
            for _ in range(max(0, times)):
                if self._flash_stop.is_set():
                    break
                # ON
                with self._lock:
                    self.pixels.fill(color)
                    self.pixels.show()
                self._sleep_interruptible(on_off_delay)
                if self._flash_stop.is_set():
                    break
                # OFF
                with self._lock:
                    self.pixels.fill(DEFAULT_OFF)
                    self.pixels.show()
                self._sleep_interruptible(on_off_delay)
        finally:
            # Restore whatever the current desired state is
            with self._lock:
                self._render_current_states_unlocked()

    def _sleep_interruptible(self, seconds: float):
        """Sleep in small slices so we can react quickly to stop events."""
        end = time.time() + seconds
        slice_s = 0.02
        while time.time() < end:
            if self._flash_stop.is_set():
                return
            time.sleep(min(slice_s, max(0, end - time.time())))

    # ------------------------------------------------------------------------------------------------------------------
    # Websocket callbacks
    def _newClient_callback(self, client):
        self.logger.info(f"New client connected: {client}")

    def _client_message_callback(self, message: Dict[str, Any], *args, **kwargs):
        """
        Expect messages of the form:
        {
            "type": <command>,
            "data": { ... }    # optional, depends on command
        }
        """

        try:
            if not isinstance(message, dict):
                self.logger.warning(f"Ignoring non-dict message: {message!r}")
                return

            msg_type = message.get("type")
            data = message.get("data", {}) or {}

            if msg_type == "ping":
                self.logger.debug("Ping received")
                return

            if msg_type == "set_config":
                # Update runtime config in-place; unknown keys ignored.
                self._apply_config_from_dict(data)
                self.logger.info(f"Applied new config: {self.config}")
                return

            if msg_type == "clear":
                self.clear()
                return

            if msg_type == "set_all":
                color = tuple(int(c) for c in data.get("color", [0, 0, 0]))
                self.setAll(*color)
                return

            if msg_type == "set_pixel":
                idx = int(data.get("index", 0))
                color = tuple(int(c) for c in data.get("color", DEFAULT_BLUE))
                self.setPixel(idx, color)
                return

            if msg_type == "blink":
                color = tuple(int(c) for c in data.get("color", DEFAULT_BLUE))
                times = int(data.get("times", 1))
                time_ms = int(data.get("time_ms", 250))
                self.flash(color, times, time_ms)
                return

            if msg_type == "set_height":
                height = float(data.get("height"))
                self.setHeight(height)
                return

            if msg_type == "set_height_pixel":
                idx = int(data.get("index", 0))
                self.setHeightPixel(idx)
                return

            if msg_type == "set_height_pixels":
                indices = data.get("indices", [])
                if isinstance(indices, list):
                    self.setHeightPixels([int(x) for x in indices])
                else:
                    self.logger.warning(f"Invalid indices payload: {indices!r}")
                return

            self.logger.warning(f"Unknown command received: {msg_type!r} with data={data!r}")

        except Exception as e:
            self.logger.error(f"Error handling message {message!r}: {e}")

    def _apply_config_from_dict(self, cfg: Dict[str, Any]):
        """
        Apply incoming config. If num_pixels changes, resize internal buffers and NeoPixel object.
        """
        # Update basic fields
        changed_num_pixels = False
        new_num_pixels = self.config.num_pixels

        if "height_offset_to_pixel_0" in cfg:
            self.config.height_offset_to_pixel_0 = float(cfg["height_offset_to_pixel_0"])
        if "distance_between_pixels" in cfg:
            self.config.distance_between_pixels = float(cfg["distance_between_pixels"])
        if "height_color" in cfg:
            hc = cfg["height_color"]
            if isinstance(hc, (list, tuple)) and len(hc) == 3:
                self.config.height_color = (int(hc[0]), int(hc[1]), int(hc[2]))
        if "num_pixels" in cfg:
            try:
                new_num_pixels = int(cfg["num_pixels"])
                changed_num_pixels = (new_num_pixels != self.config.num_pixels)
            except Exception:
                self.logger.warning(f"Invalid num_pixels in config: {cfg['num_pixels']!r}")
        if "websocket_port" in cfg:
            # Can't change running port on the fly in this simple impl; log and ignore.
            self.logger.warning("Ignoring websocket_port change at runtime (requires restart)")

        if changed_num_pixels and new_num_pixels > 0:
            with self._lock:
                self.logger.info(f"Reinitializing for new pixel count: {new_num_pixels}")
                self.config.num_pixels = new_num_pixels
                # Resize pixel_states
                old_len = len(self.pixel_states)
                if new_num_pixels > old_len:
                    self.pixel_states.extend([list(DEFAULT_OFF)] * (new_num_pixels - old_len))
                else:
                    self.pixel_states = self.pixel_states[:new_num_pixels]
                # Recreate NeoPixel object
                self.pixels = neopixel.NeoPixel(board.D18, new_num_pixels, auto_write=False)
                # Render current state on new strip
                self._render_current_states_unlocked()


if __name__ == '__main__':
    # You can optionally seed a custom config here; otherwise defaults are used.
    height_indicator = HeightIndicator()
    height_indicator.start()
    #
    # Example behavior for quick smoke-test:
    height_indicator.setHeight(400)  # uses configured mapping
    time.sleep(5)
    height_indicator.flash((0, 100, 0), 5, 200)
    time.sleep(2)
    height_indicator.flash((100, 0, 0), 5, 200)

    while True:
        time.sleep(10)
