# =====================================================================================
#  Generates printable ArUco marker images for the robot BODY markers
#  (marker_front / marker_back in robot/definitions.py -> ARUCO_SETTINGS_*).
#
#  Uses the SAME dictionary the detectors expect (DICT_4X4_1000, see
#  ARUCO_DICT_TYPE in aruco_utils.py / the per-robot ARUCO_SETTINGS). Do NOT use
#  an online generator - a different dictionary decodes the same ID to a
#  different bit pattern (this is exactly why the body markers were moved off
#  the 0-53 grid range).
#
#  Usage:  python generate_body_markers.py
#  Output: body_marker_<robot>_<front|back>_<id>.png next to this file.
# =====================================================================================
import os

import cv2
import cv2.aruco as aruco

from aruco_utils import ARUCO_DICT_TYPE

# Kept in sync by hand with robot/definitions.py ARUCO_SETTINGS_* (that module
# pulls in the whole robot stack incl. picamera2, so we don't import it here).
BODY_MARKERS = {
    "frodo1": (900, 901),
    "frodo2": (902, 903),
    "frodo3": (904, 905),
    "frodo4": (906, 907),
}

MARKER_SIDE_PX = 600
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


if __name__ == "__main__":
    dictionary = aruco.getPredefinedDictionary(ARUCO_DICT_TYPE)
    for robot, (front_id, back_id) in BODY_MARKERS.items():
        for label, marker_id in (("front", front_id), ("back", back_id)):
            img = aruco.generateImageMarker(dictionary, marker_id, MARKER_SIDE_PX)
            out_path = os.path.join(OUTPUT_DIR, f"body_marker_{robot}_{label}_{marker_id}.png")
            cv2.imwrite(out_path, img)
            print(f"wrote {out_path}")
