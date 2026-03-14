"""
Experiment Actions Registry for Host-Side Validation

This module provides a declarative registry of experiment actions for the host side.
It enables pre-parsing and validation of experiment definitions before sending them
to the robot for execution.

Unlike the robot-side parser, this module:
- Does not create action instances (those are created on the robot)
- Focuses on validation and dict creation
- Provides introspection of available actions and parameters

Usage:
    # Parse and validate an experiment file
    parser = ExperimentParser()
    definition = parser.from_file("experiment.yaml")

    # Get validated dict to send to robot
    experiment_dict = definition.to_dict()

    # Introspect available actions
    registry = get_registry()
    for name in registry.type_names:
        entry = registry.get_entry(name)
        print(f"{name}: {entry.description}")
        for param in entry.parameters:
            print(f"  - {param.name}: {param.param_type.__name__}")
"""

from __future__ import annotations

import dataclasses
import json
import math
from typing import Any, Callable

import yaml

from core.utils.files import file_exists
from core.utils.logging_utils import Logger


# ======================================================================================================================
# Parameter Types and Converters
# ======================================================================================================================

def parse_time_s(val: Any) -> float:
    """Parse time value to seconds.

    Supports:
    - '2s' or '2.5s' -> seconds
    - '500ms' -> 0.5 seconds
    - 2.0 (float) -> seconds
    - 2 (int) -> seconds
    """
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip().lower()
        if val.endswith("ms"):
            return float(val[:-2]) / 1000.0
        if val.endswith("s"):
            return float(val[:-1])
        return float(val)
    raise ValueError(f"Invalid time format: {val}")


# Keep old name as alias for backwards compatibility
parse_time_ms = parse_time_s


def parse_control_mode(val: Any) -> str:
    """Parse and validate control mode, returning normalized string."""
    valid_modes = {'OFF', 'BALANCING', 'VELOCITY', 'DIRECT', 'POSITION'}

    if isinstance(val, str):
        mode_upper = val.upper()
        if mode_upper in valid_modes:
            return mode_upper
        raise ValueError(f"Invalid control mode: {val}. Valid modes: {valid_modes}")
    if isinstance(val, int):
        mode_map = {0: 'OFF', 1: 'DIRECT', 2: 'BALANCING', 3: 'VELOCITY', 4: 'POSITION'}
        if val in mode_map:
            return mode_map[val]
        raise ValueError(f"Invalid control mode value: {val}")
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
        name: Parameter name as used in YAML/dict
        param_type: Expected Python type (int, float, str, bool, list, dict)
        default: Default value if not provided
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

    def validate(self, raw_value: Any) -> tuple[bool, Any, str | None]:
        """Validate and convert a raw value for this parameter.

        Returns:
            Tuple of (is_valid, converted_value, error_message)
        """
        if raw_value is None:
            if self.required:
                return False, None, f"Required parameter '{self.name}' is missing"
            return True, self.default, None

        try:
            if self.converter is not None:
                return True, self.converter(raw_value), None

            # Basic type validation
            if self.param_type is not Any:
                if self.param_type is bool:
                    if isinstance(raw_value, bool):
                        return True, raw_value, None
                    if isinstance(raw_value, str):
                        return True, raw_value.lower() in ('true', 'yes', '1', 'on'), None
                    return True, bool(raw_value), None
                elif self.param_type is int:
                    return True, int(raw_value), None
                elif self.param_type is float:
                    return True, float(raw_value), None
                elif self.param_type is str:
                    return True, str(raw_value), None
                elif self.param_type is list and not isinstance(raw_value, list):
                    return False, None, f"Parameter '{self.name}' must be a list"
                elif self.param_type is dict and not isinstance(raw_value, dict):
                    return False, None, f"Parameter '{self.name}' must be a dict"

            return True, raw_value, None
        except (ValueError, TypeError) as e:
            return False, None, f"Cannot convert '{raw_value}' for parameter '{self.name}': {e}"


