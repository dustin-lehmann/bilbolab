/*
 * twipr_communication.cpp
 *
 * Created on: Feb 22, 2023
 * Author: lehmann_workstation
 *
 * This file implements the UART communication functionality for the TWIPR system.
 * It includes initialization, message handling, and task management for UART communication.
 */

#include "firmware_core.h"
#include "twipr_uart_communication.h"
#include "robot-control_std.h"

// Configuration for the UART interface using DMA and COBS encoding.
static core_comm_UartInterface_config_t twipr_communication_uart_cm4_interface_config =
{
    .uart = {
        .mode = CORE_HARDWARE_UART_MODE_DMA,  // Use DMA mode for UART communication.
        .cobs_encode_rx = 1,                  // Enable COBS encoding for RX.
        .cobs_encode_tx = 1,                  // Enable COBS encoding for TX.
        .queues = 1,                         // Enable queues for communication.
    },
    .use_protocol = 1,                        // Enable protocol usage.
    .use_queue = 1                            // Enable queue usage.
};

// Thread attributes for the UART communication task.
static const osThreadAttr_t task_attributes = {
    .name = "twipr_uart_comm_task",           // Task name.
    .stack_size = 512 * 4,                    // Stack size for the task.
    .priority = (osPriority_t) osPriorityNormal  // Task priority.
};

// Preallocated memory for incoming and outgoing serial messages.
static core_comm_SerialMessage_memory<128> incoming_msg;
static core_comm_SerialMessage_memory<128> outgoing_msg;

// Flag to indicate if data is available in the receive queue.
bool rx_available = false;

/**
 * @brief Task function that executes the UART communication routine.
 *
 * This function is meant to be run as an OS thread. It retrieves the current task handle,
 * stores it in the TWIPR_UART_Communication object, and starts processing UART messages.
 *
 * @param argument Pointer to the TWIPR_UART_Communication instance.
 */
void twipr_uart_comm_task(void *argument) {
    TWIPR_UART_Communication *comm = (TWIPR_UART_Communication*) argument;
    comm->task = xTaskGetCurrentTaskHandle();
    comm->taskFunction();
}

/**
 * @brief Default constructor for the TWIPR_UART_Communication class.
 */
TWIPR_UART_Communication::TWIPR_UART_Communication() {
    // No initialization required in constructor.
}

/**
 * @brief Initializes the UART communication interface.
 *
 * Configures the hardware UART interface with the provided settings and registers the RX callback.
 *
 * @param config Configuration settings for UART communication.
 */
void TWIPR_UART_Communication::init(twipr_uart_comm_config_t config) {
    // Initialize the UART interface using the given hardware UART and configuration.
    this->_uart_cm4.init(config.huart, twipr_communication_uart_cm4_interface_config);

    // Register the RX callback to handle incoming data.
    this->_uart_cm4.registerCallback(
        CORE_COMM_SERIAL_SOCKET_CB_RX,
        core_utils_Callback<void, void>(this, &TWIPR_UART_Communication::_rx_callback)
    );
}

/**
 * @brief Starts the UART communication interface and task.
 *
 * This function starts the UART interface and creates a dedicated OS thread to handle ongoing
 * communication tasks.
 */
void TWIPR_UART_Communication::start() {
    // Start the UART interface.
    this->_uart_cm4.start();

    // Create and start the UART communication task.
    this->_thread = osThreadNew(twipr_uart_comm_task, this, &task_attributes);
}

/**
 * @brief Resets the UART communication interface.
 *
 * Resets the underlying UART interface, which can be useful to recover from errors or to
 * reinitialize communication.
 */
void TWIPR_UART_Communication::reset() {
    this->_uart_cm4.reset();
}

/**
 * @brief Prepares and sends a UART message with the provided parameters.
 *
 * Constructs a serial message with the specified command, module, address, flag, and data,
 * then transmits it using the UART interface.
 *
 * @param cmd Command identifier for the message.
 * @param module Module identifier.
 * @param address 16-bit address (split into two parts for transmission).
 * @param flag Additional flag information.
 * @param data Pointer to the data payload.
 * @param len Length of the data payload.
 */
void TWIPR_UART_Communication::send(uint8_t cmd, uint8_t module, uint16_t address, uint8_t flag, uint8_t *data, uint8_t len) {
    // Populate the outgoing message structure with the provided parameters.
	outgoing_msg.tick = tick_global;
    outgoing_msg.cmd = cmd;
    outgoing_msg.address_1 = module;
    outgoing_msg.address_2 = address >> 8;  // High byte of address.
    outgoing_msg.address_3 = address;       // Low byte of address.
    outgoing_msg.flag = flag;

    // Copy the data payload into the message.
    for (int i = 0; i < len; i++) {
        outgoing_msg.data_ptr[i] = data[i];
    }
    outgoing_msg.len = len;

    // Send the constructed message.
    this->send(&outgoing_msg);
}

