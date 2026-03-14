<template>
  <div :class="['app', { light: !darkMode }]">
    <!-- Header -->
    <header class="header">
      <div class="header-left">
        <img src="/bilbolab_logo.png" alt="BilboLab" class="header-logo">
        <span class="header-sep"></span>
        <h1>TESTBED CREATOR</h1>
      </div>
      <div class="header-center">
        <span class="coords" v-if="mouseInCanvas">
          {{ mouseWorld.x.toFixed(2) }} , {{ mouseWorld.y.toFixed(2) }} m
        </span>
      </div>
      <div class="header-right">
        <button class="btn btn-icon" @click="undo" :disabled="!canUndo" title="Undo (Cmd+Z)">&#8617;</button>
        <button class="btn btn-icon" @click="redo" :disabled="!canRedo" title="Redo (Cmd+Shift+Z)">&#8618;</button>
        <span class="header-sep"></span>
        <button :class="['btn', 'btn-snap', { active: snapEnabled }]" @click="snapEnabled = !snapEnabled"
          title="Toggle grid snapping (S)">
          Snap: {{ snapEnabled ? 'ON' : 'OFF' }}
        </button>
        <button class="btn btn-clear" @click="clearAll">Clear</button>
        <button class="btn btn-export" @click="exportYaml">Copy YAML</button>
        <button class="btn btn-import" @click="showImportModal = true">Import YAML</button>
        <span class="header-sep"></span>
        <button class="btn btn-icon btn-theme" @click="toggleTheme"
          :title="darkMode ? 'Switch to light mode' : 'Switch to dark mode'">
          <span v-if="darkMode">&#9788;</span>
          <span v-else>&#9790;</span>
        </button>
      </div>
    </header>

    <div class="main">
      <!-- Left Sidebar -->
      <aside class="sidebar sidebar-left">
        <!-- Tools -->
        <section class="panel">
          <h3 class="panel-title">Tools</h3>
          <div class="tool-grid">
            <button v-for="t in tools" :key="t.id"
              :class="['tool-btn', { active: activeTool === t.id }]"
              @click="setTool(t.id)">
              <span class="tool-icon" v-if="t.id === 'select'">
                <svg width="14" height="16" viewBox="0 0 14 16" fill="currentColor">
                  <path d="M1 0.5L1 14L4.5 10L8 15.5L10.5 14.5L7 9L12 8.5Z"/>
                </svg>
              </span>
              <span class="tool-icon" v-else>{{ t.icon }}</span>
              <span class="tool-label">{{ t.label }}</span>
              <span class="tool-key">{{ t.key }}</span>
            </button>
          </div>
        </section>

        <!-- Map Settings -->
        <section class="panel">
          <h3 class="panel-title">Map</h3>
          <div class="field-row">
            <label>X</label>
            <input type="number" v-model.number="map.xMin" step="0.5" class="field-sm">
            <span class="field-sep">to</span>
            <input type="number" v-model.number="map.xMax" step="0.5" class="field-sm">
          </div>
          <div class="field-row">
            <label>Y</label>
            <input type="number" v-model.number="map.yMin" step="0.5" class="field-sm">
            <span class="field-sep">to</span>
            <input type="number" v-model.number="map.yMax" step="0.5" class="field-sm">
          </div>
          <div class="field-row">
            <label>Grid</label>
            <input type="number" v-model.number="map.gridSize" step="0.05" min="0.01" class="field-full">
          </div>
        </section>

        <!-- Checkerboard -->
        <section class="panel">
          <h3 class="panel-title">Checkerboard</h3>
          <label class="toggle-row" @click="checkerboard.enabled = !checkerboard.enabled">
            <span :class="['toggle-switch', { active: checkerboard.enabled }]">
              <span class="toggle-knob"></span>
            </span>
            <span class="toggle-label">Show checkerboard</span>
          </label>
          <div class="field-row" v-if="checkerboard.enabled" style="margin-top:8px">
            <label>Size</label>
            <input type="number" v-model.number="checkerboard.size" step="0.1" min="0.05" class="field-full">
          </div>
        </section>

        <!-- Snapping -->
        <section class="panel">
          <h3 class="panel-title">Snapping</h3>
          <label class="toggle-row" @click="snapEnabled = !snapEnabled">
            <span :class="['toggle-switch', { active: snapEnabled }]">
              <span class="toggle-knob"></span>
            </span>
            <span class="toggle-label">Snap to grid</span>
            <span class="tool-key" style="position:static">S</span>
          </label>
          <div class="field-row" style="margin-top:8px">
            <label>Ctrl ÷</label>
            <input type="number" v-model.number="snapSubdivision" step="1" min="2" max="16" class="field-full"
              @keydown.stop title="Grid subdivision when holding Ctrl">
          </div>
          <div class="hint">Snaps to grid. Hold Ctrl for {{ snapSubdivision }}&times; finer.</div>
        </section>

        <!-- Tool-specific defaults -->
        <section class="panel" v-if="activeTool === 'circle'">
          <h3 class="panel-title">Circle Defaults</h3>
          <div class="field-row">
            <label>Radius</label>
            <input type="number" v-model.number="defaults.circleRadius" step="0.05" min="0.01" class="field-full">
          </div>
        </section>

        <section class="panel" v-if="activeTool === 'rectangle'">
          <h3 class="panel-title">Rectangle</h3>
          <div class="hint">Click and drag to draw a rectangle.</div>
        </section>

        <section class="panel" v-if="activeTool === 'wall'">
          <h3 class="panel-title">Wall Defaults</h3>
          <div class="field-row">
            <label>Thickness</label>
            <input type="number" v-model.number="defaults.wallThickness" step="0.01" min="0.01" class="field-full">
          </div>
          <div class="hint">Click two grid points to draw a wall.</div>
        </section>

        <section class="panel" v-if="activeTool === 'line'">
          <h3 class="panel-title">Line</h3>
          <div class="hint">Click two grid points to draw a line.</div>
        </section>

        <section class="panel" v-if="activeTool === 'point'">
          <h3 class="panel-title">Point</h3>
          <div class="hint">Click to place a named point.</div>
        </section>
      </aside>

      <!-- Canvas -->
      <div class="canvas-container" ref="containerRef">
        <canvas ref="canvasRef"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseLeave"
          @contextmenu.prevent
          :style="{ cursor: canvasCursor }"
        ></canvas>
      </div>

      <!-- Right Sidebar -->
      <aside class="sidebar sidebar-right">
        <!-- Properties -->
        <section class="panel" v-if="selectedObstacle">
          <h3 class="panel-title">Properties</h3>
          <div class="field-row">
            <label>ID</label>
            <input type="text" :value="selectedObstacle.id"
              @input="onIdInput($event, selectedObstacle)"
              @focus="onPropertyFocus"
              @keydown.stop
              class="field-full">
          </div>
          <template v-if="selectedObstacle.type === 'circle'">
            <div class="field-row">
              <label>Radius</label>
              <input type="number" v-model.number="selectedObstacle.radius" step="0.01" min="0.01" @focus="onPropertyFocus" @keydown.stop class="field-full">
            </div>
          </template>
          <template v-if="selectedObstacle.type === 'box'">
            <div class="field-row">
              <label>Width</label>
              <input type="number" v-model.number="selectedObstacle.width" step="0.01" min="0.01" @focus="onPropertyFocus" @keydown.stop class="field-full">
            </div>
            <div class="field-row">
              <label>Height</label>
              <input type="number" v-model.number="selectedObstacle.height" step="0.01" min="0.01" @focus="onPropertyFocus" @keydown.stop class="field-full">
            </div>
            <div class="field-row">
              <label>Angle</label>
              <input type="number" v-model.number="selectedAngleDeg" step="1" @focus="onPropertyFocus" @keydown.stop class="field-full">
              <span class="field-unit">deg</span>
            </div>
          </template>
          <template v-if="selectedObstacle.type === 'line'">
            <div class="field-row">
              <label>Length</label>
              <input type="number" v-model.number="selectedObstacle.length" step="0.01" min="0.01" @focus="onPropertyFocus" @keydown.stop class="field-full">
            </div>
            <div class="field-row">
              <label>Angle</label>
              <input type="number" v-model.number="selectedAngleDeg" step="1" @focus="onPropertyFocus" @keydown.stop class="field-full">
              <span class="field-unit">deg</span>
            </div>
          </template>
          <div class="field-row">
            <label>X</label>
            <input type="number" v-model.number="selectedObstacle.x" step="0.01" @focus="onPropertyFocus" @keydown.stop class="field-full">
          </div>
          <div class="field-row">
            <label>Y</label>
            <input type="number" v-model.number="selectedObstacle.y" step="0.01" @focus="onPropertyFocus" @keydown.stop class="field-full">
          </div>
          <button class="btn btn-delete" @click="deleteSelected">Delete</button>
        </section>

        <section class="panel" v-else>
          <div class="hint">Select an obstacle to edit its properties.</div>
        </section>

        <!-- Obstacle List -->
        <section class="panel">
          <h3 class="panel-title">Obstacles <span class="badge">{{ obstacleItems.length }}</span></h3>
          <div class="obstacle-list" v-if="obstacleItems.length > 0">
            <div v-for="(o, idx) in obstacleItems" :key="'obs-' + idx"
              :class="['obstacle-item', { selected: selectedId === o.id }]"
              @click="selectObstacle(o.id)">
              <span :class="['type-dot', o.type, { wall: o.subtype === 'wall' }]"></span>
              <span class="obstacle-id">{{ o.id }}</span>
              <button class="item-delete" @click.stop="deleteObstacle(o.id)" title="Delete">&times;</button>
            </div>
          </div>
          <div class="hint" v-else>No obstacles yet.</div>
        </section>

        <!-- Points List -->
        <section class="panel">
          <h3 class="panel-title">Points <span class="badge">{{ pointItems.length }}</span></h3>
          <div class="obstacle-list" v-if="pointItems.length > 0">
            <div v-for="(o, idx) in pointItems" :key="'pt-' + idx"
              :class="['obstacle-item', { selected: selectedId === o.id }]"
              @click="selectObstacle(o.id)">
              <span class="type-dot point"></span>
              <span class="obstacle-id">{{ o.id }}</span>
              <button class="item-delete" @click.stop="deleteObstacle(o.id)" title="Delete">&times;</button>
            </div>
          </div>
          <div class="hint" v-else>No points yet.</div>
        </section>
      </aside>
    </div>

    <!-- Import Modal -->
    <div v-if="showImportModal" class="modal-overlay" @click.self="showImportModal = false">
      <div class="modal">
        <h3 class="modal-title">Import YAML</h3>
        <textarea v-model="importText" class="modal-textarea" placeholder="Paste YAML here..." @keydown.stop></textarea>
        <div class="modal-actions">
          <button class="btn btn-clear" @click="showImportModal = false">Cancel</button>
          <button class="btn btn-export" @click="doImport">Import</button>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <transition name="toast">
      <div v-if="showToast" class="toast">{{ toastMessage }}</div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'

