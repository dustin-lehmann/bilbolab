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

export class BabylonFrodo extends BabylonObject {
    loaded = false;

    static _fovLayerCounter = 0;           // global counter across all instances
    _fovLayer = 0;                          // this instance's layer index

    constructor(id, scene, payload = {}) {
        super(id, scene, payload);

        const default_config = {
            model: "frodo_animation.babylon",
            // stays as a static correction applied to the model only (NOT the dynamic pose)
            static_rotation: Quaternion.fromEulerAngles([0, 0, Math.PI], "xyz", true),

            text: "3",
            text_color: [1, 1, 1],
            color: [1, 0.3, 1],
            scaling: 1,        // overall robot scale
            model_scaling: 1,  // extra per-model scale
            z_offset: 0,

            // FOV look
            vision_radius: 1.5,
            fov: 120,
            fovHeadingOffsetDeg: 90,
            fovAlpha: 0.3,

            // Occlusion sampling
            occlusionEnabled: true,
            raysPerDegree: 1 / 2,
            throttleHz: 0,                // 0 = every frame
            rayHeights: [0.05, 0.12, 0.25],
            useBlocksVisionOnly: false,
            blockerMeshes: null,

            ignoredBlockerNameRegex: /(ground|floor|plane|terrain|axis|gizmo)/i,
            ignoredBlockerMeshes: null,

            segmentJumpThresholdFrac: 2,
            maxRefinePasses: 2,
            minAngularStepDeg: 2,

            distanceSmoothing: 0,

            groundY: 0,
            highlightPad: 1.15,

            // local transform for label
            text_local_position: [0, 0.056, 0],
            text_local_rotation: [1.57, 0, -1.57],
            text_local_scale: [0.8, 0.8, 0.8],

            text_plane_size: 0.10,
            text_plane_rotation: [0, 0, 0],

            // Debug
            debugFov: {
                enabled: false,
                logEveryNFrames: 30,
                drawRays: true,
                drawHits: true,
                opaque: false,
                fastCheck: true,
            },
        };

        const default_data = {x: 0, y: 0, psi: 0};

        this.config = {...this.config, ...default_config, ...payload.config};
        this.config.debugFov = {...default_config.debugFov, ...(this.config.debugFov || {})};
        this.data = {...default_data, ...this.data};

        this._fovLayer = BabylonFrodo._fovLayerCounter++;

        this._dbg = {frame: 0, lines: [], hits: [], warnedOnce: false};
        this._fovMeshes = [];
        this._prevDistByAngleKey = new Map();

        // model root (child of this.root) that carries model-only tweaks (scale, static rotation, flip)
        this.modelRoot = new TransformNode(`robotModel_${this.id}`, this.scene);
        this.modelRoot.parent = this.root;

        this.buildObject();
        // this.onLoaded().then(() => {
        //     this.setState(this.data.x, this.data.y, this.data.psi);
        // });
    }

    /* === LOAD =================================================================================== */
    buildObject() {
        this._ready = SceneLoader
            .ImportMeshAsync("", "./", loadModel(this.config.model), this.scene)
            .then(({meshes}) => {
                this.onMeshLoaded(meshes);
                return this;
            });
    }

    onMeshLoaded(newMeshes) {
        // Keep a reference to the "body" for material tweaks
        this.body_mesh = newMeshes[3];

        // Parent all imported meshes under modelRoot
        for (const m of newMeshes) {
            m.parent = this.modelRoot;
            m.metadata = m.metadata || {};
            m.metadata.object = this;
            m.isPickable = true;
        }

        // Apply model-only transforms on modelRoot:
        //  - overall scale * model scale
        //  - Z flip (negative Z) as before
        const s = this.config.scaling * this.config.model_scaling;
        this.modelRoot.scaling.set(s, s, -s);


        // Material on body
        this.material = new StandardMaterial(`material_${this.id}`, this.scene);
        if (this.config.color) {
            this.material.diffuseColor = getBabylonColor3(this.config.color);
            this.material.specularColor = getBabylonColor3([0.3, 0.3, 0.3]);
        }
        this.body_mesh.material = this.material;

        if (this.config.text) this.addText();

        // Make meshes cast shadows (the TransformNode itself can't)
        if (this.scene.shadowGenerator?.addShadowCaster) {
            for (const m of newMeshes) {
                if (m instanceof Mesh) this.scene.shadowGenerator.addShadowCaster(m);
            }
        }


        if (this.config.occlusionEnabled) {
            this._initVisibilityFov();
        } else {
            this._createSimpleDiscFov();
        }

        this._isHighlighted = false;
        this.highlight(this._isHighlighted);
        this.onBuilt();
        this.loaded = true;
    }

