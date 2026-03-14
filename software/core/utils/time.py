import ctypes
from contextlib import contextmanager
from typing import Callable
import time
import threading

# === OWN PACKAGES =====================================================================================================
from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.exit import register_exit_callback
from core.utils.os_utils import getOS
from threading import Timer as ThreadTimer

if getOS() == "Windows":
    winmm = ctypes.WinDLL('winmm')
    # Declare argument/return types just to be safe
    timeBeginPeriod = winmm.timeBeginPeriod
    timeBeginPeriod.argtypes = [ctypes.c_uint]
    timeBeginPeriod.restype = ctypes.c_uint

    timeEndPeriod = winmm.timeEndPeriod
    timeEndPeriod.argtypes = [ctypes.c_uint]
    timeEndPeriod.restype = ctypes.c_uint

PRECISION_TIMING_WINDOWS_ENABLED = False


def enable_precision_timing_windows():
    global PRECISION_TIMING_WINDOWS_ENABLED
    if not PRECISION_TIMING_WINDOWS_ENABLED:
        timeBeginPeriod(1)
        PRECISION_TIMING_WINDOWS_ENABLED = True


def disable_precision_timing_windows():
    global PRECISION_TIMING_WINDOWS_ENABLED
    PRECISION_TIMING_WINDOWS_ENABLED = False
    timeEndPeriod(1)


def wait_until(
        predicate: Callable[[], bool],
        timeout_s: float,
        poll_period_s: float = 0.1,
) -> bool:
    """
    Wait until `predicate()` becomes True or timeout expires.

    Args:
        predicate: zero-argument callable returning bool
        timeout_s: timeout in seconds
        poll_period_s: sleep time between evaluations

    Returns:
        True  -> predicate became True before timeout
        False -> timeout expired first
    """
    deadline = time.monotonic() + timeout_s

    while True:
        if predicate():
            return True

        if time.monotonic() >= deadline:
            return False

        time.sleep(poll_period_s)


# ======================================================================================================================
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


def setTimeout(func: Callable, timeout: float, *args, **kwargs):
    delayed_execution(func, timeout, *args, **kwargs)


set_timeout = setTimeout

# ======================================================================================================================


# ======================================================================================================================
@callback_definition
class TimerCallbacks:
    timeout: CallbackContainer


class Timer:
    timeout: float
    repeat: bool

    callbacks: TimerCallbacks
    _threadTimer: ThreadTimer
    _reset_time: float

    _stop: bool

    def __init__(self, timeout=None, repeat: bool = False, callback: Callable | Callback | None = None):
        self._reset_time = time.time()
        self.timeout = timeout  # Type: Ignore
        self.repeat = repeat

        self._threadTimer = None  # Type: Ignore

        self.callbacks = TimerCallbacks()

        if callback is not None:
            self.callbacks.timeout.register(callback)

    # ------------------------------------------------------------------------------------------------------------------

    def start(self, timeout=None, repeat: bool = None):
        if timeout is not None:
            self.timeout = timeout

        if repeat is not None:
            self.repeat = repeat

        self.reset()

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def time(self):
        return time.time() - self._reset_time

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        self._reset_time = time.time()
        if self._threadTimer is not None:
            self._threadTimer.cancel()

        self._threadTimer = ThreadTimer(self.timeout, self._timeout_callback)
        self._threadTimer.start()

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        self._threadTimer.cancel()
        self._threadTimer = None  # Type: Ignore

    # ------------------------------------------------------------------------------------------------------------------
    def set(self, value):
        self._reset_time = time.time() - value

    def _timeout_callback(self):
        for callback in self.callbacks.timeout:
            callback()

        if self.repeat:
            self._threadTimer = ThreadTimer(self.timeout, self._timeout_callback)
            self._threadTimer.start()
        else:
            self._threadTimer = None  # Type: Ignore

    # ------------------------------------------------------------------------------------------------------------------
    def __gt__(self, other):
        return self.time > other

    # ------------------------------------------------------------------------------------------------------------------
    def __lt__(self, other):
        return self.time < other


# ======================================================================================================================
def sleep(seconds):
    precise_sleep(seconds)


