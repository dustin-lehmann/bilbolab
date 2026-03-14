/* SegmentBox builds a 3D Box that can be moved and tilted */
class SegmentBox {
    constructor(scene, options) {
        this.scene = scene;
        const texture = {
            FLU: 'lib/textures.json/texture_imu.png', // set to false to use colors on top and front side
            RFU: 'lib/textures.json/texture_imu_smartphone.png',
        };
        const axis = {
            FLU:{x:[1, 0, 0],
                y:[0, 0, 1],
                z:[0, 1, 0]},
            RFU:{x:[0, 0, 1],
                y:[-1, 0, 0],
                z:[0, 1, 0], },
        }
        const defaults = {
            color: COLORS.C1,
            scale: 1.0,
            opacity: 1,
            zOffset: 0,
            face: 5,
            // width, depth,  height
            dimensions:[5.5/2,  3.5/2, 1.3/2],
            // imu box default settings
            showAxis: false,
            showLed: false,
            type: 'box', // set to 'imu' to render imu box
            coordinates: 'FLU',
            axis: undefined,
            texture: undefined,
            qSeg2Bone: new Quaternion(1, 0, 0, 0),
        };

        options = {...defaults, ...options};

        this.options = options;
        this.dimensions = this.options.dimensions;

        const mat = new BABYLON.StandardMaterial('mat', scene);
        const boxOpts = {};
        // set texture UV or faceColors
        if (this.options.type === 'box') {
            let x = this.dimensions[0], y = this.dimensions[2], z = this.dimensions[1]

            const face = options.face;
            const faceColors = new Array(6);
            faceColors[face] = options.color; // front
            boxOpts.faceColors = faceColors;
            boxOpts.width = x * options.scale;
            boxOpts.height = z * options.scale;
            boxOpts.depth = y * options.scale;
        }
        else if (this.options.type === 'imu') {
            // keep dimension coincident with texture
            let x = this.dimensions[0], y = this.dimensions[1], z = this.dimensions[2]
            boxOpts.width = x * options.scale;
            boxOpts.height = z * options.scale;
            boxOpts.depth = y * options.scale;

            if (options.texture === undefined) {
                options.texture = _.get(texture, options.coordinates, 'lib/textures.json/texture_imu.png');
            }
            if (options.axis === undefined) {
                options.axis = _.get(axis, options.coordinates, axis.FLU);
            }

            if (options.texture) {

                mat.diffuseTexture = new BABYLON.Texture(options.texture, scene);

                const width = Math.max(4 + y + 2 * z, 3 + y + x);
                const height = 3 + 2 * x;
                boxOpts.faceUV = [
                    new BABYLON.Vector4((2 + y) / width, (2 + y + z) / height, (2 + y + x) / width, (2 + y) / height), // right (-y)
                    new BABYLON.Vector4((2 + y + x) / width, (3 + y + z) / height, (2 + y) / width, (3 + y + 2 * z) / height), // left (+y)
                    new BABYLON.Vector4((2 + y) / width, (1 + y) / height, (2 + y + z) / width, 1 / height), // front (+x)
                    new BABYLON.Vector4((3 + y + z) / width, (1 + y) / height, (3 + y + 2 * z) / width, 1 / height), // back (-x)
                    new BABYLON.Vector4(1 / width, (2 + 2 * x) / height, (1 + y) / width, (2 + x) / height), // top (+z)
                    new BABYLON.Vector4((1 + y) / width, 1 / height, 1 / width, (1 + x) / height), // bottom (-z)
                ];
            }

            options.qSeg2Bone = new Quaternion(1, 1, 0, 0);
        }
        else {
            console.log('Wrong box type!')
        }

        this.box = BABYLON.MeshBuilder.CreateBox('box', boxOpts, scene);
        this.box.material = mat;

        if (this.options.type === 'box') {
            this.highlight(true);
            this.box.material.alpha = options.opacity;
            this.box.material.zOffset = options.zOffset;
            this.box.enableEdgesRendering();
        }
        else {
            this.highlight(false);
            let x = this.dimensions[0], y = this.dimensions[1], z = this.dimensions[2]
            if (options.showLed) {
                this.led = BABYLON.MeshBuilder.CreateSphere('led', {}, scene);
                this.led.parent = this.box;
                const ledScale = x * y * z * 0.01 * options.scale;
                this.led.scaling = new BABYLON.Vector3(ledScale, ledScale, ledScale);
                this.led.position.x = -0.8 * x / 2 * options.scale;
                this.led.position.y = z / 2 * options.scale;
                this.led.position.z = 0.75 * y / 2 * options.scale;
                this.led.material = new BABYLON.StandardMaterial('ledmaterial', scene);
                this.led.material.diffuseColor = COLORS.grey;
                this.ledOn = false;
                this.defaultEmissiveColor = this.led.material.emissiveColor;
                setInterval(this._toggleLed.bind(this), 500);
            }
            if (options.showAxis) {
                const axisLen = Math.max(x, y, z) * 1.5 * options.scale;
                this.x_axis = new Arrow(this.scene, {
                    parent: this.box,
                    color: COLORS.C3,
                    vector: options.axis.x.map((e) => e * axisLen),
                    origin: options.axis.x.map((e) => e * -axisLen/2),
                    diameter: 0.1 * options.scale
                });
                this.y_axis = new Arrow(this.scene, {
                    parent: this.box,
                    color: COLORS.C2,
                    vector: options.axis.y.map((e) => e * -axisLen),
                    origin: options.axis.y.map((e) => e * axisLen/2),
                    diameter: 0.1 * options.scale
                });
                this.z_axis = new Arrow(this.scene, {
                    parent: this.box,
                    color: COLORS.C0,
                    vector: options.axis.z.map((e) => e * axisLen),
                    origin: options.axis.z.map((e) => e * -axisLen/2),
                    diameter: 0.1 * options.scale
                });
            }
        }
        this.q_EImu2EB = new Quaternion(1, -1, 0, 0); // Constant value. Do not change! This defined the difference between "our" coordinates and the weird convention Babylon is using
        // sets the anchor in the middle of the box. This is the point of rotation and movement
        this._qSeg2Bone = options.qSeg2Bone
        this.anchor = [0, 0, 0];
        this.position = [0, 0, 0]; // position of the block
        this._orientation = new Quaternion(1, 0, 0, 0); // orientation of the block
        this.parent = 'root';
        this.positionInParent = [0, 0, 0];
        this.vec2skin = _.get(options, 'vec2skin', [0, 0, 1]);
        this.diameter = 0;
    }

    hide() {
        this.box.setEnabled(false);
        this.setVisibility(false);
    }

    show() {
        this.box.setEnabled(true);
        this.setVisibility(true);
    }

    setVisibility(visible) {
        if (this.options.showLed)
            this.led.visibility = visible;
        if (this.options.showAxis) {
            this.x_axis.visibility = visible;
            this.y_axis.visibility = visible;
            this.z_axis.visibility = visible;
        }
    }

    set qSeg2Bone(quat) {
        this._qSeg2Bone = new Quaternion(quat);
    }

    get qSeg2Bone() {
        return this._qSeg2Bone
    }

    setOrientation(quat) {
        this.setQuat(quat);
        this.setPosition(this.position);
    }

    get orientation() {
        return this._orientation
    }

    setQuat(quat) {
        this._orientation = new Quaternion(quat);
        this.box.rotationQuaternion = this.q_EImu2EB.multiply(quat).multiply(this._qSeg2Bone).babylon();
    }

    setPosition(position) {
        this.position = position;
        let test = this._orientation.multiply(this._qSeg2Bone).rotate(this.anchor);
        let position_babylon = this.q_EImu2EB.rotate([this.position[0] - test[0], this.position[1] - test[1], this.position[2] - test[2]]);
        this.box.position.x = position_babylon[0];
        this.box.position.y = position_babylon[1];
        this.box.position.z = position_babylon[2];
    }

    getParent() {
        return this.parent
    }

    getAnchorGlob() {
        return this.getGlobalPoint([0, 0, 0]);
    }

    setAnchor(anchor) {
        this.anchor = anchor;
    }

    getDimensions() {
        return this.dimensions;
    }

    getGlobalPoint(point) { // 'point' is the position of a point in local coordinates relative to the anchor. The function returns this point in global coordinates
        let test = this._orientation.rotate(point);
        return [this.position[0] + test[0], this.position[1] + test[1], this.position[2] + test[2]]; // +
    }

    setParent(parent) {
        this.parent = parent;
    }

    setPositionInParent(position) {
        this.positionInParent = position;
    }

    getPositionInParent() {
        return this.positionInParent;
    }


    /* this function changes the color of the box. BUG: Having too many boxes and setting some to a different color than the initial one can result in OpenGL Errors */
    setColor(color) {
        console.log(color)
        let vColors = this.box.getVerticesData(BABYLON.VertexBuffer.ColorKind);
        for (let v = 0; v < 4; v++) {
            vColors[v * 4] = color[0];
            vColors[v * 4 + 1] = color[1];
            vColors[v * 4 + 2] = color[2];
        }
        let vertexData = new BABYLON.VertexData();
        vertexData.colors = vColors;
        vertexData.applyToMesh(this.box, true);
    }

    /* Highlights the box by making the edges bold. Second call of the function undos it */
    highlight(mode) {
        if (mode) {
            this.box.edgesWidth = 14.0;
            this.box.edgesColor = new BABYLON.Color4(0, 0, 0,  this.options.opacity);
        } else {
            this.box.edgesWidth = 4.0;
            this.box.edgesColor = new BABYLON.Color4(0.4, 0.4, 0.4, this.options.opacity);
        }
    }

    _toggleLed() {
        if (this.ledOn)
            this.led.material.emissiveColor = this.defaultEmissiveColor;
        else
            this.led.material.emissiveColor = COLORS.white;
        this.ledOn = !this.ledOn;
    }

    setAxis(axis) {
        if (this.axis === undefined) {
            this.axis = BABYLON.MeshBuilder.CreateCylinder("axis", {height: 7, diameter: 0.1}, this.scene);
            this.axis.parent = this.box;
        }

        // default orientation is in z direction
        const angle = Math.acos(axis[2]); // dot([0 0 1], j)
        const rotAxis = [-axis[1], axis[0], 0]; // cross([0 0 1], j)
        const qAxis = Quaternion.fromAngleAxis(angle, rotAxis);
        // this.axis.rotationQuaternion = CONFIG.q_Imu2Box.conjugate().multiply(qAxis).multiply(CONFIG.q_Imu2Box);
        this.axis.rotationQuaternion = this.q_Box2Imu.multiply(qAxis).multiply(this.q_Box2Imu.conj()).babylon();
    }

    setOpacity(val) {
        if (0 <= val <= 1.0) {
            this.box.material.alpha = val;
        } else {
            console.log('Invalid opacity setting value!')
        }
    }

    set edgesRendering(val) {
        if (val) {
            this.box.enableEdgesRendering();
        } else {
            this.box.disableEdgesRendering();
        }
    }

}

/* Sphere creates a spherical object with a dynamically changeable position */
class Sphere {
    constructor(scene, diameter, color, opacity) {

        this.sphere = BABYLON.MeshBuilder.CreateSphere("sphere", {
            diameterX: diameter,
            diameterY: diameter,
            diameterZ: diameter
        }, scene);
        let greenMat = new BABYLON.StandardMaterial("greenMat", scene);
        greenMat.diffuseColor = new BABYLON.Color3(color[0], color[1], color[2]);
        this.sphere.material = greenMat;
        this.sphere.material.alpha = opacity;
        this.q_EImu2EB = new Quaternion(1, -1, 0, 0);
        this.parent = 'root'
        this.positionInParent = [0, 0, 0]
    }

    setPosition(position) {
        let position_babylon = this.q_EImu2EB.rotate(position);
        this.sphere.position.x = position_babylon[0];
        this.sphere.position.y = position_babylon[1];
        this.sphere.position.z = position_babylon[2];
    }

    hide() {
        this.sphere.setEnabled(false);
    }

    show() {
        this.sphere.setEnabled(true);
    }

    setParent(parent) {
        this.parent = parent;
    }

    setPositionInParent(position) {
        this.positionInParent = position;
    }

    getPositionInParent() {
        return this.positionInParent;
    }

    setOpacity(val) {
        if (0 <= val <= 1.0) {
            this.sphere.material.alpha = val;
        } else {
            console.log('Invalid opacity setting value!')
        }
    }
}

class FloorBox {
    constructor(scene) {
        const options = {
            width: 25,
            height: 0.01,
            depth: 15,
        };
        this.box = BABYLON.MeshBuilder.CreateBox('box', options, scene);

        this.box.material = new BABYLON.StandardMaterial("texturespere", scene);
        this.box.material.diffuseColor = COLORS.grey;
        this.box.material.alpha = 0.3;
    }
}

