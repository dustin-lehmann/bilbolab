<script setup>
import { computed } from 'vue'
import { getAllActions, INTERNAL_ACTIONS, getAllCategories, getAllRequirements, getAllGuards, getSummary, getParamLines, hasMissingRequired, getTransitionPorts } from '../actionRegistry.js'
import { selection, selectNode, toggleNodeSelection, isNodeSelected, startWiring, wiring, pan, zoom, edges, mode, actionStates, layoutDirection, inspectorCollapsed } from '../graphState.js'
import { NODE_WIDTH, REQUIREMENT_WIDTH, GUARD_WIDTH, getNodeHeight, getOutputPortPos, getInputPortPos, getPortVisualCenter } from '../utils/geometry.js'

const props = defineProps({
  node: { type: Object, required: true },
})

const emit = defineEmits(['startDrag'])

const isReq = computed(() => !!props.node.isRequirement)
const isGuard = computed(() => !!props.node.isGuard)
const def = computed(() => getAllActions()[props.node.type] || INTERNAL_ACTIONS[props.node.type] || getAllRequirements()[props.node.type] || getAllGuards()[props.node.type])
const category = computed(() => getAllCategories()[def.value?.category] || { label: '?', color: '#666' })
const summaryText = computed(() => {
  // Use custom summary for builtins that have one, otherwise empty (param lines take over)
  if (def.value && typeof def.value.summary === 'function') {
    try { return def.value.summary(props.node) } catch { return '' }
  }
  return ''
})
const paramLines = computed(() => getParamLines(props.node))
const hasWarning = computed(() => hasMissingRequired(props.node))
const isSelected = computed(() => isNodeSelected(props.node.id))
const outPorts = computed(() => props.node._outPorts || getTransitionPorts(props.node.type))
const hasInputPort = computed(() => !props.node.trigger || props.node.trigger.type === 'transition')

const triggerLabel = computed(() => {
  const t = props.node.trigger
  if (!t || t.type === 'transition') return null
  if (t.type === 'immediate') return 'immediate'
  if (t.type === 'tick') return `tick ${t.tick ?? 0}`
  if (t.type === 'time') return `@${t.time ?? 0}s`
  if (t.type === 'event') return `on: ${t.event || '?'}`
  if (t.type === 'periodic') return `every ${t.period ?? 1}${t.period_unit === 'ticks' ? 't' : 's'}`
  return t.type
})

const isPlayback = computed(() => mode.value === 'playback')
const actionState = computed(() => actionStates.value[props.node.id] || 'normal')

const inputConnected = computed(() => edges.value.some(e => e.to === props.node.id))
const connectedOutPorts = computed(() => {
  const set = new Set()
  for (const e of edges.value) {
    if (e.from === props.node.id) set.add(e.fromPort)
  }
  return set
})

const isHorizontal = computed(() => layoutDirection.value === 'horizontal')
const nodeHeight = computed(() => getNodeHeight(props.node))

const PORT_COLORS = {
  done: '#45aaf2',
  error: '#e74c3c',
  timeout: '#f39c12',
  then: '#2ecc71',
  else: '#e67e22',
}

function onMouseDown(e) {
  if (e.button !== 0) return
  if (e.target.classList.contains('port')) return
  if (e.shiftKey) {
    toggleNodeSelection(props.node.id)
  } else if (!isNodeSelected(props.node.id)) {
    selectNode(props.node.id)
  }
  if (!isPlayback.value) {
    emit('startDrag', { nodeId: props.node.id, offsetX: e.offsetX, offsetY: e.offsetY, event: e })
  }
}

function onDblClick(e) {
  if (inspectorCollapsed.value) {
    selectNode(props.node.id)
    inspectorCollapsed.value = false
  }
}

function onOutPortMouseDown(e, portName) {
  if (isPlayback.value) return
  e.stopPropagation()
  e.preventDefault()
  const pos = getPortVisualCenter(e.currentTarget, pan.x, pan.y, zoom.value)
  if (pos) {
    startWiring(props.node.id, portName, pos.x, pos.y)
  }
}

function onInPortMouseDown(e) {
  if (isPlayback.value) return
  e.stopPropagation()
  e.preventDefault()
  const pos = getPortVisualCenter(e.currentTarget, pan.x, pan.y, zoom.value)
  if (pos) {
    startWiring(props.node.id, '__input__', pos.x, pos.y)
  }
}
</script>

