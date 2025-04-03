/*
 * firmware.cpp
 *
 *  Created on: Feb 13, 2023
 *      Author: lehmann_workstation
 *
 *  Description:
 *  Implementation of the TWIPR firmware control functions. This file defines
 *  the core logic for the firmware initialization, tasks, control mechanisms,
 *  and module integration for the TWIPR robot platform.
 */

#include "main.h"
#include "firmware_c.h"
#include "firmware.hpp"
#include <stdio.h>

/* Global Firmware Instance */
TWIPR_Firmware twipr_firmware;

/* Set the global tick */
uint32_t tick_global = 0;

/* Register Entries */

core_utils_RegisterEntry<bool, void> reg_f_reset(&register_map,
REG_ADDRESS_F_FIRMWARE_RESET, &twipr_firmware, &TWIPR_Firmware::reset);

/* Firmware State Register Entry */
core_utils_RegisterEntry<twipr_firmware_state_t, void> reg_fw_state(
		&register_map, REG_ADDRESS_R_FIRMWARE_STATE,
		&twipr_firmware.firmware_state);

/* Firmware Tick Register Entry */
core_utils_RegisterEntry<uint32_t, void> reg_fw_tick(&register_map,
REG_ADDRESS_R_FIRMWARE_TICK, &twipr_firmware.tick);

/* Firmware Revision Register Entry */
core_utils_RegisterEntry<twipr_firmware_revision_t, void> reg_fw_rev(
		&register_map, REG_ADDRESS_R_FIRMWARE_REVISION,
		&twipr_firmware.revision);

/* Firmware Beep Function Register Entry */
core_utils_RegisterEntry<void, buzzer_beep_struct_t> reg_fw_beep(&register_map,
REG_ADDRESS_F_FIRMWARE_BEEP, &rc_buzzer, &RobotControl_Buzzer::beep);

/* Board Revision Register Entry */
core_utils_RegisterEntry<uint8_t, void> reg_board_rev(&register_map,
REG_ADDRESS_R_BOARD_REVISION, &board_revision);

/* Max Wheel Speed Register Entry */
core_utils_RegisterEntry<float, float> reg_max_speed(&register_map,
REG_ADDRESS_RW_MAX_WHEEL_SPEED,
		&twipr_firmware.supervisor.config.max_wheel_speed);

/* External LED Function Register Entry */
core_utils_RegisterEntry<void, rgb_color_struct_t> reg_set_ext_led(
		&register_map, REG_ADDRESS_F_EXTERNAL_LED, &extender,
		&RobotControl_Extender::rgbLEDStrip_extern_setColor);

/* Debug 1 Flag Register Entry */
core_utils_RegisterEntry<uint8_t, uint8_t> reg_debug1(&register_map,
REG_ADDRESS_RW_DEBUG_1, &twipr_firmware.debugData.debug1);

/* Control */

/* Read Control Mode Register Entry */
core_utils_RegisterEntry<twipr_control_mode_t, void> reg_ctrl_mode(
		&register_map, REG_ADDRESS_R_CONTROL_MODE,
		&twipr_firmware.control.mode);

/* Set Control Mode Function Register Entry */
core_utils_RegisterEntry<uint8_t, twipr_control_mode_t> reg_set_mode(
		&register_map, REG_ADDRESS_F_CONTROL_SET_MODE, &twipr_firmware.control,
		&TWIPR_ControlManager::setMode);

/* Set Control Gain Function Register Entry */
core_utils_RegisterEntry<uint8_t, float[8]> reg_set_gain(&register_map,
REG_ADDRESS_F_CONTROL_SET_K, &twipr_firmware.control,
		&TWIPR_ControlManager::setBalancingGain);

/* Set Direct Input Register Entry */
core_utils_RegisterEntry<void, twipr_control_direct_input_t> reg_set_direct(
		&register_map, REG_ADDRESS_F_CONTROL_SET_DIRECT_INPUT,
		&twipr_firmware.control, &TWIPR_ControlManager::setDirectInput);

/* Set Balancing Input Register Entry */
core_utils_RegisterEntry<void, twipr_balancing_control_input_t> reg_set_balancing(
		&register_map, REG_ADDRESS_F_CONTROL_SET_BALANCING_INPUT,
		&twipr_firmware.control, &TWIPR_ControlManager::setBalancingInput);

