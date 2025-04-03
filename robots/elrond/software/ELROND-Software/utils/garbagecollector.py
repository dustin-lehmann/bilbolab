import gc
from contextlib import contextmanager


@contextmanager
def disable_gc():
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()