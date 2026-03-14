# BILBO Experiment Definition Guide

This document describes how to define experiments for the BILBO robot using YAML files.

## Basic Structure

An experiment definition has the following structure:

```yaml
id: my_experiment
description: A brief description of what this experiment does
timeout: 30.0  # Optional: experiment timeout in seconds
external_input_enabled: false  # Optional: keep external inputs active during experiment
actions:
  - # action 1
  - # action 2
  - # ...
```

**Required fields:**
- `id` - Unique identifier for the experiment
- `description` - Human-readable description
- `actions` - List of actions to execute

**Optional fields:**
- `timeout` - Maximum experiment duration in seconds
- `external_input_enabled` - If true, external inputs (joystick, etc.) remain active during the experiment. Default: false.
- `requirements` - Optional preconditions checked before the experiment starts (see below)

---

## Requirements

The optional `requirements` field lets you define preconditions that are checked before an experiment starts. If any requirement fails, the experiment is rejected with error messages and never begins execution. Omitting a field means "don't check".

```yaml
id: navigation_experiment
description: Navigate to waypoints
timeout: 60.0

requirements:
  optitrack: true                    # OptiTrack must be connected
  robot_id: "bilbo.*"               # Regex pattern, or list: ["bilbo1", "bilbo2"]
  control_mode: "OFF"               # Required control mode before start
  control_config: "default"         # Required control config name
  state_ranges:                      # Dynamic state must be within bounds
    - state: theta
      min: -0.1
      max: 0.1
    - state: v
      min: -0.05
      max: 0.05

actions:
  - type: set_mode
    mode: POSITION
  # ...
```

All fields under `requirements` are optional. You can use any combination:

| Field | Type | Description |
|-------|------|-------------|
| `optitrack` | bool | `true` = must be connected, `false` = must not be active |
| `robot_id` | string or list | Regex pattern(s) matched against the robot's ID |
| `control_mode` | string | Required control mode (e.g. `"OFF"`, `"BALANCING"`) |
| `control_config` | string | Required control configuration name |
| `state_ranges` | list | List of state field bounds to check |

### State Range Entries

Each entry in `state_ranges` checks a field of the robot's dynamic state:

| Field | Type | Description |
|-------|------|-------------|
| `state` | string | State field name: `x`, `y`, `v`, `theta`, `theta_dot`, `psi`, `psi_dot` |
| `min` | float | Minimum allowed value (optional) |
| `max` | float | Maximum allowed value (optional) |

### Examples

**Require OptiTrack and robot to be nearly upright:**
```yaml
requirements:
  optitrack: true
  state_ranges:
    - state: theta
      min: -0.05
      max: 0.05
```

**Restrict to specific robots:**
```yaml
requirements:
  robot_id: ["bilbo1", "bilbo3"]
```

**Require robot to be stationary and in OFF mode:**
```yaml
requirements:
  control_mode: "OFF"
  state_ranges:
    - state: v
      max: 0.01
    - state: theta_dot
      min: -0.05
      max: 0.05
```

---

## Action Scheduling

Actions can be scheduled in several ways. If no scheduling is specified, actions run sequentially (each action starts after the previous one finishes).

### Implicit Sequential Execution (Default)

```yaml
actions:
  - type: set_mode       # Runs at tick 0 (first action)
    mode: BALANCING
  - type: beep           # Runs after mode change completes
  - type: wait_time      # Runs after beep completes
    time_ms: 2000
```

### Explicit Scheduling Options

Each action supports these scheduling fields (use at most one):

| Field | Type | Description |
|-------|------|-------------|
| `tick` | int | Absolute experiment tick (100 ticks = 1 second) |
| `time` | float | Absolute time in seconds since experiment start |
| `after` | string | ID of action that must finish first |
| `delay` | float | Delay in seconds before this action (creates implicit wait) |

Additionally, every action supports optional `wait_before` and `wait_after` fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `wait_before` | time | `0` | Wait before executing the action |
| `wait_after` | time | `0` | Wait after the action completes |

Time values support: `"2s"`, `"500ms"`, `2.0` (float = seconds), `2000` (int = milliseconds).

These waits run on background threads and never block the main control loop. `wait_before` delays the start of the action, `wait_after` delays signaling completion (so the next sequential action waits). They can be combined with any action type.

**Examples:**

```yaml
actions:
  # Start at specific times
  - type: beep
    time: 0           # Start at t=0s
  - type: beep
    time: 2.0         # Start at t=2.0s
  - type: beep
    tick: 500         # Start at tick 500 (t=5.0s)

  # Explicit dependencies
  - type: set_mode
    id: start_balancing
    mode: BALANCING
  - type: beep
    after: start_balancing  # Runs after start_balancing finishes

  # Delay before action
  - type: set_mode
    mode: BALANCING
  - delay: 1.5        # Wait 1.5s after previous action
    type: beep        # Then beep

  # wait_before / wait_after
  - type: set_mode
    mode: VELOCITY
    wait_before: 1s    # Wait 1 second, then set mode
    wait_after: 500ms  # After mode is set, wait 500ms before next action
  - type: set_velocity
    forward: 0.3
```

### Action IDs

Action IDs are auto-generated as `action_0`, `action_1`, etc. You can specify custom IDs:

