from __future__ import annotations

import dataclasses

import numpy as np

from core.utils.experiments import ExperimentActionData
from robots.bilbo.robot.experiment.experiment_definitions import BILBO_ExperimentResult


# === EXPERIMENT DATA EXTRACTION =======================================================================================

@dataclasses.dataclass
class ActionSamplesResult:
    """Result of extracting samples for an action."""
    action_id: str
    action_data: ExperimentActionData
    samples: list
    start_tick: int
    end_tick: int
    start_time: float
    end_time: float
    duration: float


@dataclasses.dataclass
class GroupSamplesResult:
    """Result of extracting samples for a group action."""
    group_id: str
    group_data: ExperimentActionData
    samples: list
    start_tick: int
    end_tick: int
    start_time: float
    end_time: float
    duration: float
    sub_actions: dict[str, ActionSamplesResult]  # Sub-action ID -> ActionSamplesResult


@dataclasses.dataclass
class ExperimentSummary:
    """Summary of an experiment."""
    id: str
    status: str
    description: str
    duration: float
    num_samples: int
    num_actions: int
    num_completed_actions: int
    num_failed_actions: int
    num_skipped_actions: int
    error_action_id: str | None
    error_message: str | None


def get_action_data(data: BILBO_ExperimentResult, action_id: str) -> ExperimentActionData | None:
    """Get the ExperimentActionData for a specific action.

    Args:
        data: The experiment data
        action_id: The action ID to look up

    Returns:
        ExperimentActionData or None if not found
    """
    return data.action_data.get(action_id)


def get_action_samples(data: BILBO_ExperimentResult, action_id: str) -> ActionSamplesResult | None:
    """Get samples and data for a specific action by ID.

    Args:
        data: The experiment data
        action_id: The action ID to extract samples for

    Returns:
        ActionSamplesResult containing the action data and filtered samples,
        or None if the action is not found

    Example:
        result = get_action_samples(experiment_data, 'forward_velocity')
        print(f"Action ran for {result.duration:.2f}s with {len(result.samples)} samples")
        for sample in result.samples:
            print(f"  tick={sample.tick}, v={sample.estimation.state.v}")
    """
    action = data.action_data.get(action_id)
    if action is None:
        return None

    start_tick = action.start_tick
    end_tick = action.end_tick

    # Filter samples within the action's tick range
    samples = [s for s in data.samples if start_tick <= s.tick <= end_tick]

    return ActionSamplesResult(
        action_id=action_id,
        action_data=action,
        samples=samples,
        start_tick=start_tick,
        end_tick=end_tick,
        start_time=action.start_time,
        end_time=action.end_time,
        duration=action.end_time - action.start_time,
    )


def get_group_samples(data: BILBO_ExperimentResult, group_id: str) -> GroupSamplesResult | None:
    """Get samples and data for a group action, including sub-action data.

    This function extracts the samples for a group action and also provides
    data for each sub-action within the group.

    Args:
        data: The experiment data
        group_id: The group action ID

    Returns:
        GroupSamplesResult containing the group data, samples, and sub-action data,
        or None if the group is not found

    Example:
        result = get_group_samples(experiment_data, 'velocity_test')
        print(f"Group ran for {result.duration:.2f}s")
        for sub_id, sub_result in result.sub_actions.items():
            print(f"  {sub_id}: {sub_result.duration:.2f}s, {len(sub_result.samples)} samples")
    """
    group_data = data.action_data.get(group_id)
    if group_data is None:
        return None

    start_tick = group_data.start_tick
    end_tick = group_data.end_tick

    # Filter samples within the group's tick range
    samples = [s for s in data.samples if start_tick <= s.tick <= end_tick]

    # Find sub-actions (they have IDs like "{group_id}_sub_0", "{group_id}_sub_1", etc.)
    sub_actions = {}
    sub_action_prefix = f"{group_id}_sub_"

    for action_id, action_data in data.action_data.items():
        if action_id.startswith(sub_action_prefix):
            sub_start = action_data.start_tick
            sub_end = action_data.end_tick
            sub_samples = [s for s in data.samples if sub_start <= s.tick <= sub_end]

            sub_actions[action_id] = ActionSamplesResult(
                action_id=action_id,
                action_data=action_data,
                samples=sub_samples,
                start_tick=sub_start,
                end_tick=sub_end,
                start_time=action_data.start_time,
                end_time=action_data.end_time,
                duration=action_data.end_time - action_data.start_time,
            )

    return GroupSamplesResult(
        group_id=group_id,
        group_data=group_data,
        samples=samples,
        start_tick=start_tick,
        end_tick=end_tick,
        start_time=group_data.start_time,
        end_time=group_data.end_time,
        duration=group_data.end_time - group_data.start_time,
        sub_actions=sub_actions,
    )


