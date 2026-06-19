#include "bilbo_drive.h"
#include "modbus_rtu.h"
#include "firmware_settings.h"
#include "robot-control_board.h"
#ifdef BILBO_DRIVE_SIMPLEXMOTION_RS485
#include "simplexmotion_rs485.h"
#endif

static const char* sm_mode_name(simplexmotion_mode_t mode) {
	switch (mode) {
	case SM_MODE_OFF:            return "Off";
	case SM_MODE_RESET:          return "Reset";
	case SM_MODE_SHUTDOWN:       return "Shutdown";
	case SM_MODE_QUICKSTOP:      return "Quickstop";
	case SM_MODE_FIRMWARE:       return "Firmware";
	case SM_MODE_PWM:            return "PWM";
	case SM_MODE_FREEWHEEL:      return "Freewheel";
	case SM_MODE_POSITION:       return "Position";
	case SM_MODE_POSITION_RAMP:  return "PositionRamp";
	case SM_MODE_SPEED:          return "Speed";
	case SM_MODE_SPEED_RAMP:     return "SpeedRamp";
	case SM_MODE_SPEED_LOW:      return "SpeedLow";
	case SM_MODE_SPEED_LOW_RAMP: return "SpeedLowRamp";
	case SM_MODE_TORQUE:         return "Torque";
	case SM_MODE_BEEP:           return "Beep";
	case SM_MODE_HOMING:         return "Homing";
	case SM_MODE_COGGING:        return "Cogging";
	case SM_MODE_UNKNOWN:        return "Unknown";
	default:                     return "Unknown";
	}
}

static const osThreadAttr_t drive_task_attributes = { .name = "drive",
		.stack_size = 2000 * 4, .priority = (osPriority_t) osPriorityNormal, };

osSemaphoreId_t speed_semaphore;
osSemaphoreId_t voltage_semaphore;
osSemaphoreId_t torque_semaphore;

BILBO_Drive::BILBO_Drive() {

}

HAL_StatusTypeDef BILBO_Drive::init(bilbo_drive_config_t config,
		BILBO_Drive_Motor *motor_left, BILBO_Drive_Motor *motor_right) {

	this->config = config;
	this->motor_left = motor_left;
	this->motor_right = motor_right;

	speed_semaphore = osSemaphoreNew(1, 1, NULL);
	voltage_semaphore = osSemaphoreNew(1, 1, NULL);
	torque_semaphore = osSemaphoreNew(1, 1, NULL);

	return HAL_OK;
}

/* ======================================================================= */
HAL_StatusTypeDef BILBO_Drive::start() {

	HAL_StatusTypeDef status;

	status = this->motor_left->checkMotor();

	if (status) {
		return HAL_ERROR;
	}

	osDelay(100);
	status = this->motor_right->checkMotor();

	if (status) {
		return HAL_ERROR;
	}

#if ENABLE_MOTOR_SHUTDOWN_LINE
	// Initialize motor shutdown safety line: drive HIGH = motors allowed to run.
	// CubeMX should configure this pin as push-pull output with pullup, default HIGH.
	HAL_GPIO_WritePin(MOTOR_SHUTDOWN_LINE_LEFT_PORT, MOTOR_SHUTDOWN_LINE_LEFT_PIN, GPIO_PIN_SET);
	HAL_GPIO_WritePin(MOTOR_SHUTDOWN_LINE_RIGHT_PORT, MOTOR_SHUTDOWN_LINE_RIGHT_PIN, GPIO_PIN_SET);
#endif

	HAL_StatusTypeDef start_left = this->motor_left->start();
	HAL_StatusTypeDef start_right = this->motor_right->start();
	if (start_left != HAL_OK || start_right != HAL_OK) {
		// Motor did not enter torque mode (e.g. stuck in BEEP). Surface it —
		// otherwise every setTorque() in the drive task fails silently.
		send_error("Motor start failed to enter torque mode (L=%d R=%d)",
				start_left, start_right);
	}

	osThreadNew(startDriveTask, (void*) this, &drive_task_attributes);

	this->status = BILBO_DRIVE_STATUS_OK;
	return HAL_OK;

}

/* ======================================================================= */
HAL_StatusTypeDef BILBO_Drive::stop() {
	bilbo_drive_input_t input = { 0 };
	this->setTorque(input);
	this->motor_left->stop();
	this->motor_right->stop();

	return HAL_OK;
}

