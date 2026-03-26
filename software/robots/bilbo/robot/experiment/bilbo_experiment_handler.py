"""
BILBO Experiment Handler (Host Side)

This module provides the host-side experiment handling for BILBO robots.
It sends experiment definitions to the robot and handles experiment events.

Experiments are defined as YAML files and parsed by ExperimentParser from
core.utils.experiments. The host loads the YAML as a raw dict and sends it
directly to the robot for execution.

Example usage:
    # Run experiment from YAML file
    data = experiment_handler.run_experiment_from_file("my_experiment.yaml", blocking=True)

    # Run experiment from dict
    experiment_dict = {"id": "test", "description": "Test", "actions": [...]}
    data = experiment_handler.run_experiment(experiment_dict, blocking=True)
"""
from __future__ import annotations

import enum
import json
import os
import tempfile
import time
import webbrowser
from dataclasses import asdict
from typing import TYPE_CHECKING

import yaml

from core.utils.data import generate_time_vector_by_length
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import (
    event_definition, Event, EventFlag, pred_flag_equals,
    wait_for_events, OR, TIMEOUT, EventContainer
)
from core.utils.files import file_exists
from core.utils.logging_utils import Logger
from core.utils.plotting.plot import quick_plot
from core.utils.sound.sound import speak, beep
from robots.bilbo.definitions import EXPERIMENT_DIR
from robots.bilbo.robot.bilbo_control import BILBO_Control
from robots.bilbo.robot.bilbo_core import BILBO_Core
from robots.bilbo.robot.bilbo_definitions import MAX_STEPS_TRAJECTORY
from robots.bilbo.robot.experiment.experiment_definitions import (
    InputTrajectory,
    TrajectoryData,
    INPUT_TRAJECTORY_FILE_EXTENSION,
    read_input_file,
)
from robots.bilbo.robot.experiment.helpers import generate_random_input_trajectory, make_report

if TYPE_CHECKING:
    from robots.bilbo.robot.experiment import DILC_Experiment
    from robots.bilbo.robot.experiment.limbobar_dilc import LimboBar_DILC_Experiment

logger = Logger("BILBO_ExperimentHandler")


# ======================================================================================================================
def _resolve_trajectory_file_references(actions: list[dict], source_dir: str) -> None:
    """Resolve string input_trajectory references in experiment action dicts.

    Walks through actions (including nested groups/parallel/loops) and replaces
    string input_trajectory values with the full trajectory data loaded from
    .bitrj files in source_dir.  Modifies actions in-place.
    """
    for action in actions:
        # Handle nested actions (group, parallel, loop)
        if "actions" in action:
            sub = action["actions"]
            if isinstance(sub, list):
                _resolve_trajectory_file_references(sub, source_dir)

        action_type = action.get("type")
        if action_type != "run_trajectory":
            continue

        # input_trajectory can be a flat key or inside parameters
        if "parameters" in action and isinstance(action["parameters"], dict):
            params = action["parameters"]
        else:
            params = action

        traj_value = params.get("input_trajectory")
        if not isinstance(traj_value, str):
            continue

        # Look for <name>.bitrj in the source directory
        name = traj_value
        if not name.endswith(INPUT_TRAJECTORY_FILE_EXTENSION):
            name += INPUT_TRAJECTORY_FILE_EXTENSION
        file_path = os.path.join(source_dir, name)

        if not os.path.isfile(file_path):
            logger.warning(
                f"Trajectory file '{name}' not found in {source_dir} — "
                f"sending string reference to robot as-is"
            )
            continue

        file_data = read_input_file(file_path)
        if file_data is None:
            logger.warning(f"Failed to read trajectory file: {file_path}")
            continue

        trajectory = file_data.to_trajectory()
        params["input_trajectory"] = asdict(trajectory)
        logger.info(f"Resolved trajectory '{traj_value}' from {file_path} ({trajectory.length} steps)")


# ======================================================================================================================
# Environment directory for resolving testbed file names without full path
_ENVIRONMENTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'configs', 'testbeds', 'environments'
))


def _resolve_testbed_file_references(actions: list[dict], source_dir: str) -> None:
    """Resolve file references in load_testbed actions.

    Walks through actions (including nested groups/parallel/loops) and replaces
    string ``file`` values in ``load_testbed`` actions with the loaded environment
    data.  The compact YAML format (``size: {x: [0,3], y: [0,3]}``,
    ``obstacles[].size``, ``obstacles[].state``) is normalised to the flat dict
    format that the on-robot ``TestbedData`` expects.  Modifies actions in-place.
    """
    for action in actions:
        # Recurse into nested action containers
        if "actions" in action:
            sub = action["actions"]
            if isinstance(sub, list):
                _resolve_testbed_file_references(sub, source_dir)

        if action.get("type") != "load_testbed":
            continue

        file_value = action.get("file")
        if not isinstance(file_value, str):
            continue

        # Resolve the file path: try source_dir first, then environments dir
        if not file_value.endswith(('.yaml', '.yml')):
            file_value += '.yaml'

        file_path = os.path.join(source_dir, file_value)
        if not os.path.isfile(file_path):
            file_path = os.path.join(_ENVIRONMENTS_DIR, file_value)
        if not os.path.isfile(file_path):
            # Try just the basename in environments dir
            file_path = os.path.join(_ENVIRONMENTS_DIR, os.path.basename(file_value))

        if not os.path.isfile(file_path):
            logger.warning(
                f"Testbed file '{file_value}' not found in {source_dir} or "
                f"{_ENVIRONMENTS_DIR} — sending string reference as-is"
            )
            continue

        try:
            with open(file_path, 'r') as f:
                env_data = yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load testbed file '{file_path}': {e}")
            continue

        # Convert the compact YAML format to the flat TestbedData format
        resolved = _convert_environment_yaml(env_data)

        # Merge resolved data into the action dict (inline params take precedence)
        for key in ('config', 'obstacles', 'lines', 'points', 'poses'):
            if key not in action or action[key] is None:
                if key in resolved:
                    action[key] = resolved[key]

        # Remove the file key — robot doesn't need it
        del action['file']

        env_id = env_data.get('id', os.path.splitext(os.path.basename(file_path))[0])
        n_obs = len(resolved.get('obstacles', []))
        logger.info(f"Resolved testbed '{env_id}' from {file_path} ({n_obs} obstacles)")


