from __future__ import annotations

import math
import multiprocessing
import multiprocessing.connection
import platform
import queue
import signal
import threading
import time
from collections.abc import Callable
from os import environ

environ['SDL_JOYSTICK_HIDAPI_PS4_RUMBLE'] = '1'
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
import pygame

from pygame.joystick import Joystick as PyGameJoystick

# === CUSTOM PACKAGES ==================================================================================================
from extensions.hardware.joystick.joystick_mappings import joystick_mappings
from core.utils.callbacks import callback_definition, CallbackContainer, Callback, CallbackGroup
from core.utils.events import event_definition, Event, EventFlag, EventContainer
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger

# ======================================================================================================================
LONG_PRESSED_TIME = 1.0

logger = Logger(name='Joysticks')


def _convert_mapping(host_mapping: dict) -> dict:
    """Convert host mapping format to internal format used by Joystick classes.

    Host format:  {'BUTTONS': {name: index}, 'AXES': {name: index}}
    Internal format: {buttons: {index: name}, axes: {index: {name, scale}}}
    """
    buttons = {}
    if 'BUTTONS' in host_mapping:
        buttons = {v: k for k, v in host_mapping['BUTTONS'].items()}

    axes = {}
    if 'AXES' in host_mapping:
        for name, index in host_mapping['AXES'].items():
            axes[index] = {'name': name, 'scale': 1}

    return {'buttons': buttons, 'axes': axes}


# ======================================================================================================================
class _JoystickManagerProcess:
    pygame_joysticks: list
    _thread: threading.Thread
    _exit: bool

    def __init__(self, event_conn: multiprocessing.connection.Connection,
                 rx_conn: multiprocessing.connection.Connection, joystick_dict):

        self.event_conn = event_conn
        self.rx_conn = rx_conn

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
    def registerJoystick(self, joystick: PyGameJoystick):
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
            if event['data']['device_id'] not in self.joysticks:
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
                if self.rx_conn.poll():
                    event = self.rx_conn.recv()
                    self.handleRxEvent(event)
            except (EOFError, OSError):
                self.close()
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
                    self.event_conn.send(data)
                elif event.type == pygame.JOYDEVICEREMOVED:
                    data = {
                        'event': 'JOYDEVICEREMOVED',
                        'data': {
                            'device_id': event.instance_id,
                        }
                    }
                    self.event_conn.send(data)
                elif event.type == pygame.JOYBUTTONDOWN:
                    data = {
                        'event': 'JOYBUTTONDOWN',
                        'data': {
                            'device_id': event.instance_id,
                            'button': event.button,
                        }
                    }
                    self.event_conn.send(data)
                elif event.type == pygame.JOYBUTTONUP:
                    data = {
                        'event': 'JOYBUTTONUP',
                        'data': {
                            'device_id': event.instance_id,
                            'button': event.button,
                        }
                    }
                    self.event_conn.send(data)
                elif event.type == pygame.JOYHATMOTION:
                    data = {
                        'event': 'JOYHATMOTION',
                        'data': {
                            'device_id': event.instance_id,
                            'value': event.value
                        }
                    }
                    self.event_conn.send(data)
                elif event.type == pygame.JOYAXISMOTION:
                    ...
            pygame.event.clear()
            time.sleep(0.01)


# ------------------------------------------------------------------------------------------------------------------
def joystick_event_process(event_conn: multiprocessing.connection.Connection,
                           rx_conn: multiprocessing.connection.Connection, joystick_dict):
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    def _handle_term(*args):
        jm.close()

    jm = _JoystickManagerProcess(event_conn, rx_conn, joystick_dict)
    signal.signal(signal.SIGTERM, _handle_term)
    jm.init()
    jm.start()


# ======================================================================================================================
@callback_definition
class JoystickManager_Callbacks:
    new_joystick: CallbackContainer
    joystick_disconnected: CallbackContainer


@event_definition
class JoystickManager_Events:
    new_joystick: Event = Event(copy_data_on_set=False)
    joystick_disconnected: Event = Event(copy_data_on_set=False)