/* Set Speed Input Register Entry */
core_utils_RegisterEntry<void, twipr_speed_control_input_t> reg_set_speed(
		&register_map, REG_ADDRESS_F_CONTROL_SET_SPEED_INPUT,
		&twipr_firmware.control, &TWIPR_ControlManager::setSpeed);

/* Set PID Forward Register Entry */
core_utils_RegisterEntry<uint8_t, float[3]> reg_set_pid_fwd(&register_map,
REG_ADDRESS_F_CONTROL_SET_FORWARD_PID, &twipr_firmware.control,
		&TWIPR_ControlManager::setVelocityControlForwardPID);

/* Set PID Turn Register Entry */
core_utils_RegisterEntry<uint8_t, float[3]> reg_set_pid_turn(&register_map,
REG_ADDRESS_F_CONTROL_SET_TURN_PID, &twipr_firmware.control,
		&TWIPR_ControlManager::setVelocityControlTurnPID);

/* Get Control Configuration Register Entry */
core_utils_RegisterEntry<twipr_control_configuration_t, void> reg_get_ctrl_conf(
		&register_map, REG_ADDRESS_F_CONTROL_GET_CONFIGURATION,
		&twipr_firmware.control,
		&TWIPR_ControlManager::getControlConfiguration);

/* Sequencer */

/* Load Sequence Function Register Entry */
core_utils_RegisterEntry<bool, twipr_sequencer_sequence_data_t> reg_load_seq(
		&register_map, REG_ADDRESS_F_SEQUENCE_LOAD, &twipr_firmware.sequencer,
		&TWIPR_Sequencer::loadSequence);

/* Read Sequence Data Register Entry */
core_utils_RegisterEntry<twipr_sequencer_sequence_data_t, void> reg_read_seq(
		&register_map, REG_ADDRESS_F_SEQUENCE_READ, &twipr_firmware.sequencer,
		&TWIPR_Sequencer::readSequence);

/* Start Sequence Function Register Entry */
core_utils_RegisterEntry<bool, uint16_t> reg_start_seq(&register_map,
REG_ADDRESS_F_SEQUENCE_START, &twipr_firmware.sequencer,
		&TWIPR_Sequencer::startSequence);

/* Abort Sequence Function Register Entry */
core_utils_RegisterEntry<void, void> reg_abort_seq(&register_map,
REG_ADDRESS_F_SEQUENCE_STOP, &twipr_firmware.sequencer,
		&TWIPR_Sequencer::abortSequence);


core_utils_RegisterEntry<bool, twipr_control_configuration_t> reg_set_control_config(&register_map,
		REG_ADDRESS_F_CONTROL_SET_CONFIGURATION, &twipr_firmware.control,
		&TWIPR_ControlManager::setControlConfiguration);


core_utils_RegisterEntry<bool, bool> reg_enable_vel_int_cont(&register_map,
		REG_ADRESS_F_ENABLE_VELOCITY_INTEGRAL_CONTROL, &twipr_firmware.control,
		&TWIPR_ControlManager::enableSpeedIntegralControl);


core_utils_RegisterEntry<bool, float> reg_set_theta_offset(&register_map,
		REG_ADDRESS_F_ESTIMATION_SET_THETA_OFFSET, &twipr_firmware.estimation,
		&TWIPR_Estimation::setThetaOffset);




/* Thread Attributes for Firmware and Control Tasks */
const osThreadAttr_t firmware_task_attributes = { .name = "firmware",
		.stack_size = 2560 * 4, .priority = (osPriority_t) osPriorityNormal, };

const osThreadAttr_t control_task_attributes = { .name = "control",
		.stack_size = 2560 * 4, .priority = (osPriority_t) osPriorityNormal, };

elapsedMillis activityTimer;
elapsedMillis infoTimer;

/**
 * @brief Initializes and starts the firmware task.
 *
 * This is the entry point from the main function that spawns the firmware task.
 */
void firmware() {
	osThreadNew(start_firmware_task, (void*) &twipr_firmware,
			&firmware_task_attributes);
}

/**
 * @brief Task wrapper to execute the firmware's main task function.
 * @param argument Pointer to the firmware object.
 *
 * This function casts the argument to a TWIPR_Firmware pointer and calls the helperTask.
 */
