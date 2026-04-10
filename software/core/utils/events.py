from __future__ import annotations

import enum
import queue
import threading
from copy import deepcopy
import time
from dataclasses import is_dataclass, dataclass
from functools import partial
from typing import Callable, Any, Optional, Union, Literal, TypeAlias, Iterator
from collections import deque
import weakref
import fnmatch

# === CUSTOM MODULES ===================================================================================================
from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.dataclass_utils import deepcopy_dataclass
from core.utils.dict_utils import optimized_deepcopy
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.signature import check_signature
from core.utils.singleton import _SingletonMeta
from core.utils.time import setTimeout, setInterval
from core.utils.uuid_utils import generate_uuid

# === GLOBAL VARIABLES =================================================================================================
LOG_LEVEL = 'INFO'

logger = Logger('events')


class _TimeoutSentinel:
    __slots__ = ()

    def __repr__(self) -> str: return "TIMEOUT"


TIMEOUT: _TimeoutSentinel = _TimeoutSentinel()


# === HELPERS ==========================================================================================================
def _check_id(id: str):
    # Check that the id does not contain any special characters except for "_"
    if not isinstance(id, str):
        raise TypeError("Event ID must be a string")
    if not id:
        raise ValueError("Event ID cannot be empty")
    if not all(c.isalnum() or c == '_' for c in id):
        raise ValueError("Event ID can only contain alphanumeric characters and underscores")
    return True


# === EVENT FLAG =======================================================================================================
class EventFlag:
    id: str
    types: tuple[type, ...]  # always a tuple at runtime

    # === INIT =========================================================================================================
    def __init__(self, id: str, data_type: type | tuple[type, ...]):
        self.id = id
        if isinstance(data_type, tuple):
            if not data_type or not all(isinstance(t, type) for t in data_type):
                raise TypeError("data_type tuple must be non-empty and contain only types.")
            self.types = data_type
        elif isinstance(data_type, type):
            self.types = (data_type,)
        else:
            raise TypeError("data_type must be a type or tuple[type, ...]")

    # ------------------------------------------------------------------------------------------------------------------
    def accepts(self, value: Any) -> bool:
        return isinstance(value, self.types)

    # ------------------------------------------------------------------------------------------------------------------
    def describe(self) -> str:
        return " | ".join(t.__name__ for t in self.types)


# === PREDICATE ========================================================================================================
Predicate = Callable[[dict[str, Any], Any], bool]  # (flags, data) -> bool


def pred_flag_in(key, values) -> Predicate:
    return lambda f, d: f.get(key) in values


def pred_data_in(key, values) -> Predicate:
    return lambda f, d: isinstance(d, dict) and d.get(key) in values


def pred_data_dict_key_equals(key, expected) -> Predicate:
    return lambda f, d: d.get(key) == expected


def pred_data_equals(expected) -> Predicate:
    return lambda f, d: d == expected


def pred_flag_equals(key, expected) -> Predicate:
    return lambda f, d: f.get(key) == expected


def pred_flag_contains(flag_key: str, match_value: Any) -> Predicate:
    """
    Returns a predicate that checks if `match_value` is present in the
    flag list (or equals the single flag value) for `flag_key`.

    Works whether the flag value is a list/tuple/set or a single value.
    """

    def _pred(flags, data):
        if flag_key not in flags:
            return False
        val = flags[flag_key]
        if isinstance(val, (list, tuple, set)):
            return match_value in val
        return val == match_value

    return _pred


# === EVENT ============================================================================================================
@callback_definition
class EventCallbacks:
    set: CallbackContainer


class Event:
    id: str

    data_type: type | None
    flags: dict[str, EventFlag]
    copy_data_on_set = True
    data_is_static_dict: bool
    custom_data_copy_function = None
    max_history_time: float = 10.0  # Seconds

    parent: EventContainer | None = None
    data: Any
    callbacks: EventCallbacks
    history: deque[tuple[float, dict[str, Any], Any]]
    dict_copy_cache = None

    # === INIT =========================================================================================================
    def __init__(self,
                 id: str = None,
                 data_type: type | None = None,
                 flags: EventFlag | list[EventFlag] = None,
                 copy_data_on_set: bool = True,
                 data_is_static_dict: bool = False, ):

        if id is None:
            id = generate_uuid()

        _check_id(id)

        self.id = id

        if flags is None:
            flags = []

        if not isinstance(flags, list):
            flags = [flags]

        self.flags = {}

        for flag in flags:
            if flag.id in self.flags:
                raise Exception(f"Flag {flag.id} already exists in {self.flags}")
            self.flags[flag.id] = flag

        self.callbacks = EventCallbacks()
        self.data = None

        self.data_type = data_type
        self.copy_data_on_set = copy_data_on_set
        self.data_is_static_dict = data_is_static_dict

        self.history: deque[tuple[float, dict[str, Any], Any]] = deque()
        self._history_lock = threading.Lock()

        active_event_loop.add_event(self)

    # === PROPERTIES ===================================================================================================
    @property
    def uid(self) -> str:
        if self.parent is None:
            return self.id
        else:
            if hasattr(self.parent, 'id') and self.parent.id is not None:
                return f"{self.parent.id}:{self.id}"
            else:
                return self.id

    # === METHODS ======================================================================================================
    def on(self,
           callback: Callback | Callable,
           predicate: Predicate = None,
           once: bool = False,
           stale_event_time=None,
           discard_data: bool = False,
           discard_match_data: bool = True,
           timeout=None,
           spawn_new_threads=True,
           max_rate=None) -> SubscriberListener:
        """
        Always return a SubscriberListener as the handle.
        If once=True, the underlying Subscriber is once=True and the listener will
        auto-stop after the first delivery.
        """
        sub = Subscriber(
            id=f"{self.uid}_subscriber",
            events=(self, predicate) if predicate else self,
            once=once,
            stale_event_time=stale_event_time,
        )

        listener = SubscriberListener(
            subscriber=sub,
            callback=callback,
            max_rate=max_rate,
            spawn_new_threads=spawn_new_threads,
            auto_stop_on_first=once,  # NEW: stop listener after first emit when once=True
            timeout=timeout,
            discard_data=discard_data,
            discard_match_data=discard_match_data,
        )
        listener.start()
        return listener

    # ------------------------------------------------------------------------------------------------------------------
    def wait(self, predicate: Predicate = None, timeout: float = None,
             stale_event_time: float = None) -> tuple[Any | _TimeoutSentinel, SubscriberMatch | None]:
        subscriber = Subscriber(
            events=(self, predicate) if predicate is not None else self,
            timeout=timeout,
            stale_event_time=stale_event_time,
            once=True,
        )
        return subscriber.wait(timeout=timeout, stale_event_time=stale_event_time)

    # ------------------------------------------------------------------------------------------------------------------
    def set(self, data=None, flags: dict = None) -> None:

        # Check if the flags are valid
        assert (isinstance(flags, dict) or flags is None)
        flags = flags or {}

        # Check if all flags are valid
        for flag in flags:
            if flag not in self.flags:
                raise ValueError(f"Invalid flag: {flag}")

            ef = self.flags[flag]
            value = flags[flag]

            if not ef.accepts(value):
                raise TypeError(
                    f"Flag '{flag}' is expected to be of type {ef.describe()}, "
                    f"but got {type(value).__name__} instead."
                )

        # Check if the data is valid
        if data is not None:
            if self.data_type is not None:
                if not isinstance(data, self.data_type):
                    raise TypeError(
                        f"Data is expected to be of type {self.data_type.__name__}, "
                        f"but got {type(data).__name__} instead."
                    )

        # Make a copy of the data
        if self.copy_data_on_set:
            payload = self._copy_payload(data)
        else:
            payload = data

        self.data = payload

        now = time.monotonic()
        flags = dict(flags)
        with self._history_lock:
            self.history.append((now, flags, payload))
            self._prune_history(now)

        self.callbacks.set.call(data=payload, flags=flags)

    # ------------------------------------------------------------------------------------------------------------------
    def get_data(self, copy: bool = True) -> Any:
        if copy:
            return self._copy_payload(self.data)
        else:
            return self.data

    # ------------------------------------------------------------------------------------------------------------------
    def has_match_in_window(self, predicate: Predicate | None, window: float, now: float | None = None) -> bool:
        if window is None or window <= 0:
            return False
        if now is None:
            now = time.monotonic()
        cutoff = now - window
        with self._history_lock:
            self._prune_history(now)
            for ts, flags, data in reversed(self.history):
                if ts < cutoff:
                    break
                if predicate is None or predicate(flags, data):
                    return True
        return False

    # ------------------------------------------------------------------------------------------------------------------
    def first_match_in_window(self, predicate: Predicate | None, window: float, now: float | None = None):
        if window is None or window <= 0:
            return None
        if now is None:
            now = time.monotonic()
        cutoff = now - window
        with self._history_lock:
            self._prune_history(now)
            for ts, flags, data in reversed(self.history):
                if ts < cutoff:
                    break
                if predicate is None or predicate(flags, data):
                    return flags, data
        return None

    # === PRIVATE METHODS ==============================================================================================
    def _prune_history(self, now: float | None = None) -> None:
        if now is None:
            now = time.monotonic()
        cutoff = now - self.max_history_time
        dq = self.history
        while dq and dq[0][0] < cutoff:
            dq.popleft()

    # ------------------------------------------------------------------------------------------------------------------`
    def _copy_payload(self, data) -> Any:
        try:
            if self.data_is_static_dict and self.data_type is dict:
                payload, self.dict_copy_cache = optimized_deepcopy(data, self.dict_copy_cache)
            elif is_dataclass(self.data_type):
                payload = deepcopy_dataclass(data)
            else:
                payload = deepcopy(data)
        except Exception as e:
            payload = data
            self.copy_data_on_set = False
            logger.warning(f"Could not copy data for event {self}: {e}. Subsequent set() calls will not copy.")

        return payload

    # ------------------------------------------------------------------------------------------------------------------`
    def __repr__(self):
        return f"<Event {self.uid}>"


