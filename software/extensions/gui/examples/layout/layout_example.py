"""
Layout & Navigation Example
============================

Demonstrates the GUI's navigation and container system:
  - Multiple categories with icons
  - Subcategories (nested navigation tree)
  - Multiple pages within categories
  - Widget_Group with border and title
  - PagedWidgetGroup (tabbed container within a page)
  - Nested groups (group inside group)
  - ContainerWrapper with collapsible containers and stacks

Run from the `software/` directory:
    python -m extensions.gui.examples.layout.layout_example
"""

import random
import time

from core.utils.colors import random_color_from_palette
from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.objects import (
    Widget_Group,
    PagedWidgetGroup,
    GroupPageWidget,
    ContainerWrapper,
    GUI_Container_Stack,
    GUI_Container,
    GUI_CollapsibleContainer,
)
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.checkbox import CheckboxWidget
from extensions.gui.src.lib.objects.python.indicators import CircleIndicator
from extensions.gui.src.lib.objects.python.sliders import SliderWidget
from extensions.gui.src.lib.objects.python.text import TextWidget


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    # =========================================================================
    # Category tree
    # =========================================================================

    # Top-level categories
    cat_pages = Category(id='pages_demo', name='Pages', icon='P')
    cat_groups = Category(id='groups_demo', name='Groups', icon='G')
    cat_containers = Category(id='containers_demo', name='Containers', icon='C')
    app.addCategory(cat_pages)
    app.addCategory(cat_groups)
    app.addCategory(cat_containers)

    # Subcategories under "Pages"
    subcat_alpha = Category(id='subcat_alpha', name='Alpha')
    subcat_beta = Category(id='subcat_beta', name='Beta')
    cat_pages.addCategory(subcat_alpha)
    cat_pages.addCategory(subcat_beta)

    # Nested subcategory
    subcat_deep = Category(id='subcat_deep', name='Deep')
    subcat_alpha.addCategory(subcat_deep)

    # =========================================================================
    # Pages Demo — multiple pages in one category
    # =========================================================================
    page1 = Page(id='page_one', name='Page 1')
    page2 = Page(id='page_two', name='Page 2')
    page3 = Page(id='page_three', name='Page 3')
    cat_pages.addPage(page1, position=1)
    cat_pages.addPage(page2, position=2)
    cat_pages.addPage(page3, position=3)

    # Page 1 content
    p1_label = TextWidget(
        widget_id='p1_label',
        text='This is Page 1.\nUse the sidebar to navigate between pages and categories.',
        font_size=12, horizontal_alignment='left', vertical_alignment='top',
        text_color=[0.7, 0.85, 0.7],
    )
    page1.addWidget(p1_label, row=1, column=1, width=15, height=3)

    for i in range(6):
        btn = Button(widget_id=f'p1_btn_{i}', text=f'Button {i+1}',
                     color=random_color_from_palette('dark'))
        page1.addWidget(btn, row=4 + (i // 3) * 3, column=1 + (i % 3) * 5, width=4, height=2)
        btn.callbacks.click.register(
            lambda *a, idx=i, **kw: print(f'[layout] Page 1 — Button {idx+1} clicked'))

    # Page 2 content
    p2_label = TextWidget(
        widget_id='p2_label',
        text='This is Page 2 — a different view within the same category.',
        font_size=12, horizontal_alignment='left', vertical_alignment='top',
    )
    page2.addWidget(p2_label, row=1, column=1, width=15, height=2)

    slider = SliderWidget(
        widget_id='p2_slider', min_value=0, max_value=100, increment=1, value=50,
        color=[0.3, 0.5, 0.7], continuousUpdates=True)
    page2.addWidget(slider, row=3, column=1, width=12, height=2)

    # Page 3 — mostly empty, shows that pages can be sparse
    p3_label = TextWidget(
        widget_id='p3_label', text='Page 3 — intentionally sparse.',
        font_size=12, horizontal_alignment='center', vertical_alignment='center',
    )
    page3.addWidget(p3_label, row=8, column=5, width=10, height=2)

    # Subcategory pages
    sub_page = Page(id='alpha_page', name='Alpha Page')
    subcat_alpha.addPage(sub_page, position=1)
    sub_label = TextWidget(
        widget_id='alpha_label', text='Page inside Alpha subcategory.',
        font_size=12, horizontal_alignment='left', vertical_alignment='top',
    )
    sub_page.addWidget(sub_label, row=1, column=1, width=12, height=2)

    deep_page = Page(id='deep_page', name='Deep Page')
    subcat_deep.addPage(deep_page, position=1)
    deep_label = TextWidget(
        widget_id='deep_label', text='A deeply nested page (Pages > Alpha > Deep).',
        font_size=12, horizontal_alignment='left', vertical_alignment='top',
    )
    deep_page.addWidget(deep_label, row=1, column=1, width=14, height=2)

    # =========================================================================
    # Groups Demo — Widget_Group, nested groups
    # =========================================================================
    groups_page = Page(id='groups_page', name='Widget Groups')
    cat_groups.addPage(groups_page, position=1)

    # Basic bordered group with title
    group1 = Widget_Group(
        group_id='bordered_group',
        border=True,
        border_width=2,
        border_color=[0.4, 0.6, 0.9],
        title='Bordered Group',
        title_color=[0.4, 0.6, 0.9],
        rows=6,
        columns=10,
    )
    groups_page.addWidget(group1, row=1, column=1, width=12, height=8)

    g1_btn = Button(widget_id='g1_btn', text='Inside Group', color=[0.3, 0.3, 0.5])
    group1.addWidget(g1_btn, row=2, column=1, width=4, height=2)
    g1_btn.callbacks.click.register(
        lambda *a, **kw: print('[layout] Button inside bordered group clicked'))

    g1_slider = SliderWidget(
        widget_id='g1_slider', min_value=0, max_value=1, increment=0.1, value=0.5,
        color=[0.3, 0.5, 0.3])
    group1.addWidget(g1_slider, row=2, column=5, width=5, height=2)

    # Nested group inside group1
    group_inner = Widget_Group(
        group_id='inner_group',
        border=True,
        border_width=1,
        border_color=[0.7, 0.5, 0.3],
        title='Inner Group',
        title_color=[0.7, 0.5, 0.3],
        rows=3,
        columns=8,
    )
    group1.addWidget(group_inner, row=4, column=1, width=8, height=3)

    inner_btn = Button(widget_id='inner_btn', text='Nested', color=[0.5, 0.3, 0.2])
    group_inner.addWidget(inner_btn, row=1, column=1, width=3, height=2)
    inner_btn.callbacks.click.register(
        lambda *a, **kw: print('[layout] Button inside nested group clicked'))

    # --- Paged widget group (tabs) -------------------------------------------
    paged_page = Page(id='paged_page', name='Paged Groups')
    cat_groups.addPage(paged_page, position=2)

    tab1 = PagedWidgetGroup(group_id='tab1', title='Tab 1', icon='1')
    tab2 = PagedWidgetGroup(group_id='tab2', title='Tab 2', icon='2')
    tab3 = PagedWidgetGroup(group_id='tab3', title='Tab 3', icon='3')

    paged_group = GroupPageWidget(group_id='paged_tabs', group_bar_style='buttons')
    paged_group.addGroup(tab1)
    paged_group.addGroup(tab2)
    paged_group.addGroup(tab3)
    paged_page.addWidget(paged_group, row=1, column=1, width=18, height=16)

    # Populate tabs
    for tab, tab_name, label_text, color in [
        (tab1, 'Tab 1', 'Content of Tab 1', [0.3, 0.5, 0.7]),
        (tab2, 'Tab 2', 'Content of Tab 2', [0.5, 0.3, 0.6]),
        (tab3, 'Tab 3', 'Content of Tab 3', [0.6, 0.5, 0.2]),
    ]:
        lbl = TextWidget(
            widget_id=f'{tab.id}_label', text=label_text,
            font_size=13, horizontal_alignment='center', vertical_alignment='center')
        tab.addWidget(lbl, row=1, column=1, width=10, height=2)

        btn = Button(widget_id=f'{tab.id}_btn', text=f'Click in {tab_name}', color=color)
        tab.addWidget(btn, row=3, column=1, width=5, height=2)
        btn.callbacks.click.register(
            lambda *a, t=tab_name, **kw: print(f'[layout] Clicked inside {t}'))

    # =========================================================================
    # Containers Demo — stacks and collapsible containers
    # =========================================================================
    containers_page = Page(id='containers_page', name='Containers')
    cat_containers.addPage(containers_page, position=1)

    wrapper = ContainerWrapper('cw1', height_mode='auto')

    stack = GUI_Container_Stack('main_stack')
    wrapper.container.addObject(stack)

    # Collapsible container 1 — settings panel with sliders
    collapse1 = GUI_CollapsibleContainer(
        id='collapse_1', title='Settings',
        start_collapsed=False, height_mode='fixed', height=200)
    stack.addContainer(collapse1)

    settings_group = Widget_Group(group_id='settings_grp', rows=8, columns=14, fit=False)
    collapse1.addObject(settings_group)

    speed_slider = SliderWidget(
        widget_id='c_speed', min_value=0, max_value=100, increment=1, value=50,
        color=[0.3, 0.5, 0.7], continuousUpdates=True, title='Speed')
    settings_group.addWidget(speed_slider, row=1, column=1, width=10, height=2)

    gain_slider = SliderWidget(
        widget_id='c_gain', min_value=0, max_value=10, increment=0.1, value=2.5,
        color=[0.5, 0.3, 0.6], continuousUpdates=True, title='Gain')
    settings_group.addWidget(gain_slider, row=3, column=1, width=10, height=2)

    enable_check = CheckboxWidget(
        widget_id='c_enable', title='Enable output:', title_position='left', value=True)
    settings_group.addWidget(enable_check, row=5, column=1, width=8, height=1)

    apply_btn = Button(widget_id='c_apply', text='Apply', color=[0.2, 0.45, 0.3])
    settings_group.addWidget(apply_btn, row=7, column=1, width=3, height=1)
    apply_btn.callbacks.click.register(
        lambda *a, **kw: print('[layout] Settings applied'))

    # Fixed container — status display
    fixed_container = GUI_Container(
        'fixed_1', height_mode='fixed', height=120,
        background_color=[0.15, 0.15, 0.25])
    stack.addContainer(fixed_container)

    fixed_group = Widget_Group(group_id='fixed_grp', rows=5, columns=14, fit=False)
    fixed_container.addObject(fixed_group)

    fixed_label = TextWidget(
        widget_id='fixed_label', text='Fixed Container (always visible)',
        font_size=12, font_weight='bold', horizontal_alignment='left',
        vertical_alignment='center', text_color=[0.6, 0.7, 0.9])
    fixed_group.addWidget(fixed_label, row=1, column=1, width=12, height=1)

    for i, (name, color) in enumerate([
        ('Motor', [0.2, 0.7, 0.3]),
        ('Sensor', [0.7, 0.6, 0.1]),
        ('Network', [0.3, 0.5, 0.8]),
    ]):
        indicator = CircleIndicator(
            widget_id=f'fixed_ind_{i}', color=color, size=50)
        fixed_group.addWidget(indicator, row=3, column=1 + i * 3, width=1, height=1)

        ind_label = TextWidget(
            widget_id=f'fixed_ind_label_{i}', text=name,
            font_size=9, horizontal_alignment='center', vertical_alignment='center',
            text_color=[0.7, 0.7, 0.7])
        fixed_group.addWidget(ind_label, row=4, column=1 + i * 3, width=2, height=1)

    # Collapsible container 2 (starts collapsed) — action buttons
    collapse2 = GUI_CollapsibleContainer(
        id='collapse_2', title='Actions (click to expand)',
        start_collapsed=True, height_mode='fixed', height=180)
    stack.addContainer(collapse2)

    actions_group = Widget_Group(group_id='actions_grp', rows=6, columns=14, fit=False)
    collapse2.addObject(actions_group)

    action_names = ['Start', 'Stop', 'Reset', 'Calibrate', 'Export', 'Log']
    action_colors = [
        [0.15, 0.45, 0.2], [0.5, 0.15, 0.15], [0.4, 0.35, 0.1],
        [0.2, 0.35, 0.55], [0.35, 0.2, 0.5], [0.3, 0.3, 0.3],
    ]
    for i, (aname, acolor) in enumerate(zip(action_names, action_colors)):
        abtn = Button(
            widget_id=f'action_{aname.lower()}', text=aname, color=acolor,
            config={'fontSize': 10})
        actions_group.addWidget(abtn, row=1 + (i // 3) * 2, column=1 + (i % 3) * 4,
                                width=4, height=2)
        abtn.callbacks.click.register(
            lambda *a, n=aname, **kw: print(f'[layout] Action: {n}'))

    containers_page.addWidget(wrapper, row=1, column=1, width=18, height=18)

    # --- Start ---------------------------------------------------------------
    app.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
