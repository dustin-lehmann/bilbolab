import dataclasses

import numpy as np
import qmt

from core.utils.dataclass_utils import update_dataclass_from_dict
from core.utils.dict_utils import update_dict
from extensions.libs.babylon.src.babylon import BabylonObject


@dataclasses.dataclass
class BoxData:
    x: float = 0
    y: float = 0
    z: float = 0
    orientation: np.ndarray = dataclasses.field(default_factory=lambda: np.asarray([1, 0, 0, 0]))


class Box(BabylonObject):
    type = 'box'

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, object_id: str, **kwargs):

        super().__init__(object_id, **kwargs)
        default_config = {
            'color': [1, 0, 0],
            'size': {'x': 1, 'y': 1, 'z': 1},
            'texture': '',
            'texture_uscale': 1,
            'texture_vscale': 1,
            'wireframe': False,
            'accept_shadows': True,
        }
        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)
        self.data = BoxData()
        update_dataclass_from_dict(self.data, kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def setPosition(self, x=None, y=None, z=None):
        if x is not None:
            self.data.x = x
        if y is not None:
            self.data.y = y
        if z is not None:
            self.data.z = z
        self.update()

    # ------------------------------------------------------------------------------------------------------------------
    def setOrientation(self, quat=None):
        if quat is not None:
            self.data.orientation = np.asarray(quat, dtype=float)
            self.update()
    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self) -> dict:
        config = {
            **self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self) -> dict:
        data = {
            'position': {
                'x': self.data.x,
                'y': self.data.y,
                'z': self.data.z,
            },
            'orientation': self.data.orientation.tolist(),
        }
        return data


