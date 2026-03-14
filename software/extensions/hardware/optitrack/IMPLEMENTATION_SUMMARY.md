# OptiTrack Universal Client - Implementation Summary

## What Was Done

Created a **universal, self-adapting OptiTrack client** that works seamlessly with both Motive 2.x (NatNet 3.x) and Motive 3.0+ (NatNet 4.x) systems.

## Files Created/Modified

### New Files
1. **`lib/natnetclient.py`** - Universal NatNet protocol client
   - Detects NatNet version automatically
   - Compatible with both 3.x and 4.x protocols
   - ~800 lines, well-commented

### Modified Files
1. **`optitrack.py`** - Universal OptiTrack wrapper
   - Replaced old version
   - Detects NatNet version from client
   - Intelligently switches marker extraction method
   - Handles coordinate conversion when needed
   - ~440 lines, well-commented

2. **`__init__.py`** - Updated exports
   - Properly exports all public classes
   - Clear module docstring

### Documentation Files
1. **`UNIVERSAL_CLIENT_README.md`** - Technical overview
2. **`MIGRATION_GUIDE.md`** - Step-by-step migration guide
3. **`IMPLEMENTATION_SUMMARY.md`** - This file

## Key Features

### ✅ Automatic Version Detection

```
NatNetClient detects at connection:
├─ NatNet 3.x → uses y-up→z-up conversion + calculated markers
└─ NatNet 4.x → uses direct marker positions (no conversion)

Detected version logged at startup:
"NatNet version detected: 3.0" OR "NatNet version detected: 4.1"
```

### ✅ Intelligent Marker Extraction

| Aspect | NatNet 3.x | NatNet 4.x |
|--------|-----------|-----------|
| Source | Pose + offsets | Frame data |
| Conversion | Y-up → Z-up | None |
| Method | Calculated | Direct |
| Accuracy | Good | Excellent |
| Speed | Computed | Native |

### ✅ Backward Compatible

- Same interface as before
- No code changes required
- All existing code works unchanged
- Same data structures
- Same callback system

### ✅ Comprehensive Logging

```
NatNetClient: Connecting to Motive server at palantir.lan...
NatNetClient: Requesting NatNet version 4.1
NatNetClient: Connected to Motive
NatNetClient: Server version 2.0.0.0
NatNetClient: NatNet version 3.0.0.0
OptiTrack: NatNet version detected: 3.0
OptiTrack: Using calculated marker positions from rigid body pose + offsets (NatNet 3.x behavior)
OptiTrack: Applying y-up → z-up coordinate conversion for marker offsets
OptiTrack: Start Optitrack
OptiTrack: Optitrack running!
OptiTrack: Rigid bodies: ['bilbo2', 'origin-bilbo', 'limbo-marker']
```

## How It Works

### Connection & Version Negotiation

```python
class NatNetClient:
    def run(self):
        # Start with NatNet 4.x protocol (NAT_CONNECT)
        self._send_request(self.command_socket, self.NAT_CONNECT)
        # Server responds with version info
        # Client auto-adapts to server's actual version
```

### OptiTrack Version Detection

```python
class OptiTrack:
    def _natnet_description_callback(self, data):
        # Detect version from client
        self._natnet_major_version = self.natnetclient.major

        # Decide marker extraction method
        self._natnet_uses_direct_markers = self._natnet_major_version >= 4

        # Apply coordinate conversion if needed
        if self._natnet_major_version == 3:
            # Convert y-up → z-up
            marker_offset[0] = -raw[0]
            marker_offset[1] = -raw[2]
            marker_offset[2] = raw[1]
```

### Per-Frame Marker Extraction

```python
def _build_sample(self, data):
    if self._natnet_uses_direct_markers:
        # NatNet 4.x: Use direct positions from frame
        markers[idx] = marker_pos  # From marker_sets
    else:
        # NatNet 3.x: Calculate from pose + offset
        marker_pos = RB_pos + rotate(offset, RB_orientation)
```

## Coordinate System Handling

### The NatNet 3.x Bug & Fix

**Problem**: Motive 2.x sends marker offsets in y-up, but streaming data is z-up (inconsistency)

**Solution**: Apply transformation in description callback:

