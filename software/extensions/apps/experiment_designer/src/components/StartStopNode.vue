<script setup>
import { computed } from 'vue'
import { selection, selectNode, toggleNodeSelection, isNodeSelected, startWiring, pan, zoom, edges, mode, layoutDirection } from '../graphState.js'
import { START_WIDTH, START_HEIGHT, STOP_WIDTH, STOP_HEIGHT, ENTRY_WIDTH, ENTRY_HEIGHT, getInputPortPos, getOutputPortPos, getPortVisualCenter } from '../utils/geometry.js'

const props = defineProps({
  node: { type: Object, required: true },
})

const emit = defineEmits(['startDrag'])

const isStart = computed(() => props.node.type === '__start__')
const isStop = computed(() => props.node.type === '__stop__')
const isEntry = computed(() => props.node.type === '__entry__')
const isExit = computed(() => props.node.type === '__exit__')
const isSelected = computed(() => isNodeSelected(props.node.id))
const isPlayback = computed(() => mode.value === 'playback')

const isHorizontal = computed(() => layoutDirection.value === 'horizontal')

const outputConnected = computed(() => edges.value.some(e => e.from === props.node.id))
const inputConnected = computed(() => edges.value.some(e => e.to === props.node.id))

const width = computed(() => {
  if (isEntry.value || isExit.value) return ENTRY_WIDTH
  return isStart.value ? START_WIDTH : STOP_WIDTH
})
const height = computed(() => {
  if (isEntry.value || isExit.value) return ENTRY_HEIGHT
  return isStart.value ? START_HEIGHT : STOP_HEIGHT
})

function onMouseDown(e) {
  if (e.button !== 0) return
  if (e.target.classList.contains('port')) return
  if (e.shiftKey) {
    toggleNodeSelection(props.node.id)
  } else if (!isNodeSelected(props.node.id)) {
    selectNode(props.node.id)
  }
  if (!isPlayback.value) {
    emit('startDrag', { nodeId: props.node.id, offsetX: e.offsetX, offsetY: e.offsetY, event: e })
  }
}

function onOutPortMouseDown(e) {
  if (isPlayback.value) return
  e.stopPropagation()
  e.preventDefault()
  const pos = getPortVisualCenter(e.currentTarget, pan.x, pan.y, zoom.value)
  if (pos) {
    startWiring(props.node.id, 'done', pos.x, pos.y)
  }
}

function onInPortMouseDown(e) {
  if (isPlayback.value) return
  e.stopPropagation()
  e.preventDefault()
  const pos = getPortVisualCenter(e.currentTarget, pan.x, pan.y, zoom.value)
  if (pos) {
    startWiring(props.node.id, '__input__', pos.x, pos.y)
  }
}
</script>

<template>
  <div
    class="special-node"
    :class="{
      start: isStart,
      stop: isStop,
      entry: isEntry,
      exit: isExit,
      selected: isSelected,
    }"
    :style="{
      left: node.x + 'px',
      top: node.y + 'px',
      width: width + 'px',
      height: height + 'px',
    }"
    @mousedown="onMouseDown"
  >
    <span class="label">{{ isStart ? 'Start' : isStop ? 'Stop' : isEntry ? 'Entry' : 'Exit' }}</span>

    <!-- Start / Entry: output port — bottom (vertical) or right (horizontal) -->
    <div
      v-if="isStart || isEntry"
      class="port port-out"
      :class="{ connected: outputConnected }"
      :style="isHorizontal ? { bottom: 'auto', left: 'auto', right: '-5px', top: '50%', transform: 'translateY(-50%)' } : {}"
      @mousedown="onOutPortMouseDown"
      :data-node-id="node.id"
      data-port-name="done"
      data-port-type="out"
    ></div>

    <!-- Stop / Exit: input port — top (vertical) or left (horizontal) -->
    <div
      v-if="isStop || isExit"
      class="port port-in"
      :class="{ connected: inputConnected }"
      :style="isHorizontal ? { top: '50%', left: '-5px', transform: 'translateY(-50%)' } : {}"
      :data-node-id="node.id"
      data-port-type="in"
      @mousedown="onInPortMouseDown"
    ></div>
  </div>
</template>

<style scoped>
.special-node {
  position: absolute;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
  user-select: none;
  font-size: 12px;
  font-weight: 600;
  transition: border-color 0.15s, box-shadow 0.15s;
  overflow: visible;
}

.special-node.start {
  background: #1b4332;
  border: 2px solid #2d6a4f;
  color: #52b788;
}

.special-node.stop {
  background: #3d0a0a;
  border: 2px solid #6b1a1a;
  color: #e76f6f;
}

.special-node.entry {
  background: #1b4332;
  border: 2px solid #2d6a4f;
  color: #52b788;
  border-radius: 12px;
  font-size: 10px;
}

.special-node.exit {
  background: #3d0a0a;
  border: 2px solid #6b1a1a;
  color: #e76f6f;
  border-radius: 12px;
  font-size: 10px;
}

.special-node.selected {
  box-shadow: 0 0 0 2px var(--accent), 0 2px 8px rgba(0,0,0,0.3);
}

.label { pointer-events: none; }

/* Port dots */
.port {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--bg-surface);
  cursor: crosshair;
  transition: background 0.1s;
  position: absolute;
  z-index: 5;
}

.port::after {
  content: '';
  position: absolute;
  top: -6px;
  left: -6px;
  right: -6px;
  bottom: -6px;
  border-radius: 50%;
}

.port:hover {
  background: var(--accent);
}

.port-out.connected { background: #52b788; }
.port-in.connected { background: #e76f6f; }

.port-out {
  border: 2px solid #52b788;
  bottom: -5px;
  left: 50%;
  transform: translateX(-50%);
}

.port-in {
  border: 2px solid #e76f6f;
  top: -5px;
  left: 50%;
  transform: translateX(-50%);
}
</style>
