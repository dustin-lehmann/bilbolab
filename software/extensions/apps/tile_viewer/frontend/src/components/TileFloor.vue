<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  config: { type: Object, required: true },
  pixels: { type: Array, required: true }, // [y][x][edge][segment] -> [r,g,b]
  isOn: { type: Boolean, default: true },
  brightness: { type: Number, default: 255 },
  maxBrightness: { type: Number, default: 255 },
  scope: { type: String, default: 'segment' },
  rippleMode: { type: Boolean, default: false },
  realistic: { type: Boolean, default: false }
})

const emit = defineEmits(['paint', 'ripple', 'blink', 'hover'])

// SVG geometry (world frame: tile (0,0) bottom-left, y up; SVG y is down)
const T = 100 // tile size in SVG units
const STRIP = 13 // strip thickness
const GAP = 2.4 // gap between segments
const EDGE_NAMES = ['N', 'E', 'S', 'W']

const floorW = computed(() => props.config.tiles_x * T)
const floorH = computed(() => props.config.tiles_y * T)
const viewBox = computed(() => `-30 -10 ${floorW.value + 42} ${floorH.value + 44}`)

// All edges are inset by STRIP at both ends so every segment has the same
// length; the four STRIP x STRIP corners of each tile stay dark ("holes").
const SEG_LEN = (T - 2 * STRIP) / 5

function segmentRect(x, y, edge, s) {
  const tx = x * T
  const ty = (props.config.tiles_y - 1 - y) * T
  if (edge === 0) // N — top, segments run +x
    return { rx: tx + STRIP + s * SEG_LEN + GAP / 2, ry: ty + GAP / 2, w: SEG_LEN - GAP, h: STRIP - GAP }
  if (edge === 2) // S — bottom, segments run +x
    return { rx: tx + STRIP + s * SEG_LEN + GAP / 2, ry: ty + T - STRIP + GAP / 2, w: SEG_LEN - GAP, h: STRIP - GAP }
  if (edge === 1) // E — right, segments run +y (upwards = SVG up)
    return { rx: tx + T - STRIP + GAP / 2, ry: ty + T - STRIP - (s + 1) * SEG_LEN + GAP / 2, w: STRIP - GAP, h: SEG_LEN - GAP }
  // W — left, segments run +y
  return { rx: tx + GAP / 2, ry: ty + T - STRIP - (s + 1) * SEG_LEN + GAP / 2, w: STRIP - GAP, h: SEG_LEN - GAP }
}

const segments = computed(() => {
  const out = []
  const scale = (props.brightness / 255) * (props.maxBrightness / 255)
  for (let y = 0; y < props.config.tiles_y; y++) {
    for (let x = 0; x < props.config.tiles_x; x++) {
      for (let e = 0; e < 4; e++) {
        for (let s = 0; s < 5; s++) {
          const [r, g, b] = props.pixels[y][x][e][s]
          const rect = segmentRect(x, y, e, s)
          const black = r + g + b === 0
          let fill, opacity, lit
          if (black) {
            fill = '#10151b'
            opacity = 1
            lit = false
          } else if (props.isOn) {
            const dr = Math.round(r * scale)
            const dg = Math.round(g * scale)
            const db = Math.round(b * scale)
            fill = `rgb(${dr},${dg},${db})`
            opacity = 1
            lit = dr + dg + db > 20
          } else {
            fill = `rgb(${r},${g},${b})` // ghost of the painted state
            opacity = 0.13
            lit = false
          }
          out.push({
            key: `${x},${y},${e},${s}`,
            x, y, edge: e, segment: s,
            ...rect, fill, opacity, lit, black
          })
        }
      }
    }
  }
  return out
})

const litSegments = computed(() => segments.value.filter((s) => s.lit))

// Frosted-tile interior glow from the average of the tile's edge colors
const tileGlows = computed(() => {
  if (!props.isOn) return []
  const out = []
  const scale = (props.brightness / 255) * (props.maxBrightness / 255)
  for (let y = 0; y < props.config.tiles_y; y++) {
    for (let x = 0; x < props.config.tiles_x; x++) {
      let r = 0, g = 0, b = 0
      for (let e = 0; e < 4; e++)
        for (let s = 0; s < 5; s++) {
          r += props.pixels[y][x][e][s][0]
          g += props.pixels[y][x][e][s][1]
          b += props.pixels[y][x][e][s][2]
        }
      r = (r / 20) * scale; g = (g / 20) * scale; b = (b / 20) * scale
      if (r + g + b < 6) continue
      out.push({
        key: `glow${x},${y}`,
        rx: x * T + STRIP,
        ry: (props.config.tiles_y - 1 - y) * T + STRIP,
        fill: `rgb(${Math.round(r)},${Math.round(g)},${Math.round(b)})`
      })
    }
  }
  return out
})

