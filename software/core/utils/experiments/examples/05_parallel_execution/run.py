"""Example 05: Parallel Execution

Concept: The 'parallel' action runs all its sub-actions concurrently.
It completes only when every sub-action has finished. Use 'group' to
bundle multiple sequential steps into a single parallel branch.

What happens step by step:
  1. Log "Starting"                — before the parallel block
  2. Three groups start at once    — each simulates a sensor read
     - Sensor A: waits 100ms, sets sensor_a = "ok"
     - Sensor B: waits 200ms, sets sensor_b = "ok"
     - Sensor C: waits 150ms, sets sensor_c = "ok"
  3. Parallel block completes      — when the slowest branch (B, 200ms) finishes
  4. Log all sensor values         — all three are "ok"

Why: Parallel execution lets you run independent tasks concurrently.
Total time is ~200ms (the slowest branch), not ~450ms (sum of all).
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
        'id': 'parallel_demo',
        'variables': {
            'sensor_a': 'pending',
            'sensor_b': 'pending',
            'sensor_c': 'pending',
        },
        'actions': [
            {'type': 'log', 'message': 'Reading 3 sensors in parallel...'},
            {
                'type': 'parallel',
                'actions': [
                    {
                        'type': 'group',
                        'actions': [
                            {'type': 'log', 'message': '  [A] Starting...'},
                            {'type': 'wait_time', 'time': 0.1},
                            {'type': 'set_variable', 'name': 'sensor_a', 'value': 'ok'},
                            {'type': 'log', 'message': '  [A] Done.'},
                        ],
                    },
                    {
                        'type': 'group',
                        'actions': [
                            {'type': 'log', 'message': '  [B] Starting...'},
                            {'type': 'wait_time', 'time': 0.2},
                            {'type': 'set_variable', 'name': 'sensor_b', 'value': 'ok'},
                            {'type': 'log', 'message': '  [B] Done.'},
                        ],
                    },
                    {
                        'type': 'group',
                        'actions': [
                            {'type': 'log', 'message': '  [C] Starting...'},
                            {'type': 'wait_time', 'time': 0.15},
                            {'type': 'set_variable', 'name': 'sensor_c', 'value': 'ok'},
                            {'type': 'log', 'message': '  [C] Done.'},
                        ],
                    },
                ],
            },
            {'type': 'log', 'message': 'All done: A=${sensor_a}, B=${sensor_b}, C=${sensor_c}'},
        ],
    })

    runner = ExperimentRunner(definition, registry)
    runner.initialize()

    start = time.time()
    while not runner.step():
        time.sleep(0.005)
    elapsed = time.time() - start

    print(f'\nCompleted in {elapsed:.2f}s (parallel, not sequential)')
    print(f'Status: {runner.status}')


if __name__ == '__main__':
    main()
