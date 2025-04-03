/*
 * dynamixel.h
 *
 *  Created on: Jan 30, 2025
 *      Author: klvdw
 */

#ifndef ACTUATORS_DYNAMIXEL_H_
#define ACTUATORS_DYNAMIXEL_H

#define ULONG_MAX 0xffffffff

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

#define HANDLER_UART_NOTIFY_TIMEOUT 100
#define MOTOR_WAIT_FOR_HANDLER_TIMEOUT 300
#define MOTOR_ACQUIRE_MUTEX_TIMEOUT_IN_TASK 100


// delays
#define MOTOR_TASK_DELAY_BETWEEN_INDIVIDUAL_REQUEST 100





//Acquire
// Includes
#include "setting.h"
#include "core_hardware_UART.h"
#include "cmsis_os2.h"
#include "FreeRTOS.h"
#include "task.h"
//#include "queue.h"
//#include "semphr.h"

enum dynamixel_instruction_type_t {
	INSTRUCTION_PING = 0x01,
	INSTRUCTION_READ = 0x02,
	INSTRUCTION_WRITE = 0x03,
	INSTRUCTION_REGISTER_WRITE = 0x04,
	INSTRUCTION_ACTION = 0x05,
	INSTRUCTION_SYNC_WRITE = 0x83
};

typedef struct dynamixel_request_t {
	uint8_t motor_id; // the physical id configured in the servo
	dynamixel_instruction_type_t type;
	uint8_t write_buffer[REQUEST_WRITE_BUF_SIZE];
	uint16_t write_len;
	uint8_t read_buffer[REQUEST_READ_BUF_SIZE];
	uint16_t read_len;
	osThreadId_t thread_id;
	TaskHandle_t task_handle;
	bool success = false;
}dynamixel_request_t;

// Forward declarations
class DynamixelHandler;
//extern DynamixelHandler global_handler;



/*************************************************************************************************************************
 * Dynamixel Motor
 *
 */

/// Define a config for a single dynamixel motor
typedef struct dynamixel_config_t {

	core_hardware_UART<NUM_UART_QUEUES, UART_QUEUES_SIZE>* huart; ///< pointer to the core hardware UART object
	DynamixelHandler* handler; // the handler of this motor
	osMemoryPoolId_t request_mem_pool;
	uint8_t id; ///< ID of the dynamixel motor on the rs485 bus, maximum 253
	uint16_t profile_accel;
	uint16_t profile_velocity;

} dynamixel_config_t;


typedef enum dynamixel_operating_mode_t {
	DYNAMIXEL_CURRENT_CONTROL_MODE= 0,
	DYNAMIXEL_VELOCITY_CONTROL_MODE = 1,
	DYNAMIXEL_POSITION_CONTROL_MODE = 3,
	DYNAMIXEL_EXTENDED_POSITION_CONTROL_MODE = 4,
	DYNAMIXEL_CURRENT_BASED_POSITION_CONTROL_MODE = 5,
	DYNAMIXEL_PWM_CONTROL_MODE = 16
}dynamixel_operating_mode_t;

typedef enum dynamixel_motor_hardware_error_t {
	DYNAMIXEL_HARDWARE_ERROR_NONE = 0,
	DYNAMIXEL_HARDWARE_ERROR_VOLTAGE = 1,
	DYNAMIXEL_HARDWARE_ERROR_OVERHEATING = 2,
	DYNAMIXEL_HARDWARE_ERROR_ENCODER = 3,
	DYNAMIXEL_HARDWARE_ERROR_ELECTRICAL_SHOCK = 4,
	DYNAMIXEL_HARDWARE_ERROR_OVERLOAD = 5
}dynamixel_motor_hardware_error_t;

typedef enum dynamixel_communication_packet__error_t{
	DYNAMIXEL_COMM_ERROR_NONE = 0,
	DYNAMIXEL_COMM_ERROR_RESULT_FAIL = 1,
	DYNAMIXEL_COMM_ERROR_INSTRUCTION = 2,
	DYNAMIXEL_COMM_ERROR_CRC = 3,
	DYNAMIXEL_COMM_ERROR_DATA_RANGE = 4,
	DYNAMIXEL_COMM_ERROR_DATA_LENGTH = 5,
	DYNAMIXEL_COMM_ERROR_DATA_LIMIT = 6,
	DYNAMIXEL_COMM_ERROR_ACCESS = 7
}dynamixel_communication_packet__error_t;

typedef enum dynamixel_motor_status_t {
	DYNAMIXEL_MOTOR_IDLE,
	DYNAMIXEL_MOTOR_RUNNING,
	DYNAMIXEL_MOTOR_ERROR
}dynamixel_motor_status_t;


/**********************************
 * mutexes
*/
typedef struct dynamixel_motor_mut_t {
	osMutexId_t motor_id_mutex;
	osMutexId_t present_position_mutex;
	osMutexId_t goal_position_mutex;
	osMutexId_t hardware_error_mutex;
	osMutexId_t present_voltage_mutex;
	osMutexId_t present_temperature_mutex;
}dynamixel_motor_mut_t;


/// A single dynamixel motor
class DynamixelMotor {

public:
	DynamixelMotor(){

	}
	/// Management and general functions
	uint8_t init(dynamixel_config_t config);
	void start();
	void checkCommunication();
	dynamixel_motor_hardware_error_t checkHardwareError();

