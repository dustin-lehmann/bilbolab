/*
 * simplexmotion_can.cpp
 *
 *  Created on: Mar 10, 2025
 *      Author: lehmann
 */

#include "simplexmotion_can.h"
#include "firmware_settings.h"



SimplexMotion_CAN::SimplexMotion_CAN() {

}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::init(simplexmotion_can_config_t config) {
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
	status = this->setMode(SIMPLEXMOTION_CAN_MODE_RESET);

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

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::start() {
	HAL_StatusTypeDef status;

	status = this->setTarget(0);

	if (status) {
		return HAL_ERROR;
	}

	// Switch to torque mode. checkMotor() leaves the motor in BEEP mode, and
	// setMode() writes the mode register then reads it straight back — because
	// the CAN write is queued asynchronously, the first readback can race
	// ahead of the applied change and still report BEEP, so setMode() fails
	// and the cached mode stays BEEP. Nothing else ever retries the switch, so
	// every subsequent setTorque() would fail. Retry here until the motor
	// actually reports TORQUE.
	status = HAL_ERROR;
	for (int attempt = 0; attempt < 10 && status != HAL_OK; attempt++) {
		status = this->setMode(SIMPLEXMOTION_CAN_MODE_TORQUE);
		if (status != HAL_OK) {
			osDelay(10);
		}
	}

	if (status) {
		return HAL_ERROR;
	}

	return HAL_OK;

}


/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, uint8_t *data,
		uint8_t length) {
	return this->config.can->sendMessage(this->_getCANHeader(reg), data, length);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, float data) {
	uint8_t tx_data[4];
	float_to_bytearray(data, tx_data);
	return this->write(reg, tx_data, 4);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, uint16_t data) {
	uint8_t tx_data[2];
	uint16_to_bytearray(data, tx_data);
	return this->write(reg, tx_data, 2);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, uint32_t data) {
	uint8_t tx_data[4];
	uint32_to_bytearray(data, tx_data);
	return this->write(reg, tx_data, 4);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, int16_t data) {
	uint8_t tx_data[2];
	int16_to_bytearray(data, tx_data);
	return this->write(reg, tx_data, 2);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::write(uint16_t reg, int32_t data) {
	uint8_t tx_data[4];
	int32_to_bytearray(data, tx_data);
	return this->write(reg, tx_data, 4);
}

/* --------------------------------------------------------------------- */
CAN_Status SimplexMotion_CAN::read(uint16_t reg, uint8_t *responseData,
		uint8_t requestLength, uint8_t &responseLength) {
	return this->config.can->sendRemoteFrame(this->_getCANHeader(reg),
	SIMPLEXMOTION_CAN_REMOTE_TIMEOUT, responseData, requestLength,
			responseLength);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::read(uint16_t reg, float &data) {
	uint8_t responseData[4];
	uint8_t responseLength = 0;

	CAN_Status status = this->read(reg, responseData, 4, responseLength);

	if (status != CAN_SUCCESS || responseLength != 4) {
		return HAL_ERROR;
	}

	data = bytearray_to_float(responseData);

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::read(uint16_t reg, uint16_t &data) {
	uint8_t responseData[2];
	uint8_t responseLength = 0;

	CAN_Status status = this->read(reg, responseData, 2, responseLength);

	if (status != CAN_SUCCESS || responseLength != 2) {
		return HAL_ERROR;
	}

	data = bytearray_to_uint16(responseData);

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::read(uint16_t reg, int16_t &data) {
	uint8_t responseData[2] = {0};
	uint8_t responseLength = 0;

	CAN_Status status = this->read(reg, responseData, 2, responseLength);

	if (status != CAN_SUCCESS || responseLength != 2) {
		return HAL_ERROR;
	}

	data = bytearray_to_int16(responseData);

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::read(uint16_t reg, uint32_t &data) {
	uint8_t responseData[4];
	uint8_t responseLength = 0;

	CAN_Status status = this->read(reg, responseData, 4, responseLength);

	if (status != CAN_SUCCESS || responseLength != 4) {
		return HAL_ERROR;
	}

	data = bytearray_to_uint32(responseData);

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::read(uint16_t reg, int32_t &data) {
	uint8_t responseData[4];
	uint8_t responseLength = 0;

	CAN_Status status = this->read(reg, responseData, 4, responseLength);

	if (status != CAN_SUCCESS || responseLength != 4) {
		return HAL_ERROR;
	}

	data = bytearray_to_int32(responseData);

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::checkCommunication() {
	// Read the mode
	simplexmotion_can_mode_t mode;
	HAL_StatusTypeDef status = this->readMode(mode);

	float speed = 0;
	status = this->readSpeed(speed);

	return status;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::checkMotor() {
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

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::setTorque(float torque) {
	if (this->mode != SIMPLEXMOTION_CAN_MODE_TORQUE) {
		return HAL_ERROR;
	}

	// Calculate the corresponding torque value
	int16_t torque_value_int = (int16_t) (this->config.direction * torque
			/ this->config.torque_limit * 32767.0);

	return this->setTarget((int32_t) torque_value_int);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::readSpeed(float &speed) {
	int16_t speed_int = 0;
	HAL_StatusTypeDef status;

	status = this->read(SIMPLEXMOTION_CAN_REG_SPEED, speed_int);

	if (status) {
		return HAL_ERROR;
	}

	speed = this->config.direction * 2 * pi * speed_int / 256;

	return HAL_OK;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::readHardwareRev() {
	return HAL_ERROR;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::readSoftwareRev(uint16_t &software_rev) {
	return this->read(SIMPLEXMOTION_CAN_REG_SW_REV, software_rev);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::readName() {
	return HAL_ERROR;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::setMode(simplexmotion_can_mode_t mode) {

	HAL_StatusTypeDef status = this->write(SIMPLEXMOTION_CAN_REG_MODE,
			(uint16_t) mode);

	if (status != HAL_OK) {
		return status;
	}

	// Read back the mode
	simplexmotion_can_mode_t mode_read = SIMPLEXMOTION_CAN_MODE_OFF;
	status = this->readMode(mode_read);

	if (status != HAL_OK) {
		return status;
	}

	// Check if the mode has been successfully set

	if (mode_read != mode) {
		return HAL_ERROR;
	}

	this->mode = mode;

	return HAL_OK;

}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::readMode(simplexmotion_can_mode_t &mode) {
	uint8_t rx_data[2] = { 0 };
	uint8_t responseLength = 0;

	CAN_Status status = this->read(SIMPLEXMOTION_CAN_REG_MODE, rx_data, 2,
			responseLength);

	if (status == CAN_SUCCESS) {
		mode = (simplexmotion_can_mode_t) bytearray_to_uint16(rx_data);
		return HAL_OK;
	}

	return HAL_ERROR;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::setTarget(int32_t target) {
	return this->write(SIMPLEXMOTION_CAN_REG_TARGET_INPUT, target);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::stop() {
	HAL_StatusTypeDef status;
	status = this->setTarget(0);
	if (status) {
		return HAL_ERROR;
	}
	return HAL_OK;
//	status = this->setMode(SIMPLEXMOTION_CAN_MODE_OFF);
//	if (status) {
//		return HAL_ERROR;
//	}
//	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::emergencyStop() {
	this->setTarget(0);
	return this->setMode(SIMPLEXMOTION_CAN_MODE_OFF);
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::beep(uint16_t amplitude) {

	HAL_StatusTypeDef ret;
	ret = this->setMode(SIMPLEXMOTION_CAN_MODE_BEEP);
	if (ret) {
		return ret;
	}
	// Set the amplitude

	ret = this->setTarget((int32_t) amplitude);
	if (ret) {
		return ret;
	}
	return ret;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::setTorqueLimit(float maxTorque) {

	uint16_t torque_limit_int = (uint16_t) (maxTorque * 1000);
	HAL_StatusTypeDef status;

	status = this->write(SIMPLEXMOTION_CAN_REG_TORQUE_LIMIT, torque_limit_int);

	if (status) {
		return HAL_ERROR;
	}
	uint16_t torque_limit_check = 0;

	status = this->read(SIMPLEXMOTION_CAN_REG_TORQUE_LIMIT, torque_limit_check);

	if (torque_limit_int != torque_limit_check) {
		return HAL_ERROR;
	}

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::setSpeedLimit(uint16_t max_rpm) {
	// RampSpeedMax: motor-internal speed limit for torque mode.
	// Unit: positions/second / 16. Formula: value = rpm * 4096 / 960.
	int16_t value = (int16_t)((uint32_t)max_rpm * 4096 / 960);

	HAL_StatusTypeDef status = this->write(SIMPLEXMOTION_CAN_REG_RAMP_SPEED_MAX, value);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}

	// Read back and verify
	int16_t readback = 0;
	status = this->read(SIMPLEXMOTION_CAN_REG_RAMP_SPEED_MAX, readback);
	if (status != HAL_OK || readback != value) {
		return HAL_ERROR;
	}

	return HAL_OK;
}
/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::getTemperature(float &temperature) {
	return HAL_ERROR;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::getVoltage(float &voltage) {
	uint16_t voltage_int = 0;
	HAL_StatusTypeDef status = this->read(SIMPLEXMOTION_CAN_REG_VOLTAGE,
			voltage_int);

	if (status) {
		return status;
	}

	voltage = voltage_int * 0.01;

	return HAL_OK;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::setSpeedFilter(uint16_t value) {
	if (value > 15) {
		return HAL_ERROR;
	}

	HAL_StatusTypeDef status = this->write(SIMPLEXMOTION_CAN_REG_SPEED_FILTER, value);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}

	// Read back and verify
	uint16_t readback = 0;
	status = this->read(SIMPLEXMOTION_CAN_REG_SPEED_FILTER, readback);
	if (status != HAL_OK || readback != value) {
		return HAL_ERROR;
	}

	return HAL_OK;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::setEncoderResolution(uint16_t bits) {
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
	HAL_StatusTypeDef status = this->read(SIMPLEXMOTION_CAN_REG_MOTOR_OPTIONS, options);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}

	// Clear bits 12-15, set new resolution
	options = (options & 0x0FFF) | (resolution_field << 12);

	status = this->write(SIMPLEXMOTION_CAN_REG_MOTOR_OPTIONS, options);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}

	// Read back and verify
	uint16_t readback = 0;
	status = this->read(SIMPLEXMOTION_CAN_REG_MOTOR_OPTIONS, readback);
	if (status != HAL_OK || readback != options) {
		return HAL_ERROR;
	}

	return HAL_OK;
}

/* --------------------------------------------------------------------- */
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
HAL_StatusTypeDef SimplexMotion_CAN::configureShutdownInput() {
	HAL_StatusTypeDef status;

	// StatusInputs register (412):
	//   bits 0..3: input number for InputA (0 = IN1)
	//   bits 4..7: input number for InputB (unused, keep default)
	//   bits 8..15: filter value (use 2 for light debounce)
	uint16_t status_inputs = (2 << 8) | (0 << 0);  // InputA = IN1, filter = 2
	status = this->write(SIMPLEXMOTION_CAN_REG_STATUS_INPUTS, status_inputs);
	if (status != HAL_OK) return HAL_ERROR;

	// InputPolarity register (140):
	//   bit 0 = IN1 polarity. Set to 1 to invert (active LOW).
	//   This means: line LOW → InputA active → quickstop triggers.
	//   Read-modify-write to preserve other input polarities.
	uint16_t polarity = 0;
	this->read(SIMPLEXMOTION_CAN_REG_INPUT_POLARITY, polarity);
	polarity |= (1 << 0);  // Set bit 0: IN1 inverted (active low)
	status = this->write(SIMPLEXMOTION_CAN_REG_INPUT_POLARITY, polarity);
	if (status != HAL_OK) return HAL_ERROR;

	// MaskQuickstop register (413):
	//   bit 12 = InputA. Setting this causes a controlled quickstop
	//   when InputA becomes active (i.e., when IN1 goes LOW).
	//   Read-modify-write to preserve any existing quickstop masks.
	uint16_t mask_qs = 0;
	this->read(SIMPLEXMOTION_CAN_REG_MASK_QUICKSTOP, mask_qs);
	mask_qs |= (1 << 12);  // Enable quickstop on InputA
	status = this->write(SIMPLEXMOTION_CAN_REG_MASK_QUICKSTOP, mask_qs);
	if (status != HAL_OK) return HAL_ERROR;

	// Set the quickstop braking torque (MotorTorqueStop, register 205).
	// Use 80% of the configured torque limit for controlled deceleration.
	uint16_t stop_torque = (uint16_t)(this->config.torque_limit * 1000 * 0.8);
	status = this->write(SIMPLEXMOTION_CAN_REG_TORQUE_STOP, stop_torque);
	if (status != HAL_OK) return HAL_ERROR;

	return HAL_OK;
}

/* --------------------------------------------------------------------- */
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
HAL_StatusTypeDef SimplexMotion_CAN::configureWatchdog() {
	HAL_StatusTypeDef status;
	uint16_t readback = 0;

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

	// --- Disable events 2 and 3 first ---
	uint16_t zero = 0;
	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_CONTROL + ev_countdown), zero);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_CONTROL + ev_countdown), readback);

	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_CONTROL + ev_quickstop), zero);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_CONTROL + ev_quickstop), readback);

	// --- Event 2: Countdown (ApplData[0] = ApplData[0] - 1 every 64ms) ---
	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_TRG_REG + ev_countdown), (uint16_t)SIMPLEXMOTION_CAN_REG_APPLDATA0);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_TRG_REG + ev_countdown), readback);

	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_TRG_DATA + ev_countdown), zero);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_TRG_DATA + ev_countdown), readback);

	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_SRC_REG + ev_countdown), (uint16_t)SIMPLEXMOTION_CAN_REG_APPLDATA0);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_SRC_REG + ev_countdown), readback);

	uint16_t one = 1;
	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_SRC_DATA + ev_countdown), one);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_SRC_DATA + ev_countdown), readback);

	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_DST_REG + ev_countdown), (uint16_t)SIMPLEXMOTION_CAN_REG_APPLDATA0);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_DST_REG + ev_countdown), readback);

	// --- Event 3: Quickstop when counter == 0 ---
	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_TRG_REG + ev_quickstop), (uint16_t)SIMPLEXMOTION_CAN_REG_APPLDATA0);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_TRG_REG + ev_quickstop), readback);

	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_TRG_DATA + ev_quickstop), zero);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_TRG_DATA + ev_quickstop), readback);

	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_SRC_DATA + ev_quickstop), (uint16_t)SIMPLEXMOTION_CAN_MODE_QUICKSTOP);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_SRC_DATA + ev_quickstop), readback);

	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_DST_REG + ev_quickstop), (uint16_t)SIMPLEXMOTION_CAN_REG_MODE);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_DST_REG + ev_quickstop), readback);

	// Ensure quickstop braking torque is configured
	uint16_t stop_torque = (uint16_t)(this->config.torque_limit * 1000 * 0.8);
	status = this->write(SIMPLEXMOTION_CAN_REG_TORQUE_STOP, stop_torque);
	if (status != HAL_OK) return HAL_ERROR;
	this->read(SIMPLEXMOTION_CAN_REG_TORQUE_STOP, readback);

	// --- Write initial counter value before arming events ---
	status = this->write(SIMPLEXMOTION_CAN_REG_APPLDATA0, (uint16_t)BILBO_DRIVE_WATCHDOG_INITIAL);
	if (status != HAL_OK) return HAL_ERROR;

	// --- Arm events (write EventControl last) ---
	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_CONTROL + ev_countdown), ctrl_countdown);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_CONTROL + ev_countdown), readback);

	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_CONTROL + ev_quickstop), ctrl_quickstop);
	if (status != HAL_OK) return HAL_ERROR;
	this->read((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_CONTROL + ev_quickstop), readback);

	return HAL_OK;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::feedWatchdog() {
	return this->write(SIMPLEXMOTION_CAN_REG_APPLDATA0, (uint16_t)BILBO_DRIVE_WATCHDOG_RELOAD);
}

