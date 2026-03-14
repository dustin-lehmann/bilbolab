/**
 * Central reactive state for the experiment node graph.
 * Imported by all components that need to read/write the graph.
 *
 * Uses the new core experiment framework model:
 *   - Nodes have trigger types (immediate, transition, tick, time, event, periodic)
 *   - Edges carry transition port names + optional data mappings
 *   - Experiment-level variables are first-class
 */
import { reactive, ref, computed, watch, toRaw } from 'vue'
import { createDefaultParams, getSummary, getParamLines, getTransitionPorts, getAllActions, INTERNAL_ACTIONS, isContainer as isContainerType, isRequirementType, isGuardType } from './actionRegistry.js'
import { notifyMutation, isApplyingRemote } from './mutationBridge.js'

// ── Mode ───────────────────────────────────────────────────────────────────
export const mode = ref('edit')  // 'edit' | 'playback'

// ── Action visual states (for playback highlighting) ───────────────────────
// Map: actionId -> 'normal' | 'highlighted' | 'dimmed' | 'active' | 'completed' | 'error'
export const actionStates = ref({})

export function setMode(m) {
  mode.value = m
  if (m === 'edit') {
    clearActionStates()
  }
}

export function setActionState(actionId, state) {
  actionStates.value = { ...actionStates.value, [actionId]: state }
  if (state === 'active' && followMode.value) {
    centerOnNode(actionId)
  }
}

export function clearActionStates() {
  actionStates.value = {}
}

// ── Auto-save control ──────────────────────────────────────────────────────
export const enableAutoSave = ref(true)

// ── Graph data ─────────────────────────────────────────────────────────────
export const nodes = ref([])
export const edges = ref([])

// ── Experiment metadata ────────────────────────────────────────────────────
export const meta = reactive({
  id: 'experiment_1',
  description: 'New experiment',
  timeout: null,
  variables: {},  // { name: value } — experiment-level variables
  events: [],     // string[] — declared experiment events
})

/**
 * Get all known event names: manually declared + auto-detected from emit_event/wait_for_event nodes.
 * Returns { name: 'manual' | 'auto' } map.
 */
export function getAllEventNames() {
  const result = {}
  // Manually declared events
  for (const name of meta.events) {
    if (name) result[name] = 'manual'
  }
  // Auto-detect from graph nodes
  for (const node of nodes.value) {
    if ((node.type === 'emit_event' || node.type === 'wait_for_event') && node.params?.event) {
      const name = node.params.event
      if (name && !(name in result)) result[name] = 'auto'
    }
  }
  return result
}

// ── Viewport ───────────────────────────────────────────────────────────────
export const pan = reactive({ x: 0, y: 0 })
export const zoom = ref(1)

// ── Selection ──────────────────────────────────────────────────────────────
export const selection = reactive({
  type: null, // 'node' | 'edge' | 'multi' | null
  id: null,
})

// Multi-selection: array of selected node IDs (for marquee and shift-click)
export const selectedNodeIds = ref([])

// ── Drag-wiring state ──────────────────────────────────────────────────────
export const wiring = reactive({
  active: false,
  fromNodeId: null,
  fromPort: null,
  startX: 0,
  startY: 0,
  currentX: 0,
  currentY: 0,
})

// ── Dark mode ──────────────────────────────────────────────────────────────
export const darkMode = ref(localStorage.getItem('experiment-designer-theme') !== 'light')

// ── Layout direction ──────────────────────────────────────────────────────
export const layoutDirection = ref(localStorage.getItem('experiment-designer-direction') || 'vertical')
export function setLayoutDirection(dir) { layoutDirection.value = dir; localStorage.setItem('experiment-designer-direction', dir) }
export function toggleLayoutDirection() {
  setLayoutDirection(layoutDirection.value === 'vertical' ? 'horizontal' : 'vertical')
  snapshot()
  autoLayoutRecursive()
  nodes.value = [...nodes.value]
  zoomToFit()
}

// ── Column-wrap layout ───────────────────────────────────────────────────
export const columnWrap = ref(localStorage.getItem('experiment-designer-column-wrap') === 'true')
export function setColumnWrap(v) { columnWrap.value = v; localStorage.setItem('experiment-designer-column-wrap', v) }
export function toggleColumnWrap() {
  setColumnWrap(!columnWrap.value)
  snapshot()
  autoLayoutRecursive()
  nodes.value = [...nodes.value]
  zoomToFit()
}

// ── Panel collapse state ──────────────────────────────────────────────────
export const inspectorCollapsed = ref(false)
export function setInspectorCollapsed(v) { inspectorCollapsed.value = v }
export function toggleInspector() { inspectorCollapsed.value = !inspectorCollapsed.value }

// ── Follow mode (auto-center on active action during playback) ────────────
export const followMode = ref(localStorage.getItem('experiment-designer-follow') !== 'false')
export function setFollowMode(enabled) { followMode.value = enabled; localStorage.setItem('experiment-designer-follow', enabled) }
export function toggleFollowMode() { setFollowMode(!followMode.value) }

