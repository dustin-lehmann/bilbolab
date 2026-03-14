#!/usr/bin/env python3
"""Set up the directory structure for a simulated BILBO robot.

Usage:
    python simulation-setup.py bilbo-sim-1
    python simulation-setup.py bilbo-sim-2

Config resolution order (for both hardware and control):
    1. simulation/configs/<robot_id>/   (robot-specific sim configs)
    2. simulation/configs/default/      (shared sim defaults)

Re-running for an existing robot deletes and recreates the folder,
so config changes are always picked up.

This creates:
    <robots_path>/<robot_id>/
        ID
        config/   (robot config + testbed config)
        control/  (default control parameters)
        experiments/
        logs/
        calibration/
        software/
"""
import argparse
import os
import shutil

import yaml

SIMULATION_ROOT = os.path.dirname(os.path.abspath(__file__))
SOFTWARE_ROOT = os.path.dirname(SIMULATION_ROOT)
SIM_CONFIGS = os.path.join(SIMULATION_ROOT, 'configs')


def load_simulation_settings() -> dict:
    path = os.path.join(SOFTWARE_ROOT, 'simulation-settings.yaml')
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def _resolve_sim_config_dir(robot_id: str) -> str:
    """Return the sim config directory for this robot (robot-specific or default)."""
    robot_specific = os.path.join(SIM_CONFIGS, robot_id)
    if os.path.isdir(robot_specific):
        return robot_specific
    return os.path.join(SIM_CONFIGS, 'default')


def create_robot_config(robot_id: str, config_dir: str, dest_dir: str):
    """Create the robot hardware config, stamping in the robot ID."""
    src = os.path.join(config_dir, 'hardware.yaml')
    if not os.path.isfile(src):
        raise FileNotFoundError(f"Hardware config not found: {src}")

    with open(src, 'r') as f:
        config = yaml.safe_load(f)

    # Stamp robot identity
    config['general']['id'] = robot_id
    config['general']['short_id'] = robot_id.split('-')[-1] if '-' in robot_id else robot_id
    config['general']['simulation'] = True

    dest = os.path.join(dest_dir, f'{robot_id}.yaml')
    with open(dest, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"  Hardware config: {os.path.relpath(src, SIMULATION_ROOT)} -> {dest}")


def copy_control_configs(config_dir: str, dest_dir: str):
    """Copy all control YAML files from the sim config folder."""
    src_dir = os.path.join(config_dir, 'control')
    if not os.path.isdir(src_dir):
        print(f"  Warning: no control config folder in {config_dir}")
        return

    count = 0
    for fname in os.listdir(src_dir):
        if fname.endswith('.yaml'):
            shutil.copy2(os.path.join(src_dir, fname), os.path.join(dest_dir, fname))
            count += 1
            print(f"  Control config: {fname}")

    if count == 0:
        print(f"  Warning: no .yaml files found in {src_dir}")


def copy_testbed_config(dest_dir: str):
    """Copy all testbed config files, falling back to a minimal default for simulation."""
    src_dir = os.path.join(SOFTWARE_ROOT, 'configs', 'testbed')
    dest_testbed_dir = os.path.join(dest_dir, 'testbed')
    os.makedirs(dest_testbed_dir, exist_ok=True)

    if os.path.isdir(src_dir):
        count = 0
        for f in os.listdir(src_dir):
            if f.endswith('.yaml'):
                shutil.copy2(os.path.join(src_dir, f), os.path.join(dest_testbed_dir, f))
                count += 1
        print(f"  Copied {count} testbed config(s)")
    else:
        # Minimal fallback
        with open(os.path.join(dest_testbed_dir, 'default.yaml'), 'w') as f:
            yaml.dump({'size': [4.0, 4.0]}, f)
        print(f"  Created default testbed config")


def setup(robot_id: str):
    sim_settings = load_simulation_settings()
    robots_path = os.path.expanduser(sim_settings.get('robots_path', '~/bilbo-sim'))
    robot_path = os.path.join(robots_path, robot_id)

    # Resolve which sim config directory to use
    config_dir = _resolve_sim_config_dir(robot_id)
    config_label = os.path.relpath(config_dir, SIMULATION_ROOT)

    # Delete existing robot folder so config changes are always picked up
    if os.path.isdir(robot_path):
        shutil.rmtree(robot_path)
        print(f"Removed existing robot directory: {robot_path}")

    print(f"Setting up simulated robot '{robot_id}'")
    print(f"  Config source: {config_label}")
    print(f"  Location:      {robot_path}")

    # Create directory structure
    subdirs = ['config', 'control', 'experiments', 'logs', 'calibration', 'software']
    for d in subdirs:
        os.makedirs(os.path.join(robot_path, d), exist_ok=True)

    # Write ID file
    with open(os.path.join(robot_path, 'ID'), 'w') as f:
        f.write(robot_id)
    print(f"  Created ID file")

    # Robot hardware config
    create_robot_config(robot_id, config_dir, os.path.join(robot_path, 'config'))

    # Control configs
    copy_control_configs(config_dir, os.path.join(robot_path, 'control'))

    # Testbed config
    copy_testbed_config(os.path.join(robot_path, 'config'))

    print(f"\nDone! Run with:")
    print(f"  python main_simulation.py --robot {robot_id}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Set up a simulated BILBO robot')
    parser.add_argument('robot_id', help='Robot identifier (e.g. bilbo-sim-1)')
    args = parser.parse_args()

    setup(args.robot_id)
