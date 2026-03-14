<script setup>
import { ref, computed } from 'vue'
import { actionList, selectedActionId, selectAction, experimentData } from '../viewerState.js'
import { fmtTime, fmtNum, getActionColor, STATUS_COLORS } from '../utils/dataAccess.js'

const expandedId = ref(null)

function toggleExpand(actionId) {
  expandedId.value = expandedId.value === actionId ? null : actionId
}

function formatParams(params) {
  if (!params) return '—'
  const entries = Object.entries(params).filter(([k]) => k !== 'started')
  if (entries.length === 0) return '—'
  return entries.map(([k, v]) => {
    if (typeof v === 'object' && v !== null) return `${k}: {...}`
    return `${k}: ${JSON.stringify(v)}`
  }).join(', ')
}

function formatData(data) {
  if (!data) return null
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

function statusColor(status) {
  return STATUS_COLORS[status] || '#888'
}
</script>

<template>
  <div class="action-table">
    <div class="table-header-bar">
      <span class="section-title">Actions ({{ actionList.length }})</span>
    </div>

    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th class="col-id">ID</th>
            <th class="col-type">Type</th>
            <th class="col-status">Status</th>
            <th class="col-time">Start</th>
            <th class="col-time">End</th>
            <th class="col-time">Duration</th>
            <th class="col-params">Parameters</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="action in actionList" :key="action.id">
            <tr
              class="action-row"
              :class="{
                selected: selectedActionId === action.id,
                expanded: expandedId === action.id,
                'has-error': action.status === 'error',
              }"
              @click="selectAction(action.id)"
            >
              <td class="col-id">
                <span class="action-dot" :style="{ background: getActionColor(action.action_type) }"></span>
                {{ action.id }}
              </td>
              <td class="col-type">{{ action.action_type }}</td>
              <td class="col-status">
                <span class="status-dot" :style="{ background: statusColor(action.status) }"></span>
                {{ action.status }}
              </td>
              <td class="col-time">{{ fmtTime(action.start_time ?? 0) }}</td>
              <td class="col-time">{{ fmtTime(action.end_time ?? 0) }}</td>
              <td class="col-time">{{ fmtTime((action.end_time ?? 0) - (action.start_time ?? 0)) }}</td>
              <td class="col-params">
                <span class="params-summary">{{ formatParams(action.parameters) }}</span>
                <button
                  v-if="action.data || action.error_message || action.sub_actions"
                  class="expand-btn"
                  @click.stop="toggleExpand(action.id)"
                >{{ expandedId === action.id ? '▾' : '▸' }}</button>
              </td>
            </tr>
            <tr v-if="expandedId === action.id" class="detail-row">
              <td colspan="7">
                <div class="detail-content">
                  <div v-if="action.error_message" class="detail-section error-section">
                    <div class="detail-label">Error</div>
                    <div class="detail-value error-text">{{ action.error_message }}</div>
                  </div>
                  <div v-if="action.parameters" class="detail-section">
                    <div class="detail-label">Parameters</div>
                    <pre class="detail-pre">{{ JSON.stringify(action.parameters, null, 2) }}</pre>
                  </div>
                  <div v-if="action.data" class="detail-section">
                    <div class="detail-label">Data</div>
                    <pre class="detail-pre">{{ formatData(action.data) }}</pre>
                  </div>
                  <div v-if="action.sub_actions" class="detail-section">
                    <div class="detail-label">Sub-Actions</div>
                    <pre class="detail-pre">{{ JSON.stringify(action.sub_actions, null, 2) }}</pre>
                  </div>
                  <div v-if="action.label" class="detail-section">
                    <div class="detail-label">Label</div>
                    <div class="detail-value">{{ action.label }}</div>
                  </div>
                  <div v-if="action.meta" class="detail-section">
                    <div class="detail-label">Meta</div>
                    <pre class="detail-pre">{{ JSON.stringify(action.meta, null, 2) }}</pre>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.action-table {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.table-header-bar {
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

.table-scroll {
  flex: 1;
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

thead {
  position: sticky;
  top: 0;
  z-index: 1;
}

th {
  text-align: left;
  padding: 5px 8px;
  background: var(--bg-surface);
  color: var(--text-dim);
  font-weight: 500;
  font-size: 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

td {
  padding: 4px 8px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.action-row {
  cursor: pointer;
}
.action-row:hover { background: var(--bg-hover); }
.action-row.selected { background: var(--bg-hover); }
.action-row.has-error td { color: var(--error); }

.col-id { white-space: nowrap; }
.col-type { white-space: nowrap; }
.col-status { white-space: nowrap; }
.col-time { white-space: nowrap; font-variant-numeric: tabular-nums; }
.col-params { max-width: 400px; }

.action-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}

.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}

.params-summary {
  color: var(--text-dim);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 350px;
  display: inline-block;
  vertical-align: middle;
}

.expand-btn {
  font-family: inherit;
  font-size: 10px;
  padding: 0 4px;
  border: none;
  background: none;
  color: var(--accent);
  cursor: pointer;
  vertical-align: middle;
  margin-left: 4px;
}

.detail-row td {
  padding: 0;
  background: var(--bg-surface);
}

.detail-content {
  padding: 8px 12px 8px 32px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
}

.detail-value { font-size: 11px; }

.detail-pre {
  font-family: inherit;
  font-size: 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 6px 8px;
  overflow-x: auto;
  max-height: 200px;
  white-space: pre-wrap;
  word-break: break-all;
}

.error-text {
  color: var(--error);
  font-weight: 500;
}
</style>
