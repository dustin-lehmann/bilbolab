/*
 * bilbo_sensors.h
 *
 *  Created on: 3 Mar 2023
 *      Author: Dustin Lehmann
 */

#ifndef ESTIMATION_BILBO_SENSORS_H_
#define ESTIMATION_BILBO_SENSORS_H_

#include "core.h"
#include "robot-control_board.h"
#include "bilbo_drive.h"

typedef struct bilbo_sensors_config_t {
	BILBO_Drive *drive;
} bilbo_sensors_config_t;

typedef struct bilbo_sensors_data_t {
	float speed_left;
	float speed_right;
	bmi160_acc acc;
	bmi160_gyr gyr;
	float battery_voltage;
} bilbo_sensors_data_t;


typedef enum bilbo_sensors_status_t : int8_t {
	BILBO_SENSORS_STATUS_ERROR = -1,
	BILBO_SENSORS_STATUS_IDLE = 0,
	BILBO_SENSORS_STATUS_RUNNING = 1,
} bilbo_sensors_status_t;

class BILBO_Sensors {
public:
	BILBO_Sensors();

	uint8_t init(bilbo_sensors_config_t config);
	void start();
	uint8_t check();
	void update();
	uint8_t calibrate();

	bilbo_sensors_data_t getData();
	bilbo_sensors_status_t getStatus();
	bilbo_sensors_status_t status;
private:
	BMI160 imu;
	void _readImu();
	void _readMotorSpeed();
	void _readBatteryVoltage();
	bilbo_sensors_config_t _config;
	bilbo_sensors_data_t _data;
};

#endif /* ESTIMATION_BILBO_SENSORS_H_ */
