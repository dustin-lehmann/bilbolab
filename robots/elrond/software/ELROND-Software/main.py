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
from robot.control.ElrondJoystick_Standalone import ElrondJoystick

setLoggerLevel('wifi', 'ERROR')

logger = Logger('main')
logger.setLevel('DEBUG')


def main():
    elrond = BILBO(reset_stm32=False)
    elrond.init()
    joystick_control = ElrondJoystick(elrond, logger)
    elrond.start()
    joystick_control.start()
    elrond.actuator.extendLegs2D(3, 10)

    time.sleep(3)
    elrond.board.beep(repeats=2)
    time.sleep(1)
    #elrond.control.setMode(BILBO_Control_Mode.BALANCING)
    #time.sleep(10)
    #elrond.control.setMode(BILBO_Control_Mode.OFF)


    while True:
        elrond.update()
        time.sleep(0.05)



if __name__ == '__main__':
    main()
