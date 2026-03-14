import gc
import queue
import threading
import time
from concurrent.futures import ProcessPoolExecutor, Future
from copy import copy, deepcopy
from typing import Callable

import numpy as np

from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.dataclass_utils import asdict_optimized, from_dict_auto
from core.utils.dict_utils import optimized_deepcopy, copy_dict
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.h5 import H5PyDictLogger
from core.utils.logging_utils import Logger
from core.utils.time import TimeoutTimer
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control
from robot.core import get_main_provider, set_logging_provider, LoggingProvider
from robot.drive.bilbo_drive import BILBO_Drive
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment.experiment_handler import BILBO_ExperimentHandler
from robot.logging.bilbo_sample import BILBO_Sample
from robot.lowlevel.stm32_general import BILBO_CONTROL_DT
from robot.lowlevel.stm32_sample import BILBO_LL_Sample
from robot.sensors.bilbo_sensors import BILBO_Sensors
import dataclasses
import h5py
from core.utils.json_utils import writeJSON

# === GLOBAL SETTINGS ==================================================================================================
SAMPLE_TIMEOUT_TIME = 0.5


# === MULTIPROCESSING WORKER ===========================================================================================
def _get_data_worker(hl_filename: str,
                     ll_filename: str,
                     sample_indexes,
                     signals: list[str] | None,
                     add_intermediate_samples: bool,
                     ll_start: int | None,
                     ll_end: int | None,
                     control_dt: float) -> dict | list | None:
    """
    Worker function that runs in a separate process to read data from H5 files.
    This avoids GIL contention with the main control loop.
    """
    import h5py
    from core.utils.h5 import H5PyDictLogger
    # Create fresh H5 loggers in this process
    hl_logger = H5PyDictLogger(
        filename=hl_filename,
    )
    ll_logger = H5PyDictLogger(filename=ll_filename)

    try:
        # Initialize and open for reading
        hl_file = h5py.File(hl_filename, 'r', locking=False)
        ll_file = h5py.File(ll_filename, 'r', locking=False)

        hl_logger.file = hl_file
        hl_logger.dataset = hl_file['samples']
        hl_logger.current_size = hl_logger.dataset.shape[0]
        hl_logger.dtype = hl_logger.dataset.dtype
        hl_logger._field_paths = {name: name.split('.') for name in hl_logger.dtype.names}

        ll_logger.file = ll_file
        ll_logger.dataset = ll_file['samples']
        ll_logger.current_size = ll_logger.dataset.shape[0]
        ll_logger.dtype = ll_logger.dataset.dtype
        ll_logger._field_paths = {name: name.split('.') for name in ll_logger.dtype.names}

        # Clamp indices to what's actually available in the file
        hl_size = hl_logger.current_size
        ll_size = ll_logger.current_size

        if hl_size == 0:
            return [] if add_intermediate_samples else None

        # Adjust sample_indexes to be within bounds
        if isinstance(sample_indexes, int):
            if sample_indexes >= hl_size:
                return None
            clamped_hl_indexes = sample_indexes
        elif isinstance(sample_indexes, slice):
            start = sample_indexes.start or 0
            stop = sample_indexes.stop if sample_indexes.stop is not None else hl_size
            stop = min(stop, hl_size)  # Clamp to available data
            if start >= stop:
                return [] if add_intermediate_samples else None
            clamped_hl_indexes = slice(start, stop)
        else:
            clamped_hl_indexes = sample_indexes

        # Read high-level data
        data = hl_logger.get_samples(
            index=clamped_hl_indexes,
            signals=signals,
            to_dict=True
        )

        if data is None:
            return None

        if add_intermediate_samples and ll_start is not None and ll_end is not None:
            # Clamp low-level indices to available data
            clamped_ll_start = ll_start
            clamped_ll_end = min(ll_end, ll_size)

            if clamped_ll_start >= clamped_ll_end:
                # No LL data available, return HL data without expansion
                return data if isinstance(data, list) else [data]

            ll_sample_indexes = slice(clamped_ll_start, clamped_ll_end)
            ll_data = ll_logger.get_samples(
                index=ll_sample_indexes,
                signals=None,
                to_dict=True
            )

            if ll_data is None:
                return data if isinstance(data, list) else [data]

            # Normalize shapes
            if isinstance(data, dict):
                hl_samples = [data]
            else:
                hl_samples = list(data)

            if isinstance(ll_data, dict):
                ll_samples = [ll_data]
            else:
                ll_samples = list(ll_data)

            # Expand each high-level sample into 10 samples with LL data
            expanded_samples = []
            expected_ll_per_hl = 10
            total_hl = len(hl_samples)
            total_ll = len(ll_samples)

            for i, hl_sample in enumerate(hl_samples):
                base_tick = hl_sample.get('tick', i * 10)
                base_time = hl_sample.get('time')
                base_ll_index = i * expected_ll_per_hl

                for j in range(expected_ll_per_hl):
                    ll_index = base_ll_index + j
                    if ll_index >= total_ll:
                        break

                    ll_sample = ll_samples[ll_index]

                    # Shallow copy of the high-level sample
                    new_sample = dict(hl_sample)
                    new_sample['tick'] = base_tick + j
                    new_sample['lowlevel'] = ll_sample
                    if base_time is not None:
                        new_sample['time'] = base_time + j * control_dt

                    expanded_samples.append(new_sample)

            data = expanded_samples

        return data

    finally:
        # Clean up
        if hl_logger.file:
            hl_logger.file.close()
        if ll_logger.file:
            ll_logger.file.close()