// ── Viewport tracking (Canvas.vue updates via ResizeObserver) ─────────────
export const viewport = reactive({ width: 800, height: 600 })
export function updateViewport(w, h) { viewport.width = w; viewport.height = h }

// ── Undo/Redo ──────────────────────────────────────────────────────────────
const undoStack = ref([])
const redoStack = ref([])
const MAX_UNDO = 50
let skipSnapshot = false

export function snapshot() {
  if (skipSnapshot || isApplyingRemote()) return
  const state = JSON.stringify({ nodes: nodes.value, edges: edges.value, meta: toRaw(meta) })
  undoStack.value.push(state)
  if (undoStack.value.length > MAX_UNDO) undoStack.value.shift()
  redoStack.value = []
}

export function undo() {
  if (undoStack.value.length === 0) return
  const current = JSON.stringify({ nodes: nodes.value, edges: edges.value, meta: toRaw(meta) })
  redoStack.value.push(current)
  const prev = JSON.parse(undoStack.value.pop())
  skipSnapshot = true
  nodes.value = prev.nodes
  edges.value = prev.edges
  Object.assign(meta, prev.meta)
  skipSnapshot = false
  notifyMutation('load_state', {
    nodes: toRaw(nodes.value),
    edges: toRaw(edges.value),
    meta: toRaw(meta),
    nodeCounter,
  })
}

export function redo() {
  if (redoStack.value.length === 0) return
  const current = JSON.stringify({ nodes: nodes.value, edges: edges.value, meta: toRaw(meta) })
  undoStack.value.push(current)
  const next = JSON.parse(redoStack.value.pop())
  skipSnapshot = true
  nodes.value = next.nodes
  edges.value = next.edges
  Object.assign(meta, next.meta)
  skipSnapshot = false
  notifyMutation('load_state', {
    nodes: toRaw(nodes.value),
    edges: toRaw(edges.value),
    meta: toRaw(meta),
    nodeCounter,
  })
}

export const canUndo = computed(() => undoStack.value.length > 0)
export const canRedo = computed(() => redoStack.value.length > 0)

// ── ID generation ──────────────────────────────────────────────────────────
let nodeCounter = 0

function nextNodeId(type) {
  nodeCounter++
  return `${type}_${nodeCounter}`
}

// ── Node helpers ───────────────────────────────────────────────────────────

/**
 * Add a new node to the graph.
 *
 * Node shape:
 *   {
 *     id: string,
 *     type: string (action type_id from registry),
 *     x, y: number (canvas position),
 *     params: { ... },              — action parameters (raw, may contain expressions)
 *     trigger: { type, tick, time, event, period, period_unit } | null,
 *     _summaryText: string,         — computed compact display text
 *     _outPorts: string[],          — transition port names (from registry)
 *   }
 *
 * Special nodes: __start__ (entry point), __stop__ (visual endpoint)
 */
export function addNode(type, x, y, parentId = null) {
  // Only one setup_group / cleanup_group allowed
  if (type === 'setup_group' || type === 'cleanup_group') {
    if (nodes.value.some(n => n.type === type)) return null
  }

  snapshot()

  if (type === '__start__') {
    const node = { id: '__start__', type: '__start__', x, y, parentId: null }
    nodes.value = [...nodes.value, node]
    notifyMutation('add_node', { node: toRaw(node) })
    return node
  }

  if (type === '__stop__') {
    const id = nextNodeId('stop')
    const node = {
      id,
      type: '__stop__',
      x, y,
      parentId: null,
      params: { status: 'finished', message: '' },
    }
    nodes.value = [...nodes.value, node]
    notifyMutation('add_node', { node: toRaw(node) })
    return node
  }

  const params = createDefaultParams(type)
  const id = nextNodeId(type)
  const def = getAllActions()[type]

  // Requirement nodes: simplified shape, no ports, always root-level
  if (isRequirementType(type)) {
    const node = {
      id,
      type,
      x,
      y,
      parentId: null,
      params,
      isRequirement: true,
      _summaryText: getSummary({ type, params }),
      _paramLineCount: getSummary({ type, params }) ? 0 : getParamLines({ type, params }).length,
    }
    nodes.value = [...nodes.value, node]
    notifyMutation('add_node', { node: toRaw(node) })
    return node
  }

  // Guard nodes: simplified shape, no ports, always root-level
  if (isGuardType(type)) {
    const node = {
      id,
      type,
      x,
      y,
      parentId: null,
      params,
      isGuard: true,
      _summaryText: getSummary({ type, params }),
      _paramLineCount: getSummary({ type, params }) ? 0 : getParamLines({ type, params }).length,
    }
    nodes.value = [...nodes.value, node]
    notifyMutation('add_node', { node: toRaw(node) })
    return node
  }

  const outPorts = getTransitionPorts(type)

  const node = {
    id,
    type,
    x,
    y,
    parentId: parentId || null,
    params,
    trigger: null,  // determined by connections: immediate if from __start__, transition if from another action
    wait_before: null,
    wait_after: null,
    _summaryText: getSummary({ type, params }),
    _paramLineCount: getSummary({ type, params }) ? 0 : getParamLines({ type, params }).length,
    _outPorts: outPorts,
  }

  // Container nodes get width/height
  if (def && def.isContainer) {
    node.width = def.defaultWidth || 320
    node.height = def.defaultHeight || 400
  }

  nodes.value = [...nodes.value, node]

  // Auto-create entry/exit nodes for containers
  if (def && def.isContainer) {
    const entryId = `__entry_${id}__`
    const exitId = `__exit_${id}__`
    const isH = layoutDirection.value === 'horizontal'
    // Position entry/exit centered, near top/bottom (vertical) or left/right (horizontal).
    // ENTRY_WIDTH = 80, ENTRY_HEIGHT = 30
    const headerH = 32
    const portsH = 28
    let entryX, entryY, exitX, exitY

    if (isH) {
      const bodyLeft = x + 8
      const bodyRight = x + node.width - 8
      const centerY = y + headerH + (node.height - headerH - portsH) / 2 - 15
      entryX = bodyLeft
      entryY = centerY
      exitX = bodyRight - 80
      exitY = centerY
    } else {
      const bodyTop = y + headerH
      const bodyBottom = y + node.height - portsH
      const centerX = x + (node.width - 80) / 2
      entryX = centerX
      entryY = bodyTop + 8
      exitX = centerX
      exitY = bodyBottom - 30 - 8
    }

    const entryNode = {
      id: entryId,
      type: '__entry__',
      x: entryX,
      y: entryY,
      parentId: id,
      _outPorts: ['done'],
    }
    const exitNode = {
      id: exitId,
      type: '__exit__',
      x: exitX,
      y: exitY,
      parentId: id,
      _outPorts: [],
    }
    nodes.value = [...nodes.value, entryNode, exitNode]
    notifyMutation('add_node', { node: toRaw(entryNode) })
    notifyMutation('add_node', { node: toRaw(exitNode) })
  }

  notifyMutation('add_node', { node: toRaw(node) })
  return node
}

