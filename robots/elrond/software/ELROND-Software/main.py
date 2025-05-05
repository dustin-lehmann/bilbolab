import copy
import ctypes
import math
import time

from robot.drive.actuator_dynamixel import dynamixel_motor
from robot.elrond import BILBO
from robot.communication.serial.bilbo_serial_messages import BILBO_Debug_Message, BILBO_Sequencer_Event_Message
from robot.control.definitions import BILBO_Control_Mode
from robot.lowlevel.stm32_sample import BILBO_LL_Sample
from utils.logging_utils import setLoggerLevel, Logger
from utils.time import PerformanceTimer

setLoggerLevel('wifi', 'ERROR')

logger = Logger('main')
logger.setLevel('DEBUG')


def main():
    bilbo = BILBO(reset_stm32=False)
    bilbo.init()
    bilbo.start()
    # bilbo.board.beep()
    #bilbo.actuator.setTorque(True, dynamixel_motor.ALL_MOTORS)
    #bilbo.actuator._setPosition(0, dynamixel_motor.ALL_MOTORS)
    # time.sleep(1)
    bilbo.actuator.initializeLegs()
    # time.sleep(2)
    bilbo.actuator.extendLegs2D(6, 10)

    # time.sleep(2)
    bilbo.board.beep(repeats=2)
    time.sleep(2)
    bilbo.control.setMode(BILBO_Control_Mode.BALANCING)
    # time.sleep(10)
    # bilbo.control.setMode(BILBO_Control_Mode.OFF)


    while True:
        time.sleep(3)
        #bilbo.actuator.extendLegs2D(-5, 10)
        #bilbo.board.beep()
        #bilbo.actuator.setPosition(40, dynamixel_motor.ALL_MOTORS)
        #bilbo.actuator.extendLegsStraight(150)
        #bilbo.actuator.extendLegs2D(100, 130)
        #time.sleep(4)
        #bilbo.actuator.extendLegs2D(-50, 60)
        #time.sleep(4)
        #bilbo.actuator.extendLegs2D(50, 60)
        #time.sleep(4)
        #bilbo.board.beep('high')
        #bilbo.actuator.setPosition(0, dynamixel_motor.ALL_MOTORS)
        #bilbo.actuator.extendLegsStraight(0)
        #bilbo.actuator.extendLegs2D(-100, 130)
        #time.sleep(4)
        #bilbo.actuator.extendLegs2D(-50, 60)
        time.sleep(2)



if __name__ == '__main__':
    main()
