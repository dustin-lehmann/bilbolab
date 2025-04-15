/*
 * simplexmotion_can.cpp
 *
 *  Created on: Mar 10, 2025
 *      Author: lehmann
 */

#include "simplexmotion_can.h"



SimplexMotion_CAN::SimplexMotion_CAN() {

}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::init(simplexmotion_can_config_t config) {
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
	status = this->setMode(SIMPLEXMOTION_CAN_MODE_RESET);

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

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::start() {
	HAL_StatusTypeDef status;

	status = this->setTarget(0);

	if (status) {
		return HAL_ERROR;
	}

	status = this->setMode(SIMPLEXMOTION_CAN_MODE_TORQUE);

	if (status) {
		return HAL_ERROR;
	}

	return HAL_OK;

}


/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, uint8_t *data,
		uint8_t length) {
	return this->config.can->sendMessage(this->_getCANHeader(reg), data, length);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, float data) {
	uint8_t tx_data[4];
	float_to_bytearray(data, tx_data);
	return this->write(reg, tx_data, 4);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, uint16_t data) {
	uint8_t tx_data[2];
	uint16_to_bytearray(data, tx_data);
	return this->write(reg, tx_data, 2);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, uint32_t data) {
	uint8_t tx_data[4];
	uint32_to_bytearray(data, tx_data);
	return this->write(reg, tx_data, 4);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, int16_t data) {
	uint8_t tx_data[2];
	int16_to_bytearray(data, tx_data);
	return this->write(reg, tx_data, 2);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, int32_t data) {
	uint8_t tx_data[4];
	int32_to_bytearray(data, tx_data);
	return this->write(reg, tx_data, 4);
}

