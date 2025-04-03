from utils.callbacks import Callback
from utils.logging_utils import Logger
import dataclasses
import inspect

logger = Logger("DATALINK")


# ======================================================================================================================
class DataLink:
    """
    Represents a data parameter that can be read from or written to remotely.

    Attributes:
        identifier (str): Descriptor of the parameter.
        description (str): Description of the parameter.
        datatype (tuple or type): Allowed data types for the parameter.
        limits (list): Allowed values or range for the parameter.
        limits_mode (str): 'range' for a continuous range or 'explicit' for a set of allowed values.
        writable (bool): If False, the parameter cannot be modified.
        write_function (Callback or callable): Function to be executed when writing a value.
        read_function (Callback or callable): Function to be executed when reading the value.
        index (int): Optional index if the parameter is part of a list-like object.
        obj (object): The object associated with the parameter.
        name (str): The attribute or key name in the associated object.
    """

    def __init__(self, identifier, description, datatype, limits: list = None, limits_mode: str = 'range',
                 write_function: (Callback, callable) = None, read_function: (Callback, callable) = None,
                 obj: object = None, name: str = None, writable: bool = True, index: int = None):
        """
        Initializes a DataLink instance.

        Args:
            identifier (str): Descriptor of the parameter.
            description (str): Description of the parameter.
            datatype (tuple or type): Allowed data type(s) for the parameter.
            limits (list, optional): A list defining the allowed values or [min, max] range.
            limits_mode (str, optional): Mode for limits ('range' or 'explicit').
            write_function (Callback or callable, optional): Function to be called when setting a value.
            read_function (Callback or callable, optional): Function to be called when retrieving a value.
            obj (object, optional): Object that holds the parameter.
            name (str, optional): Name of the parameter in the associated object.
            writable (bool, optional): Indicates if the parameter is writable.
            index (int, optional): Index in the object if it is list-like.
        """
        self.identifier = identifier
        self.description = description
        self.datatype = datatype
        self.limits = limits
        self.limits_mode = limits_mode
        self.write_function = write_function
        self.read_function = read_function
        self.obj = obj
        self.name = name
        self.writable = writable
        self.index = index

    def get(self):
        """
        Retrieves the current value of the parameter. If a read function is provided, it will be used;
        otherwise, the value is retrieved directly from the associated object.

        Returns:
            The current value of the parameter.
        """
        if self.read_function is not None:
            return self.read_function()
        elif self.obj is not None and self.name is not None:
            if isinstance(self.obj, dict):
                return self.obj[self.name]
            else:
                return getattr(self.obj, self.name)

    def set(self, value) -> bool:
        """
        Sets the parameter's value after validating the data type and checking limits.

        Args:
            value: The value to set.

        Returns:
            bool: True if the value is set successfully; otherwise, False.
        """
        if not self.writable:
            return False

        # Validate the data type.
        if not isinstance(value, self.datatype):
            # Allow conversion from int to float if needed.
            if self.datatype == float and isinstance(value, int):
                value = float(value)
            else:
                return False

        # Check if the value is within the specified limits.
        if self.limits is not None:
            if self.limits_mode == 'explicit':
                if value not in self.limits:
                    return False
            elif self.limits_mode == 'range':
                if value < self.limits[0] or value > self.limits[1]:
                    return False

        # Set the value in the associated object.
        if self.obj is not None and self.name is not None:
            if isinstance(self.obj, dict):
                self.obj[self.name] = value
            else:
                setattr(self.obj, self.name, value)
        elif self.obj is not None and self.index is not None:
            self.obj[self.index] = value

        # Invoke the write callback if provided.
        if self.write_function is not None:
            if not isinstance(self.write_function, Callback) and not hasattr(self.write_function, '__self__'):
                return self.write_function(self.obj, value)
            return self.write_function(value)

        return True

    def generateDescription(self):
        """
        Generates a dictionary description of the DataLink instance.

        Returns:
            dict: A dictionary containing parameter details.
        """
        out = {
            'identifier': self.identifier,
            'description': self.description,
            'datatype': str(self.datatype),
            'limits': self.limits,
            'writable': self.writable,
            'value': self.get()
        }
        return out