void start_firmware_task(void *argument) {
	TWIPR_Firmware *firmware = (TWIPR_Firmware*) argument;
	// Start the helper task (core firmware loop)
	firmware->helperTask();
}

/**
 * @brief Constructor for TWIPR_Firmware.
 *
 * Constructor logic can be extended if necessary.
 */
TWIPR_Firmware::TWIPR_Firmware() {
	// Currently empty - add initialization if needed
}

/**
 * @brief Main firmware task logic.
 *
 * Initializes firmware components, provides feedback via buzzer and LEDs, then
 * enters the main loop for periodic control tasks.
 */
void TWIPR_Firmware::helperTask() {
	// Initialize firmware modules and configurations
	HAL_StatusTypeDef status;
	status = this->init();
	if (status == HAL_ERROR) {
		// Halt if initialization fails
		setError(BILBO_ERROR_CRITICAL, BILBO_ERROR_INIT);
		send_error("Error during initialization");
		return;
	}

	status = this->start();
	if (status == HAL_ERROR) {
		setError(BILBO_ERROR_CRITICAL, BILBO_ERROR_START);
		send_error("Error during starting");
		return;
	}

	// Signal successful initialization with a beep
	rc_buzzer.setConfig(900, 250, 1);
	rc_buzzer.start();

	// Initialize LED states
	rc_rgb_led_side_1.setColor(0, 0, 0);
	rc_rgb_led_side_1.state(1);

	extender.rgbLEDStrip_extern_setColor( { .red = 2, .green = 2, .blue = 2 });

	elapsedMillis debug_timer;

	// Main task loop
	while (true) {
		// Update control mode LED if timer exceeds 250ms
		if (this->timer_control_mode_led > 250) {
			this->timer_control_mode_led.reset();
			this->setControlModeLed();
		}

		// Debug timer reset every 1000ms
		if (debug_timer >= 1000) {
//        	info("STM32 Tick: %d", tick_global);
			debug_timer.reset();
		}
		osDelay(100);
	}
}

/**
 * @brief Initializes all firmware modules and configurations.
 *
 * Sets up robot control, peripherals, communication, sensors, estimation,
 * control, drive, safety, sequencer, and logging modules.
 *
 * @return HAL_OK if initialization succeeds, or an error status.
 */
