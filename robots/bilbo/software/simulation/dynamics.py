"""
Non-linear 3D BILBO dynamics for the simulated firmware.

State vector: [x, y, v, theta, theta_dot, psi, psi_dot]
Input vector: [tau_left, tau_right]

Euler integration at the firmware control rate (100 Hz / Ts = 0.01 s).
"""
from __future__ import annotations

import dataclasses
import math
import os

import numpy as np
import yaml


@dataclasses.dataclass
class BilboModel:
    m_b: float = 1.2
    m_w: float = 0.4
    l: float = 0.026
    d_w: float = 0.22
    I_w: float = 2e-4
    I_y: float = 0.005
    I_x: float = 0.02
    I_z: float = 0.03
    c_alpha: float = 4.6302e-4
    r_w: float = 0.06
    tau_theta: float = 0.4
    tau_x: float = 0.4
    tau_psi: float = 0.3
    max_pitch: float = 1.8326  # ~105 deg — floor contact angle


@dataclasses.dataclass
class DynamicsState:
    x: float = 0.0
    y: float = 0.0
    v: float = 0.0
    theta: float = 0.0
    theta_dot: float = 0.0
    psi: float = 0.0
    psi_dot: float = 0.0


def load_model(yaml_path: str | None = None) -> tuple[BilboModel, float, float]:
    """Load model parameters from YAML. Returns (model, Ts, battery_voltage)."""
    if yaml_path is None:
        yaml_path = os.path.join(os.path.dirname(__file__), 'model.yaml')
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)

    model = BilboModel(**data['dynamics'])
    Ts = data['simulation']['Ts']
    battery_voltage = data['simulation']['battery_voltage']
    return model, Ts, battery_voltage


