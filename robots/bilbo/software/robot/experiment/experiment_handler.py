from __future__ import annotations

import ctypes
import dataclasses
import enum
import json
import os
import threading
import time
from datetime import datetime
from typing import Any

from core.utils.experiments import (
    ExperimentDefinition, ExperimentParser, ExperimentStatus, ActionStatus,
)
from core.communication.wifi.bilbolab_wifi_interface import (
    wifi_event_definition, WifiEventContainer, WifiEvent,
)
from core.communication.wifi.data_link import CommandArgument
from core.utils.dataclass_utils import from_dict_auto, asdict_optimized
from core.utils.events import (
    event_definition, EventContainer, Event, EventFlag, pred_flag_equals,
    wait_for_events, OR, TIMEOUT
)
from core.utils.logging_utils import Logger
from core.utils.thread_utils import run_in_thread
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.communication.serial.bilbo_serial_messages import BILBO_Sequencer_Event_Message
from robot.control.bilbo_control import BILBO_Control
from robot.control.bilbo_control_definitions import BILBO_Control_Mode
from robot.core import get_logging_provider
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment.definitions import (
    BILBO_InputTrajectory, BILBO_TrajectoryData, BILBO_StateTrajectory,
    BILBO_TrajectoryExperimentData, BILBO_TrajectoryExperimentMeta,
    BILBO_LL_Sequencer_Event_Type, BILBO_ExperimentHandler_Sample
)
from robot.experiment.bilbo_experiment import BILBO_Experiment, BILBO_ExperimentResult, BILBO_ExperimentContext
from robot.experiment.helpers import get_state_trajectory_from_lowlevel_samples
from robot.interfaces.bilbo_interfaces import BILBO_Interfaces
from robot.paths import EXPERIMENTS_PATH
from robot.lowlevel.stm32_general import LOOP_TIME_CONTROL
from robot.lowlevel.stm32_sequencer import bilbo_sequence_description_t, bilbo_sequence_input_t, BILBO_Sequence_LL
from robot.testbed.bilbo_testbed_manager import BILBO_TestbedManager
from robot.utilities.bilbo_utilities import BILBO_Utilities
import robot.lowlevel.stm32_addresses as addresses

LOWLEVEL_STATE_SIGNALS = [
    'estimation.state.v',
    'estimation.state.theta',
    'estimation.state.theta_dot',
    'estimation.state.psi_dot'
]


# ======================================================================================================================
# Events and Status Enums
# ======================================================================================================================

@event_definition
class BILBO_ExperimentHandler_Events(EventContainer):
    experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_finished: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_error: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_timeout: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)

    trajectory_started: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)
    trajectory_finished: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)
    trajectory_aborted: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)

    error: Event


class BILBO_ExperimentHandler_Status(enum.StrEnum):
    IDLE = 'IDLE'
    LOADING = 'LOADING'
    EXPERIMENT = 'EXPERIMENT'
    TRAJECTORY = 'TRAJECTORY'
    ERROR = 'ERROR'


class BILBO_ExperimentHandler_TrajectoryStatus(enum.StrEnum):
    IDLE = 'IDLE'
    RUNNING = 'RUNNING'


@dataclasses.dataclass
class ExperimentMarker:
    id: str
    value: Any
    hold: bool = False


_EXPERIMENT_WIFI_EVENT = WifiEvent(data_type=dict)


@wifi_event_definition
class ExperimentWifiEvents(WifiEventContainer):
    loaded: WifiEvent = _EXPERIMENT_WIFI_EVENT
    started: WifiEvent = _EXPERIMENT_WIFI_EVENT
    finished: WifiEvent = _EXPERIMENT_WIFI_EVENT
    error: WifiEvent = _EXPERIMENT_WIFI_EVENT
    timeout: WifiEvent = _EXPERIMENT_WIFI_EVENT
    message: WifiEvent = _EXPERIMENT_WIFI_EVENT
    action_started: WifiEvent = _EXPERIMENT_WIFI_EVENT
    action_finished: WifiEvent = _EXPERIMENT_WIFI_EVENT
    trajectory_finished: WifiEvent = _EXPERIMENT_WIFI_EVENT
    trajectory_aborted: WifiEvent = _EXPERIMENT_WIFI_EVENT


# ======================================================================================================================
# Experiment Handler
# ======================================================================================================================

