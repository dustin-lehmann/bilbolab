"""Pytest conftest for simulation tests.

Installs mock hardware modules before any robot imports happen,
so tests can run on a dev machine without RPi hardware or pyserial.
"""
from simulation.mock_hardware import install_mock_hardware

install_mock_hardware()
