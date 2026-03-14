<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import {
  samples, timeVector, visibleSampleRange,
  selectedActionId, hoveredActionId, actionList, darkMode
} from '../viewerState.js'
import { extractField, fieldStats, fmtNum, getActionColor } from '../utils/dataAccess.js'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const props = defineProps({
  fields: { type: Set, required: true },
  focused: { type: Boolean, default: false },
  showActionBands: { type: Boolean, default: true },
  showActionBorders: { type: Boolean, default: true },
  syncCursorIdx: { type: Number, default: null },
  canClose: { type: Boolean, default: false },
})

const emit = defineEmits(['cursor-sync', 'remove-field', 'focus', 'drop-field', 'close', 'drag-start', 'drag-over-pane', 'drop-pane'])

const SERIES_COLORS = [
  '#45aaf2', '#2ecc71', '#e74c3c', '#f39c12', '#a55eea',
  '#4ecdc4', '#fc5c65', '#778ca3', '#26de81', '#e67e22',
  '#3498db', '#9b59b6', '#1abc9c', '#e84393', '#00cec9',
]

const chartSizer = ref(null)
const chartMount = ref(null)
const paneEl = ref(null)
let uplotInstance = null
let resizeObserver = null

const hoveredSeriesIdx = ref(null)
const cursorIdx = ref(null)
const legendHover = ref(false)
const isDragOver = ref(false)
const isDropTarget = ref(false)
const paneHovered = ref(false)
let ignoreSyncBack = false

// ── Plot data ────────────────────────────────────────────────────────────────
const plotData = computed(() => {
  const paths = [...props.fields]
  if (paths.length === 0 || samples.value.length === 0) return null

  const range = visibleSampleRange.value
  const visibleSamples = samples.value.slice(range.start, range.end)
  if (visibleSamples.length === 0) return null

  const tv = timeVector.value.slice(range.start, range.end)
  const series = paths.map((p, i) => ({
    path: p,
    data: extractField(visibleSamples, p),
    color: SERIES_COLORS[i % SERIES_COLORS.length],
    stats: null,
  }))
  for (const s of series) s.stats = fieldStats(s.data)
  return { time: tv, series, paths }
})

// ── Action bands ─────────────────────────────────────────────────────────────
function buildActionBands() {
  const acts = actionList.value
  if (acts.length === 0) return []
  const tv = timeVector.value
  if (tv.length === 0) return []
  const range = visibleSampleRange.value
  const bands = []
  for (const a of acts) {
    const st = (a.start_tick ?? 0)
    const et = (a.end_tick ?? st)
    if (et < range.start || st >= range.end) continue
    const t0 = tv[Math.max(st, range.start)] ?? 0
    const t1 = tv[Math.min(et, range.end - 1)] ?? t0
    bands.push({
      from: t0, to: t1,
      color: getActionColor(a.action_type),
      id: a.id,
      selected: a.id === selectedActionId.value,
      hovered: a.id === hoveredActionId.value,
    })
  }
  return bands
}

// ── Legend hover ──────────────────────────────────────────────────────────────
function onLegendEnter(i) {
  legendHover.value = true
  hoveredSeriesIdx.value = i + 1
}

function onLegendLeave() {
  if (contextMenu.value.show) return
  legendHover.value = false
  hoveredSeriesIdx.value = null
}

// ── Context menu ─────────────────────────────────────────────────────────────
const contextMenu = ref({ show: false, x: 0, y: 0, path: null, seriesIdx: null })
const ctxMenuStyle = computed(() => {
  const x = contextMenu.value.x, y = contextMenu.value.y
  const flipX = x + 160 > window.innerWidth
  const flipY = y + 30 > window.innerHeight
  return {
    left: flipX ? (x - 160) + 'px' : x + 'px',
    top: flipY ? (y - 30) + 'px' : y + 'px',
  }
})

function onLegendContext(e, row, i) {
  e.preventDefault()
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY, path: row.path, seriesIdx: i + 1 }
  legendHover.value = true
  hoveredSeriesIdx.value = i + 1
}

function closeContextMenu() {
  contextMenu.value = { ...contextMenu.value, show: false }
  legendHover.value = false
  hoveredSeriesIdx.value = null
}

