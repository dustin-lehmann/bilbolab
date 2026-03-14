<script setup>
import { computed } from 'vue'
import { actionList, duration, selectedActionId, hoveredActionId, selectAction, hoverAction } from '../viewerState.js'
import { getActionColor, fmtTime } from '../utils/dataAccess.js'

const totalTicks = computed(() => {
  if (actionList.value.length === 0) return 1
  return Math.max(...actionList.value.map(a => a.end_tick ?? 0), 1)
})

function barStyle(action) {
  const total = totalTicks.value
  const left = ((action.start_tick ?? 0) / total) * 100
  const width = Math.max(((action.end_tick ?? action.start_tick ?? 0) - (action.start_tick ?? 0)) / total * 100, 0.5)
  return {
    left: left + '%',
    width: width + '%',
    background: getActionColor(action.action_type),
  }
}

function isSelected(action) {
  return selectedActionId.value === action.id
}
</script>

<template>
  <div class="action-timeline">
    <div class="section-title">
      Actions Timeline
      <span v-if="selectedActionId" class="clear-selection" @click="selectAction(null)">(clear)</span>
    </div>

    <div class="timeline-list">
      <div
        v-for="action in actionList" :key="action.id"
        class="timeline-row"
        :class="{ selected: isSelected(action), hovered: hoveredActionId === action.id }"
        @click="selectAction(action.id)"
        @mouseenter="hoverAction(action.id)"
        @mouseleave="hoverAction(null)"
        :title="`${action.id}: ${action.action_type} [${fmtTime(action.start_time ?? 0)} — ${fmtTime(action.end_time ?? 0)}]`"
      >
        <div class="row-label">
          <span class="action-dot" :style="{ background: getActionColor(action.action_type) }"></span>
          <span class="action-id">{{ action.id }}</span>
          <span class="action-type">{{ action.action_type }}</span>
        </div>
        <div class="bar-track">
          <div class="bar-fill" :style="barStyle(action)"></div>
        </div>
      </div>
    </div>

    <div class="timeline-axis">
      <span>0s</span>
      <span>{{ fmtTime(duration) }}</span>
    </div>
  </div>
</template>

<style scoped>
.action-timeline {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 10px;
  overflow: hidden;
}

.section-title {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-dim);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.clear-selection {
  font-size: 10px;
  color: var(--accent);
  cursor: pointer;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
}
.clear-selection:hover { text-decoration: underline; }

.timeline-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.timeline-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 3px 6px;
  border-radius: 3px;
  cursor: pointer;
  border: 1px solid transparent;
}
.timeline-row:hover { background: var(--bg-hover); }
.timeline-row.selected {
  background: var(--bg-hover);
  border-color: var(--accent-dim);
}

.row-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
}

.action-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.action-id {
  color: var(--text-dim);
  flex-shrink: 0;
}

.action-type {
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-track {
  height: 4px;
  background: var(--bg-surface);
  border-radius: 2px;
  position: relative;
  overflow: hidden;
}

.bar-fill {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 2px;
  min-width: 2px;
  opacity: 0.8;
}

.timeline-axis {
  display: flex;
  justify-content: space-between;
  font-size: 9px;
  color: var(--text-dim);
  margin-top: 4px;
  flex-shrink: 0;
}
</style>
