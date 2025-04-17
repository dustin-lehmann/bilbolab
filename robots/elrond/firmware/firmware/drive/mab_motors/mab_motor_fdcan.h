/*
 * mab_motor.h
 *
 *  Created on: Mar 21, 2025
 *      Author: klvdw
 */

#ifndef DRIVE_MAB_MOTORS_MAB_MOTOR_FDCAN_H_
#define DRIVE_MAB_MOTORS_MAB_MOTOR_FDCAN_H_

#include "stm32h7xx_hal.h"
#include "can_mab.h"
#include "bilbo_drive_motor.h"

#define MAB_MOTOR_READ_TIMEOUT 10

typedef struct mab_motor_config_t {
	CAN *can;
	uint32_t drive_id;
	uint16_t can_watchdog_timeout = 200;
	float torque_limit = 1.75f;
	float velocity_limit = 140.0f;
} mab_motor_config_t;

typedef enum mab_motor_mode_t {
	MAB_MOTOR_MODE_IDLE,
	MAB_MOTOR_MODE_POS_PID,
	MAB_MOTOR_MODE_VELOCITY_PID,
	MAB_MOTOR_MODE_RAW_TORQUE,
	MAB_MOTOR_MODE_IMPEDANCE,
	MAB_MOTOR_MODE_POSITION_PROFILE,
	MAB_MOTOR_MODE_VELOCITY_PROFILE
} mab_motor_mode_t;

typedef struct mab_motor_impedance_constants_t {
	float kp;
	float kd;
} mab_motor_impedance_constants_t;

