"""
Test that Python software data types match the STM32 firmware C definitions.

Parses C firmware headers and compares every exchanged struct (field names,
field order, field types), enum, and message ID against the Python ctypes
Structures and IntEnums.

This catches drift when firmware structs/enums are modified but the Python
mirrors in robot/lowlevel/ are not updated (or vice versa).

Run:
    cd robots/bilbo/software
    python -m pytest simulation/test_software_firmware_sync.py -v
"""
from __future__ import annotations

import ctypes
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SOFTWARE_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_ROOT = SOFTWARE_ROOT.parent / "firmware" / "firmware"
LIBRARY_ROOT = SOFTWARE_ROOT.parent.parent.parent / "libraries" / "software" / "cpp" / "stm32" / "stm32_core_cpp_lib"


# ---------------------------------------------------------------------------
# C header parsing
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"Header not found: {path}")
    return path.read_text()


def _strip_comments(text: str) -> str:
    """Remove C/C++ comments."""
    # Block comments
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # Line comments
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _extract_struct_body(text: str, struct_name: str) -> str:
    """Extract the body of a C struct, handling nested braces in initializers."""
    pattern = re.compile(
        rf"(?:typedef\s+)?struct\s+{re.escape(struct_name)}\s*\{{",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        pytest.skip(f"Struct {struct_name} not found")
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
        i += 1
    return text[start:i - 1]


def _parse_struct_fields(text: str, struct_name: str) -> list[tuple[str, str]]:
    """Parse a C struct and return [(field_name, c_type_string), ...].

    Handles: float, uint8_t, int8_t, uint16_t, uint32_t, bool,
    nested struct types, and fixed-size arrays like float K[8].
    """
    text = _strip_comments(text)
    body = _extract_struct_body(text, struct_name)

    fields: list[tuple[str, str]] = []
    for line in body.splitlines():
        line = line.strip().rstrip(";").strip()
        # Remove default initializers (including brace-enclosed ones like = { 0 })
        line = re.sub(r"\s*=\s*\{[^}]*\}", "", line)
        line = re.sub(r"\s*=\s*[^,;{}]*", "", line)
        if not line or line.startswith("#"):
            continue
        # Skip C++ method bodies, keywords, and access specifiers
        if any(line.startswith(kw) for kw in (
            "return", "static", "constexpr", "void", "public", "private",
            "protected", "friend", "virtual", "inline", "explicit",
        )):
            continue
        # Skip lines with parentheses (function declarations/calls)
        if "(" in line or ")" in line:
            continue

        # Array: "float K[8]" or "path_point_t points[MACRO_NAME]"
        arr_match = re.match(r"(\w[\w\s*]*?)\s+(\w+)\[(\w+)\]", line)
        if arr_match:
            c_type = arr_match.group(1).strip()
            name = arr_match.group(2)
            count = arr_match.group(3)
            fields.append((name, f"{c_type}[{count}]"))
            continue

        # Regular: "type name" or "struct_type name"
        parts = line.split()
        if len(parts) >= 2:
            name = parts[-1].lstrip("*")
            c_type = " ".join(parts[:-1])
            if name and name[0].isalpha():
                fields.append((name, c_type))

    return fields


def _parse_defines(path: Path, prefix: str) -> dict[str, int]:
    """Extract #define NAME VALUE pairs."""
    defines: dict[str, int] = {}
    pattern = re.compile(r"^\s*#define\s+(\w+)\s+(0x[0-9A-Fa-f]+|\d+)")
    for line in _read_text(path).splitlines():
        m = pattern.match(line)
        if m and m.group(1).startswith(prefix):
            defines[m.group(1)] = int(m.group(2), 0)
    return defines


def _parse_enum_members(text: str, enum_name: str) -> dict[str, int]:
    """Parse C++ enum class members."""
    text = _strip_comments(text)
    pattern = re.compile(
        rf"enum\s+class\s+{re.escape(enum_name)}\s*:\s*\w+\s*\{{([^}}]+)\}}",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        pytest.skip(f"Enum {enum_name} not found")
    body = m.group(1)

    members: dict[str, int] = {}
    for entry in body.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" in entry:
            name, val = entry.split("=", 1)
            members[name.strip()] = int(val.strip(), 0)
    return members


# ---------------------------------------------------------------------------
# C type → ctypes type mapping
# ---------------------------------------------------------------------------

# Map from C type strings to ctypes type objects
C_TYPE_MAP: dict[str, type] = {
    "float": ctypes.c_float,
    "uint8_t": ctypes.c_uint8,
    "int8_t": ctypes.c_int8,
    "uint16_t": ctypes.c_uint16,
    "int16_t": ctypes.c_int16,
    "uint32_t": ctypes.c_uint32,
    "int32_t": ctypes.c_int32,
    "bool": ctypes.c_bool,
}


def _resolve_ctypes_type(c_type_str: str) -> type | None:
    """Resolve a C type string to its expected ctypes type.

    Returns None for nested struct types or macro-sized arrays.
    """
    # Array: "float[8]" → c_float * 8, "type[MACRO]" → None (skip)
    arr_match = re.match(r"(\w+)\[(\w+)\]", c_type_str)
    if arr_match:
        base = C_TYPE_MAP.get(arr_match.group(1))
        size_str = arr_match.group(2)
        if base and size_str.isdigit():
            return base * int(size_str)
        return None  # Macro-sized or nested struct array

    return C_TYPE_MAP.get(c_type_str)


def _get_ctypes_field_type(py_struct: type, field_name: str) -> type | None:
    """Get the ctypes type for a field in a ctypes.Structure."""
    for name, ftype in py_struct._fields_:
        if name == field_name:
            return ftype
    return None


# ---------------------------------------------------------------------------
# Struct comparison helper
# ---------------------------------------------------------------------------

def _compare_struct(c_header_text: str, c_struct_name: str, py_struct: type):
    """Compare a C struct against a Python ctypes Structure.

    Checks: field names, field order, and field types (where mappable).
    """
    c_fields = _parse_struct_fields(c_header_text, c_struct_name)
    py_fields = [(name, ftype) for name, ftype in py_struct._fields_]

    c_names = [name for name, _ in c_fields]
    py_names = [name for name, _ in py_fields]

    # 1. Field names must match (array fields are already just the name)
    errors = []
    if c_names != py_names:
        only_in_c = set(c_names) - set(py_names)
        only_in_py = set(py_names) - set(c_names)
        if only_in_c:
            errors.append(f"  Fields only in firmware: {only_in_c}")
        if only_in_py:
            errors.append(f"  Fields only in Python: {only_in_py}")
        if not only_in_c and not only_in_py:
            errors.append(f"  Field ORDER differs:")
            errors.append(f"    Firmware: {c_names}")
            errors.append(f"    Python:   {py_names}")

    # 2. Field types (for primitive types)
    for c_name, c_type_str in c_fields:
        expected_type = _resolve_ctypes_type(c_type_str)
        if expected_type is None:
            continue  # Nested struct or unknown - skip type check
        actual_type = _get_ctypes_field_type(py_struct, c_name)
        if actual_type is None:
            continue  # Field missing (already caught above)
        if actual_type != expected_type:
            errors.append(
                f"  Type mismatch for '{c_name}': "
                f"firmware={c_type_str}, python={actual_type.__name__}"
            )

    assert not errors, (
        f"Struct mismatch: {c_struct_name} vs {py_struct.__name__}:\n"
        + "\n".join(errors)
    )


# ===========================================================================
# Test fixtures
# ===========================================================================

@pytest.fixture(scope="module")
def fw_headers() -> dict[str, str]:
    """Load and cache all firmware header texts."""
    if not FIRMWARE_ROOT.exists():
        pytest.skip("Firmware source not available")

    headers = {}
    for path in FIRMWARE_ROOT.rglob("*.h"):
        # Skip archive directory
        if "archive" in path.parts:
            continue
        rel = str(path.relative_to(FIRMWARE_ROOT))
        headers[rel] = _read_text(path)
    return headers


@pytest.fixture(scope="module")
def lib_headers() -> dict[str, str]:
    """Load library headers (PID, feedforward)."""
    headers = {}
    if LIBRARY_ROOT.exists():
        for path in LIBRARY_ROOT.rglob("*.h"):
            rel = str(path.relative_to(LIBRARY_ROOT))
            headers[rel] = _read_text(path)
    return headers


def _find_header(headers: dict[str, str], struct_name: str) -> str:
    """Find which header contains a given struct definition."""
    for rel, text in headers.items():
        if re.search(rf"struct\s+{re.escape(struct_name)}\s*\{{", _strip_comments(text)):
            return text
    pytest.skip(f"Struct {struct_name} not found in any header")


# ===========================================================================
# 1. Control structs (bilbo_control.h, bilbo_balancing_control.h)
# ===========================================================================

class TestControlStructs:

    def test_control_input_ext(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_control_input_ext_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_control_input_ext_t"),
            "bilbo_control_input_ext_t", bilbo_control_input_ext_t,
        )

    def test_control_output(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_control_output_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_control_output_t"),
            "bilbo_control_output_t", bilbo_control_output_t,
        )

    def test_balancing_control_config(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_balancing_control_config_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_balancing_control_config_t"),
            "bilbo_balancing_control_config_t", bilbo_balancing_control_config_t,
        )

    def test_balancing_control_input(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_balancing_control_input_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_balancing_control_input_t"),
            "bilbo_balancing_control_input_t", bilbo_balancing_control_input_t,
        )

    def test_balancing_control_output(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_balancing_control_output_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_balancing_control_output_t"),
            "bilbo_balancing_control_output_t", bilbo_balancing_control_output_t,
        )

    def test_control_data(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_ll_control_data_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_control_data_t"),
            "bilbo_control_data_t", bilbo_ll_control_data_t,
        )

    def test_control_config(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_control_config_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_control_config_t"),
            "bilbo_control_config_t", bilbo_control_config_t,
        )

    def test_control_event_message_data(self, fw_headers):
        from robot.lowlevel.stm32_control import control_event_message_data_t
        _compare_struct(
            _find_header(fw_headers, "control_event_message_data_t"),
            "control_event_message_data_t", control_event_message_data_t,
        )


# ===========================================================================
# 2. VIC / TIC / PSI structs (bilbo_vic_tic.h)
# ===========================================================================

class TestVicTicPsiStructs:

    def test_tic_config(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_tic_config_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_tic_config_t"),
            "bilbo_tic_config_t", bilbo_tic_config_t,
        )

    def test_vic_config(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_vic_config_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_vic_config_t"),
            "bilbo_vic_config_t", bilbo_vic_config_t,
        )

    def test_psi_config(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_psi_config_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_psi_config_t"),
            "bilbo_psi_config_t", bilbo_psi_config_t,
        )


# ===========================================================================
# 3. Velocity control structs (bilbo_velocity_control.h)
# ===========================================================================

class TestVelocityControlStructs:

    def test_velocity_control_config(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_velocity_control_config_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_velocity_control_config_t"),
            "bilbo_velocity_control_config_t", bilbo_velocity_control_config_t,
        )

    def test_velocity_control_command(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_velocity_control_command_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_velocity_control_command_t"),
            "bilbo_velocity_control_command_t", bilbo_velocity_control_command_t,
        )

    def test_velocity_control_output(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_velocity_control_output_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_velocity_control_output_t"),
            "bilbo_velocity_control_output_t", bilbo_velocity_control_output_t,
        )

    def test_velocity_control_sample(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_velocity_control_sample_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_velocity_control_sample_t"),
            "bilbo_velocity_control_sample_t", bilbo_velocity_control_sample_t,
        )


# ===========================================================================
# 4. PID and Feedforward structs (library headers)
# ===========================================================================

class TestLibraryStructs:

    def test_pid_control_config(self, lib_headers):
        if not lib_headers:
            pytest.skip("Library headers not available")
        from robot.lowlevel.stm32_control import pid_control_config_t
        _compare_struct(
            _find_header(lib_headers, "pid_control_config_t"),
            "pid_control_config_t", pid_control_config_t,
        )

    def test_feedforward_config(self, lib_headers):
        if not lib_headers:
            pytest.skip("Library headers not available")
        from robot.lowlevel.stm32_control import feedforward_config_t
        _compare_struct(
            _find_header(lib_headers, "feedforward_config_t"),
            "feedforward_config_t", feedforward_config_t,
        )


# ===========================================================================
# 5. Position control structs (bilbo_position_control.h)
# ===========================================================================

class TestPositionControlStructs:

    def test_path_point(self, fw_headers):
        from robot.lowlevel.stm32_control import path_point_t
        _compare_struct(
            _find_header(fw_headers, "path_point_t"),
            "path_point_t", path_point_t,
        )

    def test_path_points_batch(self, fw_headers):
        from robot.lowlevel.stm32_control import path_points_batch_t
        _compare_struct(
            _find_header(fw_headers, "path_points_batch_t"),
            "path_points_batch_t", path_points_batch_t,
        )

    def test_path_start_cmd(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_path_start_cmd_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_path_start_cmd_t"),
            "bilbo_path_start_cmd_t", bilbo_path_start_cmd_t,
        )

    def test_turn_to_heading_command(self, fw_headers):
        from robot.lowlevel.stm32_control import turn_to_heading_command_t
        _compare_struct(
            _find_header(fw_headers, "turn_to_heading_command_t"),
            "turn_to_heading_command_t", turn_to_heading_command_t,
        )

    def test_move_to_point_command(self, fw_headers):
        from robot.lowlevel.stm32_control import move_to_point_command_t
        _compare_struct(
            _find_header(fw_headers, "move_to_point_command_t"),
            "move_to_point_command_t", move_to_point_command_t,
        )

    def test_position_control_output(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_position_control_output_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_position_control_output_t"),
            "bilbo_position_control_output_t", bilbo_position_control_output_t,
        )

    def test_position_control_config(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_position_control_config_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_position_control_config_t"),
            "bilbo_position_control_config_t", bilbo_position_control_config_t,
        )

    def test_position_control_data(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_position_control_data_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_position_control_data_t"),
            "bilbo_position_control_data_t", bilbo_position_control_data_t,
        )

    def test_position_control_event_data(self, fw_headers):
        from robot.lowlevel.stm32_control import position_control_event_data_t
        _compare_struct(
            _find_header(fw_headers, "position_control_event_data_t"),
            "position_control_event_data_t", position_control_event_data_t,
        )

    def test_position_state(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_position_state_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_position_state_t"),
            "bilbo_position_state_t", bilbo_position_state_t,
        )


# ===========================================================================
# 6. Estimation structs (bilbo_estimation.h)
# ===========================================================================

class TestEstimationStructs:

    def test_estimation_state(self, fw_headers):
        from robot.lowlevel.stm32_sample import bilbo_ll_estimation_data_struct
        _compare_struct(
            _find_header(fw_headers, "bilbo_estimation_state_t"),
            "bilbo_estimation_state_t", bilbo_ll_estimation_data_struct,
        )

    def test_logging_estimation(self, fw_headers):
        from robot.lowlevel.stm32_sample import bilbo_ll_sample_estimation_struct
        _compare_struct(
            _find_header(fw_headers, "bilbo_logging_estimation_t"),
            "bilbo_logging_estimation_t", bilbo_ll_sample_estimation_struct,
        )

    def test_velocity_lpf_config(self, fw_headers):
        from robot.lowlevel.stm32_sample import velocity_lowpass_filter_config_t
        _compare_struct(
            _find_header(fw_headers, "velocity_lowpass_filter_config_t"),
            "velocity_lowpass_filter_config_t", velocity_lowpass_filter_config_t,
        )

    def test_theta_dot_lpf_config(self, fw_headers):
        from robot.lowlevel.stm32_sample import theta_dot_lowpass_filter_config_t
        _compare_struct(
            _find_header(fw_headers, "theta_dot_lowpass_filter_config_t"),
            "theta_dot_lowpass_filter_config_t", theta_dot_lowpass_filter_config_t,
        )

    def test_psi_dot_lpf_config(self, fw_headers):
        from robot.lowlevel.stm32_sample import psi_dot_lowpass_filter_config_t
        _compare_struct(
            _find_header(fw_headers, "psi_dot_lowpass_filter_config_t"),
            "psi_dot_lowpass_filter_config_t", psi_dot_lowpass_filter_config_t,
        )

    def test_position_ekf_config(self, fw_headers):
        from robot.lowlevel.stm32_sample import position_ekf_config_t
        _compare_struct(
            _find_header(fw_headers, "position_ekf_config_t"),
            "position_ekf_config_t", position_ekf_config_t,
        )

    def test_estimation_config(self, fw_headers):
        from robot.lowlevel.stm32_sample import bilbo_estimation_config_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_estimation_config_t"),
            "bilbo_estimation_config_t", bilbo_estimation_config_t,
        )


# ===========================================================================
# 7. Sample / logging structs (bilbo_logging.h, bilbo_sensors.h, etc.)
# ===========================================================================

class TestSampleStructs:

    def test_sensor_data(self, fw_headers):
        from robot.lowlevel.stm32_sample import bilbo_ll_sensor_data_struct
        _compare_struct(
            _find_header(fw_headers, "bilbo_sensors_data_t"),
            "bilbo_sensors_data_t", bilbo_ll_sensor_data_struct,
        )

    def test_logging_drive(self, fw_headers):
        from robot.lowlevel.stm32_sample import bilbo_ll_sample_drive_struct
        _compare_struct(
            _find_header(fw_headers, "bilbo_logging_drive_t"),
            "bilbo_logging_drive_t", bilbo_ll_sample_drive_struct,
        )

    def test_logging_sample(self, fw_headers):
        from robot.lowlevel.stm32_sample import bilbo_ll_sample_struct
        _compare_struct(
            _find_header(fw_headers, "bilbo_logging_sample_t"),
            "bilbo_logging_sample_t", bilbo_ll_sample_struct,
        )

    def test_debug_sample(self, fw_headers):
        from robot.lowlevel.stm32_sample import bilbo_ll_sample_debug_struct
        _compare_struct(
            _find_header(fw_headers, "bilbo_debug_sample_t"),
            "bilbo_debug_sample_t", bilbo_ll_sample_debug_struct,
        )

    def test_error_log_entry(self, fw_headers):
        from robot.lowlevel.stm32_errors import bilbo_ll_log_entry_t
        _compare_struct(
            _find_header(fw_headers, "bilbo_error_log_entry_t"),
            "bilbo_error_log_entry_t", bilbo_ll_log_entry_t,
        )


# ===========================================================================
# 8. Sequencer structs (bilbo_sequencer.h)
# ===========================================================================

class TestSequencerStructs:

    def test_sequencer_sample(self, fw_headers):
        from robot.lowlevel.stm32_sample import bilbo_ll_sample_sequence_struct
        _compare_struct(
            _find_header(fw_headers, "bilbo_sequencer_sample_t"),
            "bilbo_sequencer_sample_t", bilbo_ll_sample_sequence_struct,
        )


# ===========================================================================
# 9. All enums
# ===========================================================================

class TestAllEnums:

    def _check(self, fw_headers, header_rel: str, c_name: str, py_enum):
        text = fw_headers.get(header_rel)
        if text is None:
            pytest.skip(f"Header {header_rel} not found")
        fw_members = _parse_enum_members(text, c_name)
        py_members = {m.name: m.value for m in py_enum}

        errors = []
        for name, val in fw_members.items():
            if name not in py_members:
                errors.append(f"  Missing in Python: {name} = {val}")
            elif py_members[name] != val:
                errors.append(f"  Value mismatch: {name} firmware={val} python={py_members[name]}")

        # Check for extra Python members not in firmware
        for name in py_members:
            if name not in fw_members:
                errors.append(f"  Extra in Python (not in firmware): {name} = {py_members[name]}")

        assert not errors, f"Enum {c_name} mismatch:\n" + "\n".join(errors)

    def test_control_mode(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_control_mode_t
        self._check(fw_headers, "control/bilbo_control.h",
                     "bilbo_control_mode_t", bilbo_control_mode_t)

    def test_control_status(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_control_status_t
        self._check(fw_headers, "control/bilbo_control.h",
                     "bilbo_control_status_t", bilbo_control_status_t)

    def test_control_event(self, fw_headers):
        from robot.lowlevel.stm32_control import control_event_t
        self._check(fw_headers, "control/bilbo_control.h",
                     "control_event_t", control_event_t)

    def test_balancing_control_mode(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_balancing_control_mode_t
        self._check(fw_headers, "control/bilbo_balancing_control.h",
                     "bilbo_balancing_control_mode_t", bilbo_balancing_control_mode_t)

    def test_balancing_control_status(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_balancing_control_status_t
        self._check(fw_headers, "control/bilbo_balancing_control.h",
                     "bilbo_balancing_control_status_t", bilbo_balancing_control_status_t)

    def test_position_control_mode(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_position_control_mode_t
        self._check(fw_headers, "control/bilbo_position_control.h",
                     "bilbo_position_control_mode_t", bilbo_position_control_mode_t)

    def test_path_state(self, fw_headers):
        from robot.lowlevel.stm32_control import bilbo_path_state_t
        self._check(fw_headers, "control/bilbo_position_control.h",
                     "bilbo_path_state_t", bilbo_path_state_t)

    def test_position_control_event(self, fw_headers):
        from robot.lowlevel.stm32_control import position_control_event_t
        self._check(fw_headers, "control/bilbo_position_control.h",
                     "position_control_event_t", position_control_event_t)


# ===========================================================================
# 10. Register addresses
# ===========================================================================

class TestRegisterAddresses:

    def test_all_firmware_registers_in_python(self, fw_headers):
        fw_defines = _parse_defines(
            FIRMWARE_ROOT / "firmware_addresses.h", prefix="REG_ADDRESS"
        )
        from robot.lowlevel.stm32_addresses import (
            BILBO_SystemAddresses, BILBO_ControlAddresses,
            BILBO_PositionControlAddresses, BILBO_SequencerAddresses,
            BILBO_EstimationAddresses,
        )
        py_values = set()
        for enum_cls in (BILBO_SystemAddresses, BILBO_ControlAddresses,
                         BILBO_PositionControlAddresses, BILBO_SequencerAddresses,
                         BILBO_EstimationAddresses):
            for member in enum_cls:
                py_values.add(int(member.value))

        missing = [f"  {n} = 0x{v:02X}" for n, v in sorted(fw_defines.items()) if v not in py_values]
        assert not missing, "Firmware registers missing from Python:\n" + "\n".join(missing)

    def test_no_extra_python_registers(self, fw_headers):
        fw_defines = _parse_defines(
            FIRMWARE_ROOT / "firmware_addresses.h", prefix="REG_ADDRESS"
        )
        fw_values = set(fw_defines.values())

        from robot.lowlevel.stm32_addresses import (
            BILBO_SystemAddresses, BILBO_ControlAddresses,
            BILBO_PositionControlAddresses, BILBO_SequencerAddresses,
            BILBO_EstimationAddresses,
        )
        extra = []
        for enum_cls in (BILBO_SystemAddresses, BILBO_ControlAddresses,
                         BILBO_PositionControlAddresses, BILBO_SequencerAddresses,
                         BILBO_EstimationAddresses):
            for member in enum_cls:
                if int(member.value) not in fw_values:
                    extra.append(f"  {enum_cls.__name__}.{member.name} = 0x{member.value:02X}")

        assert not extra, "Python registers not in firmware:\n" + "\n".join(extra)


# ===========================================================================
# 11. Message IDs
# ===========================================================================

class TestMessageIDs:

    def test_all_message_ids(self):
        fw_messages = _parse_defines(
            FIRMWARE_ROOT / "firmware_addresses.h", prefix="BILBO_MESSAGE"
        )
        from robot.lowlevel import stm32_messages as msgs

        py_map = {
            "BILBO_MESSAGE_PRINT": msgs.BILBO_LL_MESSAGE_PRINT,
            "BILBO_MESSAGE_ERROR": msgs.BILBO_LL_MESSAGE_ERROR,
            "BILBO_MESSAGE_SEQUENCER_EVENT": msgs.BILBO_LL_MESSAGE_SEQUENCER_EVENT,
            "BILBO_MESSAGE_CONTROL_EVENT": msgs.BILBO_LL_MESSAGE_CONTROL_EVENT,
            "BILBO_MESSAGE_WAYPOINT_EVENT": msgs.BILBO_LL_MESSAGE_WAYPOINT_EVENT,
            "BILBO_MESSAGE_POSITION_CONTROL_EVENT": msgs.BILBO_LL_MESSAGE_POSITION_CONTROL_EVENT,
            "BILBO_MESSAGE_DRIVE_EVENT": msgs.BILBO_LL_MESSAGE_DRIVE_EVENT,
        }

        errors = []
        for fw_name, fw_val in fw_messages.items():
            if fw_name in py_map:
                if py_map[fw_name] != fw_val:
                    errors.append(
                        f"  {fw_name}: firmware=0x{fw_val:02X}, python=0x{py_map[fw_name]:02X}"
                    )
            else:
                errors.append(f"  {fw_name} = 0x{fw_val:02X} not mapped in Python")

        assert not errors, "Message ID mismatches:\n" + "\n".join(errors)


# ===========================================================================
# 12. Dataclass ↔ ctypes consistency (Python internal)
# ===========================================================================

class TestDataclassCtypesConsistency:
    """Verify that Python dataclasses have the same fields as their ctypes counterparts."""

    @staticmethod
    def _check_pair(dc_cls, ct_cls):
        import dataclasses as dc
        dc_names = [f.name for f in dc.fields(dc_cls)]
        ct_names = [name for name, _ in ct_cls._fields_]
        assert dc_names == ct_names, (
            f"Field mismatch between {dc_cls.__name__} and {ct_cls.__name__}:\n"
            f"  Dataclass: {dc_names}\n"
            f"  Ctypes:    {ct_names}"
        )

    def test_sample_top_level(self):
        from robot.lowlevel.stm32_sample import BILBO_LL_Sample, bilbo_ll_sample_struct
        self._check_pair(BILBO_LL_Sample, bilbo_ll_sample_struct)

    def test_control_data(self):
        from robot.lowlevel.stm32_control import bilbo_ll_control_data, bilbo_ll_control_data_t
        self._check_pair(bilbo_ll_control_data, bilbo_ll_control_data_t)

    def test_estimation_data(self):
        from robot.lowlevel.stm32_sample import BILBO_LL_Estimation_Data, bilbo_ll_estimation_data_struct
        self._check_pair(BILBO_LL_Estimation_Data, bilbo_ll_estimation_data_struct)

    def test_sensor_data(self):
        from robot.lowlevel.stm32_sample import BILBO_LL_Sensor_Data, bilbo_ll_sensor_data_struct
        self._check_pair(BILBO_LL_Sensor_Data, bilbo_ll_sensor_data_struct)

    def test_drive_data(self):
        from robot.lowlevel.stm32_sample import BILBO_LL_Sample_Drive, bilbo_ll_sample_drive_struct
        self._check_pair(BILBO_LL_Sample_Drive, bilbo_ll_sample_drive_struct)

    def test_sequence_data(self):
        from robot.lowlevel.stm32_sample import BILBO_LL_Sample_Sequence, bilbo_ll_sample_sequence_struct
        self._check_pair(BILBO_LL_Sample_Sequence, bilbo_ll_sample_sequence_struct)

    def test_position_control_data(self):
        from robot.lowlevel.stm32_control import bilbo_position_control_data, bilbo_position_control_data_t
        self._check_pair(bilbo_position_control_data, bilbo_position_control_data_t)

    def test_velocity_command(self):
        from robot.lowlevel.stm32_control import bilbo_velocity_control_command, bilbo_velocity_control_command_t
        self._check_pair(bilbo_velocity_control_command, bilbo_velocity_control_command_t)

    def test_velocity_output(self):
        from robot.lowlevel.stm32_control import bilbo_velocity_control_output, bilbo_velocity_control_output_t
        self._check_pair(bilbo_velocity_control_output, bilbo_velocity_control_output_t)

    def test_control_config(self):
        from robot.lowlevel.stm32_control import bilbo_control_config, bilbo_control_config_t
        self._check_pair(bilbo_control_config, bilbo_control_config_t)


# ===========================================================================
# 13. UART message buffer size constraints
# ===========================================================================

# The UART TX buffer is 128 bytes total. The serial protocol uses 13 bytes
# of overhead (header, tick, cmd, addresses, flag, len, crc), leaving
# 115 bytes for the payload. Every struct sent or received via a register
# operation (read/write/execute) or as an event message must fit.
UART_TX_BUF_SIZE = 128
SERIAL_PROTOCOL_OVERHEAD = 13
MAX_UART_PAYLOAD = UART_TX_BUF_SIZE - SERIAL_PROTOCOL_OVERHEAD  # 115

# Structs that are known to exceed the buffer and are handled specially
# (e.g. bilbo_control_config_t is never actually sent as a single UART message;
# the firmware comment says "Discouraged to use over Serial").
UART_SIZE_KNOWN_EXCEPTIONS = {"bilbo_control_config_t"}

# Map C type names (as they appear in firmware_registers.cpp) to Python ctypes.
# Primitives and fixed-size arrays are resolved inline; struct types are
# imported from the Python lowlevel modules.
_PRIMITIVE_SIZES: dict[str, int] = {
    "void": 0,
    "bool": 1,
    "uint8_t": 1,
    "int8_t": 1,
    "uint16_t": 2,
    "int16_t": 2,
    "uint32_t": 4,
    "int32_t": 4,
    "float": 4,
}


def _parse_register_entries(cpp_path: Path) -> list[tuple[str, str, str, str]]:
    """Parse firmware_registers.cpp and return register entry type pairs.

    Returns list of (var_name, output_type, input_type, address_define).
    """
    text = _read_text(cpp_path)
    text = _strip_comments(text)
    # Match: core_utils_RegisterEntry<output, input> name(&register_map, ADDRESS, ...);
    pattern = re.compile(
        r"core_utils_RegisterEntry\s*<\s*"
        r"([^,>]+?)"       # output type
        r"\s*,\s*"
        r"([^,>]+?)"       # input type
        r"\s*>\s+"
        r"(\w+)"           # variable name
        r"\s*\(\s*"
        r"&register_map\s*,\s*"
        r"(\w+)"           # address define
    )
    entries = []
    for m in pattern.finditer(text):
        out_type = m.group(1).strip()
        in_type = m.group(2).strip()
        var_name = m.group(3).strip()
        addr_define = m.group(4).strip()
        entries.append((var_name, out_type, in_type, addr_define))
    return entries


# Firmware-only types that don't need Python ctypes mirrors.
# These are hardware-specific (buzzer, LEDs) or small enums/structs
# that never appear in the Python control data path.
# Values are their known sizes in bytes (from firmware headers).
_FIRMWARE_ONLY_SIZES: dict[str, int] = {
    "bilbo_firmware_state_t": 1,       # enum (uint8)
    "bilbo_firmware_revision_t": 4,    # struct {uint8 major, minor, patch, board}
    "bilbo_control_mode_t": 1,         # enum class: uint8_t
    "bilbo_path_state_t": 1,           # enum class: uint8_t
    "bilbo_sequencer_sequence_data_t": 32,  # struct with sequence metadata
    "buzzer_beep_struct_t": 8,         # struct {uint16 freq, uint16 duration, ...}
    "rgb_color_struct_t": 4,           # struct {uint8 id, r, g, b}
    "external_led_colors_struct_t": 48, # array of LED colors
}


def _c_type_size(c_type_name: str) -> int | None:
    """Return the size in bytes for a C type, or None if unknown.

    Handles primitives, fixed-size arrays like 'float[8]', struct types
    from Python ctypes modules, and known firmware-only types.
    """
    c_type_name = c_type_name.strip()
    if c_type_name in _PRIMITIVE_SIZES:
        return _PRIMITIVE_SIZES[c_type_name]

    # Fixed-size array: "float[8]"
    arr = re.match(r"(\w+)\[(\d+)\]", c_type_name)
    if arr:
        base_size = _PRIMITIVE_SIZES.get(arr.group(1))
        if base_size is not None:
            return base_size * int(arr.group(2))

    # Try importing as a ctypes struct from the Python lowlevel modules
    for module_name in ("robot.lowlevel.stm32_control", "robot.lowlevel.stm32_sample",
                        "robot.lowlevel.stm32_errors"):
        try:
            import importlib
            mod = importlib.import_module(module_name)
            cls = getattr(mod, c_type_name, None)
            if cls is not None and hasattr(cls, '_fields_'):
                return ctypes.sizeof(cls)
        except ImportError:
            continue

    # Firmware-only types (no Python mirror needed)
    if c_type_name in _FIRMWARE_ONLY_SIZES:
        return _FIRMWARE_ONLY_SIZES[c_type_name]

    return None


def _get_uart_register_payloads() -> list[tuple[str, str, str, int]]:
    """Return (addr_define, direction, c_type, size) for every non-void register payload."""
    cpp_path = FIRMWARE_ROOT / "firmware_registers.cpp"
    if not cpp_path.exists():
        pytest.skip("firmware_registers.cpp not found")

    entries = _parse_register_entries(cpp_path)
    payloads = []
    for var_name, out_type, in_type, addr_define in entries:
        for direction, c_type in [("output", out_type), ("input", in_type)]:
            size = _c_type_size(c_type)
            if size is not None and size > 0:
                payloads.append((addr_define, direction, c_type, size))
    return payloads


class TestUartPayloadSize:
    """Auto-parsed from firmware_registers.cpp: every register payload must
    fit in the 128-byte UART buffer (115 bytes after protocol overhead).

    New register entries are automatically picked up — no manual test
    additions needed.
    """

    @pytest.fixture(scope="class")
    def register_payloads(self):
        return _get_uart_register_payloads()

    def test_all_register_payloads_fit(self, register_payloads):
        """Every register input/output payload must fit in the UART buffer."""
        failures = []
        for addr, direction, c_type, size in register_payloads:
            if c_type in UART_SIZE_KNOWN_EXCEPTIONS:
                continue
            if size > MAX_UART_PAYLOAD:
                failures.append(
                    f"  {addr} {direction} {c_type}: {size} bytes"
                )
        assert not failures, (
            f"Register payloads exceeding UART limit ({MAX_UART_PAYLOAD} bytes):\n"
            + "\n".join(failures)
        )

    def test_known_exceptions_are_actually_oversized(self, register_payloads):
        """Verify that known exceptions really do exceed the limit.
        If they've been fixed, remove them from UART_SIZE_KNOWN_EXCEPTIONS."""
        for addr, direction, c_type, size in register_payloads:
            if c_type in UART_SIZE_KNOWN_EXCEPTIONS:
                assert size > MAX_UART_PAYLOAD, (
                    f"{c_type} ({size} bytes) no longer exceeds the UART limit — "
                    f"remove it from UART_SIZE_KNOWN_EXCEPTIONS"
                )

    def test_no_unknown_types(self, register_payloads):
        """Ensure the parser could resolve all register entry types.
        If this fails, a new struct type needs a Python ctypes mirror."""
        cpp_path = FIRMWARE_ROOT / "firmware_registers.cpp"
        entries = _parse_register_entries(cpp_path)
        unknown = set()
        for var_name, out_type, in_type, addr_define in entries:
            for c_type in (out_type, in_type):
                if _c_type_size(c_type.strip()) is None:
                    unknown.add(c_type.strip())
        assert not unknown, (
            f"Could not resolve size for C types (missing Python ctypes mirror?):\n"
            + "\n".join(f"  {t}" for t in sorted(unknown))
        )

    # --- Event message payloads (sent FROM firmware as MSG_EVENT) ---

    def test_event_control(self):
        """BILBO_MESSAGE_CONTROL_EVENT: control_event_message_data_t"""
        from robot.lowlevel.stm32_control import control_event_message_data_t
        size = ctypes.sizeof(control_event_message_data_t)
        assert size <= MAX_UART_PAYLOAD, (
            f"control_event_message_data_t is {size} bytes, max UART payload is {MAX_UART_PAYLOAD}"
        )

    def test_event_position_control(self):
        """BILBO_MESSAGE_POSITION_CONTROL_EVENT: position_control_event_data_t"""
        from robot.lowlevel.stm32_control import position_control_event_data_t
        size = ctypes.sizeof(position_control_event_data_t)
        assert size <= MAX_UART_PAYLOAD, (
            f"position_control_event_data_t is {size} bytes, max UART payload is {MAX_UART_PAYLOAD}"
        )
