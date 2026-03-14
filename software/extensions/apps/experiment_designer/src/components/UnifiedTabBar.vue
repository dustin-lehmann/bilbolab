<script setup>
import {
  experimentTabs, activeExperimentTabId, unifiedTabList,
  switchToExperimentContainer, closeExperimentTab, closeContainerTabForExperiment,
  newExperimentTab, renameExperimentTab,
} from '../experimentTabs.js'

defineProps({
  isPlayback: { type: Boolean, default: false },
})

function onTabClick(entry) {
  switchToExperimentContainer(entry.expTabId, entry.containerTabId)
}

function onTabClose(e, entry) {
  e.stopPropagation()
  if (entry.isRoot) {
    closeExperimentTab(entry.expTabId)
  } else {
    closeContainerTabForExperiment(entry.expTabId, entry.containerTabId)
  }
}

function onTabDblClick(entry) {
  if (!entry.isRoot) return
  const newLabel = prompt('Rename experiment:', entry.expLabel)
  if (newLabel && newLabel.trim()) {
    renameExperimentTab(entry.expTabId, newLabel.trim())
  }
}

function onNew() {
  newExperimentTab()
}

/**
 * Check if this entry is the first tab of a new experiment group
 * (used for visual separators).
 */
function isGroupStart(index) {
  if (index === 0) return false
  const list = unifiedTabList.value
  return list[index].expTabId !== list[index - 1].expTabId
}
</script>

<template>
  <div class="unified-tab-bar">
    <template v-for="(entry, idx) in unifiedTabList" :key="`${entry.expTabId}_${entry.containerTabId}`">
      <!-- Group separator between experiments -->
      <div v-if="isGroupStart(idx)" class="tab-separator"></div>

      <div
        class="tab"
        :class="{
          active: entry.isActive,
          'is-root': entry.isRoot,
        }"
        @click="onTabClick(entry)"
        @dblclick="onTabDblClick(entry)"
        :title="entry.label"
      >
        <span class="tab-label" :class="{ 'file-not-found': entry.fileNotFound }">{{ entry.label }}{{ entry.fileNotFound ? ' (not found)' : '' }}{{ entry.isRoot && entry.dirty ? ' *' : '' }}</span>
        <!-- Close button -->
        <button
          v-if="!isPlayback"
          class="tab-close"
          @click="onTabClose($event, entry)"
          :title="entry.isRoot ? 'Close experiment' : 'Close tab'"
        >&times;</button>
      </div>
    </template>

    <!-- New experiment button -->
    <button v-if="!isPlayback" class="tab-new" @click="onNew" title="New experiment">+</button>
  </div>
</template>

<style scoped>
.unified-tab-bar {
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

.tab-separator {
  width: 8px;
  flex-shrink: 0;
  background: var(--bg);
  position: relative;
}
.tab-separator::after {
  content: '';
  position: absolute;
  left: 3px;
  top: 6px;
  bottom: 6px;
  width: 1px;
  background: var(--border);
}

.tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 10px;
  font-size: 10px;
  color: var(--text-dim);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  border-right: 1px solid var(--border);
  transition: background 0.1s, color 0.1s, border-color 0.1s;
  white-space: nowrap;
  user-select: none;
  background: var(--bg-surface);
}

.tab:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  background: var(--bg);
}

.tab.is-root {
  font-weight: 600;
}

.tab-label {
  font-weight: inherit;
}

.tab-label.file-not-found {
  color: #e74c3c;
}

.tab-close {
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
.tab-close:hover {
  background: var(--bg-hover);
  color: #e74c3c;
}

.tab-new {
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
.tab-new:hover {
  color: var(--accent);
  background: var(--bg-hover);
}
</style>
