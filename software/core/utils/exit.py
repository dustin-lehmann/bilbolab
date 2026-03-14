import atexit
import inspect
import signal
import weakref
import threading
import sys
import os
import time

"""
This module provides a module-wide exit callback registry that allows you to register
exit callbacks from any thread. Every registered callback is stored as a weak reference,
so that if the owning object is garbage collected the callback will not be invoked.

Callbacks are registered via the function:
    register_exit_callback(callback, priority=1)

Callbacks are expected to have the signature:
    callback(signum, frame)
where signum and frame are provided if the exit is triggered via a signal, or may be None
if the exit is normal.

The global exit handler is automatically registered in the main thread for SIGINT (Ctrl-C),
and SIGTERM (termination signal), and SIGHUP (PyCharm Stop). Also, it is registered via
the atexit module to trigger upon normal interpreter shutdown. When the exit handler fires,
it sorts callbacks in descending order (highest priority first) and calls each one safely.
"""

# --- Global Callback Registry ---
# A list of tuples: (priority, weakref to callback).
_global_exit_callbacks = []
_global_exit_callbacks_lock = threading.Lock()
_global_exit_called = False  # Guard flag to prevent duplicate execution.

_EXIT_CALLBACK_TIMEOUT = 3

DEBUG_OUTPUTS = False


def exit_program(exit_code: int = 0, *, force: bool = True) -> None:
    """
    Exit the program *cleanly* by running registered exit callbacks once,
    then terminating the process.

    Args:
        exit_code: Process exit code.
        force: If True, always end with os._exit(exit_code) to ensure no
               non-daemon threads keep the process alive. If False, use
               sys.exit(exit_code) after callbacks (lets Python unwind).

    Notes:
        - This is safe to call from any thread.
        - If called from the main thread, we pass a real frame.
        - If called from a non-main thread, we pass frame=None.
    """
    global _global_exit_called

    # Ensure only one caller actually performs shutdown.
    with _global_exit_callbacks_lock:
        if _global_exit_called:
            # Another thread/signal already initiated shutdown.
            if force:
                os._exit(exit_code)
            raise SystemExit(exit_code)
        _global_exit_called = True

    # Provide a best-effort "frame" when called from main thread.
    frame = None
    if threading.current_thread() == threading.main_thread():
        try:
            frame = sys._getframe(1)
        except Exception:
            frame = None

    # Run callbacks.
    try:
        _execute_exit_callbacks(signum=None, frame=frame)
    finally:
        # End the process.
        if force:
            os._exit(exit_code)
        raise SystemExit(exit_code)


def register_exit_callback(callback, priority=1):
    """
    Register an exit callback to be executed when the global exit handler is triggered.

    Parameters:
        callback (callable): A callable with the signature callback(signum, frame).
                             It will be stored as a weak reference.
        priority (int): Priority of the callback. Higher values are executed first.
                        Default is 1.

    Raises:
        ValueError if callback is not callable.
    """
    if not callable(callback):
        raise ValueError("Provided callback is not callable.")

    try:
        # For bound methods, use WeakMethod; otherwise, use a normal weak reference.
        if hasattr(callback, '__self__') and callback.__self__ is not None:
            callback_ref = weakref.WeakMethod(callback)
        else:
            callback_ref = weakref.ref(callback)
    except TypeError:
        # Fallback for callables that cannot be weakly referenced.
        callback_ref = lambda: callback

    with _global_exit_callbacks_lock:
        # before appending, log exactly who-and-where
        try:
            fn = callback.__qualname__
            src = inspect.getsourcefile(callback)
            line = inspect.getsourcelines(callback)[1]
        except Exception:
            fn, src, line = repr(callback), "<unknown>", 0

        if DEBUG_OUTPUTS:
            print(f"[ExitHandler] adding {fn!r} (prio={priority}) from {src}:{line}")
        _global_exit_callbacks.append((priority, callback_ref))


class _CallbackTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _CallbackTimeout()


