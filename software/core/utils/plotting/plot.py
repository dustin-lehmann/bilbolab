import base64
import dataclasses
import io
import platform
import shutil
import subprocess
import tempfile
from typing import Sequence, Iterable, Optional, Any

import matplotlib
import matplotlib.patches as mpatches

from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.offsetbox import AnnotationBbox, TextArea, HPacker, DrawingArea, OffsetImage

from core.utils.colors import get_palette, darken_color
from core.utils.uuid_utils import generate_uuid


# === LINE =============================================================================================================
@dataclasses.dataclass
class LineConfig:
    color: str | Sequence[float] | None = 'black'
    linewidth: float = 1.5
    style: str = "-"
    alpha: float = 1


class Line:
    id: str
    start: tuple[float, float]
    end: tuple[float, float]
    config: LineConfig
    artist: Line2D | None = None

    ax: Axes | None = None

    # === INIT =========================================================================================================
    def __init__(self,
                 start: tuple[float, float],
                 end: tuple[float, float],
                 id: str | None = None,
                 config: LineConfig | None = None,
                 **overrides):

        if id is None:
            id = generate_uuid()
        self.id = id
        self.start = start
        self.end = end

        if config is None:
            config = LineConfig()
        self.config = config
        if overrides:
            self.config = dataclasses.replace(self.config, **overrides)

    # ------------------------------------------------------------------------------------------------------------------

    def plot(self, ax: Axes) -> Line2D:
        """Draw this line on the given Matplotlib Axes."""
        if self.ax is not None:
            raise ValueError("Line already plotted on an axis.")

        self.ax = ax

        x_values = (self.start[0], self.end[0])
        y_values = (self.start[1], self.end[1])

        cfg = self.config
        kwargs: dict = {
            "color": cfg.color,
            "linewidth": cfg.linewidth,
            "linestyle": cfg.style,  # Matplotlib uses 'linestyle'
            "alpha": cfg.alpha,
        }
        # Drop None values so rcParams defaults can apply
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        (self.artist,) = ax.plot(x_values, y_values, **kwargs)
        return self.artist


# === LABEL ============================================================================================================
@dataclasses.dataclass
class LabelConfig:
    # Text appearance
    color: str | Sequence[float] | None = None
    fontsize: float | None = None
    font_family: str | None = None

    # Alignment (semantic, our API)
    # When background_box == False:
    #   -> passed straight to ax.text as verticalalignment / horizontalalignment (text-based)
    # When background_box == True:
    #   -> mapped to AnnotationBbox.box_alignment (box-based)
    vertical_alignment: str = "center"  # "top" | "center" | "bottom"
    horizontal_alignment: str = "center"  # "left" | "center" | "right"

    # Background box
    background_box: bool = True
    background_color: str | Sequence[float] | None = None
    background_alpha: float = 1.0
    background_edgewidth: float = 0.5
    background_edgecolor: str | Sequence[float] | None = 'black'

    # Padding around the text inside the box (in "boxstyle pad" units)
    # This gets converted into "round,pad={box_padding}" internally.
    box_padding: float = 0.3

    # Extra offset in display (pixel) coordinates, applied to the anchor position.
    offset_x: float = 2
    offset_y: float = 2

    # Overall text alpha
    alpha: float = 1.0


class Label:
    id: str
    ax: Axes | None = None
    text: str
    position: tuple[float, float]
    config: LabelConfig
    artist: Artist | None = None

    def __init__(
            self,
            text: str,
            position: tuple[float, float],
            id: str | None = None,
            config: LabelConfig | None = None,
            **overrides,
    ):
        """
        Parameters
        ----------
        text : str
            Text content of the label.
        position : (float, float)
            Data coordinates (x, y). Interpreted as:
              - plain text (background_box=False):
                    anchor point for the text (Matplotlib semantics)
              - boxed text (background_box=True):
                    anchor point for the OUTER box edge according to
                    horizontal_alignment / vertical_alignment, with
                    compensation for padding.
        id : str | None
            Optional unique ID. If None, a UUID will be generated.
        config : LabelConfig | None
            Visual configuration for this label. If None, use defaults.
        overrides :
            Any LabelConfig fields to override for this instance, e.g.
            color='red', fontsize=10, background_color='white', etc.
        """
        if id is None:
            id = generate_uuid()
        self.id = id
        self.text = text
        self.position = position

        if config is None:
            config = LabelConfig()
        self.config = config
        if overrides:
            self.config = dataclasses.replace(self.config, **overrides)

    # ------------------------------------------------------------------------------------------------------------------
    def plot(self, ax: Axes) -> Artist:
        """Draw this label on the given Matplotlib Axes."""
        if self.ax is not None and self.ax is not ax:
            raise ValueError("Label is already plotted on a different axis.")

        self.ax = ax
        cfg = self.config
        x_target, y_target = self.position  # target OUTER box edge for top/bottom/left/right

        # --- CASE 1: NO BACKGROUND BOX -> plain Text (alignment is text-based) ---------------------------------------
        if not cfg.background_box:
            # Start from the target position and apply pixel offset in data units.
            # If alignment is center in a direction, that direction's offset is ignored.
            dx_data, dy_data = self._display_offset_to_data(
                ax,
                cfg.offset_x,
                cfg.offset_y,
                cfg.vertical_alignment,
                cfg.horizontal_alignment,
            )
            x_anchor = x_target + dx_data
            y_anchor = y_target + dy_data

            text_kwargs: dict = {
                "color": cfg.color,
                "fontsize": cfg.fontsize,
                "fontfamily": cfg.font_family,
                "verticalalignment": cfg.vertical_alignment,
                "horizontalalignment": cfg.horizontal_alignment,
                "alpha": cfg.alpha,
            }
            # Drop None values so rcParams defaults apply
            text_kwargs = {k: v for k, v in text_kwargs.items() if v is not None}

            self.artist = ax.text(x_anchor, y_anchor, self.text, **text_kwargs)
            return self.artist

        # --- CASE 2: WITH BACKGROUND BOX -> use AnnotationBbox (alignment is box-based) ------------------------------
        # Map our semantic alignments to box_alignment (0=left/bottom, 0.5=center, 1=right/top)
        h_map = {"left": 0.0, "center": 0.5, "right": 1.0}
        v_map = {"bottom": 0.0, "center": 0.5, "top": 1.0}

        h_align = h_map.get(cfg.horizontal_alignment, 0.5)
        v_align = v_map.get(cfg.vertical_alignment, 0.5)

        # Start with anchor == target; then compensate for padding so that the
        # OUTER box edge sits at the target x/y for top/bottom/left/right.
        x_anchor = x_target
        y_anchor = y_target

        if cfg.box_padding > 0:
            # Vertical compensation (top/bottom)
            if cfg.vertical_alignment in ("top", "bottom"):
                pad_y = self._estimate_vertical_pad_in_data(ax, cfg)
                if cfg.vertical_alignment == "top":
                    # Without compensation, top of box would be ABOVE y_target.
                    y_anchor = y_target - pad_y
                elif cfg.vertical_alignment == "bottom":
                    # Without compensation, bottom of box would be BELOW y_target.
                    y_anchor = y_target + pad_y

            # Horizontal compensation (left/right)
            if cfg.horizontal_alignment in ("left", "right"):
                pad_x = self._estimate_horizontal_pad_in_data(ax, cfg)
                if cfg.horizontal_alignment == "left":
                    # Without compensation, left of box would be LEFT of x_target.
                    # Move anchor to the right so outer left edge is at x_target.
                    x_anchor = x_target + pad_x
                elif cfg.horizontal_alignment == "right":
                    # Without compensation, right of box would be RIGHT of x_target.
                    # Move anchor to the left so outer right edge is at x_target.
                    x_anchor = x_target - pad_x

        # Now apply *extra* display offset (independent of axis scaling),
        # respecting alignment rules (center -> ignore in that direction).
        if cfg.offset_x != 0.0 or cfg.offset_y != 0.0:
            dx_data, dy_data = self._display_offset_to_data(
                ax,
                cfg.offset_x,
                cfg.offset_y,
                cfg.vertical_alignment,
                cfg.horizontal_alignment,
            )
            x_anchor += dx_data
            y_anchor += dy_data

        # Text properties for TextArea
        textprops: dict = {
            "color": cfg.color,
            "fontsize": cfg.fontsize,
            "fontfamily": cfg.font_family,
        }
        textprops = {k: v for k, v in textprops.items() if v is not None}

        text_area = TextArea(self.text, textprops=textprops)

        # Box style / appearance
        boxstyle_str = f"round,pad={cfg.box_padding}"
        bboxprops: dict = {
            "boxstyle": boxstyle_str,
            "facecolor": cfg.background_color if cfg.background_color is not None else "none",
            "edgecolor": cfg.background_edgecolor,
            "linewidth": cfg.background_edgewidth,
            "alpha": cfg.background_alpha,
        }
        bboxprops = {k: v for k, v in bboxprops.items() if v is not None}

        ab = AnnotationBbox(
            text_area,
            xy=(x_anchor, y_anchor),
            xycoords="data",
            box_alignment=(h_align, v_align),  # alignment is based on the box
            bboxprops=bboxprops,
            frameon=True,
        )
        ab.set_alpha(cfg.alpha)

        ax.add_artist(ab)
        self.artist = ab
        return self.artist

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _estimate_vertical_pad_in_data(ax: Axes, cfg: LabelConfig) -> float:
        """
        Estimate the vertical shift (in data units) caused by the box padding,
        so we can align the OUTER box top/bottom to the target y.
        """
        # Get fontsize in points (fall back to rcParams if not set)
        if cfg.fontsize is not None:
            fontsize_pts = cfg.fontsize
        else:
            fontsize_pts = matplotlib.rcParams.get("font.size", 12.0)

        fig = ax.figure
        dpi = fig.dpi

        # Approximate one line of text height in pixels (~ fontsize)
        text_height_px = fontsize_pts / 72.0 * dpi

        # How much padding extends the box outward in pixels (one side)
        pad_px = cfg.box_padding * text_height_px

        # Convert this vertical pixel shift to data units
        inv = ax.transData.inverted()
        y0 = inv.transform((0.0, 0.0))[1]
        y1 = inv.transform((0.0, pad_px))[1]
        pad_data = y1 - y0

        # Add a small correction for line width so thicker borders don't overshoot
        if cfg.background_edgewidth:
            lw_px = cfg.background_edgewidth / 72.0 * dpi
            y2 = inv.transform((0.0, pad_px + lw_px * 0.5))[1]
            pad_data = y2 - y0

        return pad_data

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _estimate_horizontal_pad_in_data(ax: Axes, cfg: LabelConfig) -> float:
        """
        Estimate the horizontal shift (in data units) caused by the box padding,
        so we can align the OUTER box left/right to the target x.

        We approximate padding based on text height (similar scaling in x/y).
        """
        # Get fontsize in points (fall back to rcParams if not set)
        if cfg.fontsize is not None:
            fontsize_pts = cfg.fontsize
        else:
            fontsize_pts = matplotlib.rcParams.get("font.size", 12.0)

        fig = ax.figure
        dpi = fig.dpi

        # Use text height as scale for padding
        text_height_px = fontsize_pts / 72.0 * dpi
        pad_px = cfg.box_padding * text_height_px

        # Convert this horizontal pixel shift to data units
        inv = ax.transData.inverted()
        x0 = inv.transform((0.0, 0.0))[0]
        x1 = inv.transform((pad_px, 0.0))[0]
        pad_data = x1 - x0

        # Add small correction for line width
        if cfg.background_edgewidth:
            lw_px = cfg.background_edgewidth / 72.0 * dpi
            x2 = inv.transform((pad_px + lw_px * 0.5, 0.0))[0]
            pad_data = x2 - x0

        return pad_data

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _display_offset_to_data(
            ax: Axes,
            dx_pixels: float,
            dy_pixels: float,
            vertical_alignment: str,
            horizontal_alignment: str,
    ) -> tuple[float, float]:
        """
        Convert an offset in display (pixel) coordinates into data units,
        applying direction based on alignment:

          - horizontal_alignment == "center" -> ignore x offset
          - vertical_alignment   == "center" -> ignore y offset
          - "top"    -> offset moves label DOWN
          - "bottom" -> offset moves label UP
          - "left"   -> offset moves label RIGHT
          - "right"  -> offset moves label LEFT

        The magnitude is taken from |dx_pixels| / |dy_pixels|.
        """
        # Determine effective pixel offsets based on alignment
        eff_dx = 0.0
        eff_dy = 0.0

        # Horizontal
        if horizontal_alignment == "left":
            eff_dx = abs(dx_pixels)  # move right
        elif horizontal_alignment == "right":
            eff_dx = -abs(dx_pixels)  # move left
        # center -> 0.0

        # Vertical
        if vertical_alignment == "bottom":
            eff_dy = abs(dy_pixels)  # move up
        elif vertical_alignment == "top":
            eff_dy = -abs(dy_pixels)  # move down
        # center -> 0.0

        if eff_dx == 0.0 and eff_dy == 0.0:
            return 0.0, 0.0

        inv = ax.transData.inverted()
        x0, y0 = inv.transform((0.0, 0.0))
        x1, y1 = inv.transform((eff_dx, eff_dy))
        return x1 - x0, y1 - y0


