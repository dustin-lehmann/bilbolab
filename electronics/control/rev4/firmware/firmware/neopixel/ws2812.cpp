/*
 * ws2812.cpp
 *
 *  Created on: Feb 11, 2022
 *      Author: Dustin Lehmann
 */

#include "ws2812.h"

// Global registry (support up to 2 strands; extend if needed)
uint8_t num_neopixel = 0;
WS2812_Strand *neopixel_handler[2] = { nullptr, nullptr };

/* ================================ WS2812_LED ================================ */

WS2812_LED::WS2812_LED() {
}

WS2812_LED::WS2812_LED(uint8_t position) {
	this->strand_position = position;
}

void WS2812_LED::setColor(uint8_t r, uint8_t g, uint8_t b) {
	this->red = r;
	this->green = g;
	this->blue = b;
}

void WS2812_LED::setMode(WS2812_LED_Mode m) {
	if (this->mode == WS2812_LED_MODE_CONTINIOUS
			&& m == WS2812_LED_MODE_BLINK) {
		this->blink();
	}
	this->mode = m;
}

void WS2812_LED::setBlinkConfig(WS2812_blink_config config) {
	this->blink_config = config;
}

void WS2812_LED::setBlinkConfig(uint16_t on_time_ms, int8_t counter) {
	this->blink_config.on_time_ms = on_time_ms;
	this->blink_config.counter = counter;
}

void WS2812_LED::setContiniousOutput(uint8_t output) {
	this->continious_output = output ? 1 : 0;
}

void WS2812_LED::blink() {
	if (this->mode == WS2812_LED_MODE_CONTINIOUS) {
		this->mode = WS2812_LED_MODE_BLINK;
		this->blink_output = !this->continious_output;
		this->blink_counter = this->blink_config.counter * 2;
		this->blinkTimer.reset();
	}
}

void WS2812_LED::update() {
	if (this->mode == WS2812_LED_MODE_CONTINIOUS) {
		this->led_data[0] = this->green * this->continious_output; // G
		this->led_data[1] = this->red * this->continious_output; // R
		this->led_data[2] = this->blue * this->continious_output; // B
	} else { // BLINK
		if (this->blinkTimer >= this->blink_config.on_time_ms) {
			this->blinkTimer.reset();
			this->blink_output = !this->blink_output;

			if (this->blink_counter > 0) {
				this->blink_counter--;
				if (this->blink_counter == 0) {
					this->mode = WS2812_LED_MODE_CONTINIOUS;
					this->blink_output = this->continious_output;
				}
			}
		}

		this->led_data[0] = this->green * this->blink_output; // G
		this->led_data[1] = this->red * this->blink_output; // R
		this->led_data[2] = this->blue * this->blink_output; // B
	}
}

/* ============================== WS2812_Strand ============================== */

WS2812_Strand::WS2812_Strand(TIM_HandleTypeDef *t, uint32_t ch) :
		tim(t), timer_channel(ch), num_led(MAX_LED) {
}

WS2812_Strand::WS2812_Strand(TIM_HandleTypeDef *t, uint32_t ch, uint8_t n) :
		tim(t), timer_channel(ch), num_led(n) {
}

void WS2812_Strand::init() {
	if (num_neopixel
			< (sizeof(neopixel_handler) / sizeof(neopixel_handler[0]))) {
		neopixel_handler[num_neopixel] = this;
		num_neopixel++;

	}



	for (uint8_t i = 0; i < this->num_led; i++) {
		this->led[i].strand_position = i;
	}

	this->datasent = 0;
	this->reset();
}

void WS2812_Strand::update() {
	this->data_index = 0;

	// Preamble: force data line low for ~20 us before first LED bit.
	// This prevents the DMA/timer startup glitch from being interpreted
	// as a '1' bit by the first LED (common green-tint-on-LED-0 issue).
	for (uint16_t i = 0; i < WS2812_PREAMBLE_SLOTS; i++) {
		this->pwm_data[this->data_index++] = 0;
	}

	// Update each LED's internal GRB data
	for (uint8_t i = 0; i < this->num_led; i++) {
		this->led[i].update();
	}

	// Emit GRB -> 24 bits per LED, MSB first
	for (uint8_t i = 0; i < this->num_led; i++) {
		uint32_t color = ((uint32_t) this->led[i].led_data[0] << 16) | // G
				((uint32_t) this->led[i].led_data[1] << 8) | // R
				((uint32_t) this->led[i].led_data[2]);        // B

		for (int b = 23; b >= 0; b--) {
			this->pwm_data[this->data_index++] =
					(color & (1U << b)) ? WS2812_T1H_TICKS : WS2812_T0H_TICKS;
		}
	}

	// Latch/reset: keep line low for >= 50 us; we use 100 slots (~125 us)
	for (uint16_t i = 0; i < WS2812_RESET_SLOTS; i++) {
		this->pwm_data[this->data_index++] = 0;
	}
}

void WS2812_Strand::send() {
	// Start PWM DMA; DMA config should be:
	//   - Mem size: half-word (16-bit) if using uint16_t buffer
	//   - Periph size: word/half-word (HAL reads CCR lower bits)
	//   - Mem increment: enabled; Periph increment: disabled; Circular: disabled
	HAL_TIM_PWM_Start_DMA(this->tim, this->timer_channel,
			(uint32_t*) this->pwm_data,  // HAL API uses uint32_t*
			this->data_index);

	// Busy-wait until DMA completes; (optional: sleep/idle)
	while (this->datasent == 0) {
		__NOP();
	}
	this->datasent = 0;
}

void WS2812_Strand::reset() {
	// Send just a reset tail to ensure LEDs latch previous state and are ready.
	this->data_index = 0;
	for (uint16_t i = 0; i < WS2812_RESET_SLOTS; i++) {
		this->pwm_data[this->data_index++] = 0;
	}
	HAL_TIM_PWM_Start_DMA(this->tim, this->timer_channel,
			(uint32_t*) this->pwm_data, this->data_index);
	// 50+ us low; DMA will finish much sooner, but add a small delay for safety.
	HAL_Delay(2);
}

// HAL callback (C linkage in header). Stop DMA and flag completion.
extern "C" void HAL_TIM_PWM_PulseFinishedCallback(TIM_HandleTypeDef *htim) {
	for (uint8_t i = 0; i < num_neopixel; i++) {
		WS2812_Strand *s = neopixel_handler[i];
		if (s && (htim == s->tim)) {
			HAL_TIM_PWM_Stop_DMA(s->tim, s->timer_channel);
			s->datasent = 1;
		}
	}
}
