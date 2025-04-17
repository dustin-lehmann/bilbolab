/*
 * globals.cpp
 *
 *  Created on: Dec 10, 2024
 *      Author: mneub
 */

#include "globals.hpp"

// system specific objects
can_buffer buffer;
md80 motor;

// system specific inits
void initialize_globals()
{
	motor.init(0x64, &buffer); //0x6b=107
	FDCAN_FilterTypeDef sFilterConfig = create_hfdcan_filter(
			FDCAN_STANDARD_ID,
			0,
			FDCAN_FILTER_MASK,
			FDCAN_FILTER_TO_RXFIFO0,
			0x000,
			0x000
	);
	buffer.init(&hfdcan1, sFilterConfig);

	// HIER HABE ICH SACHEN AUSPROBIERT

	osDelay(100);
	//motor.motor_calib_mode();
	osDelay(100);
	//motor.run_encoder_calib();
	//motor.restore_config();
	//motor.set_motion_mode(md80::IDLE);
	//osDelay(100);
	//motor.clear_errors();
	//osDelay(100);
	//motor.wreq_target(md80::POSITION, 1.0); // wrong mode?
	//motor.wreq_target(md80::POSITION, 10.0);
	//motor.wreq_target(md80::POSITION, 100.0);
	//motor.set_resistance(0.2);


	// motor.motor_calib_mode();

	osDelay(1);
}

/*
// system specific callbacks
void HAL_FDCAN_RxFifo0Callback(FDCAN_HandleTypeDef* hfdcan1, uint32_t RxFifo0ITs)
// TODO: adjust
{
  if((RxFifo0ITs & FDCAN_IT_RX_FIFO0_NEW_MESSAGE) != RESET)
  {
    // Retreive Rx messages from RX FIFO0
    if (HAL_FDCAN_GetRxMessage(hfdcan1, FDCAN_RX_FIFO0, &buffer.RxHeader, buffer.RxData) != HAL_OK)
    {
		// Reception Error
    	Error_Handler();
    }

    // toggke semaphore (received message)
    // alternative: queue messages
    // osSemaphoreRelease(newMsg_semaphoreHandle);

    if (HAL_FDCAN_ActivateNotification(hfdcan1, FDCAN_IT_RX_FIFO0_NEW_MESSAGE, 0) != HAL_OK)
    {
    	// Notification Error
    	Error_Handler();
    }
  }
}
*/
