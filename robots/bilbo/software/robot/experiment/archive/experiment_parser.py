"""
Experiment Parser Module

This module provides a declarative way to define experiment actions with their
parameters and parsing logic. It makes adding new actions simple by defining
an ActionEntry with the action class and its parameters.

Usage:
    # Register a new action
    register_action(ActionEntry(
        type_name="my_action",
        action_class=MyAction,
        parameters=[
            ActionParameter("param1", int, default=0),
            ActionParameter("param2", str, required=True),
        ],
    ))

    # Parse an experiment
    parser = ExperimentParser()
    definition = parser.from_file("experiment.yaml")
"""

from __future__ import annotations

import copy
import dataclasses
import json
import math
from typing import Any, Callable, TYPE_CHECKING

import yaml

from core.utils.files import file_exists
from core.utils.logging_utils import Logger

if TYPE_CHECKING:
    from robot.experiment.experiment import ExperimentAction, ExperimentActionDefinition


# ======================================================================================================================
# Parameter Types and Converters
# ======================================================================================================================

def parse_time_ms(val: Any) -> int:
    """Parse time value to milliseconds.

    Supports:
    - '2s' or '2.5s' -> seconds to milliseconds
    - '500ms' -> milliseconds
    - 2.0 (float) -> interpreted as seconds
    - 2000 (int) -> interpreted as milliseconds
    """
    if isinstance(val, float):
        return int(val * 1000)
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        val = val.strip().lower()
        if val.endswith("ms"):
            return int(float(val[:-2]))
        if val.endswith("s"):
            return int(float(val[:-1]) * 1000)
        num = float(val)
        if '.' in val:
            return int(num * 1000)
        else:
            return int(num)
    raise ValueError(f"Invalid time format: {val}")


def parse_control_mode(val: Any) -> Any:
    """Parse control mode from string, int, or enum."""
    from robot.control.bilbo_control_definitions import BILBO_Control_Mode

    if isinstance(val, BILBO_Control_Mode):
        return val
    if isinstance(val, int):
        return BILBO_Control_Mode(val)
    if isinstance(val, str):
        mode_upper = val.upper()
        mode_map = {
            'OFF': BILBO_Control_Mode.OFF,
            'BALANCING': BILBO_Control_Mode.BALANCING,
            'VELOCITY': BILBO_Control_Mode.VELOCITY,
            'DIRECT': BILBO_Control_Mode.DIRECT,
            'POSITION': BILBO_Control_Mode.POSITION,
        }
        if mode_upper in mode_map:
            return mode_map[mode_upper]
        raise ValueError(f"Invalid control mode: {val}")
    raise ValueError(f"Invalid control mode type: {type(val)}")


def parse_heading(val: Any) -> float:
    """Parse heading, converting degrees to radians if specified."""
    if isinstance(val, dict):
        if 'deg' in val:
            return math.radians(float(val['deg']))
        if 'rad' in val:
            return float(val['rad'])
    return float(val)


def normalize_path_points(points: list) -> list[dict]:
    """Normalize path points to list of dicts with x, y.

    Supported formats:
        - [x, y] - coordinate pair (list or tuple)
        - {"x": x, "y": y} - dict with x, y keys
        - {"x": x, "y": y, "type": "STOP", ...} - legacy waypoint dict (type/weight ignored)
    """
    result = []
    for pt in points:
        if isinstance(pt, dict):
            normalized = {
                "x": float(pt.get("x", 0.0)),
                "y": float(pt.get("y", 0.0)),
            }
        elif isinstance(pt, (list, tuple)):
            if len(pt) < 2:
                raise ValueError(f"Path point must have at least x, y: {pt}")
            normalized = {"x": float(pt[0]), "y": float(pt[1])}
        else:
            raise ValueError(f"Invalid path point format: {pt}")
        result.append(normalized)
    return result


# Backwards-compatible alias
normalize_waypoints = normalize_path_points


# ======================================================================================================================
# Action Parameter Definition
# ======================================================================================================================

