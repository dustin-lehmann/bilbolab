#!/usr/bin/env python3
"""Test auto-shrinking font for long text and title."""

import threading
import time

from display import TestbedDisplay


def run_test(display: TestbedDisplay | None = None):
    if display is None:
        display = TestbedDisplay()

    display.init()

    def test_task():
        print("[Test] Long text auto-fit test...")
        time.sleep(2)

        # Reproduce actual experiment: title = experiment ID, clock in replace_text mode
        display.set_background_color((0, 0, 0))
        display.set_title("testbed_bilbo_balancing_02_normal", color=(200, 0, 0), size=175)
        display.set_clock_color((255, 255, 255))
        display.start_clock(mode="replace_text")
        time.sleep(10)


        print("[Test] Done.")

    thread = threading.Thread(target=test_task, daemon=True)
    thread.start()
    display.start()




if __name__ == "__main__":
    run_test()
