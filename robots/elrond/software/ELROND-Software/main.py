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
from utils.teleplot import sendValue
from utils.time import PerformanceTimer
from robot.control.ElrondJoystick_Standalone import ElrondJoystick

setLoggerLevel('wifi', 'ERROR')

logger = Logger('main')
logger.setLevel('DEBUG')


def main():
    elrond = BILBO(reset_stm32=False)
    elrond.init()

    def update_callback(*args, **kwargs):
        theta = elrond.logging.sample.lowlevel.estimation.state.theta
        #speed_left = elrond.logging.sample.lowlevel.sensors.speed_left
        #speed_right = elrond.logging.sample.lowlevel.sensors.speed_right
        v = elrond.logging.sample.lowlevel.estimation.state.v
        sendValue('theta', math.degrees(theta))
        #sendValue('speed_left', speed_left)
        #sendValue('speed_right', speed_right)
        sendValue('v', v)

    #elrond.callbacks.update.register(update_callback)
    #elrond.events.update.on(update_callback)

    joystick_control = ElrondJoystick(elrond, logger)
    elrond.start()
    joystick_control.start()
    #elrond.actuator.extendLegs2D(3, 10)
    #elrond.actuator.extendLegsThetaHeight(3,10)
    #time.sleep(3)
    elrond.actuator.extendLegsThetaHeight(2,5)


    time.sleep(3)
    elrond.board.beep(1500,400,2)


    while True:
        time.sleep(1)



if __name__ == '__main__':
    main()