# === SUBSCRIBER =======================================================================================================
@dataclass
class _EventPayload:
    # event_id: str | None = None
    data: Any | None = None
    trace_data: Any | None = None
    flags: dict[str, Any] | None = None


@dataclass
class SubscriberMatch:
    time: float
    match: Event | Subscriber | list[Event | Subscriber]
    match_id: str | list[str]
    # Pass-through from children / original payloads
    trace_data: Any | dict[Event | Subscriber, Any]
    data: Any | dict[str, Any]
    flags: Any | dict[str, Any]

    def __repr__(self):
        return f"SubscriberMatch(time={self.time:.3f}, match={self.match!r})"

    def _resolve_node_payload(self, node) -> tuple[Optional[dict], Optional[Any], Optional[Any]]:
        """
        Return (flags_for_node, data_for_node, trace_for_node) for the given node
        from *this* match's shapes, tolerating all combinations your _fire() produces:
          - self.flags/data may be scalars or dicts keyed by node (Event or Subscriber)
          - self.trace_data may be:
              * dict keyed by child node, or
              * a SubscriberMatch directly (single-child case)
              * None (for Event leaves)
        """
        flags = None
        data = None
        trace = None

        # flags/data may be dicts keyed by the exact node object (Event or Subscriber)
        if isinstance(self.flags, dict):
            flags = self.flags.get(node)
        else:
            flags = self.flags

        if isinstance(self.data, dict):
            data = self.data.get(node)
        else:
            data = self.data

        # trace_data logic:
        if isinstance(self.trace_data, dict):
            trace = self.trace_data.get(node)
        else:
            # single-child Subscriber case: parent.trace_data is directly the child's SubscriberMatch
            if isinstance(node, Subscriber) and isinstance(self.trace_data, SubscriberMatch):
                trace = self.trace_data
            else:
                trace = self.trace_data  # usually None for Event leaves

        return flags, data, trace

    def _iter_leaf_causes(self) -> Iterator[tuple[Event, Optional[dict], Any]]:
        """
        Yield (event, flags, data) for leaf Event(s) that ultimately satisfied this match.
        """
        # Normalize to a list of nodes
        nodes = self.match if isinstance(self.match, list) else [self.match]

        for node in nodes:
            if isinstance(node, Event):
                node_flags, node_data, _ = self._resolve_node_payload(node)
                # Only yield if we actually have a payload (defensive; still allow None data)
                yield (node, node_flags, node_data)
                continue

            if isinstance(node, Subscriber):
                _, _, child_trace = self._resolve_node_payload(node)

                if isinstance(child_trace, SubscriberMatch):
                    # Recurse into the child's match
                    yield from child_trace._iter_leaf_causes()
                else:
                    # Defensive: try to fall back to the node’s own data/flags if trace missing
                    node_flags, node_data, _ = self._resolve_node_payload(node)
                    # If the child subscriber bubbled up raw leaf data, it will look like that here.
                    if isinstance(node_data, dict):
                        # try to find Event-keys with data
                        for k, v in node_data.items():
                            if isinstance(k, Event):
                                # flags may also be dict keyed by the same event
                                ev_flags = None
                                if isinstance(self.flags, dict):
                                    ev_flags = self.flags.get(k)
                                yield (k, ev_flags, v)
                    # Otherwise we have nothing else to descend into (no yield)

    def causal_events(self) -> list[tuple[Event, Optional[dict], Any]]:
        return list(self._iter_leaf_causes())

    def first_cause(self) -> Optional[tuple[Event, Optional[dict], Any]]:
        for item in self._iter_leaf_causes():
            return item
        return None

    def cause_ids(self) -> list[str]:
        return [ev.uid for (ev, _, _) in self._iter_leaf_causes()]

    def caused_by(self, what: str | Event | Callable[[Event], bool]) -> bool:
        for ev, _, _ in self._iter_leaf_causes():
            if isinstance(what, str):
                if fnmatch.fnmatchcase(ev.uid, what):
                    return True
            elif callable(what):
                try:
                    if bool(what(ev)):
                        return True
                except Exception:
                    pass
            elif isinstance(what, Event):
                if ev is what:
                    return True
        return False

    # --- inside SubscriberMatch ---

    def _iter_nodes(self):
        """
        Yield all nodes (Event or Subscriber) that lie on the satisfied path(s)
        of this match, recursively.
        """
        nodes = self.match if isinstance(self.match, list) else [self.match]
        for node in nodes:
            yield node
            # For a Subscriber node, descend into its child match if we have it
            child = None
            if isinstance(self.trace_data, dict):
                child = self.trace_data.get(node)
            elif isinstance(self.trace_data, SubscriberMatch) and isinstance(node, Subscriber):
                child = self.trace_data  # single-child case
            if isinstance(child, SubscriberMatch):
                yield from child._iter_nodes()

    def contains_node(self, node: Event | Subscriber) -> bool:
        """True if the given Event/Subscriber is present anywhere in the satisfied path."""
        return any(n is node for n in self._iter_nodes())

    def caused_by_group(self, group: Subscriber) -> bool:
        """
        True if this match involved `group` (useful for 'did the AND side win?').
        Works whether `group` is the root, a child in an OR branch, or nested deeper.
        """
        return self.contains_node(group)

    def group_match(self, group: Subscriber) -> "SubscriberMatch | None":
        """
        Return the nested SubscriberMatch that corresponds to `group`, if present.
        This is the object you'd inspect for the group's internal data/flags/trace.
        """
        # If THIS match is the group's own match
        if self.match is group or (isinstance(self.match, list) and group in self.match):
            # For a Subscriber node, its child match is stored in trace_data
            if isinstance(self.trace_data, dict):
                cm = self.trace_data.get(group)
                return cm if isinstance(cm, SubscriberMatch) else None
            if isinstance(self.trace_data, SubscriberMatch):
                # single-child case where parent == group
                return self.trace_data
            return None

        # Otherwise search recursively in children
        if isinstance(self.trace_data, dict):
            for child in self.trace_data.values():
                if isinstance(child, SubscriberMatch):
                    found = child.group_match(group)
                    if found is not None:
                        return found
        elif isinstance(self.trace_data, SubscriberMatch):
            return self.trace_data.group_match(group)
        return None

    def group_causal_events(self, group: Subscriber):
        """
        Return leaf (event, flags, data) that belong to `group` specifically.
        """
        gm = self.group_match(group)
        if gm is None:
            return []
        # Reuse your existing leaf helper on the group's own match
        return gm.causal_events() if hasattr(gm, "causal_events") else []


