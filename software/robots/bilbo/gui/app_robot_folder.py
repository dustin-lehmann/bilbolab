from extensions.gui.src.app import App, Folder
from extensions.gui.src.lib.objects.python.buttons import MultiStateButton, Button
from extensions.hardware.joystick.joystick_manager import Joystick
from robots.bilbo.manager.bilbo_joystick_control import BILBO_JoystickControl
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode


# ======================================================================================================================
class BILBO_Application_App_Robot_Folder:
    folder: Folder

    # === INIT =========================================================================================================
    def __init__(self, robot: BILBO, app: App, joystick_control: BILBO_JoystickControl):
        self.robot = robot
        self.app = app
        self.joystick_control = joystick_control
        self.folder = Folder(folder_id=robot.core.id)

        self._buildFolder()

    # === METHODS ======================================================================================================
    def _buildFolder(self):
        # --- MODE BUTTON (same behavior as in GUI Category) ---
        self.mode_button = MultiStateButton(
            id='mode_button',
            states=['OFF', 'BALANCING', 'POSITION'],
            color=[[0.4, 0, 0], [0, 0.4, 0], [0, 0, 0.4]],
            title='Mode',
        )
        self.folder.addObject(self.mode_button, row=1, column=2, width=1, height=1)

        # Map robot control mode <-> button label
        _mode_mapping = {
            BILBO_Control_Mode.OFF: 'OFF',
            BILBO_Control_Mode.BALANCING: 'BALANCING',
            BILBO_Control_Mode.VELOCITY: 'VELOCITY',
            BILBO_Control_Mode.POSITION: 'POSITION',
        }

        # Initialize button state from current robot mode
        try:
            self.mode_button.state = _mode_mapping[self.robot.control.mode]
        except Exception:
            # Fallback if anything unexpected happens
            self.mode_button.state = 'OFF'

        # Click handler: set robot control mode based on desired state
        def _mode_click_handler(*cb_args, **cb_kwargs):
            # Be defensive about callback signature: could be (state, index, ...) or (index, ...)
            idx = cb_kwargs.get('index', None)
            if idx is None:
                if len(cb_args) >= 2:
                    idx = cb_args[1]
                elif len(cb_args) >= 1:
                    idx = cb_args[0]
                else:
                    # Fallback to current state index if not provided
                    try:
                        idx = self.mode_button.states.index(self.mode_button.state)
                    except Exception:
                        idx = 0
            idx = int(idx)
            desired = self.mode_button.getStateByIndex(idx + 1)  # API is 1-based
            self.robot.control.setControlMode(
                BILBO_Control_Mode.OFF if desired == 'OFF' else BILBO_Control_Mode.BALANCING
            )

        self.mode_button.callbacks.click.register(_mode_click_handler)

        # --- TIC BUTTON (same behavior as in GUI Category) ---
        self.tic_button = MultiStateButton(
            id='tic_button',
            states=['OFF', 'ON'],
            color=[[0.4, 0, 0], [0, 0.4, 0]],
            title='TIC',
        )
        self.folder.addObject(self.tic_button, row=1, column=3, width=1, height=1)

        # Click handler: toggle TIC on the controller
        def _tic_click_handler(*cb_args, **cb_kwargs):
            idx = cb_kwargs.get('index', None)
            if idx is None:
                if len(cb_args) >= 2:
                    idx = cb_args[1]
                elif len(cb_args) >= 1:
                    idx = cb_args[0]
                else:
                    try:
                        idx = self.tic_button.states.index(self.tic_button.state)
                    except Exception:
                        idx = 0
            idx = int(idx)
            desired = self.tic_button.getStateByIndex(idx + 1)
            self.robot.control.enableTIC(desired == 'ON')

        self.tic_button.callbacks.click.register(_tic_click_handler)

        def robot_control_config_change_callback(config):
            tic_enabled = config['balancing_control']['tic']['enabled']
            self.tic_button.state = 'ON' if tic_enabled else 'OFF'

        self.robot.control.callbacks.configuration_changed.register(robot_control_config_change_callback)

        _mode_mapping = {
            BILBO_Control_Mode.OFF: 'OFF',
            BILBO_Control_Mode.BALANCING: 'BALANCING',
            BILBO_Control_Mode.VELOCITY: 'VELOCITY',
            BILBO_Control_Mode.POSITION: 'POSITION',
        }

        def robot_control_mode_change_callback(mode):
            self.mode_button.state = _mode_mapping[mode]

        self.robot.control.callbacks.mode_changed.register(robot_control_mode_change_callback)

        # --- Interface Buttons ---
        self.start_button = Button(widget_id='start_button', text='Start', color=[0.0, 0.4, 0.0])
        self.start_button.callbacks.click.register(self.robot.core.interface_events.start.set, discard_inputs=True)
        self.folder.addObject(self.start_button, row=2, column=1, width=1, height=1)

        self.resume_button = Button(widget_id='resume_button', text='Resume', color=[75 / 255, 82 / 255, 56 / 255])
        self.resume_button.callbacks.click.register(self.robot.core.interface_events.resume.set, discard_inputs=True)
        self.folder.addObject(self.resume_button, row=2, column=2, width=1, height=1)

        self.revert_button = Button(widget_id='revert_button', text='Revert', color=[59 / 255, 20 / 255, 120 / 255])
        self.revert_button.callbacks.click.register(self.robot.core.interface_events.revert.set, discard_inputs=True)
        self.folder.addObject(self.revert_button, row=2, column=3, width=1, height=1)

        self.stop_button = Button(widget_id='stop_button', text='Stop', color=[0.4, 0, 0])
        self.stop_button.callbacks.click.register(self.robot.core.interface_events.stop.set, discard_inputs=True)
        self.folder.addObject(self.stop_button, row=2, column=4, width=1, height=1)

        # --- Joystick Button ---
        self.joystick_button = Button(widget_id='joystick_button', image='gamepad.png')
        self.folder.addObject(self.joystick_button, row=2, column=6, width=1, height=1)

        # Check if joystick is assigned
        if self.joystick_control.robotIsAssigned(self.robot):
            self.joystick_button.dim(False)
        else:
            self.joystick_button.dim(True)

        def joystick_button_callback(*args, **kwargs):
            if self.joystick_control.robotIsAssigned(self.robot):
                return
            joystick = self.joystick_control.getFirstJoystick()
            if joystick is None:
                return
            self.joystick_control.assignJoystick(joystick, self.robot)

        def joystick_button_long_callback(*args, **kwargs):
            if self.joystick_control.robotIsAssigned(self.robot):
                self.joystick_control.unassignJoystick(self.robot.interfaces.joystick)

        self.joystick_button.callbacks.click.register(joystick_button_callback)
        self.joystick_button.callbacks.longClick.register(joystick_button_long_callback)

        def new_js_assignment_callback(joystick: Joystick, robot: BILBO):
            if robot == self.robot:
                self.joystick_button.dim(False)

        def js_assignment_removed_callback(joystick: Joystick, robot: BILBO):
            if robot == self.robot:
                self.joystick_button.dim(True)

        self.joystick_control.callbacks.new_assignment.register(new_js_assignment_callback)
        self.joystick_control.callbacks.assigment_removed.register(js_assignment_removed_callback)

