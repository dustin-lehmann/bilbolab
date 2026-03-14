import abc
import dataclasses
from dataclasses import dataclass, field
from typing import Any, ClassVar

from core.utils.logging_utils import Logger

from core.utils.experiments.types import ActionParameterDef, MISSING


# === Definition ===

@dataclass
class GuardDefinition:
    """Declarative description of a guard in an experiment."""
    id: str = ''
    type: str = ''
    params: dict[str, Any] = field(default_factory=dict)


# === Context ===

class GuardContext:
    """Lightweight context passed to guard setup/teardown.

    Provides access to context objects (robot, testbed, etc.) and the
    experiment definition.
    """

    def __init__(self, context_objects: dict, definition=None):
        self.context_objects = context_objects
        self.definition = definition

    def get_object(self, name: str) -> Any:
        """Get a context object by name."""
        return self.context_objects.get(name)


# === GuardBase ===

@dataclass
class GuardBase(abc.ABC):
    """Abstract base class for all experiment guards.

    Guards are paired setup/teardown hooks. Setup runs before actions,
    teardown runs in _finish() (the single exit point), guaranteeing cleanup
    regardless of how the experiment ends.

    Follows the same pattern as RequirementBase: subclasses define a type_id,
    an inner Params dataclass (auto-generates parameter_defs via
    __init_subclass__), and implement setup() and teardown().
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
        self.logger = Logger(f'Guard[{self.type_id}:{self.id}]')

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

    # --- Abstract methods ---

    @abc.abstractmethod
    def setup(self, context: GuardContext):
        """Run guard setup before experiment actions start.

        Args:
            context: Provides access to context objects and experiment definition.
        """
        ...

    @abc.abstractmethod
    def teardown(self, context: GuardContext):
        """Run guard teardown when the experiment finishes (always called).

        Args:
            context: Provides access to context objects and experiment definition.
        """
        ...

    @classmethod
    def from_params(cls, guard_id: str, params: dict[str, Any]) -> 'GuardBase':
        """Create a guard instance from parsed parameters."""
        return cls(id=guard_id, raw_params=params)


# === GuardRegistry ===

class GuardRegistry:
    """Registry of guard types. Maps type_id strings to GuardBase subclasses."""

    def __init__(self):
        self._types: dict[str, type[GuardBase]] = {}
        self.logger = Logger('GuardRegistry')

    def register(self, guard_class: type[GuardBase]):
        """Register a guard class by its type_id."""
        type_id = guard_class.type_id
        if not type_id:
            raise ValueError(f"Guard class {guard_class.__name__} has no type_id")
        if type_id in self._types:
            self.logger.warning(f"Overwriting guard type '{type_id}'")
        self._types[type_id] = guard_class

    def create_guard(self, guard_id: str, type_id: str, params: dict[str, Any] = None) -> GuardBase:
        """Create a guard instance from a type_id and parameters."""
        cls = self._types.get(type_id)
        if cls is None:
            raise ValueError(f"Unknown guard type: '{type_id}'")
        return cls.from_params(guard_id, params or {})

    def has_type(self, type_id: str) -> bool:
        return type_id in self._types

    def get_type(self, type_id: str) -> type[GuardBase] | None:
        return self._types.get(type_id)

    def list_types(self) -> list[str]:
        return list(self._types.keys())


# === Builtin Guards ===

def register_builtin_guards(registry: GuardRegistry):
    """Register all builtin guard types. Currently empty — no generic builtins needed."""
    pass
