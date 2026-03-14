<template>
    <Teleport to="body">
        <div class="tp-overlay" @click.self="$emit('cancel')">
            <div class="tp-modal">
                <div class="tp-header">
                    <h2>Pick Thumbnail</h2>
                    <button class="tp-close" @click="$emit('cancel')">&times;</button>
                </div>
                <div class="tp-body">
                    <div v-if="videos.length > 1" class="tp-video-select">
                        <label>Video</label>
                        <select v-model="selectedIdx" class="tp-select">
                            <option v-for="(v, i) in videos" :key="i" :value="i">{{ v.name || v.file }}</option>
                        </select>
                    </div>

                    <div class="tp-stage">
                        <video
                            ref="videoEl"
                            :key="selectedIdx"
                            :src="`/videos/${videos[selectedIdx].file}`"
                            :style="{ width: dispW + 'px', height: dispH + 'px' }"
                            @loadedmetadata="onMeta"
                            @timeupdate="onTimeUpdate"
                            preload="auto"
                            playsinline
                            muted
                        ></video>
                        <div
                            v-if="ready"
                            class="tp-crop-area"
                            :style="{ width: dispW + 'px', height: dispH + 'px' }"
                        >
                            <div
                                class="tp-crop-rect"
                                :style="cropStyle"
                                @mousedown.stop.prevent="startMove"
                            >
                                <div class="tp-handle tl" @mousedown.stop.prevent="startResize('tl', $event)"></div>
                                <div class="tp-handle tr" @mousedown.stop.prevent="startResize('tr', $event)"></div>
                                <div class="tp-handle bl" @mousedown.stop.prevent="startResize('bl', $event)"></div>
                                <div class="tp-handle br" @mousedown.stop.prevent="startResize('br', $event)"></div>
                            </div>
                        </div>
                    </div>

                    <div class="tp-controls" v-if="ready">
                        <button class="tp-ctrl-btn" @click="stepFrame(-1)" title="Previous frame">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" transform="scale(-1,1) translate(-24,0)"/>
                            </svg>
                        </button>
                        <button class="tp-play-btn" @click="togglePlay">
                            <span v-if="playing" class="tp-pause">&#10074;&#10074;</span>
                            <span v-else class="tp-play-icon">&#9654;</span>
                        </button>
                        <button class="tp-ctrl-btn" @click="stepFrame(1)" title="Next frame">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/>
                            </svg>
                        </button>
                        <input
                            type="range"
                            class="tp-scrubber"
                            min="0"
                            :max="duration"
                            step="0.01"
                            :value="currentTime"
                            @input="onScrub"
                        >
                        <span class="tp-time">{{ fmtTime(currentTime) }}</span>
                    </div>
                </div>
                <div class="tp-footer">
                    <button class="tp-btn tp-btn-ghost" @click="$emit('cancel')">Cancel</button>
                    <button class="tp-btn tp-btn-primary" @click="capture" :disabled="!ready">Use as Thumbnail</button>
                </div>
            </div>
        </div>
    </Teleport>
</template>

<script setup>
import { ref, reactive, computed, watch, onUnmounted } from 'vue'

const CROP_AR = 13 / 16    // width / height — matches grid tile (130×160)
const MAX_W = 720
const MAX_H = 450
const MIN_CROP = 40

const props = defineProps({
    videos: { type: Array, required: true },  // [{ name, file }]
})

const emit = defineEmits(['accept', 'cancel'])

const videoEl = ref(null)
const selectedIdx = ref(0)
const ready = ref(false)
const playing = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const natW = ref(0)
const natH = ref(0)
const crop = reactive({ x: 0, y: 0, w: 100, h: 100 })

// Display dimensions — fit video into MAX_W × MAX_H maintaining aspect ratio
const dispW = computed(() => {
    if (!natW.value) return MAX_W
    const r = natW.value / natH.value
    let w = MAX_W, h = w / r
    if (h > MAX_H) { h = MAX_H; w = h * r }
    return Math.round(w)
})
const dispH = computed(() => {
    if (!natH.value) return MAX_H
    return Math.round(dispW.value / (natW.value / natH.value))
})

const cropStyle = computed(() => ({
    left: crop.x + 'px',
    top: crop.y + 'px',
    width: crop.w + 'px',
    height: crop.h + 'px',
}))

watch(selectedIdx, () => {
    ready.value = false
    playing.value = false
})

function onMeta() {
    const v = videoEl.value
    natW.value = v.videoWidth
    natH.value = v.videoHeight
    duration.value = v.duration
    v.currentTime = Math.min(1, v.duration * 0.1)
    v.pause()
    ready.value = true
    initCrop()
}

function onTimeUpdate() {
    if (videoEl.value) currentTime.value = videoEl.value.currentTime
}

