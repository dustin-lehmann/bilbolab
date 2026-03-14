/*
 * bilbo_spi_communication.cpp
 *
 *  Created on: 12 Mar 2023
 *      Author: Dustin Lehmann
 *
 *  Description:
 *      This file implements the SPI communication interface for BILBO.
 *      It initializes the SPI slave interface, registers callbacks for
 *      RX/TX events, and provides functions for sending sample data and
 *      receiving trajectory inputs.
 */

#include "bilbo_spi_communication.h"


/**
 * @brief Constructor for the BILBO_SPI_Communication class.
 *
 * Currently, no additional initialization is performed in the constructor.
 */
BILBO_SPI_Communication::BILBO_SPI_Communication() {
}

/**
 * @brief Initialize the SPI communication interface.
 *
 * Configures the SPI hardware using the provided configuration structure.
 * It sets up the receive and transmit buffers, and registers callbacks for
 * RX (receive complete) and TX (transmit complete) events.
 *
 * @param config Configuration structure for SPI communication.
 */
void BILBO_SPI_Communication::init(bilbo_spi_comm_config_t config) {
	// Store the provided configuration locally.
	this->config = config;

	// Create a hardware SPI configuration structure and initialize buffers.
	core_hardware_spi_config_t spi_config = { .hspi = this->config.hspi,
			.rx_buffer = (uint8_t*) this->config.sequence_buffer, .tx_buffer =
					this->config.sample_response_buffer, };

	// Initialize the SPI slave with the configuration.
	this->spi_slave.init(spi_config);

	// Register the receive complete callback.
	this->spi_slave.registerCallback(CORE_HARDWARE_SPI_CALLBACK_RX,
			core_utils_Callback<void, void>(this,
					&BILBO_SPI_Communication::rx_cmplt_function));

	// Register the transmit complete callback.
	this->spi_slave.registerCallback(CORE_HARDWARE_SPI_CALLBACK_TX,
			core_utils_Callback<void, void>(this,
					&BILBO_SPI_Communication::tx_cmplt_function));

	// The RXTX callback and command buffer settings are currently commented out.
	// Uncomment and configure if full-duplex command processing is required.
	// this->spi_slave.registerCallback(CORE_HARDWARE_SPI_CALLBACK_RXTX,
	//     core_utils_Callback<void, void>(this, &BILBO_SPI_Communication::rxtx_cmplt_function));
	//
	// uint8_t trajectory_size = sizeof(bilbo_sequence_input_t);
	// uint8_t sample_size = sizeof(bilbo_logging_sample_t);
	// tx_cmd_buf[1] = trajectory_size;
	// tx_cmd_buf[2] = sample_size;
}

/**
 * @brief Start the SPI communication interface.
 *
 * Starts the SPI slave interface and immediately provides sample data
 * for transmission.
 */
void BILBO_SPI_Communication::start() {
	// Start the SPI slave.
	this->spi_slave.start();
	// Provide initial sample data for transmission.
//    this->startListeningForCommand();
//    this->provideSampleData();
}

void BILBO_SPI_Communication::reset() {

	this->spi_slave.reset();

	this->startListeningForCommand();

}

void BILBO_SPI_Communication::startListeningForCommand() {
	this->_commandBuffer[0] = 0;
	this->_commandBuffer[1] = 0;
	this->_commandBuffer[2] = 0;
	this->_commandBuffer[3] = 0;

	this->_trajectory_length = 0;

	this->mode = BILBO_SPI_COMM_MODE_LISTENING_FOR_COMMAND;
	this->spi_slave.receiveData(this->_commandBuffer,
			BILBO_SPI_COMMAND_MESSAGE_LENGTH);
}

/**
 * @brief Provide sample data using the default configuration.
 *
 * This function calls the overloaded provideSampleData function using the
 * default sample buffer and length provided in the configuration.
 */
