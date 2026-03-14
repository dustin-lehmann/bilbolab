# pygame_utils.py

import os
import sys
import platform
from contextlib import redirect_stderr

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

# Force ALSA driver on Linux (RPi), leave default on macOS/Windows
if platform.system() == "Linux":
    os.environ.setdefault("SDL_AUDIODRIVER", "alsa")

# -------------------------
# AUDIO CONFIG
# -------------------------
AUDIO_FREQUENCY = 44100
AUDIO_SIZE = -16            # signed 16-bit
AUDIO_CHANNELS = 2          # 1 = mono, 2 = stereo
AUDIO_BUFFER = 4096         # 2048–8192 recommended
# -------------------------

_initialized = False

# Silence ALSA spam only during init
class _NullWriter:
    def write(self, *_): pass
    def flush(self): pass

_null = _NullWriter()


def initialize_pygame():
    """Initialize pygame with pre_init() and a large audio buffer."""
    global _initialized

    if _initialized:
        return

    try:
        with redirect_stderr(_null):
            import pygame

            pygame.mixer.pre_init(
                frequency=AUDIO_FREQUENCY,
                size=AUDIO_SIZE,
                channels=AUDIO_CHANNELS,
                buffer=AUDIO_BUFFER,
            )

            if not pygame.get_init():
                pygame.init()

            if pygame.mixer.get_init() is None:
                pygame.mixer.init()

        _initialized = True

    except Exception as e:
        print(f"[pygame_utils] Error initializing pygame: {e}")


# Initialize immediately on import
initialize_pygame()

# Re-export pygame
import pygame
