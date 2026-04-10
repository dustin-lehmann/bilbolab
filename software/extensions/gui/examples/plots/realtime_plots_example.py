"""
Real-Time Plots Example
=======================

Demonstrates the RT_Plot_Widget with various signal types:
  Page 1 — Signals:
    - Sine & cosine on a shared Y-axis
    - Square wave & sawtooth (stepped mode)
    - Random walk with filled area and dashed lines

  Page 2 — System:
    - Damped oscillation with decay envelope
    - Lissajous X/Y coordinates
    - Dual-axis plot (temperature + humidity simulation)

All data is generated in a 20 Hz main loop.

Run from the `software/` directory:
    python -m extensions.gui.examples.plots.realtime_plots_example
"""

import math
import random
import time

from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.plot.realtime.rt_plot import RT_Plot_Widget


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    category = Category(id='plots', name='Plots', icon='P')
    app.addCategory(category)

    # =========================================================================
    # Page 1: Signals
    # =========================================================================
    page_signals = Page(id='signals', name='Signals')
    category.addPage(page_signals, position=1)

    # --- Sine & cosine -------------------------------------------------------
    plot_trig = RT_Plot_Widget(
        widget_id='trig_plot',
        plot_config={
            'title': 'Trigonometric',
            'x_axis_config': {'window_time': 15, 'pre_delay': 0.15},
            'buffer_size': 600,
        },
    )
    page_signals.addWidget(plot_trig, row=1, column=1, width=9, height=10)

    plot_trig.plot.add_y_axis('amplitude', config={
        'label': 'Amplitude', 'side': 'left', 'precision': 2,
        'min': -1.5, 'max': 1.5, 'color': [0.7, 0.7, 0.7, 1],
    })
    ts_sin = plot_trig.plot.add_timeseries('sin', config={
        'y_axis': 'amplitude', 'name': 'sin(t)',
        'color': [0.2, 0.6, 0.9, 1], 'width': 2, 'tension': 0.2,
    })
    ts_cos = plot_trig.plot.add_timeseries('cos', config={
        'y_axis': 'amplitude', 'name': 'cos(t)',
        'color': [0.9, 0.35, 0.25, 1], 'width': 2, 'tension': 0.2,
    })

    # --- Square wave & sawtooth ----------------------------------------------
    plot_waves = RT_Plot_Widget(
        widget_id='wave_plot',
        plot_config={
            'title': 'Waveforms',
            'x_axis_config': {'window_time': 15, 'pre_delay': 0.15},
            'buffer_size': 600,
        },
    )
    page_signals.addWidget(plot_waves, row=1, column=10, width=9, height=10)

    plot_waves.plot.add_y_axis('value', config={
        'label': 'Value', 'side': 'left', 'precision': 1,
        'min': -1.5, 'max': 1.5, 'color': [0.7, 0.7, 0.7, 1],
    })
    ts_square = plot_waves.plot.add_timeseries('square', config={
        'y_axis': 'value', 'name': 'Square',
        'color': [0.95, 0.7, 0.1, 1], 'width': 2, 'stepped': 'before',
    })
    ts_saw = plot_waves.plot.add_timeseries('sawtooth', config={
        'y_axis': 'value', 'name': 'Sawtooth',
        'color': [0.5, 0.9, 0.4, 1], 'width': 2,
    })

    # --- Random walk ---------------------------------------------------------
    plot_random = RT_Plot_Widget(
        widget_id='random_plot',
        plot_config={
            'title': 'Random Walk',
            'x_axis_config': {'window_time': 30, 'pre_delay': 0.2},
            'buffer_size': 600,
            'show_legend': True,
            'legend_position': 'bottom',
        },
    )
    page_signals.addWidget(plot_random, row=11, column=1, width=18, height=8)

    plot_random.plot.add_y_axis('walk', config={
        'label': 'Position', 'side': 'left', 'precision': 2,
        'color': [0.7, 0.7, 0.7, 1],
    })
    ts_walk_a = plot_random.plot.add_timeseries('walker_a', config={
        'y_axis': 'walk', 'name': 'Walker A',
        'color': [0.3, 0.85, 0.85, 1], 'fill': True,
        'fill_color': [0.3, 0.85, 0.85, 0.08], 'width': 2,
    })
    ts_walk_b = plot_random.plot.add_timeseries('walker_b', config={
        'y_axis': 'walk', 'name': 'Walker B',
        'color': [0.85, 0.45, 0.85, 1], 'fill': True,
        'fill_color': [0.85, 0.45, 0.85, 0.08], 'width': 2, 'line_dash': [6, 3],
    })

    # =========================================================================
    # Page 2: System
    # =========================================================================
    page_system = Page(id='system', name='System')
    category.addPage(page_system, position=2)

    # --- Damped oscillation --------------------------------------------------
    plot_damped = RT_Plot_Widget(
        widget_id='damped_plot',
        plot_config={
            'title': 'Damped Oscillation',
            'x_axis_config': {'window_time': 20, 'pre_delay': 0.15},
            'buffer_size': 600,
        },
    )
    page_system.addWidget(plot_damped, row=1, column=1, width=9, height=10)

    plot_damped.plot.add_y_axis('pos', config={
        'label': 'Position', 'side': 'left', 'precision': 3,
        'color': [0.7, 0.7, 0.7, 1],
    })
    ts_damped = plot_damped.plot.add_timeseries('damped', config={
        'y_axis': 'pos', 'name': 'x(t)',
        'color': [0.2, 0.8, 0.5, 1], 'width': 2, 'tension': 0.3,
    })
    ts_envelope = plot_damped.plot.add_timeseries('envelope', config={
        'y_axis': 'pos', 'name': 'envelope',
        'color': [0.7, 0.7, 0.7, 0.5], 'width': 1, 'line_dash': [4, 4],
    })

    # --- Lissajous -----------------------------------------------------------
    plot_lissajous = RT_Plot_Widget(
        widget_id='lissajous_plot',
        plot_config={
            'title': 'Lissajous X/Y',
            'x_axis_config': {'window_time': 20, 'pre_delay': 0.15},
            'buffer_size': 600,
        },
    )
    page_system.addWidget(plot_lissajous, row=1, column=10, width=9, height=10)

    plot_lissajous.plot.add_y_axis('xy', config={
        'label': 'Coordinate', 'side': 'left', 'precision': 2,
        'min': -1.2, 'max': 1.2, 'color': [0.7, 0.7, 0.7, 1],
    })
    ts_lix = plot_lissajous.plot.add_timeseries('liss_x', config={
        'y_axis': 'xy', 'name': 'X',
        'color': [0.9, 0.3, 0.3, 1], 'width': 2, 'tension': 0.3,
    })
    ts_liy = plot_lissajous.plot.add_timeseries('liss_y', config={
        'y_axis': 'xy', 'name': 'Y',
        'color': [0.3, 0.5, 0.9, 1], 'width': 2, 'tension': 0.3,
    })

    # --- Dual axis (temperature + humidity) ----------------------------------
    plot_multi = RT_Plot_Widget(
        widget_id='multi_axis_plot',
        plot_config={
            'title': 'Dual Axis',
            'x_axis_config': {'window_time': 20, 'pre_delay': 0.15},
            'buffer_size': 600,
        },
    )
    page_system.addWidget(plot_multi, row=11, column=1, width=18, height=8)

    plot_multi.plot.add_y_axis('temp', config={
        'label': 'Temperature (C)', 'side': 'left', 'precision': 1,
        'min': 15, 'max': 35, 'color': [0.9, 0.4, 0.2, 0.8], 'grid': True,
    })
    plot_multi.plot.add_y_axis('humid', config={
        'label': 'Humidity (%)', 'side': 'right', 'precision': 0,
        'min': 30, 'max': 80, 'color': [0.2, 0.5, 0.9, 0.8], 'grid': False,
    })
    ts_temp = plot_multi.plot.add_timeseries('temperature', config={
        'y_axis': 'temp', 'name': 'Temperature', 'unit': 'C',
        'color': [0.9, 0.4, 0.2, 1], 'fill': True,
        'fill_color': [0.9, 0.4, 0.2, 0.1], 'width': 2, 'tension': 0.4,
    })
    ts_humid = plot_multi.plot.add_timeseries('humidity', config={
        'y_axis': 'humid', 'name': 'Humidity', 'unit': '%',
        'color': [0.2, 0.5, 0.9, 1], 'fill': True,
        'fill_color': [0.2, 0.5, 0.9, 0.1], 'width': 2, 'tension': 0.4,
    })

    # --- Start ---------------------------------------------------------------
    app.start()

    # --- Data generation loop (20 Hz) ----------------------------------------
    t0 = time.time()
    walk_a = 0.0
    walk_b = 0.0
    temp_val = 22.0
    humid_val = 55.0

    while True:
        t = time.time() - t0
        omega = 2 * math.pi * 0.5

        # Page 1
        ts_sin.set_value(math.sin(omega * t))
        ts_cos.set_value(math.cos(omega * t))

        period = 2.0
        ts_square.set_value(1.0 if (t % period) < (period / 2) else -1.0)
        ts_saw.set_value(2.0 * ((t / period) % 1.0) - 1.0)

        walk_a += random.gauss(0, 0.02)
        walk_b += random.gauss(0, 0.025)
        ts_walk_a.set_value(walk_a)
        ts_walk_b.set_value(walk_b)

        # Page 2
        zeta = 0.1
        envelope = math.exp(-zeta * t)
        ts_damped.set_value(envelope * math.cos(2 * math.pi * 0.3 * t))
        ts_envelope.set_value(envelope)

        ts_lix.set_value(math.sin(3.0 * t))
        ts_liy.set_value(math.sin(2.0 * t))

        temp_val = max(16, min(34, temp_val + random.gauss(0, 0.05)))
        humid_val = max(32, min(78, humid_val + random.gauss(0, 0.15)))
        ts_temp.set_value(temp_val)
        ts_humid.set_value(humid_val)

        time.sleep(0.05)


if __name__ == '__main__':
    main()
