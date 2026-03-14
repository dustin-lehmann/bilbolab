// drawings.js
import {
    MeshBuilder,
    Mesh,
    TransformNode,
    StandardMaterial,
    PBRMaterial,
    Color3,
    Color4,
    Vector3,
    Material,
    DynamicTexture,
    Matrix,
    Texture,
    Quaternion as Bq,  // alias to avoid conflict with your own Quaternion class
} from "@babylonjs/core";
import {BabylonObject} from "../objects.js";
import {coordinatesToBabylon, getBabylonColor3, getHTMLColor} from "../babylon_utils.js";
import {Quaternion} from "../quaternion.js";


export class BabylonDrawingObject extends BabylonObject {
    constructor(id, scene, payload = {}) {
        super(id, scene, payload);

        const default_config = {
            // elevation above "floor" to avoid z-fighting
            lift: 0.001,
            groundY: 0, // world ground height in your coords (z-up), converted in setPosition
            // common orientation (yaw about your z-up)
            yaw: 0, // radians
            // common visibility & pickability
            pickable: false,
        };

        this.config = {...default_config, ...(this.config || {})};
        this._root = null; // TransformNode root; children are meshes that make the drawing

        this.buildObject();
    }

    /* Helpers */
    _toC3a([r, g, b, a], fallbackA = 1) {
        return {c3: new Color3(r, g, b), a: (a ?? fallbackA)};
    }

    _stdMat(id, color) {
        const {c3, a} = this._toC3a(color);
        const mat = new StandardMaterial(`${id}_mat`, this.scene);
        mat.diffuseColor = c3.clone();
        mat.emissiveColor = c3.scale(0.6);
        mat.specularColor = Color3.Black();
        mat.alpha = a;
        // These two make the overlay behave well with depth (like you did on Frodo label)
        mat.needDepthPrePass = true;
        mat.forceDepthWrite = true;
        mat.backFaceCulling = false;
        return mat;
    }

    _disposeChildren() {
        if (!this._root) return;
        for (const child of this._root.getChildMeshes()) {
            child.dispose();
        }
    }

    buildObject() {
        if (this._root) this._root.dispose();
        this._root = new TransformNode(`${this.id}_root`, this.scene);
        this._root.metadata = {object: this};

        // concrete subclasses add meshes as children of _root
        this._build();
        this._applyCommon();
    }

    // to be implemented by subclasses: must add child meshes under this._root
    _build() {
        throw new Error("Method not implemented.");
    }

    _applyCommon() {
        if (!this._root) return;
        // pickable flag
        for (const m of this._root.getChildMeshes()) {
            m.isPickable = !!this.config.pickable;
            m.metadata = m.metadata || {};
            m.metadata.object = this;
            m.renderingGroupId = 0; // opaque queue (depth writing)
        }
        // transform
        const pos = this.position || [0, 0, 0];
        this.setPosition(pos);
        this.setOrientation(this.orientation || Quaternion.fromEulerAngles([this.config.yaw, 0, 0], "zyx", true));
    }

    /* ===== BabylonObject overrides ===== */

    setPosition(position) {
        // position is [x, y, z] in your z-up coordinates.
        // We want to place on the "floor", with a slight lift over ground.
        const [x, y, z] = Array.isArray(position)
            ? position
            : [position.x, position.y, position.z];

        this.position = [x, y, z];
        const floorZ = (this.config.groundY ?? 0) + (this.config.lift ?? 0);

        // Convert your position but force the "height" to be floorZ in your coords
        const p = coordinatesToBabylon([x, y, floorZ]);
        if (this._root) this._root.position = p;
    }

    setOrientation(orientation) {
        // Allow either a Quaternion (preferred) or yaw radians.
        if (orientation instanceof Quaternion) {
            this.orientation = orientation;
        } else if (typeof orientation === "number") {
            this.orientation = Quaternion.fromEulerAngles([orientation, 0, 0], "zyx", true);
        } else {
            // fallback to yaw in config
            this.orientation = Quaternion.fromEulerAngles([this.config.yaw || 0, 0, 0], "zyx", true);
        }

        if (this._root) {
            this._root.rotationQuaternion = this.orientation.babylon();
        }
    }

    update(data = {}) {
        // Shallow-merge config & data and rebuild if geometry-affecting stuff changed.
        const keysThatRequireRebuild = [
            // generic
            "lift", "groundY", "yaw", "pickable",
            // rectangle
            "width", "height", "fillColor", "borderColor", "borderWidth",
            // circle
            "radius", "circleFillColor", "circleBorderColor", "circleBorderWidth",
            // line
            "start", "end", "lineColor", "lineWidth", "lineStyle", "dashSize", "gapSize", "dotSize"
        ];

        const old = JSON.stringify(keysThatRequireRebuild.reduce((o, k) => {
            if (this.config[k] !== undefined) o[k] = this.config[k];
            return o;
        }, {}));


        this.config = {...this.config, ...(data.config || {})};
        this.data = {...this.data, ...(data.data || {})};

        if (data.position) this.setPosition(data.position);
        if (data.orientation != null) this.setOrientation(data.orientation);

        const now = JSON.stringify(keysThatRequireRebuild.reduce((o, k) => {
            if (this.config[k] !== undefined) o[k] = this.config[k];
            return o;
        }, {}));

        if (old !== now) {
            this.redraw()
        }
    }

    redraw() {
        this._disposeChildren();
        this._build();
        this._applyCommon();
    }

    highlight(state) {
        // simple: lift emissive when highlighted
        for (const m of this._root?.getChildMeshes() || []) {
            const mat = m.material;
            if (mat && mat.emissiveColor) {
                mat.emissiveColor = state ? mat.emissiveColor.scale(1.5) : mat.emissiveColor.scale(2 / 3);
            }
        }
    }

    setVisibility(visible) {
        super.setVisibility(visible);
        if (this._root) this._root.setEnabled(!!visible);
    }

    delete() {
        this._root?.dispose?.();
        this._root = null;
    }

    dim(state) {
        for (const m of this._root?.getChildMeshes() || []) {
            if (m.material && m.material.diffuseColor) {
                m.material.alpha = state ? 0.35 : (m.material.alpha ?? 1);
            }
        }
    }

    onMessage(message) { /* no-op */
    }
}

export class BabylonRectangleDrawing extends BabylonDrawingObject {
    constructor(id, scene, payload = {}) {
        const defaults = {
            width: 1,
            height: 1,
            // fill
            fillColor: [1, 1, 1, 0.15], // [r,g,b,a] 0..1
            // border
            borderColor: [1, 1, 1, 0.9],
            borderWidth: 0.02,            // world units
            // draw order for translucent fills (higher draws later/on top)
            stack: 0,
        };
        payload.config = {...defaults, ...(payload.config || {})};
        super(id, scene, payload);
    }

