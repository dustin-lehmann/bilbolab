"""Deprecation decorator wrapping `typing_extensions.deprecated` with a default message.

Allows usage as either:

    @deprecated
    def foo(): ...

    @deprecated("Use bar() instead")
    def foo(): ...

    @deprecated("Use bar() instead", category=DeprecationWarning, stacklevel=2)
    def foo(): ...
"""

from typing_extensions import deprecated as _deprecated

DEFAULT_MESSAGE = "This API is deprecated and will be removed in a future version."


def deprecated(arg=None, /, *args, **kwargs):
    if callable(arg):
        # Used as bare @deprecated on a class or function
        return _deprecated(DEFAULT_MESSAGE, *args, **kwargs)(arg)
    # Used as @deprecated(...) — arg is the message (or None for default)
    message = arg if arg is not None else DEFAULT_MESSAGE
    return _deprecated(message, *args, **kwargs)
