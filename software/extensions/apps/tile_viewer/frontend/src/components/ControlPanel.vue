<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  isOn: Boolean,
  brightness: Number,
  maxBrightness: Number,
  scope: String,
  color: Array,
  animation: String,
  hoverInfo: Object,
  litCount: Number,
  totalSegments: Number,
  layouts: Array,
  layoutMsg: String
})

const emit = defineEmits([
  'set-on', 'set-brightness', 'set-max-brightness', 'set-scope', 'set-color',
  'set-pattern', 'stop-pattern', 'clear', 'undo', 'redo',
  'save-layout', 'load-layout', 'delete-layout'
])

const layoutName = ref('')

function saveLayout() {
  emit('save-layout', layoutName.value)
}

function confirmDelete(name) {
  if (window.confirm(`Delete layout "${name}"?`)) emit('delete-layout', name)
}

const SCOPES = [
  { id: 'segment', label: 'Segment', key: '1' },
  { id: 'edge', label: 'Edge', key: '2' },
  { id: 'tile', label: 'Tile', key: '3' },
  { id: 'all', label: 'All', key: '4' }
]

const PALETTE = [
  [255, 255, 255], [255, 176, 0], [255, 0, 0], [255, 100, 0],
  [255, 220, 0], [0, 255, 0], [0, 255, 255], [0, 90, 255],
  [180, 0, 255], [255, 0, 150]
]

const PATTERNS = [
  { id: 'checkerboard', label: 'Checker' },
  { id: 'identify_tiles', label: 'ID Tiles' },
  { id: 'identify_edges', label: 'ID Edges' }
]

const ANIMATIONS = [
  { id: 'chase', label: 'Chase', uses_color: true },
  { id: 'chase_rainbow', label: 'RGB Chase' },
  { id: 'comets', label: 'Comets' },
  { id: 'marquee', label: 'Marquee', uses_color: true },
  { id: 'rainbow', label: 'Rainbow' },
  { id: 'plasma', label: 'Plasma' },
  { id: 'scanner', label: 'Scanner', uses_color: true },
  { id: 'radar', label: 'Radar', uses_color: true },
  { id: 'sonar', label: 'Sonar', uses_color: true },
  { id: 'breathe', label: 'Breathe', uses_color: true },
  { id: 'sparkle', label: 'Sparkle', uses_color: true },
  { id: 'snakes', label: 'Snakes' },
  { id: 'tetris', label: 'Tetris' },
  { id: 'life', label: 'Life', uses_color: true },
  { id: 'storm', label: 'Storm' },
  { id: 'rain', label: 'Rain' },
  { id: 'ripple', label: 'Ripple', uses_color: true, hint: 'Click the floor to spawn waves' }
]

const brightnessPct = computed(() => Math.round((props.brightness / 255) * 100))
const sliderFill = computed(() => `${(props.brightness / 255) * 100}%`)
const maxBrightnessPct = computed(() => Math.round((props.maxBrightness / 255) * 100))
const maxSliderFill = computed(() => `${(props.maxBrightness / 255) * 100}%`)

const colorHex = computed(() => {
  const [r, g, b] = props.color
  return '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')
})

const colorCss = computed(
  () => `rgb(${props.color[0]},${props.color[1]},${props.color[2]})`
)

function sameColor(c) {
  return c[0] === props.color[0] && c[1] === props.color[1] && c[2] === props.color[2]
}

function onPickerInput(event) {
  const hex = event.target.value
  emit('set-color', [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16)
  ])
}

const hoverText = computed(() => {
  const h = props.hoverInfo
  if (!h) return '—'
  if (h.edge === null) return `TILE (${h.x},${h.y})`
  return `TILE (${h.x},${h.y}) · ${h.edge} · SEG ${h.segment}`
})
</script>

