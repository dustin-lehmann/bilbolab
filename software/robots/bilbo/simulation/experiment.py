"""
Lightweight experiment system for BILBO_CompleteAgent.

NOTE: This module does NOT use the core.utils.experiments framework that
the on-robot software and the host-side experiment handler use. It is a
standalone, simplified reimplementation for simulation purposes only.
If you are looking for the production experiment architecture (with
ActionRegistry, guards, requirements, expression engine, etc.), see
core.utils.experiments and robots/bilbo/software/robot/experiment/.

Mirrors the real robot's experiment builder/runner pattern but executes
directly on the simulation agent. Actions run sequentially; each action
starts, is polled for completion each tick, and advances to the next.

Usage — builder API::

    from robots.bilbo.simulation.experiment import ExperimentBuilder

    exp = (ExperimentBuilder()
           .move_to(1.0, 1.0, max_speed=0.5)
           .wait(2.0)
           .run_trajectory(u)
           .move_to(0.0, 0.0, target_heading=0)
           .build())

    agent.run_experiment(exp)

Usage — YAML file (same format as real robot experiments)::

    agent.run_experiment_from_file('my_experiment.yaml')
"""

from __future__ import annotations

import dataclasses
import json
import logging
import math
import os
from dataclasses import field
from typing import Any, Callable, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from robots.bilbo.simulation.agent import BILBO_CompleteAgent

from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from robots.bilbo.robot.experiment.experiment_definitions import read_input_file, InputTrajectory
from robots.bilbo.simulation.model import BILBO_3D_Input
from core.utils.dataclass_utils import from_dict_auto

logger = logging.getLogger(__name__)


# ======================================================================================================================
# Action descriptor
# ======================================================================================================================

@dataclasses.dataclass
class ExperimentAction:
    """A single action in a simulation experiment."""
    type: str
    params: dict[str, Any] = field(default_factory=dict)
    label: str = ''
    timeout: float = 0.0


# ======================================================================================================================
# Helpers
# ======================================================================================================================

def _parse_time_seconds(value) -> float:
    """Parse a time value to seconds. Accepts int (ms), float (s), or strings like '2s', '500ms'."""
    if isinstance(value, str):
        v = value.strip()
        if v.endswith('ms'):
            return float(v[:-2]) / 1000.0
        if v.endswith('s'):
            return float(v[:-1])
        return float(v) / 1000.0  # bare string → ms
    if isinstance(value, int):
        return value / 1000.0
    return float(value)


def _load_trajectory(value, source_dir: str | None):
    """Resolve a trajectory value: string (.bitrj path), dict, or passthrough."""
    if isinstance(value, str):
        path = value
        if not path.endswith('.bitrj'):
            path += '.bitrj'
        if source_dir and not os.path.isabs(path):
            path = os.path.join(source_dir, path)
        file_data = read_input_file(path)
        if file_data is None:
            raise FileNotFoundError(f"Failed to load trajectory: {path}")
        return file_data.to_trajectory()
    if isinstance(value, dict):
        return from_dict_auto(InputTrajectory, value)
    return value  # Already an InputTrajectory or numpy array


