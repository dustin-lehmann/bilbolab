/*
 * twipr_communication.cpp
 *
 *  Created on: 12 Mar 2023
 *      Author: Dustin Lehmann
 *
 *  Description:
 *      Implementation of the TWIPR communication manager. This module handles UART, SPI,
 *      and CAN bus communications. It manages message handling, DMA callbacks, and error
 *      reporting through various interfaces and callbacks.
 */

#include "twipr_communication.h"
#include <cstdio>   // For sprintf and vsnprintf
#include <cstring>  // For strlen

/**
 * Global register map instance with 255 entries initialized with the general register map.
 */
core_utils_RegisterMap<256> register_map = core_utils_RegisterMap<256>(TWIPR_REGISTER_MAP_GENERAL);

/**
 * Static buffer for outgoing serial messages used for communication responses.
 */
static core_comm_SerialMessage outgoing_msg;

/**
 * Forward declaration of the DMA transfer complete callback function.
 *
 * @param hdma Pointer to the DMA handle structure.
 */
void sample_dma_transfer_cmplt_callback(DMA_HandleTypeDef *hdma);

/**
 * Global pointer to the active communication manager instance.
 */
TWIPR_CommunicationManager *active_manager = NULL;

/**
 * @brief Default constructor for TWIPR_CommunicationManager.
 *
 * Currently no additional initialization is performed in the constructor.
 */
TWIPR_CommunicationManager::TWIPR_CommunicationManager() {
}

/**
 * @brief Initialize the communication manager with the given configuration.
 *
 * This function initializes the UART, SPI, and CAN interfaces along with their respective
 * callbacks. It also sets up the external interrupt for UART reset and registers the DMA callback.
 *
 * @param config The configuration structure containing hardware interface parameters.
 */
void TWIPR_CommunicationManager::init(twipr_communication_config_t config) {
    // Store the configuration locally.
    this->config = config;

    // Set the global active manager pointer.
    active_manager = this;

    // ---------------------------
    // Initialize the UART Interface
    // ---------------------------
    twipr_uart_comm_config_t uart_config = { .huart = this->config.huart };
    this->uart_interface.init(uart_config);

    // Register callback for UART message write events.
    this->uart_interface.registerCallback(
        TWIPR_UART_COMM_CALLBACK_MSG_WRITE,
        core_utils_Callback<void, core_comm_SerialMessage*>(this,
            &TWIPR_CommunicationManager::_uart_handleMsg_write_callback));

    // Register callback for UART message read events.
    this->uart_interface.registerCallback(
        TWIPR_UART_COMM_CALLBACK_MSG_READ,
        core_utils_Callback<void, core_comm_SerialMessage*>(this,
            &TWIPR_CommunicationManager::_uart_handleMsg_read_callback));

    // Register callback for UART function message events.
    this->uart_interface.registerCallback(
        TWIPR_UART_COMM_CALLBACK_MSG_FUNC,
        core_utils_Callback<void, core_comm_SerialMessage*>(this,
            &TWIPR_CommunicationManager::_uart_handleMsg_func_callback));

    // Register external interrupt callback for UART reset.
    core_utils_gpio_registerExtiCallback(
        this->config.reset_uart_exti,
        core_utils_Callback<void, void>(this, &TWIPR_CommunicationManager::resetUART));

    // ---------------------------
    // Initialize the SPI Interface
    // ---------------------------
    twipr_spi_comm_config_t spi_config = {
        .hspi = this->config.hspi,
        .sample_buffer = this->_sample_buffer_tx,
        .len_sample_buffer = TWIPR_FIRMWARE_SAMPLE_BUFFER_SIZE,
        .sequence_buffer = this->config.sequence_rx_buffer,
        .len_sequence_buffer = this->config.len_sequence_buffer
    };
    this->spi_interface.init(spi_config);

    // Register callback for receiving a new trajectory via SPI.


    this->spi_interface.callbacks.trajectory_received.registerFunction(this,
    		&TWIPR_CommunicationManager::_spi_rxTrajectory_callback);


    this->spi_interface.callbacks.samples_transmitted.registerFunction(this,
    		&TWIPR_CommunicationManager::_spi_txSamples_callback);



    // Register the DMA transfer complete callback for sample data transfers.
    HAL_DMA_RegisterCallback(
        TWIPR_FIRMWARE_SAMPLE_DMA_STREAM,
        HAL_DMA_XFER_CPLT_CB_ID,
        sample_dma_transfer_cmplt_callback);

    // ---------------------------
    // Initialize the CAN Bus Interface
    // ---------------------------
    can_config_t can_config = { .hfdcan = BOARD_FDCAN, };
    this->can.init(can_config);



    // Initialize the MODBUS Interface
    modbus_config_t modbus_config = {
    		.huart = this->config.modbus_huart,
			.EN_GPIOx = this->config.modbus_gpio_port,
			.EN_GPIO_Pin = this->config.modbus_gpio_pin,
			.hardware = MB_UART_DMA
    };

    this->modbus.init(modbus_config);
}

