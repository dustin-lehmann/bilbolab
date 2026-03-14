"use strict";

class Scene {
    constructor(canvas_or_engine) {
        this.engineIsShared = (canvas_or_engine instanceof BABYLON.Engine);
        if (this.engineIsShared) {
            this.engine = canvas_or_engine;
            this.canvas = this.engine.getRenderingCanvas();
        } else {
            if (typeof canvas_or_engine === "string") {
                this.canvas = document.getElementById(canvas_or_engine);
            } else {
                this.canvas = canvas_or_engine[0];  // jquery object
            }
            this.engine = new BABYLON.Engine(this.canvas, true);
        }
        this.scene = new BABYLON.Scene(this.engine);
        this.scene.useRightHandedSystem = true;

        if (!this.engineIsShared) {
            this.engine.runRenderLoop(function () {
                this.scene.render();
            }.bind(this));
            window.addEventListener('resize', function () {
                this.engine.resize();
            }.bind(this));
        }
    }
}


function applyRelativeQuatToBone(bone, quat, q_Bone2Imu) {
    const quatBabylon = q_Bone2Imu.conj().multiply(quat).multiply(q_Bone2Imu).babylon();
    bone.setRotationQuaternion(quatBabylon);
}

function applyGlobalQuatToBone(bone, mesh, quat, q_Bone2Imu, q_EImu2EB) {
    const quatBabylon = q_EImu2EB.multiply(quat).multiply(q_Bone2Imu).babylon();
    bone.setRotationQuaternion(quatBabylon, BABYLON.Space.WORLD, mesh);
}

class RiggedMesh {
    constructor(scene) {
        this.scene = scene;
        this.initialized = false;
        this.q_EImu2EB = new Quaternion(1, -1, 0, 0);
        this.q_Bone2Imu = {};
        this.bones = {};
        this.meshForBone = {};
    }

    addBones(skeleton, mesh) {
        for (let b of skeleton.bones) {
            // TODO: check for duplicated bones
            this.bones[b.name] = b;
            this.meshForBone[b.name] = mesh;
        }
    }

    setRelativeQuat(boneName, quat, parent) {
        let qRel = new Quaternion(quat);
        if (parent !== undefined) {
            qRel = (new Quaternion(parent)).conj().multiply(qRel);
        }

        applyRelativeQuatToBone(this.bones[boneName], qRel, this.q_Bone2Imu[boneName]);
    }

    setAbsoluteQuat(boneName, quat) {
        quat = new Quaternion(quat);
        applyGlobalQuatToBone(this.bones[boneName], this.meshForBone[boneName], quat, this.q_Bone2Imu[boneName], this.q_EImu2EB);
    }

    setToZeroPose(bones) {
        const q = (new Quaternion(1,0,0,0)).babylon();
        for (let b of bones) {
            this.bones[b].setRotationQuaternion(q);
        }
    }

    setAllToRestPose() {
        for (let b in this.bones) {
            this.bones[b].returnToRest();
        }
    }

    setToRestPose(bones) {
        for (let b of bones) {
            this.bones[b].returnToRest();
        }
    }
}

class IMUBox {
    constructor(scene, options) {
        this.scene = scene;
        const defaults = {
            dimX: 5.5,
            dimY: 3.5,
            dimZ: 1.3,
            texture: 'lib/textures.json/texture_imu.png', // set to false to use colors on top and front side
            color: COLORS.C1,
            led: true,
            axes: true,
            scale: 1.0,
        };
        options = {...defaults, ...options};

        const x = options.dimX, y = options.dimY, z = options.dimZ;
        const boxOpts = {
            width: x*options.scale,
            height: z*options.scale,
            depth: y*options.scale,
        };
        const mat = new BABYLON.StandardMaterial('mat', scene);

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
        } else {
            const faceColors = new Array(6);
            faceColors[4] = options.color; // top
            faceColors[2] = options.color; // front
            boxOpts.faceColors = faceColors;
        }

        this.box = BABYLON.MeshBuilder.CreateBox('box', boxOpts, scene);
        this.box.material = mat;

        this.q_EImu2EB = new Quaternion(1, -1, 0, 0);
        this.q_Box2Imu = new Quaternion(1, 1, 0, 0);

        if (options.led) {
            this.led = BABYLON.MeshBuilder.CreateSphere('led', {}, scene);
            this.led.parent = this.box;
            const ledScale = x*y*z*0.01*options.scale;
            this.led.scaling = new BABYLON.Vector3(ledScale, ledScale, ledScale);
            this.led.position.x = -0.8*x/2*options.scale;
            this.led.position.y = z/2*options.scale;
            this.led.position.z = 0.75*y/2*options.scale;
            this.led.material = new BABYLON.StandardMaterial('ledmaterial', scene);
            this.led.material.diffuseColor = COLORS.grey;
            this.ledOn = false;
            this.defaultEmissiveColor = this.led.material.emissiveColor;
            setInterval(this._toggleLed.bind(this), 500);
        }

