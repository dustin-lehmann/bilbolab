/**
 * Geometry utilities for node-graph canvas: port positions and bézier routing.
 * Direction-aware: reads layoutDirection from graphState (safe — all reads inside function bodies).
 */

import { layoutDirection } from '../graphState.js'
import { getSummary, getParamLines } from '../actionRegistry.js'

// ── Node dimensions ────────────────────────────────────────────────────────
export const NODE_WIDTH = 160
export const NODE_HEADER_HEIGHT = 28
export const NODE_ID_HEIGHT = 20
export const NODE_SUMMARY_HEIGHT = 20
export const NODE_PARAM_LINE_HEIGHT = 15  // per param line
export const NODE_PARAM_PADDING = 4       // top+bottom padding for param section
export const NODE_PORT_SECTION_HEIGHT = 20  // port labels area
export const NODE_PADDING_BOTTOM = 4

export const START_WIDTH = 100
export const START_HEIGHT = 40
export const STOP_WIDTH = 100
export const STOP_HEIGHT = 40

// Container dimensions
export const CONTAINER_HEADER_HEIGHT = 32
export const CONTAINER_MIN_WIDTH = 200
export const CONTAINER_MIN_HEIGHT = 200

// Entry/exit node dimensions
export const ENTRY_WIDTH = 80
export const ENTRY_HEIGHT = 30

// Requirement node dimensions
export const REQUIREMENT_WIDTH = 140
export const REQUIREMENT_HEIGHT = 48

// Guard node dimensions
export const GUARD_WIDTH = 200
export const GUARD_HEIGHT = 48

// Wait bar / trigger bar dimensions
export const WAIT_BAR_HEIGHT = 18
export const TRIGGER_BAR_HEIGHT = 18

/**
 * Compute the total height of an action node.
 */
export function getNodeHeight(node) {
  if (node.isRequirement) return REQUIREMENT_HEIGHT
  if (node.isGuard) return GUARD_HEIGHT
  if (node.type === '__entry__' || node.type === '__exit__') return ENTRY_HEIGHT
  if (node.height != null) return node.height  // Container nodes have explicit height
  const isH = layoutDirection.value === 'horizontal'
  let h = NODE_HEADER_HEIGHT
  if (node.trigger && node.trigger.type !== 'transition') h += TRIGGER_BAR_HEIGHT
  if (node.wait_before) h += WAIT_BAR_HEIGHT
  // Compute summary/param lines on the fly to avoid stale cached values
  const summaryText = getSummary(node)
  if (summaryText) {
    h += NODE_SUMMARY_HEIGHT
  } else {
    const plc = getParamLines(node).length
    if (plc > 0) h += plc * NODE_PARAM_LINE_HEIGHT + NODE_PARAM_PADDING
  }
  if (node.wait_after) h += WAIT_BAR_HEIGHT
  // In horizontal mode, port labels are absolutely positioned on the right side,
  // so they don't contribute to the node's height.
  if (!isH) {
    h += NODE_PORT_SECTION_HEIGHT
    h += NODE_PADDING_BOTTOM
  }
  return h
}

/**
 * Get the position of a node's input port.
 * Vertical: top center. Horizontal: left center.
 */
export function getInputPortPos(node) {
  if (node.isRequirement) return null
  if (node.isGuard) return null
  if (node.type === '__start__') return null
  if (node.type === '__entry__') return null  // Entry nodes have no input port
  // Hide input port when trigger is not transition
  if (node.trigger && node.trigger.type !== 'transition') return null

  const isH = layoutDirection.value === 'horizontal'

  if (node.type === '__exit__') {
    return isH
      ? { x: node.x, y: node.y + ENTRY_HEIGHT / 2 }
      : { x: node.x + ENTRY_WIDTH / 2, y: node.y }
  }
  if (node.type === '__stop__') {
    return isH
      ? { x: node.x, y: node.y + STOP_HEIGHT / 2 }
      : { x: node.x + STOP_WIDTH / 2, y: node.y }
  }
  // Container nodes
  if (node.width != null) {
    return isH
      ? { x: node.x, y: node.y + node.height / 2 }
      : { x: node.x + node.width / 2, y: node.y }
  }
  // Regular action nodes
  const h = getNodeHeight(node)
  return isH
    ? { x: node.x, y: node.y + h / 2 }
    : { x: node.x + NODE_WIDTH / 2, y: node.y }
}

/**
 * Get the position of a node's output port by port name.
 * Vertical: bottom (distributed by x). Horizontal: right (distributed by y).
 */
