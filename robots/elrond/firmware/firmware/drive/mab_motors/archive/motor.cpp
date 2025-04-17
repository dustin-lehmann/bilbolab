/*
 * motor.cpp
 *
 *  Created on: Dec 10, 2024
 *      Author: mneub
 */

#include "motor.hpp"

md80::md80()
{

}

bool md80::init(uint8_t id, can_buffer* buffer)
{
	this->id = id;
	this->buffer = buffer;

	// Configure TxHeader for transmission
	this->buffer->TxHeader.Identifier = id; // TODO: controller identifier
	// same for all motors
	this->buffer->TxHeader.IdType = FDCAN_STANDARD_ID; //FDCAN_STANDARD_ID / FDCAN_EXTENDED_ID;
	this->buffer->TxHeader.TxFrameType = FDCAN_DATA_FRAME; // FDCAN_REMOTE_FRAME / FDCAN_DATA_FRAME
	this->buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_20;
	this->buffer->TxHeader.ErrorStateIndicator = FDCAN_ESI_ACTIVE;
	this->buffer->TxHeader.BitRateSwitch = FDCAN_BRS_OFF;
	this->buffer->TxHeader.FDFormat = FDCAN_FD_CAN;
	this->buffer->TxHeader.TxEventFifoControl = FDCAN_NO_TX_EVENTS;
	this->buffer->TxHeader.MessageMarker = 0;

	// TODO: ping

	return true;
}

void md80::pack_motion_state_frame()
{
	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_20;

	buffer->TxData[0] = 0x41;
	buffer->TxData[1] = 0x00;
	buffer->TxData[2] = (uint8_t) mainEncoderPosition_addr; // position addr
	buffer->TxData[3] = 0x00; // position addr
	buffer->TxData[4] = 0x00;
	buffer->TxData[5] = 0x00;
	buffer->TxData[6] = 0x00;
	buffer->TxData[7] = 0x00;
	buffer->TxData[8] = (uint8_t) mainEncoderVelocity_addr; // velocity addr
	buffer->TxData[9] = 0x00; // velocity addr
	buffer->TxData[10] = 0x00;
	buffer->TxData[11] = 0x00;
	buffer->TxData[12] = 0x00;
	buffer->TxData[13] = 0x00;
	buffer->TxData[14] = (uint8_t) motorTorque_addr; // torque addr
	buffer->TxData[15] = 0x00; // torque addr
	buffer->TxData[16] = 0x00;
	buffer->TxData[17] = 0x00;
	buffer->TxData[18] = 0x00;
	buffer->TxData[19] = 0x00;
}

/*
void md80::pack_motion_state_frame()
{
	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_20;

	buffer->TxData[0] = 0x41;
	buffer->TxData[1] = 0x00;
	buffer->TxData[2] = 0x42;// 142-state //(uint8_t) mainEncoderPosition_addr; // position addr
	buffer->TxData[3] = 0x01; // position addr
	buffer->TxData[4] = 0x00;
	buffer->TxData[5] = 0x00;
	buffer->TxData[6] = 0x00;
	buffer->TxData[7] = 0x00;
	buffer->TxData[8] = 0x00;//(uint8_t) mainEncoderVelocity_addr; // velocity addr
	buffer->TxData[9] = 0x00; // velocity addr
	buffer->TxData[10] = 0x00;
	buffer->TxData[11] = 0x00;
	buffer->TxData[12] = 0x00;
	buffer->TxData[13] = 0x00;
	buffer->TxData[14] = 0x00;//(uint8_t) motorTorque_addr; // torque addr
	buffer->TxData[15] = 0x00; // torque addr
	buffer->TxData[16] = 0x00;
	buffer->TxData[17] = 0x00;
	buffer->TxData[18] = 0x00;
	buffer->TxData[19] = 0x00;
}*/

void md80::pack_position_target_frame()
{
	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_8;

	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	//memcpy(&buffer->TxData[2], &targetPosition_addr, sizeof(uint8_t));
	buffer->TxData[2] = 0x50; // (uint8_t) targetPosition_addr; // reg ID
	buffer->TxData[3] = 0x01; // 0x00;  // reg ID
	//fill with float value
	memcpy(&buffer->TxData[4], &targets.positionTarget, sizeof(float));
}



void md80::pack_velocity_target_frame()
{
	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_8;

	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	buffer->TxData[2] = 0x51; //(uint8_t) targetVelocity_addr; // reg ID
	buffer->TxData[3] = 0x01; //0x00;  // reg ID
	//fill with float value
	memcpy(&buffer->TxData[4], &targets.velocityTarget, sizeof(float));
	//buffer->TxData[4] = 0x0A;
	//buffer->TxData[5] = 0x00;
	//buffer->TxData[6] = 0x00;
	//buffer->TxData[7] = 0x00;
}

