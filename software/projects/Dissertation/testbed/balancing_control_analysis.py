import numpy as np
from numpy import nan

from core.utils.colors import get_palette
from core.utils.data import generate_time_vector
from core.utils.plotting_utils import Plot, AxisConfig, LegendConfig, Axis
from extensions.simulation.src.objects.bilbo import BILBO_Dynamics_3D, DEFAULT_BILBO_MODEL, BILBO_3D_State
from projects.Dissertation.settings import TESTBED_SIM_RESULTS_PATH

TS = 0.01

MODEL = DEFAULT_BILBO_MODEL
# (x, v, theta, theta_dot, psi, psi_dot)
DEFAULT_POLES = [0, -10, -5 + 3j, -5 - 3j, 0, -15]

BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS = np.array([
    [1,   nan, nan, nan, 0,   nan],
    [nan, 1,   nan, nan, nan, nan],
    [nan, nan, 1,   1,   nan, 0  ],
    [nan, nan, nan, nan, nan, nan],
    [0,   nan, nan, nan, 1,   1  ],
    [nan, 0,   0,   0,   nan, nan]
])


# === 1) Standing up from theta = pi/2 =======================================

def compare_conjugate_pair_stand_up():
    """
    1.1) Influence of the conjugated pair for theta on balancing performance
         Standing up from theta = pi/2 (zero input).
    """
    # Vary imaginary part / real part of theta poles:
    poles_1 = [0, -10, -5 + 3j, -5 - 3j, 0, -15]
    poles_2 = [0, -10, -5 + 5j, -5 - 5j, 0, -15]
    poles_3 = [0, -10, -3 + 3j, -3 - 3j, 0, -15]

    pole_sets = [poles_1, poles_2, poles_3]
    labels = ["$\\lambda_{\\theta} = -5 \\pm 3i$",
              "$\\lambda_{\\theta} = -5 \\pm 5i$",
              "$\\lambda_{\\theta} = -3 \\pm 3i$"]

    experiment_time = 1.5  # s
    time_vector = generate_time_vector(start=0, end=experiment_time, dt=TS)

    # zero external input
    input_array = np.zeros((len(time_vector), 2))

    x0 = BILBO_3D_State(
        x=0,
        y=0,
        v=0,
        theta=np.pi / 2,
        theta_dot=0,
        psi=0,
        psi_dot=0
    )

    # Store signals for plotting
    theta_all = []
    v_all = []
    x_all = []
    u_norm_all = []

    for poles in pole_sets:
        dynamics = BILBO_Dynamics_3D(Ts=TS, model=MODEL)
        dynamics.eigenstructureAssignment(
            poles=poles,
            eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS
        )

        states, inputs = dynamics.simulate(
            input=input_array,
            include_zero_step=True,
            x0=x0
        )

        # Convert states and inputs to arrays
        theta = np.array([s.theta for s in states])
        v = np.array([s.v for s in states])
        x = np.array([s.x for s in states])

        u = np.array(inputs)                  # shape: (N or N+1, 2)
        u_norm = np.linalg.norm(u, axis=1)    # ||u||_2

        # Cut to match time_vector length
        theta_all.append(theta[:-1])
        v_all.append(v[:-1])
        x_all.append(x[:-1])
        u_norm_all.append(u_norm[:-1])

    # Plot: 2 x 2 → theta, v, x, ||u||
    plot = Plot(
        rows=2,
        columns=2,
        size=(10, 5),
        use_agg_backend=True,
        facealpha=0,
        use_latex=False,
        font_family="Palatino"
    )

    palette = get_palette('dark', len(pole_sets))

    # Theta
    theta_cfg = AxisConfig(
        title="Standing Up – Pitch Angle $\\theta$",
        xlabel=None,
        ylabel="$\\theta$ [rad]",
        legend=True,
        palette=palette,
        xlim=(0, time_vector[-1]),
        ylim=(-1, 1.7),
        facecolor=(1, 0, 0, 0)
    )
    theta_axis = Axis(id="theta", config=theta_cfg)
    plot.set_axis(1, 1, theta_axis)

    # Velocity v
    v_cfg = AxisConfig(
        title="Standing Up – Velocity $v$",
        xlabel=None,
        ylabel="$v$ [m/s]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        ylim=(-0.5, 1.0),
        facecolor=(1, 0, 0, 0)
    )
    v_axis = Axis(id="v", config=v_cfg)
    plot.set_axis(1, 2, v_axis)

    # Displacement x
    x_cfg = AxisConfig(
        title="Standing Up – Displacement $x$",
        xlabel="time [s]",
        ylabel="$x$ [m]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    x_axis = Axis(id="x", config=x_cfg)
    plot.set_axis(2, 1, x_axis)

    # Input ||u||
    u_cfg = AxisConfig(
        title="Standing Up – Input Norm $||\\mathbf{u}||_2$",
        xlabel="time [s]",
        ylabel="$||\\mathbf{u}||_2$ [Nm]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    u_axis = Axis(id="u1", config=u_cfg)
    plot.set_axis(2, 2, u_axis)

    t_states = time_vector

    for i, label in enumerate(labels):
        theta_axis.plot(t_states, theta_all[i], label=label, color=palette[i])
        v_axis.plot(t_states, v_all[i], label=label, color=palette[i])
        x_axis.plot(t_states, x_all[i], label=label, color=palette[i])
        u_axis.plot(t_states, u_norm_all[i], label=label, color=palette[i])

    plot.show_temp_pdf()
    plot.save(f"{TESTBED_SIM_RESULTS_PATH}/bilbo_standup_conjugate_pair_theta.pdf", 'pdf')


def compare_velocity_damping_stand_up():
    """
    1.2) Influence of the velocity damping (second pole) on balancing performance
         Standing up from theta = pi/2 (zero input).
    """
    # Vary v-pole (second pole), keep theta conjugate pair fixed
    poles_1 = [0, -5,  -5 + 5j, -5 - 5j, 0, -15]
    poles_2 = [0, -10, -5 + 5j, -5 - 5j, 0, -15]
    poles_3 = [0, -20, -5 + 5j, -5 - 5j, 0, -15]

    pole_sets = [poles_1, poles_2, poles_3]
    labels = ["$\\lambda_v = -5$", "$\\lambda_v = -10$", "$\\lambda_v = -20$"]

    experiment_time = 1.5  # s
    time_vector = generate_time_vector(start=0, end=experiment_time, dt=TS)

    input_array = np.zeros((len(time_vector), 2))

    x0 = BILBO_3D_State(
        x=0,
        y=0,
        v=0,
        theta=np.pi / 2,
        theta_dot=0,
        psi=0,
        psi_dot=0
    )

    theta_all = []
    v_all = []
    x_all = []
    u_norm_all = []

    for poles in pole_sets:
        dynamics = BILBO_Dynamics_3D(Ts=TS, model=MODEL)
        dynamics.eigenstructureAssignment(
            poles=poles,
            eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS
        )

        states, inputs = dynamics.simulate(
            input=input_array,
            include_zero_step=True,
            x0=x0
        )

        theta = np.array([s.theta for s in states])
        v = np.array([s.v for s in states])
        x = np.array([s.x for s in states])

        u = np.array(inputs)
        u_norm = np.linalg.norm(u, axis=1)

        theta_all.append(theta[:-1])
        v_all.append(v[:-1])
        x_all.append(x[:-1])
        u_norm_all.append(u_norm[:-1])

    plot = Plot(
        rows=2,
        columns=2,
        size=(10, 5),
        use_agg_backend=True,
        facealpha=0,
        use_latex=False,
        font_family="Palatino"
    )

    palette = get_palette('dark', len(pole_sets))

    # Theta
    theta_cfg = AxisConfig(
        title="Standing Up – Influence of Velocity Pole on $\\theta$",
        ylabel="$\\theta$ [rad]",
        legend=True,
        palette=palette,
        xlim=(0, time_vector[-1]),
        ylim=(-1, 1.7),
        facecolor=(1, 0, 0, 0)
    )
    theta_axis = Axis(id="theta_vd", config=theta_cfg)
    plot.set_axis(1, 1, theta_axis)

    # Velocity v
    v_cfg = AxisConfig(
        title="Standing Up – Velocity $v$",
        ylabel="$v$ [m/s]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        ylim=(-0.5, 1.0),
        facecolor=(1, 0, 0, 0)
    )
    v_axis = Axis(id="v_vd", config=v_cfg)
    plot.set_axis(1, 2, v_axis)

    # Displacement x
    x_cfg = AxisConfig(
        title="Standing Up – Displacement $x$",
        xlabel="time [s]",
        ylabel="$x$ [m]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    x_axis = Axis(id="x_vd", config=x_cfg)
    plot.set_axis(2, 1, x_axis)

    # Input ||u||
    u_cfg = AxisConfig(
        title="Standing Up – Input Norm $||\\mathbf{u}||_2$",
        xlabel="time [s]",
        ylabel="$||\\mathbf{u}||_2$ [Nm]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    u_axis = Axis(id="u1_vd", config=u_cfg)
    plot.set_axis(2, 2, u_axis)

    t_states = time_vector

    for i, label in enumerate(labels):
        theta_axis.plot(t_states, theta_all[i], label=label, color=palette[i])
        v_axis.plot(t_states, v_all[i], label=label, color=palette[i])
        x_axis.plot(t_states, x_all[i], label=label, color=palette[i])
        u_axis.plot(t_states, u_norm_all[i], label=label, color=palette[i])

    plot.show_temp_pdf()
    plot.save(f"{TESTBED_SIM_RESULTS_PATH}/bilbo_standup_velocity_damping.pdf", 'pdf')


# === 2) Step response u = 0.5 between t=1 and t=3===========================

def compare_conjugate_pair_step_response():
    """
    2.1) Step response: influence of conjugated pair for theta.
         u = 0.5 from t=1 to t=3, simulation until t=5.
    """
    # Vary imaginary part / real part of theta poles:
    poles_1 = [0, -10, -5 + 3j, -5 - 3j, 0, -15]
    poles_2 = [0, -10, -5 + 5j, -5 - 5j, 0, -15]
    poles_3 = [0, -10, -3 + 3j, -3 - 3j, 0, -15]

    pole_sets = [poles_1, poles_2, poles_3]
    labels = ["$\\lambda_{\\theta} = -5 \\pm 3i$",
              "$\\lambda_{\\theta} = -5 \\pm 5i$",
              "$\\lambda_{\\theta} = -3 \\pm 3i$"]

    experiment_time = 5  # s
    time_vector = generate_time_vector(start=0, end=experiment_time, dt=TS)

    # Explicit step input: u1 = 0.5 between t=1 and t=3, same for all controllers
    input_step = np.zeros((len(time_vector), 2))
    # mask = (time_vector >= 1.0) & (time_vector < 3.0)
    mask = (time_vector >= 1.0) & (time_vector < 3.0)
    input_step[mask] = [-0.5, -0.5]
    # input_step[mask, 0] = +0.5
    input_step_norm = input_step[:, 0]

    x0 = BILBO_3D_State(
        x=0,
        y=0,
        v=0,
        theta=0,
        theta_dot=0,
        psi=0,
        psi_dot=0
    )

    theta_all = []
    v_all = []
    x_all = []

    for poles in pole_sets:
        dynamics = BILBO_Dynamics_3D(Ts=TS, model=MODEL)
        dynamics.eigenstructureAssignment(
            poles=poles,
            eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS
        )

        states, inputs = dynamics.simulate(
            input=input_step,
            include_zero_step=True,
            x0=x0
        )

        theta = np.array([s.theta for s in states])
        v = np.array([s.v for s in states])
        x = np.array([s.x for s in states])

        theta_all.append(theta[:-1])
        v_all.append(v[:-1])
        x_all.append(x[:-1])

    plot = Plot(
        rows=2,
        columns=2,
        size=(10, 5),
        use_agg_backend=True,
        facealpha=0,
        use_latex=False,
        font_family="Palatino"
    )

    palette = get_palette('dark', len(pole_sets))

    # Theta
    theta_cfg = AxisConfig(
        title="Step Response – Influence of $\\theta$ Conjugate Pair",
        xlabel="time [s]",
        ylabel="$\\theta$ [rad]",
        legend=LegendConfig(loc='upper right'),
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    theta_axis = Axis(id="theta_step_cp", config=theta_cfg)
    plot.set_axis(1, 1, theta_axis)

    # Velocity v
    v_cfg = AxisConfig(
        title="Step Response – Velocity $v$",
        xlabel="time [s]",
        ylabel="$v$ [m/s]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    v_axis = Axis(id="v_step_cp", config=v_cfg)
    plot.set_axis(1, 2, v_axis)

    # Displacement x
    x_cfg = AxisConfig(
        title="Step Response – Displacement $x$",
        xlabel="time [s]",
        ylabel="$x$ [m]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    x_axis = Axis(id="x_step_cp", config=x_cfg)
    plot.set_axis(2, 1, x_axis)

    # Input step norm (same for all controllers)
    u_cfg = AxisConfig(
        title="Step Input $\\tilde{u}_\\mathrm{L} = \\tilde{u}_\\mathrm{R}$",
        xlabel="time [s]",
        ylabel="$\\tilde{u}_\\mathrm{L},\\tilde{u}_\\mathrm{R}$ [Nm]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    u_axis = Axis(id="u1_step_cp", config=u_cfg)
    plot.set_axis(2, 2, u_axis)

    t_states = time_vector

    # States per pole set
    for i, label in enumerate(labels):
        theta_axis.plot(t_states, theta_all[i], label=label, color=palette[i])
        v_axis.plot(t_states, v_all[i], label=label, color=palette[i])
        x_axis.plot(t_states, x_all[i], label=label, color=palette[i])

    # Explicit step input
    u_axis.plot(t_states, input_step_norm, label="step input", color=palette[0])

    plot.show_temp_pdf()
    plot.save(f"{TESTBED_SIM_RESULTS_PATH}/bilbo_step_response_conjugate_pair_theta.pdf", 'pdf')


def compare_velocity_damping_step_response():
    """
    2.2) Step response: influence of velocity damping (second pole).
         u = 0.5 from t=1 to t=3, simulation until t=5.
    """
    poles_1 = [0, -5,  -5 + 5j, -5 - 5j, 0, -15]
    poles_2 = [0, -10, -5 + 5j, -5 - 5j, 0, -15]
    poles_3 = [0, -20, -5 + 5j, -5 - 5j, 0, -15]

    pole_sets = [poles_1, poles_2, poles_3]
    labels = ["$\\lambda_v = -5$", "$\\lambda_v = -10$", "$\\lambda_v = -20$"]

    experiment_time = 5.0  # s
    time_vector = generate_time_vector(start=0, end=experiment_time, dt=TS)

    # Step input (same as above)
    input_step = np.zeros((len(time_vector), 2))
    mask = (time_vector >= 1.0) & (time_vector < 3.0)
    input_step[mask] = [-0.5, -0.5]
    input_step_norm = input_step[:, 0]

    x0 = BILBO_3D_State(
        x=0,
        y=0,
        v=0,
        theta=0,
        theta_dot=0,
        psi=0,
        psi_dot=0
    )

    theta_all = []
    v_all = []
    x_all = []
    u1_all = []

    for poles in pole_sets:
        dynamics = BILBO_Dynamics_3D(Ts=TS, model=MODEL)
        dynamics.eigenstructureAssignment(
            poles=poles,
            eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS
        )

        states, inputs = dynamics.simulate(
            input=input_step,
            include_zero_step=True,
            x0=x0
        )

        theta = np.array([s.theta for s in states])
        v = np.array([s.v for s in states])
        x = np.array([s.x for s in states])

        u = np.array(inputs)
        u1 = u[:, 0]

        theta_all.append(theta[:-1])
        v_all.append(v[:-1])
        x_all.append(x[:-1])
        u1_all.append(u1[:-1])

    plot = Plot(
        rows=2,
        columns=2,
        size=(10, 5),
        use_agg_backend=True,
        facealpha=0,
        use_latex=False,
        font_family="Palatino"
    )

    palette = get_palette('dark', len(pole_sets))

    # Theta
    theta_cfg = AxisConfig(
        title="Step Response – Influence of Velocity Pole on $\\theta$",
        xlabel="time [s]",
        ylabel="$\\theta$ [rad]",
        legend=True,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    theta_axis = Axis(id="theta_step_vd", config=theta_cfg)
    plot.set_axis(1, 1, theta_axis)

    # Velocity v
    v_cfg = AxisConfig(
        title="Step Response – Velocity $v$",
        xlabel="time [s]",
        ylabel="$v$ [m/s]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    v_axis = Axis(id="v_step_vd", config=v_cfg)
    plot.set_axis(1, 2, v_axis)

    # Displacement x
    x_cfg = AxisConfig(
        title="Step Response – Displacement $x$",
        xlabel="time [s]",
        ylabel="$x$ [m]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    x_axis = Axis(id="x_step_vd", config=x_cfg)
    plot.set_axis(2, 1, x_axis)

    # Input u1 (actual wheel torque, closed-loop)
    u_cfg = AxisConfig(
        title="Step Input $\\tilde{u}_\\mathrm{L} = \\tilde{u}_\\mathrm{R}$",
        xlabel="time [s]",
        ylabel= "$\\tilde{u}_\\mathrm{L}, \\tilde{u}_\\mathrm{R}$ [Nm]",
        legend=False,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    u_axis = Axis(id="u1_step_vd", config=u_cfg)
    plot.set_axis(2, 2, u_axis)

    t_states = time_vector

    for i, label in enumerate(labels):
        theta_axis.plot(t_states, theta_all[i], label=label, color=palette[i])
        v_axis.plot(t_states, v_all[i], label=label, color=palette[i])
        x_axis.plot(t_states, x_all[i], label=label, color=palette[i])

    u_axis.plot(t_states, input_step_norm, label="step input", color=palette[0])


    plot.show_temp_pdf()
    plot.save(f"{TESTBED_SIM_RESULTS_PATH}/bilbo_step_response_velocity_damping.pdf", 'pdf')


# === 3) Influence of psi_dot gain (last pole) ===============================

def compare_psi_dot_gain_step_response():
    """
    3) Influence of the psi_dot gain (last pole).
       Step response, since it doesn't participate directly in balancing.
       u = 0.5 from t=1 to t=3, simulation until t=5.
    """
    poles_1 = [0, -10, -5 + 5j, -5 - 5j, 0, -5]
    poles_2 = [0, -10, -5 + 5j, -5 - 5j, 0, -15]
    poles_3 = [0, -10, -5 + 5j, -5 - 5j, 0, -30]

    pole_sets = [poles_1, poles_2, poles_3]
    labels = ["psi_dot pole = -5", "psi_dot pole = -15", "psi_dot pole = -30"]

    experiment_time = 5.0  # s
    time_vector = generate_time_vector(start=0, end=experiment_time, dt=TS)

    input_step = np.zeros((len(time_vector), 2))
    mask = (time_vector >= 1.0) & (time_vector < 3.0)
    input_step[mask, 0] = 0.5

    x0 = BILBO_3D_State(
        x=0,
        y=0,
        v=0,
        theta=0,
        theta_dot=0,
        psi=0,
        psi_dot=0
    )

    psi_all = []
    psi_dot_all = []
    x_all = []
    u1_all = []

    for poles in pole_sets:
        dynamics = BILBO_Dynamics_3D(Ts=TS, model=MODEL)
        dynamics.eigenstructureAssignment(
            poles=poles,
            eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS
        )

        states, inputs = dynamics.simulate(
            input=input_step,
            include_zero_step=True,
            x0=x0
        )

        psi = np.array([s.psi for s in states])
        psi_dot = np.array([s.psi_dot for s in states])
        x = np.array([s.x for s in states])

        u = np.array(inputs)
        u1 = u[:, 0]

        psi_all.append(psi[:-1])
        psi_dot_all.append(psi_dot[:-1])
        x_all.append(x[:-1])
        u1_all.append(u1[:-1])

    plot = Plot(
        rows=2,
        columns=2,
        size=(10, 5),
        use_agg_backend=True,
        facealpha=0,
        use_latex=False,
        font_family="Palatino"
    )

    palette = get_palette('dark', len(pole_sets))

    # psi
    psi_cfg = AxisConfig(
        title="Step Response – Yaw $\\psi$",
        xlabel="time [s]",
        ylabel="$\\psi$ [rad]",
        legend=True,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    psi_axis = Axis(id="psi_step", config=psi_cfg)
    plot.set_axis(1, 1, psi_axis)

    # psi_dot
    psi_dot_cfg = AxisConfig(
        title="Step Response – Yaw Rate $\\dot{\\psi}$",
        xlabel="time [s]",
        ylabel="$\\dot{\\psi}$ [rad/s]",
        legend=True,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    psi_dot_axis = Axis(id="psi_dot_step", config=psi_dot_cfg)
    plot.set_axis(1, 2, psi_dot_axis)

    # x displacement
    x_cfg = AxisConfig(
        title="Step Response – Displacement $x$",
        xlabel="time [s]",
        ylabel="$x$ [m]",
        legend=True,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    x_axis = Axis(id="x_step_psi", config=x_cfg)
    plot.set_axis(2, 1, x_axis)

    # Input u1
    u_cfg = AxisConfig(
        title="Step Input $u_1$",
        xlabel="time [s]",
        ylabel="$u_1$ [Nm]",
        legend=True,
        palette=palette,
        xlim=(0, time_vector[-1]),
        facecolor=(1, 0, 0, 0)
    )
    u_axis = Axis(id="u1_step_psi", config=u_cfg)
    plot.set_axis(2, 2, u_axis)

    t_states = time_vector

    for i, label in enumerate(labels):
        psi_axis.plot(t_states, psi_all[i], label=label, color=palette[i])
        psi_dot_axis.plot(t_states, psi_dot_all[i], label=label, color=palette[i])
        x_axis.plot(t_states, x_all[i], label=label, color=palette[i])
        u_axis.plot(t_states, u1_all[i], label=label, color=palette[i])

    plot.show_temp_pdf()
    plot.save(f"{TESTBED_SIM_RESULTS_PATH}/bilbo_step_response_psi_dot_gain.pdf", 'pdf')


# === Main wrapper ===========================================================

def run_all_comparisons():
    # 1) Standing up from theta = pi/2
    compare_conjugate_pair_stand_up()        # 1.1
    compare_velocity_damping_stand_up()      # 1.2

    # 2) Step response
    compare_conjugate_pair_step_response()   # 2.1
    compare_velocity_damping_step_response() # 2.2

    # 3) psi_dot gain
    # compare_psi_dot_gain_step_response()


if __name__ == '__main__':
    run_all_comparisons()