# === PHASE BAR ========================================================================================================
@dataclasses.dataclass
class PhaseConfig:
    """Configuration for a single phase in a phase bar."""
    color: str | Sequence[float] = 'tab:blue'
    alpha: float = 0.85
    layer: int = 0
    edge_color: str | Sequence[float] | None = None  # None = auto darker version of color
    edge_width: float = 0.5
    text_color: str | Sequence[float] | None = None  # None = auto (contrast with background)


@dataclasses.dataclass
class PhaseBarConfig:
    """Configuration for the phase bar system on an axis."""
    position: str = "bottom_inside"  # "top_inside", "bottom_inside", "bottom_outside"
    height: float = 0.06  # Height as fraction of axis height
    fontsize: float = 7
    global_alpha: float = 1.0
    layer_gap: float = 0.005  # Gap between layers as fraction of axis height
    min_width_for_inside_text: float | None = None  # Min data width to show text inside; None = always inside
    show_text: bool = True
    text_padding: float = 2  # Horizontal padding in points for text
    default_color: str | Sequence[float] = 'tab:gray'  # Default color when not specified

    # Positioning adjustments
    bottom_padding: float = 0.02  # Padding above x-axis for bottom_inside (axes fraction)
    top_padding: float = 0.02  # Padding below top for top_inside (axes fraction)
    outside_offset: float = 0.25  # How far below axis for bottom_outside (axes fraction)

    # Styling
    horizontal_padding: float = 0.002  # Padding on each side of phase (axes fraction of width)
    corner_radius: float = 0.008  # Corner rounding radius (axes fraction)
    auto_edge_darken: float = 0.25  # How much to darken color for auto edge (0-1)


class Phase:
    """Represents a single phase in a phase bar."""
    id: str
    start: float
    end: float
    config: PhaseConfig

    rect_artist: mpatches.FancyBboxPatch | None = None
    text_artist: Artist | None = None

    def __init__(
            self,
            phase_id: str,
            start: float,
            end: float,
            config: PhaseConfig | None = None,
            **overrides,
    ):
        self.id = phase_id
        self.start = start
        self.end = end

        if config is None:
            config = PhaseConfig()
        self.config = config
        if overrides:
            self.config = dataclasses.replace(self.config, **overrides)

    @staticmethod
    def _get_contrast_color(color) -> str:
        """Return 'white' or 'black' based on background luminance."""
        import matplotlib.colors as mcolors
        try:
            rgb = mcolors.to_rgb(color)
            # Perceived luminance formula
            luminance = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
            return 'white' if luminance < 0.5 else 'black'
        except Exception:
            return 'black'

    def plot(
            self,
            ax: Axes,
            bar_config: PhaseBarConfig,
            y_base: float,
            y_height: float,
            transform,
            x_padding_data: float = 0.0,
    ) -> tuple[mpatches.FancyBboxPatch, Artist | None]:
        """
        Draw this phase on the given axes.

        Parameters
        ----------
        ax : Axes
            The matplotlib axes to draw on.
        bar_config : PhaseBarConfig
            The phase bar configuration.
        y_base : float
            The y position (bottom) of this phase bar in the appropriate coordinate system.
        y_height : float
            The height of this phase bar.
        transform : Transform
            The matplotlib transform to use (blended for mixed coordinates).
        x_padding_data : float
            Horizontal padding in data units to apply to each side.

        Returns
        -------
        tuple[FancyBboxPatch, Artist | None]
            The rectangle and text artists created.
        """
        cfg = self.config
        effective_alpha = cfg.alpha * bar_config.global_alpha

        # Apply horizontal padding
        x_start = self.start + x_padding_data
        x_end = self.end - x_padding_data
        width = x_end - x_start

        # Determine edge color (auto-darken if not specified)
        if cfg.edge_color is not None:
            edge_color = cfg.edge_color
        else:
            edge_color = darken_color(cfg.color, bar_config.auto_edge_darken)

        # Use FancyBboxPatch for rounded corners
        # Note: rounding_size is in data coordinates for x, axes fraction for y
        # We use a mutation_scale to control the rounding
        rect = mpatches.FancyBboxPatch(
            (x_start, y_base),
            width=width,
            height=y_height,
            boxstyle=mpatches.BoxStyle.Round(pad=0, rounding_size=bar_config.corner_radius),
            facecolor=cfg.color,
            edgecolor=edge_color,
            linewidth=cfg.edge_width,
            alpha=effective_alpha,
            transform=transform,
            clip_on=False,
            zorder=5,
            mutation_aspect=1,
        )
        ax.add_patch(rect)
        self.rect_artist = rect

        # Text label
        self.text_artist = None
        if bar_config.show_text and self.id:
            # Determine text color
            text_color = cfg.text_color
            if text_color is None:
                text_color = self._get_contrast_color(cfg.color)

            # Check if text should be inside or above
            show_inside = True
            if bar_config.min_width_for_inside_text is not None:
                phase_width = self.end - self.start
                if phase_width < bar_config.min_width_for_inside_text:
                    show_inside = False

            x_center = (self.start + self.end) / 2

            if show_inside:
                # Text inside the bar
                y_center = y_base + y_height / 2
                self.text_artist = ax.text(
                    x_center,
                    y_center,
                    self.id,
                    ha='center',
                    va='center',
                    fontsize=bar_config.fontsize,
                    color=text_color,
                    alpha=effective_alpha,
                    transform=transform,
                    clip_on=False,
                    zorder=6,
                )
            else:
                # Text above the bar
                y_top = y_base + y_height
                self.text_artist = ax.text(
                    x_center,
                    y_top,
                    self.id,
                    ha='center',
                    va='bottom',
                    fontsize=bar_config.fontsize,
                    color=cfg.color,  # Use bar color for outside text
                    alpha=effective_alpha,
                    transform=transform,
                    clip_on=False,
                    zorder=6,
                )

        return rect, self.text_artist


# === PHASE BACKGROUND =================================================================================================
@dataclasses.dataclass
class PhaseBackgroundConfig:
    """Configuration for the phase background system on an axis."""
    alpha: float = 0.15  # Global opacity for background colors
    label_position: str = "top"  # "top" or "bottom"
    show_labels: bool = True
    show_dividers: bool = True  # Vertical lines between phases
    divider_color: str | Sequence[float] = "gray"
    divider_width: float = 0.5
    divider_style: str = "--"
    divider_alpha: float = 0.5
    fontsize: float = 8
    label_alpha: float = 1.0  # Label text alpha (1.0 = fully visible)
    label_offset: float = 0.02  # Offset from top/bottom as axes fraction

    # Label background box
    label_box: bool = True  # Whether to show a background box behind labels
    label_box_color: str | Sequence[float] = "white"
    label_box_alpha: float = 0.75
    label_box_padding: float = 0.3  # Padding inside the box
    label_box_edgecolor: str | Sequence[float] | None = None  # None = no edge
    label_box_edgewidth: float = 0.5

    # Label color (None = use darkened phase color for better visibility)
    label_color_darken: float = 0.3  # How much to darken phase color for label


