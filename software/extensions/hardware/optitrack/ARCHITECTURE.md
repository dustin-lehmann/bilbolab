# OptiTrack Universal Client - Architecture

## System Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  User Code (no changes needed)                                  │
│  from extensions.optitrack import OptiTrack                    │
│  optitrack = OptiTrack(server_address='192.168.8.131')         │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  OptiTrack.__init__()                                           │
│  ├─ Creates NatNetClient                                       │
│  ├─ Sets up callbacks                                          │
│  └─ Initializes version tracking                               │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  optitrack.start()                                              │
│  ├─ Starts processing thread                                   │
│  └─ Calls natnetclient.run()                                   │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  NatNetClient.run()                                             │
│  ├─ Creates data & command sockets                             │
│  ├─ Starts receiver threads                                    │
│  └─ Sends NAT_CONNECT request (with version 4.1 request)       │
└──────────────────┬──────────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
   ┌────────────┐        ┌─────────────────┐
   │ Server is  │        │ Server is       │
   │ NatNet 4.x │        │ NatNet 3.x      │
   │ (Motive 3) │        │ (Motive 2)      │
   └──────┬─────┘        └────────┬────────┘
          │                       │
          ▼                       ▼
   NAT_SERVERINFO            NAT_PINGRESPONSE
   (version in response)     (version in response)
          │                       │
          └───────────┬───────────┘
                      ▼
          _unpack_server_info() OR
          __processMessage(NAT_PINGRESPONSE)
                      │
          (Both set self._nat_net_version)
                      │
                      ▼
        ┌─────────────────────────────────┐
        │ OptiTrack detects version:      │
        │ self._natnet_major_version      │
        │ = natnetclient.major            │
        └────────────┬────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
    NatNet 4.x                 NatNet 3.x
    (major >= 4)               (major < 4)
        │                         │
        ▼                         ▼
  _natnet_uses_         _natnet_uses_
  direct_markers        direct_markers
  = True                = False
        │                         │
        ├──── DESCRIPTION CALLBACK ─────┤
        │                               │
        ▼                               ▼
  NO Coord              Apply y-up → z-up
  Conversion            Coordinate Conversion
        │                               │
        │                    marker_offset[0] = -raw[0]
        │                    marker_offset[1] = -raw[2]
        │                    marker_offset[2] = raw[1]
        │                               │
        └───────────┬───────────────────┘
                    ▼
        Store marker descriptions
                    │
                    ▼
        _natnet_mocap_data_callback()
        (Light: just queue frames)
                    │
                    ▼
        _processing_loop() (separate thread)
        (Process at controlled rate)
                    │
                    ▼
        ┌───────────────────────────────┐
        │ _build_sample()               │
        │                               │
        │ Choose extraction method:     │
        └───────────┬───────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
    NatNet 4.x              NatNet 3.x
    Direct Markers         Calculated
        │                   Markers
        │                       │
        ▼                       ▼
  For each rigid         For each rigid
  body:                  body:
    markers[idx] =         pose = RB position
    marker_pos             orient = RB orientation
    (from                  for each marker:
    marker_sets)             raw_offset = desc.offset
                             rotated = rotate(
                               raw_offset, orient)
                             markers[id] =
                               pose + rotated
        │                       │
        └───────────┬───────────┘
                    ▼
        Create RigidBodySample
        {
          name, id, valid,
          position, orientation,
          markers,
          markers_raw
        }
                    │
                    ▼
        Emit callbacks & events
                    │
                    ▼
        User receives same interface!
```

## Component Interaction

### NatNetClient
```
NatNetClient
├─ Sockets
│  ├─ data_socket (receive mocap data)
│  └─ command_socket (send commands, get responses)
├─ Threads
│  ├─ _data_thread_function()
│  └─ _command_thread_function()
├─ Version Detection
│  └─ major, minor properties
└─ Callbacks
   ├─ mocap_data_callback
   └─ description_message_callback
```

### OptiTrack
```
OptiTrack
├─ NatNetClient (composition)
├─ Version Detection
│  ├─ _natnet_major_version
│  └─ _natnet_uses_direct_markers
├─ Data Storage
│  └─ rigid_bodies: dict[str, RigidBodyDescription]
├─ Processing Thread
│  └─ _processing_loop()
├─ Callbacks & Events
│  ├─ sample callback/event
│  └─ description_received callback/event
└─ Methods
   ├─ init(), start(), close()
   ├─ _natnet_description_callback()
   ├─ _natnet_mocap_data_callback()
   ├─ _build_sample()
   └─ _calculate_rigid_body_marker()