    /* === SIMPLE DISC (fallback) ================================================================ */
    _createSimpleDiscFov() {
        const radius = this.config.vision_radius * this.config.scaling;
        const fovAngleRad = this.config.fov * Math.PI / 180;
        const arcFraction = this.config.fov / 360;

        const fovMaterial = new StandardMaterial(`fovMat_${this.id}`, this.scene);
        const c = getBabylonColor3(this.config.color);
        fovMaterial.diffuseColor = c;
        fovMaterial.emissiveColor = c.scale(0.8);
        fovMaterial.specularColor = c.scale(0.1);
        fovMaterial.alpha = this.config.fovAlpha;
        fovMaterial.backFaceCulling = false;
        fovMaterial.needDepthPrePass = true;
        fovMaterial.forceDepthWrite = false;
//         mat.needDepthPrePass = true;     // helps with correct depth testing for translucency
// mat.forceDepthWrite = false;

        this.fovDisc = MeshBuilder.CreateDisc(
            `fovDisc_${this.id}`,
            {radius, tessellation: 64, arc: arcFraction},
            this.scene
        );
        this.fovDisc.material = fovMaterial;
        this.fovDisc.parent = this.modelRoot;
        this.fovDisc.position = new Vector3(0, this._getFovLift(), 0);
        this.fovDisc.rotation = new Vector3(Math.PI / 2, fovAngleRad / 2, 0);
        this.fovDisc.renderingGroupId = 0;
    }

    /* === OCCLUSION-AWARE FOV =================================================================== */

    // Dynamic-only forward (root orientation), excludes static model fix
    _getLogicalForward() {
        const q = this.orientation?.babylon();
        if (!q) return new Vector3(0, 0, 1);

        let f;
        if (Vector3.TransformNormalByQuaternion) {
            f = Vector3.TransformNormalByQuaternion(Vector3.Forward(), q);
        } else if (Vector3.TransformCoordinatesByQuaternion) {
            f = Vector3.TransformCoordinatesByQuaternion(Vector3.Forward(), q).subtract(Vector3.Zero());
        } else {
            const m = new Matrix();
            q.toRotationMatrix(m);
            f = Vector3.TransformNormal(Vector3.Forward(), m);
        }
        f.y = 0;
        const len2 = f.lengthSquared();
        return len2 > 1e-12 ? f.scale(1 / Math.sqrt(len2)) : new Vector3(0, 0, 1);
    }

    _initVisibilityFov() {
        const throttleHz = Math.max(0, this.config.throttleHz | 0);
        const update = () => {
            if (!this.modelRoot || this.modelRoot.isDisposed()) return;
            const sweep = this._sampleVisibilityPointsAdaptive();
            if (!sweep || !sweep.points?.length) {
                this._clearFovMeshes();
                return;
            }
            this._buildOrUpdateFovMeshes(sweep.points, sweep.distances);
        };

        update();

        if (throttleHz <= 0) {
            this._fovObserver = this.scene.onBeforeRenderObservable.add(update);
        } else {
            const interval = 1 / throttleHz;
            let acc = 0;
            this._fovObserver = this.scene.onBeforeRenderObservable.add(() => {
                acc += this.scene.getEngine().getDeltaTime() / 1000;
                if (acc >= interval) {
                    acc = 0;
                    update();
                }
            });
        }
    }

