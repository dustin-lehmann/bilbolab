import {BabylonObject} from '../../objects.js';
import {adjustMaterialBrightness, getBabylonColor3, loadTexture} from "../../babylon_utils.js";
import {
    CreateTiledGround,
    StandardMaterial,
    Texture,
    MultiMaterial,
    SubMesh,
    MeshBuilder,
    Vector3, Color3,
    DynamicTexture
} from "@babylonjs/core";

// =====================================================================================================================
// export class BabylonSimpleFloor extends BabylonObject {
//     constructor(id, scene, payload = {}) {
//         super(id, scene, payload);
//
//         const defaultConfig = {
//             size_x: 5,          // total width of the floor (X axis, meters or units)
//             size_y: 5,          // total height/depth of the floor (Z axis)
//             tile_size: 0.5,     // desired size of a single tile (square)
//             texture: 'floor_bright.png', // URL or path to a texture image
//             color: [0.7, 0.7, 0.7],      // fallback diffuse color
//         };
//
//         this.config = {...defaultConfig, ...this.config};
//
//         // Compute how many tiles we want along each axis.
//         // We round to the nearest integer so tiles align nicely with size.
//         const tilesX = Math.max(1, Math.round(this.config.size_x / this.config.tile_size));
//         const tilesY = Math.max(1, Math.round(this.config.size_y / this.config.tile_size));
//
//         // NOTE: In Babylon, CreateGround's `subdivisions` only affects geometry density,
//         // not UVs/texture repetition. We still set it based on the max tile count so
//         // the mesh is reasonably dense (helps with lighting/shadows).
//         const subdivisions = Math.max(tilesX, tilesY);
//
//         // Create a simple ground mesh
//         this.mesh = MeshBuilder.CreateGround(
//             id + '_ground',
//             {
//                 width: this.config.size_x,
//                 height: this.config.size_y,
//                 subdivisions,       // geometry density only; does NOT control texture tiling
//                 updatable: false,
//             },
//             this.scene
//         );
//
//         // Create material
//         const mat = new StandardMaterial(id + '_mat', this.scene);
//         mat.specularColor = new Color3(0, 0, 0);              // no specular highlights
//         mat.emissiveColor = new Color3(0, 0, 0);              // keep shadows visible
//         // (Backface culling on by default; fine for a ground plane)
//         // mat.backFaceCulling = true;
//
//         if (this.config.texture) {
//             const texUrl = loadTexture(this.config.texture);
//             const tex = new Texture(texUrl, this.scene);
//             // Ensure tiling mode is wrapping (repeat)
//             tex.wrapU = Texture.WRAP_ADDRESSMODE;
//             tex.wrapV = Texture.WRAP_ADDRESSMODE;
//
//             // **This is the key:** tile the texture across the ground by scaling UVs.
//             // One repeat per tile along each axis.
//             tex.uScale = tilesX;
//             tex.vScale = tilesY;
//
//             // Optional: if your texture looks vertically flipped, uncomment the next line:
//             // tex.vScale = -tilesY;
//
//             mat.diffuseTexture = tex;
//         } else {
//             // Fallback solid color if no texture provided
//             mat.diffuseColor = getBabylonColor3(this.config.color);
//         }
//
//         this.mesh.material = mat;
//         this.mesh.isPickable = false;
//
//         // Receive shadows
//         this.mesh.receiveShadows = true;
//
//         // Store a couple of things in case you want to query/update later
//         this._tilesX = tilesX;
//         this._tilesY = tilesY;
//     }
//
//     highlight(state) {
//         // optional highlight implementation
//     }
//
//     onMessage(message) {
//         // optional message handling
//     }
//
//     setOrientation(orientation) {
//         // optional orientation handling
//     }
//
//     setPosition(position) {
//         if (Array.isArray(position)) {
//             this.mesh.position = new Vector3(...position);
//         } else if (position instanceof Vector3) {
//             this.mesh.position = position;
//         }
//     }
//
//     update(data) {
//         // optional update implementation
//         // If you ever add dynamic resizing, remember:
//         // - Recompute tilesX/tilesY from size_x/size_y/tile_size
//         // - Update mat.diffuseTexture.uScale / vScale
//         // - Rebuild the ground if width/height change (or create as updatable)
//     }
//
//     delete() {
//         this.mesh.dispose();
//     }
//
//     dim(state) {
//         return undefined;
//     }
//
//     buildObject() {
//         return undefined;
//     }
// }