// ============================================================
// CONSTANTS
// ============================================================
const DARK_COLORS = {
  circle:    { stroke: '#4ecdc4', fill: 'rgba(78,205,196,0.2)' },
  box:       { stroke: '#ff6b6b', fill: 'rgba(255,107,107,0.2)' },
  wall:      { stroke: '#feca57', fill: 'rgba(254,202,87,0.25)' },
  line:      { stroke: '#ff9f43', fill: 'rgba(255,159,67,0.25)' },
  point:     { stroke: '#a78bfa', fill: 'rgba(167,139,250,0.3)' },
  selected:  '#00d2ff',
  selectedFill: 'rgba(0, 210, 255, 0.2)',
  preview:   'rgba(255,255,255,0.15)',
  handle:    '#ffffff',
  handleFill:'#00d2ff',
  rotateLine:'rgba(0, 210, 255, 0.5)',
  grid:      '#252b3d',
  gridMajor: '#333d55',
  gridLabel: '#667088',
  bg:        '#0a0a0f',
  mapBg:     '#0d1117',
  checkerLight: '#111724',
  axis:      '#4a5570'
}

const LIGHT_COLORS = {
  circle:    { stroke: '#1a9e96', fill: 'rgba(26,158,150,0.12)' },
  box:       { stroke: '#d94040', fill: 'rgba(217,64,64,0.12)' },
  wall:      { stroke: '#c49520', fill: 'rgba(196,149,32,0.15)' },
  line:      { stroke: '#d08020', fill: 'rgba(208,128,32,0.15)' },
  point:     { stroke: '#7c5ce0', fill: 'rgba(124,92,224,0.15)' },
  selected:  '#0088bb',
  selectedFill: 'rgba(0, 136, 187, 0.12)',
  preview:   'rgba(0,0,0,0.08)',
  handle:    '#444444',
  handleFill:'#0088bb',
  rotateLine:'rgba(0, 136, 187, 0.4)',
  grid:      '#cdd2dc',
  gridMajor: '#b0b8c8',
  gridLabel: '#7882a0',
  bg:        '#eaecf0',
  mapBg:     '#f5f6f8',
  checkerLight: '#e2e5ea',
  axis:      '#a0a8b8'
}

let COLORS = DARK_COLORS

const CANVAS_PADDING = 48
const HANDLE_SIZE = 4
const HANDLE_HIT = 8
const ROTATE_OFFSET_PX = 24
const ANGLE_SNAP_DEG = 15
const POINT_RADIUS = 5        // point marker radius in px
const POINT_HIT_RADIUS = 10   // point hit detection in px

const tools = [
  { id: 'select',    label: 'Select',    icon: '\u25FB', key: '1' },
  { id: 'circle',    label: 'Circle',    icon: '\u25CB', key: '2' },
  { id: 'rectangle', label: 'Rectangle', icon: '\u25A1', key: '3' },
  { id: 'wall',      label: 'Wall',      icon: '\u2571', key: '4' },
  { id: 'line',      label: 'Line',      icon: '\u2500', key: '5' },
  { id: 'point',     label: 'Point',     icon: '\u2716', key: '6' }
]

// ============================================================
// STATE
// ============================================================
const canvasRef = ref(null)
const containerRef = ref(null)
const obstacles = ref([])
const selectedId = ref(null)
const activeTool = ref('select')
const mouseWorld = reactive({ x: 0, y: 0 })
const mouseInCanvas = ref(false)
const showToast = ref(false)
const toastMessage = ref('')
const showImportModal = ref(false)
const importText = ref('')
const snapEnabled = ref(true)
const fineSnap = ref(false)
const snapSubdivision = ref(2)
const darkMode = ref(true)

function toggleTheme() {
  darkMode.value = !darkMode.value
}

const map = reactive({
  xMin: 0, xMax: 3,
  yMin: 0, yMax: 3,
  gridSize: 0.25
})

const checkerboard = reactive({
  enabled: false,
  size: 0.5
})

const defaults = reactive({
  circleRadius: 0.15,
  rectWidth: 0.5,
  rectHeight: 0.5,
  rectAngle: 0,
  wallThickness: 0.05
})

const counters = reactive({ circle: 1, box: 1, wall: 1, line: 1, point: 1 })

// Undo/Redo
const MAX_UNDO = 100
const undoStack = ref([])
const redoStack = ref([])
let skipHistorySnapshot = false

function snapshotObstacles() {
  return JSON.stringify(obstacles.value)
}

function pushUndo() {
  undoStack.value.push(snapshotObstacles())
  if (undoStack.value.length > MAX_UNDO) undoStack.value.shift()
  redoStack.value = []
}

function undo() {
  if (undoStack.value.length === 0) return
  redoStack.value.push(snapshotObstacles())
  const prev = undoStack.value.pop()
  skipHistorySnapshot = true
  obstacles.value = JSON.parse(prev)
  selectedId.value = null
  skipHistorySnapshot = false
}

function redo() {
  if (redoStack.value.length === 0) return
  undoStack.value.push(snapshotObstacles())
  const next = redoStack.value.pop()
  skipHistorySnapshot = true
  obstacles.value = JSON.parse(next)
  selectedId.value = null
  skipHistorySnapshot = false
}

const canUndo = computed(() => undoStack.value.length > 0)
const canRedo = computed(() => redoStack.value.length > 0)

// Interaction state
const isDragging = ref(false)
const hoveredId = ref(null)
const hoveredHandle = ref(null)

let dragState = null
let handleDrag = null
let wallStart = null
let rectStart = null
let dragSnapshotted = false
let clipboard = null

// Canvas internals
let ctx = null
let animFrameId = null
let canvasW = 0
let canvasH = 0
let scale = 1
let mapOffsetX = 0
let mapOffsetY = 0
let dpr = 1

// ============================================================
// COMPUTED
// ============================================================
const selectedObstacle = computed(() =>
  obstacles.value.find(o => o.id === selectedId.value) || null
)

const obstacleItems = computed(() =>
  obstacles.value.filter(o => o.type !== 'point')
)

const pointItems = computed(() =>
  obstacles.value.filter(o => o.type === 'point')
)

const selectedAngleDeg = computed({
  get() {
    const o = selectedObstacle.value
    if (!o || (o.type !== 'box' && o.type !== 'line')) return 0
    return Math.round(o.psi * 180 / Math.PI * 100) / 100
  },
  set(deg) {
    const o = selectedObstacle.value
    if (o && (o.type === 'box' || o.type === 'line')) {
      o.psi = deg * Math.PI / 180
    }
  }
})

const canvasCursor = computed(() => {
  if (activeTool.value === 'select') {
    if (isDragging.value) return 'grabbing'
    if (hoveredHandle.value) {
      const h = hoveredHandle.value
      if (h === 'rotate') return 'crosshair'
      if (h === 'resize-radius') return 'ew-resize'
      if (h === 'resize-r' || h === 'resize-l') return 'ew-resize'
      if (h === 'resize-t' || h === 'resize-b') return 'ns-resize'
      if (h === 'resize-tr' || h === 'resize-bl') return 'nesw-resize'
      if (h === 'resize-tl' || h === 'resize-br') return 'nwse-resize'
      return 'move'
    }
    if (hoveredId.value) return 'grab'
    return 'default'
  }
  if (activeTool.value === 'rectangle') return 'crosshair'
  if (activeTool.value === 'wall') return 'crosshair'
  if (activeTool.value === 'line') return 'crosshair'
  if (activeTool.value === 'point') return 'crosshair'
  return 'copy'
})

// ============================================================
// COORDINATE TRANSFORMS
// ============================================================
function worldToCanvas(wx, wy) {
  const cx = mapOffsetX + (wx - map.xMin) * scale
  const cy = mapOffsetY + (map.yMax - wy) * scale
  return [cx, cy]
}

function canvasToWorld(cx, cy) {
  const wx = (cx - mapOffsetX) / scale + map.xMin
  const wy = map.yMax - (cy - mapOffsetY) / scale
  return [wx, wy]
}

function snapToGrid(val) {
  const gs = fineSnap.value ? map.gridSize / snapSubdivision.value : map.gridSize
  return Math.round(val / gs) * gs
}

function snapAngle(rad) {
  if (!snapEnabled.value) return rad
  const snapRad = ANGLE_SNAP_DEG * Math.PI / 180
  return Math.round(rad / snapRad) * snapRad
}

// ============================================================
// RENDERING
// ============================================================
function computeLayout() {
  const el = containerRef.value
  if (!el) return
  dpr = window.devicePixelRatio || 1
  const rect = el.getBoundingClientRect()
  canvasW = rect.width
  canvasH = rect.height

  const canvas = canvasRef.value
  canvas.width = canvasW * dpr
  canvas.height = canvasH * dpr
  canvas.style.width = canvasW + 'px'
  canvas.style.height = canvasH + 'px'
  ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  const mapW = map.xMax - map.xMin
  const mapH = map.yMax - map.yMin
  if (mapW <= 0 || mapH <= 0) return

  const availW = canvasW - CANVAS_PADDING * 2
  const availH = canvasH - CANVAS_PADDING * 2
  scale = Math.min(availW / mapW, availH / mapH)
  mapOffsetX = CANVAS_PADDING + (availW - mapW * scale) / 2
  mapOffsetY = CANVAS_PADDING + (availH - mapH * scale) / 2
}

function drawCheckerboard() {
  if (!checkerboard.enabled) return
  const cs = checkerboard.size
  if (cs <= 0) return

  ctx.fillStyle = COLORS.checkerLight

  for (let x = map.xMin; x < map.xMax + 0.0001; x += cs) {
    for (let y = map.yMin; y < map.yMax + 0.0001; y += cs) {
      const ix = Math.round((x - map.xMin) / cs)
      const iy = Math.round((y - map.yMin) / cs)
      if ((ix + iy) % 2 === 0) continue

      const x2 = Math.min(x + cs, map.xMax)
      const y2 = Math.min(y + cs, map.yMax)

      const [cx1, cy1] = worldToCanvas(x, y2)
      const [cx2, cy2] = worldToCanvas(x2, y)

      ctx.fillRect(cx1, cy1, cx2 - cx1, cy2 - cy1)
    }
  }
}

