/*
 * firmware.cpp
 *
 * Main entry point for the BILBO firmware.
 *
 * This file contains the firmware lifecycle:
 *   firmware()    — spawns the firmware FreeRTOS task
 *   init()        — configures all modules (comm, sensors, estimation, control, drive, safety, ...)
 *   start()       — starts all modules and spawns the control task
 *   task()        — 100 Hz control loop (sequencer → control → logging)
 *   helperTask()  — background housekeeping (LEDs, debug output)
 *
 * The register map wiring (UART register protocol) is in firmware_registers.cpp.
 */

#include "main.h"
#include "firmware_c.h"
#include "firmware.hpp"
#include <stdio.h>

/* ================================================================
 * GLOBALS
 * ================================================================ */

BILBO_Firmware bilbo_firmware;

uint32_t tick_global = 0;

// DMA-accessible buffer for receiving path points via SPI
_RAM_D2 path_point_t path_rx_buffer[BILBO_POSITION_CONTROL_MAX_PATH_POINTS];

/* ================================================================
 * TASK SETUP
 * ================================================================ */

static const osThreadAttr_t firmware_task_attributes = {
		.name = "firmware",
		.stack_size = 8000 * 4,
		.priority = (osPriority_t) osPriorityNormal,
};

static const osThreadAttr_t control_task_attributes = {
		.name = "control",
		.stack_size = 4000 * 4,
		.priority = (osPriority_t) osPriorityNormal,
};

void firmware() {
	osThreadNew(start_firmware_task, (void*) &bilbo_firmware,
			&firmware_task_attributes);
}

void start_firmware_task(void *argument) {
	((BILBO_Firmware*) argument)->helperTask();
}

void start_firmware_control_task(void *argument) {
	((BILBO_Firmware*) argument)->task();
}

/* ================================================================
 * INIT — configure all modules
 * ================================================================ */

