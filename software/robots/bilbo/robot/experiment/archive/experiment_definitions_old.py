"""
Experiment Definitions for BILBO Robot

This file defines the experiment action types and experiment definition structures.
It is designed to be kept in sync with the robot software implementation at:
  robots/bilbo/software/BILBO-Software/robot/experiment/bilbo_experiment.py

The host software uses these definitions to construct and serialize experiments,
which are then sent to the robot for execution.

For action introspection and validation using the new experiment framework, see
bilbo_actions.py which provides host-side ActionBase stubs with parameter_defs,
data_defs, and transition_ports matching the on-robot actions.
"""
from __future__ import annotations

import copy
import dataclasses
import enum
import json
import re
from typing import Any

import numpy as np
import yaml

from core.utils.dataclass_utils import from_dict_auto
from core.utils.files import file_exists
from core.utils.json_utils import writeJSON, readJSON
from robots.bilbo.robot.bilbo_data import BILBO_DynamicState, BILBO_Sample
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_CONTROL_DT, BILBO_Config, BILBO_ControlConfig


# ======================================================================================================================
# STATUS ENUMS
# ======================================================================================================================

class ExperimentStatus(enum.StrEnum):
    """Status of an experiment after completion."""
    FINISHED = 'finished'       # Completed successfully
    ERROR = 'error'             # Aborted due to action error
    TIMEOUT = 'timeout'         # Aborted due to experiment timeout
    ABORTED = 'aborted'         # Aborted by external request


class ExperimentActionStatus(enum.StrEnum):
    """Status of an individual action."""
    PENDING = 'pending'         # Not yet started
    RUNNING = 'running'         # Currently executing
    FINISHED = 'finished'       # Completed successfully
    ERROR = 'error'             # Failed with error
    TIMEOUT = 'timeout'         # Timed out
    SKIPPED = 'skipped'         # Skipped due to experiment abort



# ======================================================================================================================
# EXPERIMENT REQUIREMENTS
# ======================================================================================================================

@dataclasses.dataclass
class StateRangeRequirement:
    """Requirement that a dynamic state field falls within a range."""
    state: str                    # Field name on BILBO_DynamicState (x, y, v, theta, theta_dot, psi, psi_dot)
    min: float | None = None
    max: float | None = None


@dataclasses.dataclass
class ExperimentRequirements:
    """Optional preconditions checked before an experiment starts."""
    optitrack: bool | None = None
    robot_id: str | list[str] | None = None      # str (exact or regex), or list of str/regex
    control_mode: str | None = None               # e.g. "OFF", "BALANCING"
    control_config: str | None = None             # Control config name
    state_ranges: list[StateRangeRequirement] | None = None


_VAR_PATTERN = re.compile(r'\$\{(\w+)\}')


