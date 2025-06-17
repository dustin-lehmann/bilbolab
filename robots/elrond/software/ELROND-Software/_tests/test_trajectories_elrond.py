#import copy
#import ctypes
#import math
import time
import numpy as np
import matplotlib.pyplot as plt
#import addcopyfighandler
import pickle
import glob
import os
from datetime import datetime

from robot.elrond import BILBO
#from robot.communication.serial.bilbo_serial_messages import BILBO_Debug_Message, BILBO_Sequencer_Event_Message
from robot.control.definitions import BILBO_Control_Mode
from robot.experiment.bilbo_experiment import BILBO_Trajectory, BILBO_TrajectoryInput
from robot.lowlevel.stm32_general import MAX_STEPS_TRAJECTORY, LOOP_TIME_CONTROL
from robot.control.config import load_config
#from robot.lowlevel.stm32_sample import BILBO_LL_Sample
from utils.logging_utils import setLoggerLevel, Logger
#from utils.teleplot import sendValue
#from utils.time import PerformanceTimer

setLoggerLevel('wifi', 'ERROR')

logger = Logger('main')
logger.setLevel('DEBUG')

start_tick_elrond_experiments = None
end_tick_elrond_experiments = None

def elrond_experiment_test_trajectory(elrond:BILBO):
    time.sleep(0.5)
    elrond.board.beep(2000, 200, 2)
    time.sleep(0.5)
    repetitions = 2
    random_trajectory = False

    if random_trajectory:
        name = '1_random_trajectory'
        trajectory_time = 4
        trajectory: BILBO_Trajectory = elrond.experiment_handler.generateTestTrajectory(id=1,
                                                                                   time=trajectory_time,
                                                                                   frequency=3,
                                                                                   gain=0.4)
    else:
        name = '4_step_theta'
        trajectory_time = 8
        trajectory: BILBO_Trajectory = stepTrajectory(trajectory_time,1,3,-0.4,name)

    logger.info(f"Running experiment: {name} , repetitions={repetitions}, time={trajectory_time}")
    outputs = {}
    data = {}

    for i in range(0, repetitions):
        trajectory.id = i+1
        data = elrond.experiment_handler.runTrajectory(trajectory,
                                                     signals=define_signals())

        convert_data(data, outputs)
        elrond.board.beep()
        time.sleep(0.5)

        # save the data
        save_trajectory_outputs(outputs, f"{name}{i}")

def startManualExperimentButton(elrond: BILBO):
    global start_tick_elrond_experiments
    global end_tick_elrond_experiments

    if start_tick_elrond_experiments is None and end_tick_elrond_experiments is None:
        time.sleep(0.5)
        elrond.board.beep(1000, 300, 1)
        time.sleep(0.6)
        elrond.board.beep(2000, 300, 1)
        start_tick_elrond_experiments = elrond.tick
    else:
        logger.warning("Experiment already running or end index recorded")


def stopManualExperimentButton(elrond: BILBO):
    global start_tick_elrond_experiments
    global end_tick_elrond_experiments

    name_experiment = ("5_standup_theta")
    signals = define_signals()

    if start_tick_elrond_experiments is not None and end_tick_elrond_experiments is None:
        end_tick_elrond_experiments = elrond.tick
        time.sleep(0.5)
        elrond.board.beep(2000, 300, 1)
        time.sleep(0.6)
        elrond.board.beep(1000, 300, 1)

        if end_tick_elrond_experiments > start_tick_elrond_experiments:
            outputs = {}
            data = {'output': elrond.logging.getData(
                index_start=start_tick_elrond_experiments,
                index_end=end_tick_elrond_experiments,
                signals=signals)}

            convert_data(data, outputs)

            # Plot the outputs
            #plot_trajectory_outputs(outputs)
            # save the data
            save_trajectory_outputs(outputs, name_experiment)

            end_tick_elrond_experiments = None
            start_tick_elrond_experiments = None

        else:
            logger.warning("Start index bigger or same as end index")
            end_tick_elrond_experiments = None
            start_tick_elrond_experiments = None
    else:
        logger.warning("No start index recorded or internal error")

