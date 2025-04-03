/*
 * twipr_control.h
 *
 *  Created on: 3 Mar 2023
 *      Author: lehmann_workstation
 */

#ifndef CONTROL_TWIPR_CONTROL_H_
#define CONTROL_TWIPR_CONTROL_H_
#pragma once

#include "core.h"
#include "firmware_settings.h"
#include "twipr_balancing_control.h"
#include "twipr_speed_control.h"
#include "firmware_defs.h"
#include "firmware_core.h"
#include "bilbo_drive.h"

class TWIPR_Sequencer;
class TWIPR_Supervisor;
extern core_utils_RegisterMap<256> register_map;


typedef struct twipr_control_init_config_t {
	TWIPR_Estimation *estimation;
	BILBO_Drive *drive;
	float max_torque;
	float freq;
} twipr_control_init_config_t;


typedef enum twipr_control_mode_t {
	TWIPR_CONTROL_MODE_OFF = 0,
	TWIPR_CONTROL_MODE_DIRECT = 1,
	TWIPR_CONTROL_MODE_BALANCING = 2,
	TWIPR_CONTROL_MODE_VELOCITY = 3,
} twipr_control_mode_t;

typedef enum twipr_control_status_t {
	TWIPR_CONTROL_STATUS_ERROR = -1,
	TWIPR_CONTROL_STATUS_IDLE = 0,
	TWIPR_CONTROL_STATUS_RUNNING = 1,
} twipr_control_status_t;

typedef struct twipr_control_direct_input_t {
	float input_left;
	float input_right;
}twipr_control_direct_input_t;

typedef struct twipr_control_external_input_t {
	float u_direct_1;
	float u_direct_2;
	float u_balancing_1;
	float u_balancing_2;
	float u_velocity_forward;
	float u_velocity_turn;
} twipr_control_external_input_t;

typedef struct twipr_control_data_t {
	float input_velocity_forward;
	float input_velocity_turn;
	float input_balancing_1;
	float input_balancing_2;
	float input_left;
	float input_right;
	float output_left;
	float output_right;
} twipr_control_data_t;

typedef struct twipr_control_output_t {
	float u_left;
	float u_right;
} twipr_control_output_t;

typedef enum twipr_control_callback_id_t {
	TWIPR_CONTROL_CALLBACK_ERROR,
	TWIPR_CONTROL_CALLBACK_STEP,
} twipr_control_callback_id_t;

typedef struct twipr_logging_control_t {
	twipr_control_status_t control_status;
	twipr_control_mode_t control_mode;
	twipr_control_external_input_t external_input;
	twipr_control_data_t data;
} twipr_logging_control_t;


typedef struct twipr_control_callbacks_t {
	core_utils_CallbackContainer<4, uint16_t> error;
	core_utils_CallbackContainer<4, uint32_t> step;
	core_utils_CallbackContainer<4, twipr_control_mode_t> mode_change;
} twipr_control_callbacks_t;

typedef struct twipr_control_configuration_t {
	float K[8];
	float forward_kp;
	float forward_ki;
	float forward_kd;
	float turn_kp;
	float turn_ki;
	float turn_kd;
	bool vic_enabled; // Velocity Integral Control enable/disable
	float vic_ki;  // Velocity Integral Control Ki
	float vic_max_error; // Velocity Integral Control maxmum error
	float vic_v_limit;  // Velocity Integral Control Velocity Limit
} twipr_control_configuration_t;

class TWIPR_ControlManager {

public:
	TWIPR_ControlManager();

	void init(twipr_control_init_config_t config);
	uint8_t start();

	void stop();

	void reset();

	void update();



	twipr_logging_control_t getSample();

	uint8_t setMode(twipr_control_mode_t mode);
	twipr_control_status_t getStatus();

	void disableExternalInput();
	void enableExternalInput();


	void setExternalInput(twipr_control_external_input_t input);
	void setDirectInput(twipr_control_direct_input_t input);
	void setBalancingInput(twipr_balancing_control_input_t input);
	void setSpeed(twipr_speed_control_input_t speed);


	uint8_t setBalancingGain(float *K);
	uint8_t setVelocityControlForwardPID(float *K);
	uint8_t setVelocityControlForwardPID(float Kp, float Ki, float Kd);
	uint8_t setVelocityControlTurnPID(float *K);
	uint8_t setVelocityControlTurnPID(float Kp, float Ki, float Kd);

	bool setControlConfiguration(twipr_control_configuration_t config);
	twipr_control_configuration_t getControlConfiguration();

	bool enableSpeedIntegralControl(bool state);

	twipr_control_status_t status = TWIPR_CONTROL_STATUS_IDLE;
	twipr_control_mode_t mode = TWIPR_CONTROL_MODE_OFF;

	twipr_control_init_config_t config;

	twipr_control_configuration_t control_config;

	twipr_control_callbacks_t callbacks;

	friend class TWIPR_Sequencer;
	friend class TWIPR_Supervisor;

private:
	TWIPR_BalancingControl _balancing_control;
	TWIPR_SpeedControl _speed_control;
	twipr_control_external_input_t _external_input;

	twipr_control_output_t _output;

	twipr_estimation_state_t _dynamic_state;

	twipr_control_data_t _data;


	bool _externalInputEnabled = true;


	float _error_velocity_integral = 0;
	float _updateVelocityIntegralController(float velocity);

	//	twipr_control_input_t _last_input;
	//	twipr_estimation_state_t _last_dynamic_state;

	TWIPR_Estimation *_estimation;


	uint32_t _tick;

	twipr_speed_control_output_t _update_velocity_control(
			twipr_speed_control_input_t input, twipr_estimation_state_t state);

	twipr_balancing_control_output_t _update_balancing_control(
			twipr_balancing_control_input_t input,
			twipr_estimation_state_t state);

	void _setBalancingInput(twipr_balancing_control_input_t input);

	twipr_control_output_t _step_off();
	twipr_control_output_t _step_error();
	twipr_control_output_t _step_idle();
	twipr_control_output_t _step_direct(twipr_control_external_input_t input);
	twipr_control_output_t _step_balancing(twipr_control_external_input_t input,twipr_estimation_state_t state);
	twipr_control_output_t _step_velocity(twipr_control_external_input_t input, twipr_estimation_state_t state);

	void _setTorque(twipr_control_output_t output);


	void _resetExternalInput();
	void _resetOutput();
};

void twipr_control_task(void *control_manager);


void stopControl();

#endif /* CONTROL_TWIPR_CONTROL_H_ */
