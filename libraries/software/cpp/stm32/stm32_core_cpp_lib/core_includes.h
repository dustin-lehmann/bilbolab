/*
 * core_defs.h
 *
 *  Created on: 8 Jul 2022
 *      Author: Dustin Lehmann
 */

#ifndef CORE_CORE_INCLUDES_H_
#define CORE_CORE_INCLUDES_H_

#ifdef CORE_CONFIG_OVERWRITE
#include <core_config.h>
#else
#include "core_default_config.h"
#endif

#ifdef CORE_CONFIG_MCU_STM32H7
#include "stm32h7xx_hal.h"
#endif



#if CORE_CONFIG_USE_RTOS
#include "FreeRTOS.h"
#include "task.h"
#include "cmsis_os.h"
#endif

#include "core_defs.h"


#endif /* CORE_CORE_INCLUDES_H_ */
