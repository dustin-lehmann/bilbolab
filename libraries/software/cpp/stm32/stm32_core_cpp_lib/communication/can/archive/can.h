/*
 * can.h
 *
 *  Created on: May 26, 2024
 *      Author: lehmann
 */

#ifndef COMMUNICATION_CAN_CAN_H_
#define COMMUNICATION_CAN_CAN_H_

#include "stm32h7xx_hal.h"
#include "FreeRTOS.h"
#include "semphr.h"
#include "core.h"

#ifdef HAL_FDCAN_MODULE_ENABLED

// Configuration constants
#define CAN_NUMBER_CALLBACKS 8 // Number of callback slots
#define CAN_NUMBER_RR 16       // Maximum number of pending read requests

// Custom return type for sendRemoteFrame
enum CAN_Status {
    CAN_SUCCESS, CAN_READING_ERROR, CAN_RR_FULL
};

// Callback function type
//typedef void (*CANFrameCallback)(uint32_t id, const uint8_t *data, uint8_t length);

typedef struct can_frame_callback_input_t {
    uint32_t id;
    uint8_t *data;
    uint8_t length;
} can_frame_callback_input_t;

typedef core_utils_Callback<void, can_frame_callback_input_t> can_frame_callback;

struct CallbackEntry {
    can_frame_callback callback; // The callback function
    uint32_t FilterID1;          // Start of the filter range
    uint32_t FilterID2;          // End of the filter range
};

// Struct for pending read requests
typedef struct ReadRequest {
    uint32_t id;                  // The CAN ID for the read request
    uint8_t responseData[8];      // Buffer to store the response data
    uint8_t responseLength;       // Length of the response data
    TaskHandle_t taskHandle;      // Handle to the task waiting for notification
    bool isOpen;                  // Indicates if the read request is active
} ReadRequest;

typedef struct can_config_t {
    FDCAN_HandleTypeDef *hfdcan;
} can_config_t;

class CAN {
public:
    CAN();
    ~CAN();

    HAL_StatusTypeDef init(can_config_t config);
    HAL_StatusTypeDef start();

    bool registerStandardIDCallback(can_frame_callback callback,
                uint32_t FilterID1, uint32_t FilterID2);

    bool registerExtendedIDCallback(can_frame_callback callback,
                uint32_t FilterID1, uint32_t FilterID2);

    void removeStandardIDCallback(can_frame_callback callback);
    void removeExtendedIDCallback(can_frame_callback callback);

    bool addReadRequest(uint32_t id, TaskHandle_t taskHandle);
    void removeReadRequest(uint32_t id);
    void onMessageReceived(const FDCAN_RxHeaderTypeDef &header, uint8_t *data);

    HAL_StatusTypeDef sendMessage(uint32_t id,
            uint8_t *data, uint8_t length, bool isExtendedID = true);

    CAN_Status sendRemoteFrame(uint32_t id, uint32_t timeoutMs,
            uint8_t *responseData, uint8_t requestLength, uint8_t &responseLength);

    // New public function to reset the CAN module
    void reset();

    // Dedicated CAN task function to process incoming messages
    static void taskFunction(void *pvParameters);

    can_config_t config;

    QueueHandle_t messageQueue;

private:
    ReadRequest readRequests[CAN_NUMBER_RR]; // Fixed array for pending read requests
    CallbackEntry standardIDCallbacks[CAN_NUMBER_CALLBACKS]; // Callbacks for 11-bit frames
    CallbackEntry extendedIDCallbacks[CAN_NUMBER_CALLBACKS];   // Callbacks for 29-bit frames
    SemaphoreHandle_t mapMutex;                  // Mutex for thread-safe access

    // New private members for message queue and dedicated task

    TaskHandle_t canTaskHandle;
};

#endif

#endif /* COMMUNICATION_CAN_CAN_H_ */
