# =====================================================================================
#  FRODO - Line Following + ArUco Grid Navigation
#  Remote-controllable via WiFi commands: goto_grid_node, stop, trigger_servo, get_status
# =====================================================================================
import time
import threading
import cv2
import numpy as np

from core.communication.wifi.data_link import CommandArgument
from robot.frodo import FRODO
from robot.control.frodo_control import FRODO_ControlMode
from robot.utilities.video_streamer.video_streamer import VideoStreamer
from core.utils.network import getInterfaceIP
from hardware.hardware.servo import HardwareServo, NullServo
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

# --- SERVO TRIGGER (on specific ArUco IDs) ---
# First verify the pin/servo with servo_test.py.
SERVO_PIN = 19                 # BCM GPIO19 - verified with the servo_pin_scan.py sweep
SERVO_ANGLE_HOME = 0
SERVO_ANGLE_TRIGGER = 90
SERVO_TRIGGER_IDS = {999, 998, 997, 996, 995}  # seeing one of these IDs triggers the servo action
SERVO_FORWARD_DURATION = 1.0   # seconds - drive straight this long after the servo turns, then rotate_to_home()
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

# In FOLLOWING (a plain pass-through node, not the final target), a hard stop
# the instant the line is lost can permanently strand the robot: an ArUco card
# sitting on/near the line increasingly covers it as the robot gets close,
# which can lose the line just short of ARUCO_MIN_SIZE_PX (observed in the
# field: marker size froze at ~. 145px, just under the 160px accept threshold,
# because the robot fully stopped instead of creeping the last bit forward).
# Creep straight open-loop for a bit first - either the line reappears past
# the marker, or the marker grows enough to be ACCEPTED - before giving up
# and actually stopping.
LINE_LOST_CREEP_TIME = 1.0

# detectMarkers() is slow when scanning the whole frame; that delay makes the
# robot overshoot an intersection and miss the turn. Only scan the bottom region
# (markers are never expected in the top part anyway).
ARUCO_LOG_PERIOD = 0.5     # log a marker at most twice per second

# --- CLOSED-LOOP TURNING (EKF psi feedback) ---
# Instead of a blind timed turn, we turn a relative +-TURN_ANGLE from whatever
# psi actually reads when the turn starts, with a PI controller (see the
# turn-start block below for why this is relative rather than an absolute
# EAST=0/NORTH=90/.. target - psi is odometry-only and drifts over a
# multi-leg run).
# TURN_ANGLE is NOT 90deg on purpose: field-measured actual rotation for a
# commanded 90deg came out ~85deg (RADIUS calibration still undershoots a
# bit), so we command more than a true right angle to compensate. Re-measure
# with a protractor/compass after changing this and adjust again if needed.
TURN_ANGLE = np.radians(105.0)   # commanded relative turn per grid turn
TURN_KP = 1.6               # rad/s per rad of error - bumped up, turn was too gentle and lost the line
TURN_KI = 0.4                # integral gain - overcomes friction/static error
TURN_I_LIMIT = 0.5           # clamp on the integral term's contribution (rad/s)
TURN_OMEGA_MAX = 1.4         # max angular speed allowed while turning (rad/s)
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

# Marker ID -> grid coordinate. PLACEHOLDER: the real ID/coordinate mapping
# will be assigned once the markers are placed in the field.
CITY_MAP = {
    0: (0, 0), 1: (1, 0), 2: (2, 0), 3: (3, 0), 4: (4, 0), 5: (5, 0), 6: (6, 0), 7: (7, 0), 8: (8, 0),
    9: (0, 1), 10: (1, 1), 11: (2, 1), 12: (3, 1), 13: (4, 1), 14: (5, 1), 15: (6, 1), 16: (7, 1), 17: (8, 1),
    18: (0, 2), 19: (1, 2), 20: (2, 2), 21: (3, 2), 22: (4, 2), 23: (5, 2), 24: (6, 2), 25: (7, 2), 26: (8, 2),
    27: (0, 3), 28: (1, 3), 29: (2, 3), 30: (3, 3), 31: (4, 3), 32: (5, 3), 33: (6, 3), 34: (7, 3), 35: (8, 3),
    36: (0, 4), 37: (1, 4), 38: (2, 4), 39: (3, 4), 40: (4, 4), 41: (5, 4), 42: (6, 4), 43: (7, 4), 44: (8, 4),
    45: (0, 5), 46: (1, 5), 47: (2, 5), 48: (3, 5), 49: (4, 5), 50: (5, 5), 51: (6, 5), 52: (7, 5), 53: (8, 5),
}

