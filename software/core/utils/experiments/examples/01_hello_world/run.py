"""Example 01: Hello World — Minimal sequential experiment.

Concept: The simplest possible experiment using sequential shorthand.
Actions are listed in order and automatically chained — no explicit
triggers or transitions needed.

What happens step by step:
  1. "Hello" is logged             — first action runs immediately
  2. "Processing..." is logged     — auto-chained from action 1
  3. "Done!" is logged as warning  — auto-chained from action 2
  4. Experiment finishes           — all actions completed

Why: This shows the minimum boilerplate to define and run an experiment.
The sequential format auto-generates triggers and transitions so you
can focus on what actions to run, not how to wire them together.
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
        'id': 'hello_world',
        'actions': [
            {'type': 'log', 'message': 'Hello from the experiment framework!'},
            {'type': 'log', 'message': 'Processing...'},
            {'type': 'log', 'message': 'Done!', 'level': 'warning'},
        ],
    })

    runner = ExperimentRunner(definition, registry)
    runner.initialize()

    while not runner.step():
        time.sleep(0.001)

    print(f'\nStatus: {runner.status}')


if __name__ == '__main__':
    main()
