class RecordSettings extends Emitter{

    constructor(container, mainScene, backend, config) {
        super();
        const defaults = {
            id:'',
            cameraSettings: undefined,
            width: 1920.0,
            height: 1080.0,
            fps: 30,
            name: '',
        };
        config = {...defaults, ...config};
        this.config = config;
        this.element = container;
        this.scene = mainScene;
        this.backend = backend;
        this.cameraSettings = config.cameraSettings
        this.fps = config.fps
        this.sampleCount = this.backend.playback.sampleCount;
        this.recording = false

        const panel_record = new Panel(this.container, 'record');
        const recordButton = new Button(panel_record, '<span class="glyphicon glyphicon-record"></span> record',
            {checkedClass:true});

        this.emitPlaybackSample = this._linkPlayback.bind(this);

        recordButton.on('change', function (value) {
            this.recording = value;
            if (value){
                recordButton.text = '<span class="glyphicon glyphicon-record"></span> recording...';
                this.enableRecord();
            }
            else {
                recordButton.text = '<span class="glyphicon glyphicon-record"></span> record';
                this.disableRecord();
            }
        }.bind(this));

    }

    enableRecord() {
        console.log('start recording')
        this.i = this.backend.playback.currentIndex;
        this.backend.playback.pause();
        this.backend.playback.on('recordSample', this.emitPlaybackSample);
        this.timer = setInterval(this.tick.bind(this), 1000.0/this.fps);
        this.recording = true;
    }
    disableRecord(){
        this.recording = false;
        this.backend.playback.off('recordSample', this.emitPlaybackSample);
        clearInterval(this.timer);
        this.backend.playback.play();
    }

    tick() {
        this.recordSample();
        this.i+=1;
        if (this.i >= this.sampleCount) {
            this.recording = false;
            console.log('recording done');
        }
    }

    recordSample() {
        this.sendSample();
        this.makeFrame();
    }

    sendSample() {
        this.backend.playback.currentIndex = this.i;
        this.backend.playback.emit('recordSample');
    }

    makeFrame() {
        // if camera control module is given, recorde different view perspectives camera control enabled,
        // else only record with default camera.
        let msg = {
            ind: this.i,
        };

        if (this.cameraSettings === undefined) {
            BABYLON.Tools.CreateScreenshotUsingRenderTarget(this.scene.engine, this.scene.camera,
                {width: this.config.width, height: this.config.height}, function(data) {
                    msg['default'] = data;
                }.bind(this));
        }
        else{
            // loop through all fixed angles
            for (let i = 0; i < this.cameraSettings.modes.length; i++){
                this.cameraSettings.switchAngle();
                let angleName = this.cameraSettings.angleName;
                BABYLON.Tools.CreateScreenshotUsingRenderTarget(this.scene.engine, this.scene.camera,
                    {width: this.config.width, height: this.config.height}, function(data) {
                        msg[angleName] = data;
                    }.bind(this))
            }
        }
        this.emit(['frame', JSON.stringify(msg)]);
    }

    _linkPlayback() {
        this.backend.playback.sendCurrentSample();
    }
}
