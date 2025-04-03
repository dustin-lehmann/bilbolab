/*
 * twipr_drive_can.h
 *
 *  Created on: Nov 29, 2024
 *      Author: lehmann
 */

#ifndef DRIVE_TWIPR_DRIVE_CAN_H_
#define DRIVE_TWIPR_DRIVE_CAN_H_

#include "stm32h7xx_hal.h"
#include "core.h"
#include "robot-control_std.h"


#define TWIPR_DRIVE_CAN_MAIN_TASK_TIME_MS 10

#define SIMPLEXMOTION_CAN_REG_NAME 10
#define SIMPLEXMOTION_CAN_REG_SW_REV 2
#define SIMPLEXMOTION_CAN_REG_HW_REV 12
#define SIMPLEXMOTION_CAN_REG_VOLTAGE 100
#define SIMPLEXMOTION_CAN_REG_TEMP_ELECTRONICS 101
#define SIMPLEXMOTION_CAN_REG_TEMP_MOTORS 102
#define SIMPLEXMOTION_CAN_REG_TARGET_INPUT 450
#define SIMPLEXMOTION_CAN_REG_TARGET_SELECT 452

#define SIMPLEXMOTION_CAN_REG_POSITION 200
#define SIMPLEXMOTION_CAN_REG_SPEED 202

#define SIMPLEXMOTION_CAN_REG_TORQUE_LIMIT 204
#define SIMPLEXMOTION_CAN_REG_MODE 400
#define SIMPLEXMOTION_CAN_REG_TIME 420
#define SIMPLEXMOTION_CAN_REG_STATUS 410
#define SIMPLEXMOTION_CAN_REG_ERROR 415



#define SIMPLEXMOTION_CAN_REMOTE_TIMEOUT 10

typedef struct twipr_drive_can_config_t {
	CAN *can;
	uint8_t id_left;
	uint8_t id_right;
	int8_t direction_left;
	int8_t direction_right;
	float torque_max;
} twipr_drive_can_config_t;

typedef enum simplexmotion_can_mode_t {
	SIMPLEXMOTION_CAN_MODE_OFF = 0,
	SIMPLEXMOTION_CAN_MODE_RESET = 1,
	SIMPLEXMOTION_CAN_MODE_TORQUE = 40,
	SIMPLEXMOTION_CAN_MODE_SPEEDRAMP = 33,
	SIMPLEXMOTION_CAN_MODE_SPEEDLOWRAMP = 34,
	SIMPLEXMOTION_CAN_MODE_QUICKSTOP = 5,
	SIMPLEXMOTION_CAN_MODE_BEEP = 60,
	SIMPLEXMOTION_CAN_MODE_COGGING = 110,
} simplexmotion_can_mode_t;

typedef enum simplexmotion_can_error {
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_GENERAL = 0x0001,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_SOFTWARE = 0x0002,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_APPLICATION = 0x0003,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_COMMUNICATION = 0x1001,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_INVALID_REGISTER = 0x1002,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_OVERCURRENT = 0x2001,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_VOLTAGE_LOW = 0x3001,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_VOLTAGE_HIGH = 0x3002,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_TEMP_ELEC = 0x4001,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_TEMP_MOTOR = 0x4002,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_TORQUE_LIMIT = 0x5001,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_LOCKED_SHAFT = 0x6001,
	SIMPLEXMOTION_CAN_ERROR_INTERNAL_REGULATOR = 0x7001,
	SIMPLEXMOTION_CAN_ERROR_EXTERNAL_CONNECTION = 0x8001 // my own error code
} simplexmotion_can_error;

typedef struct simplexmotion_can_config_t {
	CAN *can;
	uint8_t id;
	int8_t direction;
	float torque_limit;
} simplexmotion_can_config_t;


typedef struct twipr_drive_can_speed_t {
	float speed_left;
	float speed_right;
}twipr_drive_can_speed_t;

