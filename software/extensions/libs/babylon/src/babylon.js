import {
    ArcRotateCamera,
    DirectionalLight,
    GlowLayer,
    HemisphericLight,
    MeshBuilder,
    PointerEventTypes,
    Scene as BabylonScene,
    ShadowGenerator,
    StandardMaterial,
    Vector3,
} from "@babylonjs/core";

// import {VideoRecorder} from "@babylonjs/core/Misc/videoRecorder";

import {VideoRecorder} from '@babylonjs/core';

/* === CUSTOM IMPORTS =============================================================================================== */
import {Websocket} from "./lib/websocket.js"
import {
    coordinatesFromBabylon,
    coordinatesToBabylon,
    deepMerge,
    getBabylonColor,
    getBabylonColor3,
    Scene
} from "./lib/babylon_utils.js"

import {drawCoordinateSystem} from "./lib/objects/coordinate_system.js";
import {BabylonSimpleFloor} from "./lib/objects/floor/floor.js";
import {BabylonBox, BabylonWall_Fancy} from "./lib/objects/box/box.js";
import {Quaternion} from "./lib/quaternion.js";
import {BabylonObject, BabylonObjectGroup} from "./lib/objects.js";
import {BabylonBilbo, BabylonBilboRealistic, BabylonSimpleBilbo} from "./lib/objects/bilbo/bilbo.js";

import {BABYLON_OBJECT_MAPPINGS} from "./lib/objects/mapping.js"
import {
    Callbacks,
    deg2rad,
    getColor,
    removeLeadingAndTrailingSlashes,
    splitPath,
    stringifyObject
} from "../../../gui/src/lib/helpers.js"
import './babylon.css'


/* === EXTERNAL CUSTOM IMPORTS ====================================================================================== */
import "../../../gui/src/lib/styles/widget-styles.css"
import "../../../gui/src/lib/styles/context_menu.css"
import {ButtonWidget} from "../../../gui/src/lib/objects/js/buttons.js";
import {LineScrollTextWidget} from "../../../gui/src/lib/objects/js/text.js";
import {ContextMenuItem} from "../../../gui/src/lib/objects/contextmenu.js";
import {BabylonCircleDrawing, BabylonLineDrawing, BabylonRectangleDrawing} from "./lib/objects/drawings";
import {ArucoStatic} from "./lib/objects/static/static";
import {BabylonFrodo} from "./lib/objects/frodo/frodo";

/* === HELPERS ====================================================================================================== */
function _chooseBestMime() {
    const c = [
        "video/webm;codecs=vp9",
        "video/webm;codecs=vp8",
        "video/webm;codecs=h264", // not everywhere, but sometimes available
        "video/webm"
    ];
    return c.find(t => window.MediaRecorder?.isTypeSupported?.(t)) || "video/webm";
}


/* ================================================================================================================== */
export class Babylon extends Scene {
    is_recording = false;
    // Sliding-window message rate tracker (5s window)
    _msgTimes = [];      // monotonically growing array of timestamps (ms)
    _msgHead = 0;       // index of first still-valid timestamp within _msgTimes

    _resizeArmed = false;

    constructor(id, canvasOrEngine, config = {}, objects = {}) {
        super(canvasOrEngine);

        const default_config = {
            websocket_host: 'localhost',
            websocket_port: '9000',
            coordinate_system_length: 0.5,
            show_coordinate_system: true,


            background_color: [31 / 255, 32 / 255, 35 / 255],
            ambient_color: [0.5, 0.5, 0.5],

            scene: {
                add_fog: true,
                fog_color: [31 / 255, 32 / 255, 35 / 255],
                fog_density: 0.08,
                fog_mode: 'exp2',
                fog_auto_scale: true,
                fog_reference_radius: 0,
            },

            camera: {
                position: [2, -2, 1],
                target: [0, 0, 0],
                alpha: deg2rad(-18),
                beta: deg2rad(70),
                radius: 3.5,
                fov: deg2rad(65),
                radius_lower_limit: 0.5,
                radius_upper_limit: 6,
            },
            lights: {
                hemispheric_direction: [2, -1, 0],
                hemispheric_intensity: 0.5,
                hemispheric_ground_color: [0, 0, 0],
                directional_direction: [-1, -1, -1],
                directional_position: [1, 1, 10],
                directional_intensity: 1.1,
                directional_shadows: true,
                directional_shadow_darkness: 0.4,
                directional2_direction: [1, -1, -1],
                directional2_position: [1, -1, 10],
                directional2_intensity: 0.4,
                directional2_shadows: false,
                directional2_shadow_darkness: 0.4,
            },
            ui: {
                text_color: [1, 1, 1],
                font_size: 40,
            }

        }

        this.config = deepMerge(default_config, config);
        this.id = id;
        this.objects = {}
        this._renderLoopRunning = true; // Scene constructor starts the render loop

        this.canvas = canvasOrEngine;

        console.log('babylon config')
        console.log(config)

        // element.addEventListener('mousedown', e => e.preventDefault()); // stops focus
        this._initializeWebsocket();
        this._initializeScene();
        this._addSceneClickListener();

        this._buildObjectsFromConfig(objects);

        this.callbacks = new Callbacks();
        this.callbacks.add('event');
        this.callbacks.add('log');
        this.callbacks.add('initialized')

        this.callbacks.add('record_start');
        this.callbacks.add('record_stop');
        this.callbacks.add('add_camera');
        this.callbacks.add('websocket_connected');
        this.callbacks.add('websocket_disconnected');
        this.callbacks.add('follow_started');
        this.callbacks.add('follow_stopped');

        this._addOwnCallbacks();
        // this.addTestObjects();


        setTimeout(() => {
            this.log(`Babylon scene initialized. Listening on websocket ${this.config.websocket_host}:${this.config.websocket_port}...`);
        }, 250);

        setTimeout(() => {
            this.callbacks.get('initialized').call();
        }, 500);
    }

