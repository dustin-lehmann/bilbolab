# ======================================================================================================================
from __future__ import annotations
import dataclasses
import enum
import time

from scipy.fft import rfft, rfftfreq
from scipy.signal import find_peaks
import numpy as np

from core.utils.dataclass_utils import from_dict_auto
from core.utils.files import file_exists
from core.utils.json_utils import writeJSON, readJSON
from robot.bilbo_common import BILBO_Config
from robot.bilbo_definitions import BILBO_DynamicState
from robot.control.bilbo_control_definitions import BILBO_Control_Mode, BILBO_ControlConfig
from robot.experiment.helpers import generate_trajectory_inputs
from robot.lowlevel.stm32_general import BILBO_CONTROL_DT


# ======================================================================================================================
# LOW LEVEL
# ======================================================================================================================
class BILBO_LL_Sequencer_Event_Type(enum.IntEnum):
    STARTED = 1
    FINISHED = 2
    ABORTED = 3
    RECEIVED = 4


# ======================================================================================================================
# EXPERIMENT
# ======================================================================================================================


# === TRAJECTORIES =====================================================================================================
@dataclasses.dataclass
class BILBO_InputTrajectoryStep:
    step: int
    left: float
    right: float


@dataclasses.dataclass
class BILBO_InputTrajectory:
    name: str  # Name of the trajectory
    id: int  # Numeric ID of the trajectory
    inputs: list[BILBO_InputTrajectoryStep]
    dt: float = BILBO_CONTROL_DT  # Time step

    @property
    def length(self) -> int:
        return len(self.inputs)

    @property
    def time_vector(self) -> np.ndarray:
        return np.arange(0, self.length) * self.dt

    def to_vector(self, single_input: bool = False) -> np.ndarray:
        from robot.experiment.helpers import trajectory_inputs_to_vector

        return trajectory_inputs_to_vector(self.inputs, single_input=single_input)

    @classmethod
    def from_vector(cls, vector: np.ndarray, name: str, id: int, dt: float = None, delta: float = 0.0) -> BILBO_InputTrajectory:
        return cls(name=name, id=id, inputs=generate_trajectory_inputs(vector, delta=delta), dt=dt or BILBO_CONTROL_DT)

    @classmethod
    def from_file(cls, file):
        ...

    def to_file(self, file):
        ...


@dataclasses.dataclass
class BILBO_StateTrajectory:
    states: list[BILBO_DynamicState]
    dt: float = BILBO_CONTROL_DT  # Time step

    @property
    def length(self) -> int:
        return len(self.states)

    @property
    def time_vector(self) -> np.ndarray:
        return np.arange(0, self.length) * self.dt


@dataclasses.dataclass
class BILBO_TrajectoryData:
    input_trajectory: BILBO_InputTrajectory
    state_trajectory: BILBO_StateTrajectory

    @property
    def length(self) -> int:
        return self.input_trajectory.length

    @property
    def time_vector(self) -> np.ndarray:
        return self.input_trajectory.time_vector


@dataclasses.dataclass
class BILBO_OutputTrajectory:
    output_name: str
    output: list[float]
    dt: float = BILBO_CONTROL_DT

    @property
    def length(self) -> int:
        return len(self.output)

    @property
    def time_vector(self) -> np.ndarray:
        return np.arange(0, self.length) * self.dt


@dataclasses.dataclass
class BILBO_ModelVector:
    """Impulse response model vector for DILC (Data-driven Iterative Learning Control).

    The m-vector represents the impulse response of the system. It can be
    converted to a lifted lower-triangular Toeplitz matrix (LTTM) via
    vector_to_lifted_matrix() for use in the ILC/IML learning updates.

    Attributes:
        name: Human-readable name for this model vector.
        id: Numeric identifier.
        vector: The impulse response values as a list of floats.
        dt: Sampling period in seconds.
    """
    name: str
    id: int
    vector: list[float]
    dt: float = BILBO_CONTROL_DT

    @property
    def length(self) -> int:
        return len(self.vector)

    @property
    def time_vector(self) -> np.ndarray:
        return np.arange(0, self.length) * self.dt

    def to_array(self) -> np.ndarray:
        return np.asarray(self.vector)

    def to_lifted_matrix(self) -> np.ndarray:
        """Convert the m-vector to a lifted lower-triangular Toeplitz matrix."""
        from core.utils.control_lib.lib_control.learning.lifted import vector_to_lifted_matrix
        return vector_to_lifted_matrix(self.to_array())

    @classmethod
    def from_vector(cls, vector: np.ndarray, name: str, id: int, dt: float = None) -> BILBO_ModelVector:
        return cls(name=name, id=id, vector=vector.tolist(), dt=dt or BILBO_CONTROL_DT)

    @classmethod
    def from_lifted_matrix(cls, matrix: np.ndarray, name: str, id: int, dt: float = None) -> BILBO_ModelVector:
        """Create a BILBO_ModelVector from a lifted lower-triangular Toeplitz matrix."""
        from core.utils.control_lib.lib_control.learning.lifted import lifted_matrix_to_vector
        vec = lifted_matrix_to_vector(matrix)
        return cls.from_vector(vec, name=name, id=id, dt=dt)


