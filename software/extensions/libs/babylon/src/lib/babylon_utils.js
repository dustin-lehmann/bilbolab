import * as BABYLON from "@babylonjs/core";
import {Color3, StandardMaterial, Engine, Scene as BScene} from "@babylonjs/core";

const TEXTURE_PATH_IN_PUBLIC = '/textures/'
const MODEL_PATH_IN_PUBLIC = 'models/'


export class Scene {
    constructor(canvasOrEngine) {
        this.engineIsShared = canvasOrEngine instanceof Engine;
        if (this.engineIsShared) {
            this.engine = canvasOrEngine;
            this.canvas = this.engine.getRenderingCanvas();
        } else {
            this.canvas = typeof canvasOrEngine === "string"
                ? document.getElementById(canvasOrEngine)
                : canvasOrEngine;
            this.engine = new Engine(this.canvas, true);
        }

        this.scene = new BScene(this.engine);
        this.scene.useRightHandedSystem = true;

        if (!this.engineIsShared) {
            this.engine.runRenderLoop(() => this.scene.render());
            window.addEventListener("resize", () => this.engine.resize());
        }
    }
}

// ---------------------------------------------------------------------------------------------------------------------
export function coordinatesToBabylon(coordinates) {
    if (Array.isArray(coordinates)) {
        return new BABYLON.Vector3(coordinates[0], coordinates[2], -coordinates[1]);
    } else if (coordinates && typeof coordinates === 'object' &&
        'x' in coordinates && 'y' in coordinates && 'z' in coordinates) {
        return new BABYLON.Vector3(coordinates.x, coordinates.z, -coordinates.y);
    } else {
        throw new Error('Invalid coordinates: must be an array or a Vector3-like object');
    }
}

// ---------------------------------------------------------------------------------------------------------------------
export function coordinatesFromBabylon(coordinates) {
    if ((coordinates instanceof BABYLON.Vector3)) {
        return [coordinates.x, -coordinates.z, coordinates.y];
    } else if (Array.isArray(coordinates)) {
        return [coordinates[0], -coordinates[2], coordinates[1]];
    } else {
        console.error('Invalid coordinates:', coordinates);
        return coordinates;
    }

}

// ---------------------------------------------------------------------------------------------------------------------
export function getBabylonColor3(color) {
    const [r, g, b] = color;
    return new BABYLON.Color3(r, g, b);
}

// ---------------------------------------------------------------------------------------------------------------------
export function getBabylonColor(color) {
    const [r, g, b, a = 1] = color;
    return new BABYLON.Color4(r, g, b, a);
}

// ---------------------------------------------------------------------------------------------------------------------
export function getHTMLColor(color) {
    const color_array = _getColor(color);
    return `rgba(${color_array.r}, ${color_array.g}, ${color_array.b}, ${color_array.a})`;
}

// ---------------------------------------------------------------------------------------------------------------------
function _getColor(color) {
    if (Array.isArray(color)) {
        // Python-style [r, g, b] or [r, g, b, a] with 0–1 values
        const [r, g, b, a = 1] = color;
        return {
            r: Math.round(r * 255),
            g: Math.round(g * 255),
            b: Math.round(b * 255),
            a: a
        };
    } else if (typeof color === 'string') {
        if (color === 'transparent') {
            return {r: 0, g: 0, b: 0, a: 0};
        }
        if (color.startsWith('#')) {

            let r, g, b, a = 1;
            if (color.length === 4) {
                // #rgb shorthand
                r = parseInt(color[1] + color[1], 16);
                g = parseInt(color[2] + color[2], 16);
                b = parseInt(color[3] + color[3], 16);
            } else if (color.length === 7) {
                // #rrggbb
                r = parseInt(color.slice(1, 3), 16);
                g = parseInt(color.slice(3, 5), 16);
                b = parseInt(color.slice(5, 7), 16);
            }
            return {r, g, b, a};
        } else if (color.startsWith('rgb')) {
            const match = color.match(/rgba?\(([^)]+)\)/);
            if (match) {
                const parts = match[1].split(',').map(x => parseFloat(x.trim()));
                const [r, g, b, a = 1] = parts;
                return {r, g, b, a};
            }
        }
    }

    throw new Error('Unsupported color format: ' + color);
}

// ---------------------------------------------------------------------------------------------------------------------
export function loadTexture(file_name) {
    if (file_name) {
        return `${TEXTURE_PATH_IN_PUBLIC}/${file_name}`;
    } else {
        return null;
    }
}

// ---------------------------------------------------------------------------------------------------------------------
export function loadModel(file_name) {
    if (file_name) {
        return `${MODEL_PATH_IN_PUBLIC}/${file_name}`;
    } else {
        return null;
    }
}

// ---------------------------------------------------------------------------------------------------------------------
/**
 * Adjusts the brightness of a StandardMaterial.
 *
 * @param {StandardMaterial} material
 * @param {number} factor
 *   - factor < 1.0 → darker
 *   - factor > 1.0 → brighter
 *   - factor = 1.0 → no change
 */
export function adjustMaterialBrightness(material, factor) {
    // Clamp to avoid negative colors
    const f = Math.max(0, factor);

    // Scale diffuseColor which multiplies the texture before lighting.
    // Values > 1 are allowed and make the surface brighter while preserving shadows.
    if (material.diffuseTexture) {
        material.diffuseColor = new Color3(f, f, f);
    } else {
        material.diffuseColor = material.diffuseColor.scale(f);
    }
}


/* ------------------------------------------------------------------------------------------------------------------ */
export function vecChanged(a, b, eps = 1e-5) {
    if (!a || !b) return true;
    return (
        Math.abs(a[0] - b[0]) > eps ||
        Math.abs(a[1] - b[1]) > eps ||
        Math.abs(a[2] - b[2]) > eps
    );
}

/** @private */
export function quatChanged(a, b, eps = 1e-6) {
    if (!a || !b) return true;
    return (
        Math.abs(a.x - b.x) > eps ||
        Math.abs(a.y - b.y) > eps ||
        Math.abs(a.z - b.z) > eps ||
        Math.abs(a.w - b.w) > eps
    );
}

// ---------------------------------------------------------------------------------------------------------------------
/**
 * Deep merge source into target. Arrays and non-plain-object values in source
 * overwrite target; plain objects are merged recursively. Target is not mutated.
 */
export function deepMerge(target, source) {
    const result = {...target};
    for (const key of Object.keys(source)) {
        const srcVal = source[key];
        const tgtVal = target[key];
        if (srcVal && typeof srcVal === 'object' && !Array.isArray(srcVal) &&
            tgtVal && typeof tgtVal === 'object' && !Array.isArray(tgtVal)) {
            result[key] = deepMerge(tgtVal, srcVal);
        } else {
            result[key] = srcVal;
        }
    }
    return result;
}