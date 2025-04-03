/*
 * simplexmotion.cpp
 *
 *  Created on: Feb 20, 2023
 *      Author: lehmann_workstation
 */

#include "simplexmotion.hpp"

SimplexMotionMotor::SimplexMotionMotor() {

}

// ==============================================================
uint8_t SimplexMotionMotor::writeRegisters(uint16_t address,
		uint16_t num_registers, uint16_t *data) {

	int32_t u32NotificationValue;
	modbus_query_t telegram;

	telegram.u8id = this->_config.id;

	if (num_registers > 1) {
		telegram.u8fct = MB_FC_WRITE_MULTIPLE_REGISTERS;
	} else {
		telegram.u8fct = MB_FC_WRITE_REGISTER;
	}
	telegram.u16RegAdd = address; //read temp of motor = 101
	telegram.u16CoilsNo = num_registers;
	telegram.u16reg = data;

	this->_config.modbus->query(telegram);
//	u32NotificationValue = ulTaskNotifyTake(pdTRUE, portMAX_DELAY); // block until query finished
//	uint32_t ticks1 = osKernelGetTickCount();
	u32NotificationValue = ulTaskNotifyTake(pdTRUE, portMAX_DELAY); // block until query finished
//	uint32_t ticks2 = osKernelGetTickCount();

	if (u32NotificationValue != ERR_OK_QUERY) {
		if (u32NotificationValue == ERR_TIME_OUT){
			nop();
		}
		this->error_handler(SIMPLEXMOTION_ERROR_EXTERNAL_CONNECTION);
		return 0;
	} else {
		return 1;
	}
}

// ==============================================================
uint8_t SimplexMotionMotor::readRegisters(uint16_t address,
		uint16_t num_registers, uint16_t *data) {
	int32_t u32NotificationValue;
	modbus_query_t telegram;

	telegram.u8id = this->_config.id;
	telegram.u8fct = MB_FC_READ_REGISTERS;
	telegram.u16RegAdd = address; //read temp of motor = 101
	telegram.u16CoilsNo = num_registers;
	telegram.u16reg = data;

	this->_config.modbus->query(telegram);
	u32NotificationValue = ulTaskNotifyTake(pdTRUE, portMAX_DELAY); // block until query finished
	if (u32NotificationValue != ERR_OK_QUERY) {
		if (u32NotificationValue == ERR_TIME_OUT){
			nop();
		}
		this->error_handler(SIMPLEXMOTION_ERROR_EXTERNAL_CONNECTION);
		return 0;
	} else {
		return 1;
	}
}

// ==============================================================
uint8_t SimplexMotionMotor::init(simplexmotion_config_t config) {

	this->_config = config;

	this->_checked = 0;
	this->_init = 0;

	uint8_t ret = 0;

	// Reset the motor
	ret = this->setMode(SIMPLEXMOTION_MODE_RESET);

	// Read the motor status
	simplexmotion_status_t status;
	ret = this->getStatus(&status);

	if (not (ret)) {
		return 0;
	}

	// TODO

	// Read the torque limit
//	float torque_limit = this->getTorqueLimit();

	// Read the ...

	this->_init = 1;
	this->_checked = 0;
	return 1;
}

// ==============================================================
void SimplexMotionMotor::start(simplexmotion_mode_t mode) {
	uint8_t ret = 0;
	if (!this->_init) {
		while (1) {

		}
	}
	if (!this->_checked) {
//		while (1) {
//
//		}
	}

	// Set the target to 0
	ret = this->setTarget(0);
	if (not (ret)) {
		this->error_handler(SIMPLEXMOTION_ERROR_EXTERNAL_CONNECTION);
	}

	// Set the corresponding mode
	ret = this->setMode(mode);
	if (not (ret)) {
		this->error_handler(SIMPLEXMOTION_ERROR_EXTERNAL_CONNECTION);
	}
}

// ==============================================================

uint8_t SimplexMotionMotor::startup_check() {
	uint8_t ret = 0;

	// Beep the motor once
	ret = this->beep(200);
	if (not (ret)) {
		return 0;
	}

	osDelay(250);

	ret = this->stop();
	if (not (ret)) {
		return 0;
	}
	// Set the motor into torque mode
	ret = this->setMode(SIMPLEXMOTION_MODE_TORQUE);

	if (not (ret)) {
		return 0;
	}

	// Read the current position of the motor
	int32_t position_before = this->getPositionRaw();

	// Apply a small torque for a short amount of time
	this->setTorque(0.03);
	osDelay(250);
	this->setTorque(0.0);
	osDelay(250);
	// Turn the motor off
//	this->stop();

	// Read the current position of the motor
	int32_t position_after = this->getPositionRaw();

	// Check if the position has changed
	if (position_before == position_after) {
		return 0;
	}

	this->beep(200);
	osDelay(150);
	this->stop();
	osDelay(150);
	this->beep(200);
	osDelay(300);
	this->stop();

	this->_checked = 1;
	return 1;
}

uint8_t SimplexMotionMotor::check() {

	return 1;
}
// ==============================================================
uint8_t SimplexMotionMotor::setMode(simplexmotion_mode_t mode) {
	uint16_t data = (uint16_t) mode;

	// Set the mode
	uint8_t write_success = this->writeRegisters(SIMPLEXMOTION_REG_MODE, 1,
			&data);
	if (not write_success) {
		return 0;
	}

	// Read back the mode
	uint16_t rx_data = 0;
	uint8_t read_success = this->readRegisters(SIMPLEXMOTION_REG_MODE, 1,
			&rx_data);

	if (not read_success) {
		return 0;
	}

	this->mode = rx_data;

	if (rx_data != mode) {
		return 0;
	}
	return 1;
}

