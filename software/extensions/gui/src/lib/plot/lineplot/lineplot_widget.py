# # lineplot_backend.py
#
# from __future__ import annotations
# from dataclasses import dataclass, field, asdict
# from typing import Dict, List, Tuple, Optional, Any, Iterable
# import copy
#
# from core.utils.time import delayed_execution
# from extensions.gui.src.lib.objects.objects import GUI_Object
#
#
# # ---- helpers -----------------------------------------------------------------
#
# def _merge(base: dict, *updates: dict) -> dict:
#     out = copy.deepcopy(base)
#     for u in updates:
#         if not u:
#             continue
#         for k, v in u.items():
#             if isinstance(v, dict) and isinstance(out.get(k), dict):
#                 out[k] = _merge(out[k], v)
#             else:
#                 out[k] = copy.deepcopy(v)
#     return out
#
#
# Color = Tuple[float, float, float, float]  # RGBA floats 0..1
# Point = Tuple[float, float]
#
# # ---- default configs (mirror the JS defaults) --------------------------------
# # Notes:
# # - Colors are RGBA tuples (r,g,b,a) with floats in [0,1] unless noted.
# # - Many string enums list typical values; backends may support more.
#
# DEFAULT_X = {
#     'id': 'x',  # str: Axis ID. Any non-empty string.
#     'type': 'linear',  # str: 'linear' | 'time' | 'log' | 'category'
#     'unit': '',  # str: Unit label (e.g., 's', 'Hz'); free text.
#     'min': 'auto',  # float | int | 'auto': Lower bound; 'auto' to infer from data.
#     'max': 'auto',  # float | int | 'auto': Upper bound; 'auto' to infer from data.
#     'step_size': 1,  # float > 0: Tick step (only if ticks_mode='auto').
#     'color': (0.7, 0.7, 0.7, 1),  # Color: Axis line/tick color (RGBA).
#     'label': '',  # str: Axis label text (rendered near axis).
#     'label_font_size': 12,  # int: Font size in px.
#     'label_font_family': 'Roboto, sans-serif',  # str: CSS font-family fallback list.
#     'label_font_color': None,  # Color | None: Label text color; None => use theme/default.
#     'auto_skip': True,  # bool: Hide overlapping ticks automatically.
#     'ticks_mode': 'auto',  # str: 'auto' | 'custom'
#     'ticks': [],  # list[float|str]: Explicit tick values (if ticks_mode='custom').
#     'major_ticks': [],  # list[float|str]: Extra/emphasized tick positions.
#     'major_ticks_width': 1,  # float >= 0: Line width for major ticks.
#     'major_ticks_color': 'grid',  # Color | 'grid': Use grid color keyword or explicit color.
#     'major_ticks_force_label': True  # bool: Always show a label at major tick positions.
# }
#
# DEFAULT_Y = {
#     'id': 'y',  # str: Axis ID. Must be unique among y-axes.
#     'type': 'linear',  # str: 'linear' | 'log'
#     'unit': '',  # str: Unit label (e.g., 'V', '°C'); free text.
#     'color': (0.7, 0.7, 0.7, 1),  # Color: Axis line/tick color (RGBA).
#     'label': '',  # str: Axis label text.
#     'label_font_size': 12,  # int: Font size in px.
#     'label_font_family': 'Roboto, sans-serif',  # str: CSS font-family fallback list.
#     'label_font_color': None,  # Color | None: Label text color; None => use theme/default.
#     'position': 'left',  # str: 'left' | 'right'
#     'min': 'auto',  # float | int | 'auto': Lower bound; 'auto' to infer from data.
#     'max': 'auto',  # float | int | 'auto': Upper bound; 'auto' to infer from data.
#     'step_size': 1,  # float > 0: Tick step (only if ticks_mode='auto').
#     'auto_skip': True,  # bool: Hide overlapping ticks automatically.
#     'ticks_mode': 'auto',  # str: 'auto' | 'custom'
#     'ticks': [],  # list[float|str]: Explicit tick values (if ticks_mode='custom').
#     'major_ticks': [],  # list[float|str]: Extra/emphasized tick positions.
#     'major_ticks_width': 2,  # float >= 0: Line width for major ticks.
#     'major_ticks_color': 'grid',  # Color | 'grid': Use grid color keyword or explicit color.
#     'major_ticks_force_label': True  # bool: Always show a label at major tick positions.
# }
#
# DEFAULT_SERIES = {
#     'id': 's',  # str: Series ID (unique).
#     'unit': '',  # str: Unit for legend/tooltip (e.g., 'V'); free text.
#     'y_axis': 'y',  # str: Target Y axis ID to map values.
#     'tension': 0,  # float in [0,1]: Curve smoothing (0=straight lines).
#     'color': (0, 0, 1, 1),  # Color: Stroke color (RGBA).
#     'width': 1,  # float >= 0: Line width in px.
#     'line_style': 'solid',  # str: 'solid' | 'dashed' | 'dotted'
#     'marker': 'none',  # str: 'none' | 'circle' | 'square' | 'triangle' | 'cross' ...
#     'marker_fill': True,  # bool: Fill marker interior if applicable.
#     'marker_size': 5,  # float > 0: Marker size in px.
#     'fill': False,  # bool: Area fill under line.
#     'fill_color': (0, 0, 1, 0.2),  # Color: Fill color (RGBA, alpha usually < 1).
#     'visible': True,  # bool: Toggle series visibility.
#     'show_in_legend': True  # bool: Include series in legend.
# }
#
# DEFAULT_PLOT = {
#     'background_color': (0, 0, 0, 0),  # Color: Canvas/page background (RGBA). (0 alpha = transparent)
#     'plot_background_color': (0.2, 0.2, 0.2, 0.5),  # Color: Chart plotting area background.
#     'show_grid': True,  # bool: Toggle major grid visibility.
#     'grid_color': (0.5, 0.5, 0.5, 1),  # Color: Grid line color.
#     'grid_width': 1,  # float >= 0: Grid line width in px.
#     'grid_line_style': 'solid',  # str: 'solid' | 'dashed' | 'dotted'
#     'show_legend': True,  # bool: Show/hide legend.
#     'legend_position': 'bottom',  # str: 'top' | 'bottom' | 'left' | 'right'
#     'legend_font_size': 12,  # int: Legend font size in px.
#     'legend_font_family': 'Roboto, sans-serif',  # str: CSS font-family fallback list.
#     'legend_font_color': (0.8, 0.8, 0.8, 1),  # Color: Legend text color.
#     'show_title': True, 'title': '',  # bool + str: Toggle & text for chart title.
#     'title_font_size': 12,  # int: Title font size in px.
#     'title_font_family': 'Roboto, sans-serif',  # str: CSS font-family fallback list.
#     'title_font_color': [0.8, 0.8, 0.8, 1],  # Color: Title text color.
#     'border_color': [0, 1, 0, 1],  # Color: Plot area border color.
#     'border_width': 1,  # float >= 0: Plot area border width in px.
#     'x_axis': {},  # dict: (Filled from XAxis.config). Put overrides here.
#     'y_axes': {}  # dict[str, dict]: {id: y-config}. Multiple Y axes supported.
# }
#
#
# # ---- data classes ------------------------------------------------------------
#
# @dataclass
# class XAxis:
#     id: str = 'x'
#     config: Dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_X))
#
#     def set(self, **kwargs) -> "XAxis":
#         self.config = _merge(self.config, kwargs, {'id': self.id})
#         return self
#
#     # dynamic helpers that mirror JS
#     def add_tick(self, v: float) -> "XAxis":
#         ticks = list(self.config.get('ticks', []))
#         ticks.append(v)
#         self.config['ticks'] = ticks
#         self.config['ticks_mode'] = 'custom'
#         return self
#
#     def remove_tick(self, v: float) -> "XAxis":
#         self.config['ticks'] = [x for x in self.config.get('ticks', []) if x != v]
#         return self
#
#
# @dataclass
# class YAxis:
#     id: str
#     config: Dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_Y))
#
#     def __post_init__(self):
#         self.config = _merge(DEFAULT_Y, self.config, {'id': self.id})
#
#     def set(self, **kwargs) -> "YAxis":
#         self.config = _merge(self.config, kwargs, {'id': self.id})
#         return self
#
#
# @dataclass
# class Series:
#     plot: LinePlot
#     id: str
#     config: Dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_SERIES))
#     _points: List[Point] = field(default_factory=list)
#
#
#     @property
#     def uid(self):
#         return f'{self.plot.id}/{self.id}'
#
#     def __post_init__(self):
#         self.config = _merge(DEFAULT_SERIES, self.config, {'id': self.id})
#
#     # dynamic: add/remove points
#     def add(self, x: float, y: float) -> "Series":
#         self._points.append((float(x), float(y)))
#         return self
#
#     def set(self, points: Iterable[Point]):
#         self._points = []
#         for x, y in points:
#             self._points.append((float(x), float(y)))
#
#         print(self._points)
#         if self.plot.widget:
#             self.plot.widget.executePlotFunction(path=self.uid,
#                                                  function_name='setValues',
#                                                  arguments=self._points,
#                                                  spread_args=False,
#                                                  )
#
#     def extend(self, points: Iterable[Point]) -> "Series":
#         for x, y in points:
#             self._points.append((float(x), float(y)))
#
#
#
#         return self
#
#     def remove_at_x(self, x: float) -> "Series":
#         self._points = [(px, py) for (px, py) in self._points if px != x]
#         return self
#
#     def to_dict(self) -> Dict[str, Any]:
#         return {
#             'id': self.uid,
#             'config': self.config,
#             'points': self._points
#         }
#
#
# @dataclass
# class LineSegment:
#     x1: float
#     y1: float
#     x2: float
#     y2: float
#     id: Optional[str] = None
#     color: Color = (0, 0, 0, 1)
#     width: float = 1
#     line_style: str = 'solid'  # 'solid' | 'dashed' | 'dotted'
#     label: str = ''
#     y_axis: Optional[str] = None
#
#     def to_dict(self) -> Dict[str, Any]:
#         out = {
#             'x1': self.x1, 'y1': self.y1, 'x2': self.x2, 'y2': self.y2,
#             'color': self.color, 'width': self.width, 'line_style': self.line_style,
#             'label': self.label, 'y_axis': self.y_axis
#         }
#         if self.id:
#             out['id'] = self.id
#         return out
#
#
# # ---- main plot ---------------------------------------------------------------
#
# class LinePlot:
#     """
#     Build your plot in Python and emit a single payload the frontend consumes:
#       payload = {
#         'id': <plot_id>,
#         'config': { ...plot config..., x_axis: {...}, y_axes: {id: {...}} },
#         'data': {
#           'x_axis': {...},                   # optional runtime x overrides
#           'y_axes': {id: {...}},             # optional runtime y adds/overrides
#           'series': [ {id, config, points}, ... ],
#           'lines':  [ {x1,y1,x2,y2,...}, ... ]
#         }
#       }
#     """
#     widget: LinePlotWidget | None = None
#
#     # === INIT =========================================================================================================
#     def __init__(self, plot_id: str, **config_overrides):
#         self.id = plot_id
#         self._config: Dict[str, Any] = _merge(DEFAULT_PLOT, config_overrides)
#         self.x_axis = XAxis('x', _merge(DEFAULT_X, self._config.get('x_axis', {})))
#         # y-axes registry
#         self.y_axes: Dict[str, YAxis] = {}
#         for yid, ycfg in (self._config.get('y_axes') or {}).items():
#             self.y_axes[yid] = YAxis(yid, _merge(DEFAULT_Y, ycfg, {'id': yid}))
#         # series & lines
#         self._series: Dict[str, Series] = {}
#         self._lines: List[LineSegment] = []
#
#     # ---- config surface (mirrors JS dynamic operations) ----------------------
#
#     def set_title(self, title: str) -> "LinePlot":
#         self._config['title'] = title
#         return self
#
#     def set_theme(self, **kwargs) -> "LinePlot":
#         """Convenience for plot-level visual settings."""
#         self._config = _merge(self._config, kwargs)
#         return self
#
#     # Axes
#     def add_y_axis(self, axis_id: str, **kwargs) -> YAxis:
#         y = YAxis(axis_id, kwargs)
#         self.y_axes[axis_id] = y
#         return y
#
#     def get_y_axis(self, axis_id: str) -> Optional[YAxis]:
#         return self.y_axes.get(axis_id)
#
#     # Series
#     def add_series(self, series_id: str, points=None, **series_config) -> Series:
#
#         if points is None:
#             points = []
#         s = Series(self, series_id, series_config, points)
#         self._series[series_id] = s
#
#         if self.widget:
#             self.widget.executePlotFunction(path=self.id,
#                                             function_name='addSeriesFromConfig',
#                                             arguments=s.config,
#                                             spread_args=False,
#                                             )
#
#         return s
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def get_series(self, series_id: str) -> Optional[Series]:
#         return self._series.get(series_id)
#
#     def remove_series(self, series_id: str) -> "LinePlot":
#         self._series.pop(series_id, None)
#         return self
#
#     # Lines
#     def add_line(self, x1: float, y1: float, x2: float, y2: float, *,
#                  color: Color = (0, 0, 0, 1), width: float = 1,
#                  line_style: str = 'solid', label: str = '',
#                  y_axis: Optional[str] = None, line_id: Optional[str] = None) -> LineSegment:
#         seg = LineSegment(x1, y1, x2, y2, id=line_id, color=color, width=width,
#                           line_style=line_style, label=label, y_axis=y_axis)
#         self._lines.append(seg)
#         return seg
#
#     def clear_lines(self) -> "LinePlot":
#         self._lines.clear()
#         return self
#
#     # ---- payloads ------------------------------------------------------------
#
#     def getConfiguration(self) -> Dict[str, Any]:
#         """Static plot configuration (including axes)."""
#         cfg = copy.deepcopy(self._config)
#         # embed current x & y axis configs
#         cfg['x_axis'] = copy.deepcopy(self.x_axis.config)
#         cfg['y_axes'] = {yid: ya.config for yid, ya in self.y_axes.items()}
#         return cfg
#
#     def getData(self) -> Dict[str, Any]:
#         """Initial data state to render (series points & lines)."""
#         return {
#             # x_axis/y_axes blocks here are optional runtime overrides;
#             # most users won’t need them when config already contains axes.
#             'series': [s.to_dict() for s in self._series.values()],
#             'lines': [L.to_dict() for L in self._lines],
#         }
#
#     def to_payload(self) -> Dict[str, Any]:
#         return {
#             'id': self.id,
#             'config': self.getConfiguration(),
#             'data': self.getData()
#         }
#
#
# # === LINEPLOT WIDGET ==================================================================================================
# class LinePlotWidget(GUI_Object):
#     type = 'lineplot'
#
#     # === INIT =========================================================================================================
#     def __init__(self, widget_id: str, plot_config=None, **kwargs):
#         super().__init__(widget_id, **kwargs)
#
#         plot_config = plot_config or {
#
#         }
#
#         self.plot = LinePlot(f"{widget_id}_plot", **plot_config)
#         self.plot.widget = self
#
#         # Put some testing elements here!
#         self.plot.set_title("Demo Plot (seeded in LinePlotWidget)")
#         self.plot.set_theme(
#             legend_position='bottom',
#             grid_line_style='dotted',
#             border_color=(0.4, 0.4, 0.4, 1),
#             border_width=1,
#         )
#
#         # Axes
#         self.plot.add_y_axis(
#             'main',
#             min=-1.5, max=5, step_size=0.5,
#             label='Amplitude', color=(0.7, 0.7, 0.7, 1),
#         )
#         # X: ticks 0..12, clamp range
#         self.plot.x_axis.set(min=0, max=12, ticks_mode='auto', ticks=list(range(0, 13)))
#
#         # Series
#         import math
#         s_sin = self.plot.add_series(
#             'sin',
#             y_axis='main', color=(1, 0, 0, 1),
#             width=2, line_style='solid',
#             marker='none', marker_size=4,
#         )
#
#         # Points: x = 0..12 step 0.5
#         xs = [i * 0.5 for i in range(0, 25)]
#         s_sin.extend((x, math.sin(x)) for x in xs)
#
#         def test():
#             s_cos = self.plot.add_series(
#                 'cos',
#                 points=[(x, math.cos(x)) for x in xs],
#                 y_axis='main', color=[0.75, 0.75, 0.75, 1],
#                 width=2, line_style='dashed',
#                 marker='square', marker_size=4,
#             )
#             s_cos.set([(x, math.cos(x)) for x in xs])
#             # self.plot.x_axis.set(min=0, max=20, ticks_mode='custom', ticks=list(range(0, 20)))
#             # self.update()
#
#         def test2():
#             self.plot.x_axis.set(min=0, max=20, ticks_mode='auto', ticks=list(range(0, 20)))
#             self.updateXAxis()
#
#
#         delayed_execution(test, 5)
#
#         delayed_execution(test2, 7)
#
#     # === METHODS ======================================================================================================
#     def executePlotFunction(self, path, function_name, arguments: list | dict, spread_args: bool = False):
#         data = {
#             'type': 'plot_function',
#             'path': path,
#             'function_name': function_name,
#             'arguments': arguments,
#             'spread_args': spread_args
#         }
#         self.sendMessage(data)
#     # ------------------------------------------------------------------------------------------------------------------
#     def updateXAxis(self):
#         self.executePlotFunction(path=self.plot.id,
#                                  function_name='updateXAxisFromConfig',
#                                  arguments=self.plot.x_axis.config,
#                                  spread_args=False,
#                                  )
#     # ------------------------------------------------------------------------------------------------------------------
#
#
#     def update(self):
#         ...
#         # self.sendUpdate(self.plot.to_payload())
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def getConfiguration(self) -> dict:
#         config = super().getConfiguration()
#         config['plot_id'] = self.plot.id
#         return config
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def getPayload(self) -> dict:
#         payload = super().getPayload()
#         payload['plot'] = self.plot.to_payload()
#         return payload
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def handleEvent(self, message, sender=None) -> None:
#         self.logger.warning(f"Lineplot Widget received message: {message}")
#
#     # === PRIVATE METHODS ==============================================================================================


