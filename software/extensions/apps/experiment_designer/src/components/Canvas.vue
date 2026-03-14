<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import ActionNode from './ActionNode.vue'
import StartStopNode from './StartStopNode.vue'
import ContainerNode from './ContainerNode.vue'
import ConnectionLine from './ConnectionLine.vue'
import DragLine from './DragLine.vue'
import {
  nodes, edges, pan, zoom, selection, wiring, selectedNodeIds, mode,
  addNode, addEdge, updateNodePosition, clearSelection, selectNode, selectNodes,
  updateWiring, endWiring, getNode, snapshot, isNodeSelected,
  getChildren, getChildEdges, findContainerAtPoint, moveNodeToContainer,
  removeNodeFromContainer, isEntryOrExit, getDescendants,
  activeParentId, openContainerTab, updateViewport,
} from '../graphState.js'
import { notifyMutation } from '../mutationBridge.js'
import {
  snapToGrid, NODE_WIDTH, REQUIREMENT_WIDTH, GUARD_WIDTH, GUARD_HEIGHT, getNodeHeight, START_WIDTH, START_HEIGHT, STOP_WIDTH, STOP_HEIGHT,
  CONTAINER_HEADER_HEIGHT, CONTAINER_MIN_WIDTH, CONTAINER_MIN_HEIGHT,
  ENTRY_WIDTH, ENTRY_HEIGHT, REQUIREMENT_HEIGHT,
} from '../utils/geometry.js'

const canvasRef = ref(null)
const isPlayback = computed(() => mode.value === 'playback')

// ── Computed ───────────────────────────────────────────────────────────────
// Filter nodes based on the active tab's parentId context
const isInView = (n) => {
  if (activeParentId.value === null) return !n.parentId
  return n.parentId === activeParentId.value
}

const actionNodes = computed(() =>
  nodes.value.filter(n => isInView(n) && n.type !== '__start__' && n.type !== '__stop__'
    && n.type !== '__entry__' && n.type !== '__exit__' && n.width == null && !n.isRequirement && !n.isGuard)
)

const requirementNodes = computed(() =>
  nodes.value.filter(n => isInView(n) && n.isRequirement)
)

const guardNodes = computed(() =>
  nodes.value.filter(n => isInView(n) && n.isGuard)
)

const specialNodes = computed(() =>
  nodes.value.filter(n => {
    if (!isInView(n)) return false
    if (activeParentId.value === null) {
      return n.type === '__start__' || n.type === '__stop__'
    } else {
      // In container tab view, entry/exit act as start/stop
      return n.type === '__entry__' || n.type === '__exit__'
    }
  })
)

const topLevelContainers = computed(() =>
  nodes.value.filter(n => isInView(n) && n.width != null)
)

// Edges where both endpoints are in the current view
const topLevelEdges = computed(() => {
  const viewIds = new Set(nodes.value.filter(isInView).map(n => n.id))
  return edges.value.filter(e => viewIds.has(e.from) && viewIds.has(e.to))
})

const transformStyle = computed(() =>
  `translate(${pan.x}px, ${pan.y}px) scale(${zoom.value})`
)

// Grid pattern size adjusts with zoom
const gridSize = computed(() => 20 * zoom.value)

// ── Marquee selection ─────────────────────────────────────────────────────
const marquee = reactive({ active: false, startX: 0, startY: 0, currentX: 0, currentY: 0 })
let marqueeParentId = null  // Scopes marquee to children of a specific container (null = top-level)

const marqueeRect = computed(() => {
  if (!marquee.active) return null
  const x = Math.min(marquee.startX, marquee.currentX)
  const y = Math.min(marquee.startY, marquee.currentY)
  const w = Math.abs(marquee.currentX - marquee.startX)
  const h = Math.abs(marquee.currentY - marquee.startY)
  return { x, y, w, h }
})

// Screen-space marquee rect (for the overlay div, accounting for pan+zoom)
const marqueeStyle = computed(() => {
  if (!marqueeRect.value) return null
  const r = marqueeRect.value
  return {
    left: (r.x * zoom.value + pan.x) + 'px',
    top: (r.y * zoom.value + pan.y) + 'px',
    width: (r.w * zoom.value) + 'px',
    height: (r.h * zoom.value) + 'px',
  }
})

