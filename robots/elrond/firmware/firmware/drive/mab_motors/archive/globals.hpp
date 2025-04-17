/*
 * globals.hpp
 *
 *  Created on: Dec 10, 2024
 *      Author: mneub
 */

#ifndef GLOBALS_HPP_
#define GLOBALS_HPP_

#include "main.h" // for globals from main (for example ErrorHandler();)
#include "can.hpp"
#include <stdio.h>
#include "motor.hpp"

// declaration of global variables
extern can_buffer buffer;
extern md80 motor;

// specific functions depending on globals
void initialize_globals();

// globals from main.h
extern FDCAN_HandleTypeDef hfdcan1;



#endif /* GLOBALS_HPP_ */
