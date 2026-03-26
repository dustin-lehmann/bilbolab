"""Minimal example: Plot using LaTeX text rendering."""
import numpy as np
from core.utils.plotting.plot import Plot, PlotConfig, Axis, AxisConfig, Series, SeriesConfig

t = np.linspace(0, 2 * np.pi, 200)

plot = Plot(
    rows=1, columns=1,
    config=PlotConfig(
        size=(6, 3.5),
        use_latex=True,
        font_family='serif',
        font_size=10,
    ),
)

ax = Axis('ax', AxisConfig(
    ylabel=r'Amplitude $\alpha$ [rad]',
    xlabel=r'Time $t$ [s]',
))
plot.set_axis(1, 1, ax)
ax.add_series(Series('sin', t, np.sin(t), SeriesConfig(label=r'$\sin(t)$')))
ax.add_series(Series('cos', t, np.cos(t), SeriesConfig(label=r'$\cos(t)$')))

plot.show()