# lineplot_backend.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any, Iterable
import copy

from core.utils.dict_utils import update_dict
from core.utils.time import delayed_execution
from extensions.gui.src.lib.objects.objects import Widget


# ---- helpers -----------------------------------------------------------------

def _merge(base: dict, *updates: dict) -> dict:
    out = copy.deepcopy(base)
    for u in updates:
        if not u:
            continue
        for k, v in u.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = _merge(out[k], v)
            else:
                out[k] = copy.deepcopy(v)
    return out


Color = Tuple[float, float, float, float]  # RGBA floats 0..1
Point = Tuple[float, float]

# ---- default configs (mirror the JS defaults) --------------------------------

DEFAULT_X = {
    'id': 'x',  # str: Axis ID. Any non-empty string.
    'type': 'linear',  # str: 'linear' | 'time' | 'log' | 'category'
    'unit': '',  # str: Unit label (e.g., 's', 'Hz'); free text.
    'min': 'auto',  # float | int | 'auto': Lower bound; 'auto' to infer from data.
    'max': 'auto',  # float | int | 'auto': Upper bound; 'auto' to infer from data.
    'step_size': 1,  # float > 0: Tick step (only if ticks_mode='auto').
    'color': (0.7, 0.7, 0.7, 1),  # Color: Axis line/tick color (RGBA).
    'label': 'Time [s]',  # str: Axis label text (rendered near axis).
    'label_font_size': 12,  # int: Font size in px.
    'label_font_family': 'Roboto, sans-serif',  # str: CSS font-family fallback list.
    'label_font_color': None,  # Color | None: Label text color; None => use theme/default.
    'auto_skip': True,  # bool: Hide overlapping ticks automatically.
    'ticks_mode': 'auto',  # str: 'auto' | 'custom'
    'ticks': [],  # list[float|str]: Explicit tick values (if ticks_mode='custom').
    'major_ticks': [],  # list[float|str]: Extra/emphasized tick positions.
    'major_ticks_width': 1,  # float >= 0: Line width for major ticks.
    'major_ticks_color': 'grid',  # Color | 'grid': Use grid color keyword or explicit color.
    'major_ticks_force_label': True  # bool: Always show a label at major tick positions.
}

