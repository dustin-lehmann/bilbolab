import json
import os
import utils.json_utils as json_utils
from utils.files import relativeToFullPath, fileExists, deleteFile
from paths import config_path
from utils.json_utils import readJSON, writeJSON


# ======================================================================================================================
def getBoardConfig():
    file = f"{config_path}/board.json"
    # First check if the files exist
    if not fileExists(file):
        return None

    return readJSON(file)


# ======================================================================================================================
def generate_board_config(rev):
    if rev == 'rev3':
        board_config = {
            'rev': 'rev3',
            'pins': {
                'status_led':
                    {
                        'type': 'sx1508',
                        'pin': 3
                    },
                'new_samples_interrupt': {
                    'type': 'internal',
                    'pin': 16
                },
                'uart_reset': {
                    'type': 'internal',
                    'pin': 5
                },
                'stm32_reset': {
                    'type': 'sx1508',
                    'pin': 5,
                },
                'stm32_boot0': {
                    'type': 'sx1508',
                    'pin': 0
                },
            },

            'communication': {
                'RC_PARAMS_BOARD_STM32_UART': '/dev/ttyAMA1',
                'RC_PARAMS_BOARD_STM32_UART_BAUD': 1000000,
            },
            'devices': {
                'IO_EXTENSION_I2C_ADDRESS': 0x01,
                'SHIELD_EEPROM_I2C_ADDRESS': 0x53,
            }

        }
    elif rev == 'rev4':
        board_config = {
            'rev': 'rev4',
            'pins': {
                'status_led':
                    {
                        'type': 'sx1508',
                        'pin': 2
                    },
                'new_samples_interrupt': {
                    'type': 'internal',
                    'pin': 6
                },
                'uart_reset': {
                    'type': 'internal',
                    'pin': 16
                },
                'stm32_reset': {
                    'type': 'sx1508',
                    'pin': 5,
                },
                'stm32_boot0': {
                    'type': 'sx1508',
                    'pin': 3
                },
            },

            'communication': {
                'RC_PARAMS_BOARD_STM32_UART': '/dev/ttyAMA1',
                'RC_PARAMS_BOARD_STM32_UART_BAUD': 1000000,
            },
            'devices': {
                'IO_EXTENSION_I2C_ADDRESS': 0x01,
                'SHIELD_EEPROM_I2C_ADDRESS': 0x53,
            }

        }
    elif rev == 'rev4.1':
        board_config = {
            'rev': 'rev4.1',
            'pins': {
                'status_led':
                    {
                        'type': 'sx1509',
                        'pin': 8
                    },
                'new_samples_interrupt': {
                    'type': 'internal',
                    'pin': 6
                },
                'uart_reset': {
                    'type': 'sx1509',
                    'pin': 10
                },
                'stm32_reset': {
                    'type': 'sx1509',
                    'pin': 11,
                },
                'stm32_boot0': {
                    'type': 'sx1509',
                    'pin': 14
                },
            },

            'communication': {
                'RC_PARAMS_BOARD_STM32_UART': '/dev/ttyAMA1',
                'RC_PARAMS_BOARD_STM32_UART_BAUD': 1000000,
            },
            'devices': {
                'GPIO_EXTENDER_I2C_ADDRESS': 0x3E,
                'IO_EXTENSION_I2C_ADDRESS': 0x01,
                'SHIELD_EEPROM_I2C_ADDRESS': 0x53,
            }

        }
    else:
        return

    file = f"{config_path}board.json"

    if fileExists(file):
        deleteFile(file)

    writeJSON(file, board_config)


if __name__ == '__main__':
    generate_board_config('rev4')