function getNodeRect(node) {
  if (node.type === '__start__') return { x: node.x, y: node.y, w: START_WIDTH, h: START_HEIGHT }
  if (node.type === '__stop__') return { x: node.x, y: node.y, w: STOP_WIDTH, h: STOP_HEIGHT }
  if (node.type === '__entry__' || node.type === '__exit__') return { x: node.x, y: node.y, w: ENTRY_WIDTH, h: ENTRY_HEIGHT }
  if (node.isRequirement) return { x: node.x, y: node.y, w: REQUIREMENT_WIDTH, h: REQUIREMENT_HEIGHT }
  if (node.isGuard) return { x: node.x, y: node.y, w: GUARD_WIDTH, h: GUARD_HEIGHT }
  if (node.width != null) return { x: node.x, y: node.y, w: node.width, h: node.height }
  return { x: node.x, y: node.y, w: NODE_WIDTH, h: getNodeHeight(node) }
}

function rectsOverlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
}

function updateMarqueeSelection() {
  const r = marqueeRect.value
  if (!r || r.w < 4 && r.h < 4) return
  const mRect = { x: r.x, y: r.y, w: r.w, h: r.h }
  const ids = []
  for (const node of nodes.value) {
    // Only select nodes at the same nesting level where the marquee started
    if ((node.parentId || null) !== marqueeParentId) continue
    if (rectsOverlap(mRect, getNodeRect(node))) {
      ids.push(node.id)
    }
  }
  selectNodes(ids)
}

// ── Panning ────────────────────────────────────────────────────────────────
let isPanning = false
let panStartX = 0
let panStartY = 0
let panStartPanX = 0
let panStartPanY = 0
let spaceDown = false

// CMD/Meta+drag panning: capture-phase handler intercepts before child nodes.
// Exception: CMD+click inside a non-compact container body should be handled by
// the container for internal panning, so we let those through.
function onMetaPanCapture(e) {
  if (e.button === 0 && (e.metaKey || e.ctrlKey)) {
    const containerBody = e.target.closest('.container-body')
    if (containerBody) {
      const bodyInner = containerBody.querySelector('.container-body-inner')
      if (bodyInner && !bodyInner.classList.contains('compact')) return
    }
    e.preventDefault()
    e.stopPropagation()
    startPan(e)
  }
}

function onCanvasMouseDown(e) {
  // Blur any focused inspector input so its value commits
  if (document.activeElement && document.activeElement.tagName === 'INPUT') {
    document.activeElement.blur()
  }

  // Middle-click pan
  if (e.button === 1) {
    e.preventDefault()
    startPan(e)
    return
  }

  // Left-click on canvas background or non-compact container body background
  if (e.button === 0) {
    const isCanvasBg = e.target === canvasRef.value || e.target.classList.contains('canvas-bg')
    const isContainerBg = e.target.classList.contains('container-body') || e.target.classList.contains('container-body-inner')
    if (isCanvasBg || isContainerBg) {
      if (spaceDown) {
        startPan(e)
      } else if (!isPlayback.value) {
        // Determine which container the marquee is scoped to
        if (isContainerBg) {
          const containerEl = e.target.closest('.container-node')
          marqueeParentId = containerEl?.dataset.containerId ?? null
        } else {
          // In a container tab view, nodes have parentId = activeParentId
          marqueeParentId = activeParentId.value
        }
        // Start marquee selection
        clearSelection()
        const rect = canvasRef.value.getBoundingClientRect()
        const x = (e.clientX - rect.left - pan.x) / zoom.value
        const y = (e.clientY - rect.top - pan.y) / zoom.value
        marquee.active = true
        marquee.startX = x
        marquee.startY = y
        marquee.currentX = x
        marquee.currentY = y
      }
    }
  }
}

function startPan(e) {
  isPanning = true
  panStartX = e.clientX
  panStartY = e.clientY
  panStartPanX = pan.x
  panStartPanY = pan.y
  document.body.style.cursor = 'grabbing'
}