export function removeNode(nodeId) {
  if (nodeId === '__start__') return
  const targetNode = nodes.value.find(n => n.id === nodeId)
  if (targetNode && targetNode.type === '__stop__') return
  // Prevent deleting entry/exit nodes directly
  if (isEntryOrExit(nodeId)) return

  snapshot()

  // If removing a container, recursively remove all descendants
  const descendants = getDescendants(nodeId)
  const allIds = [nodeId, ...descendants.map(n => n.id)]

  // Close any open tabs for removed containers
  for (const id of allIds) {
    closeContainerTab(id)
  }

  edges.value = edges.value.filter(e => !allIds.includes(e.from) && !allIds.includes(e.to))
  nodes.value = nodes.value.filter(n => !allIds.includes(n.id))

  if (selection.type === 'node' && allIds.includes(selection.id)) {
    selection.type = null
    selection.id = null
  }
  selectedNodeIds.value = selectedNodeIds.value.filter(id => !allIds.includes(id))
  notifyMutation('remove_node', { id: nodeId })
}

export function updateNodePosition(nodeId, x, y) {
  const node = nodes.value.find(n => n.id === nodeId)
  if (!node) return

  // If this is a container, move all descendants too
  const dx = x - node.x
  const dy = y - node.y
  node.x = x
  node.y = y

  if (node.width != null) {
    // Container node — cascade position delta to all descendants
    const descendants = getDescendants(nodeId)
    for (const child of descendants) {
      child.x += dx
      child.y += dy
    }
  }
}

export function updateNodeParams(nodeId, params) {
  const node = nodes.value.find(n => n.id === nodeId)
  if (!node) return
  node.params = { ...params }
  node._summaryText = getSummary({ type: node.type, params: node.params })
  node._paramLineCount = node._summaryText ? 0 : getParamLines({ type: node.type, params: node.params }).length
  nodes.value = [...nodes.value]
  notifyMutation('update_node_params', { id: nodeId, params: toRaw(node.params) })
}

export function updateNodeField(nodeId, field, value) {
  const node = nodes.value.find(n => n.id === nodeId)
  if (!node) return
  node[field] = value
  nodes.value = [...nodes.value]
  notifyMutation('update_node_field', { id: nodeId, field, value: toRaw(value) })
}

export function getNode(nodeId) {
  return nodes.value.find(n => n.id === nodeId)
}

// ── Edge helpers ───────────────────────────────────────────────────────────

/**
 * Edge shape:
 *   {
 *     id: string,
 *     from: string (source node id),
 *     fromPort: string (transition port name: 'done', 'error', 'timeout'),
 *     to: string (target node id),
 *     mapping: { param: value_or_expression } | null,  — data mapping (Phase 2)
 *   }
 */
