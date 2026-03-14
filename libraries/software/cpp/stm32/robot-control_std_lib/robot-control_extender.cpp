/*
 * robot-control_extender.cpp
 *
 *  Non-blocking external LED updates using HAL_I2C_Mem_Write_IT + ISR chaining.
 *  No RTOS required. Public API unchanged.
 *
 *  Created on: Apr 24, 2024
 *      Author: Dustin Lehmann
 */

#include "robot-control_extender.h"

// =========================== Config ===============================

// If your device does NOT auto-increment registers when writing,
// define this to 1 to send 3 single-byte ops instead of 1 RGB op.
#define EXT_NO_AUTOINC 1

// =========================== Helpers ==============================

// External LED register block layout per LED:
// [CONFIG, RED, GREEN, BLUE, BLINK_TIME, BLINK_CNT]
static inline uint16_t ext_led_base_reg(uint8_t index) {
	// LED i (0..15) starts at REG_EXTERNAL_RGB_LED_1_CONFIG + i*6
	return (uint16_t) (REG_EXTERNAL_RGB_LED_1_CONFIG + (index * 6));
}

// Small critical section helpers (no-RTOS)
static inline uint32_t cs_enter() {
	uint32_t primask = __get_PRIMASK();
	__disable_irq();
	return primask;
}
static inline void cs_exit(uint32_t primask) {
	if ((primask & 0x1) == 0) { // IRQs were enabled previously
		__enable_irq();
	}
}

// ====================== ISR-driven flush state ====================

struct ExtI2COp {
	uint16_t mem_addr;         // starting register (usually RED)
	uint8_t buf[3];           // RGB (or 1 if EXT_NO_AUTOINC)
	uint16_t len;              // 3 (or 1 if EXT_NO_AUTOINC)
};

#ifdef EXT_NO_AUTOINC
// Up to 3 ops per LED = 48 total
static ExtI2COp s_ops[48];
#else
  // One op per LED = 16 total
  static ExtI2COp s_ops[16];
#endif

#ifdef EXT_NO_AUTOINC
const uint8_t OPS_CAP = 48;
#else
  const uint8_t OPS_CAP = 16;
#endif
uint8_t n = 0;

// We coalesce one op per LED (RGB in one go). Max 16 ops.
static volatile uint8_t s_op_count = 0;
static volatile uint8_t s_op_index = 0;
static volatile uint8_t s_in_progress = 0;
static volatile uint8_t s_pending = 0;

// Back-ref so callbacks can access the instance
static RobotControl_Extender *s_self = nullptr;

// Track what was last sent (to send only diffs)
static external_led_colors_struct_t s_last_sent = { 0 };

// Track what we're attempting to send (for rollback-free confirmation)
static external_led_colors_struct_t s_pending_colors = { 0 };
static uint8_t s_pending_indices[16] = { 0 };  // LED indices that have pending updates
static uint8_t s_pending_count = 0;

// Forward declarations (file-local)
static void flush_build_diff(); // builds s_ops[] from s_self->current_external_colors vs s_last_sent
static void flush_kick_next();    // starts next I2C op or finishes frame
static void flush_start();        // public-side entry called by setters

// ====================== Class Implementation ======================

RobotControl_Extender::RobotControl_Extender() {
}

void RobotControl_Extender::init(extender_config_struct_t config) {
	this->config = config;
	// Point callbacks to this instance
	s_self = this;
}

void RobotControl_Extender::start() {
	// no-op
}

bool RobotControl_Extender::readBatteryVoltage() {

	uint8_t buf[4] = { 0 };

	// HAL_I2C_Mem_Read will write the register address (0xB0) then do a repeated-start read.
	HAL_StatusTypeDef st = HAL_I2C_Mem_Read(this->config.hi2c,
	EXTENDER_ADDRESS,         // 7-bit address in same form you're already using
			REG_BATTERY_VOLTAGE,             // 0xB0
			I2C_MEMADD_SIZE_8BIT, buf, 4, 20     // timeout ms (tweak as needed)
			);

	if (st != HAL_OK) {
		return false;
	}

	// Slave wrote the float into the register map as raw bytes (little-endian on Cortex-M).
	float v = 0.0f;
	memcpy(&v, buf, sizeof(v));

	this->battery_voltage = v;
	return true;
}

// -------------------------- Status LED ----------------------------

void RobotControl_Extender::setStatusLED(int8_t status) {
	uint8_t data = (uint8_t) status;
	HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
	REG_ERROR_LED_CONFIG, I2C_MEMADD_SIZE_8BIT, &data, 1, 100);
}

// ------------------------- Internal RGBs --------------------------

void RobotControl_Extender::rgbLED_intern_setState(uint8_t position,
		uint8_t state) {
	// MSB (bit7) = continuous output enable; lower bits hold mode (we write 0 here)
	uint8_t cfg = (state << 7) | 0x00; // force mode 0 here; setMode() can change it later

	switch (position) {
	case 0:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_1_CONFIG, I2C_MEMADD_SIZE_8BIT, &cfg, 1, 10);
		break;
	case 1:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_2_CONFIG, I2C_MEMADD_SIZE_8BIT, &cfg, 1, 10);
		break;
	case 2:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_3_CONFIG, I2C_MEMADD_SIZE_8BIT, &cfg, 1, 10);
		break;
	default:
		break;
	}
}