DEFAULT_Y = {
    'id': 'y',  # str: Axis ID. Must be unique among y-axes.
    'type': 'linear',  # str: 'linear' | 'log'
    'unit': '',  # str: Unit label (e.g., 'V', '°C'); free text.
    'color': (0.7, 0.7, 0.7, 1),  # Color: Axis line/tick color (RGBA).
    'label': '',  # str: Axis label text.
    'label_font_size': 12,  # int: Font size in px.
    'label_font_family': 'Roboto, sans-serif',  # str: CSS font-family fallback list.
    'label_font_color': None,  # Color | None: Label text color; None => use theme/default.
    'position': 'left',  # str: 'left' | 'right'
    'min': 'auto',  # float | int | 'auto': Lower bound; 'auto' to infer from data.
    'max': 'auto',  # float | int | 'auto': Upper bound; 'auto' to infer from data.
    'step_size': 0,  # float > 0: Tick step (only if ticks_mode='auto').
    'auto_skip': True,  # bool: Hide overlapping ticks automatically.
    'ticks_mode': 'auto',  # str: 'auto' | 'custom'
    'ticks': [],  # list[float|str]: Explicit tick values (if ticks_mode='custom').
    'major_ticks': [],  # list[float|str]: Extra/emphasized tick positions.
    'major_ticks_width': 2,  # float >= 0: Line width for major ticks.
    'major_ticks_color': 'grid',  # Color | 'grid': Use grid color keyword or explicit color.
    'major_ticks_force_label': True  # bool: Always show a label at major tick positions.
}

