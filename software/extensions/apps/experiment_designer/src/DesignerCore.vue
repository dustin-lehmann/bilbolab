<script setup>
import { ref, watch, onMounted, onUnmounted, computed, toRefs } from 'vue'
import ActionCatalog from './components/ActionCatalog.vue'
import TabBar from './components/TabBar.vue'
import ExperimentTabBar from './components/ExperimentTabBar.vue'
import UnifiedTabBar from './components/UnifiedTabBar.vue'
import Canvas from './components/Canvas.vue'
import InspectorPanel from './components/InspectorPanel.vue'
import YamlPreview from './components/YamlPreview.vue'
import TemplateMenu from './components/TemplateMenu.vue'
import RecentMenu from './components/RecentMenu.vue'
import {
  nodes, edges, meta, darkMode, selection, selectedNodeIds, pan, zoom,
  mode, setMode,
  undo, redo, canUndo, canRedo,
  addNode, selectNode, selectNodes, removeNode, removeEdge, removeSelectedNodes, clearSelection,
  loadState, snapshot, activeParentId, getDescendants,
  layoutDirection, toggleLayoutDirection, columnWrap, toggleColumnWrap, autoLayout, autoLayoutAll, zoomToFit,
  followMode, toggleFollowMode,
  inspectorCollapsed, toggleInspector,
} from './graphState.js'
import { getSummary, getParamLines, getTransitionPorts } from './actionRegistry.js'
import { selectedRobot, availableRobots, setRobot, loadManifest } from './actionRegistry.js'
import { toYaml, fromYaml } from './serializer.js'
import { snapToGrid, NODE_WIDTH } from './utils/geometry.js'
import {
  newExperimentTab, markCurrentTabDirty, markCurrentTabClean, openTemplateTab,
  getCurrentFileHandle, setCurrentFileHandle, setCurrentFileName, getCurrentFileName,
  getCurrentFilePath, setCurrentFilePath,
  switchToExistingFile, hasOpenExperiment,
} from './experimentTabs.js'
import { addRecentFile } from './recentFiles.js'

const props = defineProps({
  darkMode: { type: Boolean, default: true },
  showToolbar: { type: Boolean, default: true },
  showYamlPreview: { type: Boolean, default: true },
  showExperimentTabs: { type: Boolean, default: true },
  readOnly: { type: Boolean, default: false },
  actionLibrary: { type: String, default: null },
  transparent: { type: Boolean, default: false },
  initialMode: { type: String, default: 'edit' },
  delegateFileOps: { type: Boolean, default: false },
})

const emit = defineEmits(['yaml-changed'])

// Sync darkMode prop to global ref
watch(() => props.darkMode, (val) => {
  darkMode.value = val
}, { immediate: true })

// Sync mode prop
watch(() => props.initialMode, (val) => {
  setMode(val)
}, { immediate: true })

// ── Robot handling ────────────────────────────────────────────────────────
function onRobotChange(id) { setRobot(id) }

// ── Computed: is playback? ─────────────────────────────────────────────────
const isPlayback = computed(() => props.readOnly || mode.value === 'playback')
const directionIcon = computed(() => layoutDirection.value === 'vertical' ? '\u2193' : '\u2192')

// ── Collapsible panels ────────────────────────────────────────────────────
const catalogCollapsed = ref(false)
function toggleCatalog() { catalogCollapsed.value = !catalogCollapsed.value }

// ── YAML output ────────────────────────────────────────────────────────────
const yamlOutput = ref('')
const yamlExpanded = ref(false)

function updateYaml() {
  yamlOutput.value = toYaml(nodes.value, edges.value, meta)
  emit('yaml-changed', yamlOutput.value)
}

watch([nodes, edges, () => meta.id, () => meta.description, () => meta.timeout, () => meta.variables], () => {
  updateYaml()
  markCurrentTabDirty()
}, { deep: true })