# ======================================================================================================================
# Action Entry Definition
# ======================================================================================================================

@dataclasses.dataclass
class ActionEntry:
    """Complete definition of an experiment action type.

    This class holds all the metadata needed for:
    1. Parsing the action from YAML/dict
    2. Validating parameters
    3. Generating documentation

    Attributes:
        type_name: The action type identifier (e.g., "beep", "set_mode")
        parameters: List of ActionParameter definitions
        description: Human-readable description of the action
    """
    type_name: str
    parameters: list[ActionParameter] = dataclasses.field(default_factory=list)
    description: str = ""

    def validate_parameters(self, raw_params: dict) -> tuple[bool, dict, list[str]]:
        """Validate raw parameters dict.

        Args:
            raw_params: Dict of parameter names to raw values

        Returns:
            Tuple of (is_valid, validated_params, error_messages)
        """
        result = {}
        errors = []

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

            is_valid, converted, error = param.validate(value)
            if not is_valid:
                errors.append(error)
            else:
                result[param.name] = converted

        return len(errors) == 0, result, errors

    def get_parameter_names(self) -> list[str]:
        """Get all parameter names including aliases."""
        names = []
        for param in self.parameters:
            names.append(param.name)
            names.extend(param.aliases)
        return names


# ======================================================================================================================
# Action Registry
# ======================================================================================================================

