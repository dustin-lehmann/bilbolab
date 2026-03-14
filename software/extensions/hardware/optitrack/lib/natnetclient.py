# Copyright © 2018 Naturalpoint
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Universal NatNetClient for Motive 2.x (NatNet 3.x) and Motive 3.0+ (NatNet 4.x)

This client automatically detects the NatNet version and adapts accordingly.
It provides a unified interface that works with both old and new systems.
"""

import socket
import struct
import time
from threading import Thread
from typing import Callable

from core.utils.logging_utils import Logger


def trace(*args):
    ...
    # print("".join(map(str, args)))


# Create structs for reading various object types to speed up parsing.
Vector3 = struct.Struct('<fff')
Quaternion = struct.Struct('<ffff')
FloatValue = struct.Struct('<f')
DoubleValue = struct.Struct('<d')


class NatNetClient:
    """
    Universal NatNet client that works with both NatNet 3.x (Motive 2) and 4.x (Motive 3+)
    """

    # Client/server message ids - Compatible with both versions
    NAT_PING = 0
    NAT_PINGRESPONSE = 1
    NAT_CONNECT = 0
    NAT_SERVERINFO = 1
    NAT_REQUEST = 2
    NAT_RESPONSE = 3
    NAT_REQUEST_MODELDEF = 4
    NAT_MODELDEF = 5
    NAT_REQUEST_FRAMEOFDATA = 6
    NAT_FRAMEOFDATA = 7
    NAT_MESSAGESTRING = 8
    NAT_DISCONNECT = 9
    NAT_KEEPALIVE = 10
    NAT_UNRECOGNIZED_REQUEST = 100

    def __init__(self, server_address: str, multicast_address: str = "239.255.42.99",
                 local_address: str = "0.0.0.0", use_multicast: bool = True):
        """
        Initialize the universal NatNet client.

        Args:
            server_address: IP address of the Motive server
            multicast_address: Multicast address for data streaming
            local_address: Local IP address to bind to
            use_multicast: Whether to use multicast (True) or unicast (False)
        """
        self.server_address = server_address
        self.multicast_address = multicast_address
        self.local_address = local_address
        self.use_multicast = use_multicast

        # NatNet ports
        self.command_port = 1510
        self.data_port = 1511

        # Callbacks (interface expected by optitrack.py)
        self.mocap_data_callback: Callable | None = None
        self.description_message_callback: Callable | None = None

        # NatNet version info - will be set during connection
        self._nat_net_version = [0, 0, 0, 0]
        self._server_version = [0, 0, 0, 0]
        self._application_name = ""

        # Compatibility - provide natNetStreamVersion for old interface
        self._natNetStreamVersion = (3, 0, 0, 0)

        # Sockets and threads
        self.data_socket: socket.socket | None = None
        self.command_socket: socket.socket | None = None
        self._data_thread: Thread | None = None
        self._command_thread: Thread | None = None
        self._stop_threads = False

        # Track which protocol version we're using
        self._protocol_version_4 = False

        self.logger = Logger("NatNetClient", 'DEBUG')

    # === PROPERTIES ===

    @property
    def natNetStreamVersion(self) -> tuple:
        """Return NatNet version as tuple for compatibility."""
        return tuple(self._nat_net_version)

    @property
    def major(self) -> int:
        return self._nat_net_version[0]

    @property
    def minor(self) -> int:
        return self._nat_net_version[1]

    # === SOCKET MANAGEMENT ===

    def _create_data_socket(self, port: int) -> socket.socket | None:
        """Create a data socket for receiving NatNet data."""
        try:
            result = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            result.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            if self.use_multicast:
                result.setsockopt(
                    socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                    socket.inet_aton(self.multicast_address) + socket.inet_aton(self.local_address)
                )
                result.bind((self.local_address, port))
            else:
                result.bind(('', 0))
                if self.multicast_address != "255.255.255.255":
                    result.setsockopt(
                        socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                        socket.inet_aton(self.multicast_address) + socket.inet_aton(self.local_address)
                    )

            return result
        except socket.error as e:
            self.logger.error(f"ERROR: Could not create data socket: {e}")
            return None

    def _create_command_socket(self) -> socket.socket | None:
        """Create a command socket for NatNet commands."""
        try:
            if self.use_multicast:
                result = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
                result.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                result.bind(('', 0))
                result.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            else:
                result = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                result.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                result.bind((self.local_address, 0))

            result.settimeout(2.0)
            return result
        except socket.error as e:
            self.logger.error(f"ERROR: Could not create command socket: {e}")
            return None

    # === MESSAGE SENDING ===

    def _send_request(self, sock: socket.socket, command: int, command_str: str = "") -> int:
        """Send a request to the NatNet server."""
        packet_size = 0

        if command == self.NAT_REQUEST_MODELDEF or command == self.NAT_REQUEST_FRAMEOFDATA:
            packet_size = 0
            command_str = ""
        elif command == self.NAT_REQUEST:
            packet_size = len(command_str) + 1
        elif command == self.NAT_CONNECT:
            # Build connection packet with version request for NatNet 4.x
            command_bytes = bytearray(270)
            command_bytes[0:4] = b'Ping'
            command_bytes[265] = 4  # Request NatNet 4
            command_bytes[266] = 1
            command_bytes[267] = 0
            command_bytes[268] = 0
            packet_size = len(command_bytes) + 1

            data = command.to_bytes(2, byteorder='little', signed=True)
            data += packet_size.to_bytes(2, byteorder='little', signed=True)
            data += command_bytes
            data += b'\0'

            return sock.sendto(data, (self.server_address, self.command_port))
        elif command == self.NAT_KEEPALIVE:
            packet_size = 0
            command_str = ""
        elif command == self.NAT_PING:
            # Old-style ping for NatNet 3.x
            command_str = "Ping"
            packet_size = len(command_str) + 1

        data = command.to_bytes(2, byteorder='little', signed=True)
        data += packet_size.to_bytes(2, byteorder='little', signed=True)
        data += command_str.encode('utf-8')
        data += b'\0'

        return sock.sendto(data, (self.server_address, self.command_port))

    # === MESSAGE UNPACKING ===

    def _unpack_server_info(self, data: bytes) -> int:
        """Unpack server info response (NatNet 4.x)."""
        offset = 0

        # Application name (256 bytes)
        app_name, _, _ = bytes(data[offset:offset + 256]).partition(b'\0')
        self._application_name = app_name.decode('utf-8')
        offset += 256

        # Server version (4 bytes)
        self._server_version = list(struct.unpack('BBBB', data[offset:offset + 4]))
        offset += 4

        # NatNet version (4 bytes)
        server_nn_version = list(struct.unpack('BBBB', data[offset:offset + 4]))
        offset += 4

        self._nat_net_version = server_nn_version
        self._natNetStreamVersion = tuple(server_nn_version)
        self._protocol_version_4 = True

        self.logger.debug(f"NatNetClient: Connecting to Motive server at {self.server_address}...")
        self.logger.debug(f"NatNetClient: Connected to {self._application_name}")
        self.logger.debug(f"NatNetClient: Server version {self._server_version[0]}.{self._server_version[1]}.{self._server_version[2]}.{self._server_version[3]}")
        self.logger.debug(f"NatNetClient: NatNet version {server_nn_version[0]}.{server_nn_version[1]}.{server_nn_version[2]}.{server_nn_version[3]}")

        return offset

    def _unpack_rigid_body(self, data: memoryview) -> tuple[int, dict]:
        """Unpack a single rigid body from frame data."""
        offset = 0
        rb_data = {}

        # ID (4 bytes)
        rb_id = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
        offset += 4
        rb_data['id'] = rb_id

        # Position (12 bytes)
        pos = Vector3.unpack(data[offset:offset + 12])
        offset += 12
        rb_data['position'] = pos

        # Orientation (16 bytes)
        rot = Quaternion.unpack(data[offset:offset + 16])
        offset += 16
        rb_data['orientation'] = rot

        # Marker error (4 bytes) - version 2.0+
        if self.major >= 2:
            marker_error, = FloatValue.unpack(data[offset:offset + 4])
            offset += 4
            rb_data['marker_error'] = marker_error

        # Tracking valid (2 bytes) - version 2.6+
        if (self.major == 2 and self.minor >= 6) or self.major > 2:
            param, = struct.unpack('h', data[offset:offset + 2])
            offset += 2
            rb_data['tracking_valid'] = (param & 0x01) != 0

        return offset, rb_data

    def _unpack_data_size(self, data: memoryview) -> tuple[int, int]:
        """Unpack data size field (NatNet 4.1+)."""
        offset = 0
        size_in_bytes = 0

        if (self.major == 4 and self.minor > 0) or self.major > 4:
            size_in_bytes = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
            offset += 4

        return offset, size_in_bytes

    def _unpack_mocap_data(self, data: bytes, packet_size: int = 0) -> dict:
        """Unpack motion capture frame data (compatible with both NatNet 3 and 4)."""
        mocap_data = {
            'rigid_bodies': {},
            'marker_sets': {},
            'labeled_markers': {},
        }
        data = memoryview(data)
        offset = 0

        # Frame number (4 bytes)
        frame_number = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
        offset += 4
        mocap_data['frame'] = frame_number

        # Marker set count (4 bytes)
        marker_set_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
        offset += 4

        # Data size (NatNet 4.1+)
        off_tmp, _ = self._unpack_data_size(data[offset:])
        offset += off_tmp

        # Marker sets
        for _ in range(marker_set_count):
            # Model name
            model_name, _, _ = bytes(data[offset:]).partition(b'\0')
            offset += len(model_name) + 1
            ms_name = model_name.decode('utf-8')

            # Marker count
            marker_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
            offset += 4

            mocap_data['marker_sets'][ms_name] = {}
            for j in range(marker_count):
                pos = Vector3.unpack(data[offset:offset + 12])
                offset += 12
                mocap_data['marker_sets'][ms_name][j + 1] = pos  # 1-indexed

        # Legacy other markers count (4 bytes)
        other_marker_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
        offset += 4

        # Data size (NatNet 4.1+)
        off_tmp, _ = self._unpack_data_size(data[offset:])
        offset += off_tmp

        # Skip legacy other markers
        offset += other_marker_count * 12

        # Rigid body count (4 bytes)
        rigid_body_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
        offset += 4

        # Data size (NatNet 4.1+)
        off_tmp, _ = self._unpack_data_size(data[offset:])
        offset += off_tmp

        # Rigid bodies
        for _ in range(rigid_body_count):
            off_tmp, rb_data = self._unpack_rigid_body(data[offset:])
            offset += off_tmp
            mocap_data['rigid_bodies'][rb_data['id']] = rb_data

        # Skeleton count (4 bytes) - version 2.1+
        skeleton_count = 0
        if (self.major == 2 and self.minor > 0) or self.major > 2:
            skeleton_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
            offset += 4

            # Data size (NatNet 4.1+)
            off_tmp, _ = self._unpack_data_size(data[offset:])
            offset += off_tmp

            # Skip skeleton data (not commonly used)
            for _ in range(skeleton_count):
                offset += 4  # skeleton ID
                rb_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                offset += 4
                for _ in range(rb_count):
                    off_tmp, _ = self._unpack_rigid_body(data[offset:])
                    offset += off_tmp

        # Asset count (NatNet 4.1+)
        if (self.major == 4 and self.minor > 0) or self.major > 4:
            asset_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
            offset += 4

            # Data size
            off_tmp, _ = self._unpack_data_size(data[offset:])
            offset += off_tmp

            # Skip asset data
            for _ in range(asset_count):
                offset += 4  # asset ID

                # Rigid bodies in asset
                num_rbs = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                offset += 4
                for _ in range(num_rbs):
                    offset += 4 + 12 + 16 + 4 + 2  # ID, pos, rot, error, params

                # Markers in asset
                num_markers = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                offset += 4
                for _ in range(num_markers):
                    offset += 4 + 12 + 4 + 2 + 4  # ID, pos, size, params, residual

        # Labeled markers (version 2.3+)
        if (self.major == 2 and self.minor > 3) or self.major > 2:
            labeled_marker_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
            offset += 4

            # Data size (NatNet 4.1+)
            off_tmp, _ = self._unpack_data_size(data[offset:])
            offset += off_tmp

            for _ in range(labeled_marker_count):
                marker_id = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                offset += 4

                pos = Vector3.unpack(data[offset:offset + 12])
                offset += 12

                size = FloatValue.unpack(data[offset:offset + 4])
                offset += 4

                # Version 2.6+ params
                if (self.major == 2 and self.minor >= 6) or self.major > 2:
                    offset += 2  # param

                # Version 3.0+ residual
                if self.major >= 3:
                    offset += 4  # residual

                mocap_data['labeled_markers'][marker_id] = {
                    'id': marker_id,
                    'size': size,
                    'pos': pos
                }

        # Force plate data (version 2.9+)
        if (self.major == 2 and self.minor >= 9) or self.major > 2:
            force_plate_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
            offset += 4

            # Data size (NatNet 4.1+)
            off_tmp, _ = self._unpack_data_size(data[offset:])
            offset += off_tmp

            for _ in range(force_plate_count):
                offset += 4  # force plate ID
                channel_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                offset += 4
                for _ in range(channel_count):
                    frame_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                    offset += 4
                    offset += frame_count * 4

        # Device data (version 2.11+)
        if (self.major == 2 and self.minor >= 11) or self.major > 2:
            device_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
            offset += 4

            # Data size (NatNet 4.1+)
            off_tmp, _ = self._unpack_data_size(data[offset:])
            offset += off_tmp

            for _ in range(device_count):
                offset += 4  # device ID
                channel_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                offset += 4
                for _ in range(channel_count):
                    frame_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                    offset += 4
                    offset += frame_count * 4

        # Timecode
        offset += 8  # timecode + timecode_sub

        # Timestamp (double precision in version 2.7+)
        if (self.major == 2 and self.minor >= 7) or self.major > 2:
            timestamp, = DoubleValue.unpack(data[offset:offset + 8])
            offset += 8
        else:
            timestamp, = FloatValue.unpack(data[offset:offset + 4])
            offset += 4

        mocap_data['timestamp'] = timestamp

        # Hires timestamps (version 3.0+)
        if self.major >= 3:
            offset += 24  # 3 x 8 bytes

        # Precision timestamps (version 4.0+)
        if self.major >= 4:
            offset += 8  # 2 x 4 bytes

        return mocap_data

    def _unpack_rigid_body_description(self, data: memoryview) -> tuple[int, dict]:
        """Unpack a rigid body description."""
        offset = 0
        rb_desc = {}

        # Name (version 2.0+)
        if self.major >= 2:
            name, _, _ = bytes(data[offset:]).partition(b'\0')
            offset += len(name) + 1
            rb_desc['name'] = name.decode('utf-8')

        # ID (4 bytes)
        rb_id = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
        offset += 4
        rb_desc['id'] = rb_id

        # Parent ID (4 bytes)
        offset += 4

        # Position offset (12 bytes)
        offset += 12

        # Marker info (version 3.0+)
        if self.major >= 3:
            marker_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
            offset += 4

            rb_desc['marker_count'] = marker_count
            rb_desc['markers'] = {}

            # Calculate offsets for marker data sections
            offset1 = offset  # Marker offsets (12 bytes each)
            offset2 = offset1 + (12 * marker_count)  # Active labels (4 bytes each)
            offset3 = offset2 + (4 * marker_count)  # Marker names (version 4.0+)

            for marker_idx in range(marker_count):
                marker_id = marker_idx + 1  # 1-indexed

                # Marker offset (12 bytes)
                marker_offset = Vector3.unpack(data[offset1:offset1 + 12])
                offset1 += 12

                # Active label (4 bytes)
                offset2 += 4

                # Marker name (version 4.0+)
                if self.major >= 4:
                    marker_name, _, _ = bytes(data[offset3:]).partition(b'\0')
                    offset3 += len(marker_name) + 1

                rb_desc['markers'][marker_id] = {
                    'id': marker_id,
                    'offset': marker_offset
                }

            offset = offset3 if self.major >= 4 else offset2

        return offset, rb_desc

    def _unpack_marker_set_description(self, data: memoryview) -> tuple[int, dict]:
        """Unpack a marker set description."""
        offset = 0
        ms_desc = {}

        # Name
        name, _, _ = bytes(data[offset:]).partition(b'\0')
        offset += len(name) + 1
        ms_desc['name'] = name.decode('utf-8')

        # Marker count
        marker_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
        offset += 4
        ms_desc['marker_count'] = marker_count

        ms_desc['markers'] = {}
        for i in range(marker_count):
            marker_name, _, _ = bytes(data[offset:]).partition(b'\0')
            offset += len(marker_name) + 1
            ms_desc['markers'][i] = marker_name.decode('utf-8')

        return offset, ms_desc

    def _unpack_data_descriptions(self, data: bytes, packet_size: int = 0) -> dict:
        """Unpack model definitions."""
        descriptions = {
            'rigid_bodies': {},
            'marker_sets': {}
        }

        offset = 0

        # Dataset count
        dataset_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
        offset += 4

        for _ in range(dataset_count):
            # Data type
            data_type = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
            offset += 4

            # Data size (NatNet 4.1+)
            if (self.major == 4 and self.minor >= 1) or self.major > 4:
                offset += 4  # size_in_bytes

            if data_type == 0:  # Marker Set
                off_tmp, ms_desc = self._unpack_marker_set_description(memoryview(data[offset:]))
                offset += off_tmp
                descriptions['marker_sets'][ms_desc['name']] = ms_desc

            elif data_type == 1:  # Rigid Body
                off_tmp, rb_desc = self._unpack_rigid_body_description(memoryview(data[offset:]))
                offset += off_tmp
                descriptions['rigid_bodies'][rb_desc['name']] = rb_desc

            elif data_type == 2:  # Skeleton
                # Skip skeleton description
                name, _, _ = bytes(data[offset:]).partition(b'\0')
                offset += len(name) + 1
                offset += 4  # ID
                rb_count = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                offset += 4
                for _ in range(rb_count):
                    off_tmp, _ = self._unpack_rigid_body_description(memoryview(data[offset:]))
                    offset += off_tmp

            elif data_type == 3:  # Force Plate
                # Skip force plate description (version 3.0+)
                if self.major >= 3:
                    offset += 4  # ID
                    serial, _, _ = bytes(data[offset:]).partition(b'\0')
                    offset += len(serial) + 1
                    offset += 8  # dimensions
                    offset += 12  # origin
                    offset += 12 * 12 * 4  # cal matrix
                    offset += 4 * 3 * 4  # corners
                    offset += 4  # plate type
                    offset += 4  # channel data type
                    num_channels = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                    offset += 4
                    for _ in range(num_channels):
                        ch_name, _, _ = bytes(data[offset:]).partition(b'\0')
                        offset += len(ch_name) + 1

            elif data_type == 4:  # Device
                # Skip device description (version 3.0+)
                if self.major >= 3:
                    offset += 4  # ID
                    name, _, _ = bytes(data[offset:]).partition(b'\0')
                    offset += len(name) + 1
                    serial, _, _ = bytes(data[offset:]).partition(b'\0')
                    offset += len(serial) + 1
                    offset += 4  # device type
                    offset += 4  # channel data type
                    num_channels = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                    offset += 4
                    for _ in range(num_channels):
                        ch_name, _, _ = bytes(data[offset:]).partition(b'\0')
                        offset += len(ch_name) + 1

            elif data_type == 5:  # Camera
                # Skip camera description
                name, _, _ = bytes(data[offset:]).partition(b'\0')
                offset += len(name) + 1
                offset += 12  # position
                offset += 16  # orientation

            elif data_type == 6:  # Asset (NatNet 4.1+)
                # Skip asset description
                name, _, _ = bytes(data[offset:]).partition(b'\0')
                offset += len(name) + 1
                offset += 4  # asset type
                offset += 4  # asset ID

                # Rigid bodies
                num_rbs = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                offset += 4
                for _ in range(num_rbs):
                    off_tmp, _ = self._unpack_rigid_body_description(memoryview(data[offset:]))
                    offset += off_tmp

                # Markers
                num_markers = int.from_bytes(data[offset:offset + 4], byteorder='little', signed=True)
                offset += 4
                for _ in range(num_markers):
                    m_name, _, _ = bytes(data[offset:]).partition(b'\0')
                    offset += len(m_name) + 1
                    offset += 4 + 12 + 4 + 2  # ID, pos, size, params

        return descriptions

    def _process_message(self, data: bytes) -> int:
        """Process a received NatNet message."""
        message_id = int.from_bytes(data[0:2], byteorder='little', signed=True)
        packet_size = int.from_bytes(data[2:4], byteorder='little', signed=True)

        offset = 4

        if message_id == self.NAT_FRAMEOFDATA:
            try:
                mocap_data = self._unpack_mocap_data(data[offset:], packet_size)
                if self.mocap_data_callback is not None:
                    self.mocap_data_callback(mocap_data)
            except Exception as e:
                self.logger.error(f"NatNetClient: Error unpacking frame data: {e}")

        elif message_id == self.NAT_MODELDEF:
            try:
                descriptions = self._unpack_data_descriptions(data[offset:], packet_size)
                rb_names = list(descriptions.get('rigid_bodies', {}).keys())
                self.logger.debug(f"NatNetClient: Received model definitions - {len(rb_names)} rigid bodies: {rb_names}")
                if self.description_message_callback is not None:
                    self.description_message_callback(descriptions)
            except Exception as e:
                self.logger.error(f"NatNetClient: Error unpacking model definitions: {e}")

        elif message_id == self.NAT_PINGRESPONSE:
            # Handle both NatNet 3.x and 4.x PING responses
            if not self._protocol_version_4:
                offset += 256  # Skip the sending app's Name field
                offset += 4  # Skip the sending app's Version info
                version = struct.unpack('BBBB', data[offset:offset + 4])
                self._nat_net_version = list(version)
                self._natNetStreamVersion = version
                self.logger.debug(f"NatNetClient: Connecting to Motive server at {self.server_address}...")
                self.logger.debug(f"NatNetClient: NatNet version {version[0]}.{version[1]}.{version[2]}.{version[3]}")

        elif message_id == self.NAT_SERVERINFO:
            self._unpack_server_info(data[offset:])

        elif message_id == self.NAT_RESPONSE:
            pass  # Command response - typically ignored

        elif message_id == self.NAT_UNRECOGNIZED_REQUEST:
            self.logger.error("Received 'Unrecognized request' from server")

        elif message_id == self.NAT_MESSAGESTRING:
            message, _, _ = bytes(data[offset:]).partition(b'\0')
            self.logger.debug(f"Server message: {message.decode('utf-8')}")

        return message_id

    def _data_thread_function(self):
        """Thread function for receiving data packets."""
        recv_buffer_size = 64 * 1024

        while not self._stop_threads:
            try:
                data, _ = self.data_socket.recvfrom(recv_buffer_size)
                if len(data) > 0:
                    self._process_message(data)
            except socket.timeout:
                pass
            except socket.error as e:
                if not self._stop_threads:
                    self.logger.error(f"Data socket error: {e}")
                break

    def _command_thread_function(self):
        """Thread function for receiving command responses."""
        recv_buffer_size = 64 * 1024

        while not self._stop_threads:
            try:
                data, _ = self.command_socket.recvfrom(recv_buffer_size)
                if len(data) > 0:
                    self._process_message(data)
            except socket.timeout:
                # Send keep-alive to maintain connection (required for NatNet 4.x / Motive 3+)
                if not self._stop_threads:
                    try:
                        self._send_request(self.command_socket, self.NAT_KEEPALIVE)
                    except (socket.error, OSError):
                        break
            except socket.error as e:
                if not self._stop_threads:
                    self.logger.error(f"Command socket error: {e}")
                break

    def run(self):
        """Start the NatNet client."""
        # Create sockets
        self.data_socket = self._create_data_socket(self.data_port)
        if self.data_socket is None:
            raise RuntimeError("Could not create data socket")

        self.command_socket = self._create_command_socket()
        if self.command_socket is None:
            raise RuntimeError("Could not create command socket")

        self._stop_threads = False

        # Start threads
        self._data_thread = Thread(target=self._data_thread_function, daemon=True)
        self._data_thread.start()

        self._command_thread = Thread(target=self._command_thread_function, daemon=True)
        self._command_thread.start()

        self._keep_alive_thread = Thread(target=self.run_alive_thread, daemon=True)
        self._keep_alive_thread.start()

        # Try NatNet 4.x protocol first (works with both new and old systems)
        self.logger.debug(f"Connecting to Motive server at {self.server_address}...")
        self._send_request(self.command_socket, self.NAT_CONNECT)
        self.request_model_definitions()

    def run_alive_thread(self):
        while not self._stop_threads:
            try:
                self._send_request(self.command_socket, self.NAT_KEEPALIVE)
            except (socket.error, OSError):
                break
            time.sleep(2)

    def close(self):
        """Stop the NatNet client and clean up resources."""
        self._stop_threads = True

        if self.command_socket:
            try:
                self.command_socket.close()
            except Exception:
                pass

        if self.data_socket:
            try:
                self.data_socket.close()
            except Exception:
                pass

        if self._command_thread and self._command_thread.is_alive():
            self._command_thread.join(timeout=1.0)

        if self._data_thread and self._data_thread.is_alive():
            self._data_thread.join(timeout=1.0)

        if self._keep_alive_thread and self._keep_alive_thread.is_alive():
            self._keep_alive_thread.join(timeout=1.0)




    def request_model_definitions(self):
        """Request model definitions from the server."""
        if self.command_socket:
            self._send_request(self.command_socket, self.NAT_REQUEST_MODELDEF)
