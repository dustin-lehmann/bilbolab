/*
 * mab_motor.cpp
 *
 *  Created on: Mar 21, 2025
 *      Author: klvdw
 */
#include <mab_motor_fdcan.h>

HAL_StatusTypeDef MabMotor_FDCAN::init(mab_motor_config_t config) {
	// copy the config
	this->config = config;

	// TODO: check Communication, check Motor, reset Motor, set Torque Limit
	// check if motor is reachable
	if (this->checkCommunication()) {
		return HAL_ERROR;
	}
	osDelay(10);
	if (this->checkMotor()) {
		// failed to check motor
		// reset motor
		osDelay(10);
		if (this->resetMotor()) {
			return HAL_ERROR;
		}
		osDelay(10);
		// check motor again
		if (this->checkMotor()) {
			return HAL_ERROR;
		}
	}
	// set the watchdog
	if (this->setCANWatchdog(this->config.can_watchdog_timeout)) {
		return HAL_ERROR;
	}
	osDelay(10);
	// set the velocity limit
	if (this->setVelocityLimit(this->config.velocity_limit)) {
		return HAL_ERROR;
	}
	osDelay(10);
	// set the torque limit
	if (this->setTorqueLimit(this->config.torque_limit)) {
		return HAL_ERROR;
	}
	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::start(mab_motor_mode_t mode) {

	// set the mode
	this->setMode(mode);
	osDelay(10);
	// reset the targets
	this->setTargetPosition(0);
	osDelay(10);
	this->setTargetVelocity(0);
	osDelay(10);
	this->setTorque(0);
	osDelay(30);
	this->write_register(MAB_REG_STATE_MACHINE, (uint16_t) 39);
	this->mode = mode;

	//TODO: check status from mode set

	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::checkCommunication() {

	// check if motor is reachable
	// check for warnings and errors
	uint16_t comm_status = 0;
	this->read_register((uint16_t) MAB_REG_COMMUNICATION_ERRORS, comm_status);

	// check if there are comm errors or warnings
	if (comm_status) {
		// error
		// try to clear the warning, run clear cmd
		this->clearWarnings();
		// check if the error has been cleared
		this->read_register((uint16_t) 0x80E, comm_status);
		if (comm_status) {
			// error could not be cleared
			return HAL_ERROR;
		}
	}
	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::checkMotor() {

	// check if motor is reachable
	if (this->checkCommunication()) {
		return HAL_ERROR;
	}

	// check for warnings and errors
	uint16_t motor_status = 0;
	// check quick status vector, this shows only errors not warnings
	this->read_register((uint16_t) MAB_REG_QUICK_STATUS, motor_status);

	if(motor_status){
		// error
		// try to clear the non critical errors, run clear cmd
		uint16_t status = this->clearErrors();
		if (status) {
			// error could not be cleared , reset might be needed
			return HAL_ERROR;
		}
	}
	return HAL_OK;

}

HAL_StatusTypeDef MabMotor_FDCAN::clearErrors() {

	// run clear cmd, clears non critical errors
	this->write_register(MAB_REG_RUN_CLEAR_ERRORS, (uint8_t)1);
	// check if the errors have been cleared
	uint16_t motor_status = 0;
	this->read_register((uint16_t) MAB_REG_QUICK_STATUS, motor_status);
	if (motor_status) {
		// error could not be cleared , reset might be needed
		return HAL_ERROR;
	}
	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::clearWarnings() {

	// run clear cmd, clears warnings
	return this->write_register(MAB_REG_RUN_CLEAR_WARNINGS, (uint8_t)1);
}

HAL_StatusTypeDef MabMotor_FDCAN::resetMotor() {

	// run reset cmd
	this->write_register(MAB_REG_RUN_RESET, (uint8_t)1);

//	// check if the motor has been reset
//	uint16_t motor_status = 0;
//	this->read_register((uint16_t) 0x805, motor_status);
//	if (motor_status) {
//		// error could not be cleared , further action might be needed
//		return HAL_ERROR;
//	}
	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::setMode(mab_motor_mode_t motion_mode) {

	HAL_StatusTypeDef status = this->write_register(MAB_REG_MOTION_MODE,
			(uint8_t) motion_mode);

	if (status) {
		return status;
	}

	// read back the mode
	mab_motor_mode_t mode_read = MAB_MOTOR_MODE_IDLE;
	// TODO implement read Mode
	//status = readMode(mode_read);
	/*
	 if (status) {
	 return status;
	 }

	 // check if the mode has been successfully set
	 if (mode_read != motion_mode) {
	 return HAL_ERROR;
	 }
	 */
	this->mode = motion_mode;

	return HAL_OK;

}

HAL_StatusTypeDef MabMotor_FDCAN::setCANWatchdog(uint16_t timeout) {

	// write the timeout to the motor
	return this->write_register(MAB_REG_CAN_WATCHDOG, timeout);

	// reinitialize the can bus
	this->write_register(MAB_REG_RUN_CAN_REINIT, (uint8_t) 1);

	// read back the timeout
	uint16_t timeout_read = 0;
	this->read_register(MAB_REG_CAN_WATCHDOG, timeout_read);
	if (timeout_read != timeout) {
		return HAL_ERROR;
	}

	return HAL_OK;
}


HAL_StatusTypeDef MabMotor_FDCAN::setVelocityLimit(float maxVelocity) {

	// write the velocity limit to the motor
	return this->write_register(MAB_REG_MAX_VELOCITY, maxVelocity);
}

HAL_StatusTypeDef MabMotor_FDCAN::setTorqueLimit(float maxTorque) {

	// write the torque limit to the motor
	return this->write_register(MAB_REG_MAX_TORQUE, maxTorque);
}

HAL_StatusTypeDef MabMotor_FDCAN::setImpedanceConstants(
		mab_motor_impedance_constants_t constants) {


	// write the impedance constants to the motor
	if (this->write_register(MAB_REG_MOTOR_IMP_PID_KP, constants.kp)) {
		return HAL_ERROR;
	}
	if (this->write_register(MAB_REG_MOTOR_IMP_PID_KD, constants.kd)) {
		return HAL_ERROR;
	}
	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::setTorque(float torque) {

//	if (this->mode != MAB_MOTOR_MODE_RAW_TORQUE) {
//		return HAL_ERROR;
//	}

	// write the torque to the motor
	return this->write_register(MAB_REG_TARGET_TORQUE, torque);
}

HAL_StatusTypeDef MabMotor_FDCAN::setLEDBlink(bool enable) {

	// start LED blink function
	return this->write_register(MAB_REG_RUN_BLINK, (uint8_t) enable);
}

HAL_StatusTypeDef MabMotor_FDCAN::setTargetVelocity(float velocity) {

	// write the velocity to the motor
	return this->write_register(MAB_REG_TARGET_VELOCITY, velocity);
}

HAL_StatusTypeDef MabMotor_FDCAN::setTargetPosition(float position) {

	// write the position to the motor
	return this->write_register(MAB_REG_TARGET_POSITION, position);
}

HAL_StatusTypeDef MabMotor_FDCAN::readMode(mab_motor_mode_t &mode) {

	uint8_t mode_temp = 0;
	if (this->read_register(MAB_REG_MOTION_MODE, mode_temp)) {
		return HAL_ERROR;
	}
	mode = (mab_motor_mode_t) mode_temp;
	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::readSpeed(float &velocity) {

	float velocity_temp = 0;
	if (this->read_register(MAB_REG_TARGET_VELOCITY, velocity_temp)) {
		return HAL_ERROR;
	}
	velocity = velocity_temp;
	return HAL_OK;

}

HAL_StatusTypeDef MabMotor_FDCAN::readPosition(float &position) {

	float position_temp = 0;
	if (this->read_register(MAB_REG_TARGET_POSITION, position_temp)) {
		return HAL_ERROR;
	}
	position = position_temp;
	return HAL_OK;

}

HAL_StatusTypeDef MabMotor_FDCAN::getTemperature(float &temperature) {

	float temperature_temp = 0;
	if (this->read_register(MAB_REG_MOTOR_TEMPERATURE, temperature_temp)) {
		return HAL_ERROR;
	}
	temperature = temperature_temp;
	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::stop() {

	// stop the motor
	return this->write_register(MAB_REG_STATE_MACHINE, (uint16_t) 64);

}

HAL_StatusTypeDef MabMotor_FDCAN::write_register(uint16_t reg, uint8_t *data,
		uint8_t length) {

	return this->config.can->sendMessage(this->config.drive_id, data, length, 0);
}

HAL_StatusTypeDef MabMotor_FDCAN::write_register(uint16_t reg, float data) {

	uint8_t tx_length = 8;
	uint8_t tx_data[tx_length];

	// write the data to the buffer
	tx_data[0] = 0x40; //hex 40 stands for write-register-frame
	tx_data[1] = 0x00;

	uint16_to_bytearray(reg, &tx_data[2]); // set the register ID in little endian

	float_to_bytearray(data, &tx_data[4]); // set the data in little endian

	return this->write_register(reg, tx_data, tx_length);
}

HAL_StatusTypeDef MabMotor_FDCAN::write_register(uint16_t reg, uint8_t data) {

	uint8_t tx_length = 5;
	uint8_t tx_data[tx_length];

	// write the data to the buffer
	tx_data[0] = 0x40; //hex 40 stands for write-register-frame
	tx_data[1] = 0x00;

	uint16_to_bytearray(reg, &tx_data[2]); // set the register ID in little endian

	tx_data[4] = data;

	return this->write_register(reg, tx_data, tx_length);
}

HAL_StatusTypeDef MabMotor_FDCAN::write_register(uint16_t reg, uint16_t data) {

	uint8_t tx_length = 6;
	uint8_t tx_data[tx_length];

	// write the data to the buffer
	tx_data[0] = 0x40; //hex 40 stands for write-register-frame
	tx_data[1] = 0x00;

	uint16_to_bytearray(reg, &tx_data[2]); // set the register ID in little endian

	uint16_to_bytearray(data, &tx_data[4]); // set the data in little endian

	return this->write_register(reg, tx_data, tx_length);
}

HAL_StatusTypeDef MabMotor_FDCAN::write_register(uint16_t reg, uint32_t data) {

	uint8_t tx_length = 8;
	uint8_t tx_data[tx_length];

	// write the data to the buffer
	tx_data[0] = 0x40; //hex 40 stands for write-register-frame
	tx_data[1] = 0x00;

	uint16_to_bytearray(reg, &tx_data[2]); // set the register ID in little endian

	uint32_to_bytearray(data, &tx_data[4]); // set the data in little endian

	return this->write_register(reg, tx_data, tx_length);
}

HAL_StatusTypeDef MabMotor_FDCAN::write_register(uint16_t reg, int16_t data) {

	uint8_t tx_length = 6;
	uint8_t tx_data[tx_length];

	// write the data to the buffer
	tx_data[0] = 0x40; //hex 40 stands for write-register-frame
	tx_data[1] = 0x00;

	uint16_to_bytearray(reg, &tx_data[2]); // set the register ID in little endian

	int16_to_bytearray(data, &tx_data[4]); // set the data in little endian

	return this->write_register(reg, tx_data, tx_length);
}

HAL_StatusTypeDef MabMotor_FDCAN::write_register(uint16_t reg, int32_t data) {

	uint8_t tx_length = 8;
	uint8_t tx_data[tx_length];

	// write the data to the buffer
	tx_data[0] = 0x40; //hex 40 stands for write-register-frame
	tx_data[1] = 0x00;

	uint16_to_bytearray(reg, &tx_data[2]); // set the register ID in little endian

	int32_to_bytearray(data, &tx_data[4]); // set the data in little endian

	return this->write_register(reg, tx_data, tx_length);
}

HAL_StatusTypeDef MabMotor_FDCAN::read_register(uint16_t register_id, float &data) {

	// response will have 4 bytes of data
	uint8_t register_data_length = 4;
	uint8_t responseData[register_data_length];

	CAN_Status status = this->config.can->readMessage(this->config.drive_id, register_id,
			register_data_length, responseData, MAB_MOTOR_READ_TIMEOUT);

	if (status != CAN_SUCCESS) {
		return HAL_ERROR;
	}

	data = bytearray_to_float(responseData);

	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::read_register(uint16_t register_id, uint8_t &data) {

	// response will have 1 byte of data
	uint8_t register_data_length = 1;
	uint8_t responseData[register_data_length];

	CAN_Status status = this->config.can->readMessage(this->config.drive_id, register_id,
			register_data_length, responseData, MAB_MOTOR_READ_TIMEOUT);

	if (status != CAN_SUCCESS) {
		return HAL_ERROR;
	}

	data = responseData[0];

	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::read_register(uint16_t register_id, uint16_t &data) {

	// response will have 2 bytes of data
	uint8_t register_data_length = 2;
	uint8_t responseData[register_data_length];

	CAN_Status status = this->config.can->readMessage(this->config.drive_id, register_id,
			register_data_length, responseData, MAB_MOTOR_READ_TIMEOUT);

	if (status != CAN_SUCCESS) {
		return HAL_ERROR;
	}

	data = bytearray_to_uint16(responseData);

	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::read_register(uint16_t register_id, uint32_t &data) {

	// response will have 4 bytes of data
	uint8_t register_data_length = 4;
	uint8_t responseData[register_data_length];

	CAN_Status status = this->config.can->readMessage(this->config.drive_id, register_id,
			register_data_length, responseData, MAB_MOTOR_READ_TIMEOUT);

	if (status != CAN_SUCCESS) {
		return HAL_ERROR;
	}

	data = bytearray_to_uint32(responseData);

	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::read_register(uint16_t register_id, int16_t &data) {

	// response will have 2 bytes of data
	uint8_t register_data_length = 2;
	uint8_t responseData[register_data_length];

	CAN_Status status = this->config.can->readMessage(this->config.drive_id, register_id,
			register_data_length, responseData, MAB_MOTOR_READ_TIMEOUT);

	if (status != CAN_SUCCESS) {
		return HAL_ERROR;
	}

	data = bytearray_to_int16(responseData);

	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::read_register(uint16_t register_id, int32_t &data) {

	// response will have 4 bytes of data
	uint8_t register_data_length = 4;
	uint8_t responseData[register_data_length];

	CAN_Status status = this->config.can->readMessage(this->config.drive_id, register_id,
			register_data_length, responseData, MAB_MOTOR_READ_TIMEOUT);

	if (status != CAN_SUCCESS) {
		return HAL_ERROR;
	}

	data = bytearray_to_int32(responseData);

	return HAL_OK;
}

HAL_StatusTypeDef MabMotor_FDCAN::beep(uint16_t amplitude) {
}

HAL_StatusTypeDef MabMotor_FDCAN::getVoltage(float &voltage) {
}

void MabMotor_FDCAN::_error_handler() {
}
