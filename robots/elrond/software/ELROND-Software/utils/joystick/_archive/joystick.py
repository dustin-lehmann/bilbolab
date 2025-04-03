import ctypes
import logging
from typing import Dict, Tuple, Optional, Union, Sequence, Iterable, Iterator
import threading
# import pygame
import time


# source code from SO
# https://stackoverflow.com/questions/19749404/is-it-possible-to-rumble-a-xbox-360-controller-with-python

# Define necessary structures
class XInputVibration(ctypes.Structure):
    _fields_ = [("wLeftMotorSpeed", ctypes.c_ushort),
                ("wRightMotorSpeed", ctypes.c_ushort)]


# Load XInput.dll (-> change version number if needed (C:\Windows\System32\XInput1_<version number>))
# Or download the .dll file from the internet, it's the MICROSOFT COMMON CONTROLLER API
# 22.07.2021: newest version == 4
# XInput = ctypes.windll.xinput1_4
#
# # Set up function argument types and return type
# XInputSetState = XInput.XInputSetState
# XInputSetState.argtypes = [ctypes.c_uint, ctypes.POINTER(XInputVibration)]
# XInputSetState.restype = ctypes.c_uint

registered_joysticks = 0


# My Imports

def sign(x):
    return x and (1, -1)[x < 0]


class JoystickButton:
    time_pressed: float
    pressed: bool
    id: int
    name: str

    def __init__(self):
        pass


class Joystick:
    joystick: pygame.joystick.Joystick
    information: Dict[str, Union[int, str]]
    mapping: Dict[str, int]
    dead_band: float
    id: int
    connected: bool
    exit: bool
    axis: list
    callbacks: list

    buttons: dict  # TODO: add a button dict that stores wether a button is pressed and for how long

    _exit: bool

    _enable_rumble: bool
    _rumble_time: int

    # === INIT =========================================================================================================
    def __init__(self, Ts: float = 0.04) -> None:
        """

        :param Ts:
        """
        self.connected = False
        self.axis = [0, 0, 0, 0, 0, 0]
        self.Ts = Ts
        self.callbacks = []

        self._exit = False

        self._enable_rumble = False
        self._rumble_time = 0

        thread = threading.Thread(target=self._thread_fun, daemon=True)
        thread.start()

    # === METHODS ======================================================================================================
    def set_callback(self, callback_type, button, callback, arguments):
        """

        :param callback_type:
        :param button:
        :param callback:
        :param kwargs:
        :return:
        """
        self.callbacks.append(JoystickButtonCallback(callback_type, button, callback, arguments))

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self._exit = True

    # ------------------------------------------------------------------------------------------------------------------
    def rumble(self, strength, duration):
        if self.connected:
            if strength == 0:
                self._enable_rumble = False
                self._rumble(self.id, 0, 0)
            else:
                self._rumble(self.id, strength, strength)
                self._enable_rumble = True
                self._rumble_time = time.perf_counter_ns() + duration * 1e9

    # === PRIVATE METHODS ==============================================================================================
    def _thread_fun(self):
        """

        :return:
        """
        pygame.init()
        pygame.joystick.init()
        while not self._exit:
            self._update()
            time.sleep(0.001)

        logging.info(f"Close Joystick")

    # ------------------------------------------------------------------------------------------------------------------
    def _update(self):
        global registered_joysticks
        """

        :return:
        """

        # Events
        for event in pygame.event_a.get():
            if event.type == pygame.JOYDEVICEADDED and not self.connected:
                try:
                    self.joystick = pygame.joystick.Joystick(registered_joysticks)
                    self.id = self.joystick.get_instance_id()
                    self.connected = True
                    registered_joysticks += 1
                    logging.info(f"Joystick connected with ID {self.id}")
                except:
                    raise Exception("damn")
            elif event.type == pygame.JOYBUTTONDOWN:
                if event.instance_id == 0:
                    callback = next((x for x in self.callbacks if x.datatype == 'button' and x.button == event.button),
                                    None)
                    if callback is not None:
                        callback()
            elif event.type == pygame.JOYBUTTONUP:
                pass
            elif event.type == pygame.JOYHATMOTION:
                if event.instance_id == 0:
                    callback = next((x for x in self.callbacks if x.datatype == 'hat'), None)
                    if callback is not None:
                        callback(value=event.value)
            elif event.type == pygame.JOYAXISMOTION:
                if event.instance_id == 0:
                    callback = next((x for x in self.callbacks if x.datatype == 'axis' and x.button == event.axis),
                                    None)
                    if callback is not None:
                        callback(value=event.value)

        # Axes
        if self.connected:
            axes = self.joystick.get_numaxes()
            for i in range(0, axes):
                self.axis[i] = self.joystick.get_axis(i)

            # Rumble
            if self._enable_rumble:
                if self._rumble_time < time.perf_counter_ns():
                    self._rumble(self.id, 0, 0)
                    self._enable_rumble = False

        time.sleep(self.Ts)

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _rumble(joystick_id, left_motor, right_motor):
        """

        :param joystick_id:
        :param left_motor:
        :param right_motor:
        :return:
        """
        vibration = XInputVibration(int(left_motor * 65535), int(right_motor * 65535))
        XInputSetState(joystick_id, ctypes.byref(vibration))


class JoystickButtonCallback:
    """

    """

    def __init__(self, callback_type, button, function, arguments):
        """

        :param callback_type:
        :param button:
        :param function:
        :param kwargs:
        """
        self.type = callback_type
        self.button = button
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

# joystick_count = pygame.joystick.get_count()

# for i in range(joystick_count):
#     joystick = pygame.joystick.Joystick(i)
#     if joystick == self.joystick:
#         axes = joystick.get_numaxes()
#
#         for j in range(axes):
#             self.axes[j] = joystick.get_axis(j)