// ==============================================================
uint8_t SimplexMotionMotor::stop() {
	uint16_t data = SIMPLEXMOTION_MODE_OFF;
	this->setTarget(0);
	return this->writeRegisters(SIMPLEXMOTION_REG_MODE, 1, &data);
}

// ==============================================================
uint8_t SimplexMotionMotor::beep(uint16_t amplitude) {
	uint8_t ret = 0;
	ret = this->setMode(SIMPLEXMOTION_MODE_BEEP);

	// Set the amplitude
	ret = this->setTarget((int32_t) amplitude);

	return ret;
}
// ==============================================================
uint8_t SimplexMotionMotor::reset() {

	return 0;
}

// ==============================================================
float SimplexMotionMotor::getPosition() {
	int32_t position = 0;
	uint16_t data[2] = { 0 };

	uint8_t success = this->readRegisters(SIMPLEXMOTION_REG_POSITION, 2, data);

	if (!success) {
		return 0;
	}
	position = data[0] << 16 | data[1];
	return position / 4096.0 * this->_config.direction;
}

// ==============================================================
int32_t SimplexMotionMotor::getPositionRaw() {
	int32_t position = 0;
	uint16_t data[2] = { 0 };

	uint8_t success = this->readRegisters(SIMPLEXMOTION_REG_POSITION, 2, data);

	if (!success) {
		return 0;
	}
	position = data[0] << 16 | data[1];

	return position;
}

// ==============================================================
float SimplexMotionMotor::getVoltage(){
	float voltage = 0;
	uint16_t voltage_int = 0;
	uint8_t success = this->readRegisters(SIMPLEXMOTION_REG_VOLTAGE, 1, &voltage_int);

	if (!success) {
		return 0;
	}
	voltage = voltage_int * 0.01;

	return voltage;
}


// ==============================================================
float SimplexMotionMotor::getSpeed() {
	uint16_t speed_raw = 0;
	uint8_t success = this->readRegisters(SIMPLEXMOTION_REG_SPEED, 1,
			&speed_raw);

	int16_t speed_signed = (int16_t) speed_raw;

	if (!success) {
		return 0;
	}
	float speed = this->_config.direction * 2 * pi * speed_signed / 256;

	return speed;
}

// ==============================================================
uint8_t SimplexMotionMotor::setTorqueLimit(float maxTorque) {
	uint16_t torque_limit_int = (uint16_t) (maxTorque * 1000);

	uint8_t ret = 0;

	ret = this->writeRegisters(SIMPLEXMOTION_REG_TORQUE_LIMIT, 1,
			&torque_limit_int);

	if (not (ret)) {
		return 0;
	}

	uint16_t torque_limit_int_check = 0;
	ret = this->readRegisters(SIMPLEXMOTION_REG_TORQUE_LIMIT, 1,
			&torque_limit_int_check);

	if (not (ret)) {
		return 0;
	}

	this->torque_limit = torque_limit_int_check * 0.001;

	if (!(torque_limit_int == torque_limit_int_check)) {
		return 0;
	}

	return 1;
}

// ==============================================================
float SimplexMotionMotor::getTorqueLimit() {

	uint16_t torque_limit_int = 0;
	uint8_t ret = this->readRegisters(SIMPLEXMOTION_REG_TORQUE_LIMIT, 1,
			&torque_limit_int);

	if (not ret) {
		return -1;
	}

	float torque_limit = torque_limit_int * 0.001;

	this->torque_limit = torque_limit;
	return torque_limit;
}

// ==============================================================
float SimplexMotionMotor::getTorque() {

	return 0.0;
}

// ==============================================================
uint8_t SimplexMotionMotor::setTorque(float torque) {
	// First check if torque mode has been set
	if (!(this->mode == SIMPLEXMOTION_MODE_TORQUE)) {
		return 0;
	}

	// Calculate the corresponding torque value
	int16_t torque_value_int = (int16_t) (this->_config.direction * torque
			/ this->torque_limit * 32767.0);
	int32_t target_input = (int32_t) torque_value_int;

	uint8_t ret = this->setTarget(target_input);
	return ret;
}

// ==============================================================
uint8_t SimplexMotionMotor::setTarget(int32_t target) {
	uint8_t ret = 0;
	uint16_t tx_data[2] = { 0 };

	tx_data[0] = target >> 16;
	tx_data[1] = target & 0xFFFF;

	ret = this->writeRegisters(SIMPLEXMOTION_REG_TARGET_INPUT, 2, tx_data);
	return ret;
}

// ==============================================================
uint8_t SimplexMotionMotor::getStatus(simplexmotion_status_t *status) {
	uint16_t status_map = 0;
	uint8_t ret = this->readRegisters(SIMPLEXMOTION_REG_STATUS, 1, &status_map);

	if (not (ret)) {
		return 0;
	}

	status->fail = status_map & 1 << 0;
	status->communication_error = status_map & 1 << 1;
	status->current_error = status_map & 1 << 2;
	status->voltage_error = status_map & 1 << 3;
	status->temperature_error = status_map & 1 << 4;
	status->torque_limit = status_map & 1 << 5;
	status->locked = status_map & 1 << 6;
	status->regulator_error = status_map & 1 << 7;
	status->moving = status_map & 1 << 8;
	status->reverse = status_map & 1 << 9;
	status->target = status_map & 1 << 10;

	return 1;
}

// ==============================================================
void SimplexMotionMotor::registerCallback(simplexmotion_callback_id callback_id,
		core_utils_Callback<void, void> callback) {
	if (callback_id == SIMPLEXMOTION_CB_ERROR) {
		this->callbacks.error = callback;
	}
}

// ==============================================================
void SimplexMotionMotor::error_handler(simplexmotion_error error) {
	nop();
}

// ==============================================================
