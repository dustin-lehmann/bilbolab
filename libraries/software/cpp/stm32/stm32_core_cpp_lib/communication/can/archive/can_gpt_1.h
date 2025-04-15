/*
 * can_gpt_1.h
 *
 *  Created on: Nov 30, 2024
 *      Author: lehmann
 */

#ifndef COMMUNICATION_CAN_CAN_GPT_1_H_
#define COMMUNICATION_CAN_CAN_GPT_1_H_

#include <map>
#include <vector>
#include <functional>
#include <cstring>
#include "FreeRTOS.h"
#include "semphr.h"
#include "main.h"

// Callback type definitions
typedef std::function<void(uint32_t id, const uint8_t* data, uint8_t length)> CANFrameCallback;

class CANManager {
private:
    std::map<uint32_t, SemaphoreHandle_t> rxSemaphores; // Pending requests
    SemaphoreHandle_t mapMutex;                        // Mutex for thread-safe access

    // Callbacks for 11-bit frames
    std::vector<CANFrameCallback> standardIDCallbacks;

    // Callbacks for untracked 29-bit frames
    std::vector<CANFrameCallback> extendedIDCallbacks;

public:
    // Constructor
    CANManager() {
        mapMutex = xSemaphoreCreateMutex(); // Create a mutex for thread safety
    }

    // Destructor
    ~CANManager() {
        // Free all semaphores in the map when the class is destroyed
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        for (auto& pair : rxSemaphores) {
            vSemaphoreDelete(pair.second); // Delete the semaphore
        }
        rxSemaphores.clear(); // Clear the map
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
        status = HAL_FDCAN_ConfigFilter(hfdcan, &filterConfig);
        return status;
    }

    // Register a callback for 11-bit CAN frames
    void registerStandardIDCallback(CANFrameCallback callback) {
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        standardIDCallbacks.push_back(callback);
        xSemaphoreGive(mapMutex);
    }

    // Register a callback for untracked 29-bit CAN frames
    void registerExtendedIDCallback(CANFrameCallback callback) {
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        extendedIDCallbacks.push_back(callback);
        xSemaphoreGive(mapMutex);
    }

    // Add a pending request with a semaphore
    void addPendingRequest(uint32_t id, SemaphoreHandle_t sem) {
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        if (rxSemaphores.find(id) != rxSemaphores.end()) {
            // Free the existing semaphore if overwriting
            vSemaphoreDelete(rxSemaphores[id]);
        }
        rxSemaphores[id] = sem; // Add or update the entry
        xSemaphoreGive(mapMutex);
    }

    // Get a pending request's semaphore
    SemaphoreHandle_t getPendingRequest(uint32_t id) {
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        auto it = rxSemaphores.find(id);
        SemaphoreHandle_t sem = (it != rxSemaphores.end()) ? it->second : nullptr;
        xSemaphoreGive(mapMutex);
        return sem;
    }

    // Remove a pending request and free its semaphore
    void removePendingRequest(uint32_t id) {
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        auto it = rxSemaphores.find(id);
        if (it != rxSemaphores.end()) {
            vSemaphoreDelete(it->second); // Free the semaphore
            rxSemaphores.erase(it);       // Remove the entry from the map
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
    HAL_StatusTypeDef sendRemoteFrame(FDCAN_HandleTypeDef* hfdcan, uint32_t id, uint32_t timeoutMs, uint8_t* responseData, uint8_t& responseLength) {
        // Create a semaphore for this request
        SemaphoreHandle_t responseSemaphore = xSemaphoreCreateBinary();
        addPendingRequest(id, responseSemaphore);

        // Send Remote Frame
        FDCAN_TxHeaderTypeDef TxHeader = {
            .Identifier = id,
            .IdType = FDCAN_EXTENDED_ID,
            .TxFrameType = FDCAN_REMOTE_FRAME,
            .DataLength = FDCAN_DLC_BYTES_8, // 8-byte data length
            .ErrorStateIndicator = FDCAN_ESI_ACTIVE,
            .BitRateSwitch = FDCAN_BRS_OFF,
            .FDFormat = FDCAN_CLASSIC_CAN,
            .TxEventFifoControl = FDCAN_NO_TX_EVENTS,
            .MessageMarker = 0
        };

        HAL_StatusTypeDef status = HAL_FDCAN_AddMessageToTxFifoQ(hfdcan, &TxHeader, nullptr);
        if (status != HAL_OK) {
            removePendingRequest(id); // Clean up if transmission fails
            return status;
        }

        // Wait for the response or timeout
        if (xSemaphoreTake(responseSemaphore, pdMS_TO_TICKS(timeoutMs)) == pdTRUE) {
            responseLength = 8; // Example response length
            memcpy(responseData, rxSemaphores[id], responseLength);
            removePendingRequest(id); // Clean up after successful response
            return HAL_OK;
        } else {
            removePendingRequest(id);
            return HAL_TIMEOUT;
        }
    }

    // IRQ Callback to handle received messages
    void onMessageReceived(const FDCAN_RxHeaderTypeDef& header, uint8_t* data) {
        xSemaphoreTake(mapMutex, portMAX_DELAY);
        auto it = rxSemaphores.find(header.Identifier);

        if (it != rxSemaphores.end()) {
            // Signal the waiting semaphore
            xSemaphoreGive(it->second);
        } else {
            // Process 11-bit CAN frames
            if (header.IdType == FDCAN_STANDARD_ID) {
                for (auto& callback : standardIDCallbacks) {
                    callback(header.Identifier, data, header.DataLength >> 16);
                }
            }

            // Process untracked 29-bit CAN frames
            if (header.IdType == FDCAN_EXTENDED_ID) {
                for (auto& callback : extendedIDCallbacks) {
                    callback(header.Identifier, data, header.DataLength >> 16);
                }
            }
        }

        xSemaphoreGive(mapMutex);
    }
};

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




#endif /* COMMUNICATION_CAN_CAN_GPT_1_H_ */
