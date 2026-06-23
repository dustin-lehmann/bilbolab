/*
 * bilbo_control.h
 *
 *  Created on: Jan 11, 2026
 *      Author: lehmann
 */

#ifndef CONTROL_BILBO_CONTROL_H_
#define CONTROL_BILBO_CONTROL_H_

#include "core.h"
#include "bilbo_balancing_control.h"
#include "bilbo_velocity_control.h"
#include "bilbo_position_control.h"
#include "bilbo_vic_tic.h"

class BILBO_Sequencer;
class BILBO_Supervisor;
extern core_utils_RegisterMap<256> register_map;

/* ---------------------------------------------------------------------------------------- */
struct bilbo_control_init_config_t {
	BILBO_Estimation *estimation;
	BILBO_Drive *drive;
	float Ts;
};

/* ---------------------------------------------------------------------------------------- */
struct bilbo_control_config_t {
	float state_feedback_gain[8];
	bilbo_tic_config_t tic_config;
	bilbo_vic_config_t vic_config;
	bilbo_psi_config_t psi_config;
	bilbo_velocity_control_config_t velocity_control_config;
	bilbo_position_control_config_t position_control_config;
	float max_torque = 0.5;
};

/* ---------------------------------------------------------------------------------------- */
struct bilbo_control_input_ext_t {
	float u_left;
	float u_right;
};

/* ---------------------------------------------------------------------------------------- */
struct bilbo_control_output_t {
	float u_left;
	float u_right;
};

/* ---------------------------------------------------------------------------------------- */
enum class bilbo_control_mode_t : uint8_t {
	OFF = 0, DIRECT = 1, BALANCING = 2, VELOCITY = 3, POSITION = 4
};

/* ---------------------------------------------------------------------------------------- */
enum class bilbo_control_status_t : int8_t {
	NONE = 0, RUNNING = 1, ERROR = -1
};

/* ---------------------------------------------------------------------------------------- */
struct bilbo_control_callbacks_t {
	core_utils_CallbackContainer<4, uint16_t> error;
	core_utils_CallbackContainer<4, uint32_t> step;
	core_utils_CallbackContainer<4, bilbo_control_mode_t> mode_change;
};

/* ---------------------------------------------------------------------------------------- */
enum class control_event_t : uint8_t {
	CONTROL_EVENT_ERROR = 0,
	CONTROL_MODE_CHANGED = 1,
	CONTROL_CONFIG_CHANGED = 2,
	VIC_CHANGED = 3,
	TIC_CHANGED = 4,
	PSI_CHANGED = 5,
};

/* ---------------------------------------------------------------------------------------- */
struct bilbo_control_data_t {
	bilbo_control_mode_t mode;
	bilbo_control_status_t status;
	uint8_t vic_enabled;
	uint8_t tic_enabled;
	uint8_t psi_enabled;

	bilbo_position_control_data_t position_control_data;

	bilbo_velocity_control_command_t velocity_command;
	bilbo_velocity_control_output_t velocity_output;

	bilbo_control_input_ext_t input_ext;
	bilbo_balancing_control_output_t balancing_output;

	bilbo_control_output_t output;
};

/* ---------------------------------------------------------------------------------------- */
typedef struct control_event_message_data_t {
	control_event_t event;
	bilbo_control_mode_t mode;
	bilbo_control_data_t data;
	uint32_t tick;
} control_event_message_data_t;

/* ---------------------------------------------------------------------------------------- */
typedef BILBO_Message<control_event_message_data_t, MSG_EVENT,
BILBO_MESSAGE_CONTROL_EVENT> BILBO_Message_Control_Event;

/* ======================================================================================== */
class BILBO_Control {
public:

	BILBO_Control();
	void init(bilbo_control_init_config_t config);

	// Methods
	void start();
	void stop();
	void reset();
	bool set_mode(bilbo_control_mode_t mode);
	bool set_config(bilbo_control_config_t config); // Discouraged to use over Serial since length > 128 bytes and currently not supported

	bool set_vc_pid_v(pid_control_config_t config);
	bool set_vc_ff_v(feedforward_config_t config);
	bool set_vc_pid_psidot(pid_control_config_t config);
	bool set_vc_ff_psidot(feedforward_config_t config);

	bool set_tic_config(bilbo_tic_config_t config);
	bool set_vic_config(bilbo_vic_config_t config);
	bool set_psi_config(bilbo_psi_config_t config);
	bool set_max_torque(float max_torque);

	// Position control configuration
	bool set_position_control_config(bilbo_position_control_config_t config);
	bilbo_position_control_config_t get_position_control_config();

	// Position control interface - Path following
	bool position_clear_path();
	bool position_add_path_point(path_point_t point);
	bool position_add_path_points_batch(path_points_batch_t batch);
	bool position_add_stop_index(uint16_t index);
	bool position_start_path(bilbo_path_start_cmd_t cmd);
	void position_pause_path();
	void position_resume_path();
	void position_abort_path();
	bilbo_path_state_t position_get_path_state();
	bilbo_position_control_data_t position_get_data();
	uint16_t position_get_path_point_count();

	// Position control interface - SPI path upload
	void position_spi_path_received(uint16_t count);

	// Position control interface - Single-point commands
	bool position_turn_to_heading(turn_to_heading_command_t cmd);
	bool position_move_to_point(move_to_point_command_t cmd);
	bool position_reset();

	bilbo_control_config_t get_config();

	bilbo_control_output_t update();

	// Interface Methods
	bilbo_control_data_t get_data();
	bool set_external_input(bilbo_control_input_ext_t input);
	bool set_velocity_command(bilbo_velocity_control_command_t command);
	// One-shot position nudge ("free from wall"), OFF mode only. distance_m is the
	// travel magnitude (meters); the direction is chosen from theta to roll away
	// from the fall.
	bool nudge(float distance_m);

	bool set_balancing_gain(float K[8]);

	bool set_vic_enabled(bool state);
	bool set_tic_enabled(bool state);
	bool set_psi_enabled(bool state);
	bool set_psi_setpoint(float psi);

	bool enable_external_input();
	bool disable_external_input();
	void reset_external_input();

	// Public Variables
	bilbo_control_status_t status = bilbo_control_status_t::NONE;
	bilbo_control_mode_t mode = bilbo_control_mode_t::OFF;
	bilbo_control_init_config_t config;
	bilbo_control_config_t control_config;
	bilbo_control_callbacks_t callbacks;

	// Controllers
	BILBO_BalancingControl balancing_control;
	BILBO_VelocityControl velocity_control;
	BILBO_PositionControl position_control;
	BILBO_TIC_Controller tic_controller;
	BILBO_VIC_Controller vic_controller;
	BILBO_PSI_Controller psi_controller;

	// Pointer to SPI path receive buffer (set by firmware.cpp, in DMA-accessible RAM)
	path_point_t *spi_path_rx_buffer = nullptr;

	friend class BILBO_Sequencer;
	friend class BILBO_Supervisor;

private:

	bool _external_input_enabled = true;
	bilbo_control_input_ext_t _external_input;
	bilbo_velocity_control_command_t _velocity_command;
	bilbo_control_data_t _data;

	void _set_torque(bilbo_control_output_t output);

	void _on_tic_disabled(void);

	// Callback for position control completion (resets velocity control integrators)
	void _on_position_command_finished(uint8_t);

};

#endif /* CONTROL_BILBO_CONTROL_H_ */
