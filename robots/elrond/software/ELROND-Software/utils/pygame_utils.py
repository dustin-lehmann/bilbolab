# pygame_utils.py

import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

# Hide the Pygame support prompt (Optional)


_initialized = False


def initialize_pygame():
    global _initialized
    if not _initialized:
        if not pygame.get_init():
            pygame.init()  # Initialize all of Pygame
        if pygame.mixer.get_init() is None:
            try:
                pygame.mixer.init()  # Initialize the mixer for sound
            except pygame.error:
                pass
        _initialized = True
    else:
        # Pygame is already initialized, so we don't do anything
        pass


# Ensure that Pygame is initialized immediately upon importing this module
initialize_pygame()

# Make pygame available for import
import pygame
