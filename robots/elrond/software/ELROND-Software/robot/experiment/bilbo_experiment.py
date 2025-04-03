import ctypes
import dataclasses
import enum
import time
from typing import Any, cast
from numpy.core.defchararray import isnumeric

# ======================================================================================================================
from robot.communication.bilbo_communication import BILBO_Communication
from robot.communication.serial.bilbo_serial_messages import BILBO_Sequencer_Event_Message
from robot.control.bilbo_control import BILBO_Control
from robot.control.definitions import BILBO_Control_Mode
from robot.lowlevel.stm32_general import MAX_STEPS_TRAJECTORY, LOOP_TIME_CONTROL
from robot.lowlevel.stm32_sequencer import bilbo_sequence_input_t, bilbo_sequence_description_t, BILBO_Sequence_LL
import robot.lowlevel.stm32_addresses as addresses
from robot.utilities.bilbo_utilities import BILBO_Utilities
from utils.callbacks import callback_handler, CallbackContainer
from utils.events import event_handler, ConditionEvent
from utils.logging_utils import Logger, setLoggerLevel
from utils.ctypes_utils import struct_to_dataclass
from utils.dataclass_utils import from_dict
from paths import experiments_path
from robot.lowlevel.stm32_messages import BILBO_LL_MESSAGE_SEQUENCER_EVENT
from utils.sound.sound import speak
from utils.data import generate_random_input, generate_time_vector
from core.communication.wifi.data_link import CommandArgument


# ======================================================================================================================


class BILBO_LL_Sequencer_Event_Type(enum.IntEnum):
    STARTED = 1
    FINISHED = 2
    ABORTED = 3
    RECEIVED = 4


# ======================================================================================================================
logger = Logger('EXPERIMENT')
logger.setLevel('DEBUG')


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_TrajectoryInput:
    step: int
    left: float
    right: float


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_Trajectory:
    id: int
    name: str
    length: int
    inputs: dict[int, BILBO_TrajectoryInput]
    control_mode: BILBO_Control_Mode
    control_mode_end: BILBO_Control_Mode

    loaded: bool = False
    started: bool = False
    running: bool = False
    finished: bool = False
    aborted: bool = False


# TODO: ADD OUTPUTS TO THE TRAJECTORY

# === EXPERIMENT =======================================================================================================
class BILBO_Experiment_Type(enum.IntEnum):
    FREE = 1
    TRAJECTORY = 2
    MULTI_TRAJECTORY = 3


@dataclasses.dataclass
class BILBO_Experiment:
    name: str
    type: BILBO_Experiment_Type


# === CALLBACKS ========================================================================================================
@callback_handler
class BILBO_ExperimentCallbacks:
    trajectory_started: CallbackContainer
    trajectory_finished: CallbackContainer
    trajectory_aborted: CallbackContainer
    trajectory_loaded: CallbackContainer


@event_handler
class BILBO_ExperimentEvents:
    trajectory_started: ConditionEvent
    trajectory_finished: ConditionEvent
    trajectory_aborted: ConditionEvent
    trajectory_loaded: ConditionEvent