function onMouseMove(e) {
  if (isPanning) {
    pan.x = panStartPanX + (e.clientX - panStartX)
    pan.y = panStartPanY + (e.clientY - panStartY)
    return
  }

  if (marquee.active) {
    const rect = canvasRef.value.getBoundingClientRect()
    marquee.currentX = (e.clientX - rect.left - pan.x) / zoom.value
    marquee.currentY = (e.clientY - rect.top - pan.y) / zoom.value
    updateMarqueeSelection()
    return
  }

  if (dragging.active) {
    const rect = canvasRef.value.getBoundingClientRect()
    const x = (e.clientX - rect.left - pan.x) / zoom.value - dragging.offsetX
    const y = (e.clientY - rect.top - pan.y) / zoom.value - dragging.offsetY
    const snapped = snapToGrid(x, y)
    updateNodePosition(dragging.nodeId, snapped.x, snapped.y)
    // Move other selected nodes maintaining relative positions
    for (const other of dragging.others) {
      const ox = snapToGrid(snapped.x + other.dx, snapped.y + other.dy)
      updateNodePosition(other.id, ox.x, ox.y)
    }
    return
  }

  if (resizing.active) {
    const node = getNode(resizing.nodeId)
    if (!node) return
    const dx = (e.clientX - resizing.startX) / zoom.value
    const dy = (e.clientY - resizing.startY) / zoom.value
    const dir = resizing.direction

    let newX = resizing.origX
    let newY = resizing.origY
    let newW = resizing.origW
    let newH = resizing.origH

    if (dir.includes('e')) newW = Math.max(CONTAINER_MIN_WIDTH, resizing.origW + dx)
    if (dir.includes('w')) {
      const delta = Math.min(dx, resizing.origW - CONTAINER_MIN_WIDTH)
      newX = resizing.origX + delta
      newW = resizing.origW - delta
    }
    if (dir.includes('s')) newH = Math.max(CONTAINER_MIN_HEIGHT, resizing.origH + dy)
    if (dir.includes('n')) {
      const delta = Math.min(dy, resizing.origH - CONTAINER_MIN_HEIGHT)
      newY = resizing.origY + delta
      newH = resizing.origH - delta
    }

    // Snap dimensions
    const snapped = snapToGrid(newX, newY)
    node.x = snapped.x
    node.y = snapped.y
    node.width = Math.round(newW / 20) * 20
    node.height = Math.round(newH / 20) * 20
    return
  }

  if (wiring.active) {
    const rect = canvasRef.value.getBoundingClientRect()
    const x = (e.clientX - rect.left - pan.x) / zoom.value
    const y = (e.clientY - rect.top - pan.y) / zoom.value
    updateWiring(x, y)
    return
  }
}

function onMouseUp(e) {
  if (isPanning) {
    isPanning = false
    document.body.style.cursor = ''
    return
  }

  if (marquee.active) {
    marquee.active = false
    return
  }

  if (dragging.active) {
    // Check containment for dragged nodes (only at root level — in tab view
    // nodes already belong to the viewed container)
    if (activeParentId.value === null) {
      checkContainment(dragging.nodeId)
      for (const other of dragging.others) {
        checkContainment(other.id)
      }
    }
    // Emit batch position mutation for all moved nodes
    const positions = {}
    const primaryNode = getNode(dragging.nodeId)
    if (primaryNode) {
      positions[dragging.nodeId] = { x: primaryNode.x, y: primaryNode.y }
      // Include descendants if container
      if (primaryNode.width != null) {
        for (const desc of getDescendants(dragging.nodeId)) {
          positions[desc.id] = { x: desc.x, y: desc.y }
        }
      }
    }
    for (const other of dragging.others) {
      const n = getNode(other.id)
      if (n) {
        positions[other.id] = { x: n.x, y: n.y }
        if (n.width != null) {
          for (const desc of getDescendants(other.id)) {
            positions[desc.id] = { x: desc.x, y: desc.y }
          }
        }
      }
    }
    notifyMutation('move_nodes', { positions })
    dragging.active = false
    dragging.others = []
    document.body.style.cursor = ''
    return
  }

  if (resizing.active) {
    resizing.active = false
    document.body.style.cursor = ''
    return
  }

  if (wiring.active) {
    if (!isPlayback.value) {
      if (wiring.fromPort === '__input__') {
        // Reverse wiring: started from an input port, look for output port as drop target
        const outTarget = e.target.closest('[data-port-type="out"]')
        if (outTarget) {
          const sourceNodeId = outTarget.dataset.nodeId
          const sourcePort = outTarget.dataset.portName || 'done'
          if (sourceNodeId && sourceNodeId !== wiring.fromNodeId) {
            addEdge(sourceNodeId, sourcePort, wiring.fromNodeId)
          }
        }
      } else {
        // Normal wiring: started from output port, look for input port as drop target
        const inTarget = e.target.closest('[data-port-type="in"]')
        if (inTarget) {
          const targetNodeId = inTarget.dataset.nodeId
          if (targetNodeId && targetNodeId !== wiring.fromNodeId) {
            addEdge(wiring.fromNodeId, wiring.fromPort, targetNodeId)
          }
        }
      }
    }
    endWiring()
    return
  }
}