// Module boundary lines (every 2 tiles)
const moduleLines = computed(() => {
  const lines = []
  for (let mx = 1; mx < props.config.modules_x; mx++)
    lines.push({ x1: mx * 2 * T, y1: 0, x2: mx * 2 * T, y2: floorH.value })
  for (let my = 1; my < props.config.modules_y; my++)
    lines.push({ x1: 0, y1: my * 2 * T, x2: floorW.value, y2: my * 2 * T })
  return lines
})

// ---- interaction ----
const painting = ref(false)
const erasing = ref(false)
const hovered = ref(null)

const highlightKeys = computed(() => {
  const h = hovered.value
  if (!h || props.scope === 'all' || props.rippleMode) return new Set()
  const keys = new Set()
  if (props.scope === 'tile') {
    for (let e = 0; e < 4; e++)
      for (let s = 0; s < 5; s++) keys.add(`${h.x},${h.y},${e},${s}`)
  } else if (h.edge === null) {
    // hovering a tile interior — no specific edge/segment to highlight
  } else if (props.scope === 'segment') {
    keys.add(`${h.x},${h.y},${h.edge},${h.segment}`)
  } else if (props.scope === 'edge') {
    for (let s = 0; s < 5; s++) keys.add(`${h.x},${h.y},${h.edge},${s}`)
  }
  return keys
})

function target(hit) {
  return {
    x: hit.x,
    y: hit.y,
    edge: hit.edge === null ? null : EDGE_NAMES[hit.edge],
    segment: hit.segment
  }
}

function onDown(hit, event) {
  if (props.rippleMode) return // handled at the svg level
  painting.value = true
  erasing.value = event.button === 2
  emit('paint', target(hit), erasing.value, true)
}

function onEnter(hit) {
  hovered.value = hit
  emit('hover', target(hit))
  if (painting.value) emit('paint', target(hit), erasing.value, false)
}

function onSvgDown(event) {
  if (!props.rippleMode) return
  const svg = event.currentTarget
  const p = new DOMPoint(event.clientX, event.clientY)
    .matrixTransform(svg.getScreenCTM().inverse())
  const wx = p.x / T
  const wy = props.config.tiles_y - p.y / T
  if (wx < -0.3 || wx > props.config.tiles_x + 0.3) return
  if (wy < -0.3 || wy > props.config.tiles_y + 0.3) return
  emit('ripple', { x: wx, y: wy })
}

function onLeaveFloor() {
  hovered.value = null
  emit('hover', null)
}

function onUp() {
  painting.value = false
  erasing.value = false
}

onMounted(() => window.addEventListener('pointerup', onUp))
onBeforeUnmount(() => window.removeEventListener('pointerup', onUp))

// Tile interiors: pointer hit areas + coordinate labels
const tileCells = computed(() => {
  const out = []
  for (let y = 0; y < props.config.tiles_y; y++)
    for (let x = 0; x < props.config.tiles_x; x++)
      out.push({
        key: `cell${x},${y}`,
        x, y, edge: null, segment: null,
        tx: x * T,
        ty: (props.config.tiles_y - 1 - y) * T,
        rx: x * T + STRIP,
        ry: (props.config.tiles_y - 1 - y) * T + STRIP,
        cx: x * T + T / 2,
        cy: (props.config.tiles_y - 1 - y) * T + T / 2
      })
  return out
})

// ---- realistic mode --------------------------------------------------
// Scale: T = 100 SVG units = 500 mm tile -> 1 unit = 5 mm.
// LED strip band: 20 mm = 4 units around the tile; the carpet (460 mm =
// 92 units) sits centered inside. Each 100 mm segment carries 6 evenly
// spaced physical LEDs along the full edge (30 LEDs per 500 mm side).
const R_STRIP = 4         // 20 mm band
const R_CARPET = T - 2 * R_STRIP
const R_SEG = T / 5       // 100 mm
const R_LEDS = 6          // physical LEDs per logical segment
const R_BLEED = 9         // 45 mm of light bleeding onto the carpet

function carpetFor(cell) {
  return (cell.x + cell.y) % 2 === 0
    ? '/textures/carpet_blue.png'
    : '/textures/carpet_medium_gray.png'
}