void RobotControl_Extender::rgbLED_intern_setMode(uint8_t position,
		uint8_t mode) {
	// mode: 0 = continuous, 1 = blink. We only write mode in LSBs (MSB=0 here).
	uint8_t cfg = (mode & 0x01);

	switch (position) {
	case 0:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_1_CONFIG, I2C_MEMADD_SIZE_8BIT, &cfg, 1, 10);
		break;
	case 1:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_2_CONFIG, I2C_MEMADD_SIZE_8BIT, &cfg, 1, 10);
		break;
	case 2:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_3_CONFIG, I2C_MEMADD_SIZE_8BIT, &cfg, 1, 10);
		break;
	default:
		break;
	}
}

void RobotControl_Extender::rgbLED_intern_setColor(uint8_t position,
		uint8_t red, uint8_t green, uint8_t blue) {
	switch (position) {
	case 0:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_1_RED, I2C_MEMADD_SIZE_8BIT, &red, 1, 10);
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_1_GREEN, I2C_MEMADD_SIZE_8BIT, &green, 1, 10);
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_1_BLUE, I2C_MEMADD_SIZE_8BIT, &blue, 1, 10);
		break;
	case 1:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_2_RED, I2C_MEMADD_SIZE_8BIT, &red, 1, 10);
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_2_GREEN, I2C_MEMADD_SIZE_8BIT, &green, 1, 10);
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_2_BLUE, I2C_MEMADD_SIZE_8BIT, &blue, 1, 10);
		break;
	case 2:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_3_RED, I2C_MEMADD_SIZE_8BIT, &red, 1, 10);
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_3_GREEN, I2C_MEMADD_SIZE_8BIT, &green, 1, 10);
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_3_BLUE, I2C_MEMADD_SIZE_8BIT, &blue, 1, 10);
		break;
	default:
		break;
	}
}

void RobotControl_Extender::rgbLED_intern_blink(uint8_t position,
		uint16_t on_time_ms) {
	uint8_t time = (uint8_t) (on_time_ms / 10);
	uint8_t mode = 1; // blink

	switch (position) {
	case 0:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_1_CONFIG, I2C_MEMADD_SIZE_8BIT, &mode, 1, 10);
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_1_BLINK_TIME, I2C_MEMADD_SIZE_8BIT, &time, 1, 10);
		break;
	case 1:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_2_CONFIG, I2C_MEMADD_SIZE_8BIT, &mode, 1, 10);
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_2_BLINK_TIME, I2C_MEMADD_SIZE_8BIT, &time, 1, 10);
		break;
	case 2:
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_3_CONFIG, I2C_MEMADD_SIZE_8BIT, &mode, 1, 10);
		HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
		REG_STATUS_RGB_LED_3_BLINK_TIME, I2C_MEMADD_SIZE_8BIT, &time, 1, 10);
		break;
	default:
		break;
	}
}

// ----------- External 16-LED strip (non-blocking flush) ----------

void RobotControl_Extender::rgbLEDStrip_extern_setPixelColor(uint8_t index,
		uint8_t red, uint8_t green, uint8_t blue) {
	if (index >= 16)
		return; // guard
	current_external_colors.colors[index] = { red, green, blue };
	flush_start();
}

void RobotControl_Extender::rgbLEDStrip_extern_setPixelColor(uint8_t index,
		rgb_color_struct_t color) {
	rgbLEDStrip_extern_setPixelColor(index, color.red, color.green, color.blue);
}

void RobotControl_Extender::rgbLEDStrip_extern_setColor(
		rgb_color_struct_t color) {
	for (uint8_t i = 0; i < 16; ++i) {
		current_external_colors.colors[i] = color;
	}
	flush_start();
}

void RobotControl_Extender::rgbLEDStrip_extern_setAllColors(
		external_led_colors_struct_t colors) {
	this->current_external_colors = colors;
	flush_start();
}

// ----------------------------- Buzzer -----------------------------

void RobotControl_Extender::buzzer_setConfig(float frequency, uint16_t on_time,
		uint8_t repeats) {
	uint8_t freq = (uint8_t) (frequency / 10);
	uint8_t time = (uint8_t) (on_time / 10);

	HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS, REG_BUZZER_FREQ,
	I2C_MEMADD_SIZE_8BIT, &freq, 1, 10);
	HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
	REG_BUZZER_BLINK_TIME,
	I2C_MEMADD_SIZE_8BIT, &time, 1, 10);
	HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS,
	REG_BUZZER_BLINK_COUNTER,
	I2C_MEMADD_SIZE_8BIT, &repeats, 1, 10);
}

void RobotControl_Extender::buzzer_start() {
	uint8_t data = 1;
	HAL_I2C_Mem_Write(this->config.hi2c, EXTENDER_ADDRESS, REG_BUZZER_DATA,
	I2C_MEMADD_SIZE_8BIT, &data, 1, 10);
}

// ===================== Flush implementation ======================

