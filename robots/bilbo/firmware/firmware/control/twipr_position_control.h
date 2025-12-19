/*
 * twipr_position_control.h
 *
 *  Created on: 27 Mai 2025
 *      Author: Tiziano Humpert
 */

#ifndef CONTROL_TWIPR_position_CONTROL_H_
#define CONTROL_TWIPR_position_CONTROL_H_

#include "firmware_core.h"
#include "twipr_estimation.h"


#define TWIPR_position_CONTROL_ERROR 0x00000601
#define TWIPR_position_CONTROL_ERROR_INIT 0x00000602

typedef enum twipr_position_control_mode_t {
	TWIPR_position_CONTROL_MODE_OFF = 0,
	TWIPR_position_CONTROL_MODE_DIRECT = 1,
	TWIPR_position_CONTROL_MODE_ON = 2,
} twipr_position_control_mode_t;

typedef enum twipr_position_control_status_t {
	TWIPR_position_CONTROL_STATUS_NONE = 0,
	TWIPR_position_CONTROL_STATUS_IDLE = 1,
	TWIPR_position_CONTROL_STATUS_ERROR = -1,
	TWIPR_position_CONTROL_STATUS_RUNNING = 2,
} twipr_position_control_status_t;

typedef enum twipr_position_control_callback_id_t {
	TWIPR_position_CONTROL_CALLBACK_ERROR = 1,
} twipr_position_control_callback_id_t;

typedef struct twipr_position_control_config_t {
	float K[8] = {0};
	float pitch_offset = 0;
} twipr_position_control_config_t;

typedef struct twipr_position_control_config_t2 {
	float K[16] = {0};
	float conf[8] = {0};
	float pitch_offset = 0;
} twipr_position_control_config_t2;

typedef struct twipr_position_control_input_t {
	float u_1;
	float u_2;
} twipr_position_control_input_t;

typedef struct twipr_position_control_output_t {
	float u_1;
	float u_2;
} twipr_position_control_output_t;


class TWIPR_PositionControl {
public:
	TWIPR_PositionControl();
	void init(twipr_position_control_config_t config);
	void start();
	void reset();
	void stop();
	float x;//Position in m
	float angle;//Angle in rad

	float e_1;
	float e_2;

	float u1_norm[100] = {0};
	float u1_pos[100] = {0};

	float u2_norm[100] = {0};
	float u2_pos[100] = {0};


	int debug_counter; // <--- hier deklarieren

	void registerCallback(twipr_position_control_callback_id_t callback_id,
			void (*callback)(void *argument, void *params), void *params);

	void update(twipr_estimation_state_t state,
			twipr_position_control_input_t input,
			twipr_position_control_output_t *output);

	void set_K(float K[8]);
	void set_K_Pos(float K[16]);
	void set_Pos_Config(float K[8]);
	void setMode(twipr_position_control_mode_t mode);

	twipr_position_control_status_t status;
	twipr_position_control_mode_t mode;
	twipr_position_control_config_t config;
	twipr_position_control_config_t2 config2;
private:
	bool position_update_flag = false;
	void _calculateOutput(twipr_estimation_state_t state,
			twipr_position_control_input_t input,
			twipr_position_control_output_t *output);
	twipr_position_control_input_t _last_input;
	twipr_estimation_state_t _dynamic_state;
	twipr_estimation_state_t _last_dynamic_state;
	twipr_position_control_output_t _last_output;
};

#endif /* CONTROL_TWIPR_position_CONTROL_H_ */