function drawGrid() {
  const gs = map.gridSize
  if (gs <= 0) return

  ctx.lineWidth = 1

  for (let x = map.xMin; x <= map.xMax + gs * 0.01; x += gs) {
    const [cx] = worldToCanvas(x, 0)
    const isEdge = Math.abs(x - map.xMin) < 0.001 || Math.abs(x - map.xMax) < 0.001
    const isMajor = Math.abs(Math.round(x) - x) < 0.001
    ctx.strokeStyle = isEdge ? COLORS.axis : isMajor ? COLORS.gridMajor : COLORS.grid
    ctx.beginPath()
    ctx.moveTo(cx, mapOffsetY)
    ctx.lineTo(cx, mapOffsetY + (map.yMax - map.yMin) * scale)
    ctx.stroke()
  }

  for (let y = map.yMin; y <= map.yMax + gs * 0.01; y += gs) {
    const [, cy] = worldToCanvas(0, y)
    const isEdge = Math.abs(y - map.yMin) < 0.001 || Math.abs(y - map.yMax) < 0.001
    const isMajor = Math.abs(Math.round(y) - y) < 0.001
    ctx.strokeStyle = isEdge ? COLORS.axis : isMajor ? COLORS.gridMajor : COLORS.grid
    ctx.beginPath()
    ctx.moveTo(mapOffsetX, cy)
    ctx.lineTo(mapOffsetX + (map.xMax - map.xMin) * scale, cy)
    ctx.stroke()
  }

  // Fine grid when Ctrl is held
  if (fineSnap.value && snapEnabled.value) {
    const fineGs = gs / snapSubdivision.value
    ctx.globalAlpha = 0.7
    ctx.lineWidth = 0.5
    ctx.strokeStyle = COLORS.gridMajor

    for (let x = map.xMin; x <= map.xMax + fineGs * 0.01; x += fineGs) {
      // Skip lines that coincide with the main grid
      if (Math.abs(Math.round(x / gs) * gs - x) < 0.0001) continue
      const [cx] = worldToCanvas(x, 0)
      ctx.beginPath()
      ctx.moveTo(cx, mapOffsetY)
      ctx.lineTo(cx, mapOffsetY + (map.yMax - map.yMin) * scale)
      ctx.stroke()
    }

    for (let y = map.yMin; y <= map.yMax + fineGs * 0.01; y += fineGs) {
      if (Math.abs(Math.round(y / gs) * gs - y) < 0.0001) continue
      const [, cy] = worldToCanvas(0, y)
      ctx.beginPath()
      ctx.moveTo(mapOffsetX, cy)
      ctx.lineTo(mapOffsetX + (map.xMax - map.xMin) * scale, cy)
      ctx.stroke()
    }

    ctx.globalAlpha = 1
    ctx.lineWidth = 1
  }

  ctx.fillStyle = COLORS.gridLabel
  ctx.font = '10px JetBrains Mono'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'

  const labelStep = getLabelStep(gs)
  for (let x = map.xMin; x <= map.xMax + gs * 0.01; x += labelStep) {
    const [cx] = worldToCanvas(x, 0)
    ctx.fillText(fmt(x), cx, mapOffsetY + (map.yMax - map.yMin) * scale + 6)
  }

  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'
  for (let y = map.yMin; y <= map.yMax + gs * 0.01; y += labelStep) {
    const [, cy] = worldToCanvas(0, y)
    ctx.fillText(fmt(y), mapOffsetX - 6, cy)
  }
}

function getLabelStep(gs) {
  if (gs <= 0.1) return 0.5
  if (gs <= 0.25) return 0.5
  if (gs <= 0.5) return 1
  return gs
}

function drawObstacle(o, isSelected, alpha = 1.0) {
  if (o.type === 'point') {
    drawPointShape(o, isSelected, alpha)
    return
  }
  const colors = o.subtype === 'wall' ? COLORS.wall : COLORS[o.type] || COLORS.box
  const strokeColor = isSelected ? COLORS.selected : colors.stroke
  const fillColor = isSelected ? COLORS.selectedFill : colors.fill

  if (o.type === 'circle') {
    drawCircleShape(o.x, o.y, o.radius, strokeColor, fillColor, isSelected, alpha)
  } else if (o.type === 'line') {
    drawLineShape(o, strokeColor, isSelected, alpha)
  } else {
    drawBoxShape(o.x, o.y, o.width, o.height, o.psi, strokeColor, fillColor, isSelected, alpha)
  }
}

function drawLineShape(o, stroke, isSelected, alpha) {
  const cos = Math.cos(o.psi), sin = Math.sin(o.psi)
  const hh = o.length / 2
  // Endpoints: local (0, +hh) and (0, -hh) → same convention as wall
  const x1 = o.x - hh * sin, y1 = o.y + hh * cos
  const x2 = o.x + hh * sin, y2 = o.y - hh * cos
  const [cx1, cy1] = worldToCanvas(x1, y1)
  const [cx2, cy2] = worldToCanvas(x2, y2)

  ctx.globalAlpha = alpha
  ctx.strokeStyle = stroke
  ctx.lineWidth = isSelected ? 2.5 : 1.5
  ctx.setLineDash(isSelected ? [6, 3] : [])
  ctx.beginPath()
  ctx.moveTo(cx1, cy1)
  ctx.lineTo(cx2, cy2)
  ctx.stroke()
  ctx.setLineDash([])

  // Endpoint dots
  for (const [px, py] of [[cx1, cy1], [cx2, cy2]]) {
    ctx.beginPath()
    ctx.arc(px, py, 2.5, 0, Math.PI * 2)
    ctx.fillStyle = stroke
    ctx.fill()
  }

  ctx.globalAlpha = 1
}

function drawPointShape(o, isSelected, alpha) {
  const [cx, cy] = worldToCanvas(o.x, o.y)
  const color = isSelected ? COLORS.selected : COLORS.point.stroke
  const r = POINT_RADIUS

  ctx.globalAlpha = alpha

  // Crosshair lines
  ctx.strokeStyle = color
  ctx.lineWidth = 1.5
  ctx.setLineDash([])
  ctx.beginPath()
  ctx.moveTo(cx - r - 3, cy)
  ctx.lineTo(cx + r + 3, cy)
  ctx.moveTo(cx, cy - r - 3)
  ctx.lineTo(cx, cy + r + 3)
  ctx.stroke()

  // Filled dot
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fillStyle = isSelected ? COLORS.selectedFill : COLORS.point.fill
  ctx.fill()
  ctx.strokeStyle = color
  ctx.lineWidth = isSelected ? 2.5 : 1.5
  ctx.setLineDash(isSelected ? [4, 2] : [])
  ctx.stroke()
  ctx.setLineDash([])

  // ID label
  ctx.font = '11px JetBrains Mono'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = color
  ctx.fillText(o.id, cx + r + 6, cy)

  ctx.globalAlpha = 1
}

function drawCircleShape(wx, wy, radius, stroke, fill, isSelected, alpha) {
  const [cx, cy] = worldToCanvas(wx, wy)
  const r = radius * scale

  ctx.globalAlpha = alpha
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fillStyle = fill
  ctx.fill()
  ctx.strokeStyle = stroke
  ctx.lineWidth = isSelected ? 2.5 : 1.5
  ctx.setLineDash(isSelected ? [6, 3] : [])
  ctx.stroke()
  ctx.setLineDash([])

  ctx.beginPath()
  ctx.arc(cx, cy, 2.5, 0, Math.PI * 2)
  ctx.fillStyle = stroke
  ctx.fill()
  ctx.globalAlpha = 1
}

function drawBoxShape(wx, wy, width, height, psi, stroke, fill, isSelected, alpha) {
  const [cx, cy] = worldToCanvas(wx, wy)
  const w = width * scale
  const h = height * scale

  ctx.globalAlpha = alpha
  ctx.save()
  ctx.translate(cx, cy)
  ctx.rotate(-psi)

  ctx.fillStyle = fill
  ctx.fillRect(-w / 2, -h / 2, w, h)
  ctx.strokeStyle = stroke
  ctx.lineWidth = isSelected ? 2.5 : 1.5
  ctx.setLineDash(isSelected ? [6, 3] : [])
  ctx.strokeRect(-w / 2, -h / 2, w, h)
  ctx.setLineDash([])

  ctx.beginPath()
  ctx.arc(0, 0, 2.5, 0, Math.PI * 2)
  ctx.fillStyle = stroke
  ctx.fill()

  if (Math.abs(psi) > 0.001) {
    ctx.beginPath()
    ctx.moveTo(0, -h / 2)
    ctx.lineTo(0, -h / 2 - 6)
    ctx.strokeStyle = stroke
    ctx.lineWidth = 2
    ctx.setLineDash([])
    ctx.stroke()
  }

  ctx.restore()
  ctx.globalAlpha = 1
}

// ============================================================
// HANDLES
// ============================================================
function getHandlePositions(o) {
  const handles = []

  if (o.type === 'point') return handles

  if (o.type === 'circle') {
    handles.push({ type: 'resize-radius', wx: o.x + o.radius, wy: o.y })
    handles.push({ type: 'resize-radius', wx: o.x - o.radius, wy: o.y })
    handles.push({ type: 'resize-radius', wx: o.x, wy: o.y + o.radius })
    handles.push({ type: 'resize-radius', wx: o.x, wy: o.y - o.radius })
  } else if (o.type === 'line') {
    const cos = Math.cos(o.psi), sin = Math.sin(o.psi)
    const hh = o.length / 2
    handles.push({ type: 'resize-t', wx: o.x - hh * sin, wy: o.y + hh * cos })
    handles.push({ type: 'resize-b', wx: o.x + hh * sin, wy: o.y - hh * cos })
  } else {
    const cos = Math.cos(o.psi), sin = Math.sin(o.psi)
    const hw = o.width / 2, hh = o.height / 2

    const toWorld = (lx, ly) => [
      o.x + lx * cos - ly * sin,
      o.y + lx * sin + ly * cos
    ]

    const [tx, ty] = toWorld(0, hh)
    handles.push({ type: 'resize-t', wx: tx, wy: ty })
    const [bx, by] = toWorld(0, -hh)
    handles.push({ type: 'resize-b', wx: bx, wy: by })

    if (o.subtype !== 'wall') {
      const [rx, ry] = toWorld(hw, 0)
      handles.push({ type: 'resize-r', wx: rx, wy: ry })
      const [lx, ly] = toWorld(-hw, 0)
      handles.push({ type: 'resize-l', wx: lx, wy: ly })

      // Corner handles
      const [trx, try_] = toWorld(hw, hh)
      handles.push({ type: 'resize-tr', wx: trx, wy: try_ })
      const [tlx, tly] = toWorld(-hw, hh)
      handles.push({ type: 'resize-tl', wx: tlx, wy: tly })
      const [brx, bry] = toWorld(hw, -hh)
      handles.push({ type: 'resize-br', wx: brx, wy: bry })
      const [blx, bly] = toWorld(-hw, -hh)
      handles.push({ type: 'resize-bl', wx: blx, wy: bly })

      const rotOff = ROTATE_OFFSET_PX / scale
      const [rhx, rhy] = toWorld(0, hh + rotOff)
      const [thx, thy] = toWorld(0, hh)
      handles.push({ type: 'rotate', wx: rhx, wy: rhy, topWx: thx, topWy: thy })
    }
  }

  return handles
}

