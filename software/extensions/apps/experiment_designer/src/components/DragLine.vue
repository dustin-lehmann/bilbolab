<script setup>
import { computed } from 'vue'
import { wiring } from '../graphState.js'
import { computeBezierPath } from '../utils/geometry.js'

const path = computed(() => {
  if (!wiring.active) return ''
  return computeBezierPath(
    wiring.startX, wiring.startY,
    wiring.currentX, wiring.currentY
  )
})
</script>

<template>
  <g v-if="wiring.active" class="drag-line">
    <path
      :d="path"
      fill="none"
      stroke="#45aaf2"
      stroke-width="2"
      stroke-dasharray="6 4"
      stroke-linecap="round"
      opacity="0.8"
      style="pointer-events: none;"
    />
    <!-- Target dot at cursor -->
    <circle
      :cx="wiring.currentX"
      :cy="wiring.currentY"
      r="4"
      fill="#45aaf2"
      opacity="0.6"
      style="pointer-events: none;"
    />
  </g>
</template>