    _sampleVisibilityPointsAdaptive() {
        const cfg = this.config;
        const dbg = cfg.debugFov || {};
        const radius = cfg.vision_radius * cfg.scaling;
        const fovDeg = cfg.fov;
        const baseSamples = Math.max(8, Math.floor(fovDeg * cfg.raysPerDegree));
        const half = fovDeg * 0.5;
        const jump = Math.max(0.01, (cfg.segmentJumpThresholdFrac ?? 0.22) * radius);

        const robotPos = this.modelRoot.getAbsolutePosition().clone();
        const headingOffset = (cfg.fovHeadingOffsetDeg || 0) * Math.PI / 180;

        let forwardWorld = this._getLogicalForward();
        if (headingOffset) {
            const offMat = Matrix.RotationYawPitchRoll(headingOffset, 0, 0);
            forwardWorld = Vector3.TransformNormal(forwardWorld, offMat).normalize();
        }

        const anglesDeg = [];
        for (let i = 0; i <= baseSamples; i++) anglesDeg.push(-half + (i / baseSamples) * fovDeg);

        const castSweep = (angles) => {
            const originBaseY = (typeof cfg.groundY === "number" ? cfg.groundY : 0);
            const rayHeights = Array.isArray(cfg.rayHeights) && cfg.rayHeights.length ? cfg.rayHeights : [0.01];

            const pts = new Array(angles.length);
            const dists = new Array(angles.length);

            const rayLines = [];
            const hitDebugPoints = [];

            for (let ia = 0; ia < angles.length; ia++) {
                const angleDeg = angles[ia];
                const angleRad = angleDeg * Math.PI / 180;

                const yawMat = Matrix.RotationYawPitchRoll(angleRad, 0, 0);
                let dir = Vector3.TransformNormal(forwardWorld, yawMat);
                dir.y = 0;
                if (dir.lengthSquared() < 1e-8) dir = new Vector3(Math.cos(angleRad), 0, Math.sin(angleRad));
                dir.normalize();

                let bestDist = radius;
                let bestPoint = null;
                let usedHit = false;

                for (let h = 0; h < rayHeights.length; h++) {
                    const origin = new Vector3(robotPos.x, originBaseY + rayHeights[h], robotPos.z);
                    const ray = new Ray(origin, dir, radius);
                    const pick = this.scene.pickWithRay(
                        ray,
                        (m) => this._blockerPredicate(m),
                        /*fastCheck*/ false
                    );

                    if (pick && pick.hit && pick.pickedPoint) {
                        const dist = typeof pick.distance === "number" ? pick.distance : Vector3.Distance(origin, pick.pickedPoint);
                        if (dist < bestDist) {
                            bestDist = dist;
                            bestPoint = pick.pickedPoint.clone();
                            usedHit = true;
                        }
                    }
                }

                if (!bestPoint) {
                    const origin = new Vector3(robotPos.x, originBaseY + rayHeights[0], robotPos.z);
                    bestPoint = origin.add(dir.scale(radius));
                    bestDist = radius;
                }

                const displayY = originBaseY + this._getFovLift();
                pts[ia] = new Vector3(bestPoint.x, displayY, bestPoint.z);
                dists[ia] = bestDist;

                if (dbg.enabled && dbg.drawRays) {
                    const origin = new Vector3(robotPos.x, originBaseY + rayHeights[0], robotPos.z);
                    rayLines.push([origin.clone(), bestPoint.clone()]);
                }
                if (dbg.enabled && dbg.drawHits && usedHit) hitDebugPoints.push(bestPoint.clone());
            }

            if (dbg.enabled) {
                this._updateDebugLines(rayLines);
                this._updateDebugHitSpheres(hitDebugPoints);
            } else {
                this._clearDebugLines();
                this._clearDebugHitSpheres();
            }

            return {angles, pts, dists};
        };

        let {angles, pts, dists} = castSweep(anglesDeg);

        const refineOnce = () => {
            const inserts = [];
            for (let i = 1; i < dists.length; i++) {
                if (Math.abs(dists[i] - dists[i - 1]) > jump) {
                    const mid = 0.5 * (angles[i] + angles[i - 1]);
                    if (Math.abs(angles[i] - angles[i - 1]) >= (this.config.minAngularStepDeg ?? 0.75)) {
                        inserts.push({i, mid});
                    }
                }
            }
            if (!inserts.length) return false;

            const nextAngles = [];
            let cursor = 0;
            for (const ins of inserts) {
                while (cursor < ins.i) nextAngles.push(angles[cursor++]);
                nextAngles.push(ins.mid);
            }
            while (cursor < angles.length) nextAngles.push(angles[cursor++]);

            const res = castSweep(nextAngles);
            angles = res.angles;
            pts = res.pts;
            dists = res.dists;
            return true;
        };

        const passes = Math.max(0, this.config.maxRefinePasses | 0);
        for (let p = 0; p < passes; p++) {
            if (!refineOnce()) break;
        }

        const smoothedDists = [];
        const k = Math.max(0, Math.min(1, this.config.distanceSmoothing ?? 0));
        if (k > 0) {
            const newMap = new Map();
            for (let i = 0; i < angles.length; i++) {
                const key = Math.round(angles[i] * 100) / 100;
                const prev = this._prevDistByAngleKey.get(key);
                const cur = dists[i];
                const sm = prev == null ? cur : (1 - k) * prev + k * cur;
                smoothedDists[i] = sm;
                newMap.set(key, sm);
            }
            this._prevDistByAngleKey = newMap;
        } else {
            smoothedDists.push(...dists);
            this._prevDistByAngleKey.clear();
        }

        const centerY = (typeof cfg.groundY === "number" ? cfg.groundY : 0) + this._getFovLift();
        const headingMat = Matrix.RotationYawPitchRoll((cfg.fovHeadingOffsetDeg || 0) * Math.PI / 180, 0, 0);
        const baseForward = this._getLogicalForward();
        const forwardForRebuild = Vector3.TransformNormal(baseForward, headingMat).normalize();

        const points = [];
        for (let i = 0; i < angles.length; i++) {
            const aRad = angles[i] * Math.PI / 180;
            const yawMat = Matrix.RotationYawPitchRoll(aRad, 0, 0);
            let dir = Vector3.TransformNormal(forwardForRebuild, yawMat);
            dir.y = 0;
            dir.normalize();
            const end = new Vector3(
                this.modelRoot.position.x + this.modelRoot.getAbsolutePosition().x - this.modelRoot.position.x,
                centerY,
                this.modelRoot.position.z + this.modelRoot.getAbsolutePosition().z - this.modelRoot.position.z
            ).add(dir.scale(smoothedDists[i]));
            points.push(end);
        }

        return {points, distances: smoothedDists};
    }

