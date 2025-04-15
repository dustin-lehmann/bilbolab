/*
 * simplexmotion_rs485.cpp
 *
 *  Created on: Mar 10, 2025
 *      Author: lehmann
 */

#include "simplexmotion_rs485.h"

SimplexMotion_RS485::SimplexMotion_RS485(){

}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::init(
		simplexmotion_rs485_config_t config) {
	this->config = config;

	HAL_StatusTypeDef status;

	// Check the communication
	status = this->checkCommunication();



	if (status) {
		return HAL_ERROR;
	}
	// Read the Firmware Version

	uint16_t software_rev = 0;
	status = this->readSoftwareRev(software_rev);

	// Reset the motor
	status = this->setMode(SIMPLEXMOTION_RS485_MODE_RESET);

	if (status) {
		return HAL_ERROR;
	}

	// Set the torque limit
	status = this->setTorqueLimit(this->config.torque_limit);

	if (status) {
		return HAL_ERROR;
	}


	// Beep

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::start() {
	HAL_StatusTypeDef status;

	status = this->setTarget(0);

	if (status) {
		return HAL_ERROR;
	}

	status = this->setMode(SIMPLEXMOTION_RS485_MODE_TORQUE);

	if (status) {
		return HAL_ERROR;
	}

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::checkCommunication() {
	simplexmotion_rs485_mode_t mode;
	HAL_StatusTypeDef status = this->readMode(mode);
	return status;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::checkMotor() {
	HAL_StatusTypeDef status;
	// Check the communication
	status = this->checkCommunication();
	if (status) {
		return status;
	}
	status = this->beep(500);
	if (status) {
		return status;
	}
	osDelay(150);
	status = this->stop();

	if (status) {
		return status;
	}

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::beep(uint16_t amplitude) {
	HAL_StatusTypeDef ret;
	ret = this->setMode(SIMPLEXMOTION_RS485_MODE_BEEP);

	// Set the amplitude
	ret = this->setTarget((int32_t) amplitude);

	return ret;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::setTorque(float torque) {
	// First check if torque mode has been set
	if (!(this->mode == SIMPLEXMOTION_RS485_MODE_TORQUE)) {
		return HAL_ERROR;
	}

	// Calculate the corresponding torque value
	int16_t torque_value_int = (int16_t) (this->config.direction * torque
			/ this->config.torque_limit * 32767.0);
	int32_t target_input = (int32_t) torque_value_int;

	HAL_StatusTypeDef ret = this->setTarget(target_input);
	return ret;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readHardwareRev() {
	return HAL_ERROR;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readSoftwareRev(uint16_t &software_rev) {
	return HAL_ERROR;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readName() {
	return HAL_ERROR;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::getTemperature(float &temperature) {
	return HAL_ERROR;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::getVoltage(float &voltage) {
	uint16_t voltage_int = 0;
	HAL_StatusTypeDef success = this->readRegisters(
	SIMPLEXMOTION_RS485_REG_VOLTAGE, 1, &voltage_int);

	if (success == HAL_ERROR) {
		return HAL_ERROR;
	}
	voltage = voltage_int * 0.01;

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readSpeed(float &speed) {
	uint16_t speed_raw = 0;
	HAL_StatusTypeDef success = this->readRegisters(
	SIMPLEXMOTION_RS485_REG_SPEED, 1, &speed_raw);

	int16_t speed_signed = (int16_t) speed_raw;

	if (success == HAL_ERROR) {
		return HAL_ERROR;
	}
	speed = this->config.direction * 2 * pi * speed_signed / 256;

	return success;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::setMode(
		simplexmotion_rs485_mode_t mode) {
	uint16_t data = (uint16_t) mode;

	// Set the mode
	HAL_StatusTypeDef write_success = this->writeRegisters(
	SIMPLEXMOTION_RS485_REG_MODE, 1, &data);

	if (write_success == HAL_ERROR) {
		return HAL_ERROR;
	}

	// Read back the mode
	uint16_t rx_data = 0;
	HAL_StatusTypeDef read_success = this->readRegisters(
	SIMPLEXMOTION_RS485_REG_MODE, 1, &rx_data);

	if (read_success == HAL_ERROR) {
		return HAL_ERROR;
	}

	this->mode = (simplexmotion_rs485_mode_t) rx_data;

	if (rx_data != mode) {
		return HAL_ERROR;
	}
	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readMode(
		simplexmotion_rs485_mode_t &mode) {
	uint16_t rx_data = 0;
	HAL_StatusTypeDef read_success = this->readRegisters(
	SIMPLEXMOTION_RS485_REG_MODE, 1, &rx_data);

	if (read_success == HAL_ERROR) {
		return HAL_ERROR;
	}

	mode = (simplexmotion_rs485_mode_t) rx_data;

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::stop() {
	HAL_StatusTypeDef status;
	status = this->setTarget(0);
	if (status) {
		return HAL_ERROR;
	}
	//	status = this->setMode(SIMPLEXMOTION_CAN_MODE_OFF);
	//	if (status) {
	//		return HAL_ERROR;
	//	}
	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::setTorqueLimit(float maxTorque) {
	uint16_t torque_limit_int = (uint16_t) (maxTorque * 1000);

	HAL_StatusTypeDef ret;

	ret = this->writeRegisters(SIMPLEXMOTION_RS485_REG_TORQUE_LIMIT, 1,
			&torque_limit_int);

	if (ret == HAL_ERROR) {
		return HAL_ERROR;
	}

	uint16_t torque_limit_int_check = 0;
	ret = this->readRegisters(SIMPLEXMOTION_RS485_REG_TORQUE_LIMIT, 1,
			&torque_limit_int_check);

	if (ret == HAL_ERROR) {
		return HAL_ERROR;
	}

	if (torque_limit_int != torque_limit_int_check) {
		return HAL_ERROR;
	}

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::setTarget(int32_t target) {
	HAL_StatusTypeDef ret;
	uint16_t tx_data[2] = { 0 };

	tx_data[0] = target >> 16;
	tx_data[1] = target & 0xFFFF;

	ret = this->writeRegisters(SIMPLEXMOTION_RS485_REG_TARGET_INPUT, 2,
			tx_data);
	return ret;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::writeRegisters(uint16_t address,
		uint16_t num_registers, uint16_t *data) {

	int32_t u32NotificationValue;
	modbus_query_t telegram;

	telegram.u8id = this->config.id;

	if (num_registers > 1) {
		telegram.u8fct = MB_FC_WRITE_MULTIPLE_REGISTERS;
	} else {
		telegram.u8fct = MB_FC_WRITE_REGISTER;
	}
	telegram.u16RegAdd = address;
	telegram.u16CoilsNo = num_registers;
	telegram.u16reg = data;

	this->config.modbus->query(telegram);
//	u32NotificationValue = ulTaskNotifyTake(pdTRUE, portMAX_DELAY); // block until query finished
//	uint32_t ticks1 = osKernelGetTickCount();
	u32NotificationValue = ulTaskNotifyTake(pdTRUE, portMAX_DELAY); // block until query finished
//	uint32_t ticks2 = osKernelGetTickCount();

	if (u32NotificationValue != ERR_OK_QUERY) {
		if (u32NotificationValue == ERR_TIME_OUT) {
			return HAL_ERROR;
		}
		return HAL_OK;
	} else {
		return HAL_OK;
	}
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readRegisters(uint16_t address,
		uint16_t num_registers, uint16_t *data) {
	int32_t u32NotificationValue;
	modbus_query_t telegram;

	telegram.u8id = this->config.id;
	telegram.u8fct = MB_FC_READ_REGISTERS;
	telegram.u16RegAdd = address;
	telegram.u16CoilsNo = num_registers;
	telegram.u16reg = data;

	this->config.modbus->query(telegram);
	u32NotificationValue = ulTaskNotifyTake(pdTRUE, portMAX_DELAY); // block until query finished
	if (u32NotificationValue != ERR_OK_QUERY) {
		if (u32NotificationValue == ERR_TIME_OUT) {
			nop();
		}

		return HAL_ERROR;
	} else {
		return HAL_OK;
	}
}
