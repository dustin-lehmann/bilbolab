import threading
import time
from threading import Timer as ThreadTimer

from utils.callbacks import Callback, callback_handler, CallbackContainer


def time_ms():
    return int(time.time_ns() / 1000)


class IntervalTimer:
    """
    A timer utility to handle fixed-interval loop timing.
    Automatically calculates and aligns to the next interval based on a start time.
    """

    def __init__(self, interval: float):
        self.interval = interval
        self.previous_time = time.perf_counter()

    def sleep_until_next(self):
        """
        Sleeps until the next interval is reached, starting from the last recorded time.
        Automatically updates the internal time reference.
        """
        target_time = self.previous_time + self.interval
        current_time = time.perf_counter()
        remaining = target_time - current_time

        if remaining <= 0:
            raise Exception("Race Conditions")

        if remaining > 0:
            precise_sleep(remaining)

        self.previous_time = target_time  # Update for the next cycle

    def reset(self):
        """
        Resets the internal timer to the current time.
        """
        self.previous_time = time.perf_counter()


def precise_sleep(seconds: float):
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


@callback_handler
class Timer_Callbacks:
    timeout: CallbackContainer


class Timer:
    _reset_time: float

    timeout: float
    repeat: bool

    callbacks: Timer_Callbacks
    _threadTimer: ThreadTimer

    _stop: bool

    def __init__(self):
        self._reset_time = time.time()
        self.timeout = None
        self.repeat = False

        self._threadTimer = None

        self.callbacks = Timer_Callbacks()

    # ------------------------------------------------------------------------------------------------------------------

    def start(self, timeout=None, repeat: bool = True):
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
        self._threadTimer = None

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
            self._threadTimer = None

    # ------------------------------------------------------------------------------------------------------------------
    def __gt__(self, other):
        return self.time > other

    # ------------------------------------------------------------------------------------------------------------------
    def __lt__(self, other):
        return self.time < other


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


def performance_analyzer(func):
    """
    Decorator to track and print the execution time of a function.
    """

    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Function '{func.__name__}' executed in {elapsed_time:.4f} seconds")
        return result

    return wrapper


class PerformanceTimer:
    def __init__(self, name: str = None, unit: str = 'ms', print_output: bool = True):
        assert unit in ['ms', 's']
        self.unit = unit
        self.factor = 1000 if unit == 'ms' else 1
        self.start_time = time.perf_counter()
        self.print_output = print_output
        self.name = name

    def stop(self):
        elapsed_time = time.perf_counter() - self.start_time
        if self.print_output:
            print(f"[Timer {self.name}] Elapsed time: {elapsed_time * self.factor:.1f} {self.unit}")
        return elapsed_time
# ======================================================================================================================
def example_precise_sleep():
    while True:
        time1 = time.perf_counter()
        # time.sleep(0.001)
        precise_sleep(2.01)
        time2 = time.perf_counter()
        print(f"Sleep for 0.1 seconds. Time: {time2 - time1:.6f}")


if __name__ == '__main__':
    timer = PerformanceTimer()
    precise_sleep(0.1)
    timer.stop()