#!/usr/bin/env python3
"""
UDP client wrapper for the TestbedDisplay server.

This provides a Python class with (almost) the same API as the display,
but instead of drawing anything it just sends JSON commands via UDP.

Additionally, this client keeps a local copy of the display "state"
(text/title/colors/sizes/icon/image/clock/background, etc.) so a GUI can
read it out and persist it.

Key behavior (per request):
- This client will NOT raise errors if the display is not connected.
- Before sending, it checks `self.connected`. If not connected, it simply
  updates local state and skips sending.
- If a send fails (DNS/socket error, etc.), it marks itself disconnected
  and continues without raising.

Usage example:

    from testbed_display_client import TestbedDisplayClient

    client = TestbedDisplayClient()  # defaults to display.lan:12346
    client.start()                   # sets client.connected True/False (best-effort)

    client.set_background_color((0, 0, 64))
    client.set_title("Hello", color=(255, 215, 0), alignment="center", size=120)
    client.set_text("Main text here", size=160, color=(255, 255, 255), alignment="center")
    client.set_icon("🚀", size=160)
    client.start_clock(mode="overlay", color=(0, 255, 255))  # or mode="replace_text"

    # Read local client-side state any time:
    snapshot = client.get_state_dict(json_ready=True)
    # store snapshot in your GUI persistence layer...

    client.stop_clock()
    client.clear()
    client.quit()
"""

import copy
import json
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Union

ColorType = Union[Tuple[int, int, int], list, dict]

DEFAULT_HOST = "display.lan"
DEFAULT_LISTEN_PORT = 12346

# Keep these defaults in sync with display where it makes sense
DEFAULT_BACKGROUND_COLOR = (0, 0, 0)  # black
DEFAULT_TEXT_COLOR = (255, 255, 255)  # white
DEFAULT_TITLE_COLOR = (200, 200, 200)  # light gray
DEFAULT_CLOCK_COLOR = DEFAULT_TITLE_COLOR

# Per your request: bigger defaults on the sender side
DEFAULT_TEXT_SIZE = 176
DEFAULT_TITLE_SIZE = 200
DEFAULT_ICON_SIZE = 200


# ----------------------------------------------------------------------------------------------------------------------
# Client-side state model
# ----------------------------------------------------------------------------------------------------------------------
@dataclass
class TextBlockState:
    text: Optional[str] = None
    size: int = 0
    color: Tuple[int, int, int] = (255, 255, 255)
    alignment: str = "center"

    def to_dict(self, *, json_ready: bool = False) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "text": self.text,
            "size": int(self.size),
            "alignment": self.alignment,
            "color": list(self.color) if json_ready else tuple(self.color),
        }
        return d


@dataclass
class IconState:
    icon: Optional[str] = None
    size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"icon": self.icon, "size": int(self.size)}


@dataclass
class WallClockState:
    visible: bool = False
    color: Tuple[int, int, int] = DEFAULT_CLOCK_COLOR
    size: int = 60

    def to_dict(self, *, json_ready: bool = False) -> Dict[str, Any]:
        return {
            "visible": self.visible,
            "color": list(self.color) if json_ready else tuple(self.color),
            "size": int(self.size),
        }


@dataclass
class ClockState:
    running: bool = False
    mode: str = "overlay"
    replace_text: Optional[bool] = None
    color: Tuple[int, int, int] = DEFAULT_CLOCK_COLOR

    # Client-side timing (best-effort; display is authoritative)
    started_at_monotonic: Optional[float] = None
    accumulated_ms: int = 0

    def elapsed_ms(self) -> int:
        if not self.running or self.started_at_monotonic is None:
            return int(self.accumulated_ms)
        delta_s = time.monotonic() - self.started_at_monotonic
        return int(self.accumulated_ms + max(0.0, delta_s) * 1000.0)

    def to_dict(self, *, json_ready: bool = False, include_elapsed: bool = True) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "running": bool(self.running),
            "mode": self.mode,
            "replace_text": self.replace_text,
            "color": list(self.color) if json_ready else tuple(self.color),
            "accumulated_ms": int(self.accumulated_ms),
            "started_at_monotonic": self.started_at_monotonic,
        }
        if include_elapsed:
            d["elapsed_ms"] = int(self.elapsed_ms())
        return d