def _resolve_control_config_file_references(actions: list[dict], source_dir: str) -> None:
    """Resolve ``file`` references in ``load_control_config`` actions.

    Loads the YAML file (relative to *source_dir*) and inlines its content as
    ``config`` so that the robot can deep-merge it on top of the default config.
    Modifies actions in-place.
    """
    for action in actions:
        if "actions" in action:
            sub = action["actions"]
            if isinstance(sub, list):
                _resolve_control_config_file_references(sub, source_dir)

        if action.get("type") != "load_control_config":
            continue

        file_value = action.get("file")
        if not isinstance(file_value, str):
            continue

        if not file_value.endswith(('.yaml', '.yml')):
            file_value += '.yaml'

        file_path = os.path.join(source_dir, file_value)
        if not os.path.isfile(file_path):
            logger.warning(
                f"Control config file '{file_value}' not found in {source_dir} — "
                f"sending string reference to robot as-is"
            )
            continue

        try:
            with open(file_path, 'r') as f:
                config_data = yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load control config file '{file_path}': {e}")
            continue

        action['config'] = config_data
        del action['file']
        logger.info(f"Resolved control config from {file_path}")


def _convert_environment_yaml(env_data: dict) -> dict:
    """Convert a compact environment YAML dict to the flat TestbedData format.

    Handles the shorthand fields used in environment files:
    - ``size: {x: [min, max], y: [min, max]}`` → ``config.size: {x_min, x_max, y_min, y_max}``
    - ``obstacles[].size: [w, h]`` → ``obstacles[].width, .height``
    - ``obstacles[].state: [x, y, psi]`` → ``obstacles[].x, .y, .psi``
    - ``poses[].pose: [x, y, psi]`` → ``poses[].x, .y, .psi``
    """
    result = {}

    # Config (id + size)
    size_raw = env_data.get('size')
    if size_raw is not None:
        result['config'] = {
            'id': env_data.get('id'),
            'size': {
                'x_min': size_raw['x'][0],
                'x_max': size_raw['x'][1],
                'y_min': size_raw['y'][0],
                'y_max': size_raw['y'][1],
            }
        }
    elif env_data.get('id') is not None:
        result['config'] = {'id': env_data['id']}

    # Obstacles — normalise compact shorthand
    raw_obstacles = env_data.get('obstacles')
    if raw_obstacles:
        obstacles = []
        for obs in raw_obstacles:
            o = dict(obs)
            # size: [w, h] → width, height
            if 'size' in o:
                s = o.pop('size')
                if isinstance(s, (list, tuple)) and len(s) >= 2:
                    o.setdefault('width', float(s[0]))
                    o.setdefault('height', float(s[1]))
            # state: [x, y, psi] → x, y, psi
            if 'state' in o:
                s = o.pop('state')
                if isinstance(s, (list, tuple)) and len(s) >= 2:
                    o.setdefault('x', float(s[0]))
                    o.setdefault('y', float(s[1]))
                    if len(s) > 2:
                        o.setdefault('psi', float(s[2]))
            # Default type to box if width/height present, else circle
            if 'type' not in o:
                o['type'] = 'circle' if 'radius' in o else 'box'
            obstacles.append(o)
        result['obstacles'] = obstacles

    # Lines — pass through
    if env_data.get('lines'):
        result['lines'] = env_data['lines']

    # Points — pass through
    if env_data.get('points'):
        result['points'] = env_data['points']

    # Poses — normalise compact shorthand
    raw_poses = env_data.get('poses')
    if raw_poses:
        poses = []
        for pose in raw_poses:
            p = dict(pose)
            if 'pose' in p:
                s = p.pop('pose')
                if isinstance(s, (list, tuple)) and len(s) >= 2:
                    p.setdefault('x', float(s[0]))
                    p.setdefault('y', float(s[1]))
                    if len(s) > 2:
                        p.setdefault('psi', float(s[2]))
            poses.append(p)
        result['poses'] = poses

    return result


# ======================================================================================================================
class BILBO_ExperimentHandler_Status(enum.StrEnum):
    IDLE = "idle"
    EXPERIMENT_LOADED = "experiment_loaded"
    EXPERIMENT_RUNNING = "experiment_running"


# ======================================================================================================================
@event_definition
class BILBO_ExperimentHandler_Events:
    """Events emitted by the experiment handler."""
    status_changed: Event = Event(flags=EventFlag('status', BILBO_ExperimentHandler_Status))

    # Low-level trajectory events (from robot)
    ll_trajectory_finished: Event = Event(flags=EventFlag('trajectory_id', int))
    ll_trajectory_aborted: Event = Event(flags=EventFlag('trajectory_id', int))
    ll_trajectory_started: Event = Event(flags=EventFlag('trajectory_id', int))

    # High-level trajectory event
    trajectory_finished: Event = Event(
        flags=EventFlag('trajectory_id', (int, str)),
        data_type=TrajectoryData
    )
    trajectory_loaded: Event = Event()
    waiting_for_user: Event = Event()

    # Experiment lifecycle events (public)
    experiment_loaded: Event = Event(flags=[EventFlag('experiment_id', str), EventFlag('experiment_label', str)],
                                     copy_data_on_set=False)
    experiment_started: Event = Event(flags=[EventFlag('experiment_id', str), EventFlag('experiment_label', str)],
                                      copy_data_on_set=False)
    experiment_finished: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_error: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_timeout: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)

    # Action-level progress events
    action_started: Event = Event(flags=[EventFlag('experiment_id', str), EventFlag('action_id', str)],
                                  copy_data_on_set=False)
    action_finished: Event = Event(flags=[EventFlag('experiment_id', str), EventFlag('action_id', str)],
                                   copy_data_on_set=False)

    # Experiment message (user-facing status messages)
    experiment_message: Event = Event(flags=[EventFlag('experiment_id', str), EventFlag('level', str)],
                                      copy_data_on_set=False)

    # DILC experiment events
    dilc_experiment_initialized: Event = Event(copy_data_on_set=False)
    dilc_experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)

    # LimboBar DILC experiment events
    limbobar_dilc_experiment_initialized: Event = Event(copy_data_on_set=False)


