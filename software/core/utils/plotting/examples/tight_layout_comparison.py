"""Compare tight_layout=True vs tight_layout=False.

Creates two figures side by side so you can see the effect of tight_layout
on label clipping and subplot spacing.
"""
import os
import numpy as np
from core.utils.plotting.plot import Plot, PlotConfig, Axis, AxisConfig, Series, SeriesConfig

t = np.linspace(0, 2 * np.pi, 200)
y1 = np.sin(t)
y2 = np.cos(t)

out_dir = os.path.dirname(os.path.abspath(__file__))

for tight in [True, False]:
    plot = Plot(
        rows=2, columns=1,
        config=PlotConfig(
            size=(6, 5),
            dpi=150,
            tight_layout=tight,
            title=f'tight_layout = {tight}',
            title_font_size=14,
            save_dpi=150,
        ),
    )

    ax1 = Axis('top', AxisConfig(
        ylabel='Amplitude [rad/s²]',
        xlabel='Time [s]',
        title='Sine wave',
    ))
    plot.set_axis(1, 1, ax1)
    ax1.add_series(Series('sin', t, y1, SeriesConfig(label='sin(t)')))

    ax2 = Axis('bottom', AxisConfig(
        ylabel='Amplitude [rad/s²]',
        xlabel='Time [s]',
        title='Cosine wave',
    ))
    plot.set_axis(2, 1, ax2)
    ax2.add_series(Series('cos', t, y2, SeriesConfig(label='cos(t)')))

    label = 'tight' if tight else 'no_tight'
    plot.save(os.path.join(out_dir, f'tight_layout_{label}.png'), format='png')
    plot.close()

print("Saved to", out_dir)