class ActionRegistry:
    """Registry of all available action types.

    This is a singleton that holds all ActionEntry definitions and provides
    methods for validation and introspection.
    """

    def __init__(self):
        self._entries: dict[str, ActionEntry] = {}
        self.logger = Logger("ActionRegistry", "INFO")

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

    def validate_action(self, action_type: str, parameters: dict) -> tuple[bool, dict, list[str]]:
        """Validate action parameters.

        Returns:
            Tuple of (is_valid, validated_params, error_messages)
        """
        entry = self._entries.get(action_type)
        if entry is None:
            return False, {}, [f"Unknown action type: {action_type}"]

        return entry.validate_parameters(parameters)

    @property
    def type_names(self) -> list[str]:
        """Get list of all registered type names."""
        return list(self._entries.keys())

    def get_action_info(self, type_name: str) -> dict | None:
        """Get information about an action type for documentation/introspection."""
        entry = self._entries.get(type_name)
        if entry is None:
            return None

        return {
            "type": entry.type_name,
            "description": entry.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.param_type.__name__ if hasattr(p.param_type, '__name__') else str(p.param_type),
                    "required": p.required,
                    "default": p.default,
                    "description": p.description,
                    "aliases": p.aliases,
                }
                for p in entry.parameters
            ],
        }


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

    This class handles parsing experiments from YAML/JSON files or dicts,
    expanding shorthands, validating parameters, and creating experiment dicts.
    """

    def __init__(self, registry: ActionRegistry | None = None, validate: bool = True, debug: bool = False):
        """Initialize the parser.

        Args:
            registry: Action registry to use (defaults to global registry)
            validate: If True, validate parameters during parsing
            debug: Enable debug logging
        """
        self.registry = registry or get_registry()
        self.validate = validate
        self.debug = debug
        self.logger = Logger("ExperimentParser", "DEBUG" if debug else "INFO")

    def from_file(self, filepath: str) -> dict:
        """Parse an experiment definition from a YAML or JSON file.

        Args:
            filepath: Path to the experiment file

        Returns:
            Parsed and validated experiment dict
        """
        if not file_exists(filepath):
            raise FileNotFoundError(f"Experiment file not found: {filepath}")

        with open(filepath, "r") as f:
            if filepath.lower().endswith((".yml", ".yaml")):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        return self.from_dict(data)

    def from_dict(self, data: dict) -> dict:
        """Parse an experiment definition from a dict.

        Args:
            data: Dict containing experiment definition with 'id', 'description', 'actions'

        Returns:
            Parsed and validated experiment dict ready to send to robot
        """
        errors = []

        if "id" not in data:
            errors.append("Experiment definition requires an 'id'")
        if "description" not in data:
            errors.append("Experiment definition requires a 'description'")
        if "actions" not in data:
            errors.append("Experiment definition requires 'actions'")

        if errors:
            raise ValueError(f"Invalid experiment definition: {'; '.join(errors)}")

        raw_actions = data["actions"]
        if not isinstance(raw_actions, list):
            raise TypeError("'actions' must be a list")

        parsed_actions = []
        all_errors = []

        for i, raw_action in enumerate(raw_actions):
            if self.debug:
                self.logger.debug(f"Parsing action {i}: {raw_action}")

            try:
                action_dict, action_errors = self.parse_action(raw_action, index=i)
                parsed_actions.append(action_dict)
                all_errors.extend(action_errors)
            except Exception as e:
                all_errors.append(f"Action {i}: {e}")

            if self.debug and action_errors:
                self.logger.debug(f"Validation errors for action {i}: {action_errors}")

        if all_errors and self.validate:
            raise ValueError(f"Experiment validation failed:\n  - " + "\n  - ".join(all_errors))

        return {
            "id": data["id"],
            "description": data["description"],
            "timeout": data.get("timeout"),
            "actions": parsed_actions,
        }

    def parse_action(self, data: dict, index: int = 0) -> tuple[dict, list[str]]:
        """Parse a single action definition.

        Args:
            data: Raw action data dict (must contain 'type' field)
            index: Action index for auto-generating IDs

        Returns:
            Tuple of (parsed_action_dict, validation_errors)
        """
        errors = []

        if not isinstance(data, dict):
            return {"type": "unknown", "id": f"action_{index}"}, [
                f"Action at index {index} must be a dict, got {type(data).__name__}"
            ]

        expanded = data

        if "type" not in expanded:
            return expanded, [f"Action at index {index} missing required field 'type'"]

        action_type = expanded["type"]
        action_id = expanded.get("id", f"action_{index}")

        # Check if action type is known
        if not self.registry.has_type(action_type):
            errors.append(f"Unknown action type: {action_type}")

        # Reserved fields that should not go into parameters
        reserved_fields = {"id", "type", "tick", "after", "time", "timeout", "parameters", "wait_before", "wait_after"}

        # Collect parameters
        if "parameters" in expanded:
            parameters = expanded["parameters"]
        else:
            parameters = {
                k: v for k, v in expanded.items()
                if k not in reserved_fields
            }

        # Validate parameters if validation is enabled and action type is known
        if self.validate and self.registry.has_type(action_type):
            is_valid, validated_params, param_errors = self.registry.validate_action(action_type, parameters)
            if not is_valid:
                errors.extend(param_errors)
            else:
                parameters = validated_params

        # Build result dict
        result = {
            "id": action_id,
            "type": action_type,
        }

        # Add scheduling fields
        for field in ["tick", "after", "time", "timeout"]:
            if field in expanded:
                result[field] = expanded[field]

        # Add wait_before/wait_after (convert to seconds)
        for field in ["wait_before", "wait_after"]:
            if field in expanded:
                try:
                    result[field] = parse_time_s(expanded[field])
                except (ValueError, TypeError) as e:
                    errors.append(f"Invalid {field} value: {expanded[field]} ({e})")

        if parameters:
            result["parameters"] = parameters

        return result, errors

    def from_json(self, json_str: str) -> dict:
        """Parse an experiment definition from a JSON string."""
        data = json.loads(json_str)
        return self.from_dict(data)

    def validate_only(self, data: dict) -> tuple[bool, list[str]]:
        """Validate an experiment definition without raising exceptions.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        try:
            # Temporarily enable validation
            old_validate = self.validate
            self.validate = False  # Don't raise during parsing

            errors = []

            if "id" not in data:
                errors.append("Missing 'id'")
            if "description" not in data:
                errors.append("Missing 'description'")
            if "actions" not in data:
                errors.append("Missing 'actions'")
            elif not isinstance(data["actions"], list):
                errors.append("'actions' must be a list")
            else:
                for i, raw_action in enumerate(data["actions"]):
                    _, action_errors = self.parse_action(raw_action, index=i)
                    errors.extend(action_errors)

            self.validate = old_validate
            return len(errors) == 0, errors
        except Exception as e:
            return False, [str(e)]