function hitTestHandle(wx, wy) {
  const sel = selectedObstacle.value
  if (!sel) return null

  const hitR = HANDLE_HIT / scale
  const handles = getHandlePositions(sel)

  for (const h of handles) {
    const dx = wx - h.wx, dy = wy - h.wy
    if (dx * dx + dy * dy <= hitR * hitR) return h.type
  }
  return null
}

function drawHandles(o) {
  const handles = getHandlePositions(o)

  for (const h of handles) {
    const [cx, cy] = worldToCanvas(h.wx, h.wy)

    if (h.type === 'rotate') {
      const [tcx, tcy] = worldToCanvas(h.topWx, h.topWy)
      ctx.beginPath()
      ctx.moveTo(tcx, tcy)
      ctx.lineTo(cx, cy)
      ctx.strokeStyle = COLORS.rotateLine
      ctx.lineWidth = 1.5
      ctx.setLineDash([3, 3])
      ctx.stroke()
      ctx.setLineDash([])

      ctx.beginPath()
      ctx.arc(cx, cy, 5, 0, Math.PI * 2)
      ctx.fillStyle = hoveredHandle.value === 'rotate' ? COLORS.handleFill : COLORS.mapBg
      ctx.fill()
      ctx.strokeStyle = COLORS.handleFill
      ctx.lineWidth = 1.5
      ctx.stroke()

      ctx.beginPath()
      ctx.arc(cx, cy, 3, -Math.PI * 0.3, Math.PI * 0.8)
      ctx.strokeStyle = COLORS.handleFill
      ctx.lineWidth = 1
      ctx.stroke()
    } else {
      const isHovered = hoveredHandle.value === h.type
      const s = HANDLE_SIZE
      ctx.fillStyle = isHovered ? COLORS.handleFill : COLORS.mapBg
      ctx.fillRect(cx - s, cy - s, s * 2, s * 2)
      ctx.strokeStyle = COLORS.handle
      ctx.lineWidth = 1.5
      ctx.strokeRect(cx - s, cy - s, s * 2, s * 2)
    }
  }
}

function drawWallPreview() {
  if (!wallStart || !mouseInCanvas.value) return

  const isLine = activeTool.value === 'line'
  const previewColor = isLine ? COLORS.line.stroke : COLORS.wall.stroke
  const endX = snapToGrid(mouseWorld.x)
  const endY = snapToGrid(mouseWorld.y)
  const [sx, sy] = worldToCanvas(wallStart.x, wallStart.y)
  const [ex, ey] = worldToCanvas(endX, endY)

  ctx.beginPath()
  ctx.moveTo(sx, sy)
  ctx.lineTo(ex, ey)
  ctx.strokeStyle = previewColor
  ctx.lineWidth = isLine ? 1.5 : defaults.wallThickness * scale
  ctx.globalAlpha = 0.4
  ctx.lineCap = 'butt'
  ctx.stroke()
  ctx.globalAlpha = 1

  ctx.beginPath()
  ctx.arc(ex, ey, 5, 0, Math.PI * 2)
  ctx.fillStyle = previewColor
  ctx.globalAlpha = 0.6
  ctx.fill()
  ctx.globalAlpha = 1
}

function drawGridPointHighlight() {
  if (!mouseInCanvas.value) return

  const gx = snapToGrid(mouseWorld.x)
  const gy = snapToGrid(mouseWorld.y)
  if (gx < map.xMin - 0.001 || gx > map.xMax + 0.001) return
  if (gy < map.yMin - 0.001 || gy > map.yMax + 0.001) return

  const [cx, cy] = worldToCanvas(gx, gy)

  ctx.beginPath()
  ctx.arc(cx, cy, 5, 0, Math.PI * 2)
  const hlColor = activeTool.value === 'line' ? COLORS.line.stroke : COLORS.wall.stroke
  ctx.fillStyle = wallStart ? hlColor : 'rgba(254,202,87,0.5)'
  ctx.fill()

  if (wallStart) {
    const [scx, scy] = worldToCanvas(wallStart.x, wallStart.y)
    ctx.beginPath()
    ctx.arc(scx, scy, 6, 0, Math.PI * 2)
    ctx.strokeStyle = hlColor
    ctx.lineWidth = 2
    ctx.stroke()
  }
}

function drawPlacementPreview() {
  if (!mouseInCanvas.value) return

  const px = snapEnabled.value ? snapToGrid(mouseWorld.x) : mouseWorld.x
  const py = snapEnabled.value ? snapToGrid(mouseWorld.y) : mouseWorld.y

  if (activeTool.value === 'circle') {
    drawCircleShape(px, py, defaults.circleRadius,
      COLORS.circle.stroke, COLORS.preview, false, 0.5)
  } else if (activeTool.value === 'rectangle') {
    if (rectStart) {
      // Draw drag preview from start corner to current mouse position
      const w = Math.abs(px - rectStart.x)
      const h = Math.abs(py - rectStart.y)
      if (w > 0.001 && h > 0.001) {
        const cx = (rectStart.x + px) / 2
        const cy = (rectStart.y + py) / 2
        drawBoxShape(cx, cy, w, h, 0, COLORS.box.stroke, COLORS.preview, false, 0.5)
      }
      // Show start corner dot
      const [scx, scy] = worldToCanvas(rectStart.x, rectStart.y)
      ctx.beginPath()
      ctx.arc(scx, scy, 4, 0, Math.PI * 2)
      ctx.fillStyle = COLORS.box.stroke
      ctx.globalAlpha = 0.6
      ctx.fill()
      ctx.globalAlpha = 1
    }
  } else if (activeTool.value === 'point') {
    drawPointShape({ id: '?', x: px, y: py, type: 'point' }, false, 0.4)
  }

  // Show snap crosshair
  if (snapEnabled.value && activeTool.value !== 'point') {
    const [cx, cy] = worldToCanvas(px, py)
    ctx.strokeStyle = COLORS.preview
    ctx.lineWidth = 1
    ctx.setLineDash([4, 4])
    ctx.beginPath()
    ctx.moveTo(cx - 10, cy)
    ctx.lineTo(cx + 10, cy)
    ctx.moveTo(cx, cy - 10)
    ctx.lineTo(cx, cy + 10)
    ctx.stroke()
    ctx.setLineDash([])
  }
}

function render() {
  if (!ctx) return

  ctx.clearRect(0, 0, canvasW, canvasH)
  ctx.fillStyle = COLORS.bg
  ctx.fillRect(0, 0, canvasW, canvasH)

  // Draw map area with slightly distinct background
  const mw = (map.xMax - map.xMin) * scale
  const mh = (map.yMax - map.yMin) * scale
  if (mw > 0 && mh > 0) {
    ctx.fillStyle = COLORS.mapBg
    ctx.fillRect(mapOffsetX, mapOffsetY, mw, mh)
  }

  drawCheckerboard()
  drawGrid()

  // Draw non-selected obstacles (obstacles first, then points on top)
  for (const o of obstacles.value) {
    if (o.id === selectedId.value) continue
    if (o.type === 'point') continue
    drawObstacle(o, false)
    // Draw hover outline
    if (o.id === hoveredId.value && activeTool.value === 'select' && !hoveredHandle.value) {
      const colors = o.subtype === 'wall' ? COLORS.wall : COLORS[o.type] || COLORS.box
      if (o.type === 'circle') {
        const [cx, cy] = worldToCanvas(o.x, o.y)
        ctx.beginPath()
        ctx.arc(cx, cy, o.radius * scale + 3, 0, Math.PI * 2)
        ctx.strokeStyle = colors.stroke
        ctx.lineWidth = 1
        ctx.globalAlpha = 0.4
        ctx.setLineDash([4, 4])
        ctx.stroke()
        ctx.setLineDash([])
        ctx.globalAlpha = 1
      } else if (o.type === 'line') {
        const cosP = Math.cos(o.psi), sinP = Math.sin(o.psi)
        const hh = o.length / 2
        const [cx1, cy1] = worldToCanvas(o.x - hh * sinP, o.y + hh * cosP)
        const [cx2, cy2] = worldToCanvas(o.x + hh * sinP, o.y - hh * cosP)
        ctx.beginPath()
        ctx.moveTo(cx1, cy1)
        ctx.lineTo(cx2, cy2)
        ctx.strokeStyle = colors.stroke
        ctx.lineWidth = 3
        ctx.globalAlpha = 0.3
        ctx.setLineDash([4, 4])
        ctx.stroke()
        ctx.setLineDash([])
        ctx.globalAlpha = 1
      } else {
        const [cx, cy] = worldToCanvas(o.x, o.y)
        const pad = 3
        ctx.save()
        ctx.translate(cx, cy)
        ctx.rotate(-o.psi)
        ctx.strokeStyle = colors.stroke
        ctx.lineWidth = 1
        ctx.globalAlpha = 0.4
        ctx.setLineDash([4, 4])
        ctx.strokeRect(
          -o.width / 2 * scale - pad, -o.height / 2 * scale - pad,
          o.width * scale + pad * 2, o.height * scale + pad * 2
        )
        ctx.setLineDash([])
        ctx.restore()
        ctx.globalAlpha = 1
      }
    }
  }

  // Draw non-selected points on top of obstacles
  for (const o of obstacles.value) {
    if (o.id === selectedId.value) continue
    if (o.type !== 'point') continue
    drawObstacle(o, false)
  }

  // Draw selected obstacle on top with handles
  const sel = selectedObstacle.value
  if (sel) {
    drawObstacle(sel, true)
    if (activeTool.value === 'select' && sel.type !== 'point') {
      drawHandles(sel)
    }
  }

  // Tool-specific overlays
  if (activeTool.value === 'wall' || activeTool.value === 'line') {
    drawGridPointHighlight()
    if (wallStart) drawWallPreview()
  } else if (activeTool.value === 'circle' || activeTool.value === 'rectangle' || activeTool.value === 'point') {
    if (!dragState && !handleDrag) drawPlacementPreview()
  }

  animFrameId = requestAnimationFrame(render)
}

