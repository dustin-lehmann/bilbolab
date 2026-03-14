<template>
    <div class="video-viewer" v-if="item">
        <div class="viewer-header">
            <div class="nav-section">
                <button v-if="item.folderPath && item.folderPath.length > 0" class="back-btn" @click="goBack">
                    &larr; Back
                </button>
                <router-link v-else to="/" class="back-btn">&larr; Home</router-link>

                <div class="breadcrumb">
                    <router-link to="/" class="breadcrumb-item">Home</router-link>
                    <template v-for="(crumb, index) in item.folderPath" :key="crumb.id">
                        <span class="breadcrumb-sep">/</span>
                        <router-link :to="`/folder/${crumb.id}`" class="breadcrumb-item">
                            {{ crumb.name }}
                        </router-link>
                    </template>
                    <span class="breadcrumb-sep">/</span>
                    <span class="breadcrumb-item current">{{ item.title }}</span>
                </div>
            </div>
            <div class="header-info">
                <div class="title-row">
                    <h1 class="item-title">{{ item.title }}</h1>
                    <span class="item-type-badge video">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polygon points="5 3 19 12 5 21 5 3"/>
                        </svg>
                        Video
                    </span>
                </div>
                <p v-if="item.description" class="item-description">{{ item.description }}</p>
                <div class="header-extras">
                    <DocRefBadge :item="item" />
                    <button v-if="item.additionalInfo" class="info-btn" @click="showInfo = true">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                        More Information
                    </button>
                </div>
                <InfoPanel :visible="showInfo" :content="item.additionalInfo || ''" @close="showInfo = false" />
            </div>
        </div>

        <div class="video-area" ref="videoAreaRef">
            <video
                ref="videoRef"
                :src="`/videos/${item.file}`"
                @loadedmetadata="onVideoLoaded"
                @timeupdate="onTimeUpdate"
                @ended="onVideoEnded"
                @error="onVideoError"
                preload="auto"
                playsinline
            ></video>
            <VideoOverlay
                :current-time="currentTime"
                :overlays="item.overlays"
                :overlay-style="item.overlayStyle"
            />
            <div v-if="videoError" class="video-error">
                Video not found: {{ item.file }}
            </div>
        </div>

        <div class="controls-container">
            <div class="timeline-controls">
                <button class="play-btn" @click="togglePlayPause">
                    <span v-if="isPlaying" class="pause-icon">&#10074;&#10074;</span>
                    <span v-else class="play-icon">&#9654;</span>
                </button>

                <div class="timeline-wrapper">
                    <div class="time-display">
                        {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
                    </div>

                    <div class="timeline-with-markers">
                        <div class="timeline" @mousedown="startDrag">
                            <div class="timeline-progress" :style="{ width: progressPercent + '%' }"></div>
                            <div class="timeline-handle" :style="{ left: progressPercent + '%' }"></div>

                            <div
                                v-for="(marker, index) in (item.markers || [])"
                                :key="index"
                                class="timeline-marker"
                                :class="{ highlighted: hoveredMarkerIndex === index }"
                                :style="{ left: getMarkerPosition(marker.time) + '%' }"
                                @click.stop="seekTo(marker.time)"
                            ></div>
                        </div>

                        <div class="markers-labels" v-if="item.markers && item.markers.length > 0">
                            <button
                                v-for="(marker, index) in item.markers"
                                :key="index"
                                class="marker-label"
                                :class="{ active: isNearMarker(marker.time), highlighted: hoveredMarkerIndex === index }"
                                :style="{ left: getMarkerPosition(marker.time) + '%' }"
                                @click="seekTo(marker.time)"
                                @mouseenter="hoveredMarkerIndex = index"
                                @mouseleave="hoveredMarkerIndex = null"
                            >
                                {{ marker.label }}
                            </button>
                        </div>
                    </div>
                </div>

                <div class="playback-controls">
                    <div class="volume-controls">
                        <button class="mute-btn" @click="toggleMute" :title="isMuted ? 'Unmute' : 'Mute'">
                            <svg v-if="isMuted || volume === 0" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                                <line x1="23" y1="9" x2="17" y2="15"/>
                                <line x1="17" y1="9" x2="23" y2="15"/>
                            </svg>
                            <svg v-else-if="volume < 0.5" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                                <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
                            </svg>
                            <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
                            </svg>
                        </button>
                        <input
                            type="range"
                            class="volume-slider"
                            min="0"
                            max="1"
                            step="0.05"
                            :value="volume"
                            @input="setVolume"
                        >
                    </div>
                    <div class="speed-dropdown" :class="{ open: speedDropdownOpen }">
                        <button class="speed-btn" @click="toggleSpeedDropdown">
                            {{ playbackSpeed }}x
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M6 9l6 6 6-6"/>
                            </svg>
                        </button>
                        <div class="speed-options" v-if="speedDropdownOpen">
                            <button
                                v-for="speed in speeds"
                                :key="speed"
                                class="speed-option"
                                :class="{ active: speed === playbackSpeed }"
                                @click="setSpeed(speed)"
                            >
                                {{ speed }}x
                            </button>
                        </div>
                    </div>
                    <button class="fullscreen-btn" @click="toggleFullscreen" title="Fullscreen (F)">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    </div>

    <div v-else class="loading">
        Loading video...
    </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import DocRefBadge from './DocRefBadge.vue'
import InfoPanel from './InfoPanel.vue'
import VideoOverlay from './VideoOverlay.vue'

const showInfo = ref(false)

const props = defineProps({
    id: String
})

const router = useRouter()

const item = ref(null)
const videoRef = ref(null)
const videoAreaRef = ref(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const playbackSpeed = ref(1)
const videoError = ref(false)
const speedDropdownOpen = ref(false)
const isMuted = ref(false)
const volume = ref(1)
const hoveredMarkerIndex = ref(null)
const isDragging = ref(false)
const wasPlayingBeforeDrag = ref(false)

const speeds = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2]

const progressPercent = computed(() => {
    if (duration.value === 0) return 0
    return (currentTime.value / duration.value) * 100
})

function goBack() {
    if (item.value?.folderPath && item.value.folderPath.length > 0) {
        const parent = item.value.folderPath[item.value.folderPath.length - 1]
        router.push(`/folder/${parent.id}`)
    } else {
        router.push('/')
    }
}

async function loadItem() {
    try {
        const response = await fetch(`/api/experiments/${props.id}`)
        if (!response.ok) throw new Error('Failed to load item')
        item.value = await response.json()
    } catch (error) {
        console.error('Error loading video item:', error)
    }
}

function onVideoLoaded() {
    if (videoRef.value) {
        duration.value = videoRef.value.duration
        videoRef.value.muted = isMuted.value
        videoRef.value.volume = volume.value
    }
}

function onTimeUpdate() {
    if (videoRef.value && !isDragging.value) {
        currentTime.value = videoRef.value.currentTime
    }
}

function onVideoEnded() {
    isPlaying.value = false
}

function onVideoError() {
    videoError.value = true
}

function togglePlayPause() {
    if (!videoRef.value) return

    if (isPlaying.value) {
        videoRef.value.pause()
        isPlaying.value = false
    } else {
        // If video ended, restart from beginning
        if (duration.value > 0 && currentTime.value >= duration.value - 0.1) {
            videoRef.value.currentTime = 0
            currentTime.value = 0
        }
        videoRef.value.playbackRate = playbackSpeed.value
        videoRef.value.play().catch(e => console.log('Play error:', e))
        isPlaying.value = true
    }
}

function seekTo(time) {
    if (!videoRef.value) return
    videoRef.value.currentTime = time
    currentTime.value = time
}

function getMarkerPosition(time) {
    if (duration.value === 0) return 0
    return (time / duration.value) * 100
}

function isNearMarker(time) {
    return Math.abs(currentTime.value - time) < 0.5
}

function formatTime(seconds) {
    if (isNaN(seconds) || seconds === 0) return '0:00'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
}

// Timeline drag handling
let timelineEl = null
let seeking = false
let pendingTime = null

function performSeek(time) {
    if (!videoRef.value) return

    if (seeking) {
        pendingTime = time
        currentTime.value = time
        return
    }

    seeking = true
    pendingTime = null
    currentTime.value = time

    const video = videoRef.value

    const onSeeked = () => {
        video.removeEventListener('seeked', onSeeked)
        seeking = false

        if (pendingTime !== null && isDragging.value) {
            const pt = pendingTime
            pendingTime = null
            performSeek(pt)
        }
    }

    video.addEventListener('seeked', onSeeked)
    video.currentTime = time
}

function startDrag(event) {
    event.preventDefault()
    isDragging.value = true
    timelineEl = event.currentTarget
    seeking = false
    pendingTime = null

    if (!videoRef.value) return

    wasPlayingBeforeDrag.value = isPlaying.value

    videoRef.value.pause()
    isPlaying.value = false

    const rect = timelineEl.getBoundingClientRect()
    const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    const time = percent * duration.value
    performSeek(time)

    window.addEventListener('mousemove', onDrag)
    window.addEventListener('mouseup', stopDrag)
}

function onDrag(event) {
    if (!isDragging.value || !timelineEl || !videoRef.value) return

    const rect = timelineEl.getBoundingClientRect()
    const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    const time = percent * duration.value
    performSeek(time)
}

function stopDrag() {
    if (!isDragging.value) return

    if (pendingTime !== null && videoRef.value) {
        videoRef.value.currentTime = pendingTime
        currentTime.value = pendingTime
    }
    seeking = false
    pendingTime = null

    if (wasPlayingBeforeDrag.value && videoRef.value) {
        videoRef.value.play().catch(() => {})
        isPlaying.value = true
    }

    isDragging.value = false
    timelineEl = null
    window.removeEventListener('mousemove', onDrag)
    window.removeEventListener('mouseup', stopDrag)
}

// Volume
function loadVolumeSettings() {
    const savedMuted = localStorage.getItem('videoMuted')
    const savedVolume = localStorage.getItem('videoVolume')
    if (savedMuted !== null) {
        isMuted.value = savedMuted === 'true'
    }
    if (savedVolume !== null) {
        volume.value = parseFloat(savedVolume)
    }
}

function saveVolumeSettings() {
    localStorage.setItem('videoMuted', isMuted.value.toString())
    localStorage.setItem('videoVolume', volume.value.toString())
}

function toggleMute() {
    isMuted.value = !isMuted.value
    applyVolume()
    saveVolumeSettings()
}

function setVolume(event) {
    volume.value = parseFloat(event.target.value)
    if (volume.value > 0 && isMuted.value) {
        isMuted.value = false
    }
    applyVolume()
    saveVolumeSettings()
}

function applyVolume() {
    if (videoRef.value) {
        videoRef.value.volume = volume.value
        videoRef.value.muted = isMuted.value
    }
}

// Speed
function toggleSpeedDropdown() {
    speedDropdownOpen.value = !speedDropdownOpen.value
}

function setSpeed(speed) {
    playbackSpeed.value = speed
    speedDropdownOpen.value = false
    if (videoRef.value) {
        videoRef.value.playbackRate = speed
    }
}

// Fullscreen
function toggleFullscreen() {
    const el = videoAreaRef.value || videoRef.value
    if (!el) return
    if (document.fullscreenElement) {
        document.exitFullscreen()
    } else {
        el.requestFullscreen().catch(e => console.log('Fullscreen error:', e))
    }
}

// Keyboard shortcuts
function handleKeydown(event) {
    // Ignore when typing in inputs
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA' || event.target.tagName === 'SELECT' || event.target.isContentEditable) return

    switch (event.code) {
        case 'Space':
            event.preventDefault()
            togglePlayPause()
            break
        case 'ArrowLeft':
            event.preventDefault()
            seekTo(Math.max(0, currentTime.value - 5))
            break
        case 'ArrowRight':
            event.preventDefault()
            seekTo(Math.min(duration.value, currentTime.value + 5))
            break
        case 'KeyF':
            event.preventDefault()
            toggleFullscreen()
            break
    }
}

function handleClickOutside(event) {
    if (speedDropdownOpen.value && !event.target.closest('.speed-dropdown')) {
        speedDropdownOpen.value = false
    }
}

watch(() => props.id, () => {
    loadItem()
})

onMounted(async () => {
    loadVolumeSettings()
    await loadItem()
    window.addEventListener('keydown', handleKeydown)
    window.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
    window.removeEventListener('keydown', handleKeydown)
    window.removeEventListener('click', handleClickOutside)
    window.removeEventListener('mousemove', onDrag)
    window.removeEventListener('mouseup', stopDrag)
    if (videoRef.value) {
        videoRef.value.pause()
    }
})
</script>

<style scoped>
.video-viewer {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    overflow: hidden;
    position: relative;
}

.viewer-header {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 10px;
    flex-shrink: 0;
}

.nav-section {
    display: flex;
    align-items: center;
    gap: 8px;
}

.breadcrumb {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    flex-wrap: wrap;
}

.breadcrumb-sep {
    color: var(--border-hover);
}

.back-btn {
    color: var(--text-primary);
    text-decoration: none;
    font-size: 13px;
    padding: 5px 12px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    border-radius: 6px;
    transition: all 0.2s;
    flex-shrink: 0;
    cursor: pointer;
}

.back-btn:hover {
    background: var(--border);
    border-color: var(--border-hover);
}

.breadcrumb-item {
    color: var(--text-muted);
    text-decoration: none;
    padding: 4px 10px;
    background: var(--bg-elevated);
    border-radius: 6px;
    transition: all 0.2s;
}

.breadcrumb-item:hover:not(.current) {
    background: var(--border);
    color: var(--text-primary);
}

.breadcrumb-item.current {
    color: var(--text-primary);
    background: var(--border-light);
}

.title-row {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}

.item-title {
    font-size: 20px;
    font-weight: 600;
    margin: 0;
}

.item-type-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 500;
    padding: 4px 10px;
    border-radius: 6px;
}

