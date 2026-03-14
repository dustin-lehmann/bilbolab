<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { samples, fieldTree, darkMode } from '../viewerState.js'
import {
  presets, presetCategories, presetsLoaded, loadPresets,
  getPresetsByCategory, saveUserPreset, deleteUserPreset
} from '../utils/presetLoader.js'
import FieldTree from './FieldTree.vue'
import PlotPane from './PlotPane.vue'

// ── Layout persistence ───────────────────────────────────────────────────────
const LAYOUT_KEY = 'experiment-viewer-layout'

function serializeLayout() {
  return {
    nextId,
    activeTabId: activeTabId.value,
    focusedPlotId: focusedPlotId.value,
    plotHeights: plotHeights.value,
    showActionBands: showActionBands.value,
    showActionBorders: showActionBorders.value,
    tabs: tabs.value.map(t => ({
      id: t.id,
      label: t.label,
      plots: t.plots.map(p => ({ id: p.id, fields: [...p.fields] })),
    })),
  }
}

function saveLayout() {
  try {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(serializeLayout()))
  } catch { /* ignore */ }
}

function loadLayout() {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY)
    if (!raw) return null
    return JSON.parse(raw)
  } catch { return null }
}

// ── Tab / plot state ─────────────────────────────────────────────────────────
let nextId = 1
function makeId() { return nextId++ }

function createPlot() {
  return { id: makeId(), fields: new Set() }
}

function createTab(label) {
  return { id: makeId(), label, plots: [createPlot()] }
}

// Restore or create default state
const saved = loadLayout()
let initialTabs, initialActiveTabId, initialFocusedPlotId

if (saved && saved.tabs?.length > 0) {
  nextId = saved.nextId || 1
  initialTabs = saved.tabs.map(t => ({
    id: t.id,
    label: t.label,
    plots: t.plots.map(p => ({ id: p.id, fields: new Set(p.fields || []) })),
  }))
  initialActiveTabId = saved.activeTabId ?? initialTabs[0].id
  initialFocusedPlotId = saved.focusedPlotId ?? initialTabs[0].plots[0]?.id
} else {
  const defaultTab = createTab('Plot 1')
  initialTabs = [defaultTab]
  initialActiveTabId = defaultTab.id
  initialFocusedPlotId = defaultTab.plots[0].id
}

const tabs = ref(initialTabs)
const activeTabId = ref(initialActiveTabId)
const focusedPlotId = ref(initialFocusedPlotId)

const activeTab = computed(() => tabs.value.find(t => t.id === activeTabId.value) || tabs.value[0])

// All selected paths (union across all plots in active tab, for field tree highlighting)
const allSelectedPaths = computed(() => {
  const s = new Set()
  for (const plot of activeTab.value.plots) {
    for (const f of plot.fields) s.add(f)
  }
  return s
})

// ── Tab management ───────────────────────────────────────────────────────────
function addTab() {
  const t = createTab(`Plot ${tabs.value.length + 1}`)
  tabs.value = [...tabs.value, t]
  activeTabId.value = t.id
  focusedPlotId.value = t.plots[0].id
}

function removeTab(tabId) {
  if (tabs.value.length <= 1) return
  const idx = tabs.value.findIndex(t => t.id === tabId)
  tabs.value = tabs.value.filter(t => t.id !== tabId)
  if (activeTabId.value === tabId) {
    const newIdx = Math.min(idx, tabs.value.length - 1)
    activeTabId.value = tabs.value[newIdx].id
    focusedPlotId.value = tabs.value[newIdx].plots[0]?.id ?? null
  }
}

function switchTab(tabId) {
  activeTabId.value = tabId
  const tab = tabs.value.find(t => t.id === tabId)
  if (tab && tab.plots.length > 0) {
    // Keep focusedPlotId if it belongs to this tab, otherwise pick first
    if (!tab.plots.find(p => p.id === focusedPlotId.value)) {
      focusedPlotId.value = tab.plots[0].id
    }
  }
}

function renameTab(tabId) {
  const tab = tabs.value.find(t => t.id === tabId)
  if (!tab) return
  const name = prompt('Tab name:', tab.label)
  if (name && name.trim()) tab.label = name.trim()
}

