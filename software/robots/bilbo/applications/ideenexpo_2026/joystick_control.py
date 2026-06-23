"""Joystick control for the IdeenExpo 2026 application.

This extends the standard :class:`BILBO_JoystickControl` (which already provides
the general *user joystick* behaviour — assign/unassign/auto-assign of one
joystick per robot) with the concept of a privileged **master joystick**.

The master joystick is identified by its GUID (from the settings YAML) and is
*excluded* from normal user auto-assignment. On top of the inherited user-
joystick behaviour it can:

  * designate a *target* robot and take over (override) it,
  * force an override via a joystick button or a GUI/app button,
  * switch all robots on/off.

Most of the master logic below is deliberately kept as clearly-marked
*groundwork*: the structure, state, callbacks/events and extension points are in
place, but the precise arbitration/override behaviour is left to be refined once
the interaction design is settled. Master features are gated behind
``MasterJoystickSettings.enabled`` and default to off, so with the default
settings this class behaves exactly like the standard user-joystick control.
"""
from __future__ import annotations

import threading

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger
from extensions.hardware.joystick.joystick_manager import Joystick
from extensions.tools.cli.cli import Command, CommandArgument
from robots.bilbo.manager.bilbo_joystick_control import (
    BILBO_JoystickControl,
    BILBO_JoystickManager_CommandSet,
)
from robots.bilbo.manager.bilbo_manager import BILBO_Manager
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode

from robots.bilbo.applications.ideenexpo_2026.settings import MasterJoystickSettings

logger = Logger('master joystick')

# Distance [m] for the master "nudge" (free the selected robot from a wall).
MASTER_NUDGE_DISTANCE_M = 0.05  # 5 cm


# ======================================================================================================================
class MasterOverrideMode:
    """Override modes for the master joystick against its current target robot.

    The master always either assists or fully overrides its selected target; it is
    disengaged by clearing the target (Target → None), not by a mode. These string
    values are the states of the "Override Mode" MultiStateButton.
    """
    ASSIST = 'Assist'    # master input is mixed into the user's input (a "nudge"; see settings.assist_gain)
    FULL = 'Full'        # master takes over the target completely (a.k.a. "Override")

    ALL = (ASSIST, FULL)
    SELECTABLE = ALL     # alias: user-selectable override modes


# ======================================================================================================================
@callback_definition
class MasterJoystickCallbacks:
    master_connected: CallbackContainer
    master_disconnected: CallbackContainer
    master_target_changed: CallbackContainer
    master_mode_changed: CallbackContainer
    master_override: CallbackContainer
    master_released: CallbackContainer
    all_robots_toggled: CallbackContainer


@event_definition
class MasterJoystickEvents:
    master_connected: Event
    master_disconnected: Event
    master_target_changed: Event
    master_mode_changed: Event
    master_override: Event
    master_released: Event
    all_robots_toggled: Event