/* MechanicalChain uses the Boxes and Spheres to build an object with arbitrary segments */
class MechanicalChain extends Emitter{
    constructor(scene,options){
        super();
        this.options = options
        this.base = this.options.base
        this.scene = scene

        const defaultSettings = {
            segments:undefined,
            limit: 500,
            ground: undefined,
            emitOri: true,
            offset: 3,
        }

        //  check if joints need to be visualized first
        // if size of the joint is not given, use default value 3
        if (options.diameter !== undefined){
            this.offset = options.diameter
        }
        else {
            this.offset = 3
        }

        this.diameter = this.offset

        //////////////////////////base settings//////////////////////////////////////////////////////

        const base = {
            "human": {
                hip: {
                    name: 'hip',
                    parent: 'root',
                    dimensions: [3,6,9],
                    anchor_rel: [0, 0, 0],
                    anchor_abs: [0, 0, 0],
                    position: this.position,
                    color: 'blue',
                    face: 2,
                },
                upper_leg_left: {
                    name: 'upper_leg_left',
                    parent: 'hip',
                    dimensions: [3,12,3],
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, 0],
                    position_rel: [0, -0.5, -0.5,],
                    position_abs: [0, -0.5* this.offset, 0.5* this.offset],
                    color: 'red',
                    face: 2,
                },
                lower_leg_left: {
                    name: 'lower_leg_left',
                    dimensions: [3,12,3],
                    parent: 'upper_leg_left',
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, 0],
                    position_rel: [0, -1, 0],
                    position_abs: [0, -1* this.offset, 0],
                    color: 'red',
                    face: 2,
                },
                foot_left: {
                    name : 'foot_left',
                    dimensions: [6,3,3],
                    parent: 'lower_leg_left',
                    anchor_rel: [-0.5, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, 0],
                    position_rel: [0, -1, 0],
                    position_abs: [0, -1* this.offset, 0],
                    color: 'red',
                    face: 4,
                },
                upper_leg_right: {
                    name: 'upper_leg_right',
                    parent: 'hip',
                    dimensions: [3,12,3],
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, 0],
                    position_rel: [0, -0.5,0.5],
                    position_abs: [0, -0.5* this.offset, -0.5],
                    color: 'green',
                    face: 2,
                },
                lower_leg_right: {
                    name : 'lower_leg_right',
                    dimensions: [3,12,3],
                    parent: 'upper_leg_right',
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, 0],
                    position_rel: [0, -1, 0],
                    position_abs: [0, -1* this.offset, 0],
                    color: 'green',
                    face: 2,
                },
                foot_right: {
                    name : 'foot_right',
                    dimensions: [6,3,3],
                    parent: 'lower_leg_right',
                    anchor_rel: [-0.5, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, 0],
                    position_rel: [0, -1, 0],
                    position_abs: [0, -1* this.offset, 0],
                    color: 'green',
                    face: 4,
                },
                lower_back: {
                    name : 'lower_back',
                    dimensions: [3,6,6],
                    parent: 'hip',
                    anchor_rel: [0, -0.5, 0],
                    anchor_abs: [0, -0.5* this.offset, 0],
                    position_rel: [0, 0.5, 0],
                    position_abs: [0, 0.5* this.offset, 0],
                    color: 'blue',
                    face: 2,
                },
                upper_back: {
                    name : 'upper_back',
                    dimensions: [3,9,9],
                    parent: 'lower_back',
                    anchor_rel: [0, -0.5, 0],
                    anchor_abs: [0, -0.5* this.offset, 0],
                    position_rel: [0, 1, 0],
                    position_abs: [0, this.offset, 0],
                    color: 'blue',
                    face: 2,
                },
                upper_arm_left: {
                    name : 'upper_arm_left',
                    dimensions: [3,9,3],
                    parent: 'upper_back',
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, 0.5* this.offset],
                    position_rel: [0, 1, -0.5],
                    position_abs: [0, 0, -0.5* this.offset],
                    color: 'red',
                    face: 3,
                },
                lower_arm_left: {
                    name : 'lower_arm_left',
                    dimensions: [3,7.5,3],
                    parent: 'upper_arm_left',
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, 0],
                    position_rel: [0, -1, -0.5],
                    position_abs: [0, -1* this.offset, 0],
                    color: 'red',
                    face: 3,
                },
                hand_left: {
                    name : 'hand_left',
                    dimensions: [3,3,3],
                    parent: 'lower_arm_left',
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, 0],
                    position_rel: [0, -1, 0],
                    position_abs: [0, -1* this.offset, 0],
                    color: 'red',
                    face: 3,
                },
                upper_arm_right: {
                    name : 'upper_arm_right',
                    dimensions: [3,9,3],
                    parent: 'upper_back',
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, -0.5* this.offset],
                    position_rel: [0, 1, 0.5],
                    position_abs: [0, 0, 0.5 * this.offset,],
                    color: 'green',
                    // face: 0,
                    face: 3,
                },
                lower_arm_right: {
                    name : 'lower_arm_right',
                    dimensions: [3,7.5,3],
                    parent: 'upper_arm_right',
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 0.5 * this.offset, 0],
                    position_rel: [0, -1, 0.5],
                    position_abs: [0, -1 * this.offset, 0],
                    color:  'green',
                    face: 3,
                },
                hand_right: {
                    name : 'hand_right',
                    dimensions: [3,3,3],
                    parent: 'lower_arm_right',
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 0.5 * this.offset, 0],
                    position_rel: [0, -1, 0],
                    position_abs: [0, -1 * this.offset, 0],
                    color:  'green',
                    face: 3,
                },
                head: {
                    name: 'head',
                    dimensions: [3,7.5,4.5],
                    parent: 'upper_back',
                    anchor_rel: [0, -0.5, 0],
                    anchor_abs: [0, -0.5 * this.offset, 0],
                    position_rel: [0, 1, 0],
                    position_abs: [0, this.offset, 0],
                    color:  'blue',
                    face: 2,
                }
            },
            "mechanicalSegmentTemplate": {
                name: 'default',
                color: 'red',
                dimensions: [3,3,16],
                parent: undefined,
                anchor_rel: [-0.5, 0, 0],
                anchor_abs: [-0.5* this.offset, 0, 0],
                position_rel: [1, 0, 0],
                position_abs: [this.offset, 0, 0],
                orientation: new Quaternion(1,1,0,0),

                scale: 1.0,
                opacity: 1,
                zOffset: 0,
                diameter: 3,
                face: 4,
                qSeg2Bone: new Quaternion(1, 0, 0, 0),
            },
            "knee":{
                seg1: {
                    name: 'seg1',
                    color: "red",
                    dimensions: [3, 15, 3],
                    parent: "root",
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 1.5, 0],
                    face: 2,
                    signal:'quat1',
                },
                seg2: {
                    name : 'seg2',
                    color: "green",
                    dimensions: [3, 10, 3],
                    parent: "seg1",
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 1.5, 0],
                    position_rel: [0, -1, 0],
                    position_abs: [0, -3, 0],
                    face: 2,
                    signal:'quat2',
                },
            },
            "ankle":{
                seg1: {
                    name : 'seg1',
                    dimensions: [3,12,3],
                    parent: 'root',
                    anchor_rel: [0, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, 0],
                    color: 'red',
                    face: 2,
                    signal:'quat1',
                },
                seg2: {
                    name : 'seg2',
                    dimensions: [6,3,3],
                    parent: 'seg1',
                    anchor_rel: [-0.5, 0.5, 0],
                    anchor_abs: [0, 0.5* this.offset, 0],
                    position_rel: [0, -1, 0],
                    position_abs: [0, -1* this.offset, 0],
                    color: 'green',
                    face: 4,
                    signal:'quat2',
                },
            },
        }

        ////////////////////////////////////////////////////////////////////////////

        /* Settings */
        // note: this.settings contains all configuration for each segment
        //  e.g. format:  {seg1: {color: "red"}, ...}
        this.options = {...defaultSettings, ...this.options};
        let [settings, segmentsName] = this.getSettings(base, this.options);
        this.settings = _.cloneDeep(settings);
        this.segmentsName = segmentsName;

        //buffer for default input of qSen2Seg before slider adjustment
        this.qSen2Seg = _.get(this.options, 'qSen2Seg', {});

        // this.q_slider: buffer for slider input(right side: sen2seg)
        this.quatSliders = {};

        // heading: buffer for slider input(left side: headingAngle)
        this.heading = {};

        // buffer for segments box
        this.segments = {};

        // buffer for joint sphere
        this.joints = {};

        // segment names
        this.chainSequence = [];
        // dic contains {parent: [Children]}
        this.parentChildren = {}

        this.position = [0,0,0];

        this.rootName = undefined;

        // save last sample received and final orientation for each segment(e.g. after changed by slider)
        this.lastSample = {};
        this.chainFinalOrientation = {};
        // emit final orientation if required
        this.emitOri = this.options.emitOri;

        // build chain recursively
        this.buildChain();

        if (this.operatingSeg === undefined) {
            this.operatingSeg = this.rootName;
        }
    }

    getSettings(base, options){
        let settings;
        let segments_names;
        //  if use base template, update setting by iterate through base settings
        let base_setting = base[options.base]
        let template = {}
        if (base_setting !== undefined){
            let seg_setting = {}
            for (let segment in base_setting){
                seg_setting = {...base.mechanicalSegmentTemplate, ...base_setting[segment]}
                seg_setting = {...seg_setting, ...this.options};
                template[segment] = seg_setting
            }
            settings = template
            segments_names = Object.keys(template)
            if (options.segments === undefined){
                for (let i=0; i<segments_names.length;i++){
                    let seg_name = segments_names[i];
                    settings[seg_name] = template[seg_name];
                }
            }else{
                for (let i=0; i<segments_names.length;i++){
                    let seg_name = segments_names[i];
                    settings[seg_name] = {...template[seg_name], ...options.segments[seg_name]}
                }

            }
        }
        // if do not use base template update setting by iterate through input options
        else{
            for (let segment in options.segments){
                template[segment] = {...base.mechanicalSegmentTemplate, ...options.segments[segment]}
            }
            settings = options.segments
            segments_names = Object.keys(options.segments)
            for (let i=0; i<segments_names.length;i++){
                let seg_name = segments_names[i];
                settings[seg_name] = {...template[seg_name], ...settings[seg_name]}
            }
        }
        return [settings, segments_names]
    }

    checkParent(){
        // check if all input segments' parents are given
        //  visualization of human dody does not require parent
        if(this.base !== 'human'){
            for (let seg_name in this.settings){
                if(this.segmentsName.includes(this.settings[seg_name].parent) || this.settings[seg_name].parent === 'root'){}
                else{
                    console.log("undefined segments' parent")
                    alert("undefined segments' parent");
                }
            }
        }
    }

    buildChain(){
        // check if parent of each segment is given
        this.checkParent();
        //  add condition to prevent possible infinite loop during recursion
        //  e.g. Given chain blocks not connected
        this.limit = this.options.limit;
        this.buffer = JSON.parse(JSON.stringify(this.segmentsName))
        while(this.buffer.length>0 && this.limit>0){
            for (let i = 0; i < this.segmentsName.length;i++){
                this.setUpChain(this.segmentsName[i]);
            }
        }
        this.parentChildren = this.getParentChildren();
    }

    setUpChain(seg_name){
        // if parent segment already existed, or new segment to be added is root,
        // add new child segment, until all segments are added
        // in case unordered segments fail to attach parent
        this.limit -= 1;
        // pass if segment is already built
        if(seg_name in this.segments){}

        // build segment if its parent existed
        else if (this.settings[seg_name].parent in this.segments || this.settings[seg_name].parent === 'root')
        {
            this.buffer.splice(this.buffer.indexOf(seg_name), 1);
            this.chainSequence.push(seg_name)
            this.addElement(seg_name, this.settings)
        }
        // build parent seg first if not existed
        else if(this.limit > 0){
            this.setUpChain(this.settings[seg_name].parent)
        }
        //  avoid infinite loop when wrong parent setting is given
        else{
            console.log('pleas check if parent setting is correct')
        }
    }

    addElement(name, settings) {

        //  add addElement process:
        let seg_setting = settings[name]
        seg_setting.color = this.getColor(seg_setting.color)
        let parentSeg = seg_setting.parent

        this.segments[name] = new SegmentBox(this.scene, seg_setting)
        this.segments[name].setParent(parentSeg)

        const basis_self = seg_setting.dimensions
        this.chainFinalOrientation[this.settings[name]['signal']] = seg_setting.orientation;
        this.lastSample[this.settings[name]['signal']] = seg_setting.orientation;


        if (parentSeg === 'root') {
            this.rootName = name
            this.segments[name].setAnchor(this.getPosition(basis_self, seg_setting.anchor_rel, seg_setting.anchor_abs));
            this.segments[name].setPosition(this.position);
            this.segments[name].setOrientation(seg_setting.orientation)
        } else {
            const basis_parent = settings[parentSeg].dimensions
            let qSeg2BoneParent = this.segments[parentSeg].qSeg2Bone;

            if (seg_setting.anchor_rel !== undefined && seg_setting.anchor_abs !== undefined){
                this.segments[name].setAnchor(this.getPosition(basis_self, seg_setting.anchor_rel, seg_setting.anchor_abs));
            }
            if (seg_setting.position_rel !== undefined && seg_setting.position_abs !== undefined){
                let position_in_parent = this.getPosition(basis_parent, seg_setting.position_rel,seg_setting.position_abs)
                position_in_parent = qSeg2BoneParent.rotate(position_in_parent)

                this.segments[name].setPosition(this.segments[parentSeg].getGlobalPoint(
                    position_in_parent));
                // record child segment's position in parent segments' coordinate,
                // for position calculation in global coordinate(root coordinate)
                this.segments[name].setPositionInParent(position_in_parent);
            }
            this.segments[name].setOrientation(seg_setting.orientation)
            this.joints[name] = new Sphere(this.scene, this.diameter, [1, 1, 1], seg_setting.opacity);
            this.joints[name].setPosition(this.segments[name].getAnchorGlob())
        }
    }

    setPositions(position) {
        this.position = position;
        this.segments[this.rootName].setPosition(this.position);
        for (let i = 1; i < this.chainSequence.length; i++) {
            let name = this.chainSequence[i]
            let parent_seg = this.segments[name].parent
            this.segments[name].setPosition(
                this.segments[parent_seg].getGlobalPoint(this.segments[name].getPositionInParent())
            )
            this.joints[name].setPosition(this.segments[name].getAnchorGlob())
        }
        // send sample which does not send via backend(e.g from debugSlider)
        // to potential subScenes to creat a synchronized visualization
        if (this.emitOri) {
            this.emit('sample', this.chainFinalOrientation)
        }
    }

    setOrientations(sample) {
        // set orientation of each segment iteratively
        for (let i = 0; i < this.chainSequence.length; i++) {
            let name = this.chainSequence[i]
            let quat = _.get(sample, this.settings[name]['signal'])
            quat = new Quaternion(quat);
            this.lastSample[this.settings[name]['signal']] = quat;

            if (quat !== undefined) {
                let heading = new Quaternion(_.get(this.heading, name, [1, 0, 0, 0]))

                let quatSlider = new Quaternion(_.get(this.quatSliders, name, [1, 0, 0, 0]))
                quat = heading.multiply(quat.multiply(quatSlider))
                this.segments[name].setOrientation(quat)
                this.chainFinalOrientation[this.settings[name]['signal']] = quat;

            } else {
                console.log("no input signal");
                this.chainFinalOrientation[this.settings[name]['signal']] = new Quaternion(1,1, 0, 0);
            }
        }
        this.setPositions(this.position);
    }

    getPosition(basis, rel, abs) {
        let position = [0, 0, 0];
        for (let i = 0; i < 3; i++) {
            position[i] = basis[i] * rel[i] + abs[i];
        }
        return position
    }

    hide(seg){
        this.segments[seg].hide();
        if (this.joints[seg]){
            this.joints[seg].hide()
        }
    }

    show(seg){
        if (seg === 'all') {
            for (let seg in this.segments) {
                this.segments[seg].show();
                if (this.joints[seg]){
                    this.joints[seg].show()
                }
            }
        }
        else if (seg) {
            this.segments[seg].show();
            if (this.joints[seg]){
                this.joints[seg].show()
            }
        }
    }

    getColor(color_input){
        return _.get(COLORS, color_input, COLORS.red)
    }

    addSample(sample){
        let rootOri = _.get(sample, this.settings[this.rootName]['signal'])
        if (rootOri === undefined) {
            this._orientation = new Quaternion(1, 1, 0, 0).multiply(new Quaternion(_.get(this.quatSliders, name, [1, 0, 0, 0])));
            this.setOrientations(sample)
        } else {
            let heading = new Quaternion(_.get(this.heading, this.rootName, [1,0,0,0]));
            let quatSlider = new Quaternion(_.get(this.quatSliders, this.rootName, [1, 0, 0, 0]));
            let quatRoot = new Quaternion(rootOri);
            this._orientation = heading.multiply(quatRoot.multiply(quatSlider))
            this.setOrientations(sample);
        }
        this.lastSample = sample;
    }

    getChildren(self_name) {
        for (let name in this.segments) {
            if (this.segments[name].getParent() === self_name) {
                this._children.push(name)
                this.getChildren(name)
            }
        }
    }

    getParentChildren(){
        let ParentChild = {}

        for (let seg in this.segments) {
            this._children = [];
            this.getChildren(seg);
            ParentChild[seg] = this._children;
        }
        return ParentChild
    }

    updateQSlider(seg, quat) {
        if (this.segmentsName.includes(seg)) {
            this._operatingSeg = seg;
            this.quatSliders[seg] = quat;
            this.emit('change');
        } else {
            console.log('Invalid segment name.')
        }
    }

    updateHeading(seg, quat) {
        if (this.segmentsName.includes(seg)) {
            this._operatingSeg = seg;
            this.heading[seg] = quat;
            this.emit('change');
        } else {
            console.log('Invalid segment name.')
        }
    }

    updateBone(seg, quat) {
        if (this.segmentsName.includes(seg)) {
            this._operatingSeg = seg;
            this.segments[seg].qSeg2Bone = quat;
            this.emit('change');
        } else {
            console.log('Invalid segment name.')
        }
    }

    set operatingSeg(seg) {
        if (this.segmentsName.includes(seg)) {
            this._operatingSeg = seg;
            this.emit('change');
        } else {
            console.log('Invalid segment name.')
        }
    }

    get operatingSeg() {
        return this._operatingSeg
    }

    set emitFinalOri(val) {
        this.emitOri = val;
    }

    get emitFinalOri() {
        return this.emitOri
    }

    updateSignals(signals) {
        for (let seg in signals) {
            this.settings[seg].signal = signals[seg].signal;
        }
    }


    setOpacity(val, seg) {
        if (seg in this.segments) {
            this.segments[seg].setOpacity(val);
            if (seg in this.joints) {
                this.joints[seg].setOpacity(val);
            }
        } else {
            for (let seg in this.segments) {
                this.segments[seg].box.material.alpha = val;
                if (seg in this.joints) {
                    this.joints[seg].setOpacity(val);
                }
            }
        }
    }

    setEdges(val, seg) {
        if (seg in this.segments) {
            this.segments[seg].edgesRendering(val);
        } else {
            for (let seg in this.segments) {
                this.segments[seg].edgesRendering = val;
            }
        }
    }

    setColor(color, seg) {
        if (seg in this.segments) {
            this.segments[seg].setColor(color);
        } else {
            for (let seg in this.segments) {
                this.segments[seg].setColor(color);
            }
        }
    }

}

