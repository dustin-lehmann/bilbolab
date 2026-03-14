<script setup>
import { computed, ref, onUnmounted } from 'vue'
import { getAllActions, getAllCategories, getSummary, hasMissingRequired, getTransitionPorts } from '../actionRegistry.js'
import {
  selection, selectNode, toggleNodeSelection, isNodeSelected, startWiring, wiring,
  getNode, updateNodePosition, snapshot, nodes, edges, openContainerTab,
  pan, zoom as outerZoom, mode, actionStates, layoutDirection,
} from '../graphState.js'
import {
  NODE_WIDTH, getNodeHeight, getOutputPortPos, getInputPortPos,
  CONTAINER_HEADER_HEIGHT, CONTAINER_MIN_WIDTH, CONTAINER_MIN_HEIGHT,
  ENTRY_WIDTH, ENTRY_HEIGHT, computeBezierPath, getPortVisualCenter,
} from '../utils/geometry.js'
import ActionNode from './ActionNode.vue'
import StartStopNode from './StartStopNode.vue'
import ConnectionLine from './ConnectionLine.vue'

const props = defineProps({
  node: { type: Object, required: true },
  childNodes: { type: Array, required: true },
  childEdges: { type: Array, required: true },
  zoom: { type: Number, default: 1 },
})

const emit = defineEmits(['startDrag', 'startResize', 'nodeStartDrag'])

const isPlayback = computed(() => mode.value === 'playback')
const isHorizontal = computed(() => layoutDirection.value === 'horizontal')
const actionState = computed(() => actionStates.value[props.node.id] || 'normal')

const def = computed(() => getAllActions()[props.node.type])
const category = computed(() => getAllCategories()[def.value?.category] || { label: '?', color: '#666' })
const summaryText = computed(() => getSummary(props.node))
const isSelected = computed(() => isNodeSelected(props.node.id))
const outPorts = computed(() => props.node._outPorts || getTransitionPorts(props.node.type))
const isPhaseGroup = computed(() => props.node.type === 'setup_group' || props.node.type === 'cleanup_group')
const hasInputPort = computed(() => !isPhaseGroup.value && (!props.node.trigger || props.node.trigger.type === 'transition'))
const PHASE_LABELS = { setup_group: 'Setup', cleanup_group: 'Cleanup' }
const displayLabel = computed(() => PHASE_LABELS[props.node.type] || props.node.type)

const inputConnected = computed(() => edges.value.some(e => e.to === props.node.id))
const connectedOutPorts = computed(() => {
  const set = new Set()
  for (const e of edges.value) {
    if (e.from === props.node.id) set.add(e.fromPort)
  }
  return set
})

const PORT_COLORS = {
  done: '#45aaf2',
  error: '#e74c3c',
  timeout: '#f39c12',
  then: '#2ecc71',
  else: '#e67e22',
}

// ── Compact mode (persisted on node object so it survives remounts) ──
const isCompact = computed(() => !!props.node._compact)

function toggleCompact(e) {
  e.stopPropagation()
  props.node._compact = !props.node._compact
}

function onOpenTab(e) {
  e.stopPropagation()
  openContainerTab(props.node.id)
}

// ── Internal pan/zoom (non-compact mode) ──────────────────────────────
let isInternalPanning = false
let internalPanStartX = 0
let internalPanStartY = 0
let internalPanStartPanX = 0
let internalPanStartPanY = 0

function onBodyWheel(e) {
  if (isCompact.value) return // Let canvas handle it
  e.stopPropagation()
  e.preventDefault()

  const bodyEl = e.currentTarget
  const rect = bodyEl.getBoundingClientRect()
  // Cursor position in body's CSS coordinate system (divide by outer zoom)
  const mx = (e.clientX - rect.left) / props.zoom
  const my = (e.clientY - rect.top) / props.zoom

  const oldZoom = props.node._bodyZoom || 1
  const oldPanX = props.node._bodyPanX || 0
  const oldPanY = props.node._bodyPanY || 0

  const delta = e.deltaY > 0 ? 0.9 : 1.1
  const newZoom = Math.max(0.25, Math.min(4.0, oldZoom * delta))

  // Zoom centered on cursor
  props.node._bodyPanX = mx - (mx - oldPanX) * (newZoom / oldZoom)
  props.node._bodyPanY = my - (my - oldPanY) * (newZoom / oldZoom)
  props.node._bodyZoom = newZoom
}

function onInternalPanMove(e) {
  if (!isInternalPanning) return
  const dx = (e.clientX - internalPanStartX) / props.zoom
  const dy = (e.clientY - internalPanStartY) / props.zoom
  props.node._bodyPanX = internalPanStartPanX + dx
  props.node._bodyPanY = internalPanStartPanY + dy
}

