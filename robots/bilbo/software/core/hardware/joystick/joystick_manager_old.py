from collections.abc import Callable
from multiprocessing.managers import SyncManager

import math
import multiprocessing
import queue
import signal
import threading
import time
from os import environ

environ['SDL_JOYSTICK_HIDAPI_PS4_RUMBLE'] = '1'
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
import pygame

from pygame.joystick import Joystick as PyGameJoystick


# === CUSTOM PACKAGES ==================================================================================================
from core.hardware.joystick.joystick_mappings import joystick_mappings
from core.utils.callbacks import callback_definition, CallbackContainer, Callback, CallbackGroup
from core.utils.events import event_definition, Event, EventFlag
from core.utils.logging_utils import Logger
from core.utils.exit import register_exit_callback

# ======================================================================================================================
logger = Logger(name='Joysticks')


# ======================================================================================================================
class _JoystickManagerProcess:
    pygame_joysticks: list
    _thread: threading.Thread
    _exit: bool

    def __init__(self, event_queue: multiprocessing.Queue, rx_queue: multiprocessing.Queue, joystick_dict):

        self.event_queue = event_queue
        self.rx_queue = rx_queue

        self.pygame_joysticks = []
        self.axes_dict = joystick_dict
        self.joysticks = {}
        self._thread = threading.Thread(target=self.threadFunction)
        self._exit = False
        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def init():
        pygame.init()
        pygame.joystick.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self._thread.start()
        self.eventLoop()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self._exit = True
        try:
            self._thread.join(timeout=1)
        except Exception as e:
            logger.debug(f"Error while closing joystick manager: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def registerJoystick(self, joystick: PyGameJoystick):  # type: ignore
        self.pygame_joysticks.append(joystick)

        data = {
            'name': joystick.get_name(),
            'num_axes': joystick.get_numaxes(),
            'instance_id': joystick.get_instance_id(),
            'guid': joystick.get_guid(),
            'id': str(joystick.get_instance_id())
        }

        self.axes_dict[joystick.get_instance_id()] = [0] * joystick.get_numaxes()
        self.joysticks[joystick.get_instance_id()] = {
            'joystick': joystick,
        }

        return data

    # ------------------------------------------------------------------------------------------------------------------
    def handleRxEvent(self, event):
        if event['event'] == 'rumble':
            if event['data']['device_id'] not in self.joysticks.keys():
                return
            js = self.joysticks[event['data']['device_id']]['joystick']
            js.rumble(0.5, 0.5, 500)
            js.rumble(event['data']['strength'], event['data']['strength'], int(math.floor(event['data']['duration'])))

    # ------------------------------------------------------------------------------------------------------------------
    def threadFunction(self):
        while not self._exit:
            # Set the axes
            for joystick in self.pygame_joysticks:
                axes = [0] * joystick.get_numaxes()
                for axis in range(0, joystick.get_numaxes()):
                    axes[axis] = joystick.get_axis(axis)
                try:
                    self.axes_dict[(joystick.get_instance_id())] = axes
                except BrokenPipeError:
                    self.close()
                except Exception as e:
                    self.close()

            # Check for events:
            try:
                event = self.rx_queue.get_nowait()
                self.handleRxEvent(event)
            except queue.Empty:
                ...
            time.sleep(0.01)

    # ------------------------------------------------------------------------------------------------------------------
    def eventLoop(self):
        while not self._exit:
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEADDED:
                    pygame_joystick = pygame.joystick.Joystick(event.device_index)
                    pygame_joystick.init()
                    joystick_data = self.registerJoystick(pygame_joystick)
                    data = {
                        'event': 'JOYDEVICEADDED',
                        'data': joystick_data,
                    }
                    self.event_queue.put(data)
                elif event.type == pygame.JOYDEVICEREMOVED:
                    data = {
                        'event': 'JOYDEVICEREMOVED',
                        'data': {
                            'device_id': event.instance_id,
                        }
                    }
                    self.event_queue.put(data)
                elif event.type == pygame.JOYBUTTONDOWN:
                    data = {
                        'event': 'JOYBUTTONDOWN',
                        'data': {
                            'device_id': event.instance_id,
                            'button': event.button,
                        }
                    }
                    self.event_queue.put(data)
                elif event.type == pygame.JOYBUTTONUP:
                    data = {
                        'event': 'JOYBUTTONUP',
                        'data': {
                            'device_id': event.instance_id,
                            'button': event.button,
                        }
                    }
                    self.event_queue.put(data)
                elif event.type == pygame.JOYHATMOTION:
                    data = {
                        'event': 'JOYHATMOTION',
                        'data': {
                            'device_id': event.instance_id,
                            'value': event.value
                        }
                    }
                    self.event_queue.put(data)
                elif event.type == pygame.JOYAXISMOTION:
                    ...
                    # print(event)
            pygame.event.clear()
            time.sleep(0.01)


# ------------------------------------------------------------------------------------------------------------------
def joystick_event_process(event_queue: multiprocessing.Queue, rx_queue: multiprocessing.Queue, joystick_dict):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGQUIT, signal.SIG_IGN)
    jm = _JoystickManagerProcess(event_queue, rx_queue, joystick_dict)
    jm.init()
    jm.start()


