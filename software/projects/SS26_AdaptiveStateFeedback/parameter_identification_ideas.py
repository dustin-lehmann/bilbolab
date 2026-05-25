"""Offline parameter identification ideas for BILBO.

Two example identification schemes that reuse the simulation/cost utilities from
`offline_simulation.py`:

  1. Output-error nonlinear least squares (`scipy.optimize.least_squares`)
     -> minimises the same trajectory-mismatch cost surface that
        `plot_cost_2d` visualises, but with a trust-region optimiser.
  2. Equation-error linear least squares on the base parameters
     (M = m_b + 2*m_w + 2*I_w/r_w^2,  b = m_b*l,  c = I_y + m_b*l^2)
     -> a single linear solve; physical parameters recovered afterwards.
"""

import dataclasses

import numpy as np
from scipy.optimize import least_squares

from core.utils.control_lib.lib_control.learning.vector_generation import multisine_vector
from robots.bilbo.simulation.model import (
    BILBO_Dynamics_2D, BILBO_Dynamics_3D, DEFAULT_BILBO_MODEL,
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS,
    BILBO_2D_State, BILBO_2D_POLES,
)

from offline_simulation import _states_to_array


# === IDEA 1: OUTPUT-ERROR NONLINEAR LEAST SQUARES =====================================================================
def output_error_least_squares_example(noise_std=0.02, seed=0):
    """Identify (l, m_b, I_y) by *nonlinear* (output-error) least squares.

    The model is nonlinear in the parameters, so this is a nonlinear LS problem:
    `scipy.optimize.least_squares` minimises the 2-norm of the residual

        r(theta) = x_measured - x_simulated(theta),      theta = (l, m_b, I_y)

    i.e. exactly the cost surface explored by `plot_cost_2d`, but solved with a
    trust-region optimiser instead of a grid. All other model parameters and the
    feedback gain K are assumed known and held fixed.

    Gaussian measurement noise is added to the reference data (`noise_std` is the
    standard deviation as a fraction of each state channel's RMS variation). The
    residuals are normalised by the per-channel noise level, so the problem is a
    proper weighted LS and `inv(J^T J)` is directly the parameter covariance.
    Output-error stays statistically unbiased under measurement noise.
    """
    rng = np.random.default_rng(seed)
    base_model = dataclasses.replace(DEFAULT_BILBO_MODEL, tau_theta=0.2, tau_x=0.2)
    true_theta = np.array([base_model.l, base_model.m_b, base_model.I_y])  # (l, m_b, I_y)

    # Excitation + reference data, generated with the true model.
    # Schroeder-phase multisine -> deterministic, reproducible excitation.
    excitation = multisine_vector(600, phase='schroeder')
    u = np.column_stack([excitation, excitation])
    true_model = dataclasses.replace(base_model, l=true_theta[0],
                                     m_b=true_theta[1], I_y=true_theta[2])
    reference_dynamics = BILBO_Dynamics_3D(model=true_model)
    K = reference_dynamics.eigenstructureAssignment(
        poles=BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
        eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS)
    reference_states, _ = reference_dynamics.simulate(input=u, include_zero_step=False)
    x_clean = _states_to_array(reference_states)

    # Add measurement noise, scaled per state channel (different units!).
    noise_sigma = noise_std * np.std(x_clean, axis=0)
    x_measured = x_clean + rng.normal(scale=noise_sigma, size=x_clean.shape)
    # Residual weighting: 1/noise_sigma; channels that never move -> weight 1.
    weight = np.where(noise_sigma > 0.0, noise_sigma, 1.0)

    # Noise-normalised residual -> weighted least squares.
    def residual(theta):
        model = dataclasses.replace(base_model, l=theta[0], m_b=theta[1], I_y=theta[2])
        dynamics = BILBO_Dynamics_3D(model=model)
        dynamics.K = K
        states, _ = dynamics.simulate(input=u, include_zero_step=False)
        return ((x_measured - _states_to_array(states)) / weight).ravel()

    theta0 = np.array([0.040, 1.60, 0.009])  # deliberately wrong initial guess

    result = least_squares(
        residual, theta0,
        bounds=([0.0, 0.1, 1e-4], [0.2, 4.0, 0.05]),
        x_scale=[0.02, 1.0, 0.005],  # parameters span ~3 decades -> scale them
    )
    theta_hat = result.x

    # Residuals are noise-normalised, so inv(J^T J) is the parameter covariance.
    JtJ = result.jac.T @ result.jac
    covariance = np.linalg.inv(JtJ)
    std = np.sqrt(np.diag(covariance))
    correlation = covariance / np.outer(std, std)

    print('=== Idea 1: output-error nonlinear least squares (scipy) ===')
    print(f'measurement noise: {noise_std * 100:.0f}% of each channel RMS')
    print(f'{"param":5s} {"true":>12s} {"guess":>12s} {"estimate":>14s} '
          f'{"1-sigma":>11s} {"rel.err":>11s}')
    for i, name in enumerate(['l', 'm_b', 'I_y']):
        rel_err = (theta_hat[i] - true_theta[i]) / true_theta[i]
        print(f'{name:5s} {true_theta[i]:12.5f} {theta0[i]:12.5f} '
              f'{theta_hat[i]:14.6f} {std[i]:11.2e} {rel_err:11.2e}')
    print(f'cond(J^T J)            = {np.linalg.cond(JtJ):.2e}')
    print('correlation matrix (l, m_b, I_y) — note the l <-> I_y coupling:')
    print(np.array2string(correlation, precision=3, suppress_small=True))
    print()


