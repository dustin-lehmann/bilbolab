from __future__ import annotations

import dataclasses
import enum
import math
from typing import List, Tuple, Dict

import cv2
import numpy as np

from robots.frodo.applications.utilities.measurement_model import FRODO_MeasurementModel, measurement_model_from_file
from core.utils.files import get_absolute_path

FRODO_ID = ['frodo1', 'frodo2', 'frodo3', 'frodo4']
FRODO_USER_NAME = 'admin'
FRODO_PASSWORD = 'beutlin'
FRODO_VIDEO_PORT = 5000

TESTBED_SIZE = [3, 3]
TESTBED_ORIGIN = [0, 0]
TESTBED_TILE_SIZE = 0.5


# === DATA =============================================================================================================
@dataclasses.dataclass
class FRODO_Sample_General:
    id: str
    step: int
    time: float
    battery: float
    connection_strength: float
    internet_connection: bool


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class FRODO_DynamicState:
    x: float = 0.0
    y: float = 0.0
    v: float = 0.0
    psi: float = 0.0
    psi_dot: float = 0.0


@dataclasses.dataclass
class FRODO_Estimation_Lowlevel_Data:
    speed_left: float = 0.0
    speed_right: float = 0.0


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class FRODO_Estimation_Sample:
    state: FRODO_DynamicState
    lowlevel_data: FRODO_Estimation_Lowlevel_Data


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class FRODO_ArucoMeasurement:
    measured_aruco_id: int
    position: np.ndarray
    psi: float
    uncertainty_position: np.ndarray
    uncertainty_psi: float


class ArucoDetectorStatus(enum.StrEnum):
    OK = "OK"
    ERROR = "ERROR"


@dataclasses.dataclass
class FRODO_SensorStatus:
    aruco_detector: ArucoDetectorStatus = ArucoDetectorStatus.ERROR


# ======================================================================================================================
@dataclasses.dataclass
class FRODO_Measurements_Sample:
    status: FRODO_SensorStatus
    aruco_measurements: list[FRODO_ArucoMeasurement]


@dataclasses.dataclass
class FRODO_Control_Input:
    left: float
    right: float


