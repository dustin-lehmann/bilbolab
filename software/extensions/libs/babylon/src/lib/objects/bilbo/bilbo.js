import {BabylonObject} from "../../objects.js";
import {
    CreateBox,
    StandardMaterial,
    Texture,
    SceneLoader,
    DynamicTexture,
    TransformNode,
    Vector3,
    Mesh,
    MeshBuilder, Color3, ActionManager, ExecuteCodeAction, MultiMaterial, SubMesh, AbstractMesh, PBRMaterial
} from "@babylonjs/core";

import {
    coordinatesToBabylon,
    getBabylonColor,
    getBabylonColor3,
    loadTexture,
    loadModel,
    getHTMLColor,
} from "../../babylon_utils.js";
import {Quaternion} from '../../quaternion.js'
// import {GlowLayer} from "@babylonjs/core/Layers/glowLayer";
// import {HighlightLayer} from "@babylonjs/core/Layers/highlightLayer";
import {shadeColor, shadeColorArray} from "../../../../../../gui/src/lib/helpers.js";


/* === BABYLON SIMPLE BILBO ========================================================================================= */
export class BabylonSimpleBilbo extends BabylonObject {
    constructor(id, scene, payload = {}) {
        super(id, scene, payload);

        const default_config = {
            body_height: 0.16,
            body_width: 0.12,
            body_depth: 0.08,

            battery_height: 0.04,

            color: [1, 0.4, 0.4],
            wheel_diameter: 0.12,
            wheel_width: 0.02,
            scale: 1.0,
            text: '',
        }

        const default_data = {
            position: [0, 0, 0],
            orientation: [1, 0, 0, 0],
        }

        this.static_rotation = Quaternion.fromEulerAngles([0, 0, Math.PI / 2], 'xyz', true);

        this.config = {...default_config, ...this.config};
        this.data = {...default_data, ...this.data};

        this.buildObject();


        this.update({});
    }

    /* === METHODS ================================================================================================== */

    buildObject() {
        const body_opts = {
            width: this.config.body_width,
            height: this.config.body_height,
            depth: this.config.body_depth
        }

        this.bilboRoot = new Mesh("bilboRoot", this.scene); // no geometry, invisible
        this.bilboRoot.isVisible = false;

        const mat = new StandardMaterial('mat', this.scene);

        this.materialBody = new StandardMaterial(this.scene);
        this.materialBody.alpha = 1;
        this.materialBody.diffuseColor = getBabylonColor(this.config.color);

        this.materialWheels = new StandardMaterial(this.scene);
        this.materialWheels.alpha = 1;
        this.materialWheels.diffuseColor = new Color3(0.2, 0.2, 0.2);

        // BILBO body
        this.body = MeshBuilder.CreateBox('box', body_opts, this.scene);

        // Base body material (unchanged)
        this.materialBody = new StandardMaterial(this.scene);
        this.materialBody.alpha = 1;
        this.materialBody.diffuseColor = getBabylonColor(this.config.color);

        // Shaded front-face material (same “shade” as your battery)
        this.materialBodyFront = new StandardMaterial(this.scene);
        this.materialBodyFront.alpha = 1;
        this.materialBodyFront.diffuseColor = getBabylonColor(
            shadeColorArray(this.config.color, -60)
        );

        // MultiMaterial: [0]=base, [1]=front shaded
        const bodyMulti = new MultiMaterial("bodyMulti", this.scene);
        bodyMulti.subMaterials.push(this.materialBody);      // index 0
        bodyMulti.subMaterials.push(this.materialBodyFront); // index 1
        this.body.material = bodyMulti;

        // One submesh per face, assign front to shaded material.
        // Index order for CreateBox is: front, back, right, left, top, bottom.
        this.body.subMeshes = [];
        const totalVerts = this.body.getTotalVertices();
        new SubMesh(1, 0, totalVerts, 0, 6, this.body);  // front  -> shaded
        new SubMesh(0, 0, totalVerts, 6, 6, this.body);  // back   -> base
        new SubMesh(0, 0, totalVerts, 12, 6, this.body);  // right  -> base
        new SubMesh(0, 0, totalVerts, 18, 6, this.body);  // left   -> base
        new SubMesh(0, 0, totalVerts, 24, 6, this.body);  // top    -> base
        new SubMesh(0, 0, totalVerts, 30, 6, this.body);  // bottom -> base

        this.battery = MeshBuilder.CreateBox('battery', {
            width: this.config.body_width,
            depth: this.config.body_depth,
            height: this.config.battery_height,
        }, this.scene);

        this.materialBattery = new StandardMaterial(this.scene);
        this.materialBattery.diffuseColor = getBabylonColor(shadeColorArray(this.config.color, -30));
        this.battery.material = this.materialBattery;

        // BILBO Wheels
        this.wheel1 = MeshBuilder.CreateCylinder("cone", {
            diameterTop: this.config.wheel_diameter, tessellation: 0,
            diameter: this.config.wheel_diameter, height: this.config.wheel_width
        }, this.scene);
        // this.wheel1.position.y = this.config.wheel_diameter/2
        this.wheel1.position.x = this.config.body_width / 2 + this.config.wheel_width / 2 + 0.005
        this.wheel1.rotation.z = 3.14159 / 2;
        this.wheel1.material = this.materialWheels

        this.wheel2 = MeshBuilder.CreateCylinder("cone", {
            diameterTop: this.config.wheel_diameter, tessellation: 0,
            diameter: this.config.wheel_diameter, height: this.config.wheel_width
        }, this.scene);
        // this.wheel2.position.y = this.config.wheel_diameter/2
        this.wheel2.position.x = -(this.config.body_width / 2 + this.config.wheel_width / 2 + 0.005)
        this.wheel2.rotation.z = 3.14159 / 2;
        this.wheel2.material = this.materialWheels


        // Pivot points
        this.body.position.y = this.config.body_height / 2

        this.battery.position.y = -this.config.battery_height / 2

        this.pivotPointBody = new MeshBuilder.CreateSphere("pivotPoint", {diameter: 0.001}, this.scene);
        // this.pivotPointBody.position.y = this.config.wheel_diameter / 2 - this.config.body_width / 4;
        this.pivotPointBody.position.y = this.config.wheel_diameter / 2;
        this.pivotPointBody.rotation.x = 0
        this.body.parent = this.pivotPointBody;

        this.battery.parent = this.pivotPointBody;

        // Create a small sphere to set a new pivot point for the wheels (cylinder)
        this.pivotPointWheels = new MeshBuilder.CreateSphere("pivotPoint", {diameter: 0.001}, this.scene);
        this.pivotPointWheels.position.y = this.config.wheel_diameter / 2
        this.wheel1.parent = this.pivotPointWheels;
        this.wheel2.parent = this.pivotPointWheels;


        this.pivotPointWheels.parent = this.bilboRoot;
        this.pivotPointBody.parent = this.bilboRoot;
        this.bilboRoot.parent = this.root;
        this.scene.shadowGenerator.addShadowCaster(this.bilboRoot, true);
        this.scene.shadowGenerator2.addShadowCaster(this.bilboRoot, true);

        this._tagAllMeshes(this.bilboRoot, true);

    }

