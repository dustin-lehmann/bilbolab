/*
 * robot-control_led_strip.h
 *
 * Unified external LED strip abstraction.
 * Dispatches to either the I2C extender (WS2812) or APA102 (SPI)
 * based on LED_STRIP_APA102 / LED_STRIP_I2C in firmware_settings.h.
 *
 *  Created on: Mar 13, 2026
 *      Author: lehmann
 */

#ifndef ROBOT_CONTROL_LED_STRIP_H_
#define ROBOT_CONTROL_LED_STRIP_H_

#include "firmware_settings.h"
#include "robot-control_extender.h"

#ifdef LED_STRIP_APA102
#include "robot-control_apa102.h"
#endif

#define RC_LED_STRIP_NUM_LEDS 16

class RobotControl_LEDStrip {
public:

	void init() {
#ifdef LED_STRIP_APA102
		apa102.init();
#endif
	}

	// Set all LEDs to the same color
	void setColor(rgb_color_struct_t color) {
#ifdef LED_STRIP_APA102
		apa102.setAllColors(color.red, color.green, color.blue);
		apa102.update();
#else
		extender->rgbLEDStrip_extern_setColor(color);
#endif
	}

	// Set a single pixel
	void setPixelColor(uint8_t index, uint8_t red, uint8_t green, uint8_t blue) {
#ifdef LED_STRIP_APA102
		apa102.setColor(index, red, green, blue);
		apa102.update();
#else
		extender->rgbLEDStrip_extern_setPixelColor(index, red, green, blue);
#endif
	}

	void setPixelColor(uint8_t index, rgb_color_struct_t color) {
		setPixelColor(index, color.red, color.green, color.blue);
	}

	// Set all LEDs individually
	void setAllColors(external_led_colors_struct_t colors) {
#ifdef LED_STRIP_APA102
		for (uint8_t i = 0; i < RC_LED_STRIP_NUM_LEDS; i++) {
			apa102.setColor(i, colors.colors[i].red,
					colors.colors[i].green, colors.colors[i].blue);
		}
		apa102.update();
#else
		extender->rgbLEDStrip_extern_setAllColors(colors);
#endif
	}

#ifdef LED_STRIP_APA102
	RobotControlAPA102 apa102;
#else
	RobotControl_Extender *extender = nullptr;
#endif
};

#endif /* ROBOT_CONTROL_LED_STRIP_H_ */
