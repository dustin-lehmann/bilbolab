// less common user interface classes

class DebugLayerCheckbox extends Checkbox {
    constructor(container, scene, options) {
        const defaults = {
            text: 'Debug Layer',
            checked: false,
        };

        options = {...defaults, ...options};

        super(container, options.text, options);

        this.on("change", function(value) {
            if (value) {
                scene.scene.debugLayer.show();
            } else {
                scene.scene.debugLayer.hide();
            }
        });
    }
}

// see examples/oriestimu/
class OriEstImuSliders extends Widget {
    constructor(container) {
        super();

        const tauSliderParams = {
            value: 0,
            min: -2,
            max: 2,
            ticks: [-2, -1, 0, 1, 2],
            ticks_labels: [0.01, 0.1, 1, 10, 100],
            formatter: (val, disabled) => disabled ? val : Math.round(100 * Math.pow(10, val)) / 100,
            step: 0.1,
        };

        const zetaSliderParams = {
            value: 0,
            min: 0,
            max: 10,
            step: 0.1,
            ticks: [0, 1, 5, 10],
            ticks_labels: [0, 1, 5, 10],
            ticks_positions: [0, 10, 5*10, 10*10],
            ticks_snap_bounds: 0.2,
        };

        const ratingSliderParams = {
            value: 1,
            min: 0,
            max: 5,
            step: 0.1,
            ticks: [0, 1, 5],
            ticks_labels: [0, 1, 5],
            ticks_positions: [0, 20, 100],
            ticks_snap_bounds: 0.2,
        };

        const sliderOpts = {
            width: '300px',
            labelWidth: '3em',
            checkbox: true,
        };

        this.sliders = {};
        this.values = {};

        this.sliders.tauAcc = new SliderRow(container, tauSliderParams,
            {...sliderOpts, disabledValue: -1, label: 'τ<sub>acc</sub>'});
        this.sliders.tauMag = new SliderRow(container, tauSliderParams,
            {...sliderOpts, disabledValue: -1, label: 'τ<sub>mag</sub>'});
        this.sliders.zeta = new SliderRow(container, zetaSliderParams,
            {...sliderOpts, disabledValue: 0, label: 'ζ<sub>bias</sub>'});
        this.sliders.accRating = new SliderRow(container, ratingSliderParams,
            {...sliderOpts, disabledValue: 0, label: 'r<sub>acc</sub>'});

        this.sliders.tauAcc.on('change', this.onSliderChange.bind(this));
        this.sliders.tauMag.on('change', this.onSliderChange.bind(this));
        this.sliders.zeta.on('change', this.onSliderChange.bind(this));
        this.sliders.accRating.on('change', this.onSliderChange.bind(this));

        this.onSliderChange();
    }

    onSliderChange() {
        for (let paramName in this.sliders) {
            let val = this.sliders[paramName].value;
            if (paramName === 'tauAcc' || paramName === 'tauMag') {
                val = this.sliders[paramName].checked ? Math.pow(10, val) : -1;
            }
            this.values[paramName] = val;
        }
        this.emit('change', this.value, this);
    }

    get value() {
        return [this.values.tauAcc, this.values.tauMag, this.values.zeta, this.values.accRating];
    }
}

