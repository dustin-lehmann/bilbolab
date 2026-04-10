"""
Buttons Example
===============

Demonstrates all button types and their callback events:
  - Regular Button with click, double-click, long-press, and right-click
  - Color-changing button
  - Multi-state button cycling through modes
  - Reset button with auto-timeout
  - Context menu on right-click

Every interaction updates a live event log displayed in the GUI and prints
to the Python console.

Run from the `software/` directory:
    python -m extensions.gui.examples.buttons.buttons_example
"""

import random
import time

from core.utils.colors import random_color_from_palette
from core.utils.logging_utils import Logger, enable_redirection, addLogRedirection, LOGGING_COLORS
from core.utils.time import delayed_execution
from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button, MultiStateButton
from extensions.gui.src.lib.objects.python.text import TextWidget
from extensions.gui.src.lib.objects.python.indicators import CircleIndicator
from extensions.gui.src.lib.objects.python.callout import Callout, CalloutType
from extensions.gui.src.lib.objects.objects import ContextMenuItem, ContextMenuGroup


# ---------------------------------------------------------------------------
# Shared event log — last N events displayed in a text widget
# ---------------------------------------------------------------------------
MAX_LOG_LINES = 12
event_log = []
logger = Logger('buttons')


def log_event(text_widget, message: str):
    """Append a message to the event log, update the GUI text widget, and log."""
    event_log.append(message)
    if len(event_log) > MAX_LOG_LINES:
        event_log.pop(0)
    text_widget.updateConfig(text='\n'.join(event_log))
    logger.info(message)


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    category = Category(id='buttons', name='Buttons', icon='B')
    app.addCategory(category)

    page = Page(id='main', name='Button Showcase')
    category.addPage(page, position=1)

    # --- Event log display (right side) --------------------------------------
    log_widget = TextWidget(
        widget_id='event_log',
        text='(events will appear here)',
        font_size=10,
        horizontal_alignment='left',
        vertical_alignment='top',
        text_color=[0.8, 0.8, 0.8],
    )
    page.addWidget(log_widget, row=1, column=20, width=15, height=18)

    # --- 1. Basic button with all callback types -----------------------------
    basic_btn = Button(widget_id='basic', text='Basic Button', color=[0.2, 0.35, 0.55])
    page.addWidget(basic_btn, row=1, column=1, width=5, height=3)

    basic_btn.callbacks.click.register(
        lambda *a, **kw: log_event(log_widget, 'Basic: click'))
    basic_btn.callbacks.doubleClick.register(
        lambda *a, **kw: log_event(log_widget, 'Basic: double-click'))
    basic_btn.callbacks.longClick.register(
        lambda *a, **kw: log_event(log_widget, 'Basic: long-press'))
    basic_btn.callbacks.rightClick.register(
        lambda *a, **kw: log_event(log_widget, 'Basic: right-click'))

    # --- 2. Color-changing button (randomises on every click) ----------------
    color_btn = Button(widget_id='color', text='Random Color', color=[0.5, 0.2, 0.2])
    page.addWidget(color_btn, row=1, column=7, width=5, height=3)

    def on_color_click(*args, **kwargs):
        new_color = [random.random(), random.random(), random.random(), 1]
        color_btn.updateConfig(color=new_color)
        hex_color = '#{:02x}{:02x}{:02x}'.format(
            int(new_color[0] * 255), int(new_color[1] * 255), int(new_color[2] * 255))
        log_event(log_widget, f'Color changed to {hex_color}')

    color_btn.callbacks.click.register(on_color_click)

    # --- 3. Click counter with indicator -------------------------------------
    counter = {'n': 0}
    counter_btn = Button(widget_id='counter', text='Count: 0', color=[0.15, 0.4, 0.3])
    page.addWidget(counter_btn, row=1, column=13, width=5, height=3)

    # Indicator blinks on each click
    blink_indicator = CircleIndicator(
        widget_id='blink_led',
        color=[0.2, 0.8, 0.4],
        size=60,
        blinking=False,
    )
    page.addWidget(blink_indicator, row=2, column=18, width=1, height=1)

    def on_counter_click(*args, **kwargs):
        counter['n'] += 1
        counter_btn.updateConfig(text=f"Count: {counter['n']}")
        blink_indicator.blink(time=200)
        log_event(log_widget, f"Counter = {counter['n']}")
        # Callout every 10 clicks
        if counter['n'] % 10 == 0:
            app.callout_handler.add(Callout(
                content=f'Milestone: {counter["n"]} clicks!',
                callout_type=CalloutType.SUCCESS,
                timeout=3000,
            ))

    counter_btn.callbacks.click.register(on_counter_click)

    # --- 4. Multi-state button -----------------------------------------------
    msb = MultiStateButton(
        id='mode_switch',
        states=['OFF', 'IDLE', 'RUNNING', 'ERROR'],
        color=[
            [0.4, 0.1, 0.1],   # OFF  — dark red
            [0.5, 0.45, 0.1],  # IDLE — amber
            [0.1, 0.45, 0.2],  # RUNNING — green
            [0.6, 0.1, 0.1],   # ERROR — bright red
        ],
        title='System Mode',
    )
    page.addWidget(msb, row=5, column=1, width=5, height=3)

    # Status indicator mirrors the mode color
    mode_indicator = CircleIndicator(
        widget_id='mode_led',
        color=[0.4, 0.1, 0.1],
        size=70,
    )
    page.addWidget(mode_indicator, row=5, column=6, width=1, height=2)

    def on_mode_change(button, *args, **kwargs):
        button.increaseIndex()
        state = button.state
        color = button.config['color'][button.state_index]
        mode_indicator.updateConfig(color=color)
        log_event(log_widget, f'Mode -> {state}')

    msb.callbacks.click.register(on_mode_change)

    # --- 5. Toggle button (ON/OFF with auto-reset after 5s) ------------------
    toggle = MultiStateButton(
        id='toggle',
        states=['OFF', 'ON'],
        color=[[0.3, 0.1, 0.1], [0.1, 0.4, 0.1]],
        title='Auto-Reset',
    )
    page.addWidget(toggle, row=5, column=8, width=4, height=3)

    def on_toggle(button, *args, **kwargs):
        if button.state == 'OFF':
            button.updateConfig(state='ON')
            log_event(log_widget, 'Toggle ON — will reset in 5s')
            delayed_execution(lambda: button.updateConfig(state='OFF'), delay=5)
            delayed_execution(lambda: log_event(log_widget, 'Toggle auto-reset to OFF'), delay=5)
        else:
            button.updateConfig(state='OFF')
            log_event(log_widget, 'Toggle OFF (manual)')

    toggle.callbacks.click.register(on_toggle)

    # --- 6. Button with context menu -----------------------------------------
    ctx_btn = Button(widget_id='ctx_menu', text='Right-Click Me', color=[0.3, 0.2, 0.45])
    page.addWidget(ctx_btn, row=9, column=1, width=5, height=3)

    # Top-level menu items
    item_copy = ContextMenuItem(id='copy', name='Copy Value')
    item_paste = ContextMenuItem(id='paste', name='Paste Value')
    ctx_btn.context_menu.addItem(item_copy)
    ctx_btn.context_menu.addItem(item_paste)

    # Nested submenu
    submenu = ContextMenuGroup(id='actions', name='Actions', type='submenu')
    item_reset = ContextMenuItem(id='reset', name='Reset Counter')
    item_notify = ContextMenuItem(id='notify', name='Send Notification')
    submenu.addItem(item_reset)
    submenu.addItem(item_notify)
    ctx_btn.context_menu.addItem(submenu)

    item_copy.callbacks.click.register(
        lambda *a, **kw: log_event(log_widget, 'Context: Copy'))
    item_paste.callbacks.click.register(
        lambda *a, **kw: log_event(log_widget, 'Context: Paste'))
    item_reset.callbacks.click.register(
        lambda *a, **kw: (
            counter.update({'n': 0}),
            counter_btn.updateConfig(text='Count: 0'),
            log_event(log_widget, 'Context: Counter reset'),
        ))
    item_notify.callbacks.click.register(
        lambda *a, **kw: (
            app.callout_handler.add(Callout(
                content='Notification from context menu!',
                callout_type=CalloutType.INFO,
                timeout=4000,
            )),
            log_event(log_widget, 'Context: Notification sent'),
        ))

    # --- 7. Grid of small themed buttons -------------------------------------
    themes = [
        ('Danger', [0.6, 0.15, 0.15]),
        ('Success', [0.15, 0.5, 0.2]),
        ('Info', [0.15, 0.35, 0.6]),
        ('Warning', [0.6, 0.5, 0.1]),
        ('Purple', [0.4, 0.15, 0.55]),
        ('Teal', [0.1, 0.45, 0.45]),
    ]
    for i, (name, color) in enumerate(themes):
        btn = Button(
            widget_id=f'theme_{name.lower()}',
            text=name,
            color=color,
            config={'fontSize': 10},
        )
        row = 13 + (i // 3) * 2
        col = 1 + (i % 3) * 4
        page.addWidget(btn, row=row, column=col, width=4, height=2)
        btn.callbacks.click.register(
            lambda *a, n=name, **kw: log_event(log_widget, f'Theme: {n} clicked'))

    # --- Log forwarding to the GUI terminal ------------------------------------
    # All Logger output (from any module) is forwarded to the built-in CLI
    # terminal so it appears in the GUI's log panel.
    def _log_to_gui(log_entry, log, log_logger, level):
        text = f'[{log_logger.name}] {log}'
        color = [c / 255 for c in LOGGING_COLORS[level]]
        app.print(text, color=color)

    addLogRedirection(_log_to_gui, minimum_level='INFO')

    # --- Start ---------------------------------------------------------------
    app.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