```yaml
actions:
  - type: set_mode
    id: my_custom_id
    mode: BALANCING
  - type: beep
    after: my_custom_id
```

### Action Labels

Actions can have an optional `label` for display in experiment reports:

```yaml
actions:
  - type: group
    id: velocity_phase
    label: "Velocity Test"
    actions:
      - type: set_mode
        mode: VELOCITY
      - type: set_velocity
        forward: 0.3
        turn: 0.0
      - type: wait_time
        time_ms: 3000
```

- `label` is optional on any action
- Labels cause the action to appear as a colored phase bar overlaid on all plots in the experiment report
- Most useful on `group` actions to visually mark experiment phases in reports
- Only actions with a `label` AND that span multiple ticks get phase highlighting

---

## All Action Types

### `set_mode` - Control Mode

Sets the robot's control mode.

```yaml
- type: set_mode
  mode: BALANCING  # OFF, DIRECT, BALANCING, VELOCITY, or POSITION
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | string | `"OFF"` | Control mode: `OFF`, `DIRECT`, `BALANCING`, `VELOCITY`, `POSITION` |

**Available modes:**
- `OFF` - Motors disabled
- `DIRECT` - Raw torque passthrough
- `BALANCING` - State feedback (pitch/roll stabilization)
- `VELOCITY` - Forward velocity + yaw rate commands
- `POSITION` - XY position + heading (requires OptiTrack)

---

### `beep` - Audio Beep

Plays a beep sound.

```yaml
- type: beep
  frequency: 1000
  time_ms: 250
  repeats: 1
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `frequency` | int | 1000 | Frequency in Hz |
| `time_ms` | int | 250 | Duration in milliseconds |
| `repeats` | int | 1 | Number of repetitions |

---

### `speak` - Text-to-Speech

Speaks text using TTS.

```yaml
- type: speak
  text: "Hello world"
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | string | `""` | Text to speak |

---

### `wait_time` - Time Delay

Waits for a specified duration.

```yaml
- type: wait_time
  time_ms: 2000
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `time_ms` | int | 0 | Wait duration in milliseconds |

---

### `wait_ticks` - Tick Delay

Waits for a specified number of control loop ticks (100 Hz).

```yaml
- type: wait_ticks
  ticks: 100
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ticks` | int | 0 | Number of ticks to wait |

---

### `wait_until_tick` - Wait Until Tick

Waits until a specific experiment tick is reached.

```yaml
- type: wait_until_tick
  tick: 500
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tick` | int | 0 | Target tick number |

---

### `wait_event` - Wait for Event

Waits for a named event to be triggered.

```yaml
- type: wait_event
  event: "my_event"
  timeout: 10.0
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event` | string | `""` | Event ID to wait for |
| `timeout` | float | None | Timeout in seconds (optional) |

---

### `set_velocity` - Velocity Command

Sets forward velocity and turn rate.

```yaml
- type: set_velocity
  forward: 0.5
  turn: 0.1
  normalized: false
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `forward` | float | 0.0 | Forward velocity (m/s or normalized) |
| `turn` | float | 0.0 | Turn rate (rad/s or normalized) |
| `normalized` | bool | false | If true, values are -1 to 1 range |

---

### `set_input` - Direct Input

Sets external input values directly.

```yaml
- type: set_input
  input: [0.5, 0.1]
  normalized: false
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input` | list[float] | [0.0, 0.0] | Input values [forward, turn] |
| `normalized` | bool | false | If true, values are normalized |

---

### `set_tic` - TIC Control

Enables or disables Torque Integral Control.

```yaml
- type: set_tic
  enabled: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | bool | true | Enable TIC control |

---

### `set_marker` - Set Marker

Sets a marker value for logging/synchronization.

```yaml
- type: set_marker
  marker_id: "phase"
  marker_value: "test_start"
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `marker_id` | string | `""` | Marker identifier |
| `marker_value` | string | `""` | Marker value |

---

### `enable_external_input` - External Input Control

Enables or disables external input (joystick, etc.).

```yaml
- type: enable_external_input
  enabled: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | bool | true | Enable external input |

---

### `set_feedback_gain` - Set Feedback Gain

Sets the state feedback gain matrix K for balancing control.

```yaml
- type: set_feedback_gain
  K: [0.25, 0.2, 0.03, 0.015, 0.0, 0.0]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `K` | list[float] | [] | Feedback gain vector |

---

### `reset_control` - Reset Control State

Resets the control system state (integrators, filters, etc.).

```yaml
- type: reset_control
```

No parameters.

---

### `run_trajectory` - Execute Trajectory

Runs a predefined input trajectory.

```yaml
- type: run_trajectory
  input_trajectory:
    id: 1
    length: 100
    inputs:
      - left: 0.1
        right: 0.1
      # ... more steps
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_trajectory` | object/string | required | Trajectory definition or file path |

---

### `reset` - Reset State

Resets experiment state and re-enables external input.

```yaml
- type: reset
```

No parameters.

---

### `parallel` - Parallel Execution

Executes multiple actions simultaneously.

```yaml
- type: parallel
  actions:
    - type: beep
    - type: speak
      text: "Hello"
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `actions` | list | [] | List of actions to run in parallel |

