import threading
import re
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

from core.utils.logging_utils import Logger
from core.utils.time import precise_sleep

from core.utils.experiments.types import (
    ActionStatus, ActionResult, ActionDataDef, ActionParameterDef,
    TriggerType, ActionTrigger, ExperimentActionData,
)
from core.utils.experiments.action import ActionBase, ActionContext, ActionRegistry
from core.utils.experiments.experiment import ActionDefinition

logger = Logger('BuiltinActions')


# === Utilities ===

def _create_sub_action(context: ActionContext, sub_def: ActionDefinition,
                       override_id: str | None = None) -> ActionBase:
    """Create a sub-action instance and register it in the runner."""
    action_id = override_id or sub_def.id
    instance = context.runner.registry.create_action(action_id, sub_def.type, sub_def.params)
    instance._definition = sub_def  # attach definition for nested control flow
    context.runner.action_instances[action_id] = instance
    # Resolve parameters so the report shows actual values (not ${i} templates)
    resolved_params = context.resolve_params(dict(instance.raw_params))

    context.runner.action_data[action_id] = ExperimentActionData(
        action_type=sub_def.type,
        label=sub_def.params.get('label', ''),
        meta=sub_def.params.get('meta', {}),
        parameters=resolved_params,
    )
    return instance


def _run_sub_action(context: ActionContext, sub_def: ActionDefinition,
                    override_id: str | None = None):
    """Create, execute, and track a sub-action with proper runner event firing.

    Fires action_started/action_finished events so that external listeners
    (like the designer widget) can track sub-action progress.

    Raises RuntimeError if the sub-action fails.
    """
    action_id = override_id or sub_def.id
    instance = _create_sub_action(context, sub_def, override_id=override_id)
    sub_context = ActionContext(runner=context.runner, action=instance)
    instance.status = ActionStatus.RUNNING

    # Record start timing on the ExperimentActionData entry
    entry = context.runner.action_data.get(action_id)
    if entry:
        entry.status = ActionStatus.RUNNING
        entry.start_tick = context.runner.tick
        entry.start_time = time.time() - context.runner._start_time

    context.runner.events.action_started.set(flags={'id': action_id})
    context.runner.callbacks.action_started.call(action_id=action_id)

    completed_event = threading.Event()
    result_holder = {'port': 'done'}

    def on_complete(data, _holder=result_holder, _event=completed_event):
        _holder['port'] = data.get('port', 'done') if isinstance(data, dict) else 'done'
        _event.set()

    instance.events.finished.on(callback=on_complete, once=True)

    result = instance.execute(sub_context)

    if result == ActionResult.COMPLETED:
        # _on_action_complete already updated the ExperimentActionData entry
        context.runner.events.action_finished.set(flags={'id': action_id})
        context.runner.callbacks.action_finished.call(action_id=action_id)
        return

    if result == ActionResult.ERROR:
        context.runner.events.action_finished.set(flags={'id': action_id})
        context.runner.callbacks.action_finished.call(action_id=action_id)
        raise RuntimeError(f"Sub-action '{action_id}' failed")

    # ASYNC: wait for completion
    completed_event.wait()
    context.runner.events.action_finished.set(flags={'id': action_id})
    context.runner.callbacks.action_finished.call(action_id=action_id)

    if result_holder['port'] == 'error':
        raise RuntimeError(f"Sub-action '{action_id}' failed")

def _parse_duration(value: Any) -> float:
    """Parse a duration value into seconds.

    Supports: int/float (seconds), "2s", "500ms", "1.5s"
    """
    if isinstance(value, (int, float)):
        return float(value)  # always treated as seconds

    if isinstance(value, str):
        value = value.strip()
        match = re.match(r'^([\d.]+)\s*(s|ms|sec|seconds|milliseconds)?$', value, re.IGNORECASE)
        if match:
            num = float(match.group(1))
            unit = (match.group(2) or 's').lower()
            if unit in ('ms', 'milliseconds'):
                return num / 1000.0
            return num
        raise ValueError(f"Cannot parse duration: '{value}'")

    raise TypeError(f"Invalid duration type: {type(value)}")


def _collect_sub_actions(context: ActionContext, parent_id: str, sub_ids: list[str]):
    """Nest sub-action ExperimentActionData entries into the parent's sub_actions dict."""
    parent_entry = context.runner.action_data.get(parent_id)
    if parent_entry is None:
        return
    for sub_id in sub_ids:
        sub_entry = context.runner.action_data.get(sub_id)
        if sub_entry:
            parent_entry.sub_actions[sub_id] = sub_entry


