/*
 * core_hardware_UART.h
 *
 *  Created on: Jul 7, 2022
 *      Author: Dustin Lehmann
 */

#ifndef CORE_HARDWARE_UART_CORE_HARDWARE_UART_H_
#define CORE_HARDWARE_UART_CORE_HARDWARE_UART_H_

#include "../../core_includes.h"
#include "../../utils/core_utils.h"

#if CORE_CONFIG_USE_UART

enum core_hardware_UART_CB_ID {
	CORE_HARDWARE_UART_CB_RX
};

enum core_hardware_UART_state {
	CORE_HARDWARE_UART_STATE_NONE,
	CORE_HARDWARE_UART_STATE_INIT,
	CORE_HARDWARE_UART_STATE_RUN,
	CORE_HARDWARE_UART_STATE_ERROR,
};

enum core_hardware_UART_mode {
	CORE_HARDWARE_UART_MODE_POLL,
	CORE_HARDWARE_UART_MODE_IT,
	CORE_HARDWARE_UART_MODE_DMA,
};

typedef struct core_hardware_UART_config {
	core_hardware_UART_mode mode = CORE_HARDWARE_UART_MODE_DMA;
	uint8_t cobs_encode_rx = 1;
	uint8_t cobs_encode_tx = 1;
	uint8_t queues = 1;
} core_hardware_UART_config;

typedef struct core_hardware_UART_callbacks_t {
	core_utils_Callback<void, void> rx;
} core_hardware_UART_callbacks_t;

/* =========================================================================== */
void uartRxCmpltDMA_callback(UART_HandleTypeDef *huart, uint16_t size);
extern core_hardware_UART_config core_hardware_uart_std_config;
extern uint8_t num_uarts;
/* =========================================================================== */

/* =========================================================================== */
class UART {
public:
	UART() {

	}

	virtual void rxFunction(uint16_t len) {

	}

	virtual UART_HandleTypeDef* get_huart() {
		return NULL;
	}
};

/* =========================================================================== */
extern UART *uarts[CORE_CONFIG_MAX_UARTS];
/* ============================================================================= */

template<int num_buffers, int size_buffers>
class core_hardware_UART: public UART {
public:

	core_hardware_UART() {

	}

	/* ------------------------------------------------------------------------- */
	void init(UART_HandleTypeDef *huart) {
		this->init(huart, core_hardware_uart_std_config);
	}

	/* ------------------------------------------------------------------------- */
	void init(UART_HandleTypeDef *huart, core_hardware_UART_config config) {

		this->huart = huart;

		this->config = config;
		if (this->huart == NULL) {
			core_ErrorHandler(1);
		}
		HAL_UART_RegisterRxEventCallback(this->huart, uartRxCmpltDMA_callback);
		// __HAL_DMA_DISABLE_IT(this->huart->hdmarx, DMA_IT_HT);
		// Expanded manually to avoid C++20 volatile compound-assignment warning
		static_cast<DMA_Stream_TypeDef*>(this->huart->hdmarx->Instance)->CR =
				static_cast<DMA_Stream_TypeDef*>(this->huart->hdmarx->Instance)->CR & ~(DMA_IT_HT);

		this->state = CORE_HARDWARE_UART_STATE_INIT;

		uarts[num_uarts] = this;
		num_uarts++;
	}
	/* ------------------------------------------------------------------------- */
	void start() {
		if (this->state != CORE_HARDWARE_UART_STATE_INIT) {
			core_ErrorHandler(2);
		}

		if (this->config.mode == CORE_HARDWARE_UART_MODE_DMA) {
			this->startReceiveDMA();
		} else {
			core_ErrorHandler(3);
		}
		this->state = CORE_HARDWARE_UART_STATE_RUN;
	}
	/* ------------------------------------------------------------------------- */
	void reset() {
//		HAL_UART_DMAStop(this->huart);
		HAL_UART_Abort(this->huart);
		this->state = CORE_HARDWARE_UART_STATE_INIT;
		this->start();
	}
//	void stop();
	/* ------------------------------------------------------------------------- */
	void send(uint8_t *data, uint16_t len) {
		if (this->state != CORE_HARDWARE_UART_STATE_RUN) {
			core_ErrorHandler(4);
		}

		if (this->config.mode != CORE_HARDWARE_UART_MODE_DMA
				&& this->config.queues != 1) {
			// TODO Not implemented yet
			core_ErrorHandler(5);
		}

		if (this->config.cobs_encode_tx) {
			uint8_t len_encode = cobsEncode(data, len, this->_tx_buffer.buffer);
			this->_tx_buffer.buffer[len_encode] = 0x00;
			this->_tx_buffer.len = len_encode + 1;
			this->tx_queue.write(&this->_tx_buffer);
		} else {
			this->tx_queue.write(data, (uint8_t) len);
		}
		this->flushTx();
	}

