"""Example 07: Custom Action — Register your own action type.

Concept: Subclass ActionBase to create a reusable action type.
Define what data it produces and what parameters it needs, then
implement execute(). Register it so experiments can use it by name.

This example shows FOUR styles for defining a custom action:
  - main_inner()     — Inner Params/Data dataclasses (compact, self-contained)
  - main_external()  — External dataclasses + explicit data_type/params_type
  - main_dict()      — Explicit parameter_defs/data_defs dicts (no typing)
  - main_atomic()    — Atomic data_type (single-value shorthand)

What happens step by step (identical flow for inner/external/dict):
  1. Action is registered as 'compute_sum'
  2. Experiment runs compute_sum with values [10, 20, 30]
  3. Action computes sum=60, stores it as data via context.complete()
  4. Log reads ${sum_step.result}  — resolves to 60 from action data
  5. Second compute_sum runs with [1, 2, 3], result=6
  6. Log reads ${step2.result}     — resolves to 6

For the atomic style:
  1. DoubleAction (data_type=float) is registered as 'double'
  2. Experiment runs double with value 21
  3. Action computes 21 * 2 = 42.0, stores as data (float)
  4. Log reads ${double_step.value}  — resolves to 42.0
  5. self.data returns 42.0 directly (not a dict)

Why: Inner dataclasses are the most compact. External dataclasses let
you share types across actions. Dict style is what builtins use.
Atomic types are a shorthand for single-value actions.
"""

import time
import sys
import os
from dataclasses import dataclass
from typing import ClassVar

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..')))

from core.utils.experiments import (
    ActionBase, ActionContext, ActionResult, ActionDataDef, ActionParameterDef,
    ExperimentParser, ExperimentRunner,
    ActionRegistry, register_builtin_actions,
)


# =============================================================================
# Style 1: Inner dataclasses (compact, self-contained)
#
#   - Params/Data defined as @dataclass inside the action
#   - data_type / params_type auto-set from inner classes
#   - parameter_defs / data_defs auto-generated from dataclass fields
#   - self.get_params(context) returns a typed Params instance
#   - self.data returns a typed Data instance (setter accepts dict or Data)
# =============================================================================

@dataclass
class ComputeActionInner(ActionBase):
    """Computes the sum of a list of numbers. Types defined inline."""
    type_id: ClassVar[str] = 'compute_sum_inner'

    @dataclass
    class Params:
        values: list

    @dataclass
    class Data:
        result: float = 0.0

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)  # -> ComputeActionInner.Params
        result = sum(params.values)        # autocomplete on .values
        self.logger.info(f"sum({params.values}) = {result}")
        context.complete(data=self.Data(result=result))  # autocomplete on Data(result=)
        return ActionResult.COMPLETED


# =============================================================================
# Style 2: External dataclasses + explicit data_type/params_type
#
#   - Params/Data defined as standalone dataclasses (shareable across actions)
#   - data_type / params_type set explicitly as ClassVars
#   - Same auto-generation of parameter_defs / data_defs
#   - Same typed get_params() and self.data behavior
# =============================================================================

@dataclass
class ComputeSumParams:
    values: list


@dataclass
class ComputeSumData:
    result: float = 0.0


@dataclass
class ComputeActionExternal(ActionBase):
    """Same action, but types defined externally (reusable across actions)."""
    type_id: ClassVar[str] = 'compute_sum_external'
    params_type: ClassVar[type] = ComputeSumParams
    data_type: ClassVar[type] = ComputeSumData

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)  # -> ComputeSumParams
        result = sum(params.values)
        self.logger.info(f"sum({params.values}) = {result}")
        context.complete(data=ComputeSumData(result=result))
        return ActionResult.COMPLETED


# =============================================================================
# Style 3: Explicit dicts (original style, used by builtin actions)
#
#   - parameter_defs / data_defs declared as ClassVar dicts
#   - data_type / params_type remain None (no auto-casting)
#   - context.resolve_params() returns a plain dict
#   - context.complete(data={...}) takes a plain dict
# =============================================================================

@dataclass
class ComputeActionDict(ActionBase):
    """Same action, dict style."""
    type_id: ClassVar[str] = 'compute_sum_dict'
    data_defs: ClassVar[dict[str, ActionDataDef]] = {
        'result': ActionDataDef(id='result', description='Computed sum'),
    }
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'values': ActionParameterDef(id='values', type=list, required=True),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        params = context.resolve_params(self.raw_params)  # -> dict
        values = params.get('values', [])
        result = sum(values)
        self.logger.info(f"sum({values}) = {result}")
        context.complete(data={'result': result})
        return ActionResult.COMPLETED