function contextRemove() {
  emit('remove-field', contextMenu.value.path)
  closeContextMenu()
}

// ── Field drag & drop ────────────────────────────────────────────────────────
function onDragOver(e) {
  if (e.dataTransfer.types.includes('text/field-path')) {
    e.preventDefault()
    isDragOver.value = true
  } else if (e.dataTransfer.types.includes('text/plot-id')) {
    e.preventDefault()
    isDropTarget.value = true
    emit('drag-over-pane')
  }
}
function onDragLeave() {
  isDragOver.value = false
  isDropTarget.value = false
}
function onDrop(e) {
  isDragOver.value = false
  isDropTarget.value = false
  const fieldPath = e.dataTransfer.getData('text/field-path')
  if (fieldPath) {
    e.preventDefault()
    emit('drop-field', fieldPath)
    return
  }
  const plotId = e.dataTransfer.getData('text/plot-id')
  if (plotId) {
    e.preventDefault()
    emit('drop-pane', plotId)
  }
}

// ── Plot reorder drag ────────────────────────────────────────────────────────
function onGripDragStart(e) {
  e.dataTransfer.setData('text/plot-id', 'self')
  e.dataTransfer.effectAllowed = 'move'
  emit('drag-start')
}

// ── uPlot ────────────────────────────────────────────────────────────────────
function createChart() {
  if (!chartSizer.value || !chartMount.value || !plotData.value) return
  destroyChart()

  const { time, series } = plotData.value
  const dark = darkMode.value
  const bands = buildActionBands()
  const anyHovered = bands.some(b => b.hovered)

  const uData = [Array.from(time)]
  for (const s of series) uData.push(Array.from(s.data))

  const rect = chartSizer.value.getBoundingClientRect()
  if (rect.width < 10 || rect.height < 10) return

  const uSeries = [
    { label: 'Time (s)' },
    ...series.map((s) => ({
      label: s.path.split('.').slice(-2).join('.'),
      stroke: (u, si) => {
        const h = hoveredSeriesIdx.value
        if (h === null) return s.color
        return (h === si) ? s.color : s.color + '25'
      },
      width: 1.5,
      points: { show: false },
    }))
  ]

  const drawOverlay = (u) => {
    const ctx = u.ctx
    const { left, top, width, height } = u.bbox
    ctx.save()
    const dimColor = dark ? 'rgba(10, 10, 15, 0.55)' : 'rgba(240, 240, 245, 0.55)'
    if (anyHovered) {
      ctx.fillStyle = dimColor
      ctx.fillRect(left, top, width, height)
    }
    for (const b of bands) {
      const x0 = u.valToPos(b.from, 'x', true)
      const x1 = u.valToPos(b.to, 'x', true)
      const bw = Math.max(x1 - x0, 1)
      if (anyHovered && b.hovered) {
        ctx.save()
        ctx.globalCompositeOperation = 'destination-out'
        ctx.fillStyle = 'rgba(0,0,0,1)'
        ctx.fillRect(x0, top, bw, height)
        ctx.restore()
      }
      if (props.showActionBands) {
        let alpha = b.hovered ? '35' : b.selected ? '28' : anyHovered ? '08' : '18'
        ctx.fillStyle = b.color + alpha
        ctx.fillRect(x0, top, bw, height)
        const stripH = 3 * devicePixelRatio
        let stripAlpha = b.hovered ? '90' : (b.selected ? '70' : '40')
        if (anyHovered && !b.hovered) stripAlpha = '15'
        ctx.fillStyle = b.color + stripAlpha
        ctx.fillRect(x0, top, bw, stripH)
      }
      if (props.showActionBorders) {
        let borderAlpha = anyHovered ? (b.hovered ? 0.7 : 0.1) : (b.selected ? 0.6 : 0.3)
        ctx.strokeStyle = b.color
        ctx.globalAlpha = borderAlpha
        ctx.lineWidth = 1
        ctx.setLineDash([4, 3])
        ctx.beginPath(); ctx.moveTo(x0, top); ctx.lineTo(x0, top + height); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(x0 + bw, top); ctx.lineTo(x0 + bw, top + height); ctx.stroke()
        ctx.setLineDash([])
        ctx.globalAlpha = 1.0
      }
    }
    ctx.restore()
  }

  const opts = {
    width: Math.floor(rect.width),
    height: Math.floor(rect.height),
    cursor: { drag: { x: true, y: true, setScale: true } },
    scales: { x: { time: false } },
    axes: [
      {
        stroke: dark ? '#888' : '#666',
        grid: { stroke: dark ? '#1e1e2e' : '#e0e0e8', width: 1 },
        ticks: { stroke: dark ? '#2a2a3a' : '#d0d0da', width: 1 },
        font: '10px JetBrains Mono',
        labelFont: '10px JetBrains Mono',
        values: (u, vals) => vals.map(v => v.toFixed(1) + 's'),
      },
      {
        stroke: dark ? '#888' : '#666',
        grid: { stroke: dark ? '#1e1e2e' : '#e0e0e8', width: 1 },
        ticks: { stroke: dark ? '#2a2a3a' : '#d0d0da', width: 1 },
        font: '10px JetBrains Mono',
        labelFont: '10px JetBrains Mono',
        size: 60,
      }
    ],
    series: uSeries,
    legend: { show: false },
    hooks: {
      drawClear: [drawOverlay],
      setCursor: [(u) => {
        // When syncing from a sibling, don't update cursorIdx here
        // (it was already set in the watch before setCursor was called)
        if (ignoreSyncBack) return

        const cx = u.cursor.idx
        const cy = u.cursor.top
        const validCursor = cx != null && cy != null && cy >= 0
        cursorIdx.value = validCursor ? cx : null
        emit('cursor-sync', validCursor ? cx : null)

        if (legendHover.value) return
        if (!validCursor) {
          if (hoveredSeriesIdx.value !== null) hoveredSeriesIdx.value = null
          return
        }
        let minDist = Infinity, nearest = null
        for (let i = 1; i < u.series.length; i++) {
          if (!u.series[i].show) continue
          const val = u.data[i][cx]
          if (val == null) continue
          const py = u.valToPos(val, 'y', true)
          const cursorY = u.bbox.top + cy * devicePixelRatio
          const dist = Math.abs(py - cursorY)
          if (dist < minDist) { minDist = dist; nearest = i }
        }
        const next = (minDist < 30 * devicePixelRatio) ? nearest : null
        if (hoveredSeriesIdx.value !== next) hoveredSeriesIdx.value = next
      }],
    },
  }

  uplotInstance = new uPlot(opts, uData, chartMount.value)
}