def _substitute_variables(obj: Any, variables: dict[str, Any]) -> Any:
    """Recursively substitute ${variable} placeholders in a data structure.

    If a string is exactly "${var}", returns the variable's value preserving its
    original type (e.g. float stays float). If "${var}" is embedded in a larger
    string, it is interpolated as a string. Dicts and lists are recursively
    processed (copies are created; the original is not mutated).
    """
    if isinstance(obj, str):
        # Full-string match: preserve type
        m = _VAR_PATTERN.fullmatch(obj)
        if m and m.group(1) in variables:
            return variables[m.group(1)]
        # Partial substitution: interpolate as string
        def _replacer(match):
            name = match.group(1)
            return str(variables[name]) if name in variables else match.group(0)
        return _VAR_PATTERN.sub(_replacer, obj)
    if isinstance(obj, dict):
        return {k: _substitute_variables(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_variables(item, variables) for item in obj]
    return obj


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
# ACTION TYPES
# ======================================================================================================================

ALLOWED_ACTIONS: list[str] = [
    "beep", "set_mode", "set_tic", "set_psi_control", "set_tracker_updates", "speak", "set_marker", "run_trajectory",
    "wait_time", "wait_ticks", "wait_until_tick", "wait_event", "set_input",
    "set_velocity", "enable_external_input", "reset", "parallel", "group",
    "loop", "func", "set_feedback_gain", "reset_control",
    # Position control actions
    "move_to", "turn_to", "follow_path", "stop_path",
    "wait_position_event"
]


# ======================================================================================================================
# EXPERIMENT ACTION DEFINITION
# ======================================================================================================================

@dataclasses.dataclass
class ExperimentActionDefinition:
    """Definition of a single experiment action.

    This class represents an action that can be executed during an experiment.
    Actions can be scheduled by tick, time, or dependency (after another action).

    Example YAML:
        - type: beep
          frequency: 1000
          time_ms: 250

        - type: set_mode
          mode: BALANCING
          after: action_0
          label: "Start balancing"

        - type: group
          id: my_group
          label: "Velocity test sequence"
          actions:
            - type: set_mode
              mode: VELOCITY
            - type: set_velocity
              forward: 0.5
              turn: 0
            - type: wait_time
              time: 2.0
    """
    id: str
    type: str

    # Scheduling info (exactly one of these may be set)
    tick: int | None = None  # Absolute experiment tick
    after: str | None = None  # ID of action that must finish first
    time: float | None = None  # Absolute time [s] since experiment start

    timeout: float | None = None  # Per-action timeout (seconds, optional)

    label: str | None = None  # Human-readable label for display in reports

    meta: dict[str, Any] | None = None  # Optional metadata for reports/analysis (e.g., label_layer)

    wait_before: Any | None = None  # Wait before executing (supports "2s", "500ms", float, int ms)
    wait_after: Any | None = None   # Wait after executing (supports "2s", "500ms", float, int ms)

    # Action-specific parameters
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)

    # Sub-actions for group/parallel actions (maps action ID to definition)
    sub_actions: dict[str, 'ExperimentActionDefinition'] | None = None

    def __post_init__(self):
        if self.type not in ALLOWED_ACTIONS:
            raise ValueError(f"Action type '{self.type}' not allowed. Allowed actions: {ALLOWED_ACTIONS}")

    @classmethod
    def from_dict(cls, d: dict, index: int = 0, parent_id: str | None = None) -> "ExperimentActionDefinition":
        """
        Parse an action definition from a dict.

        Args:
            d: Dict containing action definition. Must have 'type' field.
               'id' is optional - auto-generated as 'action_{index}' if missing.
            index: Index for auto-generating ID when not provided.
            parent_id: Parent action ID for generating sub-action IDs.

        Returns:
            ExperimentActionDefinition instance.

        Raises:
            ValueError: If 'type' field is missing.
        """
        if "type" not in d:
            raise ValueError(f"Action at index {index} missing required field 'type': {d}")

        # id is optional - auto-generate if missing
        if parent_id:
            action_id = d.get("id", f"{parent_id}_sub_{index}")
        else:
            action_id = d.get("id", f"action_{index}")

        action_type = d["type"]

        # Reserved fields that should not go into parameters
        reserved_fields = {"id", "type", "tick", "after", "time", "timeout", "label", "meta", "parameters", "actions", "wait_before", "wait_after"}

        # If 'parameters' is explicitly provided, use it; otherwise collect non-reserved fields
        if "parameters" in d:
            parameters = dict(d["parameters"])  # Make a copy
        else:
            parameters = {
                k: v for k, v in d.items()
                if k not in reserved_fields
            }

        # --- Loop expansion: convert loop into nested groups at parse time ---
        if action_type == "loop":
            actions_list = parameters.pop("actions", None) or d.get("actions", [])
            variable = parameters.pop("variable", None)
            loop_count = parameters.pop("count", None)
            loop_values = parameters.pop("values", None)
            loop_range = parameters.pop("range", None)

            # Determine iteration values
            if loop_values is not None:
                iteration_values = list(loop_values)
            elif loop_range is not None:
                if isinstance(loop_range, int):
                    iteration_values = list(range(loop_range))
                elif isinstance(loop_range, list):
                    iteration_values = list(range(*loop_range))
                else:
                    raise ValueError(f"Invalid loop range: {loop_range}")
            elif loop_count is not None:
                iteration_values = list(range(int(loop_count)))
            else:
                raise ValueError("Loop action requires one of: count, values, or range")

            if variable is None:
                variable = "_index"

            # Extract loop label/meta settings for iteration wrappers
            loop_meta = d.get("meta") or {}
            loop_labels_template = loop_meta.get("loop_labels")
            loop_labels_layer = loop_meta.get("loop_labels_layer")

            # Build iteration groups
            iter_groups = []
            for i, val in enumerate(iteration_values):
                variables = {variable: val, "_index": i}
                iter_actions = _substitute_variables(copy.deepcopy(actions_list), variables)
                iter_meta = {"original_type": "loop_iteration"}
                # Apply iteration label from meta template if provided
                if loop_labels_template is not None:
                    iter_meta["label_layer"] = loop_labels_layer if loop_labels_layer is not None else 0
                iter_group = {
                    "type": "group",
                    "id": f"{action_id}_iter_{i}",
                    "meta": iter_meta,
                    "actions": iter_actions,
                }
                if loop_labels_template is not None:
                    iter_group["label"] = _substitute_variables(loop_labels_template, variables)
                iter_groups.append(iter_group)

            # Build outer group that wraps all iterations
            # Strip loop_labels/loop_labels_layer from meta before passing to outer group
            outer_meta = {k: v for k, v in loop_meta.items() if k not in ("loop_labels", "loop_labels_layer")}
            outer_meta["original_type"] = "loop"
            outer_group = {
                "type": "group",
                "id": action_id,
                "meta": outer_meta,
                "actions": iter_groups,
            }
            if d.get("label") is not None:
                outer_group["label"] = d["label"]
            # Carry over scheduling fields
            for field in ("tick", "after", "time", "timeout", "wait_before", "wait_after"):
                if d.get(field) is not None:
                    outer_group[field] = d[field]

            return cls.from_dict(outer_group, index=index, parent_id=parent_id)

        # Parse sub-actions for group/parallel types
        sub_actions: dict[str, ExperimentActionDefinition] | None = None
        if action_type in ("group", "parallel"):
            # Get actions list from parameters or top-level 'actions' field
            actions_list = parameters.pop("actions", None) or d.get("actions", [])
            if actions_list:
                sub_actions = {}
                for i, sub_def in enumerate(actions_list):
                    # Recursively parse sub-action
                    sub_action = cls.from_dict(sub_def, index=i, parent_id=action_id)
                    sub_actions[sub_action.id] = sub_action

        return cls(
            id=action_id,
            type=action_type,
            tick=d.get("tick"),
            after=d.get("after"),
            time=d.get("time"),
            timeout=d.get("timeout"),
            label=d.get("label"),
            meta=d.get("meta"),
            wait_before=d.get("wait_before"),
            wait_after=d.get("wait_after"),
            parameters=parameters,
            sub_actions=sub_actions,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        dict_out: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
        }
        if self.tick is not None:
            dict_out["tick"] = self.tick
        if self.after is not None:
            dict_out["after"] = self.after
        if self.time is not None:
            dict_out["time"] = self.time
        if self.timeout is not None:
            dict_out["timeout"] = self.timeout
        if self.label is not None:
            dict_out["label"] = self.label
        if self.meta is not None:
            dict_out["meta"] = self.meta
        if self.wait_before is not None:
            dict_out["wait_before"] = self.wait_before
        if self.wait_after is not None:
            dict_out["wait_after"] = self.wait_after
        if self.parameters:
            dict_out["parameters"] = self.parameters
        if self.sub_actions:
            # Serialize sub-actions as a list (preserving order by ID)
            dict_out["actions"] = [sub.to_dict() for sub in self.sub_actions.values()]
        return dict_out


