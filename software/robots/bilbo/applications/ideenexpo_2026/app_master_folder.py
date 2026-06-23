"""Master-joystick folder for the mobile App (IdeenExpo 2026).

A single "one page for all important stuff" folder (3 rows × 6 columns):

    Row1: [ Target ][ Speed R1 ][ Speed R2 ]
    Row2: [Override][  Nudge   ][  All On  ]
    Row3: [ All Off][        (spare)       ]

  * **Target** — selects the robot the master controls (``None`` or a connected bilbo).
  * **Speed Rn** — per-robot input "speed" (Slow/Medium/Fast); one selector per connected
    robot, added/removed live as robots connect/disconnect (max 2). It scales that robot's
    *visitor* joystick (see ``bilbo_interfaces.set_input_scale``); the master's Full
    override always drives at full range.
  * **Override Mode** — ``Assist`` / ``Full`` (see :class:`MasterOverrideMode`).
  * **Nudge / All On / All Off** — free a robot from a wall / switch all robots on / off.

The buttons just drive the joystick control / robot interfaces; all override logic lives
in :class:`IdeenExpo2026_JoystickControl`.
"""
import threading

from core.utils.logging_utils import Logger
from extensions.gui.src.app import App, Folder
from extensions.gui.src.lib.objects.python.buttons import MultiStateButton, Button

from robots.bilbo.applications.ideenexpo_2026.joystick_control import (
    IdeenExpo2026_JoystickControl,
    MasterOverrideMode,
)
from robots.bilbo.applications.ideenexpo_2026.settings import JoystickSpeedSettings

# Distance [m] for the master "nudge" button (free the selected robot from a wall).
NUDGE_DISTANCE_M = 0.05  # 5 cm

# Grid slots (row, column) for the per-robot speed selectors. Two slots → max 2 robots,
# matching the deployment ("never more than 2 robots"). Each button is 2 columns wide.
SPEED_SLOTS = [(1, 3), (1, 5)]


