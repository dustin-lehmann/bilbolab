"""General-purpose experiment framework.

Provides a flexible flow-graph execution engine with YAML-serializable experiment
definitions, runtime expression evaluation, branching, runtime loops, and event integration.
Robot-agnostic — can be used with any step-driven system.

Usage:
    from core.utils.experiments import (
        ExperimentParser, ExperimentRunner, ActionRegistry, register_builtin_actions
    )

    registry = ActionRegistry()
    register_builtin_actions(registry)

    definition = ExperimentParser.from_file('experiment.yaml')
    runner = ExperimentRunner(definition, registry)
    runner.initialize(context_objects={'robot': my_robot})

    while not runner.step():
        pass  # or sleep / tick your system
"""

from core.utils.experiments.types import (
    ActionStatus,
    ActionResult,
    ExperimentStatus,
    TriggerType,
    ActionTrigger,
    Transition,
    ActionDataDef,
    ActionParameterDef,
    ExperimentActionData,
    MISSING,
)

from core.utils.experiments.expression import ExpressionEngine, ExpressionError

from core.utils.experiments.action import (
    ActionBase,
    ActionContext,
    ActionEvents,
    ActionCallbacks,
    ActionRegistry,
)

from core.utils.experiments.experiment import (
    ActionDefinition,
    ExperimentDefinition,
    ExperimentRunner,
    ExperimentEvents,
    ExperimentCallbacks,
)

from core.utils.experiments.parser import ExperimentParser, ExperimentParserError

from core.utils.experiments.builtin_actions import register_builtin_actions

from core.utils.experiments.requirement import (
    RequirementBase,
    RequirementContext,
    RequirementResult,
    RequirementRegistry,
    RequirementDefinition,
    register_builtin_requirements,
)

from core.utils.experiments.guard import (
    GuardBase,
    GuardContext,
    GuardDefinition,
    GuardRegistry,
    register_builtin_guards,
)

from core.utils.experiments.experiment_wrapper import (
    Experiment,
    ExperimentResult,
    ExperimentResultMeta,
    EnvironmentInfo,
    GitInfo,
)