// ── Zooming ────────────────────────────────────────────────────────────────
function onWheel(e) {
  e.preventDefault()
  const rect = canvasRef.value.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top

  const oldZoom = zoom.value
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  const newZoom = Math.max(0.25, Math.min(4.0, oldZoom * delta))

  // Zoom centered on cursor
  pan.x = mx - (mx - pan.x) * (newZoom / oldZoom)
  pan.y = my - (my - pan.y) * (newZoom / oldZoom)
  zoom.value = newZoom
}

// ── Node dragging ──────────────────────────────────────────────────────────
const dragging = reactive({
  active: false,
  nodeId: null,     // primary dragged node
  offsetX: 0,
  offsetY: 0,
  // Multi-drag: offsets of other selected nodes relative to primary
  others: [],       // [{ id, dx, dy }]
})

function onNodeStartDrag({ nodeId, offsetX, offsetY, event }) {
  if (isPlayback.value) return
  snapshot()
  dragging.active = true
  dragging.nodeId = nodeId

  const rect = canvasRef.value.getBoundingClientRect()
  const nodeObj = getNode(nodeId)
  if (!nodeObj) return
  dragging.offsetX = (event.clientX - rect.left - pan.x) / zoom.value - nodeObj.x
  dragging.offsetY = (event.clientY - rect.top - pan.y) / zoom.value - nodeObj.y

  // If dragged node is part of multi-selection, prepare to move all
  if (isNodeSelected(nodeId) && selectedNodeIds.value.length > 1) {
    dragging.others = selectedNodeIds.value
      .filter(id => id !== nodeId)
      .map(id => {
        const n = getNode(id)
        return n ? { id, dx: n.x - nodeObj.x, dy: n.y - nodeObj.y } : null
      })
      .filter(Boolean)
  } else {
    dragging.others = []
  }

  document.body.style.cursor = 'grabbing'
}

// ── Container resize ──────────────────────────────────────────────────────
const resizing = reactive({
  active: false,
  nodeId: null,
  direction: '',   // 'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'
  startX: 0,
  startY: 0,
  origX: 0,
  origY: 0,
  origW: 0,
  origH: 0,
})

function onStartResize({ nodeId, direction, event }) {
  if (isPlayback.value) return
  snapshot()
  const node = getNode(nodeId)
  if (!node) return
  resizing.active = true
  resizing.nodeId = nodeId
  resizing.direction = direction
  resizing.startX = event.clientX
  resizing.startY = event.clientY
  resizing.origX = node.x
  resizing.origY = node.y
  resizing.origW = node.width
  resizing.origH = node.height
  document.body.style.cursor = direction + '-resize'
}

// ── Containment detection (after drag/drop) ────────────────────────────────
function checkContainment(nodeId) {
  const node = getNode(nodeId)
  if (!node) return
  // Don't re-parent entry/exit nodes, start/stop, requirements, guards, or containers into themselves
  if (isEntryOrExit(nodeId)) return
  if (node.type === '__start__' || node.type === '__stop__') return
  if (node.isRequirement || node.isGuard) return

  const cx = node.x + (node.width != null ? node.width / 2 : NODE_WIDTH / 2)
  const cy = node.y + (node.width != null ? CONTAINER_HEADER_HEIGHT + 10 : getNodeHeight(node) / 2)

  // Exclude self and all descendants
  const excludeIds = [nodeId, ...getDescendants(nodeId).map(n => n.id)]

  const container = findContainerAtPoint(cx, cy, excludeIds)
  if (container) {
    moveNodeToContainer(nodeId, container.id)
  } else if (node.parentId) {
    removeNodeFromContainer(nodeId)
  }
}

// ── Drag-and-drop from catalog ─────────────────────────────────────────────
function onDragOver(e) {
  e.preventDefault()
  e.dataTransfer.dropEffect = 'copy'
}

function onDrop(e) {
  e.preventDefault()
  if (isPlayback.value) return
  const type = e.dataTransfer.getData('action-type')
  if (!type) return

  const rect = canvasRef.value.getBoundingClientRect()
  const x = (e.clientX - rect.left - pan.x) / zoom.value - NODE_WIDTH / 2
  const y = (e.clientY - rect.top - pan.y) / zoom.value - 20
  const snapped = snapToGrid(x, y)
  // When in a container tab, new nodes go into that container
  const parentId = activeParentId.value || null
  const node = addNode(type, snapped.x, snapped.y, parentId)
  if (node) {
    // When at root level, still check if dropped visually into a container
    if (!parentId) checkContainment(node.id)
    selectNode(node.id)
  }
}

