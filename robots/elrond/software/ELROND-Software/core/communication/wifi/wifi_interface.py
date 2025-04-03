import enum
import threading
import time

from core.communication.protocol import Protocol
from core.communication.wifi.tcp.protocols.tcp_json_protocol import TCP_JSON_Protocol, TCP_JSON_Message
from core.communication.wifi.wifi_connection import WIFI_Connection
from core.communication.wifi.data_link import DataLink, Command, generateDataDict, generateCommandDict, CommandArgument
from utils.callbacks import Callback, callback_handler, CallbackContainer
from utils.events import event_handler
from utils.logging_utils import Logger
from utils.time import TimeoutTimer

logger = Logger("WIFI INTERFACE")


@callback_handler
class WIFI_Interface_Callbacks:
    """
    Container for WIFI Interface callbacks.

    Attributes:
        connected (CallbackContainer): Called when a connection is established.
        disconnected (CallbackContainer): Called when the connection is lost.
        sync (CallbackContainer): Called when a sync event is received.
    """
    connected: CallbackContainer
    disconnected: CallbackContainer
    sync: CallbackContainer
    heartbeat_timeout: CallbackContainer


@event_handler
class WIFI_Interface_Events:
    """
    Event handler for WIFI Interface events.

    Extend this class to implement additional event handling if needed.
    """
    ...


class WIFI_Interface_State(enum.IntEnum):
    NOT_CONNECTED = 0,
    RUNNING = 1,
    TIMEOUT = 2,
    ERROR = 3