# === EXPERIMENTS ======================================================================================================
@dataclasses.dataclass
class BILBO_TrajectoryExperimentMeta:
    robot_id: str
    description: str
    time_stamp: str
    robot_config: BILBO_Config
    control_config: BILBO_ControlConfig
    start_tick: int
    end_tick: int


@dataclasses.dataclass
class BILBO_TrajectoryExperimentData:
    id: str
    meta: BILBO_TrajectoryExperimentMeta
    data: BILBO_TrajectoryData


# === FILES ============================================================================================================
INPUT_TRAJECTORY_FILE_EXTENSION = '.bitrj'
MODEL_VECTOR_FILE_EXTENSION = '.bmvec'


@dataclasses.dataclass
class BILBO_InputFileData:
    id: str
    description: str
    trajectory: BILBO_InputTrajectory

    @property
    def length(self) -> int:
        return self.trajectory.length


def write_input_file(file_name, folder, data: BILBO_InputFileData):
    data_dict = dataclasses.asdict(data)
    file_path = f"{folder}/{file_name}{INPUT_TRAJECTORY_FILE_EXTENSION}"
    try:
        writeJSON(file_path, data_dict)
    except Exception as e:
        print(f"Error writing input file: {e}")


def read_input_file(file) -> BILBO_InputFileData | None:
    if not file_exists(file):
        raise FileNotFoundError(f"Input file not found: {file}")

    try:
        data_dict = readJSON(file)
        data = from_dict_auto(BILBO_InputFileData, data_dict)
        return data
    except Exception as e:
        print(f"Error reading input file: {e}")
        return None


@dataclasses.dataclass
class BILBO_ModelVectorFileData:
    """File data wrapper for a DILC model vector (impulse response).

    Attributes:
        id: Identifier for this model vector (e.g. experiment ID).
        description: Human-readable description.
        vector: The impulse response values.
        dt: Sampling period in seconds.
    """
    id: str
    description: str
    vector: list[float]
    dt: float = BILBO_CONTROL_DT

    @property
    def length(self) -> int:
        return len(self.vector)

    def to_array(self) -> np.ndarray:
        return np.asarray(self.vector)

    def to_lifted_matrix(self) -> np.ndarray:
        """Convert the stored m-vector to a lifted lower-triangular Toeplitz matrix."""
        from core.utils.control_lib.lib_control.learning.lifted import vector_to_lifted_matrix
        return vector_to_lifted_matrix(self.to_array())

    def to_model_vector(self, name: str = '', model_id: int = 0) -> BILBO_ModelVector:
        """Extract a BILBO_ModelVector (drops file metadata)."""
        return BILBO_ModelVector(
            name=name or self.id,
            id=model_id,
            vector=self.vector,
            dt=self.dt,
        )


def write_model_vector_file(file_name, folder, data: BILBO_ModelVectorFileData):
    data_dict = dataclasses.asdict(data)
    file_path = f"{folder}/{file_name}{MODEL_VECTOR_FILE_EXTENSION}"
    try:
        writeJSON(file_path, data_dict)
    except Exception as e:
        print(f"Error writing model vector file: {e}")


def read_model_vector_file(file) -> BILBO_ModelVectorFileData | None:
    if not file_exists(file):
        raise FileNotFoundError(f"Model vector file not found: {file}")

    try:
        data_dict = readJSON(file)
        data = from_dict_auto(BILBO_ModelVectorFileData, data_dict)
        return data
    except Exception as e:
        print(f"Error reading model vector file: {e}")
        return None


@dataclasses.dataclass(kw_only=True, frozen=True)
class ExperimentSample:
    id: str = ""
    tick: int = -1
    actions: list[str] = dataclasses.field(default_factory=lambda: [""])


@dataclasses.dataclass
class BILBO_ExperimentHandler_Sample:
    status: str = ""
    markers_json: str = ''
    experiment: ExperimentSample = dataclasses.field(default_factory=ExperimentSample)
    experiment_id: str = ""
    trajectory_id: str = ""