/* --------------------------------------------------------------------- */
CAN_Status SimplexMotion_CAN::read(uint16_t reg, uint8_t *responseData,
		uint8_t requestLength, uint8_t &responseLength) {
	return this->config.can->sendRemoteFrame(this->_getCANHeader(reg),
	SIMPLEXMOTION_CAN_REMOTE_TIMEOUT, responseData, requestLength,
			responseLength);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::read(uint16_t reg, float &data) {
	uint8_t responseData[4];
	uint8_t responseLength = 0;

	CAN_Status status = this->read(reg, responseData, 4, responseLength);

	if (status != CAN_SUCCESS || responseLength != 4) {
		return HAL_ERROR;
	}

	data = bytearray_to_float(responseData);

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::read(uint16_t reg, uint16_t &data) {
	uint8_t responseData[2];
	uint8_t responseLength = 0;

	CAN_Status status = this->read(reg, responseData, 2, responseLength);

	if (status != CAN_SUCCESS || responseLength != 2) {
		return HAL_ERROR;
	}

	data = bytearray_to_uint16(responseData);

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::read(uint16_t reg, int16_t &data) {
	uint8_t responseData[2];
	uint8_t responseLength = 0;

	CAN_Status status = this->read(reg, responseData, 2, responseLength);

	if (status != CAN_SUCCESS || responseLength != 2) {
		return HAL_ERROR;
	}

	data = bytearray_to_int16(responseData);

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::read(uint16_t reg, uint32_t &data) {
	uint8_t responseData[4];
	uint8_t responseLength = 0;

	CAN_Status status = this->read(reg, responseData, 4, responseLength);

	if (status != CAN_SUCCESS || responseLength != 4) {
		return HAL_ERROR;
	}

	data = bytearray_to_uint32(responseData);

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::read(uint16_t reg, int32_t &data) {
	uint8_t responseData[4];
	uint8_t responseLength = 0;

	CAN_Status status = this->read(reg, responseData, 4, responseLength);

	if (status != CAN_SUCCESS || responseLength != 4) {
		return HAL_ERROR;
	}

	data = bytearray_to_int32(responseData);

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::checkCommunication() {
	// Read the mode
	simplexmotion_can_mode_t mode;
	HAL_StatusTypeDef status = this->readMode(mode);
	return status;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::checkMotor() {
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

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::setTorque(float torque) {
	if (this->mode != SIMPLEXMOTION_CAN_MODE_TORQUE) {
		return HAL_ERROR;
	}

	// Calculate the corresponding torque value
	int16_t torque_value_int = (int16_t) (this->config.direction * torque
			/ this->config.torque_limit * 32767.0);

	return this->setTarget((int32_t) torque_value_int);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::readSpeed(float &speed) {
	int16_t speed_int = 0;
	HAL_StatusTypeDef status;

	status = this->read(SIMPLEXMOTION_CAN_REG_SPEED, speed_int);

	if (status) {
		return HAL_ERROR;
	}

	speed = this->config.direction * 2 * pi * speed_int / 256;

	return HAL_OK;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::readHardwareRev() {
	return HAL_ERROR;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::readSoftwareRev(uint16_t &software_rev) {
	return this->read(SIMPLEXMOTION_CAN_REG_SW_REV, software_rev);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::readName() {
	return HAL_ERROR;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::setMode(simplexmotion_can_mode_t mode) {

	HAL_StatusTypeDef status = this->write(SIMPLEXMOTION_CAN_REG_MODE,
			(uint16_t) mode);

	if (status != HAL_OK) {
		return status;
	}

	// Read back the mode
	simplexmotion_can_mode_t mode_read = SIMPLEXMOTION_CAN_MODE_OFF;
	status = this->readMode(mode_read);

	if (status != HAL_OK) {
		return status;
	}

	// Check if the mode has been successfully set

	if (mode_read != mode) {
		return HAL_ERROR;
	}

	this->mode = mode;

	return HAL_OK;

}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::readMode(simplexmotion_can_mode_t &mode) {
	uint8_t rx_data[2] = { 0 };
	uint8_t responseLength = 0;

	CAN_Status status = this->read(SIMPLEXMOTION_CAN_REG_MODE, rx_data, 2,
			responseLength);

	if (status == CAN_SUCCESS) {
		mode = (simplexmotion_can_mode_t) bytearray_to_uint16(rx_data);
		return HAL_OK;
	}

	return HAL_ERROR;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::setTarget(int32_t target) {
	return this->write(SIMPLEXMOTION_CAN_REG_TARGET_INPUT, target);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::stop() {
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
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::beep(uint16_t amplitude) {

	HAL_StatusTypeDef ret;
	ret = this->setMode(SIMPLEXMOTION_CAN_MODE_BEEP);
	if (ret) {
		return ret;
	}
	// Set the amplitude

	ret = this->setTarget((int32_t) amplitude);
	if (ret) {
		return ret;
	}
	return ret;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::setTorqueLimit(float maxTorque) {

	uint16_t torque_limit_int = (uint16_t) (maxTorque * 1000);
	HAL_StatusTypeDef status;

	status = this->write(SIMPLEXMOTION_CAN_REG_TORQUE_LIMIT, torque_limit_int);

	if (status) {
		return HAL_ERROR;
	}
	uint16_t torque_limit_check = 0;

	status = this->read(SIMPLEXMOTION_CAN_REG_TORQUE_LIMIT, torque_limit_check);

	if (torque_limit_int != torque_limit_check) {
		return HAL_ERROR;
	}

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::getTemperature(float &temperature) {
	return HAL_ERROR;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::getVoltage(float &voltage) {
	uint16_t voltage_int = 0;
	HAL_StatusTypeDef status = this->read(SIMPLEXMOTION_CAN_REG_VOLTAGE,
			voltage_int);

	if (status) {
		return status;
	}

	voltage = voltage_int * 0.01;

	return HAL_OK;
}

/* --------------------------------------------------------------------- */
uint32_t SimplexMotion_CAN::_getCANHeader(uint16_t address) {

	return (0 << 24) | (this->config.id << 16) | address;

}