DEFAULT_SERIES = {
    'id': 's',  # str: Series ID (unique).
    'unit': '',  # str: Unit for legend/tooltip (e.g., 'V'); free text.
    'y_axis': 'y',  # str: Target Y axis ID to map values.
    'tension': 0,  # float in [0,1]: Curve smoothing (0=straight lines).
    'color': (0, 0, 1, 1),  # Color: Stroke color (RGBA).
    'width': 1,  # float >= 0: Line width in px.
    'line_style': 'solid',  # str: 'solid' | 'dashed' | 'dotted'
    'marker': 'none',  # str: 'none' | 'circle' | 'square' | 'triangle' | 'cross' ...
    'marker_fill': True,  # bool: Fill marker interior if applicable.
    'marker_size': 5,  # float > 0: Marker size in px.
    'fill': False,  # bool: Area fill under line.
    'fill_color': (0, 0, 1, 0.2),  # Color: Fill color (RGBA, alpha usually < 1).
    'visible': True,  # bool: Toggle series visibility.
    'show_in_legend': True  # bool: Include series in legend.
}

DEFAULT_PLOT = {
    'background_color': (0, 0, 0, 0),  # Color: Canvas/page background (RGBA). (0 alpha = transparent)
    'plot_background_color': (0.2, 0.2, 0.2, 0.5),  # Color: Chart plotting area background.
    'show_grid': True,  # bool: Toggle major grid visibility.
    'grid_color': (0.5, 0.5, 0.5, 1),  # Color: Grid line color.
    'grid_width': 1,  # float >= 0: Grid line width in px.
    'grid_line_style': 'solid',  # str: 'solid' | 'dashed' | 'dotted'
    'show_legend': True,  # bool: Show/hide legend.
    'legend_position': 'bottom',  # str: 'top' | 'bottom' | 'left' | 'right'
    'legend_font_size': 12,  # int: Legend font size in px.
    'legend_font_family': 'Roboto, sans-serif',  # str: CSS font-family fallback list.
    'legend_font_color': (0.8, 0.8, 0.8, 1),  # Color: Legend text color.
    'show_title': True, 'title': '',  # bool + str: Toggle & text for chart title.
    'title_font_size': 12,  # int: Title font size in px.
    'title_font_family': 'Roboto, sans-serif',  # str: CSS font-family fallback list.
    'title_font_color': [0.8, 0.8, 0.8, 1],  # Color: Title text color.
    'border_color': [0, 1, 0, 1],  # Color: Plot area border color.
    'border_width': 1,  # float >= 0: Plot area border width in px.
    'x_axis': {},  # dict: (Filled from XAxis.config). Put overrides here.
    'y_axes': {}  # dict[str, dict]: {id: y-config}. Multiple Y axes supported.
}


