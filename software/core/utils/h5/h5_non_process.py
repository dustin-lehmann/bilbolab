import time
import dataclasses

import h5py
import numpy as np
import threading
import random

from h5py import vlen_dtype

from core.utils.dict_utils import cache_dict_paths_for_flatten, optimized_flatten_dict, unflatten_dict_baseline, \
    unflatten_dict_optimized
from core.utils.time import precise_sleep


# -----------------------------------------------------------------------------
# H5PyDictLogger implementation with nested signal support
# -----------------------------------------------------------------------------

class H5PyDictLogger:
    batch_size = 100

    # === INIT =========================================================================================================
    def __init__(self, filename, dataset_name="samples", chunk_size=10000,
                 type_mapping=None, compound_types: dict[str, tuple[type, np.dtype]] = None):
        """
        Initializes the H5PyDictLogger.

        :param filename: HDF5 file name.
        :param dataset_name: Name of the dataset in the file.
        :param type_mapping: Mapping from Python types to NumPy dtypes.
        :param compound_types: Mapping from flattened field paths to (dataclass_type, numpy_dtype).
            When a list field matches a registered path, it is stored as a variable-length
            array of the corresponding compound dtype. The dataclass type is used to
            convert instances to records; the dtype defines the HDF5 storage format.
            This also handles empty lists during initialization.

            Example:
                @dataclasses.dataclass
                class Waypoint:
                    x: float
                    y: float
                    type: int

                waypoint_dtype = np.dtype([('x', 'f8'), ('y', 'f8'), ('type', 'i4')])
                logger = H5PyDictLogger(
                    "log.h5",
                    compound_types={'position_control.waypoints': (Waypoint, waypoint_dtype)}
                )
        """
        if type_mapping is None:
            self.type_mapping = {float: np.float64,
                                 int: np.int32,
                                 str: h5py.string_dtype(encoding='utf-8'),
                                 bool: np.bool_,
                                 list: {
                                     int: vlen_dtype(np.int32),
                                     float: vlen_dtype(np.float64),
                                     str: vlen_dtype(h5py.string_dtype(encoding='utf-8'))
                                 }
                                 }
        else:
            self.type_mapping = type_mapping

        # compound_types: {field_path: (dataclass_type, numpy_dtype)}
        self.compound_types = compound_types or {}
        # Build reverse lookup: dataclass_type -> numpy_dtype (for runtime type checking)
        self._compound_type_to_dtype = {
            cls: dtype for cls, dtype in (v for v in self.compound_types.values())
        }

        self.filename = filename
        self.dataset_name = dataset_name
        self.dtype = None
        self.chunk_size = chunk_size
        self.file = None
        self.dataset = None
        self.lock = threading.Lock()  # Protects read/write operations.
        self.current_size = 0  # Number of samples currently in the dataset.

        self._dict_flatten_cache = None
        self._unflatten_cache = None
        self._field_paths = None

    # === METHODS ======================================================================================================
    def init(self, initial_sample: dict):
        # Create a cache for optimized flattening.
        _, self._dict_flatten_cache = cache_dict_paths_for_flatten(initial_sample, sep='.')
        # Flatten the initial sample.
        flat_sample = optimized_flatten_dict(initial_sample, self._dict_flatten_cache)
        # Infer the compound dtype from the flattened dict.
        compound_dtype, _ = self.create_dtype_and_record_from_flat_dict(flat_sample)
        self.dtype = compound_dtype

        self._field_paths = {name: name.split('.') for name in self.dtype.names}

    # ------------------------------------------------------------------------------------------------------------------
    def start(self, mode='w'):
        """
        Opens the HDF5 file. If the dataset exists, it is opened and its size recorded;
        otherwise, a new dataset is created with an initial shape of 0.
        """
        self.file = h5py.File(self.filename, mode, locking=False)
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

    # ------------------------------------------------------------------------------------------------------------------
    def append_sample(self, sample):
        """
        Appends a single sample to the dataset.

        If sample is a dict, it is first checked to see whether its keys match the
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

    # ------------------------------------------------------------------------------------------------------------------
    def append_multiple_samples(self, samples: list):
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

        # Convert the list of records to a NumPy structured array
        records_array = np.array(records, dtype=self.dtype)
        with self.lock:
            new_size = self.current_size + len(records_array)
            if self.dataset is not None:
                self.dataset.resize((new_size,))
                self.dataset[self.current_size:new_size] = records_array
                self.current_size = new_size
                self.file.flush()  # Ensure data is written to disk.

    # ------------------------------------------------------------------------------------------------------------------
    def get_samples(self, index, signals=None, to_dict: bool = False):
        """
        Unified sample retrieval.

        Parameters
        ----------
        index : int | slice | Sequence[int]
            - int      → single sample
            - slice    → range of samples
            - sequence → explicit indices
        signals : list[str] | None
            - None → full record(s)
            - list of signals / prefixes
        to_dict : bool
            - Only used when signals is None.
            - If True, convert to nested dict(s) via record_to_dict in batches.
        """

        if self.dataset is None:
            raise RuntimeError("Dataset is not open. Call start() first.")

        # ----------------------------
        # Helper to normalize indices
        # ----------------------------
        def _indices_from_slice(s: slice):
            start = s.start if s.start is not None else 0
            stop = s.stop if s.stop is not None else len(self.dataset)
            step = s.step if s.step is not None else 1
            return list(range(start, stop, step))

        # Keep track of the original index type for return-shape semantics
        is_int_index = isinstance(index, int)
        is_slice_index = isinstance(index, slice)

        # -------------------------------------
        # Case 1: integer index (no batching)
        # -------------------------------------
        if is_int_index:
            idx = index

            # signals branch: same semantics as before (single sample)
            if signals is not None:
                dtype_fields = self.dtype.names
                mapping: dict[str, list[str]] = {}
                actual_fields = set()

                for s in signals:
                    if s in dtype_fields:
                        mapping[s] = [s]
                        actual_fields.add(s)
                    else:
                        matched = [field for field in dtype_fields if field.startswith(s + '.')]
                        mapping[s] = matched
                        actual_fields.update(matched)

                field_list = list(actual_fields) if actual_fields else None

                with self.lock:
                    if field_list is None:
                        rec = self.dataset[idx]
                    else:
                        rec = self.dataset[idx][field_list]

                # Single sample: build signal -> value / nested dict
                result = {}
                for s in signals:
                    fields_for_s = mapping[s]
                    if len(fields_for_s) == 1 and fields_for_s[0] == s:
                        # direct field
                        result[s] = rec[s]
                    else:
                        # prefix → nested dict
                        subdict = {
                            field[len(s) + 1:]: rec[field]
                            for field in fields_for_s
                        }
                        result[s] = unflatten_dict_baseline(subdict)
                return result

            # signals is None → full record
            with self.lock:
                rec = self.dataset[idx]

            if to_dict:
                # record_to_dict returns a single nested dict for np.void
                return self.record_to_dict(rec)
            else:
                # Structured np.void
                return rec

        # -------------------------------------
        # Case 2: slice or sequence of indices
        # -------------------------------------
        if is_slice_index:
            indices = _indices_from_slice(index)
        else:
            # assume iterable of ints
            indices = list(index)

        total = len(indices)
        if total == 0:
            # Empty result
            if signals is None:
                return [] if to_dict else np.array([], dtype=self.dtype)
            else:
                return {s: [] for s in signals}

        use_batches = total >= self.batch_size

        # ============================================================
        # signals is None → full records (raw or nested dicts)
        # ============================================================
        if signals is None:
            # --------- Small read, no batching ----------
            if not use_batches:
                if is_slice_index:
                    with self.lock:
                        data = self.dataset[index]
                else:
                    with self.lock:
                        data = self.dataset[indices]

                if to_dict:
                    # record_to_dict will:
                    #   - slice/array → list of nested dicts
                    #   - but this branch is multi-index → always list
                    return self.record_to_dict(data)
                else:
                    return data

            # --------- Large read, batched ----------
            if not to_dict:
                # Raw structured array, but read in chunks
                batches = []
                for i in range(0, total, self.batch_size):
                    batch_indices = indices[i:i + self.batch_size]
                    with self.lock:
                        batch_data = self.dataset[batch_indices]
                    batches.append(batch_data)
                    # Give other threads time to run between batches
                    time.sleep(0.01)
                if len(batches) == 1:
                    return batches[0]
                return np.concatenate(batches)

            else:
                # to_dict=True: convert each batch separately to nested dicts
                all_dicts = []
                for i in range(0, total, self.batch_size):
                    batch_indices = indices[i:i + self.batch_size]
                    with self.lock:
                        batch_data = self.dataset[batch_indices]
                    # Outside the lock: heavy Python conversion
                    batch_dicts = self.record_to_dict(batch_data)
                    # Give other threads time to run between batches
                    time.sleep(0.01)
                    # record_to_dict on an array returns a list
                    all_dicts.extend(batch_dicts)
                return all_dicts

        # ============================================================
        # signals is not None → dict[signal] = list[values or subdict]
        # ============================================================
        dtype_fields = self.dtype.names
        mapping: dict[str, list[str]] = {}
        actual_fields = set()

        for s in signals:
            if s in dtype_fields:
                mapping[s] = [s]
                actual_fields.add(s)
            else:
                matched = [field for field in dtype_fields if field.startswith(s + '.')]
                mapping[s] = matched
                actual_fields.update(matched)

        field_list = list(actual_fields) if actual_fields else None

        # ---------- Helper to process a batch of records ----------
        def _accumulate_from_batch(batch_data, result_dict):
            # Ensure iterable of records
            if getattr(batch_data, "shape", ()) == ():
                # scalar → wrap into array for uniform handling
                batch_data = np.array([batch_data], dtype=batch_data.dtype)

            for rec in batch_data:
                for s in signals:
                    fields_for_s = mapping[s]
                    if len(fields_for_s) == 1 and fields_for_s[0] == s:
                        result_dict[s].append(rec[s])
                    else:
                        subdict = {
                            field[len(s) + 1:]: rec[field]
                            for field in fields_for_s
                        }
                        result_dict[s].append(unflatten_dict_baseline(subdict))

        # ---------- Non-batched vs batched ----------
        result = {s: [] for s in signals}

        if not use_batches:
            if is_slice_index:
                with self.lock:
                    if field_list is None:
                        batch_data = self.dataset[index]
                    else:
                        batch_data = self.dataset[index][field_list]
            else:
                with self.lock:
                    if field_list is None:
                        batch_data = self.dataset[indices]
                    else:
                        batch_data = self.dataset[indices][field_list]

            _accumulate_from_batch(batch_data, result)
            return result

        else:
            # Batched reads
            for i in range(0, total, self.batch_size):
                batch_indices = indices[i:i + self.batch_size]
                with self.lock:
                    if field_list is None:
                        batch_data = self.dataset[batch_indices]
                    else:
                        batch_data = self.dataset[batch_indices][field_list]
                _accumulate_from_batch(batch_data, result)
                # Give other threads time to run between batches
                time.sleep(0.003)
            return result

    # ------------------------------------------------------------------------------------------------------------------

    # def get_samples(self, index, signals=None, to_dict: bool = False):
    #     """
    #     Unified sample retrieval.
    #
    #     Parameters
    #     ----------
    #     index : int | slice | Sequence[int]
    #         - int      → single sample
    #         - slice    → range of samples
    #         - sequence → explicit indices
    #     signals : list[str] | None
    #         - None → full record(s)
    #         - list of signals / prefixes
    #     to_dict : bool
    #         - Only used when signals is None.
    #         - If True, convert to nested dict(s) via record_to_dict in batches.
    #
    #     Behavior for missing signals/prefixes
    #     ------------------------------------
    #     - If a requested signal is not found:
    #         * exact-field signal → returns None
    #         * prefix signal      → returns {}
    #       A warning is emitted once per call listing missing requests.
    #     """
    #     import warnings
    #
    #     if self.dataset is None:
    #         raise RuntimeError("Dataset is not open. Call start() first.")
    #
    #     # ----------------------------
    #     # Helper to normalize indices
    #     # ----------------------------
    #     def _indices_from_slice(s: slice):
    #         start = s.start if s.start is not None else 0
    #         stop = s.stop if s.stop is not None else len(self.dataset)
    #         step = s.step if s.step is not None else 1
    #         return list(range(start, stop, step))
    #
    #     # -------------------------------------
    #     # Helper: build mapping + warn once
    #     # -------------------------------------
    #     def _build_signal_mapping(req_signals: list[str]):
    #         """
    #         Returns:
    #             mapping: dict[str, list[str]]   # each requested signal -> list of actual fields
    #             actual_fields: set[str]         # union of all matched fields
    #             missing: list[tuple[str, str]]  # list of (signal, kind) where kind in {"field","prefix"}
    #         """
    #         dtype_fields = self.dtype.names
    #         mapping: dict[str, list[str]] = {}
    #         actual_fields: set[str] = set()
    #         missing: list[tuple[str, str]] = []
    #
    #         for s in req_signals:
    #             if s in dtype_fields:
    #                 mapping[s] = [s]
    #                 actual_fields.add(s)
    #                 continue
    #
    #             matched = [field for field in dtype_fields if field.startswith(s + ".")]
    #             mapping[s] = matched
    #             actual_fields.update(matched)
    #
    #             if not matched:
    #                 # Determine whether the user likely intended an exact field or a prefix:
    #                 # - if it contains a dot, user probably meant a prefix
    #                 # - otherwise ambiguous, but treat as "field" intent (most common)
    #                 kind = "prefix" if "." in s else "field"
    #                 missing.append((s, kind))
    #
    #         if missing:
    #             missing_names = [m[0] for m in missing]
    #             warnings.warn(
    #                 f"Requested signal(s)/prefix(es) not found in dataset: {missing_names}",
    #                 category=UserWarning,
    #                 stacklevel=2,
    #             )
    #
    #         return mapping, actual_fields, missing
    #
    #     # -------------------------------------
    #     # Case 1: integer index (no batching)
    #     # -------------------------------------
    #     is_int_index = isinstance(index, int)
    #     is_slice_index = isinstance(index, slice)
    #
    #     if is_int_index:
    #         idx = index
    #
    #         # signals branch: return dict per requested signal
    #         if signals is not None:
    #             mapping, actual_fields, missing = _build_signal_mapping(signals)
    #
    #             # If nothing matched, avoid reading full record
    #             if not actual_fields:
    #                 out = {}
    #                 for s in signals:
    #                     # If it was an exact field intent → None; prefix intent → {}
    #                     kind = "prefix" if "." in s else "field"
    #                     out[s] = {} if kind == "prefix" else None
    #                 return out
    #
    #             field_list = list(actual_fields)
    #
    #             with self.lock:
    #                 rec = self.dataset[idx][field_list]
    #
    #             result = {}
    #             for s in signals:
    #                 fields_for_s = mapping[s]
    #
    #                 # Missing
    #                 if not fields_for_s:
    #                     kind = "prefix" if "." in s else "field"
    #                     result[s] = {} if kind == "prefix" else None
    #                     continue
    #
    #                 # Direct field
    #                 if len(fields_for_s) == 1 and fields_for_s[0] == s:
    #                     result[s] = rec[s]
    #                     continue
    #
    #                 # Prefix → nested dict
    #                 subdict = {field[len(s) + 1:]: rec[field] for field in fields_for_s}
    #                 result[s] = unflatten_dict_baseline(subdict)
    #
    #             return result
    #
    #         # signals is None → full record
    #         with self.lock:
    #             rec = self.dataset[idx]
    #
    #         if to_dict:
    #             return self.record_to_dict(rec)
    #         return rec
    #
    #     # -------------------------------------
    #     # Case 2: slice or sequence of indices
    #     # -------------------------------------
    #     if is_slice_index:
    #         indices = _indices_from_slice(index)
    #     else:
    #         indices = list(index)
    #
    #     total = len(indices)
    #     if total == 0:
    #         if signals is None:
    #             return [] if to_dict else np.array([], dtype=self.dtype)
    #         return {s: [] for s in signals}
    #
    #     use_batches = total >= self.batch_size
    #
    #     # ============================================================
    #     # signals is None → full records (raw or nested dicts)
    #     # ============================================================
    #     if signals is None:
    #         # --------- Small read, no batching ----------
    #         if not use_batches:
    #             with self.lock:
    #                 data = self.dataset[index] if is_slice_index else self.dataset[indices]
    #             return self.record_to_dict(data) if to_dict else data
    #
    #         # --------- Large read, batched ----------
    #         if not to_dict:
    #             batches = []
    #             for i in range(0, total, self.batch_size):
    #                 batch_indices = indices[i:i + self.batch_size]
    #                 with self.lock:
    #                     batch_data = self.dataset[batch_indices]
    #                 batches.append(batch_data)
    #             return batches[0] if len(batches) == 1 else np.concatenate(batches)
    #
    #         # to_dict=True: convert each batch separately to nested dicts
    #         all_dicts = []
    #         for i in range(0, total, self.batch_size):
    #             batch_indices = indices[i:i + self.batch_size]
    #             with self.lock:
    #                 batch_data = self.dataset[batch_indices]
    #             batch_dicts = self.record_to_dict(batch_data)
    #             time.sleep(0.003)
    #             all_dicts.extend(batch_dicts)
    #         return all_dicts
    #
    #     # ============================================================
    #     # signals is not None → dict[signal] = list[values or subdict]
    #     # ============================================================
    #     mapping, actual_fields, _missing = _build_signal_mapping(signals)
    #
    #     # If nothing matched, avoid reading full records
    #     if not actual_fields:
    #         out = {}
    #         for s in signals:
    #             kind = "prefix" if "." in s else "field"
    #             fill = {} if kind == "prefix" else None
    #             out[s] = [fill] * total
    #         return out
    #
    #     field_list = list(actual_fields)
    #
    #     def _accumulate_from_batch(batch_data, result_dict):
    #         # Ensure iterable of records
    #         if getattr(batch_data, "shape", ()) == ():
    #             batch_data = np.array([batch_data], dtype=batch_data.dtype)
    #
    #         for rec in batch_data:
    #             for s in signals:
    #                 fields_for_s = mapping[s]
    #
    #                 # Missing
    #                 if not fields_for_s:
    #                     kind = "prefix" if "." in s else "field"
    #                     result_dict[s].append({} if kind == "prefix" else None)
    #                     continue
    #
    #                 # Direct
    #                 if len(fields_for_s) == 1 and fields_for_s[0] == s:
    #                     result_dict[s].append(rec[s])
    #                     continue
    #
    #                 # Prefix → nested dict
    #                 subdict = {field[len(s) + 1:]: rec[field] for field in fields_for_s}
    #                 result_dict[s].append(unflatten_dict_baseline(subdict))
    #
    #     result = {s: [] for s in signals}
    #
    #     # ---------- Non-batched ----------
    #     if not use_batches:
    #         with self.lock:
    #             if is_slice_index:
    #                 batch_data = self.dataset[index][field_list]
    #             else:
    #                 batch_data = self.dataset[indices][field_list]
    #         _accumulate_from_batch(batch_data, result)
    #         return result
    #
    #     # ---------- Batched ----------
    #     for i in range(0, total, self.batch_size):
    #         batch_indices = indices[i:i + self.batch_size]
    #         with self.lock:
    #             batch_data = self.dataset[batch_indices][field_list]
    #         _accumulate_from_batch(batch_data, result)
    #
    #     return result

    def close(self):
        """
        Closes the HDF5 file.
        """
        with self.lock:
            if self.file:
                self.file.close()
                self.file = None
                self.dataset = None

    # === PRIVATE METHODS ==============================================================================================

    def _dict_to_record(self, flat_dict):
        """
        Converts a flattened dict into a record tuple that matches self.dtype.

        Supports lists of int/float/str for fields whose dtype is a vlen type.
        Supports lists of dataclass instances for compound vlen types.
        """
        record = []

        for field in self.dtype.names:
            if field not in flat_dict:
                raise KeyError(f"Field '{field}' not found in provided dict.")

            value = flat_dict[field]
            field_dtype = self.dtype.fields[field][0]

            # --- LIST SUPPORT -----------------------------------------------------
            # Detect vlen dtype: h5py stores base dtype in metadata['vlen']
            vlen_base = None
            if getattr(field_dtype, "metadata", None) is not None:
                vlen_base = field_dtype.metadata.get("vlen")

            if isinstance(value, list) and vlen_base is not None:
                # Check if it's a compound dtype (has 'names' attribute)
                if hasattr(vlen_base, 'names') and vlen_base.names is not None:
                    # Compound vlen: convert dataclass instances to structured array
                    arr = self._dataclass_list_to_array(value, vlen_base)
                else:
                    # Simple vlen: convert Python list to ndarray
                    arr = np.asarray(value, dtype=vlen_base)
                record.append(arr)
                continue
            # ----------------------------------------------------------------------

            # Normal scalar handling
            try:
                # For plain numpy dtypes this is fine; for h5py string dtypes, this
                # usually just passes the value through.
                value = field_dtype.type(value)
            except Exception:
                # Fallback: just keep the original value
                pass

            record.append(value)

        return tuple(record)

    def _get_compound_dtype_for_type(self, element_type: type) -> np.dtype | None:
        """Get the compound dtype for a dataclass type, if registered."""
        return self._compound_type_to_dtype.get(element_type)

    def create_dtype_and_record_from_flat_dict(self, flat_dict):
        """
        Given a flattened dict, infers a NumPy compound dtype using self.type_mapping and
        creates a record tuple.

        Supports lists of int/float/str as HDF5 vlen arrays.
        Supports lists of registered dataclass instances as compound vlen arrays.
        """
        dtype_fields = []
        record_values = []

        for key, value in flat_dict.items():
            # --- LIST SUPPORT -----------------------------------------------------
            if isinstance(value, list):
                # Check if this field path is registered as a compound type
                if key in self.compound_types:
                    dataclass_type, compound_dtype = self.compound_types[key]
                    field_dtype = vlen_dtype(compound_dtype)
                    arr = self._dataclass_list_to_array(value, compound_dtype)
                    dtype_fields.append((key, field_dtype))
                    record_values.append(arr)
                    continue

                # For non-registered lists, we need at least one element to infer type
                if len(value) == 0:
                    raise ValueError(
                        f"Cannot infer element type for empty list field '{key}'. "
                        f"Either register it as a compound_type or use a non-empty default list."
                    )

                element_type = type(value[0])

                # Check if element type is a registered compound type (by type, not path)
                if element_type in self._compound_type_to_dtype:
                    compound_dtype = self._compound_type_to_dtype[element_type]
                    field_dtype = vlen_dtype(compound_dtype)
                    arr = self._dataclass_list_to_array(value, compound_dtype)
                    dtype_fields.append((key, field_dtype))
                    record_values.append(arr)
                    continue

                # Optionally: sanity check all elements are same type
                # if not all(isinstance(v, element_type) for v in value):
                #     raise ValueError(f"Mixed element types in list for field '{key}'.")

                if element_type is int:
                    base_dtype = np.int32
                elif element_type is float:
                    base_dtype = np.float64
                elif element_type is str:
                    base_dtype = h5py.string_dtype('utf-8')
                else:
                    raise ValueError(
                        f"Unsupported list element type {element_type} in field '{key}'. "
                        f"Only list[int], list[float], list[str], or registered compound types are supported."
                    )

                field_dtype = vlen_dtype(base_dtype)
                arr = np.asarray(value, dtype=base_dtype)

                dtype_fields.append((key, field_dtype))
                record_values.append(arr)
                continue
            # ---------------------------------------------------------------------

            # Non-list leaf types
            value_type = type(value)
            if value_type in self.type_mapping:
                np_type = self.type_mapping[value_type]
            else:
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

    def _dataclass_list_to_array(self, items: list, compound_dtype: np.dtype) -> np.ndarray:
        """
        Convert a list of dataclass instances to a numpy structured array.

        Each dataclass field is converted to the corresponding dtype field.
        IntEnum values are automatically converted to their integer value.
        """
        if len(items) == 0:
            return np.array([], dtype=compound_dtype)

        records = []
        for item in items:
            record = []
            for field_name in compound_dtype.names:
                val = getattr(item, field_name)
                # Handle IntEnum: convert to int value
                if hasattr(val, 'value') and isinstance(val.value, int):
                    val = val.value
                record.append(val)
            records.append(tuple(record))

        return np.array(records, dtype=compound_dtype)

    def record_to_dict(self, record_or_array):
        """
        Convert a structured np.void or np.ndarray of records into nested dict(s)
        without creating an intermediate flat dict.
        """

        def convert_value(val):
            # If it's an ndarray, check if it's a compound array (structured)
            if isinstance(val, np.ndarray):
                # Check if this is a structured array (compound type)
                if val.dtype.names is not None:
                    # Convert each element of the compound array to a dict
                    return [self._compound_record_to_dict(item) for item in val]
                # Regular array (e.g. vlen strings/ints/floats)
                return [convert_value(x) for x in val]

            # Single compound record (np.void with named fields)
            if isinstance(val, np.void) and val.dtype.names is not None:
                return self._compound_record_to_dict(val)

            # NumPy scalar → Python scalar
            if isinstance(val, np.generic):
                val = val.item()

            # HDF5 string comes out as bytes → decode
            if isinstance(val, bytes):
                return val.decode("utf-8")

            # Already a normal Python type (str/int/float/bool/None/etc.)
            return val

        def build_single(rec):
            nested = {}
            for field, path in self._field_paths.items():
                v = convert_value(rec[field])
                d = nested
                # walk the path except the last key
                for key in path[:-1]:
                    child = d.get(key)
                    if child is None:
                        child = {}
                        d[key] = child
                    d = child
                d[path[-1]] = v
            return nested

        # Single record
        if isinstance(record_or_array, np.void) or getattr(record_or_array, "shape", ()) == ():
            return build_single(record_or_array)

        # Array of records
        out = []
        for rec in record_or_array:
            out.append(build_single(rec))
        return out

    def _compound_record_to_dict(self, record: np.void) -> dict:
        """
        Convert a single compound record (np.void with named fields) to a dict.
        """
        result = {}
        for field_name in record.dtype.names:
            val = record[field_name]
            # NumPy scalar → Python scalar
            if isinstance(val, np.generic):
                val = val.item()
            # HDF5 string comes out as bytes → decode
            if isinstance(val, bytes):
                val = val.decode("utf-8")
            result[field_name] = val
        return result