# ----------------------------------------------------------------------------------------------------------------------
def precise_sleep(seconds: float, disable_precision_timing=True):
    if getOS() == "Windows":
        precise_sleep_windows(seconds, disable_precision_timing)
    else:
        precise_sleep_posix(seconds)


# ----------------------------------------------------------------------------------------------------------------------
def precise_sleep_windows(seconds: float, disable_precision_timing: bool = True):
    """Sleep with improved timer resolution on Windows."""
    # Request 1 ms resolution
    enable_precision_timing_windows()
    try:
        target = time.perf_counter() + seconds
        while True:
            now = time.perf_counter()
            if now >= target:
                break
            remaining = target - now

            # Sleep about half of the remaining time or up to 1 ms,
            # whichever is smaller. You can adjust as needed.
            if remaining > 0.001:
                time.sleep(min(remaining / 2, 0.001))
            else:
                # Busy-wait for the final few microseconds
                pass

    finally:
        # Always revert to default resolution
        if disable_precision_timing:
            disable_precision_timing_windows()


# ----------------------------------------------------------------------------------------------------------------------
def precise_sleep_posix(seconds: float):
    """
    High-precision sleep function.
    """
    target_time = time.perf_counter() + seconds

    # Coarse sleep until close to the target time
    while True:
        remaining = target_time - time.perf_counter()
        if remaining <= 0:
            break
        if remaining > 0.001:  # If more than 1ms remains, sleep briefly
            time.sleep(remaining / 2)  # Use fractional sleep to avoid overshooting
        else:
            break

    # Busy-wait for the final few microseconds
    while time.perf_counter() < target_time:
        pass


# ======================================================================================================================
class PrecisionTimer:
    def __init__(self, timeout: float = None, repeat: bool = False, callback=None):
        self.timeout = timeout  # Timeout in seconds
        self.repeat = repeat  # Whether the timer should restart
        self.callback = callback  # Callback function when timeout is reached

        self._reset_time = time.perf_counter()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._task, daemon=True)

        register_exit_callback(self.stop)

    def start(self, timeout=None, repeat: bool = None):
        if timeout is not None:
            self.timeout = timeout
        if repeat is not None:
            self.repeat = repeat

        self._stop_event.clear()
        if not self._thread.is_alive():
            self._thread = threading.Thread(target=self._task, daemon=True)
            self._thread.start()

    def stop(self, *args, **kwargs):
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join()

        if getOS() == "Windows":
            disable_precision_timing_windows()
            print("Disabled precision timing.")

    def reset(self):
        self._reset_time = time.perf_counter()

    @property
    def time(self):
        return time.perf_counter() - self._reset_time

    def _task(self):
        while not self._stop_event.is_set():
            target_time = self._reset_time + self.timeout

            while time.perf_counter() < target_time:
                if self._stop_event.is_set():
                    return
                precise_sleep(0.001)  # Sleep in small increments

            if self.callback:
                self.callback()

            if self.repeat:
                self._reset_time = time.perf_counter()
            else:
                break

    def __gt__(self, other):
        return self.time > other

    def __lt__(self, other):
        return self.time < other

    def __del__(self):
        if getOS() == "Windows":
            disable_precision_timing_windows()


# ======================================================================================================================
class IntervalTimer:
    """
    A timer utility to handle fixed-interval loop timing.
    Automatically calculates and aligns to the next interval based on a start time.
    """

    def __init__(self, interval: float, raise_race_condition_error: bool = True):
        self.interval = interval
        self.raise_race_condition_error = raise_race_condition_error
        self.previous_time = time.perf_counter()

    # ------------------------------------------------------------------------------------------------------------------
    def sleep_until_next(self):
        """
        Sleeps until the next interval is reached, starting from the last recorded time.
        Automatically updates the internal time reference.
        """
        target_time = self.previous_time + self.interval
        current_time = time.perf_counter()
        remaining = target_time - current_time

        if remaining <= 0 and self.raise_race_condition_error is True:
            raise Exception("Race Conditions")

        if remaining > 0:
            precise_sleep(remaining)

        self.previous_time = target_time  # Update for the next cycle

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        """
        Resets the internal timer to the current time.
        """
        self.previous_time = time.perf_counter()

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        ...