def _save_experiment_with_samples_worker(result_dataclass,
                                         hl_filename: str,
                                         ll_filename: str,
                                         start_tick: int,
                                         end_tick: int,
                                         control_dt: float,
                                         filepath: str,
                                         base_tick: int = 0):
    """Subprocess: convert result to dict, read H5 samples, write JSON.

    base_tick: tick of the first sample in the H5 file (accounts for startup-lost batches).
    """
    import warnings
    warnings.filterwarnings('ignore', message='.*No channels have been set up.*')
    warnings.filterwarnings('ignore', message='.*clean up.*')

    import h5py
    import sys

    result_dict = dataclasses.asdict(result_dataclass)

    hl_index_start = (start_tick - base_tick) // 10
    hl_index_end = (end_tick - base_tick) // 10

    # Verify alignment — error if runtime drift occurred
    try:
        with h5py.File(hl_filename, 'r', locking=False) as f:
            dataset = f['samples']
            if hl_index_start < dataset.shape[0]:
                actual_tick = int(dataset[hl_index_start]['tick'])
                if actual_tick != start_tick:
                    print(f"[EXPERIMENT SAVE] ERROR: H5 index drift detected! "
                          f"Expected tick {start_tick} at index {hl_index_start}, "
                          f"got tick {actual_tick} (drift: {(actual_tick - start_tick) // 10} batches). "
                          f"Experiment samples will be wrong!", file=sys.stderr)
    except Exception as e:
        print(f"[EXPERIMENT SAVE] WARNING: Could not verify H5 alignment: {e}", file=sys.stderr)

    ll_start = hl_index_start * 10
    ll_end = hl_index_end * 10

    sample_indexes = slice(hl_index_start, hl_index_end)

    samples = _get_data_worker(
        hl_filename=hl_filename,
        ll_filename=ll_filename,
        sample_indexes=sample_indexes,
        signals=None,
        add_intermediate_samples=True,
        ll_start=ll_start,
        ll_end=ll_end,
        control_dt=control_dt,
    )

    result_dict['samples'] = samples if samples is not None else []
    writeJSON(filepath, result_dict)


# === Callbacks ========================================================================================================
@callback_definition
class BILBO_Logging_Callbacks:
    on_sample: CallbackContainer
    initialized: CallbackContainer


@event_definition
class BILBO_Logging_Events:
    sample: Event = Event(data_type=BILBO_Sample)
    error: Event
    initialized: Event


