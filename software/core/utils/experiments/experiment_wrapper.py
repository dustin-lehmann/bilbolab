"""Generic experiment wrapper around ExperimentRunner.

Adds lifecycle tracking (start/end time), result collection, and a clean
override point (_build_result) for robot-specific subclasses.

Externally stepped — the owner calls initialize() once, then step() repeatedly.
"""

import getpass
import platform
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.utils.events import event_definition, EventContainer, Event, EventFlag
from core.utils.logging_utils import Logger, enable_redirection, disable_redirection

from core.utils.experiments.experiment import (
    ExperimentDefinition,
    ExperimentRunner,
)
from core.utils.experiments.action import ActionRegistry
from core.utils.experiments.builtin_actions import register_builtin_actions
from core.utils.experiments.requirement import RequirementRegistry, register_builtin_requirements
from core.utils.experiments.guard import GuardRegistry, register_builtin_guards
from core.utils.experiments.types import ExperimentStatus, ExperimentActionData


# -- Meta sub-dataclasses ------------------------------------------------------

@dataclass
class EnvironmentInfo:
    """System environment at experiment time."""
    hostname: str = ''
    os: str = ''
    architecture: str = ''
    python_version: str = ''
    user: str = ''


@dataclass
class GitInfo:
    """Git repository state at experiment time."""
    commit: str = ''
    branch: str = ''
    dirty: bool = False


@dataclass
class ExperimentResultMeta:
    """Metadata captured automatically when an experiment completes."""
    datetime: str = ''
    timestamp: float = 0.0
    environment: EnvironmentInfo = field(default_factory=EnvironmentInfo)
    git: GitInfo = field(default_factory=GitInfo)

    @classmethod
    def collect(cls, git_info: 'GitInfo | None' = None) -> 'ExperimentResultMeta':
        """Collect metadata from the current environment."""
        return cls(
            datetime=datetime.now().isoformat(),
            timestamp=time.time(),
            environment=_collect_environment(),
            git=git_info if git_info is not None else _collect_git_info(),
        )


def _collect_environment() -> EnvironmentInfo:
    return EnvironmentInfo(
        hostname=platform.node(),
        os=f"{platform.system()} {platform.release()}",
        architecture=platform.machine(),
        python_version=platform.python_version(),
        user=getpass.getuser(),
    )


def _collect_git_info() -> GitInfo:
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return GitInfo()
        commit = result.stdout.strip()
        branch = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        dirty = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() != ''
        return GitInfo(commit=commit, branch=branch, dirty=dirty)
    except Exception:
        return GitInfo()


# -- Result --------------------------------------------------------------------

@dataclass
class ExperimentResult:
    """Collected outcome of a completed experiment."""
    id: str = ''
    status: ExperimentStatus = ExperimentStatus.FINISHED
    definition: ExperimentDefinition | None = None
    meta: ExperimentResultMeta = field(default_factory=ExperimentResultMeta)
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    action_data: dict[str, ExperimentActionData] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    error_message: str = ''
    logs: list = field(default_factory=list)


@event_definition
class ExperimentWrapperEvents(EventContainer):
    started: Event
    finished: Event = Event(copy_data_on_set=False)
    message: Event = Event(flags=EventFlag('level', str), copy_data_on_set=False)