export function addEdge(fromNodeId, fromPort, toNodeId) {
  // Prevent duplicates
  const exists = edges.value.some(
    e => e.from === fromNodeId && e.fromPort === fromPort && e.to === toNodeId
  )
  if (exists) return null

  // Prevent self-loops
  if (fromNodeId === toNodeId) return null

  // Prevent connecting to __start__ (it only has outputs)
  if (toNodeId === '__start__') return null

  // Prevent connecting to/from requirement, guard, or phase group nodes
  const fromReq = nodes.value.find(n => n.id === fromNodeId)
  if (fromReq?.isRequirement || fromReq?.isGuard) return null
  if (fromReq?.type === 'setup_group' || fromReq?.type === 'cleanup_group') return null
  const toReq = nodes.value.find(n => n.id === toNodeId)
  if (toReq?.isRequirement || toReq?.isGuard) return null
  if (toReq?.type === 'setup_group' || toReq?.type === 'cleanup_group') return null

  // Prevent connecting to nodes with non-transition triggers (input port is hidden)
  const targetNode = nodes.value.find(n => n.id === toNodeId)
  if (targetNode && targetNode.trigger && targetNode.trigger.type !== 'transition') return null

  // Encapsulation enforcement: both nodes must share the same parentId
  const fromNode = nodes.value.find(n => n.id === fromNodeId)
  if (fromNode && targetNode) {
    if (fromNode.parentId !== targetNode.parentId) return null
  }

  snapshot()
  const id = `edge_${fromNodeId}_${fromPort}_${toNodeId}`
  const edge = { id, from: fromNodeId, fromPort, to: toNodeId, mapping: null }
  edges.value = [...edges.value, edge]
  notifyMutation('add_edge', { edge: toRaw(edge) })
  return edge
}

export function removeEdge(edgeId) {
  snapshot()
  edges.value = edges.value.filter(e => e.id !== edgeId)
  if (selection.type === 'edge' && selection.id === edgeId) {
    selection.type = null
    selection.id = null
  }
  notifyMutation('remove_edge', { id: edgeId })
}

export function getEdge(edgeId) {
  return edges.value.find(e => e.id === edgeId)
}

export function getEdgesFrom(nodeId) {
  return edges.value.filter(e => e.from === nodeId)
}

export function getEdgesTo(nodeId) {
  return edges.value.filter(e => e.to === nodeId)
}

export function updateEdgeMapping(edgeId, mapping) {
  const edge = edges.value.find(e => e.id === edgeId)
  if (!edge) return
  edge.mapping = mapping && Object.keys(mapping).length > 0 ? { ...mapping } : null
  edges.value = [...edges.value]
  notifyMutation('update_edge_mapping', { id: edgeId, mapping: toRaw(edge.mapping) })
}

// ── Selection ──────────────────────────────────────────────────────────────

export function selectNode(nodeId) {
  selection.type = 'node'
  selection.id = nodeId
  selectedNodeIds.value = [nodeId]
}

export function selectEdge(edgeId) {
  selection.type = 'edge'
  selection.id = edgeId
  selectedNodeIds.value = []
}

export function clearSelection() {
  selection.type = null
  selection.id = null
  selectedNodeIds.value = []
}

/**
 * Select multiple nodes (from marquee or programmatic use).
 * Sets inspector to the single node if exactly one, otherwise 'multi'.
 */
export function selectNodes(nodeIds) {
  selectedNodeIds.value = [...nodeIds]
  if (nodeIds.length === 1) {
    selection.type = 'node'
    selection.id = nodeIds[0]
  } else if (nodeIds.length > 1) {
    selection.type = 'multi'
    selection.id = null
  } else {
    selection.type = null
    selection.id = null
  }
}

/**
 * Toggle a node in/out of multi-selection (for Shift+click).
 */
export function toggleNodeSelection(nodeId) {
  const ids = [...selectedNodeIds.value]
  const idx = ids.indexOf(nodeId)
  if (idx >= 0) {
    ids.splice(idx, 1)
  } else {
    ids.push(nodeId)
  }
  selectNodes(ids)
}

export function isNodeSelected(nodeId) {
  return selectedNodeIds.value.includes(nodeId)
}

/**
 * Remove all currently selected nodes (and their edges).
 */
export function removeSelectedNodes() {
  // Filter out __start__, __stop__, and entry/exit nodes
  const stopIds = new Set(nodes.value.filter(n => n.type === '__stop__').map(n => n.id))
  const ids = selectedNodeIds.value.filter(id => id !== '__start__' && !stopIds.has(id) && !isEntryOrExit(id))
  if (ids.length === 0) return
  snapshot()

  // Collect all descendants of any selected containers
  const allIds = new Set(ids)
  for (const id of ids) {
    for (const desc of getDescendants(id)) {
      allIds.add(desc.id)
    }
  }

  // Close any open tabs for removed containers
  for (const id of allIds) {
    closeContainerTab(id)
  }

  edges.value = edges.value.filter(e => !allIds.has(e.from) && !allIds.has(e.to))
  nodes.value = nodes.value.filter(n => !allIds.has(n.id))
  clearSelection()
  // Emit load_state for bulk removal (simpler than individual remove_node calls)
  notifyMutation('load_state', {
    nodes: toRaw(nodes.value),
    edges: toRaw(edges.value),
    meta: toRaw(meta),
    nodeCounter,
  })
}

// ── Container helpers ──────────────────────────────────────────────────

/**
 * Get all descendant nodes of a container (recursive for nesting).
 */