def get_samples_by_tick_range(data: BILBO_ExperimentResult, start_tick: int, end_tick: int) -> list:
    """Get samples within a specific tick range.

    Args:
        data: The experiment data
        start_tick: Start tick (inclusive)
        end_tick: End tick (inclusive)

    Returns:
        List of samples within the tick range
    """
    return [s for s in data.samples if start_tick <= s.tick <= end_tick]


def get_samples_by_time_range(data: BILBO_ExperimentResult, start_time: float, end_time: float,
                              dt: float = 0.01) -> list:
    """Get samples within a specific time range.

    Args:
        data: The experiment data
        start_time: Start time in seconds (inclusive)
        end_time: End time in seconds (inclusive)
        dt: Sample period in seconds (default 0.01 = 100Hz)

    Returns:
        List of samples within the time range
    """
    start_tick = int(start_time / dt)
    end_tick = int(end_time / dt)
    return get_samples_by_tick_range(data, start_tick, end_tick)


def extract_state_vector(samples: list, state_name: str, source: str = 'lowlevel') -> np.ndarray:
    """Extract a state variable as a numpy array from samples.

    Args:
        samples: List of BILBO_Sample objects or dicts
        state_name: Name of the state variable (e.g., 'theta', 'v', 'x', 'y', 'psi')
        source: Data source - 'lowlevel' (100Hz, default) or 'estimation' (10Hz)

    Returns:
        Numpy array of the state values

    Example:
        result = get_action_samples(data, 'forward_velocity')
        theta = extract_state_vector(result.samples, 'theta')
        velocity = extract_state_vector(result.samples, 'v')
    """
    values = []
    for s in samples:
        if isinstance(s, dict):
            if source == 'lowlevel':
                ll = s.get('lowlevel') or {}
                ll_est = ll.get('estimation') or {}
                ll_state = ll_est.get('state') or {}
                values.append(ll_state.get(state_name, 0.0) or 0.0)
            else:
                est = s.get('estimation') or {}
                state = est.get('state') or {}
                values.append(state.get(state_name, 0.0) or 0.0)
        else:
            # Assume it's a BILBO_Sample dataclass
            if source == 'lowlevel':
                values.append(getattr(s.lowlevel.estimation.state, state_name, 0.0) or 0.0)
            else:
                values.append(getattr(s.estimation.state, state_name, 0.0) or 0.0)
    return np.array(values)


def extract_control_vector(samples: list, path: list[str]) -> np.ndarray:
    """Extract a control variable as a numpy array from samples.

    Args:
        samples: List of BILBO_Sample objects or dicts
        path: Path to the control variable, e.g., ['velocity_command', 'v']

    Returns:
        Numpy array of the control values

    Example:
        velocity_cmd = extract_control_vector(samples, ['velocity_command', 'v'])
        torque_left = extract_control_vector(samples, ['output', 'u_left'])
    """
    values = []
    for s in samples:
        if isinstance(s, dict):
            ll = s.get('lowlevel') or {}
            ctrl = ll.get('control') or {}
            val = ctrl
            for key in path:
                val = (val.get(key) if isinstance(val, dict) else None) or {}
            values.append(val if isinstance(val, (int, float)) else 0.0)
        else:
            # Assume it's a BILBO_Sample dataclass
            val = s.lowlevel.control
            for key in path:
                val = getattr(val, key, None)
                if val is None:
                    val = 0.0
                    break
            values.append(val if isinstance(val, (int, float)) else 0.0)
    return np.array(values)


def get_time_vector(samples: list, dt: float = 0.01) -> np.ndarray:
    """Generate a time vector for a list of samples.

    Args:
        samples: List of samples
        dt: Sample period in seconds (default 0.01 = 100Hz)

    Returns:
        Numpy array of time values starting from 0
    """
    return np.arange(len(samples)) * dt