# ---- data classes ------------------------------------------------------------

@dataclass
class XAxis:
    id: str = 'x'
    config: Dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_X))
    _plot_ref: LinePlot | None = None  # for live updates

    def set(self, **kwargs) -> "XAxis":
        self.config = _merge(self.config, kwargs, {'id': self.id})
        # Push to frontend if bound
        if self._plot_ref and self._plot_ref.widget:
            self._plot_ref.widget.updateXAxis()
        return self

    def add_tick(self, v: float) -> "XAxis":
        ticks = list(self.config.get('ticks', []))
        ticks.append(v)
        self.config['ticks'] = ticks
        self.config['ticks_mode'] = 'custom'
        if self._plot_ref and self._plot_ref.widget:
            self._plot_ref.widget.executePlotFunction(
                path=self._plot_ref.id,
                function_name='xAxisAddTick_interface',
                arguments=v,
                spread_args=False
            )
        return self

    def remove_tick(self, v: float) -> "XAxis":
        self.config['ticks'] = [x for x in self.config.get('ticks', []) if x != v]
        if self._plot_ref and self._plot_ref.widget:
            self._plot_ref.widget.executePlotFunction(
                path=self._plot_ref.id,
                function_name='xAxisRemoveTick_interface',
                arguments=v,
                spread_args=False
            )
        return self