# ======================================================================================================================
class IdeenExpo2026_JoystickControl(BILBO_JoystickControl):
    """User-joystick control plus a privileged master joystick."""

    master_settings: MasterJoystickSettings
    master_joystick: Joystick | None
    master_target: BILBO | None
    master_mode: str
    master_active: bool

    master_callbacks: MasterJoystickCallbacks
    master_events: MasterJoystickEvents

    # ==================================================================================================================
    def __init__(self,
                 bilbo_manager: BILBO_Manager,
                 master_settings: MasterJoystickSettings | None = None,
                 auto_assign: bool = False):

        # Master state — set *before* super().__init__ so the (overridden) joystick
        # callbacks registered there can safely reference it.
        self.master_settings = master_settings if master_settings is not None else MasterJoystickSettings()
        self.master_joystick = None
        self.master_target = None
        self.master_mode = MasterOverrideMode.ASSIST
        self.master_active = False
        # Instance id (joystick.id) of a master elected at runtime via SELECT long-press.
        # Used when the configured GUID/name cannot single out a master (e.g. several
        # controllers share the same GUID). None = no gesture-elected master.
        self._elected_master_id: str | None = None
        self._master_previous_joystick: Joystick | None = None
        # Robot the master is *fully* overriding (FULL mode). Tracked separately from
        # master_target so the user joystick is always handed back to the robot that was
        # actually taken over — even if the target was cleared or cycled in the meantime.
        self._master_override_robot: BILBO | None = None
        # Track what the master is currently applied to, so it can be cleanly torn down
        # when the target or mode changes (or the robot/master disconnects).
        self._master_applied_robot: BILBO | None = None
        self._master_applied_mode: str | None = None  # None = nothing currently applied
        self._all_robots_on = False
        # Serialises master target/mode transitions. These can be driven concurrently
        # from the joystick-callback thread (R1) and the GUI/app thread (mode/target
        # buttons); without this the assignment bookkeeping can be corrupted mid-handback,
        # leaving the user unable to drive. Re-entrant: the transition methods call each
        # other (setMasterMode → _apply_master → releaseMaster, etc.).
        self._master_lock = threading.RLock()

        self.master_callbacks = MasterJoystickCallbacks()
        self.master_events = MasterJoystickEvents()

        super().__init__(bilbo_manager, auto_assign=auto_assign)

        # Replace the base CLI command set with the expo one (adds master commands).
        self.cli_command_set = IdeenExpo2026_JoystickControl_CommandSet(self)

    # === LIFECYCLE ====================================================================================================
    def close(self):
        with self._master_lock:
            self._clear_master_application()
        super().close()

    # === MASTER: IDENTIFICATION =======================================================================================
    def _is_master(self, joystick: Joystick) -> bool:
        """True if this joystick is the configured master joystick."""
        if not self.master_settings.enabled:
            return False
        if self.master_settings.guid and joystick.guid == self.master_settings.guid:
            return True
        if self.master_settings.name and joystick.name == self.master_settings.name:
            return True
        # Runtime gesture election (SELECT long-press) — used when the GUID/name is
        # ambiguous (identical controllers). Matched on the unique pygame instance id.
        if self._elected_master_id is not None and joystick.id == self._elected_master_id:
            return True
        return False

    def _guid_master_connected(self) -> bool:
        """True if a joystick matching the configured master GUID/name is connected.

        When such a controller is present it is the rightful master, so the SELECT
        long-press gesture election is disabled (GUID wins). With no GUID/name
        configured — or none currently connected — gesture election is allowed.
        """
        if not self.master_settings.enabled:
            return False
        guid = self.master_settings.guid
        name = self.master_settings.name
        if not guid and not name:
            return False
        for js in self.joystick_manager.joysticks.values():
            if guid and js.guid == guid:
                return True
            if name and js.name == name:
                return True
        return False

    def hasMaster(self) -> bool:
        return self.master_joystick is not None

    # === MASTER: TARGETING & OVERRIDE =================================================================================
    def setMasterTarget(self, robot: BILBO | str | None):
        """Designate which robot the master controls and (re)apply the current mode.

        Wired to the app/GUI "Target" MultiStateButton. Changing the target tears
        down whatever the master was applied to and applies the current override
        mode to the new target.
        """
        if isinstance(robot, str):
            robot = self.bilbo_manager.getRobotById(robot)

        with self._master_lock:
            self.master_target = robot
            logger.info(f"Master target set to {robot.id if robot is not None else None}")

            self._apply_master()

        for callback in self.master_callbacks.master_target_changed:
            callback(robot)
        # Events carry the robot *id* (not the BILBO object): the event system
        # snapshots payloads for history, and a BILBO holds an un-picklable thread
        # lock. Callbacks above get the live object; event subscribers resolve via id.
        self.master_events.master_target_changed.set(robot.id if robot is not None else None)

    def setMasterMode(self, mode: str):
        """Set the override mode (None / Assist / Full) and apply it to the target.

        Wired to the app/GUI "Override Mode" MultiStateButton.
        """
        if mode not in MasterOverrideMode.ALL:
            logger.warning(f"Unknown master override mode: {mode}")
            return

        with self._master_lock:
            self.master_mode = mode
            logger.info(f"Master override mode set to {mode}")

            self._apply_master()

        for callback in self.master_callbacks.master_mode_changed:
            callback(mode)
        self.master_events.master_mode_changed.set(mode)

    def _apply_master(self):
        """Apply (target, mode) to the robots: tear down the previous application first."""
        self._clear_master_application()

        if self.master_joystick is None:
            return

        robot = self.master_target
        mode = self.master_mode

        if robot is not None and mode == MasterOverrideMode.ASSIST:
            try:
                robot.interfaces.set_assist_joystick(
                    self.master_joystick,
                    self.master_settings.assist_gain,
                    self.master_settings.assist_mix_mode,
                )
            except Exception as e:
                logger.error(f"Could not enable assist on {robot.id}: {e}")
            else:
                self._master_applied_robot = robot
                self._master_applied_mode = mode
                logger.info(f"Master assisting {robot.id} (gain={self.master_settings.assist_gain})")
        elif robot is not None and mode == MasterOverrideMode.FULL:
            self.assignMasterToRobot(robot)
            self._master_applied_robot = robot
            self._master_applied_mode = mode
        # No target → nothing to apply (already cleared)

        # Enable the R2 forward boost whenever the master is applied (Assist or Full).
        if self._master_applied_robot is not None:
            try:
                self._master_applied_robot.interfaces.set_boost(
                    self.master_joystick,
                    self.master_settings.boost_scale_balancing,
                    self.master_settings.boost_scale_velocity,
                    self.master_settings.boost_scale_turn_balancing,
                    self.master_settings.boost_scale_turn_velocity,
                )
            except Exception as e:
                logger.error(f"Could not enable boost on {self._master_applied_robot.id}: {e}")

        # (Re)wire the master's physical buttons to mirror the selected target robot.
        self._wire_master_buttons()

    def _clear_master_application(self):
        """Undo whatever the master was applied to (assist or full override)."""
        robot = self._master_applied_robot
        mode = self._master_applied_mode
        if robot is not None:
            try:
                if mode == MasterOverrideMode.ASSIST:
                    robot.interfaces.clear_assist_joystick()
                elif mode == MasterOverrideMode.FULL and self.master_active:
                    self.releaseMaster()
                robot.interfaces.clear_boost()
            except Exception as e:
                logger.error(f"Error clearing master application on {robot.id}: {e}")
        self._master_applied_robot = None
        self._master_applied_mode = None

        # Clear the master's button bindings so the next apply starts from a clean slate.
        if self.master_joystick is not None:
            self.master_joystick.clearAllButtonCallbacks()

    def overrideTarget(self, *args, **kwargs):
        """Take over the current target completely (Full mode).

        Convenience wrapper routed through the mode system so external callers
        (e.g. the GUI 'Override' button) stay consistent with the app's mode button.
        """
        self.setMasterMode(MasterOverrideMode.FULL)

    def toggleMasterTakeover(self, *args, **kwargs):
        """Master R1: toggle the selected target between Full takeover and Assist.

        First press takes over the robot completely (Full); pressing again hands
        it back to "help" (Assist). No-op when no target is selected.
        """
        with self._master_lock:
            if self.master_target is None:
                logger.info("R1 takeover toggle ignored: no master target selected")
                return
            if self.master_mode == MasterOverrideMode.FULL:
                self.setMasterMode(MasterOverrideMode.ASSIST)
            else:
                self.setMasterMode(MasterOverrideMode.FULL)

    def assignMasterToRobot(self, robot: BILBO | str):
        """Hand full control of ``robot`` to the master joystick (Full mode).

        The master is assigned like a normal joystick (driving + the robot's button
        mappings). Remembers the user joystick currently controlling the robot so it
        can be restored on :meth:`releaseMaster`.
        """
        if self.master_joystick is None:
            return
        if isinstance(robot, str):
            robot = self.bilbo_manager.getRobotById(robot)
        if robot is None:
            return

        with self._master_lock:
            # Remember which robot we take over and the user joystick currently driving
            # it, so releaseMaster can hand it back to exactly that joystick/robot pair.
            previous_user = self.robotIsAssigned(robot)
            self._master_previous_joystick = previous_user
            self._master_override_robot = robot
            self.master_target = robot
            self.master_active = True

            # Cleanly release the user joystick first, so it isn't left as a stale
            # assignment (the GUI would otherwise still show it "controlling" a robot it
            # no longer drives, and the entry would shadow a later restore).
            if previous_user is not None and previous_user is not self.master_joystick:
                self.unassignJoystick(previous_user)

            logger.info(f"Master joystick overriding robot {robot.id}")
            self.assignJoystick(self.master_joystick, robot)
            # A Full override always drives at full range, regardless of the robot's
            # "speed" setting (that throttles the visitor joystick, not the operator).
            try:
                robot.interfaces.set_input_scale_bypass(True)
            except Exception as e:
                logger.error(f"Could not bypass input speed on {robot.id}: {e}")
            self.master_joystick.rumble(strength=0.8, duration=200)

        for callback in self.master_callbacks.master_override:
            callback(robot)
        self.master_events.master_override.set(robot.id if robot is not None else None)

    def releaseMaster(self, *args, **kwargs):
        """Release the master from the robot it is overriding and hand it back."""
        with self._master_lock:
            if not self.master_active or self.master_joystick is None:
                return

            # Hand back to the robot we actually took over — NOT the current target,
            # which may have been cleared (Target → None) or cycled to another robot
            # before this release runs.
            robot = self._master_override_robot
            previous_user = self._master_previous_joystick

            self.unassignJoystick(self.master_joystick)
            self.master_active = False
            self._master_override_robot = None
            self._master_previous_joystick = None
            logger.info(f"Master joystick released from {robot.id if robot is not None else None}")

            # Re-enable this robot's normal input "speed" now the master no longer fully
            # overrides it (the restored user joystick is throttled again).
            if robot is not None:
                try:
                    robot.interfaces.set_input_scale_bypass(False)
                except Exception as e:
                    logger.error(f"Could not restore input speed on {robot.id}: {e}")

            # Restore the user joystick that drove the robot before takeover, but only
            # if it is still connected; otherwise leave the robot without input rather
            # than re-binding a stale/disconnected joystick.
            # joystick_manager.joysticks is keyed by the int instance_id, NOT the
            # string Joystick.id — use instance_id or the membership test is always False.
            if (self.master_settings.restore_user_on_release
                    and previous_user is not None
                    and robot is not None
                    and previous_user.instance_id in self.joystick_manager.joysticks):
                self.assignJoystick(previous_user, robot)

        for callback in self.master_callbacks.master_released:
            callback()
        self.master_events.master_released.set()

    # === MASTER: NUDGE ================================================================================================
    def nudgeMasterTarget(self, *args, **kwargs):
        """Master Y long-press: nudge the current target robot a small distance.

        ``control.nudge()`` does a blocking request/response (timeout ~2 s); run it
        off the joystick callback thread so input stays responsive. Firmware accepts
        it only in OFF mode with the robot lying over, and auto-picks the direction.
        """
        robot = self.master_target
        if robot is None:
            logger.info("Nudge ignored: no master target selected")
            return
        logger.info(f"Master nudging {robot.id} ({int(MASTER_NUDGE_DISTANCE_M * 100)} cm)")
        threading.Thread(
            target=robot.control.nudge,
            kwargs={'distance': MASTER_NUDGE_DISTANCE_M},
            daemon=True,
        ).start()

    # === MASTER: ALL-ROBOTS ON/OFF ====================================================================================
    def allRobotsOff(self, *args, **kwargs):
        """Switch *all* robots off (panic). Wired to a master button / GUI button."""
        logger.warning("Master: switching ALL robots OFF")
        self.bilbo_manager.emergencyStop()
        self._all_robots_on = False
        for callback in self.master_callbacks.all_robots_toggled:
            callback(False)
        self.master_events.all_robots_toggled.set(False)

    def allRobotsOn(self, *args, **kwargs):
        """Switch *all* robots on (groundwork: bring them into BALANCING mode)."""
        logger.info("Master: switching ALL robots ON")
        for robot in self.bilbo_manager.robots.values():
            try:
                robot.control.setControlMode(BILBO_Control_Mode.BALANCING)
            except Exception as e:
                logger.error(f"Could not switch on {robot.id}: {e}")
        self._all_robots_on = True
        for callback in self.master_callbacks.all_robots_toggled:
            callback(True)
        self.master_events.all_robots_toggled.set(True)

    def toggleAllRobots(self, *args, **kwargs):
        if self._all_robots_on:
            self.allRobotsOff()
        else:
            self.allRobotsOn()

    # === OVERRIDDEN BASE HOOKS ========================================================================================
    def _newJoystick_callback(self, joystick, *args, **kwargs):
        # The master is handled specially and must never be auto-assigned as a user controller.
        if self._is_master(joystick):
            self._registerMaster(joystick)
            # Still notify listeners (e.g. GUI joystick lists) that it connected.
            for callback in self.callbacks.new_joystick:
                callback(joystick)
            return
        super()._newJoystick_callback(joystick, *args, **kwargs)
        # Arm the SELECT long-press elect gesture on this user joystick.
        self._bind_elect_gesture(joystick)

    def _joystickDisconnected_callback(self, joystick, *args, **kwargs):
        if joystick is self.master_joystick:
            self._unregisterMaster()
            for callback in self.callbacks.joystick_disconnected:
                callback(joystick)
            return
        super()._joystickDisconnected_callback(joystick, *args, **kwargs)

    def _getFirstFreeJoystick(self):
        # Never offer the master joystick as a free user controller.
        for joystick in self.joystick_manager.joysticks.values():
            if self._is_master(joystick):
                continue
            if joystick.id not in self.assignments:
                return joystick
        return None

    def _robotDisconnected_callback(self, robot, *args, **kwargs):
        with self._master_lock:
            # If the master was overriding this robot, drop the hand-back target so we
            # don't try to restore a user joystick onto a robot that is going away.
            if robot is self._master_override_robot:
                self._master_override_robot = None
                self._master_previous_joystick = None
            # If the disconnecting robot is the one the master is applied to / targeting, clean up.
            if robot is self._master_applied_robot:
                self._clear_master_application()
            if robot is self.master_target:
                self.master_target = None
                # Keep the selected override mode (Assist/Full); clearing the target alone
                # disengages the master, and the mode re-applies when a new target is picked.
        super()._robotDisconnected_callback(robot, *args, **kwargs)

    # === MASTER: REGISTRATION =========================================================================================
    def _registerMaster(self, joystick: Joystick):
        with self._master_lock:
            self.master_joystick = joystick
            logger.info(f"Master joystick connected: id={joystick.id} guid={joystick.guid} name={joystick.name}")
            joystick.rumble(strength=0.6, duration=400)

            # Wire the master's buttons for the current (target, mode) — at minimum the panic shortcut.
            self._apply_master()

        for callback in self.master_callbacks.master_connected:
            callback(joystick)
        self.master_events.master_connected.set(joystick.id if joystick is not None else None)

    def _unregisterMaster(self):
        with self._master_lock:
            self._clear_master_application()
            if self.master_active:
                self.releaseMaster()

            joystick = self.master_joystick
            self.master_joystick = None
            self.master_active = False
            # Drop any gesture election: the elected instance id is no longer valid
            # (a reconnecting controller gets a fresh instance id).
            self._elected_master_id = None
            logger.info("Master joystick disconnected")

        for callback in self.master_callbacks.master_disconnected:
            callback(joystick)
        self.master_events.master_disconnected.set(joystick.id if joystick is not None else None)

    def _wire_master_buttons(self):
        """(Re)bind the master joystick's buttons.

        When a target robot is selected, the master's A/B/X/Y/L1/DPAD-up/down/hat
        mirror that robot's buttons (via ``interfaces.bind_buttons``), so the master
        can actuate the robot's modes (A→BALANCING, B→OFF, X→beep, Y→POSITION, ...).
        In FULL mode the target is already bound to the master by
        ``assignMasterToRobot`` (addJoystick), so it is not rebound here.

        Reserved master-only buttons (overriding the robot mapping):
          D-pad / hat LEFT/RIGHT → switch the selected target robot
          R1                     → toggle target between Full takeover and Assist
          B long-press           → all robots off (panic)
          Y long-press           → nudge the selected target (free it from a wall)

        Assumes the master's buttons were just cleared by ``_clear_master_application``.
        """
        js = self.master_joystick
        if js is None:
            return

        if self.master_target is not None and self.master_mode != MasterOverrideMode.FULL:
            try:
                self.master_target.interfaces.bind_buttons(js)
            except Exception as e:
                logger.error(f"Could not bind master buttons to {self.master_target.id}: {e}")

        # D-pad / hat LEFT/RIGHT → cycle the assist target (overrides the robot's
        # resume/revert mapping on those keys). Done in all modes.
        self._wire_master_target_switch(js)

        # R1: toggle the target between Full takeover and Assist ("help").
        if 'R1' in js.buttons:
            js.buttons['R1'].callbacks.pressed.register(self.toggleMasterTakeover)

        # Panic: B long-press → all robots off.
        if 'B' in js.buttons:
            js.buttons['B'].callbacks.long_pressed.register(self.allRobotsOff)

        # Y long-press → nudge the current target (free it from a wall).
        if 'Y' in js.buttons:
            js.buttons['Y'].callbacks.long_pressed.register(self.nudgeMasterTarget)

    def _wire_master_target_switch(self, js: Joystick):
        """Bind the master's left/right D-pad and hat keys to cycle the target robot.

        These keys are first cleared (the robot mapping / addJoystick binds them to
        resume/revert) and then rebound, so on the master they switch robots instead.
        Both the D-pad buttons (macOS) and the hat keys (Linux) are wired for
        cross-platform coverage.
        """
        # D-pad buttons (present on macOS).
        for name, direction in (('DPAD_LEFT', -1), ('DPAD_RIGHT', +1)):
            if name in js.buttons:
                js.buttons[name].clear_callbacks_and_events()
                js.buttons[name].callbacks.pressed.register(self.cycleMasterTarget, direction=direction)

        # Hat keys (used on Linux; harmless no-op on macOS).
        for hat_key, direction in (('left', -1), ('right', +1)):
            key = js.hat[hat_key]
            key.clear_callbacks_and_events()
            key.callbacks.pressed.register(self.cycleMasterTarget, direction=direction)

    def cycleMasterTarget(self, direction: int = 1, *args, **kwargs):
        """Switch the master's target to the next (+1) / previous (-1) connected robot.

        Keeps the current override mode (it is re-applied to the new target). No-op
        when no robots are connected.
        """
        with self._master_lock:
            robots = list(self.bilbo_manager.robots.values())
            if not robots:
                logger.info("Cannot cycle master target: no robots connected")
                return

            if self.master_target in robots:
                idx = robots.index(self.master_target)
                new_target = robots[(idx + direction) % len(robots)]
            else:
                new_target = robots[0] if direction > 0 else robots[-1]

            logger.info(f"Master cycling target → {new_target.id}")
            self.setMasterTarget(new_target)

    # === MASTER: GESTURE ELECTION =====================================================================================
    def electAsMaster(self, joystick: Joystick, *args, **kwargs):
        """Promote ``joystick`` to master via the SELECT long-press gesture.

        This is the fallback for when the configured GUID/name cannot single out a
        master (e.g. all controllers share one GUID): the operator long-presses SELECT
        on the controller they want as master. A controller matching the configured
        GUID/name takes precedence, so the gesture is ignored while such a controller
        is connected. After promotion the previous (gesture-elected) master is demoted
        and every remaining user joystick is (re)distributed across the robots.
        """
        if not self.master_settings.enabled:
            logger.info("Master gesture ignored: master joystick feature disabled")
            return

        with self._master_lock:
            if self._guid_master_connected():
                logger.info("Master gesture ignored: a GUID/name-matched master is connected")
                return
            if joystick is self.master_joystick:
                return

            logger.info(f"Electing joystick {joystick.id} as master (SELECT long-press)")

            # Demote a previous gesture-elected master back to a normal user joystick.
            if self.master_joystick is not None:
                self._unregisterMaster()

            # Mark the elected instance and pull it out of normal user assignment.
            self._elected_master_id = joystick.id
            self.unassignJoystick(joystick)

            # Register as master (wires master buttons, applies current target/mode).
            self._registerMaster(joystick)

            # Hand the freed robot (and the demoted old master) back to user joysticks.
            self._assignAllJoysticksToRobots()

    def _assignAllJoysticksToRobots(self):
        """Assign every free (non-master) joystick to a robot still missing one."""
        for robot in self.bilbo_manager.robots.values():
            if self.robotIsAssigned(robot) is not None:
                continue
            joystick = self._getFirstFreeJoystick()  # excludes the master (overridden below)
            if joystick is None:
                break
            self.assignJoystick(joystick, robot)

    def _bind_elect_gesture(self, joystick: Joystick):
        """Bind SELECT long-press on a user joystick to elect it as master.

        Re-applied after every (re)assignment because binding a joystick to a robot
        clears its button callbacks. No-op for the master joystick itself. SELECT is
        unused by the robot button mapping, so clearing it here is safe.
        """
        if joystick is None or self._is_master(joystick) or joystick is self.master_joystick:
            return
        select = joystick.buttons['SELECT']
        if select is None:
            return
        select.clear_callbacks_and_events()
        select.callbacks.long_pressed.register(self.electAsMaster, joystick=joystick)

    # === OVERRIDDEN ASSIGNMENT HOOKS ==================================================================================
    def assignJoystick(self, joystick, bilbo):
        if isinstance(joystick, str):
            joystick = self.joystick_manager.getJoystickById(joystick)
            if joystick is None:
                return
        super().assignJoystick(joystick, bilbo)
        # Re-arm the elect gesture: addJoystick just cleared this joystick's callbacks.
        self._bind_elect_gesture(joystick)

    def unassignJoystick(self, joystick):
        if isinstance(joystick, str):
            joystick = self.joystick_manager.getJoystickById(joystick)
            if joystick is None:
                return
        super().unassignJoystick(joystick)
        # Keep an idle user joystick electable as master (unassign cleared its callbacks).
        # joysticks is keyed by the int instance_id, not the string Joystick.id.
        if joystick.instance_id in self.joystick_manager.joysticks:
            self._bind_elect_gesture(joystick)