@dataclasses.dataclass
class BackgroundPhaseConfig:
    """Configuration for a single background phase."""
    color: str | Sequence[float] = 'tab:blue'
    alpha: float | None = None  # None = use global alpha
    label_color: str | Sequence[float] | None = None  # None = use phase color


class BackgroundPhase:
    """Represents a single background phase region."""
    id: str
    start: float
    end: float
    config: BackgroundPhaseConfig

    span_artist: mpatches.Polygon | None = None
    line_artist: Line2D | None = None
    text_artist: Artist | None = None

    def __init__(
            self,
            phase_id: str,
            start: float,
            end: float,
            config: BackgroundPhaseConfig | None = None,
            **overrides,
    ):
        self.id = phase_id
        self.start = start
        self.end = end

        if config is None:
            config = BackgroundPhaseConfig()
        self.config = config
        if overrides:
            self.config = dataclasses.replace(self.config, **overrides)

    def plot(
            self,
            ax: Axes,
            bg_config: PhaseBackgroundConfig,
            is_last: bool = False,
    ) -> tuple[mpatches.Polygon, Line2D | None, Artist | None]:
        """
        Draw this background phase on the given axes.

        Parameters
        ----------
        ax : Axes
            The matplotlib axes to draw on.
        bg_config : PhaseBackgroundConfig
            The phase background configuration.
        is_last : bool
            Whether this is the last phase (affects divider drawing).

        Returns
        -------
        tuple[Polygon, Line2D | None, Artist | None]
            The span, divider line, and text artists created.
        """
        cfg = self.config
        effective_alpha = cfg.alpha if cfg.alpha is not None else bg_config.alpha

        # Draw background span using axvspan
        self.span_artist = ax.axvspan(
            self.start,
            self.end,
            facecolor=cfg.color,
            alpha=effective_alpha,
            edgecolor='none',
            zorder=0,
        )

        # Draw divider line at the end of this phase (unless it's the last one)
        self.line_artist = None
        if bg_config.show_dividers and not is_last:
            self.line_artist = ax.axvline(
                x=self.end,
                color=bg_config.divider_color,
                linewidth=bg_config.divider_width,
                linestyle=bg_config.divider_style,
                alpha=bg_config.divider_alpha,
                zorder=1,
            )

        # Draw label
        self.text_artist = None
        if bg_config.show_labels and self.id:
            x_center = (self.start + self.end) / 2

            # Determine label color: explicit > darkened phase color
            if cfg.label_color is not None:
                label_color = cfg.label_color
            else:
                # Darken the phase color for better visibility
                label_color = darken_color(cfg.color, bg_config.label_color_darken)

            if bg_config.label_position == "top":
                y_pos = 1.0 - bg_config.label_offset
                va = "top"
            else:  # "bottom"
                y_pos = bg_config.label_offset
                va = "bottom"

            # Use blended transform: x in data, y in axes
            from matplotlib.transforms import blended_transform_factory
            transform = blended_transform_factory(ax.transData, ax.transAxes)

            # Build bbox properties if label_box is enabled
            bbox_props = None
            if bg_config.label_box:
                bbox_props = dict(
                    boxstyle=f"round,pad={bg_config.label_box_padding}",
                    facecolor=bg_config.label_box_color,
                    alpha=bg_config.label_box_alpha,
                    edgecolor=bg_config.label_box_edgecolor if bg_config.label_box_edgecolor else 'none',
                    linewidth=bg_config.label_box_edgewidth,
                )

            self.text_artist = ax.text(
                x_center,
                y_pos,
                self.id,
                ha='center',
                va=va,
                fontsize=bg_config.fontsize,
                color=label_color,
                alpha=bg_config.label_alpha,
                transform=transform,
                zorder=10,
                bbox=bbox_props,
            )

        return self.span_artist, self.line_artist, self.text_artist


# === SERIES ===========================================================================================================
@dataclasses.dataclass
class SeriesConfig:
    """Defaults for lines."""
    color: str | Sequence[float] | None = None
    linewidth: float = 1.5
    linestyle: str = "-"
    alpha: float = 1.0
    label: str | None = None
    visible: bool = True

    # Markers
    marker: str | None = None
    marker_size: float = 6.0
    marker_facecolor: str | Sequence[float] | None = None
    marker_edgecolor: str | Sequence[float] | None = None
    markevery: object | None = None

    # Special
    stairs: bool = False  # if True -> use ax.step
    static: bool = False  # if True -> not animated (always shown in full)


