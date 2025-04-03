import ctypes
from dataclasses import is_dataclass, fields
from typing import List, Dict, Tuple, Union, Type, Any

# import graphviz


# Define basic ctypes for convenience
FLOAT = ctypes.c_float
DOUBLE = ctypes.c_double
UINT8 = ctypes.c_uint8
UINT16 = ctypes.c_uint16
INT8 = ctypes.c_int8
INT16 = ctypes.c_int16
UINT32 = ctypes.c_uint32
INT32 = ctypes.c_int32

# Define a broad type hint for ctypes types and instances
CType = Union[
    Type[ctypes._SimpleCData],  # Scalar types like c_float, c_int
    Type[ctypes.Array],  # Array types like c_float * 8
    Type[ctypes.Structure],  # Structure types
    ctypes._SimpleCData,  # Instances of scalar types
    ctypes.Array,  # Instances of array types
    ctypes.Structure  # Instances of structures
]


class ConversionError(Exception):
    """Custom exception for conversion errors."""
    pass


def struct_to_dict(struct: ctypes.Structure, ctype_type: (Any, ctypes.Structure)) -> dict:
    """
    Converts a ctypes.Structure instance to a dictionary.

    Args:
        struct (ctypes.Structure): The input structure.
        ctype_type (ctypes.Structure): The type of the input structure.

    Returns:
        dict: A dictionary representation of the structure.
    """
    result = {}
    for field, field_type in ctype_type._fields_:
        value = getattr(struct, field)

        # Handle null pointers
        if (type(value) not in [int, float, bool]) and not bool(value):
            value = None

        # Handle arrays
        elif hasattr(value, "_length_") and hasattr(value, "_type_"):
            result[field] = [
                struct_to_dict(v, field_type._type_) if issubclass(field_type._type_, ctypes.Structure) else v for v in
                value]

        # Handle nested structures
        elif issubclass(field_type, ctypes.Structure):
            result[field] = struct_to_dict(value, field_type)

        # Handle primitive fields
        else:
            result[field] = value
    return result


def dict_to_struct(data: dict, struct: ctypes.Structure) -> ctypes.Structure:
    """
    Converts a dictionary to a ctypes.Structure instance.

    Args:
        data (dict): The input dictionary to convert.
        struct (ctypes.Structure): A ctypes.Structure subclass.

    Returns:
        ctypes.Structure: An instance of the given ctypes.Structure with values populated from the dictionary.

    Raises:
        ConversionError: If any keys in the dictionary are missing or don't match the structure's fields.
    """
    if not issubclass(struct, ctypes.Structure):
        raise TypeError("The provided struct must be a subclass of ctypes.Structure")

    struct_instance = struct()
    fields = {field[0]: field[1] for field in struct._fields_}

    for key, value in data.items():
        if key not in fields:
            raise ConversionError(f"Key '{key}' not found in the structure '{struct.__name__}'.")

        field_type = fields[key]

        # Handle ctypes.Array fields
        if issubclass(type(field_type), type(ctypes.Array)):
            if not isinstance(value, (list, tuple)):
                raise ConversionError(f"Expected a list or tuple for array field '{key}', got {type(value).__name__}.")
            array_type = field_type
            if len(value) != array_type._length_:
                raise ConversionError(f"Array field '{key}' expects {array_type._length_} elements, got {len(value)}.")
            try:
                setattr(struct_instance, key, array_type(*value))
            except Exception as e:
                raise ConversionError(f"Failed to set array field '{key}' on '{struct.__name__}': {e}")

        # Handle nested structures
        elif issubclass(field_type, ctypes.Structure):
            if not isinstance(value, dict):
                raise ConversionError(
                    f"Expected a dictionary for nested structure '{key}', got {type(value).__name__}.")
            setattr(struct_instance, key, dict_to_struct(value, field_type))

        # Handle scalar fields
        else:
            try:
                setattr(struct_instance, key, value)
            except Exception as e:
                raise ConversionError(f"Failed to set key '{key}' on '{struct.__name__}': {e}")

    # Check for missing keys
    for field_name in fields.keys():
        if not hasattr(struct_instance, field_name):
            raise ConversionError(f"Missing required field '{field_name}' in the dictionary for '{struct.__name__}'.")

    return struct_instance


