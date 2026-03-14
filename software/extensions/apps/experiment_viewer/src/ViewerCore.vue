<script setup>
import { ref, computed } from 'vue'
import {
  experimentData, fileName, experimentId, experimentStatus, duration, sampleCount,
  experimentMeta, actionList, selectedActionId, loadExperiment, clearExperiment
} from './viewerState.js'
import { fmtTime, fmtNum } from './utils/dataAccess.js'
import OverviewPanel from './components/OverviewPanel.vue'
import ActionTimeline from './components/ActionTimeline.vue'
import ActionTable from './components/ActionTable.vue'
import SamplePlotter from './components/SamplePlotter.vue'
import LogViewer from './components/LogViewer.vue'
import MetaPanel from './components/MetaPanel.vue'

const props = defineProps({
  darkMode: { type: Boolean, default: true },
  transparent: { type: Boolean, default: false },
})

const activeTab = ref('plot')
const isDraggingOver = ref(false)

const tabs = [
  { id: 'plot', label: 'Sample Plotter' },
  { id: 'actions', label: 'Actions' },
  { id: 'logs', label: 'Logs' },
  { id: 'meta', label: 'Config / Meta' },
]

const hasData = computed(() => experimentData.value != null)

// ── File loading ─────────────────────────────────────────────────────────────

async function openFile() {
  try {
    const [handle] = await window.showOpenFilePicker({
      types: [{ description: 'Experiment Results', accept: { 'application/json': ['.json'] } }],
      multiple: false
    })
    const file = await handle.getFile()
    await loadFromFile(file)
  } catch (e) {
    if (e.name !== 'AbortError') console.error('Failed to open file:', e)
  }
}

async function loadFromFile(file) {
  try {
    const text = await file.text()
    const data = JSON.parse(text)
    if (!data.samples && !data.actions && !data.action_data) {
      alert('This does not look like an experiment result file.')
      return
    }
    loadExperiment(data, file.name)
  } catch (e) {
    console.error('Failed to parse file:', e)
    alert('Failed to parse JSON file: ' + e.message)
  }
}

function onDragOver(e) {
  e.preventDefault()
  isDraggingOver.value = true
}

function onDragLeave() {
  isDraggingOver.value = false
}

async function onDrop(e) {
  e.preventDefault()
  isDraggingOver.value = false
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    await loadFromFile(files[0])
  }
}
</script>

<template>
  <div
    class="viewer-core"
    :class="{ dark: darkMode, light: !darkMode, transparent, 'drag-over': isDraggingOver }"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <!-- Toolbar -->
    <div class="toolbar">
      <div class="toolbar-left">
        <span class="toolbar-title">Experiment Viewer</span>
        <button class="btn" @click="openFile">Open File</button>
        <span v-if="fileName" class="file-name" :title="fileName">{{ fileName }}</span>
      </div>
      <div class="toolbar-center" v-if="hasData">
        <div class="tabs">
          <button
            v-for="tab in tabs" :key="tab.id"
            class="tab-btn" :class="{ active: activeTab === tab.id }"
            @click="activeTab = tab.id"
          >{{ tab.label }}</button>
        </div>
      </div>
      <div class="toolbar-right">
        <slot name="toolbar-right-extra" />
      </div>
    </div>

    <!-- Content -->
    <div class="content" v-if="hasData">
      <!-- Left sidebar: overview + timeline -->
      <div class="sidebar">
        <OverviewPanel />
        <ActionTimeline />
      </div>

      <!-- Main area: tabbed panels -->
      <div class="main-panel">
        <SamplePlotter v-show="activeTab === 'plot'" />
        <ActionTable v-show="activeTab === 'actions'" />
        <LogViewer v-show="activeTab === 'logs'" />
        <MetaPanel v-show="activeTab === 'meta'" />
      </div>
    </div>

    <!-- Empty state -->
    <div class="empty-state" v-else>
      <div class="empty-content">
        <div class="empty-icon">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
        </div>
        <div class="empty-title">Open an Experiment Result</div>
        <div class="empty-subtitle">
          Drop a <code>.json</code> experiment result file here, or click the button below.
        </div>
        <button class="btn btn-primary" @click="openFile">Open File</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.viewer-core {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg);
  color: var(--text);
  font-size: 12px;
}
.viewer-core.transparent { background: transparent; }
.viewer-core.drag-over { outline: 2px dashed var(--accent); outline-offset: -2px; }

/* ── Toolbar ───────────────────────────────────────────────────────────── */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
  min-height: 34px;
  gap: 12px;
  flex-shrink: 0;
}
.toolbar-left, .toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.toolbar-center { display: flex; align-items: center; }
.toolbar-title { font-weight: 600; font-size: 12px; color: var(--text-dim); }
.file-name {
  font-size: 11px;
  color: var(--accent);
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Buttons ───────────────────────────────────────────────────────────── */
.btn {
  font-family: inherit;
  font-size: 11px;
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-surface);
  color: var(--text);
  cursor: pointer;
  white-space: nowrap;
}
.btn:hover { background: var(--bg-hover); border-color: var(--accent-dim); }
.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.btn-primary:hover { opacity: 0.85; }

/* ── Tabs ──────────────────────────────────────────────────────────────── */
.tabs { display: flex; gap: 2px; }
.tab-btn {
  font-family: inherit;
  font-size: 11px;
  padding: 3px 12px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
}
.tab-btn:hover { background: var(--bg-hover); color: var(--text); }
.tab-btn.active { background: var(--bg-hover); color: var(--accent); }

/* ── Layout ────────────────────────────────────────────────────────────── */
.content {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.sidebar {
  width: 280px;
  min-width: 220px;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.main-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Empty state ───────────────────────────────────────────────────────── */
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.empty-content {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.empty-icon { color: var(--text-dim); opacity: 0.4; }
.empty-title { font-size: 16px; font-weight: 600; }
.empty-subtitle { font-size: 12px; color: var(--text-dim); max-width: 350px; }
.empty-subtitle code {
  background: var(--bg-surface);
  padding: 1px 4px;
  border-radius: 3px;
  font-family: inherit;
}
</style>
