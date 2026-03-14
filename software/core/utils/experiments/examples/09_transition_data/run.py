"""Example 09: Transition Data Mapping — Pass data between actions via transitions.

Concept: When a transition fires, it can carry a 'data' mapping that
writes values into the target action's parameters before it runs.
Source action data fields are available unprefixed in mapping expressions.

Three transition value formats are supported:
  - String:  "target_id"                              (no mapping)
  - Dict:    {target: "target_id", data: {key: val}}  (with mapping)
  - List:    [str | dict, ...]                         (fan-out to multiple targets)

What happens step by step:
  1. 'compute' runs execute_function -> robot.get_value() -> returns 42
     - Action data becomes {result: 42}
  2. Transition fires on 'done' port with mapping:
     - message: "The answer is ${result}"    ($result=42 from compute's data)
     - level: "warning"                       (literal string)
  3. 'report' log action runs with those mapped parameters
     - Logs "The answer is 42" at warning level
  4. 'report' transitions to TWO targets (fan-out):
     - 'double_log' gets message: "Double: ${compute.result * 2}"  (=84)
     - 'half_log' gets message: "Half: ${compute.result / 2}"      (=21.0)
  5. Both log actions run with their mapped messages

Why: Data mappings make data flow between actions explicit. Instead of
writing to shared variables, each transition declares exactly what data
it passes. Source action data is available unprefixed ($result) in
mapping expressions for convenience.
"""

import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..')))

from core.utils.experiments import (
    ActionDefinition, ExperimentDefinition, ExperimentRunner,
    ActionRegistry, register_builtin_actions,
    ActionTrigger, TriggerType,
)


class MockRobot:
    def get_value(self):
        return 42


def main():
    registry = ActionRegistry()
    register_builtin_actions(registry)

    robot = MockRobot()

    definition = ExperimentDefinition(
        id='transition_data_demo',
        actions=[
            # Step 1: Compute a value (produces data: {result: 42})
            ActionDefinition(
                id='compute',
                type='execute_function',
                params={'function': 'robot.get_value'},
                trigger=ActionTrigger(type=TriggerType.IMMEDIATE),
                transitions={
                    'done': {
                        'target': 'report',
                        'data': {
                            # $result is available unprefixed from compute's data
                            'message': 'The answer is ${result}',
                            'level': 'warning',
                        },
                    },
                },
            ),
            # Step 2: Log the result (message + level filled by transition mapping)
            ActionDefinition(
                id='report',
                type='log',
                trigger=ActionTrigger(type=TriggerType.TRANSITION),
                transitions={
                    # Fan-out: transition to two targets with different mappings
                    'done': [
                        {
                            'target': 'double_log',
                            'data': {'message': 'Double: ${compute.result * 2}'},
                        },
                        {
                            'target': 'half_log',
                            'data': {'message': 'Half: ${compute.result / 2}'},
                        },
                    ],
                },
            ),
            # Step 3a: Log doubled value
            ActionDefinition(
                id='double_log',
                type='log',
                trigger=ActionTrigger(type=TriggerType.TRANSITION),
            ),
            # Step 3b: Log halved value
            ActionDefinition(
                id='half_log',
                type='log',
                trigger=ActionTrigger(type=TriggerType.TRANSITION),
            ),
        ],
    )

    runner = ExperimentRunner(definition, registry)
    runner.initialize(context_objects={'robot': robot})

    while not runner.step():
        time.sleep(0.005)

    print(f'\nAction data: {runner.action_data}')
    print(f'Status: {runner.status}')


if __name__ == '__main__':
    main()
