"use strict";

class Backend extends Emitter {
    constructor(options) {
        super();

        const defaults = {
            ws: 'auto',
            defaultConfig: {},
            autoPlay: true,
            webSocketDataSourceOptions: {},
            loadJsonFiles: true,
            jsonDataSourceOptions: {},
        };
        options = {...defaults, ...options};
        this.options = options;


        let url = options.ws;
        if (url === 'auto') {
            const urlParams = new URLSearchParams(window.location.search);
            url =  urlParams.get('ws') ?? 'local';
        }
        if (url === 'local') {
            url = ((window.location.protocol === 'https:') ? 'wss://' : 'ws://') + window.location.host + '/ws';
        }
        console.log('url', url)
        this.ws = new WebSocketDataSource(url, {...options.webSocketDataSourceOptions, open: false, reconnect: false});
        this.playback = new JsonDataSource(undefined, options.jsonDataSourceOptions);
        this.lastSample = undefined;

        this.ws.on('sample', function(sample) {
            if (this.mode !== 'online') {
                if (!this.playback.paused) {
                    this.playback.pause();
                }
                this.mode = 'online';
                this.emit('modeChanged', this.mode);
            }
            this.lastSample = this.processSample(sample);
            this.emit('sample', this.lastSample);
        }.bind(this));

        this.playback.on('sample', function(sample) {
            if (this.mode !== 'playback') {
                this.mode = 'playback';
                this.emit('modeChanged', this.mode);
            }
            this.lastSample = this.processSample(sample);
            this.emit('sample', this.lastSample);
        }.bind(this));

        this.ws.on('command', function(command) {
            if (command[0] === 'setData') {
                this.playback.data = command[1];
                this.emit('setData', command[1]);
                if (this.options.autoPlay && command[1]) {
                    this.playback.play();
                }
            } else if (command[0] === 'setConfig') {
                this.emit('setConfig', command[1]);
            } else {
                this.emit('command', command);
            }
        }.bind(this));

        this._mode = 'init';
        this._configLoaded = false;
        this._dataLoaded = false;
        this.config = undefined;
        this._data = undefined;

        if (options.loadJsonFiles) {
            $.getJSON('./config.json', function (data) {
                console.log('loaded ./config.json', data);
                this.config = data;
            }.bind(this))
            .fail(function (obj) {
                console.log('failed to load ./config.json', obj);
            }.bind(this))
            .always(function () {
                this._configLoaded = true;
                this._init()
            }.bind(this))

            $.getJSON('./data.json', function (data) {
                console.log('loaded ./data.json', data);
                this._data = data;
            }.bind(this))
            .fail(function (obj) {
                console.log('failed to load ./data.json', obj);
            }.bind(this))
            .always(function () {
                this._dataLoaded = true;
                this._init()
            }.bind(this))
        } else {
            this._configLoaded = true;
            this._dataLoaded = true;
            this._init()
        }
    }

    _init() {
        if (!this._configLoaded || !this._dataLoaded) {
            return;
        }

        if (this._data && this._data.config) {  // config stored in data.config overrides config.json
            this.config = this._data.config;
        }
        if (this.config === undefined) {
            this.config = this.options.defaultConfig;
        }
        if (this.config.autoPlay !== undefined) { // autoPlay from config.json overrides autoPlay from constructor
            this.options.autoPlay = this.config.autoPlay;
        }

        this.playback.data = this._data;
        this.emit('setConfig', this.config);
        this.emit('setData', this._data);

        if (this.options.autoPlay && this._data) {
            this.playback.play();
        }

        // TODO: check if config.ws is set
        this.ws.openSocket();
    }

    addSink(sink) { // legacy message, use on('sample', callback) instead
        console.assert(sink.onSample !== undefined, 'sink.onSample() is undefined');
        this.on('sample', sink.onSample.bind(sink));
    }

    // parameterSource can be one of the following:
    // callable, e.g. dataSource.addParameter(() => {myObj.getParam()}, 'myparam')
    // object that has a value property (like many Widgets), e.g. dataSource.addParameter(checkbox, 'enabled')
    // [object, propertyName], e.g. dataSource.addParameter([myObj, 'param'], 'myparam')
    addParameter(parameterSource, parameterName) {
        this.ws.parameters[parameterName] = parameterSource;
    }