export function getDescendants(containerId) {
  const result = []
  const children = nodes.value.filter(n => n.parentId === containerId)
  for (const child of children) {
    result.push(child)
    // Recurse into nested containers
    if (child.width != null) {
      result.push(...getDescendants(child.id))
    }
  }
  return result
}

/**
 * Get array of ancestor container IDs (from immediate parent to root).
 */
export function getParentChain(nodeId) {
  const chain = []
  let current = nodes.value.find(n => n.id === nodeId)
  while (current && current.parentId) {
    chain.push(current.parentId)
    current = nodes.value.find(n => n.id === current.parentId)
  }
  return chain
}

/**
 * Move a node into a container. The node keeps its global position.
 */
export function moveNodeToContainer(nodeId, containerId) {
  const node = nodes.value.find(n => n.id === nodeId)
  if (!node) return
  if (node.parentId === containerId) return
  node.parentId = containerId
  notifyMutation('move_node_to_container', { id: nodeId, containerId })
}

/**
 * Remove a node from its container. The node keeps its global position.
 */
export function removeNodeFromContainer(nodeId) {
  const node = nodes.value.find(n => n.id === nodeId)
  if (!node || !node.parentId) return
  node.parentId = null
  notifyMutation('remove_node_from_container', { id: nodeId })
}

/**
 * Check if a node is a container's entry or exit node.
 */
export function isEntryOrExit(nodeId) {
  const node = nodes.value.find(n => n.id === nodeId)
  if (!node) return false
  return node.type === '__entry__' || node.type === '__exit__'
}

/**
 * Get the direct children of a container.
 */
export function getChildren(containerId) {
  return nodes.value.filter(n => n.parentId === containerId)
}

/**
 * Get edges where both endpoints are children of the given container.
 */
export function getChildEdges(containerId) {
  const childIds = new Set(nodes.value.filter(n => n.parentId === containerId).map(n => n.id))
  return edges.value.filter(e => childIds.has(e.from) && childIds.has(e.to))
}

/**
 * Find the deepest container whose bounds contain the given point.
 * Checks innermost first for nested containers.
 */
export function findContainerAtPoint(x, y, excludeIds = []) {
  const containers = nodes.value.filter(n => n.width != null && !excludeIds.includes(n.id))
  // Sort by depth (deepest nesting first)
  containers.sort((a, b) => getParentChain(b.id).length - getParentChain(a.id).length)

  for (const c of containers) {
    const headerH = 32
    if (x >= c.x && x <= c.x + c.width && y >= c.y + headerH && y <= c.y + c.height) {
      return c
    }
  }
  return null
}

// ── Container tabs ────────────────────────────────────────────────────────
export const openTabs = ref([{ id: 'root', label: 'Experiment' }])
export const activeTab = ref('root')

/**
 * The parentId filter for the current view.
 * 'root' → null (top-level), otherwise the container ID.
 */
export const activeParentId = computed(() =>
  activeTab.value === 'root' ? null : activeTab.value
)

export function openContainerTab(containerId) {
  const existing = openTabs.value.find(t => t.id === containerId)
  if (existing) {
    activeTab.value = containerId
    return
  }
  const node = nodes.value.find(n => n.id === containerId)
  openTabs.value = [...openTabs.value, { id: containerId, label: node?.id || containerId }]
  activeTab.value = containerId
}

export function closeContainerTab(containerId) {
  if (containerId === 'root') return
  openTabs.value = openTabs.value.filter(t => t.id !== containerId)
  if (activeTab.value === containerId) {
    activeTab.value = 'root'
  }
}

export function switchTab(tabId) {
  activeTab.value = tabId
}

// ── Wiring ─────────────────────────────────────────────────────────────────

export function startWiring(nodeId, port, x, y) {
  wiring.active = true
  wiring.fromNodeId = nodeId
  wiring.fromPort = port
  wiring.startX = x
  wiring.startY = y
  wiring.currentX = x
  wiring.currentY = y
}

export function updateWiring(x, y) {
  wiring.currentX = x
  wiring.currentY = y
}

export function endWiring() {
  wiring.active = false
  wiring.fromNodeId = null
  wiring.fromPort = null
}

// ── Persistence ────────────────────────────────────────────────────────────

const STORAGE_KEY = 'experiment-designer-state'
const STORAGE_VERSION = 5  // bump when schema changes (5 = meta.events, requirements)

export function saveState() {
  const state = {
    version: STORAGE_VERSION,
    nodes: toRaw(nodes.value),
    edges: toRaw(edges.value),
    meta: toRaw(meta),
    pan: { x: pan.x, y: pan.y },
    zoom: zoom.value,
    nodeCounter,
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch (e) {
    // Storage full
  }
}

export function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return false
    const state = JSON.parse(raw)
    // Reject incompatible versions
    if ((state.version || 1) < STORAGE_VERSION) {
      localStorage.removeItem(STORAGE_KEY)
      return false
    }
    skipSnapshot = true
    nodes.value = state.nodes || []
    edges.value = state.edges || []
    Object.assign(meta, {
      id: state.meta?.id ?? 'experiment_1',
      description: state.meta?.description ?? '',
      timeout: state.meta?.timeout ?? null,
      variables: state.meta?.variables ?? {},
      events: state.meta?.events ?? [],
    })
    pan.x = state.pan?.x ?? 0
    pan.y = state.pan?.y ?? 0
    zoom.value = state.zoom ?? 1
    nodeCounter = state.nodeCounter ?? 0
    skipSnapshot = false
    // Reset tabs on load
    openTabs.value = [{ id: 'root', label: 'Experiment' }]
    activeTab.value = 'root'
    return true
  } catch {
    return false
  }
}