    /* -------------------------------------------------------------------------------------------------------------- */

    setColor(color) {
        this.config.color = color;
        this.materialBody.diffuseColor = getBabylonColor(color);
        this.materialBodyFront.diffuseColor = getBabylonColor(shadeColorArray(color, -60));
        this.materialBattery.diffuseColor = getBabylonColor(shadeColorArray(color, -30));
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    delete() {
        this.body.dispose();
        this.wheel1.dispose();
        this.wheel2.dispose();
        this.pivotPointBody.dispose();
        this.pivotPointWheels.dispose();
        this.materialBody.dispose();
        this.materialWheels.dispose();
    }

    dim(state) {
        return undefined;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    highlight(state) {
        this._isHighlighted = state;

        if (state) {
            if (!this._highlightPlane) {
                // --- dynamic texture (ring) ---
                const texSize = 512;
                const dt = new DynamicTexture(`hlTex_${this.id}`, {width: texSize, height: texSize}, this.scene, false);
                const ctx = dt.getContext();
                ctx.clearRect(0, 0, texSize, texSize);

                const c = texSize / 2;
                const thickness = Math.floor(texSize * 0.12); // slightly thicker ring
                ctx.beginPath();
                ctx.arc(c, c, c - 1, 0, Math.PI * 2);                   // outer
                ctx.arc(c, c, c - thickness - 1, 0, Math.PI * 2, true); // inner (cut-out)

                const [r, g, b] = this.config.color || [0.4, 1, 0.4];
                ctx.fillStyle = `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, 0.5)`;
                ctx.fill();
                dt.update();

                // --- material ---
                const mat = new StandardMaterial(`hlMat_${this.id}`, this.scene);
                mat.diffuseTexture = dt;
                mat.diffuseTexture.hasAlpha = true;
                mat.useAlphaFromDiffuseTexture = true;
                mat.transparencyMode = StandardMaterial.MATERIAL_ALPHABLEND;
                mat.backFaceCulling = false;
                mat.specularColor = new Color3(0, 0, 0);
                mat.emissiveColor = getBabylonColor3(this.config.color || [0.4, 1, 0.4]);
                mat.needDepthPrePass = true;

                // --- geometry ---
                const BASE_SIZE = 1; // scale uniformly each frame
                const plane = MeshBuilder.CreatePlane(`hlPlane_${this.id}`, {size: BASE_SIZE}, this.scene);
                plane.material = mat;
                plane.isPickable = false;
                plane.rotation.x = Math.PI / 2; // lay flat on XZ
                this._hlBaseSize = BASE_SIZE;
                this._highlightPlane = plane;
            }

            this._highlightPlane.isVisible = true;

            // Configurable padding and ground height
            const groundY = typeof this.config.groundY === "number" ? this.config.groundY : 0;
            const extraPad = typeof this.config.highlightPad === "number" ? this.config.highlightPad : 1.15; // a bit bigger
            const smallLift = 0.0001;

            // Compute an orientation-independent diameter from the known simple-bilbo footprint
            const computeWorldDiameter = () => {
                // Half-extent along X: body half-width + full wheel thickness (since wheel center is offset by wheel_width/2)
                const halfX_local =
                    this.config.body_width / 2 +
                    this.config.wheel_width +
                    0.005; // the same offset you used when positioning wheels

                // Half-extent along Z: max of body half-depth vs wheel radius
                const halfZ_local = Math.max(
                    this.config.body_depth / 2,
                    this.config.wheel_diameter / 2
                );

                // If you ever scale the whole robot, respect absolute scaling on the root
                const s = this.bilboRoot ? this.bilboRoot.absoluteScaling : new Vector3(1, 1, 1);
                const halfX = Math.abs(halfX_local * s.x);
                const halfZ = Math.abs(halfZ_local * s.z);

                const radiusDiag = Math.hypot(halfX, halfZ) * extraPad;
                return radiusDiag * 2;
            };

            const updateRing = () => {
                if (!this._highlightPlane || this._highlightPlane.isDisposed()) return;

                // Follow bilbo in X/Z — pivotPointWheels and pivotPointBody share the same X/Z
                const anchor = this.pivotPointWheels || this.pivotPointBody || this.bilboRoot;
                const p = anchor.getAbsolutePosition();

                this._highlightPlane.position.x = p.x;
                this._highlightPlane.position.z = p.z;
                this._highlightPlane.position.y = groundY + smallLift;

                // Resize uniformly (independent of yaw/pitch/roll)
                const diameter = computeWorldDiameter();
                const f = diameter / this._hlBaseSize;
                this._highlightPlane.scaling.x = f;
                this._highlightPlane.scaling.y = f;
            };

            // Initial sync + per-frame follow
            updateRing();
            if (!this._highlightObserver) {
                this._highlightObserver = this.scene.onBeforeRenderObservable.add(updateRing);
            }

        } else {
            if (this._highlightObserver) {
                this.scene.onBeforeRenderObservable.remove(this._highlightObserver);
                this._highlightObserver = null;
            }
            if (this._highlightPlane) {
                this._highlightPlane.isVisible = false;
            }
        }
    }

    onMessage(message) {
        return undefined;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setOrientation(orientation) {
        this.orientation = new Quaternion(orientation);
        const quat = this.orientation.multiply(this.static_rotation).babylon();
        this.pivotPointWheels.rotationQuaternion = quat;
        this.pivotPointBody.rotationQuaternion = quat;

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setPosition(position) {
        this.pivotPointWheels.position.x = position[0]
        this.pivotPointWheels.position.z = -position[1]
        this.pivotPointBody.position.x = position[0]
        this.pivotPointBody.position.z = -position[1]
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setState(x, y, theta, psi) {
        this.setPosition([x, y, 0])
        const orientation = Quaternion.fromEulerAngles([psi, theta, 0], 'zyx', true);
        this.setOrientation(orientation);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {

        if (!data) {
            data = {};
        }

        const position = data.position || this.data.position;
        const orientation = data.orientation || this.data.orientation;
        this.setPosition(position);
        this.setOrientation(orientation);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _tagAllMeshes(root = this.bilboRoot, pickable = true) {
        if (!root) return;

        const apply = (m) => {
            m.metadata = m.metadata || {};
            m.metadata.object = this;
            m.isPickable = pickable;
        };

        // Include the root if it's a mesh
        if (root instanceof AbstractMesh) apply(root);

        // Deep-collect all descendant meshes and tag them
        const meshes = root.getChildMeshes(false); // false => include all descendants
        for (const m of meshes) apply(m);
    }
}

/* === BABYLON BILBO REALISTIC ====================================================================================== */
export class BabylonBilboRealistic extends BabylonObject {
    constructor(id, scene, payload = {}) {
        super(id, scene, payload);

        const default_config = {
            model: 'bilbo_detail.babylon',
            static_rotation: Quaternion.fromEulerAngles([Math.PI / 2, -Math.PI / 2, 0], 'xyz', true),
            text: '',
            text_color: [1, 1, 1],
            color: [0.4, 0.4, 0.4],
            scaling: 1,
            model_scaling: 0.001,
            position: [0, 0, 0],
            orientation: [1, 0, 0, 0],
            z_offset: 0.125 / 2,
            dim: false,
        }

        const default_data = {
            position: [0, 0, 0],
            orientation: [1, 0, 0, 0],
        }


        this.config = {...default_config, ...this.config};
        this.data = {...default_data, ...this.data};

        this.static_rotation_quaternion = new Quaternion(this.config.static_rotation);

        // Load the mesh
        this._ready = SceneLoader
            .ImportMeshAsync("", "./", loadModel(this.config.model), this.scene)
            .then(({meshes}) => {
                this.onMeshLoaded(meshes, /*…*/)
                return this;            // resolve with `this` so callers can chain
            });

        // Now we wait for the mesh to be loaded. The rest of the configuration resumes in onMeshLoaded()

    }

    /* === METHODS ================================================================================================== */
    buildObject() {

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onMeshLoaded(newMeshes, particleSystems, skeletons) {
        // Mesh
        this.mesh = newMeshes[0];

        newMeshes.forEach(m => {
            m.metadata = m.metadata || {};
            m.metadata.object = this;
            m.isPickable = true;
        });

        this.mesh.scaling.x = this.config.scaling * this.config.model_scaling;
        this.mesh.scaling.y = this.config.scaling * this.config.model_scaling;
        this.mesh.scaling.z = -this.config.scaling * this.config.model_scaling;

        // Material
        this.material = new StandardMaterial("material", this.scene);
        // if (this.config.color) {
        //     this.material.diffuseColor = getBabylonColor3(this.config.color);
        //     this.material.specularColor = getBabylonColor3([0.3, 0.3, 0.3]);
        // }
        this.mesh.material = this.material;

        if (this.config.text) {
            this.addText();
        }

        // this.dim(this.config.dim);

        this._isHighlighted = false;
        this.highlight(this._isHighlighted);

        // Set Position + Orientation
        this.setOrientation(this.config.orientation);
        this.setPosition(this.config.position);

        this.mesh.parent = this.root;
        this.scene.shadowGenerator.addShadowCaster(this.mesh);
        // this.scene.shadowGenerator2.addShadowCaster(this.mesh);

        this.mesh.isPickable = true;

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    addText() {
        //
        // Create a dynamic texture with a larger size.
        const dynamicTexture = new DynamicTexture("DynamicTexture", {width: 256, height: 256}, this.scene);
        const ctx = dynamicTexture.getContext();
        ctx.clearRect(0, 0, 256, 256);
        //
        // Draw a circle
        ctx.beginPath();
        ctx.arc(128, 128, 120, 0, Math.PI * 2, false); // Center (128,128) with a radius of 120.
        ctx.fillStyle = 'transparent';
        ctx.fill();
        ctx.lineWidth = 20;
        ctx.strokeStyle = getHTMLColor(this.config.text_color);
        ctx.stroke();
        //
        // The text to display.
        const text = this.config.text; // Change this to any text.

        // Define the maximum allowed text width (in pixels) within the circle.
        const maxTextWidth = 200;
        let fontSize = 250; // Start with a large font size.
        let font = `bold ${fontSize}px Arial`;

        // Set the context font and measure the text width.
        ctx.font = font;
        let measuredWidth = ctx.measureText(text).width;

        // Reduce the font size until the text fits within the maxTextWidth.
        while (measuredWidth > maxTextWidth && fontSize > 10) {
            fontSize -= 10;
            font = `bold ${fontSize}px Arial`;
            ctx.font = font;
            measuredWidth = ctx.measureText(text).width;
        }

        // Compute a y-offset to vertically center the text in the circle.
        // This calculation can be adjusted based on your design needs.
        const yOffset = 128 + fontSize / 3;

        // Draw the text on top of the circle without clearing the canvas.
        // Passing null as clearColor ensures our circle remains.
        const brightnessFactor = 1;
        const [r, g, b] = this.config.text_color;
        const textColor = `rgb(${Math.floor(r * 255 * brightnessFactor)}, ${Math.floor(g * 255 * brightnessFactor)}, ${Math.floor(b * 255 * brightnessFactor)})`;


        dynamicTexture.drawText(text, null, yOffset, font, textColor, null, true);
        dynamicTexture.update();

        // Create a new material using the dynamic texture.
        const textMaterial = new StandardMaterial("textMaterial", this.scene);
        textMaterial.diffuseTexture = dynamicTexture;
        textMaterial.diffuseTexture.hasAlpha = true;
        textMaterial.useAlphaFromDiffuseTexture = true;
        // textMaterial.disableLighting = true;
        textMaterial.backFaceCulling = false;

        textMaterial.emissiveColor = getBabylonColor3([0.01, 0.01, 0.01]);

        // Create an intermediate transform node to counteract the parent's negative scaling.
        this.textHolder = new TransformNode("textHolder", this.scene);
        this.textHolder.parent = this.mesh;
        this.textHolder.position = new Vector3(0.0325, 0.05, 0);
        this.textHolder.scaling = new Vector3(1, 1, -1);
        //
        // Create the plane that will display the text.
        this.textPlane = MeshBuilder.CreatePlane("textPlane", {width: 0.1, height: 0.1}, this.scene);
        this.textPlane.material = textMaterial;
        this.textPlane.parent = this.textHolder;
        this.textPlane.rotation = new Vector3(0, 1.57, 0);

        this.textPlane.metadata = this.textPlane.metadata || {};
        this.textPlane.metadata.object = this;
        this.textPlane.isPickable = true;
        //
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setColor(color) {
        this.config.color = color;
        if (this.material) {
            this.material.diffuseColor = getBabylonColor3(color);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onMessage(message) {
        return undefined;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setOrientation(orientation) {
        this.orientation = new Quaternion(orientation);
        this.mesh.rotationQuaternion = this.orientation.multiply(this.static_rotation_quaternion).babylon();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setPosition(position) {
        let coords;

        if (Array.isArray(position)) {
            coords = position;
        } else if (typeof position === 'object' && position !== null &&
            'x' in position && 'y' in position && 'z' in position) {
            coords = [position.x, position.y, position.z];
        } else {
            throw new Error('Invalid position format. Expected [x, y, z] or {x, y, z}.');
        }

        this.position = coords;
        this.mesh.position = coordinatesToBabylon([this.position[0], this.position[1], this.config.scaling * this.config.z_offset]);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setState(x, y, theta, psi) {
        this.setPosition([x, y, 0])
        const orientation = Quaternion.fromEulerAngles([psi, theta, 0], 'zyx', true);
        this.setOrientation(orientation);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
        const position = data.position || this.data.position;
        const orientation = data.orientation || this.data.orientation;
        this.setPosition(position);
        this.setOrientation(orientation);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onLoaded() {
        return this._ready;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setVisibility(visible) {
        super.setVisibility(visible);

        if (this.textHolder) {
            this.textHolder.isVisible = visible;
        }
        if (this.textPlane) {
            this.textPlane.isVisible = visible;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    highlight(state) {
        this._isHighlighted = state;

        if (state) {
            if (!this._highlightPlane) {
                // --- dynamic texture (donut) ---
                const texSize = 512;
                const dt = new DynamicTexture(`hlTex_${this.id}`, {width: texSize, height: texSize}, this.scene, false);
                const ctx = dt.getContext();
                ctx.clearRect(0, 0, texSize, texSize);

                const c = texSize / 2;
                const thickness = Math.floor(texSize * 0.12); // slightly thicker ring
                ctx.beginPath();
                ctx.arc(c, c, c - 1, 0, Math.PI * 2);                 // outer
                ctx.arc(c, c, c - thickness - 1, 0, Math.PI * 2, true); // inner cut-out

                const [r, g, b] = this.config.color || [0.4, 1, 0.4];
                ctx.fillStyle = `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, 0.5)`;
                ctx.fill();
                dt.update();

                // --- material ---
                const mat = new StandardMaterial(`hlMat_${this.id}`, this.scene);
                mat.diffuseTexture = dt;
                mat.diffuseTexture.hasAlpha = true;
                mat.useAlphaFromDiffuseTexture = true;
                mat.transparencyMode = StandardMaterial.MATERIAL_ALPHABLEND;
                mat.backFaceCulling = false;
                mat.specularColor = new Color3(0, 0, 0);
                mat.emissiveColor = getBabylonColor3(this.config.color || [0.4, 1, 0.4]);
                mat.needDepthPrePass = true;

                // --- geometry ---
                const BASE_SIZE = 1; // we'll scale uniformly each frame
                const plane = MeshBuilder.CreatePlane(`hlPlane_${this.id}`, {size: BASE_SIZE}, this.scene);
                plane.material = mat;
                plane.isPickable = false;
                plane.rotation.x = Math.PI / 2; // lay flat on XZ
                this._hlBaseSize = BASE_SIZE;
                this._highlightPlane = plane;
            }

            this._highlightPlane.isVisible = true;

            // Ground height (default 0). Keeps ring on the floor regardless of robot Y.
            const groundY = typeof this.config.groundY === "number" ? this.config.groundY : 0;
            const extraPad = typeof this.config.highlightPad === "number" ? this.config.highlightPad : 1.15; // a bit bigger
            const smallLift = 0.0001; // avoid z-fighting with ground

            // Compute a diameter independent of orientation using local bounds + absolute scale
            const computeWorldDiameter = () => {
                const bi = this.mesh.getBoundingInfo();
                const ext = bi.boundingBox.extendSize;   // local half-sizes
                const s = this.mesh.absoluteScaling;     // positive world scale
                const halfW = Math.abs(ext.x * s.x);
                const halfD = Math.abs(ext.z * s.z);

                // Use diagonal so the ring slightly over-covers the footprint
                const radiusXZ = Math.hypot(halfW, halfD) * extraPad;
                return radiusXZ * 2;
            };

            const updateRing = () => {
                if (!this.mesh || this.mesh.isDisposed() || !this._highlightPlane || this._highlightPlane.isDisposed()) return;

                // Follow robot in X/Z using absolute position (handles parenting)
                const p = this.mesh.getAbsolutePosition();
                this._highlightPlane.position.x = p.x;
                this._highlightPlane.position.z = p.z;
                this._highlightPlane.position.y = groundY + smallLift;

                // Resize uniformly based on current scale (not rotation)
                const diameter = computeWorldDiameter();
                const f = diameter / this._hlBaseSize;
                this._highlightPlane.scaling.x = f;
                this._highlightPlane.scaling.y = f;
            };

            // Initial sync + per-frame follow
            updateRing();
            if (!this._highlightObserver) {
                this._highlightObserver = this.scene.onBeforeRenderObservable.add(updateRing);
            }
        } else {
            if (this._highlightObserver) {
                this.scene.onBeforeRenderObservable.remove(this._highlightObserver);
                this._highlightObserver = null;
            }
            if (this._highlightPlane) {
                this._highlightPlane.isVisible = false;
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    dim(state) {
        const alpha = state ? 0.5 : 1.0;

        // Gather the root mesh plus any imported sub-meshes
        const parts = [this.mesh];
        if (this.mesh.getChildMeshes) {
            parts.push(...this.mesh.getChildMeshes());
        }

        for (const m of parts) {
            const mat = m.material;
            if (!mat || !(mat instanceof StandardMaterial)) {
                continue;
            }

            mat.alpha = alpha;

            // If this material is using a diffuse-texture alpha (i.e. your text)
            if (mat.useAlphaFromDiffuseTexture && mat.diffuseTexture) {
                // always leave in alpha-blend so its mask shows
                mat.transparencyMode = StandardMaterial.MATERIAL_ALPHABLEND;
                mat.backFaceCulling = false;
                mat.needDepthPrePass = state;
            } else {
                // robot body parts
                if (alpha < 1) {
                    mat.transparencyMode = StandardMaterial.MATERIAL_ALPHABLEND;
                    mat.backFaceCulling = false;
                    mat.needDepthPrePass = true;
                } else {
                    mat.transparencyMode = StandardMaterial.MATERIAL_OPAQUE;
                    mat.backFaceCulling = true;
                    mat.needDepthPrePass = false;
                }
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    delete() {
        this.mesh.dispose();
    }
}

/* === BABYLON BILBO ================================================================================================ */
export class BabylonBilbo extends BabylonObject {
    loaded = false;

    constructor(id, scene, payload = {}) {
        super(id, scene, payload);

        const default_config = {
            model: 'bilbo_generic.babylon',
            static_rotation: Quaternion.fromEulerAngles([0, 0, 0], 'xyz', true),
            text: '2',
            text_color: [1, 1, 1],
            color: [0.4, 1, 0.4],
            scaling: 1,
            model_scaling: 1,
            z_offset: 0.125 / 2,
            dim: false,
        }

        const default_data = {
            x: 0,
            y: 0,
            theta: 0,
            psi: 0,
        }


        this.config = {...default_config, ...this.config};
        this.data = {...default_data, ...this.data};

        this.static_rotation_quaternion = new Quaternion(this.config.static_rotation);


        this.buildObject();
        this.onLoaded().then(() => {
            this.setState(this.data.x, this.data.y, this.data.theta, this.data.psi);
        })
    }

    /* === METHODS ================================================================================================== */
    buildObject() {
        // Load the mesh
        this._ready = SceneLoader
            .ImportMeshAsync("", "./", loadModel(this.config.model), this.scene)
            .then(({meshes}) => {
                this.onMeshLoaded(meshes, /*…*/)
                return this;            // resolve with `this` so callers can chain
            });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onMeshLoaded(newMeshes, particleSystems, skeletons) {
        // Mesh
        this.mesh = newMeshes[0];

        newMeshes.forEach(m => {
            m.metadata = m.metadata || {};
            m.metadata.object = this;
            m.isPickable = true;
        });

        this.mesh.scaling.x = this.config.scaling * this.config.model_scaling;
        this.mesh.scaling.y = this.config.scaling * this.config.model_scaling;
        this.mesh.scaling.z = -this.config.scaling * this.config.model_scaling;

        // Material
        this.material = new StandardMaterial("material", this.scene);
        if (this.config.color) {
            this.material.diffuseColor = getBabylonColor3(this.config.color);
            this.material.specularColor = getBabylonColor3([0.3, 0.3, 0.3]);
        }
        this.mesh.material = this.material;

        if (this.config.text) {
            this.addText();
        }

        // this.dim(this.config.dim);

        this._isHighlighted = false;
        this.highlight(this._isHighlighted);


        this.mesh.parent = this.root;
        this.scene.shadowGenerator.addShadowCaster(this.mesh);
        // this.scene.shadowGenerator2.addShadowCaster(this.mesh);

        this.mesh.isPickable = true;

        // Set Position + Orientation
        this.setState(this.data.x, this.data.y, this.data.theta, this.data.psi);
        this.loaded = true;

    }


    /* -------------------------------------------------------------------------------------------------------------- */
    addText() {
        // Dynamic texture (keep your original resolution and sizes)
        const dynamicTexture = new DynamicTexture("DynamicTexture", {width: 256, height: 256}, this.scene);
        const ctx = dynamicTexture.getContext();
        ctx.clearRect(0, 0, 256, 256);

        // Draw circle (same geometry as before)
        ctx.beginPath();
        ctx.arc(128, 128, 120, 0, Math.PI * 2, false);
        ctx.fillStyle = 'transparent';
        ctx.fill();
        ctx.lineWidth = 20;
        ctx.strokeStyle = getHTMLColor(this.config.text_color);
        ctx.stroke();


        // Fit text exactly like before
        const text = this.config.text;
        const maxTextWidth = 200;
        let fontSize = 250;
        let font = `bold ${fontSize}px Arial`;

        ctx.font = font;
        let measuredWidth = ctx.measureText(text).width;
        while (measuredWidth > maxTextWidth && fontSize > 10) {
            fontSize -= 10;
            font = `bold ${fontSize}px Arial`;
            ctx.font = font;
            measuredWidth = ctx.measureText(text).width;
        }

        const yOffset = 128 + fontSize / 3;
        const brightnessFactor = 1;
        const [r, g, b] = this.config.text_color;
        const textColor = `rgb(${Math.floor(r * 255 * brightnessFactor)}, ${Math.floor(g * 255 * brightnessFactor)}, ${Math.floor(b * 255 * brightnessFactor)})`;

        // Use Babylon's drawText to preserve your original look
        dynamicTexture.drawText(text, null, yOffset, font, textColor, null, true);
        dynamicTexture.update();


        // --- Material: PBR with proper two-sided lighting (no glow) ---
        const textMaterial = new PBRMaterial(`textMaterial_${this.id}`, this.scene);
        textMaterial.albedoTexture = dynamicTexture;
        textMaterial.albedoTexture.hasAlpha = true;
        textMaterial.opacityTexture = dynamicTexture;
        textMaterial.useAlphaFromAlbedoTexture = true;

        // Keep it Lambert-ish and stable
        textMaterial.metallic = 0;
        textMaterial.roughness = 1;
        textMaterial.environmentIntensity = 0;     // don’t pick up reflections
        textMaterial.backFaceCulling = true;       // rely on the geometry to be double-sided
        textMaterial.twoSidedLighting = true;      // correct lighting when the back side is visible
        textMaterial.unlit = false;                // it should react to light (no emissive "glow")
        textMaterial.emissiveColor = new Color3(0, 0, 0); // explicitly no baseline glow

        // Tone down how strongly direct lights modulate the texture (optional, subtle)
        // If you still find it too contrasty, you can uncomment the next line and try 0.8–0.9
        // (textMaterial as any).albedoTexture.level = 0.9;

        // --- Holder to counter root's negative Z (as in your original) ---
        if (this.textHolder) this.textHolder.dispose();
        if (this.textPlane) this.textPlane.dispose();

        this.textHolder = new TransformNode(`textHolder_${this.id}`, this.scene);
        this.textHolder.parent = this.mesh;
        this.textHolder.position = new Vector3(0.0325, 0.05, 0);
        this.textHolder.scaling = new Vector3(1, 1, -1);

        // --- Plane: make the geometry itself double-sided so each side has correct normals ---
        this.textPlane = MeshBuilder.CreatePlane(
            `textPlane_${this.id}`,
            {width: 0.1, height: 0.1, sideOrientation: Mesh.DOUBLESIDE},
            this.scene
        );
        this.textPlane.material = textMaterial;
        this.textPlane.parent = this.textHolder;
        this.textPlane.rotation = new Vector3(0, 1.57, 0);

        // Don’t receive/cast shadows; it’s a label
        this.textPlane.receiveShadows = false;
        this.textPlane.isPickable = true;

        this.textPlane.metadata = this.textPlane.metadata || {};
        this.textPlane.metadata.object = this;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onMessage(message) {
        return undefined;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setOrientation(orientation) {
        this.orientation = new Quaternion(orientation);
        if (this.loaded) {
            this.mesh.rotationQuaternion = this.orientation.multiply(this.static_rotation_quaternion).babylon();
        }

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setPosition(position) {
        let coords;

        if (Array.isArray(position)) {
            coords = position;
        } else if (typeof position === 'object' && position !== null &&
            'x' in position && 'y' in position && 'z' in position) {
            coords = [position.x, position.y, position.z];
        } else {
            throw new Error('Invalid position format. Expected [x, y, z] or {x, y, z}.');
        }

        this.position = coords;
        if (this.loaded) {
            this.mesh.position = coordinatesToBabylon([this.position[0], this.position[1], this.config.scaling * this.config.z_offset]);
        }

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setState(x, y, theta, psi) {
        this.setPosition([x, y, 0])
        const orientation = Quaternion.fromEulerAngles([psi, theta, 0], 'zyx', true);
        this.setOrientation(orientation);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
        this.setState(data.x, data.y, data.theta, data.psi);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setColor(color) {
        this.config.color = color;
        if (this.material) {
            this.material.diffuseColor = getBabylonColor3(color);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onLoaded() {
        return this._ready;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setVisibility(visible) {
        super.setVisibility(visible);

        if (this.textHolder) {
            this.textHolder.isVisible = visible;
        }
        if (this.textPlane) {
            this.textPlane.isVisible = visible;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    highlight(state) {
        this._isHighlighted = state;

        if (state) {
            if (!this._highlightPlane) {
                // --- dynamic texture (donut) ---
                const texSize = 512;
                const dt = new DynamicTexture(`hlTex_${this.id}`, {width: texSize, height: texSize}, this.scene, false);
                const ctx = dt.getContext();
                ctx.clearRect(0, 0, texSize, texSize);

                const c = texSize / 2;
                const thickness = Math.floor(texSize * 0.12); // slightly thicker ring
                ctx.beginPath();
                ctx.arc(c, c, c - 1, 0, Math.PI * 2);                 // outer
                ctx.arc(c, c, c - thickness - 1, 0, Math.PI * 2, true); // inner cut-out

                const [r, g, b] = this.config.color || [0.4, 1, 0.4];
                ctx.fillStyle = `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, 0.5)`;
                ctx.fill();
                dt.update();

                // --- material ---
                const mat = new StandardMaterial(`hlMat_${this.id}`, this.scene);
                mat.diffuseTexture = dt;
                mat.diffuseTexture.hasAlpha = true;
                mat.useAlphaFromDiffuseTexture = true;
                mat.transparencyMode = StandardMaterial.MATERIAL_ALPHABLEND;
                mat.backFaceCulling = false;
                mat.specularColor = new Color3(0, 0, 0);
                mat.emissiveColor = getBabylonColor3(this.config.color || [0.4, 1, 0.4]);
                mat.needDepthPrePass = true;

                // --- geometry ---
                const BASE_SIZE = 1; // we'll scale uniformly each frame
                const plane = MeshBuilder.CreatePlane(`hlPlane_${this.id}`, {size: BASE_SIZE}, this.scene);
                plane.material = mat;
                plane.isPickable = false;
                plane.rotation.x = Math.PI / 2; // lay flat on XZ
                this._hlBaseSize = BASE_SIZE;
                this._highlightPlane = plane;
            }

            this._highlightPlane.isVisible = true;

            // Ground height (default 0). Keeps ring on the floor regardless of robot Y.
            const groundY = typeof this.config.groundY === "number" ? this.config.groundY : 0;
            const extraPad = typeof this.config.highlightPad === "number" ? this.config.highlightPad : 1.15; // a bit bigger
            const smallLift = 0.0001; // avoid z-fighting with ground

            // Compute a diameter independent of orientation using local bounds + absolute scale
            const computeWorldDiameter = () => {
                const bi = this.mesh.getBoundingInfo();
                const ext = bi.boundingBox.extendSize;   // local half-sizes
                const s = this.mesh.absoluteScaling;     // positive world scale
                const halfW = Math.abs(ext.x * s.x);
                const halfD = Math.abs(ext.z * s.z);

                // Use diagonal so the ring slightly over-covers the footprint
                const radiusXZ = Math.hypot(halfW, halfD) * extraPad;
                return radiusXZ * 2;
            };

            const updateRing = () => {
                if (!this.mesh || this.mesh.isDisposed() || !this._highlightPlane || this._highlightPlane.isDisposed()) return;

                // Follow robot in X/Z using absolute position (handles parenting)
                const p = this.mesh.getAbsolutePosition();
                this._highlightPlane.position.x = p.x;
                this._highlightPlane.position.z = p.z;
                this._highlightPlane.position.y = groundY + smallLift;

                // Resize uniformly based on current scale (not rotation)
                const diameter = computeWorldDiameter();
                const f = diameter / this._hlBaseSize;
                this._highlightPlane.scaling.x = f;
                this._highlightPlane.scaling.y = f;
            };

            // Initial sync + per-frame follow
            updateRing();
            if (!this._highlightObserver) {
                this._highlightObserver = this.scene.onBeforeRenderObservable.add(updateRing);
            }
        } else {
            if (this._highlightObserver) {
                this.scene.onBeforeRenderObservable.remove(this._highlightObserver);
                this._highlightObserver = null;
            }
            if (this._highlightPlane) {
                this._highlightPlane.isVisible = false;
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    dim(state) {
        const alpha = state ? 0.5 : 1.0;

        // Gather the root mesh plus any imported sub-meshes
        const parts = [this.mesh];
        if (this.mesh.getChildMeshes) {
            parts.push(...this.mesh.getChildMeshes());
        }

        for (const m of parts) {
            const mat = m.material;
            if (!mat || !(mat instanceof StandardMaterial)) {
                continue;
            }

            mat.alpha = alpha;

            // If this material is using a diffuse-texture alpha (i.e. your text)
            if (mat.useAlphaFromDiffuseTexture && mat.diffuseTexture) {
                // always leave in alpha-blend so its mask shows
                mat.transparencyMode = StandardMaterial.MATERIAL_ALPHABLEND;
                mat.backFaceCulling = false;
                mat.needDepthPrePass = state;
            } else {
                // robot body parts
                if (alpha < 1) {
                    mat.transparencyMode = StandardMaterial.MATERIAL_ALPHABLEND;
                    mat.backFaceCulling = false;
                    mat.needDepthPrePass = true;
                } else {
                    mat.transparencyMode = StandardMaterial.MATERIAL_OPAQUE;
                    mat.backFaceCulling = true;
                    mat.needDepthPrePass = false;
                }
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    delete() {
        this.mesh.dispose();
    }
}