/*
 * twipr_estimation.cpp
 *
 *  Created on: 22 Feb 2023
 *      Author: Dustin Lehmann
 */

#include "twipr_estimation.h"
#include "twipr_errors.h"


static const osThreadAttr_t estimation_task_attributes = { .name = "estimation",
		.stack_size = 1280 * 4, .priority = (osPriority_t) osPriorityNormal, };

/* ======================================================= */
TWIPR_Estimation::TWIPR_Estimation() :
		vqf(TWIPR_ESTIMATION_TS) {
	this->status = TWIPR_ESTIMATION_STATUS_NONE;
	this->vqf.setTauAcc(0.5);
}

/* ======================================================= */
void TWIPR_Estimation::init(twipr_estimation_config_t config) {
	this->config = config;

	// Initialize the sensors

	this->status = TWIPR_ESTIMATION_STATUS_IDLE;
	this->_semaphore = osSemaphoreNew(1, 1, NULL);
}

/* ======================================================= */
void TWIPR_Estimation::start() {
	osThreadNew(estimation_task, (void*) this, &estimation_task_attributes);
}
/* ======================================================= */
void TWIPR_Estimation::reset() {

}
/* ======================================================= */
void TWIPR_Estimation::task_function() {

//	this->_orientation_fusion.begin((float) TWIPR_ESTIMATION_FREQUENCY);
	this->status = TWIPR_ESTIMATION_STATUS_OK;
//	this->_sensors.calibrate();
	uint32_t ticks;

	while (true) {
		ticks = osKernelGetTickCount();
		this->update();
		osDelayUntil(ticks + (uint32_t) (1000.0 / TWIPR_ESTIMATION_FREQUENCY));
	}
}
/* ======================================================= */
void TWIPR_Estimation::stop() {

}
/* ======================================================= */
void TWIPR_Estimation::update() {

	// Update the Sensors
	this->config.sensors->update();

	// Read the sensor data
	twipr_sensors_data_t data = this->config.sensors->getData();

	// Orientation Estimation
//	this->_orientation_fusion.updateIMU(data.gyr.x, data.gyr.y, data.gyr.z,
//			data.acc.x, data.acc.y, data.acc.z);

	vqf_real_t gyr[3] = { data.gyr.x, data.gyr.y, data.gyr.z };
	vqf_real_t acc[3] = { data.acc.x, data.acc.y, data.acc.z };
	vqf.update(gyr, acc);

	vqf_real_t quat[4];

	vqf.getQuat6D(quat);
	float w = quat[0];
	float x = quat[1];
	float y = quat[2];
	float z = quat[3];

	float theta = atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y));

//	float theta = this->_orientation_fusion.getRollRadians();
	float theta_dot = data.gyr.x;

//	float theta =

	// Correct the speed by the pitch angle velocity
	data.speed_left += theta_dot;
	data.speed_right += theta_dot;
	// Get the speed and yaw speed
	float v = ((data.speed_left + data.speed_right) / 2 )
			* WHEEL_DIAMETER/2;

	float psi_dot = (data.speed_right - data.speed_left)
			* (WHEEL_DIAMETER/2) / WHEEL_DISTANCE;

	// Set the current state
	osSemaphoreAcquire(_semaphore, portMAX_DELAY);
	this->state.v = v;
	this->state.theta = theta + this->_theta_offset;
	this->state.theta_dot = theta_dot;
	this->state.psi = 0;
	this->state.psi_dot = psi_dot;

	// Calculate the average
	this->mean_state.v = this->mean_state.v
			- (this->_state_buffer[this->_state_buffer_index].v
					/ (float) TWIPR_ESTIMATION_STATE_BUFFER_SIZE)
			+ (this->state.v / (float) TWIPR_ESTIMATION_STATE_BUFFER_SIZE);
	this->mean_state.theta = this->mean_state.theta
			- (this->_state_buffer[this->_state_buffer_index].theta
					/ (float) TWIPR_ESTIMATION_STATE_BUFFER_SIZE)
			+ (this->state.theta / (float) TWIPR_ESTIMATION_STATE_BUFFER_SIZE);
	this->mean_state.theta_dot = this->mean_state.theta_dot
			- (this->_state_buffer[this->_state_buffer_index].theta_dot
					/ (float) TWIPR_ESTIMATION_STATE_BUFFER_SIZE)
			+ (this->state.theta_dot
					/ (float) TWIPR_ESTIMATION_STATE_BUFFER_SIZE);
	this->mean_state.psi = this->mean_state.psi
			- (this->_state_buffer[this->_state_buffer_index].psi
					/ (float) TWIPR_ESTIMATION_STATE_BUFFER_SIZE)
			+ (this->state.psi / (float) TWIPR_ESTIMATION_STATE_BUFFER_SIZE);
	this->mean_state.psi_dot =
			this->mean_state.psi_dot
					- (this->_state_buffer[this->_state_buffer_index].psi_dot
							/ (float) TWIPR_ESTIMATION_STATE_BUFFER_SIZE)
					+ (this->state.psi_dot
							/ (float) TWIPR_ESTIMATION_STATE_BUFFER_SIZE);

	this->_state_buffer[this->_state_buffer_index] = this->state;
	osSemaphoreRelease(_semaphore);

	this->_state_buffer_index++;
	if (this->_state_buffer_index == TWIPR_ESTIMATION_STATE_BUFFER_SIZE) {
		this->_state_buffer_index = 0;
	}

}

/* ======================================================= */
bool TWIPR_Estimation::setThetaOffset(float offset){
	this->_theta_offset = offset;
	return true;
}
/* ======================================================= */
twipr_estimation_state_t TWIPR_Estimation::getMeanState() {
	twipr_estimation_state_t out;
	osSemaphoreAcquire(_semaphore, portMAX_DELAY);
	out = this->mean_state;
	osSemaphoreRelease(_semaphore);
	return out;
}
/* ======================================================= */
twipr_estimation_state_t TWIPR_Estimation::getState() {
	osSemaphoreAcquire(_semaphore, portMAX_DELAY);
	twipr_estimation_state_t out = this->state;
	osSemaphoreRelease(_semaphore);
	return out;
}
/* ======================================================= */
void TWIPR_Estimation::setState(twipr_estimation_state_t state) {

//	twipr_error_handler(0);
}
/* ======================================================= */
twipr_logging_estimation_t TWIPR_Estimation::getSample() {
	twipr_logging_estimation_t sample;
	sample.state = this->getState();
	return sample;
}
/* ======================================================= */
void estimation_task(void *estimation) {
	TWIPR_Estimation *estimator = (TWIPR_Estimation*) estimation;
	estimator->task_function();
}
