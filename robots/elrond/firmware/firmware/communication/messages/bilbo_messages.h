/*
 * messages.h
 *
 *  Created on: Mar 7, 2025
 *      Author: lehmann
 */

#ifndef COMMUNICATION_MESSAGES_BILBO_MESSAGES_H_
#define COMMUNICATION_MESSAGES_BILBO_MESSAGES_H_

#include "bilbo_message.h"
#include "firmware_core.h"


// =========================================================================================================== //
// Define the buffer size for debug messages.
#define DEBUG_PRINT_BUFFER_SIZE 100

typedef struct debug_message_data_t {
    uint8_t flag;                             ///< Flag indicating the type of debug message.
    char message[DEBUG_PRINT_BUFFER_SIZE];    ///< Buffer to hold the debug message.
} debug_message_data_t;

typedef BILBO_Message<debug_message_data_t, MSG_EVENT, BILBO_MESSAGE_PRINT> BILBO_Debug_Message;


// =========================================================================================================== //
//typedef struct warning_message_struct_t {
//	bilbo_error_type_t error;
//	char text[100];
//} warning_message_struct_t;
//
//typedef BILBO_Message<warning_message_struct_t, MSG_EVENT, BILBO_MESSAGE_WARNING> BILBO_Message_Warning;



// =========================================================================================================== //
typedef enum sequencer_event_t {
	TRAJECTORY_STARTED = 1,
	TRAJECTORY_FINISHED = 2,
	TRAJECTORY_ABORTED = 3,
	TRAJECTORY_RECEIVED = 4,
} sequencer_event_t;

typedef struct sequencer_event_message_data_t {
	sequencer_event_t event;
	uint16_t sequence_id;
	uint32_t sequence_tick;
	uint32_t tick;
} sequencer_event_message_data_t;

typedef BILBO_Message<sequencer_event_message_data_t, MSG_EVENT, BILBO_MESSAGE_SEQUENCER_EVENT> BILBO_Message_Sequencer_Event;


#endif /* COMMUNICATION_MESSAGES_BILBO_MESSAGES_H_ */