class BilboDynamics3D:
    """Non-linear 3D BILBO dynamics with Euler integration.

    Matches the continuous-time equations used in the host-side simulation
    (software/simulation/src/objects/bilbo.py) but integrated at the firmware rate.
    """

    def __init__(self, model: BilboModel, Ts: float = 0.01):
        self.model = model
        self.Ts = Ts
        self.state = DynamicsState()
        self._ground_contact: bool = False
        self._prev_pose: dict | None = None

    def step(self, tau_left: float, tau_right: float) -> DynamicsState:
        """Advance one time step given motor torques. Returns the new state."""
        g = 9.81
        m = self.model
        s = self.state

        x = s.x
        y = s.y
        v = s.v
        theta = s.theta
        td = s.theta_dot
        psi = s.psi
        pd = s.psi_dot

        u_sum = tau_left + tau_right
        u_diff = tau_left - tau_right

        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        # Common terms
        V_1 = ((m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2) *
               (m.I_y + m.m_b * m.l ** 2) - m.m_b ** 2 * m.l ** 2 * cos_t ** 2)

        V_2 = (m.I_z + 2 * m.I_w + (m.m_w + m.I_w / m.r_w ** 2) * m.d_w ** 2 / 2
               - (m.I_z - m.I_x - m.m_b * m.l ** 2) * sin_t ** 2)

        # Coriolis / centrifugal terms
        C_11 = m.m_b ** 2 * m.l ** 2 * cos_t
        C_12 = (m.I_y + m.m_b * m.l ** 2) * m.m_b * m.l
        C_21 = (m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2) * m.m_b * m.l
        C_22 = m.m_b ** 2 * m.l ** 2 * cos_t
        C_13 = ((m.I_y + m.m_b * m.l ** 2) * m.m_b * m.l
                + m.m_b * m.l * (m.I_z - m.I_x - m.m_b * m.l ** 2) * cos_t ** 2)
        C_23 = ((m.m_b ** 2 * m.l ** 2
                 + (m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2)
                 * (m.I_z - m.I_x - m.m_b * m.l ** 2)) * cos_t)
        C_31 = 2 * (m.I_z - m.I_x - m.m_b * m.l ** 2) * cos_t
        C_32 = m.m_b * m.l

        # Damping terms
        D_11 = ((m.I_y + m.m_b * m.l ** 2) * 2 * m.c_alpha / m.r_w ** 2
                - 2 * m.m_b * m.l * cos_t * m.c_alpha / m.r_w)
        D_12 = ((m.I_y + m.m_b * m.l ** 2) * 2 * m.c_alpha / m.r_w
                - m.m_b * m.l * cos_t * 2 * m.c_alpha)
        D_21 = ((m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2) * 2 * m.c_alpha / m.r_w
                + m.m_b * m.l * cos_t * 2 * m.c_alpha / m.r_w ** 2)
        D_22 = ((m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2) * 2 * m.c_alpha
                + m.m_b * m.l * cos_t * 2 * m.c_alpha / m.r_w)
        D_33 = m.d_w ** 2 / (2 * m.r_w ** 2) * m.c_alpha

        # Input coupling
        B_1 = (m.I_y + m.m_b * m.l ** 2) / m.r_w + m.m_b * m.l * cos_t
        B_2 = m.m_b * m.l / m.r_w * cos_t + m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2
        B_3 = m.d_w / (2 * m.r_w)

        # State derivatives
        x_dot = v * math.cos(psi)
        y_dot = v * math.sin(psi)

        v_dot = (sin_t / V_1 * (-C_11 * g + C_12 * td ** 2 + C_13 * pd ** 2)
                 - D_11 / V_1 * v + D_12 / V_1 * td
                 + B_1 / V_1 * u_sum - m.tau_x * v)

        theta_dot_dot = (sin_t / V_1 * (C_21 * g - C_22 * td ** 2 - C_23 * pd ** 2)
                         + D_21 / V_1 * v - D_22 / V_1 * td
                         - B_2 / V_1 * u_sum - m.tau_theta * td)

        psi_dot_dot = (sin_t / V_2 * (C_31 * td * pd - C_32 * pd * v)
                       - D_33 / V_2 * pd
                       - B_3 / V_2 * u_diff - m.tau_psi * pd)

        # Euler integration
        dt = self.Ts
        self.state = DynamicsState(
            x=x + x_dot * dt,
            y=y + y_dot * dt,
            v=v + v_dot * dt,
            theta=theta + td * dt,
            theta_dot=td + theta_dot_dot * dt,
            psi=psi + pd * dt,
            psi_dot=pd + psi_dot_dot * dt,
        )

        self._apply_floor_constraint()

        return self.state

    def _apply_floor_constraint(self):
        """Clamp theta at max_pitch to simulate floor contact."""
        max_pitch = self.model.max_pitch
        s = self.state
        theta = s.theta
        theta_dot = s.theta_dot

        side = 1.0 if theta >= 0.0 else -1.0
        depth = abs(theta) - max_pitch
        approaching = (theta_dot * side) > 0.0

        # Contact detection with hysteresis
        tol_enter = 1e-4
        tol_exit = 2e-4

        if depth > 0.0 or (abs(abs(theta) - max_pitch) <= tol_enter and approaching):
            self._ground_contact = True
        elif abs(abs(theta) - max_pitch) > tol_exit and not approaching:
            self._ground_contact = False

        if self._prev_pose is None:
            self._prev_pose = {'x': s.x, 'y': s.y, 'psi': s.psi}

        if self._ground_contact:
            # Clamp to floor
            s.theta = side * max_pitch

            # Kill normal velocity
            if approaching:
                s.theta_dot = 0.0
            if abs(s.theta_dot) < 5e-3:
                s.theta_dot = 0.0

            # Friction: kill translational and yaw motion
            mu = 0.8
            friction_decel = mu * 9.81 * self.Ts
            if abs(s.v) < friction_decel:
                s.v = 0.0
                s.x = self._prev_pose['x']
                s.y = self._prev_pose['y']
            else:
                s.v -= math.copysign(friction_decel, s.v)

            if abs(s.psi_dot) < friction_decel:
                s.psi_dot = 0.0
                s.psi = self._prev_pose['psi']
            else:
                s.psi_dot -= math.copysign(friction_decel, s.psi_dot)

        elif depth > 0.0:
            # Penetration outside contact — resolve once
            s.theta = side * max_pitch
            if approaching:
                s.theta_dot = 0.0

        self._prev_pose = {'x': s.x, 'y': s.y, 'psi': s.psi}

    def set_state(self, **kwargs):
        """Set individual state fields."""
        for k, val in kwargs.items():
            if hasattr(self.state, k):
                setattr(self.state, k, float(val))

    def reset(self):
        self.state = DynamicsState()
        self._ground_contact = False
        self._prev_pose = None

    def get_wheel_speeds(self, tau_left: float, tau_right: float) -> tuple[float, float]:
        """Approximate wheel speeds from forward velocity and yaw rate."""
        v = self.state.v
        pd = self.state.psi_dot
        r = self.model.r_w
        d = self.model.d_w
        # v_wheel = v ± (d/2)*psi_dot, convert to angular speed
        speed_left = (v - d / 2 * pd) / r
        speed_right = (v + d / 2 * pd) / r
        return speed_left, speed_right
