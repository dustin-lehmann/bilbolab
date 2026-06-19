<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { io } from 'socket.io-client'
import TileFloor from './components/TileFloor.vue'
import ControlPanel from './components/ControlPanel.vue'

const socket = io()

const connected = ref(false)
const config = ref(null)
const pixels = ref(null) // [y][x][edge][segment] -> [r,g,b]
const isOn = ref(true)
const brightness = ref(255)
const maxBrightness = ref(255)
const animation = ref(null)

const scope = ref('segment') // segment | edge | tile | all
const viewMode = ref(
  new URLSearchParams(window.location.search).get('view')
  || localStorage.getItem('tile-view-mode')
  || 'schematic'
)
const color = ref([255, 176, 0])

function setViewMode(mode) {
  viewMode.value = mode
  localStorage.setItem('tile-view-mode', mode)
}
const hoverInfo = ref(null)
const layouts = ref([])
const layoutMsg = ref('')
let layoutMsgTimer = null

socket.on('connect', () => (connected.value = true))
socket.on('disconnect', () => (connected.value = false))

socket.on('init', (data) => {
  config.value = data.config
  applyState(data.state)
  animation.value = data.animation
  layouts.value = data.layouts || []
})

socket.on('state', applyState)
socket.on('animation', (data) => (animation.value = data.name))
socket.on('layouts', (data) => (layouts.value = data.names))
socket.on('layout_msg', (data) => {
  layoutMsg.value = data.text
  clearTimeout(layoutMsgTimer)
  layoutMsgTimer = setTimeout(() => (layoutMsg.value = ''), 4000)
})

function applyState(state) {
  pixels.value = state.pixels
  isOn.value = state.on
  brightness.value = state.brightness
  maxBrightness.value = state.max_brightness
}

const rippleMode = computed(() =>
  animation.value === 'ripple' || animation.value === 'rain'
)

function paint(target, erase, strokeStart) {
  if (rippleMode.value) return // clicks spawn waves instead
  const applies =
    scope.value === 'all' || scope.value === 'tile' || target.edge !== null
  if (!applies) return // tile interior clicked in segment/edge scope
  if (strokeStart) socket.emit('checkpoint') // one undo step per stroke
  const c = erase ? [0, 0, 0] : color.value
  if (scope.value === 'all') {
    socket.emit('set_all', { color: c })
  } else if (scope.value === 'tile') {
    socket.emit('set_tile', { x: target.x, y: target.y, color: c })
  } else if (scope.value === 'edge') {
    socket.emit('set_edge', { x: target.x, y: target.y, edge: target.edge, color: c })
  } else {
    socket.emit('set_segment', {
      x: target.x, y: target.y,
      edge: target.edge, segment: target.segment,
      color: c
    })
  }
}

function ripple(pos) {
  socket.emit('ripple', { x: pos.x, y: pos.y, color: color.value })
}

function blink(pos) {
  socket.emit('blink', { x: pos.x, y: pos.y })
}

function undo() {
  socket.emit('undo')
}

function redo() {
  socket.emit('redo')
}

function saveLayout(name) {
  socket.emit('save_layout', { name })
}

function loadLayout(name) {
  socket.emit('load_layout', { name })
}

function deleteLayout(name) {
  socket.emit('delete_layout', { name })
}

function setOn(on) {
  socket.emit('set_on', { on })
}

function setBrightness(value) {
  brightness.value = value // optimistic, slider stays smooth
  socket.emit('set_brightness', { brightness: value })
}

function setMaxBrightness(value) {
  maxBrightness.value = value
  socket.emit('set_max_brightness', { max_brightness: value })
}

function setPattern(name) {
  socket.emit('set_pattern', { name, color: color.value })
}

// color-based animations follow the selection live
watch(color, (c) => socket.emit('set_anim_color', { color: c }))

function stopPattern() {
  socket.emit('stop_pattern')
}

function clearAll() {
  socket.emit('clear')
}

const litCount = computed(() => {
  if (!pixels.value) return 0
  let n = 0
  for (const row of pixels.value)
    for (const tile of row)
      for (const edge of tile)
        for (const seg of edge)
          if (seg[0] || seg[1] || seg[2]) n++
  return n
})

const totalSegments = computed(() =>
  config.value ? config.value.tiles_x * config.value.tiles_y * 20 : 0
)