function onInternalPanUp() {
  isInternalPanning = false
  document.body.style.cursor = ''
  window.removeEventListener('mousemove', onInternalPanMove)
  window.removeEventListener('mouseup', onInternalPanUp)
}

onUnmounted(() => {
  if (isInternalPanning) {
    window.removeEventListener('mousemove', onInternalPanMove)
    window.removeEventListener('mouseup', onInternalPanUp)
  }
})

// Separate child nodes into categories
const entryExitNodes = computed(() =>
  props.childNodes.filter(n => n.type === '__entry__' || n.type === '__exit__')
)
const regularChildren = computed(() =>
  props.childNodes.filter(n => n.type !== '__entry__' && n.type !== '__exit__' && n.width == null)
)
const containerChildren = computed(() =>
  props.childNodes.filter(n => n.width != null)
)

// Transform to map global canvas coords → container-body-local coords.
// Children store global positions; the body starts at (container.x, container.y + headerHeight).
// By translating the inner div by the negative of that origin, children land at the right spot.
//
// In compact mode, we additionally scale to fit all children within the body area.
const PORTS_HEIGHT = 28
const bodyInnerTransform = computed(() => {
  const tx = -props.node.x
  const ty = -(props.node.y + CONTAINER_HEADER_HEIGHT)

  if (!isCompact.value || props.childNodes.length === 0) {
    const bpx = props.node._bodyPanX || 0
    const bpy = props.node._bodyPanY || 0
    const bz = props.node._bodyZoom || 1
    if (bz === 1 && bpx === 0 && bpy === 0) {
      return `translate(${tx}px, ${ty}px)`
    }
    return `translate(${bpx}px, ${bpy}px) scale(${bz}) translate(${tx}px, ${ty}px)`
  }

  // Calculate bounding box of all children in global coords
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const child of props.childNodes) {
    const w = child.width ?? (child.type === '__entry__' || child.type === '__exit__' ? ENTRY_WIDTH : NODE_WIDTH)
    const h = child.height ?? getNodeHeight(child)
    minX = Math.min(minX, child.x)
    minY = Math.min(minY, child.y)
    maxX = Math.max(maxX, child.x + w)
    maxY = Math.max(maxY, child.y + h)
  }

  const contentW = maxX - minX
  const contentH = maxY - minY
  if (contentW <= 0 || contentH <= 0) return `translate(${tx}px, ${ty}px)`

  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  const bodyW = props.node.width
  const bodyH = props.node.height - CONTAINER_HEADER_HEIGHT - PORTS_HEIGHT

  const padding = 20
  const s = Math.min(bodyW / (contentW + padding), bodyH / (contentH + padding), 1)

  // After: translate(tx,ty) maps global → body-local
  // Then: scale(s) scales around (0,0) = body top-left
  // Then: translate(offsetX,offsetY) centers the scaled content
  const offsetX = bodyW / 2 - s * (cx - props.node.x)
  const offsetY = bodyH / 2 - s * (cy - props.node.y - CONTAINER_HEADER_HEIGHT)

  return `translate(${offsetX}px, ${offsetY}px) scale(${s}) translate(${tx}px, ${ty}px)`
})

// For each nested container child, pre-filter its own children and edges
function getNestedChildNodes(containerId) {
  return nodes.value.filter(n => n.parentId === containerId)
}
function getNestedChildEdges(containerId) {
  const childIds = new Set(nodes.value.filter(n => n.parentId === containerId).map(n => n.id))
  return edges.value.filter(e => childIds.has(e.from) && childIds.has(e.to))
}

// ── Header interaction ──────────────────────────────────────────────
function onHeaderMouseDown(e) {
  if (e.button !== 0) return
  if (e.target.classList.contains('port')) return
  if (e.shiftKey) {
    toggleNodeSelection(props.node.id)
  } else if (!isNodeSelected(props.node.id)) {
    selectNode(props.node.id)
  }
  if (!isPlayback.value) {
    emit('startDrag', { nodeId: props.node.id, offsetX: 0, offsetY: 0, event: e })
  }
}