# ======================================================================================================================
# EXPERIMENT DEFINITION
# ======================================================================================================================

def _parse_requirements(data: dict) -> ExperimentRequirements:
    """Parse an ExperimentRequirements from a dict."""
    state_ranges = None
    if "state_ranges" in data:
        state_ranges = [
            from_dict_auto(StateRangeRequirement, sr) for sr in data["state_ranges"]
        ]
    return ExperimentRequirements(
        optitrack=data.get("optitrack"),
        robot_id=data.get("robot_id"),
        control_mode=data.get("control_mode"),
        control_config=data.get("control_config"),
        state_ranges=state_ranges,
    )


@dataclasses.dataclass(kw_only=True)
class ExperimentDefinition:
    """Definition of an experiment.

    An experiment consists of:
    - id: Unique identifier
    - description: Human-readable description
    - actions: List of actions to execute
    - timeout: Optional experiment timeout in seconds
    - label: Optional human-readable label (displayed on testbed display; falls back to id)

    Example YAML:
        id: balance_test
        label: Balance Test
        description: Test balancing control
        timeout: 30.0
        actions:
          - type: speak
            text: "Starting test"
          - type: wait_time
            time: 1.0
          - type: set_mode
            mode: BALANCING
          - type: wait_time
            time: 10.0
          - type: set_mode
            mode: OFF
    """
    id: str
    description: str
    actions: list[ExperimentActionDefinition]
    timeout: float | None = None
    label: str | None = None  # Optional human-readable label (displayed on testbed display; falls back to id)
    requirements: ExperimentRequirements | None = None  # Optional preconditions checked before experiment starts
    source_dict: dict | None = None  # Original definition dict before parsing/expansion (preserved for report YAML)

    @classmethod
    def from_dict(cls, data: dict) -> "ExperimentDefinition":
        """Parse an experiment definition from a dict.

        Supports list-based actions format with:
        - Auto-generated IDs (action_0, action_1, etc.)
        - Implicit sequential chaining (actions run after the previous one by default)
        - Delay field for relative timing
        - Parallel action groups
        """
        if "id" not in data:
            raise ValueError("Experiment definition requires an 'id'")
        if "description" not in data:
            raise ValueError("Experiment definition requires a 'description'")
        if "actions" not in data:
            raise ValueError("Experiment definition requires 'actions'")

        raw_actions = data["actions"]

        if not isinstance(raw_actions, list):
            raise TypeError("'actions' must be a list")

        # Parse actions with auto-ID generation
        actions = [
            ExperimentActionDefinition.from_dict(a, index=i)
            for i, a in enumerate(raw_actions)
        ]

        # Parse requirements
        requirements = None
        if "requirements" in data:
            requirements = _parse_requirements(data["requirements"])

        return cls(
            id=data["id"],
            description=data["description"],
            actions=actions,
            timeout=data.get("timeout"),
            label=data.get("label"),
            requirements=requirements,
            source_dict=copy.deepcopy(data),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ExperimentDefinition":
        """Parse from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_file(cls, file: str) -> "ExperimentDefinition":
        """Load from YAML or JSON file."""
        if not file_exists(file):
            raise FileNotFoundError(f"Experiment definition file not found: {file}")

        with open(file, "r") as f:
            if file.lower().endswith((".yml", ".yaml")):
                data_dict = yaml.safe_load(f)
            else:
                data_dict = json.load(f)

        return cls.from_dict(data_dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns the original source dict if available (preserves loop syntax),
        otherwise builds from the expanded actions.
        """
        if self.source_dict is not None:
            return {k: v for k, v in self.source_dict.items() if k != 'source_dict'}
        d = {
            "id": self.id,
            "description": self.description,
            "timeout": self.timeout,
            "actions": [a.to_dict() for a in self.actions],
        }
        if self.label is not None:
            d["label"] = self.label
        if self.requirements is not None:
            d["requirements"] = self.requirements_to_dict()
        return d

    def requirements_to_dict(self) -> dict[str, Any] | None:
        """Serialize requirements to a dict, omitting None fields."""
        if self.requirements is None:
            return None
        d: dict[str, Any] = {}
        if self.requirements.optitrack is not None:
            d["optitrack"] = self.requirements.optitrack
        if self.requirements.robot_id is not None:
            d["robot_id"] = self.requirements.robot_id
        if self.requirements.control_mode is not None:
            d["control_mode"] = self.requirements.control_mode
        if self.requirements.control_config is not None:
            d["control_config"] = self.requirements.control_config
        if self.requirements.state_ranges is not None:
            d["state_ranges"] = [
                {k: v for k, v in dataclasses.asdict(sr).items() if v is not None}
                for sr in self.requirements.state_ranges
            ]
        return d

    def to_yaml(self) -> str:
        """Convert to YAML string."""
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save_to_file(self, file: str) -> None:
        """Save to YAML or JSON file based on extension."""
        with open(file, "w") as f:
            if file.lower().endswith((".yml", ".yaml")):
                yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)
            else:
                json.dump(self.to_dict(), f, indent=2)