class SubscriberType(enum.StrEnum):
    AND = "AND"
    OR = "OR"


# Type definition for event specifications
EventSpec: TypeAlias = Union[
    str,  # Event ID
    Event,  # Single event
    tuple[str, Predicate],
    tuple[Event, Predicate],  # Event with predicate
    'Subscriber',  # Nested subscriber
    list[Union[  # List of any combination
        str,
        Event,
        tuple[Event, Predicate],
        tuple[str, Predicate],
        'Subscriber'
    ]]
]


@callback_definition
class SubscriberCallbacks:
    finished: CallbackContainer = CallbackContainer(inputs=['data', ('match', SubscriberMatch)])
    timeout: CallbackContainer


@dataclass
class _SubscriberEventContainer:
    event: Event | Subscriber
    predicate: Predicate | None = None
    finished: bool = False
    payload: _EventPayload | None = None

    def __post_init__(self):
        if self.payload is None:
            self.payload = _EventPayload()

    def reset(self):
        self.finished = False
        self.payload = _EventPayload()


class Subscriber:
    id: str

    events: list[_SubscriberEventContainer]

    timeout: float | None
    stale_event_time: float | None
    once: bool
    type: SubscriberType

    matches: list[SubscriberMatch]  # Previous matches (recent, pruned)

    attach_time: float | None = None

    _save_matches: bool
    _match_save_time: float
    _abort: bool

    # fan-out support
    _wait_queues: set[queue.Queue]
    _wait_queue_maxsize: int
    _wq_lock: threading.RLock

    _event_loop: EventLoop | None = None
    _SENTINEL = object()

    def __init__(self,
                 events: EventSpec,
                 id: str | None = None,
                 type: SubscriberType | None = SubscriberType.AND,
                 timeout: float | None = None,
                 stale_event_time: float | None = None,

                 once: bool = False,
                 callback: Callable | Callback | None = None,
                 execute_callback_in_thread: bool = True,

                 save_matches: bool = True,
                 match_save_time: float | None = 10,
                 queue_maxsize: int = 1,
                 event_loop: EventLoop | None = None):

        if id is None:
            id = generate_uuid(prefix="subscriber_")

        self.id = id

        self.callbacks = SubscriberCallbacks()

        if not isinstance(events, list):
            events = [events]

        self.events = []
        self.predicates = []

        for eventspec in events:
            if isinstance(eventspec, str):
                pattern_subscriber = PatternSubscriber(id=eventspec, pattern=eventspec)
                # self.events.append(pattern_subscriber)
                # self.predicates.append(None)
                self.events.append(_SubscriberEventContainer(event=pattern_subscriber, predicate=None))

                pattern_subscriber.callbacks.finished.register(self._child_subscriber_callback,
                                                               inputs={'subscriber': pattern_subscriber})
            elif isinstance(eventspec, tuple) and len(eventspec) == 2 and isinstance(eventspec[0], str) and callable(
                    eventspec[1]):
                pattern: str = eventspec[0]  # type: ignore
                predicate: Callable = eventspec[1]
                pattern_subscriber = PatternSubscriber(pattern=pattern,
                                                       predicate=predicate,
                                                       stale_event_time=stale_event_time)
                self.events.append(_SubscriberEventContainer(event=pattern_subscriber, predicate=None))
                pattern_subscriber.callbacks.finished.register(self._child_subscriber_callback,
                                                               inputs={'subscriber': pattern_subscriber})
            elif isinstance(eventspec, Event):
                self.events.append(_SubscriberEventContainer(event=eventspec, predicate=None))
            elif isinstance(eventspec, tuple) and len(eventspec) == 2 and isinstance(eventspec[0], Event) and callable(
                    eventspec[1]):
                ev, pr = eventspec
                self.events.append(_SubscriberEventContainer(event=ev, predicate=pr))
            elif isinstance(eventspec, Subscriber):
                self.events.append(_SubscriberEventContainer(event=eventspec, predicate=None))
                eventspec.callbacks.finished.register(self._child_subscriber_callback,
                                                      inputs={'subscriber': eventspec})

        self.timeout = timeout
        self.stale_event_time = stale_event_time
        self.type = type
        self.once = once

        self.logger = Logger(f"Subscriber ({[event.event.uid for event in self.events]})", LOG_LEVEL)

        self._abort = False
        self._wait_queues = set()
        self._wait_queue_maxsize = max(0, queue_maxsize)
        self._wq_lock = threading.RLock()

        if event_loop is None:
            event_loop = active_event_loop
        self._event_loop = event_loop

        if callback is not None:
            self.callbacks.finished.register(callback)

        self._save_matches = save_matches
        self._match_save_time = match_save_time
        self.execute_callback_in_thread = execute_callback_in_thread
        self.matches = []

        self.logger.debug("Add to event loop")

        self._event_loop.add_subscriber(self)
        self._check_child_subscribers()

    # === PROPERTIES ===================================================================================================
    @property
    def uid(self):
        return self.id

    # === METHODS ======================================================================================================
    def wait(self,
             timeout: float | None = None,
             stale_event_time: float | None = None) -> tuple[Any | _TimeoutSentinel, SubscriberMatch | None]:
        """
        Block until a new match arrives (fan-out via per-waiter queue).
        If a recent match exists within the provided or configured stale window,
        return it immediately without blocking.

        Returns:
            SubscriberMatch if available, else None on timeout/stop.
        """
        self.logger.debug("Wait")
        if timeout is None:
            timeout = self.timeout

        # 1) Fast path: return a recent match within the stale window (if requested)
        window = stale_event_time if stale_event_time is not None else self.stale_event_time
        if window and window > 0:
            now = time.monotonic()
            cutoff = now - window
            # Read-mostly; fine to snapshot without a separate lock
            recent = None
            for m in reversed(self.matches):
                if m.time >= cutoff:
                    recent = m
                    break
                # matches are time-ordered; we can break once older than cutoff
                # but only if we know they are sorted; they are appended in _fire() -> yes
            if recent is not None:
                return recent.data, recent

        # 2) Slow path: set up a one-off queue and block until push or timeout
        q = queue.Queue(maxsize=self._wait_queue_maxsize)
        with self._wq_lock:
            # if stop() already called, don't register / return None
            if self._abort:
                return None, None
            self._wait_queues.add(q)

        try:
            try:
                match = q.get(timeout=timeout) if timeout is not None else q.get()
            except queue.Empty:
                self.callbacks.timeout.call()
                return TIMEOUT, None

            if match is self._SENTINEL:
                return TIMEOUT, None
            return match
        finally:
            with self._wq_lock:
                self._wait_queues.discard(q)

    # ------------------------------------------------------------------------------------------------------------------
    def on(self,
           callback: Callback | Callable,
           once: bool = False,
           timeout=None,
           max_rate=None,
           discard_match_data: bool = True,
           **kwargs) -> SubscriberListener:
        """
        Always return a SubscriberListener as the handle.
        If once=True, the underlying Subscriber is once=True and the listener will
        auto-stop after the first delivery.
        """

        callback = Callback(function=callback, **kwargs)

        listener = SubscriberListener(
            subscriber=self,
            callback=callback,
            max_rate=max_rate,
            spawn_new_threads=False,  # mimic old default; flip if you want
            auto_stop_on_first=once,  # NEW: stop listener after first emit when once=True
            discard_match_data=discard_match_data,
            timeout=timeout,
        )
        listener.start()
        return listener

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        """Abort future waiting, deregister from loop, and wake any blocking wait()."""
        self._abort = True
        self._unsubscribe()
        # Broadcast sentinel to all registered wait queues
        with self._wq_lock:
            for q in list(self._wait_queues):
                self._nonblocking_push(q, self._SENTINEL)

    # === PRIVATE METHODS ==============================================================================================
    def set_match(self, event: Event | Subscriber, flags: dict[str, Any] | None, data: Any):

        container = self._get_event_container_by_event(event)

        if container is None:
            raise ValueError(f"Event {event} is not known.")

        event_uid = event.uid

        if isinstance(event, Subscriber):
            event_data = data.data
            trace_data = data
        else:
            event_data = data
            trace_data = None

        container.finished = True
        container.payload = _EventPayload(data=event_data, trace_data=trace_data, flags=flags)

        self.logger.debug(f"Match: {event_uid}, flags: {flags}, data: {data}")

        if self._is_satisfied():
            self._fire()

    # ------------------------------------------------------------------------------------------------------------------
    def _fire(self):

        self.logger.debug("Subscriber satisfied. Gathering data and flags.")

        # Gather matched data/flags
        if len(self.events) == 1:
            matched_event = self.events[0].event
            match_id = self.events[0].event.uid
            data = self.events[0].payload.data
            trace_data = self.events[0].payload.trace_data
            flags = self.events[0].payload.flags
        else:
            if self.type == SubscriberType.AND:
                matched_event = [event.event for event in self.events]
                match_id = [event.event.uid for event in self.events]
                data = {container.event: container.payload.data for container in self.events}
            else:
                matched_event = next((event.event for event in self.events if event.finished))
                match_id = next((event.event.uid for event in self.events if event.finished))
                data = next((container.payload.data for container in self.events if container.finished), None)

            trace_data = {container.event: container.payload.trace_data for container in self.events}
            flags = {container.event: container.payload.flags for container in self.events}

        match = SubscriberMatch(
            time=time.monotonic(),
            match=matched_event,
            match_id=match_id,
            data=data,
            trace_data=trace_data,
            flags=flags
        )
        self.logger.debug(f"Match: {matched_event}. Data: {match}")

        # Once semantics: prevent future matches and unsubscribe from loop
        if self.once:
            self._abort = True
            self._unsubscribe()

        # Save for stale-window replay and prune old ones
        if self._save_matches:
            self.matches.append(match)
            self._prune_matches()

        # Reset state for continuous subscribers
        if not self.once:
            for container in self.events:
                container.reset()

        # Broadcast to all current waiters (non-blocking, drop-oldest)
        with self._wq_lock:
            for q in list(self._wait_queues):
                self._nonblocking_push(q, (data, match))

        self.logger.debug("Subscriber satisfied. Fire callback(s)")
        self._execute_callback(data,
                               match,
                               execute_callback_in_thread=self.execute_callback_in_thread,
                               input_match_data=True)

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _nonblocking_push(q: queue.Queue, item):
        try:
            q.put_nowait(item)
        except queue.Full:
            # drop oldest item to make room
            try:
                _ = q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(item)
            except queue.Full:
                # still full -> give up; likely abandoned waiter
                pass

    # ------------------------------------------------------------------------------------------------------------------
    def _execute_callback(self, data, match_data, input_match_data: bool = True,
                          execute_callback_in_thread: bool = True):
        for callback in self.callbacks.finished.callbacks:
            if execute_callback_in_thread:
                if input_match_data:
                    threading.Thread(target=callback,
                                     kwargs={'data': data, 'match': match_data},
                                     daemon=True).start()
                else:
                    threading.Thread(target=callback, args=(), daemon=True).start()
            else:
                if input_match_data:
                    callback(data, match_data)
                else:
                    callback()

    # ------------------------------------------------------------------------------------------------------------------
    def _unsubscribe(self):
        if self._event_loop is not None:
            self._event_loop.remove_subscriber(self)

    # ------------------------------------------------------------------------------------------------------------------
    def _child_subscriber_callback(self, data, match, subscriber: Subscriber = None):
        self.logger.debug(f"Child subscriber callback. Child: {subscriber.__repr__()}")
        self.set_match(subscriber, None, match)

    # ------------------------------------------------------------------------------------------------------------------
    def _prune_matches(self):
        """Remove matches older than match_save_time from the current time"""
        if not self._match_save_time:
            return

        now = time.monotonic()
        cutoff = now - self._match_save_time
        # matches are appended in chronological order; prune from the front
        self.matches = [match for match in self.matches if match.time >= cutoff]

    # ------------------------------------------------------------------------------------------------------------------
    def _check_child_subscribers(self):
        if not self.stale_event_time:
            return

        child_subscribers = [c.event for c in self.events if isinstance(c.event, Subscriber)]
        now = time.monotonic()
        cutoff = now - self.stale_event_time

        for child_subscriber in child_subscribers:
            recent_matches = [m for m in child_subscriber.matches if m.time >= cutoff]
            if recent_matches:
                latest_match = max(recent_matches, key=lambda m: m.time)
                self.set_match(child_subscriber, latest_match.flags, latest_match)

    # ------------------------------------------------------------------------------------------------------------------
    def _get_event_container_by_event(self, event: Event | Subscriber) -> _SubscriberEventContainer | None:
        for container in self.events:
            if container.event == event:
                return container
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _is_satisfied(self):
        if self.type == SubscriberType.AND:
            return all(container.finished for container in self.events)
        else:
            return any(container.finished for container in self.events)

    # ------------------------------------------------------------------------------------------------------------------
    def __repr__(self):
        return f"<Subscriber {self.id} {[event.__repr__() for event in self.events]}>"


