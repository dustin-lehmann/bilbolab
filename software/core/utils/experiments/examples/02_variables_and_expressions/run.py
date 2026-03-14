"""Example 02: Variables and Expressions

Concept: Declare variables upfront, mutate them with set_variable,
and use ${...} expressions for arithmetic, interpolation, and logic.

This example shows TWO ways to build the same experiment:
  - main_dict()    — compact dict parsed by ExperimentParser (auto IDs/chaining)
  - main_classes() — explicit ActionDefinition objects (full control)

What happens step by step (identical for both):
  1. Log initial values         — x=10, y=3 from 'variables' block
  2. Set x = x * 2              — ${x * 2} evaluates to 20
  3. Log new x                  — shows x=20
  4. Set sum = x + y            — ${x + y} evaluates to 23
  5. Log with interpolation     — "sum of 20 and 3 is 23" (mixed text + ${})
  6. Set label via ternary      — ${"big" if x > 15 else "small"} -> "big"
  7. Log label                  — shows "big"

Why: Variables are the main way to pass state between actions. The
expression engine supports arithmetic, comparisons, and a set of
safe builtins (min, max, abs, round, len, int, float, str, bool).
"""

import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..')))

from core.utils.experiments import (
    ActionDefinition, ExperimentDefinition, ExperimentRunner,
    ExperimentParser, ActionRegistry, register_builtin_actions,
    ActionTrigger, TriggerType,
)


def _run(definition):
    """Shared runner logic."""
    registry = ActionRegistry()
    register_builtin_actions(registry)

    runner = ExperimentRunner(definition, registry)
    runner.initialize()

    while not runner.step():
        time.sleep(0.001)

    print(f'\nFinal variables: {runner.variables}')
    print(f'Status: {runner.status}')


def main_dict():
    """Build the experiment from a dict (parsed by ExperimentParser).

    This is the compact way: the parser auto-generates IDs, triggers,
    and transition chaining. Good for quick definitions and YAML parity.
    """
    definition = ExperimentParser.from_dict({
        'id': 'variables_demo',
        'variables': {
            'x': 10,
            'y': 3,
        },
        'actions': [
            {'type': 'log', 'message': 'Initial: x=${x}, y=${y}'},

            {'type': 'set_variable', 'name': 'x', 'value': '${x * 2}'},
            {'type': 'log', 'message': 'After x * 2: x=${x}'},

            {'type': 'set_variable', 'name': 'sum', 'value': '${x + y}'},
            {'type': 'log', 'message': 'sum of ${x} and ${y} is ${sum}'},

            {'type': 'set_variable', 'name': 'label', 'value': '${\"big\" if x > 15 else \"small\"}'},
            {'type': 'log', 'message': 'label = ${label}'},
        ],
    })

    _run(definition)


def main_classes():
    """Build the same experiment from ActionDefinition/ExperimentDefinition directly.

    This is the explicit way: you set every ID, trigger, and transition
    yourself. More verbose, but gives full control and works without the
    parser. Useful when constructing experiments programmatically.
    """
    definition = ExperimentDefinition(
        id='variables_demo',
        variables={'x': 10, 'y': 3},
        actions=[
            ActionDefinition(
                id='log_initial',
                type='log',
                params={'message': 'Initial: x=${x}, y=${y}'},
                trigger=ActionTrigger(type=TriggerType.IMMEDIATE),
                transitions={'done': 'set_x'},
            ),
            ActionDefinition(
                id='set_x',
                type='set_variable',
                params={'name': 'x', 'value': '${x * 2}'},
                trigger=ActionTrigger(type=TriggerType.TRANSITION),
                transitions={'done': 'log_x'},
            ),
            ActionDefinition(
                id='log_x',
                type='log',
                params={'message': 'After x * 2: x=${x}'},
                trigger=ActionTrigger(type=TriggerType.TRANSITION),
                transitions={'done': 'set_sum'},
            ),
            ActionDefinition(
                id='set_sum',
                type='set_variable',
                params={'name': 'sum', 'value': '${x + y}'},
                trigger=ActionTrigger(type=TriggerType.TRANSITION),
                transitions={'done': 'log_sum'},
            ),
            ActionDefinition(
                id='log_sum',
                type='log',
                params={'message': 'sum of ${x} and ${y} is ${sum}'},
                trigger=ActionTrigger(type=TriggerType.TRANSITION),
                transitions={'done': 'set_label'},
            ),
            ActionDefinition(
                id='set_label',
                type='set_variable',
                params={'name': 'label', 'value': '${\"big\" if x > 15 else \"small\"}'},
                trigger=ActionTrigger(type=TriggerType.TRANSITION),
                transitions={'done': 'log_label'},
            ),
            ActionDefinition(
                id='log_label',
                type='log',
                params={'message': 'label = ${label}'},
                trigger=ActionTrigger(type=TriggerType.TRANSITION),
            ),
        ],
    )

    _run(definition)


if __name__ == '__main__':
    print('=== From dict (parser shorthand) ===')
    main_dict()
    print('\n=== From classes (explicit) ===')
    main_classes()
