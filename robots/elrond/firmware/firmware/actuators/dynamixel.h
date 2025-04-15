/*
 * dynamixel.h
 *
 *  Created on: Jan 30, 2025
 *      Author: klvdw
 */

#ifndef ACTUATORS_DYNAMIXEL_H_
#define ACTUATORS_DYNAMIXEL_H

#define ULONG_MAX 0xffffffff


//Acquire
// Includes
#include "setting.h"
#include "core_hardware_UART.h"
#include "cmsis_os2.h"
#include "FreeRTOS.h"
#include "task.h"
#include "twipr_communication.h"
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
	uint32_t profile_accel;
	uint32_t profile_velocity;

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
	DYNAMIXEL_MOTOR_HARDWARE_ERROR_NONE = 0,
	DYNAMIXEL_MOTOR_HARDWARE_ERROR_VOLTAGE = 1,
	DYNAMIXEL_MOTOR_HARDWARE_ERROR_OVERHEATING = 2,
	DYNAMIXEL_MOTOR_HARDWARE_ERROR_ENCODER = 3,
	DYNAMIXEL_MOTOR_HARDWARE_ERROR_ELECTRICAL_SHOCK = 4,
	DYNAMIXEL_MOTOR_HARDWARE_ERROR_OVERLOAD = 5,
	DYNAMIXEL_MOTOR_HARDWARE_ERROR_REACHABLE = 10, // own code when motor not reachable
	DYNAMIXEL_MOTOR_HARDWARE_ERROR_COMMS = 11 // there is a comm error call checkCommunication instead
}dynamixel_motor_hardware_error_t;

typedef enum dynamixel_communication_packet__error_t{
	DYNAMIXEL_MOTOR_COMM_ERROR_NONE = 0,
	DYNAMIXEL_MOTOR_COMM_ERROR_RESULT_FAIL = 1,
	DYNAMIXEL_MOTOR_COMM_ERROR_INSTRUCTION = 2,
	DYNAMIXEL_MOTOR_COMM_ERROR_CRC = 3,
	DYNAMIXEL_MOTOR_COMM_ERROR_DATA_RANGE = 4,
	DYNAMIXEL_MOTOR_COMM_ERROR_DATA_LENGTH = 5,
	DYNAMIXEL_MOTOR_COMM_ERROR_DATA_LIMIT = 6,
	DYNAMIXEL_MOTOR_COMM_ERROR_ACCESS = 7,
	DYNAMIXEL_MOTOR_COMM_ERROR_REACHABLE = 10 // own error code for no comm possible
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
	HAL_StatusTypeDef init(dynamixel_config_t config);
	HAL_StatusTypeDef start();

	void checkMotor();

	// sending and writing functions
	void set_torque(bool torque_enable);
	void send_ping();
	void set_profile_accel(uint32_t accel);
	void set_profile_velocity(uint32_t velocity);
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
	uint8_t construct_request(dynamixel_instruction_type_t instruction, uint8_t *parameters, uint8_t parameter_len, uint8_t len_ctable_read, bool set_type_to_read, dynamixel_request_t* request);

private:

	dynamixel_config_t config;
	dynamixel_operating_mode_t operating_mode;

	dynamixel_motor_status_t status;
	dynamixel_communication_packet__error_t comm_error;
	dynamixel_motor_hardware_error_t hardware_error;

	uint32_t present_position;
	uint32_t goal_position;

	uint16_t present_voltage;
	uint8_t present_temperature;

	dynamixel_motor_mut_t motor_mutexes;

	dynamixel_communication_packet__error_t checkCommunication();
	dynamixel_motor_hardware_error_t checkHardwareError();


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
	HAL_StatusTypeDef process_read_request(BaseType_t status_returned,
			dynamixel_request_t *request, dynamixel_request_t *req_back,
			uint16_t * data_target, osMutexId_t mutex_for_data);
	HAL_StatusTypeDef process_read_request(BaseType_t status_returned,
			dynamixel_request_t *request, dynamixel_request_t *req_back,
			uint8_t * data_target, osMutexId_t mutex_for_data);
	// dynamixel_communication_packet__error_t process_status_packet(uint8_t * rx_data, uint16_t rx_length);

	HAL_StatusTypeDef store_data_w_mutex(uint32_t * data_target,uint32_t * temp_data, osMutexId_t mutex);
	HAL_StatusTypeDef store_data_w_mutex(uint16_t * data_target,uint16_t * temp_data, osMutexId_t mutex);
	HAL_StatusTypeDef store_data_w_mutex(uint8_t * data_target,uint8_t * temp_data, osMutexId_t mutex);

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
	DYNAMIXEL_HANDLER_RUNNING,
	DYNAMIXEL_HANDLER_ERROR
}dynamixel_handler_status_t;


typedef enum dynamixel_handler_error_t {
	DYNAMIXEL_HANDLER_ERROR_NONE = 0,
	DYNAMIXEL_HANDLER_ERROR_MOTOR_ERROR = 1, // One of the motors is in error state that cannot be resolved (hardware etc.)
	DYNAMIXEL_HANDLER_ERROR_MOTOR_COMM = 2, // One of The motors has no connection or communication error
	DYNAMIXEL_HANDLER_ERROR_INTERNAL = 3, // error in handler, could be ressources(request queue etc.)
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
	dynamixel_handler_config_t config;
	DynamixelMotor motors[NUM_DYNAMIXEL_MOTORS];

	core_hardware_UART<NUM_UART_QUEUES, UART_QUEUES_SIZE> uart;
	TaskHandle_t task_handle_dxl_handler;

	osMessageQueueId_t request_queue;

	static void handler_task(void*);

	bool check_packet_header_crc(Buffer * buffer);

	uint8_t set_parameters_sync_write(uint16_t address, uint8_t len_in_ctable, void * write_data, uint8_t * parameter_buf);

	uint16_t getCheckSum(uint16_t crc_accum, uint8_t *data_blk_ptr, uint16_t data_blk_size);
	void uart_rx_callback();


	void _error_handler(uint32_t error);

};

#endif /* ACTUATORS_DYNAMIXEL_H_ */