void md80::pack_torque_target_frame()
{
	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_8;

	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	buffer->TxData[2] = 0x52; //(uint8_t) targetTorque_addr; // reg ID
	buffer->TxData[3] = 0x01;  // reg ID
	//fill with float value
	memcpy(&buffer->TxData[4], &targets.torqueTarget, sizeof(float));
}

void md80::unpack_motion_state_frame()
{
	state.velocity = *(float*)&buffer->RxData[10];
	state.torque = *(float*)&buffer->RxData[16];
}

void md80::pack_impedance_kp_kd()
{
	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_16; // 16 gibt´s nicht

	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	buffer->TxData[2] = (uint8_t) motorImpPidKp; // reg ID
	buffer->TxData[3] = 0x00;  // reg ID
	//fill with float value
	memcpy(&buffer->TxData[4], &impedance_constants.kp, sizeof(float));

	buffer->TxData[8] = (uint8_t) motorImpPidKd; // reg ID
	buffer->TxData[9] = 0x00;  // reg ID
	//fill with float value
	memcpy(&buffer->TxData[10], &impedance_constants.kd, sizeof(float));
}

void md80::pack_motion_mode_frame(ControlMode mode)
{
	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_5;

	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	buffer->TxData[2] = 0x40;// (uint8_t) motionModeCommand_addr; // reg ID
	buffer->TxData[3] = 0x01;  // reg ID

	switch (mode)
		{
			case IDLE:
				buffer->TxData[4] = 0x00;
				break;
			case POS_PID:
				buffer->TxData[4] = 0x01;
				break;
			case VELOCITY_PID:
				buffer->TxData[4] = 0x02;
				break;
			case RAW_TORQUE:
				buffer->TxData[4] = 0x03;
				break;
			case IMPEDANCE:
				buffer->TxData[4] = 0x04;
				break;
			case POSITION_PROFILE:
				buffer->TxData[4] = 0x07;
				break;
			case VELOCITY_PROFILE:
				buffer->TxData[4] = 0x08;
				break;
		}
}

void md80::rreq_motion_data()
{
	pack_motion_state_frame();

	// take semaphore = wait for new message
	// TODO: test if semaphore is released correctly when there is no answer
	/*
	if (osSemaphoreAcquire(newMsg_semaphoreHandle, portMAX_DELAY) != osOK)
	{
		Error_Handler();
	}*/

	// transmit
	buffer->transmit();
	osDelay(10);
	unpack_motion_state_frame();
	/*
	// wait for new message (semaphore is released in callback)
	if (osSemaphoreAcquire(newMsg_semaphoreHandle, pdMS_TO_TICKS(1000)) == osOK) // pdMS_TO_TICKS(1000) with timeout instead of portMAX_DELAY
	    {
			// TODO:check if response message has right varaibles (mainEncoderPosition_addr, ...)

	        // Unpack the received message into `md80.State`
			unpack_motion_state_frame();

			// release semaphore again
			osSemaphoreRelease(newMsg_semaphoreHandle);
	    }
	else
	{
		// release semaphore
		osSemaphoreRelease(newMsg_semaphoreHandle);

		// This should not happen unless something goes wrong with the semaphore handling
		Error_Handler();
	}*/
}

void md80::wreq_target(TargetType type, float new_target)
{

	// update targets and buffer
	switch (type)
	{
		case POSITION:
			targets.positionTarget = new_target;
			pack_position_target_frame();
			break;
		case VELOCITY:
			targets.velocityTarget = new_target;
			pack_velocity_target_frame();
			break;
		case TORQUE:
			targets.torqueTarget = new_target;
			pack_torque_target_frame();
			break;
	}

	// take semaphore = wait for new message
	// TODO: test if semaphore is released correctly when there is no answer
	/*
	if (osSemaphoreAcquire(newMsg_semaphoreHandle, portMAX_DELAY) != osOK)
	{
		Error_Handler();
	}*/

	// transmit
	osDelay(10);
	buffer->RxData[0] = 0x00;
	osDelay(10);
	buffer->transmit();
	osDelay(10);
	/*
	// wait for new message (semaphore is released in callback)
	if (osSemaphoreAcquire(newMsg_semaphoreHandle, pdMS_TO_TICKS(1000)) == osOK and buffer->RxData[0] == 0x0A) // pdMS_TO_TICKS(1000) with timeout instead of portMAX_DELAY
		{
			// release semaphore again
			osSemaphoreRelease(newMsg_semaphoreHandle);
		}
	else
	{
		// release semaphore
		osSemaphoreRelease(newMsg_semaphoreHandle);

		// This should not happen unless something goes wrong with the semaphore handling
		Error_Handler();
	}*/


}