// ── Plot management ──────────────────────────────────────────────────────────
function addPlot() {
  const tab = activeTab.value
  const plot = createPlot()
  tab.plots = [...tab.plots, plot]
  focusedPlotId.value = plot.id
}

function removePlot(plotId) {
  const tab = activeTab.value
  if (tab.plots.length <= 1) return
  const idx = tab.plots.findIndex(p => p.id === plotId)
  tab.plots = tab.plots.filter(p => p.id !== plotId)
  if (focusedPlotId.value === plotId) {
    const newIdx = Math.min(idx, tab.plots.length - 1)
    focusedPlotId.value = tab.plots[newIdx].id
  }
}

// ── Plot reorder via drag ────────────────────────────────────────────────────
const dragSourcePlotId = ref(null)

function onPlotDragStart(plotId) {
  dragSourcePlotId.value = plotId
}

function onPlotDrop(targetPlotId) {
  const srcId = dragSourcePlotId.value
  dragSourcePlotId.value = null
  if (!srcId || srcId === targetPlotId) return
  const tab = activeTab.value
  const plots = [...tab.plots]
  const srcIdx = plots.findIndex(p => p.id === srcId)
  const tgtIdx = plots.findIndex(p => p.id === targetPlotId)
  if (srcIdx < 0 || tgtIdx < 0) return
  const [moved] = plots.splice(srcIdx, 1)
  plots.splice(tgtIdx, 0, moved)
  tab.plots = plots
}

// ── Field toggle (click in field tree → add/remove from focused plot) ────────
function toggleField(path) {
  const plot = activeTab.value.plots.find(p => p.id === focusedPlotId.value)
  if (!plot) return
  const s = new Set(plot.fields)
  if (s.has(path)) s.delete(path)
  else s.add(path)
  plot.fields = s
}

function clearFields() {
  const plot = activeTab.value.plots.find(p => p.id === focusedPlotId.value)
  if (plot) plot.fields = new Set()
}

function newPlotWithFields(paths) {
  const t = createTab(paths.length === 1 ? paths[0].split('.').pop() : `Plot ${tabs.value.length + 1}`)
  t.plots[0].fields = new Set(paths)
  tabs.value = [...tabs.value, t]
  activeTabId.value = t.id
  focusedPlotId.value = t.plots[0].id
}

function onDropField(plotId, path) {
  const plot = activeTab.value.plots.find(p => p.id === plotId)
  if (!plot) return
  const s = new Set(plot.fields)
  s.add(path)
  plot.fields = s
  focusedPlotId.value = plotId
}

function onRemoveField(plotId, path) {
  const plot = activeTab.value.plots.find(p => p.id === plotId)
  if (!plot) return
  const s = new Set(plot.fields)
  s.delete(path)
  plot.fields = s
}

// ── Cursor sync across plots ─────────────────────────────────────────────────
const syncCursorIdx = ref(null)
const syncSourcePlotId = ref(null)

function onCursorSync(plotId, idx) {
  syncSourcePlotId.value = plotId
  syncCursorIdx.value = idx
}

// ── Action overlay toggles ──────────────────────────────────────────────────
const showActionBands = ref(saved?.showActionBands ?? true)
const showActionBorders = ref(saved?.showActionBorders ?? true)

// ── Vertical divider dragging ────────────────────────────────────────────────
const plotHeights = ref(saved?.plotHeights ?? {})
const draggingDivider = ref(null)
const stackEl = ref(null)

function getPlotFlex(plotId) {
  return plotHeights.value[plotId] ?? 1
}

