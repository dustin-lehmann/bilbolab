/*
 * twipr_model.h
 *
 *  Created on: 22 Feb 2023
 *      Author: Dustin Lehmann
 */

#ifndef ESTIMATION_TWIPR_MODEL_H_
#define ESTIMATION_TWIPR_MODEL_H_

#include "firmware_settings.h"




// Ensure BILBO_MODEL is defined
#if !defined(BILBO_MODEL_NORMAL) && !defined(BILBO_MODEL_SMALL) && !defined(BILBO_MODEL_BIG)
    #error "BILBO_MODEL is not defined. Please define as either BILBO_MODEL_NORMAL, BILBO_MODEL_BIG, BILBO_MODEL_SMALL."
#endif

// Define WHEEL_DIAMETER based on the model
#ifdef BILBO_MODEL_NORMAL
    #define WHEEL_DIAMETER 0.12381
	#define WHEEL_DISTANCE 0.167167
#elif defined(BILBO_MODEL_SMALL)
    #define WHEEL_DIAMETER 0.099
	#define WHEEL_DISTANCE 0.157
#elif defined(BILBO_MODEL_BIG)
    #define WHEEL_DIAMETER 0.15736
	#define WHEEL_DISTANCE 0.24
#else
    #error "BILBO_MODEL is not correctly defined."
#endif

#endif /* ESTIMATION_TWIPR_MODEL_H_ */
