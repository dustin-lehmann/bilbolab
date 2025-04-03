/*
 * simplexmotion_can.h
 *
 *  Created on: Mar 10, 2025
 *      Author: lehmann
 */

#ifndef DRIVE_SIMPLEXMOTION_CAN_H_
#define DRIVE_SIMPLEXMOTION_CAN_H_

#include "bilbo_drive_motor.h"
#include "core.h"
#include "robot-control_std.h"

#define SIMPLEXMOTION_CAN_REMOTE_TIMEOUT 5

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



typedef struct simplexmotion_can_config_t {
	CAN *can;
	uint8_t id;
	int8_t direction;
	float torque_limit;
} simplexmotion_can_config_t;



class SimplexMotion_CAN: public BILBO_Drive_Motor {
public:
	SimplexMotion_CAN();

	HAL_StatusTypeDef init(simplexmotion_can_config_t);
	HAL_StatusTypeDef start();

	HAL_StatusTypeDef checkCommunication();
	HAL_StatusTypeDef checkMotor();

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
//	HAL_StatusTypeDef getTorqueLimit(float &torque_limit);

	simplexmotion_can_config_t config;
	simplexmotion_can_mode_t mode;



private:
	HAL_StatusTypeDef setTarget(int32_t target);

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


#endif /* DRIVE_SIMPLEXMOTION_CAN_H_ */