The parallel action completes when ALL sub-actions finish.

---

### `group` - Sequential Action Group

Executes multiple actions sequentially as a named group. Groups are useful for organizing related actions together and tracking their collective start and end times, which makes it easy to extract data samples for specific phases of an experiment.

```yaml
- type: group
  id: velocity_test
  label: "Velocity Test"
  actions:
    - type: set_mode
      mode: VELOCITY
    - type: set_velocity
      forward: 0.5
    - type: wait_time
      time_ms: 3000
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `actions` | list | [] | List of actions to run sequentially |

Groups with a `label` are highlighted as colored phase bars in experiment reports.

**Key differences from `parallel`:**
- `parallel`: All sub-actions start simultaneously, finishes when ALL complete
- `group`: Sub-actions run one after another (sequentially), finishes when the last one completes

**Accessing group timing data:**
After an experiment completes, you can access group timing from `ExperimentData.action_data`:

```python
data = experiment.get_data()
velocity_group = data.action_data['velocity_test']
print(f"Start tick: {velocity_group.start_tick}")
print(f"End tick: {velocity_group.end_tick}")
print(f"Start time: {velocity_group.start_time}")  # seconds
print(f"End time: {velocity_group.end_time}")      # seconds
```

---

### `loop` - Repeat Actions

Repeats a block of actions multiple times or iterates over a list of values. The loop is expanded into nested `group` actions at parse time, so the executor only ever sees groups.

Supports three iteration modes:

**1. Count-based repeat:**
```yaml
- type: loop
  count: 5
  actions:
    - type: beep
    - type: wait_time
      time_ms: 500
```

**2. Iterate over explicit values:**
```yaml
- type: loop
  variable: speed
  values: [0.2, 0.4, 0.6, 0.8, 1.0]
  actions:
    - type: set_velocity
      forward: "${speed}"
    - type: wait_time
      time_ms: 3000
```

**3. Range-based iteration:**
```yaml
- type: loop
  variable: j
  range: [0, 5]          # range(0, 5) -> 0, 1, 2, 3, 4
  actions:
    - type: group
      id: "trial_${j}"
      label: "Trial ${j}"
      actions:
        - type: set_velocity
          forward: 0.5
        - type: wait_time
          time_ms: 2000
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `actions` | list | required | List of actions to repeat each iteration |
| `count` | int | None | Number of iterations (simple repeat) |
| `variable` | string | `"_index"` | Loop variable name for `${variable}` substitution |
| `values` | list | None | Explicit list of values to iterate over |
| `range` | int/list | None | Range specification: `N`, `[end]`, `[start, end]`, or `[start, end, step]` |

**Variable substitution:**
- Use `${variable}` in any string field (action parameters, IDs, labels)
- If a string is exactly `"${variable}"`, the original type is preserved (e.g., float stays float)
- If `${variable}` is embedded in a larger string, it is interpolated as a string
- The built-in variable `${_index}` (0-based iteration index) is always available

**How it works:**
The loop is expanded at parse time into a `group` containing one sub-`group` per iteration. Each iteration group has the loop variable substituted into all action parameters, IDs, and labels. This means:
- The experiment executor only sees regular `group` actions
- Loop iteration groups appear in reports and data extraction like any other group
- Labels on iteration groups are auto-generated (e.g., `speed=0.2`, `iteration 0`)

**Nested loops:**
Loops can be nested. Inner loop variables are substituted correctly alongside outer variables:

```yaml
- type: loop
  variable: speed
  values: [0.2, 0.4]
  actions:
    - type: loop
      variable: direction
      values: [0.0, 0.5, -0.5]
      actions:
        - type: set_velocity
          forward: "${speed}"
          turn: "${direction}"
        - type: wait_time
          time_ms: 2000
```

---

## Position Control Actions

Position control actions require the robot to be in `POSITION` mode. These actions interface with the position control subsystem to move the robot to specific locations or follow paths.

### `move_to` - Move to Position

Moves the robot to a target position using position control.

```yaml
- type: move_to
  x: 1.0
  y: 0.5
  max_speed: 0.3
  timeout: 30.0
  wait: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `x` | float | 0.0 | Target X coordinate [m] |
| `y` | float | 0.0 | Target Y coordinate [m] |
| `max_speed` | float | 0.0 | Maximum speed [m/s] (0 = use default) |
| `timeout` | float | 0.0 | Command timeout [s] (0 = no timeout) |
| `wait` | bool | true | If true, wait for completion before continuing |

---

### `turn_to` - Turn to Heading

Rotates the robot in place to face a target heading.

```yaml
- type: turn_to
  heading: 1.57
  max_angular_speed: 2.0
  timeout: 10.0
  wait: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `heading` | float | 0.0 | Target heading [rad] |
| `heading_deg` | float | None | Target heading [deg] (alternative to `heading`) |
| `max_angular_speed` | float | 0.0 | Maximum turn rate [rad/s] (0 = use default) |
| `timeout` | float | 0.0 | Command timeout [s] (0 = no timeout) |
| `wait` | bool | true | If true, wait for completion before continuing |

---

### `set_waypoints` - Set Path Waypoints

Sets waypoints for path following. Must be in POSITION mode.