    _blockerPredicate(m) {
        const cfg = this.config;

        if (Array.isArray(cfg.ignoredBlockerMeshes) && cfg.ignoredBlockerMeshes.includes(m)) return false;

        // ignore own parts/debug/fov
        if (m.metadata && m.metadata.object === this) return false;
        if (m === this._fovMesh) return false;
        if (m.name && (m.name.startsWith("fovRay_") || m.name.startsWith("fovHit_") || m.name.startsWith("fovVisibility_"))) return false;

        if (m.name && cfg.ignoredBlockerNameRegex && cfg.ignoredBlockerNameRegex.test(m.name)) return false;
        if (cfg.groundNameIncludes &&
            m.name && m.name.toLowerCase().includes(cfg.groundNameIncludes.toLowerCase())) return false;

        if (cfg.useBlocksVisionOnly) return !!(m.metadata && m.metadata.blocksVision === true);
        if (Array.isArray(cfg.blockerMeshes) && cfg.blockerMeshes.length) return cfg.blockerMeshes.includes(m);

        return !!m.isPickable;
    }

    _buildOrUpdateFovMeshes(points, distances) {
        const color3 = getBabylonColor3(this.config.color);
        const alpha = (this.config.debugFov?.opaque ? 0.95 : this.config.fovAlpha) ?? 0.3;
        const centerPos = this.modelRoot.getAbsolutePosition();
        const center = new Vector3(centerPos.x, (this.config.groundY ?? 0) + this._getFovLift(), centerPos.z);

        const radius = this.config.vision_radius * this.config.scaling;
        const jump = Math.max(0.01, (this.config.segmentJumpThresholdFrac ?? 0.22) * radius);

        const segs = [];
        let start = 0;
        for (let i = 1; i < distances.length; i++) {
            if (Math.abs(distances[i] - distances[i - 1]) > jump) {
                if (i - start >= 2) segs.push([start, i]);
                start = i;
            }
        }
        if (points.length - start >= 2) segs.push([start, points.length]);

        while (this._fovMeshes.length < segs.length) {
            const m = new Mesh(`fovVisibility_${this.id}_${this._fovMeshes.length}`, this.scene);
            m.isPickable = false;
            m.renderingGroupId = 0;

            const mat = new StandardMaterial(`fovVisMat_${this.id}_${this._fovMeshes.length}`, this.scene);
            mat.diffuseColor = color3.clone();
            mat.emissiveColor = color3.scale(0.6);
            mat.specularColor = Color3.Black();
            mat.alpha = alpha;
            mat.backFaceCulling = false;
            mat.needDepthPrePass = true;
            mat.forceDepthWrite = false;

            m.material = mat;
            this._fovMeshes.push(m);
        }
        while (this._fovMeshes.length > segs.length) {
            const m = this._fovMeshes.pop();
            m?.dispose();
        }

        for (let s = 0; s < segs.length; s++) {
            const [a, b] = segs[s];
            const rim = points.slice(a, b);

            const verts = [];
            const indices = [];
            const normals = [];
            const uvs = [];

            verts.push(center.x, center.y, center.z);
            uvs.push(0.5, 0.5);

            for (let i = 0; i < rim.length; i++) {
                const pt = rim[i];
                verts.push(pt.x, pt.y, pt.z);
                uvs.push(0.5 + (pt.x - center.x), 0.5 + (pt.z - center.z));
            }

            for (let i = 1; i < rim.length; i++) indices.push(0, i, i + 1);

            const vd = new VertexData();
            vd.positions = verts;
            vd.indices = indices;
            vd.uvs = uvs;

            for (let i = 0; i < verts.length / 3; i++) normals.push(0, 1, 0);
            vd.normals = normals;

            vd.applyToMesh(this._fovMeshes[s], true);

            const mat = this._fovMeshes[s].material;
            if (mat && mat instanceof StandardMaterial) mat.alpha = alpha;
        }
    }

