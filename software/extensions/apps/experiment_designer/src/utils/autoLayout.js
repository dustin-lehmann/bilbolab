/**
 * Simplified Sugiyama layered layout algorithm for experiment node graphs.
 *
 * Steps:
 *   1. Build adjacency from edges
 *   2. Topological sort via Kahn's algorithm → assign layers
 *   3. Median heuristic to order nodes within each layer
 *   4. Position assignment along main axis (layers) and cross axis (within layer)
 */

import {
  NODE_WIDTH, START_WIDTH, START_HEIGHT, STOP_WIDTH, STOP_HEIGHT,
  ENTRY_WIDTH, ENTRY_HEIGHT, REQUIREMENT_WIDTH, REQUIREMENT_HEIGHT,
  GUARD_WIDTH, GUARD_HEIGHT, getNodeHeight,
} from './geometry.js'

// Layout constants
const V_LAYER_GAP = 40    // vertical: gap between layers (rows)
const V_NODE_GAP = 40     // vertical: gap between nodes in a layer (columns)
const H_LAYER_GAP = 80    // horizontal: gap between layers (columns)
const H_NODE_GAP = 30     // horizontal: gap between nodes in a layer (rows)
const COLUMN_GAP = 80     // gap between columns in column-wrap mode
const ROW_GAP = 80        // gap between rows in row-wrap mode

function getW(node) {
  if (node.type === '__start__') return START_WIDTH
  if (node.type === '__stop__') return STOP_WIDTH
  if (node.type === '__entry__' || node.type === '__exit__') return ENTRY_WIDTH
  if (node.isRequirement) return REQUIREMENT_WIDTH
  if (node.isGuard) return GUARD_WIDTH
  if (node.width != null) return node.width
  return NODE_WIDTH
}

function getH(node) {
  if (node.type === '__start__') return START_HEIGHT
  if (node.type === '__stop__') return STOP_HEIGHT
  if (node.type === '__entry__' || node.type === '__exit__') return ENTRY_HEIGHT
  if (node.isRequirement) return REQUIREMENT_HEIGHT
  if (node.isGuard) return GUARD_HEIGHT
  if (node.height != null) return node.height
  return getNodeHeight(node)
}

/**
 * Compute new positions for all visible nodes using layered layout.
 *
 * @param {Array} visibleNodes — nodes in current view
 * @param {Array} visibleEdges — edges between visible nodes
 * @param {string} direction — 'vertical' or 'horizontal'
 * @param {object} [opts] — options
 * @param {number|null} [opts.maxColumnHeight] — if set, vertical layout wraps into
 *   multiple columns when cumulative height exceeds this value (snake layout)
 * @param {number|null} [opts.maxRowWidth] — if set, horizontal layout wraps into
 *   multiple rows when cumulative width exceeds this value
 * @returns {Object|null} — { nodeId: { x, y } } or null if nothing to do
 */
