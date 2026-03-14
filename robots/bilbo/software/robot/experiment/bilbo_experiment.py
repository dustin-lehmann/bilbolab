"""BILBO-specific experiment wrapper.

Extends the generic Experiment with robot handle, tick-based sample collection,
and BILBO metadata (control config, testbed config, timecode).
"""

import time
from dataclasses import dataclass, field
from typing import Any

from core.utils.experiments.experiment_wrapper import Experiment, ExperimentResult, ExperimentResultMeta
from core.utils.experiments.experiment import ExperimentDefinition
from core.utils.experiments.action import ActionRegistry
from core.utils.experiments.requirement import RequirementRegistry
from core.utils.experiments.guard import GuardRegistry
from core.utils.experiments.types import ExperimentStatus
from core.utils.logging_utils import Logger

from robot.bilbo_common import BILBO_Common
from robot.experiment.actions import register_bilbo_actions, register_bilbo_requirements, register_bilbo_guards
import multiprocessing as mp
from robot.core import get_logging_provider
from robot.lowlevel.stm32_general import BILBO_CONTROL_DT


@dataclass
class BILBO_ExperimentContext:
    """Robot-specific context captured at experiment start/end."""
    description: str = ''
    start_timecode: str | None = None
    control_config: Any = None
    bilbo_config: Any = None
    testbed_config: Any = None


@dataclass
class BILBO_ExperimentResult(ExperimentResult):
    """Extended result with robot samples and context."""
    samples: list = field(default_factory=list)
    robot_context: BILBO_ExperimentContext | None = None
    start_tick: int = 0
    end_tick: int = 0


class BILBO_Experiment(Experiment):
    """BILBO-specific experiment wrapper.

    Extends the generic Experiment with:
    - Robot handle via BILBO_Common
    - Tick-based sample collection from the logging provider
    - BILBO metadata (control config, robot config, testbed, timecode)
    """

    def __init__(self, definition: ExperimentDefinition, common: BILBO_Common,
                 registry: ActionRegistry | None = None,
                 requirement_registry: RequirementRegistry | None = None,
                 guard_registry: GuardRegistry | None = None):
        self._common = common
        super().__init__(definition, registry, requirement_registry, guard_registry)
        self._start_tick: int = 0
        self._end_tick: int = 0
        self._start_timecode: str | None = None
        self.logger = Logger(f'BILBO_Experiment[{definition.id}]')

    def _create_action_registry(self) -> ActionRegistry:
        registry = super()._create_action_registry()
        register_bilbo_actions(registry)
        return registry

    def _create_requirement_registry(self) -> RequirementRegistry:
        registry = super()._create_requirement_registry()
        register_bilbo_requirements(registry)
        return registry

    def _create_guard_registry(self) -> GuardRegistry:
        registry = super()._create_guard_registry()
        register_bilbo_guards(registry)
        return registry

    @property
    def robot(self):
        return self._common.bilbo

    # ------------------------------------------------------------------------------------------------------------------
    def initialize(self, context_objects: dict[str, Any] | None = None):
        """Initialize with robot as default context object."""
        objects = {'robot': self._common.bilbo}
        if context_objects:
            objects.update(context_objects)

        super().initialize(objects)

    # ------------------------------------------------------------------------------------------------------------------
    def step(self) -> bool:
        """Advance experiment by one tick. Captures start_tick on the first call
        so that it aligns with the actual SPI sample tick (avoids stale tick from initialize)."""
        if self._start_tick == 0:
            self._start_tick = self._common.tick
            self._start_time = time.time()
            timecode = self._common.get_timecode()
            self._start_timecode = timecode.to_string() if timecode is not None else None
            self.logger.info(f"Starting experiment at tick {self._start_tick} (timecode: {self._start_timecode})")
        return super().step()

    # ------------------------------------------------------------------------------------------------------------------
    def _collect_result(self):
        """Record end tick before building result."""
        self._end_tick = self._common.tick

        super()._collect_result()


    # ------------------------------------------------------------------------------------------------------------------
    def _build_result(self) -> BILBO_ExperimentResult:
        """Build BILBO-specific result without samples.

        Samples are added later by save_result_to_file() in a subprocess,
        so the large sample data never crosses a process boundary via pickle.
        """
        robot_context = self._collect_robot_context()

        return BILBO_ExperimentResult(
            id=self.definition.id,
            status=self._runner.status or ExperimentStatus.ERROR,
            definition=self.definition,
            meta=ExperimentResultMeta.collect(git_info=self._common.git_info),
            start_time=self._start_time,
            end_time=self._end_time,
            duration=self._end_time - self._start_time,
            action_data=dict(self._runner.action_data),
            variables=dict(self._runner.variables),
            error_message=self._error_message,
            logs=self._captured_logs,
            samples=[],
            robot_context=robot_context,
            start_tick=self._start_tick,
            end_tick=self._end_tick,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def save_result_to_file(self, filepath: str, timeout: float = 60.0) -> bool:
        """Save experiment result with H5 samples to JSON in a single subprocess.

        Reads samples from H5, attaches them to the result, and writes JSON — all
        in one subprocess so ~10k sample dicts never cross a process boundary.
        """

        # Wait for logger to catch up past end tick, then flush once
        deadline = time.time() + 2.0
        while self._common.tick < (self._end_tick + 50) and time.time() < deadline:
            time.sleep(0.05)

        try:
            self._common.flush_logs()
        except Exception as e:
            self.logger.warning(f"Failed to flush logs: {e}")

        # Get H5 file paths

        logging_provider = get_logging_provider()
        hl_filename = logging_provider._h5_logger_sample.filename
        ll_filename = logging_provider._h5_logger_lowlevel.filename
        base_tick = logging_provider.base_tick

        # Lazy import to avoid circular dependency
        from robot.logging.bilbo_logging import _save_experiment_with_samples_worker

        ctx = mp.get_context('spawn')
        proc = ctx.Process(
            target=_save_experiment_with_samples_worker,
            args=(self._result, hl_filename, ll_filename,
                  self._start_tick, self._end_tick, BILBO_CONTROL_DT, filepath,
                  base_tick),
            daemon=True,
        )
        proc.start()
        proc.join(timeout=timeout)

        if proc.is_alive():
            self.logger.error(f"save_result_to_file timed out ({timeout}s)")
            proc.kill()
            return False
        if proc.exitcode != 0:
            self.logger.error(f"save_result_to_file failed (exit code {proc.exitcode})")
            return False

        self.logger.info(f"Experiment result saved to {filepath}")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _collect_robot_context(self) -> BILBO_ExperimentContext:
        """Collect robot/control/testbed context."""
        control_config = None
        try:
            control_config = self._common.bilbo.control.get_control_config()
        except Exception as e:
            self.logger.warning(f"Failed to get control config: {e}")

        return BILBO_ExperimentContext(
            description=self.definition.description,
            start_timecode=self._start_timecode,
            control_config=control_config,
            bilbo_config=self._common.config,
            testbed_config=self._common.bilbo.testbed_manager.get_data(),
        )