// ── Body interaction ─────────────────────────────────────────────────
function onBodyMouseDown(e) {
  if (e.button !== 0) return
  if (isCompact.value) return // Let canvas handle in compact mode
  // Only on body background (not child nodes)
  if (e.target.classList.contains('container-body') || e.target.classList.contains('container-body-inner')) {
    // CMD/Ctrl + drag = internal pan; without modifier, let canvas handle marquee
    if (e.metaKey || e.ctrlKey) {
      e.stopPropagation()
      e.preventDefault()
      isInternalPanning = true
      internalPanStartX = e.clientX
      internalPanStartY = e.clientY
      internalPanStartPanX = props.node._bodyPanX || 0
      internalPanStartPanY = props.node._bodyPanY || 0
      document.body.style.cursor = 'grabbing'
      window.addEventListener('mousemove', onInternalPanMove)
      window.addEventListener('mouseup', onInternalPanUp)
    }
    // Without CMD/Ctrl, don't stop propagation → canvas handles marquee
  }
}

function onBodyDblClick(e) {
  if (isCompact.value) return
  // Double-click on body background resets internal pan/zoom
  if (e.target.classList.contains('container-body') || e.target.classList.contains('container-body-inner')) {
    e.stopPropagation()
    props.node._bodyPanX = 0
    props.node._bodyPanY = 0
    props.node._bodyZoom = 1
  }
}

// ── Port interactions ───────────────────────────────────────────────
function onOutPortMouseDown(e, portName) {
  if (isPlayback.value) return
  e.stopPropagation()
  e.preventDefault()
  const pos = getPortVisualCenter(e.currentTarget, pan.x, pan.y, outerZoom.value)
  if (pos) {
    startWiring(props.node.id, portName, pos.x, pos.y)
  }
}

function onInPortMouseDown(e) {
  if (isPlayback.value) return
  e.stopPropagation()
  e.preventDefault()
  const pos = getPortVisualCenter(e.currentTarget, pan.x, pan.y, outerZoom.value)
  if (pos) {
    startWiring(props.node.id, '__input__', pos.x, pos.y)
  }
}

// ── Resize ──────────────────────────────────────────────────────────
function onResizeMouseDown(direction, e) {
  if (isPlayback.value) return
  if (wiring.active) return // Don't start resize while drawing a wire
  e.stopPropagation()
  e.preventDefault()
  emit('startResize', { nodeId: props.node.id, direction, event: e })
}

// ── Double-click to open in tab ──────────────────────────────────────
function onHeaderDblClick(e) {
  e.stopPropagation()
  openContainerTab(props.node.id)
}

// ── Child node drag forwarding ──────────────────────────────────────
function onChildStartDrag(payload) {
  emit('nodeStartDrag', payload)
}
</script>

