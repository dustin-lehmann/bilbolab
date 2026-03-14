/*
 * bilbo_spi_communication.h
 *
 *  Created on: 12 Mar 2023
 *      Author: Dustin Lehmann
 *
 *  Description:
 *      Header file for the BILBO SPI Communication interface.
 *      It defines configuration structures, enums, callback types, and the interface
 *      for managing SPI communication for sample data transmission and trajectory reception.
 */

#ifndef COMMUNICATION_BILBO_SPI_COMMUNICATION_H_
#define COMMUNICATION_BILBO_SPI_COMMUNICATION_H_

#include "core.h"
#include "bilbo_logging.h"
#include "bilbo_sequencer.h"
#include "firmware_core.h"

// Define the length of the command message used in SPI communication.
#define BILBO_SPI_COMMAND_MESSAGE_LENGTH 4

#define BILBO_SPI_COMMAND_SAMPLES_READ 0x01
#define BILBO_SPI_COMMAND_TRAJECTORY_WRITE 0x02
#define BILBO_SPI_COMMAND_PATH_WRITE 0x03

/**
 * @brief SPI Communication configuration structure.
 *
 * This structure contains all the hardware parameters and buffers needed to
 * configure the SPI communication interface.
 */
typedef struct bilbo_spi_comm_config_t {
    SPI_HandleTypeDef *hspi;                      ///< Pointer to the SPI hardware handle.
    uint8_t *sample_response_buffer;              ///< Pre-assembled response buffer ([count][batches...]).
    uint8_t *sample_response_dummy;               ///< Dummy RX buffer for SPI TransmitReceive.
    uint32_t sample_response_max_size;            ///< Max size of response buffer.
    bilbo_sequence_input_t *sequence_buffer;      ///< Buffer for receiving trajectory inputs.
    uint16_t len_sequence_buffer;                 ///< Length of the trajectory sequence buffer.
    uint8_t *path_rx_buffer;                      ///< Buffer for receiving path points via SPI.
    uint16_t len_path_buffer;                     ///< Max number of path points the buffer can hold.
} bilbo_spi_comm_config_t;

/**
 * @brief SPI Communication operating modes.
 *
 * Defines the operating mode for the SPI communication interface.
 */
typedef enum bilbo_spi_comm_mode_t : uint8_t {
    BILBO_SPI_COMM_MODE_NONE = 0,   ///< No operation mode.
	BILBO_SPI_COMM_MODE_LISTENING_FOR_COMMAND = 1,
    BILBO_SPI_COMM_MODE_RX_TRAJECTORY   = 2,   ///< Reception mode.
    BILBO_SPI_COMM_MODE_TX_SAMPLES   = 3,   ///< Transmission mode.
    BILBO_SPI_COMM_MODE_RX_PATH   = 4,   ///< Path points reception mode.
} bilbo_spi_comm_mode_t;

/**
 * @brief SPI Communication callback identifier.
 *
 * Enumerates the callback types for SPI communication events.
 */
//typedef enum bilbo_spi_comm_callback_id_t {
//    BILBO_SPI_COMM_CALLBACK_TRAJECTORY_RX,  ///< Callback for trajectory data reception.
//    BILBO_SPI_COMM_CALLBACK_SAMPLE_TX,      ///< Callback for sample data transmission.
//} bilbo_spi_comm_callback_id_t;

/**
 * @brief Structure for SPI Communication callbacks.
 *
 * Contains callback functions for trajectory reception and sample transmission events.
 */
//typedef struct bilbo_spi_comm_callbacks_t {
//    core_utils_Callback<void, uint16_t> trajectory_rx_callback; ///< Callback for trajectory reception.
//    core_utils_Callback<void, uint16_t> sample_tx_callback;       ///< Callback for sample transmission.
//} bilbo_spi_comm_callbacks_t;

typedef struct bilbo_spi_comm_callbacks_t {
	core_utils_CallbackContainer<2, uint16_t> trajectory_received;
	core_utils_CallbackContainer<2, uint16_t> trajectory_command;
	core_utils_CallbackContainer<2, void> sample_command;
	core_utils_CallbackContainer<2, void> samples_transmitted;
	core_utils_CallbackContainer<2, uint16_t> path_received;
} bilbo_spi_comm_callbacks_t;

/**
 * @brief BILBO SPI Communication class.
 *
 * This class manages SPI communication by initializing the SPI hardware,
 * starting transmission/reception, and handling callbacks for SPI events.
 */
class BILBO_SPI_Communication {
public:
    /**
     * @brief Constructor for BILBO_SPI_Communication.
     *
     * Initializes internal variables. Actual hardware initialization is done in init().
     */
    BILBO_SPI_Communication();

    /**
     * @brief Initialize the SPI communication interface.
     *
     * Configures the SPI hardware and sets up the RX/TX buffers along with their callbacks.
     *
     * @param config Configuration structure containing SPI parameters and buffers.
     */
    void init(bilbo_spi_comm_config_t config);

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
     * @brief Send a pre-assembled sample response buffer via SPI DMA.
     *
     * @param buffer   Pointer to the response buffer ([uint32_t count][batches...]).
     * @param len      Total transfer length in bytes.
     * @param dummy_rx Dummy RX buffer of the same length.
     */
    void sendSampleResponse(uint8_t *buffer, uint32_t len, uint8_t *dummy_rx);

    /**
     * @brief Receive trajectory inputs over SPI.
     *
     * Initiates the reception of trajectory input data into the configured sequence buffer.
     *
     * @param steps Number of trajectory steps (samples) to receive.
     */
    void receiveTrajectoryInputs(uint16_t steps);

    /**
     * @brief Receive path points over SPI.
     *
     * Initiates the reception of path point data into the configured path buffer.
     *
     * @param count Number of path points to receive.
     */
    void receivePathPoints(uint16_t count);


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
    bilbo_spi_comm_config_t config;         ///< SPI communication configuration.
    bilbo_spi_comm_mode_t mode = BILBO_SPI_COMM_MODE_NONE; ///< Current SPI operating mode.

    bilbo_spi_comm_callbacks_t callbacks; ///< Structure containing registered SPI callbacks.

private:

    void _handleCommand();

    uint8_t _commandBuffer[BILBO_SPI_COMMAND_MESSAGE_LENGTH]; ///< Buffer for SPI command messages.
    uint16_t _len; ///< Variable to store the length of transmitted data.
    core_hardware_SPI_slave spi_slave; ///< SPI slave interface object.




    uint16_t _trajectory_length;
    uint16_t _path_length;
};

#endif /* COMMUNICATION_BILBO_SPI_COMMUNICATION_H_ */