function destroyChart() {
  if (uplotInstance) { uplotInstance.destroy(); uplotInstance = null }
}

function resizeChart() {
  if (!uplotInstance || !chartSizer.value) return
  const rect = chartSizer.value.getBoundingClientRect()
  if (rect.width > 10 && rect.height > 10) {
    uplotInstance.setSize({ width: Math.floor(rect.width), height: Math.floor(rect.height) })
  }
}

// ── Sync cursor from sibling plots ───────────────────────────────────────────
watch(() => props.syncCursorIdx, (idx) => {
  if (!uplotInstance) return
  // Always update cursorIdx first (before setCursor triggers the hook)
  cursorIdx.value = idx
  ignoreSyncBack = true
  if (idx == null) {
    uplotInstance.setCursor({ left: -1, top: -1 })
  } else {
    const timeVal = uplotInstance.data[0]?.[idx]
    if (timeVal != null) {
      const left = uplotInstance.valToPos(timeVal, 'x')
      uplotInstance.setCursor({ left, top: -1 })
    }
  }
  ignoreSyncBack = false
})

// ── Legend stats ─────────────────────────────────────────────────────────────
const statsRows = computed(() => {
  if (!plotData.value) return []
  const idx = cursorIdx.value
  return plotData.value.series.map((s, i) => {
    const curVal = (idx != null && uplotInstance) ? uplotInstance.data[i + 1]?.[idx] : null
    return {
      path: s.path,
      color: s.color,
      leafName: s.path.split('.').pop(),
      parentPath: s.path.split('.').slice(0, -1).join('.'),
      currentValue: curVal != null ? fmtNum(curVal) : null,
      min: fmtNum(s.stats.min),
      max: fmtNum(s.stats.max),
      mean: fmtNum(s.stats.mean),
    }
  })
})

