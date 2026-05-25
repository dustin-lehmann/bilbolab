from __future__ import annotations
import abc
import dataclasses
import enum
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union, Any
import yaml

# === Import your primitives / base types =========================================
from robots.frodo.applications.navigation.navigator import (
    NavigationElement,
    NavigatedObjectState,
)
import robots.frodo.applications.navigation.navigator as agent_navigator

from robots.frodo.applications.simulation.frodo_simulation import FRODO_VisionAgent

# === App/core infra (callbacks, events, timers, logging) =========================
from core.utils.events import wait_for_events, AND, TIMEOUT, OR
from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.events import Event, event_definition, EventFlag, pred_flag_equals
from core.utils.exit import register_exit_callback
from core.utils.files import file_exists
from core.utils.logging_utils import Logger
from core.utils.exit import infinite_loop
from core.utils.time import IntervalTimer, TimeoutTimer, setTimeout


# ======================================================================================================================
# EVENT BUS
# ======================================================================================================================
@dataclass
class EventBusSubscriber:
    """Simple (topic, callback) pair registered on the EventBus."""
    topic: str
    callback: Callable | Callback | None = None


class EventBus:
    """
    Minimal pub/sub bus with in-memory history and replay-on-subscribe for the latest topic payload.

    Notes:
      * History is kept unbounded (by design here). If you push lots of events, consider pruning.
      * All history access is guarded by a single lock for simplicity.
    """

    def __init__(self):
        self._subscribers: List[EventBusSubscriber] = []
        self._lock = threading.Lock()
        self.logger = Logger('EventBus', 'DEBUG')
        self.history: list[tuple[str, Any]] = []

    def publish(self, topic: str, data: Any = None):
        """Publish data under a topic; immediately invokes matching subscribers."""
        with self._lock:
            subs = list(self._subscribers)
            # History checks must be done under the same lock to avoid races
            already = self._topic_in_history(topic)
            if already:
                self.logger.warning(f"Topic {topic} already in the history. Republishing ...")
            else:
                self.logger.debug(f"Publishing new topic \"{topic}\"")
            self.history.append((topic, data))

        # Invoke outside the lock to avoid subscriber reentrancy deadlocks
        for sub in subs:
            try:
                if sub.topic == topic:
                    if sub.callback:
                        sub.callback(topic, data)
            except Exception as e:
                # Keep the bus resilient
                self.logger.error(f"[EventBus] subscriber error on {topic}: {e}")

    def set_signal(self, signal_id, data: Any = None):
        """Convenience wrapper to publish to 'signal/<name>'."""
        signal = self.topic_signal(signal_id)
        self.publish(signal, data)

    def subscribe(self, subscriber: EventBusSubscriber):
        """
        Subscribe to a topic and immediately replay the last known payload for that topic
        (if present).
        """
        with self._lock:
            self._subscribers.append(subscriber)
            replay_data = self._get_topic_from_history(subscriber.topic)
        if replay_data is not None and subscriber.callback is not None:
            try:
                subscriber.callback(subscriber.topic, replay_data)
            except Exception as e:
                self.logger.error(f"[EventBus] replay to subscriber failed on {subscriber.topic}: {e}")

    def unsubscribe(self, subscriber: EventBusSubscriber):
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def clear(self):
        """Remove all subscribers and clear history."""
        with self._lock:
            self._subscribers.clear()
            self.history.clear()

    # --- internals (guard all history access with the lock) ----------------------
    def _topic_in_history(self, topic: str) -> bool:
        return any(t == topic for t, _ in self.history)

    def _get_topic_from_history(self, topic: str) -> Any:
        for t, d in reversed(self.history):
            if t == topic:
                return d
        return None

    # Topic helpers
    @staticmethod
    def topic_agent_finished(agent_id: str, element_id: str) -> str:
        return f"agent/{agent_id}/finished/{element_id}"

    @staticmethod
    def topic_finished(element_id: str) -> str:
        return f"finished/{element_id}"

    @staticmethod
    def topic_error(agent_id: str) -> str:
        return f"agent/{agent_id}/error"

    @staticmethod
    def topic_signal(name: str) -> str:
        return f"signal/{name}"


# ======================================================================================================================
# Conditions
# ======================================================================================================================

@event_definition
class ConditionEvents:
    satisfied: Event


@callback_definition
class ConditionCallbacks:
    satisfied: CallbackContainer


class Condition(abc.ABC):
    """A boolean gate attached to the event bus. Used in Action.conditions."""
    _satisfied_event_set: bool = False
    _flag: bool = False

    def __init__(self):
        self.events = ConditionEvents()
        self.callbacks = ConditionCallbacks()
        self.logger = Logger(f"{self.__class__.__name__}", "DEBUG")

    def attach(self, bus: EventBus): ...

    def satisfied(self) -> bool: ...

    def get_config(self) -> dict:
        return {"type": self.__class__.__name__}


