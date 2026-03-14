/*
 * firmware_registers.cpp
 *
 * Register map wiring for the BILBO firmware.
 *
 * Each entry binds a register address to a firmware variable or method,
 * making it accessible from the Raspberry Pi via the UART register protocol.
 * The register addresses are defined in firmware_addresses.h.
 *
 * Register naming convention:
 *   reg_<module>_<action>  →  REG_ADDRESS_<R|F|RW>_<MODULE>_<ACTION>
 *     R  = read-only variable
 *     F  = function call (may return a value)
 *     RW = read/write variable
 */

#include "firmware.hpp"

extern BILBO_Firmware bilbo_firmware;

/* ================================================================
 * SYSTEM / FIRMWARE  (0x01 – 0x0F)
 * ================================================================ */

core_utils_RegisterEntry<bilbo_firmware_state_t, void> reg_fw_state(
		&register_map, REG_ADDRESS_R_FIRMWARE_STATE,
		&bilbo_firmware.firmware_state);

core_utils_RegisterEntry<uint32_t, void> reg_fw_tick(
		&register_map, REG_ADDRESS_R_FIRMWARE_TICK,
		&bilbo_firmware.tick);

core_utils_RegisterEntry<bilbo_firmware_revision_t, void> reg_fw_rev(
		&register_map, REG_ADDRESS_R_FIRMWARE_REVISION,
		&bilbo_firmware.revision);

core_utils_RegisterEntry<bilbo_firmware_info_t, void> reg_fw_info(
		&register_map, REG_ADDRESS_R_FIRMWARE_INFO,
		&bilbo_firmware.firmware_info);

core_utils_RegisterEntry<void, buzzer_beep_struct_t> reg_fw_beep(
		&register_map, REG_ADDRESS_F_FIRMWARE_BEEP,
		&rc_buzzer, &RobotControl_Buzzer::beep);

core_utils_RegisterEntry<void, rgb_color_struct_t> reg_set_ext_led(
		&register_map, REG_ADDRESS_F_EXTERNAL_LED,
		&rc_led_strip, &RobotControl_LEDStrip::setColor);

core_utils_RegisterEntry<void, external_led_colors_struct_t> reg_set_all_ext_led(
		&register_map, REG_ADDRESS_F_ALL_EXTERNAL_LEDS,
		&rc_led_strip, &RobotControl_LEDStrip::setAllColors);

core_utils_RegisterEntry<uint8_t, uint8_t> reg_debug1(
		&register_map, REG_ADDRESS_RW_DEBUG_1,
		&bilbo_firmware.debugData.debug1);

core_utils_RegisterEntry<bool, void> reg_f_reset(
		&register_map, REG_ADDRESS_F_FIRMWARE_RESET,
		&bilbo_firmware, &BILBO_Firmware::reset);

core_utils_RegisterEntry<bool, void> reg_drive_reset(
		&register_map, REG_ADDRESS_F_DRIVE_RESET,
		&bilbo_firmware.drive, &BILBO_Drive::resetDrive);

/* ================================================================
 * CONTROL — CORE  (0x20 – 0x2F)
 * ================================================================ */

core_utils_RegisterEntry<bilbo_control_mode_t, void> reg_ctrl_mode(
		&register_map, REG_ADDRESS_R_CONTROL_MODE,
		&bilbo_firmware.control.mode);

core_utils_RegisterEntry<bool, bilbo_control_mode_t> reg_set_mode(
		&register_map, REG_ADDRESS_F_CONTROL_SET_MODE,
		&bilbo_firmware.control, &BILBO_Control::set_mode);

core_utils_RegisterEntry<bool, float[8]> reg_set_gain(
		&register_map, REG_ADDRESS_F_CONTROL_SET_K,
		&bilbo_firmware.control, &BILBO_Control::set_balancing_gain);

core_utils_RegisterEntry<bool, bilbo_control_input_ext_t> reg_set_balancing(
		&register_map, REG_ADDRESS_F_CONTROL_SET_BALANCING_INPUT,
		&bilbo_firmware.control, &BILBO_Control::set_external_input);

core_utils_RegisterEntry<bool, bilbo_velocity_control_command_t> reg_set_speed(
		&register_map, REG_ADDRESS_F_CONTROL_SET_SPEED_INPUT,
		&bilbo_firmware.control, &BILBO_Control::set_velocity_command);