function initCrop() {
    const w = dispW.value, h = dispH.value
    let ch = h * 0.85, cw = ch * CROP_AR
    if (cw > w * 0.85) { cw = w * 0.85; ch = cw / CROP_AR }
    crop.x = (w - cw) / 2
    crop.y = (h - ch) / 2
    crop.w = cw
    crop.h = ch
}

// --- Playback ---

function togglePlay() {
    const v = videoEl.value
    if (!v) return
    if (playing.value) { v.pause() } else { v.play() }
    playing.value = !playing.value
}

function stepFrame(dir) {
    const v = videoEl.value
    if (!v) return
    v.pause()
    playing.value = false
    v.currentTime = Math.max(0, Math.min(v.duration, v.currentTime + dir / 30))
}

function onScrub(e) {
    const v = videoEl.value
    if (!v) return
    v.pause()
    playing.value = false
    v.currentTime = parseFloat(e.target.value)
}

function fmtTime(t) {
    const m = Math.floor(t / 60)
    const s = Math.floor(t % 60)
    return `${m}:${String(s).padStart(2, '0')}`
}

// --- Crop drag / resize ---

let drag = null

function startMove(e) {
    drag = { type: 'move', mx: e.clientX, my: e.clientY, sx: crop.x, sy: crop.y }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
}

function startResize(corner, e) {
    drag = { type: 'resize', corner, mx: e.clientX, my: e.clientY, sx: crop.x, sy: crop.y, sw: crop.w, sh: crop.h }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e) {
    if (!drag) return
    const dx = e.clientX - drag.mx
    const dy = e.clientY - drag.my
    if (drag.type === 'move') {
        crop.x = clamp(drag.sx + dx, 0, dispW.value - crop.w)
        crop.y = clamp(drag.sy + dy, 0, dispH.value - crop.h)
    } else {
        resizeCrop(drag.corner, dx, dy, drag)
    }
}

function onMouseUp() {
    drag = null
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
}

onUnmounted(() => {
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
})

function clamp(v, min, max) { return Math.max(min, Math.min(max, v)) }

function resizeCrop(corner, dx, dy, s) {
    const dw = dispW.value, dh = dispH.value
    let nx = s.sx, ny = s.sy, nw = s.sw, nh = s.sh

    if (corner === 'br') {
        nw = Math.max(MIN_CROP, s.sw + dx)
        nh = nw / CROP_AR
        if (nx + nw > dw) { nw = dw - nx; nh = nw / CROP_AR }
        if (ny + nh > dh) { nh = dh - ny; nw = nh * CROP_AR }
    } else if (corner === 'bl') {
        nw = Math.max(MIN_CROP, s.sw - dx)
        nh = nw / CROP_AR
        nx = s.sx + s.sw - nw
        if (nx < 0) { nx = 0; nw = s.sx + s.sw; nh = nw / CROP_AR }
        if (ny + nh > dh) { nh = dh - ny; nw = nh * CROP_AR; nx = s.sx + s.sw - nw }
    } else if (corner === 'tr') {
        nw = Math.max(MIN_CROP, s.sw + dx)
        nh = nw / CROP_AR
        ny = s.sy + s.sh - nh
        if (nx + nw > dw) { nw = dw - nx; nh = nw / CROP_AR; ny = s.sy + s.sh - nh }
        if (ny < 0) { ny = 0; nh = s.sy + s.sh; nw = nh * CROP_AR }
    } else if (corner === 'tl') {
        nw = Math.max(MIN_CROP, s.sw - dx)
        nh = nw / CROP_AR
        nx = s.sx + s.sw - nw
        ny = s.sy + s.sh - nh
        if (nx < 0) { nx = 0; nw = s.sx + s.sw; nh = nw / CROP_AR; ny = s.sy + s.sh - nh }
        if (ny < 0) { ny = 0; nh = s.sy + s.sh; nw = nh * CROP_AR; nx = s.sx + s.sw - nw }
    }

    if (nw < MIN_CROP) { nw = MIN_CROP; nh = nw / CROP_AR }
    crop.x = nx; crop.y = ny; crop.w = nw; crop.h = nh
}

// --- Capture ---

function capture() {
    const v = videoEl.value
    if (!v) return
    v.pause()
    playing.value = false

    const scaleX = v.videoWidth / dispW.value
    const scaleY = v.videoHeight / dispH.value
    const sx = crop.x * scaleX
    const sy = crop.y * scaleY
    const sw = crop.w * scaleX
    const sh = crop.h * scaleY

    let ow = sw, oh = sh
    if (ow > 640) { oh = oh * 640 / ow; ow = 640 }

    const canvas = document.createElement('canvas')
    canvas.width = Math.round(ow)
    canvas.height = Math.round(oh)
    const ctx = canvas.getContext('2d')
    ctx.drawImage(v, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height)

    canvas.toBlob(blob => {
        if (blob) emit('accept', blob)
    }, 'image/jpeg', 0.92)
}
</script>