// ── Catalog double-click handler ───────────────────────────────────────────
function onCatalogAdd(e) {
  if (isPlayback.value) return
  const type = e.detail
  if (!type) return
  const x = (-pan.x + 400) / zoom.value - NODE_WIDTH / 2
  const y = (-pan.y + 300) / zoom.value
  const snapped = snapToGrid(x, y)
  const node = addNode(type, snapped.x, snapped.y, activeParentId.value || null)
  if (node) {
    selectNode(node.id)
  }
}

// ── File System Access API support ────────────────────────────────────────
const hasFileSystemAPI = !!window.showOpenFilePicker

const yamlFileTypes = [
  { description: 'YAML files', accept: { 'application/x-yaml': ['.yaml', '.yml'] } },
  { description: 'All files', accept: { '*/*': [] } },
]

// ── Open file ─────────────────────────────────────────────────────────────
const openFileInput = ref(null)

async function handleOpen() {
  if (props.delegateFileOps) {
    window.dispatchEvent(new CustomEvent('designer-send-event', {
      detail: { event: 'file_open', data: {} }
    }))
    return
  }
  if (hasFileSystemAPI) {
    try {
      const [handle] = await window.showOpenFilePicker({
        types: yamlFileTypes,
        multiple: false,
      })
      if (await switchToExistingFile(handle)) return
      const file = await handle.getFile()
      const text = await file.text()
      const label = file.name.replace(/\.(yaml|yml)$/, '')
      openTemplateTab(text, label)
      setCurrentFileHandle(handle)
      markCurrentTabClean()
      addRecentFile(file.name, handle)
    } catch (e) {
      if (e.name === 'AbortError') return
    }
  } else {
    openFileInput.value?.click()
  }
}

function onOpenFile(e) {
  const file = e.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    openTemplateTab(reader.result, file.name.replace(/\.(yaml|yml)$/, ''))
    setCurrentFileName(file.name)
    markCurrentTabClean()
  }
  reader.readAsText(file)
  e.target.value = ''
}

// ── Save (Cmd+S) — write to existing file handle or fall back to Save As
async function handleSave() {
  updateYaml()
  if (props.delegateFileOps) {
    const filePath = getCurrentFilePath()
    window.dispatchEvent(new CustomEvent('designer-send-event', {
      detail: { event: 'file_save', data: { yaml: yamlOutput.value, file_path: filePath } }
    }))
    return
  }
  const handle = getCurrentFileHandle()
  if (handle) {
    try {
      const writable = await handle.createWritable()
      await writable.write(yamlOutput.value)
      await writable.close()
      markCurrentTabClean()
      return
    } catch (e) {
      if (e.name === 'AbortError') return
      // Handle lost/revoked — fall through to Save As
    }
  }
  await handleSaveAs()
}