class GenericChainSlider extends Emitter {
    constructor(container, chain) {

        super();
        this.element = container;
        // this.scene = scene;
        // this.chain = scene.chain;
        this.chain = chain;

        this.qSen2Seg = Object.assign({}, this.chain.qSen2Seg)
        this.quatSliders = {};
        this._operatingSeg = undefined;
        this.segments = Object.keys(this.chain.segments);

        this.sendSample = 'last';
        this.mode = 'sen2seg';

        this.addSliders();
        // this.addCheckBox();


    }

    addCheckBox(){
        const liveSettingsPanel = new Panel(this.container, 'Show Segments',{collapsed: false});
        this.checkbox = {};
        for(let seg in this.chain.segments){
            this.checkbox[seg] = new Checkbox(liveSettingsPanel, seg ,{checked: true})
            this.checkbox[seg].on('change',function(boolean){
                if (boolean){
                    this.chain.show(seg)
                }
                else{
                    this.chain.hide(seg)
                }
            }.bind(this));
        }
    }

    addSliders(){

        const segmentsPanel = new Panel(this.container, 'Segments Sliders');
        this.dropboxLabel = new Label(segmentsPanel, 'Select Segment:');
        this.dropbox = new Dropdown(segmentsPanel, this.segments);

        this.segmentAdjustmentLabel = new Label(segmentsPanel, 'Segment Adjustment:',{id: 'sliderModeSelector'});
        this.modeSelector = new Dropdown(segmentsPanel, ['sen2seg', 'bone']);

        this.slider = new QuatEulerSliders(segmentsPanel, 0);
        new Label(segmentsPanel, 'Heading Correction:');
        this.headingSlider = new SliderRow(segmentsPanel, {value: 0,
            min: -180,
            max: 180,
            step: 1,
            ticks: [-180, -90,  0, 90, 180],
            ticks_labels: [-180, -90,  0, 90, 180],
            ticks_snap_bounds: 4,
            precision: 1},{id:'headingSlider'});

        this.advancedModeCheckBox = new Checkbox(segmentsPanel, 'Advanced Mode')

        this.sampleModeCheckBox = new Checkbox(segmentsPanel, 'use last sample', {checked: true})
        this.sampleLabel = new Label(segmentsPanel, 'Emit Sample:');
        this.sampleSlider = new QuatEulerSliders(segmentsPanel, 0);

        this.setup();
    }

    setup() {

        this.dropbox.on('change', this.onModeChange.bind(this));

        this.sampleSlider.on('change', function () {
            this.makeSample();
            // this.chain.addSample(this.makeSample());
        }.bind(this));

        this.modeSelector.on('change', function () {
            this.mode = this.modeSelector.valueText;
            this.segmentAdjustmentLabel.text = 'Segment Adjustment: ' + this.modeSelector.valueText;
        }.bind(this));

        this.slider.on('change', function (quat){
            this.changeQSliders(quat);
            this.makeSample();
            // this.chain.addSample(this.makeSample());
        }.bind(this));

        this.headingSlider.on('change', function (val) {
            this.changeHeadingSlider(val);
            this.makeSample()
            // this.chain.addSample(this.makeSample());
        }.bind(this));

        this.sampleSlider.slider_q1.value = 1.0;
        this.sampleSlider.hide = function () {
            this.sampleSlider.slider_q0.hide();
            this.sampleSlider.slider_q1.hide();
            this.sampleSlider.slider_q2.hide();
            this.sampleSlider.slider_q3.hide();
            this.sampleSlider.slider_alpha.hide();
            this.sampleSlider.slider_beta.hide();
            this.sampleSlider.slider_gamma.hide();
            this.sampleSlider.mode_dropdown.content.hide();
            this.sampleLabel.text = '';
        }.bind(this);
        this.sampleSlider.show = function () {
            // refresh dropDown menu to show sliders
            this.sampleSlider.mode_dropdown.content.show();
            if (this.sampleSlider.mode_dropdown.value === 0) {
                this.sampleSlider.slider_q0.show();
                this.sampleSlider.slider_q1.show();
                this.sampleSlider.slider_q2.show();
                this.sampleSlider.slider_q3.show();
            } else {
                this.sampleSlider.mode_dropdown.value = 0
                this.sampleSlider.onModeChange();
            }
            this.sampleLabel.text = 'Emit Sample:';
        }.bind(this);

        this.sampleModeCheckBox.on('change', function (val) {
            if (val) {
                this.sendSample = 'last';
            } else {
                this.sendSample = 'slider';
            }
        }.bind(this));

        this.advancedModeCheckBox.on('change', function (val) {
            if (val) {
                this.sampleSlider.show();
                this.modeSelector.content.show();
                this.sampleModeCheckBox.content.show();
                this.dropbox.content.show();
                this.dropboxLabel.content.show();
            }
            else {
                this.sampleSlider.hide();
                this.modeSelector.content.hide();
                this.sampleModeCheckBox.content.hide();
                this.dropbox.content.hide();
                this.dropboxLabel.content.hide();
            }
        }.bind(this));
        this.advancedModeCheckBox.emit('change', 0)

        this.onModeChange();
    }

    onModeChange() {

        this._operatingSeg = this.segments[this.dropbox.value];
        // resume with previous value when segment switch back
        let quatSeg = _.get(this.quatSliders, this.operatingSeg, new Quaternion(1, 0, 0, 0));
        this.setQuat(quatSeg);
        this.chain.operatingSeg = this._operatingSeg;
    }

    setQuat(quat) {
        this.slider.mode_dropdown.value = 0;
        this.slider.slider_q0.value = quat.w;
        this.slider.slider_q1.value = quat.x;
        this.slider.slider_q2.value = quat.y;
        this.slider.slider_q3.value = quat.z;
    }

    changeQSliders(quat) {
        // This function is only for testing and fine tuning of q_body2sensor when config.mode == 'sen2seg'
        //  this makes the sliders change q_sen2seg instead of q_bone2IMU for debug purpose
        //  ^{S1}_{E1}q(t) mult ^{B1}_{S1}q(t) mult ^{Bone}_{B1}q(t)
        // change ^{Bone}_{B1}q(t) = Q_Slider mult ^{Bone}_{B1}q(t)
        // otherwise sliders directly change q_body2sensor
        if (this.mode === 'bone') {
            // this.chain.segments[this._operatingSeg].qSeg2Bone = quat;
            this.chain.updateBone(this._operatingSeg, quat);
        } else if (this.mode === 'sen2seg'){
            this.quatSliders[this._operatingSeg] = quat;
            // this.chain.quatSliders[this._operatingSeg] = quat;
            this.chain.updateQSlider(this._operatingSeg, quat);
        }
        else {
            console.log('no sliders mode selected.');
        }
        this.emit('qChange');
    }

    changeHeadingSlider(val) {

        this.chain.updateHeading(this._operatingSeg, Quaternion.fromAngleAxis(deg2rad(val), 'z'))
        // this.chain.heading[this._operatingSeg] = Quaternion.fromAngleAxis(deg2rad(val), 'z');
        this.emit('headingChange');
    }


    makeSample() {
        const sample = this.chain.lastSample;
        this.chain.emit('change');

        if (this.sendSample === 'last') {
            this.emit('makeSample', sample);
            // return sample
        }
        else if (this.sendSample === 'slider') {
            const seg = this._operatingSeg
            for (let key in sample) {
                let signal = key.split('.')
                if (signal.includes(seg)) {
                    const ind =  signal.indexOf(seg)
                    signal[ind] = seg
                    signal = signal.join('.');
                    sample[signal] = this.sampleSlider.value;
                    break
                }
            }
            this.emit('makeSample', sample);
            // return sample
        }

    }