/**
 * @brief Start all communication interfaces.
 *
 * This function starts the UART, SPI, and CAN interfaces.
 */
void TWIPR_CommunicationManager::start() {
    // Start UART communication.
    this->uart_interface.start();

    // Start SPI communication.
    this->spi_interface.start();

    // Start CAN bus communication.
    this->can.start();

    // Start the Modbus
	#ifdef BILBO_DRIVE_SIMPLEXMOTION_RS485
    	this->modbus.start();
	#endif
}

/**
 * @brief Reset the UART interface.
 *
 * This function resets the UART interface, typically invoked by an external interrupt.
 */
void TWIPR_CommunicationManager::resetUART() {
    this->uart_interface.reset();
}


void TWIPR_CommunicationManager::resetSPI() {
	this->spi_interface.reset();
}

/**
 * @brief Callback to handle UART write messages.
 *
 * This function validates the incoming message for a write operation, writes the data to the
 * register map, and prepares an acknowledgment message.
 *
 * @param msg Pointer to the incoming serial message.
 */
void TWIPR_CommunicationManager::_uart_handleMsg_write_callback(core_comm_SerialMessage *msg) {
    // Convert the message addresses to a 16-bit address.
    uint16_t address = uint8_to_uint16(msg->address_2, msg->address_3);

    // Check if the address exists in the register map.
    if (!register_map.hasEntry(address)) {
        this->_uartResponseError(msg, TWIPR_COMM_ERROR_FLAG_WRONG_ADDRESS);
        return;
    }

    // Verify that the register entry is writable.
    if (register_map.getType(address) != REGISTER_ENTRY_TYPE_WRITABLE &&
        register_map.getType(address) != REGISTER_ENTRY_TYPE_READWRITEABLE) {
        this->_uartResponseError(msg, TWIPR_COMM_ERROR_FLAG_MSG_TYPE);
        return;
    }

    // Check if the input length matches the register map entry's expected size.
    if (register_map.getInputSize(address) != msg->len) {
        // Error response for length mismatch is commented out.
        // this->_uartResponseError(msg, TWIPR_COMM_ERROR_FLAG_LEN);
        return;
    }

    // Write the received data into the register map.
    register_map.write(address, msg->data_ptr);

    // Prepare the outgoing message (Note: all address fields are assigned to address_1,
    // which may be unintended; verify if this is correct).
    outgoing_msg.address_1 = msg->address_1;
    outgoing_msg.address_1 = msg->address_2;
    outgoing_msg.address_1 = msg->address_3;
    outgoing_msg.cmd = MSG_COMMAND_ANSWER;
    outgoing_msg.flag = 1;
    outgoing_msg.len = 0;

    // Send the response (currently commented out).
    // this->uart_interface.send(&outgoing_msg);
}

/**
 * @brief Callback to handle UART read messages.
 *
 * This function validates the incoming read request, retrieves data from the register map, and
 * sends the data back to the requester.
 *
 * @param msg Pointer to the incoming serial message.
 */