    _build() {
        const {
            width,
            height,
            fillColor,
            borderColor,
            borderWidth,
            stack,
        } = this.config;

        // tiny per-layer lift to avoid coplanarity among multiple drawings
        const stackLift = (stack | 0) * 0.00015;

        // === FILL: translucent, no depth write, painter-ordered ===
        // Ground is already XZ-aligned, perfect for our floor decals.
        const fill = MeshBuilder.CreateGround(
            `${this.id}_fill`,
            {width, height, subdivisions: 1},
            this.scene
        );
        fill.material = this._makeTranslucentFillMat(`${this.id}_fill`, fillColor);

        // render in transparent group; stable order via alphaIndex
        fill.renderingGroupId = 1;
        fill.alphaIndex = stack | 0;

        // small lift on top of base lift to avoid coplanar artifacts with other fills
        fill.position.y += stackLift;
        fill.parent = this._root;

        // === BORDER: four opaque bars (depth-writing and crisp) ===
        const bw = Math.max(0, borderWidth);
        const hx = width * 0.5;
        const hz = height * 0.5;

        // along X (top & bottom edges)
        const mkBarX = (name, z) => {
            const bar = MeshBuilder.CreateBox(
                name,
                {
                    width,              // spans the full width
                    height: 0.0005,     // ultra-thin actual thickness
                    depth: Math.max(bw, 0.0005),
                },
                this.scene
            );
            bar.material = this._stdMat(name, borderColor);
            bar.position = new Vector3(0, 0, z);
            bar.position.y += stackLift + 0.00005; // sit slightly above the fill
            bar.renderingGroupId = 0;              // opaque queue (writes depth)
            bar.parent = this._root;
        };

        mkBarX(`${this.id}_border_top`, -hz + bw * 0.5);
        mkBarX(`${this.id}_border_bottom`, hz - bw * 0.5);

        // along Z (left & right edges)
        const mkBarZ = (name, x) => {
            const bar = MeshBuilder.CreateBox(
                name,
                {
                    width: Math.max(bw, 0.0005),
                    height: 0.0005,
                    depth: height,
                },
                this.scene
            );
            bar.material = this._stdMat(name, borderColor);
            bar.position = new Vector3(x, 0, 0);
            bar.position.y += stackLift + 0.00005;
            bar.renderingGroupId = 0;
            bar.parent = this._root;
        };

        mkBarZ(`${this.id}_border_left`, -hx + bw * 0.5);
        mkBarZ(`${this.id}_border_right`, hx - bw * 0.5);
    }

    // translucent, non–depth-writing fill material (same behavior as circles)
    _makeTranslucentFillMat(id, rgba) {
        const [r, g, b, a = 1] = rgba || [1, 1, 1, 1];
        const col = new Color3(r, g, b);

        const mat = new StandardMaterial(`${id}_mat`, this.scene);
        mat.diffuseColor = col.clone();
        mat.emissiveColor = col.scale(0.6);
        mat.specularColor = Color3.Black();

        mat.alpha = a;
        mat.transparencyMode = Material.MATERIAL_ALPHABLEND; // blended
        mat.disableDepthWrite = true;                        // no depth write → no “blocking”
        mat.needDepthPrePass = false;
        mat.forceDepthWrite = false;

        mat.backFaceCulling = false;
        return mat;
    }
}


export class BabylonCircleDrawing extends BabylonDrawingObject {
    constructor(id, scene, payload = {}) {
        const defaults = {
            radius: 0.5,
            // fill
            circleFillColor: [1, 1, 1, 0.15], // [r,g,b,a] 0..1
            // border
            circleBorderColor: [1, 1, 1, 0.9],
            circleBorderWidth: 0.02, // world units (visual thickness; tube radius ~ half)
            // tesselation / quality
            tessellation: 64,
            // stacking/ordering for overlapping fills; higher = drawn later (on top)
            stack: 0,
        };


        payload.config = {...defaults, ...(payload.config || {})};
        super(id, scene, payload);
    }

    // --- build complete mesh set under this._root ---
    _build() {
        const {
            radius,
            circleFillColor,
            circleBorderColor,
            circleBorderWidth,
            tessellation,
            stack,
        } = this.config;

        // small per-instance lift to avoid coplanar headaches across multiple drawings
        const stackLift = (stack | 0) * 0.00015;

        // === FILL: translucent, no depth write, sorted via alphaIndex ===
        const disc = MeshBuilder.CreateDisc(
            `${this.id}_fill`,
            {
                radius,
                tessellation: Math.max(16, tessellation | 0),
                sideOrientation: Mesh.DOUBLESIDE,
            },
            this.scene
        );
        disc.rotation = new Vector3(Math.PI / 2, 0, 0); // lie on XZ
        disc.position.y += stackLift;                   // tiny lift for safety
        disc.material = this._makeTranslucentFillMat(`${this.id}_fill`, circleFillColor);

        // transparent group + stable painter’s order
        disc.renderingGroupId = 1;
        disc.alphaIndex = stack | 0;

        disc.parent = this._root;

        // === BORDER: opaque tube following a circle path (writes depth; stays crisp) ===
        const steps = Math.max(24, tessellation | 0);
        const pts = [];
        for (let i = 0; i <= steps; i++) {
            const t = (i / steps) * Math.PI * 2;
            pts.push(new Vector3(Math.cos(t) * radius, 0, Math.sin(t) * radius));
        }

        const tube = MeshBuilder.CreateTube(
            `${this.id}_border`,
            {
                path: pts,
                radius: Math.max(0.0005, circleBorderWidth * 0.5),
                updatable: false,
                cap: Mesh.CAP_ALL,
            },
            this.scene
        );
        tube.material = this._stdMat(`${this.id}_border`, circleBorderColor);
        tube.position.y += stackLift + 0.00005; // sit just above the fill
        tube.renderingGroupId = 0;              // opaque queue (depth writes)
        tube.parent = this._root;
    }


    setDiameter(diameter) {
        this.config.radius = diameter * 0.5;
        this.redraw();
    }

    setRadius(radius) {
        this.config.radius = radius;
        this.redraw();
    }

    // === helper: translucent, non–depth-writing material for fills ===
    _makeTranslucentFillMat(id, rgba) {
        const [r, g, b, a = 1] = rgba || [1, 1, 1, 1];
        const col = new Color3(r, g, b);

        const mat = new StandardMaterial(`${id}_mat`, this.scene);
        mat.diffuseColor = col.clone();
        mat.emissiveColor = col.scale(0.6);
        mat.specularColor = Color3.Black();

        mat.alpha = a;
        mat.transparencyMode = Material.MATERIAL_ALPHABLEND;
        mat.disableDepthWrite = true;  // <-- critical for overlapping fills
        mat.needDepthPrePass = false;
        mat.forceDepthWrite = false;

        mat.backFaceCulling = false;
        return mat;
    }
}


export class BabylonObjectCircleDrawing extends BabylonCircleDrawing {
    constructor(id, scene, payload = {}){
        super(id, scene, payload);


    }
}


export class BabylonLineDrawing extends BabylonDrawingObject {
    constructor(id, scene, payload = {}) {
        const defaults = {
            // endpoints in your z-up coords; [x,y] => z=0 implied, or [x,y,z]
            start: [0, 0, 0],
            end: [1, 0, 0],

            lineColor: [1, 1, 1, 0.95],
            lineWidth: 0.02,       // world units (tube radius ≈ half this)

            lineStyle: "solid",    // "solid" | "dashed" | "dotted"

            // You can set these to override the auto rules; if omitted they’re auto-picked.
            dashSize: undefined,  // drawn length of each dash (world units)
            gapSize: undefined,  // gap length (world units)
            dotSize: undefined,  // diameter of dots (world units)
            dotStep: undefined,  // spacing between dot centers (world units)

            // stacking/lift (cosmetic consistency with other drawings)
            stack: 0,
            groundY: 0,
            lift: 0.001,

            // optional extra yaw in your (z-up) coords
            yaw: 0,
        };
        payload.config = {...defaults, ...(payload.config || {})};
        super(id, scene, payload);
    }

