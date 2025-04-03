/*
 * bilbo_drive.h
 *
 *  Created on: Mar 10, 2025
 *      Author: lehmann
 */

#ifndef DRIVE_BILBO_DRIVE_H_
#define DRIVE_BILBO_DRIVE_H_

#include "firmware_core.h"
#include "bilbo_drive_motor.h"
#include "stm32h7xx_hal.h"
#include "core.h"
#include "robot-control_std.h"

typedef enum bilbo_drive_type_t {
	BILBO_DRIVE_SM_RS485 = 1,
	BILBO_DRIVE_SM_CAN = 2,
	BILBO_DRIVE_MAB = 3
} bilbo_drive_type_t;


typedef struct bilbo_drive_config_t {
	bilbo_drive_type_t type;
	float torque_max;
	uint32_t task_time;
} bilbo_drive_config_t;


typedef struct bilbo_drive_speed_t {
	float left;
	float right;
} bilbo_drive_speed_t;

typedef struct bilbo_drive_input_t {
	float torque_left;
	float torque_right;
} bilbo_drive_input_t;

typedef enum bilbo_drive_status_t {
	BILBO_DRIVE_STATUS_OK = 1,
	BILBO_DRIVE_STATUS_ERROR = 2,
} bilbo_drive_status_t;

class BILBO_Drive {
public:

	BILBO_Drive();

	HAL_StatusTypeDef init(bilbo_drive_config_t config,
			BILBO_Drive_Motor* motor_left,
			BILBO_Drive_Motor* motor_right);

	HAL_StatusTypeDef start();
	HAL_StatusTypeDef stop();

	bilbo_drive_speed_t getSpeed();
	void setTorque(bilbo_drive_input_t input);
	float getVoltage();

	void task();

	uint32_t tick=0;
	bilbo_drive_config_t config;
	bilbo_drive_status_t status = BILBO_DRIVE_STATUS_OK;
	BILBO_Drive_Motor* motor_left;
	BILBO_Drive_Motor* motor_right;

private:

	float _voltage = 0;
	bilbo_drive_speed_t _speed = {0};
	bilbo_drive_input_t _input = {0};
};


void startDriveTask(void* drive);



#endif /* DRIVE_BILBO_DRIVE_H_ */