class BILBO_Logging(LoggingProvider):
    tick: int = 0

    _samples_queue: queue.Queue

    _h5_logger_sample: H5PyDictLogger
    _h5_logger_lowlevel: H5PyDictLogger

    _initialized: bool = False

    _update_lock: threading.Lock

    # === INIT =========================================================================================================
    def __init__(self,
                 common: BILBO_Common,
                 communication: BILBO_Communication,
                 control: BILBO_Control,
                 sensors: BILBO_Sensors,
                 estimation: BILBO_Estimation,
                 drive: BILBO_Drive,
                 experiment_handler: BILBO_ExperimentHandler,
                 ):
        # --- INPUTS ---
        self.common = common
        self.communication = communication
        self.control = control
        self.sensors = sensors
        self.estimation = estimation
        self.drive = drive
        self.experiment_handler = experiment_handler

        # --- LOGGER ---
        self.logger = Logger('Logging', "DEBUG")

        # --- CALLBACKS AND EVENTS ---
        self.callbacks = BILBO_Logging_Callbacks()
        self.events = BILBO_Logging_Events()

        # --- MEMBERS ---
        self.tick = 0
        self.base_tick = 0  # tick of the first sample written to H5 (set on first batch)
        self.missed_batches = 0  # cumulative count of batches lost during runtime

        # --- H5 LOGGER ---
        self._h5_logger_sample = H5PyDictLogger(
            filename='log.h5',
        )
        self._h5_logger_lowlevel = H5PyDictLogger(filename='log_ll.h5')

        # --- QUEUES ---
        self._samples_queue = queue.Queue()

        # --- Sample Timeout Timer ---
        self._sample_timeout_timer = TimeoutTimer(timeout_time=SAMPLE_TIMEOUT_TIME,
                                                  timeout_callback=self._timeout_callback)

        # --- SAMPLE ---
        self.sample = None

        self._update_lock = threading.Lock()

        # --- PROCESS POOL FOR NON-BLOCKING DATA RETRIEVAL ---
        self._process_pool = ProcessPoolExecutor(max_workers=1)

        set_logging_provider(self)
        # --- EXIT HANDLING ---
        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self._initialize_caches()
        # self._setup_gc_monitor()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.communication.spi.callbacks.rx_samples.register(self._stm32_samples_callback)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        # Shutdown process pool
        if hasattr(self, '_process_pool') and self._process_pool:
            self._process_pool.shutdown(wait=False)

        # Close H5 loggers
        if hasattr(self, '_h5_logger_sample') and self._h5_logger_sample:
            self._h5_logger_sample.close()
        if hasattr(self, '_h5_logger_lowlevel') and self._h5_logger_lowlevel:
            self._h5_logger_lowlevel.close()

    # ------------------------------------------------------------------------------------------------------------------
    def flush(self):
        """Force flush all buffered H5 data to disk.

        Also trims datasets to current_size so external readers (subprocesses)
        see correct bounds via dataset.shape[0].
        """
        for logger in (self._h5_logger_sample, self._h5_logger_lowlevel):
            if logger.file:
                logger.flush_write_buffer()
                with logger.lock:
                    if logger.dataset is not None and logger.current_size < logger._allocated_size:
                        logger.dataset.resize((logger.current_size,))
                        logger._allocated_size = logger.current_size
                    logger.file.flush()

    # ------------------------------------------------------------------------------------------------------------------
    def get_tick(self) -> int:
        return self.tick

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        with self._update_lock:

            # if 290 <= self.tick <= 320:
            #     self.logger.debug(f"Start update. Old tick {self.tick}")

            # Reset timeout early
            self._sample_timeout_timer.reset()

            # Build the high-level sample
            sample_dict = self._build_sample()

            # Make the low-level samples
            sample_batch = 0

            while True:
                try:
                    batch = self._samples_queue.get_nowait()
                    sample_batch += 1
                    if sample_batch > 1:
                        if sample_batch >= 8:
                            self.logger.warning(f"Working on sample batch {sample_batch}")
                        else:
                            ...
                            # self.logger.debug(f"Working on sample batch {sample_batch}")
                except queue.Empty:
                    break

                # Get the tick from the low-level sample (authoritative source)
                ll_tick = batch[0]['tick']

                # Skip duplicate batches: if the LL tick hasn't advanced past what we
                # already processed, this is a duplicate SPI read (caused by stacked
                # GPIO interrupts when the GIL was blocked while firmware overwrote
                # _sample_buffer_tx with a newer batch)
                if ll_tick < self.tick:
                    self.logger.warning(
                        f"Skipping duplicate batch {sample_batch}: ll_tick={ll_tick} < self.tick={self.tick}")
                    continue

                # Record base tick on the very first batch
                if self.tick == 0:
                    self.base_tick = ll_tick
                    if ll_tick > 0:
                        self.logger.info(f"Logging started at tick {ll_tick} (skipped {ll_tick // 10} startup batches)")
                    else:
                        self.logger.info(f"Logging started at tick 0")

                # Detect gaps: expected tick is self.tick, any jump means we lost batches
                if 0 < self.tick < ll_tick:
                    missed = (ll_tick - self.tick) // 10
                    self.missed_batches += missed
                    self.logger.warning(f"Tick gap detected: expected {self.tick}, got {ll_tick} "
                                        f"(missed {missed} batch(es), total missed: {self.missed_batches})")

                # Always use ll_tick for the sample (it's the authoritative source)
                # Update both top-level and general.tick to keep sample consistent
                sample_dict['tick'] = ll_tick
                sample_dict['general']['tick'] = ll_tick
                self.tick = ll_tick + 10

                # Append the sample to the lowlevel logger
                t0 = time.perf_counter()

                self._h5_logger_lowlevel.append_multiple_samples(batch)
                # Append the highlevel sample to the highlevel logger
                sample_dict['lowlevel'] = batch[0]
                self._h5_logger_sample.append_sample(sample_dict)

                if self.tick % 2000 == 0:
                    self.logger.debug(f"Samples collected: {self.tick}")

                self._send_samples_to_host([sample_dict])
                self.sample = from_dict_auto(BILBO_Sample, sample_dict)
                t4 = time.perf_counter()

                self.common.events.sample.set(data=self.sample)

                # Log slow batch processing to identify bottleneck
                total = t4 - t0
                if total > 0.05:
                    self.logger.warning(
                        f"Slow batch ({total * 1000:.0f}ms)")

                # if 290 <= self.tick <= 320:
                #     self.logger.debug(f"Finished global tick: {self.tick}")

    # ------------------------------------------------------------------------------------------------------------------
    def get_data(self,
                 index: int | None = None,
                 start: int | None = None,
                 end: int | None = None,
                 signals: list[str] | None = None,
                 add_intermediate_samples: bool = False,
                 callback: Callable[[dict | list | None], None] | None = None) -> dict | list | None | Future:
        """
        Retrieves logged data using a separate process to avoid blocking the control loop.

        Args:
            index: Single tick index to retrieve (must be multiple of 10)
            start: Start tick (must be multiple of 10)
            end: End tick (must be multiple of 10)
            signals: List of flattened dict keys to return, e.g. ['estimation.state', 'sensors.imu.gyr']
            add_intermediate_samples: If True, expand HL samples with LL data (10x more samples)
            callback: If provided, runs async and calls callback(data) when done. Returns Future.
                      If None, blocks until data is ready and returns the data directly.

        Returns:
            If callback is None: The data (dict, list, or None)
            If callback is provided: A Future object that can be used to check completion
        """
        # Validation
        if index is not None and (start is not None or end is not None):
            self.logger.warning("Both index and start/end are provided. Please choose either")
            return None

        if add_intermediate_samples and signals is not None:
            self.logger.warning("Both add_intermediate_samples and signals are provided. Please choose either")
            return None

        if start is not None and start % 10 != 0:
            self.logger.warning(f"Start index {start} is not a multiple of 10")
            return None

        if end is not None and end % 10 != 0:
            self.logger.warning(f"End index {end} is not a multiple of 10")
            return None

        # Compute parameters for worker (account for base_tick offset)
        bt = self.base_tick
        if index is not None:
            sample_indexes = (index - bt) // 10
            ll_start = (index - bt) if add_intermediate_samples else None
            ll_end = (index - bt + 10) if add_intermediate_samples else None
        else:
            if start is None:
                start = bt
            if end is None:
                end = self.tick - 1
            sample_indexes = slice((start - bt) // 10, (end - bt) // 10)
            ll_start = (start - bt) if add_intermediate_samples else None
            ll_end = (end - bt) if add_intermediate_samples else None

        # Flush H5 data to disk so the reader process sees all samples
        self.flush()

        # Get file paths
        hl_filename = self._h5_logger_sample.filename
        ll_filename = self._h5_logger_lowlevel.filename

        # Verify H5 alignment before reading: check that the tick stored at the
        # computed start index actually matches the requested tick.
        if isinstance(sample_indexes, int):
            _check_idx = sample_indexes
            _expected_tick = index
        elif isinstance(sample_indexes, slice) and sample_indexes.start is not None:
            _check_idx = sample_indexes.start
            _expected_tick = (start if start is not None else bt)
        else:
            _check_idx = None
            _expected_tick = None

        if _check_idx is not None and _expected_tick is not None:
            try:
                with h5py.File(hl_filename, 'r', locking=False) as f:
                    ds = f['samples']
                    if _check_idx < ds.shape[0]:
                        actual_tick = int(ds[_check_idx]['tick'])
                        if actual_tick != _expected_tick:
                            self.logger.error(
                                f"H5 index drift detected in get_data! "
                                f"Expected tick {_expected_tick} at H5 index {_check_idx}, "
                                f"got tick {actual_tick} (drift: {(actual_tick - _expected_tick) // 10} batches). "
                                f"Data will be misaligned!")
            except Exception as e:
                self.logger.warning(f"Could not verify H5 alignment: {e}")

        # Submit to process pool
        future = self._process_pool.submit(
            _get_data_worker,
            hl_filename,
            ll_filename,
            sample_indexes,
            signals,
            add_intermediate_samples,
            ll_start,
            ll_end,
            BILBO_CONTROL_DT
        )

        if callback is not None:
            # Async mode: add callback and return future
            def _on_done(f):
                try:
                    result = f.result()
                    callback(result)
                except Exception as e:
                    self.logger.error(f"get_data worker failed: {e}")
                    callback(None)

            future.add_done_callback(_on_done)
            return future
        else:
            # Sync mode: wait for result
            try:
                return future.result()
            except Exception as e:
                self.logger.error(f"get_data worker failed: {e}")
                return None

    # ------------------------------------------------------------------------------------------------------------------
    def get_data_old(self,
                     index: int | None = None,
                     start: int | None = None,
                     end: int | None = None,
                     signals: list[str] | None = None,
                     add_intermediate_samples: bool = False) -> dict | None:
        """
        Original get_data implementation (blocks the calling thread and may cause GIL contention).

        Args:
            index:
            start:
            end:
            signals: list of the flattened dict keys to return, i.e. ['estimation.state', 'sensors.imu.gyr']
            add_intermediate_samples:
        Returns:

        """

        if index is not None and (start is not None or end is not None):
            self.logger.warning("Both index and start/end are provided. Please choose either")
            return None

        if add_intermediate_samples and signals is not None:
            self.logger.warning("Both add_intermediate_samples and signals are provided. Please choose either")
            return None

        # start and end need to be integer multiples of 10
        if start is not None and not start % 10 == 0:
            self.logger.warning(f"Start index {start} is not a multiple of 10")
            return None

        if end is not None and not end % 10 == 0:
            self.logger.warning(f"End index {end} is not a multiple of 10")
            return None

        # Map requested tick/index to high-level sample indices in H5 (account for base_tick)
        bt = self.base_tick
        if index is not None:
            # index is in "tick" domain (0, 10, 20, ...); convert to hl sample index
            sample_indexes = (index - bt) // 10
        else:
            if start is None:
                start = bt
            if end is None:
                end = self.tick - 1

            sample_indexes = slice((start - bt) // 10, (end - bt) // 10)

        data = self._h5_logger_sample.get_samples(
            index=sample_indexes,
            signals=signals,
            to_dict=True
        )

        # Give other threads time to run after H5 read
        time.sleep(0.005)

        if data is None:
            return None

        if add_intermediate_samples:
            # ------------------------------------------------------------------
            # 1) Figure out which low-level indices we need
            # ------------------------------------------------------------------
            if index is not None:
                # One high-level sample with tick = index
                # -> want low-level ticks index .. index+9
                ll_start = index
                ll_end = index + 10  # end is exclusive in our convention
            else:
                # start/end are in tick domain already and multiples of 10
                ll_start = start
                ll_end = end

            # Force using start/end so get_lowlevel_data doesn't try to use `index`
            ll_data = self.get_lowlevel_data(
                index=None,
                start=ll_start,
                end=ll_end,
                signals=None  # we need the full low-level sample
            )

            # Give other threads time to run after H5 read
            time.sleep(0.005)

            if ll_data is None:
                return None

            # Normalize shapes: make both high-level and low-level lists of dicts
            if isinstance(data, dict):
                # Single high-level sample
                hl_samples = [data]
            else:
                hl_samples = list(data)

            if isinstance(ll_data, dict):
                ll_samples = [ll_data]
            else:
                ll_samples = list(ll_data)

            # ------------------------------------------------------------------
            # 2) Expand each high-level sample into 10 samples with LL data
            # ------------------------------------------------------------------
            expanded_samples: list[dict] = []

            # Expect 10 low-level samples per high-level sample
            expected_ll_per_hl = 10
            total_hl = len(hl_samples)
            total_ll = len(ll_samples)

            if total_ll < total_hl * expected_ll_per_hl:
                self.logger.warning(
                    f"Not enough low-level samples ({total_ll}) for "
                    f"{total_hl} high-level samples (expected {total_hl * expected_ll_per_hl}). "
                    f"Will use as many as are available."
                )

            for i, hl_sample in enumerate(hl_samples):
                base_tick = hl_sample.get('tick', i * 10)
                base_time = hl_sample.get('time')
                base_ll_index = i * expected_ll_per_hl

                for j in range(expected_ll_per_hl):
                    ll_index = base_ll_index + j
                    if ll_index >= total_ll:
                        # No more low-level samples available
                        break

                    ll_sample = ll_samples[ll_index]

                    # Shallow copy of the high-level sample is enough here
                    new_sample = copy(hl_sample)
                    # Adapt the tick: base_tick .. base_tick + 9
                    new_sample['tick'] = base_tick + j
                    # Insert the corresponding low-level sample
                    new_sample['lowlevel'] = ll_sample
                    new_sample['time'] = base_time + j * BILBO_CONTROL_DT

                    expanded_samples.append(new_sample)
                    time.sleep(0.001)

                # Give other threads time to run after each high-level sample expansion (every 10 ll samples)
                time.sleep(0.01)

            data = expanded_samples

        return data

    # ------------------------------------------------------------------------------------------------------------------
    def get_lowlevel_data(self,
                          index: int | None = None,
                          start: int | None = None,
                          end: int | None = None,
                          signals: list[str] | None = None) -> dict | None:

        if index is not None and (start is not None or end is not None):
            self.logger.warning("Both index and start/end are provided. Ignoring index.")

        # start and end need to be integer multiples of 10
        if not start % 10 == 0:
            self.logger.warning(f"Start index {start} is not a multiple of 10")
            return None

        if not end % 10 == 0:
            self.logger.warning(f"End index {end} is not a multiple of 10")
            return None

        # Account for base_tick offset
        bt = self.base_tick
        if index is not None:
            sample_indexes = index - bt
        else:
            if start is None:
                start = bt
            if end is None:
                end = self.tick - 1
            sample_indexes = slice(start - bt, end - bt)

        data = self._h5_logger_lowlevel.get_samples(
            index=sample_indexes,
            signals=signals,
            to_dict=True
        )

        # Give other threads time to run after H5 read
        time.sleep(0.005)

        return data

    # ------------------------------------------------------------------------------------------------------------------

    # === PRIVATE METHODS ==============================================================================================
    def _stm32_samples_callback(self, samples, *args, **kwargs):
        #
        # if 290 <= self.tick <= 320:
        #     self.logger.debug(f"Received samples. Tick: {samples[0]['tick']} - {samples[-1]['tick']}")

        # Use deepcopy to ensure each batch in the queue has independent dict objects
        # (shallow copy would share the inner dicts, causing tick sync issues if reused)
        self._samples_queue.put(deepcopy(samples))

    # ------------------------------------------------------------------------------------------------------------------
    def _initialize_caches(self) -> None:
        if self._initialized:
            return

        # Generate dicts from the sample dataclasses
        hl_template = asdict_optimized(BILBO_Sample())
        ll_template = asdict_optimized(BILBO_LL_Sample())

        schema_hl = dict(hl_template)
        schema_ll = dict(ll_template)

        self._h5_logger_sample.init(schema_hl)
        self._h5_logger_lowlevel.init(schema_ll)

        self._h5_logger_sample.start('w')
        self._h5_logger_lowlevel.start('w')

        self._copy_cache_hl = copy_dict(dict_from=schema_hl,
                                        dict_to={},
                                        structure_cache=None)
        self._copy_cache_ll = copy_dict(dict_from=ll_template,
                                        dict_to={},
                                        structure_cache=None)

        self._initialized = True

    # ------------------------------------------------------------------------------------------------------------------
    def _setup_gc_monitor(self):
        """Install a GC callback that logs whenever a collection takes more than 10 ms."""
        self._gc_times = [0.0, 0.0, 0.0]  # start time per generation

        def _gc_callback(phase, info):
            gen = info.get('generation', 0)
            if phase == 'start':
                self._gc_times[gen] = time.perf_counter()
            elif phase == 'stop':
                elapsed = time.perf_counter() - self._gc_times[gen]
                if elapsed > 0.01:
                    collected = info.get('collected', '?')
                    uncollectable = info.get('uncollectable', '?')
                    self.logger.warning(
                        f"GC gen{gen} took {elapsed * 1000:.1f} ms "
                        f"(collected={collected}, uncollectable={uncollectable})")

        gc.callbacks.append(_gc_callback)
        self.logger.info(f"GC monitor installed. Thresholds: {gc.get_threshold()}, "
                         f"counts: {gc.get_count()}")

    # ------------------------------------------------------------------------------------------------------------------
    def _timeout_callback(self):
        self.logger.error('Sample timeout')
        self.events.error.set(flags={'type': 'sample_timeout'})
        self.common.events.error.set(data={'type': 'sample_timeout'})

    # ------------------------------------------------------------------------------------------------------------------
    def _build_sample(self) -> dict:
        sample = {
            'tick': self.tick,
            'time': time.monotonic(),
            'general': self.common.get_general_sample_dict(),
            'control': self.control.get_sample_dict(),
            'sensors': self.sensors.get_sample_dict(),
            'estimation': self.estimation.get_sample_dict(),
            'drive': self.drive.get_sample_dict(),
            'experiment': self.experiment_handler.get_sample_dict(),
        }
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def _send_samples_to_host(self, samples: list[dict]):
        samples_out = [optimized_deepcopy(s, self._copy_cache_hl) for s in samples]
        self.communication.wifi.sendStream(samples_out, 'samples')
    # ------------------------------------------------------------------------------------------------------------------
