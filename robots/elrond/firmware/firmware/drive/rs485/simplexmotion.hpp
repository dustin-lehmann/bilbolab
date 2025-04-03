/*
 * simplexmotion.hpp
 *
 *  Created on: 15 Feb 2023
 *      Author: lehmann_workstation
 */

#ifndef ROBOT_SIMPLEXMOTION_MOTORS_SIMPLEXMOTION_HPP_
#define ROBOT_SIMPLEXMOTION_MOTORS_SIMPLEXMOTION_HPP_

#include "modbus_rtu.h"
#include "../../utils/core_utils_Callback.h"

#define SIMPLEXMOTION_REG_NAME 9
#define SIMPLEXMOTION_REG_SW_REV 1
#define SIMPLEXMOTION_REG_HW_REV 2
#define SIMPLEXMOTION_REG_VOLTAGE 99
#define SIMPLEXMOTION_REG_TEMP_ELECTRONICS 100
#define SIMPLEXMOTION_REG_TEMP_MOTORS 101
#define SIMPLEXMOTION_REG_TARGET_INPUT 449
#define SIMPLEXMOTION_REG_TARGET_SELECT 451

#define SIMPLEXMOTION_REG_POSITION 199
#define SIMPLEXMOTION_REG_SPEED 201

#define SIMPLEXMOTION_REG_TORQUE_LIMIT 203
#define SIMPLEXMOTION_REG_MODE 399
#define SIMPLEXMOTION_REG_TIME 419
#define SIMPLEXMOTION_REG_STATUS 409
#define SIMPLEXMOTION_REG_ERROR 414

typedef enum simplexmotion_mode_t {
	SIMPLEXMOTION_MODE_OFF = 0,
	SIMPLEXMOTION_MODE_RESET = 1,
	SIMPLEXMOTION_MODE_TORQUE = 40,
	SIMPLEXMOTION_MODE_SPEEDRAMP = 33,
	SIMPLEXMOTION_MODE_SPEEDLOWRAMP = 34,
	SIMPLEXMOTION_MODE_QUICKSTOP = 5,
	SIMPLEXMOTION_MODE_BEEP = 60,
	SIMPLEXMOTION_MODE_COGGING = 110,
} simplexmotion_mode_t;

typedef enum simplexmotion_error {
	SIMPLEXMOTION_ERROR_INTERNAL_GENERAL = 0x0001,
	SIMPLEXMOTION_ERROR_INTERNAL_SOFTWARE = 0x0002,
	SIMPLEXMOTION_ERROR_INTERNAL_APPLICATION = 0x0003,
	SIMPLEXMOTION_ERROR_INTERNAL_COMMUNICATION = 0x1001,
	SIMPLEXMOTION_ERROR_INTERNAL_INVALID_REGISTER = 0x1002,
	SIMPLEXMOTION_ERROR_INTERNAL_OVERCURRENT = 0x2001,
	SIMPLEXMOTION_ERROR_INTERNAL_VOLTAGE_LOW = 0x3001,
	SIMPLEXMOTION_ERROR_INTERNAL_VOLTAGE_HIGH = 0x3002,
	SIMPLEXMOTION_ERROR_INTERNAL_TEMP_ELEC = 0x4001,
	SIMPLEXMOTION_ERROR_INTERNAL_TEMP_MOTOR = 0x4002,
	SIMPLEXMOTION_ERROR_INTERNAL_TORQUE_LIMIT = 0x5001,
	SIMPLEXMOTION_ERROR_INTERNAL_LOCKED_SHAFT = 0x6001,
	SIMPLEXMOTION_ERROR_INTERNAL_REGULATOR = 0x7001,
	SIMPLEXMOTION_ERROR_EXTERNAL_CONNECTION = 0x8001 // my own error code
} simplexmotion_error;

typedef struct simplexmotion_status_t {
	uint8_t fail;
	uint8_t communication_error;
	uint8_t current_error;
	uint8_t voltage_error;
	uint8_t temperature_error;
	uint8_t torque_limit;
	uint8_t regulator_error;
	uint8_t moving;
	uint8_t locked;
	uint8_t reverse;
	uint8_t target;
} simplexmotion_status_t;

typedef enum simplexmotion_callback_id {
	SIMPLEXMOTION_CB_ERROR = 0,
} simplexmotion_callback_id;

typedef struct simplexmotion_callbacks {
	core_utils_Callback<void, void> error;
} simplexmotion_callbacks;

typedef struct simplexmotion_config_t {
	uint8_t id;
	int8_t direction;
	ModbusMaster *modbus;
} simplexmotion_config_t;

class SimplexMotionMotor {

public:
	SimplexMotionMotor();

	uint8_t init(simplexmotion_config_t config);
	void start(simplexmotion_mode_t mode);

	void registerCallback(simplexmotion_callback_id callback_id, core_utils_Callback<void, void> callback);

	uint8_t writeRegisters(uint16_t address, uint16_t num_registers,
			uint16_t *data);
	uint8_t readRegisters(uint16_t address, uint16_t num_registers,
			uint16_t *data);

	uint8_t startup_check();
	uint8_t check();

	uint8_t setTarget(int32_t target);
	uint8_t setTorque(float torque);
	uint8_t setSpeed(float speed);
	float getTorque(); // REG 203
	float getPosition();
	int32_t getPositionRaw();
	float getSpeed();
	float getTorqueLimit();
	float getTemperature();
	float getVoltage();

	uint8_t getStatus(simplexmotion_status_t *status);

	uint8_t readError();
	uint32_t readTime();

	uint8_t startCoggingCalibration();
	uint8_t setTorqueLimit(float maxTorque);
	uint8_t setRampSpeedLimit(float speedlimit); //! For torque_limit mode

	uint8_t readHardwareRev();
	uint8_t readSoftwareRev();
	uint8_t readName();
	uint8_t setAddress(uint8_t address);

	uint8_t setMode(simplexmotion_mode_t mode);
	simplexmotion_mode_t readMode();
	uint8_t emergencyStop();
	uint8_t stop();
	uint8_t beep(uint16_t amplitude);
	uint8_t reset();

	uint16_t mode;

private:

	simplexmotion_callbacks callbacks;
	uint16_t rx_buffer[8];
	uint16_t tx_buffer[8];

	uint8_t connected;
	simplexmotion_error last_error;

	float torque_limit = 0;

	void error_handler(simplexmotion_error error);

	uint8_t _init = 0;
	uint8_t _checked = 0;
	uint8_t _ready = 0;
	simplexmotion_config_t _config;
};

#endif /* ROBOT_SIMPLEXMOTION_MOTORS_SIMPLEXMOTION_HPP_ */
