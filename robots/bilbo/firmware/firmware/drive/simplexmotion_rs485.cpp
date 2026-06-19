/*
 * simplexmotion_rs485.cpp
 *
 *  Created on: Mar 10, 2025
 *      Author: lehmann
 */

#include "simplexmotion_rs485.h"
#include "firmware_settings.h"

SimplexMotion_RS485::SimplexMotion_RS485(){

}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::init(
		simplexmotion_rs485_config_t config) {
	this->config = config;

	HAL_StatusTypeDef status;

	// Check the communication
	status = this->checkCommunication();



	if (status) {
		return HAL_ERROR;
	}
	// Read the Firmware Version

	uint16_t software_rev = 0;
	status = this->readSoftwareRev(software_rev);

	// Reset the motor
	status = this->setMode(SIMPLEXMOTION_RS485_MODE_RESET);

	if (status) {
		return HAL_ERROR;
	}

	// Set the torque limit
	status = this->setTorqueLimit(this->config.torque_limit);

	if (status) {
		return HAL_ERROR;
	}

	// Set speed measurement filter for low-speed applications (0-200 RPM)
	status = this->setSpeedFilter(SIMPLEXMOTION_SPEED_FILTER);

	if (status) {
		return HAL_ERROR;
	}

	// Set encoder resolution
	status = this->setEncoderResolution(SIMPLEXMOTION_ENCODER_RESOLUTION);

	if (status) {
		return HAL_ERROR;
	}

	// Set maximum speed in torque mode (motor-internal soft limit via RampSpeedMax)
#if SIMPLEXMOTION_OVERSPEED_RPM > 0
	status = this->setSpeedLimit(SIMPLEXMOTION_OVERSPEED_RPM);
	if (status) {
		return HAL_ERROR;
	}
#endif

#if ENABLE_MOTOR_SHUTDOWN_LINE
	// Configure IN1 as hardware quickstop trigger.
	// STM32 GPIO holds the line HIGH; LOW triggers motor quickstop.
	status = this->configureShutdownInput();
	if (status) {
		return HAL_ERROR;
	}
#endif

#if BILBO_DRIVE_WATCHDOG_ENABLE
	status = this->configureWatchdog();
	if (status) {
		return HAL_ERROR;
	}
#else
	// Watchdog disabled: actively tear down any events left armed by a
	// previously-flashed watchdog-enabled firmware. The events live in the
	// motor's volatile RAM and are NOT cleared by an STM32-only reflash
	// (SWD flashing does not power-cycle the motor), so without this the
	// stale countdown/quickstop events keep running and force a Quickstop.
	status = this->disableWatchdog();
	if (status) {
		return HAL_ERROR;
	}
#endif

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::start() {
	HAL_StatusTypeDef status;

	status = this->setTarget(0);

	if (status) {
		return HAL_ERROR;
	}

	status = this->setMode(SIMPLEXMOTION_RS485_MODE_TORQUE);

	if (status) {
		return HAL_ERROR;
	}

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::checkCommunication() {
	simplexmotion_rs485_mode_t mode;
	HAL_StatusTypeDef status = this->readMode(mode);
	return status;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::checkMotor() {
	HAL_StatusTypeDef status;
	// Check the communication
	status = this->checkCommunication();
	if (status) {
		return status;
	}
	status = this->beep(500);
	if (status) {
		return status;
	}
	osDelay(150);
	status = this->stop();

	if (status) {
		return status;
	}

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::beep(uint16_t amplitude) {
	HAL_StatusTypeDef ret;
	ret = this->setMode(SIMPLEXMOTION_RS485_MODE_BEEP);

	// Set the amplitude
	ret = this->setTarget((int32_t) amplitude);

	return ret;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::setTorque(float torque) {
	// First check if torque mode has been set
	if (!(this->mode == SIMPLEXMOTION_RS485_MODE_TORQUE)) {
		return HAL_ERROR;
	}

	// Calculate the corresponding torque value
	int16_t torque_value_int = (int16_t) (this->config.direction * torque
			/ this->config.torque_limit * 32767.0);
	int32_t target_input = (int32_t) torque_value_int;

	HAL_StatusTypeDef ret = this->setTarget(target_input);
	return ret;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readHardwareRev() {
	return HAL_ERROR;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readSoftwareRev(uint16_t &software_rev) {
	return HAL_ERROR;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readName() {
	return HAL_ERROR;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::getTemperature(float &temperature) {
	return HAL_ERROR;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::getVoltage(float &voltage) {
	uint16_t voltage_int = 0;
	HAL_StatusTypeDef success = this->readRegisters(
	SIMPLEXMOTION_RS485_REG_VOLTAGE, 1, &voltage_int);

	if (success == HAL_ERROR) {
		return HAL_ERROR;
	}
	voltage = voltage_int * 0.01;

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readSpeed(float &speed) {
	uint16_t speed_raw = 0;
	HAL_StatusTypeDef success = this->readRegisters(
	SIMPLEXMOTION_RS485_REG_SPEED, 1, &speed_raw);

	int16_t speed_signed = (int16_t) speed_raw;

	if (success == HAL_ERROR) {
		return HAL_ERROR;
	}
	speed = this->config.direction * 2 * pi * speed_signed / 256;

	return success;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::setMode(
		simplexmotion_rs485_mode_t mode) {
	uint16_t data = (uint16_t) mode;

	// Set the mode
	HAL_StatusTypeDef write_success = this->writeRegisters(
	SIMPLEXMOTION_RS485_REG_MODE, 1, &data);

	if (write_success == HAL_ERROR) {
		return HAL_ERROR;
	}

	// Read back the mode
	uint16_t rx_data = 0;
	HAL_StatusTypeDef read_success = this->readRegisters(
	SIMPLEXMOTION_RS485_REG_MODE, 1, &rx_data);

	if (read_success == HAL_ERROR) {
		return HAL_ERROR;
	}

	this->mode = (simplexmotion_rs485_mode_t) rx_data;

	if (rx_data != mode) {
		return HAL_ERROR;
	}
	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readMode(
		simplexmotion_rs485_mode_t &mode) {
	uint16_t rx_data = 0;
	HAL_StatusTypeDef read_success = this->readRegisters(
	SIMPLEXMOTION_RS485_REG_MODE, 1, &rx_data);

	if (read_success == HAL_ERROR) {
		return HAL_ERROR;
	}

	mode = (simplexmotion_rs485_mode_t) rx_data;

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::stop() {
	HAL_StatusTypeDef status;
	status = this->setTarget(0);
	if (status) {
		return HAL_ERROR;
	}
	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::emergencyStop() {
	this->setTarget(0);
	return this->setMode(SIMPLEXMOTION_RS485_MODE_OFF);
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::setTorqueLimit(float maxTorque) {
	uint16_t torque_limit_int = (uint16_t) (maxTorque * 1000);

	HAL_StatusTypeDef ret;

	ret = this->writeRegisters(SIMPLEXMOTION_RS485_REG_TORQUE_LIMIT, 1,
			&torque_limit_int);

	if (ret == HAL_ERROR) {
		return HAL_ERROR;
	}

	uint16_t torque_limit_int_check = 0;
	ret = this->readRegisters(SIMPLEXMOTION_RS485_REG_TORQUE_LIMIT, 1,
			&torque_limit_int_check);

	if (ret == HAL_ERROR) {
		return HAL_ERROR;
	}

	if (torque_limit_int != torque_limit_int_check) {
		return HAL_ERROR;
	}

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::setSpeedFilter(uint16_t value) {
	if (value > 15) {
		return HAL_ERROR;
	}

	HAL_StatusTypeDef status = this->writeRegisters(
			SIMPLEXMOTION_RS485_REG_SPEED_FILTER, 1, &value);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}

	// Read back and verify
	uint16_t readback = 0;
	status = this->readRegisters(
			SIMPLEXMOTION_RS485_REG_SPEED_FILTER, 1, &readback);
	if (status != HAL_OK || readback != value) {
		return HAL_ERROR;
	}

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::setEncoderResolution(uint16_t bits) {
	// bits: 12 (4096 counts), 13 (8192 counts), or 14 (16384 counts)
	uint16_t resolution_field;
	switch (bits) {
	case 12: resolution_field = 0; break;
	case 13: resolution_field = 1; break;
	case 14: resolution_field = 2; break;
	default: return HAL_ERROR;
	}

	// Read current MotorOptions to preserve other bits
	uint16_t options = 0;
	HAL_StatusTypeDef status = this->readRegisters(
			SIMPLEXMOTION_RS485_REG_MOTOR_OPTIONS, 1, &options);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}

	// Clear bits 12-15, set new resolution
	options = (options & 0x0FFF) | (resolution_field << 12);

	status = this->writeRegisters(
			SIMPLEXMOTION_RS485_REG_MOTOR_OPTIONS, 1, &options);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}

	// Read back and verify
	uint16_t readback = 0;
	status = this->readRegisters(
			SIMPLEXMOTION_RS485_REG_MOTOR_OPTIONS, 1, &readback);
	if (status != HAL_OK || readback != options) {
		return HAL_ERROR;
	}

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::setSpeedLimit(uint16_t max_rpm) {
	// RampSpeedMax: motor-internal speed limit for torque mode.
	// Unit: positions/second / 16. Formula: value = rpm * 4096 / 960.
	uint16_t value = (uint16_t)((uint32_t)max_rpm * 4096 / 960);

	HAL_StatusTypeDef status = this->writeRegisters(
			SIMPLEXMOTION_RS485_REG_RAMP_SPEED_MAX, 1, &value);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}

	// Read back and verify
	uint16_t readback = 0;
	status = this->readRegisters(
			SIMPLEXMOTION_RS485_REG_RAMP_SPEED_MAX, 1, &readback);
	if (status != HAL_OK || readback != value) {
		return HAL_ERROR;
	}

	return HAL_OK;
}

/* ================================================================================= */
/**
 * @brief Configures the motor's IN1 as a hardware quickstop trigger.
 *
 * Maps IN1 to StatusInputs InputA (status bit 12), sets polarity to
 * active-low (inverted), and enables MaskQuickstop on InputA.
 *
 * The STM32 holds the line HIGH during normal operation. On error
 * (or STM32 crash with external pulldown), the line goes LOW and
 * the motor performs a controlled quickstop using MotorTorqueStop braking.
 */
HAL_StatusTypeDef SimplexMotion_RS485::configureShutdownInput() {
	HAL_StatusTypeDef status;

	// StatusInputs register:
	//   bits 0..3: input number for InputA (0 = IN1)
	//   bits 4..7: input number for InputB (unused, keep default)
	//   bits 8..15: filter value (use 2 for light debounce)
	uint16_t status_inputs = (2 << 8) | (0 << 0);  // InputA = IN1, filter = 2
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_STATUS_INPUTS, 1, &status_inputs);
	if (status != HAL_OK) return HAL_ERROR;

	// InputPolarity register:
	//   bit 0 = IN1 polarity. Set to 1 to invert (active LOW).
	//   This means: line LOW -> InputA active -> quickstop triggers.
	//   Read-modify-write to preserve other input polarities.
	uint16_t polarity = 0;
	this->readRegisters(SIMPLEXMOTION_RS485_REG_INPUT_POLARITY, 1, &polarity);
	polarity |= (1 << 0);  // Set bit 0: IN1 inverted (active low)
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_INPUT_POLARITY, 1, &polarity);
	if (status != HAL_OK) return HAL_ERROR;

	// MaskQuickstop register:
	//   bit 12 = InputA. Setting this causes a controlled quickstop
	//   when InputA becomes active (i.e., when IN1 goes LOW).
	//   Read-modify-write to preserve any existing quickstop masks.
	uint16_t mask_qs = 0;
	this->readRegisters(SIMPLEXMOTION_RS485_REG_MASK_QUICKSTOP, 1, &mask_qs);
	mask_qs |= (1 << 12);  // Enable quickstop on InputA
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_MASK_QUICKSTOP, 1, &mask_qs);
	if (status != HAL_OK) return HAL_ERROR;

	// Set the quickstop braking torque (MotorTorqueStop).
	// Use 80% of the configured torque limit for controlled deceleration.
	uint16_t stop_torque = (uint16_t)(this->config.torque_limit * 1000 * 0.8);
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_TORQUE_STOP, 1, &stop_torque);
	if (status != HAL_OK) return HAL_ERROR;

	return HAL_OK;
}

/* ================================================================================= */
/**
 * @brief Configures motor-internal watchdog using the Events system.
 *
 * Programs two events (slots 2 and 3) that run at 2kHz inside the motor
 * controller, independent of the STM32:
 *
 *   Event 2: Countdown — decrements ApplData[0] by 1 every ~64ms.
 *            Trigger: ApplData[0] != 0 (stops at zero, no underflow).
 *            Type: Repeat (fires once per filter period).
 *            Action: ApplData[0] = ApplData[0] - 1
 *
 *   Event 3: Quickstop — triggers when counter reaches zero.
 *            Trigger: ApplData[0] == 0
 *            Type: Edge (fires once on false→true transition).
 *            Action: Mode = Quickstop (5)
 *
 * The STM32 must call feedWatchdog() periodically to reload the counter.
 * If communication stops (e.g., STM32 brownout), the counter reaches zero
 * and the motor autonomously enters Quickstop mode.
 */
HAL_StatusTypeDef SimplexMotion_RS485::configureWatchdog() {
	HAL_StatusTypeDef status;

	// Event slot indices (slots 0-1 used by overspeed protection)
	const uint16_t ev_countdown = 2;
	const uint16_t ev_quickstop = 3;

	// EventControl word layout (SimplexMotion Manual §4.7):
	//   bits 0..3:   trigger operation (1=Equal, 2=NotEqual)
	//   bits 4..7:   trigger filter (7 = 128 evals at 2kHz = 64ms)
	//   bits 8..9:   trigger type (1=Edge, 2=Repeat)
	//   bits 10..13: data operation (3=Subtract, 15=Value)

	// Event 2: Repeat, ApplData[0] != 0, Subtract 1
	uint16_t ctrl_countdown = (3 << 10) | (2 << 8) | (7 << 4) | 2;   // 0x0E72
	// Event 3: Edge, ApplData[0] == 0, write Quickstop value
	uint16_t ctrl_quickstop = (15 << 10) | (1 << 8) | (3 << 4) | 1;  // 0x3D31

	// Event data values use internal motor register numbers (not Modbus addresses)
	uint16_t reg_appldata0 = SIMPLEXMOTION_INTERNAL_REG_APPLDATA0;
	uint16_t reg_mode = SIMPLEXMOTION_INTERNAL_REG_MODE;
	uint16_t quickstop_val = (uint16_t)SIMPLEXMOTION_RS485_MODE_QUICKSTOP;
	uint16_t zero = 0;
	uint16_t one = 1;

	// --- Disable events 2 and 3 first ---
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_CONTROL + ev_countdown, 1, &zero);
	if (status != HAL_OK) return HAL_ERROR;
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_CONTROL + ev_quickstop, 1, &zero);
	if (status != HAL_OK) return HAL_ERROR;

	// --- Event 2: Countdown (ApplData[0] = ApplData[0] - 1 every 64ms) ---
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_TRG_REG + ev_countdown, 1, &reg_appldata0);
	if (status != HAL_OK) return HAL_ERROR;

	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_TRG_DATA + ev_countdown, 1, &zero);
	if (status != HAL_OK) return HAL_ERROR;

	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_SRC_REG + ev_countdown, 1, &reg_appldata0);
	if (status != HAL_OK) return HAL_ERROR;

	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_SRC_DATA + ev_countdown, 1, &one);
	if (status != HAL_OK) return HAL_ERROR;

	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_DST_REG + ev_countdown, 1, &reg_appldata0);
	if (status != HAL_OK) return HAL_ERROR;

	// --- Event 3: Quickstop when counter == 0 ---
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_TRG_REG + ev_quickstop, 1, &reg_appldata0);
	if (status != HAL_OK) return HAL_ERROR;

	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_TRG_DATA + ev_quickstop, 1, &zero);
	if (status != HAL_OK) return HAL_ERROR;

	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_SRC_DATA + ev_quickstop, 1, &quickstop_val);
	if (status != HAL_OK) return HAL_ERROR;

	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_DST_REG + ev_quickstop, 1, &reg_mode);
	if (status != HAL_OK) return HAL_ERROR;

	// Ensure quickstop braking torque is configured
	uint16_t stop_torque = (uint16_t)(this->config.torque_limit * 1000 * 0.8);
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_TORQUE_STOP, 1, &stop_torque);
	if (status != HAL_OK) return HAL_ERROR;

	// --- Write initial counter value before arming events ---
	uint16_t initial = BILBO_DRIVE_WATCHDOG_INITIAL;
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_APPLDATA0, 1, &initial);
	if (status != HAL_OK) return HAL_ERROR;

	// --- Arm events (write EventControl last) ---
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_CONTROL + ev_countdown, 1, &ctrl_countdown);
	if (status != HAL_OK) return HAL_ERROR;

	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_CONTROL + ev_quickstop, 1, &ctrl_quickstop);
	if (status != HAL_OK) return HAL_ERROR;

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::feedWatchdog() {
	uint16_t reload = BILBO_DRIVE_WATCHDOG_RELOAD;
	return this->writeRegisters(SIMPLEXMOTION_RS485_REG_APPLDATA0, 1, &reload);
}

