import dataclasses
from typing import Sequence

import matplotlib.collections as mcollections
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import numpy as np

from core.utils.dataclass_utils import update_dataclass_from_dict


# ======================================================================================================================
# === BILBO MODEL (Visual Dimensions) =================================================================================
@dataclasses.dataclass
class Plotted_BILBO_Model:
    wheel_radius: float = 0.06
    wheel_inner_ratio: float = 0.65  # Inner wheel radius as fraction of outer
    body_height: float = 0.185
    body_width: float = 0.085
    body_corner_radius: float = 0.005


# ======================================================================================================================
# === BILBO VISUAL CONFIG ==============================================================================================
@dataclasses.dataclass
class Plotted_BILBO_Config:
    model: Plotted_BILBO_Model = dataclasses.field(default_factory=Plotted_BILBO_Model)
    tire_color: str | list | tuple = 'black'
    tire_linewidth: float = 1.5
    wheel_color: str | list | tuple = 'white'
    wheel_edge_color: str | list | tuple = (0.3, 0.3, 0.3)
    wheel_linewidth: float = 1.0
    body_color: str | list | tuple = (0.3, 0.5, 0.9)
    body_edge_color: str | list | tuple = 'black'
    body_linewidth: float = 1.5
    body_opacity: float = 0.9
    zorder: int = 10


# ======================================================================================================================
# === BILBO STATE ======================================================================================================
@dataclasses.dataclass
class Plotted_BILBO_State:
    x: float = 0.0      # Forward/backward position of wheel midpoint [m]
    theta: float = 0.0   # Pitch angle [rad], 0 = upright, positive = leaning forward


# ======================================================================================================================
# === PLOTTED BILBO ====================================================================================================
class Plotted_BILBO:
    """A single BILBO robot element for 2D side-view plotting."""

    def __init__(self, config: Plotted_BILBO_Config = None, state: Plotted_BILBO_State = None, **kwargs):
        if config is None:
            config = Plotted_BILBO_Config()
        self.config = config
        if kwargs:
            update_dataclass_from_dict(self.config, kwargs)

        if state is None:
            state = Plotted_BILBO_State()
        self.state = state

        self._tire_artist: mpatches.Circle | None = None
        self._wheel_artist: mpatches.Circle | None = None
        self._body_artist: mpatches.FancyBboxPatch | None = None
        self._ax: plt.Axes | None = None
        self._drawn = False

    # ------------------------------------------------------------------------------------------------------------------
    def set_state(self, x: float = None, theta: float = None):
        if x is not None:
            self.state.x = x
        if theta is not None:
            self.state.theta = theta

    # ------------------------------------------------------------------------------------------------------------------
    def draw(self, ax: plt.Axes):
        """Draw or update the BILBO on the given axes."""
        model = self.config.model
        cfg = self.config

        cx = self.state.x
        cy = model.wheel_radius

        if not self._drawn:
            self._ax = ax

            # Tire (outer circle, filled black)
            self._tire_artist = mpatches.Circle(
                (cx, cy), model.wheel_radius,
                facecolor=cfg.tire_color,
                edgecolor=cfg.tire_color,
                linewidth=cfg.tire_linewidth,
                zorder=cfg.zorder,
            )
            ax.add_patch(self._tire_artist)

            # Wheel (inner circle)
            inner_r = model.wheel_radius * model.wheel_inner_ratio
            self._wheel_artist = mpatches.Circle(
                (cx, cy), inner_r,
                facecolor=cfg.wheel_color,
                edgecolor=cfg.wheel_edge_color,
                linewidth=cfg.wheel_linewidth,
                zorder=cfg.zorder + 1,
            )
            ax.add_patch(self._wheel_artist)

            # Body rectangle with rounded corners; drawn at origin, positioned via transform
            self._body_artist = mpatches.FancyBboxPatch(
                (-model.body_width / 2, 0),
                model.body_width,
                model.body_height,
                boxstyle=mpatches.BoxStyle.Round(pad=0, rounding_size=model.body_corner_radius),
                facecolor=cfg.body_color,
                edgecolor=cfg.body_edge_color,
                linewidth=cfg.body_linewidth,
                alpha=cfg.body_opacity,
                zorder=cfg.zorder - 1,
            )
            ax.add_patch(self._body_artist)
            self._update_body_transform()

            self._drawn = True
        else:
            self._tire_artist.center = (cx, cy)
            self._wheel_artist.center = (cx, cy)
            self._update_body_transform()

    # ------------------------------------------------------------------------------------------------------------------
    def _update_body_transform(self):
        cx = self.state.x
        cy = self.config.model.wheel_radius
        # Positive theta = forward lean = clockwise in side view = negative rotation in matplotlib
        t = (mtransforms.Affine2D()
             .rotate(-self.state.theta)
             .translate(cx, cy)
             + self._ax.transData)
        self._body_artist.set_transform(t)


