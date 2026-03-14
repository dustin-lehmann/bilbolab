"""
Compile BILBO firmware for all combinations of board revision, robot model,
and motor interface, then copy the .hex files into precompiled-firmware/.

Usage:
    python compile_all_firmware.py              # Build all 12 combinations
    python compile_all_firmware.py --dry-run    # Show what would be built
    python compile_all_firmware.py --only rev4 normal can   # Build one specific combination

Requires STM32CubeIDE installed at /Applications/STM32CubeIDE.app
(uses the bundled ARM GCC toolchain).
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from itertools import product
from pathlib import Path

# Allow importing crop_hex from core/utils/stm32
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.utils.stm32.crop_hex import cropHex

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # bilbolab/
FIRMWARE_DIR = REPO_ROOT / "robots" / "bilbo" / "firmware"
SETTINGS_FILE = FIRMWARE_DIR / "firmware" / "firmware_settings.h"
CUBEIDE_PROJECT = FIRMWARE_DIR / "cubeide-project"
BUILD_DIR = CUBEIDE_PROJECT / "Debug"
OUTPUT_DIR = FIRMWARE_DIR / "precompiled-firmware"

# ── STM32CubeIDE toolchain discovery ──────────────────────────────────────────
CUBEIDE_APP = Path("/Applications/STM32CubeIDE.app")
TOOLCHAIN_GLOB = "Contents/Eclipse/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.*/tools/bin"


def find_arm_toolchain() -> Path | None:
    """Find the ARM GCC toolchain bundled inside STM32CubeIDE."""
    matches = sorted(CUBEIDE_APP.glob(TOOLCHAIN_GLOB))
    if not matches:
        return None
    # Use the latest version (sorted alphabetically → highest version last)
    toolchain_bin = matches[-1]
    if (toolchain_bin / "arm-none-eabi-gcc").exists():
        return toolchain_bin
    return None


# ── Setting definitions ───────────────────────────────────────────────────────
BOARD_REVISIONS = {
    "rev3": "BOARD_REV_3",
    "rev4": "BOARD_REV_4",
}

MODELS = {
    "normal": "BILBO_MODEL_NORMAL",
    "small": "BILBO_MODEL_SMALL",
    "big": "BILBO_MODEL_BIG",
}

MOTORS = {
    "can": "BILBO_DRIVE_SIMPLEXMOTION_CAN",
    "rs485": "BILBO_DRIVE_SIMPLEXMOTION_RS485",
}


def read_firmware_revision() -> tuple[int, int]:
    """Read MAJOR.MINOR revision from firmware_settings.h."""
    content = SETTINGS_FILE.read_text()
    major_match = re.search(r'#define\s+BILBO_FIRMWARE_REVISION_MAJOR\s+(0x[0-9a-fA-F]+|\d+)', content)
    minor_match = re.search(r'#define\s+BILBO_FIRMWARE_REVISION_MINOR\s+(0x[0-9a-fA-F]+|\d+)', content)
    if not major_match or not minor_match:
        print("ERROR: Could not read firmware revision from firmware_settings.h")
        sys.exit(1)
    major = int(major_match.group(1), 0)
    minor = int(minor_match.group(1), 0)
    return major, minor


def generate_settings(board_key: str, model_key: str, motor_key: str,
                      fw_major: int, fw_minor: int) -> str:
    """Generate firmware_settings.h content for a specific combination."""
    board_define = BOARD_REVISIONS[board_key]
    model_define = MODELS[model_key]
    motor_define = MOTORS[motor_key]

    board_lines = []
    for key, define in BOARD_REVISIONS.items():
        prefix = "" if define == board_define else "//"
        board_lines.append(f"{prefix}#define {define}")

    model_lines = []
    for key, define in MODELS.items():
        prefix = "" if define == model_define else "//"
        model_lines.append(f"{prefix}#define {define}")

    motor_lines = []
    for key, define in MOTORS.items():
        prefix = "" if define == motor_define else "//"
        motor_lines.append(f"{prefix}#define {define}")

    return f"""\
/*
 * firmware_settings.h
 *
 * Central configuration for BILBO firmware.
 * Edit this file to build for different robot variants.
 *
 * Created on: 3 Mar 2023
 * Author: Dustin Lehmann
 */

#ifndef FIRMWARE_SETTINGS_H_
#define FIRMWARE_SETTINGS_H_

/* ================================================================
 * ROBOT VARIANT — uncomment ONE option per group
 * ================================================================ */

// Board hardware revision
{chr(10).join(board_lines)}

// Robot model (sets wheel diameter and wheel distance in bilbo_model.h)
{chr(10).join(model_lines)}

/* ================================================================
 * MOTOR INTERFACE — uncomment ONE
 * ================================================================ */

