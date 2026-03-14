import {BabylonObject} from "../../objects.js";
import {MeshBuilder, StandardMaterial, Color3, GlowLayer} from "@babylonjs/core";
import {coordinatesToBabylon, getBabylonColor3} from "../../babylon_utils.js";
import {Quaternion} from "../../quaternion.js";


// Dedicated high-intensity glow layer for cylinder meshes (shared, created once per scene)
let _cylinderGlowLayer = null;

function getCylinderGlowLayer(scene) {
    if (!_cylinderGlowLayer || _cylinderGlowLayer.isDisposed) {
        _cylinderGlowLayer = new GlowLayer("cylinderGlow", scene, {
            blurKernelSize: 32,
        });
        _cylinderGlowLayer.intensity = 0.6;
    }
    return _cylinderGlowLayer;
}

export class BabylonCylinder extends BabylonObject {
    constructor(id, scene, payload = {}) {
        super(id, scene, payload);

        const default_config = {
            color: [0.5, 0.5, 0.5],
            diameter: 0.1,
            height: 1.0,
            tessellation: 24,
            alpha: 1.0,
            accept_shadows: true,
            glow: false,            // enable emissive glow
            glow_intensity: 2.0,    // emissive color multiplier
        };
        this.config = {...default_config, ...this.config};

        const default_data = {
            position: {x: 0, y: 0, z: 0},
            orientation: [1, 0, 0, 0],
        };
        this.data = {...default_data, ...this.data};

        this.buildObject();
    }

    buildObject() {
        // BabylonJS CreateCylinder: height is along local Y axis
        this.mesh = MeshBuilder.CreateCylinder(`${this.id}_cyl`, {
            height: this.config.height,
            diameter: this.config.diameter,
            tessellation: this.config.tessellation,
        }, this.scene);

        this.mesh.parent = this.root;

        // Material
        this.material = new StandardMaterial(`${this.id}_mat`, this.scene);
        const color = getBabylonColor3(this.config.color);

        if (this.config.glow) {
            // Emissive-only material (like laser line)
            this.material.diffuseColor = Color3.Black();
            this.material.specularColor = Color3.Black();
            this.material.emissiveColor = color.scale(this.config.glow_intensity);
            this.material.backFaceCulling = false;
        } else {
            this.material.diffuseColor = color;
        }

        this.material.alpha = this.config.alpha;
        this.mesh.material = this.material;
        this.mesh.visibility = this.config.alpha;

        // Register with dedicated high-intensity glow layer
        if (this.config.glow) {
            const glowLayer = getCylinderGlowLayer(this.scene);
            glowLayer.addIncludedOnlyMesh(this.mesh);
        }

        // Shadows
        if (this.scene.shadowGenerator) {
            this.scene.shadowGenerator.addShadowCaster(this.mesh);
        }
        this.mesh.receiveShadows = this.config.accept_shadows;

        // Picking
        this.mesh.isPickable = false;
        this.mesh.metadata = {object: this};

        this.onBuilt();

        this.setPosition(this.data.position);
        this.setOrientation(this.data.orientation);
    }

    update(data) {
        const position = data.position || this.data.position;
        const orientation = data.orientation || this.data.orientation;
        this.setPosition(position);
        this.setOrientation(orientation);
    }

    setColor(color) {
        const c = getBabylonColor3(color);
        if (this.config.glow) {
            this.material.emissiveColor = c.scale(this.config.glow_intensity);
        } else {
            this.material.diffuseColor = c;
        }
        this.config.color = color;
    }

    highlight(state) {}
    onMessage(message) {}
    dim(state) {}

    delete() {
        if (this.config.glow && this.mesh) {
            const glowLayer = getCylinderGlowLayer(this.scene);
            glowLayer.removeIncludedOnlyMesh(this.mesh);
        }
        if (this.mesh) this.mesh.dispose();
        if (this.material) this.material.dispose();
    }
}