// ── Save As (Cmd+Shift+S) — always show file picker ──────────────────────
async function handleSaveAs() {
  updateYaml()
  const filename = getCurrentFileName() || `${meta.id || 'experiment'}.yaml`

  if (props.delegateFileOps) {
    const filePath = getCurrentFilePath()
    window.dispatchEvent(new CustomEvent('designer-send-event', {
      detail: { event: 'file_save_as', data: { yaml: yamlOutput.value, suggestedName: filename, file_path: filePath } }
    }))
    return
  }

  if (hasFileSystemAPI) {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: filename,
        types: yamlFileTypes,
      })
      const writable = await handle.createWritable()
      await writable.write(yamlOutput.value)
      await writable.close()
      setCurrentFileHandle(handle)
      markCurrentTabClean()
      const savedFile = await handle.getFile()
      addRecentFile(savedFile.name, handle)
      return
    } catch (e) {
      if (e.name === 'AbortError') return
    }
  }

  // Fallback: download to Downloads folder
  const blob = new Blob([yamlOutput.value], { type: 'text/yaml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
  markCurrentTabClean()
}

// ── Recent file selection ─────────────────────────────────────────────────
async function handleRecentSelect(text, name, handle) {
  if (handle && await switchToExistingFile(handle)) return
  openTemplateTab(text, name.replace(/\.(yaml|yml)$/, ''))
  if (handle) {
    setCurrentFileHandle(handle)
    markCurrentTabClean()
  }
}

// ── Import (paste/upload YAML into current tab) ──────────────────────────
const showImportModal = ref(false)
const importText = ref('')

function handleImport() {
  showImportModal.value = true
  importText.value = ''
}

function doImport() {
  if (!importText.value.trim()) return
  try {
    const result = fromYaml(importText.value)
    snapshot()
    nodes.value = result.nodes
    edges.value = result.edges
    Object.assign(meta, result.meta)
    showImportModal.value = false
    autoLayoutAll()
  } catch (e) {
    alert('Failed to parse YAML: ' + e.message)
  }
}

function handleImportFile(e) {
  const file = e.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => { importText.value = reader.result }
  reader.readAsText(file)
}

// ── New experiment ─────────────────────────────────────────────────────────
function handleNew() {
  newExperimentTab()
}

// ── Template selection ────────────────────────────────────────────────────
function handleTemplateSelect(yamlString, templateLabel) {
  openTemplateTab(yamlString, templateLabel)
}

// ── Template management events ───────────────────────────────────────────
const templateMenuRef = ref(null)

function handleTemplateSendEvent(payload) {
  const { event, data } = payload

  if (event === 'get_yaml_for_save') {
    // Frontend-only: get current YAML and complete the save
    updateYaml()
    if (templateMenuRef.value) {
      templateMenuRef.value.completeSaveTemplate(
        yamlOutput.value, data.folder, data.id, data.description
      )
    }
    return
  }

  // Forward all other template events to the widget backend
  window.dispatchEvent(new CustomEvent('designer-send-event', {
    detail: { event, data },
  }))
}

// ── Copy / Paste ──────────────────────────────────────────────────────────
let clipboard = null

function generateUniqueId(type) {
  const base = type.startsWith('__') ? type.replace(/^__|__$/g, '') : type
  const prefix = base + '_'
  let max = 0
  for (const n of nodes.value) {
    if (n.id.startsWith(prefix)) {
      const num = parseInt(n.id.slice(prefix.length), 10)
      if (!isNaN(num) && num > max) max = num
    }
  }
  return `${base}_${max + 1}`
}

function copySelection() {
  const ids = [...selectedNodeIds.value]
  if (ids.length === 0) return

  const allIds = new Set(ids)
  for (const id of ids) {
    for (const desc of getDescendants(id)) {
      allIds.add(desc.id)
    }
  }

  const nodesToCopy = nodes.value.filter(n =>
    allIds.has(n.id) && n.type !== '__start__' && n.type !== '__entry__' && n.type !== '__exit__'
  )
  if (nodesToCopy.length === 0) return

  const internalEdges = edges.value.filter(e => allIds.has(e.from) && allIds.has(e.to))

  clipboard = {
    nodes: JSON.parse(JSON.stringify(nodesToCopy)),
    edges: JSON.parse(JSON.stringify(internalEdges)),
  }
}

function pasteClipboard() {
  if (isPlayback.value) return
  if (!clipboard || clipboard.nodes.length === 0) return
  snapshot()

  const idMap = {}
  const newNodes = []

  for (const node of clipboard.nodes) {
    const newId = generateUniqueId(node.type)
    idMap[node.id] = newId

    const cloned = {
      ...node,
      id: newId,
      x: node.x + 40,
      y: node.y + 40,
    }
    if (cloned.parentId && idMap[cloned.parentId]) {
      cloned.parentId = idMap[cloned.parentId]
    } else if (cloned.parentId && !clipboard.nodes.some(n => n.id === cloned.parentId)) {
      cloned.parentId = activeParentId.value || null
    }
    cloned._summaryText = getSummary({ type: cloned.type, params: cloned.params })
    cloned._paramLineCount = cloned._summaryText ? 0 : getParamLines({ type: cloned.type, params: cloned.params }).length
    cloned._outPorts = cloned._outPorts || getTransitionPorts(cloned.type)
    newNodes.push(cloned)
  }

  for (const node of newNodes) {
    if (node.width != null) {
      const entryId = `__entry_${node.id}__`
      const exitId = `__exit_${node.id}__`
      const headerH = 32
      const portsH = 28
      const bodyTop = node.y + headerH
      const bodyBottom = node.y + node.height - portsH
      const centerX = node.x + (node.width - 80) / 2
      newNodes.push({
        id: entryId, type: '__entry__',
        x: centerX, y: bodyTop + 8,
        parentId: node.id, _outPorts: ['done'],
      })
      newNodes.push({
        id: exitId, type: '__exit__',
        x: centerX, y: bodyBottom - 30 - 8,
        parentId: node.id, _outPorts: [],
      })
    }
  }

  const newEdges = clipboard.edges.map(e => ({
    ...e,
    id: `edge_${idMap[e.from] || e.from}_${e.fromPort}_${idMap[e.to] || e.to}`,
    from: idMap[e.from] || e.from,
    to: idMap[e.to] || e.to,
  }))

  nodes.value = [...nodes.value, ...newNodes]
  edges.value = [...edges.value, ...newEdges]

  const pastedIds = clipboard.nodes.map(n => idMap[n.id]).filter(Boolean)
  selectNodes(pastedIds)

  for (const node of clipboard.nodes) {
    node.x += 40
    node.y += 40
  }
}

// ── Keyboard shortcuts ─────────────────────────────────────────────────────
function onKeyDown(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
    if (e.key === 'Escape') e.target.blur()
    return
  }

  const mod = e.metaKey || e.ctrlKey

  if (mod && e.key === 'z' && !e.shiftKey) {
    e.preventDefault(); undo()
  } else if (mod && e.key === 'z' && e.shiftKey) {
    e.preventDefault(); redo()
  } else if (mod && e.key === 'y') {
    e.preventDefault(); redo()
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && !isPlayback.value) {
    if (selection.type === 'multi') {
      removeSelectedNodes()
    } else if (selection.type === 'node') {
      removeNode(selection.id)
    } else if (selection.type === 'edge') {
      removeEdge(selection.id)
    }
  } else if (e.key === 'Escape') {
    clearSelection()
    showImportModal.value = false
  } else if (mod && e.key === 'o' && !isPlayback.value) {
    e.preventDefault(); handleOpen()
  } else if (mod && e.key === 's' && !e.shiftKey && !isPlayback.value) {
    e.preventDefault(); handleSave()
  } else if (mod && e.key === 's' && e.shiftKey && !isPlayback.value) {
    e.preventDefault(); handleSaveAs()
  } else if (mod && e.key === 'i' && !isPlayback.value) {
    e.preventDefault(); handleImport()
  } else if (mod && e.key === 'c') {
    e.preventDefault(); copySelection()
  } else if (mod && e.key === 'v' && !isPlayback.value) {
    e.preventDefault(); pasteClipboard()
  } else if (mod && e.key === '0') {
    e.preventDefault(); zoomToFit()
  } else if (mod && e.shiftKey && (e.key === 'l' || e.key === 'L')) {
    e.preventDefault(); if (!isPlayback.value) autoLayout()
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('add-action-from-catalog', onCatalogAdd)
  updateYaml()
  await loadManifest()
  if (props.actionLibrary) {
    await setRobot(props.actionLibrary)
  } else if (selectedRobot.value) {
    await setRobot(selectedRobot.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('add-action-from-catalog', onCatalogAdd)
})

// ── Public API (for widget use) ───────────────────────────────────────────
function getYaml() {
  updateYaml()
  return yamlOutput.value
}

function loadExperiment(yamlString) {
  try {
    const result = fromYaml(yamlString)
    snapshot()
    nodes.value = result.nodes
    edges.value = result.edges
    Object.assign(meta, result.meta)
    autoLayoutAll()
    return true
  } catch (e) {
    return false
  }
}

function loadFileContent(yaml, filename, filePath) {
  const label = filename.replace(/\.(yaml|yml)$/, '')
  openTemplateTab(yaml, label)
  setCurrentFileName(filename)
  if (filePath) setCurrentFilePath(filePath)
  markCurrentTabClean()
}

function notifyFileSaved(filename, filePath) {
  setCurrentFileName(filename)
  if (filePath) setCurrentFilePath(filePath)
  markCurrentTabClean()
}

defineExpose({ getYaml, loadExperiment, updateYaml, loadFileContent, notifyFileSaved })
</script>

<template>
  <div class="designer-core" :class="{ dark: darkMode, light: !darkMode, transparent: transparent }">
    <!-- Toolbar -->
    <header v-if="showToolbar" class="toolbar">
      <div class="toolbar-left">
        <span class="app-title">Experiment Designer</span>
        <select
          class="robot-select"
          :value="selectedRobot"
          @change="onRobotChange($event.target.value)"
        >
          <option value="">Builtins only</option>
          <option v-for="r in availableRobots" :key="r.id" :value="r.id">
            {{ r.label }}
          </option>
        </select>
      </div>
      <div class="toolbar-center">
        <button class="tb-btn" @click="handleNew" title="New experiment" :disabled="isPlayback">New</button>
        <button class="tb-btn" @click="handleOpen" title="Open YAML file (Cmd+O)" :disabled="isPlayback">Open</button>
        <RecentMenu v-if="!isPlayback" @select="handleRecentSelect" />
        <TemplateMenu v-if="!isPlayback" ref="templateMenuRef" @select="handleTemplateSelect" @send-event="handleTemplateSendEvent" />
        <button class="tb-btn" @click="handleSave" title="Save (Cmd+S)" :disabled="isPlayback">Save</button>
        <button class="tb-btn" @click="handleSaveAs" title="Save As (Cmd+Shift+S)" :disabled="isPlayback">Save As</button>
        <button class="tb-btn" @click="handleImport" title="Import YAML (Cmd+I)" :disabled="isPlayback">Import</button>
        <input ref="openFileInput" type="file" accept=".yaml,.yml" @change="onOpenFile" hidden />
        <span class="tb-sep"></span>
        <button class="tb-btn" :disabled="!canUndo" @click="undo" title="Undo (Cmd+Z)">Undo</button>
        <button class="tb-btn" :disabled="!canRedo" @click="redo" title="Redo (Cmd+Shift+Z)">Redo</button>
        <span class="tb-sep"></span>
        <button class="tb-btn" @click="toggleLayoutDirection" :title="'Flow direction: ' + layoutDirection">{{ directionIcon }}</button>
        <button class="tb-btn" :class="{ active: columnWrap }" @click="toggleColumnWrap" :disabled="isPlayback" title="Column-wrap: split long chains into columns">&#x25E7;</button>
        <button class="tb-btn" @click="autoLayout" :disabled="isPlayback" title="Auto-layout (Cmd+Shift+L)">Layout</button>
        <button class="tb-btn" @click="zoomToFit" title="Zoom to fit (Cmd+0)">Fit</button>
      </div>
      <div class="toolbar-right">
        <button
          class="tb-btn follow-btn"
          :class="{ active: followMode }"
          @click="toggleFollowMode"
          :title="followMode ? 'Follow mode ON — click to disable' : 'Follow mode OFF — click to enable'"
        >{{ followMode ? '\u25CE' : '\u25CB' }} Follow</button>
        <!-- Playback mode indicator -->
        <div v-if="isPlayback" class="playback-indicator">
          <span class="playback-dot"></span>
          <span class="playback-label">PLAYBACK</span>
        </div>
        <slot name="toolbar-right-extra"></slot>
      </div>
    </header>

    <!-- Playback indicator when toolbar is hidden -->
    <div v-if="!showToolbar && isPlayback" class="playback-bar">
      <span class="playback-dot"></span>
      <span class="playback-label">PLAYBACK</span>
      <button
        class="follow-toggle-mini"
        :class="{ active: followMode }"
        @click="toggleFollowMode"
        :title="followMode ? 'Follow mode ON' : 'Follow mode OFF'"
      >{{ followMode ? '\u25CE' : '\u25CB' }}</button>
    </div>

    <!-- Tab bars: two-bar layout or unified -->
    <template v-if="showExperimentTabs">
      <ExperimentTabBar v-if="!isPlayback" />
      <TabBar v-if="hasOpenExperiment" />
    </template>
    <UnifiedTabBar v-else-if="hasOpenExperiment" :is-playback="isPlayback" />

    <!-- Empty state: no experiments open -->
    <div v-if="!hasOpenExperiment" class="empty-state">
      <div class="empty-content">
        <div class="empty-title">No experiment open</div>
        <div class="empty-hint">
          <button class="empty-action" @click="handleNew">New experiment</button>
          <button class="empty-action" @click="handleOpen">Open file</button>
        </div>
      </div>
    </div>

    <!-- Main content -->
    <div v-else class="main">
      <!-- Catalog panel (collapsible) -->
      <template v-if="!isPlayback">
        <div v-if="!catalogCollapsed" class="panel-wrapper panel-left">
          <ActionCatalog />
        </div>
        <button class="panel-toggle panel-toggle-left" @click="toggleCatalog" :title="catalogCollapsed ? 'Show catalog' : 'Hide catalog'">
          <span class="toggle-icon">{{ catalogCollapsed ? '\u25B8' : '\u25C2' }}</span>
        </button>
      </template>

      <div class="canvas-area">
        <Canvas />
        <YamlPreview
          v-if="showYamlPreview && !isPlayback"
          :yaml="yamlOutput"
          :expanded="yamlExpanded"
          @toggle="yamlExpanded = !yamlExpanded"
        />
      </div>

      <!-- Inspector panel (collapsible) -->
      <template v-if="!isPlayback">
        <button class="panel-toggle panel-toggle-right" @click="toggleInspector" :title="inspectorCollapsed ? 'Show inspector' : 'Hide inspector'">
          <span class="toggle-icon">{{ inspectorCollapsed ? '\u25C2' : '\u25B8' }}</span>
        </button>
        <div v-if="!inspectorCollapsed" class="panel-wrapper panel-right">
          <InspectorPanel />
        </div>
      </template>
    </div>

    <!-- Import Modal -->
    <Teleport to="body">
      <div v-if="showImportModal" class="modal-overlay" @click.self="showImportModal = false">
        <div class="modal" :class="{ dark: darkMode }">
          <h3>Import Experiment YAML</h3>
          <textarea
            v-model="importText"
            placeholder="Paste YAML here..."
            rows="16"
          ></textarea>
          <div class="modal-actions">
            <label class="tb-btn file-label">
              Upload file
              <input type="file" accept=".yaml,.yml" @change="handleImportFile" hidden />
            </label>
            <span style="flex:1"></span>
            <button class="tb-btn" @click="showImportModal = false">Cancel</button>
            <button class="tb-btn primary" @click="doImport">Import</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.designer-core {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  width: 100%;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
}

.designer-core.transparent {
  background: transparent;
}

/* ── Toolbar ────────────────────────────────────────────────────────────── */
.toolbar {
  display: flex;
  align-items: center;
  height: 40px;
  padding: 0 12px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  gap: 8px;
}

.toolbar-left { display: flex; align-items: center; gap: 8px; }
.toolbar-center { display: flex; align-items: center; gap: 4px; flex: 1; justify-content: center; }
.toolbar-right { display: flex; align-items: center; gap: 4px; }

.app-title {
  font-weight: 600;
  font-size: 13px;
  letter-spacing: 0.5px;
}

.tb-btn {
  font-family: inherit;
  font-size: 11px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-surface);
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}
.tb-btn:hover:not(:disabled) { background: var(--bg-hover); }
.tb-btn:disabled { opacity: 0.4; cursor: default; }
.tb-btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.tb-btn.primary:hover { background: var(--accent-dim); }

.tb-sep {
  width: 1px;
  height: 18px;
  background: var(--border);
  margin: 0 4px;
}

.robot-select {
  font-family: inherit;
  font-size: 11px;
  padding: 3px 6px;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  outline: none;
  cursor: pointer;
}

/* ── Main layout ────────────────────────────────────────────────────────── */
.main {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.canvas-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

/* ── Active toggle buttons ─────────────────────────────────────────────── */
.tb-btn.active {
  background: rgba(46, 204, 113, 0.2);
  color: #2ecc71;
  border-color: rgba(46, 204, 113, 0.4);
}
.follow-btn.active {
  background: rgba(46, 204, 113, 0.2);
  color: #2ecc71;
  border-color: rgba(46, 204, 113, 0.4);
}

/* ── Playback indicator ────────────────────────────────────────────────── */
.playback-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  background: rgba(46, 204, 113, 0.15);
  border: 1px solid rgba(46, 204, 113, 0.3);
  border-radius: 4px;
}

.playback-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 24px;
  background: rgba(46, 204, 113, 0.15);
  border-bottom: 1px solid rgba(46, 204, 113, 0.3);
  flex-shrink: 0;
}

