/*
 * twipr_messages.h
 *
 *  Created on: 3 Mar 2023
 *      Author: lehmann_workstation
 */

#ifndef COMMUNICATION_TWIPR_MESSAGES_H_
#define COMMUNICATION_TWIPR_MESSAGES_H_

#include "core.h"
#include "twipr_uart_communication.h"

//
//#define MESSAGE_ID_WARNING 0x10
//#define MESSAGE_ID_ERROR 0x11
//
//
//#define MESSAGE_TRAJECTORY_FNISHED 0x30


//#define MESSAGE_ID_DEBUG 0xDD

// Messages
//#define TWIPR_MESSAGE_EVENT_WARNING 0x0301
//
//#define SEQUENCER_EVENT 0x0401




class BILBO_Message_t {
public:

	BILBO_Message_t(){

	}

	virtual core_comm_SerialMessage encode () = 0;


private:

};

template<typename data_type_t, serial_message_type_t msg_type, uint8_t message_id>
class BILBO_Message: public BILBO_Message_t {
public:

	BILBO_Message() {
		this->data = &this->data_union.data;
	}

	BILBO_Message(data_type_t message_data) {
		this->data = &this->data_union.data;
		this->data_union.data = message_data;
	}

	core_comm_SerialMessage encode() override {
		core_comm_SerialMessage msg;

		msg.cmd = this->type;
		msg.address_1 = 0x01;
		msg.address_2 = this->id >> 8;
		msg.address_3 = this->id;
		msg.flag = 0x00;
		msg.data_ptr = this->data_union.data_buffer;
		msg.len = this->len;
		return msg;
	}

	data_type_t decode(uint8_t* data) {
		for (int i=0; i<this->len ; i++){
			this->data_union.data_buffer[i] = data[i];
		}
		return this->data_union.data;
	}


	uint16_t len = sizeof(data_type_t);
	serial_message_type_t type = msg_type;
	uint8_t id = message_id;

	union data_union_t {
		uint8_t data_buffer[sizeof(data_type_t)];
		data_type_t data;
	} data_union;

	data_type_t* data;

private:

};



#endif /* COMMUNICATION_TWIPR_MESSAGES_H_ */
