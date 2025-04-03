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
from utils import colors
from utils import string_utils as string_utils

# Define mapping for log level names to numeric levels
LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}

# List to store all enabled redirections
redirections = []

# Global variable to manage file logging state
log_files: dict = {}

# Global dictionary to store custom Logger instances to prevent duplicates.
custom_loggers = {}


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
        redirect_all (bool): If True, all logs are redirected. If False, only
                             logs that would be printed to the console are redirected.
    """
    func: callable
    redirect_all: bool = False


def enable_redirection(func, redirect_all: bool = False):
    """
    Enables a log redirection.

    Parameters:
        func (callable): The function to be called for log redirection.
        redirect_all (bool): If True, redirect all log messages. If False, only
                             redirect logs that meet or exceed the console log level.
    """
    global redirections
    redirections.append(LogRedirection(func, redirect_all))


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
        if redir.redirect_all or level >= logger.level:
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

    def __init__(self, info_color=string_utils.grey):
        super().__init__()

        # Remove any existing handlers from the root logger
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        self.str_format = "%(asctime)s.%(msecs)03d %(levelname)-10s  %(name)-20s %(filename)-30s  %(message)s"
        self._filename = None

        # Define color formats for each log level
        self.FORMATS = {
            logging.DEBUG: string_utils.escapeCode(colors.DARK_BROWN) + self.str_format + string_utils.reset,
            logging.INFO: info_color + self.str_format + string_utils.reset,
            logging.WARNING: string_utils.yellow + self.str_format + string_utils.reset,
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
        self.formatter = CustomFormatter(info_color=info_color)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(self.formatter)
        self._logger.addHandler(stream_handler)
        self._logger.propagate = False
        self._logger._custom_initialized = True

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

    def debug(self, msg, *args, **kwargs):
        """
        Logs a debug-level message.
        """
        self.formatter.setFileName(self.getFileName())
        self._logger.debug(msg, *args, **kwargs)
        handle_log(msg, logger=self, level=logging.DEBUG)

    def info(self, msg, *args, **kwargs):
        """
        Logs an info-level message.
        """
        self.formatter.setFileName(self.getFileName())
        self._logger.info(msg, *args, **kwargs)
        handle_log(msg, logger=self, level=logging.INFO)

    def warning(self, msg, *args, **kwargs):
        """
        Logs a warning-level message.
        """
        self.formatter.setFileName(self.getFileName())
        self._logger.warning(msg, *args, **kwargs)
        handle_log(msg, logger=self, level=logging.WARNING)

    def error(self, msg, *args, **kwargs):
        """
        Logs an error-level message.
        """
        self.formatter.setFileName(self.getFileName())
        self._logger.error(msg, *args, **kwargs)
        handle_log(msg, logger=self, level=logging.ERROR)

    def critical(self, msg, *args, **kwargs):
        """
        Logs a critical-level message.
        """
        self.formatter.setFileName(self.getFileName())
        self._logger.critical(msg, *args, **kwargs)
        handle_log(msg, logger=self, level=logging.CRITICAL)

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