<template>
  <div
    class="container-node"
    :class="{
      selected: isSelected,
      'phase-group': isPhaseGroup,
      'state-active': actionState === 'active',
      'state-highlighted': actionState === 'highlighted',
      'state-dimmed': actionState === 'dimmed',
      'state-completed': actionState === 'completed',
      'state-error': actionState === 'error',
    }"
    :data-container-id="node.id"
    :style="{
      left: node.x + 'px',
      top: node.y + 'px',
      width: node.width + 'px',
      height: node.height + 'px',
    }"
  >
    <!-- Flow input port — top center (vertical) or left center (horizontal) -->
    <div
      v-if="hasInputPort"
      class="port port-in"
      :class="{ connected: inputConnected }"
      :style="isHorizontal ? { left: '-5px', top: '50%', transform: 'translateY(-50%)' } : {}"
      :data-node-id="node.id"
      data-port-type="in"
      @mousedown="onInPortMouseDown"
    ></div>

    <!-- Header bar -->
    <div
      class="container-header"
      :style="{ background: category.color + '22', borderColor: category.color }"
      @mousedown="onHeaderMouseDown"
      @dblclick="onHeaderDblClick"
    >
      <span class="node-type" :style="{ color: category.color }">{{ displayLabel }}</span>
      <span class="node-id-label">{{ node.id }}</span>
      <span v-if="summaryText" class="node-summary-label">{{ summaryText }}</span>
      <div class="header-controls" @mousedown.stop>
        <span class="compact-label">Compact</span>
        <div
          class="toggle-switch"
          :class="{ on: isCompact }"
          title="Fit content to view"
          @click="toggleCompact"
        ><div class="toggle-knob"></div></div>
        <button
          class="open-tab-btn"
          title="Open in tab"
          @click="onOpenTab"
        >&#x2197;</button>
      </div>
    </div>

    <!-- Body (children clipped) -->
    <div class="container-body" @mousedown="onBodyMouseDown" @wheel="onBodyWheel" @dblclick="onBodyDblClick">
      <div
        class="container-body-inner"
        :class="{ compact: isCompact }"
        :style="{ transform: bodyInnerTransform, transformOrigin: '0 0' }"
      >
        <!-- Internal edges SVG -->
        <svg class="internal-edges-svg">
          <ConnectionLine
            v-for="edge in childEdges"
            :key="edge.id"
            :edge="edge"
          />
        </svg>

        <!-- Entry/exit nodes (rendered as StartStopNode) -->
        <StartStopNode
          v-for="cn in entryExitNodes"
          :key="cn.id"
          :node="cn"
          @start-drag="onChildStartDrag"
        />

        <!-- Regular action child nodes -->
        <ActionNode
          v-for="cn in regularChildren"
          :key="cn.id"
          :node="cn"
          :zoom="zoom"
          @start-drag="onChildStartDrag"
        />

        <!-- Nested container children (recursive) -->
        <ContainerNode
          v-for="cn in containerChildren"
          :key="cn.id"
          :node="cn"
          :child-nodes="getNestedChildNodes(cn.id)"
          :child-edges="getNestedChildEdges(cn.id)"
          :zoom="zoom"
          @start-drag="onChildStartDrag"
          @start-resize="$emit('startResize', $event)"
          @node-start-drag="onChildStartDrag"
        />
      </div>
    </div>

    <!-- Output port labels — bottom (vertical) or right column (horizontal) -->
    <div v-if="outPorts.length > 0" class="container-ports-labels" :style="isHorizontal ? { position: 'absolute', right: '2px', top: '32px', bottom: '4px', width: 'auto', height: 'auto', padding: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-around', alignItems: 'flex-end' } : {}">
      <span
        v-for="(port, idx) in outPorts"
        :key="port"
        class="port-label-bottom"
        :style="isHorizontal
          ? { position: 'static', transform: 'none', color: PORT_COLORS[port] || 'var(--text-dim)', fontSize: '9px', whiteSpace: 'nowrap' }
          : { left: ((idx + 1) / (outPorts.length + 1) * 100) + '%', color: PORT_COLORS[port] || 'var(--text-dim)' }"
      >{{ port }}</span>
    </div>

    <!-- Output port dots — bottom (vertical) or right edge (horizontal) -->
    <div
      v-for="(port, idx) in outPorts"
      :key="'outport-' + port"
      class="port port-out"
      :class="{ connected: connectedOutPorts.has(port) }"
      :style="isHorizontal
        ? { right: '-5px', left: 'auto', bottom: 'auto', top: ((idx + 1) / (outPorts.length + 1) * 100) + '%', transform: 'translateY(-50%)', borderColor: PORT_COLORS[port] || '#45aaf2', background: connectedOutPorts.has(port) ? (PORT_COLORS[port] || '#45aaf2') : undefined }
        : { left: ((idx + 1) / (outPorts.length + 1) * 100) + '%', borderColor: PORT_COLORS[port] || '#45aaf2', background: connectedOutPorts.has(port) ? (PORT_COLORS[port] || '#45aaf2') : undefined }"
      :data-node-id="node.id"
      :data-port-name="port"
      data-port-type="out"
      @mousedown="onOutPortMouseDown($event, port)"
    ></div>

    <!-- Resize handles (disabled during wiring to not block port access) -->
    <template v-if="!wiring.active">
      <div class="resize-handle resize-n" @mousedown="onResizeMouseDown('n', $event)"></div>
      <div class="resize-handle resize-s" @mousedown="onResizeMouseDown('s', $event)"></div>
      <div class="resize-handle resize-e" @mousedown="onResizeMouseDown('e', $event)"></div>
      <div class="resize-handle resize-w" @mousedown="onResizeMouseDown('w', $event)"></div>
      <div class="resize-handle resize-ne" @mousedown="onResizeMouseDown('ne', $event)"></div>
      <div class="resize-handle resize-nw" @mousedown="onResizeMouseDown('nw', $event)"></div>
      <div class="resize-handle resize-se" @mousedown="onResizeMouseDown('se', $event)"></div>
      <div class="resize-handle resize-sw" @mousedown="onResizeMouseDown('sw', $event)"></div>
    </template>
  </div>
</template>

<style scoped>
.container-node {
  position: absolute;
  border-radius: 6px;
  background: var(--container-bg, var(--bg));
  border: 2px dashed var(--border);
  cursor: default;
  user-select: none;
  transition: border-color 0.15s, box-shadow 0.15s, opacity 0.3s, filter 0.3s;
  opacity: 1;
  filter: none;
  overflow: visible;
  display: flex;
  flex-direction: column;
}

.container-node.phase-group {
  border-style: solid;
  border-color: #45aaf244;
}

.container-node:hover { border-color: var(--text-dim); }

.container-node.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent), 0 2px 12px rgba(0,0,0,0.3);
}

