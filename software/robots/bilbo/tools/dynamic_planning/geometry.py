"""Robot body geometry and collision checking for limbo bar passage."""

import dataclasses

import numpy as np


@dataclasses.dataclass
class RobotGeometry:
    """Physical dimensions of the BILBO robot body (side view)."""
    body_height: float  # Height of the body above the wheel axle [m]
    body_width: float   # Width (depth) of the body in the sagittal plane [m]
    wheel_radius: float  # Wheel radius [m]


@dataclasses.dataclass
class LimboBar:
    """Circular cross-section limbo bar obstacle."""
    x: float        # Horizontal position of bar center [m]
    z: float        # Vertical position of bar center [m]
    diameter: float  # Bar diameter [m]

    @classmethod
    def from_clearance(cls, x: float, ground_clearance: float, diameter: float) -> 'LimboBar':
        """Create a bar from ground clearance (bottom of bar to floor).

        The bar center is at z = ground_clearance + diameter/2.
        """
        return cls(x=x, z=ground_clearance + diameter / 2, diameter=diameter)

    @property
    def radius(self) -> float:
        return self.diameter / 2


@dataclasses.dataclass
class LimboRectangle:
    """Axis-aligned rectangular obstacle in the world frame (side view).

    Defined by center position and full width/height.
    """
    x: float        # Horizontal position of rectangle center [m]
    z: float        # Vertical position of rectangle center [m]
    width: float    # Full width in x direction [m]
    height: float   # Full height in z direction [m]

    @classmethod
    def from_clearance(cls, x: float, ground_clearance: float,
                       width: float, height: float) -> 'LimboRectangle':
        """Create a rectangle from ground clearance (bottom edge to floor).

        The rectangle center is at z = ground_clearance + height/2.
        """
        return cls(x=x, z=ground_clearance + height / 2, width=width, height=height)

    @property
    def x_min(self) -> float:
        return self.x - self.width / 2

    @property
    def x_max(self) -> float:
        return self.x + self.width / 2

    @property
    def z_min(self) -> float:
        return self.z - self.height / 2

    @property
    def z_max(self) -> float:
        return self.z + self.height / 2


# Union type for all supported obstacles
Obstacle = LimboBar | LimboRectangle


def get_body_corners(s: float, theta: float, geom: RobotGeometry) -> np.ndarray:
    """Compute the 4 world-frame corners of the robot body.

    The body is a rectangle attached to the wheel axle at (s, r_w).
    In the body frame, it spans [-w/2, w/2] x [0, h] with origin at the axle.
    Positive theta leans the body forward (clockwise in side view).

    Returns:
        (4, 2) array of (x, z) corners in world frame.
    """
    w = geom.body_width
    h = geom.body_height

    # Body-frame corners (origin at axle): bottom-left, bottom-right, top-right, top-left
    local = np.array([
        [-w / 2, 0],
        [ w / 2, 0],
        [ w / 2, h],
        [-w / 2, h],
    ])

    # Rotation matrix: positive theta rotates clockwise in side view (x-z plane)
    c, sn = np.cos(theta), np.sin(theta)
    R = np.array([[ c, sn],
                  [-sn, c]])

    # Rotate and translate to world frame (axle at (s, wheel_radius))
    world = (R @ local.T).T + np.array([s, geom.wheel_radius])
    return world


def check_collision(s: float, theta: float, geom: RobotGeometry, obstacle: Obstacle,
                    safety_margin: float = 0.0) -> bool:
    """Check if the robot body at (s, theta) collides with an obstacle.

    Supports both circular (LimboBar) and rectangular (LimboRectangle) obstacles.

    Args:
        safety_margin: Extra clearance added around the obstacle [m].
    """
    if isinstance(obstacle, LimboBar):
        return _check_collision_circle(s, theta, geom, obstacle, safety_margin)
    elif isinstance(obstacle, LimboRectangle):
        return _check_collision_rect(s, theta, geom, obstacle, safety_margin)
    else:
        raise TypeError(f"Unknown obstacle type: {type(obstacle)}")


def _check_collision_circle(s: float, theta: float, geom: RobotGeometry,
                            bar: LimboBar, safety_margin: float) -> bool:
    """Circle-vs-rectangle test in body local frame."""
    ax_x, ax_z = s, geom.wheel_radius
    dx = bar.x - ax_x
    dz = bar.z - ax_z

    c, sn = np.cos(theta), np.sin(theta)
    local_x = c * dx - sn * dz
    local_z = sn * dx + c * dz

    w = geom.body_width
    h = geom.body_height

    nearest_x = np.clip(local_x, -w / 2, w / 2)
    nearest_z = np.clip(local_z, 0, h)

    dist_sq = (local_x - nearest_x) ** 2 + (local_z - nearest_z) ** 2
    effective_radius = bar.radius + safety_margin
    return dist_sq < effective_radius ** 2


