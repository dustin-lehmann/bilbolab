<script setup>
import { computed } from 'vue'

const props = defineProps({
  time: Number,
  total: Number,
  phase: String,
  running: Boolean,
  phases: Array,  // [{ name, duration, label, color }]
  alignPadding: Object,  // { left, right } in px, to align with chart area
})

const progress = computed(() => {
  if (!props.total) return 0
  return Math.min(100, (props.time / props.total) * 100)
})

// Compute phase segments as percentages
const segments = computed(() => {
  if (!props.phases || !props.total) return []
  let offset = 0
  return props.phases.map(p => {
    const pct = (p.duration / props.total) * 100
    const seg = { ...p, offset, pct }
    offset += pct
    return seg
  })
})
</script>

<template>
  <div class="timeline" data-tour="timeline" :style="alignPadding ? { paddingLeft: alignPadding.left + 'px', paddingRight: alignPadding.right + 'px' } : {}">
    <div class="timeline-bar">
      <div
        v-for="seg in segments"
        :key="seg.name"
        class="timeline-segment"
        :style="{
          left: seg.offset + '%',
          width: seg.pct + '%',
          background: phase === seg.name ? seg.color + '30' : 'transparent',
          borderRight: '1px solid var(--border)',
        }"
      >
        <span class="seg-label" :style="{ color: phase === seg.name ? seg.color : 'var(--text-very-dim)' }">
          {{ seg.label }}
        </span>
      </div>
      <div class="timeline-cursor" :style="{ left: progress + '%' }"></div>
    </div>
  </div>
</template>

<style scoped>
.timeline {
  flex-shrink: 0;
  padding: 6px 12px 4px;
  background: var(--bg-surface);
}
.timeline-bar {
  position: relative;
  height: 22px;
  background: var(--container-bg);
  border: 1px solid var(--border);
  border-radius: 3px;
  overflow: hidden;
}
.timeline-segment {
  position: absolute;
  top: 0;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.seg-label {
  font-size: 9px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 4px;
}
.timeline-cursor {
  position: absolute;
  top: 0;
  width: 2px;
  height: 100%;
  background: var(--accent);
  transition: left 0.05s linear;
  z-index: 1;
}
</style>