    get sliderValue() {
        return this.slider.value
    }

    get operatingSeg() {
        return this._operatingSeg
    }

    get headingValue() {
        return this.headingSlider.value
    }

    set operatingSeg(seg) {

        const ind = this.segments.indexOf(seg)
        if (ind >= 0) {
            this.dropbox.value = ind;
            this._operatingSeg = seg;
        }
    }

    addSink(sink) {
        console.assert(sink.onSample !== undefined, 'sink.onSample() is undefined');
        this.on('makeSample', sink.onSample.bind(sink));
        if ('quatSlider' in sink) {
            this.on('qChange', function () {
                let qs = sink.quatSlider;
                let adj = {};
                adj[this._operatingSeg] = this.slider.value;
                qs = {...qs, ...adj};
                sink.quatSlider = qs;
            }.bind(this));
        }
    }
}

// add small imu boxes to each segment as reference
// for a generic MechanicalChain named 'chain' in scene.
class IMUBoxesChain {
    constructor(scene, options) {
        const defaults = {
            qSensor2Segment: {},
            coordinates: 'FLU', // or 'RFU'
            showLed: true,
            showAxis:true,
            type:'imu',
            dimensions:[5.5/2,  3.5/2, 1.3/2],
        }
        options = {...defaults, ...options}
        this.scene = scene.scene;
        this.chain = scene.chain;
        // this.backend = backend;
        this.options = options;
        this._qSensor2Segment = this.options.qSensor2Segment;
        this.quatSlider = {};
        this.setup();
    }

    setup() {
        this.imuBoxes = {};
        for (let seg in this.chain.segments) {
            this.imuBoxes[seg] = new SegmentBox(this.scene, this.options);
            this.imuBoxes[seg].setParent(seg)
            this.imuBoxes[seg].diameter = Math.sqrt(this.chain.segments[seg].dimensions[0] ** 2 +
                this.chain.segments[seg].dimensions[2] ** 2);
        }
        this.onSample();
        // calculate position of imu boxes and axes when QSensor2Segment changes or Segment2Bone changes
        // this.backend.on('debugSliderChange', this.onSample.bind(this))
    }

    onSample() {
        // let seg = _.get(this.backend.ws.parameters, 'operatingSegment')
        // if (seg !== undefined) {
        //     seg = this.backend.ws.parameters.operatingSegment[0][this.backend.ws.parameters.operatingSegment[1]];
        //     this.quatSlider[seg] = this.backend.ws.parameters.debugSliderQuat[0][this.backend.ws.parameters.debugSliderQuat[1]];
        // }
        for (let seg in this.chain.segments) {

            let _qSlider = new Quaternion(_.get(this.quatSlider, seg, [1,0,0,0]));
            let _qSen2Seg =  new Quaternion(_.get(this._qSensor2Segment, seg, [1, 0, 0, 0])).multiply(_qSlider);
            let qSeg2Bone = this.chain.segments[seg].qSeg2Bone;

            // vector from the physical center to anchor point(origin of local coordinate)
            // physical center in segment's coordinate system
            let anchorDiff = this.chain.segments[seg].anchor.map(x => x * -1);

            let diameter = this.imuBoxes[seg].diameter;
            // axis pointing towards skin, norm = segment radius+imuBox width
            let axis = this.imuBoxes[seg].vec2skin.map(e => e * (diameter/2+ 0.5+
                this.dotVector(this.imuBoxes[seg].vec2skin, this.imuBoxes[seg].getDimensions())/2));
            // axis vector
            axis = _qSen2Seg.multiply(qSeg2Bone).rotate(axis)
            axis = this.addVector(axis, anchorDiff)

            this.imuBoxes[seg].setPositionInParent(axis)
            //
            this.imuBoxes[seg].setPosition(this.chain.segments[seg].getGlobalPoint(this.imuBoxes[seg].getPositionInParent()));

            this.imuBoxes[seg].setOrientation(this.chain.segments[seg].orientation.multiply(_qSen2Seg).multiply(_qSlider).multiply(qSeg2Bone));
        }
    }

    addVector(a,b){
        return a.map((e,i) => e + b[i]);
    }

    dotVector(a,b){
        return a.map((e,i) => e * b[i]).reduce((c, d) => c + d, 0);
    }

    getQuatSlider() {
        return this.quatSlider;
    }

    setQuatSlider(quatSlider) {
        this.quatSlider = quatSlider;
    }

    hide(seg){
        this.imuBoxes[seg].hide();
    }

    show(seg){
        if (seg === 'all') {
            for (let seg in this.imuBoxes) {
                this.imuBoxes[seg].show();
            }
        }
        else if (seg) {
            this.imuBoxes[seg].show();
        }
    }
}

// on/ off/ multiple-switches
class Switch extends Button {
    constructor(container, text, options) {
        const defaults = {
            id: '',
            checkable: false,
            value: 0,
            block: true,
            defaultClass: "btn-primary",
            checkedClass: undefined,
            mode: ['ON', 'OFF'],
        };
        options = {...defaults, ...options};
        super(container, options);
        this.options = options;
        this.mode = this.options.mode;
        this.text =  this.mode[this.options.value];
        this.optionNum = this.options.mode.length;
    }
    _onClick() {
        if (this.content.hasClass('disabled'))
            return;
        this.value = (this.value + 1) % this.optionNum;
        this.text = this.options.mode[this.value]
    }

    get currentMode() {
        return this.mode[this.value];
    }
}


// A simple infoBox to display given information items
// of selected segment, for different  items to display.
// Rewrite onSample() and addSink to backend for different applications.
class InfoBoxModule extends Widget {
    constructor(container, chain, options) {
        super(container, options);
        const defaults = {
            itemsName: ['segment', 'quaternion', 'euler_angle', 'heading_correction', 'index', 'time'],
            formatters: [(val => val), this.printQuat, this.printEuler, (val => val), (val => val),
                (val => Math.round(val * 100) / 100)],
        };
        options = {...defaults, ...options};
        this.options = options;
        this.chain = chain;
        this.items = {};
        this.infoPanel = new Panel(container, 'infoBox')
        for (let i = 0; i < options.itemsName.length; i++) {
            this.items[options.itemsName[i]] = new Label(this.infoPanel,'item: ' + String(i));
        }
        this.setup();
        this.onSample({});
    }

    setup() {

        this.segment = this.chain.operatingSeg;
        this.heading = Math.round(_.get(this.chain.heading, this.segment,
            new Quaternion(1,0,0,0)).angle() * 180 / Math.PI * 100) / 100;

        this.chain.on('change',function (){this.segment = this.chain.operatingSeg;}.bind(this));
        this.chain.on('change', function (){
            this.segment = this.chain.operatingSeg;
            this.heading = Math.round(_.get(this.chain.heading, this.segment,
                new Quaternion(1,0,0,0)).angle() * 180 / Math.PI * 100) / 100;
            this.signal = this.options.segments[this.segment].signal;
        }.bind(this));

        this.chain.on('sample', function (sample) {
            this.onSample(sample);
        }.bind(this));
    }

    // rewrite this function for different  items to display
    onSample(sample) {
        let s = {
            segment: this.segment,
            index:_.get(sample, 'ind', 'N/A'),
            time:_.get(sample, 't', 'N/A'),
            quaternion: _.get(sample, this.signal, new Quaternion(1,1,0,0)),
            euler_angle: _.get(sample, this.signal, new Quaternion(1,1,0,0)),
            heading_correction: String(this.heading) + '°',
        };
        for (let i = 0; i < this.options.itemsName.length; i++) {
            let format = this.options.formatters[i];
            let it = this.options.itemsName[i];
            this.items[it].text = it + ' : ' + format(_.get(s, it, 'N/A'));
        }
    }

    printEuler(quat) {
        if (typeof quat === 'string') {
            return quat
        }
        quat = new Quaternion(quat);
        let angle = quat.eulerAngles('zyx', true).map(rad2deg);
        return `\nYaw : ${Math.round(angle[0])}, \nPitch: ${Math.round(angle[1])}, \nRoll: ${Math.round(angle[2])}`
    }

    printQuat(quat) {
        if (typeof quat === 'string') {
            return quat
        }
        quat = new Quaternion(quat);
        return `w: ${quat['array'][0].toFixed(2)}\n` +
            `x:${quat['array'][1].toFixed(2)}\n` +
            `y:${quat['array'][2].toFixed(2)}\n` +
            `z:${quat['array'][3].toFixed(2)}`
    }
}

class PlotModule extends Widget{
    constructor(container, backend, chain, options) {
        super(container, options);
        const defaults = {
            plotOptions: ['acc', 'gyr', 'delta', 'euler angles'],
            width: 375,
            height: 220,
            labels: [undefined, 'x', 'y', 'z'],
            useTimeSignal: true,
            // signal of data to plot in samples
            path: 'livePlot',
        }
        options = {...defaults, ...options};
        this.options = options;
        this.backend = backend;
        this.chain = chain;

        this.path = this.options.path;
        this.segment = this.chain.operatingSeg;

        this.plotPanel = new Panel(container, 'Live Plot', {content: '', id:'plot'});
        this.segmentLable = new Label(this.plotPanel, 'Live Plot of: ' + this.segment, {id:'segmetnLabel'})
        this.label = new Label(this.plotPanel, '', {id:'plotLabel'})
        this.plotMenu = new Dropdown(this.plotPanel, this.options.plotOptions)

        insertDOM(this.plotPanel, '<h4 id="PlotHeader"></h4>');
        this.livePlot = new LinePlot(this.plotPanel, ['w', 'x', 'y', 'z'],
            {
                scaleFactor: 180/Math.PI,
                width: options.width,
                height: options.height,
                labels: options.labels,
                colors: ['#000', '#d62728', '#2ca02c', '#1f77b4'],
                useTimeSignal: options.useTimeSignal,
            });

        this.plotButton = new Button(this.plotPanel, 'Fire!', {block: false, defaultClass: 'btn-default'});
        this.setup();
        this.onModeChange();
    }

    setup() {
        // choose plot option
        this.plotMenu.on('change', this.onModeChange.bind(this));

        this.plotButton.on('change',this.onPlotChange.bind(this));

        this.chain.on('change', function () {
            this.segment = this.chain.operatingSeg;
            this.segmentLable.text = 'Live Plot of: ' + this.segment;
        }.bind(this));

    }

    // rewrite onModeChange to change description for each item to plot
    onModeChange() {
        switch (this.plotMenu.valueText) {
            case 'acc':
                this.label.text = 'Accelerometer reading';
                $("#PlotHeader").text("Accelerometer [m/s²]");
                this.livePlot.scaleFactor = 1.0;
                break;
            case 'gyr':
                this.label.text = 'Gyroscope reading';
                $("#PlotHeader").text("Gyroscope [°/s]");
                this.livePlot.scaleFactor = 180/Math.PI;
                break;
            case 'delta':
                this.label.text = 'Heading Drift/Offset';
                $("#PlotHeader").text("Estimated Delta  [°]");
                this.livePlot.scaleFactor = 180/Math.PI;
                break;
            case 'euler angles':
                this.label.text = 'Yaw / Pitch / Roll';
                $("#PlotHeader").text("Euler Angles  [°]");
                this.livePlot.scaleFactor = 180/Math.PI;
                break;
            default:
                $("#PlotHeader").text("");
        }
    }

    // rewrite onPlotChange to assemble samples for livePlot
    onPlotChange() {

        let signal = this.plotMenu.valueText;
        let segment = this.segment === undefined? this.chain.operatingSeg:this.segment;

        // send request for missing data and signal for it.
        if (_.get(this.backend.playback.data, segment + '.' + signal) === undefined)
        {
            this.backend.sendParams({signal: signal,segment: segment});
            this.path = 'livePlot';
        }
        // set signal for data to plot which already exists
        else{
            this.path = segment + '.' + signal;
        }

        this.backend.processSample = function (sample) {
            sample.w = 0.0;
            sample.x = _.get(sample, this.path, [0, 0, 0])[0];
            sample.y = _.get(sample, this.path, [0, 0, 0])[1];
            sample.z = _.get(sample, this.path, [0, 0, 0])[2];
            return sample;
        }.bind(this);
        this.backend.addSink(this.livePlot);
        this.livePlot.onSample()
    }
}


class DeltaWeightPlot extends Widget{
    constructor(container,name,options){
        super();
        const defaults = {
            width:200,
            height:120,
            delta_min:0,
            delta_max:360.0,
            weight_min:0.0,
            weight_max: 1.0,
            weight_step:0.1,
            delta_step: 30,
            seconds: 60,
            delta_line_color: 'rgba(255, 0, 50, .8)',
            delta_filt_line_color: 'rgba(0, 255, 50, .8)',
            weight_line_color: 'rgba(255, 174, 99, .8)',
            weight_fill_color: 'rgba(255,208,99, .2)'
        };

        options = {...defaults, ...options};
        this.panel = new Panel(container, 'live plot')
        this.canvas = document.createElement('canvas');
        this.canvas.id     = name;
        this.canvas.width  = options.width;
        this.canvas.height = options.height;
        this.canvas.style.zIndex   = 8;
        this.canvas.style.position = "relative";
        this.canvas.style.border   = "0px solid";
        // container.insertChild(this.canvas);
        this.panel.insertChild(this.canvas);
        var ctx = document.getElementById(name);

        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],