```yaml
- type: set_waypoints
  clear_existing: true
  waypoints:
    - x: 0.5
      y: 0.0
      type: PASS
      weight: 0.75
      speed: 0.0            # 0 = use path default
    - x: 1.0
      y: 0.5
      type: STOP
      weight: 0.9
      speed: 0.2            # slow down to 0.2 m/s for this waypoint
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `waypoints` | list | [] | List of waypoint definitions |
| `clear_existing` | bool | true | Clear existing waypoints before adding |

**Waypoint format options:**
```yaml
# Minimal (just coordinates)
- [0.5, 0.0]

# With type
- [1.0, 0.5, "STOP"]        # type: "PASS" or "STOP"

# With weight
- [1.5, 0.0, 0.9]           # weight: 0.0-1.0 (corner sharpness)

# With type and weight
- [2.0, 0.5, "STOP", 0.8]

# With type, weight, and speed
- [2.5, 0.0, "PASS", 0.75, 0.3]  # speed: m/s (0 = use path default)

# Full dict format
- x: 2.5
  y: 0.0
  type: PASS                # PASS = smooth through, STOP = stop at waypoint
  weight: 0.75              # 1.0 = sharp corner, 0.0 = smooth curve
  speed: 0.3                # Per-waypoint max speed [m/s] (0 = use path default)
```

**Per-waypoint speed:**
- Each waypoint can specify its own `speed` limit (0 = use path's max_speed)
- Speed transitions smoothly between waypoints over ~0.5 seconds
- Corner angle slowdown still applies (takes minimum of waypoint speed and corner-based limit)
- Useful for slowing down at precise positioning points or speeding up on straight segments

---

### `start_path` - Start Path Following

Starts following the loaded waypoints.

```yaml
- type: start_path
  allow_reverse: false
  timeout: 60.0
  max_speed: 0.3
  wait: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `allow_reverse` | bool | false | Allow robot to drive backwards when efficient |
| `timeout` | float | 0.0 | Path execution timeout [s] (0 = no timeout) |
| `max_speed` | float | 0.0 | Maximum speed [m/s] (0 = use default) |
| `wait` | bool | true | If true, wait for path completion before continuing |

---

### `load_path` - Load Path from Dict or File

Loads waypoints from a path definition (dict or file) and optionally starts following.

```yaml
# Load from inline definition
- type: load_path
  start: true
  clear_existing: true
  path:
    max_speed: 0.3
    allow_reverse: false
    timeout: 60.0
    waypoints:
      - [0.5, 0.0]
      - [1.0, 0.5]
      - [1.5, 0.0, "STOP"]

# Load from file
- type: load_path
  path: "waypoints.yaml"
  start: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | dict/string | required | Path definition dict or file path (YAML/JSON) |
| `start` | bool | false | Start path immediately after loading |
| `clear_existing` | bool | true | Clear existing waypoints before loading |
| `allow_reverse` | bool | None | Override allow_reverse setting |
| `timeout` | float | None | Override timeout setting |
| `max_speed` | float | None | Override max_speed setting |
| `wait` | bool | true | If start=true, wait for path completion |

**Path file format (YAML):**
```yaml
max_speed: 0.3              # optional [m/s] - default speed for all waypoints
allow_reverse: false        # optional
timeout: 60.0               # optional [s]
waypoints:
  - x: 0.5
    y: 0.0
  - x: 1.0
    y: 0.5
    type: STOP
    weight: 0.9
    speed: 0.15             # optional - override speed for this waypoint
```

**Per-waypoint speed:** Each waypoint can have its own `speed` limit. Set to 0 (or omit) to use the path's `max_speed`. Speed transitions smoothly between waypoints (~0.5s). Corner slowdown still applies.

---

### `stop_path` - Stop/Abort Path

Aborts the current path execution.

```yaml
- type: stop_path
```

No parameters.

---

### `wait_position_event` - Wait for Position Control Event

Waits for a specific position control event.

```yaml
- type: wait_position_event
  event: path_finished
  timeout: 120.0
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event` | string | "" | Event name to wait for |
| `timeout` | float | None | Timeout in seconds |

**Available events:**
- `path_finished` - Path completed successfully
- `path_timeout` - Path execution timed out
- `path_aborted` - Path was aborted
- `path_started` - Path execution started
- `move_to_point_completed` - Move-to command completed
- `move_to_point_timeout` - Move-to command timed out
- `turn_to_heading_completed` - Turn-to command completed
- `turn_to_heading_timeout` - Turn-to command timed out
- `waypoint_completed` - A waypoint was completed
- `waypoint_reached` - Robot reached a waypoint
- `waypoint_passed` - Robot passed through a waypoint
- `mode_changed` - Position control mode changed (e.g., interrupted by external control)

---

## Position Control Error Handling

Position control actions (`move_to`, `turn_to`, `start_path`, `load_path`) automatically detect and report failures:

**Detected failure conditions:**
- **Timeout**: The command took too long to complete
- **Abort**: The path/command was explicitly aborted
- **Mode change**: The control mode changed during execution (e.g., robot fell, external control took over, manual mode change)

When any of these conditions occur, the action reports an error which triggers the experiment's error handling (see "Experiment Status and Error Handling" section). This ensures you always get experiment data even when position control fails unexpectedly.

**Example: Detecting path interruption**
```yaml
id: path_with_monitoring
description: Path that might be interrupted
actions:
  - type: set_mode
    mode: POSITION
  - type: wait_time
    time_ms: 1000

  - type: group
    id: path_execution
    actions:
      - type: load_path
        path: "my_path.yaml"
        start: true
        wait: true  # Will detect mode changes and report error

  - type: set_mode
    mode: OFF