function onDividerDown(e, index) {
  e.preventDefault()
  const tab = activeTab.value
  const aboveId = tab.plots[index].id
  const belowId = tab.plots[index + 1].id
  const aboveH = plotHeights.value[aboveId] ?? 1
  const belowH = plotHeights.value[belowId] ?? 1
  const totalH = stackEl.value?.getBoundingClientRect().height ?? 400

  draggingDivider.value = { index, startY: e.clientY, aboveId, belowId, aboveH, belowH, totalH }

  const onMove = (ev) => {
    if (!draggingDivider.value) return
    const dy = ev.clientY - draggingDivider.value.startY
    const ratio = dy / draggingDivider.value.totalH * (aboveH + belowH)
    const newAbove = Math.max(0.1, aboveH + ratio)
    const newBelow = Math.max(0.1, belowH - ratio)
    plotHeights.value = { ...plotHeights.value, [aboveId]: newAbove, [belowId]: newBelow }
  }

  const onUp = () => {
    draggingDivider.value = null
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }

  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

// ── Add plot hover zone ──────────────────────────────────────────────────────
const addZoneVisible = ref(false)

// ── Presets ──────────────────────────────────────────────────────────────────
const activePresetLabel = ref(null)
const presetMenuOpen = ref(false)
const showSaveDialog = ref(false)
const savePresetName = ref('')
const savePresetCategory = ref('')
const groupedPresets = computed(() => getPresetsByCategory(presets.value))

function applyPreset(preset) {
  const plot = activeTab.value.plots.find(p => p.id === focusedPlotId.value)
  if (plot) plot.fields = new Set(preset.fields)
  activePresetLabel.value = preset.label
  presetMenuOpen.value = false
}

function togglePresetMenu() {
  presetMenuOpen.value = !presetMenuOpen.value
  showSaveDialog.value = false
}

function closePresetMenu() {
  presetMenuOpen.value = false
  showSaveDialog.value = false
}

function openSaveDialog() {
  savePresetName.value = ''
  savePresetCategory.value = 'User'
  showSaveDialog.value = true
}

function saveCurrentAsPreset() {
  const plot = activeTab.value.plots.find(p => p.id === focusedPlotId.value)
  if (!savePresetName.value.trim() || !plot || plot.fields.size === 0) return
  saveUserPreset({
    label: savePresetName.value.trim(),
    category: savePresetCategory.value.trim() || 'User',
    fields: [...plot.fields],
  })
  showSaveDialog.value = false
  activePresetLabel.value = savePresetName.value.trim()
}

// ── Persist layout on changes ────────────────────────────────────────────────
watch(
  [tabs, activeTabId, focusedPlotId, plotHeights, showActionBands, showActionBorders],
  () => saveLayout(),
  { deep: true }
)

onMounted(() => { loadPresets() })
</script>

<template>
  <div class="sample-plotter">
    <!-- Field picker sidebar -->
    <div class="field-sidebar">
      <div class="field-header">
        <span class="section-title">Fields</span>
        <button v-if="allSelectedPaths.size > 0" class="clear-btn" @click="clearFields">Clear</button>
      </div>

      <!-- Preset selector -->
      <div class="preset-bar">
        <div class="preset-dropdown-wrapper">
          <button class="preset-trigger" @click="togglePresetMenu">
            <span class="preset-trigger-label">{{ activePresetLabel || 'Presets' }}</span>
            <span class="preset-trigger-arrow">{{ presetMenuOpen ? '▴' : '▾' }}</span>
          </button>
          <div v-if="presetMenuOpen" class="preset-dropdown" @mouseleave="closePresetMenu">
            <template v-for="cat in presetCategories" :key="cat">
              <div class="preset-cat-header">{{ cat }}</div>
              <button
                v-for="p in groupedPresets[cat]" :key="p.label"
                class="preset-option"
                :class="{ active: activePresetLabel === p.label }"
                :title="p.description || p.fields.join(', ')"
                @click="applyPreset(p)"
              >
                <span class="preset-option-label">{{ p.label }}</span>
                <span class="preset-option-count">{{ p.fields.length }}</span>
              </button>
            </template>
            <div class="preset-cat-header preset-save-header"><span>Save Preset</span></div>
            <div v-if="!showSaveDialog" class="preset-save-row">
              <button class="preset-option save-btn" :disabled="allSelectedPaths.size === 0" @click.stop="openSaveDialog">
                <span class="preset-option-label">+ Save current as preset</span>
              </button>
            </div>
            <div v-else class="preset-save-form" @click.stop>
              <input v-model="savePresetName" class="save-input" placeholder="Preset name" @keydown.enter="saveCurrentAsPreset" />
              <input v-model="savePresetCategory" class="save-input" placeholder="Category (default: User)" />
              <div class="save-actions">
                <button class="save-confirm" @click="saveCurrentAsPreset" :disabled="!savePresetName.trim()">Save</button>
                <button class="save-cancel" @click="showSaveDialog = false">Cancel</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="field-tree-container">
        <FieldTree
          :nodes="fieldTree"
          :selected-paths="allSelectedPaths"
          @toggle="toggleField"
          @new-plot="newPlotWithFields"
        />
      </div>
    </div>

    <!-- Main chart area -->
    <div class="chart-area">
      <!-- Tab bar -->
      <div class="tab-bar">
        <div class="tab-bar-left">
          <button
            v-for="tab in tabs" :key="tab.id"
            class="plot-tab"
            :class="{ active: tab.id === activeTabId }"
            @click="switchTab(tab.id)"
            @dblclick="renameTab(tab.id)"
          >
            <span class="tab-label">{{ tab.label }}</span>
            <span v-if="tabs.length > 1" class="tab-close" @click.stop="removeTab(tab.id)">&times;</span>
          </button>
          <button class="tab-add" @click="addTab" title="Add tab">+</button>
        </div>
        <div class="tab-bar-right">
          <label class="chart-toggle" :class="{ active: showActionBands }" title="Show colored action regions">
            <input type="checkbox" v-model="showActionBands" />
            <span>Bands</span>
          </label>
          <label class="chart-toggle" :class="{ active: showActionBorders }" title="Show dashed action border lines">
            <input type="checkbox" v-model="showActionBorders" />
            <span>Borders</span>
          </label>
        </div>
      </div>

      <!-- Plot stack -->
      <div ref="stackEl" class="plot-stack">
        <template v-for="(plot, i) in activeTab.plots" :key="plot.id">
          <!-- Divider between plots -->
          <div
            v-if="i > 0"
            class="plot-divider"
            :class="{ dragging: draggingDivider?.index === i - 1 }"
            @mousedown="onDividerDown($event, i - 1)"
          >
            <div class="divider-line"></div>
          </div>

          <!-- Plot pane -->
          <PlotPane
            :fields="plot.fields"
            :focused="plot.id === focusedPlotId"
            :can-close="activeTab.plots.length > 1"
            :show-action-bands="showActionBands"
            :show-action-borders="showActionBorders"
            :sync-cursor-idx="syncSourcePlotId !== plot.id ? syncCursorIdx : null"
            :style="{ flex: getPlotFlex(plot.id) }"
            @focus="focusedPlotId = plot.id"
            @close="removePlot(plot.id)"
            @cursor-sync="(idx) => onCursorSync(plot.id, idx)"
            @remove-field="(path) => onRemoveField(plot.id, path)"
            @drop-field="(path) => onDropField(plot.id, path)"
            @drag-start="onPlotDragStart(plot.id)"
            @drop-pane="(srcId) => onPlotDrop(plot.id)"
          />
        </template>

        <!-- Add plot zone (bottom edge) -->
        <div
          class="add-plot-zone"
          :class="{ visible: addZoneVisible }"
          @mouseenter="addZoneVisible = true"
          @mouseleave="addZoneVisible = false"
          @click="addPlot"
        >
          <div class="add-plot-line"></div>
          <span class="add-plot-label">+ Add Plot</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sample-plotter {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

/* ── Field sidebar ─────────────────────────────────────────────────────── */
.field-sidebar {
  width: 220px;
  min-width: 180px;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.field-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px 4px;
}

.section-title {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-dim);
}

.clear-btn {
  font-family: inherit;
  font-size: 10px;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
}
.clear-btn:hover { color: var(--accent); border-color: var(--accent-dim); }

/* ── Preset dropdown ──────────────────────────────────────────────────── */
.preset-bar {
  padding: 4px 10px 6px;
  border-bottom: 1px solid var(--border);
}

.preset-dropdown-wrapper { position: relative; }

.preset-trigger {
  font-family: inherit;
  font-size: 11px;
  width: 100%;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-surface);
  color: var(--text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}
.preset-trigger:hover { border-color: var(--accent-dim); }

.preset-trigger-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preset-trigger-arrow { font-size: 9px; color: var(--text-dim); flex-shrink: 0; }

.preset-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 2px;
  max-height: 420px;
  overflow-y: auto;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  z-index: 100;
  padding: 4px 0;
}