    /* ========= override: don't re-apply pos/orientation after _build() ========= */
    _applyCommon() {
        if (!this._root) return;
        const pickable = !!this.config.pickable;
        for (const m of this._root.getChildMeshes()) {
            m.isPickable = pickable;
            m.metadata = m.metadata || {};
            m.metadata.object = this;
            m.renderingGroupId = 0; // opaque queue (depth writing)
        }
        // NOTE: Do not call setPosition/setOrientation here — _build() places the root.
    }

    /* ================================ build geometry ================================ */
    _build() {
        const {
            start, end,
            lineColor, lineWidth,
            lineStyle,
            dashSize, gapSize, dotSize, dotStep,
            stack, groundY, lift, yaw,
        } = this.config;

        // ---------- auto parameters from width (only if not provided) ----------
        const w = Math.max(1e-5, lineWidth);

        // dashed: readable “railroad” look
        const autoDash = this._autoDashParams(w); // {dash, gap}
        const D_dash = dashSize ?? autoDash.dash;
        const G_gap = gapSize ?? autoDash.gap;

        // dotted: pleasant round beads
        const autoDot = this._autoDotParams(w);   // {diameter, step}
        const DOT_D = dotSize ?? autoDot.diameter;
        const DOT_S = dotStep ?? autoDot.step;

        // normalize endpoints to [x,y,z] (your z-up)
        const toXYZ = (p) =>
            Array.isArray(p)
                ? (p.length === 2 ? [p[0], p[1], 0] : p)
                : [p.x, p.y, p.z ?? 0];

        const s = toXYZ(start);
        const e = toXYZ(end);

        // convert to Babylon coords and pin to ground+lift
        const S = coordinatesToBabylon([s[0], s[1], groundY + lift]);
        const E = coordinatesToBabylon([e[0], e[1], groundY + lift]);

        // direction & length in Babylon space (project to XZ)
        // work in YOUR z-up
        const dx = e[0] - s[0];
        const dy = e[1] - s[1];
        const len = Math.max(1e-6, Math.hypot(dx, dy));
        const yawZup = Math.atan2(dy, dx);

        const extraYaw = Quaternion.fromEulerAngles([yaw || 0, 0, 0], "zyx", true);
        const qYaw = Quaternion.fromEulerAngles([yawZup, 0, 0], "zyx", true);

        // place root at the Babylon-converted start and rotate using z-up quaternion → .babylon()
        this._root.position.copyFrom(S);
        this._root.rotationQuaternion = extraYaw.multiply(qYaw).babylon();

        const mat = this._stdMat(`${this.id}_line`, lineColor);
        const stackLift = (stack | 0) * 0.00015;

        if (lineStyle === "solid") {
            const path = [new Vector3(0, stackLift, 0), new Vector3(len, stackLift, 0)];
            const tube = MeshBuilder.CreateTube(
                `${this.id}_tube`,
                {path, radius: Math.max(0.0005, w * 0.5), cap: Mesh.CAP_ALL},
                this.scene
            );
            tube.material = mat;
            tube.parent = this._root;
            return;
        }

        if (lineStyle === "dashed") {
            const dash = Math.max(1e-4, D_dash);
            const gap = Math.max(0, G_gap);
            let cursor = 0;
            let i = 0;
            while (cursor < len - 1e-6) {
                const segLen = Math.min(dash, len - cursor);
                const path = [
                    new Vector3(cursor, stackLift, 0),
                    new Vector3(cursor + segLen, stackLift, 0),
                ];
                const tube = MeshBuilder.CreateTube(
                    `${this.id}_dash_${i++}`,
                    {path, radius: Math.max(0.0005, w * 0.5), cap: Mesh.CAP_ALL},
                    this.scene
                );
                tube.material = mat;
                tube.parent = this._root;
                cursor += dash + gap;
            }
            return;
        }

        // dotted
        const step = Math.max(1e-4, DOT_S);
        const dia = Math.max(0.0005, DOT_D);
        let d = 0;
        let j = 0;
        while (d <= len + 1e-6) {
            const s = MeshBuilder.CreateSphere(
                `${this.id}_dot_${j++}`,
                {diameter: dia, segments: 6},
                this.scene
            );
            s.material = mat;
            s.position = new Vector3(d, stackLift, 0);
            s.parent = this._root;
            d += step;
        }
    }

    /* ========= updates: rebuild when endpoints/style/width change ========= */
    update(data = {}) {
        const keys = [
            "start", "end", "lineColor", "lineWidth",
            "lineStyle", "dashSize", "gapSize", "dotSize", "dotStep",
            "yaw", "groundY", "lift", "stack", "pickable"
        ];
        const before = JSON.stringify(keys.map(k => this.config[k]));
        this.config = {...this.config, ...(data.config || {})};
        this.data = {...this.data, ...(data.data || {})};

        const after = JSON.stringify(keys.map(k => this.config[k]));
        if (before !== after) {
            this._disposeChildren();
            this._build();
            this._applyCommon();
        }
    }


    updatePoints({start, end} = {}) {
        if (start) this.config.start = start;
        if (end) this.config.end = end;
        this.redraw();
    }

    /* ============================ helpers: auto params ============================ */
    _autoDashParams(width) {
        // readable, not-too-noisy dashes that scale with thickness
        // dash ≈ 10× width, gap ≈ 4× width
        const dash = 10 * width;
        const gap = 4 * width;
        return {dash, gap};
    }

    _autoDotParams(width) {
        // round beads that look balanced for most widths
        // diameter ≈ 1.6× width, spacing (center-to-center) ≈ 3.2× width
        const diameter = 1.6 * width;
        const step = 3.2 * width;
        return {diameter, step};
    }
}


export class BabylonObjectLineDrawing extends BabylonLineDrawing {
    constructor(id, scene, payload = {}) {
        // Always pass a config object to avoid undefined writes during parent ctor build
        const safePayload = payload || {};
        safePayload.config = {...(safePayload.config || {})};
        super(id, scene, safePayload);

        // NOTE: parent constructor may call buildObject() -> _build() before this body runs
        // so guards inside _build() handle first-call initialization.

        // These will be used for subsequent updates
        this._obs = {start: null, end: null};           // observer handles
        this._last = {start: null, end: null};          // last resolved endpoints (z-up)
        this._lastFlag = {start: null, end: null};      // last world-matrix updateFlag per ref

        // Optional override used to rebuild with already-resolved points without mutating config
        this._overrideResolved = null;

        this._retargetObservers();

        // Make sure geometry uses concrete endpoints after construction
        this.redraw();
    }

    /* ---------------- lifecycle ---------------- */

    update(data = {}) {
        super.update(data);
        // If refs changed from fixed <-> object, retarget observers
        this._retargetObservers();
    }

    delete() {
        this._detach("start");
        this._detach("end");
        super.delete();
    }

    /* ---------------- build: resolve refs to concrete points ---------------- */

    _build() {

        // Defensive init for first build invoked from parent ctor
        if (!this._last) this._last = {start: null, end: null};
        if (!this._obs) this._obs = {start: null, end: null};
        if (!this._lastFlag) this._lastFlag = {start: null, end: null};
        if (!this.config) this.config = {};

        // Use override (when coming from observer) OR resolve from current config refs
        const resolvedStart = this._overrideResolved?.start ?? this._resolve(this.config.start);
        const resolvedEnd = this._overrideResolved?.end ?? this._resolve(this.config.end);

        // cache for change detection
        this._last.start = resolvedStart;
        this._last.end = resolvedEnd;

        // Temporarily inject concrete points so the parent builds correct geometry
        const originalConfig = this.config;
        this.config = {...originalConfig, start: resolvedStart, end: resolvedEnd};
        try {
            super._build();
        } finally {
            this.config = originalConfig;
            this._overrideResolved = null; // one-shot
        }
    }