@dataclass
class YAxis:
    id: str
    config: Dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_Y))

    def __post_init__(self):
        self.config = _merge(DEFAULT_Y, self.config, {'id': self.id})

    def set(self, **kwargs) -> "YAxis":
        self.config = _merge(self.config, kwargs, {'id': self.id})
        return self


@dataclass
class Series:
    plot: "LinePlot"
    id: str
    config: Dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_SERIES))
    _points: List[Point] = field(default_factory=list)

    @property
    def uid(self):
        return f'{self.plot.id}/{self.id}'

    def __post_init__(self):
        self.config = _merge(DEFAULT_SERIES, self.config, {'id': self.id})

    # dynamic: add one point
    def add(self, x: float, y: float) -> "Series":
        self._points.append((float(x), float(y)))
        if self.plot.widget:
            self.plot.widget.executePlotFunction(
                path=self.uid,
                function_name='addValue_interface',
                arguments=[x, y],
                spread_args=True
            )
        return self

    # replace entire set
    def set(self, points: Iterable[Point]) -> "Series":
        self._points = []
        normalized = []
        for x, y in points:
            pair = (float(x), float(y))
            self._points.append(pair)
            normalized.append(pair)
        if self.plot.widget:
            self.plot.widget.executePlotFunction(
                path=self.uid,
                function_name='setValues_interface',
                arguments=normalized,
                spread_args=False
            )
        return self

    # extend with multiple points (appends)
    def extend(self, points: Iterable[Point]) -> "Series":
        batch = []
        for x, y in points:
            pair = (float(x), float(y))
            self._points.append(pair)
            batch.append(pair)
        if batch and self.plot.widget:
            # Reuse setValues_interface which appends internally on JS side
            self.plot.widget.executePlotFunction(
                path=self.uid,
                function_name='setValues_interface',
                arguments=batch,
                spread_args=False
            )
        return self

    def remove_at_x(self, x: float) -> "Series":
        self._points = [(px, py) for (px, py) in self._points if px != x]
        if self.plot.widget:
            self.plot.widget.executePlotFunction(
                path=self.uid,
                function_name='removeValue_interface',
                arguments=float(x),
                spread_args=False
            )
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'config': self.config,
            'points': self._points
        }