# Closed-loop turning (via EKF psi) no longer depends on a time estimate;
# this is only a safety net in case the PI never converges at all.
TURN_TIMEOUT = 10.0


# =====================================================================================
class ArtProjectAgent:
    """
    Line-following + ArUco grid-navigation + servo-trigger agent.

    Exposes four WiFi commands so a host PC can remote-control it:
      - goto_grid_node(x, y): drive to a grid node (async - fire and forget,
        completion is reported via the 'art_project_arrived' event)
      - stop(): halt in place and clear any pending target
      - trigger_servo(): manually cycle the metronome servo, independent of position
      - get_status(): synchronous status query (state, target, pose)

    All hardware access (motors, servo, camera) happens exclusively on the run()
    loop thread. The WiFi-invoked methods above only set/read plain attributes
    under self._lock (a mailbox pattern) so there is never concurrent hardware access.
    """

    # === INIT =========================================================================================================
    def __init__(self, frodo: FRODO):
        self.frodo = frodo
        self._lock = threading.Lock()

        # --- shared state (written by run(), read by get_status()) ---
        self.state = "FOLLOWING"
        self.current_node = None          # last grid node confirmed by a marker read

        # --- shared state (written by WiFi commands, read by run()) ---
        # TEMPORARY for field testing without a host/hub connection - remove once
        # goto_grid_node() is actually being called over WiFi, this bypasses that
        # entirely and starts the robot heading here immediately.
        self.target_node = (5, 3)         # None = no goal, just keep following the line
        self.stopped = False              # manual halt-in-place, set by stop()
        self._manual_servo_request = False

        # --- streaming ---
        self._stream_frame_lock = threading.Lock()
        self.frame_out = None
        self.streamer = VideoStreamer(image_fetcher=self._get_stream_frame, port=5001)

        # --- ArUco detector ---
        self.aruco_detector = create_aruco_detector(ARUCO_DICT_TYPE)

        # --- servo trigger (SERVO_TRIGGER_IDS -> rotate 90 degrees -> forward -> rotate back) ---
        # Fall back to a no-op servo if the hardware isn't wired up / provisioned
        # yet (missing rpi_hardware_pwm or the config.txt PWM overlay) - the grid
        # navigation and ArUco logic still run, the servo just doesn't move.
        try:
            self.servo = HardwareServo(pin=SERVO_PIN)
        except (ImportError, ModuleNotFoundError, FileNotFoundError, OSError) as e:
            frodo.logger.warning(f"HardwareServo unavailable ({e}) - using NullServo (servo will not move)")
            self.servo = NullServo()
        self.servo_trigger = ArucoServoTrigger(
            self.servo, frodo.control.setTrackSpeed,
            trigger_ids=SERVO_TRIGGER_IDS,
            angle_home=SERVO_ANGLE_HOME, angle_trigger=SERVO_ANGLE_TRIGGER,
            forward_speed=0.08, forward_duration=SERVO_FORWARD_DURATION,
            approach_distance_m=SERVO_TRIGGER_APPROACH_DISTANCE_M,
            cooldown=SERVO_RETRIGGER_COOLDOWN,
        )

        # --- pose estimation (EKF: prediction + ArUco correction) ---
        # PoseEstimator in pose_estimator.py: predicts at 100 Hz from wheel odometry,
        # applies an EKF correction using measurements from frodo.sensors.aruco_detector
        # (which it converts itself from the camera frame into the robot frame). For
        # now this is ONLY shown on screen - it does NOT drive the FSM/turn decisions,
        # that logic still relies on the pixel-based ArUco detection.
        self.pose_est = PoseEstimator(frodo, verbose=False)

        self._register_wifi_commands()

    # === WIFI COMMANDS (called remotely from the host) ================================================================
    def _register_wifi_commands(self):
        wifi = self.frodo.communication.wifi

        wifi.newCommand(
            identifier='goto_grid_node',
            function=self.goto_grid_node,
            description='Drive to a grid node (x, y). Async - reports completion via the art_project_arrived event.',
            arguments=[
                CommandArgument(name='x', type=int, description='Target grid X coordinate'),
                CommandArgument(name='y', type=int, description='Target grid Y coordinate'),
            ]
        )

        wifi.newCommand(
            identifier='stop',
            function=self.stop,
            description='Halt in place and clear any pending target.',
            arguments=[]
        )

        wifi.newCommand(
            identifier='trigger_servo',
            function=self.trigger_servo,
            description='Manually cycle the metronome servo, independent of position (for testing).',
            arguments=[]
        )

        wifi.newCommand(
            identifier='get_status',
            function=self.get_status,
            description='Return current state, target node, and pose.',
            arguments=[],
            execute_in_thread=False,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def goto_grid_node(self, x: int, y: int):
        if (x, y) not in CITY_MAP.values():
            self.frodo.logger.warning(f"goto_grid_node({x},{y}): not a known CITY_MAP node, proceeding anyway")
        with self._lock:
            self.target_node = (x, y)
            self.stopped = False

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        with self._lock:
            self.stopped = True
            self.target_node = None

    # ------------------------------------------------------------------------------------------------------------------
    def trigger_servo(self):
        with self._lock:
            self._manual_servo_request = True

    # ------------------------------------------------------------------------------------------------------------------
    def get_status(self) -> dict:
        with self._lock:
            state = self.state
            target_node = self.target_node
            current_node = self.current_node
        pose_x, pose_y, pose_psi = self.pose_est.get()
        return {
            "state": state,
            "target_node": list(target_node) if target_node is not None else None,
            "current_node": list(current_node) if current_node is not None else None,
            "pose": {"x": float(pose_x), "y": float(pose_y), "psi": float(pose_psi)},
        }

    # === STREAMING ====================================================================================================
    def _get_stream_frame(self):
        with self._stream_frame_lock:
            if self.frame_out is not None:
                return self.frodo.sensors.camera.getImageBufferBytes(self.frame_out)
            return None

    # === MAIN LOOP ====================================================================================================
    def run(self):
        frodo = self.frodo

        self.streamer.start()
        ip = getInterfaceIP("wlan0")
        print(f"\n---> LIVE: http://{ip}:5001/preview <--- \n")

        # ---------------- PARAMETERS ----------------
        CURRENT_TARGET_COLOR = "pink"
        kp = 0.008
        base_speed = 0.08           # kept low for the straight-drive test
        track_width = 0.150

        # ROBOT_HEADING is NOT guessed/assumed - it's derived from the robot's own
        # first two marker fixes (see HEADING CALIBRATION below), so it's correct
        # regardless of which physical direction the robot happens to be facing
        # when placed on the line (a blind "assume I'm already driving toward the
        # target" guess was tried before and drove the robot the wrong way whenever
        # it was placed facing away from the target).
        ROBOT_HEADING = None
        LAST_SEEN_ID = None
        first_fix_coord = None     # grid coord of the very first marker seen
        heading_known = False      # True once ROBOT_HEADING has been derived from 2 real fixes
        line_lost_since = None     # FOLLOWING only - see LINE_LOST_CREEP_TIME above

        # TURNING pivots the robot roughly in place (no forward speed) - it does NOT
        # drive the robot onto the new-color lane by itself. Since the axis color is
        # fixed by design (X=pink, Y=green) and switches the instant the turn starts
        # (see the color switch at ADVANCING_TO_TURN below), the robot needs a short
        # advance AFTER the turn too - same idea as ADVANCE_TIME before the turn - to
        # physically get onto the new lane before FOLLOWING starts looking for it.
        # This advance is NOT purely blind: the pivot is never perfectly centered on
        # the intersection, so a fixed blind time either ends before the new lane is
        # even in frame (instant LINE LOST the moment FOLLOWING takes over) or drives
        # past it. Instead we check the camera every frame here too and drop into
        # FOLLOWING the moment the new-color line is actually visible; MIN_TIME is
        # just a brief blind floor (avoid reacting to a stray glimpse before the robot
        # has moved off the pivot point at all), MAX_TIME is a ceiling so we don't
        # drive forever if the lane is genuinely not reachable this way.
        TURN_EXIT_ADVANCE_MIN_TIME = 0.2   # seconds
        TURN_EXIT_ADVANCE_MAX_TIME = 1.2   # seconds
        turn_exit_start = None

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
        arriving_node = None         # the grid node we're APPROACHING/PARKING toward

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
        STOP_REASON = None      # "TURN_TIMEOUT" - distinguishes the STOPPED message
        last_turn_log = 0.0     # throttles the diagnostic log while turning

        self.pose_est.start()

        print("Remote-controllable Grid Navigation Started (ArUco Marker Mode).")
        print("Waiting for goto_grid_node(x, y) from the host. Press Ctrl+C to stop.\n")

        shape_printed = False
        last_aruco_log = 0.0

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
                pose_x, pose_y, pose_psi = self.pose_est.get()
                cv2.putText(display_frame,
                            f"EKF x={pose_x:+.2f}m y={pose_y:+.2f}m psi={np.degrees(pose_psi):+.0f}deg",
                            (10, h_img - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)

                # ---------------- MANUAL STOP (from the host) ----------------
                # Aborts whatever it was doing (turn/approach/park included) and holds
                # in place. goto_grid_node() clears the flag and resumes FOLLOWING.
                with self._lock:
                    manual_stopped = self.stopped
                if manual_stopped:
                    frodo.control.setTrackSpeed(0.0, 0.0)
                    self.state = "IDLE"
                    cv2.putText(display_frame, "STOPPED (manual)", (60, 150),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 165, 255), 3)
                    with self._stream_frame_lock:
                        self.frame_out = display_frame
                    time.sleep(0.05)
                    continue
                elif self.state == "IDLE":
                    self.state = "FOLLOWING"

                # ---------------- STOPPED (unrecoverable failure) ----------------
                if self.state == "STOPPED":
                    frodo.control.setTrackSpeed(0.0, 0.0)
                    cv2.putText(display_frame, "FAILED: TURN TIMEOUT", (60, 200),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 4)
                    print(f"\n!!! MISSION FAILED ({STOP_REASON}). Motors locked. !!!")
                    with self._stream_frame_lock:
                        self.frame_out = display_frame
                    break

                # ================= ARUCO DETECTION =================
                # The camera can be configured for a gray output (image_format="gray"
                # in robot/definitions.py) - in that case the frame is already
                # single-channel. Same guard as aruco_detector.py / line_following.py.
                gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                detected_markers, _aruco_scan_y0 = detect_markers(self.aruco_detector, gray, ARUCO_SCAN_Y_MIN)

                now = time.time()
                log_aruco = (now - last_aruco_log) > ARUCO_LOG_PERIOD
                if log_aruco:
                    last_aruco_log = now
                    if not detected_markers:
                        print(f"[{now:.1f}] ArUco: none visible")

                # ---------------- SERVO TRIGGER (SERVO_TRIGGER_IDS, automatic) ----------------
                # Independent of grid navigation: these IDs aren't in CITY_MAP so they
                # never enter the decision loop below, which is why it's checked
                # separately and first. Only triggers while driving straight
                # (FOLLOWING) - so it doesn't clash with the robot's position/speed
                # during a turn/park/approach.
                if self.state == "FOLLOWING":
                    detected_ids_now = [detected_id for detected_id, _ in detected_markers]
                    servo_matched_id = self.servo_trigger.matching_id(detected_ids_now, now)
                    if servo_matched_id is not None:
                        print(f"[{now:.1f}] Trigger ArUco ID seen: {servo_matched_id} - approaching marker")
                        self.servo_trigger.mark_triggered(now)
                        servo_phase_start = now
                        self.state = "SERVO_APPROACHING"

                    # ---------------- MANUAL SERVO TRIGGER (from the host) ----------------
                    with self._lock:
                        manual_request = self._manual_servo_request
                        if manual_request:
                            self._manual_servo_request = False
                    if manual_request and self.state == "FOLLOWING":
                        print(f"[{now:.1f}] Manual trigger_servo() requested - cycling servo in place")
                        frodo.control.setTrackSpeed(0.0, 0.0)
                        self.servo_trigger.rotate_to_trigger()
                        self.servo_trigger.rotate_to_home()
                        self.frodo.communication.send_event('art_project_servo_triggered', {'node': None})
                        print(">>> MANUAL SERVO CYCLE COMPLETE.")

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
                    elif self.state not in ("FOLLOWING", "SERVO_APPROACHING", "SERVO_ADVANCING"):
                        # SERVO_APPROACHING/SERVO_ADVANCING included: don't miss a grid
                        # decision even while driving open-loop for the servo (see the
                        # servo_phase_start note above).
                        status = f"state={self.state}"
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

                    # ---------------- POSITION TRACKING (always active, independent of target) ----------------
                    # Must update even with no target set - otherwise LAST_SEEN_ID never
                    # leaves None, which makes the "probe pink vs green" fallback in LINE
                    # FOLLOWING below (gated on LAST_SEEN_ID is None) re-run every single
                    # frame instead of just once. If both colors are ever visible at the
                    # same time (e.g. near a grid intersection), that flip-flops
                    # CURRENT_TARGET_COLOR frame to frame and the robot never drives
                    # straight (observed in the field: spins in place near markers).
                    current_coord = CITY_MAP[detected_id]
                    if detected_id != LAST_SEEN_ID:
                        LAST_SEEN_ID = detected_id
                        self.current_node = current_coord
                        print(f"\n[{now:.1f}] NODE {detected_id} -> {current_coord}")

                        # ---------------- HEADING CALIBRATION (first two real fixes) ----------------
                        # Do NOT assume "whatever direction I'm currently driving must be
                        # the direction I want" - that depends on which way the robot
                        # happened to be physically facing when placed on the line, which
                        # is not guaranteed to already point toward the goal (observed in
                        # the field: robot placed facing away from the target just kept
                        # "confirming" that wrong direction forever). Instead figure out
                        # the REAL travel direction from two actual marker fixes.
                        if not heading_known:
                            if first_fix_coord is None:
                                first_fix_coord = current_coord
                                print(f"First fix: position={current_coord} - waiting for a second "
                                      f"marker to determine the real heading")
                            else:
                                dxr = current_coord[0] - first_fix_coord[0]
                                dyr = current_coord[1] - first_fix_coord[1]
                                if dxr == 0 and dyr == 0:
                                    print(f"!!! Heading calibration: second fix {current_coord} is the same "
                                          f"as the first - retrying with the next marker")
                                    first_fix_coord = current_coord
                                else:
                                    if abs(dxr) >= abs(dyr):
                                        ROBOT_HEADING = "EAST" if dxr > 0 else "WEST"
                                    else:
                                        ROBOT_HEADING = "NORTH" if dyr > 0 else "SOUTH"
                                    CURRENT_TARGET_COLOR = "pink" if ROBOT_HEADING in ("EAST", "WEST") else "green"
                                    heading_known = True
                                    print(f"Heading calibrated from real movement {first_fix_coord} -> "
                                          f"{current_coord}: {ROBOT_HEADING} (color={CURRENT_TARGET_COLOR})")

                    # ---------------- DECISION MAKING ----------------
                    # Only ACT on a decision while actually FOLLOWING. Position/heading
                    # tracking above still runs during SERVO_APPROACHING/SERVO_ADVANCING
                    # (so we don't miss it), but enacting a decision here would overwrite
                    # self.state (to APPROACHING or ADVANCING_TO_TURN) mid-servo-sequence,
                    # permanently hijacking it away before it ever reaches rotate_to_home()
                    # - observed in the field: servo triggered and stayed open because a
                    # different grid marker was seen while driving the open-loop
                    # SERVO_ADVANCING leg. Defer any real decision until back in FOLLOWING.
                    if self.state != "FOLLOWING":
                        break

                    # No target set yet -> nothing to decide, just keep following the
                    # line (no turns). Waits for the host to call goto_grid_node().
                    with self._lock:
                        target_node = self.target_node
                    if target_node is None:
                        break

                    if current_coord == target_node:
                        print(f"*** TARGET NODE SEEN - approaching marker center before parking ***")
                        pending_action = "TARGET"
                        pending_node_xy = MARKER_WORLD_MAP.get(detected_id)
                        approach_start = now
                        arriving_node = target_node
                        self.state = "APPROACHING"
                        break

                    if not heading_known:
                        # Real heading isn't known yet (only one marker seen so far) -
                        # can't safely decide CONTINUE vs TURN. Wait for the second fix.
                        break

                    dx = target_node[0] - current_coord[0]
                    dy = target_node[1] - current_coord[1]

                    if dx > 0:
                        desired_heading = "EAST"
                    elif dx < 0:
                        desired_heading = "WEST"
                    elif dy > 0:
                        desired_heading = "NORTH"
                    else:
                        desired_heading = "SOUTH"

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

                        if pre_turn_next_state is not None:
                            # NOTE: CURRENT_TARGET_COLOR is NOT changed here - the robot
                            # is still coming from the old position during
                            # ADVANCING_TO_TURN, the color only switches once the turn
                            # actually starts.
                            # Only update ROBOT_HEADING once a turn is actually going to
                            # be executed - in the 180 degree ("not supported") case no
                            # turn happens at all, so the robot keeps physically moving
                            # in the OLD direction. Updating ROBOT_HEADING anyway (as
                            # before) desynced it from the robot's real orientation and
                            # made later decisions silently report CONTINUE/matching
                            # instead of repeatedly flagging the unsupported 180 turn.
                            ROBOT_HEADING = desired_heading
                            pre_turn_start = now
                            self.state = "ADVANCING_TO_TURN"

                    break

                # ================= LINE FOLLOWING =================
                if self.state in ("FOLLOWING", "APPROACHING"):
                    if LAST_SEEN_ID is None and self.state == "FOLLOWING":
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
                        line_lost_since = None
                        forward_speed, angular_speed = proportional_controller(error, kp, base_speed)
                        v_left, v_right = calculate_wheel_speeds(forward_speed, angular_speed, track_width)
                        frodo.control.setTrackSpeed(v_left, v_right)
                    elif self.state == "FOLLOWING" and \
                            (now - (line_lost_since or now)) < LINE_LOST_CREEP_TIME:
                        if line_lost_since is None:
                            line_lost_since = now
                        frodo.control.setTrackSpeed(base_speed, base_speed)
                        cv2.putText(display_frame, "LINE LOST - CREEPING", (10, 120),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2)
                    else:
                        frodo.control.setTrackSpeed(0.0, 0.0)

                    if self.state == "APPROACHING":
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
                            self.state = "PARKING"
                            stop_timer = time.time() + PARKING_TIME
                            pending_action = None
                            pending_node_xy = None
                            approach_line_lost_since = None

                # ================= SHORT STRAIGHT ADVANCE TO INTERSECTION =================
                # We do NOT look at the image at all - just drive forward at a fixed
                # speed (see the ADVANCE_TIME note above). We leave the actual turning
                # ENTIRELY to the psi PI controller.
                elif self.state == "ADVANCING_TO_TURN":
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
                        self.state = pre_turn_next_state
                        turn_start = None
                        pre_turn_next_state = None

                # ================= SHORT STRAIGHT ADVANCE OUT OF A TURN =================
                # The turn (above) only pivots the robot - it doesn't drive it forward
                # onto the new lane. Advance straight OPEN-LOOP (without looking at the
                # image, same as ADVANCING_TO_TURN) for a moment so the robot is
                # physically on top of the new-color line before FOLLOWING starts
                # looking for it - otherwise a pivot that isn't perfectly centered on
                # the intersection leaves the new lane just out of frame and FOLLOWING
                # reports LINE LOST even though the color/logic are both correct.
                elif self.state == "ADVANCING_FROM_TURN":
                    exit_elapsed = now - turn_exit_start
                    frodo.control.setTrackSpeed(base_speed, base_speed)
                    cv2.putText(display_frame, f"EXITING TURN {exit_elapsed:.1f}s",
                                (10, 190), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)

                    exit_line_seen = False
                    if exit_elapsed >= TURN_EXIT_ADVANCE_MIN_TIME:
                        exit_mask = get_color_mask(frame, CURRENT_TARGET_COLOR)
                        _, exit_line_seen, _ = calculate_deviation(exit_mask, display_frame)

                    if exit_line_seen or exit_elapsed >= TURN_EXIT_ADVANCE_MAX_TIME:
                        self.state = "FOLLOWING"
                        turn_exit_start = None

                # ================= SERVO: APPROACHING THE MARKER (automatic) =================
                # Same open-loop idea as ADVANCING_TO_TURN (driving WITHOUT looking at
                # the image, just a fixed forward speed) - the difference: ArUco
                # scanning/grid decisions KEEP RUNNING during this too (see the widened
                # status check above), the servo itself hasn't moved yet.
                elif self.state == "SERVO_APPROACHING":
                    servo_elapsed = now - servo_phase_start
                    frodo.control.setTrackSpeed(self.servo_trigger.forward_speed, self.servo_trigger.forward_speed)
                    cv2.putText(display_frame, f"SERVO APPROACH {servo_elapsed:.1f}s",
                                (10, 190), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)

                    if servo_elapsed >= self.servo_trigger.approach_time:
                        print(f"Reached the metronome ({servo_elapsed:.2f}s) -> triggering servo")
                        frodo.control.setTrackSpeed(0.0, 0.0)
                        time.sleep(self.servo_trigger.pre_stop_delay)   # robot is STOPPED - covers no distance
                        self.servo_trigger.rotate_to_trigger()          # blocking, short (~settle_time), robot stopped
                        servo_phase_start = now
                        self.state = "SERVO_ADVANCING"

                # ================= SERVO: SHORT FORWARD AFTER TRIGGERING (automatic) =================
                elif self.state == "SERVO_ADVANCING":
                    servo_elapsed = now - servo_phase_start
                    frodo.control.setTrackSpeed(self.servo_trigger.forward_speed, self.servo_trigger.forward_speed)
                    cv2.putText(display_frame, f"SERVO FORWARD {servo_elapsed:.1f}s",
                                (10, 190), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)

                    if servo_elapsed >= self.servo_trigger.forward_duration:
                        frodo.control.setTrackSpeed(0.0, 0.0)
                        self.servo_trigger.rotate_to_home()             # blocking, short (~settle_time), robot stopped
                        print(">>> SERVO ACTION COMPLETE - resuming line following.")
                        self.frodo.communication.send_event('art_project_servo_triggered', {'node': self.current_node})
                        self.state = "FOLLOWING"

                # ================= SHORT STRAIGHT ADVANCE AT THE TARGET =================
                # Same idea as ADVANCING_TO_TURN: drive forward at a fixed speed
                # without looking at the image for PARKING_TIME, then stop - so we end
                # up at the exact center of the marker (not by line following, since
                # the line is usually lost right on top of the marker anyway).
                elif self.state == "PARKING":
                    frodo.control.setTrackSpeed(base_speed, base_speed)
                    cv2.putText(display_frame, "PARKING...", (60, 150),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 165, 255), 3)
                    if time.time() > stop_timer:
                        frodo.control.setTrackSpeed(0.0, 0.0)
                        print("\n*** ARRIVED. Resuming line following, waiting for next goto_grid_node(). ***")
                        arrived_node = arriving_node
                        arriving_node = None
                        with self._lock:
                            # Only clear the target if the host hasn't already set a new one.
                            if self.target_node == arrived_node:
                                self.target_node = None
                        self.state = "FOLLOWING"
                        self.frodo.communication.send_event(
                            'art_project_arrived',
                            {'node': list(arrived_node) if arrived_node is not None else None}
                        )

                # ================= TURNING (closed loop, EKF psi + PI) =================
                elif self.state in ("TURNING_LEFT", "TURNING_RIGHT"):
                    if turn_start is None:
                        turn_start = now
                        turn_last_time = now
                        turn_i_acc = 0.0
                        turn_settle_start = None
                        # Target is a RELATIVE +-90deg from wherever psi actually is
                        # right now - NOT the absolute HEADING_TO_PSI value. psi is
                        # odometry-only (the EKF correction only touches x,y - see
                        # pose_estimator.py) and drifts over a multi-leg run, so by
                        # the time we reach an intersection psi can be well off the
                        # "EAST=0/NORTH=90/.." values HEADING_TO_PSI assumes. Using
                        # those absolute values as the target made a correctly-
                        # decided LEFT turn spin the wrong way (drift put the target
                        # >90deg away, so the shortest path was actually CW), and
                        # forcing the sign without fixing the target just turned that
                        # into an almost-360deg turn the "right" way instead. Turning
                        # a relative 90deg from the CURRENT psi is correct regardless
                        # of how much psi has drifted since the last turn.
                        psi_at_turn_start = self.pose_est.get()[2]
                        turn_target_psi = wrap_pi(
                            psi_at_turn_start + (TURN_ANGLE if self.state == "TURNING_LEFT" else -TURN_ANGLE)
                        )

                    psi_now = self.pose_est.get()[2]
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
                            self.state = "ADVANCING_FROM_TURN"
                            turn_exit_start = now
                            turn_start = None
                            turn_settle_start = None
                    else:
                        turn_settle_start = None

                    if turn_start is not None and elapsed > TURN_TIMEOUT:
                        print("!!! TURN TIMEOUT - failed to reach the target angle")
                        STOP_REASON = "TURN_TIMEOUT"
                        self.frodo.communication.send_event('art_project_error', {'reason': STOP_REASON})
                        self.state = "STOPPED"
                        turn_start = None

                with self._stream_frame_lock:
                    self.frame_out = display_frame

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
                self.pose_est.stop()
            except Exception:
                pass
            self.servo_trigger.shutdown()


# =====================================================================================
def main():
    frodo = FRODO()
    frodo.init()
    frodo.start()
    frodo.control.setMode(FRODO_ControlMode.EXTERNAL)

    agent = ArtProjectAgent(frodo)
    agent.run()


if __name__ == "__main__":
    main()