// ============================================================
// HIT TESTING
// ============================================================
function hitTest(wx, wy) {
  const minHit = 5 / scale

  for (let i = obstacles.value.length - 1; i >= 0; i--) {
    const o = obstacles.value[i]
    if (o.type === 'point') {
      const dx = wx - o.x, dy = wy - o.y
      const hitR = POINT_HIT_RADIUS / scale
      if (dx * dx + dy * dy <= hitR * hitR) return o.id
    } else if (o.type === 'line') {
      // Distance from point to line segment
      const cos = Math.cos(o.psi), sin = Math.sin(o.psi)
      const hh = o.length / 2
      const ax = o.x - hh * sin, ay = o.y + hh * cos
      const bx = o.x + hh * sin, by = o.y - hh * cos
      const abx = bx - ax, aby = by - ay
      const apx = wx - ax, apy = wy - ay
      const t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / (abx * abx + aby * aby)))
      const projx = ax + t * abx, projy = ay + t * aby
      const ddx = wx - projx, ddy = wy - projy
      if (ddx * ddx + ddy * ddy <= minHit * minHit) return o.id
    } else if (o.type === 'circle') {
      const dx = wx - o.x, dy = wy - o.y
      const hitRadius = Math.max(o.radius, minHit)
      if (dx * dx + dy * dy <= hitRadius * hitRadius) return o.id
    } else {
      const dx = wx - o.x, dy = wy - o.y
      const cos = Math.cos(-o.psi), sin = Math.sin(-o.psi)
      const lx = dx * cos - dy * sin
      const ly = dx * sin + dy * cos
      const halfW = Math.max(o.width / 2, minHit)
      const halfH = Math.max(o.height / 2, minHit)
      if (Math.abs(lx) <= halfW && Math.abs(ly) <= halfH) return o.id
    }
  }
  return null
}

// ============================================================
// MOUSE HANDLERS
// ============================================================
function getMouseWorld(e) {
  const canvas = canvasRef.value
  const rect = canvas.getBoundingClientRect()
  const cx = e.clientX - rect.left
  const cy = e.clientY - rect.top
  return canvasToWorld(cx, cy)
}

function onMouseDown(e) {
  if (e.button !== 0) return

  const [wx, wy] = getMouseWorld(e)

  if (activeTool.value === 'select') {
    // First: check if clicking a handle on the currently selected obstacle
    if (selectedObstacle.value && selectedObstacle.value.type !== 'point') {
      const handle = hitTestHandle(wx, wy)
      if (handle) {
        pushUndo()
        dragSnapshotted = true
        const o = selectedObstacle.value
        handleDrag = {
          id: o.id,
          handleType: handle,
          startWorldX: wx,
          startWorldY: wy,
          origX: o.x,
          origY: o.y,
          origWidth: o.width,
          origHeight: o.height,
          origLength: o.length,
          origPsi: o.psi,
          origRadius: o.radius
        }
        isDragging.value = true
        return
      }
    }

    // Second: check if clicking an obstacle body
    const hitId = hitTest(wx, wy)
    if (hitId) {
      pushUndo()
      dragSnapshotted = true
      selectedId.value = hitId
      const o = obstacles.value.find(ob => ob.id === hitId)
      dragState = {
        id: hitId,
        startWorldX: wx,
        startWorldY: wy,
        origX: o.x,
        origY: o.y
      }
      isDragging.value = true
    } else {
      selectedId.value = null
      dragState = null
      handleDrag = null
      isDragging.value = false
    }
  } else if (activeTool.value === 'circle') {
    const px = snapEnabled.value ? snapToGrid(wx) : wx
    const py = snapEnabled.value ? snapToGrid(wy) : wy
    addCircle(px, py)
  } else if (activeTool.value === 'rectangle') {
    const px = snapEnabled.value ? snapToGrid(wx) : wx
    const py = snapEnabled.value ? snapToGrid(wy) : wy
    rectStart = { x: px, y: py }
    isDragging.value = true
  } else if (activeTool.value === 'wall' || activeTool.value === 'line') {
    const gx = snapToGrid(wx)
    const gy = snapToGrid(wy)

    if (!wallStart) {
      wallStart = { x: gx, y: gy }
    } else {
      if (Math.abs(gx - wallStart.x) > 0.001 || Math.abs(gy - wallStart.y) > 0.001) {
        if (activeTool.value === 'wall') addWall(wallStart.x, wallStart.y, gx, gy)
        else addLine(wallStart.x, wallStart.y, gx, gy)
      }
      wallStart = null
    }
  } else if (activeTool.value === 'point') {
    const px = snapEnabled.value ? snapToGrid(wx) : wx
    const py = snapEnabled.value ? snapToGrid(wy) : wy
    addPoint(px, py)
  }
}

function onMouseMove(e) {
  const [wx, wy] = getMouseWorld(e)
  mouseWorld.x = wx
  mouseWorld.y = wy
  mouseInCanvas.value = true

  // Handle drag: resize or rotate
  if (handleDrag && activeTool.value === 'select') {
    const o = obstacles.value.find(ob => ob.id === handleDrag.id)
    if (!o) return

    if (handleDrag.handleType === 'rotate') {
      const dx = wx - o.x
      const dy = wy - o.y
      let newPsi = Math.atan2(dy, dx) - Math.PI / 2
      newPsi = snapAngle(newPsi)
      o.psi = newPsi
    } else if (handleDrag.handleType === 'resize-radius') {
      const dx = wx - o.x, dy = wy - o.y
      let newRadius = Math.sqrt(dx * dx + dy * dy)
      if (snapEnabled.value) newRadius = Math.max(map.gridSize, snapToGrid(newRadius))
      else newRadius = Math.max(0.01, newRadius)
      o.radius = newRadius
    } else if (o.subtype === 'wall' || o.type === 'line') {
      // Wall/line endpoint drag: freely reposition the dragged endpoint, opposite stays fixed
      const cosO = Math.cos(handleDrag.origPsi), sinO = Math.sin(handleDrag.origPsi)
      const origLen = o.type === 'line' ? handleDrag.origLength : handleDrag.origHeight
      const hh = origLen / 2

      // Fixed endpoint is the opposite end (in original world coords)
      const fx = handleDrag.handleType === 'resize-t'
        ? handleDrag.origX + hh * sinO    // bottom endpoint
        : handleDrag.origX - hh * sinO    // top endpoint
      const fy = handleDrag.handleType === 'resize-t'
        ? handleDrag.origY - hh * cosO
        : handleDrag.origY + hh * cosO

      // Snap dragged endpoint to grid
      const mx = snapEnabled.value ? snapToGrid(wx) : wx
      const my = snapEnabled.value ? snapToGrid(wy) : wy

      const ddx = mx - fx, ddy = my - fy
      const newLen = Math.sqrt(ddx * ddx + ddy * ddy)
      if (newLen < 0.01) return

      o.x = (fx + mx) / 2
      o.y = (fy + my) / 2
      if (o.type === 'line') o.length = newLen
      else o.height = newLen
      o.psi = Math.atan2(ddy, ddx) - Math.PI / 2
    } else {
      // Compute mouse in local coords relative to the ORIGINAL center
      const dx = wx - handleDrag.origX, dy = wy - handleDrag.origY
      const cosN = Math.cos(-handleDrag.origPsi), sinN = Math.sin(-handleDrag.origPsi)
      const lx = dx * cosN - dy * sinN
      const ly = dx * sinN + dy * cosN

      const effectiveGs = fineSnap.value ? map.gridSize / snapSubdivision.value : map.gridSize
      const minDim = snapEnabled.value ? effectiveGs : 0.01
      const cosP = Math.cos(handleDrag.origPsi), sinP = Math.sin(handleDrag.origPsi)

      if (handleDrag.handleType === 'resize-r' || handleDrag.handleType === 'resize-l') {
        // Anchor the opposite edge
        const fixedEdge = handleDrag.handleType === 'resize-r'
          ? -handleDrag.origWidth / 2
          :  handleDrag.origWidth / 2

        let newW = handleDrag.handleType === 'resize-r'
          ? lx - fixedEdge
          : fixedEdge - lx

        if (snapEnabled.value) newW = Math.max(minDim, snapToGrid(newW))
        else newW = Math.max(minDim, newW)

        const newCenterLx = handleDrag.handleType === 'resize-r'
          ? fixedEdge + newW / 2
          : fixedEdge - newW / 2

        o.width = newW
        o.x = handleDrag.origX + newCenterLx * cosP
        o.y = handleDrag.origY + newCenterLx * sinP
      } else if (handleDrag.handleType === 'resize-t' || handleDrag.handleType === 'resize-b') {
        const fixedEdge = handleDrag.handleType === 'resize-t'
          ? -handleDrag.origHeight / 2
          :  handleDrag.origHeight / 2

        let newH = handleDrag.handleType === 'resize-t'
          ? ly - fixedEdge
          : fixedEdge - ly

        if (snapEnabled.value) newH = Math.max(minDim, snapToGrid(newH))
        else newH = Math.max(minDim, newH)

        const newCenterLy = handleDrag.handleType === 'resize-t'
          ? fixedEdge + newH / 2
          : fixedEdge - newH / 2

        o.height = newH
        o.x = handleDrag.origX - newCenterLy * sinP
        o.y = handleDrag.origY + newCenterLy * cosP
      } else if (handleDrag.handleType.startsWith('resize-t') || handleDrag.handleType.startsWith('resize-b')) {
        // Corner resize: anchor opposite corner, change both width and height
        const ht = handleDrag.handleType
        const fixedLx = ht === 'resize-tr' || ht === 'resize-br'
          ? -handleDrag.origWidth / 2
          :  handleDrag.origWidth / 2
        const fixedLy = ht === 'resize-tr' || ht === 'resize-tl'
          ? -handleDrag.origHeight / 2
          :  handleDrag.origHeight / 2

        let newW = ht === 'resize-tr' || ht === 'resize-br'
          ? lx - fixedLx : fixedLx - lx
        let newH = ht === 'resize-tr' || ht === 'resize-tl'
          ? ly - fixedLy : fixedLy - ly

        if (snapEnabled.value) {
          newW = Math.max(minDim, snapToGrid(newW))
          newH = Math.max(minDim, snapToGrid(newH))
        } else {
          newW = Math.max(minDim, newW)
          newH = Math.max(minDim, newH)
        }

        const newCenterLx = ht === 'resize-tr' || ht === 'resize-br'
          ? fixedLx + newW / 2 : fixedLx - newW / 2
        const newCenterLy = ht === 'resize-tr' || ht === 'resize-tl'
          ? fixedLy + newH / 2 : fixedLy - newH / 2

        o.width = newW
        o.height = newH
        o.x = handleDrag.origX + newCenterLx * cosP - newCenterLy * sinP
        o.y = handleDrag.origY + newCenterLx * sinP + newCenterLy * cosP
      }
    }
    return
  }

  // Move drag
  if (dragState && activeTool.value === 'select') {
    const o = obstacles.value.find(ob => ob.id === dragState.id)
    if (!o) return

    const rawDx = wx - dragState.startWorldX
    const rawDy = wy - dragState.startWorldY

    if (o.subtype === 'wall' || o.type === 'line' || snapEnabled.value) {
      o.x = snapToGrid(dragState.origX + rawDx)
      o.y = snapToGrid(dragState.origY + rawDy)
    } else {
      o.x = dragState.origX + rawDx
      o.y = dragState.origY + rawDy
    }
    return
  }

  // Hover detection
  if (activeTool.value === 'select') {
    if (selectedObstacle.value && selectedObstacle.value.type !== 'point') {
      const handle = hitTestHandle(wx, wy)
      hoveredHandle.value = handle
      if (handle) {
        hoveredId.value = null
        return
      }
    } else {
      hoveredHandle.value = null
    }
    hoveredId.value = hitTest(wx, wy)
  }
}