@event_definition
class BILBO_ExperimentHandler_InternalEvents:
    """Internal events for experiment handling (used for blocking waits)."""
    experiment_loaded: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_finished: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_error: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_timeout: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)


# ======================================================================================================================
class BILBO_ExperimentHandler:
    """Host-side experiment handler for BILBO robots.

    This class manages:
    - Sending experiment definitions to the robot
    - Running trajectories on the robot
    - Handling experiment lifecycle events (started, finished, error, timeout)
    - Downloading experiment data from the robot

    Example usage:
        # Run experiment from YAML file
        data = handler.run_experiment_from_file("my_experiment.yaml", blocking=True)

        # Run experiment from a dict
        exp = {"id": "test", "description": "Test", "timeout": 30,
               "actions": [{"type": "set_mode", "mode": "BALANCING"},
                           {"type": "wait_time", "time": 5.0},
                           {"type": "set_mode", "mode": "OFF"}]}
        data = handler.run_experiment(exp, blocking=True)
    """
    control: BILBO_Control
    status: BILBO_ExperimentHandler_Status = BILBO_ExperimentHandler_Status.IDLE
    current_experiment_definition: dict | None = None
    experiment_actions: list[dict] = []
    current_trajectory: InputTrajectory | None = None

    _loadedTrajectory: InputTrajectory | None = None
    _last_experiment_data: dict | None = None
    _last_experiment_data_file: str | None = None
    _experiment_start_time: float | None = None  # Monotonic time when experiment started
    _EXPERIMENT_STALE_TIMEOUT: float = 600.0  # 10 minutes max before status is considered stale

    dilc_experiment: DILC_Experiment | None = None
    limbobar_dilc_experiment: LimboBar_DILC_Experiment | None = None

    # === INIT =========================================================================================================
    def __init__(self, core: BILBO_Core, control: BILBO_Control):
        self.core = core
        self.control = control
        self.id = core.id
        self.logger = self.core.logger
        self.device = self.core.device

        self.events = BILBO_ExperimentHandler_Events()
        self._events_internal = BILBO_ExperimentHandler_InternalEvents()

        # Register event handlers for robot events
        self.device.events.event.on(
            self._trajectory_event_callback,
            predicate=pred_flag_equals('event', 'trajectory_finished'),
        )

        self.device.events.event.on(
            self._trajectory_aborted_callback,
            predicate=pred_flag_equals('event', 'trajectory_aborted'),
        )

        self.device.events.event.on(
            self._experiment_event_callback,
            predicate=pred_flag_equals('container', 'experiment'),
        )

        # DILC experiment — None when no experiment is active
        self.dilc_experiment = None
        self.limbobar_dilc_experiment = None

    # === DILC ==========================================================================
    def run_dilc_from_file(self, file: str):
        """Run a DILC experiment from a YAML config file.

        Args:
            file: Path to a DILC experiment YAML file.
        """
        from robots.bilbo.robot.experiment.dilc import DILC_Experiment, DILC_Experiment_State

        # Guard against starting a second experiment
        if (self.dilc_experiment is not None
                and self.dilc_experiment.state == DILC_Experiment_State.RUNNING):
            self.logger.warning("A DILC experiment is already running")
            return

        if not file.endswith(('.yaml', '.yml')):
            file += '.yaml'

        if not os.path.isfile(file):
            file_in_experiments = os.path.join(EXPERIMENT_DIR, file)
            if not os.path.isfile(file_in_experiments):
                self.logger.error(f"DILC config file not found: {file}")
                return
            file = file_in_experiments

        # Clean up previous experiment instance to avoid duplicate event handlers
        if self.dilc_experiment is not None:
            self.dilc_experiment.close()

        self.logger.info(f"Loading DILC experiment from: {file}")
        self.dilc_experiment = DILC_Experiment(core=self.core)
        self.dilc_experiment.callbacks.experiment_initialized.register(
            lambda: self.events.dilc_experiment_initialized.set(
                data={'experiment': self.dilc_experiment}
            )
        )
        try:
            self.dilc_experiment.configure_from_yaml(file)
        except Exception as e:
            self.logger.error(f"Failed to load DILC settings: {e}")
            self.dilc_experiment = None
            return
        self.dilc_experiment.start()

    # === LIMBOBAR DILC ================================================================
    def run_limbobar_dilc_from_file(self, file: str):
        """Run a LimboBar DILC experiment from a YAML config file.

        Args:
            file: Path to a LimboBar DILC experiment YAML file.
        """
        from robots.bilbo.robot.experiment.limbobar_dilc import (
            LimboBar_DILC_Experiment, LimboBar_DILC_Experiment_State,
        )

        if (self.limbobar_dilc_experiment is not None
                and self.limbobar_dilc_experiment.state == LimboBar_DILC_Experiment_State.RUNNING):
            self.logger.warning("A LimboBar DILC experiment is already running")
            return

        if not file.endswith(('.yaml', '.yml')):
            file += '.yaml'

        if not os.path.isfile(file):
            file_in_experiments = os.path.join(EXPERIMENT_DIR, file)
            if not os.path.isfile(file_in_experiments):
                self.logger.error(f"LimboBar DILC config file not found: {file}")
                return
            file = file_in_experiments

        if self.limbobar_dilc_experiment is not None:
            self.limbobar_dilc_experiment.close()

        self.logger.info(f"Loading LimboBar DILC experiment from: {file}")
        self.limbobar_dilc_experiment = LimboBar_DILC_Experiment(core=self.core)
        self.limbobar_dilc_experiment.callbacks.experiment_initialized.register(
            lambda: self.events.limbobar_dilc_experiment_initialized.set(
                data={'experiment': self.limbobar_dilc_experiment}
            )
        )
        try:
            self.limbobar_dilc_experiment.configure_from_yaml(file)
        except Exception as e:
            self.logger.error(f"Failed to load LimboBar DILC settings: {e}")
            self.limbobar_dilc_experiment = None
            return
        self.limbobar_dilc_experiment.start()

    # === EXPERIMENTS ==================================================================

    def run_experiment(
            self,
            experiment_definition: dict,
            experiment_file_folder: str | None = None,
            source_dir: str | None = None,
            blocking: bool = False
    ) -> dict | None | bool:
        """Run an experiment on the robot.

        Args:
            experiment_definition: Experiment as a raw dict (YAML-loaded).
                Must contain 'id', 'description', and 'actions' keys.
            experiment_file_folder: Optional folder to save experiment data (if blocking)
            source_dir: Directory containing the experiment YAML (used to resolve
                        string trajectory references to .bitrj files before sending)
            blocking: If True, wait for experiment to complete and return data

        Returns:
            - If blocking: Experiment data dict on success, None on failure
            - If not blocking: True on successful start, None on failure
        """
        exp_id = experiment_definition.get('id', 'unknown')
        exp_label = experiment_definition.get('label', exp_id)
        exp_timeout = experiment_definition.get('timeout')

        self.logger.info(f"Starting experiment \"{exp_id}\"...")

        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            # Check if the status is stale (experiment event may have been lost)
            if (self._experiment_start_time is not None
                    and (time.monotonic() - self._experiment_start_time) > self._EXPERIMENT_STALE_TIMEOUT):
                self.logger.warning("Previous experiment status appears stale, resetting to IDLE")
                self.status = BILBO_ExperimentHandler_Status.IDLE
                self._experiment_start_time = None
            else:
                self.logger.error(f"Cannot start experiment: handler status is \"{self.status}\"")
                return None

        # Resolve file references in experiment actions before sending to robot
        if source_dir:
            for key in ("actions", "setup_actions", "cleanup_actions"):
                if key in experiment_definition:
                    _resolve_trajectory_file_references(experiment_definition[key], source_dir)
                    _resolve_testbed_file_references(experiment_definition[key], source_dir)
                    _resolve_control_config_file_references(experiment_definition[key], source_dir)

        result = self.device.executeFunction(
            function_name='run_experiment',
            arguments={'experiment': experiment_definition},
            return_type=bool,
        )

        if not result:
            self.logger.error("Experiment failed to start")
            return None

        # Wait for the loaded event (robot parsed the definition and is initializing)
        data, _ = self._events_internal.experiment_loaded.wait(timeout=10)
        if data is TIMEOUT:
            self.logger.error("Experiment failed to load on robot")
            return None

        self.logger.info(f"Experiment \"{exp_id}\" loaded on robot")
        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT_LOADED
        self.current_experiment_definition = experiment_definition
        self._experiment_start_time = time.monotonic()
        self.events.experiment_loaded.set(flags={'experiment_id': exp_id, 'experiment_label': exp_label})
        self.events.status_changed.set(data=self.status, flags={'status': self.status})

        # Wait for the experiment start event.
        # Use a generous timeout: guards (e.g. start) may block initialization
        # for an extended period before actions begin.
        guard_timeout = 0
        for g in experiment_definition.get('guards', []):
            gt = g.get('params', {}).get('timeout', 60)
            guard_timeout += gt
        start_wait = max(10, guard_timeout + 10)

        data, _ = self._events_internal.experiment_started.wait(timeout=start_wait)

        if data is TIMEOUT:
            self.logger.error("Experiment failed to start")
            self.status = BILBO_ExperimentHandler_Status.IDLE
            self.current_experiment_definition = None
            self._experiment_start_time = None
            return None

        self.logger.info(f"Experiment \"{exp_id}\" started successfully")
        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT_RUNNING
        self._experiment_start_time = time.monotonic()
        self.events.experiment_started.set(flags={
            'experiment_id': exp_id,
            'experiment_label': exp_label,
        })

        if blocking:
            return self._wait_for_experiment_completion(
                experiment_definition,
                experiment_file_folder
            )

        return True

    def stop_experiment(self, reason: str = "Host stop request") -> bool:
        """Stop the currently running experiment on the robot.

        Args:
            reason: Reason for stopping the experiment

        Returns:
            True if stop command was sent successfully
        """
        self.logger.info(f"Stopping experiment: {reason}")
        result = self.device.executeFunction(
            function_name='stop_experiment',
            arguments={'reason': reason},
            return_type=bool,
        )
        if result:
            self.logger.info("Experiment stop command sent successfully")
        else:
            self.logger.warning("Failed to stop experiment (may not be running)")
        return result

    def run_experiment_from_file(
            self,
            file: str,
            output: str | None = None,
            blocking: bool = True
    ) -> dict | None:
        """Load and run an experiment from a local file.

        Args:
            file: Path to experiment file (YAML or JSON).
            output: Output directory for experiment data. If None, uses the file's directory.
            blocking: If True, wait for completion

        Returns:
            Experiment data on success, None on failure
        """
        # Ensure file has proper extension
        if not file.endswith((".yaml", ".yml", ".json")):
            file += ".yaml"

        # Check if file exists
        if not file_exists(file):
            # Check if the file is in the experiments folder
            file_in_experiments_folder = f"{EXPERIMENT_DIR}/{file}"

            if not file_exists(file_in_experiments_folder):
                self.logger.error(f"Experiment file not found: {file}")
                return None

            file = file_in_experiments_folder

        # Determine output directory
        if output is None:
            # Use the experiment file's directory as output
            output = os.path.dirname(os.path.abspath(file))
            self.logger.info(f"Output directory: {output}")

        # Validate the experiment file before running
        definition = self._load_experiment_file(file)
        if definition is None:
            return None

        # Pass the YAML directory so string trajectory references can be resolved
        yaml_dir = os.path.dirname(os.path.abspath(file))

        return self.run_experiment(
            definition,
            experiment_file_folder=output,
            source_dir=yaml_dir,
            blocking=blocking,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def run_experiment_from_yaml_string(
            self,
            yaml_string: str,
            output: str | None = None,
            blocking: bool = True,
    ) -> dict | None | bool:
        """Run an experiment from a YAML string.

        Args:
            yaml_string: YAML experiment definition as a string.
            output: Output directory for experiment data. If None, uses temp dir.
            blocking: If True, wait for completion.

        Returns:
            - If blocking: Experiment data dict on success, None on failure
            - If not blocking: True on successful start, None on failure
        """
        try:
            definition = yaml.safe_load(yaml_string)
        except Exception as e:
            self.logger.error(f"Failed to parse experiment YAML: {e}")
            return None

        definition = self._validate_experiment_definition(definition)
        if definition is None:
            return None

        return self.run_experiment(
            definition,
            experiment_file_folder=output,
            blocking=blocking,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _validate_experiment_definition(self, definition) -> dict | None:
        """Validate an experiment definition dict.

        Args:
            definition: Parsed experiment definition (from YAML or JSON).

        Returns:
            The definition dict on success, None on validation failure.
        """
        if not isinstance(definition, dict):
            self.logger.error("Experiment validation failed: definition must be a mapping")
            return None

        if not definition.get('id'):
            self.logger.error("Experiment validation failed: missing 'id' field")
            return None

        actions = definition.get('actions', [])
        if not actions:
            self.logger.error("Experiment validation failed: no actions defined")
            return None

        self.logger.info(f"Loaded experiment: {definition['id']}")
        self.logger.info(f"  Description: {definition.get('description', '')}")
        self.logger.info(f"  Actions: {len(actions)}")
        if definition.get('timeout'):
            self.logger.info(f"  Timeout: {definition['timeout']}s")

        return definition

    # ------------------------------------------------------------------------------------------------------------------
    def _load_experiment_file(self, file: str) -> dict | None:
        """Load and validate an experiment definition from a YAML/JSON file.

        Args:
            file: Path to experiment file (YAML or JSON)

        Returns:
            Experiment dict on success, None on failure
        """
        try:
            with open(file, 'r') as f:
                if file.lower().endswith(('.yml', '.yaml')):
                    definition = yaml.safe_load(f)
                else:
                    definition = json.load(f)
        except FileNotFoundError as e:
            self.logger.error(f"Experiment file not found: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to parse experiment file: {e}")
            return None

        return self._validate_experiment_definition(definition)

    # ------------------------------------------------------------------------------------------------------------------
    def run_trajectory(self, trajectory: InputTrajectory) -> TrajectoryData | None:
        """Run a trajectory on the robot (blocking).

        Args:
            trajectory: The input trajectory to run

        Returns:
            Trajectory data on success, None on failure
        """
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
            events=OR(
                (self.events.ll_trajectory_finished, pred_flag_equals('trajectory_id', int(trajectory.id))),
                (self.events.ll_trajectory_aborted, pred_flag_equals('trajectory_id', int(trajectory.id)))
            ),
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

        trajectory_data = from_dict_auto(TrajectoryData, output_data_dict['data'])

        self.events.trajectory_finished.set(data=trajectory_data, flags={'trajectory_id': trajectory.id})

        self.logger.important(f"Trajectory \"{trajectory.name}\" finished.")
        return trajectory_data

    # ------------------------------------------------------------------------------------------------------------------
    def run_random_trajectory(self, time_s: float, frequency: float = 2, gain: float = 0.25, bias: float = 0.0):
        """Generate and run a random trajectory.

        Args:
            time_s: Duration in seconds
            frequency: Frequency parameter for random generation
            gain: Gain parameter for random generation
            bias: Constant offset added to the signal. Positive values bias the robot forward.
        """
        trajectory = generate_random_input_trajectory(1, time_s, frequency, gain, bias=bias)
        self.logger.info(
            f"Generated random trajectory: {trajectory.id} (Length: {trajectory.time_vector[-1]} s). "
            f"Waiting for resume event..."
        )

        self._loadedTrajectory = trajectory
        self.events.trajectory_loaded.set(data=trajectory)
        self.events.waiting_for_user.set(data=trajectory)

        # self.core.interface_events.resume.wait(timeout=None)
        data = self.run_trajectory(trajectory=trajectory)
        if data is None:
            return

    # ------------------------------------------------------------------------------------------------------------------
    def start_trajectory(self):
        """Start a pre-loaded trajectory."""
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def sendTrajectory(self):
        """Send a trajectory to the robot without starting it."""
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def stopTrajectory(self):
        """Stop the currently running trajectory."""
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def getCurrentTrajectory(self) -> InputTrajectory | None:
        """Get the currently running trajectory."""
        return self.current_trajectory

    # ------------------------------------------------------------------------------------------------------------------
    def getLoadedTrajectory(self) -> InputTrajectory | None:
        """Get the loaded (but not necessarily running) trajectory."""
        return self._loadedTrajectory

    # ------------------------------------------------------------------------------------------------------------------
    def get_last_experiment_data(self) -> dict | None:
        """Get the data from the last completed experiment."""
        return self._last_experiment_data

    # === CONVENIENCE METHODS ==========================================================================================
    def plot_last_experiment(self):
        """Plot data from the last experiment."""
        if self._last_experiment_data is None:
            self.logger.warning("No experiment data available")
            return

        samples = self._last_experiment_data['samples']
        theta = [sample['lowlevel']['estimation']['state']['theta'] for sample in samples]
        mode = [sample['control']['mode'] for sample in samples]
        v = [sample['lowlevel']['estimation']['state']['v'] for sample in samples]
        tick_ll = [sample['lowlevel']['tick'] for sample in samples]

        t = generate_time_vector_by_length(start=0, num_samples=len(theta), dt=0.01)

        quick_plot(
            x=t,
            y=theta,
            xlabel='Time [s]',
            ylabel='Theta [rad]',
            ylim=(-2, 2),
        )

        quick_plot(
            x=t,
            y=mode,
            xlabel='Time [s]',
            ylabel='Mode',
            title='Mode',
        )

        quick_plot(
            x=t,
            y=v,
            xlabel='Time [s]',
            ylabel='v [m/s]',
            title='v',
        )

        quick_plot(
            x=t,
            y=tick_ll,
            xlabel='Time [s]',
            ylabel='Tick LL',
            title='Tick LL',
        )

    # === PRIVATE METHODS ==============================================================================================
    def _wait_for_experiment_completion(
            self,
            experiment_definition: dict,
            experiment_file_folder: str | None
    ) -> dict | None:
        """Wait for experiment to complete and download data."""
        exp_id = experiment_definition.get('id', 'unknown')
        exp_timeout = experiment_definition.get('timeout')

        self.logger.info(f"Waiting for experiment \"{exp_id}\" to finish...")

        # Set a generous timeout for the wait
        wait_timeout = exp_timeout if exp_timeout else 300.0
        wait_timeout += 10.0  # Add buffer

        data, result = wait_for_events(
            events=OR(
                (self._events_internal.experiment_finished,
                 pred_flag_equals('experiment_id', exp_id)),
                (self._events_internal.experiment_error,
                 pred_flag_equals('experiment_id', exp_id)),
                (self._events_internal.experiment_timeout,
                 pred_flag_equals('experiment_id', exp_id)),
            ),
            timeout=wait_timeout
        )

        self.status = BILBO_ExperimentHandler_Status.IDLE
        self._experiment_start_time = None

        if data is TIMEOUT:
            self.logger.error("Experiment timed out (host-side timeout)")
            return None

        if result.caused_by(self._events_internal.experiment_timeout):
            self.logger.error("Experiment timed out (robot-side timeout)")
            # Public event already fired by _experiment_event_callback
            # Still download data and generate report for timed out experiments
            return self._download_experiment_data(data, experiment_file_folder)

        if result.caused_by(self._events_internal.experiment_error):
            self.logger.error("Experiment failed")
            # Public event already fired by _experiment_event_callback
            # Still download data and generate report for failed experiments
            return self._download_experiment_data(data, experiment_file_folder)

        self.logger.info(f"Experiment \"{exp_id}\" finished successfully")

        # Download the experiment data file from the robot
        return self._download_experiment_data(data, experiment_file_folder)

    def _download_experiment_data(
            self,
            file_path: str,
            experiment_file_folder: str | None
    ) -> dict | None:
        """Download experiment data from the robot.

        Args:
            file_path: Path to the experiment data file on the robot
            experiment_file_folder: Directory to save the downloaded file.
                                   If None, uses a temp directory.
        """
        if experiment_file_folder is None:
            # Use temp directory as fallback (no magic paths)
            download_dir = tempfile.gettempdir()
            self.logger.warning(f"No output directory specified, using temp: {download_dir}")
        else:
            download_dir = experiment_file_folder

        try:
            filename = self.core.file_handler.download_file(file_path, download_dir)
            self.logger.info(f"Experiment data saved to: {filename}")

            with open(filename, 'r') as f:
                experiment_data = json.load(f)

            self._last_experiment_data = experiment_data
            self._last_experiment_data_file = filename

            # Generate experiment report with same naming scheme as data file
            self._generate_report(experiment_data, data_file_path=filename)

            return experiment_data

        except Exception as e:
            self.logger.error(f"Failed to download experiment data: {e}")
            return None

    def _generate_report(
            self,
            experiment_data: dict,
            data_file_path: str | None = None,
            open_report: bool = True
    ) -> None:
        """Generate an HTML report for the experiment.

        Args:
            experiment_data: The experiment data dictionary
            data_file_path: Path to the data file. If provided, the report will be saved
                           in the same directory with the same base name but .html extension.
            open_report: If True, opens the saved report in the default browser.
        """
        try:
            exp_id = experiment_data.get('id', 'unknown')
            self.logger.info(f"Generating report for experiment \"{exp_id}\"...")

            # Determine output path based on data file path
            output_path = None
            if data_file_path:
                # Use same directory and base name, but with _report.html extension
                base_path = os.path.splitext(data_file_path)[0]
                output_path = f"{base_path}_report.html"

            # Generate and save report (show=False since we handle opening separately)
            make_report(experiment_data, output=output_path, show=(output_path is None))

            if output_path:
                self.logger.info(f"Report saved to: {output_path}")
                # Open in browser if requested
                if open_report:
                    webbrowser.open(f"file://{os.path.abspath(output_path)}")
            else:
                self.logger.info(f"Report generated for experiment \"{exp_id}\"")
        except Exception as e:
            self.logger.warning(f"Failed to generate experiment report: {e}")

    def create_experiment_bundle(
            self,
            output_dir: str,
            experiment_data: dict | None = None,
            yaml_string: str | None = None,
            source_dir: str | None = None,
    ) -> str | None:
        """Create a zip bundle containing all experiment artifacts.

        The bundle includes:
        - experiment.yaml: The experiment definition as run (not the file on disk)
        - result.json: The experiment result data
        - report.html: The generated HTML report
        - files/: Referenced files (input trajectories, testbed environments)

        Args:
            output_dir: Directory to save the zip file.
            experiment_data: Experiment result dict. If None, uses last experiment data.
            yaml_string: YAML string of the experiment definition as run.
            source_dir: Directory to find referenced files (.bitrj, .yaml environments).

        Returns:
            Path to the created zip file, or None on failure.
        """
        import zipfile

        data = experiment_data or self._last_experiment_data
        if data is None:
            self.logger.error("No experiment data available for bundle")
            return None

        exp_id = data.get('id', 'unknown')
        data_file = self._last_experiment_data_file

        os.makedirs(output_dir, exist_ok=True)
        zip_path = os.path.join(output_dir, f"{exp_id}.zip")

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 1. Experiment YAML (as run, from designer) with file paths rewritten
                bundle_yaml = self._rewrite_yaml_paths_for_bundle(yaml_string, data)
                zf.writestr('experiment.yaml', bundle_yaml)

                # 2. Result JSON
                if data_file and os.path.isfile(data_file):
                    zf.write(data_file, 'result.json')
                else:
                    zf.writestr('result.json', json.dumps(data, indent=2, default=str))

                # 3. Report HTML
                if data_file:
                    report_path = os.path.splitext(data_file)[0] + '_report.html'
                    if os.path.isfile(report_path):
                        zf.write(report_path, 'report.html')

                # 4. Referenced files from source_dir
                if source_dir and os.path.isdir(source_dir):
                    self._bundle_referenced_files(zf, data, source_dir)

            self.logger.info(f"Experiment bundle saved to: {zip_path}")
            return zip_path

        except Exception as e:
            self.logger.error(f"Failed to create experiment bundle: {e}")
            return None

    def _rewrite_yaml_paths_for_bundle(self, yaml_string: str | None, data: dict) -> str:
        """Rewrite file paths in the experiment YAML so they point to files/ within the bundle.

        Walks through all actions (including setup/cleanup and nested groups) and
        rewrites trajectory and testbed file references to ``files/<basename>``.
        """
        if yaml_string:
            definition = yaml.safe_load(yaml_string)
        else:
            definition = data.get('definition', {})
            if not definition:
                return yaml_string or ''

        def rewrite_actions(actions):
            if not isinstance(actions, (list, dict)):
                return
            items = actions.values() if isinstance(actions, dict) else actions
            for action in items:
                if not isinstance(action, dict):
                    continue
                action_type = action.get('type', '')

                if action_type == 'run_trajectory':
                    for key in ('trajectory', 'input_trajectory'):
                        val = action.get(key)
                        if isinstance(val, str):
                            basename = os.path.basename(val)
                            if not basename.endswith(INPUT_TRAJECTORY_FILE_EXTENSION):
                                basename += INPUT_TRAJECTORY_FILE_EXTENSION
                            action[key] = f'files/{basename}'

                if action_type == 'load_testbed':
                    val = action.get('file')
                    if isinstance(val, str):
                        basename = os.path.basename(val)
                        action['file'] = f'files/{basename}'

                # Recurse into nested actions (groups)
                for sub_key in ('actions', 'setup_actions', 'cleanup_actions'):
                    sub = action.get(sub_key)
                    if sub is not None:
                        rewrite_actions(sub)

        for key in ('actions', 'setup_actions', 'cleanup_actions'):
            if key in definition:
                rewrite_actions(definition[key])

        return yaml.dump(definition, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def _bundle_referenced_files(self, zf, data: dict, source_dir: str) -> None:
        """Add referenced files (trajectories, testbed environments) to the zip."""
        import zipfile

        definition = data.get('definition', {})
        all_actions = []
        for key in ('actions', 'setup_actions', 'cleanup_actions'):
            actions = definition.get(key, [])
            if isinstance(actions, list):
                self._collect_actions_recursive(actions, all_actions)

        added = set()
        for action in all_actions:
            action_type = action.get('type', '')

            # Trajectory files (.bitrj)
            if action_type == 'run_trajectory':
                params = action.get('parameters', action)
                traj_ref = params.get('input_trajectory') or params.get('trajectory')
                if isinstance(traj_ref, str):
                    self._add_file_to_zip(zf, traj_ref, source_dir,
                                          INPUT_TRAJECTORY_FILE_EXTENSION, 'files', added)

            # Testbed environment files
            if action_type == 'load_testbed':
                file_ref = action.get('file')
                if isinstance(file_ref, str):
                    self._add_file_to_zip(zf, file_ref, source_dir, '.yaml', 'files', added)

            # Control config files
            if action_type == 'load_control_config':
                file_ref = action.get('file')
                if isinstance(file_ref, str):
                    self._add_file_to_zip(zf, file_ref, source_dir, '.yaml', 'files', added)

    def _collect_actions_recursive(self, actions: list, out: list) -> None:
        """Flatten nested actions into a single list."""
        for action in actions:
            out.append(action)
            sub = action.get('actions', [])
            if isinstance(sub, list):
                self._collect_actions_recursive(sub, out)

    @staticmethod
    def _add_file_to_zip(zf, name: str, source_dir: str, ext: str,
                         zip_folder: str, added: set) -> None:
        """Try to find and add a file to the zip archive."""
        if not name.endswith(ext):
            name += ext
        file_path = os.path.join(source_dir, name)
        if not os.path.isfile(file_path):
            # Try environments dir for testbed files
            file_path = os.path.join(_ENVIRONMENTS_DIR, name)
        if not os.path.isfile(file_path):
            file_path = os.path.join(_ENVIRONMENTS_DIR, os.path.basename(name))
        if os.path.isfile(file_path) and file_path not in added:
            added.add(file_path)
            zf.write(file_path, f'{zip_folder}/{os.path.basename(file_path)}')

    def _trajectory_event_callback(self, event_data, *args, **kwargs):
        """Handle trajectory_finished events from the robot."""
        data = event_data.get('data', {}) or {}
        trajectory_id = data.get('trajectory_id', None)

        self.logger.info(f"Trajectory {trajectory_id} finished.")
        self.current_trajectory = None
        self._loadedTrajectory = None
        self.events.ll_trajectory_finished.set(
            data=data,
            flags={'trajectory_id': int(trajectory_id) if trajectory_id is not None else 0}
        )
        self.events.status_changed.set(data=self.status, flags={'status': self.status})

    def _trajectory_aborted_callback(self, event_data, *args, **kwargs):
        """Handle trajectory_aborted events from the robot."""
        data = event_data.get('data', {}) or {}
        trajectory_id = data.get('trajectory_id', None)

        self.logger.warning(f"Trajectory {trajectory_id} aborted.")
        self.current_trajectory = None
        self._loadedTrajectory = None
        self.events.ll_trajectory_aborted.set(
            data=data,
            flags={'trajectory_id': int(trajectory_id) if trajectory_id is not None else 0}
        )
        self.events.status_changed.set(data=self.status, flags={'status': self.status})

    def _experiment_event_callback(self, event_data, *args, **kwargs):
        """Handle experiment events from the robot."""
        event_name = event_data.get('event', None)
        data = event_data.get('data', {}) or {}

        experiment_id = data.get('experiment_id', None)
        payload = data.get('data', None)

        self.logger.debug(f"Received experiment event \"{event_name}\" for experiment \"{experiment_id}\"")

        match event_name:
            case 'loaded':
                self.logger.debug(f"Event: Experiment \"{experiment_id}\" loaded")
                self._events_internal.experiment_loaded.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )
                # For robot-initiated experiments (not via host run_experiment),
                # update status so concurrent starts are blocked
                if self.current_experiment_definition is None:
                    self.status = BILBO_ExperimentHandler_Status.EXPERIMENT_LOADED
                    self._experiment_start_time = time.monotonic()
                    self.events.experiment_loaded.set(flags={'experiment_id': experiment_id, 'experiment_label': experiment_id})
                    self.events.status_changed.set(data=self.status, flags={'status': self.status})

            case 'started':
                self.logger.debug(f"Event: Experiment \"{experiment_id}\" started")
                # Store action summary sent by the robot
                self.experiment_actions = data.get('actions', [])
                self._events_internal.experiment_started.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )
                # For robot-initiated experiments (not via host run_experiment),
                # emit the public event so GUI callbacks fire
                if self.current_experiment_definition is None:
                    self.status = BILBO_ExperimentHandler_Status.EXPERIMENT_RUNNING
                    self._experiment_start_time = time.monotonic()
                    self.events.experiment_started.set(flags={
                        'experiment_id': experiment_id,
                        'experiment_label': experiment_id,
                    })
                    beep(frequency=1000, time_ms=400, repeats=1, volume=1)
                    speak(f"Experiment \"{experiment_id}\" started")

            case 'finished':
                self.logger.debug(f"Event: Experiment \"{experiment_id}\" finished")
                self.status = BILBO_ExperimentHandler_Status.IDLE
                self.current_experiment_definition = None
                self.experiment_actions = []
                self._experiment_start_time = None
                self._events_internal.experiment_finished.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )
                self.events.experiment_finished.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )
                beep(frequency=1000, time_ms=400, repeats=2, volume=1)
                speak(f"Experiment \"{experiment_id}\" finished")

            case 'error':
                self.logger.warning(f"Event: Experiment \"{experiment_id}\" failed")
                self.status = BILBO_ExperimentHandler_Status.IDLE
                self.current_experiment_definition = None
                self.experiment_actions = []
                self._experiment_start_time = None
                self._events_internal.experiment_error.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )
                self.events.experiment_error.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )

            case 'timeout':
                self.logger.warning(f"Event: Experiment \"{experiment_id}\" timed out")
                self.status = BILBO_ExperimentHandler_Status.IDLE
                self.current_experiment_definition = None
                self.experiment_actions = []
                self._experiment_start_time = None
                self._events_internal.experiment_timeout.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )
                self.events.experiment_timeout.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )

            case 'action_started':
                action_id = data.get('action_id', '')
                action_type = data.get('action_type', '')
                self.logger.debug(f"Event: Action \"{action_id}\" ({action_type}) started")
                self.events.action_started.set(
                    flags={'experiment_id': experiment_id, 'action_id': action_id},
                    data=data
                )

            case 'action_finished':
                action_id = data.get('action_id', '')
                action_type = data.get('action_type', '')
                action_status = data.get('action_status', '')
                self.logger.debug(f"Event: Action \"{action_id}\" ({action_type}) finished: {action_status}")
                self.events.action_finished.set(
                    flags={'experiment_id': experiment_id, 'action_id': action_id},
                    data=data
                )

            case 'message':
                text = data.get('text', '')
                level = data.get('level', 'info')
                self.logger.info(f"Experiment message [{level}]: {text}")
                self.events.experiment_message.set(
                    flags={'experiment_id': experiment_id, 'level': level},
                    data={'text': text, 'level': level},
                )

            case 'trajectory_finished':
                pass  # Handled by _trajectory_event_callback

            case _:
                self.logger.debug(f"Unknown experiment event: {event_name}")
