"""Example 04: Conditions — if/then/else branching

Concept: The 'condition' action evaluates a test expression and
runs either the 'then' or the 'else' branch. Execution continues
after the condition regardless of which branch was taken.

What happens step by step:
  1. Log temperature (75)          — from variables
  2. Evaluate ${temperature > 60}  — true, so 'then' branch runs
  3. Log "HIGH"                    — then-branch action
  4. Set status = "high"           — then-branch action
  5. Log status                    — runs after condition, shows "high"

Why: Conditions let you make runtime decisions based on variables,
action data, or any expression. The sequential shorthand automatically
creates a merge point so the next action after the condition always runs.
"""

import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..')))

from core.utils.experiments import (
    ExperimentParser, ExperimentRunner,
    ActionRegistry, register_builtin_actions,
)


def main():
    registry = ActionRegistry()
    register_builtin_actions(registry)

    definition = ExperimentParser.from_dict({
        'id': 'branching_demo',
        'variables': {
            'temperature': 75,
        },
        'actions': [
            {'type': 'log', 'message': 'Temperature = ${temperature}'},
            {
                'type': 'condition',
                'test': '${temperature > 60}',
                'then': [
                    {'type': 'log', 'message': '  -> HIGH (above 60)'},
                    {'type': 'set_variable', 'name': 'status', 'value': 'high'},
                ],
                'else': [
                    {'type': 'log', 'message': '  -> LOW (60 or below)'},
                    {'type': 'set_variable', 'name': 'status', 'value': 'low'},
                ],
            },
            {'type': 'log', 'message': 'Result: status = ${status}'},
        ],
    })

    runner = ExperimentRunner(definition, registry)
    runner.initialize()

    while not runner.step():
        time.sleep(0.005)

    print(f'\nFinal variables: {runner.variables}')
    print(f'Status: {runner.status}')


if __name__ == '__main__':
    main()
