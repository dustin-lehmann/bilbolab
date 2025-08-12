import sys

from dynamixel_sdk import PortHandler, PacketHandler, DXL_MAKEDWORD, DXL_MAKEWORD, COMM_SUCCESS
import logging
import json
import atexit
from time import sleep


# Protocol version
PROTOCOL_VERSION = 2.0  # See which protocol version is used in the Dynamixel



def create_logger(name, level = logging.ERROR):
    # print('this is the level:', level)
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Add a StreamHandler if not already added
    if not logger.handlers:
        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_handler.setLevel(level)

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)
    return logger

def read_control_table():
    # Load the JSON file for the control table
    with open("DYNAMIXEL_XL330_ControlTable.json", "r") as file:
        control_table_list = json.load(file)

    # Convert the list into a dictionary with "Name" as the key
    control_table = {entry["Name"]: entry for entry in control_table_list}
    return control_table

def convert_operating_mode(initial_value):
    operating_modes = {
        "current": 0,
        "velocity": 1,
        "position": 3,
        "extended_position": 4,
        "current_based_position": 5,
        "PWM": 16
    }

    # Build the reverse mapping on the fly
    operating_modes_reverse = {value: key for key, value in operating_modes.items()}

    if isinstance(initial_value, str):
        mode_converted = operating_modes[initial_value]
        return mode_converted
    elif isinstance(initial_value, int):
        mode_converted = operating_modes_reverse[initial_value]
        return mode_converted
    else:
        raise TypeError("Input value for operating mode conversion must be str or int")



