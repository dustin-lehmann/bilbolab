<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { nodes, meta, getAllEventNames } from '../graphState.js'
import { getAllActions, INTERNAL_ACTIONS, getDataDefs, isRequirementType, isGuardType } from '../actionRegistry.js'

const props = defineProps({
  visible: Boolean,
  anchorRect: Object,   // { left, top, width, height }
  paramContext: Object,  // { paramName, nodeType, nodeId } for context-aware filtering
})

const emit = defineEmits(['select', 'close'])

const filterText = ref('')
const activeIndex = ref(0)
const filterInput = ref(null)
const popupEl = ref(null)

// ── Build suggestions from graph state ──────────────────────────────────

const suggestions = computed(() => {
  const sections = []
  const ctx = props.paramContext || {}

  // Determine pre-filter based on context
  const preFilter = getPreFilter(ctx)

  // Variables
  if (!preFilter || preFilter === 'variables') {
    const vars = Object.keys(meta.variables)
    if (vars.length > 0) {
      sections.push({
        label: 'Variables',
        items: vars.map(name => ({ text: `\${${name}}`, display: name, hint: 'variable' })),
      })
    }
  }

  // Action IDs (non-special, non-requirement nodes)
  if (!preFilter || preFilter === 'actions') {
    const actionNodes = nodes.value.filter(n =>
      n.type !== '__start__' && n.type !== '__stop__' &&
      n.type !== '__entry__' && n.type !== '__exit__' &&
      !isRequirementType(n.type) && !isGuardType(n.type) &&
      n.id !== ctx.nodeId
    )
    if (actionNodes.length > 0) {
      sections.push({
        label: 'Action IDs',
        items: actionNodes.map(n => ({ text: n.id, display: n.id, hint: n.type })),
      })
    }
  }

  // Action Outputs (nodes x their data defs)
  if (!preFilter || preFilter === 'outputs') {
    const outputItems = []
    for (const n of nodes.value) {
      if (n.type === '__start__' || n.type === '__stop__' ||
          n.type === '__entry__' || n.type === '__exit__' ||
          isRequirementType(n.type) || isGuardType(n.type)) continue
      const defs = getDataDefs(n.type)
      for (const key of Object.keys(defs)) {
        outputItems.push({
          text: `\${${n.id}.${key}}`,
          display: `${n.id}.${key}`,
          hint: defs[key].type || 'any',
        })
      }
    }
    if (outputItems.length > 0) {
      sections.push({ label: 'Action Outputs', items: outputItems })
    }
  }

  // Events
  if (!preFilter || preFilter === 'events') {
    const events = Object.entries(getAllEventNames())
    if (events.length > 0) {
      sections.push({
        label: 'Events',
        items: events.map(([name, source]) => ({ text: name, display: name, hint: source })),
      })
    }
  }

  // Target action's params (for set_parameter.param_name context)
  if (preFilter === 'target_params') {
    const targetItems = resolveTargetParams(ctx)
    if (targetItems.length > 0) {
      sections.push({ label: 'Target Params', items: targetItems })
    }
  }

  return sections
})

function getPreFilter(ctx) {
  if (!ctx.paramName) return null
  if (ctx.paramName === 'action_id') return 'actions'
  if (ctx.paramName === 'event') return 'events'
  if (ctx.paramName === 'name' && ctx.nodeType === 'set_variable') return 'variables'
  if (ctx.paramName === 'param_name' && ctx.nodeType === 'set_parameter') return 'target_params'
  return null
}

function resolveTargetParams(ctx) {
  // Find the sibling action_id value from the current node
  const node = nodes.value.find(n => n.id === ctx.nodeId)
  if (!node || !node.params?.action_id) return []
  const targetId = node.params.action_id
  const targetNode = nodes.value.find(n => n.id === targetId)
  if (!targetNode) return []
  const allActions = getAllActions()
  const def = allActions[targetNode.type] || INTERNAL_ACTIONS[targetNode.type]
  if (!def?.params) return []
  return Object.entries(def.params).map(([key, pDef]) => ({
    text: key,
    display: key,
    hint: pDef.type || 'str',
  }))
}

// ── Filtered flat list ──────────────────────────────────────────────────

const filteredSections = computed(() => {
  const q = filterText.value.toLowerCase()
  if (!q) return suggestions.value
  return suggestions.value
    .map(section => ({
      ...section,
      items: section.items.filter(item =>
        item.display.toLowerCase().includes(q) || item.hint.toLowerCase().includes(q)
      ),
    }))
    .filter(section => section.items.length > 0)
})