                datasets: [{
                    label: 'delta',
                    yAxisID: 'A',
                    data: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                    backgroundColor: [
                        'rgba(255,255,255, .0)',
                    ],
                    borderColor: [
                        options.delta_line_color,
                    ],
                    borderWidth: 2,
                    pointRadius: 1,
                    pointHoverRadius: 1
                },
                    {
                        label: 'delta_filt',
                        yAxisID: 'A',
                        data: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                        backgroundColor: [
                            'rgba(255,255,255, .0)',
                        ],
                        borderColor: [
                            options.delta_filt_line_color,
                        ],
                        borderWidth: 2,
                        pointRadius: 1,
                        pointHoverRadius: 1
                    },
                    {
                        label: 'weight',
                        hidden: false,
                        yAxisID: 'B',
                        data: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                        backgroundColor: [
                            options.weight_fill_color,
                        ],
                        borderColor: [
                            options.weight_line_color,
                        ],
                        borderWidth: 2,
                        pointRadius: 1,
                        pointHoverRadius: 1
                    }
                ]
            },
            options: {
                tooltips: {
                    enabled: false
                },
                responsive: true,
                scales: {
                    yAxes: [{
                        id: 'A',
                        scaleLabel: {
                            display: true,
                            labelString: 'delta [°]'
                        },
                        position: 'left',
                        ticks: {
                            max: options.delta_max,
                            min: options.delta_min,
                            stepSize: options.delta_step
                        }
                    },
                        {
                            id: 'B',
                            scaleLabel: {
                                display: true,
                                labelString: 'weight [-]'
                            },
                            gridLines: {
                                drawOnChartArea: false
                            },
                            position: 'right',
                            ticks: {
                                max: options.weight_max,
                                min: options.weight_min,
                                stepSize: options.weight_step
                            }
                        }
                    ],
                    xAxes: [{
                        //type: 'linear',
                        ticks: {
                            max: options.seconds,
                            min: 0,
                            stepSize: 1,
                            display:false,
                            /*callback: function(value, index, values) {
                                   return chartData.labels[index];
                              } */
                        }
                    }]
                }
            }})

        this.signal = _.get(options, 'plotSignal')
        this.segment = null;

    }
    pushValue(delta,delta_filt,weight){
        this.chart.data.labels.pop();
        this.chart.data.labels.push('0');
        this.chart.data.datasets[0].data.splice(0,1);
        this.chart.data.datasets[0].data.push(delta);
        this.chart.data.datasets[1].data.splice(0,1);
        this.chart.data.datasets[1].data.push(delta_filt);
        this.chart.data.datasets[2].data.splice(0,1);
        this.chart.data.datasets[2].data.push(weight);
        /*
              this.chart.data.datasets.forEach((dataset,index) => {
                  dataset.data.splice(0, 1);
                  dataset.data.push(value);
              }); */
        this.chart.update();
    }
    clearAll(){
        this.chart.data.datasets.forEach((dataset) => {
            dataset.data = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0];
        });
        this.chart.update();
    }

    onSample(sample) {
        const plotData = _.get(sample, `${this.signal}.${this.segment}`  , {});
        const delta = rad2deg(wrapToPi(_.get(plotData, 'delta', 0))) + 180;
        const delta_filt = rad2deg(wrapToPi(_.get(plotData, 'delta_filt', 0))) + 180;
        const weight = _.get(plotData, 'rating', 0);
        this.pushValue(delta,delta_filt,weight);

    }

}


class MultiSignal extends Widget {
    // subChains: [refChainA, refChainB, ...] in the first refChain only selected segment of
    //  the selected solution is shown(minimum-display)
    // mainChains: [subChainA, subChainB, ...]
    constructor(container, mainChains, subChains, options) {
        super();
        this.element = container;
        this.chain = mainChains[0];
        this.mainChains = mainChains;
        this.subChains = subChains;
        this.options = options;

        this.multiSignal = options.multiSignal;
        this.methods = Object.keys(this.options.multiSignal);

        this.addWidget();
        this.setUpWidget();
    }

    addWidget() {
        this.panel = new Panel(this.container, 'Select Solutions');

        new Label(this.panel, 'Choose result for avatar A: ')
        this.avatarA = new Checkbox(this.panel, 'avatar A')
        this.refSlectorA = new Dropdown(this.panel, this.methods);

        new Label(this.panel, 'Choose result for avatar B: ')
        this.avatarB = new Checkbox(this.panel, 'avatar B', {checked:true})
        this.refSlectorB = new Dropdown(this.panel, this.methods);

        this.signalA = _.get(this.options, 'segments');
        this.signalB = _.get(this.options, 'segments');

        this.compareButton = new Button(this.panel, 'compare', {checkedClass:true});

        // original signal
        this.mainChainSignal = {}
        for (let seg in this.chain.segments) {
            this.mainChainSignal[seg] = {'signal': this.chain.settings[seg].signal};
        }
    }

    setUpWidget() {

        // change shown segment in subScene.refChain
        this.chain.emitFinalOri = true;
        this._operatingSeg = this.chain.operatingSeg;
        this.chain.on('change', function () {
            this._operatingSeg = this.chain.operatingSeg;
            this.updateSignal();
            this.compareButton.emit('change', this.compareButton.value);
        }.bind(this));

        // set up signal path for mainChains
        this.refSlectorA.on('change', function () {
            if (this.avatarA.value) {
                this.signalA = _.get(this.multiSignal, this.refSlectorA.valueText);
                this.updateSignal();
            }
        }.bind(this));

        this.refSlectorB.on('change', function () {
            if (this.avatarB.value) {
                this.signalB = _.get(this.multiSignal, this.refSlectorB.valueText);
                this.updateSignal();
            }
        }.bind(this));

        this.compareButton.on('change', function (val) {
            if (val) {
                this.minimumDisplay(this.subChains[0])
            }
            else {
                this.hideChain(this.subChains[0]);
            }
        }.bind(this));
        this.hideChain(this.subChains[0]);
    }

    updateSignal() {

        if (this.avatarA.value) {
            for (let i = 0; i < this.mainChains.length; i++) {
                this.mainChains[i].updateSignals(this.signalA);
            }
        }

        if (this.avatarB.value) {
            // update signal for all non-overlay reference avatar
            for (let i = 1; i < this.subChains.length; i++) {
                this.subChains[i].updateSignals(this.signalB);
            }
            // update signal for overlay reference avatar
            let selectedSegSetting = {};
            selectedSegSetting[this._operatingSeg] = {signal: this.signalB[this._operatingSeg]['signal']};
            this.subChains[0].updateSignals(_.merge({}, this.signalA, selectedSegSetting));
        }
    }

    resetSignal(chains) {
        for (let i = 1; i < chains.length; i++) {
            chains[i].updateSignals(this.mainChainSignal);
        }
    }

    minimumDisplay(chain) {
        this.hideChain(chain);
        this.showChain(chain, this._operatingSeg);
    }

    hideChain(chain) {
        for (let seg in chain.segments) {
            chain.hide(seg);
        }
    }

    showChain(chain, seg) {
        if (seg in chain.segments) {
            chain.show(seg);
        } else {
            for (let seg in chain.segments) {
                chain.show(seg);
            }
        }
    }
}


class ImageMap extends Widget {
    constructor(container, options) {
        const defaults = {
            collapsible: true,
            collapsed: true,
            id: '',
            content: '',
            spacing: '10px',
            headerText: 'Selected Segment: ',
            segmentsName:['foot_left', 'lower_leg_left', 'upper_leg_left', 'foot_right', 'lower_leg_right', 'upper_leg_right', 'hip',
                'lower_back', 'upper_back', 'head', 'hand_left', 'lower_arm_left', 'upper_arm_left', 'hand_right',
                'lower_arm_right', 'upper_arm_right'],
        };
        options = {...defaults, ...options};

        super(container, options);
        this.chain = [];
        //  Image Map Generated by http://www.image-map.net/
        // available at https://github.com/abdchehadeh/bodyMap
        this.mapsterSetting = {
            fillOpacity: 0.5,
            fillColor: "d42e16",
            isSelectable: true,
            singleSelect: true,
            render_highlight: {
                fillColor: '2aff00',
                stroke: true,
            },
            render_select: {
                fillColor: 'ff000c',
                stroke: false,
                strokeColor: "3320FF",
                strokeWidth: 4,
            },
            fadeInterval: 50,
            mapKey: 'name',
            listKey: 'key',
            scaleMap: true,
            onClick: function (e) {
                if(!this.diff.includes(e.key)) {
                    this.label.text = String(e.key);
                    this.emit('click', e);
                    this.segment = e.key;
                }
            }.bind(this),
            showToolTip: true,
            toolTipClose: ["tooltip-click", "area-click"],
            areas: [],
        }

        let segs = Object.keys(this.options.segments);
        this.diff =  _.differenceBy(this.options.segmentsName, segs)
        for (let i = 0; i < this.diff.length; i++) {
            this.mapsterSetting.areas.push(
                {
                    key: this.diff[i],
                    isSelectable: false,
                    highlight: false,
                }
            )
        }

        let map = `<img src="lib/assets/human.jpg" useMap="#image-map">
                <map name="image-map">
                <area id="id_head" class="bodyParts" name="head" title="head" href="#"
                      coords="198,23,175,31,165,78,188,112,212,113,234,72,224,28" shape="poly">
                <area id="id_chest" class="bodyParts" name="upper_back" title="chest" href="#"
                      coords="154,138,244,135,253,184,249,267,199,226,152,264,147,182" shape="poly">
                <area id="id_abdominal" class="bodyParts" name="lower_back" title="abdominal" href="#"
                      coords="250,268,254,292,199,312,145,290,149,268,199,230" shape="poly">
                <area id="id_pelvis" class="bodyParts" name="hip" title="pelvis" href="#"
                      coords="254,293,256,313,201,367,140,315,145,291,199,311" shape="poly">
                <area id="id_left_femur_thigh" class="bodyParts" name="upper_leg_left" title="left femur/thigh" href="#"
                      coords="202,369,260,345,259,443,215,457" shape="poly">
                <area id="id_right_femur_thigh" class="bodyParts" name="upper_leg_right" title="right femur/thigh" href="#"
                      coords="197,371,183,453,140,441,136,348" shape="poly">
                <area id="id_right_tib_fib" class="bodyParts" name="lower_leg_right" title="right tib/fib" href="#"
                      coords="174,505,137,497,128,533,144,604,161,605,172,548" shape="poly">
                <area id="id_left_fib_tib" class="bodyParts" name="lower_leg_left" title="left fib/tib" href="#"
                      coords="226,506,226,544,237,597,257,598,268,544,265,498,244,504" shape="poly">
                <area id="id_right_foot" class="bodyParts" name="foot_right" title="right foot" href="#"
                      coords="143,633,136,680,156,697,173,692,168,636" shape="poly">
                <area id="id_left_foot" class="bodyParts" name="foot_left" title="left foot" href="#"
                      coords="230,633,225,692,246,698,261,680,257,631" shape="poly">
                <area id="id_right_humerus" class="bodyParts" name="upper_arm_right" title="right humerus" href="#"
                      coords="146,185,148,222,142,250,115,240,123,196,120,175" shape="poly">
                <area id="id_right_forearm" class="bodyParts" name="lower_arm_right" title="right forearm" href="#"
                      coords="140,276,123,317,103,308,106,292,109,264" shape="poly">
                <area id="id_right_hand" class="bodyParts" name="hand_right" title="right hand" href="#"
                      coords="117,337,107,378,89,388,75,377,85,343,71,346,80,330,94,323" shape="poly">
                <area id="id_left_hand" class="bodyParts" name="hand_left" title="left hand" href="#"
                      coords="285,341,304,322,317,327,333,351,317,342,324,379,309,389,291,377" shape="poly">
                <area id="id_left_forearm" class="bodyParts" name="lower_arm_left" title="left forearm" href="#"
                      coords="261,274,290,261,297,308,276,320" shape="poly">
                <area id="id_left_humerus" class="bodyParts" name="upper_arm_left" title="left humerus" href="#"
                      coords="278,174,279,194,283,237,256,249,253,218,254,180" shape="poly">
            </map>`
        // create div
        this.header  = $('<div>', {class:'panel-heading'}).append($('<h3>', {class:'panel-title'}).text(options.headerText));
        this.controlBar = $('<div>', {class:'panel-body in'})
        this.controlBar.css('flex-grow', '3');

        this.label = new Label(this.controlBar, 'N/A')

        this.hideCheck = new Checkbox(this.controlBar, 'hide')

        this.content = $('<div>', {class:'panel-body in'}).append(map)

        // this.content = $('<div>');
        // this.content.addClass('img');
        // this.content.append(map);
        // console.log(this.content)

        this.panel   = $('<div>', {class:'panel panel-default', id: options.id});
        this.panel.append(this.header).append(this.controlBar).append(this.content);

        if (options.collapsible) {
            this.header.on('click', this.toggle.bind(this));
            this.header.prop('style', 'cursor: pointer;');
        }

        if (options.collapsible && options.collapsed) {
            this.content.toggleClass('collapse in');
        }

        this.spacing  = options.spacing;
        this.objects = [];

        insertDOM(container, this.panel);

        this.image = $('img');

        this.image.mapster(this.mapsterSetting);

        this.segment = undefined;

        this.setUp();
    }