```python
# Transform from Motive's y-up convention to our z-up
marker_offset[0] = -marker_offset_y_up[0]   # Flip X
marker_offset[1] = -marker_offset_y_up[2]   # Use negative Z as Y
marker_offset[2] = marker_offset_y_up[1]    # Use Y as Z
```

### NatNet 4.x Improvement

Motive 3.0+ fixed the bug - all data is consistently z-up, including marker positions sent directly in frame data.

## Protocol Compatibility

### NatNet 4.x Protocol (Used by Default)

Works with:
- ✅ Motive 3.0+ (native protocol)
- ✅ Motive 2.x (also supports this protocol)

Uses:
- NAT_CONNECT message for negotiation
- Automatic version detection
- More robust error handling

### Fallback to NatNet 3.x

If server doesn't support NAT_CONNECT:
- Client receives NAT_PINGRESPONSE
- Extracts version from response
- Client continues with compatible message handling

## Usage - No Changes Required

```python
# This code works with both systems
from extensions.optitrack import OptiTrack

optitrack = OptiTrack(
    server_address='192.168.8.131',
    max_sample_rate=100,
    # Optional: network configuration
    multicast_address='239.255.42.99',
    local_address='0.0.0.0',
    use_multicast=True
)

optitrack.init()
optitrack.start()

def on_sample(sample):
    for name, rb in sample.items():
        print(f"{name}: pos={rb.position}, markers={len(rb.markers)}")

optitrack.callbacks.sample.register(on_sample)
```

## Data Guarantees

### RigidBodySample Structure
```python
@dataclass
class RigidBodySample:
    name: str                              # Rigid body name
    id: int                                # Rigid body ID
    valid: bool                            # Tracking valid
    position: numpy.ndarray                # [x, y, z] in meters
    orientation: numpy.ndarray             # [w, x, y, z] quaternion
    markers: dict[int, numpy.ndarray]      # Marker positions (world coords)
    markers_raw: dict[int, ndarray | None] # Raw data or None
```

### Marker Data

**NatNet 3.x**:
- `markers`: Calculated from pose + converted offsets
- `markers_raw`: Available raw marker data (if detected)

**NatNet 4.x**:
- `markers`: Direct from frame (highest quality)
- `markers_raw`: Always None (not used)

## Testing Coverage

### Tested With
- ✅ Motive 2.x (NatNet 3.0)
  - Coordinate conversion applied
  - Raw markers available
  - Version detection confirmed

- ✅ Motive 3.0+ (NatNet 4.x)
  - Direct marker positions used
  - No conversion applied
  - Version detection confirmed

## Performance Impact

- **No overhead**: Version detection happens once at startup
- **Optimal path**: Each mode is optimized for that NatNet version
- **Memory**: Same as before
- **CPU**: NatNet 4.x slightly more efficient (fewer calculations)

## Legacy Support

Old files (if still present):
- `optitrack.py` (old) - Can be deleted
- `optitrack_new.py` - Can be deleted
- `lib/natnetclient_modified.py` - Can be deleted
- `lib/natnetclient_new.py` - Can be deleted

Recommended: Archive these before deleting, keep for 1-2 releases.

## Logging

The implementation provides detailed logging at INFO level:

1. **Connection phase**:
   - "Connecting to Motive server at [address]..."
   - "Requesting NatNet version 4.1"

2. **Connected phase**:
   - "Connected to Motive"
   - "Server version X.X.X.X"
   - "NatNet version X.X.X.X"

3. **OptiTrack phase**:
   - "NatNet version detected: X.X"
   - "[Method selected]"
   - "[Conversion info]"
   - "Optitrack running!"
   - "Rigid bodies: [list]"

## Error Handling

- Graceful version detection failure → logs warning
- Missing rigid body in frame → marked invalid, marked with zero position
- Missing marker data → handled with defaults
- Connection failure → logged, returns False from start()

## Summary

✅ **Unified Implementation**
- One `optitrack.py` for all systems
- One `natnetclient.py` for all protocols

✅ **Intelligent Adaptation**
- Auto-detects NatNet version
- Chooses optimal method
- Handles coordinate conversion

✅ **Full Compatibility**
- Works with Motive 2.x and 3.0+
- No code changes needed
- Same interface, same behavior

✅ **Clear Visibility**
- Detailed logging
- Shows which method being used
- Helps with debugging

✅ **Production Ready**
- Thoroughly tested
- Error handling included
- Performance optimized
- Well documented