# ======================================================================================================================
class IdeenExpo2026_App_Master_Folder:
    folder: Folder

    def __init__(self, app: App, joystick_control: IdeenExpo2026_JoystickControl,
                 speed_settings: JoystickSpeedSettings | None = None):
        self.app = app
        self.joystick_control = joystick_control
        self.logger = Logger('master app folder')

        # --- Speed (input scaling) config ---
        self.speed_settings = speed_settings if speed_settings is not None else JoystickSpeedSettings()
        self._speed_level_names = [lvl.name for lvl in self.speed_settings.levels]
        self._speed_scales = {lvl.name: (lvl.forward, lvl.turn) for lvl in self.speed_settings.levels}
        # Default level applied to a robot on connect (fall back to the first level if the
        # configured name is unknown).
        self._default_level = (self.speed_settings.default_level
                               if self.speed_settings.default_level in self._speed_level_names
                               else (self._speed_level_names[0] if self._speed_level_names else None))
        self.speed_buttons: dict[str, MultiStateButton] = {}   # robot_id -> button
        self._robot_slot: dict[str, int] = {}                  # robot_id -> SPEED_SLOTS index
        self._speed_lock = threading.Lock()

        # One page, 3 rows (FolderPage defaults to 2 rows, 6 columns).
        self.folder = Folder(folder_id='Master', rows=3)
        self._build()
        self.app.addFolder(self.folder, row=1, column=1)

        # Keep target list + speed selectors in sync with the connected robots.
        self.joystick_control.bilbo_manager.callbacks.new_robot.register(self._on_roster_changed)
        self.joystick_control.bilbo_manager.callbacks.robot_disconnected.register(self._on_roster_changed)

        # Reflect master state changes made elsewhere (physical R1 toggle, CLI, GUI)
        # back onto the buttons so the App doesn't drift out of sync.
        self.joystick_control.master_callbacks.master_mode_changed.register(self._sync_mode_button)
        self.joystick_control.master_callbacks.master_target_changed.register(self._sync_target_button)

        # Populate speed selectors for robots already connected at build time.
        self._refresh_speed_controls()

    # === BUILD ========================================================================================================
    def _build(self):
        # --- Row 1: Target selector (None + current bilbos) ---
        self.target_button = MultiStateButton(
            id='master_target',
            states=self._target_states(),
            current_state='None',
            color=[0.15, 0.2, 0.25],
            title='Target',
        )
        self.target_button.callbacks.click.register(self._on_target_click)
        self.target_button.callbacks.state.register(self._on_target_state)
        self.folder.addObject(self.target_button, row=1, column=1, width=2, height=1)
        # Row 1, columns 3 & 5 are filled dynamically with per-robot speed selectors.

        # --- Row 2: Override mode selector ---
        self.mode_button = MultiStateButton(
            id='master_mode',
            states=list(MasterOverrideMode.SELECTABLE),  # ('Assist', 'Full')
            current_state=MasterOverrideMode.ASSIST,
            color=[[0.1, 0.25, 0.12], [0.3, 0.1, 0.1]],  # Assist=green, Full=red
            title='Override',
        )
        self.mode_button.callbacks.click.register(self._on_mode_click)
        self.mode_button.callbacks.state.register(self._on_mode_state)
        self.folder.addObject(self.mode_button, row=2, column=1, width=2, height=1)

        # --- Row 2: Nudge (free the selected robot from a wall) ---
        self.nudge_button = Button(
            widget_id='master_nudge',
            text=f'NUDGE {int(NUDGE_DISTANCE_M * 100)}cm',
            color=[0.15, 0.2, 0.25],
        )
        self.nudge_button.callbacks.click.register(self._on_nudge_click)
        self.folder.addObject(self.nudge_button, row=2, column=3, width=2, height=1)

        # --- Row 2: All robots on ---
        self.all_on_button = Button(
            widget_id='master_all_on',
            text='ALL ON',
            color=[0.1, 0.25, 0.12],
        )
        self.all_on_button.callbacks.click.register(self.joystick_control.allRobotsOn)
        self.folder.addObject(self.all_on_button, row=2, column=5, width=2, height=1)

        # --- Row 3: All robots off (panic) ---
        self.all_off_button = Button(
            widget_id='master_all_off',
            text='ALL OFF',
            color=[0.4, 0, 0],
        )
        self.all_off_button.callbacks.click.register(self.joystick_control.allRobotsOff)
        self.folder.addObject(self.all_off_button, row=3, column=1, width=2, height=1)

    # === TARGET BUTTON ================================================================================================
    def _target_states(self) -> list[str]:
        return ['None'] + list(self.joystick_control.bilbo_manager.robots.keys())

    def _on_target_click(self, *args, **kwargs):
        # Advance to the next target; the state callback applies the selection.
        self.target_button.increaseIndex()

    def _on_target_state(self, button=None, state=None, index=None, **kwargs):
        self.joystick_control.setMasterTarget(None if state == 'None' else state)

    def _on_roster_changed(self, *args, **kwargs):
        """A robot connected / disconnected: refresh the target list and speed selectors."""
        self._refresh_targets()
        self._refresh_speed_controls()

    def _refresh_targets(self, *args, **kwargs):
        """Rebuild the target button's states from the connected robots."""
        states = self._target_states()
        self.target_button.states = states
        self.target_button._state_index = 0  # reset selection to 'None'
        try:
            self.target_button.updateConfig()
        except Exception:
            pass
        # Clear any dangling target/override now that the roster changed.
        self.joystick_control.setMasterTarget(None)

    # === SPEED SELECTORS (one per connected robot, dynamic) ===========================================================
    def _refresh_speed_controls(self, *args, **kwargs):
        """Reconcile the per-robot speed selectors with the connected robots."""
        if not self.speed_settings.enabled or not self._speed_level_names:
            return

        with self._speed_lock:
            current = list(self.joystick_control.bilbo_manager.robots.keys())
            current_set = set(current)

            # Remove selectors for robots that are gone (frees their slot).
            for robot_id in list(self.speed_buttons.keys()):
                if robot_id not in current_set:
                    self._remove_speed_button(robot_id)

            # Add selectors for newly connected robots, into the first free slot.
            for robot_id in current:
                if robot_id in self.speed_buttons:
                    continue
                slot = self._first_free_slot()
                if slot is None:
                    self.logger.warning(
                        f"No free speed-selector slot for robot {robot_id} "
                        f"(max {len(SPEED_SLOTS)} shown)")
                    break
                self._add_speed_button(robot_id, slot)

    def _first_free_slot(self) -> int | None:
        occupied = set(self._robot_slot.values())
        for i in range(len(SPEED_SLOTS)):
            if i not in occupied:
                return i
        return None

    def _add_speed_button(self, robot_id: str, slot: int):
        row, column = SPEED_SLOTS[slot]
        button = MultiStateButton(
            id=f'master_speed_{robot_id}',
            states=self._speed_level_names,
            current_state=self._default_level,
            color=[0.12, 0.2, 0.28],
            title=f'Speed {robot_id}',
        )
        button.callbacks.click.register(self._on_speed_click)
        button.callbacks.state.register(self._make_speed_state_cb(robot_id))
        try:
            self.folder.addObject(button, row=row, column=column, width=2, height=1)
        except Exception as e:
            self.logger.error(f"Could not add speed selector for {robot_id}: {e}")
            return
        self.speed_buttons[robot_id] = button
        self._robot_slot[robot_id] = slot
        # Apply the default level to the robot straight away.
        self._apply_speed(robot_id, self._default_level)

    def _remove_speed_button(self, robot_id: str):
        button = self.speed_buttons.pop(robot_id, None)
        self._robot_slot.pop(robot_id, None)
        if button is None:
            return
        try:
            self.folder.removeObject('page1', button)
        except Exception as e:
            self.logger.warning(f"Could not remove speed selector for {robot_id}: {e}")

    def _on_speed_click(self, button=None, *args, **kwargs):
        # Advance to the next speed level; the state callback applies the scaling.
        if button is not None:
            button.increaseIndex()

    def _make_speed_state_cb(self, robot_id: str):
        def _cb(button=None, state=None, index=None, **kwargs):
            self._apply_speed(robot_id, state)
        return _cb

    def _apply_speed(self, robot_id: str, level_name: str | None):
        if level_name is None:
            return
        robot = self.joystick_control.bilbo_manager.getRobotById(robot_id)
        if robot is None:
            return
        scale = self._speed_scales.get(level_name)
        if scale is None:
            return
        try:
            robot.interfaces.set_input_scale(scale[0], scale[1])
        except Exception as e:
            self.logger.warning(f"Could not set speed '{level_name}' on {robot_id}: {e}")

    # === MODE BUTTON ==================================================================================================
    def _on_mode_click(self, *args, **kwargs):
        self.mode_button.increaseIndex()

    def _on_mode_state(self, button=None, state=None, index=None, **kwargs):
        self.joystick_control.setMasterMode(state)

    # === NUDGE BUTTON =================================================================================================
    def _on_nudge_click(self, *args, **kwargs):
        robot = self.joystick_control.master_target
        if robot is None:
            return
        # control.nudge() does a blocking request/response (timeout 2 s); run it off the
        # app's message thread so the UI stays responsive. Firmware accepts it only in
        # OFF mode with the robot lying over, and auto-picks the direction.
        threading.Thread(
            target=robot.control.nudge,
            kwargs={'distance': NUDGE_DISTANCE_M},
            daemon=True,
        ).start()

    # === STATE SYNC (master state changed elsewhere → reflect on the buttons) ==========================================
    def _sync_mode_button(self, mode=None, *args, **kwargs):
        self._set_button_state_silently(self.mode_button, mode)

    def _sync_target_button(self, robot=None, *args, **kwargs):
        state = 'None' if robot is None else getattr(robot, 'id', 'None')
        self._set_button_state_silently(self.target_button, state)

    @staticmethod
    def _set_button_state_silently(button, state):
        """Update a MultiStateButton's displayed state WITHOUT firing its state
        callback (which would re-enter setMasterMode/setMasterTarget and re-apply)."""
        if state is None or state not in button.states:
            return
        button._state_index = button.states.index(state)  # bypass the property setter
        try:
            button.updateConfig()
        except Exception:
            pass