# === Noop (internal merge point) ===

@dataclass
class NoopAction(ActionBase):
    type_id: ClassVar[str] = '_noop'

    def execute(self, context: ActionContext) -> ActionResult:
        context.complete()
        return ActionResult.COMPLETED


# === Control Flow ===

@dataclass
class GroupAction(ActionBase):
    """Execute sub-actions sequentially."""
    type_id: ClassVar[str] = 'group'
    transition_ports: ClassVar[list[str]] = ['done']

    def execute(self, context: ActionContext) -> ActionResult:
        defn = self._definition
        sub_defs = defn.sub_actions

        if not sub_defs:
            context.complete()
            return ActionResult.COMPLETED

        thread = threading.Thread(
            target=self._run_sequential, args=(context, sub_defs), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _run_sequential(self, context: ActionContext, sub_defs: list[ActionDefinition]):
        """Run sub-actions one by one."""
        try:
            for sub_def in sub_defs:
                _run_sub_action(context, sub_def)
            _collect_sub_actions(context, self.id, [d.id for d in sub_defs])
            context.complete()
        except Exception as e:
            _collect_sub_actions(context, self.id, [d.id for d in sub_defs])
            context.fail(str(e))


@dataclass
class ParallelAction(ActionBase):
    """Execute sub-actions concurrently. Done when all complete."""
    type_id: ClassVar[str] = 'parallel'
    transition_ports: ClassVar[list[str]] = ['done']

    def execute(self, context: ActionContext) -> ActionResult:
        defn = self._definition
        sub_defs = defn.sub_actions

        if not sub_defs:
            context.complete()
            return ActionResult.COMPLETED

        thread = threading.Thread(
            target=self._run_parallel, args=(context, sub_defs), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _run_parallel(self, context: ActionContext, sub_defs: list[ActionDefinition]):
        """Run sub-actions concurrently and wait for all to complete."""
        sub_ids = []
        try:
            completion_events = []
            error_holder = {'error': None}

            for sub_def in sub_defs:
                action_id = sub_def.id
                sub_ids.append(action_id)
                instance = _create_sub_action(context, sub_def)
                sub_context = ActionContext(runner=context.runner, action=instance)
                instance.status = ActionStatus.RUNNING

                # Record start timing
                entry = context.runner.action_data.get(action_id)
                if entry:
                    entry.status = ActionStatus.RUNNING
                    entry.start_tick = context.runner.tick
                    entry.start_time = time.time() - context.runner._start_time

                context.runner.events.action_started.set(flags={'id': action_id})
                context.runner.callbacks.action_started.call(action_id=action_id)
                completed_event = threading.Event()

                def on_complete(data, _event=completed_event, _id=action_id):
                    context.runner.events.action_finished.set(flags={'id': _id})
                    context.runner.callbacks.action_finished.call(action_id=_id)
                    port = data.get('port', 'done') if isinstance(data, dict) else 'done'
                    if port == 'error':
                        error_holder['error'] = f"Sub-action '{_id}' failed"
                    _event.set()

                instance.events.finished.on(callback=on_complete, once=True)
                completion_events.append(completed_event)

                result = instance.execute(sub_context)
                if result == ActionResult.COMPLETED:
                    # _on_action_complete already updated the entry
                    context.runner.events.action_finished.set(flags={'id': action_id})
                    context.runner.callbacks.action_finished.call(action_id=action_id)
                    completed_event.set()
                elif result == ActionResult.ERROR:
                    context.runner.events.action_finished.set(flags={'id': action_id})
                    context.runner.callbacks.action_finished.call(action_id=action_id)
                    error_holder['error'] = f"Sub-action '{action_id}' failed"
                    completed_event.set()

            # Wait for all to complete
            for event in completion_events:
                event.wait()

            _collect_sub_actions(context, self.id, sub_ids)
            if error_holder['error']:
                context.fail(error_holder['error'])
            else:
                context.complete()
        except Exception as e:
            _collect_sub_actions(context, self.id, sub_ids)
            context.fail(str(e))


@dataclass
class LoopAction(ActionBase):
    """Runtime loop with counter. Evaluates count expression, iterates with variable."""
    type_id: ClassVar[str] = 'loop'
    transition_ports: ClassVar[list[str]] = ['done']

    def execute(self, context: ActionContext) -> ActionResult:
        defn = self._definition
        sub_defs = defn.sub_actions

        if not sub_defs:
            context.complete()
            return ActionResult.COMPLETED

        thread = threading.Thread(
            target=self._run_loop, args=(context, defn, sub_defs), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _run_loop(self, context: ActionContext, defn: ActionDefinition, sub_defs: list[ActionDefinition]):
        """Run sub-actions in a loop.

        Supports three iteration modes (checked in order):
        1. ``values`` param  – iterate over an explicit list, setting *variable* each time.
        2. ``range`` param   – iterate over ``range(*range_param)``, setting *variable*.
        3. ``count``         – simple repeat *count* times (variable defaults to ``i``).
        """
        try:
            variable = defn.variable or 'i'
            max_iter = defn.max_iterations
            params = defn.params or {}

            # Determine iteration values
            values_param = params.get('values')
            range_param = params.get('range')

            if values_param is not None:
                # Mode 1: explicit values list
                iteration_values = list(values_param)
            elif range_param is not None:
                # Mode 2: range-based – accepts [stop], [start, stop], or [start, stop, step]
                if isinstance(range_param, (int, float)):
                    iteration_values = list(range(int(range_param)))
                else:
                    iteration_values = list(range(*[int(v) for v in range_param]))
            else:
                # Mode 3: count-based repeat
                count_val = defn.count
                if isinstance(count_val, str) and context.runner.expression_engine.is_expression(count_val):
                    count_val = context.evaluate(count_val)
                iteration_values = list(range(int(count_val)))

            all_sub_ids = []
            for idx, val in enumerate(iteration_values):
                if max_iter is not None and idx >= max_iter:
                    self.logger.warning(f"Loop '{self.id}' hit max_iterations ({max_iter})")
                    break

                context.set_variable(variable, val)

                for sub_def in sub_defs:
                    iter_id = f'{sub_def.id}_iter{idx}'
                    all_sub_ids.append(iter_id)
                    _run_sub_action(context, sub_def, override_id=iter_id)

            _collect_sub_actions(context, self.id, all_sub_ids)
            context.complete()
        except Exception as e:
            _collect_sub_actions(context, self.id, all_sub_ids)
            context.fail(str(e))


@dataclass
class WhileAction(ActionBase):
    """Runtime conditional loop. Evaluates test expression each iteration."""
    type_id: ClassVar[str] = 'while'
    transition_ports: ClassVar[list[str]] = ['done']

    def execute(self, context: ActionContext) -> ActionResult:
        defn = self._definition
        sub_defs = defn.sub_actions

        if not sub_defs:
            context.complete()
            return ActionResult.COMPLETED

        thread = threading.Thread(
            target=self._run_while, args=(context, defn, sub_defs), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _run_while(self, context: ActionContext, defn: ActionDefinition, sub_defs: list[ActionDefinition]):
        """Run sub-actions while test expression is truthy."""
        try:
            max_iter = defn.max_iterations or 10000
            iteration = 0
            all_sub_ids = []

            while True:
                if iteration >= max_iter:
                    self.logger.warning(f"While '{self.id}' hit max_iterations ({max_iter})")
                    break

                # Evaluate test expression
                test_result = context.evaluate(defn.test)
                if not test_result:
                    break

                context.set_variable('_while_iteration', iteration)

                for sub_def in sub_defs:
                    iter_id = f'{sub_def.id}_iter{iteration}'
                    all_sub_ids.append(iter_id)
                    _run_sub_action(context, sub_def, override_id=iter_id)

                iteration += 1

            _collect_sub_actions(context, self.id, all_sub_ids)
            context.complete()
        except Exception as e:
            _collect_sub_actions(context, self.id, all_sub_ids)
            context.fail(str(e))


@dataclass
class ConditionAction(ActionBase):
    """Evaluate test expression and execute then or else branch."""
    type_id: ClassVar[str] = 'condition'
    transition_ports: ClassVar[list[str]] = ['done']

    def execute(self, context: ActionContext) -> ActionResult:
        defn = self._definition

        thread = threading.Thread(
            target=self._run_condition, args=(context, defn), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _run_condition(self, context: ActionContext, defn: ActionDefinition):
        """Evaluate test and run appropriate branch."""
        try:
            test_result = context.evaluate(defn.test)

            if test_result:
                branch_defs = defn.then_actions or []
            else:
                branch_defs = defn.else_actions or []

            # Execute branch sub-actions sequentially
            for sub_def in branch_defs:
                _run_sub_action(context, sub_def)

            context.complete()
        except Exception as e:
            context.fail(str(e))


# === Timing ===

@dataclass
class WaitTimeAction(ActionBase):
    """Wait for a specified duration."""
    type_id: ClassVar[str] = 'wait_time'
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'time': ActionParameterDef(id='time', required=True, description='Duration to wait'),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        params = context.resolve_params(self.raw_params)
        duration = _parse_duration(params.get('time', params.get('duration', 0)))

        if duration <= 0:
            context.complete()
            return ActionResult.COMPLETED

        thread = threading.Thread(target=self._wait, args=(context, duration), daemon=True)
        thread.start()
        return ActionResult.ASYNC

    def _wait(self, context: ActionContext, duration: float):
        precise_sleep(duration)
        context.complete()


@dataclass
class WaitTicksAction(ActionBase):
    """Wait for a specified number of experiment ticks."""
    type_id: ClassVar[str] = 'wait_ticks'
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'ticks': ActionParameterDef(id='ticks', type=int, required=True),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        params = context.resolve_params(self.raw_params)
        ticks = int(params.get('ticks', 1))
        target_tick = context.runner.tick + ticks

        thread = threading.Thread(target=self._wait, args=(context, target_tick), daemon=True)
        thread.start()
        return ActionResult.ASYNC

    def _wait(self, context: ActionContext, target_tick: int):
        while context.runner.tick < target_tick:
            precise_sleep(0.001)
        context.complete()


# === Events ===

@dataclass
class WaitForEventAction(ActionBase):
    """Wait for an internal experiment event."""
    type_id: ClassVar[str] = 'wait_for_event'
    transition_ports: ClassVar[list[str]] = ['done', 'timeout']
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'event': ActionParameterDef(id='event', type=str, required=True),
        'timeout': ActionParameterDef(id='timeout', type=float),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        params = context.resolve_params(self.raw_params)
        event_id = params.get('event', '')
        timeout = params.get('timeout')

        thread = threading.Thread(
            target=self._wait, args=(context, event_id, timeout), daemon=True
        )
        thread.start()
        return ActionResult.ASYNC

    def _wait(self, context: ActionContext, event_id: str, timeout: float | None):
        from core.utils.events import TIMEOUT as EV_TIMEOUT

        event = context.runner.get_internal_event(event_id)
        data, match = event.wait(timeout=timeout)
        if data is EV_TIMEOUT:
            self.data['timed_out'] = True
            context.complete(port='timeout')
        else:
            self.data['data'] = data
            context.complete(port='done')


@dataclass
class EmitEventAction(ActionBase):
    """Emit an internal experiment event."""
    type_id: ClassVar[str] = 'emit_event'
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'event': ActionParameterDef(id='event', type=str, required=True),
        'data': ActionParameterDef(id='data'),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        params = context.resolve_params(self.raw_params)
        event_id = params.get('event', '')
        data = params.get('data')
        context.emit_event(event_id, data)
        context.complete()
        return ActionResult.COMPLETED


# === Variables ===

@dataclass
class SetVariableAction(ActionBase):
    """Set an experiment variable."""
    type_id: ClassVar[str] = 'set_variable'
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'name': ActionParameterDef(id='name', type=str, required=True),
        'value': ActionParameterDef(id='value', required=True),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        params = context.resolve_params(self.raw_params)
        name = params.get('name', '')
        value = params.get('value')
        context.set_variable(name, value)
        context.complete()
        return ActionResult.COMPLETED


@dataclass
class SetParameterAction(ActionBase):
    """Modify another action's parameter at runtime."""
    type_id: ClassVar[str] = 'set_parameter'
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'action_id': ActionParameterDef(id='action_id', type=str, required=True),
        'param_name': ActionParameterDef(id='param_name', type=str, required=True),
        'value': ActionParameterDef(id='value', required=True),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        params = context.resolve_params(self.raw_params)
        context.set_action_parameter(
            params.get('action_id', ''),
            params.get('param_name', ''),
            params.get('value'),
        )
        context.complete()
        return ActionResult.COMPLETED


# === Functions ===

@dataclass
class ExecuteFunctionAction(ActionBase):
    """Call a function by dot-path on context objects."""
    type_id: ClassVar[str] = 'execute_function'
    data_defs: ClassVar[dict[str, ActionDataDef]] = {
        'result': ActionDataDef(id='result', description='Return value of the function'),
    }
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'function': ActionParameterDef(id='function', type=str, required=True),
        'args': ActionParameterDef(id='args', type=list, default=[]),
        'kwargs': ActionParameterDef(id='kwargs', type=dict, default={}),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        params = context.resolve_params(self.raw_params)
        func_path = params.get('function', '')
        args = params.get('args', [])
        kwargs = params.get('kwargs', {})

        try:
            result = self._call_function(context, func_path, args, kwargs)
            self.data['result'] = result
            context.complete(data={'result': result})
            return ActionResult.COMPLETED
        except Exception as e:
            self.logger.error(f"Function '{func_path}' failed: {e}")
            context.fail(str(e))
            return ActionResult.ERROR

    def _call_function(self, context: ActionContext, func_path: str, args: list, kwargs: dict) -> Any:
        """Navigate dot-path on context objects and call the target function."""
        if func_path.startswith('.'):
            func_path = func_path[1:]

        parts = func_path.split('.')

        # First part is the context object name
        obj = context.runner.get_context_object(parts[0])
        if obj is None:
            raise AttributeError(f"Context object '{parts[0]}' not found")

        # Navigate dot-path
        for part in parts[1:-1]:
            obj = getattr(obj, part)

        func = getattr(obj, parts[-1])
        if not callable(func):
            raise TypeError(f"'{parts[-1]}' is not callable")

        return func(*args, **kwargs)


# === Experiment Control ===

@dataclass
class StopAction(ActionBase):
    """End the experiment."""
    type_id: ClassVar[str] = 'stop'
    transition_ports: ClassVar[list[str]] = []
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'status': ActionParameterDef(id='status', type=str, default='finished'),
        'message': ActionParameterDef(id='message', type=str, default=''),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        from core.utils.experiments.types import ExperimentStatus
        params = context.resolve_params(self.raw_params)
        status_str = params.get('status', 'finished')
        message = params.get('message', '')

        try:
            status = ExperimentStatus(status_str)
        except ValueError:
            status = ExperimentStatus.FINISHED

        context.runner.stop(reason=message, status=status)
        return ActionResult.COMPLETED


@dataclass
class MarkerAction(ActionBase):
    """Set a named marker (stored as a variable)."""
    type_id: ClassVar[str] = 'marker'
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'name': ActionParameterDef(id='name', type=str, required=True),
        'value': ActionParameterDef(id='value', default=True),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        params = context.resolve_params(self.raw_params)
        name = params.get('name', '')
        value = params.get('value', True)
        context.set_variable(f'_marker_{name}', value)
        self.data['name'] = name
        self.data['value'] = value
        context.complete()
        return ActionResult.COMPLETED


# === Logging ===

@dataclass
class LogAction(ActionBase):
    """Log a message to the terminal. Supports expression interpolation in message."""
    type_id: ClassVar[str] = 'log'
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'message': ActionParameterDef(id='message', type=str, required=True),
        'level': ActionParameterDef(id='level', type=str, default='info'),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        params = context.resolve_params(self.raw_params)
        message = str(params.get('message', ''))
        level = str(params.get('level', 'info')).lower()

        exp_logger = Logger(f'Experiment[{context.runner.definition.id}]')
        log_func = getattr(exp_logger, level, exp_logger.info)
        log_func(f"[{self.id}] {message}")

        context.complete()
        return ActionResult.COMPLETED


class MessageAction(ActionBase):
    """Emit a user-facing experiment message. Supports expression interpolation in text."""
    type_id: ClassVar[str] = 'message'
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {
        'text': ActionParameterDef(id='text', type=str, required=True),
        'level': ActionParameterDef(id='level', type=str, default='info'),
    }

    def execute(self, context: ActionContext) -> ActionResult:
        params = context.resolve_params(self.raw_params)
        text = str(params.get('text', ''))
        level = str(params.get('level', 'info')).lower()
        context.message(text, level)
        context.complete()
        return ActionResult.COMPLETED


# === Registration ===

def register_builtin_actions(registry: ActionRegistry):
    """Register all built-in action types with a registry."""
    builtin_types = [
        # Internal
        NoopAction,
        # Control flow
        GroupAction,
        ParallelAction,
        LoopAction,
        WhileAction,
        ConditionAction,
        # Timing
        WaitTimeAction,
        WaitTicksAction,
        # Events
        WaitForEventAction,
        EmitEventAction,
        # Variables
        SetVariableAction,
        SetParameterAction,
        # Functions
        ExecuteFunctionAction,
        # Logging
        LogAction,
        MessageAction,
        # Experiment control
        StopAction,
        MarkerAction,
    ]

    for cls in builtin_types:
        registry.register(cls)