# ======================================================================================================================
# EXPERIMENT DATA STRUCTURES
# ======================================================================================================================

@dataclasses.dataclass
class ExperimentActionData:
    """Data collected during action execution."""
    start_tick: int = 0
    end_tick: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    status: ExperimentActionStatus | str = ExperimentActionStatus.PENDING
    error_message: str | None = None
    action_type: str | None = None  # Action type (e.g., 'set_velocity', 'wait_time')
    label: str | None = None  # Human-readable label for display in reports
    meta: dict[str, Any] | None = None  # Optional metadata from action definition (e.g., label_layer)
    parameters: dict[str, Any] | None = None  # Action input parameters
    data: Any | None = None  # Action output data
    sub_actions: dict[str, ExperimentActionData] | None = None  # For group/parallel actions

    def __post_init__(self):
        # Convert string status to enum if needed
        if isinstance(self.status, str):
            try:
                self.status = ExperimentActionStatus(self.status)
            except ValueError:
                pass  # Keep as string if not a valid enum value


@dataclasses.dataclass
class TestbedSize:
    """Testbed physical dimensions."""
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclasses.dataclass
class TestbedConfig:
    """Testbed configuration."""
    size: TestbedSize


@dataclasses.dataclass
class TestbedData:
    """Testbed data captured during experiment."""
    config: TestbedConfig | None = None


@dataclasses.dataclass(frozen=True)
class ExperimentMetaData:
    """Metadata about an experiment execution."""
    description: str
    start_timecode: str | None
    date: str
    control_config: BILBO_ControlConfig
    bilbo_config: BILBO_Config
    testbed: TestbedData


@dataclasses.dataclass(frozen=False)
class ExperimentData:
    """Complete experiment data including samples and action data."""
    id: str
    status: ExperimentStatus | str = ExperimentStatus.FINISHED
    meta: ExperimentMetaData = None
    definition: ExperimentDefinition = None
    samples: list[BILBO_Sample] = dataclasses.field(default_factory=list)
    actions: dict[str, ExperimentActionData] = dataclasses.field(default_factory=dict)
    error_action_id: str | None = None  # ID of action that caused error (if status is ERROR)
    error_message: str | None = None    # Human-readable error description
    logs: list[dict] = dataclasses.field(default_factory=list)

    def __post_init__(self):
        # Convert string status to enum if needed
        if isinstance(self.status, str):
            try:
                self.status = ExperimentStatus(self.status)
            except ValueError:
                pass  # Keep as string if not a valid enum value

    @property
    def time_vector(self) -> np.ndarray:
        """Get the time vector for this experiment's samples.

        Returns a numpy array of time values in seconds, starting from 0,
        with one entry per sample at the control loop rate (BILBO_CONTROL_DT = 0.01s = 100Hz).

        Example:
            t = experiment_data.time_vector
            plt.plot(t, theta)
        """
        return np.arange(len(self.samples)) * BILBO_CONTROL_DT

    @property
    def duration(self) -> float:
        """Get the total duration of the experiment in seconds."""
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


# ======================================================================================================================
# HELPER FUNCTIONS FOR BUILDING EXPERIMENTS
# ======================================================================================================================

def beep(frequency: int = 1000, time_ms: int = 250, repeats: int = 1, **scheduling) -> ExperimentActionDefinition:
    """Create a beep action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "beep"),
        type="beep",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"frequency": frequency, "time_ms": time_ms, "repeats": repeats}
    )


def set_mode(mode: str | BILBO_Control_Mode, **scheduling) -> ExperimentActionDefinition:
    """Create a set_mode action."""
    mode_str = mode.name if isinstance(mode, BILBO_Control_Mode) else mode
    return ExperimentActionDefinition(
        id=scheduling.get("id", "set_mode"),
        type="set_mode",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"mode": mode_str}
    )


def speak(text: str, **scheduling) -> ExperimentActionDefinition:
    """Create a speak action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "speak"),
        type="speak",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"text": text}
    )