# ======================================================================================================================
# Register Built-in Actions
# ======================================================================================================================

def _register_builtin_actions():
    """Register all built-in action types."""

    # === Basic Actions ===

    register_action(ActionEntry(
        type_name="beep",
        parameters=[
            ActionParameter("frequency", int, default=1000),
            ActionParameter("time_ms", int, default=250),
            ActionParameter("repeats", int, default=1),
        ],
        description="Play a beep sound"
    ))

    register_action(ActionEntry(
        type_name="set_mode",
        parameters=[
            ActionParameter("mode", str, converter=parse_control_mode, required=True),
        ],
        description="Set the control mode"
    ))

    register_action(ActionEntry(
        type_name="set_tic",
        parameters=[
            ActionParameter("enabled", bool, default=True),
        ],
        description="Enable/disable TIC control"
    ))

    register_action(ActionEntry(
        type_name="set_psi_control",
        parameters=[
            ActionParameter("enabled", bool, default=True),
        ],
        description="Enable/disable PSI yaw angle control"
    ))

    register_action(ActionEntry(
        type_name="set_tracker_updates",
        parameters=[
            ActionParameter("enabled", bool, default=True),
        ],
        description="Enable/disable sending OptiTrack tracker updates to lowlevel firmware"
    ))

    register_action(ActionEntry(
        type_name="speak",
        parameters=[
            ActionParameter("text", str, default=""),
        ],
        description="Speak text using TTS"
    ))

    register_action(ActionEntry(
        type_name="set_marker",
        parameters=[
            ActionParameter("marker_id", str, default=""),
            ActionParameter("marker_value", str, default=""),
        ],
        description="Set an experiment marker"
    ))

    register_action(ActionEntry(
        type_name="enable_external_input",
        parameters=[
            ActionParameter("enabled", bool, default=True),
        ],
        description="Enable/disable external input"
    ))

    register_action(ActionEntry(
        type_name="set_velocity",
        parameters=[
            ActionParameter("forward", float, default=0.0),
            ActionParameter("turn", float, default=0.0),
            ActionParameter("normalized", bool, default=False),
        ],
        description="Set velocity command"
    ))

    register_action(ActionEntry(
        type_name="reset",
        parameters=[],
        description="Reset robot state"
    ))

    register_action(ActionEntry(
        type_name="run_trajectory",
        parameters=[
            ActionParameter("input_trajectory", required=True),
        ],
        description="Run a trajectory"
    ))

    register_action(ActionEntry(
        type_name="set_input",
        parameters=[
            ActionParameter("input", list, default=[0.0, 0.0]),
            ActionParameter("normalized", bool, default=False),
        ],
        description="Set raw input"
    ))

    # === Wait Actions ===

    register_action(ActionEntry(
        type_name="wait_time",
        parameters=[
            ActionParameter("time", float, default=0, converter=parse_time_s),
        ],
        description="Wait for a specified time"
    ))

    register_action(ActionEntry(
        type_name="wait_ticks",
        parameters=[
            ActionParameter("ticks", int, default=0),
        ],
        description="Wait for a number of ticks"
    ))

    register_action(ActionEntry(
        type_name="wait_until_tick",
        parameters=[
            ActionParameter("tick_target", int, default=0, aliases=["tick"]),
        ],
        description="Wait until a specific tick"
    ))

    register_action(ActionEntry(
        type_name="wait_event",
        parameters=[
            ActionParameter("event", str, default=""),
            ActionParameter("timeout", float, default=None),
        ],
        description="Wait for an event"
    ))

    # === Control Actions ===

    register_action(ActionEntry(
        type_name="parallel",
        parameters=[
            ActionParameter("sub_actions", list, default=[], aliases=["actions"]),
        ],
        description="Execute multiple actions in parallel"
    ))

    register_action(ActionEntry(
        type_name="group",
        parameters=[
            ActionParameter("sub_actions", list, default=[], aliases=["actions"]),
        ],
        description="Execute multiple actions sequentially as a named group"
    ))

    register_action(ActionEntry(
        type_name="loop",
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
        parameters=[
            ActionParameter("function", str, default=""),
            ActionParameter("args", list, default=[]),
            ActionParameter("kwargs", dict, default={}),
        ],
        description="Execute a function on the robot"
    ))

    register_action(ActionEntry(
        type_name="set_feedback_gain",
        parameters=[
            ActionParameter("K", list, required=True),
        ],
        description="Set state feedback gain"
    ))

    register_action(ActionEntry(
        type_name="reset_control",
        parameters=[],
        description="Reset control parameters to defaults"
    ))

    # === Position Control Actions ===

    register_action(ActionEntry(
        type_name="move_to",
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
        parameters=[],
        description="Stop/abort the current path"
    ))

    register_action(ActionEntry(
        type_name="follow_path",
        parameters=[
            ActionParameter("target", required=True),
            ActionParameter("waypoints", list, default=[]),
            ActionParameter("max_speed", float, default=0.0),
            ActionParameter("timeout", float, default=0.0),
            ActionParameter("allow_reverse", bool, default=False),
            ActionParameter("seed", int, default=None),
            ActionParameter("target_heading", float, default=None),
            ActionParameter("target_heading_deg", float, default=None),
            ActionParameter("heading_strength", float, default=1.0,
                            description="Strength of the heading constraint on the spline (higher = longer approach corridor)"),
            ActionParameter("wait", bool, default=True),
        ],
        description="Plan and follow a path to a target point"
    ))

    register_action(ActionEntry(
        type_name="wait_position_event",
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

def parse_experiment_file(filepath: str, validate: bool = True, debug: bool = False) -> dict:
    """Parse an experiment from a file.

    Args:
        filepath: Path to YAML or JSON experiment file
        validate: Enable parameter validation
        debug: Enable debug logging

    Returns:
        Parsed experiment dict ready to send to robot
    """
    parser = ExperimentParser(validate=validate, debug=debug)
    return parser.from_file(filepath)


def parse_experiment_dict(data: dict, validate: bool = True, debug: bool = False) -> dict:
    """Parse an experiment from a dict.

    Args:
        data: Experiment definition dict
        validate: Enable parameter validation
        debug: Enable debug logging

    Returns:
        Parsed experiment dict ready to send to robot
    """
    parser = ExperimentParser(validate=validate, debug=debug)
    return parser.from_dict(data)


def validate_experiment(data: dict) -> tuple[bool, list[str]]:
    """Validate an experiment definition without raising exceptions.

    Args:
        data: Experiment definition dict

    Returns:
        Tuple of (is_valid, error_messages)
    """
    parser = ExperimentParser(validate=True)
    return parser.validate_only(data)


def get_available_actions() -> list[dict]:
    """Get information about all available actions.

    Returns:
        List of action info dicts for documentation/introspection
    """
    registry = get_registry()
    return [registry.get_action_info(name) for name in registry.type_names]


def get_action_info(action_type: str) -> dict | None:
    """Get information about a specific action type.

    Args:
        action_type: The action type name

    Returns:
        Action info dict or None if not found
    """
    return get_registry().get_action_info(action_type)