// see examples/euler-angles/
class QuatEulerSliders extends Widget {
    constructor(container, defaultMode=0) {
        super();

        this.quat = new Quaternion(1, 0, 0, 0);

        const angleSliderParams = {
            value: 0,
            min: -180,
            max: 180,
            step: 1,
            ticks: [-180, -90,  0, 90, 180],
            ticks_labels: [-180, -90,  0, 90, 180],
            ticks_snap_bounds: 4,
            precision: 1
        };

        const quatSliderParams = {
            value: 0,
            min: -1,
            max: 1,
            step: 0.01,
            ticks: [-1, 0, 1],
            ticks_labels: [-1, 0, 1],
            ticks_snap_bounds: 0.04,
            precision: 3
        };

        const sliderOpts = {
            width: '300px',
            labelWidth: '2em'
        };

        this.modes = ['Quaternion'];
        for (let inex of ['intrinsic', 'extrinsic']) {
            for (let order of ['zyx', 'zxy', 'yxz', 'yzx', 'xyz', 'zxy', 'zxz', 'zyz', 'yxy', 'yzy', 'xyx', 'xzx']) {
                this.modes.push('Euler ' + order + ' ' + inex);
            }
        }

        this.mode = -1;
        this.mode_dropdown = new Dropdown(container, this.modes, {value: defaultMode});
        this.mode_dropdown.on('change', this.onModeChange.bind(this));

        this.slider_q0 = new SliderRow(container, {...quatSliderParams, value: 1}, {...sliderOpts, label: 'w'});
        this.slider_q1 = new SliderRow(container, quatSliderParams, {...sliderOpts, label: 'x'});
        this.slider_q2 = new SliderRow(container, quatSliderParams, {...sliderOpts, label: 'y'});
        this.slider_q3 = new SliderRow(container, quatSliderParams, {...sliderOpts, label: 'z'});

        this.slider_alpha = new SliderRow(container, angleSliderParams, {...sliderOpts, label: 'α'});
        this.slider_beta = new SliderRow(container, angleSliderParams, {...sliderOpts, label: 'β'});
        this.slider_gamma = new SliderRow(container, angleSliderParams, {...sliderOpts, label: 'γ'});

        this.onModeChange();

        this.slider_q0.on('change', this.updateQuaternion.bind(this));
        this.slider_q1.on('change', this.updateQuaternion.bind(this));
        this.slider_q2.on('change', this.updateQuaternion.bind(this));
        this.slider_q3.on('change', this.updateQuaternion.bind(this));
        this.slider_alpha.on('change', this.updateQuaternion.bind(this));
        this.slider_beta.on('change', this.updateQuaternion.bind(this));
        this.slider_gamma.on('change', this.updateQuaternion.bind(this));

    }

    onModeChange() {
        const mode = this.mode_dropdown.value;
        if (mode === this.mode)
            return;

        if (mode === 0) {
            this.slider_q0.show();
            this.slider_q1.show();
            this.slider_q2.show();
            this.slider_q3.show();
            this.slider_alpha.hide();
            this.slider_beta.hide();
            this.slider_gamma.hide();

            this.slider_q0.value = this.quat.w;
            this.slider_q1.value = this.quat.x;
            this.slider_q2.value = this.quat.y;
            this.slider_q3.value = this.quat.z;
        } else {
            this.slider_q0.hide();
            this.slider_q1.hide();
            this.slider_q2.hide();
            this.slider_q3.hide();
            this.slider_alpha.show();
            this.slider_beta.show();
            this.slider_gamma.show();

            const modeStr = this.modes[mode].split(' ');
            const angles = this.quat.eulerAngles(modeStr[1], modeStr[2] === 'intrinsic');
            this.slider_alpha.value = rad2deg(angles[0]);
            this.slider_beta.value = rad2deg(angles[1]);
            this.slider_gamma.value = rad2deg(angles[2]);
        }

        this.mode = mode;
        this.updateQuaternion();
    }

    updateQuaternion() {
        let quat;
        if (this.mode === 0) {
            // quaternion
            quat = new Quaternion(this.slider_q0.value, this.slider_q1.value, this.slider_q2.value, this.slider_q3.value);

            // set value labels next to slider to normalized values
            this.slider_q0.setCustomValueLabel(Math.round(100.0*quat.w)/100.0);
            this.slider_q1.setCustomValueLabel(Math.round(100.0*quat.x)/100.0);
            this.slider_q2.setCustomValueLabel(Math.round(100.0*quat.y)/100.0);
            this.slider_q3.setCustomValueLabel(Math.round(100.0*quat.z)/100.0);
        } else {
            // euler angles
            const modeStr = this.modes[this.mode].split(' ');
            console.assert(modeStr[0] === 'Euler', modeStr);
            console.assert(modeStr[1].length === 3, modeStr);
            console.assert(modeStr[2] === 'intrinsic' || modeStr[2] === 'extrinsic', modeStr);

            const angles = [deg2rad(this.slider_alpha.value), deg2rad(this.slider_beta.value), deg2rad(this.slider_gamma.value)];
            quat = Quaternion.fromEulerAngles(angles, modeStr[1], modeStr[2] === 'intrinsic');
        }

        this.quat = quat;
        this.emit('change', quat, this);
    }

