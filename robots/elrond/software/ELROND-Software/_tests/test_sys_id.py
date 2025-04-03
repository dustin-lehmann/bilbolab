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

    N = 5
    learning_inputs = []
    learning_outputs = []

    trajectory_time = 5

    for i in range(0, N):
        trajectory: BILBO_Trajectory = bilbo.experiment_handler.generateTestTrajectory(id=i+1, time=trajectory_time, frequency=3, gain=0.2)
        input = np.asarray([i.left + i.right for i in trajectory.inputs.values()])
        learning_inputs.append(input)
        data = bilbo.experiment_handler.runTrajectory(trajectory, signals='lowlevel.estimation.state.theta')

        learning_outputs.append(np.asarray(data['output']['lowlevel.estimation.state.theta']))
        bilbo.board.beep()
        time.sleep(8)


    verification_trajectory: BILBO_Trajectory = bilbo.experiment_handler.generateTestTrajectory(id=1, time=trajectory_time, frequency=3, gain=0.2)

    time.sleep(8)

    verification_input = np.asarray([i.left + i.right for i in verification_trajectory.inputs.values()])

    verification_data = bilbo.experiment_handler.runTrajectory(verification_trajectory, signals='lowlevel.estimation.state.theta')
    verification_output = np.asarray(verification_data['output']['lowlevel.estimation.state.theta'])

    h, P = estimate_system_and_lifted_matrix(learning_inputs, learning_outputs, len(learning_inputs[0]))


    verification_output_estimated = P@verification_input

    plt.plot(verification_output, label='True Output')
    plt.plot(verification_output_estimated, label='Estimated Output')
    plt.legend()
    plt.grid()
    plt.show()



    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
