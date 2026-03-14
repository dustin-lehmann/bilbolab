import abc
import dataclasses
from dataclasses import dataclass, field
from typing import Any, ClassVar

from core.utils.logging_utils import Logger

from core.utils.experiments.types import ActionParameterDef, MISSING


# === Result ===

@dataclass
class RequirementResult:
    """Result of a requirement check."""
    passed: bool
    message: str = ''


# === Definition ===

@dataclass
class RequirementDefinition:
    """Declarative description of a requirement in an experiment."""
    id: str = ''
    type: str = ''
    params: dict[str, Any] = field(default_factory=dict)


# === Context ===

class RequirementContext:
    """Lightweight context passed to requirement checks.

    Provides access to context objects (robot, testbed, etc.) and the
    experiment definition.
    """

    def __init__(self, context_objects: dict, definition=None):
        self.context_objects = context_objects
        self.definition = definition

    def get_object(self, name: str) -> Any:
        """Get a context object by name."""
        return self.context_objects.get(name)


# === RequirementBase ===

@dataclass
class RequirementBase(abc.ABC):
    """Abstract base class for all experiment requirements.

    Follows the same pattern as ActionBase: subclasses define a type_id,
    an inner Params dataclass (auto-generates parameter_defs via
    __init_subclass__), and implement check().
    """

    # Class-level metadata (override in subclasses)
    type_id: ClassVar[str] = ''
    params_type: ClassVar[type | None] = None
    parameter_defs: ClassVar[dict[str, ActionParameterDef]] = {}

    # Instance state
    id: str = ''
    raw_params: dict[str, Any] = field(default_factory=dict)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        params_cls = cls.__dict__.get('Params')
        if params_cls is not None and dataclasses.is_dataclass(params_cls):
            cls.params_type = params_cls
            cls.parameter_defs = {}
            for f in dataclasses.fields(params_cls):
                has_default = (f.default is not dataclasses.MISSING
                               or f.default_factory is not dataclasses.MISSING)
                default_val = f.default if f.default is not dataclasses.MISSING else MISSING
                cls.parameter_defs[f.name] = ActionParameterDef(
                    id=f.name,
                    required=not has_default,
                    default=default_val,
                )

    def __post_init__(self):
        self.logger = Logger(f'Requirement[{self.type_id}:{self.id}]')

    # --- params property ---

    def get_params_raw(self):
        """Return typed params from raw_params (no expression resolution).

        - params_type=@dataclass -> returns a dataclass instance
        - params_type=None -> returns the raw dict
        """
        pt = type(self).params_type
        if pt is None:
            return self.raw_params
        if dataclasses.is_dataclass(pt):
            field_names = {f.name for f in dataclasses.fields(pt)}
            kwargs = {k: v for k, v in self.raw_params.items() if k in field_names}
            return pt(**kwargs)
        return self.raw_params

    # --- Abstract method ---

    @abc.abstractmethod
    def check(self, context: RequirementContext) -> RequirementResult:
        """Check whether this requirement is satisfied.

        Args:
            context: Provides access to context objects and experiment definition.

        Returns:
            RequirementResult indicating pass/fail and an optional message.
        """
        ...

    @classmethod
    def from_params(cls, req_id: str, params: dict[str, Any]) -> 'RequirementBase':
        """Create a requirement instance from parsed parameters."""
        return cls(id=req_id, raw_params=params)


# === RequirementRegistry ===

class RequirementRegistry:
    """Registry of requirement types. Maps type_id strings to RequirementBase subclasses."""

    def __init__(self):
        self._types: dict[str, type[RequirementBase]] = {}
        self.logger = Logger('RequirementRegistry')

    def register(self, requirement_class: type[RequirementBase]):
        """Register a requirement class by its type_id."""
        type_id = requirement_class.type_id
        if not type_id:
            raise ValueError(f"Requirement class {requirement_class.__name__} has no type_id")
        if type_id in self._types:
            self.logger.warning(f"Overwriting requirement type '{type_id}'")
        self._types[type_id] = requirement_class

    def create_requirement(self, req_id: str, type_id: str, params: dict[str, Any] = None) -> RequirementBase:
        """Create a requirement instance from a type_id and parameters."""
        cls = self._types.get(type_id)
        if cls is None:
            raise ValueError(f"Unknown requirement type: '{type_id}'")
        return cls.from_params(req_id, params or {})

    def has_type(self, type_id: str) -> bool:
        return type_id in self._types

    def get_type(self, type_id: str) -> type[RequirementBase] | None:
        return self._types.get(type_id)

    def list_types(self) -> list[str]:
        return list(self._types.keys())


# === Builtin Requirements ===

class OSRequirement(RequirementBase):
    """Check that the current operating system matches the expected value."""
    type_id = 'os'

    @dataclass
    class Params:
        os: str  # 'linux', 'darwin', 'windows'

    def check(self, context: RequirementContext) -> RequirementResult:
        import platform
        current = platform.system().lower()
        expected = self.get_params_raw().os.lower()
        passed = current == expected
        return RequirementResult(
            passed=passed,
            message=f"Expected OS '{expected}', got '{current}'" if not passed else '',
        )


class DateRangeRequirement(RequirementBase):
    """Check that the current date falls within an optional range."""
    type_id = 'date_range'

    @dataclass
    class Params:
        after: str = ''   # ISO date string, e.g. '2025-01-01'
        before: str = ''  # ISO date string

    def check(self, context: RequirementContext) -> RequirementResult:
        from datetime import date
        today = date.today()
        params = self.get_params_raw()

        if params.after:
            after_date = date.fromisoformat(params.after)
            if today < after_date:
                return RequirementResult(
                    passed=False,
                    message=f"Current date {today} is before required date {after_date}",
                )

        if params.before:
            before_date = date.fromisoformat(params.before)
            if today > before_date:
                return RequirementResult(
                    passed=False,
                    message=f"Current date {today} is after required date {before_date}",
                )

        return RequirementResult(passed=True)


class ContextObjectRequirement(RequirementBase):
    """Check that a named context object exists (and optionally check its type)."""
    type_id = 'context_object'

    @dataclass
    class Params:
        name: str         # context object key
        type: str = ''    # optional: check isinstance (fully qualified class name)

    def check(self, context: RequirementContext) -> RequirementResult:
        params = self.get_params_raw()
        obj = context.get_object(params.name)

        if obj is None:
            return RequirementResult(
                passed=False,
                message=f"Context object '{params.name}' not found",
            )

        if params.type:
            type_name = type(obj).__name__
            if type_name != params.type:
                return RequirementResult(
                    passed=False,
                    message=f"Context object '{params.name}' has type '{type_name}', expected '{params.type}'",
                )

        return RequirementResult(passed=True)


def register_builtin_requirements(registry: RequirementRegistry):
    """Register all builtin requirement types."""
    registry.register(OSRequirement)
    registry.register(DateRangeRequirement)
    registry.register(ContextObjectRequirement)