    get value() {
        return this.quat;
    }
}

class LanguageSelector extends Box {
    constructor(container) {
        super(container, {});
        const div = $('<div></div>').css('flex-grow', '1');
        insertDOM(this, div);

        this.localeNames = { // not translated on purpose!
            'en': 'English',
            'de': 'Deutsch',
        };

        this.locales = ['en'];
        for (let locale in tr.db)
            this.locales.push(locale);
        this.localeNames = this.locales.map(this.localeName.bind(this));

        this.dropdown = new Dropdown(div, this.localeNames, {value: this.locales.indexOf(tr.locale)});
        this.listButton = new Button(this, '<span class="glyphicon glyphicon-list"></span>', {block: false});
        this.refreshButton = new Button(this, '<span class="glyphicon glyphicon-refresh"></span>', {block: false});

        this.dropdown.on('change', index => tr.setLocale(this.locales[index]));
        this.listButton.on('change', this.showMissingEntries.bind(this));
        this.refreshButton.on('change', () => location.reload());
    }

    localeName(locale) {
        if (this.localeNames[locale])
            return this.localeNames[locale] + ' (' + locale + ')';
        return locale;
    }

    showMissingEntries() {
        console.log('add this to tr.db:\n'+JSON.stringify(tr.missing, null, 4));
        const N = Object.keys(tr.missing).length;
        if (N) {
            alert('There are ' + N + ' missing entries. Open console for a template to copy!');
        } else {
            alert('No missing entries!')
        }
    }
}

class FileDropPanel extends Panel {
    constructor(container, headerText, options) {
        const defaults = {
            collapsible: true,
            collapsed: false,
            id: '',
            content: '',
            spacing: '10px',
            label: 'Drag file here or use file selector.',
            fileSelector: true,
        };
        options = {...defaults, ...options};
        super(container, headerText, options);

        this.panel.on('dragover', this._dragoverHandler.bind(this));
        this.panel.on('dragleave', this._dragleaveHandler.bind(this));
        this.panel.on('drop', this._dropHandler.bind(this));

        this.label = null;
        if (options.label) {
            this.label = new Label(this, options.label);
        }

        this.selector = null;
        if (options.fileSelector) {
            this.selector = new FileSelector(this);
            this.selector.on('file', this._onFileSelected.bind(this));
        }
    }

    _dropHandler(event){
        event.preventDefault();
        if (event.originalEvent.dataTransfer.items) {
            // Use DataTransferItemList interface to access the file(s)
            for (let i = 0; i < event.originalEvent.dataTransfer.items.length; i++) {
                // If dropped items aren't files, reject them
                if (event.originalEvent.dataTransfer.items[i].kind === 'file') {
                    this.file = event.originalEvent.dataTransfer.items[i].getAsFile();
                    this.URL = window.URL.createObjectURL(this.file);
                }
                if (this.selector) {
                    this.selector.setText(this.file.name);
                }
                this.emit('file', this.file, this.URL);
            }
        } else {
            // Use DataTransfer interface to access the file(s)
            for (let i = 0; i < event.originalEvent.dataTransfer.files.length; i++) {
                console.log('TODO: file[' + i + '].name = ' + event.originalEvent.dataTransfer.files[i].name);
            }
        }
        // Pass event to removeDragData for cleanup
        this._removeDragData(event);
        this.panel.removeClass('panel-success').addClass('panel-default');
    }

    _removeDragData(ev) {
        if (ev.originalEvent.dataTransfer.items) {
            ev.originalEvent.dataTransfer.items.clear();
        } else {
            ev.originalEvent.dataTransfer.clearData();
        }
    }

    _dragoverHandler(event){
        event.preventDefault();
        this.panel.removeClass('panel-default').addClass('panel-success');
    }
    _dragleaveHandler(event){
        event.preventDefault();
        this.panel.removeClass('panel-success').addClass('panel-default');
    }

    _onFileSelected(file, url) {
        this.file = file;
        this.URL = url;
        this.emit('file', this.file, this.URL);
    }

