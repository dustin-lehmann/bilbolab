<script setup>
import { computed } from 'vue'
import {
  experimentId, experimentStatus, experimentMeta, duration, sampleCount,
  actionList, experimentData, fileName
} from '../viewerState.js'
import { fmtTime, STATUS_COLORS } from '../utils/dataAccess.js'

const statusColor = computed(() => STATUS_COLORS[experimentStatus.value] || '#888')

const description = computed(() => {
  return experimentMeta.value?.description
    || experimentData.value?.definition?.description
    || ''
})

const date = computed(() => experimentMeta.value?.date || '—')

const robotId = computed(() => {
  return experimentMeta.value?.bilbo_config?.general?.id || '—'
})

const completedActions = computed(() => actionList.value.filter(a => a.status === 'finished' || a.status === 'completed').length)
const errorActions = computed(() => actionList.value.filter(a => a.status === 'error').length)
const errorMessage = computed(() => experimentData.value?.error_message || null)
</script>

<template>
  <div class="overview-panel">
    <div class="section-title">Overview</div>

    <div class="info-grid">
      <div class="info-row">
        <span class="info-label">ID</span>
        <span class="info-value id-value">{{ experimentId }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Status</span>
        <span class="info-value">
          <span class="status-badge" :style="{ background: statusColor }">
            {{ experimentStatus }}
          </span>
        </span>
      </div>
      <div class="info-row" v-if="description">
        <span class="info-label">Description</span>
        <span class="info-value desc-value">{{ description }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Robot</span>
        <span class="info-value">{{ robotId }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Date</span>
        <span class="info-value">{{ date }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Duration</span>
        <span class="info-value">{{ fmtTime(duration) }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Samples</span>
        <span class="info-value">{{ sampleCount.toLocaleString() }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Actions</span>
        <span class="info-value">
          {{ completedActions }}/{{ actionList.length }}
          <span v-if="errorActions > 0" class="error-count">({{ errorActions }} err)</span>
        </span>
      </div>
    </div>

    <div v-if="errorMessage" class="error-box">
      {{ errorMessage }}
    </div>
  </div>
</template>

<style scoped>
.overview-panel {
  padding: 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.section-title {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-dim);
  margin-bottom: 8px;
}

.info-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}

.info-label {
  font-size: 11px;
  color: var(--text-dim);
  flex-shrink: 0;
}

.info-value {
  font-size: 11px;
  text-align: right;
  word-break: break-all;
}

.id-value {
  color: var(--accent);
  font-weight: 500;
}

.desc-value {
  font-size: 10px;
  color: var(--text-dim);
  max-width: 180px;
}

.status-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  color: #fff;
  text-transform: uppercase;
}

.error-count { color: var(--error); }

.error-box {
  margin-top: 8px;
  padding: 6px 8px;
  background: rgba(231, 76, 60, 0.1);
  border: 1px solid rgba(231, 76, 60, 0.3);
  border-radius: 4px;
  font-size: 10px;
  color: var(--error);
  word-break: break-word;
}
</style>
