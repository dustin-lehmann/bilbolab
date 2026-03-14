/*
 * firmware.hpp
 *
 *  Created on: Feb 13, 2023
 *      Author: lehmann_workstation
 */

#ifndef FIRMWARE_HPP_
#define FIRMWARE_HPP_

#include "firmware_core.h"
#include "bilbo_communication.h"
#include "bilbo_control.h"
#include "robot-control_std.h"
#include "bilbo_estimation.h"

#include "bilbo_logging.h"
#include "bilbo_supervisor.h"
#include "bilbo_sequencer.h"
#include "io.h"

#include "bilbo_drive.h"
#include "simplexmotion_can.h"
#include "simplexmotion_rs485.h"

#include "bilbo_errors.h"

class BILBO_Firmware {

public:
	BILBO_Firmware(){
	};
	HAL_StatusTypeDef init();
	HAL_StatusTypeDef start();

	bool reset();

	void step();

	void helperTask();
	void task();


	bilbo_logging_general_t getSample();

	void errorHandler(bilbo_error_type_t error);

	bilbo_debug_sample_t getDebugSample();

	bilbo_firmware_state_t firmware_state = BILBO_FIRMWARE_STATE_NONE;

	bilbo_firmware_revision_t revision = { .major =
			BILBO_FIRMWARE_REVISION_MAJOR, .minor =
			BILBO_FIRMWARE_REVISION_MINOR };

	bilbo_firmware_info_t firmware_info = {
			.board_revision = BILBO_BOARD_REV_VALUE,
			.model = BILBO_MODEL_VALUE,
			.drive_interface = BILBO_DRIVE_INTERFACE_VALUE,
	};

	uint32_t tick = 0;

	BILBO_CommunicationManager comm;
	BILBO_Control control;
	BILBO_Sequencer sequencer;
	BILBO_Estimation estimation;
	BILBO_Supervisor supervisor;
	BILBO_Sensors sensors;
	BILBO_Logging logging;
	BILBO_Drive drive;
	BILBO_ErrorHandler error_handler;

#ifdef BILBO_DRIVE_SIMPLEXMOTION_CAN
	SimplexMotion_CAN motor_left;
	SimplexMotion_CAN motor_right;
#endif

#ifdef BILBO_DRIVE_SIMPLEXMOTION_RS485
	SimplexMotion_RS485 motor_left;
	SimplexMotion_RS485 motor_right;
#endif

	bilbo_debug_sample_t debugData;

private:

	bilbo_logging_buffer_status_t sample_buffer_state = BILBO_LOGGING_BUFFER_NOT_FULL;

	elapsedMillis timer_control_mode_led;

	void setControlModeLed();
	void updateExternalLedStrip(bilbo_control_mode_t mode);
};

void start_firmware_task(void *argument);
void start_firmware_control_task(void *argument);

#endif /* FIRMWARE_HPP_ */
