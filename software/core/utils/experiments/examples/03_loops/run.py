"""Example 03: Loops — for-loop and while-loop

Concept: Use 'loop' for counted iteration and 'while' for
condition-based repetition. Both execute their sub-actions
sequentially on each iteration.

What happens step by step:
  1. For-loop runs 4 times (i=0..3)  — adds i to total each time
  2. Log total                        — shows 6 (0+1+2+3)
  3. Set counter=3                    — prepare for while-loop
  4. While-loop runs while counter>0  — decrements counter each iteration
  5. Log counter=0                    — loop exited when condition became false

Why: 'loop' is for when you know the count upfront (or can compute it
from a variable with '$n'). 'while' is for when you need a runtime
condition check before each iteration.
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
        'id': 'loops_demo',
        'variables': {
            'total': 0,
        },
        'actions': [
            # --- For-loop: sum 0+1+2+3 ---
            {'type': 'log', 'message': '--- For-loop: sum 0..3 ---'},
            {
                'type': 'loop',
                'count': 4,
                'variable': 'i',
                'actions': [
                    {'type': 'set_variable', 'name': 'total', 'value': '${total + i}'},
                    {'type': 'log', 'message': '  i=${i}, total=${total}'},
                ],
            },
            {'type': 'log', 'message': 'Sum = ${total}  (expected: 6)'},

            # --- While-loop: countdown ---
            {'type': 'log', 'message': '--- While-loop: countdown ---'},
            {'type': 'set_variable', 'name': 'counter', 'value': 3},
            {
                'type': 'while',
                'test': '${counter > 0}',
                'actions': [
                    {'type': 'log', 'message': '  counter = ${counter}'},
                    {'type': 'set_variable', 'name': 'counter', 'value': '${counter - 1}'},
                ],
            },
            {'type': 'log', 'message': 'Done. counter = ${counter}'},
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
