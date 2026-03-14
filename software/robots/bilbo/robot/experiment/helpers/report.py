from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import numpy as np
import yaml

from core.utils.dataclass_utils import from_dict_auto
from core.utils.files import file_exists
from core.utils.json_utils import readJSON
from robots.bilbo.robot.experiment.experiment_definitions import (
    BILBO_ExperimentResult,
)

if TYPE_CHECKING:
    from core.utils.report import Report


# === REPORT GENERATION ================================================================================================
# Color palette for phase bars (distinguishable colors)
PHASE_COLORS = [
    '#3498db',  # Blue
    '#e74c3c',  # Red
    '#2ecc71',  # Green
    '#9b59b6',  # Purple
    '#f39c12',  # Orange
    '#1abc9c',  # Teal
    '#e91e63',  # Pink
    '#00bcd4',  # Cyan
    '#ff5722',  # Deep Orange
    '#8bc34a',  # Light Green
    '#673ab7',  # Deep Purple
    '#ffc107',  # Amber
]


_TRIGGER_DEFAULTS = {'period_unit': 'seconds'}


def _clean_definition_for_yaml(d):
    """Recursively strip None values, empty dicts/lists, and simplify trigger/transition fields."""
    if isinstance(d, dict):
        cleaned = {}
        for k, v in d.items():
            v = _clean_definition_for_yaml(v)
            if v is None:
                continue
            if isinstance(v, dict) and not v:
                continue
            if isinstance(v, list) and not v:
                continue
            # Strip default trigger values
            if k in _TRIGGER_DEFAULTS and v == _TRIGGER_DEFAULTS[k]:
                continue
            cleaned[k] = v
        # Simplify trigger: if only 'type' remains, collapse to string
        if 'trigger' in cleaned and isinstance(cleaned['trigger'], dict):
            t = cleaned['trigger']
            if list(t.keys()) == ['type']:
                cleaned['trigger'] = t['type']
        return cleaned
    elif isinstance(d, list):
        return [_clean_definition_for_yaml(item) for item in d]
    else:
        return d


