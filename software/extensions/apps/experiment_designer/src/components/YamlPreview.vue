<script setup>
import { ref } from 'vue'

const props = defineProps({
  yaml: { type: String, default: '' },
  expanded: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle'])
const copied = ref(false)

function copyYaml() {
  navigator.clipboard.writeText(props.yaml).then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  })
}
</script>

<template>
  <div class="yaml-panel" :class="{ expanded }">
    <div class="yaml-header" @click="emit('toggle')">
      <span class="yaml-title">YAML Preview</span>
      <span class="yaml-toggle">{{ expanded ? '\u25BE' : '\u25B4' }}</span>
    </div>
    <div v-if="expanded" class="yaml-body">
      <div class="yaml-toolbar">
        <button class="yaml-btn" @click.stop="copyYaml">
          {{ copied ? 'Copied!' : 'Copy' }}
        </button>
      </div>
      <pre class="yaml-code">{{ yaml }}</pre>
    </div>
  </div>
</template>

<style scoped>
.yaml-panel {
  flex-shrink: 0;
  background: var(--bg-surface);
  border-top: 1px solid var(--border);
}

.yaml-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  cursor: pointer;
  user-select: none;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-dim);
}
.yaml-header:hover { background: var(--bg-hover); }

.yaml-title {
  text-transform: uppercase;
  letter-spacing: 1px;
}

.yaml-toggle { font-size: 10px; }

.yaml-body {
  height: 200px;
  overflow: auto;
  border-top: 1px solid var(--border);
  position: relative;
}

.yaml-toolbar {
  position: sticky;
  top: 0;
  right: 0;
  display: flex;
  justify-content: flex-end;
  padding: 4px 8px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
}

.yaml-btn {
  font-family: inherit;
  font-size: 10px;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--bg);
  color: var(--text-dim);
  cursor: pointer;
}
.yaml-btn:hover { background: var(--bg-hover); color: var(--text); }

.yaml-code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  padding: 8px 12px;
  margin: 0;
  white-space: pre;
  color: var(--text);
  line-height: 1.5;
}
</style>