typedef enum mab_motors_register_addresses_t {
    // CAN Configuration
    MAB_REG_CAN_ID = 0x001,
    MAB_REG_CAN_BAUDRATE = 0x002,
    MAB_REG_CAN_WATCHDOG = 0x003,
    MAB_REG_CAN_TERMINATION = 0x004,

    // Motor Configuration
    MAB_REG_MOTOR_NAME = 0x010,
    MAB_REG_MOTOR_POLE_PAIRS = 0x011,
    MAB_REG_MOTOR_KT = 0x012,
    MAB_REG_MOTOR_KT_A = 0x013,
    MAB_REG_MOTOR_KT_B = 0x014,
    MAB_REG_MOTOR_KT_C = 0x015,
    MAB_REG_MOTOR_I_MAX = 0x016,
    MAB_REG_MOTOR_GEAR_RATIO = 0x017,
    MAB_REG_MOTOR_TORQUE_BANDWIDTH = 0x018,
    MAB_REG_MOTOR_FRICTION = 0x019,
    MAB_REG_MOTOR_STICTION = 0x01A,
    MAB_REG_MOTOR_RESISTANCE = 0x01B,
    MAB_REG_MOTOR_INDUCTANCE = 0x01C,
    MAB_REG_MOTOR_KV = 0x01D,
    MAB_REG_MOTOR_CALIBRATION_MODE = 0x01E,
    MAB_REG_MOTOR_THERMISTOR_TYPE = 0x01F,

    // Output Encoder
    MAB_REG_OUTPUT_ENCODER = 0x020,
    MAB_REG_OUTPUT_ENCODER_DIR = 0x021,
    MAB_REG_OUTPUT_ENCODER_DEFAULT_BAUD = 0x022,
    MAB_REG_OUTPUT_ENCODER_VELOCITY = 0x023,
    MAB_REG_OUTPUT_ENCODER_POSITION = 0x024,
    MAB_REG_OUTPUT_ENCODER_MODE = 0x025,
    MAB_REG_OUTPUT_ENCODER_CALIBRATION_MODE = 0x026,

    // Position PID
    MAB_REG_MOTOR_POS_PID_KP = 0x030,
    MAB_REG_MOTOR_POS_PID_KI = 0x031,
    MAB_REG_MOTOR_POS_PID_KD = 0x032,
    MAB_REG_MOTOR_POS_PID_WINDUP = 0x034,

    // Velocity PID
    MAB_REG_MOTOR_VEL_PID_KP = 0x040,
    MAB_REG_MOTOR_VEL_PID_KI = 0x041,
    MAB_REG_MOTOR_VEL_PID_KD = 0x042,
    MAB_REG_MOTOR_VEL_PID_WINDUP = 0x044,

    // Impedance PD
    MAB_REG_MOTOR_IMP_PID_KP = 0x050,
    MAB_REG_MOTOR_IMP_PID_KD = 0x051,

    // Main Encoder and Torque
    MAB_REG_MAIN_ENCODER_VELOCITY = 0x062,
    MAB_REG_MAIN_ENCODER_POSITION = 0x063,
    MAB_REG_MOTOR_TORQUE_OUTPUT = 0x064,

    // Run Commands
    MAB_REG_RUN_SAVE_CMD = 0x080,
    MAB_REG_RUN_TEST_MAIN_ENCODER_CMD = 0x081,
    MAB_REG_RUN_TEST_OUTPUT_ENCODER_CMD = 0x082,
    MAB_REG_RUN_CALIBRATE_CMD = 0x083,
    MAB_REG_RUN_CALIBRATE_OUTPUT_ENCODER_CMD = 0x084,
    MAB_REG_RUN_CALIBRATE_PI_GAINS = 0x085,
    MAB_REG_RUN_RESTORE_FACTORY_CONFIG = 0x087,
    MAB_REG_RUN_RESET = 0x088,
    MAB_REG_RUN_CLEAR_WARNINGS = 0x089,
    MAB_REG_RUN_CLEAR_ERRORS = 0x08A,
    MAB_REG_RUN_BLINK = 0x08B,
    MAB_REG_RUN_ZERO = 0x08C,
    MAB_REG_RUN_CAN_REINIT = 0x08D,

    // Calibration Results
    MAB_REG_CAL_OUTPUT_ENCODER_STD_DEV = 0x100,
    MAB_REG_CAL_OUTPUT_ENCODER_MIN_E = 0x101,
    MAB_REG_CAL_OUTPUT_ENCODER_MAX_E = 0x102,
    MAB_REG_CAL_MAIN_ENCODER_STD_DEV = 0x103,
    MAB_REG_CAL_MAIN_ENCODER_MIN_E = 0x104,
    MAB_REG_CAL_MAIN_ENCODER_MAX_E = 0x105,

    // Limits
    MAB_REG_POSITION_LIMIT_MAX = 0x110,
    MAB_REG_POSITION_LIMIT_MIN = 0x111,
    MAB_REG_MAX_TORQUE = 0x112,
    MAB_REG_MAX_VELOCITY = 0x113,
    MAB_REG_MAX_ACCELERATION = 0x114,
    MAB_REG_MAX_DECELERATION = 0x115,

    // Motion Profile
    MAB_REG_PROFILE_VELOCITY = 0x120,
    MAB_REG_PROFILE_ACCELERATION = 0x121,
    MAB_REG_PROFILE_DECELERATION = 0x122,
    MAB_REG_QUICK_STOP_DECELERATION = 0x123,
    MAB_REG_POSITION_WINDOW = 0x124,
    MAB_REG_VELOCITY_WINDOW = 0x125,

    // Motion Control
    MAB_REG_MOTION_MODE = 0x140,
    MAB_REG_READ_MOTION_MODE = 0x141,
    MAB_REG_STATE_MACHINE = 0x142,

    // Targets
    MAB_REG_TARGET_POSITION = 0x150,
    MAB_REG_TARGET_VELOCITY = 0x151,
    MAB_REG_TARGET_TORQUE = 0x152,

    // GPIO
    MAB_REG_USER_GPIO_CONFIGURATION = 0x160,
    MAB_REG_USER_GPIO_STATE = 0x161,

    // Direction
    MAB_REG_REVERSE_DIRECTION = 0x600,

    // Shunt Resistance
    MAB_REG_SHUNT_RESISTANCE = 0x700,

    // System Information
    MAB_REG_BUILD_DATE = 0x800,
    MAB_REG_COMMIT_HASH = 0x801,
    MAB_REG_FIRMWARE_VERSION = 0x802,
    MAB_REG_HARDWARE_VERSION = 0x803,
    MAB_REG_BRIDGE_TYPE = 0x804,
    MAB_REG_QUICK_STATUS = 0x805,
    MAB_REG_MOSFET_TEMPERATURE = 0x806,
    MAB_REG_MOTOR_TEMPERATURE = 0x807,
    MAB_REG_MOTOR_SHUTDOWN_TEMP = 0x808,
    MAB_REG_MAIN_ENCODER_ERRORS = 0x809,
    MAB_REG_OUTPUT_ENCODER_ERRORS = 0x80A,
    MAB_REG_CALIBRATION_ERRORS = 0x80B,
    MAB_REG_BRIDGE_ERRORS = 0x80C,
    MAB_REG_HARDWARE_ERRORS = 0x80D,
    MAB_REG_COMMUNICATION_ERRORS = 0x80E,
    MAB_REG_MOTION_ERRORS = 0x810
} mab_motors_register_addresses_t;

