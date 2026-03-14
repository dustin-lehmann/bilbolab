/*
 * apa102.h
 *
 *  Created on: Mar 13, 2026
 *      Author: lehmann
 */

#ifndef HARDWARE_APA102_APA102_H_
#define HARDWARE_APA102_APA102_H_

#include "stm32h7xx_hal.h"
#include <cstring>

/*
 * ============================================================================
 * SPI Configuration for APA102
 * ============================================================================
 *
 * The APA102 is a clock+data LED strip (SPI-like protocol). Only MOSI and SCK
 * are needed — MISO is unused. Configure the SPI peripheral as follows:
 *
 * STM32CubeMX / CubeIDE settings:
 *   - Mode:                   Transmit Only Master
 *   - Frame Format:           Motorola
 *   - Data Size:              8 bits
 *   - First Bit:              MSB First
 *   - Clock Polarity (CPOL):  Low  (idle low)
 *   - Clock Phase (CPHA):     1 Edge (sample on first/rising edge)
 *   - NSS Signal:             Software (no chip select needed)
 *   - Baud Rate Prescaler:    Choose for ≤ 10 MHz (e.g. prescaler 16 on
 *                              a 100 MHz APB → 6.25 MHz). APA102 tolerates
 *                              up to ~20 MHz but 1–10 MHz is safe.
 *   - CRC Calculation:        Disabled
 *   - DMA:                    Optional — enable TX DMA for non-blocking
 *                              updates on longer strips (> ~30 LEDs).
 *
 * Only two pins are required:
 *   - SPI_SCK  → APA102 CKI (Clock)
 *   - SPI_MOSI → APA102 SDI (Data)
 *
 * GPIO settings for both pins:
 *   - Mode:        Alternate Function Push-Pull
 *   - Pull:        No Pull
 *   - Speed:       High or Very High
 *
 * ============================================================================
 */

#define APA102_MAX_LEDS 64

struct apa102_color_t {
	uint8_t r;
	uint8_t g;
	uint8_t b;
};

struct apa102_config_t {
	SPI_HandleTypeDef *hspi;
	uint16_t num_leds;
};

class APA102 {
public:
	APA102();

	void init(apa102_config_t config);

	void setColor(uint16_t index, uint8_t r, uint8_t g, uint8_t b);
	void setColor(uint16_t index, apa102_color_t color);
	void setAllColors(uint8_t r, uint8_t g, uint8_t b);
	void setAllColors(apa102_color_t color);

	void setBrightness(uint8_t brightness);
	void setBrightness(uint16_t index, uint8_t brightness);

	void clear();
	void update();

	apa102_config_t config;

private:
	// Per-LED brightness (5-bit, 0–31). Default 31 (max).
	uint8_t _brightness[APA102_MAX_LEDS];
	apa102_color_t _colors[APA102_MAX_LEDS];

	// SPI frame buffer: 4 start + 4*N led + end frames
	// End frame: ceil(num_leds / 2 / 8) bytes of 0xFF, at least 4
	uint8_t _tx_buf[4 + APA102_MAX_LEDS * 4 + 8];
	uint16_t _frame_len;

	void _buildFrame();
};

#endif /* HARDWARE_APA102_APA102_H_ */
