# =====================================================================================
#  Robot-independent helper: triggers a servo move when certain ArUco IDs are seen
#  (e.g. opening a lid, waving a flag, dropping a brush).
#
#  Only needs a Servo/HardwareServo object (with a setAngle(angle, settle_time)
#  method) and a "drive(v_left, v_right)" callback - nothing FRODO-specific here,
#  so this works unchanged on other robots too (with a different servo pin / drive
#  function).
#
#  TWO WAYS TO USE THIS:
#   1) check_and_run() - simple, ONE call does everything (approach -> servo ->
#      forward -> servo) while blocking. Fine for short/simple robots.
#   2) matching_id() + mark_triggered() + rotate_to_trigger()/rotate_to_home() -
#      fine-grained API. The caller runs the approach/forward steps in its OWN
#      per-frame loop (still scanning for ArUco every frame) - so an important
#      marker (e.g. a grid navigation node) is never MISSED during that drive.
#      FRODO's grid navigation uses this second approach (see
#      art_project_frodo.py's SERVO_APPROACHING/SERVO_ADVANCING states) - in
#      the field, check_and_run()'s ~4s "blind" block caused the robot to miss
#      the next grid marker (its acceptance window is narrow in size/position)
#      and navigate to the wrong spot.
# =====================================================================================
import time


class ArucoServoTrigger:
    """When a trigger ArUco ID is seen: stop the robot -> rotate the servo to the
    trigger angle -> drive straight for a short time -> rotate the servo back home.

    servo: object with a setAngle(angle: float, settle_time: float) method
           (hardware.hardware.servo.Servo / HardwareServo).
    drive: callable(v_left: float, v_right: float) -> None (e.g. frodo.control.setTrackSpeed).
    """

    def __init__(self, servo, drive, *, trigger_ids,
                 angle_home=0, angle_trigger=90,
                 forward_speed=0.08, forward_duration=1.0,
                 approach_distance_m=0.0,
                 cooldown=5.0, pre_stop_delay=0.2, settle_time=0.5,
                 init_home=True):
        self.servo = servo
        self.drive = drive
        self.trigger_ids = set(trigger_ids)
        self.angle_home = angle_home
        self.angle_trigger = angle_trigger
        self.forward_speed = forward_speed
        self.forward_duration = forward_duration
        # When a marker is first seen, the robot is not yet lined up with it
        # (the camera sees it before we're there) - close this distance open-loop
        # (without looking at the image) before triggering the servo.
        self.approach_time = (approach_distance_m / forward_speed) if approach_distance_m > 0 else 0.0
        self.cooldown = cooldown
        self.pre_stop_delay = pre_stop_delay
        self.settle_time = settle_time
        self._last_trigger_time = -1e9

        if init_home:
            self.servo.setAngle(self.angle_home, settle_time=self.settle_time)

    # ---------------- fine-grained API (does not interrupt frame-by-frame ArUco scanning) ----------------
    def matching_id(self, detected_ids, now):
        """Returns the trigger ID if one is in detected_ids AND the cooldown has
        elapsed, otherwise returns None. ONLY checks - starts no movement."""
        if (now - self._last_trigger_time) <= self.cooldown:
            return None
        hit = self.trigger_ids.intersection(detected_ids)
        return next(iter(hit)) if hit else None

    def mark_triggered(self, now):
        """Starts the cooldown timer - call this as soon as you enter the action
        sequence, so the same ID doesn't retrigger while the robot is still in
        front of the marker."""
        self._last_trigger_time = now

    def rotate_to_trigger(self):
        """Blocks for settle_time - the robot should be STOPPED while this runs
        (no distance is covered, so there's no risk of missing another marker's
        window)."""
        self.servo.setAngle(self.angle_trigger, settle_time=self.settle_time)

    def rotate_to_home(self):
        self.servo.setAngle(self.angle_home, settle_time=self.settle_time)

    # ---------------- simple/blocking API ----------------
    def check_and_run(self, detected_ids, now):
        """One call does: (approach ->) stop -> servo to trigger angle -> forward
        -> servo back home, all blocking. WARNING: no ArUco scanning happens
        during this - the robot can miss another important marker even if it's
        right there. If scanning must not be interrupted while driving (e.g. grid
        navigation), use matching_id/mark_triggered/rotate_to_trigger/rotate_to_home
        instead."""
        matched = self.matching_id(detected_ids, now)
        if matched is None:
            return None
        print(f"[{now:.1f}] Trigger ArUco ID seen: {matched}")
        self.mark_triggered(now)

        print(">>> SERVO TRIGGERED")
        if self.approach_time > 0:
            print(f"    approaching marker ({self.approach_time:.2f}s)")
            self.drive(self.forward_speed, self.forward_speed)
            time.sleep(self.approach_time)

        print("    stop -> trigger angle -> forward -> back home")
        self.drive(0.0, 0.0)
        time.sleep(self.pre_stop_delay)

        self.rotate_to_trigger()

        self.drive(self.forward_speed, self.forward_speed)
        time.sleep(self.forward_duration)
        self.drive(0.0, 0.0)

        self.rotate_to_home()
        print(">>> SERVO ACTION COMPLETE.")
        return matched

    def shutdown(self):
        """Returns the servo home and releases it on exit (call this in your
        outer try/finally)."""
        try:
            self.servo.setAngle(self.angle_home, settle_time=self.settle_time)
        except Exception:
            pass
        try:
            self.servo.release()
        except Exception:
            pass
        try:
            self.servo.stop()
        except Exception:
            pass
