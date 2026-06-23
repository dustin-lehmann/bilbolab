/*
 * bilbo_drive_motor.h
 *
 *  Created on: Mar 10, 2025
 *      Author: lehmann
 */

#ifndef DRIVE_BILBO_DRIVE_MOTOR_H_
#define DRIVE_BILBO_DRIVE_MOTOR_H_

#include "firmware_core.h"

// Common motor mode enum — values match SimplexMotion register 400
typedef enum simplexmotion_mode_t : uint8_t {
	SM_MODE_OFF = 0,
	SM_MODE_RESET = 1,
	SM_MODE_SHUTDOWN = 4,
	SM_MODE_QUICKSTOP = 5,
	SM_MODE_FIRMWARE = 6,
	SM_MODE_PWM = 10,
	SM_MODE_FREEWHEEL = 19,
	SM_MODE_POSITION = 20,
	SM_MODE_POSITION_RAMP = 21,
	SM_MODE_SPEED = 32,
	SM_MODE_SPEED_RAMP = 33,
	SM_MODE_SPEED_LOW = 34,
	SM_MODE_SPEED_LOW_RAMP = 35,
	SM_MODE_TORQUE = 40,
	SM_MODE_BEEP = 60,
	SM_MODE_HOMING = 70,
	SM_MODE_COGGING = 110,
	SM_MODE_UNKNOWN = 255,
} simplexmotion_mode_t;

// Result of polling an in-progress open-loop nudge (see startPwmNudge()).
typedef enum pwm_nudge_state_t : uint8_t {
	PWM_NUDGE_MOVING = 0,   // still rolling toward the target
	PWM_NUDGE_REACHED = 1,  // reached the commanded distance (PWM cut)
	PWM_NUDGE_STALLED = 2,  // stopped progressing / blocked (PWM cut)
} pwm_nudge_state_t;

class BILBO_Drive_Motor {
public:

	BILBO_Drive_Motor();
	virtual ~BILBO_Drive_Motor();  // Add this!

	virtual HAL_StatusTypeDef start() = 0;

	virtual HAL_StatusTypeDef checkCommunication() = 0;
	virtual HAL_StatusTypeDef checkMotor() = 0;

	virtual HAL_StatusTypeDef beep(uint16_t amplitude) = 0;
	virtual HAL_StatusTypeDef setTorque(float torque) = 0;

	// Open-loop "nudge" support (default: unsupported). Rolls the wheels a bounded,
	// defined distance to free the robot from a wall WITHOUT a position loop (which
	// rings on this high-inertia load). enterPwmMode() switches to open-loop PWM;
	// startPwmNudge() begins rolling the given signed wheel revolutions (robot
	// frame; the motor applies its own mounting direction) at the given PWM duty;
	// updatePwmNudge() is polled each cycle and cuts the PWM once the wheel reaches
	// the target (REACHED) or stops progressing (STALLED). enterTorqueMode()
	// returns to torque control.
	virtual HAL_StatusTypeDef enterTorqueMode() { return HAL_ERROR; }
	virtual HAL_StatusTypeDef enterPwmMode() { return HAL_ERROR; }
	virtual HAL_StatusTypeDef startPwmNudge(float wheel_revolutions, int16_t pwm) {
		return HAL_ERROR;
	}
	virtual pwm_nudge_state_t updatePwmNudge() { return PWM_NUDGE_STALLED; }
	// Robot-frame distance rolled since the nudge started (encoder counts), and a
	// PWM trim (robot frame) applied to keep the two wheels matched (straight nudge).
	virtual int32_t getRobotProgress() { return 0; }
	virtual void setSyncTrim(int16_t robot_trim) {}
	virtual HAL_StatusTypeDef getTemperature(float &temperature) = 0;
	virtual HAL_StatusTypeDef getVoltage(float &voltage) = 0;

	virtual HAL_StatusTypeDef readSpeed(float &speed) = 0;
	virtual HAL_StatusTypeDef stop() = 0;
	virtual HAL_StatusTypeDef emergencyStop() = 0;

	virtual HAL_StatusTypeDef setTorqueLimit(float maxTorque) = 0;

	// Reset the underlying bus (CAN/RS485). Default: no-op.
	// Called by the drive task to recover from transient bus errors.
	virtual void resetBus() {}

	// Motor watchdog: configures motor-internal countdown + quickstop events.
	// Called during motor init. Default: no-op (for motors without event support).
	virtual HAL_StatusTypeDef configureWatchdog() { return HAL_OK; }

	// Motor watchdog: reloads the countdown counter to prevent timeout.
	// Called every drive task cycle. Default: no-op.
	virtual HAL_StatusTypeDef feedWatchdog() { return HAL_OK; }

	// Motor watchdog: tears down the countdown + quickstop events.
	// Called during motor init when the watchdog is disabled, to clear any
	// events left armed by a previously-flashed watchdog-enabled firmware.
	// Default: no-op (for motors without event support).
	virtual HAL_StatusTypeDef disableWatchdog() { return HAL_OK; }

	// Read the current motor mode from the motor controller.
	// Default: not supported.
	virtual HAL_StatusTypeDef readMotorMode(simplexmotion_mode_t &mode) {
		mode = SM_MODE_UNKNOWN;
		return HAL_ERROR;
	}

};

#endif /* DRIVE_BILBO_DRIVE_MOTOR_H_ */