void TWIPR_CommunicationManager::_uart_handleMsg_read_callback(core_comm_SerialMessage *msg) {
    // Convert the message addresses to a 16-bit address.
    uint16_t address = uint8_to_uint16(msg->address_2, msg->address_3);

    // Check if the address exists in the register map.
    if (!register_map.hasEntry(address)) {
        this->_uartResponseError(msg, TWIPR_COMM_ERROR_FLAG_WRONG_ADDRESS);
        return;
    }

    // Verify that the register entry is readable.
    if (register_map.getType(address) != REGISTER_ENTRY_TYPE_READABLE &&
        register_map.getType(address) != REGISTER_ENTRY_TYPE_READWRITEABLE) {
        this->_uartResponseError(msg, TWIPR_COMM_ERROR_FLAG_MSG_TYPE);
        return;
    }

    // Read data from the register map into the outgoing message buffer.
    uint16_t len = register_map.read(address, outgoing_msg.data_ptr);

    if (len > 0) {
        // Construct the outgoing response message.
        outgoing_msg.address_1 = msg->address_1;
        outgoing_msg.address_2 = msg->address_2;
        outgoing_msg.address_3 = msg->address_3;
        outgoing_msg.flag = 1;
        outgoing_msg.cmd = MSG_COMMAND_ANSWER;
        outgoing_msg.len = len;

        // Send the response message via UART.
        this->uart_interface.send(&outgoing_msg);
    }
}

/**
 * @brief Callback to handle UART function execution messages.
 *
 * This function validates the message for a function execution, calls the corresponding function
 * from the register map, and sends any returned data back to the requester.
 *
 * @param msg Pointer to the incoming serial message.
 */
void TWIPR_CommunicationManager::_uart_handleMsg_func_callback(core_comm_SerialMessage *msg) {
    // Convert the message addresses to a 16-bit address.
    uint16_t address = uint8_to_uint16(msg->address_2, msg->address_3);

    // Check if the address exists in the register map.
    if (!register_map.hasEntry(address)) {
        this->_uartResponseError(msg, TWIPR_COMM_ERROR_FLAG_WRONG_ADDRESS);
        return;
    }

    // Verify the input length for the function.
    if (register_map.getInputSize(address) != msg->len) {
        this->_uartResponseError(msg, TWIPR_COMM_ERROR_FLAG_LEN);
        return;
    }

    // Verify that the register entry is executable.
    if (register_map.getType(address) != REGISTER_ENTRY_TYPE_EXECUTABLE) {
        this->_uartResponseError(msg, TWIPR_COMM_ERROR_FLAG_MSG_TYPE);
        return;
    }

    // Execute the function and store the return data in the outgoing message.
    uint8_t ret_size = register_map.execute(address, msg->data_ptr, outgoing_msg.data_ptr);

    // If the function returns data, construct and send a response message.
    if (ret_size > 0) {
        outgoing_msg.address_1 = msg->address_1;
        outgoing_msg.address_2 = msg->address_2;
        outgoing_msg.address_3 = msg->address_3;
        outgoing_msg.flag = 1;
        outgoing_msg.cmd = MSG_COMMAND_ANSWER;
        outgoing_msg.len = ret_size;
        this->uart_interface.send(&outgoing_msg);
    }
}

/**
 * @brief Send an error response message over UART.
 *
 * This helper function constructs an error response message based on the incoming message and
 * provided error code, then sends it via the UART interface.
 *
 * @param incoming_message Pointer to the incoming message that caused the error.
 * @param error_code The error code to include in the response.
 */
void TWIPR_CommunicationManager::_uartResponseError(core_comm_SerialMessage *incoming_message, uint8_t error_code) {
    outgoing_msg.address_1 = incoming_message->address_1;
    outgoing_msg.address_2 = incoming_message->address_2;
    outgoing_msg.address_3 = incoming_message->address_3;
    outgoing_msg.cmd = MSG_COMMAND_ANSWER;
    outgoing_msg.flag = 0;
    outgoing_msg.len = 1;
    outgoing_msg.data_ptr[0] = error_code;
    this->uart_interface.send(&outgoing_msg);
}

