/*
 * twipr_spi_communication.h
 *
 *  Created on: 12 Mar 2023
 *      Author: Dustin Lehmann
 *
 *  Description:
 *      Header file for the TWIPR SPI Communication interface.
 *      It defines configuration structures, enums, callback types, and the interface
 *      for managing SPI communication for sample data transmission and trajectory reception.
 */

#ifndef COMMUNICATION_TWIPR_SPI_COMMUNICATION_H_
#define COMMUNICATION_TWIPR_SPI_COMMUNICATION_H_

#include "core.h"
#include "twipr_logging.h"
#include "twipr_sequencer.h"
#include "firmware_core.h"

// Define the length of the command message used in SPI communication.
#define TWIPR_SPI_COMMAND_MESSAGE_LENGTH 4

#define TWIPR_SPI_COMMAND_SAMPLES_READ 0x01
#define TWIPR_SPI_COMMAND_TRAJECTORY_WRITE 0x02

/**
 * @brief SPI Communication configuration structure.
 *
 * This structure contains all the hardware parameters and buffers needed to
 * configure the SPI communication interface.
 */
typedef struct twipr_spi_comm_config_t {
    SPI_HandleTypeDef *hspi;                      ///< Pointer to the SPI hardware handle.
    twipr_logging_sample_t *sample_buffer;        ///< Buffer for sample data transmission.
    uint16_t len_sample_buffer;                   ///< Length of the sample data buffer.
    twipr_sequence_input_t *sequence_buffer;      ///< Buffer for receiving trajectory inputs.
    uint16_t len_sequence_buffer;                 ///< Length of the trajectory sequence buffer.
} twipr_spi_comm_config_t;

/**
 * @brief SPI Communication operating modes.
 *
 * Defines the operating mode for the SPI communication interface.
 */
typedef enum twipr_spi_comm_mode_t {
    TWIPR_SPI_COMM_MODE_NONE = 0,   ///< No operation mode.
	TWIPR_SPI_COMM_MODE_LISTENING_FOR_COMMAND = 1,
    TWIPR_SPI_COMM_MODE_RX_TRAJECTORY   = 2,   ///< Reception mode.
    TWIPR_SPI_COMM_MODE_TX_SAMPLES   = 3,   ///< Transmission mode.
} twipr_spi_comm_mode_t;

/**
 * @brief SPI Communication callback identifier.
 *
 * Enumerates the callback types for SPI communication events.
 */
//typedef enum twipr_spi_comm_callback_id_t {
//    TWIPR_SPI_COMM_CALLBACK_TRAJECTORY_RX,  ///< Callback for trajectory data reception.
//    TWIPR_SPI_COMM_CALLBACK_SAMPLE_TX,      ///< Callback for sample data transmission.
//} twipr_spi_comm_callback_id_t;

/**
 * @brief Structure for SPI Communication callbacks.
 *
 * Contains callback functions for trajectory reception and sample transmission events.
 */
//typedef struct twipr_spi_comm_callbacks_t {
//    core_utils_Callback<void, uint16_t> trajectory_rx_callback; ///< Callback for trajectory reception.
//    core_utils_Callback<void, uint16_t> sample_tx_callback;       ///< Callback for sample transmission.
//} twipr_spi_comm_callbacks_t;

typedef struct bilbo_spi_comm_callbacks_t {
	core_utils_CallbackContainer<2, uint16_t> trajectory_received;
	core_utils_CallbackContainer<2, uint16_t> trajectory_command;
	core_utils_CallbackContainer<2, void> sample_command;
	core_utils_CallbackContainer<2, void> samples_transmitted;
} bilbo_spi_comm_callbacks_t;

/**
 * @brief TWIPR SPI Communication class.
 *
 * This class manages SPI communication by initializing the SPI hardware,
 * starting transmission/reception, and handling callbacks for SPI events.
 */
class TWIPR_SPI_Communication {
public:
    /**
     * @brief Constructor for TWIPR_SPI_Communication.
     *
     * Initializes internal variables. Actual hardware initialization is done in init().
     */
    TWIPR_SPI_Communication();

    /**
     * @brief Initialize the SPI communication interface.
     *
     * Configures the SPI hardware and sets up the RX/TX buffers along with their callbacks.
     *
     * @param config Configuration structure containing SPI parameters and buffers.
     */
    void init(twipr_spi_comm_config_t config);

    /**
     * @brief Start the SPI communication interface.
     *
     * Starts the SPI slave and provides initial sample data for transmission.
     */
    void start();

    void reset();

    /**
     * @brief Register a callback for SPI communication events.
     *
     * Registers a callback function for either sample transmission complete or
     * trajectory reception events.
     *
     * @param callback_id Identifier specifying the callback type.
     * @param callback Callback function to register.
     */
    void startListeningForCommand();

    /**
     * @brief Stop the SPI transmission.
     *
     * Aborts any ongoing SPI transmission using the hardware SPI handle.
     */
    void stopTransmission();

    /**
     * @brief Provide sample data using the default configuration.
     *
     * Calls the overloaded provideSampleData function with the default sample buffer
     * and buffer length provided in the configuration.
     */
    void provideSampleData();

    /**
     * @brief Receive trajectory inputs over SPI.
     *
     * Initiates the reception of trajectory input data into the configured sequence buffer.
     *
     * @param steps Number of trajectory steps (samples) to receive.
     */
    void receiveTrajectoryInputs(uint16_t steps);


    /**
     * @brief SPI receive complete callback.
     *
     * Called when the SPI slave has completed receiving data.
     */
    void rx_cmplt_function();

    /**
     * @brief SPI transmit complete callback.
     *
     * Called when the SPI slave has finished transmitting data.
     */
    void tx_cmplt_function();

    /**
     * @brief SPI full-duplex (RX/TX) complete callback.
     *
     * Currently provided as a stub for potential future use.
     */
    void rxtx_cmplt_function();

    // Public member variables.
    twipr_spi_comm_config_t config;         ///< SPI communication configuration.
    twipr_spi_comm_mode_t mode = TWIPR_SPI_COMM_MODE_NONE; ///< Current SPI operating mode.

    bilbo_spi_comm_callbacks_t callbacks; ///< Structure containing registered SPI callbacks.

private:

    void _handleCommand();

    uint8_t _commandBuffer[TWIPR_SPI_COMMAND_MESSAGE_LENGTH]; ///< Buffer for SPI command messages.
    uint16_t _len; ///< Variable to store the length of transmitted data.
    core_hardware_SPI_slave spi_slave; ///< SPI slave interface object.




    bool _samples_read;
    uint16_t _trajectory_length;
};

#endif /* COMMUNICATION_TWIPR_SPI_COMMUNICATION_H_ */
