/*
 * twipr_speed_control.h
 *
 *  Created on: Oct 29, 2024
 *      Author: Dustin Lehmann
 */

#ifndef CONTROL_TWIPR_SPEED_CONTROL_H_
#define CONTROL_TWIPR_SPEED_CONTROL_H_

#include "core.h"

class TWIPR_Supervisor; // Definition for a supervisor to have access to the private methods and variables

typedef struct twipr_speed_control_forward_config_t {
	float Kp;
	float Ki;
	float Kd;

	float Ts;

	bool enable_output_limit = false;
	float output_limit = 0;

	bool enable_integral_limit = false;
	float integral_limit = 0.05;

	bool enable_rate_limit = false;
	float rate_limit = 0;
} twipr_speed_control_forward_config_t;

typedef struct twipr_speed_control_turn_config_t {
	float Kp;
	float Ki;
	float Kd;

	float Ts;

	bool enable_output_limit = false;
	float output_limit = 0;

	bool enable_integral_limit = false;
	float integral_limit = 1;

	bool enable_rate_limit = false;
	float rate_limit = 0;
} twipr_speed_control_turn_config_t;

typedef struct twipr_speed_control_config_t {
	twipr_speed_control_forward_config_t forward_config;
	twipr_speed_control_turn_config_t turn_config;

} twipr_speed_control_config_t;

typedef struct twipr_speed_control_output_t {
	float input_left;
	float input_right;
} twipr_speed_control_output_t;

typedef struct twipr_speed_control_input_t {
	float forward;
	float turn;
} twipr_speed_control_input_t;

class TWIPR_SpeedControl {
public:
	TWIPR_SpeedControl();

	void init(twipr_speed_control_config_t config);

	void setInput(twipr_speed_control_input_t input);

	twipr_speed_control_output_t update(twipr_speed_control_input_t input, float speed_forward_meas,
			float speed_turn_meas);

	void setForwardPID(float Kp, float Ki, float Kd);
	void setTurnPID(float Kp, float Ki, float Kd);

	void reset();

	twipr_speed_control_config_t config;
	twipr_speed_control_input_t input;
	twipr_speed_control_output_t output;

	friend class TWIPR_Supervisor;

private:

	PID_Control _forward_control_pid;
	PID_Control _turn_control_pid;

};

#endif /* CONTROL_TWIPR_SPEED_CONTROL_H_ */
