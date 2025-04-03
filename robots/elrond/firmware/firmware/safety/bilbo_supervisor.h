/*
 * twipr_safety.h
 *
 *  Created on: Feb 22, 2023
 *      Author: lehmann_workstation
 */

#ifndef SAFETY_TWIPR_SAFETY_H_
#define SAFETY_TWIPR_SAFETY_H_

#include "core.h"
#include "firmware_core.h"
#include "twipr_control.h"
#include "twipr_communication.h"
#include "bilbo_drive.h"

typedef struct twipr_supervisor_stuck_config_t {
	float max_velocity_error = 0.1;
	float max_pitch_angle_deviation = 0.05;
	int stuck_duration = 50;
} twipr_supervisor_stuck_config_t;

typedef struct twipr_supervisor_stuck_data_t {
	bool is_stuck = false;
	float last_velocity_error = 0;
	float last_pitch_angle = 0;
	float error_count = 0;
} twipr_supervisor_stuck_data_t;

typedef struct twipr_supervisor_controller_config_t {
	float max_forward_pid_integrator = 0.2;
	float max_turn_pid_integrator = 0.2;
} twipr_supervisor_controller_config_t;

typedef struct twipr_supervisor_config_t {
	TWIPR_Estimation *estimation;
	BILBO_Drive *drive;
	TWIPR_ControlManager *control;
	TWIPR_CommunicationManager *communication;
	core_hardware_Button *off_button;
	float max_wheel_speed;
	twipr_supervisor_stuck_config_t stuck_config;
	twipr_supervisor_controller_config_t controller_config;
} twipr_supervisor_config_t;


typedef enum bilbo_supervisor_dings_t {
	BILBO_SUPERVISOR_NONE = 0,

	BILBO_SUPERVISOR_MAX_WHEEL_SPEED = 1,
} bilbo_supervisor_dings_t;




class TWIPR_Supervisor {
public:
	TWIPR_Supervisor();

	void init(twipr_supervisor_config_t config);
	void start();

//	bilbo_error_type_t getState();
	void task();


	twipr_supervisor_config_t config;

private:

//	bilbo_supervisor_dings_t
//	bilbo_error_type_t error = BILBO_ERROR_NONE;
//	void setError(bilbo_error_type_t error);


//	bilbo_error_t checkStuck();
//	twipr_supervisor_stuck_data_t stuck_data;

//	bilbo_supervisor_dings_t checkControllers();

	void checkMotors();

	void checkMotorSpeed();

	void checkButton();


	uint32_t lastDriveTick = 0;


};

void startTwiprSupervisorTask(void *args);

#endif /* SAFETY_TWIPR_SAFETY_H_ */