    insertChild(child) {
        this.objects.push(child);
        this.content.append(child);

        if (child.css != null)
            child.css("margin-top", this.spacing);
    }

    toggle(animated=true) {
        // this.content.toggleClass("collapse");
        if (animated)
            this.content.collapse('toggle');
        else
            this.content.toggleClass('collapse in');
        this.emit('change', this.value, this);
    }

    set spacing(spacing) {
        this._spacing = spacing;

        for (let i in this.objects) {
            i.css('margin-top', spacing);
        }
    }

    get spacing() {
        return this._spacing;
    }

    get value() { // false if panel is collapsed
        return this.content.hasClass('collapse in');
    }

    setUp() {
        this.hideCheck.on('change', function (val) {
            if (val) {
                this.deselectAll();
                this.image.mapster('set_options', {singleSelect:false});
            } else {
                this.deselectAll();
                this.image.mapster('set_options', {singleSelect:true});
            }
        }.bind(this));

        this.on('click', function (e) {
            const seg = e.key;
            const select = e.selected

            if (this.hideCheck.value && select) {
                this.emit('hide', seg);
            } else {
                this.emit('show', seg);
            }
            this.emit('select', seg);
            // chain.operatingSeg = seg
        }.bind(this));

        this.hideCheck.on('change', function (val) {
            if (!val) {
                this.emit('show', 'all')
            }
        }.bind(this));
    }

    linkChain(chain) {
        this.chain.push(chain);

        this.on('click', function (e) {
            const seg = e.key;
            const select = e.selected
            if (this.hideCheck.value && select) {
                chain.hide(seg);
            } else {
                chain.show(seg);
            }
            chain.operatingSeg = seg
        }.bind(this));

        this.hideCheck.on('change', function (val) {
            if (!val) {
                chain.show('all')
            }
        }.bind(this));
    }

    clearLink() {
        this.chain = [];
    }

    linkSlider(slider) {
        this.on('click', function (e) {
            slider.operatingSeg = e.key;
        }.bind(this));
    }

    // change segment property of widget
    linkWidget(widget) {
        if ('segment' in widget) {
            this.on('click', function () {
                widget.segment = this.segment;
            }.bind(this));
        }
    }

    deselectAll() {
        const area = [this.image.mapster('get')];
        for (let i = 0; i < area.length; i++) {
            this.image.mapster('set', false, area[i]);
        }
    }
}


class Transparency extends Widget {
    constructor(container, options) {
        super();

        const defaults = {
            value: 100,
            min: 0,
            max: 100,
            step: 1,
            ticks: [0, 50, 100],
            ticks_labels: ['0%', '50%', '100%'],
            ticks_snap_bounds: 1,
            precision: 1,
        };
        const positionParams = {
            value: 0,
            min: -100,
            max: 100,
            step: 1,
            ticks: [-100, -50,  0, 50, 100],
            ticks_labels: [-100, -50,  0, 50, 100],
            ticks_snap_bounds: 4,
            precision: 1
        };
        options = {...defaults, ...options};

        this.panel = new Panel(container, 'Reference Chain Setting');

        this.opacity = new Button(this.panel, 'opacity',
            {block: false, defaultClass: 'btn-default'})
        this.edge = new Button(this.panel, 'Edges',
            {block: false, defaultClass: 'btn-default'})
        this.positionButton = new Button(this.panel, 'Position',
            {block: false, defaultClass: 'btn-default'})

        this.transpSlider =  new SliderRow(this.panel, options, {label: 'opacity', width: '250px',});
        this.edgeCheck = new Checkbox(this.panel, 'show edges', {checked: false})

        this.x = new SliderRow(this.panel, positionParams, {...{}, label: 'x'});
        this.y = new SliderRow(this.panel, positionParams, {...{}, label: 'y'});
        this.z = new SliderRow(this.panel, positionParams, {...{}, label: 'z'});

        this.x.on('change', this.updatePosition.bind(this));
        this.y.on('change', this.updatePosition.bind(this));
        this.z.on('change', this.updatePosition.bind(this));
        this.position = [0, 0, 0];
        this.setUp();
    }

    setUp() {
        this.opacity.on('change', function () {
            this.transpSlider.show();
            this.edgeCheck.content.hide();
            this.x.hide();
            this.y.hide();
            this.z.hide();
        }.bind(this));
        this.edge.on('change', function () {
            this.transpSlider.hide();
            this.edgeCheck.content.show();
            this.x.hide();
            this.y.hide();
            this.z.hide();
        }.bind(this));
        this.positionButton.on('change', function () {
            this.transpSlider.hide();
            this.edgeCheck.content.hide();
            this.x.show();
            this.y.show();
            this.z.show();
        }.bind(this));

        this.opacity.emit('change', 1);
    }

    updatePosition() {
        this.position = [this.x.value, this.y.value, this.z.value];
        this.emit('position', this.position);
    }

    linkChain(chain) {
        this.transpSlider.on('change', function (val) {
            const op = val / 100.0;
            chain.setOpacity(op);
        }.bind(this));

        this.edgeCheck.on('change', function (val) {
            chain.setEdges(val);
        }.bind(this));

        this.edgeCheck.emit('change', false);
        this.transpSlider.value = 30;

        this.on('position', function (val) {
            chain.setPositions(val);
        }.bind(this));

    }
}


class OriEstLiveTuning extends Widget {
    constructor(container, options) {
        super();

        this.options = options;
        const tauAccParams = {
            value: 1,
            min: 0,
            max: 3,
            step: 0.1
        };
        const tauMagParams = {
            value: 0,
            min: 0,
            max: 300000,
            step: 1.0
        };
        const zetaParams = {
            value: 0,
            min: 0,
            max: 3,
            step: 0.1
        };
        const accRatingParams = {
            value: 1,
            min: 0,
            max: 1.0,
            step: 0.05,
        };

        this.oriPanel = new Panel(container, 'Oirentation Estimation Settings',{collapsed: false});
        this.tauAccSlider = new SliderRow(this.oriPanel, tauAccParams,
            {width: '200px', labelWidth: '3em', label: 'Tau Acc'})
        this.tauMagSlider = new SliderRow(this.oriPanel, tauMagParams,
            {width: '200px', labelWidth: '3em', label: 'Tau Mag'})
        this.zeta = new SliderRow(this.oriPanel, zetaParams,
            {width: '200px', labelWidth: '3em', label: 'Zeta'})
        this.accRating = new SliderRow(this.oriPanel, accRatingParams,
            {width: '200px', labelWidth: '3em', label: 'Acc bias'})

        // TODO use defaultParams initialy
        this.defaultParams = this.options.defaultParams;
        this.segment = undefined;
        this.params = {};

        this.setup();
    }

    setup() {
        this.tauAccSlider.on('change',this.updateParams.bind(this));
        this.tauMagSlider.on('change', this.updateParams.bind(this));
        this.zeta.on('change', this.updateParams.bind(this));
        this.accRating.on('change', this.updateParams.bind(this));

        this.oriEstisDisabled = false;
    }
    hide() {
        this.oriPanel.content.hide();
        this.tauAccSlider.hide();
        this.tauMagSlider.hide();
        this.zeta.hide();
        this.accRating.hide();
        this.oriPanel.content.hide();
        this.oriEstisDisabled = true;
    }
    show() {
        this.oriPanel.content.show();
        this.tauAccSlider.show();
        this.tauMagSlider.show();
        this.zeta.show();
        this.accRating.show();
        this.oriPanel.content.show();
        this.oriEstisDisabled = false;
    }

    updateParams() {
        if (!this.oriEstisDisabled) {
            let defaultOriParams = _.get(this.defaultParams, `${this.segment}.oriEst`);
            defaultOriParams = {
                ...defaultOriParams, ...{
                    tauAcc: this.tauAccSlider.value,
                    tauMag: this.tauMagSlider.value,
                    zeta: this.zeta.value,
                    accRating: this.accRating.value,
                }
            };
            this.params[this.segment] = {oriEst: defaultOriParams};
            this.emit('change', this.params);
        }
    }

    clearParams() {
        this.params = {};
        this.refreshDisplay();
    }

    refreshDisplay() {
        this.oriEstisDisabled = true;

        let oriParams = _.get(this.options, `defaultParams.${this.segment}.oriEst`);
        let params =  _.get(this.params, `${this.segment}.oriEst`);
        oriParams = {...oriParams, ...params};

        this.accRating.value = _.get(oriParams, 'accRating', 1);
        this.tauAccSlider.value = _.get(oriParams, 'tauAcc', 1);
        this.tauMagSlider.value = _.get(oriParams, 'tauMag', 300000);
        this.zeta.value = _.get(oriParams, 'zeta', 0);

        this.oriEstisDisabled = false;
    }

    setSegment(seg) {
        this.segment = seg;
        this.refreshDisplay();
    }

    getParams() {
        return this.params
    }
}

class ResetLiveTuning extends Widget {
    constructor(container, options) {
        super();
        const positionParams = {
            value: 0,
            min: -1,
            max: 1,
            step: 0.01,
            ticks: [-1, 0, 1],
            ticks_labels: [-1, 0, 1],
            ticks_snap_bounds: 0.04,
            precision: 3
        };
        const phiOffsetParams = {
            value: 0,
            min: -180,
            max: 180,
            step: 1,
            ticks: [-180, -90,  0, 90, 180],
            ticks_labels: [-180, -90,  0, 90, 180],
            ticks_snap_bounds: 4,
            precision: 1
        }

        this.options = options;
        this.axis = 'x';

        this.resetPanel = new Panel(container, 'Reset Alignment Settings');

        this.resetAlignmentexactAxisLabel = new Label(this.resetPanel, 'Exact Axis: ');
        this.exactAxis = new Dropdown(this.resetPanel, ['None', 'x', 'y', 'z']);

        this.resetAlignmentCSLabel = new Label(this.resetPanel, 'Choose Coordinate: ')
        this.buttonX = new Button(this.resetPanel, 'X', {block: false, defaultClass: 'btn-default', checkedClass: 'btn-success'});
        this.buttonY = new Button(this.resetPanel, 'Y', {block: false, defaultClass: 'btn-default', checkedClass: 'btn-success'});
        this.buttonZ = new Button(this.resetPanel, 'Z', {block: false, defaultClass: 'btn-default', checkedClass: 'btn-success'});

        this.CS = new Dropdown(this.resetPanel, ['Sensor CS', 'Global Sensor CS'])

        this.x = new SliderRow(this.resetPanel, positionParams, {...{width: '200px', labelWidth: '3em'}, label: 'x'});
        this.y = new SliderRow(this.resetPanel, positionParams, {...{width: '200px', labelWidth: '3em'}, label: 'y'});
        this.z = new SliderRow(this.resetPanel, positionParams, {...{width: '200px', labelWidth: '3em'}, label: 'z'});
        this.phiOffset = new SliderRow(this.resetPanel, phiOffsetParams, {...{width: '200px', labelWidth: '3em'}, label: 'phi Offset'});

        this.defaultParams = this.options.defaultParams;
        this.segment = undefined;
        this.params = {};

        this.setup();
        this.disabled = false;
    }

    setup() {
        this.exactAxis.on('change',this.updateParams.bind(this));

        this.x.on('change',this.updateParams.bind(this));
        this.y.on('change',this.updateParams.bind(this));
        this.z.on('change',this.updateParams.bind(this));
        this.CS.on('change', this.updateParams.bind(this));

        this.phiOffset.on('change',this.updateParams.bind(this));

        this.buttonX._onClick();
        this.buttonX.on('change', function (val) {
            if (val) {
                this.buttonY.value = 0;
                this.buttonZ.value = 0;
                this.axis = 'x';
                this.refreshDisplay();
            }
        }.bind(this));
        this.buttonY.on('change', function (val) {
            if (val) {
                this.buttonX.value = 0;
                this.buttonZ.value = 0;
                this.axis = 'y';
                this.refreshDisplay();
            }
        }.bind(this));
        this.buttonZ.on('change', function (val) {
            if (val) {
                this.buttonX.value = 0;
                this.buttonY.value = 0;
                this.axis = 'z';
                this.refreshDisplay();
            }
        }.bind(this));

        this.disabled = false;
    }
    hide() {
        this.resetPanel.content.hide();

        this.resetAlignmentexactAxisLabel.content.hide();
        this.exactAxis.content.hide();

        this.buttonX.content.hide();
        this.buttonY.content.hide();
        this.buttonZ.content.hide();

        this.resetAlignmentCSLabel.content.hide();
        this.CS.content.hide();

        this.x.hide();
        this.y.hide();
        this.z.hide();
        this.phiOffset.hide();
        this.disabled = true;
    }
    show() {
        this.resetPanel.content.show();

        this.resetAlignmentexactAxisLabel.content.show();
        this.exactAxis.content.show();

        this.buttonX.content.show();
        this.buttonY.content.show();
        this.buttonZ.content.show();

        this.resetAlignmentCSLabel.content.show();
        this.CS.content.show();

        this.x.show();
        this.y.show();
        this.z.show();
        this.phiOffset.show();

        this.disabled = false;
    }

