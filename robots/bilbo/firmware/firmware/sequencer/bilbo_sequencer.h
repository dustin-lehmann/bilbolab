/*
 * bilbo_sequencer.h
 *
 *  Created on: Nov 22, 2025
 *      Author: lehmann
 */

#ifndef SEQUENCER_BILBO_SEQUENCER_H_
#define SEQUENCER_BILBO_SEQUENCER_H_


#include <bilbo_messages.h>
#include "bilbo_control.h"
#include "firmware_core.h"

class BILBO_CommunicationManager;

/**
 * @brief Configuration for the BILBO_Sequencer.
 */
typedef struct bilbo_sequencer_config_t {
	BILBO_Control *control;
	BILBO_CommunicationManager *comm;
} bilbo_sequencer_config_t;

/**
 * @brief High-level state of the sequencer.
 */
typedef enum bilbo_sequencer_mode_t : uint8_t {
	BILBO_SEQUENCER_MODE_IDLE = 0,
	BILBO_SEQUENCER_MODE_RUNNING = 1,
	BILBO_SEQUENCER_MODE_ERROR = 2
} bilbo_sequencer_mode_t;

/**
 * @brief Metadata for a trajectory / sequence.
 */
typedef struct bilbo_sequencer_sequence_data_t {
	uint16_t sequence_id;          ///< ID of the sequence
	uint16_t length;               ///< Number of samples
	bool require_control_mode; ///< true: Control mode must be set in advance. false: Sequencer sets control mode
	uint16_t wait_time_beginning; ///< Wait time in ticks before starting sequence (currently unused)
	uint16_t wait_time_end; ///< Time in ticks after sequence (currently unused)
	bilbo_control_mode_t control_mode; ///< Control mode in which the sequence is run
	bilbo_control_mode_t control_mode_end; ///< Control mode to switch to after the sequence
	bool loaded;               ///< True if sequence data is present in buffer
} bilbo_sequencer_sequence_data_t;

/**
 * @brief Callback identifiers for application-level hooks.
 */
typedef enum bilbo_sequencer_callback_id_t : uint8_t {
	BILBO_SEQUENCER_CALLBACK_SEQUENCE_STARTED = 1,
	BILBO_SEQUENCER_CALLBACK_SEQUENCE_FINISHED = 2,
	BILBO_SEQUENCER_CALLBACK_SEQUENCE_ABORTED = 3,
} bilbo_sequencer_callback_id_t;

/**
 * @brief One sample of a sequence (trajectory input).
 */
typedef struct bilbo_sequence_input_t {
	uint32_t step;
	float u_1;
	float u_2;
} bilbo_sequence_input_t;

/**
 * @brief Sample snapshot of sequencer state (for logging / telemetry).
 */
typedef struct bilbo_sequencer_sample_t {
	bilbo_sequencer_mode_t mode;
	uint16_t sequence_id;
	uint32_t sequence_tick;
} bilbo_sequencer_sample_t;

/**
 * @brief Callback set for sequence lifecycle events.
 */
typedef struct bilbo_sequencer_callbacks_t {
	core_utils_Callback<void, uint16_t> started;
	core_utils_Callback<void, uint16_t> finished;
	core_utils_Callback<void, uint16_t> aborted;
} bilbo_sequencer_callbacks_t;

extern bilbo_sequence_input_t rx_sequence_buffer[BILBO_SEQUENCE_BUFFER_SIZE ];
extern bilbo_sequence_input_t sequence_buffer[BILBO_SEQUENCE_BUFFER_SIZE ];

/**
 * @brief Sequencer / trajectory player.
 *
 * The sequencer runs at 100 Hz (inner control loop) and plays back a
 * pre-loaded input sequence to the controller. Trajectories can be requested
 * from outside at arbitrary times, but the actual start is aligned to the
 * 10 Hz "outer loop" grid, i.e. it starts only when
 * `tick_global % 10 == 0`.
 */
class BILBO_Sequencer {
public:
	/// Alignment for sequence start in ticks of the 100 Hz loop.
	static constexpr uint32_t START_ALIGNMENT_TICKS = 10U; // 100 Hz / 10 Hz