export function getOutputPortPos(node, portName) {
  if (node.isRequirement) return null
  if (node.isGuard) return null
  if (node.type === '__stop__') return null
  if (node.type === '__exit__') return null  // Exit nodes have no output port

  const isH = layoutDirection.value === 'horizontal'

  if (node.type === '__start__') {
    return isH
      ? { x: node.x + START_WIDTH, y: node.y + START_HEIGHT / 2 }
      : { x: node.x + START_WIDTH / 2, y: node.y + START_HEIGHT }
  }
  if (node.type === '__entry__') {
    return isH
      ? { x: node.x + ENTRY_WIDTH, y: node.y + ENTRY_HEIGHT / 2 }
      : { x: node.x + ENTRY_WIDTH / 2, y: node.y + ENTRY_HEIGHT }
  }

  // Container nodes
  if (node.width != null) {
    const outPorts = node._outPorts || ['done']
    const idx = outPorts.indexOf(portName)
    if (isH) {
      if (idx === -1) return { x: node.x + node.width, y: node.y + node.height / 2 }
      const spacing = node.height / (outPorts.length + 1)
      return { x: node.x + node.width, y: node.y + spacing * (idx + 1) }
    } else {
      if (idx === -1) return { x: node.x + node.width / 2, y: node.y + node.height }
      const spacing = node.width / (outPorts.length + 1)
      return { x: node.x + spacing * (idx + 1), y: node.y + node.height }
    }
  }

  // Regular action nodes
  const h = getNodeHeight(node)
  const outPorts = node._outPorts || ['done']
  const idx = outPorts.indexOf(portName)

  if (isH) {
    if (idx === -1) return { x: node.x + NODE_WIDTH, y: node.y + h / 2 }
    const spacing = h / (outPorts.length + 1)
    return { x: node.x + NODE_WIDTH, y: node.y + spacing * (idx + 1) }
  } else {
    if (idx === -1) return { x: node.x + NODE_WIDTH / 2, y: node.y + h }
    const spacing = NODE_WIDTH / (outPorts.length + 1)
    return { x: node.x + spacing * (idx + 1), y: node.y + h }
  }
}

/**
 * Compute edge control points for routing between two points.
 *
 * Returns one of:
 *   { isMultiSegment: false, cp1x, cp1y, cp2x, cp2y }
 *     — single cubic bézier (forward edges)
 *   { isMultiSegment: true, svgPath, segments, mid }
 *     — multi-segment path (backward / cross-column/row edges)
 *
 * Segments are typed: { type: 'L'|'Q'|'C', x1, y1, ..., x2, y2 }
 */
