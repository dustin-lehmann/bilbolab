<script setup>
import { ref, computed } from 'vue'
import { logs } from '../viewerState.js'

const levelFilter = ref('all')

const levels = [
  { id: 'all', label: 'All' },
  { id: 'debug', label: 'DEBUG', level: 10 },
  { id: 'info', label: 'INFO', level: 20 },
  { id: 'warning', label: 'WARN', level: 30 },
  { id: 'error', label: 'ERROR', level: 40 },
]

const filteredLogs = computed(() => {
  const all = logs.value
  if (levelFilter.value === 'all') return all
  const lvl = levels.find(l => l.id === levelFilter.value)
  if (!lvl) return all
  return all.filter(l => (l.level ?? 20) >= lvl.level)
})

function levelClass(level) {
  if (level >= 40) return 'level-error'
  if (level >= 30) return 'level-warning'
  if (level >= 20) return 'level-info'
  return 'level-debug'
}

function levelLabel(level) {
  if (level >= 40) return 'ERR'
  if (level >= 30) return 'WRN'
  if (level >= 20) return 'INF'
  return 'DBG'
}
</script>

<template>
  <div class="log-viewer">
    <div class="log-header">
      <span class="section-title">Logs ({{ filteredLogs.length }})</span>
      <div class="level-filters">
        <button
          v-for="l in levels" :key="l.id"
          class="filter-btn"
          :class="{ active: levelFilter === l.id }"
          @click="levelFilter = l.id"
        >{{ l.label }}</button>
      </div>
    </div>

    <div class="log-scroll">
      <div
        v-for="(log, i) in filteredLogs" :key="i"
        class="log-entry"
        :class="levelClass(log.level)"
      >
        <span class="log-level">{{ levelLabel(log.level) }}</span>
        <span v-if="log.tick != null" class="log-tick">t{{ log.tick }}</span>
        <span class="log-logger" v-if="log.logger">{{ log.logger }}</span>
        <span class="log-msg">{{ log.message }}</span>
      </div>
      <div v-if="filteredLogs.length === 0" class="log-empty">No log entries.</div>
    </div>
  </div>
</template>

<style scoped>
.log-viewer {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.section-title {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-dim);
}

.level-filters {
  display: flex;
  gap: 2px;
}

.filter-btn {
  font-family: inherit;
  font-size: 10px;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
}
.filter-btn:hover { border-color: var(--accent-dim); }
.filter-btn.active {
  background: var(--bg-hover);
  color: var(--accent);
  border-color: var(--accent-dim);
}

.log-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
  font-size: 11px;
}

.log-entry {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 2px 12px;
  font-family: 'JetBrains Mono', monospace;
}
.log-entry:hover { background: var(--bg-hover); }

.log-level {
  font-size: 9px;
  font-weight: 600;
  flex-shrink: 0;
  width: 28px;
}
.level-debug .log-level { color: var(--text-dim); }
.level-info .log-level { color: var(--accent); }
.level-warning .log-level { color: var(--warning); }
.level-error .log-level { color: var(--error); }

.log-tick {
  font-size: 10px;
  color: var(--text-dim);
  flex-shrink: 0;
  min-width: 40px;
}

.log-logger {
  font-size: 10px;
  color: var(--text-dim);
  flex-shrink: 0;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-msg {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-word;
}
.level-error .log-msg { color: var(--error); }
.level-warning .log-msg { color: var(--warning); }

.log-empty {
  padding: 20px;
  text-align: center;
  color: var(--text-dim);
}
</style>
