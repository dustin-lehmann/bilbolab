import time

from core.communication.wifi.data_link import CommandArgument
# === OWN PACKAGES =====================================================================================================
from core.communication.wifi.wifi_interface import WIFI_Interface
from utils.callbacks import Callback, callback_handler, CallbackContainer


# ======================================================================================================================
@callback_handler
class BILBO_Wifi_Callbacks:
    connected: CallbackContainer
    disconnected: CallbackContainer


# ======================================================================================================================
class BILBO_WIFI_Interface:
    interface: WIFI_Interface

    connected: bool
    callbacks: BILBO_Wifi_Callbacks

    _time_sync_offset: float  # Offset to sync the device time with the server time

    def __init__(self, interface: WIFI_Interface):
        self.interface = interface

        self.connected = False

        self.interface.callbacks.connected.register(self._connectedCallback)
        self.interface.callbacks.disconnected.register(self._disconnectedCallback)
        self.interface.callbacks.sync.register(self._timeSyncCallback)

        self.callbacks = BILBO_Wifi_Callbacks()

        self._time_sync_offset = 0

    # ------------------------------------------------------------------------------------------------------------------
    def sendMessage(self, message):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def sendStream(self, data):
        if self.interface.connected:
            self.interface.sendStreamMessage(data)

    # ------------------------------------------------------------------------------------------------------------------
    def sendEvent(self, event, data=None):
        if self.interface.connected:
            self.interface.sendEventMessage(event, data)

    # ------------------------------------------------------------------------------------------------------------------
    def getTime(self):
        return time.time() + self._time_sync_offset

    # ------------------------------------------------------------------------------------------------------------------
    def addCommands(self, commands: dict):
        self.interface.addCommands(commands)

    # ------------------------------------------------------------------------------------------------------------------
    def addCommand(self, identifier: str, callback: (callable, Callback), arguments: list[(CommandArgument, str)], description: str, execute_in_thread: bool = False):
        self.interface.addCommand(identifier, callback, arguments, description, execute_in_thread)

    # ==================================================================================================================
    def _connectedCallback(self, *args, **kwargs):
        self.connected = True

        for callback in self.callbacks.connected:
            callback(*args, **kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def _disconnectedCallback(self, *args, **kwargs):
        self.connected = False

        for callback in self.callbacks.disconnected:
            callback(*args, **kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def _timeSyncCallback(self, data, *args, **kwargs):
        self._time_sync_offset = data['time'] - time.time()
