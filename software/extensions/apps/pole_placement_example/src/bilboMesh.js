/**
 * Standalone BabylonBilbo for use in webapps without the full
 * BabylonObject/WebSocket infrastructure.
 *
 * Mirrors the model-loading approach and setState() logic from
 * extensions/babylon/src/lib/objects/bilbo/bilbo.js (BabylonBilbo).
 *
 * Also includes coordinatesToBabylon and drawCoordinateSystem helpers
 * copied from extensions/babylon/src/lib/.
 */

import {
    SceneLoader, StandardMaterial, Color3,
    Vector3, Quaternion as BabylonQuaternion,
    MeshBuilder, DynamicTexture, Mesh, TransformNode,
} from '@babylonjs/core'


// ── coordinatesToBabylon (from extensions/babylon/src/lib/babylon_utils.js) ──

export function coordinatesToBabylon(coordinates) {
    if (Array.isArray(coordinates)) {
        return new Vector3(coordinates[0], coordinates[2], -coordinates[1])
    }
    return new Vector3(coordinates.x, coordinates.z, -coordinates.y)
}


// ── Quaternion (from extensions/babylon/src/lib/quaternion.js) ───────────────

class Quaternion {
    constructor(...args) {
        if (args.length === 1) {
            this.array = args[0] instanceof Quaternion ? args[0].array.slice() : args[0]
        } else {
            this.array = args
        }
        this._normalize()
    }

    get w() { return this.array[0] }
    get x() { return this.array[1] }
    get y() { return this.array[2] }
    get z() { return this.array[3] }

    static fromAngleAxis(angle, axis) {
        if (axis === 'x') axis = [1, 0, 0]
        else if (axis === 'y') axis = [0, 1, 0]
        else if (axis === 'z') axis = [0, 0, 1]
        const n = Math.hypot(...axis)
        const a = axis.map(v => v / n)
        const s = Math.sin(angle / 2)
        return new Quaternion(Math.cos(angle / 2), a[0] * s, a[1] * s, a[2] * s)
    }

    static fromEulerAngles(angles, convention, intrinsic) {
        if (intrinsic) {
            let q = Quaternion.fromAngleAxis(angles[0], convention[0])
            q = q.multiply(Quaternion.fromAngleAxis(angles[1], convention[1]))
            q = q.multiply(Quaternion.fromAngleAxis(angles[2], convention[2]))
            return q
        } else {
            let q = Quaternion.fromAngleAxis(angles[0], convention[0])
            q = Quaternion.fromAngleAxis(angles[1], convention[1]).multiply(q)
            q = Quaternion.fromAngleAxis(angles[2], convention[2]).multiply(q)
            return q
        }
    }

    multiply(o) {
        return new Quaternion(
            this.w * o.w - this.x * o.x - this.y * o.y - this.z * o.z,
            this.w * o.x + this.x * o.w + this.y * o.z - this.z * o.y,
            this.w * o.y - this.x * o.z + this.y * o.w + this.z * o.x,
            this.w * o.z + this.x * o.y - this.y * o.x + this.z * o.w,
        )
    }

    babylon() {
        return new BabylonQuaternion(this.array[1], this.array[3], -this.array[2], this.array[0]).normalize()
    }

    _normalize() {
        const n = Math.hypot(...this.array)
        this.array = this.array.map(v => v / n)
    }
}


// ── drawCoordinateSystem (from extensions/babylon/src/lib/objects/coordinate_system.js) ──

export function drawCoordinateSystem(scene, length, thickness = 0.02) {
    const z = 0.001
    const radius = thickness / 2

    const makeMat = (name, rgb) => {
        const m = new StandardMaterial(name, scene)
        m.disableLighting = true
        m.emissiveColor = new Color3(...rgb)
        return m
    }

    const pathX = [[0, 0, z], [length, 0, z]].map(coordinatesToBabylon)
    const pathY = [[0, 0, z], [0, length, z]].map(coordinatesToBabylon)
    const pathZ = [[0, 0, z], [0, 0, length + z]].map(coordinatesToBabylon)

    const axisX = MeshBuilder.CreateTube('axisX', { path: pathX, radius, tessellation: 8 }, scene)
    axisX.isPickable = false
    axisX.material = makeMat('matX', [1, 0, 0])

    const axisY = MeshBuilder.CreateTube('axisY', { path: pathY, radius, tessellation: 8 }, scene)
    axisY.isPickable = false
    axisY.material = makeMat('matY', [0, 1, 0])

    const axisZ = MeshBuilder.CreateTube('axisZ', { path: pathZ, radius, tessellation: 8 }, scene)
    axisZ.isPickable = false
    axisZ.material = makeMat('matZ', [0, 0, 1])
}


// ── BilboMesh (mirrors BabylonBilbo) ─────────────────────────────────────────

export class BilboMesh {
    loaded = false

