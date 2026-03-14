import {BabylonObject} from "../../objects.js";
import {CreateBox, StandardMaterial, Texture} from "@babylonjs/core";
import {coordinatesToBabylon, getBabylonColor, getBabylonColor3, loadTexture} from "../../babylon_utils.js";
import {Quaternion} from '../../quaternion.js'


// https://playground.babylonjs.com/#PCWRFE


/* === BABYLON BOX ================================================================================================== */
export class BabylonBox extends BabylonObject {
    constructor(id, scene, payload = {}) {
        super(id, scene, payload);

        const default_config = {
            visible: true,
            color: [0.5, 0.5, 0.5],
            texture: '',
            texture_uscale: 1,
            texture_vscale: 1,
            wireframe: false,
            wireframe_width: 0.75,
            wireframe_color: [1, 0, 0, 1],
            alpha: 1,
            size: {
                x: 1,
                y: 1,
                z: 1,
            },
            accept_shadows: true,
        }
        this.config = {...default_config, ...this.config};

        const default_data = {
            position: [0, 0, 0],
            orientation: [1, 0, 0, 0],
        }

        this.data = {...default_data, ...this.data};

        this.buildObject();

    }

    buildObject() {
        this.mesh = CreateBox('box', {
            height: this.config.size.z,
            width: this.config.size.x,
            depth: this.config.size.y
        }, this.scene);


        this.mesh.parent = this.root;

        // # --- Material ----------------
        this.material = new StandardMaterial(this.scene);

        if (this.config.texture) {
            const tex = loadTexture(this.config.texture);
            this.material.diffuseTexture = new Texture(tex, this.scene);
            this.material.diffuseTexture.uScale = this.config.texture_uscale;
            this.material.diffuseTexture.vScale = this.config.texture_vscale;
            this.material.specularColor = getBabylonColor3([0, 0, 0]);
        } else {
            this.material.diffuseColor = getBabylonColor3(this.config.color);
        }

        this.mesh.material = this.material;
        this.mesh.material.alpha = this.config.alpha;

        if (this.config.wireframe) {
            this.mesh.enableEdgesRendering();
            this.mesh.edgesWidth = this.config.wireframe_width;
            this.mesh.edgesColor = getBabylonColor(this.config.wireframe_color);
        }


        // --- SHADOW ---
        this.scene.shadowGenerator.addShadowCaster(this.mesh);
        this.mesh.acceptShadows = this.config.accept_shadows;


        // --- PICKING ---
        this.mesh.isPickable = false;
        this.mesh.metadata = {};
        this.mesh.metadata.object = this;

        this.onBuilt();

        this.setPosition(this.data.position);
        this.setOrientation(this.data.orientation);

    }

    highlight(state) {
        return undefined;
    }

    onMessage(message) {
        return undefined;
    }

    update(data) {
        const position = data.position || this.data.position;
        const orientation = data.orientation || this.data.orientation;
        this.setPosition(position);
        this.setOrientation(orientation);
    }

    delete() {
        this.mesh.dispose();
    }

    dim(state) {
        return undefined;
    }

}


/* === BABYLON WALL ================================================================================================= */
export class BabylonWall extends BabylonBox {
    constructor(id, scene, payload = {}) {
        const incoming = (payload && payload.config) ? payload.config : {};

        // Defaults specific to walls
        const wall_defaults = {
            length: 1,           // along X
            height: 0.25,        // along Z (up)
            thickness: 0.05,     // along Y (depth)
            include_end_caps: false, // adds one thickness to each end
            auto_texture_uscale: true
        };

        // Merge user config with defaults (wall-specific first; BabylonBox will add its own defaults later)
        const merged = {...wall_defaults, ...incoming};

        // Prefer new names (length/height/thickness); fall back to size.{x,y,z} if provided
        const length = (merged.length != null) ? merged.length : (incoming.size?.x ?? wall_defaults.length);
        const height = (merged.height != null) ? merged.height : (incoming.size?.z ?? wall_defaults.height);
        const thickness = (merged.thickness != null) ? merged.thickness : (incoming.size?.y ?? wall_defaults.thickness);

        // Add end caps (one thickness per end)
        const effectiveLength = length + (merged.include_end_caps ? 1 * thickness : 0);

        // Build the config that BabylonBox expects
        const boxConfig = {
            ...incoming,
            // Map to BabylonBox "size": x=length, y=thickness, z=height
            size: {
                x: effectiveLength,
                y: thickness,
                z: height
            }
        };

        // Automatic texture uScale: base on height, then scale across length (keeps texels roughly square).
        // Only set if user didn't explicitly provide texture_uscale.
        if (boxConfig.texture && merged.auto_texture_uscale !== false &&
            (incoming.texture_uscale === undefined || incoming.texture_uscale === null)) {
            boxConfig.texture_uscale = effectiveLength / height;
        }

        // Pass rebuilt config down to BabylonBox
        super(id, scene, {...payload, config: boxConfig});

        this.mesh.receiveShadows = true;
        // this.mesh.receiveShadows = true;
    }