class WIFI_Interface:
    """
    Represents a WIFI Interface for communication over TCP using a JSON-based protocol.

    Attributes:
        name (str): Device name.
        id (str): Device identifier.
        device_class (str): Device classification.
        device_type (str): Type/model of the device.
        device_revision (str): Device revision.
        uid (bytes): Unique device identifier in bytes.
        data (dict): Dictionary containing DataLink parameters or groups.
        commands (dict): Dictionary containing registered Command objects.
        connection (WIFI_Connection): Underlying WIFI connection object.
        connected (bool): Connection status.
        callbacks (WIFI_Interface_Callbacks): Callbacks for connection events.
        protocol (Protocol): Communication protocol (default is TCP_JSON_Protocol).
    """

    name: str
    id: str
    device_class: str
    device_type: str
    device_revision: str

    uid: bytes
    data: dict  # Expected to be dict[str, (dict, DataLink)]
    commands: dict  # Expected to be dict[str, (dict, Command)]

    connection: WIFI_Connection

    connected: bool

    state: WIFI_Interface_State

    callbacks: WIFI_Interface_Callbacks

    heartbeat_timer: TimeoutTimer

    protocol: Protocol = TCP_JSON_Protocol

    def __init__(self, interface_type: str = 'wifi', device_class: str = None, device_type: str = None,
                 device_revision: str = None, device_name: str = None, device_id: str = None):
        """
        Initializes the WIFI_Interface instance with the provided device information.

        Args:
            interface_type (str): Interface type (default is 'wifi').
            device_class (str, optional): Class/category of the device.
            device_type (str, optional): Type/model of the device.
            device_revision (str, optional): Revision of the device.
            device_name (str, optional): Name of the device.
            device_id (str, optional): Unique identifier for the device.
        """
        # Set device properties.
        self.device_class = device_class
        self.device_type = device_type
        self.device_revision = device_revision
        self.name = device_name
        self.id = device_id
        self.connected = False
        self.state = WIFI_Interface_State.NOT_CONNECTED

        self.heartbeat_timer = TimeoutTimer(timeout_time=5, timeout_callback=self._heartbeat_timeout_callback)

        # Initialize callbacks and WI-FI connection.
        self.callbacks = WIFI_Interface_Callbacks()
        self.connection = WIFI_Connection(id=device_id)

        # Configure WI-FI connection callbacks.
        self.connection.callbacks.connected.register(self._connected_callback)
        self.connection.callbacks.disconnected.register(self._disconnected_callback)
        self.connection.callbacks.rx.register(self._rx_callback)

        # --- PARAMETERS ---
        # Initialize the parameters dictionary (should be populated with DataLink objects or groups).
        self.data = {}  # TODO: Populate parameters for this board

        # --- COMMANDS ---
        self.commands = {}
        # Register the "getCommands" command to return all registered commands with their descriptions.
        self.addCommand("getCommands",
                        self.getCommands,
                        [],
                        "Return the description of all registered commands and their arguments.")

    def start(self):
        """
        Starts the WIFI interface by initiating the WIFI connection.
        """
        logger.debug("Start WIFI Interface")
        self.connection.start()

    def close(self):
        """
        Closes the WIFI connection.
        """
        self.connection.close()

    def sendEventMessage(self, event: str, data: dict = None, request_id: int = None):
        """
        Sends an event message to the remote device.

        Args:
            event (str): The event name.
            data (dict, optional): Additional event data.
            request_id (int, optional): Request identifier for correlating responses.
        """
        msg = TCP_JSON_Message()
        msg.source = self.id
        msg.address = ''
        msg.type = 'event'
        msg.event = event
        if data:
            msg.data.update(data)
        if request_id is not None:
            msg.request_id = request_id
        self._wifi_send(msg)

    def sendStreamMessage(self, data):
        """
        Sends a stream message to the remote device.

        Args:
            data: The data to be streamed.
        """
        msg = TCP_JSON_Message()
        msg.source = self.id
        msg.address = 0
        msg.type = 'stream'
        msg.data = data
        self._wifi_send(msg)

    def addCommands(self, commands):
        """
        Adds one or more commands to the WIFI_Interface.

        Args:
            commands (Command or list[Command] or dict): Command(s) to be added.
        """
        if isinstance(commands, Command):
            self.commands[commands.identifier] = commands
        elif isinstance(commands, list):
            assert all(isinstance(command, Command) for command in commands)
            for command in commands:
                self.commands[command.identifier] = command
        elif isinstance(commands, dict):
            for command_identifier, command in commands.items():
                assert isinstance(command, Command)
                self.commands[command_identifier] = command

    def addCommand(self, identifier: str, callback: (callable, Callback), arguments: list, description: str, execute_in_thread: bool = False):
        """
        Adds a single command to the WIFI_Interface.

        Args:
            identifier (str): Unique command identifier.
            callback (callable or Callback): The function or callback to execute.
            arguments (list): List of command arguments (each can be a string or CommandArgument).
            description (str): Description of the command.
        """
        self.commands[identifier] = Command(identifier=identifier, callback=callback, arguments=arguments,
                                            description=description, execute_in_thread=execute_in_thread)

    def getCommands(self):
        """
        Returns a dictionary description of all registered commands.

        Returns:
            dict: A dictionary with details of the commands.
        """
        return generateCommandDict(self.commands)

    def _wifi_send(self, message):
        """
        Sends a message over the WIFI connection.

        Args:
            message: The message to send.
        """
        self.connection.send(message)

    def _connected_callback(self):
        """
        Callback invoked when the WIFI connection is established.
        Sends device identification and triggers connected callbacks.
        """
        self._sendDeviceIdentification()
        self.connected = True
        self.state = WIFI_Interface_State.RUNNING
        for callback in self.callbacks.connected:
            callback(self)
        logger.info("Connected to WIFI")
        self.heartbeat_timer.start()

    def _disconnected_callback(self):
        """
        Callback invoked when the WIFI connection is lost.
        Triggers disconnected callbacks.
        """
        self.connected = False
        self.state = WIFI_Interface_State.NOT_CONNECTED
        for callback in self.callbacks.disconnected:
            callback(self)

        logger.warning("Disconnected from WIFI")

        self.heartbeat_timer.stop()

    def _rx_callback(self, message, *args, **kwargs):
        """
        Callback invoked upon receiving a message.

        Args:
            message: The received message.
        """
        self._handleRxMessage(message)

    def _handleRxMessage(self, message: TCP_JSON_Message):
        """
        Routes the incoming message to the appropriate handler based on its type.

        Args:
            message (TCP_JSON_Message): The received message.
        """
        if message.type == 'write':
            self._handler_writeMessage(message)
        elif message.type == 'read':
            self._handler_readMessage(message)
        elif message.type == 'function':
            self._handler_functionMessage(message)
        elif message.type == 'event':
            self._handlerEventMessage(message)

    def _handler_writeMessage(self, message: TCP_JSON_Message):
        """
        Processes write messages by updating parameters.
        Sends a response or event message if errors occur.

        Args:
            message (TCP_JSON_Message): The write message containing parameter updates.
        """
        errors = {}

        for entry, value in message.data.items():
            if entry not in self.data:
                logger.warning(f"Received parameter {entry}, which is not a valid entry.")
                errors[entry] = "Invalid parameter"
                continue

            param = self.data[entry]
            # Handle single parameter.
            if isinstance(param, DataLink):
                try:
                    if not param.set(value):
                        errors[entry] = f"Failed to set parameter {entry}"
                        logger.warning(f"Failed to set parameter {entry} to value {value}.")
                    else:
                        logger.debug(f"Set parameter {entry} to value {value}.")
                except Exception as e:
                    errors[entry] = str(e)
                    logger.error(f"Exception setting parameter {entry}: {e}")
            # Handle group of parameters (only one level supported).
            elif isinstance(param, dict) and isinstance(value, dict):
                for sub_entry, sub_value in value.items():
                    if sub_entry not in param:
                        logger.warning(f"Received parameter {entry}:{sub_entry}, which is not a valid entry.")
                        errors[f"{entry}:{sub_entry}"] = "Invalid sub-parameter"
                        continue
                    sub_param = param[sub_entry]
                    if not isinstance(sub_param, DataLink):
                        logger.warning(f"Cannot set parameter {entry}:{sub_entry}: unsupported parameter structure.")
                        errors[f"{entry}:{sub_entry}"] = "Invalid parameter structure"
                        continue
                    try:
                        if not sub_param.set(sub_value):
                            logger.warning(f"Failed to set parameter {entry}:{sub_entry} to value {sub_value}.")
                            errors[f"{entry}:{sub_entry}"] = f"Failed to set parameter {sub_entry}"
                        else:
                            logger.debug(f"Set parameter {entry}:{sub_entry} to value {sub_value}.")
                    except Exception as e:
                        errors[f"{entry}:{sub_entry}"] = str(e)
                        logger.error(f"Exception setting parameter {entry}:{sub_entry}: {e}")
            else:
                logger.warning(f"Parameter {entry} has unsupported structure.")
                errors[entry] = "Unsupported parameter structure"

        if message.request_response:
            response_msg = TCP_JSON_Message()
            response_msg.source = self.id
            response_msg.address = ''
            response_msg.type = 'response'
            response_msg.request_id = message.id
            response_msg.data = {"success": len(errors) == 0, "errors": errors}
            self._wifi_send(response_msg)
        elif errors:
            # If no response is explicitly requested, send an event for the errors.
            self.sendEventMessage("write_error", {"errors": errors}, request_id=message.id)

    def _handler_readMessage(self, message: TCP_JSON_Message):
        """
        Processes read messages by retrieving parameter values.

        Args:
            message (TCP_JSON_Message): The read message specifying parameters.
        """
        response = {}
        errors = {}

        # If no specific parameter is requested, read all parameters.
        if not message.data:
            for key, param in self.data.items():
                if isinstance(param, DataLink):
                    try:
                        response[key] = param.get()
                    except Exception as e:
                        errors[key] = str(e)
                        logger.error(f"Error reading parameter {key}: {e}")
                elif isinstance(param, dict):
                    response[key] = {}
                    for subkey, sub_param in param.items():
                        if isinstance(sub_param, DataLink):
                            try:
                                response[key][subkey] = sub_param.get()
                            except Exception as e:
                                errors[f"{key}:{subkey}"] = str(e)
                                logger.error(f"Error reading parameter {key}:{subkey}: {e}")
                        else:
                            errors[f"{key}:{subkey}"] = "Invalid parameter structure"
                else:
                    errors[key] = "Unsupported parameter structure"
        else:
            # Determine keys to read based on the type of message.data.
            if isinstance(message.data, dict):
                keys_to_read = message.data.keys()
            elif isinstance(message.data, list):
                keys_to_read = message.data
            else:
                keys_to_read = [message.data]

            for key in keys_to_read:
                if key not in self.data:
                    errors[key] = "Invalid parameter"
                    logger.warning(f"Received read request for invalid parameter {key}.")
                    continue
                param = self.data[key]
                if isinstance(param, DataLink):
                    try:
                        response[key] = param.get()
                    except Exception as e:
                        errors[key] = str(e)
                        logger.error(f"Error reading parameter {key}: {e}")
                elif isinstance(param, dict):
                    response[key] = {}
                    subkeys = None
                    # If message.data is a dict and provides a list of subkeys, use it; otherwise, read all subkeys.
                    if isinstance(message.data, dict) and isinstance(message.data.get(key, None), list):
                        subkeys = message.data[key]
                    if subkeys is None:
                        for subkey, sub_param in param.items():
                            if isinstance(sub_param, DataLink):
                                try:
                                    response[key][subkey] = sub_param.get()
                                except Exception as e:
                                    errors[f"{key}:{subkey}"] = str(e)
                                    logger.error(f"Error reading parameter {key}:{subkey}: {e}")
                            else:
                                errors[f"{key}:{subkey}"] = "Invalid parameter structure"
                    else:
                        for subkey in subkeys:
                            if subkey not in param:
                                errors[f"{key}:{subkey}"] = "Invalid sub-parameter"
                                logger.warning(f"Received read request for invalid sub-parameter {key}:{subkey}.")
                                continue
                            sub_param = param[subkey]
                            if isinstance(sub_param, DataLink):
                                try:
                                    response[key][subkey] = sub_param.get()
                                except Exception as e:
                                    errors[f"{key}:{subkey}"] = str(e)
                                    logger.error(f"Error reading parameter {key}:{subkey}: {e}")
                            else:
                                errors[f"{key}:{subkey}"] = "Invalid parameter structure"
                else:
                    errors[key] = "Unsupported parameter structure"
                    logger.warning(f"Parameter {key} has unsupported structure.")

        response_msg = TCP_JSON_Message()
        response_msg.source = self.id
        response_msg.address = ''
        response_msg.type = 'response'
        response_msg.request_id = message.id
        response_msg.data = {"output": response, "errors": errors, "success": len(errors) == 0}
        self._wifi_send(response_msg)

    def _handler_functionMessage(self, message: TCP_JSON_Message):
        """
        Processes function messages by executing the corresponding command in a one-shot thread.
        The thread executes the function call and sends the return message once complete.

        Args:
            message (TCP_JSON_Message): The function message containing the function name and input.
        """
        if 'function' not in message.data:
            logger.warning("Received function message without function name")
            return

        function_name = message.data['function']

        # Check if the function is registered.
        if function_name not in self.commands:
            logger.warning(f"Received function {function_name}, which is not a valid entry.")
            self.sendEventMessage("function_error", {"error": f"Function {function_name} not found"},
                                  request_id=message.id)
            return

        if 'input' not in message.data:
            logger.warning(f"Received function {function_name} without input")
            self.sendEventMessage("function_error", {"error": f"Missing input for function {function_name}"},
                                  request_id=message.id)
            return

        value = message.data['input']

        # Execute the command in a one-shot thread.
        def execute_function():
            output = None
            error = None
            try:
                output = self.commands[function_name].execute(value)
                success = True
            except Exception as e:
                logger.warning(f"Error executing function {function_name}: {e}")
                success = False
                error = str(e)

            if message.request_response is not None:
                response_message = TCP_JSON_Message()
                response_message.address = ''
                response_message.source = self.id
                response_message.type = 'response'
                response_message.request_id = message.id
                response_message.data = {'output': output,
                                         'error': error,
                                         'success': success}
                self._wifi_send(response_message)

        if self.commands[function_name].execute_in_thread:
            thread = threading.Thread(target=execute_function)
            thread.start()
        else:
            execute_function()

    def _handlerEventMessage(self, message):
        """
        Processes event messages. Currently handles 'sync' events.

        Args:
            message: The event message.
        """
        if message.event == 'sync':
            self.callbacks.sync.call(message.data)
        elif message.event == 'heartbeat':
            self._handleHeartbeatMessage(message.data)
        else:
            ...
        # match message.event:
        #     case 'sync':
        #         self.callbacks.sync.call(message.data)
        #     case 'heartbeat':
        #         self._handleHeartbeatMessage(message.data)
        #     case _:
        #         ...

    # ------------------------------------------------------------------------------------------------------------------
    def _handleHeartbeatMessage(self, data):
        self.heartbeat_timer.reset()

    # ------------------------------------------------------------------------------------------------------------------
    def _heartbeat_timeout_callback(self):
        return

        self.callbacks.heartbeat_timeout.call()
        self.heartbeat_timer.stop()
        self.state = WIFI_Interface_State.TIMEOUT
        logger.warning("Heartbeat timeout")

        # Try Sending out an event to the server
        self.sendEventMessage(event='error',
                              data={'error': 'Heartbeat timeout'})
        time.sleep(0.25)  # Short sleep to make sure the event is sent
        self.connection.disconnect()
        self.connected = False

    # ------------------------------------------------------------------------------------------------------------------
    def _sendDeviceIdentification(self):
        """
        Sends an event message with device identification information along with
        the current parameters and commands.
        """
        msg = TCP_JSON_Message()
        msg.source = self.id
        msg.address = ''
        msg.type = 'event'
        msg.event = 'device_identification'
        msg.data = {
            'device_class': self.device_class,
            'device_type': self.device_type,
            'device_name': self.name,
            'device_id': self.id,
            'address': self.id,
            'revision': self.device_revision,
            'data': generateDataDict(self.data),
            'commands': generateCommandDict(self.commands)
        }
        self._wifi_send(msg)
