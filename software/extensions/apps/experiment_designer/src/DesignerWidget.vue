<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import DesignerCore from './DesignerCore.vue'
import {
  mode, setMode, setActionState, clearActionStates, enableAutoSave,
  initDefaultGraph, serializeFullState, loadFullState, setLayoutDirection,
  nodes, edges, meta,
  addNodeDirect, removeNodeDirect, updateNodePosition, updateNodeParams,
  updateNodeField, renameNode, moveNodeToContainer, removeNodeFromContainer,
  addEdgeDirect, removeEdgeDirect, updateEdgeMapping,
  updateMeta, addVariable, removeVariable, updateVariable,
  addEvent, removeEvent, loadStateFromMutation,
} from './graphState.js'
import { initBridge, applyRemoteMutation } from './mutationBridge.js'
import { initTabs, experimentTabs, activeExperimentTabId, withSuppressedDirty, restoreTabsSync, getCurrentFilePath } from './experimentTabs.js'
import { toYaml, fromYaml } from './serializer.js'

const props = defineProps({
  darkMode: { type: Boolean, default: true },
  showToolbar: { type: Boolean, default: false },
  showYamlPreview: { type: Boolean, default: false },
  showExperimentTabs: { type: Boolean, default: false },
  readOnly: { type: Boolean, default: false },
  actionLibrary: { type: String, default: null },
  transparent: { type: Boolean, default: false },
  instanceId: { type: String, default: null },
  onPlay: { type: Function, default: null },
  onStop: { type: Function, default: null },
  onMutation: { type: Function, default: null },
})

const emit = defineEmits(['play', 'stop'])

const coreRef = ref(null)
const isPlayback = computed(() => mode.value === 'playback')
const isEdit = computed(() => mode.value === 'edit')

// Graph operations object passed to applyRemoteMutation
const graphOps = {
  addNodeDirect, removeNodeDirect, updateNodePosition, updateNodeParams,
  updateNodeField, renameNode, moveNodeToContainer, removeNodeFromContainer,
  addEdgeDirect, removeEdgeDirect, updateEdgeMapping,
  updateMeta, addVariable, removeVariable, updateVariable,
  addEvent, removeEvent, loadStateFromMutation,
}

onMounted(() => {
  // Disable auto-save in widget mode
  enableAutoSave.value = false
  // Default to horizontal layout in widget mode
  if (!localStorage.getItem('experiment-designer-direction')) {
    setLayoutDirection('horizontal')
  }

  // Initialize mutation bridge
  const id = props.instanceId || `widget_${Math.random().toString(36).slice(2, 10)}`
  initBridge(id, (mutation) => {
    if (props.onMutation) props.onMutation(mutation)
  })

  // Restore tabs from one of three sources (in priority order):
  // 1. Module-level ref — survives widget destroy/recreate (robot reconnect)
  // 2. localStorage — survives page refresh
  // 3. Fresh default graph — first-ever load
  if (experimentTabs.value.length > 0) {
    // Case 1: Re-mount after widget destroy (e.g. robot reconnect).
    // Module-level experimentTabs still populated — restore active tab's graph.
    const tab = experimentTabs.value.find(t => t.id === activeExperimentTabId.value)
                || experimentTabs.value[0]
    if (tab?.stateSnapshot) {
      withSuppressedDirty(() => {
        loadFullState(tab.stateSnapshot)
        activeExperimentTabId.value = tab.id
      })
    } else {
      initDefaultGraph()
    }
  } else if (restoreTabsSync()) {
    // Case 2: Page refresh — restored from localStorage.
  } else {
    // Case 3: First load — start with a blank experiment.
    initDefaultGraph()
    initTabs()
  }
})

// ── Play/Stop ──────────────────────────────────────────────────────────────
function onPlayClick() {
  const yaml = coreRef.value?.getYaml() || ''
  const filePath = getCurrentFilePath()
  if (props.onPlay) props.onPlay(yaml, filePath)
  else emit('play', yaml, filePath)
}

function onStopClick() {
  if (props.onStop) props.onStop()
  else emit('stop')
}

// ── Public API (exposed for JS widget wrapper) ─────────────────────────────
function loadExperiment(yamlString) {
  // Hash the incoming YAML's canonical form and compare with the current state.
  // If they produce the same canonical YAML, skip the reload to preserve
  // the user's zoom/pan/layout.
  try {
    const incoming = fromYaml(yamlString)
    const incomingYaml = toYaml(incoming.nodes, incoming.edges, incoming.meta)
    const currentYaml = coreRef.value?.getYaml() || ''
    if (incomingYaml === currentYaml) return true
  } catch {
    // Parse failed — fall through to normal load
  }
  return coreRef.value?.loadExperiment(yamlString) ?? false
}

function getYaml() {
  return coreRef.value?.getYaml() ?? ''
}

function setDesignerMode(m) {
  setMode(m)
}