# ======================================================================================================================
# === FLOOR ============================================================================================================
@dataclasses.dataclass
class Floor_Config:
    color: str | list | tuple = (0.88, 0.88, 0.88)
    height: float = 0.04
    edge_color: str | list | tuple = (0.4, 0.4, 0.4)
    edge_linewidth: float = 1.5
    zorder: int = 1


# ======================================================================================================================
# === PLOT ELEMENTS ====================================================================================================
@dataclasses.dataclass
class RectangleConfig:
    position: tuple[float, float] = (0, 0)  # Bottom-left corner
    width: float = 0.1
    height: float = 0.1
    color: str | list | tuple = 'gray'
    opacity: float = 1.0
    edge_color: str | list | tuple = 'black'
    edge_width: float = 1.0
    edge_style: str = '-'
    zorder: int = 5


class PlotRectangle:
    def __init__(self, config: RectangleConfig = None, **kwargs):
        if config is None:
            config = RectangleConfig()
        self.config = config
        if kwargs:
            update_dataclass_from_dict(self.config, kwargs)
        self._artist: mpatches.Rectangle | None = None

    def draw(self, ax: plt.Axes):
        cfg = self.config
        if self._artist is None:
            self._artist = mpatches.Rectangle(
                cfg.position, cfg.width, cfg.height,
                facecolor=cfg.color,
                alpha=cfg.opacity,
                edgecolor=cfg.edge_color,
                linewidth=cfg.edge_width,
                linestyle=cfg.edge_style,
                zorder=cfg.zorder,
            )
            ax.add_patch(self._artist)
        else:
            self._artist.set_xy(cfg.position)
            self._artist.set_width(cfg.width)
            self._artist.set_height(cfg.height)
            self._artist.set_facecolor(cfg.color)
            self._artist.set_alpha(cfg.opacity)


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class CircleConfig:
    position: tuple[float, float] = (0, 0)  # Center
    radius: float = 0.05
    color: str | list | tuple = 'gray'
    opacity: float = 1.0
    edge_color: str | list | tuple = 'black'
    edge_width: float = 1.0
    edge_style: str = '-'
    zorder: int = 5


class PlotCircle:
    def __init__(self, config: CircleConfig = None, **kwargs):
        if config is None:
            config = CircleConfig()
        self.config = config
        if kwargs:
            update_dataclass_from_dict(self.config, kwargs)
        self._artist: mpatches.Circle | None = None

    def draw(self, ax: plt.Axes):
        cfg = self.config
        if self._artist is None:
            self._artist = mpatches.Circle(
                cfg.position, cfg.radius,
                facecolor=cfg.color,
                alpha=cfg.opacity,
                edgecolor=cfg.edge_color,
                linewidth=cfg.edge_width,
                linestyle=cfg.edge_style,
                zorder=cfg.zorder,
            )
            ax.add_patch(self._artist)
        else:
            self._artist.center = cfg.position
            self._artist.set_radius(cfg.radius)
            self._artist.set_facecolor(cfg.color)
            self._artist.set_alpha(cfg.opacity)


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class DotConfig:
    position: tuple[float, float] = (0, 0)
    size: float = 0.015  # Radius in data units (meters)
    color: str | list | tuple = 'black'
    opacity: float = 1.0
    edge_color: str | list | tuple = 'none'
    edge_width: float = 0
    zorder: int = 12


