from RPi import GPIO
import atexit

from core.utils.exit import register_exit_callback

INIT = False


def init():
    GPIO.setmode(GPIO.BCM)


def setup(pin, direction, pull_up_down):
    GPIO.setup(pin, direction, pull_up_down)


def write(pin, value):
    GPIO.output(pin, value)


def toggle(pin):
    GPIO.output(pin, not GPIO.input(pin))


def read(pin):
    return GPIO.input(pin)


def add_event_detect(pin, flanks: int, callback, bouncetime):
    GPIO.add_event_detect(pin, flanks, callback, bouncetime)


def pwm_setup(pin, frequency) -> GPIO.PWM:
    GPIO.setup(pin, GPIO.OUT)
    return GPIO.PWM(pin, frequency)


def close(*args, **kwargs):
    GPIO.cleanup()


init()
register_exit_callback(close)
atexit.register(close)