/* ================================================================================= */
/**
 * @brief Tears down the motor-internal watchdog events.
 *
 * Clears EventControl for the countdown (slot 2) and quickstop (slot 3)
 * events programmed by configureWatchdog(). Called during motor init when
 * BILBO_DRIVE_WATCHDOG_ENABLE is 0.
 *
 * The events live in the motor's volatile RAM and are NOT cleared by an
 * STM32-only reflash (SWD flashing does not power-cycle the motor). Without
 * this teardown, events armed by a previously-flashed watchdog-enabled
 * firmware keep counting down and force a Quickstop once the STM32 stops
 * feeding the counter. To close the small startup window between the motor
 * RESET in init() and this teardown, the counter is reloaded first (pushing
 * any imminent timeout far out), then the quickstop event is disarmed before
 * the countdown event so the watchdog cannot trigger a Quickstop mid-teardown.
 */
HAL_StatusTypeDef SimplexMotion_RS485::disableWatchdog() {
	HAL_StatusTypeDef status;
	const uint16_t ev_countdown = 2;
	const uint16_t ev_quickstop = 3;
	uint16_t zero = 0;

	// Reload the counter so any stale countdown is far from zero while we disarm.
	uint16_t initial = BILBO_DRIVE_WATCHDOG_INITIAL;
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_APPLDATA0, 1, &initial);
	if (status != HAL_OK) return HAL_ERROR;

	// Disarm the quickstop event first to immediately neutralize the trigger.
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_CONTROL + ev_quickstop, 1, &zero);
	if (status != HAL_OK) return HAL_ERROR;

	// Then disarm the countdown event.
	status = this->writeRegisters(SIMPLEXMOTION_RS485_REG_EVENT_CONTROL + ev_countdown, 1, &zero);
	if (status != HAL_OK) return HAL_ERROR;

	return HAL_OK;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readMotorMode(simplexmotion_mode_t &mode) {
	simplexmotion_rs485_mode_t rs485_mode;
	HAL_StatusTypeDef status = this->readMode(rs485_mode);
	if (status != HAL_OK) {
		mode = SM_MODE_UNKNOWN;
		return HAL_ERROR;
	}
	mode = (simplexmotion_mode_t)rs485_mode;
	return HAL_OK;
}