@dataclasses.dataclass
class ActionParameter:
    """Defines a parameter for an experiment action.

    Attributes:
        name: Parameter name as used in YAML/dict and action class
        param_type: Expected Python type (int, float, str, bool, list, dict)
        default: Default value if not provided (None means required)
        required: Whether the parameter is required
        description: Human-readable description
        converter: Optional function to convert/validate the value
        aliases: Alternative names for this parameter in the input
    """
    name: str
    param_type: type = Any
    default: Any = None
    required: bool = False
    description: str = ""
    converter: Callable[[Any], Any] | None = None
    aliases: list[str] = dataclasses.field(default_factory=list)

    def parse_value(self, raw_value: Any) -> Any:
        """Parse and validate a raw value for this parameter."""
        if raw_value is None:
            if self.required:
                raise ValueError(f"Required parameter '{self.name}' is missing")
            return self.default

        if self.converter is not None:
            return self.converter(raw_value)

        # Basic type coercion
        if self.param_type is not Any:
            try:
                if self.param_type is bool:
                    if isinstance(raw_value, bool):
                        return raw_value
                    if isinstance(raw_value, str):
                        return raw_value.lower() in ('true', 'yes', '1', 'on')
                    return bool(raw_value)
                elif self.param_type is int:
                    return int(raw_value)
                elif self.param_type is float:
                    return float(raw_value)
                elif self.param_type is str:
                    return str(raw_value)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Cannot convert '{raw_value}' to {self.param_type.__name__} for parameter '{self.name}'") from e

        return raw_value


# ======================================================================================================================
# Action Entry Definition
# ======================================================================================================================

@dataclasses.dataclass
class ActionEntry:
    """Complete definition of an experiment action type.

    This class holds all the metadata needed to:
    1. Parse the action from YAML/dict
    2. Create action instances
    3. Validate parameters

    Attributes:
        type_name: The action type identifier (e.g., "beep", "set_mode")
        action_class: The ExperimentAction subclass to instantiate
        parameters: List of ActionParameter definitions
        description: Human-readable description of the action
    """
    type_name: str
    action_class: type[ExperimentAction]
    parameters: list[ActionParameter] = dataclasses.field(default_factory=list)
    description: str = ""

    def parse_parameters(self, raw_params: dict) -> dict:
        """Parse raw parameters dict into validated parameters.

        Args:
            raw_params: Dict of parameter names to raw values

        Returns:
            Dict of parameter names to parsed/validated values
        """
        result = {}

        for param in self.parameters:
            # Check for value under main name or aliases
            value = None
            found = False

            if param.name in raw_params:
                value = raw_params[param.name]
                found = True
            else:
                for alias in param.aliases:
                    if alias in raw_params:
                        value = raw_params[alias]
                        found = True
                        break

            if not found:
                value = None

            result[param.name] = param.parse_value(value)

        return result

    def create_action(self, definition: ExperimentActionDefinition) -> ExperimentAction:
        """Create an action instance from a definition.

        Args:
            definition: The ExperimentActionDefinition with parsed parameters

        Returns:
            An instance of the action class
        """
        # Use from_definition if available (handles special cases like nested actions in groups)
        if hasattr(self.action_class, 'from_definition'):
            return self.action_class.from_definition(definition)

        # Parse parameters
        parsed_params = self.parse_parameters(definition.parameters)

        # Build kwargs for action constructor
        wait_before_ms = 0
        if definition.wait_before is not None:
            wait_before_ms = parse_time_ms(definition.wait_before)
        wait_after_ms = 0
        if definition.wait_after is not None:
            wait_after_ms = parse_time_ms(definition.wait_after)

        kwargs = {
            "id": definition.id,
            "tick": definition.tick,
            "after": definition.after,
            "time": definition.time,
            "timeout": definition.timeout,
            "wait_before_ms": wait_before_ms,
            "wait_after_ms": wait_after_ms,
        }
        kwargs.update(parsed_params)

        return self.action_class(**kwargs)


# ======================================================================================================================
# Action Registry
# ======================================================================================================================

class ActionRegistry:
    """Registry of all available action types.

    This is a singleton that holds all ActionEntry definitions and provides
    methods for parsing and creating actions.
    """

    def __init__(self):
        self._entries: dict[str, ActionEntry] = {}
        self.logger = Logger("ActionRegistry", "DEBUG")

    def register(self, entry: ActionEntry) -> None:
        """Register an action entry."""
        if entry.type_name in self._entries:
            self.logger.warning(f"Overwriting existing action entry: {entry.type_name}")

        self._entries[entry.type_name] = entry

    def get_entry(self, type_name: str) -> ActionEntry | None:
        """Get an action entry by type name."""
        return self._entries.get(type_name)

    def has_type(self, type_name: str) -> bool:
        """Check if a type is registered."""
        return type_name in self._entries

    def create_action(self, definition: ExperimentActionDefinition) -> ExperimentAction:
        """Create an action instance from a definition."""
        entry = self._entries.get(definition.type)
        if entry is None:
            raise ValueError(f"Unknown action type: {definition.type}")

        return entry.create_action(definition)

    @property
    def type_names(self) -> list[str]:
        """Get list of all registered type names."""
        return list(self._entries.keys())


