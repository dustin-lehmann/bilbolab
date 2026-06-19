import dataclasses
import platform
import shutil
import subprocess
import tempfile
from typing import Sequence

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection
import numpy as np

from core.utils.dataclass_utils import update_dataclass_from_dict


@dataclasses.dataclass
class TilesConfig:
    size: float = 0.5  # Size of tiles in meters
    color_1: str | list | tuple = 'lightgray'
    color_2: str | list | tuple = 'white'
    opacity: float = 1.0
    border_width: float = 0  # in pixels (0 = no border)
    border_color: str | list | tuple = 'gray'
    border_opacity: float = 1.0


@dataclasses.dataclass
class GridConfig:
    major: float | None = 1  # Grid spacing in meters
    minor: float | None = 0.25  # Minor grid spacing in meters
    major_color: str | list | tuple = 'black'
    major_width: float = 1
    major_linestyle: str = '-'
    major_opacity: float = 0.3
    major_add_labels: bool = True
    major_label_fontsize: float = 12
    minor_color: str | list | tuple = 'lightgray'
    minor_width: float = 1
    minor_linestyle: str = ':'
    minor_opacity: float = 1
    minor_add_labels: bool = False


@dataclasses.dataclass
class CoordinateSystemConfig:
    length: float = 0.5  # Length of the axes in meters
    position: tuple[float, float] = (0, 0)
    line_width: float = 0.015  # Width of arrow shaft in meters
    arrow_width: float = 0.05  # Arrow head width as fraction of length
    x_color: str | list | tuple = 'red'
    y_color: str | list | tuple = 'green'
    origin_size: float = 0.03  # Size of origin dot in meters
    origin_color: str | list | tuple = 'black'
    show_labels: bool = False
    label_fontsize: float = 10
    label_offset: float = 0.05  # Offset from arrow tip


@dataclasses.dataclass
class MapConfig:
    size: tuple[float, float] | tuple[tuple[float, float], tuple[float, float]] = (3, 3)
    # Width, height in meters (centered at origin) or ((x_min, x_max), (y_min, y_max))

    figsize: tuple[float, float] | None = None  # Figure size in inches (auto if None)
    dpi: int = 100
    background_color: list | tuple | str = 'white'
    background_opacity: float = 1.0
    border: bool = True
    border_color: list | tuple | str = 'black'
    border_width: float = 2.0
    border_opacity: float = 1.0
    border_linestyle: str = '-'
    border_corner_radius: float = 0.0  # Corner radius in meters (0 = sharp corners)
    padding: float = 0.1  # Padding around the map in meters
    equal_aspect: bool = True
    title: str | None = None
    title_fontsize: float = 12
    # Font settings for math text (LaTeX-like rendering without LaTeX)
    mathtext_fontset: str | None = None  # 'stix', 'cm', 'dejavusans', 'dejavuserif', etc.
    font_family: str | None = None  # e.g., 'STIXGeneral' for STIX fonts


@dataclasses.dataclass
class PointConfig:
    position: tuple[float, float] = (0, 0)
    size: float = 0.05  # Size in meters
    color: list | tuple | str = 'red'
    opacity: float = 1.0
    marker: str = 'o'  # matplotlib marker style
    label: str | None = None
    label_position: str = 'top'  # 'top', 'bottom', 'left', 'right'
    label_fontsize: float = 10
    label_color: list | tuple | str = 'black'
    label_offset: float = 0.05
    label_background: bool = False  # Add background box to label
    label_background_color: str | list | tuple = 'white'
    label_background_opacity: float = 0.8
    label_background_padding: float = 0.15  # Padding inside box (bbox pad units)
    label_background_edge_color: str | list | tuple = 'black'
    label_background_edge_width: float = 0.5
    border: bool = False
    border_color: list | tuple | str = 'black'
    border_width: float = 1  # in pixels
    zorder: int = 10


