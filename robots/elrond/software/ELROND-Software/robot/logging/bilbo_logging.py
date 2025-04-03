import dataclasses
import gc
from collections import deque
from contextlib import contextmanager
from copy import copy, deepcopy
from datetime import datetime
import threading

# === OWN PACKAGES =====================================================================================================
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control
from robot.drive.bilbo_drive import BILBO_Drive
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment.bilbo_experiment import BILBO_ExperimentHandler
from robot.logging.bilbo_sample import BILBO_Sample
from robot.lowlevel.stm32_sample import BILBO_LL_Sample, SAMPLE_BUFFER_LL_SIZE, bilbo_ll_sample_struct
from robot.sensors.bilbo_sensors import BILBO_Sensors
from utils.callbacks import callback_handler, CallbackContainer
from utils.dict_utils import copy_dict, optimized_deepcopy, optimized_generate_empty_copies
from utils.events import EventListener
from utils.exit import ExitHandler
from utils.csv_utils import CSVLogger
from paths import experiments_path
from utils.dataclass_utils import freeze_dataclass_instance, from_dict, asdict_optimized
from utils.time import PerformanceTimer, TimeoutTimer
from utils.logging_utils import Logger, setLoggerLevel
from utils.h5 import H5PyDictLogger
from utils.ctypes_utils import struct_to_dict

logger = Logger("Logging")
logger.setLevel('DEBUG')


# === Callbacks ========================================================================================================
@callback_handler
class BILBO_Logging_Callbacks:
    on_sample: CallbackContainer
    initialized: CallbackContainer


