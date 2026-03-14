import os
import csv
import enum
import threading
import time
from dataclasses import is_dataclass, fields
from functools import lru_cache

from core.utils.dict_utils import cache_dict_paths_for_flatten, \
    optimized_flatten_dict
from core.utils.files import dirExists, makeDir
from core.utils.time import precise_sleep

# ======================================================================================================================
def read_csv_file(file_path, meta_lines=1):
    """
    Reads a CSV file and separates metadata (top lines) and data (list of dictionaries).

    :param file_path: Path to the CSV file.
    :param meta_lines: Number of lines at the top of the file considered metadata.
    :return: A dictionary with keys:
             - 'meta': List of strings representing metadata lines.
             - 'data': List of dictionaries representing the rows in the CSV file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file '{file_path}' does not exist.")

    with open(file_path, mode='r', newline='', encoding='utf-8') as file:
        lines = file.readlines()

    meta = lines[:meta_lines]  # Extract metadata lines
    csv_data_lines = lines[meta_lines:]  # Remaining lines are CSV data

    data = []
    if csv_data_lines:
        reader = csv.reader(csv_data_lines)
        headers = next(reader)
        types = next(reader)

        def convert_value(value, dtype):
            if dtype == 'int':
                return int(value)
            elif dtype == 'float':
                return float(value)
            elif dtype == 'bool':
                return value.lower() in ('true', '1', 'yes')
            else:  # default to string
                return value

        for row in reader:
            converted_row = {
                headers[i]: convert_value(row[i], types[i]) for i in range(len(headers))
            }
            data.append(_reconstruct_dict(converted_row))

    return {'meta': meta, 'data': data}


def _reconstruct_dict(flat_dict, sep='.'):
    """
    Reconstructs a nested dictionary from a flattened dictionary.
    """
    nested_dict = {}
    for key, value in flat_dict.items():
        keys = key.split(sep)
        d = nested_dict
        for part in keys[:-1]:
            d = d.setdefault(part, {})
        d[keys[-1]] = value
    return nested_dict


# ======================================================================================================================
# Optimized conversion for dataclasses using cached field metadata
@lru_cache(maxsize=None)
def get_dataclass_fields(cls):
    return fields(cls)


def asdict_optimized(obj):
    """
    Recursively converts a dataclass instance to a dict using cached field metadata.
    """
    if is_dataclass(obj):
        result = {}
        for f in get_dataclass_fields(type(obj)):
            value = getattr(obj, f.name)
            result[f.name] = asdict_optimized(value)
        return result
    elif isinstance(obj, (list, tuple)):
        return type(obj)(asdict_optimized(item) for item in obj)
    elif isinstance(obj, dict):
        return {key: asdict_optimized(value) for key, value in obj.items()}
    else:
        return obj


# ======================================================================================================================
class CSVLogger:
    def __init__(self, precision=4):
        """
        Initializes a CSVLogger instance.

        :param precision: The number of digits after the comma for values >= 1,
                          or the number of digits after the first significant digit for values < 1.
        """
        self.precision = precision
        self.file_path = None
        self.file = None
        self.writer = None
        self.fieldnames = None
        self.fieldtypes = None
        self.is_closed = True
        self.index = 0  # Initialize the index column
        self.file_lock = threading.Lock()
        # Cache for the flattening “access paths” of the event structure.
        self._cached_flatten_paths = None

    def _round_float(self, value):
        """
        Rounds a float value based on the logger's precision setting.
        For values >= 1, rounds to 'precision' decimal places.
        For values < 1, rounds so that there are 'precision' digits after the first significant digit.

        :param value: The float value to round.
        :return: The rounded float.
        """
        import math
        if value == 0:
            return 0.0
        abs_value = abs(value)
        if abs_value >= 1:
            return round(value, self.precision)
        else:
            # Determine how many decimal places to use: all digits until the first significant digit plus precision.
            d = -math.floor(math.log10(abs_value))
            return round(value, d + self.precision)

    # ------------------------------------------------------------------------------------------------------------------
    def make_file(self, file, folder="./", custom_text_header=None):
        """
        Creates (or recreates) the CSV file.
        """
        self.index = 0  # Reset the index
        self.file_path = os.path.join(folder, file)
        if not dirExists(folder):
            print(f"Folder '{folder}' does not exist. Creating it...")
            makeDir(folder)
        if os.path.exists(self.file_path):
            print(f"File '{self.file_path}' already exists. Removing it...")
            os.remove(self.file_path)
        self.file = open(self.file_path, mode='w', newline='', encoding='utf-8')
        if custom_text_header:
            if isinstance(custom_text_header, list):
                self.file.write("\n".join(custom_text_header) + "\n")
            else:
                self.file.write(custom_text_header + "\n")
        self.is_closed = False

    @property
    def is_open(self):
        return not self.is_closed

    # ------------------------------------------------------------------------------------------------------------------
    def write_data(self, data):
        """
        Appends data to the CSV file. The data can be a dict, a dataclass instance, or a list of them.
        Uses a cached flattening mapping once the first event has been processed.
        """
        with self.file_lock:
            if self.is_closed:
                return
                # raise RuntimeError("CSVLogger is already closed; cannot log more data.")

            if not isinstance(data, list):
                data = [data]

            flattened_data = []
            for d in data:
                # If the event is a dataclass instance, convert it to a dict first.
                if is_dataclass(d):
                    d = asdict_optimized(d)
                # Use cached flattening if available; otherwise, compute and cache it.
                if self._cached_flatten_paths is None:
                    flat, paths = cache_dict_paths_for_flatten(d)
                    self._cached_flatten_paths = paths
                else:
                    flat = optimized_flatten_dict(d, self._cached_flatten_paths)
                flattened_data.append(flat)

            # Add an index column to each row.
            for i, row in enumerate(flattened_data):
                flattened_data[i] = {'index': self.index, **row}
                self.index += 1

            # Round float values in each row using the helper function.
            for row in flattened_data:
                for key, value in row.items():
                    if isinstance(value, float):
                        row[key] = self._round_float(value)

            # Write header if this is the first batch.
            if self.fieldnames is None:
                self.fieldnames = list(flattened_data[0].keys())
                self.fieldtypes = [self._infer_type(flattened_data[0][key]) for key in self.fieldnames]
                self.writer = csv.writer(self.file)
                self.writer.writerow(self.fieldnames)
                self.writer.writerow(self.fieldtypes)

            for row in flattened_data:
                self.writer.writerow([row.get(field, '') for field in self.fieldnames])

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        """
        Closes the CSV file.
        """
        with self.file_lock:
            if not self.is_closed:
                if self.file:
                    self.file.close()
                self.is_closed = True
            self.file = None

    # ------------------------------------------------------------------------------------------------------------------
    def log_event(self, data):
        """
        Appends a single event's data to the CSV file. Accepts both dicts and dataclass instances.
        """
        self.write_data(data)



    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _infer_type(value):
        """
        Infers a simple type string for the value.
        """
        if isinstance(value, enum.IntEnum):
            return 'int'
        elif isinstance(value, bool):
            return 'bool'
        elif isinstance(value, int):
            return 'int'
        elif isinstance(value, float):
            return 'float'
        else:
            return 'str'

    # ------------------------------------------------------------------------------------------------------------------
    def __del__(self):
        """
        Ensures the CSV file is properly closed when the logger is destroyed.
        """
        self.close()


# ======================================================================================================================
def main():
    """
    Test main function that creates a CSV file and appends data for a couple of seconds.
    """
    logger = CSVLogger(precision=3)
    logger.make_file("test_log.csv", folder="/home/admin/robot/experiments/",
                     custom_text_header=["Test CSV Logger", "Logging data for a couple seconds"])

    print("Starting to log events...")
    start_time = time.time()
    # Log events for approximately 2 seconds.
    while time.time() - start_time < 2:
        # Prepare a sample data event (this can be a dict or a dataclass instance)
        data = {
            "timestamp": time.perf_counter(),
            "event": "log_event",
            "value": logger.index,
            "details": {"subvalue": logger.index * 2, "flag": True}
        }
        logger.log_event(data)
        precise_sleep(0.5)

    logger.close()
    print(f"Logging complete. File saved at: {logger.file_path}")


if __name__ == '__main__':
    main()
