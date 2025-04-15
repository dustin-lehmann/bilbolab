/*
 * can.cpp
 *
 *  Created on: May 26, 2024
 *      Author: lehmann
 *
 *  Modified: Added a dedicated CAN task and a message queue to remove processing from the ISR.
 */

#include <cstring>
#include "can.h"

// Additional includes required for FreeRTOS queues and tasks
#include "FreeRTOS.h"
#include "queue.h"
#include "task.h"

// Global instance pointer for CAN (used by the ISR)
CAN *can;

// Structure for queued CAN messages.
struct CAN_Message {
    FDCAN_RxHeaderTypeDef header;
    uint8_t data[8];
};

// Define a queue length for incoming messages.
#define CAN_QUEUE_LENGTH 16

uint32_t mapDLC(uint8_t dataLength);

CAN::CAN() {
    this->mapMutex = xSemaphoreCreateMutex(); // Mutex for task-level synchronization
    // Create a queue for incoming CAN messages from the ISR.
    this->messageQueue = xQueueCreate(CAN_QUEUE_LENGTH, sizeof(CAN_Message));
    this->canTaskHandle = nullptr;
}

CAN::~CAN() {
    xSemaphoreTake(this->mapMutex, portMAX_DELAY);
    for (int i = 0; i < CAN_NUMBER_RR; i++) {
        if (readRequests[i].isOpen) {
            // Close any open read requests
            readRequests[i].isOpen = false;
        }
    }
    xSemaphoreGive(this->mapMutex);
    vSemaphoreDelete(this->mapMutex);

    // Optionally clean up the message queue.
    vQueueDelete(this->messageQueue);
}

HAL_StatusTypeDef CAN::init(can_config_t config) {
    HAL_StatusTypeDef status;
    can = this;
    this->config = config;

    // Initialize read requests
    for (int i = 0; i < CAN_NUMBER_RR; i++) {
        readRequests[i].id = 0;
        readRequests[i].taskHandle = nullptr;
        readRequests[i].isOpen = false;
    }

    for (int i = 0; i < CAN_NUMBER_CALLBACKS; i++) {
        standardIDCallbacks[i].FilterID1 = 0x000;
        standardIDCallbacks[i].FilterID2 = 0x7FF; // Default: match all 11-bit IDs
        standardIDCallbacks[i].callback.registered = false;

        extendedIDCallbacks[i].callback = nullptr;
        extendedIDCallbacks[i].FilterID1 = 0x00000000;
        extendedIDCallbacks[i].FilterID2 = 0x1FFFFFFF; // Default: match all 29-bit IDs
        extendedIDCallbacks[i].callback.registered = false;
    }

    // Configure filters (same as original)
    FDCAN_FilterTypeDef filterConfig;

    // Filter for 11-bit frames -> FIFO 1
    filterConfig.IdType = FDCAN_STANDARD_ID;
    filterConfig.FilterIndex = 0; // First filter
    filterConfig.FilterType = FDCAN_FILTER_RANGE;
    filterConfig.FilterConfig = FDCAN_FILTER_TO_RXFIFO1; // Route to FIFO 1
    filterConfig.FilterID1 = 0x000; // Match all 11-bit IDs (0x000 to 0x7FF)
    filterConfig.FilterID2 = 0x7FF;
    status = HAL_FDCAN_ConfigFilter(this->config.hfdcan, &filterConfig);
    if (status != HAL_OK) {
        return status;
    }

    // Filter for 29-bit frames -> FIFO 0
    filterConfig.IdType = FDCAN_EXTENDED_ID;
    filterConfig.FilterIndex = 1; // Second filter
    filterConfig.FilterType = FDCAN_FILTER_RANGE;
    filterConfig.FilterConfig = FDCAN_FILTER_TO_RXFIFO0; // Route to FIFO 0
    filterConfig.FilterID1 = 0x00000000; // Match all 29-bit IDs (0x00000000 to 0x1FFFFFFF)
    filterConfig.FilterID2 = 0x1FFFFFFF;
    status = HAL_FDCAN_ConfigFilter(this->config.hfdcan, &filterConfig);
    if (status != HAL_OK) {
        return status;
    }

    // Enable Notifications
    status = HAL_FDCAN_ActivateNotification(this->config.hfdcan,
        FDCAN_IT_RX_FIFO0_NEW_MESSAGE, 0);
    status = HAL_FDCAN_ActivateNotification(this->config.hfdcan,
        FDCAN_IT_RX_FIFO1_NEW_MESSAGE, 0);

    return status;
}