def _action_from_dict(d: dict, source_dir: str | None = None) -> list[ExperimentAction]:
    """Convert a YAML action dict to one or more ExperimentAction objects.

    Handles wait_before/wait_after by inserting extra wait actions.
    """
    actions: list[ExperimentAction] = []
    action_type = d.get('type', '')

    # Insert wait_before
    wb = d.get('wait_before')
    if wb is not None:
        secs = _parse_time_seconds(wb)
        if secs > 0:
            actions.append(ExperimentAction(type='wait', params={'seconds': secs},
                                            label=f'Wait {secs:.2f}s (before)'))

    timeout = float(d.get('timeout', 0.0))
    label = d.get('label', '')

    # Reserved keys that are not action parameters
    _RESERVED = {'type', 'id', 'after', 'tick', 'time', 'delay', 'timeout', 'label',
                 'meta', 'wait_before', 'wait_after', 'sub_actions', 'parameters'}

    # Extract params: everything not reserved, or from explicit 'parameters' key
    if 'parameters' in d and isinstance(d['parameters'], dict):
        params = dict(d['parameters'])
    else:
        params = {k: v for k, v in d.items() if k not in _RESERVED}

    # Type-specific normalization
    match action_type:
        case 'wait_time':
            # Convert to our 'wait' type
            if 'time_s' in params:
                secs = float(params['time_s'])
            elif 'time_ms' in params:
                secs = float(params['time_ms']) / 1000.0
            else:
                secs = 0.0
            actions.append(ExperimentAction(type='wait', params={'seconds': secs},
                                            label=label or f'Wait {secs:.2f}s',
                                            timeout=timeout))

        case 'wait_ticks':
            # Approximate: assume 100 Hz
            ticks = int(params.get('ticks', 0))
            secs = ticks * 0.01
            actions.append(ExperimentAction(type='wait', params={'seconds': secs},
                                            label=label or f'Wait {ticks} ticks',
                                            timeout=timeout))

        case 'run_trajectory':
            traj_value = params.get('input_trajectory', params.get('trajectory'))
            traj = _load_trajectory(traj_value, source_dir)
            actions.append(ExperimentAction(type='run_trajectory',
                                            params={'trajectory': traj},
                                            label=label or 'Run trajectory',
                                            timeout=timeout))

        case 'set_input':
            # YAML format: input: [left, right]
            inp = params.get('input', [0.0, 0.0])
            if isinstance(inp, list) and len(inp) >= 2:
                left, right = float(inp[0]), float(inp[1])
            else:
                left = right = 0.0
            actions.append(ExperimentAction(type='set_input',
                                            params={'left': left, 'right': right},
                                            label=label or f'Set input [{left:.3f}, {right:.3f}]',
                                            timeout=timeout))

        case 'set_velocity':
            # YAML uses forward/turn; map to v/psi_dot
            v = float(params.get('forward', params.get('v', 0.0)))
            psi_dot = float(params.get('turn', params.get('psi_dot', 0.0)))
            actions.append(ExperimentAction(type='set_velocity',
                                            params={'v': v, 'psi_dot': psi_dot},
                                            label=label or f'Set velocity v={v:.2f}',
                                            timeout=timeout))

        case 'set_mode':
            actions.append(ExperimentAction(type='set_mode',
                                            params={'mode': params.get('mode', 'OFF')},
                                            label=label or f"Set mode {params.get('mode')}",
                                            timeout=timeout))

        case 'move_to':
            heading = params.get('target_heading')
            if heading is None and 'heading' in params:
                heading = float(params['heading'])
            if heading is None and 'heading_deg' in params:
                heading = math.radians(float(params['heading_deg']))
            actions.append(ExperimentAction(
                type='move_to',
                params={'x': float(params.get('x', 0)), 'y': float(params.get('y', 0)),
                        'max_speed': float(params.get('max_speed', 0.0)),
                        'target_heading': heading,
                        'heading_strength': float(params.get('heading_strength', 1.0))},
                label=label or f"Move to ({params.get('x', 0):.2f}, {params.get('y', 0):.2f})",
                timeout=timeout))

        case 'turn_to':
            heading = float(params.get('heading', 0.0))
            if 'heading_deg' in params and params['heading_deg'] is not None:
                heading = math.radians(float(params['heading_deg']))
            actions.append(ExperimentAction(type='turn_to',
                                            params={'heading': heading},
                                            label=label or f'Turn to {heading:.2f} rad',
                                            timeout=timeout))

        case 'follow_path':
            target = params.get('target')
            wps = params.get('waypoints')
            heading = params.get('target_heading')
            if heading is None and 'target_heading_deg' in params:
                heading = math.radians(float(params['target_heading_deg']))
            actions.append(ExperimentAction(
                type='follow_path',
                params={'waypoints': wps, 'target': target,
                        'max_speed': float(params.get('max_speed', 0.0)),
                        'target_heading': heading,
                        'heading_strength': float(params.get('heading_strength', 1.0)),
                        'allow_reverse': bool(params.get('allow_reverse', False)),
                        'stop_indices': params.get('stop_indices')},
                label=label or 'Follow path',
                timeout=timeout))

        case 'group':
            # Flatten group actions into the sequence
            sub_actions = params.get('actions', [])
            for sub in sub_actions:
                actions.extend(_action_from_dict(sub, source_dir))

        case 'beep' | 'speak' | 'set_tic' | 'set_psi_control' | 'reset' | \
             'enable_external_input' | 'set_marker' | 'reset_control' | \
             'set_feedback_gain' | 'stop_path':
            # Unsupported in simulation — skip silently
            logger.debug(f"Skipping unsupported action type '{action_type}' in simulation")

        case _:
            logger.warning(f"Unknown action type '{action_type}' — skipping")

    # Insert wait_after
    wa = d.get('wait_after')
    if wa is not None:
        secs = _parse_time_seconds(wa)
        if secs > 0:
            actions.append(ExperimentAction(type='wait', params={'seconds': secs},
                                            label=f'Wait {secs:.2f}s (after)'))

    return actions