def is_valid_ctype(obj) -> bool:
    """
    Check if the given object is a valid ctypes type.

    Args:
        obj: The object to check.

    Returns:
        bool: True if the object is a valid ctypes type, False otherwise.
    """
    # Basic ctypes scalar types
    scalar_ctypes = (
        ctypes._SimpleCData,  # Base class for c_int, c_float, etc.
    )
    # Check for ctypes scalar types
    if isinstance(obj, type) and issubclass(obj, scalar_ctypes):
        return True

    # Check for ctypes.Structure
    if isinstance(obj, type) and issubclass(obj, ctypes.Structure):
        return True

    # Check for ctypes.Array
    if isinstance(obj, type) and issubclass(obj, ctypes.Array):
        return True

    return False


def ctype_to_value(ctype_value, ctype_type):
    """
    Convert a ctypes instance to its Python equivalent.

    Args:
        ctype_value: The ctypes instance to convert.
        ctype_type: The type of the input (e.g., ctypes.c_int, ctypes.Structure).

    Returns:
        The Python equivalent of the input.

    Raises:
        TypeError: If the ctype_value is not an instance of ctype_type.
    """
    if not isinstance(ctype_value, ctype_type):
        raise TypeError(f"Provided ctype_value is not an instance of {ctype_type}.")

    if isinstance(ctype_value, ctypes._SimpleCData):
        return ctype_value.value  # Scalars like c_int or c_float

    if isinstance(ctype_value, ctypes.Array):
        # Convert arrays to Python lists
        return [ctype_to_value(item, ctype_type._type_) for item in ctype_value]

    if isinstance(ctype_value, ctypes.Structure):
        # Convert structures to dictionaries
        return struct_to_dict(ctype_value, ctype_type)

    raise TypeError(f"Unsupported ctypes type: {type(ctype_value)}")


def value_to_ctype(value, ctype_type):
    """
    Convert a Python value to a ctypes instance.

    Args:
        value: The Python value to convert.
        ctype_type: The desired ctypes type (e.g., ctypes.c_int, ctypes.Structure).

    Returns:
        A ctypes instance.

    Raises:
        TypeError: If the value is already of the correct ctype.
    """
    if isinstance(value, ctype_type):
        return value  # Already the correct ctype, return as is.

    if issubclass(ctype_type, ctypes._SimpleCData):
        return ctype_type(value)

    if issubclass(ctype_type, ctypes.Array):
        if not isinstance(value, (list, tuple)):
            raise TypeError("For ctypes arrays, the value must be a list or tuple.")
        if len(value) != ctype_type._length_:
            raise ValueError(f"Array must have exactly {ctype_type._length_} elements.")
        return ctype_type(*[value_to_ctype(v, ctype_type._type_) for v in value])

    if issubclass(ctype_type, ctypes.Structure):
        if not isinstance(value, dict):
            raise TypeError("For ctypes structures, the value must be a dictionary.")
        return dict_to_struct(value, ctype_type)

    raise TypeError(f"Unsupported ctypes type: {ctype_type}")


def ctype_to_bytes(ctype_value):
    """
    Convert a ctypes instance into its raw byte representation.

    Args:
        ctype_value: The ctypes instance to convert.

    Returns:
        bytes: The raw bytes representing the ctypes instance.
    """
    return ctypes.string_at(ctypes.addressof(ctype_value), ctypes.sizeof(ctype_value))


def bytes_to_ctype(byte_data, ctype_type):
    """
    Convert raw bytes into a ctypes instance.

    Args:
        ctype_type: The ctypes type to reconstruct.
        byte_data (bytes): The raw bytes representing the instance.

    Returns:
        A ctypes instance reconstructed from the byte data.
    """
    if not isinstance(byte_data, (bytes, bytearray)):
        raise TypeError("byte_data must be of type bytes or bytearray.")
    if len(byte_data) != ctypes.sizeof(ctype_type):
        raise ValueError(f"byte_data must have exactly {ctypes.sizeof(ctype_type)} bytes.")
    return ctype_type.from_buffer_copy(byte_data)


def value_to_bytes(value, ctype_type):
    return ctype_to_bytes(ctype_value=value_to_ctype(value, ctype_type))