# === Pattern Subscriber ===============================================================================================
class PatternSubscriber(Subscriber):
    pattern: str
    global_predicate: Predicate | None = None

    def __init__(self, pattern: str, *, predicate: Predicate | None | Callable = None,
                 id: str | None = None, **kwargs):
        if 'type' in kwargs and kwargs['type'] != SubscriberType.OR:
            raise ValueError("PatternSubscriber always uses OR semantics.")
        kwargs['type'] = SubscriberType.OR
        if id is None:
            id = f"pattern:{pattern}"

        self.pattern = pattern
        self.global_predicate = predicate
        super().__init__(events=[], id=id, **kwargs)

    def add_event(self, event: Event):
        # already attached?
        if any(c.event is event for c in self.events):
            return

        self.logger.debug(f"Add event: {event.uid} to pattern {self.pattern}")
        self.events.append(_SubscriberEventContainer(event=event, predicate=self.global_predicate))

        # ensure event -> subscriber dispatch
        active_event_loop.register_pattern_binding(self, event)

        # stale-window replay
        if self.stale_event_time and self.stale_event_time > 0:
            now = time.monotonic()
            if getattr(event, "max_history_time", 0) < self.stale_event_time:
                event.max_history_time = self.stale_event_time
            match = event.first_match_in_window(self.global_predicate, self.stale_event_time, now=now)
            if match is not None:
                flags, data = match
                self.set_match(event, flags, data)

    def remove_event(self, event: Event):
        idx = next((i for i, c in enumerate(self.events) if c.event is event), None)
        if idx is None:
            return
        self.events.pop(idx)

        loop = active_event_loop
        subs = loop.subscribers_by_event.get(event)
        if subs:
            subs.discard(self)
            if not subs:
                loop.subscribers_by_event.pop(event, None)

    def __repr__(self):
        return f"<PatternSubscriber {self.id} pattern={self.pattern} events={[c.event.uid for c in self.events]}>"


