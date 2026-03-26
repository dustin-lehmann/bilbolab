"""
Logging utilities module.

This module provides functionality for logging to the console and files,
as well as the ability to redirect log messages through custom callables.
Users can enable a redirection and choose whether to redirect all logs or only
those logs that would also be output to the console (i.e. those that meet the
current log level threshold).
"""

import inspect
import logging
import os
import atexit
import threading
from datetime import datetime
from dataclasses import dataclass
from core.utils import colors
from core.utils import string_utils as string_utils

# Define mapping for log level names to numeric levels
LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
    "IMPORTANT": 25,
}

logging.addLevelName(LOG_LEVELS["IMPORTANT"], "IMPORTANT")

# Central color map by numeric log level (importable from other modules)
LOGGING_COLORS = {
    logging.DEBUG: colors.DARK_GREY,
    LOG_LEVELS['IMPORTANT']: colors.MEDIUM_GREEN,
    logging.INFO: colors.WHITE,
    logging.WARNING: colors.MEDIUM_ORANGE,
    logging.ERROR: colors.RED,
    logging.CRITICAL: colors.RED,
}

# List to store all enabled redirections
redirections = []

# Global variable to manage file logging state
log_files: dict = {}

# Global dictionary to store custom Logger instances to prevent duplicates.
custom_loggers = {}

_show_log_file = False
_show_log_level = False


def setLoggingSettings(show_log_file=False, show_log_level=False):
    """
    Update global formatting flags and reconfigure all existing Logger instances
    so they pick up the new settings immediately.
    """
    global _show_log_file, _show_log_level
    _show_log_file = show_log_file
    _show_log_level = show_log_level

    # Re-apply formatter settings on every existing Logger
    for lg in custom_loggers.values():
        if hasattr(lg, '_apply_formatter_settings'):
            lg._apply_formatter_settings()


@atexit.register
def cleanup(*args, **kwargs):
    """
    Closes all open log files when the program exits.
    """
    global log_files
    for filename, data in log_files.items():
        data['file'].close()


@dataclass
class LogRedirection:
    """
    Class representing a log redirection.

    Attributes:
        func (callable): The function to call for redirection.
        minimum_level (int): Minimum level a message must have to be redirected (if not redirect_all).
        redirect_all (bool): If True, all logs are redirected. If False, only
                             logs that would be printed to the console are redirected.
    """
    func: callable
    minimum_level: int = logging.NOTSET
    redirect_all: bool = False


def enable_redirection(func, redirect_all: bool = False, minimum_level: int | str = logging.NOTSET):
    """
    Enables a log redirection.

    Parameters:
        func (callable): The function to be called for log redirection.
        redirect_all (bool): If True, redirect all log messages. If False, only
                             redirect logs that meet or exceed the console log level.
        minimum_level (int | str): Minimum log level to redirect (applies only if not redirect_all).
    """
    global redirections
    if isinstance(minimum_level, str):
        minimum_level = LOG_LEVELS.get(minimum_level, logging.NOTSET)
    redirections.append(LogRedirection(func, minimum_level=minimum_level, redirect_all=redirect_all))


# Alias for backward compatibility
addLogRedirection = enable_redirection


def disable_redirection(func):
    """
    Disables a previously enabled log redirection.

    Parameters:
        func (callable): The redirection function to disable.
    """
    global redirections
    redirections[:] = [redir for redir in redirections if redir.func != func]


def enable_file_logging(filename, path='./', custom_header: str = '', log_all_levels=False):
    """
    Enables file logging. Creates a log file with the name "<filename>_yyyymmdd_hhmmss.log".

    Parameters:
        filename (str): The base name of the log file.
        path (str): Directory where the log file will be saved.
        custom_header (str): Optional header information to include in the log.
        log_all_levels (bool): If True, all logs are written to the file regardless of level.
    """
    global log_files

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{path}/{filename}_{timestamp}.log"

    try:
        log_file = open(log_filename, 'a')
        log_file.write("BILBO Log\n")
        log_file.write(f"Time {timestamp}: {custom_header}\n")
        log_file.write("YYYY-MM-DD_hh-mm-ss-ms \t Logger \t Level \t Log\n")
        log_files[filename] = {
            'file': log_file,
            'all_levels': log_all_levels,
            'lock': threading.Lock()
        }
        print(f"File logging enabled. Logging to file: {log_filename}")
    except IOError as e:
        print(f"Failed to open log file {log_filename}: {e}")