// ── Lifecycle ────────────────────────────────────────────────────────────────
watch(() => [...props.fields], () => nextTick(() => createChart()), { deep: true })
watch(darkMode, () => nextTick(() => createChart()))
watch(selectedActionId, () => nextTick(() => createChart()))
watch(hoveredActionId, () => nextTick(() => createChart()))
watch(() => [props.showActionBands, props.showActionBorders], () => nextTick(() => createChart()))
watch(hoveredSeriesIdx, () => { if (uplotInstance) uplotInstance.redraw(false, false) })

// Watch chartSizer ref — it appears/disappears with v-if when fields change
watch(chartSizer, (el, oldEl) => {
  if (resizeObserver) {
    if (oldEl) resizeObserver.unobserve(oldEl)
    if (el) {
      resizeObserver.observe(el)
      nextTick(() => createChart())
    }
  }
}, { flush: 'post' })

onMounted(() => {
  resizeObserver = new ResizeObserver(() => {
    if (uplotInstance) resizeChart()
    else nextTick(() => createChart())
  })
  if (chartSizer.value) {
    resizeObserver.observe(chartSizer.value)
    nextTick(() => createChart())
  }
})

onBeforeUnmount(() => {
  destroyChart()
  if (resizeObserver) resizeObserver.disconnect()
})

defineExpose({ resizeChart })
</script>

<template>
  <div
    ref="paneEl"
    class="plot-pane"
    :class="{ focused, 'drag-over': isDragOver, 'drop-target': isDropTarget }"
    @click="emit('focus')"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
    @mouseenter="paneHovered = true"
    @mouseleave="paneHovered = false"
  >
    <!-- Pane controls (top-right, hover-revealed) -->
    <div class="pane-controls" v-show="paneHovered || focused">
      <div
        class="pane-grip"
        draggable="true"
        @dragstart="onGripDragStart"
        title="Drag to reorder"
      >⠿</div>
      <button
        v-if="canClose"
        class="pane-close"
        @click.stop="emit('close')"
        title="Remove plot"
      >&times;</button>
    </div>

    <div v-if="fields.size === 0" class="pane-empty">
      Drag fields here or click fields in the tree
    </div>
    <template v-else>
      <!-- Chart sizing wrapper: position:relative flex item -->
      <div ref="chartSizer" class="chart-sizer">
        <div ref="chartMount" class="chart-mount"></div>
      </div>

      <!-- Legend -->
      <div class="legend-panel">
        <div class="legend-entries">
          <div
            v-for="(row, i) in statsRows" :key="row.path"
            class="legend-entry"
            :class="{
              highlighted: hoveredSeriesIdx === i + 1,
              dimmed: hoveredSeriesIdx !== null && hoveredSeriesIdx !== i + 1
            }"
            @mouseenter="onLegendEnter(i)"
            @mouseleave="onLegendLeave"
            @contextmenu="onLegendContext($event, row, i)"
          >
            <div class="legend-entry-top">
              <span class="legend-color" :style="{ background: row.color }"></span>
              <span class="legend-leaf">{{ row.leafName }}</span>
              <span class="legend-current" :style="{ color: row.color }">{{ row.currentValue ?? '—' }}</span>
            </div>
            <div class="legend-path-row" :title="row.path">{{ row.parentPath }}</div>
            <div class="legend-stats">
              <div class="legend-stat"><span class="legend-stat-label">min</span><span class="legend-stat-value">{{ row.min }}</span></div>
              <div class="legend-stat"><span class="legend-stat-label">max</span><span class="legend-stat-value">{{ row.max }}</span></div>
              <div class="legend-stat"><span class="legend-stat-label">avg</span><span class="legend-stat-value">{{ row.mean }}</span></div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Context menu -->
    <Teleport to="body">
      <div v-if="contextMenu.show" class="legend-ctx-backdrop" @click="closeContextMenu" @contextmenu.prevent="closeContextMenu">
        <div class="legend-ctx-menu" :style="ctxMenuStyle">
          <button class="legend-ctx-item" @click="contextRemove">Remove from plot</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.plot-pane {
  display: flex;
  min-height: 0;
  flex: 1;
  overflow: hidden;
  position: relative;
  border: 1px solid transparent;
  border-radius: 3px;
  transition: border-color 0.15s;
}

