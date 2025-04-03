import h5py
import numpy as np
import threading
import time
import random

from utils.dict_utils import cache_dict_paths_for_flatten, optimized_flatten_dict, unflatten_dict_baseline
from utils.time import PerformanceTimer


#
# # -----------------------------------------------------------------------------
# # Dummy implementations for self-contained example.
# # In your production code these should be replaced by your optimized versions.
# # -----------------------------------------------------------------------------
#
# def cache_dict_paths_for_flatten(d):
#     """
#     Dummy implementation:
#     Creates a simple cache that maps keys (or nested keys joined by '_') to themselves.
#     """
#     cache = {}
#     for key, value in d.items():
#         if isinstance(value, dict):
#             for subkey in value.keys():
#                 cache[f"{key}_{subkey}"] = (key, subkey)
#         else:
#             cache[key] = key
#     return cache, None
#
#
# def optimized_flatten_dict(d, cache):
#     """
#     Dummy implementation:
#     Flattens one level of nested dicts by joining keys with an underscore.
#     """
#     flat = {}
#     for key, value in d.items():
#         if isinstance(value, dict):
#             for subkey, subvalue in value.items():
#                 flat[f"{key}_{subkey}"] = subvalue
#         else:
#             flat[key] = value
#     return flat
#
#
# def unflatten_dict_baseline(flat_dict):
#     """
#     Dummy implementation:
#     Reconstructs a nested dict from a flat dict assuming keys with an underscore
#     indicate nesting.
#     """
#     d = {}
#     for key, value in flat_dict.items():
#         if "_" in key:
#             main, sub = key.split("_", 1)
#             if main not in d:
#                 d[main] = {}
#             d[main][sub] = value
#         else:
#             d[key] = value
#     return d
#
#
# class PerformanceTimer:
#     def __init__(self):
#         self.start_time = time.time()
#
#     def stop(self):
#         elapsed = time.time() - self.start_time
#         print(f"Elapsed time: {elapsed:.6f} seconds")


# -----------------------------------------------------------------------------
# H5PyDictLogger implementation
# -----------------------------------------------------------------------------

class H5PyDictLogger:
    def __init__(self, filename, dataset_name="samples", initial_sample=None, dtype=None, chunk_size=1024,
                 type_mapping=None):
        """
        Initializes the H5PyDictLogger.

        :param filename: HDF5 file name.
        :param dataset_name: Name of the dataset in the file.
        :param initial_sample: A sample dict (with nested keys allowed) used to infer the structure.
        :param dtype: Optional NumPy compound dtype; if None it will be inferred.
        :param chunk_size: Dataset chunk size.
        :param type_mapping: Mapping from Python types to NumPy dtypes.
        """
        # Set the type mapping for inferring field types from a flattened dict.
        if type_mapping is None:
            self.type_mapping = {
                float: np.float64,
                int: np.int32,
                str: h5py.string_dtype(encoding='utf-8'),
                bool: np.bool_,
            }
        else:
            self.type_mapping = type_mapping

        if dtype is None:
            if initial_sample is None:
                raise ValueError("initial_sample must be provided to infer dtype when dtype is None")
            # Create a cache for optimized flattening.
            _, self.cache = cache_dict_paths_for_flatten(initial_sample, sep='.')
            # Flatten the initial sample.
            flat_sample = optimized_flatten_dict(initial_sample, self.cache)
            # Infer the compound dtype from the flattened dict.
            compound_dtype, _ = self.create_dtype_and_record_from_flat_dict(flat_sample)
            dtype = compound_dtype

        self.filename = filename
        self.dataset_name = dataset_name
        self.dtype = dtype
        self.chunk_size = chunk_size
        self.file = None
        self.dataset = None
        self.lock = threading.Lock()  # Protects read/write operations.
        self.current_size = 0  # Number of samples currently in the dataset.

    def start(self, mode='w'):
        """
        Opens the HDF5 file. If the dataset exists, it is opened and its size recorded;
        otherwise, a new dataset is created with an initial shape of 0.
        """
        self.file = h5py.File(self.filename, mode)
        if self.dataset_name in self.file:
            self.dataset = self.file[self.dataset_name]
            self.current_size = self.dataset.shape[0]
        else:
            self.dataset = self.file.create_dataset(
                self.dataset_name,
                shape=(0,),
                maxshape=(None,),
                dtype=self.dtype,
                chunks=(self.chunk_size,)
            )
            self.current_size = 0

    def appendSample(self, sample):
        """
        Appends a sample to the dataset.

        If `sample` is a dict, it is first checked to see whether its keys match the
        expected flattened structure. If not, the sample is flattened using the optimized
        flatten function and then converted to a tuple record.
        """
        if isinstance(sample, dict):
            # Check if the sample is already flattened (keys match dtype names)
            if set(sample.keys()) != set(self.dtype.names):
                sample = optimized_flatten_dict(sample, self.cache)
            sample = self._dict_to_record(sample)
        with self.lock:
            new_size = self.current_size + 1
            # Resize the dataset to accommodate the new sample.
            self.dataset.resize((new_size,))
            self.dataset[self.current_size] = sample
            self.current_size = new_size
            self.file.flush()  # Ensure data is written to disk.

    def getSample(self, index):
        """
        Retrieves samples from the dataset.

        Accepts either an integer (for a single sample) or a slice (for a range of samples).
        Returns the raw NumPy data.
        """
        with self.lock:
            data = self.dataset[index]
        return data

    def close(self):
        """
        Closes the HDF5 file.
        """
        with self.lock:
            if self.file:
                self.file.close()
                self.file = None
                self.dataset = None

    # --- Helper functions for converting between flattened dicts and records --- #

    def _dict_to_record(self, flat_dict):
        """
        Converts a flattened dict into a record tuple that matches self.dtype.

        Assumes the keys in flat_dict match the field names in self.dtype. Raises
        a KeyError if a field is missing.
        """
        record = []
        for field in self.dtype.names:
            if field not in flat_dict:
                raise KeyError(f"Field '{field}' not found in provided dict.")
            value = flat_dict[field]
            # Optionally convert the value to the expected type.
            expected_dtype = self.dtype.fields[field][0]
            try:
                value = expected_dtype.type(value)
            except Exception as e:
                raise ValueError(f"Could not convert field '{field}' value {value} to type {expected_dtype}: {e}")
            record.append(value)
        return tuple(record)

    def create_dtype_and_record_from_flat_dict(self, flat_dict):
        """
        Given a flattened dict, infers a NumPy compound dtype using self.type_mapping and
        creates a record tuple.

        Returns a tuple (compound_dtype, record).
        """
        dtype_fields = []
        record_values = []
        for key, value in flat_dict.items():
            value_type = type(value)
            if value_type in self.type_mapping:
                np_type = self.type_mapping[value_type]
            else:
                # Fallback handling
                if isinstance(value, float):
                    np_type = np.float64
                elif isinstance(value, int):
                    np_type = np.int32
                elif isinstance(value, str):
                    np_type = h5py.string_dtype(encoding='utf-8')
                elif isinstance(value, bool):
                    np_type = np.bool_
                else:
                    raise ValueError(f"Unsupported type {value_type} for field '{key}'")
            dtype_fields.append((key, np_type))
            record_values.append(value)
        compound_dtype = np.dtype(dtype_fields)
        record = tuple(record_values)
        return compound_dtype, record

    def record_to_dict(self, record):
        """
        Converts a NumPy record (or a structured array element) back into the original
        nested dict. If record is an array of records, returns a list of dicts.
        """
        if isinstance(record, np.ndarray):
            dict_list = []
            for rec in record:
                flat_dict = {field: rec[field] for field in rec.dtype.names}
                original = unflatten_dict_baseline(flat_dict)
                dict_list.append(original)
            return dict_list
        else:
            flat_dict = {field: record[field] for field in record.dtype.names}
            return unflatten_dict_baseline(flat_dict)


