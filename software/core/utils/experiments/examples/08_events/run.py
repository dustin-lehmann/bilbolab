"""Example 08: Events — emit and wait for internal experiment events.

Concept: Actions can emit named events and other actions can wait
for them. This enables synchronization between parallel branches.

What happens step by step:
  1. A parallel block starts two branches concurrently
  2. Branch A: logs "Waiting...", then blocks on wait_for_event("ready")
  3. Branch B: logs "Working...", waits 200ms, then emits "ready"
  4. Branch A unblocks, logs "Event received!"
  5. Parallel block completes when both branches finish
  6. Log "All done."

Why: Events let parallel branches coordinate. The emitter doesn't
need to know who is waiting, and the waiter doesn't need to know
who will emit — they just agree on an event name.
"""

import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..')))

from core.utils.experiments import (
    ExperimentParser, ExperimentRunner,
    ActionRegistry, register_builtin_actions,
)


def main():
    registry = ActionRegistry()
    register_builtin_actions(registry)

    definition = ExperimentParser.from_dict({
        'id': 'events_demo',
        'actions': [
            {
                'type': 'parallel',
                'actions': [
                    # Branch A: wait for the event
                    {
                        'type': 'group',
                        'actions': [
                            {'type': 'log', 'message': '  [A] Waiting for "ready" event...'},
                            {'type': 'wait_for_event', 'event': 'ready', 'timeout': 5.0},
                            {'type': 'log', 'message': '  [A] Event received!'},
                        ],
                    },
                    # Branch B: do work then emit
                    {
                        'type': 'group',
                        'actions': [
                            {'type': 'log', 'message': '  [B] Working...'},
                            {'type': 'wait_time', 'time': 0.2},
                            {'type': 'log', 'message': '  [B] Emitting "ready"'},
                            {'type': 'emit_event', 'event': 'ready'},
                        ],
                    },
                ],
            },
            {'type': 'log', 'message': 'All done.'},
        ],
    })

    runner = ExperimentRunner(definition, registry)
    runner.initialize()

    while not runner.step():
        time.sleep(0.005)

    print(f'\nStatus: {runner.status}')


if __name__ == '__main__':
    main()
