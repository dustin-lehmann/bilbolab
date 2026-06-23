/*
 * bilbo_control.cpp
 *
 *  Created on: Jan 11, 2026
 *      Author: lehmann
 */

#include "bilbo_control.h"
#include "bilbo_communication.h"
#include "firmware_settings.h"
#include "bilbo_model.h"

BILBO_Control *control = nullptr;

osSemaphoreId_t semaphore_external_input;

BILBO_Control::BILBO_Control() {
	// Constructor implementation (if needed)
}

/* -------------------------------------------------------------------------------------- */
void BILBO_Control::init(bilbo_control_init_config_t config) {
	this->config = config;

	// Initialize the balancing controller
	bilbo_balancing_control_config_t balancing_control_config;
	this->balancing_control.init(balancing_control_config);

	this->status = bilbo_control_status_t::RUNNING;
	this->mode = bilbo_control_mode_t::OFF;

	this->tic_controller.callbacks.disable.registerFunction(this,
			&BILBO_Control::_on_tic_disabled);

	// Register position control callbacks to reset velocity control integrators
	// when position control finishes (prevents integrator windup)
	this->position_control.callbacks.path_finished.registerFunction(this,
			&BILBO_Control::_on_position_command_finished);

	this->position_control.callbacks.path_timeout.registerFunction(this,
			&BILBO_Control::_on_position_command_finished);

	this->position_control.callbacks.path_aborted.registerFunction(this,
			&BILBO_Control::_on_position_command_finished);

}

/* -------------------------------------------------------------------------------------- */
void BILBO_Control::start() {
	this->balancing_control.start();
}

/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_config(bilbo_control_config_t config) {
	this->control_config = config;

	// Set the balancing gain
	this->balancing_control.set_K(this->control_config.state_feedback_gain);

	// Configure the velocity controller
	this->velocity_control.set_config(
			this->control_config.velocity_control_config);

	// Configure the position controller
	this->position_control.set_config(
			this->control_config.position_control_config);

	// Configure the TIC controller
	this->tic_controller.set_config(this->control_config.tic_config);

	// Configure the VIC controller
	this->vic_controller.set_config(this->control_config.vic_config);

	// Configure the PSI controller
	this->psi_controller.set_config(this->control_config.psi_config);

	return true;
}

/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_vc_pid_v(pid_control_config_t config) {
	this->control_config.velocity_control_config.pid_config_v = config;
	this->velocity_control.set_config_forward_pid(config);
	return true;
}

/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_vc_ff_v(feedforward_config_t config) {
	this->control_config.velocity_control_config.ff_config_v = config;
	this->velocity_control.set_config_forward_ff(config);
	return true;
}

/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_vc_pid_psidot(pid_control_config_t config) {
	this->control_config.velocity_control_config.pid_config_psi_dot = config;
	this->velocity_control.set_config_turn_pid(config);
	return true;
}

/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_vc_ff_psidot(feedforward_config_t config) {
	this->control_config.velocity_control_config.ff_config_psi_dot = config;
	this->velocity_control.set_config_turn_ff(config);
	return true;
}
/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_tic_config(bilbo_tic_config_t config) {
	this->control_config.tic_config = config;
	this->tic_controller.set_config(config);
	return true;
}

/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_vic_config(bilbo_vic_config_t config) {
	this->control_config.vic_config = config;
	this->vic_controller.set_config(config);
	return true;
}

/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_psi_config(bilbo_psi_config_t config) {
	this->control_config.psi_config = config;
	this->psi_controller.set_config(config);
	return true;
}

/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_max_torque(float max_torque) {
	this->control_config.max_torque = max_torque;
	return true;
}

