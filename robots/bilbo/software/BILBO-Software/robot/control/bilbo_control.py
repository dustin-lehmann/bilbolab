from core.utils.dataclass_utils import from_dict, asdict_optimized
from core.utils.dict_utils import format_floats
from robot.bilbo_common import BILBO_Common, error_handler
from robot.communication.serial.bilbo_serial_messages import BILBO_Control_Event_Message
from robot.control.bilbo_control_config import load_config
# Importing low-level sample class from STM32 interface
from robot.lowlevel.stm32_sample import BILBO_LL_Sample

# === OWN PACKAGES =====================================================================================================
from core.utils.callbacks import callback_definition, CallbackContainer
from robot.communication.bilbo_communication import BILBO_Communication
import robot.lowlevel.stm32_addresses as addresses
from robot.lowlevel.stm32_control import *
from core.utils.events import Event, event_definition, EventFlag
from core.utils.logging_utils import Logger
from robot.control.bilbo_control_data import *
from robot.control.bilbo_control_data import *
from core.utils.data import limit, are_lists_approximately_equal
from core.utils.delayed_executor import delayed_execution

# import robot.control.config as control_config



# === BILBO Control Callbacks ==========================================================================================
@callback_definition
class BILBO_Control_Callbacks:
    """
    Callback container for control-related events.

    Attributes:
        mode_change (CallbackContainer): Callback for mode changes. Expected arguments: mode (BILBO_Control_Mode), forced_change (bool).
        status_change (CallbackContainer): Callback for status changes. Expected arguments: status (BILBO_Control_State), forced_change (bool).
        error (CallbackContainer): Callback for errors.
        on_update (CallbackContainer): Callback for update events.
    """
    mode_change: CallbackContainer  # Inputs: mode: BILBO_Control_Mode, forced_change: bool
    status_change: CallbackContainer  # Inputs: status: BILBO_Control_State, forced_change: bool
    configuration_change: CallbackContainer
    error: CallbackContainer
    on_update: CallbackContainer


@event_definition
class BILBO_Control_Events:
    mode_change: Event = Event(flags=EventFlag('mode', BILBO_Control_Mode))
    configuration_change: Event
    error: Event
    status_change: Event = Event(flags=EventFlag('status', str))
    vic_change: Event
    tic_change: Event