    updateParams() {
        if (!this.disabled) {
            let paramsBuffer = _.get(this.params, `${this.segment}.reset`);
            let ax = {}
            if (this.axis === 'x')
            {
                ax = {
                    x: [this.x.value, this.y.value, this.z.value],
                    xCs: -1 * this.CS.value,
                };
            }
            else if (this.axis === 'y')
            {
                ax = {
                    y: [this.x.value, this.y.value, this.z.value],
                    yCs: -1 * this.CS.value,
                };
            }
            else if (this.axis === 'z')
            {
                ax = {
                    z: [this.x.value, this.y.value, this.z.value],
                    zCs: -1 * this.CS.value,
                };
            }
            paramsBuffer = {...paramsBuffer, ...{exactAxis: this.exactAxis.valueText}};
            paramsBuffer = {...paramsBuffer, ...ax};

            this.params[this.segment] = {reset: paramsBuffer};
            let paramsHeading = _.get(this.params, `${this.segment}.resetHeading.phiOffset`);
            this.params[this.segment]['resetHeading'] = {'phiOffset': paramsHeading||deg2rad(this.phiOffset.value)};
            this.emit('change', this.params);
        }
    }

    clearParams() {
        this.params = {};
        this.refreshDisplay();
    }

    refreshDisplay() {
        this.disabled = true;

        let params = _.get(this.defaultParams, `${this.segment}.reset`);
        let paramsInBuffer =  _.get(this.params, `${this.segment}.reset`);
        params = {...params, ...paramsInBuffer};

        this.exactAxis.value = ['None', 'x', 'y', 'z'].indexOf(_.get(params, 'exactAxis', 'None'));

        const ax = _.get({'x': 'xCs', 'y': 'yCs', 'z': 'zCs'}, this.axis);
        this.CS.value = -1 * _.get(params, ax, 0);

        this.x.value = _.get(params, this.axis, [0, 0, 0])[0];
        this.y.value = _.get(params, this.axis, [0, 0, 0])[1];
        this.z.value = _.get(params, this.axis, [0, 0, 0])[2];

        this.phiOffset.value = rad2deg(_.get(this.params, `${this.segment}.resetHeading.phiOffset`)) ||
            rad2deg(_.get(this.options, `defaultParams.${this.segment}.resetHeading.phiOffset`));

        this.disabled = false;
    }

    setSegment(seg) {
        this.segment = seg;
        this.refreshDisplay();
    }

    getParams() {
        return this.params
    }
}

class DeltaCorrectLiveTuning extends Widget {
    constructor(container, options) {
        super();

        const windowTimeSliderParams = {
            value: 8,
            min: 0,
            max: 30,
            step: 0.1
        };
        const tauSliderParams = {
            value: 5,
            min: 0,
            max: 15,
            step: 0.1
        };
        const positionParams = {
            value: 0,
            min: -1,
            max: 1,
            step: 0.01,
            ticks: [-1, 0, 1],
            ticks_labels: [-1, 0, 1],
            ticks_snap_bounds: 0.04,
            precision: 3
        };

        this.options = options;
        this.defaultParams = options.defaultParams;

        this.deltaCorrectionPanel = new Panel(container, 'Delta Correction Settings');

        this.deltaCorrectionLabel = new Label(this.deltaCorrectionPanel, 'Delta Correction: ')
        this.windowTimeDeltaCorrection = new SliderRow(this.deltaCorrectionPanel, windowTimeSliderParams,
            {width: '200px', labelWidth: '3em', label: 'window time'})
        this.tauDeltaCorrection = new SliderRow(this.deltaCorrectionPanel, tauSliderParams,
            {width: '200px', labelWidth: '3em', label: 'Tau delta'})
        this.tauBiasDeltaCorrection = new SliderRow(this.deltaCorrectionPanel, tauSliderParams,
            {width: '200px', labelWidth: '3em', label: 'Tau bias'})

        this.constraint1d = new Checkbox(this.deltaCorrectionPanel, '1D Correction')
        this.constraint2d = new Checkbox(this.deltaCorrectionPanel, '2D Correction')
        this.constraintROM = new Checkbox(this.deltaCorrectionPanel, '3D ROM Constraints')

        this.jointLabel1 = new Label(this.deltaCorrectionPanel, 'Joint 1');
        this.joint1x =  new SliderRow(this.deltaCorrectionPanel, positionParams, {...{width: '200px', labelWidth: '3em'}, label: 'x'});
        this.joint1y =  new SliderRow(this.deltaCorrectionPanel, positionParams, {...{width: '200px', labelWidth: '3em'}, label: 'y'});
        this.joint1z =  new SliderRow(this.deltaCorrectionPanel, positionParams, {...{width: '200px', labelWidth: '3em'}, label: 'z'});

        this.jointLabel2 = new Label(this.deltaCorrectionPanel, 'Joint 2');
        this.joint2x =  new SliderRow(this.deltaCorrectionPanel, positionParams, {...{width: '200px', labelWidth: '3em'}, label: 'x'});
        this.joint2y =  new SliderRow(this.deltaCorrectionPanel, positionParams, {...{width: '200px', labelWidth: '3em'}, label: 'y'});
        this.joint2z =  new SliderRow(this.deltaCorrectionPanel, positionParams, {...{width: '200px', labelWidth: '3em'}, label: 'z'});

        this.ROM = new RangeSliders(this.deltaCorrectionPanel);

        this.segment = undefined;
        this.disabled = false;
        this.params = {};
        this.setup();
    }

    setup() {
        this.constraint1d.on('change', function (val) {
            if (val) {
                this.constraint2d.value = 0;
                this.constraintROM.value = 0;
                this.jointLabel1.content.show();
                this.jointLabel2.content.hide();
                this.joint1x.show();
                this.joint1y.show();
                this.joint1z.show();
                this.joint2x.hide();
                this.joint2y.hide();
                this.joint2z.hide();
                this.ROM.hide();
            }
        }.bind(this));
        this.constraint2d.on('change', function (val) {
            if (val) {
                this.constraint1d.value = 0;
                this.constraintROM.value = 0;
                this.jointLabel2.content.show();
                this.jointLabel1.content.show();
                this.joint1x.show();
                this.joint1y.show();
                this.joint1z.show();
                this.joint2x.show();
                this.joint2y.show();
                this.joint2z.show();
            }
            else {
                this.jointLabel2.content.hide()
                this.joint2x.hide();
                this.joint2y.hide();
                this.joint2z.hide();

            }
            this.ROM.hide();
        }.bind(this));
        this.constraintROM.on('change', function (val) {
            if (val) {
                this.constraint1d.value = 0;
                this.constraint2d.value = 0;
                this.jointLabel2.content.hide();
                this.jointLabel1.content.hide();
                this.joint1x.hide();
                this.joint1y.hide();
                this.joint1z.hide();
                this.joint2x.hide();
                this.joint2y.hide();
                this.joint2z.hide();
                this.ROM.show();
            }
        }.bind(this));

        this.windowTimeDeltaCorrection.on('change', this.updateParams.bind(this));
        this.tauDeltaCorrection.on('change', this.updateParams.bind(this));
        this.tauBiasDeltaCorrection.on('change', this.updateParams.bind(this));

        this.joint1x.on('change', this.updateParams.bind(this));
        this.joint1y.on('change', this.updateParams.bind(this));
        this.joint1z.on('change', this.updateParams.bind(this));

        this.joint2x.on('change', this.updateParams.bind(this));
        this.joint2y.on('change', this.updateParams.bind(this));
        this.joint2z.on('change', this.updateParams.bind(this));

        this.ROM.on('change', this.updateParams.bind(this));

        this.disabled = false;
    }
    hide() {
        this.deltaCorrectionPanel.content.hide();
        this.deltaCorrectionLabel.content.hide();
        this.windowTimeDeltaCorrection.hide();
        this.tauDeltaCorrection.hide();
        this.tauBiasDeltaCorrection.hide();
        this.constraint1d.content.hide();
        this.constraint2d.content.hide();
        this.constraintROM.content.hide();

        this.jointLabel1.content.hide();
        this.joint1x.hide();
        this.joint1y.hide();
        this.joint1z.hide();

        this.jointLabel2.content.hide();
        this.joint2x.hide();
        this.joint2y.hide();
        this.joint2z.hide();

        this.disabled = true;
    }
    show() {
        this.deltaCorrectionPanel.content.show();
        this.deltaCorrectionLabel.content.show();
        this.windowTimeDeltaCorrection.show();
        this.tauDeltaCorrection.show();
        this.tauBiasDeltaCorrection.show();
        this.constraint1d.content.show();
        this.constraint2d.content.show();
        this.constraintROM.content.show();

        this.jointLabel1.content.show();
        this.joint1x.show();
        this.joint1y.show();
        this.joint1z.show();

        this.jointLabel2.content.show();
        this.joint2x.show();
        this.joint2y.show();
        this.joint2z.show();

        this.disabled = false;
    }

    refreshDisplay() {

        let defaultParams = _.get(this.defaultParams, `${this.segment}.deltaCorrection`);
        let paramsBuffer = _.get(this.params, `${this.segment}.deltaCorrection`);

        let joint = _.get(paramsBuffer, 'joint') || _.get(defaultParams, 'joint');
        let estSetting = {..._.get(this.defaultParams, `${this.segment}.deltaCorrection.est_settings`),
            ..._.get(this.params, `${this.segment}.deltaCorrection.est_settings`)};

        this.disabled = true;
        if (joint === undefined) {
            this.constraintROM.value = 0;
            this.constraintROM._onCheckBoxChange();
            this.constraint2d.value = 0;
            this.constraint2d._onCheckBoxChange();
            this.constraint1d.value = 0;
            this.constraint1d._onCheckBoxChange();

            this.jointLabel2.content.hide();
            this.joint2x.hide();
            this.joint2y.hide();
            this.joint2z.hide();

            this.jointLabel1.content.hide();
            this.joint1x.hide();
            this.joint1y.hide();
            this.joint1z.hide();
        }
        else if (joint[0].constructor === Array && joint.length === 2) {

            this.constraint2d.value = 1;
            this.constraint2d._onCheckBoxChange();

            this.joint1x.value = joint[0][0];
            this.joint1y.value = joint[0][1];
            this.joint1z.value = joint[0][2];

            this.joint2x.value = joint[1][0];
            this.joint2y.value = joint[1][0];
            this.joint2z.value = joint[1][0];
        }
        else if (joint[0].constructor === Array && joint.length === 3) {

            this.constraintROM.value = 1;
            this.constraintROM._onCheckBoxChange();

            this.joint1x.value = joint[0][0];
            this.joint1y.value = joint[0][1];
            this.joint1z.value = joint[0][2];

            this.joint2x.value = joint[1][0];
            this.joint2y.value = joint[1][0];
            this.joint2z.value = joint[1][0];
        }
        else if (joint[0].constructor === Number) {
            this.constraint1d.value = 1;
            this.constraint1d._onCheckBoxChange();

            this.joint1x.value = joint[0];
            this.joint1y.value = joint[1];
            this.joint1z.value = joint[2];

            this.jointLabel2.content.hide();
            this.joint2x.hide();
            this.joint2y.hide();
            this.joint2z.hide();
        }

        this.windowTimeDeltaCorrection.value = _.get(estSetting, 'windowTime', 8);
        this.tauBiasDeltaCorrection.value = _.get(estSetting, 'tauBias', 5);
        this.tauDeltaCorrection.value = _.get(estSetting, 'tauDelta', 5);

        this.disabled = false;
    }

    updateParams() {
        if (!this.disabled) {
            let joint
            let estSetting = {
                windowTime: this.windowTimeDeltaCorrection.value,
                tauDelta: this.tauDeltaCorrection.value,
                tauBias: this.tauBiasDeltaCorrection.value,
            }
            if (this.constraint1d.value) {
                joint = [this.joint1x.value, this.joint1y.value, this.joint1z.value];
            }
            else if (this.constraint2d.value) {
                joint = [[this.joint1x.value, this.joint1y.value, this.joint1z.value],
                    [this.joint2x.value, this.joint2y.value, this.joint2z.value]];
            }
            else if (this.constraintROM.value) {
                joint = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
                this.params[this.segment] = {deltaCorrection: {joint: joint, est_settings: estSetting,
                        joint_info: {'angle_ranges': this.ROM.getParams(), 'convention': 'xyz'}}};
                this.emit('change', this.params);
                return;
            }
            this.params[this.segment] = {deltaCorrection: {joint: joint, est_settings: estSetting}};
            this.emit('change', this.params);
        }
    }

    clearParams() {
        this.params = {};
        this.refreshDisplay();
    }

    setSegment(seg) {
        this.segment = seg;
        this.refreshDisplay();
    }
    getParams() {
        return this.params
    }

}

