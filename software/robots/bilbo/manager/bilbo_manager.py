from core.communication.device_server import DeviceServer, Device
from core.communication.protocol import JSON_Message
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import from_dict, from_dict_auto
from core.utils.events import event_definition, Event, pred_flag_equals
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.network.network import getHostIP
from core.utils.network.ssh import isScriptRunningViaSSH, executePythonViaSSH, stopPythonViaSSH
from extensions.tools.cli.cli import CommandSet
from robots.bilbo.manager.bilbo_manager_cli import BILBO_Manager_CommandSet
from robots.bilbo.manager.bilbo_scanner import BILBO_NetworkScanner
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_definitions import (BILBO_Config, BILBO_HOST_NAMES, BILBO_USER_NAME,
                                                  BILBO_PASSWORD, PATH_TO_MAIN, PYENV_SHIM_PATH)


# === BILBO MANAGER ====================================================================================================
@callback_definition
class BILBO_Manager_Callbacks:
    new_robot: CallbackContainer
    robot_disconnected: CallbackContainer
    stream: CallbackContainer


@event_definition
class BILBO_Manager_Events:
    new_robot: Event = Event(copy_data_on_set=False)
    robot_disconnected: Event = Event(copy_data_on_set=False)
    stream: Event


class BILBO_Manager:
    device_server: DeviceServer
    callbacks: BILBO_Manager_Callbacks
    events: BILBO_Manager_Events

    robots: dict[str, BILBO]

    bilbo_scanner: BILBO_NetworkScanner | None

    _devices: dict[str, Device]

    cli: CommandSet

    # === INIT =========================================================================================================
    def __init__(self, host: str | None = None, enable_scanner: bool = False, autostop_robots: bool = True,):
        if host is None:
            host = getHostIP()

        self.host = host

        self.callbacks = BILBO_Manager_Callbacks()
        self.events = BILBO_Manager_Events()

        self.autostop_robots = autostop_robots

        # Devices. Holds all 'bilbo' devices. After sending the correct identification we will append it to BILBOs
        self._devices = {}

        # Robots
        self.robots = {}

        # Device Server
        self.device_server = DeviceServer(host)
        # self.device_server.events.new_device.on(flags={'type': 'bilbo'}, callback=self._newDevice_event)

        self.device_server.events.new_device.on(callback=self._newDevice_event,
                                                predicate=pred_flag_equals('type', 'bilbo'))

        self.device_server.events.device_disconnected.on(callback=self._deviceDisconnected_event,
                                                         predicate=pred_flag_equals('type', 'bilbo'))

        # Scanner
        if enable_scanner:
            self.bilbo_scanner = BILBO_NetworkScanner(BILBO_HOST_NAMES)
            self.bilbo_scanner.events.found.on(self._scannerFoundRobot_event)
        else:
            self.bilbo_scanner = None

        # CLI
        self.cli = BILBO_Manager_CommandSet(self)

        # Logger
        self.logger = Logger("BILBO Manager", "DEBUG")

        # Exit Handler
        register_exit_callback(self.close, priority=10)

    # === METHODS ======================================================================================================
    def init(self):
        self.device_server.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info("Starting Bilbo Manager")
        self.device_server.start()

        if self.bilbo_scanner is not None:
            self.bilbo_scanner.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self) -> None:
        self.logger.info("Closing Bilbo Manager")

        if self.autostop_robots:
            for robot in self.robots.values():
                self._stopBilboRemotely(robot.config.id, robot.config.address)

    # ------------------------------------------------------------------------------------------------------------------
    def emergencyStop(self):
        self.logger.warning("Emergency Stop")
        for robot in self.robots.values():
            robot.stop()

    # ------------------------------------------------------------------------------------------------------------------
    def getRobotById(self, robot_id):
        if robot_id in self.robots:
            return self.robots[robot_id]
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    # === PRIVATE METHODS ==============================================================================================

    def _newDevice_event(self, device: Device):

        if device.information.device_id in self._devices:
            self.logger.warning(f"Device with id {device.information.device_id} already exists")
            return

        self._devices[device.information.device_id] = device
        self.logger.info(f"New bilbo device connected: {device.information.device_id}")
        device.callbacks.event.register(self._deviceEvent_callback, inputs={'device': device})

    # ------------------------------------------------------------------------------------------------------------------
    def _deviceDisconnected_event(self, device: Device):
        # If the device never completed the handshake (not yet in self.robots),
        # clean it up from _devices so it can reconnect later.
        device_id = device.information.device_id
        if device_id in self._devices:
            # Check if it was promoted to a full robot
            for robot in self.robots.values():
                if robot.device == device:
                    self._removeBilbo(robot)
                    return
            # Device connected but disconnected before handshake completed
            self._devices.pop(device_id)
            self.logger.info(f"Device \"{device_id}\" disconnected before handshake")

    # ------------------------------------------------------------------------------------------------------------------
    def _deviceEvent_callback(self, event_message: JSON_Message, device: Device):
        # Check if the event is a BILBO handshake. Only then do we accept it as a BILBO
        if event_message.event == 'bilbo_handshake':
            try:
                bilbo_config = from_dict_auto(BILBO_Config, event_message.data)
            except Exception as e:
                self.logger.error(f"Error in bilbo handshake: {e}. Message: {event_message}")
                return

            # Check if this device is already registered
            if bilbo_config.general.id in self.robots:
                self.logger.warning(f"Device with ID {bilbo_config.general.id} already registered")
                return

            self._addNewBilbo(device, bilbo_config)

    # ------------------------------------------------------------------------------------------------------------------
    def _addNewBilbo(self, device: Device, config: BILBO_Config):

        # Remove the callback for the event
        device.callbacks.event.remove(self._deviceEvent_callback)

        # Create a new BILBO robot
        new_robot = BILBO(device, config)
        self.robots[config.general.id] = new_robot

        # Add the robot's CLI command set
        self.cli.addChild(new_robot.interfaces.cli_command_set)

        # Call the callbacks and events for a new robot
        self.callbacks.new_robot.call(new_robot)
        self.events.new_robot.set(data=new_robot)

        self.logger.info(f"New Bilbo \"{config.general.id}\" connected")

    # ------------------------------------------------------------------------------------------------------------------
    def _removeBilbo(self, robot: BILBO):
        self.robots.pop(robot.id)
        self._devices.pop(robot.device.information.device_id)

        # Remove the robot's CLI command set
        self.cli.removeChild(robot.interfaces.cli_command_set)

        self.callbacks.robot_disconnected.call(robot)
        self.events.robot_disconnected.set(data=robot)

        self.logger.info(f"Bilbo \"{robot.id}\" disconnected")

    # ------------------------------------------------------------------------------------------------------------------
    def _scannerFoundRobot_event(self, data, *args, **kwargs):

        name = data[0]
        ip_address = data[1]

        # Check if this robot is already connected
        if name in self.robots:
            return

        self._startBilboRemotely(name, ip_address)

    # ------------------------------------------------------------------------------------------------------------------
    def _startBilboRemotely(self, name, ip_address, *args, **kwargs):
        self.logger.info(f"Starting {name} remotely via ssh")

        # 1. Check if the main script is already running
        is_running, _ = isScriptRunningViaSSH(hostname=ip_address,
                                              username=BILBO_USER_NAME,
                                              password=BILBO_PASSWORD,
                                              path_to_script=PATH_TO_MAIN
                                              )

        if is_running:
            self.logger.warning(f"Main script is already running on {name}")
            return

        # 2. Start the main script
        started = executePythonViaSSH(ip_address,
                                      BILBO_USER_NAME,
                                      BILBO_PASSWORD,
                                      PATH_TO_MAIN,
                                      pyenv_shim_path=PYENV_SHIM_PATH,
                                      use_pyenv=True)

        if started:
            self.logger.info(f"Started main script on {name}")
        else:
            self.logger.error(f"Failed to start main script on {name}")

    # ------------------------------------------------------------------------------------------------------------------
    def _stopBilboRemotely(self, name, ip_address, *args, **kwargs):
        self.logger.info(f"Stopping {name} remotely via ssh")
        stopped = stopPythonViaSSH(ip_address,
                                   BILBO_USER_NAME,
                                   BILBO_PASSWORD,
                                   PATH_TO_MAIN)