<template>
  <!-- ═══ Requirement node (simplified) ═══ -->
  <div
    v-if="isReq"
    class="action-node requirement-node"
    :class="{
      selected: isSelected,
      'state-dimmed': actionState === 'dimmed',
    }"
    :style="{
      left: node.x + 'px',
      top: node.y + 'px',
      width: REQUIREMENT_WIDTH + 'px',
    }"
    @mousedown="onMouseDown"
    @dblclick="onDblClick"
  >
    <div class="node-content">
      <div class="req-header">
        <span class="req-icon">!</span>
        <span class="req-type">{{ node.type.replace('require_', '') }}</span>
      </div>
      <div v-if="summaryText" class="req-summary">{{ summaryText }}</div>
      <div v-else-if="paramLines.length > 0" class="req-summary">
        {{ paramLines.map(p => p.display).join(', ') }}
      </div>
    </div>
  </div>

  <!-- ═══ Guard node (simplified) ═══ -->
  <div
    v-else-if="isGuard"
    class="action-node guard-node"
    :class="{
      selected: isSelected,
      'state-dimmed': actionState === 'dimmed',
    }"
    :style="{
      left: node.x + 'px',
      top: node.y + 'px',
      width: GUARD_WIDTH + 'px',
    }"
    @mousedown="onMouseDown"
    @dblclick="onDblClick"
  >
    <div class="node-content">
      <div class="guard-header">
        <span class="guard-icon">&#x1F512;</span>
        <span class="guard-type">{{ node.type }}</span>
      </div>
      <div v-if="summaryText" class="guard-summary">{{ summaryText }}</div>
      <div v-else-if="paramLines.length > 0" class="guard-summary">
        {{ paramLines.map(p => p.display).join(', ') }}
      </div>
    </div>
  </div>

  <!-- ═══ Regular action node ═══ -->
  <div
    v-else
    class="action-node"
    :class="{
      selected: isSelected,
      warning: hasWarning,
      'state-active': actionState === 'active',
      'state-highlighted': actionState === 'highlighted',
      'state-dimmed': actionState === 'dimmed',
      'state-completed': actionState === 'completed',
      'state-error': actionState === 'error',
    }"
    :style="{
      left: node.x + 'px',
      top: node.y + 'px',
      width: NODE_WIDTH + 'px',
    }"
    @mousedown="onMouseDown"
    @dblclick="onDblClick"
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

    <!-- Inner content wrapper (clips wait bars at rounded corners) -->
    <div class="node-content">
      <!-- Header -->
      <div class="node-header" :style="{ background: category.color + '22', borderColor: category.color }">
        <span class="node-type" :style="{ color: category.color }">{{ node.type }}</span>
        <span class="node-id-label">{{ node.id }}</span>
      </div>

      <!-- Trigger badge (non-transition triggers) -->
      <div v-if="triggerLabel" class="trigger-bar">{{ triggerLabel }}</div>

      <!-- Message before bar -->
      <div v-if="node.message_before" class="message-bar">{{ node.message_before }}</div>

      <!-- Wait before bar -->
      <div v-if="node.wait_before" class="wait-bar">{{ node.wait_before }}s before</div>

      <!-- Summary (custom builtin summary) -->
      <div v-if="summaryText" class="node-summary">{{ summaryText }}</div>

      <!-- Param lines (auto-generated for actions without custom summary) -->
      <div v-if="!summaryText && paramLines.length > 0" class="node-params">
        <div v-for="p in paramLines" :key="p.key" class="param-line">
          <span class="param-key">{{ p.key }}</span>
          <span class="param-val">{{ p.display }}</span>
        </div>
      </div>

      <!-- Wait after bar -->
      <div v-if="node.wait_after" class="wait-bar">{{ node.wait_after }}s after</div>

      <!-- Message after bar -->
      <div v-if="node.message_after" class="message-bar">{{ node.message_after }}</div>

      <!-- Output port labels (inside node body) — vertical: bottom row, horizontal: right column -->
      <div v-if="outPorts.length > 0" class="node-ports-labels" :style="isHorizontal ? { position: 'absolute', right: '2px', top: '28px', bottom: '4px', width: 'auto', height: 'auto', padding: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-around', alignItems: 'flex-end' } : {}">
        <span
          v-for="(port, idx) in outPorts"
          :key="port"
          class="port-label-bottom"
          :style="isHorizontal
            ? { position: 'static', transform: 'none', color: PORT_COLORS[port] || 'var(--text-dim)', fontSize: '9px', whiteSpace: 'nowrap' }
            : { left: ((idx + 1) / (outPorts.length + 1) * 100) + '%', color: PORT_COLORS[port] || 'var(--text-dim)' }"
        >{{ port }}</span>
      </div>

      <!-- No-output indicator for stop-like actions (vertical only) -->
      <div v-else-if="!isHorizontal" class="node-ports-empty">
        <span class="no-port-label">end</span>
      </div>
    </div>

    <!-- Output port dots — vertical: bottom edge, horizontal: right edge distributed by y -->
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
  </div>
</template>

<style scoped>
.action-node {
  position: absolute;
  border-radius: 6px;
  background: var(--bg-surface);
  border: 1.5px solid rgba(255,255,255,0.08);
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  cursor: grab;
  user-select: none;
  transition: border-color 0.15s, box-shadow 0.15s, opacity 0.3s, filter 0.3s;
  opacity: 1;
  filter: none;
  overflow: visible;
}

