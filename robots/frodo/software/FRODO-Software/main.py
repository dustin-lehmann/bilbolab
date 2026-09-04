import time

from archive.robot_control.utils import elapsedTimer
from core.utils.colors import color_to_255
from robot.frodo import FRODO
from robot.frodo_core.lowlevel_definitions import FRODO_LL_SAMPLE


def printData(sample: FRODO_LL_SAMPLE):
    # print(f"Speed: {sample.drive.speed.left}, {sample.drive.speed.right}")
    print(f"Speed: {sample.drive.rpm.left}, {sample.drive.rpm.right}")


def main():
    frodo = FRODO()
    frodo.init()
    frodo.start()

    # frodo.control.setTrackSpeed(0.0, 0.0)
    # frodo.core.lowlevel.events.sample.on(printData)

    frodo.core.lowlevel.board.setRGBLEDExtern(color_to_255([0, 1, 0]))


    x = ElapsedTimer()


    # time.sleep(1)
    # frodo.control.setSpeed(0.2, 0.2)
    # time.sleep(2)
    # frodo.control.setSpeed(0, 0)

    # frodo.core.lowlevel.board.setRGBLEDExtern([int(color[0] * 255), int(color[1] * 255), int(color[2] * 255)])
    # time.sleep(5)
    # return
    while True:
        time.sleep(1)



if __name__ == '__main__':
    main()