# ----------------------------------------------------------------------------------------------------------------------
class EventCondition(Condition):
    """Becomes true once a specific topic is observed on the EventBus."""
    subscriber: EventBusSubscriber | None = None
    bus: EventBus | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, topic: str):
        super().__init__()
        self.topic = topic

    # ------------------------------------------------------------------------------------------------------------------
    def attach(self, bus: EventBus):
        self.bus = bus
        self.subscriber = EventBusSubscriber(
            topic=self.topic,
            callback=self.topic_callback
        )
        self.bus.subscribe(self.subscriber)

    # ------------------------------------------------------------------------------------------------------------------
    def topic_callback(self, topic: str, data: Any = None):
        self.logger.debug(f"Condition on topic \"{topic}\" satisfied")
        # One-shot
        if self.bus and self.subscriber:
            self.bus.unsubscribe(self.subscriber)
        self._flag = True
        self.callbacks.satisfied.call(self)
        self.events.satisfied.set()
        self._satisfied_event_set = True

    # ------------------------------------------------------------------------------------------------------------------
    def satisfied(self) -> bool:
        return self._flag

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> dict:
        return {"type": "EventCondition",
                "topic": self.topic}

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: dict) -> 'EventCondition':
        return cls(
            topic=config["topic"]
        )


# ----------------------------------------------------------------------------------------------------------------------
class AllOf(Condition):
    """True once all subconditions are satisfied (AND)."""

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, conditions: Iterable[ConditionLike]):
        super().__init__()
        self.conditions = list(_coerce_conditions(conditions))

    # ------------------------------------------------------------------------------------------------------------------
    def attach(self, bus: EventBus):
        for condition in self.conditions:
            condition.attach(bus)
            condition.callbacks.satisfied.register(self._child_satisfied)

    # ------------------------------------------------------------------------------------------------------------------
    def _child_satisfied(self, *_):
        if all(c.satisfied() for c in self.conditions):
            if not self._satisfied_event_set:
                self.logger.info("All conditions satisfied!")
                self._satisfied_event_set = True
                self.callbacks.satisfied.call(self)
                self.events.satisfied.set()

    # ------------------------------------------------------------------------------------------------------------------
    def satisfied(self) -> bool:
        return all(c.satisfied() for c in self.conditions)

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> dict:
        return {"type": "AllOf",
                "conditions":
                    [c.get_config() for c in self.conditions]
                }

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: dict) -> 'AllOf':
        for condition in config["conditions"]:
            if condition["type"] not in CONDITION_MAPPING:
                raise ValueError(f"Condition type {condition['type']} not supported.")
        return cls(
            conditions=[CONDITION_MAPPING[condition["type"]].from_config(condition) for condition in
                        config["conditions"]]
        )


# ----------------------------------------------------------------------------------------------------------------------
class AnyOf(Condition):
    """True once any subcondition is satisfied (OR)."""

    def __init__(self, conditions: Iterable[Condition] | list[ConditionLike]):
        super().__init__()
        self.conditions = list(_coerce_conditions(conditions))

    # ------------------------------------------------------------------------------------------------------------------
    def attach(self, bus: EventBus):
        for condition in self.conditions:
            condition.attach(bus)
            condition.callbacks.satisfied.register(self._child_satisfied)

    # ------------------------------------------------------------------------------------------------------------------
    def _child_satisfied(self, *_):
        if not self._satisfied_event_set:
            self.logger.info("Any condition satisfied!")
            self._satisfied_event_set = True
            self.callbacks.satisfied.call(self)
            self.events.satisfied.set()

    # ------------------------------------------------------------------------------------------------------------------
    def satisfied(self) -> bool:
        return any(c.satisfied() for c in self.conditions)

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> dict:
        return {"type": "AnyOf",
                "conditions": [c.get_config() for c in self.conditions]
                }

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: dict) -> 'AnyOf':
        for condition in config["conditions"]:
            if condition["type"] not in CONDITION_MAPPING:
                raise ValueError(f"Condition type {condition['type']} not supported.")
        return cls(
            conditions=[CONDITION_MAPPING[condition["type"]].from_config(condition) for condition in
                        config["conditions"]]
        )


