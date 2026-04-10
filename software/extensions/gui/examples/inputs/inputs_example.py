"""
Input Widgets Example
=====================

Demonstrates all input widget types with cross-widget interactions:
  - Horizontal slider  -> controls a progress indicator
  - Vertical slider    -> controls a digital number display
  - Rotary dial        -> controls an indicator colour (hue wheel)
  - Text input         -> echoed into a text display widget
  - Checkbox           -> enables / disables a group of widgets
  - Multi-select       -> changes a status widget entry
  - Classic slider     -> shown for completeness

Every value change is logged to the Python console and updates at least one
other widget so you can see the feedback loop.

Run from the `software/` directory:
    python -m extensions.gui.examples.inputs.inputs_example
"""

import colorsys
import time

from core.utils.colors import random_color_from_palette
from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.checkbox import CheckboxWidget
from extensions.gui.src.lib.objects.python.dial import RotaryDialWidget
from extensions.gui.src.lib.objects.python.indicators import (
    CircleIndicator,
    ProgressIndicator,
)
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget
from extensions.gui.src.lib.objects.python.select import MultiSelectWidget
from extensions.gui.src.lib.objects.python.sliders import SliderWidget, ClassicSliderWidget
from extensions.gui.src.lib.objects.python.text import TextWidget, StatusWidget, StatusWidgetElement
from extensions.gui.src.lib.objects.python.text_input import InputWidget


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    category = Category(id='inputs', name='Inputs', icon='I')
    app.addCategory(category)

    page = Page(id='main', name='Input Widgets')
    category.addPage(page, position=1)

    # =========================================================================
    # Row 1-3: Horizontal slider -> progress indicator
    # =========================================================================
    slider_h = SliderWidget(
        widget_id='h_slider',
        min_value=0,
        max_value=100,
        increment=1,
        value=50,
        color=[0.2, 0.5, 0.8],
        direction='horizontal',
        continuousUpdates=True,
        title='Progress Control',
    )
    page.addWidget(slider_h, row=1, column=1, width=10, height=2)

    progress = ProgressIndicator(
        widget_id='progress',
        value=0.5,
        title='Progress',
        label='50%',
        type='linear',
        direction='horizontal',
        track_fill_color=[0.2, 0.5, 0.8, 0.7],
    )
    page.addWidget(progress, row=3, column=1, width=10, height=2)

    def on_h_slider(value, *args, **kwargs):
        pct = value / 100.0
        progress.value = pct
        progress.updateConfig(label=f'{int(value)}%')
        print(f'[inputs] Horizontal slider -> {value:.0f}%')

    slider_h.callbacks.value_changed.register(on_h_slider)

    # =========================================================================
    # Row 1-8: Vertical slider -> digital number display
    # =========================================================================
    slider_v = SliderWidget(
        widget_id='v_slider',
        min_value=-10,
        max_value=10,
        increment=0.1,
        value=0,
        color=[0.6, 0.3, 0.1],
        direction='vertical',
        ticks=[-10, -5, 0, 5, 10],
        continuousUpdates=True,
    )
    page.addWidget(slider_v, row=1, column=12, width=2, height=8)

    number_display = DigitalNumberWidget(
        widget_id='number',
        title='Value',
        value=0.0,
        min_value=-10,
        max_value=10,
        increment=0.1,
        color='transparent',
        text_color=[0.9, 0.6, 0.2],
    )
    page.addWidget(number_display, row=1, column=14, width=5, height=2)

    def on_v_slider(value, *args, **kwargs):
        number_display.value = value
        print(f'[inputs] Vertical slider -> {value:.1f}')

    slider_v.callbacks.value_changed.register(on_v_slider)

    # =========================================================================
    # Row 5-8: Rotary dial -> circle indicator colour (hue)
    # =========================================================================
    dial = RotaryDialWidget(
        widget_id='hue_dial',
        min_value=0,
        max_value=360,
        increment=5,
        value=180,
        continuousUpdates=True,
        dialColor=[0.4, 0.7, 0.9],
        dialWidth=8,
        title='Hue',
    )
    page.addWidget(dial, row=5, column=1, width=3, height=4)

    hue_indicator = CircleIndicator(
        widget_id='hue_led',
        color=[0.0, 1.0, 1.0],  # will be overridden
        size=80,
    )
    page.addWidget(hue_indicator, row=5, column=5, width=2, height=3)

    hue_label = TextWidget(
        widget_id='hue_label',
        text='H: 180',
        font_size=12,
        horizontal_alignment='center',
        vertical_alignment='center',
        text_color=[0.7, 0.7, 0.7],
    )
    page.addWidget(hue_label, row=9, column=4, width=4, height=1)

    def on_dial(value, *args, **kwargs):
        r, g, b = colorsys.hsv_to_rgb(value / 360.0, 0.9, 0.9)
        hue_indicator.updateConfig(color=[r, g, b])
        hue_label.updateConfig(text=f'H: {int(value)}')
        print(f'[inputs] Dial -> hue {int(value)}')

    dial.callbacks.value_changed.register(on_dial)

    # =========================================================================
    # Row 5-7: Dial 2 — with snap-to-ticks
    # =========================================================================
    dial_snap = RotaryDialWidget(
        widget_id='snap_dial',
        min_value=0,
        max_value=100,
        value=25,
        ticks=[0, 25, 50, 75, 100],
        limitToTicks=True,
        dialColor=[0.8, 0.5, 0.2],
        title='Snap',
    )
    page.addWidget(dial_snap, row=5, column=8, width=3, height=4)

    snap_label = TextWidget(
        widget_id='snap_label',
        text='Snap: 25',
        font_size=11,
        horizontal_alignment='center',
        vertical_alignment='center',
    )
    page.addWidget(snap_label, row=9, column=8, width=3, height=1)

    def on_snap_dial(value, *args, **kwargs):
        snap_label.updateConfig(text=f'Snap: {int(value)}')
        print(f'[inputs] Snap dial -> {int(value)}')

    dial_snap.callbacks.value_changed.register(on_snap_dial)

    # =========================================================================
    # Row 10-11: Text input -> echo in text widget
    # =========================================================================
    text_input = InputWidget(
        widget_id='text_in',
        title='Type something:',
        title_position='left',
        inputFieldWidth='200px',
        inputFieldPosition='right',
    )
    page.addWidget(text_input, row=10, column=1, width=12, height=1)

    echo = TextWidget(
        widget_id='echo',
        text='(your text appears here)',
        font_size=12,
        horizontal_alignment='left',
        vertical_alignment='center',
        text_color=[0.6, 0.9, 0.6],
    )
    page.addWidget(echo, row=11, column=1, width=12, height=2)

    def on_text(value, *args, **kwargs):
        echo.updateConfig(text=f'Echo: {value}')
        print(f'[inputs] Text input -> "{value}"')

    text_input.callbacks.value_changed.register(on_text)

    # =========================================================================
    # Row 10-11: Number input with validation
    # =========================================================================
    num_input = InputWidget(
        widget_id='num_in',
        title='Age (0-120):',
        title_position='left',
        datatype='int',
        value=25,
        validator=lambda x: 0 <= x <= 120,
        inputFieldWidth='80px',
        inputFieldPosition='right',
    )
    page.addWidget(num_input, row=10, column=14, width=8, height=1)

    num_echo = TextWidget(
        widget_id='num_echo',
        text='Age: 25',
        font_size=12,
        horizontal_alignment='left',
        vertical_alignment='center',
    )
    page.addWidget(num_echo, row=11, column=14, width=8, height=1)

    def on_num(value, *args, **kwargs):
        num_echo.updateConfig(text=f'Age: {value}')
        print(f'[inputs] Number input -> {value}')

    num_input.callbacks.value_changed.register(on_num)

    # =========================================================================
    # Row 13-14: Checkbox -> dim/enable the dial group
    # =========================================================================
    checkbox = CheckboxWidget(
        widget_id='enable_dial',
        title='Enable hue dial:',
        title_position='left',
        value=True,
    )
    page.addWidget(checkbox, row=13, column=1, width=8, height=1)

    def on_checkbox(value, *args, **kwargs):
        dial.dim(not value)
        hue_indicator.dim(not value)
        state = 'enabled' if value else 'disabled'
        print(f'[inputs] Hue dial {state}')

    checkbox.callbacks.changed.register(on_checkbox)


    # =========================================================================
    # Row 13-15: Multi-select -> updates a status widget
    # =========================================================================
    status = StatusWidget(
        widget_id='mode_status',
        elements={
            'mode': StatusWidgetElement(
                label='Mode', color=[0.4, 0.4, 0.4], status='Normal'),
        },
    )
    page.addWidget(status, row=13, column=14, width=6, height=3)

    select = MultiSelectWidget(
        widget_id='mode_select',
        options={
            'normal': {'label': 'Normal', 'color': [0.3, 0.3, 0.4]},
            'turbo': {'label': 'Turbo', 'color': [0.6, 0.3, 0.1]},
            'eco': {'label': 'Eco', 'color': [0.1, 0.5, 0.2]},
        },
        value='normal',
        title='Mode:',
        title_position='left',
    )
    page.addWidget(select, row=16, column=14, width=8, height=1)

    mode_colors = {
        'normal': [0.4, 0.4, 0.4],
        'turbo': [0.9, 0.4, 0.1],
        'eco': [0.1, 0.8, 0.3],
    }

    def on_select(value, *args, **kwargs):
        color = mode_colors.get(value, [0.4, 0.4, 0.4])
        status.elements['mode'].status = value.capitalize()
        status.elements['mode'].color = color
        status.updateConfig()
        print(f'[inputs] Mode -> {value}')

    select.callbacks.selection_changed.register(on_select)

    # =========================================================================
    # Row 16-17: Classic slider
    # =========================================================================
    classic = ClassicSliderWidget(
        widget_id='classic',
        value=50,
        increment=10,
        backgroundColor=[0.2, 0.2, 0.3],
        title='Classic:',
        title_position='left',
        valuePosition='right',
    )
    page.addWidget(classic, row=16, column=1, width=12, height=1)

    classic.callbacks.value_changed.register(
        lambda v, *a, **kw: print(f'[inputs] Classic slider -> {v}'))

    # =========================================================================
    # Row 17: Slider with auto-reset (springs back to center)
    # =========================================================================
    spring_slider = SliderWidget(
        widget_id='spring',
        min_value=-1.0,
        max_value=1.0,
        increment=0.05,
        value=0,
        color=[0.5, 0.2, 0.5],
        continuousUpdates=True,
        automaticReset=0.0,
        title='Spring (auto-reset)',
    )
    page.addWidget(spring_slider, row=17, column=1, width=12, height=2)

    spring_slider.callbacks.value_changed.register(
        lambda v, *a, **kw: print(f'[inputs] Spring slider -> {v:+.2f}'))

    # --- Start ---------------------------------------------------------------
    app.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
