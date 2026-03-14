"""Example 10: Combined — A realistic robot calibration experiment.

Concept: This is a comprehensive example loaded from YAML that
exercises most framework features together in a realistic scenario.

What happens step by step:
  1. Phase 1: Three sensors initialize in parallel (IMU, Encoder, Motor)
  2. Phase 2: A for-loop collects 5 calibration samples
     - Each sample computes a fake offset
     - A condition checks if the offset is an outlier (> threshold)
  3. Phase 3: Average offset is computed and outlier count checked
     - If <= 1 outlier: calibration passes
     - Otherwise: calibration fails
  4. Phase 4: A while-loop retries calibration with a relaxed threshold
     - Runs up to 2 retries, stops early if calibration passes
  5. Final status is logged

Why: This shows how loops, conditions, parallel, variables, markers,
and timing all compose naturally in a single YAML experiment.
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

    yaml_path = os.path.join(os.path.dirname(__file__), 'experiment.yaml')
    definition = ExperimentParser.from_file(yaml_path)

    print(f'Loaded: "{definition.id}" — {definition.description.strip()[:60]}...')
    print(f'{len(definition.actions)} top-level actions, {len(definition.variables)} variables\n')

    runner = ExperimentRunner(definition, registry)
    runner.initialize()

    start = time.time()
    while not runner.step():
        time.sleep(0.005)
    elapsed = time.time() - start

    print(f'\n--- Summary ---')
    print(f'Duration: {elapsed:.2f}s')
    print(f'Status: {runner.status}')
    print(f'Final variables:')
    for key, value in sorted(runner.variables.items()):
        if not key.startswith('_'):
            print(f'  {key} = {value}')


if __name__ == '__main__':
    main()