@dataclasses.dataclass
class LineConfig:
    positions: list[tuple[float, float]] = dataclasses.field(default_factory=list)
    color: list | tuple | str = 'black'
    width: float = 1.5
    opacity: float = 1.0
    style: str = '-'
    label: str | None = None
    label_position: str = 'end'  # 'start', 'middle', 'end'
    label_fontsize: float = 8
    label_color: list | tuple | str = 'black'
    label_offset: float = 0.05
    label_background: bool = False  # Add background box to label
    label_background_color: str | list | tuple = 'white'
    label_background_opacity: float = 0.8
    label_background_padding: float = 0.15  # Padding inside box (bbox pad units)
    label_background_edge_color: str | list | tuple = 'black'
    label_background_edge_width: float = 0.5
    zorder: int = 5


@dataclasses.dataclass
class TrajectoryConfig:
    x: np.ndarray | list | None = None
    y: np.ndarray | list | None = None
    color: list | tuple | str = 'blue'  # Used if gradient=False
    width: float = 2.0
    opacity: float = 1.0
    gradient: bool = False  # If True, color changes along trajectory
    gradient_cmap: str = 'viridis'  # Colormap for gradient
    gradient_start_color: str | None = None  # Override start color
    gradient_end_color: str | None = None  # Override end color
    show_start: bool = False  # Show marker at start
    show_end: bool = False  # Show marker at end
    start_marker: str = 'o'
    end_marker: str = 'o'
    start_size: float = 0.05
    end_size: float = 0.05
    start_color: str | None = None  # None = use trajectory color/gradient
    end_color: str | None = None
    label: str | None = None
    label_fontsize: float = 10
    label_color: list | tuple | str = 'black'
    label_offset: float = 0.05
    label_background: bool = False  # Add background box to label
    label_background_color: str | list | tuple = 'white'
    label_background_opacity: float = 0.8
    label_background_padding: float = 0.15  # Padding inside box (bbox pad units)
    label_background_edge_color: str | list | tuple = 'black'
    label_background_edge_width: float = 0.5
    zorder: int = 5


@dataclasses.dataclass
class RectangleConfig:
    position: tuple[float, float] = (0, 0)  # Bottom-left corner
    width: float = 1.0
    height: float = 1.0
    color: list | tuple | str = 'blue'
    opacity: float = 0.3
    border: bool = True
    border_color: list | tuple | str = 'blue'
    border_width: float = 1.0
    border_style: str = '-'
    border_opacity: float = 1.0
    zorder: int = 3


@dataclasses.dataclass
class CircleConfig:
    position: tuple[float, float] = (0, 0)  # Center
    radius: float = 0.5
    color: list | tuple | str = 'blue'
    opacity: float = 0.3
    border: bool = True
    border_color: list | tuple | str = 'blue'
    border_width: float = 1.0
    border_style: str = '-'
    border_opacity: float = 1.0
    zorder: int = 3


@dataclasses.dataclass
class LabelConfig:
    text: str = ''
    position: tuple[float, float] = (0, 0)
    fontsize: float = 10
    color: list | tuple | str = 'black'
    opacity: float = 1.0
    # Anchor: where the position refers to on the text box
    horizontal_anchor: str = 'center'  # 'left', 'center', 'right'
    vertical_anchor: str = 'center'  # 'top', 'center', 'bottom'
    # Padding from anchor position (not used when anchor is 'center')
    padding_x: float = 0.0
    padding_y: float = 0.0
    rotation: float = 0.0  # Rotation in degrees
    # Font styling
    font_style: str = 'normal'  # 'normal', 'italic', 'oblique'
    font_weight: str = 'normal'  # 'normal', 'bold', 'light', etc.
    font_family: str | None = None  # None uses default/map setting
    mathtext_fontset: str | None = None  # None uses map setting; 'stix', 'cm', etc.
    usetex: bool = False  # Use LaTeX rendering
    # Background box
    background: bool = False
    background_color: str | list | tuple = 'white'
    background_opacity: float = 0.8
    background_padding: float = 0.15
    background_edge_color: str | list | tuple = 'black'
    background_edge_width: float = 0.5
    zorder: int = 15