# === SUBSCRIBER LISTENER ==============================================================================================
@callback_definition
class SubscriberListenerCallbacks:
    timeout: CallbackContainer


class SubscriberListener:
    _max_rate: float | None
    _spawn_new_threads: bool
    _timeout: float | None
    _exit: bool = False
    _thread: threading.Thread | None = None

    _auto_stop_on_first: bool = False

    _last_callback_time: float | None = None

    _stop_event: Event

    _discard_match_data: bool
    _discard_data: bool

    def __init__(self,
                 subscriber: Subscriber,
                 callback: Callable | Callback,
                 max_rate: float | None = None,
                 spawn_new_threads: bool = False,
                 auto_stop_on_first: bool = False,
                 timeout: float | None = None,
                 discard_data: bool = False,
                 discard_match_data: bool = True):

        # Check if the callback does accept the correct arguments
        # check_signature(callback, kwarg_names=["data", "match"])
        self.SENTINEL = object()
        self.callbacks = SubscriberListenerCallbacks()
        self.subscriber = subscriber
        self.callback = callback

        if max_rate is not None and max_rate <= 0:
            raise ValueError("max_rate must be > 0")
        self._max_rate = max_rate
        self._spawn_new_threads = spawn_new_threads
        self._auto_stop_on_first = auto_stop_on_first
        self._discard_match_data = discard_match_data
        self._discard_data = discard_data
        self._timeout = timeout

        self.logger = Logger(f"Subscriber {self.subscriber.id} listener", "DEBUG")

        self.queue = queue.Queue()

        register_exit_callback(self.stop)

    # === METHODS ======================================================================================================
    def start(self):
        self.subscriber.callbacks.finished.register(self._subscriber_callback)
        self._thread = threading.Thread(target=self._task, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self, *args, **kwargs):
        """Public stop: signal + join if called from another thread."""
        self._request_stop()
        # Only join if we're NOT on the worker thread
        if self._thread is not None and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join()

    # === PRIVATE METHODS ==============================================================================================
    def _task(self):
        while not self._exit:
            try:
                if self._timeout is not None:
                    data, trace = self.queue.get(timeout=self._timeout)
                else:
                    data, trace = self.queue.get()
            except queue.Empty:
                # listener-level timeout
                self.logger.warning("SubscriberListener wait timeout.")
                self.callbacks.timeout.call()
                self.stop()
                continue

            if self._exit:
                break

            if data is self.SENTINEL:
                break

            if self._max_rate:
                now = time.monotonic()
                min_interval = 1.0 / self._max_rate
                if self._last_callback_time is not None and (now - self._last_callback_time) < min_interval:
                    continue
                self._last_callback_time = now

            self._execute_callback(data, trace, spawn_thread=self._spawn_new_threads)

            if self._auto_stop_on_first:
                self._request_stop()

    # ------------------------------------------------------------------------------------------------------------------
    def _subscriber_callback(self, data: Any, match: SubscriberMatch):
        self.queue.put((data, match))

    # ------------------------------------------------------------------------------------------------------------------
    def _execute_callback(self, data, result, spawn_thread: bool):
        # Build call signature once
        args = [] if self._discard_data else [data]
        kwargs = {} if self._discard_match_data else {"match": result}

        func = partial(self.callback, *args, **kwargs)

        if spawn_thread:
            threading.Thread(target=func, daemon=True).start()
        else:
            func()

    # ------------------------------------------------------------------------------------------------------------------
    def _request_stop(self):
        """Signal the thread to exit, without joining (safe to call from worker)."""
        self._exit = True
        self.queue.put((self.SENTINEL, None))
        self.subscriber.callbacks.finished.remove(self._subscriber_callback)


class _EventExpr:  # not exported
    __slots__ = ("children",)

    def __init__(self, *children): self.children = list(children)


# ----------------------------------------------------------------------------------------------------------------------
class _AndExpr(_EventExpr): pass


# ----------------------------------------------------------------------------------------------------------------------
class _OrExpr(_EventExpr): pass


# ----------------------------------------------------------------------------------------------------------------------
def AND(*ops, stale_event_time: float | None = None,
        event_loop: EventLoop | None = None,
        id: str | None = None) -> Subscriber:
    """
    Factory: returns a Subscriber whose children are compiled from ops with AND semantics.
    Usable anywhere, including as an operand to another Subscriber.
    """
    return _compile_expr_to_subscriber(_AndExpr(*ops), stale_event_time=stale_event_time,
                                       event_loop=event_loop, id=id)


# ----------------------------------------------------------------------------------------------------------------------
def OR(*ops, stale_event_time: float | None = None,
       event_loop: EventLoop | None = None,
       id: str | None = None) -> Subscriber:
    """Factory: returns a Subscriber with OR semantics."""
    return _compile_expr_to_subscriber(_OrExpr(*ops), stale_event_time=stale_event_time,
                                       event_loop=event_loop, id=id)


# ----------------------------------------------------------------------------------------------------------------------
def _compile_operand_to_leaf(op, *, stale_event_time: float | None, once: bool = False):
    """
    Turn a single operand into something Subscriber(events=[...]) accepts.
    Propagates stale window into PatternSubscriber leaves.
    """
    if isinstance(op, Event) or isinstance(op, Subscriber):
        return op
    if isinstance(op, tuple) and len(op) == 2:
        a, b = op
        if isinstance(a, Event) and callable(b):
            return op  # (Event, Predicate)
        if isinstance(a, str) and callable(b):
            return PatternSubscriber(pattern=a, predicate=b, stale_event_time=stale_event_time,
                                     once=once)  # type: ignore
    if isinstance(op, str):
        return PatternSubscriber(pattern=op, stale_event_time=stale_event_time, once=once)
    # Defer expr handling to caller
    return op