def stepTrajectory(time_total,time_before, step_time, step_value,name='Step_trajectory'):
    trajectory_input = {}
    total_steps = int (time_total/LOOP_TIME_CONTROL)
    for i in range(0, total_steps):
        if i < time_before/LOOP_TIME_CONTROL:
            trajectory_input[i] = BILBO_TrajectoryInput(
                step=i,
                left=0.0,
                right=0.0
            )
        elif i < (time_before+step_time)/LOOP_TIME_CONTROL:
            trajectory_input[i] = BILBO_TrajectoryInput(
                step=i,
                left=step_value,
                right=step_value
            )
        else:
            trajectory_input[i] = BILBO_TrajectoryInput(
                step=i,
                left=0.0,
                right=0.0
            )

    trajectory = BILBO_Trajectory(
        id=1,
        name=name,
        length=len(trajectory_input),
        inputs=trajectory_input,
        control_mode=BILBO_Control_Mode.BALANCING,
        control_mode_end=BILBO_Control_Mode.BALANCING,
    )
    return trajectory

def plot_trajectory_grid(outputs):
    """
    Plot the trajectory outputs in a grid layout with states vs u_external and states vs u_input/u_output.

    Args:
        outputs: dict containing the trajectory data with keys for states and control inputs
    """
    # Define the states to plot
    states = ['v', 'theta', 'theta_dot', 'psi_dot']

    # Create a figure with 4x2 subplots (4 states, 2 columns)
    fig, axs = plt.subplots(4, 2, figsize=(15, 20),dpi=300)
    fig.suptitle('Trajectory States Analysis', fontsize=16)

    # First column: States vs u_external
    for i, state in enumerate(states):
        axs[i, 0].plot(outputs[state], label=state, color='blue')
        axs[i, 0].plot(outputs['u_balancing'], label='u_external', color='red', linestyle=(0, (3,1)))
        axs[i, 0].set_xlabel('Sample Number')
        axs[i, 0].set_ylabel(f'{state}')
        axs[i, 0].set_title(f'{state} vs u_external')
        axs[i, 0].grid(True, alpha=0.3)
        axs[i, 0].legend()

    # Second column: States vs u_input/u_output
    for i, state in enumerate(states):
        axs[i, 1].plot(outputs[state], label=state, color='blue')
        axs[i, 1].plot(outputs['u_input'], label='u_input', color='red', linestyle=(2, (3,1)))
        axs[i, 1].plot(outputs['u_output'], label='u_output', color='green', linestyle=(0, (3,1)))
        axs[i, 1].set_xlabel('Sample Number')
        axs[i, 1].set_ylabel(f'{state}')
        axs[i, 1].set_title(f'{state} vs u_input/u_output')
        axs[i, 1].grid(True, alpha=0.3)
        axs[i, 1].legend()

    plt.tight_layout()
    plt.show()


def get_data_directory():
    """
    Returns the path to the data directory.
    Creates the directory if it doesn't exist.
    """
    # Get the current script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Define data directory path (you can modify this path as needed)
    data_dir = os.path.join(script_dir, '/home/admin/robot/experiments/trajectory_data')

    # Create the directory if it doesn't exist
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"Created data directory at: {data_dir}")

    return data_dir
def save_trajectory_outputs(outputs, experiment_name):
    """
    Save the trajectory outputs to a pickle file with timestamp and experiment name.

    Args:
        outputs (dict): Dictionary containing the trajectory data
        experiment_name (str): Name of the experiment
    """
    timestamp_now = datetime.now().strftime('%Y%m%d_%H%M%S')

    control_config = load_config('default')

    # Create data dictionary with all required information
    save_data = {
        'data': outputs,
        'timestamp': timestamp_now,
        'experiment_name': experiment_name,
        'control_config': control_config
    }

    # Get data directory
    data_dir = get_data_directory()

    # Create filename with timestamp first
    timestamp_str = timestamp_now
    filename = f'{timestamp_str}_{experiment_name}_trajectory_data.pkl'
    file_path = os.path.join(data_dir, filename)

    # Save to pickle file
    with open(file_path, 'wb') as f:
        pickle.dump(save_data, f)

    logger.info(f"Data saved to {file_path}")