core_utils_RegisterEntry<bilbo_control_config_t, void> reg_get_ctrl_conf(
		&register_map, REG_ADDRESS_F_CONTROL_GET_CONFIGURATION,
		&bilbo_firmware.control, &BILBO_Control::get_config);

core_utils_RegisterEntry<float, float> reg_max_speed(
		&register_map, REG_ADDRESS_RW_MAX_WHEEL_SPEED,
		&bilbo_firmware.supervisor.config.max_wheel_speed);

/* ================================================================
 * CONTROL — CONFIG & ENABLES  (0x30 – 0x3F)
 * ================================================================ */

core_utils_RegisterEntry<bool, pid_control_config_t> reg_set_vel_config_v(
		&register_map, REG_ADDRESS_F_CONTROL_SET_VELOCITY_CONFIG_V,
		&bilbo_firmware.control, &BILBO_Control::set_vc_pid_v);

core_utils_RegisterEntry<bool, feedforward_config_t> reg_set_vel_config_v_ff(
		&register_map, REG_ADDRESS_F_CONTROL_SET_VELOCITY_CONFIG_V_FF,
		&bilbo_firmware.control, &BILBO_Control::set_vc_ff_v);

core_utils_RegisterEntry<bool, pid_control_config_t> reg_set_vel_config_psidot(
		&register_map, REG_ADDRESS_F_CONTROL_SET_VELOCITY_CONFIG_PSIDOT,
		&bilbo_firmware.control, &BILBO_Control::set_vc_pid_psidot);

core_utils_RegisterEntry<bool, feedforward_config_t> reg_set_vel_config_psidot_ff(
		&register_map, REG_ADDRESS_F_CONTROL_SET_VELOCITY_CONFIG_PSIDOT_FF,
		&bilbo_firmware.control, &BILBO_Control::set_vc_ff_psidot);

core_utils_RegisterEntry<bool, bilbo_tic_config_t> reg_set_tic_config(
		&register_map, REG_ADDRESS_F_CONTROL_SET_TIC_CONFIG,
		&bilbo_firmware.control, &BILBO_Control::set_tic_config);

core_utils_RegisterEntry<bool, bilbo_vic_config_t> reg_set_vic_config(
		&register_map, REG_ADDRESS_F_CONTROL_SET_VIC_CONFIG,
		&bilbo_firmware.control, &BILBO_Control::set_vic_config);

core_utils_RegisterEntry<bool, float> reg_set_max_torque(
		&register_map, REG_ADDRESS_F_CONTROL_SET_MAX_TORQUE,
		&bilbo_firmware.control, &BILBO_Control::set_max_torque);

core_utils_RegisterEntry<bool, bool> reg_enable_tic(
		&register_map, REG_ADDRESS_F_ENABLE_TIC,
		&bilbo_firmware.control, &BILBO_Control::set_tic_enabled);

core_utils_RegisterEntry<bool, bool> reg_enable_vic(
		&register_map, REG_ADDRESS_F_ENABLE_VIC,
		&bilbo_firmware.control, &BILBO_Control::set_vic_enabled);

core_utils_RegisterEntry<bool, bool> reg_enable_vel_int_cont(
		&register_map, REG_ADDRESS_F_ENABLE_VELOCITY_INTEGRAL_CONTROL,
		&bilbo_firmware.control, &BILBO_Control::set_vic_enabled);

core_utils_RegisterEntry<bool, bilbo_psi_config_t> reg_set_psi_config(
		&register_map, REG_ADDRESS_F_CONTROL_SET_PSI_CONFIG,
		&bilbo_firmware.control, &BILBO_Control::set_psi_config);

core_utils_RegisterEntry<bool, bool> reg_enable_psi(
		&register_map, REG_ADDRESS_F_ENABLE_PSI,
		&bilbo_firmware.control, &BILBO_Control::set_psi_enabled);

core_utils_RegisterEntry<bool, float> reg_set_psi_setpoint(
		&register_map, REG_ADDRESS_F_SET_PSI_SETPOINT,
		&bilbo_firmware.control, &BILBO_Control::set_psi_setpoint);

/* ================================================================
 * SEQUENCER  (0x40 – 0x4F)
 * ================================================================ */

core_utils_RegisterEntry<bool, bilbo_sequencer_sequence_data_t> reg_load_seq(
		&register_map, REG_ADDRESS_F_SEQUENCE_LOAD,
		&bilbo_firmware.sequencer, &BILBO_Sequencer::loadSequence);

