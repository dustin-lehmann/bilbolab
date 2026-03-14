#!/usr/bin/env python3
import argparse
import json
import os
import socket
import sys
import threading
import time
from typing import Optional

os.environ["DISPLAY"] = ":0"
# If the desktop session is owned by a specific user, point at their Xauthority:
os.environ["XAUTHORITY"] = "/home/admin/.Xauthority"  # change user if needed

import pygame


# DEFAULT SETTINGS
DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_LISTEN_PORT = 12346
DEFAULT_BACKGROUND_COLOR = (0, 0, 0)   # black
DEFAULT_TEXT_COLOR = (255, 255, 255)   # white
DEFAULT_TITLE_COLOR = (200, 200, 200)  # light gray
DEFAULT_CLOCK_COLOR = DEFAULT_TITLE_COLOR  # separate, but same default as title for now

# Font sizes (already increased earlier)
DEFAULT_TEXT_SIZE = 150
DEFAULT_TITLE_SIZE = 120
DEFAULT_ICON_SIZE = 160

FPS = 30


# ----------------------------------------------------------------------------------------------------------------------
# ENV / ARGUMENTS
# ----------------------------------------------------------------------------------------------------------------------
def ensure_display_env():
    """
    Ensure environment variables are set so pygame can open a display even from SSH.
    """
    os.environ.setdefault("DISPLAY", ":0")

    if "XDG_RUNTIME_DIR" not in os.environ:
        uid = os.getuid()
        os.environ["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"

    os.environ.setdefault("SDL_VIDEODRIVER", "x11")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Network-driven testbed display using pygame on Raspberry Pi."
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_LISTEN_HOST,
        help=f"Host/IP to listen on for UDP JSON messages (default: {DEFAULT_LISTEN_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_LISTEN_PORT,
        help=f"UDP port to listen on (default: {DEFAULT_LISTEN_PORT})",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Run in a resizable window instead of fullscreen.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=800,
        help="Window width (only used when --windowed is set). Default: 800",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=480,
        help="Window height (only used when --windowed is set). Default: 480",
    )
    parser.add_argument(
        "--font-name",
        "-f",
        default=None,
        help="Default font name for pygame.font.SysFont (default: system default).",
    )
    return parser.parse_args()


