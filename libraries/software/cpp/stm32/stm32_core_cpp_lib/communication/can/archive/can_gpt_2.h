/*
 * can_gpt_2.h
 *
 *  Created on: Nov 30, 2024
 *      Author: lehmann
 */

#ifndef COMMUNICATION_CAN_CAN_GPT_2_H_
#define COMMUNICATION_CAN_CAN_GPT_2_H_

#include "FreeRTOS.h"
#include "semphr.h"
#include "main.h"

// Configuration constants
#define CAN_NUMBER_CALLBACKS 8 // Number of callback slots
#define CAN_NUMBER_RR 16       // Maximum number of pending read requests

// Custom return type for sendRemoteFrame
enum CAN_Status {
    CAN_SUCCESS,
    CAN_READING_ERROR,
    CAN_RR_FULL
};

// Callback function type
typedef void (*CANFrameCallback)(uint32_t id, const uint8_t* data, uint8_t length);

// Struct for pending read requests
struct ReadRequest {
    uint32_t id;                  // CAN ID of the request
    SemaphoreHandle_t semaphore;  // Semaphore for the request
    bool isOpen;                  // Indicates if the request is active
    uint8_t responseLength;       // Length of the received response
    uint8_t responseData[8];      // Buffer for the response payload
};

class CANManager {
private:
    ReadRequest readRequests[CAN_NUMBER_RR];           // Fixed array for pending read requests
    CANFrameCallback standardIDCallbacks[CAN_NUMBER_CALLBACKS]; // Callbacks for 11-bit frames
    CANFrameCallback extendedIDCallbacks[CAN_NUMBER_CALLBACKS]; // Callbacks for 29-bit frames
    SemaphoreHandle_t mapMutex;                        // Mutex for thread-safe access

public:
    // Constructor
    CANManager() {
        mapMutex = xSemaphoreCreateMutex(); // Create a mutex for thread safety

        // Initialize read requests
        for (int i = 0; i < CAN_NUMBER_RR; i++) {
            readRequests[i].id = 0;
            readRequests[i].semaphore = nullptr;
            readRequests[i].isOpen = false;
        }

        // Initialize callback arrays
        for (int i = 0; i < CAN_NUMBER_CALLBACKS; i++) {
            standardIDCallbacks[i] = nullptr;
            extendedIDCallbacks[i] = nullptr;
        }
    }

    // Destructor
    ~CANManager() {
        // Free all active semaphores
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        for (int i = 0; i < CAN_NUMBER_RR; i++) {
            if (readRequests[i].isOpen && readRequests[i].semaphore != nullptr) {
                vSemaphoreDelete(readRequests[i].semaphore);
            }
        }
        xSemaphoreGive(mapMutex);

        vSemaphoreDelete(mapMutex); // Delete the mutex
    }

    // Initialize the CAN peripheral with filters
    HAL_StatusTypeDef init(FDCAN_HandleTypeDef* hfdcan) {
        // Start the FDCAN peripheral
        HAL_StatusTypeDef status = HAL_FDCAN_Start(hfdcan);
        if (status != HAL_OK) {
            return status;
        }

        // Configure filters
        FDCAN_FilterTypeDef filterConfig;

        // Filter for 11-bit frames -> FIFO 1
        filterConfig.IdType = FDCAN_STANDARD_ID;
        filterConfig.FilterIndex = 0; // First filter
        filterConfig.FilterType = FDCAN_FILTER_RANGE_NO_AFFECT;
        filterConfig.FilterConfig = FDCAN_FILTER_TO_RXFIFO1; // Route to FIFO 1
        filterConfig.FilterID1 = 0x000; // Match all 11-bit IDs (0x000 to 0x7FF)
        filterConfig.FilterID2 = 0x7FF;
        status = HAL_FDCAN_ConfigFilter(hfdcan, &filterConfig);
        if (status != HAL_OK) {
            return status;
        }

        // Filter for 29-bit frames -> FIFO 0
        filterConfig.IdType = FDCAN_EXTENDED_ID;
        filterConfig.FilterIndex = 1; // Second filter
        filterConfig.FilterType = FDCAN_FILTER_RANGE_NO_AFFECT;
        filterConfig.FilterConfig = FDCAN_FILTER_TO_RXFIFO0; // Route to FIFO 0
        filterConfig.FilterID1 = 0x00000000; // Match all 29-bit IDs (0x00000000 to 0x1FFFFFFF)
        filterConfig.FilterID2 = 0x1FFFFFFF;
        return HAL_FDCAN_ConfigFilter(hfdcan, &filterConfig);
    }