    /**
     * Position is specified by the *bottom* of the wall:
     *   [x, y, zBottom]  -> internally shifted by +height/2 on Z.
     */
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

        this.basePosition = coords; // store the bottom anchor the user provided
        const height = this.config?.size?.z || 0;
        const center = [coords[0], coords[1], coords[2] + height / 2];

        // Use BabylonBox positioning (handles coordinatesToBabylon, metadata, etc.)
        return super.setPosition(center);
    }
}


/* === BABYLON WALL FANCY ============================================================================================ *
 * Adds subtle “structure” without changing how you use BabylonWall:
 * - Bottom-anchored positioning (inherits from BabylonWall)
 * - Optional edge highlight (thin outline to pop the silhouette)
 * - Normal map + (optional) parallax occlusion for depth from textures
 * - Optional top/bottom caps (slight overhang) for visual richness
 * - Keeps auto texture scaling from BabylonWall
 * ------------------------------------------------------------------------------------------------------------------ */
export class BabylonWall_Fancy extends BabylonWall {
    constructor(id, scene, payload = {}) {
        // Pass through to BabylonWall to build the base wall (length/height/thickness, include_end_caps, etc.)
        super(id, scene, payload);

        // Enhancement defaults (can be overridden via payload.config)
        const defaults = {
            // Silhouette/edge pop (independent of "wireframe")
            edge_highlight: true,
            edge_width: 0.6,
            edge_color: [0, 0, 0, 0.35], // RGBA

            // Surface detail
            normal_map: '',               // e.g., 'wood4_n.png' (tangent-space normal map)
            bump_uscale_matches_diffuse: true,
            use_parallax: false,          // set true for height-based depth; needs a height-compatible normal map
            use_parallax_occlusion: false,// stronger but heavier than simple parallax
            parallax_scale_bias: 0.03,    // tune depth; ~0.02–0.06 works well
            specular_power: 128,          // tighter highlights (StandardMaterial)

            // Decorative caps (subtle top/bottom strips to break flatness)
            cap_top_enabled: true,
            cap_top_height: 0.02,         // meters
            cap_top_overhang: 0.005,      // extends length/thickness slightly
            cap_top_texture: '',          // default: reuse wall texture

            cap_bottom_enabled: false,
            cap_bottom_height: 0.02,
            cap_bottom_overhang: 0.005,
            cap_bottom_texture: '',

            // Shadow reception for the extra pieces
            caps_accept_shadows: true,
        };

        const cfg = {...defaults, ...(payload?.config || {})};

        // --- 1) Edge highlight (subtle outline to accent form) ---
        if (cfg.edge_highlight && !this.config.wireframe) {
            this.mesh.enableEdgesRendering();
            this.mesh.edgesWidth = cfg.edge_width;
            this.mesh.edgesColor = getBabylonColor(cfg.edge_color);
        }

        // --- 2) Surface detail: normal map + optional parallax ---
        // Reuse the base StandardMaterial created by BabylonBox/BabylonWall
        if (cfg.normal_map) {
            try {
                const bumpTex = new Texture(loadTexture(cfg.normal_map), this.scene);
                this.material.bumpTexture = bumpTex;

                // Match tiling with the diffuse map unless overridden
                if (cfg.bump_uscale_matches_diffuse && this.material.diffuseTexture) {
                    bumpTex.uScale = this.material.diffuseTexture.uScale;
                    bumpTex.vScale = this.material.diffuseTexture.vScale;
                    bumpTex.uOffset = this.material.diffuseTexture.uOffset || 0;
                    bumpTex.vOffset = this.material.diffuseTexture.vOffset || 0;
                }

                // Height-from-normal parallax
                if (cfg.use_parallax || cfg.use_parallax_occlusion) {
                    this.material.useParallax = !!cfg.use_parallax;
                    this.material.useParallaxOcclusion = !!cfg.use_parallax_occlusion;
                    this.material.parallaxScaleBias = cfg.parallax_scale_bias;
                }
            } catch (e) {
                // If loading fails, just continue without a bump map
            }
        }

        // Slightly tighter specular to avoid flat look on wood/paint
        if ('specular_power' in cfg && this.material) {
            this.material.specularPower = cfg.specular_power;
            // keep specularColor subtle; StandardMaterial defaults can be a bit strong with normal maps
            if (this.material.specularColor) {
                // leave as-is if user supplied; otherwise nudge to a dim value
            } else {
                this.material.specularColor = getBabylonColor3([0.08, 0.08, 0.08]);
            }
        }

        // --- 3) Decorative caps (top/bottom “molding”) ---
        // These are thin child meshes, so they inherit rotation/position automatically
        const L = this.config.size.x; // length (X)
        const T = this.config.size.y; // thickness (Y/depth)
        const H = this.config.size.z; // height (Z/up in your coords)

        const addCap = (which) => {
            const isTop = which === 'top';
            const enabled = isTop ? cfg.cap_top_enabled : cfg.cap_bottom_enabled;
            if (!enabled) return;

            const capHeight = isTop ? cfg.cap_top_height : cfg.cap_bottom_height;
            const capOverhang = isTop ? cfg.cap_top_overhang : cfg.cap_bottom_overhang;
            const capTexture = isTop ? cfg.cap_top_texture : cfg.cap_bottom_texture;

            // Create a thin box as the cap
            const cap = CreateBox(`wall2_cap_${which}_${this.id}`, {
                // Remember BabylonBox mapping: width -> x, depth -> y, height -> z
                width: L + 2 * capOverhang,
                depth: T + 2 * capOverhang,
                height: capHeight,
            }, this.scene);

            // Material for the cap: reuse wall material but allow a different texture if provided
            const capMat = new StandardMaterial(this.scene);
            if (capTexture) {
                const tex = loadTexture(capTexture);
                capMat.diffuseTexture = new Texture(tex, this.scene);
                // Keep tiling coherent with the wall (based on height for square-ish texels)
                const uScale = (L + 2 * capOverhang) / capHeight;
                const vScale = (T + 2 * capOverhang) / capHeight;
                capMat.diffuseTexture.uScale = uScale;
                capMat.diffuseTexture.vScale = vScale;
                capMat.specularColor = getBabylonColor3([0, 0, 0]);
            } else {
                // Subtly darker tone of the wall color/texture
                if (this.material.diffuseTexture) {
                    capMat.diffuseTexture = this.material.diffuseTexture;
                } else {
                    const base = this.config.color || [0.5, 0.5, 0.5];
                    const darker = base.map((c, i) => i < 3 ? Math.max(0, c * 0.9) : c);
                    capMat.diffuseColor = getBabylonColor3(darker);
                }
            }
            capMat.alpha = this.material.alpha ?? 1;
            cap.material = capMat;

            // Parent to the wall, so it follows rotations/positioning
            cap.parent = this.mesh;

            // Local offset: Y-up in Babylon, Z-up in your coords => use coordinatesToBabylon([0,0,z])
            // Top cap sits above the wall; bottom cap sits below.
            const zOffset = (H / 2) + (capHeight / 2);
            cap.position = coordinatesToBabylon([0, 0, isTop ? zOffset : -zOffset]);

            // Picking and metadata consistent with base mesh
            cap.isPickable = false;
            cap.metadata = {parent: this.mesh, wallCap: which, object: this};

            // Shadows
            try {
                if (cfg.caps_accept_shadows && this.scene.shadowGenerator) {
                    this.scene.shadowGenerator.addShadowCaster(cap);
                }
                cap.acceptShadows = !!cfg.caps_accept_shadows;
            } catch (_) {
                // ignore if no shadow generator
            }

            // Soft outline on caps too, to match main wall
            if (cfg.edge_highlight) {
                cap.enableEdgesRendering();
                cap.edgesWidth = cfg.edge_width;
                cap.edgesColor = getBabylonColor(cfg.edge_color);
            }

            // Keep references in case you want to tweak later
            if (isTop) this.capTop = cap;
            else this.capBottom = cap;
        };

        addCap('top');
        addCap('bottom');
        this.onBuilt();
    }
}