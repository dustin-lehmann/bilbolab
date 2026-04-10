"""
Tables Example
==============

Demonstrates the Table widget with:
  - Multiple column types: text, text input, number, slider, checkbox,
    indicator, select, multi-select, button
  - Table groups with collapsible sections and coloured outlines
  - Row highlighting and background colouring
  - Dynamic row insertion/deletion in a live update loop
  - Cell-level updates in real time

Run from the `software/` directory:
    python -m extensions.gui.examples.tables.tables_example
"""

import random
import time

from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.callout import Callout, CalloutType
from extensions.gui.src.lib.objects.python.table import (
    Table,
    TableGroup,
    Row,
    TextColumn,
    TextInputColumn,
    NumberColumn,
    SliderColumn,
    CheckboxColumn,
    IndicatorColumn,
    SelectColumn,
    MultiSelectColumn,
    ButtonColumn,
)


def rgba(r, g, b, a=1.0):
    """Helper to build RGBA colour lists."""
    return [float(r), float(g), float(b), float(a)]


logger = Logger('tables')


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    # Forward Python logs to the GUI's built-in CLI terminal
    def _log_to_gui(log_entry, log, log_logger, level):
        text = f'[{log_logger.name}] {log}'
        color = [c / 255 for c in LOGGING_COLORS[level]]
        app.print(text, color=color)

    addLogRedirection(_log_to_gui, minimum_level='INFO')

    category = Category(id='tables', name='Tables', icon='T')
    app.addCategory(category)

    page = Page(id='table_demo', name='Table Demo')
    category.addPage(page, position=1)

    # =========================================================================
    # Build the table with every column type
    # =========================================================================
    table = Table(widget_id='demo_table')

    table.add_column(TextColumn(id='name', title='Name', width=0.30, font_align='left'))
    table.add_column(TextInputColumn(id='note', title='Note', width=0.25, font_align='left'))
    table.add_column(NumberColumn(id='score', title='Score', increment=0.01, width=0.10, align='right'))
    table.add_column(SliderColumn(id='progress', title='Progress', min_value=0, max_value=100, increment=1, width=0.14))
    table.add_column(CheckboxColumn(id='ok', title='OK?', width=0.06))
    table.add_column(IndicatorColumn(id='status', title='Status', width=0.07))
    table.add_column(SelectColumn(
        id='prio', title='Priority', width=0.10,
        options={'low': 'Low', 'med': 'Medium', 'high': 'High'},
    ))
    table.add_column(MultiSelectColumn(
        id='tags', title='Tags', width=0.18,
        options={'a': 'Tag A', 'b': 'Tag B', 'c': 'Tag C', 'x': 'Extra'},
    ))
    table.add_column(ButtonColumn(id='action', title='Action', width=0.10))

    # =========================================================================
    # Groups — collapsible sections with coloured outlines
    # =========================================================================

    # Blue group — collapsible
    group_alpha = TableGroup(
        id='grp_alpha',
        title='Alpha Group (collapsible, blue) — double-click title to toggle',
        title_color='white',
        collapsible=True,
        group_color=rgba(0.2, 0.55, 1.0, 0.95),
    )

    # Green group
    group_beta = TableGroup(
        id='grp_beta',
        title='Beta Group (green)',
        title_color='white',
        collapsible=False,
        group_color=rgba(0.2, 1.0, 0.45, 0.9),
    )

    # Red group with highlight + background demos
    group_attention = TableGroup(
        id='grp_attention',
        title='Attention (red, highlight + row backgrounds)',
        title_color=rgba(1, 0.9, 0.9),
        collapsible=True,
        group_color=rgba(1.0, 0.25, 0.25, 0.95),
    )

    # Register groups on the table
    table.items[group_alpha.id] = group_alpha
    table.items[group_beta.id] = group_beta
    table.items[group_attention.id] = group_attention
    group_alpha._table = table
    group_beta._table = table
    group_attention._table = table

    # =========================================================================
    # Populate Alpha group
    # =========================================================================
    group_alpha.make_row(
        name='Alice', note='editable note', score=12.35, progress=30, ok=True,
        status=[rgba(0.1, 0.9, 0.2, 0.9), 'G'], prio='med', tags=['a', 'c'], action='Ping')
    group_alpha.make_row(
        name='Bob', note='try typing + Enter', score=7.89, progress=70, ok=False,
        status=[rgba(1.0, 0.75, 0.1, 0.9), 'W'], prio='low', tags=['b'], action='Ping')
    group_alpha.make_row(
        name='Charlie', note='multi-select works', score=99.0, progress=95, ok=True,
        status=[rgba(0.2, 0.7, 1.0, 0.9), 'I'], prio='high', tags=['a', 'b', 'x'], action='Ping')

    # =========================================================================
    # Populate Beta group (row_background_color demo)
    # =========================================================================
    group_beta.make_row(
        name='Dora (tinted row)', note='entire row tinted', score=42.42, progress=10,
        ok=True, status=[rgba(0.9, 0.9, 0.9, 0.85), '.'], prio='med', tags=['c'], action='Run',
        row_background_color=rgba(0.2, 0.2, 0.2, 0.55))
    group_beta.make_row(
        name='Evan', note='normal row', score=3.14, progress=50, ok=False,
        status=[rgba(0.9, 0.4, 0.2, 0.9), '!'], prio='low', tags=[], action='Run')

    # =========================================================================
    # Populate Attention group (highlight demo)
    # =========================================================================
    group_attention.make_row(
        name='Needs Review', note='row is outlined', score=0.01, progress=5, ok=False,
        status=[rgba(1.0, 0.2, 0.2, 0.95), '!'], prio='high', tags=['x'], action='Fix',
        highlight=True)
    group_attention.make_row(
        name='Critical', note='outline + tinted bg', score=-12.34, progress=15, ok=False,
        status=[rgba(1.0, 0.15, 0.15, 0.95), '!!'], prio='high', tags=['a', 'x'], action='Fix',
        highlight=True, row_background_color=rgba(0.35, 0.0, 0.0, 0.45))

    # =========================================================================
    # Ungrouped rows
    # =========================================================================
    table.make_row(
        name='Ungrouped Row 1', note='still supports highlight', score=1.23, progress=60,
        ok=True, status=[rgba(0.3, 1.0, 0.6, 0.9), 'ok'], prio='low', tags=['b'], action='Do',
        highlight=True)
    table.make_row(
        name='Ungrouped Row 2', note='row background', score=9.99, progress=80,
        ok=True, status=[rgba(0.7, 0.7, 1.0, 0.9), 'i'], prio='med', tags=['a', 'c'], action='Do',
        row_background_color=rgba(0.1, 0.15, 0.25, 0.55))

    # =========================================================================
    # Wire up Action button callbacks
    # =========================================================================
    # ButtonCell sends a cell_edit event when clicked. Register a callback on
    # each action cell so the click does something visible.

    def _register_action_callback(row):
        """Register an action button callback that logs and shows a callout."""
        cell = row['action']
        name_cell = row['name']

        def on_action_click(value, _cell=cell, _name=name_cell):
            row_name = _name.value
            action_text = _cell.value
            logger.info(f'{action_text} → {row_name}')
            app.callout_handler.add(Callout(
                content=f'{action_text} triggered for "{row_name}"',
                callout_type=CalloutType.INFO, timeout=3000))
            # Toggle the row's highlight as visual feedback
            row.highlight = not row.highlight
            table.updateConfig()

        cell.callbacks.update_request.register(on_action_click)

    # Register on all existing rows
    for group in [group_alpha, group_beta, group_attention]:
        for row in group.rows.values():
            _register_action_callback(row)
    for item in table.items.values():
        if isinstance(item, Row):
            _register_action_callback(item)

    page.addWidget(table, width=40, height=14)

    # =========================================================================
    # Buttons for dynamic row management
    # =========================================================================
    dynamic_state = {'counter': 0, 'rows': []}

    def add_dynamic_row(*args, **kwargs):
        dynamic_state['counter'] += 1
        n = dynamic_state['counter']
        row = group_alpha.make_row(
            name=f'Dynamic #{n}',
            note='added by button',
            score=random.uniform(-5, 105),
            progress=random.randint(0, 100),
            ok=(n % 2 == 0),
            status=[rgba(0.2, 0.55, 1.0, 0.9), 'D'],
            prio=random.choice(['low', 'med', 'high']),
            tags=random.sample(['a', 'b', 'c', 'x'], k=random.randint(0, 3)),
            action='Ping',
            highlight=(n % 2 == 0),
        )
        _register_action_callback(row)
        dynamic_state['rows'].append(row)
        logger.info(f'Added dynamic row #{n}')

    def remove_oldest_row(*args, **kwargs):
        if dynamic_state['rows']:
            old = dynamic_state['rows'].pop(0)
            old.delete()
            logger.info('Removed oldest dynamic row')
        else:
            logger.warning('No dynamic rows to remove')

    btn_add = Button(widget_id='btn_add_row', text='Add Row', color=[0.15, 0.4, 0.2])
    page.addWidget(btn_add, row=16, column=1, width=5, height=2)
    btn_add.callbacks.click.register(add_dynamic_row)

    btn_remove = Button(widget_id='btn_remove_row', text='Remove Oldest', color=[0.45, 0.15, 0.15])
    page.addWidget(btn_remove, row=16, column=7, width=5, height=2)
    btn_remove.callbacks.click.register(remove_oldest_row)

    # --- Start ---------------------------------------------------------------
    app.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
