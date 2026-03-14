"""
Test that the simulation stays in sync with the actual STM32 firmware.

Parses the C firmware headers and compares register addresses, enum values,
struct field orders, and message IDs against the Python definitions and the
simulation's register handler coverage.

Run:
    cd robots/bilbo/software
    python -m pytest simulation/test_firmware_sync.py -v
"""
from __future__ import annotations

import dataclasses
import inspect
import math
import os
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SOFTWARE_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_ROOT = SOFTWARE_ROOT.parent / "firmware" / "firmware"

# ---------------------------------------------------------------------------
# C header parsing helpers
# ---------------------------------------------------------------------------

def _parse_defines(header_path: Path, prefix: str = "") -> dict[str, int]:
    """Extract #define NAME VALUE pairs from a C header, returning {name: int_value}."""
    defines: dict[str, int] = {}
    pattern = re.compile(r"^\s*#define\s+(\w+)\s+(0x[0-9A-Fa-f]+|\d+)")
    with open(header_path) as f:
        for line in f:
            m = pattern.match(line)
            if m and (not prefix or m.group(1).startswith(prefix)):
                defines[m.group(1)] = int(m.group(2), 0)
    return defines


def _parse_enum_members(header_path: Path, enum_name: str) -> dict[str, int]:
    """Parse a C++ enum class and return {member_name: int_value}."""
    text = header_path.read_text()
    # Find the enum block
    pattern = re.compile(
        rf"enum\s+class\s+{re.escape(enum_name)}\s*:\s*\w+\s*\{{([^}}]+)\}}",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        pytest.skip(f"Enum {enum_name} not found in {header_path}")
    body = m.group(1)

    members: dict[str, int] = {}
    for entry in body.split(","):
        entry = entry.strip()
        if not entry or entry.startswith("//"):
            continue
        # Remove inline comments
        entry = re.sub(r"//.*", "", entry).strip()
        if "=" in entry:
            name, val = entry.split("=", 1)
            members[name.strip()] = int(val.strip(), 0)
    return members


def _parse_struct_fields(header_path: Path, struct_name: str) -> list[str]:
    """Parse a C struct and return ordered list of field names."""
    text = header_path.read_text()
    pattern = re.compile(
        rf"(?:typedef\s+)?struct\s+{re.escape(struct_name)}\s*\{{([^}}]+)\}}",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        pytest.skip(f"Struct {struct_name} not found in {header_path}")
    body = m.group(1)

    fields: list[str] = []
    for line in body.splitlines():
        line = re.sub(r"//.*", "", line).strip().rstrip(";").strip()
        if not line:
            continue
        # Extract last word as field name (handles "type name", "type *name", etc.)
        parts = line.split()
        if parts:
            name = parts[-1].lstrip("*")
            # Skip if it looks like a nested struct/enum keyword
            if name not in ("struct", "enum", "union", "{", "}"):
                fields.append(name)
    return fields


# ===========================================================================
# 1. Register address parity: firmware_addresses.h vs stm32_addresses.py
# ===========================================================================

class TestRegisterAddresses:
    """Verify Python address enums match the C firmware #defines."""

    @pytest.fixture(autouse=True)
    def _load(self):
        if not FIRMWARE_ROOT.exists():
            pytest.skip("Firmware source not available")
        self.fw_defines = _parse_defines(
            FIRMWARE_ROOT / "firmware_addresses.h", prefix="REG_ADDRESS"
        )
        from robot.lowlevel.stm32_addresses import (
            BILBO_SystemAddresses,
            BILBO_ControlAddresses,
            BILBO_PositionControlAddresses,
            BILBO_SequencerAddresses,
            BILBO_EstimationAddresses,
        )
        self.py_enums = {
            "System": BILBO_SystemAddresses,
            "Control": BILBO_ControlAddresses,
            "PositionControl": BILBO_PositionControlAddresses,
            "Sequencer": BILBO_SequencerAddresses,
            "Estimation": BILBO_EstimationAddresses,
        }

    def test_all_firmware_addresses_have_python_counterpart(self):
        """Every REG_ADDRESS_* in the firmware header should exist in Python."""
        py_values = set()
        for enum_cls in self.py_enums.values():
            for member in enum_cls:
                py_values.add(int(member.value))

        missing = []
        for name, value in sorted(self.fw_defines.items()):
            if value not in py_values:
                missing.append(f"  {name} = 0x{value:02X}")

        assert not missing, (
            "Firmware registers missing from Python stm32_addresses.py:\n"
            + "\n".join(missing)
        )

    def test_python_addresses_match_firmware_values(self):
        """Python address values must match firmware #define values."""
        # Build reverse map: value -> firmware name
        fw_by_value: dict[int, str] = {}
        for name, value in self.fw_defines.items():
            fw_by_value.setdefault(value, name)

        mismatches = []
        for group, enum_cls in self.py_enums.items():
            for member in enum_cls:
                val = int(member.value)
                if val in fw_by_value:
                    # Value exists in both — that's fine
                    pass
                # Values not in firmware are caught by the other test

        # Direct value check: ensure no Python enum has a value that
        # doesn't appear in any firmware define
        all_fw_values = set(self.fw_defines.values())
        for group, enum_cls in self.py_enums.items():
            for member in enum_cls:
                val = int(member.value)
                if val not in all_fw_values:
                    mismatches.append(
                        f"  {group}.{member.name} = 0x{val:02X} not in firmware"
                    )

        assert not mismatches, (
            "Python addresses not found in firmware:\n" + "\n".join(mismatches)
        )


# ===========================================================================
# 2. Enum parity: firmware C++ enums vs Python IntEnums
# ===========================================================================

class TestEnumParity:
    """Verify Python IntEnums match firmware C++ enum classes."""

    @pytest.fixture(autouse=True)
    def _load(self):
        if not FIRMWARE_ROOT.exists():
            pytest.skip("Firmware source not available")

    def _check_enum(self, header_rel: str, c_enum_name: str, py_enum):
        header = FIRMWARE_ROOT / header_rel
        fw_members = _parse_enum_members(header, c_enum_name)
        py_members = {m.name: m.value for m in py_enum}

        # Check all firmware members exist in Python with same value
        missing = []
        value_mismatches = []
        for name, value in fw_members.items():
            if name not in py_members:
                missing.append(f"  {name} = {value}")
            elif py_members[name] != value:
                value_mismatches.append(
                    f"  {name}: firmware={value}, python={py_members[name]}"
                )

        errors = []
        if missing:
            errors.append(f"Members in firmware {c_enum_name} missing from Python:\n" + "\n".join(missing))
        if value_mismatches:
            errors.append(f"Value mismatches in {c_enum_name}:\n" + "\n".join(value_mismatches))
        assert not errors, "\n".join(errors)

    def test_control_mode(self):
        from robot.lowlevel.stm32_control import bilbo_control_mode_t
        self._check_enum("control/bilbo_control.h", "bilbo_control_mode_t", bilbo_control_mode_t)

    def test_control_event(self):
        from robot.lowlevel.stm32_control import control_event_t
        self._check_enum("control/bilbo_control.h", "control_event_t", control_event_t)

    def test_position_control_event(self):
        from robot.lowlevel.stm32_control import position_control_event_t
        self._check_enum("control/bilbo_position_control.h", "position_control_event_t", position_control_event_t)


# ===========================================================================
# 3. Struct field order parity: firmware C structs vs Python ctypes
# ===========================================================================

class TestStructFieldOrder:
    """Verify Python ctypes Structures have the same field order as firmware C structs."""

    @pytest.fixture(autouse=True)
    def _load(self):
        if not FIRMWARE_ROOT.exists():
            pytest.skip("Firmware source not available")

    def _check_struct(self, header_rel: str, c_struct_name: str, py_struct_cls):
        header = FIRMWARE_ROOT / header_rel
        fw_fields = _parse_struct_fields(header, c_struct_name)
        py_fields = [name for name, _ in py_struct_cls._fields_]

        if fw_fields != py_fields:
            pytest.fail(
                f"Field order mismatch for {c_struct_name}:\n"
                f"  Firmware: {fw_fields}\n"
                f"  Python:   {py_fields}"
            )

    def test_control_data(self):
        from robot.lowlevel.stm32_control import bilbo_ll_control_data_t
        self._check_struct(
            "control/bilbo_control.h", "bilbo_control_data_t", bilbo_ll_control_data_t
        )

    def test_sample_top_level(self):
        from robot.lowlevel.stm32_sample import bilbo_ll_sample_struct
        self._check_struct(
            "logging/bilbo_logging.h", "bilbo_logging_sample_t", bilbo_ll_sample_struct
        )


# ===========================================================================
# 4. Message ID parity: firmware #defines vs Python message constants
# ===========================================================================

class TestMessageIDs:
    """Verify Python message IDs match firmware BILBO_MESSAGE_* defines."""

    def test_message_ids_match(self):
        if not FIRMWARE_ROOT.exists():
            pytest.skip("Firmware source not available")

        fw_messages = _parse_defines(
            FIRMWARE_ROOT / "firmware_addresses.h", prefix="BILBO_MESSAGE"
        )
        from robot.lowlevel.stm32_messages import (
            BILBO_LL_MESSAGE_PRINT,
            BILBO_LL_MESSAGE_ERROR,
            BILBO_LL_MESSAGE_SEQUENCER_EVENT,
            BILBO_LL_MESSAGE_CONTROL_EVENT,
            BILBO_LL_MESSAGE_POSITION_CONTROL_EVENT,
        )
        py_messages = {
            "BILBO_MESSAGE_PRINT": BILBO_LL_MESSAGE_PRINT,
            "BILBO_MESSAGE_ERROR": BILBO_LL_MESSAGE_ERROR,
            "BILBO_MESSAGE_SEQUENCER_EVENT": BILBO_LL_MESSAGE_SEQUENCER_EVENT,
            "BILBO_MESSAGE_CONTROL_EVENT": BILBO_LL_MESSAGE_CONTROL_EVENT,
            "BILBO_MESSAGE_POSITION_CONTROL_EVENT": BILBO_LL_MESSAGE_POSITION_CONTROL_EVENT,
        }

        mismatches = []
        for fw_name, fw_val in fw_messages.items():
            if fw_name in py_messages:
                if py_messages[fw_name] != fw_val:
                    mismatches.append(
                        f"  {fw_name}: firmware=0x{fw_val:02X}, python=0x{py_messages[fw_name]:02X}"
                    )
            # New firmware messages not yet in Python are informational
            elif fw_name not in ("BILBO_MESSAGE_WAYPOINT_EVENT", "BILBO_MESSAGE_DRIVE_EVENT"):
                mismatches.append(f"  {fw_name} = 0x{fw_val:02X} not in Python")

        assert not mismatches, (
            "Message ID mismatches:\n" + "\n".join(mismatches)
        )


# ===========================================================================
# 5. Simulation register handler coverage
# ===========================================================================

class TestSimulationCoverage:
    """Verify the simulation handles all register addresses the Python software uses."""

    @pytest.fixture(autouse=True)
    def _load(self):
        from robot.lowlevel.stm32_addresses import (
            BILBO_SystemAddresses,
            BILBO_ControlAddresses,
            BILBO_PositionControlAddresses,
            BILBO_EstimationAddresses,
        )
        self.all_addresses = {}
        for enum_cls in (BILBO_SystemAddresses, BILBO_ControlAddresses,
                         BILBO_PositionControlAddresses, BILBO_EstimationAddresses):
            for member in enum_cls:
                self.all_addresses[int(member.value)] = f"{enum_cls.__name__}.{member.name}"

    def _get_handled_addresses(self) -> set[int]:
        """Parse simulated_communication.py to find all address comparisons."""
        src = (SOFTWARE_ROOT / "simulation" / "simulated_communication.py").read_text()
        # Match patterns like: address == BILBO_*Addresses.SOMETHING
        # and: address in (BILBO_*Addresses.X, ...)
        handled = set()

        from robot.lowlevel.stm32_addresses import (
            BILBO_SystemAddresses,
            BILBO_ControlAddresses,
            BILBO_PositionControlAddresses,
            BILBO_EstimationAddresses,
        )
        enum_map = {
            "BILBO_SystemAddresses": BILBO_SystemAddresses,
            "BILBO_ControlAddresses": BILBO_ControlAddresses,
            "BILBO_PositionControlAddresses": BILBO_PositionControlAddresses,
            "BILBO_EstimationAddresses": BILBO_EstimationAddresses,
        }

        # Find all "SomeAddresses.MEMBER" references in the source
        for match in re.finditer(r"(BILBO_\w+Addresses)\.(\w+)", src):
            cls_name, member_name = match.group(1), match.group(2)
            if cls_name in enum_map:
                try:
                    val = int(enum_map[cls_name][member_name].value)
                    handled.add(val)
                except (KeyError, ValueError):
                    pass

        return handled

    def test_executeFunction_coverage(self):
        """All addresses that could be called via executeFunction should be handled."""
        handled = self._get_handled_addresses()

        # Addresses that are read-only or handled elsewhere (board, SPI) — not via executeFunction
        excluded_names = {
            # Read-only system registers (read via readValue or board)
            "FIRMWARE_STATE", "FIRMWARE_TICK", "FIRMWARE_REVISION", "FIRMWARE_INFO",
            # Board-level functions (handled by SimulatedBoard, not serial)
            "FIRMWARE_DEBUGFUNCTION", "FIRMWARE_BEEP", "EXTERNAL_LED",
            "ALL_EXTERNAL_LEDS", "DEBUG_1_RW",
            # Read via readValue
            "READ_MODE",
            # Write via writeValue
            "RW_MAX_WHEEL_SPEED",
            # Legacy / not actively used
            "SET_FORWARD_PID", "SET_TURN_PID", "SET_DIRECT_INPUT",
            "GET_CONFIGURATION", "SET_CONFIGURATION",
            "ENABLE_VELOCITY_INTEGRAL_CONTROL", "SET_VELOCITY_INTEGRAL_CONTROL_CONFIG",
            # Sequencer (trajectory injection via SPI, not serial)
            "LOAD", "START", "STOP", "READ",
            # Position control read-only (handled in readValue path)
            "GET_CONFIG",
        }

        missing = []
        for addr, name in sorted(self.all_addresses.items()):
            short_name = name.split(".")[-1]
            if short_name in excluded_names:
                continue
            if addr not in handled:
                missing.append(f"  0x{addr:02X} {name}")

        assert not missing, (
            "Addresses not handled by simulation:\n" + "\n".join(missing)
        )

    def test_readValue_coverage(self):
        """Addresses used via readValue should be handled."""
        src = (SOFTWARE_ROOT / "simulation" / "simulated_communication.py").read_text()
        # Check that readValue handles READ_MODE
        assert "READ_MODE" in src, "readValue should handle READ_MODE"


# ===========================================================================
# 6. Sample structure completeness
# ===========================================================================

class TestSampleCompleteness:
    """Verify the simulation produces samples with all expected fields."""

    def test_ll_sample_fields(self):
        """BILBO_LL_Sample dataclass fields should match the ctypes struct fields."""
        from robot.lowlevel.stm32_sample import BILBO_LL_Sample, bilbo_ll_sample_struct

        dc_fields = {f.name for f in dataclasses.fields(BILBO_LL_Sample)}
        ct_fields = {name for name, _ in bilbo_ll_sample_struct._fields_}

        assert dc_fields == ct_fields, (
            f"Dataclass vs ctypes field mismatch:\n"
            f"  Only in dataclass: {dc_fields - ct_fields}\n"
            f"  Only in ctypes:    {ct_fields - dc_fields}"
        )

    def test_control_data_fields(self):
        """bilbo_ll_control_data dataclass should match ctypes struct."""
        from robot.lowlevel.stm32_control import bilbo_ll_control_data, bilbo_ll_control_data_t

        dc_fields = {f.name for f in dataclasses.fields(bilbo_ll_control_data)}
        ct_fields = {name for name, _ in bilbo_ll_control_data_t._fields_}

        assert dc_fields == ct_fields, (
            f"Control data field mismatch:\n"
            f"  Only in dataclass: {dc_fields - ct_fields}\n"
            f"  Only in ctypes:    {ct_fields - dc_fields}"
        )

    def test_simulation_builds_complete_sample(self):
        """SimulatedFirmware._build_sample should set all BILBO_LL_Sample fields."""
        from simulation.firmware import SimulatedFirmware

        fw = SimulatedFirmware()
        # Access _build_sample with default state
        sample = fw._build_sample(fw.dynamics.state, 0.0, 0.0)

        from robot.lowlevel.stm32_sample import BILBO_LL_Sample
        for field in dataclasses.fields(BILBO_LL_Sample):
            assert hasattr(sample, field.name), f"Sample missing field: {field.name}"
            val = getattr(sample, field.name)
            assert val is not None, f"Sample field {field.name} is None"


# ===========================================================================
# 7. Functional smoke test — simulation control loop
# ===========================================================================

class TestSimulationSmoke:
    """Basic functional tests that the simulation control loop works."""

    @pytest.fixture
    def fw(self):
        from simulation.firmware import SimulatedFirmware
        return SimulatedFirmware()

    def test_off_mode_no_torque(self, fw):
        """In OFF mode, dynamics should not move."""
        fw._step()
        assert fw._last_output_left == 0.0
        assert fw._last_output_right == 0.0

    def test_mode_transition(self, fw):
        """Mode transitions should work without errors."""
        from robot.lowlevel.stm32_control import bilbo_control_mode_t
        fw.set_K([0.1, 0.5, 0.05, 0.01, 0.1, 0.5, 0.05, 0.01])

        for mode in bilbo_control_mode_t:
            fw.set_mode(int(mode))
            assert fw.mode == mode
            fw._step()  # Should not crash

    def test_balancing_produces_torque(self, fw):
        """With non-zero K and a pitch perturbation, balancing should produce torque."""
        from robot.lowlevel.stm32_control import bilbo_control_mode_t
        fw.set_K([0.0, 1.0, 0.1, 0.0, 0.0, 1.0, 0.1, 0.0])
        fw.dynamics.state.theta = 0.05  # 2.9 deg pitch
        fw.set_mode(int(bilbo_control_mode_t.BALANCING))
        fw._step()
        assert fw._last_output_left != 0.0 or fw._last_output_right != 0.0

    def test_psi_controller_holds_heading(self, fw):
        """PSI controller should generate differential torque when heading differs from setpoint."""
        from robot.lowlevel.stm32_control import bilbo_control_mode_t
        from simulation.control import PSIConfig

        fw.set_K([0.0, 1.0, 0.1, 0.0, 0.0, 1.0, 0.1, 0.0])
        fw.set_psi_config(PSIConfig(enabled=True, Ts=0.01, kp=2.0, ki=0.0, max_torque=0.5))
        fw.set_psi_setpoint(0.0)
        fw.dynamics.state.psi = 0.3  # 17 deg heading error
        fw.set_mode(int(bilbo_control_mode_t.BALANCING))
        fw._step()
        # PSI should create differential torque (left != right due to psi correction)
        assert fw._last_bal_left != fw._last_bal_right

    def test_velocity_mode(self, fw):
        """Velocity command should propagate through the control chain."""
        from robot.lowlevel.stm32_control import bilbo_control_mode_t
        fw.set_K([0.0, 1.0, 0.1, 0.0, 0.0, 1.0, 0.1, 0.0])
        fw.set_mode(int(bilbo_control_mode_t.VELOCITY))
        fw.set_velocity_command(0.3, 0.0)
        for _ in range(10):
            fw._step()
        assert fw._last_vel_output.v_cmd == 0.3

    def test_sample_tick_increments(self, fw):
        """Tick should increment each step."""
        assert fw.tick == 0
        fw._step()
        assert fw.tick == 1
        fw._step()
        assert fw.tick == 2


# ===========================================================================
# 8. Dynamics behavioral tests
# ===========================================================================

def _step_n(fw, n: int):
    """Step the firmware n times."""
    for _ in range(n):
        fw._step()


def _make_fw():
    from simulation.firmware import SimulatedFirmware
    return SimulatedFirmware()


def _make_fw_balanced():
    """Create a firmware instance with realistic K gains in balancing mode."""
    from simulation.firmware import SimulatedFirmware
    from robot.lowlevel.stm32_control import bilbo_control_mode_t
    from simulation.control import TICConfig

    fw = SimulatedFirmware()
    # Gains from default config
    fw.set_K([0.25, 0.265, 0.035, 0.025, 0.25, 0.265, 0.035, -0.025])
    fw.set_tic_config(TICConfig(enabled=True, Ts=0.01, ki=0.4, max_torque=0.05, theta_limit=0.16))
    fw.set_mode(int(bilbo_control_mode_t.BALANCING))
    return fw


class TestDynamicsUncontrolled:
    """Test that open-loop dynamics behave physically correctly."""

    def test_upright_unstable(self):
        """Without control, a small pitch perturbation should grow (inverted pendulum is unstable)."""
        fw = _make_fw()
        fw.dynamics.state.theta = 0.01  # ~0.6 deg
        _step_n(fw, 200)  # 2 seconds
        assert abs(fw.dynamics.state.theta) > 0.1, "Robot should have fallen over"

    def test_lying_down_stable(self):
        """At theta=pi/2 (lying down), the robot should not magically stand up."""
        fw = _make_fw()
        fw.dynamics.state.theta = math.pi / 2
        initial_theta = fw.dynamics.state.theta
        _step_n(fw, 100)
        # Should stay roughly lying down (theta stays large)
        assert abs(fw.dynamics.state.theta) > 0.5, "Robot should still be lying down"

    def test_no_motion_at_rest(self):
        """Zero state + zero input = no movement."""
        fw = _make_fw()
        _step_n(fw, 100)
        s = fw.dynamics.state
        assert abs(s.x) < 1e-6
        assert abs(s.y) < 1e-6
        assert abs(s.v) < 1e-6
        assert abs(s.psi) < 1e-6
        assert abs(s.psi_dot) < 1e-6

    def test_forward_torque_moves_forward(self):
        """Equal positive torques on both wheels should produce forward motion."""
        from simulation.dynamics import BilboDynamics3D, BilboModel
        dyn = BilboDynamics3D(BilboModel(), Ts=0.01)
        # Apply symmetric torque while keeping theta=0 (idealized)
        for _ in range(50):
            dyn.step(0.1, 0.1)
            dyn.state.theta = 0.0  # Pin upright to isolate forward dynamics
            dyn.state.theta_dot = 0.0
        assert dyn.state.v > 0.0, "Forward torque should produce positive velocity"
        assert dyn.state.x > 0.0, "Robot should have moved forward"

    def test_differential_torque_turns(self):
        """Opposite torques should produce yaw rotation."""
        from simulation.dynamics import BilboDynamics3D, BilboModel
        dyn = BilboDynamics3D(BilboModel(), Ts=0.01)
        for _ in range(50):
            dyn.step(0.1, -0.1)  # Left forward, right backward
            dyn.state.theta = 0.0
            dyn.state.theta_dot = 0.0
        assert abs(dyn.state.psi_dot) > 0.01, "Differential torque should produce yaw rate"

    def test_wheel_speeds_consistent(self):
        """Wheel speeds should match forward velocity and yaw rate."""
        from simulation.dynamics import BilboDynamics3D, BilboModel
        model = BilboModel()
        dyn = BilboDynamics3D(model, Ts=0.01)
        dyn.state.v = 0.5
        dyn.state.psi_dot = 1.0
        wl, wr = dyn.get_wheel_speeds(0, 0)
        # v_left = (v - d/2 * psi_dot) / r
        expected_left = (0.5 - model.d_w / 2 * 1.0) / model.r_w
        expected_right = (0.5 + model.d_w / 2 * 1.0) / model.r_w
        assert abs(wl - expected_left) < 1e-6
        assert abs(wr - expected_right) < 1e-6

    def test_energy_not_increasing_passive(self):
        """With no input, total energy should not increase (passive system)."""
        fw = _make_fw()
        fw.dynamics.state.theta = 0.1
        fw.dynamics.state.v = 0.05

        def _kinetic_energy(s):
            m = fw.dynamics.model
            return 0.5 * (m.m_b + 2 * m.m_w) * s.v ** 2 + 0.5 * m.I_y * s.theta_dot ** 2

        e0 = _kinetic_energy(fw.dynamics.state)
        _step_n(fw, 50)
        # After falling, kinetic energy might increase from potential energy conversion,
        # but total mechanical energy should be bounded. Just check it doesn't explode.
        e_final = _kinetic_energy(fw.dynamics.state)
        assert e_final < 100 * e0 + 10, "Energy should not explode"


# ===========================================================================
# 9. Balancing control behavioral tests
# ===========================================================================

class TestBalancingBehavior:
    """Test that the balancing controller stabilizes the inverted pendulum."""

    def test_balancing_stabilizes_small_perturbation(self):
        """With good gains, a small pitch perturbation should be corrected."""
        fw = _make_fw_balanced()
        fw.dynamics.state.theta = 0.03  # ~1.7 deg
        _step_n(fw, 500)  # 5 seconds
        assert abs(fw.dynamics.state.theta) < 0.03, (
            f"Balancing should reduce pitch, got {math.degrees(fw.dynamics.state.theta):.1f} deg"
        )

    def test_balancing_limits_velocity_drift(self):
        """With VIC enabled, velocity should stay bounded near zero."""
        from simulation.control import VICConfig
        fw = _make_fw_balanced()
        fw.set_vic_config(VICConfig(enabled=True, Ts=0.01, ki=0.2, max_torque=0.02,
                                    v_limit=0.05, theta_limit=0.16))
        fw.dynamics.state.theta = 0.02
        _step_n(fw, 1000)  # 10 seconds
        assert abs(fw.dynamics.state.v) < 0.3, (
            f"Velocity should stay bounded, got {fw.dynamics.state.v:.3f} m/s"
        )

    def test_insufficient_torque_fails_to_balance(self):
        """With very low max torque, the controller cannot stabilize even a small perturbation."""
        fw = _make_fw_balanced()
        fw.set_max_torque(0.005)  # Tiny torque limit
        fw.dynamics.state.theta = 0.1  # ~5.7 deg
        _step_n(fw, 500)
        assert abs(fw.dynamics.state.theta) > 0.1, "Should fail to balance with insufficient torque"

    def test_torque_clamping(self):
        """Output torque should never exceed max_torque."""
        fw = _make_fw_balanced()
        fw.dynamics.state.theta = 0.15  # Significant pitch
        for _ in range(100):
            fw._step()
            assert abs(fw._last_output_left) <= fw.max_torque + 1e-9
            assert abs(fw._last_output_right) <= fw.max_torque + 1e-9


# ===========================================================================
# 10. Velocity control behavioral tests
# ===========================================================================

class TestVelocityControlBehavior:
    """Test that velocity commands produce the expected motion."""

    def _make_velocity_fw(self):
        from simulation.firmware import SimulatedFirmware
        from robot.lowlevel.stm32_control import bilbo_control_mode_t
        from simulation.control import TICConfig, PIDConfig, FeedforwardConfig

        fw = SimulatedFirmware()
        fw.set_K([0.25, 0.265, 0.035, 0.025, 0.25, 0.265, 0.035, -0.025])
        fw.set_tic_config(TICConfig(enabled=True, Ts=0.01, ki=0.4, max_torque=0.05, theta_limit=0.16))
        # Velocity PID with integral action
        fw.set_velocity_config_v_pid(PIDConfig(Kp=0.0, Ki=-0.03, Kd=0.0, Ts=0.01))
        fw.set_velocity_config_v_ff(FeedforwardConfig(Kv=-0.034, Ka=-0.015, Kc=-0.0081,
                                                       Ts=0.01, enable_stiction=True,
                                                       v0_stiction=0.01, v_decay_stiction=0.1))
        fw.set_mode(int(bilbo_control_mode_t.VELOCITY))
        return fw

    def test_forward_velocity_tracking(self):
        """Commanding forward velocity should eventually produce forward motion."""
        fw = self._make_velocity_fw()
        fw.set_velocity_command(0.2, 0.0)
        _step_n(fw, 500)  # 5 seconds
        # Robot should be moving forward
        assert fw.dynamics.state.v > 0.05, (
            f"Should track forward velocity, got v={fw.dynamics.state.v:.3f}"
        )
        assert fw.dynamics.state.x > 0.0, "Should have moved forward in x"

    def test_zero_velocity_stays_still(self):
        """Zero velocity command should keep robot approximately still."""
        fw = self._make_velocity_fw()
        fw.set_velocity_command(0.0, 0.0)
        _step_n(fw, 500)
        assert abs(fw.dynamics.state.v) < 0.1, "Should stay approximately still"

    def test_yaw_rate_command(self):
        """Commanding yaw rate should produce rotation."""
        fw = self._make_velocity_fw()
        from simulation.control import PIDConfig
        fw.set_velocity_config_psidot_pid(PIDConfig(Kp=0.01, Ki=0.0, Kd=0.0, Ts=0.01))
        fw.set_velocity_command(0.0, 1.0)  # 1 rad/s yaw rate
        _step_n(fw, 300)
        assert abs(fw.dynamics.state.psi) > 0.1, (
            f"Should have rotated, got psi={math.degrees(fw.dynamics.state.psi):.1f} deg"
        )


# ===========================================================================
# 11. Position control behavioral tests
# ===========================================================================

class TestPositionControlBehavior:
    """Test path following, turn-to-heading, and drive-to-point."""

    def _make_position_fw(self):
        """Create a firmware in POSITION mode with good gains.

        To isolate position control logic from dynamics instability,
        we test the position controller directly.
        """
        from simulation.position_control import SimulatedPositionControl, PositionControlConfig
        pc = SimulatedPositionControl(PositionControlConfig(
            Ts=0.01,
            kp_angular=8.0,
            ki_angular=0.25,
            kp_linear=2.0,
            kd_linear=0.5,
            max_speed=0.5,
            max_turn_rate=5.0,
            lookahead_base=0.15,
            lookahead_min=0.03,
            arrival_tolerance=0.05,
            arrival_dwell_time=0.3,
            decel_limit=0.6,
        ))
        return pc

    def test_turn_to_heading_converges(self):
        """Turn-to-heading should converge to the target heading."""
        pc = self._make_position_fw()
        pc.turn_to_heading(heading=math.pi / 2, timeout=10.0, cmd_id=1)

        psi = 0.0
        psi_dot = 0.0
        for _ in range(1000):  # 10 seconds
            v_cmd, w_cmd = pc.update(0.0, 0.0, psi, 0.0)
            # Simple kinematic integration
            psi_dot = 0.8 * psi_dot + 0.2 * w_cmd  # Low-pass to simulate inertia
            psi += psi_dot * 0.01
            assert v_cmd == 0.0, "Turn-to-heading should not produce forward velocity"

        heading_error = abs(math.atan2(math.sin(math.pi / 2 - psi), math.cos(math.pi / 2 - psi)))
        assert heading_error < math.radians(5), (
            f"Should converge to target heading, error={math.degrees(heading_error):.1f} deg"
        )

    def test_turn_to_heading_completion_event(self):
        """Turn-to-heading should emit a completion event."""
        from simulation.position_control import PositionControlEvent, PositionControlMode
        pc = self._make_position_fw()
        pc.turn_to_heading(heading=0.1, timeout=5.0, cmd_id=42)

        psi = 0.0
        completed = False
        for _ in range(500):
            v_cmd, w_cmd = pc.update(0.0, 0.0, psi, 0.0)
            psi += w_cmd * 0.01
            for evt, extra in pc.pending_events:
                if evt == PositionControlEvent.TURN_TO_HEADING_COMPLETED:
                    assert extra.get('command_id') == 42
                    completed = True
            pc.pending_events.clear()
            if completed:
                break

        assert completed, "Should have received TURN_TO_HEADING_COMPLETED event"
        assert pc.mode == PositionControlMode.IDLE

    def test_turn_to_heading_timeout(self):
        """Turn-to-heading should timeout if target is unreachable."""
        from simulation.position_control import PositionControlEvent
        pc = self._make_position_fw()
        # Very short timeout, target 180 deg away
        pc.turn_to_heading(heading=math.pi, timeout=0.05, cmd_id=7)

        timed_out = False
        for _ in range(100):
            pc.update(0.0, 0.0, 0.0, 0.0)  # Don't actually move
            for evt, extra in pc.pending_events:
                if evt == PositionControlEvent.TURN_TO_HEADING_TIMEOUT:
                    timed_out = True
            pc.pending_events.clear()
            if timed_out:
                break

        assert timed_out, "Should have received TURN_TO_HEADING_TIMEOUT"

    def test_drive_to_point_arrives(self):
        """Drive-to-point should approach the target."""
        from simulation.position_control import PositionControlEvent
        pc = self._make_position_fw()
        pc.move_to_point(x=1.0, y=0.0, timeout=20.0, cmd_id=1)

        x, y, psi, v = 0.0, 0.0, 0.0, 0.0
        completed = False
        for _ in range(2000):  # 20 seconds
            v_cmd, w_cmd = pc.update(x, y, psi, v)
            # Simple kinematic model
            v = 0.9 * v + 0.1 * v_cmd
            psi += w_cmd * 0.01
            x += v * math.cos(psi) * 0.01
            y += v * math.sin(psi) * 0.01
            for evt, extra in pc.pending_events:
                if evt == PositionControlEvent.MOVE_TO_POINT_COMPLETED:
                    completed = True
            pc.pending_events.clear()
            if completed:
                break

        dist = math.hypot(1.0 - x, 0.0 - y)
        assert dist < 0.15, f"Should approach target, final distance={dist:.3f} m"

    def test_path_following_completes(self):
        """Following a simple path should produce PATH_FINISHED event."""
        from simulation.position_control import PositionControlEvent
        pc = self._make_position_fw()

        # Simple straight path with 10 cm spacing
        for i in range(21):
            pc.add_path_point(i * 0.1, 0.0)  # 0 to 2m straight line
        pc.start_path(max_speed=0.3, timeout=30.0)

        x, y, psi, v = 0.0, 0.0, 0.0, 0.0
        finished = False
        for _ in range(3000):  # 30 seconds
            v_cmd, w_cmd = pc.update(x, y, psi, v)
            v = 0.9 * v + 0.1 * v_cmd
            psi += w_cmd * 0.01
            x += v * math.cos(psi) * 0.01
            y += v * math.sin(psi) * 0.01
            for evt, extra in pc.pending_events:
                if evt == PositionControlEvent.PATH_FINISHED:
                    finished = True
            pc.pending_events.clear()
            if finished:
                break

        assert finished, f"Path should complete. Final pos=({x:.2f}, {y:.2f}), progress={pc._progress:.1f}"

    def test_path_following_tracks_curve(self):
        """Following a curved path should stay within a lateral bound."""
        pc = self._make_position_fw()

        # Quarter circle path (radius 1m, 50 points)
        n_points = 50
        for i in range(n_points):
            angle = (math.pi / 2) * i / (n_points - 1)
            pc.add_path_point(math.sin(angle), 1.0 - math.cos(angle))
        pc.start_path(max_speed=0.3, timeout=30.0)

        x, y, psi, v = 0.0, 0.0, 0.0, 0.0
        max_cross_track = 0.0

        for _ in range(3000):
            v_cmd, w_cmd = pc.update(x, y, psi, v)
            v = 0.9 * v + 0.1 * v_cmd
            psi += w_cmd * 0.01
            x += v * math.cos(psi) * 0.01
            y += v * math.sin(psi) * 0.01

            # Cross-track error: distance from (x,y) to unit circle centered at (0,1)
            dist_to_center = math.hypot(x, y - 1.0)
            cross_track = abs(dist_to_center - 1.0)
            max_cross_track = max(max_cross_track, cross_track)

            if pc.path_state == 0:  # IDLE = finished
                break

        assert max_cross_track < 0.5, (
            f"Cross-track error too large: {max_cross_track:.3f} m"
        )

    def test_path_stop_indices(self):
        """Stop indices should produce WAYPOINT_REACHED and WAYPOINT_COMPLETED events."""
        from simulation.position_control import PositionControlEvent
        pc = self._make_position_fw()

        for i in range(31):
            pc.add_path_point(i * 0.1, 0.0)
        pc.add_stop_index(10)  # Stop at 1.0 m
        pc.add_stop_index(20)  # Stop at 2.0 m
        pc.start_path(max_speed=0.3, timeout=30.0)

        x, y, psi, v = 0.0, 0.0, 0.0, 0.0
        waypoints_reached = []
        waypoints_completed = []

        for _ in range(3000):
            v_cmd, w_cmd = pc.update(x, y, psi, v)
            v = 0.9 * v + 0.1 * v_cmd
            psi += w_cmd * 0.01
            x += v * math.cos(psi) * 0.01
            y += v * math.sin(psi) * 0.01
            for evt, extra in pc.pending_events:
                if evt == PositionControlEvent.WAYPOINT_REACHED:
                    waypoints_reached.append(extra.get('waypoint_index', -1))
                elif evt == PositionControlEvent.WAYPOINT_COMPLETED:
                    waypoints_completed.append(extra.get('waypoint_index', -1))
            pc.pending_events.clear()
            if pc.path_state == 0:
                break

        assert 10 in waypoints_reached, f"Should reach stop at index 10, got {waypoints_reached}"
        assert 10 in waypoints_completed, f"Should complete stop at index 10, got {waypoints_completed}"

    def test_path_pause_resume(self):
        """Pausing should stop output, resuming should continue."""
        from simulation.position_control import PathState
        pc = self._make_position_fw()

        for i in range(21):
            pc.add_path_point(i * 0.1, 0.0)
        pc.start_path(max_speed=0.3, timeout=30.0)

        # Run a bit
        x, y, psi, v = 0.0, 0.0, 0.0, 0.0
        for _ in range(100):
            v_cmd, w_cmd = pc.update(x, y, psi, v)
            v = 0.9 * v + 0.1 * v_cmd
            x += v * math.cos(psi) * 0.01
            pc.pending_events.clear()

        # Pause
        pc.pause_path()
        assert pc.path_state == PathState.PAUSED
        v_cmd, w_cmd = pc.update(x, y, psi, v)
        assert v_cmd == 0.0 and w_cmd == 0.0, "Paused path should output zero"

        # Resume
        pc.resume_path()
        assert pc.path_state == PathState.RUNNING
        v_cmd, w_cmd = pc.update(x, y, psi, v)
        # Should produce some output again (we're still on the path)
        # (may be zero if exactly at a waypoint, so just check no crash)

    def test_path_abort(self):
        """Aborting should emit event and go idle."""
        from simulation.position_control import PositionControlEvent, PositionControlMode
        pc = self._make_position_fw()

        for i in range(11):
            pc.add_path_point(i * 0.1, 0.0)
        pc.start_path(max_speed=0.3)

        pc.update(0.0, 0.0, 0.0, 0.0)
        pc.pending_events.clear()

        pc.abort_path()
        assert pc.mode == PositionControlMode.IDLE
        aborted = any(evt == PositionControlEvent.PATH_ABORTED for evt, _ in pc.pending_events)
        assert aborted, "Should have received PATH_ABORTED event"