    // Register a callback for 11-bit CAN frames
    bool registerStandardIDCallback(CANFrameCallback callback) {
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        for (int i = 0; i < CAN_NUMBER_CALLBACKS; i++) {
            if (standardIDCallbacks[i] == nullptr) {
                standardIDCallbacks[i] = callback;
                xSemaphoreGive(mapMutex);
                return true; // Callback registered successfully
            }
        }
        xSemaphoreGive(mapMutex);
        return false; // No available slots
    }

    // Register a callback for 29-bit CAN frames
    bool registerExtendedIDCallback(CANFrameCallback callback) {
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        for (int i = 0; i < CAN_NUMBER_CALLBACKS; i++) {
            if (extendedIDCallbacks[i] == nullptr) {
                extendedIDCallbacks[i] = callback;
                xSemaphoreGive(mapMutex);
                return true; // Callback registered successfully
            }
        }
        xSemaphoreGive(mapMutex);
        return false; // No available slots
    }

    // Add a pending read request
    bool addReadRequest(uint32_t id, SemaphoreHandle_t semaphore) {
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        for (int i = 0; i < CAN_NUMBER_RR; i++) {
            if (!readRequests[i].isOpen) {
                readRequests[i].id = id;
                readRequests[i].semaphore = semaphore;
                readRequests[i].isOpen = true;
                xSemaphoreGive(mapMutex);
                return true; // Read request added successfully
            }
        }
        xSemaphoreGive(mapMutex);
        return false; // No available slots
    }

    // Remove a pending read request
    void removeReadRequest(uint32_t id) {
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        for (int i = 0; i < CAN_NUMBER_RR; i++) {
            if (readRequests[i].isOpen && readRequests[i].id == id) {
                if (readRequests[i].semaphore != nullptr) {
                    vSemaphoreDelete(readRequests[i].semaphore);
                }
                readRequests[i].isOpen = false;
                break;
            }
        }
        xSemaphoreGive(mapMutex);
    }

    // IRQ Callback to handle received messages
    void onMessageReceived(const FDCAN_RxHeaderTypeDef& header, uint8_t* data) {
        xSemaphoreTake(mapMutex, portMAX_DELAY);

        // Check for matching read request
        for (int i = 0; i < CAN_NUMBER_RR; i++) {
            if (readRequests[i].isOpen && readRequests[i].id == header.Identifier) {
                // Extract actual response length from header
                uint8_t actualLength = header.DataLength >> 16;

                // Store the response data and length
                memcpy(readRequests[i].responseData, data, actualLength);
                readRequests[i].responseLength = actualLength;

                xSemaphoreGive(readRequests[i].semaphore); // Signal the waiting task
                readRequests[i].isOpen = false;            // Mark request as closed
                break;
            }
        }

        // Process 11-bit frames
        if (header.IdType == FDCAN_STANDARD_ID) {
            for (int i = 0; i < CAN_NUMBER_CALLBACKS; i++) {
                if (standardIDCallbacks[i] != nullptr) {
                    standardIDCallbacks[i](header.Identifier, data, header.DataLength >> 16);
                }
            }
        }

        // Process 29-bit frames
        if (header.IdType == FDCAN_EXTENDED_ID) {
            for (int i = 0; i < CAN_NUMBER_CALLBACKS; i++) {
                if (extendedIDCallbacks[i] != nullptr) {
                    extendedIDCallbacks[i](header.Identifier, data, header.DataLength >> 16);
                }
            }
        }

        xSemaphoreGive(mapMutex);
    }