HAL_StatusTypeDef TWIPR_Firmware::init() {
	// Initialize robot control and peripheral modules
	robot_control_init();
	robot_control_start();
	io_start();

	// Setup RGB LED and buzzer for feedback
	rc_rgb_led_status.setColor(120, 40, 0); // Orange color indicates startup
	rc_rgb_led_status.state(1);
	rc_buzzer.setConfig(800, 250, 1);
	rc_buzzer.start();
	osDelay(250); // Allow peripherals to initialize

	bilbo_error_handler_config_t error_handler_config = { .firmware = this };
	this->error_handler.init(error_handler_config);

	// Communication module configuration
	twipr_communication_config_t twipr_comm_config = { .huart = BOARD_CM4_UART,
			.hspi = BOARD_SPI_CM4, .sample_notification_gpio = core_utils_GPIO(
			CM4_SAMPLE_NOTIFICATION_PORT, CM4_SAMPLE_NOTIFICATION_PIN),
			.sequence_rx_buffer = this->sequencer.rx_buffer,
			.len_sequence_buffer = TWIPR_SEQUENCE_BUFFER_SIZE,
			.reset_uart_exti = CM4_UART_RESET_EXTI, .modbus_huart =
			BOARD_RS485_UART, .modbus_gpio_port =
			BOARD_RS485_UART_EN_GPIOx, .modbus_gpio_pin =
			BOARD_RS485_UART_EN_GPIO_PIN };
	this->comm.init(twipr_comm_config);
	this->comm.start();

	// Sensors initialization
	twipr_sensors_config_t twipr_sensors_config = { .drive = &this->drive };
	this->sensors.init(twipr_sensors_config);

	// Estimation module configuration
	twipr_estimation_config_t twipr_estimation_config = { .drive = &this->drive,
			.sensors = &this->sensors};
	this->estimation.init(twipr_estimation_config);

	// Control module initialization
	twipr_control_init_config_t twipr_control_config = { .estimation =
			&this->estimation, .drive = &this->drive, .max_torque =
	TWIPR_CONTROL_MAX_TORQUE, .freq = TWIPR_CONTROL_TASK_FREQ, };
	this->control.init(twipr_control_config);

	// Drive configuration

	// ------------------------------------------------------------------
#ifdef BILBO_DRIVE_SIMPLEXMOTION_CAN
	// Initialize both motors
	simplexmotion_can_config_t config_motor_left = { .can = &this->comm.can,
			.id = 1, .direction = -1, .torque_limit = 0.4 };

	this->motor_left = SimplexMotion_CAN();
	this->motor_left.init(config_motor_left);

	simplexmotion_can_config_t config_motor_right = { .can = &this->comm.can,
			.id = 2, .direction = 1, .torque_limit = 0.4 };

	this->motor_right = SimplexMotion_CAN();
	this->motor_right.init(config_motor_right);

#endif

	// ------------------------------------------------------------------
#ifdef BILBO_DRIVE_SIMPLEXMOTION_RS485
    simplexmotion_rs485_config_t config_motor_right =  {
        		.modbus = &this->comm.modbus,
    			.id = 2,
    			.direction = 1,
    			.torque_limit = 0.4
        };
    this->motor_right.init(config_motor_right);

    simplexmotion_rs485_config_t config_motor_left =  {
    		.modbus = &this->comm.modbus,
			.id = 1,
			.direction = -1,
			.torque_limit = 0.4
    };
    this->motor_left.init(config_motor_left);


	#endif

	// ------------------------------------------------------------------

	bilbo_drive_config_t drive_config = { .type = BILBO_DRIVE_TYPE,
			.torque_max = 0.4, .task_time = BILBO_DRIVE_TASK_TIME };

	this->drive.init(drive_config, &this->motor_left, &this->motor_right);

	// Safety module initialization
	twipr_supervisor_config_t supervisor_config = { .estimation =
			&this->estimation, .drive = &this->drive, .control = &this->control,
			.communication = &this->comm, .off_button = &off_button,
			.max_wheel_speed = TWIPR_SAFETY_MAX_WHEEL_SPEED, };
	this->supervisor.init(supervisor_config);

	// Sequencer module setup
	twipr_sequencer_config_t sequencer_config = { .control = &this->control,
			.comm = &this->comm, };
	this->sequencer.init(sequencer_config);

	// Logging module configuration
	twipr_logging_config_t logging_config = { .firmware = this, .control =
			&this->control, .estimation = &this->estimation, .sensors =
			&this->sensors, .sequencer = &this->sequencer, .error_handler =
			&this->error_handler };
	this->logging.init(logging_config);

	// Initialize debug data
	this->debugData = twipr_debug_sample_t { 0 };
	this->debugData.debug2 = 55;

	return HAL_OK;
}

/**
 * @brief Starts the firmware components and control tasks.
 *
 * This function starts sensors, estimation, drive, control, safety,
 * sequencer modules, and creates the control task.
 *
 * @return HAL_OK if all modules start successfully.
 */
HAL_StatusTypeDef TWIPR_Firmware::start() {
	// Start sensors and estimation modules
	this->sensors.start();
	this->estimation.start();

	HAL_StatusTypeDef status = this->drive.start();
	if (status) {
		while (true) {
			nop();
		}
	}

	// Start control and safety modules
	this->control.start();

	this->supervisor.start();

	// Start sequencer module
	this->sequencer.start();

	// Create the control task thread
	osThreadNew(start_firmware_control_task, (void*) &twipr_firmware,
			&control_task_attributes);

	// Set firmware state to running
	this->firmware_state = TWIPR_FIRMWARE_STATE_RUNNING;
	return HAL_OK;
}

bool TWIPR_Firmware::reset() {

	this->firmware_state = TWIPR_FIRMWARE_STATE_NONE;
	osDelay(20);

	this->comm.resetSPI();
	this->logging.reset();
	this->control.stop();
	osDelay(20);
	this->tick = 0;
	tick_global = 0;

	rc_buzzer.setConfig(900, 250, 1);
	rc_buzzer.start();

	this->firmware_state = TWIPR_FIRMWARE_STATE_RUNNING;

	return true;
}

/**
 * @brief Main control task function for the firmware.
 *
 * Ensures periodic execution of control logic and handles errors.
 * It measures loop time and triggers error handling if the loop overruns.
 */