const realSegments = computed(() => {
  if (!props.realistic) return []
  return segments.value.map((seg) => {
    const tx = seg.x * T
    const ty = (props.config.tiles_y - 1 - seg.y) * T
    const leds = []
    for (let k = 0; k < R_LEDS; k++) {
      const along = seg.segment * R_SEG + ((k + 0.5) * R_SEG) / R_LEDS
      if (seg.edge === 0) leds.push({ cx: tx + along, cy: ty + R_STRIP / 2 })
      else if (seg.edge === 2) leds.push({ cx: tx + along, cy: ty + T - R_STRIP / 2 })
      else if (seg.edge === 1) leds.push({ cx: tx + T - R_STRIP / 2, cy: ty + T - along })
      else leds.push({ cx: tx + R_STRIP / 2, cy: ty + T - along })
    }
    let bleed
    if (seg.edge === 0)
      bleed = { x: tx + seg.segment * R_SEG, y: ty, w: R_SEG, h: R_BLEED }
    else if (seg.edge === 2)
      bleed = { x: tx + seg.segment * R_SEG, y: ty + T - R_BLEED, w: R_SEG, h: R_BLEED }
    else if (seg.edge === 1)
      bleed = { x: tx + T - R_BLEED, y: ty + T - (seg.segment + 1) * R_SEG, w: R_BLEED, h: R_SEG }
    else
      bleed = { x: tx, y: ty + T - (seg.segment + 1) * R_SEG, w: R_BLEED, h: R_SEG }
    return {
      ...seg, leds, bleed,
      realFill: seg.black ? '#26282c' : seg.fill
    }
  })
})

const realLitSegments = computed(() => realSegments.value.filter((s) => s.lit))

const interiorCursor = computed(() => {
  if (props.rippleMode) return 'pointer'
  return props.scope === 'tile' || props.scope === 'all' ? 'crosshair' : 'default'
})

function boltPoints(cx, cy) {
  // small lightning bolt centered at (cx, cy)
  const p = [
    [1.4, -4.2], [-2.0, 0.6], [-0.3, 0.6],
    [-1.4, 4.2], [2.0, -0.6], [0.3, -0.6]
  ]
  return p.map(([dx, dy]) => `${cx + dx},${cy + dy}`).join(' ')
}

const xLabels = computed(() =>
  Array.from({ length: props.config.tiles_x }, (_, x) => ({
    x, sx: x * T + T / 2, sy: floorH.value + 22
  }))
)
const yLabels = computed(() =>
  Array.from({ length: props.config.tiles_y }, (_, y) => ({
    y, sx: -14, sy: (props.config.tiles_y - 1 - y) * T + T / 2 + 4
  }))
)
</script>

