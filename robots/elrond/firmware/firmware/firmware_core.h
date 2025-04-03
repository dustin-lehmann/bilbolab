/*
 * firmware_core.h
 *
 *  Created on: Mar 7, 2025
 *      Author: lehmann
 */

#ifndef FIRMWARE_CORE_H_
#define FIRMWARE_CORE_H_

#include "stm32h7xx.h"
#include "core.h"
#include "firmware_addresses.h"
#include "firmware_defs.h"
#include "firmware_settings.h"
#include "twipr_errors.h"

extern uint32_t tick_global;

extern void send_debug(const char *format, ...);
extern void send_info(const char *format, ...);
extern void send_warning(const char *format, ...);
extern void send_error(const char *format, ...);


//extern void setFirmwareStateError();
extern void stopControl();


#endif /* FIRMWARE_CORE_H_ */
