<script setup>
import { openTabs, activeTab, switchTab, closeContainerTab } from '../graphState.js'

function onTabClick(tabId) {
  switchTab(tabId)
}

function onTabClose(e, tabId) {
  e.stopPropagation()
  closeContainerTab(tabId)
}
</script>

<template>
  <div class="tab-bar">
    <div
      v-for="tab in openTabs"
      :key="tab.id"
      class="tab"
      :class="{ active: tab.id === activeTab }"
      @click="onTabClick(tab.id)"
    >
      <span class="tab-label">{{ tab.label }}</span>
      <button
        v-if="tab.id !== 'root'"
        class="tab-close"
        @click="onTabClose($event, tab.id)"
        title="Close tab"
      >&times;</button>
    </div>
  </div>
</template>

<style scoped>
.tab-bar {
  display: flex;
  align-items: stretch;
  height: 28px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  overflow-x: auto;
  gap: 1px;
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
  transition: background 0.1s, color 0.1s, border-color 0.1s;
  white-space: nowrap;
  user-select: none;
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

.tab-label {
  font-weight: 500;
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
</style>