.preset-cat-header {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-dim);
  padding: 6px 10px 2px;
}
.preset-cat-header:first-child { padding-top: 4px; }

.preset-option {
  font-family: inherit;
  font-size: 11px;
  width: 100%;
  padding: 3px 10px;
  border: none;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  text-align: left;
}
.preset-option:hover { background: var(--bg-hover); }
.preset-option.active { color: var(--accent); }
.preset-option:disabled { opacity: 0.4; cursor: default; }

.preset-option-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preset-option-count {
  font-size: 9px;
  color: var(--text-dim);
  flex-shrink: 0;
  background: var(--bg-hover);
  padding: 0 4px;
  border-radius: 3px;
}

.preset-save-header {
  border-top: 1px solid var(--border);
  margin-top: 4px;
  padding-top: 8px;
}

.preset-save-form {
  padding: 4px 10px 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.save-input {
  font-family: inherit;
  font-size: 10px;
  padding: 3px 6px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--bg);
  color: var(--text);
  outline: none;
}
.save-input:focus { border-color: var(--accent-dim); }
.save-input::placeholder { color: var(--text-dim); }

.save-actions { display: flex; gap: 4px; }

.save-confirm, .save-cancel {
  font-family: inherit;
  font-size: 10px;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 3px;
  cursor: pointer;
  background: var(--bg-surface);
  color: var(--text);
}
.save-confirm { background: var(--accent); color: #fff; border-color: var(--accent); }
.save-confirm:disabled { opacity: 0.4; cursor: default; }
.save-cancel:hover { background: var(--bg-hover); }

.field-tree-container {
  flex: 1;
  overflow-y: auto;
  padding: 6px 10px;
}

/* ── Chart area ────────────────────────────────────────────────────────── */
.chart-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Tab bar ──────────────────────────────────────────────────────────── */
.tab-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 6px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
  flex-shrink: 0;
  gap: 8px;
}