export class BabylonSimpleFloor extends BabylonObject {
    constructor(id, scene, payload = {}) {
        super(id, scene, payload);

        const defaultConfig = {
            size_x: [-2.5, 2.5],  // [min, max] range in meters, or scalar for centered floor
            size_y: [-2.5, 2.5],  // [min, max] range in meters, or scalar for centered floor
            tile_size: 0.5,       // desired size of a single tile
            texture: 'floor_bright.png',
            color: [0.7, 0.7, 0.7],
        };

        this.config = { ...defaultConfig, ...this.config };

        // Normalize size_x and size_y to [min, max] format
        // Supports both scalar (legacy: centered at origin) and array [min, max] formats
        if (!Array.isArray(this.config.size_x)) {
            const half = this.config.size_x / 2;
            this.config.size_x = [-half, half];
        }
        if (!Array.isArray(this.config.size_y)) {
            const half = this.config.size_y / 2;
            this.config.size_y = [-half, half];
        }

        // Compute actual dimensions from ranges
        const widthX = this.config.size_x[1] - this.config.size_x[0];
        const widthY = this.config.size_y[1] - this.config.size_y[0];

        const tilesX = Math.max(1, Math.round(widthX / this.config.tile_size));
        const tilesY = Math.max(1, Math.round(widthY / this.config.tile_size));
        const subdivisions = Math.max(tilesX, tilesY);

        this.mesh = MeshBuilder.CreateGround(
            id + '_ground',
            {
                width: widthX,
                height: widthY,
                subdivisions,
                updatable: false,
            },
            this.scene
        );

        // ----- MATERIAL -----
        const mat = new StandardMaterial(id + '_mat', this.scene);
        mat.specularColor = new Color3(0, 0, 0);
        mat.emissiveColor = new Color3(0, 0, 0);

        if (this.config.texture) {
            const texUrl = loadTexture(this.config.texture);
            const tex = new Texture(texUrl, this.scene);

            tex.wrapU = Texture.WRAP_ADDRESSMODE;
            tex.wrapV = Texture.WRAP_ADDRESSMODE;
            tex.uScale = tilesX;
            tex.vScale = tilesY;

            mat.diffuseTexture = tex;
        } else {
            mat.diffuseColor = getBabylonColor3(this.config.color);
        }

        this.mesh.material = mat;
        this.mesh.isPickable = false;
        this.mesh.receiveShadows = true;
        this.mesh.parent = this.root;

        // ----- POSITION / OFFSET HANDLING -----
        this._applyOriginAndOffset();

        this._tilesX = tilesX;
        this._tilesY = tilesY;
    }

    /**
     * Computes mesh position based on the size ranges.
     * The mesh center is placed at the center of the range.
     */
    _applyOriginAndOffset() {
        // Center of the floor is the midpoint of each range
        const centerX = (this.config.size_x[0] + this.config.size_x[1]) / 2;
        const centerY = (this.config.size_y[0] + this.config.size_y[1]) / 2;

        // In Babylon, Y maps to world Z (with negation for coordinate system)
        this.mesh.position.set(centerX, 0, -centerY);
    }

    highlight(state) {}

    onMessage(message) {}

    setOrientation(orientation) {}

    setPosition(position) {
        if (Array.isArray(position)) {
            this.mesh.position = new Vector3(...position);
        } else if (position instanceof Vector3) {
            this.mesh.position = position;
        }
    }

    update(data) {}

    delete() {
        this.mesh.dispose();
    }

    dim(state) {
        return undefined;
    }

    buildObject() {
        return undefined;
    }
}