    getFile() {
        return this.file;
    }
}


class FileSelector extends Widget {
    constructor(container, options) {
        const defaults = {
            id: '',
            buttonText: 'Browse&hellip;',
            placeholder: "No file selected"
        };
        options = {...defaults, ...options};
        super(container, options);

        this.button = $('<span>', {class: 'btn btn-primary'}).append(options.buttonText);
        this.label = $('<input>', {type: 'text', placeholder: options.placeholder, class: 'form-control', width: '100%', readonly: true});
        this.input = $('<input>', {type: 'file'});
        this.input.css('display', 'none');
        this.label.css('background', 'white');

        this.contents =  $('<div>', {class:'input-group', width: '100%'});
        const buttonSpan = $('<span>', {class: 'input-group-btn'});
        buttonSpan.append(this.button);
        this.contents.append(buttonSpan);
        this.contents.append(this.label);
        this.contents.append(this.input);

        this.button.on('click', () => this.input.trigger('click'));

        insertDOM(container, this.contents);

        this.input.on('change',this._fileButtonChange.bind(this));
        this.input.on('fileselect',this._fileSelectHandler.bind(this));
    }

    setText(text) {
        this.label.val(text);
    }

    _fileButtonChange(event) {
        const input = this.input;
        const numFiles = input.get(0).files ? input.get(0).files.length : 1;

        this.file = input.get(0).files;
        this.file = this.file[0];
        this.URL = window.URL.createObjectURL(this.file);

        const label = input.val().replace(/\\/g, '/').replace(/.*\//, '');
        this.input.trigger('fileselect', [numFiles, label]);
    }

    _fileSelectHandler(event, numFiles, label) {
        const log = numFiles > 1 ? numFiles + ' files selected' : label;
        this.setText(log);
        this.emit('file', this.file, this.URL);
    }
}


class CameraSettings {

    constructor(container, mainScene, chain, config) {
        const defaults = {
            initHeading: 166,
            target: null,
            modes: ['Free', 'Front', 'Top', 'Right', 'Left', 'Back']
        };
        config = {...defaults, ...config};
        let sliderOpts = {
            width: '300px',
            labelWidth: '2em'
        };
        const alphaSliderParams = {
            value: 0,
            min: -180,
            max: 180,
            step: 1,
            ticks: [-180, -90,  0, 90, 180],
            ticks_labels: [-180, -90,  0, 90, 180],
            ticks_snap_bounds: 4,
            precision: 1
        };
        const betaSliderParams = {
            value: 90,
            min: 0,
            max: 180,
            step: 1,
            ticks: [0, 90, 180],
            ticks_labels: [0, 90, 180],
            ticks_snap_bounds: 4,
            precision: 1
        }
        const FOVSliderParams = {
            value: 0,
            min: -1,
            max: 1,
            step: 0.01,
            ticks: [-1, 0, 1],
            ticks_labels: [-1, 0, 1],
            ticks_snap_bounds: 0.04,
            precision: 3
        };
        sliderOpts = {...sliderOpts, ...config};

        this.container = container;
        this.scene = mainScene;
        this.config = config;
        this.chain = chain;

        this.modes = this.config.modes;
        this.mode = this.config.modes[0];
        this._target = this.config.target;

        this.panelCamera = new Panel(this.container, 'Camera');

        this.dropdown = new Dropdown(this.panelCamera, ['regular', 'advance'])
        this.cameraOffsetAlpha =  new SliderRow(this.panelCamera, alphaSliderParams, {...sliderOpts, label: 'α'});
        this.cameraOffsetBeta = new SliderRow(this.panelCamera, betaSliderParams, {...sliderOpts, label: 'β'});
        this.cameraFOV = new SliderRow(this.panelCamera, FOVSliderParams, {...sliderOpts, label: 'FOV'});
        this.sliders = [];
        this.sliders.push(this.cameraOffsetAlpha, this.cameraOffsetBeta, this.cameraFOV);

        this.cameraButton = [];
        for (let i = 0; i < this.modes.length; i++) {
            this.cameraButton.push(new Button(this.panelCamera, String(this.modes[i]),
                {block: false, defaultClass: 'btn-default'}))
        }

        this.button = new Button(this.panelCamera, 'Fix on Segment', {checkedClass:true});

        this.setUpSlidersButtons();

    }

