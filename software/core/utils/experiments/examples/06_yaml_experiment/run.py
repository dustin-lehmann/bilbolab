"""Example 06: YAML Experiment — Load and run from a .yaml file.

Concept: Experiment definitions can be written in YAML and loaded
with ExperimentParser.from_file(). This separates the experiment
description from the Python runner code.

What happens step by step:
  1. Load experiment.yaml        — parser auto-detects sequential format
  2. Print metadata              — id, description, action count
  3. Run the experiment          — steps towards target angle in 3 steps
  4. Condition checks result     — logs "Target reached!" (45.0 >= 44.0)

Why: YAML is the primary format for experiment definitions. It makes
experiments readable, editable, and shareable without touching Python.
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

    print(f'Loaded: "{definition.id}"')
    print(f'Description: {definition.description.strip()}')
    print(f'Actions: {len(definition.actions)}, Variables: {definition.variables}')
    print()

    runner = ExperimentRunner(definition, registry)
    runner.initialize()

    while not runner.step():
        time.sleep(0.005)

    print(f'\nFinal variables: {runner.variables}')
    print(f'Status: {runner.status}')


if __name__ == '__main__':
    main()