def stop_file_logging(filename=None):
    """
    Stops file logging and closes the log file(s).

    Parameters:
        filename (str, optional): If provided, only the log file with this base name is stopped.
                                  Otherwise, all log files are closed.
    """
    global log_files

    if filename is not None:
        if filename in log_files:
            log_files[filename]['file'].close()
            log_files.pop(filename)
            print(f"File logging stopped for {filename}.")
    else:
        for filename, data in log_files.items():
            data['file'].close()
            print(f"File logging stopped for {filename}.")
        log_files = {}


def handle_log(log, logger: 'Logger', level):
    """
    Handles a log message by formatting it and sending it to any enabled redirections and file loggers.

    Parameters:
        log (str): The log message.
        logger (Logger): The logger instance issuing the log.
        level (int or str): The numeric or string log level.
    """
    global log_files

    # Convert level from string to numeric value if necessary
    if isinstance(level, str):
        level = LOG_LEVELS.get(level, logging.NOTSET)

    # Create reverse mapping to get level name from numeric level
    reversed_levels = {v: k for k, v in LOG_LEVELS.items()}
    level_name = reversed_levels.get(level, "NOTSET")

    current_time = datetime.now().strftime("%Y-%m-%d:%H-%M-%S-%f")[:-3]
    log_entry = f"{current_time}\t{logger.name}\t{level_name}\t{log}\n"

    # Process redirections: if a redirection is set to redirect_all, send all logs;
    # otherwise, only send logs that meet or exceed the logger's threshold.
    for redir in redirections:
        if redir.redirect_all or (level >= logger.level and level >= redir.minimum_level):
            redir.func(log_entry, log, logger, level)

    # Write log entries to file(s) if file logging is enabled
    try:
        for filename, log_file_data in log_files.items():
            with log_file_data['lock']:
                if level >= logger.level or log_file_data['all_levels']:
                    log_file_data['file'].write(log_entry)
                    log_file_data['file'].flush()
    except IOError as e:
        print(f"Failed to write to log file: {e}")


def disableAllOtherLoggers(module_name=None):
    """
    Disables all loggers except the one associated with the provided module name.

    Parameters:
        module_name (str, optional): The module name whose logger should remain enabled.
    """
    for log_name, log_obj in logging.Logger.manager.loggerDict.items():
        if log_name != module_name:
            log_obj.disabled = True


def disableLoggers(loggers: list):
    """
    Disables loggers whose names are in the provided list.

    Parameters:
        loggers (list): A list of logger names to disable.
    """
    for log_name, log_obj in logging.Logger.manager.loggerDict.items():
        if log_name in loggers:
            log_obj.disabled = True


def getLoggerByName(logger_name: str):
    """
    Retrieves a logger by its name.

    Parameters:
        logger_name (str): The name of the logger to retrieve.

    Returns:
        Logger or None: The logger object if found, otherwise None.
    """
    for log_name, log_obj in logging.Logger.manager.loggerDict.items():
        if log_name == logger_name:
            return log_obj
    return None


def setLoggerLevel(logger, level=logging.DEBUG):
    """
    Sets the logging level for one or more loggers.

    Parameters:
        logger (str, list, or list of tuples): The logger name(s) or a list of tuples
                                               (logger_name, level) to set levels.
        level (int or str): The logging level to set (used if logger is a single name or list of names).
    """
    # Convert level if it's a string.
    if isinstance(level, str):
        level = LOG_LEVELS.get(level, logging.NOTSET)

    if isinstance(logger, str):
        l = logging.getLogger(logger)
        l.setLevel(level)
    elif isinstance(logger, list) and all(isinstance(l, tuple) for l in logger):
        for logger_tuple in logger:
            logger_name, lvl = logger_tuple
            if isinstance(lvl, str):
                lvl = LOG_LEVELS.get(lvl, logging.NOTSET)
            l = getLoggerByName(logger_name)
            if l is not None:
                l.setLevel(lvl)
    elif isinstance(logger, list) and all(isinstance(l, str) for l in logger):
        for logger_name in logger:
            logger_object = getLoggerByName(logger_name)
            if logger_object is not None:
                logger_object.setLevel(level)