function onMouseUp() {
  // Rectangle drag-to-create: finalize on mouse up
  if (rectStart && activeTool.value === 'rectangle') {
    const ex = snapEnabled.value ? snapToGrid(mouseWorld.x) : mouseWorld.x
    const ey = snapEnabled.value ? snapToGrid(mouseWorld.y) : mouseWorld.y
    const w = Math.abs(ex - rectStart.x)
    const h = Math.abs(ey - rectStart.y)
    const effectiveGs = fineSnap.value ? map.gridSize / snapSubdivision.value : map.gridSize
    const minSize = snapEnabled.value ? effectiveGs : 0.01
    if (w >= minSize && h >= minSize) {
      const cx = (rectStart.x + ex) / 2
      const cy = (rectStart.y + ey) / 2
      pushUndo()
      const id = `box-${counters.box++}`
      obstacles.value.push({
        id, type: 'box', subtype: 'box',
        x: cx, y: cy, width: w, height: h, psi: 0
      })
      selectedId.value = id
    }
    rectStart = null
    isDragging.value = false
    return
  }

  // If we snapshotted but nothing actually changed, pop the undo entry
  if (dragSnapshotted && undoStack.value.length > 0) {
    const current = snapshotObstacles()
    if (undoStack.value[undoStack.value.length - 1] === current) {
      undoStack.value.pop()
    }
  }
  dragState = null
  handleDrag = null
  isDragging.value = false
  dragSnapshotted = false
}

function onMouseLeave() {
  mouseInCanvas.value = false
  dragState = null
  handleDrag = null
  rectStart = null
  isDragging.value = false
  hoveredId.value = null
  hoveredHandle.value = null
}

// ============================================================
// OBSTACLE ACTIONS
// ============================================================
function addCircle(wx, wy) {
  pushUndo()
  const id = `circle-${counters.circle++}`
  obstacles.value.push({
    id, type: 'circle', subtype: 'circle',
    x: wx, y: wy, radius: defaults.circleRadius
  })
  selectedId.value = id
}

function addRectangle(wx, wy) {
  pushUndo()
  const id = `box-${counters.box++}`
  obstacles.value.push({
    id, type: 'box', subtype: 'box',
    x: wx, y: wy,
    width: defaults.rectWidth, height: defaults.rectHeight,
    psi: defaults.rectAngle * Math.PI / 180
  })
  selectedId.value = id
}

function addWall(x1, y1, x2, y2) {
  pushUndo()
  const dx = x2 - x1, dy = y2 - y1
  const length = Math.sqrt(dx * dx + dy * dy)
  const psi = Math.atan2(dy, dx) - Math.PI / 2

  const id = `wall-${counters.wall++}`
  obstacles.value.push({
    id, type: 'box', subtype: 'wall',
    x: (x1 + x2) / 2, y: (y1 + y2) / 2,
    width: defaults.wallThickness, height: length, psi
  })
  selectedId.value = id
}

function addLine(x1, y1, x2, y2) {
  pushUndo()
  const dx = x2 - x1, dy = y2 - y1
  const length = Math.sqrt(dx * dx + dy * dy)
  const psi = Math.atan2(dy, dx) - Math.PI / 2

  const id = `line-${counters.line++}`
  obstacles.value.push({
    id, type: 'line', subtype: 'line',
    x: (x1 + x2) / 2, y: (y1 + y2) / 2,
    length, psi
  })
  selectedId.value = id
}

function addPoint(wx, wy) {
  pushUndo()
  const id = `point-${counters.point++}`
  obstacles.value.push({
    id, type: 'point', subtype: 'point',
    x: wx, y: wy
  })
  selectedId.value = id
}

function onIdInput(event, obstacle) {
  const newId = event.target.value
  // Update selectedId to track the renamed obstacle
  if (selectedId.value === obstacle.id) {
    selectedId.value = newId
  }
  obstacle.id = newId
}

function onPropertyFocus() {
  pushUndo()
}

function selectObstacle(id) {
  selectedId.value = id
  activeTool.value = 'select'
}

function deleteObstacle(id) {
  pushUndo()
  obstacles.value = obstacles.value.filter(o => o.id !== id)
  if (selectedId.value === id) selectedId.value = null
}

function deleteSelected() {
  if (selectedId.value) deleteObstacle(selectedId.value)
}

function clearAll() {
  if (obstacles.value.length === 0) return
  pushUndo()
  obstacles.value = []
  selectedId.value = null
  counters.circle = 1
  counters.box = 1
  counters.wall = 1
  counters.line = 1
  counters.point = 1
  wallStart = null
  rectStart = null
  toast('Canvas cleared')
}

function setTool(id) {
  activeTool.value = id
  wallStart = null
  rectStart = null
  if (id !== 'select') selectedId.value = null
}

// ============================================================
// YAML EXPORT
// ============================================================
function fmt(n) {
  return parseFloat(parseFloat(n).toFixed(4))
}

function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      toast('YAML copied to clipboard')
    }).catch(() => {
      toast('Failed to copy — check browser permissions')
    })
  } else {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    try {
      document.execCommand('copy')
      toast('YAML copied to clipboard')
    } catch {
      toast('Failed to copy — clipboard not available')
    }
    document.body.removeChild(textarea)
  }
}

function exportYaml() {
  const obs = obstacles.value.filter(o => o.type !== 'point' && o.type !== 'line')
  const lines = obstacles.value.filter(o => o.type === 'line')
  const pts = obstacles.value.filter(o => o.type === 'point')

  if (obs.length === 0 && lines.length === 0 && pts.length === 0) {
    toast('No obstacles, lines, or points to export')
    return
  }

  let yaml = ''

  if (obs.length > 0) {
    yaml += '  obstacles:\n'
    for (const o of obs) {
      yaml += `    - id: ${o.id}\n`
      yaml += `      type: ${o.type}\n`
      if (o.type === 'circle') {
        yaml += `      radius: ${fmt(o.radius)}\n`
        yaml += `      state: [ ${fmt(o.x)} , ${fmt(o.y)} , 0 ]\n`
      } else {
        yaml += `      size: [ ${fmt(o.width)} , ${fmt(o.height)} ]\n`
        yaml += `      state: [ ${fmt(o.x)} , ${fmt(o.y)} , ${fmt(o.psi)} ]\n`
      }
    }
  }

  if (lines.length > 0) {
    if (yaml) yaml += '\n'
    yaml += '  lines:\n'
    for (const o of lines) {
      const cos = Math.cos(o.psi), sin = Math.sin(o.psi)
      const hh = o.length / 2
      yaml += `    - id: ${o.id}\n`
      yaml += `      start: [ ${fmt(o.x - hh * sin)} , ${fmt(o.y + hh * cos)} ]\n`
      yaml += `      end: [ ${fmt(o.x + hh * sin)} , ${fmt(o.y - hh * cos)} ]\n`
    }
  }

  if (pts.length > 0) {
    if (yaml) yaml += '\n'
    yaml += '  points:\n'
    for (const p of pts) {
      yaml += `    - id: ${p.id}\n`
      yaml += `      position: [ ${fmt(p.x)} , ${fmt(p.y)} ]\n`
    }
  }

  copyToClipboard(yaml)
}