# ----------------------------------------------------------------------------------------------------------------------
class Timeout(Condition):
    """True after a wall-clock timeout."""
    _started: bool = False

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, seconds: float):
        super().__init__()
        self.seconds = seconds
        self._flag = False
        self._timer: TimeoutTimer | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def attach(self, bus: EventBus):
        self._timer = TimeoutTimer(timeout_time=self.seconds, timeout_callback=self._on_timeout)
        self._timer.start()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_timeout(self):
        self._timer = None
        self._flag = True
        self.logger.debug(f"Timeout ({self.seconds}) condition satisfied")
        self.callbacks.satisfied.call(self)
        self.events.satisfied.set()

    # ------------------------------------------------------------------------------------------------------------------
    def satisfied(self) -> bool:
        return self._flag

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> dict:
        return {"type": "Timeout", "seconds": self.seconds}

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: dict) -> 'Timeout':
        return cls(
            seconds=config["seconds"]
        )


# Sugar: accept either Condition or topic-string
ConditionLike = Union[Condition, str]


def _coerce_conditions(seq: Sequence[ConditionLike] | list[ConditionLike] | Iterable[ConditionLike]) -> List[Condition]:
    out: List[Condition] = []
    for w in seq:
        if isinstance(w, Condition):
            out.append(w)
        elif isinstance(w, str):
            out.append(EventCondition(w))
        else:
            raise TypeError(f"Unsupported condition type: {type(w)}")
    return out


# ======================================================================================================================
CONDITION_MAPPING = {
    "EventCondition": EventCondition,
    "AllOf": AllOf,
    "AnyOf": AnyOf,
    "Timeout": Timeout,
}


# ======================================================================================================================
# ACTIONS
# ======================================================================================================================
@event_definition
class ActionEvents:
    finished: Event
    timeout: Event
    error: Event


@callback_definition
class ActionCallbacks:
    finished: CallbackContainer
    timeout: CallbackContainer
    error: CallbackContainer


class ActionState(enum.StrEnum):
    NOT_READY = "not_ready"
    RUNNING = "running"
    FINISHED = "finished"


