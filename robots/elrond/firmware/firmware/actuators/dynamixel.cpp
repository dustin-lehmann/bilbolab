/*
 * dynamixel.cpp
 *
 *  Created on: Jan 30, 2025
 *      Author: klvdw
 */
#include "dynamixel.h"
#include <stdio.h>


/*************************************************************************************************************************
 * Dynamixel Motor
 *
 */

const osThreadAttr_t motor_task_attributes = { .name = "Dxl_Motor",
		.stack_size = 2560, .priority = (osPriority_t) osPriorityBelowNormal, };

/*public*/
uint8_t DynamixelMotor::init(dynamixel_config_t config) {

	//load config into class member
	this->config = config;

	//create the mutexes for member variables
	this->motor_mutexes.motor_id_mutex = osMutexNew(NULL);
	this->motor_mutexes.present_position_mutex = osMutexNew(NULL);
	this->motor_mutexes.goal_position_mutex = osMutexNew(NULL);
	this->motor_mutexes.hardware_error_mutex = osMutexNew(NULL);
	this->motor_mutexes.present_voltage_mutex = osMutexNew(NULL);
	this->motor_mutexes.present_temperature_mutex = osMutexNew(NULL);

	//create the motor task
	osThreadNew(motor_task, this, &motor_task_attributes);

	// success
	return 0;
}

void DynamixelMotor::start() {
	//
}

void DynamixelMotor::checkCommunication() {
}

dynamixel_motor_hardware_error_t DynamixelMotor::checkHardwareError() {

	return DYNAMIXEL_HARDWARE_ERROR_NONE;

}

void DynamixelMotor::send_ping() {

	// construct a ping packet, no parameters
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	construct_request(INSTRUCTION_PING, 0, 0, 0, request);
	//send the packet
	send_request_to_handler(request);

}

void DynamixelMotor::set_led(bool led_state) {

	// set the length of the parameter in bytes
	uint8_t parameter_len = 3;
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set the address, length , data etc.
	set_parameters_write(ADDRESS_LED, LEN_CTABLE_LED, &led_state,
			parameter_buf);

	//construct a packet
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	construct_request(INSTRUCTION_WRITE, parameter_buf, parameter_len, 0,
			request);

	//send the packet
	send_request_to_handler(request);

}

void DynamixelMotor::set_torque(bool torque_enable = 0) {

	// set the length of the parameter in bytes
	uint8_t parameter_len = 3;
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set the address, length , data etc.
	set_parameters_write(ADDRESS_TORQUE_ENABLE, LEN_CTABLE_TORQUE_EN,
			&torque_enable, parameter_buf);

	//construct a packet
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	construct_request(INSTRUCTION_WRITE, parameter_buf, parameter_len, 0,
			request);

	//send the packet
	send_request_to_handler(request);
}

