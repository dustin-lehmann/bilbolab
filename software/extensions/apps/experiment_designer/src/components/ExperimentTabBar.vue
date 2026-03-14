<script setup>
import { computed } from 'vue'
import { meta } from '../graphState.js'
import {
  experimentTabs, activeExperimentTabId,
  switchExperimentTab, closeExperimentTab, newExperimentTab, renameExperimentTab,
} from '../experimentTabs.js'

function tabDisplayLabel(tab) {
  let label = tab.label
  if (tab.id === activeExperimentTabId.value) {
    label = meta.id || tab.label
  } else {
    try {
      const state = JSON.parse(tab.stateSnapshot)
      label = state.meta?.id || tab.label
    } catch { /* fallback */ }
  }
  if (tab.fileName) label = `${label} (${tab.fileName})`
  return label
}

function onTabClick(tabId) {
  switchExperimentTab(tabId)
}

function onTabClose(e, tabId) {
  e.stopPropagation()
  closeExperimentTab(tabId)
}

function onTabDblClick(tab) {
  const newLabel = prompt('Rename tab:', tab.label)
  if (newLabel && newLabel.trim()) {
    renameExperimentTab(tab.id, newLabel.trim())
  }
}

function onNew() {
  newExperimentTab()
}
</script>

<template>
  <div class="experiment-tab-bar">
    <div
      v-for="tab in experimentTabs"
      :key="tab.id"
      class="exp-tab"
      :class="{ active: tab.id === activeExperimentTabId }"
      @click="onTabClick(tab.id)"
      @dblclick="onTabDblClick(tab)"
    >
      <span class="exp-tab-label">{{ tabDisplayLabel(tab) }}{{ tab.dirty ? ' *' : '' }}</span>
      <button
        class="exp-tab-close"
        @click="onTabClose($event, tab.id)"
        title="Close experiment"
      >&times;</button>
    </div>
    <button class="exp-tab-new" @click="onNew" title="New experiment">+</button>
  </div>
</template>

<style scoped>
.experiment-tab-bar {
  display: flex;
  align-items: stretch;
  height: 30px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  overflow-x: auto;
  gap: 0;
  padding-left: 4px;
}

.exp-tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 12px;
  font-size: 11px;
  color: var(--text-dim);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  border-right: 1px solid var(--border);
  transition: background 0.1s, color 0.1s, border-color 0.1s;
  white-space: nowrap;
  user-select: none;
  background: var(--bg-surface);
}

.exp-tab:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.exp-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  background: var(--bg);
}

.exp-tab-label {
  font-weight: 500;
}

.exp-tab-close {
  font-size: 13px;
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  padding: 0;
  line-height: 1;
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 2px;
}
.exp-tab-close:hover {
  background: var(--bg-hover);
  color: #e74c3c;
}

.exp-tab-new {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  font-size: 16px;
  font-weight: 300;
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  font-family: inherit;
  flex-shrink: 0;
}
.exp-tab-new:hover {
  color: var(--accent);
  background: var(--bg-hover);
}
</style>