HAL_StatusTypeDef CAN::start() {
    HAL_StatusTypeDef status = HAL_FDCAN_Start(this->config.hfdcan);
    // Create a dedicated CAN task to process messages from the queue.
    xTaskCreate(CAN::taskFunction, "CAN_Task", configMINIMAL_STACK_SIZE, this, tskIDLE_PRIORITY + 1, &this->canTaskHandle);
    return status;
}

bool CAN::addReadRequest(uint32_t id, TaskHandle_t taskHandle) {
    xSemaphoreTake(this->mapMutex, portMAX_DELAY);
    for (int i = 0; i < CAN_NUMBER_RR; i++) {
        if (!readRequests[i].isOpen) {
            readRequests[i].id = id;
            readRequests[i].taskHandle = taskHandle;
            readRequests[i].isOpen = true;
            xSemaphoreGive(this->mapMutex);
            return true;
        }
    }
    xSemaphoreGive(this->mapMutex);
    return false;
}

void CAN::removeReadRequest(uint32_t id) {
    xSemaphoreTake(this->mapMutex, portMAX_DELAY);
    for (int i = 0; i < CAN_NUMBER_RR; i++) {
        if (readRequests[i].isOpen && readRequests[i].id == id) {
            readRequests[i].isOpen = false;
            readRequests[i].taskHandle = nullptr;
            break;
        }
    }
    xSemaphoreGive(this->mapMutex);
}

// This function now runs in task context (via the dedicated CAN task)
// so it is safe to use the mapMutex while processing incoming messages.
void CAN::onMessageReceived(const FDCAN_RxHeaderTypeDef &header, uint8_t *data) {
    xSemaphoreTake(this->mapMutex, portMAX_DELAY);
    // Check for matching read request
    for (int i = 0; i < CAN_NUMBER_RR; i++) {
        if (readRequests[i].isOpen && readRequests[i].id == header.Identifier) {
            uint8_t actualLength = (uint8_t) header.DataLength;
            memcpy(readRequests[i].responseData, data, actualLength);
            readRequests[i].responseLength = actualLength;
            readRequests[i].isOpen = false;
            // Notify the waiting task
            xTaskNotifyGive(readRequests[i].taskHandle);
            break;
        }
    }
    xSemaphoreGive(this->mapMutex);

//    // Process callbacks (if needed)
//    ... (callback processing code remains as originally commented)
}

HAL_StatusTypeDef CAN::sendMessage(uint32_t id, uint8_t *data, uint8_t length, bool isExtendedID) {
    // Map the length to a valid DLC value.
    uint32_t can_dlc = mapDLC(length);
    if (can_dlc == 0xFFFFFFFF) {
        return HAL_ERROR;
    }
    FDCAN_TxHeaderTypeDef TxHeader = {
        .Identifier = id,
        .IdType = isExtendedID ? FDCAN_EXTENDED_ID : FDCAN_STANDARD_ID,
        .TxFrameType = FDCAN_DATA_FRAME,
        .DataLength = can_dlc,
        .ErrorStateIndicator = FDCAN_ESI_ACTIVE,
        .BitRateSwitch = FDCAN_BRS_OFF,
        .FDFormat = FDCAN_CLASSIC_CAN,
        .TxEventFifoControl = FDCAN_NO_TX_EVENTS,
        .MessageMarker = 0
    };
    HAL_StatusTypeDef status = HAL_FDCAN_AddMessageToTxFifoQ(this->config.hfdcan, &TxHeader, data);
    if (status) {
        nop(); // Placeholder for any additional logic if needed.
    }
    return status;
}

CAN_Status CAN::sendRemoteFrame(uint32_t id, uint32_t timeoutMs,
    uint8_t *responseData, uint8_t requestLength, uint8_t &responseLength) {

    TaskHandle_t currentTask = xTaskGetCurrentTaskHandle();
    if (!addReadRequest(id, currentTask)) {
        return CAN_RR_FULL;
    }

    FDCAN_TxHeaderTypeDef TxHeader = {
        .Identifier = id,
        .IdType = FDCAN_EXTENDED_ID, // Adjust if standard IDs should also be allowed.
        .TxFrameType = FDCAN_REMOTE_FRAME,
        .DataLength = mapDLC(requestLength),
        .ErrorStateIndicator = FDCAN_ESI_ACTIVE,
        .BitRateSwitch = FDCAN_BRS_OFF,
        .FDFormat = FDCAN_CLASSIC_CAN,
        .TxEventFifoControl = FDCAN_NO_TX_EVENTS,
        .MessageMarker = 0
    };

    if (HAL_FDCAN_AddMessageToTxFifoQ(this->config.hfdcan, &TxHeader, nullptr) != HAL_OK) {
        removeReadRequest(id);
        return CAN_READING_ERROR;
    }

    if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(timeoutMs)) > 0) {
        xSemaphoreTake(this->mapMutex, portMAX_DELAY);
        for (int i = 0; i < CAN_NUMBER_RR; i++) {
            if (readRequests[i].id == id && !readRequests[i].isOpen) {
                memcpy(responseData, readRequests[i].responseData, readRequests[i].responseLength);
                responseLength = readRequests[i].responseLength;
                break;
            }
        }
        xSemaphoreGive(this->mapMutex);
        removeReadRequest(id);
        return CAN_SUCCESS;
    } else {
        removeReadRequest(id);
        return CAN_READING_ERROR;
    }
}