const flatItems = computed(() => filteredSections.value.flatMap(s => s.items))

// Reset index on filter change
watch(filterText, () => { activeIndex.value = 0 })

// ── Keyboard navigation ─────────────────────────────────────────────────

function onKeydown(e) {
  const count = flatItems.value.length
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value + 1) % Math.max(count, 1)
    scrollActiveIntoView()
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value - 1 + Math.max(count, 1)) % Math.max(count, 1)
    scrollActiveIntoView()
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (flatItems.value[activeIndex.value]) {
      selectItem(flatItems.value[activeIndex.value])
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  }
}

function scrollActiveIntoView() {
  nextTick(() => {
    const el = popupEl.value?.querySelector('.ref-item.active')
    if (el) el.scrollIntoView({ block: 'nearest' })
  })
}

function selectItem(item) {
  emit('select', item.text)
  emit('close')
}

// ── Positioning ─────────────────────────────────────────────────────────

const popupStyle = computed(() => {
  if (!props.anchorRect) return {}
  const anchor = props.anchorRect
  const popupH = 300
  // Try to position below; if not enough room, position above
  const spaceBelow = window.innerHeight - (anchor.top + anchor.height + 4)
  const placeAbove = spaceBelow < popupH && anchor.top > popupH
  return {
    position: 'fixed',
    left: anchor.left + 'px',
    width: Math.max(anchor.width, 220) + 'px',
    maxHeight: popupH + 'px',
    ...(placeAbove
      ? { bottom: (window.innerHeight - anchor.top + 4) + 'px' }
      : { top: (anchor.top + anchor.height + 4) + 'px' }
    ),
  }
})

// ── Focus management ────────────────────────────────────────────────────

watch(() => props.visible, (v) => {
  if (v) {
    filterText.value = ''
    activeIndex.value = 0
    nextTick(() => filterInput.value?.focus())
  }
})

// Close on outside click
function onOutsideClick(e) {
  if (props.visible && popupEl.value && !popupEl.value.contains(e.target)) {
    emit('close')
  }
}

onMounted(() => document.addEventListener('mousedown', onOutsideClick, true))
onUnmounted(() => document.removeEventListener('mousedown', onOutsideClick, true))

// ── Flat index tracking ─────────────────────────────────────────────────

function getFlatIndex(sectionIdx, itemIdx) {
  let idx = 0
  for (let s = 0; s < sectionIdx; s++) {
    idx += filteredSections.value[s].items.length
  }
  return idx + itemIdx
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" ref="popupEl" class="ref-picker" :style="popupStyle" @keydown="onKeydown">
      <input
        ref="filterInput"
        v-model="filterText"
        class="ref-filter"
        placeholder="Filter..."
        spellcheck="false"
      />
      <div class="ref-list">
        <template v-for="(section, si) in filteredSections" :key="section.label">
          <div class="ref-section-header">{{ section.label }}</div>
          <div
            v-for="(item, ii) in section.items"
            :key="item.text"
            class="ref-item"
            :class="{ active: getFlatIndex(si, ii) === activeIndex }"
            @mouseenter="activeIndex = getFlatIndex(si, ii)"
            @mousedown.prevent="selectItem(item)"
          >
            <span class="ref-item-display">{{ item.display }}</span>
            <span class="ref-item-hint">{{ item.hint }}</span>
          </div>
        </template>
        <div v-if="flatItems.length === 0" class="ref-empty">No matches</div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ref-picker {
  z-index: 9999;
  background: var(--bg-surface, #1e1e2e);
  border: 1px solid var(--border, #333);
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ref-filter {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  padding: 6px 8px;
  background: var(--bg, #161622);
  color: var(--text, #ccc);
  border: none;
  border-bottom: 1px solid var(--border, #333);
  outline: none;
}
.ref-filter::placeholder { color: var(--text-dim, #666); }

.ref-list {
  overflow-y: auto;
  max-height: 260px;
  padding: 2px 0;
}

.ref-section-header {
  font-size: 9px;
  font-weight: 600;
  color: var(--text-dim, #888);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 6px 8px 2px;
}

.ref-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 11px;
  gap: 8px;
}
.ref-item:hover,
.ref-item.active {
  background: var(--bg-hover, #2a2a3e);
}

.ref-item-display {
  font-family: 'JetBrains Mono', monospace;
  color: var(--text, #ddd);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ref-item-hint {
  font-size: 9px;
  color: var(--text-dim, #666);
  flex-shrink: 0;
}

.ref-empty {
  font-size: 10px;
  color: var(--text-dim, #666);
  padding: 12px 8px;
  text-align: center;
}
</style>