# === BILBO Logging ====================================================================================================
class BILBO_Logging:
    comm: BILBO_Communication
    control: BILBO_Control
    sensors: BILBO_Sensors
    estimation: BILBO_Estimation
    drive: BILBO_Drive

    general_sample_collect_function: callable

    sample: BILBO_Sample
    _sample_buffer: (None, list[dict])

    _h5Logger: H5PyDictLogger

    SAMPLE_BUFFER_SIZE = 1 * 60 * 100

    _sample_buffer_ll: list[dict]
    _csvLogger: CSVLogger
    exit: ExitHandler

    _rx_stm32_event_listener: EventListener

    def __init__(self, comm: BILBO_Communication,
                 control: BILBO_Control,
                 sensors: BILBO_Sensors,
                 estimation: BILBO_Estimation,
                 drive: BILBO_Drive,
                 experiment_handler: BILBO_ExperimentHandler,
                 general_sample_collect_function: callable):

        self.comm = comm
        self.control = control
        self.sensors = sensors
        self.estimation = estimation
        self.drive = drive
        self.experiment_handler = experiment_handler
        self.general_sample_collect_function = general_sample_collect_function

        self.comm.spi.callbacks.rx_samples.register(self._stm32samples_callback)
        self.sample = BILBO_Sample()

        self._sample_timeout_timer = TimeoutTimer(timeout_time=1, timeout_callback=self._sample_timeout_callback)

        self._h5Logger = H5PyDictLogger(filename='log.h5')
        self._csvLogger = CSVLogger()
        self._num_samples = 0
        self.sample_index = None

        self._sample_buffer = None
        self._index_sample_buffer = 0
        self._first_sample_received = False
        self._dict_cache = None
        self._dict_cache_ll = None
        self._sample_deepcopy_cache = None
        self._sample_buffer_ll = []
        self._lock = threading.Lock()  # Lock to ensure thread-safe access to the ring buffer.
        self._samples_queue = deque()  # Queue for low-level sample batches.

    # === METHODS ======================================================================================================
    def init(self) -> None:
        self._build_sample_buffer()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self) -> None:
        # self._sample_timeout_timer.start()
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def getNumSamples(self):
        return self._num_samples

    # ------------------------------------------------------------------------------------------------------------------
    def startFileLogging(self, filename: str = None, folder: str = None):
        # Append yyyymmdd_hhmmss to the filename
        time_value = datetime.fromtimestamp(self.comm.wifi.getTime())

        if filename is not None:
            filename = f"{filename}_{time_value:%Y%m%d_%H%M%S}.csv"
        else:
            filename = f"{time_value:%Y%m%d_%H%M%S}.csv"

        folder = f"{experiments_path}/{folder}" if folder is not None else experiments_path

        logger.debug(f"Start logging to {folder}/{filename}")

        self._csvLogger.make_file(filename, folder)

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self, index_start: int = None, index_end: int = None, signals=None, hdf5_only: bool = True,
                deepcopy: bool = False) -> (list, dict):
        """
        Retrieves a list of logged samples between index_start and index_end.
        This function checks whether the requested samples are in the local ring buffer or in the HDF5 file.
        The global sample count is tracked by self._num_samples.
        The local ring buffer holds the most recent samples corresponding to indices from
        (self._num_samples - len(self._sample_buffer)) to (self._num_samples - 1) if the buffer is full.
        If the buffer is not full, samples are stored sequentially in the beginning of the list.

        Parameters:
            index_start (int): Starting global sample index.
            index_end (int): Ending global sample index.
            hdf5_only (bool): If True, only read samples from the H5Py logger.
            deepcopy (bool): If True, deep copy samples retrieved from the local ring buffer.
        """

        if signals is not None and not isinstance(signals, list):
            signals = [signals]

        with self._lock:
            total_samples = self._num_samples
            if total_samples == 0:
                return []
            # Default indices if not provided.
            if index_start is None:
                index_start = 0
            if index_end is None or index_end > total_samples:
                index_end = total_samples
            if index_start < 0:
                index_start = 0

        # If hdf5_only is requested, return all samples from H5.
        if hdf5_only:
            samples = self._h5Logger.getSampleBatch(slice(index_start, index_end), signal=signals)
            return samples

        raise Exception("HDF5 only mode supported yet.")
        # with self._lock:
        #     buffer_size = len(self._sample_buffer)
        #     result = []
        #
        #     # Determine the global index corresponding to the first sample in the ring buffer.
        #     if total_samples < buffer_size:
        #         ring_buffer_start_index = 0  # All samples are in the buffer sequentially.
        #     else:
        #         ring_buffer_start_index = total_samples - buffer_size
        #
        #     # Fetch older samples from HDF5 if needed.
        #     if index_start < ring_buffer_start_index:
        #         h5_end = min(index_end, ring_buffer_start_index)
        #         with self._h5Logger.lock:
        #             h5_data = self._h5Logger.dataset[index_start:h5_end]
        #         h5_samples = self._h5Logger.record_to_dict(h5_data)
        #         result.extend(h5_samples)
        #
        #     # Fetch samples from the local ring buffer if the requested range includes recent samples.
        #     if index_end > ring_buffer_start_index:
        #         for i in range(max(index_start, ring_buffer_start_index), index_end):
        #             if total_samples < buffer_size:
        #                 # Buffer not full: direct mapping.
        #                 local_idx = i
        #             else:
        #                 # Buffer is full: map global index to local index using circular indexing.
        #                 local_idx = (self._index_sample_buffer + (i - ring_buffer_start_index)) % buffer_size
        #             if deepcopy:
        #                 result.append(optimized_deepcopy(self._sample_buffer[local_idx], self._sample_deepcopy_cache))
        #             else:
        #                 result.append(self._sample_buffer[local_idx])
        #     return result

    # ------------------------------------------------------------------------------------------------------------------
    def stopFileLogging(self):
        self._csvLogger.close()
        logger.debug("Stop file logging")

    # ------------------------------------------------------------------------------------------------------------------
    def update(self) -> None:

        self._sample_timeout_timer.reset()

        # Collect the sample from all submodules
        timer = PerformanceTimer(name='Update', print_output=False)
        sample: dict = self._collectData()

        # Send the current sample via WI-FI
        if self.comm.wifi.connected:
            self.comm.wifi.sendStream(sample)

        batches = 0
        # Process all available low-level sample batches from the queue.
        while True:
            try:
                batch = self._samples_queue.popleft()
                batches += 1
            except IndexError:
                break

            for i in range(0, SAMPLE_BUFFER_LL_SIZE):
                self._dict_cache = copy_dict(dict_from=sample,
                                             dict_to=self._sample_buffer[self._index_sample_buffer],
                                             structure_cache=self._dict_cache)
                self._sample_buffer[self._index_sample_buffer]['general']['tick'] = sample['general']['tick'] + i
                self._sample_buffer[self._index_sample_buffer]['general']['time'] = (sample['general']['tick'] + i) * \
                                                                                    sample['general']['sample_time_ll']

                self._dict_cache_ll = copy_dict(dict_from=batch[i],
                                                dict_to=self._sample_buffer[self._index_sample_buffer]['lowlevel'],
                                                structure_cache=self._dict_cache_ll)

                self._index_sample_buffer = (self._index_sample_buffer + 1) % len(self._sample_buffer)

            # --------------------------------------------------------------------------------------------------------------
            self._h5Logger.appendSamples(self._get_last_samples(SAMPLE_BUFFER_LL_SIZE))

            # --------------------------------------------------------------------------------------------------------------
            if self._csvLogger.is_open:
                self._csvLogger.log_event(self._get_last_samples(SAMPLE_BUFFER_LL_SIZE))

            if self.sample_index is None:
                self._sample_timeout_timer.start()
                self.sample_index = from_dict(BILBO_Sample, self._sample_buffer[self._index_sample_buffer - 1]).lowlevel.general.tick

                # Check if the sample index started at 0
                if self.sample_index != SAMPLE_BUFFER_LL_SIZE - 1:
                    logger.warning(f"Sample index started at {self.sample_index - SAMPLE_BUFFER_LL_SIZE + 1} instead of 0")
                else:
                    logger.debug("Logging started with sample index 0")
            else:
                self.sample_index += SAMPLE_BUFFER_LL_SIZE

            if self.sample_index != from_dict(BILBO_Sample, self._sample_buffer[self._index_sample_buffer - 1]).lowlevel.general.tick:
                logger.warning(f"Sample index mismatch: HL: {self.sample_index} != LL: {from_dict(BILBO_Sample, self._sample_buffer[self._index_sample_buffer - 1]).lowlevel.general.tick}")

            self._num_samples += SAMPLE_BUFFER_LL_SIZE

            if self._num_samples % 2000 == 0:
                logger.debug(f"Samples collected: {self._num_samples}")

        self.sample = from_dict(BILBO_Sample, self._sample_buffer[self._index_sample_buffer - 1])

        elapsed_time = timer.stop()

        if elapsed_time > 0.1:
            logger.warning(f"Logging took {elapsed_time:.2f}s")

    # ------------------------------------------------------------------------------------------------------------------
    def deepcopy_samples(self, samples: list[dict]) -> list[dict]:
        if not isinstance(samples, list):
            samples = [samples]
        new_samples = []
        for i in range(len(samples)):
            new_samples.append(optimized_deepcopy(samples[i], self._sample_deepcopy_cache))
        return new_samples

    # === PRIVATE METHODS ==============================================================================================
    def _collectData(self) -> dict:
        sample = {
            'general': self.general_sample_collect_function(),
            'control': self.control.getSample(),
            'sensors': self.sensors.getSample(),
            'estimation': self.estimation.getSample(),
            'drive': self.drive.getSample(),
            'experiment': self.experiment_handler.getSample(),
        }
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def _stm32samples_callback(self, samples: list[dict]):
        self._samples_queue.append(copy(samples))

    # ------------------------------------------------------------------------------------------------------------------
    def _build_sample_buffer(self):
        sample = self._collectData()
        sample['lowlevel'] = asdict_optimized(BILBO_LL_Sample())

        _, self._sample_deepcopy_cache = optimized_deepcopy(sample)
        self._sample_buffer = [optimized_deepcopy(sample, self._sample_deepcopy_cache) for _ in
                               range(self.SAMPLE_BUFFER_SIZE)]

        _ = from_dict(BILBO_Sample, self._sample_buffer[0])

        self._h5Logger.init(sample)
        self._h5Logger.start('w')

    # ------------------------------------------------------------------------------------------------------------------
    def _get_last_samples(self, n: int) -> list:
        start = self._index_sample_buffer - n
        if start < 0:
            # Take the tail of the list and then the beginning
            return self._sample_buffer[start:] + self._sample_buffer[:self._index_sample_buffer]
        else:
            return self._sample_buffer[start:self._index_sample_buffer]

    # ------------------------------------------------------------------------------------------------------------------
    def _get_value_by_path(self, sample: dict, path: str):
        """
        Retrieves a value from a nested dictionary using a dot-separated path.
        """
        keys = path.split('.')
        value = sample
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, None)
            else:
                return None
        return value

    # ------------------------------------------------------------------------------------------------------------------
    def _sample_timeout_callback(self, *args, **kwargs):
        logger.error("Sample timeout")
