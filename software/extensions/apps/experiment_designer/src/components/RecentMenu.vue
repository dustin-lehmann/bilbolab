<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { recentFiles, loadRecentFiles, openRecentFile } from '../recentFiles.js'

const emit = defineEmits(['select'])

const open = ref(false)
const menuRef = ref(null)

onMounted(() => {
  loadRecentFiles()
  document.addEventListener('click', onClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
})

function onClickOutside(e) {
  if (menuRef.value && !menuRef.value.contains(e.target)) {
    open.value = false
  }
}

function toggle() {
  open.value = !open.value
}

async function onEntryClick(entry) {
  open.value = false
  const result = await openRecentFile(entry)
  if (result) {
    emit('select', result.text, result.name, result.handle)
  } else {
    alert(`Could not reopen "${entry.name}" — file may have been moved or permission was denied.`)
  }
}

function formatTime(ts) {
  const d = new Date(ts)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`
  return d.toLocaleDateString()
}
</script>

<template>
  <div class="recent-menu" ref="menuRef">
    <button
      class="recent-trigger"
      @click="toggle"
      :disabled="recentFiles.length === 0"
      title="Open recent file"
    >
      Recent <span class="caret">&#x25BE;</span>
    </button>

    <div v-if="open && recentFiles.length > 0" class="dropdown">
      <div
        v-for="entry in recentFiles"
        :key="entry.name + entry.timestamp"
        class="menu-item"
        @click="onEntryClick(entry)"
      >
        <span class="entry-name">{{ entry.name }}</span>
        <span class="entry-time">{{ formatTime(entry.timestamp) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.recent-menu {
  position: relative;
  display: inline-block;
}

.recent-trigger {
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
  display: flex;
  align-items: center;
  gap: 4px;
}
.recent-trigger:hover:not(:disabled) { background: var(--bg-hover); }
.recent-trigger:disabled { opacity: 0.4; cursor: default; }

.caret {
  font-size: 9px;
  opacity: 0.7;
}

.dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 2px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  min-width: 220px;
  max-width: 340px;
  padding: 4px 0;
  z-index: 1000;
}

.menu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  gap: 12px;
  color: var(--text);
  transition: background 0.1s;
}

.menu-item:hover {
  background: var(--bg-hover);
}

.entry-name {
  overflow: hidden;
  text-overflow: ellipsis;
}

.entry-time {
  font-size: 10px;
  opacity: 0.4;
  flex-shrink: 0;
}
</style>
