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
#include "firmware_addresses.h"
#include "bilbo_message.h"

void sendMessage(BILBO_Message_t &message);

typedef enum bilbo_drive_type_t : uint8_t {
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

typedef enum bilbo_drive_status_t : uint8_t {
	BILBO_DRIVE_STATUS_OK = 1,
	BILBO_DRIVE_STATUS_ERROR = 2,
} bilbo_drive_status_t;

typedef struct bilbo_logging_drive_t {
	uint8_t status;
	uint8_t motor_mode_left;
	uint8_t motor_mode_right;
} bilbo_logging_drive_t;

typedef struct drive_event_message_data_t {
	uint8_t status;
	uint32_t tick;
} drive_event_message_data_t;

typedef BILBO_Message<drive_event_message_data_t, MSG_EVENT,
	BILBO_MESSAGE_DRIVE_EVENT> BILBO_Message_Drive_Event;

// Number of immediate retries per failed operation (with bus reset between)
#define BILBO_DRIVE_MAX_RETRIES 1
// Consecutive failed task cycles before entering fatal error state
#define BILBO_DRIVE_MAX_CONSECUTIVE_ERRORS 3

class BILBO_Drive {
public:

	BILBO_Drive();

	HAL_StatusTypeDef init(bilbo_drive_config_t config,
			BILBO_Drive_Motor* motor_left,
			BILBO_Drive_Motor* motor_right);

	HAL_StatusTypeDef start();
	HAL_StatusTypeDef stop();
	HAL_StatusTypeDef emergencyStop();
	bool resetDrive();

	bilbo_drive_speed_t getSpeed();
	void setTorque(bilbo_drive_input_t input);
	float getVoltage();
	bilbo_logging_drive_t getSample();

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
	volatile bool _reset_requested = false;

	simplexmotion_mode_t _motor_mode_left = SM_MODE_UNKNOWN;
	simplexmotion_mode_t _motor_mode_right = SM_MODE_UNKNOWN;
};


void startDriveTask(void* drive);



#endif /* DRIVE_BILBO_DRIVE_H_ */
