/*
 * twipr_logging.h
 *
 *  Created on: Mar 7, 2023
 *      Author: lehmann_workstation
 */

#ifndef LOGGING_TWIPR_LOGGING_H_
#define LOGGING_TWIPR_LOGGING_H_

#include "twipr_estimation.h"
#include "twipr_sensors.h"
#include "twipr_control.h"
#include "twipr_sequencer.h"
#include "firmware_defs.h"
#include "bilbo_drive.h"
#include "twipr_errors.h"

class TWIPR_Firmware;


typedef struct twipr_debug_sample_t {
	uint8_t debug1;
	uint8_t debug2;
	int8_t debug3;
	int8_t debug4;
	uint16_t debug5;
	int16_t debug6;
	float debug7;
	float debug8;
} twipr_debug_sample_t;


typedef struct twipr_logging_sample_t {
	twipr_logging_general_t general;
	twipr_logging_error_t errors;
	twipr_logging_control_t control;
	twipr_logging_estimation_t estimation;
	twipr_sensors_data_t sensors;
	twipr_sequencer_sample_t sequence;
	twipr_debug_sample_t debug;
} twipr_logging_sample_t;

typedef struct twipr_logging_config_t {
	TWIPR_Firmware *firmware;
	TWIPR_ControlManager *control;
	TWIPR_Estimation *estimation;
	TWIPR_Sensors *sensors;
	TWIPR_Sequencer *sequencer;
	BILBO_ErrorHandler* error_handler;
} twipr_logging_config_t;

typedef enum twipr_logging_buffer_status_t {
	TWIPR_LOGGING_BUFFER_FULL = 1,
	TWIPR_LOGGING_BUFFER_NOT_FULL = 0,
}twipr_logging_buffer_status_t;

class TWIPR_Logging {
public:

	TWIPR_Logging();

	void init(twipr_logging_config_t config);
	void start();

	void reset();

	twipr_logging_buffer_status_t collectSamples();



	twipr_logging_sample_t sample_buffer[TWIPR_FIRMWARE_SAMPLE_BUFFER_SIZE];

	twipr_logging_config_t config;
private:

	uint32_t sample_index = 0;

};

#endif /* LOGGING_TWIPR_LOGGING_H_ */