def bytes_to_value(byte_data, ctype_type):
    return ctype_to_value(ctype_value=bytes_to_ctype(byte_data=byte_data, ctype_type=ctype_type), ctype_type=ctype_type)


def STRUCTURE(cls):
    """
    Decorator to simplify and automate the creation of ctypes.Structure classes.

    - Adds automatic inheritance from `ctypes.Structure` if not already inherited.
    - Converts a `FIELDS` attribute (list of tuples or a dictionary) into `_fields_`.

    Usage:
        Define `FIELDS` as a class attribute, either as:
        - A list of tuples: [("field_name", field_type), ...]
        - A dictionary: {"field_name": field_type, ...}

    Raises:
        AttributeError: If `FIELDS` is not defined in the class.
        TypeError: If `FIELDS` is not a valid list or dictionary.
    """
    if not hasattr(cls, "FIELDS"):
        raise AttributeError(f"Class {cls.__name__} must have a 'FIELDS' attribute to use @STRUCTURE.")

    # Check if the class already inherits from ctypes.Structure
    if not issubclass(cls, ctypes.Structure):
        cls = type(cls.__name__, (ctypes.Structure,), dict(cls.__dict__))

    # Convert FIELDS to `_fields_`
    fields = cls.FIELDS
    if isinstance(fields, dict):
        cls._fields_ = list(fields.items())
    elif isinstance(fields, list):
        cls._fields_ = fields
    else:
        raise TypeError(f"'FIELDS' attribute in {cls.__name__} must be a list of tuples or a dictionary.")

    return cls


def struct_to_dataclass(ctypes_instance: ctypes.Structure, dataclass_type: Type) -> Any:
    """
    Recursively converts a ctypes Structure to a dataclass instance. Assumes that the dataclass and the struct have
    fields with the same name.

    Args:
        ctypes_instance: An instance of a ctypes Structure.
        dataclass_type: The top-level dataclass type to map to.

    Returns:
        An instance of the dataclass_type populated with data from the ctypes instance.
    """
    if not is_dataclass(dataclass_type):
        raise ValueError(f"The provided dataclass_type {dataclass_type} is not a dataclass.")

    dataclass_fields = {field.name: field.type for field in fields(dataclass_type)}
    kwargs = {}

    for field_name, field_type in dataclass_fields.items():
        ctypes_value = getattr(ctypes_instance, field_name)

        # If the field type is a dataclass and the ctypes value is a ctypes.Structure,
        # recursively convert.
        if is_dataclass(field_type) and isinstance(ctypes_value, ctypes.Structure):
            kwargs[field_name] = struct_to_dataclass(ctypes_value, field_type)
        elif isinstance(ctypes_value, ctypes.Array):
            # Convert ctypes arrays to Python lists
            kwargs[field_name] = list(ctypes_value)
        else:
            # Direct assignment for other types
            kwargs[field_name] = ctypes_value

    return dataclass_type(**kwargs)