# ----------------------------------------------------------------------------------------------------------------------
# DISPLAY CLASS
# ----------------------------------------------------------------------------------------------------------------------
class TestbedDisplay:
    def __init__(
        self,
        host: str = DEFAULT_LISTEN_HOST,
        port: int = DEFAULT_LISTEN_PORT,
        fullscreen: bool = True,
        width: int = 1920,
        height: int = 440,
        font_name: Optional[str] = None,
    ):
        """
        A network-controlled display that listens for JSON commands via UDP and
        renders text, title, icons, images, and an optional clock.
        """
        self.host = host
        self.port = port
        self.fullscreen = fullscreen
        self.window_width = width
        self.window_height = height
        self.font_name = font_name

        # pygame objects
        self.screen: Optional[pygame.Surface] = None
        self.clock: Optional[pygame.time.Clock] = None
        self.running = False

        # network
        self.udp_socket: Optional[socket.socket] = None

        # drawing state
        self.background_color = DEFAULT_BACKGROUND_COLOR

        # main text
        self.text: Optional[str] = None
        self.text_size: int = DEFAULT_TEXT_SIZE
        self.text_color = DEFAULT_TEXT_COLOR
        self.text_alignment: str = "center"  # "left", "center", "right"

        # title text
        self.title: Optional[str] = None
        self.title_size: int = DEFAULT_TITLE_SIZE
        self.title_color = DEFAULT_TITLE_COLOR
        self.title_alignment: str = "center"  # "left", "center", "right"

        # icon (emoji)
        self.icon: Optional[str] = None
        self.icon_size: int = DEFAULT_ICON_SIZE

        # image (fullscreen background/overlay)
        self.image_path: Optional[str] = None
        self.image_surface: Optional[pygame.Surface] = None

        # clock
        self.clock_running = False
        self.clock_elapsed_ms = 0  # elapsed milliseconds
        self.clock_last_update = time.time()
        # mode: "overlay" (draw at bottom, keep text) or "replace_text" (centered, instead of text)
        self.clock_mode: str = "overlay"
        self.clock_color = DEFAULT_CLOCK_COLOR

        # font cache (kind -> size -> font)
        # kind is "normal", "emoji", or "mono"
        self._font_cache = {}



    # === METHODS ======================================================================================================
    def init(self):
        ensure_display_env()

        pygame.init()

        pygame.mouse.set_visible(False)

        pygame.font.init()

        flags = 0
        size = (self.window_width, self.window_height)
        if self.fullscreen:
            flags |= pygame.FULLSCREEN
            size = (0, 0)  # let pygame choose current display resolution

        self.screen = pygame.display.set_mode(size, flags)
        pygame.display.set_caption("Testbed Network Display")

        self.window_width, self.window_height = self.screen.get_size()
        print(f"[Display] Resolution: {self.window_width}x{self.window_height}", flush=True)

        self.clock = pygame.time.Clock()

        self._open_udp()

        # initial clear
        self.clear()
        pygame.display.flip()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        """
        Main loop. Handles pygame events, network messages, drawing, and clock updates.
        """
        if self.screen is None or self.clock is None:
            self.init()

        self.running = True
        print(f"[Network] Listening on {self.host}:{self.port} (UDP JSON)", flush=True)


        # thread = threading.Thread(target=self._task, daemon=True)
        # thread.start()
        self._task()


    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        while self.running:
            # Handle pygame events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.close()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    # ESC closes the display
                    self.close()

            # Handle incoming UDP messages (non-blocking)
            if self.udp_socket is not None:
                while True:
                    try:
                        data, addr = self.udp_socket.recvfrom(65535)
                    except BlockingIOError:
                        break  # no more data
                    except OSError:
                        # socket closed
                        break
                    else:
                        try:
                            message = data.decode("utf-8", errors="replace").strip()
                            if not message:
                                continue
                            self._on_udp_message(message)
                        except Exception as exc:  # noqa: BLE001
                            print(f"[Network] Error handling message from {addr}: {exc}", file=sys.stderr)

            # Update internal clock timer
            self._update_clock()

            # Draw current state
            self._draw_frame()

            # Limit FPS
            self.clock.tick(FPS)

        # End loop
        self.close()
    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        """
        Stop the main loop and close resources.
        """
        if self.running:
            print("[Display] Closing...", flush=True)
        self.running = False

        if self.udp_socket is not None:
            try:
                self.udp_socket.close()
            except OSError:
                pass
            self.udp_socket = None

        pygame.quit()

    # ------------------------------------------------------------------------------------------------------------------
    def set_text(
        self,
        text: Optional[str],
        size: int = DEFAULT_TEXT_SIZE,
        color=(255, 255, 255),
        alignment: str = "center",
    ):
        """
        Set main text. Vertically centered, horizontal alignment configurable.
        Alignment: "left", "center", or "right".
        """
        self.text = text
        self.text_size = size
        self.text_color = self._parse_color(color)
        self.text_alignment = alignment.lower()

    # ------------------------------------------------------------------------------------------------------------------
    def set_text_color(self, color):
        """
        Change text color without changing text content or size.
        """
        self.text_color = self._parse_color(color)

    # ------------------------------------------------------------------------------------------------------------------
    def set_title(
        self,
        text: Optional[str],
        color: tuple[int, int, int] = DEFAULT_TITLE_COLOR,
        alignment: str = "center",
        size: int = DEFAULT_TITLE_SIZE,
    ):
        """
        Set a title displayed at the top edge of the screen.
        """
        self.title = text
        self.title_color = self._parse_color(color)
        self.title_alignment = alignment.lower()
        self.title_size = size

    # ------------------------------------------------------------------------------------------------------------------
    def set_title_color(self, color):
        """
        Change title color without changing title text or size.
        """
        self.title_color = self._parse_color(color)

    # ------------------------------------------------------------------------------------------------------------------
    def set_icon(self, icon: Optional[str], size: int = DEFAULT_ICON_SIZE):
        """
        Sets a centered icon in the display. Icon is a string emoji

        :param icon: emoji string (e.g. "🚀"). None/"" to clear.
        :param size: font size in points.
        """
        self.icon = icon
        self.icon_size = size

    # ------------------------------------------------------------------------------------------------------------------
    def set_image(self, image_path: Optional[str]):
        """
        Set fullscreen image (with alpha). The current background color shows
        through transparent parts of the PNG.

        :param image_path: path to image on filesystem, or None to clear.
        """
        if not image_path:
            self.image_path = None
            self.image_surface = None
            return

        if not os.path.isfile(image_path):
            print(f"[Display] Image not found: {image_path}", file=sys.stderr)
            self.image_path = None
            self.image_surface = None
            return

        try:
            image = pygame.image.load(image_path).convert_alpha()
            image = pygame.transform.smoothscale(image, (self.window_width, self.window_height))
            self.image_surface = image
            self.image_path = image_path
            print(f"[Display] Loaded image: {image_path}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[Display] Failed to load image '{image_path}': {exc}", file=sys.stderr)
            self.image_path = None
            self.image_surface = None

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self):
        """
        Clear text, title, icon, image, and stop clock. Keep background and colors.
        """
        self.text = None
        self.title = None
        self.icon = None
        self.image_path = None
        self.image_surface = None
        self.clock_running = False
        self.clock_elapsed_ms = 0

    # ------------------------------------------------------------------------------------------------------------------
    def start_clock(self, mode: str = "overlay"):
        """
        Start the clock from 00:00:00:000.

        mode:
          - "overlay" (default): clock at bottom center, main text stays visible
          - "replace_text": clock is centered and replaces the main text (text is cleared)
        """
        self.clock_elapsed_ms = 0
        self.clock_running = True
        self.clock_last_update = time.time()

        if mode not in ("overlay", "replace_text"):
            mode = "overlay"
        self.clock_mode = mode

        if self.clock_mode == "replace_text":
            # As requested: using the clock instead of the text == delete text
            self.text = None

    # ------------------------------------------------------------------------------------------------------------------
    def stop_clock(self):
        """
        Stop the clock (time is frozen until started again).
        """
        self.clock_running = False

    # ------------------------------------------------------------------------------------------------------------------
    def set_clock_color(self, color):
        """
        Change clock color without changing the time or mode.
        """
        self.clock_color = self._parse_color(color)

    # ------------------------------------------------------------------------------------------------------------------
    def set_background_color(self, color: tuple[int, int, int] = (0, 0, 0)):
        """
        Set the solid background color. If an image is set, the image is drawn on top
        and the background color is visible where the image has transparency.
        """
        self.background_color = self._parse_color(color)

    # ------------------------------------------------------------------------------------------------------------------
    # === PRIVATE METHODS ==============================================================================================
    def _open_udp(self):
        """
        Open a non-blocking UDP socket for listening to JSON messages.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.setblocking(False)
        self.udp_socket = sock

    # ------------------------------------------------------------------------------------------------------------------
    def _on_udp_message(self, message: str):
        """
        Handle a single JSON-encoded message.

        Command-style examples:

           {"command": "set_text", "text": "Hello", "size": 96, "color": [255, 0, 0], "alignment": "left"}
           {"command": "set_text_color", "color": [255, 0, 0]}
           {"command": "set_title_color", "color": [0, 255, 0]}
           {"command": "set_clock_color", "color": [0, 255, 255]}
           {"command": "start_clock", "mode": "replace_text", "color": [0, 255, 255]}

        Direct-style examples:

           {
             "text": {"text": "Main", "size": 80, "color": [255,255,255], "alignment": "center"},
             "title": {"text": "Header", "size": 40, "color": [0,255,0], "alignment": "center"},
             "clock": {"action": "start", "mode": "overlay", "color": [255,0,0]},
             "text_color": [255,255,0],
             "title_color": [0,255,255],
             "clock_color": [255,0,255]
           }
        """
        try:
            msg = json.loads(message)
        except json.JSONDecodeError as exc:
            print(f"[Network] Invalid JSON: {exc}; message={message!r}", file=sys.stderr)
            return



        if not isinstance(msg, dict):
            print(f"[Network] Ignoring non-dict JSON message: {msg!r}", file=sys.stderr)
            return

        # First: command-oriented messages
        command = msg.get("command") or msg.get("action") or msg.get("cmd")
        if command:
            cmd = command.lower()
            if cmd == "set_text":
                self.set_text(
                    text=msg.get("text"),
                    size=int(msg.get("size", self.text_size)),
                    color=msg.get("color", self.text_color),
                    alignment=msg.get("alignment", self.text_alignment),
                )
            elif cmd == "set_text_color":
                if "color" in msg:
                    self.set_text_color(msg["color"])
            elif cmd == "set_title":
                self.set_title(
                    text=msg.get("text"),
                    size=int(msg.get("size", self.title_size)),
                    color=msg.get("color", self.title_color),
                    alignment=msg.get("alignment", self.title_alignment),
                )
            elif cmd == "set_title_color":
                if "color" in msg:
                    self.set_title_color(msg["color"])
            elif cmd == "set_icon":
                self.set_icon(
                    icon=msg.get("icon"),
                    size=int(msg.get("size", self.icon_size)),
                )
            elif cmd == "set_image":
                self.set_image(msg.get("image") or msg.get("image_path"))
            elif cmd == "clear":
                self.clear()
            elif cmd == "start_clock":
                mode = msg.get("mode", "overlay")
                if msg.get("replace_text"):
                    mode = "replace_text"
                if "color" in msg:
                    self.set_clock_color(msg["color"])
                elif "clock_color" in msg:
                    self.set_clock_color(msg["clock_color"])
                self.start_clock(mode=mode)
            elif cmd == "stop_clock":
                self.stop_clock()
            elif cmd == "set_clock_color":
                if "color" in msg:
                    self.set_clock_color(msg["color"])
            elif cmd == "set_background_color":
                self.set_background_color(msg.get("color", self.background_color))
            elif cmd == "quit":
                self.close()
            else:
                print(f"[Network] Unknown command: {command}", file=sys.stderr)
            return

        # Second: direct-style messages with structured fields
        if "background_color" in msg:
            self.set_background_color(msg["background_color"])

        if "text" in msg:
            text_cfg = msg["text"]
            if isinstance(text_cfg, dict):
                self.set_text(
                    text=text_cfg.get("text"),
                    size=int(text_cfg.get("size", self.text_size)),
                    color=text_cfg.get("color", self.text_color),
                    alignment=text_cfg.get("alignment", self.text_alignment),
                )
            else:
                self.set_text(str(text_cfg))

        if "title" in msg:
            title_cfg = msg["title"]
            if isinstance(title_cfg, dict):
                self.set_title(
                    text=title_cfg.get("text"),
                    size=int(title_cfg.get("size", self.title_size)),
                    color=title_cfg.get("color", self.title_color),
                    alignment=title_cfg.get("alignment", self.title_alignment),
                )
            else:
                self.set_title(str(title_cfg))

        if "icon" in msg:
            icon_cfg = msg["icon"]
            if isinstance(icon_cfg, dict):
                self.set_icon(
                    icon=icon_cfg.get("icon"),
                    size=int(icon_cfg.get("size", self.icon_size)),
                )
            else:
                self.set_icon(str(icon_cfg))

        if "image" in msg or "image_path" in msg:
            self.set_image(msg.get("image") or msg.get("image_path"))

        if "clock" in msg:
            clock_cfg = msg["clock"]
            if isinstance(clock_cfg, dict):
                action = clock_cfg.get("action", "").lower()
                mode = clock_cfg.get("mode", "overlay")
                if clock_cfg.get("replace_text"):
                    mode = "replace_text"
                if "color" in clock_cfg:
                    self.set_clock_color(clock_cfg["color"])
                if action == "start":
                    self.start_clock(mode=mode)
                elif action == "stop":
                    self.stop_clock()
            elif isinstance(clock_cfg, str):
                if clock_cfg.lower() == "start":
                    self.start_clock()
                elif clock_cfg.lower() == "stop":
                    self.stop_clock()

        # direct color-only updates
        if "text_color" in msg:
            self.set_text_color(msg["text_color"])
        if "title_color" in msg:
            self.set_title_color(msg["title_color"])
        if "clock_color" in msg:
            self.set_clock_color(msg["clock_color"])

        if msg.get("clear"):
            self.clear()

        if msg.get("quit"):
            self.close()

    # ------------------------------------------------------------------------------------------------------------------
    def _update_clock(self):
        """
        Update clock elapsed time if running.
        """
        if not self.clock_running:
            return
        now = time.time()
        dt = now - self.clock_last_update
        self.clock_last_update = now
        # convert to milliseconds
        self.clock_elapsed_ms += int(dt * 1000)

    # ------------------------------------------------------------------------------------------------------------------
    def _draw_frame(self):
        """
        Draw background, image, title, text, icon, and clock.
        """
        if self.screen is None:
            return

        margin = 20
        center_x = self.window_width // 2
        center_y = self.window_height // 2

        # 1) Background color first
        self.screen.fill(self.background_color)

        # 2) Image on top, keeping transparency (alpha)
        if self.image_surface is not None:
            self.screen.blit(self.image_surface, (0, 0))

        # 3) Title, fixed at top edge
        title_surface = None
        title_rect = None
        if self.title:
            title_surface = self._render_text(self.title, self.title_size, self.title_color,
                                                max_width=self.window_width - 2 * margin)
            title_rect = title_surface.get_rect()
            title_rect.top = margin
            self._apply_horizontal_alignment(
                title_rect,
                self.title_alignment,
                margin,
                center_x,
                self.window_width,
            )
            self.screen.blit(title_surface, title_rect)

        # 4) Icon (emoji) in the center
        if self.icon:
            icon_surface = self._render_text(self.icon, self.icon_size, self.text_color, emoji=True)
            icon_rect = icon_surface.get_rect(center=(center_x, center_y))
            self.screen.blit(icon_surface, icon_rect)

        # 5) Main text (vertically centered) – unless clock is replacing it
        text_surface = None
        text_rect = None
        draw_text = not (self.clock_running and self.clock_mode == "replace_text")

        if self.text and draw_text:
            text_surface = self._render_text(self.text, self.text_size, self.text_color,
                                             max_width=self.window_width - 2 * margin)
            text_rect = text_surface.get_rect()
            text_rect.centery = center_y
            self._apply_horizontal_alignment(
                text_rect,
                self.text_alignment,
                margin,
                center_x,
                self.window_width,
            )
            self.screen.blit(text_surface, text_rect)

        # 6) Clock – using monospace font so it doesn't jump horizontally
        if self.clock_running:
            clock_str = self._format_clock_time(self.clock_elapsed_ms)

            if self.clock_mode == "replace_text":
                clock_surface = self._render_text(
                    clock_str,
                    self.text_size,
                    self.clock_color,
                    mono=True,
                )
                clock_rect = clock_surface.get_rect(center=(center_x, center_y))
                self.screen.blit(clock_surface, clock_rect)
            else:
                clock_surface = self._render_text(
                    clock_str,
                    self.title_size,
                    self.clock_color,
                    mono=True,
                )
                clock_rect = clock_surface.get_rect()
                clock_rect.midbottom = (center_x, self.window_height - margin)
                self.screen.blit(clock_surface, clock_rect)

        pygame.display.flip()

    # ------------------------------------------------------------------------------------------------------------------
    def _render_text(self, text: str, size: int, color, emoji: bool = False, mono: bool = False,
                     max_width: int = 0, min_size: int = 24):
        """
        Render text with caching for fonts.

        - emoji=True: try an emoji-capable font
        - mono=True: use a monospace font (for clock)
        - max_width: if > 0, shrink font until text fits within this width
        - min_size: minimum font size when auto-shrinking
        """
        if max_width > 0:
            current_size = size
            while current_size >= min_size:
                font = self._get_font(current_size, emoji=emoji, mono=mono)
                surface = font.render(text, True, color)
                if surface.get_width() <= max_width:
                    return surface
                current_size -= 1
            # At min size, render anyway
            font = self._get_font(min_size, emoji=emoji, mono=mono)
            return font.render(text, True, color)

        font = self._get_font(size, emoji=emoji, mono=mono)
        return font.render(text, True, color)

    # ------------------------------------------------------------------------------------------------------------------
    def _get_font(self, size: int, emoji: bool = False, mono: bool = False) -> pygame.font.Font:
        """
        Get (and cache) a pygame font for given size.

        - Normal fonts use self.font_name (or system default).
        - Emoji fonts try some common emoji-capable fonts if available.
        - Mono fonts use a monospace font; good for the clock to avoid jitter.
        """
        kind = "normal"
        if emoji:
            kind = "emoji"
        elif mono:
            kind = "mono"

        key = (kind, self.font_name, size)

        if key in self._font_cache:
            return self._font_cache[key]

        font_obj: pygame.font.Font

        if emoji:
            # Try to find a commonly installed emoji font
            emoji_candidates = [
                "Noto Color Emoji",
                "Segoe UI Emoji",
                "Apple Color Emoji",
                "EmojiOne Color",
                "Twitter Color Emoji",
            ]
            font_obj = None
            for name in emoji_candidates:
                path = pygame.font.match_font(name)
                if path:
                    try:
                        font_obj = pygame.font.Font(path, size)
                        break
                    except Exception:  # noqa: BLE001
                        font_obj = None
            if font_obj is None:
                font_obj = pygame.font.SysFont(self.font_name, size)
        elif mono:
            # Monospace for clock
            mono_candidates = [
                "DejaVu Sans Mono",
                "Liberation Mono",
                "Courier New",
                "monospace",
            ]
            font_obj = None
            for name in mono_candidates:
                path = pygame.font.match_font(name)
                if path:
                    try:
                        font_obj = pygame.font.Font(path, size)
                        break
                    except Exception:  # noqa: BLE001
                        font_obj = None
            if font_obj is None:
                font_obj = pygame.font.SysFont("monospace", size)
        else:
            font_obj = pygame.font.SysFont(self.font_name, size)

        self._font_cache[key] = font_obj
        return font_obj

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _apply_horizontal_alignment(
        rect: pygame.Rect,
        alignment: str,
        margin: int,
        center_x: int,
        screen_width: int,
    ):
        """
        Apply horizontal alignment (left/center/right) to a rect.

        - left:  rect.left = margin
        - right: rect.right = screen_width - margin
        - center: rect.centerx = center_x
        """
        alignment = (alignment or "center").lower()
        if alignment == "left":
            rect.left = margin
        elif alignment == "right":
            rect.right = screen_width - margin
        else:  # center (default)
            rect.centerx = center_x

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _parse_color(value) -> tuple[int, int, int]:
        """
        Accepts:
          - (r, g, b)
          - [r, g, b]
          - {"r":..., "g":..., "b":...}
        """
        if isinstance(value, (list, tuple)) and len(value) == 3:
            return int(value[0]), int(value[1]), int(value[2])
        if isinstance(value, dict):
            return int(value.get("r", 0)), int(value.get("g", 0)), int(value.get("b", 0))
        # fallback
        return DEFAULT_TEXT_COLOR

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _format_clock_time(elapsed_ms: int) -> str:
        """
        Format elapsed_ms into hh:mm:ss:ms with 0.1s increments and padded zeros.
        """
        # quantize to 100 ms (0.1 s)
        q_ms = (elapsed_ms // 100) * 100
        total_seconds = q_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        ms = q_ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{ms:03d}"


# ----------------------------------------------------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------------------------------------------------
def main():
    args = parse_args()

    display = TestbedDisplay(
        host=args.host,
        port=args.port,
        fullscreen=not args.windowed,
        width=args.width,
        height=args.height,
        font_name=args.font_name,
    )
    display.init()
    display.start()


if __name__ == "__main__":
    main()