typedef enum mab_motors_register_size_t {
	mab_mainEncoderVelocity_size = 4,
	mab_mainEncoderPosition_size = 4,
	mab_motorTorque_size = 4,
	mab_targetPosition_size = 4,
	mab_targetVelocity_size = 4,
	mab_targetTorque_size = 4
} mab_motors_register_size_t;

class MabMotor_FDCAN: public BILBO_Drive_Motor {
public:
	MabMotor_FDCAN() {
	}

	HAL_StatusTypeDef init(mab_motor_config_t config);
	HAL_StatusTypeDef start(mab_motor_mode_t mode = MAB_MOTOR_MODE_IDLE);

	HAL_StatusTypeDef checkCommunication();
	HAL_StatusTypeDef checkMotor();

	HAL_StatusTypeDef beep(uint16_t amplitude);

	HAL_StatusTypeDef clearErrors();
	HAL_StatusTypeDef clearWarnings();
	HAL_StatusTypeDef resetMotor();

	HAL_StatusTypeDef setMode(mab_motor_mode_t motion_mode);
	HAL_StatusTypeDef setCANWatchdog(uint16_t timeout);
	HAL_StatusTypeDef setVelocityLimit(float maxVelocity);
	HAL_StatusTypeDef setTorqueLimit(float maxTorque);
	HAL_StatusTypeDef setImpedanceConstants(
			mab_motor_impedance_constants_t constants);

	HAL_StatusTypeDef setTorque(float torque);
	HAL_StatusTypeDef setLEDBlink(bool enable);
	HAL_StatusTypeDef setTargetVelocity(float velocity);
	HAL_StatusTypeDef setTargetPosition(float position);

	HAL_StatusTypeDef readMode(mab_motor_mode_t &mode);
	HAL_StatusTypeDef readSpeed(float &speed);
	HAL_StatusTypeDef readPosition(float &position);

	HAL_StatusTypeDef getTemperature(float &temperature);
	HAL_StatusTypeDef getVoltage(float &voltage);

	HAL_StatusTypeDef stop();

private:

	mab_motor_config_t config;
	mab_motor_mode_t mode;

//	mab_motors_register_addresses_t addresses;
//	mab_motors_register_size_t reg_sizes_t;

	HAL_StatusTypeDef write_register(uint16_t reg, uint8_t *data,
			uint8_t length);

	HAL_StatusTypeDef write_register(uint16_t reg, float data);
	HAL_StatusTypeDef write_register(uint16_t reg, uint8_t data);
	HAL_StatusTypeDef write_register(uint16_t reg, uint16_t data);
	HAL_StatusTypeDef write_register(uint16_t reg, uint32_t data);
	HAL_StatusTypeDef write_register(uint16_t reg, int16_t data);
	HAL_StatusTypeDef write_register(uint16_t reg, int32_t data);

	CAN_Status read_register(uint16_t reg, uint8_t *responseData,
			uint8_t requestLength, uint8_t &responseLength);

	HAL_StatusTypeDef read_register(uint16_t reg, float &data);
	HAL_StatusTypeDef read_register(uint16_t reg, uint8_t &data);
	HAL_StatusTypeDef read_register(uint16_t reg, uint16_t &data);
	HAL_StatusTypeDef read_register(uint16_t reg, uint32_t &data);
	HAL_StatusTypeDef read_register(uint16_t reg, int16_t &data);
	HAL_StatusTypeDef read_register(uint16_t reg, int32_t &data);


	void _error_handler();
};

#endif /* DRIVE_MAB_MOTORS_MAB_MOTOR_FDCAN_H_ */
