import { EventEmitter } from 'events';

// const WebSocket = require('ws');

export class Websocket extends EventEmitter {
    constructor({host, port, options = {}}) {
        super();

        const default_options = {
            reconnect_pause: 2000, // ms (base delay)
            reconnect_pause_max: 15000, // ms (max delay between reconnects)
            reconnect: true,
        }

        this.options = {
            ...default_options,
            ...(options || {})  // safely spread even if options is undefined
        };

        this.url = `ws://${host}:${port}`;
        this.connected = false;
        this.txQueue = [];
        this._reconnectAttempts = 0;
        this._reconnectTimer = null;
    }

    // -----------------------------------------------------------------------------------------------------------------
    connect() {
        try {
            this.socket = new WebSocket(this.url);
        } catch (e) {
            this._scheduleReconnect();
            return;
        }

        if (!this.socket) {
            this._scheduleReconnect();
            return;
        }

        this.socket.onopen = this.onOpen.bind(this);
        this.socket.onmessage = this.onMessage.bind(this);
        this.socket.onerror = this.onError.bind(this);
        this.socket.onclose = this.onClose.bind(this);
    }

    // -----------------------------------------------------------------------------------------------------------------
    onOpen(open) {
        console.log("Babylon websocket connected!");
        this.connected = true;
        this._reconnectAttempts = 0;
        for (let message of this.txQueue) {
            this.send(message);
        }
        this.emit('connected')
    }

    // -----------------------------------------------------------------------------------------------------------------
    onMessage(message) {
        const msg = JSON.parse(message.data);
        this.emit('message', msg);
    }

    // -----------------------------------------------------------------------------------------------------------------
    onError(err) {
        if (this.listenerCount('error') > 0) {
            this.emit('error', err);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    onClose(close) {
        if (this.connected) {
            console.log("Babylon WebSocket closed");
            this.emit('close', close);
        }
        this.connected = false;
        if (this.options.reconnect) {
            this._scheduleReconnect();
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    _scheduleReconnect() {
        if (this._reconnectTimer) {
            clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }

        this._reconnectAttempts++;
        const baseDelay = this.options.reconnect_pause;
        const maxDelay = this.options.reconnect_pause_max;
        const delay = Math.min(baseDelay * Math.pow(1.5, this._reconnectAttempts - 1), maxDelay);
        const jitter = delay * (0.8 + Math.random() * 0.4);

        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            this.connect();
        }, jitter);
    }

    // -----------------------------------------------------------------------------------------------------------------
    send(message) {
        if (this.connected) {
            this.socket.send(JSON.stringify(message))
        } else {
            this.txQueue.push(message);
        }
    }
}