class Series:
    id: str
    x_data: list[float] | Iterable[float]
    y_data: list[float] | Iterable[float]
    line: Line2D
    config: SeriesConfig

    ax: Axes | None = None

    # === INIT =========================================================================================================
    def __init__(self,
                 id: str,
                 x_data: Iterable[float | int],
                 y_data: Iterable[float | int],
                 config: SeriesConfig | None = None,
                 **overrides):

        self.id = id
        self.x_data = x_data
        self.y_data = y_data

        if config is None:
            config = SeriesConfig()
        self.config = config
        if overrides:
            self.config = dataclasses.replace(self.config, **overrides)

    # ------------------------------------------------------------------------------------------------------------------
    def plot(self, ax: Axes):
        if self.ax is not None:
            raise ValueError("Series already plotted on an axis.")
        self.ax = ax
        if self.config.stairs:
            self.line = ax.step(self.x_data, self.y_data, **self._get_config_dict())[0]  # type: ignore
        else:
            self.line = ax.plot(self.x_data, self.y_data, **self._get_config_dict())[0]  # type: ignore

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, **kwargs) -> None:
        if "config" in kwargs:
            self.config = kwargs.pop("config")
        if kwargs:
            self.line.set(**kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def set_data(
            self,
            x_data: Iterable[float | int],
            y_data: Iterable[float | int],
            *,
            autoscale: bool = True,
    ) -> None:
        """
        Replace the data of this series and update the underlying Line2D.

        Parameters
        ----------
        x_data, y_data : iterables of numeric
            New data to display.
        autoscale : bool
            If True, relimit and autoscale the attached Axes.
        """
        self.x_data = x_data
        self.y_data = y_data

        if self.line is None:
            raise RuntimeError("Series has not been plotted yet; call axis.add_series() first.")

        # Update the Matplotlib artist
        self.line.set_xdata(x_data)
        self.line.set_ydata(y_data)

        # Optionally rescale axes
        if autoscale and self.ax is not None:
            self.ax.relim()
            self.ax.autoscale_view()

    # ------------------------------------------------------------------------------------------------------------------
    def _get_config_dict(self) -> dict:
        """Convert SeriesConfig into kwargs for ax.plot / ax.step.

        Every key is explicitly mapped from SeriesConfig fields
        to the actual Matplotlib keyword arguments.
        """
        cfg = dataclasses.asdict(self.config)

        out: dict = {
            # line style
            "color": cfg["color"],  # SeriesConfig.color -> Line2D(color=...)
            "linewidth": cfg["linewidth"],  # SeriesConfig.linewidth -> Line2D(linewidth=...)
            "linestyle": cfg["linestyle"],  # SeriesConfig.linestyle -> Line2D(linestyle=...)
            "alpha": cfg["alpha"],  # SeriesConfig.alpha -> Line2D(alpha=...)

            # label / visibility
            "label": cfg["label"],  # SeriesConfig.label -> Line2D(label=...)
            "visible": cfg["visible"],  # SeriesConfig.visible -> Line2D(visible=...)

            # markers
            "marker": cfg["marker"],  # SeriesConfig.marker -> Line2D(marker=...)
            "markersize": cfg["marker_size"],  # SeriesConfig.marker_size -> Line2D(markersize=...)
            "markerfacecolor": cfg["marker_facecolor"],  # SeriesConfig.marker_facecolor -> Line2D(markerfacecolor=...)
            "markeredgecolor": cfg["marker_edgecolor"],  # SeriesConfig.marker_edgecolor -> Line2D(markeredgecolor=...)
            "markevery": cfg["markevery"],
        }

        # Drop None values to let rcParams defaults apply
        out = {k: v for k, v in out.items() if v is not None}
        return out


# === LEGEND ============================================================================================================
@dataclasses.dataclass
class LegendConfig:
    """Legend styling configuration."""
    show: bool = True
    loc: str = "upper right"
    alpha: float = 1.0
    font_size: float | None = None
    marker_scale: float = 1.0
    line_width: float = 1.0
    font_color: str | Sequence[float] | None = 'black'
    background_color: str | Sequence[float] | None = 'white'
    edge_color: str | Sequence[float] | None = None
    border_width: float | None = None
    outside_right: bool = False
    outside_right_pad: float = 0.02


# === AXIS =============================================================================================================
@dataclasses.dataclass
class AxisConfig:
    """Axis-level configuration (titles, labels, ticks, grid, legend)."""
    facecolor: str | Sequence[float] | None = 'white'

    palette: list | None = None

    # Titles
    title: str | None = None
    title_font_size: float | None = None
    title_color: str | Sequence[float] | None = 'black'

    # Labels
    xlabel: str | None = None
    ylabel: str | None = None
    label_font_size: float | None = None
    label_color: str | Sequence[float] | None = 'black'

    # Ticks
    tick_font_size: float | None = None
    xtick_rotation: float = 0.0
    ytick_rotation: float = 0.0
    xticks: list[float] | None = None
    yticks: list[float] | None = None
    xticklabels: list[str] | None = None
    yticklabels: list[str] | None = None

    # Limits
    xlim: tuple[float, float] | None = None
    ylim: tuple[float, float] | None = None

    # Grid
    grid: bool = True
    grid_alpha: float = 0.8
    grid_linestyle: str = "--"
    grid_linewidth: float = 0.5
    grid_color: str | Sequence[float] | None = dataclasses.field(default_factory=lambda: [0.2, 0.2, 0.2])

    # Legend (accepts bool for convenience: True/False → LegendConfig(show=...))
    legend: LegendConfig | bool = dataclasses.field(default_factory=LegendConfig)

    def __post_init__(self):
        if isinstance(self.legend, bool):
            self.legend = LegendConfig(show=self.legend)


class Axis:
    id: str
    ax: Axes | None = None
    config: AxisConfig
    series: dict[str, Series]
    lines: dict[str, Line]
    labels: dict[str, Label]
    phases: dict[str, Phase]
    phase_bar_config: PhaseBarConfig | None = None
    background_phases: dict[str, BackgroundPhase]
    phase_background_config: PhaseBackgroundConfig | None = None

    _palette_index: int = 0

    # === INIT =========================================================================================================
    def __init__(self,
                 id: str,
                 config: AxisConfig | None = None,
                 **overrides):

        if id is None:
            id = generate_uuid()

        self.id = id

        if config is None:
            config = AxisConfig()
        self.config = config
        if overrides:
            self.config = dataclasses.replace(self.config, **overrides)

        self.series = {}
        self.lines = {}
        self.labels = {}
        self.phases: dict[str, Phase] = {}
        self.phase_bar_config: PhaseBarConfig | None = None
        self.background_phases: dict[str, BackgroundPhase] = {}
        self.phase_background_config: PhaseBackgroundConfig | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def add_series(self, series: Series) -> Series:
        if series.id in self.series:
            raise ValueError(f"Series with ID {series.id} already exists.")

        if self.ax is None:
            raise RuntimeError("Axis must be attached to a Matplotlib Axes before adding series. "
                               "Call plot.set_axis(row, col, axis) first.")

        self.series[series.id] = series

        if series.config.color is None:
            series.config.color = self._get_next_palette_color()

        series.plot(self.ax)
        self.update_legend()
        return series

    # ------------------------------------------------------------------------------------------------------------------
    def add_label(self, label: Label) -> Label:
        """
        Add a Label to this axis and plot it immediately if the axis
        is already attached to a Matplotlib Axes.
        """
        if label.id in self.labels:
            raise ValueError(f"Label with ID {label.id} already exists.")

        self.labels[label.id] = label

        if self.ax is not None:
            label.plot(self.ax)

        return label

    # ------------------------------------------------------------------------------------------------------------------
    def plot(self,
             x_data: Iterable[float | int],
             y_data: Iterable[float | int],
             line_config: SeriesConfig | None = None,
             **overrides):

        if line_config is None:
            line_config = SeriesConfig()

        if overrides:
            line_config = dataclasses.replace(line_config, **overrides)

        series = Series(generate_uuid(), x_data, y_data, line_config)

        return self.add_series(series)

    # ------------------------------------------------------------------------------------------------------------------
    def add_line(self, line: Line) -> None:
        if line.id in self.lines:
            raise ValueError(f"Line with ID {line.id} already exists.")
        self.lines[line.id] = line
        if self.ax is not None:
            line.plot(self.ax)
            self.update_legend()

    # ------------------------------------------------------------------------------------------------------------------
    def add_vertical_line(
            self,
            x: float,
            config: LineConfig | None = None,
            label: str | None = None,
            label_position: str = "above",
            label_config: LabelConfig | dict | None = None,
            **config_overrides,
    ) -> tuple[Line2D, Label | None]:
        """
        Add a vertical line at the specified x position spanning the full axis height.

        Parameters
        ----------
        x : float
            The x position for the vertical line.
        config : LineConfig | None
            Line configuration (color, linewidth, style, alpha). If None, uses defaults.
        label : str | None
            Optional text label to display at the line.
        label_position : str
            Where to place the label: "above" (top of axis) or "below" (bottom of axis).
            Default is "above".
        label_config : LabelConfig | dict | None
            Configuration for the label. Can be:
            - LabelConfig: used directly (with vertical_alignment overridden by label_position)
            - dict: fields to override on the default LabelConfig (e.g., {'fontsize': 10, 'color': 'red'})
            - None: uses sensible defaults
        **config_overrides :
            Override specific LineConfig fields (e.g., color='red', linewidth=2).

        Returns
        -------
        tuple[Line2D, Label | None]
            The created matplotlib Line2D artist and the Label object (if label was provided).
        """
        if self.ax is None:
            raise RuntimeError(
                "Axis must be attached to a Matplotlib Axes before adding vertical lines. "
                "Call plot.set_axis(row, col, axis) first."
            )

        # Build line config
        if config is None:
            config = LineConfig()
        if config_overrides:
            config = dataclasses.replace(config, **config_overrides)

        # Create vertical line using axvline (spans full y-axis automatically)
        line_artist = self.ax.axvline(
            x=x,
            color=config.color,
            linewidth=config.linewidth,
            linestyle=config.style,
            alpha=config.alpha,
        )

        # Optionally add label
        label_obj: Label | None = None
        if label is not None:
            # Determine y position based on label_position
            # Labels are placed INSIDE the axis area to remain visible
            y_min, y_max = self.ax.get_ylim()
            y_range = y_max - y_min
            padding = 0.02 * y_range  # Small padding from edge

            if label_position == "above":
                y_pos = y_max - padding
                v_align = "top"  # Top of label at y_pos, extends downward (visible)
            else:  # "below"
                y_pos = y_min + padding
                v_align = "bottom"  # Bottom of label at y_pos, extends upward (visible)

            # Build label config: start with defaults, then apply overrides
            default_label_config = LabelConfig(
                background_box=True,
                background_color="white",
                background_alpha=0.8,
                vertical_alignment=v_align,
                horizontal_alignment="center",
                fontsize=8,
                box_padding=0.2,
                offset_x=0,
                offset_y=0,
            )

            if label_config is None:
                label_config = default_label_config
            elif isinstance(label_config, dict):
                # Apply dict overrides to the default config
                label_config = dataclasses.replace(default_label_config, **label_config)
            else:
                # LabelConfig provided - override alignment based on position
                label_config = dataclasses.replace(
                    label_config,
                    vertical_alignment=v_align,
                )

            label_obj = Label(text=label, position=(x, y_pos), config=label_config)
            self.add_label(label_obj)

        return line_artist, label_obj

    # ------------------------------------------------------------------------------------------------------------------
    def configure_phase_bar(
            self,
            config: PhaseBarConfig | dict | None = None,
            **overrides,
    ) -> PhaseBarConfig:
        """
        Configure the phase bar for this axis.

        Must be called before adding phases. Can be called with a PhaseBarConfig,
        a dict of overrides, or keyword arguments.

        Parameters
        ----------
        config : PhaseBarConfig | dict | None
            Phase bar configuration. Can be:
            - PhaseBarConfig: used directly
            - dict: fields to override on default PhaseBarConfig
            - None: uses defaults (can still override with **overrides)
        **overrides :
            Override specific PhaseBarConfig fields.

        Returns
        -------
        PhaseBarConfig
            The configured phase bar config.

        Examples
        --------
        >>> axis.configure_phase_bar(position="top_inside", height=0.08)
        >>> axis.configure_phase_bar({'position': 'bottom_outside', 'fontsize': 9})
        >>> axis.configure_phase_bar(PhaseBarConfig(position="bottom_inside"))
        """
        if config is None:
            self.phase_bar_config = PhaseBarConfig()
        elif isinstance(config, dict):
            self.phase_bar_config = PhaseBarConfig(**config)
        else:
            self.phase_bar_config = config

        if overrides:
            self.phase_bar_config = dataclasses.replace(self.phase_bar_config, **overrides)

        return self.phase_bar_config

    # ------------------------------------------------------------------------------------------------------------------
    def add_phase(
            self,
            phase_id: str,
            start: float,
            end: float,
            config: PhaseConfig | dict | None = None,
            **overrides,
    ) -> Phase:
        """
        Add a phase to the phase bar.

        Parameters
        ----------
        phase_id : str
            The identifier/label for this phase (displayed as text).
        start : float
            Start time/x-value for the phase.
        end : float
            End time/x-value for the phase.
        config : PhaseConfig | dict | None
            Phase configuration. Can be:
            - PhaseConfig: used directly
            - dict: fields to override on default PhaseConfig
            - None: uses defaults
        **overrides :
            Override specific PhaseConfig fields (e.g., color='red', layer=1).

        Returns
        -------
        Phase
            The created Phase object.

        Examples
        --------
        >>> axis.add_phase("Init", start=0, end=2, color="blue")
        >>> axis.add_phase("Run", start=2, end=8, config={'color': 'green', 'layer': 1})
        """
        if self.ax is None:
            raise RuntimeError(
                "Axis must be attached to a Matplotlib Axes before adding phases. "
                "Call plot.set_axis(row, col, axis) first."
            )

        # Auto-configure phase bar if not done
        if self.phase_bar_config is None:
            self.configure_phase_bar()

        # Build phase config
        if config is None:
            phase_config = PhaseConfig(color=self.phase_bar_config.default_color)
        elif isinstance(config, dict):
            defaults = {'color': self.phase_bar_config.default_color}
            defaults.update(config)
            phase_config = PhaseConfig(**defaults)
        else:
            phase_config = config

        if overrides:
            phase_config = dataclasses.replace(phase_config, **overrides)

        # Create the phase
        phase = Phase(phase_id=phase_id, start=start, end=end, config=phase_config)
        self.phases[phase_id] = phase

        # Draw the phase
        self._draw_phase(phase)

        return phase

    # ------------------------------------------------------------------------------------------------------------------
    def _draw_phase(self, phase: Phase) -> None:
        """Internal method to draw a phase on the axis."""
        if self.ax is None or self.phase_bar_config is None:
            return

        bar_cfg = self.phase_bar_config
        layer = phase.config.layer

        # Calculate x padding in data units
        x_min, x_max = self.ax.get_xlim()
        x_range = x_max - x_min
        x_padding_data = bar_cfg.horizontal_padding * x_range

        # Calculate y position based on position setting and layer
        # We use a blended transform: x in data coords, y in axes coords
        from matplotlib.transforms import blended_transform_factory
        transform = blended_transform_factory(self.ax.transData, self.ax.transAxes)

        if bar_cfg.position == "bottom_outside":
            # Draw below the axis, accounting for tick labels and xlabel
            y_base = -bar_cfg.outside_offset - (bar_cfg.height + bar_cfg.layer_gap) * layer
            y_height = bar_cfg.height
        elif bar_cfg.position == "bottom_inside":
            # Draw at the bottom inside the axis with padding above x-axis
            y_base = bar_cfg.bottom_padding + (bar_cfg.height + bar_cfg.layer_gap) * layer
            y_height = bar_cfg.height
        else:  # "top_inside"
            # Draw at the top inside the axis with padding below top
            y_base = 1.0 - bar_cfg.top_padding - bar_cfg.height - (bar_cfg.height + bar_cfg.layer_gap) * layer
            y_height = bar_cfg.height

        phase.plot(self.ax, bar_cfg, y_base, y_height, transform, x_padding_data)

    # ------------------------------------------------------------------------------------------------------------------
    def redraw_phases(self) -> None:
        """Redraw all phases (useful after axis limits change)."""
        # Remove existing artists
        for phase in self.phases.values():
            if phase.rect_artist is not None:
                phase.rect_artist.remove()
                phase.rect_artist = None
            if phase.text_artist is not None:
                phase.text_artist.remove()
                phase.text_artist = None

        # Redraw all phases
        for phase in self.phases.values():
            self._draw_phase(phase)

    # ------------------------------------------------------------------------------------------------------------------
    def configure_phase_background(
            self,
            config: PhaseBackgroundConfig | dict | None = None,
            **overrides,
    ) -> PhaseBackgroundConfig:
        """
        Configure the phase background for this axis.

        Parameters
        ----------
        config : PhaseBackgroundConfig | dict | None
            Phase background configuration. Can be:
            - PhaseBackgroundConfig: used directly
            - dict: fields to override on default PhaseBackgroundConfig
            - None: uses defaults (can still override with **overrides)
        **overrides :
            Override specific PhaseBackgroundConfig fields.

        Returns
        -------
        PhaseBackgroundConfig
            The configured phase background config.

        Examples
        --------
        >>> axis.configure_phase_background(alpha=0.2, show_dividers=True)
        >>> axis.configure_phase_background({'label_position': 'bottom', 'fontsize': 9})
        """
        if config is None:
            self.phase_background_config = PhaseBackgroundConfig()
        elif isinstance(config, dict):
            self.phase_background_config = PhaseBackgroundConfig(**config)
        else:
            self.phase_background_config = config

        if overrides:
            self.phase_background_config = dataclasses.replace(self.phase_background_config, **overrides)

        return self.phase_background_config

    # ------------------------------------------------------------------------------------------------------------------
    def add_background_phase(
            self,
            phase_id: str,
            start: float,
            end: float,
            config: BackgroundPhaseConfig | dict | None = None,
            **overrides,
    ) -> BackgroundPhase:
        """
        Add a background phase (colored region) to the plot.

        Parameters
        ----------
        phase_id : str
            The identifier/label for this phase (displayed as text if show_labels=True).
        start : float
            Start time/x-value for the phase.
        end : float
            End time/x-value for the phase.
        config : BackgroundPhaseConfig | dict | None
            Phase configuration. Can be:
            - BackgroundPhaseConfig: used directly
            - dict: fields to override on default BackgroundPhaseConfig
            - None: uses defaults
        **overrides :
            Override specific BackgroundPhaseConfig fields (e.g., color='red', alpha=0.2).

        Returns
        -------
        BackgroundPhase
            The created BackgroundPhase object.

        Examples
        --------
        >>> axis.add_background_phase("Init", start=0, end=2, color="lightblue")
        >>> axis.add_background_phase("Run", start=2, end=8, config={'color': 'lightgreen'})
        """
        if self.ax is None:
            raise RuntimeError(
                "Axis must be attached to a Matplotlib Axes before adding background phases. "
                "Call plot.set_axis(row, col, axis) first."
            )

        # Auto-configure phase background if not done
        if self.phase_background_config is None:
            self.configure_phase_background()

        # Build phase config
        if config is None:
            phase_config = BackgroundPhaseConfig()
        elif isinstance(config, dict):
            phase_config = BackgroundPhaseConfig(**config)
        else:
            phase_config = config

        if overrides:
            phase_config = dataclasses.replace(phase_config, **overrides)

        # Create the phase
        phase = BackgroundPhase(phase_id=phase_id, start=start, end=end, config=phase_config)
        self.background_phases[phase_id] = phase

        # Draw the phase (we need to determine if it's the last one)
        self._redraw_background_phases()

        return phase

    # ------------------------------------------------------------------------------------------------------------------
    def _redraw_background_phases(self) -> None:
        """Internal method to redraw all background phases."""
        if self.ax is None or self.phase_background_config is None:
            return

        # Remove existing artists
        for phase in self.background_phases.values():
            if phase.span_artist is not None:
                phase.span_artist.remove()
                phase.span_artist = None
            if phase.line_artist is not None:
                phase.line_artist.remove()
                phase.line_artist = None
            if phase.text_artist is not None:
                phase.text_artist.remove()
                phase.text_artist = None

        # Sort phases by start time to determine which is last
        sorted_phases = sorted(self.background_phases.values(), key=lambda p: p.start)

        # Draw all phases
        for i, phase in enumerate(sorted_phases):
            is_last = (i == len(sorted_phases) - 1)
            phase.plot(self.ax, self.phase_background_config, is_last=is_last)

    # ------------------------------------------------------------------------------------------------------------------
    def attach_to(self, ax: Axes) -> None:
        """Attach this Axis to a concrete Matplotlib Axes and apply config."""
        self.ax = ax
        cfg = self.config

        # --- Facecolor -----------------------------------------------------------------------------------------------
        if cfg.facecolor is not None:
            ax.set_facecolor(cfg.facecolor)

        # --- Titles --------------------------------------------------------------------------------------------------
        if cfg.title is not None:
            title_kwargs: dict = {}
            if cfg.title_font_size is not None:
                title_kwargs["fontsize"] = cfg.title_font_size
            if cfg.title_color is not None:
                title_kwargs["color"] = cfg.title_color
            ax.set_title(cfg.title, **title_kwargs)

        # --- Axis labels ---------------------------------------------------------------------------------------------
        if cfg.xlabel is not None:
            ax.set_xlabel(cfg.xlabel)
        if cfg.ylabel is not None:
            ax.set_ylabel(cfg.ylabel)

        # Label style (size / color)
        if cfg.label_font_size is not None:
            ax.xaxis.label.set_size(cfg.label_font_size)  # type: ignore
            ax.yaxis.label.set_size(cfg.label_font_size)  # type: ignore
        if cfg.label_color is not None:
            ax.xaxis.label.set_color(cfg.label_color)
            ax.yaxis.label.set_color(cfg.label_color)

        # --- Ticks / tick labels -------------------------------------------------------------------------------------
        # Positions
        if cfg.xticks is not None:
            ax.set_xticks(cfg.xticks)
        if cfg.yticks is not None:
            ax.set_yticks(cfg.yticks)

        # Custom tick labels
        if cfg.xticklabels is not None:
            ax.set_xticklabels(cfg.xticklabels)
        if cfg.yticklabels is not None:
            ax.set_yticklabels(cfg.yticklabels)

        # Tick label font size
        if cfg.tick_font_size is not None:
            for label in ax.get_xticklabels() + ax.get_yticklabels():
                label.set_fontsize(cfg.tick_font_size)

        # Tick label rotation
        if cfg.xtick_rotation:
            for label in ax.get_xticklabels():
                label.set_rotation(cfg.xtick_rotation)
        if cfg.ytick_rotation:
            for label in ax.get_yticklabels():
                label.set_rotation(cfg.ytick_rotation)

        # --- Limits ---------------------------------------------------------------------------------------------------
        if cfg.xlim is not None:
            ax.set_xlim(cfg.xlim)
        if cfg.ylim is not None:
            ax.set_ylim(cfg.ylim)

        # --- Grid -----------------------------------------------------------------------------------------------------
        if cfg.grid:
            ax.grid(
                True,
                alpha=cfg.grid_alpha,
                linestyle=cfg.grid_linestyle,
                linewidth=cfg.grid_linewidth,
                color=cfg.grid_color,
            )
        else:
            ax.grid(False)

    # ------------------------------------------------------------------------------------------------------------------
    # def update_legend(self) -> None:
    #     if self.ax is None:
    #         return
    #
    #     ax = self.ax
    #     cfg = self.config
    #
    #     # If legends are disabled, remove any existing legend and bail out
    #     if not cfg.legend:
    #         leg = ax.get_legend()
    #         if leg is not None:
    #             leg.remove()
    #         return
    #
    #     # Get handles/labels from the axis
    #     handles, labels = ax.get_legend_handles_labels()
    #
    #     # Filter out empty / "private" labels (Matplotlib convention)
    #     filtered = [
    #         (h, l)
    #         for h, l in zip(handles, labels)
    #         if l and not l.startswith("_")
    #     ]
    #     if not filtered:
    #         # Nothing to show: remove existing legend if there is one
    #         leg = ax.get_legend()
    #         if leg is not None:
    #             leg.remove()
    #         return
    #
    #     handles, labels = zip(*filtered)  # type: ignore
    #
    #     legend_kwargs: dict = {
    #         "loc": cfg.legend_loc,
    #         "markerscale": cfg.legend_marker_scale,
    #     }
    #     if cfg.legend_font_size is not None:
    #         legend_kwargs["fontsize"] = cfg.legend_font_size
    #
    #     # Optional: move legend outside to the right of the axes
    #     if getattr(cfg, "legend_outside_right", False):
    #         pad = getattr(cfg, "legend_outside_right_pad", 0.02)
    #         # place legend just to the right of the axes, vertically centered
    #         legend_kwargs["loc"] = "center left"
    #         legend_kwargs["bbox_to_anchor"] = (1.0 + pad, 0.5)
    #         legend_kwargs["borderaxespad"] = 0.0
    #
    #     # Create / update legend
    #     leg = ax.legend(handles, labels, **legend_kwargs)
    #
    #     # Extra styling on legend
    #     if cfg.legend_line_width is not None:
    #         for line in leg.get_lines():
    #             line.set_linewidth(cfg.legend_line_width)
    #
    #     if cfg.legend_font_color is not None:
    #         for text in leg.get_texts():
    #             text.set_color(cfg.legend_font_color)
    #
    #     if cfg.legend_alpha is not None:
    #         leg.get_frame().set_alpha(cfg.legend_alpha)
    #
    #     if cfg.legend_background_color is not None:
    #         leg.get_frame().set_facecolor(cfg.legend_background_color)
    # ------------------------------------------------------------------------------------------------------------------
    def update_legend(self) -> None:
        if self.ax is None:
            return

        ax = self.ax
        lcfg = self.config.legend

        # If legends are disabled, remove any existing legend and exit
        if not lcfg.show:
            leg = ax.get_legend()
            if leg is not None:
                leg.remove()
            return

        handles, labels = ax.get_legend_handles_labels()

        # Filter out empty / private labels
        filtered = [(h, l) for h, l in zip(handles, labels) if l and not l.startswith("_")]
        if not filtered:
            leg = ax.get_legend()
            if leg is not None:
                leg.remove()
            return

        handles, labels = zip(*filtered)

        legend_kwargs = dict(
            loc=lcfg.loc,
            markerscale=lcfg.marker_scale,
        )

        if lcfg.font_size is not None:
            legend_kwargs["fontsize"] = lcfg.font_size

        # Optional legend outside placement
        if lcfg.outside_right:
            legend_kwargs["loc"] = "center left"
            legend_kwargs["bbox_to_anchor"] = (1.0 + lcfg.outside_right_pad, 0.5)
            legend_kwargs["borderaxespad"] = 0.0

        # Create/update legend
        leg = ax.legend(handles, labels, **legend_kwargs)

        # linewidth
        if lcfg.line_width is not None:
            for line in leg.get_lines():
                line.set_linewidth(lcfg.line_width)

        # text colors
        if lcfg.font_color is not None:
            for text in leg.get_texts():
                text.set_color(lcfg.font_color)

        # --- Frame styling ----------------------------------------------------------------
        frame = leg.get_frame()

        # Background color with alpha handling
        bg = lcfg.background_color
        rgba = None

        if isinstance(bg, (list, tuple)) and len(bg) in (3, 4):
            if len(bg) == 3:
                rgba = (*bg, lcfg.alpha)
            else:
                rgba = bg
                frame.set_alpha(bg[3])
        else:
            frame.set_alpha(lcfg.alpha)

        if rgba is not None:
            frame.set_facecolor(rgba)
        elif bg is not None:
            frame.set_facecolor(bg)

        # Edge color
        if lcfg.edge_color is not None:
            frame.set_edgecolor(lcfg.edge_color)

        # Border width
        if lcfg.border_width is not None:
            frame.set_linewidth(lcfg.border_width)

    # ------------------------------------------------------------------------------------------------------------------
    def remove_series(self, series_id: str) -> None:
        series = self.series.pop(series_id, None)
        if series is None:
            return
        if series.line is not None:
            series.line.remove()
        self.update_legend()

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self) -> None:
        if self.ax is not None:
            self.ax.cla()
        self.series.clear()
        self._palette_index = 0

    # ------------------------------------------------------------------------------------------------------------------
    def add_small_label(
            self,
            label: str,
            *,
            boxed: bool = False,
            box_facecolor: str | Sequence[float] | None = "white",
            box_edgecolor: str | Sequence[float] | None = "black",
            box_alpha: float = 0.8,
            padding: float = 0.2,
            fontsize: float | None = 5,
            text_kwargs: dict[str, Any] | None = None,
    ) -> Artist:
        """
        Add a small, right-aligned label in the lower-right corner
        of THIS axis (inside the axes, using axes coordinates).

        Coordinates are in axes-fraction space:
        (0,0) bottom-left; (1,1) top-right.

        Parameters
        ----------
        label : str
            Text to display.
        boxed : bool, default False
            If True, draw a small box behind the text.
        box_facecolor, box_edgecolor, box_alpha, padding:
            Box aesthetics (as for Plot.add_small_label).
        fontsize : float, optional
            Font size. If None, falls back to global font size.
        text_kwargs : dict, optional
            Extra kwargs forwarded to `Axes.text`.

        Returns
        -------
        Artist
            The created Text artist.
        """
        if self.ax is None:
            raise RuntimeError(
                "Axis must be attached to a Matplotlib Axes before adding labels. "
                "Call plot.set_axis(row, col, axis) first."
            )

        if text_kwargs is None:
            text_kwargs = {}

        # Axes coordinates: bottom-right inside the axes
        if boxed:
            x = 0.98
            y = 0.02
        else:
            x = 0.995
            y = 0.005

        bbox = None
        if boxed:
            bbox = dict(
                boxstyle=f"round,pad={padding}",
                facecolor=box_facecolor if box_facecolor is not None else "none",
                edgecolor=box_edgecolor,
                linewidth=0.5,
                alpha=box_alpha,
            )

        text = self.ax.text(
            x,
            y,
            label,
            ha="right",
            va="bottom",
            fontsize=fontsize,
            alpha=0.7,
            bbox=bbox,
            transform=self.ax.transAxes,
            zorder=50,
            **text_kwargs,
        )
        return text

    # ------------------------------------------------------------------------------------------------------------------
    def _get_next_palette_color(self):
        """
        Return the next color from the palette, or None if no palette is set.
        Does NOT advance the Matplotlib color cycle, just our own.
        """
        if not self.config.palette:
            return None

        color = self.config.palette[self._palette_index % len(self.config.palette)]  # type: ignore
        self._palette_index += 1
        return color