/**
 * @brief SPI callback for receiving a new trajectory.
 *
 * This function is invoked when a new trajectory is received via SPI. It calls the new trajectory
 * callback and then provides sample data to the SPI interface.
 *
 * @param len The length of the received trajectory data.
 */
void TWIPR_CommunicationManager::_spi_rxTrajectory_callback(uint16_t len) {
    // Notify about the new trajectory.
    this->callbacks.trajectory_received.call(len);
}

/**
 * @brief Callback invoked when DMA completes transferring sample data.
 *
 * This function stops the current SPI transmission, provides sample data to the SPI interface,
 * and toggles the sample notification GPIO to signal successful transfer.
 */
void TWIPR_CommunicationManager::sampleBufferDMATransfer_callback() {
    // Toggle the GPIO to notify that sample data has been transferred.
    this->config.sample_notification_gpio.toggle();

    if (this->_sample_buffer_tx[0].general.tick > 0){
        rc_status_led_2.toggle();
    }
}

/**
 * @brief SPI callback for transmitting sample data.
 *
 * Currently, this function does not implement any specific behavior.
 *
 * @param len The length of the sample data to be transmitted.
 */
void TWIPR_CommunicationManager::_spi_txSamples_callback() {
    // No implementation for transmitting samples is provided here.
}


//void TWIPR_CommunicationManager::receiveTrajectoryInputs(uint16_t steps) {
//    // Check if the number of steps exceeds the allocated sequence buffer size.
//    if (steps > this->config.len_sequence_buffer) {
//        send_error("Comm: Sequence too long (%d > %d)", steps, this->config.len_sequence_buffer);
//        return;
//    }
//    // Stop current SPI transmission before receiving new trajectory inputs.
//    this->spi_interface.stopTransmission();
//    // Begin receiving trajectory inputs via SPI.
//    this->spi_interface.receiveTrajectoryInputs(steps);
//}


/**
 * @brief Provide sample data to the SPI interface via DMA.
 *
 * This function starts a DMA transfer to move sample data from the provided buffer into the
 * transmission buffer used by the SPI interface.
 *
 * @param buffer Pointer to the sample data buffer.
 */
void TWIPR_CommunicationManager::provideSampleData(twipr_logging_sample_t *buffer) {
    HAL_DMA_Start_IT(
        TWIPR_FIRMWARE_SAMPLE_DMA_STREAM,
        (uint32_t) buffer,
        (uint32_t) &this->_sample_buffer_tx,
        TWIPR_FIRMWARE_SAMPLE_BUFFER_SIZE * sizeof(twipr_logging_sample_t)
    );

}

/**
 * @brief Global DMA transfer complete callback.
 *
 * This function is called by the DMA driver when a sample data transfer completes.
 * It delegates the handling to the active communication manager instance.
 *
 * @param hdma Pointer to the DMA handle structure.
 */
void sample_dma_transfer_cmplt_callback(DMA_HandleTypeDef *hdma) {
    active_manager->sampleBufferDMATransfer_callback();
}

/**
 * @brief Send a BILBO message over UART.
 *
 * This function encodes a BILBO_Message_t into a core_comm_SerialMessage and sends it via the UART interface.
 *
 * @param message The BILBO message to be sent.
 */
void TWIPR_CommunicationManager::sendMessage(BILBO_Message_t &message) {
    core_comm_SerialMessage serial_msg = message.encode();
    // Send the encoded message using the UART interface.
    this->uart_interface.send(&serial_msg);
}

/**
 * @brief Variadic print function for formatted messaging.
 *
 * This function formats the message and forwards it to the helper function vprint to avoid code duplication.
 *
 * @param flag A flag indicating the message type (e.g., debug, info, warning, error).
 * @param format Format string for the message.
 * @param ... Additional arguments for the format string.
 */