.item-type-badge.video {
    background: rgba(139, 92, 246, 0.15);
    color: #a78bfa;
    border: 1px solid rgba(139, 92, 246, 0.3);
}

.item-description {
    color: var(--text-muted);
    font-size: 13px;
    margin-top: 4px;
}

/* Video Area */
.video-area {
    flex: 1;
    min-height: 0;
    position: relative;
    background: transparent;
    border-radius: 12px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
}

.video-area:fullscreen {
    background: #000;
}

.video-area video {
    width: 100%;
    height: 100%;
    object-fit: contain;
}

.video-error {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-elevated);
    color: var(--text-faint);
    font-size: 14px;
}

/* Controls */
.controls-container {
    background: var(--code-bg);
    border-radius: 10px;
    padding: 10px 16px;
    margin-top: 8px;
    flex-shrink: 0;
}

.timeline-controls {
    display: flex;
    align-items: flex-start;
    gap: 14px;
}

.play-btn {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: linear-gradient(135deg, #8b5cf6, #7c3aed);
    border: none;
    color: white;
    font-size: 13px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.2s, box-shadow 0.2s;
    flex-shrink: 0;
    margin-top: 9px;
}

.play-btn:hover {
    transform: scale(1.08);
    box-shadow: 0 3px 14px rgba(139, 92, 246, 0.4);
}

.play-icon { margin-left: 2px; }
.pause-icon { letter-spacing: 2px; font-size: 11px; }

.timeline-wrapper {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 5px;
}

.time-display {
    font-size: 12px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    display: flex;
    align-items: center;
    gap: 8px;
}

.timeline-with-markers {
    position: relative;
}

.timeline {
    position: relative;
    height: 8px;
    background: var(--border);
    border-radius: 4px;
    cursor: pointer;
    user-select: none;
}

.timeline:active {
    cursor: grabbing;
}

.timeline-progress {
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    background: linear-gradient(90deg, #8b5cf6, #7c3aed);
    border-radius: 4px;
    pointer-events: none;
}

.timeline-handle {
    position: absolute;
    top: 50%;
    width: 16px;
    height: 16px;
    background: white;
    border-radius: 50%;
    transform: translate(-50%, -50%);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    pointer-events: none;
}

.timeline-marker {
    position: absolute;
    top: 50%;
    width: 4px;
    height: 16px;
    background: #f59e0b;
    transform: translate(-50%, -50%);
    cursor: pointer;
    border-radius: 2px;
    transition: all 0.2s;
}

.timeline-marker:hover,
.timeline-marker.highlighted {
    background: #fbbf24;
    height: 20px;
    box-shadow: 0 0 8px rgba(245, 158, 11, 0.5);
}

.markers-labels {
    position: relative;
    height: 24px;
    margin-top: 5px;
}

.marker-label {
    position: absolute;
    transform: translateX(-50%);
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    color: var(--text-muted);
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
}

.marker-label:hover,
.marker-label.highlighted {
    background: var(--border);
    border-color: #f59e0b;
    color: var(--text-primary);
}

.marker-label.active {
    background: #f59e0b;
    border-color: #f59e0b;
    color: #000;
}

.playback-controls {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-top: 12px;
}

.volume-controls {
    display: flex;
    align-items: center;
    gap: 8px;
}

.mute-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s;
}

.mute-btn:hover {
    color: var(--text-primary);
}

.volume-slider {
    width: 80px;
    height: 4px;
    -webkit-appearance: none;
    appearance: none;
    background: var(--border-light);
    border-radius: 2px;
    cursor: pointer;
}

.volume-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 12px;
    height: 12px;
    background: var(--text-primary);
    border-radius: 50%;
    cursor: pointer;
    transition: transform 0.2s;
}