class CustomFormatter(logging.Formatter):
    """
    Custom log formatter that applies color formatting based on the log level.
    """
    _filename: str

    def __init__(self):
        super().__init__()

        # Remove any existing handlers from the root logger
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        if _show_log_level:
            if _show_log_file:
                self.str_format = "%(asctime)s.%(msecs)03d %(levelname)-12s  %(name)-20s %(filename)-30s  %(message)s"
            else:
                self.str_format = "%(asctime)s.%(msecs)03d %(levelname)-12s  %(name)-20s  %(message)s"
        else:
            if _show_log_file:
                self.str_format = "%(asctime)s.%(msecs)03d %(name)-20s %(filename)-30s  %(message)s"
            else:
                self.str_format = "%(asctime)s.%(msecs)03d %(name)-20s  %(message)s"

        self._filename = None

        # Define color formats for each log level
        self.FORMATS = {
            logging.DEBUG: string_utils.escapeCode(colors.DARK_GREY) + self.str_format + string_utils.reset,
            LOG_LEVELS['IMPORTANT']: string_utils.escapeCode(
                colors.MEDIUM_GREEN) + self.str_format + string_utils.reset,
            logging.INFO: string_utils.escapeCode(colors.CYAN) + self.str_format + string_utils.reset,
            logging.WARNING: string_utils.escapeCode(colors.MEDIUM_ORANGE) + self.str_format + string_utils.reset,
            logging.ERROR: string_utils.red + self.str_format + string_utils.reset,
            logging.CRITICAL: string_utils.bold_red + self.str_format + string_utils.reset
        }

    def setFileName(self, filename):
        """
        Sets the filename to be included in log records.

        Parameters:
            filename (str): The filename to display in the log.
        """
        self._filename = filename

    def format(self, record):
        """
        Formats the log record with the appropriate colors and formatting.

        Parameters:
            record (LogRecord): The log record to format.

        Returns:
            str: The formatted log message.
        """
        log_fmt = self.FORMATS.get(record.levelno, self.str_format)
        formatter = logging.Formatter(log_fmt, "%H:%M:%S")
        record.filename = self._filename
        record.levelname = f'[{record.levelname}]'
        record.filename = f'({record.filename})'
        record.name = f'[{record.name}]'
        record.filename = f'{record.filename}:'
        return formatter.format(record)


