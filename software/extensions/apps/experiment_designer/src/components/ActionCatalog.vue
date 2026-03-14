<script setup>
import { ref, computed, watch } from 'vue'
import { getActionsByCategory, getAllCategories, CATEGORIES, robotCategories, robotLabel, REQUIREMENTS, robotRequirements, isRequirementType, GUARDS, robotGuards, isGuardType } from '../actionRegistry.js'
import { meta, nodes, snapshot, getAllEventNames } from '../graphState.js'

const search = ref('')
const allCategories = computed(() => getAllCategories())
const expandedCategories = ref(new Set(Object.keys(allCategories.value)))

// Auto-expand new categories when robot actions are loaded
watch(allCategories, (cats) => {
  for (const key of Object.keys(cats)) {
    expandedCategories.value.add(key)
  }
})

const grouped = computed(() => {
  const all = getActionsByCategory()
  const q = search.value.toLowerCase()
  if (!q) return all

  const filtered = {}
  for (const [cat, actions] of Object.entries(all)) {
    const matches = actions.filter(a =>
      a.type.includes(q) || a.description.toLowerCase().includes(q)
    )
    if (matches.length > 0) filtered[cat] = matches
  }
  return filtered
})

// Requirements grouped: built-in vs robot-specific
const builtinRequirementItems = computed(() => {
  const q = search.value.toLowerCase()
  const items = Object.entries(REQUIREMENTS).map(([type, def]) => ({ type, ...def }))
  if (!q) return items
  return items.filter(a =>
    a.type.includes(q) || (a.description || '').toLowerCase().includes(q)
  )
})

const robotRequirementItems = computed(() => {
  const q = search.value.toLowerCase()
  const items = Object.entries(robotRequirements.value).map(([type, def]) => ({ type, ...def }))
  if (!q) return items
  return items.filter(a =>
    a.type.includes(q) || (a.description || '').toLowerCase().includes(q)
  )
})

// Guards grouped: built-in vs robot-specific
const builtinGuardItems = computed(() => {
  const q = search.value.toLowerCase()
  const items = Object.entries(GUARDS).map(([type, def]) => ({ type, ...def }))
  if (!q) return items
  return items.filter(a =>
    a.type.includes(q) || (a.description || '').toLowerCase().includes(q)
  )
})

const robotGuardItems = computed(() => {
  const q = search.value.toLowerCase()
  const items = Object.entries(robotGuards.value).map(([type, def]) => ({ type, ...def }))
  if (!q) return items
  return items.filter(a =>
    a.type.includes(q) || (a.description || '').toLowerCase().includes(q)
  )
})

function isRobotCategory(cat) {
  return !(cat in CATEGORIES) && cat in robotCategories.value
}

function categoryDisplayName(cat) {
  const base = allCategories.value[cat]?.label || cat
  if (isRobotCategory(cat) && robotLabel.value) {
    return `${robotLabel.value} / ${base}`
  }
  return base
}

function toggleCategory(cat) {
  if (expandedCategories.value.has(cat)) {
    expandedCategories.value.delete(cat)
  } else {
    expandedCategories.value.add(cat)
  }
}

function onDragStart(e, type) {
  e.dataTransfer.setData('action-type', type)
  e.dataTransfer.effectAllowed = 'copy'
}

function onDoubleClick(type) {
  window.dispatchEvent(new CustomEvent('add-action-from-catalog', { detail: type }))
}

// ── Experiment panel state ─────────────────────────────────────────────────
const experimentExpanded = ref(true)
const varsExpanded = ref(true)
const eventsExpanded = ref(true)
const reqsExpanded = ref(true)
const robotReqsExpanded = ref(true)
const guardsExpanded = ref(true)
const robotGuardsExpanded = ref(true)

// Variables
const newVarName = ref('')
const newVarValue = ref('')

function addVariable() {
  const name = newVarName.value.trim()
  if (!name) return
  snapshot()
  const val = parseVarValue(newVarValue.value)
  meta.variables = { ...meta.variables, [name]: val }
  newVarName.value = ''
  newVarValue.value = ''
}

function removeVariable(name) {
  snapshot()
  const vars = { ...meta.variables }
  delete vars[name]
  meta.variables = vars
}

function updateVariable(name, value) {
  snapshot()
  meta.variables = { ...meta.variables, [name]: parseVarValue(value) }
}