// The reset() function remains largely unchanged.
void CAN::reset() {
    HAL_FDCAN_Stop(this->config.hfdcan);
    xSemaphoreTake(this->mapMutex, portMAX_DELAY);
    for (int i = 0; i < CAN_NUMBER_RR; i++) {
        readRequests[i].isOpen = false;
        readRequests[i].taskHandle = nullptr;
    }
    xSemaphoreGive(this->mapMutex);
    HAL_FDCAN_Start(this->config.hfdcan);
}

// Dedicated CAN task that waits on the queue and processes messages.
void CAN::taskFunction(void *pvParameters) {
    CAN *instance = reinterpret_cast<CAN*>(pvParameters);
    CAN_Message msg;
    for (;;) {
        if (xQueueReceive(instance->messageQueue, &msg, portMAX_DELAY) == pdPASS) {
            instance->onMessageReceived(msg.header, msg.data);
        }
    }
}

// IRQ Callback Integration for FIFO 0 (29-bit IDs)
// Now the ISR packs the message and posts it to the queue.
extern "C" void HAL_FDCAN_RxFifo0Callback(FDCAN_HandleTypeDef *hfdcan,
        uint32_t RxFifo0ITs) {
    CAN_Message msg;
    if (HAL_FDCAN_GetRxMessage(hfdcan, FDCAN_RX_FIFO0, &msg.header, msg.data) == HAL_OK) {
        BaseType_t higherPriorityTaskWoken = pdFALSE;
        if(xQueueSendFromISR(can->messageQueue, &msg, &higherPriorityTaskWoken) != pdPASS) {
            // Queue full – message is dropped; consider error handling.
        }
        portYIELD_FROM_ISR(higherPriorityTaskWoken);
    }
}

// IRQ Callback Integration for FIFO 1 (11-bit IDs)
extern "C" void HAL_FDCAN_RxFifo1Callback(FDCAN_HandleTypeDef *hfdcan,
        uint32_t RxFifo1ITs) {
    CAN_Message msg;
    if (HAL_FDCAN_GetRxMessage(hfdcan, FDCAN_RX_FIFO1, &msg.header, msg.data) == HAL_OK) {
        BaseType_t higherPriorityTaskWoken = pdFALSE;
        if(xQueueSendFromISR(can->messageQueue, &msg, &higherPriorityTaskWoken) != pdPASS) {
            // Queue full – message is dropped.
        }
        portYIELD_FROM_ISR(higherPriorityTaskWoken);
    }
}

uint32_t mapDLC(uint8_t dataLength) {
    switch (dataLength) {
    case 0:
        return FDCAN_DLC_BYTES_0;
    case 1:
        return FDCAN_DLC_BYTES_1;
    case 2:
        return FDCAN_DLC_BYTES_2;
    case 3:
        return FDCAN_DLC_BYTES_3;
    case 4:
        return FDCAN_DLC_BYTES_4;
    case 5:
        return FDCAN_DLC_BYTES_5;
    case 6:
        return FDCAN_DLC_BYTES_6;
    case 7:
        return FDCAN_DLC_BYTES_7;
    case 8:
        return FDCAN_DLC_BYTES_8;
    case 12:
        return FDCAN_DLC_BYTES_12;
    case 16:
        return FDCAN_DLC_BYTES_16;
    case 20:
        return FDCAN_DLC_BYTES_20;
    case 24:
        return FDCAN_DLC_BYTES_24;
    case 32:
        return FDCAN_DLC_BYTES_32;
    case 48:
        return FDCAN_DLC_BYTES_48;
    case 64:
        return FDCAN_DLC_BYTES_64;
    default:
        return 0xFFFFFFFF; // Invalid DLC value
    }
}
