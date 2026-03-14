import dataclasses
import threading
import time
from collections import deque

import numpy

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger
from core.utils.orientation.orientation_3d import transform_vector_from_a_to_b_frame
from extensions.hardware.optitrack.lib.natnetclient import NatNetClient


# ======================================================================================================================
@dataclasses.dataclass(slots=True)
class RigidBodySample:
    name: str
    id: int
    valid: bool
    position: numpy.ndarray
    orientation: numpy.ndarray
    markers: dict[int, numpy.ndarray]
    markers_raw: dict[int, numpy.ndarray | None]


# ======================================================================================================================
@dataclasses.dataclass(slots=True)
class MarkerDescription:
    name: str
    id: int
    label: int
    size: None | float
    # Store as numpy array to avoid per-frame conversions
    offset: numpy.ndarray


# ======================================================================================================================
@dataclasses.dataclass(slots=True)
class RigidBodyDescription:
    name: str
    id: int
    marker_count: int
    markers: dict[int, MarkerDescription]


# ======================================================================================================================
@callback_definition
class OptiTrack_Callbacks:
    sample: CallbackContainer
    description_received: CallbackContainer


# ======================================================================================================================
@event_definition
class OptiTrack_Events:
    sample: Event
    description_received: Event


# ======================================================================================================================
class OptiTrack:
    """
    Universal OptiTrack client that works with both NatNet 3.x (Motive 2) and 4.x (Motive 3+)

    Automatically detects the NatNet version and uses the appropriate method for marker extraction:
    - NatNet 3.x: Calculates marker positions from rigid body pose + marker offsets (with y-up→z-up conversion)
    - NatNet 4.x: Uses marker positions directly from frame data (no conversion needed)
    """

    callbacks: OptiTrack_Callbacks
    events: OptiTrack_Events
    natnetclient: NatNetClient

    rigid_bodies: dict[str, RigidBodyDescription]

    description_received: bool
    first_data_frame_received: bool

    running: bool
    max_sample_rate: int

    # internal: frame queue & processing thread
    _frame_queue: deque
    _queue_lock: threading.Lock
    _processor_thread: threading.Thread | None
    _min_dt: float
    _last_emit_t: float

    # NatNet version tracking
    _natnet_major_version: int
    _natnet_uses_direct_markers: bool

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, server_address, max_sample_rate=30, multicast_address="239.255.42.99",
                 local_address="0.0.0.0", use_multicast=True):
        """
        server_address: IP/hostname of the OptiTrack streaming server
        max_sample_rate: Hz, upper bound for how often samples are emitted to your callbacks/events
        multicast_address: Multicast address for data streaming (default: 239.255.42.99)
        local_address: Local IP address to bind to (default: 0.0.0.0)
        use_multicast: Whether to use multicast (True) or unicast (False) (default: True)
        """
        self.natnetclient = NatNetClient(
            server_address=server_address,
            multicast_address=multicast_address,
            local_address=local_address,
            use_multicast=use_multicast
        )
        # Make the NatNet callbacks as light as possible
        self.natnetclient.mocap_data_callback = self._natnet_mocap_data_callback
        self.natnetclient.description_message_callback = self._natnet_description_callback

        self.max_sample_rate = int(max_sample_rate)
        self._min_dt = 1.0 / max(1, self.max_sample_rate)
        self._last_emit_t = 0.0

        self.logger = Logger("OptiTrack")
        self.logger.setLevel('INFO')

        self.rigid_bodies = {}
        self.description_received = False
        self.first_data_frame_received = False
        self.running = False

        self.callbacks = OptiTrack_Callbacks()
        self.events = OptiTrack_Events()

        # A single-slot queue that always holds the most recent frame only.
        self._frame_queue = deque(maxlen=1)
        self._queue_lock = threading.Lock()
        self._processor_thread = None

        # NatNet version tracking
        self._natnet_major_version = 0
        self._natnet_uses_direct_markers = False

    # === METHODS ======================================================================================================

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        # Start processing thread first so we're ready as soon as frames arrive
        self.running = True
        self._processor_thread = threading.Thread(target=self._processing_loop, name="OptiTrackProcessor", daemon=True)
        self._processor_thread.start()
        self.logger.info("Starting OptiTrack client")
        try:
            self.natnetclient.run()
        except Exception as e:
            self.logger.warning("Error while starting NatNetClient. Please make sure that Motive is running")
            self.running = False
            return False


        return True

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.running = False
        # NatNetClient likely has its own close/stop; if available, call it here.
        try:
            if hasattr(self.natnetclient, "close"):
                self.natnetclient.close()
        except Exception:
            pass
        # Join processor thread (best-effort)
        t = self._processor_thread
        if t and t.is_alive():
            t.join(timeout=1.0)

    # === PRIVATE METHODS ==============================================================================================
    def _natnet_description_callback(self, data):
        """
        Process model definitions from NatNet.
        Detect NatNet version and configure marker extraction method accordingly.
        """
        # Detect NatNet version from client
        self._natnet_major_version = self.natnetclient.major
        # NatNet 4.0+ sends marker positions directly in frame data
        self._natnet_uses_direct_markers = self._natnet_major_version >= 4

        self.logger.info(f"NatNet version detected: {self._natnet_major_version}.{self.natnetclient.minor}")
        if self._natnet_uses_direct_markers:
            self.logger.info("Using direct marker positions from frame data (NatNet 4.x behavior)")
        else:
            self.logger.info("Using calculated marker positions from rigid body pose + offsets (NatNet 3.x behavior)")
            if self._natnet_major_version == 3:
                self.logger.info("Applying y-up → z-up coordinate conversion for marker offsets")

        # Rigid Bodies
        for name, rigid_body_data in data.get("rigid_bodies", {}).items():
            rigid_body_id = rigid_body_data["id"]
            marker_count = rigid_body_data["marker_count"]
            markers: dict[int, MarkerDescription] = {}

            for marker_id, marker_description in rigid_body_data.get("markers", {}).items():
                marker_offset_raw = marker_description["offset"]

                # For NatNet 3.x: Apply y-up → z-up conversion
                # (marker offsets are sent in y-up even though streaming data is z-up)
                if self._natnet_major_version == 3:
                    marker_offset = [0.0] * 3
                    marker_offset[0] = -marker_offset_raw[0]
                    marker_offset[1] = -marker_offset_raw[2]
                    marker_offset[2] = marker_offset_raw[1]
                else:
                    # For NatNet 4.x+: Use directly (already in z-up)
                    marker_offset = marker_offset_raw

                # Store offset as numpy array once to avoid per-frame asarray allocations
                marker_offset_np = numpy.asarray(marker_offset, dtype=float)

                marker_size = None
                label = self._encode_marker_label(asset_id=rigid_body_id, marker_index=marker_id)
                marker_desc = MarkerDescription(
                    id=marker_id,
                    offset=marker_offset_np,
                    size=marker_size,
                    name='',
                    label=label
                )
                markers[marker_id] = marker_desc

            rigid_body_description = RigidBodyDescription(
                name=rigid_body_data["name"],
                id=rigid_body_id,
                marker_count=marker_count,
                markers=markers,
            )

            self.rigid_bodies[rigid_body_data["name"]] = rigid_body_description

        self.description_received = True

        self.callbacks.description_received.call(self.rigid_bodies)
        self.events.description_received.set(self.rigid_bodies)

    # ------------------------------------------------------------------------------------------------------------------
    def _natnet_mocap_data_callback(self, data):
        """
        SUPER LIGHT callback: just stash the latest frame and return immediately.
        Heavy work is done in _processing_loop at a controlled rate.
        """
        if not self.description_received:
            return
        with self._queue_lock:
            # Only keep most recent frame; older one is dropped automatically by maxlen=1
            self._frame_queue.append((time.perf_counter(), data))

    # ------------------------------------------------------------------------------------------------------------------
    def _processing_loop(self):
        """
        Consumes latest frames (if any) at or below max_sample_rate,
        converts them to RigidBodySample, and fires callbacks/events.
        """
        # Wait until we have descriptions
        while self.running and not self.description_received:
            time.sleep(0.001)

        while self.running:
            frame = None
            with self._queue_lock:
                if self._frame_queue:
                    frame = self._frame_queue.pop()  # get latest and clear queue
                    self._frame_queue.clear()

            if frame is None:
                time.sleep(0.0005)
                continue

            now = time.perf_counter()
            # Rate limit
            if (now - self._last_emit_t) < self._min_dt:
                # Too soon; skip processing this frame (keep loop snappy)
                continue

            _, data = frame

            if not self.first_data_frame_received:
                self._extract_initial_mocap_information(data)
                self.first_data_frame_received = True
                self.logger.info("OptiTrack running!")
                self.logger.info(f"Rigid bodies: {[body.name for body in self.rigid_bodies.values()]}")

            # Build sample (heavy part moved from NatNet thread to here)
            sample = self._build_sample(data)

            # Fire callbacks outside of locks
            for callback in self.callbacks.sample:
                try:
                    callback(sample)
                except Exception as e:
                    self.logger.error(f"Error in user sample callback: {e}")

            self.events.sample.set(data=sample)

            self._last_emit_t = now

    # ------------------------------------------------------------------------------------------------------------------
    def _build_sample(self, data) -> dict[str, RigidBodySample]:
        sample: dict[str, RigidBodySample] = {}

        rigid_bodies_local = self.rigid_bodies
        data_rb = data.get('rigid_bodies', {})
        data_marker_sets = data.get('marker_sets', {})

        for rigid_body_name, rigid_body_description in rigid_bodies_local.items():
            rbd = data_rb.get(rigid_body_description.id)
            if rbd is None:
                # Missing rigid body in this frame – mark invalid but keep structure
                sample[rigid_body_name] = RigidBodySample(
                    name=rigid_body_name,
                    id=rigid_body_description.id,
                    valid=False,
                    position=numpy.zeros(3, dtype=float),
                    orientation=numpy.array([1.0, 0.0, 0.0, 0.0], dtype=float),  # identity quaternion (wxyz)
                    markers={},
                    markers_raw={}
                )
                continue

            # Extract position/orientation
            # Using asarray without copy when possible
            position = numpy.asarray(rbd['position'], dtype=float)

            # incoming XYZW -> our WXYZ
            ox, oy, oz, ow = rbd['orientation']
            orientation = numpy.asarray([ow, ox, oy, oz], dtype=float)

            tracking_valid = bool(rbd.get('tracking_valid', True))

            # Marker set for this RB (if any)
            msd = data_marker_sets.get(rigid_body_description.name)

            markers: dict[int, numpy.ndarray] = {}
            markers_raw: dict[int, numpy.ndarray | None] = {}

            if self._natnet_uses_direct_markers and msd:
                # NatNet 4.x: Use marker positions directly from frame data
                for marker_idx, marker_pos in msd.items():
                    markers[marker_idx] = numpy.asarray(marker_pos, dtype=float)
                    markers_raw[marker_idx] = None  # Not used in this mode
            else:
                # NatNet 3.x: Calculate marker positions from rigid body pose + offsets
                for marker_id, marker_desc in rigid_body_description.markers.items():
                    # Raw marker (if present)
                    if msd:
                        raw = msd.get(marker_id)
                        marker_position_raw = numpy.asarray(list(raw), dtype=float) if raw is not None else None
                    else:
                        marker_position_raw = None

                    # Solved position from pose + offset
                    marker_position_solved = self._calculate_rigid_body_marker(
                        rigid_body_position=position,
                        rigid_body_orientation=orientation,
                        marker_offset=marker_desc.offset  # already numpy array
                    )

                    markers[marker_id] = marker_position_solved
                    markers_raw[marker_id] = marker_position_raw

            rigid_body_sample = RigidBodySample(
                name=rigid_body_name,
                id=rigid_body_description.id,
                valid=tracking_valid,
                position=position,
                orientation=orientation,
                markers=markers,
                markers_raw=markers_raw
            )
            sample[rigid_body_name] = rigid_body_sample

        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def _extract_initial_mocap_information(self, data):
        labeled = data.get('labeled_markers', {})

        for rigid_body_name, rigid_body_description in self.rigid_bodies.items():
            # First pass: fill sizes from visible labeled markers
            for marker_id, marker_description in rigid_body_description.markers.items():
                if marker_description.label in labeled:
                    marker_size = labeled[marker_description.label]['size'][0]
                    marker_description.size = marker_size
                else:
                    self.logger.debug(
                        f"Marker {marker_id} of rigid body \"{rigid_body_name}\" not visible, "
                        f"size will be inferred"
                    )

            # Second pass: infer missing sizes
            sizes = [md.size for md in rigid_body_description.markers.values() if md.size is not None]
            missing_count = sum(1 for md in rigid_body_description.markers.values() if md.size is None)
            if not sizes:
                self.logger.debug(f"No markers of rigid body \"{rigid_body_name}\" are visible, inferring sizes")
                inferred = 0.0
            else:
                if missing_count > 0:
                    self.logger.debug(
                        f"{missing_count}/{rigid_body_description.marker_count} markers of "
                        f"\"{rigid_body_name}\" not visible, inferring sizes"
                    )
                inferred = float(sum(sizes) / len(sizes))
            for md in rigid_body_description.markers.values():
                if md.size is None:
                    md.size = inferred

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _encode_marker_label(asset_id, marker_index):
        """
        Encode an asset id and a marker index into a single marker id.
        marker_id = (asset_id << 16) + marker_index
        """
        return (asset_id << 16) + marker_index

    @staticmethod
    def _decode_marker_label(marker_id):
        """
        Decode a marker id into its asset id and marker index components.
        Returns (asset_id, marker_index)
        """
        asset_id = marker_id >> 16
        marker_index = marker_id & 0xFFFF
        return asset_id, marker_index

    @staticmethod
    def _calculate_rigid_body_marker(rigid_body_position, rigid_body_orientation, marker_offset):
        # marker_offset is already a numpy array (no per-call conversion)
        vector_rotated = transform_vector_from_a_to_b_frame(
            vector_in_a_frame=marker_offset,
            orientation_from_b_to_a=rigid_body_orientation
        )
        return vector_rotated + rigid_body_position


if __name__ == '__main__':
    optitrack = OptiTrack(server_address='palantir.lan', max_sample_rate=100)
    optitrack.init()
    ok = optitrack.start()

    if ok:
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            pass
        finally:
            optitrack.close()
