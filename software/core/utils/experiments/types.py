from __future__ import annotations

import enum
import dataclasses
from dataclasses import dataclass, field
from typing import Any, Callable


# === Sentinels ===

class _MissingSentinel:
    """Sentinel to distinguish 'not set' from None."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return 'MISSING'

    def __bool__(self):
        return False


MISSING = _MissingSentinel()


# === Status Enums ===

class ActionStatus(enum.StrEnum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    ERROR = 'error'
    TIMEOUT = 'timeout'
    SKIPPED = 'skipped'


class ActionResult(enum.StrEnum):
    COMPLETED = 'completed'
    ASYNC = 'async'
    ERROR = 'error'


class ExperimentStatus(enum.StrEnum):
    RUNNING = 'running'
    FINISHED = 'finished'
    ERROR = 'error'
    TIMEOUT = 'timeout'
    ABORTED = 'aborted'


class TriggerType(enum.StrEnum):
    TRANSITION = 'transition'
    TICK = 'tick'
    TIME = 'time'
    EVENT = 'event'
    PERIODIC = 'periodic'
    IMMEDIATE = 'immediate'


# === Dataclasses ===

@dataclass
class ActionTrigger:
    type: TriggerType
    tick: int | None = None
    time: float | None = None
    event: str | None = None
    event_predicate: Callable | None = None
    period: float | None = None
    period_unit: str = 'seconds'


@dataclass
class Transition:
    source_id: str
    source_port: str
    target_id: str
    mapping: dict[str, Any] | None = None  # target_param -> value/expression


@dataclass
class ActionDataDef:
    id: str
    type: type | None = None
    description: str = ''


@dataclass
class ActionParameterDef:
    id: str
    type: type | None = None
    default: Any = MISSING
    required: bool = False
    description: str = ''
    options: list | None = None


@dataclass
class ExperimentActionData:
    """Data collected during execution of a single action."""
    action_type: str = ''
    status: ActionStatus = ActionStatus.PENDING
    start_tick: int = 0
    end_tick: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    error_message: str = ''
    label: str = ''
    meta: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    sub_actions: dict[str, 'ExperimentActionData'] = field(default_factory=dict)