HAL_StatusTypeDef BILBO_Firmware::init() {

	// --- Board-level peripherals ---

	robot_control_init();
	robot_control_start();
	io_start();

	rc_rgb_led_status.setColor(120, 40, 0);  // Orange = startup
	rc_rgb_led_status.state(1);
	rc_buzzer.setConfig(800, 250, 1);
	rc_buzzer.start();
	osDelay(250);

	// --- Error handler ---

	bilbo_error_handler_config_t error_handler_config = {
			.firmware = this };
	this->error_handler.init(error_handler_config);

	// --- Communication (UART + SPI + Modbus) ---

	bilbo_communication_config_t comm_config = {
			.huart                    = BOARD_CM4_UART,
			.hspi                     = BOARD_SPI_CM4,
			.sample_notification_gpio = core_utils_GPIO(CM4_SAMPLE_NOTIFICATION_PORT,
			                                            CM4_SAMPLE_NOTIFICATION_PIN),
			.sequence_rx_buffer       = this->sequencer.rx_buffer,
			.len_sequence_buffer      = BILBO_SEQUENCE_BUFFER_SIZE,
			.path_rx_buffer           = (uint8_t*) path_rx_buffer,
			.len_path_buffer          = BILBO_POSITION_CONTROL_MAX_PATH_POINTS,
			.reset_uart_exti          = CM4_UART_RESET_EXTI,
			.modbus_huart             = BOARD_RS485_UART,
			.modbus_gpio_port         = BOARD_RS485_UART_EN_GPIOx,
			.modbus_gpio_pin          = BOARD_RS485_UART_EN_GPIO_PIN,
	};
	this->comm.init(comm_config);
	this->comm.start();

	// --- Sensors ---

	bilbo_sensors_config_t sensors_config = {
			.drive = &this->drive };
	this->sensors.init(sensors_config);

	// --- Estimation ---

	bilbo_estimation_init_config_t estimation_config = {
			.drive   = &this->drive,
			.sensors = &this->sensors };
	this->estimation.init(estimation_config);

	// --- Control ---

	bilbo_control_init_config_t control_config = {
			.estimation = &this->estimation,
			.drive      = &this->drive,
			.Ts         = 1.0f / BILBO_CONTROL_TASK_FREQ,
	};
	this->control.init(control_config);

	// Wire SPI path receive into position control
	this->control.spi_path_rx_buffer = path_rx_buffer;
	this->comm.callbacks.path_received.registerFunction(
			&this->control, &BILBO_Control::position_spi_path_received);

	// --- Motors ---

#ifdef BILBO_DRIVE_SIMPLEXMOTION_CAN
	simplexmotion_can_config_t config_motor_left = {
			.can = &this->comm.can,
			.id = 1, .direction = -1,
			.torque_limit = BILBO_MOTOR_TORQUE_LIMIT };
	this->motor_left = SimplexMotion_CAN();
	this->motor_left.init(config_motor_left);

	simplexmotion_can_config_t config_motor_right = {
			.can = &this->comm.can,
			.id = 2, .direction = 1,
			.torque_limit = BILBO_MOTOR_TORQUE_LIMIT };
	this->motor_right = SimplexMotion_CAN();
	this->motor_right.init(config_motor_right);
#endif

#ifdef BILBO_DRIVE_SIMPLEXMOTION_RS485
	simplexmotion_rs485_config_t config_motor_right = {
			.modbus = &this->comm.modbus,
			.id = 2, .direction = 1,
			.torque_limit = BILBO_MOTOR_TORQUE_LIMIT };
	this->motor_right.init(config_motor_right);

	simplexmotion_rs485_config_t config_motor_left = {
			.modbus = &this->comm.modbus,
			.id = 1, .direction = -1,
			.torque_limit = BILBO_MOTOR_TORQUE_LIMIT };
	this->motor_left.init(config_motor_left);
#endif

	// --- Drive ---

	bilbo_drive_config_t drive_config = {
			.type      = BILBO_DRIVE_TYPE,
			.torque_max = BILBO_MOTOR_TORQUE_LIMIT,
			.task_time  = BILBO_DRIVE_TASK_TIME };
	this->drive.init(drive_config, &this->motor_left, &this->motor_right);

	// --- Safety ---

	bilbo_supervisor_config_t supervisor_config = {
			.estimation      = &this->estimation,
			.drive           = &this->drive,
			.control         = &this->control,
			.communication   = &this->comm,
			.off_button      = &off_button,
			.max_wheel_speed = BILBO_SAFETY_MAX_WHEEL_SPEED,
	};
	this->supervisor.init(supervisor_config);

	// --- Sequencer ---

	bilbo_sequencer_config_t sequencer_config = {
			.control = &this->control,
			.comm    = &this->comm,
	};
	this->sequencer.init(sequencer_config);

	// --- Logging ---

	bilbo_logging_config_t logging_config = {
			.firmware      = this,
			.control       = &this->control,
			.estimation    = &this->estimation,
			.sensors       = &this->sensors,
			.drive         = &this->drive,
			.sequencer     = &this->sequencer,
			.error_handler = &this->error_handler,
	};
	this->logging.init(logging_config);

	this->debugData = bilbo_debug_sample_t { 0 };

	return HAL_OK;
}

/* ================================================================
 * START — launch all modules and spawn the control task
 * ================================================================ */

HAL_StatusTypeDef BILBO_Firmware::start() {
	this->sensors.start();
	this->estimation.start();

	HAL_StatusTypeDef status = this->drive.start();
	if (status) {
		while (true) { nop(); }
	}

	this->control.start();
	this->supervisor.start();
	this->sequencer.start();

	osThreadNew(start_firmware_control_task, (void*) &bilbo_firmware,
			&control_task_attributes);

	this->firmware_state = BILBO_FIRMWARE_STATE_RUNNING;
	return HAL_OK;
}

/* ================================================================
 * RESET — soft-restart without power cycle
 * ================================================================ */

bool BILBO_Firmware::reset() {
	this->firmware_state = BILBO_FIRMWARE_STATE_NONE;
	osDelay(20);

	this->comm.resetSPI();
	this->logging.reset();
	this->control.stop();
	osDelay(20);

	this->tick = 0;
	tick_global = 0;

	rc_buzzer.setConfig(900, 250, 1);
	rc_buzzer.start();

	this->firmware_state = BILBO_FIRMWARE_STATE_RUNNING;
	return true;
}

/* ================================================================
 * TASK — 100 Hz control loop
 * ================================================================ */

static elapsedMillis activityTimer;
static elapsedMillis infoTimer;

