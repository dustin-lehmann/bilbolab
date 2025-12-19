/*
 * twipr_control.cpp
 *
 *  Created on: 3 Mar 2023
 *      Author: lehmann_workstation
 */

#include "twipr_control.h"
#include "twipr_communication.h"


TWIPR_ControlManager *manager;

osSemaphoreId_t semaphore_external_input;


/* ======================================================== */
void TWIPR_ControlManager::init(twipr_control_init_config_t config) {
	manager = this;
	this->config = config;
	this->_estimation = config.estimation;

	// Initialize the balancing controller
	twipr_balancing_control_config_t balancing_control_config;
	this->_balancing_control.init(balancing_control_config);

	twipr_speed_control_forward_config_t speed_control_forward_config = { .Kp =
			0, .Ki = 0, .Kd = 0, .Ts = TWIPR_CONTROL_TS_MS / 1000.0 };

	twipr_speed_control_turn_config_t speed_control_turn_config = { .Kp = 0,
			.Ki = 0, .Kd = 0, .Ts = TWIPR_CONTROL_TS_MS / 1000.0 };

	twipr_speed_control_config_t speed_control_config = { .forward_config =
			speed_control_forward_config, .turn_config =
			speed_control_turn_config };

	this->_speed_control.init(speed_control_config);

    twipr_position_control_config_t position_control_config; // ggf. Parameter setzen
    this->_position_control.init(position_control_config);

	this->status = TWIPR_CONTROL_STATUS_IDLE;
	this->mode = TWIPR_CONTROL_MODE_OFF;

	this->_resetExternalInput();
	this->_resetOutput();
	this->_tick = 0;

}
/* ======================================================== */
uint8_t TWIPR_ControlManager::start() {
	this->status = TWIPR_CONTROL_STATUS_RUNNING;
	this->_balancing_control.start();
	this->_position_control.start();

	return 1;
}

/* ======================================================== */

/* ======================================================== */
void TWIPR_ControlManager::stop() {

	this->setMode(TWIPR_CONTROL_MODE_OFF);

}
/* ======================================================== */
void TWIPR_ControlManager::reset() {
	this->_balancing_control.reset();
	this->_speed_control.reset();
	this->_error_velocity_integral = 0;
	this->_tic_integral = 0;
	this->enableTIC(false);
	this->_resetExternalInput();
}

/* ======================================================== */
bool TWIPR_ControlManager::enableVIC(bool state){
	this->control_config.vic_enabled = state;
	this->_error_velocity_integral = 0;

	control_event_message_data_t event_message_data = { .event =
			CONTROL_CONFIG_CHANGED, .mode = mode, .config =
			this->control_config, .tick = tick_global };

	BILBO_Message_Control_Event message(event_message_data);
	sendMessage(message);

	control_event_message_data_t event_message_data_vic = { .event =
			VIC_CHANGED, .mode = mode, .config =
			this->control_config, .tick = tick_global };

	return true;
}

/* ======================================================== */
bool TWIPR_ControlManager::enableTIC(bool state) {

	this->_tic_integral = 0;

	bool current_state = this->control_config.tic_enabled;
	this->control_config.tic_enabled = state;

	if (current_state == state) {
		return true;
	}

//	if (state == false){
//		send_debug("TIC disabled");
//	} else {
//		send_debug("TIC enabled");
//	}

	control_event_message_data_t event_message_data = { .event =
			CONTROL_CONFIG_CHANGED, .mode = mode, .config =
			this->control_config, .tick = tick_global };

	BILBO_Message_Control_Event message(event_message_data);
	sendMessage(message);

	control_event_message_data_t event_message_data_tic = { .event =
			TIC_CHANGED, .mode = mode, .config =
			this->control_config, .tick = tick_global };
	BILBO_Message_Control_Event message_tic(event_message_data_tic);
	sendMessage(message_tic);

	return true;
}