# ======================================================================================================================
# ======================================================================================================================
@callback_definition
class JoystickManager_Callbacks:
    new_joystick: CallbackContainer
    joystick_disconnected: CallbackContainer


# ======================================================================================================================
class JoystickManager:
    joysticks: dict
    callbacks: JoystickManager_Callbacks

    _event_thread: threading.Thread
    _process: multiprocessing.Process
    _exit: bool
    _mp_manager: SyncManager
    _event_rx_queue: multiprocessing.Queue
    _tx_queue: multiprocessing.Queue
    _joystick_dict: dict

    # === INIT =========================================================================================================
    def __init__(self, accept_unmapped_joysticks: bool = False):
        multiprocessing.set_start_method('spawn')
        register_exit_callback(self.exit)
        self.joysticks = {}

        self.accept_unmapped_joysticks = accept_unmapped_joysticks

        self.callbacks = JoystickManager_Callbacks()
        self._exit = False
        self._event_thread = threading.Thread(target=self._eventThreadFunction, daemon=True)
        self._joystick_thread = threading.Thread(target=self._joystickThreadFunction, daemon=True)
        self._event_rx_queue = multiprocessing.Queue()

        self._tx_queue = multiprocessing.Queue()
        self._mp_manager = multiprocessing.Manager()

        self._joystick_dict = self._mp_manager.dict()  # type: ignore

        self._process = multiprocessing.Process(target=joystick_event_process,
                                                args=(self._event_rx_queue, self._tx_queue, self._joystick_dict))

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        logger.info(f"Joystick manager started. Accept unmapped joysticks: {self.accept_unmapped_joysticks}")
        self._event_thread.start()
        self._joystick_thread.start()

        if self._process is not None:
            self._process.start()

    # ------------------------------------------------------------------------------------------------------------------
    def exit(self, *args, **kwargs):
        self._exit = True
        self._mp_manager.shutdown()
        time.sleep(0.5)
        if self._event_thread.is_alive():
            self._event_thread.join()

        if self._joystick_thread.is_alive():
            self._joystick_thread.join()

        if self._process is not None:
            if self._process.is_alive():
                try:
                    logger.info("Closing joystick manager process")
                    self._process.terminate()
                    self._process.join()
                except Exception as e:

                    ...
        logger.info("Close joystick manager")

    # ------------------------------------------------------------------------------------------------------------------
    def rumbleJoystick(self, device_id, strength=0.4, duration=200):
        self._tx_queue.put({
            'event': 'rumble',
            'data': {
                'device_id': device_id,
                'strength': strength,
                'duration': duration
            }
        })

    # ------------------------------------------------------------------------------------------------------------------
    def getJoystickById(self, id):
        if id not in self.joysticks.keys():
            logger.info(f"Joystick with ID {id} not connected")
            return None

        return self.joysticks[id]

    # ------------------------------------------------------------------------------------------------------------------
    def waitForJoystick(self, already_connected=False, timeout=None):
        joystick: Joystick | None = None

        if already_connected and len(self.joysticks) > 0:
            joystick = next(iter(self.joysticks.values()))
            return joystick

        def callback(new_joystick, *args, **kwargs):
            nonlocal joystick
            joystick = new_joystick

        callback_obj = self.callbacks.new_joystick.register(callback)
        t = time.time()
        while joystick is None and (timeout is not None and time.time() - t < timeout):
            time.sleep(0.1)

        self.callbacks.new_joystick.remove(callback_obj)

        if joystick is None:
            logger.warning(f"Wait for joystick timeout ({timeout} s). No joystick connected")
            return None

        joystick.rumble(strength=0.5, duration=500)
        return joystick

    # ------------------------------------------------------------------------------------------------------------------
    def _registerJoystick(self, data):
        joystick = Joystick(manager=self)
        joystick.register(data)

        if joystick.name not in joystick_mappings and not self.accept_unmapped_joysticks:
            logger.debug(f"Joystick {joystick.name} not found in mapping. Discarding.")
            del joystick
            return

        self.joysticks[joystick.id] = joystick
        logger.info(f"New Joystick connected. Type: {joystick.name}. ID: {joystick.id}")

        for callback in self.callbacks.new_joystick:
            callback(joystick)

    # ------------------------------------------------------------------------------------------------------------------
    def _removeJoystick(self, data):
        joystick = self.joysticks[(data['device_id'])]
        self.joysticks.pop(joystick.id)
        logger.info(f"Joystick disconnected. Type: {joystick.name}. ID: {joystick.id}")
        for callback in self.callbacks.joystick_disconnected:
            callback(joystick)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleButtonEvent(self, data, event_type):

        # Get the Joystick for the event
        joystick = self.joysticks[(data['device_id'])]
        button = data['button']
        if event_type == "down":
            joystick._buttonDown(button)
        elif event_type == "up":
            joystick._buttonUp(button)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleJoyHatEvent(self, data):
        joystick = self.joysticks[data['device_id']]
        if data['value'] == (0, 1):
            direction = 'up'
        elif data['value'] == (1, 0):
            direction = 'right'
        elif data['value'] == (-1, 0):
            direction = 'left'
        elif data['value'] == (0, -1):
            direction = 'down'
        else:
            return

        joystick._joyhatEvent(direction)

    # ------------------------------------------------------------------------------------------------------------------
    def _joystickThreadFunction(self):
        while not self._exit:
            try:
                for id, joystick in self.joysticks.items():
                    joystick.axis = self._joystick_dict[id]
            except Exception as e:
                pass
            time.sleep(0.01)

    # ------------------------------------------------------------------------------------------------------------------
    def _eventThreadFunction(self):

        while not self._exit:
            try:
                event = self._event_rx_queue.get(timeout=1)
                self._handleEvent(event)
            except queue.Empty:
                pass
            # Events
            time.sleep(0.01)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleEvent(self, event):
        if event['event'] == 'JOYDEVICEADDED':
            self._registerJoystick(event['data'])
        elif event['event'] == 'JOYDEVICEREMOVED':
            self._removeJoystick(event['data'])
        elif event['event'] == 'JOYBUTTONDOWN':
            self._handleButtonEvent(event['data'], 'down')
        elif event['event'] == 'JOYBUTTONUP':
            self._handleButtonEvent(event['data'], 'up')
        elif event['event'] == 'JOYHATMOTION':
            self._handleJoyHatEvent(event['data'])