void BILBO_Firmware::task() {
	uint32_t osTick;
	uint32_t loop_time;

	while (true) {
		osTick = osKernelGetTickCount();

		// Activity LED heartbeat (250 ms toggle)
		if (activityTimer > 250) {
			activityTimer.reset();
			rc_activity_led.toggle();
		}

		// Periodic debug output (every 10 s)
		if (infoTimer >= 10000) {
			infoTimer.reset();
			send_debug("Firmware state: %d, Tick: %d",
					this->firmware_state, this->tick);
		}

		// State machine
		switch (this->firmware_state) {

		case BILBO_FIRMWARE_STATE_RUNNING:
			this->sequencer.update();
			this->control.update();

			sample_buffer_state = this->logging.collectSamples();
			if (sample_buffer_state == BILBO_LOGGING_BUFFER_FULL) {
				this->comm.provideSampleData(this->logging.sample_buffer);
			}

			rc_rgb_led_status.setColor(0, 60, 0);  // Green = running
			this->tick++;
			tick_global = this->tick;
			break;

		case BILBO_FIRMWARE_STATE_NONE:
			rc_rgb_led_status.setColor(2, 2, 2);   // Dim white = idle
			break;

		case BILBO_FIRMWARE_STATE_ERROR:
			rc_rgb_led_status.setColor(120, 0, 0);  // Red = error
			rc_led_strip.setColor({ 100, 0, 0 });
			break;

		default:
			rc_rgb_led_status.setColor(120, 0, 0);
			break;
		}

		// Overrun detection
		loop_time = osKernelGetTickCount() - osTick;
		if (loop_time > (1000.0 / (float) BILBO_CONTROL_TASK_FREQ)) {
			setError(BILBO_ERROR_CRITICAL, BILBO_ERROR_FIRMWARE_RACECONDITION);
			send_error("Loop time exceeded %d ms. Shutdown", loop_time);
			this->firmware_state = BILBO_FIRMWARE_STATE_ERROR;
		}

		osDelayUntil(osTick + (uint32_t) (1000.0 / (float) BILBO_CONTROL_TASK_FREQ));
	}
}

/* ================================================================
 * HELPER TASK — background housekeeping (LEDs, buzzer)
 * ================================================================ */

void BILBO_Firmware::helperTask() {
	HAL_StatusTypeDef status = this->init();
	if (status == HAL_ERROR) {
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

	rc_buzzer.setConfig(900, 250, 1);
	rc_buzzer.start();

	rc_rgb_led_side_1.setColor(0, 0, 0);
	rc_rgb_led_side_1.state(1);
	this->updateExternalLedStrip(bilbo_control_mode_t::OFF);

	while (true) {
		if (this->timer_control_mode_led >= 250) {
			this->timer_control_mode_led.reset();
		}
		osDelay(100);
	}
}

/* ================================================================
 * UTILITY FUNCTIONS
 * ================================================================ */

bilbo_logging_general_t BILBO_Firmware::getSample() {
	return { .state = this->firmware_state };
}

void BILBO_Firmware::setControlModeLed() {
	if (this->firmware_state == BILBO_FIRMWARE_STATE_RUNNING) {
		if (this->control.mode == bilbo_control_mode_t::OFF)
			rc_rgb_led_side_1.setColor(2, 2, 2);     // White = OFF
		else if (this->control.mode == bilbo_control_mode_t::BALANCING)
			rc_rgb_led_side_1.setColor(0, 70, 0);    // Green = balancing
		else if (this->control.mode == bilbo_control_mode_t::VELOCITY)
			rc_rgb_led_side_1.setColor(0, 0, 60);    // Blue = velocity
	} else if (this->firmware_state == BILBO_FIRMWARE_STATE_ERROR) {
		rc_rgb_led_side_1.setColor(100, 0, 0);       // Red = error
	}
}

void BILBO_Firmware::updateExternalLedStrip(bilbo_control_mode_t mode) {
	switch (mode) {
	case bilbo_control_mode_t::OFF:
		rc_led_strip.setColor({ 3, 3, 3 });    break;
	case bilbo_control_mode_t::BALANCING:
		rc_led_strip.setColor({ 0, 6, 0 });    break;
	case bilbo_control_mode_t::VELOCITY:
		rc_led_strip.setColor({ 0, 6, 6 });    break;
	case bilbo_control_mode_t::POSITION:
		rc_led_strip.setColor({ 5, 0, 5 });    break;
	default:
		break;
	}
}
