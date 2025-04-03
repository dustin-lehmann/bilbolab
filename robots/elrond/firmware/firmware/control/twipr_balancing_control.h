/*
 * twipr_control.h
 *
 *  Created on: 22 Feb 2023
 *      Author: Dustin Lehmann
 */

#ifndef CONTROL_TWIPR_BALANCING_CONTROL_H_
#define CONTROL_TWIPR_BALANCING_CONTROL_H_

#include "firmware_core.h"
#include "twipr_estimation.h"


#define TWIPR_BALANCING_CONTROL_ERROR 0x00000601
#define TWIPR_BALANCING_CONTROL_ERROR_INIT 0x00000602

typedef enum twipr_balancing_control_mode_t {
	TWIPR_BALANCING_CONTROL_MODE_OFF = 0,
	TWIPR_BALANCING_CONTROL_MODE_DIRECT = 1,
	TWIPR_BALANCING_CONTROL_MODE_ON = 2,
} twipr_balancing_control_mode_t;

typedef enum twipr_balancing_control_status_t {
	TWIPR_BALANCING_CONTROL_STATUS_NONE = 0,
	TWIPR_BALANCING_CONTROL_STATUS_IDLE = 1,
	TWIPR_BALANCING_CONTROL_STATUS_ERROR = -1,
	TWIPR_BALANCING_CONTROL_STATUS_RUNNING = 2,
} twipr_balancing_control_status_t;

typedef enum twipr_balancing_control_callback_id_t {
	TWIPR_BALANCING_CONTROL_CALLBACK_ERROR = 1,
} twipr_balancing_control_callback_id_t;

typedef struct twipr_balancing_control_config_t {
	float K[8] = {0};
	float pitch_offset = 0;
} twipr_balancing_control_config_t;

typedef struct twipr_balancing_control_input_t {
	float u_1;
	float u_2;
} twipr_balancing_control_input_t;

typedef struct twipr_balancing_control_output_t {
	float u_1;
	float u_2;
} twipr_balancing_control_output_t;

class TWIPR_BalancingControl {
public:
	TWIPR_BalancingControl();
	void init(twipr_balancing_control_config_t config);
	void start();
	void reset();
	void stop();

	void registerCallback(twipr_balancing_control_callback_id_t callback_id,
			void (*callback)(void *argument, void *params), void *params);

	void update(twipr_estimation_state_t state,
			twipr_balancing_control_input_t input,
			twipr_balancing_control_output_t *output);

	void set_K(float K[8]);
	void setMode(twipr_balancing_control_mode_t mode);

	twipr_balancing_control_status_t status;
	twipr_balancing_control_mode_t mode;
	twipr_balancing_control_config_t config;
private:

	void _calculateOutput(twipr_estimation_state_t state,
			twipr_balancing_control_input_t input,
			twipr_balancing_control_output_t *output);
	twipr_balancing_control_input_t _last_input;
	twipr_estimation_state_t _dynamic_state;
	twipr_estimation_state_t _last_dynamic_state;
	twipr_balancing_control_output_t _last_output;
};

#endif /* CONTROL_TWIPR_BALANCING_CONTROL_H_ */
