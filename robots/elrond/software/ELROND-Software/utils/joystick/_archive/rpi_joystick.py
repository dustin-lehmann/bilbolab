import threading
import time

from evdev import InputDevice, categorize, ecodes


class JoystickButtonCallback:
    """

    """

    def __init__(self, event, function, arguments=None):
        """

        :param callback_type:
        :param button:
        :param function:
        :param kwargs:
        """
        self.event = event
        self.function = function
        self.arguments = arguments

    def __call__(self, *args, **kwargs):
        """

        :param args:
        :param kwargs:
        :return:
        """
        x = {**self.arguments, **kwargs}
        self.function(*args, **x)


A = 305
B = 304
X = 307
Y = 306

AXIS_LEFT_H = 0
AXIS_LEFT_V = 1
AXIS_RIGHT_H = 3
AXIS_RIGHT_V = 4


class RpiJoystick:
    _button_thread: threading.Thread
    _axis_thread: threading.Thread
    axes = []

    def __init__(self):
        self.callbacks = []
        try:
            # self.device = InputDevice('/dev/input/event4')
            self.device = InputDevice('/dev/input/event2')
        except Exception:
            raise Exception("No Joystick connected")
        self.axes = [0, 0, 0, 0]

        self._button_thread = threading.Thread(target=self._buttonThreadFunction)
        self._button_thread.start()

        self._axis_thread = threading.Thread(target=self._axisThreadFunction)
        self._axis_thread.start()

    def _buttonThreadFunction(self):
        for event in self.device.read_loop():
            if event.type == ecodes.EV_KEY:
                if event.value == 1:
                    callback = next((x for x in self.callbacks if x.event_a == event.code),
                                    None)
                    if callback is not None:
                        callback()

    def _axisThreadFunction(self):
        while True:
            self.axes[0] = (self.device.absinfo(AXIS_LEFT_H).value - 32768) / 32768
            self.axes[1] = -(self.device.absinfo(AXIS_LEFT_V).value - 32768) / 32768
            self.axes[2] = (self.device.absinfo(AXIS_RIGHT_H).value - 32768) / 32768
            self.axes[3] = -(self.device.absinfo(AXIS_RIGHT_V).value - 32768) / 32768

            time.sleep(0.025)

    def set_callback(self, event, callback, arguments=None):
        if arguments is None:
            arguments = {}
        self.callbacks.append(JoystickButtonCallback(event, callback, arguments))