def analyze_ctype_structure(
        struct_type: type,
        print_to_terminal: bool = False,
        print_to_file: bool = True,
        generate_figure: bool = False,
):
    """
    Generates diagnostics for a ctypes.Structure class, including its fields and nested structures.
    Ensures unique nodes for fields with the same name and prevents parents from linking to grandchildren.

    :param struct_type: The ctypes.Structure type to process.
    :param print_to_terminal: If True, prints the field paths to the terminal.
    :param print_to_file: If True, writes the field paths to a .txt file named after the structure.
    :param generate_figure: If True, generates a tree diagram named after the structure.
    """
    if not issubclass(struct_type, ctypes.Structure):
        raise ValueError("The provided type is not a ctypes.Structure.")

    # Define color mapping for types
    type_colors = {
        "Structure": "lightblue",
        "Array": "yellow",
        "simple": "lightgreen",  # Simple ctypes types
    }

    # Mapping to ensure explicit type names are displayed
    explicit_ctypes_names = {
        ctypes.c_uint8: "c_uint8",
        ctypes.c_uint16: "c_uint16",
        ctypes.c_uint32: "c_uint32",
        ctypes.c_uint64: "c_uint64",
        ctypes.c_int8: "c_int8",
        ctypes.c_int16: "c_int16",
        ctypes.c_int32: "c_int32",
        ctypes.c_int64: "c_int64",
        ctypes.c_float: "c_float",
        ctypes.c_double: "c_double",
        ctypes.c_char_p: "c_char_p",
        ctypes.c_void_p: "c_void_p",
        ctypes.c_long: "c_long",
        ctypes.c_ulong: "c_ulong",
        ctypes.c_ubyte: "c_uint8",  # Map internal name to explicit
        ctypes.c_byte: "c_int8",  # Map internal name to explicit
        ctypes.c_short: "c_int16",
        ctypes.c_ushort: "c_uint16",
        ctypes.c_int: "c_int32",
        ctypes.c_uint: "c_uint32",
    }

    def resolve_ctypes_type(field_type):
        """Resolves ctypes types to a readable format."""
        if isinstance(field_type, type):
            if issubclass(field_type, ctypes.Array):
                base_type = explicit_ctypes_names.get(field_type._type_, field_type._type_.__name__)
                return f"{base_type}[{field_type._length_}]"
            elif issubclass(field_type, ctypes.Structure):
                return "Structure"
            return explicit_ctypes_names.get(field_type, field_type.__name__)
        return str(field_type)

    def get_color(field_type):
        """Get the color for a field type."""
        if isinstance(field_type, type):
            if issubclass(field_type, ctypes.Array):
                return type_colors["Array"]
            elif issubclass(field_type, ctypes.Structure):
                return type_colors["Structure"]
            else:
                return type_colors["simple"]
        return type_colors["simple"]

    def get_field_paths_and_structure(struct, prefix=""):
        """Recursively extracts fields and nested structures."""
        paths = []
        structure = []
        for field_name, field_type in struct._fields_:
            full_path = f"{prefix}{field_name}"
            resolved_type = resolve_ctypes_type(field_type)

            paths.append(full_path)  # Add current field's path
            structure.append((prefix, field_name, field_type, resolved_type))

            # If the field type is another structure, process it recursively
            if isinstance(field_type, type) and issubclass(field_type, ctypes.Structure):
                nested_paths, nested_structure = get_field_paths_and_structure(field_type, prefix=f"{full_path}.")
                paths.extend(nested_paths)
                structure.extend(nested_structure)
        return paths, structure

    # Generate field paths and structure
    all_paths, structure = get_field_paths_and_structure(struct_type)

    # Write the paths to the output file if enabled
    struct_name = struct_type.__name__
    if print_to_file:
        txt_file_name = f"{struct_name}.txt"
        with open(txt_file_name, "w") as file:
            file.write(f"Fields and Paths for Structure: {struct_name}\n")
            for path in all_paths:
                file.write(f"{path}\n")

    # Optionally print paths to terminal
    if print_to_terminal:
        print(f"Fields and Paths for Structure: {struct_name}")
        for path in all_paths:
            print(path)

    # Optionally generate a tree diagram
    if generate_figure:
        graph = graphviz.Digraph(format="png")
        graph.attr(rankdir="TB")  # Top-to-Bottom layout
        graph.attr("node", shape="box")

        # Add the root node for the structure
        root_name = struct_type.__name__
        graph.node(root_name, f"{root_name} (Structure)", style="filled", fillcolor=type_colors["Structure"])

        # Recursive function to add nodes and edges
        def add_to_graph(parent, current_prefix, structure):
            for prefix, field_name, field_type, resolved_type in structure:
                # Only connect immediate children to the current parent
                if prefix.rstrip(".") == current_prefix.rstrip("."):
                    # Create a globally unique node ID using the full path
                    node_id = f"{prefix}{field_name}".replace(".", "_")
                    node_label = f"{field_name} ({resolved_type})"
                    color = get_color(field_type)

                    # Add the node to the graph
                    graph.node(node_id, node_label, style="filled", fillcolor=color)
                    graph.edge(parent, node_id)

                    # Recursively add nested structures
                    if isinstance(field_type, type) and issubclass(field_type, ctypes.Structure):
                        nested_structure = [
                            item for item in structure if item[0].startswith(f"{prefix}{field_name}.")
                        ]
                        add_to_graph(node_id, f"{prefix}{field_name}.", nested_structure)

        # Start adding nodes from the root
        add_to_graph(root_name, "", structure)

        # Render the figure with the name of the structure
        graph.render(struct_name, cleanup=True)