def plot_saved_trajectory(filename):
    """
    Load and plot trajectory data from a pickle file using the plot_trajectory_grid function.

    Args:
        filename (str): Name of the pickle file containing trajectory data
    """
    try:
        # Get full path to the file
        data_dir = get_data_directory()
        file_path = os.path.join(data_dir, filename)

        # Load the pickle file
        with open(file_path, 'rb') as f:
            saved_data = pickle.load(f)

        # Extract the trajectory data
        outputs = saved_data['data']
        experiment_name = saved_data['experiment_name']
        timestamp = saved_data['timestamp']

        # Print experiment information
        print(f"Plotting experiment: {experiment_name}")
        print(f"Recorded at: {timestamp}")
        print(f"Data loaded from: {file_path}")

        # Plot the data using the grid plotting function
        plot_trajectory_grid(outputs)

    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
    except Exception as e:
        print(f"Error loading or plotting data: {str(e)}")


def plot_latest_trajectory(experiment_name=None):
    """
    Find and plot the most recent trajectory data file for a given experiment name.
    If no experiment name is provided, plots the most recent trajectory file.

    Args:
        experiment_name (str, optional): Name of the experiment to search for
    """
    try:
        # Get data directory
        data_dir = get_data_directory()

        # List all trajectory data files
        search_pattern = os.path.join(data_dir, '*trajectory_data*.pkl')
        trajectory_files = glob.glob(search_pattern)

        if not trajectory_files:
            print(f"No trajectory data files found in {data_dir}")
            return

        # Filter by experiment name if provided
        if experiment_name:
            matching_files = [f for f in trajectory_files if experiment_name in f]
            if not matching_files:
                print(f"No trajectory files found for experiment: {experiment_name}")
                print(f"Search directory: {data_dir}")
                return
            trajectory_files = matching_files

        # Get the most recent file
        latest_file = max(trajectory_files, key=os.path.getctime)

        # Get just the filename without the path
        filename = os.path.basename(latest_file)

        # Plot the data
        plot_saved_trajectory(filename)

    except Exception as e:
        print(f"Error finding or plotting latest trajectory: {str(e)}")

def define_signals():
    signals = ['lowlevel.estimation.state.v',
               'lowlevel.estimation.state.theta',
               'lowlevel.estimation.state.theta_dot',
               'lowlevel.estimation.state.psi_dot',
               'lowlevel.sensors.speed_left',
               'lowlevel.sensors.speed_right',
               'lowlevel.control.external_input.u_balancing_1',
               'lowlevel.control.external_input.u_balancing_2',
               'lowlevel.control.data.input_left',
               'lowlevel.control.data.input_right',
               'lowlevel.control.data.output_left',
               'lowlevel.control.data.output_right']
    return signals


def convert_data(data, outputs):
    outputs['v'] = np.asarray(data['output']['lowlevel.estimation.state.v'])
    outputs['theta'] = np.asarray(data['output']['lowlevel.estimation.state.theta'])
    outputs['theta_dot'] = np.asarray(data['output']['lowlevel.estimation.state.theta_dot'])
    outputs['psi_dot'] = np.asarray(data['output']['lowlevel.estimation.state.psi_dot'])
    outputs['speed_left'] = np.asarray(data['output']['lowlevel.sensors.speed_left'])
    outputs['speed_right'] = np.asarray(data['output']['lowlevel.sensors.speed_right'])

    outputs['u_balancing_1'] = np.asarray(data['output']['lowlevel.control.external_input.u_balancing_1'])
    outputs['u_balancing_2'] = np.asarray(data['output']['lowlevel.control.external_input.u_balancing_2'])
    outputs['u_input_left'] = np.asarray(data['output']['lowlevel.control.data.input_left'])
    outputs['u_input_right'] = np.asarray(data['output']['lowlevel.control.data.input_right'])
    outputs['u_output_left'] = np.asarray(data['output']['lowlevel.control.data.output_left'])
    outputs['u_output_right'] = np.asarray(data['output']['lowlevel.control.data.output_right'])

    outputs['u_balancing'] = (np.asarray(data['output']['lowlevel.control.external_input.u_balancing_1'])
                              + np.asarray(data['output']['lowlevel.control.external_input.u_balancing_2'])) / 2

    outputs['u_input'] = (np.asarray(data['output']['lowlevel.control.data.input_left'])
                          + np.asarray(data['output']['lowlevel.control.data.input_right'])) / 2

    outputs['u_output'] = (np.asarray(data['output']['lowlevel.control.data.output_left']
                                      + np.asarray(data['output']['lowlevel.control.data.output_right'])) / 2)

if __name__ == '__main__':
    plot_latest_trajectory()
    #plot_saved_trajectory("20250616_134655_3_standup_theta_trajectory_data.pkl")