# ----------------------------------------------------------------------------------------------------------------------
def _compile_expr_to_subscriber(expr_or_leaf,
                                *,
                                stale_event_time: float | None,
                                once: bool = False,
                                event_loop: EventLoop | None,
                                id: str | None = None) -> Subscriber:
    """
    Recursively build a Subscriber tree from _AndExpr/_OrExpr or a leaf.
    Attaches a private attribute `_compiled_children` listing immediate child Subscribers,
    so we can later stop the whole tree.
    """
    # Leaf: wrap in a 1-child subscriber (type is irrelevant for single child)
    if not isinstance(expr_or_leaf, _EventExpr):
        leaf = _compile_operand_to_leaf(expr_or_leaf, stale_event_time=stale_event_time)
        sub = Subscriber(events=leaf,
                         type=SubscriberType.AND,
                         stale_event_time=stale_event_time,
                         event_loop=event_loop,
                         once=once,
                         id=id)

        sub._compiled_children = []  # for uniformity
        return sub

    # Expr: compile children
    compiled_children = []
    events_list = []
    if hasattr(expr_or_leaf, "children"):
        for ch in expr_or_leaf.children:
            if isinstance(ch, _EventExpr):
                cs = _compile_expr_to_subscriber(ch, stale_event_time=stale_event_time, once=once,
                                                 event_loop=event_loop, id=None)
                compiled_children.append(cs)
                events_list.append(cs)  # a child Subscriber is a valid event
            else:
                leaf = _compile_operand_to_leaf(ch, stale_event_time=stale_event_time, once=once)
                # Only actual Subscribers are children we must manage
                if isinstance(leaf, Subscriber):
                    compiled_children.append(leaf)
                events_list.append(leaf)

    stype = SubscriberType.AND if isinstance(expr_or_leaf, _AndExpr) else SubscriberType.OR
    sub = Subscriber(events=events_list,
                     type=stype,
                     stale_event_time=stale_event_time,
                     event_loop=event_loop,
                     once=once,
                     id=id)
    sub._compiled_children = [c for c in compiled_children if isinstance(c, Subscriber)]
    return sub


# ----------------------------------------------------------------------------------------------------------------------
def _stop_subscriber_tree(root: Subscriber):
    """Stop root and all recursively compiled children (DFS)."""
    seen = set()

    def _dfs(s: Subscriber):
        if s in seen:
            return
        seen.add(s)
        for ch in getattr(s, "_compiled_children", []):
            _dfs(ch)
        try:
            s.stop()
        except Exception:
            pass

    _dfs(root)


# ----------------------------------------------------------------------------------------------------------------------
def wait_for_events(events,
                    *,
                    timeout: float | None = None,
                    stale_event_time: float | None = None,
                    event_loop: EventLoop | None = None) -> tuple[Any | _TimeoutSentinel, SubscriberMatch | None]:
    """
    Compile events into a Subscriber tree, wait once, and stop the entire tree (root + descendants).
    `events` may be:
      - Event / Subscriber / pattern str / (Event, Predicate) / (str, Predicate)
      - OR(…) / AND(…) expressions
    """
    root = _compile_expr_to_subscriber(events,
                                       stale_event_time=stale_event_time,
                                       event_loop=event_loop,
                                       once=True,
                                       id=None)
    # Ensure single-shot behavior at the root
    root.once = True
    try:
        return root.wait(timeout=timeout, stale_event_time=stale_event_time)
    finally:
        # In case of timeout or external cancel, make sure the tree is fully torn down.
        _stop_subscriber_tree(root)


# ----------------------------------------------------------------------------------------------------------------------
def on_events(events,
              callback: Callback | Callable,
              *,
              once: bool = False,
              timeout: float | None = None,
              max_rate: float | None = None,
              stale_event_time: float | None = None,
              discard_match_data: bool = True,
              event_loop: EventLoop | None = None,
              **kwargs) -> SubscriberListener:
    """
    Compile events into a Subscriber tree and register a callback.
    `events` may be:
      - Event / Subscriber / pattern str / (Event, Predicate) / (str, Predicate)
      - OR(…) / AND(…) expressions
    Returns the SubscriberListener handle (call .stop() to unsubscribe).
    """
    root = _compile_expr_to_subscriber(events,
                                       stale_event_time=stale_event_time,
                                       event_loop=event_loop,
                                       once=once,
                                       id=None)
    root.once = once
    return root.on(callback=callback,
                   once=once,
                   timeout=timeout,
                   max_rate=max_rate,
                   discard_match_data=discard_match_data,
                   **kwargs)


