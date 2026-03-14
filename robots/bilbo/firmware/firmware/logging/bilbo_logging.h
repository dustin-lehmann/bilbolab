/*
 * bilbo_logging.h
 *
 *  Created on: Mar 7, 2023
 *      Author: lehmann_workstation
 */

#ifndef LOGGING_BILBO_LOGGING_H_
#define LOGGING_BILBO_LOGGING_H_

#include "bilbo_estimation.h"
#include "bilbo_sensors.h"
#include "bilbo_control.h"
#include "bilbo_sequencer.h"
#include "firmware_defs.h"
#include "bilbo_drive.h"
#include "bilbo_errors.h"

class BILBO_Firmware;


typedef struct bilbo_debug_sample_t {
	uint8_t debug1;
} bilbo_debug_sample_t;


typedef struct bilbo_logging_sample_t {
	uint32_t tick;
	bilbo_logging_general_t general;
	bilbo_logging_error_t errors;
	bilbo_control_data_t control;
	bilbo_logging_estimation_t estimation;
	bilbo_sensors_data_t sensors;
	bilbo_logging_drive_t drive;
	bilbo_sequencer_sample_t sequence;
	bilbo_debug_sample_t debug;
} bilbo_logging_sample_t;

typedef struct bilbo_logging_config_t {
	BILBO_Firmware *firmware;
	BILBO_Control *control;
	BILBO_Estimation *estimation;
	BILBO_Sensors *sensors;
	BILBO_Drive *drive;
	BILBO_Sequencer *sequencer;
	BILBO_ErrorHandler* error_handler;
} bilbo_logging_config_t;

typedef enum bilbo_logging_buffer_status_t : uint8_t {
	BILBO_LOGGING_BUFFER_FULL = 1,
	BILBO_LOGGING_BUFFER_NOT_FULL = 0,
}bilbo_logging_buffer_status_t;

class BILBO_Logging {
public:

	BILBO_Logging();

	void init(bilbo_logging_config_t config);
	void start();

	void reset();

	bilbo_logging_buffer_status_t collectSamples();



	bilbo_logging_sample_t sample_buffer[BILBO_FIRMWARE_SAMPLE_BUFFER_SIZE];

	bilbo_logging_config_t config;
private:

	uint32_t sample_index = 0;

};

#endif /* LOGGING_BILBO_LOGGING_H_ */