class Action(abc.ABC):
    """
    Base action with a condition gate and optional abort signal.

    Lifecycle:
      initialize() -> run() -> (internally) _wait_for_conditions() -> _execute_action() -> _on_finished()
    """
    id: str  # ID of the action
    finished_emit_signal: str | None  # Topic to emit when the action is finished
    conditions: List[Condition]  # Conditions that must be true before the action can be executed
    blocking: bool  # If true, the scheduler will not advance past this action's position until `finished` is True
    comment: Optional[str] = None  # Optional comment to describe the action

    abort_signal: str | None
    abort_condition: EventCondition | None = None
    # runtime
    state: ActionState = ActionState.NOT_READY
    started: bool = False
    finished: bool = False

    events: ActionEvents
    callbacks: ActionCallbacks
    logger: Logger

    condition_timeout: float | None = None
    execution_timeout: float | None = None

    navigator: MultiAgentNavigator | None = None

    @event_definition
    class _InternalEvents:
        ready: Event
        abort_waiting_for_conditions: Event

    # === INIT =========================================================================================================
    def __init__(self,
                 id: str,
                 finished_emit_signal: str | None = None,
                 abort_signal: str | None = None,
                 conditions: Sequence[ConditionLike] = (),
                 blocking: bool = False,
                 comment: Optional[str] = None):
        self.id = id
        self.finished_emit_signal = finished_emit_signal
        self.abort_signal = abort_signal

        if self.abort_signal:
            self.abort_condition = EventCondition(topic=self.abort_signal)

        self.conditions = _coerce_conditions(conditions)
        self.blocking = blocking
        self.comment = comment

        self.events = ActionEvents()
        self._internal_events = self._InternalEvents()
        self.callbacks = ActionCallbacks()
        self.logger = Logger(f"{self.__class__.__name__} \"{self.id}\"", "DEBUG")

    # === METHODS ======================================================================================================
    def initialize(self, navigator: MultiAgentNavigator):
        """Bind the action to a navigator and reset runtime flags."""
        self.navigator = navigator
        self.started = False
        self.finished = False
        self.state = ActionState.NOT_READY

    # ------------------------------------------------------------------------------------------------------------------
    def run(self) -> bool:
        """
        Start the action. If non-blocking, the core logic runs in a daemon thread and this returns True immediately.
        """
        self.logger.info(f"Run action {self.id}")
        if self.comment:
            self.logger.info(f"Comment: {self.comment}")
        self.started = True
        self.state = ActionState.RUNNING

        if self.blocking:
            result = self._run()
        else:
            thread = threading.Thread(target=self._run, daemon=True)
            thread.start()
            result = True

        return result

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def get_config(self) -> dict:
        ...

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    @abc.abstractmethod
    def from_config(cls, config: dict) -> Action:
        ...

    # === PRIVATE METHODS ==============================================================================================
    def _run(self) -> bool:
        # 1. Wait for conditions
        if not self._wait_for_conditions():
            return False

        self.logger.debug(f"Start execution ... ")
        # 2. Execute action
        if not self._execute_action():
            return False

        self._on_finished()
        return True

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def _execute_action(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _wait_for_conditions(self) -> bool:
        """
        Wait for the action's condition set (AND of all conditions), or optional abort signal.
        """
        self.logger.debug(f"Waiting for {len(self.conditions)} conditions")

        # No conditions -> ready immediately
        if not self.conditions:
            self.logger.debug("No conditions; proceeding immediately.")
            return True

        for condition in self.conditions:
            condition.attach(self.navigator.bus)

        condition_events = [condition.events.satisfied for condition in self.conditions]
        condition_subscriber = AND(*condition_events)

        if self.abort_condition:
            self.abort_condition.attach(self.navigator.bus)
            subscriber = OR(condition_subscriber, self.abort_condition.events.satisfied)
        else:
            subscriber = condition_subscriber

        data, trace = wait_for_events(
            events=subscriber,
            stale_event_time=0.25,
            timeout=self.condition_timeout,
        )

        if data is TIMEOUT:
            self.logger.warning(f"Action {self.id} timed out waiting for conditions.")
            self.events.timeout.set()
            return False

        if self.abort_condition and trace.caused_by(self.abort_condition.events.satisfied):
            self.logger.debug(f"Action {self.id} aborted waiting for conditions.")
            return False

        # All conditions path
        self.logger.debug(f"Conditions satisfied")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _on_finished(self):
        """Emit per-action finished signals, optional custom signal, and local events/callbacks."""
        self.finished = True
        self.state = ActionState.FINISHED
        self.logger.info(f"Action {self.id} finished.")

        if self.finished_emit_signal:
            self.logger.debug(f"Emitting optional signal \"{self.finished_emit_signal}\"")
            self.navigator.bus.publish(self.navigator.bus.topic_signal(self.finished_emit_signal), self.id)

        self.logger.debug(f"Emitting finished signal \"{self.navigator.bus.topic_finished(self.id)}\"")
        self.navigator.bus.publish(self.navigator.bus.topic_finished(self.id), self.id)

        self.callbacks.finished.call(self)
        self.events.finished.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_error(self, e: Exception):
        self.logger.error(f"Action {self.id} failed: {e}")
        self.events.error.set()
        self.callbacks.error.call(self, e)


# ----------------------------------------------------------------------------------------------------------------------
class Wait(Action):
    """Blocking wait that completes when given conditions/signals/timeout occur."""
    conditions: list[Condition]

    # === INIT =========================================================================================================
    def __init__(self,
                 id: str,
                 finished_emit_signal: str | None = None,
                 abort_signal: str | None = None,
                 conditions: list[ConditionLike] = (),
                 seconds: float | None = None,
                 signals: str | list[str] | None = None, ):

        super().__init__(id, finished_emit_signal, abort_signal, conditions, True)
        self.conditions = _coerce_conditions(conditions or [])

        self._seconds_param: float | None = seconds

        if seconds is not None:
            timeout_condition = Timeout(seconds)
            self.conditions.append(timeout_condition)

        if signals is not None and not isinstance(signals, list):
            signals = [signals]
        self._signals_param: list[str] | None = list(signals) if signals else None
        if self._signals_param:
            for sig in self._signals_param:
                self.conditions.append(EventCondition(sig))

    # ------------------------------------------------------------------------------------------------------------------
    def _execute_action(self):
        # Since the waiting part is already done in self._wait_for_conditions(),
        # we just need to emit the finished signal.
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> dict:
        return {
            "type": "wait",
            "id": self.id,
            "finished_emit_signal": self.finished_emit_signal,
            "abort_signal": self.abort_signal,
            "blocking": True,  # Wait is always blocking in this implementation
            "comment": self.comment,
            # Keep YAML simple: preserve seconds/signals if they were passed in,
            # and also include full conditions (topics may be strings).
            "seconds": self._seconds_param,
            "signals": (self._signals_param[0] if self._signals_param and len(self._signals_param) == 1
                        else self._signals_param),
            "conditions": conditions_to_config(self.conditions)
        }

    @classmethod
    def from_config(cls, config: dict) -> 'Wait':
        return cls(
            id=config["id"],
            finished_emit_signal=config.get("finished_emit_signal"),
            abort_signal=config.get("abort_signal"),
            conditions=[condition_from_config(c) for c in config.get("conditions", [])],
            seconds=config.get("seconds"),
            signals=config.get("signals"),
        )


# ----------------------------------------------------------------------------------------------------------------------
class Move(Action):
    """
    Dispatch a navigation element to an agent; waits for a matching finish/error/abort/timeout.
    """
    element: NavigationElement
    agent_id: str

    # === INIT =========================================================================================================
    def __init__(self,
                 id: str,
                 agent_id: str,
                 element: NavigationElement,
                 finished_emit_signal: str | None = None,
                 abort_signal: str | None = None,
                 conditions: Sequence[ConditionLike] = (),
                 blocking: bool = False,
                 comment: Optional[str] = None):
        super().__init__(id, finished_emit_signal, abort_signal, conditions, blocking, comment)
        self.element = element
        self.agent_id = agent_id

    # === METHODS ======================================================================================================
    def get_config(self) -> dict:
        # Try to serialize the element richly if possible
        if hasattr(self.element, "get_config") and callable(getattr(self.element, "get_config")):
            element_cfg = self.element.get_config()
        else:
            # Minimal fallback
            raise ValueError(f"Element {self.element} has no get_config() method. ")

        return {
            "type": "move",
            "id": self.id,
            "agent_id": self.agent_id,
            "finished_emit_signal": self.finished_emit_signal,
            "abort_signal": self.abort_signal,
            "blocking": self.blocking,
            "comment": self.comment,
            "conditions": conditions_to_config(self.conditions),
            "element": element_cfg,
        }

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: dict) -> 'Move':
        element_cfg = config.get("element")
        if not isinstance(element_cfg, dict):
            raise ValueError("Move action requires 'element' dict in config.")
        element = agent_navigator.element_from_config(element_cfg)

        return cls(
            id=config["id"],
            agent_id=config["agent_id"],
            element=element,
            finished_emit_signal=config.get("finished_emit_signal"),
            abort_signal=config.get("abort_signal"),
            conditions=[condition_from_config(c) for c in config.get("conditions", [])],
            blocking=config.get("blocking", False),
            comment=config.get("comment"),
        )

    # === PRIVATE METHODS ==============================================================================================
    def _execute_action(self) -> bool:
        # 1. Get the agent
        agent = self.navigator.get_agent_by_id(self.agent_id)
        if not agent:
            self.logger.error(f"Agent {self.agent_id} not found.")
            return False

        # 2. Send the element to the agent
        self.logger.debug(f"Movement: {self.element.id} -> {self.agent_id}")
        agent.add_navigation_element(self.element)

        # Gate the 'finished' event by checking the element id to avoid cross-element matches.
        # finished_guard = (agent.events.finished, pred_flag_equals('id', self.element.id))

        finished_guard = agent.events.finished

        event_list = [finished_guard,
                      agent.events.error,
                      agent.events.aborted,
                      agent.events.timeout]

        if self.abort_condition:
            event_list.append(self.abort_condition.events.satisfied)

        # 3. Wait for any of the agent's terminal events (or abort)
        data, trace = wait_for_events(
            events=OR(*event_list),
            timeout=self.execution_timeout,
            stale_event_time=1,
        )

        if data is TIMEOUT:
            self.logger.warning(f"Action {self.id} timed out waiting for agent {self.agent_id} to finish.")
            self.events.timeout.set()
            return False

        if self.abort_condition and trace.caused_by(self.abort_condition.events.satisfied):
            self.logger.debug(f"Action {self.id} aborted while waiting for agent {self.agent_id}. Aborting on agent.")
            try:
                agent.abort_current_element()
            except Exception as e:
                self.logger.warning(f"Abort request to agent {self.agent_id} raised: {e}")
            return False

        if trace.caused_by(agent.events.finished):
            self.logger.debug(f"Agent {self.agent_id} finished element {self.element.id}.")
            return True
        elif trace.caused_by(agent.events.error):
            self.logger.error(f"Agent {self.agent_id} failed.")
            self._on_error(trace.data)
            return False
        elif trace.caused_by(agent.events.aborted):
            self.logger.debug(f"Movement {self.id} aborted on agent {self.agent_id}.")
            return False
        elif trace.caused_by(agent.events.timeout):
            self.logger.warning(f"Movement {self.id} timed out on agent {self.agent_id}")
            self.events.timeout.set()
            return False
        else:
            self.logger.error(f"Action {self.id} failed: {trace.data}")
            return False


