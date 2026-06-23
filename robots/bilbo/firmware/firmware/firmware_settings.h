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
//#define BOARD_REV_3
#define BOARD_REV_4

// Robot model (sets wheel diameter and wheel distance in bilbo_model.h)
#define BILBO_MODEL_NORMAL
//#define BILBO_MODEL_SMALL
//#define BILBO_MODEL_BIG

/* ================================================================
 * MOTOR INTERFACE — uncomment ONE
 * ================================================================ */

// SimplexMotion communication bus
//#define BILBO_DRIVE_SIMPLEXMOTION_RS485
#define BILBO_DRIVE_SIMPLEXMOTION_CAN

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
// Set to 0 to disable. When disabled, the motor's watchdog events are actively
// torn down at init (disableWatchdog) so any events left armed by a previously-
// flashed watchdog-enabled firmware cannot trigger a spurious Quickstop.
#define BILBO_DRIVE_WATCHDOG_ENABLE 0

// Watchdog counter reload value, written by STM32 each drive task cycle.
// Timeout = reload × 64ms. Default 10 → 640ms.
#define BILBO_DRIVE_WATCHDOG_RELOAD 10

// Initial counter value written during motor init. Must be large enough
// to survive the time between motor init and the first drive task cycle.
// Default 100 → 6.4s.
#define BILBO_DRIVE_WATCHDOG_INITIAL 100

/* ================================================================
 * LED STRIP — select external LED strip driver
 * ================================================================ */

// LED_STRIP_I2C:   WS2812 strip driven via I2C extender (default, rev3/rev4)
// LED_STRIP_APA102: APA102 strip driven via SPI (direct from STM32)
//#define LED_STRIP_APA102
#define LED_STRIP_I2C

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
 * MANUAL NUDGE ("free from wall")
 * ================================================================ */

// One-shot nudge to roll the robot a defined distance when it is lying on the floor
// (executable only in OFF mode), driven OPEN-LOOP in PWM (mode 10) rather than with
// a position loop: the position loop rings badly on the robot's reflected inertia,
// whereas open-loop PWM just rolls the wheel and is speed-bounded (no torque-style
// runaway). The firmware watches the encoder and cuts the PWM once each wheel has
// rolled the commanded distance (or stalls).

// PWM duty for the nudge: signed motor-voltage setpoint (TargetInput in mode 10),
// where +-32767 = +-100% voltage. Low = slow roll. Raise it if the loaded wheel
// will not break free from stiction; lower it if the move is too fast/jerky.
// WARNING: torque is NOT limited in PWM mode — keep this modest and never run it
// against a blocked wheel (the stall guard below cuts it, but start conservative).
#define BILBO_NUDGE_PWM 3000             // ~9% of full voltage

// Wheel-sync trim: the two open-loop wheels run at slightly different speeds, so
// the robot would curve. Each wheel's PWM is trimmed by (SYNC_KP * position
// difference in counts) to keep them matched and roll straight. Higher = straighter
// but jerkier; lower = smoother but curves more. The trim is clamped to
// +-BILBO_NUDGE_PWM and the resulting PWM to +-BILBO_NUDGE_PWM_MAX. 8192 cnt = 1 rev.
#define BILBO_NUDGE_SYNC_KP 4
#define BILBO_NUDGE_PWM_MAX 7000

// Stall guard: if a wheel advances fewer than _STALL_MIN_COUNTS encoder counts
// within _STALL_CHECK_MS, it is treated as blocked and its PWM is cut (protects the
// motor, since PWM mode does not limit current). 8192 counts = one wheel rev.
#define BILBO_NUDGE_STALL_CHECK_MS 500
#define BILBO_NUDGE_STALL_MIN_COUNTS 20

// Max time a nudge runs before the motors are released back to torque/OFF (ms).
#define BILBO_NUDGE_TIMEOUT_MS 8000

// Only nudge when the robot is clearly lying over: |theta| above this (radians,
// ~20 deg). The move direction is chosen from sign(theta) to roll away from the fall.
#define BILBO_NUDGE_MIN_THETA 0.35f

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

#define BILBO_FIRMWARE_REVISION_MAJOR 0x03
#define BILBO_FIRMWARE_REVISION_MINOR 0x00

#endif /* FIRMWARE_SETTINGS_H_ */