# ======================================================================================================================
@event_definition
class JoystickEvents:
    button: Event = Event(flags=EventFlag('button', list))


@callback_definition
class JoystickCallbacks(CallbackGroup):
    A: CallbackContainer
    B: CallbackContainer
    X: CallbackContainer
    Y: CallbackContainer
    START: CallbackContainer
    SELECT: CallbackContainer
    L1: CallbackContainer
    R1: CallbackContainer
    L3: CallbackContainer
    R3: CallbackContainer


# ======================================================================================================================
class Joystick:
    id: str
    instance_id: int
    guid: str
    name: str
    connected: bool
    axis: list

    num_axes: int
    mapping: dict[str, int] | None
    events: JoystickEvents
    button_callbacks: list['JoystickButtonCallback']

    # joyhat_callbacks: list['JoyHatCallback']

    # buttons: dict  # TODO: add a button dict that stores whether a button is pressed and for how long

    # === INIT =========================================================================================================
    def __init__(self, manager: JoystickManager) -> None:
        """
        """
        self.connected = False
        self.axis = []
        self.button_callbacks = []
        # self.joyhat_callbacks = []

        self.events = JoystickEvents()
        self.callbacks = JoystickCallbacks()

        self.manager = manager
        self.mapping = None

        self.instance_id = -1
        self.id = ''
        self.num_axes = 0
        self.guid = ''
        self.name = ''

    # === METHODS ======================================================================================================
    def register(self, data):
        self.id = data['instance_id']
        self.instance_id = data['instance_id']
        self.guid = data['guid']
        self.name = data['name']
        self.num_axes = data['num_axes']

        if self.name in joystick_mappings:
            logger.debug(f"Joystick mapping found for {self.name}")
            self.mapping = joystick_mappings[self.name]
        else:
            logger.debug(f"No mapping found for {self.name}")
            self.mapping = None

        self.axis = [0] * self.num_axes
        self.connected = True
        self.rumble(strength=0.2, duration=200)

    # ------------------------------------------------------------------------------------------------------------------
    def setButtonCallback(self, button: int | str, function: Callable, event: str = 'down', parameters: dict = None,
                          lambdas: dict = None):

        if isinstance(button, list):
            for _button in button:
                self.button_callbacks.append(JoystickButtonCallback(_button, event, function, parameters, lambdas))
        else:
            self.button_callbacks.append(JoystickButtonCallback(button, event, function, parameters, lambdas))

    # ------------------------------------------------------------------------------------------------------------------
    def clearAllButtonCallbacks(self):
        self.button_callbacks = []
        self.callbacks.clearAllCallbacks()

    # ------------------------------------------------------------------------------------------------------------------
    def setJoyHatCallback(self, direction: str, function: Callable, parameters: dict = None, lambdas: dict = None):
        raise NotImplementedError("setJoyHatCallback not implemented for joystick")
        # if isinstance(direction, list):
        #     for dir in direction:
        #         self.joyhat_callbacks.append(JoyHatCallback(dir, function, parameters, lambdas))
        # else:
        #     self.joyhat_callbacks.append(JoyHatCallback(direction, function, parameters, lambdas))

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.connected = False

    # ------------------------------------------------------------------------------------------------------------------
    def rumble(self, strength=0.5, duration=500):
        self.manager.rumbleJoystick(self.instance_id, strength, duration)

    # ------------------------------------------------------------------------------------------------------------------
    def getAxis(self, axis: int | str):

        value = 0

        # Read the Axis
        if isinstance(axis, int):
            value = self.axis[axis]
        elif isinstance(axis, str):
            if self.mapping is not None:
                if axis in self.mapping['AXES']:
                    axis_num: int = self.mapping['AXES'][axis]  # type: ignore
                    value = self.axis[axis_num]
            else:
                logger.debug(f"No mapping found for {self.name} while reading axis {axis}")

        return value

    # ------------------------------------------------------------------------------------------------------------------
    def _buttonDown(self, button: int):
        callbacks_num = [callback for callback in self.button_callbacks if
                         callback.button == button and callback.event == 'down']

        logger.important(f"Joystick: {self.id}, Event: Button {button} down")

        for callback in callbacks_num:
            callback(joystick=self, button=button, event='down')

        button_name = ''
        if self.mapping is not None:
            button_name = {v: k for k, v in self.mapping['BUTTONS'].items()}.get(button, "")

            if button_name is not None:
                callbacks_name = [callback for callback in self.button_callbacks if
                                  callback.button == button_name and callback.event == 'down']
                for callback in callbacks_name:
                    callback(joystick=self, button=button_name, event='down')

                # Get it from the normal callbacks
                if hasattr(self.callbacks, button_name):
                    callback_container: CallbackContainer = getattr(self.callbacks, button_name)
                    callback_container.call()

        self.events.button.set(data=button, flags={'button': [button, button_name]})

    # ------------------------------------------------------------------------------------------------------------------
    def _buttonUp(self, button):
        callbacks = [callback for callback in self.button_callbacks if
                     callback.button == button and callback.event == 'up']

        for callback in callbacks:
            callback(joystick=self, button=button, event='up')

    # ------------------------------------------------------------------------------------------------------------------
    def _joyhatEvent(self, direction):
        # Lets handle joyhat events as button event
        if direction == 'up':
            button = "DPAD_UP"
        elif direction == 'right':
            button = "DPAD_RIGHT"
        elif direction == 'left':
            button = "DPAD_LEFT"
        elif direction == 'down':
            button = "DPAD_DOWN"
        else:
            return

        callbacks_name = [callback for callback in self.button_callbacks if
                          callback.button == button and callback.event == 'down']
        for callback in callbacks_name:
            callback(joystick=self, button=button, event='down')