class Experiment:
    """Generic wrapper around ExperimentRunner.

    Owns an ExperimentRunner and adds wall-clock timing, lifecycle flags,
    and structured result collection via _build_result().

    Subclass and override _build_result() to attach robot-specific data
    (samples, metadata, etc.).
    """

    def __init__(self, definition: ExperimentDefinition, registry: ActionRegistry | None = None,
                 requirement_registry: RequirementRegistry | None = None,
                 guard_registry: GuardRegistry | None = None):

        if registry is None:
            registry = self._create_action_registry()
        if requirement_registry is None:
            requirement_registry = self._create_requirement_registry()
        if guard_registry is None:
            guard_registry = self._create_guard_registry()
        self._runner = ExperimentRunner(definition, registry, requirement_registry, guard_registry)
        self._initialized = False
        self._finished = False
        self._start_time: float = 0.0
        self._end_time: float = 0.0
        self._error_message: str = ''
        self._result: ExperimentResult | None = None
        self._captured_logs: list[dict] = []
        self._log_capture_active = False
        self.events = ExperimentWrapperEvents()
        self.logger = Logger(f'Experiment[{definition.id}]')

    def _create_action_registry(self) -> ActionRegistry:
        registry = ActionRegistry()
        register_builtin_actions(registry)
        return registry

    def _create_requirement_registry(self) -> RequirementRegistry:
        registry = RequirementRegistry()
        register_builtin_requirements(registry)
        return registry

    def _create_guard_registry(self) -> GuardRegistry:
        registry = GuardRegistry()
        register_builtin_guards(registry)
        return registry

    @property
    def runner(self) -> ExperimentRunner:
        return self._runner

    @property
    def definition(self) -> ExperimentDefinition:
        return self._runner.definition

    @property
    def status(self) -> ExperimentStatus | None:
        return self._runner.status

    @property
    def result(self) -> ExperimentResult | None:
        return self._result

    @property
    def finished(self) -> bool:
        return self._finished

    # ------------------------------------------------------------------------------------------------------------------
    def _log_capture_callback(self, log_entry: str, log: str, logger: Logger, level: int):
        """Redirection callback that captures log entries."""
        self._captured_logs.append({
            'entry': log_entry.strip(),
            'message': log,
            'logger': logger.name,
            'level': level,
        })

    # ------------------------------------------------------------------------------------------------------------------
    def _start_log_capture(self):
        """Enable log redirection to capture logs during the experiment."""
        if not self._log_capture_active:
            self._captured_logs = []
            enable_redirection(self._log_capture_callback, redirect_all=False)
            self._log_capture_active = True

    # ------------------------------------------------------------------------------------------------------------------
    def _stop_log_capture(self):
        """Disable log redirection."""
        if self._log_capture_active:
            disable_redirection(self._log_capture_callback)
            self._log_capture_active = False

    # ------------------------------------------------------------------------------------------------------------------
    def initialize(self, context_objects: dict[str, Any] | None = None):
        """Prepare experiment for execution.

        Records start time, initializes the runner, and emits the started event.
        If the runner fails immediately (e.g. requirements not met), collects
        the result right away.
        """
        self._start_time = time.time()
        self._start_log_capture()

        # Forward runner message events to the wrapper's message event
        self._runner.events.message.on(self._on_runner_message)

        self._runner.initialize(context_objects)

        # Runner sets _finished=True and status=ERROR when requirements fail
        if self._runner._finished:
            self._collect_result()
            return

        self._initialized = True
        self.logger.info(f"Experiment '{self.definition.id}' started")

    # ------------------------------------------------------------------------------------------------------------------
    def step(self) -> bool:
        """Advance experiment by one tick.

        Returns True when the experiment has finished.
        """
        if self._finished:
            return True
        if not self._initialized:
            self.logger.warning("step() called before initialize()")
            return False

        if self._runner.tick == 0:
            self.events.started.set()

        runner_finished = self._runner.step()

        if runner_finished:
            self._collect_result()

        return self._finished

    # ------------------------------------------------------------------------------------------------------------------
    def abort(self, reason: str = ''):
        """Abort the experiment with an optional reason."""
        self._error_message = reason
        self._runner.abort(reason)
        if not self._finished:
            self._collect_result()

    # ------------------------------------------------------------------------------------------------------------------
    def _collect_result(self):
        """Finalize the experiment: mark finished immediately, build result in background thread."""
        self._end_time = time.time()
        self._stop_log_capture()
        self._finished = True
        threading.Thread(target=self._collect_result_worker, daemon=True).start()

    # ------------------------------------------------------------------------------------------------------------------
    def _collect_result_worker(self):
        """Build result and emit finished event (runs in background thread)."""
        try:
            self._result = self._build_result()
        except Exception as e:
            self.logger.error(f"Failed to build experiment result: {e}")
        self.events.finished.set(data=self._result)
        self.logger.info(f"Experiment '{self.definition.id}' finished: {self._runner.status}")

    # ------------------------------------------------------------------------------------------------------------------
    def _on_runner_message(self, data=None, *args, **kwargs):
        """Forward runner message events to the wrapper's message event."""
        if data:
            self.events.message.set(data=data, flags={'level': data.get('level', 'info')})

    def _build_result(self) -> ExperimentResult:
        """Build the result object. Override in subclasses for extra data."""
        return ExperimentResult(
            id=self.definition.id,
            status=self._runner.status or ExperimentStatus.ERROR,
            definition=self.definition,
            meta=ExperimentResultMeta.collect(),
            start_time=self._start_time,
            end_time=self._end_time,
            duration=self._end_time - self._start_time,
            action_data=dict(self._runner.action_data),
            variables=dict(self._runner.variables),
            error_message=self._error_message,
            logs=self._captured_logs,
        )
