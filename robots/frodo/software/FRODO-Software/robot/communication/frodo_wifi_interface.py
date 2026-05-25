import time
from typing import Callable, Union

from core.communication.wifi.bilbolab_wifi_interface import BILBOLab_Wifi_Interface
from core.communication.wifi.data_link import Command, CommandArgument
from core.communication.wifi.wifi import DeviceInformation
from core.utils import network
from core.utils.callbacks import CallbackContainer, callback_definition, Callback
from core.utils.delayed_executor import delayed_execution
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.websockets import WebsocketServer
from robot.common import FRODO_Common


# === FRODO WIFI INTERFACE =============================================================================================
@callback_definition
class FRODO_Wifi_Callbacks:
    connected: CallbackContainer
    disconnected: CallbackContainer


@event_definition
class FRODO_Wifi_Events:
    connected: Event
    disconnected: Event


class FRODO_WIFI_Interface:
    wifi: BILBOLab_Wifi_Interface

    stream_server: WebsocketServer

    callbacks: FRODO_Wifi_Callbacks
    events: FRODO_Wifi_Events

    # === INIT =========================================================================================================
    def __init__(self, common: FRODO_Common):

        self.common = common
        self.logger = Logger("WIFI INTERFACE", "DEBUG")

        self.address = network.getLocalIP_RPi()

        self.common.information.network.address = self.address

        self.callbacks = FRODO_Wifi_Callbacks()
        self.events = FRODO_Wifi_Events()

        device_information = self._gatherDeviceInformation()

        self.wifi = BILBOLab_Wifi_Interface(device_information, address=self.address)
        self.wifi.events.connected.on(self._connected_event)
        self.wifi.events.disconnected.on(self._disconnected_event)

        register_exit_callback(self.close)

    # === PROPERTIES ===================================================================================================
    @property
    def connected(self):
        return self.wifi.connected

    # === METHODS ======================================================================================================
    def init(self):
        self.wifi.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.wifi.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.logger.info("Closing FRODO WIFI Interface")

    # ------------------------------------------------------------------------------------------------------------------
    def sendStream(self, data, stream_id: str = 'sample'):
        if self.connected:
            self.wifi.sendStream(data, stream_id)

    # ------------------------------------------------------------------------------------------------------------------
    def sendEvent(self, event, data=None):
        if self.connected:
            self.wifi.sendEvent(event, data)

    # ------------------------------------------------------------------------------------------------------------------
    def getTime(self):
        synchronized_time = self.wifi.getSynchronizedTime()
        if synchronized_time is None:
            return time.time()
        else:
            return synchronized_time

    # ------------------------------------------------------------------------------------------------------------------
    def addCommand(self, command) -> Command:
        self.wifi.addCommand(command)
        return command

    # ------------------------------------------------------------------------------------------------------------------
    def newCommand(self, identifier: str,
                   function: Union[Callable, Callback],
                   arguments: list[Union[CommandArgument, str]],
                   description: str = "",
                   execute_in_thread: bool = True) -> Command:

        return self.wifi.newCommand(identifier, function, arguments, description, execute_in_thread)

    # === PRIVATE METHODS ==============================================================================================
    def _gatherDeviceInformation(self) -> DeviceInformation:
        information = DeviceInformation()
        information.device_id = self.common.id
        information.device_type = 'frodo'
        information.device_class = 'frodo'
        information.device_name = 'frodo'
        information.device_version = '0.0.0'
        return information

    # ------------------------------------------------------------------------------------------------------------------
    def _connected_event(self, *args, **kwargs):
        delayed_execution(func=self._sendFRODOHandshakeMessage, delay=1.0)

        self.common.server_connected = True
        self.callbacks.connected.call()
        self.events.connected.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _sendFRODOHandshakeMessage(self):
        information = self.common.information
        self.sendEvent('frodo_handshake', information)

    # ------------------------------------------------------------------------------------------------------------------
    def _disconnected_event(self, *args, **kwargs):
        self.common.server_connected = False
        self.callbacks.disconnected.call()
        self.events.disconnected.set()
    # ------------------------------------------------------------------------------------------------------------------
