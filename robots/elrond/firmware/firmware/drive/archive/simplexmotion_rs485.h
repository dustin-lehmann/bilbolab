/*
 * simplexmotion_rs485.h
 *
 *  Created on: Mar 10, 2025
 *      Author: lehmann
 */

#ifndef DRIVE_SIMPLEXMOTION_RS485_H_
#define DRIVE_SIMPLEXMOTION_RS485_H_

#include "bilbo_drive_motor.h"
#include "core.h"
#include "robot-control_std.h"

#define SIMPLEXMOTION_CAN_REMOTE_TIMEOUT 5

#define SIMPLEXMOTION_RS485_REG_NAME 9
#define SIMPLEXMOTION_RS485_REG_SW_REV 1
#define SIMPLEXMOTION_RS485_REG_HW_REV 2
#define SIMPLEXMOTION_RS485_REG_VOLTAGE 99
#define SIMPLEXMOTION_RS485_REG_TEMP_ELECTRONICS 100
#define SIMPLEXMOTION_RS485_REG_TEMP_MOTORS 101
#define SIMPLEXMOTION_RS485_REG_TARGET_INPUT 449
#define SIMPLEXMOTION_RS485_REG_TARGET_SELECT 451

#define SIMPLEXMOTION_RS485_REG_POSITION 199
#define SIMPLEXMOTION_RS485_REG_SPEED 201

#define SIMPLEXMOTION_RS485_REG_TORQUE_LIMIT 203
#define SIMPLEXMOTION_RS485_REG_MODE 399
#define SIMPLEXMOTION_RS485_REG_TIME 419
#define SIMPLEXMOTION_RS485_REG_STATUS 409
#define SIMPLEXMOTION_RS485_REG_ERROR 414



typedef enum simplexmotion_rs485_mode_t {
	SIMPLEXMOTION_RS485_MODE_OFF = 0,
	SIMPLEXMOTION_RS485_MODE_RESET = 1,
	SIMPLEXMOTION_RS485_MODE_TORQUE = 40,
	SIMPLEXMOTION_RS485_MODE_SPEEDRAMP = 33,
	SIMPLEXMOTION_RS485_MODE_SPEEDLOWRAMP = 34,
	SIMPLEXMOTION_RS485_MODE_QUICKSTOP = 5,
	SIMPLEXMOTION_RS485_MODE_BEEP = 60,
	SIMPLEXMOTION_RS485_MODE_COGGING = 110,
} simplexmotion_rs485_mode_t;



typedef struct simplexmotion_rs485_config_t {
	ModbusMaster *modbus;
	uint8_t id;
	int8_t direction;
	float torque_limit;
} simplexmotion_rs485_config_t;



class SimplexMotion_RS485: public BILBO_Drive_Motor {
public:
	SimplexMotion_RS485();

	HAL_StatusTypeDef init(simplexmotion_rs485_config_t);
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
	HAL_StatusTypeDef setMode(simplexmotion_rs485_mode_t mode);
	HAL_StatusTypeDef readMode(simplexmotion_rs485_mode_t &mode);
	HAL_StatusTypeDef stop();


	HAL_StatusTypeDef setTorqueLimit(float maxTorque);

	simplexmotion_rs485_config_t config;
	simplexmotion_rs485_mode_t mode;



private:
	HAL_StatusTypeDef setTarget(int32_t target);

	HAL_StatusTypeDef writeRegisters(uint16_t address, uint16_t num_registers,
			uint16_t *data);
	HAL_StatusTypeDef readRegisters(uint16_t address, uint16_t num_registers,
			uint16_t *data);

//	HAL_StatusTypeDef setTarget(int32_t target);
//
//	HAL_StatusTypeDef write(uint16_t reg, uint8_t* data, uint8_t length);
//	HAL_StatusTypeDef write(uint16_t reg, float data);
//	HAL_StatusTypeDef write(uint16_t reg, uint16_t data);
//	HAL_StatusTypeDef write(uint16_t reg, uint32_t data);
//	HAL_StatusTypeDef write(uint16_t reg, int16_t data);
//	HAL_StatusTypeDef write(uint16_t reg, int32_t data);
//
//	CAN_Status read(uint16_t reg, uint8_t *responseData, uint8_t requestLength, uint8_t &responseLength);
//
//	HAL_StatusTypeDef read(uint16_t reg, float &data);
//	HAL_StatusTypeDef read(uint16_t reg, uint16_t &data);
//	HAL_StatusTypeDef read(uint16_t reg, int16_t &data);
//	HAL_StatusTypeDef read(uint16_t reg, uint32_t &data);
//	HAL_StatusTypeDef read(uint16_t reg, int32_t &data);
//
//	uint32_t _getCANHeader(uint16_t reg);

};



#endif /* DRIVE_SIMPLEXMOTION_RS485_H_ */