# ======================================================================================================================
def example_1():
    ...


# ======================================================================================================================
if __name__ == "__main__":
    # Define an initial sample dict (structure remains constant).
    sample_dict = {
        'timestamp': 1,
        'sensor_value': random.random(),
        'control_signal': 0,
        'data': {
            'x': 3,
            's': "Hello world!"
        },
        'nested': {
            'subdict1': {
                'subdict2': {
                    'a': 2,
                    'b': 3
                },
                'c': 4
            }
        }
    }

    # Create the logger using the initial sample to infer dtype.
    logger = H5PyDictLogger("samples.h5")
    logger.init(sample_dict)
    logger.start(mode='w')

    # Append a couple of samples one by one.
    logger.append_sample(sample_dict)
    sample_dict['timestamp'] = 2
    logger.append_sample(sample_dict)

    # Now create a list of samples and append them in one batch.
    batch_samples = []
    for ts in range(3, 8000):
        sample = {
            'timestamp': ts,
            'sensor_value': random.random(),
            'control_signal': 1,
            'data': {
                'x': ts * 10,
                's': f"Batch sample {ts}"
            },
            'nested': {
                'subdict1': {
                    'subdict2': {
                        'a': ts,
                        'b': ts + 1
                    },
                    'c': ts + 2
                }
            }
        }
        batch_samples.append(sample)

    logger.append_multiple_samples(batch_samples)

    # Demonstrate retrieval of a nested dict using a prefix.
    print("Testing getSample with nested signal extraction:")
    sample0 = logger.get_samples(0, signals=['nested.subdict1.subdict2'])
    print("Sample 0 - nested.subdict1.subdict2:", sample0)

    for _ in range(10):
        time0 = time.perf_counter()
        x1 = logger.get_samples(slice(0, 5000), signals=None, to_dict=True)
        print(f"Took {((time.perf_counter() - time0) * 1000):.2f} ms to read 1000 samples.")

    # print("Batch nested.subdict1.subdict2:", batch_nested)

    # logger.close()
