import copy
import ctypes
import math
import time

from matplotlib import pyplot as plt

from robot.bilbo import BILBO
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

    time.sleep(2)
    bilbo.control.enableVelocityIntegralControl(False)
    bilbo.control.setMode(BILBO_Control_Mode.BALANCING)

    time.sleep(6)

    # bilbo.control.setVelocityIntegralControlConfig(
    #     Ki=0.05,
    #     max_error=0.5,
    #     v_limit=0
    # )

    # bilbo.control.setVelocityIntegralControlConfig(
    #     Ki=0.1,
    #     max_error=0.25,
    #     v_limit=0.1
    # )

    bilbo.control.setVelocityIntegralControlConfig(
        Ki=0.3,
        max_error=0.1,
        v_limit=0.1
    )

    time.sleep(0.2)

    bilbo.board.beep()
    bilbo.control.enableVelocityIntegralControl(True)

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
