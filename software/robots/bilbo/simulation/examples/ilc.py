import numpy as np
from matplotlib import pyplot as plt

from core.utils.control_lib.lib_control.il.ilc import BILBO_STANDARD_REFERENCE_TRAJECTORY, getTransitionMatrixFromSystem, \
    getLearningMatricesOptimal, BILBO_BUMPED_REFERENCE_TRAJECTORY
from core.utils.control_lib.lib_control.il.iml import imlUpdateOptimal, getOptimalLearningMatrix, \
    getOptimalLearningMatrixFromMatrix
from core.utils.control_lib.lib_control.lifted_systems import vec2liftedMatrix, liftedMatrix2Vec
from core.utils.data import generate_time_vector, generate_random_input, resample
from robots.bilbo.simulation.model import BILBO_Dynamics_2D, DEFAULT_BILBO_MODEL, \
    BILBO_Dynamics_2D_Linear, BILBO_2D_POLES, BILBO_MICHAEL_MODEL


def example_ilc():
    N = len(BILBO_BUMPED_REFERENCE_TRAJECTORY)
    # Generate the robot
    bilbo_dynamics = BILBO_Dynamics_2D(model=DEFAULT_BILBO_MODEL, Ts=0.01)
    bilbo_dynamics.polePlacement(poles=BILBO_2D_POLES, apply_poles_to_system=True)

    bilbo_dynamics_linear = BILBO_Dynamics_2D_Linear(model=DEFAULT_BILBO_MODEL, Ts=0.01)
    bilbo_dynamics_linear.polePlacement(poles=BILBO_2D_POLES, apply_poles_to_system=True)
    # Get the transition matrix P
    P, _m = getTransitionMatrixFromSystem(bilbo_dynamics_linear.system, N=N)

    # Reference trajectory
    reference_trajectory = BILBO_BUMPED_REFERENCE_TRAJECTORY

    # u0:
    u0 = np.zeros((N,))

    J = 20

    uj = u0
    yj = None

    error_norms = []
    outputs = []

    for j in range(0, J):
        # Apply the uj input
        states = bilbo_dynamics.simulate(input=uj, reset=True, include_zero_step=False)
        # Get the theta
        theta = np.asarray([state.theta for state in states])

        # Calculate the error
        ej = reference_trajectory - theta

        # Calculate the optimal learning matrix
        L, _ = getLearningMatricesOptimal(P, r=1e-4, s=1e-2)

        # Calculate the new input
        uj = uj + L @ ej

        outputs.append(theta)
        error_norms.append(np.linalg.norm(ej))

    plt.figure()
    plt.plot(error_norms)
    plt.grid()
    plt.show()


def example_iml():
    bilbo_dynamics = BILBO_Dynamics_2D_Linear(model=DEFAULT_BILBO_MODEL, Ts=0.01)
    bilbo_dynamics.polePlacement(poles=BILBO_2D_POLES, apply_poles_to_system=True)

    J = 30
    error_norms = []

    t_vector = generate_time_vector(start=0, end=6, dt=0.01)
    N = len(t_vector)

    m0 = np.zeros((N,))
    mj = m0

    for i in range(0, J):
        # 1. Generate a random input
        uj = generate_random_input(t_vector, f_cutoff=4, sigma_I=1)

        # 2. Apply this random input
        states = bilbo_dynamics.simulate(input=uj, reset=True, include_zero_step=False)

        # 3. Get the theta
        theta = np.asarray([state.theta for state in states])

        # 4. Calculate the IML step
        ej = theta - vec2liftedMatrix(mj) @ uj
        Lj = getOptimalLearningMatrix(uj)

        mj = mj + Lj @ ej

        error_norms.append(np.linalg.norm(ej))

    plt.figure()
    plt.plot(error_norms)
    plt.grid()
    plt.show()


