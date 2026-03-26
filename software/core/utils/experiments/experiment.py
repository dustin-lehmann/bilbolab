import threading
import time
import dataclasses
from dataclasses import dataclass, field
from typing import Any

from core.utils.events import event_definition, EventContainer, Event, EventFlag, TIMEOUT as EV_TIMEOUT
from core.utils.callbacks import callback_definition, CallbackContainer, CallbackGroup
from core.utils.logging_utils import Logger

from core.utils.experiments.types import (
    ActionStatus, ActionResult, ExperimentStatus, TriggerType,
    ActionTrigger, Transition, ExperimentActionData, MessageLevel, MISSING
)
from core.utils.experiments.expression import ExpressionEngine
from core.utils.experiments.action import ActionBase, ActionContext, ActionRegistry
from core.utils.experiments.requirement import (
    RequirementDefinition, RequirementRegistry, RequirementContext, RequirementResult
)
from core.utils.experiments.guard import (
    GuardDefinition, GuardRegistry, GuardContext, GuardBase
)


# === Experiment Definition ===

@dataclass
class ActionDefinition:
    """Declarative description of an action in an experiment."""
    id: str = ''
    type: str = ''
    params: dict[str, Any] = field(default_factory=dict)
    trigger: ActionTrigger | None = None
    transitions: dict[str, Any] | None = None
    sub_actions: list['ActionDefinition'] | None = None
    # Condition/while specific
    test: str | None = None
    # Condition branches
    then_actions: list['ActionDefinition'] | None = None
    else_actions: list['ActionDefinition'] | None = None
    # Loop specific
    count: str | int | None = None
    variable: str | None = None
    max_iterations: int | None = None
    # Timing delays (seconds)
    wait_before: float | None = None
    wait_after: float | None = None
    # Messages emitted before/after the action executes
    message_before: str | None = None
    message_after: str | None = None


@dataclass
class ExperimentDefinition:
    """Complete experiment definition with actions, variables, and metadata."""
    id: str = ''
    description: str = ''
    actions: list[ActionDefinition] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    requirements: list[RequirementDefinition] = field(default_factory=list)
    guards: list[GuardDefinition] = field(default_factory=list)
    setup_actions: list[ActionDefinition] = field(default_factory=list)
    cleanup_actions: list[ActionDefinition] = field(default_factory=list)
    timeout: float | None = None


# === Internal State Tracking ===

@dataclass
class _ActionState:
    """Internal runtime state for an action within the runner."""
    definition: ActionDefinition
    instance: ActionBase | None = None
    status: ActionStatus = ActionStatus.PENDING
    completed_port: str | None = None
    is_main_flow: bool = True  # part of the main sequential flow
    triggered_by: str | None = None  # source action ID that triggered this via transition


# === Experiment Events and Callbacks ===

@event_definition
class ExperimentEvents(EventContainer):
    started: Event
    finished: Event = Event(copy_data_on_set=False)
    error: Event = Event(flags=EventFlag('action_id', str))
    action_started: Event = Event(flags=EventFlag('id', str))
    action_finished: Event = Event(flags=EventFlag('id', str))
    message: Event = Event(flags=EventFlag('level', str), copy_data_on_set=False)


@callback_definition
class ExperimentCallbacks(CallbackGroup):
    step: CallbackContainer
    finished: CallbackContainer
    action_started: CallbackContainer
    action_finished: CallbackContainer


# === Logging Helpers ===

def _format_action_short(action: 'ActionDefinition') -> str:
    """Format an action as a compact one-line summary for logging."""
    reserved = {'id', 'type', 'trigger', 'transitions', 'actions', 'sub_actions',
                'test', 'then', 'else', 'count', 'variable', 'max_iterations',
                'params', 'wait_before', 'wait_after', 'message_before', 'message_after',
                'label', 'meta'}
    parts = [action.type]
    for key, val in action.params.items():
        if key in reserved:
            continue
        if isinstance(val, str) and len(val) > 30:
            val = val[:27] + '...'
        parts.append(f'{key}={val}')
    return ', '.join(parts)