/* ======================================================== */
void TWIPR_ControlManager::update() {

	// Read the dynamic state from the estimator
	this->_dynamic_state = this->_estimation->getState();

	// Check for errors
	// TODO

	// Initialize the drive input
	twipr_control_output_t control_output = { 0, 0 };

	switch (this->status) {
	case (TWIPR_CONTROL_STATUS_ERROR): {
		//
		this->_step_error();
		break;
	}
	case (TWIPR_CONTROL_STATUS_IDLE): {
		//
		this->_step_idle();
		break;
	}
	case (TWIPR_CONTROL_STATUS_RUNNING): {

		switch (this->mode) {
		case (TWIPR_CONTROL_MODE_OFF): {
			control_output = this->_step_off();
			break;
		}
		case (TWIPR_CONTROL_MODE_DIRECT): {
			control_output = this->_step_direct(this->_external_input);
			break;
		}
		case (TWIPR_CONTROL_MODE_BALANCING): {
			control_output = this->_step_balancing(_external_input,
					_dynamic_state);
			break;
		}
		case (TWIPR_CONTROL_MODE_VELOCITY): {
			control_output = this->_step_velocity(_external_input,
					_dynamic_state);
			break;
		}
		case (TWIPR_CONTROL_MODE_POSITION): {
			control_output = this->_step_position(_external_input,
					_dynamic_state);
			break;
		}

			break;
		}

	}
	}

	this->_data.input_left = control_output.u_left;
	this->_data.input_right = control_output.u_right;
	// Limit the Output
	control_output.u_left = limit(control_output.u_left,
			this->config.max_torque);
	control_output.u_right = limit(control_output.u_right,
			this->config.max_torque);

//	control_output.u_left = 0;
//	control_output.u_right = 0;
	// Write the output to the data
	this->_data.output_left = control_output.u_left;
	this->_data.output_right = control_output.u_right;


//	 Write the output to the motors
//	send_info("Control output: %f %f", control_output.u_left, control_output.u_right);

	this->_setTorque(control_output);

	// Increase the tick
	this->_tick++;

	// Call the step callbacks
	this->callbacks.step.call(this->_tick);

}

/* ======================================================== */
uint8_t TWIPR_ControlManager::setMode(twipr_control_mode_t mode) {

	// Setting mode should only work while running
	if (this->status == TWIPR_CONTROL_STATUS_IDLE) {
		return 0;
	}
	if (this->status == TWIPR_CONTROL_STATUS_ERROR) {
		return 0;
	}

	// Switch the mode of the balancing controller to the appropriate mode
	switch (mode) {
	case TWIPR_CONTROL_MODE_OFF: {
		this->_balancing_control.stop();
		break;
	}
	case TWIPR_CONTROL_MODE_DIRECT: {
//		if (this->config.drive->status != TWIPR_DRIVE_STATUS_RUNNING) {
//			this->config.drive->start();
//		}

		this->_balancing_control.setMode(TWIPR_BALANCING_CONTROL_MODE_DIRECT);
		break;
	}
	case TWIPR_CONTROL_MODE_BALANCING: {
//		if (this->config.drive->status != TWIPR_DRIVE_STATUS_RUNNING) {
//			this->config.drive->start();
//		}
		send_info("Set mode to balancing. Tick: %d", tick_global);
		this->_balancing_control.setMode(TWIPR_BALANCING_CONTROL_MODE_ON);
		break;
	}
	case TWIPR_CONTROL_MODE_VELOCITY: {
//		if (this->config.drive->status != TWIPR_DRIVE_STATUS_RUNNING) {
//			this->config.drive->start();
//		}
		this->_balancing_control.setMode(TWIPR_BALANCING_CONTROL_MODE_ON);
		this->_speed_control.reset();
		break;
	}
	case TWIPR_CONTROL_MODE_POSITION: {
		//		if (this->config.drive->status != TWIPR_DRIVE_STATUS_RUNNING)
		//			this->config.drive->start();
		this->_position_control.setMode(TWIPR_position_CONTROL_MODE_ON);
		send_debug("POSITION-Modus");
		break;
	}
	}


	this->reset();

	bool mode_changed = false;

	if (this->mode != mode) {
		mode_changed = true;
	}
	this->mode = mode;

	if (mode_changed) {
		this->callbacks.mode_change.call(mode);

		control_event_message_data_t event_message_data = { .event =
				CONTROL_MODE_CHANGED, .mode = mode, .config =
				this->control_config, .tick = tick_global };

		BILBO_Message_Control_Event message(event_message_data);

		sendMessage(message);

	}

	return 1;
}
/* ======================================================== */
void TWIPR_ControlManager::setExternalInput(
		twipr_control_external_input_t input) {

	if (this->_externalInputEnabled == false) {
		return;
	}

	if (this->status != TWIPR_CONTROL_STATUS_RUNNING) {
		return;
	}

	osSemaphoreAcquire(semaphore_external_input, portMAX_DELAY);
	this->_external_input = input;
	osSemaphoreRelease(semaphore_external_input);
}
/* ======================================================== */
bool TWIPR_ControlManager::setBalancingInput(
		twipr_balancing_control_input_t input) {

	if (this->_externalInputEnabled == false) {
		return false;
	}

	this->_setBalancingInput(input);
	return true;
}
void TWIPR_ControlManager::setPosition(twipr_position_control_input_t position) {

	if (this->_externalInputEnabled == false) {
		return;
	}
	send_debug("waypointsachen erhalten");
	osSemaphoreAcquire(semaphore_external_input, portMAX_DELAY);
	this->_external_input.u_position_forward = position.u_1;
	this->_external_input.u_position_turnangle = position.u_2;
	osSemaphoreRelease(semaphore_external_input);
}


