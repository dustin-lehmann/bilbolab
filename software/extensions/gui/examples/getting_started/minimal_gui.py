"""
Minimal GUI Example
===================

The absolute minimum to get a BilboLab GUI running: one category, one page,
one button. Clicking the button prints a message to the Python console.

Run from the `software/` directory:
    python -m extensions.gui.examples.getting_started.minimal_gui
"""

import time

from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.text import TextWidget


def main():
    # --- 1. Create the GUI application -------------------------------------------
    # `host` is the local IP; `run_js` launches the Vue frontend automatically.
    host = getHostIP()
    app = GUI(id='minimal_gui', host=host, run_js=True)

    # --- 2. Build the navigation tree: Category > Page ---------------------------
    category = Category(id='demo', name='Demo', icon='D')
    app.addCategory(category)

    page = Page(id='home', name='Home')
    category.addPage(page, position=1)

    # --- 3. Add widgets ----------------------------------------------------------
    # A simple click counter: the button increments a number shown in a text widget.
    click_count = {'n': 0}

    label = TextWidget(
        widget_id='counter_label',
        text='Clicks: 0',
        font_size=16,
        horizontal_alignment='center',
        vertical_alignment='center',
    )
    page.addWidget(label, row=1, column=1, width=6, height=2)

    button = Button(widget_id='click_me', text='Click Me', color=[0.2, 0.45, 0.7])
    page.addWidget(button, row=3, column=1, width=6, height=3)

    def on_click(*args, **kwargs):
        click_count['n'] += 1
        label.updateConfig(text=f"Clicks: {click_count['n']}")
        print(f"[minimal_gui] Button clicked! Total: {click_count['n']}")

    button.callbacks.click.register(on_click)

    # --- 4. Start the GUI and keep the process alive -----------------------------
    app.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
