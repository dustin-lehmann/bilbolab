"""
Data Display & Indicators Example
==================================

Demonstrates read-only display widgets and indicator animations:
  - DigitalNumberWidget with live-updating value
  - TextWidget with multi-line formatted text
  - StatusWidget with dynamic state changes
  - CircleIndicator (blinking LED)
  - LoadingIndicator (spinner)
  - ProgressIndicator (linear bar, auto-filling)
  - BatteryIndicatorWidget

Buttons on the left trigger state changes in the display widgets on the right,
so you can see how to update them from Python.

Run from the `software/` directory:
    python -m extensions.gui.examples.data_display.data_display_example
"""

import math
import random
import time

from core.utils.colors import random_color_from_palette
from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button, MultiStateButton
from extensions.gui.src.lib.objects.python.indicators import (
    CircleIndicator,
    LoadingIndicator,
    ProgressIndicator,
    BatteryIndicatorWidget,
)
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget
from extensions.gui.src.lib.objects.python.text import TextWidget, StatusWidget, StatusWidgetElement


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    category = Category(id='display', name='Data Display', icon='D')
    app.addCategory(category)

    page = Page(id='main', name='Display & Indicators')
    category.addPage(page, position=1)

    # =========================================================================
    # Digital number display — updated every tick in the main loop
    # =========================================================================
    number = DigitalNumberWidget(
        widget_id='angle',
        title='Angle',
        value=0.0,
        min_value=-180,
        max_value=180,
        precision=1,
        unit='deg',
        color='transparent',
        text_color=[0.4, 0.8, 0.95],
    )
    page.addWidget(number, row=1, column=1, width=6, height=3)

    number2 = DigitalNumberWidget(
        widget_id='velocity',
        title='Velocity',
        value=0.0,
        min_value=-5,
        max_value=5,
        precision=2,
        unit='m/s',
        color='transparent',
        text_color=[0.95, 0.6, 0.3],
    )
    page.addWidget(number2, row=1, column=7, width=6, height=3)

    # =========================================================================
    # Text widget — multi-line formatted information panel
    # =========================================================================
    info_text = TextWidget(
        widget_id='info',
        text='System Info\n-----------\nUptime: 0s\nCycles: 0\nStatus: IDLE',
        font_size=11,
        horizontal_alignment='left',
        vertical_alignment='top',
        text_color=[0.7, 0.85, 0.7],
        font_weight='normal',
    )
    page.addWidget(info_text, row=4, column=1, width=8, height=5)

    # =========================================================================
    # Status widget — dynamic status entries controlled by buttons
    # =========================================================================
    status = StatusWidget(
        widget_id='system_status',
        elements={
            'controller': StatusWidgetElement(
                label='Controller', color=[0.1, 0.7, 0.2], status='Running'),
            'sensor': StatusWidgetElement(
                label='Sensor', color=[0.1, 0.7, 0.2], status='OK'),
            'battery': StatusWidgetElement(
                label='Battery', color=[0.8, 0.7, 0.1], status='72%'),
            'network': StatusWidgetElement(
                label='Network', color=[0.1, 0.7, 0.2], status='Connected'),
        },
    )
    page.addWidget(status, row=4, column=10, width=8, height=5)

    # --- Buttons that modify the status widget ----
    btn_fault = Button(widget_id='trigger_fault', text='Trigger Fault', color=[0.5, 0.15, 0.15])
    page.addWidget(btn_fault, row=10, column=10, width=4, height=2)

    btn_clear = Button(widget_id='clear_fault', text='Clear Fault', color=[0.15, 0.4, 0.15])
    page.addWidget(btn_clear, row=10, column=14, width=4, height=2)

    def trigger_fault(*args, **kwargs):
        status.elements['sensor'].status = 'FAULT'
        status.elements['sensor'].color = [0.9, 0.15, 0.15]
        status.elements['controller'].status = 'Degraded'
        status.elements['controller'].color = [0.8, 0.5, 0.1]
        status.updateConfig()
        print('[data_display] Sensor fault triggered')

    def clear_fault(*args, **kwargs):
        status.elements['sensor'].status = 'OK'
        status.elements['sensor'].color = [0.1, 0.7, 0.2]
        status.elements['controller'].status = 'Running'
        status.elements['controller'].color = [0.1, 0.7, 0.2]
        status.updateConfig()
        print('[data_display] Fault cleared')

    btn_fault.callbacks.click.register(trigger_fault)
    btn_clear.callbacks.click.register(clear_fault)

    # =========================================================================
    # Indicators row
    # =========================================================================

    # Circle indicator — blinking heartbeat LED
    heartbeat = CircleIndicator(
        widget_id='heartbeat',
        color=[0.2, 0.85, 0.3],
        size=60,
        blinking=True,
        blinking_frequency=1.0,
    )
    page.addWidget(heartbeat, row=10, column=1, width=2, height=2)

    # Loading spinner — toggleable
    spinner = LoadingIndicator(
        widget_id='spinner',
        color=[0.5, 0.7, 0.9],
        speed=1.0,
        spinning=True,
    )
    page.addWidget(spinner, row=10, column=3, width=2, height=2)

    btn_spin = Button(widget_id='toggle_spin', text='Toggle Spin', color=[0.2, 0.35, 0.5])
    page.addWidget(btn_spin, row=12, column=3, width=3, height=1)

    spin_state = {'on': True}

    def toggle_spinner(*args, **kwargs):
        spin_state['on'] = not spin_state['on']
        spinner.updateConfig(spinning=spin_state['on'])
        print(f"[data_display] Spinner {'ON' if spin_state['on'] else 'OFF'}")

    btn_spin.callbacks.click.register(toggle_spinner)

    # Progress bar — controlled by buttons
    progress = ProgressIndicator(
        widget_id='progress',
        value=0.0,
        title='Task Progress',
        label='0%',
        type='linear',
        direction='horizontal',
        track_fill_color=[0.3, 0.6, 0.9, 0.7],
    )
    page.addWidget(progress, row=10, column=6, width=4, height=2)

    btn_progress_up = Button(widget_id='progress_up', text='+10%', color=[0.2, 0.4, 0.25])
    page.addWidget(btn_progress_up, row=12, column=6, width=2, height=1)

    btn_progress_reset = Button(widget_id='progress_reset', text='Reset', color=[0.4, 0.2, 0.2])
    page.addWidget(btn_progress_reset, row=12, column=8, width=2, height=1)

    progress_val = {'v': 0.0}

    def inc_progress(*args, **kwargs):
        progress_val['v'] = min(1.0, progress_val['v'] + 0.1)
        progress.value = progress_val['v']
        pct = int(progress_val['v'] * 100)
        progress.updateConfig(label=f'{pct}%')
        # Change color when complete
        if progress_val['v'] >= 1.0:
            progress.updateConfig(track_fill_color=[0.2, 0.8, 0.3, 0.8])
        print(f'[data_display] Progress = {pct}%')

    def reset_progress(*args, **kwargs):
        progress_val['v'] = 0.0
        progress.value = 0.0
        progress.updateConfig(label='0%', track_fill_color=[0.3, 0.6, 0.9, 0.7])
        print('[data_display] Progress reset')

    btn_progress_up.callbacks.click.register(inc_progress)
    btn_progress_reset.callbacks.click.register(reset_progress)

    # Battery indicator
    battery = BatteryIndicatorWidget(
        widget_id='battery',
        value=0.72,
        voltage=11.8,
        show='percentage',
    )
    page.addWidget(battery, row=14, column=1, width=3, height=3)

    # --- Start ---------------------------------------------------------------
    app.start()

    # --- Main loop: live-update number displays and info text ----------------
    t0 = time.time()
    cycle = 0

    while True:
        t = time.time() - t0
        cycle += 1

        # Sine wave angle, cosine velocity
        angle = 90 * math.sin(0.5 * t)
        velocity = 2.0 * math.cos(0.3 * t) + random.gauss(0, 0.05)
        number.value = round(angle, 1)
        number2.value = round(velocity, 2)

        # Update info panel
        info_text.updateConfig(text=(
            f'System Info\n'
            f'-----------\n'
            f'Uptime: {int(t)}s\n'
            f'Cycles: {cycle}\n'
            f'Angle:  {angle:+.1f} deg\n'
            f'Vel:    {velocity:+.2f} m/s'
        ))

        # Simulate battery drain
        batt = max(0.0, 0.72 - t * 0.001)
        battery.updateConfig(value=batt, voltage=round(11.8 - t * 0.015, 1))

        time.sleep(0.1)


if __name__ == '__main__':
    main()
