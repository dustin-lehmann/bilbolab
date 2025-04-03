/*
 * twipr_drive.h
 *
 *  Created on: 22 Feb 2023
 *      Author: Dustin Lehmann
 */

#ifndef DRIVE_TWIPR_DRIVE_H_
#define DRIVE_TWIPR_DRIVE_H_

#include "core.h"
#include "simplexmotion.hpp"
#include "twipr_errors.h"
#include "robot-control_std.h"

#define TWIPR_DRIVE_MAIN_TASK_TIME_MS 10
#define WAIT_TIME_BETWEEN_REQUESTS_MS 1
#define TWIPR_DRIVE_VOLTAGE_TIME_MS 1000

typedef enum twipr_drive_status_t {
	TWIPR_DRIVE_STATUS_IDLE,
	TWIPR_DRIVE_STATUS_STOP,
	TWIPR_DRIVE_STATUS_RUNNING,
	TWIPR_DRIVE_STATUS_ERROR,
} twipr_drive_status_t;

typedef enum twipr_drive_error_t {
	TWIPR_DRIVE_ERROR_NONE = 0,
	TWIPR_DRIVE_ERROR_INIT = 0x00000201,
	TWIPR_DRIVE_ERROR_COMM = 0x00000202,
	TWIPR_DRIVE_ERROR_TORQUE = 0x00000203,
	TWIPR_DRIVE_ERROR_TEMP = 0x00000204,
	TWIPR_DRIVE_ERROR_VOLTAGE = 0x00000205,
	TWIPR_DRIVE_ERROR_INTERNAL = 0x00000206
} twipr_drive_error_t;

typedef struct twipr_drive_speed_t {
	float speed_left;
	float speed_right;
} twipr_drive_speed_t;

typedef struct twipr_drive_input_t {
	float torque_left;
	float torque_right;
} twipr_drive_input_t;

typedef struct twipr_drive_config_t {
	uint8_t id_left;
	uint8_t id_right;
	int8_t direction_left;
	int8_t direction_right;
	float torque_max;
	modbus_config_t modbus_config;
} twipr_drive_config_t;

class TWIPR_Drive_RS485 {
public:
	TWIPR_Drive_RS485();
	uint8_t init(twipr_drive_config_t config);
	void start();
	void stop();
	void check();
	uint8_t startup_check();
	void update();



	void task();

	void setTorque(twipr_drive_input_t input);
	void setTorque(float torque_left, float torque_right);
	twipr_drive_status_t getState();

	twipr_drive_speed_t getSpeed();
	float getVoltage();




	twipr_drive_status_t status = TWIPR_DRIVE_STATUS_IDLE;
	twipr_drive_error_t error = TWIPR_DRIVE_ERROR_NONE;

	uint32_t tick = 0;
	uint32_t race_conditions = 0;

private:
	ModbusMaster modbus;

	SimplexMotionMotor motor_left;
	SimplexMotionMotor motor_right;

	twipr_drive_config_t _config;
	twipr_drive_input_t _last_input;
	twipr_drive_speed_t _speed;
	float _drive_voltage;


	void _error_handler(uint32_t error);

	float _readVoltage();
};

void startDriveTask(void* drive);
void twipr_drive_speed_task(void* drive);

#endif /* DRIVE_TWIPR_DRIVE_H_ */
