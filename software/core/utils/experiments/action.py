import abc
import threading
import dataclasses
from dataclasses import dataclass, field
from typing import Any, ClassVar, get_type_hints

from core.utils.events import event_definition, EventContainer, Event
from core.utils.callbacks import callback_definition, CallbackContainer, CallbackGroup
from core.utils.logging_utils import Logger

from core.utils.experiments.types import (
    ActionStatus, ActionResult, ActionDataDef, ActionParameterDef, MISSING
)


# === Events and Callbacks ===

@event_definition
class ActionEvents(EventContainer):
    started: Event
    finished: Event = Event(copy_data_on_set=False)
    error: Event
    timeout: Event


@callback_definition
class ActionCallbacks(CallbackGroup):
    finished: CallbackContainer


# === ActionContext ===

class ActionContext:
    """Passed to actions during execution. Provides access to experiment state."""

    def __init__(self, runner, action):
        self.runner = runner
        self.action = action
        self._lock = threading.Lock()

    def complete(self, port: str = 'done', data: dict | None = None):
        """Signal that the action completed successfully.

        Args:
            port: The transition port name (default 'done').
            data: Action data dict, or a dataclass instance (auto-converted to dict).
        """
        if data is not None:
            if dataclasses.is_dataclass(data) and not isinstance(data, type):
                data = dataclasses.asdict(data)
            self.action._data.update(data)
        self.action.status = ActionStatus.COMPLETED
        self.action.events.finished.set(data={'port': port})
        self.runner._on_action_complete(self.action.id, port, self.action._data)

    def fail(self, message: str = ''):
        """Signal that the action failed."""
        self.action.status = ActionStatus.ERROR
        self.action.events.error.set(data={'message': message})
        self.runner._on_action_complete(self.action.id, 'error', {'error': message})

    def evaluate(self, expression: str) -> Any:
        """Evaluate an expression against the current experiment scope."""
        scope = self.runner._build_scope(for_action_id=self.action.id)
        return self.runner.expression_engine.evaluate(expression, scope)

    def get_variable(self, name: str) -> Any:
        """Get an experiment variable."""
        with self._lock:
            return self.runner.variables.get(name, MISSING)

    def set_variable(self, name: str, value: Any):
        """Set an experiment variable."""
        with self._lock:
            self.runner.variables[name] = value

    def emit_event(self, event_id: str, data: Any = None, flags: dict | None = None):
        """Emit an internal experiment event."""
        self.runner._emit_internal_event(event_id, data, flags)

    def get_action_data(self, action_id: str, field_name: str) -> Any:
        """Get a data field from a completed action."""
        entry = self.runner.action_data.get(action_id)
        if entry is None:
            return MISSING
        return entry.data.get(field_name, MISSING)

    def get_action_parameter(self, action_id: str, param_name: str) -> Any:
        """Get a parameter from an action instance."""
        action = self.runner.action_instances.get(action_id)
        if action is None:
            return MISSING
        return action.raw_params.get(param_name, MISSING)

    def set_action_parameter(self, action_id: str, param_name: str, value: Any):
        """Set a parameter on an action instance at runtime."""
        action = self.runner.action_instances.get(action_id)
        if action is not None:
            action.raw_params[param_name] = value

    def resolve_params(self, params: dict) -> dict:
        """Resolve all expressions in a parameter dict."""
        scope = self.runner._build_scope(for_action_id=self.action.id)
        return self.runner.expression_engine.resolve_value(params, scope)

    def message(self, text: str, level: str = 'info'):
        """Emit an experiment message for display to the user.

        Args:
            text: The message text.
            level: Message level ('info', 'warning', 'error').
        """
        self.runner.message(text, level)


# === ActionBase ===