    // Method to send a CAN message (11-bit or 29-bit)
    HAL_StatusTypeDef sendMessage(FDCAN_HandleTypeDef* hfdcan, uint32_t id, uint8_t* data, uint8_t length, bool isExtendedID = true) {
        FDCAN_TxHeaderTypeDef TxHeader = {
            .Identifier = id,
            .IdType = isExtendedID ? FDCAN_EXTENDED_ID : FDCAN_STANDARD_ID,
            .TxFrameType = FDCAN_DATA_FRAME,
            .DataLength = length << 16, // Convert length to DLC
            .ErrorStateIndicator = FDCAN_ESI_ACTIVE,
            .BitRateSwitch = FDCAN_BRS_OFF,
            .FDFormat = FDCAN_CLASSIC_CAN,
            .TxEventFifoControl = FDCAN_NO_TX_EVENTS,
            .MessageMarker = 0
        };

        return HAL_FDCAN_AddMessageToTxFifoQ(hfdcan, &TxHeader, data);
    }

    // Method to send a remote frame and wait for a response
    CAN_Status sendRemoteFrame(FDCAN_HandleTypeDef* hfdcan, uint32_t id, uint32_t timeoutMs, uint8_t* responseData, uint8_t& responseLength) {
        SemaphoreHandle_t responseSemaphore = xSemaphoreCreateBinary();

        // Add the read request
        if (!addReadRequest(id, responseSemaphore)) {
            vSemaphoreDelete(responseSemaphore);
            return CAN_RR_FULL;
        }

        // Send Remote Frame
        FDCAN_TxHeaderTypeDef TxHeader = {
            .Identifier = id,
            .IdType = FDCAN_EXTENDED_ID,
            .TxFrameType = FDCAN_REMOTE_FRAME,
            .DataLength = FDCAN_DLC_BYTES_8, // 8-byte data length (as per CAN spec for remote frames)
            .ErrorStateIndicator = FDCAN_ESI_ACTIVE,
            .BitRateSwitch = FDCAN_BRS_OFF,
            .FDFormat = FDCAN_CLASSIC_CAN,
            .TxEventFifoControl = FDCAN_NO_TX_EVENTS,
            .MessageMarker = 0
        };

        if (HAL_FDCAN_AddMessageToTxFifoQ(hfdcan, &TxHeader, nullptr) != HAL_OK) {
            removeReadRequest(id);
            return CAN_READING_ERROR;
        }

        // Wait for response or timeout
        if (xSemaphoreTake(responseSemaphore, pdMS_TO_TICKS(timeoutMs)) == pdTRUE) {
            // Extract data and length from the matching read request
            for (int i = 0; i < CAN_NUMBER_RR; i++) {
                if (readRequests[i].id == id && !readRequests[i].isOpen) {
                    // Copy response data and length
                    memcpy(responseData, readRequests[i].responseData, readRequests[i].responseLength);
                    responseLength = readRequests[i].responseLength;
                    break;
                }
            }
            removeReadRequest(id);
            return CAN_SUCCESS;
        } else {
            removeReadRequest(id);
            return CAN_READING_ERROR;
        }
    }

// Global CANManager instance
CANManager canManager;

// IRQ Callback Integration for FIFO 0 (29-bit IDs)
extern "C" void HAL_FDCAN_RxFifo0Callback(FDCAN_HandleTypeDef* hfdcan, uint32_t RxFifo0ITs) {
    FDCAN_RxHeaderTypeDef rxHeader;
    uint8_t rxData[8];
    if (HAL_FDCAN_GetRxMessage(hfdcan, FDCAN_RX_FIFO0, &rxHeader, rxData) == HAL_OK) {
        canManager.onMessageReceived(rxHeader, rxData);
    }
}

// IRQ Callback Integration for FIFO 1 (11-bit IDs)
extern "C" void HAL_FDCAN_RxFifo1Callback(FDCAN_HandleTypeDef* hfdcan, uint32_t RxFifo1ITs) {
    FDCAN_RxHeaderTypeDef rxHeader;
    uint8_t rxData[8];
    if (HAL_FDCAN_GetRxMessage(hfdcan, FDCAN_RX_FIFO1, &rxHeader, rxData) == HAL_OK) {
        canManager.onMessageReceived(rxHeader, rxData);
    }
}




#endif /* COMMUNICATION_CAN_CAN_GPT_2_H_ */
