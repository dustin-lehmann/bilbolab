import time
import threading
import RPi.GPIO as GPIO

from core.utils.exit import register_exit_callback


class Button:
    _thread: threading.Thread

    def __init__(self, pin, short_press_callback=None, long_press_callback=None,
                 double_click_callback=None, long_press_duration=0.75, double_click_interval=0.3):
        """
        Initialize the Button.

        :param pin: BCM pin for the button.
        :param short_press_callback: Function to call on a short press.
        :param long_press_callback: Function to call on a long press.
        :param double_click_callback: Function to call on a double click.
        :param long_press_duration: Duration in seconds to detect a long press.
        :param double_click_interval: Max time in seconds between two clicks to register a double click.
        """
        self.pin = pin
        self.short_press_callback = short_press_callback
        self.long_press_callback = long_press_callback
        self.double_click_callback = double_click_callback
        self.long_press_duration = long_press_duration
        self.double_click_interval = double_click_interval

        self.last_pressed_time = None
        self.last_click_time = None
        self.long_press_triggered = False
        self.click_count = 0
        self.monitoring = True
        self.double_click_detected = False  # Flag to suppress short press callback after double click

        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._thread = threading.Thread(target=self._monitor_button, daemon=True)
        self._thread.start()

        register_exit_callback(self.stop)

    def _monitor_button(self):
        while self.monitoring:
            try:
                if GPIO.input(self.pin) == GPIO.LOW:  # Button pressed
                    if not self.last_pressed_time:
                        self.last_pressed_time = time.time()
                        self.long_press_triggered = False

                    elapsed_time = time.time() - self.last_pressed_time
                    if elapsed_time >= self.long_press_duration and not self.long_press_triggered:
                        self.long_press_triggered = True
                        if self.long_press_callback:
                            self.long_press_callback()
                else:  # Button released
                    if self.last_pressed_time and not self.long_press_triggered:
                        current_time = time.time()

                        if self.last_click_time and (current_time - self.last_click_time) <= self.double_click_interval:
                            # Double click detected
                            self.double_click_detected = True  # Set flag to suppress short press
                            if self.double_click_callback:
                                self.double_click_callback()
                            self.click_count = 0
                            self.last_click_time = None
                        else:
                            # Start a new click sequence
                            self.click_count = 1
                            self.last_click_time = current_time

                            # Schedule single click after a delay if no double-click occurs
                            def single_click_check():
                                time.sleep(self.double_click_interval)
                                if not self.double_click_detected:  # Only trigger if no double click
                                    if self.short_press_callback:
                                        self.short_press_callback()
                                self.click_count = 0
                                self.double_click_detected = False  # Reset double click flag

                            threading.Thread(target=single_click_check).start()

                    self.last_pressed_time = None
                    self.long_press_triggered = False

                time.sleep(0.01)  # Polling interval (10ms)
            except Exception:
                return

    def stop(self, *args, **kwargs):
        self.monitoring = False
        if self._thread.is_alive():
            self._thread.join()
