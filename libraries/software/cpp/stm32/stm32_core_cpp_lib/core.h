/*
 * core.h
 *
 *  Created on: Jul 6, 2022
 *      Author: Dustin Lehmann
 */

#ifndef CORE_CORE_H_
#define CORE_CORE_H_


#include <communication/uart_interface/core_comm_MessageQueue.h>
#include <communication/uart_interface/core_comm_UartInterface.h>
#include "ext/madgwick_ahrs/MadgwickAHRS.h"
#include "hardware/board_hardware/core_board_LedDriver.h"
#include "hardware/LED/core_hardware_led.h"
#include "hardware/UART/core_hardware_UART.h"
#include "hardware/BUTTON/core_hardware_button.h"
#include "memory/eeprom/core_memory_eeprom.h"
#include "sensors/IMU/bmi160.h"
#include "sensors/IMU/core_imu_helpers.h"
#include "communication/modbus_rtu/modbus_rtu.h"
#include "utils/core_debug.hpp"
#include "hardware/SPI/core_hardware_spi.h"
#include "control/pid/pid.h"
#include "communication/can/can_mab/can_mab.h"


#define _RAM_D2 __attribute__(( section(".ramd2block") ))

#endif /* CORE_CORE_H_ */
