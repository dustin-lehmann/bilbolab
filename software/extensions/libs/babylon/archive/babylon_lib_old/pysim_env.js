/*
  pysim_env.js
  BabylonJS Environment for Pysim visualization.
  This file sets up the scene, camera, lights, UI, and notifies the backend when the scene is loaded.
*/

var world_objects = {};

// =====================================================================================================================
// Class representing the simulation scene.
class PysimScene extends Scene {
    constructor(id, config) {
        super(id);
        this.config = config;
        console.log("Config:", config);
        this.createScene();
    }

    createScene() {
        // --- CAMERA ---
        this.camera = new BABYLON.ArcRotateCamera("Camera", 0, 0, 20, new BABYLON.Vector3(0, 0.1, 0), this.scene);
        this.camera.setPosition(new BABYLON.Vector3(0.02, 1.11, 2.3));
        this.camera.attachControl(this.canvas, true);
        this.camera.inputs.attached.keyboard.detachControl();
        this.camera.wheelPrecision = 100;
        this.camera.minZ = 0.1;

        // --- LIGHTS ---
        this.light1 = new BABYLON.HemisphericLight("light", new BABYLON.Vector3(0.5, 1, 0), this.scene);
        this.light1.intensity = 1;

        const gl = new BABYLON.GlowLayer("glow", this.scene);
        gl.intensity = 0;

        // --- BACKGROUND ---
        this.defaultBackgroundColor = new BABYLON.Color3(1, 1, 1);
        this.scene.clearColor = this.defaultBackgroundColor;

        // --- UI SETUP ---
        this.ui = BABYLON.GUI.AdvancedDynamicTexture.CreateFullscreenUI("ui", true, this.scene);
        this.textbox_time = new BABYLON.GUI.TextBlock();
        this.textbox_time.font_size = 20;
        this.textbox_time.text = "";
        this.textbox_time.color = "black";
        this.textbox_time.paddingTop = 3;
        this.textbox_time.paddingLeft = 3;
        this.textbox_time.textVerticalAlignment = BABYLON.GUI.Control.VERTICAL_ALIGNMENT_TOP;
        this.textbox_time.textHorizontalAlignment = BABYLON.GUI.Control.HORIZONTAL_ALIGNMENT_LEFT;
        this.ui.addControl(this.textbox_time);

        this.textbox_status = new BABYLON.GUI.TextBlock();
        this.textbox_status.font_size = 40;
        this.textbox_status.text = "";
        this.textbox_status.color = "black";
        this.textbox_status.paddingTop = 3;
        this.textbox_status.paddingRight = 30;
        this.textbox_status.textVerticalAlignment = BABYLON.GUI.Control.VERTICAL_ALIGNMENT_TOP;
        this.textbox_status.textHorizontalAlignment = BABYLON.GUI.Control.HORIZONTAL_ALIGNMENT_RIGHT;
        this.ui.addControl(this.textbox_status);

        this.textbox_title = new BABYLON.GUI.TextBlock();
        this.textbox_title.font_size = 40;
        this.textbox_title.text = "";
        this.textbox_title.color = "black";
        this.textbox_title.paddingTop = 3;
        this.textbox_title.paddingLeft = 3;
        this.textbox_title.textVerticalAlignment = BABYLON.GUI.Control.VERTICAL_ALIGNMENT_TOP;
        this.textbox_title.textHorizontalAlignment = BABYLON.GUI.Control.HORIZONTAL_ALIGNMENT_CENTER;
        this.ui.addControl(this.textbox_title);

        // --- COORDINATE SYSTEM ---
        drawCoordinateSystem(this.scene, 0.25);

        // --- NOTIFY BACKEND THAT SCENE IS LOADED ---
        backend.sendMessage({ 'loaded': 1 });
        return this.scene;
    }

    buildWorld() {
        if (!this.config.world || !this.config.world.objects) {
            console.warn("No world objects specified in the config");
            return;
        }
        for (const [key, value] of Object.entries(this.config.world.objects)) {
            if (value.object_type in this.config.object_config) {
                const babylon_object_name = this.config.object_config[value.object_type]['BabylonObject'];
                let objectPtr = eval(babylon_object_name);
                world_objects[key] = new objectPtr(this.scene, key, value, this.config.object_config[value.object_type]['config']);
            } else {
                console.warn("Cannot find the object type in the object definition for", key);
            }
        }
    }

    onSample(sample) {
        // console.log("Received sample:", sample);
        if (sample.type) {
            this.parseSample(sample.type, sample.data);
        }
    }

    parseSample(command, data) {
        switch (command) {
            case 'addObject':
                // Use 'data' field from the message instead of 'config'
                this.addObject(data.id, data.class, data.data);
                break;
            case 'removeObject':
                this.removeObject(data.id);
                break;
            case 'set':
                if (data.id === 'scene') {
                    break;
                } else if (data.id in world_objects) {
                    world_objects[data.id].set(data.parameter, data.value);
                }
                break;
            case 'update':
                if (data.id in world_objects) {
                    world_objects[data.id].update(data.data);
                }
                break;
            case 'function':
                if (data.id in world_objects) {
                    let fun = world_objects[data.id][data.function];
                    fun(...data.arguments);
                }
        }
    }

    addObject(object_id, object_class, data) {
        console.log("Adding object with id " + object_id + " and class " + object_class);
        if (object_class in this.config.object_mappings) {
            const babylon_object_name = this.config.object_mappings[object_class]['BabylonObject'];
            const object_config = Object.assign({}, this.config.object_mappings[object_class]['config'], data);
            var objectPtr = eval(babylon_object_name);
            world_objects[object_id] = new objectPtr(this.scene, object_id, object_config);
        }
    }

    removeObject(object_id) {
        console.log("Removing object " + object_id);
        if (object_id in world_objects) {
            world_objects[object_id].delete();
            delete world_objects[object_id];
        }
    }
}
