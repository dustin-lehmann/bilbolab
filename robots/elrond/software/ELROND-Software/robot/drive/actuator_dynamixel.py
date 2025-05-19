import ctypes
import enum
from dataclasses import dataclass
import numpy as np

from utils.ctypes_utils import STRUCTURE

from utils.logging_utils import Logger
from robot.communication.bilbo_communication import BILBO_Communication
import robot.lowlevel.stm32_addresses as addresses

class dynamixel_motor(enum.IntEnum):
    FRONT_LEFT = 0
    BACK_LEFT = 1
    FRONT_RIGHT = 2
    BACK_RIGHT = 3
    ALL_MOTORS = 4

@dataclass
class elrond_leg_params:
    # in mm
    l1 : float = 40.5     # distance between the motors
    l2 : float = 160    # length of the upper leg front
    l3 : float = 230    # length of the lower leg front
    l4 : float = 160    # length of upper leg back
    l5 : float = 230    # length of lower leg back

@STRUCTURE
class dynamixel_bool_state_single_motor_LL:
    FIELDS = {
        'motor_id': ctypes.c_uint8,
        'state': ctypes.c_bool,
    }

@STRUCTURE
class dynamixel_position_single_motor_LL:
    FIELDS = {
        'motor_id': ctypes.c_uint8,
        'position': ctypes.c_uint32,
    }

@dataclass
class actuator_angles:
    front_left: float = 0
    back_left: float = 0
    front_right: float = 0
    back_right: float = 0

@dataclass
class actuator_angles_input:
    front_left: float = 0
    back_left: float = 0
    front_right: float = 0
    back_right: float = 0

@dataclass
class actuator_admissible_range:
    front_left_min: float = 0
    front_left_max: float = 80
    back_left_min: float = 0
    back_left_max: float = 80
    front_right_min: float = 0
    front_right_max: float = 80
    back_right_min: float = 0
    back_right_max: float = 80
    height_min: float = 0 # in mm
    height_max: float = 230 # in mm

@dataclass
class actuator_offsets:
    front_left: float = 14
    back_left: float = 14
    front_right: float = 14
    back_right: float = 14
    # height difference (mm) between absolute zero point
    # and initialization point, so that height 0 is driveable
    height: float = 141

