/*
 * apa102.cpp
 *
 *  Created on: Mar 13, 2026
 *      Author: lehmann
 */

#include "apa102.h"

/* ====================================================== */
APA102::APA102() {
}

/* ====================================================== */
void APA102::init(apa102_config_t config) {
	this->config = config;

	if (this->config.num_leds > APA102_MAX_LEDS) {
		this->config.num_leds = APA102_MAX_LEDS;
	}

	// Default: all LEDs off, full brightness
	for (uint16_t i = 0; i < this->config.num_leds; i++) {
		_colors[i] = {0, 0, 0};
		_brightness[i] = 31;
	}

	_frame_len = 0;
	memset(_tx_buf, 0, sizeof(_tx_buf));
}

/* ====================================================== */
void APA102::setColor(uint16_t index, uint8_t r, uint8_t g, uint8_t b) {
	if (index >= config.num_leds)
		return;
	_colors[index] = {r, g, b};
}

/* ====================================================== */
void APA102::setColor(uint16_t index, apa102_color_t color) {
	if (index >= config.num_leds)
		return;
	_colors[index] = color;
}

/* ====================================================== */
void APA102::setAllColors(uint8_t r, uint8_t g, uint8_t b) {
	for (uint16_t i = 0; i < config.num_leds; i++) {
		_colors[i] = {r, g, b};
	}
}

/* ====================================================== */
void APA102::setAllColors(apa102_color_t color) {
	for (uint16_t i = 0; i < config.num_leds; i++) {
		_colors[i] = color;
	}
}

/* ====================================================== */
void APA102::setBrightness(uint8_t brightness) {
	uint8_t b = brightness > 31 ? 31 : brightness;
	for (uint16_t i = 0; i < config.num_leds; i++) {
		_brightness[i] = b;
	}
}

/* ====================================================== */
void APA102::setBrightness(uint16_t index, uint8_t brightness) {
	if (index >= config.num_leds)
		return;
	_brightness[index] = brightness > 31 ? 31 : brightness;
}

/* ====================================================== */
void APA102::clear() {
	for (uint16_t i = 0; i < config.num_leds; i++) {
		_colors[i] = {0, 0, 0};
	}
}

/* ====================================================== */
void APA102::update() {
	_buildFrame();
	HAL_SPI_Transmit(config.hspi, _tx_buf, _frame_len, HAL_MAX_DELAY);
}

/* ====================================================== */
void APA102::_buildFrame() {
	uint16_t pos = 0;

	// Start frame: 4 bytes of 0x00
	_tx_buf[pos++] = 0x00;
	_tx_buf[pos++] = 0x00;
	_tx_buf[pos++] = 0x00;
	_tx_buf[pos++] = 0x00;

	// LED frames: [0xE0 | brightness(5bit)] [Blue] [Green] [Red]
	for (uint16_t i = 0; i < config.num_leds; i++) {
		_tx_buf[pos++] = 0xE0 | (_brightness[i] & 0x1F);
		_tx_buf[pos++] = _colors[i].b;
		_tx_buf[pos++] = _colors[i].g;
		_tx_buf[pos++] = _colors[i].r;
	}

	// End frame: ceil(num_leds / 2) bits of 1, padded to whole bytes.
	// In practice, (num_leds + 15) / 16 bytes of 0xFF, minimum 4.
	uint16_t end_bytes = (config.num_leds + 15) / 16;
	if (end_bytes < 4)
		end_bytes = 4;
	for (uint16_t i = 0; i < end_bytes; i++) {
		_tx_buf[pos++] = 0xFF;
	}

	_frame_len = pos;
}
