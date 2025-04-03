import numpy as np

def estimate_system_and_lifted_matrix(u_list, y_list, L):
    """
    Estimate the impulse response h (of length L) for a SISO dynamic system
    from multiple input/output trajectory pairs and then compute the lifted
    system matrix P (a lower-triangular Toeplitz matrix).

    Parameters:
      u_list: list of numpy arrays
          Each array contains the input (torque) trajectory for one experiment.
      y_list: list of numpy arrays
          Each array contains the output (angle) trajectory corresponding to the input.
          It is assumed that len(u) == len(y) for each pair.
      L: int
          The number of impulse response coefficients to estimate. This also sets the
          dimensions of the lifted matrix P (L x L).

    Returns:
      h: numpy array of shape (L,)
          The estimated impulse response.
      P: numpy array of shape (L, L)
          The lifted system matrix where:
              P[i, j] = h[i - j] for i >= j, and 0 otherwise.
    """
    # Build a big regression problem from all trajectories.
    U_big = []
    Y_big = []


    for u, y in zip(u_list, y_list):
        T = len(u)
        # For each time step t in this trajectory,
        # form a row [u[t], u[t-1], ..., u[t-L+1]]
        for t in range(T):
            # Use 0 for indices t-k < 0 (causality)
            row = [u[t - k] if t - k >= 0 else 0 for k in range(L)]
            U_big.append(row)
            Y_big.append(y[t])

    U_big = np.array(U_big)
    Y_big = np.array(Y_big)

    # Solve the linear least squares problem U_big * h = Y_big
    h, residuals, rank, s = np.linalg.lstsq(U_big, Y_big, rcond=None)

    # Build the lifted system matrix P (L x L lower-triangular Toeplitz matrix)
    P = np.zeros((L, L))
    for i in range(L):
        for j in range(i + 1):  # Only fill entries for which i >= j.
            P[i, j] = h[i - j]

    return h, P


# Example usage:
if __name__ == "__main__":
    # Generate synthetic data for demonstration:
    # True impulse response (FIR of length 4)
    h_true = np.array([0.5, 0.3, 0.1, 0.05])
    L = len(h_true)

    # Create N experiments (trajectories) each of length T
    N = 5
    T = 50
    u_list = []
    y_list = []
    np.random.seed(0)
    for _ in range(N):
        u = np.random.randn(T)
        y = np.zeros(T)
        for t in range(T):
            # Convolve with the true impulse response (with causality)
            for k in range(L):
                if t - k >= 0:
                    y[t] += h_true[k] * u[t - k]
        # Optionally add some noise:
        y += 0.01 * np.random.randn(T)
        u_list.append(u)
        y_list.append(y)

    # Estimate impulse response and lifted matrix
    h_est, P_est = estimate_system_and_lifted_matrix(u_list, y_list, L)

    print("Estimated impulse response h:")
    print(h_est)
    print("\nLifted system matrix P:")
    print(P_est)