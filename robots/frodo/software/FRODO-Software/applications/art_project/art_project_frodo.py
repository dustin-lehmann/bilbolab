# =====================================================================================
#  FRODO - Line Following + ArUco Grid Navigation
#  TEST VERSION v2: straight-drive test (ID 1 -> ID 3, no turns) + ArUco console log
# =====================================================================================
import time
import threading
import cv2
import numpy as np

from robot.frodo import FRODO
from robot.control.frodo_control import FRODO_ControlMode
from robot.utilities.video_streamer.video_streamer import VideoStreamer
from core.utils.network import getInterfaceIP
from hardware.hardware.servo import HardwareServo
from pose_estimator import PoseEstimator, wrap_pi, MARKER_WORLD_MAP
from line_following import (
    get_color_mask, find_line, calculate_deviation,
    proportional_controller, calculate_wheel_speeds,
)
from aruco_utils import (
    ARUCO_DICT_TYPE, ARUCO_SCAN_Y_MIN,
    create_aruco_detector, detect_markers, marker_bbox,
)
from servo_trigger import ArucoServoTrigger

# --- WEB STREAMING ---
stream_frame_lock = threading.Lock()
frame_out = None

# --- SERVO TRIGGER (on specific ArUco IDs) ---
# First verify the pin/servo with servo_test.py.
SERVO_PIN = 19                 # BCM GPIO19 - verified with the servo_pin_scan.py sweep
SERVO_ANGLE_HOME = 0
SERVO_ANGLE_TRIGGER = 90
SERVO_TRIGGER_IDS = {9}        # seeing one of these IDs triggers the servo action
SERVO_FORWARD_DURATION = 1.5   # seconds - drive straight this long after the servo turns
SERVO_RETRIGGER_COOLDOWN = 5.0 # so passing the same marker doesn't retrigger it over and over
# When a marker is first seen, the robot is not yet lined up with it (the camera
# sees it ahead of time) - close this distance open-loop (without looking at the
# image) before triggering the servo. Measure in the field and adjust as needed.
SERVO_TRIGGER_APPROACH_DISTANCE_M = 0.16

# --- ARUCO FILTERS ---
# The DECISION (direction/target) is made as soon as a marker is ACCEPTED - but
# it isn't APPLIED right away, the robot first drives straight for ADVANCE_TIME
# (see ADVANCING_TO_TURN/PARKING below). These two solve different problems:
# decisions used to be made way too early, because ARUCO_Y_MIN=0.15 was loose
# enough that a marker got ACCEPTED while still in the middle of the path
# (observed in the field: decided at size~80-100px, even though a marker at an
# intersection could grow to 150-170px) - fixed by adding a hard floor on pixel
# SIZE (ARUCO_MIN_SIZE_PX). The decision now fires at the right time, but the
# robot may not physically be at the exact center of the intersection/marker yet
# - that last step is finished by ADVANCE_TIME (driving straight open-loop,
# WITHOUT looking at the image).
ARUCO_Y_MIN = 0.15         # markers below this height are "too far away"
ARUCO_MIN_SIZE_PX = 160    # markers smaller than this (i.e. far away) are NOT accepted
ARUCO_X_MIN = 0.10         # left edge of the lane window
ARUCO_X_MAX = 0.90         # right edge of the lane window

ARRIVE_DISTANCE_M = 0.06   # "arrived" once the EKF (x,y) is this close (m) to the target marker's world position
APPROACH_TIMEOUT = 6.0     # safety net: stop anyway if we haven't arrived within this time
APPROACH_STALL_GRACE = 0.5 # if the line has been lost this long (robot already stopped), call it "arrived" right away

# detectMarkers() is slow when scanning the whole frame; that delay makes the
# robot overshoot an intersection and miss the turn. Only scan the bottom region
# (markers are never expected in the top part anyway).
ARUCO_LOG_PERIOD = 0.5     # log a marker at most twice per second

