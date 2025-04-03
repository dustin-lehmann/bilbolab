/*
 * bilbo_drive_motor.h
 *
 *  Created on: Mar 10, 2025
 *      Author: lehmann
 */

#ifndef DRIVE_BILBO_DRIVE_MOTOR_H_
#define DRIVE_BILBO_DRIVE_MOTOR_H_

#include "firmware_core.h"

class BILBO_Drive_Motor {
public:

	BILBO_Drive_Motor();
	virtual ~BILBO_Drive_Motor();  // Add this!

	virtual HAL_StatusTypeDef start() = 0;

	virtual HAL_StatusTypeDef checkCommunication() = 0;
	virtual HAL_StatusTypeDef checkMotor() = 0;

	virtual HAL_StatusTypeDef beep(uint16_t amplitude) = 0;
	virtual HAL_StatusTypeDef setTorque(float torque) = 0;
	virtual HAL_StatusTypeDef getTemperature(float &temperature) = 0;
	virtual HAL_StatusTypeDef getVoltage(float &voltage) = 0;

	virtual HAL_StatusTypeDef readSpeed(float &speed) = 0;
	virtual HAL_StatusTypeDef stop() = 0;

	virtual HAL_StatusTypeDef setTorqueLimit(float maxTorque) = 0;

};

#endif /* DRIVE_BILBO_DRIVE_MOTOR_H_ */
