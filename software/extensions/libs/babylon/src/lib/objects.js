import {Callbacks, splitPath} from "../../../../gui/src/lib/helpers.js";

import {
    TransformNode,
    // Quaternion as BQ,
    Vector3,
    MeshBuilder,
    StandardMaterial,
    Color3,
    Matrix,
    Mesh,
    Color4
} from "@babylonjs/core";

import {EventEmitter} from "events";
import {Quaternion} from "./quaternion.js"
import {coordinatesToBabylon, quatChanged, vecChanged} from "./babylon_utils";


export class BabylonObject extends EventEmitter {
    /** @type {string} */
    id;

    /** @type {TransformNode} */
    root = null;

    /** @type {BABYLON.Mesh} */
    bounding_object = null;

    /** @type {BABYLON.Scene} */
    scene;

    /** @type {Object} */
    config;

    /** @type {Object} */
    data;

    /** @type {array} */
    position = [];

    /** @type {BQ|any} */
    orientation = null;

    /** @type {Babylon | BabylonObjectGroup} */
    parent = null;

    /** @type {boolean} */
    visible = true;

    built = false;

    constructor(id, babylon, payload = {}) {
        super();
        this.id = id;
        this.babylon = babylon;
        this.scene = babylon.scene;
        this.payload = payload;

        const default_config = {
            static_rotation: Quaternion.fromEulerAngles([0, 0, 0], "xyz", true),
            bounding_object: "box",            // "sphere" | "box" | "none"
            // If null -> auto from hierarchy.
            // Sphere: number = diameter (world units)
            // Box: [x, y, z] = width/height/depth (world units)
            bounding_object_size: null,
            // Local offset from root (x,y,z) in world units (applied in root's local frame)
            bounding_object_offset: [0, 0, 0],
            // Local rotation offset as quaternion [x,y,z,w] or {x,y,z,w}
            bounding_object_offset_rotation: [0, 0, 0, 1]
        };

        this.config = {...default_config, ...(this.payload.config || {})};
        this.data = this.payload.data || {};

        // stable transform root
        this.root = new TransformNode(`${this.id}_root`, this.scene);
        this.root.metadata = {object: this};

        this.callbacks = new Callbacks();
        this.callbacks.add("event");
        this.callbacks.add("log");
        this.callbacks.add("send_message");

        this._addListeners();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * @abstract
     */
    buildObject() {
        throw new Error("Method not implemented.");
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onBuilt() {
        // This gets called once the object is built. We can now proceed to build the bounding object
        this.bounding_object = this.buildBoundingObject();
        this.built = true;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    buildBoundingObject() {

        if (this.config.bounding_object === "none") {
            return null;
        }

        // Gather all descendant meshes under the root
        const meshes = this.root?.getChildMeshes
            ? (this.root.getChildMeshes(false))
            : [];

        if (!meshes.length) {
            return null; // nothing to bound
        }

        // Compute world-space min/max of all meshes
        const {min, max} = Mesh.MinMax(meshes);
        const worldSize = max.subtract(min);                // Vector3 (width,height,depth in world units)
        const worldCenter = min.add(worldSize.scale(0.5));  // Vector3

        // Convert world center to root-local so the bound stays aligned when parented
        const rootWorld = this.root.getWorldMatrix();
        const invRootWorld = rootWorld.clone();
        invRootWorld.invert();
        const localCenter = Vector3.TransformCoordinates(worldCenter, invRootWorld);


        let bound;
        const type = this.config.bounding_object; // "sphere" | "box"

        if (type === 'box') {
            const dimensions = [Math.max(worldSize.x, 1e-6), Math.max(worldSize.y, 1e-6), Math.max(worldSize.z, 1e-6)];
            bound = MeshBuilder.CreateBox(`${this.id}_bound_box`, {
                width: dimensions[0],
                height: dimensions[1],
                depth: dimensions[2]
            }, this.scene);
        }

        bound.parent = this.root;
        bound.position = new Vector3(localCenter.x, localCenter.y, -localCenter.z);

        // // Wireframe material + red edges
        const mat = new StandardMaterial(`${this.id}_bound_mat`, this.scene);
        mat.wireframe = true;
        mat.diffuseColor = Color3.Red();
        mat.emissiveColor = Color3.Red();
        mat.backFaceCulling = false;
        bound.material = mat;

        // Crisp edges (works nicely even when wireframe is off)
        bound.enableEdgesRendering();
        bound.edgesWidth = 0.5;
        bound.edgesColor = new Color4(1, 0, 0, 1);


        bound.isPickable = true;
        bound.metadata = {type: 'bound', blocksVision: true, object: this};

        bound.isVisible = false;
        return bound;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setPosition(position) {
        if (!this.built) {
            return;
        }
        this.position = Array.isArray(position)
            ? (position.length === 2 ? [position[0], position[1], 0] : position)
            : [position.x, position.y, position.z ?? 0];

        this.root.position = coordinatesToBabylon(this.position);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setOrientation(orientation) {
        if (!this.built) {
            return;
        }
        this.orientation = orientation instanceof Quaternion
            ? orientation
            : new Quaternion(orientation);
        const quat = this.config.static_rotation.multiply(this.orientation);
        this.root.rotationQuaternion = quat.babylon();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setVisibility(visible) {
        this.visible = visible;
        if (this.root) this.root.setEnabled(!!visible);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    showBoundObject(state) {
        if (this.bounding_object) {
            this.bounding_object.isVisible = state;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * @abstract
     */
    highlight(state) {
        throw new Error("Method not implemented.");
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    static fromConfig(id, scene, payload) {
        return new this(id, scene, payload);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * @abstract
     */
    onMessage(message) {
        throw new Error("Method not implemented.");
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    callFunction(function_name, args) {
        let fun = this[function_name];
        if (typeof fun === "function") {
            fun.apply(this, args);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _addListeners() {

        // World Matrix Update
        if (!this.root?.onAfterWorldMatrixUpdateObservable) return;

        this._lastPose = {
            position: this.position,
            orientation: this.orientation,
        }

        this._rootObs = this.root.onAfterWorldMatrixUpdateObservable.add(() => {

            const poseChanged = vecChanged(this.position, this._lastPose.position) || quatChanged(this.orientation, this._lastPose.orientation);

            this._lastPose = {
                position: this.position,
                orientation: this.orientation,
            }
            if (poseChanged) {
                this._onRootNodeUpdate();
            }


        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _onRootNodeUpdate() {
        this.emit("update");
        console.log("BabylonObject._onRootNodeUpdate");
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Helper: normalize various quaternion shapes into BABYLON.Quaternion
    _asBabylonQuaternion(q) {
        if (!q) return new Quaternion(0, 0, 0, 1);
        if (q instanceof Quaternion) return q;
        if (Array.isArray(q)) {
            const [x = 0, y = 0, z = 0, w = 1] = q;
            return new Quaternion(x, y, z, w);
        }
        if (typeof q === "object") {
            const {x = 0, y = 0, z = 0, w = 1} = q;
            return new Quaternion(x, y, z, w);
        }
        return new Quaternion(0, 0, 0, 1);
    }
}

/* === BABYLON OBJECT GROUP ========================================================================================= */
export class BabylonObjectGroup {

    /** @type {string} */
    id;

    /** @type {BABYLON.Scene} */
    scene;

    /** @type {Babylon | BabylonObjectGroup} */
    parent = null;

    /** @type {Object} */
    config;

    /** @type {Object} */
    objects;

    /** @type {boolean} */
    visible = true;

    /* === CONSTRUCTOR ============================================================================================== */
    constructor(id, scene, config = {}, objects = {}) {

        this.id = id;
        this.scene = scene;
        this.config = config;
        this.objects = {};

        this.callbacks = new Callbacks()
        this.callbacks.add('event');
        this.callbacks.add('log');
        this.callbacks.add('send_message');

        // Build Objects from config

        if (Object.keys(objects).length > 0) {
            for (const [object_id, object_config] of Object.entries(objects)) {
                this.buildObjectFromConfig(object_id, object_config);
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getBabylonVisualization() {
        if (this.parent) {
            return this.parent.getBabylonVisualization();
        }
        return null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    addObject(object) {
        if (!(object instanceof BabylonObject) && !(object instanceof BabylonObjectGroup)) {
            throw new Error('Invalid object type. Expected BabylonObject or BabylonObjectGroup.');
        }
        if (object.id in this.objects) {
            throw new Error(`Object with ID ${object.id} already exists in this group.`);
        }
        this.objects[object.id] = object;
        object.parent = this;
        object.callbacks.get('event').register(this._onObjectEvent.bind(this));
        object.callbacks.get('log').register(this.callbacks.get('log').call.bind(this.callbacks.get('log')));
        object.callbacks.get('send_message').register(this.callbacks.get('send_message').call.bind(this.callbacks.get('send_message')));
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    removeObject(object) {
        if (!(object instanceof BabylonObject) && !(object instanceof BabylonObjectGroup)) {
            throw new Error('Invalid object type. Expected BabylonObject or BabylonObjectGroup.');
        }
        if (!(object.id in this.objects)) {
            throw new Error(`Object with ID ${object.id} does not exist in this group.`);
        }
        delete this.objects[object.id];
        object.parent = null;
        if (typeof object.delete === 'function') {
            object.delete();
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    buildObjectFromConfig(object_payload) {
        const object_type = object_payload.type;
        const object_id = object_payload.id;
        const object_config = object_payload.config;

        const object_class = BABYLON_OBJECT_MAPPINGS[object_type];
        const object = object_class.buildFromConfig(object_config, this.scene);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getObjectFromPath(path) {
        let firstSegment, remainder;

        [firstSegment, remainder] = splitPath(path);

        const childKey = `${this.id}/${firstSegment}`;

        const child = this.objects[childKey];

        if (!child) {
            console.warn(`Object with ID ${childKey} not found in group ${this.id}.`);
            return null;
        }

        if (!remainder) {
            return child;
        }

        if (child instanceof BabylonObjectGroup) {
            return child.getObjectFromPath(remainder);
        } else {
            console.warn(`Object with ID ${childKey} is not a group.`);
        }

        return null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setVisibility(visibility) {

        this.visible = visibility;
        // Go through all objects in the group and set visibility
        for (const object of Object.values(this.objects)) {
            object.setVisibility(visibility);
        }
    }

    /* === PRIVATE METHODS ========================================================================================== */
    _onObjectEvent(object, event) {
        this.callbacks.get('event').call(object, event);
    }


}