import numpy as np
from matplotlib import pyplot as plt
from numpy import nan

from core.utils.colors import get_palette
from core.utils.data import generate_time_vector
from core.utils.plotting.plot import Plot, AxisConfig, Axis
from robots.bilbo.simulation.model import BILBO_Dynamics_3D, DEFAULT_BILBO_MODEL, BILBO_3D_State
from projects.Dissertation.settings import TESTBED_SIM_RESULTS_PATH

TS = 0.01

MODEL = DEFAULT_BILBO_MODEL
POLES = [0, -10, -5 + 3j, -5 - 3j, 0, -15]  # (x,v,theta, theta_dot, psi, psi_dot)
BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS = np.array([[1, nan, nan, nan, 0, nan],
                                                          [nan, 1, nan, nan, nan, nan],
                                                          [nan, nan, 1, 1, nan, 0],
                                                          [nan, nan, nan, nan, nan, nan],
                                                          [0, nan, nan, nan, 1, 1],
                                                          [nan, 0, 0, 0, nan, nan]])


def main():
    dynamics = BILBO_Dynamics_3D(Ts=TS, model=MODEL)
    dynamics.eigenstructureAssignment(poles=POLES,
                                      eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS)

    experiment_time = 30  # s
    time_vector = generate_time_vector(start=0, end=experiment_time, dt=TS)
    step_input = 0.5*np.ones((len(time_vector), 2))

    states, inputs = dynamics.simulate(
        input=step_input,
        include_zero_step=True,
        x0=BILBO_3D_State(
            x=0,
            y=0,
            v=0,
            theta=np.pi / 2,
            theta_dot=0,
            psi=0,
            psi_dot=0
        )
    )

    plt.plot(time_vector, [state.x for state in states][:-1])
    plt.show()


def compare_eigenstructure_assignment_poles_stand_up():
    poles_1 = [0, -10, -5 + 3j, -5 - 3j, 0, -15]
    poles_2 = [0, -10, -5 + 5j, -5 - 5j, 0, -15]
    poles_3 = [0, -10, -5 + 7j, -5 - 7j, 0, -15]

    poles = [poles_1, poles_2, poles_3]
    experiment_time = 2  # s
    time_vector = generate_time_vector(start=0, end=experiment_time, dt=TS)
    zero_input = np.zeros((len(time_vector), 2))

    output_states = []
    output_inputs = []

    for pole_set in poles:
        dynamics = BILBO_Dynamics_3D(Ts=TS, model=DEFAULT_BILBO_MODEL)
        dynamics.eigenstructureAssignment(poles=pole_set,
                                          eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS)

        states, inputs = dynamics.simulate(
            input=zero_input,
            include_zero_step=True,
            x0=BILBO_3D_State(
                x=0,
                y=0,
                v=0,
                theta=np.pi / 2,
                theta_dot=0,
                psi=0,
                psi_dot=0
            )
        )
        output_states.append(states)
        output_inputs.append(inputs)

    plot = Plot(rows=1,
                columns=3,
                size=(8, 3),
                use_agg_backend=True,
                facealpha=0,
                use_latex=False,
                font_family="Palatino")

    palette = get_palette('dark', 3)

    ax_cfg1 = AxisConfig(title="Pitch Angle $\\theta$",
                         xlabel="time [s]",
                         ylabel='$\\theta$ [rad]',
                         legend=True,
                         palette=palette,
                         xlim=(0, time_vector[-1]),
                         ylim=(-1, 1.6),
                         facecolor=(1, 0, 0, 0))

    axis1 = Axis(id="theta", config=ax_cfg1)
    plot.set_axis(1, 1, axis1)


    theta1 = [state.theta for state in output_states[0]]
    theta2 = [state.theta for state in output_states[1]]
    theta3 = [state.theta for state in output_states[2]]

    axis1.plot(time_vector, theta1[0:-1], label="Pole Set 1", color=palette[0])
    axis1.plot(time_vector, theta2[0:-1], label="Pole Set 2", color=palette[1])
    axis1.plot(time_vector, theta3[0:-1], label="Pole Set 3", color=palette[2])

    ax_cfg2 = AxisConfig(title="Input $\\mathbf{u}$",
                         xlabel="time [s]",
                         ylabel='$||\\mathbf{u}||_2$ [Nm]',
                         legend=True,
                         palette=palette,
                         xlim=(0, time_vector[-1]),
                         ylim=(-0.4, 0.8),
                         facecolor=(1, 0, 0, 0))

    axis2 = Axis(id="u", config=ax_cfg2)
    plot.set_axis(1, 3, axis2)

    input1 = [input[0] for input in output_inputs[0]]
    input2 = [input[0] for input in output_inputs[1]]
    input3 = [input[0] for input in output_inputs[2]]

    axis2.plot(time_vector, input1[0:-1], label="Pole Set 1", color=palette[0])
    axis2.plot(time_vector, input2[0:-1], label="Pole Set 2", color=palette[1])
    axis2.plot(time_vector, input3[0:-1], label="Pole Set 3", color=palette[2])

    # === VELOCITY ===
    velocity_axis_config = AxisConfig(title="Velocity $v$",
                                      xlabel="time [s]",
                                      ylabel='$v$ [m/s]',
                                      legend=True,
                                      palette=palette,
                                      xlim=(0, time_vector[-1]),
                                      ylim=(-0.5, 1),
                                      facecolor=(1, 0, 0, 0))
    velocity_axis = Axis(id="v", config=velocity_axis_config)
    plot.set_axis(1, 2, velocity_axis)

    v1 = [state.v for state in output_states[0]]
    v2 = [state.v for state in output_states[1]]
    v3 = [state.v for state in output_states[2]]
    velocity_axis.plot(time_vector, v1[0:-1], label="Pole Set 1", color=palette[0])
    velocity_axis.plot(time_vector, v2[0:-1], label="Pole Set 2", color=palette[1])
    velocity_axis.plot(time_vector, v3[0:-1], label="Pole Set 3", color=palette[2])


    plot.show_temp_pdf()
    plot.save(f"{TESTBED_SIM_RESULTS_PATH}/test_sim_results.pdf", 'pdf')

if __name__ == '__main__':
    main()
