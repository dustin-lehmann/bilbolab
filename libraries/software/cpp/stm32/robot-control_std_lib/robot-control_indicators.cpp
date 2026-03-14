/*
 * robot-control_indicators.cpp
 *
 *  Created on: Apr 24, 2024
 *      Author: Dustin Lehmann
 */

#include "robot-control_indicators.h"
#include "robot-control_led_strip.h"

extern RobotControl_Extender extender;

RobotControl_RGBLED::RobotControl_RGBLED(uint8_t position) {
	this->position = position;
}

void RobotControl_RGBLED::setColor(uint8_t red, uint8_t green, uint8_t blue) {
	extender.rgbLED_intern_setColor(position, red, green, blue);

}
void RobotControl_RGBLED::blink(uint16_t on_time) {
	extender.rgbLED_intern_blink(position, on_time);
}
void RobotControl_RGBLED::state(uint8_t state) {
	extender.rgbLED_intern_setState(position, state);
}

RobotControl_Buzzer::RobotControl_Buzzer() {

}

void RobotControl_Buzzer::setConfig(float freq, uint16_t on_time,
		uint8_t repeats) {
	extender.buzzer_setConfig(freq, on_time, repeats);
}
void RobotControl_Buzzer::start() {
	extender.buzzer_start();
}

void RobotControl_Buzzer::beep(float freq, uint16_t on_time, uint8_t repeats){
	this->setConfig(freq, on_time, repeats);
	this->start();
}
void RobotControl_Buzzer::beep(buzzer_beep_struct_t data){
	this->setConfig(data.freq, data.on_time, data.repeats);
	rc_status_led_2.toggle();
	this->start();
}

RobotControl_StatusLED::RobotControl_StatusLED() {

}
void RobotControl_StatusLED::setState(int8_t state) {
	extender.setStatusLED(state);
}


extern RobotControl_LEDStrip rc_led_strip;

RobotControl_ExternalRGBStrip::RobotControl_ExternalRGBStrip() {

}

void RobotControl_ExternalRGBStrip::setColor(uint8_t red, uint8_t green, uint8_t blue){

	rgb_color_struct_t color = {
			.red = red,
			.green = green,
			.blue = blue
	};
	rc_led_strip.setColor(color);
}

