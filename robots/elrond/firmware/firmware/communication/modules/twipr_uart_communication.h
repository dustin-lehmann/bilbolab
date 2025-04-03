/*
 * twipr_communication.h
 *
 *  Created on: Feb 22, 2023
 *      Author: lehmann_workstation
 *
 *  Description:
 *      Header file for the TWIPR UART Communication interface.
 *      This file defines configuration structures, constants, callback types,
 *      and the TWIPR_UART_Communication class for managing UART-based communication.
 */

#ifndef COMMUNICATION_TWIPR_UART_COMMUNICATION_H_
#define COMMUNICATION_TWIPR_UART_COMMUNICATION_H_

#include "core.h"

// Define the UART communication queue and buffer sizes.
#define TWIPR_UART_COMM_QUEUE_SIZE 10
#define TWIPR_UART_COMM_BUF_SIZE 128

// Define message command codes.
#define MSG_COMMAND_WRITE   0x01 ///< Command code for write operation.
#define MSG_COMMAND_READ    0x02 ///< Command code for read operation.
#define MSG_COMMAND_ANSWER  0x03 ///< Command code for answer response.
#define MSG_COMMAND_STREAM  0x04 ///< Command code for streaming data.
#define MSG_COMMAND_EVENT   0x05 ///< Command code for events.
#define MSG_COMMAND_MSG     0x06 ///< Command code for general messages.
#define MSG_COMMAND_FCT     0x07 ///< Command code for function execution.
#define MSG_COMMAND_ECHO    0x08 ///< Command code for echo testing.


typedef enum serial_message_type_t {
	MSG_WRITE = MSG_COMMAND_WRITE,
	MSG_READ = MSG_COMMAND_READ,
	MSG_ANSWER = MSG_COMMAND_ANSWER,
	MSG_STREAM = MSG_COMMAND_STREAM,
	MSG_EVENT = MSG_COMMAND_EVENT,
	MSG_FCT = MSG_COMMAND_FCT,
	MSG_ECHO = MSG_COMMAND_ECHO
} serial_message_type_t;

//------------------------------------------------------------------------------
// UART Communication Configuration
//------------------------------------------------------------------------------
/**
 * @brief UART Communication configuration structure.
 *
 * Contains the pointer to the UART hardware handle used for communication.
 */
typedef struct twipr_uart_comm_config_t {
    UART_HandleTypeDef *huart; ///< Pointer to the UART hardware handle.
} twipr_uart_comm_config_t;

//------------------------------------------------------------------------------
// UART Communication Callback Types
//------------------------------------------------------------------------------
/**
 * @brief UART Communication callback identifiers.
 *
 * Enumerates the different callback events available in UART communication.
 */
typedef enum twipr_uart_comm_callback_id_t {
    TWIPR_UART_COMM_CALLBACK_RX_MSG,   ///< Callback for receiving a message.
    TWIPR_UART_COMM_CALLBACK_MSG_WRITE,///< Callback for write message events.
    TWIPR_UART_COMM_CALLBACK_MSG_READ, ///< Callback for read message events.
    TWIPR_UART_COMM_CALLBACK_MSG_FUNC, ///< Callback for function execution message events.
} twipr_uart_comm_callback_id_t;

/**
 * @brief Structure for UART Communication callbacks.
 *
 * Contains callback function objects for various UART communication events.
 */
typedef struct twipr_uart_comm_callbacks_t {
    core_utils_Callback<void, core_comm_SerialMessage*> rx_msg;   ///< Callback for received messages.
    core_utils_Callback<void, core_comm_SerialMessage*> write_msg;///< Callback for write message events.
    core_utils_Callback<void, core_comm_SerialMessage*> read_msg; ///< Callback for read message events.
    core_utils_Callback<void, core_comm_SerialMessage*> func_msg; ///< Callback for function execution events.
} twipr_uart_comm_callbacks_t;

//------------------------------------------------------------------------------
// TWIPR_UART_Communication Class Declaration
//------------------------------------------------------------------------------
/**
 * @brief TWIPR UART Communication class.
 *
 * Manages UART communication including initialization, message sending,
 * reception handling, and callback registration.
 */
