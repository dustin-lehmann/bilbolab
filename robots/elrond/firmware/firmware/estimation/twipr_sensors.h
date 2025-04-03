/*
 * twipr_sensors.h
 *
 *  Created on: 3 Mar 2023
 *      Author: Dustin Lehmann
 */

#ifndef ESTIMATION_TWIPR_SENSORS_H_
#define ESTIMATION_TWIPR_SENSORS_H_

#include "core.h"
#include "robot-control_board.h"
#include "bilbo_drive.h"

typedef struct twipr_sensors_config_t {
	BILBO_Drive *drive;
} twipr_sensors_config_t;

typedef struct twipr_sensors_data_t {
	float speed_left;
	float speed_right;
	bmi160_acc acc;
	bmi160_gyr gyr;
	float battery_voltage;
} twipr_sensors_data_t;


typedef enum twipr_sensors_status_t {
	TWIPR_SENSORS_STATUS_ERROR = -1,
	TWIPR_SENSORS_STATUS_IDLE = 0,
	TWIPR_SENSORS_STATUS_RUNNING = 1,
} twipr_sensors_status_t;

class TWIPR_Sensors {
public:
	TWIPR_Sensors();

	uint8_t init(twipr_sensors_config_t config);
	void start();
	uint8_t check();
	void update();
	uint8_t calibrate();

	twipr_sensors_data_t getData();
	twipr_sensors_status_t getStatus();
	twipr_sensors_status_t status;
private:
	BMI160 imu;
	void _readImu();
	void _readMotorSpeed();
	void _readBatteryVoltage();
	twipr_sensors_config_t _config;
	twipr_sensors_data_t _data;
};

#endif /* ESTIMATION_TWIPR_SENSORS_H_ */