# Global registry instance
_registry = ActionRegistry()


def get_registry() -> ActionRegistry:
    """Get the global action registry."""
    return _registry


def register_action(entry: ActionEntry) -> None:
    """Register an action entry in the global registry."""
    _registry.register(entry)


# ======================================================================================================================
# Experiment Parser
# ======================================================================================================================

class ExperimentParser:
    """Parser for experiment definitions.

    This class handles parsing experiments from YAML/JSON files or dicts
    and creating ExperimentDefinition objects.
    """

    def __init__(self, registry: ActionRegistry | None = None, debug: bool = False):
        self.registry = registry or get_registry()
        self.debug = debug
        self.logger = Logger("ExperimentParser", "DEBUG" if debug else "INFO")

    def from_file(self, filepath: str):
        """Parse an experiment definition from a YAML or JSON file.

        Args:
            filepath: Path to the experiment file

        Returns:
            Parsed ExperimentDefinition
        """
        from robot.experiment.experiment import ExperimentDefinition

        if not file_exists(filepath):
            raise FileNotFoundError(f"Experiment file not found: {filepath}")

        with open(filepath, "r") as f:
            if filepath.lower().endswith((".yml", ".yaml")):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        return self.from_dict(data)

    def from_dict(self, data: dict):
        """Parse an experiment definition from a dict.

        Args:
            data: Dict containing experiment definition with 'id', 'description', 'actions'

        Returns:
            Parsed ExperimentDefinition
        """
        from robot.experiment.experiment import ExperimentDefinition, ExperimentActionDefinition

        if "id" not in data:
            raise ValueError("Experiment definition requires an 'id'")
        if "description" not in data:
            raise ValueError("Experiment definition requires a 'description'")
        if "actions" not in data:
            raise ValueError("Experiment definition requires 'actions'")

        raw_actions = data["actions"]
        if not isinstance(raw_actions, list):
            raise TypeError("'actions' must be a list")

        actions = []
        for i, raw_action in enumerate(raw_actions):
            if self.debug:
                self.logger.debug(f"Parsing action {i}: {raw_action}")

            action_def = self.parse_action(raw_action, index=i)
            actions.append(action_def)

            if self.debug:
                self.logger.debug(f"Parsed action {i}: type={action_def.type}, params={action_def.parameters}")

        requirements = None
        if "requirements" in data:
            requirements = self._parse_requirements(data["requirements"])

        return ExperimentDefinition(
            id=data["id"],
            description=data["description"],
            actions=actions,
            timeout=data.get("timeout"),
            label=data.get("label"),
            external_input_enabled=data.get("external_input_enabled", False),
            requirements=requirements,
            source_dict=copy.deepcopy(data),
        )

    def parse_action(self, data: dict, index: int = 0, parent_id: str | None = None):
        """Parse a single action definition.

        Args:
            data: Raw action data dict (must contain 'type' field)
            index: Action index for auto-generating IDs
            parent_id: Parent action ID for sub-action ID generation

        Returns:
            Parsed ExperimentActionDefinition
        """
        from robot.experiment.experiment import ExperimentActionDefinition

        if not isinstance(data, dict):
            raise ValueError(f"Action at index {index} must be a dict, got {type(data).__name__}")

        if "type" not in data:
            raise ValueError(f"Action at index {index} missing required field 'type': {data}")

        # Use ExperimentActionDefinition.from_dict() for consistent parsing
        # This handles sub_actions for group/parallel types
        return ExperimentActionDefinition.from_dict(data, index=index, parent_id=parent_id)

    def from_json(self, json_str: str):
        """Parse an experiment definition from a JSON string."""
        data = json.loads(json_str)
        return self.from_dict(data)

    def _parse_requirements(self, data: dict):
        """Parse an ExperimentRequirements from a dict.

        Args:
            data: Dict with optional keys: optitrack, robot_id, control_mode,
                  control_config, state_ranges.

        Returns:
            ExperimentRequirements instance.
        """
        from core.utils.dataclass_utils import from_dict_auto
        from robot.experiment.experiment import ExperimentRequirements, StateRangeRequirement

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


# ======================================================================================================================
# Register Built-in Actions
# ======================================================================================================================