// ── Keyboard ───────────────────────────────────────────────────────────────
function onKeyDown(e) {
  if (e.code === 'Space' && !e.repeat) {
    spaceDown = true
    if (canvasRef.value) canvasRef.value.style.cursor = 'grab'
  }
}
function onKeyUp(e) {
  if (e.code === 'Space') {
    spaceDown = false
    if (canvasRef.value) canvasRef.value.style.cursor = ''
  }
}

// ── Viewport size tracking ───────────────────────────────────────────────
let resizeObserver = null

onMounted(() => {
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  // Capture-phase listener for CMD+drag panning (intercepts before child handlers)
  canvasRef.value?.addEventListener('mousedown', onMetaPanCapture, true)

  // Track canvas dimensions for zoomToFit
  if (canvasRef.value) {
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        updateViewport(entry.contentRect.width, entry.contentRect.height)
      }
    })
    resizeObserver.observe(canvasRef.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  canvasRef.value?.removeEventListener('mousedown', onMetaPanCapture, true)
  resizeObserver?.disconnect()
})
</script>

<template>
  <div
    ref="canvasRef"
    class="canvas"
    @mousedown="onCanvasMouseDown"
    @wheel.prevent="onWheel"
    @dragover="onDragOver"
    @drop="onDrop"
    @contextmenu.prevent
  >
    <!-- Marquee selection rectangle -->
    <div v-if="marquee.active && marqueeStyle" class="marquee-rect" :style="marqueeStyle"></div>

    <!-- Grid background -->
    <svg class="canvas-bg" width="100%" height="100%">
      <defs>
        <pattern
          id="grid-dots"
          :width="gridSize"
          :height="gridSize"
          patternUnits="userSpaceOnUse"
          :x="pan.x % gridSize"
          :y="pan.y % gridSize"
        >
          <circle :cx="gridSize / 2" :cy="gridSize / 2" r="1" fill="var(--border)" opacity="0.5" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#grid-dots)" />
    </svg>

    <!-- Transform container -->
    <div class="transform-container" :style="{ transform: transformStyle }">
      <!-- SVG overlay for top-level connections -->
      <svg class="connections-svg">
        <ConnectionLine
          v-for="edge in topLevelEdges"
          :key="edge.id"
          :edge="edge"
        />
      </svg>

      <!-- Container nodes (rendered first so action nodes appear on top) -->
      <ContainerNode
        v-for="node in topLevelContainers"
        :key="node.id"
        :node="node"
        :child-nodes="getChildren(node.id)"
        :child-edges="getChildEdges(node.id)"
        :zoom="zoom"
        @start-drag="onNodeStartDrag"
        @start-resize="onStartResize"
        @node-start-drag="onNodeStartDrag"
      />

      <!-- Special nodes (Start/Stop) -->
      <StartStopNode
        v-for="node in specialNodes"
        :key="node.id"
        :node="node"
        @start-drag="onNodeStartDrag"
      />

      <!-- Action nodes (top-level only) -->
      <ActionNode
        v-for="node in actionNodes"
        :key="node.id"
        :node="node"
        :zoom="zoom"
        @start-drag="onNodeStartDrag"
      />

      <!-- Requirement nodes -->
      <ActionNode
        v-for="node in requirementNodes"
        :key="node.id"
        :node="node"
        :zoom="zoom"
        @start-drag="onNodeStartDrag"
      />

      <!-- Guard nodes -->
      <ActionNode
        v-for="node in guardNodes"
        :key="node.id"
        :node="node"
        :zoom="zoom"
        @start-drag="onNodeStartDrag"
      />

      <!-- Drag line on top of everything (separate SVG so it renders above containers) -->
      <svg v-if="wiring.active" class="drag-line-svg">
        <DragLine />
      </svg>
    </div>
  </div>
</template>

<style scoped>
.canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
  background: var(--bg);
}

.canvas-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.transform-container {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
  width: 0;
  height: 0;
}

.connections-svg {
  position: absolute;
  top: 0;
  left: 0;
  width: 10000px;
  height: 10000px;
  pointer-events: none;
  overflow: visible;
}

.connections-svg :deep(g) {
  pointer-events: auto;
}

.drag-line-svg {
  position: absolute;
  top: 0;
  left: 0;
  width: 10000px;
  height: 10000px;
  pointer-events: none;
  overflow: visible;
  z-index: 1000;
}

.marquee-rect {
  position: absolute;
  border: 1.5px solid var(--accent);
  background: rgba(69, 170, 242, 0.08);
  pointer-events: none;
  z-index: 100;
  border-radius: 2px;
}
</style>