function setDesignerActionState(actionId, state) {
  setActionState(actionId, state)
}

function clearDesignerActionStates() {
  clearActionStates()
}

function getFullState() {
  return serializeFullState()
}

function restoreFullState(stateJson) {
  return loadFullState(stateJson)
}

function setDesignerDarkMode(dark) {
  // Handled via prop reactivity
}

function applyRemoteMutationFn(mutation) {
  applyRemoteMutation(mutation, graphOps)
}

function applyFullState(stateData) {
  loadStateFromMutation(stateData)
}

function loadFileContentFn(yaml, filename, filePath) {
  coreRef.value?.loadFileContent(yaml, filename, filePath)
}

function notifyFileSavedFn(filename, filePath) {
  coreRef.value?.notifyFileSaved(filename, filePath)
}

defineExpose({
  loadExperiment,
  getYaml,
  getFullState,
  restoreFullState,
  setMode: setDesignerMode,
  setActionState: setDesignerActionState,
  clearActionStates: clearDesignerActionStates,
  setDarkMode: setDesignerDarkMode,
  applyRemoteMutation: applyRemoteMutationFn,
  applyFullState,
  loadFileContent: loadFileContentFn,
  notifyFileSaved: notifyFileSavedFn,
  hasRestoredTabs: () => experimentTabs.value.length > 0,
})
</script>

<template>
  <div class="designer-widget" :class="{ dark: darkMode, light: !darkMode, transparent: transparent }">
    <DesignerCore
      ref="coreRef"
      :dark-mode="darkMode"
      :show-toolbar="showToolbar"
      :show-yaml-preview="showYamlPreview"
      :show-experiment-tabs="showExperimentTabs"
      :read-only="readOnly"
      :action-library="actionLibrary"
      :transparent="transparent"
      :initial-mode="isPlayback ? 'playback' : 'edit'"
      :delegate-file-ops="true"
    />

    <!-- Play/Stop control bar at bottom (hidden in read-only mode) -->
    <div v-if="!readOnly" class="control-bar">
      <button
        class="ctrl-btn play-btn"
        :disabled="isPlayback"
        @click="onPlayClick"
        title="Run experiment"
      >&#9654; Play</button>
      <button
        class="ctrl-btn stop-btn"
        :disabled="isEdit"
        @click="onStopClick"
        title="Stop experiment"
      >&#9632; Stop</button>
    </div>
  </div>
</template>

<style scoped>
/* CSS variable definitions — needed when embedded in GUI (no App.vue :root) */
.designer-widget.dark {
  --bg: #0a0a0f;
  --bg-surface: #14141f;
  --bg-hover: #1e1e2e;
  --border: #2a2a3a;
  --text: #e0e0e0;
  --text-dim: #888;
  --accent: #45aaf2;
  --accent-dim: #2d7ab8;
  --container-bg: rgba(255, 255, 255, 0.03);
}

.designer-widget.light {
  --bg: #f0f0f5;
  --bg-surface: #ffffff;
  --bg-hover: #e8e8f0;
  --border: #d0d0da;
  --text: #1a1a2e;
  --text-dim: #666;
  --accent: #2d7ab8;
  --accent-dim: #1a5a8a;
  --container-bg: rgba(0, 0, 0, 0.03);
}

.designer-widget {
  display: flex;
  flex-direction: column;
  width: 100%;
  flex: 1;
  min-height: 0;
  background: var(--bg);
  color: var(--text);
  overflow: hidden;
  font-family: 'JetBrains Mono', monospace;
}

/* Transparent mode — let the host GUI background show through */
.designer-widget.transparent {
  --bg: transparent;
  --bg-surface: rgba(255, 255, 255, 0.04);
  --bg-hover: rgba(255, 255, 255, 0.08);
  --border: rgba(255, 255, 255, 0.1);
  --container-bg: rgba(255, 255, 255, 0.04);
}
.designer-widget.transparent.light {
  --bg: transparent;
  --bg-surface: rgba(0, 0, 0, 0.04);
  --bg-hover: rgba(0, 0, 0, 0.08);
  --border: rgba(0, 0, 0, 0.1);
  --container-bg: rgba(0, 0, 0, 0.04);
}

.control-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--bg-surface);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.ctrl-btn {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  padding: 4px 14px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-surface);
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.ctrl-btn:hover:not(:disabled) { background: var(--bg-hover); }
.ctrl-btn:disabled { opacity: 0.35; cursor: default; }

.play-btn:not(:disabled) {
  border-color: #2ecc71;
  color: #2ecc71;
}
.play-btn:not(:disabled):hover {
  background: rgba(46, 204, 113, 0.1);
}

.stop-btn:not(:disabled) {
  border-color: #e74c3c;
  color: #e74c3c;
}
.stop-btn:not(:disabled):hover {
  background: rgba(231, 76, 60, 0.1);
}
</style>