```

## Message Flow Timeline

```
Timeline                Action
─────────────────────────────────────────────────────
T=0                     User calls: optitrack.start()
T=0                     OptiTrack creates NatNetClient
T=0                     NatNetClient.run() starts sockets
T=0                     Send: NAT_CONNECT with v4.1 request
T=10ms                  Recv: Server info message
T=10ms                  Extract: NatNet version
T=10ms                  Recv: Model definitions
T=10ms                  OptiTrack._natnet_description_callback()
T=10ms                  Detect version & select method
T=10ms                  Log: "NatNet version detected: X.X"
T=10ms                  Start receiving mocap frames
T=11ms                  Recv: Frame 0 (mocap data)
T=11ms                  _natnet_mocap_data_callback() [light]
T=11ms                  Queue frame (if not already queued)
T=11ms                  _processing_loop() dequeues frame
T=11ms                  _build_sample() processes frame
T=11ms                  Emit callbacks & events
T=11ms                  User gets RigidBodySample
...                     Continue at max_sample_rate
```

## Decision Tree: Marker Extraction Method

```
Start building sample
│
├─ Is NatNet 4.x+?
│  │
│  ├─ YES
│  │  │
│  │  ├─ Do we have marker_sets in frame?
│  │  │  │
│  │  │  ├─ YES → Use direct markers from frame
│  │  │  │         markers[idx] = marker_pos
│  │  │  │         markers_raw[idx] = None
│  │  │  │
│  │  │  └─ NO → markers={}, markers_raw={}
│  │  │
│  │  └─ [END - Use direct method]
│  │
│  └─ NO (NatNet 3.x)
│     │
│     ├─ For each marker in description:
│     │  │
│     │  ├─ Get rigid body position & orientation
│     │  ├─ Get marker offset from description
│     │  ├─ Apply coordinate conversion:
│     │  │  marker_offset[0] = -raw[0]
│     │  │  marker_offset[1] = -raw[2]
│     │  │  marker_offset[2] = raw[1]
│     │  ├─ Rotate offset by RB orientation
│     │  ├─ Add to RB position
│     │  ├─ markers[id] = result
│     │  └─ markers_raw[id] = from marker_sets (if exists)
│     │
│     └─ [END - Use calculated method]
│
└─ Create RigidBodySample
   {all markers computed/extracted}
```

## Data Flow for Markers

### NatNet 3.x Path
```
Description Phase:
  Raw offset from server (y-up convention)
       ▼
  Apply conversion in _natnet_description_callback
       ▼
  Converted offset stored in MarkerDescription
       ▼
Frame Data Phase:
  RigidBody position & orientation
       ▼
  For each marker:
    Rotate (converted) offset by orientation
       ▼
    Add to RB position
       ▼
    Marker position (z-up coordinates)
```

### NatNet 4.x Path
```
Description Phase:
  Raw offset from server (z-up convention)
       ▼
  Store as-is in MarkerDescription
       ▼
Frame Data Phase:
  marker_sets contains marker positions
       ▼
  Extract positions directly
       ▼
  Marker positions (z-up coordinates)
```

## Threading Model

```
Main Thread                 OptiTrack Thread        NatNet Threads
│                           │                       │
├─ user code                ├─ _processing_loop()   ├─ _data_thread()
│  │                        │                       │
│  ├─ start()───────────────┼─────────────────────►├─ Wait for frames
│  │  │                     │                       │
│  │  └──► natnetclient     │                       ├─ Recv mocap data
│  │        .run()          │                       │
│  │                        │                       ├─ _process_message()
│  │                        │                       │
│  └─ while true:           ├─ Queue frame          │
│     wait & check data     │  (_frame_queue)       │
│                           │  ▲                    │
│                           │  │                    │
│                           ├─ Dequeue              │
│                           │  Build sample         │
│                           │  Emit callbacks       │
│                           │                       ├─ _command_thread()
│  close()────────────────► stop loop              │
│   └─ natnetclient        │                       ├─ Recv descriptions
│     .close()            └───────────────────────►├─ Get server info
│                                                   │
│                                                   └─ Threads exit
```

## Summary

The universal client achieves version compatibility through:

1. **Late Version Detection**: Detect after server responds
2. **Conditional Logic**: Choose path based on detected version
3. **Unified Interface**: Same output regardless of path taken
4. **Logging**: Show which path was chosen for debugging

Result: **One codebase, multiple versions, optimal performance.**