    _clearFovMeshes() {
        for (const m of this._fovMeshes) m?.dispose();
        this._fovMeshes = [];
    }

    /* === DEBUG VISUALS ========================================================================== */
    _updateDebugLines(raySegments) {
        const desired = raySegments.length;
        const cur = this._dbg.lines.length;

        for (let i = cur; i < desired; i++) {
            const l = MeshBuilder.CreateLines(`fovRay_${this.id}_${i}`, {
                points: [Vector3.Zero(), Vector3.Up()],
                updatable: true,
            }, this.scene);
            l.color = getBabylonColor3([1, 0, 0]);
            l.isPickable = false;
            l.alwaysSelectAsActiveMesh = true;
            l.renderingGroupId = 1;
            this._dbg.lines.push(l);
        }
        for (let i = desired; i < cur; i++) this._dbg.lines[i]?.dispose();
        this._dbg.lines.length = desired;

        for (let i = 0; i < desired; i++) {
            const seg = raySegments[i];
            const l = this._dbg.lines[i];
            if (!seg || !l) continue;
            MeshBuilder.CreateLines(null, {points: [seg[0], seg[1]], updatable: true, instance: l});
        }
    }

    _clearDebugLines() {
        for (const l of this._dbg.lines) l?.dispose();
        this._dbg.lines = [];
    }

    _updateDebugHitSpheres(points) {
        const desired = points.length;
        const cur = this._dbg.hits.length;

        for (let i = cur; i < desired; i++) {
            const s = MeshBuilder.CreateSphere(`fovHit_${this.id}_${i}`, {diameter: 0.15, segments: 6}, this.scene);
            const m = new StandardMaterial(`fovHitMat_${this.id}_${i}`, this.scene);
            m.diffuseColor = new Color3(0, 1, 0);
            m.emissiveColor = new Color3(0, 0.8, 0);
            s.material = m;
            s.isPickable = false;
            s.renderingGroupId = 1;
            this._dbg.hits.push(s);
        }
        for (let i = desired; i < cur; i++) this._dbg.hits[i]?.dispose();
        this._dbg.hits.length = desired;

        for (let i = 0; i < desired; i++) {
            const s = this._dbg.hits[i];
            const p = points[i];
            if (s && p) s.position.copyFrom(p);
        }
    }

    _clearDebugHitSpheres() {
        for (const s of this._dbg.hits) s?.dispose();
        this._dbg.hits = [];
    }

    _dbgLog(msg) {
        const dbg = this.config.debugFov || {};
        if (!dbg.enabled) return;
        const N = Math.max(1, (dbg.logEveryNFrames | 0) || 1);
        this._dbg.frame++;
        if (this._dbg.frame % N === 0) console.log(msg);
    }

    _getFovLift() {
        // Base lift + layer stride; tweak step if needed.
        const base = 0.001;
        const step = 0.001;
        return base + this._fovLayer * step;
    }

