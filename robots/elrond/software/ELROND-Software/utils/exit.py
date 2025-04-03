import os
import signal
import sys


def stop_program(force: bool = False):
    if force:
        os._exit(0)
    else:
        sys.exit()

class ExitHandler:
    _signal_received = False

    def __init__(self):
        # Store the original handlers for the signals
        self._original_handlers = {
            signal.SIGINT: signal.getsignal(signal.SIGINT),
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
        }
        # Replace the signal handlers with the utility's handler
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        # Maintain a list of registered callbacks
        self._callbacks = []

    def register(self, callback):
        """
        Register a callback to be executed when a signal is received.

        :param callback: Callable with signature `callback(signum, frame)`
        """
        if callable(callback):
            self._callbacks.append(callback)

    def _handle_signal(self, signum, frame):
        """
        Handle registered signals and call all registered callbacks,
        then chain to the original handler.
        """
        if not ExitHandler._signal_received:
            print(" ")
            print("Exit Application")
            print(" ")
            ExitHandler._signal_received = True

        # Call all registered callbacks
        for callback in self._callbacks:
            try:
                callback(signum, frame)
            except Exception as e:
                print(f"Callback error: {e}")

        # Call the original handler for the signal if it exists and is callable
        original_handler = self._original_handlers.get(signum)
        if callable(original_handler):
            try:
                original_handler(signum, frame)
            except KeyboardInterrupt:
                import os
                os._exit(0)
                # raise
        elif original_handler == signal.SIG_DFL:
            # Handle default signal behavior if necessary
            import os
            os._exit(0)
        elif original_handler == signal.default_int_handler:
            # Handle default interrupt behavior if necessary
            print(f"Default interrupt handler for signal {signum} triggered.")
