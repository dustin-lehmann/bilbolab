"""
Robot Arm Visualization Example
================================

Demonstrates building a simple 3-joint robot arm from BabylonJS primitives:
  - Base rotation (yaw around Z)
  - Shoulder pitch
  - Elbow pitch
  - Gripper open/close

The arm is constructed from boxes (links) and cylinders (joints). Forward
kinematics computes each segment's world position and orientation. Buttons
trigger smooth animated transitions between predefined poses. Sliders allow
manual joint control.

Run from the `software/` directory:
    python -m extensions.gui.examples.babylon.robot_arm_example
"""

import math
import time

import numpy as np
import qmt

from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.sliders import SliderWidget
from extensions.gui.src.lib.objects.python.text import TextWidget
from extensions.libs.babylon.src.babylon import (
    BabylonVisualization,
    BabylonCamera,
    BabylonConfig,
    BabylonScene,
    BabylonLights,
)
from extensions.libs.babylon.src.lib.objects.box.box import Box
from extensions.libs.babylon.src.lib.objects.cylinder.cylinder import Cylinder
from extensions.libs.babylon.src.lib.objects.drawings.path import PathDrawing
from extensions.libs.babylon.src.lib.objects.drawings.points import PointsDrawing
from extensions.libs.babylon.src.lib.objects.floor.checkered_floor import CheckeredFloor
from extensions.libs.babylon.src.lib.objects.laser.laser import LaserLine

logger = Logger('robot_arm')

# ============================================================================
# Arm geometry constants
# ============================================================================
BASE_HEIGHT = 0.08        # Height of the base cylinder
BASE_RADIUS = 0.12        # Radius of the base
UPPER_ARM_LENGTH = 0.50   # Length of the upper arm link
FOREARM_LENGTH = 0.40     # Length of the forearm link
LINK_WIDTH = 0.06         # Cross-section width of arm links
JOINT_RADIUS = 0.035      # Joint cylinder radius
GRIPPER_LENGTH = 0.10     # Gripper finger length
GRIPPER_GAP_OPEN = 0.08   # Gap between fingers when open
GRIPPER_GAP_CLOSED = 0.02 # Gap between fingers when closed

# ============================================================================
# Predefined poses: {name: (base_angle, shoulder_angle, elbow_angle, gripper)}
# Angles in degrees. Shoulder: 0=horizontal, 90=straight up.
# Elbow: 0=straight (continuation), positive=bend down.
# Gripper: 0=closed, 1=open.
# ============================================================================
# Angle convention (from the FK):
#   shoulder: 0 → straight up, 90 → horizontal forward
#   elbow: 0 → straight, positive → bends down, negative → bends up
POSES = {
    'Home':       (0,    15,    10,  0.5),
    'Ready':      (0,    50,    20,  1.0),
    'Pick Left':  (60,   75,    40,  1.0),
    'Grab Left':  (60,   75,    40,  0.0),
    'Pick Right': (-60,  75,    40,  1.0),
    'Grab Right': (-60,  75,    40,  0.0),
    'Place':      (0,    60,    30,  0.0),
    'Release':    (0,    60,    30,  1.0),
    'Reach Up':   (0,     5,     0,  0.5),
    'Reach Fwd':  (0,    85,    10,  1.0),
    'Fold':       (0,    15,  -120,  0.0),
}


def lerp(a, b, t):
    """Linear interpolation between a and b."""
    return a + (b - a) * t


def smoothstep(t):
    """Smooth ease-in-out curve."""
    return t * t * (3 - 2 * t)


