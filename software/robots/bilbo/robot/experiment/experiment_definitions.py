"""
Experiment Definitions for BILBO Robot

This module provides data structures for experiment results, trajectories,
and file I/O. Experiment definition and parsing is handled by the new
experiment framework in core.utils.experiments.

Status enums and action data types are imported from core.utils.experiments:
- ExperimentStatus, ActionStatus, ExperimentActionData
- ExperimentResult, ExperimentResultMeta

BILBO-specific result types are defined here:
- BILBO_ExperimentContext: Robot context captured at experiment start
- BILBO_ExperimentResult: Extends ExperimentResult with BILBO samples, context, logs

For action introspection and validation, see bilbo_actions.py which provides
host-side ActionBase stubs with parameter_defs, data_defs, and transition_ports
matching the on-robot actions.

For the old ExperimentDefinition, ExperimentBuilder, and helper functions,
see archive/experiment_definitions_old.py.
"""
from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np

from core.utils.dataclass_utils import from_dict_auto
from core.utils.experiments import (
    ExperimentStatus,
    ActionStatus,
    ExperimentActionData,
    ExperimentResult,
    ExperimentResultMeta,
)
from core.utils.files import file_exists
from core.utils.json_utils import writeJSON, readJSON
from robots.bilbo.robot.bilbo_data import BILBO_DynamicState, BILBO_Sample
from robots.bilbo.robot.bilbo_definitions import BILBO_CONTROL_DT, BILBO_Config, BILBO_ControlConfig


# ======================================================================================================================
# TRAJECTORIES
# ======================================================================================================================

@dataclasses.dataclass
class InputTrajectoryStep:
    step: int
    left: float
    right: float


@dataclasses.dataclass
class InputTrajectory:
    name: str  # Name of the trajectory
    id: int  # Numeric ID of the trajectory
    inputs: list[InputTrajectoryStep]
    dt: float = BILBO_CONTROL_DT  # Time step

    @property
    def length(self) -> int:
        return len(self.inputs)

    @property
    def time_vector(self) -> np.ndarray:
        return np.arange(0, self.length) * self.dt

    def to_vector(self, single_input: bool = False) -> np.ndarray:
        from robots.bilbo.robot.experiment.helpers import trajectory_inputs_to_vector
        return trajectory_inputs_to_vector(self.inputs, single_input=single_input)

    @classmethod
    def from_vector(cls, vector: np.ndarray, name: str, id: int, dt: float = None) -> InputTrajectory:
        from robots.bilbo.robot.experiment.helpers import generate_trajectory_inputs
        return cls(name=name, id=id, inputs=generate_trajectory_inputs(vector), dt=dt or BILBO_CONTROL_DT)

    def to_file_data(self, id: str = '', description: str = '') -> InputTrajectoryFileData:
        """Wrap this trajectory in an InputTrajectoryFileData for file I/O."""
        return InputTrajectoryFileData(
            id=id or self.name,
            description=description,
            trajectory=self,
        )


@dataclasses.dataclass
class StateTrajectory:
    states: list[BILBO_DynamicState]
    dt: float = BILBO_CONTROL_DT  # Time step

    @property
    def length(self) -> int:
        return len(self.states)

    @property
    def time_vector(self) -> np.ndarray:
        return np.arange(0, self.length) * self.dt


@dataclasses.dataclass
class TrajectoryData:
    input_trajectory: InputTrajectory
    state_trajectory: StateTrajectory

    @property
    def length(self) -> int:
        return self.input_trajectory.length

    @property
    def time_vector(self) -> np.ndarray:
        return self.input_trajectory.time_vector


@dataclasses.dataclass
class OutputTrajectory:
    output_name: str
    output: list[float]
    dt: float = BILBO_CONTROL_DT

    @property
    def length(self) -> int:
        return len(self.output)

    @property
    def time_vector(self) -> np.ndarray:
        return np.arange(0, self.length) * self.dt

    def to_array(self) -> np.ndarray:
        return np.asarray(self.output)

    def to_file_data(self, id: str = '', description: str = '') -> OutputTrajectoryFileData:
        """Wrap this trajectory in an OutputTrajectoryFileData for file I/O."""
        return OutputTrajectoryFileData(
            id=id or self.output_name,
            description=description,
            output_name=self.output_name,
            output=self.output,
            dt=self.dt,
        )