# === IDEA 2: EQUATION-ERROR LINEAR LEAST SQUARES ======================================================================
def _band_limited_excitation(n_steps, Ts, freq_max=1.5, n_sines=6, amplitude=0.4, seed=0):
    """Smooth, low-frequency multisine torque excitation (sum of sines).

    Equation-error identification has to differentiate the data, so the
    excitation is deliberately kept well below the measurement-noise band — this
    is what lets the Savitzky-Golay filter separate signal from noise.
    """
    t = np.arange(n_steps) * Ts
    freqs = np.linspace(0.3, freq_max, n_sines)
    phases = np.random.default_rng(seed).uniform(0, 2 * np.pi, n_sines)
    return amplitude / n_sines * sum(
        np.sin(2 * np.pi * f * t + ph) for f, ph in zip(freqs, phases))


def equation_error_least_squares_example(noise_std=0.01, seed=0):
    """Identify (l, m_b, I_y) by *linear* least squares on the base parameters.

    The planar BILBO equation of motion, written in *implicit* form

        Mass(p) * [v_dot; theta_ddot]  +  Coriolis  +  Gravity  =  Input

    is LINEAR in the base parameters

        p1 = M = m_b + 2*m_w + 2*I_w/r_w^2   (total effective mass)
        p2 = b = m_b * l                     (first mass moment)
        p3 = c = I_y + m_b * l^2             (pitch inertia about the wheel axis)

    Concretely, with  Mass = [[M, b*cos(th)], [b*cos(th), c]]:

        eq_v:  M*a_v + b*(cos(th)*a_th - sin(th)*th_dot^2)          =  u / r_w
        eq_th:         b*(cos(th)*a_v  - g*sin(th))      + c*a_th   = -u

    where a_v = v_dot + tau_x*v  and  a_th = theta_ddot + tau_theta*theta_dot.

    Stacking these two rows for every sample gives  Phi @ p = y, solved with a
    single linear least-squares solve. The physical parameters then follow as

        m_b = M - M_known,   l = b / m_b,   I_y = c - m_b * l^2.

    `I_y` is only ever observed through the lump `c = I_y + m_b*l^2`, which is
    exactly why it is the hardest of the three to pin down.

    Noise note: equation error must differentiate the data (which amplifies
    noise ~1/Ts), and the noisy states also enter the regressor Phi itself
    (errors-in-variables). Two standard countermeasures are used here:
      (1) a band-limited excitation, keeping the informative signal well below
          the noise band;
      (2) a Savitzky-Golay filter that smooths the measured states before the
          (forward-difference) derivatives are taken.
    The estimate is then good but, unlike output error, degrades visibly as the
    measurement noise grows.

    The tiny speed-dependent wheel drag (c_alpha) is dropped here — it does not
    admit a base-parameter (linear) implicit form. All other parameters known.
    """
    from scipy.signal import savgol_filter

    rng = np.random.default_rng(seed)
    Ts = 0.01
    g = 9.81

    # Planar 2D model; c_alpha = 0 so the implicit EOM above is exact.
    base_model = dataclasses.replace(DEFAULT_BILBO_MODEL, tau_theta=0.2, tau_x=0.2, c_alpha=0.0)
    true_l, true_m_b, true_I_y = base_model.l, base_model.m_b, base_model.I_y
    m_known = 2 * base_model.m_w + 2 * base_model.I_w / base_model.r_w ** 2

    # --- Reference data: closed-loop balancing, band-limited excitation -----
    dynamics = BILBO_Dynamics_2D(model=base_model, Ts=Ts)
    K = dynamics.polePlacement(BILBO_2D_POLES)
    excitation = _band_limited_excitation(800, Ts)
    states = dynamics.simulate(input=excitation, x0=BILBO_2D_State(0, 0, 0, 0),
                               include_zero_step=False)
    # x0 is the state BEFORE the first input; stack it in front of the results.
    traj_clean = np.vstack([np.zeros(4), [s.asarray() for s in states]])  # (N+1, 4)

    # Add measurement noise, scaled per state channel (noise_std = 0 -> none).
    noise_sigma = noise_std * np.std(traj_clean, axis=0)
    traj = traj_clean + rng.normal(scale=noise_sigma, size=traj_clean.shape)

    # Savitzky-Golay: smooth the noisy state signals (this is the only
    # noise-reduction step). Derivatives are then taken as forward differences
    # of the SMOOTHED states — for explicit-Euler data that difference is the
    # exact integrated derivative, so the method stays unbiased as noise -> 0.
    window, poly = 31, 3
    x_s = savgol_filter(traj, window, poly, axis=0)

    tau_x, tau_theta, r_w = base_model.tau_x, base_model.tau_theta, base_model.r_w

    # --- Build the regressor Phi and target y --------------------------------
    phi_rows, y_rows = [], []
    for k in range(len(excitation)):
        v, theta, theta_dot = x_s[k, 1], x_s[k, 2], x_s[k, 3]
        v_dot = (x_s[k + 1, 1] - x_s[k, 1]) / Ts
        theta_ddot = (x_s[k + 1, 3] - x_s[k, 3]) / Ts

        # Total wheel torque actually applied this step: u = excitation - K @ x.
        u = float(excitation[k] - (K @ x_s[k])[0])

        a_v = v_dot + tau_x * v
        a_th = theta_ddot + tau_theta * theta_dot
        cos_t, sin_t = np.cos(theta), np.sin(theta)

        # eq_v  and  eq_th, each linear in p = [M, b, c]
        phi_rows.append([a_v, cos_t * a_th - sin_t * theta_dot ** 2, 0.0])
        y_rows.append(u / r_w)
        phi_rows.append([0.0, cos_t * a_v - g * sin_t, a_th])
        y_rows.append(-u)

    phi = np.array(phi_rows)
    y = np.array(y_rows)

    # --- Linear least squares for the base parameters ------------------------
    p_hat, *_ = np.linalg.lstsq(phi, y, rcond=None)
    m_hat, b_hat, c_hat = p_hat

    # Recover the physical parameters.
    m_b_hat = m_hat - m_known
    l_hat = b_hat / m_b_hat
    I_y_hat = c_hat - m_b_hat * l_hat ** 2

    p_true = np.array([true_m_b + m_known,
                       true_m_b * true_l,
                       true_I_y + true_m_b * true_l ** 2])

    print('=== Idea 2: equation-error linear least squares (base parameters) ===')
    print(f'measurement noise: {noise_std * 100:.0f}% of each channel RMS '
          f'(Savitzky-Golay smoothed)')
    print('base parameters  p = [M, b = m_b*l, c = I_y + m_b*l^2]:')
    for name, est, tru in zip(['M', 'b', 'c'], p_hat, p_true):
        print(f'  {name}: true = {tru:12.6f}   estimate = {est:12.6f}   '
              f'rel.err = {(est - tru) / tru:.2e}')
    print(f'cond(Phi)              = {np.linalg.cond(phi):.2e}')
    print('recovered physical parameters:')
    for name, est, tru in zip(['l', 'm_b', 'I_y'],
                              [l_hat, m_b_hat, I_y_hat],
                              [true_l, true_m_b, true_I_y]):
        print(f'  {name:4s}: true = {tru:12.6f}   estimate = {est:12.6f}   '
              f'rel.err = {(est - tru) / tru:.2e}')
    print()


if __name__ == '__main__':
    output_error_least_squares_example()
    equation_error_least_squares_example()
