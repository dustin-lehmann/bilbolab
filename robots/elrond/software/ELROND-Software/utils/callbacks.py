import enum

# Constants to indicate whether a parameter is required or optional.
REQUIRED = True
OPTIONAL = False


class Callback:
    """
    Represents a callback function along with its associated inputs, lambda functions, and parameters.

    Attributes:
        inputs (dict): Static inputs to be passed to the callback.
        lambdas (dict): Callable values that are evaluated at the time of invocation.
        parameters (dict): Additional parameters associated with the callback.
        function (callable): The callback function to be executed.
        discard_inputs (bool): If True, ignores any extra positional or keyword arguments when calling the function.
    """
    inputs: dict
    lambdas: dict
    parameters: dict
    function: callable

    def __init__(self, function: callable, inputs: dict = None, lambdas: dict = None, parameters: dict = None,
                 discard_inputs: bool = False, *args, **kwargs):
        """
        Initializes a new Callback instance.

        Args:
            function (callable): The function to be used as callback.
            inputs (dict, optional): Fixed inputs to pass to the function.
            lambdas (dict, optional): A dictionary of callables whose results will be passed as inputs.
            parameters (dict, optional): Additional parameters for the callback.
            discard_inputs (bool, optional): If True, extra inputs provided during the call are ignored.
        """
        self.function = function

        if inputs is None:
            inputs = {}
        self.inputs = inputs

        if lambdas is None:
            lambdas = {}
        self.lambdas = lambdas

        if parameters is None:
            parameters = {}
        self.parameters = parameters

        self.discard_inputs = discard_inputs

    def __call__(self, *args, **kwargs):
        """
        Calls the callback function, merging inputs from the stored values, evaluated lambdas, and the call arguments.

        Returns:
            The return value of the callback function.
        """
        # Evaluate any lambda functions.
        lambdas_exec = {key: value() for (key, value) in self.lambdas.items()}

        # Depending on discard_inputs, either call with only the stored inputs or merge with provided args.
        if self.discard_inputs:
            ret = self.function(**{**self.inputs, **lambdas_exec})
        else:
            ret = self.function(*args, **{**self.inputs, **kwargs, **lambdas_exec})
        return ret


class CallbackContainer:
    """
    A container for managing callbacks. It allows registration, removal, and invocation of callbacks.
    It can also be parameterized with expected parameters; required parameters must be provided when registering a callback.

    Attributes:
        callbacks (list[Callback]): The list of registered Callback objects.
        expected_parameters (dict): Mapping of parameter names to a tuple (expected type, required flag).
    """
    callbacks: list[Callback]

    def __init__(self, parameters=None):
        """
        Initializes a new CallbackContainer.

        Args:
            parameters (list of tuple, optional): A list of tuples (param_name, expected_type, required_flag)
                that define the expected parameters. For example:
                [('param1', int,  OPTIONAL), ('param2', float, REQUIRED)]
        """
        self.callbacks = []
        self.parameters = parameters  # original input

        # Validate and convert the parameter specifications into a dict.
        if parameters is not None:
            if not isinstance(parameters, list):
                raise ValueError("Parameters must be provided as a list of tuples.")
            expected = {}
            for param_spec in parameters:
                if not (isinstance(param_spec, tuple) and len(param_spec) == 3):
                    raise ValueError("Each parameter specification must be a tuple of (str, type, bool).")
                name, expected_type, required_flag = param_spec
                if not isinstance(name, str):
                    raise ValueError("Parameter name must be a string.")
                if not isinstance(required_flag, bool):
                    raise ValueError("Parameter required flag must be a boolean.")
                if not isinstance(expected_type, type):
                    raise ValueError("Parameter expected type must be a type.")
                expected[name] = (expected_type, required_flag)
            self.expected_parameters = expected
        else:
            self.expected_parameters = {}

    def register(self, function: callable, inputs: dict = None, parameters: dict = None, lambdas: dict = None,
                 discard_inputs=False, *args, **kwargs):
        """
        Registers a callback function. Checks that all required parameters (if any) are provided.

        Args:
            inputs:
            function (callable): The function to register as a callback.
            parameters (dict, optional): Dictionary of parameters to associate with the callback.
            lambdas (dict, optional): Dictionary of lambdas to evaluate at call time.
            discard_inputs (bool, optional): Whether to discard extra call inputs.
            *args, **kwargs: Additional arguments passed to the Callback constructor.

        Raises:
            RuntimeError: If any required parameter (as specified by expected_parameters) is missing.
            TypeError: If a parameter value does not match its expected type.
        """
        # If expected parameters have been set, validate the provided parameters.
        if self.expected_parameters:
            if parameters is None:
                parameters = {}
            for param_name, (expected_type, required_flag) in self.expected_parameters.items():
                if param_name not in parameters:
                    if required_flag:
                        raise RuntimeError(f"Missing required parameter: {param_name}")
                    else:
                        parameters[param_name] = None
                else:
                    if parameters[param_name] is not None and not isinstance(parameters[param_name], expected_type):
                        raise TypeError(
                            f"Parameter '{param_name}' is expected to be of type {expected_type.__name__}, "
                            f"got {type(parameters[param_name]).__name__}."
                        )

        # Create a new Callback with an empty inputs dict.
        callback = Callback(function, inputs=inputs, lambdas=lambdas, parameters=parameters,
                            discard_inputs=discard_inputs, *args, **kwargs)
        self.callbacks.append(callback)

    def remove(self, callback):
        """
        Removes a callback from the container.

        Args:
            callback (Callback or callable): The callback instance or function to remove.
        """
        if isinstance(callback, Callback):
            self.callbacks.remove(callback)
        elif callable(callback):
            cb = next(cb for cb in self.callbacks if cb.function == callback)
            self.callbacks.remove(cb)

    def call(self, *args, **kwargs):
        """
        Invokes all registered callbacks with the given arguments.

        Args:
            *args: Positional arguments to pass to each callback.
            **kwargs: Keyword arguments to pass to each callback.
        """
        for callback in self.callbacks:
            callback(*args, **kwargs)

    def __iter__(self):
        """
        Returns:
            An iterator over the registered callbacks.
        """
        return iter(self.callbacks)


def callback_handler(cls):
    """
    Class decorator to automatically instantiate CallbackContainer attributes declared in the class annotations.

    If a field is annotated as a CallbackContainer and its annotation is an instance (i.e. with parameters),
    that instance is used; otherwise, a default CallbackContainer() is created.

    Args:
        cls (type): The class to decorate.

    Returns:
        The decorated class.
    """
    original_init = cls.__init__

    def new_init(self, *args, **kwargs):
        # Iterate over class annotations to set up CallbackContainer attributes.
        for name, annotation in cls.__annotations__.items():
            # If the annotation is already an instance of CallbackContainer, use it.
            if isinstance(annotation, CallbackContainer):
                setattr(self, name, annotation)
            # If the annotation is exactly the type CallbackContainer, create a default instance.
            elif annotation == CallbackContainer:
                setattr(self, name, CallbackContainer())
        if original_init:
            original_init(self, *args, **kwargs)

    cls.__init__ = new_init
    return cls