.action-node:hover { border-color: rgba(255,255,255,0.15); }

.action-node.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent), 0 2px 8px rgba(0,0,0,0.3);
}

.action-node.warning { border-color: #f7b731; }

/* Inner content wrapper — clips wait bars at corners */
.node-content {
  border-radius: 5px;
  overflow: hidden;
}

/* Header */
.node-header {
  padding: 4px 8px;
  border-bottom: 1px solid var(--border);
  border-left: 3px solid;
  display: flex;
  align-items: center;
  gap: 6px;
  height: 28px;
}

.node-type {
  font-size: 11px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.node-id-label {
  font-size: 9px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

/* Summary */
.node-summary {
  padding: 4px 8px 2px;
  font-size: 10px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  height: 20px;
}

/* Param lines */
.node-params {
  padding: 3px 8px 1px;
}

.param-line {
  display: flex;
  gap: 4px;
  font-size: 10px;
  line-height: 15px;
  overflow: hidden;
  white-space: nowrap;
}

.param-key {
  color: var(--text-dim);
  flex-shrink: 0;
}
.param-key::after { content: ':'; }

.param-val {
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Trigger badge */
.trigger-bar {
  height: 18px;
  display: flex;
  align-items: center;
  padding: 0 8px;
  font-size: 9px;
  font-weight: 600;
  color: #a55eea;
  background: #a55eea18;
  border-left: 2px solid #a55eea;
}

/* Wait bar */
.wait-bar {
  height: 18px;
  display: flex;
  align-items: center;
  padding: 0 8px;
  font-size: 9px;
  color: #f7b731;
  background: #f7b73118;
  border-left: 2px solid #f7b731;
}

/* Message bar */
.message-bar {
  height: 18px;
  display: flex;
  align-items: center;
  padding: 0 8px;
  font-size: 9px;
  color: #a0c8ff;
  background: #a0c8ff14;
  border-left: 2px solid #a0c8ff80;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Port labels section */
.node-ports-labels {
  position: relative;
  height: 20px;
  padding: 0 4px 4px;
}

.port-label-bottom {
  position: absolute;
  bottom: 4px;
  transform: translateX(-50%);
  font-size: 9px;
  white-space: nowrap;
}

.node-ports-empty {
  display: flex;
  justify-content: center;
  padding: 2px 4px 4px;
}

.no-port-label {
  font-size: 9px;
  color: var(--text-dim);
  opacity: 0.5;
  font-style: italic;
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

/* ── Requirement node ── */
.requirement-node {
  border: 1.5px dashed #e056a0;
  background: var(--bg-surface);
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}
.requirement-node:hover {
  border-color: #e77db8;
}
.requirement-node.selected {
  border-color: #e056a0;
  box-shadow: 0 0 0 2px #e056a0, 0 1px 4px rgba(0,0,0,0.2);
}

.req-header {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  background: #e056a018;
  border-bottom: 1px solid var(--border);
  height: 26px;
}

.req-icon {
  color: #e056a0;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.req-type {
  font-size: 10px;
  font-weight: 600;
  color: #e056a0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.req-summary {
  padding: 3px 8px;
  font-size: 9px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Guard node ── */
.guard-node {
  border: 1.5px dashed #3dc1d3;
  background: var(--bg-surface);
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}
.guard-node:hover {
  border-color: #6dd5e5;
}
.guard-node.selected {
  border-color: #3dc1d3;
  box-shadow: 0 0 0 2px #3dc1d3, 0 1px 4px rgba(0,0,0,0.2);
}

.guard-header {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  background: #3dc1d318;
  border-bottom: 1px solid var(--border);
  height: 26px;
}

.guard-icon {
  font-size: 11px;
  flex-shrink: 0;
}

.guard-type {
  font-size: 10px;
  font-weight: 600;
  color: #3dc1d3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.guard-summary {
  padding: 3px 8px;
  font-size: 9px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Playback action states ── */
.action-node.state-active {
  border-color: #2ecc71;
  box-shadow: 0 0 8px rgba(46, 204, 113, 0.5), 0 0 16px rgba(46, 204, 113, 0.2);
}

.action-node.state-highlighted {
  border-color: #f1c40f;
  box-shadow: 0 0 8px rgba(241, 196, 15, 0.5), 0 0 16px rgba(241, 196, 15, 0.2);
}

.action-node.state-dimmed {
  opacity: 0.3;
  filter: grayscale(0.7);
}

.action-node.state-completed {
  border-color: #2ecc71;
  opacity: 0.75;
  box-shadow: 0 0 4px rgba(46, 204, 113, 0.15);
}

.action-node.state-error {
  border-color: #e74c3c;
  box-shadow: 0 0 8px rgba(231, 76, 60, 0.5), 0 0 16px rgba(231, 76, 60, 0.2);
}
</style>
