#include "bilbo_drive.h"
#include "modbus_rtu.h"

static const osThreadAttr_t drive_task_attributes = { .name = "drive",
		.stack_size = 1800 * 4, .priority = (osPriority_t) osPriorityNormal, };

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

	this->motor_left->start();
	this->motor_right->start();

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
	while (true){
		current_tick = osKernelGetTickCount();
		if (this->status == BILBO_DRIVE_STATUS_OK) {
			if (taskmode == 0){

				HAL_StatusTypeDef status_speed_left = this->motor_left->readSpeed(motor_left_speed);
				osDelay(1);
				HAL_StatusTypeDef status_speed_right = this->motor_right->readSpeed(motor_right_speed);

				if (status_speed_left == HAL_OK && status_speed_right == HAL_OK){
					osSemaphoreAcquire(speed_semaphore, portMAX_DELAY);
					this->_speed.left = motor_left_speed;
					this->_speed.right = motor_right_speed;
					osSemaphoreRelease(speed_semaphore);
				} else {
					resetAllModbusHandlers();
					nop();
				}

				taskmode = 1;
			} else {
				osSemaphoreAcquire(torque_semaphore, portMAX_DELAY);
				motor_left_torque = this->_input.torque_left;
				motor_right_torque = this->_input.torque_right;
				osSemaphoreRelease(torque_semaphore);

				HAL_StatusTypeDef status_torque_left = this->motor_left->setTorque(motor_left_torque);
				osDelay(1);
				HAL_StatusTypeDef status_torque_right = this->motor_right->setTorque(motor_right_torque);

				if (status_torque_left == HAL_OK && status_torque_right == HAL_OK){
					nop();
				} else {
					resetAllModbusHandlers();
					nop();
				}
				taskmode = 0;
			}


		} else {
			nop();
		}

		osDelayUntil(current_tick + this->config.task_time);
	}
#endif
#ifdef BILBO_DRIVE_SIMPLEXMOTION_CAN
	while (true) {
		current_tick = osKernelGetTickCount();

		if (this->status == BILBO_DRIVE_STATUS_OK) {

			// Read the voltage
			if (voltage_timer > 2000) {
				voltage_timer.reset();
				status = this->motor_left->getVoltage(motor_left_voltage);

				if (status == HAL_OK) {
					osSemaphoreAcquire(voltage_semaphore, portMAX_DELAY);
					this->_voltage = motor_left_voltage;
					osSemaphoreRelease(voltage_semaphore);
				} else {
					// TODO
				}
				continue;
			}

			// Read the speed
			HAL_StatusTypeDef status_speed_left = this->motor_left->readSpeed(
					motor_left_speed);

			if (status_speed_left == HAL_ERROR) {
				setError(BILBO_ERROR_MAJOR, BILBO_ERROR_MOTOR_COMM);
				send_error("Motor comm error");
				this->status = BILBO_DRIVE_STATUS_ERROR;
				continue;
			}
			osDelay(2);

			HAL_StatusTypeDef status_speed_right = this->motor_right->readSpeed(
					motor_right_speed);

			if (status_speed_right == HAL_ERROR) {
				setError(BILBO_ERROR_MAJOR, BILBO_ERROR_MOTOR_COMM);
				send_error("Motor comm error");
				this->status = BILBO_DRIVE_STATUS_ERROR;
				continue;
			}

			if (status_speed_left == HAL_OK && status_speed_right == HAL_OK) {
				osSemaphoreAcquire(speed_semaphore, portMAX_DELAY);
				this->_speed.left = motor_left_speed;
				this->_speed.right = motor_right_speed;
				osSemaphoreRelease(speed_semaphore);
			}

			// Set the torque

			osSemaphoreAcquire(torque_semaphore, portMAX_DELAY);
			motor_left_torque = this->_input.torque_left;
			motor_right_torque = this->_input.torque_right;
			osSemaphoreRelease(torque_semaphore);

			status = this->motor_left->setTorque(motor_left_torque);

			if (status == HAL_ERROR) {
				setError(BILBO_ERROR_MAJOR, BILBO_ERROR_MOTOR_COMM);
				send_error("Motor comm error");
				this->status = BILBO_DRIVE_STATUS_ERROR;
				continue;
			}

			osDelay(2);
			status = this->motor_right->setTorque(motor_right_torque);

			if (status == HAL_ERROR) {
				setError(BILBO_ERROR_MAJOR, BILBO_ERROR_MOTOR_COMM);
				send_error("Motor comm error");
				this->status = BILBO_DRIVE_STATUS_ERROR;
				continue;
			}

		} else if (this->status == BILBO_DRIVE_STATUS_ERROR) {
			nop();
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
void startDriveTask(void *argument) {
	BILBO_Drive *drive = (BILBO_Drive*) argument;
	drive->task();
}
