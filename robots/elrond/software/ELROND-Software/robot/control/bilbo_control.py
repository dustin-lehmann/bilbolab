import copy
import dataclasses
import threading
import ctypes  # Needed for ctypes types in serial communication
import time

# Importing low-level sample class from STM32 interface
from robot.lowlevel.stm32_sample import BILBO_LL_Sample

# === OWN PACKAGES =====================================================================================================
from utils.callbacks import Callback, callback_handler, CallbackContainer
from robot.communication.bilbo_communication import BILBO_Communication, BILBO_Communication_Callbacks
import robot.setup as settings
import robot.lowlevel.stm32_addresses as addresses
from robot.lowlevel.stm32_control import *
from utils.logging_utils import Logger
from robot.control.definitions import *
from utils.data import limit, are_lists_approximately_equal
from utils.time import IntervalTimer
from utils.delayed_executor import delayed_execution
import robot.control.config as control_config

# === Logger ===========================================================================================================
logger = Logger('control')
logger.setLevel('INFO')


# === BILBO Control Callbacks ==========================================================================================
@callback_handler
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
    error: CallbackContainer
    on_update: CallbackContainer


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
    config: control_config.ControlConfig

    # External and manual control inputs
    external_input: BILBO_Control_Input
    enable_external_input: bool
    input: BILBO_Control_Input

    # Callback container instance for control events
    callbacks: BILBO_Control_Callbacks

    # Latest low-level control sample received from the STM32 module
    _lowlevel_control_sample: BILBO_LL_Sample

    # Timer for periodic updates (default interval: 0.1 seconds)
    # _updateTimer: IntervalTimer = IntervalTimer(0.1)

    # === INIT =========================================================================================================
    def __init__(self, comm: BILBO_Communication):
        """
        Initialize the BILBO_Control instance.

        Args:
            comm (BILBO_Communication): Communication interface used to interact with the low-level module.
        """
        # Store communication interface
        self._comm = comm

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

        # Initialize callbacks container for high-level events
        self.callbacks = BILBO_Control_Callbacks()

        # Register commands to the WI-FI module for remote control
        self._comm.wifi.addCommand(identifier='setControlMode',
                                   callback=self.setMode,
                                   arguments=['mode'],
                                   description='Sets the control mode')

        self._comm.wifi.addCommand(identifier='setNormalizedBalancingInput',
                                   callback=self.setNormalizedBalancingInput,
                                   arguments=['forward', 'turn'],
                                   description='Sets the Input')

        self._comm.wifi.addCommand(identifier='setSpeed',
                                   callback=self.setSpeed,
                                   arguments=['v', 'psi_dot'],
                                   description='Sets the Speed')

        self._comm.wifi.addCommand(identifier='setPIDForward',
                                   callback=self.setVelocityControlPID_Forward,
                                   arguments=['P', 'I', 'D'],
                                   description='Sets the PID Control Values for the Forward Velocity')

        self._comm.wifi.addCommand(identifier='setPIDTurn',
                                   callback=self.setVelocityControlPID_Turn,
                                   arguments=['P', 'I', 'D'],
                                   description='Sets the PID Control Values for the Turn Velocity')

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

        # Step 2: Process the external input and update control input accordingly
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
        logger.debug(f"Load control config \"{name}\"...")
        config = control_config.load_config(name)
        if config is None:
            logger.warning(f"Control config \"{name}\" not found")
            return None

        # Write the configuration to the hardware
        success = self._setControlConfig(config, verify=True)
        if not success:
            logger.warning(f"Control config {name} failed")
            return None

        logger.info(f"Control config \"{name}\" loaded!")
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
    def setMode(self, mode: (int, BILBO_Control_Mode)):
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
                logger.warning(f"Value of {mode} is not a valid control mode")
                return

        # If the mode is already set, exit early
        if mode == self.mode:
            return

        logger.info(f"Setting control mode to {mode.name}")

        # Set the corresponding low-level control mode
        if mode == BILBO_Control_Mode.OFF:
            self._setControlMode_LL(BILBO_Control_Mode_LL.OFF)
        elif mode == BILBO_Control_Mode.BALANCING:
            self._setControlMode_LL(BILBO_Control_Mode_LL.BALANCING)
        elif mode == BILBO_Control_Mode.VELOCITY:
            self._setControlMode_LL(BILBO_Control_Mode_LL.VELOCITY)

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
        self.setMode(BILBO_Control_Mode.BALANCING)
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
        delayed_execution(self.setMode, 0.5, mode=BILBO_Control_Mode.OFF)

    # ------------------------------------------------------------------------------------------------------------------
    def setNormalizedBalancingInput(self, forward: (int, float), turn: (int, float), force=False):
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
            forward_cmd_scaled = forward * self.config.manual.torque.forward_torque_gain
            turn_cmd_scaled = turn * self.config.manual.torque.turn_torque_gain
            # Combine inputs to calculate left and right torque values
            torque_left = -(forward_cmd_scaled + turn_cmd_scaled)
            torque_right = -(forward_cmd_scaled - turn_cmd_scaled)

            # Apply offsets from configuration
            self.external_input.balancing.u_left = torque_left + self.config.general.torque_offset[0]
            self.external_input.balancing.u_right = torque_right + self.config.general.torque_offset[1]

            if force:
                self._setBalancingInput_LL(u_left=torque_left, u_right=torque_right)
        else:
            # If not in balancing mode, no action is taken
            ...

    # ------------------------------------------------------------------------------------------------------------------
    def setNormalizedSpeedInput(self, forward: (int, float), turn: (int, float)):
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
            logger.warning("Normalized forward speed must be between -1 and 1")
            return

        if not -1 <= turn <= 1:
            logger.warning("Normalized turn speed must be between -1 and 1")
            return

        if self.mode == BILBO_Control_Mode.VELOCITY:
            # Scale speeds using configuration gains
            forward_speed_scaled = forward * self.config.manual.velocity.forward_velocity_gain
            turn_speed_scaled = turn * self.config.manual.velocity.turn_velocity_gain
            self.external_input.velocity.forward = forward_speed_scaled
            self.external_input.velocity.turn = turn_speed_scaled
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
            left = left + self.config.general.torque_offset[0]
            right = right + self.config.general.torque_offset[1]

            self.external_input.balancing.u_left = left
            self.external_input.balancing.u_right = right

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
            v = limit(v, self.config.manual.velocity.max_forward_velocity)
            psi_dot = limit(psi_dot, self.config.manual.velocity.max_turn_velocity)

            self.external_input.velocity.forward = v
            self.external_input.velocity.turn = psi_dot

    # ------------------------------------------------------------------------------------------------------------------
    def setStateFeedbackGain(self, K):
        """
        Set the state feedback gain for control.

        Args:
            K (list): Gain values for state feedback.
        """
        logger.info(f"Set State Feedback Gain to {K}")
        self.config.statefeedback.gain = K
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
        logger.info(f"Set Velocity Control PID Forward to {P}, {I}, {D}")
        self.config.velocity_control.forward.feedback.Kp = P
        self.config.velocity_control.forward.feedback.Ki = I
        self.config.velocity_control.forward.feedback.Kd = D
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
        logger.info(f"Set Velocity Control PID Turn to {P}, {I}, {D}")
        self.config.velocity_control.turn.feedback.Kp = P
        self.config.velocity_control.turn.feedback.Ki = I
        self.config.velocity_control.turn.feedback.Kd = D
        self._setVelocityControlPIDTurn_LL(P, I, D)

    # ------------------------------------------------------------------------------------------------------------------
    def setVelocityController(self, config: TWIPR_Speed_Control_Config):
        """
        Set the velocity controller configuration.

        Args:
            config (TWIPR_Speed_Control_Config): The configuration for the velocity controller.

        Raises:
            NotImplementedError: This method is not yet implemented.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def setMaxWheelSpeed(self, speed: (int, float)):
        """
        Set the maximum wheel speed.

        Args:
            speed (int or float): Maximum speed to be set.
        """
        logger.info(f"Set max wheel speed to {speed}")
        self.config.safety.max_speed = speed
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
            logger.info(f"Set velocity integral control to {enable}")

            self.config.statefeedback.vic.enabled = enable
        else:
            logger.warning("Failed to set velocity integral control")

        return success

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self) -> TWIPR_Control_Sample:
        """
        Retrieve the current control sample.

        Returns:
            TWIPR_Control_Sample: A copy of the current control status, mode, configuration name, and input.
        """
        # sample = TWIPR_Control_Sample(
        #     status=self.status,
        #     mode=self.mode,
        #     configuration=self.config.name,
        #     input=copy.copy(self.input)
        # )

        sample = {
            'status': self.status,
            'mode': self.mode,
            'configuration': self.config.name if self.config else '',
            'input': {}
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
    def _setControlConfig(self, config: control_config.ControlConfig, verify: bool = False):

        control_config = bilbo_control_configuration_ll_t(
            K=(ctypes.c_float * 8)(*config.statefeedback.gain),  # type: ignore
            forward_p=config.velocity_control.forward.feedback.Kp,
            forward_i=config.velocity_control.forward.feedback.Ki,
            forward_d=config.velocity_control.forward.feedback.Kd,
            turn_p=config.velocity_control.turn.feedback.Kp,
            turn_i=config.velocity_control.turn.feedback.Ki,
            turn_d=config.velocity_control.turn.feedback.Kd,
            vic_enabled=config.statefeedback.vic.enabled,
            vic_ki=config.statefeedback.vic.Ki,
            vic_max_error=config.statefeedback.vic.max_error,
            vic_v_limit=config.statefeedback.vic.velocity_threshold
        )

        success = self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.SET_CONFIG,
            data=control_config,
            input_type=bilbo_control_configuration_ll_t,
            output_type=ctypes.c_bool,
            timeout=1
        )

        if success is None or not success:
            logger.warning("Failed to set control configuration")
            return False

        self._setMaxWheelSpeed_LL(speed=config.safety.max_speed)

        if verify:
            # Read back configuration from low-level module
            config_ll = self._readControlConfig_LL()

            if config_ll is None:
                return False

            # Verify state feedback gain
            if not are_lists_approximately_equal(config_ll['K'], config.statefeedback.gain):
                logger.warning("State Feedback Gain not set correctly")
                return False

            # Verify forward PID control values
            if not are_lists_approximately_equal(
                    [config.velocity_control.forward.feedback.Kp,
                     config.velocity_control.forward.feedback.Ki,
                     config.velocity_control.forward.feedback.Kd],
                    [config_ll['forward_p'], config_ll['forward_i'], config_ll['forward_d']]):
                logger.warning("PID Control Values not set correctly")
                return False

            # Verify turn PID control values
            if not are_lists_approximately_equal(
                    [config.velocity_control.turn.feedback.Kp,
                     config.velocity_control.turn.feedback.Ki,
                     config.velocity_control.turn.feedback.Kd],
                    [config_ll['turn_p'], config_ll['turn_i'], config_ll['turn_d']]):
                logger.warning("PID Control Values not set correctly")
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
    def _setMaxWheelSpeed_LL(self, speed: (int, float)):
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
        self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_BALANCING_INPUT,
            data=data,
            input_type=bilbo_control_balancing_input_t
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
        self.external_input.velocity.forward = 0.0
        self.external_input.velocity.turn = 0.0
        self.external_input.balancing.u_left = 0.0
        self.external_input.balancing.u_right = 0.0
        self.external_input.direct.u_left = 0.0
        self.external_input.direct.u_right = 0.0

    # ------------------------------------------------------------------------------------------------------------------
    def _updateFromLowLevelSample(self, sample: BILBO_LL_Sample):
        """
        Update the internal state based on the latest low-level sample from the STM32 module.

        This method updates both the control status and mode by comparing the sample with the current state.

        Args:
            sample (BILBO_LL_Sample): The received low-level control sample.
        """
        # Update low-level status from sample and check for errors
        status_ll = BILBO_Control_Status_LL(sample.control.status)
        if status_ll is not self.status_ll:
            if status_ll == BILBO_Control_Status_LL.ERROR:
                logger.error("Error in the LL Control Module")
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
        if mode_ll is not self.mode_ll:
            logger.info(f"LL control mode changed to {mode_ll.name}")
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

        # Note: If the Python side uses different mode names than the low-level, a mapping should be applied here.
        if mode != self.mode:
            self._resetExternalInput()
            self.callbacks.mode_change.call(mode, forced_change=True)
            logger.info(f"Control mode changed to {mode.name}")

        self.mode = mode

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
            control_input.direct = external_input.direct
        elif self.mode == BILBO_Control_Mode.BALANCING:
            control_input.balancing = external_input.balancing
        elif self.mode == BILBO_Control_Mode.VELOCITY:
            control_input.velocity = external_input.velocity

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
            self._setDirectInput_LL(input.direct.u_left, input.direct.u_right)
        elif self.mode == BILBO_Control_Mode.BALANCING:
            self._setBalancingInput_LL(input.balancing.u_left, input.balancing.u_right)
        elif self.mode == BILBO_Control_Mode.VELOCITY:
            self._setSpeedInput_LL(input.velocity.forward, input.velocity.turn)