void BILBO_SPI_Communication::sendSampleResponse(uint8_t *buffer, uint32_t len, uint8_t *dummy_rx) {
	this->spi_slave.provideData(buffer, len, dummy_rx);
}

/**
 * @brief Receive trajectory inputs over SPI.
 *
 * Initiates the reception of trajectory input data into the configured sequence buffer.
 *
 * @param steps Number of trajectory steps (samples) to receive.
 */
void BILBO_SPI_Communication::receiveTrajectoryInputs(uint16_t steps) {
	// Calculate the total size of the data to receive.
	send_info("Waiting for trajectory with %d steps", steps);
	this->_trajectory_length = steps;
	this->spi_slave.receiveData((uint8_t*) this->config.sequence_buffer,
			sizeof(bilbo_sequence_input_t) * steps);
}

void BILBO_SPI_Communication::receivePathPoints(uint16_t count) {
	send_info("Waiting for path with %d points", count);
	this->_path_length = count;
	// Each path point is 2 floats (x, y) = 8 bytes
	this->spi_slave.receiveData(this->config.path_rx_buffer, 8 * count);
}

/**
 * @brief SPI receive complete callback.
 *
 * This function is called when the SPI slave has completed receiving data.
 * If a trajectory reception callback is registered, it is invoked with the length
 * of the sequence buffer.
 */
void BILBO_SPI_Communication::rx_cmplt_function() {

	if (this->mode == BILBO_SPI_COMM_MODE_LISTENING_FOR_COMMAND) {
		this->_handleCommand();

	} else if (this->mode == BILBO_SPI_COMM_MODE_RX_TRAJECTORY) {
		this->mode = BILBO_SPI_COMM_MODE_LISTENING_FOR_COMMAND;
		this->startListeningForCommand();
		this->callbacks.trajectory_received.call(this->_trajectory_length);
	} else if (this->mode == BILBO_SPI_COMM_MODE_RX_PATH) {
		this->mode = BILBO_SPI_COMM_MODE_LISTENING_FOR_COMMAND;
		this->startListeningForCommand();
		this->callbacks.path_received.call(this->_path_length);
	}
}

/**
 * @brief SPI transmit complete callback.
 *
 * This function is called when the SPI slave has finished transmitting data.
 * It invokes the sample transmission callback if registered, passing the length
 * of the transmitted data, and then immediately provides sample data for further transmission.
 */
void BILBO_SPI_Communication::tx_cmplt_function() {
	// Execute the TX callback if one is registered.

	if (this->mode == BILBO_SPI_COMM_MODE_TX_SAMPLES) {
		this->mode = BILBO_SPI_COMM_MODE_LISTENING_FOR_COMMAND;
		this->startListeningForCommand();
		this->callbacks.samples_transmitted.call();
	}
}

void BILBO_SPI_Communication::_handleCommand() {

	if (this->_commandBuffer[0] != 0x66) {
		send_error("SPI Command Header wrong: %d, %d, %d, %d",
				this->_commandBuffer[0], this->_commandBuffer[1],
				this->_commandBuffer[2], this->_commandBuffer[3]);
		this->startListeningForCommand();
		return;
	}

	uint8_t command = this->_commandBuffer[1];
	uint16_t length = bytearray_to_uint16(&this->_commandBuffer[2]);

	if (command == BILBO_SPI_COMMAND_SAMPLES_READ) {
		this->mode = BILBO_SPI_COMM_MODE_TX_SAMPLES;
		this->callbacks.sample_command.call();

	} else if (command == BILBO_SPI_COMMAND_TRAJECTORY_WRITE) {
		this->_trajectory_length = length;
		this->mode = BILBO_SPI_COMM_MODE_RX_TRAJECTORY;
		this->receiveTrajectoryInputs(length);

	} else if (command == BILBO_SPI_COMMAND_PATH_WRITE) {
		this->_path_length = length;
		this->mode = BILBO_SPI_COMM_MODE_RX_PATH;
		this->receivePathPoints(length);
	}

}
