"""
BILBO Experiment Module

This module provides experiment handling for BILBO robots on the host side.

Key classes:
- BILBO_ExperimentHandler: Run experiments and handle lifecycle events
- ExperimentParser: Parse experiment YAML/JSON files (from core.utils.experiments)
- ExperimentDefinition: Parsed experiment definition (from core.utils.experiments)

BILBO actions for experiment framework (host-side stubs):
- register_bilbo_actions_new(): Register BILBO actions in core ActionRegistry
- get_action_catalog(): Export action metadata for the experiment designer
- ALL_BILBO_ACTIONS_NEW: List of all BILBO ActionBase subclasses

Example usage:
    # Run experiment from YAML file
    data = handler.run_experiment_from_file("my_experiment.yaml", blocking=True)

    # Run experiment from dict
    exp = {"id": "test", "description": "Test", "timeout": 30,
           "actions": [{"type": "set_mode", "mode": "BALANCING"},
                       {"type": "wait_time", "time": 5.0},
                       {"type": "set_mode", "mode": "OFF"}]}
    data = handler.run_experiment(exp, blocking=True)
"""

# Core experiment types (re-exported for convenience)
from core.utils.experiments import (
    ExperimentStatus,
    ActionStatus,
    ExperimentActionData,
    ExperimentResult,
    ExperimentResultMeta,
)

# BILBO-specific data structures (trajectories, result types, file I/O)
from robots.bilbo.robot.experiment.experiment_definitions import (
    # BILBO result types
    BILBO_ExperimentContext,
    BILBO_ExperimentResult,

    # Trajectories
    InputTrajectory,
    InputTrajectoryStep,
    StateTrajectory,
    TrajectoryData,
    OutputTrajectory,
    ModelVector,

    # File I/O
    InputTrajectoryFileData,
    OutputTrajectoryFileData,
    ModelVectorFileData,
    INPUT_TRAJECTORY_FILE_EXTENSION,
    OUTPUT_TRAJECTORY_FILE_EXTENSION,
    MODEL_VECTOR_FILE_EXTENSION,
    write_input_file,
    read_input_file,
    write_output_file,
    read_output_file,
    write_model_vector_file,
    read_model_vector_file,
)

# Experiment handler
from robots.bilbo.robot.experiment.bilbo_experiment_handler import (
    BILBO_ExperimentHandler,
    BILBO_ExperimentHandler_Events,
    BILBO_ExperimentHandler_Status,
)

# New experiment framework (parser + definition)
from core.utils.experiments.parser import ExperimentParser
from core.utils.experiments.experiment import ExperimentDefinition

# BILBO actions for new experiment framework (host-side stubs)
from robots.bilbo.robot.experiment.bilbo_actions import (
    register_bilbo_actions as register_bilbo_actions_new,
    ALL_BILBO_ACTIONS as ALL_BILBO_ACTIONS_NEW,
    get_action_catalog,
    ACTION_CATEGORIES,
)

# Multi-trial experiments (host-side proxies)
from robots.bilbo.robot.experiment.dilc import (
    DILC_Experiment,
    DILC_Experiment_Settings,
    DILC_Experiment_State,
    DILC_Experiment_Events,
    DILC_Trial_Result,
    DILC_Trajectory_Data,
    DILC_Trial_Data,
    DILC_Results,
    DILC_Results_Meta,
    DILC_InitialConditions,
    DILC_Experiment_Meta_Settings,
    FIR_Design_Params,
    load_dilc_settings_from_yaml,
)

__all__ = [
    # Core experiment types (re-exported)
    "ExperimentStatus",
    "ActionStatus",
    "ExperimentActionData",
    "ExperimentResult",
    "ExperimentResultMeta",

    # BILBO result types
    "BILBO_ExperimentContext",
    "BILBO_ExperimentResult",

    # Trajectories
    "InputTrajectory",
    "InputTrajectoryStep",
    "StateTrajectory",
    "TrajectoryData",
    "OutputTrajectory",
    "ModelVector",

    # File I/O
    "InputTrajectoryFileData",
    "OutputTrajectoryFileData",
    "ModelVectorFileData",
    "INPUT_TRAJECTORY_FILE_EXTENSION",
    "OUTPUT_TRAJECTORY_FILE_EXTENSION",
    "MODEL_VECTOR_FILE_EXTENSION",
    "write_input_file",
    "read_input_file",
    "write_output_file",
    "read_output_file",
    "write_model_vector_file",
    "read_model_vector_file",

    # Handler
    "BILBO_ExperimentHandler",
    "BILBO_ExperimentHandler_Events",
    "BILBO_ExperimentHandler_Status",

    # New experiment framework
    "ExperimentParser",
    "ExperimentDefinition",

    # BILBO actions (new experiment framework)
    "register_bilbo_actions_new",
    "ALL_BILBO_ACTIONS_NEW",
    "get_action_catalog",
    "ACTION_CATEGORIES",

    # Multi-trial experiments
    "DILC_Experiment",
    "DILC_Experiment_Settings",
    "DILC_Experiment_State",
    "DILC_Experiment_Events",
    "DILC_Trial_Result",
    "DILC_Trajectory_Data",
    "DILC_Trial_Data",
    "DILC_Results",
    "DILC_Results_Meta",
    "DILC_InitialConditions",
    "DILC_Experiment_Meta_Settings",
    "FIR_Design_Params",
    "load_dilc_settings_from_yaml",
]