def example_dilc():
    bilbo_dynamics = BILBO_Dynamics_2D(model=DEFAULT_BILBO_MODEL, Ts=0.01)
    bilbo_dynamics.polePlacement(poles=BILBO_2D_POLES, apply_poles_to_system=True)

    reference_trajectory = BILBO_STANDARD_REFERENCE_TRAJECTORY

    N = len(reference_trajectory)
    t_vector_resample = generate_time_vector(start=0, end=(N - 1) * 0.01, dt=0.01)

    J = 30
    error_norms_identification = []
    error_norms_learning = []

    u0 = generate_random_input(t_vector_resample, f_cutoff=4, sigma_I=1)
    m0 = generate_random_input(t_vector_resample, f_cutoff=4, sigma_I=0.01)

    u = u0
    m = m0

    for j in range(0, J):
        # Run the trial with the current u
        states = bilbo_dynamics.simulate(input=u, reset=True, include_zero_step=False)
        y = np.asarray([state.theta for state in states])

        # IML
        U = vec2liftedMatrix(u)
        e_iml = y - vec2liftedMatrix(m) @ u

        W = np.eye(N)
        S = U.T @ U + 1e-6 * np.eye(N)
        S = 1.5 * S
        jitter = 1e-8 * np.eye(N)
        A = U @ W @ U.T + S + jitter
        gain = np.linalg.solve(A, U @ W)
        L_m = gain.T

        m = m + L_m @ e_iml

        # ILC
        M = vec2liftedMatrix(m)

        e_ilc = reference_trajectory - y

        W = np.eye(N)
        S = M.T @ M + 1e-6 * np.eye(N)
        S = 1.5 * S
        jitter = 1e-8 * np.eye(N)
        A = M @ W @ M.T + S + jitter
        gain = np.linalg.solve(A, M @ W)
        L_ilc = gain.T

        u = u + L_ilc @ e_ilc

        error_norms_learning.append(np.linalg.norm(e_ilc))
        error_norms_identification.append(np.linalg.norm(e_iml))

    plt.figure()
    plt.plot(error_norms_learning, label='ILC')
    plt.plot(error_norms_identification, label='IML')
    plt.legend()
    plt.grid()
    plt.show()


def example_dilc2():
    bilbo_dynamics = BILBO_Dynamics_2D(model=DEFAULT_BILBO_MODEL, Ts=0.01)
    bilbo_dynamics.polePlacement(poles=BILBO_2D_POLES, apply_poles_to_system=True)

    time_vector = generate_time_vector(start=0, end=5, dt=0.01)
    reference_trajectory = np.deg2rad(60) * np.sin(2 * np.pi * time_vector)

    N = len(reference_trajectory)

    J = 5
    error_norms_identification = []
    error_norms_learning = []

    u0 = generate_random_input(time_vector, f_cutoff=4, sigma_I=1)
    m0 = generate_random_input(time_vector, f_cutoff=4, sigma_I=0.01)

    u = u0
    m = m0

    for j in range(0, J):
        # Run the trial with the current u
        states = bilbo_dynamics.simulate(input=u, reset=True, include_zero_step=False)
        y = np.asarray([state.theta for state in states])

        # IML
        U = vec2liftedMatrix(u)
        e_iml = y - vec2liftedMatrix(m) @ u

        W = np.eye(N)
        S = U.T @ U + 1e-6 * np.eye(N)
        S = 1.5 * S
        jitter = 1e-8 * np.eye(N)
        A = U @ W @ U.T + S + jitter
        gain = np.linalg.solve(A, U @ W)
        L_m = gain.T

        m = m + L_m @ e_iml

        # ILC
        M = vec2liftedMatrix(m)

        e_ilc = reference_trajectory - y

        W = np.eye(N)
        S = M.T @ M + 1e-6 * np.eye(N)
        S = 1.5 * S
        jitter = 1e-8 * np.eye(N)
        A = M @ W @ M.T + S + jitter
        gain = np.linalg.solve(A, M @ W)
        L_ilc = gain.T

        u = u + L_ilc @ e_ilc

        error_norms_learning.append(np.linalg.norm(e_ilc))
        error_norms_identification.append(np.linalg.norm(e_iml))

    # plt.figure()
    # plt.plot(error_norms_learning, label='ILC')
    # plt.plot(error_norms_identification, label='IML')
    # plt.legend()
    # plt.grid()
    # plt.show()

    print(repr(y))

    plt.plot(y)
    plt.show()


if __name__ == '__main__':
    example_ilc()