export function computeAutoLayout(visibleNodes, visibleEdges, direction, opts = {}) {
  if (visibleNodes.length === 0) return null

  const isH = direction === 'horizontal'

  // Separate out requirement/guard nodes — they get placed above the graph, not in the flow
  const sideNodes = visibleNodes.filter(n => n.isRequirement || n.isGuard)
  // Separate setup/cleanup groups — placed above/below the main flow, not in it
  const setupNodes = visibleNodes.filter(n => n.type === 'setup_group')
  const cleanupNodes = visibleNodes.filter(n => n.type === 'cleanup_group')
  const flowNodes = visibleNodes.filter(n => !n.isRequirement && !n.isGuard && n.type !== 'setup_group' && n.type !== 'cleanup_group')

  if (flowNodes.length === 0 && sideNodes.length === 0) return null

  const nodeMap = new Map()
  for (const n of flowNodes) nodeMap.set(n.id, n)

  // Build adjacency
  const successors = new Map()   // id → [id]
  const predecessors = new Map() // id → [id]
  const inDegree = new Map()

  for (const n of flowNodes) {
    successors.set(n.id, [])
    predecessors.set(n.id, [])
    inDegree.set(n.id, 0)
  }

  for (const e of visibleEdges) {
    if (nodeMap.has(e.from) && nodeMap.has(e.to)) {
      successors.get(e.from).push(e.to)
      predecessors.get(e.to).push(e.from)
      inDegree.set(e.to, inDegree.get(e.to) + 1)
    }
  }

  // ── Kahn's topological sort → layer assignment ──
  const layers = []
  const layerOf = new Map()
  const queue = []

  for (const [id, deg] of inDegree) {
    if (deg === 0) queue.push(id)
  }

  // BFS-based layering: each node goes into the layer after its latest predecessor
  const nodeLayer = new Map()
  const bfsQueue = [...queue]
  for (const id of bfsQueue) nodeLayer.set(id, 0)

  let head = 0
  while (head < bfsQueue.length) {
    const id = bfsQueue[head++]
    const myLayer = nodeLayer.get(id)
    for (const succ of successors.get(id)) {
      const prev = nodeLayer.get(succ)
      const candidate = myLayer + 1
      if (prev === undefined || candidate > prev) {
        nodeLayer.set(succ, candidate)
      }
      inDegree.set(succ, inDegree.get(succ) - 1)
      if (inDegree.get(succ) === 0) {
        bfsQueue.push(succ)
      }
    }
  }

  // Handle disconnected flow nodes (no edges) — assign layer 0
  for (const n of flowNodes) {
    if (!nodeLayer.has(n.id)) {
      nodeLayer.set(n.id, 0)
    }
  }

  // Group into layers
  const maxLayer = Math.max(...nodeLayer.values(), 0)
  for (let i = 0; i <= maxLayer; i++) layers.push([])
  for (const [id, layer] of nodeLayer) {
    layers[layer].push(id)
    layerOf.set(id, layer)
  }

  // ── Median heuristic for ordering within layers ──
  // Sort each layer by median position of predecessors
  for (let i = 1; i < layers.length; i++) {
    const prevOrder = new Map()
    layers[i - 1].forEach((id, idx) => prevOrder.set(id, idx))

    layers[i].sort((a, b) => {
      const aPreds = predecessors.get(a).filter(p => prevOrder.has(p))
      const bPreds = predecessors.get(b).filter(p => prevOrder.has(p))
      const aMedian = aPreds.length > 0 ? median(aPreds.map(p => prevOrder.get(p))) : 0
      const bMedian = bPreds.length > 0 ? median(bPreds.map(p => prevOrder.get(p))) : 0
      return aMedian - bMedian
    })
  }

  // ── Position assignment ──
  const positions = {}

  if (isH) {
    // Horizontal: layers go left→right, nodes stack top→bottom within each layer
    const maxRowW = opts.maxRowWidth || null

    // Pre-compute each layer's width (widest node in that layer)
    const layerWidths = layers.map(layer => {
      let maxW = 0
      for (const id of layer) maxW = Math.max(maxW, getW(nodeMap.get(id)))
      return maxW
    })

    // Split layers into rows when cumulative width exceeds maxRowW
    const rows = [[]]  // each row is an array of layer indices
    let rowWidth = 0
    for (let i = 0; i < layers.length; i++) {
      const w = layerWidths[i]
      if (maxRowW && rows[rows.length - 1].length > 0 && rowWidth + w > maxRowW) {
        rows.push([])
        rowWidth = 0
      }
      rows[rows.length - 1].push(i)
      rowWidth += w + H_LAYER_GAP
    }

    // Position each row
    let rowY = 0
    for (const row of rows) {
      // Find the max height across all layers in this row
      let rowMaxH = 0
      for (const li of row) {
        let totalH = 0
        for (const id of layers[li]) totalH += getH(nodeMap.get(id))
        totalH += (layers[li].length - 1) * H_NODE_GAP
        rowMaxH = Math.max(rowMaxH, totalH)
      }

      let layerX = 20
      for (const li of row) {
        const layer = layers[li]
        let totalH = 0
        for (const id of layer) totalH += getH(nodeMap.get(id))
        totalH += (layer.length - 1) * H_NODE_GAP

        // Center this layer vertically within the row
        let nodeY = rowY - totalH / 2
        let maxW = 0
        for (const id of layer) {
          const n = nodeMap.get(id)
          const w = getW(n)
          const h = getH(n)
          positions[id] = { x: snap(layerX), y: snap(nodeY) }
          nodeY += h + H_NODE_GAP
          maxW = Math.max(maxW, w)
        }
        layerX += maxW + H_LAYER_GAP
      }
      rowY += rowMaxH + ROW_GAP
    }
  } else {
    // Vertical: layers go top→bottom, nodes distribute left→right
    const maxColH = opts.maxColumnHeight || null

    // Pre-compute each layer's height (tallest node in that layer)
    const layerHeights = layers.map(layer => {
      let maxH = 0
      for (const id of layer) maxH = Math.max(maxH, getH(nodeMap.get(id)))
      return maxH
    })

    // Split layers into columns when cumulative height exceeds maxColH
    const columns = [[]]  // each column is an array of layer indices
    let colHeight = 0
    for (let i = 0; i < layers.length; i++) {
      const h = layerHeights[i]
      // Start a new column if this layer would exceed the limit
      // (but always put at least one layer per column)
      if (maxColH && columns[columns.length - 1].length > 0 && colHeight + h > maxColH) {
        columns.push([])
        colHeight = 0
      }
      columns[columns.length - 1].push(i)
      colHeight += h + V_LAYER_GAP
    }

    // Position each column
    let columnX = 0
    for (const col of columns) {
      // Find the max width across all layers in this column
      let colMaxW = 0
      for (const li of col) {
        let totalW = 0
        for (const id of layers[li]) totalW += getW(nodeMap.get(id))
        totalW += (layers[li].length - 1) * V_NODE_GAP
        colMaxW = Math.max(colMaxW, totalW)
      }

      let layerY = 20
      for (const li of col) {
        const layer = layers[li]
        let totalW = 0
        for (const id of layer) totalW += getW(nodeMap.get(id))
        totalW += (layer.length - 1) * V_NODE_GAP

        // Center this layer within the column
        let nodeX = columnX - totalW / 2
        for (const id of layer) {
          const n = nodeMap.get(id)
          const w = getW(n)
          positions[id] = { x: snap(nodeX), y: snap(layerY) }
          nodeX += w + V_NODE_GAP
        }
        layerY += layerHeights[li] + V_LAYER_GAP
      }
      columnX += colMaxW + COLUMN_GAP
    }
  }

  // ── Position requirement/guard nodes above the main graph ──
  if (sideNodes.length > 0) {
    // Find the top-left corner of the positioned flow graph
    let minY = Infinity, minX = Infinity
    for (const pos of Object.values(positions)) {
      if (pos.y < minY) minY = pos.y
      if (pos.x < minX) minX = pos.x
    }
    if (!isFinite(minY)) minY = 20
    if (!isFinite(minX)) minX = 20

    // Place side nodes in a row above the graph (vertical) or column to the left (horizontal)
    const SIDE_GAP = 12
    if (isH) {
      // Horizontal layout: place side nodes in a row above the graph, left-aligned
      let sideX = minX
      const sideRowY = minY - REQUIREMENT_HEIGHT - 30
      for (const n of sideNodes) {
        positions[n.id] = { x: snap(sideX), y: snap(sideRowY) }
        sideX += getW(n) + SIDE_GAP
      }
    } else {
      // Vertical layout: place side nodes in a row above the graph
      let sideX = minX
      const sideRowY = minY - REQUIREMENT_HEIGHT - 30
      for (const n of sideNodes) {
        positions[n.id] = { x: snap(sideX), y: snap(sideRowY) }
        sideX += getW(n) + SIDE_GAP
      }
    }
  }

  // ── Position setup/cleanup groups above/below the main flow ──
  if (setupNodes.length > 0 || cleanupNodes.length > 0) {
    let flowMinX = Infinity, flowMinY = Infinity, flowMaxX = -Infinity, flowMaxY = -Infinity
    for (const pos of Object.values(positions)) {
      if (pos.x < flowMinX) flowMinX = pos.x
      if (pos.y < flowMinY) flowMinY = pos.y
      if (pos.x > flowMaxX) flowMaxX = pos.x
      if (pos.y > flowMaxY) flowMaxY = pos.y
    }
    // Include side nodes in bounds calculation
    for (const n of sideNodes) {
      const p = positions[n.id]
      if (p) {
        if (p.y < flowMinY) flowMinY = p.y
      }
    }
    if (!isFinite(flowMinY)) flowMinY = 20
    if (!isFinite(flowMaxY)) flowMaxY = 100
    if (!isFinite(flowMinX)) flowMinX = 20
    if (!isFinite(flowMaxX)) flowMaxX = 200

    const PHASE_GAP = 40

    if (isH) {
      // Horizontal layout: setup to the left, cleanup to the right
      for (const n of setupNodes) {
        const w = getW(n)
        positions[n.id] = { x: snap(flowMinX - w - PHASE_GAP), y: snap(flowMinY) }
      }
      for (const n of cleanupNodes) {
        // flowMaxX is just x coord of rightmost node; add typical node width
        positions[n.id] = { x: snap(flowMaxX + NODE_WIDTH + PHASE_GAP), y: snap(flowMinY) }
      }
    } else {
      // Vertical layout: setup above, cleanup below
      for (const n of setupNodes) {
        const h = getH(n)
        positions[n.id] = { x: snap(flowMinX), y: snap(flowMinY - h - PHASE_GAP) }
      }
      // Find actual max Y including node heights
      let actualMaxY = flowMaxY
      for (const fn of flowNodes) {
        const p = positions[fn.id]
        if (p) actualMaxY = Math.max(actualMaxY, p.y + getH(fn))
      }
      for (const n of cleanupNodes) {
        positions[n.id] = { x: snap(flowMinX), y: snap(actualMaxY + PHASE_GAP) }
      }
    }
  }

  return positions
}

function median(arr) {
  if (arr.length === 0) return 0
  const sorted = [...arr].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

function snap(v, grid = 20) {
  return Math.round(v / grid) * grid
}
