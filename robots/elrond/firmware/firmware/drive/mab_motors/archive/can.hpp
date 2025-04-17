/*
 * can.hpp
 *
 *  Created on: Dec 10, 2024
 *      Author: mneub
 */

#ifndef CAN_HPP_
#define CAN_HPP_

// includes
#include "stm32h7xx_hal.h"
#include "stm32h7xx_hal_fdcan.h"
#include "cmsis_os.h"
#include "can.h"


FDCAN_FilterTypeDef create_hfdcan_filter(
		uint32_t IdType,
		uint32_t FilterIndex,
		uint32_t FilterType,
		uint32_t FilterConfig,
		uint32_t FilterID1,
		uint32_t FilterID2
);

void fdcan_init(FDCAN_HandleTypeDef* hfdcan, FDCAN_FilterTypeDef sFilterConfig);

class can_buffer{
	public:
		FDCAN_TxHeaderTypeDef TxHeader;
		FDCAN_RxHeaderTypeDef RxHeader;

		CAN can;

		uint8_t RxData[20];
		uint8_t TxData[20];
		int indx = 0; // TODO: check what this was needed for in tutorial

		void transmit();

		can_buffer();
		bool init(FDCAN_HandleTypeDef* hfdcan, FDCAN_FilterTypeDef sFilterConfig);
		FDCAN_HandleTypeDef* hfdcan; // TODO: private?

};

// extern osSemaphoreId_t newMsg_semaphoreHandle;


#endif /* CAN_HPP_ */
