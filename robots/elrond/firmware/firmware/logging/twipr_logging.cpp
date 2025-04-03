/*
 * twipr_logging.cpp
 *
 *  Created on: Nov 20, 2024
 *      Author: lehmann
 */


#include "twipr_logging.h"
#include "firmware.hpp"

TWIPR_Logging::TWIPR_Logging(){

}


void TWIPR_Logging::init(twipr_logging_config_t config){
	this->config = config;
	this->sample_index = 0;
}

void TWIPR_Logging::start() {

}


void TWIPR_Logging::reset() {
	this->sample_index = 0;
}



twipr_logging_buffer_status_t TWIPR_Logging::collectSamples(){
	this->sample_buffer[this->sample_index].general = this->config.firmware->getSample();
	this->sample_buffer[this->sample_index].errors = this->config.error_handler->getSample();
	this->sample_buffer[this->sample_index].control = this->config.control->getSample();
	this->sample_buffer[this->sample_index].estimation = this->config.estimation->getSample();
	this->sample_buffer[this->sample_index].sensors = this->config.sensors->getData();
	this->sample_buffer[this->sample_index].sequence = this->config.sequencer->getSample();
	this->sample_buffer[this->sample_index].debug = this->config.firmware->debugData;

	this->sample_index++;

	if (this->sample_index == TWIPR_FIRMWARE_SAMPLE_BUFFER_SIZE){
		this->sample_index = 0;
		return TWIPR_LOGGING_BUFFER_FULL;
	}

	return TWIPR_LOGGING_BUFFER_NOT_FULL;
}



//this->_sample_buffer[this->_sample_buffer_index].general.tick = this->tick;
//		this->_sample_buffer[this->_sample_buffer_index].general.status = 1;
//
//
//		this->_sample_buffer[this->_sample_buffer_index].control =
//				this->config.control->getSample();
//		this->_sample_buffer[this->_sample_buffer_index].estimation =
//				this->config.estimation->getSample();
//		this->_sample_buffer[this->_sample_buffer_index].sensors =
//				this->config.sensors->getData();
//		this->_sample_buffer[this->_sample_buffer_index].sequence =
//						this->config.sequencer->getSample();
