import h5py
import numpy as np
import threading
import time
import random

from utils.dict_utils import cache_dict_paths_for_flatten, optimized_flatten_dict, unflatten_dict_baseline
from utils.time import PerformanceTimer


# -----------------------------------------------------------------------------
# H5PyDictLogger implementation
# -----------------------------------------------------------------------------

class H5PyDictLogger:
    def __init__(self, filename, dataset_name="samples", chunk_size=10000,
                 type_mapping=None):
        """
        Initializes the H5PyDictLogger.

        :param filename: HDF5 file name.
        :param dataset_name: Name of the dataset in the file.
        :param type_mapping: Mapping from Python types to NumPy dtypes.
        """
        if type_mapping is None:
            self.type_mapping = {
                float: np.float64,
                int: np.int32,
                str: h5py.string_dtype(encoding='utf-8'),
                bool: np.bool_,
            }
        else:
            self.type_mapping = type_mapping

        self.filename = filename
        self.dataset_name = dataset_name
        self.dtype = None
        self.chunk_size = chunk_size
        self.file = None
        self.dataset = None
        self.lock = threading.Lock()  # Protects read/write operations.
        self.current_size = 0  # Number of samples currently in the dataset.
        self._dict_flatten_cache = None

    def init(self, initial_sample: dict):
        # Create a cache for optimized flattening.
        _, self._dict_flatten_cache = cache_dict_paths_for_flatten(initial_sample, sep='.')
        # Flatten the initial sample.
        flat_sample = optimized_flatten_dict(initial_sample, self._dict_flatten_cache)
        # Infer the compound dtype from the flattened dict.
        compound_dtype, _ = self.create_dtype_and_record_from_flat_dict(flat_sample)
        self.dtype = compound_dtype

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
        Appends a single sample to the dataset.

        If `sample` is a dict, it is first checked to see whether its keys match the
        expected flattened structure. If not, the sample is flattened using the optimized
        flatten function and then converted to a tuple record.
        """
        if self.dtype is None:
            return

        if isinstance(sample, dict):
            # Check if the sample is already flattened (keys match dtype names)
            if set(sample.keys()) != set(self.dtype.names):
                sample = optimized_flatten_dict(sample, self._dict_flatten_cache)
            sample = self._dict_to_record(sample)
        with self.lock:
            new_size = self.current_size + 1
            self.dataset.resize((new_size,))
            self.dataset[self.current_size] = sample
            self.current_size = new_size
            self.file.flush()  # Ensure data is written to disk.

    def appendSamples(self, samples: list):
        """
        Appends a list of samples to the dataset in a batch operation.

        Each sample is first converted to a flattened dict (if needed) and then to a record.
        The dataset is resized once to accommodate all new samples, and they are written
        in a single operation, followed by one flush.
        """
        if self.dtype is None:
            return

        records = []
        for sample in samples:
            if isinstance(sample, dict):
                # Flatten the dict if needed
                if set(sample.keys()) != set(self.dtype.names):
                    sample = optimized_flatten_dict(sample, self._dict_flatten_cache)
                record = self._dict_to_record(sample)
                records.append(record)
            else:
                raise ValueError("Each sample must be a dictionary.")

        # Convert list of records to a NumPy structured array
        records_array = np.array(records, dtype=self.dtype)
        with self.lock:
            new_size = self.current_size + len(records_array)
            self.dataset.resize((new_size,))
            self.dataset[self.current_size:new_size] = records_array
            self.current_size = new_size
            self.file.flush()  # Ensure data is written to disk.

    def getSample(self, index, signal=None):
        """
        Retrieves samples from the dataset.

        Accepts either an integer (for a single sample) or a slice (for a range of samples).
        If 'signal' is provided as a list of field names, returns a dictionary with each key
        mapping to a list of values for that field.
        """
        with self.lock:
            if signal is not None:
                data = self.dataset[index][signal]  # Only read selected fields
            else:
                data = self.dataset[index]

        # Convert the structured array to a dict if signals are provided.
        if signal is not None:
            # Handle single sample vs multiple samples.
            if isinstance(data, np.void) or (hasattr(data, "dtype") and data.shape == ()):
                return {key: data[key] for key in data.dtype.names}
            else:
                return {key: data[key].tolist() for key in data.dtype.names}

        return data

    def getSampleBatch(self, index, signal=None, batch_size=2000):
        """
        Retrieves samples from the dataset in batches when using a slice.

        Accepts either:
          - an integer (for a single sample) or
          - a slice (for a range of samples).

        If 'signal' is provided as a list of field names, returns a dictionary where each key
        maps to a list of values for that field.

        For slices, the function processes the sample indices in batches of 'batch_size' at a time,
        holding the lock only during each batch retrieval. This avoids holding the lock for too long,
        which helps if your logging (or other operations) needs to run concurrently.
        """
        # Case 1: Single sample access.
        if isinstance(index, int):
            with self.lock:
                if signal is not None:
                    data = self.dataset[index][signal]
                else:
                    data = self.dataset[index]
            if signal is not None:
                if isinstance(data, np.void) or (hasattr(data, "dtype") and data.shape == ()):
                    return {key: data[key] for key in data.dtype.names}
                else:
                    return {key: data[key].tolist() for key in data.dtype.names}
            return data

        # Case 2: Slice access – process indices in batches.
        start = index.start if index.start is not None else 0
        stop = index.stop if index.stop is not None else len(self.dataset)
        step = index.step if index.step is not None else 1
        indices = list(range(start, stop, step))
        total_samples = len(indices)

        if signal is None:
            batches = []
            for i in range(0, total_samples, batch_size):
                batch_indices = indices[i:i + batch_size]
                with self.lock:
                    batch_data = self.dataset[batch_indices]
                batches.append(batch_data)
            return np.concatenate(batches)
        else:
            # Initialize the result dict for each field in signal.
            result = {field: [] for field in signal}
            for i in range(0, total_samples, batch_size):
                batch_indices = indices[i:i + batch_size]
                with self.lock:
                    # Retrieve only the specified fields.
                    batch_data = self.dataset[batch_indices][signal]
                # Ensure batch_data is always an array.
                if batch_data.shape == ():
                    batch_data = np.array([batch_data], dtype=batch_data.dtype)
                for field in signal:
                    # Extend the list with values from this batch.
                    result[field].extend(batch_data[field].tolist())
            return result


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

        Each field value is converted to its corresponding standard Python type.
        """

        def convert_value(val):
            if isinstance(val, np.generic):
                val = val.item()
            if isinstance(val, bytes):
                val = val.decode('utf-8')
            return val

        if isinstance(record, np.ndarray):
            dict_list = []
            for rec in record:
                flat_dict = {field: convert_value(rec[field]) for field in rec.dtype.names}
                original = unflatten_dict_baseline(flat_dict)
                dict_list.append(original)
            return dict_list
        else:
            flat_dict = {field: convert_value(record[field]) for field in record.dtype.names}
            return unflatten_dict_baseline(flat_dict)