```

If the control mode changes during path execution (e.g., robot tips over and switches to BALANCING), the `load_path` action will detect this and trigger an experiment error with full data collection.

---

## Complete Examples

### Example 1: Simple Balance Test

```yaml
id: balance_test
description: Basic balancing test with audio feedback
actions:
  - type: speak
    text: "Starting balance test"
  - type: wait_time
    time_ms: 1000
  - type: set_mode
    mode: BALANCING
  - type: beep
  - type: wait_time
    time_ms: 10000
  - type: set_mode
    mode: OFF
  - type: speak
    text: "Test complete"
```

### Example 2: Velocity Control Sequence

```yaml
id: velocity_sequence
description: Execute a velocity command sequence
timeout: 30.0
actions:
  - type: set_mode
    mode: BALANCING
  - type: wait_time
    time_ms: 2000
  - type: set_mode
    mode: VELOCITY
  - type: set_velocity        # Forward
    forward: 0.2
    turn: 0.0
  - type: wait_time
    time_ms: 3000
  - type: set_velocity        # Turn
    forward: 0.0
    turn: 0.5
  - type: wait_time
    time_ms: 2000
  - type: set_velocity        # Stop
    forward: 0.0
    turn: 0.0
  - type: wait_time
    time_ms: 1000
  - type: set_mode
    mode: OFF
```

### Example 3: Using Delays

```yaml
id: delayed_actions
description: Actions with relative delays
actions:
  - type: set_mode
    mode: BALANCING
  - delay: 2.0
    type: beep
    frequency: 800
  - delay: 1.0
    type: beep
    frequency: 1000
  - delay: 1.0
    type: beep
    frequency: 1200
  - delay: 2.0
    type: set_mode
    mode: OFF
```

### Example 4: Parallel Actions

```yaml
id: parallel_demo
description: Demonstrate parallel execution
actions:
  - type: set_mode
    mode: BALANCING
  - type: wait_time
    time_ms: 1000
  - type: parallel
    actions:
      - type: speak
        text: "Moving forward"
      - type: beep
        frequency: 500
  - type: set_velocity
    forward: 0.3
    turn: 0.0
  - type: wait_time
    time_ms: 3000
  - type: parallel
    actions:
      - type: speak
        text: "Stopping"
      - type: beep
        frequency: 1000
        repeats: 2
  - type: set_velocity
    forward: 0.0
    turn: 0.0
  - type: set_mode
    mode: OFF
```

### Example 5: Complex Experiment with Markers

```yaml
id: complex_experiment
description: Full experiment with phases and markers
timeout: 60.0
actions:
  # Phase 1: Setup
  - type: set_marker
    id: setup_phase
    marker_id: phase
    marker_value: setup
  - type: speak
    text: "Initializing experiment"
  - type: set_mode
    mode: BALANCING
  - type: wait_time
    time_ms: 2000

  # Phase 2: Test
  - type: set_marker
    id: test_phase
    marker_id: phase
    marker_value: test
    after: setup_phase
  - delay: 0.5
    type: enable_external_input
    enabled: false
  - type: set_mode
    mode: VELOCITY
  - type: set_velocity
    forward: 0.5
    turn: 0.0
  - type: wait_time
    time_ms: 5000
  - type: set_velocity
    forward: 0.0
    turn: 0.3
  - type: wait_time
    time_ms: 3000
  - type: set_velocity
    forward: 0.0
    turn: 0.0

  # Phase 3: Cleanup
  - type: set_marker
    marker_id: phase
    marker_value: cleanup
  - type: enable_external_input
    enabled: true
  - type: set_mode
    mode: OFF
  - type: speak
    text: "Experiment complete"
```

### Example 6: Timed Actions (Absolute Scheduling)

```yaml
id: timed_beeps
description: Beeps at specific times
actions:
  - type: beep
    time: 0.0
    frequency: 400
  - type: beep
    time: 1.0
    frequency: 600
  - type: beep
    time: 2.0
    frequency: 800
  - type: beep
    time: 3.0
    frequency: 1000
  - type: speak
    time: 4.0
    text: "Done"
```

### Example 7: Simple Move To Position

```yaml
id: move_to_test
description: Move to a single position
actions:
  - type: speak
    text: "Moving to position"
  - type: set_mode
    mode: POSITION
  - type: wait_time
    time_ms: 1000
  - type: move_to
    x: 1.0
    y: 0.5
  - type: speak
    text: "Arrived"
  - type: set_mode
    mode: OFF