# === PLOT =============================================================================================================
@dataclasses.dataclass
class PlotConfig:
    """Global plot / figure-level configuration."""
    size: tuple[float, float] = (10, 5)
    dpi: int = 1000
    facecolor: str | Sequence[float] | None = 'white'  # a named color or RGB tuple or 'transparent'
    facealpha: float = 1.0
    tight_layout: bool = True

    # Figure title (suptitle)
    title: str | None = None
    title_font_size: float | None = None

    # Shared axes
    sharex: bool = False
    sharey: bool = False

    # Global style
    use_latex: bool = False
    # font_family: str = "sans-serif"
    font_family: str = "sans-serif"
    font_size: float = 10.0

    # Save config
    save_dpi: int | None = None
    save_transparent: bool = False


class Plot:
    config: PlotConfig
    figure: Figure
    axes: dict[str, Axis]

    # === INIT =========================================================================================================
    def __init__(self,
                 rows: int = 1,
                 columns: int = 1,
                 config: PlotConfig | None = None,
                 use_agg_backend: bool = False,
                 **overrides):

        from matplotlib import pyplot

        if config is None:
            config = PlotConfig()

        if overrides:
            config = dataclasses.replace(config, **overrides)

        self.config = config

        self._rows = rows
        self._columns = columns

        if use_agg_backend:
            matplotlib.use("Agg", force=True)

        self._apply_global_style()

        fig, ax = pyplot.subplots(
            rows,
            columns,
            figsize=self.config.size,
            dpi=self.config.dpi,
            facecolor=self.config.facecolor,
            sharex=self.config.sharex,
            sharey=self.config.sharey,
        )
        self.figure = fig
        self.figure.patch.set_alpha(self.config.facealpha)

        # Figure title (suptitle)
        if self.config.title is not None:
            suptitle_kwargs = {}
            if self.config.title_font_size is not None:
                suptitle_kwargs['fontsize'] = self.config.title_font_size
            self.figure.suptitle(self.config.title, **suptitle_kwargs)

        # Normalize ax -> 2D list [row][col]
        if isinstance(ax, np.ndarray):
            if rows == 1 and columns == 1:
                ax_grid = [[ax.item()]]
            elif rows == 1:
                ax_grid = [list(ax)]
            elif columns == 1:
                ax_grid = [[a] for a in ax]
            else:
                ax_grid = ax.tolist()
        else:
            ax_grid = [[ax]]

        self._ax_grid: list[list[Axes]] = ax_grid

        # Store logical Axis objects here (if you want to access by ID later)
        self.axes: dict[str, Axis] = {}

        if self.config.tight_layout:
            self.figure.tight_layout()

    # ------------------------------------------------------------------------------------------------------------------
    def set_axis(self, row: int, column: int, axis: Axis) -> None:
        if row < 1 or row > self._rows:
            raise ValueError(f"Invalid row: {row}")
        if column < 1 or column > self._columns:
            raise ValueError(f"Invalid column: {column}")

        mpl_ax = self.get_mpl_axes(row, column)

        # Attach custom Axis to this Matplotlib Axes and apply config
        axis.attach_to(mpl_ax)

        # Remember it, e.g. to access by ID later
        self.axes[axis.id] = axis
        self.figure.tight_layout()

    # ------------------------------------------------------------------------------------------------------------------
    def get_axis(self, row: int, column: int) -> Axis | None:
        # If you want the logical Axis
        for axis in self.axes.values():
            if axis.ax is self.get_mpl_axes(row, column):
                return axis
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def show(self):
        # Open up the figure
        self.figure.tight_layout()
        plt.show()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self) -> None:
        try:
            plt.close(self.figure)
        except Exception:
            pass

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self) -> None:
        for row in self._ax_grid:
            for ax in row:
                ax.cla()
        for axis in self.axes.values():
            axis.series.clear()

    # ------------------------------------------------------------------------------------------------------------------
    def save(self, filename: str, format: str, show: bool = False, **kwargs):
        """
        Save the figure in the given format ("png" or "pdf").
        Parameters
        ----------
        format : str
            The output format. Supported: "png", "pdf".
        filename : str
            Output file path (without extension or with—both allowed).
        **kwargs :
            Extra parameters forwarded directly to `Figure.savefig()`.
        """
        fmt = format.lower().strip()

        if fmt not in ("png", "pdf"):
            raise ValueError(f"Unsupported format '{format}'. Expected 'png' or 'pdf'.")

        # Normalize filename extension
        if not filename.lower().endswith(f".{fmt}"):
            filename = f"{filename}.{fmt}"

        # Default save dpi/transparent come from PlotConfig
        cfg = self.config

        save_kwargs = {
            "dpi": cfg.save_dpi if cfg.save_dpi is not None else cfg.dpi,
            "transparent": cfg.save_transparent,
            "facecolor": self.figure.get_facecolor(),
            "format": fmt,
        }

        # Allow user overrides through kwargs
        save_kwargs.update(kwargs)

        # Use tight_layout
        if cfg.tight_layout:
            self.figure.tight_layout()

        self.figure.savefig(filename, **save_kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def save_as_pgfplot(self, filename: str, **kwargs):
        # TODO: Do not add
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def show_temp_pdf(self):
        pdf_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf_path = pdf_file.name
        pdf_file.close()

        self.save(pdf_path, "pdf")
        open_file_preview(pdf_path)

    # ------------------------------------------------------------------------------------------------------------------
    def get_mpl_axes(self, row: int, column: int) -> Axes:
        """1-based (row, column) -> Matplotlib Axes."""
        return self._ax_grid[row - 1][column - 1]

    # ------------------------------------------------------------------------------------------------------------------
    def add_small_label(
            self,
            label: str,
            *,
            boxed: bool = False,
            box_facecolor: str | Sequence[float] | None = "white",
            box_edgecolor: str | Sequence[float] | None = "black",
            box_alpha: float = 0.8,
            padding: float = 0.2,
            fontsize: float | None = 5,
            text_kwargs: dict[str, Any] | None = None,
    ) -> Artist:
        """
        Add a small, right-aligned label in the lower-right corner
        of the *figure* (figure coordinates).

        Parameters
        ----------
        label : str
            Text to display.
        boxed : bool, default False
            If True, draw a small box behind the text.
        box_facecolor : color, optional
            Facecolor of the box (only used if boxed=True).
        box_edgecolor : color, optional
            Edge color of the box (only used if boxed=True).
        box_alpha : float, default 0.8
            Alpha of the box background.
        padding : float, default 0.2
            Padding inside the bbox (in bbox "pad" units).
        fontsize : float, optional
            Font size for the label. If None, a slightly smaller
            version of the global font size is used.
        text_kwargs : dict, optional
            Extra kwargs forwarded to `Figure.text`.

        Returns
        -------
        Artist
            The created Text artist.
        """
        if text_kwargs is None:
            text_kwargs = {}

        # Figure coordinates: (0,0) bottom-left, (1,1) top-right

        if not boxed:
            x = 0.995
            y = 0.005
        else:
            x = 0.99
            y = 0.01

        bbox = None
        if boxed:
            bbox = dict(
                boxstyle=f"round,pad={padding}",
                facecolor=box_facecolor if box_facecolor is not None else "none",
                edgecolor=box_edgecolor,
                linewidth=0.5,
                alpha=box_alpha,
            )

        text = self.figure.text(
            x,
            y,
            label,
            ha="right",
            va="bottom",
            fontsize=fontsize,
            alpha=0.7,
            bbox=bbox,
            transform=self.figure.transFigure,
            zorder=100,
            **text_kwargs,
        )
        return text

    # ------------------------------------------------------------------------------------------------------------------
    # def add_small_label_left(
    #         self,
    #         label: str,
    #         *,
    #         url: str | None = None,
    #         boxed: bool = False,
    #         box_facecolor: str | Sequence[float] | None = "white",
    #         box_edgecolor: str | Sequence[float] | None = "black",
    #         box_alpha: float = 0.8,
    #         padding: float = 0.2,
    #         fontsize: float | None = None,
    #         text_kwargs: dict[str, Any] | None = None,
    # ) -> Artist:
    #     """
    #     Add a small, left-aligned label in the lower-left corner
    #     of the *figure* (figure coordinates), optionally as a
    #     clickable hyperlink in PDF output.
    #
    #     Parameters
    #     ----------
    #     label : str
    #         Text to display.
    #     url : str, optional
    #         If provided, this will be embedded as a clickable
    #         link in the PDF (for backends that support it).
    #     boxed : bool, default False
    #         If True, draw a small box behind the text.
    #     box_facecolor : color, optional
    #         Facecolor of the box (only used if boxed=True).
    #     box_edgecolor : color, optional
    #         Edge color of the box (only used if boxed=True).
    #     box_alpha : float, default 0.8
    #         Alpha of the box background.
    #     padding : float, default 0.2
    #         Padding inside the bbox (in bbox "pad" units).
    #     fontsize : float, optional
    #         Font size for the label. If None, a slightly smaller
    #         version of the global font size is used.
    #     text_kwargs : dict, optional
    #         Extra kwargs forwarded to `Figure.text`.
    #
    #     Returns
    #     -------
    #     Artist
    #         The created Text artist.
    #     """
    #     if text_kwargs is None:
    #         text_kwargs = {}
    #
    #     # Slightly smaller than the global font, but at least 6 pt
    #     if fontsize is None:
    #         base_size = self.config.font_size
    #         fontsize = max(base_size * 0.7, 6.0)
    #
    #     # Figure coordinates: (0,0) bottom-left, (1,1) top-right
    #     if not boxed:
    #         x = 0.005
    #         y = 0.005
    #     else:
    #         x = 0.01
    #         y = 0.01
    #
    #     bbox = None
    #     if boxed:
    #         bbox = dict(
    #             boxstyle=f"round,pad={padding}",
    #             facecolor=box_facecolor if box_facecolor is not None else "none",
    #             edgecolor=box_edgecolor,
    #             linewidth=0.5,
    #             alpha=box_alpha,
    #         )
    #
    #     text = self.figure.text(
    #         x,
    #         y,
    #         label,
    #         ha="left",
    #         va="bottom",
    #         fontsize=fontsize,
    #         alpha=0.7,
    #         bbox=bbox,
    #         transform=self.figure.transFigure,
    #         zorder=100,
    #         **text_kwargs,
    #     )
    #
    #     # This is the crucial bit: PDF backend will create a clickable link
    #     if url:
    #         text.set_url(url)
    #
    #     return text

    def add_small_label_left(
            self,
            label: str,
            *,
            url: str | None = None,
            boxed: bool = False,
            box_facecolor: str | Sequence[float] | None = "white",
            box_edgecolor: str | Sequence[float] | None = "black",
            box_alpha: float = 0.8,
            padding: float = 0.2,
            fontsize: float | None = 10,
            icon_path: str | None = None,
            text_kwargs: dict[str, Any] | None = None,
    ) -> Artist:
        import matplotlib.pyplot as _plt
        from matplotlib.text import Text

        if text_kwargs is None:
            text_kwargs = {}

        fig = self.figure

        # Figure coordinates: (0,0) bottom-left, (1,1) top-right
        if boxed:
            x = 0.015
            y = 0.015
        else:
            x = 0.005
            y = 0.005

        # --- No icon: just text ---------------------------------------------------
        if icon_path is None:
            bbox = None
            if boxed:
                bbox = dict(
                    boxstyle=f"round,pad={padding}",
                    facecolor=box_facecolor if box_facecolor is not None else "none",
                    edgecolor=box_edgecolor,
                    linewidth=0.5,
                    alpha=box_alpha,
                )

            text = fig.text(
                x,
                y,
                label,
                ha="left",
                va="bottom",
                fontsize=fontsize,
                alpha=0.7,
                bbox=bbox,
                transform=fig.transFigure,
                zorder=100,
                **text_kwargs,
            )
            if url:
                text.set_url(url)
            return text

        # --- Icon + text ----------------------------------------------------------
        img = _plt.imread(icon_path)
        img_h_px = img.shape[0] if img.ndim >= 2 else 1

        # Desired icon height in *points*.
        # Use = fontsize for same height, or slightly smaller if you prefer.
        desired_icon_height_pt = fontsize * 1.0  # or 0.9 * fontsize for a bit smaller

        if img_h_px <= 0:
            zoom = 1.0
        else:
            # CRUCIAL: zoom is in "points per image-pixel" because OffsetImage
            # internally multiplies by dpi/72 via points_to_pixels(1).
            zoom = desired_icon_height_pt / img_h_px

        icon_box = OffsetImage(img, zoom=zoom)  # dpi_cor=True by default

        label_box = TextArea(
            label,
            textprops=dict(
                fontsize=fontsize,
                alpha=0.7,
                **text_kwargs,
            ),
        )

        packed = HPacker(
            children=[icon_box, label_box],
            align="center",
            pad=0,
            sep=4,
        )

        bboxprops = None
        frameon = False
        if boxed:
            frameon = True
            bboxprops = dict(
                boxstyle=f"round,pad={padding}",
                facecolor=box_facecolor if box_facecolor is not None else "none",
                edgecolor=box_edgecolor,
                linewidth=0.5,
                alpha=box_alpha,
            )

        ab = AnnotationBbox(
            packed,
            xy=(x, y),
            xycoords="figure fraction",
            box_alignment=(0.0, 0.0),
            bboxprops=bboxprops,
            frameon=frameon,
            zorder=100,
        )

        if url:
            txt_attr = getattr(label_box, "_text", None)
            if isinstance(txt_attr, Text):
                txt_attr.set_url(url)
            elif isinstance(txt_attr, list):
                for t in txt_attr:
                    if isinstance(t, Text):
                        t.set_url(url)

        fig.add_artist(ab)
        return ab

    # ------------------------------------------------------------------------------------------------------------------
    def _apply_global_style(self) -> None:
        """Apply global rcParams based on PlotConfig (LaTeX, fonts, etc.)."""
        cfg = self.config
        rc = matplotlib.rcParams

        # Font settings (apply always)
        rc["font.family"] = cfg.font_family
        rc["font.size"] = cfg.font_size

        # LaTeX usage
        if cfg.use_latex:
            rc["text.usetex"] = True
            # Don't reset text.latex.preamble — respect whatever was set via rcParams
        else:
            rc["text.usetex"] = False


# === HELPERS ==========================================================================================================
def open_file_preview(file):
    system = platform.system()

    try:
        if system == "Darwin":
            if shutil.which("open"):
                # Try Preview explicitly; fallback to generic open
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
            # Use 'start' through the shell
            os.startfile(file)  # type: ignore[attr-defined]
            return
    except Exception:
        # Swallow open errors silently; caller may handle if needed.
        pass


# ----------------------------------------------------------------------------------------------------------------------
def figure_to_png_bytes(
        fig,
        *,
        dpi: int = 120,
        transparent: bool = True,
        bbox_inches: Optional[str] = "tight",
        pad_inches: float = 0.05,
) -> bytes:
    """
    Render a (Agg) Figure to PNG bytes without touching disk.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: F401
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=dpi,
        transparent=transparent,
        bbox_inches=bbox_inches,
        pad_inches=pad_inches,
    )
    return buf.getvalue()


# ----------------------------------------------------------------------------------------------------------------------
def figure_to_data_uri(
        fig,
        *,
        dpi: int = 120,
        fmt: str = "png",
        transparent: bool = False,
        bbox_inches: Optional[str] = "tight",
        pad_inches: float = 0.05,
) -> str:
    """
    Render a (Agg) Figure to a data URI.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: F401

    def bytes_to_data_uri(raw: bytes, mime: str = "image/png") -> str:
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:{mime};base64,{b64}"

    buf = io.BytesIO()
    fig.savefig(
        buf,
        format=fmt,
        dpi=dpi,
        transparent=transparent,
        bbox_inches=bbox_inches,
        pad_inches=pad_inches,
    )
    mime = f"image/{fmt.lower()}"
    return bytes_to_data_uri(buf.getvalue(), mime=mime)


def quick_plot(
        x: Optional[Sequence[float] | np.ndarray],
        y: Sequence[float]
           | np.ndarray
           | Sequence[Sequence[float] | np.ndarray],
        *,
        title: str | None = None,
        xlabel: str | None = None,
        ylabel: str | None = None,
        labels: Optional[Sequence[str]] = None,
        xlim: Optional[tuple[float, float]] = None,
        ylim: Optional[tuple[float, float]] = None,
        size: tuple[float, float] = (8.0, 4.0),
        legend: bool = True,
        grid: bool = True,
        use_latex: bool = False,
        font_family: str = "sans-serif",
        font_size: float = 14.0,
        palette: Optional[Sequence] = None,
        use_agg_backend: bool = True,
        open_pdf: bool = True,
        stairs: bool = True,
) -> Plot:
    """
    Quick helper to plot one or multiple y-series (optionally over a given x),
    save to a temp PDF and open it in Preview (via Plot.show_temp_pdf).

    Parameters
    ----------
    x :
        Optional x data. If None, x is taken as range(len(first_y)).
    y :
        - Single series: 1D array-like (list, np.ndarray, etc.)
        - Multiple series:
            * list/tuple of 1D array-likes: [y1, y2, ...]
            * 2D np.ndarray: shape (n_series, n_points)
    title, xlabel, ylabel :
        Axis labels & title.
    labels :
        Optional list of legend labels, one per y-series.
    xlim, ylim :
        Optional axis limits.
    size :
        Figure size in inches.
    legend :
        Whether to show a legend (only shown if labels are non-empty).
    grid :
        Whether to show a grid.
    use_latex :
        If True, enable LaTeX rendering in the plot.
    font_family, font_size :
        Global font config.
    palette :
        Optional list of colors to use for the series. If None, uses
        get_palette('dark', n_series).
    use_agg_backend :
        If True, use Agg backend so this can be called from non-main threads.
    open_pdf :
        If True, save to a temp PDF and open it via Preview (macOS) /
        xdg-open (Linux) / startfile (Windows).
    stairs: If True, plots as steps
    Returns
    -------
    Plot
        The created Plot instance (so you can further tweak or save).

    Args:

    """

    # --- Normalize y into a list of 1D arrays ----------------------------------------------------
    ys: list[np.ndarray]

    # Case 1: list/tuple of series -> [y1, y2, ...]
    if isinstance(y, (list, tuple)) and len(y) > 0 and isinstance(
            y[0], (list, tuple, np.ndarray)
    ):
        ys = [np.asarray(yi) for yi in y]  # type: ignore[arg-type]
    else:
        # Case 2: single series or 2D ndarray
        arr = np.asarray(y)
        if arr.ndim == 1:
            ys = [arr]
        elif arr.ndim == 2:
            ys = [arr[i, :] for i in range(arr.shape[0])]
        else:
            raise ValueError("`y` must be 1D (single series) or 2D (multiple series).")

    if len(ys) == 0:
        raise ValueError("No y-series provided.")

    # --- Handle x -------------------------------------------------------------------------------
    if x is None:
        n = ys[0].shape[0]
        for yi in ys:
            if yi.shape[0] != n:
                raise ValueError("All y-series must have the same length when x is None.")
        x_data: Sequence[float] = np.arange(n)
    else:
        x_data_arr = np.asarray(x)
        n = x_data_arr.shape[0]
        for yi in ys:
            if yi.shape[0] != n:
                raise ValueError("All y-series must have the same length as x.")
        x_data = x_data_arr

    # --- Palette --------------------------------------------------------------------------------
    if palette is None:
        palette = get_palette("dark", len(ys))

    # --- Build Plot & Axis ----------------------------------------------------------------------
    plot_cfg = PlotConfig(
        size=size,
        use_latex=use_latex,
        font_family=font_family,
        font_size=font_size,
    )
    plot = Plot(
        rows=1,
        columns=1,
        config=plot_cfg,
        use_agg_backend=use_agg_backend,
    )

    axis_cfg = AxisConfig(
        title=title,
        xlabel=xlabel,
        ylabel=ylabel,
        xlim=xlim,
        ylim=ylim,
        legend=legend,
        grid=grid,
        palette=list(palette),
    )
    axis = Axis(id="quick_plot_axis", config=axis_cfg)
    plot.set_axis(1, 1, axis)

    # --- Add series -----------------------------------------------------------------------------
    for idx, yi in enumerate(ys):
        label = None
        if labels is not None and idx < len(labels):
            label = labels[idx]
        axis.plot(x_data, yi, label=label, stairs=stairs)

    # --- Show / open PDF ------------------------------------------------------------------------
    if open_pdf:
        plot.show_temp_pdf()

    return plot


# === SPECIAL PLOTS ====================================================================================================
# TODO: ignore them for now
# class UpdatablePlot:
#     ...
#
#
# class RealTimePlot:
#     ...
#
#
# class PDF_Plot:
#     ...

# === SERIALIZATION ====================================================================================================


if __name__ == '__main__':
    # --- Data --------------------------------------------------------------
    x = np.linspace(0, 10, 300)
    y1 = np.sin(x)
    y2 = np.cos(x)
    y3 = np.sin(x * 0.5) * 0.7
    y4 = np.cos(x * 1.5) * 0.4

    # --- Plot Init ---------------------------------------------------------
    plot = Plot(rows=1, columns=1, size=(8, 4), use_agg_backend=False)

    axis_cfg = AxisConfig(
        title="Multiple Time Series",
        xlabel="Time [s]",
        ylabel="Value",
        grid=True,
    )

    axis = Axis(id="main", config=axis_cfg)
    plot.set_axis(1, 1, axis)

    # --- Add 4 time series -------------------------------------------------
    axis.plot(x, y1, label="sin(x)", color="tab:blue")
    axis.plot(x, y2, label="cos(x)", color="tab:red")
    axis.plot(x, y3, label="0.7·sin(0.5x)", color="tab:green")
    axis.plot(x, y4, label="0.4·cos(1.5x)", color="tab:purple")

    # --- Show --------------------------------------------------------------
    plot.show_temp_pdf()  # or plot.save(...)

    # x = np.linspace(0, 2 * np.pi, 200)
    # y_sin = np.sin(x)
    # y_cos = np.cos(x)
    #
    # quick_plot(
    #     x=x,
    #     y=[y_sin, y_cos],  # multiple series
    #     title="Sine and Cosine",
    #     xlabel="x",
    #     ylabel="Value",
    #     labels=["sin(x)", "cos(x)"],  # legend labels
    #     xlim=(0, 2 * np.pi),
    #     ylim=(-1.5, 1.5),
    # )
    #
    # x = np.linspace(0, 2 * np.pi, 200)
    #
    # plot = Plot(rows=1,
    #             columns=2,
    #             size=(6, 3),
    #             use_agg_backend=False,
    #             facealpha=0,
    #             use_latex=True,
    #             font_family="Palatino")
    #
    # # Top-left axis
    #
    # palette = get_palette('dark', 3)
    #
    # ax_cfg1 = AxisConfig(title="Sine",
    #                      xlabel="$x$",
    #                      ylabel="$\sin(x)$",
    #                      legend=True,
    #                      palette=palette,
    #                      xlim=(0, 10),
    #                      ylim=(-1.5, 1.5),
    #                      facecolor=(1, 0, 0, 0))
    #
    # axis1 = Axis(id="sine_axis", config=ax_cfg1)
    # plot.set_axis(1, 1, axis1)
    #
    # axis1.plot(x, np.sin(x), label="sin", linestyle="--", alpha=1, color='tab:blue')
    # axis1.plot(x, np.cos(x), label="cos", color=[1, 0, 0], alpha=0.5)
    #
    # line1 = Line(start=(3, -3), end=(3, 10), linewidth=1, style="--", color=(0.2, 0.2, 0.2), alpha=0.9)
    # axis1.add_line(line1)
    #
    # label_cfg = LabelConfig(
    #     color="black",
    #     background_box=True,
    #     fontsize=10,
    #     background_color="white",
    #     background_alpha=0.8,
    #     vertical_alignment='bottom',
    #     horizontal_alignment='right',
    # )
    #
    # lbl = Label("Label", position=(8, 0), config=label_cfg)
    # axis1.add_label(lbl)
    # axis1.add_small_label('123456', boxed=True)
    #
    # # Top-right axis
    # ax_cfg2 = AxisConfig(title="Cosine", xlabel="x", ylabel="cos(x)", facecolor=(0, 1, 0, 0.25))
    # axis2 = Axis(id="cos_axis", config=ax_cfg2)
    # plot.set_axis(1, 2, axis2)
    # l2 = axis2.plot(x, np.cos(x), label="cos", color="red", marker='o', markevery=10)
    #
    # y_data = 0.2 * np.cos(x)
    # l2.set_data(x, y_data)
    # plot.add_small_label('2025-11-16_PlotX-1', boxed=True)
    #
    # plot.add_small_label_left(
    #     'Experiment Video',
    #     url='https://example.com/docs',
    #     boxed=True,
    #     icon_path='./youtube_logo.png',
    #     fontsize=11
    # )
    #
    # plot.show_temp_pdf()
    # # plot.show()
    # plot.save('/Users/lehmann/Desktop/test', 'pdf')
    # plot.save('/Users/lehmann/Desktop/test', 'png')