export function getEdgeControlPoints(x1, y1, x2, y2) {
  const isH = layoutDirection.value === 'horizontal'

  if (isH) {
    const dx = Math.abs(x2 - x1)
    const dy = Math.abs(y2 - y1)
    const cp = Math.max(40, dx * 0.4)

    if (x2 > x1 + 10) {
      return { cp1x: x1 + cp, cp1y: y1, cp2x: x2 - cp, cp2y: y2, isMultiSegment: false }
    }

    // Cross-row backward: orthogonal route around row edges through the inter-row gap
    // Route: right from source → down to gap → left across gap → down to target row → right to target
    if (dy > 50) {
      const m = 25, r = 10
      const sy = y2 > y1 ? 1 : -1
      const xRight = x1 + m         // right margin past source
      const xLeft = x2 - m          // left margin before target
      const yGap = (y1 + y2) / 2    // mid-gap between rows
      const svgPath = [
        `M ${x1} ${y1}`,
        `L ${xRight - r} ${y1}`,
        `Q ${xRight} ${y1}, ${xRight} ${y1 + sy * r}`,
        `L ${xRight} ${yGap - sy * r}`,
        `Q ${xRight} ${yGap}, ${xRight - r} ${yGap}`,
        `L ${xLeft + r} ${yGap}`,
        `Q ${xLeft} ${yGap}, ${xLeft} ${yGap + sy * r}`,
        `L ${xLeft} ${y2 - sy * r}`,
        `Q ${xLeft} ${y2}, ${xLeft + r} ${y2}`,
        `L ${x2} ${y2}`,
      ].join(' ')
      return {
        isMultiSegment: true, svgPath,
        segments: [
          { type: 'L', x1, y1, x2: xRight - r, y2: y1 },
          { type: 'Q', x1: xRight - r, y1, cpx: xRight, cpy: y1, x2: xRight, y2: y1 + sy * r },
          { type: 'L', x1: xRight, y1: y1 + sy * r, x2: xRight, y2: yGap - sy * r },
          { type: 'Q', x1: xRight, y1: yGap - sy * r, cpx: xRight, cpy: yGap, x2: xRight - r, y2: yGap },
          { type: 'L', x1: xRight - r, y1: yGap, x2: xLeft + r, y2: yGap },
          { type: 'Q', x1: xLeft + r, y1: yGap, cpx: xLeft, cpy: yGap, x2: xLeft, y2: yGap + sy * r },
          { type: 'L', x1: xLeft, y1: yGap + sy * r, x2: xLeft, y2: y2 - sy * r },
          { type: 'Q', x1: xLeft, y1: y2 - sy * r, cpx: xLeft, cpy: y2, x2: xLeft + r, y2 },
          { type: 'L', x1: xLeft + r, y1: y2, x2, y2 },
        ],
        mid: { x: (xRight + xLeft) / 2, y: yGap },
      }
    }

    // Regular backward
    const offsetY = (y2 > y1) ? 60 : -60
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2
    return {
      isMultiSegment: true,
      svgPath: `M ${x1} ${y1} C ${x1 + 60} ${y1}, ${x1 + 60} ${y1 + offsetY}, ${mx} ${my} C ${x2 - 60} ${y2 - offsetY}, ${x2 - 60} ${y2}, ${x2} ${y2}`,
      segments: [
        { type: 'C', x1, y1, cp1x: x1 + 60, cp1y: y1, cp2x: x1 + 60, cp2y: y1 + offsetY, x2: mx, y2: my },
        { type: 'C', x1: mx, y1: my, cp1x: x2 - 60, cp1y: y2 - offsetY, cp2x: x2 - 60, cp2y: y2, x2, y2 },
      ],
      mid: { x: mx, y: my },
    }
  }

  // Vertical
  const dy = Math.abs(y2 - y1)
  const dx = Math.abs(x2 - x1)
  const cp = Math.max(40, dy * 0.4)

  if (y2 > y1 + 10) {
    return { cp1x: x1, cp1y: y1 + cp, cp2x: x2, cp2y: y2 - cp, isMultiSegment: false }
  }

  // Cross-column backward: orthogonal route around column edges through the inter-column gap
  // Route: down from source → across to gap → up through gap → across to target → down to target
  if (dx > 120) {
    const m = 25, r = 10
    const sx = x2 > x1 ? 1 : -1
    const yBottom = y1 + m         // below source
    const yTop = y2 - m            // above target
    const xGap = (x1 + x2) / 2    // mid-gap between columns
    const svgPath = [
      `M ${x1} ${y1}`,
      `L ${x1} ${yBottom - r}`,
      `Q ${x1} ${yBottom}, ${x1 + sx * r} ${yBottom}`,
      `L ${xGap - sx * r} ${yBottom}`,
      `Q ${xGap} ${yBottom}, ${xGap} ${yBottom - r}`,
      `L ${xGap} ${yTop + r}`,
      `Q ${xGap} ${yTop}, ${xGap + sx * r} ${yTop}`,
      `L ${x2 - sx * r} ${yTop}`,
      `Q ${x2} ${yTop}, ${x2} ${yTop + r}`,
      `L ${x2} ${y2}`,
    ].join(' ')
    return {
      isMultiSegment: true, svgPath,
      segments: [
        { type: 'L', x1, y1, x2: x1, y2: yBottom - r },
        { type: 'Q', x1, y1: yBottom - r, cpx: x1, cpy: yBottom, x2: x1 + sx * r, y2: yBottom },
        { type: 'L', x1: x1 + sx * r, y1: yBottom, x2: xGap - sx * r, y2: yBottom },
        { type: 'Q', x1: xGap - sx * r, y1: yBottom, cpx: xGap, cpy: yBottom, x2: xGap, y2: yBottom - r },
        { type: 'L', x1: xGap, y1: yBottom - r, x2: xGap, y2: yTop + r },
        { type: 'Q', x1: xGap, y1: yTop + r, cpx: xGap, cpy: yTop, x2: xGap + sx * r, y2: yTop },
        { type: 'L', x1: xGap + sx * r, y1: yTop, x2: x2 - sx * r, y2: yTop },
        { type: 'Q', x1: x2 - sx * r, y1: yTop, cpx: x2, cpy: yTop, x2, y2: yTop + r },
        { type: 'L', x1: x2, y1: yTop + r, x2, y2 },
      ],
      mid: { x: xGap, y: (yBottom + yTop) / 2 },
    }
  }

  // Regular backward
  const offsetX = (x2 > x1) ? 60 : -60
  const mx = x1 + offsetX, my = (y1 + y2) / 2
  return {
    isMultiSegment: true,
    svgPath: `M ${x1} ${y1} C ${x1} ${y1 + 60}, ${mx} ${y1 + 60}, ${mx} ${my} C ${mx} ${y2 - 60}, ${x2} ${y2 - 60}, ${x2} ${y2}`,
    segments: [
      { type: 'C', x1, y1, cp1x: x1, cp1y: y1 + 60, cp2x: mx, cp2y: y1 + 60, x2: mx, y2: my },
      { type: 'C', x1: mx, y1: my, cp1x: mx, cp1y: y2 - 60, cp2x: x2, cp2y: y2 - 60, x2, y2 },
    ],
    mid: { x: mx, y: my },
  }
}

