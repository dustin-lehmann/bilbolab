from __future__ import annotations

import abc
import dataclasses
import enum
from typing import Any

# Ideas:
...


# Blocks in the UML Can expose their parameters too, not just inputs/outputs. THis has to be reflected in my experiment language
# How to expose params in my language here for variables.
# Do I need control flow lines as class? This then seems a boit complex to be also writable by hand

# Experiments can have a run once thing at the beginning


# I would love to be able to recreate DILC just using actions here. Maybe this gets then special actions, like prepare trial with inputs and parameters and so on

# ALso multi agent ECILC describe via this via event based stuff in experiment and so on. I think events will be very
# important in experiments


# There is always a start and stop action. We can copy them in the Diagram

# STOP action needs at least one transition

# actions are triggered by a transition or if they are set to a specific time / tick.
# action trigger type define

# Triggers automatically carry action output to input, but we can also disable it by setting an input to a value. Then
# the input is discarded



# I think it would be great if all IDs of actions are unique, so that we can set parameters of other actions, like
# ACTION_ID:PARAMETER

# How to handle nested actions, like in groups? But what about auto-generated groups, then it would be hard to do it by hand in the yaml

# Experiment can also have inputs, that can be optional or required
# Can we also give it lambdas, for example to get a value from the robot, such as lambda: robot.control.mode

# Internal experiment events, but also external events, like robot.control.events.mode_changed or so. But for this we could probably just use event IDs since they already all have one?

# Repeated trigger action?

# Each action can trigger internal events on finished by ID. Also probably with a data

# Support for experiment wide params. But this is probably already handled with experiment inputs.
# Maybe make params a part of experiments, this way I could define a BILBO_Experiment, that has $ROBOT always set to self.bilbo or so, idk


class ActionTrigger:
    TRANSITION = "transition"
    TIME = "time"
    TICK = "tick"


@dataclasses.dataclass
class ExperimentActionParameter:
    id: str
    name: str
    description: str
    type: type | list[type]
    value: Any | None = None


@dataclasses.dataclass
class ExperimentActionInterface:
    input_ids: list[str]
    output_ids: list[str]
    input_names: list[str | None]
    output_names: list[str | None]
    input_types: list[type]
    output_types: list[type]
    parameters: list[ExperimentActionParameter]


@dataclasses.dataclass
class ExperimentActionSettings:
    """
    This is set by the user
    """
    id: str | None = None
    name: str | None = None
    description: str | None = None
    label: str | None = None

    # Scheduling
    after: str | None = None  # id of another action or None
    time: float | None = None  # seconds
    tick: int | None = None

    timeout: float | None = None
    parameters: dict[str, Any] | None = None


class ExperimentActionStatus(enum.StrEnum):
    ...


class ExperimentAction(abc.ABC):
    parameters: dict[str, ExperimentActionParameter]


# ======================================================================================================================
# Other important definitions
# ----------------------------------------------------------------------------------------------------------------------
class ExperimentVariable:
    id: str
    name: str
    description: str
    type: type


class ExperimentInternalEvent:
    id: str
    name: str
    description: str
    flags: list
    datatype: type


# ======================================================================================================================
# 1. EXPERIMENT ACTIONS

# ----------------------------------------------------------------------------------------------------------------------
# 1.1. Groups
class ActionGroup(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
class Parallel(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
class Loop(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
class While(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
# 1.2. Conditions

class ConditionType(enum.Enum):
    EQUAL = "=="
    NOT_EQUAL = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN_OR_EQUAL = "<="
    IN = "in"


class Condition(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
# 1.3 Timing
class TimeWait(ExperimentAction):
    ...


class TickWait(ExperimentAction):
    ...


class TimeWaitUntil(ExperimentAction):
    ...


class TickWaitUntil(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
# 1.4 Events
class EventWait(ExperimentAction):
    ...


class EventEmit(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
# 1.5. Marker
class SetMarkerAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
# 1.6. Variables
class SetVariableAction(ExperimentAction):
    ...

    # TODO: Here it should be possible to set a variable to a value or make math depending on other variables or the same


class SetParameterAction(ExperimentAction):
    ...

    # TODO: Change a parameter of another action


# ----------------------------------------------------------------------------------------------------------------------
# 1.7. Functions
class ExecuteFunctionAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
class PeriodicFunctionAction(ExperimentAction):
    ...

    # TODO: we have to define the outputs and types here. So here we could periodically poll something foe True/False for example


# ----------------------------------------------------------------------------------------------------------------------
class WaitForFunctionAction(ExperimentAction):
    ...

    # TODO: this requires a bool function and it polls it until its True/False. Runs once.


# ----------------------------------------------------------------------------------------------------------------------
# 2.0 BILBO Specific Actions

# 2.1. General
class ResetAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
# 2.2. IO
class BeepAction(ExperimentAction):
    ...


class SpeakAction(ExperimentAction):
    ...


class PlaySoundAction(ExperimentAction):
    ...


class SetLedAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
# 2.3 Control
class WaitForStaticAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
# 2.3.2 Control Config

# ----------------------------------------------------------------------------------------------------------------------
# 2.4. Input


# ----------------------------------------------------------------------------------------------------------------------
# 2.5. Positioning

# ----------------------------------------------------------------------------------------------------------------------
class MoveToAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
class TurnToHeadingAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
class TurnToPointAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
class NavigateToAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
class BuildPRMAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
class SetPlannerAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------


# ----------------------------------------------------------------------------------------------------------------------
# 2.6. Trajectories

# ----------------------------------------------------------------------------------------------------------------------
# 2.7 Interfaces

# ----------------------------------------------------------------------------------------------------------------------
# 2.8. Special Experiments


# ----------------------------------------------------------------------------------------------------------------------
# 2.9. Estimation
class EnableTrackingAction(ExperimentAction):
    ...


# ----------------------------------------------------------------------------------------------------------------------
class BILBO_Event:
    ...

    # TODO: How to get BILBO Events into the experiment? Are all events registered into the event bus by a unique id? Also for this experiment? Like internal stuff is then <experiment_id>:<event_id>? This way I could identify all events?


# === EXPERIMENT =======================================================================================================
@dataclasses.dataclass
class ExperimentInput:
    id: str
    name: str
    description: str
    type: type
    optional: bool = False
    default: Any | None = None


class Experiment:
    ...


# === EXPERIMENT HANDLER ===============================================================================================
class ExperimentHandler:
    ...
