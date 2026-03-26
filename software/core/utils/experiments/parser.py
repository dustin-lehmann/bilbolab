import json
import os
from typing import Any

import yaml

from core.utils.logging_utils import Logger

from core.utils.experiments.types import (
    TriggerType, ActionTrigger,
)
from core.utils.experiments.experiment import ActionDefinition, ExperimentDefinition
from core.utils.experiments.requirement import RequirementDefinition
from core.utils.experiments.guard import GuardDefinition

logger = Logger('ExperimentParser')


class ExperimentParserError(Exception):
    pass


class ExperimentParser:
    """Parse experiment definitions from YAML, JSON, dict, or string.

    Supports two formats:
    1. Sequential shorthand: Actions as a list with implicit chaining
    2. Canonical: Actions with explicit triggers and transitions
    """

    @classmethod
    def from_file(cls, filepath: str) -> ExperimentDefinition:
        """Load experiment from a YAML or JSON file."""
        filepath = os.path.abspath(filepath)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Experiment file not found: {filepath}")

        with open(filepath, 'r') as f:
            content = f.read()

        if filepath.endswith('.json'):
            return cls.from_json(content)
        else:
            return cls.from_yaml(content)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> ExperimentDefinition:
        """Parse experiment from a YAML string."""
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            raise ExperimentParserError("YAML must contain a mapping at the top level")
        return cls.from_dict(data)

    @classmethod
    def from_json(cls, json_str: str) -> ExperimentDefinition:
        """Parse experiment from a JSON string."""
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise ExperimentParserError("JSON must contain an object at the top level")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> ExperimentDefinition:
        """Parse experiment from a dictionary."""
        experiment_id = data.get('id', 'experiment')
        description = data.get('description', '')
        variables = data.get('variables', {})
        timeout = data.get('timeout')

        # Parse requirements
        raw_requirements = data.get('requirements', [])
        requirements = [cls._parse_requirement(r, i) for i, r in enumerate(raw_requirements)]

        # Parse guards
        raw_guards = data.get('guards', [])
        guards = [cls._parse_guard(r, i) for i, r in enumerate(raw_guards)]

        # Parse setup actions
        raw_setup = data.get('setup_actions', [])
        setup_actions = []
        for i, raw in enumerate(raw_setup):
            setup_id = raw.get('id', f'setup_{i}')
            setup_actions.append(cls._parse_action_definition(raw, index=i, auto_id=setup_id))

        # Parse cleanup actions
        raw_cleanup = data.get('cleanup_actions', [])
        cleanup_actions = []
        for i, raw in enumerate(raw_cleanup):
            cleanup_id = raw.get('id', f'cleanup_{i}')
            cleanup_actions.append(cls._parse_action_definition(raw, index=i, auto_id=cleanup_id))

        # Parse actions
        raw_actions = data.get('actions', [])
        if not raw_actions:
            raise ExperimentParserError("Experiment must have at least one action")

        is_canonical = cls._is_canonical(raw_actions)

        if is_canonical:
            actions = cls._parse_canonical(raw_actions)
        else:
            actions = cls._parse_sequential(raw_actions)

        return ExperimentDefinition(
            id=experiment_id,
            description=description,
            actions=actions,
            variables=variables,
            requirements=requirements,
            guards=guards,
            setup_actions=setup_actions,
            cleanup_actions=cleanup_actions,
            timeout=timeout,
        )

    @classmethod
    def _parse_requirement(cls, raw: dict, index: int) -> RequirementDefinition:
        """Parse a single requirement definition from a dict."""
        req_id = raw.get('id', f'req_{index}')
        req_type = raw.get('type', '')
        reserved = {'id', 'type', 'params'}
        params = dict(raw.get('params', {}))
        for key, value in raw.items():
            if key not in reserved and key not in params:
                params[key] = value
        return RequirementDefinition(id=req_id, type=req_type, params=params)

    @classmethod
    def _parse_guard(cls, raw: dict, index: int) -> GuardDefinition:
        """Parse a single guard definition from a dict."""
        guard_id = raw.get('id', f'guard_{index}')
        guard_type = raw.get('type', '')
        reserved = {'id', 'type', 'params'}
        params = dict(raw.get('params', {}))
        for key, value in raw.items():
            if key not in reserved and key not in params:
                params[key] = value
        return GuardDefinition(id=guard_id, type=guard_type, params=params)

    @classmethod
    def _is_canonical(cls, actions: list[dict]) -> bool:
        """Detect if actions use canonical format (explicit triggers/transitions)."""
        for action in actions:
            if 'trigger' in action or 'transitions' in action:
                return True
        return False

    @classmethod
    def _parse_canonical(cls, raw_actions: list[dict]) -> list[ActionDefinition]:
        """Parse actions in canonical format with explicit triggers and transitions."""
        actions = []
        for i, raw in enumerate(raw_actions):
            actions.append(cls._parse_action_definition(raw, index=i))
        return actions

    @classmethod
    def _parse_sequential(cls, raw_actions: list[dict]) -> list[ActionDefinition]:
        """Parse actions in sequential shorthand format.

        Auto-generates IDs, creates implicit transition chaining,
        and handles inline condition/loop/group/parallel blocks.
        """
        result: list[ActionDefinition] = []
        prev_action_id: str | None = None

        for i, raw in enumerate(raw_actions):
            action_id = raw.get('id', f'action_{i}')
            action_type = raw.get('type', '')

            # Handle condition with inline then/else
            if action_type == 'condition':
                condition_actions = cls._expand_condition(raw, action_id, i)

                # First action in the expansion gets triggered by previous
                if condition_actions:
                    first = condition_actions[0]
                    if prev_action_id and not first.trigger:
                        first.trigger = ActionTrigger(type=TriggerType.TRANSITION)
                        # Add transition from previous action to this condition
                        cls._add_transition_from_prev(result, prev_action_id, first.id)
                    elif not first.trigger:
                        first.trigger = ActionTrigger(type=TriggerType.IMMEDIATE)

                result.extend(condition_actions)

                # Find the merge point (last action) for continuing the chain
                if condition_actions:
                    prev_action_id = condition_actions[-1].id
                continue

            # Standard action
            defn = cls._parse_action_definition(raw, index=i, auto_id=action_id)

            # Check for explicit trigger — only 'trigger' key counts in sequential mode.
            # 'tick', 'time', 'event' at the top level are treated as action parameters.
            has_explicit_trigger = 'trigger' in raw

            if has_explicit_trigger:
                defn.trigger = cls._parse_trigger(raw['trigger'])
            elif prev_action_id:
                # Implicit chaining: transition from previous action
                defn.trigger = ActionTrigger(type=TriggerType.TRANSITION)
                cls._add_transition_from_prev(result, prev_action_id, defn.id)
            else:
                # First action: immediate trigger
                defn.trigger = ActionTrigger(type=TriggerType.IMMEDIATE)

            result.append(defn)

            # Only update prev_action_id for sequential chain if no explicit trigger
            if not has_explicit_trigger:
                prev_action_id = defn.id

        return result

    @classmethod
    def _expand_condition(cls, raw: dict, base_id: str, index: int) -> list[ActionDefinition]:
        """Expand an inline condition into separate ActionDefinitions.

        Creates:
        1. The condition action itself (with 'then' and 'else' ports)
        2. Sub-actions for then/else branches stored on the definition
        3. A merge action that both branches transition to
        """
        result = []

        # Parse then/else sub-actions
        then_raw = raw.get('then', [])
        else_raw = raw.get('else', [])

        then_defs = []
        for j, sub in enumerate(then_raw):
            sub_id = sub.get('id', f'{base_id}_then_{j}')
            then_defs.append(cls._parse_action_definition(sub, index=j, auto_id=sub_id))

        else_defs = []
        for j, sub in enumerate(else_raw):
            sub_id = sub.get('id', f'{base_id}_else_{j}')
            else_defs.append(cls._parse_action_definition(sub, index=j, auto_id=sub_id))

        # Create the condition action
        condition_defn = ActionDefinition(
            id=base_id,
            type='condition',
            params=raw.get('params', {}),
            test=raw.get('test', ''),
            then_actions=then_defs if then_defs else None,
            else_actions=else_defs if else_defs else None,
        )

        # The condition action handles its own internal branching
        # Create a merge point for continuation
        merge_id = f'{base_id}_merge'
        merge_defn = ActionDefinition(
            id=merge_id,
            type='_noop',
            trigger=ActionTrigger(type=TriggerType.TRANSITION),
        )

        # Condition transitions: done port goes to merge (after branch execution)
        condition_defn.transitions = {'done': merge_id}

        result.append(condition_defn)
        result.append(merge_defn)

        return result

    @classmethod
    def _add_transition_from_prev(cls, actions: list[ActionDefinition], prev_id: str, target_id: str):
        """Add a 'done' -> target transition to the previous action."""
        for defn in actions:
            if defn.id == prev_id:
                if defn.transitions is None:
                    defn.transitions = {}
                existing = defn.transitions.get('done')
                if existing is None:
                    defn.transitions['done'] = target_id
                elif isinstance(existing, list):
                    existing.append(target_id)
                else:
                    defn.transitions['done'] = [existing, target_id]
                return

    @classmethod
    def _parse_action_definition(cls, raw: dict, index: int = 0, auto_id: str = None) -> ActionDefinition:
        """Parse a single action definition from a dict."""
        action_id = raw.get('id', auto_id or f'action_{index}')
        action_type = raw.get('type', '')

        # Params: everything that's not a reserved key
        reserved_keys = {
            'id', 'type', 'trigger', 'transitions', 'actions', 'sub_actions',
            'test', 'then', 'else', 'count', 'variable', 'max_iterations',
            'params', 'wait_before', 'wait_after', 'message_before', 'message_after',
        }
        # Params from explicit 'params' key, or from top-level non-reserved keys
        params = dict(raw.get('params', {}))
        for key, value in raw.items():
            if key not in reserved_keys and key not in params:
                params[key] = value

        # Parse sub-actions for group/loop/parallel/while
        sub_actions = None
        sub_raw = raw.get('actions') or raw.get('sub_actions')
        if sub_raw:
            sub_actions = []
            for j, sub in enumerate(sub_raw):
                sub_id = sub.get('id', f'{action_id}_sub_{j}')
                sub_actions.append(cls._parse_action_definition(sub, index=j, auto_id=sub_id))

        # Parse then/else branches (for condition actions, including nested ones)
        then_actions = None
        then_raw = raw.get('then')
        if then_raw:
            then_actions = []
            for j, sub in enumerate(then_raw):
                sub_id = sub.get('id', f'{action_id}_then_{j}')
                then_actions.append(cls._parse_action_definition(sub, index=j, auto_id=sub_id))

        else_actions = None
        else_raw = raw.get('else')
        if else_raw:
            else_actions = []
            for j, sub in enumerate(else_raw):
                sub_id = sub.get('id', f'{action_id}_else_{j}')
                else_actions.append(cls._parse_action_definition(sub, index=j, auto_id=sub_id))

        # Parse trigger
        trigger = None
        if 'trigger' in raw:
            trigger = cls._parse_trigger(raw['trigger'])

        # Parse transitions
        transitions = raw.get('transitions')

        # Parse wait_before / wait_after (seconds, or string like "2s", "500ms")
        wait_before = cls._parse_wait_time(raw.get('wait_before'))
        wait_after = cls._parse_wait_time(raw.get('wait_after'))

        return ActionDefinition(
            id=action_id,
            type=action_type,
            params=params,
            trigger=trigger,
            transitions=transitions,
            sub_actions=sub_actions,
            test=raw.get('test'),
            then_actions=then_actions,
            else_actions=else_actions,
            count=raw.get('count'),
            variable=raw.get('variable'),
            max_iterations=raw.get('max_iterations'),
            wait_before=wait_before,
            wait_after=wait_after,
            message_before=raw.get('message_before'),
            message_after=raw.get('message_after'),
        )

    @classmethod
    def _parse_trigger(cls, trigger_data: dict | str) -> ActionTrigger:
        """Parse a trigger from dict or string shorthand."""
        if isinstance(trigger_data, str):
            # Shorthand: "immediate", "transition", "tick:5", "time:2.0", "event:name", "periodic:1:seconds"
            if trigger_data == 'immediate':
                return ActionTrigger(type=TriggerType.IMMEDIATE)
            elif trigger_data == 'transition':
                return ActionTrigger(type=TriggerType.TRANSITION)
            elif trigger_data.startswith('tick:'):
                return ActionTrigger(type=TriggerType.TICK, tick=int(trigger_data[5:]))
            elif trigger_data.startswith('time:'):
                return ActionTrigger(type=TriggerType.TIME, time=float(trigger_data[5:]))
            elif trigger_data.startswith('event:'):
                return ActionTrigger(type=TriggerType.EVENT, event=trigger_data[6:])
            elif trigger_data.startswith('periodic:'):
                parts = trigger_data.split(':')
                period = float(parts[1])
                unit = parts[2] if len(parts) > 2 else 'seconds'
                return ActionTrigger(type=TriggerType.PERIODIC, period=period, period_unit=unit)
            else:
                raise ExperimentParserError(f"Unknown trigger shorthand: {trigger_data}")

        if isinstance(trigger_data, dict):
            trigger_type = TriggerType(trigger_data.get('type', 'immediate'))
            return ActionTrigger(
                type=trigger_type,
                tick=trigger_data.get('tick'),
                time=trigger_data.get('time'),
                event=trigger_data.get('event'),
                period=trigger_data.get('period'),
                period_unit=trigger_data.get('period_unit', 'seconds'),
            )

        raise ExperimentParserError(f"Invalid trigger format: {trigger_data}")

    @staticmethod
    def _parse_wait_time(value) -> float | None:
        """Parse a wait time value into seconds. Accepts float, int, or string like '2s', '500ms'."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            s = value.strip().lower()
            if s.endswith('ms'):
                return float(s[:-2]) / 1000.0
            if s.endswith('s'):
                return float(s[:-1])
            return float(s)
        return None