const SCOPE_KEYS = { 1: 'segment', 2: 'edge', 3: 'tile', 4: 'all' }
function onKeydown(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
    return // typing in a text field — leave hotkeys (and text undo) alone
  }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
    e.preventDefault()
    if (e.shiftKey) redo()
    else undo()
    return
  }
  if (SCOPE_KEYS[e.key]) scope.value = SCOPE_KEYS[e.key]
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark"></span>
        <h1>Tile Floor</h1>
        <span class="brand-sub">IdeenExpo 2026</span>
      </div>
      <div class="topbar-right">
        <div class="view-toggle">
          <button
            :class="{ active: viewMode === 'schematic' }"
            @click="setViewMode('schematic')"
          >Schematic</button>
          <button
            :class="{ active: viewMode === 'real' }"
            @click="setViewMode('real')"
          >Real</button>
        </div>
        <span v-if="config" class="grid-info">
          {{ config.modules_x }}×{{ config.modules_y }} MODULES ·
          {{ config.tiles_x }}×{{ config.tiles_y }} TILES ·
          {{ totalSegments }} SEG
        </span>
        <span class="link-status" :class="{ up: connected }">
          <span class="link-dot"></span>{{ connected ? 'LINK' : 'NO LINK' }}
        </span>
      </div>
    </header>

    <main class="content">
      <section class="floor-pane">
        <TileFloor
          v-if="config && pixels"
          :config="config"
          :pixels="pixels"
          :is-on="isOn"
          :brightness="brightness"
          :max-brightness="maxBrightness"
          :scope="scope"
          :ripple-mode="rippleMode"
          :realistic="viewMode === 'real'"
          @paint="paint"
          @ripple="ripple"
          @blink="blink"
          @hover="hoverInfo = $event"
        />
        <div v-else class="waiting">
          <span class="waiting-text">AWAITING CONTROLLER STATE…</span>
        </div>
        <div v-if="config && !isOn" class="blanked-flag">OUTPUT BLANKED</div>
        <div v-if="config && rippleMode && isOn" class="ripple-hint">
          CLICK THE FLOOR TO SPAWN WAVES
        </div>
      </section>

      <ControlPanel
        :is-on="isOn"
        :brightness="brightness"
        :max-brightness="maxBrightness"
        :scope="scope"
        :color="color"
        :animation="animation"
        :hover-info="hoverInfo"
        :lit-count="litCount"
        :total-segments="totalSegments"
        :layouts="layouts"
        :layout-msg="layoutMsg"
        @set-on="setOn"
        @set-brightness="setBrightness"
        @set-max-brightness="setMaxBrightness"
        @set-scope="scope = $event"
        @set-color="color = $event"
        @set-pattern="setPattern"
        @stop-pattern="stopPattern"
        @clear="clearAll"
        @undo="undo"
        @redo="redo"
        @save-layout="saveLayout"
        @load-layout="loadLayout"
        @delete-layout="deleteLayout"
      />
    </main>
  </div>
</template>

<style scoped>
.shell {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  height: 52px;
  border-bottom: 1px solid var(--panel-edge);
  background: linear-gradient(180deg, #0d1217, #090d11);
  flex-shrink: 0;
}

.brand {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.brand-mark {
  width: 10px;
  height: 10px;
  background: var(--accent);
  box-shadow: 0 0 10px var(--accent);
  align-self: center;
}

.brand h1 {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

.brand-sub {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-dim);
  letter-spacing: 0.08em;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 18px;
}

.grid-info {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-dim);
  letter-spacing: 0.06em;
}

.view-toggle {
  display: flex;
  border: 1px solid var(--panel-edge);
  border-radius: 3px;
  overflow: hidden;
}

.view-toggle button {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-dim);
  background: var(--panel-inset);
  border: none;
  padding: 6px 12px;
  cursor: pointer;
  transition: color 0.12s, background 0.12s;
}

.view-toggle button.active {
  color: #0a0a06;
  background: var(--accent);
}

.link-status {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.18em;
  color: var(--danger);
}

.link-status.up {
  color: var(--ok);
}

.link-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 8px currentColor;
  animation: blink 2s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

.content {
  flex: 1;
  display: flex;
  min-height: 0;
}

.floor-pane {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 26px;
  min-width: 0;
  background:
    radial-gradient(ellipse 75% 70% at 50% 42%, rgba(40, 60, 80, 0.12), transparent 70%),
    repeating-linear-gradient(0deg, var(--bg-grid) 0 1px, transparent 1px 44px),
    repeating-linear-gradient(90deg, var(--bg-grid) 0 1px, transparent 1px 44px),
    var(--bg);
}

.waiting {
  font-family: var(--font-mono);
  color: var(--ink-dim);
  font-size: 12px;
  letter-spacing: 0.2em;
}

.waiting-text {
  animation: blink 1.4s ease-in-out infinite;
}

.blanked-flag {
  position: absolute;
  top: 14px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.3em;
  color: var(--danger);
  border: 1px solid rgba(255, 69, 58, 0.45);
  background: rgba(255, 69, 58, 0.08);
  padding: 5px 14px 5px 17px;
  border-radius: 2px;
  animation: blink 1.6s ease-in-out infinite;
  pointer-events: none;
}

.ripple-hint {
  position: absolute;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.28em;
  color: var(--accent);
  border: 1px solid var(--accent-line);
  background: var(--accent-soft);
  padding: 5px 14px 5px 17px;
  border-radius: 2px;
  animation: blink 2.2s ease-in-out infinite;
  pointer-events: none;
}
</style>