# --- CLOSED-LOOP TURNING (EKF psi feedback) ---
# The grid directions line up with the EKF's world frame (see MARKER_WORLD_MAP):
# +x = EAST, +y = NORTH. Instead of a blind timed turn, we turn to a target psi with a PI controller.
HEADING_TO_PSI = {
    "EAST": 0.0,
    "NORTH": np.pi / 2,
    "WEST": np.pi,
    "SOUTH": -np.pi / 2,
}
TURN_KP = 1.2               # rad/s per rad of error
TURN_KI = 0.4                # integral gain - overcomes friction/static error
TURN_I_LIMIT = 0.5           # clamp on the integral term's contribution (rad/s)
TURN_OMEGA_MAX = 1.0         # max angular speed allowed while turning (rad/s)
TURN_TOLERANCE = np.radians(4.0)   # tolerance for "reached the target"
TURN_SETTLE_TIME = 0.15      # stay within tolerance this long before calling the turn done (noise rejection)

# After a turn/park decision is made, the robot keeps driving STRAIGHT (WITHOUT
# looking at the image) for this long, open-loop - so it ends up at the exact
# center of the intersection/marker. Now that ARUCO_MIN_SIZE_PX already makes the
# decision fire close to the intersection (fixed the old "turning too early"
# issue), this short advance is safe: since it never looks at the image at all,
# there's no risk of intersection/marker contours steering line-following the
# wrong way (the old design used line-following here and that caused a "two-step"
# wobble).
ADVANCE_TIME = 1.0   # seconds


