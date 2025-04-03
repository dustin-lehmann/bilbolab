/*
 * twipr_sequencer.cpp
 *
 *  Created on: Nov 20, 2024
 *      Author: Dustin Lehmann
 */

#include "twipr_sequencer.h"
#include "twipr_communication.h"
#include "robot-control_std.h"

_RAM_D2 twipr_sequence_input_t rx_sequence_buffer[TWIPR_SEQUENCE_BUFFER_SIZE ];
_RAM_D2 twipr_sequence_input_t sequence_buffer[TWIPR_SEQUENCE_BUFFER_SIZE ];

//twipr_sequence_input_t rx_sequence_buffer[TWIPR_SEQUENCE_BUFFER_SIZE ];
//twipr_sequence_input_t sequence_buffer[TWIPR_SEQUENCE_BUFFER_SIZE ];


TWIPR_Sequencer* sequencer = NULL;

TWIPR_Sequencer::TWIPR_Sequencer() {

}

/* =============================================================== */
void TWIPR_Sequencer::init(twipr_sequencer_config_t config) {
	this->config = config;
	this->sequence_tick = 0;
	this->mode = TWIPR_SEQUENCER_MODE_IDLE;

	sequencer = this;

	this->resetSequenceData();

	this->config.comm->callbacks.trajectory_received.registerFunction(this,
			&TWIPR_Sequencer::spiSequenceReceived_callback);

	this->config.control->callbacks.mode_change.registerFunction(this,
			&TWIPR_Sequencer::modeChange_callback);

	HAL_DMA_RegisterCallback(
	TWIPR_FIRMWARE_TRAJECTORY_DMA_STREAM, HAL_DMA_XFER_CPLT_CB_ID,
			trajectory_dma_transfer_cmplt_callback);
}
/* =============================================================== */
void TWIPR_Sequencer::start() {

}

/* =============================================================== */
void TWIPR_Sequencer::update() {

	if (this->mode == TWIPR_SEQUENCER_MODE_IDLE
			|| this->mode == TWIPR_SEQUENCER_MODE_ERROR) {
		return;
	}

	// Sequencer is running. Do the Update

	// If this is the first sample in the sequence, send out the trajectory started message
	if (this->sequence_tick == 0) {
		sequencer_event_message_data_t event_message_data = { .event =
				TRAJECTORY_STARTED, .sequence_id =
				this->loaded_sequence.sequence_id, .sequence_tick = 0, .tick =
				tick_global };
		BILBO_Message_Sequencer_Event msg(event_message_data);
		sendMessage(msg);
	}

	// Check if we have reached the end of the sequence
	if (this->sequence_tick >= this->loaded_sequence.length) {
		this->finishSequence();

		return;
	}

	// Get the input from the sequence
	twipr_sequence_input_t current_input = sequence_buffer[this->sequence_tick];

	if (this->loaded_sequence.control_mode == TWIPR_CONTROL_MODE_BALANCING){
		twipr_balancing_control_input_t balancing_input = {
				.u_1 = current_input.u_1,
				.u_2 = current_input.u_2
		};
		this->config.control->_setBalancingInput(balancing_input);
	}



	this->sequence_tick++;
}
/* =============================================================== */
bool TWIPR_Sequencer::startSequence(uint16_t id) {
	this->sequence_tick = 0;

	// Check the requirements
	if (!this->loaded_sequence.loaded) {
		send_error("Cannot start sequence %d. Not received", id);
		return false;
	}

	// Check the control mode
	if (this->config.control->mode != this->loaded_sequence.control_mode) {
		send_error(
				"Cannot start sequence %d. Wrong control mode: %d (Required: %d)",
				id, this->loaded_sequence.control_mode);
		return false;
	}

	// Check if the loaded sequence has the same id
	if (this->loaded_sequence.sequence_id != id) {
		send_error("Cannot start sequence %d. Other sequence loaded: %d", id,
				this->loaded_sequence.sequence_id);
		return false;
	}

	this->mode = TWIPR_SEQUENCER_MODE_RUNNING;

	// Disable External Inputs to the controller
	this->config.control->disableExternalInput();

	send_info("Start Sequence %d with length %d",
			this->loaded_sequence.sequence_id, this->loaded_sequence.length);

	// Call the callback(s)
	if (this->_callbacks.started.registered) {
		this->_callbacks.started.call((uint16_t) id);
	}
	return true;
}

/* =============================================================== */
void TWIPR_Sequencer::abortSequence() {

	// TODO: I need to reflect in the sample if the sequence was finished or aborted

	// Enable external inputs to the controller
	this->config.control->enableExternalInput();

	this->config.control->_resetExternalInput();

	// Set the mode
	this->mode = TWIPR_SEQUENCER_MODE_ERROR;

	send_warning("Sequence %d has been aborted",
			this->loaded_sequence.sequence_id);

	sequencer_event_message_data_t event_message_data = { .event =
			TRAJECTORY_ABORTED,
			.sequence_id = this->loaded_sequence.sequence_id, .sequence_tick =
					this->sequence_tick, .tick = tick_global };
	BILBO_Message_Sequencer_Event msg(event_message_data);
	sendMessage(msg);

	//
	if (this->_callbacks.aborted.registered) {
		this->_callbacks.aborted.call(
				(uint16_t) this->loaded_sequence.sequence_id);
	}

	this->resetSequenceData();
}