def get_experiment_summary(data: BILBO_ExperimentResult) -> ExperimentSummary:
    """Get a summary of the experiment.

    Args:
        data: The experiment data

    Returns:
        ExperimentSummary with key statistics

    Example:
        summary = get_experiment_summary(experiment_data)
        print(f"Experiment {summary.id}: {summary.status}")
        print(f"  Duration: {summary.duration:.2f}s, {summary.num_samples} samples")
        print(f"  Actions: {summary.num_completed_actions}/{summary.num_actions} completed")
    """
    num_completed = 0
    num_failed = 0
    num_skipped = 0
    error_action_id = None

    for action_id, action_data in data.action_data.items():
        status = action_data.status
        if isinstance(status, str):
            status_str = status
        else:
            status_str = status.value if hasattr(status, 'value') else str(status)

        if status_str in ('completed', 'finished'):
            num_completed += 1
        elif status_str in ('error', 'timeout'):
            num_failed += 1
            if status_str == 'error' and error_action_id is None:
                error_action_id = action_id
        elif status_str == 'skipped':
            num_skipped += 1

    # Calculate duration from samples
    duration = len(data.samples) * 0.01 if data.samples else 0.0

    # Get description
    description = ''
    if data.definition:
        description = data.definition.description
    elif data.robot_context:
        description = data.robot_context.description

    # Get status as string
    status_str = data.status.value if hasattr(data.status, 'value') else str(data.status)

    return ExperimentSummary(
        id=data.id,
        status=status_str,
        description=description,
        duration=duration,
        num_samples=len(data.samples),
        num_actions=len(data.action_data),
        num_completed_actions=num_completed,
        num_failed_actions=num_failed,
        num_skipped_actions=num_skipped,
        error_action_id=error_action_id,
        error_message=data.error_message,
    )


def get_failed_actions(data: BILBO_ExperimentResult) -> list[tuple[str, ExperimentActionData]]:
    """Get a list of actions that failed (error or timeout).

    Args:
        data: The experiment data

    Returns:
        List of tuples (action_id, action_data) for failed actions

    Example:
        failed = get_failed_actions(experiment_data)
        for action_id, action_data in failed:
            print(f"Action {action_id} failed: {action_data.error_message}")
    """
    failed = []
    for action_id, action_data in data.action_data.items():
        status = action_data.status
        if isinstance(status, str):
            status_str = status
        else:
            status_str = status.value if hasattr(status, 'value') else str(status)

        if status_str in ('error', 'timeout'):
            failed.append((action_id, action_data))
    return failed


def get_action_duration(data: BILBO_ExperimentResult, action_id: str) -> float | None:
    """Get the duration of an action in seconds.

    Args:
        data: The experiment data
        action_id: The action ID

    Returns:
        Duration in seconds, or None if action not found
    """
    action_data = data.action_data.get(action_id)
    if action_data is None:
        return None
    return action_data.end_time - action_data.start_time


def get_actions_by_type(data: BILBO_ExperimentResult, action_type: str) -> list[tuple[str, ExperimentActionData]]:
    """Get all actions of a specific type.

    Args:
        data: The experiment data
        action_type: The action type (e.g., 'set_velocity', 'group', 'wait_time')

    Returns:
        List of tuples (action_id, action_data) for matching actions

    Example:
        velocity_actions = get_actions_by_type(data, 'set_velocity')
        for action_id, action_data in velocity_actions:
            print(f"{action_id}: forward={action_data.parameters.get('forward')}")
    """
    if data.definition is None:
        return []

    results = []
    for action_def in data.definition.actions:
        if action_def.type == action_type:
            action_data = data.action_data.get(action_def.id)
            if action_data:
                results.append((action_def.id, action_data))
    return results


def get_groups(data: BILBO_ExperimentResult) -> list[tuple[str, ExperimentActionData]]:
    """Get all group actions in the experiment.

    Args:
        data: The experiment data

    Returns:
        List of tuples (group_id, group_data) for all groups

    Example:
        groups = get_groups(experiment_data)
        for group_id, group_data in groups:
            result = get_group_samples(experiment_data, group_id)
            print(f"Group {group_id}: {result.duration:.2f}s")
    """
    return get_actions_by_type(data, 'group')