def _format_requirement_short(req: 'RequirementDefinition') -> str:
    """Format a requirement as a compact one-line summary."""
    parts = [req.type]
    for key, val in req.params.items():
        parts.append(f'{key}={val}')
    return ', '.join(parts)


def _format_guard_short(guard: 'GuardDefinition') -> str:
    """Format a guard as a compact one-line summary."""
    parts = [guard.type]
    for key, val in guard.params.items():
        parts.append(f'{key}={val}')
    return ', '.join(parts)


# === Experiment Runner ===

class ExperimentRunner:
    """Robot-agnostic experiment execution engine.

    Driven by external step() calls at any rate. Manages action lifecycle,
    transition graph, expression evaluation, and timing triggers.
    """

    def __init__(self, definition: ExperimentDefinition, registry: ActionRegistry,
                 requirement_registry: RequirementRegistry | None = None,
                 guard_registry: GuardRegistry | None = None):
        self.definition = definition
        self.registry = registry
        self.requirement_registry = requirement_registry
        self.guard_registry = guard_registry
        self.expression_engine = ExpressionEngine()

        # Runtime state
        self.variables: dict[str, Any] = {}
        self.action_data: dict[str, ExperimentActionData] = {}
        self.action_instances: dict[str, ActionBase] = {}
        self.tick: int = 0
        self.time: float = 0.0
        self.status: ExperimentStatus | None = None
        self._start_time: float = 0.0

        # Internal
        self._action_states: dict[str, _ActionState] = {}
        self._transitions: list[Transition] = []
        self._pending_time_triggers: list[tuple[float, str]] = []  # (time, action_id)
        self._pending_tick_triggers: list[tuple[int, str]] = []  # (tick, action_id)
        self._pending_wait_before: list[tuple[float, str]] = []  # (activate_at, action_id)
        self._pending_wait_after: list[tuple[float, str, str]] = []  # (fire_at, action_id, port)
        self._context_objects: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._internal_events: dict[str, Event] = {}
        self._finished = False
        self._active_guards: list[GuardBase] = []

        # Public
        self.events = ExperimentEvents()
        self.callbacks = ExperimentCallbacks()
        self.logger = Logger(f'ExperimentRunner[{definition.id}]', level='DEBUG')

    def initialize(self, context_objects: dict[str, Any] | None = None):
        """Prepare experiment for execution. Must be called before step().

        Args:
            context_objects: Named objects available to execute_function actions
        """
        self._context_objects = context_objects or {}

        # Log experiment summary before doing anything
        self._log_experiment_summary()

        n_actions = len(self.definition.actions)
        self.message(f"Experiment loaded ({n_actions} action{'s' if n_actions != 1 else ''})")

        # Check requirements before doing anything else
        if self.definition.requirements and self.requirement_registry:
            failed = self._check_requirements()
            if failed:
                self._finished = True
                self.status = ExperimentStatus.ERROR
                reasons = '; '.join(r.message for r in failed)
                self.message(f"Requirements not met: {reasons}", MessageLevel.ERROR)
                self.events.error.set(flags={'action_id': ''})
                self.events.finished.set(data={'status': ExperimentStatus.ERROR, 'reason': reasons})
                self.logger.error(f"Requirements not met: {reasons}")
                return

        self.variables = dict(self.definition.variables)
        self._finished = False
        self.tick = 0
        self.time = 0.0
        self._start_time = 0.0  # set on first step()
        self.status = ExperimentStatus.RUNNING

        has_init_work = self.definition.guards or self.definition.setup_actions
        if has_init_work:
            self.message("Initializing...")

        # Set up guards
        if self.definition.guards and self.guard_registry:
            guard_context = GuardContext(self._context_objects, self.definition, runner=self)
            for guard_def in self.definition.guards:
                try:
                    instance = self.guard_registry.create_guard(
                        guard_def.id, guard_def.type, guard_def.params
                    )
                    # Emit default message_before from the guard class (if any)
                    default_msg = getattr(instance, 'default_message_before', None)
                    if default_msg:
                        self.message(default_msg)
                    instance.setup(guard_context)
                    self._active_guards.append(instance)
                    self.logger.info(f"  Guard '{guard_def.type}' set up")
                except Exception as e:
                    self.logger.error(f"  Guard '{guard_def.type}' setup failed: {e}")
                    self.message(f"Guard '{guard_def.type}' setup failed: {e}", MessageLevel.ERROR)
                    self._finish(ExperimentStatus.ERROR, f"Guard setup failed: {e}")
                    return

        # Run setup actions (sequential, blocking)
        if self.definition.setup_actions:
            self.message(f"Running setup actions ({len(self.definition.setup_actions)})")
            success = self._run_phase_actions(self.definition.setup_actions, 'setup')
            if not success:
                self.message("Setup action failed", MessageLevel.ERROR)
                self._finish(ExperimentStatus.ERROR, 'Setup action failed')
                return

        # Build action states and transitions from definitions
        self._build_action_graph(self.definition.actions)

        # Create action instances
        for action_id, state in self._action_states.items():
            defn = state.definition
            instance = self.registry.create_action(action_id, defn.type, defn.params)
            instance._definition = defn  # attach definition for control flow actions
            state.instance = instance
            self.action_instances[action_id] = instance
            self.action_data[action_id] = ExperimentActionData(
                action_type=defn.type,
                label=defn.params.get('label', ''),
                meta=defn.params.get('meta', {}),
                parameters=dict(instance.raw_params),
            )

        # Register time/tick triggers; immediate triggers are deferred to the first step()
        self._pending_immediate: list[str] = []
        for action_id, state in self._action_states.items():
            trigger = state.definition.trigger
            if trigger and trigger.type == TriggerType.IMMEDIATE:
                self._pending_immediate.append(action_id)
            elif trigger and trigger.type == TriggerType.TIME:
                self._pending_time_triggers.append((trigger.time, action_id))
            elif trigger and trigger.type == TriggerType.TICK:
                self._pending_tick_triggers.append((trigger.tick, action_id))

        self.message("Starting experiment")
        self.events.started.set()
        self.logger.info(f"Experiment '{self.definition.id}' running")

    def step(self) -> bool:
        """Advance the experiment by one tick.

        Returns:
            True if the experiment has finished.
        """
        if self._finished:
            return True

        # Capture start time and activate immediate actions on the first step
        if self._start_time == 0.0:
            self._start_time = time.time()
            for action_id in self._pending_immediate:
                self._schedule_activation(action_id)
            self._pending_immediate.clear()

        self.tick += 1
        self.time = time.time() - self._start_time

        # Check timeout
        if self.definition.timeout and self.time > self.definition.timeout:
            self.abort(reason='Experiment timeout', status=ExperimentStatus.TIMEOUT)
            return True

        # Evaluate time triggers
        triggered = []
        for t, action_id in self._pending_time_triggers:
            if self.time >= t:
                triggered.append((t, action_id))
                self._activate_action(action_id)
        for item in triggered:
            self._pending_time_triggers.remove(item)

        # Evaluate tick triggers
        triggered = []
        for tick, action_id in self._pending_tick_triggers:
            if self.tick >= tick:
                triggered.append((tick, action_id))
                self._activate_action(action_id)
        for item in triggered:
            self._pending_tick_triggers.remove(item)

        # Evaluate wait_before delays
        triggered = []
        for activate_at, action_id in self._pending_wait_before:
            if self.time >= activate_at:
                triggered.append((activate_at, action_id))
                self._activate_action(action_id)
        for item in triggered:
            self._pending_wait_before.remove(item)

        # Evaluate wait_after delays
        triggered = []
        for fire_at, action_id, port in self._pending_wait_after:
            if self.time >= fire_at:
                triggered.append((fire_at, action_id, port))
                self._fire_transitions(action_id, port)
        for item in triggered:
            self._pending_wait_after.remove(item)

        # Call step callbacks
        self.callbacks.step.call(tick=self.tick, time=self.time)

        # Check completion
        if self._check_completion():
            self._finish(ExperimentStatus.FINISHED)
            return True

        return False

    def abort(self, reason: str = '', status: ExperimentStatus = ExperimentStatus.ABORTED):
        """Stop the experiment with the given status."""
        if status == ExperimentStatus.ABORTED:
            self.logger.warning(f"Experiment aborted: {reason}")
        self._finish(status, reason)

    def get_context_object(self, name: str) -> Any:
        """Get a context object by name."""
        return self._context_objects.get(name)

    def message(self, text: str, level: MessageLevel | str = MessageLevel.INFO):
        """Emit an experiment message for display to the user.

        Messages are logged and emitted as events so that external listeners
        (experiment handler, GUI) can display them.

        Args:
            text: The message text.
            level: Message level ('info', 'warning', 'error').
        """
        if isinstance(level, str):
            level = MessageLevel(level)
        log_func = getattr(self.logger, level.value, self.logger.info)
        log_func(f"[message] {text}")
        self.events.message.set(
            data={'text': text, 'level': level.value},
            flags={'level': level.value},
        )

    # === Internal Methods ===

    def _check_requirements(self) -> list[RequirementResult]:
        """Check all experiment requirements. Returns list of failed results."""
        context = RequirementContext(self._context_objects, self.definition)
        failed = []
        for req_def in self.definition.requirements:
            try:
                instance = self.requirement_registry.create_requirement(
                    req_def.id, req_def.type, req_def.params
                )
                result = instance.check(context)
                if not result.passed:
                    failed.append(result)
                    self.logger.error(f"Requirement '{req_def.id}' failed: {result.message}")
            except Exception as e:
                failed.append(RequirementResult(passed=False, message=f"Requirement '{req_def.id}' error: {e}"))
                self.logger.error(f"Requirement '{req_def.id}' raised exception: {e}")
        return failed

    def _log_experiment_summary(self):
        """Log a human-readable summary of the experiment before execution."""
        defn = self.definition
        sep = '─' * 60

        self.logger.info('')
        self.logger.info(sep)
        self.logger.info(f'Experiment: {defn.id}')
        if defn.description:
            self.logger.info(f'  {defn.description}')
        if defn.timeout:
            self.logger.info(f'  Timeout: {defn.timeout}s')
        self.logger.info(sep)

        if defn.requirements:
            self.logger.info('Requirements:')
            for req in defn.requirements:
                self.logger.info(f'  - {_format_requirement_short(req)}')

        if defn.guards:
            self.logger.info('Guards:')
            for g in defn.guards:
                self.logger.info(f'  - {_format_guard_short(g)}')

        if defn.requirements or defn.guards:
            self.logger.info(sep)

        if defn.setup_actions:
            self.logger.info(f'Setup Actions ({len(defn.setup_actions)}):')
            for i, action in enumerate(defn.setup_actions):
                self.logger.info(f'  {i + 1:>3}. {_format_action_short(action)}')
            self.logger.info(sep)

        self.logger.info(f'Actions ({len(defn.actions)}):')
        for i, action in enumerate(defn.actions):
            self.logger.info(f'  {i + 1:>3}. {_format_action_short(action)}')

        if defn.cleanup_actions:
            self.logger.info(sep)
            self.logger.info(f'Cleanup Actions ({len(defn.cleanup_actions)}):')
            for i, action in enumerate(defn.cleanup_actions):
                self.logger.info(f'  {i + 1:>3}. {_format_action_short(action)}')

        self.logger.info(sep)
        self.logger.info('')

    def _run_phase_actions(self, action_defs: list[ActionDefinition], phase: str) -> bool:
        """Run a list of actions sequentially and blocking.

        Used for setup_actions (before main experiment) and cleanup_actions (after).
        Resolves variable expressions in parameters.
        Supports wait_before (delay before executing) and wait_after (delay after completing).
        Returns True on success.
        """
        self.logger.info(f"Running {phase} actions ({len(action_defs)})...")
        scope = dict(self.variables)

        for i, defn in enumerate(action_defs):
            action_id = defn.id or f'{phase}_{i}'
            self.logger.info(f"  {phase}[{i}]: {_format_action_short(defn)}")

            try:
                if defn.wait_before and defn.wait_before > 0:
                    self.logger.info(f"  {phase}[{i}] waiting {defn.wait_before}s before start")
                    time.sleep(defn.wait_before)

                resolved_params = self.expression_engine.resolve_value(dict(defn.params), scope)
                instance = self.registry.create_action(action_id, defn.type, resolved_params)
                context = ActionContext(runner=self, action=instance)
                result = instance.execute(context)

                if result == ActionResult.ERROR:
                    self.logger.error(f"  {phase}[{i}] '{defn.type}' failed")
                    return False

                self.logger.info(f"  {phase}[{i}] '{defn.type}' done")

                if defn.wait_after and defn.wait_after > 0:
                    self.logger.info(f"  {phase}[{i}] waiting {defn.wait_after}s after completion")
                    time.sleep(defn.wait_after)
            except Exception as e:
                self.logger.error(f"  {phase}[{i}] '{defn.type}' raised exception: {e}")
                return False

        self.logger.info(f"{phase.capitalize()} actions completed")
        return True

    def _build_action_graph(self, definitions: list[ActionDefinition]):
        """Build action states and transitions from definitions."""
        first_action_id = None

        for defn in definitions:
            state = _ActionState(definition=defn)

            # Determine if action is main flow
            if defn.trigger and defn.trigger.type in (TriggerType.EVENT, TriggerType.PERIODIC):
                state.is_main_flow = False

            self._action_states[defn.id] = state

            if first_action_id is None:
                first_action_id = defn.id

            # Build transitions from definition
            if defn.transitions:
                for port, target_spec in defn.transitions.items():
                    self._parse_transition_value(defn.id, port, target_spec)

    def _parse_transition_value(self, source_id: str, port: str, target_spec):
        """Parse a transition target specification into Transition objects.

        Supports:
            - String: "action_1"
            - List: ["action_1", "action_2"] or [{target: ..., data: ...}, ...]
            - Dict: {target: "action_1", data: {param: "$value"}}
        """
        if isinstance(target_spec, str):
            self._transitions.append(Transition(source_id, port, target_spec))
        elif isinstance(target_spec, list):
            for item in target_spec:
                self._parse_transition_value(source_id, port, item)
        elif isinstance(target_spec, dict):
            target_id = target_spec['target']
            mapping = target_spec.get('data')
            self._transitions.append(Transition(source_id, port, target_id, mapping=mapping))

    def _activate_action(self, action_id: str):
        """Start executing an action."""
        state = self._action_states.get(action_id)
        if state is None:
            self.logger.error(f"Cannot activate unknown action: {action_id}")
            return
        if state.status != ActionStatus.PENDING:
            return

        instance = state.instance
        if instance is None:
            self.logger.error(f"Action '{action_id}' has no instance")
            return

        state.status = ActionStatus.RUNNING
        instance.status = ActionStatus.RUNNING

        # Record start timing and resolve parameters for reporting
        entry = self.action_data.get(action_id)
        if entry:
            entry.status = ActionStatus.RUNNING
            entry.start_tick = self.tick
            entry.start_time = time.time() - self._start_time
            # Resolve expressions in parameters so the result JSON has actual values
            try:
                scope = self._build_scope(for_action_id=action_id)
                entry.parameters = self.expression_engine.resolve_value(dict(instance.raw_params), scope)
            except Exception as e:
                self.logger.warning(f"Failed to resolve params for '{action_id}': {e}")

        # Emit message_before if defined on the action
        if state.definition.message_before:
            self.message(state.definition.message_before)

        context = ActionContext(runner=self, action=instance)
        instance.events.started.set()
        self.events.action_started.set(flags={'id': action_id})
        self.callbacks.action_started.call(action_id=action_id)
        self.logger.debug(f"Activating action '{action_id}' (type={state.definition.type})")

        try:
            result = instance.execute(context)
        except Exception as e:
            self.logger.error(f"Action '{action_id}' raised exception: {e}")
            self._on_action_complete(action_id, 'error', {'error': str(e)})
            return

        if result == ActionResult.COMPLETED:
            # Synchronous completion — context.complete() was already called by execute()
            pass
        elif result == ActionResult.ERROR:
            # Synchronous error
            if state.status != ActionStatus.ERROR:
                self._on_action_complete(action_id, 'error', {})
        # ASYNC: action will call context.complete() or context.fail() later

    def _on_action_complete(self, action_id: str, port: str, action_data: dict):
        """Handle action completion, fire transitions (respecting wait_after)."""
        with self._lock:
            state = self._action_states.get(action_id)
            if state is None:
                return

            if port == 'error':
                state.status = ActionStatus.ERROR
                if state.instance:
                    state.instance.status = ActionStatus.ERROR
            else:
                state.status = ActionStatus.COMPLETED
                if state.instance:
                    state.instance.status = ActionStatus.COMPLETED

            state.completed_port = port

            # Update ExperimentActionData entry
            entry = self.action_data.get(action_id)
            if entry:
                entry.status = state.status
                entry.end_tick = self.tick
                entry.end_time = time.time() - self._start_time
                entry.duration = entry.end_time - entry.start_time
                entry.data = action_data
                if port == 'error':
                    entry.error_message = action_data.get('error', '')

            self.events.action_finished.set(flags={'id': action_id})
            self.callbacks.action_finished.call(action_id=action_id)
            self.logger.debug(f"Action '{action_id}' completed (port={port})")

            # Emit message_after if defined on the action (only on success)
            if port != 'error' and state.definition.message_after:
                self.message(state.definition.message_after)

            # Check wait_after — delay transition firing
            wait_after = state.definition.wait_after
            if wait_after and wait_after > 0 and port != 'error':
                fire_at = time.time() - self._start_time + wait_after
                self._pending_wait_after.append((fire_at, action_id, port))
                self.logger.debug(f"Action '{action_id}' waiting {wait_after}s before next")
                return

            self._fire_transitions(action_id, port)

    def _fire_transitions(self, action_id: str, port: str):
        """Fire transitions from a completed action's port."""
        # Fire transitions from this action's completed port
        for transition in self._transitions:
            if transition.source_id == action_id and transition.source_port == port:
                # Apply data mapping if present
                if transition.mapping:
                    self._apply_transition_mapping(transition, action_id)

                target_state = self._action_states.get(transition.target_id)
                if target_state and target_state.status == ActionStatus.PENDING:
                    target_state.triggered_by = action_id
                    self._schedule_activation(transition.target_id)

        # Also fire 'done' transitions for 'error' if no explicit error transition exists
        if port == 'error':
            has_error_transition = any(
                t.source_id == action_id and t.source_port == 'error'
                for t in self._transitions
            )
            if not has_error_transition:
                # Propagate error to experiment level
                self.events.error.set(flags={'action_id': action_id})

    def _schedule_activation(self, action_id: str):
        """Schedule action activation, respecting wait_before."""
        state = self._action_states.get(action_id)
        if state is None:
            return
        wait_before = state.definition.wait_before
        if wait_before and wait_before > 0:
            activate_at = time.time() - self._start_time + wait_before
            self._pending_wait_before.append((activate_at, action_id))
            self.logger.debug(f"Action '{action_id}' waiting {wait_before}s before starting")
        else:
            self._activate_action(action_id)

    def _apply_transition_mapping(self, transition: Transition, source_action_id: str):
        """Apply a transition's data mapping to the target action's parameters."""
        target = self.action_instances.get(transition.target_id)
        if target is None:
            return

        # Build scope with source action data available unprefixed
        scope = self._build_scope()
        source_entry = self.action_data.get(source_action_id)
        if source_entry:
            for key, value in source_entry.data.items():
                scope[key] = value  # unprefixed: $result works

        for param_name, value_expr in transition.mapping.items():
            resolved = self.expression_engine.resolve_value(value_expr, scope)
            target.raw_params[param_name] = resolved

    def _emit_internal_event(self, event_id: str, data: Any = None, flags: dict | None = None):
        """Emit an internal experiment event (for event triggers and wait_for_event)."""
        if event_id not in self._internal_events:
            self._internal_events[event_id] = Event(id=event_id)
        self._internal_events[event_id].set(data=data, flags=flags)

    def get_internal_event(self, event_id: str) -> Event:
        """Get or create an internal experiment event."""
        if event_id not in self._internal_events:
            self._internal_events[event_id] = Event(id=event_id)
        return self._internal_events[event_id]

    def _check_completion(self) -> bool:
        """Check if all main-flow actions have completed or errored.

        Returns True when no main-flow actions are still pending/running.
        If a main-flow action errored without an error transition, the
        experiment finishes immediately with ERROR status (downstream
        pending actions will never run).
        """
        # Don't finish while there are pending delays
        if self._pending_wait_before or self._pending_wait_after:
            return False

        has_error = False
        has_unhandled_error = False

        for state in self._action_states.values():
            if not state.is_main_flow:
                continue

            if state.status == ActionStatus.ERROR:
                has_error = True
                # Check if this error has an explicit error transition
                has_error_transition = any(
                    t.source_id == state.definition.id and t.source_port == 'error'
                    for t in self._transitions
                )
                if not has_error_transition:
                    has_unhandled_error = True

            if state.status == ActionStatus.RUNNING:
                return False

        # Unhandled error: downstream actions will never run, finish now
        if has_unhandled_error:
            self._finish(ExperimentStatus.ERROR)
            return True

        # Still have pending actions that might be reached
        for state in self._action_states.values():
            if state.is_main_flow and state.status == ActionStatus.PENDING:
                return False

        if has_error:
            self._finish(ExperimentStatus.ERROR)
            return True
        return True

    def _finish(self, status: ExperimentStatus, reason: str = ''):
        """Finalize experiment."""
        if self._finished:
            return
        self._finished = True
        self.status = status

        # Emit finish message with appropriate level
        finish_levels = {
            ExperimentStatus.FINISHED: MessageLevel.INFO,
            ExperimentStatus.ERROR: MessageLevel.ERROR,
            ExperimentStatus.TIMEOUT: MessageLevel.WARNING,
            ExperimentStatus.ABORTED: MessageLevel.WARNING,
        }
        level = finish_levels.get(status, MessageLevel.INFO)
        msg = f"Experiment {status.value}"
        if reason:
            msg += f": {reason}"
        self.message(msg, level)

        # Run cleanup actions (sequential, blocking, always runs)
        if self.definition.cleanup_actions:
            self.message(f"Running cleanup actions ({len(self.definition.cleanup_actions)})")
            self._run_phase_actions(self.definition.cleanup_actions, 'cleanup')

        # Tear down guards in reverse order (guaranteed cleanup)
        if self._active_guards:
            guard_context = GuardContext(self._context_objects, self.definition, runner=self)
            for guard in reversed(self._active_guards):
                try:
                    guard.teardown(guard_context)
                    self.logger.info(f"Guard '{guard.id}' ({guard.type_id}) torn down")
                except Exception as e:
                    self.logger.error(f"Guard '{guard.id}' teardown failed: {e}")
            self._active_guards.clear()

        # Mark pending actions as skipped
        for action_id, state in self._action_states.items():
            if state.status == ActionStatus.PENDING:
                state.status = ActionStatus.SKIPPED
                if state.instance:
                    state.instance.status = ActionStatus.SKIPPED
                entry = self.action_data.get(action_id)
                if entry:
                    entry.status = ActionStatus.SKIPPED

        self.events.finished.set(data={'status': status, 'reason': reason})
        self.callbacks.finished.call(status=status, reason=reason)
        self.logger.info(f"Experiment '{self.definition.id}' finished: {status.value}"
                         + (f" ({reason})" if reason else ''))

    def _build_scope(self, for_action_id: str | None = None) -> dict[str, Any]:
        """Build the expression evaluation scope from current state.

        Args:
            for_action_id: If provided, adds ``data.field`` aliases for the
                output of whichever action triggered this one via transition.
        """
        scope = dict(self.variables)
        scope['tick'] = self.tick
        scope['time'] = self.time

        # Add action data: action_id.field_name
        for action_id, entry in self.action_data.items():
            for key, value in entry.data.items():
                scope[f'{action_id}.{key}'] = value

        # Add action parameters: action_id:param_name
        for action_id, instance in self.action_instances.items():
            for key, value in instance.raw_params.items():
                scope[f'{action_id}:{key}'] = value

        # Implicit 'data.' alias: previous action's output data
        if for_action_id:
            state = self._action_states.get(for_action_id)
            if state and state.triggered_by:
                source_entry = self.action_data.get(state.triggered_by)
                if source_entry:
                    for key, value in source_entry.data.items():
                        scope[f'data.{key}'] = value

        return scope
