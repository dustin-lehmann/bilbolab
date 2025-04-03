/*
 * setting.h
 *
 *  Created on: Jan 29, 2025
 *      Author: Dustin Lehmann
 */

#ifndef SETTING_H_
#define SETTING_H_

// Communication related settings
#define NUM_UART_QUEUES 5
#define UART_QUEUES_SIZE 128

// Actuator related settings

// Dynamixel settings
#define NUM_DYNAMIXEL_MOTORS 2

#define DYNAMIXEL_MOTOR_PROFILE_ACCEL 6
#define DYNAMIXEL_MOTOR_PROFILE_VELOCITY 15

#define LEN_REQUEST_QUEUE 10
#define REQUEST_BUFFERS_SIZE 1

#endif /* SETTING_H_ */
