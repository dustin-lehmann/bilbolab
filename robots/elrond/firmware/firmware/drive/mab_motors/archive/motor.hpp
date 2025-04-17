/*
 * motor.hpp
 *
 *  Created on: Dec 10, 2024
 *      Author: mneub
 */

#ifndef MOTOR_HPP_
#define MOTOR_HPP_

#include "can.hpp"
#include "stm32h7xx_hal.h"
#include "cmsis_os.h"
#include "main.h"
#include <stdio.h>
#include <string.h>


class md80
{
	public:
		struct State
		{
			float position;
			float velocity;
			float torque;
			// TODO: find out why encoder seperate variables
			// float outputEncoderPosition;
			// float outputEncoderVelocity;
		};

		struct Targets
		{
			float positionTarget;
			float velocityTarget;
			float torqueTarget;
		};

		enum TargetType
		{
			POSITION,
			VELOCITY,
			TORQUE
		};

		enum ControlMode
		{
			IDLE,
			POS_PID,
			VELOCITY_PID,
			RAW_TORQUE,
			IMPEDANCE,
			POSITION_PROFILE,
			VELOCITY_PROFILE
		};

		struct Impedance_constants
		{
			float kp;
			float kd;
		};

		md80();
		bool init(uint8_t id, can_buffer* buffer);
		void rreq_motion_data();
		void wreq_target(TargetType type, float new_target);
		void set_motion_mode(ControlMode mode);
		void set_resistance(float kd); // this starts impedance mode, sets kp,target_vel,target_pos to zero -> first operation mode for exo prototype
		void split_torque(float ratio);
		void motor_calib_mode();
		void clear_errors();
		void restore_config();
		void run_encoder_calib();

	private:
		int id;
		can_buffer* buffer;
		State state;
		Targets targets;
		Impedance_constants impedance_constants;

		enum Reg_Addr
		{
			mainEncoderVelocity_addr = 0x062,
			mainEncoderPosition_addr = 0x063,
			motorTorque_addr = 0x064,
			targetPosition_addr = 0x150,
			targetVelocity_addr = 0x151,
			targetTorque_addr = 0x152,
			motionModeCommand_addr = 0x140,
			motorImpPidKp = 0x050,
			motorImpPidKd = 0x051
		};
		enum Reg_Size_Bytes
		{
			mainEncoderVelocity_size = 4,
			mainEncoderPosition_size = 4,
			motorTorque_size = 4,
			targetPosition_size = 4,
			targetVelocity_size = 4,
			targetTorque_size = 4
		};
		void pack_motion_state_frame(); // pack TxFrame to read position, velocity, torque
		void unpack_motion_state_frame();
		void pack_position_target_frame(); // pack TxFrame to set position, velocity, torque
		void pack_velocity_target_frame();
		void pack_torque_target_frame();
		void pack_motion_mode_frame(ControlMode mode);
		void pack_impedance_kp_kd();
};

extern osSemaphoreId_t newMsg_semaphoreHandle;

#endif /* MOTOR_HPP_ */