void TWIPR_CommunicationManager::printf(uint8_t flag, const char *format, ...) {
    va_list args;
    va_start(args, format);
    // Forward to the internal helper function for formatted printing.
    vprint(flag, format, args);
    va_end(args);
}

/**
 * @brief Internal helper for formatted printing.
 *
 * This function takes a va_list, formats the message into a debug message buffer, and sends it
 * if the formatted string is within acceptable length.
 *
 * @param flag A flag indicating the message type.
 * @param format Format string.
 * @param args Variable argument list.
 */
void TWIPR_CommunicationManager::vprint(uint8_t flag, const char *format, va_list args) {
    int length = vsnprintf(this->_debug_message.data->message, DEBUG_PRINT_BUFFER_SIZE, format, args);
    this->_debug_message.data->flag = flag;
    // Send the message if it was successfully formatted and fits within the buffer.
    if (length > 0 && length < DEBUG_PRINT_BUFFER_SIZE) {
        this->sendMessage(this->_debug_message);
    }
}

/**
 * @brief Send a debug message (flag = 0).
 *
 * @param format Format string for the debug message.
 * @param ... Additional arguments for the format string.
 */
void TWIPR_CommunicationManager::send_debug(const char *format, ...) {
    va_list args;
    va_start(args, format);
    vprint(0, format, args);
    va_end(args);
}

/**
 * @brief Send an informational message (flag = 1).
 *
 * @param format Format string for the info message.
 * @param ... Additional arguments for the format string.
 */
void TWIPR_CommunicationManager::send_info(const char *format, ...) {
    va_list args;
    va_start(args, format);
    vprint(1, format, args);
    va_end(args);
}

/**
 * @brief Send a warning message (flag = 2).
 *
 * @param format Format string for the warning message.
 * @param ... Additional arguments for the format string.
 */
void TWIPR_CommunicationManager::send_warning(const char *format, ...) {
    va_list args;
    va_start(args, format);
    vprint(2, format, args);
    va_end(args);
}

/**
 * @brief Send an error message (flag = 3).
 *
 * @param format Format string for the error message.
 * @param ... Additional arguments for the format string.
 */
void TWIPR_CommunicationManager::send_error(const char *format, ...) {
    va_list args;
    va_start(args, format);
    vprint(3, format, args);
    va_end(args);
}

/**
 * @brief Global debug function.
 *
 * This function sends a debug message using the active communication manager instance if available.
 *
 * @param format Format string for the debug message.
 * @param ... Additional arguments for the format string.
 */
void send_debug(const char *format, ...) {
    if (active_manager) {
        va_list args;
        va_start(args, format);
        active_manager->vprint(0, format, args);
        va_end(args);
    }
}

/**
 * @brief Global info function.
 *
 * This function sends an informational message using the active communication manager instance if available.
 *
 * @param format Format string for the info message.
 * @param ... Additional arguments for the format string.
 */
void send_info(const char *format, ...) {
    if (active_manager) {
        va_list args;
        va_start(args, format);
        active_manager->vprint(1, format, args);
        va_end(args);
    }
}

/**
 * @brief Global warning function.
 *
 * This function sends a warning message using the active communication manager instance if available.
 *
 * @param format Format string for the warning message.
 * @param ... Additional arguments for the format string.
 */
void send_warning(const char *format, ...) {
    if (active_manager) {
        va_list args;
        va_start(args, format);
        active_manager->vprint(2, format, args);
        va_end(args);
    }
}

/**
 * @brief Global error function.
 *
 * This function sends an error message using the active communication manager instance if available.
 *
 * @param format Format string for the error message.
 * @param ... Additional arguments for the format string.
 */
void send_error(const char *format, ...) {
    if (active_manager) {
        va_list args;
        va_start(args, format);
        active_manager->vprint(3, format, args);
        va_end(args);
    }
}



void sendMessage(BILBO_Message_t &message) {
	if (active_manager != NULL){
		active_manager->sendMessage(message);
	}
}
