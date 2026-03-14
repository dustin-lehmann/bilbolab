/*
 * robot-control_std.h
 *
 *  Created on: Jul 29, 2022
 *      Author: Dustin Lehmann
 */

#ifndef ROBOT_CONTROL_STD_H_
#define ROBOT_CONTROL_STD_H_

#include <core.h>
#include "robot-control_board.h"
#include "robot-control_default_config.h"
#include "robot-control_extender.h"
#include "robot-control_indicators.h"
#include "robot-control_led_strip.h"

extern core_hardware_LED rc_status_led_1;
extern core_hardware_LED rc_status_led_2;

extern core_hardware_LED rc_activity_led;

extern uint8_t board_revision;

extern RobotControl_RGBLED rc_rgb_led_status;
extern RobotControl_RGBLED rc_rgb_led_side_1;
extern RobotControl_RGBLED rc_rgb_led_side_2;
extern RobotControl_StatusLED rc_error_led;

extern RobotControl_Buzzer rc_buzzer;

extern core_hardware_Button button;



extern RobotControl_Extender extender;
extern RobotControl_LEDStrip rc_led_strip;

extern UART debug_uart;


void robot_control_init();
void robot_control_start();


#endif /* ROBOT_CONTROL_STD_H_ */
