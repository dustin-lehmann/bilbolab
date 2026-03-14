import copy
import threading
from ctypes import sizeof

# === OWN PACKAGES =====================================================================================================
from core.communication.spi.spi import SPI_Interface
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import from_dict
# from utils.exit import ExitHandler
from robot.lowlevel.stm32_sample import bilbo_ll_sample_struct, BILBO_LL_Sample
from core.utils.ctypes_utils import bytes_to_value
from robot.lowlevel.stm32_sample import SAMPLE_BUFFER_LL_SIZE, MAX_PENDING_BATCHES
from hardware.hardware.gpio import GPIO_Input, InterruptFlank, PullupPulldown
from core.utils.logging_utils import Logger
from core.utils.time import precise_sleep
from core.utils.bytes_utils import intToByteList


# ======================================================================================================================
@callback_definition
class BILBO_SPI_Callbacks:
    rx_latest_sample: CallbackContainer
    rx_samples: CallbackContainer


class BILBO_SPI_Command_Type:
    READ_SAMPLE = 1
    SEND_TRAJECTORY = 2
    SEND_PATH = 3


# ======================================================================================================================
class BILBO_SPI_Interface:
    interface: SPI_Interface
    callbacks: BILBO_SPI_Callbacks
    sample_notification_pin: int

    gpio_input: GPIO_Input | None

    lock: threading.Lock

    _startSampleListening: bool

    def __init__(self, interface: SPI_Interface, sample_notification_pin):
        self.interface = interface
        self.sample_notification_pin = sample_notification_pin
        self.callbacks = BILBO_SPI_Callbacks()

        self.gpio_input = None

        self.logger = Logger('SPI')
        self.lock = threading.Lock()

        self._startSampleListening = False

        # self.exit = ExitHandler()
        # self.exit.register(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self._configureSampleGPIO()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def startSampleListener(self):
        self._startSampleListening = True

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        ...

    def sendTrajectoryData(self, trajectory_length, trajectory_data_bytes: bytes | bytearray):
        with self.lock:
            self._sendCommand(BILBO_SPI_Command_Type.SEND_TRAJECTORY, trajectory_length)
            precise_sleep(0.005)
            self.interface.send(trajectory_data_bytes)

    def sendPathData(self, path_length: int, path_data_bytes: bytes | bytearray):
        with self.lock:
            self._sendCommand(BILBO_SPI_Command_Type.SEND_PATH, path_length)
            precise_sleep(0.005)
            self.interface.send(path_data_bytes)

    # === PRIVATE METHODS ==============================================================================================
    def _configureSampleGPIO(self):
        self.gpio_input = GPIO_Input(
            pin=self.sample_notification_pin,
            pin_type='internal',
            interrupt_flank=InterruptFlank.BOTH,
            pull_up_down=PullupPulldown.DOWN,
            callback=self._samplesReadyInterrupt,
            bouncetime=1
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _sendCommand(self, command: int, length: int):
        assert (command in [BILBO_SPI_Command_Type.READ_SAMPLE, BILBO_SPI_Command_Type.SEND_TRAJECTORY, BILBO_SPI_Command_Type.SEND_PATH])

        data = bytearray(4)

        len_byte_list = intToByteList(length, 2, byteorder='little')
        data[0] = 0x66
        data[1] = command
        data[2:4] = len_byte_list
        self.interface.send(data)

    # ------------------------------------------------------------------------------------------------------------------
    def _samplesReadyInterrupt(self, *args, **kwargs):
        if not self._startSampleListening:
            return

        batches, latest_sample = self._readSamples()

        if len(batches) > 3:
            self.logger.warning(f"SPI read returned {len(batches)} pending batches")

        # Each batch is a list of sample dicts; deliver them individually
        for batch in batches:
            batch = copy.deepcopy(batch)
            for callback in self.callbacks.rx_samples:
                callback(batch)

        if latest_sample is not None:
            for callback in self.callbacks.rx_latest_sample:
                callback(latest_sample)

    # ------------------------------------------------------------------------------------------------------------------
    def _readSamples(self) -> tuple[list[list[dict]], BILBO_LL_Sample | None]:
        """Read the multi-batch response from the firmware ring buffer.

        Wire format: [uint32_t count][batch_0][batch_1]...[batch_{count-1}]
        The SPI transfer is always the maximum size; 'count' tells us how many
        batches actually contain valid data.

        Returns:
            (batches, latest_sample) where batches is a list of sample-lists
            and latest_sample is the last sample of the last batch.
        """
        batch_byte_size = SAMPLE_BUFFER_LL_SIZE * sizeof(bilbo_ll_sample_struct)
        header_size = 4  # uint32_t count
        response_size = header_size + MAX_PENDING_BATCHES * batch_byte_size

        data_rx_bytes = bytearray(response_size)
        with self.lock:
            self._sendCommand(BILBO_SPI_Command_Type.READ_SAMPLE, 0)
            precise_sleep(0.005)
            self.interface.readinto(data_rx_bytes,
                                    start=0,
                                    end=response_size,
                                    write_value=0x05)

        # Parse count from header (little-endian uint32)
        count = int.from_bytes(data_rx_bytes[0:4], byteorder='little', signed=False)
        if count > MAX_PENDING_BATCHES:
            count = MAX_PENDING_BATCHES
        if count == 0:
            return [], None

        batches = []
        latest_sample = None
        for b in range(count):
            batch_offset = header_size + b * batch_byte_size
            samples = []
            for i in range(SAMPLE_BUFFER_LL_SIZE):
                sample_offset = batch_offset + i * sizeof(bilbo_ll_sample_struct)
                sample = bytes_to_value(
                    byte_data=data_rx_bytes[sample_offset:sample_offset + sizeof(bilbo_ll_sample_struct)],
                    ctype_type=bilbo_ll_sample_struct)
                samples.append(sample)
            batches.append(samples)

        latest_sample = from_dict(BILBO_LL_Sample, batches[-1][-1])
        return batches, latest_sample
