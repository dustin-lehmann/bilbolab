import enum
import time

import board
from utils import bytes_utils as bt

RegInputDisable_B = 0x00
RegInputDisable_A = 0x01

RegPullUp_B = 0x06
RegPullUp_A = 0x07

RegPullDown_B = 0x08
RegPullDown_A = 0x09

RegDir_B = 0x0E
RegDir_A = 0x0F

RegData_B = 0x10
RegData_A = 0x11

RegReset = 0x7D

BANK_A = [0, 1, 2, 3, 4, 5, 6, 7]
BANK_B = [8, 9, 10, 11, 12, 13, 14, 15]

SX1509_I2C_ADDRESS = 0x3E

output_data_A = 0
output_data_B = 0


class SX1509_GPIO_MODE(enum.Enum):
    INPUT = 0
    OUTPUT = 1


# ======================================================================================================================
class SX1509:
    address: int
    _i2c: board.I2C

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, address: int = SX1509_I2C_ADDRESS, reset=False):
        self.address = address
        self._i2c = board.I2C()
        if reset:
            self.reset()

    # ------------------------------------------------------------------------------------------------------------------
    def configureGPIO(self, gpio: int, mode, pullup: bool = False, pulldown: bool = False):
        # set the Mode
        self._setGPIOMode(gpio, mode)

        # Set the pullup and pulldown registers
        self._setPullup(gpio, pullup)
        self._setPulldown(gpio, pulldown)

    # ------------------------------------------------------------------------------------------------------------------
    def deinitGPIO(self, gpio):
        self.configureGPIO(gpio, mode=SX1509_GPIO_MODE.INPUT)

    # ------------------------------------------------------------------------------------------------------------------
    def writeGPIO(self, gpio, state):
        if gpio in BANK_A:
            global output_data_A
            output_data_A = bt.changeBit(output_data_A, gpio, state)
            self._writeReg(RegData_A, output_data_A)
        elif gpio in BANK_B:
            global output_data_B
            output_data_B = bt.changeBit(output_data_B, gpio-8, state)
            self._writeReg(RegData_B, output_data_B)

    # ------------------------------------------------------------------------------------------------------------------
    def toggleGPIO(self, gpio):
        if gpio in BANK_A:
            global output_data_A
            output_data_A = bt.toggleBit(output_data_A, gpio)
            self._writeReg(RegData_A, output_data_A)
        elif gpio in BANK_B:
            global output_data_B
            output_data_B = bt.toggleBit(output_data_B, gpio-8)
            self._writeReg(RegData_B, output_data_B)

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        self._writeReg(RegReset, 0x12)
        self._writeReg(RegReset, 0x34)

    # ------------------------------------------------------------------------------------------------------------------
    def _setGPIOMode(self, gpio, mode: SX1509_GPIO_MODE):
        """
        Set the register RegInputDisable. A '0' indicates an INPUT, a '1' indicates an OUTPUT
        """
        # print("Set GPIO Mode")
        if isinstance(mode, SX1509_GPIO_MODE):
            mode = mode.value

        # Read the register RegInputDisable
        # data = self._readReg(RegInputDisable)
        # # Manipulate the content
        # data = bt.changeBit(data, gpio, mode)
        # self._writeReg(RegInputDisable, data)

        if gpio in BANK_A:
            direction_reg = RegDir_A
            gpio_pos = gpio
        elif gpio in BANK_B:
            direction_reg = RegDir_B
            gpio_pos = gpio-8
        else:
            return

        direction_data = self._readReg(direction_reg)
        direction_data = bt.changeBit(direction_data, gpio_pos, not mode)  # here 0 is an output and 1 is an input
        self._writeReg(direction_reg, direction_data)

    # ------------------------------------------------------------------------------------------------------------------
    def _setPullup(self, gpio, mode: bool):
        """
        Set the pullup for the GPIO pin. '0' disables the pullup, '1' enables the pullup
        """
        if gpio in BANK_A:
            pullup_reg = RegPullUp_A
        elif gpio in BANK_B:
            pullup_reg = RegPullUp_B
        else:
            return

        pullup_data = self._readReg(pullup_reg)
        pullup_data = bt.changeBit(pullup_data, gpio, mode)
        self._writeReg(pullup_reg, pullup_data)

    # ------------------------------------------------------------------------------------------------------------------
    def _setPulldown(self, gpio, mode: bool):
        """
        Set the pullup for the GPIO pin. '0' disables the pullup, '1' enables the pullup
        """
        if gpio in BANK_A:
            pulldown_reg = RegPullDown_A
        elif gpio in BANK_B:
            pulldown_reg = RegPullDown_B
        else:
            return

        pulldown_data = self._readReg(pulldown_reg)
        pulldown_data = bt.changeBit(pulldown_data, gpio, mode)
        self._writeReg(pulldown_reg, pulldown_data)

    # ------------------------------------------------------------------------------------------------------------------
    def _writeReg(self, reg, data):
        """
        """

        if not isinstance(reg, bytes):
            reg = bt.bytes_(reg)

        if not isinstance(data, bytes):
            data = bt.bytes_(data)

        self._i2c.writeto(address=self.address, buffer=reg + data)

    # ------------------------------------------------------------------------------------------------------------------
    def _readReg(self, reg):
        """
        """

        if not isinstance(reg, bytes):
            reg = bt.bytes_(reg)
        data = [0]
        self._i2c.writeto_then_readfrom(address=self.address, buffer_out=reg, buffer_in=data)

        return data[0]


def test_sx1509():
    sx1509 = SX1509()
    sx1509.reset()

    sx1509.configureGPIO(9, SX1509_GPIO_MODE.OUTPUT)

    for i in range(10):
        sx1509.writeGPIO(9, 1)
        time.sleep(0.25)
        sx1509.writeGPIO(9, 0)
        time.sleep(0.25)


if __name__ == '__main__':
    test_sx1509()