/**
 * @brief Sends a serial message over the UART interface.
 *
 * Checks the provided message and forwards it to the UART interface for transmission.
 *
 * @param msg Pointer to the serial message to be sent.
 */
void TWIPR_UART_Communication::send(core_comm_SerialMessage *msg) {
	msg->tick = tick_global;
    this->_uart_cm4.send(msg);
}

/**
 * @brief Registers a callback function for a specific UART communication event.
 *
 * Associates a callback function with a particular event (e.g., receiving a message, write, read, or function call).
 *
 * @param callback_id Identifier for the callback event.
 * @param callback Callback function to be registered.
 */
void TWIPR_UART_Communication::registerCallback(twipr_uart_comm_callback_id_t callback_id,
                                                  core_utils_Callback<void, core_comm_SerialMessage*> callback) {
    switch (callback_id) {
        case TWIPR_UART_COMM_CALLBACK_RX_MSG: {
            this->_callbacks.rx_msg = callback;
            break;
        }
        case TWIPR_UART_COMM_CALLBACK_MSG_WRITE: {
            this->_callbacks.write_msg = callback;
            break;
        }
        case TWIPR_UART_COMM_CALLBACK_MSG_READ: {
            this->_callbacks.read_msg = callback;
            break;
        }
        case TWIPR_UART_COMM_CALLBACK_MSG_FUNC: {
            this->_callbacks.func_msg = callback;
            break;
        }
    }
}

/**
 * @brief Main task function for handling UART communication.
 *
 * Continuously monitors for received data and processes incoming messages by delegating to
 * the appropriate callbacks. Includes a short delay to yield control to other tasks.
 */
void TWIPR_UART_Communication::taskFunction() {
    // Main loop for processing incoming messages.
    while (true) {
        if (rx_available) {
            rx_available = false;
            // Check if there is data in the RX queue.
            if (this->_uart_cm4.rx_queue.available()) {
                this->_handleIncomingMessages();
            }
        }
        osDelay(2);  // Delay to allow other tasks to execute.
        // Alternatively, you could use task notifications:
    }
//
//    while (true){
//    	 ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
//    	 if (this->_uart_cm4.rx_queue.available()) {
//    	                this->_handleIncomingMessages();
//			}
//    }
}

/**
 * @brief Processes incoming UART messages.
 *
 * Reads all available messages from the RX queue, checks the command type, and invokes the
 * corresponding registered callback for each message type. Updates the last received tick.
 */
void TWIPR_UART_Communication::_handleIncomingMessages() {
    // Process all messages in the RX queue.
    while (this->_uart_cm4.rx_queue.available()) {
        this->_uart_cm4.rx_queue.read(&incoming_msg);

        // TODO: Validate the message correctness (e.g., checksum, length).

        // Process the message based on its command type.
        switch (incoming_msg.cmd) {
            case MSG_COMMAND_WRITE: {
                if (this->_callbacks.write_msg.registered) {
                    this->_callbacks.write_msg.call(&incoming_msg);
                }
                break;
            }
            case MSG_COMMAND_READ: {
                if (this->_callbacks.read_msg.registered) {
                    this->_callbacks.read_msg.call(&incoming_msg);
                }
                break;
            }
            case MSG_COMMAND_EVENT: {
                // Event command received, no specific action implemented.
                nop();
                break;
            }
            case MSG_COMMAND_MSG: {
                // Message command received, no specific action implemented.
                nop();
                break;
            }
            case MSG_COMMAND_FCT: {
                if (this->_callbacks.func_msg.registered) {
                    this->_callbacks.func_msg.call(&incoming_msg);
                }
                // Optionally, handle function-specific message processing:
                // this->_handleMessage_function(&incoming_msg);
                break;
            }
            case MSG_COMMAND_ECHO: {
                // Echo the received message back.
                this->send(&incoming_msg);
                break;
            }
            default: {
                // Unknown command, skip processing.
                continue;
                break;
            }
        }
        // Update the tick count when the last message was received.
        this->last_received_message_tick = osKernelGetTickCount();
    }
}

/**
 * @brief RX callback function triggered upon receiving UART data.
 *
 * Sets a flag indicating that new data has been received. This flag is checked in the main task
 * function to trigger message processing.
 */
void TWIPR_UART_Communication::_rx_callback() {
    rx_available = true;
//    // Optionally, notify the task directly if a task notification mechanism is used:
//     if (this->task != NULL) {
//         xTaskNotifyGive(this->task);
//     }
}