class RobotArm:
    """A 3-joint robot arm built from Babylon primitives.

    Manages the 3D objects and computes forward kinematics to position
    each link and joint based on the current joint angles.
    """

    def __init__(self, babylon: BabylonVisualization):
        self.babylon = babylon

        # Current joint state (radians) — matches 'Home' pose
        self.base_angle = 0.0
        self.shoulder_angle = math.radians(15)
        self.elbow_angle = math.radians(10)
        self.gripper_openness = 0.5  # 0=closed, 1=open

        # Animation state
        self._anim_start = None    # (base, shoulder, elbow, gripper) start
        self._anim_end = None      # (base, shoulder, elbow, gripper) target
        self._anim_t0 = 0.0
        self._anim_duration = 0.0

        self._build_objects()

    def _build_objects(self):
        """Create all 3D primitives for the arm."""
        b = self.babylon

        # --- Base platform ---
        self.base = Cylinder('arm_base', color=[0.35, 0.35, 0.4],
                             diameter=BASE_RADIUS * 2, height=BASE_HEIGHT,
                             tessellation=32)
        self.base.setPosition(x=0, y=0, z=BASE_HEIGHT / 2)
        b.addObject(self.base)

        # --- Shoulder joint ---
        self.shoulder_joint = Cylinder('shoulder_joint', color=[0.6, 0.25, 0.1],
                                       diameter=JOINT_RADIUS * 2, height=LINK_WIDTH + 0.02,
                                       tessellation=20)
        b.addObject(self.shoulder_joint)

        # --- Upper arm link ---
        self.upper_arm = Box('upper_arm', color=[0.75, 0.45, 0.15],
                             size={'x': LINK_WIDTH, 'y': LINK_WIDTH, 'z': UPPER_ARM_LENGTH})
        b.addObject(self.upper_arm)

        # --- Elbow joint ---
        self.elbow_joint = Cylinder('elbow_joint', color=[0.6, 0.25, 0.1],
                                    diameter=JOINT_RADIUS * 2, height=LINK_WIDTH + 0.02,
                                    tessellation=20)
        b.addObject(self.elbow_joint)

        # --- Forearm link ---
        self.forearm = Box('forearm', color=[0.6, 0.35, 0.1],
                           size={'x': LINK_WIDTH, 'y': LINK_WIDTH, 'z': FOREARM_LENGTH})
        b.addObject(self.forearm)

        # --- Wrist joint ---
        self.wrist_joint = Cylinder('wrist_joint', color=[0.5, 0.2, 0.08],
                                    diameter=JOINT_RADIUS * 2, height=LINK_WIDTH + 0.02,
                                    tessellation=20)
        b.addObject(self.wrist_joint)

        # --- Gripper fingers (two small boxes) ---
        self.finger_l = Box('finger_l', color=[0.4, 0.4, 0.5],
                            size={'x': 0.015, 'y': LINK_WIDTH * 0.6, 'z': GRIPPER_LENGTH})
        b.addObject(self.finger_l)

        self.finger_r = Box('finger_r', color=[0.4, 0.4, 0.5],
                            size={'x': 0.015, 'y': LINK_WIDTH * 0.6, 'z': GRIPPER_LENGTH})
        b.addObject(self.finger_r)

        # --- End-effector marker (laser line from wrist to tip) ---
        self.tip_laser = LaserLine('tip_laser', color=[1.0, 0.3, 0.3],
                                   width=0.003, glow_intensity=1.5,
                                   start=[0, 0, 0], end=[0, 0, 0])
        b.addObject(self.tip_laser)

        # --- Trail of end-effector ---
        self.trail = PathDrawing('arm_trail',
                                 pathColor=[1.0, 0.5, 0.2, 0.4],
                                 pathWidth=0.006)
        b.addObject(self.trail)

        # --- Target points on the ground ---
        self.targets = PointsDrawing('target_points',
                                     fillColor=[0.3, 1.0, 0.5, 0.8],
                                     pointSize=0.04)
        b.addObject(self.targets)

    def set_joints(self, base_deg=None, shoulder_deg=None, elbow_deg=None, gripper=None):
        """Set joint angles (in degrees) and gripper openness (0-1)."""
        if base_deg is not None:
            self.base_angle = math.radians(base_deg)
        if shoulder_deg is not None:
            self.shoulder_angle = math.radians(shoulder_deg)
        if elbow_deg is not None:
            self.elbow_angle = math.radians(elbow_deg)
        if gripper is not None:
            self.gripper_openness = max(0.0, min(1.0, gripper))

    def get_joints_deg(self):
        """Return current joint angles in degrees + gripper."""
        return (
            math.degrees(self.base_angle),
            math.degrees(self.shoulder_angle),
            math.degrees(self.elbow_angle),
            self.gripper_openness,
        )

    def animate_to_pose(self, pose_name: str, duration: float = 1.5):
        """Start a smooth animation to a named pose."""
        if pose_name not in POSES:
            logger.warning(f'Unknown pose: {pose_name}')
            return
        target = POSES[pose_name]
        self._anim_start = self.get_joints_deg()
        self._anim_end = target
        self._anim_t0 = time.time()
        self._anim_duration = duration
        logger.info(f'Animating to "{pose_name}"')

    def tick(self):
        """Advance animation (if active) and update the 3D scene."""
        # Handle animation interpolation
        if self._anim_end is not None:
            elapsed = time.time() - self._anim_t0
            t = min(1.0, elapsed / max(self._anim_duration, 0.01))
            t_smooth = smoothstep(t)

            base = lerp(self._anim_start[0], self._anim_end[0], t_smooth)
            shoulder = lerp(self._anim_start[1], self._anim_end[1], t_smooth)
            elbow = lerp(self._anim_start[2], self._anim_end[2], t_smooth)
            grip = lerp(self._anim_start[3], self._anim_end[3], t_smooth)

            self.set_joints(base, shoulder, elbow, grip)

            if t >= 1.0:
                self._anim_end = None

        self._update_fk()

    def _update_fk(self):
        """Compute forward kinematics and update all 3D object positions.

        All rotations are built in local frame and composed via qmult.
        Convention: qmt.qmult(q2, q1) applies q1 first, then q2.
        Boxes have their Z-axis along the link direction by default.
        Cylinders (joints) have Z along their axis, so we rotate them
        to lie along the pitch axis (perpendicular to the arm plane).
        """
        up = np.array([0.0, 0.0, 1.0])
        local_y = np.array([0.0, 1.0, 0.0])
        local_x = np.array([1.0, 0.0, 0.0])

        # --- Base yaw (rotation around world Z) ---
        q_base = qmt.quatFromAngleAxis(self.base_angle, up)

        # --- Shoulder pitch (rotation around local Y, after base yaw) ---
        q_pitch_sh = qmt.quatFromAngleAxis(self.shoulder_angle, local_y)
        # Combined orientation after base + shoulder
        q_upper = qmt.qmult(q_base, q_pitch_sh)

        # --- Elbow pitch (rotation around local Y, relative to upper arm) ---
        q_pitch_el = qmt.quatFromAngleAxis(self.elbow_angle, local_y)
        # Combined orientation after base + shoulder + elbow
        q_fore = qmt.qmult(q_upper, q_pitch_el)

        # --- Joint cylinder orientation (axis along local Y after base yaw) ---
        # Cylinder default axis is Z; rotate 90° around local X to point along Y
        q_cyl_tilt = qmt.quatFromAngleAxis(math.pi / 2, local_x)
        q_joint_sh = qmt.qmult(q_base, q_cyl_tilt)
        q_joint_el = qmt.qmult(q_upper, q_cyl_tilt)
        q_joint_wr = qmt.qmult(q_fore, q_cyl_tilt)

        # --- Positions via forward kinematics ---
        shoulder_pos = np.array([0.0, 0.0, BASE_HEIGHT])

        upper_arm_dir = qmt.rotate(q_upper, up)
        upper_arm_center = shoulder_pos + upper_arm_dir * (UPPER_ARM_LENGTH / 2)
        elbow_pos = shoulder_pos + upper_arm_dir * UPPER_ARM_LENGTH

        forearm_dir = qmt.rotate(q_fore, up)
        forearm_center = elbow_pos + forearm_dir * (FOREARM_LENGTH / 2)
        wrist_pos = elbow_pos + forearm_dir * FOREARM_LENGTH
        tip_pos = wrist_pos + forearm_dir * GRIPPER_LENGTH

        # --- Update shoulder joint ---
        self.shoulder_joint.setPosition(x=shoulder_pos[0], y=shoulder_pos[1], z=shoulder_pos[2])
        self.shoulder_joint.setOrientation(quat=q_joint_sh.tolist())

        # --- Update upper arm ---
        self.upper_arm.setPosition(x=upper_arm_center[0], y=upper_arm_center[1], z=upper_arm_center[2])
        self.upper_arm.setOrientation(quat=q_upper.tolist())

        # --- Update elbow joint ---
        self.elbow_joint.setPosition(x=elbow_pos[0], y=elbow_pos[1], z=elbow_pos[2])
        self.elbow_joint.setOrientation(quat=q_joint_el.tolist())

        # --- Update forearm ---
        self.forearm.setPosition(x=forearm_center[0], y=forearm_center[1], z=forearm_center[2])
        self.forearm.setOrientation(quat=q_fore.tolist())

        # --- Update wrist joint ---
        self.wrist_joint.setPosition(x=wrist_pos[0], y=wrist_pos[1], z=wrist_pos[2])
        self.wrist_joint.setOrientation(quat=q_joint_wr.tolist())

        # --- Update gripper fingers ---
        grip_gap = lerp(GRIPPER_GAP_CLOSED, GRIPPER_GAP_OPEN, self.gripper_openness)
        # Offset fingers perpendicular to the arm plane (along local X)
        side_axis = qmt.rotate(q_fore, local_x)
        finger_center = wrist_pos + forearm_dir * (GRIPPER_LENGTH / 2)

        self.finger_l.setPosition(
            x=finger_center[0] + side_axis[0] * grip_gap / 2,
            y=finger_center[1] + side_axis[1] * grip_gap / 2,
            z=finger_center[2] + side_axis[2] * grip_gap / 2)
        self.finger_l.setOrientation(quat=q_fore.tolist())

        self.finger_r.setPosition(
            x=finger_center[0] - side_axis[0] * grip_gap / 2,
            y=finger_center[1] - side_axis[1] * grip_gap / 2,
            z=finger_center[2] - side_axis[2] * grip_gap / 2)
        self.finger_r.setOrientation(quat=q_fore.tolist())

        # --- Laser line from wrist to tip ---
        self.tip_laser.setPoints(
            start=wrist_pos.tolist(),
            end=tip_pos.tolist())

        # --- Trail ---
        self.trail.addPoint(tip_pos[0], tip_pos[1])
        if len(self.trail._points) > 800:
            self.trail._points = self.trail._points[-500:]


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    # Forward logs to GUI terminal
    def _log_to_gui(log_entry, log, log_logger, level):
        text = f'[{log_logger.name}] {log}'
        color = [c / 255 for c in LOGGING_COLORS[level]]
        app.print(text, color=color)

    addLogRedirection(_log_to_gui, minimum_level='INFO')

    category = Category(id='robot_arm', name='Robot Arm', icon='R')
    app.addCategory(category)

    page = Page(id='main', name='Arm Control')
    category.addPage(page, position=1)

    # =========================================================================
    # Babylon scene
    # =========================================================================
    babylon_widget = BabylonWidget(widget_id='arm_view')

    config = BabylonConfig(
        camera=BabylonCamera(
            name='Default',
            target=[0, 0, 0.3],
            alpha=math.radians(-40),
            beta=math.radians(60),
            radius=2.0,
            fov=math.radians(55),
            radius_upper_limit=6.0,
        ),
        scene=BabylonScene(add_fog=True, fog_density=0.04),
        lights=BabylonLights(
            directional_shadows=True,
            directional_shadow_darkness=0.3,
        ),
        show_coordinate_system=True,
        coordinate_system_length=0.1,
    )
    babylon = BabylonVisualization(id='babylon', config=config)
    babylon_widget.set_babylon(babylon)
    page.addWidget(babylon_widget, row=1, column=1, width=28, height=16)

    # Floor
    floor = CheckeredFloor('floor', tile_size=0.3, tiles_x=10, tiles_y=10,
                           color1=[0.38, 0.38, 0.38], color2=[0.48, 0.48, 0.48],
                           border_width=0.015)
    babylon.addObject(floor)

    # Build the arm
    arm = RobotArm(babylon)

    # Place target markers on the ground for the predefined pick/place spots
    target_pts = []
    for pose_name in ['Pick Left', 'Pick Right', 'Place']:
        base_deg, sh_deg, el_deg, _ = POSES[pose_name]
        # Approximate ground projection: reach * cos(base)
        reach = (UPPER_ARM_LENGTH * math.cos(math.radians(sh_deg))
                 + FOREARM_LENGTH * math.cos(math.radians(sh_deg + el_deg)))
        bx = reach * math.cos(math.radians(base_deg))
        by = reach * math.sin(math.radians(base_deg))
        target_pts.append([bx, by])
    arm.targets.setPoints(target_pts)

    # =========================================================================
    # Status text
    # =========================================================================
    status_text = TextWidget(
        widget_id='status',
        text='Pose: Home',
        font_size=12,
        horizontal_alignment='left',
        vertical_alignment='top',
        text_color=[0.7, 0.9, 0.7],
    )
    page.addWidget(status_text, row=1, column=29, width=12, height=2)

    joint_text = TextWidget(
        widget_id='joints',
        text='Base: 0.0\nShoulder: 15.0\nElbow: 10.0\nGripper: 50%',
        font_size=10,
        horizontal_alignment='left',
        vertical_alignment='top',
        text_color=[0.6, 0.7, 0.8],
    )
    page.addWidget(joint_text, row=3, column=29, width=12, height=4)

    # =========================================================================
    # Pose buttons
    # =========================================================================
    pose_buttons = [
        ('Home', [0.3, 0.3, 0.4]),
        ('Ready', [0.2, 0.4, 0.3]),
        ('Pick Left', [0.4, 0.3, 0.15]),
        ('Grab Left', [0.5, 0.2, 0.1]),
        ('Pick Right', [0.15, 0.3, 0.4]),
        ('Grab Right', [0.1, 0.2, 0.5]),
        ('Place', [0.3, 0.15, 0.4]),
        ('Release', [0.4, 0.2, 0.4]),
        ('Reach Up', [0.2, 0.35, 0.5]),
        ('Reach Fwd', [0.35, 0.35, 0.2]),
        ('Fold', [0.35, 0.25, 0.25]),
    ]

    row_start = 7
    for i, (pose_name, color) in enumerate(pose_buttons):
        r = row_start + (i // 2) * 2
        c = 29 + (i % 2) * 6
        btn = Button(
            widget_id=f'pose_{pose_name.lower().replace(" ", "_")}',
            text=pose_name, color=color)
        page.addWidget(btn, row=r, column=c, width=6, height=2)

        def make_cb(name):
            def cb(*args, **kwargs):
                arm.animate_to_pose(name, duration=1.2)
                status_text.updateConfig(text=f'Pose: {name}')
            return cb

        btn.callbacks.click.register(make_cb(pose_name))

    # =========================================================================
    # Manual joint sliders (on a second page)
    # =========================================================================
    page_manual = Page(id='manual', name='Manual Control')
    category.addPage(page_manual, position=2)

    babylon_widget2 = BabylonWidget(widget_id='arm_view_2')
    babylon_widget2.set_babylon(babylon)
    page_manual.addWidget(babylon_widget2, row=1, column=1, width=28, height=16)

    manual_state = {'active': False}

    slider_base = SliderWidget(
        widget_id='sl_base', min_value=-180, max_value=180, increment=1, value=0,
        color=[0.5, 0.3, 0.3], continuousUpdates=True, title='Base (deg)')
    page_manual.addWidget(slider_base, row=1, column=29, width=12, height=2)

    slider_shoulder = SliderWidget(
        widget_id='sl_shoulder', min_value=-10, max_value=120, increment=1, value=15,
        color=[0.3, 0.5, 0.3], continuousUpdates=True, title='Shoulder (deg)')
    page_manual.addWidget(slider_shoulder, row=3, column=29, width=12, height=2)

    slider_elbow = SliderWidget(
        widget_id='sl_elbow', min_value=-130, max_value=160, increment=1, value=10,
        color=[0.3, 0.3, 0.5], continuousUpdates=True, title='Elbow (deg)')
    page_manual.addWidget(slider_elbow, row=5, column=29, width=12, height=2)

    slider_gripper = SliderWidget(
        widget_id='sl_gripper', min_value=0, max_value=1.0, increment=0.05, value=0.5,
        color=[0.4, 0.4, 0.3], continuousUpdates=True, title='Gripper')
    page_manual.addWidget(slider_gripper, row=7, column=29, width=12, height=2)

    def on_base(v, *a, **kw):
        manual_state['active'] = True
        arm._anim_end = None  # cancel any running animation
        arm.set_joints(base_deg=v)

    def on_shoulder(v, *a, **kw):
        manual_state['active'] = True
        arm._anim_end = None
        arm.set_joints(shoulder_deg=v)

    def on_elbow(v, *a, **kw):
        manual_state['active'] = True
        arm._anim_end = None
        arm.set_joints(elbow_deg=v)

    def on_gripper(v, *a, **kw):
        manual_state['active'] = True
        arm._anim_end = None
        arm.set_joints(gripper=v)

    slider_base.callbacks.value_changed.register(on_base)
    slider_shoulder.callbacks.value_changed.register(on_shoulder)
    slider_elbow.callbacks.value_changed.register(on_elbow)
    slider_gripper.callbacks.value_changed.register(on_gripper)

    # Clear trail button on manual page
    btn_clear_trail = Button(widget_id='clear_trail', text='Clear Trail',
                             color=[0.4, 0.25, 0.2])
    page_manual.addWidget(btn_clear_trail, row=9, column=29, width=6, height=2)
    btn_clear_trail.callbacks.click.register(
        lambda *a, **kw: arm.trail.clearPoints())

    joint_text2 = TextWidget(
        widget_id='joints2',
        text='',
        font_size=10,
        horizontal_alignment='left',
        vertical_alignment='top',
        text_color=[0.6, 0.7, 0.8],
    )
    page_manual.addWidget(joint_text2, row=11, column=29, width=12, height=4)

    # =========================================================================
    # Start
    # =========================================================================
    babylon.start()

    # Camera presets
    babylon.add_camera(BabylonCamera(
        name='Side', target=[0, 0, 0.3],
        alpha=math.radians(-90), beta=math.radians(75), radius=2.0,
        radius_upper_limit=6.0))
    babylon.add_camera(BabylonCamera(
        name='Top', target=[0, 0, 0],
        alpha=0, beta=math.radians(5), radius=2.5,
        radius_upper_limit=6.0))
    babylon.add_camera(BabylonCamera(
        name='Front', target=[0, 0, 0.3],
        alpha=math.radians(0), beta=math.radians(80), radius=2.0,
        radius_upper_limit=6.0))

    app.start()

    # =========================================================================
    # Main loop
    # =========================================================================
    update_counter = 0
    while True:
        arm.tick()

        # Push trail update periodically
        update_counter += 1
        if update_counter % 10 == 0:
            arm.trail.update()

        # Update joint readout
        if update_counter % 5 == 0:
            b, s, e, g = arm.get_joints_deg()
            text = (f'Base:     {b:+.1f} deg\n'
                    f'Shoulder: {s:+.1f} deg\n'
                    f'Elbow:    {e:+.1f} deg\n'
                    f'Gripper:  {g:.0%}')
            joint_text.updateConfig(text=text)
            joint_text2.updateConfig(text=text)

        time.sleep(0.03)


if __name__ == '__main__':
    main()