function doImport() {
  const text = importText.value.trim()
  if (!text) { toast('No YAML to import'); return }

  try {
    pushUndo()

    // Clear current state
    obstacles.value = []
    counters.circle = 1; counters.box = 1; counters.wall = 1; counters.line = 1; counters.point = 1
    selectedId.value = null
    wallStart = null

    // Simple line-by-line YAML parser for our known format
    const imported = []
    let currentSection = null  // 'obstacles' | 'lines' | 'points'
    let currentItem = null

    for (const rawLine of text.split('\n')) {
      const line = rawLine.replace(/\r$/, '')
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue

      // Section headers
      if (/^\s*obstacles:\s*$/.test(line)) { currentSection = 'obstacles'; currentItem = null; continue }
      if (/^\s*lines:\s*$/.test(line)) { currentSection = 'lines'; currentItem = null; continue }
      if (/^\s*points:\s*$/.test(line)) { currentSection = 'points'; currentItem = null; continue }

      // New list item
      if (trimmed.startsWith('- ')) {
        if (currentItem) imported.push(currentItem)
        currentItem = { _section: currentSection }
        // Parse inline key on the "- " line: "- id: foo"
        const rest = trimmed.slice(2).trim()
        if (rest) {
          const m = rest.match(/^(\w+):\s*(.+)$/)
          if (m) currentItem[m[1]] = m[2].trim()
        }
        continue
      }

      // Key-value continuation of current item
      if (currentItem && trimmed.includes(':')) {
        const m = trimmed.match(/^(\w+):\s*(.+)$/)
        if (m) currentItem[m[1]] = m[2].trim()
      }
    }
    if (currentItem) imported.push(currentItem)

    // Helper to parse "[ 1.5 , 2.0 , 0 ]" → array of numbers
    const parseArr = (s) => {
      if (!s) return null
      const inner = s.replace(/^\[/, '').replace(/\]$/, '')
      return inner.split(',').map(v => parseFloat(v.trim()))
    }

    // Deduplicate IDs during import
    const usedIds = new Set()
    const uniqueId = (id) => {
      if (!usedIds.has(id)) { usedIds.add(id); return id }
      let n = 2
      while (usedIds.has(`${id}-${n}`)) n++
      const newId = `${id}-${n}`
      usedIds.add(newId)
      return newId
    }

    for (const item of imported) {
      if (item._section === 'obstacles') {
        const id = uniqueId(item.id || 'imported')
        const type = item.type || 'box'

        if (type === 'circle') {
          const radius = parseFloat(item.radius) || 0.15
          const state = parseArr(item.state) || [0, 0, 0]
          obstacles.value.push({
            id, type: 'circle', subtype: 'circle',
            x: state[0], y: state[1], radius
          })
        } else {
          const size = parseArr(item.size) || [0.5, 0.5]
          const state = parseArr(item.state) || [0, 0, 0]
          const isWall = id.startsWith('wall')
          obstacles.value.push({
            id, type: 'box', subtype: isWall ? 'wall' : 'box',
            x: state[0], y: state[1],
            width: size[0], height: size[1], psi: state[2]
          })
        }
      } else if (item._section === 'lines') {
        const id = uniqueId(item.id || 'line')
        const start = parseArr(item.start) || [0, 0]
        const end = parseArr(item.end) || [1, 1]
        const dx = end[0] - start[0], dy = end[1] - start[1]
        const length = Math.sqrt(dx * dx + dy * dy)
        const psi = Math.atan2(dy, dx) - Math.PI / 2
        obstacles.value.push({
          id, type: 'line', subtype: 'line',
          x: (start[0] + end[0]) / 2, y: (start[1] + end[1]) / 2,
          length, psi
        })
      } else if (item._section === 'points') {
        const id = uniqueId(item.id || 'point')
        const pos = parseArr(item.position) || [0, 0]
        obstacles.value.push({
          id, type: 'point', subtype: 'point',
          x: pos[0], y: pos[1]
        })
      }
    }

    // Set counters from highest existing IDs so new elements don't collide
    const maxNum = (prefix) => {
      let max = 0
      for (const o of obstacles.value) {
        const m = o.id.match(new RegExp(`^${prefix}-(\\d+)`))
        if (m) max = Math.max(max, parseInt(m[1]))
      }
      return max + 1
    }
    counters.circle = maxNum('circle')
    counters.box = maxNum('box')
    counters.wall = maxNum('wall')
    counters.line = maxNum('line')
    counters.point = maxNum('point')

    showImportModal.value = false
    importText.value = ''
    toast(`Imported ${obstacles.value.length} element(s)`)
  } catch (err) {
    toast('Import failed — check YAML format')
  }
}

function toast(msg) {
  toastMessage.value = msg
  showToast.value = true
  setTimeout(() => { showToast.value = false }, 2500)
}

// ============================================================
// KEYBOARD
// ============================================================
function onKeyDown(e) {
  // Undo/Redo works even when focused on inputs
  if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
    e.preventDefault()
    undo()
    return
  }
  if ((e.metaKey || e.ctrlKey) && (e.key === 'z' && e.shiftKey || e.key === 'y')) {
    e.preventDefault()
    redo()
    return
  }

  // Copy
  if ((e.metaKey || e.ctrlKey) && e.key === 'c') {
    if (selectedObstacle.value) {
      clipboard = JSON.parse(JSON.stringify(selectedObstacle.value))
      toast('Copied')
    }
    return
  }

  // Paste
  if ((e.metaKey || e.ctrlKey) && e.key === 'v') {
    if (!clipboard) return
    e.preventDefault()
    const obj = JSON.parse(JSON.stringify(clipboard))
    const key = obj.subtype
    const id = `${key}-${counters[key]++}`
    obj.id = id
    obj.x = (obj.x || 0) + 0.25
    obj.y = (obj.y || 0) - 0.25
    pushUndo()
    obstacles.value.push(obj)
    selectedId.value = id
    toast('Pasted')
    return
  }

  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return

  if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault()
    deleteSelected()
  } else if (e.key === 'Escape') {
    selectedId.value = null
    wallStart = null
    rectStart = null
    handleDrag = null
    if (activeTool.value !== 'select') activeTool.value = 'select'
  } else if (e.key === '1') {
    setTool('select')
  } else if (e.key === '2') {
    setTool('circle')
  } else if (e.key === '3') {
    setTool('rectangle')
  } else if (e.key === '4') {
    setTool('wall')
  } else if (e.key === '5') {
    setTool('line')
  } else if (e.key === '6') {
    setTool('point')
  } else if (e.key === 's' || e.key === 'S') {
    snapEnabled.value = !snapEnabled.value
  }
}

function onFineSnapDown(e) {
  if (e.key === 'Control') fineSnap.value = true
}

function onFineSnapUp(e) {
  if (e.key === 'Control') fineSnap.value = false
}

function onFineSnapBlur() {
  fineSnap.value = false
}

// ============================================================
// PERSISTENCE (localStorage)
// ============================================================
const STORAGE_KEY = 'testbed-creator-state'

function saveState() {
  try {
    const state = {
      obstacles: obstacles.value,
      counters: { ...counters },
      map: { ...map },
      checkerboard: { ...checkerboard },
      defaults: { ...defaults },
      snapEnabled: snapEnabled.value,
      snapSubdivision: snapSubdivision.value
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch { /* quota exceeded or unavailable */ }
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const state = JSON.parse(raw)

    if (Array.isArray(state.obstacles)) obstacles.value = state.obstacles
    if (state.counters) Object.assign(counters, state.counters)
    if (state.map) Object.assign(map, state.map)
    if (state.checkerboard) Object.assign(checkerboard, state.checkerboard)
    if (state.defaults) Object.assign(defaults, state.defaults)
    if (typeof state.snapEnabled === 'boolean') snapEnabled.value = state.snapEnabled
    if (typeof state.snapSubdivision === 'number' && state.snapSubdivision >= 2) snapSubdivision.value = state.snapSubdivision
  } catch { /* corrupted data, start fresh */ }
}

// ============================================================
// LIFECYCLE
// ============================================================
let resizeObserver = null

onMounted(() => {
  const savedTheme = localStorage.getItem('testbed-creator-theme')
  if (savedTheme === 'light') darkMode.value = false
  COLORS = darkMode.value ? DARK_COLORS : LIGHT_COLORS

  loadState()
  computeLayout()
  render()

  resizeObserver = new ResizeObserver(() => {
    computeLayout()
  })
  resizeObserver.observe(containerRef.value)

  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keydown', onFineSnapDown)
  window.addEventListener('keyup', onFineSnapUp)
  window.addEventListener('blur', onFineSnapBlur)
})

onUnmounted(() => {
  if (animFrameId) cancelAnimationFrame(animFrameId)
  if (resizeObserver) resizeObserver.disconnect()
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keydown', onFineSnapDown)
  window.removeEventListener('keyup', onFineSnapUp)
  window.removeEventListener('blur', onFineSnapBlur)
})

watch(() => [map.xMin, map.xMax, map.yMin, map.yMax, map.gridSize], () => {
  computeLayout()
})

// Theme switching
watch(darkMode, (isDark) => {
  COLORS = isDark ? DARK_COLORS : LIGHT_COLORS
  document.body.style.background = isDark ? '#0a0a0f' : '#f5f6f8'
  document.body.style.color = isDark ? '#e0e0e0' : '#2c3040'
  localStorage.setItem('testbed-creator-theme', isDark ? 'dark' : 'light')
})

// Save state on any change
watch(
  () => [
    JSON.stringify(obstacles.value),
    counters.circle, counters.box, counters.wall, counters.point,
    map.xMin, map.xMax, map.yMin, map.yMax, map.gridSize,
    checkerboard.enabled, checkerboard.size,
    defaults.circleRadius, defaults.rectWidth, defaults.rectHeight, defaults.rectAngle, defaults.wallThickness,
    snapEnabled.value, snapSubdivision.value
  ],
  saveState,
  { deep: true }
)
</script>

<style scoped>
/* ============================================================
   LAYOUT
   ============================================================ */
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #0a0a0f;
  color: #c8cdd5;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 44px;
  padding: 0 16px;
  background: #0f1119;
  border-bottom: 1px solid #1a1f2e;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-logo {
  height: 22px;
  width: auto;
  opacity: 0.85;
}

.header h1 {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 2px;
  color: #8892a5;
}

.header-center {
  flex: 1;
  text-align: center;
}

.coords {
  font-size: 11px;
  color: #555e75;
  letter-spacing: 1px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.header-sep {
  width: 1px;
  height: 20px;
  background: #1e2233;
  margin: 0 2px;
}

.main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ============================================================
   SIDEBARS
   ============================================================ */
.sidebar {
  width: 210px;
  flex-shrink: 0;
  overflow-y: auto;
  padding: 8px;
  background: #0c0e16;
}

.sidebar-left {
  border-right: 1px solid #1a1f2e;
}

.sidebar-right {
  border-left: 1px solid #1a1f2e;
}

.panel {
  margin-bottom: 6px;
  padding: 10px;
  background: #10131c;
  border-radius: 6px;
  border: 1px solid #1a1f2e;
}

.panel-title {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: #555e75;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.badge {
  background: #1a1f2e;
  color: #8892a5;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 10px;
}

/* ============================================================
   TOOLS
   ============================================================ */
.tool-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
}