@dataclass
class DisplayState:
    background_color: Tuple[int, int, int] = DEFAULT_BACKGROUND_COLOR

    # Style defaults on the display (these mirror “set_*_color” style ops)
    text_color: Tuple[int, int, int] = DEFAULT_TEXT_COLOR
    title_color: Tuple[int, int, int] = DEFAULT_TITLE_COLOR
    clock_color: Tuple[int, int, int] = DEFAULT_CLOCK_COLOR

    title: TextBlockState = field(
        default_factory=lambda: TextBlockState(
            text=None, size=DEFAULT_TITLE_SIZE, color=DEFAULT_TITLE_COLOR, alignment="center"
        )
    )
    text: TextBlockState = field(
        default_factory=lambda: TextBlockState(
            text=None, size=DEFAULT_TEXT_SIZE, color=DEFAULT_TEXT_COLOR, alignment="center"
        )
    )
    icon: IconState = field(default_factory=lambda: IconState(icon=None, size=DEFAULT_ICON_SIZE))
    image_path: Optional[str] = None

    clock: ClockState = field(default_factory=ClockState)
    wall_clock: WallClockState = field(default_factory=WallClockState)

    # Track last command sent (useful for debugging / GUI)
    last_payload: Optional[Dict[str, Any]] = None
    last_sent_epoch_s: Optional[float] = None

    # Track last send failure (optional debug)
    last_send_error: Optional[str] = None

    def to_dict(self, *, json_ready: bool = False, include_elapsed: bool = True) -> Dict[str, Any]:
        return {
            "background_color": list(self.background_color) if json_ready else tuple(self.background_color),
            "text_color": list(self.text_color) if json_ready else tuple(self.text_color),
            "title_color": list(self.title_color) if json_ready else tuple(self.title_color),
            "clock_color": list(self.clock_color) if json_ready else tuple(self.clock_color),
            "title": self.title.to_dict(json_ready=json_ready),
            "text": self.text.to_dict(json_ready=json_ready),
            "icon": self.icon.to_dict(),
            "image_path": self.image_path,
            "clock": self.clock.to_dict(json_ready=json_ready, include_elapsed=include_elapsed),
            "wall_clock": self.wall_clock.to_dict(json_ready=json_ready),
            "last_payload": copy.deepcopy(self.last_payload),
            "last_sent_epoch_s": self.last_sent_epoch_s,
            "last_send_error": self.last_send_error,
        }