class JointEstLiveTuning extends Widget {
    constructor(container, options) {
        super();
        this.param = {};
        this.options = options;
        this.defaultParams = options.defaultParams;

        this.segment = undefined;
        this.params = {};
        this.disabled = true;
        this.jointESTPanel = new Panel(container, 'Joint Estimation Setting');

        const wg = {
            value: 1.0,
            min: -2,
            max: 3,
            step: 0.01,
        };
        const wa = {
            value: 1.0,
            min: -2,
            max: 3,
            step: 0.01,
        };
        const dataSizeParam = {
            value: 2000,
            min: 1000,
            max: 10000,
            step: 100
        };
        const angRateEnergyParams = {
            value: 15,
            min: 0,
            max: 200,
            step: 10
        };
        const windowSizeParam = {
            value: 41,
            min: 21,
            max: 201,
            step: 2
        };

        this.weightG = new SliderRow(this.jointESTPanel, wg,
            {width: '200px', labelWidth: '3em', label: 'Gyr weight',
                valueLabelFormatter: (val => this.scale(val))});

        this.weightA = new SliderRow(this.jointESTPanel, wa,
            {width: '200px', labelWidth: '3em', label: 'Acc weight',
                valueLabelFormatter: (val => this.scale(val))});

        this.sampleCheck = new Checkbox(this.jointESTPanel, 'use sample selection');
        this.windowSize = new SliderRow(this.jointESTPanel, windowSizeParam,
            {width: '200px', labelWidth: '3em', label: 'window size'})
        this.angRateEnergyThreshold = new SliderRow(this.jointESTPanel, angRateEnergyParams,
            {width: '200px', labelWidth: '3em', label: 'angular rate energy threshold'})
        this.dataSize = new SliderRow(this.jointESTPanel, dataSizeParam,
            {width: '200px', labelWidth: '3em', label: 'data size'})

        this.setup();
        this.disabled = false;
    }

    setup() {

        this.sampleCheck.on('change', function (val) {
            if (val) {
                this.windowSize.show();
                this.angRateEnergyThreshold.show();
                this.dataSize.show();
            } else {
                this.windowSize.hide();
                this.angRateEnergyThreshold.hide();
                this.dataSize.hide();
            }
        }.bind(this));
        this.sampleCheck.on('change', this.updateParams.bind(this));

        this.weightA.on('change', this.updateParams.bind(this));
        this.weightG.on('change', this.updateParams.bind(this));
        this.windowSize.on('change', this.updateParams.bind(this));
        this.angRateEnergyThreshold.on('change', this.updateParams.bind(this));
        this.dataSize.on('change', this.updateParams.bind(this));
    }

    updateParams() {
        if (!this.disabled) {
            let p = {
                wa: this.scale(this.weightA.value),
                wg: this.scale(this.weightG.value),
                winSize: this.windowSize.value
            }
            if (this.sampleCheck.value)
            {
                p = {
                    ...p, ...{
                        angRateEnergyThreshold: this.angRateEnergyThreshold.value,
                        dataSize: this.dataSize.value,
                        useSampleSelectionthis: this.sampleCheck.value,
                    }
                };
            }
            else
            {p = {...p, ...{useSampleSelectionthis: this.sampleCheck.value,}}};

            this.params[this.segment] = {jointEst: p};
            this.emit('change', this.params);
        }
    }
    refreshDisplay() {

        let params = _.get(this.defaultParams, `${this.segment}.jointEst`);
        let paramsInBuffer =  _.get(this.params, `${this.segment}.jointEst`);
        params = {...params, ...paramsInBuffer};

        this.disabled = true;

        this.sampleCheck.value = _.get(params, 'useSampleSelection', 0)
        this.sampleCheck._onCheckBoxChange();

        this.weightA.value = this.unscale(_.get(params, 'wa', 3))
        this.weightG.value = this.unscale(_.get(params, 'wg', 0.5))

        this.windowSize.value = _.get(params, 'winSize', 61)
        this.angRateEnergyThreshold.value = _.get(params, 'angRateEnergyThreshold', 80)
        this.dataSize.value = _.get(params, 'dataSize', 2500)

        this.disabled = false;
    }

    scale(position) {
        // position will be between 0 and 100
        const minp = -2;
        const maxp = 3;
        const minv = Math.log(0.01);
        const maxv = Math.log(1000);
        // calculate adjustment factor
        const scale = (maxv-minv) / (maxp-minp);
        return Math.round(Math.exp(minv + scale*(position-minp)) * 100) / 100
    }
    unscale(value) {
        const minp = -2;
        const maxp = 3;
        const minv = Math.log(0.01);
        const maxv = Math.log(1000);
        const scale = (maxv-minv) / (maxp-minp);
        return (Math.log(value)-minv) / scale + minp;
    }

    hide() {
        this.weightG.hide();
        this.weightA.hide();
        this.sampleCheck.content.hide();
        this.windowSize.hide();
        this.angRateEnergyThreshold.hide();
        this.dataSize.hide();
        this.jointESTPanel.content.hide();
        this.disabled = true;
    }
    show() {
        this.weightG.show();
        this.weightA.show();
        this.sampleCheck.content.show();
        this.windowSize.show();
        this.angRateEnergyThreshold.show();
        this.dataSize.show();
        this.jointESTPanel.content.show();
        this.disabled = false;
    }

    setSegment(seg) {
        this.segment = seg;
        this.refreshDisplay();
    }

    clearParams() {
        this.params = {};
        this.refreshDisplay();
    }

    getParams() {
        return this.params;
    }
}

class LiveSettings extends Widget {
    constructor(container, options) {
        super();
        const defaults = {
            process: ['Solution A', 'Solution B', 'Solution C', 'Solution Manual'],
            segments:['foot_left', 'lower_leg_left', 'upper_leg_left', 'foot_right', 'lower_leg_right', 'upper_leg_right', 'hip',
                'lower_back', 'upper_back', 'head', 'hand_left', 'lower_arm_left', 'upper_arm_left', 'hand_right',
                'lower_arm_right', 'upper_arm_right'],
            lowerLimbs: ['foot_left', 'lower_leg_left', 'upper_leg_left', 'foot_right', 'lower_leg_right', 'upper_leg_right',],
        };
        options = {...defaults, ...options};
        this.options = options;
        this.defaultParams = this.options.defaultParams;

        this.params = {}
        this.liveSettingsPanel = new Panel(container, 'Live Settings',{collapsed: false});
        new Label(this.liveSettingsPanel, 'Select Segment: ')

        this.segmentSelector = new Dropdown(this.liveSettingsPanel,  Object.keys(this.options.segments));

        new Label(this.liveSettingsPanel, 'Select Solution: ')
        this.buttonA = new Button(this.liveSettingsPanel, 'Solution A', {block: false, defaultClass: 'btn-default', checkedClass: 'btn-success'});
        this.buttonB = new Button(this.liveSettingsPanel, 'Solution B', {block: false, defaultClass: 'btn-default', checkedClass: 'btn-success'});
        this.buttonC = new Button(this.liveSettingsPanel, 'Solution C', {block: false, defaultClass: 'btn-default', checkedClass: 'btn-success'});
        this.buttonM = new Button(this.liveSettingsPanel, 'Solution Manual', {block: false, defaultClass: 'btn-default', checkedClass: 'btn-success'});

        this.segment = this.segmentSelector.valueText;
        this.oriEstSettings = new OriEstLiveTuning(this.liveSettingsPanel, this.options);
        this.resetSettings = new ResetLiveTuning(this.liveSettingsPanel, this.options);
        this.jointEstSettings = new JointEstLiveTuning(this.liveSettingsPanel, this.options);
        this.deltaSettings = new DeltaCorrectLiveTuning(this.liveSettingsPanel, this.options);

        this.clearAll = new Button(this.liveSettingsPanel, 'reset all params',{block: true, defaultClass: 'btn-primary', checkedClass: 'btn-success'});
        this.confirm = new Button(this.liveSettingsPanel, 'enable manual params',{block: true, defaultClass: 'btn-primary', checkedClass: 'btn-success'});

        this.setUp();
        this.buttonM.value = 1;
    }

    setUp() {
        this.segmentSelector.on('change', function () {
            this.segment = this.segmentSelector.valueText;
            this.oriEstSettings.setSegment(this.segment);
            this.resetSettings.setSegment(this.segment);
            this.jointEstSettings.setSegment(this.segment);
            this.deltaSettings.setSegment(this.segment);
        }.bind(this));
        this.segmentSelector.emit('change');

        this.confirm.on('change', function () {
            this.emit('sendParams', this.params);
        }.bind(this));
        this.clearAll.on('change', this.clearParams.bind(this));

        this.buttonA.on('change', function (val) {
            if (val) {
                this.solution = 'A';
                this.refreshDisplay();
            }
        }.bind(this));
        this.buttonB.on('change', function (val) {
            if (val) {
                this.solution = 'B';
                this.refreshDisplay();
            }
        }.bind(this));
        this.buttonC.on('change', function (val) {
            if (val) {
                this.solution = 'C';
                this.refreshDisplay();
            }
        }.bind(this));
        this.buttonM.on('change', function (val) {
            if (val) {
                this.solution = 'M';
                this.refreshDisplay();
            }
        }.bind(this));

        this.oriEstSettings.on('change', function () {
            this.emit('change', this.params);
        }.bind(this));
        this.jointEstSettings.on('change', function () {
            this.emit('change', this.params);
        }.bind(this));
        this.deltaSettings.on('change', function () {
            this.emit('change', this.params);
        }.bind(this));
        this.resetSettings.on('change', function () {
            this.emit('change', this.params);
        }.bind(this));

        this.on('change', this.updateParams.bind(this));
    }

    refreshDisplay() {
        switch (this.solution) {
            case "M":
                this.oriEstSettings.show();
                this.resetSettings.hide();
                this.jointEstSettings.hide();
                this.deltaSettings.hide();
                this.buttonA.value = 0;
                this.buttonB.value = 0;
                this.buttonC.value = 0;
                break;
            case "A":
                this.oriEstSettings.show();
                this.resetSettings.show();
                this.jointEstSettings.hide();
                this.deltaSettings.hide();
                this.buttonB.value = 0;
                this.buttonC.value = 0;
                this.buttonM.value = 0;
                break;
            case "B":
                this.oriEstSettings.show();
                this.resetSettings.show();
                this.jointEstSettings.show();
                this.deltaSettings.hide();
                this.buttonA.value = 0;
                this.buttonC.value = 0;
                this.buttonM.value = 0;
                break;
            case "C":
                this.oriEstSettings.show();
                this.resetSettings.show();
                this.jointEstSettings.show();
                this.deltaSettings.show();
                this.buttonA.value = 0;
                this.buttonB.value = 0;
                this.buttonM.value = 0;
                break;
        }
    }

    updateParams() {
        const oriEstParams = this.oriEstSettings.getParams();
        const resetParams = this.resetSettings.getParams();
        const jointParams = this.jointEstSettings.getParams();
        const delaParams = this.deltaSettings.getParams();
        this.params = _.merge({}, oriEstParams, resetParams, jointParams, delaParams)
        console.log('Final Params: ', this.params)
    }

    clearParams() {
        this.oriEstSettings.clearParams();
        this.deltaSettings.clearParams();
        this.resetSettings.clearParams();
        this.jointEstSettings.clearParams();
        this.params = {}
    }

    linkBackend(backend) {
        this.on('sendParams', function () {
            console.log('send params')
            backend.sendParams({...this.params, ...{solution: this.solution}})
        }.bind(this));
    }
}

// pretty print obj to html
class Display extends Label{
    constructor(container, obj, options) {
        const panel = new Panel(container, 'Live Params', {collapsed: true})
        super(panel, obj, options);

    }

    set text(text) {
        const str = "<pre>" + JSON.stringify(text, function(k,v){if(v instanceof Array) return JSON.stringify(v); return v; }, 4)+ "</pre>"
        this.content.html(str);
        return this;
    }

    linkSetting(trigger) {
        trigger.on('change', function (obj) {
            this.text = obj;
        }.bind(this));
    }

}


class RangeSliders extends Widget {
    constructor(container, options) {
        super(container, options);

        const sliderOpts = {
            width: '250px',
            labelWidth: '4em',
            label:''
        };

        const defaults = {
            value: [-360, 360],
            min: -360,
            max: 360,
            step: 1,
            rangeHighlights: [{ "start": 0, "end": 0, "class": "currval"}, { "start": -0.2, "end": 0.2, "class": "zero"}],
        };

        options = {...defaults , ...options};
        this.options = options
        this.panel = new Panel(container, 'Range of Motion', {id: 'ROM'});
        this.x = new SliderRow(this.panel, defaults, {...sliderOpts, ...{label: 'x', id:'xSlider'}})
        this.y = new SliderRow(this.panel, defaults, {...sliderOpts, ...{label: 'y', id:'ySlider'}})
        this.z = new SliderRow(this.panel, defaults, {...sliderOpts, ...{label: 'z', id:'zSlider'}})

        this.setup();
    }

    setup() {
        this.x.on('change', function (val) {
            this.emit('change');
        }.bind(this));
        this.y.on('change', function (val) {
            this.emit('change');
        }.bind(this));
        this.z.on('change', function (val) {
            this.emit('change');
        }.bind(this));

        this.on('change', function () {
            this.ROM = [
                this.x.value,
                this.y.value,
                this.z.value
            ];
        }.bind(this));
    }

    getParams() {
        return this.ROM;
    }

    clearParams() {
        this.ROM = {};
        this.refreshDisplay();
    }

    show() {
        this.panel.content.show();
    }

    hide() {
        this.panel.content.hide();
    }
}

