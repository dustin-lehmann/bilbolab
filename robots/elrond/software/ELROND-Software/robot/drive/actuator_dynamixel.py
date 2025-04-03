import ctypes
import enum
from dataclasses import dataclass, fields

from numpy import unsignedinteger

from utils.ctypes_utils import STRUCTURE

from utils.logging_utils import Logger
from robot.communication.bilbo_communication import BILBO_Communication
import robot.lowlevel.stm32_addresses as addresses


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
class actuator_admissable_range:
    front_left_min: float = 0
    front_left_max: float = 80
    back_left_min: float = 0
    back_left_max: float = 80
    front_right_min: float = 0
    front_right_max: float = 80
    back_right_min: float = 0
    back_right_max: float = 80

@dataclass
class actuator_offsets:
    front_left: float = 14
    back_left: float = 14
    front_right: float = 14
    back_right: float = 14
    # height difference (mm) between absolute zero point
    # and initialization point, so that height 0 is driveable
    #height: float = 30

class ELROND_Dynamixel_Handler:
    comm: BILBO_Communication
    logger: Logger
    angles: actuator_angles
    ranges: actuator_admissable_range

    def __init__(self, comm: BILBO_Communication):
        self.comm = comm
        self.logger = Logger('actuators')
        self.logger.setLevel('INFO')

    def init(self) -> bool:
        success = self._checkMotors()

        return success

    def start(self):
        ...

    def initializeLegs(self):
        # move legs to a known position where the drive motors can spin
        angles = actuator_angles_input(14.2,14.2,14.2,14.2)
        self.moveLegs(angles)

    # def setPosition(self, position: int, motor_id: int = 254):
    #     if not (motor_id <= 252 or motor_id == 254):
    #         self.logger.info(f"Motor ID must be between 0 and 252 (single motor) or 254 (broadcast), but was {motor_id}")
    #     elif motor_id == 254:
    #         self._setPositionAll_LL(ctypes.c_uint32(position))
    #     else:
    #         position_config = dynamixel_position_single_motor_LL()
    #         position_config.motor_id = motor_id
    #         position_config.position = position
    #         self._setPositionSingle_LL(position_config)
    #         self.logger.info("set position to {}".format(position))

    def extendLegsStraight(self,height):

        # Check if the height is ok
        ...

        # Calculate the angles for the corresponding height
        ...

        # Set the angle legs
        self.moveLegs(...)

    def moveLegs(self, angles: actuator_angles_input):
        # Checking for admissible ranges
        if not self._check_angles(angles):
            raise ValueError("One or more angles are out of admissible range")
        # Check if all angles are the same
        # Call the function for the microcontroller
        if self._are_angles_equal(angles):
            self._setPositionAll_LL(ctypes.c_uint32(angles.front_left))
        else:
            self._setPositionAll_LL(ctypes.c_uint32(angles.front_left))
            self._setPositionAll_LL(ctypes.c_uint32(angles.back_left))
            self._setPositionAll_LL(ctypes.c_uint32(angles.front_right))
            self._setPositionAll_LL(ctypes.c_uint32(angles.back_right))




    def readPositions(self):
        ...

    def checkMotors(self) -> bool:
        return True


    def setTorque(self, torque_enable: bool ,motor_id: int = 254):
        if not (motor_id <= 252 or motor_id == 254):
            self.logger.info(f"Motor ID must be between 0 and 252 (single motor) or 254 (broadcast), but was {motor_id}")
        elif motor_id == 254:
            self._setTorqueAll_LL(ctypes.c_bool(torque_enable))
        else:
            self._setTorqueSingle_LL(dynamixel_bool_state_single_motor_LL(motor_id, torque_enable))

    ## helper functions

    def _are_angles_equal(self, angles: actuator_angles_input) -> bool:
        """Check if all angles are equal."""
        return (angles.front_left == angles.back_left == angles.front_right == angles.back_right)

    def _check_angles(self, angles: actuator_angles_input) -> bool:
        """Check if all angles are within their admissible ranges."""
        # Get the admissible ranges
        ranges = self.range

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