class TestbedDisplayClient:
    """
    A thin client that mimics the display-side API and sends UDP JSON messages
    to a TestbedDisplay server.

    This client also stores a local DisplayState that you can snapshot and persist
    in your GUI.

    Connection semantics:
    - UDP has no real "connected" state. Here, `connected` is an application flag:
      - `start()` calls `ping()` and sets the flag.
      - `_send()` will only send if `connected` is True.
      - If `_send()` encounters an OSError, it marks `connected=False` and suppresses errors.
    """

    connected: bool = False

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_LISTEN_PORT):
        self.host = host
        self.port = port

        self.default_background_color = DEFAULT_BACKGROUND_COLOR
        self.default_text_size = DEFAULT_TEXT_SIZE
        self.default_title_size = DEFAULT_TITLE_SIZE
        self.default_icon_size = DEFAULT_ICON_SIZE

        # Local client-side state (readable by GUI)
        self._state = DisplayState(
            background_color=DEFAULT_BACKGROUND_COLOR,
            text_color=DEFAULT_TEXT_COLOR,
            title_color=DEFAULT_TITLE_COLOR,
            clock_color=DEFAULT_CLOCK_COLOR,
        )

        # Single UDP socket reused for all sends
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Optional: set to True if you ever want to send immediately without calling start().
        # Per your request, we default to requiring `connected=True` to send.
        self._auto_connect_on_send = False

    # ------------------------------------------------------------------------------------------------------------------
    # Public state accessors
    # ------------------------------------------------------------------------------------------------------------------
    def start(self) -> bool:
        """
        Best-effort "connect": attempts a UDP ping send.
        Sets self.connected accordingly.
        """
        self.connected = bool(self.ping())
        return self.connected

    def ping(self) -> bool:
        """
        Best-effort: try to send a small UDP packet to the display.
        Note: UDP provides no acknowledgement; this only verifies we *could* send.
        """
        try:
            sent = self._sock.sendto(b"PING", (self.host, self.port))
            ok = sent == len(b"PING")
            self._state.last_send_error = None
            return ok
        except OSError as e:
            self._state.last_send_error = f"{type(e).__name__}: {e}"
            return False

    def get_state(self) -> DisplayState:
        """Return a deep copy of the current client-side DisplayState."""
        return copy.deepcopy(self._state)

    def get_state_dict(self, *, json_ready: bool = False, include_elapsed: bool = True) -> Dict[str, Any]:
        """
        Snapshot the current client-side state as a dict.

        json_ready=True converts colors to [r,g,b] lists, which is convenient to JSON-dump.
        """
        return self._state.to_dict(json_ready=json_ready, include_elapsed=include_elapsed)

    def set_connected(self, value: bool) -> None:
        """Manually override the connected flag (useful if your app knows the real state)."""
        self.connected = bool(value)

    # ------------------------------------------------------------------------------------------------------------------
    # Low-level send
    # ------------------------------------------------------------------------------------------------------------------
    def _send(self, payload: Dict[str, Any]) -> None:
        """
        Send JSON payload to the display if connected.

        Per request:
        - If not connected, do nothing (but still update local tracking fields).
        - Suppress socket/DNS errors and mark disconnected.
        """
        # Track intent (for GUI/debugging) even if we don't actually send
        self._state.last_payload = copy.deepcopy(payload)

        if not self.connected:
            # Optionally try to connect automatically (off by default)
            if self._auto_connect_on_send:
                self.connected = bool(self.ping())
            if not self.connected:
                return

        try:
            data = json.dumps(payload).encode("utf-8")
            self._sock.sendto(data, (self.host, self.port))
            self._state.last_sent_epoch_s = time.time()
            self._state.last_send_error = None
        except OSError as e:
            # Suppress error, mark as disconnected for future sends
            self.connected = False
            self._state.last_send_error = f"{type(e).__name__}: {e}"

    # ------------------------------------------------------------------------------------------------------------------
    # API methods mirroring the display side
    # ------------------------------------------------------------------------------------------------------------------
    def set_text(
        self,
        text: Optional[str],
        size: int = DEFAULT_TEXT_SIZE,
        color: ColorType = DEFAULT_TEXT_COLOR,
        alignment: str = "center",
    ) -> None:
        """
        Set main text. Vertically centered on the display, alignment controls
        left/center/right horizontally.
        """
        color_t = self._normalize_color_tuple(color)

        # Update local state
        self._state.text.text = text
        self._state.text.size = int(size)
        self._state.text.color = color_t
        self._state.text.alignment = alignment

        msg = {
            "command": "set_text",
            "text": text,
            "size": int(size),
            "color": self._serialize_color(color_t),
            "alignment": alignment,
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def set_text_color(self, color: ColorType = DEFAULT_TEXT_COLOR) -> None:
        """
        Change text color without changing text content or size.
        """
        color_t = self._normalize_color_tuple(color)

        # Update local state (both "default text_color" and current text block color)
        self._state.text_color = color_t
        self._state.text.color = color_t

        msg = {
            "command": "set_text_color",
            "color": self._serialize_color(color_t),
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def set_title(
        self,
        text: Optional[str],
        color: ColorType = DEFAULT_TITLE_COLOR,
        alignment: str = "center",
        size: int = DEFAULT_TITLE_SIZE,
    ) -> None:
        """
        Set a title at the top edge of the display.
        """
        color_t = self._normalize_color_tuple(color)

        # Update local state
        self._state.title.text = text
        self._state.title.size = int(size)
        self._state.title.color = color_t
        self._state.title.alignment = alignment

        msg = {
            "command": "set_title",
            "text": text,
            "size": int(size),
            "color": self._serialize_color(color_t),
            "alignment": alignment,
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def set_title_color(self, color: ColorType = DEFAULT_TITLE_COLOR) -> None:
        """
        Change title color without changing title text or size.
        """
        color_t = self._normalize_color_tuple(color)

        # Update local state
        self._state.title_color = color_t
        self._state.title.color = color_t

        msg = {
            "command": "set_title_color",
            "color": self._serialize_color(color_t),
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def set_icon(self, icon: Optional[str], size: int = DEFAULT_ICON_SIZE) -> None:
        """
        Set a centered icon (emoji string) on the display.
        """
        # Update local state
        self._state.icon.icon = icon
        self._state.icon.size = int(size)

        msg = {
            "command": "set_icon",
            "icon": icon,
            "size": int(size),
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def set_image(self, image_path: Optional[str]) -> None:
        """
        Set a fullscreen image. Should be a valid path on the display's filesystem.
        """
        # Update local state
        self._state.image_path = image_path

        msg = {
            "command": "set_image",
            "image": image_path,
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self) -> None:
        """
        Clear text, title, icon, image, and stop the clock.
        """
        # Update local state: reset visible content, stop clock, preserve background + style defaults
        self._state.title.text = None
        self._state.text.text = None
        self._state.icon.icon = None
        self._state.image_path = None

        # Stop clock locally and reset timing
        self._stop_clock_locally(reset=True)
        self._state.wall_clock.visible = False

        self._send({"command": "clear"})

    # ------------------------------------------------------------------------------------------------------------------
    def start_clock(
        self,
        mode: str = "overlay",
        replace_text: Optional[bool] = None,
        color: Optional[ColorType] = None,
    ) -> None:
        """
        Start the clock from 00:00:00:000.

        mode:
          - "overlay" (default): clock at bottom center, main text stays visible
          - "replace_text": clock is centered and replaces the main text

        replace_text:
          - if provided, overrides the mode on the display side.

        color:
          - optional clock color (separate from title color).
        """
        # Update local state (clock)
        self._state.clock.mode = mode
        self._state.clock.replace_text = bool(replace_text) if replace_text is not None else None

        if color is not None:
            color_t = self._normalize_color_tuple(color)
            self._state.clock.color = color_t
            self._state.clock_color = color_t  # track "default clock color" too
        else:
            # If no explicit color provided, use current clock_color default
            self._state.clock.color = self._state.clock_color

        # Reset timing and mark running
        self._state.clock.running = True
        self._state.clock.accumulated_ms = 0
        self._state.clock.started_at_monotonic = time.monotonic()

        msg: Dict[str, Any] = {
            "command": "start_clock",
            "mode": mode,
        }
        if replace_text is not None:
            msg["replace_text"] = bool(replace_text)
        if color is not None:
            msg["color"] = self._serialize_color(self._state.clock.color)
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def stop_clock(self) -> None:
        """
        Stop the clock (time is frozen until started again).
        """
        # Update local state timing
        self._stop_clock_locally(reset=False)
        self._send({"command": "stop_clock"})

    # ------------------------------------------------------------------------------------------------------------------
    def set_clock_color(self, color: ColorType = DEFAULT_CLOCK_COLOR) -> None:
        """
        Change clock color without changing the time or mode.
        """
        color_t = self._normalize_color_tuple(color)

        # Update local state
        self._state.clock_color = color_t
        self._state.clock.color = color_t

        msg = {
            "command": "set_clock_color",
            "color": self._serialize_color(color_t),
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def show_wall_clock(self, color: Optional[ColorType] = None, size: Optional[int] = None) -> None:
        """
        Show the current time of day below the elapsed clock.
        """
        self._state.wall_clock.visible = True
        if color is not None:
            self._state.wall_clock.color = self._normalize_color_tuple(color)
        if size is not None:
            self._state.wall_clock.size = int(size)

        msg: Dict[str, Any] = {"command": "show_wall_clock"}
        if color is not None:
            msg["color"] = self._serialize_color(self._state.wall_clock.color)
        if size is not None:
            msg["size"] = int(size)
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def hide_wall_clock(self) -> None:
        """
        Hide the wall clock.
        """
        self._state.wall_clock.visible = False
        self._send({"command": "hide_wall_clock"})

    # ------------------------------------------------------------------------------------------------------------------
    def set_background_color(self, color: ColorType = DEFAULT_BACKGROUND_COLOR) -> None:
        """
        Set the solid background color.
        """
        color_t = self._normalize_color_tuple(color)

        # Update local state
        self._state.background_color = color_t

        msg = {
            "command": "set_background_color",
            "color": self._serialize_color(color_t),
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def quit(self) -> None:
        """
        Ask the display to shut down gracefully.
        """
        # Local state doesn't really have a "quit" state, but we still track last payload/time in _send
        self._send({"command": "quit"})

    # ------------------------------------------------------------------------------------------------------------------
    # Convenience: combined "direct-style" updates
    # ------------------------------------------------------------------------------------------------------------------
    def update(
        self,
        *,
        background_color: Optional[ColorType] = None,
        title: Optional[Dict[str, Any]] = None,
        text: Optional[Dict[str, Any]] = None,
        icon: Optional[Dict[str, Any]] = None,
        image: Optional[str] = None,
        clock: Optional[Dict[str, Any]] = None,
        wall_clock: Optional[Dict[str, Any]] = None,
        text_color: Optional[ColorType] = None,
        title_color: Optional[ColorType] = None,
        clock_color: Optional[ColorType] = None,
        clear: bool = False,
        quit: bool = False,
    ) -> None:
        """
        Send a single combined "direct-style" update, mirroring the display's
        direct JSON format.

        This also updates the local client-side state to match what you sent.
        """
        msg: Dict[str, Any] = {}

        # Update local + outgoing message
        if background_color is not None:
            bc = self._normalize_color_tuple(background_color)
            self._state.background_color = bc
            msg["background_color"] = self._serialize_color(bc)

        if title is not None:
            t = dict(title)
            # Local
            if "text" in t:
                self._state.title.text = t.get("text")
            if "size" in t and t["size"] is not None:
                self._state.title.size = int(t["size"])
            if "alignment" in t and t["alignment"] is not None:
                self._state.title.alignment = str(t["alignment"])
            if "color" in t and t["color"] is not None:
                tc = self._normalize_color_tuple(t["color"])
                self._state.title.color = tc
                t["color"] = self._serialize_color(tc)
            msg["title"] = t

        if text is not None:
            t = dict(text)
            # Local
            if "text" in t:
                self._state.text.text = t.get("text")
            if "size" in t and t["size"] is not None:
                self._state.text.size = int(t["size"])
            if "alignment" in t and t["alignment"] is not None:
                self._state.text.alignment = str(t["alignment"])
            if "color" in t and t["color"] is not None:
                tc = self._normalize_color_tuple(t["color"])
                self._state.text.color = tc
                t["color"] = self._serialize_color(tc)
            msg["text"] = t

        if icon is not None:
            ic = dict(icon)
            # Local
            if "icon" in ic:
                self._state.icon.icon = ic.get("icon")
            if "size" in ic and ic["size"] is not None:
                self._state.icon.size = int(ic["size"])
            msg["icon"] = ic

        if image is not None:
            self._state.image_path = image
            msg["image"] = image

        if clock is not None:
            c = dict(clock)
            # Local clock updates are best-effort because display supports different "clock" formats.
            # Common patterns: {"action":"start","mode":"...","color":...} or {"action":"stop"}.
            action = c.get("action")
            if "mode" in c and c["mode"] is not None:
                self._state.clock.mode = str(c["mode"])
            if "replace_text" in c and c["replace_text"] is not None:
                self._state.clock.replace_text = bool(c["replace_text"])
            if "color" in c and c["color"] is not None:
                cc = self._normalize_color_tuple(c["color"])
                self._state.clock.color = cc
                self._state.clock_color = cc
                c["color"] = self._serialize_color(cc)

            if action == "start":
                # reset and run
                self._state.clock.running = True
                self._state.clock.accumulated_ms = 0
                self._state.clock.started_at_monotonic = time.monotonic()
            elif action == "stop":
                self._stop_clock_locally(reset=False)
            elif action == "reset":
                # if your server supports it; locally we treat as 0 and stopped
                self._stop_clock_locally(reset=True)

            msg["clock"] = c

        if wall_clock is not None:
            wc = dict(wall_clock)
            if "color" in wc and wc["color"] is not None:
                wcc = self._normalize_color_tuple(wc["color"])
                self._state.wall_clock.color = wcc
                wc["color"] = self._serialize_color(wcc)
            if "size" in wc and wc["size"] is not None:
                self._state.wall_clock.size = int(wc["size"])
            show = wc.get("show", wc.get("visible"))
            if show is not None:
                self._state.wall_clock.visible = bool(show)
            msg["wall_clock"] = wc

        if text_color is not None:
            tc = self._normalize_color_tuple(text_color)
            self._state.text_color = tc
            self._state.text.color = tc
            msg["text_color"] = self._serialize_color(tc)

        if title_color is not None:
            tc = self._normalize_color_tuple(title_color)
            self._state.title_color = tc
            self._state.title.color = tc
            msg["title_color"] = self._serialize_color(tc)

        if clock_color is not None:
            cc = self._normalize_color_tuple(clock_color)
            self._state.clock_color = cc
            self._state.clock.color = cc
            msg["clock_color"] = self._serialize_color(cc)

        if clear:
            # Apply local clear behavior as well
            self._state.title.text = None
            self._state.text.text = None
            self._state.icon.icon = None
            self._state.image_path = None
            self._stop_clock_locally(reset=True)
            self._state.wall_clock.visible = False
            msg["clear"] = True

        if quit:
            msg["quit"] = True

        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    # Utility / lifecycle
    # ------------------------------------------------------------------------------------------------------------------
    def close(self) -> None:
        """
        Close the underlying UDP socket. After this, the client cannot be used
        unless re-instantiated.
        """
        try:
            self._sock.close()
        except OSError:
            pass

    def __enter__(self) -> "TestbedDisplayClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------------------------------------------------------
    def _stop_clock_locally(self, *, reset: bool) -> None:
        """
        Update local clock timing/state as if a stop occurred.
        If reset=True, also zero out accumulated time.
        """
        if self._state.clock.running and self._state.clock.started_at_monotonic is not None:
            delta_s = time.monotonic() - self._state.clock.started_at_monotonic
            self._state.clock.accumulated_ms = int(self._state.clock.accumulated_ms + max(0.0, delta_s) * 1000.0)

        self._state.clock.running = False
        self._state.clock.started_at_monotonic = None

        if reset:
            self._state.clock.accumulated_ms = 0

    @staticmethod
    def _normalize_color_tuple(color: ColorType) -> Tuple[int, int, int]:
        """
        Normalize input color into a strict (r,g,b) tuple of ints.
        """
        if isinstance(color, (list, tuple)) and len(color) == 3:
            return (int(color[0]), int(color[1]), int(color[2]))
        if isinstance(color, dict):
            return (
                int(color.get("r", 0)),
                int(color.get("g", 0)),
                int(color.get("b", 0)),
            )
        # Fallback: if invalid, return black
        return (0, 0, 0)

    @staticmethod
    def _serialize_color(color: ColorType) -> Any:
        """
        Normalize color into something JSON-serializable that the display
        understands. The display accepts:

          - [r, g, b]
          - (r, g, b)
          - {"r":..., "g":..., "b":...}

        We convert tuples/dicts into simple [r, g, b] lists.
        """
        if isinstance(color, (list, tuple)) and len(color) == 3:
            return [int(color[0]), int(color[1]), int(color[2])]
        if isinstance(color, dict):
            return [
                int(color.get("r", 0)),
                int(color.get("g", 0)),
                int(color.get("b", 0)),
            ]
        # Fallback / invalid: just return as-is, the server will try to parse or fall back
        return color


# Optional: quick manual test when run as script
if __name__ == "__main__":
    try:
        client = TestbedDisplayClient()

        # Best-effort: sets client.connected; safe even if display isn't reachable
        client.start()

        client.clear()
        client.set_background_color((0, 0, 0))
        client.set_title("Experiment 1: Stand Up", color=(255, 255, 255), alignment="left", size=DEFAULT_TITLE_SIZE)
        client.set_text(
            "Hello from TestbedDisplayClient",
            size=DEFAULT_TEXT_SIZE,
            color=(255, 255, 255),
            alignment="center",
        )
        # client.set_icon("🚀", size=DEFAULT_ICON_SIZE)
        client.start_clock(mode="replace_text", color=(0, 255, 255))

        # Example: read and print local state snapshot
        print(json.dumps(client.get_state_dict(json_ready=True), indent=2))

        time.sleep(5.05)
        client.set_clock_color((255, 0, 0))
        print(json.dumps(client.get_state_dict(json_ready=True), indent=2))
    finally:
        client.clear()