class MapPlot:

    # === INIT =========================================================================================================
    def __init__(self, config: MapConfig | None = None, **kwargs):

        if config is None:
            config = MapConfig()
        self.config = config
        update_dataclass_from_dict(self.config, kwargs)

        self._tiles: TilesConfig | None = None
        self._grid: GridConfig | None = None
        self._coordinate_system: CoordinateSystemConfig | None = None
        self._points: list[PointConfig] = []
        self._lines: list[LineConfig] = []
        self._trajectories: list[TrajectoryConfig] = []
        self._rectangles: list[RectangleConfig] = []
        self._circles: list[CircleConfig] = []
        self._labels: list[LabelConfig] = []

        # Parse map bounds
        self._x_min, self._x_max, self._y_min, self._y_max = self._parse_size(self.config.size)

        # Matplotlib objects (created on render)
        self._fig = None
        self._ax = None

    # === METHODS ======================================================================================================
    def add_tiles(self, tiles_config: TilesConfig | None = None, **kwargs) -> 'MapPlot':
        if tiles_config is None:
            tiles_config = TilesConfig()
        update_dataclass_from_dict(tiles_config, kwargs)
        self._tiles = tiles_config
        return self

    def add_grid(self, grid_config: GridConfig | None = None, **kwargs) -> 'MapPlot':
        if grid_config is None:
            grid_config = GridConfig()
        update_dataclass_from_dict(grid_config, kwargs)
        self._grid = grid_config
        return self

    def add_coordinate_system(self, coordinate_system_config: CoordinateSystemConfig | None = None,
                              **kwargs) -> 'MapPlot':
        if coordinate_system_config is None:
            coordinate_system_config = CoordinateSystemConfig()
        update_dataclass_from_dict(coordinate_system_config, kwargs)
        self._coordinate_system = coordinate_system_config
        return self

    def add_point(self, point_config: PointConfig | None = None, **kwargs) -> 'MapPlot':
        if point_config is None:
            point_config = PointConfig()
        update_dataclass_from_dict(point_config, kwargs)
        self._points.append(point_config)
        return self

    def add_line(self, line_config: LineConfig | None = None, **kwargs) -> 'MapPlot':
        if line_config is None:
            line_config = LineConfig()
        update_dataclass_from_dict(line_config, kwargs)
        self._lines.append(line_config)
        return self

    def add_trajectory(self, x: Sequence[float] | np.ndarray, y: Sequence[float] | np.ndarray,
                       trajectory_config: TrajectoryConfig | None = None, **kwargs) -> 'MapPlot':
        if trajectory_config is None:
            trajectory_config = TrajectoryConfig()
        trajectory_config.x = np.asarray(x)
        trajectory_config.y = np.asarray(y)
        update_dataclass_from_dict(trajectory_config, kwargs)
        self._trajectories.append(trajectory_config)
        return self

    def add_rectangle(self, rectangle_config: RectangleConfig | None = None, **kwargs) -> 'MapPlot':
        if rectangle_config is None:
            rectangle_config = RectangleConfig()
        update_dataclass_from_dict(rectangle_config, kwargs)
        self._rectangles.append(rectangle_config)
        return self

    def add_circle(self, circle_config: CircleConfig | None = None, **kwargs) -> 'MapPlot':
        if circle_config is None:
            circle_config = CircleConfig()
        update_dataclass_from_dict(circle_config, kwargs)
        self._circles.append(circle_config)
        return self

    def add_label(self, text: str, position: tuple[float, float],
                  label_config: LabelConfig | None = None, **kwargs) -> 'MapPlot':
        if label_config is None:
            label_config = LabelConfig()
        label_config.text = text
        label_config.position = position
        update_dataclass_from_dict(label_config, kwargs)
        self._labels.append(label_config)
        return self

    # === RENDER =======================================================================================================
    def render(self, ax: plt.Axes | None = None) -> tuple[plt.Figure, plt.Axes]:
        """Render the map and return (figure, axes).

        If ``ax`` is given, the map is drawn into that existing axes (and its
        parent figure) instead of creating a new figure -- useful for embedding
        the map alongside other panels in a composite figure.
        """
        if ax is not None:
            self._ax = ax
            self._fig = ax.figure
        else:
            # Calculate figure size if not specified
            if self.config.figsize is None:
                width = self._x_max - self._x_min + 2 * self.config.padding
                height = self._y_max - self._y_min + 2 * self.config.padding
                # Scale to reasonable figure size (target ~6 inches for larger dimension)
                scale = 6 / max(width, height)
                figsize = (width * scale, height * scale)
            else:
                figsize = self.config.figsize

            self._fig, self._ax = plt.subplots(figsize=figsize, dpi=self.config.dpi)

        # Apply font settings for math text
        if self.config.mathtext_fontset:
            plt.rcParams['mathtext.fontset'] = self.config.mathtext_fontset
        if self.config.font_family:
            plt.rcParams['font.family'] = self.config.font_family

        # Set background
        self._ax.set_facecolor(self.config.background_color)
        self._fig.patch.set_facecolor(self.config.background_color)

        # Set limits with padding
        self._ax.set_xlim(self._x_min - self.config.padding, self._x_max + self.config.padding)
        self._ax.set_ylim(self._y_min - self.config.padding, self._y_max + self.config.padding)

        # Equal aspect ratio
        if self.config.equal_aspect:
            self._ax.set_aspect('equal')

        # Remove default axes
        self._ax.axis('off')

        # Render elements in order (back to front)
        self._render_tiles()
        self._render_grid()
        self._render_border()
        self._render_rectangles()
        self._render_circles()
        self._render_lines()
        self._render_trajectories()
        self._render_points()
        self._render_coordinate_system()
        self._render_labels()

        # Title
        if self.config.title:
            self._ax.set_title(self.config.title, fontsize=self.config.title_fontsize)

        if ax is None:
            self._fig.tight_layout()
        return self._fig, self._ax

    # === DISPLAY/SAVE =================================================================================================
    def show(self):
        """Display the map using matplotlib."""
        if self._fig is None:
            self.render()
        plt.show()

    def show_pdf(self):
        """Save to temporary PDF and open with system viewer."""
        if self._fig is None:
            self.render()

        pdf_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf_path = pdf_file.name
        pdf_file.close()

        self._fig.savefig(pdf_path, format='pdf', bbox_inches='tight', dpi=self.config.dpi)
        _open_file_preview(pdf_path)

    def save_png(self, filename: str, dpi: int | None = None):
        """Save the map as PNG."""
        if self._fig is None:
            self.render()
        if not filename.lower().endswith('.png'):
            filename += '.png'
        self._fig.savefig(filename, format='png', bbox_inches='tight', dpi=dpi or self.config.dpi)

    def save_pdf(self, filename: str):
        """Save the map as PDF."""
        if self._fig is None:
            self.render()
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'
        self._fig.savefig(filename, format='pdf', bbox_inches='tight')

    def close(self):
        """Close the figure."""
        if self._fig is not None:
            plt.close(self._fig)
            self._fig = None
            self._ax = None

    # === PRIVATE METHODS ==============================================================================================
    def _parse_size(self, size) -> tuple[float, float, float, float]:
        """Parse size config into (x_min, x_max, y_min, y_max)."""
        if isinstance(size[0], (int, float)):
            # (width, height) centered at origin
            w, h = size
            return -w / 2, w / 2, -h / 2, h / 2
        else:
            # ((x_min, x_max), (y_min, y_max))
            (x_min, x_max), (y_min, y_max) = size
            return x_min, x_max, y_min, y_max

    def _render_tiles(self):
        if self._tiles is None:
            return

        cfg = self._tiles
        tile_size = cfg.size

        # Calculate tile grid
        x_start = np.floor(self._x_min / tile_size) * tile_size
        y_start = np.floor(self._y_min / tile_size) * tile_size
        x_end = np.ceil(self._x_max / tile_size) * tile_size
        y_end = np.ceil(self._y_max / tile_size) * tile_size

        x_tiles = np.arange(x_start, x_end, tile_size)
        y_tiles = np.arange(y_start, y_end, tile_size)

        for i, x in enumerate(x_tiles):
            for j, y in enumerate(y_tiles):
                # Checkerboard pattern
                color = cfg.color_1 if (i + j) % 2 == 0 else cfg.color_2
                rect = mpatches.Rectangle(
                    (x, y), tile_size, tile_size,
                    facecolor=color,
                    alpha=cfg.opacity,
                    edgecolor=cfg.border_color if cfg.border_width > 0 else 'none',
                    linewidth=cfg.border_width,
                    zorder=1
                )
                self._ax.add_patch(rect)

    def _render_grid(self):
        if self._grid is None:
            return

        cfg = self._grid

        # Minor grid - draw lines clipped to map bounds
        if cfg.minor is not None:
            x_minor = np.arange(
                np.ceil(self._x_min / cfg.minor) * cfg.minor,
                np.floor(self._x_max / cfg.minor) * cfg.minor + cfg.minor / 2,
                cfg.minor
            )
            y_minor = np.arange(
                np.ceil(self._y_min / cfg.minor) * cfg.minor,
                np.floor(self._y_max / cfg.minor) * cfg.minor + cfg.minor / 2,
                cfg.minor
            )

            for x in x_minor:
                if self._x_min <= x <= self._x_max:
                    self._ax.plot([x, x], [self._y_min, self._y_max],
                                  color=cfg.minor_color, linewidth=cfg.minor_width,
                                  linestyle=cfg.minor_linestyle, alpha=cfg.minor_opacity, zorder=2)
            for y in y_minor:
                if self._y_min <= y <= self._y_max:
                    self._ax.plot([self._x_min, self._x_max], [y, y],
                                  color=cfg.minor_color, linewidth=cfg.minor_width,
                                  linestyle=cfg.minor_linestyle, alpha=cfg.minor_opacity, zorder=2)

        # Major grid - draw lines clipped to map bounds
        if cfg.major is not None:
            x_major = np.arange(
                np.ceil(self._x_min / cfg.major) * cfg.major,
                np.floor(self._x_max / cfg.major) * cfg.major + cfg.major / 2,
                cfg.major
            )
            y_major = np.arange(
                np.ceil(self._y_min / cfg.major) * cfg.major,
                np.floor(self._y_max / cfg.major) * cfg.major + cfg.major / 2,
                cfg.major
            )

            for x in x_major:
                if self._x_min <= x <= self._x_max:
                    self._ax.plot([x, x], [self._y_min, self._y_max],
                                  color=cfg.major_color, linewidth=cfg.major_width,
                                  linestyle=cfg.major_linestyle, alpha=cfg.major_opacity, zorder=2)
            for y in y_major:
                if self._y_min <= y <= self._y_max:
                    self._ax.plot([self._x_min, self._x_max], [y, y],
                                  color=cfg.major_color, linewidth=cfg.major_width,
                                  linestyle=cfg.major_linestyle, alpha=cfg.major_opacity, zorder=2)

            # Add labels
            if cfg.major_add_labels:
                for x in x_major:
                    if self._x_min <= x <= self._x_max:
                        self._ax.text(x, self._y_min - self.config.padding * 0.5,
                                      f'{x:.1f}', ha='center', va='top',
                                      fontsize=cfg.major_label_fontsize, zorder=20)
                for y in y_major:
                    if self._y_min <= y <= self._y_max:
                        self._ax.text(self._x_min - self.config.padding * 0.5, y,
                                      f'{y:.1f}', ha='right', va='center',
                                      fontsize=cfg.major_label_fontsize, zorder=20)

    def _render_border(self):
        if not self.config.border:
            return

        width = self._x_max - self._x_min
        height = self._y_max - self._y_min
        radius = self.config.border_corner_radius

        if radius > 0:
            # Use FancyBboxPatch for rounded corners
            rect = mpatches.FancyBboxPatch(
                (self._x_min, self._y_min),
                width, height,
                boxstyle=mpatches.BoxStyle.Round(pad=0, rounding_size=radius),
                fill=False,
                edgecolor=self.config.border_color,
                linewidth=self.config.border_width,
                linestyle=self.config.border_linestyle,
                alpha=self.config.border_opacity,
                zorder=15
            )
        else:
            # Sharp corners
            rect = mpatches.Rectangle(
                (self._x_min, self._y_min),
                width, height,
                fill=False,
                edgecolor=self.config.border_color,
                linewidth=self.config.border_width,
                linestyle=self.config.border_linestyle,
                alpha=self.config.border_opacity,
                zorder=15
            )
        self._ax.add_patch(rect)

    def _render_coordinate_system(self):
        if self._coordinate_system is None:
            return

        cfg = self._coordinate_system
        ox, oy = cfg.position
        length = cfg.length
        line_width = cfg.line_width
        head_width = length * cfg.arrow_width * 3
        head_length = length * cfg.arrow_width * 5

        # X-axis arrow (red)
        self._ax.arrow(ox, oy, length, 0,
                       width=line_width,
                       head_width=head_width, head_length=head_length,
                       fc=cfg.x_color, ec=cfg.x_color, zorder=20)

        # Y-axis arrow (green)
        self._ax.arrow(ox, oy, 0, length,
                       width=line_width,
                       head_width=head_width, head_length=head_length,
                       fc=cfg.y_color, ec=cfg.y_color, zorder=20)

        # Origin dot
        origin_circle = mpatches.Circle(
            (ox, oy), cfg.origin_size,
            facecolor=cfg.origin_color,
            edgecolor='none',
            zorder=21
        )
        self._ax.add_patch(origin_circle)

        # Labels
        if cfg.show_labels:
            self._ax.text(ox + length + cfg.label_offset, oy, 'x',
                          fontsize=cfg.label_fontsize, ha='left', va='center',
                          color=cfg.x_color, zorder=20)
            self._ax.text(ox, oy + length + cfg.label_offset, 'y',
                          fontsize=cfg.label_fontsize, ha='center', va='bottom',
                          color=cfg.y_color, zorder=20)

    def _render_points(self):
        for cfg in self._points:
            # Convert size in meters to marker size (points^2)
            # Approximate: marker size in points = size_in_data * data_to_points_scale
            # This is simplified; for accurate sizing we'd need to compute based on axes transform
            marker_size = (cfg.size * 72 * self._fig.get_figwidth() /
                           (self._x_max - self._x_min + 2 * self.config.padding)) ** 2

            edge_color = cfg.border_color if cfg.border else 'none'
            edge_width = cfg.border_width if cfg.border else 0

            self._ax.scatter([cfg.position[0]], [cfg.position[1]],
                             s=marker_size,
                             c=[cfg.color],
                             marker=cfg.marker,
                             alpha=cfg.opacity,
                             edgecolors=edge_color,
                             linewidths=edge_width,
                             zorder=cfg.zorder)

            if cfg.label:
                lx, ly = cfg.position
                offset = cfg.label_offset
                # Increase offset when background box is used to account for padding
                if cfg.label_background:
                    offset *= 1.8
                ha, va = 'center', 'center'

                if cfg.label_position == 'top':
                    ly += offset
                    va = 'bottom'
                elif cfg.label_position == 'bottom':
                    ly -= offset
                    va = 'top'
                elif cfg.label_position == 'left':
                    lx -= offset
                    ha = 'right'
                elif cfg.label_position == 'right':
                    lx += offset
                    ha = 'left'

                bbox = None
                if cfg.label_background:
                    bbox = dict(
                        boxstyle=f'round,pad={cfg.label_background_padding}',
                        facecolor=cfg.label_background_color,
                        alpha=cfg.label_background_opacity,
                        edgecolor=cfg.label_background_edge_color,
                        linewidth=cfg.label_background_edge_width
                    )

                self._ax.text(lx, ly, cfg.label,
                              fontsize=cfg.label_fontsize,
                              color=cfg.label_color,
                              ha=ha, va=va,
                              bbox=bbox,
                              zorder=cfg.zorder + 1)

    def _render_lines(self):
        for cfg in self._lines:
            if len(cfg.positions) < 2:
                continue

            x = [p[0] for p in cfg.positions]
            y = [p[1] for p in cfg.positions]

            self._ax.plot(x, y,
                          color=cfg.color,
                          linewidth=cfg.width,
                          linestyle=cfg.style,
                          alpha=cfg.opacity,
                          zorder=cfg.zorder)

            if cfg.label:
                if cfg.label_position == 'start':
                    lx, ly = x[0], y[0]
                elif cfg.label_position == 'end':
                    lx, ly = x[-1], y[-1]
                else:  # middle
                    mid = len(x) // 2
                    lx, ly = x[mid], y[mid]

                bbox = None
                if cfg.label_background:
                    bbox = dict(
                        boxstyle=f'round,pad={cfg.label_background_padding}',
                        facecolor=cfg.label_background_color,
                        alpha=cfg.label_background_opacity,
                        edgecolor=cfg.label_background_edge_color,
                        linewidth=cfg.label_background_edge_width
                    )

                self._ax.text(lx + cfg.label_offset, ly + cfg.label_offset,
                              cfg.label,
                              fontsize=cfg.label_fontsize,
                              color=cfg.label_color,
                              bbox=bbox,
                              zorder=cfg.zorder + 1)

    def _render_trajectories(self):
        for cfg in self._trajectories:
            if cfg.x is None or cfg.y is None or len(cfg.x) < 2:
                continue

            x = np.asarray(cfg.x)
            y = np.asarray(cfg.y)

            if cfg.gradient:
                # Create line segments for gradient coloring
                points = np.array([x, y]).T.reshape(-1, 1, 2)
                segments = np.concatenate([points[:-1], points[1:]], axis=1)

                # Create colormap
                if cfg.gradient_start_color and cfg.gradient_end_color:
                    # Custom two-color gradient
                    cmap = mcolors.LinearSegmentedColormap.from_list(
                        'custom', [cfg.gradient_start_color, cfg.gradient_end_color])
                else:
                    cmap = plt.get_cmap(cfg.gradient_cmap)

                # Normalize based on trajectory length
                norm = plt.Normalize(0, len(segments))

                lc = LineCollection(segments, cmap=cmap, norm=norm,
                                    linewidth=cfg.width, alpha=cfg.opacity,
                                    zorder=cfg.zorder)
                lc.set_array(np.arange(len(segments)))
                self._ax.add_collection(lc)

                # Get colors for start/end markers
                start_color = cfg.start_color or cmap(0)
                end_color = cfg.end_color or cmap(1.0)
            else:
                # Simple single-color line
                self._ax.plot(x, y,
                              color=cfg.color,
                              linewidth=cfg.width,
                              alpha=cfg.opacity,
                              zorder=cfg.zorder)
                start_color = cfg.start_color or cfg.color
                end_color = cfg.end_color or cfg.color

            # Start marker
            if cfg.show_start:
                marker_size = (cfg.start_size * 72 * self._fig.get_figwidth() /
                               (self._x_max - self._x_min + 2 * self.config.padding)) ** 2
                self._ax.scatter([x[0]], [y[0]],
                                 s=marker_size,
                                 c=[start_color],
                                 marker=cfg.start_marker,
                                 zorder=cfg.zorder + 1)

            # End marker
            if cfg.show_end:
                marker_size = (cfg.end_size * 72 * self._fig.get_figwidth() /
                               (self._x_max - self._x_min + 2 * self.config.padding)) ** 2
                self._ax.scatter([x[-1]], [y[-1]],
                                 s=marker_size,
                                 c=[end_color],
                                 marker=cfg.end_marker,
                                 zorder=cfg.zorder + 1)

            if cfg.label:
                bbox = None
                if cfg.label_background:
                    bbox = dict(
                        boxstyle=f'round,pad={cfg.label_background_padding}',
                        facecolor=cfg.label_background_color,
                        alpha=cfg.label_background_opacity,
                        edgecolor=cfg.label_background_edge_color,
                        linewidth=cfg.label_background_edge_width
                    )

                self._ax.text(x[-1] + cfg.label_offset, y[-1] + cfg.label_offset,
                              cfg.label,
                              fontsize=cfg.label_fontsize,
                              color=cfg.label_color,
                              bbox=bbox,
                              zorder=cfg.zorder + 1)

    def _render_rectangles(self):
        for cfg in self._rectangles:
            rect = mpatches.Rectangle(
                cfg.position, cfg.width, cfg.height,
                facecolor=cfg.color,
                alpha=cfg.opacity,
                edgecolor=cfg.border_color if cfg.border else 'none',
                linewidth=cfg.border_width if cfg.border else 0,
                linestyle=cfg.border_style,
                zorder=cfg.zorder
            )
            self._ax.add_patch(rect)

    def _render_circles(self):
        for cfg in self._circles:
            circle = mpatches.Circle(
                cfg.position, cfg.radius,
                facecolor=cfg.color,
                alpha=cfg.opacity,
                edgecolor=cfg.border_color if cfg.border else 'none',
                linewidth=cfg.border_width if cfg.border else 0,
                linestyle=cfg.border_style,
                zorder=cfg.zorder
            )
            self._ax.add_patch(circle)

    def _render_labels(self):
        for cfg in self._labels:
            if not cfg.text:
                continue

            # Calculate position with anchor and padding
            lx, ly = cfg.position

            # Horizontal alignment and padding
            if cfg.horizontal_anchor == 'left':
                ha = 'left'
                lx += cfg.padding_x
            elif cfg.horizontal_anchor == 'right':
                ha = 'right'
                lx -= cfg.padding_x
            else:  # center
                ha = 'center'

            # Vertical alignment and padding
            if cfg.vertical_anchor == 'top':
                va = 'top'
                ly -= cfg.padding_y
            elif cfg.vertical_anchor == 'bottom':
                va = 'bottom'
                ly += cfg.padding_y
            else:  # center
                va = 'center'

            # Background box
            bbox = None
            if cfg.background:
                bbox = dict(
                    boxstyle=f'round,pad={cfg.background_padding}',
                    facecolor=cfg.background_color,
                    alpha=cfg.background_opacity,
                    edgecolor=cfg.background_edge_color,
                    linewidth=cfg.background_edge_width
                )

            # Font properties
            font_kwargs = {
                'fontsize': cfg.fontsize,
                'color': cfg.color,
                'alpha': cfg.opacity,
                'fontstyle': cfg.font_style,
                'fontweight': cfg.font_weight,
                'rotation': cfg.rotation,
                'ha': ha,
                'va': va,
                'bbox': bbox,
                'zorder': cfg.zorder,
            }

            if cfg.font_family:
                font_kwargs['fontfamily'] = cfg.font_family

            # LaTeX rendering
            if cfg.usetex:
                font_kwargs['usetex'] = True

            # Apply per-label mathtext fontset if specified
            if cfg.mathtext_fontset:
                rc_overrides = {'mathtext.fontset': cfg.mathtext_fontset}
                if cfg.font_family:
                    rc_overrides['font.family'] = cfg.font_family
                with plt.rc_context(rc_overrides):
                    self._ax.text(lx, ly, cfg.text, **font_kwargs)
            else:
                self._ax.text(lx, ly, cfg.text, **font_kwargs)


# === UTILITY FUNCTIONS ================================================================================================
def _open_file_preview(file):
    """Open file with system default viewer."""
    system = platform.system()

    try:
        if system == "Darwin":
            if shutil.which("open"):
                try:
                    subprocess.Popen(["open", "-a", "Preview", file])
                    return
                except Exception:
                    pass
            if shutil.which("open"):
                subprocess.Popen(["open", file])
                return

        elif system == "Linux":
            if shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", file])
                return

        elif system == "Windows":
            import os
            os.startfile(file)
    except Exception:
        pass