// SimplexMotion communication bus
{chr(10).join(motor_lines)}

// Motor torque limit (Nm). Clamps all motor commands to this value.
#define BILBO_MOTOR_TORQUE_LIMIT 0.5

// Motor speed measurement filter (0 = none, 4 = default, 15 = max).
// Higher values smooth low-speed noise but add measurement lag.
#define SIMPLEXMOTION_SPEED_FILTER 5

// Motor encoder resolution in bits (12 = 4096, 13 = 8192, 14 = 16384 counts/rev).
// Higher resolution improves low-speed measurement but adds position noise.
#define SIMPLEXMOTION_ENCODER_RESOLUTION 13

// Motor-internal speed limit for torque mode (RPM). Written to the
// RampSpeedMax register during init. The motor clamps wheel speed to
// this value while in torque control mode. Set to 0 to disable.
#define SIMPLEXMOTION_OVERSPEED_RPM 700

// Hardware safety line: STM32 GPIO drives motor IN1 HIGH during operation,
// pulls LOW on error to trigger motor quickstop independent of CAN/RS485.
// Requires physical wiring from STM32 GPIO to IN1 on both motors.
#define ENABLE_MOTOR_SHUTDOWN_LINE 0

// Motor watchdog: uses SimplexMotion Events system to trigger Quickstop
// if the STM32 stops communicating with the motors (brownout/crash protection).
// A counter in ApplData[0] is decremented every 64ms by a motor-internal event.
// If the counter reaches zero, another event writes Quickstop to the Mode register.
// The STM32 periodically reloads the counter to prevent timeout.
// Set to 0 to disable.
#define BILBO_DRIVE_WATCHDOG_ENABLE 1

// Watchdog counter reload value, written by STM32 each drive task cycle.
// Timeout = reload × 64ms. Default 10 → 640ms.
#define BILBO_DRIVE_WATCHDOG_RELOAD 10

// Initial counter value written during motor init. Must be large enough
// to survive the time between motor init and the first drive task cycle.
// Default 100 → 6.4s.
#define BILBO_DRIVE_WATCHDOG_INITIAL 100

/* ================================================================
 * CONTROL LOOP
 * ================================================================ */

// Main control loop frequency (Hz). Estimation runs at the same rate.
#define BILBO_CONTROL_TASK_FREQ 100

// Max wheel speed before safety shutdown (rad/s)
#define BILBO_SAFETY_MAX_WHEEL_SPEED 75

// Enable/disable motor output (0 = dry-run, useful for testing without motors)
#define BILBO_FIRMWARE_USE_MOTORS 1

/* ================================================================
 * TRAJECTORIES & LOGGING
 * ================================================================ */

// Maximum trajectory duration (seconds). Determines pre-allocated buffer size.
#define BILBO_SEQUENCE_TIME 30

// Sample buffer aggregation time (seconds). Samples are collected for this
// duration before being sent to the host.
#define BILBO_FIRMWARE_SAMPLE_BUFFER_TIME 0.1

/* ================================================================
 * FIRMWARE REVISION — update when flashing new versions
 * ================================================================ */

#define BILBO_FIRMWARE_REVISION_MAJOR 0x{fw_major:02X}
#define BILBO_FIRMWARE_REVISION_MINOR 0x{fw_minor:02X}

