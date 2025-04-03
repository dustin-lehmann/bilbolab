/*
 * firmware.hpp
 *
 *  Created on: Feb 13, 2023
 *      Author: lehmann_workstation
 */

#ifndef FIRMWARE_HPP_
#define FIRMWARE_HPP_

#include "firmware_core.h"
#include "twipr_communication.h"
#include "twipr_control.h"
#include "robot-control_std.h"
#include "twipr_estimation.h"

#include "twipr_logging.h"
#include "bilbo_supervisor.h"
#include "twipr_sequencer.h"
#include "io.h"

#include "bilbo_drive.h"
#include "simplexmotion_can.h"
#include "simplexmotion_rs485.h"

#include "twipr_errors.h"

class TWIPR_Firmware {

public:
	TWIPR_Firmware();
	HAL_StatusTypeDef init();
	HAL_StatusTypeDef start();

	bool reset();

	void step();

	void helperTask();
	void task();


	twipr_logging_general_t getSample();

	void errorHandler(bilbo_error_type_t error);

	twipr_debug_sample_t getDebugSample();

	twipr_firmware_state_t firmware_state = TWIPR_FIRMWARE_STATE_NONE;

	twipr_firmware_revision_t revision = { .major =
			TWIPR_FIRMWARE_REVISION_MAJOR, .minor =
			TWIPR_FIRMWARE_REVISION_MINOR };
	uint32_t tick = 0;

	TWIPR_CommunicationManager comm;
	TWIPR_ControlManager control;
	TWIPR_Sequencer sequencer;
	TWIPR_Estimation estimation;
	TWIPR_Supervisor supervisor;
	TWIPR_Sensors sensors;
	TWIPR_Logging logging;
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

	twipr_debug_sample_t debugData;

private:

	twipr_logging_buffer_status_t sample_buffer_state;

	elapsedMillis timer_control_mode_led;

	void setControlModeLed();
};

void start_firmware_task(void *argument);
void start_firmware_control_task(void *argument);

#endif /* FIRMWARE_HPP_ */