static inline uint16_t base_red_reg(uint8_t i) {
	// base = CONFIG; RED is base+1
	return (uint16_t) (ext_led_base_reg(i) + 1);
}

static void flush_build_diff() {
	// Build ops for differences between current and last-sent; coalesce RGB per LED
	// IMPORTANT: Do NOT update s_last_sent here - wait until transfer succeeds
	uint8_t n = 0;
	s_pending_count = 0;

#ifndef EXT_NO_AUTOINC
	for (uint8_t i = 0; i < 16 && n < 16; ++i) {
		const rgb_color_struct_t cur = s_self->current_external_colors.colors[i];
		const rgb_color_struct_t old = s_last_sent.colors[i];
		if (cur.red == old.red && cur.green == old.green
				&& cur.blue == old.blue)
			continue;

		s_ops[n].mem_addr = base_red_reg(i);
		s_ops[n].buf[0] = cur.red;
		s_ops[n].buf[1] = cur.green;
		s_ops[n].buf[2] = cur.blue;
		s_ops[n].len = 3;
		// Track pending update for confirmation after I2C success
		s_pending_colors.colors[i] = cur;
		s_pending_indices[s_pending_count++] = i;
		++n;
	}
#else
	for (uint8_t i = 0; i < 16 && n < OPS_CAP; ++i) {
		const rgb_color_struct_t cur = s_self->current_external_colors.colors[i];
		const rgb_color_struct_t old = s_last_sent.colors[i];

		// Check if this LED needs any update
		uint8_t needs_update = 0;
		if (cur.red != old.red && n < OPS_CAP) {
			s_ops[n++] = { (uint16_t) (ext_led_base_reg(i) + 1),
					{ cur.red, 0, 0 }, 1 };
			needs_update = 1;
		}
		if (cur.green != old.green && n < OPS_CAP) {
			s_ops[n++] = { (uint16_t) (ext_led_base_reg(i) + 2), { cur.green, 0,
					0 }, 1 };
			needs_update = 1;
		}
		if (cur.blue != old.blue && n < OPS_CAP) {
			s_ops[n++] = { (uint16_t) (ext_led_base_reg(i) + 3), { cur.blue, 0,
					0 }, 1 };
			needs_update = 1;
		}
		// Track pending update for this LED
		if (needs_update && s_pending_count < 16) {
			s_pending_colors.colors[i] = cur;
			s_pending_indices[s_pending_count++] = i;
		}
	}
#endif
	s_op_count = n;
	s_op_index = 0;
}

static void flush_kick_next() {
	if (!s_self)
		return;

	if (s_op_index >= s_op_count) {
		// Frame done successfully - commit pending colors to s_last_sent
		for (uint8_t i = 0; i < s_pending_count; ++i) {
			uint8_t idx = s_pending_indices[i];
			s_last_sent.colors[idx] = s_pending_colors.colors[idx];
		}
		s_pending_count = 0;

		s_in_progress = 0;
		if (s_pending) {
			s_pending = 0;
			flush_start(); // immediately send another frame with latest data
		}
		return;
	}

	ExtI2COp *op = &s_ops[s_op_index];

	HAL_StatusTypeDef st = HAL_I2C_Mem_Write_IT(s_self->config.hi2c,
	EXTENDER_ADDRESS, op->mem_addr,
	I2C_MEMADD_SIZE_8BIT, // change to I2C_MEMADD_SIZE_16BIT if your regs are 16-bit
			op->buf, op->len);

	if (st != HAL_OK) {
		// Simple policy: skip this op and continue.
		// You can add retries/backoff based on st and HAL_I2C_GetError().
		s_op_index = static_cast<uint8_t>(s_op_index + 1);
		flush_kick_next();
	}
}

static void flush_start() {
	// Called by setters after updating shadow colors
	if (!s_self)
		return;

	uint32_t ps = cs_enter();
	if (s_in_progress) {
		// A frame is currently being sent; mark that new data arrived
		s_pending = 1;
		cs_exit(ps);
		return;
	}
	s_in_progress = 1;
	cs_exit(ps);

	// Build ops from diffs and start
	flush_build_diff();

	if (s_op_count == 0) {
		// Nothing to send; clear progress
		s_in_progress = 0;
		return;
	}
	flush_kick_next();
}

// =========================== HAL Callbacks ========================

extern "C" void HAL_I2C_MemTxCpltCallback(I2C_HandleTypeDef *hi2c) {
	if (!s_self)
		return;
	if (hi2c == s_self->config.hi2c) {
		s_op_index = static_cast<uint8_t>(s_op_index + 1);
		flush_kick_next();
	}
}

extern "C" void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *hi2c) {
	if (!s_self)
		return;
	if (hi2c == s_self->config.hi2c) {
		// On error: abort the entire frame without confirming any colors.
		// This ensures colors will be retried on the next update cycle.
		s_pending_count = 0;  // Don't confirm any pending colors
		s_op_count = 0;       // Cancel remaining ops
		s_op_index = 0;
		s_in_progress = 0;

		// If there was a pending update request, allow it to start fresh
		if (s_pending) {
			s_pending = 0;
			flush_start();
		}
	}
}
