from core.communication.device_server import DeviceServer, Device
from core.communication.protocol import JSON_Message
from core.utils.events import pred_flag_equals
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import from_dict, from_dict_auto
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.network.network import getHostIP
from extensions.tools.cli.cli import CommandSet
from robots.frodo.frodo import FRODO
from robots.frodo.frodo_definitions import FRODO_Config


@callback_definition
class FRODO_Manager_Callbacks:
    new_robot: CallbackContainer
    robot_disconnected: CallbackContainer


@event_definition
class FRODO_Manager_Events:
    new_robot: Event = Event(copy_data_on_set=False)
    robot_disconnected: Event = Event(copy_data_on_set=False)


# === FRODO MANAGER ====================================================================================================
class FRODO_Manager:
    device_server: DeviceServer

    robots: dict[str, FRODO]
    # frodo_scanner: FRODO_NetworkScanner | None

    _devices: dict[str, Device]

    cli: CommandSet

    # === INIT =========================================================================================================
    def __init__(self, host: str | None = None, enable_scanner: bool = False):
        if host is None:
            host = getHostIP()

        self.callbacks = FRODO_Manager_Callbacks()
        self.events = FRODO_Manager_Events()
        self.host = host

        self._devices = {}

        self.robots = {}

        self.device_server = DeviceServer(host)

        self.device_server.events.new_device.on(callback=self._newDevice_event,
                                                predicate=pred_flag_equals('type', 'frodo'))

        self.device_server.events.device_disconnected.on(callback=self._deviceDisconnected_event,
                                                         predicate=pred_flag_equals('type', 'frodo'))

        # CLI
        self.cli = FRODO_Manager_CommandSet(self)

        self.logger = Logger("FRODO Manager", "DEBUG")

        # Exit Handler
        register_exit_callback(self.close, priority=10)

    # === METHODS ======================================================================================================
    def init(self):
        self.device_server.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info("Starting FRODO Manager")
        self.device_server.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.logger.info("Closing FRODO Manager")

    # ------------------------------------------------------------------------------------------------------------------
    def emergencyStop(self):
        self.logger.warning("Emergency stop. Need to implement this!")

    # ------------------------------------------------------------------------------------------------------------------
    def getRobotById(self, robot_id):
        if robot_id in self.robots:
            return self.robots[robot_id]
        else:
            return None

    # === PRIVATE METHODS ==============================================================================================
    def _newDevice_event(self, device: Device):
        if device.information.device_id in self._devices:
            self.logger.warning(f"Device with id {device.information.device_id} already exists")
            return

        self._devices[device.information.device_id] = device
        self.logger.info(f"New frodo device connected: {device.information.device_id}")
        device.callbacks.event.register(self._deviceEvent_callback, inputs={'device': device})

    # ------------------------------------------------------------------------------------------------------------------
    def _deviceDisconnected_event(self, device: Device):
        # Go through all robots and check if this device is one of them
        for robot in self.robots.values():
            if robot.device == device:
                self._removeBilbo(robot)
                break

    # ------------------------------------------------------------------------------------------------------------------
    def _deviceEvent_callback(self, event_message: JSON_Message, device: Device):
        # Check if the event is a BILBO handshake. Only then do we accept it as a BILBO
        if event_message.event == 'frodo_handshake':
            try:
                frodo_config = from_dict_auto(FRODO_Config, event_message.data)
            except Exception as e:
                self.logger.error(f"Error in frodo handshake: {e}. Message: {event_message}")
                return

            # Check if this device is already registered
            if frodo_config.id in self.robots:
                self.logger.warning(f"Device with ID {frodo_config.id} already registered")
                return

            self._addNewFrodo(device, frodo_config)

    # ------------------------------------------------------------------------------------------------------------------
    def _addNewFrodo(self, device: Device, config: FRODO_Config):

        # Remove the callback for the event
        device.callbacks.event.remove(self._deviceEvent_callback)

        # Create a new BILBO robot
        new_robot = FRODO(device, config)
        self.robots[config.id] = new_robot

        # Add the robot's CLI command set
        self.cli.addChild(new_robot.interfaces.cli_command_set)

        self.logger.info(f"New FRODO \"{config.id}\" connected")

        # Call the callbacks and events for a new robot
        self.callbacks.new_robot.call(new_robot)
        self.events.new_robot.set(data=new_robot)

    # ------------------------------------------------------------------------------------------------------------------
    def _removeBilbo(self, robot: FRODO):
        self.robots.pop(robot.id)
        self._devices.pop(robot.device.information.device_id)

        # Remove the robot's CLI command set
        self.cli.removeChild(robot.interfaces.cli_command_set)

        self.callbacks.robot_disconnected.call(robot)
        self.events.robot_disconnected.set(data=robot)

        self.logger.info(f"FRODO \"{robot.id}\" disconnected")


# ======================================================================================================================
class FRODO_Manager_CommandSet(CommandSet):
    name = 'robots'
    description = 'Functions related to connected FRODO'

    # === INIT =========================================================================================================
    def __init__(self, frodo_manager: FRODO_Manager):
        self.manager = frodo_manager

        super().__init__(self.name, commands=[], children=[], description=self.description)
