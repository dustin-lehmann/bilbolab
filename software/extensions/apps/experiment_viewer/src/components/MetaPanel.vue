<script setup>
import { ref, computed } from 'vue'
import { experimentMeta, experimentDefinition, experimentData } from '../viewerState.js'

const expandedSections = ref(new Set(['control_config', 'bilbo_config']))

function toggle(section) {
  if (expandedSections.value.has(section)) {
    expandedSections.value.delete(section)
  } else {
    expandedSections.value.add(section)
  }
}

function isExpanded(section) {
  return expandedSections.value.has(section)
}

const sections = computed(() => {
  const meta = experimentMeta.value
  if (!meta) return []
  const result = []

  if (meta.control_config) {
    result.push({ id: 'control_config', label: 'Control Config', data: meta.control_config })
  }
  if (meta.bilbo_config) {
    result.push({ id: 'bilbo_config', label: 'Robot Config', data: meta.bilbo_config })
  }
  if (meta.testbed) {
    result.push({ id: 'testbed', label: 'Testbed', data: meta.testbed })
  }

  const defn = experimentDefinition.value
  if (defn) {
    result.push({ id: 'definition', label: 'Experiment Definition', data: defn })
  }

  // Add any remaining top-level meta keys
  const skip = new Set(['control_config', 'bilbo_config', 'testbed', 'description', 'start_timecode', 'date'])
  for (const [k, v] of Object.entries(meta)) {
    if (!skip.has(k) && v != null && typeof v === 'object') {
      result.push({ id: `meta_${k}`, label: k, data: v })
    }
  }

  return result
})

function formatJson(data) {
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

/** Render a config object as a flat key-value table (1 level deep). */
function flatEntries(obj) {
  if (!obj || typeof obj !== 'object') return []
  return Object.entries(obj).map(([k, v]) => {
    const isComplex = v != null && typeof v === 'object'
    return {
      key: k,
      value: isComplex ? JSON.stringify(v) : String(v),
      isComplex,
    }
  })
}
</script>

<template>
  <div class="meta-panel">
    <div class="meta-header">
      <span class="section-title">Configuration &amp; Metadata</span>
    </div>

    <div class="meta-scroll">
      <div v-for="section in sections" :key="section.id" class="config-section">
        <div class="config-header" @click="toggle(section.id)">
          <span class="expand-icon">{{ isExpanded(section.id) ? '▾' : '▸' }}</span>
          <span class="config-label">{{ section.label }}</span>
        </div>
        <div v-if="isExpanded(section.id)" class="config-body">
          <table class="kv-table">
            <tr v-for="entry in flatEntries(section.data)" :key="entry.key">
              <td class="kv-key">{{ entry.key }}</td>
              <td class="kv-val" :class="{ complex: entry.isComplex }">{{ entry.value }}</td>
            </tr>
          </table>
          <details class="raw-json">
            <summary>Raw JSON</summary>
            <pre class="json-pre">{{ formatJson(section.data) }}</pre>
          </details>
        </div>
      </div>

      <div v-if="sections.length === 0" class="meta-empty">No metadata available.</div>
    </div>
  </div>
</template>

<style scoped>
.meta-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.meta-header {
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

.meta-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
}

.config-section {
  margin-bottom: 4px;
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}

.config-header {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  cursor: pointer;
  background: var(--bg-surface);
  user-select: none;
}
.config-header:hover { background: var(--bg-hover); }

.expand-icon {
  font-size: 10px;
  width: 12px;
  text-align: center;
  flex-shrink: 0;
  color: var(--text-dim);
}

.config-label {
  font-size: 11px;
  font-weight: 500;
}

.config-body {
  padding: 6px 10px;
  border-top: 1px solid var(--border);
}

.kv-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 10px;
}

.kv-table td {
  padding: 2px 6px;
  vertical-align: top;
}

.kv-key {
  color: var(--text-dim);
  white-space: nowrap;
  width: 1%;
  padding-right: 16px;
}

.kv-val {
  word-break: break-all;
}

.kv-val.complex {
  font-size: 9px;
  color: var(--text-dim);
  max-width: 500px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.raw-json {
  margin-top: 8px;
  font-size: 10px;
}

.raw-json summary {
  cursor: pointer;
  color: var(--text-dim);
  padding: 2px 0;
}
.raw-json summary:hover { color: var(--accent); }

.json-pre {
  font-family: inherit;
  font-size: 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 6px 8px;
  overflow: auto;
  max-height: 400px;
  white-space: pre-wrap;
  word-break: break-all;
  margin-top: 4px;
}

.meta-empty {
  padding: 20px;
  text-align: center;
  color: var(--text-dim);
}
</style>