    setUpSlidersButtons() {

        this.target = this.chain.operatingSeg;
        this.chain.on('change', function () {
            this.target = this.chain.operatingSeg;
        }.bind(this));

        this.dropdown.on('change', function (val) {
            if (val === 0) {
                this.hideSliders();
            }else if (val === 1) {
                this.showSliders();
            }
        }.bind(this));

        this.initCameraOffsetAlpha = -this.config.initHeading;
        this.initCameraOffsetBeta = 0;
        this.FOV = 1.3;
        this.onSliderChange();

        this.cameraOffsetAlpha.on('change', this.onSliderChange.bind(this));
        this.cameraOffsetBeta.on('change', this.onSliderChange.bind(this));
        this.cameraFOV.on('change', this.onSliderChange.bind(this));

        this.hideSliders();

        for (let i = 0; i < this.modes.length; i++) {
            this.cameraButton[i].on('change', function (val) {
                if (val === 1) {
                    this.onModeChange(this.cameraButton[i].text);
                }
            }.bind(this));
        }

        this.button.on('change', function (val){
            if (val) {
                if (this.target === null) {
                    this.button.text = 'No Segment Selected!';
                }
                else {
                    this.scene.camera.parent = this.scene.chain.segments[this.target].box;
                    this.button.text = 'Fixed Camera: ' + String(this.target);
                }
            } else {
                this.scene.camera.parent = null;
                this.button.text = 'Free Camera';
            }
        }.bind(this))
        this.updateCamera();
    }

    showSliders() {
        for (let i = 0; i < this.sliders.length; i++) {
            this.sliders[i].show();
        }
    }

    hideSliders() {
        for (let i = 0; i < this.sliders.length; i++) {
            this.sliders[i].hide();
        }
    }


    onModeChange(val) {
        this.mode = val;
        // reset all angle buttons except triggered one
        for (let i = 0; i < this.cameraButton.length; i++) {
            if (this.cameraButton[i].text !== val) {
                this.cameraButton[i].value = 0;
            }
        }
        this.updateCamera();
    }

    onSliderChange() {
        this.cameraAlpha = deg2rad(this.initCameraOffsetAlpha + this.cameraOffsetAlpha.value);
        this.cameraBeta = deg2rad(this.initCameraOffsetBeta + this.cameraOffsetBeta.value);
        this.scene.camera.fov = this.FOV + this.cameraFOV.value
        this.updateCamera();
    }

    // overwrite this function for different mode(view direction)
    updateCamera() {
        if (this.mode === 'Front') { // Front
            this.scene.camera.alpha = this.cameraAlpha;
            this.scene.camera.beta = this.cameraBeta;
        } else if  (this.mode === 'Top') { //top
            this.scene.camera.alpha = this.cameraAlpha;
            this.scene.camera.beta = this.cameraBeta-Math.PI/2;
        }
        else if  (this.mode === 'Right') { //Right
            this.scene.camera.alpha = this.cameraAlpha + Math.PI/2;
            this.scene.camera.beta = this.cameraBeta;
        }
        else if  (this.mode === 'Left') { // Left
            this.scene.camera.alpha = this.cameraAlpha - Math.PI/2;
            this.scene.camera.beta = this.cameraBeta;
        }
        else if (this.mode === 'Back') { // Back
            this.scene.camera.alpha = this.cameraAlpha + Math.PI;
            this.scene.camera.beta = this.cameraBeta;
        } else {
            this.scene.camera.alpha = this.cameraAlpha;
            this.scene.camera.beta = this.cameraBeta;
        }
    }

    get target() {
        return this._target
    }

    set target(targetName) {
        this._target = targetName
    }

    get Alpha() {
        return this.scene.camera.alpha
    }

    get Beta() {
        return this.scene.camera.beta
    }

    get angleName() {
        return this.mode
    }

    // switch to next angle
    switchAngle() {
        const angleNum = this.modes.indexOf(this.mode)
        this.cameraButton[(angleNum+1)%this.modes.length]._onClick();
    }
}