void DynamixelMotor::set_profile_accel(uint16_t accel) {

	// set the length of the parameter in bytes
	uint8_t parameter_len = 6;
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set the address, length , data etc.
	set_parameters_write(ADDRESS_PROFILE_ACCEL, LEN_CTABLE_PROFILE_ACCEL, &accel ,parameter_buf);

	//construct a packet
	dynamixel_request_t* request = (dynamixel_request_t*)osMemoryPoolAlloc(this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	construct_request(INSTRUCTION_WRITE, parameter_buf, parameter_len,0, request);

	//send the packet
	send_request_to_handler(request);
}

void DynamixelMotor::set_profile_velocity(uint16_t velocity) {

	// set the length of the parameter in bytes
	uint8_t parameter_len = 6;
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set the address, length etc.
	set_parameters_write(ADDRESS_PROFILE_VELOCITY, LEN_CTABLE_PROFILE_VELOCITY, &velocity ,parameter_buf);

	//construct a packet
	dynamixel_request_t* request = (dynamixel_request_t*)osMemoryPoolAlloc(this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	construct_request(INSTRUCTION_WRITE, parameter_buf, parameter_len,0, request);

	//send the packet
	send_request_to_handler(request);
}


void DynamixelMotor::send_position(uint32_t position) {

	// set the length of the parameter in bytes
	uint8_t parameter_len = 6;
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set the address, length etc.
	set_parameters_write(ADDRESS_GOAL_POSITION, LEN_CTABLE_GOAL_POSITION,
			&position, parameter_buf);

	//construct a packet
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	construct_request(INSTRUCTION_WRITE, parameter_buf, parameter_len, 0,
			request);

	//send the packet
	send_request_to_handler(request);

}

void DynamixelMotor::send_position_register(uint32_t position) {

	// set the length of the parameter in bytes
	uint8_t parameter_len = 6;
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set the address, length etc.
	set_parameters_write(ADDRESS_GOAL_POSITION, LEN_CTABLE_GOAL_POSITION,
			&position, parameter_buf);

	//construct a packet
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	construct_request(INSTRUCTION_REGISTER_WRITE, parameter_buf, parameter_len,
			0, request);

	//send the packet
	send_request_to_handler(request);
}

void DynamixelMotor::send_action() {

	// construct a action packet, no parameters
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	construct_request(INSTRUCTION_ACTION, 0, 0, 0, request);

	//send the packet
	send_request_to_handler(request);
}

uint8_t DynamixelMotor::get_id() {

	// return the id
	return this->config.id;
}

float DynamixelMotor::get_present_voltage() {

	osStatus_t status = osMutexAcquire(
			this->motor_mutexes.present_voltage_mutex, 0);
	if (status == osOK) {
		float voltage = this->present_voltage;
		osMutexRelease(this->motor_mutexes.goal_position_mutex);
		return voltage;
	} else {
		// mutex not available
		return 0;
	}
}

float DynamixelMotor::get_present_temperature() {

	osStatus_t status = osMutexAcquire(
			this->motor_mutexes.present_temperature_mutex, 0);
	if (status == osOK) {
		float temperature = this->present_temperature;
		osMutexRelease(this->motor_mutexes.present_temperature_mutex);
		return temperature;
	} else {
		// mutex not available
		return 0;
	}
}

uint32_t DynamixelMotor::get_present_position() {

	osStatus_t status = osMutexAcquire(
			this->motor_mutexes.present_position_mutex, 0);
	if (status == osOK) {
		uint32_t pos = this->present_position;
		osMutexRelease(this->motor_mutexes.present_position_mutex);
		return pos;
	} else {
		// mutex not available
		return 0;
	}

}

uint32_t DynamixelMotor::get_goal_position() {

	osStatus_t status = osMutexAcquire(this->motor_mutexes.goal_position_mutex,
			0);
	if (status == osOK) {
		uint32_t pos = this->goal_position;
		osMutexRelease(this->motor_mutexes.goal_position_mutex);
		return pos;
	} else {
		// mutex not available
		return 0;
	}

}

/******************************************************************************************
 * Private Methods
 */

void DynamixelMotor::request_present_position() {

	// set the length of the parameter in bytes
	uint8_t parameter_len = 4;
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set the parameters
	set_parameters_read(ADDRESS_PRESENT_POSITION, LEN_CTABLE_PRESENT_POSITION,
			parameter_buf);

	// construct a read packet
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	construct_request(INSTRUCTION_READ, parameter_buf, parameter_len,
			LEN_CTABLE_PRESENT_POSITION, request);

	//send the packet
	send_request_to_handler(request);

	// wait for the notification by the handler
	// the handler updates the request and transfers uart data into the read buffer
	// handler returns a pointer to the processed request
	dynamixel_request_t *req_back = nullptr;
	BaseType_t status_returned = pdFALSE;
	status_returned = xTaskNotifyWait(0, ULONG_MAX, (uint32_t*) &req_back,
			MOTOR_WAIT_FOR_HANDLER_TIMEOUT);

	process_read_request(status_returned, request, req_back, &this->present_position, this->motor_mutexes.present_position_mutex);

	// return request to the memory pool
	osMemoryPoolFree(this->config.request_mem_pool, request);

}

void DynamixelMotor::request_goal_position() {

	// set the length of the parameter in bytes
	uint8_t parameter_len = 4;
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	set_parameters_read(ADDRESS_GOAL_POSITION, LEN_CTABLE_GOAL_POSITION,
			parameter_buf);

	// construct a read packet
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT); // get a request from the pool
	construct_request(INSTRUCTION_READ, parameter_buf, parameter_len,
			LEN_CTABLE_GOAL_POSITION, request);

	//send the packet
	send_request_to_handler(request);

	// wait for the notification by the handler
	// the handler updates the request and transfers uart data into the read buffer
	// handler returns a pointer to the processed request
	dynamixel_request_t *req_back = nullptr;
	BaseType_t status_returned = pdFALSE;
	status_returned = xTaskNotifyWait(0, ULONG_MAX, (uint32_t*) &req_back,
			MOTOR_WAIT_FOR_HANDLER_TIMEOUT);

	// status = read_handler(status_returned, request, req_back, data_to_write_to, mutexforthat)
	// process_read_request(status_returned, request, req_back, data_to_write_to, mutexforthat)
	// check if there was a notification to take or if there was a timeout
	if (status_returned) {
		// check if own request is the same address as received request adress
		if (request == req_back) {

			//check if the handler had success
			if (request->success) {

				// decode the position from the request
				uint8_t *read_data = request->read_buffer;
				uint32_t goal_position = ((uint32_t) read_data[12] << 24)
						|   // Most significant byte
						((uint32_t) read_data[11] << 16)
						| ((uint32_t) read_data[10] << 8)
						| (uint32_t) read_data[9];     // Least significant byte

				// store the position
				osStatus_t status = osMutexAcquire(
						this->motor_mutexes.goal_position_mutex,
						MOTOR_ACQUIRE_MUTEX_TIMEOUT_IN_TASK);
				if (status == osOK) {
					this->goal_position = goal_position;
					osMutexRelease(this->motor_mutexes.goal_position_mutex);
				} else {
					// mutex not available
				}

			} else {

				//handler received wrong id or something else
			}

		} else {
			// request addresses dont match

		}

	} else {

		// there was a timeout waiting for the handler
	}

	// return request to the memory pool
	osMemoryPoolFree(this->config.request_mem_pool, request);

}

void DynamixelMotor::request_voltage() {

	// set the length of the parameter in bytes
	uint8_t parameter_len = 4;
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set the parameters
	set_parameters_read(ADDRESS_PRESENT_INPUT_VOLTAGE, LEN_CTABLE_INPUT_VOLTAGE,
			parameter_buf);

	// construct a read packet
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	construct_request(INSTRUCTION_READ, parameter_buf, parameter_len,
			LEN_CTABLE_INPUT_VOLTAGE, request);

	//send the packet
	send_request_to_handler(request);

	// wait for the notification by the handler
	// the handler updates the request and transfers uart data into the read buffer
	// handler returns a pointer to the processed request
	dynamixel_request_t *req_back = nullptr;
	BaseType_t status_returned = pdFALSE;
	status_returned = xTaskNotifyWait(0, ULONG_MAX, (uint32_t*) &req_back,
			MOTOR_WAIT_FOR_HANDLER_TIMEOUT);

	// check if there was a notification to take or if there was a timeout
	if (status_returned) {
		// check if own request is the same address as received request adress
		if (request == req_back) {

			//check if the handler had success
			if (request->success) {

				// decode the data from the request
				uint8_t *read_data = &request->read_buffer[9];

				uint16_t input_voltage;

				for (uint8_t i = 0; i < LEN_CTABLE_INPUT_VOLTAGE; i++) {

					input_voltage |= (uint16_t) read_data[i] << (8 * i);
				}

				// store the voltage
				osStatus_t status = osMutexAcquire(
						this->motor_mutexes.present_voltage_mutex,
						MOTOR_ACQUIRE_MUTEX_TIMEOUT_IN_TASK);
				if (status == osOK) {
					this->present_voltage = input_voltage * 0.1f;
					osMutexRelease(this->motor_mutexes.present_voltage_mutex);
				} else {
					// mutex not available
				}

			} else {

				//handler had no success
				// return the request to pool

			}

		} else {
			// request addresses dont match

		}

	} else {

		// there was a timeout waiting for the handler
	}

	// return request to the memory pool
	osMemoryPoolFree(this->config.request_mem_pool, request);

}

void DynamixelMotor::request_temperature() {

	// set the length of the parameter in bytes
	uint8_t parameter_len = 4;
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set the parameters
	set_parameters_read(ADDRESS_PRESENT_TEMPERATURE, LEN_CTABLE_TEMPERATURE,
			parameter_buf);

	// construct a read packet
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	construct_request(INSTRUCTION_READ, parameter_buf, parameter_len,
			LEN_CTABLE_TEMPERATURE, request);

	//send the packet
	send_request_to_handler(request);

	// wait for the notification by the handler
	// the handler updates the request and transfers uart data into the read buffer
	// handler returns a pointer to the processed request
	dynamixel_request_t *req_back = nullptr;
	BaseType_t status_returned = pdFALSE;
	status_returned = xTaskNotifyWait(0, ULONG_MAX, (uint32_t*) &req_back,
			MOTOR_WAIT_FOR_HANDLER_TIMEOUT);

	// check if there was a notification to take or if there was a timeout
	if (status_returned) {
		// check if own request is the same address as received request adress
		if (request == req_back) {

			//check if the handler had success
			if (request->success) {

				// decode the data from the request
				uint8_t *read_data = &request->read_buffer[9];

				uint8_t present_temperature = read_data[0];

				// store the temp
				osStatus_t status = osMutexAcquire(
						this->motor_mutexes.present_temperature_mutex,
						MOTOR_ACQUIRE_MUTEX_TIMEOUT_IN_TASK);
				if (status == osOK) {
					this->present_voltage = present_temperature;
					osMutexRelease(
							this->motor_mutexes.present_temperature_mutex);
				} else {
					// mutex not available
				}

			} else {

				//handler had no success
				// return the request to pool

			}

		} else {
			// request addresses dont match

		}

	} else {

		// there was a timeout waiting for the handler
	}

	// return request to the memory pool
	osMemoryPoolFree(this->config.request_mem_pool, request);

}

void DynamixelMotor::set_parameters_write(uint8_t address,
		uint8_t length_in_controltable, void *write_data,
		uint8_t *parameter_buf) {

	// set the address
	// in little endian format
	parameter_buf[0] = (address & 0x00ff);
	parameter_buf[1] = (address >> 8) & 0x00ff;

	// depending on length of data to be written
	// cast to different type and set data
	switch (length_in_controltable) {
	case 1:
		// data is just one byte
		// cast the void pointer to uint8t * the dereference
		parameter_buf[2] = *(uint8_t*) write_data;
		break;

	case 2:
		// set the data
		// convert to little endian format
		for (uint8_t i = 0; i < length_in_controltable; i++) {

			parameter_buf[2 + i] =
					((*(uint16_t*) write_data >> (8 * i)) & 0xff);
		}
		break;

	case 4:
		// set the data
		// convert to little endian format
		for (uint8_t i = 0; i < length_in_controltable; i++) {

			parameter_buf[2 + i] =
					((*(uint32_t*) write_data >> (8 * i)) & 0xff);
		}
		break;

	default:

		// not supported data length
		break;
	}
}

void DynamixelMotor::set_parameters_read(uint8_t address,
		uint8_t length_in_controltable, uint8_t *parameter_buf) {

	// set the address
	// in little endian format
	parameter_buf[0] = (address & 0x00ff);
	parameter_buf[1] = (address >> 8) & 0x00ff;

	// set the length in bytes to be read
	parameter_buf[2] = (length_in_controltable & 0x00ff);
	parameter_buf[3] = (length_in_controltable >> 8) & 0x00ff;

}

/// makes a packet for protocol 2.0 and bundles it into a request
uint8_t DynamixelMotor::construct_request(
		dynamixel_instruction_type_t instruction, uint8_t *parameters,
		uint8_t parameter_len, uint8_t len_ctable_read,
		dynamixel_request_t *request) {

	//length of full packet is 4bytes header and reserved + 1byte ID +
	// 2bytes length declaration + 1byte instruction + 0-255bytes parameters + 2bytes checksum = 10 + length of parameters

	// set header and reserved byte
	request->write_buffer[0] = 0xFF;
	request->write_buffer[1] = 0xFF;
	request->write_buffer[2] = 0xFD;
	request->write_buffer[3] = 0x00;

	// set id
	// if its sync write use broadcast id
	if (instruction == INSTRUCTION_SYNC_WRITE) {

		request->write_buffer[4] = 0xFE;
	} else {

		osStatus_t status = osMutexAcquire(this->motor_mutexes.motor_id_mutex,
				MOTOR_ACQUIRE_MUTEX_TIMEOUT_IN_TASK);
		if (status == osOK) {
			request->write_buffer[4] = this->config.id;
			osMutexRelease(this->motor_mutexes.motor_id_mutex);
		} else {
			// mutex not available
			return 1;
		}
	}

	// set length
	uint16_t length = 3 + parameter_len; // 1byte instruction + 0-255bytes parameters + 2bytes crc
	request->write_buffer[5] = (length & 0x00FF);
	request->write_buffer[6] = (length >> 8) & 0x00FF;

	// set instruction
	request->write_buffer[7] = instruction;

	// set the parameters
	// if there are any
	if (parameter_len != 0) {
		for (uint8_t i = 0; i < parameter_len; i++) {
			// transfer given parameters byte-wise to the packet
			request->write_buffer[8 + i] = *(parameters + i);
		}
	}

	// get the checksum
	uint16_t crc = getCheckSum(0 /*starting sum is 0*/, request->write_buffer,
			8 + parameter_len /*length of the packet without checksum*/);

	// set crc in little endian notation
	request->write_buffer[8 + parameter_len] = (crc & 0x00ff); //write lower byte in buffer
	request->write_buffer[9 + parameter_len] = (crc >> 8) & 0x00ff; // write higher byte

	// bundle the rest of the request
	request->motor_id = this->config.id;
	request->type = instruction;
	request->write_len = (uint16_t) (LEN_INSTRUC_PACKET_NO_PARAMETERS
			+ parameter_len);
	request->read_len = (uint16_t) (LEN_STATUS_PACKET_NO_PARAMETERS
			+ len_ctable_read);
	request->thread_id = osThreadGetId();
	request->task_handle = xTaskGetCurrentTaskHandle();
	request->success = false;

	return 0;
}

uint8_t DynamixelMotor::send_request_to_handler(dynamixel_request_t *request) {

	uint8_t status = this->config.handler->add_request(request);
	if (status > 0) {
		// there was an error
		return 1;
	} else {

		// request was added
		return 0;
	}
}

uint16_t DynamixelMotor::getCheckSum(uint16_t crc_accum, uint8_t *data_blk_ptr,
		uint16_t data_blk_size) {
	uint16_t i, j;
	uint16_t crc_table[256] = { 0x0000, 0x8005, 0x800F, 0x000A, 0x801B, 0x001E,
			0x0014, 0x8011, 0x8033, 0x0036, 0x003C, 0x8039, 0x0028, 0x802D,
			0x8027, 0x0022, 0x8063, 0x0066, 0x006C, 0x8069, 0x0078, 0x807D,
			0x8077, 0x0072, 0x0050, 0x8055, 0x805F, 0x005A, 0x804B, 0x004E,
			0x0044, 0x8041, 0x80C3, 0x00C6, 0x00CC, 0x80C9, 0x00D8, 0x80DD,
			0x80D7, 0x00D2, 0x00F0, 0x80F5, 0x80FF, 0x00FA, 0x80EB, 0x00EE,
			0x00E4, 0x80E1, 0x00A0, 0x80A5, 0x80AF, 0x00AA, 0x80BB, 0x00BE,
			0x00B4, 0x80B1, 0x8093, 0x0096, 0x009C, 0x8099, 0x0088, 0x808D,
			0x8087, 0x0082, 0x8183, 0x0186, 0x018C, 0x8189, 0x0198, 0x819D,
			0x8197, 0x0192, 0x01B0, 0x81B5, 0x81BF, 0x01BA, 0x81AB, 0x01AE,
			0x01A4, 0x81A1, 0x01E0, 0x81E5, 0x81EF, 0x01EA, 0x81FB, 0x01FE,
			0x01F4, 0x81F1, 0x81D3, 0x01D6, 0x01DC, 0x81D9, 0x01C8, 0x81CD,
			0x81C7, 0x01C2, 0x0140, 0x8145, 0x814F, 0x014A, 0x815B, 0x015E,
			0x0154, 0x8151, 0x8173, 0x0176, 0x017C, 0x8179, 0x0168, 0x816D,
			0x8167, 0x0162, 0x8123, 0x0126, 0x012C, 0x8129, 0x0138, 0x813D,
			0x8137, 0x0132, 0x0110, 0x8115, 0x811F, 0x011A, 0x810B, 0x010E,
			0x0104, 0x8101, 0x8303, 0x0306, 0x030C, 0x8309, 0x0318, 0x831D,
			0x8317, 0x0312, 0x0330, 0x8335, 0x833F, 0x033A, 0x832B, 0x032E,
			0x0324, 0x8321, 0x0360, 0x8365, 0x836F, 0x036A, 0x837B, 0x037E,
			0x0374, 0x8371, 0x8353, 0x0356, 0x035C, 0x8359, 0x0348, 0x834D,
			0x8347, 0x0342, 0x03C0, 0x83C5, 0x83CF, 0x03CA, 0x83DB, 0x03DE,
			0x03D4, 0x83D1, 0x83F3, 0x03F6, 0x03FC, 0x83F9, 0x03E8, 0x83ED,
			0x83E7, 0x03E2, 0x83A3, 0x03A6, 0x03AC, 0x83A9, 0x03B8, 0x83BD,
			0x83B7, 0x03B2, 0x0390, 0x8395, 0x839F, 0x039A, 0x838B, 0x038E,
			0x0384, 0x8381, 0x0280, 0x8285, 0x828F, 0x028A, 0x829B, 0x029E,
			0x0294, 0x8291, 0x82B3, 0x02B6, 0x02BC, 0x82B9, 0x02A8, 0x82AD,
			0x82A7, 0x02A2, 0x82E3, 0x02E6, 0x02EC, 0x82E9, 0x02F8, 0x82FD,
			0x82F7, 0x02F2, 0x02D0, 0x82D5, 0x82DF, 0x02DA, 0x82CB, 0x02CE,
			0x02C4, 0x82C1, 0x8243, 0x0246, 0x024C, 0x8249, 0x0258, 0x825D,
			0x8257, 0x0252, 0x0270, 0x8275, 0x827F, 0x027A, 0x826B, 0x026E,
			0x0264, 0x8261, 0x0220, 0x8225, 0x822F, 0x022A, 0x823B, 0x023E,
			0x0234, 0x8231, 0x8213, 0x0216, 0x021C, 0x8219, 0x0208, 0x820D,
			0x8207, 0x0202 };

	for (j = 0; j < data_blk_size; j++) {
		i = ((uint16_t) (crc_accum >> 8) ^ data_blk_ptr[j]) & 0xFF;
		crc_accum = (crc_accum << 8) ^ crc_table[i];
	}

	return crc_accum;

}

HAL_StatusTypeDef DynamixelMotor::process_read_request(BaseType_t status_returned,
		dynamixel_request_t *request, dynamixel_request_t *req_back,
		uint32_t * data_target, osMutexId_t mutex_for_data) {

	// check if there was a notification to take or if there was a timeout
	if (status_returned) {
		// check if own request is the same address as received request adress
		if (request == req_back) {

			//check if the handler had success
			if (request->success) {

				// decode the data from the request
				uint8_t *read_data = request->read_buffer;
				uint32_t temp_data_target =
						((uint32_t) read_data[12] << 24) |   // Most significant byte
						((uint32_t) read_data[11] << 16)
						| ((uint32_t) read_data[10] << 8)
						| (uint32_t) read_data[9];     // Least significant byte

				// store the data
				osStatus_t status = osMutexAcquire(mutex_for_data, MOTOR_ACQUIRE_MUTEX_TIMEOUT_IN_TASK);
				if (status == osOK) {
					*(data_target) = temp_data_target;
					osMutexRelease(mutex_for_data);
				} else {
					// mutex not available
					return HAL_ERROR;
				}

			} else {

				//handler had no success
				return HAL_ERROR;

			}

		} else {
			// request addresses dont match
			return HAL_ERROR;
		}

	} else {

		// there was a timeout waiting for the handler
		return HAL_ERROR;
	}
	return HAL_OK;
}

void DynamixelMotor::motor_task(void *argument) {

	DynamixelMotor *motor = static_cast<DynamixelMotor*>(argument);
	osDelay(300);

	while (1) {

		// just update the positions and other values periodically
		motor->request_present_position();
		osDelay(MOTOR_TASK_DELAY_BETWEEN_INDIVIDUAL_REQUEST);
		motor->request_goal_position();
		osDelay(MOTOR_TASK_DELAY_BETWEEN_INDIVIDUAL_REQUEST);
		//motor->request_voltage();
		osDelay(MOTOR_TASK_DELAY_BETWEEN_INDIVIDUAL_REQUEST);
		//motor->request_temperature();
		osDelay(MOTOR_TASK_DELAY_BETWEEN_INDIVIDUAL_REQUEST);

	}

}

// decodes a given packet and returns a number for switch
// writes address and contents
/*
 uint8_t DynamixelMotor::decode_packet(uint8_t *packet, uint16_t packet_len) {

 //retreive address from packet
 uint16_t address = (packet[9]<<8) | packet[10];

 // retrieve


 }
 */

/*************************************************************************************************************************
 * Dynamixel Handler
 *
 */

const osThreadAttr_t handler_task_attributes = { .name = "Dxl_Handler",
		.stack_size = 2560 * 2, .priority =
				(osPriority_t) osPriorityBelowNormal1, };

uint8_t DynamixelHandler::init(dynamixel_handler_config_t config) {

	this->config = config; // copy given config

	// create own uart config
	core_hardware_UART_config uart_config = { .mode =
			CORE_HARDWARE_UART_MODE_DMA, //use DMA for uart communication
			.cobs_encode_rx = 0, // transmitting no co byte stuffing
			.cobs_encode_tx = 0, // receving no co byte stuffing
			.queues = true // use a queue
			};

	// start the config of uart hardware
	this->uart.init(this->config.huart, uart_config);

	// set the callback method of dynamixel handler as callback for uart
	this->uart.registerCallback(CORE_HARDWARE_UART_CB_RX,
			core_utils_Callback<void, void>(this,
					&DynamixelHandler::uart_rx_callback));

	for (uint8_t i = 1; i < (NUM_DYNAMIXEL_MOTORS + 1); i++) {

		dynamixel_config_t motor_config = { .huart = &this->uart, // give the uart handle to each motor
				.handler = this, // give pointer to own handler
				.request_mem_pool = this->config.request_mem_pool, //give reference to memory pools
				.id = i,
				.profile_accel = DYNAMIXEL_MOTOR_PROFILE_ACCEL,
				.profile_velocity = DYNAMIXEL_MOTOR_PROFILE_VELOCITY
		};


		// init all the motors , store as array a member variable in dynamixel handler
		bool status = this->motors[i - 1].init(motor_config);
		if (status > 0) {
			// something failed in the motor init, return val is which motor failed
			return i;
		}
	}

	// create the request queue
	this->request_queue = osMessageQueueNew(LEN_REQUEST_QUEUE,
			sizeof(dynamixel_request_t*), 0U);
	// create the task for the handler
	osThreadNew(handler_task, this, &handler_task_attributes);

	// init was successful
	return 0;
}

void DynamixelHandler::start() {
	this->uart.start();

	for (int i = 0; i < NUM_DYNAMIXEL_MOTORS; i++) {
		this->motors[i].start();
	}

}

void DynamixelHandler::set_torque_single_motor(
		dynamixel_bool_state_single_motor_t torque_config) {

	// TODO check if the motor is configured

	// set the torque on the motor
	this->motors[torque_config.motor].set_torque(torque_config.state);
}

void DynamixelHandler::send_ping_single_motor(uint8_t motor) {

	// TODO check if the motor is configured
	//send ping to desired motor
	this->motors[motor].send_ping();
}

void DynamixelHandler::set_led_single_motor(
		dynamixel_bool_state_single_motor_t led_config) {

	// set the led
	this->motors[led_config.motor].set_led(led_config.state);
}

void DynamixelHandler::send_position_single_motor(
		dynamixel_position_single_motor_t position_config) {

	// TODO check if the motor is configured
	//send position to desired motor
	this->motors[position_config.motor].send_position(position_config.position);
}

void DynamixelHandler::send_position_register_single_motor(
		dynamixel_position_single_motor_t position_config) {

	// TODO check if the motor is configured

	this->motors[position_config.motor].send_position_register(
			position_config.position);
}

void DynamixelHandler::send_action_single_motor(uint8_t motor) {

	// TODO check if the motor is configured

	this->motors[motor].send_action();
}

float DynamixelHandler::get_voltage_single_motor(uint8_t motor) {

	return this->motors[motor].get_present_voltage();
}

float DynamixelHandler::get_temperature_single_motor(uint8_t motor) {

	return this->motors[motor].get_present_temperature();
}

uint32_t DynamixelHandler::get_goal_position_single_motor(uint8_t motor) {

	// TODO check if the motor is configured

	return this->motors[motor].get_goal_position();
}

uint32_t DynamixelHandler::get_present_position_single_motor(uint8_t motor) {

	return this->motors[motor].get_present_position();
}

// TODO implement all motors functions
void DynamixelHandler::set_torque_all_motors(bool torque_enable) {

	// this function uses the sync write instruction

	// set the length of the parameter in bytes
	// 2 Bytes Address to write to, 2 bytes length of the parameter
	// 1byte id + 1byte torque enable data per motor
	uint8_t parameter_len = 4
			+ ((1 + LEN_CTABLE_TORQUE_EN) * NUM_DYNAMIXEL_MOTORS);
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set address etc. into parameter buffer
	//set_parameters_sync_write_1byte(ADDRESS_TORQUE_ENABLE, (uint8_t) torque_enable, parameter_buf);
	set_parameters_sync_write(ADDRESS_TORQUE_ENABLE, LEN_CTABLE_TORQUE_EN,
			&torque_enable, parameter_buf);

	//construct a packet
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	motors[0].construct_request(INSTRUCTION_SYNC_WRITE, parameter_buf,
			parameter_len, 0, request);

	// override motor id in request to Broadcast id
	request->motor_id = 0xFE;

	//send the packet
	add_request(request);

}

void DynamixelHandler::set_led_all_motors(bool led_state) {

	// this function uses the sync write instruction

	// set the length of the parameter in bytes
	// 2 Bytes Address to write to, 2 bytes length of the parameter
	// 1byte id + 1byte torque enable data per motor
	uint8_t parameter_len = 4 + ((1 + LEN_CTABLE_LED) * NUM_DYNAMIXEL_MOTORS);
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set address etc. into parameter buffer
	//set_parameters_sync_write_1byte(ADDRESS_TORQUE_ENABLE, (uint8_t) torque_enable, parameter_buf);
	set_parameters_sync_write(ADDRESS_LED, LEN_CTABLE_LED, &led_state,
			parameter_buf);

	//construct a packet
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	motors[0].construct_request(INSTRUCTION_SYNC_WRITE, parameter_buf,
			parameter_len, 0, request);

	// override motor id in request to Broadcast id
	request->motor_id = 0xFE;

	//send the packet
	add_request(request);

}

void DynamixelHandler::send_position_all_motors(uint32_t position) {

	// this function uses the sync write instruction

	// set the length of the parameter in bytes
	// 2 Bytes Address to write to, 2 bytes length of the parameter
	// 1byte id + 4 bytes position data per motor
	uint8_t parameter_len = 4
			+ ((1 + LEN_CTABLE_GOAL_POSITION) * NUM_DYNAMIXEL_MOTORS);
	// initialize a buffer for parameters
	uint8_t parameter_buf[parameter_len];

	// set address etc. into parameter buffer
	//set_parameters_sync_write_4bytes(ADDRESS_GOAL_POSITION, position, parameter_buf);
	set_parameters_sync_write(ADDRESS_GOAL_POSITION, LEN_CTABLE_GOAL_POSITION,
			&position, parameter_buf);

	//construct a packet
	dynamixel_request_t *request = (dynamixel_request_t*) osMemoryPoolAlloc(
			this->config.request_mem_pool, REQUEST_POOL_ALLOC_TIMEOUT);
	motors[0].construct_request(INSTRUCTION_SYNC_WRITE, parameter_buf,
			parameter_len, 0, request);

	// override motor id in request to Broadcast id
	request->motor_id = 0xFE;

	//send the packet
	add_request(request);

}

// return all goal positions
void DynamixelHandler::get_goal_position_all_motors(uint32_t *position_array) {

	for (uint8_t i = 0; i < NUM_DYNAMIXEL_MOTORS; i++) {

		position_array[i] = this->motors[i].get_goal_position();
	}

}

void DynamixelHandler::get_present_position_all_motors(
		uint32_t *position_array) {

	for (uint8_t i = 0; i < NUM_DYNAMIXEL_MOTORS; i++) {

		position_array[i] = this->motors[i].get_present_position();
	}
}

uint8_t DynamixelHandler::add_request(dynamixel_request_t *request) {

	// send the given request to the handler queue
	osStatus_t status = osMessageQueuePut(request_queue, &request, 0U,
			REQUEST_SEND_TIMEOUT);

	if (status != osOK) {
		// there was a error putting the message into the queue
		return 1;
	} else {
		// Status was ok, return zero
		return 0;
	}

}

// checks if there is the correct header
// checks if check sum is ok
bool DynamixelHandler::check_packet_header_crc(Buffer *buffer) {

	// compare header
	if (buffer->data_ptr[0] == 0xFF) {
		if (buffer->data_ptr[1] == 0xFF) {
			if (buffer->data_ptr[2] == 0xFD) {
				// header is valid
				// compare the checksum

				//calculate the checksum of the received packet
				uint16_t calculated_crc = this->getCheckSum(0, buffer->data_ptr,
						(buffer->len - 2));

				// extract the send checksum (little endian)
				uint16_t packet_crc = (buffer->data_ptr[(buffer->len - 1)] << 8)
						| buffer->data_ptr[(buffer->len - 2)];

				// if there equal packet is ok
				if (calculated_crc == packet_crc) {

					return true;
				}
			}

		}
	}
	return false;
}

uint8_t DynamixelHandler::set_parameters_sync_write(uint16_t address,
		uint8_t len_in_ctable, void *write_data, uint8_t *parameter_buf) {

	// set the address
	// in little endian format
	parameter_buf[0] = (address & 0x00ff);
	parameter_buf[1] = (address >> 8) & 0x00ff;

	//set the length of the parameter to be bulk written
	parameter_buf[2] = len_in_ctable;
	parameter_buf[3] = 0x00;

	// set the data
	// for each motor set the id and the data
	for (uint8_t i = 0; i < NUM_DYNAMIXEL_MOTORS; i++) {

		//set the id
		// first motor block (3bytes) at index 4, second on index 7 etc.
		uint8_t begin_of_block = 4 + (i * (len_in_ctable + 1));

		parameter_buf[begin_of_block] = this->motors[i].get_id();

		// depending on length of data to be written
		// cast to different type and set data
		switch (len_in_ctable) {
		case 1:
			// data is just one byte
			// cast the void pointer to uint8t * the dereference
			parameter_buf[begin_of_block + 1] = *(uint8_t*) write_data;
			break;

		case 2:
			// set the data
			// convert to little endian format
			for (uint8_t j = 0; j < len_in_ctable; j++) {

				parameter_buf[begin_of_block + 1 + j] =
						((*(uint16_t*) write_data >> (8 * j)) & 0xff);
			}
			break;

		case 4:
			// set the data
			// convert to little endian format
			for (uint8_t j = 0; j < len_in_ctable; j++) {

				parameter_buf[begin_of_block + 1 + j] =
						((*(uint32_t*) write_data >> (8 * j)) & 0xff);
			}
			break;

		default:

			// not supported data length
			return 1;
			break;
		}

	}

	return 0;
}

uint16_t DynamixelHandler::getCheckSum(uint16_t crc_accum,
		uint8_t *data_blk_ptr, uint16_t data_blk_size) {
	uint16_t i, j;
	uint16_t crc_table[256] = { 0x0000, 0x8005, 0x800F, 0x000A, 0x801B, 0x001E,
			0x0014, 0x8011, 0x8033, 0x0036, 0x003C, 0x8039, 0x0028, 0x802D,
			0x8027, 0x0022, 0x8063, 0x0066, 0x006C, 0x8069, 0x0078, 0x807D,
			0x8077, 0x0072, 0x0050, 0x8055, 0x805F, 0x005A, 0x804B, 0x004E,
			0x0044, 0x8041, 0x80C3, 0x00C6, 0x00CC, 0x80C9, 0x00D8, 0x80DD,
			0x80D7, 0x00D2, 0x00F0, 0x80F5, 0x80FF, 0x00FA, 0x80EB, 0x00EE,
			0x00E4, 0x80E1, 0x00A0, 0x80A5, 0x80AF, 0x00AA, 0x80BB, 0x00BE,
			0x00B4, 0x80B1, 0x8093, 0x0096, 0x009C, 0x8099, 0x0088, 0x808D,
			0x8087, 0x0082, 0x8183, 0x0186, 0x018C, 0x8189, 0x0198, 0x819D,
			0x8197, 0x0192, 0x01B0, 0x81B5, 0x81BF, 0x01BA, 0x81AB, 0x01AE,
			0x01A4, 0x81A1, 0x01E0, 0x81E5, 0x81EF, 0x01EA, 0x81FB, 0x01FE,
			0x01F4, 0x81F1, 0x81D3, 0x01D6, 0x01DC, 0x81D9, 0x01C8, 0x81CD,
			0x81C7, 0x01C2, 0x0140, 0x8145, 0x814F, 0x014A, 0x815B, 0x015E,
			0x0154, 0x8151, 0x8173, 0x0176, 0x017C, 0x8179, 0x0168, 0x816D,
			0x8167, 0x0162, 0x8123, 0x0126, 0x012C, 0x8129, 0x0138, 0x813D,
			0x8137, 0x0132, 0x0110, 0x8115, 0x811F, 0x011A, 0x810B, 0x010E,
			0x0104, 0x8101, 0x8303, 0x0306, 0x030C, 0x8309, 0x0318, 0x831D,
			0x8317, 0x0312, 0x0330, 0x8335, 0x833F, 0x033A, 0x832B, 0x032E,
			0x0324, 0x8321, 0x0360, 0x8365, 0x836F, 0x036A, 0x837B, 0x037E,
			0x0374, 0x8371, 0x8353, 0x0356, 0x035C, 0x8359, 0x0348, 0x834D,
			0x8347, 0x0342, 0x03C0, 0x83C5, 0x83CF, 0x03CA, 0x83DB, 0x03DE,
			0x03D4, 0x83D1, 0x83F3, 0x03F6, 0x03FC, 0x83F9, 0x03E8, 0x83ED,
			0x83E7, 0x03E2, 0x83A3, 0x03A6, 0x03AC, 0x83A9, 0x03B8, 0x83BD,
			0x83B7, 0x03B2, 0x0390, 0x8395, 0x839F, 0x039A, 0x838B, 0x038E,
			0x0384, 0x8381, 0x0280, 0x8285, 0x828F, 0x028A, 0x829B, 0x029E,
			0x0294, 0x8291, 0x82B3, 0x02B6, 0x02BC, 0x82B9, 0x02A8, 0x82AD,
			0x82A7, 0x02A2, 0x82E3, 0x02E6, 0x02EC, 0x82E9, 0x02F8, 0x82FD,
			0x82F7, 0x02F2, 0x02D0, 0x82D5, 0x82DF, 0x02DA, 0x82CB, 0x02CE,
			0x02C4, 0x82C1, 0x8243, 0x0246, 0x024C, 0x8249, 0x0258, 0x825D,
			0x8257, 0x0252, 0x0270, 0x8275, 0x827F, 0x027A, 0x826B, 0x026E,
			0x0264, 0x8261, 0x0220, 0x8225, 0x822F, 0x022A, 0x823B, 0x023E,
			0x0234, 0x8231, 0x8213, 0x0216, 0x021C, 0x8219, 0x0208, 0x820D,
			0x8207, 0x0202 };

	for (j = 0; j < data_blk_size; j++) {
		i = ((uint16_t) (crc_accum >> 8) ^ data_blk_ptr[j]) & 0xFF;
		crc_accum = (crc_accum << 8) ^ crc_table[i];
	}

	return crc_accum;

}

void DynamixelHandler::uart_rx_callback() {

	BaseType_t xHigherPriorityTaskWoken = pdFALSE;

	// notify the handler task for further handling
	vTaskNotifyGiveFromISR(task_handle_dxl_handler, &xHigherPriorityTaskWoken);

	// yield if there is a higher priority task that was interrupted
	portYIELD_FROM_ISR(xHigherPriorityTaskWoken);

}

void DynamixelHandler::handler_task(void *argument) {

	DynamixelHandler *instance = static_cast<DynamixelHandler*>(argument);

	// Initialize the used variables for the task loop
	osStatus_t status = osError;
	Buffer *buffer = nullptr;
	uint32_t notify_value = 0;

	// get the task handle
	instance->task_handle_dxl_handler = xTaskGetCurrentTaskHandle();

	while (1) {

		void *ptr_req;
		status = osMessageQueueGet(instance->request_queue, &ptr_req, 0U, 0); // get next request

		if (status == osOK) {
			// cast the received pointer to original type
			dynamixel_request_t *req = (dynamixel_request_t*) ptr_req;
			// 1. Send TX data
			instance->uart.send(req->write_buffer, req->write_len);

			if (req->type != INSTRUCTION_SYNC_WRITE) {

				// wait for response from the uart receive interrupt
				notify_value = ulTaskNotifyTake(pdTRUE,
						HANDLER_UART_NOTIFY_TIMEOUT);

				// if there was something received process it
				if (notify_value > 0) {

					// get the received status packet out of the uart rx queue buffer
					buffer = instance->uart.rx_queue.read();

					if (req->type == INSTRUCTION_READ) {

						/*
						 //debug statements
						 // get the length and data from uart
						 uint16_t len = buffer->len;
						 uint8_t *data = buffer->data_ptr;

						 for(uint8_t i = 0; i<len; i++)
						 {
						 data_from_rx[i] = data[i];
						 }

						 rx_completed++;
						 */

						//check the paket header and checksum
						if (instance->check_packet_header_crc(buffer)) {
							// extract the id from the packet and check against the provided id in the request
							if (buffer->data_ptr[4] == req->motor_id) {

								if (buffer->len <= REQUEST_READ_BUF_SIZE) {

									//copy the uart data to the request red buffer
									memcpy(req->read_buffer, buffer->data_ptr,
											buffer->len);

									// set the length of the read buffer to the receive length by uart
									req->read_len = buffer->len;

									// request is done

									// Update request status
									req->success = true;

									//notify the requesting motor task
									// send the pointer to the processed request for checking
									xTaskNotify(req->task_handle,
											(uint32_t )req,
											eSetValueWithOverwrite);

									// the requester will return the request back to the memory pool once processed

								} else {

									// the packet that has been received is too long
									req->success = false;
									// send the pointer to the processed request for checking
									xTaskNotify(req->task_handle,
											(uint32_t )req,
											eSetValueWithOverwrite);
								}

							} else {

								//the received id does not match the request
								// notify the motor from the request with success = false
								req->success = false;
								// send the pointer to the processed request for checking
								xTaskNotify(req->task_handle, (uint32_t )req,
										eSetValueWithOverwrite);

							}
						} else {

							// TODO Error handler
							req->success = false;
							// send the pointer to the processed request for checking
							xTaskNotify(req->task_handle, (uint32_t )req,
									eSetValueWithOverwrite);

						}

					} else { // its just an write, ping etc. request so no need to read back the status packet from the motor

						// Update request status, may not be needed as the request is directly returned afterwards
						req->success = true;
						// Return the request to memory pool
						osMemoryPoolFree(instance->config.request_mem_pool,
								req);

					}

				} else {

					//timeout when waiting for motor status packet occurred!
					// serial connection to the motor is not working
					req->success = false;
					// notify the motor of the failed request
					xTaskNotify(req->task_handle, (uint32_t )req,
							eSetValueWithOverwrite);

					// motor will return request to the pool

					// Return the request to memory pool
					//osMemoryPoolFree(instance->config.request_mem_pool, req);

				}

			} else {
				// its a broadcast write
				// return the request to the pool
				osMemoryPoolFree(instance->config.request_mem_pool, req);
			}

		} else {
			// the queue can be empty
			//if there is no request available, wait and retry
			osDelay(10);
		}

	}

}


