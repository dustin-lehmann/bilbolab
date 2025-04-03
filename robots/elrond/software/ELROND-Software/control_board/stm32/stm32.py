import time
from RPi import GPIO

from control_board.board_config import getBoardConfig
from core.hardware.sx1508 import SX1508, SX1508_GPIO_MODE


def resetSTM32():
    board_config = getBoardConfig()

    if board_config['rev'] == 'rev3':
        GPIO.setwarnings(False)
        GPIO.cleanup()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(board_config['pins']['RC_CM4_STM32_RESET'], GPIO.OUT)

        time.sleep(0.25)
        GPIO.output(board_config['pins']['RC_CM4_STM32_RESET'], 1)
        time.sleep(1)
        GPIO.output(board_config['pins']['RC_CM4_STM32_RESET'], 0)
        time.sleep(0.25)
        GPIO.cleanup()

    elif board_config['rev'] == 'rev4':
        sx = SX1508(reset=False)
        sx.configureGPIO(gpio=board_config['pins']['stm32_reset']['pin'], mode=SX1508_GPIO_MODE.OUTPUT, pullup=False, pulldown=True)
        sx.writeGPIO(board_config['pins']['stm32_reset']['pin'], 1)
        time.sleep(1)
        sx.writeGPIO(board_config['pins']['stm32_reset']['pin'], 0)
        time.sleep(1)


if __name__ == '__main__':
    resetSTM32()