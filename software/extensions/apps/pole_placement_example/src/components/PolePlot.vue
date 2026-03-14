<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

const props = defineProps({
  poles: Array,      // [{re, im}, ...]
  darkMode: Boolean,
})

const emit = defineEmits(['poleDragged'])

const canvasRef = ref(null)
let ctx = null
let resizeObs = null

// View bounds (complex plane)
const viewRe = ref([-22, 5])
const viewIm = ref([-10, 10])

// Dragging state
const dragging = ref(null)  // { index, re, im } — tracks last drag position

// Pole colors (matching the control groups)
const POLE_COLORS = ['#45aaf2', '#e74c3c', '#2ecc71', '#2ecc71', '#45aaf2', '#f39c12']
const POLE_LABELS = ['p0', 'p1', 'p2', 'p2*', 'p4', 'p5']

// ── Coordinate mapping ─────────────────────────────────────────────────────

function reToX(re) {
  const canvas = canvasRef.value
  if (!canvas) return 0
  const w = canvas.width
  return (re - viewRe.value[0]) / (viewRe.value[1] - viewRe.value[0]) * w
}

function imToY(im) {
  const canvas = canvasRef.value
  if (!canvas) return 0
  const h = canvas.height
  return h - (im - viewIm.value[0]) / (viewIm.value[1] - viewIm.value[0]) * h
}

function xToRe(x) {
  const canvas = canvasRef.value
  if (!canvas) return 0
  const w = canvas.getBoundingClientRect().width
  return viewRe.value[0] + x / w * (viewRe.value[1] - viewRe.value[0])
}

function yToIm(y) {
  const canvas = canvasRef.value
  if (!canvas) return 0
  const h = canvas.getBoundingClientRect().height
  return viewIm.value[0] + (h - y) / h * (viewIm.value[1] - viewIm.value[0])
}

// ── Drawing ─────────────────────────────────────────────────────────────────

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  ctx = canvas.getContext('2d')

  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)

  const w = rect.width, h = rect.height

  // Background
  ctx.fillStyle = props.darkMode ? '#0e0e16' : '#f4f4f8'
  ctx.fillRect(0, 0, w, h)

  // Grid
  ctx.strokeStyle = props.darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'
  ctx.lineWidth = 1
  const gridStepRe = 5, gridStepIm = 5
  for (let re = Math.ceil(viewRe.value[0] / gridStepRe) * gridStepRe; re <= viewRe.value[1]; re += gridStepRe) {
    const x = (re - viewRe.value[0]) / (viewRe.value[1] - viewRe.value[0]) * w
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke()
  }
  for (let im = Math.ceil(viewIm.value[0] / gridStepIm) * gridStepIm; im <= viewIm.value[1]; im += gridStepIm) {
    const y = h - (im - viewIm.value[0]) / (viewIm.value[1] - viewIm.value[0]) * h
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke()
  }

  // Axes
  const axisColor = props.darkMode ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.2)'
  ctx.strokeStyle = axisColor
  ctx.lineWidth = 1.5

  // Real axis (im=0)
  const y0 = h - (0 - viewIm.value[0]) / (viewIm.value[1] - viewIm.value[0]) * h
  ctx.beginPath(); ctx.moveTo(0, y0); ctx.lineTo(w, y0); ctx.stroke()

  // Imaginary axis (re=0)
  const x0 = (0 - viewRe.value[0]) / (viewRe.value[1] - viewRe.value[0]) * w
  ctx.beginPath(); ctx.moveTo(x0, 0); ctx.lineTo(x0, h); ctx.stroke()

  // Stability boundary (re=0 line, highlighted)
  ctx.strokeStyle = props.darkMode ? 'rgba(231, 76, 60, 0.3)' : 'rgba(192, 57, 43, 0.2)'
  ctx.lineWidth = 2
  ctx.setLineDash([4, 4])
  ctx.beginPath(); ctx.moveTo(x0, 0); ctx.lineTo(x0, h); ctx.stroke()
  ctx.setLineDash([])

  // Stable region label
  ctx.font = '10px JetBrains Mono'
  ctx.fillStyle = props.darkMode ? 'rgba(46, 204, 113, 0.4)' : 'rgba(39, 174, 96, 0.3)'
  ctx.fillText('stable', x0 - 40, y0 - 6)
  ctx.fillStyle = props.darkMode ? 'rgba(231, 76, 60, 0.4)' : 'rgba(192, 57, 43, 0.3)'
  ctx.fillText('unstable', x0 + 6, y0 - 6)

  // Axis labels
  ctx.font = '10px JetBrains Mono'
  ctx.fillStyle = props.darkMode ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)'
  ctx.fillText('Re', w - 20, y0 - 6)
  ctx.fillText('Im', x0 + 6, 14)

  // Tick labels
  ctx.font = '9px JetBrains Mono'
  ctx.fillStyle = props.darkMode ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.25)'
  for (let re = Math.ceil(viewRe.value[0] / gridStepRe) * gridStepRe; re <= viewRe.value[1]; re += gridStepRe) {
    if (re === 0) continue
    const x = (re - viewRe.value[0]) / (viewRe.value[1] - viewRe.value[0]) * w
    ctx.fillText(String(re), x + 2, y0 + 12)
  }
  for (let im = Math.ceil(viewIm.value[0] / gridStepIm) * gridStepIm; im <= viewIm.value[1]; im += gridStepIm) {
    if (im === 0) continue
    const y = h - (im - viewIm.value[0]) / (viewIm.value[1] - viewIm.value[0]) * h
    ctx.fillText(String(im) + 'j', x0 + 6, y - 2)
  }

  // Draw poles
  if (!props.poles) return
  for (let i = 0; i < props.poles.length; i++) {
    // Use drag preview position if this pole (or its conjugate) is being dragged
    let p = props.poles[i]
    if (dragging.value && dragging.value.re !== undefined) {
      const di = dragging.value.index
      if (di === i) {
        p = { re: dragging.value.re, im: dragging.value.im }
      } else if ((di === 2 && i === 3) || (di === 3 && i === 2)) {
        // Conjugate pair: mirror imaginary part
        p = { re: dragging.value.re, im: -dragging.value.im }
      }
    }
    const px = (p.re - viewRe.value[0]) / (viewRe.value[1] - viewRe.value[0]) * w
    const py = h - (p.im - viewIm.value[0]) / (viewIm.value[1] - viewIm.value[0]) * h

    const color = POLE_COLORS[i]
    const isHovered = dragging.value && dragging.value.index === i

    // Glow
    ctx.beginPath()
    ctx.arc(px, py, isHovered ? 14 : 10, 0, Math.PI * 2)
    ctx.fillStyle = color + '20'
    ctx.fill()

    // Cross (×) marker
    const sz = isHovered ? 8 : 6
    ctx.strokeStyle = color
    ctx.lineWidth = isHovered ? 2.5 : 2
    ctx.beginPath()
    ctx.moveTo(px - sz, py - sz); ctx.lineTo(px + sz, py + sz)
    ctx.moveTo(px + sz, py - sz); ctx.lineTo(px - sz, py + sz)
    ctx.stroke()

    // Label
    ctx.font = '9px JetBrains Mono'
    ctx.fillStyle = color
    const label = POLE_LABELS[i]
    ctx.fillText(label, px + sz + 3, py - 3)
  }
}