# === EVENT LOOP =======================================================================================================
class EventLoop(metaclass=_SingletonMeta):
    """
    Scalable event dispatcher with:
      - per-waiter queues (push on match)
      - stale-window precheck on registration (events + child-subscriber snapshots)
      - exact snapshot delivery
    """
    subscribers: list[Subscriber]
    events: weakref.WeakSet

    def __init__(self):
        self.events = weakref.WeakSet()
        self.subscribers: list[Subscriber] = []

        self.logger = Logger(f"EventLoop", "DEBUG")

        self.subscribers_by_event: dict[Event, set[Subscriber]] = {}
        self._subscribers_lock = threading.RLock()
        self._pattern_subscribers: set[PatternSubscriber] = set()

    # ------------------------------------------------------------------------------------------------------------------
    def add_event(self, event: Event):
        with self._subscribers_lock:
            if event in self.events:
                return
            self.events.add(event)
            event.callbacks.set.register(Callback(
                function=self._event_set,
                inputs={'event': event}
            ))

            # attach to any pattern subscribers that match this event's UID
            for ps in list(self._pattern_subscribers):
                self._attach_pattern_if_match(ps, event)

    # ------------------------------------------------------------------------------------------------------------------
    def add_subscriber(self, subscriber: Subscriber):
        with self._subscribers_lock:
            self.subscribers.append(subscriber)
            subscriber.attach_time = time.monotonic()

            if isinstance(subscriber, PatternSubscriber):
                # Track pattern subscribers for future events & attach all current matches
                self._pattern_subscribers.add(subscriber)
                for ev in list(self.events):
                    self._attach_pattern_if_match(subscriber, ev)
            else:
                # Wire explicit events for non-pattern subscribers
                for cont in subscriber.events:
                    ev = cont.event
                    if isinstance(ev, Event):
                        self.subscribers_by_event.setdefault(ev, set()).add(subscriber)

            # --- Stale prefill for this subscriber ---
            if subscriber.stale_event_time and subscriber.stale_event_time > 0:
                now = time.monotonic()

                # Prefill from Event leaves (respect per-position predicate)
                for cont in subscriber.events:
                    ev = cont.event
                    if isinstance(ev, Subscriber):
                        continue
                    # extend history window on the Event if needed
                    if getattr(ev, "max_history_time", 0) < subscriber.stale_event_time:
                        ev.max_history_time = subscriber.stale_event_time
                    pred = cont.predicate
                    match = ev.first_match_in_window(pred, subscriber.stale_event_time, now=now)
                    if match is not None:
                        flags, data = match
                        subscriber.set_match(ev, flags, data)

                # Prefill from nested Subscriber children (without mutating them):
                cutoff = now - subscriber.stale_event_time
                for cont in subscriber.events:
                    child = cont.event
                    if not isinstance(child, Subscriber):
                        continue

                    # Only snapshot child if the child was attached "recently" relative to our window.
                    child_recent = (getattr(child, "attach_time", None) or 0) >= cutoff
                    if child_recent:
                        snap = self._snapshot_match_for_subscriber(child,
                                                                   window=subscriber.stale_event_time,
                                                                   now=now)
                        if snap is not None:
                            self.logger.debug(f"Prefill stale-window snapshot for {child.id}")
                            # At this parent edge we don't have a distinct flag dict; keep None
                            subscriber.set_match(child, None, snap)

    # ------------------------------------------------------------------------------------------------------------------
    def remove_subscriber(self, waiter: Subscriber):
        with self._subscribers_lock:
            self._unsafe_removeWaiter(waiter)

    # ------------------------------------------------------------------------------------------------------------------
    def register_pattern_binding(self, ps: PatternSubscriber, ev: Event):
        with self._subscribers_lock:
            self.subscribers_by_event.setdefault(ev, set()).add(ps)

    # ------------------------------------------------------------------------------------------------------------------
    def _unsafe_removeWaiter(self, waiter: Subscriber):
        if waiter in self.subscribers:
            self.subscribers.remove(waiter)
        for cont in getattr(waiter, "events", ()):
            ev = cont.event
            s = self.subscribers_by_event.get(ev)
            if s is not None:
                s.discard(waiter)
                if not s:
                    self.subscribers_by_event.pop(ev, None)
        if isinstance(waiter, PatternSubscriber):
            self._pattern_subscribers.discard(waiter)

    # ------------------------------------------------------------------------------------------------------------------
    def _event_set(self, data, event: Event, flags, *args, **kwargs):
        with self._subscribers_lock:
            watchers = list(self.subscribers_by_event.get(event, ()))
            for waiter in watchers:
                if waiter._abort:
                    continue

                matched_any_pos = False

                for cont in waiter.events:
                    if cont.event is not event:
                        continue
                    pred = cont.predicate

                    if pred is None:
                        ok = True
                    else:
                        # IMPORTANT: predicate signature is (flags, data)
                        ok = pred(flags, data)  # type: ignore

                    if ok:
                        matched_any_pos = True
                        if not cont.finished:
                            waiter.set_match(event, flags, data)

                if not matched_any_pos:
                    continue

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _check_pattern(event_uid: str, pattern: str) -> bool:
        # Support glob wildcards against full UID. Exact match if no wildcards.
        return fnmatch.fnmatchcase(event_uid, pattern)

    # ------------------------------------------------------------------------------------------------------------------
    def _attach_pattern_if_match(self, ps: PatternSubscriber, ev: Event):
        if self._check_pattern(ev.uid, ps.pattern):
            # Let the PatternSubscriber attach and sync its internal state
            ps.add_event(ev)
            # And also register it in the reverse index so it gets _event_set callbacks
            self.subscribers_by_event.setdefault(ev, set()).add(ps)

    # ------------------------------------------------------------------------------------------------------------------
    def _snapshot_match_for_subscriber(
            self,
            sub: Subscriber,
            window: float,
            now: float | None = None
    ) -> Optional[SubscriberMatch]:
        """
        Compute a synthetic SubscriberMatch for `sub` within `window` seconds, *without*
        mutating `sub` or firing callbacks. Returns None if not satisfiable.
        Mirrors the runtime data/flags/trace shapes used in Subscriber._fire().
        """
        if not window or window <= 0:
            return None
        if now is None:
            now = time.monotonic()
        cutoff = now - window

        # Helper to snapshot a single event-position (by index in sub.events)
        def _event_pos_match(i: int) -> Optional[tuple[dict | None, Any, Event | Subscriber]]:
            cont = sub.events[i]
            ev = cont.event
            pred = cont.predicate

            if isinstance(ev, Event):
                m = ev.first_match_in_window(pred, window, now=now)
                if m is None:
                    return None
                fl, d = m
                return fl, d, ev

            # child Subscriber
            child: Subscriber = ev  # type: ignore
            # Prefer already-produced child matches within the window (no mutation)
            for cm in reversed(child.matches):
                if cm.time < cutoff:
                    break
                # parent edge doesn't have a distinct flag dict -> use None
                return None, cm, child
            # Otherwise, see if a snapshot of the child is satisfiable from history
            cm = self._snapshot_match_for_subscriber(child, window, now)
            if cm is not None:
                return None, cm, child
            return None

        # --- AND semantics: all positions must match ---
        if sub.type == SubscriberType.AND:
            pos_results: list[tuple[dict | None, Any, Event | Subscriber]] = []
            for i in range(len(sub.events)):
                r = _event_pos_match(i)
                if r is None:
                    return None
                pos_results.append(r)

            # Build a synthetic SubscriberMatch mirroring Subscriber._fire()
            matched_events = [c.event for c in sub.events]
            match_ids = [e.uid for e in matched_events]

            data: dict[Any, Any] = {}
            flags: dict[Any, Any] = {}
            trace_data: dict[Any, Any] = {}

            for (fl, d, ev) in pos_results:
                if isinstance(ev, Subscriber):
                    # d is the child's SubscriberMatch
                    child_match: SubscriberMatch = d  # type: ignore
                    data[ev] = child_match.data
                    flags[ev] = child_match.flags
                    trace_data[ev] = child_match
                else:
                    data[ev] = d
                    flags[ev] = fl
                    trace_data[ev] = None

            return SubscriberMatch(
                time=now,
                match=matched_events,
                match_id=match_ids,
                data=data,
                flags=flags,
                trace_data=trace_data,
            )

        # --- OR semantics: newest single position is enough ---
        best: tuple[float, int, tuple[dict | None, Any, Event | Subscriber]] | None = None
        for i in range(len(sub.events)):
            cont = sub.events[i]
            ev = cont.event

            if isinstance(ev, Subscriber):
                # Prefer real child matches in window
                for cm in reversed(ev.matches):
                    if cm.time < cutoff:
                        break
                    cand = (cm.time, i, (None, cm, ev))
                    if best is None or cand[0] > best[0]:
                        best = cand
                if best:
                    continue
                # Else recurse/snapshot
                cm = self._snapshot_match_for_subscriber(ev, window, now)
                if cm:
                    cand = (now, i, (None, cm, ev))
                    if best is None or cand[0] > best[0]:
                        best = cand
            else:
                m = ev.first_match_in_window(cont.predicate, window, now=now)
                if m:
                    fl, d = m
                    # We don't have the true timestamp from history; snapshot at 'now'
                    cand = (now, i, (fl, d, ev))
                    if best is None or cand[0] > best[0]:
                        best = cand

        if best is None:
            return None

        _, i, (fl, d, ev) = best
        if isinstance(ev, Subscriber):
            child_match: SubscriberMatch = d  # type: ignore
            matched_event = ev
            match_id = ev.uid
            data = child_match.data
            flags = child_match.flags
            trace_data = {ev: child_match}
        else:
            matched_event = ev
            match_id = ev.uid
            data = d
            flags = fl
            trace_data = {ev: None}

        return SubscriberMatch(
            time=now,
            match=matched_event,
            match_id=match_id,
            data=data,
            flags=flags,
            trace_data=trace_data,
        )


# === EVENT CONTAINER AND DECORATOR ====================================================================================
class EventContainer:
    id: str | None = None
    events: dict[str, Event]

    def __init__(self, id: str = None):
        if id is not None:
            _check_id(id)
        self.id = id
        self.events = {}

    def add_event(self, event: Event):
        if event.id in self.events:
            raise ValueError(f"Event {event.id} already exists.")
        if event.parent is not None:
            raise ValueError(f"Event {event.id} already has a parent.")
        self.events[event.id] = event
        event.parent = self