@dataclass
class LineSegment:
    x1: float
    y1: float
    x2: float
    y2: float
    id: Optional[str] = None
    color: Color = (0, 0, 0, 1)
    width: float = 1
    line_style: str = 'solid'
    label: str = ''
    y_axis: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out = {
            'x1': self.x1, 'y1': self.y1, 'x2': self.x2, 'y2': self.y2,
            'color': self.color, 'width': self.width, 'line_style': self.line_style,
            'label': self.label, 'y_axis': self.y_axis
        }
        if self.id:
            out['id'] = self.id
        return out


# ---- main plot ---------------------------------------------------------------

class LinePlot:
    """
    Build your plot in Python and emit a single payload the frontend consumes.
    """
    widget: LinePlotWidget | None = None

    def __init__(self, plot_id: str, **config_overrides):
        self.id = plot_id
        self._config: Dict[str, Any] = _merge(DEFAULT_PLOT, config_overrides)
        self.x_axis = XAxis('x', _merge(DEFAULT_X, self._config.get('x_axis', {})))
        self.x_axis._plot_ref = self
        # y-axes
        self.y_axes: Dict[str, YAxis] = {}
        for yid, ycfg in (self._config.get('y_axes') or {}).items():
            self.y_axes[yid] = YAxis(yid, _merge(DEFAULT_Y, ycfg, {'id': yid}))
        # series & lines
        self._series: Dict[str, Series] = {}
        self._lines: List[LineSegment] = []

    # ---- plot-level config ---------------------------------------------------

    def set_title(self, title: str) -> "LinePlot":
        self._config['title'] = title
        return self

    def set_theme(self, **kwargs) -> "LinePlot":
        self._config = _merge(self._config, kwargs)
        return self

    # ---- Y axes --------------------------------------------------------------

    def add_y_axis(self, axis_id: str, **kwargs) -> YAxis:
        y = YAxis(axis_id, kwargs)
        self.y_axes[axis_id] = y
        # live add to frontend
        if self.widget:
            self.widget.executePlotFunction(
                path=self.id,
                function_name='addYAxis_interface',
                arguments=y.config,
                spread_args=False
            )
        return y

    def remove_y_axis(self, axis_id: str) -> "LinePlot":
        self.y_axes.pop(axis_id, None)
        if self.widget:
            self.widget.executePlotFunction(
                path=self.id,
                function_name='removeYAxis_interface',
                arguments=axis_id,
                spread_args=False
            )
        return self

    def get_y_axis(self, axis_id: str) -> Optional[YAxis]:
        return self.y_axes.get(axis_id)

    # ---- Series --------------------------------------------------------------

    def add_series(self, series_id: str, points: Optional[Iterable[Point]] = None, **series_config) -> Series:
        points = list(points or [])
        s = Series(self, series_id, series_config, list(points))
        self._series[series_id] = s

        # 1) add series shell
        if self.widget:
            self.widget.executePlotFunction(
                path=self.id,
                function_name='addSeries_interface',
                arguments=s.config,
                spread_args=False
            )
        # 2) seed points (append behavior on JS side)
        if points and self.widget:
            self.widget.executePlotFunction(
                path=s.uid,
                function_name='setValues_interface',
                arguments=[(float(x), float(y)) for x, y in points],
                spread_args=False
            )

        return s

    def get_series(self, series_id: str) -> Optional[Series]:
        return self._series.get(series_id)

    def remove_series(self, series_id: str) -> "LinePlot":
        self._series.pop(series_id, None)
        if self.widget:
            self.widget.executePlotFunction(
                path=self.id,
                function_name='removeSeries_interface',
                arguments=series_id,
                spread_args=False
            )
        return self

    # ---- Lines ---------------------------------------------------------------

    def add_line(self, x1: float, y1: float, x2: float, y2: float, *,
                 color: Color = (0, 0, 0, 1), width: float = 1,
                 line_style: str = 'solid', label: str = '',
                 y_axis: Optional[str] = None, line_id: Optional[str] = None) -> LineSegment:
        seg = LineSegment(x1, y1, x2, y2, id=line_id, color=color, width=width,
                          line_style=line_style, label=label, y_axis=y_axis)
        self._lines.append(seg)
        if self.widget:
            self.widget.executePlotFunction(
                path=self.id,
                function_name='addLine_interface',
                arguments=seg.to_dict(),  # includes id if provided
                spread_args=False
            )
        return seg

    def remove_line(self, line_id: str) -> "LinePlot":
        self._lines = [ln for ln in self._lines if ln.id != line_id]
        if self.widget:
            self.widget.executePlotFunction(
                path=self.id,
                function_name='removeLine_interface',
                arguments=line_id,
                spread_args=False
            )
        return self

    def clear_lines(self) -> "LinePlot":
        self._lines.clear()
        if self.widget:
            self.widget.executePlotFunction(
                path=self.id,
                function_name='clearLines_interface',
                arguments=None,
                spread_args=False
            )
        return self

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self):
        self._series = {}
        self._lines = []
        self.y_axes = {}

        if self.widget:
            self.widget.executePlotFunction(
                path=self.id,
                function_name='clear',
                arguments=True,
                spread_args=False
            )
        return self

    # ---- payloads ------------------------------------------------------------

    def getConfiguration(self) -> Dict[str, Any]:
        cfg = copy.deepcopy(self._config)
        cfg['x_axis'] = copy.deepcopy(self.x_axis.config)
        cfg['y_axes'] = {yid: ya.config for yid, ya in self.y_axes.items()}
        return cfg

    def getData(self) -> Dict[str, Any]:
        return {
            'series': [s.to_dict() for s in self._series.values()],
            'lines': [L.to_dict() for L in self._lines],
        }

    def to_payload(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'config': self.getConfiguration(),
            'data': self.getData()
        }


