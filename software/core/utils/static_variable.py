import inspect

class StaticVariable:
    _storage = {}  # Class-level storage to hold static variables

    def __new__(cls, var_type, initial_value=None, var_name=""):
        # Automatically determine the calling function's name
        caller_function_name = inspect.stack()[1].function
        # Use a combination of the function name and variable name as a unique key
        key = (caller_function_name, var_name)
        if key not in cls._storage:
            # Create and store the variable only if it doesn't exist
            cls._storage[key] = super().__new__(cls)
            cls._storage[key]._initialize(var_type, initial_value)
        return cls._storage[key]

    def _initialize(self, var_type, initial_value):
        self.var_type = var_type
        self.value = var_type(initial_value) if initial_value is not None else var_type()

    def __iadd__(self, other):
        self.value += other
        return self

    def __isub__(self, other):
        self.value -= other
        return self

    def __imul__(self, other):
        self.value *= other
        return self

    def __itruediv__(self, other):
        self.value /= other
        return self

    def __repr__(self):
        return repr(self.value)

    def __int__(self):
        return int(self.value)

    def __float__(self):
        return float(self.value)

    def __str__(self):
        return str(self.value)