    /* ---------------- observers on referenced objects ---------------- */

    _retargetObservers() {
        this._attach("start", this.config?.start);
        this._attach("end", this.config?.end);
    }

    _attach(which, ref) {
        this._detach(which); // avoid duplicates

        if (this._isObj(ref) && ref.root?.onAfterWorldMatrixUpdateObservable) {
            // Initialize lastFlag to current so the first fire is only when it changes again
            const wm = ref.root.getWorldMatrix?.();
            this._lastFlag[which] = wm?.updateFlag ?? null;

            this._obs[which] = ref.root.onAfterWorldMatrixUpdateObservable.add(() => this._onRefMoved(which, ref));
        }
    }

    _detach(which) {
        const ref = this.config?.[which];
        if (this._obs?.[which] && this._isObj(ref) && ref.root?.onAfterWorldMatrixUpdateObservable) {
            ref.root.onAfterWorldMatrixUpdateObservable.remove(this._obs[which]);
        }
        if (this._obs) this._obs[which] = null;
        if (this._lastFlag) this._lastFlag[which] = null;
    }

    _onRefMoved(which, ref) {
        // 1) FILTER NO-OP CALLBACKS using Babylon's updateFlag
        if (this._isObj(ref) && ref.root?.getWorldMatrix) {
            const flag = ref.root.getWorldMatrix().updateFlag;
            if (this._lastFlag[which] === flag) {
                // no real transform change; ignore
                return;
            }
            this._lastFlag[which] = flag;
        }

        // 2) Resolve current endpoints (keep config refs intact)
        const s = this._resolve(this.config?.start);
        const e = this._resolve(this.config?.end);

        // 3) Compare vs last (z-up)
        if (!this._last) this._last = {start: null, end: null};
        const moved = !this._last.start || !this._last.end ||
            this._changed(s, this._last.start) || this._changed(e, this._last.end);
        if (!moved) return;

        // 4) Cache & rebuild WITHOUT mutating config.start/end (preserve object refs)
        this._last.start = s;
        this._last.end = e;

        // Use a one-shot override so _build() consumes these exact points
        this._overrideResolved = {start: s, end: e};
        this.redraw();
    }

    /* ---------------- override: prevent config mutation on point updates ---------------- */

    // If someone calls this explicitly, keep behavior non-destructive:
    updatePoints({start, end} = {}) {
        if (start) this._last.start = start;
        if (end) this._last.end = end;
        this._overrideResolved = {start: this._last.start, end: this._last.end};
        this.redraw();
    }

    /* ---------------- helpers ---------------- */

    _isObj(v) {
        return v && typeof v === "object" && v instanceof BabylonObject;
    }

    _resolve(ref) {
        // Return [x,y,z] in YOUR z-up space
        if (Array.isArray(ref)) {
            return ref.length === 2
                ? [ref[0] ?? 0, ref[1] ?? 0, 0]
                : [ref[0] ?? 0, ref[1] ?? 0, ref[2] ?? 0];
        }
        if (this._isObj(ref)) {
            // Prefer the logical z-up position maintained by the object
            const p = ref.position ?? [0, 0, 0];
            if (Array.isArray(p)) {
                return p.length === 2 ? [p[0] ?? 0, p[1] ?? 0, 0] : [p[0] ?? 0, p[1] ?? 0, p[2] ?? 0];
            }
            if (p && typeof p === "object") {
                const x = "x" in p ? p.x : 0;
                const y = "y" in p ? p.y : 0;
                const z = "z" in p ? p.z : 0;
                return [x ?? 0, y ?? 0, z ?? 0];
            }
            return [0, 0, 0];
        }
        return [0, 0, 0];
    }

    _changed(a, b) {
        const eps = 1e-5;
        return (
            Math.abs(a[0] - b[0]) > eps ||
            Math.abs(a[1] - b[1]) > eps ||
            Math.abs(a[2] - b[2]) > eps
        );
    }
}


export class BabylonLabeledLineDrawing extends BabylonLineDrawing {
    constructor(id, scene, payload = {}) {
        const defaults = {
            labelText: "THIS IS A LABEL",
            labelColor: [0, 0, 0],
            labelFontSize: 1000,
            labelLift: 0.002,
            labelOffset: 0,
            labelPlaneRotation: [-Math.PI / 2, 0, 0],
            labelPadPx: 24,
            labelHeightFactor: 6.0,
            labelFlipU: false,
            labelFlipV: false,

            labelWorldHeight: 0.06,
            labelMinWorldHeight: 0.02,
            labelResolutionMultiplier: 1,

            labelBgColor: [1, 1, 1],
            labelBgAlpha: 0.1,
            labelBgRadiusPx: 250,
            labelBorderColor: [0, 0, 0],
            labelBorderAlpha: 1,
            labelBorderWidthPx: 100,

            labelMakesGap: true,
            labelGapExtraWorld: 0.002,
        };
        payload = payload || {};
        payload.config = {...defaults, ...(payload.config || {})};
        super(id, scene, payload);

        // line caches
        this._lineMat = null;
        this._tubeA = null;
        this._tubeB = null;

        // dash/dot prototypes & instance pools
        this._dashProto = null;
        this._dashInstances = []; // InstancedMesh[]
        this._dotProto = null;
        this._dotInstances = [];  // InstancedMesh[]

        // label caches
        this._labelPlane = null;
        this._labelMat = null;
        this._labelDT = null;
        this._lastLabelSpec = {
            text: null, color: null, fontPx: null, pad: null, flips: null,
            bg: null, bgalpha: null, bgradius: null, border: null, borderAlpha: null, borderW: null,
            resMul: null
        };

        // throttled recompute
        this._dirty = true;
        this._beforeRenderObs = this.scene.onBeforeRenderObservable.add(() => {
            if (!this._dirty) return;
            this._dirty = false;
            this._recomputeGeometry(false);
        });

        this._recomputeGeometry(true);
    }

    _markDirty() {
        this._dirty = true;
    }

    redraw() {
        this._recomputeGeometry(true);
    }

    update(data = {}) {
        const keys = [
            "start", "end", "lineColor", "lineWidth",
            "lineStyle", "dashSize", "gapSize", "dotSize", "dotStep",
            "yaw", "groundY", "lift", "stack", "pickable",
            "labelText", "labelColor", "labelFontSize", "labelLift",
            "labelPlaneRotation", "labelPadPx", "labelHeightFactor",
            "labelFlipU", "labelFlipV", "labelOffset",
            "labelWorldHeight", "labelMinWorldHeight", "labelResolutionMultiplier",
            "labelBgColor", "labelBgAlpha", "labelBgRadiusPx",
            "labelBorderColor", "labelBorderAlpha", "labelBorderWidthPx",
            "labelMakesGap", "labelGapExtraWorld",
        ];
        const before = JSON.stringify(keys.map(k => this.config[k]));
        this.config = {...this.config, ...(data.config || {})};
        this.data = {...this.data, ...(data.data || {})};
        const after = JSON.stringify(keys.map(k => this.config[k]));

        if (before !== after) {
            const affectsLabelBitmap = !!(data.config && (
                "labelText" in data.config ||
                "labelColor" in data.config ||
                "labelFontSize" in data.config ||
                "labelPadPx" in data.config ||
                "labelFlipU" in data.config ||
                "labelFlipV" in data.config ||
                "labelBgColor" in data.config ||
                "labelBgAlpha" in data.config ||
                "labelBgRadiusPx" in data.config ||
                "labelBorderColor" in data.config ||
                "labelBorderAlpha" in data.config ||
                "labelBorderWidthPx" in data.config ||
                "labelResolutionMultiplier" in data.config
            ));
            this._recomputeGeometry(affectsLabelBitmap);
        }
    }

