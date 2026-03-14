<script setup>
import { ref, watch, onMounted } from 'vue'
import DesignerCore from './DesignerCore.vue'
import { darkMode } from './graphState.js'
import { restoreTabs } from './experimentTabs.js'

// ── Theme ──────────────────────────────────────────────────────────────────
const localDarkMode = ref(localStorage.getItem('experiment-designer-theme') !== 'light')

watch(localDarkMode, (dark) => {
  document.body.style.background = dark ? '#0a0a0f' : '#f0f0f5'
  document.body.style.color = dark ? '#e0e0e0' : '#1a1a2e'
  localStorage.setItem('experiment-designer-theme', dark ? 'dark' : 'light')
  darkMode.value = dark
}, { immediate: true })

function toggleTheme() {
  localDarkMode.value = !localDarkMode.value
}

// ── Mount ──────────────────────────────────────────────────────────────────
// Restore previous session tabs, or start empty
onMounted(async () => {
  await restoreTabs()
})
</script>

<template>
  <div class="app" :class="{ dark: localDarkMode, light: !localDarkMode }">
    <DesignerCore
      ref="designerRef"
      :dark-mode="localDarkMode"
      :show-toolbar="true"
      :show-yaml-preview="true"
      :show-experiment-tabs="false"
    >
      <template #toolbar-right-extra>
        <button class="theme-toggle" @click="toggleTheme" :title="localDarkMode ? 'Light mode' : 'Dark mode'">
          <span v-html="localDarkMode ? '&#9788;' : '&#9790;'"></span>
        </button>
      </template>
    </DesignerCore>
  </div>
</template>

<style>
/* ── Global resets & variables ──────────────────────────────────────────── */
:root {
  --bg: #0a0a0f;
  --bg-surface: #14141f;
  --bg-hover: #1e1e2e;
  --border: #2a2a3a;
  --text: #e0e0e0;
  --text-dim: #888;
  --accent: #45aaf2;
  --accent-dim: #2d7ab8;
  --container-bg: rgba(255, 255, 255, 0.03);
}

.light {
  --bg: #f0f0f5;
  --bg-surface: #ffffff;
  --bg-hover: #e8e8f0;
  --border: #d0d0da;
  --text: #1a1a2e;
  --text-dim: #666;
  --accent: #2d7ab8;
  --accent-dim: #1a5a8a;
  --container-bg: rgba(0, 0, 0, 0.03);
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'JetBrains Mono', monospace;
  overflow: hidden;
  height: 100vh;
}

/* ── App layout ─────────────────────────────────────────────────────────── */
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg);
  color: var(--text);
  position: relative;
}

/* ── Theme toggle ──────────────────────────────────────────────────────── */
.theme-toggle {
  font-size: 16px;
  padding: 2px 8px;
  border: none;
  background: none;
  color: var(--text);
  cursor: pointer;
  font-family: inherit;
  line-height: 1;
}
.theme-toggle:hover { color: var(--accent); }

/* ── Scrollbar styling ──────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }
</style>