/* =============================================================== */
void TWIPR_Sequencer::finishSequence() {



	// Set the sequencer mode mode
	this->mode = TWIPR_SEQUENCER_MODE_IDLE;

//	// Give an audio queue
//	rc_buzzer.setConfig(900, 150, this->loaded_sequence.sequence_id);
//	rc_buzzer.start();

	// TODO: Send Data to host
	send_info("Sequence %d finished", this->loaded_sequence.sequence_id);

	sequencer_event_message_data_t event_message_data = { .event =
			TRAJECTORY_FINISHED, .sequence_id =
			this->loaded_sequence.sequence_id, .sequence_tick =
			this->sequence_tick, .tick = tick_global };
	BILBO_Message_Sequencer_Event msg(event_message_data);

	sendMessage(msg);

	//
	if (this->_callbacks.finished.registered) {
		this->_callbacks.finished.call(
				(uint16_t) this->loaded_sequence.sequence_id);
	}



	// Set the control mode to the desired mode
	this->config.control->setMode(this->loaded_sequence.control_mode_end);


	this->resetSequenceData();

	// Enable external inputs to the controller
	this->config.control->enableExternalInput();
	//
	// Set the controller inputs to zero
	this->config.control->_resetExternalInput();
}
/* =============================================================== */
bool TWIPR_Sequencer::loadSequence(
		twipr_sequencer_sequence_data_t sequence_data) {

	send_debug("Load sequence %d with length %d", sequence_data.sequence_id,
			sequence_data.length);

	if (this->mode == TWIPR_SEQUENCER_MODE_RUNNING){
		send_error("Sequence %d currently running. Cannot load new sequence", this->loaded_sequence.sequence_id);
		return false;
	}

	// Do not accept sequences with id=0

	if (sequence_data.sequence_id == 0) {
		send_error("Sequence needs an identifier != 0");
		return false;
	}

	if (sequence_data.length > TWIPR_SEQUENCE_BUFFER_SIZE) {
		send_error("Sequence %d too long: %d samples (%d max)",
				sequence_data.sequence_id, sequence_data.length,
				TWIPR_SEQUENCE_BUFFER_SIZE);
		return false;
	}

	// Check the required control mode. For now, we only accept balancing. TODO
	if (sequence_data.control_mode != TWIPR_CONTROL_MODE_BALANCING) {
		send_error("Sequence with control mode %d is not yet supported",
				sequence_data.control_mode);
		return false;
	}

	this->loaded_sequence = sequence_data;
	this->loaded_sequence.loaded = false;
	this->mode = TWIPR_SEQUENCER_MODE_IDLE;
	return true;
}

/* =============================================================== */
twipr_sequencer_sequence_data_t TWIPR_Sequencer::readSequence() {
	return this->loaded_sequence;
}
/* =============================================================== */
// @SuppressWarnings("all")
void TWIPR_Sequencer::resetSequenceData() {
	this->loaded_sequence = {
		.sequence_id = 0,
		.length = 0,
		.require_control_mode = true,
		.wait_time_beginning = 0,
		.wait_time_end = 0,
		.control_mode = TWIPR_CONTROL_MODE_OFF,
		.control_mode_end = TWIPR_CONTROL_MODE_OFF,
		.loaded = true
	};

	this->sequence_tick = 0;
}

/* =============================================================== */
twipr_sequencer_sample_t TWIPR_Sequencer::getSample() {
	twipr_sequencer_sample_t sample;

	if (this->mode == TWIPR_SEQUENCER_MODE_RUNNING) {
		sample.mode = this->mode;
		sample.sequence_id = this->loaded_sequence.sequence_id;
		sample.sequence_tick = this->sequence_tick;
	} else {
		sample.sequence_id = 0;
		sample.sequence_tick = 0;
	}

	return sample;
}

/* =============================================================== */
void TWIPR_Sequencer::spiSequenceReceived_callback(uint16_t trajectory_length) {

	if (this->loaded_sequence.sequence_id == 0) {
		send_error("Received sequence of length %d, but did not wait for one.",
				trajectory_length);
		return;
	}

	if (this->loaded_sequence.loaded) {
		send_error("Sequence %d has already been loaded",
				this->loaded_sequence.sequence_id);
	}

	HAL_DMA_Start_IT(
	TWIPR_FIRMWARE_TRAJECTORY_DMA_STREAM, (uint32_t) &rx_sequence_buffer,
			(uint32_t) &sequence_buffer,
			sizeof(twipr_sequence_input_t) * TWIPR_SEQUENCE_BUFFER_SIZE);

}

void TWIPR_Sequencer::sequenceReceivedAndTransferred_callback() {
	this->loaded_sequence.loaded = true;
	sequencer_event_message_data_t event_message_data = { .event =
			TRAJECTORY_RECEIVED, .sequence_id =
			this->loaded_sequence.sequence_id, .sequence_tick = 0, .tick =
			tick_global };
	BILBO_Message_Sequencer_Event msg(event_message_data);
	sendMessage(msg);
}

/* =============================================================== */
void TWIPR_Sequencer::modeChange_callback(twipr_control_mode_t mode) {
// TODO
	if (this->mode != TWIPR_SEQUENCER_MODE_RUNNING) {
		return;
	}

	this->abortSequence();

}

void trajectory_dma_transfer_cmplt_callback(DMA_HandleTypeDef *hdma) {
	if (sequencer != NULL){
		sequencer->sequenceReceivedAndTransferred_callback();
	}
}

