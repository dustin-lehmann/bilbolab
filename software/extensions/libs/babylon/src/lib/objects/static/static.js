import {BabylonObject} from "../../objects.js";
import {
    StandardMaterial,
    SceneLoader,
    DynamicTexture,
    TransformNode,
    Vector3,
    MeshBuilder,
    PBRMaterial,
    Color3,
    Mesh,
    VertexData,
    Ray,
    Matrix,
} from "@babylonjs/core";

import {
    coordinatesToBabylon,
    getBabylonColor3,
    loadModel,
    getHTMLColor,
} from "../../babylon_utils.js";
import {Quaternion} from "../../quaternion.js";
import {BabylonLabeledLineDrawing, BabylonObjectLabeledLineDrawing, BabylonObjectLineDrawing} from "../drawings";


export class ArucoStatic extends BabylonObject {
    constructor(id, scene, payload = {}) {
        super(id, scene, payload);

        const default_config = {
            model: "static.babylon",
            static_rotation: Quaternion.fromEulerAngles([0, 0, -Math.PI / 2], "xyz", true),
            // static_rotation: Quaternion.fromEulerAngles([0, 0, 0], "xyz", true),
            scaling: 1
        }

        const default_data = {x: 0, y: 0, psi: 0};
        this.config = {...this.config, ...default_config, ...payload.config};
        this.data = {...default_data, ...this.data};

        this.modelRoot = new TransformNode(`robotModel_${this.id}`, this.scene);
        this.modelRoot.parent = this.root;

        this.static_rotation_quaternion = new Quaternion(this.config.static_rotation);

        this.buildObject();
        this.onLoaded().then(() => {
            this.setState(this.data.x, this.data.y, this.data.psi);
        });

    }

    buildObject() {
        this._ready = SceneLoader
            .ImportMeshAsync("", "./", loadModel(this.config.model), this.scene)
            .then(({meshes}) => {
                this.onMeshLoaded(meshes);
                return this;
            });
    }

    onMeshLoaded(newMeshes) {
        // Parent all imported meshes under modelRoot
        for (const m of newMeshes) {
            m.parent = this.modelRoot;
            m.metadata = m.metadata || {};
            m.metadata.object = this;
            m.isPickable = true;
        }
        const s = this.config.scaling;
        this.modelRoot.scaling.set(s, s, -s);

        // this.modelRoot.rotationQuaternion = this.static_rotation_quaternion.babylon();

        this.material = new StandardMaterial(`material_${this.id}`, this.scene);
        if (this.config.color) {
            this.material.diffuseColor = getBabylonColor3([1, 1, 1]);
            this.material.specularColor = getBabylonColor3([0.3, 0.3, 0.3]);
        }
        // this.root.material = this.material;
        // Make meshes cast shadows (the TransformNode itself can't)
        if (this.scene.shadowGenerator?.addShadowCaster) {
            for (const m of newMeshes) {
                if (m instanceof Mesh) this.scene.shadowGenerator.addShadowCaster(m);
            }
        }

        // this.setState(this.data.x, this.data.y, this.data.psi);
        this.loaded = true;

        this.onBuilt();
        // this.showBoundObject();
    }

    dim(state) {
        return undefined;
    }

    highlight(state) {
        return undefined;
    }

    onMessage(message) {
        return undefined;
    }

    update(data) {
        return undefined;
    }

    setState(x, y, psi) {
        this.setPosition([x, y, 0]);
        const orientation = Quaternion.fromEulerAngles([psi, 0, 0], "zyx", true);
        this.setOrientation(orientation);
    }

    // setPosition(position) {
    //     let coords;
    //
    //     if (Array.isArray(position)) {
    //         coords = position;
    //     } else if (typeof position === "object" && position !== null &&
    //         "x" in position && "y" in position && "z" in position) {
    //         coords = [position.x, position.y, position.z];
    //     } else {
    //         throw new Error("Invalid position format. Expected [x, y, z] or {x, y, z}.");
    //     }
    //
    //     this.position = coords;
    //     const pos = coordinatesToBabylon([
    //         this.position[0],
    //         this.position[1],
    //         0
    //     ]);
    //     if (this.root) this.root.position = pos;
    // }

    // setOrientation(orientation) {
    //     this.orientation = new Quaternion(orientation);
    //     if (this.root) {
    //         this.root.rotationQuaternion = this.orientation.babylon();
    //     }
    // }

    onLoaded() {
        return this._ready;
    }

}