void TWIPR_Firmware::task() {

	uint32_t osTick;  // Current system tick
	uint32_t loop_time;    // Duration of one control loop

	while (true) {
		osTick = osKernelGetTickCount();  // Record start tick

		// Toggle activity LED every 250ms
		if (activityTimer > 250) {
			activityTimer.reset();
			rc_activity_led.toggle();
		}
		if (infoTimer >= 10000) {
			infoTimer.reset();
			send_debug("Firmware state: %d, Tick: %d", this->firmware_state,
					this->tick);
		}

		switch (this->firmware_state) {

		case TWIPR_FIRMWARE_STATE_RUNNING: {

//			// Check safety module for errors
//			bilbo_error_type_t error = this->supervisor.check();
//
//			if (error != TWIPR_ERROR_NONE) {
//				this->errorHandler(error);
//			}

			// Update sequencer
			this->sequencer.update();

			// Update Control Module
			this->control.update();

			// Collect and send logging samples if buffer is full
			sample_buffer_state = this->logging.collectSamples();

			if (sample_buffer_state == TWIPR_LOGGING_BUFFER_FULL) {
				this->comm.provideSampleData(this->logging.sample_buffer);
			}

			// Set status LED to green indicating normal operation
			rc_rgb_led_status.setColor(0, 60, 0);

			// Increment firmware tick counter
			this->tick++;
			tick_global = this->tick;

			break;
		}
		case TWIPR_FIRMWARE_STATE_NONE: {
			rc_rgb_led_status.setColor(2, 2, 2);
			break;
		}

		case TWIPR_FIRMWARE_STATE_ERROR: {
			// Set LED to red in error state
			rc_rgb_led_status.setColor(120, 0, 0);
			extender.rgbLEDStrip_extern_setColor( { 100, 0, 0 });
			break;
		}
		default: {
			// Fallback for undefined states
			rc_rgb_led_status.setColor(120, 0, 0);
			break;
		}


		}

		// Calculate elapsed time for the loop
		loop_time = osKernelGetTickCount() - osTick;

		// If loop time exceeds allowed period, flag an error
		if (loop_time > (1000.0 / (float) TWIPR_CONTROL_TASK_FREQ)) {
			setError(BILBO_ERROR_MAJOR, BILBO_ERROR_FIRMWARE_RACECONDITION);
			send_error("Loop time exceeded %d ms. Shutdown", loop_time);
			this->firmware_state = TWIPR_FIRMWARE_STATE_ERROR;
		}

		// Delay until next cycle
		osDelayUntil(
				osTick + (uint32_t) (1000.0 / (float) TWIPR_CONTROL_TASK_FREQ));
	}
}

/**
 * @brief Wrapper function to start the control task.
 *
 * This function casts the argument to a firmware pointer and calls controlTask().
 * @param argument Pointer to the firmware object.
 */
void start_firmware_control_task(void *argument) {
	TWIPR_Firmware *firmware = (TWIPR_Firmware*) argument;
	firmware->task();
}

/**
 * @brief Retrieves a logging sample with the current firmware state.
 *
 * @return A logging structure containing the current tick, state, and error code.
 */
twipr_logging_general_t TWIPR_Firmware::getSample() {
	twipr_logging_general_t sample = { .tick = this->tick, .state =
			this->firmware_state };
	return sample;
}

/**
 * @brief Updates the side LED color based on the current control mode.
 *
 * Changes the LED color to represent:
 * - Red: OFF mode
 * - Amber: Balancing mode
 * - Green: Velocity mode
 */
void TWIPR_Firmware::setControlModeLed() {
	if (this->firmware_state == TWIPR_FIRMWARE_STATE_RUNNING) {
		if (this->control.mode == TWIPR_CONTROL_MODE_OFF) {
			rc_rgb_led_side_1.setColor(2, 2, 2); // White for OFF mode
		} else if (this->control.mode == TWIPR_CONTROL_MODE_BALANCING) {
			rc_rgb_led_side_1.setColor(0, 70, 0); // Amber for balancing
		} else if (this->control.mode == TWIPR_CONTROL_MODE_VELOCITY) {
			rc_rgb_led_side_1.setColor(0, 0, 60); // Blue
		}
	} else if (this->firmware_state == TWIPR_FIRMWARE_STATE_ERROR) {
		rc_rgb_led_side_1.setColor(100, 0, 00); // Red
	}

}
