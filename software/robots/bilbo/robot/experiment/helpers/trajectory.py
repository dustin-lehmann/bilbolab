from __future__ import annotations

import numpy as np

from core.utils.data import generate_time_vector, generate_random_input
from robots.bilbo.robot.bilbo_definitions import BILBO_CONTROL_DT, MAX_STEPS_TRAJECTORY
from robots.bilbo.robot.experiment.experiment_definitions import (
    InputTrajectory, InputTrajectoryStep,
)


# === TRAJECTORY =======================================================================================================
def generate_trajectory_inputs(inputs: list | np.ndarray) -> list[InputTrajectoryStep]:
    trajectory_inputs = []

    if isinstance(inputs, np.ndarray):
        inputs = inputs.tolist()

    for i, inp in enumerate(inputs):
        if isinstance(inp, list):
            left = float(inp[0])
            right = float(inp[1])
        else:
            left = float(inp) / 2
            right = float(inp) / 2

        trajectory_inputs.append(InputTrajectoryStep(
            step=i,
            left=left,
            right=right,
        ))
    return trajectory_inputs


def trajectory_inputs_to_list(trajectory_inputs: list[InputTrajectoryStep], single_input: bool = False) -> list:
    out = []
    for inp in trajectory_inputs:
        if not single_input:
            out.append([inp.left, inp.right])
        else:
            out.append(inp.left + inp.right)

    return out


def trajectory_inputs_to_vector(trajectory_inputs: list[InputTrajectoryStep],
                                single_input: bool = False) -> np.ndarray:
    return np.array(trajectory_inputs_to_list(trajectory_inputs, single_input=single_input))


def generate_random_input_trajectory(trajectory_id, time_s, frequency, gain, bias=0.0) -> InputTrajectory | None:
    """
    Generates a random test trajectory for simulation or testing purposes. The function creates a time
    vector based on the specified duration and generates random inputs filtered by a cutoff frequency
    and scaled by the provided gain. If the trajectory exceeds the maximum allowed steps, the function
    returns None. Otherwise, it returns a trajectory object containing the generated data.

    Args:
        trajectory_id: Identifier for the generated trajectory.
        time_s: Maximum time duration of the trajectory in seconds.
        frequency: Cutoff frequency for filtering random inputs.
        gain: Scaling factor for random input signal amplitude.
        bias: Constant offset added to the signal. Positive values bias the robot forward.

    Returns:
        InputTrajectory | None: The trajectory object containing the generated data or None
        if the trajectory exceeds the maximum allowed steps.
    """
    t_vector = generate_time_vector(start=0, end=time_s, dt=BILBO_CONTROL_DT)

    if len(t_vector) > MAX_STEPS_TRAJECTORY:
        print(f"Trajectory too long: {len(t_vector)} > {MAX_STEPS_TRAJECTORY} steps")
        return None

    trajectory_input = generate_random_input(t_vector=t_vector, f_cutoff=frequency, sigma_I=gain, bias=bias)
    trajectory_inputs = generate_trajectory_inputs(trajectory_input)

    trajectory = InputTrajectory(
        id=trajectory_id,
        name='test',
        dt=BILBO_CONTROL_DT,
        inputs=trajectory_inputs,
    )

    return trajectory


# === PLOTTING =========================================================================================================
def plot_input_trajectory(trajectory: InputTrajectory):
    ...
