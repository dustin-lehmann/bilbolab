import board
from RPi import GPIO


# ======================================================================================================================
class SPI_Interface:
    notification_pin: int
    spi: board.SPI

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, notification_pin: int = None, baudrate: int = 40_000_000):
        self.notification_pin = notification_pin

        self.spi = board.SPI()
        while not self.spi.try_lock():
            pass
        self.spi.configure(baudrate=baudrate)

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, data: bytearray):
        # print(f'SPI: Sending {len(data)} bytes: {data}')
        if isinstance(data, list):
            data = bytearray(data)

        if self.notification_pin is not None:
            GPIO.output(self.notification_pin, 0)
            GPIO.output(self.notification_pin, 1)

        self.spi.write(data, start=0, end=len(data))

    # ------------------------------------------------------------------------------------------------------------------
    def readinto(self, buf, start, end, write_value=2):
        return self.spi.readinto(buf, start, end, write_value)