/* ======================================================== */
void TWIPR_ControlManager::_setBalancingInput(twipr_balancing_control_input_t input) {
	osSemaphoreAcquire(semaphore_external_input, portMAX_DELAY);
	this->_external_input.u_balancing_1 = input.u_1;
	this->_external_input.u_balancing_2 = input.u_2;
	osSemaphoreRelease(semaphore_external_input);
}

/* ======================================================== */
void TWIPR_ControlManager::setSpeed(twipr_speed_control_input_t speed) {

	if (this->_externalInputEnabled == false) {
		return;
	}

	osSemaphoreAcquire(semaphore_external_input, portMAX_DELAY);
	this->_external_input.u_velocity_forward = speed.forward;
	this->_external_input.u_velocity_turn = speed.turn;
	osSemaphoreRelease(semaphore_external_input);
}

/* ======================================================== */
void TWIPR_ControlManager::setDirectInput(twipr_control_direct_input_t input) {

	if (this->_externalInputEnabled == false) {
		return;
	}

	osSemaphoreAcquire(semaphore_external_input, portMAX_DELAY);
	this->_external_input.u_direct_1 = input.input_left;
	this->_external_input.u_direct_2 = input.input_right;
	osSemaphoreRelease(semaphore_external_input);
}

/* ======================================================== */
void TWIPR_ControlManager::disableExternalInput() {
	this->_externalInputEnabled = false;

}

/* ======================================================== */
void TWIPR_ControlManager::enableExternalInput() {
	this->_externalInputEnabled = true;
}

/* ======================================================== */

twipr_control_status_t TWIPR_ControlManager::getStatus() {
	return this->status;
}

/* ======================================================== */
uint8_t TWIPR_ControlManager::setBalancingGain(float *K) {
	// This is only allowed if the controller is off
	if (this->status != TWIPR_CONTROL_STATUS_RUNNING) {
		return 0;
//		return;
	}
	if (this->mode != TWIPR_CONTROL_MODE_OFF) {
		return 0;
//		return;
	}

	this->_balancing_control.set_K(K);

	memcpy(this->control_config.K, K, sizeof(float) * 8);

	return 1;
}

