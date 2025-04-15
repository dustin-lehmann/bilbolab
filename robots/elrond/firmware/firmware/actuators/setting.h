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
#define NUM_DYNAMIXEL_MOTORS 4

#define DYNAMIXEL_MOTOR_PROFILE_ACCEL 6
#define DYNAMIXEL_MOTOR_PROFILE_VELOCITY 15

#define LEN_REQUEST_QUEUE 10
#define REQUEST_BUFFERS_SIZE 1


#define ADDRESS_OPERATING_MODE 0x0B
#define ADDRESS_TORQUE_ENABLE 0x40
#define ADDRESS_LED 0x41
#define ADDRESS_HARDWARE_ERROR_STATUS 0x46
#define ADDRESS_PROFILE_ACCEL 0x6C
#define ADDRESS_PROFILE_VELOCITY 0x70
#define ADDRESS_GOAL_POSITION 0x74
#define ADDRESS_PRESENT_POSITION 0x84
#define ADDRESS_PRESENT_INPUT_VOLTAGE 0x90
#define ADDRESS_PRESENT_TEMPERATURE 0x92

// defines the length of the value in the control table
// of the servo in bytes
#define LEN_CTABLE_OPERATING_MODE 1U
#define LEN_CTABLE_TORQUE_EN 1U
#define LEN_CTABLE_LED 1U
#define LEN_CTABLE_HARDWARE_ERROR_STATUS 1U
#define LEN_CTABLE_PROFILE_ACCEL 4U
#define LEN_CTABLE_PROFILE_VELOCITY 4U
#define LEN_CTABLE_GOAL_POSITION 4U
#define LEN_CTABLE_PRESENT_POSITION 4U
#define LEN_CTABLE_INPUT_VOLTAGE 2U
#define LEN_CTABLE_TEMPERATURE 1U

//length of full packet is 4bytes header and reserved + 1byte ID +
// 2bytes length declaration + 1byte instruction + 0-255bytes parameters + 2bytes checksum = 10 + length of parameters
#define LEN_INSTRUC_PACKET_NO_PARAMETERS 10U
#define LEN_STATUS_PACKET_NO_PARAMETERS 11U //status packet has one byte more, the error field
#define LEN_PARAMETER_BUF_READ 4U //standard length of the parameter buf for a read request

// Define the motors
// number corresponds to the index
// of the motor in the motors array in the handler
#define FRONT_LEFT_MOTOR 0
#define BACK_LEFT_MOTOR 1
#define FRONT_RIGHT_MOTOR 2
#define BACK_RIGHT_MOTOR 3

// Buffer configuration
#define REQUEST_WRITE_BUF_SIZE 64    // Dynamixel max TX packet size
#define REQUEST_READ_BUF_SIZE 128   // Dynamixel max RX packet size
#define REQUEST_POOL_SIZE 15	// available buffers in memory pool


// timeouts
#define REQUEST_SEND_TIMEOUT 100 // timeout of the message queue put function
// Deprecated #define REQUEST_GET_TIMEOUT 100 // timeout for getting a message out of the queue

#define REQUEST_POOL_ALLOC_TIMEOUT 10

#define HANDLER_UART_NOTIFY_TIMEOUT 30
#define MOTOR_WAIT_FOR_HANDLER_TIMEOUT 300
#define MOTOR_ACQUIRE_MUTEX_TIMEOUT_IN_TASK 20


// delays
#define MOTOR_TASK_DELAY_BETWEEN_INDIVIDUAL_REQUEST 100


#endif /* SETTING_H_ */