class NavigatorStatus(enum.StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class NavigatorElementStatus(enum.StrEnum):
    MOVING = "MOVING"
    WAITING = "WAITING"
    WAITING_FOR_EVENT = "WAITING_FOR_EVENT"
    ERROR = "ERROR"
    DONE = "DONE"


@dataclasses.dataclass
class NavigatorSample:
    status: NavigatorStatus
    element_status: NavigatorElementStatus
    current_element: dict | None
    element_queue: list[dict]
    current_element_index: int
    elements_remaining: int


@dataclasses.dataclass
class FRODO_Control_Sample:
    mode: FRODO_ControlMode
    input: FRODO_Control_Input
    navigator: NavigatorSample


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class FRODO_Sample:
    general: FRODO_Sample_General
    estimation: FRODO_Estimation_Sample
    measurements: FRODO_Measurements_Sample
    control: FRODO_Control_Sample


# ======================================================================================================================

class FRODO_ControlMode(enum.StrEnum):
    EXTERNAL = 'EXTERNAL',
    NAVIGATION = 'NAVIGATION',


# === CAMERA ===========================================================================================================

class PyCameraType(enum.StrEnum):
    V1 = 'V1',
    V2 = 'V2',
    V3 = 'V3',
    GS = 'GS',


"""
Robot overview definitions.

This module centralizes:
1) All dataclass type definitions (documented and grouped together).
2) All concrete data instantiations in one dedicated section.

Contents
--------
- Dataclasses:
    * FRODO_Physical_Model
    * FRODO_Optitrack_Settings
    * FRODO_Camera_Settings
    * FRODO_Aruco_Settings
    * FRODO_Definition
    * Static_Optitrack_Definition
    * Static_Definition

- Data:
    * OptiTrack origins (ORIGIN_FRODO, OPTITRACK_ORIGINS)
    * FRODO colors, physical model (shared), per-robot camera, OptiTrack, ArUco
    * Aggregated FRODO_DEFINITIONS (per robot)
    * Static targets (STATIC_DEFINITIONS)

- Utilities:
    * get_all_aruco_ids()
"""


# ======================================================================================================================
# === DATACLASS DEFINITIONS (Documented) ===============================================================================
# ======================================================================================================================
@dataclasses.dataclass
class FRODO_Network_Settings:
    address: str
    data_stream_port: int
    gui_port: int
    ssid: str
    username: str
    password: str


@dataclasses.dataclass
class FRODO_Physical_Model:
    """
    Physical dimensions and mechanical constants of a FRODO robot.

    Attributes
    ----------
    length : float
        Robot body length [m].
    width : float
        Robot body width [m].
    height : float
        Robot body height [m].
    aruco_marker_size : float
        Side length of ArUco markers mounted on the robot [m].
    aruco_marker_height : float
        Height/offset of the ArUco marker plane above ground [m].
    wheel_base : float
        Distance between the left and right wheel contact centers [m].
    """
    length: float
    width: float
    height: float
    aruco_marker_size: float
    aruco_marker_height: float
    wheel_base: float


@dataclasses.dataclass
class FRODO_Optitrack_Settings:
    """
    OptiTrack constellation used to infer robot pose.

    Attributes
    ----------
    points : list[int]
        IDs of the rigid-body markers associated with the robot.
    y_start : int
        Marker ID at the beginning of the robot's +Y direction.
    y_end : int
        Marker ID at the end of the robot's +Y direction.
    x_start : int
        Marker ID at the beginning of the robot's +X direction.
    """
    points: List[int]
    y_start: int
    y_end: int
    x_start: int


@dataclasses.dataclass
class FRODO_Camera_Settings:
    """
    Onboard camera configuration.

    Attributes
    ----------
    camera : PyCameraType
        Camera type/driver selector.
    fov : float
        Horizontal field of view [rad].
    resolution : tuple[int, int]
        (width, height) in pixels.
    autofocus : bool
        Whether autofocus is enabled.
    gain : float
        Analog/digital gain (driver-dependent units).
    exposure_time : int
        Exposure time (driver-dependent units, typically microseconds).
    frame_rate : int
        Target frame rate [Hz].
    image_format : str
        Pixel format (e.g., 'gray').
    camera_to_center_distance : float
        Distance from camera optical center to robot geometric center [m].
    """
    camera: PyCameraType
    fov: float
    resolution: Tuple[int, int]
    autofocus: bool
    gain: float
    exposure_time: int
    frame_rate: int
    image_format: str
    camera_to_center_distance: float


@dataclasses.dataclass
class FRODO_Aruco_Settings:
    """
    ArUco detection and marker allocation.

    Attributes
    ----------
    detection_rate : int
        Desired detection/processing rate [Hz].
    dictionary : int
        OpenCV ArUco dictionary constant, e.g., cv2.aruco.DICT_4X4_100.
    marker_size : float
        Side length of the printed markers [m].
    marker_front : int
        First marker ID allocated to the robot (inclusive).
    marker_back : int
        Last marker ID allocated to the robot (inclusive).
    """
    detection_rate: int
    dictionary: int
    marker_size: float
    marker_front: int
    marker_back: int


@dataclasses.dataclass
class FRODO_Config:
    """
    Complete FRODO robot definition.

    Attributes
    ----------
    id : str
        Robot identifier (e.g., 'frodo1').
    color : list[float]
        RGB color used for visualization, values in [0, 1].
    camera : FRODO_Camera_Settings
        Camera configuration.
    aruco : FRODO_Aruco_Settings
        ArUco configuration.
    optitrack : FRODO_Optitrack_Settings
        OptiTrack configuration.
    physical_model : FRODO_Physical_Model
        Physical parameters.
    """
    id: str
    color: List[float]
    network: FRODO_Network_Settings
    camera: FRODO_Camera_Settings
    aruco: FRODO_Aruco_Settings
    optitrack: FRODO_Optitrack_Settings
    physical_model: FRODO_Physical_Model
    measurement_model: FRODO_MeasurementModel = dataclasses.field(default_factory=FRODO_MeasurementModel)


# --- Statics (non-robot tracked targets) ------------------------------------------------------------------------------

@dataclasses.dataclass
class Static_Optitrack_Definition:
    """
    Minimal OptiTrack definition for static props/fixtures.

    Attributes
    ----------
    origin : int
        Marker ID used as the local origin.
    x_end : int
        Marker ID defining the +X direction (with origin).
    y_end : int
        Marker ID defining the +Y direction (with origin).
    """
    origin: int
    x_end: int
    y_end: int


@dataclasses.dataclass
class Static_Definition:
    """
    Static target definition with optional ArUco markers.

    Attributes
    ----------
    color : list[float]
        RGB color used for visualization, values in [0, 1].
    aruco_front : int
        First ArUco marker ID for this static target (inclusive).
    aruco_back : int
        Last ArUco marker ID for this static target (inclusive).
    optitrack : Static_Optitrack_Definition
        OptiTrack axes definition for the static target.
    """
    color: List[float]
    aruco_front: int
    aruco_back: int
    optitrack: Static_Optitrack_Definition


@dataclasses.dataclass
class TrackedOrigin_Definition:
    points: list[int]
    origin: int
    x_axis_end: int
    y_axis_end: int
    x_offset: float = 0
    y_offset: float = 0


# ======================================================================================================================
# === DATA (All concrete values below) =================================================================================
# ======================================================================================================================

# === OptiTrack: Origins ===============================================================================================
ORIGIN_FRODO_DEFINITION = TrackedOrigin_Definition(
    points=[1, 2, 3, 4, 5],
    origin=3,
    x_axis_end=2,
    y_axis_end=5,
    x_offset=0.01,
    y_offset=0.01,
)

OPTITRACK_ORIGIN: dict[str, TrackedOrigin_Definition] = {
    "origin_frodo": ORIGIN_FRODO_DEFINITION,
}

# === FRODO: Colors ====================================================================================================

FRODO_COLORS: Dict[str, List[float]] = {
    "frodo1": [217 / 255, 41 / 255, 17 / 255],  # orange
    "frodo4": [53 / 255, 97 / 255, 204 / 255],  # blue
    "frodo3": [136 / 255, 224 / 255, 4 / 255],  # green
    "frodo2": [188 / 255, 35 / 255, 201 / 222],  # purple
}

# === FRODO: Shared physical model =====================================================================================

FRODO_MODEL_GENERAL = FRODO_Physical_Model(
    length=0.3,
    width=0.3,
    height=0.3,
    aruco_marker_size=0.08,
    aruco_marker_height=0.05,
    wheel_base=0.2,
)

# === FRODO: Per-robot camera settings =================================================================================

FRODO_CAMERA_SETTINGS_FRODO1 = FRODO_Camera_Settings(
    camera=PyCameraType.GS,
    fov=np.deg2rad(120),
    resolution=(728, 544),
    camera_to_center_distance=0.0647,
    autofocus=False,
    gain=10,
    exposure_time=4000,
    frame_rate=60,
    image_format="gray",
)

FRODO_CAMERA_SETTINGS_FRODO2 = FRODO_Camera_Settings(
    camera=PyCameraType.GS,
    fov=np.deg2rad(120),
    resolution=(728, 544),
    camera_to_center_distance=0.0647,
    autofocus=False,
    gain=10,
    exposure_time=4000,
    frame_rate=60,
    image_format="gray",
)

FRODO_CAMERA_SETTINGS_FRODO3 = FRODO_Camera_Settings(
    camera=PyCameraType.GS,
    fov=np.deg2rad(90),
    resolution=(728, 544),
    camera_to_center_distance=0.0647,
    autofocus=False,
    gain=10,
    exposure_time=4000,
    frame_rate=60,
    image_format="gray",
)

FRODO_CAMERA_SETTINGS_FRODO4 = FRODO_Camera_Settings(
    camera=PyCameraType.GS,
    fov=np.deg2rad(60),
    resolution=(728, 544),
    camera_to_center_distance=0.0647,
    autofocus=False,
    gain=10,
    exposure_time=4000,
    frame_rate=60,
    image_format="gray",
)

CAMERA_SETTINGS: Dict[str, FRODO_Camera_Settings] = {
    "frodo1": FRODO_CAMERA_SETTINGS_FRODO1,
    "frodo2": FRODO_CAMERA_SETTINGS_FRODO2,
    "frodo3": FRODO_CAMERA_SETTINGS_FRODO3,
    "frodo4": FRODO_CAMERA_SETTINGS_FRODO4,
}

# === FRODO: Per-robot OptiTrack settings =============================================================================

FRODO1_OPTITRACK_SETTINGS = FRODO_Optitrack_Settings(
    points=[1, 2, 3, 4, 5],
    y_start=6,
    y_end=4,
    x_start=3,
)  # DONE

FRODO2_OPTITRACK_SETTINGS = FRODO_Optitrack_Settings(
    points=[1, 2, 3, 4, 5],
    y_start=1,
    y_end=5,
    x_start=4,
)  # DONE

FRODO3_OPTITRACK_SETTINGS = FRODO_Optitrack_Settings(
    points=[1, 2, 3, 4, 5],
    y_start=1,
    y_end=3,
    x_start=4,
)  # DONE

FRODO4_OPTITRACK_SETTINGS = FRODO_Optitrack_Settings(
    points=[1, 2, 3, 4, 5],
    y_start=2,
    y_end=4,
    x_start=5,
)  # DONE

OPTITRACK_SETTINGS: Dict[str, FRODO_Optitrack_Settings] = {
    "frodo1": FRODO1_OPTITRACK_SETTINGS,
    "frodo2": FRODO2_OPTITRACK_SETTINGS,
    "frodo3": FRODO3_OPTITRACK_SETTINGS,
    "frodo4": FRODO4_OPTITRACK_SETTINGS,
}

# === FRODO: Per-robot ArUco settings ==================================================================================

ARUCO_SETTINGS_FRODO1 = FRODO_Aruco_Settings(
    detection_rate=10,
    dictionary=cv2.aruco.DICT_4X4_100,
    marker_size=0.08,
    marker_front=18,
    marker_back=19,
)

ARUCO_SETTINGS_FRODO2 = FRODO_Aruco_Settings(
    detection_rate=10,
    dictionary=cv2.aruco.DICT_4X4_100,
    marker_size=0.08,
    marker_front=50,
    marker_back=51,
)

ARUCO_SETTINGS_FRODO3 = FRODO_Aruco_Settings(
    detection_rate=10,
    dictionary=cv2.aruco.DICT_4X4_100,
    marker_size=0.08,
    marker_front=52,
    marker_back=53,
)

ARUCO_SETTINGS_FRODO4 = FRODO_Aruco_Settings(
    detection_rate=10,
    dictionary=cv2.aruco.DICT_4X4_100,
    marker_size=0.08,
    marker_front=14,
    marker_back=15,
)

ARUCO_SETTINGS: Dict[str, FRODO_Aruco_Settings] = {
    "frodo1": ARUCO_SETTINGS_FRODO1,
    "frodo2": ARUCO_SETTINGS_FRODO2,
    "frodo3": ARUCO_SETTINGS_FRODO3,
    "frodo4": ARUCO_SETTINGS_FRODO4,
}

# ======================================================================================================================


# === FRODO: Aggregated per-robot definitions ==========================================================================
# Builds a complete FRODO_Definition for each robot from the pieces above.
#
# FRODO_DEFINITIONS: Dict[str, FRODO_Config] = {
#     rid: FRODO_Config(
#         id=rid,
#         color=FRODO_COLORS[rid],
#         camera=CAMERA_SETTINGS[rid],
#         aruco=ARUCO_SETTINGS[rid],
#         optitrack=OPTITRACK_SETTINGS[rid],
#         physical_model=FRODO_MODEL_GENERAL,
#         measurement_model=measurement_model_from_file(relativeToFullPath("./measurement_model.yaml"))
#     )
#     for rid in ("frodo1", "frodo2", "frodo3", "frodo4")
# }

# === Statics ==========================================================================================================

STATIC1_DEFINITION = Static_Definition(
    color=[0.9, 0.9, 0.9],
    aruco_front=2,
    aruco_back=3,
    optitrack=Static_Optitrack_Definition(
        origin=4,
        x_end=2,
        y_end=1,
    ),
)

STATIC2_DEFINITION = Static_Definition(
    color=[0.9, 0.9, 0.9],
    aruco_front=0,
    aruco_back=1,
    optitrack=Static_Optitrack_Definition(
        origin=4,
        x_end=2,
        y_end=1,
    ),
)

STATIC_DEFINITIONS: Dict[str, Static_Definition] = {
    "static1": STATIC1_DEFINITION,
    "static2": STATIC2_DEFINITION,
}


FRODO_ARUCO_DEFINITIONS = {
    'frodo1': ARUCO_SETTINGS_FRODO1,
    'frodo2': ARUCO_SETTINGS_FRODO2,
    'frodo3': ARUCO_SETTINGS_FRODO3,
    'frodo4': ARUCO_SETTINGS_FRODO4,
}

# ======================================================================================================================
# === UTILITIES ========================================================================================================
# ======================================================================================================================

def get_all_aruco_ids() -> List[int]:
    """
    Collect all allocated ArUco marker IDs for robots and static targets.

    Returns
    -------
    list[int]
        Sorted list of unique marker IDs across all FRODO robots and statics.
    """
    ids: List[int] = []

    # From robots (use ARUCO_SETTINGS to avoid hardcoding robot IDs)
    for robot_id, aruco in ARUCO_SETTINGS.items():
        ids.extend(range(aruco.marker_front, aruco.marker_back + 1))

    # From static definitions
    for static_id, static_def in STATIC_DEFINITIONS.items():
        ids.extend(range(static_def.aruco_front, static_def.aruco_back + 1))

    # Deduplicate and sort for stability
    return sorted(set(ids))


# ======================================================================================================================
def getObjectFromArucoId(aruco_id):
    for key, obj in FRODO_ARUCO_DEFINITIONS.items():
        if obj.marker_front == aruco_id:
            return 'frodo', key, math.pi
        elif obj.marker_back == aruco_id:
            return 'frodo', key, 0.0

    for key, obj in STATIC_DEFINITIONS.items():
        if obj.aruco_front == aruco_id:
            return 'static', key, math.pi
        elif obj.aruco_back == aruco_id:
            return 'static', key, 0.0

    return None, None, None