.tool-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 4px;
  background: #151821;
  border: 1px solid #1e2233;
  border-radius: 5px;
  color: #8892a5;
  cursor: pointer;
  font-family: inherit;
  font-size: 10px;
  transition: all 0.15s;
  position: relative;
}

.tool-btn:hover {
  background: #1a1f30;
  border-color: #2a3048;
  color: #c8cdd5;
}

.tool-btn.active {
  background: #1a2535;
  border-color: #4ecdc4;
  color: #4ecdc4;
}

.tool-icon {
  font-size: 18px;
  line-height: 1;
}

.tool-label {
  font-size: 9px;
  font-weight: 500;
}

.tool-key {
  position: absolute;
  top: 2px;
  right: 4px;
  font-size: 8px;
  color: #3a4258;
}

/* ============================================================
   SNAP / CHECKERBOARD TOGGLE
   ============================================================ */
.toggle-row {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
  padding: 2px 0;
}

.toggle-switch {
  width: 32px;
  height: 18px;
  border-radius: 9px;
  background: #1e2233;
  border: 1px solid #2a3048;
  position: relative;
  transition: all 0.2s;
  flex-shrink: 0;
}

.toggle-switch.active {
  background: #1a3535;
  border-color: #4ecdc4;
}

.toggle-knob {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #555e75;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: all 0.2s;
}

.toggle-switch.active .toggle-knob {
  left: 16px;
  background: #4ecdc4;
}

.toggle-label {
  font-size: 10px;
  color: #8892a5;
  flex: 1;
}

/* ============================================================
   FORM FIELDS
   ============================================================ */
.field-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.field-row label {
  font-size: 10px;
  color: #555e75;
  min-width: 40px;
  flex-shrink: 0;
}

.field-row input {
  background: #151821;
  border: 1px solid #1e2233;
  border-radius: 4px;
  padding: 4px 6px;
  color: #c8cdd5;
  font-family: inherit;
  font-size: 11px;
  outline: none;
  transition: border-color 0.15s;
}

.field-row input:focus {
  border-color: #4ecdc4;
}

.field-sm {
  width: 52px;
}

.field-full {
  flex: 1;
  min-width: 0;
}

.field-sep {
  font-size: 9px;
  color: #3a4258;
}

.field-unit {
  font-size: 9px;
  color: #3a4258;
  flex-shrink: 0;
}

.hint {
  font-size: 10px;
  color: #3a4258;
  font-style: italic;
  padding: 4px 0;
}

/* ============================================================
   BUTTONS
   ============================================================ */
.btn {
  padding: 6px 14px;
  border: 1px solid #1e2233;
  border-radius: 5px;
  font-family: inherit;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-icon {
  background: #151821;
  color: #8892a5;
  border-color: #1e2233;
  font-size: 15px;
  padding: 4px 8px;
  line-height: 1;
}

.btn-icon:hover:not(:disabled) {
  background: #1a1f30;
  border-color: #3a4258;
  color: #c8cdd5;
}

.btn-icon:disabled {
  opacity: 0.3;
  cursor: default;
}

.btn-snap {
  background: #151821;
  color: #555e75;
  border-color: #1e2233;
}

.btn-snap.active {
  background: #1a3535;
  border-color: #4ecdc4;
  color: #4ecdc4;
}

.btn-snap:hover {
  border-color: #3a4258;
}

.btn-clear {
  background: #1a1520;
  border-color: #555e75;
  color: #8892a5;
}

.btn-clear:hover {
  background: #2a1515;
  border-color: #ff6b6b;
  color: #ff6b6b;
}

.btn-export {
  background: #162a2a;
  border-color: #4ecdc4;
  color: #4ecdc4;
}

.btn-export:hover {
  background: #1a3535;
}

.btn-delete {
  width: 100%;
  margin-top: 8px;
  background: #2a1515;
  border-color: #ff6b6b;
  color: #ff6b6b;
}

.btn-delete:hover {
  background: #351a1a;
}

/* ============================================================
   OBSTACLE LIST
   ============================================================ */
.obstacle-list {
  max-height: 300px;
  overflow-y: auto;
}

.obstacle-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.1s;
}

.obstacle-item:hover {
  background: #151821;
}

.obstacle-item.selected {
  background: #1a2535;
}

.obstacle-id {
  flex: 1;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.type-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.type-dot.circle { background: #4ecdc4; }
.type-dot.box { background: #ff6b6b; }
.type-dot.wall { background: #feca57; border-radius: 2px; }
.type-dot.line { background: #ff9f43; border-radius: 2px; width: 12px; height: 3px; }
.type-dot.point { background: #a78bfa; }

.item-delete {
  background: none;
  border: none;
  color: #3a4258;
  cursor: pointer;
  font-size: 14px;
  padding: 0 2px;
  line-height: 1;
  font-family: inherit;
  transition: color 0.1s;
}

.item-delete:hover {
  color: #ff6b6b;
}

/* ============================================================
   CANVAS
   ============================================================ */
.canvas-container {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.canvas-container canvas {
  display: block;
  width: 100%;
  height: 100%;
}

/* ============================================================
   TOAST
   ============================================================ */
.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background: #1a2535;
  border: 1px solid #4ecdc4;
  color: #4ecdc4;
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  z-index: 100;
  pointer-events: none;
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(12px);
}

.btn-theme {
  font-size: 16px !important;
  line-height: 1;
}

.btn-import {
  background: #1a2030;
  border-color: #8892a5;
  color: #8892a5;
}

.btn-import:hover {
  background: #1a2535;
  border-color: #c8cdd5;
  color: #c8cdd5;
}

/* ============================================================
   MODAL
   ============================================================ */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.modal {
  background: #10131c;
  border: 1px solid #1a1f2e;
  border-radius: 8px;
  padding: 20px;
  width: 520px;
  max-width: 90vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.modal-title {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 1px;
  color: #8892a5;
}

.modal-textarea {
  width: 100%;
  height: 300px;
  background: #151821;
  border: 1px solid #1e2233;
  border-radius: 6px;
  padding: 10px;
  color: #c8cdd5;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  resize: vertical;
  outline: none;
}

.modal-textarea:focus {
  border-color: #4ecdc4;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* ============================================================
   LIGHT THEME
   ============================================================ */
.app.light {
  background: #f5f6f8;
  color: #2c3040;
}

.app.light .header {
  background: #ffffff;
  border-bottom-color: #dde0e6;
}

.app.light .header h1 {
  color: #5a6478;
}

.app.light .header-logo {
  filter: none;
}

.app.light .coords {
  color: #8892a5;
}

.app.light .header-sep {
  background: #dde0e6;
}

.app.light .sidebar {
  background: #f0f1f4;
}

.app.light .sidebar-left {
  border-right-color: #dde0e6;
}

.app.light .sidebar-right {
  border-left-color: #dde0e6;
}

.app.light .panel {
  background: #ffffff;
  border-color: #dde0e6;
}

.app.light .panel-title {
  color: #8892a5;
}

.app.light .badge {
  background: #e4e6ea;
  color: #5a6478;
}

.app.light .tool-btn {
  background: #f0f1f4;
  border-color: #dde0e6;
  color: #5a6478;
}

.app.light .tool-btn:hover {
  background: #e4e6ea;
  border-color: #c8ced8;
  color: #2c3040;
}

.app.light .tool-btn.active {
  background: #dff0ee;
  border-color: #2ba89f;
  color: #2ba89f;
}

.app.light .tool-key {
  color: #b8bcc8;
}

.app.light .toggle-switch {
  background: #dde0e6;
  border-color: #c8ced8;
}

.app.light .toggle-switch.active {
  background: #dff0ee;
  border-color: #2ba89f;
}

.app.light .toggle-knob {
  background: #a0a8b8;
}

.app.light .toggle-switch.active .toggle-knob {
  background: #2ba89f;
}

.app.light .toggle-label {
  color: #5a6478;
}

.app.light .field-row label {
  color: #8892a5;
}

.app.light .field-row input {
  background: #f5f6f8;
  border-color: #d0d4dc;
  color: #2c3040;
}

.app.light .field-row input:focus {
  border-color: #2ba89f;
}

.app.light .field-sep {
  color: #b8bcc8;
}

.app.light .field-unit {
  color: #b8bcc8;
}

.app.light .hint {
  color: #a0a8b8;
}

.app.light .btn {
  border-color: #d0d4dc;
}

.app.light .btn-icon {
  background: #f0f1f4;
  color: #5a6478;
  border-color: #d0d4dc;
}

.app.light .btn-icon:hover:not(:disabled) {
  background: #e4e6ea;
  border-color: #b8bcc8;
  color: #2c3040;
}

.app.light .btn-snap {
  background: #f0f1f4;
  color: #8892a5;
  border-color: #d0d4dc;
}

.app.light .btn-snap.active {
  background: #dff0ee;
  border-color: #2ba89f;
  color: #2ba89f;
}

.app.light .btn-snap:hover {
  border-color: #b8bcc8;
}

.app.light .btn-clear {
  background: #f5f0f5;
  border-color: #d0d4dc;
  color: #5a6478;
}

.app.light .btn-clear:hover {
  background: #fce8e8;
  border-color: #e04545;
  color: #e04545;
}

.app.light .btn-export {
  background: #dff0ee;
  border-color: #2ba89f;
  color: #2ba89f;
}

.app.light .btn-export:hover {
  background: #d0ebe8;
}

.app.light .btn-delete {
  background: #fce8e8;
  border-color: #e04545;
  color: #e04545;
}

.app.light .btn-delete:hover {
  background: #f8d0d0;
}

.app.light .obstacle-item:hover {
  background: #f0f1f4;
}

.app.light .obstacle-item.selected {
  background: #dff0ee;
}

.app.light .item-delete {
  color: #b8bcc8;
}

.app.light .item-delete:hover {
  color: #e04545;
}

.app.light .btn-import {
  background: #f0f1f4;
  border-color: #b8bcc8;
  color: #5a6478;
}

.app.light .btn-import:hover {
  background: #e4e6ea;
  border-color: #8892a5;
  color: #2c3040;
}

.app.light .modal {
  background: #ffffff;
  border-color: #dde0e6;
}

.app.light .modal-title {
  color: #5a6478;
}

.app.light .modal-textarea {
  background: #f5f6f8;
  border-color: #d0d4dc;
  color: #2c3040;
}

.app.light .modal-textarea:focus {
  border-color: #2ba89f;
}

.app.light .toast {
  background: #ffffff;
  border-color: #2ba89f;
  color: #2ba89f;
}
</style>