def wait_time(time_s: float = 0, **scheduling) -> ExperimentActionDefinition:
    """Create a wait_time action. Time is in seconds."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "wait_time"),
        type="wait_time",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"time": float(time_s)}
    )


def wait_ticks(ticks: int, **scheduling) -> ExperimentActionDefinition:
    """Create a wait_ticks action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "wait_ticks"),
        type="wait_ticks",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"ticks": ticks}
    )


def set_velocity(forward: float = 0.0, turn: float = 0.0, normalized: bool = False, **scheduling) -> ExperimentActionDefinition:
    """Create a set_velocity action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "set_velocity"),
        type="set_velocity",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"forward": forward, "turn": turn, "normalized": normalized}
    )


def set_input(input: list[float], normalized: bool = False, **scheduling) -> ExperimentActionDefinition:
    """Create a set_input action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "set_input"),
        type="set_input",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"input": input, "normalized": normalized}
    )


def run_trajectory(trajectory: InputTrajectory | dict | str, **scheduling) -> ExperimentActionDefinition:
    """Create a run_trajectory action."""
    # Convert trajectory to dict if it's a dataclass
    if isinstance(trajectory, InputTrajectory):
        trajectory = dataclasses.asdict(trajectory)
    return ExperimentActionDefinition(
        id=scheduling.get("id", "run_trajectory"),
        type="run_trajectory",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"input_trajectory": trajectory}
    )


def set_marker(marker_id: str, marker_value: str, **scheduling) -> ExperimentActionDefinition:
    """Create a set_marker action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "set_marker"),
        type="set_marker",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"marker_id": marker_id, "marker_value": marker_value}
    )


def enable_external_input(enabled: bool = True, **scheduling) -> ExperimentActionDefinition:
    """Create an enable_external_input action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "enable_external_input"),
        type="enable_external_input",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"enabled": enabled}
    )


def reset(**scheduling) -> ExperimentActionDefinition:
    """Create a reset action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "reset"),
        type="reset",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={}
    )


def parallel(actions: list[ExperimentActionDefinition | dict], **scheduling) -> ExperimentActionDefinition:
    """Create a parallel action that runs multiple actions simultaneously."""
    parent_id = scheduling.get("id", "parallel")
    sub_actions_dict: dict[str, ExperimentActionDefinition] = {}
    for i, a in enumerate(actions):
        if isinstance(a, ExperimentActionDefinition):
            sub_action = a
        else:
            sub_action = ExperimentActionDefinition.from_dict(a, index=i, parent_id=parent_id)
        sub_actions_dict[sub_action.id] = sub_action
    return ExperimentActionDefinition(
        id=parent_id,
        type="parallel",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        label=scheduling.get("label"),
        parameters={},
        sub_actions=sub_actions_dict if sub_actions_dict else None,
    )


def group(actions: list[ExperimentActionDefinition | dict], **scheduling) -> ExperimentActionDefinition:
    """Create a group action that runs multiple actions sequentially.

    Groups are useful for organizing related actions together and tracking
    their collective start and end times for later data extraction.

    Args:
        actions: List of actions to execute sequentially within the group
    """
    parent_id = scheduling.get("id", "group")
    sub_actions_dict: dict[str, ExperimentActionDefinition] = {}
    for i, a in enumerate(actions):
        if isinstance(a, ExperimentActionDefinition):
            sub_action = a
        else:
            sub_action = ExperimentActionDefinition.from_dict(a, index=i, parent_id=parent_id)
        sub_actions_dict[sub_action.id] = sub_action
    return ExperimentActionDefinition(
        id=parent_id,
        type="group",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        label=scheduling.get("label"),
        parameters={},
        sub_actions=sub_actions_dict if sub_actions_dict else None,
    )


def loop(actions: list[ExperimentActionDefinition | dict], count: int | None = None,
         variable: str | None = None, values: list | None = None,
         loop_range: list | int | None = None, **scheduling) -> ExperimentActionDefinition:
    """Create a loop action that repeats a block of actions.

    The loop is expanded into nested groups at parse time. Supports three modes:
    - count: repeat N times
    - values: iterate over an explicit list
    - loop_range: iterate over range(start, end[, step])

    Args:
        actions: List of actions to repeat each iteration
        count: Number of iterations (simple repeat)
        variable: Loop variable name for substitution (default: '_index')
        values: Explicit list of values to iterate over
        loop_range: Range specification: int, [end], [start, end], or [start, end, step]
    """
    # Convert ExperimentActionDefinition instances to dicts for the loop expansion
    action_dicts = []
    for a in actions:
        if isinstance(a, ExperimentActionDefinition):
            action_dicts.append(a.to_dict())
        else:
            action_dicts.append(a)

    loop_dict: dict[str, Any] = {
        "type": "loop",
        "id": scheduling.get("id", "loop"),
        "actions": action_dicts,
    }
    if count is not None:
        loop_dict["count"] = count
    if variable is not None:
        loop_dict["variable"] = variable
    if values is not None:
        loop_dict["values"] = values
    if loop_range is not None:
        loop_dict["range"] = loop_range

    # Carry over scheduling fields
    for field in ("tick", "after", "time", "timeout", "label", "wait_before", "wait_after"):
        if scheduling.get(field) is not None:
            loop_dict[field] = scheduling[field]

    return ExperimentActionDefinition.from_dict(loop_dict)


def set_tic(enabled: bool = True, **scheduling) -> ExperimentActionDefinition:
    """Create a set_tic action (Torque Integral Control)."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "set_tic"),
        type="set_tic",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"enabled": enabled}
    )