```

### Example 8: Turn to Heading

```yaml
id: turn_test
description: Turn to face different directions
actions:
  - type: speak
    text: "Turning test"
  - type: set_mode
    mode: POSITION
  - type: wait_time
    time_ms: 1000
  - type: turn_to
    heading_deg: 90
  - type: speak
    text: "Facing East"
  - type: turn_to
    heading_deg: 180
  - type: speak
    text: "Facing South"
  - type: turn_to
    heading_deg: 0
  - type: speak
    text: "Facing North"
  - type: set_mode
    mode: OFF
```

### Example 9: Path Following with Waypoints

```yaml
id: path_following
description: Follow a rectangular path
actions:
  - type: speak
    text: "Starting path following"
  - type: set_mode
    mode: POSITION
  - type: wait_time
    time_ms: 1000

  # Set waypoints for a rectangle
  - type: set_waypoints
    waypoints:
      - [0.5, 0.0]
      - [0.5, 0.5]
      - [0.0, 0.5]
      - [0.0, 0.0, "STOP"]

  # Start following
  - type: start_path
    max_speed: 0.25
    wait: true

  - type: speak
    text: "Path complete"
  - type: set_mode
    mode: OFF
```

### Example 10: Load Path from File

```yaml
id: file_path_test
description: Load and follow a path from file
actions:
  - type: speak
    text: "Loading path from file"
  - type: set_mode
    mode: POSITION
  - type: wait_time
    time_ms: 1000

  # Load and start path
  - type: load_path
    path: "~/robot/paths/figure_eight.yaml"
    start: true
    max_speed: 0.3
    wait: true

  - type: speak
    text: "Path finished"
  - type: set_mode
    mode: OFF
```

### Example 11: Complex Navigation Sequence

```yaml
id: navigation_demo
description: Demonstrate various position control features
timeout: 120.0
actions:
  - type: speak
    text: "Navigation demonstration"
  - type: set_mode
    mode: POSITION
  - type: wait_time
    time_ms: 1000

  # Move to starting position
  - type: set_marker
    marker_id: phase
    marker_value: move_to_start
  - type: move_to
    x: 0.5
    y: 0.0
    max_speed: 0.2

  # Turn to face the path direction
  - type: set_marker
    marker_id: phase
    marker_value: align
  - type: turn_to
    heading_deg: 45

  # Set up waypoints with different types
  - type: set_marker
    marker_id: phase
    marker_value: path_setup
  - type: set_waypoints
    waypoints:
      - [0.7, 0.2]                    # Pass through
      - [1.0, 0.5, 0.5]               # Smooth corner (low weight)
      - [1.2, 0.3]                    # Pass through
      - [1.0, 0.0, "STOP", 0.9]       # Stop with sharp approach

  # Follow the path
  - type: set_marker
    marker_id: phase
    marker_value: following
  - type: start_path
    max_speed: 0.25
    allow_reverse: false
    wait: true

  # Return to origin
  - type: set_marker
    marker_id: phase
    marker_value: return
  - type: move_to
    x: 0.0
    y: 0.0
  - type: turn_to
    heading_deg: 0

  - type: speak
    text: "Demo complete"
  - type: set_mode
    mode: OFF
```

### Example 12: Path with Inline Definition and Per-Waypoint Speeds

```yaml
id: inline_path
description: Load path from inline definition with variable speeds
actions:
  - type: speak
    text: "Inline path test"
  - type: set_mode
    mode: POSITION
  - type: wait_time
    time_ms: 1000

  - type: load_path
    start: true
    wait: true
    path:
      max_speed: 0.3            # default speed for waypoints without explicit speed
      allow_reverse: false
      timeout: 60.0
      waypoints:
        - x: 0.5
          y: 0.0
          speed: 0.4            # faster on straight segment
        - x: 1.0
          y: 0.5
          type: PASS
          weight: 0.6
          speed: 0.2            # slow down for corner
        - x: 0.5
          y: 1.0
                                # no speed = uses path max_speed (0.3)
        - x: 0.0
          y: 0.5
          type: STOP
          weight: 0.9
          speed: 0.15           # slow approach to final waypoint

  - type: speak
    text: "Finished"
  - type: set_mode
    mode: OFF
```

### Example 13: Non-Blocking Position Commands

```yaml
id: async_navigation
description: Position commands without waiting
actions:
  - type: set_mode
    mode: POSITION
  - type: wait_time
    time_ms: 1000

  # Start move without waiting
  - type: move_to
    x: 1.0
    y: 0.5
    wait: false

  # Do other things while moving
  - type: parallel
    actions:
      - type: speak
        text: "Moving in background"
      - type: wait_position_event
        event: move_to_point_completed
        timeout: 30.0

  - type: speak
    text: "Arrived"
  - type: set_mode
    mode: OFF
