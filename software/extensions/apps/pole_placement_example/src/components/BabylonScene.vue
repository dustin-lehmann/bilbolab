<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  Engine, Scene, ArcRotateCamera, HemisphericLight, DirectionalLight,
  MeshBuilder, StandardMaterial, Color3, Color4, Vector3, ShadowGenerator,
} from '@babylonjs/core'
import { BilboMesh, drawCoordinateSystem } from '../bilboMesh.js'

const props = defineProps({
  state: Array,     // [x, y, v, theta, theta_dot, psi, psi_dot]
  phase: String,
  darkMode: Boolean,
})

const emit = defineEmits(['restart'])

const canvasRef = ref(null)
let engine = null
let scene = null
let bilbo = null
let camera = null

const CAM_ALPHA = 2.3, CAM_BETA = 1.2, CAM_RADIUS = 2.0
const INTRO_ALPHA = -0.3, INTRO_BETA = 1.35, INTRO_RADIUS = 1.0, INTRO_DURATION = 4000
let activeIntroObs = null

function resetCamera() {
  if (!camera) return
  camera.alpha = CAM_ALPHA
  camera.beta = CAM_BETA
  camera.radius = CAM_RADIUS
  camera.target = new Vector3(0, 0.08, 0)
}

function playCameraIntro() {
  if (!camera || !scene) return
  if (activeIntroObs) scene.onBeforeRenderObservable.remove(activeIntroObs)
  camera.alpha = INTRO_ALPHA
  camera.beta = INTRO_BETA
  camera.radius = INTRO_RADIUS
  camera.target = new Vector3(0, 0.08, 0)
  const start = performance.now()
  function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2 }
  activeIntroObs = scene.onBeforeRenderObservable.add(() => {
    const t = Math.min(1, (performance.now() - start) / INTRO_DURATION)
    const e = easeInOut(t)
    camera.alpha = INTRO_ALPHA + (CAM_ALPHA - INTRO_ALPHA) * e
    camera.beta = INTRO_BETA + (CAM_BETA - INTRO_BETA) * e
    camera.radius = INTRO_RADIUS + (CAM_RADIUS - INTRO_RADIUS) * e
    if (t >= 1) {
      scene.onBeforeRenderObservable.remove(activeIntroObs)
      activeIntroObs = null
    }
  })
}

defineExpose({ playCameraIntro })