# =============================================================================
# Style 4: Atomic data_type (single-value shorthand)
#
#   - data_type = float  → self.data returns a float (stored as {'value': x})
#   - No Data class needed
#   - In expressions: ${action_id.value} accesses the stored value
# =============================================================================

@dataclass
class DoubleAction(ActionBase):
    """Doubles a number. Demonstrates atomic data_type."""
    type_id: ClassVar[str] = 'double'
    data_type: ClassVar[type] = float

    @dataclass
    class Params:
        value: float

    def execute(self, context: ActionContext) -> ActionResult:
        params = self.get_params(context)  # -> DoubleAction.Params
        result = params.value * 2
        self.logger.info(f"{params.value} * 2 = {result}")
        self.data = result  # setter stores as {'value': 42.0}
        context.complete(data={'value': result})
        return ActionResult.COMPLETED


# =============================================================================
# Experiment definitions
# =============================================================================

EXPERIMENT_COMPUTE = {
    'actions': [
        {'id': 'sum_step', 'type': 'PLACEHOLDER', 'values': [10, 20, 30]},
        {'type': 'log', 'message': 'First sum: ${sum_step.result}'},
        {'id': 'step2', 'type': 'PLACEHOLDER', 'values': [1, 2, 3]},
        {'type': 'log', 'message': 'Second sum: ${step2.result}'},
    ],
}

EXPERIMENT_DOUBLE = {
    'actions': [
        {'id': 'double_step', 'type': 'double', 'value': 21},
        {'type': 'log', 'message': 'Doubled: ${double_step.value}'},
    ],
}


def _make_compute_experiment(type_id: str) -> dict:
    """Clone EXPERIMENT_COMPUTE with a specific action type."""
    exp = {'actions': [dict(a) for a in EXPERIMENT_COMPUTE['actions']]}
    exp['actions'][0]['type'] = type_id
    exp['actions'][2]['type'] = type_id
    return exp


def _run(registry, experiment: dict, action_type: str):
    definition = ExperimentParser.from_dict({'id': 'custom_action_demo', **experiment})
    runner = ExperimentRunner(definition, registry)
    runner.initialize()
    while not runner.step():
        time.sleep(0.005)
    print(f'  Action data: {runner.action_data}')
    print(f'  Status: {runner.status}')
    action_cls = registry.get_type(action_type)
    print(f'  data_type:      {action_cls.data_type}')
    print(f'  params_type:    {action_cls.params_type}')


def main_inner():
    """Style 1: Inner Params/Data dataclasses."""
    registry = ActionRegistry()
    register_builtin_actions(registry)
    registry.register(ComputeActionInner)
    _run(registry, _make_compute_experiment('compute_sum_inner'), 'compute_sum_inner')

    # Demonstrate typed data property
    action = ComputeActionInner(id='demo')
    action.data = {'result': 42.0}
    print(f'  action.data = {action.data}')    # -> ComputeActionInner.Data(result=42.0)
    print(f'  action._data = {action._data}')  # -> {'result': 42.0}


def main_external():
    """Style 2: External dataclasses with explicit data_type/params_type."""
    registry = ActionRegistry()
    register_builtin_actions(registry)
    registry.register(ComputeActionExternal)
    _run(registry, _make_compute_experiment('compute_sum_external'), 'compute_sum_external')

    # Same typed behavior, but with external classes
    action = ComputeActionExternal(id='demo')
    action.data = {'result': 42.0}
    print(f'  action.data = {action.data}')    # -> ComputeSumData(result=42.0)
    action.data = ComputeSumData(result=99.0)  # set from external dataclass
    print(f'  action.data = {action.data}')    # -> ComputeSumData(result=99.0)
    print(f'  action._data = {action._data}')  # -> {'result': 99.0}


def main_dict():
    """Style 3: Explicit defs dicts (no typing)."""
    registry = ActionRegistry()
    register_builtin_actions(registry)
    registry.register(ComputeActionDict)
    _run(registry, _make_compute_experiment('compute_sum_dict'), 'compute_sum_dict')


def main_atomic():
    """Style 4: Atomic data_type=float."""
    registry = ActionRegistry()
    register_builtin_actions(registry)
    registry.register(DoubleAction)
    _run(registry, EXPERIMENT_DOUBLE, 'double')

    # Demonstrate atomic data property
    action = DoubleAction(id='demo')
    action.data = 42.0
    print(f'  action.data = {action.data}')    # -> 42.0 (float, not dict)
    print(f'  action._data = {action._data}')  # -> {'value': 42.0}


if __name__ == '__main__':
    print('=== Style 1: Inner dataclasses ===')
    main_inner()
    print('\n=== Style 2: External dataclasses ===')
    main_external()
    print('\n=== Style 3: Dict style ===')
    main_dict()
    print('\n=== Style 4: Atomic type ===')
    main_atomic()
