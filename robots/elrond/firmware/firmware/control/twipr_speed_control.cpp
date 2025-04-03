/*
 * twipr_speed_control.cpp
 *
 *  Created on: Oct 29, 2024
 *      Author: Dustin Lehmann
 */

#include "twipr_speed_control.h"

TWIPR_SpeedControl::TWIPR_SpeedControl() {

}


uint8_t counter = 0;

// =========================================================================================================================== //
void TWIPR_SpeedControl::init(twipr_speed_control_config_t config) {
	this->config = config;
	pid_control_config_t forward_control_config = { .Kp =
			this->config.forward_config.Kp,
			.Ki = this->config.forward_config.Ki, .Kd =
					this->config.forward_config.Kd, .Ts =
					this->config.forward_config.Ts,

			.enable_integral_limit =
					this->config.forward_config.enable_integral_limit,
			.error_integral_limit = this->config.forward_config.integral_limit,

			.enable_output_limit =
					this->config.forward_config.enable_output_limit,
			.output_limit_max = this->config.forward_config.output_limit,
			.output_limit_min = -this->config.forward_config.output_limit,

			.enable_rate_limit = this->config.forward_config.enable_rate_limit,
			.rate_limit_max = this->config.forward_config.rate_limit,
			.rate_limit_min = -this->config.forward_config.rate_limit, };

	pid_control_config_t turn_control_config = { .Kp =
			this->config.turn_config.Kp, .Ki = this->config.turn_config.Ki,
			.Kd = this->config.turn_config.Kd,
			.Ts = this->config.turn_config.Ts,

			.enable_integral_limit =
					this->config.turn_config.enable_integral_limit,
			.error_integral_limit = this->config.turn_config.integral_limit,

			.enable_output_limit = this->config.turn_config.enable_output_limit,
			.output_limit_max = this->config.turn_config.output_limit,
			.output_limit_min = -this->config.turn_config.output_limit,

			.enable_rate_limit = this->config.turn_config.enable_rate_limit,
			.rate_limit_max = this->config.turn_config.rate_limit,
			.rate_limit_min = -this->config.turn_config.rate_limit, };

	this->_forward_control_pid.init(forward_control_config);
	this->_turn_control_pid.init(turn_control_config);

}

void TWIPR_SpeedControl::reset() {
	this->_forward_control_pid.reset();
	this->_turn_control_pid.reset();

	this->input.forward = 0;
	this->input.turn = 0;
	this->output.input_left = 0;
	this->output.input_right = 0;
}

// =========================================================================================================================== //
twipr_speed_control_output_t TWIPR_SpeedControl::update(
		twipr_speed_control_input_t input, float speed_forward_meas,
		float speed_turn_meas) {
	twipr_speed_control_output_t output = { .input_left = 0, .input_right = 0 };

	this->input = input;
	float error_speed = input.forward - speed_forward_meas;
	float error_turn = input.turn - speed_turn_meas;

	float output_forward = this->_forward_control_pid.update(error_speed);
	float output_turn = this->_turn_control_pid.update(error_turn);

	this->output.input_left = output_forward / 2.0 + output_turn / 2.0;
	this->output.input_right = output_forward / 2.0 - output_turn / 2.0;

	return this->output;

	return output;
}

// =========================================================================================================================== //
void TWIPR_SpeedControl::setForwardPID(float Kp, float Ki, float Kd) {
	this->config.forward_config.Kp = Kp;
	this->config.forward_config.Ki = Ki;
	this->config.forward_config.Kd = Kd;

	this->_forward_control_pid.config.Kp = Kp;
	this->_forward_control_pid.config.Ki = Ki;
	this->_forward_control_pid.config.Kd = Kd;

}

// =========================================================================================================================== //
void TWIPR_SpeedControl::setTurnPID(float Kp, float Ki, float Kd) {
	this->config.turn_config.Kp = Kp;
	this->config.turn_config.Ki = Ki;
	this->config.turn_config.Kd = Kd;

	this->_turn_control_pid.config.Kp = Kp;
	this->_turn_control_pid.config.Ki = Ki;
	this->_turn_control_pid.config.Kd = Kd;
}