onMounted(() => {
  engine = new Engine(canvasRef.value, true, { preserveDrawingBuffer: true, stencil: true })
  scene = new Scene(engine)
  scene.useRightHandedSystem = true
  const bgDark = new Color4(0.12, 0.12, 0.16, 1)
  const bgLight = new Color4(0.94, 0.94, 0.96, 1)
  scene.clearColor = props.darkMode ? bgDark : bgLight

  // Fog matching background color
  scene.fogMode = Scene.FOGMODE_EXP2
  scene.fogDensity = 0.12
  scene.fogColor = props.darkMode ? new Color3(0.12, 0.12, 0.16) : new Color3(0.94, 0.94, 0.96)

  // Camera
  camera = new ArcRotateCamera('cam', INTRO_ALPHA, INTRO_BETA, INTRO_RADIUS, new Vector3(0, 0.08, 0), scene)
  camera.attachControl(canvasRef.value, true)
  playCameraIntro()
  camera.lowerRadiusLimit = 0.5
  camera.upperRadiusLimit = 5
  camera.upperBetaLimit = Math.PI / 2 - 0.01
  camera.fov = 1.1
  camera.wheelDeltaPercentage = 0.02
  camera.minZ = 0.05

  // Prevent camera from clipping below the ground plane
  const MIN_CAM_Y = 0.05
  scene.onBeforeRenderObservable.add(() => {
    if (camera.position.y < MIN_CAM_Y) {
      camera.beta = Math.acos(MIN_CAM_Y / camera.radius)
    }
  })

  // Lights
  const hemi = new HemisphericLight('hemi', new Vector3(0, 1, 0), scene)
  hemi.intensity = 0.9
  hemi.groundColor = new Color3(0.45, 0.45, 0.5)

  const dir = new DirectionalLight('dir', new Vector3(-0.5, -1, 0.8), scene)
  dir.position = new Vector3(2, 4, -2)
  dir.intensity = 1.0

  const shadowGen = new ShadowGenerator(1024, dir)
  shadowGen.useBlurExponentialShadowMap = true
  shadowGen.blurKernel = 16

  // Floor
  const floor = MeshBuilder.CreateGround('floor', { width: 60, height: 60, subdivisions: 60 }, scene)
  const floorMat = new StandardMaterial('floorMat', scene)
  floorMat.diffuseColor = props.darkMode ? new Color3(0.22, 0.22, 0.26) : new Color3(0.85, 0.85, 0.88)
  floorMat.specularColor = new Color3(0, 0, 0)
  floor.material = floorMat
  floor.receiveShadows = true

  // Grid lines on floor (keep grid local, fog hides the rest)
  const gridSize = 10, gridStep = 0.5
  const gridColor = props.darkMode ? new Color3(0.30, 0.30, 0.34) : new Color3(0.72, 0.72, 0.76)
  for (let i = -gridSize / 2; i <= gridSize / 2; i += gridStep) {
    const lineX = MeshBuilder.CreateLines('gx', { points: [new Vector3(i, 0.001, -gridSize / 2), new Vector3(i, 0.001, gridSize / 2)] }, scene)
    lineX.color = gridColor
    const lineZ = MeshBuilder.CreateLines('gz', { points: [new Vector3(-gridSize / 2, 0.001, i), new Vector3(gridSize / 2, 0.001, i)] }, scene)
    lineZ.color = gridColor
  }

  // Coordinate system
  drawCoordinateSystem(scene, 0.3)

  // BILBO robot (loads .babylon model, mirrors BabylonBilbo)
  bilbo = new BilboMesh(scene, {
    color: [0.85, 0.25, 0.25],
    text: 'B',
    shadowGenerator: shadowGen,
  })

  engine.runRenderLoop(() => scene.render())
  window.addEventListener('resize', () => engine.resize())

  // Initial resize
  engine.resize()
})

// Update robot pose from simulation state
watch(() => props.state, (st) => {
  if (!st || !bilbo) return
  const [x, y, v, theta, theta_dot, psi, psi_dot] = st
  bilbo.setState(x, y, theta, psi)
}, { deep: true })

// Theme change
watch(() => props.darkMode, (dark) => {
  if (scene) {
    scene.clearColor = dark ? new Color4(0.12, 0.12, 0.16, 1) : new Color4(0.94, 0.94, 0.96, 1)
    scene.fogColor = dark ? new Color3(0.12, 0.12, 0.16) : new Color3(0.94, 0.94, 0.96)
  }
})

onBeforeUnmount(() => {
  if (bilbo) bilbo.dispose()
  if (engine) {
    engine.stopRenderLoop()
    engine.dispose()
  }
})
</script>

<template>
  <div class="scene-container" data-tour="scene">
    <canvas ref="canvasRef" class="babylon-canvas" />
    <div class="phase-badge" v-if="phase && phase !== 'idle'">
      {{ phase.replace('_', ' ') }}
    </div>
    <button class="play-btn" data-tour="play" @click="emit('restart')" title="Restart simulation">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
        <path d="M6 4l15 8-15 8z" />
      </svg>
    </button>
    <button class="reset-cam-btn" data-tour="reset-cam" @click="resetCamera" title="Reset camera view">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M1 1v5h5" /><path d="M1 6A7 7 0 1 1 2.8 12" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.scene-container {
  flex: 1;
  position: relative;
  min-height: 0;
}
.babylon-canvas {
  width: 100%;
  height: 100%;
  display: block;
  outline: none;
}
.phase-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  font-size: 11px;
  font-weight: 500;
  padding: 4px 10px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-dim);
}
.play-btn {
  position: absolute;
  bottom: 12px;
  left: 12px;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 50%;
  color: var(--accent);
  cursor: pointer;
  padding: 0 0 0 4px;
}
.play-btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.reset-cam-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-dim);
  cursor: pointer;
  padding: 0;
}
.reset-cam-btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}
</style>
