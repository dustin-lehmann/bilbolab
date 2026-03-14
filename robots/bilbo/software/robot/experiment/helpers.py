from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from core.utils.data import generate_time_vector, generate_random_input
from robot.bilbo_definitions import BILBO_DynamicState
from robot.control.bilbo_control_definitions import BILBO_Control_Mode
from robot.lowlevel.stm32_general import LOOP_TIME_CONTROL, MAX_STEPS_TRAJECTORY, BILBO_CONTROL_DT


if TYPE_CHECKING:
    from robot.experiment.definitions import BILBO_InputTrajectoryStep, BILBO_InputTrajectory


# === TRAJECTORY =======================================================================================================
def generate_trajectory_inputs(inputs: list | np.ndarray, delta: float = 0.0) -> list[BILBO_InputTrajectoryStep]:
    from robot.experiment.definitions import BILBO_InputTrajectoryStep
    trajectory_inputs = []

    if isinstance(inputs, np.ndarray):
        inputs = inputs.tolist()

    for i, inp in enumerate(inputs):
        if isinstance(inp, list):
            left = float(inp[0])
            right = float(inp[1])
        else:
            left = float(inp) * (0.5 + delta)
            right = float(inp) * (0.5 - delta)

        trajectory_inputs.append(BILBO_InputTrajectoryStep(
            step=i,
            left=left,
            right=right,
        ))
    return trajectory_inputs


def trajectory_inputs_to_list(trajectory_inputs: list[BILBO_InputTrajectoryStep], single_input: bool = False) -> list:
    out = []
    for inp in trajectory_inputs:
        if not single_input:
            out.append([inp.left, inp.right])
        else:
            out.append(inp.left + inp.right)

    return out


def trajectory_inputs_to_vector(trajectory_inputs: list[BILBO_InputTrajectoryStep],
                                single_input: bool = False) -> np.ndarray:
    return np.array(trajectory_inputs_to_list(trajectory_inputs, single_input=single_input))


def generate_random_input_trajectory(trajectory_id, time_s, frequency, gain, bias=0.0) -> BILBO_InputTrajectory | None:
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
        BILBO_InputTrajectory | None: The trajectory object containing the generated data or None
        if the trajectory exceeds the maximum allowed steps.
    """
    t_vector = generate_time_vector(start=0, end=time_s, dt=BILBO_CONTROL_DT)

    if len(t_vector) > MAX_STEPS_TRAJECTORY:
        print(f"Trajectory too long: {len(t_vector)} > {MAX_STEPS_TRAJECTORY} steps")
        return None

    trajectory_input = generate_random_input(t_vector=t_vector, f_cutoff=frequency, sigma_I=gain, bias=bias)
    trajectory_inputs = generate_trajectory_inputs(trajectory_input)

    from robot.experiment.definitions import BILBO_InputTrajectory
    trajectory = BILBO_InputTrajectory(
        id=trajectory_id,
        name='test',
        dt=BILBO_CONTROL_DT,
        inputs=trajectory_inputs,
    )

    return trajectory


# ----------------------------------------------------------------------------------------------------------------------
def get_state_trajectory_from_lowlevel_samples(samples: dict) -> list[BILBO_DynamicState]:
    """
    Build a list of BILBO_DynamicState from flat-list logging samples.

    Expected keys (lists of equal length ideally):
      - 'lowlevel.estimation.state.v'
      - 'lowlevel.estimation.state.theta'
      - 'lowlevel.estimation.state.theta_dot'
      - 'lowlevel.estimation.state.psi'
      - 'lowlevel.estimation.state.psi_dot'

    Missing keys (or those explicitly set to None) are treated as zeros.
    If series have differing lengths, the longest length is used and shorter
    series are padded with zeros.
    """
    # Mapping from dataclass field -> logging key
    keymap = {
        "v": 'estimation.state.v',
        "theta": 'estimation.state.theta',
        "theta_dot": 'estimation.state.theta_dot',
        "psi": 'estimation.state.psi',  # psi_key from your prep is None -> leave default if missing
        "psi_dot": 'estimation.state.psi_dot',
        # x_key, y_key are intentionally None -> default to 0.0
        "x": None,
        "y": None,
    }

    # Pull series from samples; normalize to lists or None
    series: dict[str, list | None] = {}
    for field, key in keymap.items():
        if key is None:
            series[field] = None
        else:
            seq = samples.get(key, None)
            # Accept both list and tuple; otherwise treat as missing
            if isinstance(seq, (list, tuple)):
                series[field] = list(seq)
            else:
                series[field] = None

    # Determine trajectory length (use the longest available series)
    lengths = [len(seq) for seq in series.values() if isinstance(seq, list)]
    n = max(lengths) if lengths else 0
    if n == 0:
        return []

    def get_val(field: str, i: int) -> float:
        seq = series.get(field)
        if isinstance(seq, list) and i < len(seq):
            try:
                return float(seq[i])
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    traj: list[BILBO_DynamicState] = []
    for i in range(n):
        state = BILBO_DynamicState(
            x=get_val("x", i),  # will be 0.0 since key is None
            y=get_val("y", i),  # will be 0.0 since key is None
            v=get_val("v", i),
            theta=get_val("theta", i),
            theta_dot=get_val("theta_dot", i),
            psi=get_val("psi", i),  # 0.0 if key missing/None
            psi_dot=get_val("psi_dot", i),
        )
        traj.append(state)

    return traj