<style scoped>
.tp-overlay {
    position: fixed; inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex; align-items: center; justify-content: center;
    z-index: 10001; padding: 20px;
}

.tp-modal {
    background: var(--bg-elevated, #1e1e2e);
    border: 1px solid var(--border, #2a2a3e);
    border-radius: 12px;
    display: flex; flex-direction: column;
    max-width: 90vw; max-height: 90vh;
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.5);
}

.tp-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px 20px; border-bottom: 1px solid var(--border);
}
.tp-header h2 { font-size: 16px; font-weight: 600; margin: 0; }

.tp-close {
    background: none; border: none; color: var(--text-faint); font-size: 22px;
    cursor: pointer; padding: 0 4px; border-radius: 4px; line-height: 1;
}
.tp-close:hover { color: var(--text-primary); background: var(--border); }

.tp-body { padding: 16px 20px; overflow-y: auto; }

.tp-video-select {
    display: flex; align-items: center; gap: 10px; margin-bottom: 12px;
}
.tp-video-select label { font-size: 12px; font-weight: 500; color: var(--text-muted); }
.tp-select {
    flex: 1; padding: 6px 10px;
    background: var(--bg-input, #16162a); border: 1px solid var(--border);
    border-radius: 6px; color: #ddd; font-size: 13px; cursor: pointer;
}

.tp-stage {
    position: relative;
    display: inline-block;
    line-height: 0;
    border-radius: 8px;
    overflow: hidden;
    background: #000;
}

.tp-stage video {
    display: block;
}

.tp-crop-area {
    position: absolute; top: 0; left: 0;
    overflow: hidden;
    cursor: crosshair;
}

.tp-crop-rect {
    position: absolute;
    border: 2px solid rgba(255, 255, 255, 0.85);
    box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.55);
    cursor: move;
    z-index: 2;
}

.tp-handle {
    position: absolute;
    width: 12px; height: 12px;
    background: #fff;
    border: 1px solid rgba(0, 0, 0, 0.3);
    border-radius: 2px;
    z-index: 3;
}
.tp-handle.tl { top: -6px; left: -6px; cursor: nw-resize; }
.tp-handle.tr { top: -6px; right: -6px; cursor: ne-resize; }
.tp-handle.bl { bottom: -6px; left: -6px; cursor: sw-resize; }
.tp-handle.br { bottom: -6px; right: -6px; cursor: se-resize; }

/* Controls */
.tp-controls {
    display: flex; align-items: center; gap: 6px;
    margin-top: 12px; padding: 8px 0;
}

.tp-play-btn {
    width: 32px; height: 32px;
    border-radius: 50%;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    border: none; color: #fff; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; flex-shrink: 0;
}
.tp-play-btn:hover { filter: brightness(1.15); }
.tp-play-icon { margin-left: 2px; }
.tp-pause { font-size: 10px; letter-spacing: 1px; }

.tp-ctrl-btn {
    width: 28px; height: 28px;
    border-radius: 6px;
    background: var(--bg-elevated, #1e1e2e); border: 1px solid var(--border);
    color: var(--text-muted); cursor: pointer;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.tp-ctrl-btn:hover { color: var(--text-primary); border-color: var(--border-hover); }

.tp-scrubber {
    flex: 1; height: 4px;
    -webkit-appearance: none; appearance: none;
    background: var(--border); border-radius: 2px; outline: none;
    cursor: pointer;
}
.tp-scrubber::-webkit-slider-thumb {
    -webkit-appearance: none; appearance: none;
    width: 14px; height: 14px; border-radius: 50%;
    background: #3b82f6; border: 2px solid #fff;
    cursor: pointer; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
}

.tp-time {
    font-size: 12px; color: var(--text-faint);
    font-variant-numeric: tabular-nums;
    min-width: 40px; text-align: right; flex-shrink: 0;
}

/* Footer */
.tp-footer {
    display: flex; justify-content: flex-end; gap: 8px;
    padding: 14px 20px; border-top: 1px solid var(--border);
}

.tp-btn {
    padding: 8px 18px; border: none; border-radius: 8px;
    font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s;
}
.tp-btn-primary { background: #3b82f6; color: white; }
.tp-btn-primary:hover:not(:disabled) { background: #2563eb; }
.tp-btn-primary:disabled { opacity: 0.45; cursor: default; }
.tp-btn-ghost { background: transparent; color: var(--text-muted); border: 1px solid var(--border); }
.tp-btn-ghost:hover { background: var(--bg-elevated); color: var(--text-secondary); }
</style>
