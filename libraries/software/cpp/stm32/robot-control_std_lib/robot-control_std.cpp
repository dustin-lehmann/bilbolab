/*
 * robot-control_std.cpp
 *
 *  Created on: Jul 29, 2022
 *      Author: Dustin Lehmann
 */

#include "robot-control_std.h"
#include <stdio.h>

//core_hardware_LED rc_status_led_1(BOARD_LED_1_PORT, BOARD_LED_1_PIN);
core_hardware_LED rc_status_led_2(BOARD_LED_2_PORT, BOARD_LED_2_PIN);



core_hardware_LED rc_activity_led(BOARD_LED_ACT_PORT, BOARD_LED_ACT_PIN);
RobotControl_StatusLED rc_error_led;

//core_hardware_Button button(BOARD_BUTTON_PORT, BOARD_BUTTON_PIN);

uint8_t board_revision = BOARD_REVISION;


RobotControl_Extender extender;
RobotControl_LEDStrip rc_led_strip;

RobotControl_RGBLED rc_rgb_led_status(0);
RobotControl_RGBLED rc_rgb_led_side_1(1);
RobotControl_RGBLED rc_rgb_led_side_2(2);



RobotControl_Buzzer rc_buzzer;



//core_debug_Interface debug(CORE_DEBUG_INTERFACE_UART, BOARD_DEBUG_UART);
Madgwick sensor_fusion;


//const osThreadAttr_t rc_task_attributes = { .name = "rc_default", .stack_size =
//		128 * 4, .priority = (osPriority_t) osPriorityHigh4, };


void robot_control_start();
void robot_control_sensor_task(void *argument);
void robot_control_task(void *argument);



// ------------------------------------------------------------------------------------------------------------
void robot_control_init(){
	extender_config_struct_t extender_config = {
			.hi2c = BOARD_I2C_INTERN,
	};
	extender.init(extender_config);

#ifdef LED_STRIP_APA102
	rc_led_strip.init();
#else
	rc_led_strip.extender = &extender;
#endif
}
// ------------------------------------------------------------------------------------------------------------
void robot_control_start(){
	rc_error_led.setState(0);

    rgb_color_struct_t color = {
    		.red = 0,
			.green = 0,
			.blue = 0,
    };
    rc_led_strip.setColor(color);

//	debug_uart.start();
//	osThreadNew(robot_control_task, NULL, &rc_task_attributes);
}

// ------------------------------------------------------------------------------------------------------------
void robot_control_task(void *argument){
//	debug.start();
	rc_error_led.setState(0);

	rc_buzzer.setConfig(440, 250, 1);
	rc_buzzer.start();


//
//    rgb_color_struct_t color = {
//    		.red = 0,
//			.green = 0,
//			.blue = 0,
//    };
//    extender.rgbLEDStrip_extern_setColor(color);


	uint32_t kernel_ticks = 0;
	while (true){
			kernel_ticks = osKernelGetTickCount();
//			rc_activity_led.toggle();
			osDelayUntil(kernel_ticks + (uint32_t) 250);
	}
}
