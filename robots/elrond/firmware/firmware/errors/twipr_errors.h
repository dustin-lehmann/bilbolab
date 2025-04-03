/*
 * twipr_errors.h
 *
 *  Created on: 4 Mar 2023
 *      Author: Dustin Lehmann
 */

#ifndef ERRORS_TWIPR_ERRORS_H_
#define ERRORS_TWIPR_ERRORS_H_

#include "core.h"
#include "robot-control_std.h"
#include "firmware_core.h"
#include "bilbo_messages.h"

#define BILBO_ERROR_LOG_SIZE 100

class TWIPR_Firmware;

typedef enum bilbo_error_type_t {
	BILBO_ERROR_NONE = 0,
	BILBO_ERROR_WARNING = 1,
	BILBO_ERROR_MINOR = 2,
	BILBO_ERROR_MAJOR = 3,
	BILBO_ERROR_CRITICAL = 4
} bilbo_error_type_t;

typedef enum bilbo_error_t {
	BILBO_ERROR_UNSPECIFIED = 0,
	BILBO_WARNING_WHEEL_SPEED = 1,
	BILBO_WARNING_MANUAL_STOP = 2,
	BILBO_ERROR_INIT = 3,
	BILBO_ERROR_START = 4,
	BILBO_ERROR_IMU_INITIALIZE = 5,
	BILBO_ERROR_MOTOR_RACECONDITIONS = 6,
	BILBO_ERROR_FIRMWARE_RACECONDITION = 7,
	BILBO_ERROR_MOTOR_COMM = 8
} bilbo_error_t;


typedef struct error_message_data_t {
	bilbo_error_type_t type;
	bilbo_error_t error;
	bilbo_error_type_t overall_error;
} error_message_data_t;

typedef BILBO_Message<error_message_data_t, MSG_EVENT, BILBO_MESSAGE_ERROR> BILBO_Message_Error;



typedef struct bilbo_error_log_entry_t {
	uint32_t tick;
	bilbo_error_type_t type;
	bilbo_error_t error;
} bilbo_error_log_entry_t;

typedef struct bilbo_error_handler_config_t {
	TWIPR_Firmware* firmware;
} bilbo_error_handler_config_t;

typedef struct twipr_logging_error_t {
	bilbo_error_type_t state;
	bilbo_error_log_entry_t last_entry;
} twipr_logging_error_t;

class BILBO_ErrorHandler {
public:
	BILBO_ErrorHandler();

	void init(bilbo_error_handler_config_t config);

	void setError(bilbo_error_type_t type , bilbo_error_t error);
	void clearErrorState(bilbo_error_type_t type);

	bilbo_error_type_t getStatus();

	twipr_logging_error_t getSample();


	bilbo_error_log_entry_t error_log[BILBO_ERROR_LOG_SIZE];


	bilbo_error_handler_config_t config;
private:
	uint16_t log_index = 0;
	bilbo_error_type_t state = BILBO_ERROR_NONE;

};

void setError(bilbo_error_type_t type, bilbo_error_t error);

//void twipr_error_handler(uint32_t errorcode);
//void twipr_error_handler(uint32_t errorcode, uint8_t *data, uint16_t len);

#endif /* ERRORS_TWIPR_ERRORS_H_ */