/* -------------------------------------------------------------------------------------- */
bilbo_control_config_t BILBO_Control::get_config() {

	// Collect the config from the velocity and position controllers
	this->control_config.velocity_control_config =
			this->velocity_control.get_config();
	this->control_config.position_control_config =
			this->position_control.get_config();

	return this->control_config;

}
/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_balancing_gain(float K[8]) {
	this->control_config.state_feedback_gain[0] = K[0];
	this->control_config.state_feedback_gain[1] = K[1];
	this->control_config.state_feedback_gain[2] = K[2];
	this->control_config.state_feedback_gain[3] = K[3];
	this->control_config.state_feedback_gain[4] = K[4];
	this->control_config.state_feedback_gain[5] = K[5];
	this->control_config.state_feedback_gain[6] = K[6];
	this->control_config.state_feedback_gain[7] = K[7];

	this->balancing_control.set_K(this->control_config.state_feedback_gain);

	return true;
}
/* -------------------------------------------------------------------------------------- */
void BILBO_Control::stop() {
	this->set_mode(bilbo_control_mode_t::OFF);
	this->_set_torque({ 0.0f, 0.0f });
}
/* -------------------------------------------------------------------------------------- */
void BILBO_Control::reset() {
	this->balancing_control.reset();
	this->velocity_control.reset();
	this->position_control.reset();

	this->_external_input_enabled = true;
	this->_external_input = { 0, 0 };

}
/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_mode(bilbo_control_mode_t mode) {
	if (this->status != bilbo_control_status_t::RUNNING) {
		return false;
	}

	// If the drive is in error, attempt to auto-recover before engaging any
	// active mode (e.g. after an overspeed emergency stop). This lets the user
	// re-arm balancing/velocity/position directly without a separate manual
	// drive reset. OFF never needs a healthy drive, so it is left untouched.
	if (mode != bilbo_control_mode_t::OFF
			&& this->config.drive->status == BILBO_DRIVE_STATUS_ERROR) {
		send_info("Drive in error on mode change to %d — attempting auto-reset. "
				"Tick: %d", (int) mode, tick_global);
		this->config.drive->resetDrive();
		if (this->config.drive->status == BILBO_DRIVE_STATUS_ERROR) {
			send_error("Auto-reset failed; cannot set mode to %d while drive is "
					"in error state. Tick: %d", (int) mode, tick_global);
			return false;
		}
	}

	if (this->mode == mode) {
		return true;
	}

	switch (mode) {
	case bilbo_control_mode_t::OFF: {
		this->balancing_control.stop();
//		this->_set_torque( { 0.0f, 0.0f });
		this->set_vic_enabled(false);
		this->set_tic_enabled(false);
		this->set_psi_enabled(false);
//		send_info("Set mode to OFF. Tick: %d", tick_global);
		break;
	}
	case bilbo_control_mode_t::DIRECT: {
		this->balancing_control.set_mode(
				bilbo_balancing_control_mode_t::DIRECT);
		this->set_vic_enabled(false);
		this->set_tic_enabled(false);
		this->set_psi_enabled(false);
		send_info("Set mode to DIRECT. Tick: %d", tick_global);
		break;
	}
	case bilbo_control_mode_t::BALANCING: {
		this->vic_controller.reset();
		this->psi_controller.reset();
		this->set_vic_enabled(true); // Sets VIC to enabled if configured
		this->set_tic_enabled(false);
		this->set_psi_enabled(false); // PSI is toggled manually via button
		this->balancing_control.set_mode(bilbo_balancing_control_mode_t::ON);
//		send_info("Set mode to BALANCING. Tick: %d", tick_global);
		break;
	}
	case bilbo_control_mode_t::VELOCITY: {

		// Check if we go here from OFF mode. This is not allowed.
		// We need to go through balancing or position

		if (this->mode == bilbo_control_mode_t::OFF) {
			send_error("Cannot set mode to VELOCITY from OFF. "
					"Please switch to BALANCING or POSITION first. Tick: %d",
					tick_global);
			return false;
		}

		this->balancing_control.set_mode(bilbo_balancing_control_mode_t::ON);
		this->velocity_control.reset();
		this->vic_controller.set_enabled(false); // Disable VIC when entering VELOCITY mode
		this->set_tic_enabled(false);
		this->set_psi_enabled(false); // Disable PSI when entering VELOCITY mode
//		send_info("Set mode to VELOCITY. Tick: %d", tick_global);
		break;
	}
	case bilbo_control_mode_t::POSITION: {

		// Check if we go here from OFF mode. This is not allowed.
		// We need to go through balancing or velocity
		if (this->mode == bilbo_control_mode_t::OFF) {
			send_error("Cannot set mode to POSITION from OFF. "
					"Please switch to BALANCING or VELOCITY first. Tick: %d",
					tick_global);
			return false;
		}
		this->vic_controller.set_enabled(false); // Disable VIC when entering POSITION mode
		this->set_tic_enabled(false);
		this->set_psi_enabled(false); // Disable PSI when entering POSITION mode
		this->balancing_control.set_mode(bilbo_balancing_control_mode_t::ON);
		this->velocity_control.reset();
		// Reset position control and clear any existing path/commands
		this->position_control.reset();
		this->position_control.clear_path();
//		send_info("Set mode to POSITION. Tick: %d", tick_global);
		break;
	}
	}

	// Reset controllers when entering a new mode
	this->reset();

	this->mode = mode;

	this->_data.mode = this->mode;

	// Call the callbacks and events
	this->callbacks.mode_change.call(mode);

	control_event_message_data_t event_message_data = { .event =
			control_event_t::CONTROL_MODE_CHANGED, .mode = mode, .data =
			this->_data, .tick = tick_global };

	send_info("Control mode changed to %d. Tick: %d", (int) mode, tick_global);

	BILBO_Message_Control_Event message(event_message_data);
	sendMessage(message);

	return true;

}
/* -------------------------------------------------------------------------------------- */
bilbo_control_data_t BILBO_Control::get_data() {
	return this->_data;
}
/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_external_input(bilbo_control_input_ext_t input) {
	if (this->_external_input_enabled) {
		this->_external_input = input;
		return true;
	} else {
		return false;
	}
}

