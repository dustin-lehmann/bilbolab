import os
import fcntl
import signal
import sys
import time
import tempfile
from core.utils.exit import register_exit_callback


def resolve_lock_file_path(lock_file="default.lock"):
    """
    Resolves the path of the lock file based on the input.

    Args:
        lock_file (str): The user-provided lock file name or path.

    Returns:
        str: The resolved absolute path to the lock file.
    """
    if lock_file.endswith(".lock") and not os.path.isabs(lock_file):
        return os.path.join(tempfile.gettempdir(), lock_file)

    if os.path.isabs(lock_file) and os.path.exists(os.path.dirname(lock_file)):
        return lock_file

    return os.path.join(tempfile.gettempdir(), os.path.basename(lock_file))


def process_running(pid):
    """
    Checks if a process with the given PID is running.

    Args:
        pid (int): The process ID to check.

    Returns:
        bool: True if the process is running, False otherwise.
    """
    try:
        os.kill(pid, 0)  # Signal 0 checks process existence
        return True
    except (ProcessLookupError, ValueError):
        return False


class SingletonLock:
    """
    A cross-platform singleton lock class to ensure that only one instance of a process can run at a time.

    Attributes:
        lock_file (str): Path to the lock file.
        override (bool): If True, allows this instance to take over the lock.
        timeout (float): Time in seconds to wait for acquiring the lock. None means no waiting.
        mode (str): An optional mode string to write into the lock file.
    """

    def __init__(self, lock_file="default.lock", override=False, timeout=None, mode=None, override_timeout=5):
        self.lock_file = resolve_lock_file_path(lock_file)
        self.lock_fd = None
        self.override = override
        self.timeout = timeout
        self.override_timeout = override_timeout
        self.lock_acquired = False
        self.mode = mode
        register_exit_callback(self._release_lock)
        self.script = os.path.basename(sys.argv[0])  # Top-level script

    def _release_lock(self, *args, **kwargs):
        """
        Releases the lock and removes the lock file if owned by the current process.
        """
        if self.lock_acquired:
            try:
                if self.lock_fd:
                    self.lock_fd.seek(0)
                    pid_in_file = self.lock_fd.read().strip().split("\n")[0]
                    if pid_in_file == str(os.getpid()):
                        fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                        self.lock_fd.close()
                        self.lock_fd = None
                        if os.path.exists(self.lock_file):
                            os.remove(self.lock_file)
                        print(f"Lock released and lock file '{self.lock_file}' removed.")
                    else:
                        print(f"Lock file '{self.lock_file}' is not owned by this process. Skipping removal.")
            except Exception as e:
                print(f"Error releasing lock: {e}")
            finally:
                self.lock_acquired = False

    def __enter__(self):
        """
        Acquires the lock and writes the current PID, script name, and optional mode to the lock file.

        Returns:
            self: The SingletonLock instance.
        """
        start_time = time.time()
        while True:
            try:
                if os.path.exists(self.lock_file):
                    with open(self.lock_file, "r") as f:
                        pid = int(f.readline().strip())
                        if process_running(pid):
                            if self.override:
                                print(f"Overriding lock held by process {pid}.")
                                os.kill(pid, signal.SIGTERM)
                                time.sleep(1)  # Allow time for the process to clean up
                                elapsed = 0
                                while os.path.exists(self.lock_file) and elapsed < self.override_timeout:
                                    time.sleep(0.1)
                                    elapsed = time.time() - start_time
                                if os.path.exists(self.lock_file):
                                    print(f"Timeout: Forcefully removing stale lock file '{self.lock_file}'.")
                                    os.remove(self.lock_file)
                            else:
                                raise RuntimeError(f"Lock held by process {pid}.")
                        else:
                            print(f"Removing stale lock file '{self.lock_file}'.")
                            os.remove(self.lock_file)

                self.lock_fd = open(self.lock_file, "w+")
                fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.lock_acquired = True
                self.lock_fd.truncate(0)
                self.lock_fd.write(f"{os.getpid()}\n{self.script}\n{self.mode or ''}")
                self.lock_fd.flush()
                print(f"Lock acquired by {self.script} with mode {self.mode}")
                break
            except IOError:
                if self.timeout is not None:
                    elapsed = time.time() - start_time
                    if elapsed >= self.timeout:
                        raise RuntimeError(f"Timeout: Unable to acquire lock within {self.timeout} seconds.")
                    time.sleep(0.1)
                else:
                    sys.exit(1)
        return self

    def __del__(self):
        self._release_lock()

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Releases the lock when exiting the context.
        """
        self._release_lock()

    def get_mode(self):
        """
        Reads and returns the mode from the lock file, if available.

        Returns:
            str: The mode string, or None if not found.
        """
        if os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, "r") as f:
                    f.readline()  # Skip PID line
                    f.readline()  # Skip script line
                    return f.readline().strip() or None
            except Exception as e:
                print(f"Error reading mode: {e}")
        return None

    def get_script(self):
        """
        Reads and returns the script name from the lock file, if available.

        Returns:
            str: The script name, or None if not found.
        """
        if os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, "r") as f:
                    f.readline()  # Skip PID line
                    return f.readline().strip() or None
            except Exception as e:
                print(f"Error reading script: {e}")
        return None


def get_lock_mode(lock_file="default.lock"):
    """
    Reads the mode from the lock file.

    Args:
        lock_file (str): The user-provided lock file name or path. Defaults to 'default.lock'.

    Returns:
        str: Mode string, or None if not found.
    """
    resolved_path = resolve_lock_file_path(lock_file)
    if os.path.exists(resolved_path):
        try:
            with open(resolved_path, "r") as f:
                f.readline()
                f.readline()
                return f.readline().strip() or None
        except Exception as e:
            print(f"Error reading mode: {e}")
    return None


def get_lock_script(lock_file="default.lock"):
    """
    Reads the script name from the lock file.

    Args:
        lock_file (str): The user-provided lock file name or path. Defaults to 'default.lock'.

    Returns:
        str: Script name, or None if not found.
    """
    resolved_path = resolve_lock_file_path(lock_file)
    if os.path.exists(resolved_path):
        try:
            with open(resolved_path, "r") as f:
                f.readline()
                return f.readline().strip() or None
        except Exception as e:
            print(f"Error reading script: {e}")
    return None


def terminate(lock_file="default.lock"):
    """
    Terminates the process holding the lock.

    Args:
        lock_file (str): The user-provided lock file name or path. Defaults to 'default.lock'.
    """
    resolved_path = resolve_lock_file_path(lock_file)
    if os.path.exists(resolved_path):
        try:
            with open(resolved_path, "r") as f:
                pid_line = f.readline().strip()
                pid = int(pid_line)
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            if os.path.exists(resolved_path):
                os.remove(resolved_path)
        except ValueError:
            if os.path.exists(resolved_path):
                os.remove(resolved_path)
        except Exception as e:
            print(f"Unexpected error during termination: {e}")