core_utils_RegisterEntry<bilbo_sequencer_sequence_data_t, void> reg_read_seq(
		&register_map, REG_ADDRESS_F_SEQUENCE_READ,
		&bilbo_firmware.sequencer, &BILBO_Sequencer::readSequence);

core_utils_RegisterEntry<bool, uint16_t> reg_start_seq(
		&register_map, REG_ADDRESS_F_SEQUENCE_START,
		&bilbo_firmware.sequencer, &BILBO_Sequencer::startSequence);

core_utils_RegisterEntry<void, void> reg_abort_seq(
		&register_map, REG_ADDRESS_F_SEQUENCE_STOP,
		&bilbo_firmware.sequencer, &BILBO_Sequencer::abortSequence);

/* ================================================================
 * ESTIMATION  (0x50 – 0x5F)
 * ================================================================ */

core_utils_RegisterEntry<bool, float> reg_set_theta_offset(
		&register_map, REG_ADDRESS_F_ESTIMATION_SET_THETA_OFFSET,
		&bilbo_firmware.estimation, &BILBO_Estimation::setThetaOffset);

core_utils_RegisterEntry<void, bilbo_position_state_t> reg_set_position_state(
		&register_map, REG_ADDRESS_F_ESTIMATION_SET_POSITION_STATE,
		&bilbo_firmware.estimation, &BILBO_Estimation::set_position_state);

core_utils_RegisterEntry<void, bilbo_position_state_t> reg_set_position_update(
		&register_map, REG_ADDRESS_F_ESTIMATION_SET_POSITION_UPDATE,
		&bilbo_firmware.estimation, &BILBO_Estimation::set_position_update);

core_utils_RegisterEntry<void, void> reg_estimation_reset(
		&register_map, REG_ADDRESS_F_ESTIMATION_RESET,
		&bilbo_firmware.estimation, &BILBO_Estimation::reset);

core_utils_RegisterEntry<velocity_lowpass_filter_config_t, void> reg_get_velocity_lpf(
		&register_map, REG_ADDRESS_F_ESTIMATION_GET_VELOCITY_LPF,
		&bilbo_firmware.estimation, &BILBO_Estimation::get_velocity_lpf_config);

core_utils_RegisterEntry<void, velocity_lowpass_filter_config_t> reg_set_velocity_lpf(
		&register_map, REG_ADDRESS_F_ESTIMATION_SET_VELOCITY_LPF,
		&bilbo_firmware.estimation, &BILBO_Estimation::set_velocity_lpf_config);

core_utils_RegisterEntry<psi_dot_lowpass_filter_config_t, void> reg_get_psidot_lpf(
		&register_map, REG_ADDRESS_F_ESTIMATION_GET_PSIDOT_LPF,
		&bilbo_firmware.estimation, &BILBO_Estimation::get_psi_dot_lpf_config);

core_utils_RegisterEntry<void, psi_dot_lowpass_filter_config_t> reg_set_psidot_lpf(
		&register_map, REG_ADDRESS_F_ESTIMATION_SET_PSIDOT_LPF,
		&bilbo_firmware.estimation, &BILBO_Estimation::set_psi_dot_lpf_config);

core_utils_RegisterEntry<theta_dot_lowpass_filter_config_t, void> reg_get_theta_dot_lpf(
		&register_map, REG_ADDRESS_F_ESTIMATION_GET_THETA_DOT_LPF,
		&bilbo_firmware.estimation, &BILBO_Estimation::get_theta_dot_lpf_config);

core_utils_RegisterEntry<void, theta_dot_lowpass_filter_config_t> reg_set_theta_dot_lpf(
		&register_map, REG_ADDRESS_F_ESTIMATION_SET_THETA_DOT_LPF,
		&bilbo_firmware.estimation, &BILBO_Estimation::set_theta_dot_lpf_config);

core_utils_RegisterEntry<bilbo_estimation_config_t, void> reg_get_estimation_config(
		&register_map, REG_ADDRESS_F_ESTIMATION_GET_CONFIG,
		&bilbo_firmware.estimation, &BILBO_Estimation::get_config);

core_utils_RegisterEntry<void, bilbo_estimation_config_t> reg_set_estimation_config(
		&register_map, REG_ADDRESS_F_ESTIMATION_SET_CONFIG,
		&bilbo_firmware.estimation, &BILBO_Estimation::set_config);