# === BILBO Control ====================================================================================================
class BILBO_Control:
    """
    High-level control class for the BILBO robot.

    This class handles configuration, mode switching, input processing, and communication with the low-level STM32 module.
    It makes use of callbacks for various events (e.g., mode change, status updates) and executes commands via a Wi-Fi interface.
    """

    # Communication interface with BILBO hardware
    _comm: BILBO_Communication

    # Current control statuses and modes (both high-level and low-level)
    status: BILBO_Control_Status
    mode: BILBO_Control_Mode

    mode_ll: BILBO_Control_Mode_LL
    status_ll: BILBO_Control_Status_LL

    # Control configuration (loaded from control_config)
    config: BILBO_ControlConfig

    ll_config: BILBO_LL_ControlConfig

    # External and manual control inputs
    external_input: BILBO_Control_Input
    enable_external_input: bool
    input: BILBO_Control_Input

    # Callback container instance for control events
    callbacks: BILBO_Control_Callbacks

    # The latest low-level control sample received from the STM32 module
    _lowlevel_control_sample: BILBO_LL_Sample

    # Timer for periodic updates (default interval: 0.1 seconds)
    # _updateTimer: IntervalTimer = IntervalTimer(0.1)

    # === INIT =========================================================================================================
    def __init__(self, core: BILBO_Common, comm: BILBO_Communication):
        """
        Initialize the BILBO_Control instance.

        Args:
            comm (BILBO_Communication): Communication interface used to interact with the low-level module.
        """
        self.logger = Logger('CONTROL')
        self.logger.setLevel('INFO')
        # Store communication interface
        self._comm = comm

        self.common = core

        # Load the default configuration later
        self.config = None  # type: Ignore

        # Initialize high-level status and mode to error/off
        self.status = BILBO_Control_Status(BILBO_Control_Status.ERROR)
        self.mode = BILBO_Control_Mode(BILBO_Control_Mode.OFF)
        self.status_ll = BILBO_Control_Status_LL(BILBO_Control_Status_LL.ERROR)
        self.mode_ll = BILBO_Control_Mode_LL(BILBO_Control_Mode_LL.OFF)

        # Initialize control inputs
        self.external_input = BILBO_Control_Input()
        self.input = BILBO_Control_Input()
        self.enable_external_input = True

        # Register the callback for receiving STM32 samples
        self._comm.callbacks.rx_stm32_sample.register(self._lowlevel_sample_callback)

        # Initialize callback container for high-level events
        self.callbacks = BILBO_Control_Callbacks()
        self.events = BILBO_Control_Events()

        # Register commands to the WI-FI module for remote control
        self._comm.wifi.newCommand(identifier='setControlMode',
                                   function=self.set_mode,
                                   arguments=['mode'],
                                   description='Sets the control mode')

        self._comm.wifi.newCommand(identifier='setNormalizedBalancingInput',
                                   function=self.setNormalizedBalancingInput,
                                   arguments=['forward', 'turn'],
                                   description='Sets the Input')

        self._comm.wifi.newCommand(identifier='setSpeed',
                                   function=self.setSpeed,
                                   arguments=['v', 'psi_dot'],
                                   description='Sets the Speed')

        self._comm.wifi.newCommand(identifier='setPIDForward',
                                   function=self.setVelocityControlPID_Forward,
                                   arguments=['P', 'I', 'D'],
                                   description='Sets the PID Control Values for the Forward Velocity')

        self._comm.wifi.newCommand(identifier='setPIDTurn',
                                   function=self.setVelocityControlPID_Turn,
                                   arguments=['P', 'I', 'D'],
                                   description='Sets the PID Control Values for the Turn Velocity')

        self._comm.wifi.newCommand(identifier='enableTIC',
                                   function=self.enableTIC,
                                   arguments=['enable'],
                                   description='Enabled Theta Integral Control')

        self._comm.serial.callbacks.event.register(self._ll_control_event_callback,
                                                   parameters={'messages': [BILBO_Control_Event_Message]})

        # Optionally, a dedicated thread could be started for continuous control updates
        # self._thread = threading.Thread(target=self._threadFunction)

        self._lowlevel_control_sample = None  # Type: Ignore

    # === METHODS ======================================================================================================
    def init(self):
        """
        Placeholder for additional initialization steps.

        This method is intended to be extended as needed.
        """

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        """
        Start the control module by loading the default configuration and setting the control status to NORMAL.

        Returns:
            bool: True if the configuration was loaded successfully; False otherwise.
        """
        self.set_mode(BILBO_Control_Mode.OFF)
        self.config = self.loadConfig('default')
        if self.config is None:
            return False

        self.status = BILBO_Control_Status.NORMAL
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        """
        Main update loop for processing inputs and updating control signals.

        Steps:
            1. Process the latest low-level STM32 sample.
            2. Update external input.
            3. Set the processed input into the system.
            4. Call any user-defined update callbacks.
        """
        # Step 1: Process the STM32 sample
        self._updateFromLowLevelSample(self._lowlevel_control_sample)

        # Step 2: Process the external input and update the control input accordingly
        external_input = self._updateExternalInput(self.external_input)

        # For now, manual input is the only method, so we copy the external input
        self.input = external_input

        # Set the control input in the low-level hardware
        self._setInput(self.input)

        # Call user-defined update callbacks
        self.callbacks.on_update.call()

    # ------------------------------------------------------------------------------------------------------------------
    def loadConfig(self, name):
        """
        Load a control configuration by name and write it to the low-level module.

        Args:
            name (str): Name of the configuration to load.

        Returns:
            control_config.ControlConfig: The loaded configuration if successful, or None otherwise.
        """
        self.logger.debug(f"Load control config \"{name}\"...")
        config = load_config(name)
        if config is None:
            self.logger.warning(f"Control config \"{name}\" not found")
            return None

        # Write the configuration to the hardware
        success = self._setControlConfig(config, verify=True)
        if not success:
            self.logger.warning(f"Control config {name} failed")
            return None

        self.logger.info(f"Control config \"{name}\" loaded!")
        self.config = config
        self._resetExternalInput()
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def saveConfig(self, name, config=None):
        """
        Save the current control configuration.

        Args:
            name (str): Name to save the configuration under.
            config (optional): The configuration data to save. If None, uses the current config.

        Raises:
            NotImplementedError: This function is not implemented.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def set_mode(self, mode: int | BILBO_Control_Mode):
        """
        Set the current control mode.

        The mode can be passed either as an integer or as a BILBO_Control_Mode enum.
        Depending on the selected mode, the corresponding low-level control mode is set.

        Args:
            mode (int or BILBO_Control_Mode): The desired control mode.
        """
        # Convert integer mode to enum if necessary
        if isinstance(mode, int):
            try:
                mode = BILBO_Control_Mode(mode)
            except ValueError:
                self.logger.warning(f"Value of {mode} is not a valid control mode")
                return

        # If the mode is already set, exit early
        if mode == self.mode:
            return

        self.logger.info(f"Setting control mode to {mode.name}")

        # Set the corresponding low-level control mode
        if mode == BILBO_Control_Mode.OFF:
            self._setControlMode_LL(BILBO_Control_Mode_LL.OFF)
            self.mode = BILBO_Control_Mode.OFF
        elif mode == BILBO_Control_Mode.BALANCING:
            self._setControlMode_LL(BILBO_Control_Mode_LL.BALANCING)
            self.mode = BILBO_Control_Mode.BALANCING
        elif mode == BILBO_Control_Mode.VELOCITY:
            self._setControlMode_LL(BILBO_Control_Mode_LL.VELOCITY)
            self.mode = BILBO_Control_Mode.VELOCITY

        elif mode == BILBO_Control_Mode.POSITION:
            self._setControlMode_LL(BILBO_Control_Mode_LL.POSITION)
            self.mode = BILBO_Control_Mode.POSITION
        # Reset external input on mode change
        self._resetExternalInput()
        # Notify callbacks of the mode change
        self.callbacks.mode_change.call(mode, forced_change=False)

    # ------------------------------------------------------------------------------------------------------------------
    def standUp(self):
        """
        Transition the control mode from OFF to BALANCING, and then schedule a switch to VELOCITY.

        This method is used to start the robot's balancing process.
        """
        if not self.mode == BILBO_Control_Mode.OFF:
            return
        self.set_mode(BILBO_Control_Mode.BALANCING)
        # Delay execution to allow balancing before switching to velocity mode
        # delayed_execution(self.setMode, 1, mode=BILBO_Control_Mode.VELOCITY)

    # ------------------------------------------------------------------------------------------------------------------
    def fallOver(self, direction='forward'):
        """
        Simulate a controlled fall over by setting a low speed and switching off control mode.

        Args:
            direction (str): Direction of the fall; valid values are 'forward' or 'backward'.

        Raises:
            Exception: If the provided direction is invalid.
        """
        if not self.mode == BILBO_Control_Mode.VELOCITY:
            return

        if direction == 'forward':
            self.setSpeed(v=0.2, psi_dot=0)
        elif direction == 'backward':
            self.setSpeed(v=-0.2, psi_dot=0)
        else:
            raise Exception("Invalid direction")

        # Schedule a switch to OFF mode after a short delay
        delayed_execution(self.set_mode, 0.5, mode=BILBO_Control_Mode.OFF)

    # ------------------------------------------------------------------------------------------------------------------
    def setNormalizedBalancingInput(self, forward: int | float, turn: int | float, force=False):
        """
        Set the balancing input based on normalized forward and turn values.

        The normalized values are scaled using configuration gains and then combined to compute
        left and right torque commands.

        Args:
            forward (int or float): Normalized forward input.
            turn (int or float): Normalized turn input.
            force (bool): If True, force the low-level command update immediately.
        """

        assert isinstance(forward, (int, float))
        assert isinstance(turn, (int, float))

        if self.mode == BILBO_Control_Mode.BALANCING:
            # Scale the commands using configuration gains
            forward_cmd_scaled = forward * self.config.external_inputs.balancing_input_gain['forward']
            turn_cmd_scaled = turn * self.config.external_inputs.balancing_input_gain['turn']
            # Combine inputs to calculate left and right torque values
            torque_left = -(forward_cmd_scaled + turn_cmd_scaled)
            torque_right = -(forward_cmd_scaled - turn_cmd_scaled)

            # Apply offsets from configuration
            self.external_input.u_ext[0] = torque_left + self.config.general.torque_offset['left']
            self.external_input.u_ext[1] = torque_right + self.config.general.torque_offset['right']

            if force:
                self._setBalancingInput_LL(u_left=torque_left, u_right=torque_right)
        else:
            # If not in balancing mode, no action is taken
            ...

    # ------------------------------------------------------------------------------------------------------------------
    def setNormalizedSpeedInput(self, forward: int | float, turn: int | float):
        """
        Set the velocity input based on normalized forward and turn values.

        Values are first validated to be within [-1, 1] and then scaled with configuration gains.

        Args:
            forward (int or float): Normalized forward speed input.
            turn (int or float): Normalized turn speed input.
        """
        assert isinstance(forward, (int, float))
        assert isinstance(turn, (int, float))

        if not -1 <= forward <= 1:
            self.logger.warning("Normalized forward speed must be between -1 and 1")
            return

        if not -1 <= turn <= 1:
            self.logger.warning("Normalized turn speed must be between -1 and 1")
            return

        if self.mode == BILBO_Control_Mode.VELOCITY:
            # Scale speeds using configuration gains
            forward_speed_scaled = forward * self.config.external_inputs.speed_input_gain['forward']
            turn_speed_scaled = turn * self.config.external_inputs.speed_input_gain['turn']
            self.external_input.v[0] = forward_speed_scaled
            self.external_input.v[1] = turn_speed_scaled
        else:

            # If not in velocity mode, ignore the input
            ...

    # ------------------------------------------------------------------------------------------------------------------
    def setBalancingInput(self, left: float, right: float):
        """
        Set the balancing input directly with left and right torque values.

        Offsets from the configuration are added to the provided inputs.

        Args:
            left (float): Torque for the left motor.
            right (float): Torque for the right motor.
        """
        assert isinstance(left, float)
        assert isinstance(right, float)

        if self.mode == BILBO_Control_Mode.BALANCING:
            left = left + self.config.general.torque_offset['left']
            right = right + self.config.general.torque_offset['right']

            self.external_input.u_ext[0] = left
            self.external_input.u_ext[1] = right

    # ------------------------------------------------------------------------------------------------------------------
    def setSpeed(self, v: float = 0, psi_dot: float = 0):
        """
        Set the speed input for velocity mode.

        The inputs are limited by the maximum velocities defined in the configuration.

        Args:
            v (float): Forward velocity.
            psi_dot (float): Turning velocity.
        """
        assert isinstance(v, (int, float))
        assert isinstance(psi_dot, (int, float))

        if self.mode == BILBO_Control_Mode.VELOCITY:
            # Apply limits defined in the configuration
            v = limit(v, self.config.speed_control.max_speeds['forward'])
            psi_dot = limit(psi_dot, self.config.speed_control.max_speeds['turn'])

            self.external_input.v[0] = v
            self.external_input.v[1] = psi_dot

    # ------------------------------------------------------------------------------------------------------------------
    def setStateFeedbackGain(self, K):
        """
        Set the state feedback gain for control.

        Args:
            K (list): Gain values for state feedback.
        """
        self.logger.info(f"Set State Feedback Gain to {K}")
        self.config.balancing_control.K = K
        self._setStateFeedbackGain_LL(K)

    # ------------------------------------------------------------------------------------------------------------------
    def setVelocityControlPID_Forward(self, P: float, I: float, D: float):
        """
        Set the PID control parameters for forward velocity.

        Args:
            P (float): Proportional gain.
            I (float): Integral gain.
            D (float): Derivative gain.
        """
        self.logger.info(f"Set Velocity Control PID Forward to {P}, {I}, {D}")
        self.config.speed_control.v.Kp = P
        self.config.speed_control.v.Ki = I
        self.config.speed_control.v.Kd = D
        self._setVelocityControlPIDForward_LL(P, I, D)

    # ------------------------------------------------------------------------------------------------------------------
    def setVelocityControlPID_Turn(self, P: float, I: float, D: float):
        """
        Set the PID control parameters for turn velocity.

        Args:
            P (float): Proportional gain.
            I (float): Integral gain.
            D (float): Derivative gain.
        """
        self.logger.info(f"Set Velocity Control PID Turn to {P}, {I}, {D}")
        self.config.speed_control.psidot.Kp = P
        self.config.speed_control.psidot.Ki = I
        self.config.speed_control.psidot.Kd = D
        self._setVelocityControlPIDTurn_LL(P, I, D)

    # ------------------------------------------------------------------------------------------------------------------
    def setVelocityController(self, config):
        """
        Set the velocity controller configuration.

        Args:
            config (TWIPR_Speed_Control_Config): The configuration for the velocity controller.

        Raises:
            NotImplementedError: This method is not yet implemented.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def setMaxWheelSpeed(self, speed: int | float):
        """
        Set the maximum wheel speed.

        Args:
            speed (int or float): Maximum speed to be set.
        """
        self.logger.info(f"Set max wheel speed to {speed}")
        self.config.general.max_wheel_speed = speed
        self._setMaxWheelSpeed_LL(speed)

    # ------------------------------------------------------------------------------------------------------------------
    def enableVelocityIntegralControl(self, enable: bool) -> bool:
        success = self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ENABLE_VELOCITY_INTEGRAL_CONTROL,
            data=enable,
            input_type=ctypes.c_bool,
            output_type=ctypes.c_bool
        )

        if success:
            self.logger.info(f"Set velocity integral control to {enable}")

            self.config.balancing_control.vic.enabled = enable
        else:
            self.logger.warning("Failed to set velocity integral control")

        return success

    # ------------------------------------------------------------------------------------------------------------------
    def enableTIC(self, enable: bool) -> bool:
        if self.mode == BILBO_Control_Mode.OFF:
            self.logger.warning("Cannot enable TIC in OFF mode")
            return False

        success = self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ENABLE_TIC,
            data=enable,
            input_type=ctypes.c_bool,
            output_type=ctypes.c_bool,
        )

        if success:
            self.logger.info(f"Set TIC to {enable}")
            self.config.balancing_control.tic.enabled = enable
        else:
            self.logger.warning("Failed to set TIC")

        return success

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self) -> BILBO_Control_Sample:
        """
        Retrieve the current control sample.

        Returns:
            BILBO_Control_Sample: A copy of the current control status, mode, configuration name, and input.
        """
        sample = BILBO_Control_Sample(
            status=self.status,
            mode=self.mode,
            configuration=self.config.name if self.config else '',
            tic_enabled=self.config.balancing_control.tic.enabled,
        )
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample_dict(self) -> dict:
        sample = {
            'status': self.status,
            'mode': self.mode,
            'tic_enabled': self.config.balancing_control.tic.enabled,
            'configuration': self.config.name if self.config else '',
            # 'input': {}
        }
        return sample

    # = PRIVATE METHODS ================================================================================================
    def _lowlevel_sample_callback(self, sample: BILBO_LL_Sample) -> None:
        """
        Callback function that is triggered upon receiving a new low-level sample from the STM32 module.

        Args:
            sample (BILBO_LL_Sample): The received low-level control sample.
        """
        self._lowlevel_control_sample = sample

    # ------------------------------------------------------------------------------------------------------------------
    def _updateControlConfigFromLL(self, ll_control_config: BILBO_LL_ControlConfig) -> BILBO_ControlConfig:
        control_config = self.config

        control_config.balancing_control.K = ll_control_config.K
        control_config.speed_control.v.Kp = ll_control_config.forward_p
        control_config.speed_control.v.Ki = ll_control_config.forward_i
        control_config.speed_control.v.Kd = ll_control_config.forward_d
        control_config.speed_control.psidot.Kp = ll_control_config.turn_p
        control_config.speed_control.psidot.Ki = ll_control_config.turn_i
        control_config.speed_control.psidot.Kd = ll_control_config.turn_d
        control_config.balancing_control.vic.enabled = ll_control_config.vic_enabled
        control_config.balancing_control.vic.max_error = ll_control_config.vic_max_error
        control_config.balancing_control.vic.v_limit = ll_control_config.vic_v_limit
        control_config.balancing_control.vic.ki = ll_control_config.vic_ki
        control_config.balancing_control.tic.enabled = ll_control_config.tic_enabled
        control_config.balancing_control.tic.ki = ll_control_config.tic_ki
        control_config.balancing_control.tic.max_error = ll_control_config.tic_max_error
        control_config.balancing_control.tic.theta_limit = ll_control_config.tic_theta_limit

        self.config = control_config

        return control_config

    # ------------------------------------------------------------------------------------------------------------------
    def _ll_mode_change_callback(self, mode_ll: BILBO_Control_Mode_LL, *args, **kwargs) -> None:
        mode = None
        if mode_ll == BILBO_Control_Mode_LL.OFF:
            mode = BILBO_Control_Mode.OFF
        elif mode_ll == BILBO_Control_Mode_LL.DIRECT:
            mode = BILBO_Control_Mode.DIRECT
        elif mode_ll == BILBO_Control_Mode_LL.BALANCING:
            mode = BILBO_Control_Mode.BALANCING
        elif mode_ll == BILBO_Control_Mode_LL.VELOCITY:
            mode = BILBO_Control_Mode.VELOCITY
        elif mode_ll == BILBO_Control_Mode_LL.POSITION:
            mode = BILBO_Control_Mode.POSITION
        else:
            raise Exception("Unknown low-level mode")

        self.mode = mode

        self.callbacks.mode_change.call(mode, forced_change=False)
        self.events.mode_change.set(data=mode, flags={'mode': mode})

        # Send Event to Host
        self._comm.wifi.sendEvent(event='control',
                                  data={
                                      'event': 'mode_change',
                                      'mode': mode,
                                      'config': asdict_optimized(self.config),
                                  })

    # ------------------------------------------------------------------------------------------------------------------
    def _ll_configuration_change_callback(self, configuration: dict):

        try:
            control_config_ll = from_dict(BILBO_LL_ControlConfig, configuration)
        except Exception as e:
            self.logger.warning(f"Failed to parse low-level configuration: {e}")
            return

        self.logger.info(f"Received changed low-level configuration: {configuration}")

        self._updateControlConfigFromLL(control_config_ll)

        self.callbacks.configuration_change.call(configuration)
        self.events.configuration_change.set(data=configuration)
        self._comm.wifi.sendEvent(event='control',
                                  data={
                                      'event': 'configuration_change',
                                      'configuration': asdict_optimized(self.config),
                                  })

    # ------------------------------------------------------------------------------------------------------------------
    def _ll_vic_change_callback(self, configuration: dict):

        try:
            control_config_ll = from_dict(BILBO_LL_ControlConfig, configuration)
        except Exception as e:
            self.logger.warning(f"Failed to parse low-level configuration: {e}")
            return

        self._updateControlConfigFromLL(control_config_ll)

        self._comm.wifi.sendEvent(event='control',
                                  data={
                                      'event': 'vic_change',
                                      'vic_enabled': self.config.balancing_control.vic.enabled,
                                      'configuration': asdict_optimized(self.config),
                                  })

        self.logger.info(f"VIC enabled: {self.config.balancing_control.vic.enabled}")

    # ------------------------------------------------------------------------------------------------------------------
    def _ll_tic_change_callback(self, configuration: dict):

        try:
            control_config_ll = from_dict(BILBO_LL_ControlConfig, configuration)
        except Exception as e:
            self.logger.warning(f"Failed to parse low-level configuration: {e}")
            return

        self._updateControlConfigFromLL(control_config_ll)

        self._comm.wifi.sendEvent(event='control',
                                  data={
                                      'event': 'tic_change',
                                      'tic_enabled': self.config.balancing_control.tic.enabled,
                                      'configuration': configuration,
                                  })

        self.logger.info(f"TIC enabled: {self.config.balancing_control.tic.enabled}")

    # ------------------------------------------------------------------------------------------------------------------
    def _setControlConfig(self, config: BILBO_ControlConfig, verify: bool = False):

        control_config = bilbo_control_configuration_ll_t(
            K=(ctypes.c_float * 8)(*config.balancing_control.K),  # type: ignore
            forward_p=config.speed_control.v.Kp,
            forward_i=config.speed_control.v.Ki,
            forward_d=config.speed_control.v.Kd,
            turn_p=config.speed_control.psidot.Kp,
            turn_i=config.speed_control.psidot.Ki,
            turn_d=config.speed_control.psidot.Kd,
            vic_enabled=config.balancing_control.vic.enabled,
            vic_ki=config.balancing_control.vic.ki,
            vic_max_error=config.balancing_control.vic.max_error,
            vic_v_limit=config.balancing_control.vic.v_limit,
            tic_enabled=config.balancing_control.tic.enabled,
            tic_ki=config.balancing_control.tic.ki,
            tic_max_error=config.balancing_control.tic.max_error,
            tic_theta_limit=config.balancing_control.tic.theta_limit
        )

        success = self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.SET_CONFIG,
            data=control_config,
            input_type=bilbo_control_configuration_ll_t,  # type: ignore
            output_type=ctypes.c_bool,
            timeout=1
        )

        if success is None or not success:
            self.logger.warning("Failed to set control configuration")
            return False

        self._setMaxWheelSpeed_LL(speed=config.general.max_wheel_speed)

        if verify:
            # Read back configuration from the low-level module
            config_ll = self._readControlConfig_LL()

            if config_ll is None:
                return False

            # Verify state feedback gain
            if not are_lists_approximately_equal(config_ll['K'], config.balancing_control.K):
                self.logger.warning("State Feedback Gain not set correctly")
                return False

            # Verify forward PID control values
            if not are_lists_approximately_equal(
                    [config.speed_control.v.Kp,
                     config.speed_control.v.Ki,
                     config.speed_control.v.Kd],
                    [config_ll['forward_p'], config_ll['forward_i'], config_ll['forward_d']]):
                self.logger.warning("PID Control Values not set correctly")
                return False

            # Verify turn PID control values
            if not are_lists_approximately_equal(
                    [config.speed_control.psidot.Kp,
                     config.speed_control.psidot.Ki,
                     config.speed_control.psidot.Kd],
                    [config_ll['turn_p'], config_ll['turn_i'], config_ll['turn_d']]):
                self.logger.warning("PID Control Values not set correctly")
                return False

        return success

    # ------------------------------------------------------------------------------------------------------------------
    def _setControlMode_LL(self, mode: BILBO_Control_Mode_LL) -> None:
        """
        Set the low-level control mode by sending the corresponding command via the serial interface.

        Args:
            mode (BILBO_Control_Mode_LL): The low-level control mode to set.
        """
        assert (isinstance(mode, BILBO_Control_Mode_LL))
        self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_MODE,
            data=mode.value,
            input_type=ctypes.c_uint8
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _readControlMode_LL(self):
        """
        Placeholder for reading the current low-level control mode.

        Returns:
            NotImplemented
        """
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _readControlState_LL(self):
        """
        Placeholder for reading the current low-level control state.

        Returns:
            NotImplemented
        """
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _setMaxWheelSpeed_LL(self, speed: int | float):
        """
        Set the maximum wheel speed in the low-level module.

        Args:
            speed (int or float): The maximum wheel speed.
        """
        self._comm.serial.writeValue(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_RW_MAX_WHEEL_SPEED,
            value=float(speed),
            type=ctypes.c_float
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _setStateFeedbackGain_LL(self, K) -> None:
        """
        Set the state feedback gain in the low-level module.

        Args:
            K (list): List of gain values (must have 8 elements).
        """
        assert (isinstance(K, list))
        assert (len(K) == 8)
        assert (all(isinstance(elem, (float, int)) for elem in K))
        self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_K,
            data=K,
            input_type=ctypes.c_float * 8,  # type: Ignore
            output_type=None
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _setVelocityControlPIDForward_LL(self, P: float, I: float, D: float) -> None:
        """
        Set the forward velocity PID parameters in the low-level module.

        Args:
            P (float): Proportional gain.
            I (float): Integral gain.
            D (float): Derivative gain.
        """
        self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_FORWARD_PID,
            data=[P, I, D],
            input_type=ctypes.c_float * 3,  # type: Ignore
            output_type=None
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _setVelocityControlPIDTurn_LL(self, P: float, I: float, D: float) -> None:
        """
        Set the turn velocity PID parameters in the low-level module.

        Args:
            P (float): Proportional gain.
            I (float): Integral gain.
            D (float): Derivative gain.
        """
        self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_TURN_PID,
            data=[P, I, D],
            input_type=ctypes.c_float * 3,  # type: Ignore
            output_type=None
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _setVelocityControl_LL(self):
        """
        Placeholder for setting the complete velocity control.

        Raises:
            NotImplementedError: This method is not implemented.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def _setBalancingInput_LL(self, u_left: float, u_right: float):
        """
        Set the balancing input in the low-level module.

        Args:
            u_left (float): Left motor torque.
            u_right (float): Right motor torque.
        """
        assert (isinstance(u_left, (int, float)))
        assert (isinstance(u_right, (int, float)))
        data = {
            'u_left': float(u_left),
            'u_right': float(u_right)
        }

        result = self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_BALANCING_INPUT,
            data=data,
            input_type=bilbo_control_balancing_input_t,
            output_type=ctypes.c_bool,
            timeout=1
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _setSpeedInput_LL(self, v: float, psi_dot: float) -> None:
        """
        Set the speed input in the low-level module.

        Args:
            v (float): Forward velocity.
            psi_dot (float): Turning velocity.
        """
        assert (isinstance(v, (int, float)))
        assert (isinstance(psi_dot, (int, float)))
        data = {
            'forward': v,
            'turn': psi_dot
        }
        self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_SPEED_INPUT,
            data=data,
            input_type=bilbo_control_speed_input_t
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _setDirectInput_LL(self, u_left: float, u_right: float) -> None:
        """
        Set direct control input in the low-level module.

        Args:
            u_left (float): Left motor direct input.
            u_right (float): Right motor direct input.
        """
        assert (isinstance(u_left, float))
        assert (isinstance(u_right, float))
        data = {
            'u_left': u_left,
            'u_right': u_right
        }
        self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_DIRECT_INPUT,
            data=data,
            input_type=bilbo_control_direct_input_t
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _readControlConfig_LL(self) -> dict:
        """
        Read the current control configuration from the low-level module.

        Returns:
            dict: A dictionary containing the low-level control configuration.
        """
        return self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_READ_CONFIG,
            data=None,
            output_type=bilbo_control_configuration_ll_t
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _resetExternalInput(self):
        """
        Reset all external control inputs to zero.
        """
        self.external_input.u_ext = [0, 0]
        self.external_input.v = [0, 0]

    # ------------------------------------------------------------------------------------------------------------------
    def _updateFromLowLevelSample(self, sample: BILBO_LL_Sample):
        """
        Update the internal state based on the latest low-level sample from the STM32 module.

        This method updates both the control status and mode by comparing the sample with the current state.

        Args:
            sample (BILBO_LL_Sample): The received low-level control sample.
        """
        # Update low-level status from sample and check for errors
        try:
            status_ll = BILBO_Control_Status_LL(sample.control.status)
        except ValueError:
            error_message = f"Received invalid status: {sample.control.status}. Possible mismatch of" \
                            f"lowlevel firmware and python module."
            self.logger.error(error_message)
            error_handler(severity='error', message=error_message)
            return

        if status_ll is not self.status_ll:
            if status_ll == BILBO_Control_Status_LL.ERROR:
                self.logger.error("Error in the LL Control Module")
        self.status_ll = status_ll

        # Map low-level status to high-level status
        status = None
        if status_ll == BILBO_Control_Status_LL.ERROR:
            status = BILBO_Control_Status.ERROR
        elif status_ll == BILBO_Control_Status_LL.RUNNING:
            status = BILBO_Control_Status.NORMAL

        # If the status changed, call the status change callback
        if status != self.status:
            self.callbacks.status_change.call(status, forced_change=True)

        # Update low-level mode from sample
        mode_ll = BILBO_Control_Mode_LL(sample.control.mode)
        self.mode_ll = mode_ll

        # Map low-level mode to high-level mode
        mode = None
        if mode_ll == BILBO_Control_Mode_LL.OFF:
            mode = BILBO_Control_Mode.OFF
        elif mode_ll == BILBO_Control_Mode_LL.DIRECT:
            mode = BILBO_Control_Mode.DIRECT
        elif mode_ll == BILBO_Control_Mode_LL.BALANCING:
            mode = BILBO_Control_Mode.BALANCING
        elif mode_ll == BILBO_Control_Mode_LL.VELOCITY:
            mode = BILBO_Control_Mode.VELOCITY
        else:
            return

        # self.mode = mode

    # ------------------------------------------------------------------------------------------------------------------
    def _updateExternalInput(self, external_input: BILBO_Control_Input):
        """
        Update the external input based on the current control mode.

        Args:
            external_input (BILBO_Control_Input): The current external input.

        Returns:
            BILBO_Control_Input: The updated control input.
        """
        control_input = BILBO_Control_Input()

        # If external input is disabled or mode is OFF, return a zeroed input
        if not self.enable_external_input:
            return control_input

        if self.mode == BILBO_Control_Mode.OFF:
            return control_input
        elif self.mode == BILBO_Control_Mode.DIRECT:
            raise NotImplementedError("Direct control input not yet implemented")
        elif self.mode == BILBO_Control_Mode.BALANCING:
            control_input.u_ext = [self.external_input.u_ext[0], self.external_input.u_ext[1]]
        elif self.mode == BILBO_Control_Mode.VELOCITY:
            control_input.v = [self.external_input.v[0], self.external_input.v[1]]

        return control_input

    # ------------------------------------------------------------------------------------------------------------------
    def _setInput(self, input: BILBO_Control_Input):
        """
        Set the input to the low-level module based on the current control mode.

        Args:
            input (BILBO_Control_Input): The input to be applied.
        """
        if self.mode == BILBO_Control_Mode.OFF:
            return

        elif self.mode == BILBO_Control_Mode.DIRECT:
            # self._setDirectInput_LL(input.direct.u_left, input.direct.u_right)
            self.logger.error("Direct control is not implemented yet")
        elif self.mode == BILBO_Control_Mode.BALANCING:
            self._setBalancingInput_LL(input.u_ext[0], input.u_ext[1])
        elif self.mode == BILBO_Control_Mode.VELOCITY:
            self.logger.error("Velocity control is not implemented yet")
            # self._setSpeedInput_LL(input.velocity.forward, input.velocity.turn)

    # ------------------------------------------------------------------------------------------------------------------
    def _ll_control_event_callback(self, message: BILBO_Control_Event_Message, *args, **kwargs):

        event = BILBO_Control_Event_Type(message.data['event'])  # type: ignore

        if event == BILBO_Control_Event_Type.ERROR:
            self.logger.error(f"Error in the LL Control Module: {message.data['error']}")  # type: ignore
        elif event == BILBO_Control_Event_Type.MODE_CHANGED:
            self._ll_mode_change_callback(BILBO_Control_Mode_LL(message.data['mode']))  # type: ignore
        elif event == BILBO_Control_Event_Type.CONFIGURATION_CHANGED:
            self._ll_configuration_change_callback(message.data['config'])  # type: ignore
        elif event == BILBO_Control_Event_Type.VIC_CHANGED:
            self._ll_vic_change_callback(message.data['config'])  # type: ignore
        elif event == BILBO_Control_Event_Type.TIC_CHANGED:
            self._ll_tic_change_callback(message.data['config'])  # type: ignore