def make_report(
        experiment: str | dict | BILBO_ExperimentResult,
        output: str | None = None,
        format: str = 'html',
        states: list[str] | None = None,
        phase_style: str = 'bar',
        show: bool = True,
) -> 'Report':
    """
    Generate an HTML report for an experiment.

    Parameters
    ----------
    experiment : str | dict | BILBO_ExperimentResult
        Experiment data source:
        - str: Path to a .json file containing experiment data
        - dict: Dictionary containing experiment data
        - BILBO_ExperimentResult: Typed experiment result dataclass
    output : str | None
        Output file path. If None and show=True, opens in browser.
    format : str
        Output format: 'html' or 'pdf'.
    states : list[str] | None
        List of state names to plot. If None, plots all: ['theta', 'v', 'psi', 'psi_dot', 'x', 'y'].
    phase_style : str
        Style for phase visualization: 'bar' (default) or 'background'.
        - 'bar': Compact phase bar at bottom inside of plot
        - 'background': Full-height colored background regions with labels at top
    show : bool
        If True and output is None, opens the report in a viewer.

    Returns
    -------
    Report
        The Report object.

    Example
    -------
    >>> make_report("experiment_data.json")
    >>> make_report(experiment_dict, output="report.html")
    >>> make_report(experiment_data, states=['theta', 'v'], phase_style='background')
    """
    from pathlib import Path
    import json

    from core.utils.report import Report
    from core.utils.plotting.plot import Plot, Axis, AxisConfig
    from core.utils.plotting.map_plot import MapPlot
    from robots.bilbo.robot.bilbo_data import BILBO_STATE_DATA_DEFINITIONS

    # Load experiment data
    if isinstance(experiment, str):
        with open(experiment, 'r') as f:
            exp_dict = json.load(f)
    elif isinstance(experiment, BILBO_ExperimentResult):
        exp_dict = dataclasses.asdict(experiment)
    else:
        exp_dict = experiment

    # Extract key data (with None checks)
    exp_id = exp_dict.get('id', 'unknown')
    definition = exp_dict.get('definition') or {}
    meta = exp_dict.get('meta') or {}
    robot_context = exp_dict.get('robot_context') or {}
    samples = exp_dict.get('samples') or []
    actions_data = exp_dict.get('action_data') or {}
    logs_raw = exp_dict.get('logs') or []

    # Extract experiment status information
    exp_status = exp_dict.get('status', 'finished')
    error_message = exp_dict.get('error_message')

    # Derive error_action_id from action_data (find first action with status 'error')
    error_action_id = None
    for aid, adata in actions_data.items():
        a_status = adata.get('status', '') if isinstance(adata, dict) else ''
        if a_status in ('error', 'ERROR'):
            error_action_id = aid
            break

    # Determine if experiment was successful
    is_success = exp_status in ('finished', 'FINISHED')
    is_error = exp_status in ('error', 'ERROR')
    is_timeout = exp_status in ('timeout', 'TIMEOUT')
    is_aborted = exp_status in ('aborted', 'ABORTED')

    # Create status display info
    status_info = {
        'status': exp_status,
        'is_success': is_success,
        'is_error': is_error,
        'is_timeout': is_timeout,
        'is_aborted': is_aborted,
        'error_action_id': error_action_id,
        'error_message': error_message,
        'status_label': 'Success' if is_success else exp_status.upper() if isinstance(exp_status, str) else str(
            exp_status),
        'status_class': 'success' if is_success else 'error' if is_error else 'warning' if (
                    is_timeout or is_aborted) else 'unknown',
    }

    # Process logs: add level_name for display
    LOG_LEVEL_NAMES = {10: 'DEBUG', 20: 'INFO', 30: 'WARNING', 40: 'ERROR', 50: 'CRITICAL'}
    logs = []
    for log in logs_raw:
        level = log.get('level', 20)
        logs.append({
            'tick': log.get('tick', 0),
            'level': level,
            'level_name': LOG_LEVEL_NAMES.get(level, 'INFO'),
            'logger': log.get('logger', ''),
            'message': log.get('message', ''),
        })

    # Get description from definition or robot_context
    description = definition.get('description', '') if definition else ''
    if not description:
        description = robot_context.get('description', '') if robot_context else ''

    # Default states to plot
    if states is None:
        states = ['theta', 'theta_dot', 'v', 'psi', 'psi_dot', 'x', 'y']

    # Extract time vector and state data
    if len(samples) == 0:
        raise ValueError("No samples in experiment data")

    # Generate time vector like in plot_last_experiment (dt=0.01 = 100Hz)
    from core.utils.data import generate_time_vector_by_length
    t = generate_time_vector_by_length(start=0, num_samples=len(samples), dt=0.01)
    duration = len(samples) * 0.01  # n samples at 100Hz = n * dt

    # Extract state vectors from lowlevel.estimation.state (better resolution)
    state_data = {}
    for state_name in states:
        values = []
        for s in samples:
            # Use lowlevel.estimation.state for better resolution
            ll = s.get('lowlevel') or {}
            ll_est = ll.get('estimation') or {}
            ll_state = ll_est.get('state') or {}
            values.append(ll_state.get(state_name, 0.0) or 0.0)
        state_data[state_name] = np.array(values)

    # Process actions for display
    action_defs = definition.get('actions') or []
    actions_info = []
    phase_actions = []
    color_index = 0

    # First pass: identify group IDs to detect nested actions
    group_ids = set()
    for action_def in action_defs:
        if action_def is None:
            continue
        if action_def.get('type') == 'group':
            group_ids.add(action_def.get('id', ''))

    # Helper to check if an action is a sub-action of a group
    def is_sub_action(action_id: str) -> bool:
        for group_id in group_ids:
            if action_id.startswith(f"{group_id}_sub_"):
                return True
        return False

    # Helper to add action info (used recursively for groups)
    def process_action(action_def, index, is_nested=False, parent_sub_actions_data=None, depth=0):
        nonlocal color_index
        if action_def is None:
            return

        action_id = action_def.get('id', f'action_{index}')
        action_type = action_def.get('type', 'unknown')

        # Loops/while are expanded to groups at runtime — treat as group for processing
        if action_type in ('loop', 'while'):
            action_type = 'group'

        # Extract parameters - handle multiple formats:
        # 1. New dataclass format: {'type': 'set_velocity', 'params': {'forward': 0.5}}
        # 2. Full format: {'type': 'set_velocity', 'parameters': {'forward': 0.5}}
        # 3. Shorthand format: {'type': 'set_velocity', 'forward': 0.5}
        reserved_fields = {
            'id', 'type', 'tick', 'after', 'time', 'timeout', 'label', 'meta',
            'parameters', 'params', 'actions', 'sub_actions', 'wait_before', 'wait_after',
            'trigger', 'transitions', 'test', 'then_actions', 'else_actions',
            'count', 'variable', 'max_iterations',
        }
        if 'params' in action_def and isinstance(action_def['params'], dict):
            params = action_def['params']
        elif 'parameters' in action_def:
            params = action_def['parameters']
        else:
            # Collect all non-reserved fields as parameters (shorthand format)
            params = {k: v for k, v in action_def.items() if k not in reserved_fields}

        # Get timing and status from actions_data or parent's sub_actions
        if parent_sub_actions_data and action_id in parent_sub_actions_data:
            # Sub-action data is in parent's sub_actions field
            action_timing = parent_sub_actions_data.get(action_id) or {}
        else:
            # Top-level action data
            action_timing = actions_data.get(action_id) or {}

        start_time = action_timing.get('start_time')
        end_time = action_timing.get('end_time')
        start_tick = action_timing.get('start_tick') or 0
        end_tick = action_timing.get('end_tick') or 0

        # Get sub-actions data for group/parallel actions (for passing to nested processing)
        sub_actions_data = action_timing.get('sub_actions') or {}

        # Use parameters from action data if available (more accurate than definition)
        if action_timing.get('parameters'):
            params = action_timing.get('parameters')

        # Get action status and label
        action_status = action_timing.get('status', 'pending')
        action_error_message = action_timing.get('error_message')
        action_label = action_timing.get('label') or action_def.get('label')  # Prefer runtime data, fallback to definition
        action_meta = action_timing.get('meta') or action_def.get('meta')  # Prefer runtime data, fallback to definition
        # Use original_type from meta for display (e.g., 'loop', 'loop_iteration')
        display_type = (action_meta or {}).get('original_type', action_type)
        is_action_error = action_status in ('error', 'ERROR')
        is_action_success = action_status in ('completed', 'COMPLETED', 'finished', 'FINISHED')
        is_action_pending = action_status in ('pending', 'PENDING')

        # Check if this is the error action
        is_error_action_flag = (error_action_id == action_id)

        # Check if action spans multiple ticks (has duration)
        has_phase = (end_tick - start_tick) > 1 if start_tick is not None and end_tick is not None else False

        # Assign color for labeled actions with duration
        color = None
        if has_phase and action_label:
            color = PHASE_COLORS[color_index % len(PHASE_COLORS)]
            color_index += 1
            phase_actions.append({
                'id': action_id,
                'label': action_label,
                'type': action_type,
                'color': color,
                'start_time': start_time,
                'end_time': end_time,
                'label_layer': (action_meta or {}).get('label_layer', 0),
            })

        # Format parameters for display (exclude nested actions from params string for groups)
        params_for_display = {k: v for k, v in params.items() if k not in ('actions', 'actions_count')}
        params_str = _format_action_params(action_type, params_for_display)
        if action_type in ('group', 'parallel'):
            # Count sub-actions from data if available, otherwise from definition
            # Check both top-level 'actions' (new format) and params (old format)
            def_actions = action_def.get('actions', []) or action_def.get('sub_actions', []) or params.get('actions', []) or []
            num_sub_actions = len(sub_actions_data) if sub_actions_data else params.get('actions_count', len(def_actions))
            params_str = f"{num_sub_actions} actions"

        # Extract path points for set_path/set_waypoints actions
        waypoints = None
        if action_type in ('set_path', 'set_waypoints'):
            raw_points = params.get('points', params.get('waypoints', []))
            waypoints = []
            for pt in raw_points:
                if isinstance(pt, dict):
                    waypoints.append({
                        'x': pt.get('x', 0),
                        'y': pt.get('y', 0),
                    })
                elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    waypoints.append({
                        'x': pt[0],
                        'y': pt[1],
                    })

        actions_info.append({
            'index': index,
            'id': action_id,
            'type': display_type,
            'label': action_label,
            'params_str': params_str,
            'start_time': start_time,
            'end_time': end_time,
            'has_phase': has_phase,
            'color': color,
            'status': action_status,
            'is_error': is_action_error,
            'is_success': is_action_success,
            'is_pending': is_action_pending,
            'is_error_action': is_error_action_flag,
            'error_message': action_error_message,
            'is_nested': is_nested,
            'depth': depth,
            'is_group': action_type in ('group', 'parallel'),
            'waypoints': waypoints,
        })

        # If this is a group/parallel action, process its sub-actions
        if action_type in ('group', 'parallel') and sub_actions_data:
            # Process sub-actions using the data from parent's sub_actions field
            for sub_idx, (sub_action_id, sub_action_data) in enumerate(sub_actions_data.items()):
                sub_params = sub_action_data.get('parameters') or {}

                # Get action type from data (preferred) or infer from parameters
                sub_action_type = sub_action_data.get('action_type')
                if not sub_action_type:
                    sub_action_type = _infer_type_from_params(sub_params)

                # Create a synthetic action def for processing
                sub_action_def = {
                    'id': sub_action_id,
                    'type': sub_action_type,
                    'label': sub_action_data.get('label'),
                    'parameters': sub_params,
                }
                process_action(sub_action_def, f"{index}.{sub_idx}", is_nested=True, parent_sub_actions_data=sub_actions_data, depth=depth + 1)
        elif action_type in ('group', 'parallel'):
            # Fallback: use definition-based sub-actions (when no runtime data available)
            # Look for 'actions' at top level (new format) or in params (old format)
            sub_actions_defs = action_def.get('actions', []) or action_def.get('sub_actions', []) or params.get('actions', []) or []
            for sub_idx, sub_action in enumerate(sub_actions_defs):
                sub_action_id = sub_action.get('id', f"{action_id}_sub_{sub_idx}")
                sub_action_with_id = dict(sub_action)
                sub_action_with_id['id'] = sub_action_id
                process_action(sub_action_with_id, f"{index}.{sub_idx}", is_nested=True, parent_sub_actions_data=None, depth=depth + 1)

    def _infer_type_from_params(params: dict) -> str:
        """Try to infer action type from parameters."""
        # Check for common parameter patterns
        if 'mode' in params:
            return 'set_mode'
        if 'forward' in params or 'turn' in params:
            return 'set_velocity'
        if 'time' in params:
            return 'wait_time'
        if 'ticks' in params:
            return 'wait_ticks'
        if 'frequency' in params:
            return 'beep'
        if 'text' in params:
            return 'speak'
        if 'x' in params and 'y' in params:
            return 'move_to'
        if 'heading' in params or 'heading_deg' in params:
            return 'turn_to'
        if 'input' in params:
            return 'set_input'
        if 'points' in params:
            return 'set_path'
        if 'waypoints' in params:
            return 'set_waypoints'
        if 'K' in params:
            return 'set_feedback_gain'
        return 'unknown'

    for i, action_def in enumerate(action_defs):
        process_action(action_def, i, is_nested=False, parent_sub_actions_data=None)

    # Phase bar height as fraction of plot (used for ylim adjustment)
    PHASE_BAR_HEIGHT = 0.07

    # Helper to calculate ylim with padding for phase bar
    # Determine the number of phase bar layers needed
    num_phase_layers = max((p.get('label_layer', 0) for p in phase_actions), default=0) + 1 if phase_actions else 1

    def calc_ylim_with_phase_padding(*data_arrays):
        """Calculate ylim that leaves room for phase bar at bottom."""
        all_data = np.concatenate([d for d in data_arrays if len(d) > 0])
        y_min, y_max = np.min(all_data), np.max(all_data)
        y_range = y_max - y_min
        if y_range == 0:
            y_range = 1.0  # Avoid division by zero
        # Add padding: small margin at top, larger at bottom for phase bar(s)
        padding_top = 0.05 * y_range
        total_phase_height = PHASE_BAR_HEIGHT * num_phase_layers
        padding_bottom = (total_phase_height / (1 - total_phase_height)) * y_range + 0.05 * y_range
        return (y_min - padding_bottom, y_max + padding_top)

    # Helper to add phase visualization to an axis
    def add_phases_to_axis(axis):
        if not phase_actions:
            return
        if phase_style == 'bar':
            # Phase bar at bottom inside
            axis.configure_phase_bar(
                position="bottom_inside",
                height=PHASE_BAR_HEIGHT,
                fontsize=11,
                corner_radius=0.01,
                horizontal_padding=0.002,
            )
            for phase in phase_actions:
                if phase['start_time'] is not None and phase['end_time'] is not None:
                    axis.add_phase(
                        phase['label'],
                        start=phase['start_time'],
                        end=phase['end_time'],
                        color=phase['color'],
                        layer=phase.get('label_layer', 0),
                    )
        else:
            # Phase background with labels at top
            axis.configure_phase_background(
                show_labels=True,
                alpha=0.2,
                label_position="top",
                fontsize=11,
                label_box=True,
                label_box_alpha=0.8,
            )
            for phase in phase_actions:
                if phase['start_time'] is not None and phase['end_time'] is not None:
                    axis.add_background_phase(
                        phase_id=phase['label'],
                        start=phase['start_time'],
                        end=phase['end_time'],
                        color=phase['color'],
                    )

    # Create plots
    plots = []
    for state_name in states:
        if state_name not in state_data:
            continue

        y = state_data[state_name]
        state_def = BILBO_STATE_DATA_DEFINITIONS.get(state_name, {})
        unit = state_def.get('unit', '')
        ylabel = f"{state_name} [{unit}]" if unit else state_name

        # Calculate ylim with padding for phase bar if needed
        ylim = calc_ylim_with_phase_padding(y) if (phase_style == 'bar' and phase_actions) else None

        # Create plot - wider aspect ratio, taller, transparent background
        p = Plot(rows=1, columns=1, size=(10, 3.5), use_agg_backend=True, facealpha=0)
        axis = Axis(id="main", config=AxisConfig(
            xlabel="Time [s]",
            ylabel=ylabel,
            grid=True,
            label_font_size=14,
            tick_font_size=12,
            facecolor='none',
            xlim=(t[0], t[-1]),  # No white space on left/right
            ylim=ylim,
        ))
        p.set_axis(1, 1, axis)

        # Add phase visualization
        add_phases_to_axis(axis)

        # Plot state data with thicker line
        axis.plot(t, y, color='#2c3e50', linewidth=1.8)

        plots.append({
            'title': ylabel,
            'image': p,
        })

    # Create trajectory map plot
    trajectory_map = None
    if 'x' in state_data and 'y' in state_data:
        x_data = state_data['x']
        y_data = state_data['y']

        # Get testbed size from robot_context
        # Structure: testbed_config -> config -> size (TestbedSize with x_min/x_max/y_min/y_max)
        testbed_data = robot_context.get('testbed_config') or {}
        testbed_cfg = testbed_data.get('config') or testbed_data
        testbed_size = testbed_cfg.get('size') if isinstance(testbed_cfg, dict) else None

        if isinstance(testbed_size, dict):
            x_min = testbed_size.get('x_min', -2.0)
            x_max = testbed_size.get('x_max', 2.0)
            y_min = testbed_size.get('y_min', -2.0)
            y_max = testbed_size.get('y_max', 2.0)
        else:
            x_min, x_max = -2.0, 2.0
            y_min, y_max = -2.0, 2.0

        # Create map plot
        map_plot = MapPlot(
            size=((x_min, x_max), (y_min, y_max)),
            padding=0.15,
            border_corner_radius=0.05,
        )
        map_plot.add_grid(major=1.0, minor=0.25, major_opacity=0.4, minor_opacity=0.8)
        map_plot.add_coordinate_system(length=0.3)

        # Add trajectory with gradient
        map_plot.add_trajectory(
            x_data, y_data,
            gradient=True,
            gradient_cmap='viridis',
            width=2.5,
            show_start=True,
            show_end=True,
            start_color='green',
            end_color='red',
        )

        # Render and store
        map_plot.render()
        trajectory_map = map_plot

    # Create control plots from lowlevel.control
    control_plots = []

    # Helper to create a dual-line plot (left/right or similar)
    def create_control_plot(title: str, data1: np.ndarray, data2: np.ndarray,
                            label1: str, label2: str, ylabel: str) -> Plot:
        # Calculate ylim with padding for phase bar if needed
        ylim = calc_ylim_with_phase_padding(data1, data2) if (phase_style == 'bar' and phase_actions) else None

        p = Plot(rows=1, columns=1, size=(10, 3.5), use_agg_backend=True, facealpha=0)
        axis = Axis(id="main", config=AxisConfig(
            xlabel="Time [s]",
            ylabel=ylabel,
            grid=True,
            label_font_size=14,
            tick_font_size=12,
            facecolor='none',
            xlim=(t[0], t[-1]),
            ylim=ylim,
            legend=True,
        ))
        p.set_axis(1, 1, axis)

        # Add phase visualization
        add_phases_to_axis(axis)

        axis.plot(t, data1, color='#e74c3c', linewidth=1.8, label=label1)
        axis.plot(t, data2, color='#3498db', linewidth=1.8, label=label2)
        return p

    # Helper to create a dual y-axis plot (for velocity_command)
    def create_dual_yaxis_plot(title: str, data1: np.ndarray, data2: np.ndarray,
                               label1: str, label2: str, ylabel1: str, ylabel2: str) -> Plot:
        # Calculate ylim with padding for phase bar if needed
        ylim1 = calc_ylim_with_phase_padding(data1) if (phase_style == 'bar' and phase_actions) else None

        p = Plot(rows=1, columns=1, size=(10, 3.5), use_agg_backend=True, facealpha=0)
        axis = Axis(id="main", config=AxisConfig(
            xlabel="Time [s]",
            ylabel=ylabel1,
            grid=True,
            label_font_size=14,
            tick_font_size=12,
            facecolor='none',
            xlim=(t[0], t[-1]),
            ylim=ylim1,
        ))
        p.set_axis(1, 1, axis)

        # Add phase visualization
        add_phases_to_axis(axis)

        # Plot first data on primary axis
        axis.plot(t, data1, color='#e74c3c', linewidth=1.8, label=label1)
        line1 = axis.ax.get_lines()[-1]

        # Create secondary y-axis
        ax2 = axis.ax.twinx()
        ax2.set_ylabel(ylabel2, fontsize=14, color='#3498db')
        ax2.tick_params(axis='y', labelcolor='#3498db', labelsize=12)
        line2, = ax2.plot(t, data2, color='#3498db', linewidth=1.8, label=label2)

        # Set ylim for secondary axis with phase bar padding
        if phase_style == 'bar' and phase_actions:
            ylim2 = calc_ylim_with_phase_padding(data2)
            ax2.set_ylim(ylim2)

        # Combined legend
        axis.ax.legend([line1, line2], [label1, label2], loc='upper right', fontsize=10)

        return p

    # Extract control data from samples
    def extract_control_data(path: list[str]) -> np.ndarray:
        values = []
        for s in samples:
            ll = s.get('lowlevel') or {}
            ctrl = ll.get('control') or {}
            val = ctrl
            for key in path:
                val = (val.get(key) if isinstance(val, dict) else None) or {}
            values.append(val if isinstance(val, (int, float)) else 0.0)
        return np.array(values)

    # control mode (step plot with named ticks)
    mode_data = extract_control_data(['mode'])
    if np.any(mode_data):
        MODE_NAMES = {0: 'OFF', 1: 'DIRECT', 2: 'BALANCING', 3: 'VELOCITY', 4: 'POSITION'}
        mode_values_present = sorted(set(int(v) for v in mode_data))
        yticks = [float(v) for v in mode_values_present]
        yticklabels = [MODE_NAMES.get(v, str(v)) for v in mode_values_present]
        y_pad = 0.5
        ylim_mode = (min(mode_values_present) - y_pad, max(mode_values_present) + y_pad)

        p = Plot(rows=1, columns=1, size=(10, 3.5), use_agg_backend=True, facealpha=0)
        axis = Axis(id="main", config=AxisConfig(
            xlabel="Time [s]",
            ylabel="Control Mode",
            grid=True,
            label_font_size=14,
            tick_font_size=12,
            facecolor='none',
            xlim=(t[0], t[-1]),
            ylim=ylim_mode,
            yticks=yticks,
            yticklabels=yticklabels,
            legend=False,
        ))
        p.set_axis(1, 1, axis)
        add_phases_to_axis(axis)
        axis.plot(t, mode_data, color='#2c3e50', linewidth=1.8, stairs=True)
        control_plots.append({
            'title': 'Control Mode',
            'image': p,
        })

    # control mode vs LL tick
    ll_ticks = np.array([
        (s.get('lowlevel') or {}).get('tick', 0)
        for s in samples
    ], dtype=float)
    if np.any(mode_data) and np.any(ll_ticks):
        p_tick = Plot(rows=1, columns=1, size=(10, 3.5), use_agg_backend=True, facealpha=0)
        axis_tick = Axis(id="main", config=AxisConfig(
            xlabel="LL Tick",
            ylabel="Control Mode",
            grid=True,
            label_font_size=14,
            tick_font_size=12,
            facecolor='none',
            xlim=(ll_ticks[0], ll_ticks[-1]),
            ylim=ylim_mode,
            yticks=yticks,
            yticklabels=yticklabels,
            legend=False,
        ))
        p_tick.set_axis(1, 1, axis_tick)
        add_phases_to_axis(axis_tick)
        axis_tick.plot(ll_ticks, mode_data, color='#2c3e50', linewidth=1.8, stairs=True)
        control_plots.append({
            'title': 'Control Mode (LL Tick)',
            'image': p_tick,
        })

    # velocity_command: v and psi_dot (dual y-axis)
    vel_cmd_v = extract_control_data(['velocity_command', 'v'])
    vel_cmd_psi_dot = extract_control_data(['velocity_command', 'psi_dot'])
    if np.any(vel_cmd_v) or np.any(vel_cmd_psi_dot):
        control_plots.append({
            'title': 'Velocity Command',
            'image': create_dual_yaxis_plot(
                'Velocity Command', vel_cmd_v, vel_cmd_psi_dot,
                'v', 'psi_dot', 'v [m/s]', 'psi_dot [rad/s]'
            ),
        })

    # velocity_output: u_l and u_r
    vel_out_l = extract_control_data(['velocity_output', 'u_l'])
    vel_out_r = extract_control_data(['velocity_output', 'u_r'])
    if np.any(vel_out_l) or np.any(vel_out_r):
        control_plots.append({
            'title': 'Velocity Output',
            'image': create_control_plot(
                'Velocity Output', vel_out_l, vel_out_r,
                'left', 'right', 'u'
            ),
        })

    # input_ext: u_left and u_right
    inp_ext_l = extract_control_data(['input_ext', 'u_left'])
    inp_ext_r = extract_control_data(['input_ext', 'u_right'])
    if np.any(inp_ext_l) or np.any(inp_ext_r):
        control_plots.append({
            'title': 'External Input',
            'image': create_control_plot(
                'External Input', inp_ext_l, inp_ext_r,
                'left', 'right', 'u'
            ),
        })

    # balancing_output: u_1 and u_2
    bal_out_1 = extract_control_data(['balancing_output', 'u_1'])
    bal_out_2 = extract_control_data(['balancing_output', 'u_2'])
    if np.any(bal_out_1) or np.any(bal_out_2):
        control_plots.append({
            'title': 'Balancing Output',
            'image': create_control_plot(
                'Balancing Output', bal_out_1, bal_out_2,
                'left', 'right', 'u'
            ),
        })

    # output: u_left and u_right
    out_l = extract_control_data(['output', 'u_left'])
    out_r = extract_control_data(['output', 'u_right'])
    if np.any(out_l) or np.any(out_r):
        control_plots.append({
            'title': 'Control Output',
            'image': create_control_plot(
                'Control Output', out_l, out_r,
                'left', 'right', 'u'
            ),
        })

    # Extract control configuration from robot_context
    control_config = _extract_control_config(robot_context)

    # Generate YAML representation of the experiment definition
    experiment_yaml_raw = ''
    experiment_yaml_highlighted = ''
    if definition:
        try:
            # Prefer the original source dict (preserves loop syntax, shorthand, etc.)
            source = definition.get('source_dict') or definition
            # Strip internal fields and clean up null/empty values
            yaml_dict = {k: v for k, v in source.items() if not k.startswith('_') and k != 'source_dict'}
            yaml_dict = _clean_definition_for_yaml(yaml_dict)
            experiment_yaml_raw = yaml.dump(yaml_dict, default_flow_style=False, sort_keys=False)
            experiment_yaml_highlighted = _highlight_yaml(experiment_yaml_raw)
        except Exception as e:
            # If YAML generation fails, just skip it
            experiment_yaml_raw = f"# Error generating YAML: {e}"
            experiment_yaml_highlighted = f'<span class="yaml-comment"># Error generating YAML: {e}</span>'

    # Load template and render — template is in parent (experiment/) directory's templates/ folder
    template_path = Path(__file__).parent.parent / "templates" / "experiment_report_template.html"
    report = Report(template_path, plot_dpi=120, plot_width="100%")

    report.render(
        title=f"Experiment Report: {exp_id}",
        experiment_id=exp_id,
        description=description,
        date=meta.get('datetime', ''),
        num_samples=len(samples),
        duration=duration,
        status=status_info,
        actions=actions_info,
        phase_actions=phase_actions,
        plots=plots,
        control_plots=control_plots,
        trajectory_map=trajectory_map,
        control_config=control_config,
        logs=logs,
        experiment_yaml=bool(experiment_yaml_raw),
        experiment_yaml_raw=experiment_yaml_raw,
        experiment_yaml_highlighted=experiment_yaml_highlighted,
    )

    # Output
    if output:
        if format == 'pdf':
            report.save_pdf(output)
        else:
            report.save_html(output)
    elif show:
        if format == 'pdf':
            report.show_pdf()
        else:
            report.show_html()

    return report