    // replace this function to modify each sample before it is being sent out
    processSample(sample) {
        return sample;
    }

    sendMessage(message) {
        this.ws.sendMessage(message);
    }

    sendCommand(command) {
        console.log('sending command', command);
        this.sendMessage(command);
    }

    sendParams(params) {
        this.sendMessage(params);
    }
}

class WebSocketDataSource extends Emitter {
    constructor(url, options) {
        super();
        this.url = url;

        const defaults = {
            sendParamsOnReceivedMsg: true,
            sendParamsInteval: undefined, // TO IMPLEMENT, interval in ms
            open: true,
            reconnect: true,
        };
        options = {...defaults, ...options};
        this.options = options;

        this.sendParamsOnReceivedMsg = options.sendParamsOnReceivedMsg;

        this.open = false;
        this.sendQueue = [];
        this.parameters = {};

        if (options.open) {
            this.openSocket();
        }
    }

    openSocket() {
        this.socket = new WebSocket(this.url);
        if (!this.socket) {
            alert('Opening WebSocket failed!');
        }

        this.socket.onopen = this.onOpen.bind(this);
        this.socket.onmessage = this.onMessage.bind(this);
        this.socket.onerror = this.onError.bind(this);
        this.socket.onclose = this.onClose.bind(this);
    }

    addSink(sink) {
        console.assert(sink.onSample !== undefined, 'sink.onSample() is undefined');
        this.on('sample', sink.onSample.bind(sink));
    }

    onOpen(open) {
        console.log("WebSocket has been opened", open, this);
        this.open = true;
        for (let message of this.sendQueue) {
            this.socket.send(message);
        }
        this.sendQueue = [];
        this.emit('open');
    };

    onMessage(message) {
        // console.log(message.data);
        const msg = JSON.parse(message.data);
        if (Array.isArray(msg)) {
            this.emit('command', msg);
            return;
        }

        this.lastSample = this.processSample(msg);

        this.emit('sample', this.lastSample);

        if (this.sendParamsOnReceivedMsg && Object.keys(this.parameters).length) {
            let params = {};
            for (let parameterName in this.parameters) {
                const source = this.parameters[parameterName];
                let val = undefined;
                if (source instanceof Function) {
                    val = source();
                } else if (source instanceof Array) {
                    console.assert(source.length === 2);
                    val = source[0][source[1]];
                } else {
                    val = source.value;
                }
                params[parameterName] = val;
            }
            this.lastParams = params;
            // console.log(JSON.stringify(params));
            this.socket.send(JSON.stringify(params));
        }
    }

    onError(error) {
        console.log("WebSocket error:", error, this);
        this.emit('error', error);
    }

    onClose(close) {
        console.log("WebSocket has been closed", close, this);
        this.open = false;
        this.emit('close', close);
        if (this.options.reconnect)
            this.openSocket();
    }

    // parameterSource can be one of the following:
    // callable, e.g. dataSource.addParameter(() => {myObj.getParam()}, 'myparam')
    // object that has a value property (like many Widgets), e.g. dataSource.addParameter(checkbox, 'enabled')
    // [object, propertyName], e.g. dataSource.addParameter([myObj, 'param'], 'myparam')
    addParameter(parameterSource, parameterName) {
        this.parameters[parameterName] = parameterSource;
    }

    processSample(sample) {
        return sample;
    }

    sendMessage(message) {
        const msg = JSON.stringify(message);
        if (!this.open) {
            this.sendQueue.push(msg);
        } else {
            this.socket.send(msg);
        }
    }
}


class JsonDataSource extends Emitter {
    constructor(url, options) {
        super();

        const defaults = {
            fps: 30,
            speed: 1,
            reverse: false,
            loop: false,
        };
        options = {...defaults, ...options};

        this._data = undefined;
        this._paused = true;
        this._timer = undefined;
        this._currentTime = 0;
        this._currentIndex = -1;
        this._lastTick = 0;
        this._sampleCount = 0;
        this._keys = [];
        this.lastSample = undefined;

        this.fps = options.fps;
        this.speed = options.speed;
        this.reverse = options.reverse;
        this.loop = options.loop;

        this.url = url;
    }

