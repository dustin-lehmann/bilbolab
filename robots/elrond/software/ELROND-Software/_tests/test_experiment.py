import time

from robot.bilbo import BILBO
from robot.control.definitions import BILBO_Control_Mode
from robot.experiment.bilbo_experiment import BILBO_TrajectoryInput, BILBO_Trajectory

if __name__ == "__main__":
    bilbo = BILBO()
    bilbo.init()
    bilbo.start()

    time.sleep(2)
    inputs = {}
    for i in range(100):
        inputs[i] = BILBO_TrajectoryInput(step=i, left=0.5, right=0.7)

    trajectory = BILBO_Trajectory(
        id=14,
        name='Test',
        length=len(inputs),
        inputs=inputs,
        control_mode=BILBO_Control_Mode.BALANCING,
        control_mode_end=BILBO_Control_Mode.OFF,
    )

    bilbo.experiment_handler.setTrajectory(trajectory)

    while True:
        time.sleep(1)
