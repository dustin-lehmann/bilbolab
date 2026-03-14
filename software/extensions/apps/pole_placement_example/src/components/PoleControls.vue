<script setup>
import { computed } from 'vue'

const props = defineProps({
  poleParams: Object,
  kError: String,
  useLinear: Boolean,
  extInputMag: Number,
  darkMode: Boolean,
})

const emit = defineEmits(['restart', 'update:useLinear', 'update:extInputMag'])

// Pole groups for display
const poleGroups = computed(() => [
  {
    label: 'Position (integrator)',
    key: 'p0_re',
    re: props.poleParams.p0_re,
    im: 0,
    color: '#45aaf2',
    min: -5, max: 2, step: 0.5,
  },
  {
    label: 'Velocity',
    key: 'p1_re',
    re: props.poleParams.p1_re,
    im: 0,
    color: '#e74c3c',
    min: -25, max: -1, step: 0.5,
  },
  {
    label: 'Pitch (θ, θ̇)',
    key_re: 'p2_re',
    key_im: 'p2_im',
    re: props.poleParams.p2_re,
    im: props.poleParams.p2_im,
    color: '#2ecc71',
    min_re: -20, max_re: -0.5, step_re: 0.5,
    min_im: 0.5, max_im: 12, step_im: 0.5,
  },
  {
    label: 'Yaw (integrator)',
    key: 'p4_re',
    re: props.poleParams.p4_re,
    im: 0,
    color: '#45aaf2',
    min: -5, max: 2, step: 0.5,
  },
  {
    label: 'Yaw rate (ψ̇)',
    key: 'p5_re',
    re: props.poleParams.p5_re,
    im: 0,
    color: '#f39c12',
    min: -30, max: -1, step: 0.5,
  },
])

function onSlider(key, val) {
  props.poleParams[key] = parseFloat(val)
}

const presets = [
  { label: 'Default', p0: 0, p1: -10, p2_re: -5, p2_im: 3, p4: 0, p5: -15, linear: false },
  { label: 'Oscillating', p0: 0, p1: -13, p2_re: -1, p2_im: 8, p4: 0, p5: -3, linear: false },
  { label: 'Stable position', p0: -2, p1: -8, p2_re: -5, p2_im: 3, p4: -2, p5: -10, linear: true },
  { label: 'Snappy', p0: 0, p1: -22, p2_re: -15, p2_im: 5, p4: 0, p5: -25, linear: false },
]

function applyPreset(p) {
  props.poleParams.p0_re = p.p0
  props.poleParams.p1_re = p.p1
  props.poleParams.p2_re = p.p2_re
  props.poleParams.p2_im = p.p2_im
  props.poleParams.p4_re = p.p4
  props.poleParams.p5_re = p.p5
  emit('update:useLinear', p.linear)
}

function resetDefaults() {
  applyPreset(presets[0])
}
</script>