# ----------------------------------------------------------------------------------------------------------------------
class ActionGroup(Action):
    """
    Sequence/group of actions executed via plan's stepping.
    """
    actions: list[Action]

    # === INIT =========================================================================================================
    def __init__(self,
                 id: str,
                 actions: list[Action],
                 finished_emit_signal: str | None = None,
                 abort_signal: str | None = None,
                 conditions: Sequence[ConditionLike] = (),
                 blocking: bool = False,
                 comment: Optional[str] = None
                 ):
        super().__init__(id, finished_emit_signal, abort_signal, conditions, blocking, comment)
        self.actions = actions

    # === METHODS ======================================================================================================
    def initialize(self, navigator: MultiAgentNavigator):
        self.navigator = navigator
        self.started = False
        self.finished = False
        self.state = ActionState.NOT_READY
        for action in self.actions:
            action.initialize(self.navigator)

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> dict:
        return {
            "type": "group",
            "id": self.id,
            "finished_emit_signal": self.finished_emit_signal,
            "abort_signal": self.abort_signal,
            "blocking": self.blocking,
            "comment": self.comment,
            "conditions": conditions_to_config(self.conditions),
            "actions": [a.get_config() for a in self.actions],
        }

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: dict) -> 'ActionGroup':
        actions_cfg = config.get("actions", [])
        actions = [action_from_config(ac) for ac in actions_cfg]
        return cls(
            id=config["id"],
            actions=actions,
            finished_emit_signal=config.get("finished_emit_signal"),
            abort_signal=config.get("abort_signal"),
            conditions=[condition_from_config(c) for c in config.get("conditions", [])],
            blocking=config.get("blocking", False),
            comment=config.get("comment"),
        )

    # === PRIVATE METHODS ==============================================================================================
    def _execute_action(self) -> bool:
        for action in self.actions:
            result = action.run()
            if not result:
                return False
        return True


