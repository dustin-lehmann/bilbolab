/*
 * io.cpp
 *
 *  Created on: Jan 17, 2025
 *      Author: lehmann
 */

#include "io.h"

core_hardware_LED rc_button_led_1(GPIOA, GPIO_PIN_0);
core_hardware_LED rc_button_led_2(GPIOA, GPIO_PIN_1);
core_hardware_Button side_button(GPIOC, GPIO_PIN_1);
core_hardware_Button off_button(GPIOC, GPIO_PIN_0);


void io_start() {
rc_button_led_1.on();
rc_button_led_2.on();
}
