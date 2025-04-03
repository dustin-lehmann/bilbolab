import enum

# ======================================================================================================================
from core.hardware.sx1508 import SX1508, SX1508_GPIO_MODE
from core.hardware.sx1509 import SX1509, SX1509_GPIO_MODE
from utils.callbacks import Callback
import core.hardware.rpi_gpio as gpio


# ======================================================================================================================
class PullupPulldown(enum.IntEnum):
    DOWN = 21
    OFF = 20
    UP = 22


# ======================================================================================================================
class GPIO_Output:
    pin_type: str
    pin: int
    write_direction: str

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, pin: int, pin_type: str = 'internal', write_direction: str = 'normal', value: int = 0,
                 pull_up_down: PullupPulldown = PullupPulldown.OFF):
        assert pin_type in ('internal', 'sx1508', 'sx1509')
        assert (write_direction in ('normal', 'inverted'))

        self.pin_type = pin_type
        self.pin = pin
        self.write_direction = write_direction

        if pin_type == 'internal':
            gpio.setup(self.pin, gpio.GPIO.OUT, pull_up_down)
        elif pin_type == 'sx1508':
            self.sx1508 = SX1508()
            self.sx1508.configureGPIO(self.pin, mode=SX1508_GPIO_MODE.OUTPUT)
        elif pin_type == 'sx1509':
            self.sx1509 = SX1509()
            self.sx1509.configureGPIO(self.pin, mode=SX1509_GPIO_MODE.OUTPUT)

        self.write(value)

    # ------------------------------------------------------------------------------------------------------------------
    def write(self, value):

        if self.write_direction == 'inverted':
            value = ~value

        if self.pin_type == 'internal':
            gpio.write(self.pin, value)
        elif self.pin_type == 'sx1508':
            self.sx1508.writeGPIO(self.pin, value)
        elif self.pin_type == 'sx1509':
            self.sx1509.writeGPIO(self.pin, value)

    # ------------------------------------------------------------------------------------------------------------------
    def on(self):
        self.write(1)

    # ------------------------------------------------------------------------------------------------------------------
    def off(self):
        self.write(0)

    # ------------------------------------------------------------------------------------------------------------------
    def toggle(self):
        if self.pin_type == 'internal':
            gpio.toggle(self.pin)
        elif self.pin_type == 'sx1508':
            self.sx1508.toggleGPIO(self.pin)
        elif self.pin_type == 'sx1509':
            self.sx1509.toggleGPIO(self.pin)


# ======================================================================================================================
class InterruptFlank(enum.IntEnum):
    RISING = 31
    FALLING = 32
    BOTH = 33
    NONE = 0


# ======================================================================================================================
class GPIO_Input:
    pin: int
    pin_type: str
    interrupt_flank: InterruptFlank
    callback: Callback
    pup: PullupPulldown
    bouncetime: int

    def __init__(self, pin: int, pin_type: str = 'internal',
                 interrupt_flank: InterruptFlank = InterruptFlank.NONE,
                 pull_up_down: PullupPulldown = PullupPulldown.OFF,
                 callback: (callable, Callback) = None,
                 bouncetime: int = 10):

        assert pin_type in ('internal', 'sx1508')
        self.pin_type = pin_type
        self.pin = pin
        self.interrupt_flank = interrupt_flank
        self.callback = callback
        self.pup = pull_up_down
        self.bouncetime = bouncetime

        if pin_type == 'internal':

            gpio.setup(self.pin, gpio.GPIO.IN, self.pup)

            if self.interrupt_flank != InterruptFlank.NONE:
                gpio.add_event_detect(pin=self.pin,
                                      flanks=self.interrupt_flank.value,
                                      callback=self.callback,
                                      bouncetime=self.bouncetime)

        elif pin_type == 'sx1508':
            raise NotImplementedError('SX1508 Input is not implemented yet')

        elif pin_type == 'sx1509':
            raise NotImplementedError('SX1509 Input is not implemented yet')

    # ------------------------------------------------------------------------------------------------------------------
    def addInterrupt(self, interrupt_flank: InterruptFlank, callback: (callable, Callback), bouncetime: int = 10):
        gpio.add_event_detect(pin=self.pin,
                              flanks=interrupt_flank.value,
                              callback=callback,
                              bouncetime=bouncetime)

    # ------------------------------------------------------------------------------------------------------------------
    def read(self):
        return gpio.read(self.pin)