uint8_t TWIPR_ControlManager::setPositionGain(float *K) {
	// This is only allowed if the controller is off
	if (this->status != TWIPR_CONTROL_STATUS_RUNNING) {
		return 0;
//		return;
	}
	if (this->mode != TWIPR_CONTROL_MODE_OFF) {
		return 0;
//		return;
	}

    this->_position_control.set_K_Pos(K); //

	//memcpy(this->control_config.K, K, sizeof(float) * 8);

	return 1;
}

/* ======================================================== */
uint8_t TWIPR_ControlManager::setPositionConfig(float *K) {
	// This is only allowed if the controller is off
	if (this->status != TWIPR_CONTROL_STATUS_RUNNING) {
		return 0;
//		return;
	}
	if (this->mode != TWIPR_CONTROL_MODE_OFF) {
		return 0;
//		return;
	}
	if (K[0] == 1){
		send_debug("reset inputs for position control");
		this->_external_input.u_position_forward = 0;
		this->_external_input.u_position_turnangle = 0;
	}
    this->_position_control.set_Pos_Config(K); //

	//memcpy(this->control_config.K, K, sizeof(float) * 8);

	return 1;
}
/* ======================================================== */
uint8_t TWIPR_ControlManager::setVelocityControlForwardPID(float *PID) {
	this->_speed_control.setForwardPID(PID[0], PID[1], PID[2]);
	this->control_config.forward_kp = PID[0];
	this->control_config.forward_ki = PID[1];
	this->control_config.forward_kd = PID[2];
	return 1;
}

/* ======================================================== */
uint8_t TWIPR_ControlManager::setVelocityControlForwardPID(float Kp, float Ki, float Kd) {
	this->_speed_control.setForwardPID(Kp, Ki, Kd);
	this->control_config.forward_kp = Kp;
	this->control_config.forward_ki = Ki;
	this->control_config.forward_kd = Kd;
	return 1;
}

/* ======================================================== */
uint8_t TWIPR_ControlManager::setVelocityControlTurnPID(float *PID) {
	this->_speed_control.setTurnPID(PID[0], PID[1], PID[2]);

	this->control_config.turn_kp = PID[0];
	this->control_config.turn_ki = PID[1];
	this->control_config.turn_kd = PID[2];

	return 1;
}

/* ======================================================== */
uint8_t TWIPR_ControlManager::setVelocityControlTurnPID(float Kp, float Ki, float Kd) {
	this->_speed_control.setTurnPID(Kp, Ki, Kd);
	this->control_config.turn_kp = Kp;
	this->control_config.turn_ki = Ki;
	this->control_config.turn_kd = Kd;
	return 1;
}

/* ======================================================== */
bool TWIPR_ControlManager::setControlConfiguration(twipr_control_configuration_t config){
	this->control_config = config;
	this->setBalancingGain(config.K);
	this->setVelocityControlForwardPID(config.forward_kp, config.forward_ki, config.forward_kd);
	this->setVelocityControlTurnPID(config.turn_kp, config.turn_ki, config.turn_kd);
	this->reset();
	return true;
}