typedef struct twipr_drive_can_input_t {
	float torque_left;
	float torque_right;
} twipr_drive_can_input_t;


typedef enum twipr_drive_can_status_t {
	TWIPR_DRIVE_CAN_STATUS_STOP,
	TWIPR_DRIVE_CAN_STATUS_RUNNING,
	TWIPR_DRIVE_CAN_STATUS_ERROR,
} twipr_drive_can_status_t;


class SimplexMotion_CAN {
public:

	SimplexMotion_CAN();
	HAL_StatusTypeDef init(simplexmotion_can_config_t config);
	HAL_StatusTypeDef start(simplexmotion_can_mode_t mode=SIMPLEXMOTION_CAN_MODE_OFF);


	HAL_StatusTypeDef checkCommunication();

	HAL_StatusTypeDef checkMotor();

	HAL_StatusTypeDef setTarget(int32_t target);

	HAL_StatusTypeDef beep(uint16_t amplitude);
	HAL_StatusTypeDef setTorque(float torque);
	HAL_StatusTypeDef readHardwareRev();
	HAL_StatusTypeDef readSoftwareRev(uint16_t &software_rev);
	HAL_StatusTypeDef readName();
	HAL_StatusTypeDef getTemperature(float &temperature);
	HAL_StatusTypeDef getVoltage(float &voltage);

	HAL_StatusTypeDef readSpeed(float &speed);
	HAL_StatusTypeDef setMode(simplexmotion_can_mode_t mode);
	HAL_StatusTypeDef readMode(simplexmotion_can_mode_t &mode);


	HAL_StatusTypeDef stop();


	HAL_StatusTypeDef setTorqueLimit(float maxTorque);
	HAL_StatusTypeDef getTorqueLimit(float &torque_limit);

	simplexmotion_can_mode_t mode = SIMPLEXMOTION_CAN_MODE_OFF;

	simplexmotion_can_config_t config;

	uint32_t motorTick = 0;
private:

	HAL_StatusTypeDef write(uint16_t reg, uint8_t* data, uint8_t length);
	HAL_StatusTypeDef write(uint16_t reg, float data);
	HAL_StatusTypeDef write(uint16_t reg, uint16_t data);
	HAL_StatusTypeDef write(uint16_t reg, uint32_t data);
	HAL_StatusTypeDef write(uint16_t reg, int16_t data);
	HAL_StatusTypeDef write(uint16_t reg, int32_t data);

	CAN_Status read(uint16_t reg, uint8_t *responseData, uint8_t requestLength, uint8_t &responseLength);

	HAL_StatusTypeDef read(uint16_t reg, float &data);
	HAL_StatusTypeDef read(uint16_t reg, uint16_t &data);
	HAL_StatusTypeDef read(uint16_t reg, int16_t &data);
	HAL_StatusTypeDef read(uint16_t reg, uint32_t &data);
	HAL_StatusTypeDef read(uint16_t reg, int32_t &data);

	uint32_t _getCANHeader(uint16_t reg);
};

class TWIPR_Drive_CAN {
public:

	TWIPR_Drive_CAN();
	HAL_StatusTypeDef init(twipr_drive_can_config_t config);
	HAL_StatusTypeDef start();
	HAL_StatusTypeDef stop();


	twipr_drive_can_speed_t getSpeed();
	HAL_StatusTypeDef setTorque(twipr_drive_can_input_t input);
	float getVoltage();


	void task();

	twipr_drive_can_config_t config;
	SimplexMotion_CAN motor_left;
	SimplexMotion_CAN motor_right;
	twipr_drive_can_input_t input = {0};
	uint32_t tick = 0;
	twipr_drive_can_status_t status = TWIPR_DRIVE_CAN_STATUS_STOP;

private:
	float drive_voltage = 0;
	twipr_drive_can_speed_t speed = {0};
};

void startCANDriveTask(void* drive);

#endif /* DRIVE_TWIPR_DRIVE_CAN_H_ */
