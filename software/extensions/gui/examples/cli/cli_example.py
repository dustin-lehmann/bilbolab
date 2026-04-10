"""
CLI (Command-Line Interface) Example
=====================================

Demonstrates the integrated terminal / CLI system:
  - Defining commands with typed arguments
  - Nested command sets (subcommands)
  - Commands that control GUI widgets (change colors, set values, toggle state)
  - Commands that query widget state and print results to the terminal
  - Optional, default, and flag arguments
  - Background / threaded command execution

The GUI shows a terminal widget where you can type commands, plus a panel of
widgets that the commands control.

Try these in the terminal:
    help                         — list available commands
    set color 0.9 0.2 0.3       — change the indicator colour
    set progress 75              — set the progress bar value
    toggle                       — toggle the LED on/off
    status                       — print current widget states
    greet Alice                  — personalised greeting
    greet Bob --shout            — greeting in uppercase
    countdown 5                  — background countdown (threaded)

Run from the `software/` directory:
    python -m extensions.gui.examples.cli.cli_example
"""

import time

from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.callout import Callout, CalloutType
from extensions.gui.src.lib.objects.python.indicators import CircleIndicator, ProgressIndicator
from extensions.gui.src.lib.objects.python.text import TextWidget
from extensions.tools.cli.cli import CLI, CommandSet, Command, CommandArgument


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    category = Category(id='cli_demo', name='CLI', icon='>')
    app.addCategory(category)

    page = Page(id='main', name='CLI Demo')
    category.addPage(page, position=1)

    # =========================================================================
    # Widgets that CLI commands will control
    # =========================================================================

    # Indicator LED
    led = CircleIndicator(
        widget_id='led',
        color=[0.2, 0.8, 0.3],
        size=70,
        blinking=False,
    )
    page.addWidget(led, row=1, column=1, width=2, height=2)

    led_state = {'on': True, 'color': [0.2, 0.8, 0.3]}

    # Progress bar
    progress = ProgressIndicator(
        widget_id='progress',
        value=0.0,
        title='Progress',
        label='0%',
        type='linear',
        direction='horizontal',
        track_fill_color=[0.3, 0.6, 0.9, 0.7],
    )
    page.addWidget(progress, row=1, column=4, width=8, height=2)

    progress_state = {'value': 0}

    # Status display
    status_text = TextWidget(
        widget_id='status',
        text='Waiting for commands...',
        font_size=11,
        horizontal_alignment='left',
        vertical_alignment='top',
        text_color=[0.7, 0.9, 0.7],
    )
    page.addWidget(status_text, row=3, column=1, width=12, height=4)

    logger = Logger('cli')

    # =========================================================================
    # Build the CLI command tree
    # =========================================================================
    root = CommandSet(name='root', description='CLI demo commands')

    # --- 'set' subcommand group ----------------------------------------------
    set_cmds = CommandSet(name='set', description='Change widget properties')

    def cmd_set_color(r: float, g: float, b: float):
        """Set the LED indicator colour (RGB 0-1)."""
        color = [float(r), float(g), float(b)]
        led.updateConfig(color=color)
        led_state['color'] = color
        status_text.updateConfig(text=f'LED colour set to [{r:.2f}, {g:.2f}, {b:.2f}]')
        logger.info(f'LED colour -> {color}')
        return f'Colour set to [{r:.2f}, {g:.2f}, {b:.2f}]'

    set_cmds.addCommand(Command(
        name='color',
        function=cmd_set_color,
        description='Set LED colour (R G B, each 0.0-1.0)',
        arguments=[
            CommandArgument(name='r', type=float, description='Red'),
            CommandArgument(name='g', type=float, description='Green'),
            CommandArgument(name='b', type=float, description='Blue'),
        ],
    ))

    def cmd_set_progress(value: int):
        """Set the progress bar percentage (0-100)."""
        value = max(0, min(100, int(value)))
        pct = value / 100.0
        progress.value = pct
        progress.updateConfig(label=f'{value}%')
        progress_state['value'] = value
        status_text.updateConfig(text=f'Progress set to {value}%')
        logger.info(f'Progress -> {value}%')
        return f'Progress = {value}%'

    set_cmds.addCommand(Command(
        name='progress',
        function=cmd_set_progress,
        description='Set progress bar (0-100)',
        arguments=[
            CommandArgument(name='value', type=int, description='Percentage'),
        ],
    ))

    root.addChild(set_cmds)

    # --- 'toggle' command ----------------------------------------------------
    def cmd_toggle():
        """Toggle the LED on/off."""
        led_state['on'] = not led_state['on']
        if led_state['on']:
            led.updateConfig(color=led_state['color'])
        else:
            led.updateConfig(color=[0.15, 0.15, 0.15])
        state = 'ON' if led_state['on'] else 'OFF'
        status_text.updateConfig(text=f'LED toggled {state}')
        logger.info(f'LED toggled {state}')
        return f'LED is now {state}'

    root.addCommand(Command(
        name='toggle',
        function=cmd_toggle,
        description='Toggle the LED indicator on/off',
    ))

    # --- 'status' command ----------------------------------------------------
    def cmd_status():
        """Print current state of all controlled widgets."""
        led_str = 'ON' if led_state['on'] else 'OFF'
        lines = [
            f"LED: {led_str} (colour {led_state['color']})",
            f"Progress: {progress_state['value']}%",
        ]
        result = '\n'.join(lines)
        status_text.updateConfig(text=result)
        logger.info('Status queried')
        return result

    root.addCommand(Command(
        name='status',
        function=cmd_status,
        description='Show current widget states',
    ))

    # --- 'greet' command (optional + flag arguments) -------------------------
    def cmd_greet(name: str, shout: bool = False):
        """Greet someone. Use --shout for uppercase."""
        msg = f'Hello, {name}!'
        if shout:
            msg = msg.upper()
        status_text.updateConfig(text=msg)
        app.callout_handler.add(Callout(
            content=msg, callout_type=CalloutType.INFO, timeout=3000))
        logger.info(f'Greeting: {msg}')
        return msg

    root.addCommand(Command(
        name='greet',
        function=cmd_greet,
        description='Greet someone (--shout for uppercase)',
        arguments=[
            CommandArgument(name='name', type=str, description='Person to greet'),
            CommandArgument(name='shout', type=bool, is_flag=True, optional=True,
                           default=False, description='Shout the greeting'),
        ],
    ))

    # --- 'countdown' command (runs in background thread) ---------------------
    def cmd_countdown(seconds: int = 5):
        """Run a countdown, updating progress bar each second."""
        total = max(1, int(seconds))
        for i in range(total, 0, -1):
            pct = int((1 - i / total) * 100)
            progress.value = pct / 100.0
            progress.updateConfig(label=f'{pct}% ({i}s left)')
            progress_state['value'] = pct
            status_text.updateConfig(text=f'Countdown: {i}s remaining')
            time.sleep(1)
        progress.value = 1.0
        progress.updateConfig(label='100%')
        progress_state['value'] = 100
        status_text.updateConfig(text='Countdown complete!')
        app.callout_handler.add(Callout(
            content='Countdown finished!',
            callout_type=CalloutType.SUCCESS, timeout=3000))
        logger.info('Countdown complete')
        return 'Done!'

    root.addCommand(Command(
        name='countdown',
        function=cmd_countdown,
        description='Background countdown (updates progress bar)',
        arguments=[
            CommandArgument(name='seconds', type=int, optional=True, default=5,
                           description='Duration in seconds'),
        ],
        execute_in_thread=True,
    ))

    # --- 'notify' command ----------------------------------------------------
    def cmd_notify(message: str, level: str = 'info'):
        """Send a callout notification. Level: info, warning, error, success."""
        type_map = {
            'info': CalloutType.INFO,
            'warning': CalloutType.WARNING,
            'error': CalloutType.ERROR,
            'success': CalloutType.SUCCESS,
        }
        ct = type_map.get(level.lower(), CalloutType.INFO)
        app.callout_handler.add(Callout(content=message, callout_type=ct, timeout=5000))
        logger.info(f'Notification [{level}]: {message}')
        return f'Sent {level} notification'

    root.addCommand(Command(
        name='notify',
        function=cmd_notify,
        description='Send a callout notification',
        arguments=[
            CommandArgument(name='message', type=str, description='Notification text'),
            CommandArgument(name='level', type=str, optional=True, default='info',
                           short_name='l', description='info/warning/error/success'),
        ],
    ))

    # --- Wire up CLI to the GUI's built-in CLI terminal ------------------------
    # The GUI has an integrated CLI terminal (app.cli_terminal). This is NOT
    # the same as TerminalWidget (which is an SSH terminal).
    cli = CLI(id='demo_cli', root=root, allow_set_change=True)
    app.cli_terminal.setCLI(cli)

    # --- Quick-action buttons (alternative to typing) ------------------------
    btn_toggle = Button(widget_id='btn_toggle', text='Toggle LED', color=[0.25, 0.4, 0.3])
    page.addWidget(btn_toggle, row=7, column=1, width=4, height=2)
    btn_toggle.callbacks.click.register(lambda *a, **kw: cmd_toggle())

    btn_reset = Button(widget_id='btn_reset', text='Reset Progress', color=[0.4, 0.25, 0.25])
    page.addWidget(btn_reset, row=7, column=5, width=4, height=2)
    btn_reset.callbacks.click.register(lambda *a, **kw: cmd_set_progress(0))

    btn_fill = Button(widget_id='btn_fill', text='Fill Progress', color=[0.25, 0.35, 0.5])
    page.addWidget(btn_fill, row=7, column=9, width=4, height=2)
    btn_fill.callbacks.click.register(lambda *a, **kw: cmd_set_progress(100))

    # --- Log forwarding to the GUI terminal ------------------------------------
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
