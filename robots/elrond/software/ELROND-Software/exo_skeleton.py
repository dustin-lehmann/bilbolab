import ctypes
import time

import drivers.lowlevel.stm32_addresses as addresses



from control_board.control_board import RobotControl_Board
from control_board.lowlevel_definitions import BILBO_GeneralAddresses, twipr_beep_struct
from drivers.communication.bilbo_communication import BILBO_Communication
from drivers.utilities.id import readID
from utils.logging_utils import setLoggerLevel, Logger

setLoggerLevel('wifi', 'ERROR')

logger = Logger('EXO_SKELETON')
logger.setLevel('DEBUG')


class Exo_Skeleton:

    comm : BILBO_Communication
    board : RobotControl_Board

    def __init__(self):
        id = readID()
        self.board = RobotControl_Board(device_class='robot', device_type='bilbo', device_revision='v3',
                                    device_id=id, device_name=id)

        self.comm = BILBO_Communication(board=self.board)

        self.board.init()
        self.comm.init()
        self.board.start()
        self.comm.start()

        '''self.comm.wifi.addCommand(identifier='ident',
                                  callback=self.sampleFunc,
                                  arguments=['agrument', 'list'],
                                  description='this is a sample callback for CLI')'''
        
    def beep(self, frequency: (str, float) = None, time_ms: int = 500, repeats: int = 1):
        if frequency is None:
            frequency = 500

        if isinstance(frequency, str):
            if frequency == 'low':
                frequency = 200
            elif frequency == 'medium':
                frequency = 600
            elif frequency == 'high':
                frequency = 900
            else:
                frequency = 500

        beep_data = {
            'frequency': frequency,
            'time': time_ms,
            'repeats': repeats
        }

        self.comm.serial.executeFunction(
            module=0x01,
            address=BILBO_GeneralAddresses.ADDRESS_FIRMWARE_BEEP,
            data=beep_data,
            input_type=twipr_beep_struct
        )

    
    # ------------------------------------------------------------------------------------------------------------------
    def exoStartMotor(self) -> int:
        success = self.comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.EXO_MotorAddresses.EXO_MOTOR_START,
            data=None,
            input_type=None,
            output_type=ctypes.c_uint8
        )

        if success == 0:
            logger.info(f"Start Motor Successfull {success}")

            #self.config.statefeedback.vic.enabled = enable
        else:
            logger.warning(f"Failed to Start Motor {success}")

        return success
    
    # ------------------------------------------------------------------------------------------------------------------
    def exoStopMotor(self) -> int:
        success = self.comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.EXO_MotorAddresses.EXO_MOTOR_STOP,
            data=None,
            input_type=None,
            output_type=ctypes.c_uint8
        )

        if success == 0:
            logger.info(f"Stop Motor Successfull {success}")

            #self.config.statefeedback.vic.enabled = enable
        else:
            logger.warning(f"Failed to Stop Motor {success}")

        return success
    
    # ------------------------------------------------------------------------------------------------------------------
    def exoSetTargetPosition(self, targetPosition : ctypes.c_float) -> int:
        success = self.comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.EXO_MotorAddresses.EXO_MOTOR_SET_TARGET_POSITION,
            data=targetPosition,
            input_type=ctypes.c_float,
            output_type=ctypes.c_uint8
        )

        if success == 0:
            logger.info(f"Set Target Position Successfull: {success}")

            #self.config.statefeedback.vic.enabled = enable
        else:
            logger.warning(f"Failed to Set Target Position: {success}")

        return success
    
     # ------------------------------------------------------------------------------------------------------------------
    def exoSetTargetVelocity(self, targetVelocity : ctypes.c_float) -> int:
        success = self.comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.EXO_MotorAddresses.EXO_MOTOR_SET_TARGET_VELOCITY,
            data=targetVelocity,
            input_type=ctypes.c_float,
            output_type=ctypes.c_uint8
        )

        if success == 0:
            logger.info(f"Set Target Velocity Successfull: {success}")

            #self.config.statefeedback.vic.enabled = enable
        else:
            logger.warning(f"Failed to Set Target Velocity: {success}")

        return success

    # ------------------------------------------------------------------------------------------------------------------
    def exoSetTorque(self, torque : ctypes.c_float) -> int:
        success = self.comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.EXO_MotorAddresses.EXO_MOTOR_SET_TORQUE,
            data=torque,
            input_type=ctypes.c_float,
            output_type=ctypes.c_uint8
        )

        if success == 0:
            logger.info(f"Set Torque Successfull {success}")

            #self.config.statefeedback.vic.enabled = enable
        else:
            logger.warning(f"Failed to Set Torque {success}")

        return success
    
    # ------------------------------------------------------------------------------------------------------------------
    def exoSetMode(self, mode : addresses.EXO_mab_motor_mode_t) -> int:

        success = self.comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.EXO_MotorAddresses.EXO_MOTOR_SET_MODE,
            data=ctypes.c_uint32(mode),
            input_type=ctypes.c_uint32,
            output_type=ctypes.c_uint8
        )

        if success == 0:
            logger.info(f"Set Mode Successfull {success}")

            #self.config.statefeedback.vic.enabled = enable
        else:
            logger.warning(f"Failed to Set Mode {success}")

        return success
    
    def exoSetImpedanceParams(self, kp, kd):
        
        success = self.comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.EXO_MotorAddresses.EXO_MOTOR_SET_IMPEDANCE_CONSTS,
            data=addresses.EXO_mab_motor_impedance_const_struct(kp, kd),
            input_type=ctypes.Structure,
            output_type=ctypes.c_uint8
        )

        if success == 0:
            logger.info(f"Set Impedance Parameters Successfull: {success}")

            #self.config.statefeedback.vic.enabled = enable
        else:
            logger.warning(f"Failed to Set Impedance Parameters: {success}")

        return success