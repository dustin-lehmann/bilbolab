import argparse
import os
import sys
import time

import yaml

SOFTWARE_ROOT = os.path.dirname(os.path.abspath(__file__))
SOFTWARE_PARENT = os.path.dirname(SOFTWARE_ROOT)

# Add the software root to the Python path so this file can be run directly
if SOFTWARE_PARENT not in sys.path:
    sys.path.insert(0, SOFTWARE_PARENT)


def _load_simulation_settings() -> dict:
    """Load simulation-settings.yaml."""
    path = os.path.join(SOFTWARE_ROOT, 'simulation-settings.yaml')
    if os.path.exists(path):
        with open(path, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


def _setup_simulation(robot_id: str | None):
    """Install hardware mocks and override paths for simulation."""
    from simulation.mock_hardware import install_mock_hardware
    install_mock_hardware()

    sim_settings = _load_simulation_settings()
    robots_path = os.path.expanduser(sim_settings.get('robots_path', '~/bilbo-sim'))

    if robot_id is None:
        robot_id = sim_settings.get('robot_id', 'bilbo-sim')

    robot_path = os.path.join(robots_path, robot_id)
    if not os.path.isdir(robot_path):
        raise FileNotFoundError(
            f"Simulated robot directory '{robot_path}' not found. "
            f"Run: python simulation-setup.py {robot_id}"
        )

    from robot.paths import init_paths
    init_paths(robot_path)


# ── Parse args & bootstrap ────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='BILBO Software (Simulation)')
parser.add_argument('--robot', default=None, help='Simulated robot ID')
_args = parser.parse_args()

_setup_simulation(_args.robot)

from robot.bilbo import BILBO


def main():
    bilbo = BILBO(simulation=True)
    bilbo.init()
    bilbo.start()

    while True:
        time.sleep(100)


if __name__ == '__main__':
    main()