class TWIPR_UART_Communication {
public:
    xTaskHandle task;                   ///< Handle for the UART communication task.
    uint32_t last_received_message_tick = 0; ///< Timestamp of the last received message.

    /**
     * @brief Constructor for TWIPR_UART_Communication.
     *
     * Initializes the UART communication interface.
     */
    TWIPR_UART_Communication();

    /**
     * @brief Initialize the UART communication interface.
     *
     * Configures the UART hardware and internal buffers using the given configuration.
     *
     * @param config The UART configuration structure.
     */
    void init(twipr_uart_comm_config_t config);

    /**
     * @brief Start the UART communication task.
     *
     * Initiates the UART communication process.
     */
    void start();

    /**
     * @brief Reset the UART interface.
     *
     * Resets the UART interface hardware.
     */
    void reset();

    /**
     * @brief Send a serial message over UART.
     *
     * Overloaded function to send a message by value.
     *
     * @param msg The serial message to be sent.
     */
    void send(core_comm_SerialMessage msg);

    /**
     * @brief Send a serial message over UART.
     *
     * Overloaded function to send a message by pointer.
     *
     * @param msg Pointer to the serial message to be sent.
     */
    void send(core_comm_SerialMessage *msg);

    /**
     * @brief Construct and send a serial message over UART.
     *
     * Constructs a serial message from the provided parameters and sends it.
     *
     * @param cmd The command code.
     * @param module The module identifier.
     * @param address The address associated with the message.
     * @param flag A flag indicating message status.
     * @param data Pointer to the message data.
     * @param len Length of the message data.
     */
    void send(uint8_t cmd, uint8_t module, uint16_t address, uint8_t flag,
              uint8_t *data, uint8_t len);

    /**
     * @brief Send raw data over UART.
     *
     * Sends a raw buffer of data over the UART interface.
     *
     * @param buffer Pointer to the raw data buffer.
     * @param len Length of the data to send.
     */
    void sendRaw(uint8_t *buffer, uint16_t len);

    /**
     * @brief Register a callback for UART communication events.
     *
     * Registers a callback function for the specified UART event.
     *
     * @param callback_id Identifier of the callback event.
     * @param callback The callback function to register.
     */
    void registerCallback(twipr_uart_comm_callback_id_t callback_id,
                          core_utils_Callback<void, core_comm_SerialMessage*> callback);

    /**
     * @brief Main task function for UART communication.
     *
     * This function runs as a separate task to handle incoming messages and manage UART communication.
     */
    void taskFunction();

private:
    osThreadId_t _thread; ///< Handle to the internal UART task thread.

    /**
     * @brief UART receive callback.
     *
     * Called when data is received over UART.
     */
    void _rx_callback();

    /**
     * @brief Handle incoming UART messages.
     *
     * Processes received messages from the UART interface.
     */
    void _handleIncomingMessages();

    /**
     * @brief Handle a read message event.
     *
     * Processes an incoming read message.
     *
     * @param msg Pointer to the received serial message.
     */
    void _handleMessage_read(core_comm_SerialMessage *msg);

    /**
     * @brief Handle a write message event.
     *
     * Processes an incoming write message.
     *
     * @param msg Pointer to the received serial message.
     */
    void _handleMessage_write(core_comm_SerialMessage *msg);

    /**
     * @brief Handle a function execution message event.
     *
     * Processes an incoming function execution message.
     *
     * @param msg Pointer to the received serial message.
     */
    void _handleMessage_function(core_comm_SerialMessage *msg);

    /**
     * @brief Internal UART interface.
     *
     * Manages the UART communication queue and buffer.
     */
    core_comm_UartInterface<TWIPR_UART_COMM_QUEUE_SIZE, TWIPR_UART_COMM_BUF_SIZE> _uart_cm4;

    RegisterMap *register_map; ///< Pointer to the global register map.

    /**
     * @brief Structure to hold registered UART callbacks.
     */
    twipr_uart_comm_callbacks_t _callbacks;
};

#endif /* COMMUNICATION_TWIPR_UART_COMMUNICATION_H_ */