# ======================================================================================================================
@dataclasses.dataclass
class CommandArgument:
    """
    Represents a command argument with its properties.

    Attributes:
        name (str): The argument's name.
        description (str): A brief description of the argument.
        type (type): Expected type of the argument.
        optional (bool): Indicates whether the argument is optional.
        default (any): Default value if the argument is not provided.
    """
    name: str
    description: str
    type: type
    optional: bool = False
    default: any = None


# ----------------------------------------------------------------------------------------------------------------------
class Command:
    """
    Encapsulates a command with its callback, arguments, and description.

    Attributes:
        identifier (str): Unique identifier for the command.
        callback (callable or Callback): The function or callback to execute.
        arguments (dict): Dictionary of CommandArgument objects, keyed by argument name.
        description (str): Description of the command.
    """

    def __init__(self, identifier: str, callback: (callable, Callback), arguments, description: str, execute_in_thread=False):
        """
        Initializes a Command instance.

        Args:
            identifier (str): Unique identifier for the command.
            callback (callable or Callback): The function or callback to be executed.
            arguments (dict or list): Either a dictionary or a list of command arguments. If a list is provided,
                                      string items are converted into CommandArgument with type set to object.
            description (str): A textual description of the command.
        """
        self.identifier = identifier
        self.callback = callback
        self.description = description
        self.execute_in_thread = execute_in_thread

        # Convert arguments to a dictionary if provided as a list.
        if isinstance(arguments, dict):
            self.arguments = arguments
        elif isinstance(arguments, list):
            arg_dict = {}
            for item in arguments:
                if isinstance(item, str):
                    # Create a CommandArgument with the name; type is object, and it's non-optional.
                    arg_dict[item] = CommandArgument(name=item, description=item, type=object, optional=False)
                elif isinstance(item, CommandArgument):
                    arg_dict[item.name] = item
                else:
                    logger.error(f"Unsupported argument type in initialization: {item}")
            self.arguments = arg_dict
        else:
            logger.error("Unsupported type for arguments in Command initialization. Expected dict or list.")
            self.arguments = {}

    def execute(self, arguments=None):
        """
        Executes the command callback with the provided arguments.

        If arguments are not provided for an optional parameter, the default value is used.
        If the default is not specified in the CommandArgument, an attempt is made to retrieve it from
        the callback's signature.

        Args:
            arguments (dict or list, optional): Arguments to pass to the callback. If a list is provided,
                                                  it is mapped to the command's arguments based on their order.

        Returns:
            The result of the callback execution, or None if a required argument is missing.
        """
        if arguments is None:
            arguments = {}

        # Convert list of arguments to a dictionary using the order of keys.
        if not isinstance(arguments, dict):
            if isinstance(arguments, list):
                new_args = {}
                keys = list(self.arguments.keys())
                for i, value in enumerate(arguments):
                    if i < len(keys):
                        new_args[keys[i]] = value
                arguments = new_args
            else:
                logger.error("Arguments provided to execute must be a dict or list.")
                arguments = {}

        final_args = {}

        # Process each expected argument.
        for arg_name, command_arg in self.arguments.items():
            if arg_name in arguments:
                final_args[arg_name] = arguments[arg_name]
            else:
                if command_arg.optional:
                    # Use the provided default if not None, else try to get a default from the callback signature.
                    if command_arg.default is not None:
                        final_args[arg_name] = command_arg.default
                    else:
                        func = self.callback.function if isinstance(self.callback, Callback) else self.callback
                        try:
                            sig = inspect.signature(func)
                            param = sig.parameters.get(arg_name)
                            if param and param.default is not inspect.Parameter.empty:
                                final_args[arg_name] = param.default
                            else:
                                final_args[arg_name] = None
                        except Exception as e:
                            logger.error(f"Could not inspect callback for command {self.identifier}: {e}")
                            final_args[arg_name] = None
                else:
                    logger.error(f"Missing required argument '{arg_name}' for command {self.identifier}")
                    return

        # Execute the callback with the collected arguments.
        if isinstance(self.callback, Callback):
            return self.callback(**final_args)
        else:
            return self.callback(**final_args)

    def generateDescription(self):
        """
        Generates a dictionary description of the command, including its identifier, description,
        and details of its arguments.

        Returns:
            dict: A dictionary representing the command details.
        """
        out = {
            'identifier': self.identifier,
            'description': self.description,
            'arguments': {arg_name: self._serialize_command_argument(arg)
                          for arg_name, arg in self.arguments.items()}
        }
        return out

    def _serialize_command_argument(self, arg: CommandArgument) -> dict:
        """
        Serializes a CommandArgument into a dictionary for descriptive purposes.

        Args:
            arg (CommandArgument): The command argument to serialize.

        Returns:
            dict: A dictionary representation of the command argument.
        """
        arg_dict = dataclasses.asdict(arg)
        if 'type' in arg_dict:
            arg_dict['type'] = arg_dict['type'].__name__ if hasattr(arg_dict['type'], '__name__') else str(
                arg_dict['type'])
        return arg_dict