@dataclasses.dataclass
class ModelVector:
    """Impulse response model vector for DILC (Data-driven Iterative Learning Control).

    The m-vector represents the impulse response of the system. It can be
    converted to a lifted lower-triangular Toeplitz matrix (LTTM) via
    vec2liftedMatrix() for use in the ILC/IML learning updates.

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
        from core.utils.control_lib.lib_control.lifted_systems import vec2liftedMatrix
        return vec2liftedMatrix(self.to_array())

    @classmethod
    def from_vector(cls, vector: np.ndarray, name: str, id: int, dt: float = None) -> ModelVector:
        return cls(name=name, id=id, vector=vector.tolist(), dt=dt or BILBO_CONTROL_DT)

    @classmethod
    def from_lifted_matrix(cls, matrix: np.ndarray, name: str, id: int, dt: float = None) -> ModelVector:
        """Create a ModelVector from a lifted lower-triangular Toeplitz matrix."""
        from core.utils.control_lib.lib_control.lifted_systems import liftedMatrix2Vec
        vec = liftedMatrix2Vec(matrix)
        return cls.from_vector(vec, name=name, id=id, dt=dt)

    def to_file_data(self, id: str = '', description: str = '') -> ModelVectorFileData:
        """Wrap this model vector in a ModelVectorFileData for file I/O."""
        return ModelVectorFileData(
            id=id or self.name,
            description=description,
            vector=self.vector,
            dt=self.dt,
        )


# ======================================================================================================================
# TESTBED DATA (mirrors robots.bilbo.testbed.testbed to avoid circular imports)
# ======================================================================================================================

@dataclasses.dataclass
class TestbedSize:
    x_min: float = -2.0
    x_max: float = 2.0
    y_min: float = -2.0
    y_max: float = 2.0


@dataclasses.dataclass
class TestbedConfig:
    size: TestbedSize = dataclasses.field(default_factory=TestbedSize)
    id: str | None = None


@dataclasses.dataclass
class TestbedData:
    config: TestbedConfig | None = None
    obstacles: list | None = None
    lines: list | None = None
    points: list | None = None
    poses: list | None = None


# ======================================================================================================================
# BILBO EXPERIMENT CONTEXT & RESULT
# ======================================================================================================================

@dataclasses.dataclass
class BILBO_ExperimentContext:
    """Robot-specific context captured at experiment start.

    Mirrors the robot-side context so the host can deserialize experiment
    result files produced by the robot.
    """
    description: str = ''
    start_timecode: str | None = None
    control_config: BILBO_ControlConfig | None = None
    bilbo_config: BILBO_Config | None = None
    testbed_config: TestbedData | None = None


@dataclasses.dataclass
class BILBO_ExperimentResult(ExperimentResult):
    """BILBO-specific experiment result extending the core ExperimentResult.

    Adds robot samples, context, tick range, and logs on top of the generic
    ExperimentResult fields (id, status, definition, meta, action_data, etc.).
    """
    samples: list[BILBO_Sample] = dataclasses.field(default_factory=list)
    robot_context: BILBO_ExperimentContext = dataclasses.field(default_factory=BILBO_ExperimentContext)
    start_tick: int = 0
    end_tick: int = 0
    logs: list[dict] = dataclasses.field(default_factory=list)

    @property
    def time_vector(self) -> np.ndarray:
        """Get the time vector for this experiment's samples.

        Returns a numpy array of time values in seconds, starting from 0,
        with one entry per sample at the control loop rate (BILBO_CONTROL_DT = 0.01s = 100Hz).
        """
        return np.arange(len(self.samples)) * BILBO_CONTROL_DT

    @property
    def sample_duration(self) -> float:
        """Get the total duration of the experiment in seconds (from sample count)."""
        return len(self.samples) * BILBO_CONTROL_DT


# ======================================================================================================================
# TRAJECTORY FILE I/O
# ======================================================================================================================

INPUT_TRAJECTORY_FILE_EXTENSION = '.bitrj'
OUTPUT_TRAJECTORY_FILE_EXTENSION = '.botrj'
MODEL_VECTOR_FILE_EXTENSION = '.bmvec'


@dataclasses.dataclass
class InputTrajectoryFileData:
    id: str
    description: str
    trajectory: InputTrajectory

    @property
    def length(self) -> int:
        return self.trajectory.length

    def to_trajectory(self) -> InputTrajectory:
        """Extract the InputTrajectory."""
        return self.trajectory


@dataclasses.dataclass
class OutputTrajectoryFileData:
    id: str
    description: str
    output_name: str          # e.g. "theta"
    output: list[float]       # the trajectory values
    dt: float = BILBO_CONTROL_DT

    @property
    def length(self) -> int:
        return len(self.output)

    def to_array(self) -> np.ndarray:
        return np.asarray(self.output)

    def to_trajectory(self) -> OutputTrajectory:
        """Extract an OutputTrajectory (drops id/description metadata)."""
        return OutputTrajectory(
            output_name=self.output_name,
            output=self.output,
            dt=self.dt,
        )


def write_input_file(file_name, folder, data: InputTrajectoryFileData):
    data_dict = dataclasses.asdict(data)
    file_path = f"{folder}/{file_name}{INPUT_TRAJECTORY_FILE_EXTENSION}"
    try:
        writeJSON(file_path, data_dict)
    except Exception as e:
        print(f"Error writing input file: {e}")


def read_input_file(file) -> InputTrajectoryFileData | None:
    if not file_exists(file):
        raise FileNotFoundError(f"Input file not found: {file}")

    try:
        data_dict = readJSON(file)
        # Fast path: construct trajectory steps directly instead of going
        # through from_dict_auto, which does expensive per-element reflection
        # for the inputs list (can take 10+ seconds for ~300 steps).
        traj_dict = data_dict.get('trajectory', {})
        raw_inputs = traj_dict.get('inputs', [])
        steps = [InputTrajectoryStep(step=d['step'], left=d['left'], right=d['right'])
                 for d in raw_inputs]
        trajectory = InputTrajectory(
            name=traj_dict.get('name', ''),
            id=traj_dict.get('id', 0),
            inputs=steps,
            dt=traj_dict.get('dt', BILBO_CONTROL_DT),
        )
        return InputTrajectoryFileData(
            id=data_dict.get('id', ''),
            description=data_dict.get('description', ''),
            trajectory=trajectory,
        )
    except Exception as e:
        print(f"Error reading input file: {e}")
        return None


def write_output_file(file_path: str, data: OutputTrajectoryFileData):
    writeJSON(file_path, dataclasses.asdict(data))


def read_output_file(file_path: str) -> OutputTrajectoryFileData:
    if not file_exists(file_path):
        raise FileNotFoundError(f"Output trajectory file not found: {file_path}")
    data_dict = readJSON(file_path)
    return from_dict_auto(OutputTrajectoryFileData, data_dict)


@dataclasses.dataclass
class ModelVectorFileData:
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
        from core.utils.control_lib.lib_control.lifted_systems import vec2liftedMatrix
        return vec2liftedMatrix(self.to_array())

    def to_model_vector(self, name: str = '', model_id: int = 0) -> ModelVector:
        """Extract a ModelVector (drops file metadata)."""
        return ModelVector(
            name=name or self.id,
            id=model_id,
            vector=self.vector,
            dt=self.dt,
        )


def write_model_vector_file(file_path: str, data: ModelVectorFileData):
    writeJSON(file_path, dataclasses.asdict(data))


def read_model_vector_file(file_path: str) -> ModelVectorFileData:
    if not file_exists(file_path):
        raise FileNotFoundError(f"Model vector file not found: {file_path}")
    data_dict = readJSON(file_path)
    return from_dict_auto(ModelVectorFileData, data_dict)