/* --------------------------------------------------------------------- */
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
HAL_StatusTypeDef SimplexMotion_CAN::disableWatchdog() {
	HAL_StatusTypeDef status;
	const uint16_t ev_countdown = 2;
	const uint16_t ev_quickstop = 3;
	uint16_t zero = 0;

	// Reload the counter so any stale countdown is far from zero while we disarm.
	status = this->write(SIMPLEXMOTION_CAN_REG_APPLDATA0, (uint16_t)BILBO_DRIVE_WATCHDOG_INITIAL);
	if (status != HAL_OK) return HAL_ERROR;

	// Disarm the quickstop event first to immediately neutralize the trigger.
	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_CONTROL + ev_quickstop), zero);
	if (status != HAL_OK) return HAL_ERROR;

	// Then disarm the countdown event.
	status = this->write((uint16_t)(SIMPLEXMOTION_CAN_REG_EVENT_CONTROL + ev_countdown), zero);
	if (status != HAL_OK) return HAL_ERROR;

	return HAL_OK;
}

/* --------------------------------------------------------------------- */
HAL_StatusTypeDef SimplexMotion_CAN::readMotorMode(simplexmotion_mode_t &mode) {
	simplexmotion_can_mode_t can_mode;
	HAL_StatusTypeDef status = this->readMode(can_mode);
	if (status != HAL_OK) {
		mode = SM_MODE_UNKNOWN;
		return HAL_ERROR;
	}
	mode = (simplexmotion_mode_t)can_mode;
	return HAL_OK;
}

/* --------------------------------------------------------------------- */
void SimplexMotion_CAN::resetBus() {
	this->config.can->reset();
}

/* --------------------------------------------------------------------- */
uint32_t SimplexMotion_CAN::_getCANHeader(uint16_t address) {

	return (0 << 24) | (this->config.id << 16) | address;

}
