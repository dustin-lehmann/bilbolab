from core.utils.exit import register_exit_callback
from core.hardware.network import get_wifi_ssid, check_internet, getSignalStrength
from robot.bilbo_common import BILBO_Common
from robot.logging.bilbo_sample import BILBO_Sample
from robot.utilities.display.display import Display
from robot.utilities.display.pages import StatusPage


# === BILBO DISPLAY ====================================================================================================
class BILBO_Display:
    display: Display

    core: BILBO_Common

    _display_started: bool = False


    # === INIT =========================================================================================================
    def __init__(self, core: BILBO_Common):
        self.core = core
        self.display = Display()

        self.status_page = StatusPage()
        self.display.add_page(self.status_page)

        self.core.events.sample.on(
            callback=self._updateDisplay,
            max_rate=0.2
        )

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        # Start the display immediately with the Status page
        self.display.change_page('Status', start_thread=False)
        self.display.start()
        self._display_started = True

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.display.stop()

    # === PRIVATE METHODS ==============================================================================================

    # ------------------------------------------------------------------------------------------------------------------
    def _updateDisplay(self, sample: BILBO_Sample, *args, **kwargs):
        battery_voltage = sample.sensors.power.bat_voltage

        if battery_voltage > 15.5:
            level = 'full'
        elif battery_voltage > 13.5:
            level = 'half'
        else:
            level = 'empty'
        self.status_page.set_battery(level, battery_voltage)

        config = self.core.config

        self.status_page.set_ip_address(config.network.address)
        self.status_page.set_user_and_hostname(config.network.username, config.general.id)
        self.status_page.set_ssid(get_wifi_ssid())

        self.status_page.set_internet_status(check_internet(timeout=1))

        data = getSignalStrength('wlan0')
        signal_strength = data.get('percent', 0)

        if signal_strength > 85:
            self.status_page.set_signal_strength('high')
        elif signal_strength > 30:
            self.status_page.set_signal_strength('medium')
        elif signal_strength > 1:
            self.status_page.set_signal_strength('low')
        else:
            self.status_page.set_signal_strength('none')

        # Joystick check
        joystick_connected = self.core.joystick_connected
        self.status_page.set_joystick_status(joystick_connected)

        # Server connection check
        server_connected = self.core.server_connected

        self.status_page.set_server_connection(server_connected)

    # ------------------------------------------------------------------------------------------------------------------