# === JOYSTICK MANAGER =================================================================================================
class JoystickManager:
    joysticks: dict[int, Joystick]
    callbacks: JoystickManager_Callbacks
    events: JoystickManager_Events

    _exit: bool = False

    # === INIT =========================================================================================================
    def __init__(self, accept_unmapped_joysticks: bool = False):
        try:
            multiprocessing.set_start_method('spawn')
        except RuntimeError:
            pass  # Already set

        self.joysticks = {}
        self.accept_unmapped_joysticks = accept_unmapped_joysticks
        self.callbacks = JoystickManager_Callbacks()
        self.events = JoystickManager_Events()
        self.logger = Logger(f"JoystickManager", "DEBUG")

        self._event_thread = threading.Thread(target=self._event_task, daemon=True)
        self._joystick_axes_thread = threading.Thread(target=self._joystick_axes_task, daemon=True)

        # Use Pipes instead of Queues to avoid semaphore leaks with 'spawn' start method.
        self._event_recv, event_send = multiprocessing.Pipe(duplex=False)
        tx_recv, self._tx_send = multiprocessing.Pipe(duplex=False)
        self._mp_manager = multiprocessing.Manager()
        self._joystick_mp_dict = self._mp_manager.dict()
        self._process = multiprocessing.Process(target=joystick_event_process,
                                                args=(event_send, tx_recv, self._joystick_mp_dict))

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info(f"Joystick manager started. Accept unmapped joysticks: {self.accept_unmapped_joysticks}")
        self._event_thread.start()
        self._joystick_axes_thread.start()

        if self._process is not None:
            self._process.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        if self._exit:
            return
        self._exit = True

        # Terminate the subprocess first
        if self._process is not None:
            try:
                if self._process.is_alive():
                    self.logger.info("Closing joystick manager process")
                    self._process.terminate()
                    self._process.join(timeout=3)
                    if self._process.is_alive():
                        self.logger.warning("Joystick manager process did not terminate, killing it")
                        self._process.kill()
                        self._process.join(timeout=2)
            except Exception as e:
                self.logger.error(f"Error closing joystick manager process: {type(e).__name__}: {e}")
            finally:
                try:
                    self._process.close()
                except ValueError:
                    pass

        # Shut down the multiprocessing manager
        try:
            self._mp_manager.shutdown()
        except Exception:
            pass

        # Close pipe ends
        for conn in (self._event_recv, self._tx_send):
            try:
                conn.close()
            except Exception:
                pass

        if self._event_thread.is_alive():
            self._event_thread.join(timeout=2)
        if self._joystick_axes_thread.is_alive():
            self._joystick_axes_thread.join(timeout=2)

        self.logger.info("Close joystick manager")

    # ------------------------------------------------------------------------------------------------------------------
    def rumbleJoystick(self, device_id, strength=0.4, duration=200):
        try:
            self._tx_send.send({
                'event': 'rumble',
                'data': {
                    'device_id': device_id,
                    'strength': strength,
                    'duration': duration
                }
            })
        except (BrokenPipeError, OSError):
            pass

    # ------------------------------------------------------------------------------------------------------------------
    def getJoystickById(self, id) -> Joystick | None:
        if id not in self.joysticks:
            self.logger.info(f"Joystick with ID {id} not connected")
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
            self.logger.warning(f"Wait for joystick timeout ({timeout} s). No joystick connected")
            return None

        joystick.rumble(strength=0.5, duration=500)
        return joystick

    # === PRIVATE METHODS ==============================================================================================
    def _event_task(self):
        while not self._exit:
            try:
                if self._event_recv.poll(timeout=1):
                    event = self._event_recv.recv()
                    self._handle_event(event['event'], event['data'])
            except (EOFError, OSError):
                break
            time.sleep(0.01)

    # ------------------------------------------------------------------------------------------------------------------
    def _joystick_axes_task(self):
        while not self._exit:
            try:
                for id, joystick in self.joysticks.items():
                    joystick.axes = self._joystick_mp_dict[id]
            except Exception as e:
                self.logger.error(f"Error while updating joystick axes: {e}")
            time.sleep(0.02)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_event(self, event: str, data: dict | None = None):
        match event:
            case 'JOYDEVICEADDED':
                self._handle_joystick_added(data)
            case 'JOYDEVICEREMOVED':
                self._handle_joystick_removed(data)
            case 'JOYBUTTONDOWN':
                self._handle_joystick_button_down(data)
            case 'JOYBUTTONUP':
                self._handle_joystick_button_up(data)
            case 'JOYHATMOTION':
                self._handle_joystick_hat_motion(data)
            case _:
                self.logger.warning(f"Unknown event received: {event}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_joystick_added(self, data: dict):
        instance_id = data['instance_id']
        guid = data['guid']
        name = data['name']
        num_axes = data['num_axes']

        self.logger.debug(f"New joystick connected. Type: {name}. ID: {instance_id}. GUID: {guid}")

        # Get host mapping and convert to internal format
        if name in joystick_mappings:
            mapping = _convert_mapping(joystick_mappings[name])
        elif self.accept_unmapped_joysticks:
            mapping = {'buttons': {}, 'axes': {}}
        else:
            self.logger.debug(f"Joystick {name} not found in mapping. Discarding.")
            return

        joystick = Joystick(id=str(instance_id),
                            manager=self,
                            instance_id=instance_id,
                            guid=guid,
                            name=name,
                            num_axes=num_axes,
                            mapping=mapping)

        if instance_id in self.joysticks:
            self.logger.warning(f"Joystick with ID {instance_id} already exists. Ignoring duplicate connection.")
            return

        self.joysticks[instance_id] = joystick
        self.logger.info(f"New Joystick connected. Type: {name}. ID: {instance_id}")

        self.callbacks.new_joystick.call(joystick)
        self.events.new_joystick.set(joystick)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_joystick_removed(self, data: dict):
        device_id = data['device_id']

        if device_id not in self.joysticks:
            self.logger.warning(f"Joystick with ID {device_id} not found. Ignoring disconnect event.")
            return
        joystick = self.joysticks[device_id]
        self.logger.info(f"Joystick with ID \"{device_id}\" disconnected")
        self.joysticks.pop(device_id)

        self.callbacks.joystick_disconnected.call(joystick)
        self.events.joystick_disconnected.set(joystick)
        joystick.on_disconnect()

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_joystick_button_down(self, data: dict):
        device_id = data['device_id']
        button = data['button']
        if device_id in self.joysticks:
            self.joysticks[device_id]._on_button_down(button)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_joystick_button_up(self, data: dict):
        device_id = data['device_id']
        button = data['button']
        if device_id in self.joysticks:
            self.joysticks[device_id]._on_button_up(button)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_joystick_hat_motion(self, data: dict):
        device_id = data['device_id']
        value = tuple(data['value'])
        if device_id in self.joysticks:
            self.joysticks[device_id]._on_hat_motion(value)


# === JOYSTICK BUTTON ==================================================================================================
@callback_definition
class JoystickButtonCallbacks(CallbackGroup):
    pressed: CallbackContainer
    long_pressed: CallbackContainer


@event_definition
class JoystickButtonEvents(EventContainer):
    pressed: Event
    long_pressed: Event


class JoystickButton:
    id: str
    index: int

    def __init__(self, id: str, index: int):
        self.id = id
        self.index = index
        self.callbacks = JoystickButtonCallbacks()
        self.events = JoystickButtonEvents()

    def on_pressed(self):
        self.callbacks.pressed.call()
        self.events.pressed.set()

    def on_long_pressed(self):
        self.callbacks.long_pressed.call()
        self.events.long_pressed.set()

    def clear_callbacks_and_events(self):
        self.callbacks.clearAllCallbacks()


class JoystickButtons:
    _buttons: dict[int, JoystickButton]

    def __init__(self, mapping: dict):
        self._buttons = {}
        self._buttons_by_id: dict[str, JoystickButton] = {}
        self._mapping = mapping
        mapping_buttons: dict[int, str] = mapping['buttons']

        for button_index, button_id in mapping_buttons.items():
            button = JoystickButton(button_id, button_index)
            self._buttons[button_index] = button
            if button_id in self._buttons_by_id:
                raise ValueError(f"Duplicate button id in mapping: {button_id}")
            self._buttons_by_id[button_id] = button

    def clear_callbacks_and_events(self):
        for button in self._buttons.values():
            button.clear_callbacks_and_events()

    def _get_button_by_id(self, button_id: str) -> JoystickButton | None:
        return self._buttons_by_id.get(button_id)

    def __getitem__(self, item: int | str) -> JoystickButton | None:
        if isinstance(item, int):
            return self._buttons.get(item)
        return self._get_button_by_id(item)

    def __contains__(self, item: int | str) -> bool:
        if isinstance(item, int):
            return item in self._buttons
        return self._get_button_by_id(item) is not None


# === JOYSTICK HAT =====================================================================================================
class JoystickHatKey:
    callbacks: JoystickButtonCallbacks
    events: JoystickButtonEvents

    def __init__(self, hat_key: tuple[int, int]):
        self.callbacks = JoystickButtonCallbacks()
        self.events = JoystickButtonEvents()

    def on_pressed(self):
        self.callbacks.pressed.call()
        self.events.pressed.set()

    def on_long_pressed(self):
        self.callbacks.long_pressed.call()
        self.events.long_pressed.set()

    def clear_callbacks_and_events(self):
        self.callbacks.clearAllCallbacks()


class JoystickHat:
    MAPPING = {
        'up': (0, 1),
        'down': (0, -1),
        'left': (-1, 0),
        'right': (1, 0)
    }

    _keys: dict[tuple[int, int], JoystickHatKey]

    def __init__(self):
        self._keys = {
            (0, 1): JoystickHatKey((0, 1)),
            (0, -1): JoystickHatKey((0, -1)),
            (-1, 0): JoystickHatKey((-1, 0)),
            (1, 0): JoystickHatKey((1, 0))
        }

    def clear_callbacks_and_events(self):
        for key in self._keys.values():
            key.clear_callbacks_and_events()

    def __getitem__(self, item: tuple[int, int] | str) -> JoystickHatKey:
        if isinstance(item, tuple):
            return self._keys[item]
        return self._keys[self.MAPPING[item]]


# === JOYSTICK =========================================================================================================
@callback_definition
class JoystickCallbacks:
    button_pressed: CallbackContainer
    button_long_pressed: CallbackContainer
    disconnected: CallbackContainer


@event_definition
class JoystickEvents:
    button_pressed: Event = Event(flags=EventFlag('button', (str, int)))
    button_long_pressed: Event = Event(flags=EventFlag('button', (str, int)))
    disconnected: Event


class Joystick:
    id: str
    instance_id: int
    guid: str
    name: str
    connected: bool
    num_axes: int
    mapping: dict[str, int | dict] | None

    buttons: JoystickButtons
    hat: JoystickHat
    axes: list[float]

    _pressed_buttons: dict[int, float]
    _pressed_hat_keys: dict[tuple[int, int], float]
    _hat_value = (0, 0)

    # === INIT =========================================================================================================
    def __init__(self, id: str,
                 instance_id: int,
                 guid: str,
                 name: str,
                 num_axes: int,
                 mapping: dict | None,
                 manager: JoystickManager):
        self.id = id
        self.manager = manager
        self.instance_id = instance_id
        self.guid = guid
        self.name = name
        self.connected = True
        self.num_axes = num_axes
        self.mapping = mapping

        self.axes = [0] * num_axes

        self.callbacks = JoystickCallbacks()
        self.events = JoystickEvents()
        self.logger = Logger(f"Joystick {name}:{self.instance_id}", "DEBUG")

        # Build the buttons and hat
        self.buttons = JoystickButtons(mapping)
        self.hat = JoystickHat()
        self._pressed_buttons = {}
        self._pressed_hat_keys = {}

        self._axis_name_to_index = {
            axis["name"]: index
            for index, axis in self.mapping["axes"].items()
        }

        self._exit = False
        self._thread = threading.Thread(target=self._task, daemon=True)
        self._lock = threading.Lock()
        self._thread.start()

        self.rumble(strength=0.2, duration=200)

    # === METHODS ======================================================================================================
    def _task(self):
        while not self._exit:
            now = time.monotonic()

            # Snapshot keys only (cheap)
            with self._lock:
                button_keys = list(self._pressed_buttons.keys())
                hat_keys = list(self._pressed_hat_keys.keys())

            # ---- Buttons long press ----
            for button in button_keys:
                with self._lock:
                    t0 = self._pressed_buttons.get(button)
                    if t0 is None or (now - t0) <= LONG_PRESSED_TIME:
                        continue
                    self._pressed_buttons.pop(button, None)

                btn = self.buttons[button]
                if btn is not None:
                    btn.on_long_pressed()
                    self.logger.debug(f"Button {btn.index}/{btn.id} long pressed")
                    self.callbacks.button_long_pressed.call(button)
                    self.events.button_long_pressed.set(data=button, flags={'button': btn.id})
                    self.rumble(strength=0.7, duration=100)

            # ---- Hat long press ----
            for k in hat_keys:
                with self._lock:
                    t0 = self._pressed_hat_keys.get(k)
                    if t0 is None or (now - t0) <= LONG_PRESSED_TIME:
                        continue
                    self._pressed_hat_keys.pop(k, None)

                key = self.hat[k]
                key.on_long_pressed()
                self.logger.debug(f"Hat key {k} long pressed")
                self.rumble(strength=0.7, duration=100)

            time.sleep(0.1)

    # ------------------------------------------------------------------------------------------------------------------
    def on_disconnect(self):
        self.connected = False
        self._exit = True
        self._thread.join(timeout=2)
        self.clear_callbacks_and_events()
        self.callbacks.disconnected.call()
        self.events.disconnected.set()

    # ------------------------------------------------------------------------------------------------------------------
    def rumble(self, strength=0.4, duration=200):
        self.manager.rumbleJoystick(self.instance_id, strength, duration)

    # ------------------------------------------------------------------------------------------------------------------
    def getAxis(self, axis: int | str):
        if isinstance(axis, int):
            index = axis
        else:
            index = self._axis_name_to_index.get(axis)
            if index is None:
                self.logger.warning(f"Axis {axis} not found in mapping. Returning 0.")
                return 0.0

        value = self.axes[index]
        scale = float(self.mapping['axes'][index]['scale'])

        return value * scale

    # ------------------------------------------------------------------------------------------------------------------
    def clearAllButtonCallbacks(self):
        self.buttons.clear_callbacks_and_events()
        self.hat.clear_callbacks_and_events()

    # ------------------------------------------------------------------------------------------------------------------
    def clear_callbacks_and_events(self):
        self.buttons.clear_callbacks_and_events()
        self.hat.clear_callbacks_and_events()

    # === PRIVATE METHODS ==============================================================================================
    def _on_button_down(self, button: int):
        self.logger.debug(f"Button {button} down")
        with self._lock:
            self._pressed_buttons[button] = time.monotonic()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_button_up(self, button: int):
        self.logger.debug(f"Button {button} up")

        with self._lock:
            t0 = self._pressed_buttons.pop(button, None)

        if t0 is None:
            return

        pressed_time = time.monotonic() - t0

        if pressed_time < LONG_PRESSED_TIME:
            btn = self.buttons[button]
            if btn is not None:
                btn.on_pressed()
                self.logger.debug(f"Button {btn.index}/{btn.id} pressed")
                self.callbacks.button_pressed.call(button)
                self.events.button_pressed.set(data=button, flags={'button': btn.id})

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _hat_to_keys(value: tuple[int, int]) -> set[tuple[int, int]]:
        x, y = value
        keys: set[tuple[int, int]] = set()
        if x == -1:
            keys.add((-1, 0))
        elif x == 1:
            keys.add((1, 0))
        if y == -1:
            keys.add((0, -1))
        elif y == 1:
            keys.add((0, 1))
        return keys

    # ------------------------------------------------------------------------------------------------------------------
    def _on_hat_motion(self, value: tuple[int, int]):
        now = time.monotonic()

        with self._lock:
            prev = self._hat_value
            self._hat_value = value

        prev_keys = self._hat_to_keys(prev)
        new_keys = self._hat_to_keys(value)

        pressed = new_keys - prev_keys
        released = prev_keys - new_keys

        # Handle presses
        if pressed:
            with self._lock:
                for k in pressed:
                    self._pressed_hat_keys[k] = now
            for k in pressed:
                self.logger.debug(f"Hat key down: {k}")

        # Handle releases (possible short press)
        for k in released:
            with self._lock:
                t0 = self._pressed_hat_keys.pop(k, None)

            if t0 is None:
                continue

            dt = now - t0
            if dt < LONG_PRESSED_TIME:
                key = self.hat[k]
                key.on_pressed()
                self.logger.debug(f"Hat key {k} pressed")


# ======================================================================================================================
def main():
    jm = JoystickManager()
    jm.init()
    jm.start()

    while len(jm.joysticks) == 0:
        time.sleep(1)

    joystick = list(jm.joysticks.values())[0]

    joystick.buttons['A'].callbacks.pressed.register(lambda: print("A pressed!"))
    joystick.buttons['A'].callbacks.long_pressed.register(lambda: print("A long pressed!"))
    joystick.buttons['B'].callbacks.pressed.register(lambda: print("B pressed!"))
    joystick.hat['up'].callbacks.pressed.register(lambda: print("DPAD UP!"))
    joystick.hat['down'].callbacks.pressed.register(lambda: print("DPAD DOWN!"))

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