def _check_collision_rect(s: float, theta: float, geom: RobotGeometry,
                          rect: LimboRectangle, safety_margin: float) -> bool:
    """Rectangle-vs-rectangle overlap via Separating Axis Theorem (SAT).

    The obstacle rectangle is axis-aligned in the world frame. The robot body
    is rotated by theta. We test all 4 potential separating axes (2 from each
    rectangle's edges).
    """
    body_corners = get_body_corners(s, theta, geom)

    # Inflate obstacle by safety margin
    ox_min = rect.x_min - safety_margin
    ox_max = rect.x_max + safety_margin
    oz_min = rect.z_min - safety_margin
    oz_max = rect.z_max + safety_margin

    obs_corners = np.array([
        [ox_min, oz_min],
        [ox_max, oz_min],
        [ox_max, oz_max],
        [ox_min, oz_max],
    ])

    # SAT axes: 2 from obstacle (world-aligned) + 2 from body (rotated)
    c, sn = np.cos(theta), np.sin(theta)
    axes = [
        np.array([1.0, 0.0]),   # obstacle x-axis
        np.array([0.0, 1.0]),   # obstacle z-axis
        np.array([c, -sn]),     # body local x-axis
        np.array([sn, c]),      # body local z-axis (up along body)
    ]

    for axis in axes:
        proj_body = body_corners @ axis
        proj_obs = obs_corners @ axis
        if proj_body.max() < proj_obs.min() or proj_obs.max() < proj_body.min():
            return False  # Separating axis found → no collision

    return True  # No separating axis → collision


def check_collision_grid(s_grid: np.ndarray, theta_grid: np.ndarray,
                         geom: RobotGeometry, obstacles: list[Obstacle],
                         safety_margin: float = 0.0) -> np.ndarray:
    """Vectorized collision check over a meshgrid of (s, theta) values.

    Args:
        s_grid: 2D array of s values (from meshgrid).
        theta_grid: 2D array of theta values (from meshgrid).
        geom: Robot geometry.
        obstacles: List of obstacles (LimboBar and/or LimboRectangle).
        safety_margin: Extra clearance added around obstacles [m].

    Returns:
        Boolean 2D array, True where collision occurs.
    """
    occupied = np.zeros(s_grid.shape, dtype=bool)

    w = geom.body_width
    h = geom.body_height

    c = np.cos(theta_grid)
    sn = np.sin(theta_grid)

    for obs in obstacles:
        if isinstance(obs, LimboBar):
            dx = obs.x - s_grid
            dz = obs.z - geom.wheel_radius

            local_x = c * dx - sn * dz
            local_z = sn * dx + c * dz

            nearest_x = np.clip(local_x, -w / 2, w / 2)
            nearest_z = np.clip(local_z, 0, h)

            dist_sq = (local_x - nearest_x) ** 2 + (local_z - nearest_z) ** 2
            effective_radius = obs.radius + safety_margin
            occupied |= dist_sq < effective_radius ** 2

        elif isinstance(obs, LimboRectangle):
            # Vectorized SAT for axis-aligned obstacle vs rotated body
            ox_min = obs.x_min - safety_margin
            ox_max = obs.x_max + safety_margin
            oz_min = obs.z_min - safety_margin
            oz_max = obs.z_max + safety_margin

            # Body corners in local frame (origin at axle)
            body_local = np.array([
                [-w / 2, 0],
                [ w / 2, 0],
                [ w / 2, h],
                [-w / 2, h],
            ])

            # For each grid point, rotate and translate all 4 corners
            # body_world[corner, grid_i, grid_j, xy]
            for corner in body_local:
                cx = c * corner[0] + sn * corner[1] + s_grid
                cz = -sn * corner[0] + c * corner[1] + geom.wheel_radius

                # If any body corner is inside the inflated obstacle rect,
                # that's a sufficient (not necessary) collision indicator.
                # For full SAT we need all 4 axes, but checking corner-in-rect
                # plus obstacle-corner-in-body covers most cases.
                inside = (cx >= ox_min) & (cx <= ox_max) & (cz >= oz_min) & (cz <= oz_max)
                occupied |= inside

            # Also check obstacle corners inside body (in body-local frame)
            for ocx, ocz in [(ox_min, oz_min), (ox_max, oz_min),
                             (ox_max, oz_max), (ox_min, oz_max)]:
                dx = ocx - s_grid
                dz = ocz - geom.wheel_radius
                local_x = c * dx - sn * dz
                local_z = sn * dx + c * dz
                inside = (local_x >= -w / 2) & (local_x <= w / 2) & (local_z >= 0) & (local_z <= h)
                occupied |= inside

    return occupied