    /**
     * @param {BABYLON.Scene} scene
     * @param {object} [opts]
     * @param {number[]} [opts.color]  - [r, g, b] 0-1
     * @param {string} [opts.text]
     * @param {number} [opts.scaling]
     * @param {BABYLON.ShadowGenerator} [opts.shadowGenerator]
     */
    constructor(scene, opts = {}) {
        this.scene = scene
        this.mesh = null
        this.material = null
        this.position = [0, 0, 0]
        this.orientation = null

        this.config = {
            color: opts.color || [0.4, 1, 0.4],
            text: opts.text || null,
            text_color: opts.text_color || [1, 1, 1],
            scaling: opts.scaling || 1,
            model_scaling: 1,
            z_offset: 0.125 / 2,
        }
        this.textHolder = null
        this.textPlane = null

        this.static_rotation_quaternion = Quaternion.fromEulerAngles([0, 0, 0], 'xyz', true)
        this.shadowGenerator = opts.shadowGenerator || null

        this._ready = this._loadModel()
    }

    async _loadModel() {
        const result = await SceneLoader.ImportMeshAsync('', './', 'models/bilbo_generic.babylon', this.scene)
        this._onMeshLoaded(result.meshes)
        return this
    }

    _onMeshLoaded(newMeshes) {
        this.mesh = newMeshes[0]

        newMeshes.forEach(m => {
            m.metadata = m.metadata || {}
            m.metadata.object = this
            m.isPickable = true
        })

        this.mesh.scaling.x = this.config.scaling * this.config.model_scaling
        this.mesh.scaling.y = this.config.scaling * this.config.model_scaling
        this.mesh.scaling.z = -this.config.scaling * this.config.model_scaling

        // Material
        this.material = new StandardMaterial('bilboMaterial', this.scene)
        if (this.config.color) {
            this.material.diffuseColor = new Color3(...this.config.color)
            this.material.specularColor = new Color3(0.3, 0.3, 0.3)
        }
        this.mesh.material = this.material

        // Shadows
        if (this.shadowGenerator) {
            this.shadowGenerator.addShadowCaster(this.mesh)
        }

        this.loaded = true
        if (this.config.text) this.addText()
        this.setState(0, 0, 0, 0)
    }

    addText() {
        const tex = new DynamicTexture('bilboTextTex', { width: 256, height: 256 }, this.scene)
        const ctx = tex.getContext()
        const [r, g, b] = this.config.text_color

        // Draw circle outline
        ctx.clearRect(0, 0, 256, 256)
        ctx.beginPath()
        ctx.arc(128, 128, 120, 0, Math.PI * 2)
        ctx.lineWidth = 20
        ctx.strokeStyle = `rgb(${r * 255 | 0},${g * 255 | 0},${b * 255 | 0})`
        ctx.stroke()

        // Auto-fit text
        let fontSize = 250
        const maxW = 200
        ctx.font = `bold ${fontSize}px sans-serif`
        while (ctx.measureText(this.config.text).width > maxW && fontSize > 20) {
            fontSize -= 10
            ctx.font = `bold ${fontSize}px sans-serif`
        }

        tex.drawText(this.config.text, null, 128 + fontSize / 3,
            `bold ${fontSize}px sans-serif`,
            `rgb(${r * 255 | 0},${g * 255 | 0},${b * 255 | 0})`, null, true)
        tex.update()

        const mat = new StandardMaterial('bilboTextMat', this.scene)
        mat.diffuseTexture = tex
        mat.diffuseTexture.hasAlpha = true
        mat.useAlphaFromDiffuseTexture = true
        mat.backFaceCulling = false
        mat.emissiveColor = new Color3(0.01, 0.01, 0.01)

        this.textHolder = new TransformNode('textHolder', this.scene)
        this.textHolder.parent = this.mesh
        this.textHolder.position = new Vector3(0.0325, 0.05, 0)
        this.textHolder.scaling = new Vector3(1, 1, -1)

        this.textPlane = MeshBuilder.CreatePlane('textPlane', {
            width: 0.1, height: 0.1, sideOrientation: Mesh.DOUBLESIDE
        }, this.scene)
        this.textPlane.material = mat
        this.textPlane.parent = this.textHolder
        this.textPlane.rotation = new Vector3(0, 1.57, 0)
    }

    onLoaded() {
        return this._ready
    }

    // ── setState (matches BabylonBilbo.setState exactly) ─────────────────────

    setState(x, y, theta, psi) {
        this.setPosition([x, y, 0])
        const orientation = Quaternion.fromEulerAngles([psi, theta, 0], 'zyx', true)
        this.setOrientation(orientation)
    }

    setPosition(position) {
        this.position = position
        if (this.loaded && this.mesh) {
            this.mesh.position = coordinatesToBabylon([
                this.position[0],
                this.position[1],
                this.config.scaling * this.config.z_offset,
            ])
        }
    }

    setOrientation(orientation) {
        this.orientation = new Quaternion(orientation)
        if (this.loaded && this.mesh) {
            this.mesh.rotationQuaternion = this.orientation.multiply(this.static_rotation_quaternion).babylon()
        }
    }

    setColor(color) {
        this.config.color = color
        if (this.material) {
            this.material.diffuseColor = new Color3(...color)
        }
    }

    dispose() {
        if (this.textPlane) this.textPlane.dispose()
        if (this.textHolder) this.textHolder.dispose()
        if (this.mesh) this.mesh.dispose()
        if (this.material) this.material.dispose()
    }
}