/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::enable_external_input() {
	this->_external_input_enabled = true;
	return true;
}

/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::disable_external_input() {
	this->_external_input_enabled = false;
	return true;
}

/* -------------------------------------------------------------------------------------- */
void BILBO_Control::reset_external_input() {
	this->_external_input = { 0, 0 };
}
/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_velocity_command(
		bilbo_velocity_control_command_t command) {
	this->_velocity_command = command;
	return true;
}
/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::nudge(float distance_m) {
	// Recovery move: only from OFF mode, only when the robot is clearly lying
	// over. Rolls the wheels a bounded distance (motor position move) away from
	// the direction it fell. distance_m is the travel distance magnitude.
	if (this->status != bilbo_control_status_t::RUNNING) {
		return false;
	}
	if (this->mode != bilbo_control_mode_t::OFF) {
		send_error("Nudge only allowed in OFF mode. Tick: %d", tick_global);
		return false;
	}

	float theta = this->config.estimation->getState().theta;
	float abs_theta = (theta < 0.0f) ? -theta : theta;
	if (abs_theta < BILBO_NUDGE_MIN_THETA) {
		send_error("Nudge refused: |theta|=%d mrad below threshold (not lying over). Tick: %d",
				(int) (abs_theta * 1000), tick_global);
		return false;
	}

	// Move the body AWAY from the fall. theta > 0 (fell forward) rolls one way,
	// theta < 0 (fell backward) the other. If it moves toward the wall instead
	// of away on the bench, flip this single sign.
	float sign = (theta > 0.0f) ? -1.0f : 1.0f;
	// Travel distance (m) -> wheel revolutions via the model wheel circumference
	// (d = pi * WHEEL_DIAMETER * revolutions).
	const float pi_f = 3.14159265358979f;
	float magnitude_m = (distance_m < 0.0f) ? -distance_m : distance_m;
	float signed_rev = sign * magnitude_m / (pi_f * WHEEL_DIAMETER);

	bool ok = this->config.drive->nudge(signed_rev);
	if (ok) {
		send_info("Nudge: %d mm -> %d milli-rev (theta=%d mrad). Tick: %d",
				(int) (sign * magnitude_m * 1000), (int) (signed_rev * 1000),
				(int) (theta * 1000), tick_global);
	} else {
		send_error("Nudge rejected by drive (busy or not OK). Tick: %d", tick_global);
	}
	return ok;
}
/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_vic_enabled(bool state) {
	if (!this->control_config.vic_config.enabled) {
		return false;
	}
	this->vic_controller.set_enabled(state);
	this->_data.vic_enabled = state;

	control_event_message_data_t event_message_data_vic = { .event =
			control_event_t::VIC_CHANGED, .mode = mode, .data = this->_data,
			.tick = tick_global };
	BILBO_Message_Control_Event message_vic(event_message_data_vic);
	sendMessage(message_vic);
	return true;

}
/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_tic_enabled(bool state) {

	if (!this->control_config.tic_config.enabled) {
		return false;
	}

	this->tic_controller.set_enabled(state);
	this->_data.tic_enabled = state;

	control_event_message_data_t event_message_data_tic = { .event =
			control_event_t::TIC_CHANGED, .mode = mode, .data = this->_data,
			.tick = tick_global };
	BILBO_Message_Control_Event message_tic(event_message_data_tic);
	sendMessage(message_tic);
	return true;

}
/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_psi_enabled(bool state) {
	if (state == this->psi_controller.is_enabled()) {
		return true;
	}

	this->psi_controller.set_enabled(state);
	this->_data.psi_enabled = this->psi_controller.is_enabled();

	if (state) {
		send_info("PSI control enabled. Tick: %d", tick_global);
	} else {
		send_info("PSI control disabled. Tick: %d", tick_global);
	}

	control_event_message_data_t event_message_data_psi = { .event =
			control_event_t::PSI_CHANGED, .mode = mode, .data = this->_data,
			.tick = tick_global };
	BILBO_Message_Control_Event message_psi(event_message_data_psi);
	sendMessage(message_psi);
	return true;
}
/* -------------------------------------------------------------------------------------- */
bool BILBO_Control::set_psi_setpoint(float psi) {
	this->psi_controller.set_setpoint(psi);
	return true;
}
/* -------------------------------------------------------------------------------------- */
bilbo_control_output_t BILBO_Control::update() {

	bilbo_velocity_control_command_t velocity_command = { .v = 0, .psi_dot = 0 };
	bilbo_velocity_control_output_t velocity_output = { 0, 0 };

	bilbo_control_input_ext_t external_input = { 0, 0 };
	bilbo_balancing_control_input_t balancing_input = { 0, 0 };
	bilbo_balancing_control_output_t balancing_output = { 0, 0 };

	bilbo_control_output_t output = { 0, 0 };

	// Fetch the current dynamic state
	bilbo_estimation_state_t dynamic_state =
			this->config.estimation->getState();

	bilbo_position_state_t position_state =
			this->config.estimation->position_state;

	if (this->status != bilbo_control_status_t::RUNNING) {
		this->_set_torque(output);

	} else {  // Running mode

		switch (this->mode) {
		case bilbo_control_mode_t::OFF: {
			break;
		}
		case bilbo_control_mode_t::DIRECT: {
			// Direct control mode
			output.u_left = this->_external_input.u_left;
			output.u_right = this->_external_input.u_right;
			break;
		}
		case bilbo_control_mode_t::BALANCING: {
			// Balancing control mode

			// 1. Update the balancing controller
			external_input = { this->_external_input.u_left,
					this->_external_input.u_right };
			balancing_input = { external_input.u_left, external_input.u_right };
			balancing_output = this->balancing_control.update(dynamic_state,
					balancing_input);
			// 2. Update VIC
			float vic_output = this->vic_controller.update(dynamic_state.v,
					dynamic_state.theta);

			// 3. Update TIC
			float tic_output = this->tic_controller.update(dynamic_state.theta);

			// 4. Update PSI (differential: +left, -right)
			float psi_output = this->psi_controller.update(dynamic_state.psi);

			// 5. Combine outputs
			output.u_left = balancing_output.u_1 + vic_output + tic_output + psi_output;
			output.u_right = balancing_output.u_2 + vic_output + tic_output - psi_output;
			break;
		}
		case bilbo_control_mode_t::VELOCITY: {
			// Velocity control mode

			// 1. Update the velocity controller

			velocity_command = this->_velocity_command;

			velocity_output = this->velocity_control.update(velocity_command,
					dynamic_state.v, dynamic_state.psi_dot);

			// 2. Take this output as balancing input
			external_input = { velocity_output.u_l, velocity_output.u_r };
			balancing_input = { external_input.u_left, external_input.u_right };
			balancing_output = this->balancing_control.update(dynamic_state,
					balancing_input);

			// 3. Update TIC
			float tic_output = this->tic_controller.update(dynamic_state.theta);

			// 4. Combine outputs
			output.u_left = balancing_output.u_1 + tic_output;
			output.u_right = balancing_output.u_2 + tic_output;
			break;
		}
		case bilbo_control_mode_t::POSITION: {
			// Position control mode
			// All position and heading commands go through position_control

			// Update position controller (handles path following, turn-to-heading, drive-to-point)
			bilbo_position_control_output_t position_output =
					this->position_control.update(position_state, dynamic_state.v);

			velocity_command.v = position_output.v_cmd;
			velocity_command.psi_dot = position_output.psi_dot_cmd;

			// Update velocity controller with the command
			velocity_output = this->velocity_control.update(velocity_command,
					dynamic_state.v, dynamic_state.psi_dot);

			// Take velocity output as balancing input
			external_input = { velocity_output.u_l, velocity_output.u_r };
			balancing_input = { external_input.u_left, external_input.u_right };
			balancing_output = this->balancing_control.update(dynamic_state,
					balancing_input);

			// Update TIC
			float tic_output = this->tic_controller.update(dynamic_state.theta);

			// Combine outputs
			output.u_left = balancing_output.u_1 + tic_output;
			output.u_right = balancing_output.u_2 + tic_output;
			break;
		}
		}
	}

	output.u_left = limit(output.u_left, this->control_config.max_torque);
	output.u_right = limit(output.u_right, this->control_config.max_torque);

	this->_data.status = this->status;
	this->_data.mode = this->mode;
	this->_data.tic_enabled = this->tic_controller.is_enabled();
	this->_data.vic_enabled = this->vic_controller.is_active();
	this->_data.psi_enabled = this->psi_controller.is_active();
	this->_data.position_control_data = this->position_control.get_data();
	this->_data.velocity_command = velocity_command;
	this->_data.velocity_output = velocity_output;
	this->_data.input_ext = external_input;
	this->_data.balancing_output = balancing_output;
	this->_data.output = output;

	// Write the torque to the motors
	this->_set_torque(output);

	return output;
}
/* -------------------------------------------------------------------------------------- */
void BILBO_Control::_set_torque(bilbo_control_output_t output) {
	// Apply the torque to the motors
	bilbo_drive_input_t drive_input = { .torque_left = output.u_left,
			.torque_right = output.u_right };

	this->config.drive->setTorque(drive_input);
}
/* -------------------------------------------------------------------------------------- */
void stopControl() {
	if (control) {
		control->stop();
	}
}