	// sending and writing functions
	void set_torque(bool torque_enable);
	void send_ping();
	void set_profile_accel(uint16_t accel);
	void set_profile_velocity(uint16_t velocity);
	void set_led(bool led_state);
	void send_position(uint32_t position);
	void send_position_register(uint32_t position);
	void send_action();

	// getter and read functions
	uint8_t get_id();
	float get_present_voltage();
	float get_present_temperature();
	uint32_t get_present_position();
	uint32_t get_goal_position();

	// For receiving status packets
	//void receive_callback(uint8_t *packet, uint16_t packet_len);
	uint8_t construct_request(dynamixel_instruction_type_t instruction, uint8_t *parameters, uint8_t parameter_len, uint8_t len_ctable_read, dynamixel_request_t* request);

private:

	uint32_t present_position;

	uint32_t goal_position;

	uint8_t hardware_error_status;

	float present_voltage;

	float present_temperature;

	dynamixel_config_t config;

	dynamixel_motor_mut_t motor_mutexes;

	void request_present_position();
	void request_goal_position();
	void request_voltage();
	void request_temperature();


	void set_parameters_write(uint8_t address, uint8_t length_in_controltable, void * write_data, uint8_t * parameter_buf);
	void set_parameters_read(uint8_t address, uint8_t length_in_controltable, uint8_t * parameter_buf);


	//uint8_t construct_request(dynamixel_instruction_type_t instruction, uint8_t *parameters, uint8_t parameter_len, uint8_t len_ctable_read, dynamixel_request_t* request);
	uint8_t send_request_to_handler(dynamixel_request_t* request);

	uint16_t getCheckSum(uint16_t crc_accum, uint8_t *data_blk_ptr, uint16_t data_blk_size);
	//uint8_t decode_packet(uint8_t * packet, uint16_t packet_len);
	HAL_StatusTypeDef process_read_request(BaseType_t status_returned,
			dynamixel_request_t *request, dynamixel_request_t *req_back,
			uint32_t * data_target, osMutexId_t mutex_for_data);
	// dynamixel_communication_packet__error_t process_status_packet(uint8_t * rx_data, uint16_t rx_length);


	static void motor_task(void*);

};

/*************************************************************************************************************************
 * Dynamixel Handler
 *
 */

/// a Config for a dynamixel handler
/// this handler manages several dynamixel motors
typedef struct dynamixel_handler_config_t {

	UART_HandleTypeDef* huart; ///< pointer to hardware uart handle
	osMemoryPoolId_t request_mem_pool; //the request pool used

} dynamixel_handler_config_t;


typedef enum dynamixel_handler_status_t{
	DYNAMIXEL_HANDLER_IDLE,
	DYNAMIXEL_HANDLER_STOP,
	DYNAMIXEL_HANDLER_RUNNING,
	DYNAMIXEL_HANDLER_ERROR

}dynamixel_handler_error_state_t;


typedef enum dynamixel_handler_error_t {


}dynamixel_handler_error_t;


// input type to enable or disable a bool val on one motor
typedef struct dynamixel_bool_state_single_motor_t {
	uint8_t motor; // index of the motor in the handler array starting from 0
	bool state;
}dynamixel_bool_state_single_motor_t;

// input type to send a position to a motor
typedef struct dynamixel_position_single_motor_t {
	uint8_t motor; // index of the motor in the handler array starting from 0
	uint32_t position;
}dynamixel_position_single_motor_t;

/// Manages multiple dynamixel motor classes
class DynamixelHandler {
public:
	DynamixelHandler(){
	}

	uint8_t init(dynamixel_handler_config_t config);
	void start();
	void set_torque_single_motor(dynamixel_bool_state_single_motor_t torque_config);
	void send_ping_single_motor(uint8_t motor);
	void set_led_single_motor(dynamixel_bool_state_single_motor_t led_config);
	void send_position_single_motor(dynamixel_position_single_motor_t position_config);
	void send_position_register_single_motor(dynamixel_position_single_motor_t position_config);
	void send_action_single_motor(uint8_t motor);

	float get_voltage_single_motor(uint8_t motor);
	float get_temperature_single_motor(uint8_t motor);

	uint32_t get_goal_position_single_motor(uint8_t motor);
	uint32_t get_present_position_single_motor(uint8_t motor);

	void set_torque_all_motors(bool torque_enable);
	void set_led_all_motors(bool led_state);
	void send_position_all_motors(uint32_t position);

	void get_goal_position_all_motors(uint32_t * position_array);
	void get_present_position_all_motors(uint32_t * position_array);

	uint8_t add_request(dynamixel_request_t * request);

private:
	osMessageQueueId_t request_queue;

	DynamixelMotor motors[NUM_DYNAMIXEL_MOTORS];

	dynamixel_handler_config_t config;
	core_hardware_UART<NUM_UART_QUEUES, UART_QUEUES_SIZE> uart;

	TaskHandle_t task_handle_dxl_handler;

	static void handler_task(void*);

	bool check_packet_header_crc(Buffer * buffer);

	uint8_t set_parameters_sync_write(uint16_t address, uint8_t len_in_ctable, void * write_data, uint8_t * parameter_buf);

	uint16_t getCheckSum(uint16_t crc_accum, uint8_t *data_blk_ptr, uint16_t data_blk_size);
	void uart_rx_callback();


	void _error_handler(uint32_t error);

};

#endif /* ACTUATORS_DYNAMIXEL_H_ */
