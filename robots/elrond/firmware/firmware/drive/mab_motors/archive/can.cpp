/*
 * can.cpp
 *
 *  Created on: Dec 10, 2024
 *      Author: mneub
 */


#include "can.hpp"
#include "main.h"


can_buffer::can_buffer()
{

}

bool can_buffer::init(FDCAN_HandleTypeDef* hfdcan, FDCAN_FilterTypeDef sFilterConfig)
{
	this->hfdcan = hfdcan;

	can_config_t can_config = {hfdcan};
	this->can.init(can_config);

	//fdcan_init(this->hfdcan, sFilterConfig);

	return true;
}

void can_buffer::transmit()
{

	//this->can.sendMessage(this->TxHeader.Identifier, this->TxData, length, isExtendedID);
	/*
	// TODO: consider data_length
	if (HAL_FDCAN_AddMessageToTxFifoQ(hfdcan, &TxHeader, TxData) != HAL_OK)
		{
			Error_Handler();
		}
	*/
}

FDCAN_FilterTypeDef create_hfdcan_filter(uint32_t IdType, uint32_t FilterIndex, uint32_t FilterType, uint32_t FilterConfig, uint32_t FilterID1, uint32_t FilterID2)
{
	FDCAN_FilterTypeDef sFilterConfig;

	sFilterConfig.IdType = IdType;
	sFilterConfig.FilterIndex = FilterIndex;
	sFilterConfig.FilterType = FilterType;
	sFilterConfig.FilterConfig = FilterConfig;
	sFilterConfig.FilterID1 = FilterID1;
	sFilterConfig.FilterID2 = FilterID2;

	return sFilterConfig;
}


void fdcan_init(FDCAN_HandleTypeDef* hfdcan, FDCAN_FilterTypeDef sFilterConfig)
{

	/*
	if (HAL_FDCAN_ConfigFilter(hfdcan, &sFilterConfig) != HAL_OK)
	{
	  // Filter configuration Error
	  Error_Handler();

	// start FDCAN
	// if data is received, HAL_FDCAN_RxFifo0Callback() is triggert
	if(HAL_FDCAN_Start(hfdcan)!= HAL_OK)
	{
		Error_Handler();
	}
	if (HAL_FDCAN_ActivateNotification(hfdcan, FDCAN_IT_RX_FIFO0_NEW_MESSAGE, 0) != HAL_OK) // FDCAN_IT_RX_FIFO0_NEW_MESSAGE is the interrupt flag
	{
		//Notification Error
		Error_Handler();
	}
	*/
}