ACTION_MAPPING = {
    'wait': Wait,
    'move': Move,
    'group': ActionGroup
}


# ======================================================================================================================
# PLAN
# ======================================================================================================================
class NavigatorPlanState(enum.StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


@event_definition
class NavigatorPlanEvents:
    finished: Event = Event(copy_data_on_set=False)
    error: Event


@callback_definition
class NavigatorPlanCallback:
    finished: CallbackContainer = CallbackContainer(inputs=["plan"])
    error: CallbackContainer


@dataclasses.dataclass(frozen=True)
class NavigatorPlan_Sample:
    id: str
    status: NavigatorPlanState
    current_action: str | None
    current_action_index: int | None


class NavigatorPlan:
    """
    A linear plan: executes actions in order. Non-blocking actions are dispatched
    and the plan advances; completion is detected via the combined finished events.
    """
    id: str

    current_action: Action | None = None
    current_action_index: int | None = None

    actions: list[Action]
    navigator: MultiAgentNavigator | None = None

    state: NavigatorPlanState = NavigatorPlanState.IDLE

    _thread: threading.Thread | None = None

    # === INIT =========================================================================================================
    def __init__(self, id, actions: list[Action]):
        self.id = id
        self.actions = actions

        self.events = NavigatorPlanEvents()
        self.callbacks = NavigatorPlanCallback()
        self.logger = Logger(f"NavigatorPlan \"{self.id}\"", "DEBUG")

    # === METHODS ======================================================================================================
    def initialize(self, navigator: MultiAgentNavigator) -> bool:
        """Bind to a navigator, check preconditions, and initialize actions."""
        self.navigator = navigator
        self.current_action = None
        self.current_action_index = 0
        self.state = NavigatorPlanState.IDLE

        result = self._check_preconditions()
        if not result:
            return False

        for action in self.actions:
            action.initialize(navigator)

        self.logger.info(f"Initialized plan with {len(self.actions)} actions.")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _check_preconditions(self) -> bool:
        """
        Verify that all navigation objects (agents) referenced by every action
        (including children of ActionGroups) exist in the navigator.

        Raises:
            ValueError: if any Move action references an agent that is not
                        registered in the MultiAgentNavigator.
        """
        if not self.navigator:
            raise RuntimeError("NavigatorPlan must be initialized with a navigator before checking preconditions.")

        missing: dict[str, list[str]] = {}  # agent_id -> [action_ids]

        def walk(actions: Iterable[Action]):
            for act in actions:
                if isinstance(act, Move):
                    if act.agent_id not in self.navigator.agents:
                        missing.setdefault(act.agent_id, []).append(act.id)
                elif isinstance(act, ActionGroup):
                    walk(act.actions)
                else:
                    # Other action types (e.g., Wait) do not reference agents directly
                    pass

        walk(self.actions)

        if missing:
            details = ", ".join(
                f"{agent_id} (used by actions: {', '.join(action_ids)})"
                for agent_id, action_ids in missing.items()
            )
            msg = f"Precondition failed: missing agents in navigator -> {details}"
            self.logger.error(msg)
            return False

        self.logger.debug("Preconditions OK: all referenced agents are present in the navigator.")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def run(self) -> None:
        """
        Start the plan. If non-empty, we register a combined finished listener so
        the plan can resolve when all actions report finished.
        """
        self.logger.info(f"Run plan")
        self.state = NavigatorPlanState.RUNNING

        # If there are no actions, finish immediately.
        if not self.actions:
            self._on_last_action_finished()
            return

        # Register the finished callback for the last action group (all actions finished)
        finished_events = AND(*[action.events.finished for action in self.actions])
        finished_events.on(callback=self._on_last_action_finished, once=True)

        self._thread = threading.Thread(target=self._task, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: dict) -> 'NavigatorPlan':
        """
        Expected shape:
        {
          "id": "plan_id",
          "actions": [ { "type": "...", ... }, ... ]
        }
        """
        pid = config.get("id")
        if not pid:
            raise ValueError("NavigatorPlan config missing 'id'")
        actions_cfg = config.get("actions", [])
        actions = [action_from_config(ac) for ac in actions_cfg]
        return cls(pid, actions)

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> dict:
        return {
            "id": self.id,
            "actions": [a.get_config() for a in self.actions],
        }

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_yaml(cls, yaml_file: str) -> 'NavigatorPlan':
        if not file_exists(yaml_file):
            raise FileNotFoundError(f"File not found: {yaml_file}")
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # Allow either top-level plan object or nested under "plan"
        plan_cfg = data.get("plan", data)
        return cls.from_config(plan_cfg)

    # ------------------------------------------------------------------------------------------------------------------
    def to_yaml(self, file_path: str):
        data = {"plan": self.get_config()}
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> NavigatorPlan_Sample:
        return NavigatorPlan_Sample(self.id,
                                    self.state,
                                    self.current_action.id if self.current_action else None,
                                    self.current_action_index)

    # === PRIVATE METHODS ==============================================================================================
    def _task(self) -> None:
        """
        Core stepping loop: dispatch actions in order. Non-blocking actions are dispatched
        (and may finish later); blocking actions complete before we advance the index.
        """
        while True:
            # 1. Take the next action
            if self.current_action_index >= len(self.actions):
                return

            action = self.actions[self.current_action_index]
            self.logger.info(f"Starting action {action.id} ({self.current_action_index + 1}/{len(self.actions)})")
            result = action.run()

            if not result:
                self.logger.warning(f"Action {action.id} failed. Exiting plan.")
                self.callbacks.error.call(self)
                self.events.error.set()
                return

            # Logging reflects actual behavior for blocking vs non-blocking actions
            if action.blocking:
                self.logger.info(f"Finished action {action.id} ({self.current_action_index + 1}/{len(self.actions)})")
            else:
                self.logger.info(f"Dispatched action {action.id} ({self.current_action_index + 1}/{len(self.actions)})")

            self.current_action_index += 1

    # ------------------------------------------------------------------------------------------------------------------
    def _on_last_action_finished(self, *args, **kwargs):
        self.logger.info(f"Plan finished.")
        self.events.finished.set(self)
        self.callbacks.finished.call(self)
        self.state = NavigatorPlanState.FINISHED


# ======================================================================================================================
# NAVIGATOR
# ======================================================================================================================
class MultiAgentNavigator_State(enum.StrEnum):
    RUNNING = 'running'
    IDLE = 'idle'


@dataclasses.dataclass(frozen=True)
class MultiAgentNavigator_Sample:
    status: MultiAgentNavigator_State
    current_plan_id: str | None
    current_plan: NavigatorPlan_Sample


class MultiAgentNavigator:
    """
    Orchestrates agents and a single active plan over an EventBus.
    """
    bus: EventBus
    agents: dict[str, agent_navigator.NavigatedObject]
    current_plan: NavigatorPlan | None
    state: MultiAgentNavigator_State = MultiAgentNavigator_State.IDLE

    # === INIT =========================================================================================================
    def __init__(self):
        self.bus = EventBus()
        self.agents = {}
        self.logger = Logger("MultiAgentNavigator", "DEBUG")

        self.current_plan = None

    # === METHODS ======================================================================================================
    def add_agent(self, agent: agent_navigator.NavigatedObject):
        if agent.id in self.agents:
            self.logger.warning(f"Agent {agent.id} already exists.")
            return
        self.agents[agent.id] = agent
        self.logger.info(f"Added agent {agent.id}")

    # ------------------------------------------------------------------------------------------------------------------
    def remove_agent(self, agent: str | agent_navigator.NavigatedObject):
        if isinstance(agent, agent_navigator.NavigatedObject):
            agent = agent.id
        if agent not in self.agents:
            self.logger.warning(f"Agent {agent} not found.")
            return
        del self.agents[agent]
        self.logger.info(f"Removed agent {agent}")

    # ------------------------------------------------------------------------------------------------------------------
    def load_plan(self, plan: NavigatorPlan, start: bool = False) -> bool:
        """
        Load a plan (replacing the current plan once it's finished), clear the bus, and optionally start it.
        """
        if self.state == MultiAgentNavigator_State.RUNNING:
            self.logger.warning("Cannot load a plan while the navigator is running.")
            return False

        if self.current_plan is not None and self.current_plan.state != NavigatorPlanState.FINISHED:
            self.logger.warning(f"Plan {plan.id} not finished. Exiting plan.")
            return False

        # Clear the event bus
        self.bus.clear()

        self.current_plan = None
        result = plan.initialize(self)
        if not result:
            self.logger.warning(f"Plan {plan.id} initialization failed. Exiting plan.")
            return False
        self.current_plan = plan
        self.current_plan.callbacks.finished.register(self._plan_finished_callback)
        self.current_plan.callbacks.error.register(self._plan_error_callback)

        self.logger.info(f"Loaded plan {self.current_plan.id} with {len(self.current_plan.actions)} actions.")

        if start:
            self.run_current_plan()

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def load_plan_from_file(self, plan_file: str, start: bool = False):
        """
        Load a plan from a YAML file (replacing the current plan once it's finished), clear the bus, and optionally
        start it.
        """
        if not file_exists(plan_file):
            self.logger.warning(f"File {plan_file} not found. Exiting.")
            return
        plan = NavigatorPlan.from_yaml(plan_file)
        self.load_plan(plan, start)

    # ------------------------------------------------------------------------------------------------------------------
    def stop_current_plan(self):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def run_current_plan(self, blocking: bool = False, timeout: float | None = None) -> bool:
        if not self.current_plan:
            self.logger.warning("No current plan to start.")
            return False

        if self.current_plan.state != NavigatorPlanState.IDLE:
            self.logger.warning(f"Plan {self.current_plan.id} not idle. Exiting plan.")
            return False

        self.logger.info(f"Starting plan {self.current_plan.id}")

        plan = self.current_plan
        self.current_plan.run()

        if blocking:
            data, trace = wait_for_events(
                events=OR(
                    plan.events.finished,
                    plan.events.error,
                ),
                timeout=timeout
            )
            if data is TIMEOUT:
                self.logger.warning(f"Plan {plan.id} timed out.")
                return False
            if trace.caused_by(self.current_plan.events.error):
                self.logger.error(f"Plan {plan.id} failed.")
                return False

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def get_agent_by_id(self, agent_id: str) -> agent_navigator.NavigatedObject | None:
        if agent_id not in self.agents:
            self.logger.warning(f"Agent {agent_id} not found.")
            return None

        return self.agents[agent_id]

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> MultiAgentNavigator_Sample:
        return MultiAgentNavigator_Sample(self.state,
                                          current_plan_id=self.current_plan.id if self.current_plan else None,
                                          current_plan=self.current_plan.get_sample() if self.current_plan else None)

    # === PRIVATE METHODS ==============================================================================================
    def _plan_finished_callback(self, *args, **kwargs):
        self.logger.info(f" ✅ Finished plan {self.current_plan.id}")
        self.current_plan = None
        self.state = MultiAgentNavigator_State.IDLE

    # ------------------------------------------------------------------------------------------------------------------
    def _plan_error_callback(self, error: Exception):
        self.logger.error(f"❌ Error in plan {self.current_plan.id}: {error}")
        self.current_plan = None
        self.state = MultiAgentNavigator_State.IDLE


# === HELPERS ==========================================================================================================
# --- Condition helpers (place near CONDITION_MAPPING) ---------------------------
def condition_from_config(obj: Union[str, dict]) -> Condition:
    """Accept either a topic string or a condition config dict."""
    if isinstance(obj, str):
        return EventCondition(obj)
    if not isinstance(obj, dict) or "type" not in obj:
        raise ValueError(f"Invalid condition config: {obj}")
    t = obj["type"]
    if t not in CONDITION_MAPPING:
        raise ValueError(f"Unsupported condition type: {t}")
    return CONDITION_MAPPING[t].from_config(obj)


# ----------------------------------------------------------------------------------------------------------------------
def conditions_to_config(conditions: Iterable[ConditionLike]) -> list[dict | str]:
    """Preserve 'string topic' shorthand when possible; otherwise full dicts."""
    out: list[dict | str] = []
    for c in conditions:
        if isinstance(c, EventCondition):
            # keep shorthand as plain topic string
            out.append(c.topic)
        elif isinstance(c, Condition):
            out.append(c.get_config())
        elif isinstance(c, str):
            out.append(c)  # already a topic
        else:
            raise TypeError(f"Unsupported condition type in serialization: {type(c)}")
    return out


# ----------------------------------------------------------------------------------------------------------------------
def action_from_config(config: dict) -> 'Action':
    t = config.get("type")
    if not t:
        raise ValueError("Action config missing 'type'")
    cls = ACTION_MAPPING.get(t.lower()) or ACTION_MAPPING.get(t)
    if not cls:
        raise ValueError(f"Unsupported action type: {t}")
    return cls.from_config(config)


if __name__ == '__main__':
    ...