void md80::set_motion_mode(ControlMode mode)
{
	pack_motion_mode_frame(mode);
	osDelay(10);
	// take semaphore = wait for new message
	// TODO: test if semaphore is released correctly when there is no answer
	/*
	if (osSemaphoreAcquire(newMsg_semaphoreHandle, portMAX_DELAY) != osOK)
	{
		Error_Handler();
	}*/

	// transmit
	buffer->transmit();
	osDelay(10);
	/*
	// wait for new message (semaphore is released in callback)
	if (osSemaphoreAcquire(newMsg_semaphoreHandle, pdMS_TO_TICKS(1000)) == osOK and buffer->RxData[0] == 0x0A) // pdMS_TO_TICKS(1000) with timeout instead of portMAX_DELAY
		{
			// release semaphore again
			osSemaphoreRelease(newMsg_semaphoreHandle);
		}
	else
	{
		// release semaphore
		osSemaphoreRelease(newMsg_semaphoreHandle);

		// This should not happen unless something goes wrong with the semaphore handling
		Error_Handler();
	}*/

}

void md80::set_resistance(float kd)
{

	set_motion_mode(IMPEDANCE);
	osDelay(100);

	impedance_constants.kp = 0.9;
	impedance_constants.kd = kd;
	osDelay(100);
	pack_impedance_kp_kd();
	osDelay(100);
	buffer->transmit();
	osDelay(100);


    /*wreq_target(VELOCITY, 3.0);
	osDelay(1);
	wreq_target(POSITION, 0.0);
	osDelay(1);*/


	/*
	if (osSemaphoreAcquire(newMsg_semaphoreHandle, portMAX_DELAY) != osOK)
	{
		Error_Handler();
	}*/
	// TODO: semaphores, check response


	// osDelay(3);
	/*
	if (buffer->RxData[0] == 0x0A) // pdMS_TO_TICKS(1000) with timeout instead of portMAX_DELAY
	{
				// release semaphore again
				osSemaphoreRelease(newMsg_semaphoreHandle);
	}*/
}

void md80::motor_calib_mode()
{
	// STARTS CALIBRATION MODE OF MOTOR -> SHOULD MOVE AFTER CALLING THAT (WAS ALREADY TESTED)

	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_5;

	// write 0x00 into register motorCalibrationMode, which means a full calibration should be done
	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	buffer->TxData[2] = 0x1E; // reg ID motorCalibrationMode
	buffer->TxData[3] = 0x00; // reg ID motorCalibrationMode
	buffer->TxData[4] = 0x00; // value to be written

	osDelay(100);
	buffer->transmit();
	osDelay(1000);

	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_5;

	// write another value than 0x00 into register runCalibrateCmd to start calibration
	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	buffer->TxData[2] = 0x83; // reg ID runCalibrateCmd
	buffer->TxData[3] = 0x00; // reg ID runCalibrateCmd
	buffer->TxData[4] = 0x01; // value to be written

	osDelay(100);
	buffer->transmit();
	osDelay(100);


}

void md80::run_encoder_calib()
{
	// TODO: trennen
	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_5;

	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	//memcpy(&buffer->TxData[2], &targetPosition_addr, sizeof(uint8_t));
	buffer->TxData[2] = 0x26; // (uint8_t) targetPosition_addr; // reg ID
	buffer->TxData[3] = 0x00; // reg ID
	buffer->TxData[4] = 0x00;

	osDelay(100);
	buffer->transmit();
	osDelay(100);


	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_5;

	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	//memcpy(&buffer->TxData[2], &targetPosition_addr, sizeof(uint8_t));
	buffer->TxData[2] = 0x84; // (uint8_t) targetPosition_addr; // reg ID
	buffer->TxData[3] = 0x00; // reg ID
	buffer->TxData[4] = 0x00;

	osDelay(100);
	buffer->transmit();
	osDelay(100);
}

void md80::clear_errors()
{
	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_5;

	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	//memcpy(&buffer->TxData[2], &targetPosition_addr, sizeof(uint8_t));
	buffer->TxData[2] = 0x89; // (uint8_t) targetPosition_addr; // reg ID
	buffer->TxData[3] = 0x00; // reg ID
	buffer->TxData[4] = 0x01;

	osDelay(100);
	buffer->transmit();
	osDelay(100);

	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_5;

	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	buffer->TxData[2] = 0x8A; // (uint8_t) targetPosition_addr; // reg ID
	buffer->TxData[3] = 0x00; // reg ID
	buffer->TxData[4] = 0x01;

	osDelay(100);
	buffer->transmit();
	osDelay(100);
}

void md80::restore_config()
{
	buffer->TxHeader.DataLength = FDCAN_DLC_BYTES_5;

	buffer->TxData[0] = 0x40;
	buffer->TxData[1] = 0x00;
	buffer->TxData[2] = 0x87; // (uint8_t) targetPosition_addr; // reg ID
	buffer->TxData[3] = 0x00; // reg ID
	buffer->TxData[4] = 0x01;

	osDelay(100);
	buffer->transmit();
	osDelay(100);
}


void md80::split_torque(float ratio)
{
	wreq_target(TORQUE, ratio*state.torque);
}
