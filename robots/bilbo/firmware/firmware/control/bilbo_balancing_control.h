/*
 * bilbo_control.h
 *
 *  Created on: 22 Feb 2023
 *      Author: Dustin Lehmann
 */

#ifndef CONTROL_BILBO_BALANCING_CONTROL_H_
#define CONTROL_BILBO_BALANCING_CONTROL_H_

#include "firmware_core.h"
#include "bilbo_estimation.h"

#define BILBO_BALANCING_CONTROL_ERROR 0x00000601
#define BILBO_BALANCING_CONTROL_ERROR_INIT 0x00000602

enum class bilbo_balancing_control_mode_t: uint8_t {
	OFF = 0,
	DIRECT = 1,
	ON = 2,
};

enum class bilbo_balancing_control_status_t: int8_t {
	NONE = 0,
	IDLE = 1,
	ERROR = -1,
	RUNNING = 2,
};

typedef enum bilbo_balancing_control_callback_id_t : uint8_t {
	BILBO_BALANCING_CONTROL_CALLBACK_ERROR = 1,
} bilbo_balancing_control_callback_id_t;

typedef struct bilbo_balancing_control_config_t {
	float K[8] = { 0 };
	float pitch_offset = 0;
} bilbo_balancing_control_config_t;

typedef struct bilbo_balancing_control_input_t {
	float u_1;
	float u_2;
} bilbo_balancing_control_input_t;

typedef struct bilbo_balancing_control_output_t {
	float u_1;
	float u_2;
} bilbo_balancing_control_output_t;

class BILBO_BalancingControl {
public:
	BILBO_BalancingControl();
	void init(bilbo_balancing_control_config_t config);
	void start();
	void reset();
	void stop();

	void registerCallback(bilbo_balancing_control_callback_id_t callback_id,
			void (*callback)(void *argument, void *params), void *params);

	bilbo_balancing_control_output_t update(bilbo_estimation_state_t state,
			bilbo_balancing_control_input_t input);

	void set_K(float K[8]);
	void set_mode(bilbo_balancing_control_mode_t mode);

	bilbo_balancing_control_status_t status;
	bilbo_balancing_control_mode_t mode;
	bilbo_balancing_control_config_t config;
private:

	bilbo_balancing_control_output_t _calculateOutput(bilbo_estimation_state_t state,
			bilbo_balancing_control_input_t input);
	bilbo_balancing_control_input_t _last_input;
	bilbo_estimation_state_t _dynamic_state;
	bilbo_estimation_state_t _last_dynamic_state;
	bilbo_balancing_control_output_t _last_output;
};

#endif /* CONTROL_BILBO_BALANCING_CONTROL_H_ */
