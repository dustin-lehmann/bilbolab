import time

from robot.applications.standalone.joystick_control import StandaloneJoystickControl
from robot.bilbo import BILBO

from utils.teleplot import sendValue


def main():
    twipr = BILBO(reset_stm32=False)
    joystick_control = StandaloneJoystickControl(bilbo=twipr)
    twipr.init()
    joystick_control.init()
    twipr.start()
    joystick_control.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        exit(0)

if __name__ == '__main__':
    main()
