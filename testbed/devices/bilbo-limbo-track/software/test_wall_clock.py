#!/usr/bin/env python3
"""Test title, elapsed clock, and wall clock together."""

import threading
import time

from display import TestbedDisplay


def run_test(display: TestbedDisplay | None = None):
    if display is None:
        display = TestbedDisplay(fullscreen=False, width=1920, height=440)

    display.init()

    def test_task():
        time.sleep(1)

        display.set_background_color((0, 0, 0))
        display.set_title("testbed_bilbo_balancing_02_normal", color=(200, 0, 0), size=175)
        display.set_clock_color((255, 255, 255))
        display.start_clock(mode="replace_text")
        display.show_wall_clock(color=(255, 255, 255), size=80)

        time.sleep(15)

        display.clear()
        print("[Test] Done.")

    thread = threading.Thread(target=test_task, daemon=True)
    thread.start()
    display.start()


if __name__ == "__main__":
    run_test()
