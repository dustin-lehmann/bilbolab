/*
 * bilbo_communication.h
 *
 *  Created on: 12 Mar 2023
 *      Author: Dustin Lehmann
 *
 *  Description:
 *      Header file for the BILBO Communication Manager.
 *      This file defines error flags, callback types, configuration structures,
 *      and the BILBO_CommunicationManager class interface for managing UART, SPI, and CAN communications.
 */

#ifndef COMMUNICATION_BILBO_COMMUNICATION_H_
#define COMMUNICATION_BILBO_COMMUNICATION_H_

#include <bilbo_message.h>
#include <bilbo_messages.h>
#include <cstdarg> // For va_list, va_start, va_end

// Include core libraries and hardware-specific communication headers.
#include "core.h"
#include "bilbo_uart_communication.h"
#include "bilbo_spi_communication.h"
#include "firmware_defs.h"
#include "bilbo_control.h"
#include "bilbo_sequencer.h"

// Define error flag macros for communication error responses.
#define BILBO_COMM_ERROR_FLAG_UNKNOWN         0x01  ///< Unknown error flag.
#define BILBO_COMM_ERROR_FLAG_WRONG_ADDRESS   0x02  ///< Error flag for accessing a non-existent register.
#define BILBO_COMM_ERROR_FLAG_WRITE           0x03  ///< Error flag for write operation errors.
#define BILBO_COMM_ERROR_FLAG_READ            0x04  ///< Error flag for read operation errors.
#define BILBO_COMM_ERROR_FLAG_LEN             0x05  ///< Error flag for length mismatches.
#define BILBO_COMM_ERROR_FLAG_MSG_TYPE        0x06  ///< Error flag for message type mismatches.

// Declare the global register map with 255 entries for communication registers.
extern core_utils_RegisterMap<256> register_map;




/**
 * @brief Structure for communication callbacks.
 *
 * This structure holds callback containers for various communication events.
 */
typedef struct bilbo_communication_callbacks_t {
    core_utils_CallbackContainer<5, uint16_t> trajectory_received; ///< Callback container for new trajectory events.
    core_utils_CallbackContainer<5, uint16_t> path_received;       ///< Callback container for path data received via SPI.
} bilbo_communication_callbacks_t;

// Global logging functions for debugging and informational messages.
void send_debug(const char *format, ...);
void send_info(const char *format, ...);
void send_warning(const char *format, ...);
void send_error(const char *format, ...);


void sendMessage(BILBO_Message_t &message);


/**
 * @brief Configuration structure for BILBO Communication Manager.
 *
 * This structure defines the hardware interfaces and buffers used for communication.
 */
typedef struct bilbo_communication_config_t {
    UART_HandleTypeDef *huart;              ///< Pointer to the UART hardware handle.
    SPI_HandleTypeDef *hspi;                ///< Pointer to the SPI hardware handle.
    core_utils_GPIO sample_notification_gpio; ///< GPIO used for sample notifications.
    bilbo_sequence_input_t *sequence_rx_buffer; ///< Buffer for receiving sequence inputs over SPI.
    uint16_t len_sequence_buffer;           ///< Length of the sequence buffer.
    uint8_t *path_rx_buffer;                ///< Buffer for receiving path points over SPI.
    uint16_t len_path_buffer;               ///< Max number of path points the buffer can hold.
    uint16_t reset_uart_exti;               ///< External interrupt line used for UART reset.
    UART_HandleTypeDef *modbus_huart;
    GPIO_TypeDef* modbus_gpio_port;
    uint16_t modbus_gpio_pin;
} bilbo_communication_config_t;


/**
 * @brief BILBO Communication Manager class.
 *
 * This class manages communication over UART, SPI, and CAN buses.
 * It handles initialization, message processing, DMA transfers, and logging.
 */
class BILBO_CommunicationManager {
public:
    /**
     * @brief Constructor for BILBO_CommunicationManager.
     */
    BILBO_CommunicationManager();

    /**
     * @brief Initialize communication interfaces and callbacks.
     *
     * Sets up the UART, SPI, and CAN interfaces along with their callbacks.
     *
     * @param config Configuration structure with hardware interface parameters.
     */
    void init(bilbo_communication_config_t config);

