import sys
import threading
from typing import Any


# Thread-safe singleton metaclass
class _SingletonMeta(type):
    _instances: dict[type, Any] = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        # Double-checked locking so __init__ runs only once
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    inst = super().__call__(*args, **kwargs)
                    cls._instances[cls] = inst

                    # Ensure the module-level name is set the moment the first instance exists
                    mod = sys.modules[cls.__module__]
                    if getattr(mod, "active_event_loop", None) is None:
                        setattr(mod, "active_event_loop", inst)
        return cls._instances[cls]