/* ======================================================================= */
bool BILBO_Drive::resetDrive() {
	if (this->status != BILBO_DRIVE_STATUS_ERROR) {
		send_info("Drive reset requested but not in error state");
		return true;
	}

	// Signal the drive task to perform the reset from within its thread
	// (avoids bus contention — the task owns the CAN/RS485 bus)
	this->_reset_requested = true;

	// Wait for the task to process the reset (with timeout).
	// The reset may retry up to 3 times with bus resets between attempts.
	uint32_t timeout = 3000; // ms
	uint32_t start = osKernelGetTickCount();
	while (this->_reset_requested && (osKernelGetTickCount() - start) < timeout) {
		osDelay(5);
	}

	if (this->status == BILBO_DRIVE_STATUS_OK) {
		drive_event_message_data_t event_data = { .status = (uint8_t)BILBO_DRIVE_STATUS_OK, .tick = tick_global };
		BILBO_Message_Drive_Event message(event_data);
		sendMessage(message);
		send_info("Drive reset successful (tick %lu)", (unsigned long)tick_global);
		return true;
	} else {
		send_error("Drive reset failed (timeout or motor restart failed)");
		return false;
	}
}

/* ======================================================================= */
HAL_StatusTypeDef BILBO_Drive::emergencyStop() {
	// Only set the flag here — do NOT call CAN/RS485 directly.
	// The drive task owns the bus and will execute the actual
	// motor shutdown on its next iteration.
	this->status = BILBO_DRIVE_STATUS_ERROR;
	this->motor_left->emergencyStop();
	osDelay(1);
	this->motor_right->emergencyStop();

	drive_event_message_data_t event_data = { .status = (uint8_t)BILBO_DRIVE_STATUS_ERROR, .tick = tick_global };
	BILBO_Message_Drive_Event message(event_data);
	sendMessage(message);

	return HAL_OK;
}

/* ======================================================================= */
bilbo_drive_speed_t BILBO_Drive::getSpeed() {
	osSemaphoreAcquire(speed_semaphore, portMAX_DELAY);
	bilbo_drive_speed_t speed = this->_speed;
	osSemaphoreRelease(speed_semaphore);
	return speed;
}

/* ======================================================================= */
void BILBO_Drive::setTorque(bilbo_drive_input_t input) {
	osSemaphoreAcquire(torque_semaphore, portMAX_DELAY);
	this->_input = input;
	osSemaphoreRelease(torque_semaphore);
}

/* ======================================================================= */
float BILBO_Drive::getVoltage() {
	osSemaphoreAcquire(voltage_semaphore, portMAX_DELAY);
	float voltage = this->_voltage;
	osSemaphoreRelease(voltage_semaphore);
	return voltage;
}