def _execute_exit_callbacks(signum=None, frame=None):
    """
    Execute all registered exit callbacks in descending order of priority.
    Each one gets at most _EXIT_CALLBACK_TIMEOUT seconds before we give up.
    """
    with _global_exit_callbacks_lock:
        callbacks = list(_global_exit_callbacks)

    if DEBUG_OUTPUTS:
        print(f"[ExitHandler] about to run {len(callbacks)} callbacks:")
        for prio, cref in callbacks:
            cb = cref()
            print(f"{cb} Prio: {prio}")

    with _global_exit_callbacks_lock:
        callbacks = list(_global_exit_callbacks)

    callbacks.sort(key=lambda tup: tup[0], reverse=True)

    for priority, callback_ref in callbacks:
        # resolve the weakref
        callback = None
        try:
            callback = callback_ref()
        except Exception as e:
            print(f"[ExitHandler] ❌ error retrieving callback (priority={priority}): {e}")
            continue

        if callback is None:
            # it was garbage-collected
            continue

        # figure out a human-readable name and file/line
        try:
            name = getattr(callback, "__qualname__", callback.__name__)
        except Exception:
            name = repr(callback)
        try:
            srcfile = inspect.getsourcefile(callback) or inspect.getfile(callback)
            _, lineno = inspect.getsourcelines(callback)
        except (OSError, TypeError):
            srcfile = "<unknown>"
            lineno = 0

        if DEBUG_OUTPUTS:
            print(f"[ExitHandler {signum}] → calling {name} (priority={priority}) defined at {srcfile}:{lineno}")

        # set up the alarm-based timeout (Unix/POSIX only)
        old_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _alarm_handler)
        signal.setitimer(signal.ITIMER_REAL, _EXIT_CALLBACK_TIMEOUT)

        try:
            callback()
        except _CallbackTimeout:
            if DEBUG_OUTPUTS:
                print(f"[ExitHandler] ⏰ timeout: {name} did not finish within {_EXIT_CALLBACK_TIMEOUT}s, skipping")
        except Exception as e:
            if DEBUG_OUTPUTS:
                print(f"[ExitHandler] ❌ exception in {name}: {e}")
        finally:
            # cancel and restore
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)


def _global_exit_handler(signum=None, frame=None):
    """
    Global exit handler that is triggered either by a signal or via atexit.
    It safely calls all registered callbacks only once.

    Parameters:
        signum (int): Signal number if triggered by a signal; otherwise None.
        frame (frame): The current stack frame if triggered by a signal; otherwise None.
    """
    global _global_exit_called
    if DEBUG_OUTPUTS:
        print(f"=== ENTER EXIT HANDLER : {signum} Frame: {frame}. Callbacks: {len(list(_global_exit_callbacks))} ===")
    # traceback.print_stack(frame)
    if _global_exit_called:
        return  # Prevent duplicate execution.
    _global_exit_called = True

    _execute_exit_callbacks(signum, frame)

    # Always do an immediate, hard exit so no threads are left running.
    if DEBUG_OUTPUTS:
        print(f"[EXIT HANDLER]: EXIT PROGRAM")
    os._exit(0)


# --- Automatic Registration in the Main Thread ---
if threading.current_thread() == threading.main_thread():
    # Register our global exit handler for SIGINT, SIGTERM, and SIGHUP.
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda signum, frame: _global_exit_handler(signum, frame))

    # Also register our handler with the atexit module for normal shutdown.
    atexit.register(_global_exit_handler, None, None)


def infinite_loop():
    """Block the calling thread forever, sleeping in 1-second intervals."""
    while True:
        time.sleep(1)


# --- Example and Simulation Scenarios ---
if __name__ == '__main__':
    print("Registering exit callbacks from various contexts...\n")


    # Simple functions to use as exit callbacks.
    def cleanup_low():
        time.sleep(5)
        print("Low priority cleanup executed. (priority 1)")


    def cleanup_high():
        print("High priority cleanup executed. (priority 3)")


    # Register simple functions.
    register_exit_callback(cleanup_low, priority=1)
    register_exit_callback(cleanup_high, priority=3)


    # A class with a bound method as exit callback.
    class MyObject:
        def __init__(self, name):
            self.name = name
            register_exit_callback(self.cleanup, priority=2)

        def cleanup(self):
            print(f"MyObject '{self.name}' cleanup executed. (priority 2) | signum:")


    # Create an instance that registers its cleanup method.
    obj = MyObject("TestObject")


    # Register a callback that deliberately raises an exception to test safety.
    def faulty_callback():
        print("Faulty callback executing. (priority 2)")
        raise ValueError("Simulated error in exit callback")


    # register_exit_callback(faulty_callback, priority=2)

    # --- Simulation functions for different exit scenarios ---
    def simulate_signal_exit():
        print("\nSimulating SIGINT signal exit...")
        _global_exit_handler(signal.SIGINT, None)


    def simulate_exception_exit():
        print("\nSimulating exit due to an unhandled exception...")
        try:
            raise Exception("Simulated unhandled exception")
        except Exception as e:
            print("Exception caught in simulation:", e)
            _global_exit_handler(None, None)


    def simulate_normal_exit():
        print("\nSimulating normal program exit...")
        while True:
            time.sleep(1)
            print("HELLO")
        sys.exit(0)


    # --- Let the user choose a simulation scenario ---
    print("Choose a scenario to simulate:")
    print("1: Simulate SIGINT signal exit")
    print("2: Simulate exit due to unhandled exception")
    print("3: Simulate normal program exit")

    choice = input("Enter choice (1/2/3): ").strip()
    if choice == "1":
        simulate_signal_exit()
    elif choice == "2":
        simulate_exception_exit()
    elif choice == "3":
        simulate_normal_exit()
    else:
        print("Invalid choice. Exiting normally...")
        # In a normal exit (without signal), _global_exit_handler will be automatically
        # triggered via atexit.