export function initDefaultGraph() {
  skipSnapshot = true
  nodeCounter = 0
  nodes.value = []
  edges.value = []
  const isH = layoutDirection.value === 'horizontal'
  addNode('__start__', isH ? 80 : 300, isH ? 200 : 80)
  addNode('__stop__', isH ? 500 : 300, isH ? 200 : 400)
  meta.id = 'experiment_1'
  meta.description = 'New experiment'
  meta.timeout = null
  meta.variables = {}
  meta.events = []
  skipSnapshot = false
  undoStack.value = []
  redoStack.value = []
  openTabs.value = [{ id: 'root', label: 'Experiment' }]
  activeTab.value = 'root'
}

// ── Full state serialization (for experiment tab switching) ────────────────

export function serializeFullState() {
  return JSON.stringify({
    version: STORAGE_VERSION,
    nodes: toRaw(nodes.value),
    edges: toRaw(edges.value),
    meta: toRaw(meta),
    pan: { x: pan.x, y: pan.y },
    zoom: zoom.value,
    nodeCounter,
    openTabs: toRaw(openTabs.value),
    activeTab: activeTab.value,
  })
}

export function loadFullState(serialized) {
  try {
    const state = JSON.parse(serialized)
    skipSnapshot = true
    nodes.value = state.nodes || []
    edges.value = state.edges || []
    Object.assign(meta, {
      id: state.meta?.id ?? 'experiment_1',
      description: state.meta?.description ?? '',
      timeout: state.meta?.timeout ?? null,
      variables: state.meta?.variables ?? {},
      events: state.meta?.events ?? [],
    })
    pan.x = state.pan?.x ?? 0
    pan.y = state.pan?.y ?? 0
    zoom.value = state.zoom ?? 1
    nodeCounter = state.nodeCounter ?? 0
    openTabs.value = state.openTabs || [{ id: 'root', label: 'Experiment' }]
    activeTab.value = state.activeTab || 'root'
    undoStack.value = []
    redoStack.value = []
    skipSnapshot = false
    notifyMutation('load_state', {
      nodes: toRaw(nodes.value),
      edges: toRaw(edges.value),
      meta: toRaw(meta),
      nodeCounter,
    })
    return true
  } catch {
    return false
  }
}

// ── Auto-layout ───────────────────────────────────────────────────────────
import { computeAutoLayout } from './utils/autoLayout.js'
import { NODE_WIDTH, getNodeHeight, START_WIDTH, START_HEIGHT, STOP_WIDTH, STOP_HEIGHT, ENTRY_WIDTH, ENTRY_HEIGHT, REQUIREMENT_WIDTH, REQUIREMENT_HEIGHT, GUARD_WIDTH, GUARD_HEIGHT, CONTAINER_HEADER_HEIGHT, CONTAINER_MIN_WIDTH, CONTAINER_MIN_HEIGHT } from './utils/geometry.js'

function getNodeWidth(node) {
  if (node.type === '__start__') return START_WIDTH
  if (node.type === '__stop__') return STOP_WIDTH
  if (node.type === '__entry__' || node.type === '__exit__') return ENTRY_WIDTH
  if (node.isRequirement) return REQUIREMENT_WIDTH
  if (node.isGuard) return GUARD_WIDTH
  if (node.width != null) return node.width
  return NODE_WIDTH
}

function getNodeFullHeight(node) {
  if (node.type === '__start__') return START_HEIGHT
  if (node.type === '__stop__') return STOP_HEIGHT
  if (node.type === '__entry__' || node.type === '__exit__') return ENTRY_HEIGHT
  if (node.isRequirement) return REQUIREMENT_HEIGHT
  if (node.isGuard) return GUARD_HEIGHT
  if (node.height != null) return node.height
  return getNodeHeight(node)
}

/**
 * After laying out a container's children, resize the container to fit them.
 */
