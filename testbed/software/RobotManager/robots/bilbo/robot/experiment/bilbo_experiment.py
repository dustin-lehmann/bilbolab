from __future__ import annotations

import abc
import dataclasses
import enum
import json
import tempfile
import threading
import time
from dataclasses import asdict
from typing import Any, Union

import numpy as np
import yaml
from dacite import Config

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.data import generate_time_vector, generate_time_vector_by_length
from core.utils.dataclass_utils import from_dict_auto, asdict_optimized
from core.utils.events import event_definition, Event, EventFlag, pred_flag_equals, wait_for_events, OR, TIMEOUT, \
    EventContainer
from core.utils.files import file_exists
from core.utils.logging_utils import Logger
from core.utils.plotting.plot import quick_plot
from core.utils.sound.sound import speak
from robots.bilbo.robot.bilbo_control import BILBO_Control
# === CUSTOM PACKAGES ==================================================================================================
from robots.bilbo.robot.bilbo_core import BILBO_Core
from robots.bilbo.robot.bilbo_definitions import MAX_STEPS_TRAJECTORY, HOST_EXPERIMENT_FOLDER
from robots.bilbo.robot.experiment.experiment_definitions import BILBO_InputTrajectory, BILBO_TrajectoryData, \
    ExperimentDefinition, ExperimentData, ExperimentActionDefinition
from robots.bilbo.robot.experiment.experiment_helpers import generate_random_input_trajectory


# # ======================================================================================================================
# class BILBO_Experiment_Status(enum.StrEnum):
#     NONE = "none"
#     RUNNING_TRAJECTORY = "running_trajectory"
#     CALCULATING = "calculating"
#     WAITING_FOR_USER = "waiting_for_user"
#     FINISHED = "finished"
#     ABORTED = "aborted"
#
#
# @event_definition
# class BILBO_Experiment_Events(EventContainer):
#     started: Event
#     finished: Event
#     aborted: Event
#     status_changed: Event = Event(flags=EventFlag('status', BILBO_Experiment_Status))
#
#
# @callback_definition
# class BILBO_Experiment_Callbacks:
#     stopped: CallbackContainer
#
#
# class BILBO_Experiment(abc.ABC):
#     type: str
#     events: BILBO_Experiment_Events
#
#     status: BILBO_Experiment_Status
#
#     _thread: threading.Thread | None = None
#     _stopEvent: Event
#     _exit: bool = False
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def __init__(self, core: BILBO_Core, experiment_handler: BILBO_ExperimentHandler, control: BILBO_Control):
#         self.core = core
#         self.experiment_handler = experiment_handler
#         self.control = control
#         self.events = BILBO_Experiment_Events()
#         self.callbacks = BILBO_Experiment_Callbacks()
#
#         self.status = BILBO_Experiment_Status.NONE
#         self.logger = Logger("Experiment")
#         self._thread = threading.Thread(target=self.task, daemon=True)
#         self._stopEvent = Event()
#
#     # === PROPERTIES ===================================================================================================
#     @property
#     def status(self):
#         return self._status
#
#     @status.setter
#     def status(self, value: BILBO_Experiment_Status):
#         self._status = value
#         self.events.status_changed.set(data=value, flags={'status': value})
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def start(self):
#         self.events.started.set()
#         self._thread.start()
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def stop(self, aborted: bool = False):
#         self._exit = True
#         self._stopEvent.set()
#
#         if aborted:
#             self.events.aborted.set()
#         else:
#             self.events.finished.set()
#
#         self.callbacks.stopped.call()
#         self.logger.info("Experiment stopped")
#
#     # ------------------------------------------------------------------------------------------------------------------
#     @abc.abstractmethod
#     def task(self):
#         ...


# ======================================================================================================================


# ======================================================================================================================
class BILBO_ExperimentHandler_Status(enum.StrEnum):
    IDLE = "idle"
    EXPERIMENT_RUNNING = "experiment_running"


