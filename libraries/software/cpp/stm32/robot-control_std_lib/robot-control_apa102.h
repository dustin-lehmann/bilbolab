/*
 * robot-control_apa102.h
 *
 *  Created on: Mar 13, 2026
 *      Author: lehmann
 */

#ifndef ROBOT_CONTROL_APA102_H_
#define ROBOT_CONTROL_APA102_H_
#include "apa102.h"
#include "robot-control_board.h"


#define ROBOT_CONTROL_APA102_NUM_LEDS 16


class RobotControlAPA102 {
public:
	RobotControlAPA102() = default;

	void init() {
		apa102_config_t config;
		config.hspi = LED_APA102_SPI;
		config.num_leds = ROBOT_CONTROL_APA102_NUM_LEDS;
		this->strip.init(config);
	}

	void setColor(uint16_t index, uint8_t r, uint8_t g, uint8_t b) {
		this->strip.setColor(index, r, g, b);
	}

	void setColor(uint16_t index, apa102_color_t color) {
		this->strip.setColor(index, color);
	}

	void setAllColors(uint8_t r, uint8_t g, uint8_t b) {
		this->strip.setAllColors(r, g, b);
	}

	void setAllColors(apa102_color_t color) {
		this->strip.setAllColors(color);
	}

	void setBrightness(uint8_t brightness) {
		this->strip.setBrightness(brightness);
	}

	void setBrightness(uint16_t index, uint8_t brightness) {
		this->strip.setBrightness(index, brightness);
	}

	void clear() {
		this->strip.clear();
	}

	void update() {
		this->strip.update();
	}

private:
	APA102 strip;
};

#endif /* ROBOT_CONTROL_APA102_H_ */