    get fps() {
        return this._fps;
    }

    set fps(fps) {
        if (!this._paused) {
            this.pause();
            this.play();
        }
        this._fps = fps;
    }

    get url() {
        return this._url;
    }

    set url(url) {
        this._url = url;
        if (url) {
            $.getJSON(url, this._dataLoaded.bind(this));
        } else {
            this.data = undefined;
        }
    }

    get data() {
        return this._data;
    }

    set data(data) {
        this._data = data;
        this._sampleCount = (this.data && this.data.t) ? this.data.t.length : 0;  // use this.data to allow overriding of getter!
        this._currentIndex = -1;
        this._currentTime = 0;
        this._keys = JsonDataSource._findKeys(this.data, this._sampleCount, '');
        this.emit('ready');
    }

    isLoaded() {
        return Boolean(this.data);
    }

    get sampleCount() {
        return this._sampleCount;
    }

    get currentIndex() {
        return this._currentIndex;
    }

    set currentIndex(i) {
        const index = Math.max(0, Math.min(i, this.sampleCount));
        if (index === this._currentIndex) {
            return;
        }
        this._currentIndex = index;
        this.sendCurrentSample();
    }

    get currentTime() {
        return this._currentTime;
    }

    set currentTime(t) {
        const dataT = this.data.t;
        const N = this.sampleCount;
        let i = this.currentIndex;

        while (i+1 < N && dataT[i+1] < t + 1e-6) {
            i++;
        }
        while (i > 0 && dataT[i] > t + 1e-6) {
            i--;
        }

        this.currentIndex = i;
        this._currentTime = t;
    }

    static fileExists(url) {
        if(url){
            const req = new XMLHttpRequest();
            req.open('HEAD', url, false);
            req.send();
            return req.status === 200;
        } else {
            return false;
        }
    }

    play() {
        clearInterval(this._timer);
        this._timer = setInterval(this._tick.bind(this), 1000.0/this.fps);
        this._lastTick = Date.now();
        this._paused = false;
        this.emit('play');
    }

    pause() {
        clearInterval(this._timer);
        this._paused = true;
        this.emit('pause');
    }

    get paused() {
        return this._paused;
    }

    stop() {
        clearInterval(this._timer);
        this._paused = true;
        this._currentIndex = -1;
        this._currentTime = 0;
        this.emit('stop');
    }


    addSink(sink) {
        console.assert(sink.onSample !== undefined, 'sink.onSample() is undefined');
        this.on('sample', sink.onSample.bind(sink));
    }

    _dataLoaded(data) {
        console.log('json loaded:', data, this);
        this.data = data;
    }

    _tick() {
        const deltaT = (this.reverse ? -1 : 1) * this.speed * (Date.now() - this._lastTick)/1000.0;
        // console.log('deltaT', deltaT);
        this._lastTick = Date.now();

        this.currentTime = this.currentTime + deltaT;

        if (this.currentIndex >= this.sampleCount-1) {
            console.log('reached end');
            this.stop();
            if (this.loop) {
                this.play();
            }
        }
    }

    sendCurrentSample() {
        const i = this.currentIndex;
        const data = this.data;

        let sample = {
            ind: i,
            length: this.sampleCount,
        };

        for (let key of this._keys) {
            _.set(sample, key, _.get(data, key)[i]);
        }

        this.lastSample = sample;
        this._currentTime = sample.t;
        this.emit('sample', sample);
    }

    static _findKeys(data, N, prefix) {
        if (N === 0) {
            return [];
        }
        const keys = [];

        _.forOwn(data, function(v, k) {
            if(_.isArray(v) && v.length === N) {
                keys.push(prefix + k);
            } else if(_.isPlainObject(v)) {
                keys.push(...JsonDataSource._findKeys(v, N, prefix + k + '.'));
            }
        });

        return keys;
    }
}
