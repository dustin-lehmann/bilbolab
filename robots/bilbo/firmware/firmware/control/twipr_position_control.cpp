/*
 * twipr_control.cpp
 *
 *  Created on: 22 Feb 2023
 *      Author: Dustin Lehmann
 */

#include <twipr_position_control.h>
#include "ekf.h"

TWIPR_PositionControl::TWIPR_PositionControl() {
	this->mode = TWIPR_position_CONTROL_MODE_OFF;
	this->status = TWIPR_position_CONTROL_STATUS_NONE;
}

/* ========================================================================= */
void TWIPR_PositionControl::init(twipr_position_control_config_t config) {
	this->config = config;
	this->status = TWIPR_position_CONTROL_STATUS_IDLE;
}

/* ========================================================================= */
void TWIPR_PositionControl::start() {
	if (this->status == TWIPR_position_CONTROL_STATUS_NONE
			|| this->status == TWIPR_position_CONTROL_STATUS_ERROR) {

//		setError();
//		twipr_error_handler(TWIPR_position_CONTROL_ERROR_INIT);
	}
	this->status = TWIPR_position_CONTROL_STATUS_RUNNING;
}

/* ========================================================================= */
void TWIPR_PositionControl::update(twipr_estimation_state_t state,
		twipr_position_control_input_t input,
		twipr_position_control_output_t *output) {

	switch (this->status) {
	case TWIPR_position_CONTROL_STATUS_NONE: {
		output->u_1 = 0;
		output->u_2 = 0;
		break;
	}
	case TWIPR_position_CONTROL_STATUS_IDLE: {
		output->u_1 = 0;
		output->u_2 = 0;
		break;
	}
	case TWIPR_position_CONTROL_STATUS_ERROR: {
		output->u_1 = 0;
		output->u_2 = 0;
		break;
	}
	case TWIPR_position_CONTROL_STATUS_RUNNING: {
		switch (this->mode) {
		case TWIPR_position_CONTROL_MODE_OFF: {
			output->u_1 = 0;
			output->u_2 = 0;
			break;
		}
		case TWIPR_position_CONTROL_MODE_DIRECT: {
			output->u_1 = input.u_1;
			output->u_2 = input.u_2;
			break;
		}
		case TWIPR_position_CONTROL_MODE_ON: {
			this->_calculateOutput(state, input, output);
		}
		}
	}
	}
}
/* ========================================================================= */
void TWIPR_PositionControl::_calculateOutput(twipr_estimation_state_t state,
		twipr_position_control_input_t input,
		twipr_position_control_output_t *output) {


	float Ts = 0.01; //sampling time

	/* integration of existing states to get position and angle states */
	this->x += state.v * Ts;
	this->angle += state.psi_dot * Ts;

	float z[2] = {0, 0};
	bool meas_valid = this->position_update_flag;

	if (this->position_update_flag == true){
//		this->e_1 =0;
//		this->e_2 =0;
//		this->x = config2.conf[1];
//		this->angle = config2.conf[2];
		this->position_update_flag = false;

		z[0] = config2.conf[1];
		z[1] = config2.conf[2];


		send_debug("integrators reset and position set to: %.2f %.2f", this->x, this->angle);
	}


	ekf_state_t est;
	ekf_robot_update(state.v, state.psi_dot, z, meas_valid, &est);
	this->x = est.x;
	this->angle = est.psi;


	/* check 2 pi periodicity */
	if (this->angle >= 6.28){
		this->angle = 0;
		input.u_2 = 0;
	}


	this->e_1 += (input.u_1 - this->x) * Ts;
	this->e_2 += (input.u_2 - this->angle) * Ts;

	/* ARW: Check if intergral is too high  if special config otherwise default*/
	if (this->e_1 >= 0.2/this->config2.K[6]){
				this->e_1 =0.2/this->config2.K[6];
			}

	if (this->e_2 >= 0.2/this->config2.K[7]){
				this->e_2 =0.2/this->config2.K[7];
			}






	output->u_1 =     this->config2.K[0] * (input.u_1-this->x)
	                    - this->config2.K[1] * state.v
	                    - this->config2.K[2] * state.theta
	                    - this->config2.K[3] * state.theta_dot
	                    +this->config2.K[4] * (input.u_2-this->angle)
	                    - this->config2.K[5] * state.psi_dot;
	                    - this->config2.K[6] * this->e_1
	                    - this->config2.K[7] * this->e_2;

	output->u_2 =     this->config2.K[8] *  (input.u_1-this->x)
	                    - this->config2.K[9] * state.v
	                    - this->config2.K[10] * state.theta
	                    - this->config2.K[11] * state.theta_dot
	                    + this->config2.K[12] * (input.u_2-this->angle)
	                    - this->config2.K[13] * state.psi_dot;
	                    - this->config2.K[14] * this->e_1
	                    - this->config2.K[15] * this->e_2;


	/* sendig debugmessage every 100 step if configured in config*/
	if (++this->debug_counter >= 100 && this->config2.conf[6] != 0) {
		send_debug(
			        "%.2f:%.2fu%.2f:%.2f",
			        input.u_1,  input.u_2,  this->x , this->angle
			    );
		send_debug(
			        "est %.2f:%.2f:%.2f",
			        est.x  ,est.y, est.psi
			    );

	    this->debug_counter = 0;

	}



	if(config2.conf[7] != 0){
		output->u_1 = 0;
		output->u_2 = 0;

	}
	if (output->u_1 >1 || output->u_2 >1){

		output->u_1 =0;
		output->u_2 =0;
		this->e_1 = 0;
		this->e_2 = 0;
		send_debug("zu hohe u. Abbruch");
	}


}
/* ========================================================================= */
void TWIPR_PositionControl::reset() {
//	this->stop();
//	this->start();
}
/* ========================================================================= */
void TWIPR_PositionControl::stop() {
	this->mode = TWIPR_position_CONTROL_MODE_OFF;
//	this->status = TWIPR_position_CONTROL_STATUS_IDLE;
}
/* ========================================================================= */
void TWIPR_PositionControl::set_K(float K[8]) {
	memcpy(this->config.K, K, sizeof(float) * 8);
}

/* ========================================================================= */
void TWIPR_PositionControl::set_K_Pos(float K[16]) {
	memcpy(this->config2.K, K, sizeof(float) * 16);
}
/* ========================================================================= */
void TWIPR_PositionControl::set_Pos_Config(float K[8]) {
	if (K[0] == 1){
		send_debug("Position update flag set!");
		this->position_update_flag = true;
//		this->e_1 =0;
//		this->e_2 =0;
//		this->x = K[1];
//		this->angle = K[2];
		//this->position_update_flag = false;
	}
	memcpy(this->config2.conf, K, sizeof(float) * 8);



}
/* ========================================================================= */
void TWIPR_PositionControl::setMode(twipr_position_control_mode_t mode) {

	if (this->status == TWIPR_position_CONTROL_STATUS_ERROR){
		return;
	}

	if (this->status == TWIPR_position_CONTROL_STATUS_NONE){
		return;
	}
	this->mode = mode;
}