function resizeContainerToFit(containerId) {
  const container = nodes.value.find(n => n.id === containerId)
  if (!container || container.width == null) return

  const children = nodes.value.filter(n => n.parentId === containerId)
  if (children.length === 0) return

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const child of children) {
    const w = getNodeWidth(child)
    const h = getNodeFullHeight(child)
    minX = Math.min(minX, child.x)
    minY = Math.min(minY, child.y)
    maxX = Math.max(maxX, child.x + w)
    maxY = Math.max(maxY, child.y + h)
  }

  const pad = 24
  const headerH = CONTAINER_HEADER_HEIGHT
  const portsH = 28  // port labels section at the bottom

  const contentW = maxX - minX
  const contentH = maxY - minY
  // Ensure the container is wide enough for the header controls (~240px)
  const newW = Math.max(CONTAINER_MIN_WIDTH, 240, roundGrid(contentW + 2 * pad))
  const newH = Math.max(CONTAINER_MIN_HEIGHT, roundGrid(contentH + headerH + portsH + 2 * pad))

  // Center children horizontally if the container is wider than needed
  const contentCenterX = (minX + maxX) / 2
  const newX = roundGrid(contentCenterX - newW / 2)
  const newY = roundGrid(minY - headerH - pad)

  container.x = newX
  container.y = newY
  container.width = newW
  container.height = newH
}

function roundGrid(v, grid = 20) {
  return Math.round(v / grid) * grid
}

/**
 * Auto-layout nodes within a specific parent scope, without snapshot or reactivity trigger.
 * Used internally by autoLayout() and toggleLayoutDirection().
 */
function layoutNodesInParent(parentId) {
  const childNodes = nodes.value.filter(n =>
    parentId === null ? !n.parentId : n.parentId === parentId
  )
  if (childNodes.length === 0) return

  const childIds = new Set(childNodes.map(n => n.id))
  const childEdges = edges.value.filter(e => childIds.has(e.from) && childIds.has(e.to))

  const opts = {}
  if (columnWrap.value) {
    if (layoutDirection.value === 'horizontal') {
      opts.maxRowWidth = viewport.width - 80
    } else {
      opts.maxColumnHeight = viewport.height - 80
    }
  }
  const positions = computeAutoLayout(childNodes, childEdges, layoutDirection.value, opts)
  if (!positions) return

  for (const [id, pos] of Object.entries(positions)) {
    const node = nodes.value.find(n => n.id === id)
    if (node) {
      const dx = pos.x - node.x
      const dy = pos.y - node.y
      node.x = pos.x
      node.y = pos.y
      // If container, move descendants too
      if (node.width != null) {
        for (const child of getDescendants(id)) {
          child.x += dx
          child.y += dy
        }
      }
    }
  }
}

/**
 * Recursively auto-layout all containers (bottom-up) and then the root/current view.
 * Resizes containers to fit their children after each level.
 */
function autoLayoutRecursive() {
  const containers = nodes.value.filter(n => n.width != null)
  // Sort deepest-first so inner containers are laid out before their parents
  containers.sort((a, b) => getParentChain(b.id).length - getParentChain(a.id).length)
  for (const c of containers) {
    layoutNodesInParent(c.id)
    resizeContainerToFit(c.id)
  }
  // Layout root level (now with correctly-sized containers)
  layoutNodesInParent(activeParentId.value)
}

export function autoLayout() {
  snapshot()
  autoLayoutRecursive()
  nodes.value = [...nodes.value]
  zoomToFit()
}

/**
 * Full recursive auto-layout, intended for use after YAML import.
 */
export function autoLayoutAll() {
  autoLayoutRecursive()
  nodes.value = [...nodes.value]
  zoomToFit()
}

export function zoomToFit() {
  const parentId = activeParentId.value
  const visibleNodes = nodes.value.filter(n =>
    parentId === null ? !n.parentId : n.parentId === parentId
  )
  if (visibleNodes.length === 0) return

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const n of visibleNodes) {
    const w = getNodeWidth(n)
    const h = getNodeFullHeight(n)
    minX = Math.min(minX, n.x)
    minY = Math.min(minY, n.y)
    maxX = Math.max(maxX, n.x + w)
    maxY = Math.max(maxY, n.y + h)
  }

  const contentW = maxX - minX
  const contentH = maxY - minY
  if (contentW <= 0 || contentH <= 0) return

  const padding = 60
  const vw = viewport.width
  const vh = viewport.height
  const newZoom = Math.min(
    (vw - padding * 2) / contentW,
    (vh - padding * 2) / contentH,
    4.0
  )
  const clampedZoom = Math.max(0.25, Math.min(4.0, newZoom))

  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  pan.x = vw / 2 - cx * clampedZoom
  pan.y = vh / 2 - cy * clampedZoom
  zoom.value = clampedZoom
}

export function centerOnNode(nodeId) {
  const node = nodes.value.find(n => n.id === nodeId)
  if (!node) return
  const w = getNodeWidth(node)
  const h = getNodeFullHeight(node)
  const cx = node.x + w / 2
  const cy = node.y + h / 2
  pan.x = viewport.width / 2 - cx * zoom.value
  pan.y = viewport.height / 2 - cy * zoom.value
}

// ── Remote mutation ops (used by mutationBridge.applyRemoteMutation) ──────
// These apply changes without calling snapshot() or notifyMutation().

/**
 * Add a node directly from a remote mutation (no snapshot, no notify).
 */
