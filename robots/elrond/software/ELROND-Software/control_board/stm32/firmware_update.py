import os
import subprocess
import sys

import RPi.GPIO as GPIO
import serial
import time
import board
import busio

from stm32loader import main as stm32loader_main
import sys

import shutil

from control_board.board_config import getBoardConfig
from control_board.control_board_settings import RC_PARAMS_BOARD_STM32_UART
from control_board.stm32.stm32 import resetSTM32
from core.hardware.sx1508 import SX1508, SX1508_GPIO_MODE


class STM32_FirmwareUpdater:
    sx: SX1508
    board_config: dict

    def __init__(self):
        self.sx = SX1508(reset=True)
        self.board_config = getBoardConfig()
        self.device = RC_PARAMS_BOARD_STM32_UART

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        self.sx.configureGPIO(self.board_config['pins']['RC_SX1508_STM32_BOOT0'],SX1508_GPIO_MODE.OUTPUT, pullup=True)

    # ------------------------------------------------------------------------------------------------------------------
    def setBoot0(self, state):
        if state:
            self.sx.writeGPIO(self.board_config['pins']['RC_SX1508_STM32_BOOT0'], 1)
        else:
            self.sx.writeGPIO(self.board_config['pins']['RC_SX1508_STM32_BOOT0'], 0)

    # ------------------------------------------------------------------------------------------------------------------
    def checkBootloader(self) -> bool:
        check = False
        uart = serial.Serial(self.device, baudrate=57600, timeout=1)

        try:
            uart.open()
        except serial.SerialException:
            try:  # Restart the device
                uart.close()
                uart.open()
            except serial.SerialException:
                raise Exception("Cannot open the serial device")

        for i in range(0, 2):
            uart.write(b'\x7F')
            answer = uart.read(1)
            if answer == b'\x1F' or answer == b'\x79':
                check = True
                break
        uart.close()
        return check

    # ------------------------------------------------------------------------------------------------------------------
    def enterBootloader(self):
        print("Enter Bootloader")
        self.setBoot0(True)
        time.sleep(0.25)
        resetSTM32()

    # ------------------------------------------------------------------------------------------------------------------
    def exitBootloader(self):
        print("Exit Bootloader")
        self.setBoot0(False)
        time.sleep(0.25)
        resetSTM32()

    # ------------------------------------------------------------------------------------------------------------------
    def uploadFirmware(self, file):

        firmwares_folder = os.path.join(os.path.dirname(__file__), 'firmwares')

        # Construct the full path to the firmware file
        firmware_path = os.path.join(firmwares_folder, file)

        # Check if the file exists
        if not os.path.isfile(firmware_path):
            print(f"Firmware '{file}' not found in '{firmwares_folder}'.")
            return

        print("-------------------------------------------------------------")
        print("Uploading firmware")
        self.enterBootloader()
        time.sleep(0.25)
        check = self.checkBootloader()

        if not check:
            print("Cannot enter bootloader")
            self.close()
            return
        else:
            print("Bootloader entered")
        print("-------------------------------------------------------------")
        print(f"Flash Firmware {file}")

        self.flash_firmware(firmware_path)

        self.exitBootloader()
    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.exitBootloader()

    def flash_firmware(self, firmware_path):
        # Define the path to stm32flash executable
        stm32flash_path = "./stm32flash/stm32flash"

        # Check if the stm32flash executable exists
        if not os.path.exists(stm32flash_path):
            print(f"{stm32flash_path} not found. Attempting to build it using 'make' command...")
            success = compileSTM32Flash()
            if not success:
                return

        # Define the command and arguments
        command = [stm32flash_path, "-w", firmware_path, "-b", "57600", self.device]

        try:
            # Execute the command
            result = subprocess.run(command, check=True)

        except subprocess.CalledProcessError as e:
            # Print the error if command fails
            print(f"Error uploading firmware")


def compileSTM32Flash() -> bool:
    try:
        # Run the make command in the stm32flash subdirectory
        make_result = subprocess.run(["make"], cwd="./stm32flash", check=True)
        print("Build successful.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error during 'make': {e}")
        return False # Exit the function if build fails

def firmware_update(file):
    updater = STM32_FirmwareUpdater()
    updater.init()
    updater.uploadFirmware(file)

if __name__ == '__main__':
    firmware_update()