    delete() {
        if (this._beforeRenderObs) {
            this.scene.onBeforeRenderObservable.remove(this._beforeRenderObs);
            this._beforeRenderObs = null;
        }
        // solids
        if (this._tubeA && !this._tubeA.isDisposed()) this._tubeA.dispose();
        if (this._tubeB && !this._tubeB.isDisposed()) this._tubeB.dispose();
        if (this._lineMat && !this._lineMat.isDisposed) this._lineMat.dispose();

        // dashes
        for (const inst of this._dashInstances) inst?.dispose?.();
        this._dashInstances = [];
        this._dashProto?.dispose?.();
        this._dashProto = null;

        // dots
        for (const inst of this._dotInstances) inst?.dispose?.();
        this._dotInstances = [];
        this._dotProto?.dispose?.();
        this._dotProto = null;

        // label
        if (this._labelPlane && !this._labelPlane.isDisposed()) this._labelPlane.dispose();
        if (this._labelMat && !this._labelMat.isDisposed) this._labelMat.dispose();
        if (this._labelDT && !this._labelDT.isDisposed) this._labelDT.dispose();

        super.delete();
    }

    _recomputeGeometry(fullRecreate) {
        const {
            start, end,
            lineColor, lineWidth,
            lineStyle, dashSize, gapSize, dotSize, dotStep,
            stack, groundY, lift, yaw,
            labelText, labelColor, labelFontSize, labelLift,
            labelPadPx, labelHeightFactor, labelPlaneRotation,
            labelFlipU, labelFlipV, labelOffset,
            labelWorldHeight, labelMinWorldHeight, labelResolutionMultiplier,
            labelBgColor, labelBgAlpha, labelBgRadiusPx,
            labelBorderColor, labelBorderAlpha, labelBorderWidthPx,
            labelMakesGap, labelGapExtraWorld,
        } = this.config;

        // Resolve endpoints (z-up → Babylon)
        const s = this._resolveRef(start);
        const e = this._resolveRef(end);
        const S = coordinatesToBabylon([s[0], s[1], groundY + lift]);
        const dx = e[0] - s[0];
        const dy = e[1] - s[1];
        const len = Math.max(1e-6, Math.hypot(dx, dy));
        const yawZup = Math.atan2(dy, dx);

        const extraYaw = Quaternion.fromEulerAngles([yaw || 0, 0, 0], "zyx", true);
        const qYaw = Quaternion.fromEulerAngles([yawZup, 0, 0], "zyx", true);

        const root = this._root;
        root.position.copyFrom(S);
        root.rotationQuaternion = extraYaw.multiply(qYaw).babylon();

        const stackLift = (stack | 0) * 0.00015;
        const w = Math.max(1e-5, lineWidth);

        // material
        if (!this._lineMat || this._lineMat.isDisposed) {
            this._lineMat = this._stdMat(`${this.id}_line`, lineColor);
        }
        const mat = this._lineMat;

        // Build/update label first to know its world width (for gap)
        const minH = Math.max(0, Number(labelMinWorldHeight ?? 0.02));
        const planeHSelected = (labelWorldHeight && labelWorldHeight > 0)
            ? labelWorldHeight
            : (w * (labelHeightFactor ?? 6.0));
        const planeH = Math.max(planeHSelected, minH);

        const midX = len * 0.5;
        const liftWorld = stackLift + Math.max(0, labelLift);

        const labelInfo = this._buildOrUpdateLabel({
            text: String(labelText ?? ""),
            color: labelColor,
            fontPx: labelFontSize | 0,
            heightWorld: planeH,
            liftWorld,
            midX,
            planeRotation: labelPlaneRotation,
            flipU: !!labelFlipU,
            flipV: !!labelFlipV,
            offsetZ: labelOffset ?? 0,
            bgColor: labelBgColor,
            bgAlpha: Number.isFinite(labelBgAlpha) ? labelBgAlpha : 1,
            bgRadius: Math.max(0, labelBgRadiusPx | 0),
            borderColor: labelBorderColor,
            borderAlpha: Math.max(0, Number(labelBorderAlpha ?? 0)),
            borderW: Math.max(0, labelBorderWidthPx | 0),
            resMul: Math.max(1, labelResolutionMultiplier | 0),
        }, root, fullRecreate) || {planeW: 0};

        // gap calculation (local X)
        const eps = 1e-6;
        let gapL = 0, gapR = 0, hasGap = false;
        if (labelMakesGap && this._labelPlane && this._labelPlane.isEnabled()) {
            const extra = Math.max(0, labelGapExtraWorld || 0);
            const half = (labelInfo.planeW * 0.5) + extra;
            gapL = Math.max(0, midX - half);
            gapR = Math.min(len, midX + half);
            hasGap = (gapR > gapL + eps) && ((gapR - gapL) < (len - eps));
        }

        // ---------- SOLID ----------
        if (lineStyle === "solid") {
            const mkTube = (name, path, existing) => {
                if (!existing || existing.isDisposed() || fullRecreate) {
                    existing?.dispose?.();
                    const t = MeshBuilder.CreateTube(
                        name,
                        {path, radius: Math.max(0.0005, w * 0.5), cap: Mesh.CAP_ALL, updatable: true},
                        this.scene
                    );
                    t.material = mat;
                    t.parent = root;
                    return t;
                } else {
                    MeshBuilder.CreateTube(name, {path, instance: existing});
                    existing.radius = Math.max(0.0005, w * 0.5);
                    return existing;
                }
            };

            if (hasGap) {
                // left
                if (gapL > eps) {
                    const pathA = [new Vector3(0, stackLift, 0), new Vector3(gapL, stackLift, 0)];
                    this._tubeA = mkTube(`${this.id}_tubeA`, pathA, this._tubeA);
                    this._tubeA.setEnabled(true);
                } else {
                    this._tubeA?.setEnabled(false);
                }
                // right
                if ((len - gapR) > eps) {
                    const pathB = [new Vector3(gapR, stackLift, 0), new Vector3(len, stackLift, 0)];
                    this._tubeB = mkTube(`${this.id}_tubeB`, pathB, this._tubeB);
                    this._tubeB.setEnabled(true);
                } else {
                    this._tubeB?.setEnabled(false);
                }
            } else {
                const path = [new Vector3(0, stackLift, 0), new Vector3(len, stackLift, 0)];
                this._tubeA = mkTube(`${this.id}_tubeA`, path, this._tubeA);
                this._tubeA.setEnabled(true);
                this._tubeB?.setEnabled(false);
            }

            this._disableDashPool();
            this._disableDotPool();
            return;
        }

        // Ensure prototypes exist & match radius
        const ensureDashProto = () => {
            const r = Math.max(0.0005, w * 0.5);
            if (!this._dashProto || this._dashProto.isDisposed()) {
                // Unit-length tube from x=0 → x=1 (so scaling.x controls dash length only)
                const path = [new Vector3(0, stackLift, 0), new Vector3(1, stackLift, 0)];
                this._dashProto = MeshBuilder.CreateTube(`${this.id}_dashProto`,
                    {path, radius: r, cap: Mesh.CAP_ALL, updatable: false}, this.scene);
                this._dashProto.material = mat;
                this._dashProto.parent = root;
                this._dashProto.setEnabled(false);
                this._dashProto.renderingGroupId = 0;
            } else {
                // update radius by recreating geometry if needed (simple approach: dispose & rebuild if radius changed a lot)
                // For robustness we just leave it; visual difference is minimal across small width changes per frame.
            }
        };
        const ensureDotProto = () => {
            const dia = Math.max(0.0005, (dotSize ?? this._autoDotParams(w).diameter));
            if (!this._dotProto || this._dotProto.isDisposed()) {
                this._dotProto = MeshBuilder.CreateSphere(`${this.id}_dotProto`,
                    {diameter: dia, segments: 8}, this.scene);
                this._dotProto.material = mat;
                this._dotProto.parent = root;
                this._dotProto.setEnabled(false);
                this._dotProto.renderingGroupId = 0;
            } else {
                // update size if needed by scaling prototype (instances inherit), keeping it simple:
                const s = dia / this._dotProto.getBoundingInfo().boundingBox.extendSize.x / 2 || 1;
                this._dotProto.scaling.set(s, s, s);
            }
        };

        // ---------- DASHED ----------
        if (lineStyle === "dashed") {
            const auto = this._autoDashParams(w);
            const D = Math.max(1e-4, dashSize ?? auto.dash);
            const G = Math.max(0, gapSize ?? auto.gap);

            ensureDashProto();

            // Compute segments and (re)use instance pool
            let cursor = 0;
            let need = 0;
            while (cursor < len - eps) {
                const segLen = Math.min(D, len - cursor);
                const segStart = cursor;
                const segEnd = cursor + segLen;

                const intersectsGap = hasGap && !(segEnd <= gapL || segStart >= gapR);
                if (!intersectsGap) need++;
                cursor += D + G;
            }
            this._ensureDashPool(need);

            // Write transforms
            cursor = 0;
            let idx = 0;
            while (cursor < len - eps) {
                const segLen = Math.min(D, len - cursor);
                const segStart = cursor;
                const segEnd = cursor + segLen;
                const intersectsGap = hasGap && !(segEnd <= gapL || segStart >= gapR);
                if (!intersectsGap) {
                    const inst = this._dashInstances[idx++];
                    inst.setEnabled(true);
                    // position at local X = segStart; proto spans [0..1] so scale X = segLen
                    inst.position.set(segStart, stackLift, 0);
                    inst.scaling.set(segLen, 1, 1); // scale along X only → radius preserved
                }
                cursor += D + G;
            }
            // disable leftovers
            for (; idx < this._dashInstances.length; idx++) this._dashInstances[idx].setEnabled(false);

            // hide solid & dots
            this._tubeA?.setEnabled(false);
            this._tubeB?.setEnabled(false);
            this._disableDotPool();
            return;
        }

        // ---------- DOTTED ----------
        if (lineStyle === "dotted") {
            const auto = this._autoDotParams(w);
            const step = Math.max(1e-4, dotStep ?? auto.step);
            const dia = Math.max(0.0005, dotSize ?? auto.diameter);

            ensureDotProto();

            // Count needed dots
            let d = 0, need = 0;
            while (d <= len + eps) {
                const insideGap = hasGap && d >= gapL && d <= gapR;
                if (!insideGap) need++;
                d += step;
            }
            this._ensureDotPool(need);

            // Place dots
            d = 0;
            let idx = 0;
            while (d <= len + eps) {
                const insideGap = hasGap && d >= gapL && d <= gapR;
                if (!insideGap) {
                    const inst = this._dotInstances[idx++];
                    inst.setEnabled(true);
                    inst.position.set(d, stackLift, 0);
                    // keep radius constant; proto already sized. If user overrides dotSize, adjust uniform scaling fast:
                    const scale = dia / (this._dotProto.metadata?.baseDia || dia);
                    inst.scaling.set(scale, scale, scale);
                }
                d += step;
            }
            for (; idx < this._dotInstances.length; idx++) this._dotInstances[idx].setEnabled(false);

            // hide solid & dashes
            this._tubeA?.setEnabled(false);
            this._tubeB?.setEnabled(false);
            this._disableDashPool();
            return;
        }
    }