.tab-bar-left {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  overflow-x: auto;
}

.tab-bar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.plot-tab {
  font-family: inherit;
  font-size: 10px;
  padding: 3px 8px;
  border: 1px solid transparent;
  border-radius: 4px 4px 0 0;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.plot-tab:hover { background: var(--bg-hover); color: var(--text); }
.plot-tab.active {
  background: var(--bg);
  color: var(--accent);
  border-color: var(--border);
  border-bottom-color: var(--bg);
}

.tab-label { pointer-events: none; }
.tab-close {
  font-size: 12px;
  line-height: 1;
  opacity: 0.4;
  cursor: pointer;
}
.tab-close:hover { opacity: 1; color: var(--error); }

.tab-add {
  font-family: inherit;
  font-size: 12px;
  padding: 2px 6px;
  border: none;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  border-radius: 3px;
}
.tab-add:hover { background: var(--bg-hover); color: var(--text); }

/* ── Chart toggles ────────────────────────────────────────────────────── */
.chart-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: var(--text-dim);
  cursor: pointer;
  user-select: none;
}
.chart-toggle input { display: none; }
.chart-toggle.active { color: var(--text); }
.chart-toggle span::before { content: '○ '; font-size: 8px; }
.chart-toggle.active span::before { content: '● '; color: var(--accent); }

/* ── Plot stack ───────────────────────────────────────────────────────── */
.plot-stack {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

/* ── Plot divider ─────────────────────────────────────────────────────── */
.plot-divider {
  height: 7px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: row-resize;
  position: relative;
  z-index: 10;
}

.plot-divider:hover .divider-line,
.plot-divider.dragging .divider-line {
  background: var(--accent-dim);
  height: 2px;
}

.divider-line {
  width: 100%;
  height: 1px;
  background: var(--border);
  transition: background 0.1s, height 0.1s;
}

/* ── Add plot zone (bottom edge) ──────────────────────────────────────── */
.add-plot-zone {
  height: 6px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  position: relative;
  transition: height 0.15s, background 0.15s;
  overflow: hidden;
}

.add-plot-zone.visible {
  height: 24px;
  background: var(--bg-surface);
}

.add-plot-line {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--border);
  transition: background 0.1s;
}

.add-plot-zone.visible .add-plot-line {
  background: var(--accent-dim);
}

.add-plot-label {
  font-size: 10px;
  color: var(--text-dim);
  opacity: 0;
  transition: opacity 0.15s;
  user-select: none;
}

.add-plot-zone.visible .add-plot-label {
  opacity: 1;
}

.add-plot-zone:hover .add-plot-label {
  color: var(--accent);
}
</style>