core_utils_RegisterEntry<void, bool> reg_set_dead_reckoning_enable(
		&register_map, REG_ADDRESS_F_ESTIMATION_SET_DEAD_RECKONING_ENABLE,
		&bilbo_firmware.estimation, &BILBO_Estimation::set_dead_reckoning_enable);

/* ================================================================
 * POSITION CONTROL  (0x60 – 0x6F)
 * ================================================================ */

core_utils_RegisterEntry<bool, bilbo_position_control_config_t> reg_position_set_config(
		&register_map, REG_ADDRESS_F_POSITION_SET_CONFIG,
		&bilbo_firmware.control, &BILBO_Control::set_position_control_config);

core_utils_RegisterEntry<bilbo_position_control_config_t, void> reg_position_get_config(
		&register_map, REG_ADDRESS_F_POSITION_GET_CONFIG,
		&bilbo_firmware.control, &BILBO_Control::get_position_control_config);

core_utils_RegisterEntry<bool, void> reg_position_clear_path(
		&register_map, REG_ADDRESS_F_POSITION_CLEAR_PATH,
		&bilbo_firmware.control, &BILBO_Control::position_clear_path);

core_utils_RegisterEntry<bool, path_point_t> reg_position_add_path_point(
		&register_map, REG_ADDRESS_F_POSITION_ADD_PATH_POINT,
		&bilbo_firmware.control, &BILBO_Control::position_add_path_point);

core_utils_RegisterEntry<bool, bilbo_path_start_cmd_t> reg_position_start_path(
		&register_map, REG_ADDRESS_F_POSITION_START_PATH,
		&bilbo_firmware.control, &BILBO_Control::position_start_path);

core_utils_RegisterEntry<void, void> reg_position_pause_path(
		&register_map, REG_ADDRESS_F_POSITION_PAUSE_PATH,
		&bilbo_firmware.control, &BILBO_Control::position_pause_path);

core_utils_RegisterEntry<void, void> reg_position_resume_path(
		&register_map, REG_ADDRESS_F_POSITION_RESUME_PATH,
		&bilbo_firmware.control, &BILBO_Control::position_resume_path);

core_utils_RegisterEntry<void, void> reg_position_abort_path(
		&register_map, REG_ADDRESS_F_POSITION_ABORT_PATH,
		&bilbo_firmware.control, &BILBO_Control::position_abort_path);

core_utils_RegisterEntry<bilbo_path_state_t, void> reg_position_path_state(
		&register_map, REG_ADDRESS_R_POSITION_PATH_STATE,
		&bilbo_firmware.control, &BILBO_Control::position_get_path_state);

core_utils_RegisterEntry<bilbo_position_control_data_t, void> reg_position_data(
		&register_map, REG_ADDRESS_R_POSITION_DATA,
		&bilbo_firmware.control, &BILBO_Control::position_get_data);

core_utils_RegisterEntry<uint16_t, void> reg_position_path_point_count(
		&register_map, REG_ADDRESS_R_POSITION_PATH_POINT_COUNT,
		&bilbo_firmware.control, &BILBO_Control::position_get_path_point_count);

core_utils_RegisterEntry<bool, uint16_t> reg_position_add_stop_index(
		&register_map, REG_ADDRESS_F_POSITION_ADD_STOP_INDEX,
		&bilbo_firmware.control, &BILBO_Control::position_add_stop_index);

core_utils_RegisterEntry<bool, path_points_batch_t> reg_position_add_path_batch(
		&register_map, REG_ADDRESS_F_POSITION_ADD_PATH_BATCH,
		&bilbo_firmware.control, &BILBO_Control::position_add_path_points_batch);

core_utils_RegisterEntry<bool, turn_to_heading_command_t> reg_position_turn_to_heading(
		&register_map, REG_ADDRESS_F_POSITION_TURN_TO_HEADING,
		&bilbo_firmware.control, &BILBO_Control::position_turn_to_heading);

core_utils_RegisterEntry<bool, move_to_point_command_t> reg_position_move_to_point(
		&register_map, REG_ADDRESS_F_POSITION_MOVE_TO_POINT,
		&bilbo_firmware.control, &BILBO_Control::position_move_to_point);

core_utils_RegisterEntry<bool, void> reg_position_reset(
		&register_map, REG_ADDRESS_F_POSITION_RESET,
		&bilbo_firmware.control, &BILBO_Control::position_reset);