    /* === LABEL ================================================================================== */
    addText() {
        const dynamicTexture = new DynamicTexture(
            `DynamicTexture_${this.id}`,
            {width: 256, height: 256},
            this.scene
        );

        const ctx = dynamicTexture.getContext();
        ctx.clearRect(0, 0, 256, 256);

        ctx.beginPath();
        ctx.arc(128, 128, 120, 0, Math.PI * 2, false);
        ctx.fillStyle = "transparent";
        ctx.fill();
        ctx.lineWidth = 20;
        ctx.strokeStyle = getHTMLColor(this.config.text_color);
        ctx.stroke();

        const text = this.config.text ?? "";
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
        const [r, g, b] = this.config.text_color;
        const textColor = `rgb(${Math.floor(r * 255)}, ${Math.floor(g * 255)}, ${Math.floor(b * 255)})`;
        dynamicTexture.drawText(text, null, yOffset, font, textColor, null, true);
        dynamicTexture.update();

        const textMaterial = new PBRMaterial(`textMaterial_${this.id}`, this.scene);
        textMaterial.albedoTexture = dynamicTexture;
        textMaterial.albedoTexture.hasAlpha = true;
        textMaterial.useAlphaFromAlbedoTexture = true;
        textMaterial.opacityTexture = null;
        textMaterial.transparencyMode = PBRMaterial.MATERIAL_ALPHATEST;
        textMaterial.alphaCutOff = 0.2;
        textMaterial.needDepthPrePass = true;
        textMaterial.forceDepthWrite = true;
        textMaterial.metallic = 0;
        textMaterial.roughness = 1;
        textMaterial.environmentIntensity = 0;
        textMaterial.backFaceCulling = true;
        textMaterial.twoSidedLighting = true;
        textMaterial.unlit = false;
        textMaterial.emissiveColor = new Color3(0, 0, 0);

        this.textHolder?.dispose?.();
        this.textPlane?.dispose?.();

        const [px, py, pz] = this.config.text_local_position ?? [0.0325, 0.05, 0];
        const [rx, ry, rz] = this.config.text_local_rotation ?? [0, 1.57, 0];
        const [sx, sy, sz] = this.config.text_local_scale ?? [1, 1, -1];

        this.textHolder = new TransformNode(`textHolder_${this.id}`, this.scene);
        this.textHolder.parent = this.modelRoot;
        this.textHolder.position = new Vector3(px, py, pz);
        this.textHolder.rotation = new Vector3(rx, ry, rz);
        this.textHolder.scaling = new Vector3(sx, sy, sz);

        const planeSize = this.config.text_plane_size ?? 0.1;
        const [prx, pry, prz] = this.config.text_plane_rotation ?? [0, 0, 0];

        this.textPlane = MeshBuilder.CreatePlane(
            `textPlane_${this.id}`,
            {width: planeSize, height: planeSize, sideOrientation: Mesh.DOUBLESIDE},
            this.scene
        );
        this.textPlane.material = textMaterial;
        this.textPlane.parent = this.textHolder;
        this.textPlane.rotation = new Vector3(prx, pry, prz);
        this.textPlane.receiveShadows = false;
        this.textPlane.isPickable = true;
        this.textPlane.renderingGroupId = 0;

        this.textPlane.metadata = this.textPlane.metadata || {};
        this.textPlane.metadata.object = this;
    }

    /* === STATE ================================================================================== */
    onMessage(message) {
        return undefined;
    }

    setState(x, y, psi) {
        this.setPosition([x, y, 0]);
        const orientation = Quaternion.fromEulerAngles([psi, 0, 0], "zyx", true);
        this.setOrientation(orientation);
    }

    update(data) {
        if (!this.loaded) return;
        this.setState(data.x, data.y, data.psi);
    }

    onLoaded() {
        return this._ready;
    }

    setVisibility(visible) {
        super.setVisibility(visible); // toggles this.root (and thus modelRoot subtree)

        if (this.textHolder) this.textHolder.isVisible = visible;
        if (this.textPlane) this.textPlane.isVisible = visible;
        if (this.fovDisc) this.fovDisc.isVisible = visible;
        for (const m of this._fovMeshes) if (m) m.isVisible = visible;
        if (this._highlightPlane) this._highlightPlane.isVisible = visible && this._isHighlighted;
        if (this._dbg?.lines?.length) this._dbg.lines.forEach(l => l.isVisible = visible);
        if (this._dbg?.hits?.length) this._dbg.hits.forEach(s => s.isVisible = visible);
    }