<template>
  <svg
    class="floor"
    :class="{ ripple: rippleMode }"
    :viewBox="viewBox"
    @contextmenu.prevent
    @pointerdown="onSvgDown"
    @pointerleave="onLeaveFloor"
  >
    <defs>
      <filter id="bloom" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="5.5" result="blur" />
      </filter>
      <filter id="tileblur" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="14" />
      </filter>
      <filter id="bleedblur" x="-80%" y="-80%" width="260%" height="260%">
        <feGaussianBlur stdDeviation="2.6" />
      </filter>
    </defs>

    <!-- floor base -->
    <rect
      x="0" y="0" :width="floorW" :height="floorH"
      fill="#0a0e13" stroke="#222c37" stroke-width="1.5"
    />

    <!-- ============ realistic mode: strip band + carpet inlays ========= -->
    <g v-if="realistic">
      <template v-for="cell in tileCells" :key="'r' + cell.key">
        <!-- very dark grey LED strip band (full tile, carpet covers center) -->
        <rect :x="cell.tx" :y="cell.ty" :width="T" :height="T" fill="#17181b" />
        <image
          :href="carpetFor(cell)"
          :x="cell.tx + R_STRIP" :y="cell.ty + R_STRIP"
          :width="R_CARPET" :height="R_CARPET"
          preserveAspectRatio="xMidYMid slice"
        />
      </template>
    </g>

    <!-- realistic: diffused light bleeding onto the carpet -->
    <g v-if="realistic" class="bleed" filter="url(#bleedblur)">
      <rect
        v-for="seg in realLitSegments" :key="'bl' + seg.key"
        :x="seg.bleed.x" :y="seg.bleed.y"
        :width="seg.bleed.w" :height="seg.bleed.h"
        :fill="seg.fill" opacity="0.55"
      />
    </g>

    <!-- realistic: the physical LEDs, 6 per 100 mm segment -->
    <g v-if="realistic">
      <g
        v-for="seg in realSegments" :key="'led' + seg.key"
        :fill="seg.realFill" :fill-opacity="seg.opacity"
      >
        <circle
          v-for="(led, k) in seg.leds" :key="k"
          :cx="led.cx" :cy="led.cy" r="1.05"
        />
      </g>
    </g>

    <!-- ============ schematic mode layers ============================== -->
    <!-- frosted tile interiors -->
    <g v-if="!realistic" filter="url(#tileblur)" opacity="0.33">
      <rect
        v-for="gl in tileGlows" :key="gl.key"
        :x="gl.rx" :y="gl.ry" :width="T - 2 * STRIP" :height="T - 2 * STRIP"
        :fill="gl.fill"
      />
    </g>

    <!-- bloom layer behind the crisp segments -->
    <g v-if="!realistic" filter="url(#bloom)" opacity="0.85">
      <rect
        v-for="seg in litSegments" :key="'b' + seg.key"
        :x="seg.rx" :y="seg.ry" :width="seg.w" :height="seg.h"
        :fill="seg.fill"
      />
    </g>

    <!-- tile interiors: hit areas for tile/all painting + coordinates -->
    <g>
      <rect
        v-for="cell in tileCells" :key="cell.key"
        :x="cell.rx" :y="cell.ry" :width="T - 2 * STRIP" :height="T - 2 * STRIP"
        fill="transparent"
        :style="{ cursor: interiorCursor }"
        @pointerdown.prevent="onDown(cell, $event)"
        @pointerenter="onEnter(cell)"
      />
      <text
        v-for="cell in tileCells" :key="'c' + cell.key"
        class="tile-coord"
        :x="cell.cx" :y="cell.cy + 4"
        text-anchor="middle"
      >{{ cell.x }},{{ cell.y }}</text>
      <!-- blink button: flash this tile (also on the physical floor) -->
      <g
        v-for="cell in tileCells" :key="'bl' + cell.key"
        class="blink-btn"
        @pointerdown.stop.prevent="emit('blink', { x: cell.x, y: cell.y })"
      >
        <title>Blink tile ({{ cell.x }},{{ cell.y }})</title>
        <circle :cx="cell.cx" :cy="cell.cy + 21" r="7.5" />
        <polygon
          :points="boltPoints(cell.cx, cell.cy + 21)"
        />
      </g>
    </g>

    <!-- crisp LED segments (in realistic mode: invisible hit targets +
         hover outline only — the dots above carry the visuals) -->
    <g>
      <rect
        v-for="seg in segments" :key="seg.key"
        class="seg"
        :x="seg.rx" :y="seg.ry" :width="seg.w" :height="seg.h"
        rx="2.5"
        :fill="realistic ? 'transparent' : seg.fill"
        :fill-opacity="realistic ? 1 : seg.opacity"
        :stroke="highlightKeys.has(seg.key) ? 'var(--accent)'
                 : realistic ? 'none' : 'rgba(255,255,255,0.05)'"
        :stroke-width="highlightKeys.has(seg.key) ? 1.6 : 0.6"
        @pointerdown.prevent="onDown(seg, $event)"
        @pointerenter="onEnter(seg)"
      />
    </g>

    <!-- module boundaries -->
    <g pointer-events="none">
      <line
        v-for="(l, i) in moduleLines" :key="'m' + i"
        v-bind="l"
        stroke="rgba(255,176,0,0.22)" stroke-width="1.6" stroke-dasharray="7 5"
      />
    </g>

    <!-- coordinate labels (world frame, origin bottom-left) -->
    <g class="labels" pointer-events="none">
      <text v-for="l in xLabels" :key="'x' + l.x" :x="l.sx" :y="l.sy" text-anchor="middle">
        {{ l.x }}
      </text>
      <text v-for="l in yLabels" :key="'y' + l.y" :x="l.sx" :y="l.sy" text-anchor="end">
        {{ l.y }}
      </text>
      <text :x="floorW + 14" :y="floorH + 22" text-anchor="start" class="axis">x→</text>
      <text x="-14" y="-2" text-anchor="end" class="axis">y↑</text>
    </g>
  </svg>
</template>

<style scoped>
.floor {
  width: 100%;
  height: 100%;
  max-width: 1500px;
  max-height: 100%;
}

.seg {
  cursor: crosshair;
  transition: stroke 0.08s;
}

.floor.ripple .seg {
  cursor: pointer;
}

.bleed {
  mix-blend-mode: screen;
}

.labels text {
  font-family: var(--font-mono);
  font-size: 11px;
  fill: var(--ink-dim);
}

.tile-coord {
  font-family: var(--font-mono);
  font-size: 11px;
  fill: rgba(205, 215, 225, 0.42);
  pointer-events: none;
}

.blink-btn {
  cursor: pointer;
}

.blink-btn circle {
  fill: rgba(255, 255, 255, 0.04);
  stroke: rgba(205, 215, 225, 0.22);
  stroke-width: 1;
  transition: fill 0.12s, stroke 0.12s;
}

.blink-btn polygon {
  fill: rgba(205, 215, 225, 0.35);
  pointer-events: none;
  transition: fill 0.12s;
}

.blink-btn:hover circle {
  fill: rgba(255, 176, 0, 0.18);
  stroke: var(--accent);
}

.blink-btn:hover polygon {
  fill: var(--accent);
}

.labels .axis {
  fill: var(--accent);
  font-size: 10px;
  letter-spacing: 0.1em;
}
</style>