    _ensureDashPool(n) {
        // Grow pool
        while (this._dashInstances.length < n) {
            const inst = this._dashProto.createInstance(`${this.id}_dash_${this._dashInstances.length}`);
            inst.parent = this._root;
            inst.material = this._lineMat;
            inst.setEnabled(false);
            inst.isPickable = false;
            inst.renderingGroupId = 0;
            this._dashInstances.push(inst);
        }
        // No shrink (avoid churn); extras are disabled each frame.
    }

    _disableDashPool() {
        for (const inst of this._dashInstances) inst.setEnabled(false);
    }

    _ensureDotPool(n) {
        // record base diameter for scaling math
        if (!this._dotProto.metadata) this._dotProto.metadata = {};
        if (!this._dotProto.metadata.baseDia) {
            const bb = this._dotProto.getBoundingInfo().boundingBox;
            this._dotProto.metadata.baseDia = (bb.maximumWorld.x - bb.minimumWorld.x);
        }
        while (this._dotInstances.length < n) {
            const inst = this._dotProto.createInstance(`${this.id}_dot_${this._dotInstances.length}`);
            inst.parent = this._root;
            inst.material = this._lineMat;
            inst.setEnabled(false);
            inst.isPickable = false;
            inst.renderingGroupId = 0;
            this._dotInstances.push(inst);
        }
    }

    _disableDotPool() {
        for (const inst of this._dotInstances) inst.setEnabled(false);
    }