def load_experiment(file: str) -> list[ExperimentAction]:
    """Load an experiment from a YAML or JSON file.

    Supports the same format as the real robot's experiment YAML files,
    including .bitrj trajectory file references resolved relative to the
    YAML file's directory.

    Returns a list of ExperimentAction objects suitable for
    ``agent.run_experiment()``.
    """
    if not os.path.isfile(file):
        raise FileNotFoundError(f"Experiment file not found: {file}")

    source_dir = os.path.dirname(os.path.abspath(file))

    with open(file, 'r') as f:
        if file.lower().endswith(('.yml', '.yaml')):
            data = yaml.safe_load(f)
        else:
            data = json.load(f)

    raw_actions = data.get('actions', [])
    actions: list[ExperimentAction] = []
    for raw in raw_actions:
        actions.extend(_action_from_dict(raw, source_dir))

    return actions


# ======================================================================================================================
# Experiment runner
# ======================================================================================================================

class ExperimentRunner:
    """Step-based experiment executor for BILBO_CompleteAgent.

    Call ``step()`` once per LOGIC tick.  The runner advances through the
    action list sequentially, starting each action and polling its
    completion predicate until it returns True (or the action times out).
    """

    def __init__(self, agent: BILBO_CompleteAgent, actions: list[ExperimentAction]):
        self.agent = agent
        self.actions = list(actions)

        self._idx: int = 0
        self._started: bool = False
        self._done_check: Callable[[], bool] | None = None
        self._action_start_tick: int = 0
        self._tick: int = 0

        self.finished: bool = False
        self.aborted: bool = False

        # Callbacks
        self.on_finished: Callable | None = None
        self.on_action_started: Callable[[int, ExperimentAction], None] | None = None
        self.on_action_finished: Callable[[int, ExperimentAction], None] | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def step(self):
        """Advance the experiment by one tick. Call from LOGIC scheduler."""
        if self.finished or self.aborted:
            return

        self._tick += 1

        # All actions done?
        if self._idx >= len(self.actions):
            self.finished = True
            self.agent.logger.info("Experiment finished")
            if self.on_finished:
                self.on_finished()
            return

        action = self.actions[self._idx]

        # Start action on first encounter
        if not self._started:
            self._start_action(action)
            self._started = True
            self._action_start_tick = self._tick

            if self.on_action_started:
                self.on_action_started(self._idx, action)

            # Instant action — advance immediately
            if self._done_check is None:
                self._advance()
                return

        # Poll completion
        if self._done_check is not None and self._done_check():
            self._advance()
            return

        # Timeout check
        if action.timeout > 0:
            elapsed = (self._tick - self._action_start_tick) * float(self.agent.Ts)
            if elapsed >= action.timeout:
                self.agent.logger.warning(
                    f"Experiment action '{action.label or action.type}' timed out "
                    f"after {action.timeout:.1f}s")
                self._advance()

    # ------------------------------------------------------------------------------------------------------------------
    def abort(self):
        self.aborted = True
        self.agent.logger.info("Experiment aborted")

    # ------------------------------------------------------------------------------------------------------------------
    def _advance(self):
        if self.on_action_finished:
            self.on_action_finished(self._idx, self.actions[self._idx])
        self._idx += 1
        self._started = False
        self._done_check = None

    # ------------------------------------------------------------------------------------------------------------------
    def _start_action(self, action: ExperimentAction):
        agent = self.agent
        p = action.params

        match action.type:
            # --- motion -----------------------------------------------------------
            case 'move_to':
                agent.move_to_point(
                    x=p['x'], y=p['y'],
                    max_speed=p.get('max_speed', 0.0),
                    target_heading=p.get('target_heading'),
                    heading_strength=p.get('heading_strength', 1.0),
                    timeout=p.get('move_timeout', 0.0),
                )
                self._done_check = lambda: (
                    agent._position_control.is_idle
                    and agent._pending_heading is None
                )

            case 'turn_to':
                heading = p.get('heading', 0.0)
                if 'heading_deg' in p and p['heading_deg'] is not None:
                    heading = math.radians(p['heading_deg'])
                agent.turn_to_heading(heading, timeout=p.get('turn_timeout', 0.0))
                self._done_check = lambda: agent._position_control.is_idle

            case 'follow_path':
                agent.follow_path(
                    waypoints=p['waypoints'],
                    max_speed=p.get('max_speed', 0.0),
                    target_heading=p.get('target_heading'),
                    heading_strength=p.get('heading_strength', 1.0),
                    allow_reverse=p.get('allow_reverse', False),
                    timeout=p.get('path_timeout', 0.0),
                    stop_indices=p.get('stop_indices'),
                )
                self._done_check = lambda: (
                    agent._position_control.is_idle
                    and agent._pending_heading is None
                )

            # --- trajectory -------------------------------------------------------
            case 'run_trajectory':
                agent.run_trajectory(p['trajectory'])
                self._done_check = lambda: not agent.is_trajectory_running

            # --- timing -----------------------------------------------------------
            case 'wait':
                wait_ticks = int(p['seconds'] / float(agent.Ts))
                target_tick = self._tick + wait_ticks
                self._done_check = lambda: self._tick >= target_tick

            # --- instant commands -------------------------------------------------
            case 'set_mode':
                mode = p['mode']
                if isinstance(mode, str):
                    mode = BILBO_Control_Mode[mode]
                agent.set_mode(mode)
                self._done_check = None

            case 'set_velocity':
                agent.set_velocity(
                    v=p.get('v', 0.0),
                    psi_dot=p.get('psi_dot', 0.0),
                )
                self._done_check = None

            case 'set_input':
                agent.input = BILBO_3D_Input(
                    M_L=float(p.get('left', 0.0)),
                    M_R=float(p.get('right', 0.0)),
                )
                self._done_check = None

            # --- custom function --------------------------------------------------
            case 'func':
                fn = p['function']
                args = p.get('args', ())
                kwargs = p.get('kwargs', {})
                result = fn(*args, **kwargs)
                # If the function returns a callable, use it as the done check
                if callable(result):
                    self._done_check = result
                else:
                    self._done_check = None

            case _:
                agent.logger.warning(f"Unknown experiment action: {action.type}")
                self._done_check = None