/* -------------------------------------------------------------------------------------- */
void BILBO_Control::_on_tic_disabled() {
	this->_data.tic_enabled = false;
	control_event_message_data_t event_message_data_tic = { .event =
			control_event_t::TIC_CHANGED, .mode = mode, .data = this->_data,
			.tick = tick_global };
	BILBO_Message_Control_Event message_tic(event_message_data_tic);
	sendMessage(message_tic);
}

/* -------------------------------------------------------------------------------------- */
void BILBO_Control::_on_position_command_finished(uint8_t) {
	// Reset velocity control PID integrators when position control finishes/times out/aborts.
	// This prevents integrator windup from causing the robot to lean forward after reaching
	// its target position (especially noticeable on high-friction surfaces like carpet).
	this->velocity_control.reset();
}

/* -------------------------------------------------------------------------------------- */
/* POSITION CONTROL INTERFACE                                                             */
/* -------------------------------------------------------------------------------------- */

bool BILBO_Control::set_position_control_config(bilbo_position_control_config_t config) {
	return this->position_control.set_config(config);
}

bilbo_position_control_config_t BILBO_Control::get_position_control_config() {
	return this->position_control.get_config();
}

bool BILBO_Control::position_clear_path() {
	this->position_control.clear_path();
	return true;
}