def read_experiment_data(file: str) -> BILBO_ExperimentResult:
    """Read experiment data from a JSON file and deserialize to BILBO_ExperimentResult."""
    if not file_exists(file):
        raise FileNotFoundError(f"Experiment data file not found: {file}")

    data_dict = readJSON(file)

    data = from_dict_auto(BILBO_ExperimentResult, data_dict)

    return data


def _highlight_yaml(yaml_str: str) -> str:
    """Apply HTML syntax highlighting to YAML string."""
    import html
    lines = yaml_str.split('\n')
    highlighted_lines = []

    for line in lines:
        # Escape HTML entities first
        escaped = html.escape(line)

        # Check if it's a comment
        stripped = escaped.strip()
        if stripped.startswith('#'):
            highlighted_lines.append(f'<span class="yaml-comment">{escaped}</span>')
            continue

        # Check for key: value pattern
        if ':' in escaped:
            colon_idx = escaped.index(':')
            # Check if there's content after the colon
            key_part = escaped[:colon_idx]
            rest = escaped[colon_idx:]

            # Highlight the key
            highlighted = f'<span class="yaml-key">{key_part}</span>'

            # Check what comes after the colon
            value_part = rest[1:].strip() if len(rest) > 1 else ''

            if value_part:
                # It's a key: value on same line
                if value_part.startswith("'") or value_part.startswith('"'):
                    # String value
                    highlighted += f':<span class="yaml-string"> {value_part}</span>'
                elif value_part in ('true', 'false', 'True', 'False'):
                    # Boolean
                    highlighted += f':<span class="yaml-boolean"> {value_part}</span>'
                elif value_part in ('null', 'None', '~'):
                    # Null
                    highlighted += f':<span class="yaml-null"> {value_part}</span>'
                elif value_part.replace('.', '').replace('-', '').replace('e', '').replace('E', '').isdigit():
                    # Number (including floats and scientific notation)
                    highlighted += f':<span class="yaml-number"> {value_part}</span>'
                else:
                    # Unquoted string or other
                    highlighted += f':<span class="yaml-string"> {value_part}</span>'
            else:
                # Just key: with nothing after (nested object or list follows)
                highlighted += ':'

            highlighted_lines.append(highlighted)
        elif stripped.startswith('-'):
            # List item
            indent = len(escaped) - len(escaped.lstrip())
            marker_idx = escaped.index('-')
            indent_part = escaped[:marker_idx]
            rest = escaped[marker_idx + 1:].strip()

            highlighted = f'{indent_part}<span class="yaml-list-marker">-</span>'
            if rest:
                # Check if it's a key: value after the list marker
                if ':' in rest:
                    highlighted += ' ' + _highlight_yaml(rest).strip()
                else:
                    highlighted += f'<span class="yaml-string"> {rest}</span>'
            highlighted_lines.append(highlighted)
        else:
            # Plain text (likely a string value continuation)
            highlighted_lines.append(f'<span class="yaml-string">{escaped}</span>' if escaped.strip() else escaped)

    return '\n'.join(highlighted_lines)