.volume-slider::-webkit-slider-thumb:hover {
    transform: scale(1.2);
}

.volume-slider::-moz-range-thumb {
    width: 12px;
    height: 12px;
    background: var(--text-primary);
    border-radius: 50%;
    cursor: pointer;
    border: none;
}

.speed-dropdown {
    position: relative;
}

.speed-btn {
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    color: var(--text-primary);
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 8px;
}

.speed-btn:hover {
    background: var(--border);
    border-color: var(--border-hover);
}

.speed-btn svg {
    transition: transform 0.2s;
}

.speed-dropdown.open .speed-btn svg {
    transform: rotate(180deg);
}

.speed-options {
    position: absolute;
    bottom: 100%;
    right: 0;
    margin-bottom: 8px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    overflow: hidden;
    min-width: 80px;
}

.speed-option {
    width: 100%;
    background: none;
    border: none;
    color: var(--text-muted);
    padding: 10px 16px;
    text-align: left;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.2s;
}

.speed-option:hover {
    background: var(--border);
    color: var(--text-primary);
}

.speed-option.active {
    background: #8b5cf6;
    color: var(--text-primary);
}

.fullscreen-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s;
}

.fullscreen-btn:hover {
    color: var(--text-primary);
}

.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 50vh;
    color: var(--text-muted);
}
</style>
