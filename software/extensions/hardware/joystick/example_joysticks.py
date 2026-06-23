import logging
import time

from extensions.hardware.joystick.joystick_manager import JoystickManager, Joystick

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d  %(levelname)-8s  %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')


def callback_new_joystick(joystick, *args, **kwargs):
    joystick.setButtonCallback(button=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16], event='down', function=callback_button,
                               parameters={'eventtype': 'down'})

    # joystick.setJoyHatCallback(['up', 'down', 'left', 'right'], joyhat_callback)


def callback_button(joystick: Joystick, button, eventtype, *args, **kwargs):
    print(f"Button {button}, Event: {eventtype}, Joystick: {joystick.guid}")
    joystick.rumble(strength=0.5, duration=0.75)


def joyhat_callback(joystick, direction):
    print(f"JoyHat: Joystick: {joystick.uuid}, Direction: {direction}")
    joystick.rumble(strength=1, duration=500)


def main():
    jm = JoystickManager()
    jm.start()

    jm.callbacks.new_joystick.register(callback_new_joystick)

    while True:
        for uuid, joystick in jm.joysticks.items():
            # print(f"Joystick {joystick.id}, Axis 0: {joystick.axis[0]}")
            axes_formatted = " ".join(f"Axis {i}: {axis: 5.2f}" for i, axis in enumerate(joystick.axes))
            print(f"Joystick {joystick.id}, {axes_formatted}")

        time.sleep(0.1)


if __name__ == '__main__':
    main()