def _safe_float(value, default=0.0):
    """Safely convert a value to float, returning default if conversion fails."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _extract_control_config(robot_context: dict) -> dict | None:
    """Extract and structure control config from robot_context for report display.

    Returns a dict with sections ready for template rendering, or None if no config available.
    """
    cc = (robot_context.get('control_config') or {}) if robot_context else {}
    if not cc:
        return None

    def _fmt(val, decimals=4):
        """Format a numeric value for display."""
        if isinstance(val, bool):
            return str(val)
        if isinstance(val, float):
            # Use fewer decimals for cleaner display
            if val == 0.0:
                return '0'
            if abs(val) >= 100:
                return f'{val:.1f}'
            if abs(val) >= 1:
                return f'{val:.{min(decimals, 3)}f}'.rstrip('0').rstrip('.')
            return f'{val:.{decimals}f}'.rstrip('0').rstrip('.')
        if isinstance(val, list):
            return '[' + ', '.join(_fmt(v) for v in val) + ']'
        return str(val)

    def _p(label: str, name: str) -> str:
        """Prefix a parameter name with an optional label."""
        return f'{label} {name}' if label else name

    def _pid_rows(pid: dict, label: str) -> list[dict]:
        """Create display rows for a PID config."""
        if not pid:
            return []
        rows = []
        rows.append({'name': _p(label, 'Kp'), 'value': _fmt(pid.get('Kp', 0)), 'unit': ''})
        rows.append({'name': _p(label, 'Ki'), 'value': _fmt(pid.get('Ki', 0)), 'unit': ''})
        rows.append({'name': _p(label, 'Kd'), 'value': _fmt(pid.get('Kd', 0)), 'unit': ''})
        if pid.get('enable_output_limit'):
            rows.append({'name': _p(label, 'Output limit'), 'value': _fmt(pid.get('output_limit', 0)), 'unit': ''})
        if pid.get('enable_i_limit'):
            rows.append({'name': _p(label, 'I-term limit'), 'value': _fmt(pid.get('i_term_limit', 0)), 'unit': ''})
        if pid.get('enable_d_filter'):
            rows.append({'name': _p(label, 'D-filter Td'), 'value': _fmt(pid.get('Td_filter', 0)), 'unit': 's'})
        if pid.get('enable_rate_limit'):
            rows.append({'name': _p(label, 'Rate limit'), 'value': _fmt(pid.get('rate_limit', 0)), 'unit': ''})
        if pid.get('enable_setpoint_rate_limit'):
            rows.append({'name': _p(label, 'SP rate limit'), 'value': _fmt(pid.get('setpoint_rate_limit', 0)), 'unit': ''})
        return rows

    def _ff_rows(ff: dict, label: str) -> list[dict]:
        """Create display rows for a Feedforward config."""
        if not ff:
            return []
        rows = []
        rows.append({'name': _p(label, 'Kv'), 'value': _fmt(ff.get('Kv', 0)), 'unit': ''})
        rows.append({'name': _p(label, 'Ka'), 'value': _fmt(ff.get('Ka', 0)), 'unit': ''})
        if ff.get('Kc', 0) != 0 or ff.get('enable_stiction'):
            rows.append({'name': _p(label, 'Kc'), 'value': _fmt(ff.get('Kc', 0)), 'unit': ''})
        if ff.get('enable_vref_slew'):
            rows.append({'name': _p(label, 'Vref slew'), 'value': _fmt(ff.get('vref_slew_rate', 0)), 'unit': ''})
        if ff.get('enable_stiction'):
            rows.append({'name': _p(label, 'v0 stiction'), 'value': _fmt(ff.get('v0_stiction', 0)), 'unit': 'm/s'})
            rows.append({'name': _p(label, 'v decay'), 'value': _fmt(ff.get('v_decay_stiction', 0)), 'unit': ''})
        if ff.get('enable_output_limit'):
            rows.append({'name': _p(label, 'Output limit'), 'value': _fmt(ff.get('output_limit', 0)), 'unit': ''})
        return rows

    sections = []

    # General
    general = cc.get('general') or {}
    if general:
        sections.append({
            'title': 'General',
            'rows': [
                {'name': 'Max wheel speed', 'value': _fmt(general.get('max_wheel_speed', 0)), 'unit': 'rad/s'},
                {'name': 'Max wheel torque', 'value': _fmt(general.get('max_wheel_torque', 0)), 'unit': 'Nm'},
                {'name': 'External inputs', 'value': str(general.get('enable_external_inputs', False)), 'unit': ''},
                {'name': 'Torque offset', 'value': _fmt(general.get('torque_offset', [0, 0])), 'unit': 'Nm'},
            ],
        })

    # Balancing control
    bal = cc.get('balancing_control') or {}
    if bal:
        rows = []
        # K vector as separate matrix display (split into rows of 4)
        K = bal.get('K', [])
        k_matrix = None
        if K:
            k_matrix = []
            for i in range(0, len(K), 4):
                k_matrix.append([_fmt(v) for v in K[i:i+4]])

        tic = bal.get('tic') or {}
        rows.append({'subsection': 'Theta Integral (TIC)'})
        if tic.get('enabled'):
            rows.append({'name': 'Ki', 'value': _fmt(tic.get('ki', 0)), 'unit': ''})
            rows.append({'name': 'Max torque', 'value': _fmt(tic.get('max_torque', 0)), 'unit': 'Nm'})
            rows.append({'name': 'Theta limit', 'value': _fmt(tic.get('theta_limit', 0)), 'unit': 'rad'})
        else:
            rows.append({'name': 'Status', 'value': 'disabled', 'unit': ''})

        vic = bal.get('vic') or {}
        rows.append({'subsection': 'Velocity Integral (VIC)'})
        if vic.get('enabled'):
            rows.append({'name': 'Ki', 'value': _fmt(vic.get('ki', 0)), 'unit': ''})
            rows.append({'name': 'Max torque', 'value': _fmt(vic.get('max_torque', 0)), 'unit': 'Nm'})
            rows.append({'name': 'v limit', 'value': _fmt(vic.get('v_limit', 0)), 'unit': 'm/s'})
        else:
            rows.append({'name': 'Status', 'value': 'disabled', 'unit': ''})

        psi = bal.get('psi') or {}
        rows.append({'subsection': 'Yaw (PSI)'})
        if psi.get('enabled'):
            rows.append({'name': 'Kp', 'value': _fmt(psi.get('kp', 0)), 'unit': ''})
            rows.append({'name': 'Ki', 'value': _fmt(psi.get('ki', 0)), 'unit': ''})
            rows.append({'name': 'Max torque', 'value': _fmt(psi.get('max_torque', 0)), 'unit': 'Nm'})
        else:
            rows.append({'name': 'Status', 'value': 'disabled', 'unit': ''})

        sections.append({'title': 'Balancing Control', 'rows': rows, 'k_matrix': k_matrix})

    # Velocity control
    vel = cc.get('velocity_control') or {}
    if vel:
        rows = []
        v_cfg = vel.get('v') or {}
        v_pid = _pid_rows(v_cfg.get('pid') or {}, '')
        v_ff = _ff_rows(v_cfg.get('feedforward') or {}, '')
        if v_pid or v_ff:
            rows.append({'subsection': 'Forward velocity (v) — PID'})
            rows.extend(v_pid)
            rows.append({'subsection': 'Forward velocity (v) — Feedforward'})
            rows.extend(v_ff)

        psidot_cfg = vel.get('psidot') or {}
        psi_pid = _pid_rows(psidot_cfg.get('pid') or {}, '')
        psi_ff = _ff_rows(psidot_cfg.get('feedforward') or {}, '')
        if psi_pid or psi_ff:
            rows.append({'subsection': 'Yaw rate (ψ̇) — PID'})
            rows.extend(psi_pid)
            rows.append({'subsection': 'Yaw rate (ψ̇) — Feedforward'})
            rows.extend(psi_ff)

        if rows:
            sections.append({'title': 'Velocity Control', 'rows': rows})

    # Position control
    pos = cc.get('position_control') or {}
    if pos:
        rows = [
            {'name': 'kp angular', 'value': _fmt(pos.get('kp_angular', 0)), 'unit': 'rad/s / rad'},
            {'name': 'ki angular', 'value': _fmt(pos.get('ki_angular', 0)), 'unit': 'rad/s / rad·s'},
            {'name': 'kp linear', 'value': _fmt(pos.get('kp_linear', 0)), 'unit': '1/s'},
            {'name': 'ki linear', 'value': _fmt(pos.get('ki_linear', 0)), 'unit': '1/s²'},
            {'name': 'kd linear', 'value': _fmt(pos.get('kd_linear', 0)), 'unit': ''},
            {'name': 'Max speed', 'value': _fmt(pos.get('max_speed', 0)), 'unit': 'm/s'},
            {'name': 'Max turn rate', 'value': _fmt(pos.get('max_turn_rate', 0)), 'unit': 'rad/s'},
            {'name': 'Lookahead base', 'value': _fmt(pos.get('lookahead_base', 0)), 'unit': 'm'},
            {'name': 'Lookahead min', 'value': _fmt(pos.get('lookahead_min', 0)), 'unit': 'm'},
            {'name': 'Arrival tolerance', 'value': _fmt(pos.get('arrival_tolerance', 0)), 'unit': 'm'},
            {'name': 'Arrival dwell', 'value': _fmt(pos.get('arrival_dwell_time', 0)), 'unit': 's'},
            {'name': 'Decel limit', 'value': _fmt(pos.get('decel_limit', 0)), 'unit': 'm/s²'},
            {'name': 'Curvature gain', 'value': _fmt(pos.get('curvature_gain', 0)), 'unit': ''},
            {'name': 'Curvature lookahead', 'value': _fmt(pos.get('curvature_lookahead', 0)), 'unit': 'm'},
        ]
        sections.append({'title': 'Position Control', 'rows': rows})

    if not sections:
        return None

    return {
        'name': cc.get('name', ''),
        'description': cc.get('description', ''),
        'sections': sections,
    }


def _format_action_params(action_type: str, params: dict) -> str:
    """Format action parameters for display."""
    if not params:
        return ""

    try:
        # Special formatting for common action types
        if action_type == 'set_mode':
            return f"mode={params.get('mode', '?')}"
        elif action_type == 'set_velocity':
            fwd = params.get('forward', 0)
            turn = params.get('turn', 0)
            return f"v={fwd}, turn={turn}"
        elif action_type == 'wait_time':
            t = params.get('time', params.get('time_ms', 0))
            if isinstance(t, (int, float)):
                return f"{float(t):.2f}s"
            return f"{t}"
        elif action_type == 'wait_ticks':
            return f"{params.get('ticks', 0)} ticks"
        elif action_type == 'beep':
            freq = params.get('frequency', 1000)
            ms = params.get('time_ms', 250)
            return f"{freq}Hz, {ms}ms"
        elif action_type == 'speak':
            text = params.get('text', '')
            if len(text) > 40:
                text = text[:37] + '...'
            return f'"{text}"'
        elif action_type == 'move_to':
            x = _safe_float(params.get('x', 0))
            y = _safe_float(params.get('y', 0))
            return f"({x:.2f}, {y:.2f})"
        elif action_type == 'turn_to':
            if 'heading_deg' in params:
                return f"{_safe_float(params['heading_deg']):.1f} deg"
            return f"{_safe_float(params.get('heading', 0)):.2f} rad"
        elif action_type in ('set_path', 'set_waypoints'):
            points = params.get('points', params.get('waypoints', []))
            return f"{len(points)} path points"
        elif action_type == 'start_path':
            parts = []
            if _safe_float(params.get('max_speed', 0)) > 0:
                parts.append(f"speed={params['max_speed']}")
            if _safe_float(params.get('timeout', 0)) > 0:
                parts.append(f"timeout={params['timeout']}s")
            if params.get('allow_reverse'):
                parts.append("reverse=yes")
            return ", ".join(parts) if parts else ""
        elif action_type == 'run_trajectory':
            traj = params.get('input_trajectory', {})
            if isinstance(traj, dict):
                name = traj.get('name', 'unnamed')
                return f"trajectory: {name}"
            return "trajectory"
        elif action_type == 'set_input':
            inp = params.get('input', [0, 0])
            if isinstance(inp, str):
                return inp  # Unresolved expression — show as-is
            if isinstance(inp, (list, tuple)) and len(inp) >= 2:
                return f"[{_safe_float(inp[0]):.3f}, {_safe_float(inp[1]):.3f}]"
            return str(inp)
        elif action_type == 'set_feedback_gain':
            K = params.get('K', [])
            if len(K) > 4:
                return f"K=[{_safe_float(K[0]):.2f}, {_safe_float(K[1]):.2f}, ... ({len(K)} elements)]"
            return f"K={K}"
        else:
            # Generic formatting
            parts = []
            for k, v in params.items():
                if isinstance(v, float):
                    parts.append(f"{k}={v:.3f}")
                elif isinstance(v, (list, dict)) and len(str(v)) > 30:
                    parts.append(f"{k}=...")
                else:
                    parts.append(f"{k}={v}")
            return ", ".join(parts[:3])  # Limit to 3 params
    except Exception:
        # Fallback: just show params as-is rather than crashing report generation
        return str(params)[:80]