class BILBO_ExperimentHandler:
    @event_definition
    class InternalEvents(EventContainer):
        trajectory_loaded: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)
        trajectory_started: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)
        trajectory_finished: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)
        trajectory_aborted: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)

    status: BILBO_ExperimentHandler_Status = BILBO_ExperimentHandler_Status.IDLE
    trajectory_status: BILBO_ExperimentHandler_TrajectoryStatus = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
    events: BILBO_ExperimentHandler_Events

    active_experiment: BILBO_Experiment | None = None
    active_trajectory: BILBO_InputTrajectory | None = None

    action_event: Event

    # === INIT =========================================================================================================
    def __init__(self, common: BILBO_Common,
                 communication: BILBO_Communication,
                 estimation: BILBO_Estimation,
                 interfaces: BILBO_Interfaces,
                 utilities: BILBO_Utilities,
                 control: BILBO_Control,
                 testbed: BILBO_TestbedManager
                 ):
        self.common = common
        self.communication = communication
        self.estimation = estimation
        self.interfaces = interfaces
        self.utilities = utilities
        self.control = control
        self.testbed = testbed

        self.logger = Logger('Experiment Handler', "DEBUG")
        self.events = BILBO_ExperimentHandler_Events()
        self.wifi_events = ExperimentWifiEvents(wifi=communication.wifi.wifi, id='experiment')
        self._internal_events = BILBO_ExperimentHandler.InternalEvents()
        self.action_event = Event(flags=EventFlag('id', str))
        self.markers = {}
        self._active_dilc_experiment = None
        self._active_iitl_experiment = None
        self._active_iml_experiment = None

        self.common.callbacks.end_of_step.register(self._end_of_step_callback)

        # Stop running experiment when the stop interaction event is received
        self.common.interaction_events.stop.on(self._on_stop_interaction_event)

        self.communication.serial.callbacks.event.register(self._sequencer_event_callback,
                                                           parameters={'messages': [BILBO_Sequencer_Event_Message]})

        # ── WiFi Commands ─────────────────────────────────────────────────────

        self.communication.wifi.newCommand(
            identifier='run_experiment',
            function=self._run_experiment_external,
            arguments=[
                CommandArgument(
                    name='experiment',
                    type=dict,
                    optional=False,
                    description="Experiment definition"
                )
            ],
            description="Start an experiment from definition dict",
        )

        self.communication.wifi.newCommand(
            identifier='stop_experiment',
            function=self.stop_experiment,
            arguments=[
                CommandArgument(
                    name='reason',
                    type=str,
                    optional=True,
                    default='Host stop request',
                    description="Reason for stopping the experiment"
                )
            ],
            description="Stop the currently running experiment",
        )

        self.communication.wifi.newCommand(
            identifier='run_trajectory',
            function=self._run_trajectory_external,
            arguments=[
                CommandArgument(
                    name='trajectory_data',
                    type=dict,
                    optional=False,
                    description="Trajectory definition"
                )
            ]
        )

        self.communication.wifi.newCommand(
            identifier='run_dilc_experiment',
            function=self._run_dilc_experiment_external,
            arguments=[
                CommandArgument(
                    name='settings',
                    type=dict,
                    optional=False,
                    description="DILC experiment settings"
                )
            ],
            description="Start a DILC experiment (blocking, runs in thread)",
        )

        self.communication.wifi.newCommand(
            identifier='run_limbobar_dilc_experiment',
            function=self._run_limbobar_dilc_experiment_external,
            arguments=[
                CommandArgument(
                    name='settings',
                    type=dict,
                    optional=False,
                    description="LimboBar DILC experiment settings"
                )
            ],
            description="Start a LimboBar DILC experiment (blocking, runs in thread)",
        )

        self.communication.wifi.newCommand(
            identifier='run_snr_dilc_experiment',
            function=self._run_snr_dilc_experiment_external,
            arguments=[
                CommandArgument(
                    name='settings',
                    type=dict,
                    optional=False,
                    description="SNR DILC experiment settings"
                )
            ],
            description="Start an SNR-adaptive DILC experiment (blocking, runs in thread)",
        )

        self.communication.wifi.newCommand(
            identifier='run_cooperative_dilc_experiment',
            function=self._run_cooperative_dilc_experiment_external,
            arguments=[
                CommandArgument(
                    name='settings',
                    type=dict,
                    optional=False,
                    description="Cooperative DILC experiment settings"
                )
            ],
            description="Start a cooperative (multi-agent) DILC experiment (blocking, runs in thread)",
        )

        self.communication.wifi.newCommand(
            identifier='set_dilc_auto_start_trials',
            function=self._set_dilc_auto_start_trials,
            arguments=[
                CommandArgument(name='value', type=bool, optional=False,
                                description="Enable or disable auto-start of trials")
            ],
            description="Set DILC auto_start_trials during experiment",
        )

        self.communication.wifi.newCommand(
            identifier='set_dilc_auto_accept_trials',
            function=self._set_dilc_auto_accept_trials,
            arguments=[
                CommandArgument(name='value', type=bool, optional=False,
                                description="Enable or disable auto-accept of trials")
            ],
            description="Set DILC auto_accept_trials during experiment",
        )

        self.communication.wifi.newCommand(
            identifier='run_iitl_experiment',
            function=self._run_iitl_experiment_external,
            arguments=[
                CommandArgument(
                    name='settings',
                    type=dict,
                    optional=False,
                    description="IITL experiment settings"
                )
            ],
            description="Start an IITL experiment (blocking, runs in thread)",
        )

        self.communication.wifi.newCommand(
            identifier='set_iitl_auto_start_trials',
            function=self._set_iitl_auto_start_trials,
            arguments=[
                CommandArgument(name='value', type=bool, optional=False,
                                description="Enable or disable auto-start of trials")
            ],
            description="Set IITL auto_start_trials during experiment",
        )

        self.communication.wifi.newCommand(
            identifier='set_iitl_auto_accept_trials',
            function=self._set_iitl_auto_accept_trials,
            arguments=[
                CommandArgument(name='value', type=bool, optional=False,
                                description="Enable or disable auto-accept of trials")
            ],
            description="Set IITL auto_accept_trials during experiment",
        )

        self.communication.wifi.newCommand(
            identifier='run_iml_experiment',
            function=self._run_iml_experiment_external,
            arguments=[
                CommandArgument(
                    name='settings',
                    type=dict,
                    optional=False,
                    description="IML experiment settings"
                )
            ],
            description="Start an IML (model identification) experiment (blocking, runs in thread)",
        )

        self.communication.wifi.newCommand(
            identifier='set_iml_auto_start_trials',
            function=self._set_iml_auto_start_trials,
            arguments=[
                CommandArgument(name='value', type=bool, optional=False,
                                description="Enable or disable auto-start of trials")
            ],
            description="Set IML auto_start_trials during experiment",
        )

        self.communication.wifi.newCommand(
            identifier='set_iml_auto_accept_trials',
            function=self._set_iml_auto_accept_trials,
            arguments=[
                CommandArgument(name='value', type=bool, optional=False,
                                description="Enable or disable auto-accept of trials")
            ],
            description="Set IML auto_accept_trials during experiment",
        )

    # === LIFECYCLE ====================================================================================================
    def init(self):
        ...

    def start(self):
        ...

    def step(self):
        """Advance the active experiment by one tick. Called at 100 Hz from bilbo.update()."""
        if self.active_experiment is not None:
            self.active_experiment.step()

    # === TRAJECTORY EXECUTION =========================================================================================
    def run_trajectory(self, trajectory: BILBO_InputTrajectory) -> BILBO_TrajectoryExperimentData | None:
        """Run an input trajectory on the STM32 via SPI injection. BLOCKING."""

        self.control.disable_external_input()

        if self.trajectory_status == BILBO_ExperimentHandler_TrajectoryStatus.RUNNING:
            self.logger.warning(f"Trajectory {trajectory.id} is already running. Aborting.")
            return None

        if trajectory.length % 10 != 0:
            self.logger.warning(
                f"Trajectory {trajectory.id} has an invalid length ({trajectory.length}). It has to be a multiple of 10.")
            return None

        self.logger.info(f"Running trajectory {trajectory.id} ...")
        self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.RUNNING

        try:
            # 1) Load onto the low-level (STM32)
            if not self._load_trajectory_to_lowlevel(trajectory):
                self.logger.warning(f"Failed to load trajectory {trajectory.id}")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            # 2) Start on the low level. This returns False only on genuine
            # validation failures (nothing loaded / wrong id); a missing START
            # ACK is no longer treated as failure (see method docstring). Send a
            # STOP on failure so the STM32 can never be left running a sequence
            # the CM5 believes failed.
            if not self._start_loaded_trajectory_on_lowlevel(trajectory.id):
                self.logger.warning(f"Failed to start trajectory {trajectory.id}")
                try:
                    self._send_trajectory_stop_signal_to_lowlevel()
                except Exception as e:
                    self.logger.error(f"Failed to send stop signal to low-level: {e}")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            # 3) Wait for STARTED or ABORTED (early stop handling)
            data, trace = wait_for_events(
                events=OR(
                    (self._internal_events.trajectory_started, pred_flag_equals('trajectory_id', trajectory.id)),
                    (self._internal_events.trajectory_aborted, pred_flag_equals('trajectory_id', trajectory.id))
                ),
                timeout=1,
                stale_event_time=0.2,
            )

            if data is TIMEOUT:
                self.logger.warning(f"Failed to start trajectory {trajectory.id}: No start/stop event received")
                try:
                    self._send_trajectory_stop_signal_to_lowlevel()
                except Exception as e:
                    self.logger.error(f"Failed to send stop signal to low-level: {e}")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            if trace.caused_by(self._internal_events.trajectory_aborted):
                self.logger.warning(f"Trajectory {trajectory.id} aborted before start")
                self.events.trajectory_aborted.set(flags={'trajectory_id': trajectory.id})
                self.wifi_events.trajectory_aborted.send(data={'trajectory_id': trajectory.id})
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            self.utilities.beep(1000, 250, 1)
            time.sleep(0.01)
            start_tick = data.get('tick')

            if start_tick is None:
                self.logger.warning(f"Trajectory {trajectory.id}: STARTED tick missing")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            self.events.trajectory_started.set(data=start_tick, flags={'trajectory_id': trajectory.id})

            self.logger.info(f"Trajectory {trajectory.id} started at tick {start_tick}")

            # 4) Wait for FINISHED or ABORTED during execution
            run_timeout = trajectory.length * LOOP_TIME_CONTROL + 2.0

            data, trace = wait_for_events(
                events=OR(
                    (self._internal_events.trajectory_finished, pred_flag_equals('trajectory_id', trajectory.id)),
                    (self._internal_events.trajectory_aborted, pred_flag_equals('trajectory_id', trajectory.id))
                ),
                timeout=run_timeout,
                stale_event_time=0.2,
            )

            if data is TIMEOUT:
                self.logger.warning(f"Trajectory {trajectory.id} timeout: No finish/stop event received")
                try:
                    self._send_trajectory_stop_signal_to_lowlevel()
                except Exception as e:
                    self.logger.error(f"Failed to send stop signal to low-level: {e}")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            if trace.caused_by(self._internal_events.trajectory_aborted):
                self.logger.warning(f"Trajectory {trajectory.id} aborted during execution")
                self.events.trajectory_aborted.set(flags={'trajectory_id': trajectory.id})
                self.wifi_events.trajectory_aborted.send(data={'trajectory_id': trajectory.id})
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            self.utilities.beep(1000, 250, 2)
            end_tick = data.get('tick')
            if end_tick is None:
                self.logger.warning(f"Trajectory {trajectory.id}: FINISHED tick missing")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            # 5) Let the logger catch up a little beyond end_tick
            while self.common.tick < (end_tick + 100):
                time.sleep(0.1)

            # 6) Read signals from the logging provider
            lowlevel_signals = get_logging_provider().get_lowlevel_data(
                signals=LOWLEVEL_STATE_SIGNALS,
                start=start_tick,
                end=end_tick
            )

            output_data = BILBO_TrajectoryData(
                input_trajectory=trajectory,
                state_trajectory=BILBO_StateTrajectory(
                    states=get_state_trajectory_from_lowlevel_samples(lowlevel_signals)
                )
            )

            trajectory_experiment_data = BILBO_TrajectoryExperimentData(
                id=str(trajectory.id),
                data=output_data,
                meta=BILBO_TrajectoryExperimentMeta(
                    robot_id=self.common.id,
                    description='',
                    time_stamp=datetime.now().isoformat(),
                    robot_config=self.common.config,
                    control_config=self.control.get_control_config(),
                    start_tick=start_tick,
                    end_tick=end_tick,
                ),
            )

            self.events.trajectory_finished.set(data=trajectory_experiment_data, flags={'trajectory_id': trajectory.id})

            self.logger.info(f"Trajectory {trajectory.id} finished at tick {end_tick}")

            # 7) Send the trajectory-finished event via Wi-Fi
            self.wifi_events.trajectory_finished.send(data={
                'trajectory_id': trajectory.id,
                'data': trajectory_experiment_data,
            })

            self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
            return trajectory_experiment_data

        finally:
            self.control.enable_external_input()

    # === EXPERIMENTS ==================================================================================================
    def run_experiment(self, definition: ExperimentDefinition) -> bool:
        """Initialize and activate an experiment. Non-blocking — stepping happens in _end_of_step_callback."""

        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            self.logger.warning(f"Cannot start experiment: handler status is \"{self.status}\"")
            return False

        if self.active_experiment is not None:
            self.logger.warning("Cannot start experiment: another experiment is already active")
            return False

        # Transition to LOADING immediately to block concurrent requests
        self.status = BILBO_ExperimentHandler_Status.LOADING
        self.wifi_events.loaded.send(data={
            'experiment_id': definition.id,
        })

        experiment = BILBO_Experiment(
            definition=definition,
            common=self.common,
        )

        # Wire experiment messages to WiFi before initialize (guards emit messages during setup).
        # Use a closure capturing `experiment` directly so messages are forwarded even before
        # self.active_experiment is set (which happens after initialize).
        exp_id = definition.id
        def _forward_message(data=None, *args, **kwargs):
            if not data:
                return
            self.wifi_events.message.send(data={
                'experiment_id': exp_id,
                'text': data.get('text', ''),
                'level': data.get('level', 'info'),
            })
        experiment.events.message.on(_forward_message)

        experiment.initialize()

        experiment.events.started.on(self._on_experiment_started, once=True)

        # If requirements failed, the experiment finishes immediately during initialize
        if experiment.finished:
            self.logger.error(f"Experiment \"{definition.id}\" failed during initialization")
            self.status = BILBO_ExperimentHandler_Status.IDLE
            result = experiment.result
            error_msg = result.error_message if result else 'Unknown initialization error'
            self.wifi_events.error.send(data={
                'experiment_id': definition.id,
                'data': None,
                'error_message': error_msg,
            })
            self.events.experiment_error.set(flags={'experiment_id': definition.id})
            return False

        # Wire finished event (handles all outcomes: success, error, timeout, stop)
        experiment.events.finished.on(self._on_experiment_finished, once=True)

        # Wire action-level events for host progress tracking
        experiment.runner.callbacks.action_started.register(self._on_action_started)
        experiment.runner.callbacks.action_finished.register(self._on_action_finished)

        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT
        self.wifi_events.started.send(data={
            'experiment_id': definition.id,
            'actions': [{'id': a.id, 'type': a.type, 'params': a.params} for a in definition.actions],
        })
        self.events.experiment_started.set(flags={'experiment_id': definition.id})

        time.sleep(0.1)  # Let host display update

        self.active_experiment = experiment
        self.logger.info(f"Experiment \"{definition.id}\" activated")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _run_experiment_external(self, experiment: dict) -> bool:
        """WiFi command handler: parse experiment dict and start it."""
        try:
            definition = ExperimentParser.from_dict(experiment)
        except Exception as e:
            self.logger.error(f"Failed to parse experiment definition: {e}")
            return False
        return self.run_experiment(definition)

    # ------------------------------------------------------------------------------------------------------------------
    def stop_experiment(self, reason: str = "Host stop request") -> bool:
        """Stop the currently running experiment."""
        if self.active_experiment is None:
            self.logger.info("No experiment running to stop")
            return False
        experiment_id = self.active_experiment.definition.id
        self.logger.warning(f"Stopping experiment \"{experiment_id}\": {reason}")
        self.active_experiment.abort(reason=reason)
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _on_stop_interaction_event(self, *args, **kwargs):
        """Handle the stop interaction event (button press or WiFi command)."""
        self.stop_experiment(reason="Stop interaction event")

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_started(self, *args, **kwargs):
        self.common.board.beep(frequency=1000, time_ms=500, repeats=1)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_finished(self, result: BILBO_ExperimentResult = None, *args, **kwargs):
        """Handle experiment completion (success, error, timeout, stop).

        Cleans up handler state immediately so the robot remains responsive,
        then saves result and notifies host in a background thread.
        """
        experiment_id = result.id if result else "unknown"
        status = result.status if result else ExperimentStatus.ERROR

        self.logger.info(f"Experiment \"{experiment_id}\" finished with status: {status}")

        if status == ExperimentStatus.ABORTED or status == ExperimentStatus.ERROR:
            self.common.board.beep(frequency=400, time_ms=500, repeats=3)
        elif status == ExperimentStatus.FINISHED:
            self.common.board.beep(frequency=1000, time_ms=500, repeats=2)
        else:
            ...

        # Grab experiment reference before cleanup
        experiment = self.active_experiment

        # Clean up IMMEDIATELY so the handler accepts new commands
        self.active_experiment = None
        self.status = BILBO_ExperimentHandler_Status.IDLE

        # Save result and send WiFi events in background thread so we don't
        # block the robot if the save subprocess hangs
        threading.Thread(
            target=self._save_and_notify,
            args=(experiment, result, experiment_id, status),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------------------------------------------------------
    def _save_and_notify(self, experiment, result, experiment_id, status):
        """Save experiment result to file and send WiFi events (runs in background thread)."""
        filepath = None
        if result is not None and experiment is not None:
            timestamp = datetime.fromtimestamp(result.start_time).strftime("%Y-%m-%d_%H-%M-%S")
            suffix = f"_{status.value}" if status != ExperimentStatus.FINISHED else ""
            filename = f"{experiment_id}_{timestamp}{suffix}.json"
            filepath = os.path.join(EXPERIMENTS_PATH, filename)
            os.makedirs(EXPERIMENTS_PATH, exist_ok=True)
            if not experiment.save_result_to_file(filepath):
                self.logger.error(f"Failed to save experiment result to {filepath}")
                filepath = None

        # Emit local events
        if status == ExperimentStatus.FINISHED:
            self.events.experiment_finished.set(flags={'experiment_id': experiment_id})
        elif status == ExperimentStatus.TIMEOUT:
            self.events.experiment_timeout.set(flags={'experiment_id': experiment_id})
        else:
            self.events.experiment_error.set(flags={'experiment_id': experiment_id})

        # Send WiFi event based on status
        wifi_data = {'experiment_id': experiment_id, 'data': filepath}
        if status == ExperimentStatus.FINISHED:
            self.wifi_events.finished.send(data=wifi_data)
        elif status == ExperimentStatus.TIMEOUT:
            self.wifi_events.timeout.send(data=wifi_data)
        else:
            wifi_data['error_message'] = result.error_message if result else ''
            self.wifi_events.error.send(data=wifi_data)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_started(self, action_id: str, *args, **kwargs):
        """Forward runner action_started event to host via WiFi."""
        if self.active_experiment is None:
            return

        # Get action type from the runner's action data
        action_type = ''
        if action_id and action_id in self.active_experiment.runner.action_data:
            action_type = self.active_experiment.runner.action_data[action_id].action_type

        self.wifi_events.action_started.send(data={
            'experiment_id': self.active_experiment.definition.id,
            'action_id': action_id,
            'action_type': action_type,
        })

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_finished(self, action_id: str, *args, **kwargs):
        """Forward runner action_finished event to host via WiFi."""
        if self.active_experiment is None:
            return

        # Get action details from the runner's action data
        action_type = ''
        action_status = ''
        if action_id and action_id in self.active_experiment.runner.action_data:
            entry = self.active_experiment.runner.action_data[action_id]
            action_type = entry.action_type
            action_status = entry.status.value if entry.status else ''

        self.wifi_events.action_finished.send(data={
            'experiment_id': self.active_experiment.definition.id,
            'action_id': action_id,
            'action_type': action_type,
            'action_status': action_status,
        })

    # === SAMPLE =======================================================================================================
    def get_sample_dict(self) -> dict:
        if self.active_experiment is not None:
            exp = self.active_experiment
            runner = exp.runner if hasattr(exp, 'runner') else None
            running = [sid for sid, s in runner._action_states.items()
                       if s.status == ActionStatus.RUNNING] if runner and hasattr(runner, '_action_states') else []
            experiment_sub = {
                'id': exp.definition.id,
                'tick': exp.tick if hasattr(exp, 'tick') else -1,
                'actions': running if running else [""],
            }
        else:
            experiment_sub = {
                'id': "",
                'tick': -1,
                'actions': [""],
            }

        sample = {
            'status': self.status.value,
            'experiment_id': self.active_experiment.definition.id if self.active_experiment is not None else "",
            'trajectory_id': str(self.active_trajectory.id) if self.active_trajectory is not None else "",
            'markers_json': json.dumps([(marker.id, marker.value) for marker in self.markers.values()]),
            'experiment': experiment_sub,
        }
        return sample

    # === DILC EXPERIMENTS =============================================================================================
    def run_dilc_experiment(self, settings):
        """Run a DILC experiment. BLOCKING."""
        from robot.experiment.trial_experiments.dilc import DILC_Experiment

        experiment = DILC_Experiment(
            common=self.common,
            estimation=self.estimation,
            control=self.control,
            communication=self.communication,
            interfaces=self.interfaces,
            experiment_handler=self,
            settings=settings,
        )
        self._active_dilc_experiment = experiment
        try:
            return experiment.run()
        finally:
            self._active_dilc_experiment = None

    def run_limbobar_dilc_experiment(self, settings):
        """Run a LimboBar DILC experiment. BLOCKING."""
        from robot.experiment.trial_experiments.limbobar_dilc import LimboBar_DILC_Experiment

        experiment = LimboBar_DILC_Experiment(
            common=self.common,
            estimation=self.estimation,
            control=self.control,
            communication=self.communication,
            interfaces=self.interfaces,
            experiment_handler=self,
            settings=settings,
        )
        self._active_dilc_experiment = experiment
        try:
            return experiment.run()
        finally:
            self._active_dilc_experiment = None

    # === WIFI HANDLERS ================================================================================================
    def _set_dilc_auto_start_trials(self, value: bool) -> bool:
        if self._active_dilc_experiment is None:
            self.logger.warning("No active DILC experiment — cannot set auto_start_trials")
            return False
        self._active_dilc_experiment.set_auto_start_trials(value)
        return True

    def _set_dilc_auto_accept_trials(self, value: bool) -> bool:
        if self._active_dilc_experiment is None:
            self.logger.warning("No active DILC experiment — cannot set auto_accept_trials")
            return False
        self._active_dilc_experiment.set_auto_accept_trials(value)
        return True

    def _run_dilc_experiment_external(self, settings: dict) -> bool:
        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            self.logger.warning(f"Cannot start DILC experiment: handler is {self.status}")
            return False

        from robot.experiment.trial_experiments.dilc import DILC_Experiment_Settings

        try:
            dilc_settings = from_dict_auto(DILC_Experiment_Settings, settings)
            self.logger.info(f"Received DILC experiment request: {dilc_settings.id}")
        except Exception as e:
            self.logger.error(f"Failed to parse DILC experiment settings: {e}")
            return False

        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT
        run_in_thread(self._run_dilc_experiment_thread, dilc_settings)
        return True

    def _run_dilc_experiment_thread(self, settings):
        try:
            self.run_dilc_experiment(settings)
        finally:
            self.status = BILBO_ExperimentHandler_Status.IDLE

    # === SNR DILC EXPERIMENTS =========================================================================================
    def run_snr_dilc_experiment(self, settings):
        """Run an SNR-adaptive DILC experiment. BLOCKING."""
        from robot.experiment.trial_experiments.snr_dilc import SNR_DILC_Experiment

        experiment = SNR_DILC_Experiment(
            common=self.common,
            estimation=self.estimation,
            control=self.control,
            communication=self.communication,
            interfaces=self.interfaces,
            experiment_handler=self,
            settings=settings,
        )
        self._active_dilc_experiment = experiment
        try:
            return experiment.run()
        finally:
            self._active_dilc_experiment = None

    def _run_snr_dilc_experiment_external(self, settings: dict) -> bool:
        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            self.logger.warning(f"Cannot start SNR DILC experiment: handler is {self.status}")
            return False

        from robot.experiment.trial_experiments.snr_dilc import SNR_DILC_Experiment_Settings

        try:
            snr_settings = from_dict_auto(SNR_DILC_Experiment_Settings, settings)
            self.logger.info(f"Received SNR DILC experiment request: {snr_settings.id}")
        except Exception as e:
            self.logger.error(f"Failed to parse SNR DILC experiment settings: {e}")
            return False

        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT
        run_in_thread(self._run_snr_dilc_experiment_thread, snr_settings)
        return True

    def _run_snr_dilc_experiment_thread(self, settings):
        try:
            self.run_snr_dilc_experiment(settings)
        finally:
            self.status = BILBO_ExperimentHandler_Status.IDLE

    # === COOPERATIVE DILC EXPERIMENTS =================================================================================
    def run_cooperative_dilc_experiment(self, settings):
        """Run a cooperative (multi-agent, single-robot) DILC experiment. BLOCKING."""
        from robot.experiment.trial_experiments.cooperative_dilc import CooperativeDILC_Experiment

        experiment = CooperativeDILC_Experiment(
            common=self.common,
            estimation=self.estimation,
            control=self.control,
            communication=self.communication,
            interfaces=self.interfaces,
            experiment_handler=self,
            settings=settings,
        )
        self._active_dilc_experiment = experiment
        try:
            return experiment.run()
        finally:
            self._active_dilc_experiment = None

    def _run_cooperative_dilc_experiment_external(self, settings: dict) -> bool:
        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            self.logger.warning(f"Cannot start cooperative DILC experiment: handler is {self.status}")
            return False

        from robot.experiment.trial_experiments.cooperative_dilc import CooperativeDILC_Experiment_Settings

        try:
            coop_settings = from_dict_auto(CooperativeDILC_Experiment_Settings, settings)
            self.logger.info(f"Received cooperative DILC experiment request: {coop_settings.id}")
        except Exception as e:
            self.logger.error(f"Failed to parse cooperative DILC experiment settings: {e}")
            return False

        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT
        run_in_thread(self._run_cooperative_dilc_experiment_thread, coop_settings)
        return True

    def _run_cooperative_dilc_experiment_thread(self, settings):
        try:
            self.run_cooperative_dilc_experiment(settings)
        finally:
            self.status = BILBO_ExperimentHandler_Status.IDLE

    # === IITL EXPERIMENTS =============================================================================================
    def run_iitl_experiment(self, settings):
        """Run an IITL experiment. BLOCKING."""
        from robot.experiment.trial_experiments.iitl import IITL_Experiment

        experiment = IITL_Experiment(
            common=self.common,
            estimation=self.estimation,
            control=self.control,
            communication=self.communication,
            interfaces=self.interfaces,
            experiment_handler=self,
            settings=settings,
        )
        self._active_iitl_experiment = experiment
        try:
            return experiment.run()
        finally:
            self._active_iitl_experiment = None

    def _set_iitl_auto_start_trials(self, value: bool) -> bool:
        if self._active_iitl_experiment is None:
            self.logger.warning("No active IITL experiment — cannot set auto_start_trials")
            return False
        self._active_iitl_experiment.set_auto_start_trials(value)
        return True

    def _set_iitl_auto_accept_trials(self, value: bool) -> bool:
        if self._active_iitl_experiment is None:
            self.logger.warning("No active IITL experiment — cannot set auto_accept_trials")
            return False
        self._active_iitl_experiment.set_auto_accept_trials(value)
        return True

    def _run_iitl_experiment_external(self, settings: dict) -> bool:
        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            self.logger.warning(f"Cannot start IITL experiment: handler is {self.status}")
            return False

        from robot.experiment.trial_experiments.iitl import IITL_Experiment_Settings

        try:
            iitl_settings = from_dict_auto(IITL_Experiment_Settings, settings)
            self.logger.info(f"Received IITL experiment request: {iitl_settings.id}")
        except Exception as e:
            self.logger.error(f"Failed to parse IITL experiment settings: {e}")
            return False

        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT
        run_in_thread(self._run_iitl_experiment_thread, iitl_settings)
        return True

    def _run_iitl_experiment_thread(self, settings):
        try:
            self.run_iitl_experiment(settings)
        finally:
            self.status = BILBO_ExperimentHandler_Status.IDLE

    # === IML EXPERIMENTS ==============================================================================================
    def run_iml_experiment(self, settings):
        """Run an IML (model identification) experiment. BLOCKING."""
        from robot.experiment.trial_experiments.iml import IML_Experiment

        experiment = IML_Experiment(
            common=self.common,
            estimation=self.estimation,
            control=self.control,
            communication=self.communication,
            interfaces=self.interfaces,
            experiment_handler=self,
            settings=settings,
        )
        self._active_iml_experiment = experiment
        try:
            return experiment.run()
        finally:
            self._active_iml_experiment = None

    def _set_iml_auto_start_trials(self, value: bool) -> bool:
        if self._active_iml_experiment is None:
            self.logger.warning("No active IML experiment — cannot set auto_start_trials")
            return False
        self._active_iml_experiment.set_auto_start_trials(value)
        return True

    def _set_iml_auto_accept_trials(self, value: bool) -> bool:
        if self._active_iml_experiment is None:
            self.logger.warning("No active IML experiment — cannot set auto_accept_trials")
            return False
        self._active_iml_experiment.set_auto_accept_trials(value)
        return True

    def _run_iml_experiment_external(self, settings: dict) -> bool:
        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            self.logger.warning(f"Cannot start IML experiment: handler is {self.status}")
            return False

        from robot.experiment.trial_experiments.iml import IML_Experiment_Settings

        try:
            iml_settings = from_dict_auto(IML_Experiment_Settings, settings)
            self.logger.info(f"Received IML experiment request: {iml_settings.id}")
        except Exception as e:
            self.logger.error(f"Failed to parse IML experiment settings: {e}")
            return False

        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT
        run_in_thread(self._run_iml_experiment_thread, iml_settings)
        return True

    def _run_iml_experiment_thread(self, settings):
        try:
            self.run_iml_experiment(settings)
        finally:
            self.status = BILBO_ExperimentHandler_Status.IDLE

    def _run_limbobar_dilc_experiment_external(self, settings: dict) -> bool:
        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            self.logger.warning(f"Cannot start LimboBar DILC experiment: handler is {self.status}")
            return False

        from robot.experiment.trial_experiments.limbobar_dilc import LimboBar_DILC_Experiment_Settings

        try:
            settings_parsed = from_dict_auto(LimboBar_DILC_Experiment_Settings, settings)
            self.logger.info(f"Received LimboBar DILC experiment request: {settings_parsed.id}")
        except Exception as e:
            self.logger.error(f"Failed to parse LimboBar DILC experiment settings: {e}")
            return False

        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT
        run_in_thread(self._run_limbobar_dilc_experiment_thread, settings_parsed)
        return True

    def _run_limbobar_dilc_experiment_thread(self, settings):
        try:
            self.run_limbobar_dilc_experiment(settings)
        finally:
            self.status = BILBO_ExperimentHandler_Status.IDLE

    def _run_trajectory_external(self, trajectory_data: dict) -> bool:
        try:
            trajectory = from_dict_auto(BILBO_InputTrajectory, trajectory_data)
        except Exception as e:
            self.logger.error(f"Failed to parse trajectory: {e}")
            return False

        run_in_thread(self.run_trajectory, trajectory)
        return True

    # === LOW-LEVEL TRAJECTORY METHODS =================================================================================
    def _load_trajectory_to_lowlevel(self, trajectory: BILBO_InputTrajectory) -> bool:
        self.logger.debug(f"Loading trajectory {trajectory.id} to STM32 ... ")

        if trajectory.length != len(trajectory.inputs):
            self.logger.warning(f"Trajectory length does not match number of inputs. "
                                f"Trajectory length: {trajectory.length}, Number of inputs: {len(trajectory.inputs)}. "
                                f"Will not be loaded to STM32.")
            return False

        success = self._send_trajectory_description_to_lowlevel(trajectory)

        if not success:
            self.logger.warning("Failed to set trajectory description on STM32. Aborting trajectory load.")
            return False

        trajectory_bytes = self._trajectory_input_to_bytes(trajectory.inputs)

        self.communication.spi.sendTrajectoryData(trajectory.length, trajectory_bytes)

        data, trace = self._internal_events.trajectory_loaded.wait(timeout=0.1,
                                                                   stale_event_time=0.2,
                                                                   predicate=pred_flag_equals('trajectory_id',
                                                                                              trajectory.id)
                                                                   )

        if data is TIMEOUT:
            self.logger.warning("Failed to load trajectory. Did not receive loaded event.")
            return False

        self.logger.debug(f"Trajectory {trajectory.id} loaded successfully!")

        return True

    def _send_trajectory_description_to_lowlevel(self, trajectory: BILBO_InputTrajectory) -> bool:
        sequence_description = bilbo_sequence_description_t(
            sequence_id=trajectory.id,
            length=trajectory.length,
            require_control_mode=False,
            wait_time_beginning=1,
            wait_time_end=1,
            control_mode=BILBO_Control_Mode.BALANCING.value,
            control_mode_end=BILBO_Control_Mode.BALANCING.value,
            loaded=False
        )

        success = self.communication.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_SequencerAddresses.LOAD,
            data=sequence_description,
            input_type=bilbo_sequence_description_t,  # type: ignore
            output_type=ctypes.c_bool,
            timeout=1
        )

        return success

    @staticmethod
    def _trajectory_input_to_bytes(trajectory_input: list) -> bytes:
        ArrayType = bilbo_sequence_input_t * len(trajectory_input)  # type: ignore
        c_array = ArrayType()  # type: ignore

        for i, inp in enumerate(trajectory_input):
            c_array[i].step = i
            c_array[i].u_1 = inp.left
            c_array[i].u_2 = inp.right

        bytes_data = ctypes.string_at(ctypes.byref(c_array), ctypes.sizeof(c_array))
        return bytes_data

    def _start_loaded_trajectory_on_lowlevel(self, trajectory_id: int) -> bool:
        self.logger.debug(f"Starting trajectory {trajectory_id} on STM32 ... ")

        trajectory_data = self._read_loaded_trajectory_from_lowlevel()

        if trajectory_data is None:
            self.logger.warning("Checking loaded trajectory failed on STM32. No trajectory loaded. Aborting.")
            return False

        if trajectory_data.sequence_id != trajectory_id:
            self.logger.warning(
                f"Wrong set trajectory id. Expected {trajectory_id}, loaded: {trajectory_data.sequence_id}")
            return False

        if not trajectory_data.loaded:
            self.logger.warning(f"Trajectory {trajectory_data} is known to the STM32, but not loaded. Aborting.")
            return False

        success = self._send_trajectory_start_signal_to_lowlevel(trajectory_id)

        if not success:
            # The START register on the STM32 only validates and *queues* a start
            # request; the actual start is aligned to the 10 Hz grid and confirmed
            # asynchronously via the STARTED sequencer event. A missing/late ACK
            # (e.g. the register reply stuck behind other UART traffic) therefore
            # does NOT mean the start failed -- the firmware may well go on to run
            # the trajectory. Don't abort here; let the caller decide based on the
            # STARTED/ABORTED event (which is the authoritative signal).
            self.logger.warning(
                "START acknowledgment from STM32 missing/late; "
                "waiting for sequencer event to confirm start.")

        return True

    def _read_loaded_trajectory_from_lowlevel(self) -> BILBO_Sequence_LL | None:
        trajectory_data_struct = self.communication.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_SequencerAddresses.READ,
            data=None,
            input_type=None,
            output_type=bilbo_sequence_description_t,
            timeout=0.1
        )

        if trajectory_data_struct is None:
            self.logger.warning("Failed to get trajectory data from STM32")
            return None

        trajectory = from_dict_auto(data_class=BILBO_Sequence_LL, data=trajectory_data_struct)

        return trajectory

    def _send_trajectory_start_signal_to_lowlevel(self, trajectory_id: int) -> bool:
        success = self.communication.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_SequencerAddresses.START,
            data=trajectory_id,
            input_type=ctypes.c_uint16,
            output_type=ctypes.c_bool,
            timeout=0.1
        )

        return success

    def _send_trajectory_stop_signal_to_lowlevel(self) -> bool:
        success = self.communication.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_SequencerAddresses.STOP,
            data=None,
            input_type=None,
            output_type=None,
            timeout=0.1
        )

        return success

    # === SEQUENCER EVENT CALLBACK =====================================================================================
    def _sequencer_event_callback(self, message: BILBO_Sequencer_Event_Message, *args, **kwargs):
        event = BILBO_LL_Sequencer_Event_Type(message.data['event']).name

        self.logger.debug(f"Received sequencer event: {event}. {message}")

        trajectory_id = message.data['sequence_id']
        tick = message.data['tick']

        match event:
            case 'STARTED':
                self.logger.debug(f"Trajectory {trajectory_id} started")
                self._internal_events.trajectory_started.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                                             flags={'trajectory_id': trajectory_id})
            case 'FINISHED':
                self.logger.debug(f"Trajectory {trajectory_id} finished")
                self._internal_events.trajectory_finished.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                                              flags={'trajectory_id': trajectory_id})
            case 'RECEIVED':
                self.logger.debug(f"Trajectory {trajectory_id} loaded")
                self._internal_events.trajectory_loaded.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                                            flags={'trajectory_id': trajectory_id})
            case 'ABORTED':
                self.logger.debug(f"Trajectory {trajectory_id} aborted")
                self._internal_events.trajectory_aborted.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                                             flags={'trajectory_id': trajectory_id})

    # === END-OF-STEP ==================================================================================================
    def _end_of_step_callback(self):
        for marker in list(self.markers.values()):
            if not marker.hold:
                del self.markers[marker.id]
