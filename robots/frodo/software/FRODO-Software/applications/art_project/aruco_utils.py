# =====================================================================================
#  Robot-independent ArUco detection helpers. Only needs a gray frame - nothing
#  FRODO-specific here, so this can be reused on other robots.
# =====================================================================================
import cv2.aruco as aruco

# ArUco dictionary in use. Marker IDs must have been generated with this dictionary.
ARUCO_DICT_TYPE = aruco.DICT_4X4_50

# detectMarkers() is slow when scanning the whole frame; that delay makes the robot
# overshoot an intersection and miss the turn. Only scan the bottom region (markers
# are never expected in the top part anyway).
ARUCO_SCAN_Y_MIN = 0.10


def create_aruco_detector(dict_type=ARUCO_DICT_TYPE):
    aruco_dictionary = aruco.getPredefinedDictionary(dict_type)
    aruco_detector_params = aruco.DetectorParameters()
    return aruco.ArucoDetector(aruco_dictionary, aruco_detector_params)


def detect_markers(aruco_detector, gray_frame, scan_y_min_ratio=ARUCO_SCAN_Y_MIN):
    """gray_frame: FULL-size, single-channel (gray) frame. Only scans the bottom
    scan_y_min_ratio region (for performance) and re-aligns the pixel coordinates
    back to the full frame.
    Returns: (detected_markers, scan_y0) - detected_markers = [(id, corners), ...]
    corners: shape (1, 4, 2), pixel coordinates relative to the full frame."""
    h_img = gray_frame.shape[0]
    scan_y0 = int(scan_y_min_ratio * h_img)
    corners_list, ids_arr, _rejected = aruco_detector.detectMarkers(gray_frame[scan_y0:, :])

    if ids_arr is None:
        return [], scan_y0

    aligned_corners = [c + [[0, scan_y0]] for c in corners_list]
    return list(zip(ids_arr.flatten().tolist(), aligned_corners)), scan_y0


def marker_bbox(marker_corners):
    """marker_corners: shape (1, 4, 2), pixel coordinates relative to the full frame.
    Returns: (x, y, w, h, center_x, center_y, size)."""
    pts = marker_corners.reshape(4, 2)
    x = int(pts[:, 0].min())
    x_max = int(pts[:, 0].max())
    y = int(pts[:, 1].min())
    y_max = int(pts[:, 1].max())
    w, h = x_max - x, y_max - y
    center_x = x + w // 2
    center_y = y + h // 2
    size = max(w, h)
    return x, y, w, h, center_x, center_y, size
