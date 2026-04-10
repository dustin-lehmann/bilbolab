"""
Parent-Child GUI Example
========================

Demonstrates linking two independent GUI instances together:
  - A parent GUI with its own categories and pages
  - A child GUI on a different WebSocket port
  - The child GUI is attached to a category in the parent, so both
    appear in the same sidebar navigation

This is useful for multi-process or multi-machine setups where each
subsystem runs its own GUI server.

Run from the `software/` directory:
    python -m extensions.gui.examples.advanced.parent_child_example
"""

import time

from core.utils.colors import random_color_from_palette
from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.popup import Popup
from extensions.gui.src.lib.objects.python.sliders import SliderWidget


def create_parent_gui(host, port):
    """Create and start the parent GUI."""
    parent_app = GUI(id='parent_gui', host=host, ws_port=port, run_js=True)

    cat1 = parent_app.addCategory(Category(id='category1', name='Category 1', max_pages=1))
    cat2 = parent_app.addCategory(Category(id='category2', name='Category 2'))

    child_cat1 = cat1.addCategory(Category(id='child_category1', name='X1'))

    page1 = cat1.addPage(Page(id='page1', name='Page 1'))
    button1 = page1.addWidget(Button(widget_id='button1', text='Parent Button', color=[0.3, 0, 0]))
    button1.callbacks.click.register(
        lambda *a, **kw: print('[parent_child] Parent button clicked'))

    parent_app.start()
    return parent_app


def create_child_gui(host, port, parent_port):
    """Create and start the child GUI on a separate port."""
    child_app = GUI(id='child_gui', host=host, ws_port=port, js_app_port=5555, run_js=True)

    cat1 = child_app.addCategory(Category(id='category1', name='Child Cat 1'))
    cat2 = child_app.addCategory(Category(id='category2', name='Child Cat 2'))
    page1 = cat1.addPage(Page(id='page1', name='Child Page 1'))
    page2 = cat1.addPage(Page(id='page2', name='Child Page 2'))

    button1 = Button(widget_id='button1', text='Child Button', color=[0, 0.6, 0])
    page1.addWidget(button1)
    button1.callbacks.click.register(
        lambda *a, **kw: button1.updateConfig(color=random_color_from_palette('dark')))

    slider = SliderWidget(
        widget_id='slider2', min_value=0, max_value=100, increment=0.1,
        value=20, color=random_color_from_palette('dark'), direction='horizontal',
        ticks=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        continuousUpdates=True)
    page1.addWidget(slider, width=6, height=2)

    popup_button = Button(widget_id='popup_button', text='Open Popup')
    page1.addWidget(popup_button, width=4)
    popup_button.callbacks.click.register(
        lambda *a, **kw: child_app.openPopup(
            Popup(id='popup1', type='dialog', title='Child Popup')))

    child_app.start()
    return child_app


def main():
    host = getHostIP()
    parent_port = 8100
    child_port = 8101

    parent_app = create_parent_gui(host, parent_port)
    child_app = create_child_gui(host, child_port, parent_port)

    # Link child GUI into the parent's sidebar
    time.sleep(1)
    parent_app.addChildGUI(
        child_address=host,
        child_port=child_port,
        parent_object=':parent_gui:/categories/category1',
    )

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