# === BILBO_ExperimentHandler =========================================================================================
class BILBO_ExperimentHandler:
    communication: BILBO_Communication
    callbacks: BILBO_ExperimentCallbacks
    events: BILBO_ExperimentEvents
    current_trajectory: BILBO_Trajectory = None

    running: bool = False

    def __init__(self, communication: BILBO_Communication, utils: BILBO_Utilities, control: BILBO_Control):
        self.communication = communication
        self.callbacks = BILBO_ExperimentCallbacks()
        self.events = BILBO_ExperimentEvents()
        self.utils = utils
        self.logging = None
        self.control = control

        self.communication.serial.callbacks.event.register(self._sequencer_event_callback,
                                                           parameters={'messages': [BILBO_Sequencer_Event_Message]})


        self.communication.wifi.addCommand(
            identifier='runTrajectory',
            arguments=[
                CommandArgument(name='trajectory_id',
                                type=int,
                                optional=False,
                                description='ID of the trajectory to run'),
                CommandArgument(name='input',
                                type=list,
                                optional=False,
                                description='Input Left/Right to the trajectory'),
                CommandArgument(name='signals',
                                type=list,
                                optional=True,
                                description='Signals to return from the trajectory'),
            ],
            callback=self._run_trajectory_external,
            description='Run a trajectory',
            execute_in_thread = True
        )

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, logging):
        self.logging = logging
    # ------------------------------------------------------------------------------------------------------------------
    def loadTrajectoryFromFile(self) -> BILBO_Trajectory:
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def saveTrajectoryToFile(self, trajectory: BILBO_Trajectory, filename: str):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def setTrajectory(self, trajectory: BILBO_Trajectory) -> bool:

        logger.info(f"Loading trajectory {trajectory.id} ... ")

        # First, check the trajectory length
        if trajectory.length != len(trajectory.inputs):
            logger.warning(f"Trajectory length does not match number of inputs. "
                           f"Trajectory length: {trajectory.length}, Number of inputs: {len(trajectory.inputs)}")
            return False

        # Load the trajectory data to the stm32
        success = self._setTrajectoryDescription_LL(trajectory)

        if not success:
            logger.warning("Failed to set trajectory")
            return False

        # Send the trajectory inputs via SPI
        trajectory_bytes = self._trajectoryInputToBytes(trajectory.inputs)
        self.communication.spi.sendTrajectoryData(trajectory.length, trajectory_bytes)

        success = self.events.trajectory_loaded.wait(
            timeout=2,
            stale_event_time=0.2,
            flags={'trajectory_id': trajectory.id}
        )

        if not success:
            logger.warning("Failed to load trajectory")
            return False

        logger.info(f"Trajectory {trajectory.id} loaded!")
        self.utils.speak(f"Trajectory {trajectory.id} loaded")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def startTrajectory(self, trajectory_id) -> bool:

        # First, check if a trajectory is loaded
        trajectory_data = self._readTrajectoryDescription_LL()

        if trajectory_data is None:
            logger.warning("No trajectory loaded")
            return False

        if trajectory_data.sequence_id != trajectory_id:
            logger.warning(f"Wrong trajectory id. Expected {trajectory_id}, loaded: {trajectory_data.sequence_id}")

        if not trajectory_data.loaded:
            logger.warning("Trajectory not loaded")

        logger.debug("Start trajectory")

        success = self._startTrajectory_LL(trajectory_id)

        if not success:
            logger.warning("Failed to start trajectory")
            return False

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def stopTrajectory(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def generateTestTrajectory(self, id, time, frequency=2, gain=0.25) -> (BILBO_Trajectory, None):
        # generate a simple trajectory

        t_vector = generate_time_vector(start=0, end=time, dt=LOOP_TIME_CONTROL)

        if len(t_vector) > MAX_STEPS_TRAJECTORY:
            logger.warning("Trajectory too long")
            return None

        input = generate_random_input(t_vector=t_vector, f_cutoff=frequency, sigma_I=gain)

        trajectory_inputs = self._generateTrajectoryInputs(input)

        trajectory = BILBO_Trajectory(
            id=id,
            name='test',
            length=len(trajectory_inputs),
            inputs=trajectory_inputs,
            control_mode=BILBO_Control_Mode.BALANCING,
            control_mode_end=BILBO_Control_Mode.BALANCING
        )

        return trajectory

    # ------------------------------------------------------------------------------------------------------------------
    def runTrajectory(self, trajectory: BILBO_Trajectory, signals: (list, str) = None) -> (dict, None):

        if signals is not None and not isinstance(signals, list):
            signals = [signals]


        logger.info(f"Running trajectory {trajectory.id} ...")

        # Set the trajectory data in the LL Module
        success = self.setTrajectory(trajectory)

        if not success:
            logger.warning(f"Failed to load trajectory {trajectory.id}")
            return None

        # Start the trajectory
        success = self.startTrajectory(trajectory.id)

        if not success:
            logger.warning(f"Failed to run trajectory {trajectory.id}")
            return None

        success = self.events.trajectory_started.wait(
            timeout=2,
            stale_event_time=0.2,
            flags={'trajectory_id': trajectory.id}
        )

        if not success:
            logger.warning(f"Failed to start trajectory {trajectory.id}")
            return None

        start_tick = self.events.trajectory_started.get_data()['tick']

        success = self.events.trajectory_finished.wait(
            timeout=trajectory.length * 0.01 + 2,
            stale_event_time=0.2,
            flags={'trajectory_id': trajectory.id}
        )

        if not success:
            logger.warning(f"Failed to finish trajectory {trajectory.id}")
            return None

        end_tick = self.events.trajectory_finished.get_data()['tick']

        if start_tick is None or end_tick is None:
            return None

        # Wait for the logger to reach the number of samples
        while self.logging.sample_index < (end_tick+100):
            time.sleep(0.1)

        output_signals = {}
        if signals is not None:
            output_signals = self.logging.getData(
                signals=signals,
                index_start=start_tick,
                index_end=end_tick
            )

        output_data = {
            'start_tick': start_tick,
            'end_tick': end_tick,
            'trajectory': trajectory,
            'output': output_signals
        }

        # Send the event via Wi-Fi
        self.communication.wifi.sendEvent(event='trajectory',
                                          data={
                                              'event': 'finished',
                                              'trajectory_id': trajectory.id,
                                              'input': [[float(inp.left), float(inp.right)] for inp in trajectory.inputs.values()],
                                              'output': output_signals,
                                          })

        return output_data

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self):
        sample = {}
        return sample

    # === PRIVATE METHODS ==============================================================================================
    def _setTrajectoryDescription_LL(self, trajectory: BILBO_Trajectory) -> bool:
        # Transform the trajectory into the corresponding ctypes structure

        sequence_description = bilbo_sequence_description_t(
            sequence_id=trajectory.id,
            length=trajectory.length,
            require_control_mode=False,
            wait_time_beginning=1,
            wait_time_end=1,
            control_mode=trajectory.control_mode.value,
            control_mode_end=trajectory.control_mode_end.value,
            loaded=False
        )

        # Send the trajectory to the STM32
        success = self.communication.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_SequencerAddresses.LOAD,
            data=sequence_description,
            input_type=bilbo_sequence_description_t,
            output_type=ctypes.c_bool,
            timeout=0.1
        )

        if not success:
            logger.warning(f'Failed to set trajectory description {trajectory.id}')
            return False
        else:
            ...
            # logger.debug(f'Trajectory description {trajectory.id} transferred')

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _startTrajectory_LL(self, trajectory_id) -> bool:
        self.running = True
        self.control.enable_external_input = False

        success = self.communication.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_SequencerAddresses.START,
            data=trajectory_id,
            input_type=ctypes.c_uint16,
            output_type=ctypes.c_bool,
            timeout=0.1
        )

        return success

    # ------------------------------------------------------------------------------------------------------------------
    def _stopTrajectory_LL(self) -> bool:
        success = self.communication.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_SequencerAddresses.STOP,
            data=None,
            input_type=None,
            output_type=None,
            timeout=0.1
        )

        return success

    # ------------------------------------------------------------------------------------------------------------------
    def _readTrajectoryDescription_LL(self) -> (BILBO_Sequence_LL, None):

        logger.debug("Get trajectory data")
        trajectory_data_struct = self.communication.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_SequencerAddresses.READ,
            data=None,
            input_type=None,
            output_type=bilbo_sequence_description_t,
            timeout=0.1
        )

        if trajectory_data_struct is None:
            logger.warning("Failed to get trajectory data")
            return None

        trajectory = from_dict(data=trajectory_data_struct, data_class=BILBO_Sequence_LL)

        return trajectory

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _trajectoryInputToBytes(trajectory_input: dict[int, BILBO_TrajectoryInput]) -> bytes:
        # Create a ctypes array type of the correct length

        ArrayType: Any = cast(Any, bilbo_sequence_input_t * len(trajectory_input))  # type: ignore
        c_array = ArrayType()  # Now this won't raise a warning

        # Populate the ctypes array with data from trajectory_input
        for i, inp in trajectory_input.items():
            c_array[i].step = inp.step
            c_array[i].u_1 = inp.left
            c_array[i].u_2 = inp.right

        # Get the byte representation of the array
        bytes_data = ctypes.string_at(ctypes.byref(c_array), ctypes.sizeof(c_array))
        return bytes_data

    # ------------------------------------------------------------------------------------------------------------------
    def _sendTrajectoryInputs_ll(self, trajectory: BILBO_Trajectory):
        trajectory_bytes = self._trajectoryInputToBytes(trajectory.inputs)
        self.communication.spi.sendTrajectoryData(trajectory.length, trajectory_bytes)

    # ------------------------------------------------------------------------------------------------------------------
    def _generateStep(self, gain, length):
        trajectory_input = {}

        for i in range(length):
            trajectory_input[i] = BILBO_TrajectoryInput(
                step=i,
                left=gain * 1.0,
                right=gain * 1.0
            )

        return trajectory_input

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _generateTrajectoryInputs(input_list: list):
        trajectory_inputs = {}

        for i, input in enumerate(input_list):
            if isinstance(input, list):
                input_left = float(input[0])
                input_right = float(input[1])
            else:
                input_left = float(input)
                input_right = float(input)

            trajectory_inputs[i] = BILBO_TrajectoryInput(
                step=i,
                left=input_left,
                right=input_right,
            )
        return trajectory_inputs

    # ------------------------------------------------------------------------------------------------------------------
    def _run_trajectory_external(self, trajectory_id, input, signals=None):
        print("Run Trajectory External")

        if signals is not None and not isinstance(signals, list):
            signals = [signals]


        trajectory = BILBO_Trajectory(
            id=trajectory_id,
            name='test',
            length=len(input),
            inputs=self._generateTrajectoryInputs(input),
            control_mode=BILBO_Control_Mode.BALANCING,
            control_mode_end=BILBO_Control_Mode.BALANCING
        )

        self.runTrajectory(trajectory, signals=signals)


    # ------------------------------------------------------------------------------------------------------------------
    def _sequencer_event_callback(self, message: BILBO_Sequencer_Event_Message, *args, **kwargs):
        event = BILBO_LL_Sequencer_Event_Type(message.data['event']).name
        trajectory_id = message.data['sequence_id']
        tick = message.data['tick']
        if event == 'STARTED':
            self.utils.speak(f"Trajectory {trajectory_id} started")
            logger.info(f"Trajectory {trajectory_id} started (Tick: {tick})")
            self.callbacks.trajectory_started.call(trajectory_id=trajectory_id, tick=tick)

            self.events.trajectory_started.set(resource={'tick': tick, 'trajectory_id': trajectory_id},
                                               flags={'trajectory_id': trajectory_id})

        elif event == 'FINISHED':
            self.utils.speak(f"Trajectory {trajectory_id} finished")
            logger.info(f"Trajectory {trajectory_id} finished (Tick: {tick})")

            self.callbacks.trajectory_finished.call(trajectory_id=trajectory_id, tick=tick)
            self.events.trajectory_finished.set(resource={'tick': tick, 'trajectory_id': trajectory_id},
                                                flags={'trajectory_id': trajectory_id})

            self.running = False
            self.control.enable_external_input = True

        elif event == 'RECEIVED':
            logger.debug(f"Trajectory {trajectory_id} loaded")
            self.callbacks.trajectory_loaded.call(trajectory_id=trajectory_id, tick=tick)
            self.events.trajectory_loaded.set(resource={'tick': tick, 'trajectory_id': trajectory_id},
                                              flags={'trajectory_id': trajectory_id})

        elif event == 'ABORTED':
            self.utils.speak(f"Trajectory {trajectory_id} aborted")
            logger.info(f"Trajectory {trajectory_id} aborted")

            self.callbacks.trajectory_aborted.call(trajectory_id=trajectory_id, tick=tick)
            self.events.trajectory_aborted.set(resource={'tick': tick, 'trajectory_id': trajectory_id},
                                               flags={'trajectory_id': trajectory_id})

            self.running = False
            self.control.enable_external_input = True
# ======================================================================================================================