# -----------------------------------------------------------------------------
# Example usage: writer and reader threads
# -----------------------------------------------------------------------------

def writer_thread(logger, n_samples=2000):
    """
    Simulates logging samples by appending new records.
    Each sample is a dict; the logger automatically converts it.
    """
    for i in range(n_samples):
        sample = {
            'timestamp': time.time(),
            'sensor_value': random.random(),
            'control_signal': i,
            'data': {
                'x': random.randint(0, 10),
                's': f"Sample {i}"
            }
        }
        logger.appendSample(sample)
        time.sleep(0.001)  # Simulate delay between samples.


def reader_thread(logger):
    """
    Periodically reads a slice of samples from the logger.

    Once there are more than 200 samples, it reads samples from index 100 to 200,
    converts them back to dicts, and prints them.
    """
    while True:
        with logger.lock:
            size = logger.current_size
        if size > 1000:
            timer = PerformanceTimer()
            samples = logger.getSample(slice(0, 1000))

            # Convert the flat records back into the original nested dicts.
            samples_as_dicts = logger.record_to_dict(samples)
            timer.stop()
            print("Read samples from index 100 to 200:")
            print(samples_as_dicts)
            break
        time.sleep(0.01)


# -----------------------------------------------------------------------------
# Main example demonstrating usage
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Define an initial sample dict (structure remains constant).
    sample_dict = {
        'timestamp': 5.2,
        'sensor_value': random.random(),
        'control_signal': 0,
        'data': {
            'x': 3,
            's': "Hello world!"
        }
    }

    # Create the logger using the initial sample to infer dtype.
    logger = H5PyDictLogger("samples.h5", initial_sample=sample_dict)
    logger.start(mode='w')
    print("Using dtype:")
    print(logger.dtype)

    # # Append an initial sample using a flattened dict.
    # sample_flat = optimized_flatten_dict(sample_dict, cache_dict_paths_for_flatten(sample_dict)[0])
    # logger.appendSample(sample_flat)

    # Start writer and reader threads to simulate logging and reading.
    t_writer = threading.Thread(target=writer_thread, args=(logger,))
    t_reader = threading.Thread(target=reader_thread, args=(logger,))

    t_writer.start()
    t_reader.start()

    t_writer.join()
    t_reader.join()
    logger.close()

    # -----------------------------------------------------------------------------
    # Explanation:
    # When appending a sample, the logger resizes the dataset and writes the new record
    # directly to the HDF5 file (using file.flush() to ensure the data is saved).
    # When reading samples, the data is read directly from the HDF5 file.
    # -----------------------------------------------------------------------------