// ── Interaction ─────────────────────────────────────────────────────────────

function findNearestPole(mx, my) {
  if (!props.poles) return null
  const canvas = canvasRef.value
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  const w = rect.width, h = rect.height

  let bestDist = 20  // pixel threshold
  let bestIdx = null

  for (let i = 0; i < props.poles.length; i++) {
    const p = props.poles[i]
    const px = (p.re - viewRe.value[0]) / (viewRe.value[1] - viewRe.value[0]) * w
    const py = h - (p.im - viewIm.value[0]) / (viewIm.value[1] - viewIm.value[0]) * h
    const dist = Math.hypot(mx - px, my - py)
    if (dist < bestDist) { bestDist = dist; bestIdx = i }
  }
  return bestIdx
}

function onMouseDown(e) {
  const rect = canvasRef.value.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  const idx = findNearestPole(mx, my)
  if (idx !== null) {
    dragging.value = { index: idx }
    e.preventDefault()
  }
}

function onMouseMove(e) {
  if (!dragging.value) {
    // Just update cursor
    const rect = canvasRef.value.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const idx = findNearestPole(mx, my)
    canvasRef.value.style.cursor = idx !== null ? 'grab' : 'default'
    return
  }

  canvasRef.value.style.cursor = 'grabbing'
  const rect = canvasRef.value.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top

  let re = xToRe(mx)
  let im = yToIm(my)

  // Clamp to reasonable bounds
  re = Math.max(-30, Math.min(5, re))
  im = Math.max(-15, Math.min(15, im))

  // Snap to real axis for real poles
  const idx = dragging.value.index
  if (idx === 0 || idx === 1 || idx === 4 || idx === 5) {
    im = 0
  }

  dragging.value.re = Math.round(re * 10) / 10
  dragging.value.im = Math.round(im * 10) / 10
  emit('poleDragged', dragging.value.index, dragging.value.re, dragging.value.im)
  draw()
}

function onMouseUp() {
  // Emit final pole position only on release
  if (dragging.value && dragging.value.re !== undefined) {
    emit('poleDragged', dragging.value.index, dragging.value.re, dragging.value.im)
  }
  dragging.value = null
  if (canvasRef.value) canvasRef.value.style.cursor = 'default'
}

// ── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  draw()
  resizeObs = new ResizeObserver(() => draw())
  resizeObs.observe(canvasRef.value)
  window.addEventListener('mouseup', onMouseUp)
  window.addEventListener('mousemove', onMouseMove)
})

onBeforeUnmount(() => {
  if (resizeObs) resizeObs.disconnect()
  window.removeEventListener('mouseup', onMouseUp)
  window.removeEventListener('mousemove', onMouseMove)
})

watch(() => props.poles, draw, { deep: true })
watch(() => props.darkMode, () => nextTick(draw))
</script>

<template>
  <div class="plot-container" data-tour="pole-plot">
    <div class="plot-title">Pole Map (s-plane)</div>
    <canvas
      ref="canvasRef"
      class="pole-canvas"
      @mousedown="onMouseDown"
    />
    <div class="plot-hint">Drag poles to move them</div>
  </div>
</template>

<style scoped>
.plot-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 8px;
}
.plot-title {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-dim);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.pole-canvas {
  flex: 1;
  width: 100%;
  min-height: 0;
  border-radius: 4px;
  border: 1px solid var(--border);
}
.plot-hint {
  font-size: 9px;
  color: var(--text-very-dim);
  margin-top: 4px;
  text-align: center;
}
</style>
