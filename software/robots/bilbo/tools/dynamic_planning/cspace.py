"""Configuration space computation for (s, theta) planning."""

import dataclasses

import matplotlib.pyplot as plt
import numpy as np

from .geometry import RobotGeometry, Obstacle, check_collision_grid


@dataclasses.dataclass
class CSpaceObstacle:
    """Rectangular obstacle defined directly in (s, theta) configuration space.

    Blocks a rectangular region [s_min, s_max] x [theta_min, theta_max].
    Theta values are in radians.
    """
    s_min: float
    s_max: float
    theta_min: float  # [rad]
    theta_max: float  # [rad]


@dataclasses.dataclass
class CSpaceConfig:
    """Grid parameters for the configuration space."""
    s_range: tuple[float, float] = (-0.5, 2.5)
    theta_range: tuple[float, float] = (-1.2, 1.2)  # [rad]
    s_resolution: int = 400
    theta_resolution: int = 400
    safety_margin: float = 0.02  # Extra clearance around obstacles [m]
    obstacles: list[CSpaceObstacle] = dataclasses.field(default_factory=list)


class ConfigurationSpace:
    """Discretized (s, theta) configuration space with obstacle occupancy."""

    def __init__(self, geom: RobotGeometry, bars: list[Obstacle],
                 config: CSpaceConfig = None):
        if config is None:
            config = CSpaceConfig()
        self.config = config
        self.geom = geom
        self.bars = bars

        # Build grid axes
        self.s_axis = np.linspace(config.s_range[0], config.s_range[1], config.s_resolution)
        self.theta_axis = np.linspace(config.theta_range[0], config.theta_range[1], config.theta_resolution)
        self.s_grid, self.theta_grid = np.meshgrid(self.s_axis, self.theta_axis, indexing='ij')

        # Compute occupancy (with safety margin for planning clearance)
        self.occupied = check_collision_grid(
            self.s_grid, self.theta_grid, geom, bars,
            safety_margin=config.safety_margin,
        )

        # Burn in C-space obstacles (rectangles in s, theta space)
        for obs in config.obstacles:
            self.occupied |= (
                (self.s_grid >= obs.s_min) & (self.s_grid <= obs.s_max) &
                (self.theta_grid >= obs.theta_min) & (self.theta_grid <= obs.theta_max)
            )

        # Grid cell sizes for nearest-neighbor lookup
        self._ds = (config.s_range[1] - config.s_range[0]) / (config.s_resolution - 1)
        self._dtheta = (config.theta_range[1] - config.theta_range[0]) / (config.theta_resolution - 1)

    def _to_index(self, s: float, theta: float) -> tuple[int, int]:
        """Convert (s, theta) to nearest grid indices."""
        i = int(round((s - self.config.s_range[0]) / self._ds))
        j = int(round((theta - self.config.theta_range[0]) / self._dtheta))
        i = np.clip(i, 0, self.config.s_resolution - 1)
        j = np.clip(j, 0, self.config.theta_resolution - 1)
        return i, j

    def is_free(self, s: float, theta: float) -> bool:
        """Check if a configuration is collision-free (nearest-neighbor grid lookup)."""
        i, j = self._to_index(s, theta)
        return not self.occupied[i, j]

    def is_edge_free(self, s1: float, theta1: float, s2: float, theta2: float,
                     n_checks: int = None) -> bool:
        """Check if a straight line in C-space is collision-free.

        The number of checks scales with edge length to ensure we never
        step over narrow obstacles (at least 1 check per grid cell).
        """
        if n_checks is None:
            # Scale checks with edge length relative to grid resolution
            ds = abs(s2 - s1) / self._ds
            dt = abs(theta2 - theta1) / self._dtheta
            n_checks = max(20, int(2 * max(ds, dt)))
        for alpha in np.linspace(0, 1, n_checks):
            s = s1 + alpha * (s2 - s1)
            theta = theta1 + alpha * (theta2 - theta1)
            if not self.is_free(s, theta):
                return False
        return True

    def plot(self, ax: plt.Axes = None):
        """Plot the C-space occupancy as a heatmap."""
        if ax is None:
            _, ax = plt.subplots(figsize=(10, 6))

        # occupied.T because meshgrid indexing='ij': rows=s, cols=theta
        # We want s on x-axis, theta on y-axis
        extent = [
            self.config.s_range[0], self.config.s_range[1],
            np.degrees(self.config.theta_range[0]), np.degrees(self.config.theta_range[1]),
        ]
        ax.imshow(
            self.occupied.T,
            origin='lower', aspect='auto', extent=extent,
            cmap='Reds', alpha=0.6, interpolation='nearest',
        )
        ax.set_xlabel('s [m]')
        ax.set_ylabel('theta [deg]')
        ax.set_title('Configuration Space')
        return ax