# ======================================================================================================================
@event_definition
class BILBO_ExperimentHandler_Events:
    status_changed: Event = Event(flags=EventFlag('status', BILBO_ExperimentHandler_Status))

    ll_trajectory_finished: Event = Event(flags=EventFlag('trajectory_id', int))
    ll_trajectory_aborted: Event = Event(flags=EventFlag('trajectory_id', int))
    ll_trajectory_started: Event = Event(flags=EventFlag('trajectory_id', int))

    trajectory_finished: Event = Event(flags=EventFlag('trajectory_id', (int, str)),
                                       data_type=BILBO_TrajectoryData)

    trajectory_loaded: Event = Event()

    waiting_for_user: Event = Event()

    experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_finished: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_error: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_timeout: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)

    dilc_experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)


@event_definition
class BILBO_ExperimentHandler_InternalEvents:
    experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_finished: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_error: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_timeout: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)


# ======================================================================================================================
class BILBO_ExperimentHandler:
    # experiment: BILBO_Experiment | None = None
    control: BILBO_Control

    status: BILBO_ExperimentHandler_Status = BILBO_ExperimentHandler_Status.IDLE
    current_trajectory: BILBO_InputTrajectory | None = None

    _loadedTrajectory: BILBO_InputTrajectory | None = None

    # === INIT =========================================================================================================
    def __init__(self, core: BILBO_Core, control: BILBO_Control):
        self.core = core
        self.control = control
        self.id = core.id
        self.logger = self.core.logger
        self.device = self.core.device

        self.events = BILBO_ExperimentHandler_Events()
        self._events_internal = BILBO_ExperimentHandler_InternalEvents()

        self.device.events.event.on(self._trajectory_event_callback,
                                    predicate=pred_flag_equals('event', 'trajectory')
                                    )

        self.device.events.event.on(self._experiment_event_callback,
                                    predicate=pred_flag_equals('event', 'experiment'))

    # === METHODS ======================================================================================================
    def run_experiment(self,
                       experiment_definition: ExperimentDefinition,
                       experiment_file_folder: str | None = None,
                       blocking: bool = False) -> ExperimentData | None | bool:

        self.logger.info(f"Starting experiment \"{experiment_definition.id}\"...")

        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            self.logger.error("Experiment already running")
            return None

        definition_dict = experiment_definition.to_dict()

        result = self.device.executeFunction(
            function_name='run_experiment',
            arguments={
                'experiment': definition_dict,
            },
            return_type=bool,
        )

        if not result:
            self.logger.error("Experiment failed to start")
            return None

        # Wait for the experiment start event
        data, _ = self._events_internal.experiment_started.wait(timeout=2)

        if data is TIMEOUT:
            self.logger.error("Experiment failed to start")
            return None

        self.logger.info(f"Experiment \"{experiment_definition.id}\" started successfully")

        if blocking:
            self.logger.info(f"Waiting for experiment \"{experiment_definition.id}\"to finish...")
            data, result = wait_for_events(
                events=OR(
                    (self._events_internal.experiment_finished,
                     pred_flag_equals('experiment_id', experiment_definition.id)),
                    (self._events_internal.experiment_error,
                     pred_flag_equals('experiment_id', experiment_definition.id)),
                    (self._events_internal.experiment_timeout,
                     pred_flag_equals('experiment_id', experiment_definition.id)),
                ),
                timeout=experiment_definition.timeout
            )

            if data is TIMEOUT:
                self.logger.error("Experiment timed out")
                return None

            if result.caused_by(self.events.experiment_timeout):
                self.logger.error("Experiment timed out")
                return None

            elif result.caused_by(self.events.experiment_error):
                self.logger.error("Experiment failed")
                return None

            self.logger.info(f"Experiment \"{experiment_definition.id}\" finished successfully")

            # TODO: Testing the data
            self.logger.info(f"Experiment data: {data}")

            # Download the file
            if experiment_file_folder is None:
                with tempfile.TemporaryDirectory(prefix="experiment_") as tmpdir:
                    filename = self.core.file_handler.download_file(data, tmpdir)

                    with open(filename, 'r') as f:
                        experiment_data = json.load(f)

                    return experiment_data
            else:
                filename = self.core.file_handler.download_file(data, experiment_file_folder)

                with open(filename, 'r') as f:
                    experiment_data = json.load(f)

                return experiment_data
            # samples = experiment_data['samples']
            # theta = [sample['lowlevel']['estimation']['state']['theta'] for sample in samples]
            # mode = [sample['control']['mode'] for sample in samples]
            # input = [sample['lowlevel']['control']['data']['input_left'] for sample in samples]
            # mode_ll = [sample['lowlevel']['control']['mode'] for sample in samples]
            # v = [sample['lowlevel']['estimation']['state']['v'] for sample in samples]
            #
            # tick_ll = [sample['lowlevel']['tick'] for sample in samples]
            #
            # t = generate_time_vector_by_length(start=0, num_samples=len(theta), dt=0.01)
            #
            # quick_plot(
            #     x=t,
            #     y=theta,
            #     xlabel='Time [s]',
            #     ylabel='Theta [rad]',
            #     ylim=(-2, 2),
            # )
            #
            # quick_plot(
            #     x=t,
            #     y=mode,
            #     xlabel='Time [s]',
            #     ylabel='Mode',
            #     title='Mode',
            # )
            #
            # quick_plot(
            #     x=t,
            #     y=input,
            #     xlabel='Time [s]',
            #     ylabel='Input',
            #     title='Input',
            # )
            # quick_plot(
            #     x=t,
            #     y=mode_ll,
            #     xlabel='Time [s]',
            #     ylabel='Mode LL',
            #     title='Mode LL',
            # )
            #
            # quick_plot(
            #     x=t,
            #     y=v,
            #     xlabel='Time [s]',
            #     ylabel='v [m/s]',
            #     title='v',
            # )
            #
            # quick_plot(
            #     x=t,
            #     y=tick_ll,
            #     xlabel='Time [s]',
            #     ylabel='Tick LL',
            #     title='Tick LL',
            # )

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def stop_experiment(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def run_experiment_from_file(self, file: str, blocking: bool = True) -> ExperimentData | None:

        if not file.endswith(".yaml"):
            file += ".yaml"

        if not file_exists(file):
            # Check if the file is in the experiments folder
            file_in_experiments_folder = f"{HOST_EXPERIMENT_FOLDER}/{file}"

            if not file_exists(file_in_experiments_folder):
                self.logger.error(f"Experiment file not found: {file}")
                return None

            file = file_in_experiments_folder

        definition = ExperimentDefinition.from_file(file)
        return self.run_experiment(definition, blocking=blocking)

    # ------------------------------------------------------------------------------------------------------------------
    def runPositionTest(self,waypoints: list = [[0.6, 0], [0.6, 0.75], [1.2, 0.75], [1.2, 1.7], [1.75, 1.7], [1.75, 1.7],
                                           [1.75, 0.75], [1, 0.75], [0.5, 0.75], [0, 0]], controlParams: dict = None):
        speak(f"Start position control test with {len(waypoints)} waypoints")
        waypoints = [[0.6, 0], [0.6, 0.75], [1.2, 0.75], [1.2, 1.7], [1.75, 1.7], [1.75, 1.7], [1.2, 1.7], [1.2, 0.75],
                     [0.6, 0.75], [0.6, 0], [0, 0]]
        # ▊   sendKPos[
        #     -0.35, -0.25, -0.35, -0.04, -0.04, -0.025, 0.5, 0, -0.35, -0.25, -0.35, -0.04, 0.04, 0.025, 0.5, 0]                                                                                                ▎
        # self.device.function(function='setPositionControlKPos', data={
        #     'K_Pos': controlParams
        # })

        self.control.initKpos()
        speak("Initialized K position control gains")
        time.sleep(5)

        for waypoint in waypoints:
            self.device.executeFunction(function_name='setPositionControlWaypoints', arguments={
                'waypoints': waypoint
            })
            time.sleep(1)

    def run_trajectory(self, trajectory: BILBO_InputTrajectory) -> BILBO_TrajectoryData | None:
        assert len(trajectory.inputs) <= MAX_STEPS_TRAJECTORY
        assert trajectory.length == len(trajectory.inputs)
        assert trajectory.time_vector.shape[0] == trajectory.length

        self.logger.info(f"Trying to run trajectory \"{trajectory.name}\" on device ...")

        self._loadedTrajectory = trajectory
        # Kick off on the device
        self.device.executeFunction(
            function_name='run_trajectory',
            arguments={'trajectory_data': asdict(trajectory)},
        )

        # Wait for either "finished" or "aborted" for this trajectory id

        data, result = wait_for_events(
            events=
            OR((self.events.ll_trajectory_finished, pred_flag_equals('trajectory_id', int(trajectory.id))),
               self.events.ll_trajectory_aborted),
            timeout=float(trajectory.time_vector[-1] + 5.0),
            stale_event_time=0.5,
        )

        if data is TIMEOUT:
            self.logger.error(f"Trajectory \"{trajectory.name}\" failed due to timeout")
            return None

        if result.caused_by(self.events.ll_trajectory_aborted):
            self.logger.error(f"Trajectory \"{trajectory.name}\" aborted")
            return None

        output_data_dict: dict | None = data.get('data', None)

        if output_data_dict is None:
            self.logger.error(f"Trajectory \"{trajectory.name}\" failed due to missing data")
            return None

        trajectory_data = from_dict_auto(BILBO_TrajectoryData, output_data_dict['data'])

        self.events.trajectory_finished.set(data=trajectory_data, flags={'trajectory_id': trajectory.id})

        self.logger.important(f"Trajectory \"{trajectory.name}\" finished.")
        return trajectory_data

    # ------------------------------------------------------------------------------------------------------------------
    def run_random_trajectory(self, time_s, frequency=2, gain=0.25):

        trajectory = generate_random_input_trajectory(1, time_s, frequency, gain)
        self.logger.info(
            f"Generated random trajectory: {trajectory.id} (Length: {trajectory.time_vector[-1]} s). "
            f"Waiting for resume event...")

        self._loadedTrajectory = trajectory
        self.events.trajectory_loaded.set(data=trajectory)
        self.events.waiting_for_user.set(data=trajectory)

        self.core.interface_events.resume.wait(timeout=None)
        data = self.run_trajectory(trajectory=trajectory)
        if data is None:
            return

        # Plot the input and output data

        # time_vector = data.input_trajectory.time_vector
        #
        # # Plot input trajectory
        # ax1.plot(time_vector, data.input_trajectory.inputs)
        # ax1.set_xlabel('Time [s]')
        # ax1.set_ylabel('Input')
        # ax1.set_title('Input Trajectory')
        # ax1.grid(True)
        #
        # # Plot states
        # ax2.plot(time_vector, data.states)
        # ax2.set_xlabel('Time [s]')
        # ax2.set_ylabel('States')
        # ax2.set_title('System States')
        # ax2.grid(True)
        #
        # fig.tight_layout()
        #

        # return self.run_trajectory(trajectory=trajectory)

    # ------------------------------------------------------------------------------------------------------------------
    def start_trajectory(self):
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def sendTrajectory(self):
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def stopTrajectory(self):
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def _trajectory_event_callback(self, message, *args, **kwargs):
        if 'event' not in message.data:
            self.logger.error(f"Robot {self.id}: Received trajectory event without event field")

        match message.data['event']:
            case 'finished':
                self.logger.info(f"Trajectory {message.data['trajectory_id']} finished.")
                # speak(f"{self.id}: Trajectory {message.data['trajectory_id']} finished")
                self.current_trajectory = None
                self._loadedTrajectory = None
                # self.status = BILBO_ExperimentHandler_Status.IDLE
                self.events.ll_trajectory_finished.set(data=message.data,
                                                       flags={'trajectory_id': int(message.data['trajectory_id'])})

                self.events.status_changed.set(data=self.status, flags={'status': self.status})

            case 'started':
                self.logger.info(f"Trajectory {message.data['trajectory_id']} started.")
                # speak(f"{self.id}: Trajectory {message.data['trajectory_id']} started")
                self.current_trajectory = self._loadedTrajectory
                # self.status = BILBO_ExperimentHandler_Status.RUNNING
                self.events.ll_trajectory_started.set(data=message.data,
                                                      flags={'trajectory_id': message.data['trajectory_id']})
                self.events.status_changed.set(data=self.status, flags={'status': self.status})

            case 'aborted':
                self.logger.info(f"Trajectory {message.data['trajectory_id']} aborted.")
                speak(f"{self.id}: Trajectory {message.data['trajectory_id']} aborted")
                self.current_trajectory = None
                self._loadedTrajectory = None
                # self.status = BILBO_ExperimentHandler_Status.IDLE
                self.events.ll_trajectory_aborted.set(data=message.data,
                                                      flags={'trajectory_id': message.data['trajectory_id']})
                self.events.status_changed.set(data=self.status, flags={'status': self.status})

    # ------------------------------------------------------------------------------------------------------------------
    def _experiment_event_callback(self, message, *args, **kwargs):
        if 'event' not in message.data:
            self.logger.error(f"Robot {self.id}: Received experiment event without event field")

        event = message.data['event']
        experiment_id = message.data['experiment_id']
        data = message.data.get('data', None)

        self.logger.debug(f"Received experiment event \"{event}\" for experiment \"{experiment_id}\"")
        self.logger.debug(f"Experiment data: {data}")

        if event == 'started':
            self.logger.debug(f"Experiment \"{experiment_id}\" started")
            self._events_internal.experiment_started.set(flags={'experiment_id': experiment_id}, data=data)
        elif event == 'finished':
            self.logger.debug(f"Experiment \"{experiment_id}\" finished")
            self._events_internal.experiment_finished.set(flags={'experiment_id': experiment_id}, data=data)
        elif event == 'error':
            self.logger.warning(f"Experiment \"{experiment_id}\" failed")
            self._events_internal.experiment_error.set(flags={'experiment_id': experiment_id}, data=data)
        elif event == 'timeout':
            self.logger.warning(f"Experiment \"{experiment_id}\" timed out")
            self._events_internal.experiment_timeout.set(flags={'experiment_id': experiment_id}, data=data)
        else:
            self.logger.error(f"Unknown experiment event: {event}")

    # ------------------------------------------------------------------------------------------------------------------
    def getCurrentTrajectory(self) -> BILBO_InputTrajectory | None:
        return self.current_trajectory

    # ------------------------------------------------------------------------------------------------------------------
    def getLoadedTrajectory(self) -> BILBO_InputTrajectory | None:
        return self._loadedTrajectory

    # ------------------------------------------------------------------------------------------------------------------
    def test_trajectory_experiment(self):

        u = -0.5 * np.ones(100 * 1)
        traj = BILBO_InputTrajectory.from_vector(vector=u, name='test_trajectory', id=1)

        exp_definition = ExperimentDefinition(
            id='test_experiment',
            description='Test experiment',
            actions=[
                ExperimentActionDefinition(
                    id='traj',
                    type='run_trajectory',
                    parameters={
                        'input_trajectory': traj,
                    }
                )
            ]
        )

        data = self.run_experiment(exp_definition, blocking=True)

        if data is None:
            self.logger.error("Experiment \"test_trajectory\" failed")
        else:
            self.logger.important(f"Experiment \"test_trajectory\" succeeded.")

        pass

    # ------------------------------------------------------------------------------------------------------------------
    # @staticmethod
    # def getTrajectoryExperimentDataFromDict(data: dict) -> BILBO_ExperimentData:
    #     config = Config(
    #         cast=[int, float],  # allow casting numbers where JSON gives str/float
    #         strict=False,  # ignore unknown fields if the device returns extra data
    #     )
    #     return from_dict_auto(BILBO_ExperimentData, data)