class PlotDot:
    def __init__(self, config: DotConfig = None, **kwargs):
        if config is None:
            config = DotConfig()
        self.config = config
        if kwargs:
            update_dataclass_from_dict(self.config, kwargs)
        self._artist: mpatches.Circle | None = None

    def draw(self, ax: plt.Axes):
        cfg = self.config
        if self._artist is None:
            self._artist = mpatches.Circle(
                cfg.position, cfg.size,
                facecolor=cfg.color,
                alpha=cfg.opacity,
                edgecolor=cfg.edge_color,
                linewidth=cfg.edge_width,
                zorder=cfg.zorder,
            )
            ax.add_patch(self._artist)
        else:
            self._artist.center = cfg.position
            self._artist.set_radius(cfg.size)
            self._artist.set_facecolor(cfg.color)
            self._artist.set_alpha(cfg.opacity)


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class LabelConfig:
    position: tuple[float, float] = (0, 0)
    text: str = ''
    fontsize: float = 10
    color: str | list | tuple = 'black'
    opacity: float = 1.0
    ha: str = 'center'  # horizontal alignment: 'left', 'center', 'right'
    va: str = 'center'  # vertical alignment: 'top', 'center', 'bottom'
    rotation: float = 0.0
    font_weight: str = 'normal'
    font_style: str = 'normal'
    background: bool = False
    background_color: str | list | tuple = 'white'
    background_opacity: float = 0.8
    background_edge_color: str | list | tuple = 'black'
    background_edge_width: float = 0.5
    background_padding: float = 0.15
    zorder: int = 15


class PlotLabel:
    def __init__(self, config: LabelConfig = None, **kwargs):
        if config is None:
            config = LabelConfig()
        self.config = config
        if kwargs:
            update_dataclass_from_dict(self.config, kwargs)
        self._artist = None

    def draw(self, ax: plt.Axes):
        cfg = self.config
        bbox = None
        if cfg.background:
            bbox = dict(
                boxstyle=f'round,pad={cfg.background_padding}',
                facecolor=cfg.background_color,
                alpha=cfg.background_opacity,
                edgecolor=cfg.background_edge_color,
                linewidth=cfg.background_edge_width,
            )

        if self._artist is None:
            self._artist = ax.text(
                cfg.position[0], cfg.position[1], cfg.text,
                fontsize=cfg.fontsize,
                color=cfg.color,
                alpha=cfg.opacity,
                ha=cfg.ha, va=cfg.va,
                rotation=cfg.rotation,
                fontweight=cfg.font_weight,
                fontstyle=cfg.font_style,
                bbox=bbox,
                zorder=cfg.zorder,
            )
        else:
            self._artist.set_position(cfg.position)
            self._artist.set_text(cfg.text)
            self._artist.set_alpha(cfg.opacity)
            if bbox:
                self._artist.set_bbox(bbox)


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class LineConfig:
    points: Sequence[tuple[float, float]] = dataclasses.field(default_factory=list)
    color: str | list | tuple = 'black'
    width: float = 1.5
    style: str = '-'
    opacity: float = 1.0
    zorder: int = 5


class PlotLine:
    def __init__(self, config: LineConfig = None, **kwargs):
        if config is None:
            config = LineConfig()
        self.config = config
        if kwargs:
            update_dataclass_from_dict(self.config, kwargs)
        self._artist = None

    def draw(self, ax: plt.Axes):
        cfg = self.config
        if len(cfg.points) < 2:
            return
        xs = [p[0] for p in cfg.points]
        ys = [p[1] for p in cfg.points]

        if self._artist is None:
            (self._artist,) = ax.plot(
                xs, ys,
                color=cfg.color,
                linewidth=cfg.width,
                linestyle=cfg.style,
                alpha=cfg.opacity,
                zorder=cfg.zorder,
            )
        else:
            self._artist.set_data(xs, ys)
            self._artist.set_color(cfg.color)
            self._artist.set_alpha(cfg.opacity)


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class PathConfig:
    x: Sequence[float] | np.ndarray = dataclasses.field(default_factory=list)
    y: Sequence[float] | np.ndarray = dataclasses.field(default_factory=list)
    color: str | list | tuple = 'dodgerblue'
    width: float = 2.0
    style: str = '-'
    opacity: float = 1.0
    gradient: bool = False
    gradient_cmap: str = 'viridis'
    gradient_start_color: str | list | tuple | None = None
    gradient_end_color: str | list | tuple | None = None
    zorder: int = 5