    /* === METHODS ================================================================================================== */
    addObject(object) {
        // Check if the object id is already in objects
        if (object.id in this.objects) {
            console.warn(`Object with id ${object.id} already exists`);
            return;
        }

        if (!(object instanceof BabylonObject)) {
            console.warn(`Object is not a BabylonObject`);
            return;
        }

        this.objects[object.id] = object;
        object.parent = this;
        object.callbacks.get('event').register(this._onObjectEvent.bind(this));
        object.callbacks.get('log').register(this._onObjectLog.bind(this));
        object.callbacks.get('send_message').register(this._onObjectSendMessage.bind(this));
        console.log(`BABYLON: Added object with id ${object.id}`);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    removeObject(object) {

        // Check if object is a string
        if (typeof object === 'string') {
            object = this.getObjectByUID(object);
            if (!object) {
                console.warn(`Object with id ${object} does not exist`);
                return;
            }
        }
        if (object.id in this.objects) {
            delete this.objects[object.id];
        } else {
            console.warn(`Object with id ${object.id} does not exist`);
        }

        if (typeof object.delete === 'function') {
            object.delete();
        }
        this.log(`Object ${object.id} removed`, 'warning');
    }

    reset() {
        // Snapshot the values since removeObject mutates this.objects
        const objects = Object.values(this.objects);
        for (const obj of objects) {
            this.removeObject(obj);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    send(msg) {
        this.websocket.send(msg);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    sendEvent(event, id = null) {
        const message = {
            type: 'event',
            id: id,
            event: event,
        }
        this.send(message);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getObjectByUID(uid) {

        uid = removeLeadingAndTrailingSlashes(uid);

        let first_part, remainder;
        [first_part, remainder] = splitPath(uid);

        if (first_part !== this.id) {
            this.log(`getObjectByUID: ${uid} does not match this.id: ${this.id}`);
            return null;
        }
        if (!remainder) {
            return this;
        }

        [first_part, remainder] = splitPath(remainder);

        first_part = `${this.id}/${first_part}`

        if (first_part in this.objects) {
            if (!remainder) {
                return this.objects[first_part];
            } else {
                if (this.objects[first_part] instanceof BabylonObjectGroup) {
                    return this.objects[first_part].getObjectByPath(remainder);
                } else {
                    return null;
                }
            }
        }
        return null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setCamera() {

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setArcRotateCamera(position, target, alpha, beta, radius, fov) {
        this._cancelCameraAnim();
        if (target) this.camera.setTarget(coordinatesToBabylon(target));
        if (position && alpha == null && beta == null && radius == null) {
            this.camera.setPosition(coordinatesToBabylon(position));
        }
        if (alpha != null) this.camera.alpha = alpha;
        if (beta != null) this.camera.beta = beta;
        if (radius != null) this.camera.radius = radius;
        if (fov != null) this.camera.fov = fov;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    animateCamera(start, end, duration, easing) {
        this._cancelCameraAnim();

        if (!start) {
            const t = this.camera.target;
            start = {
                target: [t.x, -t.z, t.y],   // babylon → world coordinates
                alpha: this.camera.alpha,
                beta: this.camera.beta,
                radius: this.camera.radius,
                fov: this.camera.fov,
            };
        }

        const easingFn = {
            linear:     t => t,
            smoothstep: t => t * t * (3 - 2 * t),
            ease_in:    t => t * t,
            ease_out:   t => 1 - (1 - t) * (1 - t),
        }[easing] || (t => t * t * (3 - 2 * t));

        let elapsed = 0;
        this._cameraAnimObserver = this.scene.onBeforeRenderObservable.add(() => {
            elapsed += this.scene.getEngine().getDeltaTime() / 1000;
            const t = Math.min(elapsed / duration, 1);
            const s = easingFn(t);

            const lerp = (a, b) => a + (b - a) * s;
            const lerpArr = (a, b) => a.map((v, i) => lerp(v, b[i]));

            const target = lerpArr(start.target, end.target);
            this.camera.setTarget(coordinatesToBabylon(target));
            this.camera.alpha = lerp(start.alpha, end.alpha);
            this.camera.beta = lerp(start.beta, end.beta);
            this.camera.radius = lerp(start.radius, end.radius);
            this.camera.fov = lerp(start.fov, end.fov);

            if (t >= 1) {
                this._cancelCameraAnim();
            }
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _cancelCameraAnim() {
        if (this._cameraAnimObserver) {
            this.scene.onBeforeRenderObservable.remove(this._cameraAnimObserver);
            this._cameraAnimObserver = null;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    followObject(objectId) {
        this.stopFollowing();

        let target = null;
        for (const obj of Object.values(this.objects)) {
            if (obj.id === objectId) { target = obj; break; }
        }
        if (!target) {
            console.warn(`followObject: object '${objectId}' not found`);
            return;
        }

        this._followTarget = target;
        this._followObserver = this.scene.onBeforeRenderObservable.add(() => {
            const pos = this._followTarget.position;
            if (pos && pos.length >= 2) {
                this.camera.setTarget(coordinatesToBabylon(pos));
            }
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    stopFollowing() {
        if (this._followObserver) {
            this.scene.onBeforeRenderObservable.remove(this._followObserver);
            this._followObserver = null;
        }
        this._followTarget = null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getBabylonVisualization() {
        return this;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getDebugData() {
        const data = {};
        const scene = this.scene;
        const cam = scene?.activeCamera || this.camera;

        const safeVec = (v) => v ? [Number(v.x || 0), Number(v.y || 0), Number(v.z || 0)] : null;
        const deg = (r) => (r != null ? (r * 180 / Math.PI) : null);

        if (!cam) {
            data.camera = {present: false};
            return data;
        }

        const type = (typeof cam.getClassName === 'function') ? cam.getClassName() : (cam.constructor?.name || 'Camera');
        const isTargetCam = (cam.getTarget && typeof cam.getTarget === 'function');
        const hasRotation = !!cam.rotation || !!cam.rotationQuaternion;

        // Common camera info
        const common = {
            present: true,
            type,
            name: cam.name ?? null,
            id: cam.id ?? null,
            uniqueId: cam.uniqueId ?? null,
            mode: cam.mode === 1 ? "ORTHOGRAPHIC" : "PERSPECTIVE",
            fov_deg: cam.mode === 1 ? null : (cam.fov ? deg(cam.fov) : null),

            // Ortho params (useful if mode=ORTHOGRAPHIC)
            orthoLeft: cam.orthoLeft ?? null,
            orthoRight: cam.orthoRight ?? null,
            orthoTop: cam.orthoTop ?? null,
            orthoBottom: cam.orthoBottom ?? null,

            minZ: cam.minZ ?? null,
            maxZ: cam.maxZ ?? null,
            inertia: cam.inertia ?? null,
            position: coordinatesFromBabylon(safeVec(cam.position)),
            target: isTargetCam ? coordinatesFromBabylon(safeVec(cam.getTarget())) : null,
            upVector: coordinatesFromBabylon(safeVec(cam.upVector)),

            // Rotation (if available)
            rotation_euler_deg: (() => {
                if (cam.rotation) {
                    return [deg(cam.rotation.x), deg(cam.rotation.y), deg(cam.rotation.z)];
                }
                if (cam.rotationQuaternion && typeof cam.rotationQuaternion.toEulerAngles === 'function') {
                    const e = cam.rotationQuaternion.toEulerAngles();
                    return [deg(e.x), deg(e.y), deg(e.z)];
                }
                return null;
            })(),
        };

        // Type-specific
        const specific = {};

        // ArcRotateCamera
        if (type === "ArcRotateCamera") {
            specific.arcRotate = {
                alpha_deg: deg(cam.alpha),
                beta_deg: deg(cam.beta),
                radius: cam.radius ?? null,

                // limits
                lowerAlphaLimit_deg: cam.lowerAlphaLimit != null ? deg(cam.lowerAlphaLimit) : null,
                upperAlphaLimit_deg: cam.upperAlphaLimit != null ? deg(cam.upperAlphaLimit) : null,
                lowerBetaLimit_deg: cam.lowerBetaLimit != null ? deg(cam.lowerBetaLimit) : null,
                upperBetaLimit_deg: cam.upperBetaLimit != null ? deg(cam.upperBetaLimit) : null,
                lowerRadiusLimit: cam.lowerRadiusLimit ?? null,
                upperRadiusLimit: cam.upperRadiusLimit ?? null,

                // controls/sensitivities
                wheelPrecision: cam.wheelPrecision ?? null,
                wheelDeltaPercentage: cam.wheelDeltaPercentage ?? null,
                panningSensibility: cam.panningSensibility ?? null,
                angularSensibilityX: cam.angularSensibilityX ?? null,
                angularSensibilityY: cam.angularSensibilityY ?? null,

                // behaviors
                useAutoRotationBehavior: !!cam.useAutoRotationBehavior,
                useBouncingBehavior: !!cam.useBouncingBehavior,
                useFramingBehavior: !!cam.useFramingBehavior,

                // inertial offsets (if user is dragging the mouse)
                inertialAlphaOffset_deg: cam.inertialAlphaOffset != null ? deg(cam.inertialAlphaOffset) : null,
                inertialBetaOffset_deg: cam.inertialBetaOffset != null ? deg(cam.inertialBetaOffset) : null,
                inertialRadiusOffset: cam.inertialRadiusOffset ?? null,
                inertialPanningX: cam.inertialPanningX ?? null,
                inertialPanningY: cam.inertialPanningY ?? null,
            };
        }

        // FollowCamera (if you ever use it)
        if (type === "FollowCamera") {
            specific.follow = {
                lockedTarget: !!cam.lockedTarget,
                radius: cam.radius ?? null,
                heightOffset: cam.heightOffset ?? null,
                rotationOffset_deg: cam.rotationOffset != null ? deg(cam.rotationOffset) : null,
                cameraAcceleration: cam.cameraAcceleration ?? null,
                maxCameraSpeed: cam.maxCameraSpeed ?? null,
            };
        }

        // Free/Universal/Touch cameras share some stuff
        if (type === "FreeCamera" || type === "UniversalCamera" || type === "TouchCamera") {
            specific.freeLike = {
                speed: cam.speed ?? null,
                angularSensibility: cam.angularSensibility ?? null,
                keysUp: cam.keysUp ?? null,
                keysDown: cam.keysDown ?? null,
                keysLeft: cam.keysLeft ?? null,
                keysRight: cam.keysRight ?? null,
                ellipsoid: cam.ellipsoid ? safeVec(cam.ellipsoid) : null,
            };
        }

        data.camera = {...common, ...specific};
        return data;
    }

    getMessagesPerSecond(windowSeconds = 5) {
        const now = (typeof performance !== 'undefined' ? performance.now() : Date.now());
        const windowMs = Math.max(1, (windowSeconds ?? 5) * 1000);
        const cutoff = now - windowMs;

        // Prune anything outside the 5s window
        while (this._msgHead < this._msgTimes.length && this._msgTimes[this._msgHead] < cutoff) {
            this._msgHead++;
        }

        const count = this._msgTimes.length - this._msgHead;
        if (count <= 0) return 0;

        // During startup, only use the span we actually observed so far (grows up to windowMs)
        const firstTs = this._msgTimes[this._msgHead];
        const spanMs = Math.max(1, Math.min(windowMs, now - firstTs));

        // Use (N-1) / span to avoid overestimating with just 1–2 samples
        const intervals = Math.max(0, count - 1);
        const perSec = intervals / (spanMs / 1000);

        return Math.round(perSec);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    startRecording(fileName = "babylonjs.webm", maxDurationSeconds = 0 /* manual stop */, upscale = 1.0) {
        const engine = this.scene?.getEngine?.();
        if (!engine) {
            this.log("No engine for recording.", "error");
            return;
        }
        if (!VideoRecorder.IsSupported(engine)) {
            this.log("Video recording not supported in this browser.", "warning");
            return;
        }
        if (this.is_recording) {
            this.log("Already recording.", "warning");
            return;
        }

        // --- A) Render more pixels while recording ---
        this._prevScaling = engine.getHardwareScalingLevel?.() ?? 1;
        // Smaller number = more pixels. Halving -> 2x resolution; clamp to avoid insane values.
        const scaleDown = 1 / upscale; // 2× internal resolution during recording
        engine.setHardwareScalingLevel(Math.max(0.25, this._prevScaling * scaleDown));

        // --- B) Better codec + higher FPS (if the browser supports it) ---
        const options = {
            fps: 60,
            mimeType: _chooseBestMime(),       // try VP9/VP8/H264-in-webm
            recordChunckSize: 5_000_000        // bigger chunks = fewer file parts
        };

        this._videoRecorder = new VideoRecorder(engine, options);
        this.is_recording = true;
        this.log(`Started recording to "${fileName}" (fps=${options.fps}, mime=${options.mimeType}).`, "important");

        this.callbacks.get('record_start').call(fileName);
        // Save promise so we can clean up *after* finalize
        this._recordingPromise = this._videoRecorder
            .startRecording(fileName, maxDurationSeconds)
            .then((blob) => {
                this.log(`Recording finished (${Math.round((blob?.size || 0) / 1024)} KB).`, "important");

            })
            .catch((err) => this.log(`Recorder error: ${err}`, "error"))
            .finally(() => {
                // Restore resolution and dispose only after finalize
                try {
                    engine.setHardwareScalingLevel(this._prevScaling);
                } catch {
                }
                this._videoRecorder?.dispose?.();
                this._videoRecorder = null;
                this._recordingPromise = null;
                this.callbacks.get('record_stop').call();
            });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    startRecordingHiBitrate(fileName = "babylonjs_highbit.webm", fps = 60, videoBitsPerSecond = 12_000_000, upscale = 1.0) {
        const canvas = this.scene?.getEngine?.().getRenderingCanvas?.();
        if (!canvas) {
            this.log("No canvas for recording.", "error");
            return;
        }
        if (this.is_recording) {
            this.log("Already recording.", "warning");
            return;
        }

        // Optionally render more pixels (upscale > 1 = higher resolution)
        const engine = this.scene.getEngine();
        this._prevScaling = engine.getHardwareScalingLevel?.() ?? 1;
        const scaleDown = 1 / upscale;
        engine.setHardwareScalingLevel(Math.max(0.25, this._prevScaling * scaleDown));

        const mime = _chooseBestMime();
        const stream = canvas.captureStream(fps);
        const rec = new MediaRecorder(stream, {mimeType: mime, videoBitsPerSecond});
        this._customRecorder = rec;
        this.is_recording = true;

        const chunks = [];
        rec.ondataavailable = (e) => {
            if (e.data?.size) chunks.push(e.data);
        };
        rec.onstop = () => {
            const blob = new Blob(chunks, {type: mime});

            if (this._pendingSavePath) {
                this._sendBlobToServer(blob, fileName);
                this._pendingSavePath = null;
            } else {
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = fileName;
                a.click();
                setTimeout(() => URL.revokeObjectURL(a.href), 5000);
            }

            // restore
            try {
                engine.setHardwareScalingLevel(this._prevScaling);
                this.log("Setting back hardware scaling", "important");
            } catch {
                this.log("Failed to restore hardware scaling", "error");
            }
            this._customRecorder = null;
            this.is_recording = false;
            this.log(`High-bitrate recording saved (${Math.round(blob.size / 1024)} KB).`, "important");
            this.callbacks.get('record_stop').call();
        };
        rec.start(1000); // collect data every second
        this.log(`Started high-bitrate recording (fps=${fps}, ~${Math.round(videoBitsPerSecond / 1e6)} Mbps, ${mime}).`, "important");
        this.callbacks.get('record_start').call(fileName);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    stopRecording() {
        // Custom high-bitrate path?
        if (this._customRecorder) {
            try {
                this._customRecorder.stop();               // finalize async -> onstop handler does download + restore + callbacks
                this.log("Stopping high-bitrate recording…", "info");
            } catch (e) {
                this.log(`Stop error (hi-bitrate): ${e}`, "error");
            } finally {
                // Optional: reflect UI state immediately; finalize still fires record_stop later
                this.is_recording = false;
            }
            return true;
        }

        // Built-in Babylon VideoRecorder?
        if (this._videoRecorder) {
            try {
                this._videoRecorder.stopRecording();       // finalize async -> startRecording().finally handles dispose + restore + callbacks
                this.log("Stopping recording…", "info");
            } catch (err) {
                this.log(`Failed to stop recording: ${err}`, "error");
            } finally {
                this.is_recording = false;
            }
            return true;
        }

        this.log("No active recording.", "warning");
        return false;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    log(message, level = 'info') {

        // Check if message is an object
        if (typeof message === 'object') {
            message = stringifyObject(message, true);
        }

        this.callbacks.get('log').call(message, level);
    }

    /* === PRIVATE METHODS ========================================================================================== */
    _initializeWebsocket() {
        this.websocket = new Websocket({host: this.config.websocket_host, port: this.config.websocket_port});
        this.websocket.on('message', this._handleMessage.bind(this));
        this.websocket.on('connected', this._onWebsocketConnect.bind(this));
        this.websocket.on('close', this._onWebsocketDisconnected.bind(this));
        this.websocket.connect();
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _onWebsocketConnect() {
        this.callbacks.get('websocket_connected').call();
        this.log(`Websocket connected`)

        // Restart the render loop (stopped on disconnect)
        if (this.engine && !this._renderLoopRunning) {
            this.engine.runRenderLoop(() => this.scene.render());
            this._renderLoopRunning = true;
        }
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _onWebsocketDisconnected() {
        this.callbacks.get('websocket_disconnected').call();
        this.log(`Websocket disconnected`)
        this.reset();

        // Stop the render loop to prevent WebGL errors on disposed resources
        if (this.engine) {
            this.engine.stopRenderLoop();
            this._renderLoopRunning = false;
        }
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _addOwnCallbacks() {
        this.callbacks.get('record_start').register((fileName) => {
            const event = {
                'type': 'record_start',
                'data': {
                    'fileName': fileName
                }
            }
            this.sendEvent(event, this.id);
        });

        this.callbacks.get('record_stop').register(() => {
            const event = {
                'type': 'record_stop',
                'data': {}
            }
            this.sendEvent(event, this.id);
        });

    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleMessage(msg) {
        this._trackIncomingMessage(); // For tracking how many messages we've received in the last second

        switch (msg.type) {
            case 'init':
                this._handleInitMessage(msg);
                break;
            case 'addObject':
                this._handleAddObjectMessage(msg);
                break;
            case 'removeObject':
                this._handleRemoveObjectMessage(msg);
                break;
            case 'update':
                this._handleUpdateMessage(msg);
                break;
            case 'updateObject':
                this._handleUpdateObjectMessage(msg);
                break;
            case 'updateObjectConfig':
                this._handleUpdateObjectConfigMessage(msg);
                break;
            case 'objectFunction':
                this._handleObjectFunctionMessage(msg);
                break;
            case 'command':
                this._handleCommand(msg);
                break;
            case 'add_camera':
                if (msg.camera) {
                    this.callbacks.get('add_camera').call(msg.camera);
                }
                break;
            case 'set_camera':
                this.setArcRotateCamera(
                    msg.position || null,
                    msg.target || null,
                    msg.alpha != null ? msg.alpha : null,
                    msg.beta != null ? msg.beta : null,
                    msg.radius != null ? msg.radius : null,
                    msg.fov != null ? msg.fov : null,
                );
                break;
            case 'animate_camera':
                this.animateCamera(
                    msg.start || null,
                    msg.end,
                    msg.duration || 2.0,
                    msg.easing || 'smoothstep',
                );
                break;
            case 'follow_object':
                this.followObject(msg.object_id);
                this.callbacks.get('follow_started').call(msg.object_id);
                break;
            case 'stop_following':
                this.stopFollowing();
                this.callbacks.get('follow_stopped').call();
                break;
            case 'set_dropdown':
                this._applyDropdown(msg.items || [], msg.selected || null);
                break;
            case 'update_dropdown_selection':
                if (this._dropdown && msg.selected != null) {
                    this._dropdown.value = msg.selected;
                }
                break;
            default:
                console.warn(`Unknown message type: ${msg.type}`);
                break;
        }
    }

    _trackIncomingMessage() {
        const now = (typeof performance !== 'undefined' ? performance.now() : Date.now());
        const WINDOW_MS = 5000;

        this._msgTimes.push(now);

        // Drop anything older than (now - 5s) by advancing the head
        const cutoff = now - WINDOW_MS;
        while (this._msgHead < this._msgTimes.length && this._msgTimes[this._msgHead] < cutoff) {
            this._msgHead++;
        }

        // Compact occasionally to avoid the array growing forever
        if (this._msgHead > 512 && this._msgHead > (this._msgTimes.length >> 1)) {
            this._msgTimes = this._msgTimes.slice(this._msgHead);
            this._msgHead = 0;
        }
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _applyDropdown(items, selected) {
        if (!this._dropdown) return;
        this._dropdown.innerHTML = '';
        if (!items || items.length === 0) {
            this._dropdown.style.display = 'none';
            return;
        }
        for (const item of items) {
            const opt = document.createElement('option');
            opt.value = item.key;
            opt.textContent = item.label;
            this._dropdown.appendChild(opt);
        }
        if (selected != null) {
            this._dropdown.value = selected;
        }
        this._dropdown.style.display = 'block';
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleInitMessage(msg) {
        this.log(`Received init message`);
        if (msg.payload) {
            if (msg.payload.config) {
                this._applyInitConfig(msg.payload.config);
            }
            if (msg.payload.objects) {
                this._buildObjectsFromConfig(msg.payload.objects);
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _applyInitConfig(config) {
        // Camera
        if (config.camera && this.camera) {
            const cam = config.camera;
            // Apply target first (before alpha/beta/radius, which depend on it)
            if (cam.target) this.camera.setTarget(coordinatesToBabylon(cam.target));
            // position recalculates alpha/beta/radius, so only use it when those aren't explicitly set
            const hasExplicitOrbit = cam.alpha != null || cam.beta != null || cam.radius != null;
            if (cam.position && !hasExplicitOrbit) this.camera.setPosition(coordinatesToBabylon(cam.position));
            // Explicit orbit parameters take precedence over position
            if (cam.alpha != null) this.camera.alpha = cam.alpha;
            if (cam.beta != null) this.camera.beta = cam.beta;
            if (cam.radius != null) this.camera.radius = cam.radius;
            if (cam.fov != null) this.camera.fov = cam.fov;
            if (cam.radius_lower_limit != null) this.camera.lowerRadiusLimit = cam.radius_lower_limit;
            if (cam.radius_upper_limit != null) this.camera.upperRadiusLimit = cam.radius_upper_limit;
        }

        // Background & ambient
        if (config.background_color) {
            this.scene.clearColor = getBabylonColor(config.background_color);
        }
        if (config.ambient_color) {
            this.scene.ambientColor = getBabylonColor3(config.ambient_color);
        }

        // Fog
        if (config.scene) {
            const sc = config.scene;
            if (sc.add_fog) {
                if (sc.fog_mode === 'exp2') this.scene.fogMode = BabylonScene.FOGMODE_EXP2;
                else if (sc.fog_mode === 'linear') this.scene.fogMode = BabylonScene.FOGMODE_LINEAR;
                else if (sc.fog_mode === 'exp') this.scene.fogMode = BabylonScene.FOGMODE_EXP;
                if (sc.fog_density != null) this.scene.fogDensity = sc.fog_density;
                if (sc.fog_color) this.scene.fogColor = getBabylonColor3(sc.fog_color);
            }
        }

        // Lights
        if (config.lights) {
            const lc = config.lights;
            if (lc.hemispheric_direction && this.hemisphericLight) {
                this.hemisphericLight.direction = coordinatesToBabylon(lc.hemispheric_direction);
            }
            if (lc.hemispheric_intensity != null && this.hemisphericLight) {
                this.hemisphericLight.intensity = lc.hemispheric_intensity;
            }
            if (lc.hemispheric_ground_color && this.hemisphericLight) {
                this.hemisphericLight.groundColor = getBabylonColor3(lc.hemispheric_ground_color);
            }
            if (lc.directional_direction && this.dirLight) {
                this.dirLight.direction = coordinatesToBabylon(lc.directional_direction);
            }
            if (lc.directional_position && this.dirLight) {
                this.dirLight.position = coordinatesToBabylon(lc.directional_position);
            }
            if (lc.directional_intensity != null && this.dirLight) {
                this.dirLight.intensity = lc.directional_intensity;
            }
            // Shadows for directional 1
            if (lc.directional_shadows != null && this.dirLight) {
                if (lc.directional_shadows && !this.scene.shadowGenerator) {
                    this._enableShadows(this.dirLight, 'shadowGenerator', lc.directional_shadow_darkness ?? 0.4);
                } else if (!lc.directional_shadows && this.scene.shadowGenerator) {
                    this.scene.shadowGenerator.dispose();
                    this.scene.shadowGenerator = null;
                    this.dirLight.shadowEnabled = false;
                }
            }
            if (lc.directional_shadow_darkness != null && this.scene.shadowGenerator) {
                this.scene.shadowGenerator.setDarkness(lc.directional_shadow_darkness);
            }

            if (lc.directional2_direction && this.dirLight2) {
                this.dirLight2.direction = coordinatesToBabylon(lc.directional2_direction);
            }
            if (lc.directional2_position && this.dirLight2) {
                this.dirLight2.position = coordinatesToBabylon(lc.directional2_position);
            }
            if (lc.directional2_intensity != null && this.dirLight2) {
                this.dirLight2.intensity = lc.directional2_intensity;
            }
            // Shadows for directional 2
            if (lc.directional2_shadows != null && this.dirLight2) {
                if (lc.directional2_shadows && !this.scene.shadowGenerator2) {
                    this._enableShadows(this.dirLight2, 'shadowGenerator2', lc.directional2_shadow_darkness ?? 0.4);
                } else if (!lc.directional2_shadows && this.scene.shadowGenerator2) {
                    this.scene.shadowGenerator2.dispose();
                    this.scene.shadowGenerator2 = null;
                    this.dirLight2.shadowEnabled = false;
                }
            }
            if (lc.directional2_shadow_darkness != null && this.scene.shadowGenerator2) {
                this.scene.shadowGenerator2.setDarkness(lc.directional2_shadow_darkness);
            }
        }

        // Additional camera views (for BabylonContainer to consume)
        if (config.cameras) {
            this.config.cameras = config.cameras;
        }

        // Coordinate system — dispose old axes, then redraw with the correct length
        for (const name of ['axisX', 'axisY', 'axisZ']) {
            const mesh = this.scene.getMeshByName(name);
            if (mesh) mesh.dispose();
        }
        if (config.show_coordinate_system !== false) {
            const len = config.coordinate_system_length ?? this.config.coordinate_system_length;
            drawCoordinateSystem(this.scene, len);
        }

        // Rebuild light helpers now that the real light positions/directions are applied
        this._rebuildLightHelpers();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _enableShadows(light, sceneProperty, darkness = 0.4) {
        light.shadowEnabled = true;
        const gen = new ShadowGenerator(1024, light);
        this.scene[sceneProperty] = gen;
        gen.useExponentialShadowMap = true;
        gen.depthScale = 200;
        gen.forceBackFacesOnly = true;
        gen.usePercentageCloserFiltering = true;
        gen.useContactHardeningShadowMap = true;
        gen.filteringQuality = ShadowGenerator.QUALITY_HIGH;
        gen.bias = 1e-6;
        gen.setDarkness(darkness);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _rebuildLightHelpers() {
        // Dispose existing helpers so we can rebuild with current light values
        const old = this.scene.meshes.filter(m => m.name.startsWith('_lightHelper_'));
        for (const m of old) {
            if (m.material) m.material.dispose();
            m.dispose();
        }
        this._createLightHelpers();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _createLightHelpers() {
        const radius = 0.08;
        const arrowLen = 2.0;
        const sphereRadius = 0.3;

        const makeMat = (name, rgb) => {
            const m = new StandardMaterial(name, this.scene);
            m.disableLighting = true;
            m.emissiveColor = getBabylonColor3(rgb);
            return m;
        };

        // Hemispheric — arrow from origin in light direction (yellow)
        if (this.hemisphericLight) {
            const hDir = this.hemisphericLight.direction.normalize().scale(arrowLen);
            const hPath = [Vector3.Zero(), hDir];
            const hTube = MeshBuilder.CreateTube("_lightHelper_hemi_dir", {path: hPath, radius, tessellation: 8}, this.scene);
            hTube.material = makeMat("_lightHelper_hemi_mat", [1, 1, 0]);
            hTube.isPickable = false;
            hTube.setEnabled(false);
        }

        // Directional 1 — sphere + arrow (orange)
        if (this.dirLight) {
            const d1Mat = makeMat("_lightHelper_dir1_mat", [1, 0.5, 0]);

            const d1Sphere = MeshBuilder.CreateSphere("_lightHelper_dir1_pos", {diameter: sphereRadius * 2}, this.scene);
            d1Sphere.position = this.dirLight.position.clone();
            d1Sphere.material = d1Mat;
            d1Sphere.isPickable = false;
            d1Sphere.setEnabled(false);

            const d1End = this.dirLight.position.add(this.dirLight.direction.normalize().scale(arrowLen));
            const d1Tube = MeshBuilder.CreateTube("_lightHelper_dir1_dir", {path: [this.dirLight.position.clone(), d1End], radius, tessellation: 8}, this.scene);
            d1Tube.material = d1Mat;
            d1Tube.isPickable = false;
            d1Tube.setEnabled(false);
        }

        // Directional 2 — sphere + arrow (cyan)
        if (this.dirLight2) {
            const d2Mat = makeMat("_lightHelper_dir2_mat", [0, 1, 1]);

            const d2Sphere = MeshBuilder.CreateSphere("_lightHelper_dir2_pos", {diameter: sphereRadius * 2}, this.scene);
            d2Sphere.position = this.dirLight2.position.clone();
            d2Sphere.material = d2Mat;
            d2Sphere.isPickable = false;
            d2Sphere.setEnabled(false);

            const d2End = this.dirLight2.position.add(this.dirLight2.direction.normalize().scale(arrowLen));
            const d2Tube = MeshBuilder.CreateTube("_lightHelper_dir2_dir", {path: [this.dirLight2.position.clone(), d2End], radius, tessellation: 8}, this.scene);
            d2Tube.material = d2Mat;
            d2Tube.isPickable = false;
            d2Tube.setEnabled(false);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _buildObjectsFromConfig(objects) {
        // Loop through the objects keys and values
        for (const [key, value] of Object.entries(objects)) {
            if (value.id in this.objects) continue;  // skip already-registered objects (by uid)
            const type = value.type;
            const object_class = BABYLON_OBJECT_MAPPINGS[type];
            if (!object_class) {
                this.log(`Unknown object type: ${type}`, "error");
                continue;
            }
            const object = new object_class(value.id, this, value);
            this.addObject(object);
        }
    }

    _buildObjectFromConfig(object_payload) {
        const type = object_payload.type;
        const object_class = BABYLON_OBJECT_MAPPINGS[type];
        if (!object_class) {
            this.log(`Unknown object type: ${type}`, "error");
            return;
        }
        const object = new object_class(object_payload.id, this, object_payload);
        this.addObject(object);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleAddObjectMessage(msg) {
        this._buildObjectFromConfig(msg.payload);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleRemoveObjectMessage(msg) {
        console.log(`Received remove object message:`);
        console.log(msg);
        this.removeObject(msg.id);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleUpdateMessage(msg) {

        if (!('updates' in msg)) {
            this.log(`Received update message without message field: ${msg}`, "error");
            return;
        }

        for (const [id, update] of Object.entries(msg.updates)) {
            const object = this.getObjectByUID(id);
            if (!object) {
                this.log(`Received update for unknown object: ${id}`, "error");
                continue;
            }
            object.update(update)
        }

    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleUpdateObjectMessage(msg) {
        this.log(`Received update object message:`);
        this.log(msg);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleUpdateObjectConfigMessage(msg) {
        this.log(`Received update object config message:`);
        this.log(msg);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleObjectFunctionMessage(msg) {
        const id = msg.id;
        const fnName = msg.function;
        const args = msg.arguments || {};

        if (!id || !fnName) {
            this.log(`objectFunction: missing id or function name`, "error");
            return;
        }

        const object = this.getObjectByUID(id);
        if (!object) {
            this.log(`objectFunction: unknown object ${id}`, "error");
            return;
        }

        if (typeof object[fnName] !== 'function') {
            this.log(`objectFunction: ${fnName} is not a function on ${id}`, "error");
            return;
        }

        // Call with keyword args as positional args (ordered by the arguments dict)
        const argValues = Object.values(args);
        object[fnName](...argValues);
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleCommand(msg) {
        const command = msg.command;
        const params = msg.params || {};
        switch (command) {
            case 'startRecording':
                this._startRecordingFromCommand(params);
                break;
            case 'stopRecording':
                this.stopRecording();
                break;
            case 'close':
                this.websocket.options.reconnect = false;
                this.websocket.socket?.close();
                window.close();
                break;
            case 'setTitle':
                if (this.container?.top_bar_title) {
                    this.container.top_bar_title.textContent = params.text ?? '';
                }
                break;
            case 'setLabel':
                this._handleSetLabel(params);
                break;
            case 'removeLabel':
                this._handleRemoveLabel(params);
                break;
            default:
                this.log(`Unknown command: ${command}`, "warning");
                break;
        }
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleSetLabel(params) {
        const id = params.id;
        const text = params.text ?? '';
        if (!id || !this.container?._overlayLabels) return;

        let entry = this.container._overlayLabels.get(id);
        if (!entry) {
            const el = document.createElement('div');
            el.style.cssText =
                'position:absolute; background:rgba(0,0,0,0.6); color:#fff; font-family:sans-serif; ' +
                'font-size:14px; padding:4px 10px; border-radius:4px; white-space:pre;';
            this.container._overlayLabelsContainer.appendChild(el);
            entry = { el, x: 0.05, y: 0.95, fontSize: 14 };
            this.container._overlayLabels.set(id, entry);
        }
        // Update position/style if provided
        if (params.x != null) entry.x = params.x;
        if (params.y != null) entry.y = params.y;
        if (params.fontSize != null) entry.fontSize = params.fontSize;
        if (params.color) entry.el.style.color = params.color;
        if (params.background) entry.el.style.background = params.background;
        entry.el.style.fontSize = entry.fontSize + 'px';

        // Position the DOM element using normalized coords (x: 0=left..1=right, y: 0=top..1=bottom)
        // Use CSS transform to anchor the element at the correct point
        const xPct = (entry.x * 100).toFixed(2);
        const yPct = (entry.y * 100).toFixed(2);
        entry.el.style.left = xPct + '%';
        entry.el.style.top = yPct + '%';
        entry.el.style.transform = `translate(-${xPct}%, -${yPct}%)`;

        entry.el.textContent = text;
        entry.el.style.display = text ? '' : 'none';
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _handleRemoveLabel(params) {
        const id = params.id;
        if (!id || !this.container?._overlayLabels) return;

        const entry = this.container._overlayLabels.get(id);
        if (entry) {
            entry.el.remove();
            this.container._overlayLabels.delete(id);
        }
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _startRecordingFromCommand(params) {
        const fileName = params.filename || "babylonjs.webm";
        const fps = params.fps || 60;
        const bitrate = params.bitrate || 12_000_000;
        const savePath = params.save_path || null;
        const overlay = params.overlay || false;
        const upscale = params.upscale || 1.0;

        // Store save_path so the onstop handlers know where to send the blob
        this._pendingSavePath = savePath;

        if (overlay && this.container) {
            this.container.startRecordingHiBitrateWithOverlay({fileName, fps, videoBitsPerSecond: bitrate, upscale});
        } else {
            this.startRecordingHiBitrate(fileName, fps, bitrate, upscale);
        }
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    async _sendBlobToServer(blob, fileName) {
        const CHUNK_SIZE = 48_000; // ~48 KB raw -> ~64 KB base64 (avoids WS continuation frames)
        const totalChunks = Math.ceil(blob.size / CHUNK_SIZE);
        this.log(`Sending recording to server: ${fileName} (${totalChunks} chunks, ${Math.round(blob.size / 1024)} KB)`, "important");

        for (let i = 0; i < totalChunks; i++) {
            const slice = blob.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE);
            const base64 = await this._blobToBase64(slice);
            this.send({
                type: 'recordingData',
                fileName,
                chunkIndex: i,
                totalChunks,
                data: base64,
            });
            // Yield briefly so the server can process each chunk
            if (i % 10 === 9) await new Promise(r => setTimeout(r, 0));
        }

        this.send({
            type: 'recordingComplete',
            fileName,
        });
        this.log(`Recording data sent to server: ${fileName}`, "important");
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    _blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                // result is "data:<mime>;base64,XXXX" — strip the prefix
                const base64 = reader.result.split(',')[1];
                resolve(base64);
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }

    /* --------------------------------------------------------------------------------------------------------------- */
    // _addGlobalResizeListener() {
    //     // const engine = new Engine(this.canvas, true, {preserveDrawingBuffer: true, stencil: true});
    //     const engine = this.scene.getEngine();
    //
    //     // This ensures Babylon accounts for HiDPI / Retina displays
    //     engine.setHardwareScalingLevel(1 / window.devicePixelRatio);
    //
    //     // Resize on window change
    //     window.addEventListener("resize", () => {
    //         engine.resize();
    //     });
    // }

    _addGlobalResizeListener() {
        if (this._resizeArmed) return;    // <- guard
        this._resizeArmed = true;
        const engine = this.scene.getEngine();
        const canvas = engine.getRenderingCanvas();
        let lastDPR = -1;

        const applyDPRAndResize = () => {
            const dpr = Math.max(1, window.devicePixelRatio || 1);
            // Update hardware scaling **only if** DPR changed
            if (dpr !== lastDPR) {
                engine.setHardwareScalingLevel(1 / dpr);
                lastDPR = dpr;
            }

            // Make the backing store exactly CSS size * DPR (rounded to ints)
            const rect = canvas.getBoundingClientRect();
            const width = Math.max(1, Math.round(rect.width * dpr));
            const height = Math.max(1, Math.round(rect.height * dpr));

            // Only touch the engine if size actually changed (prevents extra frames)
            if (engine.getRenderWidth(true) !== width || engine.getRenderHeight(true) !== height) {
                engine.setSize(width, height, true);
            } else {
                // Still notify Babylon so projection matrices pick up aspect properly
                engine.resize(true);
            }
        };

        // 1) Window resize (covers most layout changes)
        window.addEventListener('resize', applyDPRAndResize);

        // 2) DPR/zoom changes (Chrome/Safari/Edge)
        if (window.matchMedia) {
            // Re-arm a new media query every time, since the expression uses the current DPR
            const armResolutionWatcher = () => {
                const mq = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
                const handler = () => {
                    mq.removeEventListener?.('change', handler);
                    armResolutionWatcher();
                    applyDPRAndResize();
                };
                mq.addEventListener?.('change', handler);
            };
            armResolutionWatcher();
        }

        // 3) VisualViewport scale changes (Safari/iPadOS often fires this)
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', applyDPRAndResize);
            window.visualViewport.addEventListener('scroll', applyDPRAndResize); // some browsers signal zoom via “scroll”
        }

        // 4) Container resize (e.g. split pane, tabs, flexbox)
        if (typeof ResizeObserver !== 'undefined') {
            this._resizeObserver = new ResizeObserver(applyDPRAndResize);
            // Observe the canvas’ parent to catch layout changes
            const parent = canvas.parentElement || canvas;
            this._resizeObserver.observe(parent);
        }

        // Initial sizing
        applyDPRAndResize();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _initializeScene() {

        // — CAMERA —
        const camera = new ArcRotateCamera("Camera",
            this.config.camera.alpha, this.config.camera.beta,
            this.config.camera.radius, coordinatesToBabylon(this.config.camera.target), this.scene);

        if (this.config.camera.position) {
            camera.setPosition(coordinatesToBabylon(this.config.camera.position));
        }
        camera.attachControl(this.canvas, true);
        camera.inputs.attached.keyboard.detachControl();
        camera.wheelPrecision = 100;
        camera.minZ = 0.1;
        camera.lowerBetaLimit = 0.0;            // optional: avoid exactly straight-down
        camera.upperBetaLimit = Math.PI / 2 - 0.05;    // never go below the ground plane
        camera.lowerRadiusLimit = this.config.camera.radius_lower_limit;
        camera.upperRadiusLimit = this.config.camera.radius_upper_limit;
        camera.fov = this.config.camera.fov;
        this.camera = camera;

        // this.framing = new FramingBehavior()
        // camera.addBehavior(this.framing);
        // this.framing.radiusScale = 1.2;       // padding around the mesh
        // this.framing.focusOnFramedObject = true;
        //
        // this.scene.animationsEnabled = true;
        // console.log(camera.getBehaviorByName("Framing"));  // should log your FramingBehavior instance


        // camera.onViewMatrixChangedObservable.add(() => {
        //     // serialize exactly the numbers you’ll want to hard‐code next time
        //     const cfg = {
        //         alpha: camera.alpha,
        //         beta: camera.beta,
        //         radius: camera.radius,
        //         target: [camera.target.x, camera.target.y, camera.target.z],
        //         position: [camera.position.x, camera.position.y, camera.position.z]
        //     };
        //     console.log("NEW CAMERA CONFIG:\n", JSON.stringify(cfg, null, 2));
        // });

        // now fence focus as desired (pick A or B)
        this.canvas.setAttribute('tabindex', '-1');           // A) unfocusable
// or
        this.canvas.tabIndex = 0;                             // B) keyboard ok
        this.canvas.addEventListener('mousedown', e => e.preventDefault(), {capture: true});

        // — LIGHT —
        const lc = this.config.lights;
        this.hemisphericLight = new HemisphericLight("light", coordinatesToBabylon(lc.hemispheric_direction), this.scene);
        this.hemisphericLight.intensity = lc.hemispheric_intensity;
        this.hemisphericLight.groundColor = getBabylonColor3(lc.hemispheric_ground_color);
        new GlowLayer("glow", this.scene).intensity = 0.1;

        // - SHADOW -
        this.dirLight = new DirectionalLight(
            "shadowLight",
            new Vector3(0, 0, 0),
            this.scene
        );
        this.dirLight.position = coordinatesToBabylon(lc.directional_position);
        this.dirLight.direction = coordinatesToBabylon(lc.directional_direction);
        this.dirLight.intensity = lc.directional_intensity;

        if (lc.directional_shadows) {
            this._enableShadows(this.dirLight, 'shadowGenerator', lc.directional_shadow_darkness);
        }

        this.dirLight2 = new DirectionalLight(
            "shadowLight2",
            new Vector3(0, 0, 0),
            this.scene
        );
        this.dirLight2.position = coordinatesToBabylon(lc.directional2_position);
        this.dirLight2.direction = coordinatesToBabylon(lc.directional2_direction);
        this.dirLight2.intensity = lc.directional2_intensity;

        if (lc.directional2_shadows) {
            this._enableShadows(this.dirLight2, 'shadowGenerator2', lc.directional2_shadow_darkness);
        }

        // — BACKGROUND —
        this.scene.clearColor = getBabylonColor(this.config.background_color);

        this.scene.ambientColor = getBabylonColor3(this.config.ambient_color);

        if (this.config.scene.add_fog) {
            if (this.config.scene.fog_mode === 'exp2') {
                this.scene.fogMode = BabylonScene.FOGMODE_EXP2;
            } else if (this.config.scene.fog_mode === 'linear') {
                this.scene.fogMode = BabylonScene.FOGMODE_LINEAR;
            } else if (this.config.scene.fog_mode === 'exp') {
                this.scene.fogMode = BabylonScene.FOGMODE_EXP;
            } else {
                console.warn(`Unknown fog mode: ${this.config.scene.fog_mode}`);
            }
            this.scene.fogDensity = this.config.scene.fog_density;
            this.scene.fogColor = getBabylonColor3(this.config.scene.fog_color);

            // Auto-scale fog density with camera radius so apparent fog stays
            // constant regardless of zoom level.
            if (this.config.scene.fog_auto_scale) {
                const baseDensity = this.config.scene.fog_density;
                const refRadius = this.config.scene.fog_reference_radius > 0
                    ? this.config.scene.fog_reference_radius
                    : this.camera.radius;  // use initial radius as reference
                this.camera.onViewMatrixChangedObservable.add(() => {
                    if (this.scene.fogMode !== BabylonScene.FOGMODE_NONE) {
                        this.scene.fogDensity = baseDensity * (refRadius / this.camera.radius);
                    }
                });
            }
        }


        // — COORDINATES +
        if (this.config.show_coordinate_system) {
            drawCoordinateSystem(this.scene, this.config.coordinate_system_length);
        }

        // Light helpers are created in _applyInitConfig after the real light
        // settings arrive, so that they reflect the user-provided positions.

        // once, after scene creation:
        this.scene.setRenderingOrder(
            0,
            null, // opaque
            null, // alphaTest
            // transparent compare
            (a, b) => {
                const cam = this.scene.activeCamera;
                const da = Vector3.Distance(cam.position, a.getBoundingInfo().boundingSphere.centerWorld);
                const db = Vector3.Distance(cam.position, b.getBoundingInfo().boundingSphere.centerWorld);
                // draw far first, near last (so near blends over far)
                return db - da;
            }
        );

        // const engine = this.scene.getEngine();
        // console.log(engine);
        //
        // engine.runRenderLoop(() => {
        //     // Skip if the canvas has zero size (prevents GL_INVALID_FRAMEBUFFER warnings)
        //     if (!engine.getRenderWidth(true) || !engine.getRenderHeight(true)) return;
        //     this.scene.render();
        // });

        // — DROPDOWN OVERLAY —
        this._dropdown = document.createElement('select');
        this._dropdown.classList.add('babylon-dropdown');
        this._dropdown.style.display = 'none';
        this._dropdown.addEventListener('change', () => {
            this.sendEvent({type: 'dropdown_select', selected: this._dropdown.value});
        });
        // Append to the canvas container so it overlays the 3D viewport
        const canvasContainer = this.canvas.parentElement;
        if (canvasContainer) {
            canvasContainer.appendChild(this._dropdown);
        }

        return this.scene;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    get selectedDropdownValue() {
        if (!this._dropdown || this._dropdown.style.display === 'none') return null;
        return this._dropdown.value || null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _addSceneClickListener() {
        // Transparent ground plane for picking (floor tiles are not pickable)
        this._pickPlane = MeshBuilder.CreateGround(
            '__pickPlane', {width: 1000, height: 1000}, this.scene
        );
        this._pickPlane.isPickable = true;
        this._pickPlane.visibility = 0;  // fully transparent but still pickable

        this.scene.onPointerObservable.add((pointerInfo) => {
            if (pointerInfo.type === PointerEventTypes.POINTERDOWN) {
                this._handleSingleSceneClick();

            } else if (pointerInfo.type === PointerEventTypes.POINTERDOUBLETAP) {
                this._handleDoubleSceneClick();
            }
        });

        // Middle-click on canvas → floor_middleclick event
        this.canvas.addEventListener('pointerdown', (evt) => {
            if (evt.button !== 1) return;
            evt.preventDefault();
            const pick = this.scene.pick(this.scene.pointerX, this.scene.pointerY);
            if (pick.hit) {
                const p = pick.pickedPoint;
                this.sendEvent({
                    type: 'floor_middleclick',
                    position: [p.x, -p.z, p.y],
                });
            }
        });

        // Right-click on canvas → floor_rightclick event
        this.canvas.addEventListener('contextmenu', (evt) => {
            evt.preventDefault();
            const pick = this.scene.pick(this.scene.pointerX, this.scene.pointerY);
            if (pick.hit) {
                const p = pick.pickedPoint;
                const pos = [p.x, -p.z, p.y];
                this.sendEvent({
                    type: 'floor_rightclick',
                    position: pos,
                });
            }
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _handleSingleSceneClick() {
        const pick = this.scene.pick(this.scene.pointerX, this.scene.pointerY);
        if (pick.hit) {
            if (pick.pickedMesh.metadata && pick.pickedMesh.metadata.object) {
                const clickedObject = pick.pickedMesh.metadata.object;

                this.sendEvent({
                    type: 'object_click',
                    object_id: clickedObject.id,
                    position: clickedObject.position || [],
                });
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _handleDoubleSceneClick() {
        const pick = this.scene.pick(this.scene.pointerX, this.scene.pointerY);
        if (pick.hit) {
            const p = pick.pickedPoint;
            const pos = [p.x, -p.z, p.y];
            this.sendEvent({
                type: 'floor_doubleclick',
                position: pos,
            });
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _onObjectEvent(obj, event) {
        this.log(`Object ${obj.id} event: ${event}`);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _onObjectLog(obj, message, level = 'info') {
        this.log(`Object ${obj.id}: ${message}`, level);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _onObjectSendMessage(obj, message) {
        this.log(`Object ${obj.id} send message: ${message}`);
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    /* -------------------------------------------------------------------------------------------------------------- */

    /* -------------------------------------------------------------------------------------------------------------- */
    addTestObjects() {


        // const as1 = new ArucoStatic('static1', this, {});
        // this.addObject(as1);


        // this.frodo2 = new BabylonFrodo('frodo2', this, {scaling: 1, color: [0, 0.7, 0.2]});
        // this.frodo2.onLoaded().then(() => {
        //     this.frodo2.setState(0, -1, 0);
        // })

        // const simplebox2 = new BabylonBox('box1', this, {config: {size: {x: 0.1, y: 0.1, z: 0.1}}});
        // // simplebox.onLoaded().then(() => {
        // simplebox2.setPosition([1, 0, 0]);

        return;


        const cir2 = new BabylonCircleDrawing("circle2", this.scene, {
            data: {
                radius: 0.75
            },
            config: {
                circleFillColor: [0, 1, 0, 0.05],
                circleBorderColor: [0, 1, 0, 0.2],
                circleBorderWidth: 0.01,
            }
        });
        this.addObject(cir2);
        cir2.setPosition([0, 0, 0]);

        // // Make a function that changes the size of the circle with an interval. Make it grow and then shrink
        // const changeSize = () => {
        //     const size = cir2.config.radius;
        //     cir2.setRadius(size + 0.01);
        // }
        //
        // setInterval(changeSize, 50);
        // //
        // const line = new BabylonLineDrawing("line1", this.scene, {
        //     config: {
        //         start: [0, 0, 0],
        //         end: [-0.6, -0.2, 0],
        //         lineColor: [1, 0, 0, 0.5],
        //         lineWidth: 0.005,
        //         lineStyle: "dotted",
        //     }
        // });
        // this.addObject(line);
        //
        // const move_line = () => {
        //     const new_end = [Math.sin(Date.now() / 1000), Math.cos(Date.now() / 1000), 0];
        //
        //     line.updatePoints({end: new_end});
        // }
        //
        // setInterval(move_line, 50);

        const simple_bilbo1 = new BabylonBilbo('sb1', this.scene, {});

        simple_bilbo1.onLoaded().then(() => {
            simple_bilbo1.setState(0.5, 0.5, 0, -Math.PI / 4);
        })

        const simple_bilbo2 = new BabylonBilbo('sb1', this.scene, {});

        simple_bilbo2.onLoaded().then(() => {
            simple_bilbo2.setState(0.5, 0.1, 0, -Math.PI / 4);
        })

        const simplebox = new BabylonBox('box1', this.scene, {config: {size: {x: 0.1, y: 0.1, z: 0.1}}});
        // simplebox.onLoaded().then(() => {
        simplebox.setPosition([1, 0, 0]);
        // })

        // // this.addObject(simple_bilbo1);
        // //
        // // this.bilbo2 = new BabylonBilboRealistic('bilbo2', this.scene, {config: {text: '2', color: [0.5, 0.5, 0.7]}});
        //
        // this.frodo1 = new BabylonFrodo('frodo1', this.scene, {config: {scaling: 1}});
        //
        // this.frodo1.onLoaded().then(() => {
        //     this.frodo1.setState(0, 1, -Math.PI / 4);
        // })
        //
        // return;

        // this.frodo2 = new BabylonFrodo('frodo2', this.scene, {scaling: 1, color: [0, 0.7, 0.2]});
        // this.frodo2.onLoaded().then(() => {
        //     this.frodo2.setState(0, -1, 0);
        // })

    }


    dispose() {
        this._resizeObserver?.disconnect();
        this._resizeObserver = null;
        this._mq?.removeEventListener?.('change', this._mqHandler);
        this._mq = this._mqHandler = null;
        window.visualViewport?.removeEventListener?.('resize', this._vvHandler);
        window.removeEventListener('resize', this._winResizeHandler);

        // Stop render loop and dispose engine/scene
        if (this.engine) {
            this.engine.stopRenderLoop();
            this._renderLoopRunning = false;
        }
        this.reset();
        if (this.scene) {
            this.scene.dispose();
        }
        if (this.engine) {
            this.engine.dispose();
        }
    }
}


// =====================================================================================================================
class CameraButton
    extends ButtonWidget {
    constructor(id, config = {}) {
        // Keep the ButtonWidget constructor behavior (it builds the element and calls configureElement)
        super(id, config);

        // Provide a couple of gentle defaults if caller didn't pass them
        const cameraDefaults = {
            image: './icons/camera-icon.png',
            image_width: '75%',
            image_height: '75%',
            number: 1,           // badge number
            adjust_icon_size: true
        };
        this.configuration = {...cameraDefaults, ...this.configuration};

        // Reconfigure again so our defaults take effect when constructed with minimal config
        this.configureElement(this.element);

    }

    configureElement(element) {
        // Build the base button first
        super.configureElement(element);

        // Ensure the button is a positioned container for the badge
        element.style.position = element.style.position || 'relative';

        // Create (or re-attach) the badge
        const number = (this.configuration && this.configuration.number != null)
            ? String(this.configuration.number) : "";

        if (!this._badgeEl) {
            this._badgeEl = document.createElement('div');
            this._badgeEl.className = 'cameraBadge';
        }
        this._badgeEl.textContent = number;

        // Minimal inline styles so you don't need extra CSS
        Object.assign(this._badgeEl.style, {
            position: 'absolute',
            left: '1px',
            bottom: '1px',
            minWidth: '18px',
            height: '18px',
            padding: '0 4px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '9px',
            background: 'rgba(0,0,0,1)',
            color: '#fff',
            fontSize: '10px',
            lineHeight: '18px',
            border: '1px solid rgba(255,255,255,0.25)',
            pointerEvents: 'none', // never block clicks on the button
            zIndex: '1',
            opacity: '1',
        });

        // ButtonWidget.configureElement() resets innerHTML every time, so always append (or re-append) the badge last.
        element.appendChild(this._badgeEl);
        element.classList.add('camera-button');
    }

    setNumber(n) {
        this.configuration.number = n;
        if (this._badgeEl) this._badgeEl.textContent = String(n);
    }
}

// =====================================================================================================================
class TerminalButton extends ButtonWidget {
    constructor(id, config = {}) {
        // Keep ButtonWidget behavior (builds element + calls configureElement)
        super(id, config);

        // Safe defaults so the button looks just like your existing one
        const defaults = {
            image: './icons/terminal-icon.png',
            image_width: '75%',
            image_height: '75%',
            notifications: 0,             // starting count
            max_display: 99,              // 100+ shows as "99+"
        };
        this.configuration = {...defaults, ...this.configuration};

        // Internal state
        this._notifCount = Number(this.configuration.notifications) || 0;

        // Re-configure so our defaults apply when constructed with minimal config
        this.configureElement(this.element);

        this.container.style.overflow = 'visible';
    }

    configureElement(element) {
        super.configureElement(element);

        element.classList.add('terminal-button');
        element.style.position = element.style.position || 'relative';

        // ⬇️ This is the important part: beat the generic .buttonItem { overflow:hidden }
        element.style.overflow = 'visible';
        element.style.zIndex = '1'; // keep the badge above neighbors

        if (!this._badgeEl) {
            this._badgeEl = document.createElement('div');
            this._badgeEl.className = 'terminalBadge';
        }

        this._renderBadge();
        element.appendChild(this._badgeEl);
    }

    // --- Public API -------------------------------------------------------------------------------------------------
    increaseNotificationCount(delta = 1) {
        const d = Number.isFinite(delta) ? delta : 1;
        this.setNotificationCount((this._notifCount || 0) + d);
    }

    removeNotificationCount() {
        // Resets to zero (and hides the badge)
        this.setNotificationCount(0);
    }

    setNotificationCount(n) {
        const next = Math.max(0, Number(n) || 0);
        if (next === this._notifCount) return;
        this._notifCount = next;
        this._renderBadge();
    }

    getNotificationCount() {
        return this._notifCount || 0;
    }

    // --- Private helpers -------------------------------------------------------------------------------------------
    _renderBadge() {
        if (!this._badgeEl) return;

        const count = this._notifCount || 0;
        if (count <= 0) {
            this._badgeEl.style.display = 'none';
            return;
        }

        const cap = Number(this.configuration.max_display) || 99;
        const text = count > cap ? `${cap}+` : String(count);

        this._badgeEl.textContent = text;
        this._badgeEl.style.display = 'flex';
    }
}

// =====================================================================================================================
class RecordButton extends ButtonWidget {
    constructor(id, config = {}) {
        super(id, config);

        // Gentle defaults
        const defaults = {
            image: './icons/record-icon.png',
            image_width: '85%',
            image_height: '85%',
            tooltip: 'Record'
        };
        this.configuration = {...defaults, ...this.configuration};

        // Callbacks used by the context menu entries
        this.callbacks.add('hbr_recording');
        this.callbacks.add('hbr_recording_overlay');

        // Internal timer state
        this._recStartTs = 0;
        this._ticker = null;
        this._timerEl = null;

        // Build DOM + styles
        this.configureElement(this.element);

        // Context menu: High Bit Rate
        const high_bit_rate_element = new ContextMenuItem('hbr', {
            name: 'Record High Bit Rate',
            front_icon: '🔴'
        });
        this.addItemToContextMenu(high_bit_rate_element);
        high_bit_rate_element.callbacks.get('click').register(() => {
            this.callbacks.get('hbr_recording').call();
        });

        // Context menu: High Bit Rate with Overlay
        const high_bit_rate_element2 = new ContextMenuItem('hbr2', {
            name: "Record High Bit Rate with Overlay",
            front_icon: '🔴'
        });
        this.addItemToContextMenu(high_bit_rate_element2);
        high_bit_rate_element2.callbacks.get('click').register(() => {
            this.callbacks.get('hbr_recording_overlay').call();
        });


    }

    configureElement(element) {
        super.configureElement(element);
        element.classList.add('record-button');

        if (this.configuration.tooltip) {
            this.setTooltip(this.configuration.tooltip);
        }

        // The button must be a positioned container so the timer can sit above it
        element.style.position = element.style.position || 'relative';
        element.style.overflow = 'visible';

        // Ensure the small timer pill exists (but hidden until recording)
        if (!this._timerEl) {
            this._timerEl = document.createElement('div');
            this._timerEl.className = 'record-timer';
            this._timerEl.setAttribute('aria-hidden', 'true');
            this._timerEl.textContent = '00:00';
            // this.container.appendChild(this._timerEl);
            element.appendChild(this._timerEl);
        }

        this.container.style.overflow = 'visible';
    }

    /** Turns on the blinking / 'REC' style and shows the mm:ss timer */
    startBlinking() {
        if (!this.element) return;

        // Add visual recording state
        this.element.classList.add('is-recording');
        this.setTooltip('');
        this.element.setAttribute('aria-pressed', 'true');

        // (Re)start timer logic
        this._recStartTs = Date.now();
        if (this._timerEl) this._timerEl.textContent = '00:00';

        // Clear any previous ticker (safety)
        if (this._ticker) {
            clearInterval(this._ticker);
            this._ticker = null;
        }

        // Update every 250ms so we cross second boundaries smoothly, but only show mm:ss
        this._ticker = setInterval(() => {
            if (!this._timerEl) return;
            const elapsedMs = Math.max(0, Date.now() - this._recStartTs);
            const totalSeconds = Math.floor(elapsedMs / 1000);
            const mm = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
            const ss = String(totalSeconds % 60).padStart(2, '0');
            this._timerEl.textContent = `${mm}:${ss}`;
        }, 250);
    }

    /** Turns off the blinking / 'REC' style and hides the timer */
    stopBlinking() {
        if (!this.element) return;

        // Visual state off
        this.element.classList.remove('is-recording');
        this.setTooltip(this.configuration.tooltip || 'Record');
        this.element.setAttribute('aria-pressed', 'false');

        // Stop timer + reset text (kept hidden by CSS when not recording)
        if (this._ticker) {
            clearInterval(this._ticker);
            this._ticker = null;
        }
        if (this._timerEl) {
            this._timerEl.textContent = '00:00';
        }
    }

    /** Convenience for toggling from the outside */
    setRecording(isRecording) {
        if (isRecording) this.startBlinking();
        else this.stopBlinking();
    }
}

// =====================================================================================================================
export class BabylonContainer {

    /** @type {HTMLElement | null } */
    container = null;

    /** @type {HTMLElement | null } */
    element = null;

    /** @type {Callbacks} */
    callbacks


    /** @type {Object} */
    cameras = {}

    // TODO: This belong to the debug overlay
    /** @type {number} */
    _suppressClickUntil = 0;


    // === CONSTRUCTOR =================================================================================================
    constructor(id, container, payload = {}) {

        const default_config = {
            show_widget_controls: true,
            widget_controls_position: 'inside',  // inside, outside
            control_bar_height: 35, // px
            babylon: {},
            title: 'Dustin Babylon.JS',
        }

        this.configuration = {...default_config, ...payload.config};

        this.container = container;
        this.id = id;

        this.element = this.initializeElement();
        this.configureElement();

        this.babylon = new Babylon(this.id, this.babylon_canvas, payload.config, payload.objects);
        this.babylon.container = this;

        this.babylon_canvas.setAttribute('tabindex', '-1');
        this.babylon_canvas.addEventListener('mousedown', (e) => e.preventDefault(), {capture: true});

        this._attachBabylonCallbacks();
        this.attachListeners();

        this._debugCollapse = {};
        this._debugBuilt = false;


        this.top_bar_time = this.top_bar_time || this.element.querySelector('.top-bar .time');

        // --- simple elapsed timer ---
        this._timerStart = Date.now();

        const pad2 = (n) => String(n).padStart(2, '0');
        const tickElapsed = () => {
            const secs = Math.floor((Date.now() - this._timerStart) / 1000);
            const h = Math.floor(secs / 3600);
            const m = Math.floor((secs % 3600) / 60);
            const s = secs % 60;
            if (this.top_bar_time) this.top_bar_time.textContent = `${pad2(h)}:${pad2(m)}:${pad2(s)}`;
        };

        // kick it off + repeat every second
        tickElapsed();
        this._timeInterval = setInterval(tickElapsed, 1000);
    }

    // === METHODS =====================================================================================================
    initializeElement() {
        const element = document.createElement('div');
        element.classList.add('babylon-container');

        // const el = document.querySelector('.no-focus-on-click');
        // element.addEventListener('mousedown', e => e.preventDefault()); // stops focus

        if (this.configuration.widget_controls_position === 'inside') {
            element.classList.add('babylon-controls-inside');
        } else {
            element.classList.add('babylon-controls-outside');
        }


        this.babylon_canvas_container = document.createElement('div');
        this.babylon_canvas_container.classList.add('babylon-canvas-container');
        element.appendChild(this.babylon_canvas_container);

        this.babylon_canvas = document.createElement('canvas');
        this.babylon_canvas.classList.add('babylon-canvas');
        this.babylon_canvas_container.appendChild(this.babylon_canvas);

        this.babylon_controls = document.createElement('div');
        this.babylon_controls.classList.add('babylon-controls');
        element.appendChild(this.babylon_controls);
        this.babylon_controls.style.setProperty('--control-height', `${this.configuration.control_bar_height}px`)


        // Connection Indicator
        this.connection_indicator = document.createElement('div');
        this.connection_indicator.classList.add('connection');
        this.babylon_controls.appendChild(this.connection_indicator);

        this.connection_circle = document.createElement('div');
        this.connection_circle.classList.add('connection-circle');
        this.connection_indicator.appendChild(this.connection_circle);

        this.connection_message = document.createElement('div');
        this.connection_message.classList.add('connection-messages');
        this.connection_indicator.appendChild(this.connection_message);

        this.connection_message.textContent = '20 M/s'

        // Add buttons here
        const button_container = document.createElement('div');
        button_container.classList.add('buttons');
        this.babylon_controls.appendChild(button_container);

        const buttons = {}

        this.button_record = new RecordButton('record', {
            config: {image: './icons/record-icon.png', image_width: '85%', image_height: '85%'}
        });
        this.button_record.setTooltip("Record");
        this.button_record.attach(button_container);

        this.button_record.callbacks.get('click').register(() => {
            if (!this.babylon.is_recording) {
                this.babylon.startRecording("babylonjs.webm",);
            } else {
                this.babylon.stopRecording();
            }
        });

        this.button_record.callbacks.get('hbr_recording').register(() => {
            if (!this.babylon.is_recording) {
                this.babylon.startRecordingHiBitrate();
            }
        });

        this.button_record.callbacks.get('hbr_recording_overlay').register(() => {
            if (!this.babylon.is_recording) {
                // this.babylon.startRecordingHiBitrate("babylonjs.webm");
                this.startRecordingHiBitrateWithOverlay();
            }
        });

        this.button_settings = new ButtonWidget('settings',
            {
                config: {
                    image: './icons/settings-icon.png',
                    image_width: '75%',
                    image_height: '75%',
                }
            });

        this.button_settings.setTooltip("Settings");
        this.button_settings.attach(button_container);

        this.button_settings.callbacks.get('click').register(() => {
            if (this.settings_overlay && this.settings_overlay.style.display === 'flex') {
                this.closeSettingsOverlay();
            } else {
                this.openSettingsOverlay();
            }
        });

        this.button_assets = new ButtonWidget('assets',
            {
                config: {
                    image: './icons/assets-icon.png',
                    image_width: '75%',
                    image_height: '75%',
                }
            });

        this.button_assets.setTooltip("Assets");
        this.button_assets.attach(button_container);

        this.button_assets.callbacks.get('click').register(() => {
            if (this.assets_overlay && this.assets_overlay.style.display === 'flex') {
                this.closeAssetsOverlay();
            } else {
                this.openAssetsOverlay();
            }
        });

        const button_fullscreen = new ButtonWidget('fullscreen',
            {
                config: {
                    image: './icons/fullscreen-icon.png',
                    image_width: '75%',
                    image_height: '75%',
                }
            })

        button_fullscreen.setTooltip("Fullscreen");
        button_fullscreen.attach(button_container);

        button_fullscreen.callbacks.get('click').register(() => {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                this.element.requestFullscreen();
            }
        });

        element.addEventListener('fullscreenchange', () => {
            if (document.fullscreenElement) {
                button_fullscreen.setTooltip("Exit Fullscreen");
            } else {
                button_fullscreen.setTooltip("Fullscreen");
            }
        });

        const popoutIcon = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6'/%3E%3Cpolyline points='15 3 21 3 21 9'/%3E%3Cline x1='10' y1='14' x2='21' y2='3'/%3E%3C/svg%3E";
        const button_popout = new ButtonWidget('popout', {
            config: {
                image: popoutIcon,
                image_width: '75%',
                image_height: '75%',
            }
        });
        button_popout.setTooltip("Pop Out");
        button_popout.attach(button_container);

        button_popout.callbacks.get('click').register(() => {
            const host = this.configuration.websocket_host || this.babylon.config.websocket_host || 'localhost';
            const port = this.configuration.websocket_port || this.babylon.config.websocket_port || '9000';
            const title = this.configuration.title || 'Babylon Visualization';
            const id = this.babylon.id;

            // Pass the full config so the popup renders identically
            const storageKey = `babylon_config_${id}`;
            sessionStorage.setItem(storageKey, JSON.stringify(this.babylon.config));

            const url = new URL('/babylon-popup.html', window.location.origin);
            url.searchParams.set('id', id);
            url.searchParams.set('host', host);
            url.searchParams.set('port', port);
            url.searchParams.set('title', title);
            window.open(url.href, '_blank', 'width=1200,height=800,resizable=yes');
        });

        this.button_terminal = new TerminalButton('terminal', {
            config: {image: './icons/terminal-icon.png'}
        });

        this.button_terminal.setTooltip("Terminal");
        this.button_terminal.attach(button_container);

        const button_debug = new ButtonWidget('terminal',
            {
                config: {
                    image: './icons/debug-icon.png',
                    image_width: '75%',
                    image_height: '75%',
                }
            })

        button_debug.setTooltip("Debug");
        button_debug.attach(button_container);

        button_debug.callbacks.get('click').register(() => {
            if (this.debug_overlay.style.display === 'flex') {
                this.closeDebugOverlay();
            } else {
                this.openDebugOverlay();
            }
        })

        // --- Copy Camera button with right-click context menu ---
        const copyCameraIcon = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z'/%3E%3Ccircle cx='12' cy='13' r='4'/%3E%3C/svg%3E";
        const button_copy_camera = new ButtonWidget('copy_camera', {
            config: {
                image: copyCameraIcon,
                image_width: '75%',
                image_height: '75%',
            }
        });
        button_copy_camera.setTooltip("Copy Camera");
        button_copy_camera.attach(button_container);

        // Helper: read current camera values as Python-friendly strings
        const _getCameraValues = () => {
            const cam = this.babylon.camera;
            if (!cam) return null;
            const t = cam.target;
            return {
                alpha: cam.alpha.toFixed(4),
                beta: cam.beta.toFixed(4),
                radius: cam.radius.toFixed(2),
                fov: cam.fov.toFixed(4),
                fov_deg: (cam.fov * 180 / Math.PI).toFixed(1),
                tx: t.x.toFixed(2),
                ty: (-t.z).toFixed(2),
                tz: t.y.toFixed(2),
            };
        };

        const _copyAndFlash = (text) => {
            const onSuccess = () => {
                button_copy_camera.setTooltip("Copied!");
                setTimeout(() => button_copy_camera.setTooltip("Copy Camera"), 1500);
            };
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(onSuccess)
                    .catch(err => console.warn('Copy camera to clipboard failed:', err));
            } else {
                // Fallback for non-secure contexts (HTTP)
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                onSuccess();
            }
        };

        // Left click: BabylonCamera constructor
        button_copy_camera.callbacks.get('click').register(() => {
            const v = _getCameraValues();
            if (!v) return;
            _copyAndFlash(
                `BabylonCamera(target=[${v.tx}, ${v.ty}, ${v.tz}], alpha=${v.alpha}, beta=${v.beta}, radius=${v.radius}, fov=${v.fov})`
            );
        });

        // Right click: context menu with multiple formats
        const camMenu = document.createElement('div');
        camMenu.classList.add('camera-copy-menu');
        camMenu.style.display = 'none';
        element.appendChild(camMenu);

        const menuItems = [
            {label: 'Copy BabylonCamera', fmt: (v) =>
                `BabylonCamera(target=[${v.tx}, ${v.ty}, ${v.tz}], alpha=${v.alpha}, beta=${v.beta}, radius=${v.radius}, fov=${v.fov})`
            },
            {label: 'Copy add_camera()', fmt: (v) =>
                `babylon.add_camera(BabylonCamera(name="Camera", target=[${v.tx}, ${v.ty}, ${v.tz}], alpha=${v.alpha}, beta=${v.beta}, radius=${v.radius}, fov=${v.fov}))`
            },
        ];

        for (const item of menuItems) {
            const row = document.createElement('div');
            row.classList.add('camera-copy-menu-item');
            row.textContent = item.label;
            row.addEventListener('click', (e) => {
                e.stopPropagation();
                const v = _getCameraValues();
                if (v) _copyAndFlash(item.fmt(v));
                camMenu.style.display = 'none';
            });
            camMenu.appendChild(row);
        }

        button_copy_camera.getElement().addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            // Position menu above the button
            const rect = button_copy_camera.getElement().getBoundingClientRect();
            const parentRect = element.getBoundingClientRect();
            camMenu.style.left = `${rect.left - parentRect.left}px`;
            camMenu.style.bottom = `${parentRect.bottom - rect.top + 4}px`;
            camMenu.style.display = 'flex';
        });

        // Close menu on any click elsewhere
        document.addEventListener('click', () => { camMenu.style.display = 'none'; });

        const top_bar = document.createElement('div');
        top_bar.classList.add('top-bar');
        element.appendChild(top_bar);

        const top_bar_title = document.createElement('div');
        top_bar_title.classList.add('title');
        top_bar_title.textContent = this.configuration.title;
        top_bar.appendChild(top_bar_title);

        // Follow indicator (hidden by default)
        this._followBadge = document.createElement('div');
        this._followBadge.classList.add('follow-badge');
        this._followBadge.style.display = 'none';
        this._followBadge.addEventListener('click', () => {
            this.babylon.stopFollowing();
            this._hideFollowBadge();
        });
        top_bar.appendChild(this._followBadge);

        const top_bar_time = document.createElement('div');
        top_bar_time.classList.add('time');
        top_bar_time.textContent = "00:00:00";
        top_bar.appendChild(top_bar_time);


        // Overlays
        this.terminal_overlay = document.createElement('div');
        this.terminal_overlay.classList.add('terminal-overlay');
        this.terminal_overlay.style.display = 'none';

        this.button_terminal.callbacks.get('click').register(() => {
            if (this.terminal_overlay.style.display === 'flex') {
                this.closeTerminalOverlay();
            } else {
                this.openTerminalOverlay();
            }
        })

        this.terminal_output = new LineScrollTextWidget('terminal_output', {
            config: {
                font_size: 10,
            }
        });
        this.terminal_overlay.appendChild(this.terminal_output.getElement());
        const terminal_close_button_container = document.createElement('div');
        terminal_close_button_container.classList.add('terminal-close-button-container');
        this.terminal_overlay.appendChild(terminal_close_button_container);
        this.terminal_close_button = new ButtonWidget('terminal_close', {
            config:
                {
                    icon: "❌"
                }
        });
        this.terminal_close_button.callbacks.get('click').register(() => {
            this.closeTerminalOverlay();
        })
        terminal_close_button_container.appendChild(this.terminal_close_button.getElement());

        this.terminal_output.addLine("Welcome to Dustin's Babylon.js container!");
        element.appendChild(this.terminal_overlay);


        // Babylon Debug Overlay
        this.debug_overlay = document.createElement('div');
        this.debug_overlay.classList.add('debug-overlay');
        this.debug_overlay.style.display = 'none';
        element.appendChild(this.debug_overlay);

        // Assets Overlay
        this.assets_overlay = document.createElement('div');
        this.assets_overlay.classList.add('assets-overlay');
        this.assets_overlay.style.display = 'none';

        const assets_close_container = document.createElement('div');
        assets_close_container.classList.add('overlay-close-button');
        assets_close_container.innerHTML = '&#x2715;';
        assets_close_container.addEventListener('click', () => this.closeAssetsOverlay());
        this.assets_overlay.appendChild(assets_close_container);

        this._assetsListContainer = document.createElement('div');
        this._assetsListContainer.classList.add('assets-list');
        this.assets_overlay.appendChild(this._assetsListContainer);

        element.appendChild(this.assets_overlay);

        // Settings Overlay
        this.settings_overlay = document.createElement('div');
        this.settings_overlay.classList.add('settings-overlay');
        this.settings_overlay.style.display = 'none';

        const settings_close_container = document.createElement('div');
        settings_close_container.classList.add('overlay-close-button');
        settings_close_container.innerHTML = '&#x2715;';
        settings_close_container.addEventListener('click', () => this.closeSettingsOverlay());
        this.settings_overlay.appendChild(settings_close_container);

        this._settingsListContainer = document.createElement('div');
        this._settingsListContainer.classList.add('settings-list');
        this.settings_overlay.appendChild(this._settingsListContainer);

        element.appendChild(this.settings_overlay);

        this.top_bar = top_bar;
        this.top_bar_title = top_bar_title;
        this.top_bar_time = top_bar_time;

        // Overlay labels container (fills parent, labels are individually positioned)
        this._overlayLabelsContainer = document.createElement('div');
        this._overlayLabelsContainer.style.cssText =
            'position:absolute; inset:0; pointer-events:none; z-index:50;';
        element.appendChild(this._overlayLabelsContainer);
        this._overlayLabels = new Map(); // id -> { el, x, y, fontSize }

        this._setConnectionStatus(false, '');

        this.container.appendChild(element);
        return element;
    }

    // -----------------------------------------------------------------------------------------------------------------
    configureElement() {

    }

    // -----------------------------------------------------------------------------------------------------------------
    attachListeners() {

    }

    // -----------------------------------------------------------------------------------------------------------------
    addLineToTerminal(line, color = 'white', add_notification = true) {

        this.terminal_output.addLine(line, color);
        if (add_notification) {
            if (this.terminal_overlay.style.display === 'none') {
                this.button_terminal.increaseNotificationCount();
            }
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    openTerminalOverlay() {
        this.closeDebugOverlay();
        this.closeAssetsOverlay();
        this.closeSettingsOverlay();
        const controlsHeight = this.babylon_controls.offsetHeight;
        const topBarHeight = this.element.querySelector('.top-bar').offsetHeight;

        this.terminal_overlay.style.top = `${topBarHeight + 5}px`;
        this.terminal_overlay.style.bottom = `${controlsHeight + 5}px`;


        this.terminal_overlay.style.display = 'flex';

        this.terminal_output.scrollDown();
        this.button_terminal.setNotificationCount(0);

    }

    // -----------------------------------------------------------------------------------------------------------------
    closeTerminalOverlay() {
        this.terminal_overlay.style.display = 'none';
    }

    // -----------------------------------------------------------------------------------------------------------------
    openAssetsOverlay() {
        this.closeTerminalOverlay();
        this.closeDebugOverlay();
        this.closeSettingsOverlay();

        const controlsHeight = this.babylon_controls.offsetHeight;
        const topBarHeight = this.element.querySelector('.top-bar').offsetHeight;

        this.assets_overlay.style.top = `${topBarHeight + 5}px`;
        this.assets_overlay.style.bottom = `${controlsHeight + 5}px`;
        this.assets_overlay.style.display = 'flex';

        this._renderAssetsList();
    }

    // -----------------------------------------------------------------------------------------------------------------
    closeAssetsOverlay() {
        this.assets_overlay.style.display = 'none';
    }

    // -----------------------------------------------------------------------------------------------------------------
    _renderAssetsList() {
        const container = this._assetsListContainer;
        container.innerHTML = '';

        const objects = this.babylon.objects;
        if (!objects || Object.keys(objects).length === 0) {
            const empty = document.createElement('div');
            empty.classList.add('asset-item');
            empty.style.opacity = '0.5';
            empty.textContent = 'No objects in scene';
            container.appendChild(empty);
            return;
        }

        for (const [id, obj] of Object.entries(objects)) {
            const item = document.createElement('div');
            item.classList.add('asset-item');

            const icon = document.createElement('span');
            icon.textContent = (obj.objects) ? '\u25B6' : '\u25CF';
            icon.style.fontSize = '8px';
            icon.style.opacity = '0.6';
            item.appendChild(icon);

            const label = document.createElement('span');
            label.textContent = id;
            item.appendChild(label);

            item.addEventListener('click', () => {
                this.babylon.followObject(obj.id);
                this._showFollowBadge(obj.id);
                this.closeAssetsOverlay();
            });

            container.appendChild(item);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    openSettingsOverlay() {
        this.closeTerminalOverlay();
        this.closeDebugOverlay();
        this.closeAssetsOverlay();

        const controlsHeight = this.babylon_controls.offsetHeight;
        const topBarHeight = this.element.querySelector('.top-bar').offsetHeight;

        this.settings_overlay.style.top = `${topBarHeight + 5}px`;
        this.settings_overlay.style.bottom = `${controlsHeight + 5}px`;
        this.settings_overlay.style.display = 'flex';

        this._renderSettings();
    }

    // -----------------------------------------------------------------------------------------------------------------
    closeSettingsOverlay() {
        this.settings_overlay.style.display = 'none';
    }

    // -----------------------------------------------------------------------------------------------------------------
    _renderSettings() {
        const container = this._settingsListContainer;
        container.innerHTML = '';

        const scene = this.babylon.scene;
        if (!scene) return;

        // Store original fog mode on first render
        if (this._originalFogMode == null) {
            this._originalFogMode = scene.fogMode;
        }

        // --- Fog toggle ---
        const fogRow = this._createToggleRow('Fog', scene.fogMode !== 0, (enabled) => {
            if (enabled) {
                scene.fogMode = this._originalFogMode || BabylonScene.FOGMODE_EXP2;
            } else {
                scene.fogMode = BabylonScene.FOGMODE_NONE;
            }
        });
        container.appendChild(fogRow);

        // --- Coordinate Axes toggle ---
        const axisNames = ['axisX', 'axisY', 'axisZ'];
        const axisMeshes = axisNames.map(n => scene.getMeshByName(n)).filter(Boolean);

        if (axisMeshes.length > 0) {
            const axesEnabled = axisMeshes[0].isEnabled();
            const axesRow = this._createToggleRow('Coordinate Axes', axesEnabled, (enabled) => {
                axisMeshes.forEach(m => m.setEnabled(enabled));
            });
            container.appendChild(axesRow);
        }

        // --- Light Helpers toggle ---
        const lightHelperMeshes = scene.meshes.filter(m => m.name.startsWith('_lightHelper_'));
        if (lightHelperMeshes.length > 0) {
            const lightsEnabled = lightHelperMeshes[0].isEnabled();
            const lightsRow = this._createToggleRow('Light Helpers', lightsEnabled, (enabled) => {
                lightHelperMeshes.forEach(m => m.setEnabled(enabled));
            });
            container.appendChild(lightsRow);
        }

        // --- Wireframe toggle ---
        const wireRow = this._createToggleRow('Wireframe', scene.forceWireframe || false, (enabled) => {
            scene.forceWireframe = enabled;
        });
        container.appendChild(wireRow);

        // --- FOV slider ---
        const cam = this.babylon.camera;
        if (cam) {
            const currentDeg = cam.fov * 180 / Math.PI;
            const fovRow = this._createSliderRow('FOV', currentDeg, 5, 120, '°', (val) => {
                cam.fov = val * Math.PI / 180;
            });
            container.appendChild(fovRow);

            // --- Radius upper limit slider ---
            const radiusRow = this._createSliderRow(
                'Max Radius', cam.upperRadiusLimit, 2, 50, 'm',
                (val) => { cam.upperRadiusLimit = val; }
            );
            container.appendChild(radiusRow);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    _createToggleRow(label, initialState, onChange) {
        const row = document.createElement('div');
        row.classList.add('setting-row');

        const labelEl = document.createElement('span');
        labelEl.classList.add('setting-label');
        labelEl.textContent = label;
        row.appendChild(labelEl);

        const toggle = document.createElement('label');
        toggle.classList.add('toggle');

        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = initialState;
        input.addEventListener('change', () => onChange(input.checked));

        const slider = document.createElement('span');
        slider.classList.add('toggle-slider');

        toggle.appendChild(input);
        toggle.appendChild(slider);
        row.appendChild(toggle);

        return row;
    }

    // -----------------------------------------------------------------------------------------------------------------
    _createSliderRow(label, initialValue, min, max, unit, onChange) {
        const row = document.createElement('div');
        row.classList.add('setting-row', 'setting-row-slider');

        const labelEl = document.createElement('span');
        labelEl.classList.add('setting-label');
        labelEl.textContent = label;
        row.appendChild(labelEl);

        const controls = document.createElement('div');
        controls.classList.add('setting-slider-controls');

        const valueEl = document.createElement('span');
        valueEl.classList.add('setting-slider-value');
        valueEl.textContent = `${Math.round(initialValue)}${unit}`;

        const input = document.createElement('input');
        input.type = 'range';
        input.classList.add('setting-slider');
        input.min = min;
        input.max = max;
        input.step = 1;
        input.value = Math.round(initialValue);
        input.addEventListener('input', () => {
            const val = parseFloat(input.value);
            valueEl.textContent = `${Math.round(val)}${unit}`;
            onChange(val);
        });

        controls.appendChild(input);
        controls.appendChild(valueEl);
        row.appendChild(controls);

        return row;
    }

    // -----------------------------------------------------------------------------------------------------------------
    _showFollowBadge(objectId) {
        this._followBadge.innerHTML = `Following: <strong>${objectId}</strong> <span class="follow-badge-x">&#x2715;</span>`;
        this._followBadge.style.display = 'flex';
    }

    // -----------------------------------------------------------------------------------------------------------------
    _hideFollowBadge() {
        this._followBadge.style.display = 'none';
    }

    // -----------------------------------------------------------------------------------------------------------------
    addCameraView(camera_data = {}) {
        // Where to append: the existing control bar's .buttons grid
        const buttonContainer = this.babylon_controls.querySelector('.buttons');
        if (!buttonContainer) {
            console.warn('BabylonContainer.addCameraView: .buttons container not found');
            return;
        }

        // Decide id and sequential number
        const currentCount = Object.keys(this.cameras).length;
        const number = (camera_data.number != null) ? camera_data.number : (currentCount + 1);
        const id = camera_data.id || `camera_${number}`;

        // Create the button
        const btn = new CameraButton(id, {
            config: {
                image: camera_data.image || "./icons/camera-icon.png",
                image_width: "75%",
                image_height: "75%",
                text: (camera_data.text || ""), // optional label if you later want one
                number
            }
        });

        // Keep a reference
        this.cameras[id] = {button: btn, data: camera_data};

        // Add to the grid
        btn.attach(buttonContainer);
        btn.setTooltip(camera_data.name || `Camera ${number}`);


        btn.callbacks.get('click').register(() => {
            this.babylon.stopFollowing();
            this._hideFollowBadge();
            const fov = camera_data.fov != null ? camera_data.fov : this.babylon.config.camera.fov;
            this.babylon.setArcRotateCamera(camera_data.position,
                camera_data.target,
                camera_data.alpha,
                camera_data.beta,
                camera_data.radius,
                fov);
        })

        // Auto-adjust the grid columns to fit however many buttons exist now
        const totalButtons = buttonContainer.children.length;
        buttonContainer.style.gridTemplateColumns = `repeat(${totalButtons}, 1fr)`;
        buttonContainer.style.aspectRatio = `${totalButtons}`;
    }


    // -----------------------------------------------------------------------------------------------------------------
    startRecordingHiBitrateWithOverlay({
                                           fileName = "babylonjs.webm",
                                           fps = 60,
                                           videoBitsPerSecond = 12_000_000,
                                           upscale = 1.0,
                                           enableTimeTicker = false,      // if true, updates this.top_bar_time every second while recording
                                       } = {}) {
        const engine = this.babylon.scene?.getEngine?.();
        const src = engine?.getRenderingCanvas?.();

        if (!engine || !src) {
            this.babylon?.log?.("No canvas for recording.", "error");
            return;
        }
        if (this.babylon.is_recording) {
            this.babylon?.log?.("Already recording.", "warning");
            return;
        }

        // -------- helpers ----------
        const syncSize = () => {
            mix.width = src.width;
            mix.height = src.height;
        };

        // Rounded-rect path helper (single radius)
        const roundRectPath = (ctx, x, y, w, h, r) => {
            const rr = Math.max(0, Math.min(r, Math.min(w, h) / 2));
            ctx.beginPath();
            ctx.moveTo(x + rr, y);
            ctx.arcTo(x + w, y, x + w, y + h, rr);
            ctx.arcTo(x + w, y + h, x, y + h, rr);
            ctx.arcTo(x, y + h, x, y, rr);
            ctx.arcTo(x, y, x + w, y, rr);
            ctx.closePath();
        };

        // Minimal parser for the FIRST box-shadow only (ignores "inset" and spread)
        const parseBoxShadow = (sh) => {
            if (!sh || sh === "none") return null;
            const m = sh.match(/(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px(?:\s+(\d+(?:\.\d+)?)px)?(?:\s+\d+(?:\.\d+)?)?\s+(.*)/);
            if (!m) return null;
            const [, ox, oy, blur = "0", color = "rgba(0,0,0,0.25)"] = m;
            return {ox: +ox, oy: +oy, blur: +blur, color: color.trim()};
        };

        // Optional ticking of the time element while recording
        let ticking = false, tickTimer = null;
        const startTick = () => {
            if (!enableTimeTicker || ticking) return;
            ticking = true;
            tickTimer = setInterval(() => {
                if (this.top_bar_time) {
                    this.top_bar_time.textContent = new Date().toLocaleTimeString();
                }
            }, 1000);
        };
        const stopTick = () => {
            ticking = false;
            if (tickTimer) clearInterval(tickTimer), (tickTimer = null);
        };

        // -------- set higher internal resolution while recording ----------
        this.babylon._prevScaling = engine.getHardwareScalingLevel?.() ?? 1;
        const scaleDown = 1 / upscale;
        engine.setHardwareScalingLevel(Math.max(0.25, this.babylon._prevScaling * scaleDown));

        // -------- capture WebGL canvas via video element ----------
        // WebGL canvases have preserveDrawingBuffer=false by default, so reading
        // from the canvas at arbitrary times (setInterval) yields blank frames.
        // Piping through captureStream → <video> keeps the latest decoded frame.
        const srcVideo = document.createElement('video');
        srcVideo.muted = true;
        srcVideo.playsInline = true;
        srcVideo.style.display = 'none';
        document.body.appendChild(srcVideo);
        const srcStream = src.captureStream(fps);
        srcVideo.srcObject = srcStream;
        srcVideo.play().catch(() => {});

        // -------- build mix canvas ----------
        const mix = document.createElement('canvas');
        const ctx = mix.getContext('2d', {alpha: true});
        ctx.imageSmoothingEnabled = true;
        syncSize();

        // -------- per-frame composer ----------
        let drawIntervalId = null;
        const draw = () => {
            if (mix.width !== src.width || mix.height !== src.height) syncSize();

            // CSS pixels -> video pixels; keeps fonts crisp under DPR / scaling
            const rect = src.getBoundingClientRect();
            const cssToVideo = rect.width ? (src.width / rect.width) : (window.devicePixelRatio || 1);

            ctx.clearRect(0, 0, mix.width, mix.height);
            ctx.drawImage(srcVideo, 0, 0, mix.width, mix.height);

            // draw a "pill" for a DOM element at left or right edge
            const drawPill = (el, anchor = "left") => {
                if (!el) return;

                const s = getComputedStyle(el);
                if (s.display === "none" || s.visibility === "hidden" || (parseFloat(s.opacity) || 1) === 0) return;

                const text = el.textContent ?? "";

                // font
                const fontPx = (parseFloat(s.fontSize) || 16) * cssToVideo;
                const font = `${s.fontStyle || ""} ${s.fontVariant || ""} ${s.fontWeight || 400} ${fontPx}px ${s.fontFamily || "sans-serif"}`.trim();
                ctx.font = font;
                ctx.textBaseline = "top";

                // paddings
                const padL = (parseFloat(s.paddingLeft) || 12) * cssToVideo;
                const padR = (parseFloat(s.paddingRight) || 12) * cssToVideo;
                const padT = (parseFloat(s.paddingTop) || 6) * cssToVideo;
                const padB = (parseFloat(s.paddingBottom) || 6) * cssToVideo;

                // text metrics
                const m = ctx.measureText(text);
                const tW = m.width;
                const tH = (m.actualBoundingBoxAscent || fontPx * 0.8) + (m.actualBoundingBoxDescent || fontPx * 0.2);

                // box size + position
                const boxW = tW + padL + padR;
                const boxH = tH + padT + padB;

                const inset = 16 * cssToVideo;
                let x = inset, y = inset;
                if (anchor === "right") x = mix.width - inset - boxW;

                // styles
                const bg = (s.backgroundColor && s.backgroundColor !== "rgba(0, 0, 0, 0)")
                    ? s.backgroundColor
                    : "rgba(0,0,0,0.55)";
                const color = s.color || "#fff";
                const radius = ((parseFloat(s.borderTopLeftRadius) || parseFloat(s.borderRadius) || (boxH / 2))) * cssToVideo;
                const bw = (parseFloat(s.borderWidth) || 0) * cssToVideo;
                const bc = s.borderColor || "transparent";
                const bs = parseBoxShadow(s.boxShadow);

                // background + shadow
                ctx.save();
                if (bs) {
                    ctx.shadowColor = bs.color;
                    ctx.shadowBlur = bs.blur * cssToVideo;
                    ctx.shadowOffsetX = bs.ox * cssToVideo;
                    ctx.shadowOffsetY = bs.oy * cssToVideo;
                } else {
                    ctx.shadowColor = "transparent";
                }
                ctx.globalAlpha = 0.8;

                roundRectPath(ctx, x, y, boxW, boxH, radius);
                ctx.fillStyle = bg;
                ctx.fill();

                if (bw > 0) {
                    ctx.lineWidth = bw;
                    ctx.strokeStyle = bc;
                    ctx.stroke();
                }

                // text (no shadow for crisp glyphs)
                ctx.shadowColor = "transparent";
                ctx.fillStyle = color;
                ctx.fillText(text, x + padL, y + padT);
                ctx.restore();
            };

            // LEFT: title, RIGHT: time — read LIVE every frame
            drawPill(this.top_bar_title, "left");
            drawPill(this.top_bar_time, "right");

            // Draw custom overlay labels at their configured positions
            if (this._overlayLabels?.size > 0) {
                for (const [, entry] of this._overlayLabels) {
                    const labelEl = entry.el;
                    if (labelEl.style.display === 'none' || !labelEl.textContent) continue;
                    const cs = getComputedStyle(labelEl);
                    const fontSize = (entry.fontSize || 14) * cssToVideo;
                    const padL = Math.round(fontSize * 0.6);
                    const padR = padL;
                    const padT = Math.round(fontSize * 0.35);
                    const padB = padT;
                    const font = `600 ${fontSize}px ${cs.fontFamily || 'sans-serif'}`;
                    ctx.font = font;
                    const textW = ctx.measureText(labelEl.textContent).width;
                    const boxW = padL + textW + padR;
                    const boxH = padT + fontSize + padB;
                    const radius = 6 * cssToVideo;
                    // Position from normalized coords (x: 0=left, 1=right; y: 0=top, 1=bottom)
                    const nx = entry.x ?? 0.05;
                    const ny = entry.y ?? 0.95;
                    const px = nx * mix.width - boxW * nx;  // anchor shifts with x: 0→left-aligned, 1→right-aligned
                    const py = ny * mix.height - boxH * ny;
                    ctx.save();
                    ctx.globalAlpha = 0.8;
                    roundRectPath(ctx, px, py, boxW, boxH, radius);
                    ctx.fillStyle = cs.backgroundColor || 'rgba(0,0,0,0.6)';
                    ctx.fill();
                    ctx.shadowColor = 'transparent';
                    ctx.fillStyle = cs.color || '#fff';
                    ctx.fillText(labelEl.textContent, px + padL, py + padT);
                    ctx.restore();
                }
            }

        };
        const drawIntervalMs = Math.max(1, Math.round(1000 / fps));
        drawIntervalId = setInterval(draw, drawIntervalMs);

        // -------- start recording the mix canvas ----------
        const mime = _chooseBestMime();
        const stream = mix.captureStream(fps);
        const rec = new MediaRecorder(stream, {mimeType: mime, videoBitsPerSecond});

        // Hook into your existing stop flow
        this.babylon._customRecorder = rec;
        this.babylon.is_recording = true;

        const chunks = [];
        rec.ondataavailable = (e) => {
            if (e.data?.size) chunks.push(e.data);
        };

        rec.onstop = () => {
            clearInterval(drawIntervalId);
            stopTick();

            // Clean up the video element used for canvas capture
            srcVideo.pause();
            srcVideo.srcObject = null;
            srcStream.getTracks().forEach(t => t.stop());
            srcVideo.remove();

            const blob = new Blob(chunks, {type: mime});

            if (this.babylon._pendingSavePath) {
                this.babylon._sendBlobToServer(blob, fileName);
                this.babylon._pendingSavePath = null;
            } else {
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = fileName;
                a.click();
                setTimeout(() => URL.revokeObjectURL(a.href), 5000);
            }

            try {
                engine.setHardwareScalingLevel(this.babylon._prevScaling);
                this.babylon.log("Setting back hardware scaling", "important");
            } catch {
            }

            this.babylon._customRecorder = null;
            this.babylon.is_recording = false;
            this.babylon.log(`High-bitrate recording saved (${Math.round(blob.size / 1024)} KB).`, "important");
            this.babylon.callbacks.get('record_stop').call();
        };

        rec.start(1000); // collect data every second
        this.babylon.log(`Started high-bitrate recording with HUD (fps=${fps}, ~${Math.round(videoBitsPerSecond / 1e6)} Mbps, ${mime}).`, "important");
        this.babylon.callbacks.get('record_start').call(fileName);

        // Start optional ticking of the time label
        startTick();
    }

    /* === PRIVATE METHODS ========================================================================================== */
    _onBabylonLog(message, level = 'info') {
        switch (level) {
            case 'debug':
                this.addLineToTerminal(message, 'white', false);
                break;
            case 'info':
                this.addLineToTerminal(message, 'white', false);
                break;
            case 'warning':
                this.addLineToTerminal(message, 'orange', true);
                break;
            case 'error':
                this.addLineToTerminal(message, 'red', true);
                break;
            case 'important':
                this.addLineToTerminal(message, 'green', true);
                break;
            default:
                console.warn(`BabylonContainer._onBabylonLog: unknown log level: ${level}`);
                break;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _attachBabylonCallbacks() {
        this.babylon.callbacks.get('log').register(this._onBabylonLog.bind(this));
        this.babylon.callbacks.get('record_start').register(() => {
            this.button_record.startBlinking();
        });
        this.babylon.callbacks.get('record_stop').register(() => {
            this.button_record.stopBlinking();
        })

        this.babylon.callbacks.get('websocket_connected').register(() => {
            this._setConnectionStatus(true, this.babylon.getMessagesPerSecond());
            if (this._mpsTimer) clearInterval(this._mpsTimer);
            this._mpsTimer = setInterval(() => {
                this._setConnectionStatus(true, this.babylon.getMessagesPerSecond());
            }, 1000);
        });
        this.babylon.callbacks.get('websocket_disconnected').register(() => {
            if (this._mpsTimer) clearInterval(this._mpsTimer), this._mpsTimer = null;
            this._setConnectionStatus(false, '');
        });

        this.babylon.callbacks.get('initialized').register(this._on_babylon_initialized.bind(this))

        this.babylon.callbacks.get('add_camera').register((camera_data) => {
            this.addCameraView(camera_data);
        });

        this.babylon.callbacks.get('follow_started').register((objectId) => {
            this._showFollowBadge(objectId);
        });
        this.babylon.callbacks.get('follow_stopped').register(() => {
            this._hideFollowBadge();
        });
    }

    _on_babylon_initialized() {
        this.addCameraView({
            name: 'default',
            position: coordinatesFromBabylon(this.babylon.camera.position),
            target: coordinatesFromBabylon(this.babylon.camera.target),
            alpha: this.babylon.camera.alpha,
            beta: this.babylon.camera.beta,
            radius: this.babylon.camera.radius,
            fov: this.babylon.camera.fov,
        })

        // Add camera views from config (if any)
        const cameras = this.babylon.config.cameras;
        if (Array.isArray(cameras)) {
            for (const cam of cameras) {
                this.addCameraView(cam);
            }
        }
    }

    _setConnectionStatus(connected, messages_per_second) {
        if (connected) {
            this.connection_circle.style.backgroundColor = getColor([154 / 255, 205 / 255, 50 / 255]);
            this.connection_message.style.display = 'block';
            this.connection_message.textContent = `${messages_per_second} msg/s`;
        } else {
            this.connection_circle.style.backgroundColor = getColor([255 / 255, 64 / 255, 64 / 255]);
            this.connection_message.textContent = ``;
            this.connection_message.style.display = 'none';
        }


    }

    /* +++ DEBUG OVERLAY ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++ */
    _ensureDebugOverlayScaffold() {
        if (this._debugBuilt) return;

        // Panel that holds the content (we'll scroll this programmatically)
        this._debugPanel = document.createElement('div');
        this._debugPanel.classList.add('debug-panel');
        // Important: we will NOT enable pointer events on this element, so canvas interactions pass through.
        // Scrolling is handled by a global wheel interceptor.
        this.debug_overlay.appendChild(this._debugPanel);
        this._debugBuilt = true;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _formatNum(n, digits = 3) {
        if (n == null || Number.isNaN(n)) return '—';
        return Number(n).toFixed(digits);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _formatVec3(v) {
        if (!v) return '—';
        return `(${this._formatNum(v[0])}, ${this._formatNum(v[1])}, ${this._formatNum(v[2])})`;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _buildCategory(parent, name, buildBody) {
        const collapsed = !!this._debugCollapse[name];

        const cat = document.createElement('div');
        cat.className = 'debug-category' + (collapsed ? ' collapsed' : '');
        cat.dataset.name = name;

        // Header (visually clickable, but the panel itself is pointer-events:none;
        // we toggle via a global capture-phase click interceptor)
        const title = document.createElement('button');
        title.type = 'button';
        title.className = 'debug-category-title';
        title.innerHTML = `
        <span class="caret" aria-hidden="true"></span>
        <span class="title-text">${name}</span>
    `;

        const body = document.createElement('div');
        body.className = 'debug-body';

        buildBody(body);

        cat.appendChild(title);
        cat.appendChild(body);
        parent.appendChild(cat);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _renderDebugOverlay(debugData) {
        if (!this._debugPanel) return;

        const root = document.createElement('div');
        root.className = 'debug-root';

        // ===== Camera =====
        const cam = debugData?.camera || {present: false};

        this._buildCategory(root, 'Camera', (body) => {
            const addField = (label, value, indent = false) => {
                const row = document.createElement('div');
                row.className = 'debug-field' + (indent ? ' indent' : '');
                const l = document.createElement('span');
                l.className = 'debug-label';
                l.textContent = label;
                const v = document.createElement('span');
                v.className = 'debug-value';
                v.textContent = value;
                row.appendChild(l);
                row.appendChild(v);
                body.appendChild(row);
            };

            if (!cam.present) {
                addField('Present', 'No active camera');
                return;
            }

            addField('Type', cam.type || '—');
            addField('Name', cam.name ?? '—');
            addField('Mode', cam.mode ?? '—');
            addField('FOV (deg)', this._formatNum(cam.fov_deg));
            addField('MinZ / MaxZ', `${this._formatNum(cam.minZ)} / ${this._formatNum(cam.maxZ)}`);
            addField('Position', this._formatVec3(cam.position));
            if (cam.target) addField('Target', this._formatVec3(cam.target));
            if (cam.rotation_euler_deg) {
                const [rx, ry, rz] = cam.rotation_euler_deg;
                addField('Rotation (deg)', `(${this._formatNum(rx)}, ${this._formatNum(ry)}, ${this._formatNum(rz)})`);
            }
            if (cam.upVector) addField('Up Vector', this._formatVec3(cam.upVector));
            addField('Inertia', this._formatNum(cam.inertia));

            if (cam.arcRotate) {
                addField('— ArcRotate —', '', false);
                addField('alpha (deg)', this._formatNum(cam.arcRotate.alpha_deg), true);
                addField('beta (deg)', this._formatNum(cam.arcRotate.beta_deg), true);
                addField('radius', this._formatNum(cam.arcRotate.radius), true);
                addField('α limits (deg)',
                    `${this._formatNum(cam.arcRotate.lowerAlphaLimit_deg)} / ${this._formatNum(cam.arcRotate.upperAlphaLimit_deg)}`, true);
                addField('β limits (deg)',
                    `${this._formatNum(cam.arcRotate.lowerBetaLimit_deg)} / ${this._formatNum(cam.arcRotate.upperBetaLimit_deg)}`, true);
                addField('radius limits',
                    `${this._formatNum(cam.arcRotate.lowerRadiusLimit)} / ${this._formatNum(cam.arcRotate.upperRadiusLimit)}`, true);
                addField('wheelPrecision', this._formatNum(cam.arcRotate.wheelPrecision, 0), true);
                addField('wheelDeltaPercentage', this._formatNum(cam.arcRotate.wheelDeltaPercentage, 4), true);
                addField('panningSensibility', this._formatNum(cam.arcRotate.panningSensibility, 0), true);
                addField('angularSensibilityX / Y',
                    `${this._formatNum(cam.arcRotate.angularSensibilityX, 0)} / ${this._formatNum(cam.arcRotate.angularSensibilityY, 0)}`, true);
                addField('behaviors', [
                    cam.arcRotate.useAutoRotationBehavior ? 'auto' : null,
                    cam.arcRotate.useBouncingBehavior ? 'bounce' : null,
                    cam.arcRotate.useFramingBehavior ? 'framing' : null
                ].filter(Boolean).join(', ') || '—', true);
                addField('inertial α/β/radius',
                    `${this._formatNum(cam.arcRotate.inertialAlphaOffset_deg)} / ${this._formatNum(cam.arcRotate.inertialBetaOffset_deg)} / ${this._formatNum(cam.arcRotate.inertialRadiusOffset)}`, true);
                addField('inertial pan X/Y',
                    `${this._formatNum(cam.arcRotate.inertialPanningX)} / ${this._formatNum(cam.arcRotate.inertialPanningY)}`, true);
            }

            if (cam.follow) {
                addField('— Follow —', '', false);
                addField('lockedTarget', cam.follow.lockedTarget ? 'yes' : 'no', true);
                addField('radius', this._formatNum(cam.follow.radius), true);
                addField('heightOffset', this._formatNum(cam.follow.heightOffset), true);
                addField('rotationOffset (deg)', this._formatNum(cam.follow.rotationOffset_deg), true);
                addField('cameraAcceleration', this._formatNum(cam.follow.cameraAcceleration, 4), true);
                addField('maxCameraSpeed', this._formatNum(cam.follow.maxCameraSpeed, 4), true);
            }

            if (cam.freeLike) {
                const name = (cam.type || '').replace('Camera', '') || 'Free-like';
                addField(`— ${name} —`, '', false);
                addField('speed', this._formatNum(cam.freeLike.speed), true);
                addField('angularSensibility', this._formatNum(cam.freeLike.angularSensibility, 0), true);
                addField('keys Up/Down/Left/Right',
                    `${JSON.stringify(cam.freeLike.keysUp)} / ${JSON.stringify(cam.freeLike.keysDown)} / ${JSON.stringify(cam.freeLike.keysLeft)} / ${JSON.stringify(cam.freeLike.keysRight)}`, true);
                addField('ellipsoid', this._formatVec3(cam.freeLike.ellipsoid), true);
            }
        });

        // Swap content then cache header elements for hit-testing
        this._debugPanel.replaceChildren(root);
        this._debugHeaders = Array.from(this._debugPanel.querySelectorAll('.debug-category-title'));
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _findHeaderAt(x, y) {
        if (!this._debugPanel || !this._debugHeaders || !this._debugHeaders.length) return null;
        for (const h of this._debugHeaders) {
            const r = h.getBoundingClientRect();
            if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return h;
        }
        return null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _attachDebugInterceptors() {
        // Wheel: scroll the panel and block Babylon zoom (unchanged)
        if (!this._onDebugWheel) {
            this._onDebugWheel = (e) => {
                if (!this._debugPanel || this.debug_overlay.style.display !== 'flex') return;

                const r = this._debugPanel.getBoundingClientRect();
                const overPanel = (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom);
                if (!overPanel) return;

                const unit = (e.deltaMode === 1) ? 16 : 1; // Firefox normalization
                this._debugPanel.scrollTop += e.deltaY * unit;
                this._debugPanel.scrollLeft += e.deltaX * unit;

                e.preventDefault();
                e.stopPropagation();
                if (e.stopImmediatePropagation) e.stopImmediatePropagation();
            };
            window.addEventListener('wheel', this._onDebugWheel, {passive: false, capture: true});
        }

        // Toggle on pointerdown ONLY, then fence the click
        if (!this._onDebugPointerDown) {
            this._onDebugPointerDown = (e) => {
                if (!this._debugPanel || this.debug_overlay.style.display !== 'flex') return;

                const header = this._findHeaderAt(e.clientX, e.clientY);
                if (!header) return;

                const cat = header.closest('.debug-category');
                const name = cat?.dataset?.name;
                const isCollapsed = !cat.classList.contains('collapsed');
                cat.classList.toggle('collapsed', isCollapsed);
                if (name) this._debugCollapse[name] = isCollapsed;

                // Fence the follow-up 'click' so it doesn't toggle again
                this._suppressClickUntil = performance.now() + 350;

                e.preventDefault();
                e.stopPropagation();
                if (e.stopImmediatePropagation) e.stopImmediatePropagation();
            };
            window.addEventListener('pointerdown', this._onDebugPointerDown, {capture: true});
        }

        // Swallow the synthetic click right after we handled pointerdown
        if (!this._onDebugClickFence) {
            this._onDebugClickFence = (e) => {
                if (performance.now() < this._suppressClickUntil) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (e.stopImmediatePropagation) e.stopImmediatePropagation();
                }
            };
            window.addEventListener('click', this._onDebugClickFence, {capture: true});
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _detachDebugInterceptors() {
        if (this._onDebugWheel) {
            window.removeEventListener('wheel', this._onDebugWheel, {capture: true});
            this._onDebugWheel = null;
        }
        if (this._onDebugPointerDown) {
            window.removeEventListener('pointerdown', this._onDebugPointerDown, {capture: true});
            this._onDebugPointerDown = null;
        }
        if (this._onDebugClickFence) {
            window.removeEventListener('click', this._onDebugClickFence, {capture: true});
            this._onDebugClickFence = null;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _startDebugUpdates() {
        if (this._debugInterval) return;
        this._debugInterval = setInterval(() => {
            const data = this.babylon.getDebugData();
            this._renderDebugOverlay(data);
        }, 200);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _stopDebugUpdates() {
        if (this._debugInterval) {
            clearInterval(this._debugInterval);
            this._debugInterval = null;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    openDebugOverlay() {
        this.closeTerminalOverlay();
        this.closeAssetsOverlay();
        this.closeSettingsOverlay();
        this.debug_overlay.style.display = 'flex';

        const controlsHeight = this.babylon_controls.offsetHeight;
        const topBarHeight = this.element.querySelector('.top-bar').offsetHeight;

        this.debug_overlay.style.top = `${topBarHeight + 5}px`;
        this.debug_overlay.style.bottom = `${controlsHeight + 5}px`;

        this._ensureDebugOverlayScaffold();

        this._renderDebugOverlay(this.babylon.getDebugData());
        this._startDebugUpdates();
        this._attachDebugInterceptors();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    closeDebugOverlay() {
        this._stopDebugUpdates();
        this._detachDebugInterceptors();
        this.debug_overlay.style.display = 'none';
    }

    resize() {

    }

    onFirstShow() {
        this.babylon._addGlobalResizeListener();
        const engine = this.babylon.scene.getEngine();
        // Re-apply DPR + size for first real layout
        if (typeof this.babylon._addGlobalResizeListener === 'function') {
            // already armed; just trigger it by a manual resize
            engine.resize(true);
        } else {
            // safety: do it manually
            engine.setHardwareScalingLevel(1 / (window.devicePixelRatio || 1));
            engine.resize(true);
        }
    }
}