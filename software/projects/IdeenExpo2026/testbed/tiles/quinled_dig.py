"""
QuinLED Dig-Octa controller (WLED-based).

Controls one QuinLED Dig-Octa board running WLED firmware over its JSON API.
Each physical LED strip is mapped to one WLED segment. Multiple boards can be
controlled by instantiating multiple `QuinLEDDig` objects.

Example
-------
    board = QuinLEDDig(
        host="192.168.1.50",
        strips=[
            StripConfig(name="front", length=5),
            StripConfig(name="left",  length=60),
            StripConfig(name="right", length=60),
            StripConfig(name="back",  length=120),
        ],
    )
    board.set_strip("front", (255, 0, 0))
    board.set_led("left", 3, (0, 255, 0))
    board.set_strip_brightness("right", 128)
    board.strip_off("back")
    board.all_off()

Notes
-----
* On the QuinLED Dig-Octa, configure WLED's LED settings so that the strips
  are appended in the same order as passed in `strips=`. The class computes
  segment offsets automatically from the lengths provided here.
* WLED must reachable over HTTP (default port 80).
"""

from __future__ import annotations

import atexit
import signal
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import requests


Color = tuple[int, int, int]


@dataclass
class StripConfig:
    name: str
    length: int
    # Power safety cap, expressed as the maximum allowed per-LED channel sum
    # (R + G + B), 0..765. Examples:
    #   765 → no limit (full white permitted)
    #   255 → ~33 % of max power: (255,0,0) OK, (255,255,255) scaled to (85,85,85)
    # Setting this guarantees you never exceed the configured budget regardless
    # of what color is requested — over-budget colors are scaled down uniformly,
    # preserving hue.
    max_channel_sum: int = 765
    # ---- power model ---- #
    # Current draw of one logical LED at full white (R=G=B=255), in mA.
    # Defaults match a typical WS2811 24 V strip with 6 LEDs per logical
    # pixel (~60 mA/pixel @ full white). Override per strip if you have
    # something different, e.g. 5 V single-LED WS2812B ≈ 60 mA too,
    # high-density 5 V strips can be 50–80 mA.
    mA_per_led_full_white: float = 60.0
    voltage: float = 24.0


@dataclass
class _Strip:
    cfg: StripConfig
    seg_id: int
    start: int
    stop: int  # exclusive

    @property
    def name(self) -> str:
        return self.cfg.name

    @property
    def length(self) -> int:
        return self.cfg.length


class QuinLEDDigError(RuntimeError):
    pass