/* ================================================================================= */
void SimplexMotion_RS485::resetBus() {
	resetAllModbusHandlers();
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::setTarget(int32_t target) {
	HAL_StatusTypeDef ret;
	uint16_t tx_data[2] = { 0 };

	tx_data[0] = target >> 16;
	tx_data[1] = target & 0xFFFF;

	ret = this->writeRegisters(SIMPLEXMOTION_RS485_REG_TARGET_INPUT, 2,
			tx_data);
	return ret;
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::writeRegisters(uint16_t address,
		uint16_t num_registers, uint16_t *data) {

	int32_t u32NotificationValue;
	modbus_query_t telegram;

	telegram.u8id = this->config.id;

	if (num_registers > 1) {
		telegram.u8fct = MB_FC_WRITE_MULTIPLE_REGISTERS;
	} else {
		telegram.u8fct = MB_FC_WRITE_REGISTER;
	}
	telegram.u16RegAdd = address;
	telegram.u16CoilsNo = num_registers;
	telegram.u16reg = data;

	this->config.modbus->query(telegram);
//	u32NotificationValue = ulTaskNotifyTake(pdTRUE, portMAX_DELAY); // block until query finished
//	uint32_t ticks1 = osKernelGetTickCount();
	u32NotificationValue = ulTaskNotifyTake(pdTRUE, portMAX_DELAY); // block until query finished
//	uint32_t ticks2 = osKernelGetTickCount();

	if (u32NotificationValue != ERR_OK_QUERY) {
		if (u32NotificationValue == ERR_TIME_OUT) {
			return HAL_ERROR;
		}
		return HAL_OK;
	} else {
		return HAL_OK;
	}
}

/* ================================================================================= */
HAL_StatusTypeDef SimplexMotion_RS485::readRegisters(uint16_t address,
		uint16_t num_registers, uint16_t *data) {
	int32_t u32NotificationValue;
	modbus_query_t telegram;

	telegram.u8id = this->config.id;
	telegram.u8fct = MB_FC_READ_REGISTERS;
	telegram.u16RegAdd = address;
	telegram.u16CoilsNo = num_registers;
	telegram.u16reg = data;

	this->config.modbus->query(telegram);
	u32NotificationValue = ulTaskNotifyTake(pdTRUE, portMAX_DELAY); // block until query finished
	if (u32NotificationValue != ERR_OK_QUERY) {
		if (u32NotificationValue == ERR_TIME_OUT) {
			nop();
		}

		return HAL_ERROR;
	} else {
		return HAL_OK;
	}
}