function parseVarValue(text) {
  if (text === 'true') return true
  if (text === 'false') return false
  if (text === 'null') return null
  const num = Number(text)
  if (!isNaN(num) && text !== '') return num
  return text
}

function formatValue(val) {
  if (val === null || val === undefined) return ''
  if (Array.isArray(val) || typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

// Events
const allEvents = computed(() => getAllEventNames())
const newEventName = ref('')

function addEvent() {
  const name = newEventName.value.trim()
  if (!name) return
  if (meta.events.includes(name)) return
  snapshot()
  meta.events = [...meta.events, name]
  newEventName.value = ''
}

function removeEvent(name) {
  snapshot()
  meta.events = meta.events.filter(e => e !== name)
}
</script>

<template>
  <aside class="catalog">
    <div class="catalog-header">
      <span class="catalog-title">Actions</span>
    </div>

    <div class="search-box">
      <input
        v-model="search"
        type="text"
        placeholder="Search..."
        class="search-input"
      />
    </div>

    <div class="catalog-list">
      <!-- Action categories -->
      <div
        v-for="(actions, cat) in grouped"
        :key="cat"
        class="category-group"
      >
        <div
          class="category-header"
          @click="toggleCategory(cat)"
        >
          <span class="expand-arrow">{{ expandedCategories.has(cat) ? '\u25BE' : '\u25B8' }}</span>
          <span
            class="category-dot"
            :style="{ background: allCategories[cat]?.color || '#666' }"
          ></span>
          <span class="category-name">{{ categoryDisplayName(cat) }}</span>
          <span class="category-count">{{ actions.length }}</span>
        </div>

        <div v-if="expandedCategories.has(cat)" class="category-items">
          <div
            v-for="action in actions"
            :key="action.type"
            class="action-item"
            draggable="true"
            @dragstart="onDragStart($event, action.type)"
            @dblclick="onDoubleClick(action.type)"
            :title="action.description"
          >
            <span
              class="action-dot"
              :style="{ background: allCategories[cat]?.color || '#666' }"
            ></span>
            <div class="action-info">
              <span class="action-name">{{ action.type }}</span>
              <span class="action-desc">{{ action.description }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ Requirements section ═══ -->
      <div v-if="builtinRequirementItems.length > 0 || robotRequirementItems.length > 0" class="section-separator">
        <span class="separator-label">Requirements</span>
      </div>

      <!-- Built-in requirements -->
      <div v-if="builtinRequirementItems.length > 0" class="category-group">
        <div class="category-header" @click="reqsExpanded = !reqsExpanded">
          <span class="expand-arrow">{{ reqsExpanded ? '\u25BE' : '\u25B8' }}</span>
          <span class="category-dot" style="background: #e056a0"></span>
          <span class="category-name">General</span>
          <span class="category-count">{{ builtinRequirementItems.length }}</span>
        </div>
        <div v-if="reqsExpanded" class="category-items">
          <div
            v-for="req in builtinRequirementItems"
            :key="req.type"
            class="action-item"
            draggable="true"
            @dragstart="onDragStart($event, req.type)"
            @dblclick="onDoubleClick(req.type)"
            :title="req.description"
          >
            <span class="action-dot" style="background: #e056a0"></span>
            <div class="action-info">
              <span class="action-name">{{ req.type.replace('require_', '') }}</span>
              <span class="action-desc">{{ req.description }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Robot-specific requirements -->
      <div v-if="robotRequirementItems.length > 0" class="category-group">
        <div class="category-header" @click="robotReqsExpanded = !robotReqsExpanded">
          <span class="expand-arrow">{{ robotReqsExpanded ? '\u25BE' : '\u25B8' }}</span>
          <span class="category-dot" style="background: #e056a0"></span>
          <span class="category-name">{{ robotLabel || 'Robot' }}</span>
          <span class="category-count">{{ robotRequirementItems.length }}</span>
        </div>
        <div v-if="robotReqsExpanded" class="category-items">
          <div
            v-for="req in robotRequirementItems"
            :key="req.type"
            class="action-item"
            draggable="true"
            @dragstart="onDragStart($event, req.type)"
            @dblclick="onDoubleClick(req.type)"
            :title="req.description"
          >
            <span class="action-dot" style="background: #e056a0"></span>
            <div class="action-info">
              <span class="action-name">{{ req.type.replace('require_', '') }}</span>
              <span class="action-desc">{{ req.description }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ Guards section ═══ -->
      <div v-if="builtinGuardItems.length > 0 || robotGuardItems.length > 0" class="section-separator">
        <span class="separator-label">Guards</span>
      </div>

      <!-- Built-in guards -->
      <div v-if="builtinGuardItems.length > 0" class="category-group">
        <div class="category-header" @click="guardsExpanded = !guardsExpanded">
          <span class="expand-arrow">{{ guardsExpanded ? '\u25BE' : '\u25B8' }}</span>
          <span class="category-dot" style="background: #3dc1d3"></span>
          <span class="category-name">General</span>
          <span class="category-count">{{ builtinGuardItems.length }}</span>
        </div>
        <div v-if="guardsExpanded" class="category-items">
          <div
            v-for="guard in builtinGuardItems"
            :key="guard.type"
            class="action-item"
            draggable="true"
            @dragstart="onDragStart($event, guard.type)"
            @dblclick="onDoubleClick(guard.type)"
            :title="guard.description"
          >
            <span class="action-dot" style="background: #3dc1d3"></span>
            <div class="action-info">
              <span class="action-name">{{ guard.type }}</span>
              <span class="action-desc">{{ guard.description }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Robot-specific guards -->
      <div v-if="robotGuardItems.length > 0" class="category-group">
        <div class="category-header" @click="robotGuardsExpanded = !robotGuardsExpanded">
          <span class="expand-arrow">{{ robotGuardsExpanded ? '\u25BE' : '\u25B8' }}</span>
          <span class="category-dot" style="background: #3dc1d3"></span>
          <span class="category-name">{{ robotLabel || 'Robot' }}</span>
          <span class="category-count">{{ robotGuardItems.length }}</span>
        </div>
        <div v-if="robotGuardsExpanded" class="category-items">
          <div
            v-for="guard in robotGuardItems"
            :key="guard.type"
            class="action-item"
            draggable="true"
            @dragstart="onDragStart($event, guard.type)"
            @dblclick="onDoubleClick(guard.type)"
            :title="guard.description"
          >
            <span class="action-dot" style="background: #3dc1d3"></span>
            <div class="action-info">
              <span class="action-name">{{ guard.type }}</span>
              <span class="action-desc">{{ guard.description }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ Experiment panel ═══ -->
      <div class="section-separator">
        <span class="separator-label">Experiment</span>
      </div>

      <!-- Variables subsection -->
      <div class="experiment-section">
        <div class="exp-section-header" @click="varsExpanded = !varsExpanded">
          <span class="expand-arrow">{{ varsExpanded ? '\u25BE' : '\u25B8' }}</span>
          <span class="exp-section-title">Variables</span>
          <span class="category-count">{{ Object.keys(meta.variables).length }}</span>
        </div>
        <div v-if="varsExpanded" class="exp-section-body">
          <div v-for="(value, name) in meta.variables" :key="name" class="exp-var-row">
            <span class="exp-var-name">{{ name }}</span>
            <input type="text" :value="formatValue(value)" @change="updateVariable(name, $event.target.value)" class="exp-var-input" />
            <button class="exp-del-btn" @click="removeVariable(name)" title="Remove">&times;</button>
          </div>
          <div class="exp-add-row">
            <input v-model="newVarName" type="text" placeholder="name" class="exp-var-input" @keydown.enter="addVariable" />
            <input v-model="newVarValue" type="text" placeholder="value" class="exp-var-input" @keydown.enter="addVariable" />
            <button class="exp-add-btn" @click="addVariable" title="Add variable">+</button>
          </div>
        </div>
      </div>

      <!-- Events subsection -->
      <div class="experiment-section">
        <div class="exp-section-header" @click="eventsExpanded = !eventsExpanded">
          <span class="expand-arrow">{{ eventsExpanded ? '\u25BE' : '\u25B8' }}</span>
          <span class="exp-section-title">Events</span>
          <span class="category-count">{{ Object.keys(allEvents).length }}</span>
        </div>
        <div v-if="eventsExpanded" class="exp-section-body">
          <div v-for="(source, name) in allEvents" :key="name" class="exp-event-row">
            <span class="exp-event-name">{{ name }}</span>
            <span v-if="source === 'auto'" class="exp-auto-tag">auto</span>
            <button v-if="source === 'manual'" class="exp-del-btn" @click="removeEvent(name)" title="Remove">&times;</button>
          </div>
          <div v-if="Object.keys(allEvents).length === 0" class="exp-empty">No events declared</div>
          <div class="exp-add-row">
            <input v-model="newEventName" type="text" placeholder="event name" class="exp-var-input" style="flex:1" @keydown.enter="addEvent" />
            <button class="exp-add-btn" @click="addEvent" title="Add event">+</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="catalog-footer">
      <div class="legend-item">Drag or double-click to add</div>
    </div>
  </aside>
</template>

<style scoped>
.catalog {
  width: 200px;
  height: 100%;
  flex-shrink: 0;
  background: var(--bg-surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.catalog-header {
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-dim);
}

.search-box {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}

.search-input {
  width: 100%;
  font-family: inherit;
  font-size: 11px;
  padding: 4px 8px;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  outline: none;
}
.search-input:focus { border-color: var(--accent); }

.catalog-list {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}

.category-group {
  border-bottom: 1px solid var(--border);
}
.category-group:last-child {
  border-bottom: none;
}

.category-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  user-select: none;
  background: var(--bg);
  transition: background 0.1s;
}
.category-header:hover { background: var(--bg-hover); }

.expand-arrow {
  font-size: 10px;
  width: 10px;
  color: var(--text-dim);
}

.category-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
}

.category-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.category-count {
  font-size: 9px;
  font-weight: 400;
  color: var(--text-dim);
  background: var(--bg-surface);
  padding: 1px 5px;
  border-radius: 8px;
}

.category-items {
  padding: 4px 0;
}

.action-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 12px 4px 24px;
  font-size: 11px;
  cursor: grab;
  user-select: none;
  transition: background 0.1s;
}
.action-item:hover { background: var(--bg-hover); }
.action-item:active { cursor: grabbing; }

.action-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 4px;
}

.action-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.action-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.action-desc {
  font-size: 9px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.catalog-footer {
  padding: 6px 12px;
  border-top: 1px solid var(--border);
}

.legend-item {
  font-size: 9px;
  color: var(--text-dim);
  font-style: italic;
}

/* ── Section separator ── */
.section-separator {
  padding: 6px 8px 2px;
  border-top: 1px solid var(--border);
}

.separator-label {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-dim);
  opacity: 0.7;
}

/* ── Experiment panel ── */
.experiment-section {
  border-bottom: 1px solid var(--border);
}

.exp-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  cursor: pointer;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  user-select: none;
  transition: background 0.1s;
}
.exp-section-header:hover { background: var(--bg-hover); }

.exp-section-title {
  flex: 1;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.exp-section-body {
  padding: 2px 8px 6px;
}

.exp-var-row {
  display: flex;
  align-items: center;
  gap: 3px;
  margin-bottom: 3px;
}

.exp-var-name {
  font-size: 9px;
  font-weight: 500;
  color: var(--accent);
  min-width: 40px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.exp-var-input {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  padding: 2px 4px;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 3px;
  outline: none;
  flex: 1;
  min-width: 0;
}
.exp-var-input:focus { border-color: var(--accent); }

.exp-del-btn {
  font-size: 12px;
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  padding: 0 2px;
  line-height: 1;
}
.exp-del-btn:hover { color: #e74c3c; }

.exp-add-row {
  display: flex;
  gap: 3px;
  margin-top: 3px;
}

.exp-add-btn {
  font-size: 12px;
  font-weight: 700;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--accent);
  cursor: pointer;
  border-radius: 3px;
  padding: 0 5px;
  line-height: 1;
}
.exp-add-btn:hover { background: var(--bg-hover); }

.exp-event-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 2px;
  padding: 1px 0;
}

.exp-event-name {
  font-size: 9px;
  font-weight: 500;
  color: #a55eea;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.exp-auto-tag {
  font-size: 8px;
  color: var(--text-dim);
  background: var(--bg);
  padding: 0 4px;
  border-radius: 3px;
  border: 1px solid var(--border);
}

.exp-empty {
  font-size: 9px;
  color: var(--text-dim);
  font-style: italic;
  padding: 2px 0;
}
</style>