```

### Example 14: Using Groups for Data Extraction

Groups allow you to organize experiment phases and easily extract the corresponding data later.

```yaml
id: grouped_experiment
description: Experiment with named groups for easy data extraction
timeout: 60.0
actions:
  - type: set_mode
    mode: BALANCING
  - type: wait_time
    time_ms: 2000

  # Group 1: Forward velocity test
  - type: group
    id: forward_test
    actions:
      - type: set_mode
        mode: VELOCITY
      - type: set_velocity
        forward: 0.3
        turn: 0.0
      - type: wait_time
        time_ms: 3000
      - type: set_velocity
        forward: 0.0
        turn: 0.0

  - type: wait_time
    time_ms: 1000

  # Group 2: Turn test
  - type: group
    id: turn_test
    actions:
      - type: set_velocity
        forward: 0.0
        turn: 0.5
      - type: wait_time
        time_ms: 2000
      - type: set_velocity
        forward: 0.0
        turn: 0.0

  - type: wait_time
    time_ms: 1000

  # Group 3: Combined motion
  - type: group
    id: combined_test
    actions:
      - type: set_velocity
        forward: 0.2
        turn: 0.3
      - type: wait_time
        time_ms: 3000
      - type: set_velocity
        forward: 0.0
        turn: 0.0

  - type: set_mode
    mode: OFF
```

**Extracting group data in Python:**

```python
# Run the experiment
data = experiment_handler.run_experiment_blocking(experiment)

# Extract samples for each group
forward_group = data.action_data['forward_test']
turn_group = data.action_data['turn_test']
combined_group = data.action_data['combined_test']

# Get samples within each group's time range
forward_samples = [s for s in data.samples
                   if forward_group.start_tick <= s.tick <= forward_group.end_tick]
turn_samples = [s for s in data.samples
                if turn_group.start_tick <= s.tick <= turn_group.end_tick]
combined_samples = [s for s in data.samples
                    if combined_group.start_tick <= s.tick <= combined_group.end_tick]

print(f"Forward test: {len(forward_samples)} samples, "
      f"{forward_group.end_time - forward_group.start_time:.2f}s duration")
print(f"Turn test: {len(turn_samples)} samples")
print(f"Combined test: {len(combined_samples)} samples")
```

### Example 15: Using Loops for Parameter Sweeps

Loops make it easy to test different parameter values without duplicating actions:

```yaml
id: velocity_sweep
description: Test different forward velocities
timeout: 60.0
actions:
  - type: set_mode
    mode: BALANCING
  - type: wait_time
    time_ms: 2000
  - type: set_mode
    mode: VELOCITY

  # Sweep through velocities
  - type: loop
    variable: speed
    values: [0.1, 0.2, 0.3, 0.4, 0.5]
    actions:
      - type: group
        id: "test_${speed}"
        label: "v=${speed} m/s"
        actions:
          - type: set_velocity
            forward: "${speed}"
          - type: wait_time
            time_ms: 3000
          - type: set_velocity
            forward: 0.0
            turn: 0.0
          - type: wait_time
            time_ms: 1000

  - type: set_mode
    mode: OFF
```

Each iteration creates a labeled group, so the report shows phase bars like "v=0.1 m/s", "v=0.2 m/s", etc.

### Example 16: Repeated Trials with Loop

```yaml
id: repeated_trials
description: Run 5 identical trials with beep between each
timeout: 120.0
actions:
  - type: set_mode
    mode: BALANCING
  - type: wait_time
    time_ms: 2000

  - type: loop
    count: 5
    actions:
      - type: group
        id: "trial_${_index}"
        label: "Trial ${_index}"
        actions:
          - type: beep
          - type: set_mode
            mode: VELOCITY
          - type: set_velocity
            forward: 0.3
            turn: 0.0
          - type: wait_time
            time_ms: 3000
          - type: set_velocity
            forward: 0.0
            turn: 0.0
          - type: wait_time
            time_ms: 1000
          - type: set_mode
            mode: BALANCING
          - type: wait_time
            time_ms: 1000

  - type: set_mode
    mode: OFF
```

---

## Experiment Status and Error Handling

Experiments track their completion status, which is included in the experiment data. This allows you to analyze data even when an experiment fails or is aborted.

### Experiment Status Values

| Status | Description |
|--------|-------------|
| `finished` | Experiment completed successfully |
| `error` | Experiment aborted due to an action error |
| `timeout` | Experiment aborted due to timeout |
| `aborted` | Experiment aborted by external request |

### Action Status Values

Each action also tracks its individual status:

| Status | Description |
|--------|-------------|
| `pending` | Action has not started yet |
| `running` | Action is currently executing |
| `finished` | Action completed successfully |
| `error` | Action failed with an error |
| `timeout` | Action timed out |
| `skipped` | Action was skipped due to experiment abort |

### Action Data Structure

Each action in `data.actions` contains detailed information:

| Field | Type | Description |
|-------|------|-------------|
| `start_tick` | int | Tick when action started |
| `end_tick` | int | Tick when action ended |
| `start_time` | float | Start time in seconds |
| `end_time` | float | End time in seconds |
| `status` | string | Action status (see above) |
| `error_message` | string | Error description (if failed) |
| `label` | string | Human-readable label (if set) |
| `parameters` | dict | **Input parameters** configured for this action |
| `data` | dict | **Output data** produced by the action |

**`parameters`** contains the action's input configuration. Examples:
- `set_velocity`: `{'forward': 0.5, 'turn': 0.1, 'normalized': False}`
- `move_to`: `{'x': 1.0, 'y': 0.5, 'max_speed': 0.3, 'timeout': 30.0, 'wait': True}`
- `set_waypoints`: `{'waypoints': [...], 'clear_existing': True}`

**`data`** contains output/results from the action. Most actions leave this `None`, but path actions store the actual waypoints used:
- `start_path` / `load_path`: `{'waypoints': [{'x': 0.5, 'y': 0.0, 'type': 'PASS', 'weight': 0.75, 'speed': 0.0}, ...]}`

**Example: Accessing action parameters**
```python
data = experiment_handler.run_experiment_blocking(experiment)