bool BILBO_Control::position_add_path_point(path_point_t point) {
	return this->position_control.add_path_point(point.x, point.y);
}

bool BILBO_Control::position_add_path_points_batch(path_points_batch_t batch) {
	return this->position_control.add_path_points_batch(batch);
}

bool BILBO_Control::position_add_stop_index(uint16_t index) {
	return this->position_control.add_stop_index(index);
}

bool BILBO_Control::position_start_path(bilbo_path_start_cmd_t cmd) {
	if (this->mode != bilbo_control_mode_t::POSITION) {
		send_error("Cannot start position path when not in POSITION mode");
		return false;
	}

	return this->position_control.start_path(cmd);
}

void BILBO_Control::position_pause_path() {
	this->position_control.pause_path();
}

void BILBO_Control::position_resume_path() {
	this->position_control.resume_path();
}

void BILBO_Control::position_abort_path() {
	this->position_control.abort_path();
}

bilbo_path_state_t BILBO_Control::position_get_path_state() {
	return this->position_control.get_path_state();
}

bilbo_position_control_data_t BILBO_Control::position_get_data() {
	return this->position_control.get_data();
}

uint16_t BILBO_Control::position_get_path_point_count() {
	return this->position_control.get_path_point_count();
}

bool BILBO_Control::position_turn_to_heading(turn_to_heading_command_t cmd) {
	if (this->mode != bilbo_control_mode_t::POSITION) {
		send_error("Cannot turn to heading when not in POSITION mode");
		return false;
	}
	return this->position_control.turn_to_heading(cmd);
}

bool BILBO_Control::position_move_to_point(move_to_point_command_t cmd) {
	if (this->mode != bilbo_control_mode_t::POSITION) {
		send_error("Cannot move to point when not in POSITION mode");
		return false;
	}
	return this->position_control.move_to_point(cmd);
}

bool BILBO_Control::position_reset() {
	return this->position_control.reset();
}

void BILBO_Control::position_spi_path_received(uint16_t count) {
	if (this->spi_path_rx_buffer != nullptr) {
		this->position_control.spiPathReceived(this->spi_path_rx_buffer, count);
	}
}
