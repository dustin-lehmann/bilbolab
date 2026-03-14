<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import ViewerCore from './ViewerCore.vue'
import { darkMode, loadExperiment, clearExperiment } from './viewerState.js'

const props = defineProps({
  darkMode: { type: Boolean, default: true },
  transparent: { type: Boolean, default: false },
  instanceId: { type: String, default: null },
  onFileLoaded: { type: Function, default: null },
})

const coreRef = ref(null)

onMounted(() => {
  darkMode.value = props.darkMode
})

// ── Public API (exposed for JS widget wrapper) ──────────────────────────────

/**
 * Load experiment data programmatically (e.g. from Python backend).
 */
function loadData(jsonData, fileName = '') {
  loadExperiment(jsonData, fileName)
  if (props.onFileLoaded) props.onFileLoaded(fileName)
}

function clear() {
  clearExperiment()
}

defineExpose({ loadData, clear })
</script>

<template>
  <div class="viewer-widget" :class="{ dark: darkMode, light: !darkMode, transparent }">
    <ViewerCore
      ref="coreRef"
      :dark-mode="darkMode"
      :transparent="transparent"
    />
  </div>
</template>

<style scoped>
.viewer-widget {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.viewer-widget.transparent {
  --bg: transparent;
  --bg-surface: rgba(255, 255, 255, 0.04);
  --bg-hover: rgba(255, 255, 255, 0.08);
  --border: rgba(255, 255, 255, 0.1);
  --container-bg: rgba(255, 255, 255, 0.04);
}
</style>