<template>
  <aside class="panel">
    <!-- POWER -->
    <section class="group">
      <h2>Output</h2>
      <div class="power-row">
        <button
          class="power-btn"
          :class="{ on: isOn }"
          @click="emit('set-on', !isOn)"
        >
          <span class="power-lamp"></span>
          {{ isOn ? 'ON' : 'OFF' }}
        </button>
        <button class="btn" @click="emit('clear')">Clear</button>
      </div>
      <div class="bri-row">
        <label>Brightness</label>
        <span class="bri-value">{{ brightnessPct }}%</span>
      </div>
      <input
        type="range" min="0" max="255"
        :value="brightness"
        :style="{ '--fill': sliderFill }"
        @input="emit('set-brightness', Number($event.target.value))"
      />
      <div class="bri-row limit-row">
        <label>Max Brightness</label>
        <span class="bri-value limit">{{ maxBrightnessPct }}%</span>
      </div>
      <input
        type="range" min="0" max="255" class="limit"
        :value="maxBrightness"
        :style="{ '--fill': maxSliderFill }"
        @input="emit('set-max-brightness', Number($event.target.value))"
      />
    </section>

    <!-- PAINT -->
    <section class="group">
      <h2>Paint</h2>
      <div class="scope-row">
        <button
          v-for="s in SCOPES" :key="s.id"
          class="btn scope-btn"
          :class="{ active: scope === s.id }"
          :title="`Hotkey ${s.key}`"
          @click="emit('set-scope', s.id)"
        >
          {{ s.label }}<span class="hotkey">{{ s.key }}</span>
        </button>
      </div>
      <div class="palette">
        <button
          v-for="(c, i) in PALETTE" :key="i"
          class="swatch"
          :class="{ selected: sameColor(c) }"
          :style="{ background: `rgb(${c[0]},${c[1]},${c[2]})` }"
          @click="emit('set-color', c)"
        ></button>
        <label class="swatch custom" :style="{ background: colorHex }">
          <input type="color" :value="colorHex" @input="onPickerInput" />
          <span>+</span>
        </label>
      </div>
      <div class="color-readout">{{ colorHex.toUpperCase() }}</div>
      <div class="undo-row">
        <button class="btn" title="Cmd/Ctrl+Z" @click="emit('undo')">↩ Undo</button>
        <button class="btn" title="Cmd/Ctrl+Shift+Z" @click="emit('redo')">Redo ↪</button>
      </div>
    </section>

    <!-- PATTERNS -->
    <section class="group">
      <h2>Test Patterns</h2>
      <div class="pattern-grid">
        <button
          v-for="p in PATTERNS" :key="p.id"
          class="btn"
          @click="emit('set-pattern', p.id)"
        >
          {{ p.label }}
        </button>
      </div>
    </section>

    <!-- ANIMATIONS -->
    <section class="group">
      <h2>Animations</h2>
      <div class="pattern-grid">
        <button
          v-for="p in ANIMATIONS" :key="p.id"
          class="btn"
          :class="{ running: animation === p.id }"
          :title="p.hint || (p.uses_color ? 'Uses the selected color' : '')"
          @click="emit('set-pattern', p.id)"
        >
          {{ p.label }}<span
            v-if="p.uses_color"
            class="color-mark"
            :style="{ background: colorCss }"
          ></span>
        </button>
        <button class="btn stop" :disabled="!animation" @click="emit('stop-pattern')">
          ■ Stop
        </button>
      </div>
    </section>

    <!-- LAYOUTS -->
    <section class="group">
      <h2>Layouts</h2>
      <div class="save-row">
        <input
          v-model="layoutName"
          class="name-input"
          type="text"
          placeholder="layout name…"
          spellcheck="false"
          @keydown.enter="saveLayout"
        />
        <button class="btn" title="Save the current floor as a layout" @click="saveLayout">
          Save
        </button>
      </div>
      <div v-if="layouts && layouts.length" class="layout-list">
        <div v-for="name in layouts" :key="name" class="layout-item">
          <button class="btn layout-load" :title="`Load “${name}”`"
                  @click="emit('load-layout', name)">
            {{ name }}
          </button>
          <button class="btn layout-del" title="Delete" @click="confirmDelete(name)">
            ✕
          </button>
        </div>
      </div>
      <div v-else class="layout-empty">no saved layouts</div>
      <div v-if="layoutMsg" class="layout-msg">{{ layoutMsg }}</div>
    </section>

    <!-- STATUS -->
    <section class="group status">
      <h2>Status</h2>
      <div class="status-line"><span>CURSOR</span><span>{{ hoverText }}</span></div>
      <div class="status-line"><span>LIT</span><span>{{ litCount }} / {{ totalSegments }}</span></div>
      <div class="status-line"><span>ANIM</span><span>{{ animation || '—' }}</span></div>
    </section>

    <footer class="hints">
      L-CLICK PAINT · R-CLICK ERASE · ⌘Z UNDO
    </footer>
  </aside>