// =====================================================================================================================
export class BabylonFloorInstanced extends BabylonObject {
    constructor(id, scene, payload = {}) {
        super(id, scene, payload);

        const defaultConfig = {
            tile_size: 0.5,
            tiles_x: 10,
            tiles_y: 10,
            offset: [0, 0],
            color1: [0.5, 0.5, 0.5],
            color2: [0.65, 0.65, 0.65],
            texture_1: 'drawing_board.png',
            texture_2: 'drawing_board.png',
            brightness_1: 1,
            brightness_2: 0.9,
            border_type: 'line', // null, 'line', or 'tile'
            border_color: [0.4, 0.4, 0.4],
            border_width: 0.025,
            border_texture: 'floor_bright.png',
            border_texture_brightness: 0.6
        };

        this.config = {...defaultConfig, ...this.config};
        const {tile_size, tiles_x, tiles_y} = this.config;
        const offsetX = this.config.offset[0] || 0;
        const offsetZ = -(this.config.offset[1] || 0);

        // --- Create materials ---
        this.material1 = new StandardMaterial(id + '_mat1', this.scene);
        if (this.config.texture_1) {
            const tex1 = loadTexture(this.config.texture_1);
            this.material1.diffuseTexture = new Texture(tex1, this.scene);
        } else {
            this.material1.diffuseColor = getBabylonColor3(this.config.color1);
        }
        this.material1.specularColor = getBabylonColor3([0, 0, 0]);
        adjustMaterialBrightness(this.material1, this.config.brightness_1);

        this.material2 = new StandardMaterial(id + '_mat2', this.scene);
        if (this.config.texture_2) {
            const tex2 = loadTexture(this.config.texture_2);
            this.material2.diffuseTexture = new Texture(tex2, this.scene);
        } else {
            this.material2.diffuseColor = getBabylonColor3(this.config.color2);
        }
        this.material2.specularColor = getBabylonColor3([0, 0, 0]);
        adjustMaterialBrightness(this.material2, this.config.brightness_2);

        if (this.config.border_type === 'tile') {
            this.borderMaterial = new StandardMaterial(id + '_mat_border', this.scene);
            if (this.config.border_texture) {
                const texB = loadTexture(this.config.border_texture);
                this.borderMaterial.diffuseTexture = new Texture(texB, this.scene);
            } else {
                this.borderMaterial.diffuseColor = getBabylonColor3(this.config.border_color);
            }
            this.borderMaterial.specularColor = getBabylonColor3([0, 0, 0]);
            adjustMaterialBrightness(this.borderMaterial, this.config.border_texture_brightness);
        }

        // --- Create invisible base tile meshes (flat on XZ plane) ---
        this.baseTiles = {};
        const createBase = (name, material) => {
            const mesh = MeshBuilder.CreateGround(
                id + '_' + name,
                {width: tile_size, height: tile_size},
                this.scene
            );
            mesh.material = material;
            mesh.isVisible = false;
            mesh.receiveShadows = true;
            mesh.isPickable = false;
            return mesh;
        };

        this.baseTiles.mat1 = createBase('template1', this.material1);
        this.baseTiles.mat2 = createBase('template2', this.material2);
        if (this.config.border_type === 'tile') {
            this.baseTiles.border = createBase('templateBorder', this.borderMaterial);
        }

        // --- Instance tiles in a grid ---
        this.tiles = [];
        for (let r = 0; r < tiles_y; r++) {
            this.tiles[r] = [];
            for (let c = 0; c < tiles_x; c++) {
                const isBorder = r === 0 || r === tiles_y - 1 || c === 0 || c === tiles_x - 1;
                let sourceMesh;
                if (this.config.border_type === 'tile' && isBorder) {
                    sourceMesh = this.baseTiles.border;
                } else {
                    sourceMesh = ((r + c) % 2 === 0)
                        ? this.baseTiles.mat1
                        : this.baseTiles.mat2;
                }

                const inst = sourceMesh.createInstance(id + `_tile_${c}_${r}`);
                // Map grid x->world x, grid y->world -z
                inst.isPickable = false;
                inst.position.x = (c - tiles_x / 2 + 0.5) * tile_size + offsetX;
                inst.position.z = -(r - tiles_y / 2 + 0.5) * tile_size + offsetZ;
                this.tiles[r][c] = inst;
            }
        }

        // --- Optional line border ---
        if (this.config.border_type === 'line') {
            const halfX = tile_size * tiles_x / 2;
            const halfZ = tile_size * tiles_y / 2;
            const path = [
                new Vector3(-halfX + offsetX, 0.01, -halfZ + offsetZ),
                new Vector3(halfX + offsetX, 0.01, -halfZ + offsetZ),
                new Vector3(halfX + offsetX, 0.01, halfZ + offsetZ),
                new Vector3(-halfX + offsetX, 0.01, halfZ + offsetZ),
                new Vector3(-halfX + offsetX, 0.01, -halfZ + offsetZ)
            ];
            const borderTube = MeshBuilder.CreateTube(
                id + '_borderTube',
                {path, radius: this.config.border_width / 2, sideOrientation: MeshBuilder.DOUBLESIDE},
                this.scene
            );
            const tubeMat = new StandardMaterial(id + '_borderLineMat', this.scene);
            tubeMat.diffuseColor = getBabylonColor3(this.config.border_color);
            tubeMat.emissiveColor = getBabylonColor3(this.config.border_color);
            tubeMat.specularColor = getBabylonColor3([0, 0, 0]);
            borderTube.material = tubeMat;
        }
    }

    /**
     * Toggle visibility of the tile at grid coords (x,y).
     * Here y in grid maps to -z in world.
     * @param {number} x - Column (0..tiles_x-1)
     * @param {number} y - Row (0..tiles_y-1)
     * @param {boolean} state - true = visible, false = hidden
     */
    setTileVisibility(x, y, state) {
        if (y < 0 || y >= this.tiles.length) return;
        const row = this.tiles[y];
        if (!row || x < 0 || x >= row.length) return;
        row[x].isVisible = state;
    }

    /**
     * Show or hide the entire floor (all tiles and base meshes).
     * @param {boolean} visible
     */
    setVisibility(visible) {
        this.visible = visible;
        const state = !!visible;
        // Toggle tile instances (InstancedMesh needs setEnabled)
        for (const row of this.tiles) {
            for (const tile of row) {
                tile.setEnabled(state);
            }
        }
        // Toggle base tile templates
        if (this.baseTiles) {
            for (const mesh of Object.values(this.baseTiles)) {
                if (mesh) mesh.setEnabled(state);
            }
        }
    }

    highlight(state) {
        return undefined;
    }

    onMessage(message) {
        return undefined;
    }

    setOrientation(orientation) {
        return undefined;
    }

    setPosition(position) {
        return undefined;
    }

    update(data) {
        return undefined;
    }

    dim(state) {
        return undefined;
    }

    delete() {
        this.mesh.dispose();
    }
}