	BILBO_Sequencer();

	/**
	 * @brief Initialize the sequencer with the required managers.
	 */
	void init(bilbo_sequencer_config_t config);

	/**
	 * @brief Start the sequencer subsystem (if needed).
	 *
	 * Currently a no-op but kept for symmetry.
	 */
	void start();

	/**
	 * @brief Main update function, called at 100 Hz.
	 *
	 * - Handles delayed trajectory start on the 10 Hz grid.
	 * - Sends events.
	 * - Feeds the controller with the current sequence sample.
	 */
	void update();

	/**
	 * @brief Request starting of a sequence with given id.
	 *
	 * This does not start the sequence immediately. It:
	 *  - validates the request,
	 *  - queues it,
	 *  - and the actual start is performed in update() when
	 *    `tick_global % START_ALIGNMENT_TICKS == 0`.
	 *
	 * @param id Sequence ID that should be started.
	 * @return true if the request was accepted and queued, false on error.
	 */
	bool startSequence(uint16_t id);

	/**
	 * @brief Abort the currently running sequence (if any).
	 *
	 * Sets the sequencer to ERROR mode until a new sequence is loaded.
	 */
	void abortSequence();

	/**
	 * @brief Finish the current sequence normally.
	 *
	 * Sends the FINISHED event, restores controller state and goes back to IDLE.
	 */
	void finishSequence();

	/**
	 * @brief Load sequence metadata before receiving the actual data via SPI/DMA.
	 *
	 * @param sequence_data Meta information about the sequence.
	 * @return true if sequence data was accepted and sequencer is ready to receive samples.
	 */
	bool loadSequence(bilbo_sequencer_sequence_data_t sequence_data);

	/**
	 * @brief Get the currently loaded sequence metadata.
	 */
	bilbo_sequencer_sequence_data_t readSequence();

	/**
	 * @brief Clear sequence meta information and reset counters.
	 *
	 * The sequencer mode itself is not changed by this function.
	 */
	void resetSequenceData();

	/**
	 * @brief Get a snapshot of the sequencer state for logging / telemetry.
	 */
	bilbo_sequencer_sample_t getSample();

	/**
	 * @brief Callback from communication layer when raw trajectory data has been received.
	 *
	 * This triggers a DMA transfer from rx_buffer to the working buffer.
	 */
	void spiSequenceReceived_callback(uint16_t length);

	/**
	 * @brief Callback when the control mode of the controller changes.
	 *
	 * If a sequence is running, it will be aborted.
	 */
	void modeChange_callback(bilbo_control_mode_t mode);

	/**
	 * @brief Called once the DMA transfer of the complete sequence has finished.
	 */
	void sequenceReceivedAndTransferred_callback();

	// Public state (as in original code)
	bilbo_sequencer_mode_t mode;
	uint32_t sequence_tick;
	bilbo_sequencer_config_t config;
	bilbo_sequencer_sequence_data_t loaded_sequence;

	bilbo_sequence_input_t *rx_buffer = rx_sequence_buffer;
	bilbo_sequence_input_t *buffer = sequence_buffer;

private:
	/**
	 * @brief Perform the actual start of the sequence.
	 *
	 * Called internally from update() when:
	 *  - a start was requested and
	 *  - tick_global is aligned to the start grid.
	 *
	 * @return true on success, false if the start could not be performed.
	 */

	bool _startSequenceInternal();

	/**
	 * @brief Send a TRAJECTORY_ABORTED event when the queued start fails validation.
	 */
	void _sendStartFailedAbort();

	/// Queued start request flag.
	bool _start_requested = false;
	/// Sequence id that was requested to start.
	uint16_t _start_requested_id = 0;
	/// Tick at which the start was requested (for debugging).
	uint32_t _start_request_tick = 0;

	bilbo_sequencer_callbacks_t _callbacks;
};

void trajectory_dma_transfer_cmplt_callback(DMA_HandleTypeDef *hdma);

#endif /* SEQUENCER_BILBO_SEQUENCER_H_ */
