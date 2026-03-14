<script setup>
import { computed } from 'vue'
import { selection, selectEdge, getNode } from '../graphState.js'
import { getOutputPortPos, getInputPortPos, computeBezierPath, getEdgeControlPoints } from '../utils/geometry.js'

const props = defineProps({
  edge: { type: Object, required: true },
})

const PORT_COLORS = {
  done: '#45aaf2',
  error: '#e74c3c',
  timeout: '#f39c12',
  then: '#2ecc71',
  else: '#e67e22',
}

const isSelected = computed(() => selection.type === 'edge' && selection.id === props.edge.id)
const color = computed(() => PORT_COLORS[props.edge.fromPort] || '#45aaf2')

const hasMapping = computed(() => props.edge.mapping && Object.keys(props.edge.mapping).length > 0)
const mappingCount = computed(() => hasMapping.value ? Object.keys(props.edge.mapping).length : 0)

const MAX_DISPLAY_MAPPINGS = 4
const MAX_VALUE_LEN = 20

const mappingLines = computed(() => {
  if (!hasMapping.value) return []
  const entries = Object.entries(props.edge.mapping)
  const lines = []
  const limit = Math.min(entries.length, MAX_DISPLAY_MAPPINGS)
  for (let i = 0; i < limit; i++) {
    const [param, val] = entries[i]
    const display = String(val).length > MAX_VALUE_LEN
      ? String(val).slice(0, MAX_VALUE_LEN) + '\u2026'
      : String(val)
    lines.push(`${param} \u2190 ${display || '?'}`)
  }
  if (entries.length > MAX_DISPLAY_MAPPINGS) {
    lines.push(`+${entries.length - MAX_DISPLAY_MAPPINGS} more`)
  }
  return lines
})

const labelBoxWidth = computed(() => {
  if (!mappingLines.value.length) return 0
  const maxLen = Math.max(...mappingLines.value.map(l => l.length))
  return Math.min(maxLen * 6.2 + 12, 180)
})

const labelBoxHeight = computed(() => {
  if (!mappingLines.value.length) return 0
  return mappingLines.value.length * 13 + 8
})

const startEnd = computed(() => {
  const fromNode = getNode(props.edge.from)
  const toNode = getNode(props.edge.to)
  if (!fromNode || !toNode) return null

  const start = getOutputPortPos(fromNode, props.edge.fromPort)
  const end = getInputPortPos(toNode)
  if (!start || !end) return null

  return { start, end }
})

const path = computed(() => {
  if (!startEnd.value) return ''
  const { start, end } = startEnd.value
  return computeBezierPath(start.x, start.y, end.x, end.y)
})

const midpoint = computed(() => {
  if (!startEnd.value) return null
  const { start, end } = startEnd.value
  const pts = getEdgeControlPoints(start.x, start.y, end.x, end.y)

  if (!pts.isMultiSegment) {
    const t = 0.5, mt = 0.5
    const x = mt*mt*mt*start.x + 3*mt*mt*t*pts.cp1x + 3*mt*t*t*pts.cp2x + t*t*t*end.x
    const y = mt*mt*mt*start.y + 3*mt*mt*t*pts.cp1y + 3*mt*t*t*pts.cp2y + t*t*t*end.y
    return { x, y }
  }

  // Multi-segment: use the precomputed midpoint
  return pts.mid
})

function onClick(e) {
  e.stopPropagation()
  selectEdge(props.edge.id)
}
</script>

<template>
  <g class="connection-line" @click="onClick">
    <!-- Invisible fat line for easier click targeting -->
    <path
      :d="path"
      fill="none"
      stroke="transparent"
      stroke-width="12"
      style="cursor: pointer;"
    />
    <!-- Visible line -->
    <path
      :d="path"
      fill="none"
      :stroke="isSelected ? '#fff' : color"
      :stroke-width="isSelected ? 2.5 : 2"
      :stroke-dasharray="isSelected ? 'none' : 'none'"
      stroke-linecap="round"
      :opacity="isSelected ? 1 : 0.7"
      style="pointer-events: none; transition: stroke 0.15s, stroke-width 0.15s;"
    />
    <!-- Mapping labels -->
    <g v-if="hasMapping && midpoint" :transform="`translate(${midpoint.x + 8}, ${midpoint.y - labelBoxHeight / 2})`" style="pointer-events: none;">
      <rect
        x="-4" y="-2"
        :width="labelBoxWidth + 4"
        :height="labelBoxHeight + 2"
        rx="4"
        fill="#1a1a2e"
        :opacity="isSelected ? 0.95 : 0.85"
        stroke="none"
      />
      <text
        v-for="(line, i) in mappingLines"
        :key="i"
        x="2" :y="11 + i * 13"
        :fill="isSelected ? '#fff' : (i === mappingLines.length - 1 && mappingCount > MAX_DISPLAY_MAPPINGS ? '#888' : color)"
        font-size="9"
        font-family="'JetBrains Mono', monospace"
      >{{ line }}</text>
    </g>
  </g>
</template>