export function addNodeDirect(nodeDict) {
  if (!nodeDict || nodes.value.find(n => n.id === nodeDict.id)) return
  // Recompute display fields that the remote side may not have
  if (nodeDict.type && nodeDict.params && !nodeDict.isRequirement && !nodeDict.isGuard
      && nodeDict.type !== '__start__' && nodeDict.type !== '__stop__'
      && nodeDict.type !== '__entry__' && nodeDict.type !== '__exit__') {
    nodeDict._summaryText = getSummary({ type: nodeDict.type, params: nodeDict.params })
    nodeDict._paramLineCount = nodeDict._summaryText ? 0 : getParamLines({ type: nodeDict.type, params: nodeDict.params }).length
    if (!nodeDict._outPorts) {
      nodeDict._outPorts = getTransitionPorts(nodeDict.type)
    }
  }
  if ((nodeDict.isRequirement || nodeDict.isGuard) && nodeDict.params) {
    nodeDict._summaryText = getSummary({ type: nodeDict.type, params: nodeDict.params })
    nodeDict._paramLineCount = nodeDict._summaryText ? 0 : getParamLines({ type: nodeDict.type, params: nodeDict.params }).length
  }
  nodes.value = [...nodes.value, nodeDict]
  // Track node counter
  const parts = nodeDict.id.split('_')
  const num = parseInt(parts[parts.length - 1])
  if (!isNaN(num) && num > nodeCounter) nodeCounter = num
}

/**
 * Remove a node directly from a remote mutation (no snapshot, no notify).
 */
export function removeNodeDirect(nodeId) {
  if (nodeId === '__start__') return
  const targetNode = nodes.value.find(n => n.id === nodeId)
  if (targetNode && targetNode.type === '__stop__') return
  if (isEntryOrExit(nodeId)) return
  const descendants = getDescendants(nodeId)
  const allIds = new Set([nodeId, ...descendants.map(n => n.id)])
  for (const id of allIds) closeContainerTab(id)
  edges.value = edges.value.filter(e => !allIds.has(e.from) && !allIds.has(e.to))
  nodes.value = nodes.value.filter(n => !allIds.has(n.id))
  if (selection.type === 'node' && allIds.has(selection.id)) {
    selection.type = null
    selection.id = null
  }
  selectedNodeIds.value = selectedNodeIds.value.filter(id => !allIds.has(id))
}

/**
 * Rename a node (move onIdChange logic from InspectorPanel into graphState).
 */
export function renameNode(oldId, newId) {
  const node = nodes.value.find(n => n.id === oldId)
  if (!node) return
  node.id = newId
  for (const edge of edges.value) {
    if (edge.from === oldId) edge.from = newId
    if (edge.to === oldId) edge.to = newId
    edge.id = `edge_${edge.from}_${edge.fromPort}_${edge.to}`
  }
  // Update parentId references
  for (const n of nodes.value) {
    if (n.parentId === oldId) n.parentId = newId
  }
  if (selection.type === 'node' && selection.id === oldId) {
    selection.id = newId
  }
  nodes.value = [...nodes.value]
  edges.value = [...edges.value]
  notifyMutation('rename_node', { oldId, newId })
}

/**
 * Add an edge directly from a remote mutation (no validation, no snapshot, no notify).
 */
export function addEdgeDirect(edgeDict) {
  if (!edgeDict || edges.value.find(e => e.id === edgeDict.id)) return
  edges.value = [...edges.value, edgeDict]
}

/**
 * Remove an edge directly from a remote mutation (no snapshot, no notify).
 */
export function removeEdgeDirect(edgeId) {
  edges.value = edges.value.filter(e => e.id !== edgeId)
  if (selection.type === 'edge' && selection.id === edgeId) {
    selection.type = null
    selection.id = null
  }
}

/**
 * Update a meta field directly.
 */
export function updateMeta(field, value) {
  meta[field] = value
}

/**
 * Add/update/remove variables and events.
 */
export function addVariable(name, value) {
  if (!meta.variables) meta.variables = {}
  meta.variables[name] = value
}

export function removeVariable(name) {
  if (meta.variables) delete meta.variables[name]
}

export function updateVariable(name, value) {
  if (!meta.variables) meta.variables = {}
  meta.variables[name] = value
}

export function addEvent(name) {
  if (!meta.events) meta.events = []
  if (!meta.events.includes(name)) meta.events.push(name)
}

export function removeEvent(name) {
  if (meta.events) {
    const idx = meta.events.indexOf(name)
    if (idx >= 0) meta.events.splice(idx, 1)
  }
}

/**
 * Load full state from a remote mutation (no snapshot, no notify).
 */
export function loadStateFromMutation(data) {
  skipSnapshot = true
  nodes.value = data.nodes || []
  edges.value = data.edges || []
  if (data.meta) {
    Object.assign(meta, {
      id: data.meta.id ?? 'experiment_1',
      description: data.meta.description ?? '',
      timeout: data.meta.timeout ?? null,
      variables: data.meta.variables ?? {},
      events: data.meta.events ?? [],
    })
  }
  if (data.nodeCounter !== undefined) nodeCounter = data.nodeCounter
  skipSnapshot = false
}

// Auto-save disabled — tab system manages state per-tab, use file save instead.
// Preferences (theme, layout direction, etc.) are saved individually via their own localStorage keys.