<template>
  <div class="controls-panel" data-tour="controls">
    <div class="section-header">
      <span>Pole Configuration</span>
      <div class="header-actions">
        <button class="btn-small" @click="resetDefaults">Reset</button>
        <button class="btn-small btn-accent" @click="emit('restart')">Restart Sim</button>
      </div>
    </div>

    <div class="poles-list">
      <div
        v-for="(g, i) in poleGroups"
        :key="i"
        class="pole-group"
      >
        <div class="pole-label">
          <span class="pole-dot" :style="{ background: g.color }"></span>
          <span class="pole-name">{{ g.label }}</span>
        </div>

        <!-- Single real pole -->
        <div v-if="g.key" class="slider-row">
          <span class="slider-label">Re</span>
          <input
            type="range"
            :min="g.min" :max="g.max" :step="g.step"
            :value="g.re"
            @input="onSlider(g.key, $event.target.value)"
            class="slider"
          />
          <input
            type="number"
            :value="g.re"
            :min="g.min" :max="g.max" :step="g.step"
            @change="onSlider(g.key, $event.target.value)"
            class="num-input"
          />
        </div>

        <!-- Complex pair: Re slider -->
        <div v-if="g.key_re" class="slider-row">
          <span class="slider-label">Re</span>
          <input
            type="range"
            :min="g.min_re" :max="g.max_re" :step="g.step_re"
            :value="g.re"
            @input="onSlider(g.key_re, $event.target.value)"
            class="slider"
          />
          <input
            type="number"
            :value="g.re"
            :min="g.min_re" :max="g.max_re" :step="g.step_re"
            @change="onSlider(g.key_re, $event.target.value)"
            class="num-input"
          />
        </div>

        <!-- Complex pair: Im slider -->
        <div v-if="g.key_im" class="slider-row">
          <span class="slider-label">Im</span>
          <input
            type="range"
            :min="g.min_im" :max="g.max_im" :step="g.step_im"
            :value="g.im"
            @input="onSlider(g.key_im, $event.target.value)"
            class="slider"
          />
          <input
            type="number"
            :value="g.im"
            :min="g.min_im" :max="g.max_im" :step="g.step_im"
            @change="onSlider(g.key_im, $event.target.value)"
            class="num-input"
          />
        </div>
      </div>
    </div>

    <div class="presets" data-tour="presets">
      <button
        v-for="p in presets" :key="p.label"
        class="preset-btn"
        @click="applyPreset(p)"
      >{{ p.label }}</button>
    </div>

    <div v-if="kError" class="k-error">{{ kError }}</div>

    <!-- Simulation config -->
    <div class="section-header" style="margin-top: 12px;">
      <span>Simulation</span>
    </div>
    <div class="sim-config" data-tour="sim-config">
      <label class="switch-row">
        <span class="switch-label">Dynamics model</span>
        <div class="toggle-group">
          <button
            class="toggle-btn"
            :class="{ active: !useLinear }"
            @click="emit('update:useLinear', false)"
          >Nonlinear</button>
          <button
            class="toggle-btn"
            :class="{ active: useLinear }"
            @click="emit('update:useLinear', true)"
          >Linear</button>
        </div>
      </label>
      <div class="slider-row" style="margin-top: 8px;">
        <span class="switch-label">External input</span>
        <input
          type="range"
          min="0.1" max="1" step="0.1"
          :value="extInputMag"
          @input="emit('update:extInputMag', parseFloat($event.target.value))"
          class="slider"
        />
        <span class="input-value">{{ extInputMag.toFixed(1) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.controls-panel {
  padding: 10px 12px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-dim);
  margin-bottom: 8px;
}
.header-actions { display: flex; gap: 6px; }

.btn-small {
  font-family: inherit;
  font-size: 10px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  background: var(--bg-surface);
  color: var(--text-dim);
  border-radius: 3px;
  cursor: pointer;
}
.btn-small:hover { background: var(--bg-hover); color: var(--text); }
.btn-accent { border-color: var(--accent-dim); color: var(--accent); }
.btn-accent:hover { background: var(--accent-glow); }

.poles-list { display: flex; flex-direction: column; gap: 8px; }

.pole-group {
  background: var(--container-bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px 10px;
}

.pole-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.pole-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.pole-name {
  font-size: 10px;
  color: var(--text);
  flex: 1;
}

.slider-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
}
.slider-label {
  font-size: 9px;
  color: var(--text-very-dim);
  width: 16px;
  flex-shrink: 0;
}
.slider {
  flex: 1;
  height: 4px;
  -webkit-appearance: none;
  appearance: none;
  background: var(--border);
  border-radius: 2px;
  outline: none;
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
}
.num-input {
  font-family: inherit;
  font-size: 10px;
  width: 62px;
  padding: 2px 4px;
  border: 1px solid var(--border);
  background: var(--bg-surface);
  color: var(--text);
  border-radius: 3px;
  text-align: right;
}
.num-input:focus { outline: 1px solid var(--accent); }

.presets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.preset-btn {
  font-family: inherit;
  font-size: 10px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  background: var(--container-bg);
  color: var(--text-dim);
  border-radius: 3px;
  cursor: pointer;
  transition: background 0.1s, color 0.1s;
}
.preset-btn:hover {
  background: var(--bg-hover);
  color: var(--text);
  border-color: var(--accent-dim);
}

.k-error {
  font-size: 10px;
  color: var(--danger);
  padding: 6px 8px;
  margin-top: 8px;
  background: rgba(231, 76, 60, 0.1);
  border-radius: 4px;
}

.sim-config {
  background: var(--container-bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px 10px;
}

.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.switch-label {
  font-size: 10px;
  color: var(--text);
}
.toggle-group {
  display: flex;
  border: 1px solid var(--border);
  border-radius: 3px;
  overflow: hidden;
}
.toggle-btn {
  font-family: inherit;
  font-size: 10px;
  padding: 3px 10px;
  border: none;
  background: var(--bg-surface);
  color: var(--text-dim);
  cursor: pointer;
  transition: background 0.1s, color 0.1s;
}
.toggle-btn:not(:last-child) {
  border-right: 1px solid var(--border);
}
.toggle-btn.active {
  background: var(--accent);
  color: #fff;
}
.toggle-btn:hover:not(.active) {
  background: var(--bg-hover);
  color: var(--text);
}
.input-value {
  font-size: 10px;
  color: var(--text-dim);
  font-variant-numeric: tabular-nums;
  width: 28px;
  text-align: right;
  flex-shrink: 0;
}
</style>