    /**
     * @brief Start all communication interfaces.
     *
     * Starts the UART, SPI, and CAN communications.
     */
    void start();

    /**
     * @brief Provide sample data for SPI transmission via DMA.
     *
     * Initiates a DMA transfer from the given sample data buffer to the SPI interface.
     *
     * @param buffer Pointer to the sample data buffer.
     */
    void provideSampleData(bilbo_logging_sample_t *buffer);


    void resetSPI();

    /**
     * @brief Receive trajectory inputs over SPI.
     *
     * Validates and receives trajectory data into the designated sequence buffer.
     *
     * @param steps The number of trajectory steps to receive.
     */
//    void receiveTrajectoryInputs(uint16_t steps);

    /**
     * @brief Reset the UART interface.
     *
     * Resets the UART communication, typically triggered by an external event.
     */
    void resetUART();

    /**
     * @brief Send a message over UART.
     *
     * Encodes a BILBO message and sends it using the UART interface.
     *
     * @param message The BILBO message to be sent.
     */
    void sendMessage(BILBO_Message_t &message);

    /**
     * @brief Formatted printing function.
     *
     * Sends a formatted message with the specified flag.
     *
     * @param flag Message flag (e.g., debug, info, warning, error).
     * @param format Format string.
     * @param ... Additional arguments.
     */
    void printf(uint8_t flag, const char* format, ...);

    /**
     * @brief Helper function for formatted printing.
     *
     * Processes the variable argument list and sends the formatted message.
     *
     * @param flag Message flag.
     * @param format Format string.
     * @param args Variable argument list.
     */
    void vprint(uint8_t flag, const char *format, va_list args);

    /**
     * @brief Debug logging function.
     *
     * Sends a debug message (flag = 0).
     *
     * @param format Format string.
     * @param ... Additional arguments.
     */
    void send_debug(const char *format, ...);

    /**
     * @brief Informational logging function.
     *
     * Sends an informational message (flag = 1).
     *
     * @param format Format string.
     * @param ... Additional arguments.
     */
    void send_info(const char *format, ...);

    /**
     * @brief Warning logging function.
     *
     * Sends a warning message (flag = 2).
     *
     * @param format Format string.
     * @param ... Additional arguments.
     */
    void send_warning(const char *format, ...);

    /**
     * @brief Error logging function.
     *
     * Sends an error message (flag = 3).
     *
     * @param format Format string.
     * @param ... Additional arguments.
     */
    void send_error(const char *format, ...);

    /**
     * @brief Communication callbacks structure.
     *
     * Contains callback functions for various communication events.
     */
    bilbo_communication_callbacks_t callbacks;

    /**
     * @brief Reset ring buffer state (call before SPI reset).
     */
    void resetSampleRing();

    // Public member variables for configuration and interfaces.
    bilbo_communication_config_t config; ///< Communication configuration parameters.
    BILBO_UART_Communication uart_interface; ///< UART communication interface.
    BILBO_SPI_Communication spi_interface;   ///< SPI communication interface.
    CAN can;                                 ///< CAN bus communication interface.
    ModbusMaster modbus;

private:
    // Private callback handlers for UART messages.
    void _uart_handleMsg_write_callback(core_comm_SerialMessage *msg);
    void _uart_handleMsg_read_callback(core_comm_SerialMessage *msg);
    void _uart_handleMsg_func_callback(core_comm_SerialMessage *msg);

    // Private callback handlers for SPI messages.
    void _spi_rxTrajectory_callback(uint16_t len);
    void _spi_rxPath_callback(uint16_t len);
    void _spi_txSamples_callback();
    void _spi_sampleCommand_callback();
    void _prepareSampleResponse();

    /**
     * @brief Helper function to send an error response over UART.
     *
     * Constructs and sends an error response message based on the incoming message and error code.
     *
     * @param incoming_message Pointer to the original message that caused the error.
     * @param error_code Error code to include in the response.
     */
    void _uartResponseError(core_comm_SerialMessage *incoming_message, uint8_t error_code);

    // Private buffers for sample data and debug messages.

    BILBO_Debug_Message _debug_message; ///< Debug message object for logging.
};

#endif /* COMMUNICATION_BILBO_COMMUNICATION_H_ */
