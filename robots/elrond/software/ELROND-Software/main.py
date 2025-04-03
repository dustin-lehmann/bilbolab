import copy
import ctypes
import math
import time

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

    time.sleep(2)

    while True:
        bilbo.board.beep()
        time.sleep(1)
        bilbo.board.beep('high')
        time.sleep(1)


if __name__ == '__main__':
    main()