/* ======================================================================= */
void BILBO_Drive::task() {
	uint32_t current_tick = 0;
	uint32_t ticks_loop = 0;
	elapsedMillis voltage_timer = 0;

	float motor_left_speed = 0;
	float motor_left_voltage = 0;
	float motor_left_torque = 0;

	float motor_right_speed = 0;
	float motor_right_torque = 0;

	HAL_StatusTypeDef status = HAL_ERROR;

#ifdef BILBO_DRIVE_SIMPLEXMOTION_RS485
	uint8_t taskmode = 0;
	uint32_t consecutive_errors = 0;
	elapsedMillis mode_check_timer = 0;

	while (true){
		current_tick = osKernelGetTickCount();
		if (this->status == BILBO_DRIVE_STATUS_OK) {
			bool cycle_ok = true;

#if BILBO_DRIVE_WATCHDOG_ENABLE
			this->motor_left->feedWatchdog();
			osDelay(1);
			this->motor_right->feedWatchdog();
			osDelay(1);
#endif

			// Periodically read motor modes (~every 2s)
			if (mode_check_timer > 2000) {
				mode_check_timer.reset();
				simplexmotion_mode_t mode_left, mode_right;

				if (this->motor_left->readMotorMode(mode_left) == HAL_OK) {
					if (mode_left != this->_motor_mode_left) {
						send_info("Motor left mode changed: %s -> %s",
								sm_mode_name(this->_motor_mode_left), sm_mode_name(mode_left));
						this->_motor_mode_left = mode_left;
					}
				}
				osDelay(1);
				if (this->motor_right->readMotorMode(mode_right) == HAL_OK) {
					if (mode_right != this->_motor_mode_right) {
						send_info("Motor right mode changed: %s -> %s",
								sm_mode_name(this->_motor_mode_right), sm_mode_name(mode_right));
						this->_motor_mode_right = mode_right;
					}
				}
			}

			if (taskmode == 0){

				HAL_StatusTypeDef status_speed_left = this->motor_left->readSpeed(motor_left_speed);
				if (status_speed_left != HAL_OK) {
					this->motor_left->resetBus();
					osDelay(1);
					status_speed_left = this->motor_left->readSpeed(motor_left_speed);
				}

				osDelay(1);

				HAL_StatusTypeDef status_speed_right = this->motor_right->readSpeed(motor_right_speed);
				if (status_speed_right != HAL_OK) {
					this->motor_right->resetBus();
					osDelay(1);
					status_speed_right = this->motor_right->readSpeed(motor_right_speed);
				}

				if (status_speed_left == HAL_OK && status_speed_right == HAL_OK){
					osSemaphoreAcquire(speed_semaphore, portMAX_DELAY);
					this->_speed.left = motor_left_speed;
					this->_speed.right = motor_right_speed;
					osSemaphoreRelease(speed_semaphore);
				} else {
					cycle_ok = false;
				}

				taskmode = 1;
			} else {
				osSemaphoreAcquire(torque_semaphore, portMAX_DELAY);
				motor_left_torque = this->_input.torque_left;
				motor_right_torque = this->_input.torque_right;
				osSemaphoreRelease(torque_semaphore);

				HAL_StatusTypeDef status_torque_left = this->motor_left->setTorque(motor_left_torque);
				if (status_torque_left != HAL_OK) {
					this->motor_left->resetBus();
					osDelay(1);
					status_torque_left = this->motor_left->setTorque(motor_left_torque);
				}

				osDelay(1);

				HAL_StatusTypeDef status_torque_right = this->motor_right->setTorque(motor_right_torque);
				if (status_torque_right != HAL_OK) {
					this->motor_right->resetBus();
					osDelay(1);
					status_torque_right = this->motor_right->setTorque(motor_right_torque);
				}

				if (status_torque_left != HAL_OK || status_torque_right != HAL_OK){
					cycle_ok = false;
				}

				taskmode = 0;
			}

			if (cycle_ok) {
				consecutive_errors = 0;
			} else {
				consecutive_errors++;
				if (consecutive_errors >= BILBO_DRIVE_MAX_CONSECUTIVE_ERRORS) {
					setError(BILBO_ERROR_MAJOR, BILBO_ERROR_MOTOR_COMM);
					send_error("RS485 motor comm failed %d consecutive times",
							BILBO_DRIVE_MAX_CONSECUTIVE_ERRORS);
					this->status = BILBO_DRIVE_STATUS_ERROR;
				}
			}

		} else if (this->status == BILBO_DRIVE_STATUS_ERROR) {
			if (this->_reset_requested) {
				SimplexMotion_RS485* ml = static_cast<SimplexMotion_RS485*>(this->motor_left);
				SimplexMotion_RS485* mr = static_cast<SimplexMotion_RS485*>(this->motor_right);

				HAL_StatusTypeDef s1 = HAL_ERROR;
				HAL_StatusTypeDef s2 = HAL_ERROR;

				for (int attempt = 0; attempt < 3 && !(s1 == HAL_OK && s2 == HAL_OK); attempt++) {
					// Reset Modbus handlers — kills the task, recreates it
					// with fresh UART/DMA. Only once: both motors share
					// the same bus so resetAllModbusHandlers covers both.
					ml->resetBus();
					osDelay(100); // let new Modbus task start + DMA settle

					// Send RESET mode to clear motor fault/quickstop state.
					// Ignore return: RESET is transient (motor goes to OFF),
					// so the readback verify fails, but the command is sent.
					ml->setMode(SIMPLEXMOTION_RS485_MODE_RESET);
					osDelay(10);
					mr->setMode(SIMPLEXMOTION_RS485_MODE_RESET);
					osDelay(100); // let motors complete reset cycle

					s1 = ml->start();
					osDelay(10);
					s2 = mr->start();

					if (!(s1 == HAL_OK && s2 == HAL_OK)) {
						send_error("Drive reset attempt %d failed (L=%d R=%d)", attempt + 1, s1, s2);
					}
				}

				if (s1 == HAL_OK && s2 == HAL_OK) {
					consecutive_errors = 0;
					osSemaphoreAcquire(speed_semaphore, portMAX_DELAY);
					this->_speed = {0, 0};
					osSemaphoreRelease(speed_semaphore);
					this->status = BILBO_DRIVE_STATUS_OK;
				} else {
					send_error("Drive reset failed after 3 attempts");
				}
				this->_reset_requested = false;
			} else {
				this->motor_left->emergencyStop();
				osDelay(1);
				this->motor_right->emergencyStop();
			}
		}

		osDelayUntil(current_tick + this->config.task_time);
	}
#endif
#ifdef BILBO_DRIVE_SIMPLEXMOTION_CAN
	osDelay(100);
	uint32_t consecutive_errors = 0;
	elapsedMillis mode_check_timer = 0;

	while (true) {
		current_tick = osKernelGetTickCount();

		if (this->status == BILBO_DRIVE_STATUS_OK) {

			bool cycle_ok = true;

#if BILBO_DRIVE_WATCHDOG_ENABLE
			this->motor_left->feedWatchdog();
			osDelay(2);
			this->motor_right->feedWatchdog();
			osDelay(2);
#endif

			// Read the voltage (non-critical, no retry needed)
			if (voltage_timer > 2000) {
				voltage_timer.reset();
				status = this->motor_left->getVoltage(motor_left_voltage);

				if (status == HAL_OK) {
					osSemaphoreAcquire(voltage_semaphore, portMAX_DELAY);
					this->_voltage = motor_left_voltage;
					osSemaphoreRelease(voltage_semaphore);
				}
				// Voltage read failure is non-critical, don't count as error
				continue;
			}

			// Periodically read motor modes (~every 2s)
			if (mode_check_timer > 2000) {
				mode_check_timer.reset();
				simplexmotion_mode_t mode_left, mode_right;

				if (this->motor_left->readMotorMode(mode_left) == HAL_OK) {
					if (mode_left != this->_motor_mode_left) {
						send_info("Motor left mode changed: %s -> %s",
								sm_mode_name(this->_motor_mode_left), sm_mode_name(mode_left));
						this->_motor_mode_left = mode_left;
					}
				}
				osDelay(2);
				if (this->motor_right->readMotorMode(mode_right) == HAL_OK) {
					if (mode_right != this->_motor_mode_right) {
						send_info("Motor right mode changed: %s -> %s",
								sm_mode_name(this->_motor_mode_right), sm_mode_name(mode_right));
						this->_motor_mode_right = mode_right;
					}
				}
				continue;
			}

			// --- Read speed (left) with retry ---
			HAL_StatusTypeDef status_speed_left = this->motor_left->readSpeed(
					motor_left_speed);

			if (status_speed_left != HAL_OK) {
				// Bus may be hung — reset and retry once
				this->motor_left->resetBus();
				osDelay(2);
				status_speed_left = this->motor_left->readSpeed(motor_left_speed);
			}

			if (status_speed_left != HAL_OK) {
				cycle_ok = false;
			}

			osDelay(2);

			// --- Read speed (right) with retry ---
			HAL_StatusTypeDef status_speed_right = HAL_ERROR;
			if (cycle_ok) {
				status_speed_right = this->motor_right->readSpeed(
						motor_right_speed);

				if (status_speed_right != HAL_OK) {
					this->motor_right->resetBus();
					osDelay(2);
					status_speed_right = this->motor_right->readSpeed(motor_right_speed);
				}

				if (status_speed_right != HAL_OK) {
					cycle_ok = false;
				}
			}

			if (status_speed_left == HAL_OK && status_speed_right == HAL_OK) {
				osSemaphoreAcquire(speed_semaphore, portMAX_DELAY);
				this->_speed.left = motor_left_speed;
				this->_speed.right = motor_right_speed;
				osSemaphoreRelease(speed_semaphore);
			}

			// --- Set torque with retry ---
			if (cycle_ok) {
				osSemaphoreAcquire(torque_semaphore, portMAX_DELAY);
				motor_left_torque = this->_input.torque_left;
				motor_right_torque = this->_input.torque_right;
				osSemaphoreRelease(torque_semaphore);

				status = this->motor_left->setTorque(motor_left_torque);
				if (status != HAL_OK) {
					this->motor_left->resetBus();
					osDelay(2);
					status = this->motor_left->setTorque(motor_left_torque);
				}
				if (status != HAL_OK) {
					cycle_ok = false;
				}

				osDelay(2);

				if (cycle_ok) {
					status = this->motor_right->setTorque(motor_right_torque);
					if (status != HAL_OK) {
						this->motor_right->resetBus();
						osDelay(2);
						status = this->motor_right->setTorque(motor_right_torque);
					}
					if (status != HAL_OK) {
						cycle_ok = false;
					}
				}
			}

			// --- Evaluate cycle result ---
			if (cycle_ok) {
				consecutive_errors = 0;
			} else {
				consecutive_errors++;

				if (consecutive_errors >= 2) {
					setError(BILBO_ERROR_WARNING, BILBO_ERROR_MOTOR_COMM);
					send_error("Motor comm error (attempt %lu/%d)",
							consecutive_errors, BILBO_DRIVE_MAX_CONSECUTIVE_ERRORS);
				}

				if (consecutive_errors >= BILBO_DRIVE_MAX_CONSECUTIVE_ERRORS) {
					setError(BILBO_ERROR_MAJOR, BILBO_ERROR_MOTOR_COMM);
					send_error("Motor comm failed %d consecutive times, entering error state",
							BILBO_DRIVE_MAX_CONSECUTIVE_ERRORS);
					this->status = BILBO_DRIVE_STATUS_ERROR;
#if ENABLE_MOTOR_SHUTDOWN_LINE
					HAL_GPIO_WritePin(MOTOR_SHUTDOWN_LINE_LEFT_PORT, MOTOR_SHUTDOWN_LINE_LEFT_PIN, GPIO_PIN_RESET);
					HAL_GPIO_WritePin(MOTOR_SHUTDOWN_LINE_RIGHT_PORT, MOTOR_SHUTDOWN_LINE_RIGHT_PIN, GPIO_PIN_RESET);
#endif
					this->motor_left->stop();
					osDelay(2);
					this->motor_right->stop();
				}
			}

		} else if (this->status == BILBO_DRIVE_STATUS_ERROR) {
			if (this->_reset_requested) {
				// Perform reset from within the drive task (owns the bus)
				HAL_StatusTypeDef s1 = this->motor_left->start();
				osDelay(10);
				HAL_StatusTypeDef s2 = this->motor_right->start();

				if (s1 == HAL_OK && s2 == HAL_OK) {
					consecutive_errors = 0;
					osSemaphoreAcquire(speed_semaphore, portMAX_DELAY);
					this->_speed = {0, 0};
					osSemaphoreRelease(speed_semaphore);
					this->status = BILBO_DRIVE_STATUS_OK;
				} else {
					send_error("Drive reset failed: motor restart failed in task");
				}
				this->_reset_requested = false;
			} else {
				// Set motors to OFF mode so they release torque.
				// Called from the drive task thread to avoid CAN bus
				// contention with the supervisor thread.
				this->motor_left->emergencyStop();
				osDelay(2);
				this->motor_right->emergencyStop();
			}
		}

		ticks_loop = osKernelGetTickCount() - current_tick;

		if (ticks_loop > this->config.task_time) {
			setError(BILBO_ERROR_WARNING, BILBO_ERROR_MOTOR_RACECONDITIONS);
		}

		this->tick++;
		osDelayUntil(current_tick + this->config.task_time);
	}
#endif
}

/* ======================================================================= */
bilbo_logging_drive_t BILBO_Drive::getSample() {
	return {
		.status = (uint8_t)this->status,
		.motor_mode_left = (uint8_t)this->_motor_mode_left,
		.motor_mode_right = (uint8_t)this->_motor_mode_right,
	};
}

/* ======================================================================= */
void startDriveTask(void *argument) {
	BILBO_Drive *drive = (BILBO_Drive*) argument;
	drive->task();
}