# ======================================================================================================================
def generateDataDict(data: dict[str, DataLink]):
    """
    Recursively generates a dictionary description for a collection of DataLink objects.

    Args:
        data (dict[str, DataLink]): Dictionary where keys are names and values are DataLink instances or nested dictionaries.

    Returns:
        dict: A nested dictionary with details of the DataLink parameters.
    """
    out = {}
    for name, value in data.items():
        if isinstance(value, DataLink):
            out[name] = value.generateDescription()
        elif isinstance(value, dict):
            out[name] = generateDataDict(value)
    return out


# ======================================================================================================================
def generateCommandDict(commands: dict[str, Command]):
    """
    Generates a dictionary description for a collection of Command objects.

    Args:
        commands (dict[str, Command]): Dictionary where keys are command names and values are Command instances.

    Returns:
        dict: A dictionary with details of the commands.
    """
    out = {}
    for name, command in commands.items():
        out[name] = command.generateDescription()
    return out


# ======================================================================================================================
# Example usage of the defined classes and functions.
if __name__ == '__main__':
    # ---------------------------
    # Example for DataLink
    # ---------------------------
    print("==== DataLink Examples ====")
    # Create a simple object (dictionary) to hold parameter values.
    sample_obj = {"param1": 10, "param2": 0.5}
    data_links = {
        "param1": DataLink(
            identifier="param1",
            description="An integer parameter between 0 and 100",
            datatype=int,
            limits=[0, 100],
            limits_mode="range",
            obj=sample_obj,
            name="param1",
            writable=True
        ),
        "param2": DataLink(
            identifier="param2",
            description="A float parameter between 0.0 and 1.0",
            datatype=float,
            limits=[0.0, 1.0],
            limits_mode="range",
            obj=sample_obj,
            name="param2",
            writable=False
        )
    }
    print("Initial Data Dictionary:")
    print(generateDataDict(data_links))

    # Modify a writable DataLink and display the updated dictionary.
    data_links["param1"].set(50)
    print("\nData Dictionary after setting param1 to 50:")
    print(generateDataDict(data_links))

    # ---------------------------
    # Example for Command
    # ---------------------------
    print("\n==== Command Examples ====")


    def add_numbers(a: int, b: int = 5):
        """
        Adds two numbers and returns the result.

        Args:
            a (int): The first number.
            b (int, optional): The second number (default is 5).

        Returns:
            int: The sum of a and b.
        """
        return a + b


    # Create command arguments with optional and default values.
    arg_a = CommandArgument(name="a", description="First number", type=int, optional=False)
    arg_b = CommandArgument(name="b", description="Second number", type=int, optional=True, default=5)

    # Initialize the Command with a list of arguments.
    command = Command("add_numbers", add_numbers, [arg_a, arg_b],
                      "Adds two numbers with an optional second parameter.")

    print("Command Description:")
    print(command.generateDescription())

    # Execute the command by providing only the required argument; the optional argument will use its default.
    result = command.execute({"a": 10})
    print("\nExecution Result (a=10, b uses default value 5):", result)

    # Execute the command by providing both arguments.
    result = command.execute({"a": 7, "b": 3})
    print("Execution Result (a=7, b=3):", result)

    # ---------------------------
    # Example for generateCommandDict
    # ---------------------------
    commands = {
        "add_numbers": command
    }
    print("\nGenerated Command Dictionary:")
    print(generateCommandDict(commands))