# -----------------------------------------------------------------------------
# Main example demonstrating usage
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Define an initial sample dict (structure remains constant).
    sample_dict = {
        'timestamp': 1,
        'sensor_value': random.random(),
        'control_signal': 0,
        'data': {
            'x': 3,
            's': "Hello world!"
        }
    }

    # Create the logger using the initial sample to infer dtype.
    logger = H5PyDictLogger("samples.h5")
    logger.init(sample_dict)
    logger.start(mode='w')

    # Append a couple of samples one by one.
    logger.appendSample(sample_dict)
    sample_dict['timestamp'] = 2
    logger.appendSample(sample_dict)

    # Now create a list of samples and append them in one batch.
    batch_samples = []
    for ts in range(3, 8):
        sample = {
            'timestamp': ts,
            'sensor_value': random.random(),
            'control_signal': 1,
            'data': {
                'x': ts * 10,
                's': f"Batch sample {ts}"
            }
        }
        batch_samples.append(sample)

    logger.appendSamples(batch_samples)

    # Use PerformanceTimer to measure read times.
    timer = PerformanceTimer(print_output=True)
    sample_read_0 = logger.getSample(0)
    sample_read_1 = logger.getSample(1)
    timer.stop()

    print(f"Sample 0: {sample_read_0}")
    print(f"Sample 1: {sample_read_1}")

    logger.close()
