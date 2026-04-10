"""
Experiment Designer Loop Example
================================

Extends the basic experiment designer example with a loop container
to test nested playback highlighting.

Run from the `software/` directory:
    python -m extensions.gui.examples.advanced.experiment_designer_loop_example
"""

import time
import threading

from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.experiment_designer import (
    ExperimentDesignerWidget,
    ActionLibrary,
)
from core.utils.experiments import (
    ExperimentParser,
    ExperimentRunner,
    ActionRegistry,
    register_builtin_actions,
)

LOOP_EXPERIMENT = """\
id: loop_demo
description: Experiment with a loop container to test nested playback highlighting

variables:
  iterations: 3
  pause: 1.5

actions:
  - id: log_start
    type: log
    message: "Starting loop experiment"
  - id: wait_setup
    type: wait_time
    time: 5.1
  - id: main_loop
    type: loop
    count: ${iterations}
    variable: i
    actions:
      - id: log_iter
        type: log
        message: "Iteration ${i}"
      - id: wait_iter
        type: wait_time
        time: ${pause}
      - id: set_progress
        type: set_variable
        name: progress
        value: ${i}
  - id: log_done
    type: log
    message: "Loop experiment finished"
"""

_runner = None
_runner_lock = threading.Lock()


def on_play(widget, yaml=''):
    """Parse YAML and start experiment execution."""
    global _runner
    with _runner_lock:
        if _runner is not None:
            return
    print(f'[experiment_loop] Received YAML ({len(yaml)} chars)')

    registry = ActionRegistry()
    register_builtin_actions(registry)

    try:
        definition = ExperimentParser.from_yaml(yaml)
        runner = ExperimentRunner(definition, registry)
    except Exception as e:
        print(f'[experiment_loop] Failed to parse: {e}')
        widget.set_mode('edit')
        return

    with _runner_lock:
        _runner = runner

    runner.initialize()
    widget.run(runner)

    def step_loop():
        global _runner
        while True:
            finished = runner.step()
            if finished:
                break
            time.sleep(0.05)
        print(f'[experiment_loop] Finished: {runner.status.value}')
        with _runner_lock:
            _runner = None

    threading.Thread(target=step_loop, daemon=True).start()


def on_stop(widget):
    """Abort the running experiment."""
    print('[experiment_loop] Stopped')
    with _runner_lock:
        if _runner is not None:
            _runner.abort('User stopped')


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    category = Category(id='experiments', name='Experiments', icon='E')
    app.addCategory(category)

    page = Page(id='designer', name='Designer')
    category.addPage(page, position=1)

    designer = ExperimentDesignerWidget(
        'exp_designer',
        on_play=on_play,
        on_stop=on_stop,
        show_toolbar=True,
        action_library=ActionLibrary.BILBO,
        transparent=True,
    )
    page.addWidget(designer, row=1, column=1, width=40, height=18)

    app.start()

    time.sleep(10)
    designer.load_experiment(LOOP_EXPERIMENT)
    print('[experiment_loop] Loop experiment loaded')

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