    /* ----- label helpers (same as before) ----- */
    _buildOrUpdateLabel(opts, root, fullRecreate) {
        const {
            text, color, fontPx,
            heightWorld, liftWorld,
            midX, planeRotation,
            flipU, flipV,
            offsetZ = 0,
            bgColor, bgAlpha, bgRadius,
            borderColor, borderAlpha, borderW,
            resMul = 1,
        } = opts;

        if (!text || !text.trim()) {
            if (this._labelPlane) this._labelPlane.setEnabled(false);
            return {planeW: 0};
        }

        const pad = Math.max(0, this.config.labelPadPx | 0);
        const spec = {
            text,
            color: JSON.stringify(color ?? [1, 1, 1]),
            fontPx: fontPx | 0,
            pad,
            flips: `${flipU}|${flipV}`,
            bg: JSON.stringify(bgColor ?? [1, 1, 1]),
            bgalpha: Number(bgAlpha ?? 1).toFixed(3),
            bgradius: bgRadius | 0,
            border: JSON.stringify(borderColor ?? [0, 0, 0]),
            borderAlpha: Number(borderAlpha ?? 0).toFixed(3),
            borderW: borderW | 0,
            resMul: resMul | 0,
        };

        const sameSpec =
            this._lastLabelSpec.text === spec.text &&
            this._lastLabelSpec.color === spec.color &&
            this._lastLabelSpec.fontPx === spec.fontPx &&
            this._lastLabelSpec.pad === spec.pad &&
            this._lastLabelSpec.flips === spec.flips &&
            this._lastLabelSpec.bg === spec.bg &&
            this._lastLabelSpec.bgalpha === spec.bgalpha &&
            this._lastLabelSpec.bgradius === spec.bgradius &&
            this._lastLabelSpec.border === spec.border &&
            this._lastLabelSpec.borderAlpha === spec.borderAlpha &&
            this._lastLabelSpec.borderW === spec.borderW &&
            this._lastLabelSpec.resMul === spec.resMul;

        if (!sameSpec) {
            const fontPxClamped = Math.max(8, fontPx | 0);
            const font = `bold ${fontPxClamped}px Arial`;

            const ensureDT = () => {
                if (!this._labelDT || this._labelDT.isDisposed) {
                    this._labelDT = new DynamicTexture(
                        `labelDT_${this.id}`,
                        {width: 256, height: 128},
                        this.scene,
                        false,
                        Texture.NEAREST_NEAREST
                    );
                } else {
                    this._labelDT.updateSamplingMode(Texture.NEAREST_NEAREST);
                }
                this._labelDT.hasAlpha = true;
                this._labelDT.wrapU = Texture.CLAMP_ADDRESSMODE;
                this._labelDT.wrapV = Texture.CLAMP_ADDRESSMODE;
                return this._labelDT;
            };
            ensureDT();

            const ctxMeasure = this._labelDT.getContext();
            ctxMeasure.font = font;
            const metrics = ctxMeasure.measureText(text);
            const rawTextW = Math.max(1, metrics.width || (fontPxClamped * text.length * 0.6));
            const rawTextH = Math.max(fontPxClamped, Math.ceil(fontPxClamped * 1.2));

            const totalPad = pad + (borderW > 0 ? Math.ceil(borderW) : 0);
            const sizeW = Math.max(64, Math.ceil((rawTextW + totalPad * 2) * Math.max(1, resMul | 0)));
            const sizeH = Math.max(32, Math.ceil((rawTextH + totalPad * 2) * Math.max(1, resMul | 0)));

            this._labelDT.scaleTo(sizeW, sizeH);

            const ctx = this._labelDT.getContext();
            ctx.save();
            ctx.globalCompositeOperation = "copy";
            ctx.fillStyle = "rgba(0,0,0,0)";
            ctx.fillRect(0, 0, sizeW, sizeH);
            ctx.restore();

            ctx.font = font;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.lineJoin = "round";
            ctx.lineCap = "round";

            const toRGBA = (arr, a = 1) => {
                const r = Math.round(255 * (arr?.[0] ?? 1));
                const g = Math.round(255 * (arr?.[1] ?? 1));
                const b = Math.round(255 * (arr?.[2] ?? 1));
                const alpha = Math.max(0, Math.min(1, a));
                return `rgba(${r},${g},${b},${alpha})`;
            };

            const roundRect = (ctx, x, y, w, h, r) => {
                const radius = Math.max(0, Math.min(r, Math.min(w, h) * 0.5));
                ctx.beginPath();
                ctx.moveTo(x + radius, y);
                ctx.lineTo(x + w - radius, y);
                ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
                ctx.lineTo(x + w, y + h - radius);
                ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
                ctx.lineTo(x + radius, y + h);
                ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
                ctx.lineTo(x, y + radius);
                ctx.quadraticCurveTo(x, y, x + radius, y);
                ctx.closePath();
            };

            const inset = 0.5;
            const rectX = inset, rectY = inset;
            const rectW = sizeW - inset * 2, rectH = sizeH - inset * 2;

            roundRect(ctx, rectX, rectY, rectW, rectH, spec.bgradius | 0);
            ctx.fillStyle = toRGBA(JSON.parse(spec.bg), Number(spec.bgalpha));
            ctx.fill();

            if ((Number(spec.borderAlpha) ?? 0) > 0 && (spec.borderW ?? 0) > 0) {
                ctx.lineWidth = Math.max(1, spec.borderW | 0);
                ctx.strokeStyle = toRGBA(JSON.parse(spec.border), Number(spec.borderAlpha));
                const halfLW = ctx.lineWidth * 0.5;
                roundRect(ctx, rectX + halfLW, rectY + halfLW,
                    rectW - ctx.lineWidth, rectH - ctx.lineWidth,
                    Math.max(0, (spec.bgradius | 0) - halfLW));
                ctx.stroke();
            }

            const [tr, tg, tb] = Array.isArray(color) ? color : [0, 0, 0];
            ctx.fillStyle = `rgb(${Math.round(tr * 255)},${Math.round(tg * 255)},${Math.round(tb * 255)})`;
            ctx.fillText(text, sizeW / 2, sizeH / 2);

            this._labelDT.update();

            if (!this._labelMat || this._labelMat.isDisposed) {
                const m = new StandardMaterial(`labelMat_${this.id}`, this.scene);
                m.diffuseTexture = this._labelDT;
                m.emissiveTexture = this._labelDT;
                m.opacityTexture = this._labelDT;
                m.diffuseColor = Color3.White();
                m.emissiveColor = Color3.White();
                m.specularColor = Color3.Black();
                m.backFaceCulling = true;
                m.useAlphaFromDiffuseTexture = true;
                m.transparencyMode = Material.MATERIAL_ALPHABLEND;
                m.needDepthPrePass = true;
                m.forceDepthWrite = true;
                m.zOffset = -2;
                this._labelMat = m;
            } else {
                this._labelMat.diffuseTexture = this._labelDT;
                this._labelMat.emissiveTexture = this._labelDT;
                this._labelMat.opacityTexture = this._labelDT;
                this._labelMat.zOffset = -2;
            }

            const texs = [this._labelMat.diffuseTexture, this._labelMat.emissiveTexture, this._labelMat.opacityTexture];
            for (const t of texs) if (t) {
                t.uScale = flipU ? -1 : 1;
                t.vScale = flipV ? -1 : 1;
                t.wrapU = Texture.CLAMP_ADDRESSMODE;
                t.wrapV = Texture.CLAMP_ADDRESSMODE;
            }

            if (!this._labelPlane || this._labelPlane.isDisposed()) {
                this._labelPlane = MeshBuilder.CreatePlane(
                    `labelPlane_${this.id}`,
                    {width: 1, height: 1, sideOrientation: Mesh.DOUBLESIDE},
                    this.scene
                );
                this._labelPlane.parent = this._root;
                this._labelPlane.material = this._labelMat;
                this._labelPlane.isPickable = false;
                this._labelPlane.renderingGroupId = 2;

                const [rx, ry, rz] = Array.isArray(planeRotation) ? planeRotation : [Math.PI / 2, 0, 0];
                this._labelPlane.rotation = new Vector3(rx, ry, rz);
            } else {
                this._labelPlane.material = this._labelMat;
                this._labelPlane.renderingGroupId = 2;
            }

            this._lastLabelSpec = spec;
        }

        // scale & place plane using texture aspect
        let planeW = 0;
        if (this._labelPlane) {
            const texSize = this._labelDT?.getSize?.();
            const aspect = texSize ? (texSize.width / texSize.height) : 4;
            const planeH = heightWorld;
            planeW = Math.max(planeH * aspect, planeH * 0.5);
            this._labelPlane.scaling = new Vector3(planeW, planeH, 1);
            this._labelPlane.position = new Vector3(midX, liftWorld, offsetZ | 0);
            this._labelPlane.setEnabled(true);
        }
        return {planeW};
    }

    _isObj(v) {
        return v && typeof v === "object" && v instanceof BabylonObject;
    }

    _resolveRef(ref) {
        if (Array.isArray(ref)) {
            return ref.length === 2 ? [ref[0] ?? 0, ref[1] ?? 0, 0] : [ref[0] ?? 0, ref[1] ?? 0, ref[2] ?? 0];
        }
        if (this._isObj(ref)) {
            const p = ref.position ?? [0, 0, 0];
            if (Array.isArray(p)) {
                return p.length === 2 ? [p[0] ?? 0, p[1] ?? 0, 0] : [p[0] ?? 0, p[1] ?? 0, p[2] ?? 0];
            }
            if (p && typeof p === "object") {
                const x = "x" in p ? p.x : 0;
                const y = "y" in p ? p.y : 0;
                const z = "z" in p ? p.z : 0;
                return [x ?? 0, y ?? 0, z ?? 0];
            }
        }
        return [0, 0, 0];
    }
}


