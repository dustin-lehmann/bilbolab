"""
LQR Controller Implementation for BILBO Robot

This module implements a Linear Quadratic Regulator (LQR) for balancing
control of the two-wheeled inverted pendulum robot.

The state vector is defined as:
    x = [theta, theta_dot, psi, psi_dot]^T

where:
    theta     - pitch angle (body tilt from vertical)
    theta_dot - pitch angular velocity
    psi       - yaw angle (heading)
    psi_dot   - yaw angular velocity
"""

import numpy as np
from scipy import linalg
from dataclasses import dataclass
from typing import Tuple


@dataclass
class RobotParameters:
    """Physical parameters of the BILBO robot."""

    # Mass properties
    m_body: float = 2.5      # Body mass [kg]
    m_wheel: float = 0.15    # Wheel mass [kg]

    # Geometric properties
    l_body: float = 0.15     # Distance from wheel axis to CoM [m]
    r_wheel: float = 0.05    # Wheel radius [m]
    d_wheel: float = 0.20    # Distance between wheels [m]

    # Inertia properties
    I_body: float = 0.02     # Body moment of inertia [kg*m^2]
    I_wheel: float = 0.001   # Wheel moment of inertia [kg*m^2]

    # Physical constants
    g: float = 9.81          # Gravitational acceleration [m/s^2]


class LQRController:
    """
    Linear Quadratic Regulator for BILBO balancing control.

    The controller computes optimal state feedback gains K such that
    the control law u = -K @ x minimizes the quadratic cost:

        J = integral(x^T Q x + u^T R u) dt

    where Q penalizes state deviations and R penalizes control effort.
    """

    def __init__(self, params: RobotParameters = None):
        self.params = params or RobotParameters()
        self.A, self.B = self._compute_linearized_system()
        self.K = None
        self.Q = None
        self.R = None

    def _compute_linearized_system(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute linearized state-space matrices around the upright equilibrium.

        Returns:
            A: State matrix (4x4)
            B: Input matrix (4x2)
        """
        p = self.params

        # Derived quantities
        M = p.m_body + 2 * p.m_wheel
        I_total = p.I_body + p.m_body * p.l_body**2

        # Linearized dynamics around theta = 0
        # State: [theta, theta_dot, psi, psi_dot]
        # Input: [tau_left, tau_right]

        a23 = p.m_body * p.g * p.l_body / I_total
        b21 = -1.0 / (I_total * p.r_wheel)
        b42 = p.d_wheel / (2 * p.I_wheel * p.r_wheel)

        A = np.array([
            [0, 1, 0, 0],
            [a23, 0, 0, 0],
            [0, 0, 0, 1],
            [0, 0, 0, 0]
        ])

        B = np.array([
            [0, 0],
            [b21, b21],
            [0, 0],
            [b42, -b42]
        ])

        return A, B

    def compute_gains(self, Q: np.ndarray = None, R: np.ndarray = None) -> np.ndarray:
        """
        Compute LQR gains by solving the continuous-time algebraic Riccati equation.

        Args:
            Q: State weighting matrix (4x4), default emphasizes pitch angle
            R: Control weighting matrix (2x2), default balances control effort

        Returns:
            K: Feedback gain matrix (2x4)
        """
        # Default weighting matrices
        if Q is None:
            Q = np.diag([100.0, 10.0, 50.0, 5.0])  # theta, theta_dot, psi, psi_dot
        if R is None:
            R = np.diag([1.0, 1.0])  # left and right motor torques

        self.Q = Q
        self.R = R

        # Solve continuous-time algebraic Riccati equation
        # A^T P + P A - P B R^-1 B^T P + Q = 0
        P = linalg.solve_continuous_are(self.A, self.B, Q, R)

        # Compute optimal gain: K = R^-1 B^T P
        self.K = np.linalg.inv(R) @ self.B.T @ P

        return self.K

    def compute_control(self, state: np.ndarray, reference: np.ndarray = None) -> np.ndarray:
        """
        Compute control torques for given state.

        Args:
            state: Current state vector [theta, theta_dot, psi, psi_dot]
            reference: Desired state (default is upright equilibrium)

        Returns:
            u: Control torques [tau_left, tau_right]
        """
        if self.K is None:
            self.compute_gains()

        if reference is None:
            reference = np.zeros(4)

        error = state - reference
        u = -self.K @ error

        return u

    def check_stability(self) -> bool:
        """
        Check if the closed-loop system is stable.

        Returns:
            True if all eigenvalues have negative real parts
        """
        if self.K is None:
            self.compute_gains()

        A_cl = self.A - self.B @ self.K
        eigenvalues = np.linalg.eigvals(A_cl)

        return np.all(np.real(eigenvalues) < 0)

    def get_closed_loop_poles(self) -> np.ndarray:
        """Get eigenvalues of the closed-loop system."""
        if self.K is None:
            self.compute_gains()

        A_cl = self.A - self.B @ self.K
        return np.linalg.eigvals(A_cl)


def main():
    """Example usage of the LQR controller."""

    # Create controller with default robot parameters
    controller = LQRController()

    # Compute optimal gains
    K = controller.compute_gains()

    print("LQR Controller for BILBO Robot")
    print("=" * 40)
    print(f"\nFeedback gain matrix K:")
    print(f"  Shape: {K.shape}")
    print(f"  K = \n{K}")

    # Check stability
    is_stable = controller.check_stability()
    print(f"\nClosed-loop stability: {'Stable' if is_stable else 'Unstable'}")

    # Show closed-loop poles
    poles = controller.get_closed_loop_poles()
    print(f"\nClosed-loop poles:")
    for i, pole in enumerate(poles):
        print(f"  p{i+1} = {pole:.4f}")

    # Simulate control for a perturbed state
    initial_state = np.array([0.1, 0.0, 0.0, 0.0])  # 0.1 rad pitch perturbation
    u = controller.compute_control(initial_state)

    print(f"\nControl response to {np.degrees(initial_state[0]):.1f} deg pitch:")
    print(f"  tau_left  = {u[0]:.4f} Nm")
    print(f"  tau_right = {u[1]:.4f} Nm")


if __name__ == "__main__":
    main()