class ELROND_Dynamixel_Handler:
    comm: BILBO_Communication
    logger: Logger
    angles: actuator_angles
    ranges: actuator_admissible_range
    offsets: actuator_offsets

    def __init__(self, comm: BILBO_Communication):
        self.comm = comm
        self.logger = Logger('actuators')
        self.logger.setLevel('INFO')

        self.angles = actuator_angles()
        self.ranges = actuator_admissible_range()
        self.offsets = actuator_offsets()

    def init(self) -> bool:
        success = self.checkMotors()
        #self.initializeLegs()

        return success

    def start(self):
        ...

    def initializeLegs(self):
        # move legs to a known position where the drive motors can spin
        angles = actuator_angles_input(0,0,0,0)
        self.moveLegs(angles)

    def extendLegsStraight(self,height: float ):

        # Check if the height is ok
       if height < self.ranges.height_min or height > self.ranges.height_max:
           raise ValueError("Height is out of admissible range")

        # Calculate the angles for the corresponding height
       angles = self._calculate_angles(0,height + self.offsets.height)

        # Set the angle legs
       self.moveLegs(angles)

    def extendLegs2D(self, x_target:float, y_target:float):

        # Calculate the angles for the corresponding height
        angles = self._calculate_angles(x_target, y_target + self.offsets.height)

        # Set the angle legs
        self.moveLegs(angles)

    def extendLegsThetaHeight(self, theta: float, height: float):
        # Calculate the x and y coordinates for the corresponding height and theta
        x_target = height * np.sin(np.radians(theta))
        y_target = height * np.cos(np.radians(theta))
        #y_target = height

        # Move legs with the calculated coordinates
        print(f"Theta: {theta}, Height: {height}, X: {x_target}, Y: {y_target}")
        self.extendLegs2D(x_target, y_target)

    def moveLegs(self, angles: actuator_angles_input):
        """
        Move the legs to the specified angles.

        This function sets the positions of the legs based on the input angles. It first checks if
        the angles are within admissible ranges and if all angles are equal. Depending on these
        checks, it sets the torque and positions for the motors accordingly.

        Args:
            angles (actuator_angles_input): The desired angles for the front-left, back-left,
                                            front-right, and back-right motors.

        Raises:
            ValueError: If any of the angles are out of the admissible range.
        """
        # Checking if the angles are within admissible ranges
        if not self._check_angles(angles):
            raise ValueError("One or more angles are out of admissible range")

        # Check if all angles are equal
        if self._angles_equal(angles):
            # Set torque and position for all motors if angles are equal
            self.setTorque(True, dynamixel_motor.ALL_MOTORS)
            self._setPosition(angles.front_left + self.offsets.front_left, dynamixel_motor.ALL_MOTORS)
        else:
            # Set torque and position individually for each motor
            self.setTorque(True, dynamixel_motor.FRONT_LEFT)
            self._setPosition(angles.front_left + self.offsets.front_left, dynamixel_motor.FRONT_LEFT)

            self.setTorque(True, dynamixel_motor.BACK_LEFT)
            self._setPosition(angles.back_left + self.offsets.back_left, dynamixel_motor.BACK_LEFT)

            self.setTorque(True, dynamixel_motor.FRONT_RIGHT)
            self._setPosition(angles.front_right + self.offsets.front_right, dynamixel_motor.FRONT_RIGHT)

            self.setTorque(True, dynamixel_motor.BACK_RIGHT)
            self._setPosition(angles.back_right + self.offsets.back_right, dynamixel_motor.BACK_RIGHT)




    def readPositions(self):
        ...

    def checkMotors(self) -> bool:
        return True

    def setTorque(self, torque: bool, motor: dynamixel_motor):
        """Set the torque of a single motor or all motors to the given state."""
        if motor == dynamixel_motor.ALL_MOTORS:
            self._setTorqueAll_LL(torque)
        else:
            torque_config = dynamixel_bool_state_single_motor_LL(motor, torque)
            self._setTorqueSingle_LL(torque_config)

    def setLED(self, led_enable: bool, motor: dynamixel_motor):
        """Set the LED of a single motor or all motors to the given state."""
        if motor == dynamixel_motor.ALL_MOTORS:
            self._setLEDAll_LL(led_enable)
        else:
            led_config = dynamixel_bool_state_single_motor_LL(motor, led_enable)
            self._setLEDSingle_LL(led_config)

    def _setPosition(self, position: float, motor: dynamixel_motor):
        """Set the position of a single motor or all motors to the given state."""
        if position < 0:
            raise ValueError("Position cannot be negative")
        position_pulses = int(position/0.088)
        if motor == dynamixel_motor.ALL_MOTORS:
            self._setPositionAll_LL(ctypes.c_uint32(position_pulses))
        else:
            position_config = dynamixel_position_single_motor_LL(motor, ctypes.c_uint32(position_pulses))
            self._setPositionSingle_LL(position_config)

    ## helper functions

    def _angles_equal(self, angles: actuator_angles_input) -> bool:
        """Check if all angles are equal."""
        return (angles.front_left == angles.back_left == angles.front_right == angles.back_right)

    def _check_angles(self, angles: actuator_angles_input) -> bool:
        """Check if all angles are within their admissible ranges."""
        # Get the admissible ranges
        ranges = self.ranges

        # Check each angle against its range
        if not (ranges.front_left_min <= angles.front_left <= ranges.front_left_max):
            return False
        if not (ranges.back_left_min <= angles.back_left <= ranges.back_left_max):
            return False
        if not (ranges.front_right_min <= angles.front_right <= ranges.front_right_max):
            return False
        if not (ranges.back_right_min <= angles.back_right <= ranges.back_right_max):
            return False

        return True

    def _calculate_angles(self, x_target: float, y_target: float) -> actuator_angles_input:
        """
            Solves the inverse kinematics for a five-bar linkage with origin at midpoint.
            Returns the base joint angles (θ1, θ3) and intermediate angles (θ2, θ4).
            """
        # Shift target to original frame (A0 at (0,0), B0 at (d,0))
        x = x_target + elrond_leg_params.l1 / 2
        y = y_target

        # First chain (A0 -> P)
        r_sq = x ** 2 + y ** 2
        cos_theta2 = (r_sq - elrond_leg_params.l2 ** 2 - elrond_leg_params.l3 ** 2) / (2 * elrond_leg_params.l2 * elrond_leg_params.l3)

        if abs(cos_theta2) > 1:
            raise ValueError("Target position not reachable by the first chain.")

        theta2 = -np.arccos(cos_theta2)  # Elbow-up solution

        # Calculate θ1
        alpha = np.arctan2(y, x)
        beta = np.arctan2(elrond_leg_params.l3 * np.sin(theta2), elrond_leg_params.l2 + elrond_leg_params.l3 * np.cos(theta2))
        theta1 = alpha - beta

        # Second chain (B0 -> P)
        r_prime_sq = (x - elrond_leg_params.l1) ** 2 + y ** 2
        cos_theta4 = (r_prime_sq - elrond_leg_params.l4 ** 2 - elrond_leg_params.l5 ** 2) / (2 * elrond_leg_params.l4 * elrond_leg_params.l5)

        if abs(cos_theta4) > 1:
            raise ValueError("Target position not reachable by the second chain.")

        theta4 = np.arccos(cos_theta4)  # Elbow-up solution

        # Calculate θ3
        alpha_prime = np.arctan2(y, x - elrond_leg_params.l1)
        beta_prime = np.arctan2(elrond_leg_params.l5 * np.sin(theta4), elrond_leg_params.l4 + elrond_leg_params.l5 * np.cos(theta4))
        theta3 = alpha_prime - beta_prime

        theta1_deg = 180 - np.degrees(theta1)
        theta3_deg = np.degrees(theta3)
        angles_out = actuator_angles_input(theta3_deg,theta1_deg,theta3_deg,theta1_deg)
        print("Theta 1: ", theta1_deg, "Theta 3: ", theta3_deg)
        return angles_out

    # direct mirrors of the lowlevel functions
    def _setTorqueSingle_LL(self, torque_config: dynamixel_bool_state_single_motor_LL) -> None:
        self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                         address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATOR_SET_TORQUE_SINGLE,
                                         data= torque_config,
                                         input_type= dynamixel_bool_state_single_motor_LL,  # type: Ignore
                                         output_type=None)

    def _sendPingSingle_LL(self, motor_id: int) -> None:
        self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                         address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATOR_SEND_PING_SINGLE,
                                         data= ctypes.c_uint8(motor_id),
                                         input_type= ctypes.c_uint8,
                                         output_type=None)

    def _setLEDSingle_LL(self, led_config: dynamixel_bool_state_single_motor_LL) -> None:
        self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                         address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATOR_SET_LED_SINGLE,
                                         data= led_config,
                                         input_type= dynamixel_bool_state_single_motor_LL,
                                         output_type=None)

    def _setPositionSingle_LL(self, position_config: dynamixel_position_single_motor_LL) -> None:
        self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                         address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATOR_SET_POSITION_SINGLE,
                                         data= position_config,
                                         input_type= dynamixel_position_single_motor_LL,
                                         output_type=None)

    def _getVoltageSingle_LL(self, motor_id: int) -> float:
        return self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                                address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATOR_GET_VOLTAGE_SINGLE,
                                                data= ctypes.c_uint8(motor_id),
                                                input_type= ctypes.c_uint8,
                                                output_type=ctypes.c_float)

    def _getTemperatureSingle_LL(self, motor_id: int) -> float:
        return self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                                address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATOR_GET_TEMPERATURE_SINGLE,
                                                data= ctypes.c_uint8(motor_id),
                                                input_type= ctypes.c_uint8,
                                                output_type=ctypes.c_float)

    def _getGoalPositionSingle_LL(self, motor_id: int) -> int:
        return self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                                address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATORS_GET_GOAL_POSITION_SINGLE,
                                                data= ctypes.c_uint8(motor_id),
                                                input_type= ctypes.c_uint8,
                                                output_type=ctypes.c_uint32)

    def _getPresentPositionSingle_LL(self, motor_id: int) -> int:
        return self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                                address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATORS_GET_PRESENT_POSITION_SINGLE,
                                                data= ctypes.c_uint8(motor_id),
                                                input_type= ctypes.c_uint8,
                                                output_type=ctypes.c_uint32)

    # ALL Motors Functions

    def _setTorqueAll_LL(self, torque_enable: bool) -> None:
        self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                         address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATORS_SET_TORQUE_ALL,
                                         data= ctypes.c_bool(torque_enable),
                                         input_type= ctypes.c_bool,
                                         output_type=None)

    def _setLEDAll_LL(self, led_enable: bool) -> None:
        self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                         address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATORS_SET_LED_ALL,
                                         data= ctypes.c_bool(led_enable),
                                         input_type= ctypes.c_bool,
                                         output_type=None)

    def _setPositionAll_LL(self, position: ctypes.c_uint32) -> None:
        self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
                                         address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATORS_SET_POSITION_ALL,
                                         data= position,
                                         input_type= ctypes.c_uint32)

    #def _getVoltageAll_LL(self) -> float:
    #    return self.comm.serial.executeFunction(module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
    #                                            address=addresses.TWIPR_ActuatorAddresses.ADDRESS_ACTUATORS_GET_VOLTAGE_ALL,
    #                                            data= None,
    #                                            input_type= None,
    #                                            output_type=ctypes.c_float)