@dataclass
class ActionBase(abc.ABC):
    """Abstract base class for all experiment actions.

    Subclasses must define class-level metadata and implement execute().
    """

    # Class-level metadata (override in subclasses)
    type_id: ClassVar[str] = ''
    data_type: ClassVar[type | None] = None
    params_type: ClassVar[type | None] = None
    data_defs: ClassVar[dict[str, ActionDataDef]] = {}
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {}
    transition_ports: ClassVar[list[str]] = ['done']  # 'error' is always implicit

    # Instance state
    id: str = ''
    raw_params: dict[str, Any] = field(default_factory=dict)
    status: ActionStatus = ActionStatus.PENDING

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # --- data_type and data_defs ---
        data_cls = cls.__dict__.get('Data')
        if data_cls is not None and dataclasses.is_dataclass(data_cls):
            # Inner Data dataclass → set data_type and auto-generate data_defs
            cls.data_type = data_cls
            cls.data_defs = {
                f.name: ActionDataDef(id=f.name)
                for f in dataclasses.fields(data_cls)
            }
        elif 'data_type' in cls.__dict__ and cls.__dict__['data_type'] is not None:
            dt = cls.__dict__['data_type']
            if dataclasses.is_dataclass(dt):
                cls.data_defs = {
                    f.name: ActionDataDef(id=f.name)
                    for f in dataclasses.fields(dt)
                }
            else:
                # Atomic type (float, int, str, etc.)
                cls.data_defs = {'value': ActionDataDef(id='value')}

        # --- params_type and parameter_defs ---
        params_cls = cls.__dict__.get('Params')
        if params_cls is not None and dataclasses.is_dataclass(params_cls):
            # Inner Params dataclass → set params_type and auto-generate parameter_defs
            cls.params_type = params_cls
            cls.parameter_defs = {}
            try:
                type_hints = get_type_hints(params_cls)
            except Exception:
                type_hints = {}
            for f in dataclasses.fields(params_cls):
                has_default = (f.default is not dataclasses.MISSING
                               or f.default_factory is not dataclasses.MISSING)
                default_val = f.default if f.default is not dataclasses.MISSING else MISSING
                cls.parameter_defs[f.name] = ActionParameterDef(
                    id=f.name,
                    type=type_hints.get(f.name),
                    required=not has_default,
                    default=default_val,
                )
        elif 'params_type' in cls.__dict__ and cls.__dict__['params_type'] is not None:
            pt = cls.__dict__['params_type']
            if dataclasses.is_dataclass(pt):
                cls.parameter_defs = {}
                try:
                    type_hints = get_type_hints(pt)
                except Exception:
                    type_hints = {}
                for f in dataclasses.fields(pt):
                    has_default = (f.default is not dataclasses.MISSING
                                   or f.default_factory is not dataclasses.MISSING)
                    default_val = f.default if f.default is not dataclasses.MISSING else MISSING
                    cls.parameter_defs[f.name] = ActionParameterDef(
                        id=f.name,
                        type=type_hints.get(f.name),
                        required=not has_default,
                        default=default_val,
                    )
            else:
                # Atomic type
                cls.parameter_defs = {'value': ActionParameterDef(id='value', required=True)}

    def __post_init__(self):
        self._data: dict[str, Any] = {}
        self.events = ActionEvents()
        self.callbacks = ActionCallbacks()
        self.logger = Logger(f'Action[{self.type_id}:{self.id}]')
        self._definition = None  # set by runner or parent action after creation

    # --- data property ---

    @property
    def data(self):
        """Typed view of action data.

        - data_type=None   → returns the raw dict (mutable, same as _data)
        - data_type=@dataclass → returns an instance of that dataclass
        - data_type=float/int/… → returns the atomic value

        Setter accepts dict, dataclass instance, or atomic value.
        Note: modifying fields on a returned dataclass does NOT update _data.
        Use the setter or context.complete(data=...) to persist changes.
        """
        dt = type(self).data_type
        if dt is None:
            return self._data
        if dataclasses.is_dataclass(dt):
            field_names = {f.name for f in dataclasses.fields(dt)}
            kwargs = {k: v for k, v in self._data.items() if k in field_names}
            return dt(**kwargs)
        # Atomic type
        val = next(iter(self._data.values()), None) if self._data else None
        return dt(val) if val is not None else dt()

    @data.setter
    def data(self, value):
        if value is None:
            self._data = {}
        elif isinstance(value, dict):
            self._data = value
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            self._data = dataclasses.asdict(value)
        else:
            # Atomic value
            self._data = {'value': value}

    # --- params property ---

    @property
    def params(self):
        """Typed view of raw parameters (unresolved).

        - params_type=None     → returns raw_params dict directly
        - params_type=@dataclass → returns a dataclass instance
        - params_type=float/…   → returns the atomic value

        For resolved parameters (with expression evaluation), use get_params(context).
        """
        pt = type(self).params_type
        if pt is None:
            return self.raw_params
        if dataclasses.is_dataclass(pt):
            field_names = {f.name for f in dataclasses.fields(pt)}
            kwargs = {k: v for k, v in self.raw_params.items() if k in field_names}
            return pt(**kwargs)
        # Atomic type
        val = next(iter(self.raw_params.values()), None) if self.raw_params else None
        return pt(val) if val is not None else pt()

    @params.setter
    def params(self, value):
        if value is None:
            self.raw_params = {}
        elif isinstance(value, dict):
            self.raw_params = value
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            self.raw_params = dataclasses.asdict(value)
        else:
            # Atomic value
            self.raw_params = {'value': value}

    # --- Methods ---

    def get_params(self, context: ActionContext):
        """Resolve parameters and return typed result.

        - params_type=@dataclass → returns instance with resolved values
        - params_type=float/…    → returns resolved atomic value
        - params_type=None       → returns resolved dict
        """
        resolved = context.resolve_params(self.raw_params)
        pt = type(self).params_type
        if pt is not None:
            if dataclasses.is_dataclass(pt):
                field_names = {f.name for f in dataclasses.fields(pt)}
                return pt(**{k: v for k, v in resolved.items() if k in field_names})
            # Atomic type
            val = next(iter(resolved.values()), None) if resolved else None
            return pt(val) if val is not None else pt()
        return resolved

    @abc.abstractmethod
    def execute(self, context: ActionContext) -> ActionResult:
        """Execute the action.

        Returns:
            ActionResult.COMPLETED - action finished synchronously
            ActionResult.ASYNC - action is running asynchronously (will call context.complete/fail)
            ActionResult.ERROR - action failed synchronously
        """
        ...

    @classmethod
    def from_params(cls, action_id: str, params: dict[str, Any]) -> 'ActionBase':
        """Create an action instance from parsed parameters.

        Override this in subclasses to add custom parameter parsing/validation.
        The default implementation simply passes raw_params through.
        """
        return cls(id=action_id, raw_params=params)

    def on_reset(self):
        """Called before each loop iteration to reset action state."""
        self.status = ActionStatus.PENDING
        self._data.clear()


# === ActionRegistry ===

class ActionRegistry:
    """Registry of action types. Maps type_id strings to ActionBase subclasses."""

    def __init__(self):
        self._types: dict[str, type[ActionBase]] = {}
        self.logger = Logger('ActionRegistry')

    def register(self, action_class: type[ActionBase]):
        """Register an action class by its type_id."""
        type_id = action_class.type_id
        if not type_id:
            raise ValueError(f"Action class {action_class.__name__} has no type_id")
        if type_id in self._types:
            self.logger.warning(f"Overwriting action type '{type_id}'")
        self._types[type_id] = action_class

    def create_action(self, action_id: str, type_id: str, params: dict[str, Any] = None) -> ActionBase:
        """Create an action instance from a type_id and parameters.

        Uses the action class's from_params() classmethod, which subclasses
        can override for custom parameter parsing/validation.
        """
        cls = self._types.get(type_id)
        if cls is None:
            raise ValueError(f"Unknown action type: '{type_id}'")
        return cls.from_params(action_id, params or {})

    def has_type(self, type_id: str) -> bool:
        return type_id in self._types

    def get_type(self, type_id: str) -> type[ActionBase] | None:
        return self._types.get(type_id)

    def list_types(self) -> list[str]:
        return list(self._types.keys())