# ======================================================================================================================
# Builder
# ======================================================================================================================

class ExperimentBuilder:
    """Fluent builder for simulation experiments.

    Mirrors the real robot's ``ExperimentBuilder`` API. Each method appends
    an action and returns ``self`` for chaining.

    Example::

        exp = (ExperimentBuilder()
               .set_mode('BALANCING')
               .wait(1.0)
               .move_to(2.0, 1.5, max_speed=0.5, target_heading=0)
               .wait(0.5)
               .run_trajectory(u)
               .set_mode('OFF')
               .build())

        agent.run_experiment(exp)
    """

    def __init__(self):
        self._actions: list[ExperimentAction] = []

    # --- motion -------------------------------------------------------------------

    def move_to(self, x: float, y: float, max_speed: float = 0.0,
                target_heading: float | None = None,
                heading_strength: float = 1.0,
                timeout: float = 0.0) -> ExperimentBuilder:
        self._actions.append(ExperimentAction(
            type='move_to',
            params={'x': x, 'y': y, 'max_speed': max_speed,
                    'target_heading': target_heading,
                    'heading_strength': heading_strength},
            label=f'Move to ({x:.2f}, {y:.2f})',
            timeout=timeout,
        ))
        return self

    def turn_to(self, heading: float = 0.0, heading_deg: float | None = None,
                timeout: float = 0.0) -> ExperimentBuilder:
        label = (f'Turn to {heading_deg:.1f} deg' if heading_deg is not None
                 else f'Turn to {heading:.2f} rad')
        self._actions.append(ExperimentAction(
            type='turn_to',
            params={'heading': heading, 'heading_deg': heading_deg},
            label=label,
            timeout=timeout,
        ))
        return self

    def follow_path(self, waypoints: list, max_speed: float = 0.0,
                    target_heading: float | None = None,
                    heading_strength: float = 1.0,
                    allow_reverse: bool = False, timeout: float = 0.0,
                    stop_indices: list[int] | None = None) -> ExperimentBuilder:
        self._actions.append(ExperimentAction(
            type='follow_path',
            params={'waypoints': waypoints, 'max_speed': max_speed,
                    'target_heading': target_heading,
                    'heading_strength': heading_strength,
                    'allow_reverse': allow_reverse,
                    'stop_indices': stop_indices},
            label=f'Follow path ({len(waypoints)} waypoints)',
            timeout=timeout,
        ))
        return self

    # --- trajectory ---------------------------------------------------------------

    def run_trajectory(self, trajectory, timeout: float = 0.0) -> ExperimentBuilder:
        self._actions.append(ExperimentAction(
            type='run_trajectory',
            params={'trajectory': trajectory},
            label='Run trajectory',
            timeout=timeout,
        ))
        return self

    # --- timing -------------------------------------------------------------------

    def wait(self, seconds: float) -> ExperimentBuilder:
        self._actions.append(ExperimentAction(
            type='wait',
            params={'seconds': seconds},
            label=f'Wait {seconds:.2f}s',
        ))
        return self

    # --- instant commands ---------------------------------------------------------

    def set_mode(self, mode: str | BILBO_Control_Mode) -> ExperimentBuilder:
        self._actions.append(ExperimentAction(
            type='set_mode',
            params={'mode': mode},
            label=f'Set mode {mode}',
        ))
        return self

    def set_velocity(self, v: float = 0.0, psi_dot: float = 0.0) -> ExperimentBuilder:
        self._actions.append(ExperimentAction(
            type='set_velocity',
            params={'v': v, 'psi_dot': psi_dot},
            label=f'Set velocity v={v:.2f}, psi_dot={psi_dot:.2f}',
        ))
        return self

    def set_input(self, left: float = 0.0, right: float = 0.0) -> ExperimentBuilder:
        self._actions.append(ExperimentAction(
            type='set_input',
            params={'left': left, 'right': right},
            label=f'Set input left={left:.3f}, right={right:.3f}',
        ))
        return self

    # --- custom -------------------------------------------------------------------

    def func(self, function: Callable, *args, **kwargs) -> ExperimentBuilder:
        """Call an arbitrary function.

        If the function returns a callable, it is used as a completion
        predicate (polled each tick until it returns True).  Otherwise
        the action completes immediately.
        """
        name = getattr(function, '__name__', 'function')
        self._actions.append(ExperimentAction(
            type='func',
            params={'function': function, 'args': args, 'kwargs': kwargs},
            label=f'Call {name}',
        ))
        return self

    # --- file loading -------------------------------------------------------------

    @staticmethod
    def from_file(file: str) -> list[ExperimentAction]:
        """Load actions from a YAML/JSON experiment file.

        Convenience alias for :func:`load_experiment`.
        """
        return load_experiment(file)

    # --- build --------------------------------------------------------------------

    def build(self) -> list[ExperimentAction]:
        """Return the list of experiment actions."""
        return list(self._actions)