class Logger:
    """
    Custom Logger class that wraps Python's standard logging.Logger.
    Provides methods for colored console output, file logging, and log redirection.
    """
    _logger: logging.Logger
    name: str
    color: list

    def __new__(cls, name, *args, **kwargs):
        global custom_loggers
        if name in custom_loggers:
            return custom_loggers[name]
        instance = super(Logger, cls).__new__(cls)
        custom_loggers[name] = instance
        return instance

    def __init__(self, name, level: str = 'INFO', info_color=colors.LIGHT_GREY, background=None, color=None):
        # Ensure mapping dict exists even if re-initializing existing logger
        if not hasattr(self, '_level_map'):
            self._level_map = {}

        self.name = name
        self._logger = logging.getLogger(name)
        # Check if the underlying logger has already been configured.
        if getattr(self._logger, '_custom_initialized', False):
            self.setLevel(level)
            return

        self.setLevel(level)
        self.color = color

        # Convert RGB tuple/list to 256-color escape if necessary.
        if isinstance(info_color, tuple) or isinstance(info_color, list):
            info_color = string_utils.rgb_to_256color_escape(info_color, background)

        # Create a new formatter and add a stream handler only once.
        self.formatter = CustomFormatter()
        self.stream_handler = logging.StreamHandler()
        self.stream_handler.setFormatter(self.formatter)
        self._logger.addHandler(self.stream_handler)
        self._logger.propagate = False
        self._logger._custom_initialized = True

    def _apply_formatter_settings(self):
        """
        Re-create the CustomFormatter (respecting the current
        _show_log_file/_show_log_level flags) and re-attach it
        to the stream handler.
        """
        # build a fresh formatter using the updated globals
        new_fmt = CustomFormatter()
        self.formatter = new_fmt

        # swap the formatter on the existing stream handler
        self.stream_handler.setFormatter(new_fmt)

    @staticmethod
    def getFileName():
        """
        Retrieves the filename of the caller.

        Returns:
            str: The base name of the caller's file.
        """
        frame = inspect.currentframe().f_back.f_back
        filename = frame.f_globals.get('__file__', 'unknown')
        return os.path.basename(filename)

    def _mapped_log(self, original_level, msg, *args, **kwargs):
        """
        Internal helper to remap a log call from original_level to a mapped
        level (if configured), then emit the log and handle redirections/file output.
        """
        self.formatter.setFileName(self.getFileName())
        mapped_level = self._level_map.get(original_level, original_level)
        self._logger.log(mapped_level, msg, *args, **kwargs)
        handle_log(msg, logger=self, level=mapped_level)

    def debug(self, msg, *args, **kwargs):
        self._mapped_log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._mapped_log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._mapped_log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._mapped_log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self._mapped_log(logging.CRITICAL, msg, *args, **kwargs)

    def important(self, msg, *args, **kwargs):
        self._mapped_log(LOG_LEVELS['IMPORTANT'], msg, *args, **kwargs)

    def setLevel(self, level):
        """
        Sets the logging level for this logger.

        Parameters:
            level (str or int): The logging level to set. If a string, it must be one of the keys in LOG_LEVELS.
        """
        if isinstance(level, str):
            if level not in LOG_LEVELS:
                raise ValueError('Invalid log level')
            numeric_level = LOG_LEVELS[level]
        elif isinstance(level, int):
            numeric_level = level
        else:
            raise ValueError('Level must be a string or integer')

        self._logger.setLevel(numeric_level)

    @property
    def level(self):
        """
        Retrieves the current logging level from the underlying logger.
        """
        return self._logger.level

    # === STATIC FORMATTING HELPERS (for startup banners, phase separators, etc.) ====
    @staticmethod
    def _print_stderr(text: str):
        """Print to stderr (same stream as logging) to guarantee correct ordering with log messages."""
        import sys
        sys.stderr.write(text + '\n')
        sys.stderr.flush()

    @staticmethod
    def section(title: str, width: int = 70):
        """Print a section separator line with a title, e.g. '── Communication ──────'"""
        fill = width - len(title) - 4  # 4 = '── ' + ' '
        if fill < 2:
            fill = 2
        line = f"\u2500\u2500 {title} " + "\u2500" * fill
        colored = f"{string_utils.escapeCode(colors.GREY)}{line}{string_utils.reset}"
        Logger._print_stderr(colored)

    @staticmethod
    def banner(lines: list[str], width: int = 60, color=colors.MEDIUM_GREEN):
        """Print a box banner, e.g. for startup/shutdown milestones."""
        esc = string_utils.escapeCode(color)
        rst = string_utils.reset
        border = "\u2550" * width
        parts = [f"{esc}\u2554{border}\u2557{rst}"]
        for text in lines:
            padding = width - len(text) - 2
            if padding < 0:
                padding = 0
            parts.append(f"{esc}\u2551  {text}{' ' * padding}\u2551{rst}")
        parts.append(f"{esc}\u255a{border}\u255d{rst}")
        Logger._print_stderr('\n'.join(parts))

    @staticmethod
    def divider(width: int = 70, color=colors.GREY):
        """Print a simple horizontal divider line."""
        esc = string_utils.escapeCode(color)
        rst = string_utils.reset
        Logger._print_stderr(f"{esc}{'\u2500' * width}{rst}")

    def switchLoggingLevel(self, level_from, level_to):
        """
        Remaps log calls from level_from to level_to for this logger.

        For example, downgrade all INFO calls to DEBUG so that calls to .info()
        will be emitted as DEBUG-level logs.
        """
        if isinstance(level_from, str):
            lvl_from = LOG_LEVELS.get(level_from.upper())
            if lvl_from is None:
                raise ValueError(f"Invalid level_from: {level_from}")
        elif isinstance(level_from, int):
            lvl_from = level_from
        else:
            raise ValueError("level_from must be a string or integer")

        if isinstance(level_to, str):
            lvl_to = LOG_LEVELS.get(level_to.upper())
            if lvl_to is None:
                raise ValueError(f"Invalid level_to: {level_to}")
        elif isinstance(level_to, int):
            lvl_to = level_to
        else:
            raise ValueError("level_to must be a string or integer")

        self._level_map[lvl_from] = lvl_to


if __name__ == '__main__':
    logger = Logger('test', 'DEBUG')
    setLoggingSettings(show_log_file=False, show_log_level=False)
    logger.info('This is an info message')
    logger.warning('This is a warning message')
    logger.debug('This is a debug message')
    logger.important('This is an important message')
    logger.error('This is an error message')
    logger.critical('This is a critical message')
