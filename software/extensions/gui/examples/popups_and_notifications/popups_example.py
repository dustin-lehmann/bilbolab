"""
Popups & Notifications Example
==============================

Demonstrates every popup and notification style:
  - Window popup (opens in a new browser window)
  - Dialog popup (in-page overlay, draggable)
  - Tab popup (opens in a new browser tab)
  - Non-closeable dialog (must use dismiss button)
  - Large resizable popup with button grid
  - Semi-transparent dialog
  - YesNo confirmation dialog
  - Callout notifications: INFO, WARNING, ERROR, SUCCESS
  - Interactive callout with custom buttons

Each popup type is triggered by a button.  The buttons are laid out on a
single page so you can try them all side by side.

Run from the `software/` directory:
    python -m extensions.gui.examples.popups_and_notifications.popups_example
"""

import time

from core.utils.colors import random_color_from_palette
from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.callout import Callout, CalloutType, CalloutButton
from extensions.gui.src.lib.objects.python.popup import Popup, YesNoPopup
from extensions.gui.src.lib.objects.python.sliders import SliderWidget
from extensions.gui.src.lib.objects.python.text import TextWidget


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    category = Category(id='popups', name='Popups', icon='P')
    app.addCategory(category)

    page = Page(id='popup_demo', name='Popups & Notifications')
    category.addPage(page, position=1)

    # --- Section label -------------------------------------------------------
    section_popups = TextWidget(
        widget_id='section_popups',
        text='Popup Types',
        font_size=14,
        font_weight='bold',
        horizontal_alignment='left',
        vertical_alignment='center',
        text_color=[0.8, 0.8, 0.8],
    )
    page.addWidget(section_popups, row=1, column=1, width=18, height=1)

    # =========================================================================
    # 1. Window popup
    # =========================================================================
    def open_window(*args, **kwargs):
        popup = Popup(
            popup_id='window_popup', type='window', title='Window Popup',
            closeable=True, size=[600, 400], grid=[6, 6])

        label = TextWidget(
            widget_id='wlabel',
            text='This is a Window popup.\nIt opens in a separate browser window.',
            font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=6, height=3)

        slider = SliderWidget(
            widget_id='wslider', min_value=0, max_value=100,
            increment=1, value=50, color=random_color_from_palette('dark'))
        popup.group.addWidget(slider, row=4, column=1, width=4, height=1)

        close_btn = Button(widget_id='wclose', text='Close', color=[0.5, 0.15, 0.15])
        popup.group.addWidget(close_btn, row=6, column=5, width=2, height=1)
        close_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)
        print('[popups] Opened window popup')

    btn_window = Button(widget_id='btn_window', text='Window Popup', color=[0.15, 0.3, 0.5])
    page.addWidget(btn_window, row=2, column=1, width=5, height=2)
    btn_window.callbacks.click.register(open_window)

    # =========================================================================
    # 2. Dialog popup (in-page overlay)
    # =========================================================================
    def open_dialog(*args, **kwargs):
        popup = Popup(
            popup_id='dialog_popup', type='dialog', title='Dialog Popup',
            closeable=True, size=[500, 350], grid=[5, 5])

        label = TextWidget(
            widget_id='dlabel',
            text='This is a Dialog popup.\nIt overlays the current page.\nYou can drag and resize it.',
            font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=5, height=2)

        btn_a = Button(widget_id='dbtn_a', text='Option A', color=random_color_from_palette('dark'))
        popup.group.addWidget(btn_a, row=3, column=1, width=2, height=1)
        btn_a.callbacks.click.register(lambda *a, **kw: print('[popups] Dialog: Option A'))

        btn_b = Button(widget_id='dbtn_b', text='Option B', color=random_color_from_palette('dark'))
        popup.group.addWidget(btn_b, row=3, column=3, width=2, height=1)
        btn_b.callbacks.click.register(lambda *a, **kw: print('[popups] Dialog: Option B'))

        close_btn = Button(widget_id='dclose', text='Close', color=[0.5, 0.15, 0.15])
        popup.group.addWidget(close_btn, row=5, column=4, width=2, height=1)
        close_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)
        print('[popups] Opened dialog popup')

    btn_dialog = Button(widget_id='btn_dialog', text='Dialog Popup', color=[0.3, 0.15, 0.5])
    page.addWidget(btn_dialog, row=2, column=7, width=5, height=2)
    btn_dialog.callbacks.click.register(open_dialog)

    # =========================================================================
    # 3. Tab popup
    # =========================================================================
    def open_tab(*args, **kwargs):
        popup = Popup(
            popup_id='tab_popup', type='tab', title='Tab Popup',
            closeable=True, size=[700, 500], grid=[6, 6])

        label = TextWidget(
            widget_id='tlabel',
            text='This is a Tab popup.\nIt opens in a new browser tab.',
            font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=6, height=2)

        close_btn = Button(widget_id='tclose', text='Close', color=[0.5, 0.15, 0.15])
        popup.group.addWidget(close_btn, row=6, column=5, width=2, height=1)
        close_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)
        print('[popups] Opened tab popup')

    btn_tab = Button(widget_id='btn_tab', text='Tab Popup', color=[0.15, 0.5, 0.3])
    page.addWidget(btn_tab, row=2, column=13, width=5, height=2)
    btn_tab.callbacks.click.register(open_tab)

    # =========================================================================
    # 4. Non-closeable dialog
    # =========================================================================
    def open_noncloseable(*args, **kwargs):
        popup = Popup(
            popup_id='nc_popup', type='dialog', title='Non-Closeable',
            closeable=False, size=[400, 250], grid=[4, 4])

        label = TextWidget(
            widget_id='nclabel',
            text='This dialog has no close button.\nUse the button below to dismiss.',
            font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=4, height=2)

        dismiss = Button(widget_id='ncdismiss', text='Dismiss', color=[0.4, 0.4, 0.1])
        popup.group.addWidget(dismiss, row=4, column=2, width=2, height=1)
        dismiss.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)
        print('[popups] Opened non-closeable dialog')

    btn_nc = Button(widget_id='btn_nc', text='Non-Closeable', color=[0.5, 0.4, 0.1])
    page.addWidget(btn_nc, row=5, column=1, width=5, height=2)
    btn_nc.callbacks.click.register(open_noncloseable)

    # =========================================================================
    # 5. Semi-transparent dialog (no overlay)
    # =========================================================================
    def open_transparent(*args, **kwargs):
        popup = Popup(
            popup_id='transparent_popup', type='dialog', title='Transparent',
            closeable=True, size=[450, 300], grid=[5, 5],
            disable_gui=False, opacity=0.7)

        label = TextWidget(
            widget_id='trlabel',
            text='Semi-transparent dialog (opacity=0.7)\nwith no background overlay.',
            font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=5, height=2)

        close_btn = Button(widget_id='trclose', text='Close', color=[0.5, 0.15, 0.15])
        popup.group.addWidget(close_btn, row=5, column=4, width=2, height=1)
        close_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)
        print('[popups] Opened transparent dialog')

    btn_transparent = Button(widget_id='btn_transparent', text='Transparent', color=[0.35, 0.2, 0.35])
    page.addWidget(btn_transparent, row=5, column=7, width=5, height=2)
    btn_transparent.callbacks.click.register(open_transparent)

    # =========================================================================
    # 6. YesNo confirmation dialog
    # =========================================================================
    def open_yesno(*args, **kwargs):
        popup = YesNoPopup(title='Confirm Action', message='Do you want to proceed?')
        popup.yes_button.callbacks.click.register(
            lambda *a, **kw: print('[popups] YesNo: YES'))
        popup.no_button.callbacks.click.register(
            lambda *a, **kw: print('[popups] YesNo: NO'))
        app.openPopup(popup)
        print('[popups] Opened YesNo popup')

    btn_yesno = Button(widget_id='btn_yesno', text='YesNo Dialog', color=[0.4, 0.2, 0.1])
    page.addWidget(btn_yesno, row=5, column=13, width=5, height=2)
    btn_yesno.callbacks.click.register(open_yesno)

    # =========================================================================
    # Callout / notification section
    # =========================================================================
    section_callouts = TextWidget(
        widget_id='section_callouts',
        text='Callout Notifications',
        font_size=14,
        font_weight='bold',
        horizontal_alignment='left',
        vertical_alignment='center',
        text_color=[0.8, 0.8, 0.8],
    )
    page.addWidget(section_callouts, row=8, column=1, width=18, height=1)

    # Info callout
    btn_info = Button(widget_id='btn_info', text='INFO', color=[0.1, 0.3, 0.6])
    page.addWidget(btn_info, row=9, column=1, width=4, height=2)
    btn_info.callbacks.click.register(lambda *a, **kw: (
        app.callout_handler.add(Callout(
            content='This is an informational callout.',
            callout_type=CalloutType.INFO, timeout=5000)),
        print('[popups] INFO callout'),
    ))

    # Warning callout
    btn_warn = Button(widget_id='btn_warn', text='WARNING', color=[0.6, 0.45, 0.1])
    page.addWidget(btn_warn, row=9, column=5, width=4, height=2)
    btn_warn.callbacks.click.register(lambda *a, **kw: (
        app.callout_handler.add(Callout(
            content='Something needs your attention!',
            callout_type=CalloutType.WARNING, timeout=5000)),
        print('[popups] WARNING callout'),
    ))

    # Error callout
    btn_error = Button(widget_id='btn_error', text='ERROR', color=[0.6, 0.15, 0.15])
    page.addWidget(btn_error, row=9, column=9, width=4, height=2)
    btn_error.callbacks.click.register(lambda *a, **kw: (
        app.callout_handler.add(Callout(
            content='An error has occurred!',
            callout_type=CalloutType.ERROR, timeout=5000)),
        print('[popups] ERROR callout'),
    ))

    # Success callout
    btn_success = Button(widget_id='btn_success', text='SUCCESS', color=[0.15, 0.45, 0.15])
    page.addWidget(btn_success, row=9, column=13, width=4, height=2)
    btn_success.callbacks.click.register(lambda *a, **kw: (
        app.callout_handler.add(Callout(
            content='Operation completed successfully!',
            callout_type=CalloutType.SUCCESS, timeout=5000)),
        print('[popups] SUCCESS callout'),
    ))

    # Persistent callout (no timeout)
    btn_persist = Button(widget_id='btn_persist', text='Persistent Callout', color=[0.35, 0.35, 0.35])
    page.addWidget(btn_persist, row=12, column=1, width=5, height=2)
    btn_persist.callbacks.click.register(lambda *a, **kw: (
        app.callout_handler.add(Callout(
            content='This callout stays until manually dismissed.',
            callout_type=CalloutType.INFO, timeout=None)),
        print('[popups] Persistent callout'),
    ))

    # --- Start ---------------------------------------------------------------
    app.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
