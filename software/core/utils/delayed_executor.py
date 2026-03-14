import threading
import time
from typing import Callable, Any

class DelayedExecutor:
    def __init__(self, func: Callable, delay: float, *args, **kwargs):
        """
        Initialize the DelayedExecutor.

        :param func: The function to execute.
        :param delay: Time in seconds to wait before executing the function.
        :param args: Positional arguments for the function.
        :param kwargs: Keyword arguments for the function.
        """
        self.func = func
        self.delay = delay
        self.args = args
        self.kwargs = kwargs

    def start(self):
        """
        Start the delayed execution in a separate thread.
        """
        thread = threading.Thread(target=self._delayed_run)
        thread.daemon = True  # Ensures the thread exits when the main program exits
        thread.start()

    def _delayed_run(self):
        """
        Wait for the specified delay and then execute the function.
        """
        time.sleep(self.delay)
        self.func(*self.args, **self.kwargs)


def delayed_execution(func: Callable, delay: float, *args, **kwargs) -> None:
    """
    Execute a function after a specified delay in a non-blocking manner.

    :param func: The function to execute.
    :param delay: Time in seconds to wait before executing the function.
    :param args: Positional arguments for the function.
    :param kwargs: Keyword arguments for the function.
    """
    executor = DelayedExecutor(func, delay, *args, **kwargs)
    executor.start()