#endif /* FIRMWARE_SETTINGS_H_ */
"""


def hex_filename(board_key: str, model_key: str, motor_key: str,
                 fw_major: int, fw_minor: int) -> str:
    """Generate output filename like bilbo_v3.0_rev4_normal_can.hex"""
    return f"bilbo_v{fw_major}.{fw_minor}_{board_key}_{model_key}_{motor_key}.hex"


def clean_build(toolchain_path: Path, jobs: int = 8) -> tuple[bool, str]:
    """Run make clean && make all in the Debug directory."""
    env = os.environ.copy()
    env["PATH"] = f"{toolchain_path}:{env['PATH']}"

    # Clean
    result = subprocess.run(
        ["make", "clean"],
        cwd=BUILD_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, f"make clean failed:\n{result.stderr}"

    # Also remove all object files to ensure a fully clean build
    for ext in ("*.o", "*.d", "*.su", "*.cyclo"):
        for f in BUILD_DIR.rglob(ext):
            f.unlink()

    # Build
    result = subprocess.run(
        ["make", f"-j{jobs}", "all"],
        cwd=BUILD_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        return False, f"make failed:\n{result.stderr}\n{result.stdout}"

    return True, result.stdout


def build_combination(
    board_key: str,
    model_key: str,
    motor_key: str,
    fw_major: int,
    fw_minor: int,
    toolchain_path: Path,
    jobs: int,
    dry_run: bool = False,
) -> bool:
    """Build one firmware variant and copy the hex file."""
    name = hex_filename(board_key, model_key, motor_key, fw_major, fw_minor)
    combo_label = f"v{fw_major}.{fw_minor} / {board_key} / {model_key} / {motor_key}"

    if dry_run:
        print(f"  [dry-run] Would build: {combo_label} → {name}")
        return True

    print(f"\n{'='*60}")
    print(f"  Building: {combo_label}")
    print(f"  Output:   {name}")
    print(f"{'='*60}")

    # Write settings
    settings_content = generate_settings(board_key, model_key, motor_key, fw_major, fw_minor)
    SETTINGS_FILE.write_text(settings_content)

    # Build
    t0 = time.time()
    success, output = clean_build(toolchain_path, jobs)
    elapsed = time.time() - t0

    if not success:
        print(f"  FAILED ({elapsed:.1f}s)")
        print(output)
        return False

    # Copy hex file
    hex_src = BUILD_DIR / "bilbo.hex"
    if not hex_src.exists():
        print(f"  FAILED: bilbo.hex not found after build")
        return False

    hex_dst = OUTPUT_DIR / name
    shutil.copy2(hex_src, hex_dst)
    raw_kb = hex_dst.stat().st_size / 1024

    # Strip RAM addresses that CubeIDE adds to the hex file
    cropHex(str(hex_dst))
    cropped_kb = hex_dst.stat().st_size / 1024

    print(f"  OK ({elapsed:.1f}s, {raw_kb:.0f} KB → {cropped_kb:.0f} KB cropped) → {hex_dst.relative_to(REPO_ROOT)}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Compile BILBO firmware for all setting combinations."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be built without actually building."
    )
    parser.add_argument(
        "--only", nargs=3, metavar=("BOARD", "MODEL", "MOTOR"),
        help="Build only one combination, e.g. --only rev4 normal can"
    )
    parser.add_argument(
        "--jobs", "-j", type=int, default=8,
        help="Number of parallel make jobs (default: 8)"
    )
    args = parser.parse_args()

    # Validate --only arguments
    if args.only:
        board, model, motor = args.only
        if board not in BOARD_REVISIONS:
            print(f"Unknown board '{board}'. Options: {', '.join(BOARD_REVISIONS)}")
            sys.exit(1)
        if model not in MODELS:
            print(f"Unknown model '{model}'. Options: {', '.join(MODELS)}")
            sys.exit(1)
        if motor not in MOTORS:
            print(f"Unknown motor '{motor}'. Options: {', '.join(MOTORS)}")
            sys.exit(1)
        combinations = [(board, model, motor)]
    else:
        combinations = list(product(BOARD_REVISIONS, MODELS, MOTORS))

    # Find toolchain
    toolchain_path = find_arm_toolchain()
    if toolchain_path is None and not args.dry_run:
        print("ERROR: Could not find ARM GCC toolchain in STM32CubeIDE.")
        print(f"  Looked in: {CUBEIDE_APP / TOOLCHAIN_GLOB}")
        print("  Make sure STM32CubeIDE is installed at /Applications/STM32CubeIDE.app")
        sys.exit(1)

    if not args.dry_run:
        print(f"Toolchain: {toolchain_path}")

    # Verify build directory exists
    if not BUILD_DIR.exists() and not args.dry_run:
        print(f"ERROR: Build directory not found: {BUILD_DIR}")
        print("  Open the project in STM32CubeIDE and build once to generate the makefiles.")
        sys.exit(1)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Read firmware revision before saving (so we use the current version)
    fw_major, fw_minor = read_firmware_revision()
    print(f"Firmware revision: v{fw_major}.{fw_minor}")

    # Save original settings file to restore later
    original_settings = SETTINGS_FILE.read_text()

    print(f"Building {len(combinations)} firmware variant(s)...")
    if args.dry_run:
        print()

    results = {}
    try:
        for board_key, model_key, motor_key in combinations:
            ok = build_combination(
                board_key, model_key, motor_key,
                fw_major, fw_minor,
                toolchain_path, args.jobs, args.dry_run,
            )
            results[(board_key, model_key, motor_key)] = ok
    finally:
        # Always restore original settings
        if not args.dry_run:
            SETTINGS_FILE.write_text(original_settings)
            print(f"\nRestored firmware_settings.h to original state.")

    # Summary
    succeeded = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)

    print(f"\n{'='*60}")
    print(f"  Results: {succeeded} succeeded, {failed} failed")
    if failed:
        print("  Failed combinations:")
        for (b, m, d), ok in results.items():
            if not ok:
                print(f"    - {b} / {m} / {d}")
    print(f"{'='*60}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
