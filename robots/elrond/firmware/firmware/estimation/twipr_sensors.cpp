/*
 * twipr_sensors.cpp
 *
 *  Created on: 3 Mar 2023
 *      Author: Dustin Lehmann
 */

#include "twipr_sensors.h"

TWIPR_Sensors::TWIPR_Sensors() {

}

/* ======================================================= */
uint8_t TWIPR_Sensors::init(twipr_sensors_config_t config) {

	// Initialize the IMU
	bmi160_gyr_config_t gyr_config;
	bmi160_acc_config_t acc_config;
	bmi160_config_t imu_config = { .hspi = BOARD_SPI_INTERN, .CS_GPIOx =
	BOARD_CS_IMU_PORT, .CS_GPIO_Pin =
	BOARD_CS_IMU_PIN, .gyr = gyr_config, .acc = acc_config };

	uint8_t success = imu.init(imu_config);

	if (!success) {
		setError(BILBO_ERROR_MAJOR, BILBO_ERROR_IMU_INITIALIZE);
		this->status = TWIPR_SENSORS_STATUS_ERROR;
		return 0;
	}

	this->_config = config;

	this->status = TWIPR_SENSORS_STATUS_IDLE;
	return 1;
}
/* ======================================================= */
void TWIPR_Sensors::start() {
	this->status = TWIPR_SENSORS_STATUS_RUNNING;
}
/* ======================================================= */
uint8_t TWIPR_Sensors::check() {

	// Check the IMU
	uint8_t success = imu.check();

	// Check the motors
	// TODO

	return success;

}
/* ======================================================= */
void TWIPR_Sensors::update() {
	this->_readImu();
	this->_readMotorSpeed();
	this->_readBatteryVoltage();
}
/* ======================================================= */
twipr_sensors_data_t TWIPR_Sensors::getData() {
	return this->_data;
}
/* ======================================================= */
twipr_sensors_status_t TWIPR_Sensors::getStatus() {
	return this->status;
}
/* ======================================================= */
uint8_t TWIPR_Sensors::calibrate() {
	//TODO
	this->imu.fastOffsetCalibration();
	return 0;
}

/* ======================================================= */
void TWIPR_Sensors::_readImu() {
	this->imu.update();
	memcpy(&this->_data.acc, &this->imu.acc, sizeof(this->_data.acc));
	memcpy(&this->_data.gyr, &this->imu.gyr, sizeof(this->_data.gyr));
}

/* ======================================================= */
void TWIPR_Sensors::_readMotorSpeed() {
	// TODO: I probably need some check here if this has been initialized or so

	bilbo_drive_speed_t motor_speed = this->_config.drive->getSpeed();

	this->_data.speed_left = motor_speed.left;
	this->_data.speed_right = motor_speed.right;

	nop();
}

/* ======================================================= */
void TWIPR_Sensors::_readBatteryVoltage() {
	float voltage = this->_config.drive->getVoltage();
	this->_data.battery_voltage = voltage;
}