def wait_event(event: str, timeout: float | None = None, **scheduling) -> ExperimentActionDefinition:
    """Create a wait_event action."""
    params = {"event": event}
    if timeout is not None:
        params["timeout"] = timeout
    return ExperimentActionDefinition(
        id=scheduling.get("id", "wait_event"),
        type="wait_event",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters=params
    )


def wait_until_tick(tick_target: int, **scheduling) -> ExperimentActionDefinition:
    """Create a wait_until_tick action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "wait_until_tick"),
        type="wait_until_tick",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"tick": tick_target}
    )


def func(function: str, args: list = None, kwargs: dict = None, **scheduling) -> ExperimentActionDefinition:
    """Create a func action to execute an arbitrary function on the robot.

    Args:
        function: Dot-separated path to the function, e.g. ".control.set_mode"
        args: Positional arguments to pass to the function
        kwargs: Keyword arguments to pass to the function
    """
    return ExperimentActionDefinition(
        id=scheduling.get("id", "func"),
        type="func",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"function": function, "args": args or [], "kwargs": kwargs or {}}
    )


def set_feedback_gain(K: list, **scheduling) -> ExperimentActionDefinition:
    """Create a set_feedback_gain action to set the state feedback gain K."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "set_feedback_gain"),
        type="set_feedback_gain",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"K": K}
    )


def reset_control(**scheduling) -> ExperimentActionDefinition:
    """Create a reset_control action to reload control parameters from config."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "reset_control"),
        type="reset_control",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={}
    )


# ======================================================================================================================
# POSITION CONTROL HELPER FUNCTIONS
# ======================================================================================================================

def move_to(x: float, y: float, max_speed: float = 0.0, timeout: float = 0.0,
            wait: bool = True, **scheduling) -> ExperimentActionDefinition:
    """Create a move_to action to move to a position.

    Args:
        x, y: Target position in world coordinates [m]
        max_speed: Maximum speed (0 = use default)
        timeout: Command timeout (0 = no timeout)
        wait: If True, wait for completion before continuing
    """
    return ExperimentActionDefinition(
        id=scheduling.get("id", "move_to"),
        type="move_to",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={"x": x, "y": y, "max_speed": max_speed, "timeout": timeout, "wait": wait}
    )


def turn_to(heading: float = 0.0, heading_deg: float | None = None,
            max_angular_speed: float = 0.0, timeout: float = 0.0,
            wait: bool = True, **scheduling) -> ExperimentActionDefinition:
    """Create a turn_to action to turn to a heading.

    Args:
        heading: Target heading in radians
        heading_deg: Alternative: specify heading in degrees (overrides heading)
        max_angular_speed: Maximum turn rate (0 = use default)
        timeout: Command timeout (0 = no timeout)
        wait: If True, wait for completion before continuing
    """
    params = {"max_angular_speed": max_angular_speed, "timeout": timeout, "wait": wait}
    if heading_deg is not None:
        params["heading_deg"] = heading_deg
    else:
        params["heading"] = heading
    return ExperimentActionDefinition(
        id=scheduling.get("id", "turn_to"),
        type="turn_to",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters=params
    )


def follow_path(target: dict | list | tuple, waypoints: list[dict | list | tuple] | None = None,
                max_speed: float = 0.0, timeout: float = 0.0, allow_reverse: bool = False,
                seed: int | None = None, target_heading: float | None = None,
                target_heading_deg: float | None = None,
                wait: bool = True, **scheduling) -> ExperimentActionDefinition:
    """Create a follow_path action to plan and follow a path to a target point.

    Uses the motion planner (RRT) to compute a collision-free path from the current
    position to the target, optionally passing through intermediate waypoints,
    then loads and follows the planned path.

    Args:
        target: Target position as {"x": ..., "y": ...}, [x, y], or (x, y)
        waypoints: Optional intermediate waypoints, each as:
            - {"x": ..., "y": ..., "weight": 0.9, "stop": False}
            - [x, y] or [x, y, weight] or [x, y, weight, stop]
            weight controls how closely the path must pass the waypoint (default 0.9).
            stop=True makes the robot pause at this waypoint.
        max_speed: Speed limit [m/s] (0 = use default)
        timeout: Path execution timeout [s] (0 = no timeout)
        allow_reverse: If True, robot may drive backwards
        seed: Random seed for planner reproducibility
        target_heading: Desired heading [rad] at the target (None = unconstrained)
        target_heading_deg: Alternative: specify target heading in degrees (overrides target_heading)
        wait: If True, wait for path completion before continuing
    """
    # Normalize target to dict
    if isinstance(target, (list, tuple)):
        target = {"x": target[0], "y": target[1] if len(target) > 1 else 0.0}
    params = {
        "target": target,
        "max_speed": max_speed,
        "timeout": timeout,
        "allow_reverse": allow_reverse,
        "wait": wait,
    }
    if waypoints:
        params["waypoints"] = waypoints
    if seed is not None:
        params["seed"] = seed
    if target_heading_deg is not None:
        params["target_heading_deg"] = target_heading_deg
    elif target_heading is not None:
        params["target_heading"] = target_heading
    return ExperimentActionDefinition(
        id=scheduling.get("id", "follow_path"),
        type="follow_path",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters=params
    )


def stop_path(**scheduling) -> ExperimentActionDefinition:
    """Create a stop_path action to abort the current path."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "stop_path"),
        type="stop_path",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters={}
    )