.playback-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #2ecc71;
  animation: pulse-dot 1.5s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.playback-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: #2ecc71;
}

.follow-toggle-mini {
  margin-left: 8px;
  padding: 1px 6px;
  font-size: 11px;
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: 3px;
  background: transparent;
  color: #999;
  cursor: pointer;
}
.follow-toggle-mini.active {
  background: rgba(46, 204, 113, 0.2);
  color: #2ecc71;
  border-color: rgba(46, 204, 113, 0.4);
}

/* ── Modal ──────────────────────────────────────────────────────────────── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  width: 560px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.modal.dark { background: #14141f; color: #e0e0e0; }

.modal h3 { font-size: 14px; font-weight: 600; }

.modal textarea {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 10px;
  resize: vertical;
  outline: none;
}
.modal textarea:focus { border-color: var(--accent); }

.modal-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.file-label { cursor: pointer; }

/* ── Collapsible panel wrappers ────────────────────────────────────────── */
.panel-wrapper {
  flex-shrink: 0;
  overflow: hidden;
  min-height: 0;
}

.panel-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  flex-shrink: 0;
  background: var(--bg-surface);
  border: none;
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
  color: var(--text-dim);
  cursor: pointer;
  padding: 0;
  font-family: inherit;
  transition: background 0.15s, color 0.15s;
}
.panel-toggle:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.toggle-icon {
  font-size: 10px;
  line-height: 1;
}

.panel-toggle-left {
  border-left: none;
}
.panel-toggle-right {
  border-right: none;
}

/* ── Empty state ──────────────────────────────────────────────────────── */
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}

.empty-content {
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty-title {
  font-size: 14px;
  color: var(--text-dim);
  font-weight: 500;
}

.empty-hint {
  display: flex;
  gap: 8px;
  justify-content: center;
}

.empty-action {
  font-family: inherit;
  font-size: 12px;
  padding: 6px 16px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-surface);
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.empty-action:hover {
  background: var(--bg-hover);
  border-color: var(--accent);
  color: var(--accent);
}
</style>