# ======================================================================================================================
class JoyHatCallback:
    callback: Callback
    direction: str

    def __init__(self, direction, function: Callable, parameters: dict = None, lambdas: dict = None):
        self.direction = direction
        self.callback = Callback(function, parameters, lambdas)

    def __call__(self, *args, **kwargs):
        """

        :param args:
        :param kwargs:
        :return:
        """
        self.callback(*args, **kwargs)


# ======================================================================================================================
class JoystickButtonCallback:
    callback: Callback
    event: str

    def __init__(self, button: str | int, event, function: Callable, parameters: dict = None, lambdas: dict = None):
        """

        :param button:
        :param function:
        """
        self.button = button
        self.event = event
        self.callback = Callback(function, parameters, lambdas)

    def __call__(self, *args, **kwargs):
        """

        :param args:
        :param kwargs:
        :return:
        """
        self.callback(*args, **kwargs)


# ======================================================================================================================
def main():
    jm = JoystickManager()
    jm.init()
    jm.start()

    logger.setLevel('DEBUG')

    joystick = jm.waitForJoystick(timeout=2)

    while True:
        if len(jm.joysticks) > 0:
            for id, joystick in jm.joysticks.items():
                ...
                # print(f"{joystick.axis[1]}")
        time.sleep(0.1)


if __name__ == '__main__':
    main()
