import time
from typing import Union

# === OWN PACKAGES =====================================================================================================
from hardware.hardware.gpio import GPIO_Output
from core.communication.i2c.i2c import I2C_Interface
from core.communication.spi.spi import SPI_Interface
# from core.hardware.sx1508 import SX1508, SX1508_GPIO_MODE
from core.communication.serial.serial_interface import Serial_Interface
from hardware.board_config import getBoardConfig
from hardware.io_extension.io_extension import RobotControl_IO_Extension
from core.utils.logging_utils import Logger
from hardware.lowlevel_definitions import bilbo_external_rgb_struct, BILBO_AddressTables, BILBO_GeneralAddresses, \
    bilbo_beep_struct, bilbo_all_external_leds_struct
from core.utils.exit import register_exit_callback
import core.hardware.eeprom as eeprom
from hardware.shields.shields import SHIELDS, SHIELD_ID_ADDRESS


# === GLOBAL VARIABLES =================================================================================================


# === RobotControl_Board ===============================================================================================
class RobotControl_Board:
    spi_interface: SPI_Interface
    serial_interface: Serial_Interface
    i2c_interface: I2C_Interface

    status_led: GPIO_Output
    uart_reset_pin: GPIO_Output

    io_extension: RobotControl_IO_Extension

    shield = None

    # === INIT =========================================================================================================
    def __init__(self):

        self.logger = Logger("BOARD")
        self.board_config = getBoardConfig()

        self.spi_interface = SPI_Interface(notification_pin=None, baudrate=10000000)

        self.serial_interface = Serial_Interface(port=self.board_config.definitions.communication.serial.device,
                                                 baudrate=self.board_config.definitions.communication.serial.baud
                                                 )

        self.i2c_interface = I2C_Interface()

        self.io_extension = RobotControl_IO_Extension(interface=self.i2c_interface)

        self.status_led = GPIO_Output(pin_type=self.board_config.definitions.pins.status_led.type,
                                      pin=self.board_config.definitions.pins.status_led.pin,
                                      )

        self.setStatusLed(0)

        self.uart_reset_pin = GPIO_Output(
            pin_type=self.board_config.definitions.pins.uart_reset.type,
            pin=self.board_config.definitions.pins.uart_reset.pin,
            value=0,
        )

        register_exit_callback(self.handle_exit)

    # === METHODS ======================================================================================================
    def init(self):
        self.logger.debug("Reset UART")
        self.resetUart()
        self.shield = self.checkForShield()

    # ------------------------------------------------------------------------------------------------------------------
    def checkForShield(self):
        try:
            shield_id = eeprom.read_bytes(eeprom_address=self.board_config.definitions.devices.shield_eeprom,
                                          byte_address=SHIELD_ID_ADDRESS,
                                          num_bytes=1)
        except Exception as e:
            self.logger.error(f"Error reading shield id: {e}")
            return

        # Check if the shield id is in the list of known shields
        if shield_id in SHIELDS:
            self.logger.info(f"Found shield: {SHIELDS[shield_id]['name']}")
            shield = SHIELDS[shield_id]['class']()
            return shield
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.serial_interface.start()

    # ------------------------------------------------------------------------------------------------------------------
    def resetUart(self):
        self.uart_reset_pin.write(1)
        time.sleep(0.001)
        self.uart_reset_pin.write(0)

    # ------------------------------------------------------------------------------------------------------------------
    def setStatusLed(self, state, *args, **kwargs):
        self.status_led.write(state)

    # ------------------------------------------------------------------------------------------------------------------
    def setRGBLEDIntern(self, position, color):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def setRGBLEDExtern(self, color):
        color_struct = bilbo_external_rgb_struct(red=color[0], green=color[1], blue=color[2])
        self.serial_interface.function(address=BILBO_GeneralAddresses.ADDRESS_FIRMWARE_EXTERNAL_LED,
                                       module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
                                       input_type=bilbo_external_rgb_struct,
                                       data=color_struct)

        time.sleep(0.01)
        self.serial_interface.function(address=BILBO_GeneralAddresses.ADDRESS_FIRMWARE_EXTERNAL_LED,
                                       module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
                                       input_type=bilbo_external_rgb_struct,
                                       data=color_struct)

    # ------------------------------------------------------------------------------------------------------------------
    def setAllLEDsExtern(self, colors):
        """
        Set colors for all 16 external LEDs in one shot.

        Args:
            colors: iterable of RGB triplets (r,g,b) with 0..255 values.
                    If fewer than 16 provided, the rest are set to (0,0,0).
                    If more than 16 provided, extras are ignored.
        """
        # Build the fixed-size array of 16 bilbo_external_rgb_struct
        arr = (bilbo_external_rgb_struct * 16)()

        def _clamp(x):
            try:
                x = int(x)
            except Exception:
                x = 0
            return 0 if x < 0 else 255 if x > 255 else x

        # Fill array
        for i in range(16):
            if i < len(colors):
                r, g, b = colors[i]
            else:
                r = g = b = 0
            arr[i] = bilbo_external_rgb_struct(
                red=_clamp(r),
                green=_clamp(g),
                blue=_clamp(b),
            )

        # Wrap into the top-level struct
        payload = bilbo_all_external_leds_struct(colors=arr)

        # Send via your serial interface. Use the address constant that
        # you registered for this function (REG_ADDRESS_F_ALL_EXTERNAL_LEDS).
        self.serial_interface.function(
            address=BILBO_GeneralAddresses.ADDRESS_FIRMWARE_ALL_EXTERNAL_LED,
            module=BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            input_type=bilbo_all_external_leds_struct,
            data=payload,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def beep(self, frequency: Union[str, float, None] = None, time_ms: int = 500, repeats: int = 1):
        if frequency is None:
            frequency = 500

        if isinstance(frequency, str):
            if frequency == 'low':
                frequency = 200
            elif frequency == 'medium':
                frequency = 600
            elif frequency == 'high':
                frequency = 900
            else:
                frequency = 500

        beep_data = {
            'frequency': frequency,
            'time': time_ms,
            'repeats': repeats
        }

        self.serial_interface.function(
            address=BILBO_GeneralAddresses.ADDRESS_FIRMWARE_BEEP,
            module=0x01,
            data=beep_data,
            input_type=bilbo_beep_struct
        )

    # ------------------------------------------------------------------------------------------------------------------
    def handle_exit(self, *args, **kwargs):
        time.sleep(0.25)
        self.setStatusLed(0)
        self.setRGBLEDExtern([2, 2, 2])
        self.logger.info("Exit Board")
