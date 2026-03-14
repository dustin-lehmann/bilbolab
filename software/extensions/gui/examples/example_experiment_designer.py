import time
import threading

from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.experiment_designer import ExperimentDesignerWidget, ActionLibrary
from core.utils.experiments import (
    ExperimentParser, ExperimentRunner, ActionRegistry,
    register_builtin_actions, ExperimentStatus
)

SAMPLE_EXPERIMENT = """\
id: playback_demo
description: Multi-step experiment to test playback highlighting

variables:
  delay: 2.0
  iterations: 3

actions:
  - id: log_start
    type: log
    message: "Starting experiment"
  - id: wait_initial
    type: wait_time
    time: 1.0
  - id: set_counter
    type: set_variable
    name: iterations
    value: 5
  - id: wait_main
    type: wait_time
    time: ${delay}
  - id: log_progress
    type: log
    message: "Main phase complete"
  - id: wait_final
    type: wait_time
    time: 0.5
  - id: log_done
    type: log
    message: "Experiment finished"
"""

_runner = None
_runner_lock = threading.Lock()


def on_play(widget, yaml=''):
    """Run experiment using the widget's built-in runner connection."""
    global _runner

    with _runner_lock:
        if _runner is not None:
            return
    print(f"[PLAY] Received experiment YAML ({len(yaml)} chars)")

    registry = ActionRegistry()
    register_builtin_actions(registry)

    try:
        definition = ExperimentParser.from_yaml(yaml)
        runner = ExperimentRunner(definition, registry)
    except Exception as e:
        print(f"[PLAY] Failed to parse experiment: {e}")
        widget.set_mode('edit')
        return

    with _runner_lock:
        _runner = runner

    # Attach runner to widget for playback tracking — caller drives the step loop
    runner.initialize()
    widget.run(runner)

    def step_loop():
        global _runner

        while True:
            finished = runner.step()
            if finished:
                break
            time.sleep(0.05)

        print(f"[PLAY] Experiment {runner.status.value}")

        with _runner_lock:
            _runner = None

    threading.Thread(target=step_loop, daemon=True).start()


def on_stop(widget):
    """Abort the running experiment."""
    print("[STOP] Experiment stopped")
    with _runner_lock:
        if _runner is not None:
            _runner.abort('User stopped')


def example_experiment_designer():
    host = getHostIP()
    app = GUI(id="gui", host=host, run_js=True)

    category = Category(id="experiments", name="Experiments", icon="E")
    app.addCategory(category)

    page = Page(id="designer", name="Designer")
    category.addPage(page, position=1)

    designer = ExperimentDesignerWidget(
        'exp_designer',
        on_play=on_play,
        on_stop=on_stop,
        show_toolbar=True,
        action_library=ActionLibrary.BILBO,
    )
    page.addWidget(designer, row=1, column=1, width=40, height=18)

    app.start()

    # Load the sample experiment after the GUI has initialized
    time.sleep(10)
    designer.load_experiment(SAMPLE_EXPERIMENT)
    print("[INIT] Sample experiment loaded into designer")

    while True:
        time.sleep(1)


if __name__ == '__main__':
    example_experiment_designer()