class PlotPath:
    def __init__(self, config: PathConfig = None, **kwargs):
        if config is None:
            config = PathConfig()
        self.config = config
        if kwargs:
            update_dataclass_from_dict(self.config, kwargs)
        self._artist = None

    def draw(self, ax: plt.Axes):
        cfg = self.config
        x = np.asarray(cfg.x)
        y = np.asarray(cfg.y)
        if len(x) < 2:
            return

        if self._artist is not None:
            return

        if cfg.gradient:
            points = np.column_stack([x, y]).reshape(-1, 1, 2)
            segments = np.concatenate([points[:-1], points[1:]], axis=1)

            if cfg.gradient_start_color is not None and cfg.gradient_end_color is not None:
                cmap = mcolors.LinearSegmentedColormap.from_list(
                    'path_grad', [cfg.gradient_start_color, cfg.gradient_end_color])
            else:
                cmap = plt.get_cmap(cfg.gradient_cmap)

            norm = plt.Normalize(0, len(segments))
            lc = mcollections.LineCollection(
                segments, cmap=cmap, norm=norm,
                linewidth=cfg.width, alpha=cfg.opacity,
                linestyle=cfg.style, zorder=cfg.zorder,
            )
            lc.set_array(np.arange(len(segments)))
            ax.add_collection(lc)
            self._artist = lc
        else:
            (self._artist,) = ax.plot(
                x, y,
                color=cfg.color,
                linewidth=cfg.width,
                linestyle=cfg.style,
                alpha=cfg.opacity,
                zorder=cfg.zorder,
            )


# ======================================================================================================================
# === BILBO 2D PLOT ====================================================================================================
@dataclasses.dataclass
class BILBO_2D_Plot_Config:
    x_range: tuple[float, float] = (-1.0, 1.0)
    figsize: tuple[float, float] | None = None  # Auto-computed from data extents if None
    fig_width: float = 10  # Reference width in inches (used when figsize is None)
    min_fig_height: float = 3.0  # Minimum figure height in inches (used when figsize is None)
    dpi: int = 100
    background_color: str | list | tuple = 'white'
    floor: Floor_Config = dataclasses.field(default_factory=Floor_Config)
    padding: float = 0.05
    equal_aspect: bool = True
    show_grid: bool = False
    show_x_axis: bool = True
    show_y_axis: bool = False
    title: str | None = None


