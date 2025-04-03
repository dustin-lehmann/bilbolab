/*
 * twipr_errors.cpp
 *
 *  Created on: 6 Mar 2023
 *      Author: lehmann_workstation
 */


#include "twipr_errors.h"
#include "firmware.hpp"

BILBO_ErrorHandler* handler;
osSemaphoreId_t log_semaphore;

/* ================================================================================== */
BILBO_ErrorHandler::BILBO_ErrorHandler() {
	handler = this;
	log_semaphore = osSemaphoreNew(1, 1, NULL);
	this->log_index = 0;
}


void BILBO_ErrorHandler::init(bilbo_error_handler_config_t config){
	this->config = config;
}

/* ================================================================================== */
void BILBO_ErrorHandler::setError(bilbo_error_type_t type, bilbo_error_t error){
	osSemaphoreAcquire(log_semaphore, portMAX_DELAY);

	bilbo_error_log_entry_t new_entry = {
			.tick = tick_global,
			.type = type,
			.error = error
	};

	this->error_log[this->log_index] = new_entry;

	this->log_index++;

	if (this->log_index == BILBO_ERROR_LOG_SIZE){
		this->log_index = 0;
	}

	if (type>this->state){
		this->state = type;
	}

	if (this->state >= BILBO_ERROR_MAJOR){

		this->config.firmware->firmware_state = TWIPR_FIRMWARE_STATE_ERROR;
		stopControl();

		// TODO: Make LEDs red, send error message
	}

	osSemaphoreRelease(log_semaphore);

	BILBO_Message_Error msg = BILBO_Message_Error({
		.type = type,
		.error = error,
		.overall_error = this->state
	});

	sendMessage(msg);
}


/* ================================================================================== */
void BILBO_ErrorHandler::clearErrorState(bilbo_error_type_t type){

	// TODO: This might not be good. If I just want to clean a max wheel speed I should not clear all warnings
	if (this->state <= type){
		this->state = BILBO_ERROR_NONE;
	}
}


/* ================================================================================== */
bilbo_error_type_t BILBO_ErrorHandler::getStatus(){
	osSemaphoreAcquire(log_semaphore, portMAX_DELAY);
	bilbo_error_type_t status = this->state;
	osSemaphoreRelease(log_semaphore);
	return status;
}


/* ================================================================================== */
twipr_logging_error_t BILBO_ErrorHandler::getSample(){

	twipr_logging_error_t sample;
	osSemaphoreAcquire(log_semaphore,
			portMAX_DELAY);
	sample.state = this->state;

	uint16_t index;
	if (this->log_index == 0){
		index = BILBO_ERROR_LOG_SIZE-1;
	} else {
		index = this->log_index;
	}

	sample.last_entry = this->error_log[index];
	osSemaphoreRelease(log_semaphore);

	return sample;
}


/* ================================================================================== */
void setError(bilbo_error_type_t type, bilbo_error_t error){
	if(handler){
		handler->setError(type, error);
	}
}