/* ======================================================== */
twipr_control_configuration_t TWIPR_ControlManager::getControlConfiguration() {
	twipr_control_configuration_t config;

	config = this->control_config;

	memcpy(config.K, this->_balancing_control.config.K, sizeof(float) * 8);
	config.forward_kp = this->_speed_control.config.forward_config.Kp;
	config.forward_ki = this->_speed_control.config.forward_config.Ki;
	config.forward_kd = this->_speed_control.config.forward_config.Kd;

	config.turn_kp = this->_speed_control.config.turn_config.Kp;
	config.turn_ki = this->_speed_control.config.turn_config.Ki;
	config.turn_kd = this->_speed_control.config.turn_config.Kd;

	return config;
}
/* ======================================================== */
twipr_control_output_t TWIPR_ControlManager::_step_off() {
	this->_resetExternalInput();
	this->_resetOutput();
	twipr_control_output_t output = { 0, 0 };
	return output;
}
/* ======================================================== */
twipr_control_output_t TWIPR_ControlManager::_step_direct(
		twipr_control_external_input_t input) {
	//
	this->_resetOutput();
	// TODO

	twipr_control_output_t output = { 0, 0 };
	return output;

}
/* ======================================================== */
twipr_control_output_t TWIPR_ControlManager::_step_idle() {
	this->_resetExternalInput();
	this->_resetOutput();
	twipr_control_output_t output = { 0, 0 };
	return output;
}
/* ======================================================== */
twipr_control_output_t TWIPR_ControlManager::_step_error() {
	this->_resetExternalInput();
	this->_resetOutput();
	twipr_control_output_t output = { 0, 0 };
	return output;
}
/* ======================================================== */
twipr_control_output_t TWIPR_ControlManager::_step_balancing(
		twipr_control_external_input_t input, twipr_estimation_state_t state) {

	twipr_control_output_t output = { 0, 0 };

	twipr_balancing_control_input_t balancing_control_input = {
			input.u_balancing_1, input.u_balancing_2, };

	this->_data.input_balancing_1 = balancing_control_input.u_1;
	this->_data.input_balancing_2 = balancing_control_input.u_2;

	twipr_balancing_control_output_t balancing_control_output =
			this->_update_balancing_control(balancing_control_input, state);


	float output_velocity_integral_control = this->_updateVelocityIntegralController(state.v);
	float output_tic = this->_updateTIC(state.theta);

	output.u_left = balancing_control_output.u_1 + output_velocity_integral_control + output_tic;
	output.u_right = balancing_control_output.u_2 + output_velocity_integral_control + output_tic;

	return output;

}
twipr_control_output_t TWIPR_ControlManager::_step_position(
		twipr_control_external_input_t input, twipr_estimation_state_t state) {

	twipr_control_output_t output = { 0, 0 };

	twipr_position_control_input_t position_control_input = {
			input.u_position_forward, input.u_position_turnangle, };

	this->_data.input_balancing_1 = position_control_input.u_1;
	this->_data.input_balancing_2 = position_control_input.u_2;

	twipr_position_control_output_t position_control_output =
			this->_update_position_control(position_control_input, state);


//	float output_velocity_integral_control = this->_updateVelocityIntegralController(state.v);
//	float output_tic = this->_updateTIC(state.theta);

	output.u_left = position_control_output.u_1;// + output_velocity_integral_control + output_tic;
	output.u_right = position_control_output.u_2;// + output_velocity_integral_control + output_tic;
	//send_info("Control output: %f %f", output.u_left, output.u_right);
	return output;

}

/* ======================================================== */
float TWIPR_ControlManager::_updateVelocityIntegralController(float velocity){

	if (this->control_config.vic_enabled == false){
		return 0;
	}

	if (this->control_config.vic_v_limit != 0){
		if (std::fabs(velocity) > this->control_config.vic_v_limit){
			this->_error_velocity_integral = 0;
			return 0;
		}
	}

	// Integrate the error
	this->_error_velocity_integral += 1/this->config.freq * velocity;


	// Max the integral
	if (this->_error_velocity_integral > this->control_config.vic_max_error){
		this->_error_velocity_integral = this->control_config.vic_max_error;
	}
	else if (this->_error_velocity_integral < - this->control_config.vic_max_error){
		this->_error_velocity_integral = -this->control_config.vic_max_error;
	}

	// Calculate the return value
	float output = this->_error_velocity_integral * this->control_config.vic_ki;

	return output;
}