# === EVENT CONTAINER DECORATOR ========================================================================================
def event_definition(cls):
    """
    Per-instance Event fields that are automatically added as children of the container.

    Usage:
        @event_definition
        class RobotEvents(EventContainer):
            ready: Event = Event(flags=[EventFlag('level', str)])
            moved: Event

    Notes:
      - If the class does not subclass EventContainer, this decorator will still create
        `self.events` and inject a compatible `add_event` method on the instance.
      - Each instance receives fresh Event objects.
      - Each Event's `id` defaults to the attribute name (even when cloning a class-level template).
    """
    import sys
    import types as _types
    import typing
    from typing import get_origin, get_args

    original_init = getattr(cls, "__init__", None)

    # --- Resolve annotations (supports `from __future__ import annotations`) ---
    try:
        module_globals = sys.modules[cls.__module__].__dict__
        hints = typing.get_type_hints(cls, globalns=module_globals, localns=dict(vars(cls)))
    except Exception:
        hints = getattr(cls, "__annotations__", {}) or {}

    def _is_event_type(t) -> bool:
        if t is Event:
            return True
        if isinstance(t, str):
            return t == "Event" or t.endswith(".Event")
        origin = get_origin(t)
        # Union handling (typing.Union or PEP 604)
        try:
            is_union = (origin is typing.Union) or (origin is _types.UnionType)
        except Exception:
            is_union = (origin is typing.Union)
        if is_union:
            return any(_is_event_type(arg) for arg in get_args(t))
        if origin is typing.ClassVar:
            return False
        return False

    def _clone_event_template(template: Event, new_id: str) -> Event:
        # Rebuild flags schema
        flags = [EventFlag(ef.id, ef.types) for ef in template.flags.values()]
        clone = Event(
            id=new_id,
            data_type=template.data_type,
            flags=flags,
            copy_data_on_set=template.copy_data_on_set,
            data_is_static_dict=template.data_is_static_dict,
        )
        # Copy non-ctor attributes
        clone.custom_data_copy_function = template.custom_data_copy_function
        clone.max_history_time = template.max_history_time
        return clone

    def _ensure_container_bits(self):
        # Ensure this instance has a place to register events
        if not hasattr(self, "events") or not isinstance(getattr(self, "events"), dict):
            self.events = {}

        # Provide add_event if missing (mirror EventContainer.add_event semantics)
        if not hasattr(self, "add_event") or not callable(getattr(self, "add_event")):
            def _add_event(_self, event: Event):
                if event.id in _self.events:
                    raise ValueError(f"Event {event.id} already exists.")
                if event.parent is not None:
                    raise ValueError(f"Event {event.id} already has a parent.")
                _self.events[event.id] = event
                event.parent = _self

            # Bind as a method on the instance
            setattr(self, "add_event", _add_event.__get__(self, self.__class__))

    def new_init(self, *args, **kwargs):
        # Run any user-defined __init__ first
        if original_init:
            original_init(self, *args, **kwargs)

        # Ensure container plumbing exists
        _ensure_container_bits(self)

        # 1) Process annotated attributes
        if isinstance(hints, dict):
            for attr_name, anno in hints.items():
                default_val = getattr(cls, attr_name, None)

                # If class-level default is an Event → clone it per instance and rename to attr_name
                if isinstance(default_val, Event):
                    ev = _clone_event_template(default_val, new_id=attr_name)
                    setattr(self, attr_name, ev)
                    # Register as child
                    self.add_event(ev)
                    continue

                # If annotated as Event (or Optional/Union including Event) and not set in instance → create fresh
                if _is_event_type(anno) and attr_name not in self.__dict__:
                    ev = Event(id=attr_name)
                    setattr(self, attr_name, ev)
                    self.add_event(ev)

        # 2) Pick up any unannotated class-level Event defaults
        for attr_name, value in vars(cls).items():
            if isinstance(value, Event) and attr_name not in self.__dict__:
                ev = _clone_event_template(value, new_id=attr_name)
                setattr(self, attr_name, ev)
                self.add_event(ev)

    cls.__init__ = new_init
    return cls


# ======================================================================================================================
active_event_loop = EventLoop()


# === EXAMPLEScale =====================================================================================================
def example_1():
    logger = Logger("example_1", "DEBUG")
    event1 = Event(id="event1", flags=[EventFlag("level1", str)])
    event2 = Event(id="event2", flags=[EventFlag("level2", str)])
    event23 = Event(id="event23", flags=[EventFlag("level23", str)])

    def subscriber_callback(data, **kwargs):
        logger.info(f"Subscriber callback: {data}")

    subscriber = Subscriber(events=[event1], type=SubscriberType.OR)
    subscriber.on(subscriber_callback)

    def fire_events():
        logger.info("Firing events")
        event1.set(data='data1', flags={'level1': 'a'})

    setInterval(fire_events, 1)

    while True:
        time.sleep(1)


def example_wait():
    event1 = Event(id="event1", flags=EventFlag("level1", str))

    subscriber = Subscriber(events=[event1])

    def fire_events():
        event1.set(data='data1', flags={'level1': 'a'})

    setTimeout(fire_events, 1)

    data, result = subscriber.wait(timeout=10)
    print(result)


def example_wait_for_events():
    event1 = Event(id='event1', flags=[EventFlag('level1', str)])
    event2 = Event(id='event2', flags=[EventFlag('level2', str)])
    event23 = Event(id='event23', flags=[EventFlag('level23', str)])

    def fire_events():
        ...
        # event1.set(data='data1', flags={'level1': 'a'})
        # event2.set(data='data2', flags={'level2': 'b'})
        event23.set(data='data23', flags={'level23': 'c'})

    setTimeout(fire_events, 1)

    data, trace = wait_for_events(OR((event1, pred_flag_equals('level1', 'a')), event2, "event2*"), timeout=4)
    print(data)
    print(trace)

    while True:
        time.sleep(1)


def example_nested_ands_2():
    logger = Logger("example_nested_ands", "DEBUG")
    event1 = Event(id="event1", flags=[EventFlag("level1", str)])
    event2 = Event(id="event2", flags=None)
    events = [event1, event2]

    def fire_events():
        event1.set(data='data1', flags={'level1': 'a'})
        event2.set(data='data2')

    fire_events()

    time.sleep(3)

    data, trace = wait_for_events(
        events=[
            AND(*events)
        ],
        stale_event_time=1,
        timeout=4,
    )

    if data == TIMEOUT:
        print("TIMEOUT")
    else:
        print("OK")


def example_pattern_matches():
    event1 = Event(id='event1')
    event2 = Event(id='event2')
    event23 = Event(id='event23')

    def emit():
        event23.set(data='data23')

    def subscriber_callback(data, match, **kwargs):
        print(f"Subscriber callback: {data}, match: {match.match_id}")

    subscriber = Subscriber(events="event2*")
    listener = subscriber.on(subscriber_callback)

    setTimeout(emit, 1)

    while True:
        time.sleep(1)


def test_pattern_subscriber_attaches_and_receives_events():
    e1 = Event(id="sensor_temp")
    e2 = Event(id="sensor_humid")
    e3 = Event(id="actor_motor")

    hits = []

    def subscriber_callback(data, match, **kwargs):
        print(f"Subscriber callback: {data}, match: {match.match_id}")
        hits.append(match.match_id)

    # ps = Subscriber(events="sensor*")
    # ps = PatternSubscriber(pattern="sensor_*", predicate=None, stale_event_time=0.5)
    # ps_listener = ps.on(subscriber_callback, once=False)

    normal_subscriber = Subscriber(events=[e1, e2, e3], type=SubscriberType.OR)
    normal_listener = normal_subscriber.on(subscriber_callback)

    # Emit from both sensors, but not the actor
    e1.set(data={"t": 21})
    # e2.set(data={"h": 55})
    # e3.set(data={"rpm": 1000})

    # ok = wait_true(lambda: len(hits) >= 2, timeout=1.0)
    # assert ok
    # # Ensure only sensor_* matched
    # ids = [mid for (mid, _) in hits]
    # assert "sensor_temp" in ids and "sensor_humid" in ids
    # assert "actor_motor" not in ids
    #
    # ps_listener.stop()
    # ps.stop()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    test_pattern_subscriber_attaches_and_receives_events()
    # test_pattern_subscriber_attach_and_fire()
