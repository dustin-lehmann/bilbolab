"""
Universal OptiTrack NatNet client for Motive 2.x (NatNet 3.x) and Motive 3.0+ (NatNet 4.x)

This module provides a drop-in replacement that automatically detects the NatNet version
and uses the appropriate marker extraction method.

Example:
    from extensions.hardware.optitrack import OptiTrack

    optitrack = OptiTrack(server_address='192.168.8.131')
    optitrack.init()
    optitrack.start()
"""

from extensions.hardware.optitrack.optitrack import (
    OptiTrack,
    RigidBodySample,
    RigidBodyDescription,
    MarkerDescription,
    OptiTrack_Callbacks,
    OptiTrack_Events,
)

__all__ = [
    'OptiTrack',
    'RigidBodySample',
    'RigidBodyDescription',
    'MarkerDescription',
    'OptiTrack_Callbacks',
    'OptiTrack_Events',
]
