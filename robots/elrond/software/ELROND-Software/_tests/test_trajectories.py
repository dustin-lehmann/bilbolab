import copy
import ctypes
import math
import time
import numpy as np
from matplotlib import pyplot as plt

from robot.bilbo import BILBO
from robot.communication.serial.bilbo_serial_messages import BILBO_Debug_Message, BILBO_Sequencer_Event_Message
from robot.control.definitions import BILBO_Control_Mode
from robot.experiment.bilbo_experiment import BILBO_Trajectory
from robot.lowlevel.stm32_sample import BILBO_LL_Sample
from sys_id import estimate_system_and_lifted_matrix
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


    bilbo.control.setMode(BILBO_Control_Mode.BALANCING)
    time.sleep(5)

    N = 2
    trajectory_time = 5
    trajectory: BILBO_Trajectory = bilbo.experiment_handler.generateTestTrajectory(id=1,
                                                                                   time=trajectory_time,
                                                                                   frequency=3,
                                                                                   gain=0.15)
    outputs = []


    for i in range(0, N):
        trajectory.id = i+1
        data = bilbo.experiment_handler.runTrajectory(trajectory, signals='lowlevel.estimation.state.theta')
        outputs.append(np.asarray(data['output']['lowlevel.estimation.state.theta']))
        bilbo.board.beep()
        time.sleep(5)

    # for i in range(N):
    #     plt.plot(outputs[i])
    # plt.legend()
    # plt.grid()
    # plt.show()



    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