class QuinLEDDig:
    """Universal controller for a single QuinLED Dig-Octa board (WLED)."""

    def __init__(
        self,
        host: str,
        strips: Sequence[StripConfig],
        port: int = 80,
        timeout: float = 2.0,
        transition_ms: int = 0,
        udp_port: int = 21324,
        off_at_exit: bool = True,
    ) -> None:
        if not strips:
            raise ValueError("At least one strip must be configured.")
        names = [s.name for s in strips]
        if len(set(names)) != len(names):
            raise ValueError(f"Duplicate strip names: {names}")

        self.host = host
        self.port = port
        self.udp_port = udp_port
        self.timeout = timeout
        # WLED transition time in 1/10 s units. 0 = instant (snappy).
        self._tt = max(0, int(round(transition_ms / 100)))

        # Resolve hostname once. mDNS (`.local`) lookups per-request can
        # add ~5 s of latency each, so we never send with an unresolved
        # hostname: until resolution succeeds (background retry below),
        # UDP frames are dropped and HTTP calls fail fast.
        self._ip: str | None
        try:
            self._ip = socket.gethostbyname(host)
        except socket.gaierror:
            self._ip = None
            threading.Thread(
                target=self._resolve_loop, daemon=True,
                name=f'QuinLEDDig-resolve-{host}',
            ).start()

        # Persistent HTTP session → TCP keep-alive, no reconnect per request.
        self._session = requests.Session()

        # Reusable UDP socket for the realtime protocol.
        self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._strips: dict[str, _Strip] = {}
        offset = 0
        for i, cfg in enumerate(strips):
            if cfg.length <= 0:
                raise ValueError(f"Strip {cfg.name!r} length must be > 0")
            self._strips[cfg.name] = _Strip(
                cfg=cfg, seg_id=i, start=offset, stop=offset + cfg.length
            )
            offset += cfg.length
        self._total_leds = offset

        # ----------------------- software state ----------------------- #
        # The class maintains the "intended" pixel buffer, per-strip
        # brightness/on, and global master brightness/on. Any setter
        # mutates this state and then sends a single UDP frame containing
        # the composited result for the whole chain.
        self._pixel_buf: dict[str, list[Color]] = {
            name: [(0, 0, 0)] * s.length for name, s in self._strips.items()
        }
        self._strip_bri: dict[str, int] = {name: 255 for name in self._strips}
        self._strip_on:  dict[str, bool] = {name: True for name in self._strips}
        self._master_bri: int = 255
        self._master_on:  bool = True
        # WLED realtime hold time (seconds). Max is 255 → effectively
        # "stay in realtime until we send the next packet".
        self._udp_hold: int = 255

        if off_at_exit:
            atexit.register(self._shutdown)
            self._install_signal_handlers()

    @property
    def _base_url(self) -> str:
        return f"http://{self._ip or self.host}:{self.port}"

    def _resolve_loop(self) -> None:
        """Retry hostname resolution until the board appears on the net."""
        while self._ip is None:
            time.sleep(10.0)
            try:
                self._ip = socket.gethostbyname(self.host)
                print(f"[QuinLEDDig] Resolved {self.host} -> {self._ip}")
            except socket.gaierror:
                pass

    def _install_signal_handlers(self) -> None:
        """Catch SIGTERM/SIGINT so the LEDs blank out on `kill` too.

        atexit alone doesn't fire on SIGTERM. We chain to any previously
        installed handler so we don't trample on the user's own setup.
        Only runs in the main thread (signal.signal restriction).
        """
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                prev = signal.getsignal(sig)
                def _handler(signum, frame, _prev=prev):
                    self._shutdown()
                    # Chain to previous handler (or default behavior).
                    if callable(_prev) and _prev not in (
                        signal.SIG_IGN, signal.SIG_DFL
                    ):
                        _prev(signum, frame)
                    else:
                        sys.exit(128 + signum)
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                # Not main thread, or signal unavailable on this platform.
                pass

    def _shutdown(self) -> None:
        """Best-effort blackout. Never raises."""
        try:
            for name in self._strips:
                self._pixel_buf[name] = [(0, 0, 0)] * self._strips[name].length
            self._master_on = False
            self._render()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def strip_names(self) -> list[str]:
        return list(self._strips.keys())

    @property
    def total_leds(self) -> int:
        return self._total_leds

    def strip_length(self, name: str) -> int:
        return self._get(name).length

    # ------------------------------------------------------------------ #
    # Power budget
    # ------------------------------------------------------------------ #
    def set_strip_power_limit(self, name: str, max_channel_sum: int) -> None:
        """Update a strip's per-LED power cap at runtime (0..765)."""
        self._get(name).cfg.max_channel_sum = max(0, min(765, int(max_channel_sum)))

    def _budget(self, strip: _Strip, color: Color) -> list[int]:
        """Clamp + scale a color to fit the strip's per-LED power budget.

        If R+G+B exceeds the configured cap, scale all three channels
        uniformly so the sum equals the cap (preserves hue).
        """
        r, g, b = _clamp_color(color)
        cap = strip.cfg.max_channel_sum
        total = r + g + b
        if cap < 765 and total > cap:
            scale = cap / total
            r = int(r * scale)
            g = int(g * scale)
            b = int(b * scale)
        return [r, g, b]

    # ------------------------------------------------------------------ #
    # Whole-chain frame interface (used by QuinLEDTileDriver)
    # ------------------------------------------------------------------ #
    def show_frame(self, colors: Sequence[Color]) -> None:
        """Overwrite ALL strips in chain order and render once.

        `colors` must contain exactly `total_leds` RGB triples, ordered
        like the configured strips (= WLED output order). Accepts lists
        of tuples or a numpy array of shape (total_leds, 3).
        """
        if len(colors) != self._total_leds:
            raise ValueError(
                f"Expected {self._total_leds} colors, got {len(colors)}"
            )
        for s in self._strips.values():
            self._pixel_buf[s.name] = [
                (int(c[0]), int(c[1]), int(c[2]))
                for c in colors[s.start:s.stop]
            ]
        self._render()

    def init_realtime(self) -> None:
        """Prepare WLED for realtime UDP control.

        WLED scales incoming realtime pixel data by its on-device master
        brightness, so pin it to 255 and turn the device on — all
        brightness handling happens on our side (baked into pixel values).
        """
        self._post_state({'on': True, 'bri': 255})

    # ------------------------------------------------------------------ #
    # Setup — push our segment layout to WLED
    # ------------------------------------------------------------------ #
    def push_segment_layout(self) -> None:
        """Tell WLED about our strip → segment mapping.

        Call once after instantiation (or whenever the configured layout
        changes) so WLED's segments match this object's view of the world.
        """
        seg = []
        for s in self._strips.values():
            seg.append(
                {
                    "id": s.seg_id,
                    "start": s.start,
                    "stop": s.stop,
                    "grp": 1,
                    "spc": 0,
                    "on": True,
                    "bri": 255,
                    "col": [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
                }
            )
        # Disable any extra segments WLED may have lying around.
        for extra_id in range(len(self._strips), 16):
            seg.append({"id": extra_id, "stop": 0})
        self._post_state({"seg": seg})

    # ------------------------------------------------------------------ #
    # Global controls
    # ------------------------------------------------------------------ #
    def all_on(self) -> None:
        self._master_on = True
        self._render()

    def all_off(self) -> None:
        self._master_on = False
        self._render()

    def set_master_brightness(self, brightness: int) -> None:
        """Global brightness cap, applied on top of per-strip brightness."""
        self._master_bri = _clamp_u8(brightness)
        self._render()

    def set_brightness(self, brightness: int) -> None:
        """Per-strip brightness on every strip uniformly.

        Leaves master untouched, so final output ≈ master * strip / 255.
        """
        b = _clamp_u8(brightness)
        for name in self._strips:
            self._strip_bri[name] = b
        self._render()

    def set_all(self, color: Color) -> None:
        """Set every LED on every strip to `color`."""
        for name, s in self._strips.items():
            self._pixel_buf[name] = [color] * s.length
        self._render()

    # ------------------------------------------------------------------ #
    # Per-strip controls
    # ------------------------------------------------------------------ #
    def strip_on(self, name: str) -> None:
        self._get(name)  # validate
        self._strip_on[name] = True
        self._render()

    def strip_off(self, name: str) -> None:
        self._get(name)
        self._strip_on[name] = False
        self._render()

    def set_strip_brightness(self, name: str, brightness: int) -> None:
        self._get(name)
        self._strip_bri[name] = _clamp_u8(brightness)
        self._render()

    def set_strip(self, name: str, color: Color) -> None:
        """Set all LEDs of a single strip to `color`."""
        s = self._get(name)
        self._pixel_buf[name] = [color] * s.length
        self._render()

    def set_led(self, name: str, index: int, color: Color) -> None:
        """Set a single LED (0-based, relative to the strip's start)."""
        s = self._get(name)
        if not 0 <= index < s.length:
            raise IndexError(
                f"LED index {index} out of range for strip {name!r} (0..{s.length - 1})"
            )
        self._pixel_buf[name][index] = color
        self._render()

    def set_leds(self, name: str, pixels: Iterable[tuple[int, Color]]) -> None:
        """Set many individual LEDs on one strip in a single render."""
        s = self._get(name)
        buf = self._pixel_buf[name]
        for index, color in pixels:
            if not 0 <= index < s.length:
                raise IndexError(
                    f"LED index {index} out of range for strip {name!r}"
                )
            buf[index] = color
        self._render()

    def set_strip_pixels(self, name: str, colors: Sequence[Color]) -> None:
        """Overwrite a strip's pixels with the given color sequence."""
        s = self._get(name)
        if len(colors) != s.length:
            raise ValueError(
                f"Expected {s.length} colors for strip {name!r}, got {len(colors)}"
            )
        self._pixel_buf[name] = list(colors)
        self._render()

    def clear_strip(self, name: str) -> None:
        self.set_strip(name, (0, 0, 0))

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #
    def get_state(self) -> dict:
        r = self._session.get(f"{self._base_url}/json/state", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_info(self) -> dict:
        r = self._session.get(f"{self._base_url}/json/info", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------ #
    # Realtime UDP (DNRGB) — every setter composes a frame here
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        """Re-send the current frame. Call periodically (>once per ~200 s)
        if you want to be robust against WLED's realtime timeout."""
        self._render()

    def _render(self) -> None:
        """Compose the entire LED chain from internal state and send it."""
        if self._ip is None:
            return  # board not resolved (yet) — drop the frame
        body = bytearray()
        for _strip, r, g, b in self._iter_rendered():
            body.append(r); body.append(g); body.append(b)
        # DNRGB header: [protocol=4, timeout, start_hi, start_lo]
        header = bytes([4, self._udp_hold, 0, 0])
        self._udp.sendto(header + bytes(body), (self._ip, self.udp_port))

    def _iter_rendered(self):
        """Yield (strip, r, g, b) for every LED, after budget + brightness."""
        for s in self._strips.values():
            on = self._master_on and self._strip_on[s.name]
            bri_factor = (
                (self._master_bri / 255.0) * (self._strip_bri[s.name] / 255.0)
                if on else 0.0
            )
            for color in self._pixel_buf[s.name]:
                if bri_factor == 0.0:
                    yield s, 0, 0, 0
                    continue
                r, g, b = self._budget(s, color)
                yield s, int(r * bri_factor), int(g * bri_factor), int(b * bri_factor)

    # ------------------------------------------------------------------ #
    # Power estimation
    # ------------------------------------------------------------------ #
    def estimated_current_a(self) -> float:
        """Total estimated current draw across all strips, in amps."""
        return sum(self.estimated_current_per_strip().values())

    def estimated_power_w(self) -> float:
        """Total estimated power draw across all strips, in watts."""
        return sum(self.estimated_power_per_strip().values())

    def estimated_current_per_strip(self) -> dict[str, float]:
        """Per-strip current draw estimate, in amps."""
        out: dict[str, float] = {name: 0.0 for name in self._strips}
        for strip, r, g, b in self._iter_rendered():
            # Per-LED current scales with channel sum: (R+G+B)/765 of full-white draw.
            led_mA = ((r + g + b) / 765.0) * strip.cfg.mA_per_led_full_white
            out[strip.name] += led_mA
        return {name: mA / 1000.0 for name, mA in out.items()}

    def estimated_power_per_strip(self) -> dict[str, float]:
        """Per-strip power draw estimate, in watts."""
        amps = self.estimated_current_per_strip()
        return {
            name: amps[name] * self._strips[name].cfg.voltage
            for name in self._strips
        }

    def power_report(self) -> str:
        """Human-readable summary of current/power draw per strip + total."""
        lines = []
        total_a = 0.0
        total_w = 0.0
        for name, s in self._strips.items():
            a = self.estimated_current_per_strip()[name]
            w = a * s.cfg.voltage
            total_a += a
            total_w += w
            lines.append(
                f"  {name:>10s}: {a*1000:6.0f} mA  @ {s.cfg.voltage:4.1f} V  →  {w:5.1f} W"
                f"   ({s.length} LEDs, {s.cfg.mA_per_led_full_white:.0f} mA/LED full white)"
            )
        lines.append(f"  {'TOTAL':>10s}: {total_a*1000:6.0f} mA  →  {total_w:5.1f} W")
        return "\n".join(lines)

    def send_strip_udp(self, name: str, colors: Sequence[Color]) -> None:
        """Convenience: overwrite a strip's pixels and render.

        Kept for backwards compatibility — same effect as `set_strip_pixels`.
        """
        self.set_strip_pixels(name, colors)

    def ping(self) -> bool:
        if self._ip is None:
            return False
        try:
            self.get_info()
            return True
        except requests.RequestException:
            return False

    def test_connection(self, verbose: bool = True) -> bool:
        """End-to-end communication test: HTTP, UDP, and LED count check.

        Returns True if everything looks healthy. With `verbose=True`
        prints a short diagnostic report.

        Checks:
          1. Hostname resolution (already cached in self._ip).
          2. HTTP GET /json/info — confirms WLED is responding.
          3. WLED's configured LED count covers our total_leds.
          4. UDP send to the realtime port — confirms the socket works
             (UDP is connectionless so this only catches local errors).
        """
        ok = True
        lines: list[str] = []

        if self._ip is None:
            if verbose:
                print("Connection test:")
                print(f"  Host:      {self.host}  →  UNRESOLVED "
                      f"(board offline? retrying in background)")
                print("  → PROBLEMS DETECTED")
            return False

        lines.append(f"Host:      {self.host}  →  {self._ip}:{self.port}")

        # 1) HTTP
        try:
            t0 = time.perf_counter()
            info = self.get_info()
            dt = (time.perf_counter() - t0) * 1000
            ver = info.get("ver", "?")
            wled_leds = info.get("leds", {}).get("count")
            name = info.get("name", "?")
            lines.append(
                f"HTTP /info: OK ({dt:.1f} ms)  WLED v{ver}  name={name!r}  leds={wled_leds}"
            )
        except requests.RequestException as e:
            lines.append(f"HTTP /info: FAIL  ({e})")
            wled_leds = None
            ok = False

        # 2) LED count sanity check
        if wled_leds is not None:
            if wled_leds >= self._total_leds:
                lines.append(
                    f"LED count: OK  (board has {wled_leds}, we need {self._total_leds})"
                )
            else:
                lines.append(
                    f"LED count: MISMATCH  WLED reports {wled_leds} but we configured "
                    f"{self._total_leds} — extra LEDs will be ignored by WLED."
                )
                ok = False

        # 3) UDP
        try:
            # Send a no-op DNRGB packet (zero pixels). WLED accepts header-only
            # packets; if not, this is still a valid local socket send test.
            header = bytes([4, self._udp_hold, 0, 0])
            self._udp.sendto(header, (self._ip, self.udp_port))
            lines.append(f"UDP {self.udp_port}: send OK (no reply expected — UDP is fire-and-forget)")
        except OSError as e:
            lines.append(f"UDP {self.udp_port}: FAIL  ({e})")
            ok = False

        if verbose:
            print("Connection test:")
            for ln in lines:
                print(f"  {ln}")
            print(f"  → {'OK' if ok else 'PROBLEMS DETECTED'}")
        return ok

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _get(self, name: str) -> _Strip:
        try:
            return self._strips[name]
        except KeyError:
            raise KeyError(
                f"Unknown strip {name!r}. Known: {list(self._strips)}"
            ) from None

    def _post_state(self, payload: dict) -> dict:
        # "v": False tells WLED not to echo back the full state JSON.
        # "tt": <deciseconds> sets the transition time for this request.
        if self._ip is None:
            raise QuinLEDDigError(
                f"WLED host {self.host!r} not resolved (board offline?)"
            )
        payload = {"v": False, "tt": self._tt, **payload}
        try:
            r = self._session.post(
                f"{self._base_url}/json/state",
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            raise QuinLEDDigError(f"WLED request failed ({self.host}): {e}") from e
        try:
            return r.json()
        except ValueError:
            return {}


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _clamp_u8(v: int) -> int:
    return max(0, min(255, int(v)))


def _clamp_color(c: Color) -> Color:
    r, g, b = c
    return (_clamp_u8(r), _clamp_u8(g), _clamp_u8(b))


# ---------------------------------------------------------------------- #
# Minimal smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    import time

    HOST = "led_controller_1.local"   # change to your board's IP/hostname
    STRIP = "strip1"
    PAUSE = 0.8

    board = QuinLEDDig(
        host=HOST,
        strips=[StripConfig(name=STRIP, length=5)],
    )

    if not board.ping():
        raise SystemExit(f"Cannot reach WLED at {HOST}")

    print(f"Connected. Info: {board.get_info().get('ver', '?')}")

    print("Pushing segment layout...")
    # board.push_segment_layout()
    board.set_master_brightness(255)

    # print("1) Fill whole strip red, then green, then blue")
    # for color in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]:
    #     time1 = time.perf_counter()
    #     board.set_strip(STRIP, color)
    #     time2 = time.perf_counter()
    #     print(f"Color change took {time2 - time1:.3f} seconds")
    #     time.sleep(PAUSE)
    #
    # print("2) Clear, then light LEDs one by one (white)")
    # board.clear_strip(STRIP)
    # time.sleep(PAUSE)
    # for i in range(5):
    #     board.set_led(STRIP, i, (255, 255, 255))
    #     time.sleep(0.3)
    #
    # print("3) Set all 5 pixels to different colors in one request")
    # board.set_strip_pixels(
    #     STRIP,
    #     [(255, 0, 0), (255, 128, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255)],
    # )
    # time.sleep(PAUSE)
    #
    # print("4) Update just LEDs 0 and 4 (set_leds, single request)")
    # board.set_leds(STRIP, [(0, (255, 0, 255)), (4, (0, 255, 255))])
    # time.sleep(PAUSE)
    #
    # print("5) Dim the strip down then back up")
    # for bri in (200, 150, 100, 50, 10, 50, 100, 150, 200, 255):
    #     board.set_strip_brightness(STRIP, bri)
    #     time.sleep(0.15)
    #
    # print("6) Turn the strip off, then back on")
    # board.strip_off(STRIP)
    # time.sleep(PAUSE)
    # board.strip_on(STRIP)
    # time.sleep(PAUSE)

    # print("7) Brightness sweep across all strips (honors master cap)")
    # board.set_all((255, 255, 255))
    # for bri in (255, 0, 64, 0, 128, 0, 255):
    #     board.set_brightness(bri)
    #     time.sleep(1)

    print("8) Breathing — 10 cycles")
    import math
    base_color = (255, 0, 0)
    cycles = 10
    cycle_s = 2.0
    duration = cycles * cycle_s
    fps = 120
    t_start = time.perf_counter()
    next_frame = t_start
    frame_dt = 1 / fps
    while True:
        now = time.perf_counter()
        t = now - t_start
        if t >= duration:
            break
        phase = 2 * math.pi * (t / cycle_s)
        level = (1 - math.cos(phase)) / 2          # 0 → 1 → 0
        level = level ** 2.2                       # perceptual gamma
        rgb = tuple(int(round(c * level)) for c in base_color)
        board.set_strip(STRIP, rgb)
        next_frame += frame_dt
        sleep_for = next_frame - time.perf_counter()
        if sleep_for > 0:
            time.sleep(sleep_for)
        else:
            next_frame = time.perf_counter()      # we fell behind — resync

    print("9) Global off / on")
    board.all_off()
    time.sleep(PAUSE)
    board.all_on()
    time.sleep(PAUSE)

    print("Done — turning everything off.")
    board.all_off()