class XL330Motor:
    control_table: dict = None
    dxl_id: int = None
    device_name: str = None
    baud_rate: int = None

    def __init__(self, dxl_id = 1, baudrate = 57600, device_name='COM3'):
        self.dxl_id = dxl_id
        self.baudrate = baudrate
        self.name = f'XL300Motor-ID{self.dxl_id}'
        self.device_name = device_name # e.g. Windows: "COM1"   Linux: "/dev/ttyUSB0" Mac: "/dev/tty.usbserial-*"
        self.control_table = read_control_table() # get the control table from the .json file
        self.logger = create_logger(name = self.name, level = logging.DEBUG) # get logger to log debug and error messages
        self.portHandler =  PortHandler(device_name)
        self.open_port()

        self.packetHandler = PacketHandler(PROTOCOL_VERSION)

    def open_port(self):
        if self.portHandler.is_open:
            self.logger.warning(f"Tried to open port, but port is already open, device name: {self.device_name}")
            return
        if self.portHandler.openPort():
            self.logger.debug(f"Succeeded to open the port, device name: {self.device_name}")
        else:
            self.logger.error("Failed to open the port, terminating")
            quit()

        # Set port baudrate
        if self.portHandler.setBaudRate(self.baudrate):
            self.logger.debug(f'Succeeded to set the baudrate: {self.baudrate}')
        else:
            self.logger.error("Failed to change the baudrate, terminating")
            quit()

        atexit.register(self.close_port)

    def close_port(self):
        self.portHandler.closePort()
        self.logger.debug(f'closing the port')

    def reboot_motor(self):
        """
        Sends the reboot instruction to the motor. This resets its state without physically power cycling it.
        """
        try:
            result, error = self.packetHandler.reboot(self.portHandler, self.dxl_id)

            if result != COMM_SUCCESS:
                self.logger.error(f"{self.name}: Failed to reboot the motor. Result: {result}")
            elif error != 0:
                error_description = self.packetHandler.getRxPacketError(error)
                self.logger.error(f"{self.name}: Error during reboot: {error_description}")
            else:
                self.logger.info(f"{self.name}: Successfully rebooted the motor.")
        except Exception as e:
            self.logger.error(f"{self.name}: Exception occurred while rebooting: {e}")

    def interpret_hardware_error_status(self, error_flags):
        """
        Interprets the hardware error status into human-readable descriptions.
        :param error_flags: A list of True/False values representing the status of each bit.
        :return: A dictionary mapping error descriptions to their active/inactive states.
        """
        # Map bit indices to error descriptions
        error_descriptions = {
            0: "Input Voltage Error",
            1: "Unused",
            2: "Overheating Error",
            3: "Unused",
            4: "Electrical Shock Error",
            5: "Overload Error",
            6: "Unused",
            7: "Unused"
        }

        # Create a dictionary with descriptions and their status
        interpreted_status = {desc: error_flags[bit] for bit, desc in error_descriptions.items()}

        self.logger.debug(f"{self.name}: Interpreted Hardware Error Status: {interpreted_status}")
        return interpreted_status

    # ------------------------------- setter ----------------------------------------

    def set_value(self, param_name, value):
        """
        Set the value of a parameter based on its byte size.
        Checks hardware error status before attempting to write.
        Logs errors if any are detected and skips further actions.
        """
        area, torque_was_enabled = [None, None]  # Default value to avoid uninitialized reference in `finally`
        # todo: Remove the many loggings of the erorr, introduce verbose param into the setter getters to not log everyhting all the time
        try:
            # Step 1: Check hardware error status
            raw_error_flags = self.get_hardware_error_status()
            if any(raw_error_flags):  # Only log if there are active errors
                interpreted_errors = self.interpret_hardware_error_status(raw_error_flags)
                self.logger.error(f"{self.name}: Hardware Error Detected: {interpreted_errors}")
                return  # Skip further actions if errors are present

            # Step 2: Get parameter information
            try:
                param_info = self.control_table[param_name]
            except KeyError:
                raise KeyError(f"{self.name}: Parameter {param_name} not found in control table!")

            min_val, max_val = param_info['Range']
            if not min_val <= value <= max_val:
                raise ValueError(f"{self.name}: Value {value} out of range for {param_name} [{min_val}, {max_val}]")

            address = param_info['Address']
            byte_size = param_info['ByteSize']
            area = param_info['Area']  # Set the area here

            # Step 3: Handle EEPROM writes (disable torque if needed)
            torque_was_enabled = False
            if area == "EEPROM":
                torque_was_enabled = self.get_torque_enabled()
                if torque_was_enabled:
                    self.set_torque_enabled(False)

            # Step 4: Write the value
            if byte_size == 1:
                result, error = self.packetHandler.write1ByteTxRx(self.portHandler, self.dxl_id, address, value)
            elif byte_size == 2:
                result, error = self.packetHandler.write2ByteTxRx(self.portHandler, self.dxl_id, address, value)
            elif byte_size == 4:
                result, error = self.packetHandler.write4ByteTxRx(self.portHandler, self.dxl_id, address, value)
            else:
                raise ValueError(f"Unsupported byte size: {byte_size}")

            # Step 5: Check communication result
            if result != COMM_SUCCESS:
                self.logger.error(
                    f"{self.name}: Communication error when writing {value} to {param_name}. Result: {result}")
            elif error != 0:
                error_description = self.packetHandler.getRxPacketError(error)
                self.logger.error(
                    f"{self.name}: Hardware error when writing {value} to {param_name}. Error: {error_description}")
            else:
                self.logger.debug(f"{self.name}: Successfully wrote {value} to {param_name} (address {address})")

        except Exception as e:
            self.logger.error(f"{self.name}: Exception occurred while setting {param_name}: {e}")

        finally:
            # Step 6: Re-enable torque if it was previously enabled
            if area == "EEPROM" and 'torque_was_enabled' in locals() and torque_was_enabled:
                self.set_torque_enabled(True)

    def set_torque_enabled(self, enabled:bool):
        """
        enables/ disables torque of the motor. If torque enable is True, data in the EEPROM area will be locked
        :param enabled: Enable or disable motor torque
        :return:
        """
        address = "Torque Enable" # address
        self.set_value(address, enabled)

    def set_operating_mode(self, control_mode: int | str = None):
        if isinstance(control_mode, int):
            self.set_value('Operating Mode', control_mode)
        elif isinstance(control_mode, str): # translate str to int
            num_control_mode = convert_operating_mode(control_mode)
            self.set_value('Operating Mode', num_control_mode)

    def set_position_limits(self, position_limits: list = [0,4095]):
        self.set_value('Min Position Limit', position_limits[0])
        self.set_value('Max Position Limit', position_limits[1])

    def set_goal_position(self, goal_position):
        self.set_value('Goal Position', goal_position)

    def set_goal_current(self, goal_current):
        self.set_value('Goal Current', goal_current)

    def set_goal_velocity(self, goal_velocity):
        self.set_value('Goal Velocity', goal_velocity)

    def set_profile_velocity(self, velocity: int):
        """
        Set the profile velocity of the motor.
        :param velocity: Desired velocity in pulses per second (within the allowed range).
        """
        self.set_value('Profile Velocity', velocity)

    def set_profile_acceleration(self, acceleration: int):
        """
        Set the profile acceleration of the motor.
        :param acceleration: Desired acceleration in pulses per second squared (within the allowed range).
        """
        self.set_value('Profile Acceleration', acceleration)

    # ------------------------------- getter ----------------------------------------

    def get_value(self, param_name) -> []:
        """
        Get the value of parameter "param_name"
        :param param_name: Name of parameter as specified in the control table .json
        :return:
        """
        try:
            param_information = self.control_table[param_name]
        except KeyError:
            raise(KeyError, f'{self.name}: Error, parameter: {param_name} is not defined in the control table json! Could not read parameter.')

        address = param_information['Address']
        length = param_information['ByteSize']
        data, result, error =  self.packetHandler.readTxRx(self.portHandler, self.dxl_id, address, length)

        if length == 1:
            data_read = data[0] if (result == COMM_SUCCESS) else 0

        elif length == 2:
            data_read = DXL_MAKEWORD(data[0], data[1]) if (result == COMM_SUCCESS) else 0

        elif length == 4:
            data_read = DXL_MAKEDWORD(DXL_MAKEWORD(data[0], data[1]),
                                      DXL_MAKEWORD(data[2], data[3])) if (result == COMM_SUCCESS) else 0
        else:
            raise(ValueError, f'{self.name}: Byte size: {length} of requested parameter: {param_name} not supported, check with control table.')

        if param_name == 'Operating Mode':
            self.logger.debug(f'read param {param_name}: {convert_operating_mode(data_read)}')
        else:
            self.logger.debug(f'read param {param_name}: {data_read}')

        return data_read, result, error

    def get_torque_enabled(self):
        return self.get_value('Torque Enable')[0]

    def get_operating_mode(self):
        num_value = self.get_value('Operating Mode')[0]
        str_value = convert_operating_mode(num_value)

        return str_value

    def get_position_limits(self)-> [int,int]:
        max_pos = self.get_value('Max Position Limit')
        min_pos = self.get_value('Min Position Limit')
        return max_pos, min_pos

    def get_present_position(self):
        current_position = self.get_value('Present Position')[0]
        return current_position

    def get_profile_velocity(self) -> int:
        """
        Get the current profile velocity of the motor.
        :return: The profile velocity in pulses per second.
        """
        velocity = self.get_value('Profile Velocity')[0]
        self.logger.debug(f"Profile Velocity: {velocity}")
        return velocity

    def get_profile_acceleration(self) -> int:
        """
        Get the current profile acceleration of the motor.
        :return: The profile acceleration in pulses per second squared.
        """
        acceleration = self.get_value('Profile Acceleration')[0]
        self.logger.debug(f"Profile Acceleration: {acceleration}")
        return acceleration

    def get_hardware_error_status(self):
        """
        Reads the hardware error status and returns a list of True/False values for each bit.
        :return: A list of 8 boolean values representing the status of each bit.
        """
        try:
            # Read the Hardware Error Status (1 byte at Address 70)
            error_status = self.get_value("Hardware Error Status")[0]

            # Convert the byte into a list of boolean values for each bit
            error_flags = [(error_status & (1 << bit)) != 0 for bit in range(8)]
            self.logger.debug(f"{self.name}: Raw Hardware Error Status: {error_flags}")
            return error_flags

        except Exception as e:
            self.logger.error(f"{self.name}: Exception occurred while reading hardware error status: {e}")
            return [False] * 8  # Return all False if there's an error


def example_position():

    motor.set_operating_mode('position')  # for other modes see convert_operating_mode function

    motor.set_torque_enabled(True)
    motor.get_torque_enabled()

    motor.get_operating_mode()
    motor.set_torque_enabled(True)

    motor.set_torque_enabled(True)
    motor.get_position_limits()

    motor.set_goal_position(1000)

def example_force():
    ...

if __name__ == "__main__":
    motor = XL330Motor()
    motor.reboot_motor()
    motor.set_position_limits([351, 1290])
    example_position()