# === WALL =============================================================================================================
@dataclasses.dataclass
class WallData:
    """
    Bottom-anchored position (x, y, z_bottom) and quaternion orientation [w, x, y, z].
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0  # bottom z (the JS side lifts by +height/2 internally)
    orientation: np.ndarray = dataclasses.field(default_factory=lambda: np.asarray([1, 0, 0, 0]))


# === WALL (matches BabylonWall) ======================================================================================

class Wall(BabylonObject):
    """
    Python-side wall object. Matches the JS BabylonWall behavior:

    - Primary geometric config is given by: length (x), thickness (y), height (z).
    - If include_end_caps=True, the *effective* rendered length is length + 2*thickness.
    - Position is specified at the *bottom* of the wall (we just store it; JS shifts by +height/2).
    - Auto texture uScale can be enabled to keep texels roughly square based on length/height.
    """
    type = 'wall'

    def __init__(self, object_id: str, **kwargs):
        super().__init__(object_id, **kwargs)

        # Generic rendering defaults (kept similar to your Box for consistency)
        # Note: we keep accept_shadows default True on Python side, like your Box.
        generic_defaults = {
            'color': [0.5, 0.5, 0.5],
            'texture': '',
            # If texture_uscale is None and auto_texture_uscale=True, it will be computed from length/height.
            'texture_uscale': None,
            'texture_vscale': 1,
            'wireframe': False,
            'wireframe_width': 0.75,
            'wireframe_color': [1, 0, 0, 1],
            'alpha': 1,
            'accept_shadows': True,
        }

        # Wall-specific defaults (preferred API)
        wall_defaults = {
            'length': 1.0,  # along X
            'height': 0.25,  # along Z (up in your coords)
            'thickness': 0.02,  # along Y (depth)
            'include_end_caps': False,  # adds one thickness to each end
            'auto_texture_uscale': True,  # compute uScale ~ length/height if texture present and user didn't set uScale
        }

        # Merge incoming kwargs into config (allow adding keys)
        self.config = update_dict({}, generic_defaults, wall_defaults, kwargs, allow_add=True)

        # Prefer new names (length/height/thickness); fall back to size.{x,y,z} if provided
        incoming = kwargs.get('config', kwargs)  # support both flat kwargs or kwargs['config'] style
        size_in = (incoming.get('size') or {}) if isinstance(incoming, dict) else {}

        def _pick(pref_key, size_key, default_val):
            if pref_key in self.config and self.config[pref_key] is not None:
                return self.config[pref_key]
            if size_key in size_in and size_in[size_key] is not None:
                return size_in[size_key]
            return default_val

        self._length = _pick('length', 'x', wall_defaults['length'])
        self._height = _pick('height', 'z', wall_defaults['height'])
        self._thickness = _pick('thickness', 'y', wall_defaults['thickness'])
        self._include_end_caps = bool(self.config.get('include_end_caps', wall_defaults['include_end_caps']))
        self._auto_tex = bool(self.config.get('auto_texture_uscale', wall_defaults['auto_texture_uscale']))

        # Data (bottom-anchored)
        self.data = WallData()
        update_dataclass_from_dict(self.data, kwargs)

        # Ensure we push initial config/data to frontend when attached
        self.updateConfig()
        self.update()

    # ------------------------------------------------------------------------------------------------------------------
    def _effective_length(self) -> float:
        """
        Adds one thickness to each end when include_end_caps is True.
        """
        return float(self._length + (2 * self._thickness if self._include_end_caps else 0.0))

    # ------------------------------------------------------------------------------------------------------------------
    def _computed_size_dict(self) -> dict:
        """
        What BabylonBox expects: x=length, y=thickness, z=height.
        """
        return {
            'x': self._effective_length(),
            'y': float(self._thickness),
            'z': float(self._height),
        }

    # ------------------------------------------------------------------------------------------------------------------
    def setPosition(self, x=None, y=None, z=None):
        """
        Set the *bottom* anchor position. The JS wall lifts its internal center by +height/2.
        """
        if x is not None:
            self.data.x = x
        if y is not None:
            self.data.y = y
        if z is not None:
            self.data.z = z
        self.update()

    # ------------------------------------------------------------------------------------------------------------------
    def setOrientation(self, quat=None):
        """
        Set orientation as a quaternion [w, x, y, z].
        """
        if quat is not None:
            self.data.orientation = np.asarray(quat, dtype=float)
        self.update()

    # ------------------------------------------------------------------------------------------------------------------
    def setAngle(self, angle: float):
        quat = qmt.quatFromAngleAxis(angle, [0, 0, 1])
        self.setOrientation(quat)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self) -> dict:
        """
        Serialize config for the frontend BabylonWall (which in turn constructs a BabylonBox with mapped size).
        """
        cfg = {
            **self.config,
            # Always provide a size that reflects the preferred (length/height/thickness) mapping:
            'size': self._computed_size_dict(),
            # And also include the explicit LH T fields for clarity/debugging (frontend may ignore).
            'length': float(self._length),
            'height': float(self._height),
            'thickness': float(self._thickness),
            'include_end_caps': self._include_end_caps,
            'auto_texture_uscale': self._auto_tex,
        }

        # Auto-compute texture uScale if desired and if a texture is present and user didn't set one.
        if cfg.get('texture') and self._auto_tex and (cfg.get('texture_uscale') in (None, '', 0)):
            h = max(float(self._height), 1e-9)
            cfg['texture_uscale'] = float(self._effective_length() / h)

        # Ensure numbers are plain Python types (useful for JSON serialization)
        return cfg

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self) -> dict:
        """
        Bottom-anchored position + quaternion orientation.
        """
        return {
            'position': {
                'x': float(self.data.x),
                'y': float(self.data.y),
                'z': float(self.data.z),  # bottom; JS object shifts internally by +height/2
            },
            'orientation': self.data.orientation.tolist(),
        }


# === WALL FANCY (matches BabylonWall_Fancy) ==========================================================================
class WallFancy(Wall):
    """
    Fancy wall variant that mirrors BabylonWall_Fancy:

    - Inherits all Wall behavior (bottom-anchored, include_end_caps, auto uScale).
    - Adds visual refinements: subtle edge highlight, normal map + optional parallax, decorative caps.
    """
    type = 'wall_fancy'

    def __init__(self, object_id: str, **kwargs):
        # Fancy-specific defaults from your JS with sensible Python-side equivalents
        fancy_defaults = {
            # Edge highlight (independent of wireframe)
            'edge_highlight': True,
            'edge_width': 0.6,
            'edge_color': [0, 0, 0, 0.35],  # RGBA

            # Surface detail
            'normal_map': '',
            'bump_uscale_matches_diffuse': True,
            'use_parallax': False,
            'use_parallax_occlusion': False,
            'parallax_scale_bias': 0.03,
            'specular_power': 128,

            # Decorative caps (top/bottom)
            'cap_top_enabled': True,
            'cap_top_height': 0.02,
            'cap_top_overhang': 0.005,
            'cap_top_texture': '',

            'cap_bottom_enabled': False,
            'cap_bottom_height': 0.02,
            'cap_bottom_overhang': 0.005,
            'cap_bottom_texture': '',

            # Shadow reception for extra pieces
            'caps_accept_shadows': True,
        }

        # Blend fancy defaults into kwargs/config before calling Wall.__init__
        merged = update_dict({}, fancy_defaults, kwargs, allow_add=True)
        super().__init__(object_id, **merged)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self) -> dict:
        """
        Extend Wall.getConfig() with fancy visual options so the JS BabylonWall_Fancy
        can apply normal maps, edge highlight, caps, etc.
        """
        cfg = super().getConfig()

        # Ensure all fancy keys exist (some may have been added by user overrides)
        # (Using setdefault to avoid overwriting any values already present in cfg)
        fancy_keys = {
            'edge_highlight': True,
            'edge_width': 0.6,
            'edge_color': [0, 0, 0, 0.35],
            'normal_map': '',
            'bump_uscale_matches_diffuse': True,
            'use_parallax': False,
            'use_parallax_occlusion': False,
            'parallax_scale_bias': 0.03,
            'specular_power': 128,
            'cap_top_enabled': True,
            'cap_top_height': 0.02,
            'cap_top_overhang': 0.005,
            'cap_top_texture': '',
            'cap_bottom_enabled': False,
            'cap_bottom_height': 0.02,
            'cap_bottom_overhang': 0.005,
            'cap_bottom_texture': '',
            'caps_accept_shadows': True,
        }
        for k, v in fancy_keys.items():
            cfg.setdefault(k, v)

        return cfg