/* ======================================================== */
float TWIPR_ControlManager::_updateTIC(float theta) {
	if (this->control_config.tic_enabled == false){
		return 0;
	}

	if (this->control_config.tic_theta_limit != 0){
		if (std::fabs(theta) > this->control_config.tic_theta_limit){
			this->_tic_integral = 0;
			this->enableTIC(false);
			return 0;
		}
	}

	this->_tic_integral += 1/this->config.freq * theta;

	if (this->_tic_integral > this->control_config.tic_max_error){
		this->_tic_integral = this->control_config.tic_max_error;
	}
	else if (this->_tic_integral < -this->control_config.tic_max_error){
		this->_tic_integral = - this->control_config.tic_max_error;
	}

	float output = this->_tic_integral * this->control_config.tic_ki;

	return output;
}


/* ======================================================== */
twipr_control_output_t TWIPR_ControlManager::_step_velocity(
		twipr_control_external_input_t input, twipr_estimation_state_t state) {

	twipr_control_output_t output = { 0, 0 };

	twipr_speed_control_input_t speed_control_input = { .forward =
			input.u_velocity_forward, .turn = input.u_velocity_turn, };

	this->_data.input_velocity_forward = input.u_velocity_forward;
	this->_data.input_velocity_turn = input.u_velocity_turn;

	// Update the Speed Controller
	twipr_speed_control_output_t speed_control_output =
			this->_update_velocity_control(speed_control_input, state);

	// Feed the result into the balancing controller
	twipr_balancing_control_input_t balancing_control_input = { .u_1 =
			speed_control_output.input_left, .u_2 =
			speed_control_output.input_right };

	this->_data.input_balancing_1 = balancing_control_input.u_1;
	this->_data.input_balancing_2 = balancing_control_input.u_2;

	twipr_balancing_control_output_t balancing_control_output =
			this->_update_balancing_control(balancing_control_input, state);

	output.u_left = balancing_control_output.u_1;
	output.u_right = balancing_control_output.u_2;

	return output;

}
/* ======================================================== */
twipr_speed_control_output_t TWIPR_ControlManager::_update_velocity_control(
		twipr_speed_control_input_t input, twipr_estimation_state_t state) {

	twipr_speed_control_output_t output = { 0, 0 };

	output = this->_speed_control.update(input, state.v, state.psi_dot);

	return output;
}

/* ======================================================== */
twipr_balancing_control_output_t TWIPR_ControlManager::_update_balancing_control(
		twipr_balancing_control_input_t input, twipr_estimation_state_t state) {

	twipr_balancing_control_output_t output = { 0, 0 };

	// Update the balancing controller
	this->_balancing_control.update(state, input, &output);

	return output;
}

/* ======================================================== */
twipr_position_control_output_t TWIPR_ControlManager::_update_position_control(
		twipr_position_control_input_t input, twipr_estimation_state_t state) {

	twipr_position_control_output_t output = { 0, 0 };

	// Update the balancing controller
	this->_position_control.update(state, input, &output);

	return output;
}
/* ======================================================== */
void TWIPR_ControlManager::_setTorque(twipr_control_output_t output) {
	// Limit the maximum torque

	// Apply the torque to the motors
	bilbo_drive_input_t drive_input = { .torque_left = output.u_left,
			.torque_right = output.u_right };

	this->config.drive->setTorque(drive_input);
}

/* ======================================================== */
twipr_logging_control_t TWIPR_ControlManager::getSample() {
	twipr_logging_control_t sample;
	sample.control_mode = this->mode;
	sample.control_status = this->status;
	sample.data = this->_data;

	return sample;
}

/* ======================================================== */
void TWIPR_ControlManager::_resetExternalInput() {

	this->_external_input.u_direct_1 = 0.0;
	this->_external_input.u_direct_2 = 0.0;
	this->_external_input.u_balancing_1 = 0.0;
	this->_external_input.u_balancing_2 = 0.0;
	this->_external_input.u_velocity_forward = 0.0;
	this->_external_input.u_velocity_turn = 0.0;
	this->_output.u_left = 0.0;
	this->_output.u_right = 0.0;

}

void TWIPR_ControlManager::_resetOutput() {
	this->_output.u_left = 0;
	this->_output.u_right = 0;
}



void stopControl(){
	if (manager){
		manager->stop();
	}
}
