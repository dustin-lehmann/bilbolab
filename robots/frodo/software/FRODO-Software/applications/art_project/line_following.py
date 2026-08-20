# =====================================================================================
#  Robot-independent line following: image processing + differential-drive control math.
#  Only needs a camera frame (RGB) and a track_width (m) - nothing FRODO-specific
#  here, so this can be reused on other robots as-is.
# =====================================================================================
import cv2
import numpy as np

# --- IMAGE PROCESSING ---
ROI_TOP = 0.55          # look at the bottom 45% of the image (= how far ahead we look)
MIN_AREA = 800          # blobs smaller than this are noise

# --- KINEMATIC LIMITS ---
MAX_OMEGA = 1.5         # rad/s
V_WHEEL_MAX = 0.25      # m/s - tune to your motor's real maximum


def get_color_mask(frame, target_color):
    """frame: RAW camera frame (RGB). Must NOT have anything drawn on it!"""
    if frame.ndim == 2:
        bgr_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    else:
        bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    hsv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2HSV)

    if target_color == "pink":
        lower_bound = np.array([140, 50, 50])
        upper_bound = np.array([179, 255, 255])
    elif target_color == "green":
        lower_bound = np.array([40, 100, 100])
        upper_bound = np.array([80, 255, 255])
    elif target_color == "blue":
        lower_bound = np.array([100, 100, 100])
        upper_bound = np.array([130, 255, 255])
    else:
        raise ValueError("Unknown color! Only use 'pink', 'green' or 'blue'.")

    mask = cv2.inRange(hsv, lower_bound, upper_bound)
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    return mask


def find_line(mask):
    """Finds the largest valid contour on the mask, does NOT draw anything (used
    for color probing). Returns: (error, area, cx, cy, c_shifted) or None (no
    line found / too small)."""
    h_img, w_img = mask.shape[:2]
    y0 = int(h_img * ROI_TOP)

    roi_mask = mask[y0:, :]
    contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if len(contours) == 0:
        return None

    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)

    if area < MIN_AREA:
        return None

    M = cv2.moments(c)
    if M["m00"] == 0:
        return None

    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"]) + y0      # add the ROI offset back

    camera_center = w_img // 2
    error = cx - camera_center
    c_shifted = c + np.array([[[0, y0]]])

    return error, area, cx, cy, c_shifted


def calculate_deviation(mask, frame):
    """mask: mask built from the raw frame. frame: frame to draw the overlay on."""
    h_img, w_img = mask.shape[:2]
    y0 = int(h_img * ROI_TOP)

    # always draw the ROI boundary
    cv2.line(frame, (0, y0), (w_img, y0), (255, 255, 0), 2)

    found = find_line(mask)
    if found is None:
        cv2.putText(frame, "LINE LOST", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        return 0.0, False, 0.0

    error, area, cx, cy, c_shifted = found
    camera_center = w_img // 2

    # --- visualization ---
    cv2.drawContours(frame, [c_shifted], -1, (0, 255, 0), 2)
    cv2.circle(frame, (cx, cy), 8, (255, 0, 0), -1)
    cv2.line(frame, (camera_center, 0), (camera_center, h_img), (0, 255, 255), 2)
    cv2.line(frame, (camera_center, cy), (cx, cy), (0, 0, 255), 3)
    cv2.putText(frame, f"Error: {error} px  Area: {int(area)}", (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    return error, True, area


def proportional_controller(error, kp, base_speed):
    abs_error = abs(error)

    if abs_error > 120:
        forward_speed = base_speed * 0.2
    elif abs_error > 60:
        forward_speed = base_speed * 0.5
    else:
        forward_speed = base_speed

    angular_speed = float(np.clip(-kp * error, -MAX_OMEGA, MAX_OMEGA))
    return forward_speed, angular_speed


def calculate_wheel_speeds(forward_speed, angular_speed, track_width):
    half_w = 0.5 * track_width
    v_left = forward_speed - half_w * angular_speed
    v_right = forward_speed + half_w * angular_speed

    # saturate by scaling, not clipping -> keeps the curvature (vL/vR ratio) intact
    peak = max(abs(v_left), abs(v_right))
    if peak > V_WHEEL_MAX:
        s = V_WHEEL_MAX / peak
        v_left *= s
        v_right *= s

    return v_left, v_right
