/*
 * firmware_defs.h
 *
 *  Created on: 16 Mar 2023
 *      Author: lehmann_workstation
 */

#ifndef FIRMWARE_DEFS_H_
#define FIRMWARE_DEFS_H_

#include "core.h"
#include "firmware_settings.h"


// ------------------------------------------------------------------------------------------------ //
typedef struct twipr_firmware_revision_t {
	uint8_t major;
	uint8_t minor;
}twipr_firmware_revision_t;


typedef enum twipr_firmware_state_t {
	TWIPR_FIRMWARE_STATE_ERROR = -1,
	TWIPR_FIRMWARE_STATE_RUNNING = 1,
	TWIPR_FIRMWARE_STATE_NONE = 0,
} twipr_firmware_state_t;

typedef struct twipr_logging_general_t {
	uint32_t tick;
	twipr_firmware_state_t state;
} twipr_logging_general_t;

#define TWIPR_FIRMWARE_SAMPLE_BUFFER_SIZE (uint16_t) (TWIPR_FIRMWARE_SAMPLE_BUFFER_TIME * 1000 / TWIPR_CONTROL_TS_MS)
#define TWIPR_SEQUENCE_BUFFER_SIZE (uint32_t) (TWIPR_SEQUENCE_TIME * 1000/TWIPR_CONTROL_TS_MS)
#define TWIPR_CONTROL_TS_MS (uint32_t) (1000.0 / TWIPR_CONTROL_TASK_FREQ)

#ifdef BILBO_DRIVE_SIMPLEXMOTION_RS485
#define BILBO_DRIVE_TYPE BILBO_DRIVE_SM_RS485
#define BILBO_DRIVE_TASK_TIME 20
#endif

#ifdef BILBO_DRIVE_SIMPLEXMOTION_CAN
#define BILBO_DRIVE_TYPE BILBO_DRIVE_SM_CAN
#define BILBO_DRIVE_TASK_TIME 10
#endif


extern DMA_HandleTypeDef hdma_memtomem_dma2_stream0;
#define TWIPR_FIRMWARE_SAMPLE_DMA_STREAM &hdma_memtomem_dma2_stream0

extern DMA_HandleTypeDef hdma_memtomem_dma2_stream1;
#define TWIPR_FIRMWARE_TRAJECTORY_DMA_STREAM &hdma_memtomem_dma2_stream1

#endif /* FIRMWARE_DEFS_H_ */