/**
 * Compute SVG path between two points.
 */
export function computeBezierPath(x1, y1, x2, y2) {
  const pts = getEdgeControlPoints(x1, y1, x2, y2)
  if (!pts.isMultiSegment) {
    return `M ${x1} ${y1} C ${pts.cp1x} ${pts.cp1y}, ${pts.cp2x} ${pts.cp2y}, ${x2} ${y2}`
  }
  return pts.svgPath
}

/**
 * Hit-test a point against an edge path (approximate by sampling).
 */
export function hitTestBezier(x1, y1, x2, y2, px, py, threshold = 8) {
  const pts = getEdgeControlPoints(x1, y1, x2, y2)
  const steps = 20

  if (!pts.isMultiSegment) {
    for (let i = 0; i <= steps; i++) {
      const t = i / steps
      const bx = cubicPoint(x1, pts.cp1x, pts.cp2x, x2, t)
      const by = cubicPoint(y1, pts.cp1y, pts.cp2y, y2, t)
      if (Math.hypot(bx - px, by - py) < threshold) return true
    }
    return false
  }

  for (const seg of pts.segments) {
    const n = seg.type === 'L' ? 4 : steps
    for (let i = 0; i <= n; i++) {
      const t = i / n
      const p = sampleSegment(seg, t)
      if (Math.hypot(p.x - px, p.y - py) < threshold) return true
    }
  }
  return false
}

function sampleSegment(seg, t) {
  if (seg.type === 'L') {
    return {
      x: seg.x1 + t * (seg.x2 - seg.x1),
      y: seg.y1 + t * (seg.y2 - seg.y1),
    }
  }
  if (seg.type === 'Q') {
    const mt = 1 - t
    return {
      x: mt * mt * seg.x1 + 2 * mt * t * seg.cpx + t * t * seg.x2,
      y: mt * mt * seg.y1 + 2 * mt * t * seg.cpy + t * t * seg.y2,
    }
  }
  // Cubic
  const mt = 1 - t
  return {
    x: mt*mt*mt*seg.x1 + 3*mt*mt*t*seg.cp1x + 3*mt*t*t*seg.cp2x + t*t*t*seg.x2,
    y: mt*mt*mt*seg.y1 + 3*mt*mt*t*seg.cp1y + 3*mt*t*t*seg.cp2y + t*t*t*seg.y2,
  }
}

function cubicPoint(p0, p1, p2, p3, t) {
  const mt = 1 - t
  return mt * mt * mt * p0 + 3 * mt * mt * t * p1 + 3 * mt * t * t * p2 + t * t * t * p3
}

/**
 * Get the visual center of a port DOM element in canvas (transform-container) coordinates.
 * This accounts for any CSS transforms (container body zoom, etc.) automatically.
 */
export function getPortVisualCenter(portEl, panX, panY, outerZoom) {
  const rect = portEl.getBoundingClientRect()
  // Traverse up to find the canvas element rather than using a global query
  const canvasEl = portEl.closest('.canvas') || document.querySelector('.canvas')
  if (!canvasEl) return null
  const canvasRect = canvasEl.getBoundingClientRect()
  return {
    x: (rect.left + rect.width / 2 - canvasRect.left - panX) / outerZoom,
    y: (rect.top + rect.height / 2 - canvasRect.top - panY) / outerZoom,
  }
}

/**
 * Snap a position to a grid.
 */
export function snapToGrid(x, y, gridSize = 20) {
  return {
    x: Math.round(x / gridSize) * gridSize,
    y: Math.round(y / gridSize) * gridSize,
  }
}