        if (options.axes) {
            const axisLen = Math.max(x, y, z)*1.5*options.scale;
            this.x_axis = new Arrow(this.scene, {parent: this.box, color: COLORS.C3, vector: [axisLen, 0, 0], origin: [-axisLen/2, 0, 0], diameter: 0.1*options.scale});
            this.y_axis = new Arrow(this.scene, {parent: this.box, color: COLORS.C2, vector: [0, 0, -axisLen], origin: [0, 0, axisLen/2], diameter: 0.1*options.scale});
            this.z_axis = new Arrow(this.scene, {parent: this.box, color: COLORS.C0, vector: [0, axisLen, 0], origin: [0, -axisLen/2, 0], diameter: 0.1*options.scale});
        }
    }

    setQuat(quat) {
        this.box.rotationQuaternion = this.q_EImu2EB.multiply(quat).multiply(this.q_Box2Imu).babylon();
    }

    set visibility(visible) {
        this.box.visibility = visible;
        if (this.led)
            this.led.visibility = visible;
        if (this.x_axis) {
            this.x_axis.visibility = visible;
            this.y_axis.visibility = visible;
            this.z_axis.visibility = visible;
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
}

class IMUScene extends Scene {
    constructor(id, options) {
        const defaults = {
            signal: 'quat',
            axisSignal: undefined,
            texture: 'lib/textures.json/texture_imu.png',
        };
        options = {...defaults, ...options};
        super(id);
        this.options = options;
        this.createScene();
    }

    createScene() {
        this.camera = new BABYLON.ArcRotateCamera("ArcRotateCamera", 1, 0.8, 10, new BABYLON.Vector3(0, 0, 0), this.scene);
        // this.camera.attachControl(this.canvas, false);
        this.light = new BABYLON.HemisphericLight('light1', new BABYLON.Vector3(0,1,0), this.scene);

        this.imu = new IMUBox(this.scene, {axes: false, texture: this.options.texture});

        this.ui = BABYLON.GUI.AdvancedDynamicTexture.CreateFullscreenUI("ui", true, this.scene);
        this.textbox = new BABYLON.GUI.TextBlock();
        this.textbox.font_size = 14;
        this.textbox.text = "";
        this.textbox.color = "white";
        this.textbox.paddingTop = 3;
        this.textbox.paddingLeft = 3;
        this.textbox.textVerticalAlignment = BABYLON.GUI.Control.VERTICAL_ALIGNMENT_TOP;
        this.textbox.textHorizontalAlignment = BABYLON.GUI.Control.HORIZONTAL_ALIGNMENT_LEFT;
        this.ui.addControl(this.textbox);
    }

    onSample(sample) {
        const q = new Quaternion(_.get(sample, this.options.signal));
        this.imu.setQuat(q);
        if (this.options.axisSignal) {
            this.imu.setAxis(_.get(sample, this.options.axisSignal));
        }

        const angles = q.eulerAngles('zyx', true).map(rad2deg);
        const text = 'yaw:\n' + Math.round(angles[0]) + '°\npitch:\n' + Math.round(-angles[1]) + '°\nroll:\n' + Math.round(angles[2]) + '°';
        this.textbox.text = text;
    }
}

class Arrow {
    constructor(scene, options) {
        const defaults = {
            parent: undefined,
            diameter: 0.1,
            scale: 1.0,
            origin: [0, 0, 0],
            color: undefined,
            vector: [0,1,0],
            arrowSize: 5,
        };
        options = {...defaults, ...options};

        this.scene = scene;
        this.mesh = BABYLON.Mesh.CreateCylinder('cylinder', 1, options.diameter, options.diameter, 12, 1, scene);
        this.mesh.parent = options.parent;

        this.mesh.material = new BABYLON.StandardMaterial("mat", scene);
        if (options.color) {
            this.mesh.material.diffuseColor = options.color;
        }

        this.arrowheadLength = options.arrowSize*options.diameter;
        if (options.arrowSize) {
            this.arrowhead = BABYLON.Mesh.CreateCylinder('arrowhead', this.arrowheadLength, 1e-10, this.arrowheadLength/2, 12, 1, scene);
            this.arrowhead.parent = options.parent;
            this.arrowhead.material = new BABYLON.StandardMaterial("mat", scene);
        }

        if (options.color) {
            this.mesh.material.diffuseColor = options.color;
            if (this.arrowhead)
                this.arrowhead.material.diffuseColor = options.color;
        }

        if (options.parent)
            this.q_EImu2EB = new Quaternion(1, 0, 0, 0);
        else
            this.q_EImu2EB = new Quaternion(1, -1, 0, 0);

        this.origin = new BABYLON.Vector3(...options.origin);
        this.quat = new Quaternion(1,0,0,0);
        this.offset = [0,0,0];
        this.scale = options.scale;

        this.setVector(options.vector);
    }

    setVector(vec) {
        this.quat = this.q_EImu2EB.multiply(Quaternion.from2Vectors([0,1,0], vec));
        const length = vecNorm(vec)*this.scale - this.arrowheadLength;
        const offset = this.quat.rotate([0, length/2, 0]);
        this.mesh.position = this.origin.add(new BABYLON.Vector3(offset[0], offset[1], offset[2]));
        this.mesh.scaling.y = length;
        this.mesh.rotationQuaternion = this.quat.babylon();
        if (this.arrowhead) {
            const pos = this.quat.rotate([0, length + this.arrowheadLength/2, 0]);
            this.arrowhead.position = new BABYLON.Vector3(pos[0]+this.origin.x, pos[1]+this.origin.y, pos[2]+this.origin.z);
            this.arrowhead.rotationQuaternion = this.quat.babylon();
        }
    }

    set visibility(visible) {
        this.mesh.visibility = visible;
        if (this.arrowhead)
            this.arrowhead.visibility = visible;
    }
}