def wait_position_event(event: str, timeout: float | None = None,
                        **scheduling) -> ExperimentActionDefinition:
    """Create a wait_position_event action to wait for a position control event.

    Args:
        event: Event name, one of:
            - "path_finished", "path_timeout", "path_aborted"
            - "move_to_point_completed", "move_to_point_timeout"
            - "turn_to_heading_completed", "turn_to_heading_timeout"
            - "stop_reached", "stop_completed"
        timeout: Timeout in seconds (None = no timeout)
    """
    params = {"event": event}
    if timeout is not None:
        params["timeout"] = timeout
    return ExperimentActionDefinition(
        id=scheduling.get("id", "wait_position_event"),
        type="wait_position_event",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        timeout=scheduling.get("timeout"),
        parameters=params
    )


# ======================================================================================================================
# EXPERIMENT BUILDER
# ======================================================================================================================

class ExperimentBuilder:
    """Builder class for creating experiments programmatically.

    Example:
        exp = (ExperimentBuilder("my_test", "Test experiment")
               .speak("Starting test")
               .wait(time_s=1.0)
               .set_mode("BALANCING")
               .wait(time_s=10.0)
               .set_mode("OFF")
               .build())
    """

    def __init__(self, id: str, description: str, timeout: float | None = None, label: str | None = None):
        self.id = id
        self.description = description
        self.timeout = timeout
        self.label = label
        self._actions: list[ExperimentActionDefinition] = []
        self._action_counter = 0
        self._requirements: ExperimentRequirements | None = None

    def _next_id(self, prefix: str = "action") -> str:
        id = f"{prefix}_{self._action_counter}"
        self._action_counter += 1
        return id

    def add(self, action: ExperimentActionDefinition) -> "ExperimentBuilder":
        """Add a raw action definition."""
        if not action.id or action.id in ["beep", "set_mode", "speak", "wait_time", "wait_ticks",
                                           "set_velocity", "set_input", "run_trajectory", "set_marker",
                                           "enable_external_input", "reset", "parallel", "set_tic",
                                           "wait_event", "wait_until_tick"]:
            action.id = self._next_id(action.type)
        self._actions.append(action)
        return self

    def beep(self, frequency: int = 1000, time_ms: int = 250, repeats: int = 1) -> "ExperimentBuilder":
        return self.add(beep(frequency, time_ms, repeats, id=self._next_id("beep")))

    def set_mode(self, mode: str | BILBO_Control_Mode) -> "ExperimentBuilder":
        return self.add(set_mode(mode, id=self._next_id("set_mode")))

    def speak(self, text: str) -> "ExperimentBuilder":
        return self.add(speak(text, id=self._next_id("speak")))

    def wait(self, time_s: float = 0, ticks: int = None) -> "ExperimentBuilder":
        if ticks is not None:
            return self.add(wait_ticks(ticks, id=self._next_id("wait_ticks")))
        return self.add(wait_time(time_s, id=self._next_id("wait_time")))

    def set_velocity(self, forward: float = 0.0, turn: float = 0.0, normalized: bool = False) -> "ExperimentBuilder":
        return self.add(set_velocity(forward, turn, normalized, id=self._next_id("set_velocity")))

    def set_input(self, input: list[float], normalized: bool = False) -> "ExperimentBuilder":
        return self.add(set_input(input, normalized, id=self._next_id("set_input")))

    def run_trajectory(self, trajectory: InputTrajectory | dict | str) -> "ExperimentBuilder":
        return self.add(run_trajectory(trajectory, id=self._next_id("run_trajectory")))

    def set_marker(self, marker_id: str, marker_value: str) -> "ExperimentBuilder":
        return self.add(set_marker(marker_id, marker_value, id=self._next_id("set_marker")))

    def enable_external_input(self, enabled: bool = True) -> "ExperimentBuilder":
        return self.add(enable_external_input(enabled, id=self._next_id("enable_external_input")))

    def reset(self) -> "ExperimentBuilder":
        return self.add(reset(id=self._next_id("reset")))

    def set_tic(self, enabled: bool = True) -> "ExperimentBuilder":
        return self.add(set_tic(enabled, id=self._next_id("set_tic")))

    def wait_event(self, event: str, timeout: float | None = None) -> "ExperimentBuilder":
        return self.add(wait_event(event, timeout, id=self._next_id("wait_event")))

    def wait_until_tick(self, tick_target: int) -> "ExperimentBuilder":
        return self.add(wait_until_tick(tick_target, id=self._next_id("wait_until_tick")))

    def parallel(self, *actions: ExperimentActionDefinition | dict) -> "ExperimentBuilder":
        return self.add(parallel(list(actions), id=self._next_id("parallel")))

    def group(self, *actions: ExperimentActionDefinition | dict, id: str = None) -> "ExperimentBuilder":
        """Add a group of actions that execute sequentially with timing tracking."""
        group_id = id if id else self._next_id("group")
        return self.add(group(list(actions), id=group_id))

    def loop(self, actions: list[ExperimentActionDefinition | dict], count: int | None = None,
             variable: str | None = None, values: list | None = None,
             loop_range: list | int | None = None, **kwargs) -> "ExperimentBuilder":
        """Add a loop that repeats a block of actions.

        Args:
            actions: List of actions to repeat
            count: Number of iterations (simple repeat)
            variable: Loop variable name for ${variable} substitution
            values: Explicit list of values to iterate over
            loop_range: Range spec: int, [end], [start, end], or [start, end, step]
        """
        return self.add(loop(actions, count=count, variable=variable, values=values,
                            loop_range=loop_range, id=self._next_id("loop"), **kwargs))

    def func(self, function: str, args: list = None, kwargs: dict = None) -> "ExperimentBuilder":
        return self.add(func(function, args, kwargs, id=self._next_id("func")))

    def set_feedback_gain(self, K: list) -> "ExperimentBuilder":
        return self.add(set_feedback_gain(K, id=self._next_id("set_feedback_gain")))

    def reset_control(self) -> "ExperimentBuilder":
        return self.add(reset_control(id=self._next_id("reset_control")))

    # Position control methods
    def move_to(self, x: float, y: float, max_speed: float = 0.0, timeout: float = 0.0,
                wait: bool = True) -> "ExperimentBuilder":
        return self.add(move_to(x, y, max_speed, timeout, wait, id=self._next_id("move_to")))

    def turn_to(self, heading: float = 0.0, heading_deg: float | None = None,
                max_angular_speed: float = 0.0, timeout: float = 0.0,
                wait: bool = True) -> "ExperimentBuilder":
        return self.add(turn_to(heading, heading_deg, max_angular_speed, timeout, wait,
                               id=self._next_id("turn_to")))

    def follow_path(self, target: dict | list | tuple,
                    waypoints: list[dict | list | tuple] | None = None,
                    max_speed: float = 0.0, timeout: float = 0.0,
                    allow_reverse: bool = False, seed: int | None = None,
                    target_heading: float | None = None,
                    target_heading_deg: float | None = None,
                    wait: bool = True) -> "ExperimentBuilder":
        return self.add(follow_path(target, waypoints, max_speed, timeout, allow_reverse,
                                    seed, target_heading, target_heading_deg, wait,
                                    id=self._next_id("follow_path")))

    def stop_path(self) -> "ExperimentBuilder":
        return self.add(stop_path(id=self._next_id("stop_path")))

    def wait_position_event(self, event: str, timeout: float | None = None) -> "ExperimentBuilder":
        return self.add(wait_position_event(event, timeout, id=self._next_id("wait_position_event")))

    # --- Requirements ---

    def _ensure_requirements(self) -> ExperimentRequirements:
        if self._requirements is None:
            self._requirements = ExperimentRequirements()
        return self._requirements

    def require_optitrack(self, active: bool = True) -> "ExperimentBuilder":
        """Require OptiTrack to be connected (True) or disconnected (False)."""
        self._ensure_requirements().optitrack = active
        return self

    def require_robot_id(self, robot_id: str | list[str]) -> "ExperimentBuilder":
        """Require the robot ID to match a pattern or list of patterns (regex)."""
        self._ensure_requirements().robot_id = robot_id
        return self

    def require_control_mode(self, mode: str) -> "ExperimentBuilder":
        """Require a specific control mode (e.g. 'OFF', 'BALANCING')."""
        self._ensure_requirements().control_mode = mode
        return self

    def require_control_config(self, config: str) -> "ExperimentBuilder":
        """Require a specific control config to be loaded."""
        self._ensure_requirements().control_config = config
        return self

    def require_state_range(self, state: str, min: float | None = None, max: float | None = None) -> "ExperimentBuilder":
        """Require a dynamic state field to be within a range."""
        req = self._ensure_requirements()
        if req.state_ranges is None:
            req.state_ranges = []
        req.state_ranges.append(StateRangeRequirement(state=state, min=min, max=max))
        return self

    def build(self) -> ExperimentDefinition:
        """Build and return the experiment definition."""
        return ExperimentDefinition(
            id=self.id,
            description=self.description,
            actions=self._actions,
            timeout=self.timeout,
            label=self.label,
            requirements=self._requirements,
        )