def main():
    global frame_out

    # ---------------- 1. ROBOT ----------------
    frodo = FRODO()
    frodo.init()
    frodo.start()
    frodo.control.setMode(FRODO_ControlMode.EXTERNAL)

    # ---------------- 2. STREAM ----------------
    def get_stream_frame():
        with stream_frame_lock:
            if frame_out is not None:
                return frodo.sensors.camera.getImageBufferBytes(frame_out)
            return None

    streamer = VideoStreamer(image_fetcher=get_stream_frame, port=5001)
    streamer.start()
    ip = getInterfaceIP("wlan0")
    print(f"\n---> LIVE: http://{ip}:5001/preview <--- \n")

    # ---------------- 3. PARAMETERS ----------------
    CURRENT_TARGET_COLOR = "pink"
    kp = 0.008
    base_speed = 0.08           # kept low for the straight-drive test
    track_width = 0.150

    ROBOT_STATE = "FOLLOWING"
    ROBOT_HEADING = "EAST"      # placeholder until the first marker is read; real calibration happens below
    TARGET_COORD = (2, 1)
    LAST_SEEN_ID = None

    # Once we decide "arrived" at the target, the robot keeps driving straight
    # OPEN-LOOP (without looking at the image) for PARKING_TIME before stopping -
    # so it ends up at the exact center of the marker (see the ADVANCE_TIME note above).
    PARKING_TIME = ADVANCE_TIME + 0.5
    stop_timer = 0

    # APPROACHING state: a direction decision was made but not yet APPLIED. Line
    # following keeps running until the EKF (x,y) gets close to the marker's world
    # position (pending_node_xy), then pending_action is applied ONCE (see the note above).
    pending_action = None        # "TARGET" | None
    pending_node_xy = None
    approach_start = None
    last_approach_log = 0.0
    approach_line_lost_since = None

    # ADVANCING_TO_TURN: a turn decision was made, the robot keeps driving straight
    # for ADVANCE_TIME, then the turn actually starts (see the note above).
    pre_turn_next_state = None   # "TURNING_LEFT" | "TURNING_RIGHT"
    pre_turn_start = None

    # SERVO_APPROACHING/SERVO_ADVANCING: starts once the servo trigger ID is seen
    # (see the SERVO_* constants above). Same idea as ADVANCING_TO_TURN - open-loop
    # driving, but ArUco scanning/grid decisions KEEP RUNNING during this too (see
    # the widened status check below) - in the field, the earlier design (which
    # blocked the whole action in one go) made the robot miss the next grid marker
    # during its ~4s of blind driving and navigate to the wrong place.
    servo_phase_start = None

    turn_start = None
    turn_last_time = None
    turn_i_acc = 0.0
    turn_settle_start = None
    turn_target_psi = None
    TURN_TARGET_HEADING = None   # set once a turn decision is made (see the decision block)
    STOP_REASON = None      # "TARGET" or "TURN_TIMEOUT" - distinguishes the STOPPED message
    last_turn_log = 0.0     # throttles the diagnostic log while turning

    # Closed-loop turning (via EKF psi) no longer depends on a time estimate;
    # this is only a safety net in case the PI never converges at all.
    TURN_TIMEOUT = 10.0

    # Marker ID -> grid coordinate. PLACEHOLDER: the real ID/coordinate mapping
    # will be assigned once the markers are placed in the field.
    CITY_MAP = {
        0: (0, 0), 1: (1, 0), 2: (2, 0),
        3: (0, 1), 4: (1, 1), 5: (2, 1),
        6: (0, 2), 7: (1, 2), 8: (2, 2),
    }

    # ---------------- 3b. ARUCO DETECTOR ----------------
    aruco_detector = create_aruco_detector(ARUCO_DICT_TYPE)

    # ---------------- 3d. SERVO TRIGGER (ID9 -> rotate 90 degrees -> forward -> rotate back) ----------------
    servo = HardwareServo(pin=SERVO_PIN)
    servo_trigger = ArucoServoTrigger(
        servo, frodo.control.setTrackSpeed,
        trigger_ids=SERVO_TRIGGER_IDS,
        angle_home=SERVO_ANGLE_HOME, angle_trigger=SERVO_ANGLE_TRIGGER,
        forward_speed=base_speed, forward_duration=SERVO_FORWARD_DURATION,
        approach_distance_m=SERVO_TRIGGER_APPROACH_DISTANCE_M,
        cooldown=SERVO_RETRIGGER_COOLDOWN,
    )

    print("Autonomous Grid Navigation Started (ArUco Marker Mode).")
    print(f"Target: {TARGET_COORD} | Heading: {ROBOT_HEADING} | base_speed: {base_speed}")
    print("Press Ctrl+C to stop.\n")

    shape_printed = False
    last_aruco_log = 0.0

    # ---------------- 3c. POSE ESTIMATION (EKF: prediction + ArUco correction) ----------------
    # PoseEstimator in pose_estimator.py: predicts at 100 Hz from wheel odometry,
    # applies an EKF correction using measurements from frodo.sensors.aruco_detector
    # (which it converts itself from the camera frame into the robot frame). For
    # now this is ONLY shown on screen - it does NOT drive the FSM/turn decisions,
    # that logic still relies on the pixel-based ArUco detection.
    pose_est = PoseEstimator(frodo, verbose=False)
    pose_est.start()

    try:
        while True:
            frame = frodo.sensors.camera.events.frame.get_data()
            if frame is None:
                continue

            display_frame = frame.copy()
            h_img, w_img = display_frame.shape[:2]

            if not shape_printed:
                print(f">>> Frame size: {w_img} x {h_img}")
                shape_printed = True

            # ---------------- EKF POSE OVERLAY (visual sanity check only) ----------------
            pose_x, pose_y, pose_psi = pose_est.get()
            cv2.putText(display_frame,
                        f"EKF x={pose_x:+.2f}m y={pose_y:+.2f}m psi={np.degrees(pose_psi):+.0f}deg",
                        (10, h_img - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)

            # ---------------- STOPPED ----------------
            if ROBOT_STATE == "STOPPED":
                frodo.control.setTrackSpeed(0.0, 0.0)
                if STOP_REASON == "TARGET":
                    cv2.putText(display_frame, "DESTINATION REACHED", (60, 200),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 4)
                    print("\n*** MISSION ACCOMPLISHED. Motors locked. ***")
                else:
                    cv2.putText(display_frame, "FAILED: TURN TIMEOUT", (60, 200),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 4)
                    print(f"\n!!! MISSION FAILED ({STOP_REASON}). Motors locked. !!!")
                with stream_frame_lock:
                    frame_out = display_frame
                break

            # ================= ARUCO DETECTION =================
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)      # from the RAW frame
            detected_markers, _aruco_scan_y0 = detect_markers(aruco_detector, gray, ARUCO_SCAN_Y_MIN)

            now = time.time()
            log_aruco = (now - last_aruco_log) > ARUCO_LOG_PERIOD
            if log_aruco:
                last_aruco_log = now
                if not detected_markers:
                    print(f"[{now:.1f}] ArUco: none visible")

            # ---------------- SERVO TRIGGER (ID9 etc.) ----------------
            # Independent of grid navigation: ID9 isn't in CITY_MAP so it never
            # enters the decision loop below, which is why it's checked separately
            # and first. Only triggers while driving straight (FOLLOWING) - so it
            # doesn't clash with the robot's position/speed during a turn/park/approach.
            # Driving (approach + forward-after-trigger) happens in the
            # SERVO_APPROACHING/SERVO_ADVANCING states, inside the frame loop below -
            # so ArUco scanning/grid decisions are never interrupted during it (see
            # the note at the top of servo_trigger.py).
            if ROBOT_STATE == "FOLLOWING":
                detected_ids_now = [detected_id for detected_id, _ in detected_markers]
                servo_matched_id = servo_trigger.matching_id(detected_ids_now, now)
                if servo_matched_id is not None:
                    print(f"[{now:.1f}] Trigger ArUco ID seen: {servo_matched_id} - approaching marker")
                    servo_trigger.mark_triggered(now)
                    servo_phase_start = now
                    ROBOT_STATE = "SERVO_APPROACHING"

            for detected_id, marker_corners in detected_markers:
                # marker_corners: shape (1, 4, 2) - pixel coordinates relative to the full frame
                x, y, w_r, h_r, center_x, center_y, aruco_size = marker_bbox(marker_corners)

                cv2.rectangle(display_frame, (x, y), (x + w_r, y + h_r), (255, 0, 255), 3)
                cv2.putText(display_frame, f"{detected_id} ({aruco_size}px)", (x, max(y - 10, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

                # --- filter decision ---
                if center_y < ARUCO_Y_MIN * h_img or aruco_size < ARUCO_MIN_SIZE_PX:
                    status = "TOO FAR"
                elif center_x < ARUCO_X_MIN * w_img or center_x > ARUCO_X_MAX * w_img:
                    status = "WRONG LANE"
                elif detected_id not in CITY_MAP:
                    status = "NOT ON MAP"
                elif detected_id == LAST_SEEN_ID:
                    status = "already processed"
                elif ROBOT_STATE not in ("FOLLOWING", "SERVO_APPROACHING", "SERVO_ADVANCING"):
                    # SERVO_APPROACHING/SERVO_ADVANCING included: don't miss a grid
                    # decision even while driving open-loop for the servo (see the
                    # servo_phase_start note above).
                    status = f"state={ROBOT_STATE}"
                else:
                    status = "ACCEPTED"

                if log_aruco:
                    print(f"[{now:.1f}] ArUco {detected_id!r:6} "
                          f"center=({center_x:4d},{center_y:4d}) size={aruco_size:3d}px "
                          f"-> {status}")

                if status == "TOO FAR":
                    cv2.putText(display_frame, f"ArUco {detected_id}: TOO FAR", (10, 80),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    continue

                if status == "WRONG LANE":
                    cv2.putText(display_frame, f"ArUco {detected_id}: WRONG LANE", (10, 120),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2)
                    continue

                cv2.putText(display_frame, f"ArUco ID: {detected_id} DETECTED", (10, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                if status != "ACCEPTED":
                    continue

                # ---------------- DECISION MAKING ----------------
                current_coord = CITY_MAP[detected_id]
                is_initial_fix = LAST_SEEN_ID is None      # robot is learning its position for the first time
                LAST_SEEN_ID = detected_id

                print(f"\n[{now:.1f}] NODE {detected_id} -> {current_coord}")

                if current_coord == TARGET_COORD:
                    print(f"*** TARGET NODE SEEN - approaching marker center before parking ***")
                    pending_action = "TARGET"
                    pending_node_xy = MARKER_WORLD_MAP.get(detected_id)
                    approach_start = now
                    ROBOT_STATE = "APPROACHING"
                    break

                dx = TARGET_COORD[0] - current_coord[0]
                dy = TARGET_COORD[1] - current_coord[1]

                if dx > 0:
                    desired_heading = "EAST"
                elif dx < 0:
                    desired_heading = "WEST"
                elif dy > 0:
                    desired_heading = "NORTH"
                else:
                    desired_heading = "SOUTH"

                if is_initial_fix:
                    # ROBOT_HEADING started out as just a guess (always "EAST").
                    # If the robot is placed on a marker other than (0,0), that
                    # guess can be wrong. Now that we know the real position from
                    # the first marker read, calibrate straight to the real
                    # heading instead of attempting a turn.
                    ROBOT_HEADING = desired_heading
                    CURRENT_TARGET_COLOR = "pink" if desired_heading in ("EAST", "WEST") else "green"
                    print(f"Initial fix: position={current_coord} -> heading calibrated to: {ROBOT_HEADING} "
                          f"(color={CURRENT_TARGET_COLOR})")
                    break

                print(f"Heading: {ROBOT_HEADING} -> Desired: {desired_heading}")

                if ROBOT_HEADING == desired_heading:
                    print("Action: CONTINUE")
                else:
                    # The turn does NOT start immediately: since ARUCO_MIN_SIZE_PX
                    # already makes the decision fire close to the intersection,
                    # the robot first drives straight for ADVANCE_TIME OPEN-LOOP
                    # (without looking at the image) to reach the exact center of
                    # the intersection, then the turn actually begins.
                    TURN_TARGET_HEADING = desired_heading
                    if (ROBOT_HEADING, desired_heading) in [
                        ("EAST", "SOUTH"), ("SOUTH", "WEST"),
                        ("WEST", "NORTH"), ("NORTH", "EAST"),
                    ]:
                        pre_turn_next_state = "TURNING_RIGHT"
                        print("Action: TURN RIGHT (after short advance)")
                    elif (ROBOT_HEADING, desired_heading) in [
                        ("EAST", "NORTH"), ("NORTH", "WEST"),
                        ("WEST", "SOUTH"), ("SOUTH", "EAST"),
                    ]:
                        pre_turn_next_state = "TURNING_LEFT"
                        print("Action: TURN LEFT (after short advance)")
                    else:
                        print("!!! 180 degree turn required - not supported")
                        pre_turn_next_state = None

                    # NOTE: CURRENT_TARGET_COLOR is NOT changed here - the robot is
                    # still coming from the old position during ADVANCING_TO_TURN,
                    # the color only switches once the turn actually starts.
                    ROBOT_HEADING = desired_heading

                    if pre_turn_next_state is not None:
                        pre_turn_start = now
                        ROBOT_STATE = "ADVANCING_TO_TURN"

                break

            # ================= LINE FOLLOWING =================
            if ROBOT_STATE in ("FOLLOWING", "APPROACHING"):
                if LAST_SEEN_ID is None and ROBOT_STATE == "FOLLOWING":
                    # No marker read yet -> we don't know which color line we're
                    # on (the default "pink" is just a placeholder). Try both
                    # colors and follow whichever is visible, so we can still
                    # reach a marker even if we start on the green path.
                    best_color, best_found = None, None
                    for probe_color in ("pink", "green"):
                        found = find_line(get_color_mask(frame, probe_color))
                        if found is not None and (best_found is None or found[1] > best_found[1]):
                            best_color, best_found = probe_color, found
                    if best_color is not None:
                        CURRENT_TARGET_COLOR = best_color

                mask = get_color_mask(frame, CURRENT_TARGET_COLOR)          # RAW frame!
                error, line_detected, _area = calculate_deviation(mask, display_frame)

                if line_detected:
                    forward_speed, angular_speed = proportional_controller(error, kp, base_speed)
                    v_left, v_right = calculate_wheel_speeds(forward_speed, angular_speed, track_width)
                    frodo.control.setTrackSpeed(v_left, v_right)
                else:
                    frodo.control.setTrackSpeed(0.0, 0.0)

                if ROBOT_STATE == "APPROACHING":
                    # Only used for the target marker (see the TARGET REACHED
                    # decision) - since it's one-shot, the EKF-drift risk that
                    # exists for intermediate turns doesn't apply here.
                    if pending_node_xy is None:
                        dist_to_node = 0.0     # not in MARKER_WORLD_MAP - apply immediately
                    else:
                        dist_to_node = float(np.hypot(pending_node_xy[0] - pose_x, pending_node_xy[1] - pose_y))

                    approach_elapsed = now - approach_start
                    cv2.putText(display_frame, f"APPROACHING TARGET {dist_to_node:.2f}m",
                                (10, 190), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)

                    if (now - last_approach_log) > 0.3:
                        last_approach_log = now
                        print(f"  [APPROACH {approach_elapsed:.2f}s] target_xy={pending_node_xy} "
                              f"ekf=({pose_x:+.2f},{pose_y:+.2f}) distance={dist_to_node:.3f}m")

                    # Once the line is lost, the robot is already stopped (setTrackSpeed(0,0)
                    # above) - in that case the EKF distance also stops changing, so it may
                    # never drop below ARRIVE_DISTANCE_M and we'd wait uselessly until
                    # APPROACH_TIMEOUT (6s) (observed in the field: "DESTINATION REACHED"
                    # was delayed by 3-5s). If the robot is REALLY not moving (line lost),
                    # call it "arrived" after a short grace period instead - waiting longer buys nothing.
                    if line_detected:
                        approach_line_lost_since = None
                        stalled = False
                    else:
                        if approach_line_lost_since is None:
                            approach_line_lost_since = now
                        stalled = (now - approach_line_lost_since) > APPROACH_STALL_GRACE

                    arrived = dist_to_node <= ARRIVE_DISTANCE_M
                    timed_out = approach_elapsed > APPROACH_TIMEOUT
                    if timed_out and not arrived:
                        print(f"!!! APPROACH TIMEOUT ({APPROACH_TIMEOUT}s) - EKF distance stayed at "
                              f"{dist_to_node:.3f}m, stopping anyway")
                    elif stalled and not arrived:
                        print(f"Line lost, robot stopped ({dist_to_node:.3f}m) - wait ended early")

                    if arrived or timed_out or stalled:
                        print(f"*** MARKER CENTER REACHED ({dist_to_node:.3f}m). "
                              f"Parking for {PARKING_TIME}s ***")
                        frodo.control.setTrackSpeed(0.0, 0.0)
                        ROBOT_STATE = "PARKING"
                        STOP_REASON = "TARGET"
                        stop_timer = time.time() + PARKING_TIME
                        pending_action = None
                        pending_node_xy = None
                        approach_line_lost_since = None

            # ================= SHORT STRAIGHT ADVANCE TO INTERSECTION =================
            # We do NOT look at the image at all - just drive forward at a fixed
            # speed (see the ADVANCE_TIME note above). We leave the actual turning
            # ENTIRELY to the psi PI controller.
            elif ROBOT_STATE == "ADVANCING_TO_TURN":
                advance_elapsed = now - pre_turn_start
                frodo.control.setTrackSpeed(base_speed, base_speed)
                cv2.putText(display_frame, f"ADVANCING {advance_elapsed:.1f}s -> {TURN_TARGET_HEADING}",
                            (10, 190), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)

                if advance_elapsed >= ADVANCE_TIME:
                    print(f"Reached intersection ({advance_elapsed:.2f}s) -> turn starting")
                    # The color switches now: the turn is actually starting, the
                    # robot will look for the new direction's color instead of
                    # the old path's.
                    CURRENT_TARGET_COLOR = "pink" if TURN_TARGET_HEADING in ("EAST", "WEST") else "green"
                    frodo.control.setTrackSpeed(0.0, 0.0)
                    ROBOT_STATE = pre_turn_next_state
                    turn_start = None
                    pre_turn_next_state = None

            # ================= SERVO: APPROACHING THE MARKER =================
            # Same open-loop idea as ADVANCING_TO_TURN (driving WITHOUT looking at
            # the image, just a fixed forward speed) - the difference: ArUco
            # scanning/grid decisions KEEP RUNNING during this too (see the widened
            # status check above), the servo itself hasn't moved yet.
            elif ROBOT_STATE == "SERVO_APPROACHING":
                servo_elapsed = now - servo_phase_start
                frodo.control.setTrackSpeed(servo_trigger.forward_speed, servo_trigger.forward_speed)
                cv2.putText(display_frame, f"SERVO APPROACH {servo_elapsed:.1f}s",
                            (10, 190), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)

                if servo_elapsed >= servo_trigger.approach_time:
                    print(f"Reached the metronome ({servo_elapsed:.2f}s) -> triggering servo")
                    frodo.control.setTrackSpeed(0.0, 0.0)
                    time.sleep(servo_trigger.pre_stop_delay)   # robot is STOPPED - covers no distance
                    servo_trigger.rotate_to_trigger()          # blocking, short (~settle_time), robot stopped
                    servo_phase_start = now
                    ROBOT_STATE = "SERVO_ADVANCING"

            # ================= SERVO: SHORT FORWARD AFTER TRIGGERING =================
            elif ROBOT_STATE == "SERVO_ADVANCING":
                servo_elapsed = now - servo_phase_start
                frodo.control.setTrackSpeed(servo_trigger.forward_speed, servo_trigger.forward_speed)
                cv2.putText(display_frame, f"SERVO FORWARD {servo_elapsed:.1f}s",
                            (10, 190), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)

                if servo_elapsed >= servo_trigger.forward_duration:
                    frodo.control.setTrackSpeed(0.0, 0.0)
                    servo_trigger.rotate_to_home()             # blocking, short (~settle_time), robot stopped
                    print(">>> SERVO ACTION COMPLETE - resuming line following.")
                    ROBOT_STATE = "FOLLOWING"

            # ================= SHORT STRAIGHT ADVANCE AT THE TARGET =================
            # Same idea as ADVANCING_TO_TURN: drive forward at a fixed speed
            # without looking at the image for PARKING_TIME, then stop - so we end
            # up at the exact center of the marker (not by line following, since
            # the line is usually lost right on top of the marker anyway).
            elif ROBOT_STATE == "PARKING":
                frodo.control.setTrackSpeed(base_speed, base_speed)
                cv2.putText(display_frame, "PARKING...", (60, 150),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 165, 255), 3)
                if time.time() > stop_timer:
                    frodo.control.setTrackSpeed(0.0, 0.0)
                    ROBOT_STATE = "STOPPED"

            # ================= TURNING (closed loop, EKF psi + PI) =================
            elif ROBOT_STATE in ("TURNING_LEFT", "TURNING_RIGHT"):
                if turn_start is None:
                    turn_start = now
                    turn_last_time = now
                    turn_i_acc = 0.0
                    turn_settle_start = None
                    turn_target_psi = HEADING_TO_PSI[TURN_TARGET_HEADING]

                psi_now = pose_est.get()[2]
                e_psi = wrap_pi(turn_target_psi - psi_now)

                dt_turn = max(now - turn_last_time, 1e-3)
                turn_last_time = now

                # Anti-windup: don't accumulate the integral when the output is
                # already saturated AND the error would push it further into
                # saturation. Otherwise (in the first few seconds, omega saturated
                # at +1.0 while the error is still positive) the integral silently
                # winds up to the ceiling, and once the robot overshoots the
                # target (the error flips sign) the P term's correction gets
                # smothered for seconds - that's the "very slow recovery after
                # overshoot" observed in the field.
                w_pretest = TURN_KP * e_psi + turn_i_acc
                is_saturated = abs(w_pretest) >= TURN_OMEGA_MAX
                same_direction = (e_psi * w_pretest) > 0
                if not (is_saturated and same_direction):
                    turn_i_acc = float(np.clip(turn_i_acc + e_psi * dt_turn * TURN_KI,
                                                -TURN_I_LIMIT, TURN_I_LIMIT))
                omega_cmd = float(np.clip(TURN_KP * e_psi + turn_i_acc,
                                           -TURN_OMEGA_MAX, TURN_OMEGA_MAX))

                v_left, v_right = calculate_wheel_speeds(0.0, omega_cmd, track_width)
                frodo.control.setTrackSpeed(v_left, v_right)

                elapsed = now - turn_start
                cv2.putText(display_frame,
                            f"TURNING {elapsed:.1f}s -> {TURN_TARGET_HEADING} "
                            f"err={np.degrees(e_psi):+.0f}deg",
                            (10, 160), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2)

                if (now - last_turn_log) > 0.3:
                    last_turn_log = now
                    print(f"  [TURN {elapsed:.2f}s] target={TURN_TARGET_HEADING} "
                          f"psi={np.degrees(psi_now):+.1f} err={np.degrees(e_psi):+.1f} "
                          f"omega={omega_cmd:+.2f}")

                if abs(e_psi) < TURN_TOLERANCE:
                    if turn_settle_start is None:
                        turn_settle_start = now
                    elif now - turn_settle_start > TURN_SETTLE_TIME:
                        print(f"Heading {TURN_TARGET_HEADING} reached after {elapsed:.2f}s "
                              f"(err={np.degrees(e_psi):+.1f}deg)")
                        frodo.control.setTrackSpeed(0.0, 0.0)
                        ROBOT_STATE = "FOLLOWING"
                        turn_start = None
                        turn_settle_start = None
                else:
                    turn_settle_start = None

                if turn_start is not None and elapsed > TURN_TIMEOUT:
                    print("!!! TURN TIMEOUT - failed to reach the target angle")
                    ROBOT_STATE = "STOPPED"
                    STOP_REASON = "TURN_TIMEOUT"
                    turn_start = None

            with stream_frame_lock:
                frame_out = display_frame

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"\n!!! ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            frodo.control.setTrackSpeed(0.0, 0.0)
            print("Motors stopped.")
        except Exception:
            pass
        try:
            pose_est.stop()
        except Exception:
            pass
        servo_trigger.shutdown()


if __name__ == "__main__":
    main()