    /* === HIGHLIGHT RING ======================================================================== */
    highlight(state) {
        this._isHighlighted = state;

        if (state) {
            if (!this._highlightPlane) {
                const texSize = 512;
                const dt = new DynamicTexture(`hlTex_${this.id}`, {width: texSize, height: texSize}, this.scene, false);
                const ctx = dt.getContext();
                ctx.clearRect(0, 0, texSize, texSize);

                const c = texSize / 2;
                const thickness = Math.floor(texSize * 0.12);
                ctx.beginPath();
                ctx.arc(c, c, c - 1, 0, Math.PI * 2);
                ctx.arc(c, c, c - thickness - 1, 0, Math.PI * 2, true);

                const [r, g, b] = this.config.color || [1, 0, 0];
                ctx.fillStyle = `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, 0.5)`;
                ctx.fill();
                dt.update();

                const mat = new StandardMaterial(`hlMat_${this.id}`, this.scene);
                mat.diffuseTexture = dt;
                mat.diffuseTexture.hasAlpha = true;
                mat.useAlphaFromDiffuseTexture = true;
                mat.transparencyMode = StandardMaterial.MATERIAL_ALPHABLEND;
                mat.backFaceCulling = false;
                mat.specularColor = new Color3(0, 0, 0);
                mat.emissiveColor = getBabylonColor3(this.config.color || [1, 0, 0]);
                mat.needDepthPrePass = true;
                mat.forceDepthWrite = true;
                mat.disableDepthTest = false;

                const BASE_SIZE = 1;
                const plane = MeshBuilder.CreatePlane(`hlPlane_${this.id}`, {size: BASE_SIZE}, this.scene);
                plane.material = mat;
                plane.isPickable = false;
                plane.rotation.x = Math.PI / 2;
                plane.renderingGroupId = 0;

                this._hlBaseSize = BASE_SIZE;
                this._highlightPlane = plane;
            }

            this._highlightPlane.isVisible = true;

            const groundY = typeof this.config.groundY === "number" ? this.config.groundY : 0;
            const extraPad = typeof this.config.highlightPad === "number" ? this.config.highlightPad : 1.15;
            const smallLift = this._getFovLift();

            const computeWorldDiameter = () => {
                const bi = this.modelRoot.getHierarchyBoundingVectors();
                // fallback: use child mesh bounding info if needed
                let halfW = 0, halfD = 0;
                if (bi?.max && bi?.min) {
                    const dx = Math.abs(bi.max.x - bi.min.x) * 0.5;
                    const dz = Math.abs(bi.max.z - bi.min.z) * 0.5;
                    halfW = dx;
                    halfD = dz;
                }
                const radiusXZ = Math.hypot(halfW, halfD) * extraPad;
                return Math.max(0.001, radiusXZ * 2);
            };

            const updateRing = () => {
                if (!this.modelRoot || this.modelRoot.isDisposed() || !this._highlightPlane || this._highlightPlane.isDisposed()) return;

                const p = this.modelRoot.getAbsolutePosition();
                this._highlightPlane.position.x = p.x;
                this._highlightPlane.position.z = p.z;
                this._highlightPlane.position.y = groundY + smallLift;

                const diameter = computeWorldDiameter();
                const f = diameter / this._hlBaseSize;
                this._highlightPlane.scaling.x = f;
                this._highlightPlane.scaling.y = f;
            };

            updateRing();
            if (!this._highlightObserver) {
                this._highlightObserver = this.scene.onBeforeRenderObservable.add(updateRing);
            }
        } else {
            if (this._highlightObserver) {
                this.scene.onBeforeRenderObservable.remove(this._highlightObserver);
                this._highlightObserver = null;
            }
            if (this._highlightPlane) this._highlightPlane.isVisible = false;
        }
    }

    /* === DISPOSE =============================================================================== */
    delete() {
        if (this._highlightObserver) {
            this.scene.onBeforeRenderObservable.remove(this._highlightObserver);
            this._highlightObserver = null;
        }
        if (this._fovObserver) {
            this.scene.onBeforeRenderObservable.remove(this._fovObserver);
            this._fovObserver = null;
        }
        if (this._highlightPlane && !this._highlightPlane.isDisposed()) this._highlightPlane.dispose();
        this._clearFovMeshes();
        if (this.fovDisc && !this.fovDisc.isDisposed()) this.fovDisc.dispose();
        if (this.textPlane && !this.textPlane.isDisposed()) this.textPlane.dispose();
        if (this.textHolder && !this.textHolder.isDisposed()) this.textHolder.dispose();

        // Disposing the root will clean up modelRoot and imported meshes as well
        super.delete();
    }

    dim(state) {
        return undefined;
    }
}