# ======================================================================================================================
class TimeoutTimer:
    def __init__(self, timeout_time, timeout_callback):
        """
        Initializes the TimeoutTimer.

        :param timeout_time: The timeout duration in seconds.
        :param timeout_callback: The callback function to execute on timeout.
        """
        self.timeout_time = timeout_time
        self.timeout_callback = timeout_callback
        self._last_reset_time = None  # Will track the last reset time
        self._stop_event = threading.Event()
        self._is_running = threading.Event()  # Controls whether the timer is counting
        self._timer_thread = threading.Thread(target=self._run_timer, daemon=True)
        self._timer_thread.start()

    def _run_timer(self):
        """The method executed by the timer thread."""
        while not self._stop_event.is_set():
            # Timer logic only executes if the timer is in a running state
            if self._is_running.is_set():
                if self._last_reset_time is not None and time.time() - self._last_reset_time >= self.timeout_time:
                    # Timer has timed out; trigger the callback and enter timeout state
                    self.timeout_callback()
                    self._is_running.clear()  # Exit the running state
            time.sleep(0.1)  # Small sleep to avoid high CPU usage.

    def start(self):
        """
        Starts the timer. If already running, it continues without resetting the time.
        """
        if not self._is_running.is_set():
            self._is_running.set()
            self._last_reset_time = time.time()

    def reset(self):
        """
        Resets the timer by updating the last reset time.
        """
        if self._is_running.is_set():
            self._last_reset_time = time.time()

    def stop(self):
        """
        Stops the timer (ends the running state but keeps the thread alive).
        """
        self._is_running.clear()

    def close(self):
        """
        Fully stops the timer thread and terminates it.
        """
        self._stop_event.set()
        self._timer_thread.join()


# ======================================================================================================================
def setInterval(callback: Callback | Callable, interval: float, *args, **kwargs) -> Timer:
    """
    JS-like setInterval for Python using the existing Timer class.
    Returns a Timer object you can cancel via .stop() or clearInterval().

    :param callback: Function (or Callback) to invoke every `interval` seconds.
    :param interval: Interval in seconds (float).
    :param args: Positional args passed to the callback.
    :param kwargs: Keyword args passed to the callback.
    :return: Timer (call .stop() to cancel).
    """

    def _runner():
        try:
            callback(*args, **kwargs)
        except Exception:
            import traceback
            traceback.print_exc()

    t = Timer(timeout=interval, repeat=True, callback=_runner)
    t.start()
    return t


def clearInterval(timer: Timer) -> None:
    """
    JS-like clearInterval. Stops the provided Timer.
    """
    if timer is not None:
        timer.stop()


@contextmanager
def measure_time(label="Operation"):
    start = time.perf_counter()
    yield
    print(f"{label} took {(time.perf_counter() - start) * 1000:.1f} ms")


# ======================================================================================================================
def example_timer():
    previous_time = time.perf_counter()

    def timer_timeout_callback():
        nonlocal previous_time
        x = time.perf_counter()
        print(f"Timer Timeout {x - previous_time}")
        previous_time = x

    timer = Timer(timeout=0.05, repeat=True, callback=timer_timeout_callback)

    timer.start()

    while True:
        time.sleep(10)


# ----------------------------------------------------------------------------------------------------------------------
def example_precision_timer():
    previous_time = time.perf_counter()

    def timer_timeout_callback():
        nonlocal previous_time
        x = time.perf_counter()
        print(f"Precision Timer Timeout {x - previous_time}")
        previous_time = x

    timer = PrecisionTimer(timeout=1, repeat=True, callback=timer_timeout_callback)

    timer.start()

    time.sleep(5)

    timer.stop()

    time.sleep(1)


# ----------------------------------------------------------------------------------------------------------------------
def example_precise_sleep():
    while True:
        time1 = time.perf_counter()
        precise_sleep(0.01)
        time2 = time.perf_counter()
        print(f"Precise Sleep Time {time2 - time1}")


# Example usage:
if __name__ == "__main__":
    # example_precision_timer()
    example_precise_sleep()
