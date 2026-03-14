import {BabylonObject} from "../../objects.js";
import {MeshBuilder, StandardMaterial, Color3, Mesh, Vector3, GlowLayer} from "@babylonjs/core";
import {coordinatesToBabylon, getBabylonColor3} from "../../babylon_utils.js";

// Shared high-intensity GlowLayer for all laser meshes (created once per scene)
let _laserGlowLayer = null;

function getLaserGlowLayer(scene) {
    if (!_laserGlowLayer || _laserGlowLayer.isDisposed) {
        _laserGlowLayer = new GlowLayer("laserGlow", scene, {
            blurKernelSize: 32,
        });
        _laserGlowLayer.intensity = 0.6;
    }
    return _laserGlowLayer;
}


export class BabylonLaserLine extends BabylonObject {
    constructor(id, scene, payload = {}) {
        super(id, scene, payload);

        const default_config = {
            color: [1, 0, 0],
            width: 0.005,
            glow_intensity: 2.0,
            alpha: 1.0,
        };
        this.config = {...default_config, ...this.config};

        const default_data = {
            start: [0, 0, 0],
            end: [1, 0, 0],
        };
        this.data = {...default_data, ...this.data};

        this.tube = null;
        this.material = null;

        this.buildObject();
    }

    buildObject() {
        const start = coordinatesToBabylon(this.data.start);
        const end = coordinatesToBabylon(this.data.end);

        const path = [start, end];
        const radius = Math.max(0.0005, this.config.width * 0.5);

        this.tube = MeshBuilder.CreateTube(
            `${this.id}_tube`,
            {path, radius, cap: Mesh.CAP_ALL, updatable: true},
            this.scene
        );
        this.tube.parent = this.root;

        // Emissive material for glow
        this.material = new StandardMaterial(`${this.id}_mat`, this.scene);
        const color = getBabylonColor3(this.config.color);
        this.material.diffuseColor = Color3.Black();
        this.material.specularColor = Color3.Black();
        this.material.emissiveColor = color.scale(this.config.glow_intensity);
        this.material.alpha = this.config.alpha;
        this.material.backFaceCulling = false;

        this.tube.material = this.material;
        this.tube.isPickable = false;
        // visibility affects both the mesh rendering and the glow pass
        this.tube.visibility = this.config.alpha;

        // Register with dedicated high-intensity laser GlowLayer
        const glowLayer = getLaserGlowLayer(this.scene);
        glowLayer.addIncludedOnlyMesh(this.tube);

        this.onBuilt();
    }

    update(data) {
        const start = data.start || this.data.start;
        const end = data.end || this.data.end;

        this.data.start = start;
        this.data.end = end;

        const bStart = coordinatesToBabylon(start);
        const bEnd = coordinatesToBabylon(end);
        const path = [bStart, bEnd];
        const radius = Math.max(0.0005, this.config.width * 0.5);

        // Rebuild tube in-place
        MeshBuilder.CreateTube(
            `${this.id}_tube`,
            {path, radius, instance: this.tube}
        );
    }

    updateConfig(config) {
        this.config = {...this.config, ...config};

        const color = getBabylonColor3(this.config.color);
        this.material.emissiveColor = color.scale(this.config.glow_intensity);
        this.material.alpha = this.config.alpha;
        this.tube.visibility = this.config.alpha;
    }

    highlight(state) {
    }

    onMessage(message) {
    }

    dim(state) {
        if (this.material) {
            const a = state ? 0.2 : (this.config.alpha ?? 1.0);
            this.material.alpha = a;
            this.tube.visibility = a;
        }
    }

    delete() {
        if (this.tube) {
            const glowLayer = getLaserGlowLayer(this.scene);
            glowLayer.removeIncludedOnlyMesh(this.tube);
            this.tube.dispose();
        }
        if (this.material) this.material.dispose();
    }
}