.plot-pane.focused {
  border-color: var(--accent-dim);
}

.plot-pane.drag-over {
  border-color: var(--accent);
  background: rgba(69, 170, 242, 0.05);
}

.plot-pane.drop-target {
  border-color: var(--success);
  background: rgba(46, 204, 113, 0.05);
}

/* ── Pane controls (top-right overlay) ────────────────────────────────── */
.pane-controls {
  position: absolute;
  top: 2px;
  right: 2px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 2px;
  opacity: 0.7;
  transition: opacity 0.15s;
}

.plot-pane:hover .pane-controls { opacity: 1; }

.pane-grip {
  font-size: 10px;
  padding: 1px 3px;
  cursor: grab;
  color: var(--text-dim);
  border-radius: 3px;
  user-select: none;
  line-height: 1;
  letter-spacing: 1px;
}
.pane-grip:hover { background: var(--bg-hover); color: var(--text); }
.pane-grip:active { cursor: grabbing; }

.pane-close {
  font-family: inherit;
  font-size: 13px;
  line-height: 1;
  padding: 0 4px;
  border: none;
  background: none;
  color: var(--text-dim);
  cursor: pointer;
  border-radius: 3px;
}
.pane-close:hover { background: var(--bg-hover); color: var(--error); }

.pane-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
  font-size: 11px;
  opacity: 0.6;
}

/* ── Chart sizing (decoupled from uPlot content dimensions) ──────────── */
.chart-sizer {
  flex: 1;
  min-width: 0;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.chart-mount {
  position: absolute;
  inset: 0;
}

/* ── Legend ────────────────────────────────────────────────────────────── */
.legend-panel {
  width: 180px;
  min-width: 140px;
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.legend-entries {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.legend-entry {
  padding: 4px 8px;
  cursor: default;
  transition: background 0.1s, opacity 0.15s;
  border-left: 2px solid transparent;
}

.legend-entry:hover,
.legend-entry.highlighted {
  background: var(--bg-hover);
}
.legend-entry.highlighted {
  border-left-color: var(--accent);
}
.legend-entry.dimmed {
  opacity: 0.35;
}

.legend-entry-top {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.legend-color {
  width: 7px;
  height: 7px;
  border-radius: 2px;
  flex-shrink: 0;
}

.legend-leaf {
  font-size: 10px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.legend-current {
  font-size: 10px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  margin-left: auto;
  flex-shrink: 0;
  white-space: nowrap;
}

.legend-path-row {
  font-size: 9px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-left: 12px;
  line-height: 1.3;
  opacity: 0.6;
}

.legend-stats {
  display: flex;
  flex-direction: column;
  gap: 0px;
  padding-left: 12px;
}

.legend-stat {
  display: flex;
  justify-content: space-between;
  gap: 4px;
  font-size: 8px;
}

.legend-stat-label {
  color: var(--text-dim);
  flex-shrink: 0;
}

.legend-stat-value {
  color: var(--text);
  font-variant-numeric: tabular-nums;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* ── Context menu ─────────────────────────────────────────────────────── */
.legend-ctx-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9999;
}

.legend-ctx-menu {
  position: fixed;
  background: var(--bg-surface, #1e1e2e);
  border: 1px solid var(--border, #333);
  border-radius: 4px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  padding: 3px 0;
  min-width: 140px;
  z-index: 10000;
}

.legend-ctx-item {
  font-family: inherit;
  font-size: 11px;
  width: 100%;
  padding: 4px 12px;
  border: none;
  background: transparent;
  color: var(--text, #ccc);
  cursor: pointer;
  text-align: left;
}
.legend-ctx-item:hover {
  background: var(--bg-hover, #2a2a3a);
}
</style>