# ======================================================================================================================
class IdeenExpo2026_JoystickControl_CommandSet(BILBO_JoystickManager_CommandSet):
    """Joystick CLI for the expo: the standard joystick commands plus master ones."""

    def __init__(self, joystick_control: IdeenExpo2026_JoystickControl):
        super().__init__(joystick_control)
        self.expo_joystick_control = joystick_control

        self.addCommand(Command(name='list-guids',
                                function=self._list_guids,
                                allow_positionals=False,
                                description='List connected joysticks with their GUIDs (to configure the master)'))

        self.addCommand(Command(name='master',
                                function=self._master_status,
                                allow_positionals=False,
                                description='Show master joystick status'))

        self.addCommand(Command(name='master-target',
                                function=self._set_master_target,
                                allow_positionals=True,
                                arguments=[
                                    CommandArgument(name='robot',
                                                    short_name='r',
                                                    type=str,
                                                    description='ID of the robot the master should target',
                                                    optional=False),
                                ],
                                description='Set the robot the master joystick targets'))

        self.addCommand(Command(name='master-override',
                                function=self.expo_joystick_control.overrideTarget,
                                allow_positionals=False,
                                description='Master takes over its current target robot'))

        self.addCommand(Command(name='master-release',
                                function=self.expo_joystick_control.releaseMaster,
                                allow_positionals=False,
                                description='Master releases the robot it is overriding'))

        self.addCommand(Command(name='all-off',
                                function=self.expo_joystick_control.allRobotsOff,
                                allow_positionals=False,
                                description='Switch all robots off'))

        self.addCommand(Command(name='all-on',
                                function=self.expo_joystick_control.allRobotsOn,
                                allow_positionals=False,
                                description='Switch all robots on'))

    # ------------------------------------------------------------------------------------------------------------------
    def _list_guids(self):
        output = ''
        for joystick in self.expo_joystick_control.joystick_manager.joysticks.values():
            output += f"{joystick.id}: {joystick.name} \t guid={joystick.guid}\n"
        if output == '':
            output = 'No joysticks connected'
        self.expo_joystick_control.joystick_manager.logger.info(output)
        return output

    # ------------------------------------------------------------------------------------------------------------------
    def _master_status(self):
        jc = self.expo_joystick_control
        master = jc.master_joystick
        target = jc.master_target
        output = (
            f"Master enabled : {jc.master_settings.enabled}\n"
            f"Master joystick: {master.id if master is not None else 'not connected'}\n"
            f"Target robot   : {target.id if target is not None else None}\n"
            f"Overriding     : {jc.master_active}"
        )
        jc.joystick_manager.logger.info(output)
        return output

    # ------------------------------------------------------------------------------------------------------------------
    def _set_master_target(self, robot: str):
        bilbo = self.expo_joystick_control.bilbo_manager.getRobotById(robot)
        if bilbo is None:
            return f"Robot with ID {robot} not found"
        self.expo_joystick_control.setMasterTarget(bilbo)