export class BabylonObjectLabeledLineDrawing extends BabylonLabeledLineDrawing {
    constructor(id, scene, payload = {}) {
        const safePayload = payload || {};
        safePayload.config = {...(safePayload.config || {})};
        super(id, scene, safePayload);

        this._obs = {start: null, end: null};
        this._retargetObservers();
        this._markDirty();
    }

    update(data = {}) {
        super.update(data);
        this._retargetObservers();
    }

    delete() {
        this._detach("start");
        this._detach("end");
        super.delete();
    }

    _retargetObservers() {
        this._attach("start", this.config?.start);
        this._attach("end", this.config?.end);
    }

    _attach(which, ref) {
        this._detach(which);
        if (this._isObj(ref) && ref.root?.onAfterWorldMatrixUpdateObservable) {
            this._obs[which] = ref.root.onAfterWorldMatrixUpdateObservable.add(() => {
                this._markDirty();
            });
        }
    }

    _detach(which) {
        const ref = this.config?.[which];
        if (this._obs?.[which] && this._isObj(ref) && ref.root?.onAfterWorldMatrixUpdateObservable) {
            ref.root.onAfterWorldMatrixUpdateObservable.remove(this._obs[which]);
        }
        if (this._obs) this._obs[which] = null;
    }

    _isObj(v) {
        return v && typeof v === "object" && v instanceof BabylonObject;
    }
}


/* ===== PATH DRAWING ===== */
export class BabylonPathDrawing extends BabylonDrawingObject {
    constructor(id, scene, payload = {}) {
        const defaults = {
            pathColor: [1, 1, 1, 0.95],
            pathWidth: 0.01,
            groundY: 0,
            lift: 0.001,
        };
        payload.config = {...defaults, ...(payload.config || {})};

        // points live in data so they can be streamed via update()
        const defaultData = {
            points: [],   // [[x,y], [x,y,z], …] in z-up coords
        };
        payload.data = {...defaultData, ...(payload.data || {})};

        super(id, scene, payload);
    }

    _applyCommon() {
        if (!this._root) return;
        for (const m of this._root.getChildMeshes()) {
            m.isPickable = !!this.config.pickable;
            m.metadata = m.metadata || {};
            m.metadata.object = this;
            m.renderingGroupId = 0;
        }
    }

    _build() {
        const pts = this.data.points;
        if (!pts || pts.length < 2) return;

        const {pathColor, pathWidth, groundY, lift} = this.config;
        const floorY = (groundY ?? 0) + (lift ?? 0);
        const halfW = Math.max(0.0005, pathWidth * 0.5);

        const {c3, a} = this._toC3a(pathColor);
        const mat = new StandardMaterial(`${this.id}_path_mat`, this.scene);
        mat.diffuseColor = c3.clone();
        mat.emissiveColor = c3.scale(0.6);
        mat.specularColor = Color3.Black();
        mat.alpha = a;
        mat.backFaceCulling = false;

        // Build one quad per segment to avoid twisting at corners
        for (let i = 0; i < pts.length - 1; i++) {
            const ax = pts[i][0] ?? 0;
            const ay = pts[i][1] ?? 0;
            const bx = pts[i + 1][0] ?? 0;
            const by = pts[i + 1][1] ?? 0;

            const dx = bx - ax;
            const dy = by - ay;
            const len = Math.max(1e-9, Math.hypot(dx, dy));
            // Perpendicular in z-up coords
            const nx = -dy / len * halfW;
            const ny = dx / len * halfW;

            const left = [
                coordinatesToBabylon([ax + nx, ay + ny, floorY]),
                coordinatesToBabylon([bx + nx, by + ny, floorY]),
            ];
            const right = [
                coordinatesToBabylon([ax - nx, ay - ny, floorY]),
                coordinatesToBabylon([bx - nx, by - ny, floorY]),
            ];

            const seg = MeshBuilder.CreateRibbon(
                `${this.id}_seg_${i}`,
                {pathArray: [left, right], sideOrientation: Mesh.DOUBLESIDE, updatable: false},
                this.scene
            );
            seg.material = mat;
            seg.parent = this._root;
        }
    }

    update(data = {}) {
        if (data.config) this.config = {...this.config, ...data.config};
        if (data.data) this.data = {...this.data, ...data.data};
        if (data.points) this.data.points = data.points;
        if (data.position) this.setPosition(data.position);
        this._disposeChildren();
        this._build();
        this._applyCommon();
    }
}


/* ===== POINTS DRAWING ===== */
export class BabylonPointsDrawing extends BabylonDrawingObject {
    constructor(id, scene, payload = {}) {
        const defaults = {
            fillColor: [1, 1, 1, 0.8],
            pointSize: 0.02,
            groundY: 0,
            lift: 0.002,
        };
        payload.config = {...defaults, ...(payload.config || {})};

        const defaultData = {
            points: [],
        };
        payload.data = {...defaultData, ...(payload.data || {})};

        super(id, scene, payload);
    }

    _applyCommon() {
        if (!this._root) return;
        for (const m of this._root.getChildMeshes()) {
            m.isPickable = !!this.config.pickable;
            m.metadata = m.metadata || {};
            m.metadata.object = this;
        }
    }

    _build() {
        const pts = this.data.points;
        if (!pts || pts.length === 0) return;

        const {fillColor, pointSize, groundY, lift} = this.config;
        const floorY = (groundY ?? 0) + (lift ?? 0);
        const radius = Math.max(0.001, pointSize * 0.5);

        // Fill material (translucent)
        const fillMat = this._makeTranslucentMat(`${this.id}_fill`, fillColor);

        // Fill template disc
        const fillTemplate = MeshBuilder.CreateDisc(
            `${this.id}_fill_tmpl`,
            {radius, tessellation: 24, sideOrientation: Mesh.DOUBLESIDE},
            this.scene
        );
        fillTemplate.material = fillMat;
        fillTemplate.isVisible = false;
        fillTemplate.rotation.x = Math.PI / 2;
        fillTemplate.parent = this._root;

        // Instance fill at each point
        for (let i = 0; i < pts.length; i++) {
            const p = pts[i];
            const pos = coordinatesToBabylon([p[0] ?? 0, p[1] ?? 0, floorY]);

            const fillInst = fillTemplate.createInstance(`${this.id}_f_${i}`);
            fillInst.position = pos;
            fillInst.parent = this._root;
        }
    }

    _makeTranslucentMat(id, rgba) {
        const [r, g, b, a = 1] = rgba || [1, 1, 1, 1];
        const col = new Color3(r, g, b);
        const mat = new StandardMaterial(`${id}_mat`, this.scene);
        mat.diffuseColor = col.clone();
        mat.emissiveColor = col.scale(0.6);
        mat.specularColor = Color3.Black();
        mat.alpha = a;
        mat.transparencyMode = Material.MATERIAL_ALPHABLEND;
        mat.disableDepthWrite = true;
        mat.needDepthPrePass = false;
        mat.forceDepthWrite = false;
        mat.backFaceCulling = false;
        return mat;
    }

    update(data = {}) {
        if (data.config) this.config = {...this.config, ...data.config};
        if (data.data) this.data = {...this.data, ...data.data};
        if (data.points) this.data.points = data.points;
        if (data.position) this.setPosition(data.position);
        this._disposeChildren();
        this._build();
        this._applyCommon();
    }
}