# Get velocity that was commanded
velocity_action = data.actions['set_velocity_0']
print(f"Commanded velocity: forward={velocity_action.parameters['forward']}, "
      f"turn={velocity_action.parameters['turn']}")

# Get waypoints from a path action
path_action = data.actions['load_path_0']
if path_action.data:
    waypoints = path_action.data['waypoints']
    print(f"Path had {len(waypoints)} waypoints:")
    for wp in waypoints:
        print(f"  ({wp['x']}, {wp['y']}) type={wp['type']}")
```

### Handling Experiment Results

```python
# Run experiment (data is returned even if experiment fails)
data = experiment_handler.run_experiment_blocking(experiment)

if data is None:
    print("Failed to start experiment")
elif data.status == 'finished':
    print(f"Experiment completed successfully with {len(data.samples)} samples")
else:
    print(f"Experiment {data.status}: {data.error_message}")
    if data.error_action_id:
        print(f"  Failed action: {data.error_action_id}")
        failed_action = data.actions[data.error_action_id]
        print(f"  Action status: {failed_action.status}")

    # Data is still available for analysis
    print(f"  Collected {len(data.samples)} samples before failure")

    # Check individual action statuses
    for action_id, action_data in data.actions.items():
        print(f"  {action_id}: {action_data.status}")
```

### Error Recovery Example

```yaml
id: robust_experiment
description: Experiment with error-prone action
timeout: 30.0
actions:
  - type: set_mode
    mode: BALANCING
  - type: wait_time
    time_ms: 2000

  # This path might fail if position is invalid
  - type: group
    id: path_attempt
    actions:
      - type: set_mode
        mode: POSITION
      - type: load_path
        path: "my_path.yaml"
        start: true
        wait: true

  - type: set_mode
    mode: OFF
```

If the path action fails, the experiment data will still contain:
- All samples up to the point of failure
- The `path_attempt` group's timing (partial)
- The error action ID and message
- Status of all actions (which completed, which was skipped)

---

## Experiment Reports

After an experiment completes, the host generates an HTML report containing:
- **Summary**: Experiment ID, status, duration, sample count
- **Action list**: All actions with status, timing, and parameters. `set_waypoints` actions show an expanded waypoint table.
- **Phase bars**: Actions with a `label` field appear as colored bars on all plots, making it easy to see which data corresponds to which experiment phase.
- **State plots**: Time-series of robot state (position, velocity, pitch, etc.)

To get phase bars on your report plots, add `label` to your groups:

```yaml
- type: group
  id: forward_drive
  label: "Forward Drive"
  actions:
    - type: set_velocity
      forward: 0.5
      turn: 0.0
    - type: wait_time
      time_ms: 3000
```

---

## Tips and Best Practices

1. **Use full `type:` syntax** - Always use the explicit `type:` field for every action to avoid ambiguity.

2. **Always end with `type: set_mode` / `mode: OFF`** - Ensure the robot is in a safe state when the experiment ends.

3. **Use `timeout`** - Set a reasonable timeout to prevent runaway experiments.

4. **Test with beeps** - Use beeps to indicate phase transitions during development.

5. **Use markers for analysis** - Set markers at key points to help with post-experiment data analysis.

6. **Parallel for feedback** - Use parallel actions to provide audio feedback without blocking the main sequence.

7. **Explicit IDs for dependencies** - When using `after`, give actions explicit IDs for clarity.

8. **Use groups for data extraction** - Wrap related actions in a `group` with a meaningful ID to easily extract the corresponding samples during post-processing.

### Position Control Tips

9. **Set mode to POSITION first** - Position control actions require `type: set_mode` / `mode: POSITION` before they can execute.

10. **Use `wait: true` (default)** - Most position commands should wait for completion to ensure proper sequencing.

11. **Set appropriate timeouts** - Position commands can take varying amounts of time; set timeouts to handle stuck situations.

12. **Waypoint types matter**:
    - Use `PASS` for smooth path following (robot curves through waypoints)
    - Use `STOP` when the robot must come to a full stop at a waypoint

13. **Waypoint weights control cornering**:
    - `weight: 1.0` = sharp corner (follows waypoint closely)
    - `weight: 0.0` = smooth curve (may cut corners significantly)
    - `weight: 0.75` = balanced default

14. **Per-waypoint speed limits**:
    - `speed: 0.0` = use path's max_speed (default)
    - `speed: 0.2` = limit to 0.2 m/s when approaching this waypoint
    - Speed transitions smoothly between waypoints (~0.5s)
    - Corner slowdown still applies (takes minimum)
    - Useful for precision positioning or fast straight segments

15. **Path files for reusable routes** - Store frequently used paths in YAML files for easy reuse.

16. **Use `wait_position_event` for complex logic** - When you need to react to specific events like `waypoint_completed`.

---

## File Location

Experiment files should be placed in:
```
~/robot/experiments/
```

The experiment handler will look for files in this directory.