</template>

<style scoped>
.panel {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 16px;
  border-left: 1px solid var(--panel-edge);
  background: var(--panel);
  overflow-y: auto;
}

.group h2 {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.28em;
  text-transform: uppercase;
  color: var(--ink-dim);
  border-bottom: 1px solid var(--panel-edge);
  padding-bottom: 6px;
  margin-bottom: 10px;
}

/* power */
.power-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.power-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.22em;
  padding: 10px;
  border-radius: 3px;
  cursor: pointer;
  color: var(--ink-dim);
  background: var(--panel-inset);
  border: 1px solid var(--panel-edge);
  transition: all 0.15s;
}

.power-btn .power-lamp {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #2a333d;
  transition: all 0.15s;
}

.power-btn.on {
  color: var(--ok);
  border-color: rgba(61, 220, 132, 0.4);
}

.power-btn.on .power-lamp {
  background: var(--ok);
  box-shadow: 0 0 9px var(--ok);
}

.bri-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
}

.bri-row label {
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--ink-dim);
}

.bri-value {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent);
}

.limit-row {
  margin-top: 12px;
}

.bri-value.limit {
  color: #ff6a3d;
}

/* paint */
.scope-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 5px;
  margin-bottom: 12px;
}

.scope-btn {
  padding: 7px 2px;
  font-size: 10px;
  position: relative;
}

.scope-btn .hotkey {
  position: absolute;
  top: 2px;
  right: 4px;
  font-size: 7px;
  opacity: 0.5;
}

.palette {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 7px;
}

.swatch {
  aspect-ratio: 1;
  border-radius: 3px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  cursor: pointer;
  transition: transform 0.1s, box-shadow 0.1s;
}

.swatch:hover {
  transform: scale(1.12);
}

.swatch.selected {
  box-shadow: 0 0 0 2px var(--bg), 0 0 0 3.5px var(--accent);
}

.swatch.custom {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.swatch.custom input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.swatch.custom span {
  font-size: 13px;
  font-weight: 700;
  color: #0a0a06;
  mix-blend-mode: difference;
  filter: invert(1);
  pointer-events: none;
}

.color-readout {
  margin-top: 9px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-dim);
  text-align: right;
}

.undo-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-top: 10px;
}

/* patterns */
.pattern-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
}

.color-mark {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-left: 6px;
  vertical-align: middle;
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.btn.stop:disabled {
  opacity: 0.35;
  cursor: default;
}

/* layouts */
.save-row {
  display: flex;
  gap: 6px;
  margin-bottom: 9px;
}

.name-input {
  flex: 1;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink);
  background: var(--panel-inset);
  border: 1px solid var(--panel-edge);
  border-radius: 3px;
  padding: 7px 9px;
  outline: none;
}

.name-input:focus {
  border-color: var(--accent-line);
}

.name-input::placeholder {
  color: var(--ink-faint);
}

.layout-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 150px;
  overflow-y: auto;
}

.layout-item {
  display: flex;
  gap: 4px;
}

.layout-load {
  flex: 1;
  text-align: left;
  text-transform: none;
  letter-spacing: 0.04em;
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.layout-del {
  padding: 8px 9px;
  flex-shrink: 0;
}

.layout-del:hover {
  color: var(--danger);
  border-color: rgba(255, 69, 58, 0.45);
}

.layout-empty {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-faint);
  padding: 2px 0;
}

.layout-msg {
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--accent);
}

/* status */
.status-line {
  display: flex;
  justify-content: space-between;
  font-family: var(--font-mono);
  font-size: 10.5px;
  padding: 3.5px 0;
  color: var(--ink);
}

.status-line span:first-child {
  color: var(--ink-faint);
  letter-spacing: 0.15em;
}

.hints {
  margin-top: auto;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  color: var(--ink-faint);
  text-align: center;
  padding-top: 10px;
  border-top: 1px solid var(--panel-edge);
}
</style>