	/* ------------------------------------------------------------------------- */
	void sendRaw(uint8_t *data, uint16_t len) {
		if (this->state != CORE_HARDWARE_UART_STATE_RUN) {
			core_ErrorHandler(4);
		}

		if (this->config.mode != CORE_HARDWARE_UART_MODE_DMA
				&& this->config.queues != 1) {
			// TODO Not implemented yet
			core_ErrorHandler(5);
		}

		this->tx_queue.write(data, (uint8_t) len);
		this->flushTx();
	}

	/* ------------------------------------------------------------------------- */
	int8_t available() {
		return this->rx_queue.available();
	}

	/* ------------------------------------------------------------------------- */
	void startReceiveDMA() {

		if (this->config.queues) {
			HAL_UARTEx_ReceiveToIdle_DMA(this->huart,
					&this->_rx_buffer.buffer[0], size_buffers);
			// __HAL_DMA_DISABLE_IT(this->huart->hdmarx, DMA_IT_HT);
			// Expanded manually to avoid C++20 volatile compound-assignment warning
			static_cast<DMA_Stream_TypeDef*>(this->huart->hdmarx->Instance)->CR =
				static_cast<DMA_Stream_TypeDef*>(this->huart->hdmarx->Instance)->CR & ~(DMA_IT_HT);
		} else {
			core_ErrorHandler(CORE_ERROR_NOT_IMPLEMENTED);
		}
	}

	/* ------------------------------------------------------------------------- */
	void rxFunction(uint16_t len) {
		if (len == 0) {
			return;
		}

		if (this->config.cobs_encode_rx) {
			len = cobsDecodeInPlace(this->_rx_buffer.buffer, len - 1);
		}

		this->_rx_buffer.len = len;
		if (this->config.queues) {
			this->rx_queue.write(&this->_rx_buffer);
		}

		if (this->_callbacks.rx.registered) {
			this->_callbacks.rx.call();
		}

		this->startReceiveDMA();
	}

	/* ------------------------------------------------------------------------- */
	void registerCallback(core_hardware_UART_CB_ID callback_id,
			core_utils_Callback<void, void> callback) {
		if (callback_id == CORE_HARDWARE_UART_CB_RX) {
			this->_callbacks.rx = callback;
		}
	}

	/* ------------------------------------------------------------------------- */
	UART_HandleTypeDef* get_huart() {
		return this->huart;
	}
	/* ------------------------------------------------------------------------- */
	core_hardware_UART_state state = CORE_HARDWARE_UART_STATE_NONE;
	core_hardware_UART_config config;
	UART_HandleTypeDef *huart;
	core_utils_BufferQueue<num_buffers, size_buffers> rx_queue;
	core_utils_BufferQueue<num_buffers, size_buffers> tx_queue;

private:

	core_hardware_UART_callbacks_t _callbacks;
	uint8_t _rx_encode_buf[size_buffers + 10];
	uint8_t _tx_encode_buf[size_buffers + 10];
	core_utils_Buffer<size_buffers> _rx_buffer;
	core_utils_Buffer<size_buffers> _tx_buffer;

	/* ------------------------------------------------------------------------- */
	void flushTx() {
		while (!(this->huart->gState == HAL_UART_STATE_READY)) {

		}
		this->sendNextBuffer();
	}

	/* ------------------------------------------------------------------------- */
	void sendNextBuffer() {
		if (!this->tx_queue.available()) {
			return;
		}

		if (this->huart->gState != HAL_UART_STATE_READY) {
			return;
		}

		uint8_t *buffer = NULL;
		uint8_t len = this->tx_queue.read(&buffer);
		HAL_UART_Transmit_DMA(this->huart, buffer, len);
	}

}
;
#endif



/**
 * @brief Resets the UART peripheral and clears all flags.
 * @param huart Pointer to a UART_HandleTypeDef structure that contains
 *              the configuration information for the specified UART module.
 */


#endif /* CORE_HARDWARE_UART_CORE_HARDWARE_UART_H_ */
