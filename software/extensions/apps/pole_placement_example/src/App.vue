<script setup>
import { ref, watch, onMounted } from 'vue'

const coreRef = ref(null)
import PolePlacementCore from './components/PolePlacementCore.vue'
import TourOverlay from './components/TourOverlay.vue'

const darkMode = ref(localStorage.getItem('pole-placement-theme') !== 'light')

watch(darkMode, (dark) => {
  document.body.style.background = dark ? '#0a0a0f' : '#f0f0f5'
  document.body.style.color = dark ? '#e0e0e0' : '#1a1a2e'
  localStorage.setItem('pole-placement-theme', dark ? 'dark' : 'light')
}, { immediate: true })

function toggleTheme() { darkMode.value = !darkMode.value }

// ── Tour ────────────────────────────────────────────────────────────────────
const showTour = ref(false)

const tourSteps = [
  {
    title: 'Pole Placement Explorer',
    description: 'Explore eigenstructure assignment for the BILBO inverted pendulum. Place poles and see their effect on the dynamics in real time.',
  },
  {
    selector: '[data-tour="scene"]',
    title: '3D Simulation',
    description: 'Live 3D view of the robot responding to your pole placement. Orbit, zoom, and pan with your mouse.',
  },
  {
    selector: '[data-tour="play"]',
    title: 'Restart Simulation',
    description: 'Restarts the simulation. The robot goes through: fallen, stand-up, step forward, pause, step backward, and settle.',
  },
  {
    selector: '[data-tour="reset-cam"]',
    title: 'Reset Camera',
    description: 'Resets the camera to its default position.',
  },
  {
    selector: '[data-tour="timeline"]',
    title: 'Phase Timeline',
    description: 'Shows the current simulation phase, aligned with the state plot below.',
  },
  {
    selector: '[data-tour="state-plot"]',
    title: 'State Plot',
    description: 'State evolution over time: x, v, θ, θ̇, ψ. Line colors match the pole group colors.',
  },
  {
    selector: '[data-tour="pole-plot"]',
    title: 'Pole Map (s-plane)',
    description: 'Closed-loop pole locations in the complex plane. Drag poles to reposition them. Left half-plane = stable.',
  },
  {
    selector: '[data-tour="controls"]',
    title: 'Pole Configuration',
    description: 'Adjust poles via sliders or number inputs. Colors indicate groups: position (blue), pitch (red/green), yaw (blue/orange).',
  },
  {
    selector: '[data-tour="presets"]',
    title: 'Presets',
    description: 'Quick-apply predefined pole configurations: default, oscillating, stable position (linear), or snappy response.',
  },
  {
    selector: '[data-tour="sim-config"]',
    title: 'Simulation Settings',
    description: 'Toggle nonlinear/linear dynamics and adjust step input magnitude.',
  },
  {
    selector: '[data-tour="theme"]',
    title: 'Theme',
    description: 'Switch dark/light mode.',
  },
]

function onTourClose() {
  showTour.value = false
  localStorage.setItem('pole-placement-tour-seen', '1')
  coreRef.value?.restartWithIntro()
}

onMounted(() => {
  if (!localStorage.getItem('pole-placement-tour-seen')) {
    setTimeout(() => { showTour.value = true }, 800)
  }
})
</script>

<template>
  <div class="app" :class="{ dark: darkMode, light: !darkMode }">
    <div class="toolbar">
      <div class="toolbar-left">
        <span class="title">Pole Placement Explorer</span>
        <span class="subtitle">BILBO Eigenstructure Assignment</span>
      </div>
      <div class="toolbar-right">
        <button class="toolbar-btn" @click="showTour = true" title="Take a tour" data-tour="help">?</button>
        <button class="toolbar-btn" data-tour="theme" @click="toggleTheme" :title="darkMode ? 'Light mode' : 'Dark mode'">
          <span v-html="darkMode ? '&#9788;' : '&#9790;'"></span>
        </button>
      </div>
    </div>
    <PolePlacementCore ref="coreRef" :dark-mode="darkMode" />
    <TourOverlay :active="showTour" :steps="tourSteps" @close="onTourClose" />
  </div>
</template>

<style>
:root {
  --bg: #0a0a0f;
  --bg-surface: #14141f;
  --bg-hover: #1e1e2e;
  --border: #2a2a3a;
  --text: #e0e0e0;
  --text-dim: #888;
  --text-very-dim: #555;
  --accent: #45aaf2;
  --accent-dim: #2d7ab8;
  --accent-glow: rgba(69, 170, 242, 0.15);
  --danger: #e74c3c;
  --success: #2ecc71;
  --warning: #f39c12;
  --container-bg: rgba(255, 255, 255, 0.03);
}

.light {
  --bg: #f0f0f5;
  --bg-surface: #ffffff;
  --bg-hover: #e8e8f0;
  --border: #d0d0da;
  --text: #1a1a2e;
  --text-dim: #666;
  --text-very-dim: #999;
  --accent: #2d7ab8;
  --accent-dim: #1a5a8a;
  --accent-glow: rgba(45, 122, 184, 0.12);
  --danger: #c0392b;
  --success: #27ae60;
  --warning: #e67e22;
  --container-bg: rgba(0, 0, 0, 0.03);
}

* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'JetBrains Mono', monospace; overflow: hidden; height: 100vh; }

.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg);
  color: var(--text);
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 40px;
  padding: 0 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
  flex-shrink: 0;
}
.toolbar-left { display: flex; align-items: baseline; gap: 12px; }
.toolbar-right { display: flex; align-items: center; gap: 4px; }
.title { font-size: 13px; font-weight: 600; }
.subtitle { font-size: 11px; color: var(--text-dim); }

.toolbar-btn {
  font-size: 16px;
  padding: 2px 8px;
  border: none;
  background: none;
  color: var(--text);
  cursor: pointer;
  font-family: inherit;
  line-height: 1;
  border-radius: 4px;
}
.toolbar-btn:hover { color: var(--accent); background: var(--bg-hover); }

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }
</style>