# === LINEPLOT WIDGET ==========================================================
class LinePlotWidget(Widget):
    type = 'lineplot'

    def __init__(self, widget_id: str, plot_config=None, **kwargs):
        super().__init__(widget_id, **kwargs)

        plot_default_config = {
            'title': ''
        }

        if plot_config is None:
            plot_config = {}

        plot_config = update_dict(plot_default_config, plot_config, kwargs, allow_add=False)


        self.plot = LinePlot(f"{widget_id}_plot", **plot_config)
        self.plot.widget = self

        self.plot.set_title(plot_config['title'])
        self.plot.set_theme(
            legend_position='bottom',
            grid_line_style='dotted',
            border_color=(0.4, 0.4, 0.4, 1),
            border_width=1,
        )

        # # Demo content (can be removed in production)
        # self.plot.set_title("Demo Plot (seeded in LinePlotWidget)")

        #
        # # Axes
        # self.plot.add_y_axis(
        #     'main',
        #     min=-1.5, max=5, step_size=0.5,
        #     label='Amplitude', color=(0.7, 0.7, 0.7, 1),
        # )
        # # X config
        # self.plot.x_axis.set(min=0, max=12, ticks_mode='auto', ticks=list(range(0, 13)))
        #
        # # Series
        # import math
        # s_sin = self.plot.add_series(
        #     'sin',
        #     y_axis='main', color=(1, 0, 0, 1),
        #     width=2, line_style='solid',
        #     marker='none', marker_size=4,
        # )
        #
        # xs = [i * 0.5 for i in range(0, 25)]
        # s_sin.extend((x, math.sin(x)) for x in xs)
        #
        # def test():
        #     s_cos = self.plot.add_series(
        #         'cos',
        #         points=[(x, math.cos(x)) for x in xs],
        #         y_axis='main', color=(0.75, 0.75, 0.75, 1),
        #         width=2, line_style='dashed',
        #         marker='square', marker_size=4,
        #     )
        #     # also show point-by-point add for demo
        #     for x in [12.5, 13.0]:
        #         s_cos.add(x, math.cos(x))
        #
        # def test2():
        #     self.plot.x_axis.set(min=0, max=20, ticks_mode='auto', ticks=list(range(0, 21)))
        #
        # def test3():
        #     s_sin.extend([(14, 3), (17, -1)])
        #
        # delayed_execution(test, 5)
        # delayed_execution(test2, 7)
        # delayed_execution(test3, 10)

    # === Bridge to frontend ===================================================

    def executePlotFunction(self, path, function_name, arguments: list | dict | float | int | str | None,
                            spread_args: bool = False):
        data = {
            'type': 'plot_function',
            'path': path,
            'function_name': function_name,
            'arguments': arguments,
            'spread_args': spread_args
        }
        self.sendWidgetMessage(data)

    def updateXAxis(self):
        self.executePlotFunction(
            path=self.plot.id,
            function_name='updateXAxisFromConfig_interface',
            arguments=self.plot.x_axis.config,
            spread_args=False,
        )

    def update(self):
        ...
        # self.sendUpdate(self.plot.to_payload())

    def getConfiguration(self) -> dict:
        config = super().getConfiguration()
        config['plot_id'] = self.plot.id
        return config

    def getPayload(self) -> dict:
        payload = super().getPayload()
        payload['plot'] = self.plot.to_payload()
        return payload

    def handleEvent(self, message, sender=None) -> None:
        self.logger.warning(f"Lineplot Widget received message: {message}")