/* Header */
.container-header {
  padding: 4px 8px;
  border-bottom: 1px solid var(--border);
  border-radius: 4px 4px 0 0;
  border-left: 3px solid;
  display: flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  flex-shrink: 0;
  cursor: grab;
}

.node-type {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.node-id-label {
  font-size: 9px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.node-summary-label {
  font-size: 9px;
  color: var(--text-dim);
  white-space: nowrap;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.compact-label {
  font-size: 8px;
  color: var(--text-dim);
  white-space: nowrap;
}

/* Apple-style toggle switch */
.toggle-switch {
  width: 28px;
  height: 16px;
  border-radius: 8px;
  background: var(--border);
  cursor: pointer;
  position: relative;
  transition: background 0.2s ease;
  flex-shrink: 0;
}

.toggle-switch.on {
  background: var(--accent);
}

.toggle-knob {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #fff;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

.toggle-switch.on .toggle-knob {
  transform: translateX(12px);
}

/* Open-in-tab button */
.open-tab-btn {
  font-size: 11px;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--bg-surface);
  color: var(--text-dim);
  cursor: pointer;
  flex-shrink: 0;
  line-height: 1;
  padding: 0;
  transition: background 0.15s, color 0.15s;
}
.open-tab-btn:hover { background: var(--bg-hover); color: var(--accent); }

/* Body */
.container-body {
  flex: 1;
  position: relative;
  overflow: hidden;
  min-height: 0;
}

.container-body-inner {
  position: absolute;
  inset: 0;
}

.container-body-inner.compact {
  pointer-events: none;
}

.internal-edges-svg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: visible;
}

.internal-edges-svg :deep(g) {
  pointer-events: auto;
}

/* Output port labels */
.container-ports-labels {
  position: relative;
  height: 20px;
  padding: 0 4px 4px;
  flex-shrink: 0;
}

.port-label-bottom {
  position: absolute;
  bottom: 4px;
  transform: translateX(-50%);
  font-size: 9px;
  color: var(--text-dim);
  white-space: nowrap;
}

/* Port dots */
.port {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--accent);
  background: var(--bg-surface);
  cursor: crosshair;
  transition: background 0.1s;
  z-index: 5;
  position: absolute;
}

.port::after {
  content: '';
  position: absolute;
  top: -6px;
  left: -6px;
  right: -6px;
  bottom: -6px;
  border-radius: 50%;
}

.port:hover { background: var(--accent); }
.port-in.connected { background: var(--accent); }

.port-in {
  top: -5px;
  left: 50%;
  transform: translateX(-50%);
}

.port-out {
  bottom: -5px;
  transform: translateX(-50%);
}

/* Resize handles */
.resize-handle {
  position: absolute;
  z-index: 10;
}

.resize-n {
  top: -3px; left: 8px; right: 8px; height: 6px;
  cursor: n-resize;
}
.resize-s {
  bottom: -3px; left: 8px; right: 8px; height: 6px;
  cursor: s-resize;
}
.resize-e {
  top: 8px; bottom: 8px; right: -3px; width: 6px;
  cursor: e-resize;
}
.resize-w {
  top: 8px; bottom: 8px; left: -3px; width: 6px;
  cursor: w-resize;
}
.resize-ne {
  top: -4px; right: -4px; width: 10px; height: 10px;
  cursor: ne-resize;
}
.resize-nw {
  top: -4px; left: -4px; width: 10px; height: 10px;
  cursor: nw-resize;
}
.resize-se {
  bottom: -4px; right: -4px; width: 10px; height: 10px;
  cursor: se-resize;
}
.resize-sw {
  bottom: -4px; left: -4px; width: 10px; height: 10px;
  cursor: sw-resize;
}

/* ── Playback action states ── */
.container-node.state-active {
  border-color: #2ecc71;
  box-shadow: 0 0 8px rgba(46, 204, 113, 0.5), 0 0 16px rgba(46, 204, 113, 0.2);
}

.container-node.state-highlighted {
  border-color: #f1c40f;
  box-shadow: 0 0 8px rgba(241, 196, 15, 0.5), 0 0 16px rgba(241, 196, 15, 0.2);
}

.container-node.state-dimmed {
  opacity: 0.3;
  filter: grayscale(0.7);
}

.container-node.state-completed {
  border-color: #2ecc71;
  opacity: 0.75;
  box-shadow: 0 0 4px rgba(46, 204, 113, 0.15);
}

.container-node.state-error {
  border-color: #e74c3c;
  box-shadow: 0 0 8px rgba(231, 76, 60, 0.5), 0 0 16px rgba(231, 76, 60, 0.2);
}
</style>