def _register_builtin_actions():
    """Register all built-in action types."""
    from robot.experiment.experiment import (
        BeepAction, SetModeAction, SetTICAction, SetTrackerUpdatesAction,
        SpeakAction, SetMarkerAction,
        EnableExternalInputAction, SetVelocityAction, ResetAction, RunTrajectoryAction,
        SetInputAction, WaitTimeAction, WaitTickAction, WaitUntilTickAction,
        WaitEventAction, ParallelAction, GroupAction, FuncAction, SetFeedbackGainAction,
        ResetControlAction, MoveToAction, TurnToAction,
        StopPathAction, FollowPathAction, WaitPositionEventAction
    )

    # === Basic Actions ===

    register_action(ActionEntry(
        type_name="beep",
        action_class=BeepAction,
        parameters=[
            ActionParameter("frequency", int, default=1000),
            ActionParameter("time_ms", int, default=250),
            ActionParameter("repeats", int, default=1),
        ],
        description="Play a beep sound"
    ))

    register_action(ActionEntry(
        type_name="set_mode",
        action_class=SetModeAction,
        parameters=[
            ActionParameter("mode", converter=parse_control_mode, required=True),
        ],
        description="Set the control mode"
    ))

    register_action(ActionEntry(
        type_name="set_tic",
        action_class=SetTICAction,
        parameters=[
            ActionParameter("enabled", bool, default=True),
        ],
        description="Enable/disable TIC control"
    ))

    register_action(ActionEntry(
        type_name="set_tracker_updates",
        action_class=SetTrackerUpdatesAction,
        parameters=[
            ActionParameter("enabled", bool, default=True),
        ],
        description="Enable/disable sending OptiTrack tracker updates to lowlevel firmware"
    ))

    register_action(ActionEntry(
        type_name="speak",
        action_class=SpeakAction,
        parameters=[
            ActionParameter("text", str, default=""),
        ],
        description="Speak text using TTS"
    ))

    register_action(ActionEntry(
        type_name="set_marker",
        action_class=SetMarkerAction,
        parameters=[
            ActionParameter("marker_id", str, default=""),
            ActionParameter("marker_value", str, default=""),
        ],
        description="Set an experiment marker"
    ))

    register_action(ActionEntry(
        type_name="enable_external_input",
        action_class=EnableExternalInputAction,
        parameters=[
            ActionParameter("enabled", bool, default=True),
        ],
        description="Enable/disable external input"
    ))

    register_action(ActionEntry(
        type_name="set_velocity",
        action_class=SetVelocityAction,
        parameters=[
            ActionParameter("forward", float, default=0.0),
            ActionParameter("turn", float, default=0.0),
            ActionParameter("normalized", bool, default=False),
        ],
        description="Set velocity command"
    ))

    register_action(ActionEntry(
        type_name="reset",
        action_class=ResetAction,
        parameters=[],
        description="Reset robot state"
    ))

    register_action(ActionEntry(
        type_name="run_trajectory",
        action_class=RunTrajectoryAction,
        parameters=[
            ActionParameter("input_trajectory", required=True),
        ],
        description="Run a trajectory"
    ))

    register_action(ActionEntry(
        type_name="set_input",
        action_class=SetInputAction,
        parameters=[
            ActionParameter("input", list, default=[0.0, 0.0]),
            ActionParameter("normalized", bool, default=False),
        ],
        description="Set raw input"
    ))

    # === Wait Actions ===

    register_action(ActionEntry(
        type_name="wait_time",
        action_class=WaitTimeAction,
        parameters=[
            ActionParameter("time_ms", int, default=0, converter=parse_time_ms),
        ],
        description="Wait for a specified time"
    ))

    register_action(ActionEntry(
        type_name="wait_ticks",
        action_class=WaitTickAction,
        parameters=[
            ActionParameter("ticks", int, default=0),
        ],
        description="Wait for a number of ticks"
    ))

    register_action(ActionEntry(
        type_name="wait_until_tick",
        action_class=WaitUntilTickAction,
        parameters=[
            ActionParameter("tick_target", int, default=0, aliases=["tick"]),
        ],
        description="Wait until a specific tick"
    ))

    register_action(ActionEntry(
        type_name="wait_event",
        action_class=WaitEventAction,
        parameters=[
            ActionParameter("event", str, default=""),
            ActionParameter("timeout", float, default=None),
        ],
        description="Wait for an event"
    ))

    # === Control Actions ===

    register_action(ActionEntry(
        type_name="parallel",
        action_class=ParallelAction,
        parameters=[
            ActionParameter("sub_actions", list, default=[], aliases=["actions"]),
        ],
        description="Execute multiple actions in parallel"
    ))

    register_action(ActionEntry(
        type_name="group",
        action_class=GroupAction,
        parameters=[
            ActionParameter("sub_actions", list, default=[], aliases=["actions"]),
        ],
        description="Execute multiple actions sequentially as a named group"
    ))

    register_action(ActionEntry(
        type_name="loop",
        action_class=GroupAction,  # Loops are expanded into groups at parse time
        parameters=[
            ActionParameter("actions", list, required=True),
            ActionParameter("count", int, default=None),
            ActionParameter("variable", str, default=None),
            ActionParameter("values", list, default=None),
            ActionParameter("range", list, default=None),
        ],
        description="Repeat a block of actions N times or over a list of values"
    ))

    register_action(ActionEntry(
        type_name="func",
        action_class=FuncAction,
        parameters=[
            ActionParameter("function", str, default=""),
            ActionParameter("args", list, default=[]),
            ActionParameter("kwargs", dict, default={}),
        ],
        description="Execute a function on the robot"
    ))

    register_action(ActionEntry(
        type_name="set_feedback_gain",
        action_class=SetFeedbackGainAction,
        parameters=[
            ActionParameter("K", list, required=True),
        ],
        description="Set state feedback gain"
    ))

    register_action(ActionEntry(
        type_name="reset_control",
        action_class=ResetControlAction,
        parameters=[],
        description="Reset control parameters to defaults"
    ))

    # === Position Control Actions ===

    register_action(ActionEntry(
        type_name="move_to",
        action_class=MoveToAction,
        parameters=[
            ActionParameter("x", float, default=0.0),
            ActionParameter("y", float, default=0.0),
            ActionParameter("max_speed", float, default=0.0),
            ActionParameter("timeout", float, default=0.0),
            ActionParameter("wait", bool, default=True),
        ],
        description="Move to a position"
    ))

    register_action(ActionEntry(
        type_name="turn_to",
        action_class=TurnToAction,
        parameters=[
            ActionParameter("heading", float, default=0.0),
            ActionParameter("max_angular_speed", float, default=0.0),
            ActionParameter("timeout", float, default=0.0),
            ActionParameter("wait", bool, default=True),
        ],
        description="Turn to a heading"
    ))

    register_action(ActionEntry(
        type_name="stop_path",
        action_class=StopPathAction,
        parameters=[],
        description="Stop/stop the current path"
    ))

    register_action(ActionEntry(
        type_name="follow_path",
        action_class=FollowPathAction,
        parameters=[
            ActionParameter("target", required=True),
            ActionParameter("waypoints", list, default=[]),
            ActionParameter("max_speed", float, default=0.0),
            ActionParameter("timeout", float, default=0.0),
            ActionParameter("allow_reverse", bool, default=False),
            ActionParameter("seed", int, default=None),
            ActionParameter("wait", bool, default=True),
        ],
        description="Plan and follow a path to a target point"
    ))

    register_action(ActionEntry(
        type_name="wait_position_event",
        action_class=WaitPositionEventAction,
        parameters=[
            ActionParameter("event", str, default=""),
            ActionParameter("event_timeout", float, default=None, aliases=["timeout"]),
        ],
        description="Wait for a position control event"
    ))


# Initialize builtin actions when module is imported
_register_builtin_actions()


# ======================================================================================================================
# Convenience Functions
# ======================================================================================================================

def parse_experiment_file(filepath: str, debug: bool = False) -> ExperimentDefinition:
    """Parse an experiment from a file.

    Args:
        filepath: Path to YAML or JSON experiment file
        debug: Enable debug logging

    Returns:
        Parsed ExperimentDefinition
    """
    parser = ExperimentParser(debug=debug)
    return parser.from_file(filepath)


def parse_experiment_dict(data: dict, debug: bool = False) -> ExperimentDefinition:
    """Parse an experiment from a dict.

    Args:
        data: Experiment definition dict
        debug: Enable debug logging

    Returns:
        Parsed ExperimentDefinition
    """
    parser = ExperimentParser(debug=debug)
    return parser.from_dict(data)


# Re-export for convenience
ExperimentDefinition = None  # Will be set after import

def _setup_exports():
    """Set up module exports after circular imports are resolved."""
    global ExperimentDefinition
    from robot.experiment.experiment import ExperimentDefinition as ED
    ExperimentDefinition = ED

# Defer export setup
try:
    _setup_exports()
except ImportError:
    pass  # Will be set later when experiment module is imported