class BILBO_2D_Plot:
    """2D side-view plot of one or more BILBO robots on a floor."""

    def __init__(self, config: BILBO_2D_Plot_Config = None, **kwargs):
        if config is None:
            config = BILBO_2D_Plot_Config()
        self.config = config
        if kwargs:
            update_dataclass_from_dict(self.config, kwargs)

        self._bilbos: list[Plotted_BILBO] = []
        self._elements: list = []  # All non-bilbo elements
        self._fig: plt.Figure | None = None
        self._ax: plt.Axes | None = None
        self._initialized = False

    # === PROPERTIES ===================================================================================================
    @property
    def fig(self) -> plt.Figure | None:
        return self._fig

    @property
    def ax(self) -> plt.Axes | None:
        return self._ax

    @property
    def bilbos(self) -> list[Plotted_BILBO]:
        return self._bilbos

    # === ADD ELEMENTS =================================================================================================
    def add_bilbo(self, config: Plotted_BILBO_Config = None,
                  state: Plotted_BILBO_State = None, **kwargs) -> Plotted_BILBO:
        """Add a BILBO to the plot. Returns the Plotted_BILBO instance for state updates."""
        if config is None:
            config = Plotted_BILBO_Config()
        if kwargs:
            update_dataclass_from_dict(config, kwargs)
        bilbo = Plotted_BILBO(config=config, state=state)
        self._bilbos.append(bilbo)
        return bilbo

    def add_rectangle(self, config: RectangleConfig = None, **kwargs) -> PlotRectangle:
        if config is None:
            config = RectangleConfig()
        if kwargs:
            update_dataclass_from_dict(config, kwargs)
        elem = PlotRectangle(config=config)
        self._elements.append(elem)
        return elem

    def add_circle(self, config: CircleConfig = None, **kwargs) -> PlotCircle:
        if config is None:
            config = CircleConfig()
        if kwargs:
            update_dataclass_from_dict(config, kwargs)
        elem = PlotCircle(config=config)
        self._elements.append(elem)
        return elem

    def add_dot(self, config: DotConfig = None, **kwargs) -> PlotDot:
        if config is None:
            config = DotConfig()
        if kwargs:
            update_dataclass_from_dict(config, kwargs)
        elem = PlotDot(config=config)
        self._elements.append(elem)
        return elem

    def add_label(self, text: str, position: tuple[float, float],
                  config: LabelConfig = None, **kwargs) -> PlotLabel:
        if config is None:
            config = LabelConfig()
        config.text = text
        config.position = position
        if kwargs:
            update_dataclass_from_dict(config, kwargs)
        elem = PlotLabel(config=config)
        self._elements.append(elem)
        return elem

    def add_line(self, points: Sequence[tuple[float, float]],
                 config: LineConfig = None, **kwargs) -> PlotLine:
        if config is None:
            config = LineConfig()
        config.points = list(points)
        if kwargs:
            update_dataclass_from_dict(config, kwargs)
        elem = PlotLine(config=config)
        self._elements.append(elem)
        return elem

    def add_path(self, x: Sequence[float] | np.ndarray, y: Sequence[float] | np.ndarray,
                 config: PathConfig = None, **kwargs) -> PlotPath:
        if config is None:
            config = PathConfig()
        config.x = np.asarray(x)
        config.y = np.asarray(y)
        if kwargs:
            update_dataclass_from_dict(config, kwargs)
        elem = PlotPath(config=config)
        self._elements.append(elem)
        return elem

    # === DRAW =========================================================================================================
    def draw(self):
        """Draw or update the entire plot. Call this after changing bilbo states for animation."""
        if not self._initialized:
            self._init_figure()

        for elem in self._elements:
            elem.draw(self._ax)

        for bilbo in self._bilbos:
            bilbo.draw(self._ax)

        if self._fig is not None:
            self._fig.canvas.draw_idle()

    # === DISPLAY / SAVE ===============================================================================================
    def show(self):
        self.draw()
        plt.show()

    def save_png(self, filename: str, dpi: int = None):
        self.draw()
        if not filename.lower().endswith('.png'):
            filename += '.png'
        self._fig.savefig(filename, format='png', bbox_inches='tight', dpi=dpi or self.config.dpi)

    def save_pdf(self, filename: str):
        self.draw()
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'
        self._fig.savefig(filename, format='pdf', bbox_inches='tight')

    def close(self):
        if self._fig is not None:
            plt.close(self._fig)
            self._fig = None
            self._ax = None
            self._initialized = False

    # === PRIVATE ======================================================================================================
    def _init_figure(self):
        cfg = self.config

        # Compute data extents first
        x_min, x_max = cfg.x_range
        pad = cfg.padding
        data_width = (x_max - x_min) + 2 * pad

        max_height = 0
        for bilbo in self._bilbos:
            m = bilbo.config.model
            h = m.wheel_radius + m.body_height
            if h > max_height:
                max_height = h
        if max_height == 0:
            max_height = 0.35
        max_height *= 1.1

        floor_cfg = cfg.floor
        y_bottom = -floor_cfg.height
        data_height = (max_height + pad) - y_bottom

        # Compute figsize to match data aspect ratio (no wasted space)
        if cfg.figsize is not None:
            figsize = cfg.figsize
        else:
            fig_w = cfg.fig_width
            fig_h = max(fig_w * (data_height / data_width), cfg.min_fig_height)
            figsize = (fig_w, fig_h)

        self._fig, self._ax = plt.subplots(figsize=figsize, dpi=cfg.dpi)
        ax = self._ax

        ax.set_facecolor(cfg.background_color)
        self._fig.patch.set_facecolor(cfg.background_color)

        ax.set_xlim(x_min - pad, x_max + pad)
        ax.set_ylim(y_bottom, max_height + pad)

        if cfg.equal_aspect:
            ax.set_aspect('equal')

        # Floor rectangle fills from y_bottom to ground line (y=0)
        floor_width = (x_max - x_min) + 2 * pad
        floor_rect = mpatches.Rectangle(
            (x_min - pad, y_bottom),
            floor_width, floor_cfg.height,
            facecolor=floor_cfg.color,
            edgecolor='none',
            zorder=floor_cfg.zorder,
        )
        ax.add_patch(floor_rect)

        # Ground line
        ax.plot([x_min - pad, x_max + pad], [0, 0],
                color=floor_cfg.edge_color, linewidth=floor_cfg.edge_linewidth,
                zorder=floor_cfg.zorder + 1)

        if cfg.show_grid:
            ax.grid(True, alpha=0.3)

        if cfg.title:
            ax.set_title(cfg.title)

        # X axis
        if not cfg.show_x_axis:
            ax.set_xticks([])
            ax.set_xlabel('')
            ax.spines['bottom'].set_visible(False)
        else:
            ax.set_xlabel('x [m]')

        # Y axis
        ax.set_yticks([])
        ax.set_ylabel('')
        if not cfg.show_y_axis:
            ax.spines['left'].set_visible(False)

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        self._fig.tight_layout()
        self._initialized = True
