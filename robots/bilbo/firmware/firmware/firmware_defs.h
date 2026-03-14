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
typedef struct bilbo_firmware_revision_t {
	uint8_t major;
	uint8_t minor;
}bilbo_firmware_revision_t;


typedef enum bilbo_firmware_state_t : int8_t {
	BILBO_FIRMWARE_STATE_ERROR = -1,
	BILBO_FIRMWARE_STATE_RUNNING = 1,
	BILBO_FIRMWARE_STATE_NONE = 0,
} bilbo_firmware_state_t;

// ------------------------------------------------------------------------------------------------ //
// Firmware info: compile-time settings readable by the host software
// ------------------------------------------------------------------------------------------------ //
typedef enum bilbo_board_revision_t : uint8_t {
	BILBO_BOARD_REV_3 = 3,
	BILBO_BOARD_REV_4 = 4,
} bilbo_board_revision_t;

typedef enum bilbo_model_type_t : uint8_t {
	BILBO_MODEL_TYPE_NORMAL = 0,
	BILBO_MODEL_TYPE_SMALL = 1,
	BILBO_MODEL_TYPE_BIG = 2,
} bilbo_model_type_t;

typedef enum bilbo_drive_interface_t : uint8_t {
	BILBO_DRIVE_INTERFACE_RS485 = 1,
	BILBO_DRIVE_INTERFACE_CAN = 2,
} bilbo_drive_interface_t;

typedef struct bilbo_firmware_info_t {
	bilbo_board_revision_t board_revision;
	bilbo_model_type_t model;
	bilbo_drive_interface_t drive_interface;
} bilbo_firmware_info_t;

// Resolve compile-time settings to enum values
#ifdef BOARD_REV_3
#define BILBO_BOARD_REV_VALUE BILBO_BOARD_REV_3
#elif defined(BOARD_REV_4)
#define BILBO_BOARD_REV_VALUE BILBO_BOARD_REV_4
#endif

#ifdef BILBO_MODEL_NORMAL
#define BILBO_MODEL_VALUE BILBO_MODEL_TYPE_NORMAL
#elif defined(BILBO_MODEL_SMALL)
#define BILBO_MODEL_VALUE BILBO_MODEL_TYPE_SMALL
#elif defined(BILBO_MODEL_BIG)
#define BILBO_MODEL_VALUE BILBO_MODEL_TYPE_BIG
#endif

#ifdef BILBO_DRIVE_SIMPLEXMOTION_RS485
#define BILBO_DRIVE_INTERFACE_VALUE BILBO_DRIVE_INTERFACE_RS485
#elif defined(BILBO_DRIVE_SIMPLEXMOTION_CAN)
#define BILBO_DRIVE_INTERFACE_VALUE BILBO_DRIVE_INTERFACE_CAN
#endif

// ------------------------------------------------------------------------------------------------ //

typedef struct bilbo_logging_general_t {
	bilbo_firmware_state_t state;
} bilbo_logging_general_t;

#define BILBO_FIRMWARE_SAMPLE_BUFFER_SIZE (uint16_t) (BILBO_FIRMWARE_SAMPLE_BUFFER_TIME * 1000 / BILBO_CONTROL_TS_MS)
#define BILBO_MAX_PENDING_BATCHES 4
#define BILBO_SEQUENCE_BUFFER_SIZE (uint32_t) (BILBO_SEQUENCE_TIME * 1000/BILBO_CONTROL_TS_MS)
#define BILBO_CONTROL_TS_MS (uint32_t) (1000.0 / BILBO_CONTROL_TASK_FREQ)

#ifdef BILBO_DRIVE_SIMPLEXMOTION_RS485
#define BILBO_DRIVE_TYPE BILBO_DRIVE_SM_RS485
#define BILBO_DRIVE_TASK_TIME 20
#endif

#ifdef BILBO_DRIVE_SIMPLEXMOTION_CAN
#define BILBO_DRIVE_TYPE BILBO_DRIVE_SM_CAN
#define BILBO_DRIVE_TASK_TIME 10
#endif


extern DMA_HandleTypeDef hdma_memtomem_dma2_stream0;
#define BILBO_FIRMWARE_SAMPLE_DMA_STREAM &hdma_memtomem_dma2_stream0

extern DMA_HandleTypeDef hdma_memtomem_dma2_stream1;
#define BILBO_FIRMWARE_TRAJECTORY_DMA_STREAM &hdma_memtomem_dma2_stream1

#endif /* FIRMWARE_DEFS_H_ */

